#!/usr/bin/env bash
set -euo pipefail
API=${API:-http://localhost:8080}
KEY=${API_KEY:-change-me-admin-token}
SLUG=${SLUG:-demo-station-$(date +%s)}
EMAIL=${EMAIL:-${SLUG}@example.com}

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
if [ -z "$PYBIN" ]; then
  echo 'python3/python is required for smoke_test JSON generation and parsing' >&2
  exit 1
fi

json_get() {
  "$PYBIN" -c 'import json,sys; data=json.load(sys.stdin); print(data.get(sys.argv[1], ""))' "$1"
}

pretty() {
  "$PYBIN" -m json.tool 2>/dev/null || cat
}

json_tenant_create() {
  "$PYBIN" - "$EMAIL" "$SLUG" <<'PY'
import json
import sys
email, slug = sys.argv[1], sys.argv[2]
payload = {
    "name": "Demo Station",
    "email": email,
    "slug": slug,
    "admin_username": "admin",
    "admin_password": "ChangeMe123!",
    "rpm": 60,
    "tpm": 100000,
    "monthly_limit": 10000000,
    "deploy": True,
    "apply_k8s": False,
}
print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
PY
}

json_custom_domain() {
  "$PYBIN" - "$SLUG" <<'PY'
import json
import sys
slug = sys.argv[1]
payload = {
    "domain": f"api-{slug}.customer.example",
    "use_cloudflare": True,
}
print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
PY
}

json_provision_job() {
  "$PYBIN" - "$SLUG" <<'PY'
import json
import sys
slug = sys.argv[1]
payload = {
    "dry_run": True,
    "verify_domains": True,
    "run_inline": True,
    "idempotency_key": f"{slug}-provision-v1",
}
print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
PY
}

json_queued_job() {
  "$PYBIN" - "$SLUG" "$1" <<'PY'
import json
import sys
slug, suffix = sys.argv[1], sys.argv[2]
payload = {
    "dry_run": True,
    "verify_domains": True,
    "run_inline": False,
    "idempotency_key": f"{slug}-{suffix}",
    "max_attempts": 3,
}
print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
PY
}

json_failure_job() {
  "$PYBIN" - "$SLUG" <<'PY'
import json
import sys
slug = sys.argv[1]
payload = {
    "dry_run": True,
    "verify_domains": True,
    "run_inline": True,
    "idempotency_key": f"{slug}-failure-retry-v1",
    "max_attempts": 2,
    "simulate_failure_phase": "bind_upstream",
}
print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
PY
}

api_request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local tmp
  tmp=$(mktemp)
  local code
  if [ -n "$body" ]; then
    code=$(curl -sS -o "$tmp" -w '%{http_code}' -X "$method" "$API$path" \
      -H "Content-Type: application/json" -H "X-API-Key: $KEY" -d "$body")
  else
    code=$(curl -sS -o "$tmp" -w '%{http_code}' -X "$method" "$API$path" \
      -H "X-API-Key: $KEY")
  fi

  if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
    cat "$tmp"
    rm -f "$tmp"
    return 0
  fi

  echo "HTTP $code for $method $path" >&2
  echo 'Response body:' >&2
  cat "$tmp" >&2
  echo >&2
  if [ -n "$body" ]; then
    echo 'Request body:' >&2
    echo "$body" >&2
  fi
  rm -f "$tmp"
  return 1
}

api_post() {
  local path="$1"
  local body
  if [ "$#" -ge 2 ]; then
    body="$2"
  else
    body='{}'
  fi
  api_request POST "$path" "$body"
}

api_get() {
  local path="$1"
  api_request GET "$path"
}

api_patch() {
  local path="$1"
  local body
  if [ "$#" -ge 2 ]; then
    body="$2"
  else
    body='{}'
  fi
  api_request PATCH "$path" "$body"
}

echo '1) health'
curl -fsS "$API/health" | pretty

echo '2) ready'
curl -fsS "$API/ready" | pretty

