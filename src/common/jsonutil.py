"""Strict JSON helpers shared by the HTTP faces.

Python's stock JSON parser accepts ``NaN``/``Infinity`` extensions and can
raise implementation exceptions (``ValueError`` for oversized integer
literals, ``RecursionError`` for deeply nested documents).  The HTTP faces
must translate all of those into a normal 4xx response instead of dropping the
connection.
"""

from __future__ import annotations

import json
import math
from typing import Any


def _parse_finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number is not valid")
    return value


def _reject_constant(text: str) -> None:
    raise ValueError(f"invalid JSON constant: {text}")


def loads_strict(text: str) -> Any:
    """Parse standard JSON, rejecting non-finite numbers and constants."""
    return json.loads(
        text,
        parse_float=_parse_finite_float,
        parse_constant=_reject_constant,
    )


__all__ = ["loads_strict"]
