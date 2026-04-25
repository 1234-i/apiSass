from __future__ import annotations

from pathlib import Path
from shutil import which
from typing import Any

from app.core.config import Settings

REAL_ADAPTERS = ('k8s', 'newapi', 'sub2api', 'cloudflare')


def credential_present(value: str | None) -> bool:
    if value is None:
        return False
    value = str(value).strip()
    if not value:
        return False
    return not value.lower().startswith('change-me')


def allowed_real_adapters(settings: Settings) -> set[str]:
    raw = (settings.real_external_allowlist or '').strip()
    if not raw:
        return set()
    values = {item.strip().lower() for item in raw.split(',') if item.strip()}
    return values & set(REAL_ADAPTERS)


def adapter_allowed(settings: Settings, component: str) -> bool:
    return component.lower() in allowed_real_adapters(settings)


def real_external_enabled(settings: Settings, component: str) -> bool:
    """Return True only when the global real-call gate and the component switch both allow it."""
    if not settings.allow_real_external_calls:
        return False
    component = component.lower()
    if not adapter_allowed(settings, component):
        return False
    if component == 'k8s':
        return settings.apply_k8s and settings.k8s_apply_mode == 'real'
    if component == 'newapi':
        return not settings.newapi_mock and credential_present(settings.newapi_admin_token)
    if component == 'sub2api':
        # 真实开站可先用 Sub2API 后台预创建的站长 key；不强制依赖未稳定的管理 API。
        return not settings.sub2api_mock and (
            credential_present(settings.sub2api_tenant_key) or credential_present(settings.sub2api_admin_key)
        )
    if component == 'cloudflare':
        return not settings.cloudflare_mock and credential_present(settings.cloudflare_api_token) and credential_present(settings.cloudflare_zone_id)
    return False


def external_call_mode(settings: Settings, component: str) -> str:
    return 'real_enabled' if real_external_enabled(settings, component) else 'mock_or_dry_run'


