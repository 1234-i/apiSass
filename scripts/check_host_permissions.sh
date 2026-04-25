#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
missing=0
for script in "$ROOT"/scripts/*.sh; do
  if [ ! -x "$script" ]; then
    echo "not executable: ${script#$ROOT/}"
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "script permission check failed: run chmod +x scripts/*.sh or use a fixed release zip"
  exit 1
fi
echo "script permission check OK"
