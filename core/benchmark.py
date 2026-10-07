"""core/benchmark.py — Latency and throughput benchmarking harness for Muse 3.0."""

from __future__ import annotations

import asyncio
import json
import statistics
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional


class BenchmarkRunner:
    """Measures latency of operations across iterations and computes p50/p95/p99."""

    def __init__(self, daemon_url: str = "http://127.0.0.1:18010"):
        self.daemon_url = daemon_url
        self.results: Dict[str, Dict[str, float]] = {}

    def _call_tool(self, tool: str, args: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        req = urllib.request.Request(
            f"{self.daemon_url}/tool",
            data=json.dumps({"tool": tool, "args": args or {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return {"data": data, "latency_ms": dt_ms}

    def measure_sync(self, name: str, fn: Callable[[], Any], iterations: int = 10) -> Dict[str, float]:
        latencies: List[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            fn()
            dt_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(dt_ms)
        return self._calc_stats(name, latencies)

    async def measure_async(self, name: str, fn: Callable[[], Any], iterations: int = 10) -> Dict[str, float]:
        latencies: List[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            await fn()
            dt_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(dt_ms)
        return self._calc_stats(name, latencies)

    def _calc_stats(self, name: str, latencies: List[float]) -> Dict[str, float]:
        sorted_lat = sorted(latencies)
        count = len(sorted_lat)
        p50 = sorted_lat[int(count * 0.50)]
        p90 = sorted_lat[int(count * 0.90)]
        p95 = sorted_lat[min(int(count * 0.95), count - 1)]
        p99 = sorted_lat[min(int(count * 0.99), count - 1)]
        stats = {
            "count": count,
            "min_ms": round(sorted_lat[0], 2),
            "p50_ms": round(p50, 2),
            "p90_ms": round(p90, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "max_ms": round(sorted_lat[-1], 2),
            "mean_ms": round(statistics.mean(sorted_lat), 2),
        }
        self.results[name] = stats
        return stats

    def run_daemon_suite(self, iterations: int = 10) -> Dict[str, Dict[str, float]]:
        """Run standard benchmarks against live HTTP daemon."""
        # 1. Health check
        def ping_test():
            req = urllib.request.Request(f"{self.daemon_url}/health")
            with urllib.request.urlopen(req, timeout=5.0) as r:
                return json.loads(r.read().decode())
        self.measure_sync("daemon_health_get", ping_test, iterations=iterations)

        # 2. Tool ping
        def tool_ping():
            return self._call_tool("ping")
        self.measure_sync("daemon_tool_ping", tool_ping, iterations=iterations)

        # 3. Tab list
        def tool_tabs_list():
            return self._call_tool("tabs_list")
        self.measure_sync("daemon_tabs_list", tool_tabs_list, iterations=iterations)

        return self.results

    def generate_markdown_report(self) -> str:
        lines = [
            "# Muse 3.0 Performance Benchmark Report",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "| Operation | Count | Min (ms) | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Mean (ms) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for op, s in self.results.items():
            lines.append(
                f"| `{op}` | {s['count']} | {s['min_ms']} | {s['p50_ms']} | "
                f"{s['p90_ms']} | {s['p95_ms']} | {s['p99_ms']} | {s['mean_ms']} |"
            )
        return "\n".join(lines)


if __name__ == "__main__":
    runner = BenchmarkRunner()
    print("[benchmark] Running daemon benchmark suite...")
    try:
        runner.run_daemon_suite(iterations=10)
        report = runner.generate_markdown_report()
        print(report)
    except Exception as e:
        print(f"[benchmark] Daemon not available or error: {e}")
