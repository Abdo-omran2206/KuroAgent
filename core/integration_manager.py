"""
core/integration_manager.py — Integration Manager for KuroAgent

Central manager responsible for:
  - Discovering integrations (GitHub, Google Drive, Email, Telegram, Discord, Slack)
  - Connection status & encrypted credential management
  - Natural Language Intent Routing (e.g. 'send Telegram message to channel' -> telegram)
  - Permission scope enforcement
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.paths import ENV_FILE
from core.vault import vault
from integrations.base import BaseIntegration, IntegrationActionType
from integrations.github_integration import GitHubIntegration
from integrations.google_drive_integration import GoogleDriveIntegration
from integrations.email_integration import EmailIntegration
from integrations.telegram_integration import TelegramIntegration
from integrations.discord_integration import DiscordIntegration


class IntegrationManager:
    """
    Central connection manager for external services.
    """

    def __init__(self):
        self._integrations: Dict[str, BaseIntegration] = {}
        self._register_default_integrations()

    def _register_default_integrations(self):
        github = GitHubIntegration()
        drive = GoogleDriveIntegration()
        email = EmailIntegration()
        telegram = TelegramIntegration()
        discord = DiscordIntegration()

        self._integrations[github.name] = github
        self._integrations[drive.name] = drive
        self._integrations[email.name] = email
        self._integrations[telegram.name] = telegram
        self._integrations[discord.name] = discord

    def register_integration(self, integration: BaseIntegration) -> None:
        self._integrations[integration.name] = integration

    def get_integration(self, name: str) -> Optional[BaseIntegration]:
        return self._integrations.get(name.lower())

    def list_integrations(self) -> List[Dict[str, Any]]:
        return [integ.get_status() for integ in self._integrations.values()]

    def connect_integration(self, name: str, token: str, user: Optional[str] = None) -> bool:
        """
        Connects an integration with provided token/key and persists it to Encrypted Vault and .env.
        """
        clean_name = name.lower()
        if clean_name in ("tg", "tele"):
            clean_name = "telegram"
        elif clean_name in ("disc", "discord_webhook"):
            clean_name = "discord"

        integ = self.get_integration(clean_name)
        if not integ:
            return False

        creds = {"token": token, "user": user or f"{clean_name}_user"}
        if clean_name == "telegram" and user:
            creds["chat_id"] = user
        elif clean_name == "discord":
            creds["webhook_url"] = token

        success = integ.connect(creds)
        if success:
            env_var_map = {
                "github": ("GITHUB_TOKEN", "GITHUB_USER"),
                "google_drive": ("GOOGLE_DRIVE_TOKEN", "GOOGLE_DRIVE_USER"),
                "email": ("EMAIL_TOKEN", "EMAIL_USER"),
                "telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
                "discord": ("DISCORD_WEBHOOK_URL", None),
            }
            if clean_name in env_var_map:
                token_var, user_var = env_var_map[clean_name]
                os.environ[token_var] = token
                vault.set_secret(token_var, token, description=f"{clean_name.upper()} credential")
                if user_var and user:
                    os.environ[user_var] = user
                    vault.set_secret(user_var, user, description=f"{clean_name.upper()} user/chat_id")
                self._persist_to_env(token_var, token, user_var, user)

            return True
        return False

    def disconnect_integration(self, name: str) -> bool:
        """
        Disconnects an integration and clears its active session.
        """
        integ = self.get_integration(name)
        if not integ:
            return False
        return integ.disconnect()

    def _persist_to_env(self, token_var: str, token_val: str, user_var: Optional[str], user_val: Optional[str]) -> None:
        """Helper to write token to .env file."""
        env_vars = {}
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

        env_vars[token_var] = token_val
        if user_var and user_val:
            env_vars[user_var] = user_val

        try:
            lines = [f"{k}={v}" for k, v in env_vars.items()]
            ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    def route_intent(self, prompt: str) -> Optional[BaseIntegration]:
        """
        Routes natural language user requests to the appropriate connected service.
        """
        p_lower = prompt.lower()
        if any(w in p_lower for w in ("github", "pull request", "repo", "pr", "issue")):
            return self.get_integration("github")
        elif any(w in p_lower for w in ("drive", "google drive", "upload report", "drive pdf")):
            return self.get_integration("google_drive")
        elif any(w in p_lower for w in ("email", "gmail", "mail", "inbox", "unread")):
            return self.get_integration("email")
        elif any(w in p_lower for w in ("telegram", "telegram channel", "telegram bot", "send telegram", "tg message")):
            return self.get_integration("telegram")
        elif any(w in p_lower for w in ("discord", "discord webhook", "discord server", "discord channel")):
            return self.get_integration("discord")
        return None


# Global instance
integration_manager = IntegrationManager()
