"""
core/skill_system.py — Reusable Skill System for KuroAgent

Manages structured, reusable procedural skills with full metadata:
  - Name, Description, Purpose
  - Required tools, Preconditions, Workflow
  - Parameters, Examples, Known failure cases
  - Version, Success/failure history

Discovers skills from both %APPDATA%\\Kuro\\skills\\ (directory-based)
and SQLite procedural_memory table.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.memory_types import ProceduralMemory, memory_manager
from core.paths import SKILLS_DIR


@dataclass
class SkillSpec:
    """Full specification of a reusable Kuro skill."""
    name: str
    description: str
    purpose: str = ""
    required_tools: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    workflow: List[str] = field(default_factory=list)  # Step-by-step actions/prompts
    parameters: Dict[str, str] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    known_failures: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    success_count: int = 0
    failure_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return (self.success_count / total) if total > 0 else 0.0

    def to_procedural_memory(self) -> ProceduralMemory:
        return ProceduralMemory(
            name=self.name,
            description=self.description,
            workflow="\n".join(self.workflow) if isinstance(self.workflow, list) else str(self.workflow),
            required_tools=self.required_tools,
            preconditions=self.preconditions,
            known_failures=self.known_failures,
            parameters=self.parameters,
            examples=self.examples,
            version=self.version,
            success_count=self.success_count,
            failure_count=self.failure_count,
        )

    def save_to_file(self, base_dir: Optional[Path] = None) -> Path:
        """Saves skill as a structured JSON file under APPDATA skills directory."""
        target_dir = (base_dir or SKILLS_DIR) / self.name
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / "skill.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

        # Also write readable markdown summary
        md_path = target_dir / "README.md"
        md_content = (
            f"# Skill: {self.name} (v{self.version})\n\n"
            f"**Description:** {self.description}\n\n"
            f"**Purpose:** {self.purpose}\n\n"
            f"### Required Tools\n" + "\n".join(f"- `{t}`" for t in self.required_tools) + "\n\n"
            f"### Preconditions\n" + "\n".join(f"- {p}" for p in self.preconditions) + "\n\n"
            f"### Workflow\n" + "\n".join(f"{i+1}. {step}" for i, step in enumerate(self.workflow)) + "\n\n"
            f"**Success Rate:** {self.success_rate:.1%} ({self.success_count} passed / {self.failure_count} failed)\n"
        )
        md_path.write_text(md_content, encoding="utf-8")
        return file_path


class SkillSystem:
    """
    Skill discovery, relevance matching, execution tracking, and creation.
    """

    def __init__(self):
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    def discover_skills(self) -> List[SkillSpec]:
        """Discovers all skills from APPDATA skill files and SQLite database."""
        skills_map: Dict[str, SkillSpec] = {}

        # 1. Load from file system (%APPDATA%\Kuro\skills\<skill>\skill.json)
        if SKILLS_DIR.exists():
            for folder in SKILLS_DIR.iterdir():
                if folder.is_dir():
                    json_file = folder / "skill.json"
                    if json_file.exists():
                        try:
                            with open(json_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            spec = SkillSpec(**data)
                            skills_map[spec.name] = spec
                        except Exception:
                            pass

        # 2. Load from SQLite procedural memory
        try:
            db_skills = memory_manager.list_skills()
            for pm in db_skills:
                if pm.name not in skills_map:
                    workflow_list = pm.workflow.splitlines() if isinstance(pm.workflow, str) else pm.workflow
                    skills_map[pm.name] = SkillSpec(
                        name=pm.name,
                        description=pm.description,
                        workflow=workflow_list,
                        required_tools=pm.required_tools,
                        preconditions=pm.preconditions,
                        known_failures=pm.known_failures,
                        parameters=pm.parameters,
                        examples=pm.examples,
                        version=pm.version,
                        success_count=pm.success_count,
                        failure_count=pm.failure_count,
                    )
        except Exception:
            pass

        return list(skills_map.values())

    def find_relevant_skills(self, goal: str, limit: int = 3) -> List[SkillSpec]:
        """Finds skills matching keywords in the task goal."""
        all_skills = self.discover_skills()
        if not all_skills:
            return []

        goal_lower = goal.lower()
        scored: List[tuple[float, SkillSpec]] = []

        for skill in all_skills:
            score = 0.0
            if skill.name.lower() in goal_lower:
                score += 3.0
            for word in skill.name.lower().replace("_", " ").split():
                if len(word) > 2 and word in goal_lower:
                    score += 1.0
            for word in skill.description.lower().split():
                if len(word) > 3 and word in goal_lower:
                    score += 0.2

            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in scored[:limit]]

    def create_skill_from_workflow(
        self,
        name: str,
        description: str,
        workflow_steps: List[str],
        required_tools: Optional[List[str]] = None,
        purpose: str = "",
    ) -> SkillSpec:
        """
        Creates and persists a new skill created from a successful task workflow.
        """
        spec = SkillSpec(
            name=name,
            description=description,
            purpose=purpose or description,
            workflow=workflow_steps,
            required_tools=required_tools or [],
        )

        # Persist to disk and DB
        spec.save_to_file()
        memory_manager.save_skill(spec.to_procedural_memory())
        return spec

    def record_execution_result(self, name: str, success: bool) -> None:
        """Updates skill statistics."""
        memory_manager.record_skill_result(name, success=success)
        # Update disk file if exists
        skill_dir = SKILLS_DIR / name
        json_file = skill_dir / "skill.json"
        if json_file.exists():
            try:
                with open(json_file, "r+", encoding="utf-8") as f:
                    data = json.load(f)
                    if success:
                        data["success_count"] = data.get("success_count", 0) + 1
                    else:
                        data["failure_count"] = data.get("failure_count", 0) + 1
                    f.seek(0)
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.truncate()
            except Exception:
                pass


# Global instance
skill_system = SkillSystem()
