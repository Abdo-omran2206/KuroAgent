"""
KURO SQLite Database Storage Module (memory_db.py)

Manages persistent SQLite storage in d:\\vscode\\Kuro\\brain\\kuro.db.
Handles conversation history, personality traits, execution plans, and skills.
Ensures thread safety by using context-managed connection instances with check_same_thread=False.
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import config
from core.paths import APP_DIR as BASE_DIR, BRAIN_DIR as DB_DIR, DB_PATH


@contextmanager
def get_db():
    """Context manager providing thread-safe SQLite connection and transaction management."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initializes the SQLite schema in kuro.db if tables do not already exist."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Conversations Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                user_text TEXT,
                assistant_text TEXT,
                summary TEXT,
                metadata TEXT
            )
            """
        )

        # Personality Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS personality (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )
            """
        )

        # Plans Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                title TEXT,
                goal TEXT,
                steps_json TEXT,
                status TEXT,
                created_at REAL,
                updated_at REAL
            )
            """
        )

        # Skills Table (legacy — kept for backward compatibility)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                name TEXT PRIMARY KEY,
                description TEXT,
                steps TEXT,
                created_at REAL
            )
            """
        )

        # ── Semantic Memory (facts, knowledge, project info) ──────────────────
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at REAL,
                updated_at REAL
            )
            """
        )

        # ── Procedural Memory (full structured skill system) ───────────────────
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS procedural_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                workflow TEXT DEFAULT '',
                required_tools TEXT DEFAULT '[]',
                preconditions TEXT DEFAULT '[]',
                known_failures TEXT DEFAULT '[]',
                parameters TEXT DEFAULT '{}',
                examples TEXT DEFAULT '[]',
                version TEXT DEFAULT '1.0.0',
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                created_at REAL,
                updated_at REAL
            )
            """
        )

        # ── Task State Persistence ─────────────────────────────────────────────
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                state TEXT DEFAULT 'pending',
                plan TEXT DEFAULT '{}',
                steps_completed INTEGER DEFAULT 0,
                steps_total INTEGER DEFAULT 0,
                error TEXT,
                verification_result TEXT,
                retry_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                history TEXT DEFAULT '[]',
                created_at REAL,
                updated_at REAL
            )
            """
        )

        # ── Execution Metrics ──────────────────────────────────────────────────
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                model TEXT,
                provider TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                tool_calls INTEGER DEFAULT 0,
                retries INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                success INTEGER DEFAULT 0,
                verification_result TEXT,
                estimated_cost REAL,
                created_at REAL
            )
            """
        )



def save_chat_entry(user_text: str, assistant_text: str, metadata: Any = None) -> int:
    """Saves a user interaction and assistant response to conversations table.

    Args:
        user_text: Input text from the user.
        assistant_text: Response text from the assistant.
        metadata: Optional dictionary or JSON string containing metadata.

    Returns:
        The row ID of the inserted conversation entry.
    """
    init_db()
    if metadata is not None and not isinstance(metadata, str):
        metadata_str = json.dumps(metadata, ensure_ascii=False)
    else:
        metadata_str = metadata

    now = time.time()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO conversations (timestamp, user_text, assistant_text, summary, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now, user_text, assistant_text, None, metadata_str)
        )
        return cursor.lastrowid


def get_chat_history(limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves the recent chat history in chronological order.

    Args:
        limit: Maximum number of recent chat entries to return.

    Returns:
        List of conversation dictionaries.
    """
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, user_text, assistant_text, summary, metadata
            FROM conversations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()

    history = []
    for row in reversed(rows):
        meta = row["metadata"]
        if meta and isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                pass
        history.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "user_text": row["user_text"],
            "assistant_text": row["assistant_text"],
            "summary": row["summary"],
            "metadata": meta
        })
    return history


def save_conversation_summary(summary_text: str) -> None:
    """Saves or updates a conversation summary in the database."""
    init_db()
    now = time.time()
    with get_db() as conn:
        cursor = conn.cursor()
        # Find the latest conversation row to attach summary to
        cursor.execute("SELECT id FROM conversations ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE conversations SET summary = ? WHERE id = ?", (summary_text, row["id"]))
        else:
            cursor.execute(
                """
                INSERT INTO conversations (timestamp, user_text, assistant_text, summary, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, "", "", summary_text, None)
            )


