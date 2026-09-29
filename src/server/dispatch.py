"""Top-layer dispatch: explicit operation registry + response shell.

Spec: ``spec/design-concepts/顶层/1-顶层.md`` (top layer) and
``spec/design-concepts/上层/1-上层.md`` (business packages).

This module is deliberately free of ``transport.*`` / ``socket`` / ``subprocess``
imports: the ``Middle`` object is injected by the process assembly
(``server.api_server``), and the dispatch chain only talks to ``pyapi``.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from pyapi.models import Middle

#: ``operation -> OperationSpec``; duplicated names are a startup error (§2.1).
PACKAGES: dict[str, "OperationSpec"] = {}

#: Packages that failed to load (spec 上层 §4.3: they only disable themselves).
#: Filled by the process assembly (``server.api_server``).
PACKAGE_LOAD_ERRORS: dict[str, str] = {}


@dataclass(frozen=True)
class OperationSpec:
    package: type
    method: str
    request_model: Callable[..., Any]


class DispatchError(Exception):
    """Structural failure: malformed body, unknown operation, bad Request."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def register_operation(
    operation: str,
    package: type,
    method: str,
    request_model: Callable[..., Any],
    *,
    replace: bool = False,
) -> None:
    if not isinstance(operation, str) or not operation:
        raise ValueError("operation must be a non-empty dotted name")
    if operation in PACKAGES and not replace:
        raise ValueError(f"operation {operation!r} is already registered")
    PACKAGES[operation] = OperationSpec(package, method, request_model)


def jsonable(value: Any) -> Any:
    """Convert package results into JSON-safe data (顶层不解释业务)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump") and callable(value.model_dump):  # pydantic
        return jsonable(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: jsonable(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if isinstance(value, BaseException):
        return str(value)
    return str(value)


def build_request(spec: OperationSpec, payload: Mapping[str, Any], token: str) -> Any:
    fields = {key: value for key, value in payload.items() if key != "operation"}
    fields["token"] = token
    try:
        return spec.request_model(**fields)
    except TypeError as exc:
        raise DispatchError(f"invalid request for operation: {exc}") from exc
    except ValueError as exc:
        raise DispatchError(f"invalid request for operation: {exc}") from exc


def dispatch(middle: Middle, payload: Mapping[str, Any]) -> tuple[int, Any]:
    """Run one operation and return ``(http_status, body)`` per 顶层 §3.

    业务包构造只接收 ``Middle``（顶层 §2.4 / 上层 §2.2 的唯一口径）。
    """
    if not isinstance(payload, Mapping):
        return 400, {"ok": False, "error": "request body must be an object"}

    operation = payload.get("operation")
    if not isinstance(operation, str) or not operation:
        return 400, {"ok": False, "error": "operation is required"}

    token = payload.get("token")
    if not isinstance(token, str) or not token:
        return 400, {"ok": False, "error": "token is required"}

    spec = PACKAGES.get(operation)
    if spec is None:
        return 404, {"ok": False, "error": f"unknown operation: {operation}"}

    try:
        request = build_request(spec, payload, token)
    except DispatchError as exc:
        return exc.status, {"ok": False, "error": str(exc)}

    try:
        package = spec.package(middle)
        method = getattr(package, spec.method)
        result = method(request)
    except (TypeError, ValueError) as exc:
        # 上层 §3.3: structural/domain validation raises -> 4xx, not 5xx
        return 400, {"ok": False, "error": f"invalid request: {exc}"}
    except Exception as exc:  # noqa: BLE001 - unexpected: 5xx, no stack trace
        return 500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # 业务包可达：成功/业务失败都直接返回业务 Result 本体，顶层不解释。
    return 200, jsonable(result)


def operations() -> list[str]:
    return sorted(PACKAGES)


__all__ = [
    "DispatchError",
    "OperationSpec",
    "PACKAGE_LOAD_ERRORS",
    "PACKAGES",
    "build_request",
    "dispatch",
    "jsonable",
    "operations",
    "register_operation",
]
