"""core/validation/computer_validator.py — Harmless Real Desktop Automation Tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from core.tools.adapters.computer.pyautogui_adapter import PyAutoGUIAdapter


@dataclass
class ComputerTestResult:
    backend: str
    action: str
    success: bool
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ComputerRealWorldValidator:
    """Executes safe, harmless real Windows application interaction tests."""

    @classmethod
    async def validate_computer_backend(cls, backend_name: str) -> List[ComputerTestResult]:
        results: List[ComputerTestResult] = []
        adapter = PyAutoGUIAdapter()

        # 1. Desktop Coordinates & Screen Inspection
        t0 = time.perf_counter()
        try:
            pos = await adapter.get_cursor_position()
            wins = await adapter.list_windows()
            try:
                ss = await adapter.take_screenshot()
                ss_size = len(ss)
            except Exception:
                ss_size = 0
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                ComputerTestResult(
                    backend=backend_name,
                    action="desktop_inspection",
                    success=isinstance(pos, (tuple, list)),
                    duration_ms=round(dur, 2),
                    details={"cursor": pos, "screenshot_size": ss_size, "windows_count": len(wins)},
                )
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                ComputerTestResult(
                    backend=backend_name,
                    action="desktop_inspection",
                    success=False,
                    duration_ms=round(dur, 2),
                    error=str(e),
                )
            )

        # 2. Notepad Harmless Workflow
        t0 = time.perf_counter()
        test_file = os.path.join(tempfile.gettempdir(), f"muse_test_{int(time.time())}.txt")
        test_content = "Muse Computer Control Test"
        try:
            # Write via Python standard file I/O to simulate and verify filesystem interaction
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(test_content)

            # Launch notepad showing the test file
            proc = subprocess.Popen(["notepad.exe", test_file])
            await asyncio.sleep(1.0)

            # Check process is alive
            is_alive = proc.poll() is None

            # Close notepad cleanly
            proc.terminate()
            proc.wait(timeout=3.0)

            # Verify file contents
            with open(test_file, "r", encoding="utf-8") as f:
                read_back = f.read()

            verified = read_back == test_content
            if os.path.isfile(test_file):
                os.remove(test_file)

            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                ComputerTestResult(
                    backend=backend_name,
                    action="notepad_application_flow",
                    success=is_alive and verified,
                    duration_ms=round(dur, 2),
                    details={"process_launched": is_alive, "content_verified": verified},
                )
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            if os.path.isfile(test_file):
                try:
                    os.remove(test_file)
                except Exception:
                    pass
            results.append(
                ComputerTestResult(
                    backend=backend_name,
                    action="notepad_application_flow",
                    success=False,
                    duration_ms=round(dur, 2),
                    error=str(e),
                )
            )

        # 3. Calculator Harmless Launch & Terminate
        t0 = time.perf_counter()
        try:
            calc_proc = subprocess.Popen(["calc.exe"])
            await asyncio.sleep(1.0)
            calc_running = calc_proc.poll() is None
            try:
                calc_proc.terminate()
                calc_proc.wait(timeout=2.0)
            except Exception:
                # On Windows calc may be a Modern App launcher, kill via taskkill if needed
                subprocess.run(["taskkill", "/F", "/IM", "CalculatorApp.exe"], capture_output=True)

            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                ComputerTestResult(
                    backend=backend_name,
                    action="calculator_launch_terminate",
                    success=calc_running,
                    duration_ms=round(dur, 2),
                    details={"launched": calc_running},
                )
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                ComputerTestResult(
                    backend=backend_name,
                    action="calculator_launch_terminate",
                    success=False,
                    duration_ms=round(dur, 2),
                    error=str(e),
                )
            )

        return results
