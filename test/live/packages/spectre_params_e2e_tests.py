# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 19:55
# 依赖: 真机 vblog token（wsl-gent spectre role）+ 本文件自建 RC netlist
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：token/业务面可达 + spectre bin 存在（basic.command.run test -x）；
# ②③ 自建 netlist / 本地 JSON 数据并校验基线（文件存在、可读）；
# ④ 只做被测动作（每个 (op,param) 一个 case）；
# ⑤ 读回比对：run 断言 status+落盘目录；measure 断言数值；export 断言列序/精度/行数；
# ⑥ 不清理现场（证据目录保留导出件），现场状态写进证据 JSON。
"""``spectre.*`` **参数级**验收 TB（第八轮补缺，C0/B3 口径）。

补齐机器矩阵里"从未被任何 TB 使用过"的参数：

* `spectre.run`: `output_root`（下载落 `<output_root>/<job>`）、`spectre_bin`（显式二进制 + 负向不存在）；
* `spectre.measure`: `source_path`（调用方 JSON 文件，不是 role 路径）；
* `spectre.export`: `source_path` + `columns`（列序）+ `precision`（1..16，负向 0 必须结构化失败）。

判据不是"ok"：run 要看到落盘文件；measure 要数值对上；export 要读回文件内容核对列序与四舍五入。

用法::

    PYTHONPATH=src python test/live/packages/spectre_params_e2e_tests.py --transport http --token vb-vblog
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
PARAM_DIR = ROOT / "test" / "artifacts" / "env" / "round8-spectre-params"
OUT_DIR = ROOT / "test" / "artifacts" / "evidence" / "round8" / "spectre-params"
SPECTRE_BIN = "/opt/eda/cadence/SPECTRE241/bin/spectre"

RC_NETLIST = """simulator lang=spectre
global 0
V1 (IN 0) vsource type=pulse val0=0 val1=1 period=1u width=500n rise=1n fall=1n
R1 (IN OUT) resistor r=1k
C1 (OUT 0) capacitor c=1p
tran tran stop=5u
save OUT
saveOptions options save=selected
"""

MEASURE_DATA = {"time": [0.0, 1.0, 2.0, 3.0], "sig": [0.0, 1.0, 2.0, 3.0],
                "sig_round": [0.0, 1.23456, 2.34567, 3.45678]}


class HttpTransport:
    middle = None

    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.token = token

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base, data=body, headers={"Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


class DirectTransport:
    def __init__(self, token: str) -> None:
        from common.paths import init_work_dir
        from server import dispatch  # noqa: F401
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(WORK_DIR))
        register_packages()
        self.middle = BusinessServer()
        for op in dispatch.PACKAGES:
            dispatch.PACKAGES[op] = dispatch.PACKAGES[op]
        self.token = token

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        from server import dispatch

        operation = payload.pop("operation")
        return dispatch.dispatch(self.middle, operation, payload)


def op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    response = transport.call({"operation": operation, "token": transport.token, **fields})
    data = _c1_wrapper(response)
    if response.get("ok") is False or data.get("ok") is False:
        raise AssertionError(f"{operation} failed: {response.get('error') or data.get('error')}")
    return data


def expect_fail(transport, operation: str, **fields: Any) -> str:
    response = transport.call({"operation": operation, "token": transport.token, **fields})
    data = _c1_wrapper(response)
    if response.get("ok") is not False and data.get("ok") is not False:
        raise AssertionError(f"{operation} expected structured failure, got ok")
    return str(response.get("error") or data.get("error") or "")


def run_case(name: str, check: Callable[[], Any], results: list[dict]) -> None:
    started = dt.datetime.now().isoformat(timespec="seconds")
    try:
        detail = check()
        results.append({"case": name, "started": started, "ok": True, "error": None,
                        "detail": detail})
        print(f"[PASS] {name}")
    except Exception as exc:  # noqa: BLE001 - 证据要保留失败原因
        results.append({"case": name, "started": started, "ok": False,
                        "error": f"{type(exc).__name__}: {exc}"})
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["http", "direct"], default="http")
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--spice-bin", default=SPECTRE_BIN)
    args = parser.parse_args()

    PARAM_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    netlist = PARAM_DIR / "tb_rc.scs"
    netlist.write_text(RC_NETLIST, encoding="utf-8")
    data_path = PARAM_DIR / "measure_data.json"
    data_path.write_text(json.dumps(MEASURE_DATA), encoding="utf-8")

    transport = (HttpTransport(API, args.token) if args.transport == "http"
                 else DirectTransport(args.token))
    results: list[dict] = []

    def case_output_root() -> None:
        out_root = PARAM_DIR / "spectre-root"
        job = f"param_outroot_{dt.datetime.now().strftime('%H%M%S')}"
        value = op(transport, "spectre.run", tasks=[{"job": job, "netlist": str(netlist)}],
                   output_root=str(out_root), parse="auto", timeout=900)["value"]
        runs = value.get("runs") or []
        assert runs and runs[0].get("ok") is True, f"run ok: {runs[0].get('ok')}"
        assert (runs[0].get("value") or {}).get("status") == "success", \
            f"run value.status: {(runs[0].get('value') or {}).get('status')}"
        local = out_root / job
        files = [p for p in local.rglob("*") if p.is_file()] if local.exists() else []
        assert local.exists() and files, f"output_root 下没有落盘: {local}"
        assert any(p.name.endswith(".raw") or p.name == "spectre.out" for p in files), \
            f"落盘文件不含结果: {[p.name for p in files][:8]}"
        return {"local_dir": str(local), "files": len(files)}

    def case_spectre_bin() -> None:
        check = transport.call({"operation": "basic.command.run", "token": transport.token,
                                "cmd": f"test -x {args.spice_bin} && echo OK"})
        assert "OK" in json.dumps(check), f"spectre bin 不存在: {args.spice_bin}"
        job = f"param_bin_{dt.datetime.now().strftime('%H%M%S')}"
        value = op(transport, "spectre.run",
                   tasks=[{"job": job, "netlist": str(netlist)}],
                   spectre_bin=args.spice_bin, parse="auto", timeout=900)["value"]
        runs = value.get("runs") or []
        assert runs and runs[0].get("ok") is True, f"explicit bin run: {runs[0].get('ok')}"
        assert (runs[0].get("value") or {}).get("status") == "success"
        error = expect_fail(transport, "spectre.run",
                            tasks=[{"job": f"param_badbin_{dt.datetime.now().strftime('%H%M%S')}",
                                    "netlist": str(netlist)}],
                            spectre_bin="/nonexistent/spectre-does-not-exist", timeout=120)
        assert error, "坏 spectre_bin 必须给结构化错误"
        return {"explicit_bin_ok": True, "bad_bin_error": error[:160]}

    def case_measure_source_path() -> None:
        value = op(transport, "spectre.measure", source_path=str(data_path),
                   metrics=[{"type": "min", "signal": "sig"},
                            {"type": "max", "signal": "sig"},
                            {"type": "threshold_crossing", "signal": "sig", "threshold": 1.5}],
                   timeout=60)["value"]
        by_type = {m["type"]: m for m in value.get("metrics") or []}
        assert abs(by_type["min"]["value"] - 0.0) < 1e-9, by_type["min"]
        assert abs(by_type["max"]["value"] - 3.0) < 1e-9, by_type["max"]
        cross = by_type["threshold_crossing"]["value"]
        assert 1.0 <= cross <= 2.0, f"threshold_crossing={cross}"
        assert value.get("source") == str(data_path), value.get("source")
        return {"min": by_type["min"]["value"], "max": by_type["max"]["value"],
                "cross": cross}

    def case_export_columns_precision() -> None:
        csv_path = OUT_DIR / "spectre_params_export.csv"
        csv_path.unlink(missing_ok=True)
        value = op(transport, "spectre.export", format="csv", source_path=str(data_path),
                   output_path=str(csv_path), columns=["time", "sig_round"], precision=3,
                   timeout=60)["value"]
        assert value.get("columns") == ["time", "sig_round"], value.get("columns")
        assert int(value.get("rows") or 0) == len(MEASURE_DATA["time"]), value.get("rows")
        text = csv_path.read_text(encoding="utf-8").strip().splitlines()
        assert text[0].split(",") == ["time", "sig_round"], text[0]
        # 口径（2026-09-28 实测 + 代码 `f"{v:.{precision}g}"`）：precision 是**有效数字**
        # 而不是小数位（spec 未定义 → P-078）。1.23456/2.34567/3.45678 在 precision=3
        # 下应写作 1.23 / 2.35 / 3.46。
        joined = ",".join(text[1:])
        assert "1.23" in joined and "2.35" in joined and "3.46" in joined, \
            f"precision=3（有效数字）未生效: {text[1:]}"

        json_path = OUT_DIR / "spectre_params_export.json"
        json_path.unlink(missing_ok=True)
        value_json = op(transport, "spectre.export", format="json", source_path=str(data_path),
                        output_path=str(json_path), timeout=60)["value"]
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload.get("format") == "json" and _c1_wrapper(payload), payload
        assert value_json.get("bytes", 0) > 0, value_json

        error = expect_fail(transport, "spectre.export", format="csv",
                            source_path=str(data_path),
                            output_path=str(OUT_DIR / "bad_precision.csv"), precision=0,
                            timeout=30)
        assert "precision" in error, f"precision=0 必须点名失败: {error}"
        return {"csv_rows": value.get("rows"), "json_bytes": value_json.get("bytes"),
                "bad_precision_error": error[:120]}

    def case_measure_bad_source() -> None:
        error = expect_fail(transport, "spectre.measure",
                            source_path=str(PARAM_DIR / "no_such_data.json"),
                            metrics=[{"type": "min", "signal": "sig"}], timeout=30)
        assert error, "不存在的 source_path 必须结构化失败"
        return {"error": error[:160]}

    run_case("RUN-P1 output_root 落盘", case_output_root, results)
    run_case("RUN-P2 spectre_bin 显式/负向", case_spectre_bin, results)
    run_case("MEASURE-P1 source_path", case_measure_source_path, results)
    run_case("EXPORT-P1 columns+precision+source_path", case_export_columns_precision, results)
    run_case("MEASURE-P2 坏 source_path", case_measure_bad_source, results)

    evidence = {
        "tb": "spectre_params_e2e_tests",
        "transport": args.transport,
        "token": args.token,
        "environment": {"host": "wsl-gent", "user": "Gent", "spectre_bin": args.spice_bin,
                        "netlist": str(netlist), "data": str(data_path)},
        "cases": results,
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "ok": all(r["ok"] for r in results),
    }
    out = OUT_DIR / "spectre-params.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n{evidence['passed']}/{evidence['total']} 通过；证据：{out}")
    return 0 if evidence["ok"] else 1


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
