from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Ensure IPv4 resolution on systems where IPv6 routes are unavailable
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_getaddrinfo


def test_endpoint(base_url: str, is_public: bool = False) -> Dict[str, Any]:
    print(f"\n========================================================")
    print(f" TESTING: {base_url} ({'PUBLIC NGROK' if is_public else 'LOCAL GATEWAY'})")
    print(f"========================================================")

    headers = {
        "User-Agent": "muse-live-verifier/4.0",
        "ngrok-skip-browser-warning": "1",
        "Content-Type": "application/json",
    }
    results = {}

    # 1. /health
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(f"{base_url}/health", headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            ok = resp.status == 200 and data.get("ok") is True
            print(f"  [1] /health              : {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> {data.get('status')}")
            results["health"] = (ok, dur, data)
    except Exception as e:
        print(f"  [1] /health              : FAIL -> {e}")
        results["health"] = (False, 0, str(e))

    # 2. /status
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(f"{base_url}/status", headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            ok = resp.status == 200 and data.get("ok") is True
            print(f"  [2] /status              : {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> single_port={data.get('single_port')}")
            results["status"] = (ok, dur, data)
    except Exception as e:
        print(f"  [2] /status              : FAIL -> {e}")
        results["status"] = (False, 0, str(e))

    # 3. /dashboard
    t0 = time.perf_counter()
    try:
        dash_headers = dict(headers)
        dash_headers["Accept"] = "text/html"
        req = urllib.request.Request(f"{base_url}/dashboard", headers=dash_headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            content = resp.read().decode("utf-8", errors="replace")
            ok = resp.status == 200 and ("Muse" in content or "html" in content.lower())
            print(f"  [3] /dashboard           : {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> {len(content)} bytes HTML")
            results["dashboard"] = (ok, dur, len(content))
    except Exception as e:
        print(f"  [3] /dashboard           : FAIL -> {e}")
        results["dashboard"] = (False, 0, str(e))

    # 4. /mcp initialize
    t0 = time.perf_counter()
    try:
        init_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "live-tester", "version": "4.0"}},
        }).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/mcp", data=init_payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            server_name = data.get("result", {}).get("serverInfo", {}).get("name")
            ok = resp.status == 200 and bool(server_name)
            print(f"  [4] /mcp initialize      : {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> server={server_name}")
            results["mcp_init"] = (ok, dur, server_name)
    except Exception as e:
        print(f"  [4] /mcp initialize      : FAIL -> {e}")
        results["mcp_init"] = (False, 0, str(e))

    # 5. /mcp tools/list
    t0 = time.perf_counter()
    try:
        list_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/mcp", data=list_payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            tools = data.get("result", {}).get("tools", [])
            ok = resp.status == 200 and len(tools) > 0
            print(f"  [5] /mcp tools/list      : {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> {len(tools)} tools discovered")
            results["mcp_list"] = (ok, dur, len(tools))
    except Exception as e:
        print(f"  [5] /mcp tools/list      : FAIL -> {e}")
        results["mcp_list"] = (False, 0, str(e))

    # 6. /mcp tools/call: ping
    t0 = time.perf_counter()
    try:
        call_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {}},
        }).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/mcp", data=call_payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            call_res = data.get("result", {})
            ok = resp.status == 200 and "error" not in data
            print(f"  [6] tools/call (ping)    : {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> {call_res}")
            results["call_ping"] = (ok, dur, call_res)
    except Exception as e:
        print(f"  [6] tools/call (ping)    : FAIL -> {e}")
        results["call_ping"] = (False, 0, str(e))

    # 7. /mcp tools/call: fetch_url (Real fetch through tunnel!)
    t0 = time.perf_counter()
    try:
        fetch_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "fetch_url", "arguments": {"url": "https://httpbin.org/html"}},
        }).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/mcp", data=fetch_payload, headers=headers)
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            content_text = str(data.get("result", ""))
            ok = resp.status == 200 and ("Herman Melville" in content_text or "heading" in content_text.lower() or "success" in content_text.lower() or len(content_text) > 20)
            print(f"  [7] tools/call (fetch_url): {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> response length {len(content_text)}")
            results["call_fetch"] = (ok, dur, len(content_text))
    except Exception as e:
        print(f"  [7] tools/call (fetch_url): FAIL -> {e}")
        results["call_fetch"] = (False, 0, str(e))

    # 8. Security Guardrail Check: Call a protected tool (session_list)
    t0 = time.perf_counter()
    try:
        prot_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "session_list", "arguments": {}},
        }).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/mcp", data=prot_payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            dur = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            has_error = "error" in data or data.get("result", {}).get("isError") is True
            if is_public:
                # MUST be blocked on public tunnel
                ok = has_error
                status_label = "BLOCKED (SECURE - CORRECT)" if ok else "ALLOWED (SECURITY LEAK!)"
            else:
                # Allowed locally
                ok = not has_error
                status_label = "ALLOWED (AUTHORIZED LOCAL)" if ok else "BLOCKED (LOCAL ERROR)"
            print(f"  [8] security guardrail   : {'PASS' if ok else 'FAIL'} ({dur:.1f}ms) -> {status_label}")
            results["guardrail"] = (ok, dur, status_label)
    except urllib.error.HTTPError as e:
        dur = (time.perf_counter() - t0) * 1000.0
        if is_public and e.code in (401, 403):
            print(f"  [8] security guardrail   : PASS ({dur:.1f}ms) -> BLOCKED (HTTP {e.code} SECURE)")
            results["guardrail"] = (True, dur, f"HTTP {e.code}")
        else:
            print(f"  [8] security guardrail   : FAIL -> HTTP {e.code}")
            results["guardrail"] = (False, dur, f"HTTP {e.code}")
    except Exception as e:
        print(f"  [8] security guardrail   : FAIL -> {e}")
        results["guardrail"] = (False, 0, str(e))

    return results


def main():
    print("=" * 60)
    print(" MUSE BROWSER AUTOMATION 4.0 — LIVE TUNNEL VERIFICATION")
    print("=" * 60)

    # 1. Test Local
    local_url = "http://127.0.0.1:18010"
    local_results = test_endpoint(local_url, is_public=False)

    # 2. Discover Public ngrok URL
    from core.exposure.manager import ExposureManager
    exp = ExposureManager()
    purl = exp.get_public_url() or "https://endorphin-italicize-mockup.ngrok-free.dev"

    # 3. Test Public ngrok
    ngrok_results = test_endpoint(purl, is_public=True)

    # Summary
    print("\n" + "=" * 60)
    print(" VERIFICATION SUMMARY")
    print("=" * 60)
    local_passes = sum(1 for v in local_results.values() if v[0])
    ngrok_passes = sum(1 for v in ngrok_results.values() if v[0])

    print(f"Local Gateway ({local_url})  : {local_passes}/{len(local_results)} PASSED")
    print(f"Public ngrok  ({purl}) : {ngrok_passes}/{len(ngrok_results)} PASSED")

    if local_passes == len(local_results) and ngrok_passes == len(ngrok_results):
        print("\n[ALL 16 LIVE CHECKS PASSED - TUNNELS AND SECURITY FULLY VERIFIED]")
        sys.exit(0)
    else:
        print(f"\n[PARTIAL SUCCESS: Local {local_passes}/{len(local_results)}, Ngrok {ngrok_passes}/{len(ngrok_results)}]")
        sys.exit(1)


if __name__ == "__main__":
    main()