def safe_settings_snapshot(settings: Settings) -> dict[str, Any]:
    """Expose configuration safely without leaking secrets."""
    kubeconfig_path = Path(settings.kubeconfig_path) if settings.kubeconfig_path else None
    kubectl_path = which('kubectl')
    warnings: list[str] = []
    allowed = sorted(allowed_real_adapters(settings))
    blocked = [name for name in REAL_ADAPTERS if name not in allowed]

    if settings.k8s_apply_mode == 'real' and not settings.allow_real_external_calls:
        warnings.append('K8S_APPLY_MODE=real was requested, but ALLOW_REAL_EXTERNAL_CALLS=false keeps Kubernetes in safe dry-run mode.')
    if settings.k8s_apply_mode == 'real' and settings.allow_real_external_calls and not adapter_allowed(settings, 'k8s'):
        warnings.append('K8S_APPLY_MODE=real was requested, but REAL_EXTERNAL_ALLOWLIST does not include k8s.')
    if not settings.newapi_mock and not settings.allow_real_external_calls:
        warnings.append('NEWAPI_MOCK=false was requested, but ALLOW_REAL_EXTERNAL_CALLS=false keeps New API calls mocked.')
    if not settings.newapi_mock and settings.allow_real_external_calls and not adapter_allowed(settings, 'newapi'):
        warnings.append('NEWAPI_MOCK=false was requested, but REAL_EXTERNAL_ALLOWLIST does not include newapi.')
    if not settings.sub2api_mock and not settings.allow_real_external_calls:
        warnings.append('SUB2API_MOCK=false was requested, but ALLOW_REAL_EXTERNAL_CALLS=false keeps Sub2API calls mocked.')
    if not settings.sub2api_mock and settings.allow_real_external_calls and not adapter_allowed(settings, 'sub2api'):
        warnings.append('SUB2API_MOCK=false was requested, but REAL_EXTERNAL_ALLOWLIST does not include sub2api.')
    if not settings.cloudflare_mock and not settings.allow_real_external_calls:
        warnings.append('CLOUDFLARE_MOCK=false was requested, but ALLOW_REAL_EXTERNAL_CALLS=false keeps Cloudflare calls mocked.')
    if not settings.cloudflare_mock and settings.allow_real_external_calls and not adapter_allowed(settings, 'cloudflare'):
        warnings.append('CLOUDFLARE_MOCK=false was requested, but REAL_EXTERNAL_ALLOWLIST does not include cloudflare.')
    if real_external_enabled(settings, 'newapi') and not credential_present(settings.newapi_admin_user_id):
        warnings.append('New API real mode is enabled but NEWAPI_ADMIN_USER_ID is empty; some management APIs may require New-Api-User header.')
    if real_external_enabled(settings, 'sub2api') and not credential_present(settings.sub2api_tenant_key):
        warnings.append('Sub2API real mode has no SUB2API_TENANT_KEY; adapter will fall back to deterministic key unless you implement Sub2API management API.')

    return {
        'app': {'name': settings.app_name, 'env': settings.app_env, 'version': settings.app_version},
        'safety': {
            'allow_real_external_calls': settings.allow_real_external_calls,
            'effective_mode': 'real_external_calls_possible' if settings.allow_real_external_calls else 'safe_mock_dry_run',
            'allowed_real_adapters': allowed,
            'blocked_real_adapters': blocked,
            'will_call_k8s': real_external_enabled(settings, 'k8s'),
            'will_call_newapi': real_external_enabled(settings, 'newapi'),
            'will_call_sub2api': real_external_enabled(settings, 'sub2api'),
            'will_call_cloudflare': real_external_enabled(settings, 'cloudflare'),
        },
        'domain': {
            'base_domain': settings.base_domain,
            'public_gateway_cname': settings.public_gateway_cname,
        },
        'k8s': {
            'apply_k8s': settings.apply_k8s,
            'k8s_apply_mode': settings.k8s_apply_mode,
            'effective_mode': external_call_mode(settings, 'k8s'),
            'namespace_prefix': settings.k8s_namespace_prefix,
            'namespace_mode': settings.k8s_namespace_mode,
            'target_namespace': settings.k8s_target_namespace,
            'create_namespace': settings.k8s_create_namespace,
            'ingress_class': settings.k8s_ingress_class,
            'tls_secret_name': settings.k8s_tls_secret_name,
            'kubeconfig_path': settings.kubeconfig_path,
            'context': settings.k8s_context,
            'server_dry_run_first': settings.k8s_server_dry_run_first,
            'rollout_timeout_seconds': settings.k8s_rollout_timeout_seconds,
            'kubeconfig_present': bool(kubeconfig_path and kubeconfig_path.exists()),
            'kubectl_present': bool(kubectl_path),
            'kubectl_path': kubectl_path,
        },
        'newapi': {
            'mock_flag': settings.newapi_mock,
            'effective_mode': external_call_mode(settings, 'newapi'),
            'image': settings.newapi_image,
            'default_replicas': settings.newapi_default_replicas,
            'admin_token_present': credential_present(settings.newapi_admin_token),
            'admin_user_id_present': credential_present(settings.newapi_admin_user_id),
            'channel_path': settings.newapi_channel_path,
            'token_path': settings.newapi_token_path,
        },
        'sub2api': {
            'mock_flag': settings.sub2api_mock,
            'effective_mode': external_call_mode(settings, 'sub2api'),
            'base_url': settings.sub2api_base_url,
            'admin_key_present': credential_present(settings.sub2api_admin_key),
            'tenant_key_present': credential_present(settings.sub2api_tenant_key),
        },
        'cloudflare': {
            'mock_flag': settings.cloudflare_mock,
            'effective_mode': external_call_mode(settings, 'cloudflare'),
            'api_token_present': credential_present(settings.cloudflare_api_token),
            'zone_id_present': credential_present(settings.cloudflare_zone_id),
            'fallback_origin': settings.cloudflare_custom_hostname_fallback_origin,
        },
        'storage': {
            'manifest_output_dir': settings.manifest_output_dir,
            'mock_runtime_dir': settings.mock_runtime_dir,
        },
        'warnings': warnings,
    }
