"""用例档位审计：每个 op 在 semi/live 的调用点数量 + 是否含"非法档"线索。

回答《全量测试准则》里"一个操作要写多档用例（最简/日常/边界/非法）"的覆盖状况：

* `single`：semi/live 里该 op 只出现 **1 次**（可疑：只有一个档位）；
* `no_negative`：该 op 所在 TB 里没有"预期失败"线索（`expect_fail` / `_write_fails` /
  `must fail` / `_expect_failure` …）—— 线索缺失不等于没有非法档（可能用了别的 helper），
  但需要人工逐条复核。

用法::

    PYTHONPATH=src python test/shared/runners/case_profile_audit.py \
        [--matrix test/reports/round9/op-param-matrix.json] \
        [--out test/reports/round10/case-profile-audit-r10.json]

输出 JSON + 人读 md；**不自动判定通过**，只出清单供人工分诊（与 round9 口径一致）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST = ROOT / "test"

#: 预期失败/非法档的写法线索（缺了不一定是缺口，但要看一眼）
NEGATIVE_HINTS = (
    "expect_fail", "expect_failures", "_write_fails", "must fail",
    "_expect_failure", "assert not", "ok) is not True", "ok) is not true",
    "structured failure", "结构化失败", "拒绝",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", default="test/reports/round9/op-param-matrix.json")
    parser.add_argument("--out", default="test/reports/round10/case-profile-audit-r10.json")
    args = parser.parse_args(argv)

    live_files = [p for p in TEST.rglob("*.py")
                  if "/live/" in p.as_posix() or "/semi/" in p.as_posix()]
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in live_files}

    doc = json.loads(Path(args.matrix).read_text(encoding="utf-8"))
    rows = doc["rows"] if isinstance(doc, dict) else doc

    ops: dict[str, dict] = {}
    for row in rows:
        op = str(row.get("op") or "")
        if "." not in op:
            continue
        entry = ops.setdefault(op, {"sites": set()})
        entry["sites"].update(row.get("op_sites") or [])

    def site_path(site: str) -> str:
        return str(site).replace("\\", "/").split(":")[0]

    single: list[str] = []
    no_negative: list[str] = []
    for op, entry in sorted(ops.items()):
        short = ".".join(op.split(".")[-2:])
        wanted = {site_path(s) for s in entry["sites"]}
        live_texts = {p: t for p, t in texts.items()
                      if str(p.relative_to(ROOT)).replace("\\", "/") in wanted}
        hits = sum(t.count(f'"{op}"') + t.count(f"'{op}'")
                   + t.count(f'"{short}"') + t.count(f"'{short}'")
                   for t in live_texts.values())
        negative = any(any(h in t for h in NEGATIVE_HINTS) for t in live_texts.values())
        if hits < 2:
            single.append(op)
        if not negative:
            no_negative.append(op)

    payload = {
        "matrix": args.matrix,
        "ops_total": len(ops),
        "single_live_site": single,
        "no_negative_hint": no_negative,
        "note": "清单仅供人工分诊：single=该 op 在 live/semi 只出现 1 次；"
                "no_negative_hint=所在 TB 无预期失败线索（可能用别的写法，需人工确认）。",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    md = out.with_suffix(".md")
    lines = [
        "# 用例档位审计（semi/live 调用点 × 非法档线索）",
        "",
        f"> 矩阵：`{args.matrix}`；op 总数 **{len(ops)}**。",
        f"> `single`（live/semi 只出现 1 次）**{len(single)}**；"
        f"`no_negative_hint` **{len(no_negative)}**。",
        "",
        "## single（需人工确认是否只有一个档位）",
        "",
        *(f"- `{op}`" for op in single),
        "",
        "## no_negative_hint（需人工确认非法档写法）",
        "",
        *(f"- `{op}`" for op in no_negative),
        "",
        "> 口径：本工具只出清单；分诊结论请写在 round10 的审计 md 里（含误报/真实缺口）。",
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ops={len(ops)} single={len(single)} no_negative_hint={len(no_negative)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
