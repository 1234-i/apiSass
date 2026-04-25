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
- 新增真实开站脚本骨架：`scripts/real_open_station.sh`。它有强制确认闸门，默认不会运行真实外部操作。
- 新增真实链路文档：`docs/REAL_OPEN_STATION_FLOW.md`。

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
