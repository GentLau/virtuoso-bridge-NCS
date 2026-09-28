# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =======================================================================
"""`timeout` 参数的统一合同（op×param 矩阵里 38 条 GAP 的同一字段家族）。

逐条"传一次 timeout"没有额外信息量，但**逐个 op 断言非法 timeout 一定被拒（4xx）**
有意义：它能抓出"某个 op 声明了 timeout 却不校验"。

做法：从 `src/pyapi/packages/*.py` 的 `OPERATIONS` 表自动枚举 op 与请求模型，
按字段注解合成最小 payload，再走**真实入口** `server.dispatch.dispatch()`，
middle 用"宽容替身"（所有调用返回成功桩）——于是：

  * `timeout=0`（非法）必须得到 400（参数编程错误）；
  * 若某 op 返回 200，说明它**收下了非法 timeout**（缺陷候选，本用例失败）；
  * 若某 op 返回 500，说明替身桩形状不匹配，记入 `unresolved` 供人工复核（不算失败）。

第 1 步（环境检查）：离线用例，不需要真机环境检查。
第 3 步（构建前置）：自动枚举 + 合成 payload，见 setUpClass。
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
import typing
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "test" / "shared" / "runners"))

import build_op_param_matrix as matrix  # noqa: E402
from pyapi.models import CommandResult, ExecutionStatus, QueryResult, VirtuosoResult  # noqa: E402
from server import dispatch as dispatch_module  # noqa: E402

PACKAGE_DIR = ROOT / "src" / "pyapi" / "packages"
EVIDENCE = ROOT / "test" / "artifacts" / "evidence" / "round8" / "timeout-contract.json"


class _PermissiveMiddle:
    """所有业务方法都返回成功桩；属性访问不抛错。"""

    def query(self, **_kwargs):
        return QueryResult(status=ExecutionStatus.SUCCESS)

    def execute_skill(self, *_args, **_kwargs):
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="3")

    def run_command(self, *_args, **_kwargs):
        return CommandResult(returncode=0, stdout="", stderr="", kind="command")

    def upload_file(self, *_args, **_kwargs):
        return CommandResult(returncode=0, stdout="", stderr="", kind="command")

    def download_file(self, *_args, **_kwargs):
        return CommandResult(returncode=0, stdout="", stderr="", kind="command")

    def run_gui_command(self, *_args, **_kwargs):
        return CommandResult(returncode=0, stdout="", stderr="", kind="command")

    def run_spectre_command(self, *_args, **_kwargs):
        return CommandResult(returncode=0, stdout="", stderr="", kind="command")

    def close(self):
        return None

    def __getattr__(self, name):  # 其它方法一律当成"返回成功桩的可调用"
        def _stub(*_args, **_kwargs):
            return CommandResult(returncode=0, stdout="", stderr="", kind="command")
        return _stub


def _sample_for(annotation: object, name: str):
    # 注意：包源码用 `from __future__ import annotations` + `X | None` 写法，
    # 在 py3.9 上 `typing.get_type_hints()` 会去求值字符串注解 → TypeError。
    # 因此这里对**字符串注解**做文本判定，不调用 get_type_hints（Linux py3.9 实测）。
    if isinstance(annotation, str):
        text = annotation.strip()
        base = text.split("|")[0].strip()
        if base.startswith(("list[", "List[")):
            return []
        if base.startswith(("dict[", "Dict[")):
            return {}
        if base in ("str", "Any") or base.startswith(("Literal[", "Optional[str]")):
            return "1+2" if name in ("skill_code", "skill") else "x"
        if base == "int":
            return 1
        if base == "float":
            return 1.0
        if base == "bool":
            return True
        return None
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Union:
        inner = [a for a in args if a is not type(None)]
        return _sample_for(inner[0], name) if len(inner) == 1 else None
    if origin in (list, typing.List):
        inner = _sample_for(args[0], name) if args else "x"
        return [] if inner is None else [inner]
    if origin in (dict, typing.Dict):
        return {}
    if annotation is str:
        return "1+2" if name in ("skill_code", "skill") else "x"
    if annotation is int:
        return 1
    if annotation is float:
        return 1.0
    if annotation is bool:
        return True
    return None


def _payload_for(model) -> dict | None:
    payload: dict = {}
    if dataclasses.is_dataclass(model):
        for field in dataclasses.fields(model):
            if field.name == "timeout":
                continue
            if (field.default is not dataclasses.MISSING
                    or field.default_factory is not dataclasses.MISSING):
                continue
            value = _sample_for(field.type, field.name)
            if value is None:
                return None
            payload[field.name] = value
        return payload
    for name, meta in (getattr(model, "model_fields", {}) or {}).items():
        if name == "timeout" or not meta.is_required():
            continue
        value = _sample_for(meta.annotation, name)
        if value is None:
            return None
        payload[name] = value
    return payload


def _load_ops() -> dict[str, dict]:
    modules = {
        path.stem: importlib.import_module(f"pyapi.packages.{path.stem}")
        for path in sorted(PACKAGE_DIR.glob("*.py")) if not path.stem.startswith("_")
    }
    ops = {}
    for op, info in matrix.load_operations().items():
        module = modules.get(Path(info["package"]).stem)
        model = getattr(module, info["model"], None) if module else None
        if model is not None:
            ops[op] = {"model": model, "method": info["method"]}
    return ops


class TestTimeoutContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server.api_server import register_packages  # noqa: PLC0415
        register_packages()
        cls.ops = _load_ops()
        cls.declared = sorted(op for op, i in cls.ops.items()
                              if "timeout" in _field_names(i["model"]))
        cls.accepted = []      # 收下非法 timeout（失败）
        cls.rejected = []      # 400（期望）
        cls.unresolved = []    # 500 / 无法构造
        for op in cls.declared:
            info = cls.ops[op]
            payload = _payload_for(info["model"])
            if payload is None:
                cls.unresolved.append((op, "payload-synthesis"))
                continue
            payload.update({"operation": op, "token": "t-timeout", "timeout": 0})
            status, body = dispatch_module.dispatch(_PermissiveMiddle(), payload)
            if status == 400:
                cls.rejected.append(op)
            elif status == 200:
                cls.accepted.append((op, body.get("error")))
            else:
                cls.unresolved.append((op, f"{status}: {str(body.get('error'))[:80]}"))
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps({
            "declared_timeout_ops": len(cls.declared),
            "rejected_400": sorted(cls.rejected),
            "accepted_invalid_200": sorted(op for op, _ in cls.accepted),
            "unresolved": [{"op": op, "why": why} for op, why in cls.unresolved],
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    def test_ops_declaring_timeout_are_enumerated(self):
        self.assertGreaterEqual(len(self.declared), 38,
                                f"声明 timeout 的 op 少于矩阵口径：{len(self.declared)}")

    def test_invalid_timeout_never_accepted(self):
        self.assertEqual([], self.accepted,
                         f"这些 op 收下了非法 timeout=0（必须 400）：{self.accepted[:5]}")

    def test_majority_rejected_and_unresolved_recorded(self):
        total = len(self.rejected) + len(self.accepted) + len(self.unresolved)
        self.assertEqual(len(self.declared), total)
        self.assertGreaterEqual(len(self.rejected), int(len(self.declared) * 0.6),
                                f"可判定的 op 太少：rejected={len(self.rejected)} "
                                f"unresolved={len(self.unresolved)}")


def _field_names(model) -> set[str]:
    if dataclasses.is_dataclass(model):
        return {field.name for field in dataclasses.fields(model)}
    return set(getattr(model, "model_fields", {}) or {})


if __name__ == "__main__":
    unittest.main()