def get_latest_summary() -> Optional[str]:
    """Retrieves the most recent conversation summary."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT summary FROM conversations
            WHERE summary IS NOT NULL AND summary != ''
            ORDER BY id DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
        return row["summary"] if row else None


def save_plan(plan_id: str, title: str, goal: str, steps: Any, status: str = "pending") -> Dict[str, Any]:
    """Saves or updates a plan in the database.

    Args:
        plan_id: Unique identifier for the plan.
        title: Plan title.
        goal: Goal description.
        steps: List of step descriptions or dicts.
        status: Current plan status (default: 'pending').

    Returns:
        The saved plan dictionary.
    """
    init_db()
    now = time.time()
    if isinstance(steps, (list, dict)):
        steps_json = json.dumps(steps, ensure_ascii=False)
    elif isinstance(steps, str):
        steps_json = steps
    else:
        steps_json = json.dumps([])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT created_at FROM plans WHERE id = ?", (plan_id,))
        existing = cursor.fetchone()
        created_at = existing["created_at"] if existing else now

        cursor.execute(
            """
            INSERT INTO plans (id, title, goal, steps_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                goal = excluded.goal,
                steps_json = excluded.steps_json,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (plan_id, title, goal, steps_json, status, created_at, now)
        )
    return get_plan(plan_id)


def get_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a plan by ID."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        row = cursor.fetchone()
        if not row:
            return None

        steps = row["steps_json"]
        if steps:
            try:
                steps = json.loads(steps)
            except Exception:
                pass
        return {
            "id": row["id"],
            "title": row["title"],
            "goal": row["goal"],
            "steps": steps,
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }


def update_plan_step(plan_id: str, step_index: int, status: str, result: Any = None) -> Optional[Dict[str, Any]]:
    """Updates the status and optional result of a specific step in a plan.

    Args:
        plan_id: Unique identifier for the plan.
        step_index: Index of the step to update (0-indexed).
        status: New status for the step (e.g. 'completed', 'in_progress', 'failed').
        result: Optional result or output message for the step.

    Returns:
        Updated plan dictionary or None if plan not found / index out of bounds.
    """
    plan = get_plan(plan_id)
    if not plan:
        return None

    steps = plan.get("steps", [])
    if not isinstance(steps, list) or step_index < 0 or step_index >= len(steps):
        return None

    step = steps[step_index]
    if isinstance(step, dict):
        step["status"] = status
        if result is not None:
            step["result"] = result
    elif isinstance(step, str):
        steps[step_index] = {
            "description": step,
            "status": status,
            "result": result
        }
    else:
        steps[step_index] = {
            "step": str(step),
            "status": status,
            "result": result
        }

    steps_json = json.dumps(steps, ensure_ascii=False)
    now = time.time()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE plans SET steps_json = ?, updated_at = ? WHERE id = ?",
            (steps_json, now, plan_id)
        )
    return get_plan(plan_id)


def list_plans() -> List[Dict[str, Any]]:
    """Returns a list of all plans sorted by updated_at descending."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans ORDER BY updated_at DESC")
        rows = cursor.fetchall()

    plans = []
    for row in rows:
        steps = row["steps_json"]
        if steps:
            try:
                steps = json.loads(steps)
            except Exception:
                pass
        plans.append({
            "id": row["id"],
            "title": row["title"],
            "goal": row["goal"],
            "steps": steps,
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })
    return plans


def set_personality_trait(key: str, value: str) -> None:
    """Sets or updates a personality trait key-value pair."""
    init_db()
    now = time.time()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO personality (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, str(value), now)
        )


def get_personality() -> Dict[str, str]:
    """Retrieves all personality traits as a dictionary of key-value pairs."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM personality")
        rows = cursor.fetchall()
    return {row["key"]: row["value"] for row in rows}


def save_skill(name: str, description: str, steps: Any) -> Dict[str, Any]:
    """Saves or updates a skill in the skills table."""
    init_db()
    now = time.time()
    steps_str = json.dumps(steps, ensure_ascii=False) if not isinstance(steps, str) else steps
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO skills (name, description, steps, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                steps = excluded.steps
            """,
            (name, description, steps_str, now)
        )
    return get_skill(name)


def get_skill(name: str) -> Optional[Dict[str, Any]]:
    """Retrieves a skill by name."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skills WHERE name = ?", (name,))
        row = cursor.fetchone()
        if not row:
            return None
        steps = row["steps"]
        if steps:
            try:
                steps = json.loads(steps)
            except Exception:
                pass
        return {
            "name": row["name"],
            "description": row["description"],
            "steps": steps,
            "created_at": row["created_at"]
        }


