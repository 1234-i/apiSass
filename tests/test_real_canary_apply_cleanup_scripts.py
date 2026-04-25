from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "real_k8s_canary_apply_and_cleanup.sh"
STATIC_CHECK = ROOT / "scripts" / "real_k8s_canary_apply_cleanup_static_check.sh"
CONFIRM_WORD = "I_UNDERSTAND_THIS_WILL_CREATE_K8S_RESOURCES_AND_THEN_CLEAN_THEM_UP"


def run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [*args],
        cwd=ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_apply_cleanup_requires_confirmation_before_env_or_kubectl(tmp_path):
    result = run_script(
        "bash",
        str(SCRIPT),
        env={"ENV_FILE": str(tmp_path / ".env.real-canary")},
    )

    assert result.returncode == 2
    assert "Refusing to run Real Canary 0 Step 3 apply-and-cleanup" in result.stderr
    assert CONFIRM_WORD in result.stderr
    assert "missing" not in result.stderr


def test_apply_cleanup_script_contains_guardrails_without_legacy_flows():
    text = SCRIPT.read_text(encoding="utf-8")

    assert CONFIRM_WORD in text
    assert "trap cleanup_on_exit EXIT" in text
    assert "/deploy" in text
    assert "/provision" not in text
    assert "delete -f" in text
    assert "--ignore-not-found=true" in text
    assert "NEWAPI_MOCK" in text
    assert "SUB2API_MOCK" in text
    assert "CLOUDFLARE_MOCK" in text
    assert "K8S_CANARY_MODE" in text
    assert "require_non_placeholder NEWAPI_SQL_DSN_TEMPLATE" in text
    assert "require_non_placeholder NEWAPI_REDIS_CONN_TEMPLATE" in text
    assert "CANARY_SELECTOR" in text
    assert "real_k8s_canary_open.sh" not in text
    assert "real_k8s_canary_cleanup.sh" not in text


def test_apply_cleanup_script_does_not_echo_secret_values():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "must be a real test value" in text
    assert "got ${NEWAPI_SQL_DSN_TEMPLATE" not in text
    assert "got ${NEWAPI_REDIS_CONN_TEMPLATE" not in text
    assert "looks like a placeholder: $" not in text
    assert "echo \"$API_KEY" not in text


def test_apply_cleanup_static_check_passes_without_creating_resources():
    result = run_script("bash", str(STATIC_CHECK))

    assert result.returncode == 0, result.stderr
    assert "apply cleanup static checks passed without creating resources" in result.stdout
