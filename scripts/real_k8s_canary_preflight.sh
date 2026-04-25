#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=${ENV_FILE:-.env.real-canary}
if [ ! -f "$ENV_FILE" ]; then
  echo "$ENV_FILE is missing. Copy .env.real-canary.example and fill test Sealos values first." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

failures=0
check() {
  local name="$1" result="$2" message="$3"
  if [ "$result" = "true" ]; then
    printf 'ok   %s - %s\n' "$name" "$message"
  else
    printf 'fail %s - %s\n' "$name" "$message"
    failures=$((failures + 1))
  fi
}

only_k8s_allowlist() {
  [ "${REAL_EXTERNAL_ALLOWLIST:-}" = "k8s" ]
}

check env_file true "$ENV_FILE present"
check allow_real_external_calls "$([ "${ALLOW_REAL_EXTERNAL_CALLS:-false}" = "true" ] && echo true || echo false)" "ALLOW_REAL_EXTERNAL_CALLS=true"
check real_external_allowlist "$([ "$(only_k8s_allowlist && echo yes || echo no)" = "yes" ] && echo true || echo false)" "REAL_EXTERNAL_ALLOWLIST=k8s only"
check newapi_mock "$([ "${NEWAPI_MOCK:-true}" = "true" ] && echo true || echo false)" "NEWAPI_MOCK=true"
check sub2api_mock "$([ "${SUB2API_MOCK:-true}" = "true" ] && echo true || echo false)" "SUB2API_MOCK=true"
check cloudflare_mock "$([ "${CLOUDFLARE_MOCK:-true}" = "true" ] && echo true || echo false)" "CLOUDFLARE_MOCK=true"
check k8s_mode "$([ "${APPLY_K8S:-false}" = "true" ] && [ "${K8S_APPLY_MODE:-mock}" = "real" ] && echo true || echo false)" "APPLY_K8S=true and K8S_APPLY_MODE=real"

HOST_KUBECONFIG=${REAL_KUBECONFIG_HOST_PATH:-./real-kubeconfig/sealos-canary.yaml}
check kubeconfig_path "$([ -f "$HOST_KUBECONFIG" ] && echo true || echo false)" "$HOST_KUBECONFIG exists"
check kubectl_binary "$(command -v kubectl >/dev/null 2>&1 && echo true || echo false)" "host kubectl available"

if command -v kubectl >/dev/null 2>&1 && [ -f "$HOST_KUBECONFIG" ]; then
  context_args=()
  if [ -n "${K8S_CONTEXT:-}" ]; then
    context_args=(--context "$K8S_CONTEXT")
  fi
  kubectl --kubeconfig "$HOST_KUBECONFIG" "${context_args[@]}" version --client=true >/dev/null
  current_context=$(kubectl --kubeconfig "$HOST_KUBECONFIG" "${context_args[@]}" config current-context 2>/dev/null || true)
  check kubectl_context "$([ -n "$current_context" ] && echo true || echo false)" "current-context=${current_context:-missing}"

  namespace=${K8S_TARGET_NAMESPACE:-}
  if [ "${K8S_NAMESPACE_MODE:-generated}" = "fixed" ]; then
    check target_namespace "$([ -n "$namespace" ] && echo true || echo false)" "K8S_TARGET_NAMESPACE is set"
  else
    namespace=${K8S_TARGET_NAMESPACE:-default}
    if kubectl --kubeconfig "$HOST_KUBECONFIG" "${context_args[@]}" auth can-i create namespace >/dev/null 2>&1; then
      check can_create_namespace true "can create namespace"
    else
      check can_create_namespace false "cannot create namespace"
    fi
  fi

  if [ -n "$namespace" ]; then
    for resource in deployment service ingress horizontalpodautoscaler; do
      if kubectl --kubeconfig "$HOST_KUBECONFIG" "${context_args[@]}" auth can-i create "$resource" -n "$namespace" >/dev/null 2>&1; then
        check "can_create_${resource}" true "can create $resource in $namespace"
      else
        check "can_create_${resource}" false "cannot create $resource in $namespace"
      fi
    done
  fi
fi

if [ "$failures" -gt 0 ]; then
  echo "real k8s canary preflight failed: $failures issue(s)" >&2
  exit 1
fi

echo "real k8s canary preflight passed"
