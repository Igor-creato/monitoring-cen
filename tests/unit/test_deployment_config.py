from pathlib import Path


def test_dockerfiles_copy_backend_before_installing_local_package() -> None:
    for dockerfile in (Path("docker/backend.Dockerfile"), Path("docker/worker.Dockerfile")):
        lines = dockerfile.read_text(encoding="utf-8").splitlines()
        backend_copy_index = lines.index("COPY backend /app/backend")
        install_index = lines.index("RUN pip install --upgrade pip && pip install /app")

        assert backend_copy_index < install_index


def test_sarif_upload_steps_skip_missing_scan_outputs() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "hashFiles('trivy-api.sarif') != ''" in workflow
    assert "hashFiles('trivy-worker.sarif') != ''" in workflow


def test_ssh_deploy_script_uses_supported_failure_handling() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "script_stop:" not in workflow
    assert "script: |\n            set -e" in workflow


def test_smoke_retries_public_endpoints_after_container_recreate() -> None:
    smoke = Path("scripts/smoke.sh").read_text(encoding="utf-8")

    assert "SMOKE_RETRIES" in smoke
    assert "until [ \"$attempt\" -ge \"$SMOKE_RETRIES\" ]" in smoke
