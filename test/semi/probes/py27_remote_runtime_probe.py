# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 17:15
# 依赖: wsl-gent 上的真 Python 2.7（Cadence XCELIUM 自带）+ SSH 免密
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`ssh wsl-gent` + `<py27> -V` 必须报 Python 2.7 + `python3` 可用；
# ② 构建：在靶机上建专属临时根 `~/.virtuoso-bridge/py27-probe-<stamp>/`，
#    上传两个探针与 `ramic_bridge_daemon_27.py`（按 `<root>/src/bridge/resources/` 布局）；
# ③ 最终检查：确认上传文件就位、解释器可执行、目标端口空闲（探针自己会报）；
# ④ 执行：远端分别用 **python3** 跑 `py27_daemon_probe.py`（驱动真 py2.7 daemon）、
#    用 **python2.7 本身**跑 `py27_handler_probe.py`（_read_frame 异常分支）；
# ⑤ 读回比对：两个 JSON 的判据字段（daemon: passed==total；handler: ok=true 且无 NACK 帧）；
# ⑥ 收尾：`rm -rf` 远端临时根，证据 JSON 拉回本地与 `--out` 同目录。
"""把 py2.7 的两个专项探针接到半真机批次里（此前"无人引用"）。

覆盖面（我们承诺"远端侧支持 Python 2.7+ / 3.6+"，但此前只测过 py3 语义的对照）：
* **真 py2.7 解释器**下启动 `ramic_bridge_daemon_27.py` 并覆盖 token / log_level /
  log_max_bytes 拒绝分支与超时看门狗；
* **真 py2.7** 下判定 `_read_frame` 抛 ValueError 的分支：必须**静默丢弃**，不得回 NACK
  （P-039 口径；此前的 py3 猴补丁结论不可信）。

用法::

    PYTHONPATH=src python test/semi/probes/py27_remote_runtime_probe.py \
        --out test/artifacts/evidence/round9/py27-remote-runtime.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PY27 = "/opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/python2.7/bin/python2.7"
PROBES = ROOT / "test" / "semi" / "probes"
DAEMON27 = ROOT / "src" / "bridge" / "resources" / "ramic_bridge_daemon_27.py"
STAMP = time.strftime("%m%d%H%M%S")


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def _ssh(host: str, script: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return _run(["ssh", "-o", "BatchMode=yes", host, script], timeout=timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--py27", default=PY27)
    parser.add_argument("--port", type=int, default=6599)
    parser.add_argument("--out", default=str(ROOT / "test" / "artifacts" / "evidence"
                                             / "round9" / "py27-remote-runtime.json"))
    args = parser.parse_args(argv)

    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    # `scp` 走 SFTP 时**不展开** `$HOME` → 先取远端家目录的绝对路径。
    remote_home = "".join((_ssh(args.host, "echo $HOME", timeout=60).stdout or "").split()) \
        or "/home/Gent"
    remote_root = f"{remote_home}/.virtuoso-bridge/py27-probe-{STAMP}"
    evidence: dict = {"host": args.host, "py27": args.py27, "remote_root": remote_root,
                      "cases": {}}
    results: list[tuple[str, str]] = []

    def run(name: str, func):
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        print(f"PASS    {name}", flush=True)
        return value

    def case_env() -> None:
        version = _ssh(args.host, f"'{args.py27}' -V 2>&1", timeout=60)
        text = (version.stdout or "") + (version.stderr or "")
        assert "Python 2.7" in text, f"靶机没有可用的真 py2.7: {text[:120]!r}"
        py3 = _ssh(args.host, "python3 -V 2>&1", timeout=60)
        assert "Python 3" in ((py3.stdout or "") + (py3.stderr or "")), "靶机缺 python3"
        evidence["cases"]["env"] = {"py27": text.strip()}

    def case_upload() -> None:
        mk = _ssh(args.host, f"mkdir -p {remote_root}/probes {remote_root}/src/bridge/resources "
                            f"{remote_root}/evidence && echo READY", timeout=60)
        assert "READY" in (mk.stdout or ""), f"建远端目录失败: {mk.stderr[:120]}"
        for local in (PROBES / "py27_daemon_probe.py", PROBES / "py27_handler_probe.py"):
            copied = _run(["scp", "-q", str(local),
                           f"{args.host}:{remote_root}/probes/{local.name}"], timeout=180)
            assert copied.returncode == 0, f"上传 {local.name} 失败: {copied.stderr[:120]}"
        copied = _run(["scp", "-q", str(DAEMON27),
                       f"{args.host}:{remote_root}/src/bridge/resources/"], timeout=180)
        assert copied.returncode == 0, f"上传 daemon_27 失败: {copied.stderr[:120]}"
        listing = _ssh(args.host, f"ls {remote_root}/probes {remote_root}/src/bridge/resources",
                       timeout=60)
        assert "py27_daemon_probe.py" in listing.stdout and "py27_handler_probe.py" in listing.stdout, \
            f"远端文件不齐: {listing.stdout[:200]}"
        evidence["cases"]["upload"] = {"listing": listing.stdout.split()}

    def case_daemon_probe() -> None:
        cmd = (f"cd {remote_root} && python3 probes/py27_daemon_probe.py "
               f"--py27 '{args.py27}' --daemon src/bridge/resources/ramic_bridge_daemon_27.py "
               f"--port {args.port} --token py27-probe "
               f"--out {remote_root}/evidence/py27-daemon.json")
        proc = _ssh(args.host, cmd, timeout=600)
        evidence["cases"]["daemon_probe_rc"] = proc.returncode
        assert proc.returncode == 0, \
            f"py27 daemon 探针失败(rc={proc.returncode}): {(proc.stdout or proc.stderr)[-300:]}"
        _run(["scp", "-q", f"{args.host}:{remote_root}/evidence/py27-daemon.json",
              str(out_dir / "py27-daemon-probe.json")], timeout=120)
        doc = json.loads((out_dir / "py27-daemon-probe.json").read_text(encoding="utf-8"))
        passed, total = int(doc.get("passed") or 0), int(doc.get("total") or 0)
        assert total > 0 and passed == total, f"daemon 探针判据未全过: {passed}/{total} {doc}"
        evidence["cases"]["daemon_probe"] = {"passed": passed, "total": total,
                                             "cases": [c.get("case") for c in doc.get("cases") or []]}

    def case_handler_probe() -> None:
        cmd = (f"cd {remote_root} && '{args.py27}' probes/py27_handler_probe.py "
               f"--src src --out {remote_root}/evidence/py27-handler.json")
        proc = _ssh(args.host, cmd, timeout=600)
        evidence["cases"]["handler_probe_rc"] = proc.returncode
        assert proc.returncode == 0, \
            f"py27 handler 探针失败(rc={proc.returncode}): {(proc.stdout or proc.stderr)[-300:]}"
        _run(["scp", "-q", f"{args.host}:{remote_root}/evidence/py27-handler.json",
              str(out_dir / "py27-handler-probe.json")], timeout=120)
        doc = json.loads((out_dir / "py27-handler-probe.json").read_text(encoding="utf-8"))
        assert doc.get("ok") is True and not doc.get("nack_frames"), \
            f"handler 探针判据未过（值级）: {doc}"
        evidence["cases"]["handler_probe"] = {"verdict": doc.get("verdict"),
                                              "nack_frames": doc.get("nack_frames")}

    run("PY27-ENV 靶机真 py2.7 + python3", case_env)
    run("PY27-BUILD 上传探针与 daemon_27", case_upload)
    run("PY27-DAEMON 真 py2.7 daemon 拒绝分支全过", case_daemon_probe)
    run("PY27-HANDLER 真 py2.7 _read_frame 静默丢弃（无 NACK）", case_handler_probe)

    _ssh(args.host, f"rm -rf {remote_root}", timeout=120)
    failures = [name for name, status in results if status != "PASS"]
    evidence["results"] = [{"case": name, "status": status} for name, status in results]
    Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(f"evidence: {args.out}")
    print(f"{len(results) - len(failures)}/{len(results)} 通过"
          + (f"；失败 {failures}" if failures else ""))
    return 0 if not failures and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
