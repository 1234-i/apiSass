from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import yaml
from app.core.config import Settings


WORKLOAD_KINDS = {'Secret', 'Deployment', 'Service', 'Ingress', 'HorizontalPodAutoscaler'}
REQUIRED_KINDS = {'Namespace'} | WORKLOAD_KINDS


def _selector_labels(slug: str) -> dict[str, str]:
    return {
        'app': f'newapi-{slug}',
        'tenant': slug,
        'managed-by': 'ai-api-saas-control-plane',
        'app.kubernetes.io/managed-by': 'api-saas-control-plane',
    }


def _labels(slug: str, settings: Settings | None = None) -> dict[str, str]:
    labels = _selector_labels(slug)
    if settings and settings.k8s_canary_mode:
        labels.update({
            'api-saas.weisoft.chat/canary': 'true',
            'api-saas.weisoft.chat/tenant-slug': slug,
        })
    return labels


def _annotations(settings: Settings) -> dict[str, str]:
    if not settings.k8s_canary_mode:
        return {}
    return {
        'api-saas.weisoft.chat/canary-created-at': datetime.now(timezone.utc).isoformat(),
        'api-saas.weisoft.chat/canary-max-lifetime-seconds': str(settings.k8s_canary_max_lifetime_seconds),
    }


def _metadata(name: str, namespace: str | None, labels: dict[str, str], annotations: dict[str, str]) -> dict:
    metadata: dict[str, object] = {'name': name, 'labels': labels}
    if namespace:
        metadata['namespace'] = namespace
    if annotations:
        metadata['annotations'] = annotations
    return metadata


def _template_metadata(labels: dict[str, str], annotations: dict[str, str]) -> dict:
    metadata: dict[str, object] = {'labels': labels}
    if annotations:
        metadata['annotations'] = annotations
    return metadata


def namespace_for(settings: Settings, slug: str) -> str:
    if settings.k8s_namespace_mode == 'fixed':
        if not settings.k8s_target_namespace:
            raise ValueError('K8S_TARGET_NAMESPACE is required when K8S_NAMESPACE_MODE=fixed')
        return settings.k8s_target_namespace
    return f'{settings.k8s_namespace_prefix}-{slug}'


def _optional_int(value: str | int | None, name: str) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be an integer when set') from exc


def _pod_security_context(settings: Settings) -> dict:
    context: dict[str, object] = {
        'runAsNonRoot': True,
        'seccompProfile': {'type': 'RuntimeDefault'},
    }
    optional_fields = {
        'runAsUser': _optional_int(settings.k8s_pod_run_as_user, 'K8S_POD_RUN_AS_USER'),
        'runAsGroup': _optional_int(settings.k8s_pod_run_as_group, 'K8S_POD_RUN_AS_GROUP'),
        'fsGroup': _optional_int(settings.k8s_pod_fs_group, 'K8S_POD_FS_GROUP'),
    }
    for key, value in optional_fields.items():
        if value is not None:
            context[key] = value
    return context


def desired_manifest_kinds(settings: Settings | None = None) -> set[str]:
    if settings and settings.k8s_namespace_mode == 'fixed' and not settings.k8s_create_namespace:
        return set(WORKLOAD_KINDS)
    return set(REQUIRED_KINDS)


