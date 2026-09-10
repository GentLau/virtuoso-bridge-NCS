"""Registration probes (step 3): read-only checks against the target.

Remote mode probes through SSH; local mode runs the equivalent checks on this
machine.  Every probe reports a specific reason on failure so the six-step
flow can abort without writing anything to the registry.
"""

from __future__ import annotations

import getpass
import shlex
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from transport.ssh import SSHRunner


def _ssh_config_hostname(host: str) -> str | None:
    """Resolve a host alias through the local ssh config (``ssh -G``)."""
    try:
        out = subprocess.run(
            ["ssh", "-G", host], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        if line.startswith("hostname "):
            return line.split(None, 1)[1].strip() or None
    return None


def _fingerprint_from_key_lines(lines: list[str]) -> str | None:
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", prefix="vb_keys_", suffix=".tmp", delete=False
        ) as f:
            tmp_path = Path(f.name)
            f.write("\n".join(lines) + "\n")
        fp = subprocess.run(
            ["ssh-keygen", "-lf", str(tmp_path)], capture_output=True, text=True, timeout=10
        )
        return fp.stdout.strip().split()[1] if fp.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def host_key_fingerprint(host: str, port: int = 22) -> str | None:
    """Fingerprint for the target host, preferring recorded ``known_hosts``.

    SSH aliases (e.g. ``wsl-gent``) may only exist in ``~/.ssh/config``; try
    the alias, then its resolved hostname, in known_hosts before falling back
    to ``ssh-keyscan``.
    """
    candidates = [host]
    resolved = _ssh_config_hostname(host)
    if resolved and resolved != host:
        candidates.append(resolved)

    for candidate in candidates:
        try:
            found = subprocess.run(
                ["ssh-keygen", "-F", candidate], capture_output=True, text=True, timeout=10
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            found = ""
        key_lines = [
            ln for ln in found.splitlines()
            if "ssh-" in ln and not ln.startswith("#")
        ]
        if key_lines:
            fp = _fingerprint_from_key_lines(key_lines)
            if fp:
                return fp

    for candidate in candidates:
        try:
            scan = subprocess.run(
                ["ssh-keyscan", "-t", "ed25519,rsa", "-p", str(port), candidate],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            scan = ""
        key_lines = [
            ln for ln in scan.splitlines()
            if "ssh-" in ln and not ln.startswith("#")
        ]
        if key_lines:
            fp = _fingerprint_from_key_lines(key_lines)
            if fp:
                return fp
    return None


# -- remote probes -----------------------------------------------------------

def remote_hostname(runner: SSHRunner) -> str:
    """Remote hostname, preferring the fully-qualified name."""
    r = runner.run_command("hostname -f 2>/dev/null || hostname", timeout=10)
    return r.stdout.strip() if r.returncode == 0 else ""


def remote_user(runner: SSHRunner) -> str:
    r = runner.run_command("whoami", timeout=10)
    return r.stdout.strip() if r.returncode == 0 else ""


def remote_user_exists(runner: SSHRunner, username: str) -> bool:
    """Verify the daemon account exists on the target host."""
    r = runner.run_command(f"id {shlex.quote(username)}", timeout=10)
    return r.returncode == 0


def remote_path_writable(runner: SSHRunner, path: str) -> bool:
    """Ensure the deploy root exists and is writable on the target."""
    r = runner.run_command(
        f"mkdir -p {shlex.quote(path)} && test -w {shlex.quote(path)}", timeout=15
    )
    return r.returncode == 0


def remote_executable_exists(runner: SSHRunner, path: str) -> bool:
    """Validate an explicitly supplied remote tool path (daemon-independent)."""
    r = runner.run_command(
        f"test -x {shlex.quote(path)}", timeout=15
    )
    return r.returncode == 0


def detect_remote_python(runner: SSHRunner) -> tuple[str, int] | None:
    """Find a usable remote interpreter and pin its absolute path.

    Prefers the Cadence-bundled interpreters under ``$CDSHOME`` (which are
    usually absent from PATH), then falls back to PATH names.  The probe runs
    as one remote command so registration stays a single SSH round trip.
    Returns ``None`` when no interpreter is found.
    """
    script = (
        "for p in "
        '"$CDSHOME/tools.lnx86/python/64bit/bin/python3" '
        '"$CDSHOME/tools.lnx86/python3.6/bin/python3.6" '
        '"$CDSHOME/tools.lnx86/python2.7/bin/python2.7" '
        "python3 python python2.7 python2; do "
        'if [ -x "$p" ] || command -v "$p" >/dev/null 2>&1; then '
        'v=$("$p" --version 2>&1) && { echo "CMD:$p $v"; break; } || true; '
        "fi; done"
    )
    r = runner.run_command(script, timeout=20)
    last = (r.stdout or "").strip().splitlines()
    line = last[-1] if last else ""
    if line.startswith("CMD:") and "Python" in line:
        cmd = line[4:].strip().split()[0]
        major = 2 if "Python 2" in line else 3
        if cmd:
            return cmd, major
    # Fallback: individual PATH probes for hosts without a Bourne-style shell.
    for cmd in ("python3", "python", "python2.7", "python2"):
        rr = runner.run_command(f"{shlex.quote(cmd)} --version 2>&1", timeout=10)
        if rr.returncode == 0 and "Python" in rr.stdout + rr.stderr:
            major = 2 if "Python 2" in (rr.stdout + rr.stderr) else 3
            return cmd, major
    return None


def port_free_on_remote(runner: SSHRunner, port: int, python_cmd: str) -> bool:
    prog = (
        "import socket\n"
        "s = socket.socket()\n"
        "try:\n"
        "    s.bind(('0.0.0.0', %d))\n"
        "    s.close()\n"
        "    raise SystemExit(0)\n"
        "except OSError:\n"
        "    raise SystemExit(1)\n" % port
    )
    cmd = "%s - <<'PY'\n%sPY\n" % (python_cmd, prog)
    r = runner.run_command(cmd, timeout=10)
    return r.returncode == 0


def allocate_remote_port(
    runner: SSHRunner,
    python_cmd: str,
    start: int = 65081,
    tries: int = 50,
    reserved: set[int] | None = None,
) -> int | None:
    """Find the first free port in one remote Python probe (one SSH trip).

    ``reserved`` ports (already pinned in the registry) are never returned.
    """
    reserved = reserved or set()
    prog = (
        "import socket\n"
        "start = %d\n"
        "reserved = %r\n"
        "for port in range(start, start + %d):\n"
        "    if port in reserved:\n"
        "        continue\n"
        "    s = socket.socket()\n"
        "    try:\n"
        "        s.bind(('0.0.0.0', port))\n"
        "        s.close()\n"
        "        print(port)\n"
        "        raise SystemExit(0)\n"
        "    except OSError:\n"
        "        s.close()\n"
        "raise SystemExit(1)\n" % (start, sorted(reserved), tries)
    )
    cmd = "%s - <<'PY'\n%sPY\n" % (python_cmd, prog)
    r = runner.run_command(cmd, timeout=20)
    out = r.stdout.strip()
    if r.returncode == 0 and out.isdigit():
        return int(out)
    # Fallback: single-port checks for hosts without a Bourne-style shell.
    for port in range(start, start + tries):
        if port in reserved:
            continue
        if port_free_on_remote(runner, port, python_cmd):
            return port
    return None


def allocate_local_port(start: int = 65081, tries: int = 50) -> int | None:
    """Find a free local loopback port (remote-mode tunnel endpoint)."""
    for port in range(start, start + tries):
        if local_port_free(port):
            return port
    return None


# -- local-mode equivalents --------------------------------------------------

def local_hostname() -> str:
    return socket.gethostname()


def local_user() -> str:
    return getpass.getuser()


def local_python() -> tuple[str, int]:
    return sys.executable, 2 if sys.version_info.major == 2 else 3


def local_port_free(port: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def local_path_writable(path: str | Path) -> bool:
    try:
        target = Path(path).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".vb_probe"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


__all__ = [
    "allocate_local_port",
    "allocate_remote_port",
    "detect_remote_python",
    "remote_executable_exists",
    "host_key_fingerprint",
    "local_hostname",
    "local_path_writable",
    "local_port_free",
    "local_python",
    "local_user",
    "port_free_on_remote",
    "remote_hostname",
    "remote_path_writable",
    "remote_user",
    "remote_user_exists",
]
