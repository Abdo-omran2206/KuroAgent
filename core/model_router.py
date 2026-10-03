"""
core/model_router.py — Model Router & Execution Metrics Engine for KuroAgent

Provides task-aware model routing and execution metrics tracking.

Task Types:
  FAST_SIMPLE      — Short queries, simple file listings, summaries -> fast/cheap model
  COMPLEX_REASONING— Multi-step planning, analysis, architecture -> reasoning model
  CODING           — Code generation, editing, refactoring -> coding-capable model
  VISION           — Multimodal image analysis -> vision model

Preserves multi-provider / multi-key failover fallback chain.
Tracks execution metrics (tokens, tool calls, duration, retries, cost).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core import config
from core.logger import logger


# ─────────────────────────────────────────────────────────────────────────────
# Task Type Enum
# ─────────────────────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    FAST_SIMPLE       = "fast_simple"
    COMPLEX_REASONING = "complex_reasoning"
    CODING            = "coding"
    VISION            = "vision"


# Default model preferences per task type (across supported providers)
_TASK_MODEL_PREFERENCES: Dict[TaskType, Dict[str, List[str]]] = {
    TaskType.FAST_SIMPLE: {
        "gemini": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-flash-latest"],
        "groq": ["llama-3.1-8b-instant", "gemma2-9b-it"],
        "openrouter": ["google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.1-8b-instruct:free"],
        "openai": ["gpt-4o-mini"],
    },
    TaskType.COMPLEX_REASONING: {
        "gemini": ["gemini-2.0-flash", "gemini-1.5-pro"],
        "groq": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
        "openrouter": ["meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-chat:free"],
        "openai": ["gpt-4o", "gpt-4o-mini"],
    },
    TaskType.CODING: {
        "gemini": ["gemini-2.0-flash", "gemini-1.5-flash"],
        "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        "openrouter": ["qwen/qwen-2.5-coder-32b-instruct:free", "meta-llama/llama-3.3-70b-instruct:free"],
        "openai": ["gpt-4o", "gpt-4o-mini"],
    },
    TaskType.VISION: {
        "gemini": ["gemini-2.0-flash", "gemini-1.5-flash"],
        "openai": ["gpt-4o", "gpt-4o-mini"],
        "openrouter": ["google/gemini-2.0-flash-exp:free"],
        "groq": ["llama-3.2-11b-vision-preview"],
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# Execution Metrics Data Model
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionMetrics:
    """Tracks token usage, execution time, retries, and costs for a task."""

    def __init__(self, task_id: Optional[str] = None):
        self.task_id = task_id
        self.provider: str = ""
        self.model: str = ""
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.tool_calls: int = 0
        self.retries: int = 0
        self.start_time: float = time.time()
        self.duration_seconds: float = 0.0
        self.success: bool = True
        self.verification_result: Optional[str] = None
        self.estimated_cost: float = 0.0

    def record_tool_call(self) -> None:
        self.tool_calls += 1

    def record_retry(self) -> None:
        self.retries += 1

    def finish(self, success: bool = True, verification_msg: Optional[str] = None) -> None:
        self.duration_seconds = round(time.time() - self.start_time, 2)
        self.success = success
        self.verification_result = verification_msg
        self._persist()

    def _persist(self) -> None:
        try:
            from core import memory_db
            memory_db.save_execution_metrics({
                "task_id": self.task_id,
                "model": self.model,
                "provider": self.provider,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "tool_calls": self.tool_calls,
                "retries": self.retries,
                "duration_seconds": self.duration_seconds,
                "success": self.success,
                "verification_result": self.verification_result,
                "estimated_cost": self.estimated_cost,
            })
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Model Router
# ─────────────────────────────────────────────────────────────────────────────

class ModelRouter:
    """
    Intelligent Model Router that selects the best provider & model
    for a given task while preserving multi-key fallback pools.
    """

    def classify_task(self, prompt: str, has_image: bool = False) -> TaskType:
        """Classifies task intent into a TaskType."""
        if has_image:
            return TaskType.VISION

        p_lower = prompt.lower()

        # Coding keywords
        code_kw = ["write code", "fix bug", "function", "class", "def ", "import ", "refactor", "implement", "create file", "script", "py", "js", "html", "css"]
        if any(kw in p_lower for kw in code_kw):
            return TaskType.CODING

        # Complex reasoning keywords
        reasoning_kw = ["plan", "architecture", "analyze", "design", "explain why", "strategy", "compare", "evaluate", "review", "step by step"]
        if any(kw in p_lower for kw in reasoning_kw):
            return TaskType.COMPLEX_REASONING

        # Default to fast simple
        return TaskType.FAST_SIMPLE

    def select_route(
        self,
        prompt: str,
        preferred_provider: Optional[str] = None,
        preferred_model: Optional[str] = None,
        has_image: bool = False,
    ) -> Tuple[str, str, TaskType]:
        """
        Determines the optimal (provider, model, task_type) route.
        """
        task_type = self.classify_task(prompt, has_image=has_image)

        provider = preferred_provider or config.get_active_provider()
        model = preferred_model

        if not model:
            # Check task preferences for this provider
            provider_prefs = _TASK_MODEL_PREFERENCES.get(task_type, {}).get(provider, [])
            if provider_prefs:
                model = provider_prefs[0]
            else:
                model = config.get_active_model(provider)

        logger.debug(f"Routed task [{task_type.value}] -> Provider: {provider}, Model: {model}")
        return provider, model, task_type


# Global instances
model_router = ModelRouter()
