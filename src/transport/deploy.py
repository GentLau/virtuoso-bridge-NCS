"""Tool-like deploy helper: put bottom files in place for one user.

This module contains no routing logic.  Callers resolve host/account themselves
and pass an ``SSHRunner`` (or ``local=True`` for a local filesystem); both the
runtime ``RemoteClient`` and the standalone registration module reuse it.
"""

from __future__ import annotations

import importlib.resources
import logging
import os
import shlex
from pathlib import Path

from transport import remote_paths
from transport.setup import generate_setup_il
from transport.ssh import SSHRunner

logger = logging.getLogger(__name__)


def deploy_files(
    *,
    runner: SSHRunner | None,
    token: str,
    user: str,
    scratch_root: str,
    python_major: int,
    python_cmd: str,
    port: int,
    local: bool,
) -> str:
    """Deploy daemon/il/setup for one user and return the setup path."""
    ramic = remote_paths.ramic_dir(user, scratch_root)
    setup_dir = remote_paths.setup_dir(user, scratch_root)
    status = remote_paths.status_dir(user, scratch_root)

    daemon_variants = [
        ("ramic_bridge_daemon_3.py", remote_paths.daemon_path(user, 3, scratch_root)),
        ("ramic_bridge_daemon_27.py", remote_paths.daemon_path(user, 2, scratch_root)),
    ]
    il_src = importlib.resources.files("bridge.resources") / "ramic_bridge.il"
    selected_daemon = remote_paths.daemon_path(user, python_major, scratch_root)
    il_dst = remote_paths.il_path(user, scratch_root)
    setup_dst = remote_paths.setup_il_path(user, scratch_root)
    identity_dst = remote_paths.identity_path(user, scratch_root)

    setup = generate_setup_il(
        daemon=str(selected_daemon),
        il=str(il_dst),
        python_cmd=python_cmd,
        port=port,
        token=token,
        identity=str(identity_dst),
    )

    if local:
        for d in (ramic, setup_dir, status):
            Path(d).mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(d, 0o700)
            except OSError:
                pass
        for src_name, dst in daemon_variants:
            src = importlib.resources.files("bridge.resources") / src_name
            Path(dst).write_bytes(src.read_bytes())
        Path(il_dst).write_bytes(il_src.read_bytes())
        Path(setup_dst).write_text(setup, encoding="utf-8")
        return str(setup_dst)

    if runner is None:
        raise RuntimeError("remote deploy requires an SSHRunner")

    mkdir = (
        f"mkdir -p {shlex.quote(ramic)} {shlex.quote(setup_dir)} {shlex.quote(status)}"
        f" && chmod 700 {shlex.quote(ramic)} {shlex.quote(setup_dir)} {shlex.quote(status)}"
    )
    result = runner.run_command(mkdir)
    if result.returncode != 0:
        raise RuntimeError(f"deploy mkdir failed: {result.stderr.strip()}")

    for src_name, dst in daemon_variants:
        src = importlib.resources.files("bridge.resources") / src_name
        text = src.read_text(encoding="utf-8")
        result = runner.upload_text(text, str(dst))
        if result.returncode != 0:
            raise RuntimeError(f"deploy failed for {dst}: {result.stderr.strip()}")

    result = runner.upload_text(il_src.read_text(encoding="utf-8"), str(il_dst))
    if result.returncode != 0:
        raise RuntimeError(f"deploy failed for {il_dst}: {result.stderr.strip()}")

    result = runner.upload_text(setup, str(setup_dst))
    if result.returncode != 0:
        raise RuntimeError(f"deploy setup failed: {result.stderr.strip()}")
    return str(setup_dst)


__all__ = ["deploy_files"]
