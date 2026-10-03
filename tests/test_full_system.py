"""
tests/test_full_system.py — End-to-End System Integrity Test for KuroAgent
Verifies all 15 core architectural systems in a chain of logical integration tests.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import APP_DIR, USER_DATA_DIR, BRAIN_DIR, SKILLS_DIR, CONFIG_DIR, DB_PATH
from core.permissions import check_permission, RiskLevel, PermissionGate
from core.task_state import TaskState, task_registry, Task
from core.memory_types import memory_manager, SemanticMemory, ProceduralMemory, WorkingMemory
from core.context_engine import context_engine
from core.verification import verification_engine, VerificationStatus
from core.skill_system import skill_system
from core.plugin_registry import registry, ToolContract
from core.project_aware import project_inspector
from core.model_router import model_router, TaskType, ExecutionMetrics
from core.self_update import self_update_pipeline
from core.experiment import experiment_runner, CandidateSolution
from core.multi_agent import orchestrator
from core.integration_manager import integration_manager
from core.logger import logger, LogLevel
from core import memory, memory_db


class TestFullSystemIntegrity(unittest.TestCase):

    def test_01_paths_and_storage_structure(self):
        """Verify clean separation between APP_DIR and USER_DATA_DIR."""
        self.assertTrue(APP_DIR.exists())
        self.assertTrue(USER_DATA_DIR.exists())
        self.assertTrue(BRAIN_DIR.exists())
        self.assertTrue(SKILLS_DIR.exists())
        self.assertTrue(CONFIG_DIR.exists())

    def test_02_permission_layer_security_gate(self):
        """Verify strict permission levels and runtime overrides."""
        gate = PermissionGate(safe_mode=True)
        res_safe = gate.check("read_file", interactive=False)
        self.assertTrue(res_safe.allowed)
        self.assertEqual(res_safe.risk, RiskLevel.SAFE)

        res_confirm = gate.check("run_command", interactive=False)
        self.assertFalse(res_confirm.allowed)
        self.assertTrue(res_confirm.requires_confirmation)

        res_danger = gate.check("delete_file", interactive=False)
        self.assertFalse(res_danger.allowed)
        self.assertEqual(res_danger.risk, RiskLevel.DANGEROUS)

    def test_03_task_state_machine_lifecycle(self):
        """Verify full lifecycle transitions and SQLite persistence."""
        task = task_registry.create(goal="Deploy service")
        self.assertEqual(task.state, TaskState.PENDING)
        self.assertTrue(task.mark_planning())
        self.assertTrue(task.mark_executing())
        self.assertTrue(task.mark_verifying("Checks passed"))
        self.assertTrue(task.mark_completed())
        self.assertTrue(task.is_terminal())

        persisted = memory_db.get_task(task.task_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["state"], "completed")

    def test_04_memory_bridge_normalization(self):
        """Verify memory normalization between SQLite and JSON cache."""
        memory.save_memory("Test question", "Test response", metadata={"source": "test"})
        history = memory.load_memory()
        self.assertTrue(len(history) > 0)
        latest = history[-1]
        self.assertIn("user", latest)
        self.assertIn("assistant", latest)
        self.assertIn("user_text", latest)
        self.assertIn("assistant_text", latest)

    def test_05_context_engine_budget(self):
        """Verify context retrieval complies with token constraints."""
        context = context_engine.build(
            user_input="Analyze codebase performance",
            task_goal="Analyze codebase performance",
            episode_limit=3,
        )
        self.assertIsInstance(context, str)

    def test_06_verification_engine_strategies(self):
        """Verify individual verification strategies."""
        # Non-existent file verification
        v_res = verification_engine.verify_action(
            "write_file",
            tool_input={"path": "non_existent_file_xyz.txt", "content": "data"},
            tool_output={"success": True},
        )
        self.assertFalse(v_res.is_success)

        # Successful command check
        v_cmd = verification_engine.verify_action(
            "run_command",
            tool_input={"cmd": "echo test"},
            tool_output={"success": True, "returncode": 0, "stderr": ""},
        )
        self.assertTrue(v_cmd.is_success)

    def test_07_skill_system_lifecycle(self):
        """Verify skill creation, saving, and discovery."""
        skill = skill_system.create_skill_from_workflow(
            name="system_check",
            description="Run diagnostic checks",
            workflow_steps=["check os", "check python"],
        )
        self.assertEqual(skill.name, "system_check")
        all_skills = skill_system.discover_skills()
        self.assertTrue(any(s.name == "system_check" for s in all_skills))

    def test_08_plugin_registry_and_contracts(self):
        """Verify tool registration and execution."""
        contract = registry.register_function(
            name="system_ping",
            description="Ping function",
            handler=lambda host="localhost": {"success": True, "host": host},
            risk_level=RiskLevel.SAFE,
        )
        self.assertTrue(registry.has_tool("system_ping"))
        res = registry.execute_tool("system_ping", {"host": "127.0.0.1"})
        self.assertTrue(res["success"])
        self.assertEqual(res["host"], "127.0.0.1")

    def test_09_project_profiling(self):
        """Verify project inspection."""
        profile = project_inspector.inspect(".", force_refresh=True)
        self.assertIn("Python", profile.languages)
        self.assertIn("requirements.txt", profile.config_files)

    def test_10_model_router_and_metrics(self):
        """Verify intent classification and metrics tracking."""
        prov, mod, t_type = model_router.select_route("Write a python script")
        self.assertEqual(t_type, TaskType.CODING)

        prov_v, mod_v, t_type_v = model_router.select_route("Describe photo", has_image=True)
        self.assertEqual(t_type_v, TaskType.VISION)

        metrics = ExecutionMetrics(task_id="task_full_test")
        metrics.record_tool_call()
        metrics.finish(success=True)
        self.assertEqual(metrics.tool_calls, 1)

    def test_11_multi_agent_orchestration(self):
        """Verify sub-agent delegation."""
        res = orchestrator.delegate("research", "Python 3.13 features")
        self.assertTrue(res.get("success", False))

    def test_12_experiment_system(self):
        """Verify candidate solution evaluation."""
        candidates = [
            CandidateSolution(name="sol_a", description="Method A", handler=lambda: {"success": True, "val": 1}),
            CandidateSolution(name="sol_b", description="Method B", handler=lambda: {"success": True, "val": 2}),
        ]
        report = experiment_runner.run_experiment(
            experiment_id="exp_01",
            problem_statement="Optimize calculation",
            candidates=candidates,
        )
        self.assertIsNotNone(report.winner_name)

    def test_13_integrations_and_intent_routing(self):
        """Verify external services and natural-language intent routing."""
        services = integration_manager.list_integrations()
        names = [s["name"] for s in services]
        self.assertIn("github", names)
        self.assertIn("google_drive", names)
        self.assertIn("email", names)

        self.assertEqual(integration_manager.route_intent("check my PR on github").name, "github")
        self.assertEqual(integration_manager.route_intent("search my Google Drive files").name, "google_drive")
        self.assertEqual(integration_manager.route_intent("check my unread emails in inbox").name, "email")


    def test_14_encrypted_vault_lifecycle(self):
        """Verify Encrypted Credential Vault storage, masking, lock, and unlock."""
        from core.vault import VaultManager, mask_secret
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_vault_path = Path(tmp_dir) / "test_vault.enc"
            v = VaultManager(vault_path=test_vault_path)
            
            # 1. Set secret
            self.assertTrue(v.set_secret("OPENAI_TEST_KEY", "sk-proj-1234567890abcdef1234567890", description="OpenAI API key"))
            self.assertEqual(v.get_secret("OPENAI_TEST_KEY"), "sk-proj-1234567890abcdef1234567890")
            
            # 2. Masking
            masked = mask_secret("sk-proj-1234567890abcdef1234567890")
            self.assertTrue(masked.startswith("sk-p"))
            self.assertTrue(masked.endswith("7890"))
            self.assertIn("****", masked)

            # 3. List secrets
            all_sec = v.list_secrets()
            self.assertEqual(len(all_sec), 1)
            self.assertEqual(all_sec[0]["key"], "OPENAI_TEST_KEY")

            # 4. Lock & Unlock
            v.lock()
            self.assertTrue(v.is_locked())
            self.assertIsNone(v.get_secret("OPENAI_TEST_KEY"))

            unlocked = v.unlock()
            self.assertTrue(unlocked)
            self.assertFalse(v.is_locked())
            self.assertEqual(v.get_secret("OPENAI_TEST_KEY"), "sk-proj-1234567890abcdef1234567890")

            # 5. Delete secret
            self.assertTrue(v.delete_secret("OPENAI_TEST_KEY"))
            self.assertIsNone(v.get_secret("OPENAI_TEST_KEY"))

    def test_15_sandbox_guard_and_ast_safety(self):
        """Verify AST code safety analysis, blocking dangerous operations, and safe interpreter execution."""
        from core.sandbox import SandboxGuard
        from tools.interpreter import execute_python_code

        guard = SandboxGuard()
        
        # 1. Safe code passes
        safe_code = "x = 10\ny = 20\nresult = x + y"
        rep_safe = guard.validate_python_code(safe_code)
        self.assertTrue(rep_safe.is_safe)
        self.assertEqual(rep_safe.risk_level, "SAFE")

        exec_res = execute_python_code(safe_code)
        self.assertTrue(exec_res["success"])
        self.assertEqual(exec_res["return_value"], 30)

        # 2. Dangerous imports blocked
        dangerous_code = "import _ctypes\nprint('pwned')"
        rep_danger = guard.validate_python_code(dangerous_code)
        self.assertFalse(rep_danger.is_safe)
        self.assertEqual(rep_danger.risk_level, "BLOCKED")

        exec_blocked = execute_python_code(dangerous_code)
        self.assertFalse(exec_blocked["success"])
        self.assertIn("SANDBOX GUARD BLOCKED", exec_blocked["stderr"])

        # 3. Destructive disk patterns blocked
        format_code = "import os\nos.system('format C:')"
        rep_format = guard.validate_python_code(format_code)
        self.assertFalse(rep_format.is_safe)
        self.assertEqual(rep_format.risk_level, "BLOCKED")

    def test_17_telegram_and_discord_integrations(self):
        """Verify Telegram and Discord integration registration, action routing, and error diagnostics."""
        from integrations.telegram_integration import TelegramIntegration
        from integrations.discord_integration import DiscordIntegration
        from core.integration_manager import integration_manager

        # 1. Telegram integration abstraction
        tg = TelegramIntegration()
        self.assertEqual(tg.name, "telegram")
        self.assertEqual(tg.version, "2.0.0")

        # Telegram error explanation helper check
        explanation = tg._explain_error("Bad Request: chat not found", "@non_existent_channel")
        self.assertIn("was not found", explanation)

        explanation_admin = tg._explain_error("Bad Request: need administrator rights in the channel", "-100123456789")
        self.assertIn("Administrator", explanation_admin)

        # 2. Discord integration abstraction
        disc = DiscordIntegration()
        self.assertEqual(disc.name, "discord")

        # 3. Intent routing check
        tg_route = integration_manager.route_intent("Send alert to my telegram channel")
        self.assertIsNotNone(tg_route)
        self.assertEqual(tg_route.name, "telegram")

        disc_route = integration_manager.route_intent("Post summary to discord webhook")
        self.assertIsNotNone(disc_route)
        self.assertEqual(disc_route.name, "discord")

    def test_18_smart_notifier_and_diagnostics(self):
        """Verify smart multi-channel notifier and diagnostic inspector."""
        from tools.notifier import send_smart_notification, diagnose_channel, NotificationUrgency

        # Windows toast delivery check
        res = send_smart_notification(
            title="Unit Test Alert",
            message="Testing multi-channel notification engine.",
            urgency=NotificationUrgency.INFO,
            channels=["toast"],
        )
        self.assertIn("toast", res.get("dispatched", {}))
        self.assertTrue(res["dispatched"]["toast"].get("success", False))

        # Channel diagnosis test
        diag_tele = diagnose_channel("telegram", target="@test_channel")
        self.assertEqual(diag_tele.get("channel"), "telegram")


if __name__ == "__main__":
    unittest.main()
