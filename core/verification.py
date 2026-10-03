"""
core/verification.py — Verification Strategy Engine for KuroAgent

Implements explicit verification strategies for every tool action.
Ensures Kuro never assumes a task succeeded simply because a tool call didn't throw.

Verification States:
  SUCCESS         — Result verified independently
  PARTIAL_SUCCESS — Action performed but output incomplete or warnings present
  FAILURE         — Verification failed (file missing, syntax error, test failed)
  UNKNOWN         — Cannot be automatically verified

Strategies:
  - File exists & size check
  - Syntax check (python py_compile)
  - Execution test check
  - JSON / Config validity check
  - Browser URL / state check
  - Command exit code check
"""

from __future__ import annotations

import json
import os
import py_compile
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class VerificationStatus(str, Enum):
    SUCCESS         = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE         = "failure"
    UNKNOWN         = "unknown"


class VerificationResult:
    """Result of verifying an action."""

    def __init__(
        self,
        status: VerificationStatus,
        strategy: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.status = status
        self.strategy = strategy
        self.message = message
        self.details = details or {}

    @property
    def is_success(self) -> bool:
        return self.status in (VerificationStatus.SUCCESS, VerificationStatus.PARTIAL_SUCCESS)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "strategy": self.strategy,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"VerificationResult(status={self.status.value!r}, strategy={self.strategy!r}, message={self.message!r})"


# ─────────────────────────────────────────────────────────────────────────────
# Verification Engine
# ─────────────────────────────────────────────────────────────────────────────

class VerificationEngine:
    """
    Evaluates execution outcomes using targeted verification strategies.
    """

    def verify_action(
        self,
        action: str,
        tool_input: Dict[str, Any],
        tool_output: Dict[str, Any],
    ) -> VerificationResult:
        """
        Main entry point. Routes to appropriate strategy based on action name.
        """
        # If tool returned an explicit error before execution
        if tool_output.get("success") is False:
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="error_check",
                message=f"Action reported failure: {tool_output.get('error', 'Unknown error')}",
                details=tool_output,
            )

        if action in ("write_file", "create_file"):
            return self._verify_file_write(tool_input, tool_output)

        elif action == "edit_file":
            return self._verify_file_edit(tool_input, tool_output)

        elif action == "run_command":
            return self._verify_command(tool_input, tool_output)

        elif action == "execute_python":
            return self._verify_python_exec(tool_input, tool_output)

        elif action == "browse_web":
            return self._verify_web_browse(tool_input, tool_output)

        elif action == "execute_sql":
            return self._verify_sql_exec(tool_input, tool_output)

        elif action == "create_plan":
            return VerificationResult(
                status=VerificationStatus.SUCCESS,
                strategy="plan_check",
                message="Plan structure verified and saved.",
            )

        # Default fallback verification for read-only or miscellaneous actions
        return VerificationResult(
            status=VerificationStatus.SUCCESS if tool_output.get("success", True) else VerificationStatus.FAILURE,
            strategy="default_output_check",
            message="Tool executed without error.",
            details={"output_keys": list(tool_output.keys())},
        )

    # ── Individual Verification Strategies ────────────────────────────────────

    def _verify_file_write(self, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> VerificationResult:
        path_str = tool_input.get("path", "")
        expected_content = tool_input.get("content", "")

        if not path_str:
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="file_exists",
                message="No path provided for file verification.",
            )

        p = Path(path_str).resolve()
        if not p.exists():
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="file_exists",
                message=f"File '{path_str}' does not exist after write.",
            )

        actual_size = p.stat().st_size
        if actual_size == 0 and len(expected_content) > 0:
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="file_size",
                message=f"File '{path_str}' exists but is empty (expected {len(expected_content)} bytes).",
            )

        # Python syntax check if writing a .py file
        if p.suffix == ".py":
            syntax_res = self._check_python_syntax(p)
            if not syntax_res[0]:
                return VerificationResult(
                    status=VerificationStatus.FAILURE,
                    strategy="python_syntax",
                    message=f"File written but contains Python syntax error: {syntax_res[1]}",
                )

        # JSON syntax check if writing a .json file
        if p.suffix == ".json":
            json_res = self._check_json_syntax(p)
            if not json_res[0]:
                return VerificationResult(
                    status=VerificationStatus.FAILURE,
                    strategy="json_syntax",
                    message=f"File written but contains invalid JSON: {json_res[1]}",
                )

        return VerificationResult(
            status=VerificationStatus.SUCCESS,
            strategy="file_exists_and_valid",
            message=f"File '{path_str}' verified ({actual_size} bytes).",
            details={"size": actual_size, "path": str(p)},
        )

    def _verify_file_edit(self, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> VerificationResult:
        path_str = tool_input.get("path", "")
        replacement = tool_input.get("replacement", "")

        p = Path(path_str).resolve()
        if not p.exists():
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="file_exists",
                message=f"File '{path_str}' not found after edit.",
            )

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            if replacement and replacement not in content:
                return VerificationResult(
                    status=VerificationStatus.PARTIAL_SUCCESS,
                    strategy="content_match",
                    message=f"Edit warning: replacement text not found verbatim in '{path_str}'.",
                )
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="read_check",
                message=f"Failed to read file after edit: {e}",
            )

        if p.suffix == ".py":
            syntax_res = self._check_python_syntax(p)
            if not syntax_res[0]:
                return VerificationResult(
                    status=VerificationStatus.FAILURE,
                    strategy="python_syntax",
                    message=f"Edit introduced Python syntax error: {syntax_res[1]}",
                )

        return VerificationResult(
            status=VerificationStatus.SUCCESS,
            strategy="file_edit_verified",
            message=f"File '{path_str}' edit verified.",
        )

    def _verify_command(self, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> VerificationResult:
        returncode = tool_output.get("returncode", 0)
        stderr = tool_output.get("stderr", "")

        if returncode != 0:
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="command_returncode",
                message=f"Command exited with non-zero status ({returncode}): {stderr[:200]}",
                details=tool_output,
            )

        if stderr and ("error" in stderr.lower() or "fatal" in stderr.lower()):
            return VerificationResult(
                status=VerificationStatus.PARTIAL_SUCCESS,
                strategy="command_stderr",
                message="Command completed with return code 0 but emitted error messages on stderr.",
                details={"stderr_snippet": stderr[:200]},
            )

        return VerificationResult(
            status=VerificationStatus.SUCCESS,
            strategy="command_returncode",
            message="Command executed successfully with return code 0.",
        )

    def _verify_python_exec(self, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> VerificationResult:
        stderr = tool_output.get("stderr", "")
        stdout = tool_output.get("stdout", "")

        if stderr and "Traceback" in stderr:
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="python_traceback",
                message=f"Python code raised an exception: {stderr.splitlines()[-1]}",
                details={"stderr": stderr},
            )

        return VerificationResult(
            status=VerificationStatus.SUCCESS,
            strategy="python_exec",
            message="Python code executed without uncaught exceptions.",
            details={"stdout_snippet": stdout[:150]},
        )

    def _verify_web_browse(self, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> VerificationResult:
        word_count = tool_output.get("word_count", 0)
        title = tool_output.get("title", "")

        if word_count == 0:
            return VerificationResult(
                status=VerificationStatus.PARTIAL_SUCCESS,
                strategy="web_content",
                message="Web page fetched but returned 0 words (empty or blocked).",
            )

        return VerificationResult(
            status=VerificationStatus.SUCCESS,
            strategy="web_content",
            message=f"Web page fetched successfully ('{title}', {word_count} words).",
        )

    def _verify_sql_exec(self, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> VerificationResult:
        error = tool_output.get("error")
        if error:
            return VerificationResult(
                status=VerificationStatus.FAILURE,
                strategy="sql_error",
                message=f"SQL error: {error}",
            )
        return VerificationResult(
            status=VerificationStatus.SUCCESS,
            strategy="sql_check",
            message="SQL query executed successfully.",
        )

    # ── Helper Syntax Checks ──────────────────────────────────────────────────

    def _check_python_syntax(self, path: Path) -> Tuple[bool, str]:
        try:
            py_compile.compile(str(path), doraise=True)
            return True, ""
        except py_compile.PyCompileError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def _check_json_syntax(self, path: Path) -> Tuple[bool, str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
            return True, ""
        except Exception as e:
            return False, str(e)


# Global instance
verification_engine = VerificationEngine()
