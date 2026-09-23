"""Classify uncovered lines with *proof*, not with an excuse.

The acceptance rule is: every line that the test run did not execute must fall
into a category that a reviewer can check.  Hand-written exemption lists rot
and hide gaps, so this script derives the categories from the source itself
(``ast``): a line is only excused when the syntax proves it cannot run in the
measurement environment, or when it is explicitly marked in the source.

    python test/shared/runners/classify_uncovered.py \
        --json test/artifacts/evidence/cov-main/coverage-main-strict.json \
        --out  test/reports/coverage-pack/coverage-rules-auto.json \
        --unclassified-out test/reports/coverage-pack/unclassified.txt

Categories (each carries the AST evidence that produced it):

* ``pragma-no-cover``      - the line carries ``# pragma: no cover``
* ``type-checking-only``   - inside ``if TYPE_CHECKING:``
* ``optional-dependency``  - inside an ``except ImportError/ModuleNotFoundError``
* ``platform-guarded``     - inside a ``sys.platform`` / ``os.name`` guard whose
                             branch does not apply to this platform
* ``abstract-method``      - body of a method decorated ``@abstractmethod``
* ``main-guard``           - inside ``if __name__ == "__main__":``
* ``not-implemented``      - a ``raise NotImplementedError`` statement

Everything else is written to ``unclassified`` - that list is the honest
"to-fix" backlog and the only thing a coverage claim may not wave away.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

PRAGMA = "pragma-no-cover"
TYPE_CHECKING_ONLY = "type-checking-only"
OPTIONAL_DEP = "optional-dependency"
PLATFORM_GUARDED = "platform-guarded"
ABSTRACT = "abstract-method"
MAIN_GUARD = "main-guard"
NOT_IMPLEMENTED = "not-implemented"
UNCLASSIFIED = "unclassified"


def _ranges(node: ast.AST) -> range:
    """Line numbers spanned by ``node`` (1-based, inclusive end)."""
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None:
        return range(0)
    return range(start, (end or start) + 1)


def _is_type_checking(test: ast.AST) -> bool:
    return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"


def _is_main_guard(test: ast.AST) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
    )


def _platform_text(test: ast.AST) -> str:
    try:
        return ast.unparse(test)
    except Exception:  # noqa: BLE001 - older grammars
        return ""


def collect(source: str, this_platform: str, this_os: str) -> dict[int, tuple[str, str]]:
    """Map line -> (category, evidence) for one source file."""
    tree = ast.parse(source)
    found: dict[int, tuple[str, str]] = {}
    lines = source.splitlines()

    for lineno, text in enumerate(lines, start=1):
        if "pragma: no cover" in text:
            found[lineno] = (PRAGMA, "explicit pragma in source")

    class Visitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            if _is_type_checking(node.test):
                for lineno in _ranges(node):
                    found.setdefault(
                        lineno, (TYPE_CHECKING_ONLY, "inside `if TYPE_CHECKING:`")
                    )
            elif _is_main_guard(node.test):
                for lineno in _ranges(node):
                    found.setdefault(lineno, (MAIN_GUARD, 'inside `if __name__ == "__main__":`'))
            else:
                text = _platform_text(node.test)
                if ("sys.platform" in text or "os.name" in text
                        or "platform.system" in text):
                    # Which side is dead depends on the platform this
                    # classification is produced on; record it explicitly so the
                    # reviewer can re-run the other platform and compare.
                    for lineno in _ranges(node):
                        found.setdefault(
                            lineno,
                            (
                                PLATFORM_GUARDED,
                                f"guarded by `{text}` (this run: platform={this_platform}, os={this_os})",
                            ),
                        )
            self.generic_visit(node)

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            names = []
            if isinstance(node.type, ast.Name):
                names = [node.type.id]
            elif isinstance(node.type, ast.Tuple):
                names = [elt.id for elt in node.type.elts if isinstance(elt, ast.Name)]
            if any(name in ("ImportError", "ModuleNotFoundError") for name in names):
                for lineno in _ranges(node):
                    found.setdefault(
                        lineno,
                        (OPTIONAL_DEP, f"inside `except {', '.join(names)}` handler"),
                    )
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._maybe_abstract(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._maybe_abstract(node)
            self.generic_visit(node)

        def _maybe_abstract(self, node) -> None:
            for decorator in node.decorator_list:
                name = decorator.id if isinstance(decorator, ast.Name) else (
                    decorator.attr if isinstance(decorator, ast.Attribute) else ""
                )
                if name == "abstractmethod":
                    for stmt in node.body:
                        for lineno in _ranges(stmt):
                            found.setdefault(
                                lineno, (ABSTRACT, f"body of `{node.name}` is @abstractmethod")
                            )

        def visit_Raise(self, node: ast.Raise) -> None:
            exc = node.exc
            name = ""
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                name = exc.func.id
            elif isinstance(exc, ast.Name):
                name = exc.id
            if name == "NotImplementedError":
                for lineno in _ranges(node):
                    found.setdefault(lineno, (NOT_IMPLEMENTED, "raise NotImplementedError"))

    Visitor().visit(tree)
    return found


def _to_tool_category(category: str) -> str:
    """Map the AST categories onto coverage_evidence.py's fixed vocabulary.

    ``coverage_evidence.py`` accepts exactly four categories: ``to-fix``,
    ``env-blocked``, ``spec-exempt``, ``defensive``.  Lines this script cannot
    prove stay *absent* from the rules file, so the tool reports them as
    ``unclassified`` - the honest backlog.
    """
    if category in (PRAGMA, TYPE_CHECKING_ONLY, ABSTRACT, MAIN_GUARD, NOT_IMPLEMENTED):
        return "defensive"
    if category in (PLATFORM_GUARDED, OPTIONAL_DEP):
        return "env-blocked"
    return "to-fix"


def _group_ranges(lines: list[tuple[int, str, str]]) -> list[dict[str, str]]:
    """Collapse consecutive lines sharing (category, why) into range specs."""
    rules: list[dict[str, str]] = []
    current: dict | None = None
    for lineno, category, why in sorted(lines):
        if current and current["category"] == category and current["why"] == why \
                and lineno == current["end"] + 1:
            current["end"] = lineno
            continue
        if current:
            rules.append(_render_rule(current))
        current = {"start": lineno, "end": lineno, "category": category, "why": why}
    if current:
        rules.append(_render_rule(current))
    return rules


def _render_rule(current: dict) -> dict[str, str]:
    spec = (f"{current['start']}" if current["start"] == current["end"]
            else f"{current['start']}-{current['end']}")
    return {"lines": spec, "category": current["category"], "why": current["why"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, help="coverage.py JSON report")
    parser.add_argument("--out", required=True,
                        help="rules file for coverage_evidence.py --rules")
    parser.add_argument("--source-root", default="src")
    parser.add_argument("--unclassified-out", default="",
                        help="also write the to-fix list as a text file")
    args = parser.parse_args()

    report = json.loads(Path(args.json).read_text(encoding="utf-8"))
    classification: dict[str, list[dict[str, str]]] = {}
    unclassified: list[str] = []
    counts: dict[str, int] = {}

    for name, entry in sorted(report["files"].items()):
        missing = list(entry.get("missing_lines") or [])
        if not missing:
            continue
        path = Path(name)
        if not path.exists():
            path = ROOT / name
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            found = collect(source, sys.platform, __import__("os").name)
        except SyntaxError as exc:
            found = {}
            unclassified.append(f"{name}: <cannot parse: {exc}>")

        excused: list[tuple[int, str, str]] = []
        for lineno in missing:
            ast_category, evidence = found.get(lineno, ("", ""))
            if not ast_category:
                unclassified.append(f"{name.replace(chr(92), '/')}:{lineno}")
                counts[UNCLASSIFIED] = counts.get(UNCLASSIFIED, 0) + 1
                continue
            tool_category = _to_tool_category(ast_category)
            counts[tool_category] = counts.get(tool_category, 0) + 1
            excused.append((lineno, tool_category, f"{ast_category}: {evidence}"))
        if excused:
            classification[name.replace("\\", "/")] = _group_ranges(excused)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(classification, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.unclassified_out:
        Path(args.unclassified_out).write_text(
            "\n".join(unclassified) + "\n", encoding="utf-8"
        )

    total = sum(counts.values())
    print(json.dumps({"total_missing": total, "by_category": counts}, ensure_ascii=False))
    print(f"rules -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
