"""Probe: gui 包在真实 display 上的行为（半真机表征，非准出证据）。

覆盖测试要点里“不建议追”的 X11/GUI 现场路径中**归属上层 gui 包**的部分：
窗口管理器重父化下 EWMH 顶层窗口识别、整屏截图、CIW 定位。其余
（py2.7 daemon、平台矩阵）不属上层包，不在本探针范围。

运行（需远端 Virtuoso/display 就绪）：

    python test/semi/probes/gui_display_probe.py \
        --work-dir test/artifacts/env/log-vblog --token vb-vblog

退出码：0=全部 PASS；1=有 FAIL；2=环境不满足（记为 PENDING）。
证据写 ``test/artifacts/evidence/<run-id>/gui-display-probe.json``。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import init_work_dir  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402
from pyapi.packages import gui  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    init_work_dir(args.work_dir)
    middle = BusinessServer()
    pkg = gui.Package(middle)
    results: dict[str, str] = {}
    try:
        facts = middle.query(token=args.token)
        display = (facts.roles.get("gui").display if facts.roles.get("gui")
                   else None)
        listed = pkg.list_windows(gui.ListWindowsRequest(
            token=args.token, timeout=60))
        if listed.ok:
            ciw = [w for w in listed.windows if w["kind"] == "ciw"]
            results["display"] = display or "unset"
            results["list_windows"] = (
                "PASS" if listed.windows else "PENDING(empty desktop)")
            results["top_level_count"] = str(len(listed.windows))
            results["ciw_detected"] = "PASS" if ciw else "PENDING(no CIW)"

            with tempfile.TemporaryDirectory(prefix="vb-gui-probe-") as tmp:
                shot = pkg.screenshot(gui.ScreenshotRequest(
                    token=args.token, target="display",
                    output_path=str(Path(tmp) / "display.ppm"),
                    timeout=120,
                ))
                results["screenshot_display"] = (
                    "PASS" if shot.ok and Path(shot.local_path or "").is_file()
                    else f"FAIL: {shot.error}")
    except Exception as exc:  # noqa: BLE001
        results["error"] = f"{type(exc).__name__}: {exc}"

    verdict_keys = ("list_windows", "ciw_detected", "screenshot_display")
    verdicts = [str(results.get(key, "")) for key in verdict_keys]
    failed = [key for key in verdict_keys
              if str(results.get(key, "")).startswith("FAIL")]
    if failed:
        status = "FAIL"
    elif any(value.startswith("PENDING") for value in verdicts):
        status = "PENDING"
    elif all(value.startswith("PASS") for value in verdicts):
        status = "PASS"
    else:
        status = "FAIL"

    payload = {
        "run_id": f"gui-display-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        "command": " ".join(sys.argv),
        "machine": "DESKTOP-F143LSD -> wsl-gent",
        "status": status,
        "results": results,
    }
    out = Path(args.out) if args.out else (
        ROOT / "test" / "artifacts" / "evidence"
        / payload["run_id"] / "gui-display-probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if status == "FAIL" else (2 if status == "PENDING" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
