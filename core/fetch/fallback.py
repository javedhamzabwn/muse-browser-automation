"""core/fetch/fallback.py — Error Classification, Circuit Breaker & Fallback Manager."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("muse.fetch.fallback")


class FetchErrorKind(str, Enum):
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    JS_REQUIRED = "JS_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CAPTCHA = "CAPTCHA"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    BROWSER_CRASH = "BROWSER_CRASH"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    EXTRACTION_FAILURE = "EXTRACTION_FAILURE"
    UNKNOWN = "UNKNOWN"


class ErrorClassifier:
    """Classifies raw errors and response bodies into standardized FetchErrorKind."""

    @classmethod
    def classify(
        cls,
        error: Optional[Exception | str] = None,
        status_code: Optional[int] = None,
        content: Optional[str] = None,
    ) -> FetchErrorKind:
        err_str = str(error or "").lower()
        body = (content or "").lower()

        # 1. Timeout
        if "timeout" in err_str or "timed out" in err_str:
            return FetchErrorKind.TIMEOUT

        # 2. CAPTCHA / Bot Defense
        if any(w in err_str or w in body for w in ("cf-turnstile", "turnstile", "recaptcha", "hcaptcha", "arkose", "challenge-running", "just a moment...")):
            return FetchErrorKind.CAPTCHA

        # 3. Blocked / Rate Limited
        if status_code in (403, 429) or any(w in err_str or w in body for w in ("access denied", "rate limit", "blocked", "forbidden")):
            return FetchErrorKind.BLOCKED

        # 4. Auth Required
        if status_code in (401, 407) or any(w in err_str or w in body for w in ("login required", "sign in", "unauthorized")):
            return FetchErrorKind.AUTH_REQUIRED

        # 5. JS Required
        if any(w in body for w in ("enable javascript", "please turn on javascript", "javascript is required", "need to enable javascript")):
            return FetchErrorKind.JS_REQUIRED

        # 6. Network error
        if any(w in err_str for w in ("connection refused", "getaddrinfo failed", "network error", "dns_probe_finished", "connection reset")):
            return FetchErrorKind.NETWORK_ERROR

        # 7. Browser crash
        if any(w in err_str for w in ("target closed", "browser disconnected", "session closed", "crash", "sigkill")):
            return FetchErrorKind.BROWSER_CRASH

        if status_code and status_code >= 500:
            return FetchErrorKind.INVALID_RESPONSE

        return FetchErrorKind.UNKNOWN


class FailureMemory:
    """Remembers backend failures per domain to skip known failing tiers."""

    def __init__(self, memory_ttl_sec: float = 300.0):
        self.ttl = memory_ttl_sec
        # domain -> {tool_name: (error_kind, expiry_time)}
        self._memory: Dict[str, Dict[str, Tuple[FetchErrorKind, float]]] = {}

    def record_failure(self, url: str, tool: str, kind: FetchErrorKind) -> None:
        domain = self._get_domain(url)
        if not domain:
            return
        if domain not in self._memory:
            self._memory[domain] = {}
        self._memory[domain][tool] = (kind, time.time() + self.ttl)
        logger.info("Recorded failure for %s on %s: %s (expires in %ds)", tool, domain, kind.value, int(self.ttl))

    def is_failing(self, url: str, tool: str) -> Optional[FetchErrorKind]:
        domain = self._get_domain(url)
        if not domain or domain not in self._memory:
            return None
        entry = self._memory[domain].get(tool)
        if not entry:
            return None
        kind, expiry = entry
        if time.time() > expiry:
            self._memory[domain].pop(tool, None)
            return None
        return kind

    @staticmethod
    def _get_domain(url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""


class CircuitBreaker:
    """Trips if a specific backend repeatedly fails across multiple domains."""

    def __init__(self, threshold: int = 5, recovery_time_sec: float = 60.0):
        self.threshold = threshold
        self.recovery_time = recovery_time_sec
        self._failure_counts: Dict[str, int] = {}
        self._tripped_until: Dict[str, float] = {}

    def record_success(self, tool: str) -> None:
        self._failure_counts[tool] = max(0, self._failure_counts.get(tool, 0) - 1)

    def record_failure(self, tool: str) -> None:
        count = self._failure_counts.get(tool, 0) + 1
        self._failure_counts[tool] = count
        if count >= self.threshold:
            self._tripped_until[tool] = time.time() + self.recovery_time
            logger.warning("Circuit breaker TRIPPED for %s (recovery in %ds)", tool, int(self.recovery_time))

    def is_available(self, tool: str) -> bool:
        until = self._tripped_until.get(tool)
        if until:
            if time.time() < until:
                return False
            # Recovery period elapsed
            self._tripped_until.pop(tool, None)
            self._failure_counts[tool] = 0
        return True
