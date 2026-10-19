import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


class Sandbox:
    def __init__(self, real_uv=False):
        self.tmp = tempfile.TemporaryDirectory(prefix="home-", dir=os.environ["CPP_TEST_ROOT"])
        self.home = Path(self.tmp.name)
        self.bin = self.home / "fake-bin"
        self.bin.mkdir()
        self.env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin:/usr/sbin:/sbin",
                    "TMPDIR": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        # Absolute interpreter avoids relying on macOS' optional system Python.
        fake = self.home / "fake-cli.py"
        fake.write_text(f"#!{sys.executable}\n" + (ROOT / "tests/fake_cli.py").read_text().split("\n", 1)[1])
        fake.chmod(0o755)
        for name in ("claude", "launchctl", "osascript", *( () if real_uv else ("uv",) )):
            (self.bin / name).symlink_to(fake)
        # Not on PATH: initial state genuinely has no claude-swap command.
        self.swap = self.home / "synthetic/claude-swap"
        self.swap.parent.mkdir()
        self.swap.symlink_to(fake)
        self.env["CLAUDE_PRO_POOL_SWAP"] = str(self.swap)
        self.main = {"loggedIn": True, "email": "identity-main", "orgId": ""}

    def write(self, relative, obj):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj))

    def run(self, args, code=0, input=None, timeout=180, cwd=None):
        result = subprocess.run([str(a) for a in args], env=self.env, cwd=cwd or ROOT, input=input,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode != code:
            raise AssertionError(f"command {args}: expected {code}, got {result.returncode}\n{result.stdout}")
        return result.stdout

    def install(self):
        return self.run(["bash", "./install.sh"])

    def manage(self, *args, **kwargs):
        return self.run([self.home / ".local/bin/claude-pro-pool", *args], **kwargs)

    def dispatch(self, *args, **kwargs):
        return self.run([self.home / ".local/bin/dispatch-claude", *args], **kwargs)

    def add(self, number):
        self.write("next-identity.json", {"loggedIn": True, "email": f"identity-{number}", "orgId": ""})
        return self.manage("add-account", input="y\n")

    def seed(self, count=3):
        self.write(".fake-main", self.main)
        self.manage("add-account", "--current")
        for n in range(2, count + 1):
            self.add(n)

    def jobs(self):
        root = Path(self.env.get("CLAUDE_PRO_POOL_JOBS", self.home / ".claude-pro-pool/jobs"))
        return sorted(root.glob("*/meta.json"))

    def latest(self):
        return json.loads(self.jobs()[-1].read_text())

    def cleanup(self):
        self.tmp.cleanup()
