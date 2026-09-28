"""把"换个实现就变红"的负控制固化成可复跑脚本（独立复核 D3）。

背景：第五轮新增的两个契约 TB —

* `test/offline/unit/test_daemon_log_utf8_budget.py`（截断不得产出半个 UTF-8 字符）
* `test/offline/unit/test_middle_reserved_codes.py`（真实命令 rc=124/255 仍是 `kind=command`）

当时只把负控制的**输出文本**留在 `test/artifacts/evidence/round5-offline/*-negative-control.txt`，
仓库里没有可复跑入口，评审现场无法复算"断言有没有鉴别力"。本脚本补上：

做法（安全）：把 `src/` + `test/`（排除 `artifacts/`、`__pycache__`）复制到
`test/artifacts/tmp/negctl-<rand>/`，**只在副本里**改坏实现，然后在副本里跑对应 TB：

1. 基线（不改）必须**全绿**；
2. 变异后必须**变红**（红 = 断言有鉴别力）。

**绝不修改仓库里的 `src/`**。

用法::

    python test/shared/runners/negative_controls.py
    python test/shared/runners/negative_controls.py --out test/artifacts/evidence/round5-offline/negative-controls.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

CONTROLS = [
    {
        "name": "utf8-truncation-emits-replacement-char",
        "why": "把半字符丢弃改成 U+FFFD 兜底 → TB 必须红（spec 日志 §5/§8-7）",
        "file": "src/bridge/resources/ramic_bridge_daemon_3.py",
        "needle": 'body = err_text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")',
        "replace": 'body = err_text.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")',
        "test": "test/offline/unit/test_daemon_log_utf8_budget.py",
    },
    {
        "name": "reserved-codes-remapped-to-timeout-transport",
        "why": "把真实 rc=124/255 改判 timeout/transport → TB 必须红（spec 总览 §4.5）",
        "file": "src/transport/middle.py",
        "needle": "            return CommandResult(proc.returncode, proc.stdout, proc.stderr)",
        "replace": (
            "            if proc.returncode == 124:\n"
            "                return CommandResult(124, proc.stdout, proc.stderr, kind=\"timeout\")\n"
            "            if proc.returncode == 255:\n"
            "                return CommandResult(255, proc.stdout, proc.stderr, kind=\"transport\")\n"
            "            return CommandResult(proc.returncode, proc.stdout, proc.stderr)"
        ),
        "test": "test/offline/unit/test_middle_reserved_codes.py",
    },
]


def _copy_repo_subset(dest: Path) -> None:
    ignore = shutil.ignore_patterns("artifacts", "__pycache__", ".git", "*.pyc")
    shutil.copytree(ROOT / "src", dest / "src", ignore=ignore)
    shutil.copytree(ROOT / "test", dest / "test", ignore=ignore)
    for extra in ("pyproject.toml", "pytest.ini", "setup.cfg"):
        candidate = ROOT / extra
        if candidate.is_file():
            shutil.copy2(candidate, dest / extra)


def _run_test(sandbox: Path, test_path: str) -> tuple[int, str]:
    env = {"PYTHONPATH": "src", **{k: v for k, v in __import__("os").environ.items() if k not in ("COVERAGE_FILE",)}}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-q", "-p", "no:cacheprovider", "--no-header"],
        cwd=sandbox, env=env, capture_output=True, text=True, timeout=900,
    )
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-4:])
    return proc.returncode, tail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    sandbox = ROOT / "test" / "artifacts" / "tmp" / f"negctl-{uuid.uuid4().hex[:8]}"
    sandbox.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    try:
        _copy_repo_subset(sandbox)
        for control in CONTROLS:
            target = sandbox / control["file"]
            original = target.read_text(encoding="utf-8")
            if original.count(control["needle"]) != 1:
                results.append({"name": control["name"], "verdict": "ERROR",
                                "detail": "needle not unique", "hits": original.count(control["needle"])})
                continue
            rc_base, tail_base = _run_test(sandbox, control["test"])
            target.write_text(original.replace(control["needle"], control["replace"]), encoding="utf-8")
            rc_mut, tail_mut = _run_test(sandbox, control["test"])
            target.write_text(original, encoding="utf-8")
            verdict = "PASS" if (rc_base == 0 and rc_mut != 0) else "FAIL"
            results.append({
                "name": control["name"], "why": control["why"], "test": control["test"],
                "baseline_rc": rc_base, "baseline_tail": tail_base,
                "mutated_rc": rc_mut, "mutated_tail": tail_mut, "verdict": verdict,
            })
            print(f"[{verdict}] {control['name']}: baseline rc={rc_base}, mutated rc={rc_mut}")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    ok = bool(results) and all(item["verdict"] == "PASS" for item in results)
    payload = {"ok": ok, "controls": results}
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"evidence: {out}")
    print(f"verdict: {'PASS' if ok else 'FAIL'}（{sum(1 for i in results if i['verdict']=='PASS')}/{len(results)} 条负控制具备鉴别力）")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
