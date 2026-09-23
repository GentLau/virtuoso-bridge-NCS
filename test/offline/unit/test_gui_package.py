"""gui business package unit tests — fake middle only, no X11/Virtuoso."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, QueryResult, RoleQuery
from pyapi.packages.gui import (
    AutoDismissRequest,
    ListWindowsRequest,
    Package,
    ScreenshotRequest,
    SendKeyRequest,
    parse_xwininfo_tree,
)

TREE = """\
xwininfo: Window id: 0x50e (the root window) (has no name)

  Root window id: 0x50e (the root window) (has no name)
  Parent window id: 0x0 (none)
     48 children:
     0x1600007 (has no name): ()  1x1+0+0  +0+0
     0x1600005 "perfUtilExtCtrl": ("perfUtilExtCtrl" "perfUtilExtCtrl")  640x480+0+0  +0+0
     0x400008 "Virtuoso 6.1.8-64b - Log: /home/Gent/project/vb11/CDS.log": ("virtuoso" "virtuoso")  795x193+243+804  +243+804
     0x600010 "Confirm Save Changes": ("virtuoso" "Dialog")  400x120+100+100  +100+100
"""


class FakeMiddle:
    def __init__(self):
        self.calls: list[tuple] = []
        self.tree = TREE
        self.verify_rc = 0
        self.list_rc = 0
        self.gui_rc = 0
        self.download_rc = 0
        self.query_result = QueryResult(
            status=ExecutionStatus.SUCCESS,
            roles={
                "file": RoleQuery(root="/srv/vb/vb11/file"),
                "gui": RoleQuery(root="/srv/vb/vb11/gui", display=":99"),
            },
        )

    def run_gui_command(self, cmd, timeout=None, *, token):
        self.calls.append(("gui", cmd, token))
        if "xwininfo -id" in cmd:
            rc = self.verify_rc
        elif "xwininfo -root -tree" in cmd:
            rc = self.list_rc
        else:
            rc = self.gui_rc
        return CommandResult(rc, self.tree if "root -tree" in cmd else "", "err" if rc else "")

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        self.calls.append(("download", remote_path, str(local_path), token))
        return CommandResult(self.download_rc, "", "down err" if self.download_rc else "")

    def query(self, token):
        self.calls.append(("query", token))
        return self.query_result

    def execute_skill(self, skill_code, timeout=None, *, token):
        return CommandResult(0, "", "")

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        return CommandResult(0, "", "")

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        return CommandResult(0, "", "")

    def run_spectre_command(self, cmd, timeout=None, *, token):
        return CommandResult(0, "", "")


class TestParse(unittest.TestCase):
    def test_parses_ciw_aux_anon_dialog(self):
        windows = parse_xwininfo_tree(TREE)
        by_id = {w["window_id"]: w for w in windows}
        self.assertEqual(by_id["0x400008"]["kind"], "ciw")
        self.assertEqual(by_id["0x400008"]["title"], "Virtuoso 6.1.8-64b - Log: /home/Gent/project/vb11/CDS.log")
        self.assertEqual(by_id["0x1600005"]["kind"], "aux")
        self.assertEqual(by_id["0x1600005"]["suggested_action"], "ignore")
        self.assertEqual(by_id["0x1600007"]["kind"], "anon")
        self.assertEqual(by_id["0x600010"]["kind"], "dialog")
        self.assertEqual(by_id["0x600010"]["suggested_action"], "dismiss")
        self.assertEqual(by_id["0x400008"]["wm_class"], ["virtuoso", "virtuoso"])


class TestListWindows(unittest.TestCase):
    def test_list_windows_ok(self):
        middle = FakeMiddle()
        result = Package(middle).list_windows(ListWindowsRequest(token="vb-vb11"))
        self.assertTrue(result.ok)
        self.assertEqual(len(result.windows), 4)
        self.assertEqual([c[0] for c in middle.calls], ["query", "gui"])
        self.assertIn("export DISPLAY=:99", middle.calls[1][1])
        self.assertIn("xwininfo -root -tree", middle.calls[1][1])

    def test_list_windows_missing_display(self):
        middle = FakeMiddle()
        middle.query_result = QueryResult(
            status=ExecutionStatus.SUCCESS,
            roles={"gui": RoleQuery(root="/srv/vb/vb11/gui")},
        )
        result = Package(middle).list_windows(ListWindowsRequest(token="vb-vb11"))
        self.assertFalse(result.ok)
        self.assertIn("display", result.error)

    def test_list_windows_ewmh_client_list(self):
        middle = FakeMiddle()
        middle.tree = """\
