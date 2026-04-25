# AI API SaaS Control Plane MVP v0.10-realflow

这是以 **v0.10** 为基线收口的“开站工厂真实链路准备版”。它不包含 v0.11 的 billing/usage 代码，因为站长结账先复用 Sub2API 自带账单。

目标：把 **Sealos 官方公有云 + New API + Sub2API** 串成自动开站工厂。

默认仍为 **mock/dry-run 安全模式**：不会触发真实 Sealos、Sub2API、New API、Cloudflare、域名或 API key 操作。

## 本版新增

- 保留 v0.10 已通过验证的 worker/retry/audit/manifest/HPA 能力。
- 新增 `GET /api/v1/system/real-flow-preflight`：真实开站前配置预检，不调用外部系统。
- New API 适配器改为更接近真实管理 API：支持 `Authorization: Bearer`、可选 `New-Api-User`、`/api/channel/`、`/api/token/`。
- Sub2API 适配器支持 `SUB2API_TENANT_KEY`：你可以先在 Sub2API 后台创建站长 key，用 Sub2API 自带账单给下游站长结算。
- New API manifest 增加生产相关 env：`CRYPTO_SECRET`、`TZ`、`STREAMING_TIMEOUT`、`ERROR_LOG_ENABLED`、`BATCH_UPDATE_ENABLED`。
- New API Deployment manifest 增加 Restricted PodSecurity 所需 hardening：关闭自动挂载 ServiceAccount token、Pod 级 `runAsNonRoot`/`RuntimeDefault` seccomp、Container 级 `allowPrivilegeEscalation=false` 和 `capabilities.drop=[ALL]`。
- 新增可选 Pod 身份配置：`K8S_POD_RUN_AS_USER`、`K8S_POD_RUN_AS_GROUP`、`K8S_POD_FS_GROUP`。默认不硬编码 UID/GID，避免在未确认镜像文件权限前影响 rollout。
- 新增真实开站脚本骨架：`scripts/real_open_station.sh`。它有强制确认闸门，默认不会运行真实外部操作。
- 新增 Real Canary 0 离线 doctor：`scripts/real_k8s_canary_doctor.sh` 和 `scripts/real_k8s_canary_doctor_matrix.sh`。它们只检查本地 `.env.real-canary`、kubeconfig 文件状态、gitignore 和安全开关，不调用 Kubernetes API。
- 新增 Real Canary 0 Step 2 server-side dry-run 脚本骨架：`scripts/real_k8s_canary_server_dry_run.sh`。它必须由人类单独授权，只能执行 `kubectl apply --dry-run=server` 做 API server 校验，不持久化资源。
- 新增 Step 2 静态保护：`scripts/real_k8s_canary_server_dry_run_static_check.sh`，并纳入 `local_validate.sh`。该检查不调用 `kubectl`。
- 新增 Real Canary 0 Step 3 护栏脚本：`scripts/real_k8s_canary_apply_and_cleanup.sh`。它必须由人类单独授权，会真实创建 K8s canary 资源并立即 cleanup；本地验证只运行静态检查，不执行该脚本。
- 新增 canary 标签和 TTL annotation：保留 `app=newapi-<slug>` 作为稳定 selector，额外使用 `api-saas.weisoft.chat/canary=true` 和 `api-saas.weisoft.chat/tenant-slug=<slug>` 做 cleanup/post-check。
- 新增真实链路文档：`docs/REAL_OPEN_STATION_FLOW.md`。
- 新增 Real Canary 0 runbook：`docs/REAL_CANARY_0_RUNBOOK.md`。
- 真实 K8s preflight 只允许在人类明确授权后查询 Kubernetes API，确认词为 `I_UNDERSTAND_THIS_WILL_QUERY_K8S_API`。
- 真实 K8s server-side dry-run 只允许在人类明确授权后查询 Kubernetes API server 做 manifest 校验，确认词为 `I_UNDERSTAND_THIS_WILL_QUERY_K8S_API_WITH_SERVER_DRY_RUN_BUT_NOT_CREATE_RESOURCES`。

## 本地一键验证

```bash
cp .env.example .env
./scripts/local_validate.sh
```

覆盖内容：

- Docker Compose build/start `api/db/redis`
- `/health`、`/ready`
- `/api/v1/system/preflight`
- `/api/v1/system/real-flow-preflight`
- 创建租户
- manifest validation
- deployment plan
- mock deploy
- mock init New API
- mock bind Sub2API
- mock custom domain add/verify
- one-shot provision
- Redis RPM check
- workflow job / audit events / idempotency / queued job / cancel / worker tick / failure injection / retry recovery
- container pytest

## 默认安全配置

```env
ALLOW_REAL_EXTERNAL_CALLS=false
APPLY_K8S=false
K8S_APPLY_MODE=mock
NEWAPI_MOCK=true
SUB2API_MOCK=true
CLOUDFLARE_MOCK=true
```

