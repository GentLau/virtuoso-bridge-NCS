"""典型业务包示例：导入网表。

对外一个动作 ``virtuoso.netlist.import``，内部三步：
上传网表 → Skill 导入 → Skill 建 symbol。

按 ``spec/design-concepts/上层/1-上层.md`` 的最小契约实现，用于测试插件形态。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyapi.models import Middle

OPERATION_NAME = "virtuoso.netlist.import"


@dataclass(frozen=True)
class Request:
    token: str
    local_netlist: str
    library: str
    cell: str
    job: str
    timeout: float | None = None


@dataclass
class Result:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    remote_netlist: str = ""


def _validate(request: Request) -> None:
    for name in ("token", "library", "cell", "job"):
        value = getattr(request, name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
    if not request.local_netlist:
        raise ValueError("local_netlist must be a non-empty path")
    if request.timeout is not None and request.timeout <= 0:
        raise ValueError("timeout must be positive or None")


#: spec 上层 §4.2: operation metadata for the top-layer registry
OPERATIONS = ((OPERATION_NAME, "run", Request, Result),)


class Package:
    """参考实现：只调中层五接口，失败即停并保留步骤痕迹。"""

    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def run(self, request: Request) -> Result:
        _validate(request)
        # 参考实现不落任何 cell/view/symbol：不得伪造成功。
        return Result(
            False, [],
            "virtuoso.netlist.import is a reference stub: "
            "no cell/view/symbol is created",
        )


# 自描述导出：操作名、Request、Result、Package（见 spec 上层 §4.2）
__all__ = ["OPERATION_NAME", "Package", "Request", "Result"]
