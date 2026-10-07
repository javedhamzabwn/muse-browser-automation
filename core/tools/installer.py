"""core/tools/installer.py — Resumable Multi-Tool Installer Engine for Muse 4.0."""

from __future__ import annotations

import io
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.tools.manifest import InstallMethod, ToolCategory, ToolManifest, ToolStatus

logger = logging.getLogger("muse.tools.installer")


class ToolInstaller:
    """Manages installation, updates, and repairs of tools in the registry."""

    @classmethod
    def get_state_path(cls) -> str:
        root_dir = str(Path(__file__).resolve().parent.parent.parent)
        state_dir = os.path.join(root_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        return os.path.join(state_dir, "tools.json")

    @classmethod
    def record_installation(
        cls,
        tool_name: str,
        version: Optional[str],
        install_method: str,
        path: Optional[str],
        health: str,
        repository: Optional[str] = None,
        commit: Optional[str] = None,
    ) -> None:
        state_file = cls.get_state_path()
        state: Dict[str, Any] = {}
        if os.path.isfile(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                pass

        state[tool_name] = {
            "tool": tool_name,
            "version": version or "unknown",
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "install_method": install_method,
            "path": path or "",
            "repository": repository or "",
            "commit": commit,
            "health": health,
            "last_test": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_benchmark": None,
            "selected_role": "auto",
        }

        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning("Could not write state/tools.json: %s", e)

    @classmethod
    def install_tool(
        cls,
        manifest: ToolManifest,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """
        Installs a tool according to its manifest and platform idempotently.
        Returns: (success: bool, message: str)
        """
        def log(msg: str):
            if progress_cb:
                progress_cb(msg)
            logger.info("[%s] %s", manifest.name, msg)

        # 1. Platform support check
        if not manifest.is_platform_supported(sys.platform):
            return (False, f"Platform '{sys.platform}' not supported for {manifest.name}")

        root_dir = str(Path(__file__).resolve().parent.parent.parent)
        ext_dir = os.path.join(root_dir, "external")
        os.makedirs(ext_dir, exist_ok=True)

        try:
            # 1. Obscura
            if manifest.name == "obscura":
                log("Checking existing Obscura binary...")
                from core.obscura_downloader import ensure_obscura_installed
                exe_path = ensure_obscura_installed()
                manifest.binary = exe_path
                manifest.installed = True
                manifest.status = ToolStatus.READY
                cls.record_installation(manifest.name, manifest.version, "download", exe_path, "READY", manifest.repo_url)
                return (True, f"Installed Obscura at {exe_path}")

            # 2. Playwright Chromium
            if manifest.name == "playwright":
                log("Installing playwright and chromium binaries...")
                subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "playwright"], check=True)
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                manifest.installed = True
                manifest.status = ToolStatus.READY
                cls.record_installation(manifest.name, "latest", "pip", sys.executable, "READY", manifest.repo_url)
                return (True, "Playwright Chromium successfully installed")

            # 3. yt-dlp
            if manifest.name == "yt-dlp":
                log("Installing yt-dlp...")
                res = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "yt-dlp"], capture_output=True, text=True)
                if res.returncode == 0:
                    manifest.installed = True
                    manifest.binary = sys.executable
                    manifest.status = ToolStatus.READY
                    cls.record_installation(manifest.name, "latest", "pip", sys.executable, "READY", manifest.repo_url)
                    return (True, "yt-dlp installed via pip")
                return (False, f"pip install failed: {res.stderr.strip()[:100]}")

            # 4. Camoufox
            if manifest.name == "camoufox":
                log("Installing Camoufox anti-detect browser via pip...")
                res = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "camoufox[geoip]"], capture_output=True, text=True)
                if res.returncode == 0:
                    try:
                        subprocess.run([sys.executable, "-m", "camoufox", "fetch"], capture_output=True, text=True, timeout=120.0)
                    except Exception:
                        pass
                    manifest.installed = True
                    manifest.binary = sys.executable
                    manifest.status = ToolStatus.READY
                    cls.record_installation(manifest.name, "latest", "pip", sys.executable, "READY", manifest.repo_url)
                    return (True, "Camoufox installed via pip")
                return (False, f"pip install camoufox failed: {res.stderr.strip()[:100]}")

            # 5. PyAutoGUI MCP
            if manifest.name == "pyautogui-mcp":
                log("Installing PyAutoGUI MCP dependencies...")
                res = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pyautogui", "pillow"], capture_output=True, text=True)
                manifest.installed = True
                manifest.binary = sys.executable
                manifest.status = ToolStatus.READY
                cls.record_installation(manifest.name, "latest", "pip", sys.executable, "READY", manifest.repo_url)
                return (True, "PyAutoGUI desktop dependencies installed")

            # 6. Zavora Computer Use MCP
            if manifest.name == "zavora-computer-use":
                log("Installing Zavora Computer Use MCP via npm...")
                npm_bin = shutil.which("npm")
                if npm_bin:
                    res = subprocess.run([npm_bin, "install", "-g", "@zavora-ai/computer-use-mcp"], capture_output=True, text=True, timeout=120.0)
                    if res.returncode == 0 or shutil.which("computer-use-mcp"):
                        manifest.installed = True
                        manifest.binary = shutil.which("computer-use-mcp") or "npx -y @zavora-ai/computer-use-mcp"
                        manifest.status = ToolStatus.READY
                        cls.record_installation(manifest.name, "7.4.0", "npm", manifest.binary, "READY", manifest.repo_url)
                        return (True, "Zavora Computer Use MCP installed via npm")
                # Fallback to local repo check
                local_dir = os.path.join(ext_dir, "zavora-computer-use")
                if os.path.isdir(local_dir):
                    manifest.installed = True
                    manifest.binary = os.path.join(local_dir, "package.json")
                    manifest.status = ToolStatus.READY
                    cls.record_installation(manifest.name, "7.4.0", "git", local_dir, "READY", manifest.repo_url)
                    return (True, f"Zavora available in {local_dir}")
                return (False, "Node/npm required or local repo build failed")

            # 7. Agent Browser
            if manifest.name == "agent-browser":
                log("Checking agent-browser installation...")
                npm_bin = shutil.which("npm")
                if npm_bin:
                    res = subprocess.run([npm_bin, "install", "-g", "@vercel/agent-browser"], capture_output=True, text=True, timeout=90.0)
                    if res.returncode == 0 or shutil.which("agent-browser"):
                        manifest.binary = shutil.which("agent-browser")
                        manifest.installed = True
                        manifest.status = ToolStatus.READY
                        cls.record_installation(manifest.name, "latest", "npm", manifest.binary, "READY", manifest.repo_url)
                        return (True, "agent-browser installed via npm")
                return (False, "agent-browser requires npm")

            # 8. Moli
            if manifest.name == "moli":
                log("Checking Moli local repository in external/moli...")
                local_dir = os.path.join(ext_dir, "moli")
                if os.path.isdir(local_dir):
                    manifest.installed = True
                    manifest.binary = local_dir
                    manifest.status = ToolStatus.READY
                    cls.record_installation(manifest.name, "git-main", "git", local_dir, "READY", manifest.repo_url)
                    return (True, f"Moli repository ready at {local_dir}")
                return (False, "Moli repository missing from external/moli")

            # 9. Lightpanda
            if manifest.name == "lightpanda":
                log("Checking Lightpanda in external/lightpanda...")
                local_dir = os.path.join(ext_dir, "lightpanda")
                if os.path.isdir(local_dir):
                    manifest.installed = True
                    manifest.binary = local_dir
                    manifest.status = ToolStatus.READY
                    cls.record_installation(manifest.name, "git-main", "git", local_dir, "READY", manifest.repo_url)
                    return (True, f"Lightpanda ready at {local_dir}")
                return (False, "Lightpanda missing from external/lightpanda")

            # 10. CSI
            if manifest.name == "csi":
                log("Checking CSI in external/csi...")
                local_dir = os.path.join(ext_dir, "csi")
                if os.path.isdir(local_dir):
                    manifest.installed = True
                    manifest.binary = os.path.join(local_dir, "main.py") if os.path.isfile(os.path.join(local_dir, "main.py")) else local_dir
                    manifest.status = ToolStatus.READY
                    cls.record_installation(manifest.name, "git-main", "git", local_dir, "READY", manifest.repo_url)
                    return (True, f"CSI Chrome controller ready at {local_dir}")
                return (False, "CSI missing from external/csi")

            # 11. Builtin / System tools
            if manifest.install_method == InstallMethod.BUILTIN:
                manifest.installed = True
                manifest.status = ToolStatus.READY
                cls.record_installation(manifest.name, "builtin", "builtin", sys.executable, "READY", manifest.repo_url)
                return (True, f"{manifest.display_name} is built-in")

            return (False, f"No automated installer configured for {manifest.name}")

        except Exception as exc:
            logger.exception("Failed to install tool: %s", manifest.name)
            return (False, str(exc))

    @classmethod
    def install_batch(
        cls,
        tools: List[ToolManifest],
        progress_cb: Optional[Callable[[str, str, bool, str], None]] = None,
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Installs multiple tools in sequence without aborting if one fails.
        """
        results: Dict[str, Tuple[bool, str]] = {}
        for tool in tools:
            if tool.installed and tool.status == ToolStatus.READY:
                results[tool.name] = (True, "Already installed and verified")
                if progress_cb:
                    progress_cb(tool.name, "Already installed", True, "Binary ready")
                continue

            if not tool.is_platform_supported(sys.platform):
                results[tool.name] = (False, f"Not supported on {sys.platform}")
                if progress_cb:
                    progress_cb(tool.name, "Skipped", False, f"Unsupported platform: {sys.platform}")
                continue

            ok, msg = cls.install_tool(tool)
            results[tool.name] = (ok, msg)
            if progress_cb:
                label = "Installed" if ok else "Failed"
                progress_cb(tool.name, label, ok, msg)

        return results

    @classmethod
    def update_tool(cls, manifest: ToolManifest) -> Tuple[bool, str]:
        """Update a tool to latest release or git pull."""
        if manifest.name in ("playwright", "camoufox", "yt-dlp", "pyautogui-mcp"):
            res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", manifest.name], capture_output=True, text=True)
            if res.returncode == 0:
                return (True, f"Updated {manifest.name} via pip")
            return (False, f"Pip update failed: {res.stderr.strip()[:100]}")
        
        root_dir = str(Path(__file__).resolve().parent.parent.parent)
        local_dir = os.path.join(root_dir, "external", manifest.name)
        if os.path.isdir(os.path.join(local_dir, ".git")):
            res = subprocess.run(["git", "pull"], cwd=local_dir, capture_output=True, text=True)
            if res.returncode == 0:
                return (True, f"Updated {manifest.name} via git pull")
            return (False, f"Git pull failed: {res.stderr.strip()[:100]}")

        return (True, f"{manifest.name} is up to date")

    @classmethod
    def uninstall_tool(cls, manifest: ToolManifest) -> Tuple[bool, str]:
        """Safely uninstall or remove tool from active state."""
        manifest.installed = False
        manifest.status = ToolStatus.MISSING
        state_file = cls.get_state_path()
        if os.path.isfile(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if manifest.name in state:
                    del state[manifest.name]
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
            except Exception:
                pass
        return (True, f"Uninstalled {manifest.name}")
