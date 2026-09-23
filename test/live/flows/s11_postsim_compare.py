"""S11 后仿对照驱动：同一测试台跑「原理图网表」与「版图提取网表」，比对 DC 节点。

背景：完整寄生 PEX 的 ``-fmt spice`` 阶段当前有缺陷
（``bug-20260922T130754Z-vblog-836e3215``，见 test/reports/问题登记.md P-034），
所以本驱动用 Calibre LVS 的**版图提取网表**（``svdb/<top>.sp``，无寄生）做后仿，
并把结果与原理图 CDL 网表逐节点对比——两个 netlist 使用同一套 PDK 模型、
同一测试台与同一 ``soft_bin=allmodels`` 口径。

两个网表由测试工程师准备（当前落在
``test/artifacts/evidence/s11-postsim/cmp_top_pre.scs`` / ``cmp_top_post.scs``），
本脚本只负责：提交 spectre.run → 提取 DC 节点 → 计算差值 → 落盘证据。

    python test/live/flows/s11_postsim_compare.py \
        --sim-token <calprobe-token> \
        --pre  test/artifacts/evidence/s11-postsim/cmp_top_pre.scs \
        --post test/artifacts/evidence/s11-postsim/cmp_top_post.scs \
        --out  test/artifacts/evidence/s11-postsim/postsim-evidence.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
API = "http://127.0.0.1:8127/api/operation"

#: 原理图 / 版图两侧的等价节点（见 artifacts/s11-postsim/README.md 的接线说明）
NODE_PAIRS = (
    ("out", "dc_out", "dc_out"),
    ("v1/n5", "dc_XI0.v1", "dc_n5"),
    ("v2/n6", "dc_XI0.v2", "dc_n6"),
    ("tail/n2", "dc_XI0.tail", "dc_n2"),
)


def call(payload: dict, timeout: int = 900) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return {"ok": False, "error": f"HTTP {error.code}: {error.read().decode('utf-8')[:300]}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim-token", required=True)
    parser.add_argument("--pre", required=True)
    parser.add_argument("--post", required=True)
    parser.add_argument("--out", default=str(ROOT / "test/artifacts/evidence/s11-postsim/postsim-evidence.json"))
    parser.add_argument("--job-prefix", default="cmp_top")
    args = parser.parse_args()

    pre = Path(args.pre).resolve()
    post = Path(args.post).resolve()
    for path in (pre, post):
        if not path.exists():
            raise SystemExit(f"netlist not found: {path}")

    clean = call(
        {
            "operation": "basic.command.run",
            "token": args.sim_token,
            "timeout": 120,
            "cmd": (
                "rm -rf /home/Gent/.virtuoso-bridge/calprobe/spectre/spectre/"
                f"{args.job_prefix}_pre /home/Gent/.virtuoso-bridge/calprobe/spectre/spectre/{args.job_prefix}_post "
                "&& echo cleaned"
            ),
        }
    )
    if not clean.get("ok"):
        raise SystemExit(f"cannot clean run dirs: {clean.get('error')}")

    response = call(
        {
            "operation": "spectre.run",
            "token": args.sim_token,
            "tasks": [
                {"job": f"{args.job_prefix}_pre", "netlist": str(pre)},
                {"job": f"{args.job_prefix}_post", "netlist": str(post)},
            ],
            "max_workers": 2,
            "mode": "spectre",
            "parse": "auto",
            "download": True,
            "keep_run_dir": True,
            "timeout": 900,
        }
    )
    runs = ((response.get("data") or {}).get("value") or {}).get("runs") or []
    if not response.get("ok") or len(runs) != 2:
        raise SystemExit(f"spectre.run failed: {json.dumps(response, ensure_ascii=False)[:500]}")

    by_job = {run.get("job"): (run.get("value") or {}) for run in runs}
    pre_data = by_job[f"{args.job_prefix}_pre"].get("data") or {}
    post_data = by_job[f"{args.job_prefix}_post"].get("data") or {}

    rows = []
    for label, pre_key, post_key in NODE_PAIRS:
        a = pre_data.get(pre_key)
        b = post_data.get(post_key)
        delta = abs(a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        rows.append({"node": label, "pre": a, "post": b, "abs_delta_v": delta})
    numeric = [row["abs_delta_v"] for row in rows if row["abs_delta_v"] is not None]
    max_delta = max(numeric) if numeric else None

    evidence = {
        "stage": "post-sim (S11, extracted layout netlist without parasitics)",
        "method": {
            "pre": str(pre),
            "post": str(post),
            "analysis": "DC operating point on a common testbench (PDK tt_25/tt_18, soft_bin=allmodels)",
            "parasitic_pex_blocked_by": "bug-20260922T130754Z-vblog-836e3215 (P-034)",
        },
        "node_comparison": rows,
        "max_abs_delta_v": max_delta,
        "verdict": "match" if (max_delta is not None and max_delta < 1e-3) else "check",
        "spectre": {
            job: {"status": value.get("status"), "output_dir": value.get("output_dir")}
            for job, value in by_job.items()
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: evidence[k] for k in ("max_abs_delta_v", "verdict")}, ensure_ascii=False))
    for row in rows:
        print(f"{row['node']:8s} pre={row['pre']!r} post={row['post']!r} delta={row['abs_delta_v']}")
    return 0 if evidence["verdict"] == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
