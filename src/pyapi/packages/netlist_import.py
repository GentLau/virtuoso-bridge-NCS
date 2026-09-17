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
        steps: list[dict[str, Any]] = []
        remote = f"imports/{request.job}/netlist.scs"

        up = self.middle.upload_file(
            Path(request.local_netlist), remote,
            timeout=request.timeout, token=request.token,
        )
        steps.append({"step": "upload", "ok": up.returncode == 0, "detail": up._asdict()})
        if up.returncode != 0:
            return Result(False, steps, up.stderr or "upload failed", remote)

        import_skill = (
            f'printf("import lib=%s cell=%s file=%s\\n" '
            f'"{request.library}" "{request.cell}" "{remote}")'
        )
        imported = self.middle.execute_skill(
            import_skill, timeout=request.timeout, token=request.token,
        )
        steps.append({"step": "import", "ok": imported.ok, "detail": imported.model_dump()})
        if not imported.ok:
            return Result(False, steps, "; ".join(imported.errors) or "import failed", remote)

        symbol_skill = (
            f'printf("symbol lib=%s cell=%s\\n" "{request.library}" "{request.cell}")'
        )
        symbol = self.middle.execute_skill(
            symbol_skill, timeout=request.timeout, token=request.token,
        )
        steps.append({"step": "symbol", "ok": symbol.ok, "detail": symbol.model_dump()})
        if not symbol.ok:
            return Result(False, steps, "; ".join(symbol.errors) or "symbol failed", remote)

        return Result(True, steps, None, remote)


# 自描述导出：操作名、Request、Result、Package（见 spec 上层 §4.2）
__all__ = ["OPERATION_NAME", "Package", "Request", "Result"]