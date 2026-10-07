"""core/session/injector.py — Injects Authenticated Vault Sessions into Browser Contexts."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("muse.session.injector")


class SessionInjector:
    """Injects decrypted session cookies and storage into target browser runtimes."""

    @staticmethod
    async def inject_into_playwright(context: Any, payload: Dict[str, Any]) -> int:
        """
        Inject cookies and storage state into Playwright BrowserContext.
        Returns count of injected cookies.
        """
        cookies = payload.get("cookies", [])
        if not cookies:
            return 0

        pw_cookies = []
        for c in cookies:
            cookie_dict = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
            }
            if c.get("secure") is not None:
                cookie_dict["secure"] = bool(c["secure"])
            if c.get("httpOnly") is not None:
                cookie_dict["httpOnly"] = bool(c["httpOnly"])
            if c.get("sameSite") in ("Strict", "Lax", "None"):
                cookie_dict["sameSite"] = c["sameSite"]
            exp = c.get("expires")
            if isinstance(exp, (int, float)) and exp > 0:
                if exp > 10_000_000_000_000:
                    exp_sec = (exp / 1_000_000.0) - 11644473600.0
                elif exp > 100_000_000_000:
                    exp_sec = exp / 1000.0
                else:
                    exp_sec = float(exp)
                if 0 < exp_sec < 4_102_444_800:
                    cookie_dict["expires"] = round(exp_sec, 2)
            pw_cookies.append(cookie_dict)

        try:
            await context.add_cookies(pw_cookies)
            logger.info("Successfully injected %d cookies into Playwright context", len(pw_cookies))
            return len(pw_cookies)
        except Exception as e:
            logger.warning("Failed to inject cookies into Playwright context: %s", e)
            return 0

    @staticmethod
    async def inject_into_cdp(cdp_client: Any, payload: Dict[str, Any]) -> int:
        """Inject cookies into active Chrome/Obscura CDP session."""
        cookies = payload.get("cookies", [])
        if not cookies:
            return 0

        count = 0
        for c in cookies:
            try:
                await cdp_client.send(
                    "Network.setCookie",
                    {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ""),
                        "path": c.get("path", "/"),
                        "secure": bool(c.get("secure", False)),
                        "httpOnly": bool(c.get("httpOnly", False)),
                    },
                )
                count += 1
            except Exception:
                pass
        return count
