"""Deprecated internal import shim; the implementation lives in roles.py."""
from transport.roles import (
    ResolvedRole,
    ResolvedTargets,
    fingerprint_conflicts,
    resolve,
)

__all__ = ["ResolvedRole", "ResolvedTargets", "fingerprint_conflicts", "resolve"]
