#!/usr/bin/env bash
set -euo pipefail

CONFIRM_WORD=I_UNDERSTAND_THIS_WILL_CREATE_K8S_RESOURCES_AND_THEN_CLEAN_THEM_UP

if [ "${REAL_K8S_APPLY_CLEANUP_CONFIRM:-}" != "$CONFIRM_WORD" ]; then
  cat >&2 <<TXT
Refusing to run Real Canary 0 Step 3 apply-and-cleanup.

This step will create real Kubernetes canary resources in the configured test namespace,
then attempt cleanup on success or failure.

Set:
  REAL_K8S_APPLY_CLEANUP_CONFIRM=$CONFIRM_WORD
TXT
  exit 2
fi

ENV_FILE=${ENV_FILE:-.env.real-canary}
API=${API:-http://localhost:8080}
HOST_KUBECONFIG=${REAL_KUBECONFIG_HOST_PATH:-./real-kubeconfig/sealos-canary.yaml}
SLUG=${SLUG:-canary-real-apply-$(date +%s)}
DRY_RUN_SLUG=${DRY_RUN_SLUG:-${SLUG}-dryrun}
EMAIL=${EMAIL:-canary@example.com}
TENANT_NAME=${TENANT_NAME:-Real K8s Apply Cleanup Canary}
ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-ChangeMe123!}

tenant_id=""
manifest_file=""
cleanup_needed=false
cleanup_ran=false
failures=0

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    echo ""
  fi
}

PYBIN=$(find_python)
[ -n "$PYBIN" ] || { echo "python3/python is required" >&2; exit 1; }

fail() {
  echo "fail $1" >&2
  failures=$((failures + 1))
}

require_eq() {
  local name="$1" actual="$2" expected="$3"
  if [ "$actual" = "$expected" ]; then
    printf 'ok   %s=%s\n' "$name" "$actual"
  else
    fail "$name expected $expected got ${actual:-<empty>}"
  fi
}

require_non_placeholder() {
  local name="$1" actual="${!1:-}" lower
  lower=$(printf '%s' "$actual" | tr '[:upper:]' '[:lower:]')
  case "$lower" in
    ""|*replace_with*|postgresql://user:pass@host*|redis://:pass@host*|*example.com*|your-*|*placeholder*)
      fail "$name must be a real test value before Step 3 apply-and-cleanup"
      ;;
    *)
      printf 'ok   %s is set to a non-placeholder test value\n' "$name"
      ;;
  esac
}

api_request() {
  local method="$1" path="$2" body="${3:-}" tmp code
  tmp=$(mktemp)
  if [ -n "$body" ]; then
    code=$(curl -sS -o "$tmp" -w '%{http_code}' -X "$method" "$API$path" -H "Content-Type: application/json" -H "X-API-Key: ${API_KEY}" -d "$body")
  else
    code=$(curl -sS -o "$tmp" -w '%{http_code}' -X "$method" "$API$path" -H "X-API-Key: ${API_KEY}")
  fi
  if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
    cat "$tmp"
    rm -f "$tmp"
    return 0
  fi
  echo "HTTP $code for $method $path" >&2
  cat "$tmp" >&2
  echo >&2
  rm -f "$tmp"
  return 1
}

api_get() {
  api_request GET "$1"
}

api_post() {
  local body="${2:-}"
  [ -n "$body" ] || body='{}'
  api_request POST "$1" "$body"
}

host_kubectl_get_by_canary_selector() {
  local selector="$1"
  if [ -n "${K8S_CONTEXT:-}" ]; then
    kubectl --kubeconfig "$HOST_KUBECONFIG" --context "$K8S_CONTEXT" \
      get deployments.apps,services,ingresses.networking.k8s.io,horizontalpodautoscalers.autoscaling \
      -n "${K8S_TARGET_NAMESPACE}" \
      -l "$selector" \
      -o name \
      --ignore-not-found 2>/dev/null || true
  else
    kubectl --kubeconfig "$HOST_KUBECONFIG" \
      get deployments.apps,services,ingresses.networking.k8s.io,horizontalpodautoscalers.autoscaling \
      -n "${K8S_TARGET_NAMESPACE}" \
      -l "$selector" \
      -o name \
      --ignore-not-found 2>/dev/null || true
  fi
}

cleanup_on_exit() {
  local exit_code=$?
  if [ "$cleanup_needed" != "true" ] || [ "$cleanup_ran" = "true" ]; then
    exit "$exit_code"
  fi
  cleanup_ran=true
  echo "== Step 3 cleanup =="
  if [ -n "$tenant_id" ]; then
    api_post "/api/v1/tenants/${tenant_id}/delete-runtime" >/dev/null 2>&1 || true
  fi
  if [ -n "$manifest_file" ] && [ -f "$manifest_file" ]; then
    if [ -n "${K8S_CONTEXT:-}" ]; then
      kubectl --kubeconfig "$HOST_KUBECONFIG" --context "$K8S_CONTEXT" delete -f "$manifest_file" --ignore-not-found=true || true
    else
      kubectl --kubeconfig "$HOST_KUBECONFIG" delete -f "$manifest_file" --ignore-not-found=true || true
    fi
  fi
  local remaining
  remaining=$(host_kubectl_get_by_canary_selector "$CANARY_SELECTOR")
  if [ -n "$remaining" ]; then
    echo "resources still exist after cleanup:" >&2
    echo "$remaining" >&2
    exit 1
  fi
  echo "ok   cleanup post-check found no canary resources"
  exit "$exit_code"
}

