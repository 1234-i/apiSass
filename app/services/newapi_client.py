from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class NewAPIClient:
    """New API 管理适配器。

    默认 mock；真实模式必须同时满足：
    ALLOW_REAL_EXTERNAL_CALLS=true、NEWAPI_MOCK=false、NEWAPI_ADMIN_TOKEN 非空。

    New API 官方管理 API 使用 Authorization: Bearer {token}，部分接口还可能需要
    New-Api-User: {user_id}。因此这里把 user_id 做成可选配置项，便于不同版本调试。
    """

    def __init__(
        self,
        endpoint: str,
        admin_token: str | None = None,
        mock: bool = True,
        allow_real: bool = False,
        settings: Settings | None = None,
    ):
        self.endpoint = endpoint.rstrip('/')
        self.admin_token = admin_token
        self.mock = mock
        self.allow_real = allow_real
        self.settings = settings or get_settings()

    def _token(self, tenant_slug: str) -> str:
        digest = hashlib.sha256(f'newapi:{self.endpoint}:{tenant_slug}'.encode()).hexdigest()[:24]
        return f'newapi-mock-token-{digest}'

    def _headers(self) -> dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self.admin_token:
            headers['Authorization'] = f'Bearer {self.admin_token}'
        if self.settings.newapi_admin_user_id:
            headers['New-Api-User'] = self.settings.newapi_admin_user_id
        return headers

    def _url(self, path: str) -> str:
        return f'{self.endpoint}/{path.lstrip("/")}'

    def _render_template_payload(self, template: str, values: dict[str, Any]) -> dict[str, Any]:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace('{' + key + '}', str(value))
        return json.loads(rendered)

    def channel_payload(self, name: str, base_url: str, api_key: str) -> dict[str, Any]:
        values = {
            'name': name,
            'base_url': base_url,
            'api_key': api_key,
            'models': self.settings.newapi_channel_models,
            'group': self.settings.newapi_channel_group,
            'channel_type': self.settings.newapi_channel_type,
        }
        if self.settings.newapi_channel_payload_template:
            return self._render_template_payload(self.settings.newapi_channel_payload_template, values)
        return {
            'mode': self.settings.newapi_channel_mode,
            'channel': {
                'name': name,
                'type': self.settings.newapi_channel_type,
                'key': api_key,
                'base_url': base_url,
                'models': self.settings.newapi_channel_models,
                'group': self.settings.newapi_channel_group,
                'status': 1,
            },
        }

    async def health_check(self) -> dict[str, Any]:
        if self.mock or not self.allow_real or not self.admin_token:
            return {
                'status': 'mocked',
                'operation': 'health_check',
                'endpoint': self.endpoint,
                'message': 'New API health check mock；未调用真实 New API。',
                'checked_at': datetime.now(timezone.utc).isoformat(),
            }
        async with httpx.AsyncClient(timeout=self.settings.newapi_api_timeout_seconds) as client:
            resp = await client.get(self._url(self.settings.newapi_health_path), headers=self._headers())
            return {'status': resp.status_code, 'ok': resp.status_code < 500, 'body': resp.text[:1000]}

    async def create_admin(self, username: str, password: str) -> dict[str, Any]:
        payload = {'username': username, 'password_length': len(password)}
        if self.mock or not self.allow_real or not self.admin_token:
            return {
                'status': 'mocked',
                'operation': 'create_admin',
                'endpoint': self.endpoint,
                'payload': payload,
                'message': 'New API admin 初始化 mock 成功；未调用真实 New API。',
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
        # New API 的 root/admin bootstrap 通常需要通过首次安装 UI 或已有管理员 Access Token 完成。
        # 这里真实模式不盲目创建用户，避免不同版本接口差异导致误操作。
        return {
            'status': 'skipped_manual_bootstrap',
            'operation': 'create_admin',
            'endpoint': self.endpoint,
            'payload': payload,
            'message': '真实模式已启用：New API 管理员需通过首次安装 UI 或已有 Access Token 准备；本步骤跳过用户创建。',
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

    async def create_channel(self, name: str, base_url: str, api_key: str) -> dict[str, Any]:
        payload = self.channel_payload(name, base_url, api_key)
        safe_payload = json.loads(json.dumps(payload, ensure_ascii=False))
        safe_payload_text = json.dumps(safe_payload, ensure_ascii=False)
        if api_key:
            safe_payload_text = safe_payload_text.replace(api_key, f'***{api_key[-8:]}')
        safe_payload = json.loads(safe_payload_text)

        if self.mock or not self.allow_real or not self.admin_token:
            return {
                'status': 'mocked',
                'operation': 'create_channel',
                'endpoint': self.endpoint,
                'path': self.settings.newapi_channel_path,
                'payload': safe_payload,
                'message': 'New API channel 绑定 mock 成功；未调用真实 New API。',
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
        async with httpx.AsyncClient(timeout=self.settings.newapi_api_timeout_seconds) as client:
            resp = await client.post(self._url(self.settings.newapi_channel_path), json=payload, headers=self._headers())
            try:
                data = resp.json()
            except Exception:
                data = {'raw': resp.text[:2000]}
            return {'status': resp.status_code, 'ok': 200 <= resp.status_code < 300, 'path': self.settings.newapi_channel_path, 'response': data, 'payload_preview': safe_payload}

    async def create_token(self, tenant_slug: str, name: str = 'default') -> dict[str, Any]:
        payload = {'name': name}
        if self.mock or not self.allow_real or not self.admin_token:
            return {
                'status': 'mocked',
                'operation': 'create_token',
                'endpoint': self.endpoint,
                'path': self.settings.newapi_token_path,
                'token': self._token(tenant_slug),
                'name': name,
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
        async with httpx.AsyncClient(timeout=self.settings.newapi_api_timeout_seconds) as client:
            resp = await client.post(self._url(self.settings.newapi_token_path), json=payload, headers=self._headers())
            try:
                data = resp.json()
            except Exception:
                data = {'raw': resp.text[:2000]}
            return {'status': resp.status_code, 'ok': 200 <= resp.status_code < 300, 'path': self.settings.newapi_token_path, 'response': data}
