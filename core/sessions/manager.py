"""core/sessions/manager.py — Safe Browser Profile & Session Management."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("muse.sessions")


@dataclass
class SessionProfile:
    """Represents an isolated browser session/profile."""

    name: str
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    browser_type: str = "auto"
    custom_browser_path: Optional[str] = None
    cookie_count: int = 0
    domains: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProfileManager:
    """Manages browser profiles, cookies, and authentication state securely."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.join(os.path.expanduser("~"), ".muse", "profiles")
        os.makedirs(self.base_dir, exist_ok=True)
        self.active_profile_file = os.path.join(self.base_dir, "active_profile.txt")
        self._ensure_default_profile()

    def _ensure_default_profile(self) -> None:
        if not self.list_profiles():
            self.create_profile("default")
            self.set_active_profile("default")

    def _get_profile_dir(self, name: str) -> str:
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
        return os.path.join(self.base_dir, safe_name)

    def list_profiles(self) -> List[SessionProfile]:
        """List all configured profiles with summary metadata (no raw cookie values)."""
        profiles = []
        if not os.path.isdir(self.base_dir):
            return profiles

        for entry in os.listdir(self.base_dir):
            pdir = os.path.join(self.base_dir, entry)
            if os.path.isdir(pdir):
                meta_file = os.path.join(pdir, "meta.json")
                if os.path.isfile(meta_file):
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        profiles.append(SessionProfile(**data))
                    except Exception:
                        pass
        return sorted(profiles, key=lambda p: p.name)

    def get_profile(self, name: str) -> Optional[SessionProfile]:
        pdir = self._get_profile_dir(name)
        meta_file = os.path.join(pdir, "meta.json")
        if os.path.isfile(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SessionProfile(**data)
            except Exception:
                pass
        return None

    def create_profile(
        self,
        name: str,
        clone_from: Optional[str] = None,
        custom_browser_path: Optional[str] = None,
    ) -> SessionProfile:
        pdir = self._get_profile_dir(name)
        os.makedirs(pdir, exist_ok=True)

        if clone_from:
            src_dir = self._get_profile_dir(clone_from)
            if os.path.isdir(src_dir):
                for item in os.listdir(src_dir):
                    s = os.path.join(src_dir, item)
                    d = os.path.join(pdir, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    elif item != "meta.json":
                        shutil.copy2(s, d)

        prof = SessionProfile(
            name=name,
            created_at=time.time(),
            last_used_at=time.time(),
            custom_browser_path=custom_browser_path,
        )
        self._save_profile(prof)
        return prof

    def delete_profile(self, name: str) -> bool:
        if name.lower() == "default":
            logger.warning("Cannot delete default profile")
            return False
        pdir = self._get_profile_dir(name)
        if os.path.isdir(pdir):
            shutil.rmtree(pdir, ignore_errors=True)
            if self.get_active_profile() == name:
                self.set_active_profile("default")
            return True
        return False

    def get_active_profile(self) -> str:
        if os.path.isfile(self.active_profile_file):
            try:
                with open(self.active_profile_file, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if val and os.path.isdir(self._get_profile_dir(val)):
                    return val
            except Exception:
                pass
        return "default"

    def set_active_profile(self, name: str) -> bool:
        pdir = self._get_profile_dir(name)
        if not os.path.isdir(pdir):
            return False
        with open(self.active_profile_file, "w", encoding="utf-8") as f:
            f.write(name)
        return True

    def import_cookies(self, profile_name: str, cookies: List[Dict[str, Any]]) -> int:
        """Import cookies list into profile."""
        pdir = self._get_profile_dir(profile_name)
        os.makedirs(pdir, exist_ok=True)
        cookie_file = os.path.join(pdir, "cookies.json")

        existing: List[Dict[str, Any]] = []
        if os.path.isfile(cookie_file):
            try:
                with open(cookie_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        # Merge by (name, domain, path)
        merged_map = {(c.get("name"), c.get("domain"), c.get("path", "/")): c for c in existing}
        for c in cookies:
            key = (c.get("name"), c.get("domain"), c.get("path", "/"))
            merged_map[key] = c

        merged = list(merged_map.values())
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(merged, f)

        # Update metadata
        prof = self.get_profile(profile_name) or SessionProfile(name=profile_name)
        prof.cookie_count = len(merged)
        prof.domains = sorted(list({c.get("domain", "") for c in merged if c.get("domain")}))
        self._save_profile(prof)
        return len(cookies)

    def export_cookies_masked(self, profile_name: str, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export safe, masked cookies (never exposes raw cookie value in logs or output)."""
        pdir = self._get_profile_dir(profile_name)
        cookie_file = os.path.join(pdir, "cookies.json")
        if not os.path.isfile(cookie_file):
            return []

        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                raw_cookies = json.load(f)
            masked = []
            for c in raw_cookies:
                c_domain = c.get("domain", "")
                if domain and domain.lower() not in c_domain.lower():
                    continue
                masked.append({
                    "name": c.get("name"),
                    "domain": c.get("domain"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", False),
                    "httpOnly": c.get("httpOnly", False),
                    "value": "****** [MASKED]",
                })
            return masked
        except Exception:
            return []

    def clear_cookies(self, profile_name: str, domain: Optional[str] = None) -> int:
        """Clear cookies for a domain or whole profile."""
        pdir = self._get_profile_dir(profile_name)
        cookie_file = os.path.join(pdir, "cookies.json")
        if not os.path.isfile(cookie_file):
            return 0

        with open(cookie_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        if domain:
            kept = [c for c in cookies if domain.lower() not in c.get("domain", "").lower()]
            removed = len(cookies) - len(kept)
            with open(cookie_file, "w", encoding="utf-8") as f:
                json.dump(kept, f)
        else:
            removed = len(cookies)
            os.remove(cookie_file)

        prof = self.get_profile(profile_name)
        if prof:
            prof.cookie_count = 0 if not domain else len(kept)
            self._save_profile(prof)
        return removed

    def _save_profile(self, prof: SessionProfile) -> None:
        pdir = self._get_profile_dir(prof.name)
        os.makedirs(pdir, exist_ok=True)
        meta_file = os.path.join(pdir, "meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(prof.to_dict(), f, indent=2)
