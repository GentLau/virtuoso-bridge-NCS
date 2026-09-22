"""Input validation shared by registration and registry models."""
from __future__ import annotations

import re

USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
DISPLAY_RE = re.compile(r"^[A-Za-z0-9._/-]*:[0-9]+(\.[0-9]+)?$")
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


__all__ = [
    "DISPLAY_RE",
    "TOKEN_RE",
    "USER_RE",
    "validate_display",
    "validate_token",
    "validate_user_name",
]