## 真实开站前预检

```bash
./scripts/real_flow_preflight.sh
```

或者：

```bash
curl http://localhost:8080/api/v1/system/real-flow-preflight \
  -H 'X-API-Key: change-me-admin-token'
```

## Real Canary 0

Real Canary 0 分阶段推进，每一步都需要单独授权：

1. `scripts/real_k8s_canary_doctor.sh --strict`
   只做离线检查，不调用 Kubernetes API。
2. `scripts/real_k8s_canary_preflight.sh`
   只做 `kubectl version/current-context/auth can-i` 查询，不创建资源。
3. `scripts/real_k8s_canary_server_dry_run.sh`
   只做 `kubectl apply --dry-run=server`。这会向 Kubernetes API server 提交 manifest 做服务端校验，但不会持久化创建、修改或删除资源。
4. `scripts/real_k8s_canary_apply_and_cleanup.sh`
   真实创建一个 K8s canary runtime，然后无论成功或失败都尝试 cleanup。此步骤必须单独授权，且只允许测试 namespace、测试 DB/Redis 和 K8s 外呼。

Step 2 server-side dry-run 仍然禁止：

- `real_k8s_canary_open.sh`
- `real_k8s_canary_cleanup.sh`
- `kubectl apply` 不带 `--dry-run=server`
- `kubectl delete`
- New API/Sub2API/Cloudflare/domain/API-key 真实调用

Step 2 通过但出现 PodSecurity restricted warning 时，不进入 Step 3。必须先修 manifest securityContext，并要求下一次 server-side dry-run 不再出现 `would violate PodSecurity`。ServiceAccount token warning 可能来自 kubeconfig token 类型；它应记录，但不直接作为 Step 3 blocker，除非 Sealos 明确拒绝该 token。

Step 3 只允许通过 `/api/v1/tenants/{tenant_id}/deploy` 且 body 为 `{"dry_run": false}` 触发真实 K8s apply。Step 3 不允许调用 `/provision`，也不允许调用真实 New API、Sub2API、Cloudflare、domain API 或 API-key 操作。

Step 3 canary cleanup/post-check 使用组合 selector：

```text
app=newapi-<slug>,api-saas.weisoft.chat/canary=true,api-saas.weisoft.chat/tenant-slug=<slug>
```

`api-saas.weisoft.chat/canary` 和 `api-saas.weisoft.chat/tenant-slug` 只用于 metadata cleanup/audit，不进入 Deployment selector 或 Service selector。

## 真实开站脚本骨架

**默认不会执行真实外部调用。** 只有你显式配置真实 `.env` 并设置确认变量后才会运行：

```bash
REAL_FLOW_CONFIRM=I_UNDERSTAND_THIS_CAN_TOUCH_SEALOS \
SLUG=my-first-real-station \
EMAIL=station@example.com \
./scripts/real_open_station.sh
```

真实模式最低需要：

```env
ALLOW_REAL_EXTERNAL_CALLS=true
APPLY_K8S=true
K8S_APPLY_MODE=real
KUBECONFIG_PATH=/app/.kube/config
BASE_DOMAIN=yourdomain.com
PUBLIC_GATEWAY_CNAME=ingress.yourdomain.com
NEWAPI_SQL_DSN_TEMPLATE=postgresql://...
NEWAPI_REDIS_CONN_TEMPLATE=redis://...
NEWAPI_MOCK=false
NEWAPI_ADMIN_TOKEN=...
SUB2API_BASE_URL=https://your-sub2api.example.com
SUB2API_TENANT_KEY=...
SUB2API_MOCK=false
```

Cloudflare 仅在你要自动绑定客户自定义域名时才需要：

```env
CLOUDFLARE_MOCK=false
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ZONE_ID=...
```

## 关键 API

- `GET /api/v1/system/preflight`
- `GET /api/v1/system/real-flow-preflight`
- `POST /api/v1/tenants`
- `GET /api/v1/tenants/{tenant_id}/manifest-validation`
- `GET /api/v1/tenants/{tenant_id}/deployment-plan`
- `POST /api/v1/tenants/{tenant_id}/deploy`
- `POST /api/v1/tenants/{tenant_id}/init-newapi`
- `POST /api/v1/tenants/{tenant_id}/bind-upstream`
- `POST /api/v1/tenants/{tenant_id}/provision`
- `POST /api/v1/tenants/{tenant_id}/jobs/provision`
- `POST /api/v1/workers/mock/provision/tick`

## 为什么先不做 SaaS billing

当前策略是：站长结账先走 Sub2API 内置的下游 key、费用账单和用量统计。控制面只负责开站、部署、初始化、绑定上游和域名，不重复实现账单系统。
