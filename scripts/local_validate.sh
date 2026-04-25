#!/usr/bin/env bash
set -euo pipefail
cp -n .env.example .env || true
bash ./scripts/check_host_permissions.sh >/dev/null
bash ./scripts/check_env_files.sh
bash ./scripts/real_k8s_canary_static_check.sh
# 为避免旧数据库 schema 影响本地验证，默认清理 volume。生产环境不要执行这个脚本。
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose up -d --build
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8080/ready >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [ "$i" = "60" ]; then
    echo 'service not ready'
    docker compose logs api
    exit 1
  fi
done
API_KEY=change-me-admin-token bash ./scripts/smoke_test.sh
bash ./scripts/adapter_preflight.sh >/dev/null
bash ./scripts/container_tests.sh
