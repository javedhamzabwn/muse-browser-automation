"""core/tools/lifecycle.py — Process and Service Lifecycle Manager for Tools."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Dict, Optional

from core.tools.manifest import ToolManifest, ToolStatus

logger = logging.getLogger("muse.tools.lifecycle")


class ToolLifecycleManager:
    """Manages long-running tool background processes (CSI daemon, Obscura CDP, Moli)."""

    def __init__(self):
        self._running_processes: Dict[str, subprocess.Popen] = {}

    def is_running(self, manifest: ToolManifest) -> bool:
        """Check if background process for tool is active."""
        proc = self._running_processes.get(manifest.name)
        if proc and proc.poll() is None:
            return True
        return False

    def start(self, manifest: ToolManifest, extra_args: Optional[list[str]] = None) -> bool:
        """Starts background tool process if start_command is configured."""
        if self.is_running(manifest):
            return True

        if not manifest.binary:
            logger.warning("Cannot start %s: binary not resolved", manifest.name)
            return False

        # Custom start behavior
        if manifest.name == "obscura":
            try:
                cmd = [manifest.binary, "--remote-debugging-port=9222"]
                if extra_args:
                    cmd.extend(extra_args)
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                self._running_processes["obscura"] = proc
                manifest.status = ToolStatus.RUNNING
                return True
            except Exception as e:
                logger.error("Failed to start Obscura process: %s", e)
                return False

        if manifest.start_command:
            try:
                cmd = [manifest.binary if c == manifest.name else c for c in manifest.start_command]
                if extra_args:
                    cmd.extend(extra_args)
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                self._running_processes[manifest.name] = proc
                manifest.status = ToolStatus.RUNNING
                return True
            except Exception as e:
                logger.error("Failed to start %s process: %s", manifest.name, e)
                return False

        return True

    def stop(self, manifest: ToolManifest) -> bool:
        """Stops background tool process."""
        proc = self._running_processes.pop(manifest.name, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                manifest.status = ToolStatus.READY
                return True
            except Exception as e:
                logger.error("Failed to stop %s: %s", manifest.name, e)
                return False
        return True

    def stop_all(self) -> None:
        """Terminate all background tool processes."""
        for name in list(self._running_processes.keys()):
            proc = self._running_processes.pop(name, None)
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
