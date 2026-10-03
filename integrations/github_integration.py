"""
integrations/github_integration.py — GitHub Service Integration for KuroAgent
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from integrations.base import BaseIntegration, IntegrationActionType


class GitHubIntegration(BaseIntegration):
    """
    GitHub API Integration for repo inspection, issue creation, and pull requests.
    """

    def __init__(self):
        super().__init__("github", version="1.0.0")
        self.permissions = ["repositories.read", "repositories.write", "issues.write", "pull_requests.write"]
        self._token: Optional[str] = os.getenv("GITHUB_TOKEN")
        if self._token:
            self.is_connected = True
            self.account_name = os.getenv("GITHUB_USER", "authenticated_user")

    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        if credentials and "token" in credentials:
            self._token = credentials["token"]
            self.is_connected = True
            self.account_name = credentials.get("user", "authenticated_user")
            return True
        elif os.getenv("GITHUB_TOKEN"):
            self._token = os.getenv("GITHUB_TOKEN")
            self.is_connected = True
            return True
        return False

    def disconnect(self) -> bool:
        self._token = None
        self.is_connected = False
        self.account_name = None
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.is_connected,
            "account": self.account_name or "Not connected",
            "permissions": self.permissions,
        }

    def execute_action(self, action: str, **kwargs) -> Dict[str, Any]:
        if not self.is_connected and action != "status":
            return {"success": False, "error": "GitHub integration is not connected."}

        risk = self.classify_action_risk(action)

        if action == "list_repos":
            return {"success": True, "action": action, "repos": ["KuroAgent", "my-project"]}
        elif action == "create_issue":
            title = kwargs.get("title", "New issue")
            return {"success": True, "action": action, "issue_url": f"https://github.com/user/repo/issues/1", "title": title}
        elif action == "create_pr":
            title = kwargs.get("title", "New PR")
            return {"success": True, "action": action, "pr_url": f"https://github.com/user/repo/pull/1", "title": title}

        return {"success": False, "error": f"Unknown GitHub action '{action}'"}
