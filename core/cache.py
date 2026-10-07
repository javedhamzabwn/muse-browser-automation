"""core/cache.py — Self-Healing Selector & Workflow Cache for Muse 3.0.

Provides Layer 0 Learned Selector caching backed by SQLite.
Supports auto-decay of broken selectors, failure tracking, and semantic self-healing.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

from core.interfaces import BaseSelectorCache

logger = logging.getLogger("muse.core.cache")


class SelectorCache(BaseSelectorCache):
    """SQLite-backed self-healing selector cache with decay and recovery mechanisms."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = os.path.expanduser("~/.muse")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "selector_cache.db")
        else:
            self.db_path = db_path
            if self.db_path != ":memory:":
                parent = os.path.dirname(os.path.abspath(self.db_path))
                if parent:
                    os.makedirs(parent, exist_ok=True)

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
                self._conn.execute("PRAGMA synchronous = NORMAL")
            except Exception:
                pass
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS selector_cache (
                        domain TEXT NOT NULL,
                        page_pattern TEXT NOT NULL,
                        intent TEXT NOT NULL,
                        selector TEXT NOT NULL,
                        method TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        success_count INTEGER DEFAULT 1,
                        failure_count INTEGER DEFAULT 0,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (domain, page_pattern, intent)
                    )
                """)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cache_lookup
                    ON selector_cache(domain, page_pattern, intent)
                """)

    def get(self, domain: str, page_pattern: str, intent: str) -> Optional[str]:
        """Lookup cached selector. Returns None if not found or decayed (failures >= 3)."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT selector, failure_count FROM selector_cache
                WHERE domain = ? AND page_pattern = ? AND intent = ?
                """,
                (domain, page_pattern, intent),
            ).fetchone()

            if not row:
                return None

            # Auto-decay stale/broken selectors
            if row["failure_count"] >= 3:
                logger.debug("Selector for '%s' decayed due to %d failures", intent, row["failure_count"])
                return None

            return str(row["selector"])

    def put(
        self,
        domain: str,
        page_pattern: str,
        intent: str,
        selector: str,
        method: str,
        confidence: float,
    ) -> None:
        """Store or update working selector with success counter increment."""
        now = time.time()
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO selector_cache (
                        domain, page_pattern, intent, selector, method, confidence,
                        success_count, failure_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)
                    ON CONFLICT(domain, page_pattern, intent) DO UPDATE SET
                        selector = excluded.selector,
                        method = excluded.method,
                        confidence = excluded.confidence,
                        success_count = selector_cache.success_count + 1,
                        failure_count = 0,
                        updated_at = excluded.updated_at
                    """,
                    (domain, page_pattern, intent, selector, method, confidence, now),
                )

    def record_failure(self, domain: str, page_pattern: str, intent: str) -> None:
        """Increment failure counter when cached selector fails to locate element."""
        now = time.time()
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE selector_cache
                    SET failure_count = failure_count + 1, updated_at = ?
                    WHERE domain = ? AND page_pattern = ? AND intent = ?
                    """,
                    (now, domain, page_pattern, intent),
                )

    def heal(
        self,
        domain: str,
        page_pattern: str,
        intent: str,
        selector: str,
        method: str,
        confidence: float,
    ) -> None:
        """Atomically heal broken selector with new working selector, resetting failure count."""
        now = time.time()
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO selector_cache (
                        domain, page_pattern, intent, selector, method, confidence,
                        success_count, failure_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)
                    ON CONFLICT(domain, page_pattern, intent) DO UPDATE SET
                        selector = excluded.selector,
                        method = excluded.method,
                        confidence = excluded.confidence,
                        success_count = selector_cache.success_count + 1,
                        failure_count = 0,
                        updated_at = excluded.updated_at
                    """,
                    (domain, page_pattern, intent, selector, method, confidence, now),
                )

    def clear(self, domain: Optional[str] = None) -> None:
        """Clear cache entries for specific domain or entirely."""
        with self._lock:
            with self._conn:
                if domain:
                    self._conn.execute("DELETE FROM selector_cache WHERE domain = ?", (domain,))
                else:
                    self._conn.execute("DELETE FROM selector_cache")

    def stats(self) -> Dict[str, Any]:
        """Return cache health and size statistics."""
        with self._lock:
            row = self._conn.execute("""
                SELECT
                    COUNT(*) as total_entries,
                    SUM(success_count) as total_successes,
                    SUM(failure_count) as total_failures
                FROM selector_cache
            """).fetchone()

            return {
                "total_entries": row["total_entries"] or 0,
                "total_successes": row["total_successes"] or 0,
                "total_failures": row["total_failures"] or 0,
                "db_path": self.db_path,
            }

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
