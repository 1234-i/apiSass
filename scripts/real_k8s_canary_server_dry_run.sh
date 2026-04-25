#!/usr/bin/env bash
set -euo pipefail

CONFIRM_WORD=I_UNDERSTAND_THIS_WILL_QUERY_K8S_API_WITH_SERVER_DRY_RUN_BUT_NOT_CREATE_RESOURCES

if [ "${REAL_K8S_SERVER_DRY_RUN_CONFIRM:-}" != "$CONFIRM_WORD" ]; then
  cat >&2 <<TXT
Refusing to run Real Canary 0 Step 2 server-side dry-run.

This step will query the Kubernetes API server by running:
  kubectl apply --dry-run=server -f <manifest>

It must not persist resources.

Set:
  REAL_K8S_SERVER_DRY_RUN_CONFIRM=$CONFIRM_WORD
TXT
  exit 2
fi

ENV_FILE=${ENV_FILE:-.env.real-canary}
API=${API:-http://localhost:8080}
HOST_KUBECONFIG=${REAL_KUBECONFIG_HOST_PATH:-./real-kubeconfig/sealos-canary.yaml}
SLUG=${SLUG:-canary-server-dry-run-$(date +%s)}
EMAIL=${EMAIL:-canary@example.com}
TENANT_NAME=${TENANT_NAME:-Real K8s Server Dry Run Canary}

failures=0

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
  local name="$1" actual="$2"
  case "$actual" in
    ""|example.com|your-test-domain.com|ingress.example.com|ingress.your-test-domain.com)
      fail "$name must be a real test value before server-side dry-run manifest validation"
      ;;
    *)
      printf 'ok   %s is set for server-side dry-run\n' "$name"
      ;;
  esac
}

api_get() {
  curl -fsS -H "X-API-Key: ${API_KEY}" "$API$1"
}

api_post() {
  curl -fsS -X POST "$API$1" -H "Content-Type: application/json" -H "X-API-Key: ${API_KEY}" -d "$2"
}

host_kubectl() {
  if [ -n "${K8S_CONTEXT:-}" ]; then
    kubectl --kubeconfig "$HOST_KUBECONFIG" --context "$K8S_CONTEXT" "$@"
  else
    kubectl --kubeconfig "$HOST_KUBECONFIG" "$@"
  fi
}

container_kubectl() {
  docker compose -f docker-compose.yml -f docker-compose.real-canary.yml exec -T \
    -e KUBECONFIG="${KUBECONFIG_PATH:-/app/.kube/sealos-canary.yaml}" \
    api kubectl "$@"
}

bash ./scripts/check_source_format.sh
bash ./scripts/check_env_files.sh "$ENV_FILE"
bash ./scripts/real_k8s_canary_static_check.sh
bash ./scripts/real_k8s_canary_doctor.sh --strict

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

require_eq ALLOW_REAL_EXTERNAL_CALLS "${ALLOW_REAL_EXTERNAL_CALLS:-}" true
require_eq REAL_EXTERNAL_ALLOWLIST "${REAL_EXTERNAL_ALLOWLIST:-}" k8s
require_eq APPLY_K8S "${APPLY_K8S:-}" true
require_eq K8S_APPLY_MODE "${K8S_APPLY_MODE:-}" real
require_eq K8S_SERVER_DRY_RUN_FIRST "${K8S_SERVER_DRY_RUN_FIRST:-}" true
require_eq NEWAPI_MOCK "${NEWAPI_MOCK:-}" true
require_eq SUB2API_MOCK "${SUB2API_MOCK:-}" true
require_eq CLOUDFLARE_MOCK "${CLOUDFLARE_MOCK:-}" true

require_non_placeholder BASE_DOMAIN "${BASE_DOMAIN:-}"
require_non_placeholder PUBLIC_GATEWAY_CNAME "${PUBLIC_GATEWAY_CNAME:-}"

if [ ! -f "$HOST_KUBECONFIG" ]; then
  fail "$HOST_KUBECONFIG missing"
fi

if [ "$failures" -gt 0 ]; then
  echo "server-side dry-run safety checks failed before any kubectl apply --dry-run=server call" >&2
  exit 1
fi

curl -fsS "$API/health" >/dev/null
curl -fsS "$API/ready" >/dev/null
preflight_json=$(api_get "/api/v1/system/preflight")

python3 - "$preflight_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
safety = payload.get("config", {}).get("safety", {})
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
    print("system preflight refused server-side dry-run:", "; ".join(failed), file=sys.stderr)
    raise SystemExit(1)
print("ok   system preflight allows only k8s real calls")
PY

tenant_payload=$(
  python3 - "$TENANT_NAME" "$SLUG" "$EMAIL" <<'PY'
import json
import sys

name, slug, email = sys.argv[1:4]
print(json.dumps({
    "name": name,
    "slug": slug,
    "email": email,
    "plan": "canary",
    "apply_k8s": False,
}))
PY
)

tenant_json=$(api_post "/api/v1/tenants" "$tenant_payload")
tenant_id=$(
  python3 - "$tenant_json" <<'PY'
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

api_get "/api/v1/tenants/${tenant_id}" >/dev/null
api_get "/api/v1/tenants/${tenant_id}/manifest-validation" >/dev/null

tmp_manifest=$(mktemp)
host_dry_run_log=$(mktemp)
container_dry_run_log=$(mktemp)
trap 'rm -f "$tmp_manifest" "$host_dry_run_log" "$container_dry_run_log"' EXIT
api_get "/api/v1/manifests/${tenant_id}" > "$tmp_manifest"
echo "ok   wrote manifest to temporary file"

assert_no_podsecurity_warning() {
  local name="$1"
  local log_file="$2"
  if grep -qi "would violate PodSecurity" "$log_file"; then
    echo "ERROR: server dry-run still reports PodSecurity warning in $name output" >&2
    cat "$log_file" >&2
    exit 1
  fi
  if grep -Eqi "allowPrivilegeEscalation|capabilities\\.drop|runAsNonRoot|seccompProfile" "$log_file"; then
    echo "ERROR: server dry-run still reports restricted PodSecurity field warnings in $name output" >&2
    cat "$log_file" >&2
    exit 1
  fi
  echo "ok   $name server dry-run has no restricted PodSecurity warning"
}

if ! host_kubectl apply --dry-run=server -f "$tmp_manifest" >"$host_dry_run_log" 2>&1; then
  cat "$host_dry_run_log" >&2
  exit 1
fi
cat "$host_dry_run_log"
assert_no_podsecurity_warning "host kubectl" "$host_dry_run_log"

if ! cat "$tmp_manifest" | container_kubectl apply --dry-run=server -f - >"$container_dry_run_log" 2>&1; then
  cat "$container_dry_run_log" >&2
  exit 1
fi
cat "$container_dry_run_log"
assert_no_podsecurity_warning "container kubectl" "$container_dry_run_log"

remaining=$(
  host_kubectl get deployments.apps,services,ingresses.networking.k8s.io,horizontalpodautoscalers.autoscaling \
    -n "${K8S_TARGET_NAMESPACE}" \
    -l "app=${SLUG}" \
    -o name \
    --ignore-not-found 2>/dev/null || true
)

if [ -n "$remaining" ]; then
  echo "server-side dry-run left matching resources, which should be impossible:" >&2
  echo "$remaining" >&2
  exit 1
fi

echo "real k8s canary server-side dry-run passed without persistent resources"
