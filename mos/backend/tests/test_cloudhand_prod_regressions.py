from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import cloudhand.secrets as secrets_module
from cloudhand.core.apply import _resolve_provider_credential_env
from cloudhand.models import ApplicationSpec
from cloudhand.secrets import _resolve_local_keys_dir


def _moshq_git_app_payload() -> dict:
    return {
        "name": "mos-ui",
        "source_type": "git",
        "repo_url": "https://github.com/example/repo",
        "branch": "main",
        "runtime": "nodejs",
        "build_config": {
            "install_command": "npm ci",
            "build_command": "npm run build",
            "system_packages": [],
        },
        "service_config": {
            "command": "npm run preview -- --host 0.0.0.0 --port 5173 --strictPort",
            "environment": {},
            "ports": [5173],
            "server_names": ["moshq.app"],
            "https": True,
        },
        "destination_path": "/opt/apps",
    }


def test_moshq_git_workload_rejects_python_http_server() -> None:
    payload = _moshq_git_app_payload()
    payload["runtime"] = "python"
    payload["service_config"]["command"] = "python3 -m http.server 5173 --directory dist --bind 0.0.0.0"

    with pytest.raises(
        ValidationError,
        match=r"moshq\.app workloads may not use Python's built-in static file server",
    ):
        ApplicationSpec.model_validate(payload)


def test_git_static_site_allows_spa_fallback_without_command() -> None:
    payload = _moshq_git_app_payload()
    payload["service_config"]["command"] = None
    payload["service_config"]["static_root"] = "mos/frontend/dist"
    payload["service_config"]["spa_fallback"] = True

    app = ApplicationSpec.model_validate(payload)

    assert app.service_config.command is None
    assert app.service_config.static_root == "mos/frontend/dist"
    assert app.service_config.spa_fallback is True


def test_git_static_site_requires_build_command() -> None:
    payload = _moshq_git_app_payload()
    payload["build_config"]["build_command"] = None
    payload["service_config"]["command"] = None
    payload["service_config"]["static_root"] = "mos/frontend/dist"
    payload["service_config"]["spa_fallback"] = True

    with pytest.raises(
        ValidationError,
        match=r"build_config\.build_command is required when service_config\.static_root is configured",
    ):
        ApplicationSpec.model_validate(payload)


def test_git_static_site_rejects_command_when_static_root_is_configured() -> None:
    payload = _moshq_git_app_payload()
    payload["service_config"]["static_root"] = "mos/frontend/dist"
    payload["service_config"]["spa_fallback"] = True

    with pytest.raises(
        ValidationError,
        match=r"service_config\.command must be omitted when service_config\.static_root is configured",
    ):
        ApplicationSpec.model_validate(payload)


def test_moshq_git_workload_requires_rebuild_commands() -> None:
    payload = _moshq_git_app_payload()
    payload["build_config"]["install_command"] = None
    payload["build_config"]["build_command"] = None

    with pytest.raises(
        ValidationError,
        match=r"moshq\.app workloads must set build_config\.install_command",
    ):
        ApplicationSpec.model_validate(payload)


def test_resolve_provider_credential_env_uses_cloudhand_secrets_file(tmp_path: Path) -> None:
    root = tmp_path
    cloudhand_dir = root / "cloudhand"
    cloudhand_dir.mkdir()
    (cloudhand_dir / "secrets.json").write_text(
        json.dumps({"providers": {"hetzner": {"token": "token-from-secrets"}}}),
        encoding="utf-8",
    )

    env: dict[str, str] = {}
    _resolve_provider_credential_env(root=root, provider="hetzner", env=env)

    assert env["TF_VAR_hcloud_token"] == "token-from-secrets"


def test_resolve_provider_credential_env_errors_cleanly_when_token_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("HCLOUD_TOKEN", raising=False)
    monkeypatch.delenv("TF_VAR_hcloud_token", raising=False)
    env: dict[str, str] = {}

    with pytest.raises(
        ValueError,
        match=r"Missing Hetzner provider token",
    ):
        _resolve_provider_credential_env(root=tmp_path, provider="hetzner", env=env)


def test_resolve_local_keys_dir_prefers_existing_shared_project_keypair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    shared_dir = tmp_path / "shared-keys"
    shared_dir.mkdir()
    (shared_dir / "mos_id_rsa").write_text("private", encoding="utf-8")
    (shared_dir / "mos_id_rsa.pub").write_text("public\n", encoding="utf-8")

    home_dir = tmp_path / "home"
    monkeypatch.delenv("CLOUDHAND_KEYS_DIR", raising=False)
    monkeypatch.setattr(secrets_module, "_SHARED_KEYS_DIR", shared_dir)
    monkeypatch.setattr(secrets_module.Path, "home", staticmethod(lambda: home_dir))

    assert _resolve_local_keys_dir("mos") == shared_dir
