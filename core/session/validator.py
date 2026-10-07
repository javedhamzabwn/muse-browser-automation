"""core/session/validator.py — Validates Session Authentication State without Exposing Tokens."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("muse.session.validator")


class SessionValidator:
    """Tests session validity against real target websites and returns high-level status."""

    @classmethod
    async def validate_session_online(
        cls,
        session_id: str,
        target_domain: str,
        vault: Any,
        browser_backend: str = "playwright",
    ) -> Dict[str, Any]:
        """
        Launches headless browser, injects session payload, navigates to target,
        and determines if authentication state is verified.
        Never returns or logs cookie values.
        """
        rec = vault.get_session(session_id)
        if not rec:
            return {
                "session_id": session_id,
                "status": "NOT_FOUND",
                "validation": {"browser_launch": "FAIL", "session_injection": "FAIL", "site_navigation": "FAIL", "authenticated_state": "FAIL"},
                "error": f"Session '{session_id}' not found in vault",
            }

        target_url = f"https://{target_domain}" if not target_domain.startswith("http") else target_domain
        steps = {
            "browser_launch": "PENDING",
            "session_injection": "PENDING",
            "site_navigation": "PENDING",
            "authenticated_state": "PENDING",
        }

        try:
            # 1. Load payload (permission enforced)
            payload = vault.load_session_payload(session_id, target_tool=browser_backend, target_url=target_url)

            # 2. Launch headless browser
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                steps["browser_launch"] = "PASS"
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context()

                # 3. Inject session
                from core.session.injector import SessionInjector
                injected_count = await SessionInjector.inject_into_playwright(context, payload)
                steps["session_injection"] = "PASS" if injected_count > 0 else "FAIL"

                # 4. Navigate
                page = await context.new_page()
                resp = await page.goto(target_url, timeout=15000, wait_until="domcontentloaded")
                steps["site_navigation"] = "PASS" if resp and resp.status < 400 else "FAIL"

                # 5. Evaluate authentication status heuristics (never read cookie values)
                content = (await page.content()).lower()
                title = (await page.title()).lower()

                # Heuristics:
                # If page contains signs of being logged out or explicit login redirects:
                login_triggers = ["login", "sign in", "log in", "create account", "join now"]
                avatar_triggers = ["logout", "sign out", "my account", "profile", "account settings", "dashboard"]

                has_auth_markers = any(m in content for m in avatar_triggers)
                has_login_markers = any(m in title for m in ["log in", "sign in"])

                if has_auth_markers and not has_login_markers:
                    auth_status = "AUTHENTICATED"
                    steps["authenticated_state"] = "PASS"
                elif has_login_markers:
                    auth_status = "NOT_AUTHENTICATED"
                    steps["authenticated_state"] = "FAIL"
                else:
                    auth_status = "AUTHENTICATED" if injected_count > 0 and steps["site_navigation"] == "PASS" else "UNKNOWN"
                    steps["authenticated_state"] = "PASS" if auth_status == "AUTHENTICATED" else "UNKNOWN"

                await browser.close()

                # Update vault status
                vault.update_status(session_id, auth_status)
                return {
                    "session_id": session_id,
                    "target_domain": target_domain,
                    "status": auth_status,
                    "validation": steps,
                }

        except PermissionError as pe:
            return {
                "session_id": session_id,
                "status": "PERMISSION_DENIED",
                "validation": steps,
                "error": str(pe),
            }
        except Exception as exc:
            logger.warning("Validation exception for session %s: %s", session_id, exc)
            return {
                "session_id": session_id,
                "status": "UNKNOWN",
                "validation": steps,
                "error": str(exc),
            }
