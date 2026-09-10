from pathlib import Path
p=Path('src/transport/remote_paths.py')
t=p.read_text(encoding='utf-8')
new='''from __future__ import annotations

import posixpath

DEFAULT_SCRATCH_ROOT = "~/.virtuoso-bridge"


def scratch_root(root: str | None = None) -> str:
    value = root or DEFAULT_SCRATCH_ROOT
    if value.startswith("~"):
        from pathlib import Path
        value = str(Path(value).expanduser())
    return value.rstrip("/")


def token_dir(token: str, root: str | None = None) -> str:
    return posixpath.join(scratch_root(root), token)


def ramic_dir(token: str, root: str | None = None) -> str:
    return posixpath.join(token_dir(token, root), "ramic")


def setup_dir(token: str, root: str | None = None) -> str:
    return posixpath.join(token_dir(token, root), "setup")


def status_dir(token: str, root: str | None = None) -> str:
    return posixpath.join(token_dir(token, root), "status")


def daemon_path(token: str, python_major: int, root: str | None = None) -> str:
    name = "ramic_bridge_daemon_27.py" if python_major == 2 else "ramic_bridge_daemon_3.py"
    return posixpath.join(ramic_dir(token, root), name)


def il_path(token: str, root: str | None = None) -> str:
    return posixpath.join(ramic_dir(token, root), "ramic_bridge.il")


def setup_il_path(token: str, root: str | None = None) -> str:
    return posixpath.join(setup_dir(token, root), "virtuoso_setup.il")


def identity_path(token: str, root: str | None = None) -> str:
    return posixpath.join(status_dir(token, root), "daemon_identity.txt")


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
    "token_dir",
]
'''
p.write_text(new, encoding='utf-8')
print('remote_paths rewritten as POSIX strings')
