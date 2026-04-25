from typing import Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    email: EmailStr
    slug: str | None = Field(default=None, description='用于生成二级域名前缀；为空则根据 name 自动生成')
    plan: str = 'standard'
    admin_username: str = 'admin'
    admin_password: str = Field(min_length=8, default='ChangeMe123!')
    rpm: int = Field(default=60, ge=1)
    tpm: int = Field(default=100000, ge=1)
    monthly_limit: int = Field(default=10000000, ge=1)
    deploy: bool = True
    apply_k8s: bool | None = None

class TenantUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None
    status: str | None = None

class QuotaUpdate(BaseModel):
    rpm: int | None = Field(default=None, ge=1)
    tpm: int | None = Field(default=None, ge=1)
    monthly_limit: int | None = Field(default=None, ge=1)

class CustomDomainCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    use_cloudflare: bool = False

class ApplyRequest(BaseModel):
    dry_run: bool | None = Field(default=None, description='为空则使用 K8S_APPLY_MODE/APPLY_K8S；true 时强制不真实 apply')
    wait_ready: bool = True

class NewAPIInitRequest(BaseModel):
    force: bool = False

class UpstreamBindRequest(BaseModel):
    force: bool = False

class ProvisionRequest(BaseModel):
    dry_run: bool | None = None
    verify_domains: bool = True

class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    email: str
    plan: str
    status: str
    admin_username: str
    url: str | None = None
    namespace: str | None = None
    manifest_path: str | None = None
    model_config = {'from_attributes': True}

class DomainOut(BaseModel):
    id: str
    domain: str
    type: str
    status: str
    validation_status: str | None = None
    dns_target: str | None = None
    model_config = {'from_attributes': True}

class InstanceOut(BaseModel):
    id: str
    name: str
    namespace: str
    endpoint: str
    status: str
    manifest_path: str | None
    last_apply_output: str | None = None
    model_config = {'from_attributes': True}

class QuotaOut(BaseModel):
    rpm: int
    tpm: int
    monthly_limit: int
    model_config = {'from_attributes': True}

class UpstreamOut(BaseModel):
    id: str
    name: str
    sub2api_base_url: str
    sub2api_key: str
    policy: dict
    status: str
    model_config = {'from_attributes': True}

class JobOut(BaseModel):
    id: str
    action: str
    status: str
    idempotency_key: str | None = None
    message: str | None = None
    result: dict | None = None
    attempts: int = 0
    max_attempts: int = 3
    locked_by: str | None = None
    locked_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    model_config = {'from_attributes': True}


class AuditEventOut(BaseModel):
    id: str
    tenant_id: str
    job_id: str | None = None
    event_type: str
    severity: str
    message: str | None = None
    payload: dict | None = None
    created_at: datetime | None = None
    model_config = {'from_attributes': True}


class ProvisionJobRequest(BaseModel):
    dry_run: bool | None = None
    verify_domains: bool = True
    run_inline: bool = True
    idempotency_key: str | None = Field(default=None, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=10)
    simulate_failure_phase: str | None = Field(
        default=None,
        description='mock-only: deploy | init_newapi | bind_upstream | domains | complete',
    )


class JobRunRequest(BaseModel):
    worker_id: str = Field(default='mock-worker-inline', max_length=128)
    force: bool = False


class JobRetryRequest(BaseModel):
    run_inline: bool = True
    worker_id: str = Field(default='mock-worker-retry', max_length=128)
    clear_simulated_failure: bool = True
    simulate_failure_phase: str | None = Field(default=None, description='可选：重试时重新设置 mock failure phase')
    max_attempts: int | None = Field(default=None, ge=1, le=20)


class JobCancelRequest(BaseModel):
    reason: str | None = Field(default='cancelled by operator', max_length=255)


class WorkerTickRequest(BaseModel):
    worker_id: str = Field(default='mock-worker-tick', max_length=128)
    limit: int = Field(default=5, ge=1, le=50)


class WorkerTickOut(BaseModel):
    worker_id: str
    processed_count: int
    processed_job_ids: list[str]
    jobs: list[JobOut]


class WorkflowJobOut(BaseModel):
    id: str
    tenant_id: str
    action: str
    status: str
    idempotency_key: str | None = None
    message: str | None = None
    result: dict | None = None
    attempts: int = 0
    max_attempts: int = 3
    locked_by: str | None = None
    locked_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    events: list[AuditEventOut] = []
    model_config = {'from_attributes': True}

class TenantDetail(TenantOut):
    domains: list[DomainOut] = []
    instances: list[InstanceOut] = []
    quota: QuotaOut | None = None
    upstreams: list[UpstreamOut] = []
    jobs: list[JobOut] = []

class OperationResult(BaseModel):
    action: str
    status: str
    tenant_id: str | None = None
    instance_id: str | None = None
    message: str | None = None
    dry_run: bool = True
    output: Any | None = None
