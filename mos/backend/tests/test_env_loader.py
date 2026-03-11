from __future__ import annotations

import os
from pathlib import Path

from app.env_loader import iter_backend_env_files, load_backend_env_files


def test_iter_backend_env_files_prioritizes_backend_env() -> None:
    backend_root = Path("/tmp/repo/mos/backend")

    assert iter_backend_env_files(backend_root) == (
        backend_root / ".env",
        Path("/tmp/repo/.env.local.consolidated"),
        Path("/tmp/repo/.env"),
    )


def test_load_backend_env_files_prefers_backend_env_over_repo_consolidated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    backend_root = project_root / "mos" / "backend"
    backend_root.mkdir(parents=True)

    (project_root / ".env.local.consolidated").write_text("GEMINI_API_KEY=repo-key\n", encoding="utf-8")
    (project_root / ".env").write_text("GEMINI_API_KEY=root-key\n", encoding="utf-8")
    (backend_root / ".env").write_text("GEMINI_API_KEY=backend-key\n", encoding="utf-8")

    original = os.getenv("GEMINI_API_KEY")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    try:
        load_backend_env_files(backend_root)
        assert os.getenv("GEMINI_API_KEY") == "backend-key"
    finally:
        if original is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = original


def test_load_backend_env_files_keeps_process_env_authoritative(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    backend_root = project_root / "mos" / "backend"
    backend_root.mkdir(parents=True)

    (project_root / ".env.local.consolidated").write_text("GEMINI_API_KEY=repo-key\n", encoding="utf-8")
    (backend_root / ".env").write_text("GEMINI_API_KEY=backend-key\n", encoding="utf-8")

    original = os.getenv("GEMINI_API_KEY")
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")

    try:
        load_backend_env_files(backend_root)
        assert os.getenv("GEMINI_API_KEY") == "process-key"
    finally:
        if original is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = original
