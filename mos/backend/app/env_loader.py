from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def iter_backend_env_files(backend_root: Path) -> tuple[Path, Path, Path]:
    project_root = backend_root.parent.parent
    return (
        backend_root / ".env",
        project_root / ".env.local.consolidated",
        project_root / ".env",
    )


def load_backend_env_files(backend_root: Path) -> tuple[Path, Path, Path]:
    env_files = iter_backend_env_files(backend_root)
    for path in env_files:
        if path.exists():
            load_dotenv(path, override=False)
    return env_files
