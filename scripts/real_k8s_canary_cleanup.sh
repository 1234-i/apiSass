#!/usr/bin/env bash
set -euo pipefail

if [ "${REAL_K8S_CANARY_CONFIRM:-}" != "I_UNDERSTAND_THIS_WILL_DELETE_K8S_RESOURCES" ]; then
  cat >&2 <<'TXT'
Refusing to cleanup Real Canary 0 resources.
Set REAL_K8S_CANARY_CONFIRM=I_UNDERSTAND_THIS_WILL_DELETE_K8S_RESOURCES only for the test canary slug you intend to remove.
TXT
  exit 2
fi

ENV_FILE=${ENV_FILE:-.env.real-canary}
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE is missing" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

API=${API:-http://localhost:8080}
KEY=${API_KEY:-change-me-admin-token}
SLUG=${SLUG:-canary-001}
PYBIN=$(command -v python3 || command -v python)
[ -n "$PYBIN" ] || { echo 'python3/python is required' >&2; exit 1; }

api_get(){ curl -fsS "$API$1" -H "X-API-Key: $KEY"; }
api_post(){ curl -fsS -X POST "$API$1" -H "X-API-Key: $KEY"; }

TENANT_ID=$(api_get "/api/v1/tenants" | "$PYBIN" -c 'import json,sys
slug=sys.argv[1]
for row in json.load(sys.stdin):
    if row.get("slug") == slug:
        print(row.get("id",""))
        break
' "$SLUG")

if [ -z "$TENANT_ID" ]; then
  echo "tenant for slug=$SLUG not found; attempting kubectl lookup only"
else
  echo "== delete runtime via control plane =="
  api_post "/api/v1/tenants/$TENANT_ID/delete-runtime" | "$PYBIN" -m json.tool
fi

namespace=${K8S_TARGET_NAMESPACE:-ai-tenant-$SLUG}
echo '== verify resources removed =='
if docker compose -f docker-compose.yml -f docker-compose.real-canary.yml exec -T api \
  kubectl get deployment,service,ingress -n "$namespace" -l "app=newapi-$SLUG" --ignore-not-found=true | grep -q "newapi-$SLUG"; then
  echo "resources still exist for slug=$SLUG" >&2
  exit 1
fi

echo "Real Canary 0 cleanup completed for slug=$SLUG namespace=$namespace"
