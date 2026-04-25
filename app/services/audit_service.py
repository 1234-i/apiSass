from __future__ import annotations

from sqlalchemy.orm import Session
from app.models.tenant import AuditEvent, DeploymentJob, Tenant


def record_event(
    db: Session,
    *,
    tenant: Tenant,
    event_type: str,
    severity: str = 'info',
    message: str | None = None,
    payload: dict | None = None,
    job: DeploymentJob | None = None,
) -> AuditEvent:
    """Create an audit event without committing the transaction.

    v0.8 keeps audit logging local and DB-backed. No external log sink is called.
    """
    event = AuditEvent(
        tenant_id=tenant.id,
        job_id=job.id if job else None,
        event_type=event_type,
        severity=severity,
        message=message,
        payload=payload or {},
    )
    db.add(event)
    db.flush()
    return event
