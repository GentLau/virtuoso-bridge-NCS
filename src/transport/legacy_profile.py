"""Legacy profile resolution adapter.

Profile is replaced by ``user``; this only exists to migrate old scripts that
pass ``profile=...`` / rely on ``VB_PROFILE``.
"""

from __future__ import annotations

import os


def resolve_legacy_profile(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    value = os.environ.get("VB_PROFILE", "").strip()
    return value or None


__all__ = ["resolve_legacy_profile"]
