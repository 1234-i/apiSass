# Phase 2-5 dry-run/mock 验证说明

本版本的目标是：在没有真实 Sealos、Sub2API、Cloudflare、域名和 API Key 的情况下，验证控制面的完整编排闭环。

## Phase 2：部署 New API runtime

接口：

```http
POST /api/v1/tenants/{tenant_id}/deploy
```

请求：

```json
{"dry_run": true, "wait_ready": true}
```

行为：

- 校验 manifest 是否包含 Namespace/Secret/Deployment/Service/Ingress/HPA
- 不调用真实 kubectl
- 写入 `mock-runtime/<slug>.json`
- instance.status 更新为 `running_mock`
- tenant.status 更新为 `runtime_ready_mock`

## Phase 3：初始化 New API

接口：

```http
POST /api/v1/tenants/{tenant_id}/init-newapi
```

行为：

- mock 创建管理员
- mock 创建 default runtime token
- instance.status 更新为 `newapi_initialized_mock`

## Phase 4：绑定 Sub2API upstream

接口：

```http
POST /api/v1/tenants/{tenant_id}/bind-upstream
```

行为：

- mock 校验 Sub2API key
- mock 调用 New API create_channel
- upstream.status 更新为 `bound_mock`
- upstream.policy 记录 last_bind 和 sub2api_verify

## Phase 5：域名绑定与验证

接口：

```http
POST /api/v1/tenants/{tenant_id}/domains
POST /api/v1/tenants/{tenant_id}/domains/{domain_id}/verify
```

行为：

- 子域名默认 `wildcard_ready`
- 自定义域名默认返回 CNAME/TXT mock 验证记录
- verify 后 custom domain 状态变为 `active` / `mock_active`

## 一键串联

接口：

```http
POST /api/v1/tenants/{tenant_id}/provision
```

行为：

```text
deploy runtime mock
  -> init New API mock
  -> bind Sub2API mock
  -> verify domains mock
  -> tenant.status = active_mock
```

## 本地验证

```bash
./scripts/local_validate.sh
```
