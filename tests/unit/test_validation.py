"""tests/unit/test_validation.py — Unit tests for Real-World Validation Suite."""

import asyncio
import os
import shutil
import tempfile
import unittest

from core.validation.browser_validator import BrowserRealWorldValidator, WebsiteTestResult
from core.validation.computer_validator import ComputerRealWorldValidator, ComputerTestResult
from core.validation.mcp_validator import McpGatewayValidator, McpTestResult
from core.validation.runner import ValidationRunner


class TestValidationSuite(unittest.TestCase):
    def setUp(self):
        self.temp_reports = tempfile.mkdtemp(prefix="muse_test_reports_")
        self.runner = ValidationRunner(output_root=self.temp_reports)

    def tearDown(self):
        shutil.rmtree(self.temp_reports, ignore_errors=True)

    def test_mcp_gateway_validation(self):
        val = McpGatewayValidator(mcp_url="http://127.0.0.1:18010/mcp")
        results = val.validate_mcp_gateway()
        self.assertTrue(len(results) >= 3)
        # Check initialize passes
        init_res = next((r for r in results if r.test_name == "mcp_initialize"), None)
        self.assertIsNotNone(init_res)
        self.assertTrue(init_res.success)

        # Check tools list passes
        list_res = next((r for r in results if r.test_name == "mcp_tools_list"), None)
        self.assertIsNotNone(list_res)
        self.assertTrue(list_res.success)
        self.assertGreaterEqual(list_res.details.get("total_tools", 0), 20)

    def test_computer_use_validation(self):
        results = asyncio.run(ComputerRealWorldValidator.validate_computer_backend("pyautogui"))
        self.assertTrue(len(results) >= 2)
        actions = [r.action for r in results]
        self.assertIn("desktop_inspection", actions)
        self.assertIn("notepad_application_flow", actions)

    def test_synthetic_and_local_categories(self):
        cat1 = asyncio.run(self.runner.run_synthetic_tests())
        self.assertEqual(cat1["category"], "Synthetic tests")
        self.assertTrue(cat1["total"] >= 1)

        cat4 = asyncio.run(self.runner.run_browser_session_tests())
        self.assertEqual(cat4["category"], "Real browser-session tests")
        self.assertEqual(cat4["failed"], 0)
        self.assertTrue(cat4["passed"] >= 3)

    def test_report_generation(self):
        res = asyncio.run(self.runner.run_all())
        self.assertIn("categories", res)
        self.assertEqual(len(res["categories"]), 6)

        # Check all required files were generated
        summary_md = os.path.join(self.temp_reports, "tool-validation", "summary.md")
        browser_json = os.path.join(self.temp_reports, "tool-validation", "browser-results.json")
        computer_json = os.path.join(self.temp_reports, "tool-validation", "computer-results.json")
        mcp_json = os.path.join(self.temp_reports, "tool-validation", "mcp-results.json")
        bm_json = os.path.join(self.temp_reports, "tool-validation", "benchmarks.json")
        errors_json = os.path.join(self.temp_reports, "tool-validation", "errors.json")

        self.assertTrue(os.path.isfile(summary_md))
        self.assertTrue(os.path.isfile(browser_json))
        self.assertTrue(os.path.isfile(computer_json))
        self.assertTrue(os.path.isfile(mcp_json))
        self.assertTrue(os.path.isfile(bm_json))
        self.assertTrue(os.path.isfile(errors_json))

        # Check content in summary.md
        with open(summary_md, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Muse Browser Automation 4.0", content)
            self.assertIn("Category Status Matrix", content)


if __name__ == "__main__":
    unittest.main()
