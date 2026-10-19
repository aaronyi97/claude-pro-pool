#!/bin/bash
set -euo pipefail
umask 077
if [ "$(uname -s)" != Darwin ]; then
  echo 'claude-pro-pool 首版仅支持 macOS。' >&2
  exit 2
fi
pool_state="${CLAUDE_PRO_POOL_HOME:-$HOME/.claude-pro-pool}"
mkdir -p "$pool_state"
pool_state="$(cd "$pool_state" && pwd)"
export CLAUDE_PRO_POOL_HOME="$pool_state"
export TMPDIR="$pool_state/cache/tmp"
mkdir -p "$TMPDIR"
pool_stage="$(mktemp -d "$TMPDIR/install.XXXXXX")"
trap 'rm -rf "$pool_stage"' EXIT
pool_source=''
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  pool_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -z "$pool_source" ] || [ ! -f "$pool_source/lib/pool.py" ]; then
  curl -fsSL https://github.com/aaronyi97/claude-pro-pool/archive/refs/heads/main.tar.gz -o "$pool_stage/source.tar.gz"
  tar -xzf "$pool_stage/source.tar.gz" -C "$pool_stage"
  pool_source="$pool_stage/claude-pro-pool-main"
fi
# Use private directories; never replace a user's global uv tools or shell setup.
pool_uv="$(command -v uv || true)"
if [ -z "$pool_uv" ]; then
  pool_uv="$pool_state/deps/uv/uv"
  if [ ! -x "$pool_uv" ]; then
    curl -fsSL https://astral.sh/uv/install.sh -o "$pool_stage/uv-install.sh"
    UV_UNMANAGED_INSTALL="$pool_state/deps/uv" sh "$pool_stage/uv-install.sh"
  fi
fi
export UV_TOOL_DIR="$pool_state/deps/tools"
export UV_TOOL_BIN_DIR="$pool_state/deps/bin"
export UV_PYTHON_INSTALL_DIR="$pool_state/deps/python"
export UV_CACHE_DIR="$pool_state/cache/uv"
"$pool_uv" tool install --python 3.12 claude-swap==0.26.0
echo '（如果上面提示 deps/bin 不在 PATH，可以忽略：依赖装在本工具的私有目录，命令入口稍后放进 ~/.local/bin。）'
pool_python="$UV_TOOL_DIR/claude-swap/bin/python"
[ -x "$pool_python" ] || { echo '私有 Python 未安装；请检查 uv 输出。' >&2; exit 2; }
mkdir -p "$pool_state/runtime"
for pool_part in bin lib templates skills; do
  cp -R "$pool_source/$pool_part" "$pool_stage/$pool_part"
done
for pool_part in bin lib templates skills; do
  rm -rf "$pool_state/runtime/$pool_part"
  mv "$pool_stage/$pool_part" "$pool_state/runtime/$pool_part"
done
"$pool_python" -I "$pool_state/runtime/lib/pool.py" install
