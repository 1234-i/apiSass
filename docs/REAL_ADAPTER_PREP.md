# v0.7 真实接入前适配层准备说明

本项目 v0.7 仍然默认保持 **mock/dry-run 安全模式**，不会调用真实 Sealos/Kubernetes、New API、Sub2API、Cloudflare 或域名服务。

v0.7 的新增重点是：把测试也放进容器镜像，让 Codex 可以在和 API 相同的运行环境里验证安全闸门和适配层契约。

## 全局安全闸门

`.env.example` 默认：

```env
ALLOW_REAL_EXTERNAL_CALLS=false
APPLY_K8S=false
K8S_APPLY_MODE=mock
NEWAPI_MOCK=true
SUB2API_MOCK=true
CLOUDFLARE_MOCK=true
```

即使误把 `NEWAPI_MOCK=false`、`SUB2API_MOCK=false`、`CLOUDFLARE_MOCK=false` 或 `K8S_APPLY_MODE=real`，只要 `ALLOW_REAL_EXTERNAL_CALLS=false`，服务层仍会走 mock/dry-run。

## 预检接口

```bash
curl http://localhost:8080/api/v1/system/preflight \
  -H 'X-API-Key: change-me-admin-token'
```

这个接口只检查本地配置和文件存在性，不会调用外部系统。

返回内容包括：

- 是否处于 safe mock/dry-run 模式
- Kubernetes apply 模式
- kubeconfig 文件是否存在
- kubectl 是否存在
- New API/Sub2API/Cloudflare token 是否配置，但不会泄露 token
- 真实调用是否可能发生
- 配置警告

## 租户部署计划接口

```bash
curl http://localhost:8080/api/v1/tenants/<tenant_id>/deployment-plan \
  -H 'X-API-Key: change-me-admin-token'
```

它会输出：

- tenant endpoint
- instance namespace/name/status
- manifest 校验结果
- upstream key 后缀
- Phase 2-5 每一步对应的 API
- 每一步是否会调用外部系统
- `/provision` 一键串联建议 body

## 容器内适配层契约测试

```bash
./scripts/container_tests.sh
```

或：

```bash
docker compose --profile test run --rm tests
```

当前测试会验证：

- 默认设置下所有外部调用被全局安全闸门阻止。
- 即使组件 mock flag 被关闭，只要 `ALLOW_REAL_EXTERNAL_CALLS=false`，New API/Sub2API/Cloudflare/K8s 仍保持 mock/dry-run。
- safe snapshot 不泄露真实 token 值。
- Kubernetes manifest 会被校验，但不会真实 apply。

## 未来真实 Sealos 接入建议

不要直接让 Web API 容器持有长期 kubeconfig。更推荐：

1. 控制面只创建 deployment job。
2. 独立 deployment worker 持有 Sealos kubeconfig。
3. worker 从 DB/队列领取 job。
4. worker 执行 kubectl apply/rollout/delete。
5. worker 回写 job 状态和 instance 状态。

v0.7 先保留 `kubectl_apply()` 适配点，但默认不会执行。

## 真实调用开启条件

未来调试真实调用时，至少要同时满足：

```env
ALLOW_REAL_EXTERNAL_CALLS=true
```

并按组件分别设置：

```env
# K8s/Sealos
APPLY_K8S=true
K8S_APPLY_MODE=real
KUBECONFIG_PATH=/app/.kube/config

# New API
NEWAPI_MOCK=false
NEWAPI_ADMIN_TOKEN=...

# Sub2API
SUB2API_MOCK=false
SUB2API_ADMIN_KEY=...

# Cloudflare
CLOUDFLARE_MOCK=false
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ZONE_ID=...
```

v0.7 不建议在生产前打开这些配置；请先让 Codex/开发者用 preflight、deployment-plan 和 container tests 验证配置不会误触发外部操作。
