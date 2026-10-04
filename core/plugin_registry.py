"""
core/plugin_registry.py — Plugin Architecture & Tool Contract for KuroAgent

Refactors tool handling into a modular plugin-ready registry with standard contracts.
Every tool or plugin registers with:
  - name
  - description
  - input_schema
  - output_schema
  - risk_level (SAFE, CONFIRM, DANGEROUS)
  - execution_handler (callable)
  - version
  - category/plugin_name

Supports dynamic loading of user plugins from %APPDATA%\\Kuro\\plugins\\
and built-in core tools.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.permissions import RiskLevel, register_action_risk


@dataclass
class ToolContract:
    """Standardized metadata and execution contract for a tool/action."""
    name: str
    description: str
    handler: Callable[..., Dict[str, Any]]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.CONFIRM
    version: str = "1.0.0"
    plugin_name: str = "core"
    category: str = "general"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Executes the tool handler with parameters."""
        try:
            return self.handler(**kwargs)
        except Exception as e:
            return {"success": False, "error": f"Tool Execution Exception [{self.name}]: {str(e)}"}


class PluginRegistry:
    """
    Central discovery, registration, and dispatch engine for tools and plugins.
    """

    def __init__(self):
        self._tools: Dict[str, ToolContract] = {}
        self._plugins: Dict[str, Dict[str, Any]] = {}

    def register_tool(self, tool: ToolContract) -> None:
        """Registers a ToolContract into the registry and updates risk policies."""
        self._tools[tool.name] = tool
        register_action_risk(tool.name, tool.risk_level)

    def register_function(
        self,
        name: str,
        description: str,
        handler: Callable[..., Dict[str, Any]],
        risk_level: RiskLevel = RiskLevel.CONFIRM,
        plugin_name: str = "core",
        category: str = "general",
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> ToolContract:
        """Convenience function to register a callable handler directly."""
        contract = ToolContract(
            name=name,
            description=description,
            handler=handler,
            input_schema=input_schema or {},
            risk_level=risk_level,
            plugin_name=plugin_name,
            category=category,
        )
        self.register_tool(contract)
        return contract

    def get_tool(self, name: str) -> Optional[ToolContract]:
        """Retrieves a registered tool by action name."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Checks if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> List[ToolContract]:
        """Returns all registered tool contracts."""
        return list(self._tools.values())

    def execute_tool(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Finds and executes a registered tool."""
        tool = self.get_tool(name)
        if not tool:
            return {"success": False, "error": f"Unknown action '{name}' in plugin registry."}
        return tool.execute(**params)

    def load_user_plugins(self, plugins_dir: Optional[Path] = None) -> int:
        """
        Dynamically discovers and loads external plugins from %APPDATA%\\Kuro\\plugins\\

        Plugin directory structure expected:
          plugins/
            <plugin_name>/
              plugin.json
              plugin.py
        """
        if plugins_dir is None:
            from core.paths import PLUGINS_DIR
            plugins_dir = PLUGINS_DIR

        if not plugins_dir.exists():
            return 0

        loaded_count = 0
        for plugin_folder in plugins_dir.iterdir():
            if plugin_folder.is_dir():
                manifest_path = plugin_folder / "plugin.json"
                py_path = plugin_folder / "plugin.py"

                if manifest_path.exists() and py_path.exists():
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            manifest = json.load(f)

                        p_name = manifest.get("name", plugin_folder.name)
                        p_version = manifest.get("version", "1.0.0")

                        # Dynamically import module
                        sys.path.insert(0, str(plugin_folder))
                        mod_name = f"kuro_plugin_{plugin_folder.name}"
                        spec = importlib.util.spec_from_file_location(mod_name, str(py_path))
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            sys.modules[mod_name] = module
                            spec.loader.exec_module(module)

                            # If plugin module exposes register(registry)
                            if hasattr(module, "register") and callable(module.register):
                                module.register(self)

                            self._plugins[p_name] = {
                                "manifest": manifest,
                                "dir": str(plugin_folder),
                                "version": p_version,
                                "status": "active",
                            }
                            loaded_count += 1
                    except Exception:
                        pass

        return loaded_count

    def generate_system_tool_schemas(self) -> str:
        """Generates compact prompt schema documentation for LLM tool selection."""
        lines = []
        for tool in self._tools.values():
            schema_sample = {"action": tool.name}
            if tool.input_schema and "properties" in tool.input_schema:
                for k in tool.input_schema["properties"]:
                    schema_sample[k] = f"<{k}>"
            lines.append(f"- {tool.name}: {tool.description}\n  Schema: ```json\n{json.dumps(schema_sample)}\n```")
        return "\n".join(lines)


# Global instance
registry = PluginRegistry()
