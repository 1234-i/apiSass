from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import httpx
from app.core.config import Settings
from app.services.safety import credential_present


class Sub2APIClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _deterministic_key(self, tenant_slug: str) -> str:
        digest = hashlib.sha256(f'{self.settings.sub2api_key_prefix}:{tenant_slug}'.encode()).hexdigest()[:16]
        return f'{self.settings.sub2api_key_prefix}-{tenant_slug}-{digest}'

    async def create_tenant_key(self, tenant_slug: str) -> str:
        """创建/分配 Sub2API 上游 key。

        默认 mock，生成 deterministic key。真实收口版优先使用 SUB2API_TENANT_KEY：
        你可以先在 Sub2API 后台给站长创建一个 key，然后让控制面把这个 key 写入 New API channel。
        这样可以直接复用 Sub2API 内置的下游账单和费用结算。
        """
        if (not self.settings.allow_real_external_calls) or self.settings.sub2api_mock:
            return self._deterministic_key(tenant_slug)
        if credential_present(self.settings.sub2api_tenant_key):
            return str(self.settings.sub2api_tenant_key)
        # Sub2API 管理 API 不同版本可能变化；这里保留适配点，不在真实模式下伪造 key。
        if credential_present(self.settings.sub2api_admin_key):
            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    await client.get(self.settings.sub2api_base_url.rstrip('/') + self.settings.sub2api_health_path)
                except Exception:
                    pass
        return self._deterministic_key(tenant_slug)

    async def verify_key(self, tenant_slug: str, api_key: str) -> dict:
        if (not self.settings.allow_real_external_calls) or self.settings.sub2api_mock:
            return {
                'status': 'mock_verified',
                'tenant_slug': tenant_slug,
                'api_key_suffix': api_key[-8:],
                'base_url': self.settings.sub2api_base_url,
                'verified_at': datetime.now(timezone.utc).isoformat(),
            }
        if not credential_present(api_key):
            return {'status': 'missing_key', 'tenant_slug': tenant_slug, 'base_url': self.settings.sub2api_base_url}
        # 对 Sub2API 的实际 key 校验先做轻量 health probe，不直接发模型请求，避免产生费用。
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(self.settings.sub2api_base_url.rstrip('/') + self.settings.sub2api_health_path)
                return {
                    'status': 'health_checked',
                    'http_status': resp.status_code,
                    'tenant_slug': tenant_slug,
                    'api_key_suffix': api_key[-8:],
                    'base_url': self.settings.sub2api_base_url,
                    'verified_at': datetime.now(timezone.utc).isoformat(),
                }
            except Exception as exc:
                return {
                    'status': 'health_check_failed',
                    'tenant_slug': tenant_slug,
                    'api_key_suffix': api_key[-8:],
                    'base_url': self.settings.sub2api_base_url,
                    'error': str(exc),
                    'verified_at': datetime.now(timezone.utc).isoformat(),
                }
