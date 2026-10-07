"""core/risk_engine.py — Action Risk Assessment & Approval Gates for Muse 3.0.

Evaluates browser actions, target elements, and URL boundaries to categorize risk
(LOW, MEDIUM, HIGH, CRITICAL) and enforce human-in-the-loop approval or dry-run safety.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Coroutine, Dict, List, Optional

from core.types import ActionRiskLevel, ElementQuery, ResolvedElement

HIGH_RISK_KEYWORDS = [
    "delete", "remove", "destroy", "purge", "cancel account",
    "pay", "purchase", "order", "charge", "checkout", "transfer",
    "password", "secret", "private key", "auth token", "credit card",
]

CRITICAL_URL_PATTERNS = [
    r"/checkout/pay",
    r"/billing/charge",
    r"/settings/delete",
    r"/transfer/funds",
]


class RiskEngine:
    """Evaluates risks and enforces safety policies before executing browser mutations."""

    def __init__(
        self,
        max_auto_risk: ActionRiskLevel = ActionRiskLevel.MEDIUM,
        dry_run: bool = False,
        approval_hook: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, bool]]] = None,
    ):
        self.max_auto_risk = max_auto_risk
        self.dry_run = dry_run
        self.approval_hook = approval_hook

    def assess_risk(
        self,
        action: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        element: Optional[ResolvedElement] = None,
        query: Optional[ElementQuery] = None,
    ) -> ActionRiskLevel:
        """Classify risk of the proposed action."""
        if action in ("navigate", "scroll", "read", "model", "screenshot"):
            return ActionRiskLevel.LOW

        # Check critical URL boundaries
        for pat in CRITICAL_URL_PATTERNS:
            if re.search(pat, url, re.IGNORECASE):
                return ActionRiskLevel.CRITICAL

        # Collect target text signals
        signals: List[str] = []
        if element:
            signals.append(element.name)
            signals.append(element.selector)
            signals.append(element.tag)
        if query:
            if query.name: signals.append(query.name)
            if query.description: signals.append(query.description)
            if query.text: signals.append(query.text)
            if query.selector: signals.append(query.selector)
        if params:
            for v in params.values():
                if isinstance(v, str):
                    signals.append(v)

        combined_text = " ".join(signals).lower()

        # Check high-risk keywords
        for kw in HIGH_RISK_KEYWORDS:
            if kw in combined_text:
                return ActionRiskLevel.HIGH

        if action in ("click", "type", "press"):
            return ActionRiskLevel.MEDIUM

        return ActionRiskLevel.LOW

    async def verify_permission(
        self,
        action: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        element: Optional[ResolvedElement] = None,
        query: Optional[ElementQuery] = None,
    ) -> bool:
        """Check if action is permitted to execute automatically or requires approval."""
        risk = self.assess_risk(action, url, params, element, query)

        # In dry-run mode, mutating actions are simulated
        if self.dry_run and action not in ("read", "scroll", "screenshot"):
            return False

        # Order of risk levels
        risk_hierarchy = {
            ActionRiskLevel.LOW: 1,
            ActionRiskLevel.MEDIUM: 2,
            ActionRiskLevel.HIGH: 3,
            ActionRiskLevel.CRITICAL: 4,
        }

        if risk_hierarchy[risk] > risk_hierarchy[self.max_auto_risk]:
            if self.approval_hook:
                payload = {
                    "action": action,
                    "url": url,
                    "risk": risk.value,
                    "params": params or {},
                    "element": element.to_dict() if element else None,
                }
                return await self.approval_hook(payload)
            # No approval hook provided: high risk action blocked by default
            return False

        return True
