"""Registration probes (step 3): read-only checks against the target.

Remote mode probes through SSH; local mode runs the equivalent checks on this
machine.  Every probe reports a specific reason on failure so the six-step
flow can abort without writing anything to the registry.
"""

from __future__ import annotations

import getpass
import os
import shlex
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from common.ssh import SSHRunner
from common.validation import validate_display


#: 在目标解释器内直接打印三段版本号（py2/py3 同一条命令，不依赖 --version 文案）。
_PYTHON_VERSION_CODE = 'import sys; print("%d.%d.%d" % sys.version_info[:3])'


def _parse_python_version(text: str | None) -> tuple[int, int, int] | None:
    """Extract the last ``X.Y[.Z]`` token from probe output (None if absent)."""
    if not text:
        return None
    for token in reversed(text.split()):
        numbers = token.split(".")
        if len(numbers) not in (2, 3):
            continue
        try:
            major, minor = int(numbers[0]), int(numbers[1])
            micro = int(numbers[2]) if len(numbers) == 3 else 0
        except ValueError:
            continue
        return (major, minor, micro)
    return None


def python_version_supported(version: tuple[int, int, int] | None) -> bool:
    """r17: role machines accept Python 2.7+ or 3.6.8+."""
    if version is None:
        return False
    major, minor, micro = version
    return (major == 2 and minor >= 7) or (
        major == 3 and (minor, micro) >= (6, 8)
    )


