import subprocess
import os
import time
from typing import Dict, Any, Optional

def is_git_repo() -> bool:
    """Checks if the current working directory is inside a git repository."""
    try:
        res = subprocess.run(
            "git rev-parse --is-inside-work-tree",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        return res.returncode == 0 and "true" in res.stdout.lower()
    except Exception:
        return False

def create_checkpoint(message: str = "KURO Auto Checkpoint") -> Dict[str, Any]:
    """
    Creates a temporary git stash / commit checkpoint before executing automated edits.
    Allows instant rollback with /undo.
    """
    if not is_git_repo():
        # Not a git repo, skip quietly
        return {"success": False, "reason": "Not a git repository."}

    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        stash_msg = f"kuro_checkpoint_{int(time.time())}: {message} ({timestamp})"
        
        # Save working directory state to stash
        cmd = f'git stash push -u -m "{stash_msg}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        # Re-apply stash immediately so working tree is unaltered, but checkpoint is preserved
        apply_cmd = "git stash apply stash@{0}"
        subprocess.run(apply_cmd, shell=True, capture_output=True, text=True, timeout=10)

        return {
            "success": True,
            "stash_msg": stash_msg,
            "stdout": res.stdout.strip()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def rollback_checkpoint() -> Dict[str, Any]:
    """
    Reverts the last changes made by restoring the most recent git stash or discarding changes.
    """
    if not is_git_repo():
        return {"success": False, "error": "Current directory is not a git repository."}

    try:
        # Discard untracked and modified changes back to HEAD
        cmd_reset = "git checkout . && git clean -fd"
        res = subprocess.run(cmd_reset, shell=True, capture_output=True, text=True, timeout=15)
        
        return {
            "success": res.returncode == 0,
            "stdout": "Reverted working directory back to last clean state.",
            "stderr": res.stderr
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
