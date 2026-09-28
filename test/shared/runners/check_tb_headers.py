# -*- coding: utf-8 -*-
"""TB 注释头核账：扫描 TB/探针文件顶部的规范注释头，校验必填字段并给出补全草案。

规范见 `test/docs/写TB规范.md` §0。用法::

    python test/shared/runners/check_tb_headers.py                 # 报表 + JSON 证据
    python test/shared/runners/check_tb_headers.py --fail          # 有缺失时 rc=1（将来可入门禁）
    python test/shared/runners/check_tb_headers.py --emit draft.md # 生成"每个文件一份补全草案"
    python test/shared/runners/check_tb_headers.py --only test/live/flows/design_iterate_tb.py

草案只做**启发式推断**（层从目录、被测对象从代码里的 operation 字面量、token 从文件里出现过的值、
依赖从文件里引用的其它 `test/**.py`），作者必须自己核对——尤其是"作者"和"判据"两栏。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
#: 这些目录**整个都是 TB/探针**（含 `cov_*_real.py`、`s11_postsim_compare.py` 这类不按
#: `*_tb.py` 命名的流程脚本），所以按目录收全，而不是按文件名模式收——按模式收会漏（实测漏过 3 份）。
#: 纯 pytest 用例目录（`offline/{unit,integration,scenario}`）不在范围内：那些是用例文件，不是 TB。
SCAN_DIRS = ("test/semi/probes", "test/semi/transport", "test/semi/registration",
             "test/live/e2e", "test/live/flows", "test/live/packages",
             "test/live/registration", "test/live/stress", "test/live/transport",
             "test/offline/core")
SKIP_FILES = {"__init__.py", "conftest.py"}
#: 固定 3 栏、固定顺序（改这个元组 = 改规范，必须同时改 test/docs/写TB规范.md §0）
FIELDS = ("作者", "最后改动", "依赖")
REQUIRED = FIELDS
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}$")
OPEN_RE = re.compile(r"^#\s*=+\s*TB 注释头")
CLOSE_RE = re.compile(r"^#\s*=+\s*$")
HEADER_LINE = re.compile(r"^#\s*(?P<key>[^\s:：]+)\s*[:：]\s*(?P<value>.+?)\s*$")
OP_RE = re.compile(r'"(?P<op>(?:virtuoso|basic|calibre|spectre|maestro)\.[a-z0-9_.]+)"')
ATOM_RE = re.compile(r'"op"\s*:\s*"(?P<atom>[a-z_0-9]+)"')
TOKEN_RE = re.compile(r"\b(?:vb-[a-z0-9]+|[0-9a-f]{32})\b")
PATH_RE = re.compile(r"test/[A-Za-z0-9_./\-]+\.py")
EVIDENCE_RE = re.compile(r"test/artifacts/evidence/[A-Za-z0-9_./\-]*")


def layer_of(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith("test/semi/"):
        return "半真机"
    if rel.startswith("test/live/"):
        return "真机"
    return "离线"


def candidate_files() -> list[Path]:
    found: set[Path] = set()
    for base in SCAN_DIRS:
        for path in (ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts or path.name in SKIP_FILES:
                continue
            if path.is_file():
                found.add(path)
    return sorted(found)


def parse_header(path: Path) -> tuple[dict[str, str], list[str]]:
    """返回 (字段, 结构问题)。结构问题 = 顺序错 / 块内多出无法识别或不连续的行。"""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    fields: dict[str, str] = {}
    order: list[str] = []
    problems: list[str] = []
    inside = False
    opened = False
    for line in lines[:60]:
        if not inside:
            if OPEN_RE.match(line):
                inside, opened = True, True
            continue
        if CLOSE_RE.match(line):
            inside = False
            break
        match = HEADER_LINE.match(line.rstrip())
        if not match or match.group("key") not in FIELDS:
            problems.append(f"块内出现无法识别的行: {line.strip()[:60]}")
            continue
        key, value = match.group("key"), match.group("value")
        if key in fields:
            problems.append(f"字段重复: {key}")
        fields[key] = value
        order.append(key)
    if not opened:
        return {}, ["没有 TB 注释头（规范：test/docs/写TB规范.md §0）"]
    expected = [f for f in FIELDS if f in fields]
    if order != expected:
        problems.append("字段顺序不符合规范：" + " → ".join(order)
                        + f"（应为 {' → '.join(FIELDS)}）")
    return fields, problems


def validate(fields: dict[str, str]) -> tuple[list[str], list[str]]:
    """返回 (缺失字段, 格式/取值问题)。"""
    missing = [key for key in FIELDS if not fields.get(key)]
    problems: list[str] = []
    value = fields.get("最后改动", "")
    if value and not DATETIME_RE.match(value):
        problems.append("最后改动 必须是 YYYY-MM-DD HH:MM（精确到分钟，后面不要跟说明文字）")
    if fields.get("作者") and not re.match(r"^(测试|设计)/\S+", fields["作者"]):
        problems.append("作者 必须是 测试/<名字> 或 设计/<名字>")
    author = fields.get("作者", "")
    if author and re.search(r"[<>]|待填|待认领|待补|名字|TBD|unknown|xxx", author, re.I):
        problems.append(f"作者是占位符（未认领）：{author}")
    return missing, problems


def draft(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    # 只推"依赖"（3 栏里唯一需要从文件里读的）：引用到的其它 test/**.py
    deps = sorted({p for p in PATH_RE.findall(text) if p != rel})[:3]
    return {
        "作者": "<填：测试/<名字> 或 设计/<名字>>",
        "最后改动": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "依赖": ", ".join(deps) if deps else "无",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fail", action="store_true", help="有缺失字段时 rc=1")
    parser.add_argument("--json", default="test/artifacts/evidence/tb-headers.json")
    parser.add_argument("--emit", default="", help="把补全草案写到该 markdown 路径")
    parser.add_argument("--only", default="", help="只检查一个文件")
    args = parser.parse_args(argv)

    files = ([ROOT / args.only] if args.only else candidate_files())
    rows = []
    for path in files:
        if not path.is_file():
            continue
        header, structure = parse_header(path)
        missing, format_problems = validate(header)
        problems = structure + format_problems
        rows.append({"file": path.relative_to(ROOT).as_posix(),
                     "layer": layer_of(path),
                     "has_header": bool(header),
                     "missing": missing,
                     "problems": problems,
                     "header": header,
                     "draft": draft(path)})

    complete = [r for r in rows if not r["missing"] and not r["problems"] and r["has_header"]]
    none_header = [r for r in rows if not r["has_header"]]
    partial = [r for r in rows if r["has_header"] and (r["missing"] or r["problems"])]
    print(f"TB 候选文件 {len(rows)}：合格 {len(complete)}；"
          f"不合格（缺字段/顺序错/格式错）{len(partial)}；完全没有注释头 {len(none_header)}")
    for row in partial + none_header:
        parts = []
        if row["missing"]:
            parts.append(f"缺 {', '.join(row['missing'])}")
        parts.extend(row["problems"])
        detail = "; ".join(parts) or "（无）"
        print(f"  - [{row['layer']}] {row['file']}  {detail}")

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"total": len(rows), "complete": len(complete),
                               "partial": len(partial), "no_header": len(none_header),
                               "fields": list(FIELDS),
                               "rows": rows}, ensure_ascii=False, indent=1,
                              default=str), encoding="utf-8")
    print(f"证据: {out}")

    if args.emit:
        lines = ["# TB 注释头补全草案（机器生成，作者必须核对）", "",
                 f"> 生成：check_tb_headers.py ｜ 候选 {len(rows)} 份 ｜ 规范：`test/docs/写TB规范.md` §0", ""]
        for row in sorted(rows, key=lambda r: (r["missing"] == [], r["file"])):
            if not row["missing"]:
                continue
            lines += [f"## {row['file']}", "", "```python",
                      "# === TB 注释头（规范见 test/docs/写TB规范.md §0）====================="]
            for key in FIELDS:
                value = row["header"].get(key) or row["draft"].get(key, "")
                lines.append(f"# {key}: {value}")
            lines += ["# =====================================================================",
                      "```", ""]
        Path(args.emit).write_text("\n".join(lines), encoding="utf-8")
        print(f"草案: {args.emit}")

    return 1 if (args.fail and (partial or none_header)) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
