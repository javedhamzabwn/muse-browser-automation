"""core/session — Muse Session Vault and Profile Bridge."""

from core.session.audit import SessionAuditEntry, SessionAuditLog
from core.session.browser_bridge import BrowserProfileBridge
from core.session.encryption import VaultEncryption
from core.session.importer import BrowserSessionImporter
from core.session.injector import SessionInjector
from core.session.permissions import SessionPermissionPolicy
from core.session.validator import SessionValidator
from core.session.vault import SessionRecord, SessionVault

__all__ = [
    "SessionVault",
    "SessionRecord",
    "VaultEncryption",
    "SessionPermissionPolicy",
    "SessionAuditLog",
    "SessionAuditEntry",
    "SessionInjector",
    "SessionValidator",
    "BrowserSessionImporter",
    "BrowserProfileBridge",
]
