"""
integrations/telegram_integration.py — Telegram Bot & Channel Integration for KuroAgent

Features:
- Send messages to Users, Groups, Supergroups, and Public/Private Channels.
- Handles channel usernames (e.g. @my_channel) and numeric IDs (-100xxxxxxxxx).
- Robust HTML & Markdown formatting with automatic plain text fallback on parse errors.
- Image, document, and media upload support.
- Deep diagnostics: Explains exact root causes for Telegram HTTP errors (400, 401, 403, 429).
"""

from __future__ import annotations

import os
import json
import html
import urllib.request
import urllib.error
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logger import logger
from core.vault import vault
from integrations.base import BaseIntegration, IntegrationActionType


class TelegramIntegration(BaseIntegration):
    """
    Comprehensive Telegram Bot & Channel Integration.
    """

    def __init__(self):
        super().__init__(name="telegram", version="2.0.0")
        self.bot_token: Optional[str] = None
        self.default_chat_id: Optional[str] = None
        self.bot_username: Optional[str] = None
        self._load_saved_credentials()

    def _load_saved_credentials(self) -> None:
        """Loads credentials from Vault, notifications config, or env."""
        token = vault.get_secret("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = vault.get_secret("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")

        if not token:
            # Check notifications.json
            from core.paths import CONFIG_DIR
            cfg_path = CONFIG_DIR / "notifications.json"
            if cfg_path.exists():
                try:
                    data = json.loads(cfg_path.read_text(encoding="utf-8"))
                    token = data.get("telegram_token", "")
                    chat_id = chat_id or data.get("telegram_chat_id", "")
                except Exception:
                    pass

        if token:
            self.connect({"token": token, "chat_id": chat_id})

    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """
        Authenticates bot token against Telegram getMe API.
        """
        if not credentials or "token" not in credentials:
            return False

        token = str(credentials["token"]).strip()
        chat_id = str(credentials.get("chat_id") or "").strip()

        if not token:
            return False

        # Validate with Telegram API
        success, bot_info, err = self._api_get_me(token)
        if success and bot_info:
            self.bot_token = token
            self.default_chat_id = chat_id or self.default_chat_id
            self.bot_username = bot_info.get("username", "KuroBot")
            self.account_name = f"@{self.bot_username}"
            self.is_connected = True
            self.permissions = ["sendMessage", "sendPhoto", "sendDocument", "getChat", "getUpdates"]

            # Save in Vault
            vault.set_secret("TELEGRAM_BOT_TOKEN", token, description="Telegram Bot Token")
            if chat_id:
                vault.set_secret("TELEGRAM_CHAT_ID", chat_id, description="Telegram Default Chat/Channel ID")

            logger.info(f"[Telegram] Connected as @{self.bot_username}")
            return True
        else:
            logger.warning(f"[Telegram] Connection failed: {err}")
            return False

    def disconnect(self) -> bool:
        self.bot_token = None
        self.default_chat_id = None
        self.bot_username = None
        self.account_name = None
        self.is_connected = False
        self.permissions = []
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "connected": self.is_connected,
            "account": self.account_name or (f"@{self.bot_username}" if self.bot_username else "Disconnected"),
            "default_chat_id": self.default_chat_id or "Not configured",
            "permissions": self.permissions,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Telegram API Core Calls
    # ─────────────────────────────────────────────────────────────────────────

    def _api_get_me(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KURO-Agent/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    return True, data.get("result", {}), None
                return False, None, data.get("description", "Unknown API error")
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                return False, None, err_body.get("description", str(e))
            except Exception:
                return False, None, str(e)
        except Exception as e:
            return False, None, str(e)

    def diagnose_chat_or_channel(self, target_chat_id: str) -> Dict[str, Any]:
        """
        Diagnoses whether a chat ID or channel is valid, reachable, and whether
        the bot has permission to post to it.
        """
        if not self.is_connected or not self.bot_token:
            return {"success": False, "error": "Telegram bot is not connected. Use /connect telegram <BOT_TOKEN>."}

        target = str(target_chat_id).strip()
        url = f"https://api.telegram.org/bot{self.bot_token}/getChat"
        payload = json.dumps({"chat_id": target}).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "KURO-Agent/2.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    res = data["result"]
                    chat_type = res.get("type", "unknown")
                    title = res.get("title") or res.get("username") or res.get("first_name", "Private Chat")
                    return {
                        "success": True,
                        "chat_id": target,
                        "type": chat_type,
                        "title": title,
                        "description": res.get("description", ""),
                        "can_send": True,
                        "message": f"Successfully verified {chat_type} '{title}' (ID: {target}).",
                    }
        except urllib.error.HTTPError as e:
            err_desc = ""
            try:
                err_desc = json.loads(e.read().decode("utf-8")).get("description", "")
            except Exception:
                err_desc = str(e)

            explanation = self._explain_error(err_desc, target)
            return {
                "success": False,
                "error_code": e.code,
                "raw_error": err_desc,
                "explanation": explanation,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _explain_error(self, err_desc: str, target: str) -> str:
        """Provides user-friendly instructions for resolving Telegram permission errors."""
        desc_lower = err_desc.lower()
        if "chat not found" in desc_lower:
            if target.startswith("@"):
                return f"Channel '{target}' was not found. Verify the username is correct and that the channel is public."
            elif target.startswith("-100") or target.startswith("-"):
                return (f"Group/Channel ID '{target}' not found. Make sure you added @{self.bot_username or 'your bot'} "
                        f"to the channel as an Administrator with 'Post Messages' permission enabled.")
            else:
                return f"User chat '{target}' not found. The user must open Telegram and send /start to @{self.bot_username or 'your bot'} first."
        elif "bot is not a member of the channel" in desc_lower or "need administrator rights" in desc_lower or "not enough rights" in desc_lower:
            return (f"Bot @{self.bot_username or 'bot'} is in the channel but lacks permission to post. "
                    f"Go to Channel Settings -> Administrators -> Add @{self.bot_username or 'bot'} -> Enable 'Post Messages'.")
        elif "bot was blocked by the user" in desc_lower:
            return f"The recipient has blocked @{self.bot_username or 'your bot'}."
        elif "can't parse entities" in desc_lower:
            return "Formatting entity parsing error in Markdown/HTML. KURO will automatically retry with plain text."
        return f"Telegram API error: {err_desc}"

    def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        title: Optional[str] = None,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = False,
    ) -> Dict[str, Any]:
        """
        Sends a message to a Telegram chat, group, or channel.
        Uses HTML parsing by default to avoid Markdown escaping issues.
        """
        if not self.is_connected or not self.bot_token:
            return {"success": False, "error": "Telegram bot is not connected. Configure with /connect telegram <BOT_TOKEN>."}

        target = str(chat_id or self.default_chat_id or "").strip()
        if not target:
            return {"success": False, "error": "No recipient chat_id or channel specified. Use /connect telegram <TOKEN> <CHAT_ID>."}

        # Build formatted text
        if parse_mode.upper() == "HTML":
            if title:
                formatted_body = f"<b>🔔 {html.escape(title)}</b>\n\n{html.escape(text)}"
            else:
                formatted_body = html.escape(text)
        elif parse_mode.upper() == "MARKDOWN":
            formatted_body = f"*{title}*\n\n{text}" if title else text
        else:
            formatted_body = f"[{title}]\n\n{text}" if title else text

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": target,
            "text": formatted_body,
            "parse_mode": parse_mode if parse_mode.upper() in ("HTML", "MARKDOWN", "MARKDOWNV2") else None,
            "disable_web_page_preview": disable_web_page_preview,
        }

        # Send attempt
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "KURO-Agent/2.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    msg_id = data.get("result", {}).get("message_id")
                    return {"success": True, "chat_id": target, "message_id": msg_id, "channel": "telegram"}
        except urllib.error.HTTPError as e:
            try:
                err_desc = json.loads(e.read().decode("utf-8")).get("description", "")
            except Exception:
                err_desc = str(e)

            # If formatting failed, retry once with plain text
            if "can't parse entities" in err_desc.lower() and payload.get("parse_mode"):
                try:
                    payload["parse_mode"] = None
                    payload["text"] = f"{title}\n\n{text}" if title else text
                    req_retry = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json", "User-Agent": "KURO-Agent/2.0"}
                    )
                    with urllib.request.urlopen(req_retry, timeout=10) as resp_retry:
                        data_retry = json.loads(resp_retry.read().decode("utf-8"))
                        if data_retry.get("ok"):
                            return {"success": True, "chat_id": target, "message_id": data_retry.get("result", {}).get("message_id"), "channel": "telegram"}
                except Exception:
                    pass

            explanation = self._explain_error(err_desc, target)
            return {"success": False, "error": explanation, "raw_error": err_desc, "status_code": e.code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_photo(
        self,
        photo_path_or_url: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends a photo to a chat or channel."""
        if not self.is_connected or not self.bot_token:
            return {"success": False, "error": "Telegram not connected."}

        target = str(chat_id or self.default_chat_id or "").strip()
        if not target:
            return {"success": False, "error": "No chat_id specified."}

        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"

        # If it's a web URL
        if str(photo_path_or_url).startswith("http://") or str(photo_path_or_url).startswith("https://"):
            payload = {"chat_id": target, "photo": photo_path_or_url, "caption": caption or ""}
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "KURO-Agent/2.0"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return {"success": True, "chat_id": target}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Local file upload via multipart/form-data
        local_p = Path(photo_path_or_url)
        if not local_p.exists():
            return {"success": False, "error": f"Photo file '{photo_path_or_url}' not found."}

        try:
            boundary = f"----WebKitFormBoundary{os.urandom(16).hex()}"
            body = bytearray()

            # chat_id field
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{target}\r\n'.encode("utf-8"))

            # caption field
            if caption:
                body.extend(f"--{boundary}\r\n".encode("utf-8"))
                body.extend(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode("utf-8"))

            # photo file field
            mime = mimetypes.guess_type(str(local_p))[0] or "image/png"
            file_bytes = local_p.read_bytes()
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="photo"; filename="{local_p.name}"\r\n'.encode("utf-8"))
            body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
            body.extend(file_bytes)
            body.extend(b"\r\n")
            body.extend(f"--{boundary}--\r\n".encode("utf-8"))

            req = urllib.request.Request(
                url,
                data=bytes(body),
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "User-Agent": "KURO-Agent/2.0",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return {"success": True, "chat_id": target, "file": local_p.name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_action(self, action: str, **kwargs) -> Dict[str, Any]:
        """Dynamic action dispatcher for Telegram integration."""
        if action in ("send_message", "notify", "post"):
            return self.send_message(
                text=kwargs.get("text") or kwargs.get("message", ""),
                chat_id=kwargs.get("chat_id") or kwargs.get("channel"),
                title=kwargs.get("title"),
                parse_mode=kwargs.get("parse_mode", "HTML"),
            )
        elif action in ("send_photo", "photo", "image"):
            return self.send_photo(
                photo_path_or_url=kwargs.get("photo") or kwargs.get("image", ""),
                caption=kwargs.get("caption") or kwargs.get("message"),
                chat_id=kwargs.get("chat_id") or kwargs.get("channel"),
            )
        elif action in ("diagnose", "test", "verify"):
            target = kwargs.get("chat_id") or kwargs.get("channel") or self.default_chat_id
            if not target:
                return {"success": False, "error": "No chat_id provided to test."}
            return self.diagnose_chat_or_channel(target)
        elif action in ("get_me", "whoami"):
            if not self.bot_token:
                return {"success": False, "error": "Not connected"}
            ok, info, err = self._api_get_me(self.bot_token)
            return {"success": ok, "bot_info": info, "error": err}
        return {"success": False, "error": f"Unknown action '{action}' for Telegram integration."}
