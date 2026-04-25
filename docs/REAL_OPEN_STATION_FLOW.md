# v0.10-realflow：真实开站工厂收口方案

本版本以 v0.10 为基线，不引入 v0.11 billing/usage。站长结算先复用 Sub2API 自带的下游 key、费用账单和用量统计。

## 默认安全原则

默认 `.env.example` 中：

```env
ALLOW_REAL_EXTERNAL_CALLS=false
APPLY_K8S=false
K8S_APPLY_MODE=mock
NEWAPI_MOCK=true
SUB2API_MOCK=true
CLOUDFLARE_MOCK=true
```

所以本地验证、Codex 验证、CI 测试都不会真实调用：

- Sealos/Kubernetes
- New API 管理 API
- Sub2API
- Cloudflare
- DNS/证书系统

## 真实开站链路

目标链路：

```text
POST /tenants
  -> 生成 tenant/subdomain/quota/upstream/manifest
POST /deploy
  -> kubectl apply 到 Sealos/K8s
  -> 等待 New API Deployment ready
POST /init-newapi
  -> 使用 New API Access Token 调用 New API 管理 API
  -> 可创建 token；管理员 bootstrap 若版本不支持 API，则人工/首次 UI 完成
POST /bind-upstream
  -> 把 Sub2API endpoint + Sub2API tenant key 写入 New API channel
POST /domains/{id}/verify
  -> 平台泛域名直接 active；自定义域名可走 Cloudflare for SaaS
```

## 真实模式配置

最低需要：

```env
ALLOW_REAL_EXTERNAL_CALLS=true
APPLY_K8S=true
K8S_APPLY_MODE=real
KUBECONFIG_PATH=/app/.kube/config
BASE_DOMAIN=yourdomain.com
PUBLIC_GATEWAY_CNAME=ingress.yourdomain.com
K8S_INGRESS_CLASS=<your-sealos-ingress-class>
K8S_TLS_SECRET_NAME=<your-wildcard-tls-secret>
NEWAPI_SQL_DSN_TEMPLATE=postgresql://user:pass@host:5432/newapi_{slug}
NEWAPI_REDIS_CONN_TEMPLATE=redis://:pass@host:6379/0
NEWAPI_MOCK=false
NEWAPI_ADMIN_TOKEN=<New API access token>
SUB2API_BASE_URL=https://sub2api.yourdomain.com
SUB2API_TENANT_KEY=<key-created-in-sub2api-for-this-station-or-shared-test-key>
SUB2API_MOCK=false
```

可选：

```env
NEWAPI_ADMIN_USER_ID=<user id if your New API version requires New-Api-User header>
NEWAPI_CHANNEL_PAYLOAD_TEMPLATE={"mode":"single","channel":{"name":"{name}","type":{channel_type},"key":"{api_key}","base_url":"{base_url}","models":"{models}","group":"{group}","status":1}}
```

## 使用 Sub2API 账单的建议

因为 Sub2API 内置了下游 key、费用账单和用量统计，当前控制面不重复做 billing。建议流程：

1. 在 Sub2API 中创建一个下游站长 key。
2. 把这个 key 填到 `SUB2API_TENANT_KEY`。
3. 控制面创建 New API 站点时，把 Sub2API 作为 New API channel 的上游。
4. 下游站长的消耗和结算先在 Sub2API 中查看。

后续如果你要每个站长自动创建 Sub2API key，再补 Sub2API 管理 API 适配器即可；当前版本把这个位置留好，但不冒充不同版本的管理 API。

## 真实开站前预检

```bash
./scripts/real_flow_preflight.sh
```

返回 `status=ready_for_real` 才建议继续真实开站。

## 真实开站脚本

脚本有强制确认，避免误触发：

```bash
REAL_FLOW_CONFIRM=I_UNDERSTAND_THIS_CAN_TOUCH_SEALOS \
SLUG=my-first-real-station \
EMAIL=station@example.com \
STATION_NAME='My First Real Station' \
./scripts/real_open_station.sh
```

## 需要人工验证的点

真实模式第一次跑通时，建议你只做一个测试站：

1. `kubectl get ns` 能看到租户 namespace。
2. `kubectl get deploy -n <namespace>` ready。
3. `kubectl get ingress -n <namespace>` host 正确。
4. `https://<slug>.<BASE_DOMAIN>` 能打开 New API。
5. New API 内能看到绑定的 Sub2API channel。
6. 用 New API 生成的 token 调用 `/v1/models` 或轻量接口。
7. Sub2API 后台能看到该 key 的用量记录。

## 不要在第一次真实开站时做的事

- 不要一次创建多个租户。
- 不要同时打开 Cloudflare 自定义域名自动化。
- 不要把所有上游 key 暴露给 New API 租户。
- 不要跳过 Sub2API 单 key/小额度测试。
- 不要把 `ALLOW_REAL_EXTERNAL_CALLS=true` 放到默认 `.env.example`。
