"""core/session/vault.py — Muse Session Vault with Encrypted Storage & Policy Enforcement."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.session.audit import SessionAuditLog
from core.session.encryption import VaultEncryption
from core.session.permissions import SessionPermissionPolicy

logger = logging.getLogger("muse.session.vault")


@dataclass
class SessionRecord:
    session_id: str
    name: str
    domains: List[str]
    source_browser: str
    source_profile: str
    allowed_tools: List[str]
    created_at: str
    updated_at: str
    expires_at: Optional[str] = None
    status: str = "UNKNOWN"  # "AUTHENTICATED", "NOT_AUTHENTICATED", "EXPIRED", "REVOKED"
    cookie_count: int = 0
    has_local_storage: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SessionVault:
    """Secure encrypted repository for user-imported browser authentication sessions."""

    _instance: Optional[SessionVault] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, vault_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return
        self.vault_dir = vault_dir or os.path.join(os.path.expanduser("~"), ".muse", "session-vault")
        self.encrypted_dir = os.path.join(self.vault_dir, "encrypted")
        os.makedirs(self.encrypted_dir, exist_ok=True)

        self.db_path = os.path.join(self.vault_dir, "metadata.db")
        self.encryption = VaultEncryption(vault_dir=self.vault_dir)
        self.audit = SessionAuditLog(vault_dir=self.vault_dir)

        self._init_db()
        self._initialized = True

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    domains TEXT NOT NULL,
                    source_browser TEXT NOT NULL,
                    source_profile TEXT NOT NULL,
                    allowed_tools TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    status TEXT NOT NULL,
                    cookie_count INTEGER NOT NULL,
                    has_local_storage INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def store_session(
        self,
        name: str,
        domains: List[str],
        source_browser: str,
        source_profile: str,
        allowed_tools: List[str],
        cookies: List[Dict[str, Any]],
        local_storage: Optional[Dict[str, Any]] = None,
        expires_at: Optional[str] = None,
    ) -> SessionRecord:
        """Encrypts credentials and stores metadata in database."""
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        # Payload to encrypt (cookies and localStorage)
        payload = {
            "session_id": session_id,
            "domains": domains,
            "cookies": cookies,
            "local_storage": local_storage or {},
        }
        raw_bytes = json.dumps(payload).encode("utf-8")
        encrypted_bytes = self.encryption.encrypt(raw_bytes)

        # Write to encrypted file
        enc_file = os.path.join(self.encrypted_dir, f"{session_id}.enc")
        with open(enc_file, "wb") as f:
            f.write(encrypted_bytes)

        rec = SessionRecord(
            session_id=session_id,
            name=name,
            domains=domains,
            source_browser=source_browser,
            source_profile=source_profile,
            allowed_tools=allowed_tools,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            status="UNKNOWN",
            cookie_count=len(cookies),
            has_local_storage=bool(local_storage),
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, name, domains, source_browser, source_profile,
                    allowed_tools, created_at, updated_at, expires_at,
                    status, cookie_count, has_local_storage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.session_id,
                    rec.name,
                    json.dumps(rec.domains),
                    rec.source_browser,
                    rec.source_profile,
                    json.dumps(rec.allowed_tools),
                    rec.created_at,
                    rec.updated_at,
                    rec.expires_at,
                    rec.status,
                    rec.cookie_count,
                    1 if rec.has_local_storage else 0,
                ),
            )
            conn.commit()

        self.audit.record(
            action="import",
            domain=",".join(domains),
            source=f"{source_browser} ({source_profile})",
            target=",".join(allowed_tools),
            operation="store_session",
            result="SUCCESS",
            details=f"Stored {len(cookies)} cookies (encrypted)",
        )
        return rec

    def list_sessions(self, domain: Optional[str] = None) -> List[SessionRecord]:
        """Lists metadata of all stored sessions without revealing tokens."""
        records: List[SessionRecord] = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions ORDER BY created_at DESC")
            rows = cursor.fetchall()

        for r in rows:
            domains = json.loads(r[2])
            if domain and not any(domain.lower() in d.lower() for d in domains):
                continue
            records.append(
                SessionRecord(
                    session_id=r[0],
                    name=r[1],
                    domains=domains,
                    source_browser=r[3],
                    source_profile=r[4],
                    allowed_tools=json.loads(r[5]),
                    created_at=r[6],
                    updated_at=r[7],
                    expires_at=r[8],
                    status=r[9],
                    cookie_count=r[10],
                    has_local_storage=bool(r[11]),
                )
            )
        return records

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            r = cursor.fetchone()
            if not r:
                return None
            return SessionRecord(
                session_id=r[0],
                name=r[1],
                domains=json.loads(r[2]),
                source_browser=r[3],
                source_profile=r[4],
                allowed_tools=json.loads(r[5]),
                created_at=r[6],
                updated_at=r[7],
                expires_at=r[8],
                status=r[9],
                cookie_count=r[10],
                has_local_storage=bool(r[11]),
            )

    def load_session_payload(
        self,
        session_id: str,
        target_tool: str,
        target_url: str,
    ) -> Dict[str, Any]:
        """
        Enforces domain and tool permission policies, then decrypts and returns credentials.
        Never exposed over external API or logs.
        """
        rec = self.get_session(session_id)
        if not rec:
            raise KeyError(f"Session '{session_id}' not found in vault")
        if rec.status == "REVOKED":
            raise RuntimeError(f"Session '{session_id}' has been revoked")

        policy = SessionPermissionPolicy(
            allowed_domains=rec.domains,
            allowed_tools=rec.allowed_tools,
        )

        # Policy checks
        if not policy.is_domain_allowed(target_url):
            self.audit.record(
                action="access_denied",
                domain=target_url,
                source=rec.name,
                target=target_tool,
                operation="load_session_payload",
                result="BLOCKED",
                details=f"Domain '{target_url}' not in allowed scope {rec.domains}",
            )
            raise PermissionError(f"Session '{session_id}' is not scoped for domain '{target_url}'")

        if not policy.is_tool_allowed(target_tool):
            self.audit.record(
                action="access_denied",
                domain=target_url,
                source=rec.name,
                target=target_tool,
                operation="load_session_payload",
                result="BLOCKED",
                details=f"Tool '{target_tool}' not in allowed tool scope {rec.allowed_tools}",
            )
            raise PermissionError(f"Session '{session_id}' is not authorized for tool '{target_tool}'")

        # Decrypt payload
        enc_file = os.path.join(self.encrypted_dir, f"{session_id}.enc")
        if not os.path.isfile(enc_file):
            raise FileNotFoundError(f"Encrypted session file missing: {enc_file}")

        with open(enc_file, "rb") as f:
            encrypted_data = f.read()

        raw_bytes = self.encryption.decrypt(encrypted_data)
        data = json.loads(raw_bytes.decode("utf-8"))

        self.audit.record(
            action="inject",
            domain=target_url,
            source=rec.name,
            target=target_tool,
            operation="load_session_payload",
            result="SUCCESS",
        )
        return data

    def update_status(self, session_id: str, status: str) -> None:
        valid_statuses = {"AUTHENTICATED", "NOT_AUTHENTICATED", "EXPIRED", "REVOKED", "UNKNOWN"}
        if status not in valid_statuses:
            status = "UNKNOWN"
        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status, now, session_id),
            )
            conn.commit()

    def revoke_session(self, session_id: str, purge_metadata: bool = False) -> bool:
        """Securely zeroes and removes encrypted file and marks session REVOKED."""
        rec = self.get_session(session_id)
        if not rec:
            return False

        enc_file = os.path.join(self.encrypted_dir, f"{session_id}.enc")
        if os.path.isfile(enc_file):
            try:
                # Secure erase overwrite
                size = os.path.getsize(enc_file)
                with open(enc_file, "wb") as f:
                    f.write(os.urandom(size))
                os.remove(enc_file)
            except Exception as e:
                logger.warning("Error wiping encrypted session file: %s", e)

        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        with sqlite3.connect(self.db_path) as conn:
            if purge_metadata:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            else:
                conn.execute("UPDATE sessions SET status = 'REVOKED', updated_at = ? WHERE session_id = ?", (now, session_id))
            conn.commit()

        self.audit.record(
            action="revoke",
            domain=",".join(rec.domains),
            source=rec.name,
            target="all",
            operation="revoke_session",
            result="SUCCESS",
            details="Session credentials wiped and session revoked",
        )
        return True
