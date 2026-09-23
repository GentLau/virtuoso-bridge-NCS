"""Static contract of the registration page (per-role override UI, spec r2)."""

import re
import sys
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[3] / "src" / "register" / "registration_page.html"
ROLES = ("gui", "daemon", "command", "file", "spectre")
FIELDS = ("mode", "host", "user", "jump_host", "root")


class TestRegistrationPageContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_every_role_has_override_inputs(self):
        for role in ROLES:
            for field in FIELDS:
                self.assertIn(
                    f'id="role_{role}_{field}"', self.html,
                    f"missing per-role input role_{role}_{field}",
                )

    def test_override_inputs_are_named_for_formdata(self):
        for role in ROLES:
            for field in FIELDS:
                self.assertIn(f'name="role_{role}_{field}"', self.html)

    def test_payload_builder_folds_role_overrides(self):
        self.assertIn("const roles = {gui: {}, daemon: daemon", self.html)
        self.assertIn("const prefix = 'role_' + name + '_';", self.html)
        self.assertIn("payload.roles = roles;", self.html)

    def test_local_mode_rejects_connection_fields(self):
        self.assertIn("mode=local 的 role 不能填写", self.html)

    def test_gui_display_override_is_present(self):
        self.assertIn('id="role_gui_display"', self.html)
        self.assertIn('name="role_gui_display"', self.html)

    def test_details_blocks_are_balanced(self):
        self.assertEqual(
            self.html.count("<details"), self.html.count("</details>"),
            "unbalanced <details> blocks in the page",
        )

    def test_expected_fields_are_display_only(self):
        """expected_* 由探测回写，页面不得把它们作为用户输入提交。"""
        self.assertNotRegex(self.html, r'name="role_[a-z]+_expected_')

    def test_mode_is_never_defaulted_or_inferred(self):
        """多用户与注册 §2: mode.default 必填、不推断；页面不得预选或兜底。"""
        self.assertNotIn('name="mode" value="remote" checked', self.html)
        self.assertNotIn('name="mode" value="local" checked', self.html)
        self.assertNotIn("|| 'remote'", self.html)
        self.assertNotIn("return node ? node.value : 'auto'", self.html)
        self.assertIn("请选择运行模式", self.html)


if __name__ == "__main__":
    unittest.main()
