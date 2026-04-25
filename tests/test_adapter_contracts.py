import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.session import Base
from app.models.tenant import DeploymentJob
from app.services.cloudflare_client import CloudflareClient
from app.services.k8s_renderer import kubectl_apply, render_newapi_manifests, validate_manifest, write_manifest
from app.services.newapi_client import NewAPIClient
from app.services.sub2api_client import Sub2APIClient
from app.schemas.tenant import TenantCreate
from app.services import tenant_service


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
async def test_newapi_allowlist_blocks_real_call_even_with_token():
    settings = Settings(
        allow_real_external_calls=True,
        real_external_allowlist='k8s',
        newapi_mock=False,
        newapi_admin_token='looks-real',
        newapi_api_timeout_seconds=0.1,
    )
    client = NewAPIClient(
        'http://127.0.0.1:9',
        admin_token='looks-real',
        mock=False,
        allow_real=True,
        settings=settings,
    )
    result = await client.create_token('demo', name='blocked-by-allowlist')
    assert result['status'] == 'mocked'
    assert result['token'].startswith('newapi-mock-token-')


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


@pytest.mark.asyncio
async def test_sub2api_allowlist_blocks_static_key_and_health_probe():
    settings = Settings(
        allow_real_external_calls=True,
        real_external_allowlist='k8s',
        sub2api_mock=False,
        sub2api_tenant_key='sub2api-real-tenant-key',
        sub2api_admin_key='real-admin-key',
    )
    key = await Sub2APIClient(settings).create_tenant_key('demo')
    verification = await Sub2APIClient(settings).verify_key('demo', key)
    assert key.startswith(settings.sub2api_key_prefix)
    assert verification['status'] == 'mock_verified'


@pytest.mark.asyncio
async def test_cloudflare_allowlist_blocks_real_custom_hostname_call():
    settings = Settings(
        allow_real_external_calls=True,
        real_external_allowlist='k8s',
        cloudflare_mock=False,
        cloudflare_api_token='real-cf-token',
        cloudflare_zone_id='real-zone-id',
        public_gateway_cname='ingress.example.com',
    )
    result = await CloudflareClient(settings).create_custom_hostname('api.customer.example')
    assert result['status'] == 'mock_pending_validation'
    assert result['dns_target'] == 'ingress.example.com'


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


def test_empty_tls_secret_omits_ingress_tls():
    settings = Settings(k8s_tls_secret_name='')
    docs = render_newapi_manifests(
        settings,
        slug='demo',
        domain='demo.example.com',
        admin_username='admin',
        admin_password='ChangeMe123!',
    )
    ingress = next(doc for doc in docs if doc['kind'] == 'Ingress')
    assert 'tls' not in ingress['spec']


@pytest.mark.asyncio
async def test_create_tenant_never_inline_real_applies(monkeypatch, tmp_path):
    settings = Settings(
        allow_real_external_calls=True,
        real_external_allowlist='k8s',
        apply_k8s=True,
        k8s_apply_mode='real',
        manifest_output_dir=str(tmp_path / 'manifests'),
        mock_runtime_dir=str(tmp_path / 'runtime'),
    )
    monkeypatch.setattr(tenant_service, 'get_settings', lambda: settings)

    def fail_inline_apply(*args, **kwargs):
        raise AssertionError('create_tenant must not call kubectl_apply inline')

    monkeypatch.setattr(tenant_service, 'kubectl_apply', fail_inline_apply)

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        tenant = await tenant_service.create_tenant(
            db,
            TenantCreate(
                name='Real Apply Blocked',
                email='blocked@example.com',
                slug='blocked-inline',
                deploy=True,
                apply_k8s=True,
            ),
        )
        assert tenant.status == 'manifest_generated'
        jobs = db.execute(select(DeploymentJob).where(DeploymentJob.tenant_id == tenant.id)).scalars().all()
        assert any(job.action == 'inline_apply_blocked' for job in jobs)
        assert any(job.action == 'create_tenant' and job.status == 'succeeded' for job in jobs)
