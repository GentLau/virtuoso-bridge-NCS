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
            "['host', 'user', 'jump_host', 'jump_user', 'proxy', 'key_dir', 'key'].forEach(function(field) {",
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

    def test_root_default_uses_five_role_semantics(self):
        """root.default 是各 role 根的基准，不是共享的部署根。"""
        self.assertIn("~/.virtuoso-bridge/&lt;userid&gt;", self.html)
        self.assertIn("~/.virtuoso-bridge/<userid>", self.html)
        self.assertNotIn("必须同时对部署主机、GUI 主机和 daemon 主机可见", self.html)
        self.assertIn("各 role 根互相独立", self.html)

    def test_role_table_exposes_full_common_overrides(self):
        """5 role 都应能从页面覆盖 jump_user/proxy，而不仅是全局默认。"""
        for role in ROLES:
            for field in ("jump_user", "proxy"):
                self.assertIn(f'id="role_{role}_{field}"', self.html)
                self.assertIn(f'name="role_{role}_{field}"', self.html)

    def test_daemon_python_can_be_explicitly_submitted(self):
        """role.daemon.python 是环境项：缺省探测，显式提供时校验。"""
        self.assertIn('id="role_daemon_python"', self.html)
        self.assertIn('name="role_daemon_python"', self.html)
        self.assertIn(
            "'root', 'display', 'max_sessions', 'python'",
            self.html,
        )

    def test_role_hosts_have_a_single_source(self):
        """daemon/spectre 的快捷字段与 role 表不能同时提交两套主机配置。"""
        self.assertNotIn('name="daemon_host"', self.html)
        self.assertNotIn('name="daemon_user"', self.html)
        self.assertNotIn('name="spectre_host"', self.html)

    def test_deployment_summary_uses_daemon_root(self):
        """bridge 文件只部署到 daemon.root，展示不能拿 file.root 冒充。"""
        self.assertIn("resolved.daemon_root", self.html)
        self.assertNotIn(
            "deployResult = {tone: 'success', text: resolved.file_root}",
            self.html,
        )

    def test_file_and_spectre_routes_use_their_own_role_fallback(self):
        """file/spectre 独立解析，回退 ssh.default，不再跟随 command。"""
        self.assertNotIn("跟随 command 主机并按用户隔离", self.html)
        self.assertNotIn("缺省同 command 主机", self.html)
        self.assertIn("继承 ssh.default", self.html)

    def test_console_has_three_separate_workspaces(self):
        """注册、个人管理、管理员系统管理必须是三个可切换工作区。"""
        for page_id in ("page-register", "page-personal", "page-admin"):
            self.assertIn(f'id="{page_id}"', self.html)
        self.assertIn('data-page="register"', self.html)
        self.assertIn('data-page="personal"', self.html)
        self.assertIn('data-page="admin"', self.html)
        self.assertIn("function switchWorkspace(name)", self.html)

    def test_personal_page_combines_query_and_update(self):
        """个人页必须在同一详情面板内完成查询、编辑、diff、保存和删除。"""
        for element_id in (
            "personalConnectBtn",
            "personalTokenInput",
            "personalEnhancedInput",
            "personalDetail",
            "personalEditBtn",
            "personalEditor",
            "personalDiffBox",
            "personalSaveBtn",
            "personalDeleteBtn",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn("'/api/user/' + encodeURIComponent(user)", self.html)
        self.assertIn("'/api/user/' + encodeURIComponent(user) + '/update'", self.html)
        self.assertIn("function personalRequest(path, options, payload)", self.html)
        self.assertIn("body.enhanced_token = credentials.enhanced", self.html)
        self.assertIn("'Authorization': 'Bearer ' + credentials.personal", self.html)
        self.assertNotIn("'Authorization': 'Bearer ' + credentials.enhanced", self.html)
        self.assertNotIn("增强凭据兼容模式", self.html)
        self.assertIn("function inspectPersonalPatch(patch)", self.html)
        self.assertIn("key / key_dir 属于管理员字段", self.html)

    def test_admin_page_is_system_scoped(self):
        """管理员页只管理系统配置和进程，不承载逐用户参数编辑。"""
        self.assertIn('id="adminBusinessPoolSize"', self.html)
        self.assertIn("'/api/config'", self.html)
        self.assertIn("'/api/process/status'", self.html)
        self.assertIn("'/api/process/' + action", self.html)
        self.assertNotIn('id="adminEditBtn"', self.html)

    def test_personal_page_encodes_v42_field_level_boundaries(self):
        """个人页必须披露只读字段、保密字段和删除的管理员边界。"""
        self.assertIn("只读字段", self.html)
        self.assertIn("DELETE /api/user/&lt;user&gt;", self.html)
        self.assertIn("仍要求管理员 Authorization", self.html)
        self.assertIn("function renderPersonalFailure(error, action)", self.html)
        self.assertIn("管理员字段", self.html)


if __name__ == "__main__":
    unittest.main()
