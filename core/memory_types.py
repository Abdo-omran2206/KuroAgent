"""
core/memory_types.py — Structured Memory Type Interfaces for KuroAgent

Extends the existing memory system with clearly typed memory categories:

  Episodic Memory   — What happened? (conversation history, events)
  Semantic Memory   — What does Kuro know? (facts, project info, user preferences)
  Procedural Memory — How to do something? (skills, workflows, patterns)
  Working Memory    — What is happening right now? (current task context)

All memory types build on top of the existing SQLite brain (memory_db.py).
The existing conversation history remains the primary episodic store.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EpisodicMemory:
    """A specific event or interaction that happened."""
    id: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
    user_text: str = ""
    assistant_text: str = ""
    summary: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_context_str(self) -> str:
        parts = []
        if self.summary:
            parts.append(f"[Summary] {self.summary}")
        if self.user_text:
            parts.append(f"User: {self.user_text}")
        if self.assistant_text:
            parts.append(f"KURO: {self.assistant_text[:300]}")
        return "\n".join(parts)


@dataclass
class SemanticMemory:
    """A fact, piece of knowledge, or learned information."""
    id: Optional[int] = None
    key: str = ""                   # Unique key/concept name
    value: str = ""                 # The knowledge/fact
    category: str = "general"      # e.g. 'project', 'user_preference', 'fact'
    confidence: float = 1.0        # 0.0 to 1.0
    source: str = ""               # Where this came from
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)

    def to_context_str(self) -> str:
        return f"[{self.category}] {self.key}: {self.value}"


@dataclass
class ProceduralMemory:
    """A skill, workflow, or procedural knowledge."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    workflow: str = ""             # Step-by-step procedure
    required_tools: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    known_failures: List[str] = field(default_factory=list)
    parameters: Dict[str, str] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    success_count: int = 0
    failure_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def to_context_str(self) -> str:
        return (
            f"[Skill: {self.name}] {self.description}\n"
            f"Workflow: {self.workflow[:200]}"
        )


@dataclass
class WorkingMemory:
    """
    Current task context — what is happening right now.

    This is ephemeral and is reset per task.
    """
    task_id: Optional[str] = None
    goal: str = ""
    current_step: str = ""
    completed_steps: List[str] = field(default_factory=list)
    pending_steps: List[str] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_result: Optional[str] = None
    context_notes: Dict[str, str] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_tool_result(self, action: str, result: Dict[str, Any]) -> None:
        self.tool_results.append({
            "action": action,
            "result": result,
            "timestamp": time.time(),
        })
        self.last_action = action
        # Summarize result for observations
        obs = f"Action '{action}' "
        if result.get("success") is False:
            obs += f"failed: {result.get('error', 'unknown error')}"
        else:
            obs += "succeeded"
        self.observations.append(obs)
        self.updated_at = time.time()

    def add_observation(self, text: str) -> None:
        self.observations.append(text)
        self.updated_at = time.time()

    def to_context_str(self) -> str:
        """Formats the current working memory as a compact context string for the LLM."""
        parts = [f"[Working Memory] Goal: {self.goal}"]
        if self.current_step:
            parts.append(f"Current Step: {self.current_step}")
        if self.completed_steps:
            completed = ", ".join(self.completed_steps[-5:])
            parts.append(f"Completed: {completed}")
        if self.pending_steps:
            pending = ", ".join(self.pending_steps[:5])
            parts.append(f"Pending: {pending}")
        if self.observations:
            recent_obs = self.observations[-3:]
            parts.append(f"Recent Observations: {'; '.join(recent_obs)}")
        if self.context_notes:
            for k, v in list(self.context_notes.items())[-5:]:
                parts.append(f"Note [{k}]: {v}")
        return "\n".join(parts)

    def reset(self) -> None:
        """Resets working memory for a new task."""
        self.goal = ""
        self.current_step = ""
        self.completed_steps = []
        self.pending_steps = []
        self.tool_results = []
        self.observations = []
        self.last_action = None
        self.last_result = None
        self.context_notes = {}
        self.task_id = None
        self.started_at = time.time()
        self.updated_at = time.time()


