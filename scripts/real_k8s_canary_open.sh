#!/usr/bin/env bash
set -euo pipefail

if [ "${REAL_K8S_CANARY_CONFIRM:-}" != "I_UNDERSTAND_ONLY_K8S_WILL_BE_TOUCHED" ]; then
  cat >&2 <<'TXT'
Refusing to run Real Canary 0.
Set REAL_K8S_CANARY_CONFIRM=I_UNDERSTAND_ONLY_K8S_WILL_BE_TOUCHED only after .env.real-canary points at a Sealos test workspace/kubeconfig.
This script must keep New API management, Sub2API, Cloudflare and custom domains mocked.
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
EMAIL=${EMAIL:-canary@example.com}
STATION_NAME=${STATION_NAME:-Real K8s Canary}
ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-ChangeMe123!}

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
api_post(){
  local path="$1" body="${2-}"
  [ -n "$body" ] || body='{}'
  api_request POST "$path" "$body"
}

echo '== real-flow preflight =='
PREFLIGHT=$(api_get "/api/v1/system/real-flow-preflight")
echo "$PREFLIGHT" | pretty
echo "$PREFLIGHT" | "$PYBIN" -c 'import json,sys
d=json.load(sys.stdin)
assert d.get("will_call_k8s") is True, "will_call_k8s must be true"
assert d.get("will_call_newapi") is False, "will_call_newapi must stay false"
assert d.get("will_call_sub2api") is False, "will_call_sub2api must stay false"
assert d.get("will_call_cloudflare") is False, "will_call_cloudflare must stay false"
'

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

echo '== create tenant + manifest =='
CREATE_RESP=$(api_post "/api/v1/tenants" "$PAYLOAD")
echo "$CREATE_RESP" | pretty
TENANT_ID=$(echo "$CREATE_RESP" | json_get id)
[ -n "$TENANT_ID" ] || { echo 'tenant id missing' >&2; exit 1; }

echo '== deployment plan =='
PLAN=$(api_get "/api/v1/tenants/$TENANT_ID/deployment-plan")
echo "$PLAN" | pretty
echo "$PLAN" | "$PYBIN" -c 'import json,sys
d=json.load(sys.stdin)
steps=d.get("steps", [])
assert any(s.get("name")=="deploy_newapi_runtime" and s.get("will_call_external") is True for s in steps)
assert all(s.get("will_call_external") is False for s in steps if s.get("name")!="deploy_newapi_runtime")
'

echo '== deploy only K8s/Sealos real path =='
DEPLOY_RESP=$(api_post "/api/v1/tenants/$TENANT_ID/deploy" '{"dry_run":false,"wait_ready":true}')
echo "$DEPLOY_RESP" | pretty

echo '== tenant detail =='
TENANT_DETAIL=$(api_get "/api/v1/tenants/$TENANT_ID")
echo "$TENANT_DETAIL" | pretty

echo '== runtime state =='
api_get "/api/v1/mock/runtime/$SLUG" | pretty

namespace=$(echo "$TENANT_DETAIL" | "$PYBIN" -c 'import json,sys
d=json.load(sys.stdin)
instances=d.get("instances") or []
print(d.get("namespace") or (instances[0].get("namespace") if instances else "") or "")
')
[ -n "$namespace" ] || namespace=${K8S_TARGET_NAMESPACE:-ai-tenant-$SLUG}
echo '== kubectl resources =='
docker compose -f docker-compose.yml -f docker-compose.real-canary.yml exec -T api \
  kubectl get deployment,service,ingress,pods -n "$namespace" -l "app=newapi-$SLUG" -o wide

echo "Real Canary 0 open completed for tenant_id=$TENANT_ID slug=$SLUG namespace=$namespace"