trap cleanup_on_exit EXIT

bash ./scripts/check_source_format.sh
bash ./scripts/check_env_files.sh "$ENV_FILE"
bash ./scripts/real_k8s_canary_static_check.sh
bash ./scripts/real_k8s_canary_doctor.sh --strict
bash ./scripts/real_k8s_canary_server_dry_run_static_check.sh
bash ./scripts/real_k8s_canary_apply_cleanup_static_check.sh

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

require_eq ALLOW_REAL_EXTERNAL_CALLS "${ALLOW_REAL_EXTERNAL_CALLS:-}" true
require_eq REAL_EXTERNAL_ALLOWLIST "${REAL_EXTERNAL_ALLOWLIST:-}" k8s
require_eq APPLY_K8S "${APPLY_K8S:-}" true
require_eq K8S_APPLY_MODE "${K8S_APPLY_MODE:-}" real
require_eq K8S_SERVER_DRY_RUN_FIRST "${K8S_SERVER_DRY_RUN_FIRST:-}" true
require_eq K8S_CANARY_MODE "${K8S_CANARY_MODE:-}" true
require_eq NEWAPI_MOCK "${NEWAPI_MOCK:-}" true
require_eq SUB2API_MOCK "${SUB2API_MOCK:-}" true
require_eq CLOUDFLARE_MOCK "${CLOUDFLARE_MOCK:-}" true
require_non_placeholder NEWAPI_SQL_DSN_TEMPLATE
require_non_placeholder NEWAPI_REDIS_CONN_TEMPLATE

if [ "$failures" -gt 0 ]; then
  echo "Step 3 safety checks failed before any real apply" >&2
  exit 1
fi

CANARY_SELECTOR="app=newapi-${SLUG},api-saas.weisoft.chat/canary=true,api-saas.weisoft.chat/tenant-slug=${SLUG}"

REAL_K8S_SERVER_DRY_RUN_CONFIRM=I_UNDERSTAND_THIS_WILL_QUERY_K8S_API_WITH_SERVER_DRY_RUN_BUT_NOT_CREATE_RESOURCES \
  SLUG="$DRY_RUN_SLUG" \
  EMAIL="$EMAIL" \
  bash ./scripts/real_k8s_canary_server_dry_run.sh

curl -fsS "$API/health" >/dev/null
curl -fsS "$API/ready" >/dev/null

tenant_payload=$(
  "$PYBIN" - "$TENANT_NAME" "$SLUG" "$EMAIL" "$ADMIN_USERNAME" "$ADMIN_PASSWORD" <<'PY'
import json
import sys

name, slug, email, admin_username, admin_password = sys.argv[1:6]
print(json.dumps({
    "name": name,
    "slug": slug,
    "email": email,
    "plan": "canary",
    "admin_username": admin_username,
    "admin_password": admin_password,
    "deploy": True,
    "apply_k8s": False,
}))
PY
)

tenant_json=$(api_post "/api/v1/tenants" "$tenant_payload")
tenant_id=$(
  "$PYBIN" - "$tenant_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
tenant_id = payload.get("id")
if not tenant_id:
    print("tenant id missing from create response", file=sys.stderr)
    raise SystemExit(1)
print(tenant_id)
PY
)
echo "ok   created local canary tenant record $tenant_id"

plan_json=$(api_get "/api/v1/tenants/${tenant_id}/deployment-plan")
"$PYBIN" - "$plan_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
safety = payload.get("safety", {})
required = {
    "will_call_k8s": True,
    "will_call_newapi": False,
    "will_call_sub2api": False,
    "will_call_cloudflare": False,
}
failed = []
for key, expected in required.items():
    if safety.get(key) is not expected:
        failed.append(f"{key} expected {expected} got {safety.get(key)}")
if failed:
    print("deployment plan refused Step 3:", "; ".join(failed), file=sys.stderr)
    raise SystemExit(1)
print("ok   deployment plan allows only k8s real calls")
PY

manifest_file="generated-manifests/${SLUG}.yaml"
cleanup_needed=true

deploy_json=$(api_post "/api/v1/tenants/${tenant_id}/deploy" '{"dry_run":false,"wait_ready":true}')
echo "$deploy_json" | "$PYBIN" -m json.tool

remaining=$(host_kubectl_get_by_canary_selector "$CANARY_SELECTOR")
if [ -z "$remaining" ]; then
  echo "no canary resources found after apply; refusing to report Step 3 success" >&2
  exit 1
fi
echo "$remaining"

cleanup_on_exit
