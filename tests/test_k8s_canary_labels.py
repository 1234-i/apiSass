from __future__ import annotations

from app.core.config import Settings
from app.services.k8s_renderer import render_newapi_manifests


SLUG = "canary-label-demo"


def _render(canary_mode: bool) -> list[dict]:
    return render_newapi_manifests(
        Settings(
            k8s_tls_secret_name="",
            k8s_namespace_mode="fixed",
            k8s_target_namespace="ns-test",
            k8s_create_namespace=False,
            k8s_canary_mode=canary_mode,
            k8s_canary_max_lifetime_seconds=600,
        ),
        slug=SLUG,
        domain=f"{SLUG}.example.com",
        admin_username="admin",
        admin_password="ChangeMe123!",
    )


def _doc(docs: list[dict], kind: str) -> dict:
    return next(doc for doc in docs if doc["kind"] == kind)


def test_canary_mode_keeps_existing_app_selector_labels_stable():
    docs = _render(canary_mode=True)
    deployment = _doc(docs, "Deployment")
    service = _doc(docs, "Service")

    assert deployment["spec"]["selector"]["matchLabels"]["app"] == f"newapi-{SLUG}"
    assert service["spec"]["selector"]["app"] == f"newapi-{SLUG}"
    assert deployment["spec"]["template"]["metadata"]["labels"]["app"] == f"newapi-{SLUG}"


def test_canary_mode_excludes_canary_labels_from_selectors():
    docs = _render(canary_mode=True)
    deployment_selector = _doc(docs, "Deployment")["spec"]["selector"]["matchLabels"]
    service_selector = _doc(docs, "Service")["spec"]["selector"]

    assert "api-saas.weisoft.chat/canary" not in deployment_selector
    assert "api-saas.weisoft.chat/tenant-slug" not in deployment_selector
    assert "api-saas.weisoft.chat/canary" not in service_selector
    assert "api-saas.weisoft.chat/tenant-slug" not in service_selector


def test_canary_mode_adds_labels_to_runtime_resource_metadata():
    docs = _render(canary_mode=True)

    for kind in ("Secret", "Deployment", "Service", "Ingress", "HorizontalPodAutoscaler"):
        labels = _doc(docs, kind)["metadata"]["labels"]
        assert labels["api-saas.weisoft.chat/canary"] == "true"
        assert labels["api-saas.weisoft.chat/tenant-slug"] == SLUG


def test_canary_mode_adds_ttl_annotations_to_runtime_resource_metadata():
    docs = _render(canary_mode=True)

    for kind in ("Secret", "Deployment", "Service", "Ingress", "HorizontalPodAutoscaler"):
        annotations = _doc(docs, kind)["metadata"]["annotations"]
        assert "api-saas.weisoft.chat/canary-created-at" in annotations
        assert annotations["api-saas.weisoft.chat/canary-max-lifetime-seconds"] == "600"


def test_canary_mode_false_omits_canary_label():
    docs = _render(canary_mode=False)

    for kind in ("Secret", "Deployment", "Service", "Ingress", "HorizontalPodAutoscaler"):
        labels = _doc(docs, kind)["metadata"]["labels"]
        assert "api-saas.weisoft.chat/canary" not in labels
        assert "api-saas.weisoft.chat/tenant-slug" not in labels
