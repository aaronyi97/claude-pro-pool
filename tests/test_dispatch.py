"""Behavioral tests; all profiles, records and subprocesses are synthetic."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_dispatch():
    path = ROOT / "bin/dispatch-claude"
    loader = importlib.machinery.SourceFileLoader("dispatch", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["CPP_TEST_ROOT"])
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {
            "HOME": str(self.home), "CLAUDE_PRO_POOL_JOBS": str(self.home / "alternate-jobs"),
        })
        self.env.start()
        self.d = load_dispatch()
        self.d.require_jobs()
        self.d.SESS.mkdir(parents=True)
        for n in range(1, 10):
            (self.d.SESS / f"{n}-profile").mkdir()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def account(self, n, h5=10, d7=20, reset="2030-01-02T00:00:00Z", **extra):
        return dict(number=n, alias=f"acc{n}", active=n == 1, usageStatus="ok",
                    usage={"fiveHour": {"pct": h5}, "sevenDay": {"pct": d7, "resetsAt": reset}}, **extra)

    def test_jobs_are_overridable(self):
        self.assertEqual(self.d.JOBS, self.home / "alternate-jobs")

    def test_selection_excludes_main_busy_disabled_unknown_and_thresholds(self):
        data = {"activeAccountNumber": 1, "accounts": [
            self.account(1), self.account(2), self.account(3, disabled=True),
            self.account(4, h5=80), self.account(5, d7=95), self.account(6), self.account(7),
        ]}
        data["accounts"][-1]["usageStatus"] = "auth_error"
        with patch.object(self.d, "interactive_count", side_effect=lambda p: int(Path(p).name == "6-profile")):
            self.assertEqual([r["num"] for r in self.d.rank(self.d.evaluate(data, 1))], [2])

    def test_rank_load_then_early_weekly_reset_then_hourly_usage(self):
        data = {"accounts": [self.account(2, h5=5), self.account(3, h5=40, reset="2030-01-01T00:00:00Z"),
                             self.account(4, h5=1, reset="2029-01-01T00:00:00Z")]}
        with patch.object(self.d, "running_jobs_by_account", return_value={4: 1}):
            self.assertEqual([r["num"] for r in self.d.rank(self.d.evaluate(data, 1))], [3, 2, 4])

    def test_follow_holds_until_follow_threshold_and_explicit_override(self):
        data = {"accounts": [self.account(2, h5=94, d7=98), self.account(3)]}
        job = {"holder": 2, "caller_account": 1}
        with patch.object(self.d, "fetch_accounts", return_value=data):
            self.assertEqual(self.d.choose(job, False)[0]["num"], 2)
            data["accounts"][0]["usage"]["fiveHour"]["pct"] = 95
            self.assertEqual(self.d.choose(job, False)[0]["num"], 3)
            job["force_next"] = 2
            self.assertEqual(self.d.choose(job, False)[0]["num"], 2)

    def test_cooldown_expires_and_success_clears(self):
        self.d.mark_bad(2, "terms")
        self.assertIn("2", self.d.bad_accounts())
        with patch.object(self.d.time, "time", return_value=10**12):
            self.assertNotIn("2", self.d.bad_accounts())
        self.d.clear_bad(2)
        self.assertNotIn("2", self.d.bad_accounts())

    def test_migration_preserves_transcript_and_sidecars(self):
        src, dst, sid = self.home / "src", self.home / "dst", "synthetic-session"
        for relative in [f"projects/project/{sid}.jsonl", f"projects/project/{sid}/subagents/a.jsonl",
                         f"file-history/{sid}/f", f"session-env/{sid}/vars"]:
            path = src / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'opaque signed thinking and tool output\n')
        self.assertTrue(self.d.migrate(sid, src, dst))
        for path in src.rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (dst / path.relative_to(src)).read_bytes())

    def test_inherits_model_with_pretty_json_and_latest_model_command(self):
        cfg, sid = self.home / ".claude", "parent-session"
        path = cfg / "projects/project" / f"{sid}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-opus-test"}}) + "\n")
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(cfg), "CLAUDE_CODE_SESSION_ID": sid}):
            self.assertEqual(self.d.inherited_model(), "claude-opus-test")
            with path.open("a") as out:
                out.write(json.dumps({"type": "system", "content": "<local-command-stdout>Set model to `sonnet`</local-command-stdout>"}) + "\n")
            self.assertEqual(self.d.inherited_model(), "sonnet")

    def test_job_identifier_cannot_escape_jobs_root(self):
        with self.assertRaises(SystemExit):
            self.d.job_dir("../outside")