echo '2b) system preflight safe mode'
api_get "/api/v1/system/preflight" | pretty

echo '2c) real-flow preflight should stay safe/not ready by default'
api_get "/api/v1/system/real-flow-preflight" | pretty

echo '3) create tenant + generate manifest'
TENANT_PAYLOAD=$(json_tenant_create)
RESP=$(api_post "/api/v1/tenants" "$TENANT_PAYLOAD")
echo "$RESP" | pretty
TENANT_ID=$(echo "$RESP" | json_get id)
if [ -z "$TENANT_ID" ]; then
  echo 'tenant id missing from create response' >&2
  exit 1
fi

echo '4) get tenant detail'
api_get "/api/v1/tenants/$TENANT_ID" | pretty

echo '5) validate manifest'
api_get "/api/v1/tenants/$TENANT_ID/manifest-validation" | pretty

echo '5b) deployment plan dry-run preview'
api_get "/api/v1/tenants/$TENANT_ID/deployment-plan" | pretty

echo '6) Phase 2 deploy runtime mock/dry-run'
DEPLOY_RESP=$(api_post "/api/v1/tenants/$TENANT_ID/deploy" '{"dry_run":true,"wait_ready":true}')
echo "$DEPLOY_RESP" | pretty

echo '7) Phase 3 init New API mock'
api_post "/api/v1/tenants/$TENANT_ID/init-newapi" '{"force":true}' | pretty

echo '8) Phase 4 bind Sub2API upstream mock'
api_post "/api/v1/tenants/$TENANT_ID/bind-upstream" '{"force":true}' | pretty

echo '9) Phase 5 add custom domain placeholder + verify mock'
DOMAIN_PAYLOAD=$(json_custom_domain)
DOMAIN_RESP=$(api_post "/api/v1/tenants/$TENANT_ID/domains" "$DOMAIN_PAYLOAD")
echo "$DOMAIN_RESP" | pretty
DOMAIN_ID=$(echo "$DOMAIN_RESP" | json_get id)
if [ -z "$DOMAIN_ID" ]; then
  echo 'domain id missing from custom domain response' >&2
  exit 1
fi
api_post "/api/v1/tenants/$TENANT_ID/domains/$DOMAIN_ID/verify" '{}' | pretty

echo '10) one-shot provision endpoint should be idempotent-ish in mock mode'
api_post "/api/v1/tenants/$TENANT_ID/provision" '{"dry_run":true,"verify_domains":true}' | pretty

echo '11) patch quota'
api_patch "/api/v1/tenants/$TENANT_ID/quota" '{"rpm":120,"tpm":200000}' | pretty

echo '12) rpm check'
api_post "/api/v1/runtime/$SLUG/check-rpm" '{}' | pretty

echo '13) mock runtime state'
api_get "/api/v1/mock/runtime/$SLUG" | pretty

echo '14) manifest first 160 lines'
api_get "/api/v1/manifests/$TENANT_ID" | sed -n '1,160p'

echo '15) provision workflow job with audit events and idempotency key'
JOB_PAYLOAD=$(json_provision_job)
JOB_RESP=$(api_post "/api/v1/tenants/$TENANT_ID/jobs/provision" "$JOB_PAYLOAD")
echo "$JOB_RESP" | pretty
JOB_ID=$(echo "$JOB_RESP" | json_get id)
if [ -z "$JOB_ID" ]; then
  echo 'job id missing from provision workflow response' >&2
  exit 1
fi

JOB_STATUS=$(echo "$JOB_RESP" | json_get status)
if [ "$JOB_STATUS" != "succeeded" ]; then
  echo "expected provision workflow job to succeed, got: $JOB_STATUS" >&2
  exit 1
fi

echo '16) get provision workflow job'
api_get "/api/v1/jobs/$JOB_ID" | pretty

echo '17) get provision workflow job audit events'
api_get "/api/v1/jobs/$JOB_ID/events" | pretty

