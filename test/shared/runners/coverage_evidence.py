"""Turn a coverage.py JSON report into an auditable evidence pack.

The pack is deliberately boring: every number in the final report must be
recomputable from the raw ``coverage.json`` and every uncovered line must be
either present in the classification file or surfaced as ``unclassified``.

Usage::

    python test/shared/runners/coverage_evidence.py \
        --json test/artifacts/evidence/cov-main/coverage-main-strict.json \
        --out-dir test/reports/coverage-pack \
        --rules test/reports/coverage-pack/coverage-rules-auto.json \
        --source-root src

Rules file format (JSON).  ``lines`` accepts single numbers, ranges and lists
(``"12,14-18"``); every uncovered line not matched by a rule is reported as
``unclassified``::

    {
      "src/common/ssh.py": [
        {"lines": "691", "category": "defensive",
         "why": "run() never returns None on this branch"},
        {"lines": "704-710", "category": "env-blocked",
         "why": "needs a POSIX ssh binary; Windows client has none"}
      ]
    }

Categories are fixed: ``to-fix``, ``env-blocked``, ``spec-exempt``, ``defensive``.
Anything missing from the file is reported as ``unclassified`` so that a
reviewer can immediately see that the work of justifying uncovered lines is
not finished.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

CATEGORIES = ("to-fix", "env-blocked", "spec-exempt", "defensive")


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _line_text(source_root: Path, path: str, line: int, width: int = 110) -> str:
    file_path = source_root / Path(path)
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if 1 <= line <= len(text):
        return text[line - 1].strip()[:width]
    return ""


def _expand_spec(spec: str) -> list[int]:
    out: list[int] = []
    for chunk in str(spec).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            out.extend(range(int(start), int(end) + 1))
        else:
            out.append(int(chunk))
    return out


def _load_rules(path: str) -> dict[str, dict[str, dict]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expanded: dict[str, dict[str, dict]] = {}
    for file_path, rules in raw.items():
        per_line: dict[str, dict] = {}
        for index, rule in enumerate(rules):
            for line in _expand_spec(rule["lines"]):
                per_line[str(line)] = {
                    "category": rule.get("category", "unclassified"),
                    "why": rule.get("why", ""),
                    "_rule": f"{_norm(file_path)}#{index}",
                }
        expanded[_norm(file_path)] = per_line
    return expanded


def _rule_usage(path: str) -> dict[str, int]:
    """Declared line count of every rule, keyed ``file#index``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    usage: dict[str, int] = {}
    for file_path, rules in raw.items():
        for index, rule in enumerate(rules):
            usage[f"{_norm(file_path)}#{index}"] = len(_expand_spec(rule["lines"]))
    return usage


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provenance(json_path: Path) -> dict:
    """Everything a reviewer needs to re-run this exact measurement.

    The pack answers "was the tree even the tree you claim?": on a dirty
    worktree a commit id alone is not enough, so the content hash of every
    ``src/**/*.py`` is recorded next to the python/coverage versions, the
    git dirty-file list, the exact command line and the input report hash.
    """
    import hashlib
    import platform
    import subprocess
    import sys
    import time

    def git(*cmd: str) -> str:
        try:
            done = subprocess.run(
                ["git", *cmd], capture_output=True, text=True, timeout=30
            )
            return done.stdout.strip()
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            return f"<git failed: {exc}>"

    entries: list[tuple[str, str]] = []
    for path in sorted(Path("src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        entries.append((path.as_posix(), _sha256(path)))
    tree = hashlib.sha256(
        "".join(f"{name}:{digest}\n" for name, digest in entries).encode("utf-8")
    ).hexdigest()
    try:
        coverage_version = subprocess.run(
            [sys.executable, "-m", "coverage", "--version"],
            capture_output=True, text=True,
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        coverage_version = f"<coverage --version failed: {exc}>"
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": " ".join(sys.argv),
        "python": sys.version.split()[0],
        "coverage": coverage_version,
        "platform": platform.platform(),
        "git_head": git("rev-parse", "HEAD"),
        "git_dirty_files": [
            line for line in git("status", "--porcelain").splitlines() if line.strip()
        ],
        "src_file_count": len(entries),
        "src_tree_sha256": tree,
        "coverage_json": str(json_path),
        "coverage_json_sha256": _sha256(json_path) if json_path.exists() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="coverage.py JSON report")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--classification", default="")
    parser.add_argument("--rules", default="")
    parser.add_argument("--source-root", default="src")
    parser.add_argument("--top", type=int, default=0, help="limit module table rows")
    args = parser.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    files = data["files"]
    totals = data["totals"]
    source_root = Path(args.source_root)

    classification: dict[str, dict[str, dict]] = {}
    rule_usage: dict[str, int] = {}
    if args.rules:
        classification.update(_load_rules(args.rules))
        rule_usage = _rule_usage(args.rules)
    if args.classification:
        raw = json.loads(Path(args.classification).read_text(encoding="utf-8"))
        classification.update({_norm(k): v for k, v in raw.items()})

    rows = []
    uncovered_lines: list[str] = []
    branch_lines: list[str] = []
    cat_counter: Counter[str] = Counter()
    matched_rules: Counter[str] = Counter()
    unclassified: list[str] = []
    bad_category: list[str] = []

    for path, entry in sorted(files.items()):
        norm = _norm(path)
        summary = entry["summary"]
        missing = list(entry.get("missing_lines") or [])
        missing_branches = list(entry.get("missing_branches") or [])
        rows.append(
            {
                "file": norm,
                "statements": summary["num_statements"],
                "missing_lines": summary["missing_lines"],
                "statement_pct": round(
                    summary.get("percent_statements_covered", summary["percent_covered"]), 2
                ),
                "branches": summary.get("num_branches") or 0,
                "missing_branches": summary.get("missing_branches") or 0,
                "branch_pct": round(summary["percent_branches_covered"], 2)
                if summary.get("percent_branches_covered") is not None
                else None,
            }
        )
        per_file = classification.get(norm, {})
        for line in missing:
            item = per_file.get(str(line))
            if item is None:
                unclassified.append(f"{norm}:{line}")
                covered_by = "unclassified"
            else:
                covered_by = item.get("category", "unclassified")
                matched_rules[item.get("_rule", "")] += 1
                if covered_by not in CATEGORIES:
                    bad_category.append(f"{norm}:{line} -> {covered_by}")
                    covered_by = "unclassified"
                else:
                    why = (item.get("why") or "").strip()
                    if not why:
                        bad_category.append(f"{norm}:{line} -> category without why")
                        covered_by = "unclassified"
            cat_counter[covered_by] += 1
            text = _line_text(source_root, norm, line)
            uncovered_lines.append(f"{norm}:{line}\t{covered_by}\t{text}")
        for src, dst in missing_branches:
            branch_lines.append(
                f"{norm}:{src}->{dst}\t{_line_text(source_root, norm, src, 90)}"
            )

    rows.sort(key=lambda r: (-r["missing_lines"], r["file"]))
    if args.top:
        rows = rows[: args.top]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_out = {
        "source_json": str(Path(args.json).resolve()),
        "totals": totals,
        "derived": {
            "statement_pct": round(totals.get("percent_statements_covered", 0.0), 2),
            "branch_pct": round(totals["percent_branches_covered"], 2)
            if totals.get("percent_branches_covered") is not None
            else None,
            "combined_pct": round(totals.get("percent_covered", 0.0), 2),
            "files": len(files),
            "missing_line_entries": len(uncovered_lines),
            "missing_branch_entries": len(branch_lines),
        },
        "classification": {
            "counts": dict(cat_counter),
            "unclassified_count": len(unclassified),
            "invalid_entries": bad_category,
            "stale_rules": sorted(
                rule for rule in rule_usage if not matched_rules.get(rule)
            ),
            "classification_file": (
                str(Path(args.classification).resolve()) if args.classification else None
            ),
            "rules_file": str(Path(args.rules).resolve()) if args.rules else None,
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "| file | stmts | miss | line% | branches | miss-br | branch% |\n",
        "|---|---:|---:|---:|---:|---:|---:|\n",
    ]
    for row in rows:
        bp = "n/a" if row["branch_pct"] is None else f"{row['branch_pct']:.1f}"
        lines.append(
            f"| `{row['file']}` | {row['statements']} | {row['missing_lines']} | "
            f"{row['statement_pct']:.1f} | {row['branches']} | {row['missing_branches']} | {bp} |\n"
        )
    (out_dir / "modules.md").write_text("".join(lines), encoding="utf-8")

    (out_dir / "uncovered-lines.tsv").write_text(
        "# path:line\tcategory\tsource\n" + "\n".join(uncovered_lines) + "\n",
        encoding="utf-8",
    )
    (out_dir / "missing-branches.tsv").write_text(
        "# path:from->to\tsource\n" + "\n".join(branch_lines) + "\n", encoding="utf-8"
    )
    (out_dir / "unclassified.txt").write_text("\n".join(unclassified) + "\n", encoding="utf-8")

    (out_dir / "manifest.json").write_text(
        json.dumps(_provenance(Path(args.json)), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary_out["derived"], ensure_ascii=False))
    print(json.dumps(summary_out["classification"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
