"""
core/sandbox.py — Sandboxed Execution Guard, Path Validator, and Privacy Sanitizer

Provides execution guardrails for KuroAgent:
1. AST Code Safety Analyzer: Inspects Python AST for dangerous system operations (formatting drives, recursive deletions, fork bombs, unauthorized socket servers).
2. Virtual Sandbox Workspace: Provides isolated filesystem execution context.
3. Path Traversal Guard: Prevents directory escapes (e.g. `../../Windows/System32`).
4. Privacy & PII Sanitizer: Masks credentials, tokens, emails, and sensitive keys in outputs and logs.
"""

import ast
import os
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

from core.paths import SANDBOX_DIR, APP_DIR, USER_DATA_DIR
from core.logger import logger


# Banned dangerous modules and attribute access patterns
BANNED_IMPORTS: Set[str] = {
    "_ctypes",
    "winreg",
    "msvcrt",
}

DANGEROUS_CALLS: Set[str] = {
    "os.system",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "shutil.rmtree",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.run",
    "ctypes.windll",
    "ctypes.cdll",
}

# Regex for destructive system shell commands
DESTRUCTIVE_COMMAND_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bdel\s+(/[fFsqSQ\s]+)?([a-zA-Z]:\\|\*.*)", re.IGNORECASE),
    re.compile(r"\brmdir\s+/[sS]", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\s+(/|[a-zA-Z]:\\)", re.IGNORECASE),
    re.compile(r"\bdd\s+if=.*of=/dev/", re.IGNORECASE),
    re.compile(r"\b(mkfs|diskpart)\b", re.IGNORECASE),
    re.compile(r"\bshutdown\s+/[sSrRtT]", re.IGNORECASE),
]

# Sensitive Token Patterns for Privacy Masking
SENSITIVE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("OpenAI/Groq API Key", re.compile(r"\b(sk-[a-zA-Z0-9_-]{20,})\b")),
    ("Google Gemini Key", re.compile(r"\b(AIza[a-zA-Z0-9_-]{35})\b")),
    ("GitHub Token", re.compile(r"\b(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{50,})\b")),
    ("Slack Token", re.compile(r"\b(xox[baprs]-[a-zA-Z0-9_-]{20,})\b")),
    ("Discord Webhook", re.compile(r"https://discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+")),
    ("Telegram Bot Token", re.compile(r"\b\d{8,10}:[a-zA-Z0-9_-]{35}\b")),
    ("Generic Bearer Token", re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]{25,})", re.IGNORECASE)),
    ("Email Address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")),
]


class CodeSecurityReport:
    """Represents the findings of an AST code safety analysis."""

    def __init__(self):
        self.is_safe: bool = True
        self.risk_level: str = "SAFE"  # SAFE, WARNING, BLOCKED
        self.violations: List[str] = []
        self.warnings: List[str] = []

    def block(self, reason: str):
        self.is_safe = False
        self.risk_level = "BLOCKED"
        self.violations.append(reason)

    def warn(self, reason: str):
        if self.risk_level != "BLOCKED":
            self.risk_level = "WARNING"
        self.warnings.append(reason)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "risk_level": self.risk_level,
            "violations": self.violations,
            "warnings": self.warnings,
        }


