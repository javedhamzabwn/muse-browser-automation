"""core/tools/detector.py — System and Binary Detection Engine for Muse 4.0."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from typing import Optional, Tuple

from core.tools.manifest import ToolManifest, ToolStatus


class ToolDetector:
    """Detects whether binaries and tools are installed and operational on current host."""

    @staticmethod
    def find_binary(name: str, candidate_paths: Optional[list[str]] = None) -> Optional[str]:
        """Search PATH and known installation locations for binary."""
        # 1. Search system PATH
        found = shutil.which(name)
        if found:
            return os.path.abspath(found)

        # 2. Add .exe on Windows if not provided
        if sys.platform == "win32" and not name.lower().endswith(".exe"):
            found = shutil.which(f"{name}.exe")
            if found:
                return os.path.abspath(found)

        # 3. Check candidate paths
        if candidate_paths:
            for p in candidate_paths:
                expanded = os.path.expanduser(os.path.expandvars(p))
                if os.path.isfile(expanded):
                    return os.path.abspath(expanded)
                if sys.platform == "win32" and not expanded.lower().endswith(".exe"):
                    exe = f"{expanded}.exe"
                    if os.path.isfile(exe):
                        return os.path.abspath(exe)

        return None

    @staticmethod
    def is_python_module_available(module_name: str) -> bool:
        """Check if python package is importable."""
        try:
            return importlib.util.find_spec(module_name) is not None
        except Exception:
            return False

    @classmethod
    def detect_tool(cls, manifest: ToolManifest) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Detects installation state and version for given tool manifest.
        Returns: (installed: bool, resolved_binary: Optional[str], version: Optional[str])
        """
        resolved_bin: Optional[str] = None
        version: Optional[str] = None

        # Builtin tools (like http_static or playwright internal)
        if manifest.name == "http_static":
            return (True, sys.executable, f"python-{sys.version.split()[0]}")

        if manifest.name == "playwright":
            has_mod = cls.is_python_module_available("playwright")
            if has_mod:
                try:
                    import playwright
                    return (True, sys.executable, getattr(playwright, "__version__", "installed"))
                except Exception:
                    return (True, sys.executable, "installed")
            return (False, None, None)

        if manifest.name == "obscura":
            from core.obscura_downloader import get_default_obscura_dir, get_obscura_executable_path
            target_path = get_obscura_executable_path()
            if os.path.isfile(target_path):
                return (True, target_path, "v0.2.3")
            # Also check PATH
            bin_path = cls.find_binary("obscura")
            if bin_path:
                return (True, bin_path, "v0.2.3")
            return (False, None, None)

        if manifest.name == "chrome":
            # Check standard Chrome locations
            chrome_candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
            ]
            bin_path = cls.find_binary("chrome", chrome_candidates)
            if bin_path:
                return (True, bin_path, "installed")
            return (False, None, None)

        if manifest.name == "camoufox":
            if cls.is_python_module_available("camoufox"):
                try:
                    import camoufox
                    ver = getattr(camoufox, "__version__", "installed")
                    if hasattr(ver, "__version__"):
                        ver = getattr(ver, "__version__")
                    ver_str = str(ver) if not isinstance(ver, str) else ver
                    if "module" in ver_str:
                        ver_str = "installed"
                    return (True, sys.executable, ver_str)
                except Exception:
                    return (True, sys.executable, "installed")
            return (False, None, None)

        root_dir = str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent)
        ext_dir = os.path.join(root_dir, "external")
        tool_ext_dir = os.path.join(ext_dir, manifest.name)

        if manifest.name in ("pyautogui-mcp", "pyautogui"):
            if cls.is_python_module_available("pyautogui") or cls.is_python_module_available("PIL"):
                return (True, sys.executable, "python-api")

        if manifest.name == "zavora-computer-use":
            return (True, "node", "installed")

        if manifest.name == "yt-dlp":
            yt_bin = shutil.which("yt-dlp")
            if yt_bin and os.path.isfile(yt_bin):
                try:
                    res = subprocess.run([yt_bin, "--version"], capture_output=True, text=True, timeout=3.0)
                    if res.returncode == 0:
                        return (True, yt_bin, res.stdout.strip())
                except Exception:
                    pass
                return (True, yt_bin, "installed")
            if cls.is_python_module_available("yt_dlp"):
                try:
                    import yt_dlp.version
                    ver = getattr(yt_dlp.version, "__version__", "pip-installed")
                    return (True, sys.executable, ver)
                except Exception:
                    return (True, sys.executable, "pip-installed")

        if manifest.name == "agent-browser":
            ab_bin = shutil.which("agent-browser")
            if ab_bin and os.path.isfile(ab_bin):
                try:
                    res = subprocess.run([ab_bin, "--version"], capture_output=True, text=True, timeout=3.0)
                    out = (res.stdout or res.stderr).strip()
                    m = re.search(r"(\d+(\.\d+)+)", out)
                    return (True, ab_bin, m.group(1) if m else out)
                except Exception:
                    return (True, ab_bin, "installed")

        # Standard binary detection for external tools (moli, lightpanda, csi, go-mcp-computer-use, etc.)
        candidates = [
            os.path.join(tool_ext_dir, f"{manifest.name}.exe"),
            os.path.join(tool_ext_dir, "bin", f"{manifest.name}.exe"),
            os.path.join(tool_ext_dir, "target", "release", f"{manifest.name}.exe"),
            os.path.join(tool_ext_dir, "zig-out", "bin", f"{manifest.name}.exe"),
            os.path.join(tool_ext_dir, ".venv", "Scripts", f"{manifest.name}.exe"),
        ]
        user_home = os.path.expanduser("~")
        if manifest.name == "moli":
            candidates.extend([
                os.path.join(user_home, ".moli", "bin", "moli.exe"),
                os.path.join(user_home, "moli", "moli.exe"),
                r"C:\moli\moli.exe",
            ])
        elif manifest.name == "lightpanda":
            candidates.extend([
                os.path.join(user_home, ".lightpanda", "lightpanda.exe"),
                os.path.join(user_home, "lightpanda", "lightpanda.exe"),
                r"C:\lightpanda\lightpanda.exe",
            ])
        elif manifest.name == "csi":
            candidates.extend([
                os.path.join(user_home, ".csi", "csi.exe"),
                os.path.join(user_home, "csi", "csi.exe"),
            ])
        elif manifest.name == "go-mcp-computer-use":
            candidates.extend([
                os.path.join(tool_ext_dir, "go-mcp-computer-use.exe"),
                os.path.join(user_home, "go", "bin", "go-mcp-computer-use.exe"),
            ])

        bin_name = manifest.binary or manifest.name
        resolved_bin = cls.find_binary(bin_name, candidates)
        if not resolved_bin or not os.path.isfile(resolved_bin):
            return (False, None, None)

        # Run version command if configured
        if manifest.version_command:
            try:
                cmd = [resolved_bin if c == bin_name else c for c in manifest.version_command]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
                out = (res.stdout or res.stderr).strip()
                # Parse version like 2024.08.01 or 1.2.3
                m = re.search(r"(\d+(\.\d+)+)", out)
                version = m.group(1) if m else (out.splitlines()[0] if out else "installed")
            except Exception:
                version = "installed"
        else:
            version = "installed"

        return (True, resolved_bin, version or "installed")
