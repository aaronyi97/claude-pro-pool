import os
from pathlib import Path
import tarfile
import unittest

from support import Sandbox


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()

    def tearDown(self):
        self.s.cleanup()

    def test_clean_home_install_add_reinstall_and_uninstall(self):
        self.assertFalse((self.s.home / ".claude").exists())
        self.s.install()
        self.assertIn("还没有号", self.s.manage("doctor", code=1))
        self.s.seed(2)
        self.assertIn("doctor: 正常", self.s.manage("doctor"))
        self.s.install()
        rules = self.s.home / ".claude/CLAUDE.md"
        self.assertEqual(rules.read_text().count("rules:BEGIN"), 1)
        self.s.manage("uninstall")
        self.assertFalse((self.s.home / ".local/bin/claude-pro-pool").exists())
        self.assertFalse((self.s.home / ".local/bin/dispatch-claude").exists())
        self.assertFalse(rules.exists())
        self.assertFalse((self.s.home / ".claude/skills/claude-pro-pool").exists())
        self.assertFalse((self.s.home / "Library/LaunchAgents/io.github.claude-pro-pool.sync.plist").exists())
        self.assertFalse((self.s.home / ".claude-pro-pool/deps").exists())
        self.assertTrue((self.s.home / ".claude-swap-backup/sequence.json").exists())
        self.s.run(["bash", "./uninstall.sh"])

    def test_existing_files_are_identical_after_uninstall(self):
        files = {".claude/CLAUDE.md": b"Custom instructions\r\nNo final newline", ".zshrc": b"# my shell\n",
                 ".bashrc": b"# bash", ".claude/settings.json": b'{"custom": true}\n',
                 ".local/bin/dispatch-claude": b"#!/bin/sh\necho custom\n"}
        for name, data in files.items():
            path = self.s.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.s.install()
        self.s.install()
        self.s.manage("uninstall")
        for name, data in files.items():
            self.assertEqual((self.s.home / name).read_bytes(), data)
        self.assertFalse((self.s.home / ".claude-pro-pool").exists())

    def test_main_login_not_required_for_install(self):
        self.s.install()
        output = self.s.manage("add-account", "--current", code=2)
        self.assertIn("未登录", output)

    def test_duplicate_and_wrong_slot_do_not_overwrite(self):
        self.s.install()
        self.s.seed(2)
        self.assertIn("未重复添加", self.s.add(2))
        self.s.write("next-identity.json", {"loggedIn": True, "email": "new-identity", "orgId": ""})
        self.assertIn("未覆盖", self.s.manage("add-account", "--slot", "1", input="y\n", code=2))

    def test_pipe_installer_downloads_repository_archive(self):
        from support import ROOT
        archive = self.s.home / "repository.tar.gz"
        with tarfile.open(archive, "w:gz") as out:
            for name in ("bin", "lib", "templates", "skills"):
                out.add(ROOT / name, arcname=f"claude-pro-pool-main/{name}")
        curl = self.s.bin / "curl"
        import shlex
        curl.write_text("#!/bin/sh\ncase \"$2\" in\n" +
                        "https://github.com/3918109465-beep/claude-pro-pool/archive/refs/heads/main.tar.gz)\n" +
                        "cp " + shlex.quote(str(archive)) + ' "$4";;\n*) exit 9;;\nesac\n')
        curl.chmod(0o755)
        output = self.s.run(["bash"], input=(ROOT / "install.sh").read_text())
        self.assertIn("安装完成", output)
        self.assertIn("还没有号", self.s.manage("doctor", code=1))

    def test_custom_state_path_with_spaces_is_pinned_in_installed_wrappers(self):
        custom = self.s.home / "custom pool"
        self.s.env["CLAUDE_PRO_POOL_HOME"] = str(custom)
        self.s.install()
        del self.s.env["CLAUDE_PRO_POOL_HOME"]
        self.assertIn("还没有号", self.s.manage("doctor", code=1))
        self.s.manage("uninstall")
        self.assertFalse(custom.exists())


@unittest.skipUnless(os.environ.get("CPP_REAL_INSTALL") == "1", "set CPP_REAL_INSTALL=1 for official network dependency installation")
class RealInstallTests(unittest.TestCase):
    def test_official_uv_bootstrap_and_pinned_dependency_in_clean_home(self):
        s = Sandbox(real_uv=True)
        try:
            output = s.install()
            self.assertIn("安装完成", output)
            python = s.home / ".claude-pro-pool/deps/tools/claude-swap/bin/python"
            version = s.run([python, "-I", "-c", "import importlib.metadata; print(importlib.metadata.version('claude-swap'))"])
            self.assertEqual(version.strip(), "0.26.0")
            adapter = s.home / ".claude-pro-pool/runtime/bin/pool-swap"
            self.assertIn("0.26.0", s.run([adapter, "--version"]))
            self.assertIn("还没有号", s.manage("doctor", code=1))
            s.seed(2)
            self.assertIn("doctor: 正常", s.manage("doctor"))
            s.install()
            s.manage("uninstall")
            self.assertFalse((s.home / ".claude-pro-pool/deps").exists())
            print("REAL INSTALL: official uv + Python + claude-swap 0.26.0, doctor, synthetic enrollment, reinstall, uninstall PASS")
        finally:
            s.cleanup()
