# -*- coding: utf-8 -*-
"""半真机层探针批量入口：按主题把 `test/semi/probes/*.py` 跑一遍并落证据。

为什么需要它：半真机探针是**一次性诊断脚本**，历史上常常"只在某一轮跑过"，下一轮没人记得
怎么跑（参数、依赖都散在各文件 docstring 里）。本 runner 把"怎么跑"固化成一张表，每轮至少
复跑一次，避免出现"矩阵标着已验、其实本轮没跑"（见 `test/reports/round7-测试报告.md` §3）。

用法::

    $env:PYTHONPATH='src'
    python test/shared/runners/run_semi_probes.py --group all
    python test/shared/runners/run_semi_probes.py --group calibre
    python test/shared/runners/run_semi_probes.py --probe symbol_pkg_probe.py --dry

约定：探针自己负责把证据写进 `test/artifacts/evidence/**`；runner 只跑 + 记录 rc/stdout 尾巴/耗时，
汇总成一份 JSON；**探针红就是红**，runner 不重试、不改口径。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBES_DIR = ROOT / "test" / "semi" / "probes"
LOG_DIR = ROOT / "test" / "artifacts" / "evidence" / "round7" / "semi-logs"
DEFAULT_OUT = ROOT / "test" / "artifacts" / "evidence" / "round7" / "semi-probes.json"

WORK_VBLOG = "test/artifacts/env/log-vblog"
TOKEN_VBLOG = "vb-vblog"
TOKEN_USER1 = "vb-vbuser1"
TOKEN_USER2 = "vb-vbuser2"


def _pdk_token() -> str:
    """PDK/Calibre 实例的 token：优先环境变量，其次读常驻注册表（registry.json 已 gitignore）。

    报告/仓库里不写明文 token（见 `test/docs/写TB规范.md` §5 红线）。
    """
    import json
    import os

    token = os.environ.get("VB_PDK_TOKEN", "")
    if token:
        return token
    registry = (Path(__file__).resolve().parents[3] / "test" / "artifacts" / "env"
                / "log-vblog" / "registry.json")
    try:
        users = json.loads(registry.read_text(encoding="utf-8"))
        return str((users.get("calprobe") or {}).get("token") or "")
    except Exception:  # noqa: BLE001 - 拿不到就留空，探针会给出"token 为空"的明确报错
        return ""


TOKEN_PDK = _pdk_token() or "<PDK_TOKEN>"
PDK_ROOT = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"
CADS = "/opt/eda/cadence/IC618"


def entry(group: str, argv: list[str] | None = None, needs: str = "",
          path: str | None = None, timeout: int = 900) -> dict:
    return {"group": group, "argv": argv or [], "needs": needs,
            "path": path, "timeout": timeout}


PROBES: dict[str, dict] = {
    "layout_lock_ownership_probe.py": entry(
        "layout", ["--work-dir", WORK_VBLOG, "--token", TOKEN_VBLOG], "业务面 8127 + 真 Virtuoso"),
    "layout_p044_second_write_probe.py": entry(
        "layout", ["--work-dir", WORK_VBLOG, "--token", TOKEN_VBLOG], "P-044 复验（真 Virtuoso）"),
    "twouser_same_view_probe.py": entry(
        "layout", ["--work-dir", WORK_VBLOG, "--token-a", TOKEN_USER1, "--token-b", TOKEN_USER2,
                   "--lib", "serdes_rx", "--cell", "twouser_probe_r7",
                   "--out", "test/artifacts/evidence/round7/twouser-same-view.json"],
        "两个真实用户 + /project 共享库（serdes_rx；TEST_LIB 只在 calprobe 的 cds.lib 里）"),
    "gui_display_probe.py": entry(
        "gui", ["--work-dir", WORK_VBLOG, "--token", TOKEN_VBLOG], "X11 display + 真实 CIW"),
    # 位置参数：`<mode> <lib> <cell> [view] [overwrite]`；`--token` 换实例
    # （SRX65/DI65 这些库在 PDK 实例的 cds.lib 里，vblog 实例看不到）
    "symbol_pkg_probe.py": entry(
        "symbol", ["read", "SRX65", "ctle_core", "symbol", "--token", TOKEN_PDK],
        "PDK 实例（SRX65/ctle_core 只在 calprobe 的 cds.lib 里）"),
    "symbol_regen_handle_probe.py": entry("symbol", [], "PDK 实例"),
    "symbol_generate_hierarchy_handle_probe.py": entry("symbol", [], "PDK 实例"),
    "symbol_screenshot_probe.py": entry("symbol", [], "X11 display + 真实窗口"),
    "symbol_http_400_repro.py": entry("symbol", [], "业务面 8127"),
    "shared_cdf_pollution_probe.py": entry("schematic", [], "PDK 实例 + peer 用户"),
    "schematic_pin_ops_probe.py": entry("schematic", [], "PDK 实例"),
    "maestro_env_probe.py": entry("maestro", [], "真 Virtuoso + ADE 库"),
    "maestro_pkg_probe.py": entry("maestro", [], "真 Virtuoso"),
    "maestro_session_conflict_probe.py": entry("maestro", [], "只读诊断（真 Virtuoso）"),
    "maestro_leak_probe.py": entry("maestro", [], "被 import 的库（无 __main__，单跑会红）"),
    "maestro_e2e_probe.py": entry("maestro", [], "真 Virtuoso + SKILL（较慢）", None, 1500),
    "maestro_screenshot_probe.py": entry("maestro", [], "X11 display + 真实 ADE 窗口"),
    "calibre_env_probe.py": entry("calibre", ["--facts"], "calibre 环境（远程）"),
    "calibre_cdl_probe.py": entry("calibre", [], "PDK 实例 + auCdl"),
    "cdl_export_variants_probe.py": entry("calibre", [], "PDK 实例 + 多参数导出"),
    "calibre_package_http_probe.py": entry("calibre", ["--kind", "env"], "业务面 8128"),
    "spectre_ac_pipeline_probe.py": entry("spectre", [], "PDK 实例"),
    "skill_syntax_matrix_tb.py": entry("skill", [], "业务面 8127"),
    # `--tree` 需要具体目录；主用法是 `--check`（远端树 → 本地解析）
    "skill_tooling_probe.py": entry("skill", ["--check"], "业务面 8127 + 远端 finder 树"),
    # 远端模式才是真链路（middle → SSH → wsl-gent 的 Cadence 文档树）
    "skillref_probe.py": entry(
        "skill", ["--source", "remote", "--doc-root", "/opt/eda/cadence/IC618/doc",
                  "--doc-token", TOKEN_VBLOG], "wsl-gent Cadence 文档树"),
    # 本机有一份 Cadence 文档拷贝（C:\Users\user\Desktop\doc，223 项）→ local 模式可跑
    "docs_search_probe.py": entry(
        "skill", ["--root", r"C:\Users\user\Desktop\doc", "--query", "schCreatePin"],
        "本地 Cadence 文档拷贝"),
    "paramiko_ssh_config_true_probe.py": entry("transport", ["--connection"], "ssh_config 主机"),
    "lone_surrogate_probe.py": entry("transport", [], "本地 HTTP 边界"),
    "one_shot_burst_tb.py": entry(
        "transport", ["--work-dir", "test/artifacts/env/one-shot-burst", "--token", TOKEN_VBLOG],
        "业务面 8127", "test/semi/transport"),
    "log_matrix_real_tb.py": entry(
        "transport", ["--work-dir", WORK_VBLOG, "--token", TOKEN_VBLOG], "业务面 8127",
        "test/semi/transport"),
    "ssh_backend_semi_tb.py": entry("transport", [], "可达 SSH 主机", "test/semi/transport"),
    "role_credential_isolation_tb.py": entry(
        "transport", ["--out", "test/artifacts/evidence/round7/role-credential-isolation.json"],
        "两把真钥（见 test/reports/internal/环境Runbook-内部.md §3.1）", "test/semi/transport"),
}


def _run_one(name: str, spec: dict, *, dry: bool) -> dict:
    base = PROBES_DIR if spec.get("path") is None else ROOT / str(spec["path"])
    script = base / name
    if not script.is_file():
        return {"probe": name, "status": "missing", "detail": str(script)}
    argv = [sys.executable, str(script), *[str(x) for x in spec.get("argv", [])]]
    if dry:
        return {"probe": name, "status": "dry", "argv": argv[2:], "needs": spec.get("needs")}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                             timeout=spec.get("timeout", 900),
                             env={**os.environ, "PYTHONPATH": "src"})
        rc, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        rc = 124
        out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) \
            else (exc.stdout or "")
        err = f"TIMEOUT after {spec.get('timeout', 900)}s"
    elapsed = round(time.monotonic() - started, 2)
    log_path.write_text(f"$ {' '.join(argv)}\n\n--- stdout ---\n{out}\n--- stderr ---\n{err}\n",
                        encoding="utf-8")
    tail = [line for line in (out.strip().splitlines() + err.strip().splitlines())[-6:] if line]
    return {"probe": name, "status": "ok" if rc == 0 else "fail", "rc": rc,
            "seconds": elapsed, "log": str(log_path.relative_to(ROOT)),
            "tail": tail, "needs": spec.get("needs")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="all")
    parser.add_argument("--probe", action="append", default=[])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--dry", action="store_true", help="只打印将要执行的命令")
    args = parser.parse_args(argv)

    selected = {name: spec for name, spec in PROBES.items()
                if (not args.probe or name in args.probe)
                and (args.group == "all" or spec.get("group") == args.group)}
    if not selected:
        parser.error(f"没有匹配的探针（--group {args.group}）")

    results = [_run_one(name, spec, dry=args.dry) for name, spec in selected.items()]
    failed = [r["probe"] for r in results if r["status"] == "fail"]
    payload = {"group": args.group, "count": len(results), "failed": failed,
               "ok": not failed, "results": results}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in results:
        extra = f"  rc={row.get('rc')} {row.get('seconds')}s" if row.get("rc") is not None else ""
        print(f"[{row['status']:>7}] {row['probe']}{extra}")
        for line in row.get("tail", [])[-2:]:
            print(f"           {line[:150]}")
    print(f"\nsummary: {out}  ok={payload['ok']}  failed={failed}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
