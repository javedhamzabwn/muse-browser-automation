"""core/fetch/cache.py — TTL Response & Content Cache with Privacy Protections."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("muse.fetch.cache")


class FetchCache:
    """Persistent SQLite-backed cache for public fetches and extracted content."""

    def __init__(self, db_path: Optional[str] = None, default_ttl_sec: int = 3600):
        if db_path is None:
            base_dir = os.path.join(os.path.expanduser("~"), ".muse")
            os.makedirs(base_dir, exist_ok=True)
            db_path = os.path.join(base_dir, "fetch_cache.db")

        self.db_path = db_path
        self.default_ttl = default_ttl_sec
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fetch_cache (
                        url_hash TEXT PRIMARY KEY,
                        url TEXT,
                        title TEXT,
                        content TEXT,
                        text TEXT,
                        links_json TEXT,
                        metadata_json TEXT,
                        status_code INTEGER,
                        created_at REAL,
                        expires_at REAL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON fetch_cache(expires_at)")
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize fetch cache DB: %s", e)

    @staticmethod
    def _hash_url(url: str) -> str:
        return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve unexpired cached fetch result if available."""
        url_hash = self._hash_url(url)
        now = time.time()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT title, content, text, links_json, metadata_json, status_code, created_at
                    FROM fetch_cache
                    WHERE url_hash = ? AND expires_at > ?
                    """,
                    (url_hash, now),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "url": url,
                        "title": row[0],
                        "content": row[1],
                        "text": row[2],
                        "links": json.loads(row[3] or "[]"),
                        "metadata": json.loads(row[4] or "{}"),
                        "status_code": row[5],
                        "cached_at": row[6],
                    }
        except Exception as e:
            logger.error("Error reading fetch cache: %s", e)
        return None

    def set(
        self,
        url: str,
        title: str,
        content: str,
        text: str,
        links: list,
        metadata: dict,
        status_code: int = 200,
        ttl_sec: Optional[int] = None,
        is_authenticated: bool = False,
    ) -> None:
        """Cache public result. Strictly skips if authenticated/private."""
        if is_authenticated:
            return  # Privacy rule: never cache authenticated private content

        ttl = ttl_sec if ttl_sec is not None else self.default_ttl
        now = time.time()
        expires = now + ttl
        url_hash = self._hash_url(url)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fetch_cache
                    (url_hash, url, title, content, text, links_json, metadata_json, status_code, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url_hash,
                        url,
                        title,
                        content,
                        text,
                        json.dumps(links),
                        json.dumps(metadata),
                        status_code,
                        now,
                        expires,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error("Error writing fetch cache: %s", e)

    def prune(self) -> int:
        """Remove expired entries."""
        now = time.time()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("DELETE FROM fetch_cache WHERE expires_at <= ?", (now,))
                conn.commit()
                return cur.rowcount
        except Exception:
            return 0
