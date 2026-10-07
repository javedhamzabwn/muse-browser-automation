"""core/task_engine.py — Task Engine, Checkpointing & Resource Governor for Muse 3.0.

Provides multi-step task execution, state checkpointing, error recovery,
and resource limits (step budgets, timeouts, loop prevention).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from core.interfaces import BaseTaskEngine
from core.types import TaskCheckpoint

logger = logging.getLogger("muse.core.task_engine")


@dataclass
class ManagedTask:
    task_id: str
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    tool: Optional[str] = None
    browser: Optional[str] = None
    profile: Optional[str] = None
    status: str = "queued"
    duration: Optional[float] = None
    error: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskGovernor:
    """Resource governor enforcing concurrency limits, step budgets, and timeouts."""

    def __init__(
        self,
        max_concurrent_tasks: int = 5,
        max_steps_per_task: int = 100,
        step_timeout_sec: float = 30.0,
    ):
        self.max_steps_per_task = max_steps_per_task
        self.step_timeout_sec = step_timeout_sec
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._active_tasks: Dict[str, int] = {}  # task_id -> step_count

    async def acquire_slot(self) -> None:
        await self._semaphore.acquire()

    def release_slot(self) -> None:
        self._semaphore.release()

    def record_step(self, task_id: str) -> int:
        count = self._active_tasks.get(task_id, 0) + 1
        if count > self.max_steps_per_task:
            raise RuntimeError(
                f"Task '{task_id}' exceeded max step budget ({self.max_steps_per_task}). "
                "Possible infinite loop detected."
            )
        self._active_tasks[task_id] = count
        return count

    def finish_task(self, task_id: str) -> None:
        self._active_tasks.pop(task_id, None)


class TaskEngine(BaseTaskEngine):
    """Engine managing multi-step workflows, persistent checkpoints, and resilient retries."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        governor: Optional[TaskGovernor] = None,
    ):
        if db_path is None:
            data_dir = os.path.expanduser("~/.muse")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "tasks.db")
        else:
            self.db_path = db_path
            if self.db_path != ":memory:":
                parent = os.path.dirname(os.path.abspath(self.db_path))
                if parent:
                    os.makedirs(parent, exist_ok=True)

        self.governor = governor or TaskGovernor()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
                self._conn.execute("PRAGMA synchronous = NORMAL")
            except Exception:
                pass
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS task_checkpoints (
                        task_id TEXT NOT NULL,
                        step_index INTEGER NOT NULL,
                        action TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        PRIMARY KEY (task_id, step_index)
                    )
                """)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_checkpoint_lookup
                    ON task_checkpoints(task_id, step_index DESC)
                """)
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS managed_tasks (
                        task_id TEXT PRIMARY KEY,
                        created_at REAL NOT NULL,
                        started_at REAL,
                        finished_at REAL,
                        tool TEXT,
                        browser TEXT,
                        profile TEXT,
                        status TEXT NOT NULL,
                        duration REAL,
                        error TEXT,
                        payload_json TEXT
                    )
                """)

    async def create_checkpoint(self, checkpoint: TaskCheckpoint) -> None:
        """Persist a task checkpoint to SQLite."""
        state_str = json.dumps(checkpoint.state, default=str)
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO task_checkpoints (task_id, step_index, action, state_json, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(task_id, step_index) DO UPDATE SET
                        action = excluded.action,
                        state_json = excluded.state_json,
                        timestamp = excluded.timestamp
                    """,
                    (
                        checkpoint.task_id,
                        checkpoint.step_index,
                        checkpoint.action,
                        state_str,
                        checkpoint.timestamp,
                    ),
                )

    async def load_last_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        """Retrieve the latest verified checkpoint for task resumption."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT task_id, step_index, action, state_json, timestamp
                FROM task_checkpoints
                WHERE task_id = ?
                ORDER BY step_index DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()

            if not row:
                return None

            try:
                state_data = json.loads(row["state_json"])
            except Exception:
                state_data = {}

            return TaskCheckpoint(
                task_id=row["task_id"],
                step_index=row["step_index"],
                action=row["action"],
                state=state_data,
                timestamp=row["timestamp"],
            )

    async def list_checkpoints(self, task_id: str) -> List[TaskCheckpoint]:
        """List all historical checkpoints for a given task."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT task_id, step_index, action, state_json, timestamp
                FROM task_checkpoints
                WHERE task_id = ?
                ORDER BY step_index ASC
                """,
                (task_id,),
            ).fetchall()

            out = []
            for r in rows:
                try:
                    st = json.loads(r["state_json"])
                except Exception:
                    st = {}
                out.append(
                    TaskCheckpoint(
                        task_id=r["task_id"],
                        step_index=r["step_index"],
                        action=r["action"],
                        state=st,
                        timestamp=r["timestamp"],
                    )
                )
            return out

    async def clear_checkpoints(self, task_id: Optional[str] = None) -> None:
        """Purge checkpoints for a task or all tasks."""
        with self._lock:
            with self._conn:
                if task_id:
                    self._conn.execute("DELETE FROM task_checkpoints WHERE task_id = ?", (task_id,))
                else:
                    self._conn.execute("DELETE FROM task_checkpoints")

    async def run_step(
        self,
        task_id: str,
        step_index: int,
        action: str,
        step_coro_fn: Callable[[], Coroutine[Any, Any, Any]],
        max_retries: int = 3,
        state_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute a single workflow step with governor checks, retry logic, and auto-checkpointing."""
        self.governor.record_step(task_id)

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                res = await asyncio.wait_for(
                    step_coro_fn(), timeout=self.governor.step_timeout_sec
                )
                # Successful execution: create checkpoint
                snap = state_snapshot or {}
                snap["attempt"] = attempt
                snap["ok"] = True
                await self.create_checkpoint(
                    TaskCheckpoint(
                        task_id=task_id,
                        step_index=step_index,
                        action=action,
                        state=snap,
                    )
                )
                return res
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Task '%s' step %d (%s) attempt %d/%d failed: %s",
                    task_id,
                    step_index,
                    action,
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    # Jittered exponential backoff
                    await asyncio.sleep(0.05 * (2 ** (attempt - 1)))

        raise RuntimeError(
            f"Task '{task_id}' step {step_index} ({action}) failed after {max_retries} attempts: {last_error}"
        )

    def register_task(
        self,
        task_id: str,
        tool: Optional[str] = None,
        browser: Optional[str] = None,
        profile: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ManagedTask:
        """Register a new managed task in queued status."""
        task = ManagedTask(
            task_id=task_id,
            created_at=time.time(),
            tool=tool,
            browser=browser,
            profile=profile,
            status="queued",
            payload=payload or {},
        )
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO managed_tasks
                    (task_id, created_at, started_at, finished_at, tool, browser, profile, status, duration, error, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.created_at,
                        task.started_at,
                        task.finished_at,
                        task.tool,
                        task.browser,
                        task.profile,
                        task.status,
                        task.duration,
                        task.error,
                        json.dumps(task.payload),
                    ),
                )
        return task

    def update_task(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> None:
        """Update task state (running, waiting_approval, waiting_human, completed, failed, cancelled)."""
        now = time.time()
        with self._lock:
            with self._conn:
                if status == "running":
                    self._conn.execute(
                        "UPDATE managed_tasks SET status = ?, started_at = coalesce(started_at, ?) WHERE task_id = ?",
                        (status, now, task_id),
                    )
                elif status in ("completed", "failed", "cancelled"):
                    self._conn.execute(
                        "UPDATE managed_tasks SET status = ?, finished_at = ?, error = coalesce(?, error), duration = coalesce(?, duration) WHERE task_id = ?",
                        (status, now, error, duration, task_id),
                    )
                else:
                    self._conn.execute(
                        "UPDATE managed_tasks SET status = ?, error = coalesce(?, error) WHERE task_id = ?",
                        (status, error, task_id),
                    )

    def get_task(self, task_id: str) -> Optional[ManagedTask]:
        """Fetch managed task by ID."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM managed_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            return ManagedTask(
                task_id=row["task_id"],
                created_at=row["created_at"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                tool=row["tool"],
                browser=row["browser"],
                profile=row["profile"],
                status=row["status"],
                duration=row["duration"],
                error=row["error"],
                payload=payload,
            )

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[ManagedTask]:
        """List recent tasks, optionally filtered by status."""
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM managed_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM managed_tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            tasks = []
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except Exception:
                    payload = {}
                tasks.append(
                    ManagedTask(
                        task_id=row["task_id"],
                        created_at=row["created_at"],
                        started_at=row["started_at"],
                        finished_at=row["finished_at"],
                        tool=row["tool"],
                        browser=row["browser"],
                        profile=row["profile"],
                        status=row["status"],
                        duration=row["duration"],
                        error=row["error"],
                        payload=payload,
                    )
                )
            return tasks

    def cancel_task(self, task_id: str) -> bool:
        """Mark task as cancelled."""
        task = self.get_task(task_id)
        if not task:
            return False
        if task.status in ("completed", "failed", "cancelled"):
            return False
        self.update_task(task_id, "cancelled", error="Cancelled by user/agent")
        return True

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
