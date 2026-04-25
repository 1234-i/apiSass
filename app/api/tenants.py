from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from app.core.security import require_api_key
from app.db.session import get_db
from app.models.tenant import Tenant, Domain
from app.schemas.tenant import (
    TenantCreate, TenantOut, TenantDetail, TenantUpdate, QuotaUpdate, QuotaOut,
    CustomDomainCreate, DomainOut, InstanceOut, ApplyRequest, NewAPIInitRequest,
    UpstreamBindRequest, ProvisionRequest, OperationResult,
)
from app.services.tenant_service import (
    create_tenant, update_quota, add_custom_domain, verify_domain, apply_instance,
    delete_instance, deploy_instance, init_newapi, bind_upstream, provision_tenant,
    manifest_validation_for_tenant, deployment_plan_for_tenant,
)

router = APIRouter(prefix='/api/v1/tenants', tags=['tenants'], dependencies=[Depends(require_api_key)])


def tenant_query():
    return select(Tenant).options(
        selectinload(Tenant.domains),
        selectinload(Tenant.instances),
        selectinload(Tenant.quota),
        selectinload(Tenant.upstreams),
        selectinload(Tenant.jobs),
    )


def load_tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.execute(tenant_query().where(Tenant.id == tenant_id)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail='tenant not found')
    return tenant


def to_out(t: Tenant) -> TenantOut:
    domain = next((d.domain for d in t.domains if d.type == 'subdomain'), None) if t.domains else None
    domain = domain or (t.domains[0].domain if t.domains else None)
    inst = t.instances[0] if t.instances else None
    return TenantOut(
        id=t.id, name=t.name, slug=t.slug, email=t.email, plan=t.plan, status=t.status,
        admin_username=t.admin_username, url=f'https://{domain}' if domain else None,
        namespace=inst.namespace if inst else None,
        manifest_path=inst.manifest_path if inst else None,
    )


def to_detail(t: Tenant) -> TenantDetail:
    out = to_out(t).model_dump()
    out['domains'] = t.domains
    out['instances'] = t.instances
    out['quota'] = t.quota
    out['upstreams'] = t.upstreams
    out['jobs'] = t.jobs
    return TenantDetail(**out)

@router.post('', response_model=TenantOut)
async def create(payload: TenantCreate, db: Session = Depends(get_db)):
    tenant = await create_tenant(db, payload)
    loaded = load_tenant(db, tenant.id)
    return to_out(loaded)

@router.get('', response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db)):
    rows = db.execute(tenant_query().order_by(Tenant.created_at.desc())).scalars().all()
    return [to_out(t) for t in rows]

@router.get('/{tenant_id}', response_model=TenantDetail)
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    return to_detail(load_tenant(db, tenant_id))

@router.patch('/{tenant_id}', response_model=TenantOut)
def patch_tenant(tenant_id: str, payload: TenantUpdate, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    if payload.name is not None:
        tenant.name = payload.name
    if payload.plan is not None:
        tenant.plan = payload.plan
    if payload.status is not None:
        tenant.status = payload.status
    db.add(tenant)
    db.commit()
    return to_out(load_tenant(db, tenant_id))

@router.post('/{tenant_id}/suspend', response_model=TenantOut)
def suspend(tenant_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    tenant.status = 'suspended'
    db.add(tenant)
    db.commit()
    return to_out(load_tenant(db, tenant_id))

@router.post('/{tenant_id}/resume', response_model=TenantOut)
def resume(tenant_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    tenant.status = 'active'
    db.add(tenant)
    db.commit()
    return to_out(load_tenant(db, tenant_id))

@router.patch('/{tenant_id}/quota', response_model=QuotaOut)
def patch_quota(tenant_id: str, payload: QuotaUpdate, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    return update_quota(db, tenant, payload)

@router.post('/{tenant_id}/domains', response_model=DomainOut)
async def create_custom_domain(tenant_id: str, payload: CustomDomainCreate, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    return await add_custom_domain(db, tenant, payload.domain, payload.use_cloudflare)

@router.post('/{tenant_id}/domains/{domain_id}/verify', response_model=DomainOut)
async def verify_tenant_domain(tenant_id: str, domain_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    domain = db.query(Domain).filter(Domain.id == domain_id, Domain.tenant_id == tenant.id).first()
    if not domain:
        raise HTTPException(status_code=404, detail='domain not found')
    return await verify_domain(db, tenant, domain)

@router.get('/{tenant_id}/manifest-validation')
def validate_manifest(tenant_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    return manifest_validation_for_tenant(tenant)


@router.get('/{tenant_id}/deployment-plan')
def deployment_plan(tenant_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    return deployment_plan_for_tenant(tenant)

@router.post('/{tenant_id}/apply', response_model=InstanceOut)
def apply_tenant_manifest(tenant_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    if not tenant.instances:
        raise HTTPException(status_code=404, detail='instance not found')
    return apply_instance(db, tenant.instances[0])

@router.post('/{tenant_id}/deploy', response_model=OperationResult)
def deploy_tenant_manifest(tenant_id: str, payload: ApplyRequest | None = None, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    if not tenant.instances:
        raise HTTPException(status_code=404, detail='instance not found')
    payload = payload or ApplyRequest()
    result = deploy_instance(db, tenant, tenant.instances[0], dry_run=payload.dry_run, wait_ready=payload.wait_ready)
    instance = result['instance']
    return OperationResult(
        action='deploy_runtime', status=instance.status, tenant_id=tenant.id, instance_id=instance.id,
        message='runtime deployed in mock/dry-run mode' if result['dry_run'] else 'runtime deployed',
        dry_run=result['dry_run'],
        output={'stdout': result['output'], 'meta': result['meta'], 'runtime_state': result['runtime_state']},
    )

@router.post('/{tenant_id}/init-newapi', response_model=OperationResult)
async def init_tenant_newapi(tenant_id: str, payload: NewAPIInitRequest | None = None, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    payload = payload or NewAPIInitRequest()
    result = await init_newapi(db, tenant, force=payload.force)
    return OperationResult(action='init_newapi', status='succeeded', tenant_id=tenant.id, message='New API initialized in mock mode', dry_run=True, output=result)

@router.post('/{tenant_id}/bind-upstream', response_model=OperationResult)
async def bind_tenant_upstream(tenant_id: str, payload: UpstreamBindRequest | None = None, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    payload = payload or UpstreamBindRequest()
    result = await bind_upstream(db, tenant, force=payload.force)
    return OperationResult(action='bind_upstream', status='succeeded', tenant_id=tenant.id, message='Sub2API upstream bound in mock mode', dry_run=True, output=result)

@router.post('/{tenant_id}/provision', response_model=OperationResult)
async def provision(tenant_id: str, payload: ProvisionRequest | None = None, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    payload = payload or ProvisionRequest()
    result = await provision_tenant(db, tenant, dry_run=payload.dry_run, verify_domains=payload.verify_domains)
    loaded = load_tenant(db, tenant_id)
    return OperationResult(
        action='provision_tenant', status=loaded.status, tenant_id=tenant.id,
        message='Phase 2-5 mock provision completed', dry_run=True, output=result,
    )

@router.post('/{tenant_id}/delete-runtime', response_model=InstanceOut)
def delete_tenant_runtime(tenant_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    if not tenant.instances:
        raise HTTPException(status_code=404, detail='instance not found')
    return delete_instance(db, tenant.instances[0])
