# v0.9 Mock Worker / Retry / Recovery Contract

v0.9 把 v0.8 的 Provision Workflow Job 继续向“准生产任务编排层”推进，但默认仍然只执行 mock/dry-run：

```env
ALLOW_REAL_EXTERNAL_CALLS=false
APPLY_K8S=false
K8S_APPLY_MODE=mock
NEWAPI_MOCK=true
SUB2API_MOCK=true
CLOUDFLARE_MOCK=true
```

因此，本版本不会调用真实 Sealos、kubectl、New API、Sub2API、Cloudflare、DNS 或任何真实 API key。

## 新增接口

### 创建 queued job

```bash
POST /api/v1/tenants/{tenant_id}/jobs/provision
```

请求体：

```json
{
  "dry_run": true,
  "verify_domains": true,
  "run_inline": false,
  "idempotency_key": "tenant-a-provision-v1",
  "max_attempts": 3
}
```

`run_inline=false` 时，job 会保持 `queued`，等待 mock worker 或手动 run。

### 手动运行 job

```bash
POST /api/v1/jobs/{job_id}/run
```

```json
{"worker_id":"operator-cli","force":false}
```

### 取消 queued job

```bash
POST /api/v1/jobs/{job_id}/cancel
```

```json
{"reason":"operator cancelled before deploy"}
```

只有 `queued` / `pending` 状态能取消。

### mock worker tick

```bash
POST /api/v1/workers/mock/provision/tick
```

```json
{"worker_id":"mock-worker-1","limit":5}
```

该接口会按创建时间扫描 queued provision jobs，并内联执行。它只是 worker 合约模拟，不会产生真实外部调用。

### mock failure injection

为了让 Codex 在本地验证失败恢复，Provision Job 可以传入：

```json
{
  "run_inline": true,
  "simulate_failure_phase": "bind_upstream",
  "max_attempts": 2
}
```

支持的 mock failure phase：

- `deploy`
- `init_newapi`
- `bind_upstream`
- `domains`
- `complete`

失败 job 会返回 HTTP 200，但 `status=failed`，并在 audit events 中记录 `job.failed` 和 `job.retry_available`。

### retry failed job

```bash
POST /api/v1/jobs/{job_id}/retry
```

```json
{
  "run_inline": true,
  "worker_id": "retry-worker",
  "clear_simulated_failure": true
}
```

默认会清除 mock failure injection，然后立即重新运行。真实接入前，这个接口用于验证 operator recovery 流程。

## 事件流

典型成功事件：

```text
job.created
job.attempt.started
job.started
phase.deploy.started
phase.deploy.succeeded
phase.init_newapi.started
phase.init_newapi.succeeded
phase.bind_upstream.started
phase.bind_upstream.succeeded
phase.domains.started
phase.domains.succeeded
job.succeeded
```

典型失败/恢复事件：

```text
job.failed
job.retry_available
job.retried
job.attempt.started
job.succeeded
```

## 未来真实 worker 接入建议

当前版本所有 worker 行为都在 API 进程中 mock 执行。真实生产建议改为：

```text
控制面 API 只创建 job
外部 deployment worker 拉取 queued job
worker 持有 Sealos kubeconfig / Cloudflare token / New API admin token
worker 写回 job status + audit events
```

这样可以避免控制面直接持有高危凭据，也便于横向扩展和按故障域隔离。
