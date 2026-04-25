from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.core.security import require_api_key
from app.db.session import get_db
from app.models.tenant import DeploymentJob
from app.schemas.tenant import (
    AuditEventOut,
    JobCancelRequest,
    JobOut,
    JobRetryRequest,
    JobRunRequest,
    ProvisionJobRequest,
    WorkerTickOut,
    WorkerTickRequest,
    WorkflowJobOut,
)
from app.services.workflow_service import (
    cancel_job,
    create_and_optionally_run_provision_job,
    get_job_or_404,
    list_audit_events_for_job,
    list_audit_events_for_tenant,
    list_jobs_for_tenant,
    retry_job,
    run_job_by_id,
    tick_mock_worker,
)
from app.api.tenants import load_tenant

router = APIRouter(tags=['jobs'], dependencies=[Depends(require_api_key)])


def to_workflow_job(job: DeploymentJob, events=None) -> WorkflowJobOut:
    return WorkflowJobOut(
        id=job.id,
        tenant_id=job.tenant_id,
        action=job.action,
        status=job.status,
        idempotency_key=job.idempotency_key,
        message=job.message,
        result=job.result,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        locked_by=job.locked_by,
        locked_at=job.locked_at,
        next_run_at=job.next_run_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        events=events if events is not None else getattr(job, 'events', []),
    )


@router.post('/api/v1/tenants/{tenant_id}/jobs/provision', response_model=WorkflowJobOut)
async def create_provision_workflow_job(tenant_id: str, payload: ProvisionJobRequest | None = None, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    payload = payload or ProvisionJobRequest()
    job = await create_and_optionally_run_provision_job(db, tenant, payload)
    events = list_audit_events_for_job(db, job)
    return to_workflow_job(job, events)


@router.get('/api/v1/tenants/{tenant_id}/jobs', response_model=list[JobOut])
def list_tenant_jobs(tenant_id: str, db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    return list_jobs_for_tenant(db, tenant)


@router.get('/api/v1/tenants/{tenant_id}/audit-events', response_model=list[AuditEventOut])
def list_tenant_audit_events(tenant_id: str, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    tenant = load_tenant(db, tenant_id)
    return list_audit_events_for_tenant(db, tenant, limit=limit)


@router.get('/api/v1/jobs/{job_id}', response_model=WorkflowJobOut)
def get_workflow_job(job_id: str, db: Session = Depends(get_db)):
    job = db.execute(
        select(DeploymentJob)
        .options(selectinload(DeploymentJob.events))
        .where(DeploymentJob.id == job_id)
    ).scalar_one_or_none()
    if not job:
        job = get_job_or_404(db, job_id)
    return to_workflow_job(job)


@router.get('/api/v1/jobs/{job_id}/events', response_model=list[AuditEventOut])
def list_workflow_job_events(job_id: str, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    return list_audit_events_for_job(db, job)


@router.post('/api/v1/jobs/{job_id}/run', response_model=WorkflowJobOut)
async def run_workflow_job(job_id: str, payload: JobRunRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or JobRunRequest()
    job = await run_job_by_id(db, job_id, worker_id=payload.worker_id, force=payload.force)
    return to_workflow_job(job, list_audit_events_for_job(db, job))


@router.post('/api/v1/jobs/{job_id}/cancel', response_model=WorkflowJobOut)
def cancel_workflow_job(job_id: str, payload: JobCancelRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or JobCancelRequest()
    job = cancel_job(db, job_id, reason=payload.reason)
    return to_workflow_job(job, list_audit_events_for_job(db, job))


@router.post('/api/v1/jobs/{job_id}/retry', response_model=WorkflowJobOut)
async def retry_workflow_job(job_id: str, payload: JobRetryRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or JobRetryRequest()
    job = await retry_job(db, job_id, payload)
    return to_workflow_job(job, list_audit_events_for_job(db, job))


@router.post('/api/v1/workers/mock/provision/tick', response_model=WorkerTickOut)
async def run_mock_worker_tick(payload: WorkerTickRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or WorkerTickRequest()
    jobs, ids = await tick_mock_worker(db, payload)
    return WorkerTickOut(worker_id=payload.worker_id, processed_count=len(jobs), processed_job_ids=ids, jobs=jobs)