echo '18) idempotency replay should return the same workflow job'
JOB_RESP_2=$(api_post "/api/v1/tenants/$TENANT_ID/jobs/provision" "$JOB_PAYLOAD")
echo "$JOB_RESP_2" | pretty
JOB_ID_2=$(echo "$JOB_RESP_2" | json_get id)
if [ "$JOB_ID" != "$JOB_ID_2" ]; then
  echo "idempotency replay returned a different job: $JOB_ID_2 != $JOB_ID" >&2
  exit 1
fi

echo '19) tenant audit events'
api_get "/api/v1/tenants/$TENANT_ID/audit-events?limit=20" | pretty

echo '20) create queued job and cancel it before worker runs'
QUEUED_CANCEL_PAYLOAD=$(json_queued_job "queued-cancel-v1")
QUEUED_CANCEL_RESP=$(api_post "/api/v1/tenants/$TENANT_ID/jobs/provision" "$QUEUED_CANCEL_PAYLOAD")
echo "$QUEUED_CANCEL_RESP" | pretty
QUEUED_CANCEL_ID=$(echo "$QUEUED_CANCEL_RESP" | json_get id)
QUEUED_CANCEL_STATUS=$(echo "$QUEUED_CANCEL_RESP" | json_get status)
if [ "$QUEUED_CANCEL_STATUS" != "queued" ]; then
  echo "expected queued job, got: $QUEUED_CANCEL_STATUS" >&2
  exit 1
fi
api_post "/api/v1/jobs/$QUEUED_CANCEL_ID/cancel" '{"reason":"smoke test cancel"}' | pretty

echo '21) create queued job and run it via mock worker tick'
QUEUED_RUN_PAYLOAD=$(json_queued_job "queued-worker-v1")
QUEUED_RUN_RESP=$(api_post "/api/v1/tenants/$TENANT_ID/jobs/provision" "$QUEUED_RUN_PAYLOAD")
echo "$QUEUED_RUN_RESP" | pretty
QUEUED_RUN_ID=$(echo "$QUEUED_RUN_RESP" | json_get id)
api_post "/api/v1/workers/mock/provision/tick" '{"worker_id":"smoke-worker","limit":5}' | pretty
QUEUED_RUN_FINAL=$(api_get "/api/v1/jobs/$QUEUED_RUN_ID")
echo "$QUEUED_RUN_FINAL" | pretty
QUEUED_RUN_STATUS=$(echo "$QUEUED_RUN_FINAL" | json_get status)
if [ "$QUEUED_RUN_STATUS" != "succeeded" ]; then
  echo "expected worker-run job to succeed, got: $QUEUED_RUN_STATUS" >&2
  exit 1
fi

echo '22) create mock failure job and verify it fails without external calls'
FAILURE_PAYLOAD=$(json_failure_job)
FAILURE_RESP=$(api_post "/api/v1/tenants/$TENANT_ID/jobs/provision" "$FAILURE_PAYLOAD")
echo "$FAILURE_RESP" | pretty
FAILURE_JOB_ID=$(echo "$FAILURE_RESP" | json_get id)
FAILURE_STATUS=$(echo "$FAILURE_RESP" | json_get status)
if [ "$FAILURE_STATUS" != "failed" ]; then
  echo "expected mock failure job to fail, got: $FAILURE_STATUS" >&2
  exit 1
fi

echo '23) retry failed job with simulated failure cleared'
RETRY_RESP=$(api_post "/api/v1/jobs/$FAILURE_JOB_ID/retry" '{"run_inline":true,"worker_id":"smoke-retry-worker","clear_simulated_failure":true}')
echo "$RETRY_RESP" | pretty
RETRY_STATUS=$(echo "$RETRY_RESP" | json_get status)
if [ "$RETRY_STATUS" != "succeeded" ]; then
  echo "expected retry job to succeed, got: $RETRY_STATUS" >&2
  exit 1
fi

echo '24) get retry job events'
api_get "/api/v1/jobs/$FAILURE_JOB_ID/events" | pretty

echo 'smoke test passed'
