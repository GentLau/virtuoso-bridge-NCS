# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 21:05
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：离线用例，不需要真机；
# ②③ 构建：从 `src/pyapi/packages/*.py` 的 `OPERATIONS` 注册表导入全部 op 与 Request 类；
# ④ 只做被测动作：逐 op 读 Request 的 pydantic 字段（不实例化、不联网）；
# ⑤ 比对：公共字段的存在性/默认值/成对性 + 已删字段不得回归；
# ⑥ 无副作用（纯静态反射）。
"""公共请求字段合同（round9）：把 op×参数矩阵里"通用字段 GAP"用一条全量合同覆盖。

判据：
  * 每个 op 的 Request 必须接受 `step_details`（bool，默认 False）——C1 决策 2 的公共开关；
  * `log_level` / `log_max_bytes`（C2）必须**成对出现**，且 `basic.skill.execute` 必须两者都有；
  * 已按口径删除的字段不得回归：calibre 的 `power`/`ground`（P-092）、
    maestro export 的 `include_results`（P-084）、结果模型上的 `metadata`（C1 决策 3）。
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import fields as dataclass_fields, MISSING, is_dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def _all_operations() -> list[tuple[str, str, type]]:
    """返回 [(op_name, package_name, RequestClass)]，来自各包的 OPERATIONS 注册表。"""
    ops: list[tuple[str, str, type]] = []
    packages_dir = ROOT / "src" / "pyapi" / "packages"
    for path in sorted(packages_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = importlib.import_module(f"pyapi.packages.{path.stem}")
        for entry in getattr(module, "OPERATIONS", ()) or ():
            if len(entry) >= 3 and isinstance(entry[0], str) and isinstance(entry[2], type):
                ops.append((entry[0], path.stem, entry[2]))
    return ops


OPS = _all_operations()


def _fields(cls: type) -> dict[str, object] | None:
    """返回 {字段名: 默认值}；支持 dataclass 与 pydantic 两种 Request 形态。"""
    if is_dataclass(cls):
        return {
            f.name: (f.default if f.default is not MISSING else None)
            for f in dataclass_fields(cls)
        }
    model_fields = getattr(cls, "model_fields", None)
    if model_fields is not None:
        return {name: fi.default for name, fi in model_fields.items()}
    return None


def test_operations_registry_is_not_empty() -> None:
    assert len(OPS) >= 70, f"注册表异常：只解析到 {len(OPS)} 个 op"


@pytest.mark.parametrize("op,package,request_cls", OPS, ids=[f"{o}" for o, _, _ in OPS])
def test_step_details_field_present_with_false_default(op, package, request_cls) -> None:
    fields = _fields(request_cls)
    assert fields is not None, f"{op}: {request_cls.__name__} 既不是 dataclass 也不是 pydantic 模型"
    assert "step_details" in fields, f"{op}: {request_cls.__name__} 缺公共字段 step_details"
    assert fields["step_details"] is False, (
        f"{op}: step_details 默认值应为 False，实测 {fields['step_details']!r}")


def test_log_fields_are_paired() -> None:
    bad: list[str] = []
    for op, package, request_cls in OPS:
        fields = _fields(request_cls) or {}
        has_level = "log_level" in fields
        has_bytes = "log_max_bytes" in fields
        if has_level != has_bytes:
            bad.append(f"{op}（log_level={has_level}, log_max_bytes={has_bytes}）")
    assert not bad, f"log_level/log_max_bytes 必须成对：{bad}"


def test_skill_execute_has_log_fields() -> None:
    skill = [cls for op, _pkg, cls in OPS if op == "basic.skill.execute"]
    assert skill, "注册表里找不到 basic.skill.execute"
    fields = _fields(skill[0]) or {}
    assert "log_level" in fields and "log_max_bytes" in fields, (
        "basic.skill.execute 必须接受 log_level/log_max_bytes（C2）")
    # 可选语义：缺省必须是 None（"未给" 与 "显式给值" 必须可分）
    assert fields["log_level"] is None and fields["log_max_bytes"] is None, (
        f"log 字段缺省必须是 None，实测 {fields['log_level']!r}/{fields['log_max_bytes']!r}")


def test_skill_ops_have_log_fields() -> None:
    """C2：所有 skill 型 op 都应带 log 选项（当前口径：56 个）。"""
    skill_ops = [
        (op, cls) for op, _pkg, cls in OPS
        if "log_level" in (_fields(cls) or {})
    ]
    assert len(skill_ops) >= 50, (
        f"带 log_level 的 op 只有 {len(skill_ops)} 个，低于口径（≥50）："
        f"{[op for op, _ in skill_ops][:8]}…")
    missing_bytes = [op for op, cls in skill_ops if "log_max_bytes" not in (_fields(cls) or {})]
    assert not missing_bytes, f"这些 op 有 log_level 却缺 log_max_bytes：{missing_bytes}"


def test_removed_fields_do_not_come_back() -> None:
    """口径已删字段的负向合同（P-092 / P-084 / C1 决策 3）。"""
    offenders: list[str] = []
    for op, package, request_cls in OPS:
        fields = _fields(request_cls) or {}
        if package == "calibre" and ({"power", "ground"} & set(fields)):
            offenders.append(f"{op}: power/ground 回归")
        if op.startswith("virtuoso.maestro.export") and "include_results" in fields:
            offenders.append(f"{op}: include_results 回归")
    assert not offenders, f"已删字段回归：{offenders}"

    from pyapi import models as pyapi_models

    for cls_name in ("VirtuosoResult", "SimulationResult"):
        cls = getattr(pyapi_models, cls_name, None)
        if cls is None:
            continue
        assert "metadata" not in getattr(cls, "model_fields", {}), (
            f"{cls_name} 的 metadata 字段已按 C1 决策 3 删除，不得回归")
