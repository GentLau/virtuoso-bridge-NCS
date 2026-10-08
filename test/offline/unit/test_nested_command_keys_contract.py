# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:10
# 依赖: 无
# =======================================================================
"""round9 补点：嵌套命令键的 L0 契约（`commands[].*` / `tasks[].*`）。

背景：round9 的嵌套键审计（`test/reports/round9/nested-key-coverage.md`）发现
**20 个用户可传的嵌套键从未被任何 TB 触碰**：

* symbol：`place_pin` 的 `half_size`/`label_pos`/`label_justify`/`label_orient`/`label_font`/`label_height`，
  `set_pin_properties` 的 `label_justify`/`label_orient`/`label_font`/`label_height`，
  `set_label_properties` 的 `label_type`；
* schematic：`place_wire` 的 `x_spacing`/`y_spacing`；
* maestro：`set_corner` 的 `enabled`/`enable_tests`/`disable_tests`、`set_var` 的 `type_name`/`type_value`、
  `load_corners` 的 `sections`、`setup_corner` 的 `model_file`/`model_section`、
  job policy 三操作的 `name`/`job_type`/`test` 键（`create_job_policy`/`delete_job_policy`/
  `attach_job_policy`，P-118 起取代 `set_job_policy`）。

**判据（期望 / 实际 / 判定）**：喂入该键后，生成的 SKILL 文本必须出现与"键已生效"唯一对应的片段
（例如 `?enabled nil`、`~>labelType = "drawing"`、`schCreateWire(… 0.25 0.5 …)`）；
实际值取自记录型假 middle 捕获的 SKILL；判定 = 断言命中（含负例：非法/遗留键必须被拒绝）。

> ⚠ 口径（`写TB规范.md`）：本文件属**离线契约**，只证明参数被正确拼装进 SKILL，
> **不得**在报告里算作这些操作"已被真机覆盖"；真机判据仍须由 live TB 承担。

六步流程（`写TB规范.md` §1）——离线用例：
① 环境检查**不适用**（纯字符串构造 + 假 middle，不连真机）；
②③ 前置构建/校验**不适用**（无持久对象、无远端路径）；
④⑤ = Arrange→Act→Assert（每条断言给出期望与实际）；⑥ 无现场可留（不落盘、不起服务、不占端口）。
"""
from __future__ import annotations

import unittest

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import maestro as M
from pyapi.packages import schematic as SC
from pyapi.packages import spectre as SP
from pyapi.packages import symbol as S


def _ok(output: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=output)


class CaptureMiddle:
    """记录 execute_skill 的假 middle；按队列作答，缺省返回 `"ok"`。"""

    def __init__(self, *results: str) -> None:
        self.calls: list[str] = []
        self.queue = [_ok(r) for r in results]

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append(skill_code)
        return self.queue.pop(0) if self.queue else _ok('"ok"')

    def query(self, *, token, role=None, name=None):
        class _Role:
            root = "/role/root"

        class _Query:
            roles = {"command": _Role(), "daemon": _Role(), "file": _Role()}

        return _Query()


