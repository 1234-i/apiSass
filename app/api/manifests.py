from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.core.security import require_api_key
from app.db.session import get_db
from app.models.tenant import Instance

router = APIRouter(prefix='/api/v1/manifests', tags=['manifests'], dependencies=[Depends(require_api_key)])

@router.get('/{tenant_id}', response_class=PlainTextResponse)
def get_manifest(tenant_id: str, db: Session = Depends(get_db)):
    inst = db.query(Instance).filter(Instance.tenant_id == tenant_id).first()
    if not inst or not inst.manifest_path:
        raise HTTPException(status_code=404, detail='manifest not found')
    path = Path(inst.manifest_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail='manifest file missing')
    return path.read_text(encoding='utf-8')
