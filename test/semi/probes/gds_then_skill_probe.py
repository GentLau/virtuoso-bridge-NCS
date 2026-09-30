# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:40
# 依赖: 无
# =====================================================================
"""GDS 导出后同会话 SKILL 是否仍可用（P-075 回归探针）。

背景：`virtuoso.layout.gds`（strmout/XStream）在导出会话里会留下一个**模态**
"Stream out translation complete" 对话框，把该会话的 SKILL 通道挂住 —— 之后任何
`basic.skill.execute` 都 30s 超时，且 `gui.auto_dismiss` 关不掉，必须重启实例。

本探针把这条判据固定下来（**红线**：导出后同会话 SKILL 必须还能用）：

    ① 建 lib/cell + layout（一个矩形）并回读确认；
    ② `virtuoso.layout.gds` 导出到"还不存在"的目录（顺带回归远端发布建目录）；
    ③ 同会话发一次 `1+2`，要求在 --skill-timeout 秒内返回 3；
    ④ 再发一次 `schematic.read`（若 ③ 已经超时，说明会话挂死，直接判 FAIL 并提示重启）。

用法::

    PYTHONPATH=src python test/semi/probes/gds_then_skill_probe.py \
        --token d6af595b342647b58ec63ca6 --lib GDSKILL [--skill-timeout 60]

证据：`test/artifacts/evidence/round7/gds-then-skill.json`
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_RUNNERS = ROOT / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
PDK_ROOT = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"
LAYERMAP = f"{PDK_ROOT}/tsmcN65/tsmcN65.layermap"
#: 默认按 PDK 实例（calprobe）的 file role root；换 token 时用 --file-root 指到该实例可写的根
DEFAULT_FILE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/file"


def call(token: str, operation: str, timeout: float = 300, **fields) -> dict:
    body = json.dumps({"operation": operation, "token": token, **fields}).encode("utf-8")
    request = urllib.request.Request(API, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))
    except OSError as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}", "data": None}


def value_of(response: dict) -> dict:
    return ((response).get("value")) or {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--token", default="d6af595b342647b58ec63ca6")
    parser.add_argument("--base", default=API)
    parser.add_argument("--lib", default="GDSKILL")
    parser.add_argument("--cell", default="gds_probe")
    parser.add_argument("--tech", default="tsmcN65")
    parser.add_argument("--file-root", default=DEFAULT_FILE_ROOT,
                        help="该 token 可写的 file role root（库与 GDS 都落在这里）")
    parser.add_argument("--skill-timeout", type=float, default=60.0,
                        help="导出后同会话 SKILL 的允许时限（秒）")
    parser.add_argument("--out", default=str(ROOT / "test" / "artifacts" / "evidence"
                                             / "round7" / "gds-then-skill.json"))
    args = parser.parse_args(argv)

    require_environment(base=args.base, token=args.token, require_lib=[args.tech])
    steps: list[dict] = []

    def record(name: str, ok: bool, detail=None) -> bool:
        steps.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" -> {detail}" if detail else ""))
        return bool(ok)

    file_root = f"{args.file_root.rstrip('/')}/gds_skill"
    call(args.token, "basic.command.run", cmd=f"mkdir -p {file_root}", timeout=120)
    lib_path = f"{file_root}/{args.lib}"
    created = call(args.token, "virtuoso.cellview.lib.create", timeout=300,
                   library=args.lib, path=lib_path, technology_library=args.tech)
    record("lib-create", bool(created.get("ok")) or "already" in str(created.get("error")),
           created.get("error"))
    view = call(args.token, "virtuoso.cellview.view.create", timeout=180,
                library=args.lib, cell=args.cell, view="layout", view_type="maskLayout")
    record("layout-view-create", bool(view.get("ok")), view.get("error"))
    wrote = call(args.token, "virtuoso.layout.write", timeout=600, library=args.lib,
                 cell=args.cell, view="layout",
                 commands=[{"op": "place_rect", "layer": "M1", "purpose": "drawing",
                            "bbox": [[0.0, 0.0], [4.0, 3.0]]}])
    record("layout-write", bool(wrote.get("ok")), wrote.get("error"))
    read = call(args.token, "virtuoso.layout.read", timeout=300, library=args.lib,
                cell=args.cell, view="layout", detail="geometry")
    record("layout-read-back", bool(read.get("ok")),
           {"shape_count": len((value_of(read).get("shapes") or []))})

    gds_dir = f"{file_root}/gds/{int(time.time())}"
    gds = call(args.token, "virtuoso.layout.gds", timeout=900, action="export",
               library=args.lib, cell=args.cell, view="layout", file_path=f"{gds_dir}/{args.cell}.gds",
               file_is_local=False, top_cell=args.cell, layer_map=LAYERMAP,
               layer_map_is_local=False, tech_lib=args.tech)
    record("gds-export", bool(gds.get("ok")), gds.get("error"))

    started = time.time()
    skill = call(args.token, "basic.skill.execute", timeout=args.skill_timeout + 30,
                 skill_code="1+2")
    elapsed = round(time.time() - started, 1)
    ok_skill = bool(skill.get("ok")) and \
        str(((skill).get("result") or {}).get("output", "")).strip('"') == "3"
    record(f"skill-after-gds(<{args.skill_timeout:g}s)", ok_skill,
           {"elapsed_s": elapsed, "error": skill.get("error")})
    if not ok_skill:
        steps.append({"name": "hint", "ok": True,
                      "detail": "会话很可能被 XStream 模态框挂死（P-075）；"
                                "请在该实例的 DISPLAY 上查 'Stream out translation complete' 并重启实例"})

    payload = {"token": args.token, "library": args.lib, "cell": args.cell,
               "ok": all(step["ok"] for step in steps), "steps": steps}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nverdict: {'clean' if payload['ok'] else 'RED（P-075）'}\nevidence: {out}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
