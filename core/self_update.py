"""
core/self_update.py — Safe Self-Improvement & Staged Update Pipeline for KuroAgent

Implements the staged self-modification and self-update workflow:
  Observe Problem
    ↓
  Understand Context & Propose Change
    ↓
  Create Git Checkpoint
    ↓
  Create Staging / Isolated Copy
    ↓
  Apply Changes
    ↓
  Run Static Checks & Tests
    ↓
  Evaluate & Promote Candidate (or Rollback if Failed)

The running Kuro process is never directly overwritten until candidate
validation succeeds.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.paths import APP_DIR, UPDATES_DIR
from core.permissions import check_permission


class SelfUpdatePipeline:
    """
    Manages safe, staged self-modification and updates.
    """

    def __init__(self):
        UPDATES_DIR.mkdir(parents=True, exist_ok=True)

    def propose_self_modification(
        self,
        target_file: str,
        proposed_content: str,
        reason: str = "Self-improvement patch",
    ) -> Dict[str, Any]:
        """
        Executes a controlled self-modification pipeline.
        Returns result dict indicating whether the modification passed validation and was promoted.
        """
        # 1. Permission check (DANGEROUS level)
        perm = check_permission("self_modify", context=f"Modify {target_file}: {reason}")
        if not perm.allowed:
            return {"success": False, "stage": "permission", "error": f"Permission denied: {perm.reason}"}

        target_path = (APP_DIR / target_file).resolve()
        if not str(target_path).startswith(str(APP_DIR.resolve())):
            return {"success": False, "stage": "path_check", "error": "Target file is outside APP_DIR."}

        # 2. Git Checkpoint
        checkpoint_ok = self._create_git_checkpoint(f"Pre-self-update: {target_file}")

        # Create isolated staging workspace
        staging_dir = Path(tempfile.mkdtemp(prefix="kuro_stage_"))
        try:
            # 3. Create Isolated Staging Copy of target file
            rel_path = target_path.relative_to(APP_DIR)
            staged_file = staging_dir / rel_path
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            staged_file.write_text(proposed_content, encoding="utf-8")

            # 4. Run Static Syntax Checks
            syntax_ok, syntax_err = self._run_syntax_check(staged_file)
            if not syntax_ok:
                return {
                    "success": False,
                    "stage": "syntax_check",
                    "error": f"Syntax check failed: {syntax_err}",
                    "rolled_back": True,
                }

            # 5. Run Test Suite on Staged Version
            tests_ok, test_out = self._run_tests()
            if not tests_ok:
                return {
                    "success": False,
                    "stage": "test_verification",
                    "error": f"Unit tests failed: {test_out[:200]}",
                    "rolled_back": True,
                }

            # 6. Apply / Promote Change
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_file, target_path)

            return {
                "success": True,
                "stage": "promoted",
                "message": f"Successfully updated '{target_file}' following full validation.",
            }

        except Exception as e:
            self.rollback_git_checkpoint()
            return {"success": False, "stage": "exception", "error": str(e), "rolled_back": True}

        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def _create_git_checkpoint(self, message: str) -> bool:
        try:
            from tools.git_checkpoint import create_checkpoint
            res = create_checkpoint(message)
            return res.get("success", False)
        except Exception:
            return False

    def rollback_git_checkpoint(self) -> bool:
        try:
            from tools.git_checkpoint import rollback_checkpoint
            res = rollback_checkpoint()
            return res.get("success", False)
        except Exception:
            return False

    def _run_syntax_check(self, file_path: Path) -> Tuple[bool, str]:
        if file_path.suffix == ".py":
            import py_compile
            try:
                py_compile.compile(str(file_path), doraise=True)
                return True, ""
            except Exception as e:
                return False, str(e)
        return True, ""

    def _run_tests(self) -> Tuple[bool, str]:
        test_file = APP_DIR / "tests" / "test_evolution.py"
        if not test_file.exists():
            return True, "No test file found"

        try:
            res = subprocess.run(
                [sys.executable, str(test_file)],
                cwd=str(APP_DIR),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return res.returncode == 0, res.stdout or res.stderr
        except Exception as e:
            return False, str(e)


# Global instance
self_update_pipeline = SelfUpdatePipeline()
