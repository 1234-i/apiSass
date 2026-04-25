#!/usr/bin/env bash
set -euo pipefail

TARGET=${TARGET:-scripts/real_k8s_canary_apply_and_cleanup.sh}
CONFIRM_WORD=I_UNDERSTAND_THIS_WILL_CREATE_K8S_RESOURCES_AND_THEN_CLEAN_THEM_UP
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

contains() {
  local pattern="$1" label="$2"
  if [ -f "$TARGET" ] && grep -Fq -- "$pattern" "$TARGET"; then
    ok "$label"
  else
    bad "$label missing"
  fi
}

contains "$CONFIRM_WORD" "apply cleanup confirmation word present"
contains "trap cleanup_on_exit EXIT" "trap cleanup present"
contains "/deploy" "deploy endpoint present"
contains "kubectl --kubeconfig" "kubectl command present"
contains "delete -f" "kubectl delete -f cleanup present"
contains "--ignore-not-found=true" "ignore-not-found cleanup present"
contains "NEWAPI_MOCK" "NEWAPI_MOCK=true check present"
contains "SUB2API_MOCK" "SUB2API_MOCK=true check present"
contains "CLOUDFLARE_MOCK" "CLOUDFLARE_MOCK=true check present"
contains "K8S_CANARY_MODE" "K8S_CANARY_MODE=true check present"
contains "require_non_placeholder NEWAPI_SQL_DSN_TEMPLATE" "DB placeholder check present"
contains "require_non_placeholder NEWAPI_REDIS_CONN_TEMPLATE" "Redis placeholder check present"
contains "CANARY_SELECTOR" "canary selector post-check present"
contains "api-saas.weisoft.chat/canary=true" "canary label selector present"
contains "api-saas.weisoft.chat/tenant-slug" "tenant slug label selector present"

if [ -f "$TARGET" ] && grep -Fq "/provision" "$TARGET"; then
  bad "forbidden endpoint found in $TARGET"
else
  ok "no forbidden one-shot endpoint reference found"
fi

if [ -f "$TARGET" ] && grep -Eq "/init-newapi|/bind-upstream|/domains/.*/verify|/domains\"" "$TARGET"; then
  bad "non-K8s management endpoint found in $TARGET"
else
  ok "no New API/Sub2API/domain management endpoint found"
fi

if [ -f "$TARGET" ] && grep -Fq "real_k8s_canary_open.sh" "$TARGET"; then
  bad "open script reference found in $TARGET"
else
  ok "no open script reference found"
fi

if [ -f "$TARGET" ] && grep -Fq "real_k8s_canary_cleanup.sh" "$TARGET"; then
  bad "legacy cleanup script reference found in $TARGET"
else
  ok "no legacy cleanup script reference found"
fi

if [ "$failed" -ne 0 ]; then
  exit 1
fi

echo "real k8s canary apply cleanup static checks passed without creating resources"
