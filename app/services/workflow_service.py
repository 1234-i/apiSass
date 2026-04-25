from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.tenant import AuditEvent, DeploymentJob, Domain, Tenant
from app.schemas.tenant import ProvisionJobRequest, JobRetryRequest, WorkerTickRequest
from app.services.audit_service import record_event
from app.services.tenant_service import (
    bind_upstream,
    deploy_instance,
    ensure_instance_manifest,
    init_newapi,
    verify_domain,
)

WORKFLOW_ACTION_PROVISION = 'workflow_provision'
RUNNABLE_STATUSES = {'queued', 'pending'}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _load_job(db: Session, job_id: str) -> DeploymentJob | None:
    return db.execute(
        select(DeploymentJob)
        .options(selectinload(DeploymentJob.events))
        .where(DeploymentJob.id == job_id)
    ).scalar_one_or_none()


def get_job_or_404(db: Session, job_id: str) -> DeploymentJob:
    job = _load_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='job not found')
    return job


def list_jobs_for_tenant(db: Session, tenant: Tenant) -> list[DeploymentJob]:
    return db.execute(
        select(DeploymentJob)
        .where(DeploymentJob.tenant_id == tenant.id)
        .order_by(DeploymentJob.created_at.desc())
    ).scalars().all()


def list_audit_events_for_tenant(db: Session, tenant: Tenant, limit: int = 100) -> list[AuditEvent]:
    return db.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).scalars().all()


def list_audit_events_for_job(db: Session, job: DeploymentJob) -> list[AuditEvent]:
    return db.execute(
        select(AuditEvent)
        .where(AuditEvent.job_id == job.id)
        .order_by(AuditEvent.created_at.asc())
    ).scalars().all()


def _find_idempotent_job(db: Session, tenant: Tenant, idempotency_key: str | None) -> DeploymentJob | None:
    if not idempotency_key:
        return None
    return db.execute(
        select(DeploymentJob)
        .where(
            DeploymentJob.tenant_id == tenant.id,
            DeploymentJob.action == WORKFLOW_ACTION_PROVISION,
            DeploymentJob.idempotency_key == idempotency_key,
        )
        .order_by(DeploymentJob.created_at.desc())
    ).scalar_one_or_none()


def _request_snapshot(payload: ProvisionJobRequest) -> dict[str, Any]:
    return {
        'dry_run': payload.dry_run,
        'verify_domains': payload.verify_domains,
        'run_inline': payload.run_inline,
        'idempotency_key': payload.idempotency_key,
        'max_attempts': payload.max_attempts,
        'simulate_failure_phase': payload.simulate_failure_phase,
    }


def _payload_from_job(job: DeploymentJob) -> ProvisionJobRequest:
    result = job.result or {}
    request = result.get('request') or result
    return ProvisionJobRequest(
        dry_run=request.get('dry_run'),
        verify_domains=bool(request.get('verify_domains', True)),
        run_inline=bool(request.get('run_inline', True)),
        idempotency_key=job.idempotency_key or request.get('idempotency_key'),
        max_attempts=int(job.max_attempts or request.get('max_attempts') or 3),
        simulate_failure_phase=request.get('simulate_failure_phase'),
    )


def _set_request_snapshot(job: DeploymentJob, payload: ProvisionJobRequest, *, preserve_result: dict | None = None) -> None:
    current = preserve_result if preserve_result is not None else (job.result or {})
    job.result = {**current, 'request': _request_snapshot(payload)}


def _maybe_fail(payload: ProvisionJobRequest, phase: str) -> None:
    if payload.simulate_failure_phase == phase:
        raise RuntimeError(f'mock simulated failure at phase: {phase}')


