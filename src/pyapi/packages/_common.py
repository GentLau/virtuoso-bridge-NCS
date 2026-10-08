"""包内共享小工具（P-130 收敛）。

上层各包此前各自复制了 ``_step`` 与通用 ``_require_*`` 校验；这里只保留
一份实现，按既有（已被各包离线契约测试钉住的）语义分档导出：

* ``_step``：9 个包（cellview/gui/layout/maestro/schematic/spectre/symbol/
  verilog/veriloga）同一实现；
* ``_require_text``：空串拒绝、**空白串接受**（basic/cellview/maestro/
  schematic/symbol 与 gui 的既有语义）；
* ``_require_nonblank_text``：空白串也拒绝（calibre/layout/skillref/
  spectre/verilog/veriloga 的既有语义），各包以 ``as _require_text`` 别名导入
  以保持包内调用点不变；
* ``_require_timeout``：严口径（bool 拒绝、必须有限正数）——原
  basic/skillref/spectre 的实现；其余包原有的宽松版对合法输入行为一致，
  仅收紧畸形输入（``True``/``inf``/``nan``）；
* ``_require_bool``：返回布尔值（合法的 ``True/False`` 原样返回）；
* ``_require_token``：basic/calibre/skillref 同一实现。

行为约束（P-130）：收敛不改各包对**合法输入**的行为；畸形输入的校验
口径按上述分档统一。
"""
from __future__ import annotations

import math
from typing import Any


def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _require_token(token: Any) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    return token


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_nonblank_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(timeout: Any) -> None:
    if timeout is None:
        return
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout must be a positive finite number or None")


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value
