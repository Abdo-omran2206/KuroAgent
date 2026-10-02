"""
Verification test script for tools/hotkey.py
Tests start_global_hotkey_listener, focus_kuro_window, stop_hotkey_listener, and get_system_power_status
in both headless and GUI environments.
"""

import sys
import os
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.hotkey import (
    start_global_hotkey_listener,
    focus_kuro_window,
    stop_hotkey_listener,
    get_system_power_status,
)


def test_hotkey_module():
    print("1. Testing focus_kuro_window()...")
    res = focus_kuro_window()
    print(f"   focus_kuro_window() returned: {res} (No exception raised)")

    print("2. Testing get_system_power_status()...")
    pstatus = get_system_power_status()
    print(f"   get_system_power_status() returned: {pstatus}")
    assert isinstance(pstatus, dict)
    assert "available" in pstatus
    assert "ac_online" in pstatus

    triggered = False

    def on_trigger_cb():
        nonlocal triggered
        triggered = True
        print("   on_trigger callback invoked!")

    print("3. Testing start_global_hotkey_listener()...")
    started = start_global_hotkey_listener(on_trigger=on_trigger_cb)
    print(f"   start_global_hotkey_listener() returned: {started}")

    time.sleep(0.5)

    print("4. Testing stop_hotkey_listener()...")
    stop_hotkey_listener()
    print("   stop_hotkey_listener() executed successfully")

    print("\n--- ALL HOTKEY MODULE TESTS PASSED ---")


if __name__ == "__main__":
    test_hotkey_module()
