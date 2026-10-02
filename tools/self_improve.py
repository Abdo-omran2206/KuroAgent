import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List

SKILLS_DIR = Path("scratch/skills")

def ensure_skills_dir():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

def save_learned_skill(name: str, description: str, steps: str) -> Dict[str, Any]:
    """
    Saves a new learned skill/routine into scratch/skills/<name>.md so KURO can re-use it.
    """
    ensure_skills_dir()
    file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower().strip()) + ".md"
    target_path = SKILLS_DIR / file_name

    content = f"""# KURO Learned Skill: {name}
**Description:** {description}

## Workflow & Steps:
{steps}
"""
    try:
        target_path.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "skill_name": name,
            "path": str(target_path),
            "message": f"Skill '{name}' saved successfully to {target_path}"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to save skill: {str(e)}"}


def list_learned_skills() -> List[Dict[str, str]]:
    """
    Lists all self-learned skills stored in scratch/skills/
    """
    ensure_skills_dir()
    skills = []
    for f in SKILLS_DIR.glob("*.md"):
        try:
            txt = f.read_text(encoding="utf-8")
            skills.append({"name": f.stem, "path": str(f), "preview": txt[:200]})
        except Exception:
            pass
    return skills
