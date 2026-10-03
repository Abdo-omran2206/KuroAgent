"""
integrations/base.py — Abstract Base Class & Action Risk for External Integrations

Defines the contract for external integrations (GitHub, Google Drive, Email, etc.):
  - Name, Version, Connected Status
  - Action Risk Classification:
      READ                 — Automatically allowed if authorized
      WRITE                — Controlled by permission setting
      EXTERNAL_SIDE_EFFECT — Requires confirmation by default
      DESTRUCTIVE          — Always requires confirmation
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional


class IntegrationActionType(str, Enum):
    READ                 = "read"
    WRITE                = "write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    DESTRUCTIVE          = "destructive"


class BaseIntegration(ABC):
    """
    Common abstraction for external connected services.
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.is_connected: bool = False
        self.account_name: Optional[str] = None
        self.permissions: List[str] = []

    @abstractmethod
    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """Authenticates and establishes connection with external service."""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """Revokes tokens and disconnects integration."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns connection status summary."""
        pass

    @abstractmethod
    def execute_action(self, action: str, **kwargs) -> Dict[str, Any]:
        """Executes named integration action."""
        pass

    def classify_action_risk(self, action: str) -> IntegrationActionType:
        """Default action risk classification."""
        if any(w in action for w in ("delete", "remove", "destroy", "purge")):
            return IntegrationActionType.DESTRUCTIVE
        if any(w in action for w in ("send", "create", "post", "open_pr", "push")):
            return IntegrationActionType.EXTERNAL_SIDE_EFFECT
        if any(w in action for w in ("write", "update", "upload")):
            return IntegrationActionType.WRITE
        return IntegrationActionType.READ
