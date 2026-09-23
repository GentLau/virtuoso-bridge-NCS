"""Probe: remote SKILL Finder tree -> local parse -> search (design PoC).

Validates the skill_tooling data path before the package exists:
download the remote ``doc/finder/SKILL`` tree with one recursive
``basic.file.download`` call, parse it with the stdlib-only parser vendored
in ``tools/skill_doc_server.py``, then cross-check against the 8123 service.

Usage:
    python test/semi/probes/skill_tooling_probe.py --check --compare-8123
    python test/semi/probes/skill_tooling_probe.py --tree <local finder/SKILL dir>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_TREE = (
    ROOT / "test" / "artifacts" / "skill-tooling-tb" / "probe" / "finder" / "SKILL"
)
DOC_SERVER = ROOT / "tools" / "skill_doc_server.py"
DOC_SERVICE = "http://127.0.0.1:8123"


def load_doc_server():
    """Import tools/skill_doc_server.py by path (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("skill_doc_server", DOC_SERVER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses resolves annotations through sys.modules; register first.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def service_find(query: str, mode: str = "fuzzy", limit: int = 50) -> list:
    params = urllib.parse.urlencode({"q": query, "mode": mode, "limit": limit})
    url = f"{DOC_SERVICE}/api/find?{params}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["results"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    parser.add_argument("--check", action="store_true", help="assert probe expectations")
    parser.add_argument(
        "--compare-8123", action="store_true", help="cross-check against the 8123 service"
    )
    args = parser.parse_args()

    tree = args.tree
    if not tree.is_dir():
        print(f"FAIL tree not found: {tree}")
        return 2

    doc = load_doc_server()
    entries = doc.parse_fnd_directory(tree)
    files = sorted(p.name for p in tree.rglob("*.fnd"))

    finder = doc.SKILLFinder()
    finder.load(tree)
    exact = finder.search("dbOpenCellViewByType", mode="exact", limit=5)
    fuzzy = finder.search("dbOpenCellView", mode="fuzzy", limit=5)

    summary = {
        "tree": str(tree),
        "fnd_files": len(files),
        "entries": len(entries),
        "exact_hits": [e.name for e in exact],
        "fuzzy_hits": [e.name for e in fuzzy],
    }
    if exact:
        summary["exact_syntax"] = " ".join(exact[0].syntax.split())

    if args.compare_8123:
        names = sorted(e["name"] for e in service_find("dbOpenCellView", "fuzzy", 5))
        summary["service_8123_fuzzy"] = names
        summary["matches_service"] = names == sorted(e.name for e in fuzzy)

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.check:
        return 0

    problems = []
    if len(files) < 30:
        problems.append(f"expected >=30 .fnd files, got {len(files)}")
    if len(entries) < 8000:
        problems.append(f"expected >=8000 entries, got {len(entries)}")
    if "dbOpenCellViewByType" not in [e.name for e in exact]:
        problems.append("exact search missed dbOpenCellViewByType")
    if args.compare_8123 and not summary.get("matches_service"):
        problems.append("local parse differs from the 8123 doc service")
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        return 1
    print("PASS skill-tooling data path (download -> parse -> search)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
