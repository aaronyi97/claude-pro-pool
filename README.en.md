# claude-pro-pool

Keep your main Claude Code conversation focused on coordination. Dispatch heavy work to your other personal Pro/Max subscriptions, run headless in the background, and resume the same transcript on another account if a limit is reached.

**Requires macOS, Claude Code CLI, and two or more personal Pro/Max subscriptions.** Linux and Windows installation are not supported in this release. No preinstalled claude-swap or Python is required.

```bash
git clone https://github.com/aaronyi97/claude-pro-pool.git
cd claude-pro-pool
bash ./install.sh
export PATH="$HOME/.local/bin:$PATH"
claude-pro-pool add-account --current
claude-pro-pool add-account
claude-pro-pool doctor
```

Log into your usual main account first with `claude auth login` if needed. The second command opens the official browser login for another account and asks you to verify the identity. Repeat for further accounts. Or install with one line:

```bash
curl -fsSL https://raw.githubusercontent.com/aaronyi97/claude-pro-pool/main/install.sh | bash
```

Start a new normal `claude` conversation. Installed rules request automatic delegation of heavy reading, code inspection, tests and scripting. Model behavior is not guaranteed. The main conversation runs `dispatch-claude run --prompt-file /absolute/task.md` using its Bash tool's background mode; leave the dispatcher's default wait enabled so the tool delivers completion. Detached terminal jobs can use `--no-wait`, then `wait JOB`. Desktop notifications are best effort.

Commands: `accounts`, `run`, `ask`, `continue`, `wait`, `status`, `logs`, `cancel`. Management: `add-account`, `reauth N`, `disable N`, `enable N`, `remove N`, `doctor`, `sync`, `sync-service`, `uninstall`. See [command reference](docs/commands.md) and [Chinese guide](README.md).

Automatic selection excludes the caller, default account, interactive sessions, disabled accounts and unknown usage. New work needs under 80% five-hour and 95% weekly usage. Rank by running job count, earliest weekly reset, then lowest five-hour usage. Follow-ups stay on the current account below 95%/99%. Limits, authentication and terms errors trigger bounded migration/resumption. Explicit `--account N` overrides selection protections.

Without `--model`, the dispatcher reads the parent transcript to inherit its model. `CLAUDE_EFFORT` supplies effort. An explicit agent controls unspecified model/effort. Unavailable parent-model information produces a warning and uses Claude's configured default.

**Default permission mode is `bypassPermissions`: headless workers skip operation approval and can execute commands and change accessible files.** Use only trusted tasks. Set `CLAUDE_PRO_POOL_PERMISSION_MODE=acceptEdits` or `default` for narrower approval behavior; headless permission requests may fail. Existing Claude settings are not overwritten.

Jobs default to `~/.claude-pro-pool/jobs`; override with `CLAUDE_PRO_POOL_JOBS`. Shared rules, skills, settings, project memory and missing user MCP definitions synchronize through a launchd agent. Credentials and complete conversation histories remain separate. Account migration copies only the job's transcript and sidecars.

A small adapter pinned to 0.26.0 replaces upstream's sharing callback with the reversible project synchronizer. Upstream still handles authentication, storage, usage and isolation; its source is not modified or vendored. Validate the adapter before upgrading the dependency.

Install is repeatable and backs up existing managed files. Uninstall with `claude-pro-pool uninstall` or `bash ./uninstall.sh`. It removes commands, marked blocks, service, links and private dependencies; retains user changes, account/login data, enrollment profiles, job records and merged memories. Conflicts are reported with backups retained.

Each account is the user's own regular subscription with normal login. This tool only allocates local tasks between accounts. Users must determine compliance with Anthropic's terms themselves.

Depends on [claude-swap 0.26.0](https://github.com/realiti4/claude-swap), installed separately through [uv](https://docs.astral.sh/uv/getting-started/installation/). No upstream source is vendored. [MIT license](LICENSE).
