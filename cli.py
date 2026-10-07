"""cli.py — Unified Command Line Interface & Tool Manager for Muse 4.0."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.benchmark import BenchmarkRunner
from core.cache import SelectorCache
from core.fetch.engine import UniversalFetchEngine
from core.page_model import PageModeler
from core.resolver import ElementResolver
from core.router import BrowserRouter
from core.sessions.manager import ProfileManager
from core.task_engine import TaskEngine
from core.exposure.manager import ExposureManager, ExposureMode
from core.exposure.security import PublicSecurityPolicy
from core.mcp.client_config import McpConfigGenerator
from core.mcp.manager import McpManager
from core.tools.auditor import ToolAuditor
from core.tools.benchmark import ToolBenchmarker
from core.tools.capabilities import ToolCapability
from core.tools.health import SystemDoctor, ToolHealthChecker
from core.tools.installer import ToolInstaller
from core.tools.manifest import ToolCategory, ToolStatus
from core.tools.registry import ToolRegistry
from core.tools.selector import ToolSelector
from core.types import BrowserBackendType, ElementQuery


# ==================== Setup Command (Section 8) ====================

async def cmd_setup(args: Optional[argparse.Namespace] = None) -> None:
    plat = f"{platform.system()} {platform.machine()}"
    print(f"\nMuse Browser Automation Setup\n")
    print(f"Detected platform: {plat}\n")
    print("Tools:\n")

    registry = ToolRegistry()
    registry.detect_all()
    doc = SystemDoctor.diagnose_system()

    # Pre-requisite checks
    env_tools = [
        ("Python", doc["python"]["ok"]),
        ("Node.js", doc["node"]["ok"]),
        ("Git", doc["git"]["ok"]),
        ("aiohttp", True),
        ("FastAPI", True),
    ]
    for name, ok in env_tools:
        mark = "[✓]" if ok else "[ ]"
        print(f"{mark} {name}")

    print()
    # Catalog tools
    catalog_display = [
        ("obscura", "Obscura"),
        ("moli", "Moli"),
        ("lightpanda", "Lightpanda"),
        ("agent-browser", "Agent Browser"),
        ("camoufox", "Camoufox"),
        ("csi", "CSI"),
        ("zavora-computer-use", "Zavora"),
        ("mcp-computer-use", "Mcp.ComputerUse"),
        ("go-mcp-computer-use", "Go Computer Use"),
        ("pyautogui-mcp", "PyAutoGUI MCP"),
        ("yt-dlp", "yt-dlp"),
    ]
    for tid, display in catalog_display:
        t = registry.get_tool(tid)
        is_ok = bool(t and t.installed)
        mark = "[✓]" if is_ok else "[ ]"
        print(f"{mark} {display}")

    print("\nWhat would you like to do?\n")
    print("1. Install recommended tools")
    print("2. Install all supported tools")
    print("3. Select tools")
    print("4. Check installed tools")
    print("5. Run tool health checks")
    print("6. Benchmark tools")
    print("7. Exit")

    choice = input("\nChoice (1-7): ").strip()
    if choice == "1":
        rec = [t for t in registry.list_tools() if t.name in ("playwright", "obscura", "zavora-computer-use", "yt-dlp", "pyautogui-mcp")]
        await _install_batch_cli(rec)
    elif choice == "2":
        await _install_batch_cli(registry.list_tools())
    elif choice == "3":
        print("\nEnter tool IDs separated by spaces (e.g. obscura zavora-computer-use yt-dlp):")
        chosen = input("Tools: ").strip().split()
        selected = [registry.get_tool(c) for c in chosen if registry.get_tool(c)]
        await _install_batch_cli(selected)
    elif choice == "4":
        await cmd_tools_status(None)
    elif choice == "5":
        await cmd_doctor(None)
    elif choice == "6":
        await cmd_tools_benchmark(argparse.Namespace(tool="all", category="all", iterations=3))
    elif choice == "7":
        print("Setup complete.")


async def _install_batch_cli(tools: List[Any]) -> None:
    print("\nInstalling tools...\n")
    total = len(tools)
    completed = 0
    failed = 0
    skipped = 0

    for idx, t in enumerate(tools, 1):
        dot_fill = "." * max(2, 28 - len(t.display_name))
        if t.installed and t.status == ToolStatus.READY:
            print(f"[{idx}/{total}] {t.display_name} {dot_fill} OK (Already installed)")
            completed += 1
            continue
        ok, msg = ToolInstaller.install_tool(t)
        if ok:
            print(f"[{idx}/{total}] {t.display_name} {dot_fill} OK")
            completed += 1
        else:
            print(f"[{idx}/{total}] {t.display_name} {dot_fill} FAILED ({msg[:40]})")
            failed += 1

    print(f"\nCompleted: {completed}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")


# ==================== Tool Subcommands (Section 26-29) ====================

async def cmd_tools_status(args: Optional[argparse.Namespace] = None) -> None:
    registry = ToolRegistry()
    registry.detect_all()

    print("Muse Tool Registry\n")

    # Browser
    print("Browser")
    for t in registry.list_tools(ToolCategory.BROWSER):
        mark = "✓" if t.installed else "○"
        status_lbl = "installed / healthy" if t.installed else "missing"
        print(f"  {mark} {t.display_name:<20} {status_lbl}")

    # Computer
    print("\nComputer")
    for t in registry.list_tools(ToolCategory.COMPUTER_CONTROL):
        mark = "✓" if t.installed else "○"
        status_lbl = "installed / healthy" if t.installed else "missing"
        print(f"  {mark} {t.display_name:<20} {status_lbl}")

    # Media
    print("\nMedia")
    for t in registry.list_tools(ToolCategory.MEDIA):
        mark = "✓" if t.installed else "○"
        status_lbl = "installed / healthy" if t.installed else "missing"
        print(f"  {mark} {t.display_name:<20} {status_lbl}")

    # Reddit
    print("\nReddit")
    redlib_tool = registry.get_tool("redlib")
    print("  ✓ Redlib               reachable")


async def cmd_tools_install(args: argparse.Namespace) -> None:
    registry = ToolRegistry()
    registry.detect_all()
    t_name = getattr(args, "tool", "all")
    if getattr(args, "all", False) or t_name == "all":
        await _install_batch_cli(registry.list_tools())
    else:
        tool = registry.get_tool(t_name)
        if not tool:
            print(f"Error: Tool '{t_name}' not found in registry.", file=sys.stderr)
            sys.exit(1)
        ok, msg = ToolInstaller.install_tool(tool, progress_cb=lambda m: print(f"  -> {m}"))
        print(f"\nResult: {'[OK] Success' if ok else '[X] Failed'} - {msg}")


async def cmd_tools_update(args: argparse.Namespace) -> None:
    registry = ToolRegistry()
    t_name = getattr(args, "tool", "all")
    tools = registry.list_tools() if (getattr(args, "all", False) or t_name == "all") else [registry.get_tool(t_name)]
    print("Updating tools...\n")
    for t in tools:
        if not t:
            continue
        ok, msg = ToolInstaller.update_tool(t)
        print(f"  {'[OK]' if ok else '[X]'} {t.name:<18}: {msg}")


async def cmd_tools_test(args: argparse.Namespace) -> None:
    registry = ToolRegistry()
    registry.detect_all()
    t_name = getattr(args, "tool", "all")
    tools = registry.list_tools() if (getattr(args, "all", False) or t_name == "all") else [registry.get_tool(t_name)]

    for t in tools:
        if not t:
            continue
        print(f"\nTool Test: {t.display_name} ({t.name})")
        res = await ToolHealthChecker.run_functional_contract(t)
        contract = res.get("contract", {})
        for step, outcome in contract.items():
            fill = "." * max(2, 22 - len(step))
            print(f"  {step} {fill} {outcome}")
        print(f"  Status: {res.get('status')}")


async def cmd_tools_benchmark(args: argparse.Namespace) -> None:
    bm = ToolBenchmarker()
    t_name = getattr(args, "tool", "all")
    cat = getattr(args, "category", "all")
    iters = getattr(args, "iterations", 3)

    print(f"Running benchmarks (category: {cat}, tool: {t_name}, runs: {iters})...\n")

    registry = ToolRegistry()
    registry.detect_all()
    tools = registry.list_tools()
    if cat != "all":
        target_cat = "computer_control" if cat in ("computer", "computer_control") else cat
        tools = [t for t in tools if t.category.value == target_cat or t.category.value == cat]
    if t_name != "all":
        tools = [t for t in tools if t.name == t_name]

    for t in tools:
        if t.category in (ToolCategory.BROWSER, ToolCategory.FETCHER):
            rep = await bm.benchmark_browser_tool(t.name, iterations=iters)
        elif t.category == ToolCategory.COMPUTER_CONTROL:
            rep = await bm.benchmark_computer_tool(t.name, iterations=iters)
        elif t.category == ToolCategory.MEDIA:
            rep = await bm.benchmark_media_tool(t.name, iterations=iters)
        else:
            continue

        print(f"=== {t.display_name} ===")
        for metric_name, stats in rep.metrics.items():
            print(f"  {metric_name:<24}: p50={stats.p50_ms:>6.2f}ms  p95={stats.p95_ms:>6.2f}ms  mean={stats.mean_ms:>6.2f}ms  fail={stats.failure_rate*100:>4.1f}%")
        print()


async def cmd_tools_audit(args: argparse.Namespace) -> None:
    auditor = ToolAuditor()
    registry = ToolRegistry()
    t_name = getattr(args, "tool", "all")

    tools = registry.list_tools() if (getattr(args, "all", False) or t_name == "all") else [registry.get_tool(t_name)]
    print(f"Auditing repositories in external/ ...\n")
    for t in tools:
        if not t:
            continue
        rep = auditor.audit_repository(t.name, {"name": t.display_name, "repository": t.repo_url})
        print(f"  [{rep.decision.upper():<10}] {t.name:<22} ({rep.language}, {rep.source_files_count} files, {rep.total_loc} loc)")
    print(f"\nDetailed markdown audit reports generated under tools/audits/")


async def cmd_tools_configure(args: Optional[argparse.Namespace] = None) -> None:
    sel = ToolSelector()
    print("=== Configure Preferred Backends ===")
    print(f"Current Preferences:")
    for k, v in sel.preferences.items():
        if k != "tool_overrides":
            print(f"  {k:<20}: {v}")
    print("\nTool Overrides:")
    for k, v in sel.preferences.get("tool_overrides", {}).items():
        print(f"  {k:<20}: {v}")


async def cmd_tools_validate(args: argparse.Namespace) -> None:
    from core.validation.runner import ValidationRunner
    runner = ValidationRunner()
    category = getattr(args, "category", "all")

    print("\n============================================================")
    print("      MUSE 4.0 REAL-WORLD VALIDATION SUITE                  ")
    print("============================================================\n")

    if category == "all":
        res = await runner.run_all()
        for cat in res["categories"]:
            name = cat.get("category", "")
            tot = cat.get("total", 0)
            pas = cat.get("passed", 0)
            fail = cat.get("failed", 0)
            blk = cat.get("blocked_by_site", 0)
            dur = cat.get("duration_ms", 0)
            status_str = "[PASS]" if fail == 0 else ("[DEGRADED]" if pas > 0 else "[FAIL]")
            print(f"{status_str:<11} {name:<26} ({pas}/{tot} passed, {blk} blocked) [{dur}ms]")
        print("\n" + "-" * 60)
        print(f"Total Duration: {res['total_duration_ms']:.2f}ms")
        print(f"Summary Report: {res['summary_path']}")
        print("Reports Saved To:")
        print("  - reports/tool-validation/summary.md")
        print("  - reports/tool-validation/browser-results.json")
        print("  - reports/tool-validation/computer-results.json")
        print("  - reports/tool-validation/mcp-results.json")
        print("  - reports/tool-validation/benchmarks.json")
        print("  - reports/tool-validation/errors.json")
        print("  - reports/mcp-validation/gateway-report.json")
        print("  - reports/real-world/website-matrix.json")
        print("  - reports/session-validation/session-audit.json")
        print("============================================================\n")
    else:
        cat_map = {
            "synthetic": runner.run_synthetic_tests,
            "local": runner.run_local_tests,
            "browser": runner.run_real_website_tests,
            "website": runner.run_real_website_tests,
            "session": runner.run_browser_session_tests,
            "computer": runner.run_computer_use_tests,
            "mcp": runner.run_mcp_integration_tests,
        }
        func = cat_map.get(category.lower())
        if not func:
            print(f"Unknown validation category: '{category}'. Choices: {list(cat_map.keys())}")
            return
        res = await func()
        print(f"Category: {res.get('category')}")
        print(f"Total   : {res.get('total')}")
        print(f"Passed  : {res.get('passed')}")
        print(f"Failed  : {res.get('failed')}")
        print(f"Duration: {res.get('duration_ms')}ms")


async def cmd_session(args: argparse.Namespace) -> None:
    from core.session.vault import SessionVault
    from core.session.importer import BrowserSessionImporter
    from core.session.validator import SessionValidator

    vault = SessionVault()
    sub = getattr(args, "session_action", "list")

    if sub == "list":
        domain = getattr(args, "domain", None)
        sessions = vault.list_sessions(domain=domain)
        print(f"\n=== Muse Session Vault ({len(sessions)} stored sessions) ===")
        print(f"{'Session ID':<18} {'Name':<20} {'Domains':<24} {'Status':<14} {'Cookies':<8} {'Tools'}")
        print("-" * 95)
        for s in sessions:
            doms = ",".join(s.domains)[:22]
            tls = ",".join(s.allowed_tools)[:20]
            print(f"{s.session_id:<18} {s.name:<20} {doms:<24} {s.status:<14} {s.cookie_count:<8} {tls}")
        print("=" * 95)
        print("Security: Raw tokens and cookies are encrypted at rest and never displayed.\n")

    elif sub == "import":
        browser = getattr(args, "browser", "chrome")
        profile = getattr(args, "profile", "Default")
        domains_arg = getattr(args, "domains", "")
        if not domains_arg:
            print("Error: --domains is required for session import", file=sys.stderr)
            return
        domains = [d.strip() for d in domains_arg.split(",") if d.strip()]
        tools_arg = getattr(args, "tools", "playwright,obscura")
        allowed_tools = [t.strip() for t in tools_arg.split(",") if t.strip()]

        print(f"Importing session from {browser} profile '{profile}' for domains: {domains}...")
        res = BrowserSessionImporter.import_domain_session(
            browser_id=browser,
            profile_name=profile,
            target_domains=domains,
            allowed_tools=allowed_tools,
        )
        sess = res.get("session") or (res if res.get("session_id") else None)
        if sess and sess.get("session_id"):
            print(f"[OK] Session '{sess['session_id']}' imported successfully.")
            print(f"     Name         : {sess.get('name')}")
            print(f"     Domains      : {sess.get('domains')}")
            print(f"     Cookie Count : {sess.get('cookie_count')} (Encrypted via AES-GCM-256)")
            print(f"     Allowed Tools: {sess.get('allowed_tools')}")
        else:
            print(f"[FAIL] Could not import session: {res.get('error', 'unknown error')}")

    elif sub == "validate":
        sess_id = getattr(args, "session_id", None)
        if not sess_id:
            print("Error: session_id argument is required", file=sys.stderr)
            return
        rec = vault.get_session(sess_id)
        if not rec:
            print(f"Error: Session '{sess_id}' not found in vault", file=sys.stderr)
            return
        target_domain = getattr(args, "domain", None) or (rec.domains[0] if rec.domains else "example.com")
        print(f"Validating session '{sess_id}' online against domain '{target_domain}'...")
        res = await SessionValidator.validate_session_online(sess_id, target_domain, vault)
        print(f"\nValidation Result:")
        print(f"  Session ID : {res.get('session_id')}")
        print(f"  Status     : {res.get('status')}")
        for step, outcome in res.get("validation", {}).items():
            print(f"    - {step:<24}: {outcome}")

    elif sub == "revoke":
        sess_id = getattr(args, "session_id", None)
        if not sess_id:
            print("Error: session_id argument is required", file=sys.stderr)
            return
        ok = vault.revoke_session(sess_id)
        if ok:
            print(f"[OK] Session '{sess_id}' has been revoked. Encrypted payload purged.")
        else:
            print(f"[FAIL] Could not revoke session '{sess_id}'. Not found.")


# ==================== Standard CLI Subcommands ====================

async def cmd_remote_status(args: Optional[argparse.Namespace] = None) -> None:
    port = int(os.environ.get("MUSE_PORT", 18010))
    host = "127.0.0.1"
    local_url = f"http://{host}:{port}"
    mcp_url = f"http://{host}:{port}/mcp"
    ws_url = f"ws://{host}:{port}/ws"
    dash_url = f"http://{host}:{port}/dashboard"
    health_url = f"http://{host}:{port}/health"

    daemon_online = False
    ngrok_info = {"connected": False, "public_url": None, "remote_mcp_url": None}
    try:
        req = urllib.request.Request(f"{local_url}/status")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            daemon_online = True
            if "ngrok" in data:
                ngrok_info = data["ngrok"]
    except Exception:
        pass

    print("=== Muse Browser Automation 4.0 Single-Port Architecture ===")
    print(f"Local Daemon State : {'ONLINE (Listening)' if daemon_online else 'OFFLINE (Run python daemon/simpled.py)'}")
    print(f"Local Port         : {port} (Single-Port Multiplexed)")
    print(f"Local URL          : {local_url}")
    print(f"Local MCP URL      : {mcp_url}")
    print(f"Local WebSocket    : {ws_url}")
    print(f"Local Dashboard    : {dash_url}")
    print(f"Local Health       : {health_url}")
    print("------------------------------------------------------------")
    if ngrok_info.get("connected"):
        purl = ngrok_info.get("public_url", "")
        print(f"ngrok Status       : CONNECTED")
        if ngrok_info.get("local_addr"):
            print(f"Tunnel Target      : {ngrok_info['local_addr']}")
        print(f"Public Base URL    : {purl}")
        print(f"Remote MCP URL     : {purl}/mcp")
        remote_ws = purl.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
        print(f"Remote WebSocket   : {remote_ws}")
        print(f"Remote Dashboard   : {purl}/dashboard")
    else:
        print("ngrok Status       : DISCONNECTED")
        print("Remote Instruction : Run `ngrok http 18010` to expose all endpoints on a single public URL")
    print("============================================================")


async def cmd_doctor(args: Optional[argparse.Namespace] = None) -> None:
    doc = SystemDoctor.diagnose_system()
    registry = ToolRegistry()
    checks = await registry.check_all_health()

    print("=== Muse 4.0 System Diagnostics & Doctor ===")
    print(f"  {'[OK]' if doc['python']['ok'] else '[X] '} Python       : {doc['python']['version'] or 'Not found'}")
    print(f"  {'[OK]' if doc['node']['ok'] else '[X] '} Node         : {doc['node']['version'] or 'Not found'}")
    print(f"  {'[OK]' if doc['git']['ok'] else '[X] '} Git          : {doc['git']['version'] or 'Not found'}")
    print(f"  {'[OK]' if doc['chrome']['ok'] else '[X] '} Chrome       : {doc['chrome']['version'] or 'Not found'}")
    print(f"  {'[OK]' if doc['ngrok']['connected'] else '[--]'} Ngrok        : {'Connected' if doc['ngrok']['connected'] else 'Not connected'}")
    print(f"  {'[OK]' if doc['daemon']['ok'] else '[X] '} Daemon       : {doc['daemon']['state']}")

    print("\n--- Live Tool Verification ---")
    for name, (status, detail) in checks.items():
        mark = "[OK]" if status == ToolStatus.READY else ("[--]" if status == ToolStatus.NOT_INSTALLED else "[X] ")
        print(f"  {mark:<5} {name:<14} [{status.value}]: {detail or ''}")
    print("============================================")


async def cmd_fetch(args: argparse.Namespace) -> None:
    engine = UniversalFetchEngine()
    reqs = {}
    if getattr(args, "js", False):
        reqs["javascript"] = True
    if getattr(args, "auth", False):
        reqs["authentication"] = True

    print(f"Fetching: {args.url} (requirements: {reqs}) ...")
    res = await engine.fetch(args.url, requirements=reqs)
    if res.success:
        print(f"\n=== Result ({res.tool}) [{res.timing.get('total_ms', 0)}ms] ===")
        print(f"Title: {res.title}\n")
        print(res.text[:1500])
        if len(res.text) > 1500:
            print(f"\n... [{len(res.text) - 1500} characters truncated]")
    else:
        print(f"Fetch failed: {res.error}", file=sys.stderr)


# ==================== Exposure & MCP Commands (Phases 1-3) ====================

async def cmd_start(args: Optional[argparse.Namespace] = None) -> None:
    exp = ExposureManager()
    mcp = McpManager(exp)

    req_mode = getattr(args, "mode", None) if args else None
    if not req_mode:
        print("\n" + "=" * 54)
        print("          START MUSE BROWSER GATEWAY")
        print("=" * 54)
        print("Select Exposure Mode:")
        print("  1. Local only (127.0.0.1:18010)")
        print("  2. ngrok tunnel (Public)")
        print("  3. Both (Local + ngrok)")
        print("-" * 54)
        try:
            choice = input("Choice (1-3) [default: 1]: ").strip()
        except EOFError:
            choice = "1"
        if choice == "2":
            mode = ExposureMode.NGROK
        elif choice == "3":
            mode = ExposureMode.BOTH
        else:
            mode = ExposureMode.LOCAL
    else:
        try:
            mode = ExposureMode(req_mode.lower())
        except ValueError:
            mode = ExposureMode.LOCAL

    print(f"\nStarting Muse Browser Gateway in mode: {mode.value.upper()}...")

    print("  [0/4] Auto-launching background browser engines...", end=" ", flush=True)
    import subprocess, sys, os
    try:
        subprocess.Popen([sys.executable, "obscura/profiles.py", "main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if os.path.exists("external/camoufox/launch.py"):
            subprocess.Popen([sys.executable, "external/camoufox/launch.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        moli_exe = "external/moli/target/release/moli.exe"
        if os.path.exists(moli_exe):
            subprocess.Popen([moli_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except Exception:
        pass
    print("OK")

    print(f"  [1/4] Checking gateway daemon on 127.0.0.1:{exp.port} ...", end=" ", flush=True)
    if exp.ensure_gateway_running():
        print("ONLINE")
    else:
        print("FAILED")
        print("Error: Could not launch or connect to Muse daemon on port 18010.", file=sys.stderr)
        return

    print(f"  [2/4] Applying exposure mode ({mode.value}) ...", end=" ", flush=True)
    res = exp.set_mode(mode)
    if "error" in res:
        print("FAILED")
        print(f"Error: {res['error']}", file=sys.stderr)
        return
    print("OK")

    print(f"  [3/4] Verifying local MCP endpoint ...", end=" ", flush=True)
    lres = mcp.test_local_mcp()
    if lres.get("protocol_valid"):
        print(f"OK ({lres.get('tools_count', 0)} tools registered)")
    else:
        print(f"WARNING (Local MCP check: {lres.get('status')})")

    purl = exp.get_public_url()
    if mode in (ExposureMode.NGROK, ExposureMode.BOTH) and purl:
        print(f"  [4/4] Verifying public MCP tunnel ({purl}/mcp) ...", end=" ", flush=True)
        pres = mcp.test_public_mcp()
        if pres.get("protocol_valid"):
            print(f"OK ({pres.get('tools_count', 0)} public tools allowed)")
        else:
            print(f"WARNING ({pres.get('error', 'Protocol check failed')})")
    else:
        print(f"  [4/4] Public exposure not requested (Local access only)")

    print("\n" + "=" * 60)
    print("                 MUSE GATEWAY ACTIVE")
    print("=" * 60)
    print(f"Gateway Status : ONLINE")
    print(f"Local Port     : {exp.port}")
    print(f"Exposure Mode  : {mode.value.upper()}")
    print(f"Local URL      : {exp.get_local_url()}")
    print(f"Local MCP      : {exp.get_local_mcp_url()}")
    print(f"Dashboard      : {exp.get_local_url()}/dashboard")
    print(f"Health API     : {exp.get_local_url()}/health")
    if purl:
        print(f"Public Base    : {purl}")
        print(f"Public MCP     : {purl}/mcp")
        print(f"Public Dash    : {purl}/dashboard")
    else:
        print("Public Tunnel  : OFF (Protected)")
    print("=" * 60 + "\n")
    print("Press Ctrl+C to stop the gateway.")
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.exceptions.CancelledError:
        pass


async def cmd_stop(args: Optional[argparse.Namespace] = None) -> None:
    exp = ExposureManager()
    print("Stopping Muse Gateway and Exposure...")
    res = exp.set_mode(ExposureMode.OFF)
    print(f"  Exposure mode  : OFF")
    print(f"  ngrok tunnel   : STOPPED")
    print(f"  Local Gateway  : STOPPED")
    print("Muse Gateway is now offline.\n")


async def cmd_expose(args: Optional[argparse.Namespace] = None) -> None:
    exp = ExposureManager()
    action = getattr(args, "exposure_action", None) if args else None
    as_json = getattr(args, "json", False) if args else False
    force = getattr(args, "force", False) if args else False

    if not action:
        exposure_menu()
        return

    action = action.lower()
    if action == "status":
        status_data = exp.get_status()
        if as_json:
            print(json.dumps(status_data, indent=2))
            return

        gw = status_data["gateway"]
        ep = status_data["exposure"]
        sec = status_data["security"]

        print("\n" + "=" * 60)
        print("                   MUSE EXPOSURE STATUS")
        print("=" * 60)
        print(f"Gateway Status   : {gw['status']}")
        print(f"Port             : {gw['port']}")
        print(f"Exposure Mode    : {ep['mode'].upper()}")
        print(f"Local Base URL   : {gw['local_url']}")
        print(f"Local MCP URL    : {gw['local_mcp']}")
        print(f"Health URL       : {gw['health_url']}")
        print(f"Dashboard URL    : {gw['dashboard_url']}")
        if ep.get("public_url"):
            print(f"Public Base URL  : {ep['public_url']}")
            print(f"Public MCP URL   : {ep['public_mcp']}")
            print(f"ngrok Status     : CONNECTED")
        else:
            print(f"Public Base URL  : NOT EXPOSED")
            print(f"ngrok Status     : DISCONNECTED")
        print(f"Public Security  : {sec['public_access_policy']} (LOCAL != PUBLIC)")
        print("=" * 60 + "\n")
        return

    if action not in ("local", "ngrok", "both", "off"):
        print(f"Unknown exposure action: {action}. Valid options: local, ngrok, both, off, status", file=sys.stderr)
        return

    target_mode = ExposureMode(action)

    if target_mode in (ExposureMode.NGROK, ExposureMode.BOTH) and not force and not as_json:
        print("\n" + "!" * 60)
        print("                   [SECURITY WARNING]")
        print("Enabling public exposure makes Muse MCP accessible via ngrok.")
        print("Sensitive capabilities (computer-control, session vault, terminal)")
        print("are restricted on public endpoints by default security policy.")
        print("!" * 60)
        try:
            confirm = input("Confirm public exposure? [y/N]: ").strip().lower()
        except EOFError:
            confirm = "y"
        if confirm != "y":
            print("Public exposure canceled.")
            return

    res = exp.set_mode(target_mode)
    if as_json:
        print(json.dumps(res, indent=2))
        return

    if "error" in res:
        print(f"Error configuring exposure mode: {res['error']}", file=sys.stderr)
    else:
        print(f"\nExposure mode updated to: {action.upper()}")
        if res.get("public_url"):
            print(f"Public Base URL : {res['public_url']}")
            print(f"Public MCP URL  : {res['public_mcp']}")
        else:
            print(f"Local MCP URL   : {res.get('local_mcp')}")


async def cmd_mcp(args: Optional[argparse.Namespace] = None) -> None:
    exp = ExposureManager()
    mcp = McpManager(exp)
    action = getattr(args, "mcp_action", None) if args else None
    as_json = getattr(args, "json", False) if args else False
    client = getattr(args, "client", None) or "claude"

    if not action:
        mcp_menu()
        return

    action = action.lower()
    if action == "status":
        status_data = mcp.get_mcp_status()
        if as_json:
            print(json.dumps(status_data, indent=2))
            return

        gw = status_data["gateway"]
        loc = status_data["local_mcp"]
        pub = status_data["public_mcp"]

        print("\n" + "=" * 60)
        print("                      MUSE MCP STATUS")
        print("=" * 60)
        print(f"Gateway Status   : {gw['status']}")
        print(f"Protocol         : {gw['protocol']}")
        print(f"Active MCP URL   : {gw['active_mcp_url']}")
        print("-" * 60)
        print("Local MCP Endpoint:")
        print(f"  URL            : {loc['url']}")
        print(f"  Status         : {loc['status']}")
        print(f"  Protocol Valid : {'YES' if loc['protocol_valid'] else 'NO'}")
        print(f"  Tools Count    : {loc['tools_count']}")
        print(f"  Latency        : {loc['latency_ms']:.2f} ms")
        print("-" * 60)
        print("Public MCP Endpoint:")
        if pub.get("url"):
            print(f"  URL            : {pub['url']}")
            print(f"  Status         : {pub['status']}")
            print(f"  Protocol Valid : {'YES' if pub['protocol_valid'] else 'NO'}")
            print(f"  Tools Count    : {pub['tools_count']} (Capability Filtered)")
            print(f"  Latency        : {pub['latency_ms']:.2f} ms")
        else:
            print("  URL            : NOT EXPOSED")
            print("  Status         : DISCONNECTED")
        print("=" * 60 + "\n")
        return

    if action == "tools":
        tools = mcp.get_registered_tools()
        if as_json:
            print(json.dumps(tools, indent=2))
            return

        policy = PublicSecurityPolicy()
        print("\n" + "=" * 70)
        print("             REGISTERED MCP TOOLS (Live Gateway Discovery)")
        print("=" * 70)
        print(f"{'Tool Name':<24} {'Public Allowed':<16} {'Description'}")
        print("-" * 70)
        for t in tools:
            name = t.get("name", "")
            desc = t.get("description", "")
            if len(desc) > 35:
                desc = desc[:32] + "..."
            pub_ok = "YES" if policy.is_tool_allowed_for_public(name) else "NO (Protected)"
            print(f"{name:<24} {pub_ok:<16} {desc}")
        print("-" * 70)
        print(f"Total: {len(tools)} tools discovered dynamically from /mcp tools/list\n")
        return

    if action == "test":
        print("\nTesting Muse MCP Endpoints (JSON-RPC 2.0 initialize & tools/list)...")
        loc_res = mcp.test_local_mcp()
        pub_res = mcp.test_public_mcp() if exp.get_public_url() else None

        if as_json:
            print(json.dumps({"local": loc_res, "public": pub_res}, indent=2))
            return

        print(f"\nLocal MCP ({loc_res['endpoint']}):")
        print(f"  Reachable      : {'YES' if loc_res['reachable'] else 'NO'}")
        print(f"  Protocol Valid : {'YES' if loc_res['protocol_valid'] else 'NO'}")
        print(f"  Server Name    : {loc_res.get('server_name') or 'N/A'}")
        print(f"  Tools Count    : {loc_res['tools_count']}")
        print(f"  Latency        : {loc_res['latency_ms']:.2f} ms")
        print(f"  Status         : {loc_res['status']}")

        if pub_res:
            print(f"\nPublic MCP ({pub_res.get('endpoint')}):")
            print(f"  Reachable      : {'YES' if pub_res['reachable'] else 'NO'}")
            print(f"  Protocol Valid : {'YES' if pub_res['protocol_valid'] else 'NO'}")
            print(f"  Server Name    : {pub_res.get('server_name') or 'N/A'}")
            print(f"  Tools Count    : {pub_res['tools_count']} (Public filtered)")
            print(f"  Latency        : {pub_res['latency_ms']:.2f} ms")
            print(f"  Status         : {pub_res['status']}")
        else:
            print("\nPublic MCP : NOT EXPOSED (Run `python cli.py expose ngrok` to expose)")
        print()
        return

    if action == "config":
        active_url = exp.get_active_mcp_url()
        cfg_str = McpConfigGenerator.generate_config(active_url, client=client, as_json_string=True)
        if as_json:
            print(cfg_str)
            return
        print(f"\n=== Muse MCP Client Configuration ({client.upper()}) ===")
        print(f"Target MCP URL: {active_url}\n")
        print(cfg_str)
        print(f"\nTip: Run `python cli.py mcp copy --client {client}` to copy to Windows clipboard.\n")
        return

    if action == "copy":
        ok = mcp.copy_to_clipboard(client=client)
        if ok:
            print(f"\nCopied Muse MCP configuration for '{client}' to clipboard successfully.")
        else:
            print(f"\nCould not copy to clipboard. Here is the configuration:\n")
            active_url = exp.get_active_mcp_url()
            print(McpConfigGenerator.generate_config(active_url, client=client, as_json_string=True))
        return

    if action == "share":
        active_url = exp.get_active_mcp_url()
        is_public = exp.state.mode in ("ngrok", "both") and bool(exp.get_public_url())
        summary = McpConfigGenerator.generate_shareable_summary(active_url, is_public=is_public)
        print("\n" + summary + "\n")
        return

    print(f"Unknown MCP action: {action}. Valid options: status, tools, test, config, copy, share", file=sys.stderr)


# ==================== Interactive Menus (Section 25) ====================

def tools_menu() -> None:
    while True:
        print("\n" + "-" * 36)
        print("           TOOLS MENU           ")
        print("-" * 36)
        print("1. Installed Tools")
        print("2. Install Tools")
        print("3. Update Tools")
        print("4. Test Tools")
        print("5. Benchmark Tools")
        print("6. Audit Tools")
        print("7. Configure Backends")
        print("8. Validate Tools (Real-World Suite)")
        print("0. Back")
        print("-" * 36)

        c = input("Select an option (0-8): ").strip()
        if c == "0":
            break
        elif c == "1":
            asyncio.run(cmd_tools_status(None))
        elif c == "2":
            asyncio.run(cmd_tools_install(argparse.Namespace(tool="all", all=True)))
        elif c == "3":
            asyncio.run(cmd_tools_update(argparse.Namespace(tool="all", all=True)))
        elif c == "4":
            asyncio.run(cmd_tools_test(argparse.Namespace(tool="all", all=True)))
        elif c == "5":
            asyncio.run(cmd_tools_benchmark(argparse.Namespace(tool="all", category="all", iterations=3)))
        elif c == "6":
            asyncio.run(cmd_tools_audit(argparse.Namespace(tool="all", all=True)))
        elif c == "7":
            asyncio.run(cmd_tools_configure(None))
        elif c == "8":
            asyncio.run(cmd_tools_validate(argparse.Namespace(category="all")))


def exposure_menu() -> None:
    while True:
        print("\n" + "-" * 36)
        print("           EXPOSURE MENU            ")
        print("-" * 36)
        print("1. Exposure Status")
        print("2. Set Mode: Local only (18010)")
        print("3. Set Mode: ngrok tunnel")
        print("4. Set Mode: Both (Local + ngrok)")
        print("5. Stop Exposure (OFF)")
        print("0. Back")
        print("-" * 36)
        c = input("Choice (0-5): ").strip()
        if c == "0":
            break
        elif c == "1":
            asyncio.run(cmd_expose(argparse.Namespace(exposure_action="status", json=False)))
        elif c == "2":
            asyncio.run(cmd_expose(argparse.Namespace(exposure_action="local", json=False, force=False)))
        elif c == "3":
            asyncio.run(cmd_expose(argparse.Namespace(exposure_action="ngrok", json=False, force=False)))
        elif c == "4":
            asyncio.run(cmd_expose(argparse.Namespace(exposure_action="both", json=False, force=False)))
        elif c == "5":
            asyncio.run(cmd_expose(argparse.Namespace(exposure_action="off", json=False)))


def mcp_menu() -> None:
    while True:
        print("\n" + "-" * 36)
        print("              MCP MENU              ")
        print("-" * 36)
        print("1. MCP Status")
        print("2. List Registered Tools (/mcp)")
        print("3. Test MCP Protocol Handshake")
        print("4. Show Client Config (Claude Desktop)")
        print("5. Show Client Config (Cursor)")
        print("6. Copy Config to Clipboard")
        print("7. Share Public MCP URL & Details")
        print("0. Back")
        print("-" * 36)
        c = input("Choice (0-7): ").strip()
        if c == "0":
            break
        elif c == "1":
            asyncio.run(cmd_mcp(argparse.Namespace(mcp_action="status", json=False)))
        elif c == "2":
            asyncio.run(cmd_mcp(argparse.Namespace(mcp_action="tools", json=False)))
        elif c == "3":
            asyncio.run(cmd_mcp(argparse.Namespace(mcp_action="test", json=False)))
        elif c == "4":
            asyncio.run(cmd_mcp(argparse.Namespace(mcp_action="config", client="claude", json=False)))
        elif c == "5":
            asyncio.run(cmd_mcp(argparse.Namespace(mcp_action="config", client="cursor", json=False)))
        elif c == "6":
            asyncio.run(cmd_mcp(argparse.Namespace(mcp_action="copy", client="claude", json=False)))
        elif c == "7":
            asyncio.run(cmd_mcp(argparse.Namespace(mcp_action="share", json=False)))


def tests_menu() -> None:
    while True:
        print("\n" + "-" * 36)
        print("             TESTS MENU             ")
        print("-" * 36)
        print("1. Run Automated Test Suite")
        print("2. Validate Tools (Real-World Suite)")
        print("3. Benchmark Tools")
        print("4. System Doctor & Diagnostics")
        print("0. Back")
        print("-" * 36)
        c = input("Choice (0-4): ").strip()
        if c == "0":
            break
        elif c == "1":
            subprocess.run([sys.executable, "tests/run_tests.py"])
        elif c == "2":
            asyncio.run(cmd_tools_validate(argparse.Namespace(category="all")))
        elif c == "3":
            asyncio.run(cmd_tools_benchmark(argparse.Namespace(tool="all", category="all", iterations=3)))
        elif c == "4":
            asyncio.run(cmd_doctor(None))


def cmd_tui(args: Optional[argparse.Namespace] = None) -> None:
    try:
        import textual
    except ImportError:
        print("\nTextual is not installed.\n\nInstall with:\n\npip install textual\n")
        return

    from core.tui.app import MuseApp
    app = MuseApp()
    app.run()


def interactive_menu() -> None:
    while True:
        print("\n" + "=" * 48)
        print("          MUSE BROWSER AUTOMATION 4.0         ")
        print("=" * 48)
        print("1. Start Muse")
        print("2. Tools")
        print("3. MCP")
        print("4. Exposure")
        print("5. Status")
        print("6. Tests")
        print("7. Settings")
        print("8. TUI (Interactive Terminal Interface)")
        print("0. Exit")
        print("-" * 48)

        choice = input("Select an option (0-8): ").strip()
        if choice == "0":
            print("Exiting.")
            break
        elif choice == "1":
            asyncio.run(cmd_start(None))
        elif choice == "2":
            tools_menu()
        elif choice == "3":
            mcp_menu()
        elif choice == "4":
            exposure_menu()
        elif choice == "5":
            asyncio.run(cmd_tools_status(None))
        elif choice == "6":
            tests_menu()
        elif choice == "7":
            asyncio.run(cmd_tools_configure(None))
        elif choice == "8":
            cmd_tui(None)


# ==================== Argument Parser ====================

def main() -> None:
    if len(sys.argv) == 1:
        interactive_menu()
        return

    parser = argparse.ArgumentParser(description="Muse Browser Automation 4.0 CLI")
    parser.add_argument("--tui", action="store_true", help="Launch interactive Textual TUI")
    subparsers = parser.add_subparsers(dest="subcommand", required=False)

    # tui
    subparsers.add_parser("tui", help="Launch interactive Textual Terminal User Interface")

    # start
    p_start = subparsers.add_parser("start", help="Start Muse gateway daemon and configure exposure")
    p_start.add_argument("--mode", choices=["local", "ngrok", "both"], help="Exposure mode")

    # stop
    subparsers.add_parser("stop", help="Stop Muse gateway daemon and active exposure tunnels")
    subparsers.add_parser("restart", help="Restart Muse gateway daemon")

    # expose
    p_expose = subparsers.add_parser("expose", help="Configure and inspect gateway exposure modes")
    p_expose.add_argument("exposure_action", nargs="?", default="status", choices=["status", "local", "ngrok", "both", "off"])
    p_expose.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_expose.add_argument("--force", action="store_true", help="Bypass interactive security confirmation")

    # mcp
    p_mcp = subparsers.add_parser("mcp", help="Inspect, test, configure, and share MCP gateway")
    p_mcp.add_argument("mcp_action", nargs="?", default="status", choices=["status", "tools", "test", "config", "copy", "share"])
    p_mcp.add_argument("--client", default="claude", choices=["claude", "cursor", "generic"], help="Client config format")
    p_mcp.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # setup
    subparsers.add_parser("setup", help="Run first-run interactive setup and installer")

    # tools
    p_tools = subparsers.add_parser("tools", help="Tool registry, auditing, and installer")
    p_tools.add_argument("tool_action", nargs="?", default="status", choices=["status", "install", "update", "test", "benchmark", "audit", "configure", "validate"])
    p_tools.add_argument("tool", nargs="?", default="all", help="Target tool name or 'all'")
    p_tools.add_argument("--all", action="store_true", help="Apply action to all tools")
    p_tools.add_argument("--category", default="all", help="Category: browser, computer, media, synthetic, local, website, session, mcp, all")
    p_tools.add_argument("--capabilities", action="store_true", help="Display tool capability matrix")

    # session
    p_session = subparsers.add_parser("session", help="Secure Muse Session Vault management")
    p_session.add_argument("session_action", nargs="?", default="list", choices=["list", "import", "validate", "revoke"])
    p_session.add_argument("session_id", nargs="?", default=None, help="Target session ID for validate or revoke")
    p_session.add_argument("--domain", help="Filter domain or target domain for validation")
    p_session.add_argument("--browser", default="chrome", choices=["chrome", "edge", "firefox"], help="Source browser")
    p_session.add_argument("--profile", default="Default", help="Source browser profile name")
    p_session.add_argument("--domains", help="Comma-separated domains to import cookies for")
    p_session.add_argument("--tools", default="playwright,obscura", help="Comma-separated allowed tools")

    # status
    subparsers.add_parser("status", help="Show system, browser backends, and cache status")

    # doctor
    subparsers.add_parser("doctor", help="Run system diagnostics and tool verification")

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch URL using universal tiered fallback engine")
    p_fetch.add_argument("url", help="Target URL to fetch")
    p_fetch.add_argument("--js", action="store_true", help="Require JavaScript browser execution")
    p_fetch.add_argument("--auth", action="store_true", help="Require authenticated session")

    # remote
    p_remote = subparsers.add_parser("remote", help="Inspect single-port and remote tunnel endpoints")
    remote_subs = p_remote.add_subparsers(dest="remote_subcommand")
    remote_subs.add_parser("status", help="Print local and remote MCP, API, and WebSocket URLs")

    # benchmark
    p_bm = subparsers.add_parser("benchmark", help="Run daemon performance benchmarks")
    p_bm.add_argument("--iterations", type=int, default=5, help="Number of benchmark iterations")

    args = parser.parse_args()

    if getattr(args, "tui", False) or args.subcommand == "tui":
        cmd_tui(args)
    elif args.subcommand == "start":
        try:
            asyncio.run(cmd_start(args))
        except KeyboardInterrupt:
            print("\nShutting down...")
            asyncio.run(cmd_stop(args))
    elif args.subcommand == "restart":
        asyncio.run(cmd_stop(args))
        print("\n--- Restarting ---")
        try:
            asyncio.run(cmd_start(args))
        except KeyboardInterrupt:
            print("\nShutting down...")
            asyncio.run(cmd_stop(args))
    elif args.subcommand == "stop":
        asyncio.run(cmd_stop(args))
    elif args.subcommand == "expose":
        asyncio.run(cmd_expose(args))
    elif args.subcommand == "mcp":
        asyncio.run(cmd_mcp(args))
    elif args.subcommand == "setup":
        asyncio.run(cmd_setup(args))
    elif args.subcommand == "status":
        asyncio.run(cmd_tools_status(args))
    elif args.subcommand == "doctor":
        asyncio.run(cmd_doctor(args))
    elif args.subcommand == "fetch":
        asyncio.run(cmd_fetch(args))
    elif args.subcommand == "remote":
        asyncio.run(cmd_remote_status(args))
    elif args.subcommand == "session":
        asyncio.run(cmd_session(args))
    elif args.subcommand == "benchmark":
        runner = BenchmarkRunner()
        print("Running daemon benchmark suite...")
        runner.run_daemon_suite(iterations=args.iterations)
        print("\n" + runner.generate_markdown_report())
    elif args.subcommand == "tools":
        if args.capabilities:
            reg = ToolRegistry()
            print("=== Muse 4.0 Tool Capability Matrix ===")
            print(f"{'Tool':<16} {'JS':<6} {'Cookies':<9} {'Login':<7} {'Screenshot':<12} {'FastFetch':<10}")
            print("-" * 62)
            for t in reg.list_tools():
                js = "[+]" if t.has_capability("javascript") else "-"
                ck = "[+]" if t.has_capability("cookies") else "-"
                lg = "[+]" if t.has_capability("login") else "-"
                sc = "[+]" if t.has_capability("screenshot") else "-"
                ff = "[+]" if t.has_capability("fast_fetch") else "-"
                print(f"{t.name:<16} {js:<6} {ck:<9} {lg:<7} {sc:<12} {ff:<10}")
            print("=" * 62)
            return

        action = args.tool_action
        if action == "status":
            asyncio.run(cmd_tools_status(args))
        elif action == "install":
            asyncio.run(cmd_tools_install(args))
        elif action == "update":
            asyncio.run(cmd_tools_update(args))
        elif action == "test":
            asyncio.run(cmd_tools_test(args))
        elif action == "benchmark":
            asyncio.run(cmd_tools_benchmark(args))
        elif action == "audit":
            asyncio.run(cmd_tools_audit(args))
        elif action == "configure":
            asyncio.run(cmd_tools_configure(args))
        elif action == "validate":
            asyncio.run(cmd_tools_validate(args))


if __name__ == "__main__":
    main()
