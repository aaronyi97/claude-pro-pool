import json
import unittest
from support import Sandbox


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.s.install()
        self.s.seed(2)

    def tearDown(self):
        self.s.cleanup()

    def test_settings_memory_and_mcp_restore_without_losing_new_user_edits(self):
        s = self.s
        s.write(".claude/settings.json", {"custom": True})
        s.write(".claude.json", {"mcpServers": {"shared": {"command": "shared-cmd"}, "local": {"command": "main-cmd"}}})
        base = s.home / ".claude-swap-backup/sessions/2-profile"
        cfg = base / ".claude.json"
        original = {"synthetic": True, "mcpServers": {"local": {"command": "account-cmd"}}}
        cfg.write_text(json.dumps(original))
        memory = base / "projects/project/memory"
        memory.mkdir(parents=True)
        (memory / "fact.md").write_text("A durable fact")
        s.manage("sync")
        self.assertTrue((base / "settings.json").is_symlink())
        self.assertTrue(memory.is_symlink())
        data = json.loads(cfg.read_text())
        self.assertEqual(data["mcpServers"]["local"]["command"], "account-cmd")
        self.assertEqual(data["mcpServers"]["shared"]["command"], "shared-cmd")
        data["userEdit"] = "keep"
        cfg.write_text(json.dumps(data))
        s.manage("uninstall")
        self.assertFalse(memory.is_symlink())
        self.assertEqual((memory / "fact.md").read_text(), "A durable fact")
        self.assertEqual((s.home / ".claude/projects/project/memory/fact.md").read_text(), "A durable fact")
        data = json.loads(cfg.read_text())
        self.assertEqual(data["userEdit"], "keep")
        self.assertEqual(data["mcpServers"], original["mcpServers"])

    def test_conflicting_memory_is_left_in_place_and_reported(self):
        base = self.s.home / ".claude-swap-backup/sessions/2-profile/projects/project/memory"
        shared = self.s.home / ".claude/projects/project/memory"
        for path, content in [(base, "account"), (shared, "main")]:
            path.mkdir(parents=True)
            (path / "fact.md").write_text(content)
        self.assertIn("memory-CONFLICT", self.s.manage("sync"))
        self.assertFalse(base.is_symlink())
        self.assertEqual((base / "fact.md").read_text(), "account")
        self.assertIn("记忆无同步冲突", self.s.manage("doctor", code=1))

    def test_doctor_does_not_claim_stopped_service_or_bad_login_is_healthy(self):
        (self.s.home / ".fake-launchctl").unlink()
        self.s.write("fake-policy.json", {"2": {"usageStatus": "no_credentials"}})
        output = self.s.manage("doctor", code=1)
        self.assertIn("WARN 同步服务已加载", output)
        self.assertIn("reauth 2", output)

    def test_doctor_detects_profile_identity_mismatch_even_with_cached_quota(self):
        self.s.write(".claude-swap-backup/sessions/2-profile/.fake-login",
                     {"loggedIn": True, "email": "wrong-identity", "orgId": ""})
        output = self.s.manage("doctor", code=1)
        self.assertIn("未确认或身份不符", output)

