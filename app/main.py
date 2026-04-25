from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.tenants import router as tenants_router
from app.api.manifests import router as manifests_router
from app.api.runtime import router as runtime_router
from app.api.mock import router as mock_router
from app.api.system import router as system_router
from app.api.jobs import router as jobs_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version='0.10-realflow',
    description='AI API 中转 SaaS 控制面 MVP v0.10-realflow：以 v0.10 为基线收口开站工厂，补齐真实 Sealos/New API/Sub2API 适配结构；默认仍为 mock/dry-run。'
)
app.include_router(health_router)
app.include_router(tenants_router)
app.include_router(manifests_router)
app.include_router(runtime_router)
app.include_router(mock_router)
app.include_router(system_router)
app.include_router(jobs_router)
