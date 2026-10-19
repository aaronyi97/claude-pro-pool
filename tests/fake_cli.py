#!/usr/bin/env python3
"""Synthetic CLI boundary: never invokes an actual Claude client or credential API."""
import json
import os
from pathlib import Path
import shutil
import sys
import time

home = Path.home()
name = Path(sys.argv[0]).name
args = sys.argv[1:]
store = home / ".claude-swap-backup"
sequence = store / "sequence.json"


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


if name == "launchctl":
    marker = home / ".fake-launchctl"
    if args[0] == "print":
        sys.exit(0 if marker.exists() else 1)
    if args[0] == "bootstrap":
        marker.touch()
    elif args[0] == "bootout":
        marker.unlink(missing_ok=True)
    sys.exit(0)

if name == "osascript":
    with (home / "notifications.log").open("a") as out:
        out.write(args[-1] + "\n")
    sys.exit(0)

if name == "uv":
    root, bin_dir = Path(os.environ["UV_TOOL_DIR"]), Path(os.environ["UV_TOOL_BIN_DIR"])
    target = root / "claude-swap/bin"
    target.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for path, source in [(target / "python", sys.executable), (bin_dir / "claude-swap", __file__)]:
        if not path.exists():
            path.symlink_to(source)
    (target.parent / "pyvenv.cfg").touch()
    sys.exit(0)

if name == "claude-swap":
    if args == ["--version"]:
        print("claude-swap 0.26.0")
        sys.exit(0)
    seq = read(sequence, {"accounts": {}, "sequence": [], "activeAccountNumber": None})
    if args[0] == "list":
        default = read(home / ".fake-main", {})
        active = next((int(n) for n, a in seq["accounts"].items() if a["email"] == default.get("email")), None)
        rows = []
        policy = read(home / "fake-policy.json", {})
        for n, a in seq["accounts"].items():
            p = policy.get(n, {})
            rows.append(dict(number=int(n), alias=a["alias"], active=int(n) == active,
                             disabled=a.get("disabled", False), usageStatus=p.get("usageStatus", "ok"),
                             usage={"fiveHour": {"pct": p.get("h5", 10)},
                                    "sevenDay": {"pct": p.get("d7", 10), "resetsAt": p.get("reset", f"2030-01-{int(n):02d}T00:00:00Z")}}))
        print(json.dumps({"accounts": rows, "activeAccountNumber": active}))
    elif args[0] == "add":
        profile = Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else home
        identity = read(profile / ".fake-login", read(home / ".fake-main", {}))
        n = args[args.index("--slot") + 1]
        alias = args[args.index("--alias") + 1] if "--alias" in args else f"acc{n}"
        seq["accounts"][n] = dict(email=identity["email"], organizationUuid=identity.get("orgId", ""), alias=alias)
        seq["sequence"] = sorted(int(n) for n in seq["accounts"])
        seq["activeAccountNumber"] = int(n)
        write(sequence, seq)
    elif args[0] == "run":
        n = args[1]
        profile = store / "sessions" / f"{n}-profile"
        profile.mkdir(parents=True, exist_ok=True)
        if not (profile / ".claude.json").exists():
            write(profile / ".claude.json", {"synthetic": True})
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(profile), FAKE_ACCOUNT=n)
        os.execvpe("claude", ["claude", *args[args.index("--") + 1:]], env)
    elif args[0] in {"disable", "enable"}:
        seq["accounts"][args[1]]["disabled"] = args[0] == "disable"
        write(sequence, seq)
    elif args[0] == "remove":
        if input("Remove synthetic account? [y/N] ") == "y":
            seq["accounts"].pop(args[1])
            write(sequence, seq)
    else:
        sys.exit(2)
    sys.exit(0)

if name == "claude":
    if args == ["--version"]:
        print("Claude Code synthetic")
        sys.exit(0)
    profile = Path(os.environ.get("CLAUDE_CONFIG_DIR", home))
    if args[:2] == ["auth", "login"]:
        identity = read(home / "next-identity.json", {"loggedIn": True, "email": "identity-other", "orgId": ""})
        write(profile / ".fake-login", identity)
        sys.exit(0)
    if args[:2] == ["auth", "status"]:
        print(json.dumps(read(profile / ".fake-login", read(home / ".fake-main", {"loggedIn": False}))))
        sys.exit(0)
    n = os.environ["FAKE_ACCOUNT"]
    policy = read(home / "fake-policy.json", {}).get(n, {})
    if policy.get("delay"):
        time.sleep(policy["delay"])
    sid = args[args.index("--resume") + 1] if "--resume" in args else args[args.index("--session-id") + 1]
    record = profile / "projects/project" / f"{sid}.jsonl"
    if "--resume" in args and not record.exists():
        print("missing migrated transcript", file=sys.stderr)
        sys.exit(9)
    record.parent.mkdir(parents=True, exist_ok=True)
    with record.open("a") as out:
        out.write(json.dumps({"type": "assistant", "message": {"model": "synthetic", "content": [{"type": "thinking", "signature": "opaque-synthetic"}]}}) + "\n")
    side = record.parent / sid / "subagents"
    side.mkdir(parents=True, exist_ok=True)
    (side / "worker.jsonl").write_text("synthetic tool output")
    mode = policy.get("mode", "ok")
    model = args[args.index("--model") + 1] if "--model" in args else "synthetic-default"
    with (home / "invocations.jsonl").open("a") as out:
        out.write(json.dumps({"account": n, "args": args, "resume": "--resume" in args,
                              "forbidden_env": [k for k in ("CLAUDE_SECURESTORAGE_CONFIG_DIR", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_SESSION_ID") if k in os.environ]}) + "\n")
    print(json.dumps({"type": "system", "subtype": "init", "model": model}))
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "synthetic progress"}]}}))
    errors = {"limit": "You've hit your usage limit", "auth": "OAuth session expired",
              "terms": "Please accept our updated consumer terms", "transient": "API Error: 503 overloaded"}
    if mode == "stderr-auth":
        print("not logged in", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"type": "result", "is_error": mode != "ok", "result": errors.get(mode, "synthetic success"), "num_turns": 1}))
    sys.exit(1 if mode != "ok" else 0)

raise SystemExit("Unknown synthetic executable name")
