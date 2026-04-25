import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = 'tenants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default='standard')
    status: Mapped[str] = mapped_column(String(32), default='provisioning')
    admin_username: Mapped[str] = mapped_column(String(128), default='admin')
    admin_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    domains: Mapped[list['Domain']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    instances: Mapped[list['Instance']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    quota: Mapped['Quota'] = relationship(back_populates='tenant', cascade='all, delete-orphan', uselist=False)
    upstreams: Mapped[list['UpstreamBinding']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    jobs: Mapped[list['DeploymentJob']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    audit_events: Mapped[list['AuditEvent']] = relationship(back_populates='tenant', cascade='all, delete-orphan')


class Domain(Base):
    __tablename__ = 'domains'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), default='subdomain')
    status: Mapped[str] = mapped_column(String(32), default='active')
    validation_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dns_target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tenant: Mapped[Tenant] = relationship(back_populates='domains')


class Instance(Base):
    __tablename__ = 'instances'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='generated')
    manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_apply_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tenant: Mapped[Tenant] = relationship(back_populates='instances')


class UpstreamBinding(Base):
    __tablename__ = 'upstream_bindings'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    name: Mapped[str] = mapped_column(String(128), default='default-sub2api')
    sub2api_base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    sub2api_key: Mapped[str] = mapped_column(String(255), nullable=False)
    policy: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default='pending')
    tenant: Mapped[Tenant] = relationship(back_populates='upstreams')


class Quota(Base):
    __tablename__ = 'quotas'
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), primary_key=True)
    rpm: Mapped[int] = mapped_column(Integer, default=60)
    tpm: Mapped[int] = mapped_column(Integer, default=100000)
    monthly_limit: Mapped[int] = mapped_column(Integer, default=10000000)
    tenant: Mapped[Tenant] = relationship(back_populates='quota')


class DeploymentJob(Base):
    __tablename__ = 'deployment_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='queued')
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant: Mapped[Tenant] = relationship(back_populates='jobs')
    events: Mapped[list['AuditEvent']] = relationship(back_populates='job', cascade='all, delete-orphan')


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey('deployment_jobs.id'), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default='info')
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tenant: Mapped[Tenant] = relationship(back_populates='audit_events')
    job: Mapped[DeploymentJob | None] = relationship(back_populates='events')
