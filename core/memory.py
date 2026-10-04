import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from core import config


def _normalize_memory_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures memory dictionary has consistent user, assistant, user_text, and assistant_text keys."""
    user = item.get("user") or item.get("user_text") or ""
    assistant = item.get("assistant") or item.get("assistant_text") or ""
    timestamp = item.get("timestamp", time.time())
    metadata = item.get("metadata") or {}
    summary = item.get("summary")

    return {
        "timestamp": timestamp,
        "user": user,
        "assistant": assistant,
        "user_text": user,
        "assistant_text": assistant,
        "metadata": metadata,
        "summary": summary,
    }


def load_memory() -> List[Dict[str, Any]]:
    """Loads memory items from SQLite database or JSON file fallback with normalized keys."""
    try:
        from core import memory_db
        history = memory_db.get_chat_history(limit=config.MAX_MEMORY_ITEMS)
        if history:
            return [_normalize_memory_item(h) for h in history]
    except Exception:
        pass

    memory_path = config.MEMORY_FILE
    if not memory_path.exists():
        return []
    try:
        with open(memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [_normalize_memory_item(d) for d in data if isinstance(d, dict)]
            return []
    except Exception:
        return []


def save_memory(user_input: str, response: str, metadata: Dict[str, Any] = None) -> None:
    """Saves user interaction to both SQLite brain database and memory.json cache."""
    # Save to SQLite brain database
    try:
        from core import memory_db
        memory_db.save_chat_entry(user_input, response, metadata)
    except Exception:
        pass

    # Also update JSON cache
    memory = load_memory()
    entry = _normalize_memory_item({
        "timestamp": time.time(),
        "user": user_input,
        "assistant": response,
        "metadata": metadata or {}
    })
    memory.append(entry)

    # Trim memory to maximum items
    if len(memory) > config.MAX_MEMORY_ITEMS:
        memory = memory[-config.MAX_MEMORY_ITEMS:]

    try:
        with open(config.MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Auto-compress/summarize memory if items exceed threshold
    if len(memory) >= 10 and len(memory) % 5 == 0:
        summarize_memory_async()


def summarize_memory_async() -> None:
    """Triggers background summarization of conversation history to compress context."""
    import threading

    def _worker():
        try:
            from core.llm import ask_llm
            from core import memory_db
            history = load_memory()
            if not history:
                return
            formatted = "\n".join([f"User: {h['user']}\nKURO: {h['assistant']}" for h in history[-10:] if h.get("user")])
            if not formatted.strip():
                return
            prompt = (
                "Summarize the key decisions, user directives, technical facts, and ongoing task state "
                "from this conversation history into 3-5 concise bullet points:\n\n" + formatted
            )
            summary = ask_llm(prompt, system_prompt="You are a conversation summarizer. Be extremely factual and concise.")
            if summary and not summary.startswith("[Error"):
                memory_db.save_conversation_summary(summary)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def clear_memory() -> bool:
    """Clears stored memory in both JSON cache and SQLite."""
    try:
        if config.MEMORY_FILE.exists():
            with open(config.MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
        try:
            from core import memory_db
            with memory_db.get_db() as conn:
                conn.execute("DELETE FROM conversations")
        except Exception:
            pass
        return True
    except Exception:
        return False


def get_formatted_context(limit: int = 5) -> str:
    """Returns recent memory items + latest persistent conversation summary for LLM context."""
    memory = load_memory()
    summary = ""

    try:
        from core import memory_db
        summary = memory_db.get_latest_summary()
    except Exception:
        pass

    lines = []
    if summary:
        lines.append(f"--- Persistent Memory Summary ---\n{summary}\n")

    if memory:
        recent = memory[-limit:]
        lines.append("--- Recent Conversation Context ---")
        for item in recent:
            u = item.get("user") or item.get("user_text") or ""
            a = item.get("assistant") or item.get("assistant_text") or ""
            if u:
                lines.append(f"User: {u}")
            if a:
                lines.append(f"KURO: {a}")

    return "\n".join(lines)
