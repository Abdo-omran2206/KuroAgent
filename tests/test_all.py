"""
Master Integration & Regression Test Suite for KURO 2.0.
Verifies all core modules, tools, brain database, personality engine, and system features.
"""

import sys
import os
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Suppress pygame startup banner during tests
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"


class TestKuroCore(unittest.TestCase):

    def test_01_config_and_brain_paths(self):
        from core import config
        self.assertTrue(config.BASE_DIR.exists())
        self.assertTrue(config.BRAIN_DIR.exists())
        self.assertEqual(config.MEMORY_FILE, config.BRAIN_DIR / "memory.json")
        self.assertEqual(config.PERSONALITY_FILE, config.BRAIN_DIR / "personality.md")

    def test_02_memory_db_sqlite(self):
        from core import memory_db
        memory_db.init_db()
        
        # Test chat entry save & retrieve
        row_id = memory_db.save_chat_entry("Test prompt", "Test response", {"test": True})
        self.assertGreater(row_id, 0)
        
        history = memory_db.get_chat_history(limit=5)
        self.assertGreater(len(history), 0)
        
        # Test summary save & retrieve
        memory_db.save_conversation_summary("Summary test point 1")
        summary = memory_db.get_latest_summary()
        self.assertIsNotNone(summary)
        
        # Test trait setting
        memory_db.set_personality_trait("unit_test", "passed")
        traits = memory_db.get_personality()
        self.assertEqual(traits.get("unit_test"), "passed")

    def test_03_personality_engine(self):
        from core import personality
        p_text = personality.load_personality()
        self.assertIn("KURO", p_text)
        
        sys_prompt = personality.get_system_personality_prompt()
        self.assertIn("PERSISTENT PERSONALITY PROFILE", sys_prompt)

    def test_04_memory_module(self):
        from core import memory
        memory.save_memory("Test question", "Test answer")
        ctx = memory.get_formatted_context(limit=2)
        self.assertTrue(len(ctx) > 0)

    def test_05_task_planner(self):
        from tools.planner import create_task_plan, get_active_plan, format_plan_table
        plan = create_task_plan("Build test pipeline")
        self.assertIsNotNone(plan.get("id"))
        self.assertIn(plan.get("status"), ("pending", "in_progress"))
        
        formatted = format_plan_table(plan)
        self.assertIn("Task Plan", formatted)

    def test_06_files_and_sql_tools(self):
        from tools.files import execute_sql_query, write_md_note, read_file
        
        # SQL test
        res = execute_sql_query("brain/kuro.db", "SELECT 1 AS test_val;")
        self.assertTrue(res.get("success"))
        self.assertEqual(res["rows"][0]["test_val"], 1)
        
        # MD note test
        note_res = write_md_note("brain/notes/test_note.md", "Test Note", "Body of test note")
        self.assertTrue(note_res.get("success"))
        
        read_res = read_file("brain/notes/test_note.md")
        self.assertTrue(read_res.get("success"))
        self.assertIn("Body of test note", read_res["content"])

    def test_07_voice_catalog(self):
        from tools.voice import list_available_voices, set_voice_name, get_active_voice
        voices = list_available_voices()
        self.assertIn("ava", voices)
        self.assertIn("andrew", voices)
        
        ok, msg = set_voice_name("andrew")
        self.assertTrue(ok)
        self.assertIn("ANDREW", get_active_voice().upper())

    def test_08_hotkey_listener(self):
        from tools.hotkey import start_global_hotkey_listener, stop_global_hotkey_listener
        started = start_global_hotkey_listener()
        if sys.platform == "win32":
            self.assertTrue(started)
        stop_global_hotkey_listener()

    def test_09_notifier_tool(self):
        from tools.notifier import send_toast_notification
        res = send_toast_notification("KURO Test", "Unit test notification")
        if sys.platform == "win32":
            self.assertTrue(res.get("success"))

    def test_10_db_explorer_tool(self):
        from tools.db_explorer import explore_database
        res_tables = explore_database("brain/kuro.db", op="list_tables")
        self.assertTrue(res_tables.get("success"))
        self.assertGreater(len(res_tables.get("tables", [])), 0)

        res_schema = explore_database("brain/kuro.db", op="export_schema")
        self.assertTrue(res_schema.get("success"))
        self.assertIn("Database Schema Summary", res_schema.get("schema_md", ""))

    def test_11_browser_automation_tool(self):
        from tools.web_browser import automate_browser
        res = automate_browser("https://example.com")
        self.assertTrue(res.get("success"))

    def test_12_agent_self_access_and_schemas(self):
        from core.agent import KuroAgent
        agent = KuroAgent()
        sys_ctx = agent._build_system_context()
        self.assertIn("FULL ACCESS and self-modification authority", sys_ctx)
        self.assertIn("send_notification", sys_ctx)
        self.assertIn("inspect_db", sys_ctx)
        self.assertIn("automate_browser", sys_ctx)


if __name__ == "__main__":
    unittest.main(verbosity=2)
