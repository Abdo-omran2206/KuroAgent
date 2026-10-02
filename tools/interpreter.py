import sys
import io
import traceback
from typing import Dict, Any

def execute_python_code(code: str) -> Dict[str, Any]:
    """
    Executes Python code dynamically and captures stdout/stderr output.
    Acts as an embedded Python interpreter system layer.
    """
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    sys.stdout = stdout_buffer
    sys.stderr = stderr_buffer

    execution_context = {}
    success = True
    error_msg = None

    try:
        # Execute the python code in custom execution context
        exec(code, execution_context)
    except Exception as e:
        success = False
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    captured_stdout = stdout_buffer.getvalue()
    captured_stderr = stderr_buffer.getvalue()

    return {
        "success": success,
        "stdout": captured_stdout,
        "stderr": captured_stderr if not error_msg else (captured_stderr + "\n" + error_msg),
        "return_value": execution_context.get("result", None)
    }