def _no_window_kwargs() -> dict:
    """Hide the Windows console for external ssh/scp probes (CREATE_NO_WINDOW)."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _ssh_config_hostname(host: str) -> str | None:
    """Resolve a host alias through the local ssh config (``ssh -G``)."""
    try:
        out = subprocess.run(
            ["ssh", "-G", host], capture_output=True, text=True, timeout=10,
        **_no_window_kwargs()
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        if line.startswith("hostname "):
            return line.split(None, 1)[1].strip() or None
    return None


def ssh_port_is_22(host: str) -> bool:
    """Resolve an SSH alias and enforce the spec's fixed port-22 rule."""
    try:
        out = subprocess.run(
            ["ssh", "-G", host], capture_output=True, text=True, timeout=10,
            **_no_window_kwargs()
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in out.splitlines():
        if line.startswith("port "):
            try:
                return int(line.split(None, 1)[1].strip()) == 22
            except (IndexError, ValueError):
                return False
    return True


def _fingerprint_from_key_lines(lines: list[str]) -> str | None:
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", prefix="vb_keys_", suffix=".tmp", delete=False
        ) as f:
            tmp_path = Path(f.name)
            f.write("\n".join(lines) + "\n")
        fp = subprocess.run(
            ["ssh-keygen", "-lf", str(tmp_path)], capture_output=True, text=True,
            timeout=10, **_no_window_kwargs(),
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


def scan_host_key_fingerprint(host: str, port: int = 22) -> str | None:
    """Fetch a key directly for the explicit-fingerprint first-trust path."""
    try:
        found = subprocess.run(
            ["ssh-keyscan", "-p", str(port), host],
            capture_output=True, text=True, timeout=10,
            **_no_window_kwargs(),
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    key_lines = [
        line for line in found.splitlines()
        if "ssh-" in line and not line.startswith("#")
    ]
    return _fingerprint_from_key_lines(key_lines) if key_lines else None


def host_key_fingerprint(host: str, port: int = 22) -> str | None:
    """Fingerprint for the target host from ``known_hosts`` only.

    No TOFU: a fingerprint may only come from an already recorded and
    matching known_hosts entry.  Missing entries make registration fail and
    ask the user to establish trust out-of-band first.
    """
    candidates = [host]
    resolved = _ssh_config_hostname(host)
    if resolved and resolved != host:
        candidates.append(resolved)

    for candidate in candidates:
        try:
            found = subprocess.run(
                ["ssh-keygen", "-F", candidate], capture_output=True, text=True,
                timeout=10, **_no_window_kwargs(),
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
    return None

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


def _display_validate_script(display: str) -> str:
    return (
        "d=" + shlex.quote(display) + "; "
        "if command -v xdpyinfo >/dev/null 2>&1; then "
        "DISPLAY=\"$d\" XAUTHORITY=\"${XAUTHORITY:-$HOME/.Xauthority}\" "
        "xdpyinfo >/dev/null 2>&1; "
        "else "
        "DISPLAY=\"$d\" XAUTHORITY=\"${XAUTHORITY:-$HOME/.Xauthority}\" "
        "xwininfo -root >/dev/null 2>&1; "
        "fi"
    )


_DISPLAY_DETECT_SCRIPT = (
    "pids=$(pgrep -u \"$(id -u)\" -x virtuoso 2>/dev/null || true); "
    "count=$(printf '%s\\n' \"$pids\" | sed '/^$/d' | wc -l); "
    "[ \"$count\" -eq 1 ] || exit 3; "
    "pid=$(printf '%s\\n' \"$pids\" | sed -n '1p'); "
    "tr '\\0' '\\n' < \"/proc/$pid/environ\" 2>/dev/null | "
    "sed -n 's/^DISPLAY=//p' | head -1"
)


def validate_remote_display(
    runner: SSHRunner, display: str, timeout: float = 15
) -> bool:
    """Return whether an explicit GUI display is reachable on a remote host."""
    result = runner.run_command(
        _display_validate_script(display), timeout=timeout
    )
    return result.returncode == 0


def detect_remote_display(runner: SSHRunner, timeout: float = 15) -> str | None:
    """Detect DISPLAY only when exactly one Virtuoso process exists."""
    result = runner.run_command(_DISPLAY_DETECT_SCRIPT, timeout=timeout)
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in (result.stdout or "").splitlines()]
    if not lines or not lines[-1]:
        return None
    try:
        return validate_display(lines[-1])
    except ValueError:
        return None


def validate_local_display(display: str, timeout: float = 15) -> bool:
    """Local equivalent of :func:`validate_remote_display`."""
    try:
        result = subprocess.run(
            ["sh", "-c", _display_validate_script(display)],
            capture_output=True,
            text=True,
            timeout=timeout,
            **_no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def detect_local_display(timeout: float = 15) -> str | None:
    """Local equivalent of :func:`detect_remote_display`."""
    try:
        result = subprocess.run(
            ["sh", "-c", _DISPLAY_DETECT_SCRIPT],
            capture_output=True,
            text=True,
            timeout=timeout,
            **_no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in (result.stdout or "").splitlines()]
    if not lines or not lines[-1]:
        return None
    try:
        return validate_display(lines[-1])
    except ValueError:
        return None


def detect_remote_spectre(runner: SSHRunner) -> str | None:
    """Auto-detect spectre on the command host (same strategy as the old CLI)."""
    r = runner.run_command(
        "command -v spectre 2>/dev/null || which spectre 2>/dev/null || true",
        timeout=15,
    )
    out = (r.stdout or "").strip().splitlines()
    return out[-1].strip() or None if out else None


def detect_local_spectre() -> str | None:
    import shutil
    return shutil.which("spectre")


def remote_python_version(
    runner: SSHRunner, python_cmd: str
) -> tuple[int, int, int] | None:
    """Return the exact version of an explicitly supplied remote interpreter."""
    quoted = shlex.quote(python_cmd)
    r = runner.run_command(
        f"{quoted} -c '{_PYTHON_VERSION_CODE}'", timeout=10
    )
    if r.returncode != 0:
        return None
    lines = (r.stdout or "").strip().splitlines()
    return _parse_python_version(lines[-1] if lines else None)


def local_python_version(python_cmd: str) -> tuple[int, int, int] | None:
    """Return the exact version of an explicitly supplied local interpreter."""
    try:
        r = subprocess.run(
            [python_cmd, "-c", _PYTHON_VERSION_CODE],
            capture_output=True, text=True, timeout=10,
            **_no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    lines = (r.stdout or "").strip().splitlines()
    return _parse_python_version(lines[-1] if lines else None)


def detect_remote_python(runner: SSHRunner) -> tuple[str, int] | None:
    """Find a *supported* remote interpreter and pin its absolute path.

    Prefers the Cadence-bundled interpreters under ``$CDSHOME`` (which are
    usually absent from PATH), then falls back to PATH names.  The probe runs
    as one remote command so registration stays a single SSH round trip.
    r17: role machines require Python 2.7+ or 3.6.8+, so interpreters that
    exist but fall outside that window are skipped, never deployed to.
    Returns ``None`` when no supported interpreter is found.
    """
    script = (
        "for p in "
        '"$CDSHOME/tools.lnx86/python/64bit/bin/python3" '
        '"$CDSHOME/tools.lnx86/python3.6/bin/python3.6" '
        '"$CDSHOME/tools.lnx86/python2.7/bin/python2.7" '
        "python3 python python2.7 python2; do "
        'if [ -x "$p" ] || command -v "$p" >/dev/null 2>&1; then '
        f"v=$(\"$p\" -c '{_PYTHON_VERSION_CODE}' 2>/dev/null) || v=; "
        '[ -n "$v" ] && echo "CMD:$p $v"; '
        "fi; done"
    )
    r = runner.run_command(script, timeout=20)
    for line in (r.stdout or "").strip().splitlines():
        if not line.startswith("CMD:"):
            continue
        parts = line[4:].strip().split()
        if not parts:
            continue
        cmd = parts[0]
        version = _parse_python_version(" ".join(parts[1:]))
        if cmd and python_version_supported(version):
            return cmd, version[0]
    # Fallback: individual PATH probes for hosts without a Bourne-style shell.
    for cmd in ("python3", "python", "python2.7", "python2"):
        version = remote_python_version(runner, cmd)
        if version and python_version_supported(version):
            return cmd, version[0]
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


def allocate_local_port(
    start: int = 65081,
    tries: int = 50,
    reserved: set[int] | None = None,
) -> int | None:
    """Find a free local loopback port (remote-mode tunnel endpoint).

    ``reserved`` are local tunnel ports already assigned to other registry
    users.  They must never be handed out again, even if nothing is listening
    right now (the tunnel is created lazily on first use, so OS-freeness alone
    is not enough).
    """
    taken = reserved or set()
    for port in range(start, start + tries):
        if port in taken:
            continue
        if local_port_free(port):
            return port
    return None


# -- local-mode equivalents --------------------------------------------------

def local_hostname() -> str:
    return socket.gethostname()


def local_user() -> str:
    return getpass.getuser()


def local_executable_exists(path: str) -> bool:
    """Validate a user-provided local executable (bare name or absolute path)."""
    if not path:
        return False
    import shutil as _shutil
    import os as _os
    resolved = _shutil.which(path) if ("/" not in path and "\\" not in path) else path
    if not resolved:
        return False
    return _os.path.isfile(resolved) and _os.access(resolved, _os.X_OK)


def local_python() -> tuple[str, int]:
    return sys.executable, 2 if sys.version_info.major == 2 else 3


def local_port_free(port: int) -> bool:
    # Two checks are needed.  (1) bind: a socket already owns the port (or an
    # exclusive listener blocks it).  (2) connect: on Windows a wildcard
    # bind() does NOT collide with a specific-address listener such as an
    # existing ``ssh -L 127.0.0.1:port`` tunnel, so bind alone can report
    # "free" while something is already accepting on the loopback port.
    probe = socket.socket()
    try:
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    finally:
        probe.close()
    check = socket.socket()
    check.settimeout(0.2)
    try:
        return check.connect_ex(("127.0.0.1", port)) != 0
    finally:
        check.close()


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
    "local_python_version",
    "python_version_supported",
    "remote_python_version",
    "scan_host_key_fingerprint",
    "ssh_port_is_22",
    "allocate_local_port",
    "allocate_remote_port",
    "detect_local_spectre",
    "detect_local_display",
    "detect_remote_display",
    "detect_remote_python",
    "detect_remote_spectre",
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
    "validate_local_display",
    "validate_remote_display",
]
