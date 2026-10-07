# Session Lifecycle & Task Engine

## Overview

The Session and Task Engine (`core/task_engine.py`) provides durable execution guarantees for multi-step browser automations. Long-running or multi-step agent actions are tracked as stateful tasks that can pause, resume, checkpoint, and gracefully handle transient failures.

---

## Task Lifecycle States

```
                +------------+
                |   QUEUED   |
                +-----+------+
                      |
                      v
                +------------+      Require Human
                |  RUNNING   |-------------------------> +----------------+
                +-----+------+                           | WAITING_HUMAN  |
                      |                                  +--------+-------+
                      |                                           |
                      | Action verification passed                | Approved
                      v                                           v
                +------------+                           +----------------+
                | COMPLETED  | <-------------------------| RUNNING (CONT) |
                +------------+                           +----------------+
                      |
                      | Unrecoverable error
                      v
                +------------+
                |   FAILED   |
                +------------+
```

### State Definitions

- `QUEUED`: Task created and awaiting worker execution.
- `RUNNING`: Actively performing navigation, DOM extraction, or interaction steps.
- `WAITING_APPROVAL`: Paused waiting for user or agent approval before executing high-risk mutations (payments, account settings).
- `WAITING_HUMAN`: Paused waiting for human input on complex CAPTCHAs, SMS OTPs, or MFA challenges.
- `COMPLETED`: All steps executed and verified successfully.
- `FAILED`: Retry budget exhausted or fatal runtime failure encountered.
- `CANCELLED`: Explicitly aborted via API or MCP command.

---

## Checkpointing & State Persistence

Tasks maintain full audit trails in `~/.muse/tasks.db` (SQLite):

- **Automatic Checkpointing**: Checkpoint created after each successful step with DOM snapshot, active URL, and session metadata.
- **Resumability**: If the daemon restarts or crashes, incomplete tasks can be reloaded and resumed from their last verified checkpoint without restarting from scratch.
- **Budget Governor**: Tracks execution time and action counts against configurable budgets to prevent runaway loops:
  ```python
  TaskGovernor(max_runtime_sec=300, max_actions=50)
  ```

---

## Step Retries & Transient Recovery

When an action step fails:
1. The error classifier identifies if the failure is transient (e.g. element not yet attached, network blip).
2. For transient failures, the step is retried with exponential backoff (up to `max_retries`).
3. For permanent failures (e.g. 404 Not Found, bad selector syntax), execution halts immediately, saving the error snapshot to the task record.
