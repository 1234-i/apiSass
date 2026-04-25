from app.core.config import Settings
from app.services.safety import real_external_enabled, safe_settings_snapshot


def test_default_safety_gate_blocks_real_external_calls():
    settings = Settings()
    assert settings.allow_real_external_calls is False
    assert real_external_enabled(settings, 'k8s') is False
    assert real_external_enabled(settings, 'newapi') is False
    assert real_external_enabled(settings, 'sub2api') is False
    assert real_external_enabled(settings, 'cloudflare') is False


def test_component_real_requires_global_gate_and_credentials():
    settings = Settings(
        allow_real_external_calls=True,
        real_external_allowlist='k8s,newapi,sub2api,cloudflare',
        newapi_mock=False,
        newapi_admin_token='real-token',
        sub2api_mock=False,
        sub2api_admin_key='real-sub2api-key',
        cloudflare_mock=False,
        cloudflare_api_token='real-cf-token',
        cloudflare_zone_id='real-zone-id',
        apply_k8s=True,
        k8s_apply_mode='real',
    )
    assert real_external_enabled(settings, 'k8s') is True
    assert real_external_enabled(settings, 'newapi') is True
    assert real_external_enabled(settings, 'sub2api') is True
    assert real_external_enabled(settings, 'cloudflare') is True


def test_allowlist_limits_real_external_components():
    settings = Settings(
        allow_real_external_calls=True,
        real_external_allowlist='k8s',
        apply_k8s=True,
        k8s_apply_mode='real',
        newapi_mock=False,
        newapi_admin_token='real-token',
        sub2api_mock=False,
        sub2api_tenant_key='real-sub2api-key',
        cloudflare_mock=False,
        cloudflare_api_token='real-cf-token',
        cloudflare_zone_id='real-zone-id',
    )
    snapshot = safe_settings_snapshot(settings)
    assert real_external_enabled(settings, 'k8s') is True
    assert real_external_enabled(settings, 'newapi') is False
    assert real_external_enabled(settings, 'sub2api') is False
    assert real_external_enabled(settings, 'cloudflare') is False
    assert snapshot['safety']['allowed_real_adapters'] == ['k8s']
    assert snapshot['safety']['will_call_k8s'] is True
    assert snapshot['safety']['will_call_newapi'] is False


def test_safe_snapshot_never_exposes_secret_values():
    settings = Settings(
        allow_real_external_calls=True,
        newapi_mock=False,
        newapi_admin_token='secret-newapi-token',
        sub2api_mock=False,
        sub2api_admin_key='secret-sub2api-key',
        cloudflare_mock=False,
        cloudflare_api_token='secret-cf-token',
        cloudflare_zone_id='secret-zone-id',
    )
    snapshot = safe_settings_snapshot(settings)
    rendered = str(snapshot)
    assert 'secret-newapi-token' not in rendered
    assert 'secret-sub2api-key' not in rendered
    assert 'secret-cf-token' not in rendered
    assert snapshot['newapi']['admin_token_present'] is True
    assert snapshot['sub2api']['admin_key_present'] is True
    assert snapshot['cloudflare']['api_token_present'] is True
