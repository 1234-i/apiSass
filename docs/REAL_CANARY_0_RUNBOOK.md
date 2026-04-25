# Real Canary 0 Runbook

Current phase: local/mock/dry-run readiness only.

## Codex May Run

- `bash ./scripts/check_source_format.sh`
- `bash ./scripts/check_env_files.sh`
- `bash ./scripts/check_env_files.sh .env.real-canary`
- `bash ./scripts/real_k8s_canary_static_check.sh`
- `bash ./scripts/real_k8s_canary_doctor.sh`
- `bash ./scripts/local_validate.sh`
- `docker compose exec api pytest -q tests`

These checks are local-only or Docker-local. The offline doctor does not call `kubectl`, `curl`, `docker compose exec`, Sealos, New API, Sub2API, Cloudflare, DNS, or API-key services.

## Codex Must Not Run Without Human-Specific Authorization

- `bash ./scripts/real_k8s_canary_preflight.sh`
- `bash ./scripts/real_k8s_canary_open.sh`
- `bash ./scripts/real_k8s_canary_cleanup.sh`

The preflight script calls the Kubernetes API through `kubectl auth can-i`. The open and cleanup scripts can create, update, or delete real Kubernetes resources. They require explicit human authorization for that specific action in the Codex thread.

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
REAL_K8S_PREFLIGHT_CONFIRM=I_UNDERSTAND_THIS_TOUCHES_K8S_API \
bash ./scripts/real_k8s_canary_preflight.sh
```

That command queries the Kubernetes API but must not mutate resources.
