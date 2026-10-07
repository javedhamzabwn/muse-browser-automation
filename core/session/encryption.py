"""core/session/encryption.py — Authenticated AES-GCM 256-bit Encryption for Session Vault."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class VaultEncryption:
    """Provides authenticated AES-256-GCM encryption with PBKDF2 key derivation."""

    def __init__(self, vault_dir: Optional[str] = None):
        self.vault_dir = vault_dir or os.path.join(os.path.expanduser("~"), ".muse", "session-vault")
        os.makedirs(self.vault_dir, exist_ok=True)
        self.salt_file = os.path.join(self.vault_dir, ".vault_salt")
        self.key_seed_file = os.path.join(self.vault_dir, ".vault_seed")
        self._salt = self._get_or_create_salt()
        self._key = self._derive_master_key()

    def _get_or_create_salt(self) -> bytes:
        if os.path.isfile(self.salt_file):
            try:
                with open(self.salt_file, "rb") as f:
                    s = f.read()
                if len(s) == 32:
                    return s
            except Exception:
                pass
        salt = os.urandom(32)
        with open(self.salt_file, "wb") as f:
            f.write(salt)
        return salt

    def _derive_master_key(self) -> bytes:
        seed = b""
        if os.path.isfile(self.key_seed_file):
            try:
                with open(self.key_seed_file, "rb") as f:
                    seed = f.read()
            except Exception:
                pass
        if len(seed) < 32:
            seed = os.urandom(64)
            with open(self.key_seed_file, "wb") as f:
                f.write(seed)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._salt,
            iterations=100_000,
        )
        return kdf.derive(seed)

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypts data using AES-GCM with a fresh 12-byte nonce."""
        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        # Format: nonce (12 bytes) + ciphertext/tag
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypts and authenticates AES-GCM data."""
        if len(encrypted_data) < 28:
            raise ValueError("Ciphertext too short to contain nonce and authentication tag")
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, ciphertext, None)