def create_provision_job(db: Session, tenant: Tenant, payload: ProvisionJobRequest) -> tuple[DeploymentJob, bool]:
    """Create a workflow job or return an existing one for the idempotency key."""
    existing = _find_idempotent_job(db, tenant, payload.idempotency_key)
    if existing:
        record_event(
            db,
            tenant=tenant,
            job=existing,
            event_type='job.idempotent_reuse',
            message='Returned existing provision workflow job for idempotency key',
            payload={'idempotency_key': payload.idempotency_key, 'job_id': existing.id, 'status': existing.status},
        )
        db.commit()
        return get_job_or_404(db, existing.id), True

    job = DeploymentJob(
        tenant_id=tenant.id,
        action=WORKFLOW_ACTION_PROVISION,
        status='queued',
        idempotency_key=payload.idempotency_key,
        message='provision workflow queued',
        result={'request': _request_snapshot(payload)},
        attempts=0,
        max_attempts=payload.max_attempts,
        next_run_at=_utcnow(),
    )
    db.add(job)
    db.flush()
    record_event(
        db,
        tenant=tenant,
        job=job,
        event_type='job.created',
        message='Provision workflow job created',
        payload=_request_snapshot(payload),
    )
    db.commit()
    return get_job_or_404(db, job.id), False


