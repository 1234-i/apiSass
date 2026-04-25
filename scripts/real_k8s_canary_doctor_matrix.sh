#!/usr/bin/env bash
set -euo pipefail

if [ -f .env.real-canary ] || [ -d real-kubeconfig ]; then
  echo "Refusing to run matrix while .env.real-canary or real-kubeconfig exists." >&2
  exit 2
fi

cleanup() {
  rm -f .env.real-canary
  rm -rf real-kubeconfig
}
trap cleanup EXIT

run_doctor() {
  bash ./scripts/real_k8s_canary_doctor.sh
}

expect_output() {
  local output="$1"
  local pattern="$2"
  local label="$3"
  if ! grep -Fq "$pattern" <<<"$output"; then
    echo "doctor matrix failed in $label: missing $pattern" >&2
    echo "$output" >&2
    exit 1
  fi
}

reset_case() {
  rm -f .env.real-canary
  rm -rf real-kubeconfig
}

write_real_canary_env() {
  cp .env.real-canary.example .env.real-canary
  python3 - <<'PY'
from pathlib import Path

path = Path(".env.real-canary")
values = {
    "K8S_TARGET_NAMESPACE": "sealos-test-namespace",
    "BASE_DOMAIN": "canary.example.test",
    "PUBLIC_GATEWAY_CNAME": "ingress.canary.example.test",
    "NEWAPI_SQL_DSN_TEMPLATE": "postgresql://user:pass@postgres.example.test:5432/newapi",
    "NEWAPI_REDIS_CONN_TEMPLATE": "redis://:pass@redis.example.test:6379/0",
}

lines = []
for raw in path.read_text(encoding="utf-8").splitlines():
    if "=" not in raw or raw.lstrip().startswith("#"):
        lines.append(raw)
        continue
    key, _value = raw.split("=", 1)
    lines.append(f"{key}={values.get(key, _value)}")

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

write_fake_kubeconfig() {
  mkdir -p real-kubeconfig
  cat > real-kubeconfig/sealos-canary.yaml <<'YAML'
apiVersion: v1
kind: Config
clusters:
- name: fake-canary
  cluster:
    server: https://kubernetes.invalid
contexts:
- name: fake-canary
  context:
    cluster: fake-canary
    user: fake-canary
current-context: fake-canary
users:
- name: fake-canary
  user:
    token: fake-token
YAML
}

reset_case
out=$(run_doctor)
expect_output "$out" "real_k8s_canary_doctor_status=not_configured" "case A"
expect_output "$out" "safe_to_run_real_preflight=false" "case A"
expect_output "$out" "will_call_k8s_api=false" "case A"
expect_output "$out" "missing=.env.real-canary,real-kubeconfig/sealos-canary.yaml" "case A"
echo "ok doctor matrix case A"

reset_case
write_real_canary_env
out=$(run_doctor)
expect_output "$out" "real_k8s_canary_doctor_status=not_configured" "case B"
expect_output "$out" "safe_to_run_real_preflight=false" "case B"
expect_output "$out" "missing=real-kubeconfig/sealos-canary.yaml" "case B"
echo "ok doctor matrix case B"

reset_case
write_real_canary_env
write_fake_kubeconfig
chmod 0644 real-kubeconfig/sealos-canary.yaml
out=$(run_doctor)
expect_output "$out" "real_k8s_canary_doctor_status=not_configured" "case C"
expect_output "$out" "safe_to_run_real_preflight=false" "case C"
expect_output "$out" "kubeconfig_permissions_should_be_600_or_stricter" "case C"
echo "ok doctor matrix case C"

reset_case
write_real_canary_env
write_fake_kubeconfig
chmod 0600 real-kubeconfig/sealos-canary.yaml
out=$(run_doctor)
expect_output "$out" "real_k8s_canary_doctor_status=ready_for_human_authorized_preflight" "case D"
expect_output "$out" "safe_to_run_real_preflight=true" "case D"
expect_output "$out" "required_confirmation=REAL_K8S_PREFLIGHT_CONFIRM=I_UNDERSTAND_THIS_WILL_QUERY_K8S_API" "case D"
echo "ok doctor matrix case D"

echo "real k8s canary doctor matrix passed without external calls"
