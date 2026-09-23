"""Input validation shared by registration and registry models."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping

USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
DISPLAY_RE = re.compile(r"^[A-Za-z0-9._/-]*:[0-9]+(\.[0-9]+)?$")
ROLE_GROUP_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ROLE_GROUP_MAX_BYTES = 16 * 1024
ROLE_FIXED_FIELDS = frozenset({
    "mode", "host", "user", "jump_host", "jump_user", "proxy",
    "key_dir", "key",
    "root", "expected_fingerprint", "max_sessions",
    "daemon_port", "local_port", "python", "expected_hostname",
    "expected_user", "display", "bin",
})
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def validate_user_name(value: str) -> str:
    """Validate the user id used as a registry key and path segment."""
    value = str(value or "")
    if not USER_RE.fullmatch(value):
        raise ValueError("user format is invalid")
    if value.endswith((".", " ")) or ".." in value:
        raise ValueError("user may not contain '..' or end with '.' or space")
    stem = value.split(".", 1)[0].upper()
    if stem in _RESERVED:
        raise ValueError(f"user {value!r} is a reserved device name")
    return value


def validate_token(value: str) -> str:
    """Validate the opaque symmetric bearer ticket."""
    value = str(value or "")
    if not TOKEN_RE.fullmatch(value):
        raise ValueError("token format is invalid")
    return value


def validate_key_name(value: str) -> str:
    """Validate ``role.*.key``: a file name only, never a path (spec §5)."""
    text = str(value or "")
    if not text or text in (".", ".."):
        raise ValueError("key must be a file name")
    if "/" in text or "\\" in text or "\x00" in text:
        raise ValueError("key must be a file name without directory components")
    return text


def validate_display(value: str | None) -> str | None:
    """Validate an X11 display value used as ``DISPLAY``.

    Empty strings are treated as "not provided"; shell metacharacters are
    rejected so the value can be safely embedded in a command.
    """
    if value is None:
        return None
    text = str(value)
    if not text or not text.strip():
        return None
    if text != text.strip():
        raise ValueError("display must not contain surrounding whitespace")
    if len(text) > 256 or not DISPLAY_RE.fullmatch(text):
        raise ValueError("display must look like ':11', 'localhost:10.0', or 'unix/:0'")
    return text


def _validate_group_scalar(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("role user group values must be finite JSON numbers")
        return
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("role user group strings must not contain NUL")
        return
    raise ValueError(
        "role user group values must be JSON scalars "
        "(string/number/boolean/null)"
    )


def validate_role_groups(
    extras: Mapping[str, Any] | None,
    *,
    reserved: set[str],
) -> None:
    """Validate the per-role user-group extension envelope (配置文档 §2.3).

    The middle layer deliberately does not interpret group contents.  It only
    enforces the schema boundary: a valid group name, an object value containing
    scalar fields only, no NUL bytes, and a 16 KiB per-role limit.
    """
    if not extras:
        return

    total = 0
    for name, value in extras.items():
        if not isinstance(name, str) or not ROLE_GROUP_NAME_RE.fullmatch(name):
            raise ValueError(
                f"role user group name is invalid: {name!r} "
                "(expected ^[a-z][a-z0-9_-]{0,63}$)"
            )
        if name in reserved:
            raise ValueError(f"role user group name conflicts with fixed field: {name}")
        if not isinstance(value, dict):
            raise ValueError(f"role user group {name!r} must be an object")

        for key, item in value.items():
            if not isinstance(key, str) or not key or "\x00" in key:
                raise ValueError(
                    f"role user group {name!r} contains an invalid field name"
                )
            _validate_group_scalar(item)

        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        total += len(encoded)
        if total > ROLE_GROUP_MAX_BYTES:
            raise ValueError(
                f"role user groups exceed {ROLE_GROUP_MAX_BYTES} bytes"
            )


__all__ = [
    "DISPLAY_RE",
    "ROLE_GROUP_MAX_BYTES",
    "ROLE_GROUP_NAME_RE",
    "ROLE_FIXED_FIELDS",
    "TOKEN_RE",
    "USER_RE",
    "validate_display",
    "validate_key_name",
    "validate_role_groups",
    "validate_token",
    "validate_user_name",
]