async def run_provision_job_inline(
    db: Session,
    tenant: Tenant,
    job: DeploymentJob,
    payload: ProvisionJobRequest | None = None,
    *,
    worker_id: str = 'mock-worker-inline',
    force: bool = False,
) -> DeploymentJob:
    """Run Phase 2-5 provision workflow inline in mock/dry-run-safe mode."""
    payload = payload or _payload_from_job(job)

    if job.status == 'succeeded':
        return get_job_or_404(db, job.id)
    if job.status == 'cancelled' and not force:
        raise HTTPException(status_code=409, detail='job is cancelled; retry it before running')
    if job.status == 'running' and not force:
        raise HTTPException(status_code=409, detail='job is already running')
    if job.status == 'failed' and not force:
        raise HTTPException(status_code=409, detail='job failed; call /retry to requeue it')
    if job.attempts >= job.max_attempts and job.status != 'failed' and not force:
        raise HTTPException(status_code=409, detail='job has exhausted max_attempts')

    results: dict[str, Any] = {}
    request_snapshot = _request_snapshot(payload)
    try:
        job.attempts = int(job.attempts or 0) + 1
        job.max_attempts = payload.max_attempts
        job.status = 'running'
        job.message = 'provision workflow running'
        job.locked_by = worker_id
        job.locked_at = _utcnow()
        job.completed_at = None
        job.next_run_at = None
        _set_request_snapshot(job, payload)
        db.add(job)
        record_event(db, tenant=tenant, job=job, event_type='job.attempt.started', message='Provision workflow attempt started', payload={'attempt': job.attempts, 'max_attempts': job.max_attempts, 'worker_id': worker_id})
        record_event(db, tenant=tenant, job=job, event_type='job.started', message='Provision workflow started', payload={'worker_id': worker_id, 'request': request_snapshot})
        db.commit()

        _maybe_fail(payload, 'deploy')
        record_event(db, tenant=tenant, job=job, event_type='phase.deploy.started', message='Phase 2 deploy runtime started')
        instance = ensure_instance_manifest(db, tenant)
        deploy_result = deploy_instance(db, tenant, instance, dry_run=payload.dry_run, wait_ready=True)
        results['deploy'] = {
            'instance_id': deploy_result['instance'].id,
            'status': deploy_result['instance'].status,
            'dry_run': deploy_result['dry_run'],
            'runtime_state': deploy_result['runtime_state'],
            'meta': deploy_result['meta'],
        }
        record_event(db, tenant=tenant, job=job, event_type='phase.deploy.succeeded', message='Phase 2 deploy runtime succeeded', payload=results['deploy'])
        db.commit()

        _maybe_fail(payload, 'init_newapi')
        record_event(db, tenant=tenant, job=job, event_type='phase.init_newapi.started', message='Phase 3 New API init started')
        init_result = await init_newapi(db, tenant, force=True)
        results['init_newapi'] = init_result
        record_event(db, tenant=tenant, job=job, event_type='phase.init_newapi.succeeded', message='Phase 3 New API init succeeded', payload=init_result)
        db.commit()

        _maybe_fail(payload, 'bind_upstream')
        record_event(db, tenant=tenant, job=job, event_type='phase.bind_upstream.started', message='Phase 4 upstream bind started')
        bind_result = await bind_upstream(db, tenant, force=True)
        results['bind_upstream'] = bind_result
        record_event(db, tenant=tenant, job=job, event_type='phase.bind_upstream.succeeded', message='Phase 4 upstream bind succeeded', payload=bind_result)
        db.commit()

        _maybe_fail(payload, 'domains')
        domain_results: list[dict[str, str | None]] = []
        if payload.verify_domains:
            record_event(db, tenant=tenant, job=job, event_type='phase.domains.started', message='Phase 5 domain verification started')
            domains = db.execute(select(Domain).where(Domain.tenant_id == tenant.id)).scalars().all()
            for domain in domains:
                verified = await verify_domain(db, tenant, domain)
                domain_results.append({'domain': verified.domain, 'status': verified.status, 'validation_status': verified.validation_status})
            record_event(db, tenant=tenant, job=job, event_type='phase.domains.succeeded', message='Phase 5 domain verification succeeded', payload={'domains': domain_results})
            db.commit()
        results['domains'] = domain_results

        _maybe_fail(payload, 'complete')
        tenant.status = 'active_mock' if results.get('deploy', {}).get('dry_run', True) else 'active'
        job.status = 'succeeded'
        job.message = 'provision workflow completed'
        job.result = {'request': request_snapshot, 'attempts': job.attempts, 'max_attempts': job.max_attempts, 'results': results}
        job.completed_at = _utcnow()
        job.locked_by = None
        job.locked_at = None
        job.next_run_at = None
        db.add_all([tenant, job])
        record_event(db, tenant=tenant, job=job, event_type='job.succeeded', message='Provision workflow completed', payload={'status': tenant.status, 'attempt': job.attempts})
        db.commit()
        return get_job_or_404(db, job.id)
    except Exception as exc:
        exhausted = job.attempts >= job.max_attempts
        job.status = 'failed'
        job.message = 'provision workflow failed'
        job.result = {
            'request': request_snapshot,
            'attempts': job.attempts,
            'max_attempts': job.max_attempts,
            'error': str(exc),
            'partial': results,
            'retry_available': not exhausted,
        }
        job.completed_at = _utcnow()
        job.locked_by = None
        job.locked_at = None
        job.next_run_at = None if exhausted else _utcnow() + timedelta(seconds=get_settings().workflow_retry_backoff_seconds)
        db.add(job)
        record_event(db, tenant=tenant, job=job, event_type='job.failed', severity='error', message=str(exc), payload={'partial': results, 'attempt': job.attempts, 'max_attempts': job.max_attempts, 'retry_available': not exhausted})
        if not exhausted:
            record_event(db, tenant=tenant, job=job, event_type='job.retry_available', message='Job can be retried', payload={'next_run_at': job.next_run_at.isoformat() if job.next_run_at else None})
        db.commit()
        return get_job_or_404(db, job.id)


async def create_and_optionally_run_provision_job(db: Session, tenant: Tenant, payload: ProvisionJobRequest) -> DeploymentJob:
    job, reused = create_provision_job(db, tenant, payload)
    if reused:
        return job
    if payload.run_inline:
        return await run_provision_job_inline(db, tenant, job, payload, worker_id='mock-worker-inline')
    return job


async def run_job_by_id(db: Session, job_id: str, *, worker_id: str = 'mock-worker-inline', force: bool = False) -> DeploymentJob:
    job = get_job_or_404(db, job_id)
    tenant = db.execute(select(Tenant).where(Tenant.id == job.tenant_id)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail='tenant not found for job')
    if job.action != WORKFLOW_ACTION_PROVISION:
        raise HTTPException(status_code=400, detail=f'unsupported job action: {job.action}')
    return await run_provision_job_inline(db, tenant, job, _payload_from_job(job), worker_id=worker_id, force=force)


