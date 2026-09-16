"""Six-step registration over the real HTTP API (artifact-producing TB).

Drives ``server.registration_server`` exactly as the registration page does:
apply -> validate -> probe -> deploy -> verify (+ step 6 durable write), then
reads back, updates and deletes the user.  Steps 3/4 go to a real SSH host
(``wsl-gent``); step 5's Skill smoke runs against a protocol-compatible fake
daemon on that host, so the whole flow is automatable without a CIW.

Run with::

    PYTHONPATH=src python test/tb/registration_http_six_step_tb.py \
        --work-dir test/tb/artifacts/reg-six --out test/tb/artifacts/reg-six/evidence.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import tempfile
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from server.registration_server import RegistrationServer  # noqa: E402
from transport.registry import load_registry  # noqa: E402
from transport.runtime_paths import registry_path, set_working_dir  # noqa: E402

try:
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


class ProbeFailure(AssertionError):
    pass


class _StopAfterDeploy(Exception):
    """Control-flow marker: remote 1-4 phase finished successfully."""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Http:
    """Minimal JSON client plus the raw evidence trail for the report."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.trail: list[dict] = []

    def call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                status = response.status
                body = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:  # 4xx/5xx still carry JSON
            status = error.code
            raw = error.read().decode("utf-8")
            try:
                body = json.loads(raw or "{}")
            except ValueError:
                body = {"raw": raw}
        self.trail.append({"method": method, "path": path, "status": status,
                           "request": payload, "response": body})
        return status, body


