"""客户端 SSH 凭据解析与公钥指纹（spec r18–r22，中层配置文档 §2.3/§2.5/§5）。"""

from __future__ import annotations

import base64
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common import ssh_credentials as cred


class TestResolveCredential(unittest.TestCase):
    def test_role_level_overrides_default(self):
        self.assertEqual(
            cred.resolve_credential(
                "/role/.ssh", "role_key", default_key_dir="/default", default_key="d"
            ),
            ("/role/.ssh", "role_key"),
        )

    def test_key_dir_falls_back_to_default_then_home_ssh(self):
        self.assertEqual(
            cred.resolve_credential(None, "k", default_key_dir="/d")[0], "/d"
        )
        self.assertEqual(
            cred.resolve_credential(None, "k")[0], cred.DEFAULT_KEY_DIR
        )

    def test_no_key_resolves_to_none(self):
        self.assertIsNone(cred.resolve_credential(None, None))
        self.assertIsNone(
            cred.resolve_credential("/x", "", default_key_dir="/d")
        )


class TestPublicKeyFingerprint(unittest.TestCase):
    def _open_ssh_fingerprint(self, blob: bytes) -> str:
        digest = hashlib.sha256(blob).digest()
        return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")

    def test_reads_dot_pub_next_to_private_key(self):
        blob = b"test-blob"
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "id_ed25519").write_text("private\n", encoding="utf-8")
            (Path(tmp) / "id_ed25519.pub").write_text(
                "ssh-ed25519 " + base64.b64encode(blob).decode() + " u@h\n",
                encoding="utf-8",
            )
            self.assertEqual(
                cred.public_key_fingerprint(tmp, "id_ed25519"),
                self._open_ssh_fingerprint(blob),
            )

    def test_falls_back_to_a_public_key_file(self):
        blob = b"other-blob"
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pub_only").write_text(
                "ecdsa-sha2-nistp256 " + base64.b64encode(blob).decode() + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                cred.public_key_fingerprint(tmp, "pub_only"),
                self._open_ssh_fingerprint(blob),
            )

    def test_missing_or_invalid_public_key_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(cred.public_key_fingerprint(tmp, "absent"))
            (Path(tmp) / "broken.pub").write_text(
                "ssh-ed25519 not-base64!!\n", encoding="utf-8"
            )
            self.assertIsNone(cred.public_key_fingerprint(tmp, "broken"))

    def test_identity_is_key_dir_key_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity = cred.credential_identity(tmp, "id_rsa")
            self.assertTrue(identity.endswith("id_rsa"))
            self.assertIn(Path(tmp).name, identity)


if __name__ == "__main__":
    unittest.main()