# ─────────────────────────────────────────────────────────────────────────────
# Memory Manager — unified interface
# ─────────────────────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Unified interface for all memory types.

    Acts as the bridge between the agent and the SQLite brain.
    """

    def __init__(self):
        self._working: WorkingMemory = WorkingMemory()

    # ── Working Memory ────────────────────────────────────────────────────────

    @property
    def working(self) -> WorkingMemory:
        return self._working

    def start_task(self, goal: str, task_id: Optional[str] = None) -> None:
        """Initializes working memory for a new task."""
        self._working.reset()
        self._working.goal = goal
        self._working.task_id = task_id

    def reset_working(self) -> None:
        """Resets working memory."""
        self._working.reset()

    # ── Semantic Memory ───────────────────────────────────────────────────────

    def save_fact(
        self,
        key: str,
        value: str,
        category: str = "general",
        source: str = "",
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Stores a semantic fact in the database."""
        try:
            from core import memory_db
            memory_db.save_semantic_memory(
                key=key,
                value=value,
                category=category,
                source=source,
                confidence=confidence,
                tags=tags or [],
            )
            return True
        except Exception:
            return False

    def get_fact(self, key: str) -> Optional[SemanticMemory]:
        """Retrieves a semantic fact by key."""
        try:
            from core import memory_db
            row = memory_db.get_semantic_memory(key)
            if row:
                return SemanticMemory(**row)
        except Exception:
            pass
        return None

    def search_facts(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[SemanticMemory]:
        """Searches semantic memories by keyword."""
        try:
            from core import memory_db
            rows = memory_db.search_semantic_memory(query, category=category, limit=limit)
            return [SemanticMemory(**r) for r in rows]
        except Exception:
            return []

    # ── Procedural Memory (Skills) ─────────────────────────────────────────

    def save_skill(self, skill: ProceduralMemory) -> bool:
        """Saves a procedural skill to the database."""
        try:
            from core import memory_db
            memory_db.save_procedural_memory(asdict(skill))
            return True
        except Exception:
            return False

    def get_skill(self, name: str) -> Optional[ProceduralMemory]:
        """Retrieves a skill by name."""
        try:
            from core import memory_db
            row = memory_db.get_procedural_memory(name)
            if row:
                return ProceduralMemory(**row)
        except Exception:
            pass
        return None

    def list_skills(self) -> List[ProceduralMemory]:
        """Lists all procedural skills."""
        try:
            from core import memory_db
            rows = memory_db.list_procedural_memory()
            return [ProceduralMemory(**r) for r in rows]
        except Exception:
            return []

    def record_skill_result(self, name: str, success: bool) -> None:
        """Updates the success/failure count for a skill."""
        try:
            from core import memory_db
            memory_db.update_skill_stats(name, success=success)
        except Exception:
            pass

    # ── Episodic Memory ───────────────────────────────────────────────────────

    def get_recent_episodes(self, limit: int = 5) -> List[EpisodicMemory]:
        """Returns recent conversation episodes."""
        try:
            from core import memory_db
            history = memory_db.get_chat_history(limit=limit)
            episodes = []
            for h in history:
                episodes.append(EpisodicMemory(
                    id=h.get("id"),
                    timestamp=h.get("timestamp", time.time()),
                    user_text=h.get("user_text", h.get("user", "")),
                    assistant_text=h.get("assistant_text", h.get("assistant", "")),
                    summary=h.get("summary"),
                    metadata=h.get("metadata") or {},
                ))
            return episodes
        except Exception:
            return []

    # ── Context Builder ───────────────────────────────────────────────────────

    def build_context(
        self,
        include_working: bool = True,
        include_episodic: bool = True,
        include_semantic_keys: Optional[List[str]] = None,
        episode_limit: int = 4,
    ) -> str:
        """
        Builds a compact context string for the LLM combining relevant memory types.
        Only includes what is relevant — not the entire history.
        """
        sections: List[str] = []

        # Working memory (current task state)
        if include_working and self._working.goal:
            sections.append(self._working.to_context_str())

        # Episodic memory (recent conversations)
        if include_episodic:
            episodes = self.get_recent_episodes(limit=episode_limit)
            if episodes:
                lines = ["[Recent Conversation]"]
                for ep in episodes[-episode_limit:]:
                    if ep.summary:
                        lines.append(f"  Summary: {ep.summary}")
                    elif ep.user_text:
                        lines.append(f"  User: {ep.user_text[:100]}")
                        lines.append(f"  KURO: {ep.assistant_text[:150]}")
                sections.append("\n".join(lines))

        # Semantic facts (explicit keys or project-level facts)
        if include_semantic_keys:
            facts = []
            for key in include_semantic_keys:
                fact = self.get_fact(key)
                if fact:
                    facts.append(fact.to_context_str())
            if facts:
                sections.append("[Known Facts]\n" + "\n".join(facts))

        return "\n\n".join(sections)


# ─────────────────────────────────────────────────────────────────────────────
# Global Instance
# ─────────────────────────────────────────────────────────────────────────────

memory_manager = MemoryManager()
