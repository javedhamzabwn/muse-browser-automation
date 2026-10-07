"""core/obscura_downloader.py — Automatic download and setup for Obscura stealth browser."""

from __future__ import annotations

import io
import json
import os
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from typing import Optional

GITHUB_REPO = "h4ckf0r0day/obscura"
FALLBACK_VERSION = "v0.2.3"


def get_default_obscura_dir() -> str:
    """Returns the default directory where Obscura binaries are stored."""
    if os.environ.get("OBSCURA_DIR"):
        return os.environ["OBSCURA_DIR"]
    return os.path.join(os.path.expanduser("~"), "obscura")


def get_obscura_executable_path(base_dir: Optional[str] = None) -> str:
    """Returns full path to the obscura executable."""
    bdir = base_dir or get_default_obscura_dir()
    exe_name = "obscura.exe" if sys.platform == "win32" else "obscura"
    return os.path.join(bdir, exe_name)


def detect_asset_name() -> str:
    """Detects appropriate upstream release asset name for current OS and architecture."""
    os_name = sys.platform
    machine = platform.machine().lower()

    if os_name == "win32":
        return "obscura-x86_64-windows-stealth.zip"
    elif os_name == "darwin":
        arch = "aarch64" if "arm" in machine or "aarch64" in machine else "x86_64"
        return f"obscura-{arch}-macos-stealth.tar.gz"
    elif os_name.startswith("linux"):
        arch = "aarch64" if "arm" in machine or "aarch64" in machine else "x86_64"
        return f"obscura-{arch}-linux-stealth.tar.gz"
    raise RuntimeError(f"Unsupported platform for prebuilt Obscura: {os_name} {machine}")


def get_download_url() -> str:
    """Fetches the latest download URL from GitHub Releases, with pinned fallback."""
    asset_name = detect_asset_name()
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Muse-Browser-Automation/3.0"})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for asset in data.get("assets", []):
                if asset.get("name") == asset_name:
                    return str(asset.get("browser_download_url"))
    except Exception as e:
        print(f"[obscura_downloader] Warning: GitHub API release query failed ({e}); using pinned release fallback.")

    # Pinned fallback URL
    return f"https://github.com/{GITHUB_REPO}/releases/download/{FALLBACK_VERSION}/{asset_name}"


def ensure_obscura_installed(target_dir: Optional[str] = None, force_reinstall: bool = False) -> str:
    """Ensures Obscura binary exists. If missing, downloads and extracts automatically."""
    bdir = target_dir or get_default_obscura_dir()
    exe_path = get_obscura_executable_path(bdir)

    if os.path.isfile(exe_path) and not force_reinstall:
        return exe_path

    os.makedirs(bdir, exist_ok=True)
    asset_name = detect_asset_name()

    # Check for local pre-downloaded archive first
    repo_obscura = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "obscura"))
    candidate_archives = [
        os.path.join(bdir, asset_name),
        os.path.join(repo_obscura, asset_name),
        os.path.join(repo_obscura, "obscura-x86_64-windows-stealth.zip"),
        os.path.join(os.getcwd(), "obscura", asset_name),
    ]

    local_archive = next((p for p in candidate_archives if os.path.isfile(p)), None)
    if local_archive:
        print(f"[obscura_downloader] Found local archive: {local_archive}. Extracting to {bdir}...")
        if local_archive.endswith(".zip"):
            with zipfile.ZipFile(local_archive) as zf:
                zf.extractall(bdir)
        elif local_archive.endswith(".tar.gz"):
            with tarfile.open(local_archive, mode="r:gz") as tf:
                tf.extractall(bdir)
    else:
        download_url = get_download_url()
        print(f"[obscura_downloader] Obscura binary missing. Auto-downloading {asset_name} from:")
        print(f"  {download_url}")
        print(f"  Target: {bdir}")

        req = urllib.request.Request(download_url, headers={"User-Agent": "Muse-Browser-Automation/3.0"})
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            content = resp.read()

        print(f"[obscura_downloader] Downloaded {len(content) / (1024 * 1024):.1f} MB. Extracting...")

        if asset_name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                zf.extractall(bdir)
        elif asset_name.endswith(".tar.gz"):
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tf:
                tf.extractall(bdir)

    # Search for extracted obscura binary if extracted in nested folder
    if not os.path.isfile(exe_path):
        for root, _, files in os.walk(bdir):
            for f in files:
                if f.lower() in ("obscura.exe", "obscura"):
                    nested_path = os.path.join(root, f)
                    if nested_path != exe_path:
                        shutil.move(nested_path, exe_path)

    # Set executable permissions on Unix
    if sys.platform != "win32" and os.path.isfile(exe_path):
        os.chmod(exe_path, 0o755)

    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"Failed to extract Obscura executable to {exe_path}")

    print(f"[obscura_downloader] Obscura successfully installed at {exe_path}")
    return exe_path


if __name__ == "__main__":
    path = ensure_obscura_installed()
    print(f"Obscura ready: {path} (exists: {os.path.isfile(path)})")
