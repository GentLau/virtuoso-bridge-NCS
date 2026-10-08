# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 23:00
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：本探针是**纯本机取证**——
#   ① 无需真机/靶机（不连业务面）；②③ 用现成 Cadence 文档树当输入（无持久对象）；
#   ④ 跑一次 legacy 全文检索；⑤ 打印命中数与耗时（期望 vs 实测）；⑥ 不落盘除 --out 指定的证据。
"""Probe: run the legacy full-text doc search (src_bak docs_search) locally.

Answers "can we do full-text search at all?" without touching 8123: the legacy
``docs_search.py`` is stdlib-only at import time, so it can be executed
standalone against a real Cadence doc tree.

Usage:
    python test/semi/probes/docs_search_probe.py --root <doc dir> --query "ground bounce"
    python test/semi/probes/docs_search_probe.py --root C:\\Users\\user\\Desktop\\doc --query "..." --cache-root <dir>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODULE_PATH = ROOT / "src_bak" / "virtuoso_bridge" / "virtuoso" / "docs_search.py"


def load_docs_search():
    spec = importlib.util.spec_from_file_location("legacy_docs_search", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--cache-root", type=Path, default=None)
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"FAIL root not found: {args.root}")
        return 2

    module = load_docs_search()
    started = time.perf_counter()
    results = module.search_docs(
        args.query,
        [args.root],
        limit=args.limit,
        cache_root=args.cache_root,
        rebuild=False,
    )
    elapsed = time.perf_counter() - started

    summary = {
        "root": str(args.root),
        "query": args.query,
        "cache_root": str(args.cache_root) if args.cache_root else None,
        "elapsed_s": round(elapsed, 2),
        "hits": len(results),
        "results": [
            {
                "kind": item.get("kind"),
                "relative_path": item.get("relative_path"),
                "title": (item.get("title") or "")[:80],
                "snippet": " ".join(str(item.get("snippet") or "").split())[:180],
            }
            for item in results
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
