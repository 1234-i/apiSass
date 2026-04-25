from __future__ import annotations
import json
import time
from slugify import slugify
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException
from app.core.config import get_settings
from app.models.tenant import Tenant, Domain, Instance, Quota, UpstreamBinding, DeploymentJob
from app.schemas.tenant import TenantCreate, QuotaUpdate
from app.services.k8s_renderer import (
    render_newapi_manifests,
    write_manifest,
    kubectl_apply,
    kubectl_delete,
    kubectl_get_resources,
    kubectl_wait_ready,
    namespace_for,
    write_mock_runtime_state,
    delete_mock_runtime_state,
    validate_manifest,
    should_mock,
)
from app.services.sub2api_client import Sub2APIClient
from app.services.newapi_client import NewAPIClient
from app.services.cloudflare_client import CloudflareClient
from app.services.safety import real_external_enabled, safe_settings_snapshot


def normalize_slug(name: str, explicit: str | None) -> str:
    raw = explicit or name
    slug = slugify(raw).lower().strip('-')
    if not slug:
        raise HTTPException(status_code=400, detail='slug 不能为空；请提供英文/数字 slug')
    if len(slug) > 48:
        slug = slug[:48].rstrip('-')
    return slug


def primary_domain(tenant: Tenant) -> str | None:
    if not tenant.domains:
        return None
    subdomains = [d.domain for d in tenant.domains if d.type == 'subdomain']
    return subdomains[0] if subdomains else tenant.domains[0].domain


def add_job(db: Session, tenant: Tenant, *, action: str, status: str, message: str | dict | None = None) -> DeploymentJob:
    if isinstance(message, (dict, list)):
        message = json.dumps(message, ensure_ascii=False)
    job = DeploymentJob(tenant_id=tenant.id, action=action, status=status, message=message)
    db.add(job)
    db.flush()
    return job


def ensure_instance_manifest(db: Session, tenant: Tenant) -> Instance:
    settings = get_settings()
    domain_value = primary_domain(tenant)
    if not domain_value:
        domain_row = db.execute(select(Domain).where(Domain.tenant_id == tenant.id).order_by(Domain.created_at.asc())).scalar_one_or_none()
        domain_value = domain_row.domain if domain_row else None
    if not domain_value:
        raise HTTPException(status_code=400, detail='tenant has no domain')
    existing = tenant.instances[0] if tenant.instances else None
    if existing and existing.manifest_path:
        return existing

    manifests = render_newapi_manifests(
        settings,
        slug=tenant.slug,
        domain=domain_value,
        admin_username=tenant.admin_username,
        admin_password=tenant.admin_password,
    )
    manifest_path = write_manifest(settings, tenant.slug, manifests)
    if existing:
        existing.manifest_path = manifest_path
        existing.status = 'generated'
        db.add(existing)
        return existing
    instance = Instance(
        tenant_id=tenant.id,
        name=f'newapi-{tenant.slug}',
        namespace=namespace_for(settings, tenant.slug),
        endpoint=f'https://{domain_value}',
        status='generated',
        manifest_path=manifest_path,
    )
    db.add(instance)
    db.flush()
    return instance


