"""core/observability.py — Structured Action Tracing & Anti-Bot/CAPTCHA Detection for Muse 3.0."""

from __future__ import annotations

import collections
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("muse.core.observability")

CAPTCHA_DETECTION_SCRIPT = r"""
(() => {
    // 1. Cloudflare Turnstile
    if (
        document.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
        document.querySelector('[name="cf-turnstile-response"]') ||
        document.querySelector('.cf-turnstile') ||
        document.title.includes('Just a moment...') ||
        document.title.includes('Attention Required! | Cloudflare')
    ) {
        return { detected: true, type: 'cloudflare_turnstile' };
    }

    // 2. Google reCAPTCHA
    if (
        document.querySelector('iframe[src*="google.com/recaptcha"]') ||
        document.querySelector('iframe[src*="recaptcha.net"]') ||
        document.querySelector('.g-recaptcha') ||
        document.querySelector('#g-recaptcha-response')
    ) {
        return { detected: true, type: 'recaptcha' };
    }

    // 3. hCaptcha
    if (
        document.querySelector('iframe[src*="hcaptcha.com"]') ||
        document.querySelector('.h-captcha') ||
        document.querySelector('[name="h-captcha-response"]')
    ) {
        return { detected: true, type: 'hcaptcha' };
    }

    // 4. Arkose / FunCaptcha
    if (
        document.querySelector('iframe[src*="arkoselabs.com"]') ||
        document.querySelector('#arkose')
    ) {
        return { detected: true, type: 'arkose_funcaptcha' };
    }

    return { detected: false, type: null };
})();
"""


class ActionTracer:
    """In-memory circular trace log for real-time observability and dashboard streaming."""

    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self._buffer: collections.deque[Dict[str, Any]] = collections.deque(maxlen=capacity)

    def record(
        self,
        action: str,
        duration_ms: float,
        ok: bool,
        tab_id: str,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry = {
            "timestamp": time.time(),
            "action": action,
            "duration_ms": round(duration_ms, 2),
            "ok": ok,
            "tab_id": tab_id,
            "details": details or {},
            "error": error,
        }
        self._buffer.append(entry)
        return entry

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        entries = list(self._buffer)
        return entries[-limit:]

    def clear(self) -> None:
        self._buffer.clear()


class CaptchaDetector:
    """Fast detection of anti-bot challenges and CAPTCHA overlays."""

    @classmethod
    async def detect(cls, backend: Any, tab_id: str) -> Dict[str, Any]:
        try:
            res = await backend.evaluate(tab_id, CAPTCHA_DETECTION_SCRIPT.strip())
            if isinstance(res, dict):
                return res
        except Exception as exc:
            logger.debug("CAPTCHA detection evaluation error: %s", exc)
        return {"detected": False, "type": None}
