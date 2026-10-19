#!/usr/bin/env python3
"""Installation, enrollment, diagnostics and reversible shared configuration."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HOME = Path.home()
STATE = Path(os.environ.get("CLAUDE_PRO_POOL_HOME", HOME / ".claude-pro-pool")).expanduser().resolve()
SOURCE = Path(__file__).resolve().parents[1]
CONFIG = HOME / ".claude"
SWAP_ROOT = HOME / ".claude-swap-backup"
SESSIONS = SWAP_ROOT / "sessions"
LABEL = "io.github.claude-pro-pool.sync"
PLIST = HOME / "Library/LaunchAgents" / f"{LABEL}.plist"
BIN = HOME / ".local/bin"
SHARED = ["settings.json", "settings.local.json", "keybindings.json", "CLAUDE.md", "skills",
          "commands", "agents", "rules", "output-styles", "plugins/installed_plugins.json",
          "plugins/known_marketplaces.json"]
IDENTITY_ENV = {"CLAUDE_CONFIG_DIR", "CLAUDE_SECURESTORAGE_CONFIG_DIR", "CLAUDE_CODE_SESSION_ID",
                "CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY",
                "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS",
                "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR"}


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def write_bytes(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pool-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, data):
    write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def exists(path):
    return os.path.lexists(path)


def remove(path):
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def fingerprint(path):
    path = Path(path)
    if path.is_symlink():
        return "link:" + os.readlink(path)
    if path.is_file():
        return "file:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return "directory" if path.is_dir() else "missing"


class Managed:
    """Record originals before mutation; never overwrite later user changes."""
    def __init__(self):
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = STATE / "managed.json"
        self.data = read_json(self.path, {"entries": {}, "created_dirs": []})

    def save(self):
        write_json(self.path, self.data)

    def mkdir(self, path):
        path = Path(path)
        missing = []
        while not path.exists():
            missing.append(path)
            path = path.parent
        for item in reversed(missing):
            item.mkdir(mode=0o700)
            self.data["created_dirs"].append(str(item))
        self.save()

    def remember(self, path, kind="file"):
        path = Path(path).absolute()
        key = str(path)
        if key not in self.data["entries"]:
            entry = {"path": key, "kind": kind, "original": exists(path)}
            if exists(path):
                backup = STATE / "backups" / uuid.uuid4().hex
                backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if path.is_symlink():
                    backup.symlink_to(os.readlink(path))
                elif path.is_dir():
                    shutil.copytree(path, backup, symlinks=True)
                else:
                    shutil.copy2(path, backup)
                entry["backup"] = str(backup)
            self.data["entries"][key] = entry
            self.save()
        return self.data["entries"][key]

    def snapshot(self, path):
        """Retain the immediate pre-change version, including edits after install."""
        path = Path(path)
        if not exists(path) or not path.is_file() or path.is_symlink():
            return
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        target = STATE / "backups/versions" / digest
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, target)

    def link(self, src, dest):
        src, dest = Path(src), Path(dest)
        if dest.is_symlink() and dest.resolve() == src.resolve():
            return
        entry = self.remember(dest)
        if entry.get("installed") and fingerprint(dest) != entry["installed"]:
            raise RuntimeError(f"同步目标已被用户替换，保留原样：{dest}；手工合并后再 sync")
        self.mkdir(dest.parent)
        # Track intention before mutation, so an interrupted install is reversible.
        entry["installed"] = "link:" + str(src)
        self.save()
        remove(dest)
        dest.symlink_to(src, target_is_directory=src.is_dir())

    def file(self, dest, content, mode=0o600):
        dest = Path(dest)
        if exists(dest) and dest.read_bytes() == content:
            return
        entry = self.remember(dest)
        if entry.get("installed") and fingerprint(dest) != entry["installed"]:
            raise RuntimeError(f"保留用户修改，未覆盖：{dest}；请先手动合并")
        self.mkdir(dest.parent)
        entry["installed"] = "file:" + hashlib.sha256(content).hexdigest()
        self.save()
        self.snapshot(dest)
        write_bytes(dest, content, mode)

    def block(self, path, tag, body):
        path = Path(path)
        if path.is_symlink():
            path = path.resolve()
        start, end = f"<!-- claude-pro-pool:{tag}:BEGIN -->", f"<!-- claude-pro-pool:{tag}:END -->"
        if tag == "path":
            start, end = f"# claude-pro-pool:{tag}:BEGIN", f"# claude-pro-pool:{tag}:END"
        content = path.read_bytes() if path.exists() else b""
        old_content = content
        pattern = re.compile(rb"\n\n" + re.escape(start.encode()) + rb".*?" + re.escape(end.encode()) + rb"\n", re.S)
        if content.count(start.encode()) != content.count(end.encode()):
            raise RuntimeError(f"标记块不完整，请修复后重试：{path}")
        if start.encode() in content and not pattern.search(content):
            raise RuntimeError(f"标记块已被移动，请先移除该块后重试：{path}")
        entry = self.remember(path, "block")
        new = f"\n\n{start}\n{body.rstrip()}\n{end}\n".encode()
        content = pattern.sub(b"", content) + new
        entry.update(start=start, end=end)
        self.mkdir(path.parent)
        self.save()
        if content != old_content:
            self.snapshot(path)
            write_bytes(path, content, path.stat().st_mode & 0o777 if path.exists() else 0o600)

    def restore(self):
        conflicts = []
        for key, entry in reversed(list(self.data["entries"].items())):
            path = Path(key)
            if entry["kind"] == "block":
                if not path.exists():
                    self.data["entries"].pop(key, None)
                    continue
                content = path.read_bytes()
                pattern = re.compile(rb"\n\n" + re.escape(entry["start"].encode()) + rb".*?" + re.escape(entry["end"].encode()) + rb"\n", re.S)
                cleaned = pattern.sub(b"", content)
                if cleaned == content and entry["start"].encode() in content:
                    conflicts.append(key)
                    continue
                if not entry["original"] and not cleaned:
                    path.unlink()
                else:
                    self.snapshot(path)
                    write_bytes(path, cleaned, path.stat().st_mode & 0o777)
            elif fingerprint(path) == entry.get("installed"):
                remove(path)
                if entry["original"]:
                    backup = Path(entry["backup"])
                    if backup.is_symlink():
                        path.symlink_to(os.readlink(backup))
                    elif backup.is_dir():
                        shutil.copytree(backup, path, symlinks=True)
                    else:
                        shutil.copy2(backup, path)
            elif exists(path):
                conflicts.append(key)
                continue
            self.data["entries"].pop(key, None)
        for directory in reversed(self.data["created_dirs"]):
            try:
                Path(directory).rmdir()
            except OSError:
                pass
        self.save()
        return conflicts


def clean_env(profile=None):
    env = {k: v for k, v in os.environ.items() if k not in IDENTITY_ENV}
    env["PATH"] = str(STATE / "deps/bin") + os.pathsep + env.get("PATH", "")
    if profile:
        env["CLAUDE_CONFIG_DIR"] = str(profile)
    # The management parent holds .manage.lock while waiting on upstream.
    env["CLAUDE_PRO_POOL_MANAGE_LOCK_HELD"] = "1"
    return env


def swap():
    return os.environ.get("CLAUDE_PRO_POOL_SWAP") or str(STATE / "runtime/bin/pool-swap")


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def account_data():
    if not (SWAP_ROOT / "sequence.json").exists():
        return {"accounts": [], "activeAccountNumber": None}
    result = run([swap(), "list", "--json"], env=clean_env(), capture_output=True, text=True, timeout=120)
    data = json.loads(result.stdout)
    if not isinstance(data.get("accounts"), list):
        raise RuntimeError("claude-swap 返回了无效账号表")
    return data


def service_loaded():
    result = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    return result.returncode == 0


def install_service(m):
    env = {"HOME": str(HOME), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "CLAUDE_PRO_POOL_HOME": str(STATE)}
    spec = {"Label": LABEL, "ProgramArguments": [sys.executable, "-I", str(SOURCE / "lib/pool.py"), "sync"],
            "RunAtLoad": True, "StartInterval": 300, "EnvironmentVariables": env,
            "WatchPaths": [str(SWAP_ROOT / "sequence.json"), str(SESSIONS)],
            "StandardOutPath": str(STATE / "sync.log"), "StandardErrorPath": str(STATE / "sync.log")}
    m.file(PLIST, plistlib.dumps(spec))
    if service_loaded():
        run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    result = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
    if result.returncode:
        print("WARN 同步服务未加载（例如没有 GUI 登录会话）；图形桌面中运行 claude-pro-pool sync-service。")


def install():
    if sys.platform != "darwin":
        raise RuntimeError("首版安装仅支持 macOS；Linux/Windows 暂不支持")
    m = Managed()
    import shlex
    adapter = ("#!/bin/sh\nexport CLAUDE_PRO_POOL_HOME=" + shlex.quote(str(STATE)) +
               "\nexec " + shlex.quote(sys.executable) + " -I " + shlex.quote(str(SOURCE / "lib/swap_adapter.py")) + ' "$@"\n')
    write_bytes(SOURCE / "bin/pool-swap", adapter.encode(), 0o755)
    m.block(CONFIG / "CLAUDE.md", "rules", (SOURCE / "templates/CLAUDE.md").read_text())
    m.link(SOURCE / "skills/claude-pro-pool", CONFIG / "skills/claude-pro-pool")
    for command in ("claude-pro-pool", "dispatch-claude"):
        # A shell wrapper pins the private Python and relocatable runtime.
        script = ("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -I " +
                  shlex.quote(str(SOURCE / ("lib/pool.py" if command == "claude-pro-pool" else "bin/dispatch-claude"))) + ' "$@"\n')
        script = script.replace("\nexec ", "\nexport CLAUDE_PRO_POOL_HOME=" + shlex.quote(str(STATE)) + "\nexec ")
        m.file(BIN / command, script.encode(), 0o755)
    for name in (".zshrc", ".bashrc", ".bash_profile"):
        m.block(HOME / name, "path", 'export PATH="$HOME/.local/bin:$PATH"')
    cfg = STATE / "config.json"
    if not cfg.exists():
        write_json(cfg, {"permission_mode": "bypassPermissions", "desktop_notifications": True})
    install_service(m)
    sync()
    print('安装完成。当前终端执行：export PATH="$HOME/.local/bin:$PATH"')
    print("下一步：claude-pro-pool add-account --current（登记已登录主号），再逐个 add-account 登录其余账号。")


def sync():
    m = Managed()
    warnings = []
    for profile in sorted(SESSIONS.glob("[0-9]*-*")):
        if not profile.is_dir() or profile.is_symlink():
            continue
        for name in SHARED:
            source = CONFIG / name
            if source.exists():
                m.link(source.resolve(), profile / name)
        projects = profile / "projects"
        if projects.is_dir() and not projects.is_symlink():
            for project in projects.iterdir():
                memory = project / "memory"
                shared = CONFIG / "projects" / project.name / "memory"
                if not project.is_dir() or project.is_symlink():
                    continue
                if memory.is_symlink() and memory.resolve() == shared.resolve():
                    continue
                if memory.is_dir() and not memory.is_symlink():
                    if any(p.is_symlink() for p in memory.rglob("*")):
                        warnings.append(f"memory-CONFLICT: {profile.name}/{project.name}: 含符号链接，保留原目录")
                        continue
                    files = [p for p in memory.rglob("*") if p.is_file() and not p.is_symlink()]
                    conflicts = [p.relative_to(memory) for p in files if (shared / p.relative_to(memory)).exists()
                                 and p.read_bytes() != (shared / p.relative_to(memory)).read_bytes()]
                    if conflicts:
                        warnings.append(f"memory-CONFLICT: {profile.name}/{project.name}: {len(conflicts)} 个文件；原目录保留")
                        continue
                    for path in files:
                        target = shared / path.relative_to(memory)
                        if not target.exists():
                            m.mkdir(target.parent)
                            # New merged memories are user data and survive uninstall.
                            shutil.copy2(path, target)
                m.mkdir(shared)
                m.link(shared, memory)
        # Only mcpServers is shared; no whole-profile or credential-file copying.
        main_config = CONFIG / ".config.json" if (CONFIG / ".config.json").exists() else HOME / ".claude.json"
        servers = (read_json(main_config, {}) or {}).get("mcpServers", {})
        target = profile / ".claude.json"
        if target.exists() and servers:
            data = read_json(target, {})
            missing = {k: v for k, v in servers.items() if k not in data.get("mcpServers", {})}
            if missing:
                entry = m.remember(target, "mcp")
                # Record only our additions; uninstall preserves other profile updates.
                entry.setdefault("added_mcp", {}).update(missing)
                m.save()
                data.setdefault("mcpServers", {}).update(missing)
                m.snapshot(target)
                write_json(target, data)
    write_json(STATE / "sync-status.json", {"at": time.time(), "warnings": warnings})
    for warning in warnings:
        print(warning)
    print(f"sync: 完成，{len(warnings)} 项需人工合并")


def auth_status(profile=None):
    result = run(["claude", "auth", "status"], env=clean_env(profile), capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)
    if not data.get("loggedIn"):
        raise RuntimeError("未登录；请运行 claude auth login，再登记主号，或重试 add-account")
    return data


def add_account(args):
    # The official clients handle credential storage. Never inspect tokens here.
    profile = None
    if not args.current:
        profile = STATE / "enrollment" / uuid.uuid4().hex
        profile.mkdir(parents=True, mode=0o700)
        print("请在浏览器中登录准备加入的另一个 Pro/Max 账号。不要在这里登录正在运行主对话的账号。", flush=True)
        run(["claude", "auth", "login", "--claudeai"], env=clean_env(profile))
    identity = auth_status(profile)
    seq = read_json(SWAP_ROOT / "sequence.json", {"accounts": {}})
    matching = [int(n) for n, a in seq.get("accounts", {}).items()
                if a.get("email") == identity.get("email") and a.get("organizationUuid", "") == (identity.get("orgId") or "")]
    if matching:
        print(f"该账号已在号池 acc{matching[0]}，未重复添加。重登现有账号请用 reauth。")
        return
    number = args.slot if args.slot is not None else (max([int(n) for n in seq.get("accounts", {})] + [0]) + 1)
    if number < 1 or str(number) in seq.get("accounts", {}):
        raise RuntimeError("目标编号已占用或无效；未覆盖任何账号")
    print(f"登录核对：{identity.get('email', '(CLI 未返回身份)')}；将保存为 acc{number}", flush=True)
    if not args.current and input("确认这是要加入的账号？[y/N] ").strip().lower() != "y":
        print("已取消。临时登录目录保留；不清除任何登录凭据。")
        return
    command = [swap(), "add", "--slot", str(number), "--alias", args.alias or f"acc{number}"]
    run(command, env=clean_env(profile))
    if not args.current:
        # --version initializes the isolated profile without making a model request.
        run([swap(), "run", str(number), "--", "--version"], env=clean_env(profile), capture_output=True)
    sync()
    print(f"acc{number} 已加入。运行 claude-pro-pool doctor 检查额度；可继续 add-account 加下一个号。")


def busy_account(number):
    # Import the dispatcher without executing its command interface.
    import runpy
    d = runpy.run_path(str(SOURCE / "bin/dispatch-claude"), run_name="pool_dispatch")
    directory = d["account_dir"](number)
    return (bool(directory and d["interactive_count"](directory)) or
            bool(d["running_jobs_by_account"]().get(number)))


def reauth(args):
    if busy_account(args.number):
        raise RuntimeError("该号仍有交互会话或派单；先结束它们再重登")
    seq = read_json(SWAP_ROOT / "sequence.json", {})
    old = seq.get("accounts", {}).get(str(args.number))
    if not old:
        raise RuntimeError("账号编号不存在")
    profile = STATE / "enrollment" / uuid.uuid4().hex
    profile.mkdir(parents=True, mode=0o700)
    print("请在浏览器中登录该编号原来的账号。", flush=True)
    run(["claude", "auth", "login", "--claudeai"], env=clean_env(profile))
    identity = auth_status(profile)
    if identity.get("email") != old.get("email") or (identity.get("orgId") or "") != old.get("organizationUuid", ""):
        raise RuntimeError("账号身份不符，未覆盖原编号")
    run([swap(), "add", "--slot", str(args.number)], env=clean_env(profile))
    run([swap(), "run", str(args.number), "--", "--version"], env=clean_env(profile), capture_output=True)
    sync()


def doctor():
    issues = 0
    def check(ok, label, action):
        nonlocal issues
        issues += not ok
        print(("OK   " if ok else "WARN ") + label + ("" if ok else " → " + action))
    check(bool(shutil.which("claude")), "Claude CLI", "安装官方 Claude Code CLI 后重新运行 doctor")
    uv = STATE / "deps/uv/uv"
    check(uv.exists() or bool(shutil.which("uv")), "uv", "重新运行 bash ./install.sh")
    private = STATE / "deps/tools/claude-swap/pyvenv.cfg"
    check(private.exists(), "claude-swap 0.26.0 私有依赖", "重新运行 bash ./install.sh")
    try:
        result = run([swap(), "--version"], env=clean_env(), capture_output=True, text=True, timeout=15)
        check(bool(re.search(r"\b0\.26\.0\b", result.stdout)), "claude-swap 版本 0.26.0", "重新安装固定版本依赖")
    except (OSError, subprocess.SubprocessError):
        check(False, "claude-swap 无法运行", "重新运行安装命令")
    rule = CONFIG / "CLAUDE.md"
    check(rule.exists() and "claude-pro-pool:rules:BEGIN" in rule.read_text(), "主对话规则块", "重新运行安装命令")
    check((CONFIG / "skills/claude-pro-pool/SKILL.md").is_file(), "派单 skill", "重新运行安装命令")
    check(PLIST.exists() and service_loaded(), "同步服务已加载", "在 GUI 登录会话中运行 claude-pro-pool sync-service")
    sync_state = read_json(STATE / "sync-status.json", {})
    check(time.time() - sync_state.get("at", 0) < 660, "最近 11 分钟同步成功", "运行 claude-pro-pool sync；查看 sync.log")
    check(not sync_state.get("warnings"), "记忆无同步冲突", "查看 sync.log，合并 memory-CONFLICT 后运行 sync")
    try:
        data = account_data()
        accounts = data["accounts"]
        check(bool(accounts), f"号池：{len(accounts)} 个号" if accounts else "还没有号", "先 add-account --current，再 add-account")
        import runpy
        d = runpy.run_path(str(SOURCE / "bin/dispatch-claude"), run_name="pool_dispatch")
        rows = d["evaluate"](data, d["caller_account"](data.get("activeAccountNumber")))
        for a, row in zip(accounts, rows):
            usage_ok = a.get("usageStatus") == "ok"
            print(f"{'OK  ' if usage_ok else 'WARN'} acc{a['number']} 登录/额度={a.get('usageStatus')} "
                  f"5h={row['h5']}% 7d={row['d7']}%：{'、'.join(row['why']) or '可派单'}")
            if not usage_ok:
                issues += 1
                print(f"     → claude-pro-pool reauth {a['number']}；条款问题需本人在 claude.ai 同意")
        check(bool(d["rank"](rows)), "有可自动派单账号", "增加其余账号；额度不足请等待重置，停用号可 enable")
    except (OSError, ValueError, subprocess.SubprocessError, SystemExit) as exc:
        check(False, "无法读取号池（未假装额度正常）", f"运行 dispatch-claude accounts；错误类型 {type(exc).__name__}")
    print(f"doctor: {issues} 项需处理" if issues else "doctor: 正常")
    return 1 if issues else 0


def uninstall():
    jobs = Path(os.environ.get("CLAUDE_PRO_POOL_JOBS", STATE / "jobs")).expanduser()
    for meta in jobs.glob("*/meta.json"):
        job = read_json(meta, {})
        if job.get("status") in {"queued", "running"}:
            raise RuntimeError("仍有未结束任务；先用 dispatch-claude cancel/wait 结束任务再卸载")
    m = Managed()
    if service_loaded():
        run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    # Remove only MCP entries we inserted and that users have not subsequently changed.
    for key, entry in list(m.data["entries"].items()):
        if entry["kind"] != "mcp":
            continue
        path = Path(key)
        if path.exists():
            data = read_json(path, {})
            for name, value in entry["added_mcp"].items():
                if data.get("mcpServers", {}).get(name) == value:
                    del data["mcpServers"][name]
            original = read_json(entry["backup"], {})
            if "mcpServers" not in original and not data.get("mcpServers"):
                data.pop("mcpServers", None)
            if data == original:
                shutil.copy2(entry["backup"], path)
            else:
                m.snapshot(path)
                write_json(path, data)
        m.data["entries"].pop(key)
    m.save()
    conflicts = m.restore()
    if conflicts:
        print("已保留安装后发生修改的文件及原备份，请手工核对：\n" + "\n".join(conflicts))
        return 1
    # Unique data and login state are intentionally retained. Private deps are disposable.
    for name in ("runtime", "deps", "cache", "backups", "managed.json", "config.json", "sync.log", "sync-status.json", ".manage.lock"):
        remove(STATE / name)
    try:
        (STATE / "jobs").rmdir()
    except OSError:
        pass
    try:
        STATE.rmdir()
    except OSError:
        pass
    print("已卸载命令、规则、skill、同步链接、服务与私有依赖。账号登录、任务记录及合并的记忆保留。")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="claude-pro-pool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("install", "doctor", "sync", "sync-service", "accounts", "uninstall"):
        sub.add_parser(name)
    add = sub.add_parser("add-account")
    add.add_argument("--current", action="store_true")
    add.add_argument("--slot", type=int)
    add.add_argument("--alias")
    for name in ("disable", "enable", "remove", "reauth"):
        sub.add_parser(name).add_argument("number", type=int)
    args = ap.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(STATE / ".manage.lock", "a") as lock:
        # Serialize journal changes, enrollment and periodic sync.
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.cmd == "doctor":
            return doctor()
        if args.cmd == "install":
            install()
        elif args.cmd == "sync":
            sync()
        elif args.cmd == "sync-service":
            install_service(Managed())
        elif args.cmd == "add-account":
            add_account(args)
        elif args.cmd == "reauth":
            reauth(args)
        elif args.cmd == "accounts":
            run([BIN / "dispatch-claude", "accounts"])
        elif args.cmd in {"disable", "enable", "remove"}:
            if args.cmd == "remove" and busy_account(args.number):
                raise RuntimeError("该号仍有交互会话或派单，先结束后再移除")
            run([swap(), args.cmd, str(args.number)], env=clean_env())
        elif args.cmd == "uninstall":
            return uninstall()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        # Do not print captured CLI output: it can contain authorization material.
        print(f"claude-pro-pool: {error if isinstance(error, RuntimeError) else type(error).__name__}；需要时查看官方 CLI 的本地诊断。", file=sys.stderr)
        sys.exit(2)
