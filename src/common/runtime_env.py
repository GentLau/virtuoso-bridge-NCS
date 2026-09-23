"""Client runtime environment guard (spec r17: client Python >= 3.9).

Warn-only on purpose: an older interpreter may still start and get far, so
this must not refuse to run; it prints one warning naming the unmet
requirement so the user knows the remaining behaviour is unspecified.
"""
from __future__ import annotations

import sys

MIN_CLIENT_PYTHON: tuple[int, int] = (3, 9)

_warned = False


def warn_if_client_python_unsupported() -> str | None:
    """Emit one warning (per process) when this client Python is too old.

    Returns the warning text when it was printed, ``None`` otherwise.
    """
    global _warned
    if sys.version_info[:2] >= MIN_CLIENT_PYTHON or _warned:
        return None
    _warned = True
    major, minor = sys.version_info[:2]
    text = (
        f"warning: Python {major}.{minor} "
        f"does not satisfy the client requirement (>= 3.9); behaviour is "
        "unspecified and may fail in unexpected places"
    )
    print(text, file=sys.stderr)
    return text
