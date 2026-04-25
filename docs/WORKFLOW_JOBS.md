# v0.8 Provision Workflow Jobs

v0.8 新增一个本地可验证的编排任务层，用来为未来真实 Sealos worker 做准备。默认仍为 mock/dry-run，不会触发任何真实 Sealos、New API、Sub2API、Cloudflare、DNS、kubectl 或 API key 操作。

## 为什么需要 Workflow Job

之前的 `/provision` 是同步一键串联接口。它适合 MVP 验证，但真实 SaaS 开站需要：

- 可追踪的 job id
- 幂等重放，避免重复开站
- 每个阶段的审计事件
- 失败后能看到失败阶段和 partial result
- 未来可以替换成异步 worker / queue

## 新接口

### 创建并执行 Provision Job

```bash
curl -X POST http://localhost:8080/api/v1/tenants/$TENANT_ID/jobs/provision \
  -H "X-API-Key: change-me-admin-token" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "verify_domains": true,
    "run_inline": true,
    "idempotency_key": "tenant-demo-provision-v1"
  }'
```

默认 `run_inline=true`，在本地 mock 模式下会立即完成。未来真实接入时可以改成 `run_inline=false`，由外部 worker 消费 job。

### 查询 Job

```bash
curl -H "X-API-Key: change-me-admin-token" \
  http://localhost:8080/api/v1/jobs/$JOB_ID
```

### 查询 Job 事件

```bash
curl -H "X-API-Key: change-me-admin-token" \
  http://localhost:8080/api/v1/jobs/$JOB_ID/events
```

### 查询租户审计事件

```bash
curl -H "X-API-Key: change-me-admin-token" \
  'http://localhost:8080/api/v1/tenants/$TENANT_ID/audit-events?limit=50'
```

## 事件类型

典型事件包括：

- `job.created`
- `job.started`
- `phase.deploy.started`
- `phase.deploy.succeeded`
- `phase.init_newapi.started`
- `phase.init_newapi.succeeded`
- `phase.bind_upstream.started`
- `phase.bind_upstream.succeeded`
- `phase.domains.started`
- `phase.domains.succeeded`
- `job.succeeded`
- `job.idempotent_reuse`
- `job.failed`

## 安全边界

Provision Workflow Job 只调用已有的安全适配层：

- `deploy_instance()` 默认 mock/dry-run
- `init_newapi()` 默认 mock
- `bind_upstream()` 默认 mock
- `verify_domain()` 默认 mock

只要 `.env` 保持：

```env
ALLOW_REAL_EXTERNAL_CALLS=false
APPLY_K8S=false
K8S_APPLY_MODE=mock
NEWAPI_MOCK=true
SUB2API_MOCK=true
CLOUDFLARE_MOCK=true
```

就不会进行任何真实外部操作。
