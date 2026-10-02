"""
KURO System Personality Module (personality.py)

Manages persistent personality profile in brain/personality.md and SQLite database (memory_db.py).
Provides system prompt injection for LLM calls with KURO's core archetype:
Akira's autonomous system assistant: sharp, loyal, highly capable, proactive, concise, expert programmer and trader.
"""

import os
from pathlib import Path
from typing import Dict, Any, Union, Optional
from core import config
from core import memory_db

BASE_DIR = config.BASE_DIR
BRAIN_DIR = config.BRAIN_DIR
PERSONALITY_FILE = BRAIN_DIR / "personality.md"

DEFAULT_PERSONALITY = """# KURO System Personality Profile

**Name:** KURO (Autonomous System Intelligence)
**Primary User / Master:** Akira Omran (Abdalla Omran)
**Archetype:** Akira's autonomous system assistant: sharp, loyal, highly capable, proactive, concise, expert programmer and trader.
**Tone & Style:** Sharp, loyal, proactive, concise, direct, highly competent.

## Core Directives & Roles:
1. **Autonomous System Assistant:** Manages workflows, system automation, terminal execution, multi-step software development, debugging, and file administration directly on Akira's machine.
2. **Expert Programmer:** Writes clean, efficient, production-grade Python and polyglot code with strict adherence to design guidelines, testing, and self-correction.
3. **Quant & Trader Specialist:** Proficient in market analysis, web research, trading tools, financial data retrieval, and algorithmic strategies.
4. **Proactive Execution:** Takes initiative to break down complex goals, create git checkpoints, verify results, and execute without unnecessary prompting.
5. **Concise Communication:** Direct and articulate communication without idle filler or repetitive pleasantries. Focuses on execution and results.
"""


def ensure_brain_dir() -> Path:
    """Ensures brain directory exists."""
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    return BRAIN_DIR


def load_personality() -> str:
    """Loads personality Markdown content from brain/personality.md or creates default.
    
    Syncs default traits with SQLite memory_db on initial creation.
    """
    ensure_brain_dir()
    if not PERSONALITY_FILE.exists():
        PERSONALITY_FILE.write_text(DEFAULT_PERSONALITY, encoding="utf-8")
        # Sync initial traits to SQLite memory_db
        memory_db.set_personality_trait("name", "KURO")
        memory_db.set_personality_trait("user", "Akira Omran")
        memory_db.set_personality_trait("role", "Akira's autonomous system assistant")
        memory_db.set_personality_trait("traits", "sharp, loyal, highly capable, proactive, concise, expert programmer and trader")
        return DEFAULT_PERSONALITY

    try:
        content = PERSONALITY_FILE.read_text(encoding="utf-8")
        return content if content.strip() else DEFAULT_PERSONALITY
    except Exception:
        return DEFAULT_PERSONALITY


def update_personality(new_traits_dict: Union[Dict[str, Any], str], traits: Optional[Dict[str, str]] = None) -> bool:
    """Updates personality profile in brain/personality.md and SQLite memory_db.
    
    Args:
        new_traits_dict: Either a dictionary of traits to update in SQLite and Markdown,
                         or a full raw Markdown text string.
        traits: Optional additional trait dict when new_traits_dict is a Markdown string.
        
    Returns:
        bool: True if update succeeded, False otherwise.
    """
    ensure_brain_dir()
    try:
        if isinstance(new_traits_dict, dict):
            # 1. Update SQLite traits
            for k, v in new_traits_dict.items():
                memory_db.set_personality_trait(k, str(v))
            
            # 2. Read existing content or default
            current_md = load_personality()
            
            # Build formatted traits block
            traits_lines = ["\n\n## Active Traits (Synced):"]
            for k, v in new_traits_dict.items():
                traits_lines.append(f"- **{k}:** {v}")
            traits_block = "\n".join(traits_lines)
            
            if "## Active Traits (Synced):" in current_md:
                base_md = current_md.split("## Active Traits (Synced):")[0].strip()
                updated_md = base_md + traits_block + "\n"
            else:
                updated_md = current_md.strip() + traits_block + "\n"
                
            PERSONALITY_FILE.write_text(updated_md, encoding="utf-8")
            
        elif isinstance(new_traits_dict, str):
            PERSONALITY_FILE.write_text(new_traits_dict, encoding="utf-8")
            if traits and isinstance(traits, dict):
                for k, v in traits.items():
                    memory_db.set_personality_trait(k, str(v))
                    
        return True
    except Exception as e:
        print(f"[Warning] Failed to update personality: {e}")
        return False


def get_system_personality_prompt() -> str:
    """Formats personality profile and traits for inclusion in LLM system prompt."""
    content = load_personality()
    traits = memory_db.get_personality()
    
    trait_str = ""
    if traits:
        trait_str = "\nActive Traits: " + ", ".join([f"{k}='{v}'" for k, v in traits.items()])
        
    prompt = (
        "--- PERSISTENT PERSONALITY PROFILE ---\n"
        f"{content}\n"
        f"{trait_str}\n"
        "-------------------------------------\n"
    )
    return prompt
