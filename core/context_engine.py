"""
core/context_engine.py — Context Retrieval Engine for KuroAgent

The context engine retrieves ONLY the information relevant to the current task,
rather than blindly sending the entire conversation history to the LLM.

It assembles context from:
  1. Current working memory (task state, current step)
  2. Relevant episodic memories (recent + task-related)
  3. Relevant semantic facts (project info, user preferences)
  4. Relevant skills/procedures (that might apply to this task)
  5. Tool results from the current step
  6. Conversation summary (compressed long-term memory)

The context is kept within a configurable token budget.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# Approximate token estimator (4 chars ≈ 1 token)
def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ─────────────────────────────────────────────────────────────────────────────
# Context Sections
# ─────────────────────────────────────────────────────────────────────────────

class ContextSection:
    """A named section of context with an associated priority and content."""

    def __init__(self, name: str, content: str, priority: int = 5, required: bool = False):
        """
        Args:
            name: Section identifier (for debugging/logging).
            content: The text content.
            priority: 1 (highest) to 10 (lowest). Sections are dropped from lowest priority first
                      when token budget is exceeded.
            required: If True, this section is never dropped even over budget.
        """
        self.name = name
        self.content = content.strip()
        self.priority = priority
        self.required = required

    @property
    def token_count(self) -> int:
        return _approx_tokens(self.content)

    def __repr__(self) -> str:
        return f"ContextSection(name={self.name!r}, tokens={self.token_count}, priority={self.priority})"


# ─────────────────────────────────────────────────────────────────────────────
# Context Engine
# ─────────────────────────────────────────────────────────────────────────────

class ContextEngine:
    """
    Assembles the optimal context for an LLM call given a task and token budget.

    Usage:
        engine = ContextEngine(max_tokens=3000)
        context_str = engine.build(task_goal="Deploy React app", user_input="Deploy my app")
    """

    DEFAULT_MAX_TOKENS = 3000  # Conservative default to leave room for LLM output

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.max_tokens = max_tokens

    def build(
        self,
        user_input: str,
        task_goal: Optional[str] = None,
        task_id: Optional[str] = None,
        include_skills: bool = True,
        include_project: bool = True,
        episode_limit: int = 4,
        extra_sections: Optional[List[ContextSection]] = None,
    ) -> str:
        """
        Builds an optimized context string for the LLM.

        Args:
            user_input: The current user message.
            task_goal: The current task goal (may differ from user_input after planning).
            task_id: Optional task ID for working memory lookup.
            include_skills: Whether to include relevant skills.
            include_project: Whether to include project profile.
            episode_limit: Max number of recent conversation episodes to include.
            extra_sections: Additional custom sections to include.

        Returns:
            A single context string optimized for the token budget.
        """
        sections: List[ContextSection] = []
        goal = task_goal or user_input

        # 1. Conversation summary (long-term memory, high priority)
        summary_text = self._get_conversation_summary()
        if summary_text:
            sections.append(ContextSection(
                name="conversation_summary",
                content=f"[Long-Term Memory Summary]\n{summary_text}",
                priority=2,
                required=False,
            ))

        # 2. Working memory (current task state — highest priority after system prompt)
        working_text = self._get_working_memory(task_id)
        if working_text:
            sections.append(ContextSection(
                name="working_memory",
                content=working_text,
                priority=1,
                required=True,
            ))

        # 3. Recent episodic memory (recent conversations)
        episodes_text = self._get_recent_episodes(limit=episode_limit)
        if episodes_text:
            sections.append(ContextSection(
                name="recent_episodes",
                content=f"[Recent Conversation History]\n{episodes_text}",
                priority=3,
                required=False,
            ))

        # 4. Relevant semantic facts (project info, user prefs)
        if include_project:
            facts_text = self._get_relevant_facts(goal)
            if facts_text:
                sections.append(ContextSection(
                    name="semantic_facts",
                    content=f"[Relevant Knowledge]\n{facts_text}",
                    priority=4,
                    required=False,
                ))

        # 5. Relevant skills
        if include_skills:
            skills_text = self._get_relevant_skills(goal)
            if skills_text:
                sections.append(ContextSection(
                    name="relevant_skills",
                    content=f"[Relevant Skills]\n{skills_text}",
                    priority=5,
                    required=False,
                ))

        # 6. Extra sections from caller
        if extra_sections:
            sections.extend(extra_sections)

        # Apply token budget — drop lowest priority sections first
        return self._assemble_within_budget(sections)

    def _assemble_within_budget(self, sections: List[ContextSection]) -> str:
        """Assembles sections within the token budget, dropping lowest priority first."""
        # Sort: required first, then by priority ascending (1 = highest priority)
        sorted_sections = sorted(sections, key=lambda s: (not s.required, s.priority))

        selected: List[ContextSection] = []
        total_tokens = 0

        for section in sorted_sections:
            if section.required:
                selected.append(section)
                total_tokens += section.token_count
            elif total_tokens + section.token_count <= self.max_tokens:
                selected.append(section)
                total_tokens += section.token_count
            # else: skip this section (over budget)

        # Re-sort by original semantic order (priority) for output
        selected.sort(key=lambda s: s.priority)
        return "\n\n".join(s.content for s in selected if s.content)

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _get_conversation_summary(self) -> str:
        try:
            from core import memory_db
            return memory_db.get_latest_summary() or ""
        except Exception:
            return ""

    def _get_working_memory(self, task_id: Optional[str] = None) -> str:
        try:
            from core.memory_types import memory_manager
            wm = memory_manager.working
            if wm.goal or (task_id and wm.task_id == task_id):
                return wm.to_context_str()
        except Exception:
            pass
        return ""

    def _get_recent_episodes(self, limit: int = 4) -> str:
        try:
            from core import memory_db
            history = memory_db.get_chat_history(limit=limit)
            if not history:
                return ""
            lines = []
            for h in history[-limit:]:
                user = h.get("user_text", h.get("user", ""))
                assistant = h.get("assistant_text", h.get("assistant", ""))
                if user:
                    lines.append(f"User: {user[:150]}")
                if assistant:
                    lines.append(f"KURO: {assistant[:250]}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _get_relevant_facts(self, goal: str) -> str:
        try:
            from core import memory_db
            # Search for facts related to the goal keywords
            keywords = _extract_keywords(goal)
            all_facts = []
            for kw in keywords[:5]:  # limit searches
                rows = memory_db.search_semantic_memory(kw, limit=3)
                all_facts.extend(rows)

            # Deduplicate by key
            seen_keys = set()
            unique_facts = []
            for f in all_facts:
                if f.get("key") not in seen_keys:
                    seen_keys.add(f.get("key"))
                    unique_facts.append(f)

            if not unique_facts:
                return ""
            return "\n".join(
                f"  [{f.get('category', 'fact')}] {f.get('key', '')}: {f.get('value', '')}"
                for f in unique_facts[:8]
            )
        except Exception:
            return ""

    def _get_relevant_skills(self, goal: str) -> str:
        try:
            from core import memory_db
            # Try to find skills relevant to the goal
            skills = memory_db.list_procedural_memory()
            if not skills:
                # Fallback to old skills format
                from tools.self_improve import list_learned_skills
                old_skills = list_learned_skills()
                if old_skills:
                    return "\n".join(
                        f"  - {s['name']}: {s['preview'][:100]}"
                        for s in old_skills[:5]
                    )
                return ""

            goal_lower = goal.lower()
            relevant = []
            for skill in skills:
                name = skill.get("name", "").lower()
                desc = skill.get("description", "").lower()
                if any(kw in name or kw in desc for kw in _extract_keywords(goal)):
                    relevant.append(skill)

            if not relevant:
                relevant = skills[:3]  # Fall back to listing recent skills

            return "\n".join(
                f"  - {s.get('name', '')}: {s.get('description', '')[:100]}"
                for s in relevant[:5]
            )
        except Exception:
            return ""


def _extract_keywords(text: str) -> List[str]:
    """Extracts meaningful keywords from a text for relevance matching."""
    # Remove common stop words and punctuation
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "must", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "my", "me", "i", "it",
        "that", "this", "and", "or", "but", "not", "no", "so", "if", "then",
        "please", "kuro", "help", "what", "how", "why", "when", "where", "get",
        "make", "create", "build", "run", "show", "list",
    }
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', text.lower())
    return [w for w in words if w not in stop_words][:10]


# ─────────────────────────────────────────────────────────────────────────────
# Global Instance
# ─────────────────────────────────────────────────────────────────────────────

context_engine = ContextEngine()
