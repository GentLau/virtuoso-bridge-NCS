# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 11:35
# 依赖: 无（自造最小 RC 网表）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`basic.skill.execute("1+1")` 探活；
# ②③ 构建：本地写一个最小 RC + dcOp 网表（每个 mode 一份独立 job，job 名带时间戳避免目录非空）；
# ④ 只做被测动作：`spectre.run` 带不同 `mode`（一个 mode 一个 task）；
# ⑤ 读回比对（值级）：
#    * `<mode>` 对应的命令行开关必须出现在 `runs[].value.command` 里
#      （`+preset=<mode> +mt`，或 `+aps`；`spectre` 无附加开关）；
#    * `runs[].value.status == "success"` 且 `returncode == 0`；
#    * DC 数据非空（`runs[].value.data` 有节点），证明仿真真的跑了；
# ⑥ 收尾：只写本 TB 的 run 目录；证据 JSON 落盘。
"""`spectre.run` 的 `mode` 全取值真机覆盖（round9 参数缺口：5 个取值此前只有离线拼装断言）。

背景（`test/reports/round9/nested-key-coverage.md` §3）：`src/pyapi/packages/spectre.py::_MODES`
共 7 个取值 `spectre / aps / cx / ax / mx / lx / vx`，而全测试树里
**只有离线合同 `test/offline/unit/test_nested_command_keys_contract.py` 触碰过 `cx/ax/mx/lx/vx`**，
真机（S1/S2）从未跑过 —— 属于"参数在请求模型里、但没有实际执行证据"的缺口。

本 TB 用同一个最小网表把 7 个取值各跑一次，并断言**命令行开关**与**结果状态**（值级）；
另用负例钉住 `mode="x"` 已被删除（P-108）。

用法::

    PYTHONPATH=src python test/live/packages/spectre_modes_e2e_tests.py --transport http \
        --out test/artifacts/evidence/round9/spectre-modes-r9.json
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
STAMP = time.strftime("%m%d%H%M%S")
WORK = ROOT / "test" / "artifacts" / "env" / "spectre-modes"
NETLIST = WORK / f"mode_probe_{STAMP}.scs"

#: mode → 命令行里必须出现的开关（`spectre` 无附加开关）
MODE_ARGS: dict[str, tuple[str, ...]] = {
    "spectre": (),
    "aps": ("+aps",),
    "cx": ("+preset=cx", "+mt"),
    "ax": ("+preset=ax", "+mt"),
    "mx": ("+preset=mx", "+mt"),
    "lx": ("+preset=lx", "+mt"),
    "vx": ("+preset=vx", "+mt"),
}

NETLIST_TEXT = """simulator lang=spectre
global 0
V1 (in 0) vsource dc=1
R1 (in out) resistor r=1k
R2 (out 0) resistor r=1k
dcOp dc oppoint=logfile
"""


class HttpTransport:
    def __init__(self, api: str, token: str) -> None:
        self.api, self.token = api, token

    def call(self, payload: dict[str, Any], timeout: int = 900) -> dict[str, Any]:
        body = json.dumps({"token": self.token, **payload}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.api, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return {"ok": False,
                    "error": f"HTTP {error.code}: {error.read().decode('utf-8')[:300]}"}


def run_suite(transport: HttpTransport) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    results: list[tuple[str, str]] = []
    evidence: dict[str, Any] = {"stamp": STAMP, "netlist": str(NETLIST), "cases": {}}
    WORK.mkdir(parents=True, exist_ok=True)
    NETLIST.write_text(NETLIST_TEXT, encoding="utf-8", newline="\n")

    def run(name: str, func) -> None:
        try:
            func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return
        results.append((name, "PASS"))
        print(f"PASS    {name}", flush=True)

    def case_env() -> None:
        response = transport.call({"operation": "basic.skill.execute", "skill_code": "1+1"})
        assert response.get("ok") is True, f"业务面探活失败: {response.get('error')}"

    def make_case(mode: str):
        def case() -> None:
            job = f"mode_{mode}_{STAMP}"
            response = transport.call({
                "operation": "spectre.run",
                "tasks": [{"job": job, "netlist": str(NETLIST), "mode": mode}],
                "parse": "auto",
                "keep_run_dir": True,
            })
            runs = (response.get("value") or {}).get("runs") or []
            assert response.get("ok") is True, \
                f"mode={mode} 运行失败: {json.dumps(response, ensure_ascii=False)[:300]}"
            assert len(runs) == 1, f"mode={mode} runs 数量异常: {runs}"
            # 表 C 真缺口：顶层 `succeeded/failed` 之前没人断言（matri x: spectre.run.succeeded）
            summary = response.get("value") or {}
            assert summary.get("succeeded") == 1, \
                f"mode={mode} 顶层 succeeded 应为 1（实测 {summary.get('succeeded')!r}）"
            assert summary.get("failed") == 0, \
                f"mode={mode} 顶层 failed 应为 0（实测 {summary.get('failed')!r}）"
            inner = runs[0].get("value") or {}
            command = str(inner.get("command") or "")
            status = inner.get("status")
            returncode = inner.get("returncode")
            data = inner.get("data") or {}
            record = {"command": command, "status": status, "returncode": returncode,
                      "data_nodes": len(data), "errors": inner.get("errors"),
                      "warnings": inner.get("warnings")}
            evidence["cases"][mode] = record
            for flag in MODE_ARGS[mode]:
                assert flag in command, \
                    f"mode={mode} 命令行未带 `{flag}`（实测 {command!r}）"
            assert status == "success", f"mode={mode} status={status!r}（期望 success）：{record}"
            assert returncode == 0, f"mode={mode} returncode={returncode!r}（期望 0）"
            assert len(data) > 0, f"mode={mode} DC 数据为空（仿真没真跑）：{record}"
        return case

    run("MODE-ENV 业务面探活（1+1）", case_env)

    def case_x_removed() -> None:
        response = transport.call({
            "operation": "spectre.run",
            "tasks": [{"job": f"mode_x_removed_{STAMP}",
                       "netlist": str(NETLIST), "mode": "x"}],
            "parse": "auto",
            "keep_run_dir": True,
        })
        text = json.dumps(response, ensure_ascii=False)
        assert response.get("ok") is not True, \
            f"P-108：mode=x 已删除，必须在请求校验阶段拒绝：{text[:300]}"
        assert "must be one of" in text, \
            f"P-108：mode=x 的拒绝文案应列出合法 mode：{text[:300]}"
        evidence["cases"]["x_removed"] = {"response": response}

    run("MODE-x-removed mode=x 必须在请求校验拒绝（P-108）", case_x_removed)
    for mode in MODE_ARGS:
        label = f"MODE-{mode} mode={mode}（命令行开关 + status/rc + DC 数据）"
        if mode in ("cx", "ax", "mx", "lx", "vx"):
            label += " ← round9 缺口"
        run(label, make_case(mode))
    return results, evidence


def main(argv: list[str] | None = None) -> int:
    global API, TOKEN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    API, TOKEN = args.api, args.token
    results, evidence = run_suite(HttpTransport(args.api, args.token))
    failures = [name for name, status in results if status != "PASS"]
    evidence["results"] = [{"case": n, "status": s} for n, s in results]
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"evidence: {path}")
    print(f"{len(results) - len(failures)}/{len(results)} 通过"
          + (f"；失败 {failures}" if failures else ""))
    return 0 if not failures and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
