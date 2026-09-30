# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（真机靶机指纹/业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时，正文有一行注释说明。
"""layout.gds 远端发布的路径边界攻击（第五轮，P-051 修复后）。

P-051 修的是"目标父目录不存在时自动建目录"。修完之后真正危险的是**命令拼接/路径边界**：

* C1 正常路径（对照）；
* C2 目标目录名**含空格**（`mkdir -p`/`cp` 若不带引号就会在这里炸）；
* C3 目标的父级是一个**普通文件**（应结构化失败，不能挂死/不能假装成功）；
* C4 相对路径（spec 要求相对路径按 file role root 解析或明确拒绝）。

每条记录：请求 ok / error / steps、远端 `stat` 结果。verdict 汇总各条是否"行为可预期"。
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
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "d6af595b342647b58ec63ca6"          # calprobe（PDK）
LIB, CELL = "SRX65", "ctle_core"
FILE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/file/serdes_rx"
LAYERMAP = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/tsmcN65/tsmcN65.layermap"
PDK_LIB = "tsmcN65"


def call(operation: str, **fields: Any) -> dict:
    body = json.dumps({"operation": operation, "token": TOKEN, **fields},
                      ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def remote(cmd: str) -> str:
    """取远端命令 stdout。

    C4 契约（2026-09-30 迁移）：`basic.command.run` 的结果是**具名对象**
    `{returncode, stdout, stderr, kind}`，不再是位置数组 —— 旧代码按 `[1]` 取 stdout，
    迁移后直接 `KeyError: 1`（本探针因此长期无人能跑）。
    """
    result = call("basic.command.run", cmd=cmd, timeout=120).get("result")
    if isinstance(result, dict):
        return str(result.get("stdout") or "")
    if isinstance(result, (list, tuple)) and len(result) > 1:
        return str(result[1])
    return ""


def export(path: str) -> dict:
    return call("virtuoso.layout.gds", action="export", library=LIB, cell=CELL,
                view="layout", file_path=path, file_is_local=False, top_cell=CELL,
                layer_map=LAYERMAP, layer_map_is_local=False, tech_lib=PDK_LIB,
                timeout=900)


def exists(path: str) -> str:
    return remote(f"stat -c %s {json.dumps(path)} 2>/dev/null || echo MISSING").strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "test" / "artifacts" / "evidence" / "round4-probes")
    args = ap.parse_args(argv)
    report: dict[str, Any] = {"token": TOKEN, "library": LIB, "cell": CELL}

    # 现场准备：一个干净的父目录 + 一个"父级是文件"的错位场景
    remote(f"rm -rf {FILE_ROOT}/path_edges && mkdir -p {FILE_ROOT}/path_edges && echo ok")
    remote(f"rm -f {FILE_ROOT}/path_edges/blocker && "
           f"printf 'x' > {FILE_ROOT}/path_edges/blocker && echo ok")

    cases = {
        "C1_normal": f"{FILE_ROOT}/path_edges/plain/{CELL}.gds",
        "C2_space": f"{FILE_ROOT}/path_edges/with space/{CELL}.gds",
        "C3_parent_is_file": f"{FILE_ROOT}/path_edges/blocker/{CELL}.gds",
        "C4_relative": f"relative_out/{CELL}.gds",
    }
    for name, path in cases.items():
        entry: dict[str, Any] = {"path": path}
        started = time.time()
        response = export(path)
        entry["seconds"] = round(time.time() - started, 2)
        entry["ok"] = response.get("ok")
        entry["error"] = response.get("error")
        value = ((response).get("value") or {})
        entry["steps"] = [s.get("name") for s in (value.get("steps") or [])] \
            if isinstance(value, dict) else None
        if not path.startswith("/"):
            root = FILE_ROOT
            entry["stat"] = exists(f"{root}/{path}")
        else:
            entry["stat"] = exists(path)
        report[name] = entry

    checks = {
        "C1_normal_ok": report["C1_normal"]["ok"] is True,
        "C2_space_ok": report["C2_space"]["ok"] is True,
        "C3_fails_cleanly": (report["C3_parent_is_file"]["ok"] is False
                             and bool(report["C3_parent_is_file"]["error"])),
        "C4_relative_handled": (report["C4_relative"]["ok"] is True
                                or bool(report["C4_relative"]["error"])),
    }
    report["checks"] = checks
    report["verdict"] = "clean" if all(checks.values()) else "path-edge-issue"

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "round4-gds-path-edges.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, entry in report.items():
        if name in cases:
            print(f"{name}: ok={entry['ok']} stat={entry['stat']} err={str(entry['error'])[:90]}")
    print(f"verdict: {report['verdict']}  checks={checks}")
    print(f"evidence: {path}")
    return 0 if report["verdict"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
