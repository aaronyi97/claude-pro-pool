import json
from pathlib import Path
import unittest
from support import Sandbox


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.s.install()
        self.s.seed()
        self.s.env["CLAUDE_PRO_POOL_JOBS"] = str(self.s.home / "alternate-jobs")

    def tearDown(self):
        self.s.cleanup()

    def test_limit_auth_and_terms_switch_and_resume_original_record(self):
        for mode in ("limit", "auth", "terms", "stderr-auth"):
            with self.subTest(mode=mode):
                self.s.write("fake-policy.json", {"2": {"mode": mode}})
                self.s.dispatch("run", "--account", "2", "--prompt", "synthetic work")
                job = self.s.latest()
                self.assertEqual(job["status"], "done")
                self.assertEqual([r["account"] for r in job["rounds"]], [2, 3])
                self.assertTrue(job["rounds"][1]["moved_record"])
                self.assertEqual(job["rounds"][1]["kind"], "auto-continue")
                dest = self.s.home / ".claude-swap-backup/sessions/3-profile/projects/project" / job["session_id"]
                self.assertTrue((dest / "subagents/worker.jsonl").exists())
                self.assertTrue((self.s.jobs()[-1].parent / "completion.json").exists())
                # Explicit success on the same account clears cross-job cooldown.
                self.s.write("fake-policy.json", {})
                self.s.dispatch("run", "--account", "2", "--prompt", "reset cooldown")

    def test_ask_and_continue_keep_session_and_move_when_follow_threshold_exceeded(self):
        self.s.dispatch("run", "--prompt", "work")
        job = self.s.latest()
        sid, jid = job["session_id"], job["id"]
        self.s.dispatch("ask", jid, "--prompt", "follow-up")
        self.s.write("fake-policy.json", {"2": {"h5": 95}})
        self.s.dispatch("continue", jid)
        job = self.s.latest()
        self.assertEqual(job["session_id"], sid)
        self.assertEqual([r["account"] for r in job["rounds"]], [2, 2, 3])
        self.assertTrue(job["rounds"][-1]["moved_record"])
        self.assertIn("synthetic progress", self.s.dispatch("logs", jid))
        self.assertIn("完成", self.s.dispatch("status", jid))

    def test_unknown_usage_does_not_fall_back_to_main(self):
        self.s.write("fake-policy.json", {"2": {"usageStatus": "auth_error"}, "3": {"h5": 80}})
        self.s.dispatch("run", "--prompt", "work", code=3)
        self.assertEqual(self.s.latest()["status"], "no-account")
        self.assertFalse((self.s.home / "invocations.jsonl").exists())

    def test_inheritance_permission_configuration_and_identity_scrubbing(self):
        path = self.s.home / ".claude/projects/project/parent.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-opus-test"}}) + "\n")
        self.s.env.update({"CLAUDE_CODE_SESSION_ID": "parent", "CLAUDE_EFFORT": "max",
                           "CLAUDE_SECURESTORAGE_CONFIG_DIR": "synthetic-parent", "ANTHROPIC_API_KEY": "synthetic",
                           "ANTHROPIC_BASE_URL": "https://invalid.example", "CLAUDE_PRO_POOL_PERMISSION_MODE": "acceptEdits"})
        self.s.dispatch("run", "--prompt", "work")
        invocation = json.loads((self.s.home / "invocations.jsonl").read_text().splitlines()[-1])
        self.assertEqual(invocation["forbidden_env"], [])
        for option, value in [("--model", "claude-opus-test"), ("--effort", "max"), ("--permission-mode", "acceptEdits")]:
            self.assertEqual(invocation["args"][invocation["args"].index(option) + 1], value)

    def test_detach_wait_cancel_and_timeout(self):
        self.s.write("fake-policy.json", {"2": {"delay": 20}})
        self.s.dispatch("run", "--prompt", "work", "--no-wait")
        job = self.s.latest()
        self.s.dispatch("cancel", job["id"])
        self.s.dispatch("wait", job["id"], code=6)
        self.s.dispatch("run", "--prompt", "work", "--timeout", "1", code=5)
        job = self.s.latest()
        self.s.write("fake-policy.json", {})
        self.s.dispatch("continue", job["id"])
        self.assertEqual(self.s.latest()["status"], "done")

