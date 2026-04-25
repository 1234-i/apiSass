# 本地验证

## 一键验证

```bash
cp -n .env.example .env
./scripts/local_validate.sh
```

验证成功时会看到：

- `/health` 返回 ok
- `/ready` 返回 ready
- 创建租户成功
- manifest validation 返回 ok=true
- `/deploy` 返回 `running_mock`
- `/init-newapi` 返回 mocked
- `/bind-upstream` 返回 mocked
- custom domain verify 返回 `mock_active`
- `/provision` 返回 `active_mock`
- `/api/v1/mock/runtime/<slug>` 有 runtime state
- manifest 输出包含 Namespace/Secret/Deployment/Service/Ingress/HPA
- `/api/v1/system/preflight` 显示 safe_mode=true
- 容器内 `pytest -q tests` 通过

## macOS Python 兼容性

`scripts/smoke_test.sh` 已自动选择 `python3`，没有 `python3` 时才回退到 `python`。

Host-side pytest requires Python >= 3.10 because the codebase uses modern union type annotations such as `str | None`. The recommended validation path is Docker:

```bash
./scripts/local_validate.sh
docker compose exec api pytest -q tests
```

Do not treat host Python 3.9 pytest collection failures as application regressions; run pytest in the Python 3.12 container instead.

## 容器内测试

v0.7 开始 Dockerfile 会复制 `tests/`，可以直接运行：

```bash
./scripts/container_tests.sh
```

也可以使用 Compose test profile：

```bash
docker compose --profile test run --rm tests
```

## 单独检查适配层安全状态

```bash
./scripts/adapter_preflight.sh
```

这个接口只做本地配置检查，不调用真实 Sealos/New API/Sub2API/Cloudflare。

## 清理

```bash
docker compose down -v --remove-orphans
rm -rf generated-manifests mock-runtime
```


## v0.9 note

新增 mock worker queue、job cancel/run/retry、failure injection/recovery，详见 `docs/WORKFLOW_WORKER.md`。
## Host 脚本权限检查

从 v0.10 开始，发布 zip 内的 `scripts/*.sh` 会保留可执行权限。解压后可以先运行：

```bash
./scripts/check_host_permissions.sh
```

期望输出：

```text
script permission check OK
```

随后直接运行：

```bash
./scripts/local_validate.sh
```
