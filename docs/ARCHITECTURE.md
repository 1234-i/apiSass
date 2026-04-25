# 架构说明

## 目标

构建一个 AI API 中转 SaaS 控制面，让下游站长可以自动获得自己的 New API 分站，并由平台统一接入 Sub2API 上游号池。

## 分层

```text
SaaS 控制面（本项目）
  ├─ 租户 / 域名 / quota / job / 实例状态
  ├─ Sealos/K8s 部署编排
  ├─ New API 初始化编排
  ├─ Sub2API upstream 绑定编排
  └─ Cloudflare/custom domain 编排

New API runtime
  ├─ 每个标准站长一个实例
  ├─ 处理下游用户、token、计费、模型渠道
  └─ 上游 channel 指向 Sub2API

Sub2API upstream pool
  ├─ 管理上游订阅号池 / API key / OAuth
  ├─ 分片、并发控制、粘性会话
  └─ 不直接暴露给下游站长
```

## v0.5 mock 模式

默认配置：

```env
K8S_APPLY_MODE=mock
NEWAPI_MOCK=true
SUB2API_MOCK=true
CLOUDFLARE_MOCK=true
```

mock 模式的意义：

- 先验证控制面编排逻辑。
- 不依赖真实 Sealos、真实域名、真实 API Key。
- 所有外部调用都产生可检查的 mock 结果和 job 日志。
- 生成的 manifest 仍然是真实 Kubernetes YAML。

## 租户生命周期

```text
POST /tenants
  -> 创建 tenant/domain/quota/upstream
  -> 生成 New API manifest
  -> tenant.status = manifest_generated

POST /tenants/{id}/deploy
  -> 校验 manifest
  -> mock apply
  -> mock wait ready
  -> 写 mock-runtime/<slug>.json
  -> instance.status = running_mock

POST /tenants/{id}/init-newapi
  -> mock create admin
  -> mock create token
  -> instance.status = newapi_initialized_mock

POST /tenants/{id}/bind-upstream
  -> mock verify Sub2API key
  -> mock create New API channel
  -> upstream.status = bound_mock

POST /tenants/{id}/provision
  -> 串联 deploy/init/bind/verify
  -> tenant.status = active_mock
```

## 为什么标准站长先用独立 New API 实例

MVP 阶段不建议把所有站长塞进一个共享 New API：

- 独立实例隔离故障域。
- 站长自定义域名、Logo、配置更简单。
- 出问题可以单独暂停/删除 runtime。
- 后续可升级为 VIP 独立 DB/Redis/上游池。

## 真实上线时要补齐

- deployment worker，不让 API 容器直接持有 kubeconfig。
- Alembic 迁移。
- 密码和 API key 加密存储。
- New API / Sub2API 真实管理 API adapter。
- Cloudflare for SaaS 真实 custom hostname。
- Redis 租户级 RPM/TPM/并发限流。
- 上游池分片、健康检查、冷却和自动隔离。
