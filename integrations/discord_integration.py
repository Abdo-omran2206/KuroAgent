"""
integrations/discord_integration.py — Discord Webhook & Bot Integration for KuroAgent

Features:
- Sends rich embeds, formatted text, and alert cards to Discord channels.
- Supports Webhook URLs and Bot tokens.
- Diagnostic testing and channel verification.
"""

from __future__ import annotations

import os
import json
import time
import platform
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from core.logger import logger
from core.vault import vault
from integrations.base import BaseIntegration


class DiscordIntegration(BaseIntegration):
    """
    Discord Webhook & Channel Integration.
    """

    def __init__(self):
        super().__init__(name="discord", version="2.0.0")
        self.webhook_url: Optional[str] = None
        self._load_saved_credentials()

    def _load_saved_credentials(self) -> None:
        url = vault.get_secret("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
        if not url:
            from core.paths import CONFIG_DIR
            cfg_path = CONFIG_DIR / "notifications.json"
            if cfg_path.exists():
                try:
                    data = json.loads(cfg_path.read_text(encoding="utf-8"))
                    url = data.get("discord_webhook", "")
                except Exception:
                    pass

        if url:
            self.connect({"token": url, "webhook_url": url})

    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        if not credentials:
            return False

        url = credentials.get("webhook_url") or credentials.get("token")
        if not url or not str(url).startswith("http"):
            return False

        self.webhook_url = str(url).strip()
        self.is_connected = True
        self.account_name = "Discord Webhook"
        self.permissions = ["send_message", "send_embed"]

        vault.set_secret("DISCORD_WEBHOOK_URL", self.webhook_url, description="Discord Webhook URL")
        logger.info("[Discord] Webhook connected successfully.")
        return True

    def disconnect(self) -> bool:
        self.webhook_url = None
        self.is_connected = False
        self.account_name = None
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "connected": self.is_connected,
            "account": "Active Webhook" if self.is_connected else "Disconnected",
            "permissions": self.permissions,
        }

    def send_message(
        self,
        text: str,
        title: Optional[str] = None,
        color: int = 3447003,
        username: str = "KURO Agent",
    ) -> Dict[str, Any]:
        if not self.is_connected or not self.webhook_url:
            return {"success": False, "error": "Discord is not connected. Use /connect discord <WEBHOOK_URL>."}

        payload: Dict[str, Any] = {
            "username": username,
            "avatar_url": "https://raw.githubusercontent.com/Abdo-omran2206/KuroAgent/main/assets/kuro_icon.png",
        }

        if title:
            payload["embeds"] = [{
                "title": f"🤖 {title}",
                "description": text,
                "color": color,
                "footer": {"text": f"KURO 2.0 • {time.strftime('%Y-%m-%d %H:%M:%S')}"},
                "fields": [
                    {"name": "Host", "value": platform.node(), "inline": True},
                ]
            }]
        else:
            payload["content"] = text

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": "KURO-Agent/2.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"success": resp.status in (200, 204), "status_code": resp.status, "channel": "discord"}
        except urllib.error.HTTPError as e:
            try:
                err_msg = json.loads(e.read().decode("utf-8")).get("message", str(e))
            except Exception:
                err_msg = str(e)
            return {"success": False, "error": f"Discord HTTP {e.code}: {err_msg}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_action(self, action: str, **kwargs) -> Dict[str, Any]:
        if action in ("send_message", "post", "notify"):
            return self.send_message(
                text=kwargs.get("text") or kwargs.get("message", ""),
                title=kwargs.get("title"),
                color=kwargs.get("color", 3447003),
            )
        elif action in ("test", "verify"):
            return self.send_message(
                text="🔔 KURO 2.0 Discord Integration Test Alert — Connected and operational!",
                title="System Diagnostic Test",
                color=3066993,
            )
        return {"success": False, "error": f"Unknown action '{action}' for Discord integration."}
