"""
core/logger.py — Structured Logging for KuroAgent

Provides configurable structured logging with levels:
  QUIET  — Only errors and critical warnings
  NORMAL — Standard user-facing output
  DEBUG  — Detailed execution trace for developers
  TRACE  — Full verbose output including all LLM calls and tool I/O

Secrets are never exposed in logs.
Logs are written to %APPDATA%\\Kuro\\logs\\ in production.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Log Level Enum
# ─────────────────────────────────────────────────────────────────────────────

class LogLevel(IntEnum):
    QUIET  = 0
    NORMAL = 1
    DEBUG  = 2
    TRACE  = 3


_LEVEL_NAMES = {
    LogLevel.QUIET:  "QUIET",
    LogLevel.NORMAL: "NORMAL",
    LogLevel.DEBUG:  "DEBUG",
    LogLevel.TRACE:  "TRACE",
}

# Secret patterns — these values are redacted from all log output
_SECRET_PATTERNS = [
    re.compile(r'(sk-[a-zA-Z0-9\-_]{20,})', re.IGNORECASE),         # OpenAI keys
    re.compile(r'(AIza[0-9A-Za-z\-_]{35})', re.IGNORECASE),          # Google API keys
    re.compile(r'(gsk_[a-zA-Z0-9]{50,})', re.IGNORECASE),            # Groq keys
    re.compile(r'(["\']?(?:api_key|apikey|secret|token|password)["\']?\s*[:=]\s*["\']?([^"\'\\s,}{]{8,})["\']?)',
               re.IGNORECASE),
]


def _redact(text: str) -> str:
    """Redacts potential secrets from a log string."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# KuroLogger
# ─────────────────────────────────────────────────────────────────────────────

