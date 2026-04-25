from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.security import require_api_key
from app.db.session import get_db
from app.models.tenant import Tenant
from app.services.rate_limit import RedisRateLimiter

router = APIRouter(prefix='/api/v1/runtime', tags=['runtime'], dependencies=[Depends(require_api_key)])

@router.post('/{tenant_slug}/check-rpm')
def check_rpm(tenant_slug: str, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if not tenant or not tenant.quota:
        raise HTTPException(status_code=404, detail='tenant or quota not found')
    ok, remaining = RedisRateLimiter().allow(f'tenant:{tenant_slug}:rpm', tenant.quota.rpm, 60)
    return {'allowed': ok, 'remaining': remaining, 'rpm': tenant.quota.rpm}
