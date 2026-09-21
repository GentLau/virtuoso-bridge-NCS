"""Process-level read-only config data.

Same nature as :mod:`common.paths`: all layers may read the process snapshot;
the control plane is the only writer.  This module intentionally knows no
section semantics (for example, it does not validate the ``skillref`` shape).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from common.paths import config_path

_snapshot_path: Path | None = None
_snapshot: Mapping[str, Any] | None = None


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def _resolve(path: Path | str | None) -> Path:
    return Path(path or config_path()).expanduser().resolve()


def load_config_file(path: Path | str) -> dict[str, Any]:
    """Read one config file.  Missing/invalid/non-object files mean ``{}``."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def init_config(path: Path | str | None = None) -> Mapping[str, Any]:
    """Import the process-wide snapshot exactly once."""
    global _snapshot_path, _snapshot
    resolved = _resolve(path)
    if _snapshot is not None:
        if _snapshot_path == resolved:
            return _snapshot
        raise RuntimeError("config already initialized for a different work dir")
    _snapshot_path = resolved
    _snapshot = _freeze(load_config_file(resolved))
    return _snapshot


def reload_config(path: Path | str | None = None) -> Mapping[str, Any]:
    """Explicitly re-import the snapshot (admin reload/restart only)."""
    global _snapshot_path, _snapshot
    resolved = _resolve(path if path is not None else _snapshot_path)
    _snapshot_path = resolved
    _snapshot = _freeze(load_config_file(resolved))
    return _snapshot


def replace_snapshot(
    config: Mapping[str, Any], *, path: Path | str | None = None
) -> Mapping[str, Any]:
    """Replace the in-memory snapshot without file IO (control-plane writer)."""
    global _snapshot_path, _snapshot
    if path is not None:
        _snapshot_path = _resolve(path)
    elif _snapshot_path is None:
        _snapshot_path = _resolve(None)
    _snapshot = _freeze(copy.deepcopy(dict(config)))
    return _snapshot


def snapshot() -> Mapping[str, Any]:
    """Return the frozen process snapshot; an uninitialized snapshot is empty."""
    return _snapshot if _snapshot is not None else MappingProxyType({})


def snapshot_dict() -> dict[str, Any]:
    """Return a plain mutable copy (for JSON responses/tests)."""
    return _thaw(snapshot())


def value(key: str, default: Any = None) -> Any:
    return snapshot().get(key, default)


def section(name: str) -> Mapping[str, Any] | None:
    value_ = snapshot().get(name)
    return value_ if isinstance(value_, Mapping) else None


__all__ = [
    "init_config",
    "load_config_file",
    "reload_config",
    "replace_snapshot",
    "section",
    "snapshot",
    "snapshot_dict",
    "value",
]
