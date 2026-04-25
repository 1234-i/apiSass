#!/usr/bin/env bash
set -euo pipefail

TARGET=${TARGET:-scripts/real_k8s_canary_server_dry_run.sh}
CONFIRM_WORD=I_UNDERSTAND_THIS_WILL_QUERY_K8S_API_WITH_SERVER_DRY_RUN_BUT_NOT_CREATE_RESOURCES
failed=0

ok() {
  printf 'ok %s\n' "$1"
}

bad() {
  printf '%s\n' "$1" >&2
  failed=1
}

if [ ! -f "$TARGET" ]; then
  bad "$TARGET missing"
else
  ok "$TARGET exists"
fi

if [ -f "$TARGET" ] && grep -Fq "$CONFIRM_WORD" "$TARGET"; then
  ok "server dry-run confirmation word present"
else
  bad "server dry-run confirmation word missing"
fi

if [ -f "$TARGET" ] && grep -Fq -- "--dry-run=server" "$TARGET"; then
  ok "kubectl server dry-run marker present"
else
  bad "--dry-run=server marker missing"
fi

if [ -f "$TARGET" ] && grep -Eq "kubectl[[:space:]].*delete|delete[[:space:]]" "$TARGET"; then
  bad "dangerous kubectl delete/delete command found in $TARGET"
else
  ok "no delete command found"
fi

if [ -f "$TARGET" ] && grep -Fq "real_k8s_canary_open.sh" "$TARGET"; then
  bad "open script reference found in $TARGET"
else
  ok "no open script reference found"
fi

if [ -f "$TARGET" ] && grep -Fq "real_k8s_canary_cleanup.sh" "$TARGET"; then
  bad "cleanup script reference found in $TARGET"
else
  ok "no cleanup script reference found"
fi

if [ -f "$TARGET" ] && grep -Fq "/provision" "$TARGET"; then
  bad "/provision endpoint reference found in $TARGET"
else
  ok "no provision endpoint reference found"
fi

if [ -f "$TARGET" ] && grep -Eq "/deploy|dry_run[[:space:]]*[:=][[:space:]]*false" "$TARGET"; then
  bad "deploy endpoint or dry_run=false reference found in $TARGET"
else
  ok "no deploy endpoint or dry_run=false reference found"
fi

apply_without_dry_run=$(
  python3 - "$TARGET" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text(encoding="utf-8")
commands = []
for line in text.splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if "apply" in stripped and "kubectl" in stripped:
        commands.append(stripped)

for command in commands:
    if "--dry-run=server" not in command:
        print(command)
PY
)

if [ -n "$apply_without_dry_run" ]; then
  bad "kubectl apply command without --dry-run=server found: $apply_without_dry_run"
else
  ok "all direct kubectl apply commands use --dry-run=server"
fi

if [ "$failed" -ne 0 ]; then
  exit 1
fi

echo "real k8s canary server dry-run static checks passed without calling kubectl"