class KuroLogger:
    """
    Structured logger for KuroAgent.

    Supports console output (via Rich) and optional file logging.
    Automatically redacts secrets from all output.
    """

    def __init__(self, name: str = "kuro", level: LogLevel = LogLevel.NORMAL):
        self.name = name
        self.level = level
        self._file_handler: Optional[logging.FileHandler] = None
        self._python_logger = logging.getLogger(f"kuro.{name}")
        self._python_logger.setLevel(logging.DEBUG)
        self._console_available = True
        self._setup_file_logging()

    def _setup_file_logging(self) -> None:
        """Sets up file logging to the logs directory."""
        try:
            from core.paths import LOGS_DIR
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            log_file = LOGS_DIR / "kuro.log"
            handler = logging.FileHandler(str(log_file), encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            self._python_logger.addHandler(handler)
            self._file_handler = handler
        except Exception:
            pass  # File logging is optional

    def _console_print(self, msg: str, style: str = "") -> None:
        """Prints to console using Rich if available, otherwise plain print."""
        try:
            from rich.console import Console
            console = Console(highlight=False)
            if style:
                console.print(f"[{style}]{msg}[/{style}]")
            else:
                console.print(msg)
        except Exception:
            print(msg)

    def _format_msg(self, category: str, message: str, data: Optional[Dict] = None) -> str:
        parts = [f"[{category}] {_redact(message)}"]
        if data:
            try:
                data_str = json.dumps(data, default=str, ensure_ascii=False)
                parts.append(_redact(data_str))
            except Exception:
                pass
        return " | ".join(parts)

    # ── Logging methods ───────────────────────────────────────────────────────

    def error(self, message: str, data: Optional[Dict] = None) -> None:
        """Always logged regardless of level."""
        msg = self._format_msg("ERROR", message, data)
        self._python_logger.error(msg)
        self._console_print(msg, "bold red")

    def warning(self, message: str, data: Optional[Dict] = None) -> None:
        """Logged at NORMAL and above."""
        if self.level >= LogLevel.NORMAL:
            msg = self._format_msg("WARN", message, data)
            self._python_logger.warning(msg)
            self._console_print(msg, "yellow")

    def info(self, message: str, data: Optional[Dict] = None) -> None:
        """Logged at NORMAL and above."""
        if self.level >= LogLevel.NORMAL:
            msg = self._format_msg("INFO", message, data)
            self._python_logger.info(msg)
            # Info messages don't spam the console — only go to file

    def task(self, message: str, data: Optional[Dict] = None) -> None:
        """Task-lifecycle messages — always shown at NORMAL+."""
        if self.level >= LogLevel.NORMAL:
            msg = self._format_msg("TASK", message, data)
            self._python_logger.info(msg)
            self._console_print(f"[dim][TASK][/dim] {_redact(message)}", "")

    def action(self, action_name: str, context: str = "", data: Optional[Dict] = None) -> None:
        """Tool action events — shown at DEBUG+."""
        if self.level >= LogLevel.DEBUG:
            msg = self._format_msg(f"ACTION:{action_name}", context, data)
            self._python_logger.debug(msg)
            self._console_print(f"[dim cyan][ACTION:{action_name}][/dim cyan] {_redact(context)}", "")

    def result(self, action_name: str, success: bool, detail: str = "") -> None:
        """Tool result events — shown at DEBUG+."""
        if self.level >= LogLevel.DEBUG:
            status = "OK" if success else "FAIL"
            msg = self._format_msg(f"RESULT:{action_name}:{status}", detail)
            self._python_logger.debug(msg)
            color = "dim green" if success else "dim red"
            self._console_print(f"[{color}][{status}] {action_name}: {_redact(detail[:150])}[/{color}]", "")

    def llm_call(self, provider: str, model: str, prompt_preview: str = "") -> None:
        """LLM call events — shown at TRACE only."""
        if self.level >= LogLevel.TRACE:
            preview = prompt_preview[:100].replace("\n", " ")
            msg = self._format_msg(f"LLM:{provider}/{model}", preview)
            self._python_logger.debug(msg)
            self._console_print(f"[dim][LLM:{provider}/{model}] {_redact(preview)}...[/dim]", "")

    def verification(self, strategy: str, result: str, success: Optional[bool] = None) -> None:
        """Verification events — shown at DEBUG+."""
        if self.level >= LogLevel.DEBUG:
            status = "" if success is None else (" ✓" if success else " ✗")
            msg = self._format_msg(f"VERIFY:{strategy}", result + status)
            self._python_logger.debug(msg)

    def permission(self, action: str, risk: str, allowed: bool) -> None:
        """Permission gate events — shown at DEBUG+."""
        if self.level >= LogLevel.DEBUG:
            status = "ALLOWED" if allowed else "DENIED"
            msg = self._format_msg(f"PERM:{status}", f"{action} [{risk}]")
            self._python_logger.debug(msg)

    def debug(self, message: str, data: Optional[Dict] = None) -> None:
        """Debug messages — shown at DEBUG+."""
        if self.level >= LogLevel.DEBUG:
            msg = self._format_msg("DEBUG", message, data)
            self._python_logger.debug(msg)
            self._console_print(f"[dim][DEBUG] {_redact(message)}[/dim]", "")

    def trace(self, message: str, data: Optional[Dict] = None) -> None:
        """Trace messages — shown at TRACE only."""
        if self.level >= LogLevel.TRACE:
            msg = self._format_msg("TRACE", message, data)
            self._python_logger.debug(msg)
            self._console_print(f"[dim italic][TRACE] {_redact(message)}[/dim italic]", "")

    def set_level(self, level: LogLevel) -> None:
        """Changes the logging level at runtime."""
        self.level = level

    def set_level_from_string(self, level_str: str) -> None:
        """Sets level from a string name (quiet/normal/debug/trace)."""
        mapping = {
            "quiet": LogLevel.QUIET,
            "normal": LogLevel.NORMAL,
            "debug": LogLevel.DEBUG,
            "trace": LogLevel.TRACE,
        }
        lvl = mapping.get(level_str.lower())
        if lvl is not None:
            self.level = lvl

    @property
    def level_name(self) -> str:
        return _LEVEL_NAMES.get(self.level, "UNKNOWN")


# ─────────────────────────────────────────────────────────────────────────────
# Global Logger Instance
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_default_level() -> LogLevel:
    env = os.getenv("KURO_LOG_LEVEL", "normal").lower().strip()
    mapping = {"quiet": LogLevel.QUIET, "normal": LogLevel.NORMAL,
               "debug": LogLevel.DEBUG, "trace": LogLevel.TRACE}
    return mapping.get(env, LogLevel.NORMAL)


logger = KuroLogger(name="main", level=_resolve_default_level())


def get_logger(name: str = "kuro") -> KuroLogger:
    """Returns a named logger instance inheriting the global level."""
    child = KuroLogger(name=name, level=logger.level)
    return child
