"""
KURO Global Hotkey & System Power Listener Module
Provides zero-dependency Win32 global hotkey handling (Ctrl+Shift+K / Ctrl+Alt+K) via ctypes RegisterHotKey
and window focus capabilities (GetConsoleWindow, SetForegroundWindow, ShowWindow).
Also includes system power status monitoring via Win32 API (GetSystemPowerStatus).
Handles headless environments and non-Windows operating systems gracefully without throwing exceptions.
"""

import sys
import os
import ctypes
from ctypes import wintypes
import threading
import time
from typing import Callable, Optional, Dict, Any

# ─────────────────────────────────────────────────────────
# Win32 API Constants
# ─────────────────────────────────────────────────────────
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
VK_K = 0x4B
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_REMOVE = 0x0001

HOTKEY_ID_CTRL_SHIFT_K = 1001
HOTKEY_ID_CTRL_ALT_K = 1002

_hotkey_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_is_listening = False


# ─────────────────────────────────────────────────────────
# Win32 Power Status Struct
# ─────────────────────────────────────────────────────────
class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def focus_kuro_window() -> bool:
    """
    Brings KURO's console/terminal window to the foreground using Win32 API.
    Uses GetConsoleWindow, ShowWindow, and SetForegroundWindow.
    Falls back to EnumWindows searching for visible process windows if GetConsoleWindow returns 0.
    Returns True if a window was focused, False otherwise.
    Does not throw exceptions if running headlessly or without UI.
    """
    if sys.platform != "win32":
        return False

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. Primary approach: GetConsoleWindow
        hwnd = kernel32.GetConsoleWindow()

        # 2. Fallback: Search visible top-level windows for current process or parent process
        if not hwnd:
            pid = os.getpid()
            ppid = os.getppid() if hasattr(os, "getppid") else None

            found_hwnds = []

            def enum_proc(h, _):
                if user32.IsWindowVisible(h):
                    w_pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(w_pid))
                    if w_pid.value == pid or (ppid and w_pid.value == ppid):
                        found_hwnds.append(h)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            user32.EnumWindows(WNDENUMPROC(enum_proc), 0)

            if found_hwnds:
                hwnd = found_hwnds[0]

        if not hwnd:
            return False

        SW_RESTORE = 9
        SW_SHOW = 5

        # Check if window is minimized (iconic)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        # Bring window to front
        user32.SetForegroundWindow(hwnd)
        return True

    except Exception:
        return False


def get_system_power_status() -> Dict[str, Any]:
    """
    Returns current Windows system power & battery status using Win32 API GetSystemPowerStatus.
    Returns a dict with ac_online, battery_percent, charging, etc.
    Returns safe default values on error, headless setups, or non-Windows platforms.
    """
    if sys.platform != "win32":
        return {
            "available": False,
            "ac_online": True,
            "battery_percent": None,
            "charging": False,
        }

    try:
        status = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            ac_online = status.ACLineStatus == 1
            percent = status.BatteryLifePercent if status.BatteryLifePercent != 255 else None
            charging = bool(status.BatteryFlag & 8)
            return {
                "available": True,
                "ac_online": ac_online,
                "battery_percent": percent,
                "charging": charging,
                "ac_line_status_raw": status.ACLineStatus,
                "battery_flag_raw": status.BatteryFlag,
            }
    except Exception:
        pass

    return {
        "available": False,
        "ac_online": True,
        "battery_percent": None,
        "charging": False,
    }


def _hotkey_loop(on_trigger: Optional[Callable] = None):
    """
    Background worker loop that registers global Windows hotkeys (Ctrl+Shift+K / Ctrl+Alt+K)
    using Win32 ctypes RegisterHotKey, with a non-blocking PeekMessageW message loop.
    Falls back to the `keyboard` module if RegisterHotKey fails or is unavailable.
    """
    if sys.platform != "win32":
        return

    registered = False
    reg_shift = False
    reg_alt = False
    user32 = None

    try:
        user32 = ctypes.windll.user32

        # Try RegisterHotKey for Ctrl + Shift + K
        res_shift = user32.RegisterHotKey(
            None, HOTKEY_ID_CTRL_SHIFT_K, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_K
        )
        if res_shift:
            reg_shift = True

        # Try RegisterHotKey for Ctrl + Alt + K
        res_alt = user32.RegisterHotKey(
            None, HOTKEY_ID_CTRL_ALT_K, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_K
        )
        if res_alt:
            reg_alt = True

        registered = reg_shift or reg_alt
    except Exception:
        registered = False

    if registered and user32:
        msg = wintypes.MSG()
        try:
            while not _stop_event.is_set():
                # PeekMessageW is non-blocking when PM_REMOVE is specified
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY and msg.wParam in (
                        HOTKEY_ID_CTRL_SHIFT_K,
                        HOTKEY_ID_CTRL_ALT_K,
                    ):
                        focus_kuro_window()
                        if on_trigger:
                            try:
                                on_trigger()
                            except Exception:
                                pass
                    elif msg.message == WM_QUIT:
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.05)
        finally:
            try:
                if reg_shift:
                    user32.UnregisterHotKey(None, HOTKEY_ID_CTRL_SHIFT_K)
                if reg_alt:
                    user32.UnregisterHotKey(None, HOTKEY_ID_CTRL_ALT_K)
            except Exception:
                pass
    else:
        # Fallback to keyboard package if RegisterHotKey is unavailable
        try:
            import keyboard

            def handle_trigger():
                focus_kuro_window()
                if on_trigger:
                    try:
                        on_trigger()
                    except Exception:
                        pass

            h1 = None
            h2 = None
            try:
                h1 = keyboard.add_hotkey("ctrl+shift+k", handle_trigger)
            except Exception:
                pass
            try:
                h2 = keyboard.add_hotkey("ctrl+alt+k", handle_trigger)
            except Exception:
                pass

            while not _stop_event.is_set():
                time.sleep(0.05)

            if h1:
                try:
                    keyboard.remove_hotkey(h1)
                except Exception:
                    pass
            if h2:
                try:
                    keyboard.remove_hotkey(h2)
                except Exception:
                    pass
        except Exception:
            # Gracefully ignore if running in headless environment without UI or keyboard privileges
            pass


def start_global_hotkey_listener(on_trigger: Optional[Callable] = None) -> bool:
    """
    Launches daemon thread listening for Windows hotkey (Ctrl + Shift + K or Ctrl + Alt + K).
    Returns True if thread started or is already running, False on unsupported platforms or error.
    """
    global _hotkey_thread, _is_listening

    if sys.platform != "win32":
        return False

    if _hotkey_thread and _hotkey_thread.is_alive():
        return True

    _stop_event.clear()
    _hotkey_thread = threading.Thread(
        target=_hotkey_loop,
        args=(on_trigger,),
        name="KuroHotkeyListenerThread",
        daemon=True,
    )
    try:
        _hotkey_thread.start()
        _is_listening = True
        return True
    except Exception:
        return False


def stop_hotkey_listener():
    """Stops global hotkey listener thread."""
    global _is_listening
    _stop_event.set()
    _is_listening = False


def stop_global_hotkey_listener():
    """Alias for stop_hotkey_listener()."""
    stop_hotkey_listener()
