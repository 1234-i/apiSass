# Real Canary 0 Runbook

Current phase: local/mock/dry-run readiness only.

## Codex May Run

- `bash ./scripts/check_source_format.sh`
- `bash ./scripts/check_env_files.sh`
- `bash ./scripts/check_env_files.sh .env.real-canary`
- `bash ./scripts/real_k8s_canary_static_check.sh`
- `bash ./scripts/real_k8s_canary_server_dry_run_static_check.sh`
- `bash ./scripts/real_k8s_canary_doctor.sh`
- `bash ./scripts/real_k8s_canary_doctor_matrix.sh`
- `bash ./scripts/local_validate.sh`
- `docker compose exec api pytest -q tests`

These checks are local-only or Docker-local. The offline doctor does not call `kubectl`, `curl`, `docker compose exec`, Sealos, New API, Sub2API, Cloudflare, DNS, or API-key services.
The doctor matrix creates only fake local files and refuses to run if `.env.real-canary` or `real-kubeconfig` already exists.

## Codex Must Not Run Without Human-Specific Authorization

- `bash ./scripts/real_k8s_canary_preflight.sh`
- `bash ./scripts/real_k8s_canary_server_dry_run.sh`
- `bash ./scripts/real_k8s_canary_open.sh`
- `bash ./scripts/real_k8s_canary_cleanup.sh`

The preflight script calls the Kubernetes API through `kubectl auth can-i`.
The server-side dry-run script calls the Kubernetes API server through `kubectl apply --dry-run=server`; it must not persist resources.
The open and cleanup scripts can create, update, or delete real Kubernetes resources. They require explicit human authorization for that specific action in the Codex thread.

## Offline Doctor

Run:

```bash
bash ./scripts/real_k8s_canary_doctor.sh
```

Expected not-configured output before real credentials are prepared:

```text
real_k8s_canary_doctor_status=not_configured
safe_to_run_real_preflight=false
will_call_k8s_api=false
will_call_newapi=false
will_call_sub2api=false
will_call_cloudflare=false
missing=.env.real-canary,real-kubeconfig/sealos-canary.yaml
```

Strict mode is useful for CI or a final readiness gate:

```bash
bash ./scripts/real_k8s_canary_doctor.sh --strict
```

In strict mode, missing `.env.real-canary` or `real-kubeconfig/sealos-canary.yaml` exits non-zero.

## Real Canary 0 Required Local Files

Prepare these files outside Git:

- `.env.real-canary`
- `real-kubeconfig/sealos-canary.yaml`

Both paths are ignored by `.gitignore`.

The env file must keep Real Canary 0 K8s-only:

```env
ALLOW_REAL_EXTERNAL_CALLS=true
REAL_EXTERNAL_ALLOWLIST=k8s
APPLY_K8S=true
K8S_APPLY_MODE=real
K8S_SERVER_DRY_RUN_FIRST=true
K8S_NAMESPACE_MODE=fixed
K8S_CREATE_NAMESPACE=false
NEWAPI_MOCK=true
SUB2API_MOCK=true
CLOUDFLARE_MOCK=true
KUBECONFIG_PATH=/app/.kube/sealos-canary.yaml
```

Keep real New API, Sub2API, Cloudflare, domain, and API-key operations disabled until a later explicitly authorized phase.

## Human-Authorized Preflight

Only after the offline doctor reports:

```text
real_k8s_canary_doctor_status=ready_for_human_authorized_preflight
safe_to_run_real_preflight=true
```

the human may authorize this exact command:

```bash
REAL_K8S_PREFLIGHT_CONFIRM=I_UNDERSTAND_THIS_WILL_QUERY_K8S_API \
bash ./scripts/real_k8s_canary_preflight.sh
```

That command queries the Kubernetes API but must not mutate resources.

## Human-Authorized Server-Side Dry Run

Only after Step 1 preflight passes, the human may separately authorize Step 2:

```bash
REAL_K8S_SERVER_DRY_RUN_CONFIRM=I_UNDERSTAND_THIS_WILL_QUERY_K8S_API_WITH_SERVER_DRY_RUN_BUT_NOT_CREATE_RESOURCES \
SLUG=canary-server-dry-run-001 \
EMAIL=canary@example.com \
bash ./scripts/real_k8s_canary_server_dry_run.sh
```

This command runs `kubectl apply --dry-run=server` against the Kubernetes API server. The purpose is to validate rendered manifests with API-server admission/schema/RBAC checks without persisting resources.

Step 2 must not run:

- `real_k8s_canary_open.sh`
- `real_k8s_canary_cleanup.sh`
- `kubectl apply` without `--dry-run=server`
- `kubectl delete`
- `/api/v1/tenants/{id}/deploy` with `dry_run=false`
- `/api/v1/tenants/{id}/provision`
- New API, Sub2API, Cloudflare, domain, or API-key real operations

Before Step 2, replace placeholder domain values in `.env.real-canary`:

```env
BASE_DOMAIN=example.com
PUBLIC_GATEWAY_CNAME=ingress.example.com
```

with real test values for the canary domain and Sealos ingress. Step 2 does not call DNS or domain APIs, but the manifest should be validated with realistic host values.
