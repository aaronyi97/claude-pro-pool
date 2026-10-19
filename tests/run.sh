#!/bin/bash
set -euo pipefail
if [ -z "${CPP_TEST_ROOT:-}" ]; then
  echo '请先设置 CPP_TEST_ROOT，指向专门放假 HOME 的测试目录。' >&2
  exit 2
fi
mkdir -p "$CPP_TEST_ROOT"
cd "$(dirname "$0")/.."
bash -n install.sh uninstall.sh tests/run.sh
python3 -B -m unittest discover -s tests -v
git diff --check
