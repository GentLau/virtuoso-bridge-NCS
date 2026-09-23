"""End-to-end acceptance tests for basic / demo / gui / netlist.import.

Run with ``--transport direct`` or ``--transport http``.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "log-vblog"
SCRATCH = WORK_DIR / "infra_e2e"
SCRATCH.mkdir(parents=True, exist_ok=True)


def _remote_run_dir(case: str) -> str:
    """Resolve a per-run directory from the registry's file role root."""
    registry = json.loads((WORK_DIR / "registry.json").read_text(encoding="utf-8"))
    entry = next(
        item for item in registry.values()
        if isinstance(item, dict) and item.get("token") == TOKEN
    )
    role = (entry.get("roles") or {}).get("file") or {}
    root = role.get("root") or (entry.get("root") or {}).get("default")
    if not root:
        raise AssertionError("file role root is not configured")
    return posixpath.join(
        str(root).rstrip("/"), "tmp", "tb", f"infra-{case}-{uuid.uuid4().hex[:8]}"
    )


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


class DirectTransport:
    def __init__(self) -> None:
        from common import config as config_base
        from common.paths import config_path, init_work_dir
        from server import dispatch
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(WORK_DIR))
        config_base.init_config(config_path())
        register_packages()
        self.dispatch = dispatch
        self.middle = BusinessServer()

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, body = self.dispatch.dispatch(self.middle, payload)
        if status not in (200, 400):
            raise AssertionError(f"dispatch status {status}: {body}")
        return body


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    return response["data"]


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _case_basic(transport) -> None:
    skill = _op(transport, "basic.skill.execute", skill_code="1+1")
    _check("2" in (skill.get("result", {}).get("output") or ""), f"skill: {skill}")

    command = _op(transport, "basic.command.run", cmd="echo bridge-ok")
    command_result = command.get("result") or []
    _check(command_result[0] == 0 and "bridge-ok" in command_result[1],
           f"command: {command}")

    gui = _op(transport, "basic.gui.run", cmd="echo gui-ok")
    _check((gui.get("result") or [1])[0] == 0, f"gui: {gui}")

    spectre = _op(transport, "basic.spectre.run", cmd="echo spectre-ok")
    _check((spectre.get("result") or [1])[0] == 0, f"spectre: {spectre}")


def _case_file_roundtrip(transport) -> None:
    local_in = SCRATCH / "roundtrip_in.txt"
    local_in.write_text("vb-file-roundtrip\n", encoding="utf-8")
    run_dir = _remote_run_dir("roundtrip")
    remote = posixpath.join(run_dir, "roundtrip.txt")
    local_out = SCRATCH / "roundtrip_out.txt"
    up = _op(transport, "basic.file.upload",
             local_path=str(local_in), remote_path=remote)
    _check((up.get("result") or [1])[0] == 0, f"upload: {up}")
    down = _op(transport, "basic.file.download",
               remote_path=remote, local_path=str(local_out))
    _check((down.get("result") or [1])[0] == 0, f"download: {down}")
    _check(local_out.read_text(encoding="utf-8") == local_in.read_text(encoding="utf-8"),
           "file roundtrip mismatch")
    _op(transport, "basic.command.run", cmd=f"rm -rf {run_dir}")


def _case_demo(transport) -> None:
    facts = _op(transport, "demo.paths.facts")
    _check(facts.get("work_root"), f"paths.facts: {facts}")

    probe = _op(transport, "demo.parallel.probe",
                commands=["echo p1", "echo p2"], parallel=True)
    _check(probe.get("ok") and len(probe.get("results", [])) == 2, f"probe: {probe}")

    local_in = SCRATCH / "pipeline_in.txt"
    local_in.write_text("pipeline-data\n", encoding="utf-8")
    local_out = SCRATCH / "pipeline_out.txt"
    run_dir = _remote_run_dir("pipeline")
    remote_input = posixpath.join(run_dir, "in.txt")
    remote_output = posixpath.join(run_dir, "out.txt")
    pipeline = _op(
        transport, "demo.pipeline.run",
        local_input=str(local_in),
        remote_input=remote_input,
        skill_code='printf("skill-ok")',
        command=f"cat {remote_input} > {remote_output}",
        remote_output=remote_output,
        local_output=str(local_out),
    )
    _check(pipeline.get("ok"), f"pipeline: {pipeline}")
    _check(local_out.read_text(encoding="utf-8") == "pipeline-data\n", "pipeline content")
    _op(transport, "basic.command.run", cmd=f"rm -rf {run_dir}")

    netlist = SCRATCH / "demo_netlist.scs"
    netlist.write_text("// demo netlist\n", encoding="utf-8")
    imported = _op(
        transport, "virtuoso.netlist.import",
        local_netlist=str(netlist), library="schemtest",
        cell="demo_net_e2e", job="demo_net_e2e",
    )
    _check(imported.get("ok"), f"netlist.import: {imported}")


def _case_gui(transport) -> None:
    listing = _op(transport, "virtuoso.gui.list_windows")
    _check(listing.get("ok") and isinstance(listing.get("windows"), list),
           f"list_windows: {listing}")

    dismissed = _op(transport, "virtuoso.gui.auto_dismiss", max_attempts=1)
    _check(dismissed.get("ok"), f"auto_dismiss: {dismissed}")

    # send_key against a nonexistent window: exercises the injection path and
    # must fail with a structured X11 error (bad window), not a crash.
    response = transport.call({
        "operation": "virtuoso.gui.send_key", "token": TOKEN,
        "window_id": "0xdeadbeef", "key": "enter",
    })
    _check(not response.get("ok"), f"send_key bad window must fail: {response}")
    _check("BadWindow" in (response.get("error") or ""),
           f"send_key error text: {response.get('error')}")

    output = SCRATCH / "ciw.ppm"
    shot = _op(transport, "virtuoso.gui.screenshot",
               target="ciw", output_path=str(output))
    _check(shot.get("ok") and output.is_file() and output.stat().st_size > 0,
           f"screenshot: {shot}")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("BASIC-01 skill/command/gui/spectre", lambda: _case_basic(transport))
    run("BASIC-02 file upload/download", lambda: _case_file_roundtrip(transport))
    run("DEMO-01 paths/parallel/pipeline/netlist", lambda: _case_demo(transport))
    run("GUI-01 list/auto_dismiss/send_key/screenshot", lambda: _case_gui(transport))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="direct")
    args = parser.parse_args()
    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