def list_skills() -> List[Dict[str, Any]]:
    """Lists all registered skills."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skills ORDER BY name ASC")
        rows = cursor.fetchall()
    skills = []
    for row in rows:
        steps = row["steps"]
        if steps:
            try:
                steps = json.loads(steps)
            except Exception:
                pass
        skills.append({
            "name": row["name"],
            "description": row["description"],
            "steps": steps,
            "created_at": row["created_at"]
        })
    return skills


# ═══════════════════════════════════════════════════════════════════════════
# Semantic Memory CRUD
# ═══════════════════════════════════════════════════════════════════════════

def save_semantic_memory(
    key: str,
    value: str,
    category: str = "general",
    source: str = "",
    confidence: float = 1.0,
    tags: list = None,
) -> None:
    """Upserts a semantic fact."""
    init_db()
    now = time.time()
    tags_str = json.dumps(tags or [])
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO semantic_memory (key, value, category, confidence, source, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                category = excluded.category,
                confidence = excluded.confidence,
                source = excluded.source,
                tags = excluded.tags,
                updated_at = excluded.updated_at
            """,
            (key, value, category, confidence, source, tags_str, now, now),
        )


def get_semantic_memory(key: str) -> Optional[Dict[str, Any]]:
    """Retrieves a semantic fact by key."""
    init_db()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM semantic_memory WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    return _row_to_semantic(row)


