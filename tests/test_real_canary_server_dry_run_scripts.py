from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "real_k8s_canary_server_dry_run.sh"
STATIC_CHECK = ROOT / "scripts" / "real_k8s_canary_server_dry_run_static_check.sh"
CONFIRM_WORD = "I_UNDERSTAND_THIS_WILL_QUERY_K8S_API_WITH_SERVER_DRY_RUN_BUT_NOT_CREATE_RESOURCES"


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


def test_server_dry_run_requires_confirmation_before_env_or_kubectl(tmp_path):
    result = run_script(
        "bash",
        str(SCRIPT),
        env={"ENV_FILE": str(tmp_path / ".env.real-canary")},
    )
    assert result.returncode == 2
    assert "Refusing to run Real Canary 0 Step 2 server-side dry-run" in result.stderr
    assert CONFIRM_WORD in result.stderr
    assert "missing" not in result.stderr


def test_server_dry_run_script_contains_confirmation_and_server_dry_run_only():
    text = SCRIPT.read_text(encoding="utf-8")
    assert CONFIRM_WORD in text
    assert "--dry-run=server" in text
    assert "kubectl delete" not in text
    assert "real_k8s_canary_open.sh" not in text
    assert "real_k8s_canary_cleanup.sh" not in text
    assert "/provision" not in text
    assert "/deploy" not in text
    assert "dry_run=false" not in text


def test_server_dry_run_static_check_passes_without_calling_kubectl():
    result = run_script("bash", str(STATIC_CHECK))
    assert result.returncode == 0, result.stderr
    assert "server dry-run static checks passed without calling kubectl" in result.stdout
