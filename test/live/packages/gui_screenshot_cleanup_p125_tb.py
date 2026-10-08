# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:06
# 依赖: 无
# =======================================================================
"""P-125 红钉（真机）：`gui.screenshot` 下载后必须清理远端暂存（P-091 口径）。

schematic/symbol/layout 三包已在 `finally` 里 `rm -f` 远端暂存（“远端暂存、
下载后清理”口径），gui 包第 4 份实现只下载不清理 → 远端 `.ppm` 无界残留。

攻击方式：连拍 **3 张**，量化泄漏（每拍一张应新增残留 0 个；现状应新增 3 个，
证明无界增长而不是偶发）。判据：动作前后远端 `shot-*.ppm` 集合必须不变。
红钉标记 `[P-125-RED-PIN]`；修复后打印 `[P-125-GREEN]` 并 rc=0，
由 `run_redpins.py` 报 UNEXPECTED-GREEN 提醒销钉。

第 1 步（环境检查）：8127 业务面 + token `vb-vblog`（常驻环境）先 `1+2`。
用法：PYTHONPATH=src python test/live/packages/gui_screenshot_cleanup_p125_tb.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
EVIDENCE = ROOT / "test" / "artifacts" / "evidence" / "redpins" / "p125-gui-shot-cleanup.json"
LOCAL_PNG = ROOT / "test" / "artifacts" / "tmp" / "p125-gui-shot.png"
FIND_SHOTS = (
    "find $HOME/.virtuoso-bridge -maxdepth 6 -name 'shot-*.ppm' "
    "-printf '%p\\n' 2>/dev/null | sort"
)


def _call(payload: dict, timeout: int = 300) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def _op(operation: str, **fields) -> dict:
    return _call({"operation": operation, "token": TOKEN, **fields})


def _stdout_of(response: dict) -> str:
    result = response.get("result")
    if isinstance(result, dict):
        return str(result.get("stdout") or "")
    return str(response.get("stdout") or "")


def _remote_shots() -> list[str]:
    response = _op("basic.command.run", cmd=FIND_SHOTS, timeout=60)
    if not response.get("ok"):
        raise SystemExit(f"[P-125-BROKEN] 远端列举失败: {response}")
    return [line.strip() for line in _stdout_of(response).splitlines() if line.strip()]


def main() -> int:
    # ① 环境检查：业务面 + 该 token 的 daemon 可用
    probe = _op("basic.skill.execute", skill_code="1+2", timeout=60)
    if not probe.get("ok"):
        print(f"[P-125-BROKEN] 业务面/daemon 不可用: {probe}")
        return 1

    # ②③ 基线：记录动作前的远端 shot 集合
    before = _remote_shots()

    # ④ 被测动作：gui.screenshot（默认 target=ciw）
    shots: list[dict] = []
    for index in range(3):
        local_png = LOCAL_PNG.with_name(f"{LOCAL_PNG.stem}-{index}.png")
        local_png.parent.mkdir(parents=True, exist_ok=True)
        if local_png.exists():
            local_png.unlink()
        shot = _op(
            "virtuoso.gui.screenshot",
            output_path=str(local_png), target="ciw", timeout=180,
        )
        if not shot.get("ok"):
            print(f"[P-125-BROKEN] gui.screenshot 第 {index + 1} 张调用失败: {shot}")
            return 1
        shots.append({
            "local_png": str(local_png),
            "local_png_exists": local_png.is_file(),
            "local_png_bytes": local_png.stat().st_size if local_png.is_file() else 0,
        })

    # ⑤ 读回比对：远端暂存必须被清掉
    after = _remote_shots()
    residual = sorted(set(after) - set(before))
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps(
            {
                "tb": "gui_screenshot_cleanup_p125_tb",
                "token": TOKEN,
                "shots": shots,
                "before": before,
                "after": after,
                "residual": residual,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    if residual:
        print(
            f"[P-125-RED-PIN] 连拍 3 张后远端新增残留 {len(residual)} 个"
            f"（每张都泄漏，无界增长）: {residual}"
        )
        print(f"[P-125-RED-PIN] 证据: {EVIDENCE.relative_to(ROOT).as_posix()}")
        return 1
    print(f"[P-125-GREEN] 远端无新增残留（证据: {EVIDENCE.relative_to(ROOT).as_posix()}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
