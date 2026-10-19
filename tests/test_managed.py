import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["CPP_TEST_ROOT"])
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.home), "CLAUDE_PRO_POOL_HOME": str(self.home / "pool")})
        self.env.start()
        spec = importlib.util.spec_from_file_location("pool", ROOT / "lib/pool.py")
        self.pool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.pool)
        self.m = self.pool.Managed()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_marked_install_twice_and_remove_restore_exact_bytes(self):
        path = self.home / "CLAUDE.md"
        original = b"# My settings\r\nCustom without final newline"
        path.write_bytes(original)
        self.m.block(path, "rules", "dispatch heavy work")
        self.m.block(path, "rules", "dispatch heavy work")
        self.assertEqual(path.read_text().count("BEGIN"), 1)
        self.m.restore()
        self.assertEqual(path.read_bytes(), original)

    def test_uninstall_keeps_user_edits_even_after_reinstall(self):
        path = self.home / "CLAUDE.md"
        path.write_text("User text")
        self.m.block(path, "rules", "dispatch heavy work")
        with path.open("a") as out:
            out.write("\nAdded after installation\n")
        self.m.block(path, "rules", "updated rule")
        self.m.restore()
        self.assertEqual(path.read_text(), "User text\nAdded after installation\n")

    def test_symlink_configuration_keeps_dotfiles_link(self):
        target = self.home / "dotfile"
        target.write_text("Original")
        path = self.home / "CLAUDE.md"
        path.symlink_to(target)
        self.m.block(path, "rules", "text")
        self.assertTrue(path.is_symlink())
        self.m.restore()
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(), "Original")

    def test_existing_directory_is_backed_up_and_restored(self):
        src, dst = self.home / "shared", self.home / "account-skills"
        src.mkdir()
        dst.mkdir()
        (dst / "mine.md").write_text("Keep me")
        self.m.link(src, dst)
        self.assertTrue(dst.is_symlink())
        self.m.restore()
        self.assertFalse(dst.is_symlink())
        self.assertEqual((dst / "mine.md").read_text(), "Keep me")

