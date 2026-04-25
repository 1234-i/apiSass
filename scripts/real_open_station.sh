#!/usr/bin/env bash
set -euo pipefail

API=${API:-http://localhost:8080}
KEY=${API_KEY:-change-me-admin-token}
SLUG=${SLUG:-real-demo-$(date +%s)}
EMAIL=${EMAIL:-${SLUG}@example.com}
STATION_NAME=${STATION_NAME:-Real Demo Station}
ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-ChangeMe123!}

if [ "${REAL_FLOW_CONFIRM:-}" != "I_UNDERSTAND_THIS_CAN_TOUCH_SEALOS" ]; then
  cat >&2 <<'TXT'
Refusing to run real open-station flow.
Set REAL_FLOW_CONFIRM=I_UNDERSTAND_THIS_CAN_TOUCH_SEALOS only after you have configured:
  ALLOW_REAL_EXTERNAL_CALLS=true
  APPLY_K8S=true
  K8S_APPLY_MODE=real
  NEWAPI_MOCK=false
  SUB2API_MOCK=false
  real kubeconfig/Sealos access, BASE_DOMAIN, PUBLIC_GATEWAY_CNAME,
  NEWAPI_SQL_DSN_TEMPLATE, NEWAPI_REDIS_CONN_TEMPLATE, NEWAPI_ADMIN_TOKEN,
  SUB2API_BASE_URL and SUB2API_TENANT_KEY.
TXT
  exit 2
fi

find_python() {
  if command -v python3 >/dev/null 2>&1; then command -v python3; elif command -v python >/dev/null 2>&1; then command -v python; else echo ""; fi
}
PYBIN=$(find_python)
[ -n "$PYBIN" ] || { echo 'python3/python is required' >&2; exit 1; }

pretty() { "$PYBIN" -m json.tool 2>/dev/null || cat; }
json_get() { "$PYBIN" -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"; }

api_request() {
  local method="$1" path="$2" body="${3:-}" tmp code
  tmp=$(mktemp)
  if [ -n "$body" ]; then
    code=$(curl -sS -o "$tmp" -w '%{http_code}' -X "$method" "$API$path" -H "Content-Type: application/json" -H "X-API-Key: $KEY" -d "$body")
  else
    code=$(curl -sS -o "$tmp" -w '%{http_code}' -X "$method" "$API$path" -H "X-API-Key: $KEY")
  fi
  if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then cat "$tmp"; rm -f "$tmp"; return 0; fi
  echo "HTTP $code for $method $path" >&2; cat "$tmp" >&2; echo >&2; rm -f "$tmp"; return 1
}
api_get(){ api_request GET "$1"; }
api_post(){ local path="$1"; local body; if [ "$#" -ge 2 ]; then body="$2"; else body="{}"; fi; api_request POST "$path" "$body"; }

PAYLOAD=$("$PYBIN" - "$EMAIL" "$SLUG" "$STATION_NAME" "$ADMIN_USERNAME" "$ADMIN_PASSWORD" <<'PY'
import json, sys
email, slug, name, admin_user, admin_pass = sys.argv[1:]
print(json.dumps({
  "name": name,
  "email": email,
  "slug": slug,
  "admin_username": admin_user,
  "admin_password": admin_pass,
  "deploy": True,
  "apply_k8s": False
}, separators=(",", ":")))
PY
)

echo '== real-flow preflight =='
api_get "/api/v1/system/real-flow-preflight" | pretty

echo '== create tenant + manifest =='
CREATE_RESP=$(api_post "/api/v1/tenants" "$PAYLOAD")
echo "$CREATE_RESP" | pretty
TENANT_ID=$(echo "$CREATE_RESP" | json_get id)
[ -n "$TENANT_ID" ] || { echo 'tenant id missing' >&2; exit 1; }

echo '== manifest validation =='
api_get "/api/v1/tenants/$TENANT_ID/manifest-validation" | pretty

echo '== real deploy to Sealos/K8s =='
api_post "/api/v1/tenants/$TENANT_ID/deploy" '{"dry_run":false,"wait_ready":true}' | pretty

echo '== init New API management =='
api_post "/api/v1/tenants/$TENANT_ID/init-newapi" '{"force":true}' | pretty

echo '== bind Sub2API upstream =='
api_post "/api/v1/tenants/$TENANT_ID/bind-upstream" '{"force":true}' | pretty

echo '== final tenant detail =='
api_get "/api/v1/tenants/$TENANT_ID" | pretty

echo "Real open-station flow completed for tenant_id=$TENANT_ID slug=$SLUG"
