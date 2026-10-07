"""tests/integration/test_daemon_health.py — Integration test for daemon endpoint."""

import json
import unittest
import urllib.request


class TestDaemonHealth(unittest.TestCase):
    DAEMON_URL = "http://127.0.0.1:18010"

    def _is_daemon_up(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.DAEMON_URL}/health", timeout=1) as resp:
                data = json.loads(resp.read().decode())
                return bool(data.get("ok"))
        except Exception:
            return False

    def test_daemon_health_endpoint(self):
        if not self._is_daemon_up():
            self.skipTest("Daemon not running on 127.0.0.1:18010")

        req = urllib.request.Request(f"{self.DAEMON_URL}/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertIn("ext", data)

    def test_daemon_404_handling(self):
        if not self._is_daemon_up():
            self.skipTest("Daemon not running on 127.0.0.1:18010")

        req = urllib.request.Request(f"{self.DAEMON_URL}/nonexistent_endpoint")
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                self.assertFalse(data.get("ok"))
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            data = json.loads(e.read().decode())
            self.assertFalse(data.get("ok"))


if __name__ == "__main__":
    unittest.main()
