"""
core/paths.py — Centralized Path Manager for KuroAgent

Handles all path resolution for both Developer Mode (python main.py) and
Production Mode (Kuro.exe). Cleanly separates:
  - Application files (installed, mostly immutable)
  - User data (AppData\\Kuro, writable by plugins/skills/memory)

No absolute paths are hard-coded. All paths are derived from this module.
"""

import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    """Returns True if running as a PyInstaller-packaged executable."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _detect_dev_mode() -> bool:
    """Returns True if running in developer mode (from source, not frozen)."""
    return not _is_frozen() and os.getenv("KURO_DEV_MODE", "").lower() in ("", "1", "true", "yes")


# ─────────────────────────────────────────────────────────────────────────────
# Mode Detection
# ─────────────────────────────────────────────────────────────────────────────

IS_FROZEN: bool = _is_frozen()
IS_DEV: bool = _detect_dev_mode()


# ─────────────────────────────────────────────────────────────────────────────
# Application Directory (where the code lives)
# ─────────────────────────────────────────────────────────────────────────────

if IS_FROZEN:
    # PyInstaller: sys._MEIPASS is the temporary extracted path,
    # but the actual exe dir is what we want for the application root.
    APP_DIR: Path = Path(sys.executable).resolve().parent
else:
    # Developer mode: root is 2 levels up from this file (core/paths.py → root)
    APP_DIR: Path = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# User Data Directory (%APPDATA%\Kuro on Windows, ~/.kuro on others)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_user_data_dir() -> Path:
    """
    Resolves the user-writable data directory.
    - Production (frozen): %APPDATA%\\Kuro
    - Developer mode: <repo_root>  (so existing dev files work unchanged)
    - Override: KURO_DATA_DIR environment variable
    """
    override = os.getenv("KURO_DATA_DIR", "").strip()
    if override:
        return Path(override)

    if IS_DEV:
        # In dev mode, keep everything in the repo root for backward compat
        return APP_DIR

    # Production / installed mode
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "Kuro"
    else:
        return Path.home() / ".kuro"


USER_DATA_DIR: Path = _resolve_user_data_dir()

# ─────────────────────────────────────────────────────────────────────────────
# User-Writable Subdirectories
# ─────────────────────────────────────────────────────────────────────────────

BRAIN_DIR: Path    = USER_DATA_DIR / "brain"
MEMORY_DIR: Path   = USER_DATA_DIR / "memory"
SKILLS_DIR: Path   = USER_DATA_DIR / "skills"
PLUGINS_DIR: Path  = USER_DATA_DIR / "plugins"
CONFIG_DIR: Path   = USER_DATA_DIR / "config"
LOGS_DIR: Path     = USER_DATA_DIR / "logs"
CACHE_DIR: Path    = USER_DATA_DIR / "cache"
UPDATES_DIR: Path  = USER_DATA_DIR / "updates"
PROJECTS_DIR: Path = USER_DATA_DIR / "projects"
INTEGRATIONS_DIR: Path = USER_DATA_DIR / "integrations"
SCRATCH_DIR: Path  = USER_DATA_DIR / "scratch"
SANDBOX_DIR: Path  = USER_DATA_DIR / "sandbox"
NOTES_DIR: Path    = BRAIN_DIR / "notes"

# ─────────────────────────────────────────────────────────────────────────────
# Application-Level (mostly read-only) Paths
# ─────────────────────────────────────────────────────────────────────────────

CORE_DIR: Path     = APP_DIR / "core"
TOOLS_DIR: Path    = APP_DIR / "tools"
ASSETS_DIR: Path   = APP_DIR / "assets"
BUILD_DIR: Path    = APP_DIR / "build"

# ─────────────────────────────────────────────────────────────────────────────
# Key Files
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH: Path      = BRAIN_DIR / "kuro.db"
MEMORY_JSON: Path  = BRAIN_DIR / "memory.json"
ENV_FILE: Path     = APP_DIR / ".env"
HISTORY_FILE: Path = USER_DATA_DIR / ".kuro_history"
VAULT_FILE: Path   = CONFIG_DIR / "vault.enc"

# Config files
KURO_CONFIG: Path        = CONFIG_DIR / "kuro.json"
INTEGRATIONS_CONFIG: Path = CONFIG_DIR / "integrations.json"

# System prompts / personality (user-editable in data dir)
SYSTEM_PROMPT_FILE: Path = BRAIN_DIR / "kuro_prompt.txt"
PERSONALITY_FILE: Path   = BRAIN_DIR / "personality.md"


# ─────────────────────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────────────────────

_REQUIRED_DIRS = [
    BRAIN_DIR,
    MEMORY_DIR,
    SKILLS_DIR,
    PLUGINS_DIR,
    CONFIG_DIR,
    LOGS_DIR,
    CACHE_DIR,
    UPDATES_DIR,
    SCRATCH_DIR,
    SANDBOX_DIR,
    NOTES_DIR,
    INTEGRATIONS_DIR,
]


def ensure_dirs() -> None:
    """Creates all required user-data directories (idempotent, safe to call multiple times)."""
    for d in _REQUIRED_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # Best effort — log elsewhere if needed


def get_skill_dir(skill_name: str) -> Path:
    """Returns the directory for a specific skill."""
    return SKILLS_DIR / skill_name


def get_plugin_dir(plugin_name: str) -> Path:
    """Returns the directory for a specific plugin."""
    return PLUGINS_DIR / plugin_name


def get_integration_dir(integration_name: str) -> Path:
    """Returns the directory for a specific integration under AppData."""
    return INTEGRATIONS_DIR / integration_name


def get_project_dir(project_name: str) -> Path:
    """Returns the directory for a cached project profile."""
    return PROJECTS_DIR / project_name


def summary() -> dict:
    """Returns a human-readable summary of the current path configuration."""
    return {
        "mode": "developer" if IS_DEV else ("frozen/production" if IS_FROZEN else "production"),
        "app_dir": str(APP_DIR),
        "user_data_dir": str(USER_DATA_DIR),
        "brain_dir": str(BRAIN_DIR),
        "skills_dir": str(SKILLS_DIR),
        "plugins_dir": str(PLUGINS_DIR),
        "config_dir": str(CONFIG_DIR),
        "logs_dir": str(LOGS_DIR),
        "db_path": str(DB_PATH),
    }


# Auto-initialize on import
ensure_dirs()
