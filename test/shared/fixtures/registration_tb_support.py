"""Shared client-side helpers for the registration live TBs.

These are test-fixture utilities only; they contain no product logic.  The
registration TBs use their own in-process ``RegistrationServer`` and work-dir,
so no 8127/8131 business face is required.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

try:  # Windows: keep ssh/scp console windows hidden
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover - POSIX
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


class ProbeFailure(AssertionError):
    """A TB assertion with enough context for the evidence JSON."""


class Results:
    """Small check ledger used by the registration TBs."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, **detail) -> bool:
        self.items.append({"name": name, "ok": bool(ok), **_redact(detail)})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}"
              + (f"  {detail}" if detail else ""))
        return bool(ok)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.items if item["ok"])


def _redact(value):
    """Never persist registration/session credentials in evidence."""
    if isinstance(value, dict):
        return {
            key: ("***" if key in ("token", "enhanced_token") else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


redact = _redact


class Http:
    """Minimal JSON client with a redacted evidence trail."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.trail: list[dict] = []

    def call(self, method: str, path: str, payload: dict | None = None,
             timeout: float = 180.0) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                body = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read().decode("utf-8")
            try:
                body = json.loads(raw or "{}")
            except ValueError:
                body = {"raw": raw}
        self.trail.append({"method": method, "path": path,
                           "request": _redact(payload), "status": status,
                           "response": _redact(body)})
        return status, body


def ssh(host: str, command: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
        capture_output=True, text=True, timeout=timeout, **no_window(),
    )


def remote_home(host: str) -> str:
    result = ssh(host, 'printf "%s" "$HOME"', timeout=30)
    home = (result.stdout or "").strip()
    if result.returncode != 0 or not home:
        raise ProbeFailure(f"cannot resolve remote HOME on {host}: {result.stderr.strip()}")
    return home


def remote_free_port(host: str, start: int = 65300, tries: int = 80) -> int:
    """Ask remote python3 for an ephemeral port; fall back to an ss scan."""
    command = (
        "python3 -c \"import socket; s=socket.socket(); "
        "s.bind(('127.0.0.1',0)); p=s.getsockname()[1]; s.close(); print(p)\""
    )
    result = ssh(host, command, timeout=30)
    out = (result.stdout or "").strip()
    if result.returncode == 0 and out.isdigit():
        return int(out)
    for port in range(start, start + tries):
        probe = ssh(host, f"ss -ltn | grep -c ':{port} '", timeout=20)
        if probe.returncode != 0 or (probe.stdout or "").strip() == "0":
            return port
    raise ProbeFailure(f"no free remote port found on {host}")


def local_free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_local_port(port: int, timeout: float = 20.0, host: str = "127.0.0.1") -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def wait_remote_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = ssh(host, f"ss -ltn | grep -c ':{port} '", timeout=20)
        if (probe.stdout or "").strip() == "1":
            return True
        time.sleep(0.4)
    return False


def remove_local_tree(path: Path) -> None:
    """Best-effort removal of a test-owned local tree (non-production helper)."""
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_dir():
                child.rmdir()
            else:
                child.unlink()
        except OSError:
            pass
    try:
        path.rmdir()
    except OSError:
        pass
