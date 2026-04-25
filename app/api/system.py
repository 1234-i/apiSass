from __future__ import annotations

from fastapi import APIRouter, Depends
from app.core.config import get_settings
from app.core.security import require_api_key
from app.services.safety import safe_settings_snapshot
from app.services.realflow import real_flow_preflight

router = APIRouter(prefix='/api/v1/system', tags=['system'], dependencies=[Depends(require_api_key)])


@router.get('/preflight')
def preflight():
    """Return a safe readiness report for Sealos/K8s/New API/Sub2API/Cloudflare adapters.

    This endpoint intentionally does not call external systems. It only inspects local
    config, local file availability, and whether credentials are present.
    """
    settings = get_settings()
    snapshot = safe_settings_snapshot(settings)
    checks = []

    def add(name: str, ok: bool, message: str):
        checks.append({'name': name, 'ok': ok, 'message': message})

    add('safe_mode', not settings.allow_real_external_calls, 'default mock/dry-run mode is active' if not settings.allow_real_external_calls else 'real external calls may be enabled by configuration')
    add('base_domain', bool(settings.base_domain), f'base domain: {settings.base_domain}')
    add('gateway_cname', bool(settings.public_gateway_cname), f'public gateway cname: {settings.public_gateway_cname}')
    add('manifest_output_dir', bool(settings.manifest_output_dir), f'manifest output dir: {settings.manifest_output_dir}')
    add('mock_runtime_dir', bool(settings.mock_runtime_dir), f'mock runtime dir: {settings.mock_runtime_dir}')

    return {
        'status': 'ok',
        'safe_mode': not settings.allow_real_external_calls,
        'checks': checks,
        'config': snapshot,
    }


@router.get('/real-flow-preflight')
def real_flow_preflight_endpoint():
    """真实开站前预检。默认不调用外部系统，只检查配置/本地文件/安全闸门。"""
    return real_flow_preflight(get_settings())