async def create_tenant(db: Session, payload: TenantCreate) -> Tenant:
    settings = get_settings()
    slug = normalize_slug(payload.name, payload.slug)
    existing = db.execute(select(Tenant).where((Tenant.slug == slug) | (Tenant.email == payload.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail='tenant slug 或 email 已存在')

    tenant = Tenant(
        name=payload.name, slug=slug, email=payload.email, plan=payload.plan,
        admin_username=payload.admin_username, admin_password=payload.admin_password,
        status='provisioning' if payload.deploy else 'created'
    )
    db.add(tenant)
    db.flush()

    domain_value = f'{slug}.{settings.base_domain}'
    domain = Domain(tenant_id=tenant.id, domain=domain_value, type='subdomain', status='active', validation_status='wildcard_ready', dns_target=settings.public_gateway_cname)
    quota = Quota(tenant_id=tenant.id, rpm=payload.rpm, tpm=payload.tpm, monthly_limit=payload.monthly_limit)
    db.add_all([domain, quota])

    sub_key = await Sub2APIClient(settings).create_tenant_key(slug)
    upstream = UpstreamBinding(
        tenant_id=tenant.id,
        sub2api_base_url=settings.sub2api_base_url,
        sub2api_key=sub_key,
        policy={'default': True, 'plan': payload.plan, 'mode': 'real' if real_external_enabled(settings, 'sub2api') else 'mock'},
        status='created'
    )
    db.add(upstream)

    add_job(db, tenant, action='create_tenant', status='running')

    if payload.deploy:
        # create 阶段只负责生成清单；真实或 mock 部署由 /deploy 或 /provision 触发。
        instance = ensure_instance_manifest(db, tenant)
        if payload.apply_k8s:
            add_job(
                db,
                tenant,
                action='inline_apply_blocked',
                status='succeeded',
                message='create_tenant never performs real inline apply; call /deploy explicitly after reviewing the deployment plan',
            )
        tenant.status = 'manifest_generated'
        db.add(instance)

    add_job(db, tenant, action='create_tenant', status='succeeded', message='tenant created; manifest generated' if payload.deploy else 'tenant created')
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def update_quota(db: Session, tenant: Tenant, payload: QuotaUpdate) -> Quota:
    quota = tenant.quota or Quota(tenant_id=tenant.id)
    if payload.rpm is not None:
        quota.rpm = payload.rpm
    if payload.tpm is not None:
        quota.tpm = payload.tpm
    if payload.monthly_limit is not None:
        quota.monthly_limit = payload.monthly_limit
    db.add(quota)
    add_job(db, tenant, action='update_quota', status='succeeded', message={'rpm': quota.rpm, 'tpm': quota.tpm, 'monthly_limit': quota.monthly_limit})
    db.commit()
    db.refresh(quota)
    return quota


async def add_custom_domain(db: Session, tenant: Tenant, domain_name: str, use_cloudflare: bool) -> Domain:
    settings = get_settings()
    exists = db.execute(select(Domain).where(Domain.domain == domain_name)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail='domain 已存在')
    dns_target = settings.public_gateway_cname
    status = 'pending_validation'
    validation_status = 'manual_dns_required'
    cf_result = None
    if use_cloudflare:
        cf_result = await CloudflareClient(settings).create_custom_hostname(domain_name)
        dns_target = cf_result.get('dns_target') or dns_target
        validation_status = str(cf_result.get('status'))
    else:
        validation_status = 'mock_manual_dns_required' if settings.cloudflare_mock else 'manual_dns_required'
    row = Domain(tenant_id=tenant.id, domain=domain_name, type='custom', status=status, validation_status=validation_status, dns_target=dns_target)
    db.add(row)
    add_job(db, tenant, action='add_custom_domain', status='succeeded', message={'domain': domain_name, 'cloudflare': cf_result or {'dns_target': dns_target, 'status': validation_status}})
    db.commit()
    db.refresh(row)
    return row


async def verify_domain(db: Session, tenant: Tenant, domain: Domain) -> Domain:
    settings = get_settings()
    if domain.type == 'subdomain':
        domain.status = 'active'
        domain.validation_status = 'wildcard_ready'
        result = {'status': 'wildcard_ready', 'domain': domain.domain}
    else:
        result = await CloudflareClient(settings).verify_custom_hostname(domain.domain)
        domain.status = 'active' if str(result.get('status')).startswith('mock') or result.get('status') == 'active' else 'pending_validation'
        domain.validation_status = str(result.get('status'))
        domain.dns_target = result.get('dns_target') or domain.dns_target
    db.add(domain)
    add_job(db, tenant, action='verify_domain', status='succeeded', message=result)
    db.commit()
    db.refresh(domain)
    return domain


def deploy_instance(db: Session, tenant: Tenant, instance: Instance, *, dry_run: bool | None = None, wait_ready: bool = True) -> dict:
    settings = get_settings()
    if not instance.manifest_path:
        instance = ensure_instance_manifest(db, tenant)
    ok, output, meta = kubectl_apply(settings, instance.manifest_path, force_dry_run=dry_run)
    if not ok:
        instance.status = 'apply_failed'
        instance.last_apply_output = output
        tenant.status = 'apply_failed'
        db.add_all([tenant, instance])
        add_job(db, tenant, action='deploy_runtime', status='failed', message={'output': output, 'meta': meta})
        db.commit()
        raise HTTPException(status_code=500, detail={'message': 'kubectl apply failed', 'output': output, 'meta': meta})

    ready_meta = None
    if wait_ready:
        # 在 mock/dry-run 中立即 ready；真实模式使用 kubectl rollout status。
        ok_ready, ready_output, ready_meta = kubectl_wait_ready(
            settings,
            namespace=instance.namespace,
            deployment=instance.name,
            replicas=settings.newapi_default_replicas,
            force_dry_run=dry_run,
        )
        output = '\n'.join([x for x in [output, ready_output] if x])
        if not ok_ready:
            instance.status = 'not_ready'
            instance.last_apply_output = output
            db.add(instance)
            add_job(db, tenant, action='wait_runtime_ready', status='failed', message={'output': ready_output, 'meta': ready_meta})
            db.commit()
            raise HTTPException(status_code=500, detail={'message': 'deployment not ready', 'output': ready_output, 'meta': ready_meta})

    mock_mode = should_mock(settings, dry_run)
    instance.status = 'running_mock' if mock_mode else 'running'
    instance.last_apply_output = output
    tenant.status = 'runtime_ready_mock' if mock_mode else 'runtime_ready'
    resources_meta = None
    if not mock_mode:
        ok_resources, resources_output, resources_meta = kubectl_get_resources(
            settings,
            namespace=instance.namespace,
            slug=tenant.slug,
            force_dry_run=dry_run,
        )
        output = '\n'.join([x for x in [output, resources_output] if x])
        if not ok_resources:
            instance.status = 'resource_query_failed'
            instance.last_apply_output = output
            db.add(instance)
            add_job(db, tenant, action='get_runtime_resources', status='failed', message={'output': resources_output, 'meta': resources_meta})
            db.commit()
            raise HTTPException(status_code=500, detail={'message': 'runtime resource query failed', 'output': resources_output, 'meta': resources_meta})
    runtime_state = write_mock_runtime_state(
        settings,
        slug=tenant.slug,
        namespace=instance.namespace,
        endpoint=instance.endpoint,
        status=instance.status,
        manifest_path=instance.manifest_path,
        extra={
            'ready': True,
            'deployment_name': instance.name,
            'service_name': instance.name,
            'ingress_name': instance.name,
            'rollout_status': 'mock_ready' if mock_mode else 'ready',
            'external_calls': {
                'k8s': not mock_mode,
                'newapi': False,
                'sub2api': False,
                'cloudflare': False,
            },
            'apply': meta,
            'wait': ready_meta,
            'resources': resources_meta,
        },
    )
    db.add_all([tenant, instance])
    add_job(db, tenant, action='deploy_runtime', status='succeeded', message={'output': output, 'runtime_state': runtime_state, 'meta': meta})
    db.commit()
    db.refresh(instance)
    return {'instance': instance, 'output': output, 'meta': meta, 'runtime_state': runtime_state, 'dry_run': mock_mode}


def apply_instance(db: Session, instance: Instance) -> Instance:
    tenant = db.query(Tenant).filter(Tenant.id == instance.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail='tenant not found')
    return deploy_instance(db, tenant, instance, dry_run=None, wait_ready=True)['instance']


def delete_instance(db: Session, instance: Instance) -> Instance:
    settings = get_settings()
    tenant = db.query(Tenant).filter(Tenant.id == instance.tenant_id).first()
    ok, output, meta = kubectl_delete(settings, instance.manifest_path, force_dry_run=None)
    delete_mock_runtime_state(settings, tenant.slug if tenant else instance.name)
    instance.status = 'deleted' if ok else 'delete_failed'
    instance.last_apply_output = output
    if tenant:
        tenant.status = 'runtime_deleted' if ok else 'delete_failed'
        db.add(tenant)
        add_job(db, tenant, action='delete_runtime', status='succeeded' if ok else 'failed', message={'output': output, 'meta': meta})
    db.add(instance)
    db.commit()
    db.refresh(instance)
    if not ok:
        raise HTTPException(status_code=500, detail={'message': 'kubectl delete failed', 'output': output})
    return instance


async def init_newapi(db: Session, tenant: Tenant, *, force: bool = False) -> dict:
    settings = get_settings()
    if not tenant.instances:
        raise HTTPException(status_code=404, detail='instance not found')
    instance = tenant.instances[0]
    if instance.status not in {'running', 'running_mock', 'runtime_ready', 'runtime_ready_mock'} and not force:
        raise HTTPException(status_code=409, detail=f'instance is not running: {instance.status}; call /deploy first or pass force=true')
    client = NewAPIClient(instance.endpoint, admin_token=settings.newapi_admin_token, mock=not real_external_enabled(settings, 'newapi'), allow_real=real_external_enabled(settings, 'newapi'), settings=settings)
    admin_result = await client.create_admin(tenant.admin_username, tenant.admin_password)
    token_result = await client.create_token(tenant.slug, name='default-runtime-token')
    instance.status = 'newapi_initialized' if real_external_enabled(settings, 'newapi') else 'newapi_initialized_mock'
    tenant.status = 'newapi_initialized' if real_external_enabled(settings, 'newapi') else 'newapi_initialized_mock'
    db.add_all([tenant, instance])
    result = {'admin': admin_result, 'token': token_result, 'endpoint': instance.endpoint}
    add_job(db, tenant, action='init_newapi', status='succeeded', message=result)
    db.commit()
    return result


async def bind_upstream(db: Session, tenant: Tenant, *, force: bool = False) -> dict:
    settings = get_settings()
    if not tenant.instances:
        raise HTTPException(status_code=404, detail='instance not found')
    if not tenant.upstreams:
        sub_key = await Sub2APIClient(settings).create_tenant_key(tenant.slug)
        upstream = UpstreamBinding(tenant_id=tenant.id, sub2api_base_url=settings.sub2api_base_url, sub2api_key=sub_key, policy={'default': True}, status='created')
        db.add(upstream)
        db.flush()
    upstream = tenant.upstreams[0]
    instance = tenant.instances[0]
    if instance.status not in {'newapi_initialized', 'newapi_initialized_mock', 'running', 'running_mock'} and not force:
        raise HTTPException(status_code=409, detail=f'New API not initialized: {instance.status}; call /init-newapi first or pass force=true')
    sub_verify = await Sub2APIClient(settings).verify_key(tenant.slug, upstream.sub2api_key)
    channel = await NewAPIClient(instance.endpoint, admin_token=settings.newapi_admin_token, mock=not real_external_enabled(settings, 'newapi'), allow_real=real_external_enabled(settings, 'newapi'), settings=settings).create_channel(
        upstream.name,
        upstream.sub2api_base_url,
        upstream.sub2api_key,
    )
    upstream.status = 'bound' if (real_external_enabled(settings, 'newapi') and real_external_enabled(settings, 'sub2api')) else 'bound_mock'
    upstream.policy = {**(upstream.policy or {}), 'last_bind': channel, 'sub2api_verify': sub_verify}
    tenant.status = 'upstream_bound_mock' if upstream.status == 'bound_mock' else 'upstream_bound'
    db.add_all([tenant, upstream])
    result = {'upstream_id': upstream.id, 'sub2api': sub_verify, 'newapi_channel': channel}
    add_job(db, tenant, action='bind_upstream', status='succeeded', message=result)
    db.commit()
    return result


async def provision_tenant(db: Session, tenant: Tenant, *, dry_run: bool | None = None, verify_domains: bool = True) -> dict:
    instance = ensure_instance_manifest(db, tenant)
    deploy_result = deploy_instance(db, tenant, instance, dry_run=dry_run, wait_ready=True)
    # 让 mock 状态的更新时间有稳定顺序，方便本地读日志。
    time.sleep(get_settings().provision_wait_seconds)
    init_result = await init_newapi(db, tenant, force=True)
    bind_result = await bind_upstream(db, tenant, force=True)
    domain_results = []
    if verify_domains:
        # 重新读取 domains，避免关系对象 stale。
        domains = db.execute(select(Domain).where(Domain.tenant_id == tenant.id)).scalars().all()
        for d in domains:
            verified = await verify_domain(db, tenant, d)
            domain_results.append({'domain': verified.domain, 'status': verified.status, 'validation_status': verified.validation_status})
    tenant.status = 'active_mock' if deploy_result['dry_run'] else 'active'
    db.add(tenant)
    add_job(db, tenant, action='provision_tenant', status='succeeded', message={'deploy': deploy_result['output'], 'init': init_result, 'bind': bind_result, 'domains': domain_results})
    db.commit()
    deploy_summary = {
        'instance_id': deploy_result['instance'].id,
        'instance_status': deploy_result['instance'].status,
        'output': deploy_result['output'],
        'meta': deploy_result['meta'],
        'runtime_state': deploy_result['runtime_state'],
        'dry_run': deploy_result['dry_run'],
    }
    return {'deploy': deploy_summary, 'init_newapi': init_result, 'bind_upstream': bind_result, 'domains': domain_results}


def manifest_validation_for_tenant(tenant: Tenant) -> dict:
    if not tenant.instances or not tenant.instances[0].manifest_path:
        return {'ok': False, 'message': 'manifest not generated'}
    return validate_manifest(tenant.instances[0].manifest_path, get_settings())


def deployment_plan_for_tenant(tenant: Tenant) -> dict:
    """Build a non-mutating deployment plan for the tenant.

    The plan is safe for Codex/local validation: it never calls Sealos, New API,
    Sub2API, Cloudflare, kubectl, or DNS providers.
    """
    settings = get_settings()
    instance = tenant.instances[0] if tenant.instances else None
    manifest_validation = validate_manifest(instance.manifest_path, settings) if instance and instance.manifest_path else {'ok': False, 'message': 'manifest not generated'}
    domain_value = primary_domain(tenant)
    upstream = tenant.upstreams[0] if tenant.upstreams else None
    safe_snapshot = safe_settings_snapshot(settings)

    steps = [
        {
            'phase': 2,
            'name': 'deploy_newapi_runtime',
            'method': 'POST',
            'endpoint': f'/api/v1/tenants/{tenant.id}/deploy',
            'mode': safe_snapshot['k8s']['effective_mode'],
            'will_call_external': False if safe_snapshot['k8s']['effective_mode'] != 'real_enabled' else True,
            'status_source': 'instances.status',
            'expected_status_mock': 'running_mock',
        },
        {
            'phase': 3,
            'name': 'init_newapi_admin_and_token',
            'method': 'POST',
            'endpoint': f'/api/v1/tenants/{tenant.id}/init-newapi',
            'mode': safe_snapshot['newapi']['effective_mode'],
            'will_call_external': False if safe_snapshot['newapi']['effective_mode'] != 'real_enabled' else True,
            'expected_status_mock': 'newapi_initialized_mock',
        },
        {
            'phase': 4,
            'name': 'bind_sub2api_upstream_to_newapi_channel',
            'method': 'POST',
            'endpoint': f'/api/v1/tenants/{tenant.id}/bind-upstream',
            'mode': 'newapi=%s, sub2api=%s' % (safe_snapshot['newapi']['effective_mode'], safe_snapshot['sub2api']['effective_mode']),
            'will_call_external': safe_snapshot['newapi']['effective_mode'] == 'real_enabled' or safe_snapshot['sub2api']['effective_mode'] == 'real_enabled',
            'expected_status_mock': 'upstream_bound_mock',
        },
        {
            'phase': 5,
            'name': 'verify_domains',
            'method': 'POST',
            'endpoint': f'/api/v1/tenants/{tenant.id}/provision',
            'mode': safe_snapshot['cloudflare']['effective_mode'],
            'will_call_external': False if safe_snapshot['cloudflare']['effective_mode'] != 'real_enabled' else True,
            'expected_status_mock': 'active_mock',
        },
    ]

    return {
        'tenant': {
            'id': tenant.id,
            'slug': tenant.slug,
            'status': tenant.status,
            'primary_domain': domain_value,
            'endpoint': f'https://{domain_value}' if domain_value else None,
        },
        'instance': {
            'id': instance.id if instance else None,
            'name': instance.name if instance else None,
            'namespace': instance.namespace if instance else None,
            'status': instance.status if instance else None,
            'manifest_path': instance.manifest_path if instance else None,
        },
        'manifest_validation': manifest_validation,
        'upstream': {
            'id': upstream.id if upstream else None,
            'status': upstream.status if upstream else None,
            'base_url': upstream.sub2api_base_url if upstream else settings.sub2api_base_url,
            'key_suffix': upstream.sub2api_key[-8:] if upstream else None,
        },
        'safety': safe_snapshot['safety'],
        'warnings': safe_snapshot['warnings'],
        'steps': steps,
        'one_shot': {
            'method': 'POST',
            'endpoint': f'/api/v1/tenants/{tenant.id}/provision',
            'body': {'dry_run': True, 'verify_domains': True},
        },
    }
