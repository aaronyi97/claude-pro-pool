import importlib.util
import json
import os
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from support import ROOT, Sandbox


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.s.install()
        self.s.seed(2)
        spec = importlib.util.spec_from_file_location("adapter", ROOT / "lib/swap_adapter.py")
        self.adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.adapter)

    def tearDown(self):
        self.s.cleanup()

    def test_adapter_uses_owned_sync_and_keeps_account_mcp(self):
        self.s.write(".claude.json", {"mcpServers": {"same": {"command": "main"}, "new": {"command": "new"}}})
        profile = self.s.home / ".claude-swap-backup/sessions/2-profile"
        (profile / ".claude.json").write_text(json.dumps({"mcpServers": {"same": {"command": "local"}}}))
        with patch.dict(os.environ, self.s.env, clear=True):
            self.adapter.pool_sharing(None, profile, True)
        data = json.loads((profile / ".claude.json").read_text())
        self.assertEqual(data["mcpServers"]["same"]["command"], "local")
        self.assertEqual(data["mcpServers"]["new"]["command"], "new")
        self.assertTrue((profile / "CLAUDE.md").is_symlink())

    def test_pinned_upstream_callback_is_replaced_without_vendoring(self):
        class Session:
            _sync_sharing = None
        called = []
        modules = {"claude_swap": ModuleType("claude_swap"),
                   "claude_swap.session": SimpleNamespace(SessionManager=Session),
                   "claude_swap.cli": SimpleNamespace(main=lambda: called.append(True))}
        with patch.dict(sys.modules, modules), patch.object(self.adapter.importlib.metadata, "version", return_value="0.26.0"):
            self.adapter.main()
        self.assertIs(Session._sync_sharing, self.adapter.pool_sharing)
        self.assertEqual(called, [True])

    def test_different_upstream_version_fails_closed(self):
        with patch.object(self.adapter.importlib.metadata, "version", return_value="0.27.0"):
            with self.assertRaises(RuntimeError):
                self.adapter.main()
