from __future__ import annotations

import posixpath

DEFAULT_SCRATCH_ROOT = "~/.virtuoso-bridge"


def scratch_root(root: str | None = None) -> str:
    value = root or DEFAULT_SCRATCH_ROOT
    if value.startswith("~"):
        from pathlib import Path
        value = str(Path(value).expanduser())
    return value.rstrip("/")


def _valid_user_segment(user: str) -> None:
    if (
        not user
        or user.startswith(("/", "\\"))
        or "/" in user
        or "\\" in user
        or ".." in user
    ):
        raise ValueError(f"user must be a single path segment: {user!r}")


def user_dir(user: str, root: str | None = None) -> str:
    """Return the single per-user bridge work directory.

    ``root`` is already ``deploy.scratch_root``, i.e. the per-user directory
    (``~/.virtuoso-bridge/<user>``); no user segment is appended here.  The
    username is still validated for containment.
    """
    _valid_user_segment(user)
    return scratch_root(root)


def ramic_dir(user: str, root: str | None = None) -> str:
    return posixpath.join(user_dir(user, root), "ramic")


def setup_dir(user: str, root: str | None = None) -> str:
    return posixpath.join(user_dir(user, root), "setup")


def status_dir(user: str, root: str | None = None) -> str:
    return posixpath.join(user_dir(user, root), "status")


def daemon_path(user: str, python_major: int, root: str | None = None) -> str:
    name = "ramic_bridge_daemon_27.py" if python_major == 2 else "ramic_bridge_daemon_3.py"
    return posixpath.join(ramic_dir(user, root), name)


def il_path(user: str, root: str | None = None) -> str:
    return posixpath.join(ramic_dir(user, root), "ramic_bridge.il")


def setup_il_path(user: str, root: str | None = None) -> str:
    return posixpath.join(setup_dir(user, root), "virtuoso_setup.il")


def identity_path(user: str, root: str | None = None) -> str:
    return posixpath.join(status_dir(user, root), "daemon_identity.txt")


__all__ = [
    "DEFAULT_SCRATCH_ROOT",
    "daemon_path",
    "identity_path",
    "il_path",
    "ramic_dir",
    "scratch_root",
    "setup_dir",
    "setup_il_path",
    "status_dir",
    "user_dir",
]
