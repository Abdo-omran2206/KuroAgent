import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# Load dotenv if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Base & Brain directories
BASE_DIR = Path(__file__).resolve().parent.parent
BRAIN_DIR = BASE_DIR / "brain"
BRAIN_DIR.mkdir(parents=True, exist_ok=True)

# Config & Storage Locations
MEMORY_FILE = BRAIN_DIR / "memory.json"
SYSTEM_PROMPT_FILE = BRAIN_DIR / "kuro_prompt.txt"
PERSONALITY_FILE = BRAIN_DIR / "personality.md"
ENV_FILE = BASE_DIR / ".env"

# Autonomous Agent Settings
MAX_AUTONOMOUS_STEPS = int(os.getenv("KURO_MAX_STEPS", "10"))
SAFE_MODE = os.getenv("KURO_SAFE_MODE", "true").lower() in ("true", "1", "yes")
AUTO_GIT_CHECKPOINTS = os.getenv("KURO_GIT_CHECKPOINTS", "true").lower() in ("true", "1", "yes")
MAX_MEMORY_ITEMS = int(os.getenv("KURO_MAX_MEMORY", "25"))

# Provider Priority Chain (in order of preference)
PROVIDER_CHAIN = ["gemini", "groq", "openrouter", "openai"]

# Model Chains per Provider (fallback sequence)
MODEL_CHAINS = {
    "gemini": [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest"
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it"
    ],
    "openrouter": [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "deepseek/deepseek-chat:free",
        "qwen/qwen-2.5-coder-32b-instruct:free"
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o"
    ],
    "ollama": [
        "llama3",
        "qwen2.5-coder",
        "mistral",
        "deepseek-coder"
    ]
}

# Base URLs
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def _is_valid_key(key: str) -> bool:
    """Returns True if the API key is not a dummy placeholder string."""
    if not key or not isinstance(key, str):
        return False
    k = key.strip().lower()
    if k.startswith("your_") or "your_" in k or k == "none" or "placeholder" in k:
        return False
    return True


def _parse_keys_from_env(key_name: str, single_name: str = None) -> List[str]:
    """Parses a list of API keys from comma-separated string or multiple env vars, ignoring dummy placeholders."""
    keys = []
    val = os.getenv(key_name, "")
    if val:
        for k in val.split(","):
            k_clean = k.strip()
            if _is_valid_key(k_clean) and k_clean not in keys:
                keys.append(k_clean)
    if single_name:
        s_val = os.getenv(single_name, "").strip()
        if _is_valid_key(s_val) and s_val not in keys:
            keys.append(s_val)
    return keys


class KeyPool:
    """
    Intelligent Multi-Key Pool with Rate-Limit & Failure Cooldown Tracking.
    """
    def __init__(self, provider: str, keys: List[str]):
        self.provider = provider
        self.keys = keys
        self.cooldowns: Dict[str, float] = {}
        self.current_idx = 0

    def add_key(self, key: str):
        if key not in self.keys:
            self.keys.append(key)

    def get_available_key(self) -> Optional[str]:
        now = time.time()
        for k in list(self.cooldowns.keys()):
            if now >= self.cooldowns[k]:
                del self.cooldowns[k]

        available = [k for k in self.keys if k not in self.cooldowns]
        if not available:
            if self.cooldowns:
                earliest_key = min(self.cooldowns, key=self.cooldowns.get)
                return earliest_key
            return None

        self.current_idx = (self.current_idx + 1) % len(available)
        return available[self.current_idx]

    def mark_rate_limited(self, key: str, cooldown_seconds: float = 60.0):
        self.cooldowns[key] = time.time() + cooldown_seconds

    def mark_invalid(self, key: str):
        self.cooldowns[key] = time.time() + 86400


# Initialize Key Pools
KEY_POOLS: Dict[str, KeyPool] = {
    "gemini": KeyPool("gemini", _parse_keys_from_env("GEMINI_API_KEYS", "GEMINI_API_KEY")),
    "groq": KeyPool("groq", _parse_keys_from_env("GROQ_API_KEYS", "GROQ_API_KEY")),
    "openrouter": KeyPool("openrouter", _parse_keys_from_env("OPENROUTER_API_KEYS", "OPENROUTER_API_KEY")),
    "openai": KeyPool("openai", _parse_keys_from_env("OPENAI_API_KEYS", "OPENAI_API_KEY")),
}


def get_available_providers() -> List[str]:
    """Returns list of providers that currently have available keys/endpoints."""
    available = []
    for p in PROVIDER_CHAIN:
        pool = KEY_POOLS.get(p)
        if pool and (pool.keys or p == "ollama"):
            available.append(p)
    return available


def get_active_provider() -> str:
    """Returns the primary active provider or the first available in priority chain."""
    preferred = os.getenv("KURO_PROVIDER", "gemini").lower()
    if preferred in KEY_POOLS and KEY_POOLS[preferred].get_available_key():
        return preferred
    available = get_available_providers()
    return available[0] if available else "gemini"


def get_active_model(provider: str = None) -> str:
    """Returns the default primary model for a provider."""
    p = provider or get_active_provider()
    env_model = os.getenv(f"{p.upper()}_MODEL")
    if env_model:
        return env_model
    chains = MODEL_CHAINS.get(p, ["gemini-3.6-flash"])
    return chains[0] if chains else "gemini-3.6-flash"


def save_api_key(key: str, provider: str = "gemini") -> bool:
    """Saves API key to KeyPool and persists to .env file."""
    p = provider.lower()
    if p not in KEY_POOLS:
        KEY_POOLS[p] = KeyPool(p, [])
    
    KEY_POOLS[p].add_key(key)

    env_vars = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    single_key_name = f"{p.upper()}_API_KEY"
    plural_key_name = f"{p.upper()}_API_KEYS"

    # Append to existing keys if present
    existing = env_vars.get(plural_key_name, env_vars.get(single_key_name, ""))
    keys_list = [k.strip() for k in existing.split(",") if k.strip()]
    if key not in keys_list:
        keys_list.append(key)

    env_vars[single_key_name] = keys_list[0]
    if len(keys_list) > 1:
        env_vars[plural_key_name] = ",".join(keys_list)

    try:
        lines = [f"{k}={v}" for k, v in env_vars.items()]
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def get_pool_status_summary() -> List[Dict[str, Any]]:
    """Returns human-readable summary of all key pools for UI display."""
    summary = []
    now = time.time()
    for name, pool in KEY_POOLS.items():
        total = len(pool.keys)
        cooling = sum(1 for k in pool.keys if k in pool.cooldowns and pool.cooldowns[k] > now)
        active = total - cooling
        summary.append({
            "provider": name.upper(),
            "total_keys": total,
            "active_keys": active,
            "cooling_keys": cooling,
            "models": MODEL_CHAINS.get(name, [])
        })
    return summary
