"""P-077: explicit remote tool values accept PATH names and file paths.

The daemon setup consumes ``role.daemon.python`` / ``role.spectre.bin`` via
``/usr/bin/env <value>``, so ``python3`` is a valid explicit value.  The
registration probe must resolve that value through PATH just like the runtime
does, while still rejecting aliases/functions/builtins and missing paths.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult  # noqa: E402
from register.probe import remote_executable_exists  # noqa: E402


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = list(responses)
        self.commands: list[str] = []

    def run_command(self, command: str, timeout=None) -> CommandResult:
        self.commands.append(command)
        return self.responses.pop(0) if self.responses else CommandResult(
            returncode=0, stdout="", stderr="",
        )


class TestRemoteExecutableExists(unittest.TestCase):
    def test_bare_path_name_uses_command_v(self) -> None:
        runner = FakeRunner([CommandResult(returncode=0, stdout="", stderr="")])
        self.assertTrue(remote_executable_exists(runner, "python3"))
        self.assertIn("command -v", runner.commands[-1])
        self.assertIn("python3", runner.commands[-1])

    def test_absolute_path_uses_file_and_execute_checks(self) -> None:
        runner = FakeRunner([CommandResult(returncode=0, stdout="", stderr="")])
        self.assertTrue(remote_executable_exists(runner, "/usr/bin/python3"))
        self.assertIn("test -f", runner.commands[-1])
        self.assertIn("test -x", runner.commands[-1])

    def test_missing_or_non_file_command_is_rejected(self) -> None:
        runner = FakeRunner([CommandResult(returncode=1, stdout="", stderr="missing")])
        self.assertFalse(remote_executable_exists(runner, "not-a-real-tool"))
        self.assertIn("command -v", runner.commands[-1])


if __name__ == "__main__":
    unittest.main()