class TestSymbolPinLabelKeys(unittest.TestCase):
    """symbol：pin 标签族 7 键（round9 审计中 14 条 op×键 缺口）。"""

    def _write(self, commands, *results):
        middle = CaptureMiddle(*results)
        result = S.Package(middle).write(
            S.WriteRequest(token="t", library="L", cell="C", commands=commands))
        return result, middle

    def test_place_pin_label_keys_reach_skill(self):
        # 期望：half_size 决定 bbox 半宽 0.2；label_* 六键原样进 schCreateSymbolLabel
        result, middle = self._write(
            [{"op": "place_pin", "name": "VIN", "pos": [0.5, 0.5], "half_size": 0.2,
              "label_pos": [0.9, 0.7], "label_justify": "lowerLeft", "label_orient": "R90",
              "label_font": "courier", "label_height": 0.1}],
            '"ok"', '"open-ok"', "db:1", '"saved"')
        self.assertTrue(result.ok, result.error)
        skill = middle.calls[2]
        actual = {
            "bbox_half_size": "list(list(0.3 0.3) list(0.7 0.7))" in skill,
            "label_pos": "list(0.9 0.7)" in skill,
            "label_justify": '"lowerLeft"' in skill,
            "label_orient": '"R90"' in skill,
            "label_font": '"courier"' in skill,
            "label_height": " 0.1 " in skill,
            "label_fn": "schCreateSymbolLabel(" in skill,
        }
        self.assertEqual(actual, dict.fromkeys(actual, True), f"actual={actual}")

    def test_place_pin_defaults_are_stable(self):
        # 期望：half_size 默认 0.0625 → bbox 半宽 0.0625；label_font 默认 stick、label_height 0.0625
        result, middle = self._write(
            [{"op": "place_pin", "name": "VIN", "pos": [0.0, 0.0]}],
            '"ok"', '"open-ok"', "db:1", '"saved"')
        self.assertTrue(result.ok, result.error)
        skill = middle.calls[2]
        self.assertIn("list(list(-0.0625 -0.0625) list(0.0625 0.0625))", skill)
        self.assertIn('"stick"', skill)
        self.assertIn(" 0.0625 ", skill)

    def test_place_pin_rejects_legacy_label_xy(self):
        # 期望：遗留 label_x/label_y 明确拒绝并指路 label_pos（与 spec 3-symbol.md 一致）
        middle = CaptureMiddle('"ok"', '"open-ok"')
        result = S.Package(middle).write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_pin", "name": "VIN", "pos": [0, 0],
                       "label_x": 1.0}]))
        self.assertFalse(result.ok)
        self.assertIn("label_pos", result.error)

    def test_set_pin_properties_label_keys_reach_skill(self):
        result, middle = self._write(
            [{"op": "set_pin_properties", "name": "VIN", "label_justify": "centerLeft",
              "label_orient": "R180", "label_font": "courier", "label_height": 0.2}],
            '"ok"', '"open-ok"', "db:1", '"saved"')
        self.assertTrue(result.ok, result.error)
        skill = middle.calls[2]
        actual = {
            "font": '~>font = "courier"' in skill,
            "height": "~>height = 0.2" in skill,
            "justify": '~>justify = "centerLeft"' in skill,
            "orient": '~>orient = "R180"' in skill,
        }
        self.assertEqual(actual, dict.fromkeys(actual, True), f"actual={actual}")

    def test_set_label_properties_label_type_reaches_skill(self):
        # 期望：label_type 是 set_label_properties 的可写字段（~>labelType）；pos 为定位必填
        middle = CaptureMiddle('"ok"', '"open-ok"', "db:1", '"saved"')
        result = S.Package(middle).write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "set_label_properties", "text": "OUT", "pos": [1.5, 2.5],
                       "label_type": "drawing"}]))
        self.assertTrue(result.ok, result.error)
        self.assertIn('~>labelType = "drawing"', middle.calls[2])

    def test_set_label_properties_requires_a_writable_field(self):
        # 期望：不给任何可写字段时结构化失败（不产生空赋值 SKILL）
        middle = CaptureMiddle('"ok"', '"open-ok"', "db:1", '"saved"')
        result = S.Package(middle).write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "set_label_properties", "text": "OUT", "pos": [1.5, 2.5]}]))
        self.assertFalse(result.ok)
        self.assertIn("writable field", result.error)