def search_semantic_memory(
    query: str, category: Optional[str] = None, limit: int = 10
) -> List[Dict[str, Any]]:
    """Searches semantic memory by keyword match on key and value."""
    init_db()
    like = f"%{query}%"
    with get_db() as conn:
        if category:
            rows = conn.execute(
                """SELECT * FROM semantic_memory
                   WHERE category = ? AND (key LIKE ? OR value LIKE ?)
                   ORDER BY updated_at DESC LIMIT ?""",
                (category, like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM semantic_memory
                   WHERE key LIKE ? OR value LIKE ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (like, like, limit),
            ).fetchall()
    return [_row_to_semantic(r) for r in rows]


def list_semantic_memory(category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Lists semantic memory entries optionally filtered by category."""
    init_db()
    with get_db() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM semantic_memory WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM semantic_memory ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_row_to_semantic(r) for r in rows]


def _row_to_semantic(row) -> Dict[str, Any]:
    tags = row["tags"]
    try:
        tags = json.loads(tags) if tags else []
    except Exception:
        tags = []
    return {
        "id": row["id"],
        "key": row["key"],
        "value": row["value"],
        "category": row["category"],
        "confidence": row["confidence"],
        "source": row["source"],
        "tags": tags,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Procedural Memory CRUD
# ═══════════════════════════════════════════════════════════════════════════

def save_procedural_memory(data: Dict[str, Any]) -> None:
    """Upserts a procedural skill/workflow."""
    init_db()
    now = time.time()
    name = data.get("name", "")
    if not name:
        return

    def _j(v, default="[]"):
        if isinstance(v, (list, dict)):
            return json.dumps(v)
        return v or default

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO procedural_memory
                (name, description, workflow, required_tools, preconditions,
                 known_failures, parameters, examples, version,
                 success_count, failure_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                workflow = excluded.workflow,
                required_tools = excluded.required_tools,
                preconditions = excluded.preconditions,
                known_failures = excluded.known_failures,
                parameters = excluded.parameters,
                examples = excluded.examples,
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            (
                name,
                data.get("description", ""),
                data.get("workflow", ""),
                _j(data.get("required_tools", []), "[]"),
                _j(data.get("preconditions", []), "[]"),
                _j(data.get("known_failures", []), "[]"),
                _j(data.get("parameters", {}), "{}"),
                _j(data.get("examples", []), "[]"),
                data.get("version", "1.0.0"),
                data.get("success_count", 0),
                data.get("failure_count", 0),
                now,
                now,
            ),
        )


def get_procedural_memory(name: str) -> Optional[Dict[str, Any]]:
    """Retrieves a procedural skill by name."""
    init_db()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM procedural_memory WHERE name = ?", (name,)
        ).fetchone()
    return _row_to_procedural(row) if row else None


def list_procedural_memory(limit: int = 50) -> List[Dict[str, Any]]:
    """Lists all procedural skills."""
    init_db()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM procedural_memory ORDER BY name ASC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_procedural(r) for r in rows]


def update_skill_stats(name: str, success: bool) -> None:
    """Increments success or failure count for a procedural skill."""
    init_db()
    field = "success_count" if success else "failure_count"
    with get_db() as conn:
        conn.execute(
            f"UPDATE procedural_memory SET {field} = {field} + 1, updated_at = ? WHERE name = ?",
            (time.time(), name),
        )


def _row_to_procedural(row) -> Dict[str, Any]:
    def _pj(v, default):
        try:
            return json.loads(v) if v else default
        except Exception:
            return default

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "workflow": row["workflow"],
        "required_tools": _pj(row["required_tools"], []),
        "preconditions": _pj(row["preconditions"], []),
        "known_failures": _pj(row["known_failures"], []),
        "parameters": _pj(row["parameters"], {}),
        "examples": _pj(row["examples"], []),
        "version": row["version"],
        "success_count": row["success_count"],
        "failure_count": row["failure_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Task State Persistence CRUD
# ═══════════════════════════════════════════════════════════════════════════

def save_task(data: Dict[str, Any]) -> None:
    """Upserts a task state record."""
    init_db()
    now = time.time()

    def _j(v, default="{}"):
        if isinstance(v, (list, dict)):
            return json.dumps(v)
        return v or default

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO tasks
                (task_id, goal, state, plan, steps_completed, steps_total,
                 error, verification_result, retry_count, metadata, history,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                goal = excluded.goal,
                state = excluded.state,
                plan = excluded.plan,
                steps_completed = excluded.steps_completed,
                steps_total = excluded.steps_total,
                error = excluded.error,
                verification_result = excluded.verification_result,
                retry_count = excluded.retry_count,
                metadata = excluded.metadata,
                history = excluded.history,
                updated_at = excluded.updated_at
            """,
            (
                data.get("task_id", ""),
                data.get("goal", ""),
                data.get("state", "pending"),
                _j(data.get("plan"), "{}"),
                data.get("steps_completed", 0),
                data.get("steps_total", 0),
                data.get("error"),
                data.get("verification_result"),
                data.get("retry_count", 0),
                _j(data.get("metadata", {}), "{}"),
                _j(data.get("history", []), "[]"),
                data.get("created_at", now),
                data.get("updated_at", now),
            ),
        )


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a task by ID."""
    init_db()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    return _row_to_task(row) if row else None


def list_tasks(limit: int = 50, state: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists tasks, optionally filtered by state."""
    init_db()
    with get_db() as conn:
        if state:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_row_to_task(r) for r in rows]


def _row_to_task(row) -> Dict[str, Any]:
    def _pj(v, default):
        try:
            return json.loads(v) if v else default
        except Exception:
            return default

    return {
        "task_id": row["task_id"],
        "goal": row["goal"],
        "state": row["state"],
        "plan": _pj(row["plan"], {}),
        "steps_completed": row["steps_completed"],
        "steps_total": row["steps_total"],
        "error": row["error"],
        "verification_result": row["verification_result"],
        "retry_count": row["retry_count"],
        "metadata": _pj(row["metadata"], {}),
        "history": _pj(row["history"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Execution Metrics CRUD
# ═══════════════════════════════════════════════════════════════════════════

def save_execution_metrics(data: Dict[str, Any]) -> None:
    """Saves execution metrics for a task."""
    init_db()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO execution_metrics
                (task_id, model, provider, input_tokens, output_tokens,
                 tool_calls, retries, duration_seconds, success,
                 verification_result, estimated_cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("task_id"),
                data.get("model", ""),
                data.get("provider", ""),
                data.get("input_tokens", 0),
                data.get("output_tokens", 0),
                data.get("tool_calls", 0),
                data.get("retries", 0),
                data.get("duration_seconds", 0.0),
                1 if data.get("success") else 0,
                data.get("verification_result"),
                data.get("estimated_cost"),
                time.time(),
            ),
        )


def get_metrics_summary(limit: int = 20) -> List[Dict[str, Any]]:
    """Returns recent execution metrics."""
    init_db()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM execution_metrics ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