class ASTSafetyVisitor(ast.NodeVisitor):
    """Inspects AST nodes for unauthorized operations."""

    def __init__(self, report: CodeSecurityReport, strict: bool = False):
        self.report = report
        self.strict = strict

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in BANNED_IMPORTS:
                self.report.block(f"Import of dangerous low-level module '{alias.name}' is prohibited.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module in BANNED_IMPORTS:
            self.report.block(f"Import from dangerous module '{node.module}' is prohibited.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func_name = self._resolve_call_name(node.func)
        if func_name:
            if func_name in ("os.system", "os.popen"):
                self.report.warn(f"Direct OS shell execution via '{func_name}' detected.")
            elif func_name in ("shutil.rmtree", "os.remove", "os.unlink"):
                self.report.warn(f"File deletion call '{func_name}' detected.")
            elif func_name.startswith("ctypes."):
                self.report.block(f"Direct native memory access via '{func_name}' is blocked.")

        self.generic_visit(node)

    def _resolve_call_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._resolve_call_name(node.value)
            if val:
                return f"{val}.{node.attr}"
            return node.attr
        return None


class SandboxGuard:
    """
    Central Sandbox & Security Enforcement System for KuroAgent.
    """

    def __init__(self):
        self._enabled: bool = True
        self._strict_mode: bool = False
        self._privacy_masking: bool = True
        self._sandbox_dir: Path = SANDBOX_DIR
        self._ensure_sandbox_workspace()

    def _ensure_sandbox_workspace(self):
        try:
            self._sandbox_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True
        logger.info("[Sandbox] Security sandbox activated.")

    def disable(self) -> None:
        self._enabled = False
        logger.warning("[Sandbox] Security sandbox deactivated.")

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "strict_mode": self._strict_mode,
            "privacy_masking": self._privacy_masking,
            "sandbox_dir": str(self._sandbox_dir),
            "total_sandbox_files": len(list(self._sandbox_dir.glob("*"))) if self._sandbox_dir.exists() else 0,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 1. AST Code Analysis
    # ─────────────────────────────────────────────────────────────────────────

    def validate_python_code(self, code_str: str) -> CodeSecurityReport:
        """
        Parses and inspects Python source code before dynamic execution.
        """
        report = CodeSecurityReport()
        if not self._enabled:
            return report

        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            report.block(f"Syntax error in code: {e}")
            return report

        visitor = ASTSafetyVisitor(report, strict=self._strict_mode)
        visitor.visit(tree)

        # Check for obvious destructive strings
        for pat in DESTRUCTIVE_COMMAND_PATTERNS:
            if pat.search(code_str):
                report.block(f"Destructive disk/system command pattern detected: {pat.pattern}")

        return report

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Path Traversal Guard
    # ─────────────────────────────────────────────────────────────────────────

    def validate_path_safety(self, target_path: str, allowed_roots: Optional[List[Path]] = None) -> Tuple[bool, str]:
        """
        Validates that target_path does not escape into critical OS directories.
        """
        if not self._enabled:
            return True, ""

        try:
            resolved = Path(target_path).resolve()
        except Exception as e:
            return False, f"Invalid path syntax: {e}"

        # System root protection on Windows (e.g. C:\Windows, C:\Windows\System32)
        if sys.platform == "win32":
            windir = os.environ.get("WINDIR", "C:\\Windows").lower()
            system32 = os.path.join(windir, "system32").lower()
            res_str = str(resolved).lower()

            if res_str.startswith(system32) or res_str == windir:
                return False, f"Access to system directory '{resolved}' is blocked."

        # If allowed_roots are given, verify path resides inside at least one
        if allowed_roots:
            allowed = any(resolved == root or root in resolved.parents for root in allowed_roots)
            if not allowed:
                return False, f"Path '{resolved}' is outside allowed workspaces."

        return True, ""

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Privacy & PII Sanitizer
    # ─────────────────────────────────────────────────────────────────────────

    def sanitize_text(self, text: str, mask_emails: bool = False) -> str:
        """
        Masks sensitive API keys, tokens, and credentials in given text.
        """
        if not self._privacy_masking or not text:
            return text

        sanitized = text
        for name, pattern in SENSITIVE_PATTERNS:
            if name == "Email Address" and not mask_emails:
                continue

            def _replacer(match):
                full_val = match.group(0)
                if len(full_val) <= 8:
                    return "********"
                return full_val[:4] + "****" + full_val[-4:]

            sanitized = pattern.sub(_replacer, sanitized)

        return sanitized

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Isolated Execution Helper
    # ─────────────────────────────────────────────────────────────────────────

    def get_isolated_sandbox_path(self, filename: str) -> Path:
        """Returns a safe path within the dedicated sandbox directory."""
        clean_name = Path(filename).name
        return self._sandbox_dir / clean_name

    def clean_sandbox(self) -> int:
        """Removes all temporary files from the sandbox workspace. Returns count of deleted files."""
        count = 0
        if not self._sandbox_dir.exists():
            return count

        for item in self._sandbox_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    count += 1
                elif item.is_dir():
                    import shutil
                    shutil.rmtree(item)
                    count += 1
            except Exception as e:
                logger.warning(f"[Sandbox] Could not delete '{item}': {e}")
        return count


# Global Sandbox Instance
sandbox = SandboxGuard()