class TestSchematicWireSpacingKeys(unittest.TestCase):
    """schematic：`place_wire` 的 x_spacing / y_spacing（spec 未记载，见 round9 报告）。"""

    def test_place_wire_spacing_keys_reach_skill(self):
        middle = CaptureMiddle('"open-ok"', '"ok"', '"saved"')
        result = SC.Package(middle).write(SC.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_wire", "points": [[0, 0], [1, 0]],
                       "x_spacing": 0.25, "y_spacing": 0.5}]))
        self.assertTrue(result.ok, result.error)
        wire = [c for c in middle.calls if "schCreateWire(" in c]
        self.assertEqual(len(wire), 1, middle.calls)
        # 期望：x_spacing=0.25 / y_spacing=0.5 出现在 schCreateWire 的第 5/6 实参位
        self.assertIn("list(0:0 1:0) 0.25 0.5 ", wire[0])

    def test_place_wire_spacing_defaults_to_zero(self):
        middle = CaptureMiddle('"open-ok"', '"ok"', '"saved"')
        result = SC.Package(middle).write(SC.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_wire", "points": [[0, 0], [1, 0]]}]))
        self.assertTrue(result.ok, result.error)
        wire = [c for c in middle.calls if "schCreateWire(" in c][0]
        self.assertIn("list(0:0 1:0) 0 0 ", wire)


class TestMaestroNestedKeys(unittest.TestCase):
    """maestro：test/corner 门控、变量类型、corner 模型、job policy（12 条 op×键 缺口）。"""

    def _exprs(self, command: dict) -> list[str]:
        return M.Package(CaptureMiddle())._command_exprs(command, "s1")

    def test_set_corner_gating_keys(self):
        skill = self._exprs({"op": "set_corner", "name": "c1", "enabled": True,
                             "enable_tests": ["t1"], "disable_tests": ["t2"]})[0]
        actual = {"enabled": "?enabled t" in skill,
                  "enable_tests": '?enableTests `("t1")' in skill,
                  "disable_tests": '?disableTests `("t2")' in skill,
                  "corner_name": 'maeSetCorner("c1"' in skill}
        self.assertEqual(actual, dict.fromkeys(actual, True), f"actual={actual}")

    def test_set_corner_enabled_false_is_explicit_nil(self):
        skill = self._exprs({"op": "set_corner", "name": "c1", "enabled": False})[0]
        self.assertIn("?enabled nil", skill)

    def test_set_corner_omits_gating_keys_when_absent(self):
        skill = self._exprs({"op": "set_corner", "name": "c1"})[0]
        self.assertNotIn("?enabled", skill)
        self.assertNotIn("?enableTests", skill)
        self.assertNotIn("?disableTests", skill)

    def test_set_var_type_name_and_type_value(self):
        skill = self._exprs({"op": "set_var", "name": "v1", "value": 1.5,
                             "type_name": "corner", "type_value": ["c1"]})[0]
        self.assertIn('?typeName "corner"', skill)
        self.assertIn('?typeValue \'("c1")', skill)
        self.assertIn('axlGetCorner(sdb cn)', skill)  # 先存在性校验再写

    def test_set_var_scope_test_derives_type(self):
        skill = self._exprs({"op": "set_var", "name": "v1", "value": 1.5,
                             "scope": "test", "test": "t1"})[0]
        self.assertIn('?typeName "test"', skill)
        self.assertIn('?typeValue \'("t1")', skill)

    def test_set_var_non_test_corner_type_name_is_not_emitted(self):
        # 期望：type_name 只认 test/corner；其它值不产生 ?typeName（当前实现语义，如实钉住）
        skill = self._exprs({"op": "set_var", "name": "v1", "value": 1.5,
                             "type_name": "global"})[0]
        self.assertNotIn("?typeName", skill)

    def test_load_corners_sections_key(self):
        skill = self._exprs({"op": "load_corners", "filepath": "/tmp/c.corners",
                             "sections": "mc"})[0]
        self.assertIn('?sections "mc"', skill)

    def test_setup_corner_model_keys(self):
        skill = self._exprs({"op": "setup_corner", "name": "c1",
                             "model_file": "/pdk/models.scs",
                             "model_section": "TT"})[0]
        self.assertIn('axlSetModelFile(model "/pdk/models.scs")', skill)
        self.assertIn('axlSetModelSection(model "TT")', skill)

    # ---- P-118：job policy 三操作（create / delete / attach） --------------------
    def test_create_job_policy_without_name_updates_global_default(self):
        # name 省略 = 改全局默认：不加 jp->name，直接把改过的 DPL set 回去
        skill = self._exprs({"op": "create_job_policy",
                             "policy": {"configuretimeout": "300"}})[0]
        self.assertIn('?jobType "simulation"', skill)
        self.assertIn("maeSetJobPolicy(jp ?jobType", skill)
        self.assertNotIn("jp->name =", skill)
        self.assertNotIn("maeGetJobPolicyByName", skill)

    def test_create_job_policy_named_resource_restores_default(self):
        # name 显式 = 建/覆盖具名资源；set 会临时改变默认引用，必须恢复
        skill = self._exprs({"op": "create_job_policy", "name": "my policy",
                             "policy": {"maxjobs": 3}})[0]
        self.assertIn('maeGetJobPolicyByName("my policy"', skill)
        self.assertIn('jp->name = "my policy"', skill)
        self.assertIn("jp->maxjobs = 3", skill)
        self.assertIn('unless(equal("my policy" base->name)', skill)
        self.assertIn('error("failed to restore the default job policy")', skill)

    def test_create_job_policy_netlisting_prepends_lscs(self):
        skill = self._exprs({"op": "create_job_policy", "name": "NetP",
                             "job_type": "netlisting",
                             "policy": {"maxjobs": 1}})[0]
        self.assertIn('maeSetJobControlMode("LSCS"', skill)
        self.assertIn('?jobType "netlisting"', skill)

    def test_create_job_policy_rejects_bad_name_and_job_type(self):
        with self.assertRaises(ValueError):
            self._exprs({"op": "create_job_policy", "name": 'bad"name',
                         "policy": {"maxjobs": 1}})
        with self.assertRaises(ValueError):
            self._exprs({"op": "create_job_policy", "job_type": "MonteCarlo",
                         "policy": {"maxjobs": 1}})

    def test_delete_job_policy_and_default_guard(self):
        skill = self._exprs({"op": "delete_job_policy", "name": "P1"})[0]
        self.assertIn('axlDeleteJobPolicy("P1")', skill)
        # 真机口径：返回值不可靠（.jp 清理失败也返回 nil），以复查为准
        self.assertIn('maeGetJobPolicyByName("P1")', skill)
        self.assertIn("policy still exists", skill)
        for default in ("Maestro Default", "Netlisting Default"):
            with self.assertRaises(ValueError):
                self._exprs({"op": "delete_job_policy", "name": default})

    def test_attach_job_policy_mounts_named_policy(self):
        skill = self._exprs({"op": "attach_job_policy", "test": "ac",
                             "name": "P1"})[0]
        self.assertIn('maeGetJobPolicyByName("P1"', skill)
        self.assertIn('maeSetJobPolicy(jp ?testName "ac"', skill)
        self.assertIn('?jobType "simulation"', skill)
        self.assertIn('maeHasTestJobPolicy("ac"', skill)

    def test_attach_job_policy_default_name_detaches(self):
        # name 等于该 jobType 当前默认名（动态比较 base->name）→ 整体去挂载
        skill = self._exprs({"op": "attach_job_policy", "test": "ac",
                             "name": "P1"})[0]
        self.assertIn('maeClearTestJobPolicy("ac"', skill)
        self.assertIn('equal("P1" base->name)', skill)
        self.assertIn('maeHasTestJobPolicy("ac"', skill)

    def test_attach_job_policy_without_name_detaches(self):
        skill = self._exprs({"op": "attach_job_policy", "test": "ac"})[0]
        self.assertIn('maeClearTestJobPolicy("ac"', skill)
        self.assertIn('maeHasTestJobPolicy("ac"', skill)
        self.assertNotIn("maeSetJobPolicy", skill)

    def test_attach_job_policy_netlisting_is_setup_scoped(self):
        # 真机口径：netlisting 无 test 级挂载，attach = 设置 setup 级单例
        skill = self._exprs({"op": "attach_job_policy", "test": "ac",
                             "name": "NetP",
                             "job_type": "netlisting"})[0]
        self.assertIn('maeSetJobControlMode("LSCS"', skill)
        self.assertIn('maeGetJobPolicyByName("NetP"', skill)
        self.assertIn('maeSetJobPolicy(jp ?jobType "netlisting"', skill)
        self.assertIn('equal("NetP" maeGetJobPolicy(?jobType "netlisting"', skill)

    def test_attach_job_policy_netlisting_without_name_restores_default(self):
        skill = self._exprs({"op": "attach_job_policy", "test": "ac",
                             "job_type": "netlisting"})[0]
        self.assertIn('maeGetJobPolicyByName("Netlisting Default")', skill)
        self.assertIn('maeSetJobPolicy(jp ?jobType "netlisting"', skill)
        self.assertIn('equal("Netlisting Default"', skill)

    def test_spec_name_key_on_delete_output_and_delete_spec(self):
        # delete_output：delete_spec=True 时按 spec_name 删同名 spec；缺省回落到 "<test>.<name>"
        explicit = self._exprs({"op": "delete_output", "name": "OUT", "test": "t1",
                                "delete_spec": True, "spec_name": "t1.OUT"})
        self.assertEqual(len(explicit), 2, explicit)
        self.assertIn('axlGetSpec(axlGetMainSetupDB("s1") "t1.OUT")', explicit[1])
        fallback = self._exprs({"op": "delete_output", "name": "OUT", "test": "t1",
                                "delete_spec": True})
        self.assertIn('"t1.OUT"', fallback[1])
        # delete_spec：spec_name 优先，缺省回落 name
        direct = self._exprs({"op": "delete_spec", "spec_name": "t1.GAIN"})[0]
        self.assertIn('axlGetSpec(axlGetMainSetupDB("s1") "t1.GAIN")', direct)


class TestSpectreModeEnum(unittest.TestCase):
    """spectre：`_MODES` 的 5 个从未被 TB 使用的取值（ax/cx/lx/mx/vx）。"""

    def test_all_documented_modes_are_accepted(self):
        for mode in ("spectre", "aps", "cx", "ax", "mx", "lx", "vx"):
            with self.subTest(mode=mode):
                self.assertEqual(SP._require_mode(mode), mode)

    def test_unknown_mode_is_rejected(self):
        for bad in ("bogus_mode", "x"):
            with self.subTest(mode=bad):
                with self.assertRaises(ValueError) as ctx:
                    SP._require_mode(bad)
                self.assertIn("must be one of", str(ctx.exception))

    def test_task_normalization_accepts_every_mode(self):
        # 期望：tasks[].mode 走同一校验；逐 mode 构造一次请求都能通过
        for mode in SP._MODES:
            with self.subTest(mode=mode):
                request = SP.RunRequest(token="t", tasks=[{
                    "job": "j1", "netlist": "n.scs", "mode": mode}])
                tasks = SP._normalize_tasks(request)
                self.assertEqual(tasks[0]["mode"], mode)


if __name__ == "__main__":
    unittest.main()
