import pytest

from app.core.config import Settings
from app.services.cloudflare_client import CloudflareClient
from app.services.k8s_renderer import kubectl_apply, render_newapi_manifests, validate_manifest, write_manifest
from app.services.newapi_client import NewAPIClient
from app.services.sub2api_client import Sub2APIClient


@pytest.mark.asyncio
async def test_newapi_adapter_stays_mock_when_global_gate_closed():
    client = NewAPIClient(
        'https://tenant.example.com',
        admin_token='looks-real-but-must-not-be-used',
        mock=False,
        allow_real=False,
    )
    result = await client.create_admin('admin', 'ChangeMe123!')
    assert result['status'] == 'mocked'
    assert '未调用真实 New API' in result['message']


@pytest.mark.asyncio
async def test_sub2api_adapter_stays_mock_when_global_gate_closed():
    settings = Settings(
        allow_real_external_calls=False,
        sub2api_mock=False,
        sub2api_admin_key='looks-real-but-must-not-be-used',
    )
    client = Sub2APIClient(settings)
    key = await client.create_tenant_key('demo')
    verification = await client.verify_key('demo', key)
    assert key.startswith(settings.sub2api_key_prefix)
    assert verification['status'] == 'mock_verified'


@pytest.mark.asyncio
async def test_cloudflare_adapter_stays_mock_when_global_gate_closed():
    settings = Settings(
        allow_real_external_calls=False,
        cloudflare_mock=False,
        cloudflare_api_token='looks-real-but-must-not-be-used',
        cloudflare_zone_id='looks-real-but-must-not-be-used',
        public_gateway_cname='ingress.example.com',
    )
    result = await CloudflareClient(settings).create_custom_hostname('api.customer.example')
    assert result['status'] == 'mock_pending_validation'
    assert result['dns_target'] == 'ingress.example.com'


def test_k8s_adapter_validates_manifest_but_does_not_apply_when_gate_closed(tmp_path):
    settings = Settings(
        allow_real_external_calls=False,
        apply_k8s=True,
        k8s_apply_mode='real',
        manifest_output_dir=str(tmp_path / 'manifests'),
        mock_runtime_dir=str(tmp_path / 'runtime'),
    )
    docs = render_newapi_manifests(
        settings,
        slug='demo',
        domain='demo.example.com',
        admin_username='admin',
        admin_password='ChangeMe123!',
    )
    manifest_path = write_manifest(settings, 'demo', docs)
    ok, output, meta = kubectl_apply(settings, manifest_path)
    assert ok is True
    assert '[mock]' in output
    assert meta['validation']['ok'] is True


def test_newapi_channel_payload_matches_management_api_wrapper_shape():
    settings = Settings(newapi_channel_models='gpt-4o,gpt-4o-mini', newapi_channel_group='default')
    client = NewAPIClient('https://tenant.example.com', admin_token='token', mock=True, allow_real=False, settings=settings)
    payload = client.channel_payload('default-sub2api', 'https://sub2api.example.com', 'sk-real-value')
    assert payload['mode'] == 'single'
    assert 'channel' in payload
    assert payload['channel']['base_url'] == 'https://sub2api.example.com'
    assert payload['channel']['key'] == 'sk-real-value'
    assert payload['channel']['models'] == 'gpt-4o,gpt-4o-mini'


@pytest.mark.asyncio
async def test_sub2api_real_mode_can_use_static_tenant_key_without_admin_api():
    settings = Settings(
        allow_real_external_calls=True,
        real_external_allowlist='sub2api',
        sub2api_mock=False,
        sub2api_tenant_key='sub2api-real-tenant-key',
        sub2api_admin_key='change-me-sub2api-admin-key',
    )
    key = await Sub2APIClient(settings).create_tenant_key('demo')
    assert key == 'sub2api-real-tenant-key'


def test_fixed_namespace_manifest_omits_namespace_kind(tmp_path):
    settings = Settings(
        k8s_namespace_mode='fixed',
        k8s_target_namespace='sealos-test',
        k8s_create_namespace=False,
        manifest_output_dir=str(tmp_path / 'manifests'),
    )
    docs = render_newapi_manifests(
        settings,
        slug='demo',
        domain='demo.example.com',
        admin_username='admin',
        admin_password='ChangeMe123!',
    )
    kinds = [doc['kind'] for doc in docs]
    assert 'Namespace' not in kinds
    assert all(doc.get('metadata', {}).get('namespace') == 'sealos-test' for doc in docs if doc['kind'] != 'Namespace')
    manifest_path = write_manifest(settings, 'demo', docs)
    validation = validate_manifest(manifest_path, settings)
    assert validation['ok'] is True
