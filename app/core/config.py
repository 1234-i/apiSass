from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'ai-api-saas-control-plane'
    app_env: str = 'dev'
    app_version: str = '0.10-realflow'
    api_key: str = 'change-me-admin-token'
    # 全局真实外部调用闸门：默认关闭，任何 K8s/NewAPI/Sub2API/Cloudflare 都不会真实调用。
    allow_real_external_calls: bool = False
    # 细粒度真实外部调用白名单，例如 Real Canary 0 只允许 "k8s"。
    real_external_allowlist: str = ''

    database_url: str = 'postgresql+psycopg://saas:saas@db:5432/saas'
    redis_url: str = 'redis://redis:6379/0'

    base_domain: str = 'example.com'
    public_gateway_cname: str = 'ingress.example.com'

    k8s_namespace_prefix: str = 'ai-tenant'
    k8s_namespace_mode: str = 'generated'  # generated | fixed
    k8s_target_namespace: str | None = None
    k8s_create_namespace: bool = True
    k8s_ingress_class: str = 'nginx'
    k8s_tls_secret_name: str = 'wildcard-example-com-tls'
    k8s_pod_run_as_user: str | None = None
    k8s_pod_run_as_group: str | None = None
    k8s_pod_fs_group: str | None = None
    k8s_canary_mode: bool = False
    k8s_canary_max_lifetime_seconds: int = 600
    newapi_image: str = 'calciumion/new-api:latest'
    newapi_container_port: int = 3000
    newapi_default_replicas: int = 1
    newapi_sql_dsn_template: str = 'REPLACE_WITH_SEALOS_DB_DSN_FOR_{slug}'
    newapi_redis_conn_template: str = 'REPLACE_WITH_SEALOS_REDIS_URL_FOR_{slug}'
    newapi_session_secret_prefix: str = 'change-me-session'
    newapi_crypto_secret_prefix: str = 'change-me-crypto'
    newapi_timezone: str = 'Asia/Shanghai'
    newapi_streaming_timeout_seconds: int = 300
    newapi_error_log_enabled: bool = True
    newapi_batch_update_enabled: bool = True
    # New API 管理 API：真实模式使用 Access Token；文档建议 Authorization: Bearer {token}。
    newapi_admin_token: str | None = None
    newapi_admin_user_id: str | None = None
    newapi_mock: bool = True
    newapi_health_path: str = '/'
    newapi_channel_path: str = '/api/channel/'
    newapi_token_path: str = '/api/token/'
    newapi_api_timeout_seconds: float = 20.0
    # New API channel payload 可按实际版本调整；模板变量：{name},{base_url},{api_key},{models},{group},{channel_type}。
    newapi_channel_payload_template: str | None = None
    newapi_channel_mode: str = 'single'
    newapi_channel_type: int = 1
    newapi_channel_models: str = 'gpt-4o,gpt-4o-mini,claude-3-5-sonnet,gemini-1.5-pro'
    newapi_channel_group: str = 'default'

    sub2api_base_url: str = 'https://sub2api.example.com'
    sub2api_admin_key: str = 'change-me-sub2api-admin-key'
    sub2api_key_prefix: str = 'sub2api-placeholder-key'
    sub2api_mock: bool = True
    # 开站工厂真实收口版默认不强依赖 Sub2API 管理 API。真实模式可使用你在 Sub2API 后台创建的站长专属 key。
    sub2api_tenant_key: str | None = None
    sub2api_health_path: str = '/health'

    # APPLY_K8S=false + K8S_APPLY_MODE=mock 是默认验证模式：不需要真实 Sealos/kubeconfig。
    apply_k8s: bool = False
    k8s_apply_mode: str = 'mock'  # mock | dry-run | real
    kubeconfig_path: str = '/app/.kube/config'
    k8s_context: str | None = None
    k8s_rollout_timeout_seconds: int = 180
    k8s_server_dry_run_first: bool = True
    manifest_output_dir: str = '/app/generated-manifests'
    mock_runtime_dir: str = '/app/mock-runtime'
    provision_wait_seconds: float = 0.05
    workflow_retry_backoff_seconds: float = 0.05
    kubectl_timeout_seconds: int = 180

    cloudflare_api_token: str | None = None
    cloudflare_zone_id: str | None = None
    cloudflare_custom_hostname_fallback_origin: str | None = None
    cloudflare_mock: bool = True

    default_rpm: int = 60
    default_tpm: int = 100000
    default_monthly_limit: int = 10000000


@lru_cache
def get_settings() -> Settings:
    return Settings()
