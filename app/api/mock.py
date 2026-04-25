from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_api_key
from app.core.config import get_settings
from app.services.k8s_renderer import read_mock_runtime_state

router = APIRouter(prefix='/api/v1/mock', tags=['mock'], dependencies=[Depends(require_api_key)])

@router.get('/runtime/{tenant_slug}')
def get_mock_runtime(tenant_slug: str):
    state = read_mock_runtime_state(get_settings(), tenant_slug)
    if not state:
        raise HTTPException(status_code=404, detail='mock runtime state not found')
    return state
