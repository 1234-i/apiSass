#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path
import sys

minimum_lines = {
    ".env.example": 50,
    ".env.real-canary.example": 50,
    ".env.real.example": 35,
    "scripts/local_validate.sh": 15,
    "scripts/check_env_files.sh": 40,
    "scripts/real_k8s_canary_static_check.sh": 70,
    "scripts/real_k8s_canary_doctor.sh": 100,
    "scripts/real_k8s_canary_doctor_matrix.sh": 100,
    "scripts/real_k8s_canary_preflight.sh": 80,
    "scripts/real_k8s_canary_server_dry_run.sh": 120,
    "scripts/real_k8s_canary_server_dry_run_static_check.sh": 80,
    "scripts/real_k8s_canary_open.sh": 80,
    "scripts/real_k8s_canary_cleanup.sh": 40,
}

required_markers = {
    ".env.example": ("APP_NAME=", "ALLOW_REAL_EXTERNAL_CALLS=", "NEWAPI_MOCK=", "SUB2API_MOCK=", "CLOUDFLARE_MOCK="),
    ".env.real-canary.example": (
        "ALLOW_REAL_EXTERNAL_CALLS=true",
        "REAL_EXTERNAL_ALLOWLIST=k8s",
        "REAL_K8S_PREFLIGHT_CONFIRM=",
        "NEWAPI_MOCK=true",
        "SUB2API_MOCK=true",
        "CLOUDFLARE_MOCK=true",
    ),
    ".env.real.example": ("ALLOW_REAL_EXTERNAL_CALLS=true", "NEWAPI_MOCK=false", "APPLY_K8S=true"),
    "scripts/real_k8s_canary_preflight.sh": ("REAL_K8S_PREFLIGHT_CONFIRM", "I_UNDERSTAND_THIS_WILL_QUERY_K8S_API", "kubectl auth can-i"),
    "scripts/real_k8s_canary_server_dry_run.sh": (
        "REAL_K8S_SERVER_DRY_RUN_CONFIRM",
        "I_UNDERSTAND_THIS_WILL_QUERY_K8S_API_WITH_SERVER_DRY_RUN_BUT_NOT_CREATE_RESOURCES",
        "--dry-run=server",
    ),
    "scripts/real_k8s_canary_server_dry_run_static_check.sh": (
        "real k8s canary server dry-run static checks passed without calling kubectl",
        "--dry-run=server",
    ),
    "scripts/real_k8s_canary_doctor.sh": ("will_call_k8s_api=false", "ready_for_human_authorized_preflight", "I_UNDERSTAND_THIS_WILL_QUERY_K8S_API"),
    "scripts/real_k8s_canary_doctor_matrix.sh": ("doctor matrix case A", "doctor matrix case D", "I_UNDERSTAND_THIS_WILL_QUERY_K8S_API"),
    "scripts/local_validate.sh": ("check_source_format.sh", "check_env_files.sh", "real_k8s_canary_doctor.sh", "real_k8s_canary_server_dry_run_static_check.sh", "real_k8s_canary_doctor_matrix.sh", "docker compose up", "container_tests.sh"),
}

failed = False

for name, min_lines in minimum_lines.items():
    path = Path(name)
    if not path.exists():
        print(f"{name}: missing", file=sys.stderr)
        failed = True
        continue

    data = path.read_bytes()
    if b"\r" in data:
        print(f"{name}: contains CR/CRLF line endings", file=sys.stderr)
        failed = True

    text = data.decode("utf-8")
    lines = text.splitlines()
    if len(lines) < min_lines:
        print(f"{name}: expected at least {min_lines} lines, got {len(lines)}", file=sys.stderr)
        failed = True

    if name.endswith(".sh") and not text.startswith("#!/usr/bin/env bash\n"):
        print(f"{name}: shell script must start with bash shebang on its own line", file=sys.stderr)
        failed = True

    if any(len(line) > 1000 for line in lines):
        print(f"{name}: contains a line over 1000 chars; possible newline collapse", file=sys.stderr)
        failed = True

    for marker in required_markers.get(name, ()):
        if marker not in text:
            print(f"{name}: missing marker {marker!r}", file=sys.stderr)
            failed = True

    print(f"ok {name} source format")

if failed:
    raise SystemExit(1)
PY
