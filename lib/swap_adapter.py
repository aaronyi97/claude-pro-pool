"""Use upstream auth/isolation while this project owns reversible sharing.

No upstream source is vendored. This small integration is pinned to 0.26.0's
SessionManager callback and fails closed on a different installed version.
"""
import fcntl
import importlib.metadata
from pathlib import Path
import os
import runpy


def pool_sharing(self, session_dir, share, share_history=False):
    if not share or share_history:
        raise RuntimeError("pool adapter supports managed sharing only")
    pool = runpy.run_path(str(Path(__file__).with_name("pool.py")), run_name="pool_adapter")
    # Enrollment's parent holds the lock and is synchronously waiting for us.
    if os.environ.get("CLAUDE_PRO_POOL_MANAGE_LOCK_HELD") == "1":
        pool["sync"]()
    else:
        with open(pool["STATE"] / ".manage.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            pool["sync"]()


def main():
    if importlib.metadata.version("claude-swap") != "0.26.0":
        raise RuntimeError("pool adapter requires claude-swap==0.26.0")
    from claude_swap.session import SessionManager
    from claude_swap.cli import main as upstream_main
    SessionManager._sync_sharing = pool_sharing
    upstream_main()


if __name__ == "__main__":
    main()
