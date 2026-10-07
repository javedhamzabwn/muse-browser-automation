"""tests/unit/test_task_engine.py — Unit tests for Phase 7 Task Engine & Resource Governor."""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.task_engine import TaskEngine, TaskGovernor
from core.types import TaskCheckpoint


class TestTaskEngine(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = TaskEngine(db_path=":memory:")

    async def asyncTearDown(self):
        self.engine.close()

    async def test_checkpoint_lifecycle(self):
        # Initial check
        last = await self.engine.load_last_checkpoint("task-1")
        self.assertIsNone(last)

        # Store checkpoint 0
        cp0 = TaskCheckpoint(task_id="task-1", step_index=0, action="navigate", state={"url": "https://example.com"})
        await self.engine.create_checkpoint(cp0)

        # Store checkpoint 1
        cp1 = TaskCheckpoint(task_id="task-1", step_index=1, action="click", state={"target": "#login"})
        await self.engine.create_checkpoint(cp1)

        # Load last
        last = await self.engine.load_last_checkpoint("task-1")
        self.assertIsNotNone(last)
        self.assertEqual(last.step_index, 1)
        self.assertEqual(last.action, "click")
        self.assertEqual(last.state.get("target"), "#login")

        # List all
        all_cps = await self.engine.list_checkpoints("task-1")
        self.assertEqual(len(all_cps), 2)
        self.assertEqual(all_cps[0].action, "navigate")
        self.assertEqual(all_cps[1].action, "click")

        # Clear
        await self.engine.clear_checkpoints("task-1")
        self.assertIsNone(await self.engine.load_last_checkpoint("task-1"))

    async def test_run_step_success_auto_checkpoint(self):
        calls = 0

        async def step_action():
            nonlocal calls
            calls += 1
            return "done"

        res = await self.engine.run_step(
            task_id="task-run",
            step_index=0,
            action="submit",
            step_coro_fn=step_action,
            state_snapshot={"field": "val"},
        )
        self.assertEqual(res, "done")
        self.assertEqual(calls, 1)

        last = await self.engine.load_last_checkpoint("task-run")
        self.assertIsNotNone(last)
        self.assertEqual(last.step_index, 0)
        self.assertEqual(last.state.get("ok"), True)
        self.assertEqual(last.state.get("field"), "val")

    async def test_run_step_retry_recovery(self):
        attempts = 0

        async def flaky_step():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionResetError("Transient network failure")
            return "recovered"

        res = await self.engine.run_step(
            task_id="task-flaky",
            step_index=0,
            action="fetch",
            step_coro_fn=flaky_step,
            max_retries=3,
        )
        self.assertEqual(res, "recovered")
        self.assertEqual(attempts, 3)

        last = await self.engine.load_last_checkpoint("task-flaky")
        self.assertIsNotNone(last)
        self.assertEqual(last.state.get("attempt"), 3)

    async def test_run_step_retry_exhaustion(self):
        async def always_fails():
            raise ValueError("Permanent failure")

        with self.assertRaises(RuntimeError) as ctx:
            await self.engine.run_step(
                task_id="task-fail",
                step_index=0,
                action="bad_step",
                step_coro_fn=always_fails,
                max_retries=2,
            )
        self.assertIn("failed after 2 attempts", str(ctx.exception))

    async def test_governor_budget_exceeded(self):
        gov = TaskGovernor(max_steps_per_task=2)
        engine = TaskEngine(db_path=":memory:", governor=gov)

        async def dummy_step():
            return True

        # Step 1: OK
        await engine.run_step("task-gov", 0, "s1", dummy_step)
        # Step 2: OK
        await engine.run_step("task-gov", 1, "s2", dummy_step)
        # Step 3: Exceeds budget (2) -> raises RuntimeError
        with self.assertRaises(RuntimeError) as ctx:
            await engine.run_step("task-gov", 2, "s3", dummy_step)
        self.assertIn("exceeded max step budget", str(ctx.exception))
        engine.close()

    def test_managed_tasks_lifecycle(self):
        t = self.engine.register_task(
            task_id="task-101",
            tool="moli",
            browser="playwright",
            profile="default",
            payload={"url": "https://example.com"},
        )
        self.assertEqual(t.status, "queued")

        self.engine.update_task("task-101", "running")
        t2 = self.engine.get_task("task-101")
        self.assertEqual(t2.status, "running")
        self.assertIsNotNone(t2.started_at)

        self.engine.update_task("task-101", "waiting_approval")
        self.assertEqual(self.engine.get_task("task-101").status, "waiting_approval")

        self.engine.update_task("task-101", "completed", duration=120.5)
        t_done = self.engine.get_task("task-101")
        self.assertEqual(t_done.status, "completed")
        self.assertEqual(t_done.duration, 120.5)

        # Cancel another task
        self.engine.register_task("task-102")
        self.assertTrue(self.engine.cancel_task("task-102"))
        self.assertEqual(self.engine.get_task("task-102").status, "cancelled")


if __name__ == "__main__":
    unittest.main()
