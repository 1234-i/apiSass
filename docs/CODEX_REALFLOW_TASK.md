# 给 Codex 的下一阶段任务：v0.10-realflow 真实开站收口

## 目标

以 v0.10-realflow 为基线，把开站工厂跑通到真实 Sealos，但默认验证仍保持 mock/dry-run。

## 不做

- 不做 SaaS billing/usage。
- 不引入 v0.11 billing 代码。
- 不在默认本地验证中调用真实 Sealos/Sub2API/New API/Cloudflare。

## 验证任务

1. 运行：

```bash
./scripts/local_validate.sh
```

2. 检查：

```bash
./scripts/real_flow_preflight.sh
```

默认应返回 `not_ready_for_real`，且 `safe_mode=true`。

3. 确认 manifest 包含：

- Namespace
- Secret
- Deployment
- Service
- Ingress
- HorizontalPodAutoscaler
- Secret 中包含 `SQL_DSN`、`REDIS_CONN_STRING`、`SESSION_SECRET`、`CRYPTO_SECRET`、`STREAMING_TIMEOUT`

4. 确认 New API channel payload contract：

```bash
docker compose exec api pytest -q tests
```

## 真实模式只做代码审查，不默认执行

真实模式需要用户提供：

- Sealos kubeconfig
- BASE_DOMAIN / PUBLIC_GATEWAY_CNAME
- K8S_INGRESS_CLASS / TLS secret
- New API DB/Redis DSN template
- New API Access Token
- Sub2API tenant key

拿到这些后，先让用户运行：

```bash
./scripts/real_flow_preflight.sh
```

只有 `status=ready_for_real` 后，才建议运行：

```bash
REAL_FLOW_CONFIRM=I_UNDERSTAND_THIS_CAN_TOUCH_SEALOS ./scripts/real_open_station.sh
```
