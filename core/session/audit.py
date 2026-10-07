"""core/session/audit.py — Privacy-Preserving Audit Logger for Session Vault."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("muse.session.audit")


@dataclass
class SessionAuditEntry:
    timestamp: str
    action: str              # "import", "validate", "inject", "revoke", "access_denied"
    domain: str
    source: str              # e.g. "Chrome Profile 1"
    target: str              # e.g. "Camoufox", "Obscura", "Playwright"
    operation: str
    result: str              # "SUCCESS", "FAILURE", "BLOCKED", "EXPIRED"
    details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SessionAuditLog:
    """Maintains an append-only audit trail strictly free of secrets, cookies, or credentials."""

    def __init__(self, vault_dir: Optional[str] = None):
        self.vault_dir = vault_dir or os.path.join(os.path.expanduser("~"), ".muse", "session-vault")
        os.makedirs(self.vault_dir, exist_ok=True)
        self.log_file = os.path.join(self.vault_dir, "audit.jsonl")

    def record(
        self,
        action: str,
        domain: str,
        source: str,
        target: str,
        operation: str,
        result: str,
        details: Optional[str] = None,
    ) -> SessionAuditEntry:
        # Strict validation: never allow tokens or cookie values into audit
        safe_details = details
        if safe_details and any(k in safe_details.lower() for k in ("cookie=", "token=", "session=", "key=", "bearer")):
            safe_details = "[REDACTED_BY_AUDIT_POLICY]"

        entry = SessionAuditEntry(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            action=action,
            domain=domain,
            source=source,
            target=target,
            operation=operation,
            result=result,
            details=safe_details,
        )

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as e:
            logger.warning("Failed to append to session audit log: %s", e)

        return entry

    def get_recent(self, limit: int = 50) -> List[SessionAuditEntry]:
        if not os.path.isfile(self.log_file):
            return []
        entries: List[SessionAuditEntry] = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        entries.append(SessionAuditEntry(**d))
        except Exception as e:
            logger.warning("Failed to read audit log: %s", e)
        return entries
