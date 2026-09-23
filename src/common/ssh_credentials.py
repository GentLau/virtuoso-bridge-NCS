"""Client-side SSH credential resolution and public-key fingerprints.

Spec r18–r22（中层配置文档 §2.3/§2.5/§5）:

* 凭据是 ``key_dir`` + ``key``，位于**客户端侧**；role 级字段缺省回退
  ``ssh.default.*``，``key_dir`` 再缺省 = 客户端 ``~/.ssh``；
* ``key`` 只允许文件名；remote role 必须能解析出凭据；
* 凭据按**公钥指纹**查重（本模块提供 OpenSSH 风格 ``SHA256:<base64>``）。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path

#: `key_dir` 的最终缺省：客户端本机 ``~/.ssh``（spec §2.5）。
DEFAULT_KEY_DIR = "~/.ssh"

_PUBLIC_KEY_PREFIXES = ("ssh-", "ecdsa-", "sk-ssh-", "sk-ecdsa-")


def resolve_credential(
    key_dir: str | None,
    key: str | None,
    *,
    default_key_dir: str | None = None,
    default_key: str | None = None,
) -> tuple[str, str] | None:
    """Role-level credential with fallback to the global default.

    Returns ``(key_dir, key)`` or ``None`` when no key resolves at all.
    """
    resolved_key = key or default_key
    if not resolved_key:
        return None
    return (key_dir or default_key_dir or DEFAULT_KEY_DIR, resolved_key)


def credential_path(key_dir: str, key: str) -> Path:
    return Path(key_dir).expanduser() / key


def credential_identity(key_dir: str, key: str) -> str:
    """Human-readable identifier used by ``user remove`` reporting."""
    return str(credential_path(key_dir, key))


def _fingerprint_from_text(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(_PUBLIC_KEY_PREFIXES):
            try:
                blob = base64.b64decode(parts[1], validate=True)
            except (binascii.Error, ValueError):
                return None
            digest = hashlib.sha256(blob).digest()
            return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")
    return None


def public_key_fingerprint(key_dir: str, key: str) -> str | None:
    """OpenSSH-style fingerprint of the credential's public key.

    Prefers ``<key>.pub`` next to the private key and falls back to the key
    file itself when it already holds a public key.  Returns ``None`` when
    neither file can be read as a public key.
    """
    path = credential_path(key_dir, key)
    for candidate in (path.with_name(path.name + ".pub"), path):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fingerprint = _fingerprint_from_text(text)
        if fingerprint:
            return fingerprint
    return None


__all__ = [
    "DEFAULT_KEY_DIR",
    "credential_identity",
    "credential_path",
    "public_key_fingerprint",
    "resolve_credential",
]
