#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PARENT=$(dirname "$ROOT")
PROJECT=$(basename "$ROOT")
OUT=${OUT:-$PARENT/ai-api-saas-mvp-v0.10-realflow.zip}
rm -f "$OUT"
chmod +x "$ROOT"/scripts/*.sh
cd "$PARENT"
zip -r "$OUT" "$PROJECT" \
  -x "$PROJECT/*/__pycache__/*" \
     "$PROJECT/.env" \
     "$PROJECT/generated-manifests/*" \
     "$PROJECT/mock-runtime/*" \
     "$PROJECT/.git/*" \
     "$PROJECT/.venv/*" \
     "$PROJECT/.pytest_cache/*"
echo "exported: $OUT"
