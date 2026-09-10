"""Local working directory policy.

The bridge is started with a working directory (or falls back to the platform
config directory).  Every local file operation lives under it and the child
structure is fixed:

    <work_dir>/
      registry.json
      temp/
      log/
      artifact/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_NAME = "virtuoso_bridge"

_work_dir: Path | None = None


def default_working_dir() -> Path:
    """Platform config directory, matching the legacy ``config_dir()`` default."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / _APP_NAME


def set_working_dir(path: str | Path | None) -> Path:
    """Bind the local working directory (startup input)."""
    global _work_dir
    _work_dir = Path(path).expanduser().resolve() if path is not None else default_working_dir()
    _work_dir.mkdir(parents=True, exist_ok=True)
    return _work_dir


def working_dir() -> Path:
    return _work_dir or default_working_dir()


def sub_dir(name: str) -> Path:
    path = working_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def registry_path() -> Path:
    return working_dir() / "registry.json"


def temp_dir() -> Path:
    return sub_dir("temp")


def log_dir() -> Path:
    return sub_dir("log")


def artifact_dir() -> Path:
    return sub_dir("artifact")


def command_log_file() -> Path:
    return log_dir() / "commands.log"


__all__ = [
    "artifact_dir",
    "command_log_file",
    "default_working_dir",
    "log_dir",
    "registry_path",
    "set_working_dir",
    "sub_dir",
    "temp_dir",
    "working_dir",
]
