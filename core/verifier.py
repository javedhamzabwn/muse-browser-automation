"""core/verifier.py — Event-Driven Wait Engine & Action Verifier for Muse 3.0.

Eliminates arbitrary sleeps (such as sleep(0.8) or sleep(3)) by continuously
monitoring DOM mutations, URL transitions, title changes, and accessibility state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from core.interfaces import BaseActionVerifier, BaseBrowserBackend
from core.types import VerificationResult

logger = logging.getLogger("muse.core.verifier")

CAPTURE_STATE_JS = r"""
(() => {
    if (!window.__muse_observer_installed) {
        window.__muse_mutation_counter = 0;
        try {
            const observer = new MutationObserver((mutations) => {
                window.__muse_mutation_counter += mutations.length;
            });
            observer.observe(document.documentElement, {
                childList: true,
                subtree: true,
                attributes: true,
                characterData: true
            });
            window.__muse_observer_installed = true;
        } catch (_) {}
    }

    const active = document.activeElement;
    const dialogs = document.querySelectorAll('dialog[open], [role="dialog"], [aria-modal="true"]');
    return {
        url: location.href,
        title: document.title,
        mutations: window.__muse_mutation_counter || 0,
        active_tag: active ? active.tagName.toLowerCase() : '',
        active_id: active ? active.id : '',
        modal_open: dialogs.length > 0,
        readyState: document.readyState
    };
})();
"""


class ActionVerifier(BaseActionVerifier):
    """Event-driven verification of browser actions and DOM state transitions."""

    async def capture_state(self, backend: BaseBrowserBackend, tab_id: str) -> Dict[str, Any]:
        """Capture lightweight snapshot of page state before executing action."""
        try:
            res = await backend.evaluate(tab_id, CAPTURE_STATE_JS.strip())
            if isinstance(res, dict):
                res["timestamp"] = time.time()
                return res
        except Exception as exc:
            logger.debug("Failed capturing in-page state: %s", exc)

        # Fallback to high-level backend calls
        try:
            url = await backend.get_url(tab_id)
            title = await backend.get_title(tab_id)
            return {
                "url": url,
                "title": title,
                "mutations": 0,
                "active_tag": "",
                "active_id": "",
                "modal_open": False,
                "readyState": "complete",
                "timestamp": time.time(),
            }
        except Exception:
            return {"url": "", "title": "", "mutations": 0, "timestamp": time.time()}

    async def verify_action(
        self,
        backend: BaseBrowserBackend,
        tab_id: str,
        action: str,
        before_state: Dict[str, Any],
        expected_change: Optional[str] = None,
        timeout_ms: int = 1000,
    ) -> VerificationResult:
        """Verify if action caused the expected or any meaningful state change."""
        start = time.perf_counter()
        deadline = start + (timeout_ms / 1000.0)
        poll_interval = 0.01  # 10ms polling interval

        before_url = before_state.get("url", "")
        before_title = before_state.get("title", "")
        before_mutations = before_state.get("mutations", 0)
        before_modal = before_state.get("modal_open", False)

        last_state = before_state

        while time.perf_counter() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                curr = await backend.evaluate(tab_id, CAPTURE_STATE_JS.strip())
                if not isinstance(curr, dict):
                    continue
                last_state = curr
            except Exception:
                continue

            curr_url = curr.get("url", "")
            curr_title = curr.get("title", "")
            curr_mutations = curr.get("mutations", 0)
            curr_modal = curr.get("modal_open", False)

            url_changed = curr_url != before_url
            title_changed = curr_title != before_title
            dom_mutated = (curr_mutations > before_mutations) or (curr_modal != before_modal)
            page_changed = url_changed or title_changed or dom_mutated

            if expected_change:
                if expected_change == "url_change" and url_changed:
                    return VerificationResult(
                        verified=True,
                        page_changed=True,
                        url_changed=True,
                        title_changed=title_changed,
                        dom_mutated=dom_mutated,
                        details={"elapsed_ms": (time.perf_counter() - start) * 1000.0, "new_url": curr_url},
                    )
                elif expected_change == "modal_open" and curr_modal:
                    return VerificationResult(
                        verified=True,
                        page_changed=True,
                        url_changed=url_changed,
                        title_changed=title_changed,
                        dom_mutated=True,
                        details={"elapsed_ms": (time.perf_counter() - start) * 1000.0, "modal_open": True},
                    )
                elif expected_change == "title_change" and title_changed:
                    return VerificationResult(
                        verified=True,
                        page_changed=True,
                        url_changed=url_changed,
                        title_changed=True,
                        dom_mutated=dom_mutated,
                        details={"elapsed_ms": (time.perf_counter() - start) * 1000.0, "new_title": curr_title},
                    )
            elif page_changed:
                return VerificationResult(
                    verified=True,
                    page_changed=True,
                    url_changed=url_changed,
                    title_changed=title_changed,
                    dom_mutated=dom_mutated,
                    details={
                        "elapsed_ms": (time.perf_counter() - start) * 1000.0,
                        "mutations": curr_mutations - before_mutations,
                    },
                )

        # Timeout reached without detected state transition
        elapsed = (time.perf_counter() - start) * 1000.0
        return VerificationResult(
            verified=False,
            page_changed=False,
            url_changed=False,
            title_changed=False,
            dom_mutated=False,
            details={"elapsed_ms": elapsed, "timeout": True},
        )
