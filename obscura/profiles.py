"""
obscura_profiles.py — Manage Obscura browser profiles.

Three profile types:
  1. MAIN    — Persistent profile with user's Chrome cookies. Always kept.
  2. TEMP    — Clone of main profile (has cookies). Auto-deleted when closed.
  3. EMPTY   — Blank profile, no cookies. Auto-deleted when closed.

Usage:
    python obscura_profiles.py main          # Start Obscura with the main profile
    python obscura_profiles.py temp          # Start with a temp copy (has cookies, auto-deletes)
    python obscura_profiles.py empty         # Start with a blank profile (auto-deletes)
    python obscura_profiles.py sync          # Sync Chrome cookies into the main profile
    python obscura_profiles.py list          # List all active profiles
    python obscura_profiles.py cleanup       # Delete all temp/empty profiles
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import urllib.request

import websockets

# ── Configuration ────────────────────────────────────────────────────
OBSCURA_EXE = r"C:\Users\AL Hussain Academy\obscura\obscura.exe"
PROFILES_DIR = r"C:\Users\AL Hussain Academy\obscura"
MAIN_PROFILE = os.path.join(PROFILES_DIR, "profile")
TEMP_DIR = os.path.join(PROFILES_DIR, "temp_profiles")
DAEMON_URL = "http://127.0.0.1:18010/tool"
CREATE_NO_WINDOW = 0x08000000
# ─────────────────────────────────────────────────────────────────────

msg_id = 0

async def cdp(ws, method, session_id=None, **params):
    global msg_id
    msg_id += 1
    req = {"id": msg_id, "method": method, "params": params}
    if session_id:
        req["sessionId"] = session_id
    await ws.send(json.dumps(req))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        resp = json.loads(raw)
        if "id" in resp and resp["id"] == msg_id:
            return resp

def daemon_tool(tool_name, args=None):
    req = urllib.request.Request(
        DAEMON_URL,
        data=json.dumps({"tool": tool_name, "args": args or {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    r = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    if r.get("ok"):
        return r.get("result")
    raise RuntimeError(f"Daemon '{tool_name}' failed: {r.get('error')}")

def is_port_open(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False

def find_free_port(start=9222, end=9250):
    for port in range(start, end):
        if not is_port_open(port):
            return port
    raise RuntimeError("No free ports available in range 9222-9250")

def start_obscura(profile_dir, port):
    os.makedirs(profile_dir, exist_ok=True)
    proc = subprocess.Popen(
        [
            OBSCURA_EXE, "serve",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--stealth",
            "--storage-dir", profile_dir,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    for _ in range(30):
        time.sleep(0.5)
        if is_port_open(port):
            return proc, port
    raise RuntimeError(f"Obscura did not start on port {port} within 15 seconds.")

def save_profile_info(profile_dir, port, profile_type, pid):
    info = {
        "profile_dir": profile_dir,
        "port": port,
        "type": profile_type,
        "pid": pid,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    info_path = os.path.join(profile_dir, ".obscura_profile_info.json")
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)
    return info

def list_profiles():
    profiles = []
    if os.path.exists(MAIN_PROFILE):
        info_path = os.path.join(MAIN_PROFILE, ".obscura_profile_info.json")
        if os.path.exists(info_path):
            with open(info_path) as f:
                profiles.append(json.load(f))
        else:
            profiles.append({"profile_dir": MAIN_PROFILE, "type": "main", "port": 9222})

    if os.path.exists(TEMP_DIR):
        for name in os.listdir(TEMP_DIR):
            pdir = os.path.join(TEMP_DIR, name)
            if os.path.isdir(pdir):
                info_path = os.path.join(pdir, ".obscura_profile_info.json")
                if os.path.exists(info_path):
                    with open(info_path) as f:
                        profiles.append(json.load(f))
                else:
                    profiles.append({"profile_dir": pdir, "type": "unknown"})
    return profiles

def cleanup_temp_profiles():
    deleted = 0
    if os.path.exists(TEMP_DIR):
        for name in os.listdir(TEMP_DIR):
            pdir = os.path.join(TEMP_DIR, name)
            if os.path.isdir(pdir):
                try:
                    shutil.rmtree(pdir)
                    deleted += 1
                except Exception as e:
                    print(f"  Could not delete {pdir}: {e}")
    return deleted

# ── Cookie Sync Logic ────────────────────────────────────────────────

def get_chrome_cookies_via_daemon():
    """Extract full Chrome cookie jar via daemon extension."""
    try:
        health = json.loads(urllib.request.urlopen("http://127.0.0.1:18010/health", timeout=3).read().decode())
        if not (health.get("ok") and health.get("ext")):
            print("[profiles] WARNING: Daemon not healthy or extension not connected.")
            return []
    except Exception:
        print("[profiles] WARNING: Cannot reach daemon at port 18010.")
        return []

    print("[profiles] Extracting cookies from Chrome (full jar)...")
    _tab = daemon_tool("tabs.create", {"url": "about:blank"})
    _tab_id = _tab.get("tabId")
    try:
        jar = daemon_tool("cookies.export_cdp", {"tabId": _tab_id})
    finally:
        try:
            daemon_tool("tabs.close", {"tabId": _tab_id})
        except Exception:
            pass
    raw = jar.get("cookies", []) if isinstance(jar, dict) else []
    print(f"[profiles] Got {len(raw)} cookies from Chrome.")
    return raw

def merge_cookies_to_profile(profile_dir, raw_cookies):
    """Merge raw CDP cookies into Obscura's cookies.json."""
    if not raw_cookies:
        return 0, 0

    def _conv(c):
        domain = c.get("domain", "") or ""
        return {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": domain.lstrip("."),
            "path": c.get("path", "/") or "/",
            "secure": bool(c.get("secure")),
            "httpOnly": bool(c.get("httpOnly")),
            "sameSite": c.get("sameSite") or "Lax",
            "expires": (lambda e: None if e in (None, -1) else int(e))(c.get("expires", -1)),
            "hostOnly": not domain.startswith("."),
        }

    cj_path = os.path.join(profile_dir, "cookies.json")
    existing = []
    if os.path.exists(cj_path):
        try:
            existing = json.load(open(cj_path, encoding="utf-8"))
        except Exception:
            existing = []
            
    idx = {(e.get("domain"), e.get("path"), e.get("name")): i for i, e in enumerate(existing)}
    added = updated = 0
    
    for c in raw_cookies:
        o = _conv(c)
        if not o["name"] or not o["domain"]:
            continue
        key = (o["domain"], o["path"], o["name"])
        if key in idx:
            existing[idx[key]] = o
            updated += 1
        else:
            idx[key] = len(existing)
            existing.append(o)
            added += 1
            
    os.makedirs(profile_dir, exist_ok=True)
    with open(cj_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    return added, updated

async def graceful_stop_obscura(port):
    """Try to gracefully close Obscura via CDP, fallback to taskkill."""
    import subprocess as _sp
    
    # Try CDP Browser.close first
    if is_port_open(port):
        print(f"[profiles] Attempting graceful shutdown on port {port}...")
        try:
            ws_url = f"ws://127.0.0.1:{port}/devtools/browser"
            async with websockets.connect(ws_url, timeout=2) as ws:
                await cdp(ws, "Browser.close")
        except Exception:
            pass
            
    # Wait for graceful exit
    for _ in range(10):
        if not is_port_open(port):
            return True
        time.sleep(0.5)
        
    # Fallback to forceful taskkill
    stop_pid = None
    try:
        r = _sp.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            parts = line.split()
            if (len(parts) >= 5 and parts[0] == "TCP"
                    and parts[1].rsplit(":", 1)[-1] == str(port)
                    and parts[3] == "LISTENING"):
                stop_pid = int(parts[4])
                break
    except Exception as e:
        print(f"[profiles] netstat failed: {e}")
        
    if stop_pid:
        print(f"[profiles] Force stopping Obscura (PID {stop_pid})...")
        _sp.run(["taskkill", "/F", "/PID", str(stop_pid)], capture_output=True, timeout=10)
        for _ in range(10):
            if not is_port_open(port):
                return True
            time.sleep(0.5)
    return not is_port_open(port)

async def sync_cookies_to_main():
    """Sync Chrome cookies into the main Obscura profile (durable)."""
    raw = get_chrome_cookies_via_daemon()
    if not raw:
        return False

    # Stop main Obscura safely so we can merge cookies.json
    if is_port_open(9222):
        closed = await graceful_stop_obscura(9222)
        if not closed:
            print("[profiles] ERROR: port 9222 still open; aborting merge.")
            return False

    # Merge into cookies.json
    added, updated = merge_cookies_to_profile(MAIN_PROFILE, raw)
    print(f"[profiles] cookies.json: {added + updated} total affected ({added} added, {updated} updated).")

    # Restart main Obscura
    print("[profiles] Restarting main Obscura on port 9222...")
    proc, _port = start_obscura(MAIN_PROFILE, 9222)
    save_profile_info(MAIN_PROFILE, 9222, "main", proc.pid)
    print(f"[profiles] Main profile running again (PID {proc.pid}).")
    return True

# ── Commands ─────────────────────────────────────────────────────────

async def cmd_main_profile():
    print("[profiles] === MAIN PROFILE ===")
    if is_port_open(9222):
        print("[profiles] Main profile already running on port 9222.")
    else:
        print("[profiles] Starting main profile...")
        proc, port = start_obscura(MAIN_PROFILE, 9222)
        save_profile_info(MAIN_PROFILE, port, "main", proc.pid)
        print(f"[profiles] Main profile started on port {port} (PID {proc.pid}).")
    print("[profiles] CDP endpoint: ws://127.0.0.1:9222/devtools/browser")

async def cmd_temp_profile():
    print("[profiles] === TEMP PROFILE (with fresh cookies) ===")
    profile_id = f"temp_{uuid.uuid4().hex[:8]}"
    profile_dir = os.path.join(TEMP_DIR, profile_id)

    # 1. Copy main profile structure
    print("[profiles] Cloning main profile...")
    if os.path.exists(MAIN_PROFILE):
        shutil.copytree(MAIN_PROFILE, profile_dir, dirs_exist_ok=True)
    else:
        os.makedirs(profile_dir, exist_ok=True)

    # Remove profile lock file if copied
    lock_file = os.path.join(profile_dir, "SingletonLock")
    if os.path.exists(lock_file):
        os.remove(lock_file)

    # 2. Extract fresh cookies and merge them directly to the TEMP clone before starting
    print("[profiles] Injecting fresh cookies directly into temp profile...")
    raw = get_chrome_cookies_via_daemon()
    if raw:
        added, updated = merge_cookies_to_profile(profile_dir, raw)
        print(f"[profiles] Injected {added + updated} fresh cookies into temp profile.")

    # 3. Start Obscura on a new port
    port = find_free_port(9223)
    print(f"[profiles] Starting temp profile on port {port}...")
    proc, port = start_obscura(profile_dir, port)
    save_profile_info(profile_dir, port, "temp", proc.pid)

    print(f"[profiles] Temp profile ready!")
    print(f"[profiles] CDP endpoint: ws://127.0.0.1:{port}/devtools/browser")
    print(f"[profiles] Profile dir: {profile_dir}")
    print(f"[profiles] This profile will be deleted when you run: python obscura_profiles.py cleanup")
    return port

async def cmd_empty_profile():
    print("[profiles] === EMPTY PROFILE (no cookies) ===")
    profile_id = f"empty_{uuid.uuid4().hex[:8]}"
    profile_dir = os.path.join(TEMP_DIR, profile_id)
    os.makedirs(profile_dir, exist_ok=True)

    port = find_free_port(9223)
    print(f"[profiles] Starting empty profile on port {port}...")
    proc, port = start_obscura(profile_dir, port)
    save_profile_info(profile_dir, port, "empty", proc.pid)

    print(f"[profiles] Empty profile ready!")
    print(f"[profiles] CDP endpoint: ws://127.0.0.1:{port}/devtools/browser")
    print(f"[profiles] Profile dir: {profile_dir}")
    print(f"[profiles] This profile will be deleted when you run: python obscura_profiles.py cleanup")
    return port

def main():
    parser = argparse.ArgumentParser(description="Obscura Profile Manager")
    parser.add_argument("action", choices=["main", "temp", "empty", "sync", "list", "cleanup"],
                        help="main=persistent profile, temp=clone with cookies, empty=blank, sync=update cookies, list=show profiles, cleanup=delete temp profiles")
    args = parser.parse_args()

    if args.action == "main":
        asyncio.run(cmd_main_profile())
    elif args.action == "temp":
        asyncio.run(cmd_temp_profile())
    elif args.action == "empty":
        asyncio.run(cmd_empty_profile())
    elif args.action == "sync":
        asyncio.run(sync_cookies_to_main())
    elif args.action == "list":
        profiles = list_profiles()
        print(f"[profiles] Found {len(profiles)} profile(s):")
        for p in profiles:
            ptype = p.get("type", "?")
            port = p.get("port", "?")
            pdir = p.get("profile_dir", "?")
            running = is_port_open(port) if isinstance(port, int) else False
            status = "RUNNING" if running else "STOPPED"
            print(f"  [{ptype.upper():5s}] port={port} status={status} dir={pdir}")
    elif args.action == "cleanup":
        count = cleanup_temp_profiles()
        print(f"[profiles] Deleted {count} temp/empty profile(s).")

if __name__ == "__main__":
    main()
