# -*- coding: utf-8 -*-
"""半真机层探针批量入口：按主题把 `test/semi/probes/*.py` 跑一遍并落证据。

为什么需要它：半真机探针是**一次性诊断脚本**，历史上常常"只在某一轮跑过"，下一轮没人记得
怎么跑（参数、依赖都散在各文件 docstring 里）。本 runner 把"怎么跑"固化成一张表，每轮至少
复跑一次，避免出现"矩阵标着已验、其实本轮没跑"（见 `test/reports/round7-测试报告.md` §3）。

用法::

    $env:PYTHONPATH='src'
    python test/shared/runners/run_semi_probes.py --group all
    python test/shared/runners/run_semi_probes.py --group calibre
    python test/shared/runners/run_semi_probes.py --probe calibre_env_probe.py --dry

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
# 探针日志与结果始终落在「本次 --out 的同一目录」下（run-id 由调用方决定），
# 不写死某一轮——2026-09-28 修：原来写死 round7，第八轮的日志会混进第七轮目录。
DEFAULT_OUT = ROOT / "test" / "artifacts" / "evidence" / "semi-probes.json"

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
    "layout_depth_probe.py": entry(
        "layout", [], "业务面 8127 + vb-vblog（P-082 depth>0 红灯钉）"),
    "layout_p044_second_write_probe.py": entry(
        "layout", ["--work-dir", WORK_VBLOG, "--token", TOKEN_VBLOG], "P-044 复验（真 Virtuoso）"),
    "twouser_same_view_probe.py": entry(
        "layout", ["--work-dir", WORK_VBLOG, "--token-a", TOKEN_USER1, "--token-b", TOKEN_USER2,
                   "--lib", "serdes_rx", "--cell", "twouser_probe_r7",
                   "--out", "test/artifacts/evidence/round7/twouser-same-view.json"],
        "两个真实用户 + /project 共享库（serdes_rx；TEST_LIB 只在 calprobe 的 cds.lib 里）"),
    "gui_display_probe.py": entry(
        "gui", ["--work-dir", WORK_VBLOG, "--token", TOKEN_VBLOG], "X11 display + 真实 CIW"),
    # 2026-09-30 接线：三个此前"无人引用"的探针（`run_semi_probes.py` 漏登记）
    #  * 日志轮转（日志 spec §8.5 的"文件轮转/清空"行为，本机文件/子进程即可）
    #  * layout region/depth direct 复验（P-082/P-085 回归）
    #  * GDS 导出后同会话 SKILL 仍可用（P-075 回归；需 PDK 实例的库 GDSKILL/gds_probe）
    "log_rotation_lock_probe.py": entry(
        "transport", [], "本地文件/子进程：per-pid 日志轮转不受他人持锁影响（日志 spec §8.5）"),
    "layout_depth_region_direct_probe.py": entry(
        "layout", [], "业务面 8127 + vb-vblog（P-082/P-085 region 两点 + depth 下钻）"),
    "gds_then_skill_probe.py": entry(
        "layout", ["--token", TOKEN_PDK], "PDK 实例（calprobe）：GDS 导出后同会话 SKILL 仍可用（P-075）"),
    # py2.7 专项（本机编排、靶机执行）：真 py2.7 daemon 拒绝分支 + `_read_frame` 静默丢弃。
    # 我们承诺"远端侧 2.7+ / 3.6+"，此前两个 py27 探针**无人引用**（只跑过 py3 对照）。
    "py27_remote_runtime_probe.py": entry(
        "py27", ["--out", "test/artifacts/evidence/round9/py27-remote-runtime.json"],
        "wsl-gent 真 Python 2.7.6（XCELIUM 自带）+ python3；scp 上传探针/daemon_27 后在靶机执行"),
    # 路径边界攻击（P-051 回归）：目标目录含空格 / 父级是普通文件 / 相对路径 → 不得挂死或假成功
    "gds_publish_path_edges_probe.py": entry(
        "layout", ["--out", "test/artifacts/evidence/round9/gds-publish-path-edges.json"],
        "业务面 8127 + vb-vblog（layout.gds 远端发布路径边界，P-051 回归）"),
    # 2026-09-30 接线（本批）：三个"需要自带夹具"的回归探针
    #  * P-095：悬空 Overwrite History 目标 → run 不得挂死（探针自己 open_gui 造会话，收尾关闭）
    #  * P-096：死属主/活锁/自家锁 三态 → 结构化语义正确且实例不挂死
    #  * P-076：2 任务 spectre.run 三轮均正常收尾、无线程泄漏
    "maestro_p095_overwrite_wedge_probe.py": entry(
        "maestro", ["--out", "test/artifacts/evidence/round9/p095-overwrite-wedge.json"],
        "业务面 8127 + vb-vblog（maestro_tb/rc_probe；探针自带 GUI 会话夹具）"),
    "maestro_p096_write_lock_probe.py": entry(
        "maestro", [], "业务面 8127 + vb-vblog（自建 p096_lock_scratch 夹具；死锁/活锁/自家锁三态）"),
    "p076_fix_verify_probe.py": entry(
        "spectre", [], "业务面 8127 + wsl-gent（2 任务 spectre.run × 3 轮，P-076 回归）"),
    # 位置参数：`<mode> <lib> <cell> [view] [overwrite]`；`--token` 换实例
    # （SRX65/DI65 这些库在 PDK 实例的 cds.lib 里，vblog 实例看不到）
    "symbol_regen_handle_probe.py": entry("symbol", [], "PDK 实例"),
    "symbol_generate_hierarchy_handle_probe.py": entry("symbol", [], "PDK 实例"),
    "symbol_screenshot_probe.py": entry("symbol", [], "X11 display + 真实窗口"),
    "shared_cdf_pollution_probe.py": entry("schematic", [], "PDK 实例 + peer 用户"),
    "schematic_pin_ops_probe.py": entry("schematic", [], "PDK 实例"),
    "schematic_wire_style_probe.py": entry("schematic", [], "PDK 实例"),
    "maestro_env_probe.py": entry("maestro", [], "真 Virtuoso + ADE 库"),
    "maestro_export_include_results_probe.py": entry(
        "maestro", [], "业务面 8127 + rc_probe history（P-084 红灯钉）"),
    "maestro_save_false_disk_probe.py": entry(
        "maestro", [], "业务面 8127 + maestro_tb/rc_probe 磁盘 sdb（P-087 红灯钉）"),
    "maestro_delete_var_all_probe.py": entry(
        "maestro", [], "业务面 8127 + maestro_tb/rc_probe（P-088 红灯钉：delete_var scope=all）"),
    "maestro_open_waveform_result_probe.py": entry(
        "maestro", [], "业务面 8127 + rc_probe history（P-089 红灯钉：open_waveform_gui.result 被忽略）"),
    "maestro_session_conflict_probe.py": entry("maestro", [], "只读诊断（真 Virtuoso）"),
    "maestro_screenshot_probe.py": entry("maestro", [], "X11 display + 真实 ADE 窗口"),
    "calibre_env_probe.py": entry("calibre", ["--facts"], "calibre 环境（远程）"),
    "calibre_cdl_probe.py": entry("calibre", [], "PDK 实例 + auCdl"),
    "cdl_export_variants_probe.py": entry("calibre", [], "PDK 实例 + 多参数导出"),
    "calibre_package_http_probe.py": entry("calibre", ["--kind", "env"], "业务面 8127（默认 8127/vb-vblog）"),
    "calibre_flat_turbo_probe.py": entry(
        "calibre", [], "业务面 8127（P-093/P-094 回归：flat DRC 无 -turbo + 秒退快速 failed）"),
    "calibre_timeout_probe.py": entry(
        "calibre", [], "业务面 8127（P-098 回归：blocking 超时返回 timeout）"),
    "spectre_ac_pipeline_probe.py": entry("spectre", [], "PDK 实例"),
    "skill_syntax_matrix_tb.py": entry("skill", [], "业务面 8127"),
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
        "transport", ["--out", "{evidence_dir}/role-credential-isolation.json"],
        "两把真钥（见 test/reports/internal/环境Runbook-内部.md §3.1）", "test/semi/transport"),
}


def _run_one(name: str, spec: dict, *, dry: bool, log_dir: Path, evidence_dir: str) -> dict:
    base = PROBES_DIR if spec.get("path") is None else ROOT / str(spec["path"])
    script = base / name
    if not script.is_file():
        return {"probe": name, "status": "missing", "detail": str(script)}
    argv = [sys.executable, str(script),
            *[str(x).replace("{evidence_dir}", evidence_dir)
              for x in spec.get("argv", [])]]
    if dry:
        return {"probe": name, "status": "dry", "argv": argv[2:], "needs": spec.get("needs")}
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    started = time.monotonic()
    try:
        # 探针输出是 UTF-8（含中文/符号）；Windows 默认 locale 是 GBK，必须显式指定，
        # 否则读线程会抛 UnicodeDecodeError 把 runner 整个打断（2026-09-28 实测）。
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=spec.get("timeout", 900),
                             env={**os.environ, "PYTHONPATH": "src",
                                  "PYTHONIOENCODING": "utf-8"})
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

    out = Path(args.out)
    if not out.is_absolute():
        out = (ROOT / out).resolve()
    log_dir = out.parent / "semi-logs"
    evidence_dir = out.parent.as_posix()
    results = []
    for name, spec in selected.items():
        if not args.dry:
            print(f"[ .. ] {name}", flush=True)
        row = _run_one(name, spec, dry=args.dry, log_dir=log_dir,
                       evidence_dir=evidence_dir)
        results.append(row)
        if not args.dry:
            extra = (f" rc={row.get('rc')} {row.get('seconds')}s"
                     if row.get("rc") is not None else "")
            print(f"[{row['status']:>4}] {name}{extra}", flush=True)
    failed = [r["probe"] for r in results if r["status"] == "fail"]
    payload = {"group": args.group, "count": len(results), "failed": failed,
               "ok": not failed, "results": results}
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
