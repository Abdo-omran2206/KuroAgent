import subprocess
import os
import platform
import json
import urllib.request
from typing import Dict, Any, Optional

def send_toast_notification(title: str, message: str) -> Dict[str, Any]:
    """
    Sends a native Windows Toast Notification using PowerShell.
    No external pip packages required.
    """
    if platform.system() != "Windows":
        return {"success": False, "error": "Toast notifications are only supported on Windows OS."}

    # Escape quotes for PowerShell script
    title_escaped = title.replace('"', '`"').replace("'", "''")
    msg_escaped = message.replace('"', '`"').replace("'", "''")

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $template = @"
    <toast>
        <visual>
            <binding template="ToastGeneric">
                <text id="1">{title_escaped}</text>
                <text id="2">{msg_escaped}</text>
            </binding>
        </visual>
    </toast>
"@

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("KURO System Assistant")
    $notifier.Show($toast)
    """

    try:
        process = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        if process.returncode == 0:
            return {"success": True, "title": title, "message": message, "method": "windows_toast"}
        else:
            # Fallback to msg command or basic PowerShell notify icon
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
            return {"success": True, "title": title, "message": message, "method": "windows_balloon_fallback"}

    except Exception as e:
        return {"success": False, "error": f"Notification failed: {str(e)}"}


def send_webhook_notification(webhook_url: str, title: str, message: str) -> Dict[str, Any]:
    """Sends a push notification payload to a Discord or generic webhook URL."""
    payload = {
        "embeds": [{
            "title": f"🤖 KURO: {title}",
            "description": message,
            "color": 3447003
        }]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json", "User-Agent": "KURO-Assistant/2.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"success": resp.status in (200, 204), "status": resp.status}
    except Exception as e:
        return {"success": False, "error": str(e)}
