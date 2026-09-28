"""契约 TB：pyapi 接口面与中层 ``Middle`` 协议的调用形状必须一致（第五轮新增）。

背景：D2 修复（HEAD ``91e3e6d``，*fix(D2): VirtuosoInterface.execute_skill
补齐 log_level/log_max_bytes 可选参数*）改的是
``src/pyapi/models.py::VirtuosoInterface``，但仓库里没有任何用例引用这个
ABC（``rg VirtuosoInterface test/`` 只剩环境文档）→ 这条修复此前 **0 覆盖**，
下次再漏参数不会被任何门禁拦住。

本 TB 用 ``inspect.signature`` 把"上层接口 = 中层协议"的调用形状钉住：

* ``execute_skill`` 在两层同名、同序、同默认值（含 ``log_level``/``log_max_bytes``）；
* 五个业务接口 + ``query`` 的 ``token`` 都是 **必填 keyword-only**；
* 一个最小实现能通过形状检查（正例），而"少写一个日志参数"的近亲实现
  必须被拒（负控制，证明断言有鉴别力）。
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyapi.models import Middle, VirtuosoInterface, VirtuosoResult  # noqa: E402

#: 期望的 execute_skill 形状（含 D2 补上的两个日志参数）
EXECUTE_SKILL_PARAMS = ["self", "skill_code", "timeout", "token", "log_level", "log_max_bytes"]
EXECUTE_SKILL_DEFAULTS = {"timeout": None, "log_level": None, "log_max_bytes": None}


def _shape_ok(func) -> bool:
    """按"名字 + 顺序 + 默认值"判一个 execute_skill 是否合形。"""
    sig = inspect.signature(func)
    if list(sig.parameters) != EXECUTE_SKILL_PARAMS:
        return False
    return all(sig.parameters[name].default == default
               for name, default in EXECUTE_SKILL_DEFAULTS.items())


def test_execute_skill_shape_matches_between_pyapi_and_middle():
    for owner in (VirtuosoInterface, Middle):
        params = list(inspect.signature(owner.execute_skill).parameters)
        assert params == EXECUTE_SKILL_PARAMS, (owner, params)
        assert _shape_ok(owner.execute_skill), owner


def test_token_is_required_keyword_only_on_every_business_interface():
    for name in ("execute_skill", "run_command", "upload_file", "download_file",
                 "run_gui_command", "run_spectre_command", "query"):
        param = inspect.signature(getattr(Middle, name)).parameters["token"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert param.default is inspect.Parameter.empty, name


def test_log_params_are_keyword_only_optional():
    sig = inspect.signature(VirtuosoInterface.execute_skill)
    for name in ("log_level", "log_max_bytes"):
        param = sig.parameters[name]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert param.default is None, name


def test_abstract_interface_cannot_instantiate_but_minimal_impl_can():
    with pytest.raises(TypeError):
        VirtuosoInterface()  # 负控制：ABC 不可直接实例化

    class Impl(VirtuosoInterface):
        def ensure_ready(self, timeout: int = 10) -> VirtuosoResult:
            raise NotImplementedError

        def execute_skill(self, skill_code: str, timeout: float | None = None, *,
                          token: str, log_level: str | None = None,
                          log_max_bytes: int | None = None) -> VirtuosoResult:
            raise NotImplementedError

        def test_connection(self, timeout: int = 10) -> bool:
            return False

    impl = Impl()
    assert isinstance(impl, VirtuosoInterface)
    # 用未绑定的类函数做形状检查（绑定方法会省略 self 参数）
    assert _shape_ok(Impl.execute_skill)


def test_near_miss_signature_is_rejected_by_the_shape_check():
    """负控制：少了 ``log_max_bytes`` 的实现必须判不合形。"""

    class NearMiss:
        def execute_skill(self, skill_code, timeout=None, *, token,
                          log_level=None):  # 少了 log_max_bytes
            ...

    class AlsoNearMiss:
        # 参数齐但默认值漂了（timeout 默认 30 而非 None）
        def execute_skill(self, skill_code, timeout=30, *, token,
                          log_level=None, log_max_bytes=None):
            ...

    assert not _shape_ok(NearMiss.execute_skill)
    assert not _shape_ok(AlsoNearMiss.execute_skill)
