from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import httpx
from app.core.config import Settings
from app.services.safety import credential_present, real_external_enabled

class CloudflareClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def enabled(self) -> bool:
        return credential_present(self.settings.cloudflare_api_token) and credential_present(self.settings.cloudflare_zone_id)

    async def create_custom_hostname(self, hostname: str) -> dict:
        """Cloudflare for SaaS custom hostname 适配点。默认 mock，不需要真实 Cloudflare。"""
        target = self.settings.cloudflare_custom_hostname_fallback_origin or self.settings.public_gateway_cname
        if not real_external_enabled(self.settings, 'cloudflare'):
            txt = hashlib.sha256(hostname.encode()).hexdigest()[:24]
            return {
                'status': 'mock_pending_validation',
                'dns_target': target,
                'hostname': hostname,
                'validation_record': {'type': 'CNAME', 'name': hostname, 'value': target},
                'ownership_record': {'type': 'TXT', 'name': f'_cf-custom-hostname.{hostname}', 'value': txt},
                'message': 'Cloudflare mock：请让客户 CNAME 到 dns_target；真实模式会创建 custom hostname。',
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
        url = f'https://api.cloudflare.com/client/v4/zones/{self.settings.cloudflare_zone_id}/custom_hostnames'
        payload = {
            'hostname': hostname,
            'ssl': {'method': 'http', 'type': 'dv', 'settings': {'http2': 'on', 'tls_1_3': 'on'}},
        }
        headers = {'Authorization': f'Bearer {self.settings.cloudflare_api_token}', 'Content-Type': 'application/json'}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers=headers)
            try:
                data = resp.json()
            except Exception:
                data = {'raw': resp.text}
        return {'status': resp.status_code, 'dns_target': target, 'response': data}

    async def verify_custom_hostname(self, hostname: str) -> dict:
        target = self.settings.cloudflare_custom_hostname_fallback_origin or self.settings.public_gateway_cname
        if not real_external_enabled(self.settings, 'cloudflare'):
            return {
                'status': 'mock_active',
                'hostname': hostname,
                'dns_target': target,
                'ssl_status': 'mock_issued',
                'verified_at': datetime.now(timezone.utc).isoformat(),
            }
        return {'status': 'not_implemented_real_verify', 'hostname': hostname}
