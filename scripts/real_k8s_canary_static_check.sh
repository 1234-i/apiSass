#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=${ENV_FILE:-.env.real-canary.example}

bash ./scripts/check_env_files.sh
bash ./scripts/check_env_files.sh "$ENV_FILE"

python3 - "$ENV_FILE" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

env_path = Path(sys.argv[1])
if not env_path.exists():
    print(f"{env_path} is missing", file=sys.stderr)
    raise SystemExit(2)

values: dict[str, str] = {}
for lineno, raw in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    key, value = line.split("=", 1)
    values[key] = value

failures: list[str] = []


def require(name: str, expected=None) -> None:
    value = values.get(name)
    if value is None:
        failures.append(f"{name} is missing")
        return
    if expected is not None and value != expected:
        failures.append(f"{name} must be {expected!r}, got {value!r}")


require("ALLOW_REAL_EXTERNAL_CALLS", "true")
require("REAL_EXTERNAL_ALLOWLIST", "k8s")
require("APPLY_K8S", "true")
require("K8S_APPLY_MODE", "real")
require("K8S_SERVER_DRY_RUN_FIRST", "true")
require("NEWAPI_MOCK", "true")
require("SUB2API_MOCK", "true")
require("CLOUDFLARE_MOCK", "true")

for name in ("KUBECONFIG_PATH", "BASE_DOMAIN", "PUBLIC_GATEWAY_CNAME", "NEWAPI_SQL_DSN_TEMPLATE", "NEWAPI_REDIS_CONN_TEMPLATE"):
    if not values.get(name):
        failures.append(f"{name} must be set in {env_path}")

namespace_mode = values.get("K8S_NAMESPACE_MODE")
if namespace_mode not in {"fixed", "generated"}:
    failures.append("K8S_NAMESPACE_MODE must be fixed or generated")
if namespace_mode == "fixed" and not values.get("K8S_TARGET_NAMESPACE"):
    failures.append("K8S_TARGET_NAMESPACE must be set when K8S_NAMESPACE_MODE=fixed")

allowlist = {item.strip() for item in values.get("REAL_EXTERNAL_ALLOWLIST", "").split(",") if item.strip()}
for adapter in ("newapi", "sub2api", "cloudflare"):
    if adapter in allowlist:
        failures.append(f"Real Canary 0 must not allow real {adapter}")

for name in ("NEWAPI_ADMIN_TOKEN", "SUB2API_ADMIN_KEY", "SUB2API_TENANT_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID"):
    if values.get(name):
        failures.append(f"{name} should stay empty for K8s-only Real Canary 0")

if failures:
    for failure in failures:
        print(f"fail {failure}", file=sys.stderr)
    raise SystemExit(1)

print(f"ok {env_path} is K8s-only Real Canary 0 static config")
PY

if ! grep -q 'REAL_K8S_PREFLIGHT_CONFIRM=I_UNDERSTAND_THIS_TOUCHES_K8S_API' scripts/real_k8s_canary_preflight.sh; then
  echo 'scripts/real_k8s_canary_preflight.sh must require REAL_K8S_PREFLIGHT_CONFIRM before kubectl checks' >&2
  exit 1
fi

if grep -Eq 'kubectl[[:space:]]+(apply|create|delete|patch|replace)' scripts/real_k8s_canary_preflight.sh; then
  echo 'scripts/real_k8s_canary_preflight.sh must not mutate Kubernetes resources' >&2
  exit 1
fi

echo 'ok real k8s canary static checks passed without calling kubectl'
