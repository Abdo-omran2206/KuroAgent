"""
integrations package — External Connected Services for KuroAgent
"""

from integrations.base import BaseIntegration, IntegrationActionType
from integrations.github_integration import GitHubIntegration
from integrations.google_drive_integration import GoogleDriveIntegration
from integrations.email_integration import EmailIntegration
from integrations.telegram_integration import TelegramIntegration
from integrations.discord_integration import DiscordIntegration

__all__ = [
    "BaseIntegration",
    "IntegrationActionType",
    "GitHubIntegration",
    "GoogleDriveIntegration",
    "EmailIntegration",
    "TelegramIntegration",
    "DiscordIntegration",
]
