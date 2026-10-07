"""core/exposure/manager.py — Central Exposure & Gateway Manager for Muse 4.0."""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("muse.exposure.manager")

DEFAULT_PORT = 18010
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"


class ExposureMode(str, enum.Enum):
    LOCAL = "local"
    NGROK = "ngrok"
    BOTH = "both"
    OFF = "off"


@dataclass
class ExposureState:
    mode: str = "off"
    local_port: int = DEFAULT_PORT
    local_url: str = f"http://127.0.0.1:{DEFAULT_PORT}"
    public_url: Optional[str] = None
    mcp_path: str = "/mcp"
    started_at: Optional[str] = None
    daemon_pid: Optional[int] = None
    ngrok_pid: Optional[int] = None
    ngrok_managed_by_muse: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExposureManager:
    """
    Central exposure manager ensuring all external access to Muse
    routes through the single multiplexed gateway port (:18010).
    """

    _instance: Optional[ExposureManager] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, state_file: Optional[str] = None):
        repo_root = Path(__file__).resolve().parent.parent.parent
        self.state_file = state_file or str(repo_root / "state" / "exposure.json")
        self.port = self.resolve_gateway_port()
        self.state = self._load_state()
        self._initialized = True

    # -------------------------------------------------------------------------
    # Central URL Resolvers (Section 7)
    # -------------------------------------------------------------------------
    @classmethod
    def resolve_gateway_port(cls) -> int:
        """Dynamically resolves port from MUSE_PORT env var or default 18010."""
        env_port = os.environ.get("MUSE_PORT")
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                pass
        return DEFAULT_PORT

    @classmethod
    def get_local_url(cls, port: Optional[int] = None) -> str:
        p = port or cls.resolve_gateway_port()
        return f"http://127.0.0.1:{p}"

    @classmethod
    def get_local_mcp_url(cls, port: Optional[int] = None) -> str:
        return f"{cls.get_local_url(port)}/mcp"

    def get_public_url(self) -> Optional[str]:
        """Discovers active public URL dynamically from ngrok API."""
        tunnel = self.detect_ngrok_tunnel()
        if tunnel and tunnel.get("public_url"):
            self.state.public_url = tunnel["public_url"]
            return tunnel["public_url"]
        return None

    def get_public_mcp_url(self) -> Optional[str]:
        purl = self.get_public_url()
        return f"{purl}/mcp" if purl else None

    def get_active_mcp_url(self) -> str:
        """Returns public MCP if active and verified, otherwise local MCP."""
        p_mcp = self.get_public_mcp_url()
        if p_mcp and self.state.mode in (ExposureMode.NGROK.value, ExposureMode.BOTH.value):
            return p_mcp
        return self.get_local_mcp_url(self.port)

    # -------------------------------------------------------------------------
    # State Persistence (Phase 6)
    # -------------------------------------------------------------------------
    def _load_state(self) -> ExposureState:
        if os.path.isfile(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return ExposureState(**data)
            except Exception:
                pass
        return ExposureState(
            local_port=self.port,
            local_url=self.get_local_url(self.port),
        )

    def save_state(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.state_file)), exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning("Could not persist exposure state: %s", e)

    # -------------------------------------------------------------------------
    # Port & Process Management (Phase 5)
    # -------------------------------------------------------------------------
    def is_port_listening(self, port: Optional[int] = None) -> bool:
        """Checks if a TCP socket is currently bound on 127.0.0.1:<port>."""
        import socket
        p = port or self.port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", p)) == 0

    def is_gateway_healthy(self, port: Optional[int] = None) -> bool:
        """Sends HTTP request to /health to verify it is an authentic Muse daemon."""
        p = port or self.port
        # If running inside daemon's event loop on same port, avoid self-deadlock
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running() and p == self.port and 'simpled.py' in sys.argv[0]:
                return True
        except RuntimeError:
            pass

        url = f"http://127.0.0.1:{p}/health"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "muse-exposure-manager"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("ok") is True
        except Exception:
            pass
        return False

    def get_port_owner_pid(self, port: Optional[int] = None) -> Optional[int]:
        """Finds PID of process listening on port without killing anything."""
        p = port or self.port
        if sys.platform == "win32":
            try:
                cmd = f"Get-NetTCPConnection -LocalPort {p} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"
                res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=5)
                output = res.stdout.strip()
                if output:
                    return int(output.split()[0])
                if output and output.isdigit():
                    return int(output)
            except Exception:
                pass
        return None

    # -------------------------------------------------------------------------
    # ngrok Tunnel Discovery & Lifecycle (Phase 4)
    # -------------------------------------------------------------------------
    def detect_ngrok_tunnel(self) -> Optional[Dict[str, Any]]:
        """
        Inspects live ngrok local API at http://127.0.0.1:4040/api/tunnels.
        Never assumes an old or cached URL.
        """
        try:
            req = urllib.request.Request(NGROK_API_URL, headers={"User-Agent": "muse-exposure-manager"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    tunnels = data.get("tunnels", [])
                    # Look strictly for tunnel pointing to our gateway port
                    for t in tunnels:
                        addr = str(t.get("config", {}).get("addr", ""))
                        if str(self.port) in addr and t.get("proto") == "https":
                            return t
        except Exception:
            pass
        return None

    def create_or_connect_ngrok_tunnel(self) -> Optional[str]:
        """
        Connects port 18010 to ngrok.
        1. Checks if tunnel already exists.
        2. If ngrok daemon is running on 4040, creates tunnel via API.
        3. If ngrok is not running, launches 'ngrok http <port>'.
        """
        existing = self.detect_ngrok_tunnel()
        if existing and existing.get("public_url"):
            addr = str(existing.get("config", {}).get("addr", ""))
            if str(self.port) in addr:
                return existing["public_url"]

        # Try creating tunnel via ngrok API on port 4040
        try:
            payload = json.dumps({"name": "muse_gateway", "addr": str(self.port), "proto": "http"}).encode("utf-8")
            req = urllib.request.Request(NGROK_API_URL, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status in (200, 201):
                    data = json.loads(resp.read().decode("utf-8"))
                    purl = data.get("public_url")
                    if purl:
                        return purl
        except Exception:
            pass

        # ngrok process not running or failed to create via API; spawn ngrok subprocess
        try:
            proc = subprocess.Popen(
                ["ngrok", "http", str(self.port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.state.ngrok_pid = proc.pid
            self.state.ngrok_managed_by_muse = True

            # Poll for public URL up to 8 seconds
            for _ in range(16):
                time.sleep(0.5)
                tunnel = self.detect_ngrok_tunnel()
                if tunnel and tunnel.get("public_url"):
                    return tunnel["public_url"]
        except Exception as e:
            logger.error("Could not spawn ngrok: %s", e)

        return None

    def stop_ngrok_exposure(self) -> None:
        """Stops public ngrok tunnel cleanly without killing unrelated user processes."""
        # 1. Delete muse_gateway tunnel via API
        try:
            req = urllib.request.Request(f"{NGROK_API_URL}/muse_gateway", method="DELETE")
            urllib.request.urlopen(req, timeout=3.0)
        except Exception:
            pass

        # 2. If Muse spawned the ngrok process, terminate it
        if self.state.ngrok_managed_by_muse and self.state.ngrok_pid:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(self.state.ngrok_pid)], capture_output=True)
                else:
                    os.kill(self.state.ngrok_pid, 9)
            except Exception:
                pass
            self.state.ngrok_pid = None
            self.state.ngrok_managed_by_muse = False

        self.state.public_url = None

    # -------------------------------------------------------------------------
    # Mode Transitions & Lifecycle (Section 1)
    # -------------------------------------------------------------------------
    def ensure_gateway_running(self) -> bool:
        """Ensures local gateway is listening on port 18010. Spawns daemon if offline."""
        if self.is_gateway_healthy():
            return True

        if self.is_port_listening():
            # Port listening but not responding healthy to /health
            pid = self.get_port_owner_pid()
            logger.warning("Port %d is bound by PID %s but /health failed", self.port, pid)
            return False

        # Launch daemon
        daemon_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "daemon", "simpled.py")
        daemon_script = os.path.normpath(daemon_script)
        try:
            proc = subprocess.Popen(
                [sys.executable, daemon_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=os.path.dirname(daemon_script) + "/..",
            )
            self.state.daemon_pid = proc.pid
            # Poll /health up to 8 seconds
            for _ in range(16):
                time.sleep(0.5)
                if self.is_gateway_healthy():
                    return True
        except Exception as e:
            logger.error("Failed to start gateway daemon: %s", e)
        return False

    def set_mode(self, mode: ExposureMode, is_self: bool = False) -> Dict[str, Any]:
        """Transitions exposure mode between LOCAL, NGROK, BOTH, OFF."""
        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        if mode == ExposureMode.OFF:
            self.stop_ngrok_exposure()
            # Stop daemon if managed by Muse or listening
            target_pid = self.state.daemon_pid or (None if is_self else self.get_port_owner_pid())
            if not is_self and target_pid:
                try:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(target_pid)], capture_output=True)
                    else:
                        os.kill(target_pid, 9)
                except Exception:
                    pass
                self.state.daemon_pid = None

            self.state.mode = ExposureMode.OFF.value
            self.state.public_url = None
            self.state.started_at = None
            self.save_state()
            return {"mode": "off", "status": "STOPPED", "local_url": None, "public_url": None}

        # For LOCAL, NGROK, or BOTH: ensure gateway is running
        if not is_self:
            gateway_ok = self.ensure_gateway_running()
            if not gateway_ok:
                return {"error": f"Failed to start local gateway on port {self.port}", "mode": self.state.mode}

        if mode == ExposureMode.LOCAL:
            self.stop_ngrok_exposure()
            self.state.mode = ExposureMode.LOCAL.value
            self.state.public_url = None
            self.state.started_at = self.state.started_at or now
            self.save_state()
            return {
                "mode": "local",
                "status": "ONLINE",
                "local_url": self.get_local_url(self.port),
                "local_mcp": self.get_local_mcp_url(self.port),
                "public_url": None,
                "public_mcp": None,
            }

        if mode in (ExposureMode.NGROK, ExposureMode.BOTH):
            purl = self.create_or_connect_ngrok_tunnel()
            if not purl:
                return {
                    "error": "Could not establish ngrok tunnel. Verify ngrok is installed or run `ngrok http 18010`.",
                    "mode": self.state.mode,
                }
            self.state.public_url = purl
            self.state.mode = mode.value
            self.state.started_at = self.state.started_at or now
            self.save_state()
            return {
                "mode": mode.value,
                "status": "ONLINE",
                "local_url": self.get_local_url(self.port),
                "local_mcp": self.get_local_mcp_url(self.port),
                "public_url": purl,
                "public_mcp": f"{purl}/mcp",
            }

        return {"error": f"Unknown mode: {mode}"}

    def get_status(self, is_self: bool = False) -> Dict[str, Any]:
        """Returns comprehensive machine-readable exposure and gateway status."""
        self.state = self._load_state()
        daemon_online = True if is_self else self.is_gateway_healthy()
        
        tunnel = self.detect_ngrok_tunnel()
        tunnel_url = tunnel.get("public_url") if tunnel else None
        ngrok_connected = bool(tunnel_url)

        purl = None
        if self.state.mode in (ExposureMode.NGROK.value, ExposureMode.BOTH.value):
            purl = tunnel_url or self.state.public_url
        elif ngrok_connected and self.state.mode != ExposureMode.OFF.value:
            purl = tunnel_url

        active_mode = self.state.mode
        if not daemon_online and active_mode != ExposureMode.OFF.value:
            active_mode = "degraded"

        return {
            "gateway": {
                "status": "ONLINE" if daemon_online else "OFFLINE",
                "port": self.port,
                "local_url": self.get_local_url(self.port),
                "local_mcp": self.get_local_mcp_url(self.port),
                "health_url": f"{self.get_local_url(self.port)}/health",
                "dashboard_url": f"{self.get_local_url(self.port)}/dashboard",
            },
            "exposure": {
                "mode": active_mode,
                "public_url": purl,
                "public_mcp": f"{purl}/mcp" if purl else None,
                "ngrok_connected": ngrok_connected,
                "started_at": self.state.started_at,
            },
            "security": {
                "default_mode": "LOCAL",
                "public_access_policy": "STRICT_CAPABILITY_FILTERED",
            },
        }
