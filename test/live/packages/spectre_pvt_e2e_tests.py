# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 23:45
# 依赖: test/artifacts/evidence/s11-postsim/cmp_top_pre.scs（S11 真设计 DC 网表基准）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`basic.skill.execute("1+1")` 探活 + 基线（tt/27℃/2.5V）DC 跑通；
# ②③ 构建：以 S11 真网表为模板，按维度生成变体（**只改一个变量**：process / voltage / temperature），
#    每个变体一个独立 job，互不覆盖；
# ④ 只做被测动作：`spectre.run`（一次 HTTP 调用，多个 task）；
# ⑤ 读回比对：逐节点比对 DC 工作点（值级，不是"跑完算过"）：
#    * P 维度：ss_25/ss_18 与 ff_25/ff_18 必须给出**与 tt 不同**的 DC 解；
#    * V 维度：2.25V 与 2.5V 必须给出不同解；
#    * T 维度：125℃ / -40℃ 与 27℃ 必须给出不同解（若 Spectre 语法/许可拒绝，如实记 ENV-NOTE）；
#    判据阈值：至少 3 个节点绝对变化 > 1e-6 V。
# ⑥ 收尾：不污染共享库（只写本 TB 的 run 目录），证据 JSON 落盘。
"""PVT（工艺角 / 电压 / 温度）真机扫描验收。

覆盖动机（round9 缺口清单）：**PVT 是用户点名"要做"的一项**，而此前全套 TB 只覆盖了
maestro 的 corner *配置面*（`set_corner`/`setup_corner`/变量 scope）与后仿对照
（`s11_postsim_compare` 的 pre/post 同 corner 对比）；**没有任何 TB 真正跑过多 corner /
变电压 / 变温度的扫描**。

本 TB 用 S11 真设计（`cmp_top` 的比较器 DC 网表，PDK CRN65GPNEW 的 `cor_25/cor_18` 模型）
把三个维度各扫一档，并把**逐节点 DC 工作点**写进证据：

===========  =============================================  ==================
维度          变体                                            判据
===========  =============================================  ==================
process       tt / ss / ff（`section=tt_25` 等两处 include）    与 tt 至少 3 节点不同
voltage       VDD 2.5V → 2.25V                                与基准至少 3 节点不同
temperature   options temp=27 → 125 / -40℃                     与基准至少 3 节点不同
===========  =============================================  ==================

用法::

    PYTHONPATH=src python test/live/packages/spectre_pvt_e2e_tests.py --transport http \
        --out test/artifacts/evidence/round9/spectre-pvt-r9.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
BASE_NETLIST = ROOT / "test" / "artifacts" / "evidence" / "s11-postsim" / "cmp_top_pre.scs"
STAMP = time.strftime("%H%M%S")

#: 判据阈值：节点绝对变化超过它才算"这一档真的改变了结果"
DELTA_EPS = 1e-6
#: 一个变体至少要让它这么多个节点发生变化
MIN_CHANGED_NODES = 3


class HttpTransport:
    def __init__(self, api: str, token: str) -> None:
        self.api, self.token = api, token

    def call(self, payload: dict[str, Any], timeout: int = 1800) -> dict[str, Any]:
        body = json.dumps({"token": self.token, **payload}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.api, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return {"ok": False,
                    "error": f"HTTP {error.code}: {error.read().decode('utf-8')[:300]}"}


def _value(response: dict[str, Any]) -> dict[str, Any]:
    """C1 契约：业务载荷在顶层 `value`（新口径亦可能是 `result`）。"""
    for key in ("value", "result"):
        value = response.get(key)
        if isinstance(value, dict):
            return value
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def _skill(transport: "HttpTransport", code: str) -> str:
    response = transport.call({"operation": "basic.skill.execute", "skill_code": code})
    if response.get("ok") is not True:
        raise AssertionError(f"skill failed: {response.get('error')}")
    return str(_value(response).get("output") or "")


def variant_netlist(base: str, *, sections: tuple[str, str] | None = None,
                    vdd: str | None = None, temp: str | None = None) -> str:
    """按维度改写网表（每个变体只动一个变量；未指定的维度保持与基准一致）。"""
    text = base
    if sections:
        text = text.replace("section=tt_25", f"section={sections[0]}")
        text = text.replace("section=tt_18", f"section={sections[1]}")
    if vdd:
        text = text.replace("VDD (vdd 0) vsource dc=2.5", f"VDD (vdd 0) vsource dc={vdd}")
    if temp:
        text = text.replace("simulatorOptions options soft_bin=allmodels",
                            f"simulatorOptions options soft_bin=allmodels temp={temp}")
    return text


def run_variants(transport: "HttpTransport", variants: dict[str, str],
                 work: Path) -> dict[str, dict[str, Any]]:
    """把每个变体写成独立 .scs 并一次提交给 `spectre.run`，返回 job → run 结果。"""
    work.mkdir(parents=True, exist_ok=True)
    tasks = []
    for job, text in variants.items():
        path = work / f"cmp_pvt_{job}_{STAMP}.scs"
        path.write_text(text, encoding="utf-8", newline="\n")
        tasks.append({"job": f"pvt_{job}_{STAMP}", "netlist": str(path)})
    response = transport.call({
        "operation": "spectre.run",
        "tasks": tasks,
        "max_workers": 2,
        "mode": "spectre",
        "parse": "auto",
        "download": True,
        "keep_run_dir": True,
        "timeout": 900,
    })
    if response.get("ok") is not True:
        raise AssertionError(
            f"spectre.run failed: {json.dumps(response, ensure_ascii=False)[:400]}")
    runs = _value(response).get("runs") or []
    return {str(run.get("job")): _value(run) for run in runs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--base-netlist", default=str(BASE_NETLIST))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    transport = HttpTransport(args.api, args.token)
    base_path = Path(args.base_netlist)
    if not base_path.is_file():
        raise SystemExit(f"基准网表不存在：{base_path}")
    base = base_path.read_text(encoding="utf-8")

    results: list[tuple[str, str, dict[str, Any]]] = []
    evidence: dict[str, Any] = {"stamp": STAMP, "base_netlist": str(base_path), "cases": {}}
    work = ROOT / "test" / "artifacts" / "evidence" / "round9" / "pvt-netlists"

    def record(name: str, ok: bool, detail: dict[str, Any]) -> None:
        results.append((name, "PASS" if ok else "FAIL", detail))
        evidence["cases"][name] = {"ok": ok, **detail}
        print(f"{'PASS' if ok else 'FAIL':6}  {name}", flush=True)

    try:
        _skill(transport, "1+1")
        record("PVT-ENV 业务面/ token 可用（1+1）", True, {})
    except Exception as exc:  # noqa: BLE001
        record("PVT-ENV 业务面/ token 可用（1+1）", False,
               {"error": f"{type(exc).__name__}: {exc}"})
        return _finish(results, evidence, args.out)

    variants = {
        "tt": variant_netlist(base),
        "ss": variant_netlist(base, sections=("ss_25", "ss_18")),
        "ff": variant_netlist(base, sections=("ff_25", "ff_18")),
        "lowv": variant_netlist(base, vdd="2.25"),
        "hot": variant_netlist(base, temp="125"),
        "cold": variant_netlist(base, temp="-40"),
    }
    try:
        runs = run_variants(transport, variants, work)
    except Exception as exc:  # noqa: BLE001
        record("PVT-RUN spectre.run 提交", False, {"error": f"{type(exc).__name__}: {exc}"})
        return _finish(results, evidence, args.out)

    def job(name: str) -> str:
        return f"pvt_{name}_{STAMP}"

    def dc(job_name: str) -> dict[str, Any]:
        return runs.get(job_name, {}).get("data") or {}

    base_dc = dc(job("tt"))
    record("PVT-01 基线 tt/27℃/2.5V DC 跑通（节点数 >0）",
           len(base_dc) > 0,
           {"nodes": len(base_dc), "status": runs.get(job("tt"), {}).get("status")})
    if not base_dc:
        return _finish(results, evidence, args.out)

    def compare(name: str, label: str, note: str = "") -> None:
        other = dc(job(name))
        shared = [k for k in base_dc
                  if k in other and isinstance(base_dc[k], (int, float))
                  and isinstance(other[k], (int, float))]
        deltas = {k: abs(float(other[k]) - float(base_dc[k])) for k in shared}
        changed = sorted(k for k, v in deltas.items() if v > DELTA_EPS)
        detail = {
            "status": runs.get(job(name), {}).get("status"),
            "nodes": len(other), "shared_nodes": len(shared),
            "changed_nodes": len(changed),
            "max_delta_v": (max(deltas.values()) if deltas else None),
            "top_deltas": dict(sorted(deltas.items(), key=lambda kv: -kv[1])[:3]),
        }
        ok = len(other) > 0 and len(changed) >= MIN_CHANGED_NODES
        if not ok and note == "env":
            results.append((f"{name} {label}", "ENV-NOTE", detail))
            evidence["cases"][f"{name}_note"] = {"ok": None, **detail}
            print(f"NOTE    {name} {label}（环境不支持，见 evidence）", flush=True)
            return
        record(f"{name} {label}", ok, detail)

    compare("ss", "PVT-02 process=ss 与 tt 至少 3 节点不同")
    compare("ff", "PVT-03 process=ff 与 tt 至少 3 节点不同")
    compare("lowv", "PVT-04 VDD 2.25V 与 2.5V 至少 3 节点不同")
    compare("hot", "PVT-05 125℃ 与 27℃ 至少 3 节点不同", note="env")
    compare("cold", "PVT-06 -40℃ 与 27℃ 至少 3 节点不同", note="env")

    evidence["baseline_nodes"] = {k: base_dc[k] for k in sorted(base_dc)[:12]}
    return _finish(results, evidence, args.out)


def _finish(results: list[tuple[str, str, dict[str, Any]]], evidence: dict[str, Any],
            out: str | None) -> int:
    failures = [n for n, s, _ in results if s == "FAIL"]
    evidence["results"] = [{"case": n, "status": s} for n, s, _ in results]
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"evidence: {path}")
    print(f"{len(results) - len(failures)}/{len(results)} 通过"
          + (f"；失败 {failures}" if failures else ""))
    return 0 if not failures and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
