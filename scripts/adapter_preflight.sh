#!/usr/bin/env bash
set -euo pipefail
API=${API:-http://localhost:8080}
KEY=${API_KEY:-change-me-admin-token}
if command -v python3 >/dev/null 2>&1; then
  PYBIN=$(command -v python3)
elif command -v python >/dev/null 2>&1; then
  PYBIN=$(command -v python)
else
  PYBIN=""
fi
RESP=$(curl -fsS "$API/api/v1/system/preflight" -H "X-API-Key: $KEY")
if [ -n "$PYBIN" ]; then
  echo "$RESP" | "$PYBIN" -m json.tool
else
  echo "$RESP"
fi
