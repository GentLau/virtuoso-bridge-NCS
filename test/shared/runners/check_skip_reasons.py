# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 03:20
# 依赖: 无
# =======================================================================
"""skip 原因检查器（2026-09-29 起定为硬规矩：**任何 skip 必须写明原因**）。

两类检查：

A. **静态**：AST 扫 `test/**/*.py` 里的 `skip` / `skipif` / `skipUnless` / `expectedFailure` 装饰器，
   要求带非空 reason（字符串字面量，或 `reason=` 关键字；`unittest.skipIf` 的第二个参数即 reason）。
   命中"无 reason""reason 为空串"即算违规。

B. **动态**：解析给定的 JUnit XML（默认取最近的 `offline-win-final*.xml` 与 `offline-linux-py39-final*.xml`），
   按 `skipped@message` 分组统计；只要出现空 message / `no message` 即算违规。

输出 JSON 证据（默认 `test/artifacts/evidence/skip-reasons.json`）+ 控制台摘要；有违规 rc=1。
用法：
  python test/shared/runners/check_skip_reasons.py
  python test/shared/runners/check_skip_reasons.py --xml test/artifacts/evidence/round8/offline-win-final3.xml
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP_DECORATORS = {"skip", "skipif", "skipUnless", "expectedFailure"}


def _const_text(node: ast.AST, consts: dict[str, str]) -> str | None:
    """字符串字面量，或指向模块级字符串常量的 Name（如 `_ADMIN_REASON`）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    if isinstance(node, ast.Name):
        return consts.get(node.id, "").strip() or None
    return None


def _reason_of(call: ast.Call, consts: dict[str, str]) -> str | None:
    """从 `pytest.mark.skip(...)` / `unittest.skipIf(...)` 调用里取 reason 文本。

    `unittest.skipUnless(condition, reason)` 的 reason 是**第二个**位置参数；
    `pytest.mark.skip(reason=...)` 用关键字。两种都要支持，并允许 reason 指向模块级常量。
    """
    for kw in call.keywords:
        if kw.arg == "reason":
            return _const_text(kw.value, consts)
    if call.args:
        last = call.args[-1]
        text = _const_text(last, consts)
        if text:
            return text
        if len(call.args) >= 2:
            return _const_text(call.args[1], consts)
    return None


def scan_static() -> list[dict]:
    violations: list[dict] = []
    for path in sorted((ROOT / "test").rglob("*.py")):
        if "artifacts" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        consts: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        consts[target.id] = node.value.value
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name not in SKIP_DECORATORS:
                continue
            parent = getattr(node, "parent", None)
            reason = _reason_of(node, consts)
            if not reason:
                violations.append({
                    "file": path.relative_to(ROOT).as_posix(),
                    "line": getattr(node, "lineno", None),
                    "decorator": name,
                    "problem": "missing or empty reason",
                })
    return violations


def scan_xml(paths: list[str]) -> dict:
    grouped: dict[str, list[str]] = defaultdict(list)
    empty: list[dict] = []
    totals = {"files": 0, "tests": 0, "skips": 0}
    for p in paths:
        try:
            root = ET.parse(p).getroot()
        except (OSError, ET.ParseError):
            continue
        totals["files"] += 1
        for case in root.iter("testcase"):
            totals["tests"] += 1
            skipped = case.find("skipped")
            if skipped is None:
                continue
            totals["skips"] += 1
            msg = (skipped.get("message") or "").strip()
            if not msg or msg.lower() in ("no message", "unconditional skip"):
                empty.append({"file": p, "case": f'{case.get("classname")}::{case.get("name")}'})
                msg = "<EMPTY>"
            grouped[msg].append(f'{Path(p).name}::{case.get("name")}')
    return {"totals": totals, "by_reason": {k: len(v) for k, v in grouped.items()}, "empty": empty}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", nargs="*", default=None)
    parser.add_argument("--out", default=str(ROOT / "test" / "artifacts" / "evidence" / "skip-reasons.json"))
    args = parser.parse_args()

    if args.xml:
        xml_paths = args.xml
    else:
        xml_paths = (sorted(glob.glob(str(ROOT / "test/artifacts/evidence/round8/offline-win-final*.xml")))
                     + sorted(glob.glob(str(ROOT / "test/artifacts/evidence/round8/offline-linux-py39-final*.xml"))))
    static = scan_static()
    dynamic = scan_xml(xml_paths)
    payload = {
        "static_violations": static,
        "dynamic": dynamic,
        "xml_files": xml_paths,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"静态：扫 test/ 下 skip 装饰器 → 违规 {len(static)} 条")
    for v in static[:10]:
        print("   ", v["file"], v["line"], v["decorator"], v["problem"])
    t = dynamic["totals"]
    print(f"动态：{t['files']} 份 XML / {t['tests']} 用例 / {t['skips']} 条 skip / 无原因 {len(dynamic['empty'])} 条")
    for reason, count in sorted(dynamic["by_reason"].items(), key=lambda kv: -kv[1])[:8]:
        print(f"   [{count}] {reason[:96]}")
    print(f"evidence: {args.out}")
    return 1 if (static or dynamic["empty"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
