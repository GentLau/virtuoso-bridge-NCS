"""Shared test credentials (spec r18+): role.key_dir/key must resolve to a
client-side private key plus a readable public key for fingerprinting.

Only the file *format* matters here: a dummy private key file and a
valid-looking ``<key>.pub`` are enough for registration-time probes.
"""
from __future__ import annotations

import base64
import itertools
import tempfile
from pathlib import Path

_counter = itertools.count(1)


def make_credential(name: str = "id_ed25519") -> tuple[str, str]:
    """Create ``<tmp>/<name>`` + ``<name>.pub`` and return ``(key_dir, key)``.

    Each call yields a *distinct* public key blob, so two calls model two
    different credentials; pass the same returned tuple to model reuse.
    """
    key_dir = Path(tempfile.mkdtemp(prefix="vb-key-"))
    (key_dir / name).write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\ndummy\n", encoding="utf-8"
    )
    blob = base64.b64encode(
        f"test-blob-{next(_counter)}".encode("utf-8")
    ).decode("ascii")
    (key_dir / f"{name}.pub").write_text(
        f"ssh-ed25519 {blob} test@local\n", encoding="utf-8"
    )
    return str(key_dir), name


def ssh_default(host: str = "server-a", user: str = "alice", **extra) -> dict:
    """One ``ssh.default`` mapping that satisfies the credential requirement."""
    key_dir, key = make_credential()
    values: dict = {"host": host, "user": user, "key_dir": key_dir, "key": key}
    values.update(extra)
    return values
