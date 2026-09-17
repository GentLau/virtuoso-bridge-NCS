"""进程级本机路径基座（基底模块，四层共享）。

纪律：

1. **只初始化一次**：入口调用 ``init_work_dir()``；同一路径重复调用幂等，
   不同路径报错（测试用 ``init_work_dir(..., force=True)`` 或
   ``override_work_dir_for_tests()``）。
2. **只读**：对外只有 ``work_root()/temp_dir()/log_dir()/artifact_dir()/...``，
   没有通用 setter。
3. **中立**：本模块不 import 任何业务层。
4. **只放进程级**：请求级子目录、当前用户/token、远端路径一律不进这里。

子结构（惰性创建）::

    <work_root>/
      registry.json
      server.json
      temp/
      log/commands.log
      artifact/
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_APP_NAME = "virtuoso_bridge"

_lock = threading.Lock()
_work_root: Path | None = None


def default_work_dir() -> Path:
    """平台默认工作根（仅入口在缺 ``--work-dir`` 时使用）。"""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / _APP_NAME


def init_work_dir(path: str | Path | None = None, *, force: bool = False) -> Path:
    """Bind the process-wide work root (the entry point calls this once).

    ``path=None`` -> :func:`default_work_dir`.  The same path may be initialized
    again (control face + business face in one process); a *different* path is a
    programming error unless ``force=True`` (tests/tools).
    """
    global _work_root
    resolved = (
        Path(path).expanduser().resolve() if path is not None else default_work_dir()
    )
    with _lock:
        if _work_root is not None and not force:
            if _work_root == resolved:
                return _work_root
            raise RuntimeError(
                f"work dir already initialized: {_work_root} (requested {resolved})"
            )
        resolved.mkdir(parents=True, exist_ok=True)
        _work_root = resolved
        return _work_root


def override_work_dir_for_tests(path: str | Path) -> Path:
    """Test/tool only: switch the work root (production never calls this)."""
    return init_work_dir(path, force=True)


def reset_work_dir() -> None:
    """Test only: forget the current binding so the next ``init`` can set it."""
    global _work_root
    with _lock:
        _work_root = None


def work_root() -> Path:
    if _work_root is None:
        raise RuntimeError(
            "work dir not initialized: the entry point must call init_work_dir()"
        )
    return _work_root


def sub_dir(name: str) -> Path:
    path = work_root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_dir() -> Path:
    return sub_dir("temp")


def log_dir() -> Path:
    return sub_dir("log")


def artifact_dir() -> Path:
    return sub_dir("artifact")


def registry_path() -> Path:
    return work_root() / "registry.json"


def server_config_path() -> Path:
    return work_root() / "server.json"


def command_log_file() -> Path:
    return log_dir() / "commands.log"


__all__ = [
    "artifact_dir",
    "command_log_file",
    "default_work_dir",
    "init_work_dir",
    "log_dir",
    "override_work_dir_for_tests",
    "registry_path",
    "reset_work_dir",
    "server_config_path",
    "sub_dir",
    "temp_dir",
    "work_root",
]
