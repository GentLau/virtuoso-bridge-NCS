"""Contracts for the ``calibre`` package's argv builder and kind detection.

These two helpers decide *what actually runs on the real machine*: ``_argv_for``
builds the Calibre command lines (a wrong flag silently produces a green run of
the wrong analysis) and ``_detect_kind`` decides which analysis a re-run of an
existing run directory belongs to.  Both are pure functions of the request, so
they are pinned here instead of being inferred from a real Calibre run.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _fake_middle import FakeMiddle, ok_command

from pyapi.models import ExecutionStatus, QueryResult, RoleQuery, VirtuosoResult
from pyapi.packages.calibre import Package, RunRequest, _argv_for


def _request(**overrides) -> RunRequest:
    fields = dict(token="tok", gds="/remote/top.gds", top="top", deck="/pdk/calibre.lvs")
    fields.update(overrides)
    return RunRequest(**fields)


class TestRunRequestValidation(unittest.TestCase):
    def test_empty_token_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _request(token="")
        self.assertIn("token", str(ctx.exception))

    def test_blank_gds_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _request(gds="   ")
        self.assertIn("gds", str(ctx.exception))

    def test_optional_text_rejects_nul(self):
        with self.assertRaises(ValueError) as ctx:
            _request(cdl="/tmp/a\x00b")
        self.assertIn("NUL", str(ctx.exception))

    def test_turbo_range_and_bool_are_rejected(self):
        for bad in (0, 65, True):
            with self.subTest(turbo=bad):
                with self.assertRaises(ValueError):
                    _request(turbo=bad)

    def test_bad_fmt_is_rejected(self):
        with self.assertRaises(ValueError):
            _request(fmt="gds")


class TestArgvFor(unittest.TestCase):
    def test_drc_hierarchical(self):
        argv = _argv_for("drc", _request(hier=True), "calibre", "/run", "deck")
        self.assertEqual(argv, [["calibre", "-drc", "-hier", "-turbo", "4",
                                 "/run/run_drc.cal"]])

    def test_drc_flat_omits_hier_flag(self):
        argv = _argv_for("drc", _request(hier=False), "calibre", "/run", "deck")
        self.assertEqual(argv, [["calibre", "-drc", "-turbo", "4", "/run/run_drc.cal"]])

    def test_lvs_hierarchical(self):
        argv = _argv_for("lvs", _request(hier=True, turbo=8), "c", "/run", "deck")
        self.assertEqual(argv, [["c", "-lvs", "-hier", "-turbo", "8", "/run/run_lvs.cal"]])

    def test_pex_runs_two_stages(self):
        argv = _argv_for("pex", _request(), "calibre", "/run", "deck")
        self.assertEqual(len(argv), 2)
        self.assertEqual(argv[0], ["calibre", "-xrc", "-phdb", "-turbo", "4",
                                   "/run/run_pex.cal"])
        self.assertEqual(argv[1], ["calibre", "-xrc", "-pdb", "-rc",
                                   "/run/run_pex.cal", "-turbo", "4"])

    def test_pex_adds_a_format_stage_only_for_spice_like_formats(self):
        plain = _argv_for("pex", _request(fmt="none"), "calibre", "/run", "deck")
        spice = _argv_for("pex", _request(fmt="spice"), "calibre", "/run", "deck")
        simple = _argv_for("pex", _request(fmt="simple"), "calibre", "/run", "deck")
        self.assertEqual(len(plain), 2)
        self.assertEqual(len(spice), 3)
        self.assertEqual(len(simple), 3)
        self.assertEqual(spice[2],
                         ["calibre", "-xrc", "-fmt", "spice", "/run/run_pex.cal"])
        self.assertEqual(simple[2],
                         ["calibre", "-xrc", "-fmt", "simple", "/run/run_pex.cal"])


class TestDetectKind(unittest.TestCase):
    def test_reads_kind_from_run_dir_marker(self):
        middle = FakeMiddle()
        middle.queue("run_command", ok_command("lvs\n"))
        package = Package(middle)
        steps: list[dict] = []
        self.assertEqual(package._detect_kind(_request(run_dir="/run"), steps), "lvs")
        self.assertTrue(steps[-1]["ok"])

    def test_reads_kind_from_job_json_contents(self):
        middle = FakeMiddle()
        middle.queue("run_command", ok_command('{"kind": "pex", "gds": "x"}'))
        package = Package(middle)
        steps: list[dict] = []
        self.assertEqual(package._detect_kind(_request(run_dir="/run"), steps), "pex")

    def test_unrecognised_output_falls_back_to_drc(self):
        middle = FakeMiddle()
        middle.queue("run_command", ok_command("something else\n"))
        package = Package(middle)
        steps: list[dict] = []
        self.assertEqual(package._detect_kind(_request(run_dir="/run"), steps), "drc")
        self.assertFalse(steps[-1]["ok"])
        self.assertEqual(steps[-1]["detail"], "assume drc")

    def test_without_run_dir_no_probe_is_run(self):
        middle = FakeMiddle()
        package = Package(middle)
        steps: list[dict] = []
        self.assertEqual(package._detect_kind(_request(run_dir=None), steps), "drc")
        self.assertFalse(middle.called("run_command"))


class TestCalibreBinAndRoot(unittest.TestCase):
    def _query(self, **role_extras):
        command = RoleQuery(root="/remote/root")
        for key, value in role_extras.items():
            setattr(command, key, value)
        return QueryResult(status=ExecutionStatus.SUCCESS, roles={"command": command})

    def test_override_wins_without_querying(self):
        middle = FakeMiddle()
        package = Package(middle)
        steps: list[dict] = []
        self.assertEqual(package._calibre_bin("tok", "/opt/calibre", steps), "/opt/calibre")
        self.assertFalse(middle.called("query"))
        self.assertEqual(steps[-1]["detail"]["source"], "request")

    def test_registry_role_group_supplies_the_binary(self):
        middle = FakeMiddle()
        middle.query_result = self._query(calibre={"bin": "  /pdk/calibre  "})
        package = Package(middle)
        steps: list[dict] = []
        self.assertEqual(package._calibre_bin("tok", None, steps), "  /pdk/calibre  ")
        self.assertTrue(steps[-1]["ok"])

    def test_query_failure_is_reported_not_raised(self):
        middle = FakeMiddle()
        middle.raise_on = {"query"}
        package = Package(middle)
        steps: list[dict] = []
        self.assertIsNone(package._calibre_bin("tok", None, steps))
        self.assertFalse(steps[-1]["ok"])
        self.assertIn("RuntimeError", steps[-1]["detail"])

    def test_command_root_comes_from_the_role(self):
        middle = FakeMiddle()
        middle.query_result = self._query()
        package = Package(middle)
        steps: list[dict] = []
        self.assertEqual(package._command_root("tok", steps), "/remote/root")
        self.assertTrue(steps[-1]["ok"])

    def test_command_root_query_failure_returns_none(self):
        middle = FakeMiddle()
        middle.raise_on = {"query"}
        package = Package(middle)
        steps: list[dict] = []
        self.assertIsNone(package._command_root("tok", steps))
        self.assertFalse(steps[-1]["ok"])


if __name__ == "__main__":
    unittest.main()
