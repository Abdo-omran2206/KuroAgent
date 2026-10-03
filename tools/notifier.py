"""
tools/notifier.py — Next-Gen Multi-Channel Notification Engine for KuroAgent

Features:
  - 🍞 Rich Windows 10/11 Action Center Toast with Branding, Sound & Urgency
  - 🔊 Neural Speech Alerts & Audio Chimes
  - 🎮 Discord Webhooks with Urgency-Colored Embeds
  - 📱 Telegram Bot & Channel Instant Alerts (HTML entity escaping, image attachments, deep error diagnostics)
  - 💬 Slack Webhook Integration
  - 🔒 Encrypted Secret Vault Integration
  - ⚙️ Channel Config Persistence (%APPDATA%\\Kuro\\config\\notifications.json)
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
import html
import urllib.request
import urllib.error
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.paths import APP_DIR, CONFIG_DIR
from core.vault import vault
from core.logger import logger


class NotificationUrgency(str, Enum):
    INFO     = "info"        # Blue
    SUCCESS  = "success"     # Green
    WARNING  = "warning"     # Yellow/Orange
    CRITICAL = "critical"    # Red
    ALERT    = "alert"       # Magenta / Urgent


_URGENCY_COLORS = {
    NotificationUrgency.INFO:     3447003,   # #3498DB (Blue)
    NotificationUrgency.SUCCESS:  3066993,   # #2ECC71 (Green)
    NotificationUrgency.WARNING:  15105570,  # #E67E22 (Orange)
    NotificationUrgency.CRITICAL: 15158332,  # #E74C3C (Red)
    NotificationUrgency.ALERT:    10181046,  # #9B59B6 (Purple)
}

_TOAST_SOUNDS = {
    "default":  "ms-winsoundevent:Notification.Default",
    "im":       "ms-winsoundevent:Notification.IM",
    "mail":     "ms-winsoundevent:Notification.Mail",
    "reminder": "ms-winsoundevent:Notification.Reminder",
    "alarm":    "ms-winsoundevent:Notification.Looping.Alarm",
    "silent":   "",
}


def _get_config_file() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR / "notifications.json"


def load_notification_config() -> Dict[str, Any]:
    """Loads saved notification settings, prioritizing Encrypted Vault and .env."""
    cfg_file = _get_config_file()
    file_cfg = {}
    if cfg_file.exists():
        try:
            file_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    discord = vault.get_secret("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL") or file_cfg.get("discord_webhook", "")
    tele_token = vault.get_secret("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or file_cfg.get("telegram_token", "")
    tele_chat = vault.get_secret("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or file_cfg.get("telegram_chat_id", "")
    slack = vault.get_secret("SLACK_WEBHOOK_URL") or os.getenv("SLACK_WEBHOOK_URL") or file_cfg.get("slack_webhook", "")

    return {
        "discord_webhook": discord,
        "telegram_token":  tele_token,
        "telegram_chat_id":tele_chat,
        "slack_webhook":   slack,
        "default_channels":file_cfg.get("default_channels", ["toast"]),
        "sound_enabled":   file_cfg.get("sound_enabled", True),
    }


def save_notification_config(config_data: Dict[str, Any]) -> bool:
    """Saves notification configuration to JSON and Encrypted Vault."""
    cfg_file = _get_config_file()
    try:
        cfg_file.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")
        if config_data.get("discord_webhook"):
            vault.set_secret("DISCORD_WEBHOOK_URL", config_data["discord_webhook"], description="Discord Webhook URL")
        if config_data.get("telegram_token"):
            vault.set_secret("TELEGRAM_BOT_TOKEN", config_data["telegram_token"], description="Telegram Bot Token")
        if config_data.get("telegram_chat_id"):
            vault.set_secret("TELEGRAM_CHAT_ID", config_data["telegram_chat_id"], description="Telegram Chat/Channel ID")
        if config_data.get("slack_webhook"):
            vault.set_secret("SLACK_WEBHOOK_URL", config_data["slack_webhook"], description="Slack Webhook URL")
        return True
    except Exception as e:
        logger.error(f"[Notifier] Failed to save config: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. Windows Action Center Toast Notification
# ─────────────────────────────────────────────────────────────────────────────

def send_toast_notification(
    title: str,
    message: str,
    urgency: NotificationUrgency = NotificationUrgency.INFO,
    sound: str = "default",
    app_id: str = "KURO AI Assistant",
) -> Dict[str, Any]:
    """Sends an advanced branded Windows Toast Notification."""
    if platform.system() != "Windows":
        return {"success": False, "error": "Toast notifications are only supported on Windows OS."}

    icon_path = (APP_DIR / "assets" / "kuro_icon.png").resolve()
    icon_xml = f'<image placement="appLogoOverride" src="{icon_path}" hint-crop="circle"/>' if icon_path.exists() else ''

    sound_uri = _TOAST_SOUNDS.get(sound.lower(), _TOAST_SOUNDS["default"])
    sound_xml = f'<audio src="{sound_uri}" silent="false"/>' if sound_uri else '<audio silent="true"/>'

    urgency_badge = {
        NotificationUrgency.INFO:     "ℹ️ INFO",
        NotificationUrgency.SUCCESS:  "✅ SUCCESS",
        NotificationUrgency.WARNING:  "⚠️ WARNING",
        NotificationUrgency.CRITICAL: "🚨 CRITICAL",
        NotificationUrgency.ALERT:    "🔔 ALERT",
    }.get(urgency, "🔔 ALERT")

    title_escaped = f"[{urgency_badge}] {title}".replace('"', '`"').replace("'", "''")
    msg_escaped = message.replace('"', '`"').replace("'", "''")
    time_str = time.strftime("%I:%M %p")

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $template = @"
    <toast duration="short">
        <visual>
            <binding template="ToastGeneric">
                {icon_xml}
                <text id="1">{title_escaped}</text>
                <text id="2">{msg_escaped}</text>
                <text placement="attribution">KURO 2.0 • {time_str}</text>
            </binding>
        </visual>
        {sound_xml}
    </toast>
"@

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{app_id}")
    $notifier.Show($toast)
    """

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return {"success": True, "method": "windows_toast", "title": title, "urgency": urgency.value}
        else:
            fallback_ps = f'''
            Add-Type -AssemblyName System.Windows.Forms
            $global:bal = New-Object System.Windows.Forms.NotifyIcon
            $path = (Get-Process -id $pid).Path
            $bal.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
            $bal.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
            $bal.BalloonTipTitle = "{title_escaped}"
            $bal.BalloonTipText = "{msg_escaped}"
            $bal.Visible = $true
            $bal.ShowBalloonTip(5000)
            '''
            subprocess.run(["powershell", "-NoProfile", "-Command", fallback_ps], capture_output=True, timeout=10)
            return {"success": True, "method": "balloon_fallback", "title": title}
    except Exception as e:
        return {"success": False, "error": f"Toast notification error: {str(e)}"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Discord Webhook Notification
# ─────────────────────────────────────────────────────────────────────────────

def send_discord_notification(
    webhook_url: str,
    title: str,
    message: str,
    urgency: NotificationUrgency = NotificationUrgency.INFO,
    image_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Sends a rich embedded notification card to Discord."""
    color = _URGENCY_COLORS.get(urgency, 3447003)
    embed: Dict[str, Any] = {
        "title": f"🤖 {title}",
        "description": message,
        "color": color,
        "fields": [
            {"name": "Urgency", "value": urgency.value.upper(), "inline": True},
            {"name": "Host", "value": platform.node(), "inline": True},
        ],
        "footer": {"text": f"KURO 2.0 • {time.strftime('%Y-%m-%d %H:%M:%S')}"},
    }
    if image_url:
        embed["image"] = {"url": image_url}

    payload = {
        "username": "KURO Agent",
        "avatar_url": "https://raw.githubusercontent.com/Abdo-omran2206/KuroAgent/main/assets/kuro_icon.png",
        "embeds": [embed]
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "KURO-Assistant/2.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"success": resp.status in (200, 204), "channel": "discord", "status": resp.status}
    except urllib.error.HTTPError as e:
        try:
            err_msg = json.loads(e.read().decode("utf-8")).get("message", str(e))
        except Exception:
            err_msg = str(e)
        return {"success": False, "channel": "discord", "error": f"Discord HTTP {e.code}: {err_msg}"}
    except Exception as e:
        return {"success": False, "channel": "discord", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Telegram Bot & Channel Notification
# ─────────────────────────────────────────────────────────────────────────────

def send_telegram_notification(
    bot_token: str,
    chat_id: str,
    title: str,
    message: str,
    urgency: NotificationUrgency = NotificationUrgency.INFO,
    image_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends a formatted notification to a Telegram user, group, or channel.
    Uses HTML formatting with automatic escaping to prevent parsing crashes.
    """
    from integrations.telegram_integration import TelegramIntegration
    tg = TelegramIntegration()
    if not tg.is_connected or tg.bot_token != bot_token:
        tg.connect({"token": bot_token, "chat_id": chat_id})

    badge = {
        NotificationUrgency.INFO: "ℹ️",
        NotificationUrgency.SUCCESS: "✅",
        NotificationUrgency.WARNING: "⚠️",
        NotificationUrgency.CRITICAL: "🚨",
        NotificationUrgency.ALERT: "🔔",
    }.get(urgency, "🔔")

    formatted_title = f"{badge} {title}"

    if image_path:
        res = tg.send_photo(
            photo_path_or_url=image_path,
            caption=f"<b>{html.escape(formatted_title)}</b>\n\n{html.escape(message)}\n\n<code>[{urgency.value.upper()} | {time.strftime('%H:%M:%S')}]</code>",
            chat_id=chat_id,
        )
    else:
        body = f"{message}\n\n<code>[{urgency.value.upper()} | {time.strftime('%H:%M:%S')}]</code>"
        res = tg.send_message(
            text=body,
            title=formatted_title,
            chat_id=chat_id,
            parse_mode="HTML"
        )
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 4. Slack Webhook Notification
# ─────────────────────────────────────────────────────────────────────────────

def send_slack_notification(
    webhook_url: str,
    title: str,
    message: str,
    urgency: NotificationUrgency = NotificationUrgency.INFO,
) -> Dict[str, Any]:
    """Sends a Block-Kit notification message to Slack."""
    payload = {
        "text": f"*{title}*\n{message}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🤖 KURO: {title}", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Urgency:*\n`{urgency.value.upper()}`"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{time.strftime('%H:%M:%S')}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message},
            },
        ],
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "KURO-Assistant/2.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"success": resp.status == 200, "channel": "slack"}
    except Exception as e:
        return {"success": False, "channel": "slack", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Smart Multi-Channel Dispatcher & Diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def send_smart_notification(
    title: str,
    message: str,
    urgency: NotificationUrgency = NotificationUrgency.INFO,
    channels: Optional[List[str]] = None,
    speak: bool = False,
    sound: str = "default",
    target_override: Optional[str] = None,
    image_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Omni-channel smart notifier. Dispatches notifications concurrently across
    all configured channels with optional voice chimes and attachments.
    """
    cfg = load_notification_config()
    target_channels = [c.lower() for c in (channels or cfg.get("default_channels", ["toast"]))]

    results: Dict[str, Any] = {"title": title, "urgency": urgency.value, "dispatched": {}}

    # 1. Windows Toast
    if "toast" in target_channels or "all" in target_channels:
        toast_res = send_toast_notification(title, message, urgency=urgency, sound=sound)
        results["dispatched"]["toast"] = toast_res

    # 2. Discord Webhook
    if ("discord" in target_channels or "all" in target_channels):
        webhook_target = target_override if (target_override and str(target_override).startswith("http")) else cfg.get("discord_webhook")
        if webhook_target:
            disc_res = send_discord_notification(webhook_target, title, message, urgency=urgency)
            results["dispatched"]["discord"] = disc_res
        elif "discord" in target_channels:
            results["dispatched"]["discord"] = {"success": False, "error": "Discord webhook URL not configured."}

    # 3. Telegram Bot / Channel
    if ("telegram" in target_channels or "tg" in target_channels or "all" in target_channels):
        bot_tok = cfg.get("telegram_token")
        target_chat = target_override or cfg.get("telegram_chat_id")
        if bot_tok and target_chat:
            tele_res = send_telegram_notification(bot_tok, target_chat, title, message, urgency=urgency, image_path=image_path)
            results["dispatched"]["telegram"] = tele_res
        elif "telegram" in target_channels:
            missing = []
            if not bot_tok: missing.append("token")
            if not target_chat: missing.append("chat_id")
            results["dispatched"]["telegram"] = {"success": False, "error": f"Telegram missing: {', '.join(missing)}. Use /connect telegram <BOT_TOKEN> <CHAT_ID_OR_CHANNEL>."}

    # 4. Slack
    if ("slack" in target_channels or "all" in target_channels):
        slack_target = target_override if (target_override and str(target_override).startswith("http")) else cfg.get("slack_webhook")
        if slack_target:
            slack_res = send_slack_notification(slack_target, title, message, urgency=urgency)
            results["dispatched"]["slack"] = slack_res
        elif "slack" in target_channels:
            results["dispatched"]["slack"] = {"success": False, "error": "Slack webhook URL not configured."}

    # 5. Optional Neural Voice Alert
    if speak:
        def _speak_worker():
            try:
                from tools.voice import speak_text
                speak_text(f"Notice: {title}. {message}", async_mode=False)
            except Exception:
                pass
        threading.Thread(target=_speak_worker, daemon=True).start()

    results["success"] = any(r.get("success", False) for r in results["dispatched"].values()) or len(results["dispatched"]) == 0
    return results


def diagnose_channel(channel_name: str, target: Optional[str] = None) -> Dict[str, Any]:
    """
    Runs diagnostic inspection on a notification channel to report exact status,
    bot information, permissions, and remediation tips.
    """
    cfg = load_notification_config()
    chan = channel_name.lower()

    if chan in ("telegram", "tg"):
        from integrations.telegram_integration import TelegramIntegration
        tg = TelegramIntegration()
        token = cfg.get("telegram_token")
        if not token:
            return {
                "channel": "telegram",
                "connected": False,
                "error": "No Telegram Bot Token configured.",
                "solution": "1. Create a bot with @BotFather on Telegram.\n2. Run: /connect telegram <BOT_TOKEN> <CHAT_ID_OR_CHANNEL>",
            }

        chat_target = target or cfg.get("telegram_chat_id")
        if not chat_target:
            return {
                "channel": "telegram",
                "connected": tg.is_connected,
                "bot": tg.account_name,
                "error": "Bot token is valid, but no Chat ID / Channel is configured.",
                "solution": "• For a Telegram Channel: Set chat_id to @your_channel_name or -100xxxxxxxxxx.\n• Important: Add your bot as an Administrator to the channel with 'Post Messages' enabled!\n• For Private Chat: Send /start to your bot in Telegram and use your numeric user ID.",
            }

        diag = tg.diagnose_chat_or_channel(chat_target)
        return {
            "channel": "telegram",
            "connected": tg.is_connected,
            "bot": tg.account_name,
            "target": chat_target,
            "diagnosis": diag,
        }

    elif chan in ("discord",):
        url = target or cfg.get("discord_webhook")
        if not url:
            return {"channel": "discord", "connected": False, "error": "No Discord webhook URL configured."}
        return {"channel": "discord", "connected": True, "target": url[:30] + "..."}

    return {"channel": chan, "error": f"Unknown channel '{channel_name}'"}


# Backward compatibility alias
def send_webhook_notification(webhook_url: str, title: str, message: str) -> Dict[str, Any]:
    return send_discord_notification(webhook_url, title, message)

