# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 20:45
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
#   ① 环境/前置：见正文的 require_environment 或首段只读探测（本节不适用时正文写明）；
#   ②③ 构建/校验被改对象：由用例内建前置保证；④ 只做被测动作；
#   ⑤ 打印期望 vs 实测（判据见正文）；⑥ 半真机不清理现场，留下状态便于复核。
"""calibre 包 **HTTP 业务面** 探针（第五轮新增，真机）。

与 ``calibre_env_probe.py``（direct 直连、自己拼命令）不同，本探针走**产品路径**：
``calibre.check_env`` → ``calibre.drc|lvs``（blocking）→ ``calibre.status`` →
``calibre.read_results``，即"用户经业务面调用 calibre 包"的真实形状。

为什么要这个探针：常驻注册表原先没有任何 ``role.command.calibre`` 工具事实，
``test/live/packages/`` 也没有 calibre 套件 —— 新注册的 calibre 包 **0 真机覆盖**。
第五轮起用独立 work-dir（``test/artifacts/env/s11-calibre``）+ 独立业务面
（8128）把这条路径打通，本探针负责留证。

用法::

    python test/semi/probes/calibre_package_http_probe.py --kind drc \
        --gds /home/Gent/project/vblog/s11_inv/s11/inv.gds --top inv \
        --deck /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre/drc/calibre.drc \
        --out test/artifacts/evidence/round5-main/calibre-drc.json

    # LVS 需要源网表（CDL/SPICE）
    python test/semi/probes/calibre_package_http_probe.py --kind lvs ... --cdl /path/x.cdl

环境（一次性，2026-09-23 建）::

    # 1) 专用 work-dir + 注册表：复制常驻注册表里任一真实例条目，新增
    #    role.command.calibre.bin，例如
    #    test/artifacts/env/s11-calibre/registry.json:
    #      {"s11cal": {<calprobe 条目副本>,
    #                  "token": "vb-s11cal",
    #                  "roles": {"command": {"calibre": {"bin":
    #                     "/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre"}}}}}
    # 2) 独立业务面（避免打扰常驻 8127）：
    #    PYTHONPATH=src python -m server.api_server --port 8128 \
    #        --work-dir test/artifacts/env/s11-calibre
    # 3) LVS 的 --cdl 是**远端路径**（包不代传源网表）：先 scp 上去再用。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

#: 真实 PDK 根（calprobe 环境里 /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW）；只用于"缺省 deck"解析
PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def call(base: str, operation: str, token: str, **fields) -> dict:
    body = json.dumps({"operation": operation, "token": token, **fields}).encode("utf-8")
    request = urllib.request.Request(
        base, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # 默认走**常驻业务面**（8127 + vb-vblog）：calibre_bin 已配在该 token 的 command role 上。
    # 历史专用面 8128 / vb-s11cal 已停用；要用需先按 §0 准备（或显式 --base/--token 指到别的实例）。
    parser.add_argument("--base", default="http://127.0.0.1:8127/api/operation")
    parser.add_argument("--token", default="vb-vblog")
    parser.add_argument("--kind", choices=("env", "drc", "lvs"), default="drc")
    parser.add_argument("--gds", default="/home/Gent/project/vblog/s11_inv/s11/inv.gds")
    parser.add_argument("--top", default="inv")
    # 缺省 deck 按 kind 解析：`--kind drc/lvs` 不带 deck 会被业务面判为
    # 「deck must be a non-empty string」（实测：探针默认空串直接红，白跑一次）。
    # 需要覆盖时显式给 --deck。
    parser.add_argument("--deck", default="")
    parser.add_argument("--cdl", default="")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--timeout", type=int, default=900,
                        help="blocking run 的超时（秒）；仅 --kind drc/lvs 用")
    parser.add_argument("--no-block", action="store_true",
                        help="不阻塞：立即返回 job_id，之后用 calibre.status 轮询")
    args = parser.parse_args(argv)

    evidence: dict = {"base": args.base, "token": args.token, "kind": args.kind}
    if args.kind == "env":
        evidence["check_env"] = call(args.base, "calibre.check_env", args.token,
                                     deck=args.deck or None)
        ok = bool(evidence["check_env"].get("ok"))
    else:
        deck = args.deck
        if not deck and args.kind in ("drc", "lvs"):
            deck = (f"{PDK}/Calibre/drc/calibre.drc" if args.kind == "drc"
                    else f"{PDK}/Calibre/lvs/calibre.lvs")
        fields = {"gds": args.gds, "top": args.top, "deck": deck,
                  "blocking": not args.no_block, "timeout": args.timeout}
        if args.cdl:
            fields["cdl"] = args.cdl
        evidence["run"] = call(args.base, f"calibre.{args.kind}", args.token, **fields)
        data = evidence["run"].get("data") or {}
        value = data.get("value") or {}
        job_id = value.get("job_id")
        run_dir = value.get("run_dir") or args.run_dir
        evidence["job"] = {"job_id": job_id, "run_dir": run_dir,
                           "status": value.get("status")}
        if job_id or run_dir:
            evidence["status"] = call(args.base, "calibre.status", args.token,
                                      job_id=job_id, run_dir=run_dir, kind=args.kind)
            evidence["read_results"] = call(
                args.base, "calibre.read_results", args.token,
                job_id=job_id, run_dir=run_dir, kind=args.kind, limit=20,
            )
        ok = bool(evidence["run"].get("ok"))

    text = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text[:4000])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
