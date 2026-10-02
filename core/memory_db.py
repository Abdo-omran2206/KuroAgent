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

BASE_DIR = config.BASE_DIR
DB_DIR = config.BRAIN_DIR
DB_PATH = DB_DIR / "kuro.db"


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

        # Skills Table
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


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
