from fastapi import APIRouter
from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(tags=['health'])

@router.get('/health')
def health():
    return {'status': 'ok', 'app': get_settings().app_name}

@router.get('/ready')
def ready():
    with engine.connect() as conn:
        conn.execute(text('select 1'))
    return {'status': 'ready'}
