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

    def test_enhanced_token_field_is_declared(self):
        """spec r18–r22: apply 可携带增强凭据（管理员或任一已登记持有者 token）。"""
        self.assertIn('id="enhanced_token"', self.html)
        self.assertIn('name="enhanced_token"', self.html)
        self.assertIn('spellcheck="false"', self.html)
        self.assertIn("仅在声明本机模式", self.html)
        self.assertIn("管理员 token", self.html)
        self.assertIn("已登记持有者", self.html)
        self.assertIn("不落盘", self.html)

    def test_enhanced_token_is_required_only_for_local_declarations(self):
        """mode=local（含任一 role 为 local）才要求增强凭据，remote 保持可选。"""
        self.assertIn("function effectiveRoleMode(", self.html)
        self.assertIn("function localModeDeclared()", self.html)
        self.assertIn("byId('enhanced_token').required = localDeclared;", self.html)
        self.assertIn("本机模式必填", self.html)
        self.assertIn("本机模式需要增强凭据", self.html)
        # role 级 local 切换同样要驱动必填状态刷新
        self.assertIn(
            "byId('role_' + name + '_mode').addEventListener('change', updateModeUI)",
            self.html,
        )

    def test_payload_carries_enhanced_token_only_when_filled(self):
        self.assertIn(
            "if (flat.enhanced_token) payload.enhanced_token = flat.enhanced_token;",
            self.html,
        )

    def test_enhanced_token_is_not_written_to_the_local_draft(self):
        """凭据只用于本次 apply：不得抄进 sessionStorage 草稿。"""
        self.assertIn("if (key === 'enhanced_token') return;", self.html)

    def test_role_credentials_are_rejected_for_local_roles(self):
        """local role 不得携带 key_dir/key（与后端 role 校验一致）。"""
        self.assertIn(
            "['host', 'user', 'jump_host', 'key_dir', 'key'].forEach(function(field) {",
            self.html,
        )

    def test_step_one_auth_failure_returns_to_the_form(self):
        """增强凭据校验失败（401）时回到表单修正，而非停在通用错误面板。"""
        self.assertIn(
            "if (info.step === 1 && (error.status === 400 || error.status === 401)) {",
            self.html,
        )

    def test_role_field_errors_are_cleared_between_validations(self):
        """role 字段清空后必须撤销上一次的 setCustomValidity，否则表单永远无法提交。"""
        self.assertIn(
            "document.querySelectorAll('#f [id^=\"role_\"]').forEach(function(node) {",
            self.html,
        )


if __name__ == "__main__":
    unittest.main()
