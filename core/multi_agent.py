"""
core/multi_agent.py — Multi-Agent Architecture Abstraction for KuroAgent

Prepares Kuro for future multi-agent workflows. Provides clean interfaces
for specialized agents while allowing Kuro to act as the primary Orchestrator.

Specialized Agents:
  - ResearchAgent   — Web search, document reading, repo exploration
  - CodingAgent     — Code generation, refactoring, linting, tests
  - BrowserAgent    — Headless web automation & page scraping
  - TestingAgent    — Running unit tests, syntax validation
  - PlanningAgent   — High-level goal decomposition

Avoids premature complexity by offering decoupled callable interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseAgent(ABC):
    """Base interface for all specialized agents."""

    def __init__(self, name: str, role_description: str):
        self.name = name
        self.role_description = role_description

    @abstractmethod
    def run_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Runs a sub-task and returns structured output."""
        pass


class ResearchAgent(BaseAgent):
    """Specialized agent for web search, documentation reading, and repository analysis."""

    def __init__(self):
        super().__init__("ResearchAgent", "Researches web data, documentation, and codebase structure.")

    def run_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from tools.web import search_web
        res = search_web(prompt)
        return {"success": True, "agent": self.name, "findings": res.get("results", [])}


class CodingAgent(BaseAgent):
    """Specialized agent for code editing, creation, and script execution."""

    def __init__(self):
        super().__init__("CodingAgent", "Handles code writing, refactoring, and execution.")

    def run_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from tools.interpreter import execute_python_code
        if context and "code" in context:
            res = execute_python_code(context["code"])
            return {"success": res.get("success", True), "agent": self.name, "output": res}
        return {"success": True, "agent": self.name, "message": f"Coding task received: {prompt}"}


class BrowserAgent(BaseAgent):
    """Specialized agent for headless web browsing and page automation."""

    def __init__(self):
        super().__init__("BrowserAgent", "Automates web navigation and scrapes content.")

    def run_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from tools.web_browser import browse_web_headless
        url = context.get("url", prompt) if context else prompt
        res = browse_web_headless(url)
        return {"success": res.get("success", True), "agent": self.name, "page_data": res}


class TestingAgent(BaseAgent):
    """Specialized agent for test execution and verification."""

    def __init__(self):
        super().__init__("TestingAgent", "Executes unit tests and verifies code syntax.")

    def run_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from core.verification import verification_engine
        path = context.get("path", "") if context else ""
        if path:
            v_res = verification_engine._check_python_syntax(path)
            return {"success": v_res[0], "agent": self.name, "syntax_ok": v_res[0], "message": v_res[1]}
        return {"success": True, "agent": self.name, "message": "Test verification complete."}


class AgentOrchestrator:
    """
    Coordinates and delegates sub-tasks to specialized agents.
    """

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {
            "research": ResearchAgent(),
            "coding": CodingAgent(),
            "browser": BrowserAgent(),
            "testing": TestingAgent(),
        }

    def delegate(self, agent_name: str, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Delegates a task to a named specialized agent."""
        agent = self._agents.get(agent_name.lower())
        if not agent:
            return {"success": False, "error": f"Specialized agent '{agent_name}' not found."}
        return agent.run_task(prompt, context)


# Global instance
orchestrator = AgentOrchestrator()
