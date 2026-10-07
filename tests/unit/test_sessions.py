"""tests/unit/test_sessions.py — Unit tests for Phase 16/19 Profile & Session Manager."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from core.sessions.manager import ProfileManager


class TestProfileManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = ProfileManager(base_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_profile_created(self):
        profiles = self.mgr.list_profiles()
        names = [p.name for p in profiles]
        self.assertIn("default", names)
        self.assertEqual(self.mgr.get_active_profile(), "default")

    def test_create_and_switch_profile(self):
        prof = self.mgr.create_profile("work_account")
        self.assertEqual(prof.name, "work_account")
        self.assertTrue(self.mgr.set_active_profile("work_account"))
        self.assertEqual(self.mgr.get_active_profile(), "work_account")

    def test_cookie_import_and_masked_export(self):
        raw_cookies = [
            {
                "name": "session_id",
                "value": "super_secret_auth_token_12345",
                "domain": ".github.com",
                "path": "/",
            },
            {
                "name": "theme",
                "value": "dark",
                "domain": ".github.com",
                "path": "/",
            },
        ]
        count = self.mgr.import_cookies("default", raw_cookies)
        self.assertEqual(count, 2)

        # Check masked export
        masked = self.mgr.export_cookies_masked("default")
        self.assertEqual(len(masked), 2)
        for m in masked:
            # Value must NEVER contain raw secret!
            self.assertNotIn("super_secret_auth_token_12345", m["value"])
            self.assertIn("[MASKED]", m["value"])

    def test_delete_profile(self):
        self.mgr.create_profile("temp_profile")
        self.assertTrue(self.mgr.delete_profile("temp_profile"))
        names = [p.name for p in self.mgr.list_profiles()]
        self.assertNotIn("temp_profile", names)

        # Deleting default should be rejected
        self.assertFalse(self.mgr.delete_profile("default"))


if __name__ == "__main__":
    unittest.main()
