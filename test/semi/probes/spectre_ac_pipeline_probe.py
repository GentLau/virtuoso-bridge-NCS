# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =====================================================================
"""Spectre AC 链路探针（第五轮新增，真机）：解析命名耦合 + measure 默认 x 契约。

两个独立缺陷面（都在真机复现，纯 RC 网表，不依赖 PDK）：

* A：``parse_psf_directory`` 只认 ``ac.ac`` / ``ac.ac.ac`` / ``*.ac.ac``
  （``src/pyapi/packages/_spectre_util.py:405-409``）。spectre 默认把分析写成
  ``<分析名>.ac``，所以分析名不是字面 ``ac``（例如 ``ac1``）时**整个 AC 数据集丢失**：
  ``spectre.run`` 返回 ``status=partial``、``analyses=[]``。
* B：即使解析成功（分析名 ``ac``），键名带 ``ac_`` 前缀（``ac_freq``/``ac_out``），
  而 ``spectre.measure`` 的 AC 指标默认 ``x="freq"``（spec 7-spectre §measure 明写
  默认 ``freq``）→ 按 spec 形状（只给 signal/frequency）调用必然报
  ``ValueError: signal 'freq' is missing``。离线单测用的是手写 ``freq`` 键数据，
  所以这条链路此前从未被真实 AC 数据验证过。

verdict ∈ {clean, ac-name-coupling, measure-default-x, both, error}

用法::

    python test/semi/probes/spectre_ac_pipeline_probe.py
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
_RUNNERS = Path(__file__).resolve().parents[3] / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
DEFAULT_TOKEN = "d6af595b342647b58ec63ca6"
SPECTRE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/spectre/spectre"

NETLIST = """simulator lang=spectre
global 0

V1 (in 0) vsource dc=0 mag=1
R1 (in out) resistor r=1k
C1 (out 0) capacitor c=1p

{analysis} ac start=1k stop=1G dec=10
"""


def call(token: str, operation: str, **fields: Any) -> dict:
    body = json.dumps({"operation": operation, "token": token, **fields},
                      ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def run_ac(token: str, job: str, analysis: str, stage: Path) -> dict:
    netlist = stage / f"{job}.scs"
    netlist.write_text(NETLIST.format(analysis=analysis), encoding="utf-8")
    call(token, "basic.command.run",
         cmd=f"rm -rf {SPECTRE_ROOT}/{job} && echo cleaned", timeout=120)
    response = call(token, "spectre.run",
                    tasks=[{"job": job, "netlist": str(netlist), "parse": "auto"}],
                    parse="auto", download=True, keep_run_dir=True, max_workers=1,
                    timeout=600)
    run = (((_c1_wrapper(response)).get("value") or {}).get("runs") or [{}])[0]
    return run.get("value") or {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "test" / "artifacts" / "evidence" / "round4-probes")
    args = ap.parse_args(argv)
    require_environment(base=API, token=args.token)
    stage = args.out / "spectre-ac"
    stage.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {"token": args.token}
    try:
        named_ac1 = run_ac(args.token, "acpipe_named_ac1", "ac1", stage)
        report["A_named_ac1"] = {
            "status": named_ac1.get("status"),
            "analyses": named_ac1.get("analyses"),
            "has_ac_data": any(str(k).startswith("ac_") for k in (_c1_wrapper(named_ac1))),
        }
        report["A_ok"] = bool(named_ac1.get("analyses"))

        named_ac = run_ac(args.token, "acpipe_named_ac", "ac", stage)
        report["B_named_ac"] = {
            "status": named_ac.get("status"),
            "analyses": named_ac.get("analyses"),
            "keys": sorted(_c1_wrapper(named_ac))[:6],
        }
        report["B_parse_ok"] = bool(named_ac.get("analyses"))
        if report["B_parse_ok"]:
            spec_shape = call(
                args.token, "spectre.measure", data=_c1_wrapper(named_ac),
                metrics=[{"type": "ac_magnitude", "signal": "out",
                          "frequency": 1e6, "scale": "db"}])
            value = ((_c1_wrapper(spec_shape)).get("value") or {})
            metrics = value.get("metrics") or []
            report["B_spec_shape"] = metrics
            report["B_spec_shape_ok"] = bool(metrics) and bool(metrics[0].get("ok"))
            explicit = call(
                args.token, "spectre.measure", data=_c1_wrapper(named_ac),
                metrics=[{"type": "ac_magnitude", "signal": "ac_out", "x": "ac_freq",
                          "frequency": 1e6, "scale": "db"}])
            report["B_explicit_x"] = (((_c1_wrapper(explicit)).get("value")
                                       or {}).get("metrics"))
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"

    a_ok, b_ok = report.get("A_ok", False), report.get("B_spec_shape_ok", False)
    report["verdict"] = ("clean" if a_ok and b_ok else
                         "both" if not a_ok and not b_ok else
                         "ac-name-coupling" if not a_ok else "measure-default-x")
    path = args.out / "round4-spectre-ac-pipeline.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "B_spec_shape"},
                     ensure_ascii=False))
    print(f"verdict: {report['verdict']}")
    print(f"evidence: {path}")
    return 0 if report["verdict"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
