"""
core/task_state.py — Task Lifecycle State Machine for KuroAgent

Implements a structured task lifecycle with persistence:

  PENDING → PLANNING → EXECUTING → VERIFYING → COMPLETED
                                 ↘ FAILED → RECOVERING → RETRY → VERIFYING

Possible states:
  PENDING     — Task created but not yet started
  PLANNING    — Agent is decomposing the goal into steps
  EXECUTING   — Steps are being executed
  WAITING     — Waiting for user input or external event
  VERIFYING   — Checking whether the action succeeded
  RECOVERING  — Handling a failure, trying to recover
  COMPLETED   — Task successfully finished
  FAILED      — Task failed and recovery was not possible
  CANCELLED   — Task was cancelled by user

Tasks are persisted in SQLite so Kuro can recover from interrupted sessions.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# State Enum
# ─────────────────────────────────────────────────────────────────────────────

class TaskState(str, Enum):
    PENDING    = "pending"
    PLANNING   = "planning"
    EXECUTING  = "executing"
    WAITING    = "waiting"
    VERIFYING  = "verifying"
    RECOVERING = "recovering"
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


# Valid state transitions
_VALID_TRANSITIONS: Dict[TaskState, List[TaskState]] = {
    TaskState.PENDING:    [TaskState.PLANNING, TaskState.CANCELLED],
    TaskState.PLANNING:   [TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED],
    TaskState.EXECUTING:  [TaskState.VERIFYING, TaskState.WAITING, TaskState.FAILED, TaskState.CANCELLED],
    TaskState.WAITING:    [TaskState.EXECUTING, TaskState.CANCELLED, TaskState.FAILED],
    TaskState.VERIFYING:  [TaskState.COMPLETED, TaskState.RECOVERING, TaskState.FAILED, TaskState.EXECUTING],
    TaskState.RECOVERING: [TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED],
    TaskState.COMPLETED:  [],  # Terminal state
    TaskState.FAILED:     [TaskState.RECOVERING, TaskState.CANCELLED],  # Allow retry from failed
    TaskState.CANCELLED:  [],  # Terminal state
}

TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}


# ─────────────────────────────────────────────────────────────────────────────
# Task Data Model
# ─────────────────────────────────────────────────────────────────────────────

class Task:
    """
    Represents a single agent task with full lifecycle tracking.

    Attributes:
        task_id: Unique identifier.
        goal: The original user request / goal description.
        state: Current lifecycle state.
        plan: Optional structured plan (list of steps from planner).
        steps_completed: Number of steps completed.
        steps_total: Total number of steps in the plan.
        error: Last error message (if any).
        verification_result: Result of the last verification.
        retry_count: Number of times this task has been retried.
        metadata: Arbitrary key-value store for extra data.
        created_at: Unix timestamp when task was created.
        updated_at: Unix timestamp of last state change.
        history: List of state transition records.
    """

    def __init__(
        self,
        goal: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.task_id: str = task_id or f"task_{uuid.uuid4().hex[:10]}"
        self.goal: str = goal
        self.state: TaskState = TaskState.PENDING
        self.plan: Optional[Dict[str, Any]] = None
        self.steps_completed: int = 0
        self.steps_total: int = 0
        self.error: Optional[str] = None
        self.verification_result: Optional[str] = None
        self.retry_count: int = 0
        self.metadata: Dict[str, Any] = metadata or {}
        self.created_at: float = time.time()
        self.updated_at: float = self.created_at
        self.history: List[Dict[str, Any]] = []

    # ── State Machine ─────────────────────────────────────────────────────────

    def transition(self, new_state: TaskState, reason: str = "") -> bool:
        """
        Attempts to transition to a new state.

        Returns True if the transition was valid and applied.
        Returns False if the transition is not allowed from the current state.
        """
        allowed = _VALID_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            return False

        record = {
            "from": self.state.value,
            "to": new_state.value,
            "reason": reason,
            "timestamp": time.time(),
        }
        self.history.append(record)
        self.state = new_state
        self.updated_at = time.time()
        self._auto_persist()
        return True

    def force_transition(self, new_state: TaskState, reason: str = "") -> None:
        """Forces a state transition (bypasses validation — use sparingly)."""
        record = {
            "from": self.state.value,
            "to": new_state.value,
            "reason": f"[FORCED] {reason}",
            "timestamp": time.time(),
        }
        self.history.append(record)
        self.state = new_state
        self.updated_at = time.time()
        self._auto_persist()

    def _auto_persist(self) -> None:
        try:
            from core import memory_db
            memory_db.save_task(self.to_dict())
        except Exception:
            pass

    def is_terminal(self) -> bool:
        """Returns True if the task is in a terminal state (completed/failed/cancelled)."""
        return self.state in TERMINAL_STATES

    def can_retry(self, max_retries: int = 3) -> bool:
        """Returns True if the task can be retried."""
        return self.state == TaskState.FAILED and self.retry_count < max_retries

    def mark_planning(self) -> bool:
        return self.transition(TaskState.PLANNING, "Starting planning phase")

    def mark_executing(self) -> bool:
        return self.transition(TaskState.EXECUTING, "Executing plan steps")

    def mark_verifying(self, result: Optional[str] = None) -> bool:
        if result:
            self.verification_result = result
        return self.transition(TaskState.VERIFYING, "Verifying action result")

    def mark_completed(self, result: Optional[str] = None) -> bool:
        if result:
            self.verification_result = result
        return self.transition(TaskState.COMPLETED, "Task completed successfully")

    def mark_failed(self, error: str) -> bool:
        self.error = error
        return self.transition(TaskState.FAILED, f"Task failed: {error}")

    def mark_recovering(self) -> bool:
        self.retry_count += 1
        return self.transition(TaskState.RECOVERING, f"Recovering (attempt {self.retry_count})")

    def mark_cancelled(self, reason: str = "User cancelled") -> bool:
        return self.transition(TaskState.CANCELLED, reason)

    def mark_waiting(self, reason: str = "Waiting") -> bool:
        return self.transition(TaskState.WAITING, reason)

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "state": self.state.value,
            "plan": self.plan,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "error": self.error,
            "verification_result": self.verification_result,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        task = cls(goal=data["goal"], task_id=data.get("task_id"))
        task.state = TaskState(data.get("state", "pending"))
        task.plan = data.get("plan")
        task.steps_completed = data.get("steps_completed", 0)
        task.steps_total = data.get("steps_total", 0)
        task.error = data.get("error")
        task.verification_result = data.get("verification_result")
        task.retry_count = data.get("retry_count", 0)
        task.metadata = data.get("metadata", {})
        task.created_at = data.get("created_at", time.time())
        task.updated_at = data.get("updated_at", time.time())
        task.history = data.get("history", [])
        return task

    def __repr__(self) -> str:
        return f"Task(id={self.task_id!r}, goal={self.goal[:40]!r}, state={self.state.value!r})"


# ─────────────────────────────────────────────────────────────────────────────
# Task Registry (in-memory + SQLite persistence)
# ─────────────────────────────────────────────────────────────────────────────

class TaskRegistry:
    """
    Manages active and historical tasks.

    Persists tasks in SQLite for cross-session recovery.
    """

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._current_task_id: Optional[str] = None

    def create(self, goal: str, metadata: Optional[Dict[str, Any]] = None) -> Task:
        """Creates a new task and registers it."""
        task = Task(goal=goal, metadata=metadata)
        self._tasks[task.task_id] = task
        self._current_task_id = task.task_id
        self._persist(task)
        return task

    def get(self, task_id: str) -> Optional[Task]:
        """Returns a task by ID from the in-memory registry."""
        return self._tasks.get(task_id)

    def get_current(self) -> Optional[Task]:
        """Returns the most recently created/active task."""
        if self._current_task_id:
            return self._tasks.get(self._current_task_id)
        return None

    def set_current(self, task_id: str) -> bool:
        """Sets the current active task."""
        if task_id in self._tasks:
            self._current_task_id = task_id
            return True
        return False

    def list_active(self) -> List[Task]:
        """Returns all tasks that are not in a terminal state."""
        return [t for t in self._tasks.values() if not t.is_terminal()]

    def list_all(self) -> List[Task]:
        """Returns all tasks."""
        return list(self._tasks.values())

    def update(self, task: Task) -> None:
        """Persists an updated task."""
        self._tasks[task.task_id] = task
        self._persist(task)

    def _persist(self, task: Task) -> None:
        """Saves task state to SQLite."""
        try:
            from core import memory_db
            memory_db.save_task(task.to_dict())
        except Exception:
            pass  # Non-fatal — in-memory still works

    def load_from_db(self) -> None:
        """Loads recent tasks from SQLite into the in-memory registry."""
        try:
            from core import memory_db
            rows = memory_db.list_tasks(limit=50)
            for row in rows:
                task = Task.from_dict(row)
                self._tasks[task.task_id] = task
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Global Registry Instance
# ─────────────────────────────────────────────────────────────────────────────

task_registry = TaskRegistry()
