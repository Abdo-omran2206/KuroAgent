"""
core/project_aware.py — Project Inspection & Awareness Engine for KuroAgent

Inspects the current working project directory and builds a complete profile:
  - Language(s) & Frameworks (Python, Node.js/React/Vite, Rust, Go, Java, etc.)
  - Package manager (pip, npm, pnpm, yarn, cargo, poetry, etc.)
  - Key entry points (main.py, index.js, src/App.tsx, etc.)
  - Important directories & configuration files
  - Build/test/run commands
  - Dependencies
  - Git status

Profiles are cached in %APPDATA%\\Kuro\\projects\\ and SQLite semantic memory
so Kuro does not rediscover everything for every single task step.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logger import logger
from core.paths import PROJECTS_DIR


class ProjectProfile:
    """Represents a cached project profile."""

    def __init__(self, root_dir: str):
        self.root_dir: str = str(Path(root_dir).resolve())
        self.name: str = Path(self.root_dir).name
        self.languages: List[str] = []
        self.frameworks: List[str] = []
        self.package_managers: List[str] = []
        self.entry_points: List[str] = []
        self.config_files: List[str] = []
        self.important_dirs: List[str] = []
        self.scripts: Dict[str, str] = {}
        self.dependencies: List[str] = []
        self.build_command: str = ""
        self.test_command: str = ""
        self.git_status: str = ""
        self.architecture_hints: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "root_dir": self.root_dir,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "package_managers": self.package_managers,
            "entry_points": self.entry_points,
            "config_files": self.config_files,
            "important_dirs": self.important_dirs,
            "scripts": self.scripts,
            "dependencies": self.dependencies,
            "build_command": self.build_command,
            "test_command": self.test_command,
            "git_status": self.git_status,
            "architecture_hints": self.architecture_hints,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectProfile":
        profile = cls(root_dir=data.get("root_dir", "."))
        profile.name = data.get("name", "unknown")
        profile.languages = data.get("languages", [])
        profile.frameworks = data.get("frameworks", [])
        profile.package_managers = data.get("package_managers", [])
        profile.entry_points = data.get("entry_points", [])
        profile.config_files = data.get("config_files", [])
        profile.important_dirs = data.get("important_dirs", [])
        profile.scripts = data.get("scripts", {})
        profile.dependencies = data.get("dependencies", [])
        profile.build_command = data.get("build_command", "")
        profile.test_command = data.get("test_command", "")
        profile.git_status = data.get("git_status", "")
        profile.architecture_hints = data.get("architecture_hints", [])
        return profile

    def format_summary(self) -> str:
        lines = [
            f"[Project Profile: {self.name}]",
            f"Languages: {', '.join(self.languages) if self.languages else 'Unknown'}",
            f"Frameworks: {', '.join(self.frameworks) if self.frameworks else 'None detected'}",
            f"Package Managers: {', '.join(self.package_managers) if self.package_managers else 'None'}",
            f"Entry Points: {', '.join(self.entry_points) if self.entry_points else 'None detected'}",
            f"Configs: {', '.join(self.config_files[:5])}",
        ]
        if self.build_command:
            lines.append(f"Build Cmd: `{self.build_command}`")
        if self.test_command:
            lines.append(f"Test Cmd: `{self.test_command}`")
        return "\n".join(lines)


class ProjectInspector:
    """
    Inspects directories and generates / refreshes ProjectProfile instances.
    """

    def inspect(self, root_dir_str: str = ".", force_refresh: bool = False) -> ProjectProfile:
        root_dir = Path(root_dir_str).resolve()
        cache_file = PROJECTS_DIR / f"{root_dir.name}_profile.json"

        if not force_refresh and cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return ProjectProfile.from_dict(data)
            except Exception:
                pass

        logger.info(f"Building project profile for '{root_dir}'...")
        profile = ProjectProfile(str(root_dir))

        # Detect files and configs
        self._detect_languages_and_configs(root_dir, profile)
        self._detect_package_json(root_dir, profile)
        self._detect_python_env(root_dir, profile)
        self._detect_git_status(root_dir, profile)
        self._detect_entry_points_and_dirs(root_dir, profile)

        # Cache result
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to cache project profile", {"error": str(e)})

        return profile

    def _detect_languages_and_configs(self, root: Path, profile: ProjectProfile) -> None:
        file_map = {
            "requirements.txt": ("Python", "pip"),
            "pyproject.toml": ("Python", "poetry/flit"),
            "setup.py": ("Python", "setuptools"),
            "Pipfile": ("Python", "pipenv"),
            "package.json": ("JavaScript/TypeScript", "npm"),
            "Cargo.toml": ("Rust", "cargo"),
            "go.mod": ("Go", "go modules"),
            "pom.xml": ("Java", "maven"),
            "build.gradle": ("Java/Kotlin", "gradle"),
            "CMakeLists.txt": ("C/C++", "cmake"),
            "Makefile": ("C/C++/Make", "make"),
            "Dockerfile": ("Docker", "docker"),
            "docker-compose.yml": ("Docker Compose", "docker-compose"),
            "vite.config.js": ("Vite/React", "vite"),
            "vite.config.ts": ("Vite/React/TS", "vite"),
            "tsconfig.json": ("TypeScript", "tsc"),
        }

        for file_name, (lang_or_fw, pkg) in file_map.items():
            if (root / file_name).exists():
                profile.config_files.append(file_name)
                if "/" in lang_or_fw:
                    for item in lang_or_fw.split("/"):
                        if item not in profile.languages and item not in profile.frameworks:
                            profile.languages.append(item)
                else:
                    if lang_or_fw not in profile.languages:
                        profile.languages.append(lang_or_fw)
                if pkg and pkg not in profile.package_managers:
                    profile.package_managers.append(pkg)

    def _detect_package_json(self, root: Path, profile: ProjectProfile) -> None:
        pkg_json = root / "package.json"
        if not pkg_json.exists():
            return
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            scripts = data.get("scripts", {})
            profile.scripts = scripts

            if "build" in scripts:
                profile.build_command = f"npm run build"
            if "test" in scripts:
                profile.test_command = f"npm test"

            deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
            profile.dependencies = deps[:20]  # top 20

            if "react" in deps:
                profile.frameworks.append("React")
            if "vue" in deps:
                profile.frameworks.append("Vue")
            if "express" in deps:
                profile.frameworks.append("Express")
            if "next" in deps:
                profile.frameworks.append("Next.js")
        except Exception:
            pass

    def _detect_python_env(self, root: Path, profile: ProjectProfile) -> None:
        if "Python" not in profile.languages:
            return
        reqs = root / "requirements.txt"
        if reqs.exists():
            try:
                deps = [line.strip().split("==")[0].split(">=")[0] for line in reqs.read_text().splitlines() if line.strip() and not line.startswith("#")]
                profile.dependencies = deps[:20]
                if "pytest" in deps:
                    profile.test_command = "pytest"
                if "django" in deps:
                    profile.frameworks.append("Django")
                if "flask" in deps:
                    profile.frameworks.append("Flask")
                if "fastapi" in deps:
                    profile.frameworks.append("FastAPI")
                if "typer" in deps:
                    profile.frameworks.append("Typer CLI")
            except Exception:
                pass

    def _detect_git_status(self, root: Path, profile: ProjectProfile) -> None:
        if not (root / ".git").exists():
            profile.git_status = "Not a Git repository"
            return
        try:
            res = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                changes = res.stdout.strip().splitlines()
                profile.git_status = f"Clean branch" if not changes else f"{len(changes)} modified/untracked files"
        except Exception:
            profile.git_status = "Git status check failed"

    def _detect_entry_points_and_dirs(self, root: Path, profile: ProjectProfile) -> None:
        possible_entries = ["main.py", "app.py", "index.js", "index.ts", "src/index.js", "src/main.py", "src/App.tsx", "src/main.tsx", "cmd/main.go"]
        for entry in possible_entries:
            if (root / entry).exists():
                profile.entry_points.append(entry)

        possible_dirs = ["src", "core", "tools", "tests", "components", "pages", "api", "build", "dist", "brain"]
        for d in possible_dirs:
            if (root / d).is_dir():
                profile.important_dirs.append(d)


# Global instance
project_inspector = ProjectInspector()