class LocalFakeDaemon:
    """In-process protocol-compatible daemon for local-mode registration."""

    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.token = token
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self.requests: list[dict] = []

    def _serve(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            try:
                raw = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                request = json.loads(raw.decode("utf-8"))
                self.requests.append({k: v for k, v in request.items() if k != "token"})
                if request.get("token") != self.token:
                    payload = {"error": "invalid token", "log": ""}
                    conn.sendall(b"\x15" + json.dumps(payload).encode() + b"\x1e")
                    continue
                payload = {"value": "2", "log": ""}
                conn.sendall(b"\x02" + json.dumps(payload).encode() + b"\x1e")
            except Exception:  # noqa: BLE001 - the TB reports failures elsewhere
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def start(self) -> None:
        # bind only when the daemon is supposed to be up: the probe in step 3
        # must observe the port as free
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(16)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._thread.join(timeout=5)


class FakeDaemon:
    """Protocol-compatible daemon on the target host (started via ssh)."""

    def __init__(self, host: str, port: int, token_prefix: str) -> None:
        self.host = host
        self.port = port
        self.token_prefix = token_prefix
        self._proc: subprocess.Popen | None = None
        self.tag = uuid.uuid4().hex[:8]
        self.remote_dir = f"/tmp/vb-six-{self.tag}"

    @property
    def token(self) -> str:
        return f"{self.token_prefix}-00"

    def _ssh(self, command: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["ssh", self.host, command], capture_output=True, text=True,
            timeout=timeout, **no_window(),
        )

    def start(self) -> None:
        """Run the fake daemon in the foreground of a kept-open ssh session.

        Backgrounding through ssh is unreliable here (the channel stays open),
        so the TB owns the ssh process and terminates it during cleanup.
        """
        self._ssh(f"mkdir -p {self.remote_dir}")
        source = ROOT / "test" / "tb" / "fake_daemon_host.py"
        copied = subprocess.run(
            ["scp", str(source), f"{self.host}:{self.remote_dir}/fake_daemon_host.py"],
            capture_output=True, text=True, timeout=120, **no_window(),
        )
        if copied.returncode != 0:
            raise ProbeFailure(f"scp of fake daemon failed: {copied.stderr.strip()}")
        remote_cmd = (
            f"cd {self.remote_dir} && exec python3 fake_daemon_host.py "
            f"--base-port {self.port} --count 1 --token-prefix {self.token_prefix}"
        )
        self._proc = subprocess.Popen(
            ["ssh", self.host, remote_cmd],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            **no_window(),
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            probe = self._ssh(f"ss -tln | grep -c ':{self.port} '", timeout=20)
            if probe.stdout.strip().endswith("1"):
                return
            time.sleep(0.5)
        self.stop()
        raise ProbeFailure(f"fake daemon did not listen on {self.port}")

    def stop(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
            self._proc = None
        # bracket-escaped pattern: matches the daemon, never this ssh command
        port_pattern = f"[{self.port}]"
        self._ssh(
            f"pkill -f 'fake_daemon_host.py --base-port {port_pattern}'", timeout=30
        )
        self._ssh(f"rm -rf {self.remote_dir}", timeout=30)


def request_payload(
    user: str, token: str, host: str, ssh_user: str, root: str, port: int,
    *, local: bool = False,
) -> dict:
    if local:
        return {
            "user": user,
            "token": token,
            "mode": "local",
            "root": {"default": root},
            "roles": {"daemon": {"daemon_port": port, "local_port": port}},
            "log_level": "off",
            "thread_pool_size": 8,
            "channel_budget": 8,
        }
    return {
        "user": user,
        "token": token,
        "mode": "remote",
        "ssh": {"default": {"host": host, "user": ssh_user}},
        "root": {"default": root},
        "roles": {
            "daemon": {
                "daemon_port": port,
                "local_port": free_port(),
                "root": root,
            },
        },
        "log_level": "off",
        "thread_pool_size": 8,
        "channel_budget": 8,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--user", default="vbsix")
    parser.add_argument("--daemon-port", type=int, default=0,
                        help="0 = auto-select (local mode only)")
    parser.add_argument("--root", default="")
    parser.add_argument(
        "--local-mode",
        action="store_true",
        help="run the whole six-step flow in local mode with an in-process daemon",
    )
    parser.add_argument(
        "--stop-after-deploy",
        action="store_true",
        help="remote 1-4 only: step 5 needs a CIW-started daemon (bridge never starts it)",
    )
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    if not args.out:
        args.out = str(work_dir / "evidence.json")
    set_working_dir(work_dir)
    registry = load_registry(registry_path())

    prefix = f"vbsix{uuid.uuid4().hex[:6]}"
    local_root_tmp: Path | None = None
    if args.local_mode:
        token = args.token or f"{prefix}-00"
        port = args.daemon_port or free_port()
        local_daemon = LocalFakeDaemon(port, token)
        daemon = None
        if not args.root:
            # deployed files are throw-away evidence: keep them out of the
            # artifact dir and remove them when the run finishes
            local_root_tmp = Path(tempfile.mkdtemp(prefix="vb-six-root-"))
        root = args.root or str(local_root_tmp)
    else:
        local_daemon = None
        daemon = FakeDaemon(args.host, args.daemon_port, prefix)
        token = args.token or daemon.token
        port = args.daemon_port
        root = args.root or f"/home/{args.ssh_user}/.virtuoso-bridge/{args.user}"

    http_port = free_port()
    def registry_snapshot() -> bytes | None:
        return registry_path().read_bytes() if registry_path().exists() else None

    def assert_no_registry_write(step: str) -> None:
        """前五步必须零落盘：registry.json 一个字节都不能变。"""
        if registry_snapshot() != registry_before:
            raise ProbeFailure(f"{step} touched registry.json (step 6 owns the only write)")

    server = RegistrationServer(("127.0.0.1", http_port), registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    http = Http(f"http://127.0.0.1:{http_port}")

    steps: list[dict] = []
    started = time.monotonic()
    # keep the TB re-runnable: remove a user left behind by a previous run
    if registry.get(args.user) is not None:
        status, body = http.call("DELETE", f"/api/user/{args.user}")
        steps.append({"action": "pre-cleanup", "status": status,
                      "removed": body.get("removed")})
        if status != 200:
            raise ProbeFailure(f"pre-cleanup failed: {body}")
    registry_before = registry_snapshot()
    ok = True
    try:
        # -- step 1: apply -------------------------------------------------
        status, body = http.call(
            "POST", "/api/register/apply",
            request_payload(args.user, token, args.host, args.ssh_user, root,
                            port, local=args.local_mode),
        )
        steps.append({"step": 1, "action": "apply", "status": status,
                      "stage": body.get("stage"), "step_field": body.get("step")})
        if status != 200 or body.get("stage") != "applied":
            raise ProbeFailure(f"step 1 failed: {body}")
        assert_no_registry_write("step 1")

        # -- step 2: local validation --------------------------------------
        status, body = http.call("POST", f"/api/register/{args.user}/validate")
        steps.append({"step": 2, "action": "validate", "status": status,
                      "stage": body.get("stage")})
        if status != 200 or body.get("stage") != "validated":
            raise ProbeFailure(f"step 2 failed: {body}")
        assert_no_registry_write("step 2")

        # -- step 3: probe --------------------------------------------------
        status, body = http.call("POST", f"/api/register/{args.user}/probe")
        steps.append({"step": 3, "action": "probe", "status": status,
                      "stage": body.get("stage"),
                      "daemon_python": (body.get("entry") or {}).get("roles", {})
                      .get("daemon", {}).get("python"),
                      "fingerprint": bool((body.get("entry") or {}).get("roles", {})
                                          .get("daemon", {}).get("expected_fingerprint"))})
        if status != 200 or body.get("stage") != "probed":
            raise ProbeFailure(f"step 3 failed: {body}")
        if not body.get("entry"):
            raise ProbeFailure("step 3 did not return the candidate entry")
        assert_no_registry_write("step 3")

        # -- step 4: deploy -------------------------------------------------
        status, body = http.call("POST", f"/api/register/{args.user}/deploy")
        steps.append({"step": 4, "action": "deploy", "status": status,
                      "stage": body.get("stage"), "setup_path": body.get("setup_path")})
        if status != 200 or body.get("stage") != "deployed":
            raise ProbeFailure(f"step 4 failed: {body}")
        setup_path = body.get("setup_path") or ""
        if not setup_path.endswith("virtuoso_setup.il"):
            raise ProbeFailure(f"step 4 returned no setup path: {setup_path!r}")
        # deploy must have put real files on the target, not just a path string
        if args.local_mode:
            if not Path(setup_path).is_file():
                raise ProbeFailure(f"step 4 did not write the setup file: {setup_path}")
        else:
            probe = subprocess.run(
                ["ssh", args.host, f"test -f {setup_path} && echo present"],
                capture_output=True, text=True, timeout=60, **no_window(),
            )
            if probe.returncode != 0 or "present" not in probe.stdout:
                raise ProbeFailure(
                    f"step 4 did not create {setup_path} on {args.host}: {probe.stderr.strip()}"
                )
        assert_no_registry_write("step 4")

        # -- step 5 + 6: connectivity then the single durable write ---------
        if args.stop_after_deploy:
            steps.append({
                "action": "stop-after-deploy",
                "note": "step 5 needs the CIW to load the deployed setup (daemon startup "
                        "belongs to the site topology, not to the bridge)",
            })
            raise _StopAfterDeploy()
        if local_daemon is not None:
            local_daemon.start()
        if daemon is not None:
            daemon.start()
        status, body = http.call("POST", f"/api/register/{args.user}/verify")
        steps.append({"step": 5, "action": "verify", "status": status,
                      "stage": body.get("stage"), "step_field": body.get("step"),
                      "report": body.get("report"), "errors": body.get("errors")})
        if status != 200 or body.get("stage") != "committed" or body.get("step") != 6:
            raise ProbeFailure(f"step 5/6 failed: {body}")
        report = body.get("report") or {}
        if not (report.get("command_ok") and report.get("skill_ok") and report.get("token_ok")):
            raise ProbeFailure(f"connectivity report incomplete: {report}")
        on_disk = json.loads(registry_path().read_text(encoding="utf-8"))
        if args.user not in on_disk:
            raise ProbeFailure("step 6 did not persist the user")
        steps.append({"step": 6, "action": "registry-write", "users": sorted(on_disk)})

        # -- read back / update / delete ------------------------------------
        status, body = http.call("GET", f"/api/user/{args.user}")
        steps.append({"action": "read-back", "status": status,
                      "token_matches": body.get("entry", {}).get("token") == token})
        if status != 200 or body.get("entry", {}).get("token") != token:
            raise ProbeFailure(f"read-back failed: {body}")

        status, body = http.call("GET", "/api/users")
        if status != 200 or args.user not in [u["user"] for u in body.get("users", [])]:
            raise ProbeFailure(f"user listing missed the new user: {body}")
        steps.append({"action": "list-users", "status": status,
                      "count": len(body.get("users", []))})

        status, current = http.call("GET", f"/api/user/{args.user}")
        entry = current.get("entry") or {}
        entry.setdefault("runtime", {})["thread_pool_size"] = 12
        # spec 多用户与注册 §5: ``mode`` is fixed at registration time and is
        # not part of the update whitelist, so a GET round-trip omits it.
        entry.pop("mode", None)
        status, body = http.call("POST", f"/api/user/{args.user}/update", entry)
        steps.append({"action": "update", "status": status,
                      "thread_pool_size": (body.get("entry", {}).get("runtime") or {})
                      .get("thread_pool_size")})
        if status != 200 or (body.get("entry", {}).get("runtime") or {}).get("thread_pool_size") != 12:
            raise ProbeFailure(f"update failed: {body}")

        status, body = http.call("POST", f"/api/user/{args.user}/update",
                                 {"mode": {"default": "remote"}})
        steps.append({"action": "update-rejects-mode", "status": status,
                      "detail": body.get("detail")})
        if status != 400 or "mode" not in json.dumps(body):
            raise ProbeFailure(f"mode must not be updatable: {body}")

        status, body = http.call("DELETE", f"/api/user/{args.user}")
        steps.append({"action": "delete", "status": status, "removed": body.get("removed")})
        if status != 200 or not body.get("removed"):
            raise ProbeFailure(f"delete failed: {body}")
        on_disk = json.loads(registry_path().read_text(encoding="utf-8"))
        if args.user in on_disk:
            raise ProbeFailure("delete left the user in the registry file")
        steps.append({"action": "delete-verify", "users": sorted(on_disk)})

        # -- negative: verify before deploy must fail, never write ----------
        bad_user = args.user + "bad"
        bad_port = free_port()
        status, body = http.call(
            "POST", "/api/register/apply",
            request_payload(bad_user, token + "-x", args.host, args.ssh_user, root,
                            bad_port, local=args.local_mode),
        )
        if status != 200 or body.get("stage") != "applied":
            raise ProbeFailure(f"negative-case apply did not reach 'applied': {body}")
        status, body = http.call("POST", f"/api/register/{bad_user}/verify")
        errors = " ".join(body.get("errors") or [])
        steps.append({"action": "verify-before-deploy", "status": status,
                      "stage": body.get("stage"), "errors": body.get("errors")})
        if body.get("stage") != "failed":
            raise ProbeFailure(f"out-of-order verify was accepted: {body}")
        if "order" not in errors.lower() and "deployed" not in errors.lower():
            raise ProbeFailure(
                f"failure does not describe the step-order violation: {body}"
            )
        assert_no_registry_write("out-of-order verify")
        on_disk = json.loads(registry_path().read_text(encoding="utf-8"))
        if bad_user in on_disk:
            raise ProbeFailure("failed registration still reached the registry")
    except _StopAfterDeploy:
        pass
    except Exception as exc:  # noqa: BLE001
        ok = False
        steps.append({"action": "error", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        try:
            if daemon is not None:
                daemon.stop()
            if local_daemon is not None:
                local_daemon.stop()
        except Exception:  # noqa: BLE001
            pass
        if local_root_tmp is not None:
            shutil.rmtree(local_root_tmp, ignore_errors=True)
        server.shutdown()
        server.server_close()

    evidence = {
        "ok": ok,
        "phase": "1-4 (remote)" if args.stop_after_deploy else "1-6",
        "user": args.user,
        "token": token,
        "host": args.host,
        "daemon_port": port,
        "http_port": http_port,
        "work_dir": str(work_dir),
        "steps": steps,
        "http_trail": http.trail,
        "elapsed_s": time.monotonic() - started,
    }
    text = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, "steps": steps}, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
