from app.core.config import Settings
from app.services.k8s_renderer import render_newapi_manifests, validate_manifest, write_manifest


def _deployment(docs: list[dict]) -> dict:
    return next(doc for doc in docs if doc['kind'] == 'Deployment')


def _ingress(docs: list[dict]) -> dict:
    return next(doc for doc in docs if doc['kind'] == 'Ingress')


def _render(settings: Settings | None = None) -> list[dict]:
    return render_newapi_manifests(
        settings or Settings(k8s_tls_secret_name=''),
        slug='secure-demo',
        domain='secure-demo.example.com',
        admin_username='admin',
        admin_password='ChangeMe123!',
    )


def test_deployment_manifest_defaults_to_restricted_podsecurity(tmp_path):
    settings = Settings(k8s_tls_secret_name='', manifest_output_dir=str(tmp_path))
    docs = _render(settings)
    deployment = _deployment(docs)
    pod_spec = deployment['spec']['template']['spec']
    pod_security = pod_spec['securityContext']
    container_security = pod_spec['containers'][0]['securityContext']

    assert pod_spec['automountServiceAccountToken'] is False
    assert pod_security['runAsNonRoot'] is True
    assert pod_security['seccompProfile']['type'] == 'RuntimeDefault'
    assert 'runAsUser' not in pod_security
    assert 'runAsGroup' not in pod_security
    assert 'fsGroup' not in pod_security
    assert container_security['allowPrivilegeEscalation'] is False
    assert 'ALL' in container_security['capabilities']['drop']

    manifest_path = write_manifest(settings, 'secure-demo', docs)
    validation = validate_manifest(manifest_path, settings)
    assert validation['ok'] is True
    assert validation['missing_security'] == []


def test_deployment_manifest_renders_optional_pod_identity_fields():
    docs = _render(
        Settings(
            k8s_tls_secret_name='',
            k8s_pod_run_as_user='1000',
            k8s_pod_run_as_group='1000',
            k8s_pod_fs_group='1000',
        )
    )
    pod_security = _deployment(docs)['spec']['template']['spec']['securityContext']

    assert pod_security['runAsUser'] == 1000
    assert pod_security['runAsGroup'] == 1000
    assert pod_security['fsGroup'] == 1000


def test_deployment_manifest_rejects_non_integer_optional_pod_identity_fields():
    settings = Settings(k8s_pod_run_as_user='not-an-int')

    try:
        _render(settings)
    except ValueError as exc:
        assert 'K8S_POD_RUN_AS_USER must be an integer when set' in str(exc)
    else:
        raise AssertionError('non-integer K8S_POD_RUN_AS_USER should fail manifest rendering')


def test_empty_tls_secret_still_omits_ingress_tls_with_security_context():
    docs = _render(Settings(k8s_tls_secret_name=''))

    assert 'tls' not in _ingress(docs)['spec']
