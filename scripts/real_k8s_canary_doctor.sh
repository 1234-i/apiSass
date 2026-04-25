#!/usr/bin/env bash
set -euo pipefail

STRICT=false
if [ "${1:-}" = "--strict" ]; then
  STRICT=true
elif [ "${1:-}" != "" ]; then
  echo "usage: $0 [--strict]" >&2
  exit 2
fi

ENV_FILE=${ENV_FILE:-.env.real-canary}
HOST_KUBECONFIG=${REAL_KUBECONFIG_HOST_PATH:-./real-kubeconfig/sealos-canary.yaml}

bash ./scripts/check_env_files.sh --allow-missing "$ENV_FILE"

python3 - "$ENV_FILE" "$HOST_KUBECONFIG" "$STRICT" <<'PY'
from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
kubeconfig_path = Path(sys.argv[2])
strict = sys.argv[3].lower() == "true"

required_values = {
    "ALLOW_REAL_EXTERNAL_CALLS": "true",
    "REAL_EXTERNAL_ALLOWLIST": "k8s",
    "APPLY_K8S": "true",
    "K8S_APPLY_MODE": "real",
    "K8S_SERVER_DRY_RUN_FIRST": "true",
    "K8S_NAMESPACE_MODE": "fixed",
    "K8S_CREATE_NAMESPACE": "false",
    "NEWAPI_MOCK": "true",
    "SUB2API_MOCK": "true",
    "CLOUDFLARE_MOCK": "true",
}

required_nonempty = (
    "KUBECONFIG_PATH",
    "K8S_TARGET_NAMESPACE",
    "BASE_DOMAIN",
    "PUBLIC_GATEWAY_CNAME",
    "NEWAPI_SQL_DSN_TEMPLATE",
    "NEWAPI_REDIS_CONN_TEMPLATE",
)

secret_keys = (
    "NEWAPI_ADMIN_TOKEN",
    "SUB2API_ADMIN_KEY",
    "SUB2API_TENANT_KEY",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ZONE_ID",
)

values: dict[str, str] = {}
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value


def git_ignored(path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass

    ignore_file = Path(".gitignore")
    if not ignore_file.exists():
        return False
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        pattern = raw.strip()
        if not pattern or pattern.startswith("#"):
            continue
        if pattern == path:
            return True
        if pattern.endswith("/") and path.startswith(pattern):
            return True
    return False


issues: list[str] = []
missing: list[str] = []

if not env_path.exists():
    missing.append(str(env_path))
else:
    for key, expected in required_values.items():
        actual = values.get(key)
        if actual != expected:
            issues.append(f"{key}_expected_{expected}_got_{actual or 'missing'}")

    for key in required_nonempty:
        if not values.get(key):
            issues.append(f"{key}_missing")

    allowlist = {item.strip() for item in values.get("REAL_EXTERNAL_ALLOWLIST", "").split(",") if item.strip()}
    for adapter in ("newapi", "sub2api", "cloudflare"):
        if adapter in allowlist:
            issues.append(f"{adapter}_must_not_be_allowlisted")

    for key in secret_keys:
        if values.get(key):
            issues.append(f"{key}_should_stay_empty_for_real_canary_0")

if not kubeconfig_path.exists():
    missing.append(str(kubeconfig_path))
else:
    mode = stat.S_IMODE(kubeconfig_path.stat().st_mode)
    if mode & 0o077:
        issues.append(f"kubeconfig_permissions_should_be_600_or_stricter_actual_{oct(mode)}")

env_ignored = git_ignored(".env.real-canary")
kubeconfig_ignored = git_ignored("real-kubeconfig/sealos-canary.yaml")
if not env_ignored:
    issues.append(".env.real-canary_not_gitignored")
if not kubeconfig_ignored:
    issues.append("real-kubeconfig/sealos-canary.yaml_not_gitignored")

ready = not missing and not issues
status = "ready_for_human_authorized_preflight" if ready else "not_configured"

print(f"real_k8s_canary_doctor_status={status}")
print(f"safe_to_run_real_preflight={'true' if ready else 'false'}")
print("will_call_k8s_api=false")
print("will_call_newapi=false")
print("will_call_sub2api=false")
print("will_call_cloudflare=false")
print(f"env_file={env_path}")
print(f"kubeconfig_file={kubeconfig_path}")
print(f"env_file_present={'true' if env_path.exists() else 'false'}")
print(f"kubeconfig_present={'true' if kubeconfig_path.exists() else 'false'}")
print(f"env_file_gitignored={'true' if env_ignored else 'false'}")
print(f"kubeconfig_gitignored={'true' if kubeconfig_ignored else 'false'}")
print(f"missing={','.join(missing)}")
print(f"issues={','.join(issues)}")
if ready:
    print("required_confirmation=REAL_K8S_PREFLIGHT_CONFIRM=I_UNDERSTAND_THIS_WILL_QUERY_K8S_API")
else:
    print("next_action=copy .env.real-canary.example to .env.real-canary and prepare real-kubeconfig/sealos-canary.yaml")

if strict and not ready:
    raise SystemExit(1)
PY