def cancel_job(db: Session, job_id: str, *, reason: str | None = None) -> DeploymentJob:
    job = get_job_or_404(db, job_id)
    tenant = db.execute(select(Tenant).where(Tenant.id == job.tenant_id)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail='tenant not found for job')
    if job.status not in {'queued', 'pending'}:
        raise HTTPException(status_code=409, detail=f'cannot cancel job in status {job.status}')
    job.status = 'cancelled'
    job.message = reason or 'cancelled by operator'
    job.completed_at = _utcnow()
    job.locked_by = None
    job.locked_at = None
    job.next_run_at = None
    db.add(job)
    record_event(db, tenant=tenant, job=job, event_type='job.cancelled', message=job.message, payload={'reason': job.message})
    db.commit()
    return get_job_or_404(db, job.id)


async def retry_job(db: Session, job_id: str, payload: JobRetryRequest) -> DeploymentJob:
    job = get_job_or_404(db, job_id)
    tenant = db.execute(select(Tenant).where(Tenant.id == job.tenant_id)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail='tenant not found for job')
    if job.status not in {'failed', 'cancelled'}:
        raise HTTPException(status_code=409, detail=f'cannot retry job in status {job.status}')

    request = _payload_from_job(job)
    if payload.max_attempts is not None:
        job.max_attempts = payload.max_attempts
        request.max_attempts = payload.max_attempts
    elif job.attempts >= job.max_attempts:
        job.max_attempts = job.attempts + 1
        request.max_attempts = job.max_attempts

    if payload.clear_simulated_failure:
        request.simulate_failure_phase = None
    if payload.simulate_failure_phase is not None:
        request.simulate_failure_phase = payload.simulate_failure_phase

    job.status = 'queued'
    job.message = 'job requeued for retry'
    job.completed_at = None
    job.locked_by = None
    job.locked_at = None
    job.next_run_at = _utcnow()
    _set_request_snapshot(job, request, preserve_result=job.result or {})
    db.add(job)
    record_event(db, tenant=tenant, job=job, event_type='job.retried', message='Job requeued for retry', payload={'attempts': job.attempts, 'max_attempts': job.max_attempts, 'clear_simulated_failure': payload.clear_simulated_failure})
    db.commit()
    if payload.run_inline:
        return await run_provision_job_inline(db, tenant, get_job_or_404(db, job.id), request, worker_id=payload.worker_id, force=True)
    return get_job_or_404(db, job.id)


async def tick_mock_worker(db: Session, payload: WorkerTickRequest) -> tuple[list[DeploymentJob], list[str]]:
    now = _utcnow()
    jobs = db.execute(
        select(DeploymentJob)
        .where(
            DeploymentJob.action == WORKFLOW_ACTION_PROVISION,
            DeploymentJob.status.in_(list(RUNNABLE_STATUSES)),
        )
        .order_by(DeploymentJob.created_at.asc())
        .limit(payload.limit)
    ).scalars().all()

    processed: list[DeploymentJob] = []
    ids: list[str] = []
    for job in jobs:
        if job.next_run_at is not None and job.next_run_at > now:
            continue
        tenant = db.execute(select(Tenant).where(Tenant.id == job.tenant_id)).scalar_one_or_none()
        if not tenant:
            continue
        record_event(db, tenant=tenant, job=job, event_type='worker.tick.claimed', message='Mock worker claimed job', payload={'worker_id': payload.worker_id})
        db.commit()
        ran = await run_provision_job_inline(db, tenant, job, _payload_from_job(job), worker_id=payload.worker_id)
        processed.append(ran)
        ids.append(ran.id)
    return processed, ids
