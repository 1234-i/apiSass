# Changelog

## v0.10-realflow

- 以 v0.10 为基线收口“开站工厂”，不引入 v0.11 billing/usage。
- 新增 `GET /api/v1/system/real-flow-preflight`，真实开站前检查配置和安全闸门，默认不调用外部系统。
- New API 真实适配器支持 Bearer Access Token、可选 `New-Api-User`、`/api/channel/`、`/api/token/`，并支持 `NEWAPI_CHANNEL_PAYLOAD_TEMPLATE` 自定义 payload。
- Sub2API 适配器支持 `SUB2API_TENANT_KEY`，可先用 Sub2API 自带账单给下游站长结算。
- New API manifest 增加 `CRYPTO_SECRET`、`TZ`、`STREAMING_TIMEOUT`、`ERROR_LOG_ENABLED`、`BATCH_UPDATE_ENABLED`。
- 新增 `scripts/real_flow_preflight.sh` 和 `scripts/real_open_station.sh`；后者需要强制确认变量，不会误触发真实 Sealos。
- 新增 `docs/REAL_OPEN_STATION_FLOW.md` 与 `docs/CODEX_REALFLOW_TASK.md`。
- 默认仍为 mock/dry-run 安全模式。

## v0.10.0

- 修复 v0.9 zip 发布包中部分 `scripts/*.sh` 没有可执行权限，导致 `./scripts/local_validate.sh` 在 host shell 直接运行失败的问题。
- 新增 `scripts/check_host_permissions.sh`，验证解压后的脚本权限。
- `scripts/local_validate.sh` 开始时执行权限自检；内部调用 `smoke_test.sh`、`adapter_preflight.sh`、`container_tests.sh` 改为显式 `bash`，增强跨环境稳定性。
- `scripts/export_for_codex.sh` 导出前自动 `chmod +x scripts/*.sh`，并导出为 `ai-api-saas-mvp-v0.10.zip`。
- app 版本更新为 `0.10.0`。
- 默认仍为 mock/dry-run 安全模式，不触发真实 Sealos/Sub2API/New API/Cloudflare/域名/API key 操作。

## v0.9.0

- 新增 mock worker / queue 合约：`run_inline=false` 时 Provision Job 会进入 `queued` 状态。
- 新增 `POST /api/v1/jobs/{job_id}/run`，可手动运行 queued job。
- 新增 `POST /api/v1/jobs/{job_id}/cancel`，可取消 queued/pending job。
- 新增 `POST /api/v1/jobs/{job_id}/retry`，可重试 failed/cancelled job。
- 新增 `POST /api/v1/workers/mock/provision/tick`，模拟 worker 批量领取并执行 queued provision jobs。
- `DeploymentJob` 新增 `attempts`、`max_attempts`、`locked_by`、`locked_at`、`next_run_at` 字段，便于后续接真实 worker/队列。
- `ProvisionJobRequest` 新增 `simulate_failure_phase` 和 `max_attempts`，支持 mock-only 失败注入与恢复验证。
- `scripts/smoke_test.sh` 增加 queued job cancel、mock worker tick、failure injection、retry recovery 验证。
- 新增 `docs/WORKFLOW_WORKER.md`。
- app 版本更新为 `0.9.0`。


## v0.8.0

- 新增 Provision Workflow Job：`POST /api/v1/tenants/{tenant_id}/jobs/provision`。
- 新增审计事件表 `audit_events`，记录 Phase 2-5 每个阶段的开始、成功、失败和幂等重放。
- 新增 `GET /api/v1/jobs/{job_id}`、`GET /api/v1/jobs/{job_id}/events`、`GET /api/v1/tenants/{tenant_id}/audit-events`。
- Provision Job 支持 `idempotency_key`，重复提交同一个 key 会返回原 job，避免重复执行开站流程。
- `scripts/smoke_test.sh` 增加 workflow job、事件查询、幂等 replay 验证。
- 新增 `docs/WORKFLOW_JOBS.md`。
- app 版本更新为 `0.8.0`。

## v0.7.0

- Dockerfile 复制 `tests/`、`pytest.ini` 和 `docs/`，支持容器内直接运行 pytest。
- 新增 `scripts/container_tests.sh`。
- `scripts/local_validate.sh` 在 smoke test 和 adapter preflight 后继续执行容器内单元测试。
- `docker-compose.yml` 新增 `tests` profile，可用 `docker compose --profile test run --rm tests` 运行测试。
- 新增 `tests/test_adapter_contracts.py`，验证 New API/Sub2API/Cloudflare/K8s 在全局安全闸门关闭时保持 mock/dry-run，不触发真实外部调用。
- app 版本更新为 `0.7.0`。

## v0.6.0

- 新增全局安全闸门 `ALLOW_REAL_EXTERNAL_CALLS=false`，默认阻止所有真实外部调用。
- 新增 `GET /api/v1/system/preflight`，安全检查 K8s/New API/Sub2API/Cloudflare 适配层配置。
- 新增 `GET /api/v1/tenants/{tenant_id}/deployment-plan`，输出 Phase 2-5 非破坏性部署计划。
- `scripts/smoke_test.sh` 增加 preflight 和 deployment-plan 验证。
- New API、Sub2API、Cloudflare、K8s 调用均增加安全闸门保护；默认仍为 mock/dry-run。
- 新增 `docs/REAL_ADAPTER_PREP.md`，说明未来真实 Sealos 接入方式。

## v0.5

- 修复 `scripts/smoke_test.sh` 中未加引号的 Bash 参数默认值写法导致请求体多出右花括号的问题。
- `api_post` / `api_patch` 改为显式判断参数个数，避免请求体被追加额外 `}`。
- 保持默认 mock/dry-run 安全模式，不会访问真实 Sealos、Sub2API、Cloudflare 或真实域名。

## v0.4

- 修复 `scripts/smoke_test.sh` 中租户创建 JSON 由 shell 字符串拼接导致的 422 风险。
- 改为使用 `python3` / `python` 自动生成 JSON payload，避免转义双引号和多余 `}` 问题。
- `api_request` 增加 HTTP 状态码、响应体、请求体错误输出，方便 Codex 本地定位失败点。
- 保持默认 mock/dry-run 安全模式，不触发真实 Sealos、Sub2API、Cloudflare、域名或 API Key 操作。

## v0.3

- 补齐 Phase 2-5 dry-run/mock：deploy、init-newapi、bind-upstream、domain verify、provision。
- 新增 mock-runtime 状态文件与 manifest-validation。
