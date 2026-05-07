from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterator


class DeployLockConflict(RuntimeError):
    pass


_ACTIVE_LOCK_KEYS: ContextVar[frozenset[str]] = ContextVar(
    "deploy_active_lock_keys",
    default=frozenset(),
)
_DEFAULT_STALE_AFTER = timedelta(hours=6)


@dataclass(frozen=True)
class DeployLockHandle:
    key: str
    path: Path
    metadata: dict[str, Any]
    reentrant: bool = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_lock_component(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:80] or "unnamed"


def _lock_key(*, plan_path: str, workload_name: str) -> str:
    plan = str(Path(plan_path).expanduser().resolve())
    workload = (workload_name or "").strip() or "*"
    import hashlib

    digest = hashlib.sha256(f"{plan}\n{workload}".encode("utf-8")).hexdigest()[:24]
    return f"{_safe_lock_component(workload)}-{digest}"


def _metadata_path(lock_path: Path) -> Path:
    return lock_path / "metadata.json"


def _read_existing_metadata(lock_path: Path) -> dict[str, Any]:
    path = _metadata_path(lock_path)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _format_conflict_message(
    *,
    plan_path: str,
    workload_name: str,
    lock_path: Path,
    metadata: dict[str, Any],
    stale_after: timedelta,
) -> str:
    acquired_at = _parse_timestamp(metadata.get("acquiredAt"))
    stale_suffix = ""
    if acquired_at and datetime.now(timezone.utc) - acquired_at > stale_after:
        stale_suffix = (
            " The lock appears stale; an operator must inspect and remove it explicitly "
            "before retrying."
        )
    owner = str(metadata.get("jobId") or metadata.get("userId") or "unknown").strip()
    return (
        "Deploy lock is already held "
        f"for workload '{workload_name or '*'}' in plan '{plan_path}'. "
        f"owner={owner}; lockPath={lock_path}.{stale_suffix}"
    )


@contextmanager
def acquire_deploy_lock(
    *,
    lock_root: Path,
    plan_path: str,
    workload_name: str,
    job_id: str | None,
    org_id: str | None,
    user_id: str | None,
    stale_after: timedelta = _DEFAULT_STALE_AFTER,
) -> Iterator[DeployLockHandle]:
    root = lock_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = _lock_key(plan_path=plan_path, workload_name=workload_name)
    active_keys = _ACTIVE_LOCK_KEYS.get()
    lock_path = root / f"{key}.lock"
    metadata = {
        "lockVersion": 1,
        "planPath": str(Path(plan_path).expanduser().resolve()),
        "workloadName": (workload_name or "").strip() or "*",
        "jobId": (job_id or "").strip() or None,
        "orgId": (org_id or "").strip() or None,
        "userId": (user_id or "").strip() or None,
        "acquiredAt": _utc_now_iso(),
        "process": "mos-backend",
        "pid": os.getpid(),
    }

    if key in active_keys:
        yield DeployLockHandle(key=key, path=lock_path, metadata=metadata, reentrant=True)
        return

    try:
        lock_path.mkdir(mode=0o700)
    except FileExistsError as exc:
        existing_metadata = _read_existing_metadata(lock_path)
        raise DeployLockConflict(
            _format_conflict_message(
                plan_path=plan_path,
                workload_name=workload_name,
                lock_path=lock_path,
                metadata=existing_metadata,
                stale_after=stale_after,
            )
        ) from exc

    token = _ACTIVE_LOCK_KEYS.set(active_keys | {key})
    try:
        _metadata_path(lock_path).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        yield DeployLockHandle(key=key, path=lock_path, metadata=metadata)
    finally:
        _ACTIVE_LOCK_KEYS.reset(token)
        shutil.rmtree(lock_path, ignore_errors=True)
