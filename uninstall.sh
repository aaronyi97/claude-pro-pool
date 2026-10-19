#!/bin/bash
set -euo pipefail
pool_state="${CLAUDE_PRO_POOL_HOME:-$HOME/.claude-pro-pool}"
if [ ! -f "$pool_state/runtime/lib/pool.py" ]; then
  echo '没有找到 claude-pro-pool 安装。'
  exit 0
fi
exec "$pool_state/deps/tools/claude-swap/bin/python" -I "$pool_state/runtime/lib/pool.py" uninstall
