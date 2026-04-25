from __future__ import annotations

from pathlib import Path
from shutil import which
from typing import Any

from app.core.config import Settings
from app.services.safety import adapter_allowed, credential_present, real_external_enabled, safe_settings_snapshot


def real_flow_preflight(settings: Settings) -> dict[str, Any]:
    """真实开站前的本地/配置预检。

    不调用外部系统，只检查是否具备从 mock 切到真实模式的配置条件。
    """
    snapshot = safe_settings_snapshot(settings)
    kubeconfig = Path(settings.kubeconfig_path) if settings.kubeconfig_path else None

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, required_for_real: bool, message: str, details: dict | None = None):
        checks.append({
            'name': name,
            'ok': ok,
            'required_for_real': required_for_real,
            'message': message,
            'details': details or {},
        })

    add('global_real_gate', settings.allow_real_external_calls, True, 'ALLOW_REAL_EXTERNAL_CALLS must be true for real open-station flow')
    add('k8s_allowlisted', adapter_allowed(settings, 'k8s'), True, 'REAL_EXTERNAL_ALLOWLIST must include k8s for Real Canary 0')
    add('k8s_real_mode', real_external_enabled(settings, 'k8s'), True, 'APPLY_K8S=true and K8S_APPLY_MODE=real are required for real kubectl apply')
    add('kubectl_binary', bool(which('kubectl')), True, 'kubectl must be installed in the api container or external worker')
    add('kubeconfig_present', bool(kubeconfig and kubeconfig.exists()), True, f'kubeconfig must exist at {settings.kubeconfig_path}')
    add('namespace_mode', settings.k8s_namespace_mode in {'generated', 'fixed'}, True, 'K8S_NAMESPACE_MODE must be generated or fixed')
    add('fixed_namespace', settings.k8s_namespace_mode != 'fixed' or bool(settings.k8s_target_namespace), True, 'K8S_TARGET_NAMESPACE is required when K8S_NAMESPACE_MODE=fixed')
    add('base_domain', bool(settings.base_domain and settings.base_domain != 'example.com'), True, 'BASE_DOMAIN should be your production wildcard domain')
    add('gateway_cname', bool(settings.public_gateway_cname and settings.public_gateway_cname != 'ingress.example.com'), True, 'PUBLIC_GATEWAY_CNAME should point to Sealos public ingress')
    add('tls_secret', bool(settings.k8s_tls_secret_name and settings.k8s_tls_secret_name != 'wildcard-example-com-tls'), False, 'K8S_TLS_SECRET_NAME should reference an existing wildcard TLS secret or Sealos-managed cert')
    add('newapi_dsn', 'REPLACE_WITH' not in settings.newapi_sql_dsn_template, True, 'NEWAPI_SQL_DSN_TEMPLATE must point to a real Sealos database DSN')
    add('newapi_redis', 'REPLACE_WITH' not in settings.newapi_redis_conn_template, True, 'NEWAPI_REDIS_CONN_TEMPLATE must point to a real Sealos Redis URL')
    add('newapi_admin_token_optional', credential_present(settings.newapi_admin_token), False, 'NEWAPI_ADMIN_TOKEN is not required for Real Canary 0; New API management stays mocked')
    add('newapi_kept_mock', not real_external_enabled(settings, 'newapi'), False, 'Real Canary 0 must keep New API management calls mocked')
    add('sub2api_base_url_optional', bool(settings.sub2api_base_url and 'example.com' not in settings.sub2api_base_url), False, 'SUB2API_BASE_URL is not required for Real Canary 0; Sub2API stays mocked')
    add('sub2api_tenant_key', credential_present(settings.sub2api_tenant_key), False, 'SUB2API_TENANT_KEY is recommended; create it in Sub2API UI to reuse Sub2API billing')
    add('sub2api_kept_mock', not real_external_enabled(settings, 'sub2api'), False, 'Real Canary 0 must keep Sub2API calls mocked')
    add('cloudflare_kept_mock', not real_external_enabled(settings, 'cloudflare'), False, 'Real Canary 0 must keep Cloudflare calls mocked')

    blocking = [c for c in checks if c['required_for_real'] and not c['ok']]
    recommended_missing = [c for c in checks if (not c['required_for_real']) and not c['ok']]

    return {
        'status': 'ready_for_real' if not blocking else 'not_ready_for_real',
        'real_canary_0_status': 'ready_for_k8s_canary' if not blocking and real_external_enabled(settings, 'k8s') and not any(real_external_enabled(settings, c) for c in ('newapi', 'sub2api', 'cloudflare')) else 'not_ready_for_k8s_canary',
        'safe_mode': not settings.allow_real_external_calls,
        'allowed_real_adapters': snapshot['safety']['allowed_real_adapters'],
        'blocked_real_adapters': snapshot['safety']['blocked_real_adapters'],
        'will_call_k8s': snapshot['safety']['will_call_k8s'],
        'will_call_newapi': snapshot['safety']['will_call_newapi'],
        'will_call_sub2api': snapshot['safety']['will_call_sub2api'],
        'will_call_cloudflare': snapshot['safety']['will_call_cloudflare'],
        'blocking_count': len(blocking),
        'recommended_missing_count': len(recommended_missing),
        'checks': checks,
        'blocking': blocking,
        'recommended_missing': recommended_missing,
        'config': snapshot,
        'next_steps': [
            'Keep default .env in mock/dry-run for local validation.',
            'Create real Sealos DB/Redis or fill Sealos managed DB connection templates.',
            'Create/verify wildcard domain and TLS handling in Sealos ingress.',
            'Create or obtain New API admin access token after first New API bootstrap.',
            'Create a Sub2API tenant/downstream key in Sub2API UI and put it into SUB2API_TENANT_KEY.',
            'Only then set ALLOW_REAL_EXTERNAL_CALLS=true, APPLY_K8S=true, K8S_APPLY_MODE=real, NEWAPI_MOCK=false, SUB2API_MOCK=false.',
        ],
    }
