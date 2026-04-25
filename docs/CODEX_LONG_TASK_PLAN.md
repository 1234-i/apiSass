# Codex 长任务计划

当前版本：v0.5 dry-run/mock 可验证版。

## 已完成

- FastAPI 控制面
- PostgreSQL / Redis / Docker Compose
- 租户创建与查询
- New API K8s/Sealos manifest 生成
- Namespace/Secret/Deployment/Service/Ingress/HPA 输出
- Phase 2 `/deploy` mock apply + wait ready
- Phase 3 `/init-newapi` mock 初始化 New API
- Phase 4 `/bind-upstream` mock 绑定 Sub2API upstream
- Phase 5 custom domain + Cloudflare for SaaS mock 验证
- `/provision` 一键串联 Phase 2-5
- `mock-runtime/<slug>.json` 状态文件
- Redis RPM 限流验证
- smoke/local_validate 脚本兼容 python3/python

## Codex 下一步任务：从 mock 到真实适配

### Task 1：真实 Sealos/Kubernetes apply worker

目标：不要让 API 容器直接持有 kubeconfig，把部署动作拆成 worker。

要求：

1. 新增 deployment worker 进程或服务。
2. API 创建 `DeploymentJob`。
3. worker 读取 pending job。
4. worker 执行 kubectl apply / wait ready / delete。
5. worker 回写 job 和 instance 状态。
6. 保留 `K8S_APPLY_MODE=mock|dry-run|real`。

### Task 2：真实 New API 管理接口适配

目标：把 mock 的 `NewAPIClient` 替换为真实版本。

要求：

1. 根据 New API 当前版本确认管理员初始化方式。
2. 实现登录 / 获取 token / 创建 channel / 创建 token。
3. 为不同 New API 版本保留 adapter。
4. 失败时写 job 日志。
5. 不要把 admin password/token 明文返回给前端。

### Task 3：真实 Sub2API 管理接口适配

目标：把 Sub2API 上游 key 创建、校验、分池打通。

要求：

1. 确认 Sub2API 当前管理 API。
2. 实现创建 tenant key / policy / quota。
3. 支持多个上游池 shard。
4. 每个租户只拿到自己的 key。
5. 失败自动回滚 New API channel 或标记 pending。

### Task 4：Cloudflare for SaaS 真实 custom hostname

目标：站长自定义域名自动验证和证书签发。

要求：

1. 实现 create custom hostname。
2. 实现 hostname status polling。
3. 保存 validation records。
4. 支持 pending / active / failed 状态。
5. 支持后台重新验证。

### Task 5：租户级风控

目标：不要让一个站长拖垮全部号池。

要求：

1. Redis token bucket / sliding window。
2. 租户级 RPM / TPM / 并发。
3. 上游 shard 失败率监控。
4. 异常租户隔离。
5. VIP 租户专属池。

### Task 6：生产化安全

目标：避免 MVP 直接上线造成安全问题。

要求：

1. 密码 hash，不再保存明文 `admin_password`。
2. API key 加密存储。
3. 管理后台 OAuth/OIDC。
4. 操作审计日志。
5. DB 迁移改为 Alembic。
6. 敏感字段不进入 job.message。

## 验收命令

```bash
./scripts/local_validate.sh
```

必须通过后才能进入真实外部服务联调。

## v0.7 后续 Codex 任务建议

1. 保持 `ALLOW_REAL_EXTERNAL_CALLS=false`，不要开启真实外部调用。
2. 增加 pytest，对 `/api/v1/system/preflight`、`/deployment-plan`、`/provision` 做 API 级测试。
3. 设计 deployment worker：控制面只创建 job，worker 才持有 kubeconfig。
4. 给 New API/Sub2API/Cloudflare 客户端补真实接口契约测试，但先全部使用 mock server。
5. 在真实 Sealos 接入前，把所有敏感配置移入 Secret，不要写入 manifest 明文。


## v0.9 note

新增 mock worker queue、job cancel/run/retry、failure injection/recovery，详见 `docs/WORKFLOW_WORKER.md`。
