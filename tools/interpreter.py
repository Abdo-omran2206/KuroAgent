"""
tools/interpreter.py — Sandboxed Python Interpreter for KuroAgent

Executes Python code dynamically with AST safety analysis, output capture,
and privacy sanitization.
"""

import sys
import io
import traceback
from typing import Dict, Any, Optional

from core.sandbox import sandbox
from core.logger import logger


def execute_python_code(code: str, custom_globals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Executes Python code dynamically and captures stdout/stderr output.
    Pre-validates AST for destructive or unauthorized commands via SandboxGuard.
    """
    # 1. AST Safety Pre-Check
    report = sandbox.validate_python_code(code)
    if not report.is_safe:
        logger.warning(f"[Interpreter] Blocked unsafe execution attempt: {report.violations}")
        return {
            "success": False,
            "stdout": "",
            "stderr": "🔒 [SANDBOX GUARD BLOCKED]: Execution rejected due to security policy:\n- " + "\n- ".join(report.violations),
            "return_value": None,
            "security_report": report.to_dict(),
        }

    # 2. Setup Buffers & Context
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    sys.stdout = stdout_buffer
    sys.stderr = stderr_buffer

    execution_context = custom_globals if custom_globals is not None else {}
    success = True
    error_msg = None

    try:
        # Execute the python code in execution context
        exec(code, execution_context)
    except Exception as e:
        success = False
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    captured_stdout = stdout_buffer.getvalue()
    raw_stderr = captured_stderr = stderr_buffer.getvalue()
    if error_msg:
        captured_stderr = (raw_stderr + "\n" + error_msg) if raw_stderr else error_msg

    # 3. Privacy Sanitization
    safe_stdout = sandbox.sanitize_text(captured_stdout)
    safe_stderr = sandbox.sanitize_text(captured_stderr)

    return {
        "success": success,
        "stdout": safe_stdout,
        "stderr": safe_stderr,
        "return_value": execution_context.get("result", None),
        "security_warnings": report.warnings,
    }
