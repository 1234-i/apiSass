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

Step 3 must not run while Step 2 reports a PodSecurity restricted warning. The New API Deployment manifest must pass server-side dry-run without `would violate PodSecurity` before any persistent apply is considered.

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

The script captures host and container `kubectl apply --dry-run=server` output and fails if Kubernetes reports restricted PodSecurity fields such as `allowPrivilegeEscalation`, `capabilities.drop`, `runAsNonRoot`, or `seccompProfile`.

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

## PodSecurity Restricted Hardening

The rendered New API Deployment includes:

- `spec.template.spec.automountServiceAccountToken=false`
- `spec.template.spec.securityContext.runAsNonRoot=true`
- `spec.template.spec.securityContext.seccompProfile.type=RuntimeDefault`
- `spec.template.spec.containers[].securityContext.allowPrivilegeEscalation=false`
- `spec.template.spec.containers[].securityContext.capabilities.drop=[ALL]`

Do not add `readOnlyRootFilesystem=true` until the New API image write paths are confirmed. The current hardening intentionally targets the fields reported by Kubernetes PodSecurity restricted warnings.

Optional pod identity fields are available but disabled by default:

```env
K8S_POD_RUN_AS_USER=
K8S_POD_RUN_AS_GROUP=
K8S_POD_FS_GROUP=
```

Set them only after confirming the New API image can run with that UID/GID and the required filesystem permissions. The ServiceAccount token warning emitted by kubectl can come from the kubeconfig token type; record it, but do not treat it as a manifest blocker unless Sealos rejects the request.

## Step 3 Guarded Apply And Cleanup

Step 3 is the first Real Canary phase that creates persistent Kubernetes resources. It must be separately authorized by a human for that exact run.

The only allowed Step 3 entrypoint is:

```bash
REAL_K8S_APPLY_CLEANUP_CONFIRM=I_UNDERSTAND_THIS_WILL_CREATE_K8S_RESOURCES_AND_THEN_CLEAN_THEM_UP \
SLUG=canary-real-apply-001 \
EMAIL=canary@example.com \
bash ./scripts/real_k8s_canary_apply_and_cleanup.sh
```

Step 3 will:

- create real Kubernetes canary resources in the configured test namespace
- call `/api/v1/tenants/{tenant_id}/deploy` with `{"dry_run": false}`
- refuse placeholder test DB/Redis settings before apply
- keep New API, Sub2API, Cloudflare, domain, and API-key operations mocked
- avoid `/api/v1/tenants/{tenant_id}/provision`
- run the Step 2 server-side dry-run first
- attempt cleanup on success or failure

Step 3 must use test infrastructure only:

- a test Sealos namespace
- test PostgreSQL and Redis values usable by the New API pod
- no production DB/Redis
- no production domain automation

When `K8S_CANARY_MODE=true`, manifests keep the stable selector label:

```yaml
app: newapi-<slug>
```

The canary labels are added separately for cleanup and audit:

```yaml
api-saas.weisoft.chat/canary: "true"
api-saas.weisoft.chat/tenant-slug: <slug>
```

Those canary labels must not be added to Deployment or Service selectors. Cleanup and post-check use the combined selector:

```bash
app=newapi-${SLUG},api-saas.weisoft.chat/canary=true,api-saas.weisoft.chat/tenant-slug=${SLUG}
```

The canary annotations are:

```yaml
api-saas.weisoft.chat/canary-created-at: "<timestamp>"
api-saas.weisoft.chat/canary-max-lifetime-seconds: "600"
```

The TTL annotation is an audit marker only; cleanup is still performed by the Step 3 wrapper.
