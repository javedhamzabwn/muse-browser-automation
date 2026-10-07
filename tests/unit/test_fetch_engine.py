"""tests/unit/test_fetch_engine.py — Unit tests for Phase 8/9 Universal Fetch & Fallback."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from core.fetch.cache import FetchCache
from core.fetch.engine import UniversalFetchEngine
from core.fetch.fallback import ErrorClassifier, FailureMemory, FetchErrorKind
from core.fetch.planner import FetchPlanner
from core.fetch.reddit import RedditFetcher
from tests.synthetic_server import SyntheticServer


class TestUniversalFetchEngine(unittest.IsolatedAsyncioTestCase):
    server: SyntheticServer
    base_url: str

    @classmethod
    def setUpClass(cls):
        cls.server = SyntheticServer(port=18084)
        cls.server.start()
        cls.base_url = cls.server.url

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache = FetchCache(db_path=os.path.join(self.temp_dir, "test_cache.db"))
        self.engine = UniversalFetchEngine(cache=self.cache)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_tier0_static_fetch(self):
        url = f"{self.base_url}/synthetic.html"
        res = await self.engine.fetch(url)
        self.assertTrue(res.success)
        self.assertEqual(res.tool, "http_static")
        self.assertIn("Synthetic Test Suite", res.title)
        self.assertIn("Submit Order", res.text)
        self.assertIsInstance(res.links, list)
        self.assertLess(res.timing["total_ms"], 100.0)  # Ultra-fast

    async def test_cache_hit_speed(self):
        url = f"{self.base_url}/synthetic.html"
        # 1st fetch populates cache
        res1 = await self.engine.fetch(url)
        self.assertTrue(res1.success)

        # 2nd fetch hits cache
        res2 = await self.engine.fetch(url)
        self.assertTrue(res2.success)
        self.assertEqual(res2.tool, "cache")
        self.assertEqual(res2.title, res1.title)
        self.assertLess(res2.timing["total_ms"], 10.0)  # <10ms cache retrieval

    def test_error_classifier(self):
        self.assertEqual(
            ErrorClassifier.classify("Connection timed out after 5000ms"),
            FetchErrorKind.TIMEOUT,
        )
        self.assertEqual(
            ErrorClassifier.classify(content="Please enable JavaScript to view this page"),
            FetchErrorKind.JS_REQUIRED,
        )
        self.assertEqual(
            ErrorClassifier.classify(content="Cloudflare cf-turnstile verification"),
            FetchErrorKind.CAPTCHA,
        )
        self.assertEqual(
            ErrorClassifier.classify(status_code=403),
            FetchErrorKind.BLOCKED,
        )
        self.assertEqual(
            ErrorClassifier.classify(status_code=401),
            FetchErrorKind.AUTH_REQUIRED,
        )

    def test_reddit_url_detection(self):
        self.assertTrue(RedditFetcher.is_reddit_url("https://www.reddit.com/r/Python/"))
        self.assertTrue(RedditFetcher.is_reddit_url("https://redd.it/xyz123"))
        self.assertFalse(RedditFetcher.is_reddit_url("https://news.ycombinator.com"))
        self.assertEqual(
            RedditFetcher.extract_reddit_path("https://reddit.com/r/programming/top/?t=day"),
            "/r/programming/top/?t=day",
        )

    def test_planner_routing(self):
        # Static
        chain1 = FetchPlanner.plan("https://example.com", {})
        self.assertEqual(chain1[0], "http_static")

        # JS required
        chain2 = FetchPlanner.plan("https://example.com", {"javascript": True})
        self.assertNotIn("http_static", chain2)
        self.assertEqual(chain2[0], "playwright")

        # Reddit
        chain3 = FetchPlanner.plan("https://www.reddit.com/r/news", {})
        self.assertEqual(chain3[0], "redlib")


if __name__ == "__main__":
    unittest.main()