_NET_CLIENT_LIST(WINDOW): window id # 0x400008, 0x600010
__TREE__
xwininfo: Window id: 0x50e (the root window) (has no name)

  Root window id: 0x50e (the root window) (has no name)
     0x400008 "Virtuoso 6.1.8-64b - Log: /home/Gent/virtuoso_11.log": ("virtuoso" "virtuoso")  795x193+243+804  +243+804
        0x400009 "child": ("virtuoso" "virtuoso")  100x100+0+0  +0+0
     0x600010 "Confirm Save Changes": ("virtuoso" "Dialog")  400x120+100+100  +100+100
"""
        result = Package(middle).list_windows(ListWindowsRequest(token="vb-vb11"))
        self.assertTrue(result.ok)
        ids = [w["window_id"] for w in result.windows]
        self.assertEqual(ids, ["0x400008", "0x600010"])
        self.assertEqual(result.windows[0]["kind"], "ciw")

    def test_list_windows_gui_failure(self):
        middle = FakeMiddle()
        middle.list_rc = 1
        result = Package(middle).list_windows(ListWindowsRequest(token="vb-vb11"))
        self.assertFalse(result.ok)
        self.assertIn("err", result.error)


class TestSendKey(unittest.TestCase):
    def test_whitelist(self):
        middle = FakeMiddle()
        for bad in ("tab", "click", "ctrl-c", ""):
            with self.assertRaises(ValueError):
                Package(middle).send_key(SendKeyRequest(token="t", window_id="0x1", key=bad))

    def test_send_and_verify(self):
        middle = FakeMiddle()
        result = Package(middle).send_key(
            SendKeyRequest(token="vb-vb11", window_id="0x600010", key="enter"),
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.still_mapped)
        gui_calls = [c[1] for c in middle.calls if c[0] == "gui"]
        self.assertIn("export DISPLAY=:99", gui_calls[0])
        self.assertIn("python3", gui_calls[0])
        self.assertIn("0x600010", gui_calls[0])
        self.assertIn("XTestFakeKeyEvent", gui_calls[0])
        self.assertIn("xwininfo -id 0x600010", gui_calls[1])

    def test_still_mapped_false_when_window_gone(self):
        middle = FakeMiddle()
        middle.verify_rc = 1
        result = Package(middle).send_key(
            SendKeyRequest(token="t", window_id="0x600010", key="escape"),
        )
        self.assertTrue(result.ok)
        self.assertFalse(result.still_mapped)


class TestAutoDismiss(unittest.TestCase):
    def test_dialog_candidates_only_and_order(self):
        middle = FakeMiddle()
        middle.verify_rc = 1  # escape dismisses the dialog on first attempt
        result = Package(middle).auto_dismiss(AutoDismissRequest(token="vb-vb11", max_attempts=2))
        self.assertTrue(result.ok)
        self.assertEqual(len(result.dismissed), 1)
        self.assertEqual(result.dismissed[0]["window_id"], "0x600010")
        keys = [c for c in result.dismissed[0]["attempts"]]
        self.assertEqual([k["key"] for k in keys], ["escape"])
        # verify succeeded for escape -> window already gone, no second attempt
        self.assertFalse(result.dismissed[0]["still_mapped"])


class TestScreenshot(unittest.TestCase):
    def test_ciw_screenshot_flow(self):
        middle = FakeMiddle()
        result = Package(middle).screenshot(
            ScreenshotRequest(token="vb-vb11", output_path="out.ppm", target="ciw"),
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.local_path, "out.ppm")
        kinds = [c[0] for c in middle.calls]
        self.assertEqual(kinds, ["query", "query", "gui", "gui", "download"])
        capture = middle.calls[3][1]
        self.assertIn("python3", capture)
        self.assertIn("export DISPLAY=:99", capture)
        self.assertIn("0x400008", capture)
        self.assertIn("/srv/vb/vb11/gui/screenshots/shot-", capture)
        self.assertTrue(middle.calls[4][1].startswith("/srv/vb/vb11/gui/screenshots/shot-"))

    def test_target_validation(self):
        middle = FakeMiddle()
        for bad in ("all", "0xZZ", ""):
            with self.assertRaises(ValueError):
                Package(middle).screenshot(
                    ScreenshotRequest(token="t", output_path="o", target=bad),
                )

    def test_no_ciw(self):
        middle = FakeMiddle()
        middle.tree = TREE.replace("Virtuoso 6.1.8", "Nothing")
        result = Package(middle).screenshot(
            ScreenshotRequest(token="t", output_path="o", target="ciw"),
        )
        self.assertFalse(result.ok)
        self.assertIn("no CIW window", result.error)


if __name__ == "__main__":
    unittest.main()
