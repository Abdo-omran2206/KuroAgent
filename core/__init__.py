import os

# Fix for rich._unicode_data version resolution
os.environ.setdefault("UNICODE_VERSION", "15.1.0")

from core.config import (
    BASE_DIR,
    BRAIN_DIR,
    MEMORY_FILE,
    SYSTEM_PROMPT_FILE,
    PERSONALITY_FILE,
    ENV_FILE,
    MAX_AUTONOMOUS_STEPS,
    SAFE_MODE,
    AUTO_GIT_CHECKPOINTS,
    MAX_MEMORY_ITEMS,
    KEY_POOLS,
    get_active_provider,
    get_active_model,
    save_api_key,
    get_pool_status_summary,
)

from core.llm import ask_llm
from core.agent import KuroAgent
from core import memory
from core import memory_db
from core import personality
