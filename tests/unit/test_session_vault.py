"""tests/unit/test_session_vault.py — Unit tests for Muse Session Vault & Encryption."""

import os
import shutil
import tempfile
import unittest

from core.session.audit import SessionAuditLog
from core.session.encryption import VaultEncryption
from core.session.permissions import SessionPermissionPolicy
from core.session.vault import SessionRecord, SessionVault


class TestSessionVault(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="muse_test_vault_")
        # Reset singleton instance
        SessionVault._instance = None
        self.vault = SessionVault(vault_dir=self.temp_dir)

    def tearDown(self):
        SessionVault._instance = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_encryption_roundtrip(self):
        enc = VaultEncryption(vault_dir=self.temp_dir)
        plaintext = b"super_secret_session_token_12345"
        encrypted = enc.encrypt(plaintext)

        self.assertNotEqual(plaintext, encrypted)
        self.assertTrue(len(encrypted) > len(plaintext))

        decrypted = enc.decrypt(encrypted)
        self.assertEqual(plaintext, decrypted)

    def test_store_and_list_session(self):
        cookies = [
            {"name": "auth_token", "value": "secret_token_val", "domain": "github.com", "path": "/"}
        ]
        rec = self.vault.store_session(
            name="GitHub Main",
            domains=["github.com"],
            source_browser="chrome",
            source_profile="Default",
            allowed_tools=["playwright", "obscura"],
            cookies=cookies,
        )

        self.assertIsNotNone(rec.session_id)
        self.assertTrue(rec.session_id.startswith("sess-"))
        self.assertEqual(rec.cookie_count, 1)

        # Ensure encrypted file exists
        enc_file = os.path.join(self.temp_dir, "encrypted", f"{rec.session_id}.enc")
        self.assertTrue(os.path.isfile(enc_file))

        # Check list sessions without secrets
        sessions = self.vault.list_sessions()
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s.name, "GitHub Main")
        self.assertEqual(s.domains, ["github.com"])
        self.assertEqual(s.allowed_tools, ["playwright", "obscura"])

        # Check zero-secret guarantee: secret string not in metadata or str representation
        self.assertNotIn("secret_token_val", str(s.to_dict()))
        self.assertNotIn("auth_token", str(s.to_dict()))

    def test_domain_scoping_enforcement(self):
        cookies = [{"name": "sid", "value": "val123", "domain": "api.github.com"}]
        rec = self.vault.store_session(
            name="Scoped Session",
            domains=["github.com"],
            source_browser="chrome",
            source_profile="Default",
            allowed_tools=["playwright"],
            cookies=cookies,
        )

        # Allowed sub-domain navigation
        payload = self.vault.load_session_payload(rec.session_id, target_tool="playwright", target_url="https://api.github.com/user")
        self.assertIn("cookies", payload)

        # Denied domain navigation
        with self.assertRaises(PermissionError):
            self.vault.load_session_payload(rec.session_id, target_tool="playwright", target_url="https://malicious.org/steal")

    def test_tool_scoping_enforcement(self):
        cookies = [{"name": "sid", "value": "val123", "domain": "example.com"}]
        rec = self.vault.store_session(
            name="Playwright Only",
            domains=["example.com"],
            source_browser="chrome",
            source_profile="Default",
            allowed_tools=["playwright"],
            cookies=cookies,
        )

        # Disallowed tool
        with self.assertRaises(PermissionError):
            self.vault.load_session_payload(rec.session_id, target_tool="unauthorized_backend", target_url="https://example.com")

    def test_session_revocation(self):
        cookies = [{"name": "sid", "value": "val123", "domain": "example.com"}]
        rec = self.vault.store_session(
            name="To Revoke",
            domains=["example.com"],
            source_browser="chrome",
            source_profile="Default",
            allowed_tools=["playwright"],
            cookies=cookies,
        )
        enc_file = os.path.join(self.temp_dir, "encrypted", f"{rec.session_id}.enc")
        self.assertTrue(os.path.isfile(enc_file))

        ok = self.vault.revoke_session(rec.session_id)
        self.assertTrue(ok)

        # Encrypted payload must be deleted
        self.assertFalse(os.path.isfile(enc_file))

        # Status must be REVOKED
        revoked_rec = self.vault.get_session(rec.session_id)
        self.assertIsNotNone(revoked_rec)
        self.assertEqual(revoked_rec.status, "REVOKED")

        # Loading payload must fail
        with self.assertRaises(RuntimeError):
            self.vault.load_session_payload(rec.session_id, target_tool="playwright", target_url="https://example.com")


if __name__ == "__main__":
    unittest.main()
