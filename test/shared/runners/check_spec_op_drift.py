"""spec 声明的操作 vs 实现 OPERATIONS 的漂移核对（第八轮）。

两个方向都要报：
  * SPEC-ONLY：spec 里写了、实现里没有 → 要么是文档滞后（需改 spec），要么是实现缺功能（**缺陷**）；
  * IMPL-ONLY：实现里有、spec 没写 → 未文档化操作（上层看不到的能力，需补 spec）。

用法::

    python test/shared/runners/check_spec_op_drift.py            # 打印 + 写 md/json
    python test/shared/runners/check_spec_op_drift.py --fail     # 有 SPEC-ONLY 时退出码非 0
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "spec" / "design-concepts"
PKG = ROOT / "src" / "pyapi" / "packages"
OUT = ROOT / "test" / "reports" / "round8"

OP_FAMILY = ("virtuoso", "spectre", "calibre", "basic", "maestro")
#: 全名（`virtuoso.schematic.read`）直接算操作标识
OP_TOKEN_RE = re.compile(r"`((?:virtuoso|spectre|calibre|basic|maestro)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*)`")
#: 文档内短名（如 `schematic.read` / `lib.list`）只在**操作表行**语境里才算
SHORT_TOKEN_RE = re.compile(r"`([a-z][a-z0-9_]*\.[a-z0-9_]+(?:\.[a-z0-9_]+)?)`")
OP_CONTEXT_RE = re.compile(r"操作|接口|读|写|删除|创建|改名|复制|查询|运行|生成|导出|导入|保存|列出|绑定|实例化|打开|关闭")
#: 形如 `spectre.out` / `maestro.sdb` 的其实是文件名/目录名，不是操作
FILEISH_RE = re.compile(r"\.(bin|out|fc|ic|root|sdb|log|scs|psf|cdl|gds|rep|txt|json|xml)$")
#: 文档里以短名出现的操作（如 cellview 文档里的 `lib.list` / `category.rename`）
SHORT_OP_RE = re.compile(r"^\s*\|\s*[a-z_]+\s*\|\s*`?([a-z_]+\.[a-z_]+)`?\s*\|")
OPS_RE = re.compile(r"OPERATIONS\s*=\s*\(([\s\S]*?)\n\)")
ENTRY_RE = re.compile(r'\(\s*"([\w.]+)"\s*,\s*"(\w+)"\s*,\s*(\w+)')


def impl_ops() -> dict[str, str]:
    ops: dict[str, str] = {}
    for path in sorted(PKG.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = OPS_RE.search(text)
        if not m:
            continue
        for op, method, _model in ENTRY_RE.findall(m.group(1)):
            ops[op] = f"{path.relative_to(ROOT).as_posix()}::{method}"
    return ops


def spec_ops() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(SPEC.rglob("*.md")):
        rel = path.relative_to(SPEC).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for token in OP_TOKEN_RE.findall(line):
                if FILEISH_RE.search(token):
                    continue
                found.setdefault(token, []).append(f"{rel}:{line_no}")
            if line.strip().startswith("|") and OP_CONTEXT_RE.search(line):
                for token in SHORT_TOKEN_RE.findall(line):
                    if FILEISH_RE.search(token):
                        continue
                    found.setdefault(token, []).append(f"{rel}:{line_no}")
            m = SHORT_OP_RE.match(line)
            if m:
                found.setdefault(m.group(1), []).append(f"{rel}:{line_no}")
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=str(OUT / "spec-op-drift.md"))
    ap.add_argument("--json", default=str(OUT / "spec-op-drift.json"))
    ap.add_argument("--fail", action="store_true")
    args = ap.parse_args()

    impl = impl_ops()
    spec = spec_ops()

    def matches_impl(op: str, impl_name: str) -> bool:
        """spec 写法与实现写法可能只差前缀（`cell.create` vs `virtuoso.cellview.cell.create`）。"""
        if op == impl_name:
            return True
        return impl_name.endswith("." + op) or op.endswith("." + impl_name)

    spec_only = {k: v for k, v in spec.items() if not any(matches_impl(k, i) for i in impl)}
    impl_only = {k: v for k, v in impl.items() if not any(matches_impl(s, k) for s in spec)}

    lines = [
        "# spec 操作 ↔ 实现 OPERATIONS 漂移核对",
        "",
        f"- 实现 OPERATIONS：{len(impl)} 个；spec 提到的操作标识：{len(spec)} 个",
        f"- **SPEC-ONLY（spec 有、实现无）**：{len(spec_only)}",
        f"- IMPL-ONLY（实现有、spec 未提）：{len(impl_only)}",
        "",
    ]
    if spec_only:
        lines += ["## SPEC-ONLY（需判定：文档滞后 or 实现缺功能）", ""]
        for op, refs in sorted(spec_only.items()):
            lines.append(f"- `{op}` — {', '.join(refs[:4])}")
        lines.append("")
    if impl_only:
        lines += ["## IMPL-ONLY（未文档化操作）", ""]
        for op, ref in sorted(impl_only.items()):
            lines.append(f"- `{op}` — {ref}")
        lines.append("")

    Path(args.md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(args.json).write_text(
        json.dumps({"spec_only": spec_only, "impl_only": impl_only,
                    "impl_total": len(impl), "spec_total": len(spec)},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"实现 op {len(impl)}；spec op 标识 {len(spec)}；SPEC-ONLY {len(spec_only)}；IMPL-ONLY {len(impl_only)}")
    print(f"  -> {args.md}")
    return 1 if (args.fail and spec_only) else 0


if __name__ == "__main__":
    raise SystemExit(main())