def render_newapi_manifests(settings: Settings, *, slug: str, domain: str, admin_username: str, admin_password: str) -> list[dict]:
    ns = namespace_for(settings, slug)
    name = f'newapi-{slug}'
    selector_labels = _selector_labels(slug)
    labels = _labels(slug, settings)
    annotations = _annotations(settings)
    secret_name = f'{name}-secret'
    sql_dsn = settings.newapi_sql_dsn_template.format(slug=slug)
    redis_conn = settings.newapi_redis_conn_template.format(slug=slug)
    ingress_spec = {
        'ingressClassName': settings.k8s_ingress_class,
        'rules': [{'host': domain, 'http': {'paths': [{
            'path': '/', 'pathType': 'Prefix',
            'backend': {'service': {'name': name, 'port': {'number': 80}}}
        }]}}]
    }
    if settings.k8s_tls_secret_name and settings.k8s_tls_secret_name.strip():
        ingress_spec['tls'] = [{'hosts': [domain], 'secretName': settings.k8s_tls_secret_name}]

    docs: list[dict] = []
    if settings.k8s_namespace_mode == 'generated' or settings.k8s_create_namespace:
        docs.append({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': _metadata(ns, None, labels, annotations)})
    docs.extend([
        {
            'apiVersion': 'v1', 'kind': 'Secret', 'metadata': _metadata(secret_name, ns, labels, annotations),
            'type': 'Opaque', 'stringData': {
                'SQL_DSN': sql_dsn,
                'REDIS_CONN_STRING': redis_conn,
                'SESSION_SECRET': f'{settings.newapi_session_secret_prefix}-{slug}',
                'CRYPTO_SECRET': f'{settings.newapi_crypto_secret_prefix}-{slug}',
                'TZ': settings.newapi_timezone,
                'STREAMING_TIMEOUT': str(settings.newapi_streaming_timeout_seconds),
                'ERROR_LOG_ENABLED': str(settings.newapi_error_log_enabled).lower(),
                'BATCH_UPDATE_ENABLED': str(settings.newapi_batch_update_enabled).lower(),
                # Optional operator hints only; admin bootstrap may still require New API UI/token flow.
                'ROOT_USERNAME': admin_username,
                'ROOT_PASSWORD': admin_password,
            }
        },
        {
            'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': _metadata(name, ns, labels, annotations),
            'spec': {
                'replicas': settings.newapi_default_replicas,
                'selector': {'matchLabels': selector_labels},
                'template': {'metadata': _template_metadata(labels, annotations), 'spec': {
                    'automountServiceAccountToken': False,
                    'securityContext': _pod_security_context(settings),
                    'containers': [{
                        'name': 'new-api', 'image': settings.newapi_image, 'imagePullPolicy': 'IfNotPresent',
                        'ports': [{'containerPort': settings.newapi_container_port, 'name': 'http'}],
                        'envFrom': [{'secretRef': {'name': secret_name}}],
                        'readinessProbe': {'httpGet': {'path': '/', 'port': 'http'}, 'initialDelaySeconds': 10, 'periodSeconds': 10, 'failureThreshold': 6},
                        'livenessProbe': {'httpGet': {'path': '/', 'port': 'http'}, 'initialDelaySeconds': 30, 'periodSeconds': 20, 'failureThreshold': 6},
                        'resources': {'requests': {'cpu': '100m', 'memory': '256Mi'}, 'limits': {'cpu': '1000m', 'memory': '1Gi'}},
                        'securityContext': {
                            'allowPrivilegeEscalation': False,
                            'capabilities': {'drop': ['ALL']},
                        },
                    }]}}
            }
        },
        {
            'apiVersion': 'v1', 'kind': 'Service', 'metadata': _metadata(name, ns, labels, annotations),
            'spec': {'selector': selector_labels, 'ports': [{'name': 'http', 'port': 80, 'targetPort': 'http'}]}
        },
        {
            'apiVersion': 'networking.k8s.io/v1', 'kind': 'Ingress',
            'metadata': _metadata(
                name,
                ns,
                labels,
                {'kubernetes.io/ingress.class': settings.k8s_ingress_class, **annotations},
            ),
            'spec': ingress_spec
        },
        {
            'apiVersion': 'autoscaling/v2', 'kind': 'HorizontalPodAutoscaler',
            'metadata': _metadata(name, ns, labels, annotations),
            'spec': {
                'scaleTargetRef': {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'name': name},
                'minReplicas': settings.newapi_default_replicas,
                'maxReplicas': max(2, settings.newapi_default_replicas * 3),
                'metrics': [{'type': 'Resource', 'resource': {'name': 'cpu', 'target': {'type': 'Utilization', 'averageUtilization': 70}}}]
            }
        }
    ])
    return docs


def write_manifest(settings: Settings, slug: str, manifests: list[dict]) -> str:
    out_dir = Path(settings.manifest_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'{slug}.yaml'
    with path.open('w', encoding='utf-8') as f:
        yaml.safe_dump_all(manifests, f, allow_unicode=True, sort_keys=False)
    return str(path)


def load_manifest(path: str) -> list[dict]:
    with Path(path).open('r', encoding='utf-8') as f:
        return [doc for doc in yaml.safe_load_all(f) if doc]


def validate_manifest(path: str, settings: Settings | None = None) -> dict:
    docs = load_manifest(path)
    kinds = [doc.get('kind') for doc in docs]
    missing = sorted(desired_manifest_kinds(settings) - set(kinds))
    missing_security: list[str] = []
    for doc in docs:
        if doc.get('kind') != 'Deployment':
            continue
        pod_spec = doc.get('spec', {}).get('template', {}).get('spec', {})
        pod_security = pod_spec.get('securityContext', {})
        containers = pod_spec.get('containers', [])
        container_security = containers[0].get('securityContext', {}) if containers else {}
        if pod_spec.get('automountServiceAccountToken') is not False:
            missing_security.append('Deployment.spec.template.spec.automountServiceAccountToken=false')
        if pod_security.get('runAsNonRoot') is not True:
            missing_security.append('Deployment.spec.template.spec.securityContext.runAsNonRoot=true')
        if pod_security.get('seccompProfile', {}).get('type') != 'RuntimeDefault':
            missing_security.append('Deployment.spec.template.spec.securityContext.seccompProfile.type=RuntimeDefault')
        if container_security.get('allowPrivilegeEscalation') is not False:
            missing_security.append('Deployment container securityContext.allowPrivilegeEscalation=false')
        if 'ALL' not in container_security.get('capabilities', {}).get('drop', []):
            missing_security.append('Deployment container securityContext.capabilities.drop includes ALL')
    return {'ok': not missing and not missing_security, 'kinds': kinds, 'missing': missing, 'missing_security': missing_security, 'count': len(docs)}


def _mock_state_path(settings: Settings, slug: str) -> Path:
    out_dir = Path(settings.mock_runtime_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f'{slug}.json'


def write_mock_runtime_state(settings: Settings, *, slug: str, namespace: str, endpoint: str, status: str, manifest_path: str, extra: dict | None = None) -> dict:
    manifest_info = validate_manifest(manifest_path, settings)
    state = {
        'slug': slug,
        'namespace': namespace,
        'endpoint': endpoint,
        'status': status,
        'manifest_path': manifest_path,
        'manifest': manifest_info,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'mode': settings.k8s_apply_mode,
    }
    if extra:
        state.update(extra)
    path = _mock_state_path(settings, slug)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    return state


def read_mock_runtime_state(settings: Settings, slug: str) -> dict | None:
    path = _mock_state_path(settings, slug)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def delete_mock_runtime_state(settings: Settings, slug: str) -> dict:
    path = _mock_state_path(settings, slug)
    existed = path.exists()
    if existed:
        path.unlink()
    return {'deleted': existed, 'path': str(path)}


def should_mock(settings: Settings, force_dry_run: bool | None = None) -> bool:
    # Explicit dry-run always wins.
    if force_dry_run is True:
        return True
    from app.services.safety import real_external_enabled

    if not real_external_enabled(settings, 'k8s'):
        return True
    return False


def _kubectl_base(settings: Settings) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    if settings.kubeconfig_path:
        env['KUBECONFIG'] = settings.kubeconfig_path
    cmd = ['kubectl']
    if settings.k8s_context:
        cmd.extend(['--context', settings.k8s_context])
    return cmd, env


def _run_kubectl(settings: Settings, args: list[str], *, timeout: int | None = None) -> tuple[bool, str, dict]:
    cmd, env = _kubectl_base(settings)
    full_cmd = cmd + args
    proc = subprocess.run(
        full_cmd,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout or settings.kubectl_timeout_seconds,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output, {'cmd': full_cmd, 'returncode': proc.returncode}


def kubectl_apply(settings: Settings, manifest_path: str, *, force_dry_run: bool | None = None) -> tuple[bool, str, dict | None]:
    validation = validate_manifest(manifest_path, settings)
    if not validation['ok']:
        return False, f'manifest validation failed: missing {validation["missing"]}', {'validation': validation}

    if should_mock(settings, force_dry_run):
        return True, '[mock] kubectl apply skipped; manifest validated and mock runtime state should be written by service layer', {'validation': validation, 'mode': settings.k8s_apply_mode}

    messages: list[str] = []
    details: dict[str, object] = {'validation': validation, 'mode': 'real'}
    if settings.k8s_server_dry_run_first:
        dry_ok, dry_output, dry_meta = _run_kubectl(settings, ['apply', '--dry-run=server', '-f', manifest_path])
        messages.append(dry_output)
        details['server_dry_run'] = dry_meta | {'ok': dry_ok}
        if not dry_ok:
            return False, '\n'.join(x for x in messages if x), details
    apply_ok, apply_output, apply_meta = _run_kubectl(settings, ['apply', '-f', manifest_path])
    messages.append(apply_output)
    details['apply'] = apply_meta | {'ok': apply_ok}
    return apply_ok, '\n'.join(x for x in messages if x), details


def kubectl_wait_ready(settings: Settings, *, namespace: str, deployment: str, replicas: int, force_dry_run: bool | None = None) -> tuple[bool, str, dict]:
    if should_mock(settings, force_dry_run):
        return True, f'[mock] deployment/{deployment} in namespace/{namespace} readyReplicas={replicas}', {
            'namespace': namespace, 'deployment': deployment, 'replicas': replicas, 'readyReplicas': replicas, 'mode': settings.k8s_apply_mode
        }
    timeout_seconds = settings.k8s_rollout_timeout_seconds
    ok, output, meta = _run_kubectl(
        settings,
        ['rollout', 'status', f'deployment/{deployment}', '-n', namespace, f'--timeout={timeout_seconds}s'],
        timeout=timeout_seconds + 30,
    )
    return ok, output, {'namespace': namespace, 'deployment': deployment, 'mode': 'real', **meta}


def kubectl_get_resources(settings: Settings, *, namespace: str, slug: str, force_dry_run: bool | None = None) -> tuple[bool, str, dict]:
    if should_mock(settings, force_dry_run):
        return True, '[mock] kubectl get resources skipped', {'namespace': namespace, 'slug': slug, 'mode': settings.k8s_apply_mode}
    selector = f'app=newapi-{slug}'
    ok, output, meta = _run_kubectl(settings, ['get', 'deployment,service,ingress,pods', '-n', namespace, '-l', selector, '-o', 'json'])
    parsed = None
    if ok:
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = None
    return ok, output, {'namespace': namespace, 'slug': slug, 'selector': selector, 'mode': 'real', 'resources': parsed, **meta}


def kubectl_delete(settings: Settings, manifest_path: str, *, force_dry_run: bool | None = None) -> tuple[bool, str, dict | None]:
    validation = validate_manifest(manifest_path, settings)
    if should_mock(settings, force_dry_run):
        return True, '[mock] kubectl delete skipped; mock runtime state removed by service layer', {'validation': validation, 'mode': settings.k8s_apply_mode}
    ok, output, meta = _run_kubectl(settings, ['delete', '-f', manifest_path, '--ignore-not-found=true'])
    return ok, output, {'validation': validation, 'mode': 'real', **meta}
