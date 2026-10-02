import subprocess
import os
import platform
from typing import Dict, Any

RISKY_COMMAND_PATTERNS = [
    "rm -rf", "del /f", "del /s", "rd /s", "format ", "dd if=",
    "shutdown", "reboot", "mkfs", "drop database", "icacls",
    "chmod -r 777", "chown -r", "reg delete", "diskpart"
]

def is_risky_command(cmd: str) -> bool:
    """Checks if a command contains potentially destructive patterns."""
    cmd_lower = cmd.lower().strip()
    return any(pattern in cmd_lower for pattern in RISKY_COMMAND_PATTERNS)

def run_command(cmd: str, cwd: str = None, confirm_if_risky: bool = True) -> Dict[str, Any]:
    """
    Executes a system shell command safely using subprocess.
    Captures stdout, stderr, and return code.
    """
    if is_risky_command(cmd) and confirm_if_risky:
        # Warning payload if risky
        return {
            "success": False,
            "stdout": "",
            "stderr": f"SECURITY NOTICE: Command '{cmd}' flagged as potentially destructive.",
            "returncode": -1,
            "requires_confirmation": True
        }

    try:
        working_dir = cwd or os.getcwd()
        # Execute using default shell
        process = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=120
        )
        return {
            "success": process.returncode == 0,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "returncode": process.returncode,
            "requires_confirmation": False
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command execution timed out after 120 seconds.",
            "returncode": -1,
            "requires_confirmation": False
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to execute command: {str(e)}",
            "returncode": -1,
            "requires_confirmation": False
        }

def get_system_info() -> Dict[str, str]:
    """Returns basic system environment information."""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "python_version": platform.python_version(),
        "cwd": os.getcwd(),
        "user": os.getlogin() if hasattr(os, "getlogin") else os.getenv("USERNAME", os.getenv("USER", "user"))
    }
