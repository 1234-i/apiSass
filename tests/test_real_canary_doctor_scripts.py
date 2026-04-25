from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


def test_check_env_files_accepts_specific_missing_file(tmp_path):
    missing = tmp_path / ".env.real-canary"
    result = run_script("bash", "./scripts/check_env_files.sh", str(missing))
    assert result.returncode == 0
    assert "missing; skipped" in result.stdout


def test_check_env_files_rejects_inline_comment_export_and_duplicate(tmp_path):
    env_file = tmp_path / "bad.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_NAME=demo # inline comment",
                "export APPLY_K8S=true",
                "APPLY_K8S=true",
                "APPLY_K8S=false",
                "BROKEN LINE",
            ]
        ),
        encoding="utf-8",
    )
    result = run_script("bash", "./scripts/check_env_files.sh", str(env_file))
    assert result.returncode == 1
    assert "inline comments are not allowed" in result.stderr
    assert "export is not allowed" in result.stderr
    assert "duplicate key" in result.stderr
    assert "invalid env line" in result.stderr


def test_real_k8s_canary_doctor_missing_inputs_is_non_failing(tmp_path):
    result = run_script(
        "bash",
        "./scripts/real_k8s_canary_doctor.sh",
        env={
            "ENV_FILE": str(tmp_path / ".env.real-canary"),
            "REAL_KUBECONFIG_HOST_PATH": str(tmp_path / "real-kubeconfig/sealos-canary.yaml"),
        },
    )
    assert result.returncode == 0
    assert "real_k8s_canary_doctor_status=not_configured" in result.stdout
    assert "safe_to_run_real_preflight=false" in result.stdout
    assert "will_call_k8s_api=false" in result.stdout


def test_real_k8s_canary_doctor_strict_missing_inputs_fails(tmp_path):
    result = run_script(
        "bash",
        "./scripts/real_k8s_canary_doctor.sh",
        "--strict",
        env={
            "ENV_FILE": str(tmp_path / ".env.real-canary"),
            "REAL_KUBECONFIG_HOST_PATH": str(tmp_path / "real-kubeconfig/sealos-canary.yaml"),
        },
    )
    assert result.returncode == 1
    assert "real_k8s_canary_doctor_status=not_configured" in result.stdout
