"""Offline contract for structured registration probe status.

The registration control plane serves API consumers first: callers must be
able to read which role succeeded, failed, warned, or was not attempted
without parsing natural-language errors.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import register.flow as flow_module
from register.models import (
    ConnectivityReport,
    RegistrationRequest,
    RegistrationState,
)
from register.server import RegistrationHandler


class _PayloadHandler:
    """Only the static payload projection is needed for this contract test."""

    _redacted = staticmethod(RegistrationHandler._redacted)
    _state_payload = RegistrationHandler._state_payload


def _local_request(root: str) -> RegistrationRequest:
    return RegistrationRequest(
        mode="local",
        user="probe-status",
        root={"default": root},
        roles={"gui": {"display": ":99"}},
    )


def _status_by_role(rows: list[dict]) -> dict[str, dict]:
    return {row["role"]: row for row in rows}


class TestProbeStatusContract(unittest.TestCase):
    def test_success_reports_every_role(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-probe-ok-") as root:
            request = _local_request(root)
            with mock.patch.object(
                flow_module.probes, "validate_local_display", return_value=True,
            ), mock.patch.object(
                flow_module.probes, "local_port_free", return_value=True,
            ), mock.patch.object(
                flow_module.probes, "detect_local_spectre",
                return_value="/opt/spectre/bin/spectre",
            ):
                result = flow_module._probe(request, token="tok-probe")

        statuses = _status_by_role(result.probe_results)
        self.assertEqual(
            [row["role"] for row in result.probe_results],
            ["gui", "daemon", "command", "file", "spectre"],
        )
        self.assertEqual(
            [statuses[name]["status"] for name in
             ("gui", "daemon", "command", "file", "spectre")],
            ["ok", "ok", "ok", "ok", "ok"],
        )
        self.assertTrue(all(statuses[name]["blocking"] for name in
                            ("gui", "daemon", "command", "file")))
        self.assertFalse(statuses["spectre"]["blocking"])
        self.assertIsNone(statuses["spectre"]["code"])

    def test_blocking_failure_marks_later_roles_not_run(self) -> None:
        def writable(path) -> bool:
            return not str(path).rstrip("/\\").endswith("command")

        with tempfile.TemporaryDirectory(prefix="vb-probe-fail-") as root:
            request = _local_request(root)
            with mock.patch.object(
                flow_module.probes, "validate_local_display", return_value=True,
            ), mock.patch.object(
                flow_module.probes, "local_port_free", return_value=True,
            ), mock.patch.object(
                flow_module.probes, "local_path_writable", side_effect=writable,
            ):
                with self.assertRaises(flow_module.RegistrationProbeError) as ctx:
                    flow_module._probe(request, token="tok-probe")

        statuses = _status_by_role(ctx.exception.probe_results)
        self.assertEqual(statuses["gui"]["status"], "ok")
        self.assertEqual(statuses["daemon"]["status"], "ok")
        self.assertEqual(statuses["command"]["status"], "error")
        self.assertEqual(statuses["file"]["status"], "not_run")
        self.assertEqual(statuses["spectre"]["status"], "not_run")
        self.assertEqual(statuses["file"]["code"], "not_run")
        self.assertEqual(statuses["spectre"]["code"], "not_run")
        self.assertTrue(statuses["command"]["blocking"])
        self.assertIn("command", statuses["command"]["message"])

    def test_flow_preserves_partial_probe_results_on_failure(self) -> None:
        registry = mock.Mock()
        registry.entries.return_value = []
        flow = flow_module.RegistrationFlow(registry)
        flow.start(RegistrationRequest(
            mode="local", user="probe-flow", token="tok-flow",
        ))
        flow.state.stage = "validated"
        failure = flow_module.RegistrationProbeError("command probe failed")
        failure.probe_results = [
            {"role": "gui", "status": "ok", "blocking": True,
             "code": None, "message": None},
            {"role": "daemon", "status": "ok", "blocking": True,
             "code": None, "message": None},
            {"role": "command", "status": "error", "blocking": True,
             "code": "command_probe_failed", "message": str(failure)},
            {"role": "file", "status": "not_run", "blocking": True,
             "code": "not_run", "message": None},
            {"role": "spectre", "status": "not_run", "blocking": False,
             "code": "not_run", "message": None},
        ]
        with mock.patch.object(flow_module, "probe_user", side_effect=failure):
            state = flow.probe()
        self.assertEqual(state.stage, "failed")
        self.assertEqual(
            [row["status"] for row in state.probe_results],
            ["ok", "ok", "error", "not_run", "not_run"],
        )

    def test_status_payload_exposes_probe_results_and_fingerprint(self) -> None:
        state = RegistrationState(
            user="alice",
            stage="failed",
            step=3,
            probe_results=[{
                "role": "command",
                "status": "error",
                "blocking": True,
                "code": "command_probe_failed",
                "message": "ssh unreachable",
            }],
            report=ConnectivityReport(
                token="tok",
                command_ok=True,
                skill_ok=True,
                token_ok=True,
                fingerprint_ok=False,
                detail="host key mismatch",
            ),
        )
        payload = _PayloadHandler()._state_payload(state)
        self.assertEqual(payload["probe_results"][0]["role"], "command")
        self.assertEqual(payload["probe_results"][0]["status"], "error")
        self.assertFalse(payload["report"]["fingerprint_ok"])


if __name__ == "__main__":
    unittest.main()
