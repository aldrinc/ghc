from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from typing import Any, Optional
from uuid import UUID, uuid4

import httpx

from app.config import settings
from app.services import namecheap_dns as namecheap_dns_service


class DeployError(RuntimeError):
    pass


_DEPLOY_JOB_LOG_TAIL_CHARS = 12000
_ORG_SCOPED_PORT_RANGE_START = 20000
_ORG_SCOPED_PORT_RANGE_END = 29999
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")
_ARTIFACT_ASSET_PUBLIC_ID_KEYS = {
    "assetPublicId",
    "thumbAssetPublicId",
    "posterAssetPublicId",
    "iconAssetPublicId",
    "swatchAssetPublicId",
}
_DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES = int(
    os.getenv("DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES", str(150 * 1024 * 1024))
)
_DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION = int(
    os.getenv("DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION", "1600")
)
_DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY = int(
    os.getenv("DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY", "80")
)
_PUBLIC_ASSET_URL_PREFIXES = (
    "/public/assets/",
    "public/assets/",
    "/api/public/assets/",
    "api/public/assets/",
)


def _find_repo_root(start: Path) -> Path:
    """
    Locate the ghc repo root by walking upwards from `start`.

    We intentionally do not assume cwd is the repo root (in production we `cd mos/backend`).
    """
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "mos" / "backend").is_dir() and (candidate / "mos" / "frontend").is_dir():
            return candidate
    raise DeployError(
        "Unable to locate repo root (expected to find mos/backend and mos/frontend). "
        "Run the server from inside the repo or set DEPLOY_ROOT_DIR to an absolute path."
    )


def _cloudhand_dir() -> Path:
    """
    Runtime directory for plans + Terraform state.

    NOTE: This is intentionally NOT the Python package `cloudhand/` under mos/backend/.
    """
    raw = Path(settings.DEPLOY_ROOT_DIR)
    if raw.is_absolute():
        return raw
    repo_root = _find_repo_root(Path.cwd())
    return (repo_root / raw).resolve()


def _terraform_dir() -> Path:
    return _cloudhand_dir() / "terraform"


def _resolve_terraform_bin() -> str:
    tf_bin = shutil.which("terraform")
    if not tf_bin:
        raise DeployError("Terraform binary 'terraform' not found in PATH. Install Terraform on the MOS API host.")
    return tf_bin


def _find_latest_plan() -> Optional[Path]:
    ch_dir = _cloudhand_dir()
    if not ch_dir.exists():
        return None
    plans = sorted(
        (
            path
            for path in ch_dir.glob("plan-*.json")
            if not path.name.startswith("plan-apply-")
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return plans[0] if plans else None


def _assert_under_cloudhand(path: Path) -> Path:
    ch_dir = _cloudhand_dir().resolve()
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(ch_dir):
        raise DeployError("plan_path must be inside the deploy plan directory (DEPLOY_ROOT_DIR).")
    return resolved


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jobs_dir() -> Path:
    return _cloudhand_dir() / "jobs"


def _job_path(job_id: str) -> Path:
    safe = (job_id or "").strip()
    if not safe:
        raise DeployError("job_id is required.")
    if "/" in safe or "\\" in safe:
        raise DeployError("job_id is invalid.")
    return _jobs_dir() / f"{safe}.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _read_job(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.exists():
        raise DeployError(f"Deploy job '{job_id}' not found.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read deploy job '{job_id}': {exc}") from exc
    if not isinstance(raw, dict):
        raise DeployError(f"Deploy job '{job_id}' is invalid.")
    return raw


def _publish_jobs_dir() -> Path:
    return _cloudhand_dir() / "publish-jobs"


def _publish_job_path(job_id: str) -> Path:
    safe = (job_id or "").strip()
    if not safe:
        raise DeployError("job_id is required.")
    if "/" in safe or "\\" in safe:
        raise DeployError("job_id is invalid.")
    return _publish_jobs_dir() / f"{safe}.json"


def _read_publish_job(job_id: str) -> dict[str, Any]:
    path = _publish_job_path(job_id)
    if not path.exists():
        raise DeployError(f"Publish job '{job_id}' not found.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read publish job '{job_id}': {exc}") from exc
    if not isinstance(raw, dict):
        raise DeployError(f"Publish job '{job_id}' is invalid.")
    return raw


def get_latest_plan() -> dict[str, str]:
    plan_path = _find_latest_plan()
    if not plan_path:
        raise DeployError("No plan found.")
    try:
        content = plan_path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"Failed to read plan: {exc}") from exc
    return {"path": str(plan_path), "content": content}


def get_workload_domains_from_plan(
    *,
    workload_name: str,
    plan_path: str | None = None,
    instance_name: str | None = None,
) -> dict[str, Any]:
    name = (workload_name or "").strip()
    if not name:
        raise DeployError("workload_name is required.")

    base_plan_path = _assert_under_cloudhand(Path(plan_path)) if plan_path else _find_latest_plan()
    if not base_plan_path or not base_plan_path.exists():
        raise DeployError("No plan found.")

    try:
        plan = json.loads(base_plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec") or {}
    instances = new_spec.get("instances") or []
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    found = False
    server_names: list[str] = []
    https: bool | None = None

    for inst in instances:
        if instance_name and inst.get("name") != instance_name:
            continue
        workloads = inst.get("workloads") or []
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if (workload.get("name") or "").strip() != name:
                continue
            found = True

            service_config = workload.get("service_config") or {}
            if not isinstance(service_config, dict):
                break

            raw_server_names = service_config.get("server_names") or []
            if raw_server_names is None:
                raw_server_names = []
            if not isinstance(raw_server_names, list):
                raise DeployError("Workload service_config.server_names must be a list.")

            cleaned: list[str] = []
            seen: set[str] = set()
            for raw in raw_server_names:
                if not isinstance(raw, str):
                    raise DeployError("Workload service_config.server_names entries must be strings.")
                hostname = raw.strip()
                if not hostname:
                    continue
                if hostname in seen:
                    continue
                seen.add(hostname)
                cleaned.append(hostname)
            server_names = cleaned

            https_value = service_config.get("https")
            if isinstance(https_value, bool):
                https = https_value

            break
        if found:
            break

    return {
        "plan_path": str(base_plan_path),
        "workload_found": found,
        "server_names": server_names,
        "https": https,
    }


def save_plan(*, content: str, path: str | None = None) -> dict[str, str]:
    # Validate JSON early
    try:
        json.loads(content)
    except Exception as exc:
        raise DeployError(f"Plan content is not valid JSON: {exc}") from exc

    ch_dir = _cloudhand_dir()
    ch_dir.mkdir(parents=True, exist_ok=True)

    if path:
        plan_path = _assert_under_cloudhand(Path(path))
    else:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
        plan_path = ch_dir / f"plan-{ts}.json"

    try:
        plan_path.write_text(content, encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"Failed to write plan: {exc}") from exc

    return {"path": str(plan_path)}


def _deep_merge(dst: Any, patch: Any) -> Any:
    """
    Recursive merge for dict patches.

    - dict + dict => merge keys recursively
    - all other types (including lists) => patch overwrites dst
    """
    if isinstance(dst, dict) and isinstance(patch, dict):
        out = dict(dst)
        for k, v in patch.items():
            out[k] = _deep_merge(out.get(k), v)
        return out
    return patch


def _coerce_service_port(*, raw_port: Any, context: str) -> int:
    try:
        port = int(raw_port)
    except Exception as exc:
        raise DeployError(f"{context} port '{raw_port}' is invalid.") from exc
    if port < 1 or port > 65535:
        raise DeployError(f"{context} port {port} is out of range (1-65535).")
    return port


def _extract_primary_service_port(*, workload: dict[str, Any], context: str) -> int | None:
    service_config = workload.get("service_config")
    if service_config is None:
        return None
    if not isinstance(service_config, dict):
        raise DeployError(f"{context} service_config must be an object.")
    ports = service_config.get("ports")
    if ports is None:
        return None
    if not isinstance(ports, list):
        raise DeployError(f"{context} service_config.ports must be a list.")
    if not ports:
        return None
    return _coerce_service_port(raw_port=ports[0], context=f"{context} service_config")


def _extract_workload_server_names(*, workload: dict[str, Any], context: str) -> list[str]:
    service_config = workload.get("service_config")
    if not isinstance(service_config, dict):
        raise DeployError(f"{context} service_config must be an object.")
    raw_server_names = service_config.get("server_names")
    if raw_server_names is None:
        return []
    if not isinstance(raw_server_names, list):
        raise DeployError(f"{context} service_config.server_names must be a list.")
    server_names: list[str] = []
    for idx, value in enumerate(raw_server_names):
        if not isinstance(value, str):
            raise DeployError(f"{context} service_config.server_names[{idx}] must be a string.")
        hostname = value.strip()
        if hostname:
            server_names.append(hostname)
    return server_names


def _collect_used_instance_ports(*, plan: dict[str, Any], instance_name: str | None) -> set[int]:
    new_spec = plan.get("new_spec")
    if not isinstance(new_spec, dict):
        raise DeployError("Plan new_spec must be an object.")
    instances = new_spec.get("instances")
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    target_instance_name = (instance_name or "").strip()
    used_ports: set[int] = set()
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        current_instance_name = str(inst.get("name") or "").strip()
        if target_instance_name and current_instance_name != target_instance_name:
            continue
        workloads = inst.get("workloads")
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            service_config = workload.get("service_config")
            if not isinstance(service_config, dict):
                continue
            raw_ports = service_config.get("ports")
            if raw_ports is None:
                continue
            if not isinstance(raw_ports, list):
                raise DeployError("Workload service_config.ports must be a list.")
            for raw_port in raw_ports:
                used_ports.add(_coerce_service_port(raw_port=raw_port, context="Workload service_config"))
    return used_ports


def _org_scoped_service_port(*, org_id: str, used_ports: set[int]) -> int:
    normalized_org = (org_id or "").strip().lower()
    if not normalized_org:
        raise DeployError("org_id is required for deterministic workload port assignment.")

    span = _ORG_SCOPED_PORT_RANGE_END - _ORG_SCOPED_PORT_RANGE_START + 1
    if span <= 0:
        raise DeployError("Invalid org-scoped port range configuration.")

    seed = hashlib.sha256(normalized_org.encode("utf-8")).hexdigest()
    offset = int(seed[:8], 16) % span
    for step in range(span):
        candidate = _ORG_SCOPED_PORT_RANGE_START + ((offset + step) % span)
        if candidate not in used_ports:
            return candidate
    raise DeployError(
        f"No free org-scoped ports available in range {_ORG_SCOPED_PORT_RANGE_START}-{_ORG_SCOPED_PORT_RANGE_END}."
    )


def _ensure_org_scoped_workload_port(
    *,
    workload: dict[str, Any],
    existing_workload: dict[str, Any] | None,
    org_id: str,
    plan: dict[str, Any],
    instance_name: str | None,
) -> dict[str, Any]:
    service_config = workload.get("service_config")
    if not isinstance(service_config, dict):
        raise DeployError("Workload service_config must be an object.")

    server_names = _extract_workload_server_names(workload=workload, context="Workload patch")
    # Domain-based routing does not require an org-scoped origin port.
    if server_names:
        return workload

    explicit_port = _extract_primary_service_port(workload=workload, context="Workload patch")
    if explicit_port is not None:
        return workload

    if existing_workload is not None:
        existing_port = _extract_primary_service_port(workload=existing_workload, context="Existing workload")
        if existing_port is not None:
            service_config["ports"] = [existing_port]
            workload["service_config"] = service_config
            return workload

    used_ports = _collect_used_instance_ports(plan=plan, instance_name=instance_name)
    assigned_port = _org_scoped_service_port(org_id=org_id, used_ports=used_ports)
    service_config["ports"] = [assigned_port]
    workload["service_config"] = service_config
    return workload


def build_funnel_publication_workload_patch(
    *,
    workload_name: str,
    client_id: str,
    upstream_base_url: str,
    upstream_api_base_url: str,
    server_names: list[str],
    https: bool,
    destination_path: str,
) -> dict[str, Any]:
    name = workload_name.strip()
    if not name:
        raise DeployError("Deploy workloadName must be non-empty.")
    _ = upstream_base_url

    resolved_client_id = client_id.strip()
    if not resolved_client_id:
        raise DeployError("Deploy client_id must be non-empty.")

    api_base_root = upstream_api_base_url.strip().rstrip("/")
    if not api_base_root.startswith(("http://", "https://")):
        raise DeployError("Deploy upstreamApiBaseUrl must start with http:// or https://.")

    seen_server_names: set[str] = set()
    normalized_server_names: list[str] = []
    for raw in server_names:
        hostname = raw.strip().lower()
        if not hostname:
            continue
        if " " in hostname:
            raise DeployError(f"Invalid hostname in deploy serverNames: '{raw}'.")
        if hostname in seen_server_names:
            continue
        seen_server_names.add(hostname)
        normalized_server_names.append(hostname)

    destination = destination_path.strip()
    if not destination:
        raise DeployError("Deploy destinationPath must be non-empty.")

    https_enabled = https and bool(normalized_server_names)

    return {
        "name": name,
        "source_type": "funnel_artifact",
        "source_ref": {
            "client_id": resolved_client_id,
            "upstream_api_base_root": api_base_root,
            "runtime_dist_path": settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH,
            "artifact": {
                "meta": {
                    "clientId": resolved_client_id,
                },
                "products": {},
            },
        },
        "repo_url": None,
        "runtime": "static",
        "build_config": {
            "install_command": None,
            "build_command": None,
            "system_packages": [],
        },
        "service_config": {
            "command": None,
            "environment": {},
            "ports": [],
            "server_names": normalized_server_names,
            "https": https_enabled,
        },
        "destination_path": destination,
    }


def build_funnel_artifact_workload_patch(
    *,
    workload_name: str,
    client_id: str,
    upstream_base_url: str,
    upstream_api_base_url: str,
    server_names: list[str],
    https: bool,
    destination_path: str,
) -> dict[str, Any]:
    return build_funnel_publication_workload_patch(
        workload_name=workload_name,
        client_id=client_id,
        upstream_base_url=upstream_base_url,
        upstream_api_base_url=upstream_api_base_url,
        server_names=server_names,
        https=https,
        destination_path=destination_path,
    )


def _walk_json_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json_dicts(item)


def _extract_public_asset_id_from_url(raw_value: str) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None

    path = value
    if value.startswith(("http://", "https://")):
        path = urlsplit(value).path or ""

    trimmed_path = path.strip()
    lowered_path = trimmed_path.lower()
    for prefix in _PUBLIC_ASSET_URL_PREFIXES:
        if not lowered_path.startswith(prefix):
            continue
        remainder = trimmed_path[len(prefix):]
        token = remainder.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip()
        if not token:
            return None
        if "." in token:
            token = token.split(".", 1)[0]
        if not token:
            return None
        return token

    return None


def _extract_embedded_asset_public_ids(
    *,
    puck_data: dict[str, Any],
    design_system_tokens: dict[str, Any] | None,
    context_label: str,
) -> set[str]:
    public_ids: set[str] = set()

    for obj in _walk_json_dicts(puck_data):
        for key in _ARTIFACT_ASSET_PUBLIC_ID_KEYS:
            if key not in obj:
                continue
            raw_value = obj.get(key)
            if not isinstance(raw_value, str) or not raw_value.strip():
                raise DeployError(
                    f"{context_label} includes invalid {key}. Expected a non-empty UUID string."
                )
            cleaned = raw_value.strip()
            try:
                normalized = str(UUID(cleaned))
            except ValueError as exc:
                raise DeployError(
                    f"{context_label} includes invalid {key} '{cleaned}'. Expected a UUID."
                ) from exc
            public_ids.add(normalized)

        for raw_value in obj.values():
            if not isinstance(raw_value, str):
                continue
            public_id_from_url = _extract_public_asset_id_from_url(raw_value)
            if not public_id_from_url:
                continue
            try:
                normalized_from_url = str(UUID(public_id_from_url))
            except ValueError as exc:
                raise DeployError(
                    f"{context_label} includes invalid public asset URL '{raw_value}'. "
                    "Expected /public/assets/<uuid>."
                ) from exc
            public_ids.add(normalized_from_url)

    if isinstance(design_system_tokens, dict):
        brand = design_system_tokens.get("brand")
        if isinstance(brand, dict) and brand.get("logoAssetPublicId") is not None:
            raw_logo_public_id = brand.get("logoAssetPublicId")
            if not isinstance(raw_logo_public_id, str) or not raw_logo_public_id.strip():
                raise DeployError(
                    f"{context_label} designSystemTokens.brand.logoAssetPublicId must be a non-empty UUID string."
                )
            cleaned_logo_public_id = raw_logo_public_id.strip()
            try:
                normalized_logo_public_id = str(UUID(cleaned_logo_public_id))
            except ValueError as exc:
                raise DeployError(
                    f"{context_label} designSystemTokens.brand.logoAssetPublicId "
                    f"'{cleaned_logo_public_id}' is not a valid UUID."
                ) from exc
            public_ids.add(normalized_logo_public_id)

    return public_ids


def _build_embedded_asset_payload(
    *,
    session: Any,
    org_id: str,
    client_id: str,
    public_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], int]:
    if not public_ids:
        return {}, 0

    from sqlalchemy import select

    from app.db.models import Asset
    from app.services.media_storage import MediaStorage

    asset_public_ids = [UUID(value) for value in public_ids]
    assets = list(
        session.scalars(
            select(Asset).where(
                Asset.org_id == org_id,
                Asset.client_id == client_id,
                Asset.public_id.in_(asset_public_ids),
            )
        ).all()
    )
    assets_by_public_id = {str(asset.public_id): asset for asset in assets}
    missing_public_ids = [public_id for public_id in public_ids if public_id not in assets_by_public_id]
    if missing_public_ids:
        raise DeployError(
            "Funnel artifact references assetPublicId values that do not exist for this client: "
            + ", ".join(missing_public_ids)
        )

    storage = MediaStorage()
    output: dict[str, dict[str, Any]] = {}
    total_bytes = 0

    for public_id in public_ids:
        asset = assets_by_public_id[public_id]
        if asset.asset_kind != "image":
            raise DeployError(
                f"Asset {public_id} has kind '{asset.asset_kind}'. Only image assets can be embedded in funnel artifacts."
            )
        if asset.file_status != "ready":
            raise DeployError(
                f"Asset {public_id} is not ready (file_status={asset.file_status or 'null'})."
            )
        if not asset.storage_key:
            raise DeployError(f"Asset {public_id} is missing storage_key.")

        data, downloaded_content_type = storage.download_bytes(key=asset.storage_key)
        if not data:
            raise DeployError(f"Asset {public_id} downloaded empty bytes from object storage.")

        content_type = (asset.content_type or downloaded_content_type or "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            raise DeployError(
                f"Asset {public_id} has unsupported content type '{content_type or 'unknown'}'. Expected image/*."
            )

        data, content_type = _optimize_embedded_artifact_image_bytes(
            data=data,
            content_type=content_type,
            public_id=public_id,
        )

        total_bytes += len(data)
        if total_bytes > _DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES:
            raise DeployError(
                "Embedded funnel artifact assets exceed DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES "
                f"(current={total_bytes} bytes, limit={_DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES} bytes)."
            )

        output[public_id] = {
            "contentType": content_type,
            "sizeBytes": len(data),
            "bytesBase64": base64.b64encode(data).decode("ascii"),
        }

    return output, total_bytes


def _optimize_embedded_artifact_image_bytes(
    *,
    data: bytes,
    content_type: str,
    public_id: str,
) -> tuple[bytes, str]:
    """
    Reduce embedded artifact size by resizing and re-encoding common raster assets to WebP.

    We intentionally keep strict behavior: invalid optimization config or unreadable image bytes
    fail fast with a descriptive error.
    """

    normalized_content_type = str(content_type or "").strip().lower()
    if normalized_content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        return data, normalized_content_type

    max_dimension = _DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION
    quality = _DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY
    if max_dimension <= 0:
        raise DeployError("DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION must be greater than zero.")
    if quality < 1 or quality > 100:
        raise DeployError("DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY must be between 1 and 100.")

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.copy()
    except Exception as exc:
        raise DeployError(
            f"Failed to decode embedded artifact asset image bytes for {public_id}: {exc}"
        ) from exc

    width, height = image.size
    if width <= 0 or height <= 0:
        raise DeployError(f"Embedded artifact asset {public_id} has invalid image dimensions ({width}x{height}).")

    longest_edge = max(width, height)
    if longest_edge > max_dimension:
        scale = max_dimension / float(longest_edge)
        resized = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        image = image.resize(resized, Image.Resampling.LANCZOS)

    # Preserve alpha when present; otherwise use RGB for denser encoding.
    if "A" in image.getbands():
        if image.mode != "RGBA":
            image = image.convert("RGBA")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    output = io.BytesIO()
    try:
        image.save(output, format="WEBP", quality=quality, method=6)
    except Exception as exc:
        raise DeployError(f"Failed to encode embedded artifact asset {public_id} to WebP: {exc}") from exc

    optimized = output.getvalue()
    if not optimized:
        raise DeployError(f"Embedded artifact asset {public_id} optimized to empty bytes.")
    return optimized, "image/webp"


def build_client_funnel_runtime_artifact_payload(
    *,
    session: Any,
    org_id: str,
    client_id: str,
    updated_from_funnel_id: str,
    updated_from_publication_id: str,
) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder
    from sqlalchemy import select

    from app.db.enums import FunnelStatusEnum
    from app.db.models import Funnel, FunnelPage, Product, ProductVariant
    from app.db.repositories.funnels import FunnelPublicRepository
    from app.services.design_systems import resolve_design_system_tokens
    from app.services.public_routing import require_product_route_slug

    template_to_artifact: dict[str, str] = {
        "pre-sales-listicle": "presales",
        "sales-pdp": "sales",
    }

    client_funnels = list(
        session.scalars(
            select(Funnel).where(
                Funnel.org_id == org_id,
                Funnel.client_id == client_id,
                Funnel.active_publication_id.is_not(None),
                Funnel.status != FunnelStatusEnum.disabled,
            ).order_by(Funnel.created_at.asc(), Funnel.id.asc())
        ).all()
    )
    if not client_funnels:
        raise DeployError("No published funnels found for client deploy artifact.")

    product_ids: set[str] = set()
    for client_funnel in client_funnels:
        if not client_funnel.product_id:
            raise DeployError(f"Published funnel '{client_funnel.id}' is missing product_id.")
        product_ids.add(str(client_funnel.product_id))

    products = list(
        session.scalars(
            select(Product).where(
                Product.org_id == org_id,
                Product.id.in_(product_ids),
            )
        ).all()
    )
    products_by_id = {str(product.id): product for product in products}
    missing_product_ids = sorted(pid for pid in product_ids if pid not in products_by_id)
    if missing_product_ids:
        raise DeployError(
            "Missing products for published funnels in deploy artifact generation: "
            + ", ".join(missing_product_ids)
        )

    public_repo = FunnelPublicRepository(session)
    products_payload: dict[str, dict[str, Any]] = {}
    product_slug_to_product_id: dict[str, str] = {}
    embedded_asset_public_ids: set[str] = set()

    for client_funnel in client_funnels:
        route_slug = (client_funnel.route_slug or "").strip()
        if not route_slug:
            raise DeployError("Published funnel is missing route_slug.")

        product_id = str(client_funnel.product_id)
        product = products_by_id.get(product_id)
        if not product:
            raise DeployError(f"Product '{product_id}' not found while creating deploy artifact.")

        try:
            product_slug = require_product_route_slug(product=product)
        except ValueError as exc:
            raise DeployError(str(exc)) from exc

        existing_product_id = product_slug_to_product_id.get(product_slug)
        if existing_product_id and existing_product_id != product_id:
            raise DeployError(
                f"Product route slug '{product_slug}' is used by multiple products. "
                "Ensure product ids have unique 8-character prefixes."
            )
        product_slug_to_product_id[product_slug] = product_id

        active_publication_id = str(client_funnel.active_publication_id or "").strip()
        if not active_publication_id:
            raise DeployError(f"Published funnel '{client_funnel.id}' has no active publication.")
        active_publication = public_repo.get_active_publication(
            funnel_id=str(client_funnel.id),
            publication_id=active_publication_id,
        )
        if not active_publication:
            raise DeployError(f"Active publication not found for funnel '{client_funnel.id}'.")
        publication_pages = public_repo.list_publication_pages(publication_id=active_publication_id)
        if not publication_pages:
            raise DeployError(f"Publication '{active_publication_id}' contains no pages.")

        page_details: list[tuple[str, str, Any, FunnelPage | None]] = []
        entry_slug: str | None = None
        seen_artifacts: set[str] = set()

        for item in publication_pages:
            version = public_repo.get_page_version(version_id=str(item.page_version_id))
            if not version:
                raise DeployError(f"Publication page '{item.page_id}' has no version.")
            page = session.scalars(select(FunnelPage).where(FunnelPage.id == item.page_id)).first()
            template_id = (page.template_id if page else None) or ""
            artifact_slug = template_to_artifact.get(template_id)
            if not artifact_slug:
                raise DeployError(
                    f"Page '{item.page_id}' in funnel '{client_funnel.id}' has unsupported template '{template_id or 'unknown'}'."
                )
            if artifact_slug in seen_artifacts:
                raise DeployError(
                    f"Funnel '{client_funnel.id}' has multiple pages mapped to artifact '{artifact_slug}'."
                )
            seen_artifacts.add(artifact_slug)
            page_details.append((artifact_slug, str(item.page_id), version, page))
            if str(item.page_id) == str(active_publication.entry_page_id):
                entry_slug = artifact_slug

        if not entry_slug:
            raise DeployError(f"Entry page artifact slug not found for funnel '{client_funnel.id}'.")

        page_map = {page_id: artifact_slug for artifact_slug, page_id, _, _ in page_details}
        pages_payload: dict[str, dict[str, Any]] = {}
        for artifact_slug, page_id, version, page in page_details:
            tokens = resolve_design_system_tokens(
                session=session,
                org_id=str(client_funnel.org_id),
                client_id=str(client_funnel.client_id),
                funnel=client_funnel,
                page=page,
            )
            page_context_label = (
                f"Funnel '{client_funnel.id}' page '{page_id}' ({product_slug}/{route_slug}/{artifact_slug})"
            )
            page_asset_public_ids = _extract_embedded_asset_public_ids(
                puck_data=version.puck_data,
                design_system_tokens=tokens if isinstance(tokens, dict) else None,
                context_label=page_context_label,
            )
            embedded_asset_public_ids.update(page_asset_public_ids)
            pages_payload[artifact_slug] = {
                "productSlug": product_slug,
                "funnelId": str(client_funnel.id),
                "funnelSlug": route_slug,
                "publicationId": active_publication_id,
                "pageId": page_id,
                "slug": artifact_slug,
                "puckData": version.puck_data,
                "pageMap": page_map,
                "designSystemTokens": tokens,
                "nextPageId": str(page.next_page_id) if page and page.next_page_id else None,
            }

        variants_query = select(ProductVariant).where(ProductVariant.product_id == product.id)
        if client_funnel.selected_offer_id:
            variants_query = variants_query.where(ProductVariant.offer_id == client_funnel.selected_offer_id)
        variants = session.scalars(variants_query).all()
        serialized_variants: list[dict[str, Any]] = []
        for variant in variants:
            data = jsonable_encoder(variant)
            data.pop("external_price_id", None)
            serialized_variants.append(data)

        commerce_payload: dict[str, Any] | None = None
        if serialized_variants:
            commerce_payload = {
                "productSlug": product_slug,
                "funnelSlug": route_slug,
                "funnelId": str(client_funnel.id),
                "product": {
                    **jsonable_encoder(product),
                    "variants": serialized_variants,
                    "variants_count": len(serialized_variants),
                },
            }

        product_bucket = products_payload.setdefault(
            product_slug,
            {
                "meta": {
                    "productId": product_id,
                    "productSlug": product_slug,
                },
                "funnels": {},
            },
        )
        funnels_payload = product_bucket.get("funnels")
        if not isinstance(funnels_payload, dict):
            raise DeployError(f"Artifact product '{product_slug}' has an invalid funnels payload.")
        if route_slug in funnels_payload:
            raise DeployError(
                f"Duplicate funnel route slug '{route_slug}' within artifact product '{product_slug}'."
            )

        funnels_payload[route_slug] = {
            "meta": {
                "productSlug": product_slug,
                "funnelSlug": route_slug,
                "funnelId": str(client_funnel.id),
                "publicationId": active_publication_id,
                "entrySlug": entry_slug,
                "pages": [{"pageId": page_id, "slug": artifact_slug} for artifact_slug, page_id, _, _ in page_details],
            },
            "pages": pages_payload,
            "commerce": commerce_payload,
        }

    embedded_assets, total_embedded_asset_bytes = _build_embedded_asset_payload(
        session=session,
        org_id=org_id,
        client_id=client_id,
        public_ids=sorted(embedded_asset_public_ids),
    )

    return {
        "meta": {
            "clientId": str(client_id),
            "updatedFromFunnelId": updated_from_funnel_id,
            "updatedFromPublicationId": updated_from_publication_id,
        },
        "products": products_payload,
        "assets": {
            "totalBytes": total_embedded_asset_bytes,
            "items": embedded_assets,
        },
    }


def persist_client_funnel_runtime_artifact(
    *,
    session: Any,
    org_id: str,
    funnel_id: str,
    publication_id: str,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.enums import ArtifactTypeEnum
    from app.db.models import Funnel
    from app.db.repositories.artifacts import ArtifactsRepository

    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise DeployError("Funnel not found while creating deploy artifact.")

    client_id = str(funnel.client_id)
    payload = build_client_funnel_runtime_artifact_payload(
        session=session,
        org_id=org_id,
        client_id=client_id,
        updated_from_funnel_id=str(funnel.id),
        updated_from_publication_id=publication_id,
    )

    artifacts_repo = ArtifactsRepository(session)
    latest = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        artifact_type=ArtifactTypeEnum.funnel_runtime_bundle,
    )
    next_version = int(latest.version) + 1 if latest and latest.version else 1
    artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=client_id,
        artifact_type=ArtifactTypeEnum.funnel_runtime_bundle,
        data=payload,
        created_by_user=created_by_user_id,
        version=next_version,
    )
    return {
        "artifact_id": str(artifact.id),
        "artifact_version": int(artifact.version),
        "client_id": client_id,
    }


def hydrate_funnel_artifact_workload_patch(
    *,
    session: Any,
    org_id: str,
    funnel_id: str,
    publication_id: str,
    workload_patch: dict[str, Any],
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    source_type = str(workload_patch.get("source_type") or "").strip().lower()
    if source_type != "funnel_artifact":
        return workload_patch

    source_ref = workload_patch.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError("funnel_artifact workload patch is missing source_ref.")

    artifact_ref = persist_client_funnel_runtime_artifact(
        session=session,
        org_id=org_id,
        funnel_id=funnel_id,
        publication_id=publication_id,
        created_by_user_id=created_by_user_id,
    )
    source_ref["client_id"] = str(artifact_ref["client_id"])
    source_ref["artifact_id"] = str(artifact_ref["artifact_id"])
    source_ref["artifact_version"] = int(artifact_ref["artifact_version"])
    source_ref["artifact"] = {
        "meta": {
            "clientId": str(artifact_ref["client_id"]),
            "artifactId": str(artifact_ref["artifact_id"]),
            "artifactVersion": int(artifact_ref["artifact_version"]),
        },
        "products": {},
    }
    workload_patch["source_ref"] = source_ref
    return workload_patch


def patch_workload_in_plan(
    *,
    org_id: str,
    workload_patch: dict[str, Any],
    plan_path: str | None = None,
    instance_name: str | None = None,
    create_if_missing: bool = False,
    in_place: bool = False,
) -> dict[str, Any]:
    from cloudhand.models import ApplicationSpec

    name = (workload_patch.get("name") or "").strip()
    if not name:
        raise DeployError("Workload patch must include a non-empty 'name' field.")
    resolved_org_id = (org_id or "").strip()
    if not resolved_org_id:
        raise DeployError("org_id is required when patching a workload.")

    ch_dir = _cloudhand_dir()
    ch_dir.mkdir(parents=True, exist_ok=True)

    base_plan_path = _assert_under_cloudhand(Path(plan_path)) if plan_path else _find_latest_plan()
    if not base_plan_path or not base_plan_path.exists():
        raise DeployError("No plan found.")

    try:
        plan = json.loads(base_plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec") or {}
    instances = new_spec.get("instances") or []
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    updated = 0
    for inst in instances:
        if instance_name and inst.get("name") != instance_name:
            continue
        workloads = inst.get("workloads") or []
        if not isinstance(workloads, list):
            continue
        for i, existing in enumerate(workloads):
            if (existing.get("name") or "").strip() != name:
                continue
            merged = _deep_merge(existing, workload_patch)
            merged = _ensure_org_scoped_workload_port(
                workload=merged,
                existing_workload=existing if isinstance(existing, dict) else None,
                org_id=resolved_org_id,
                plan=plan,
                instance_name=str(inst.get("name") or "").strip() or None,
            )
            try:
                validated = ApplicationSpec.model_validate(merged)
            except Exception as exc:
                raise DeployError(f"Updated workload is invalid: {exc}") from exc
            workloads[i] = json.loads(validated.model_dump_json())
            inst["workloads"] = workloads
            updated += 1

    if updated == 0:
        if not create_if_missing:
            raise DeployError(f"No workload named '{name}' found in plan.")

        # Choose where to insert the new workload
        if instance_name:
            target_inst = next((i for i in instances if i.get("name") == instance_name), None)
            if not target_inst:
                raise DeployError(f"Instance '{instance_name}' not found in plan.")
        else:
            if len(instances) != 1:
                raise DeployError("instance_name is required when plan contains multiple instances.")
            target_inst = instances[0]

        workload_for_create = _ensure_org_scoped_workload_port(
            workload=dict(workload_patch),
            existing_workload=None,
            org_id=resolved_org_id,
            plan=plan,
            instance_name=str(target_inst.get("name") or "").strip() or None,
        )

        try:
            validated = ApplicationSpec.model_validate(workload_for_create)
        except Exception as exc:
            raise DeployError(f"Workload is invalid: {exc}") from exc

        target_inst.setdefault("workloads", [])
        if not isinstance(target_inst["workloads"], list):
            target_inst["workloads"] = []
        target_inst["workloads"].append(json.loads(validated.model_dump_json()))
        updated = 1

    plan["new_spec"] = new_spec

    out_path = base_plan_path if in_place else (ch_dir / f"plan-{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%SZ')}.json")
    try:
        out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"Failed to write updated plan: {exc}") from exc

    return {
        "status": "ok",
        "base_plan_path": str(base_plan_path),
        "updated_plan_path": str(out_path),
        "workload_name": name,
        "updated_count": updated,
    }


def _bootstrap_deploy_plan_payload(*, workload_patch: dict[str, Any], instance_name: str | None) -> dict[str, Any]:
    from cloudhand.models import ApplicationSpec

    resolved_instance_name = (instance_name or "").strip() or "ubuntu-4gb-nbg1-2"

    try:
        validated_workload = ApplicationSpec.model_validate(workload_patch)
    except Exception as exc:
        raise DeployError(f"Workload is invalid for bootstrap plan: {exc}") from exc

    workload_payload = json.loads(validated_workload.model_dump_json())
    return {
        "operations": [],
        "new_spec": {
            "provider": "hetzner",
            "region": "fsn1",
            "networks": [
                {
                    "name": "default",
                    "cidr": "10.0.0.0/16",
                }
            ],
            "instances": [
                {
                    "name": resolved_instance_name,
                    "size": "cx23",
                    "network": "default",
                    "region": "nbg1",
                    "labels": {},
                    "workloads": [workload_payload],
                    "maintenance": None,
                }
            ],
            "load_balancers": [],
            "firewalls": [],
            "dns_records": [],
            "containers": [],
        },
    }


def ensure_plan_for_funnel_publish_workload(
    *,
    workload_patch: dict[str, Any],
    plan_path: str | None,
    instance_name: str | None,
) -> dict[str, Any]:
    requested_plan_path = (plan_path or "").strip()
    if requested_plan_path:
        candidate = _assert_under_cloudhand(Path(requested_plan_path))
        if candidate.exists():
            return {"plan_path": str(candidate), "bootstrapped": False}
        bootstrap_payload = _bootstrap_deploy_plan_payload(
            workload_patch=workload_patch,
            instance_name=instance_name,
        )
        saved = save_plan(content=json.dumps(bootstrap_payload, indent=2), path=str(candidate))
        return {"plan_path": saved["path"], "bootstrapped": True}

    latest = _find_latest_plan()
    if latest and latest.exists():
        return {"plan_path": str(latest), "bootstrapped": False}

    bootstrap_payload = _bootstrap_deploy_plan_payload(
        workload_patch=workload_patch,
        instance_name=instance_name,
    )
    saved = save_plan(content=json.dumps(bootstrap_payload, indent=2))
    return {"plan_path": saved["path"], "bootstrapped": True}


def _load_funnel_runtime_artifact_payload_for_apply(*, artifact_id: str) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.enums import ArtifactTypeEnum
    from app.db.models import Artifact

    session = SessionLocal()
    try:
        artifact = session.scalars(select(Artifact).where(Artifact.id == artifact_id)).first()
    finally:
        session.close()

    if not artifact:
        raise DeployError(f"Funnel runtime artifact '{artifact_id}' was not found.")
    if artifact.type != ArtifactTypeEnum.funnel_runtime_bundle:
        raise DeployError(
            f"Artifact '{artifact_id}' has type '{artifact.type.value}' but expected '{ArtifactTypeEnum.funnel_runtime_bundle.value}'."
        )
    data = artifact.data
    if not isinstance(data, dict):
        raise DeployError(f"Artifact '{artifact_id}' payload is invalid.")
    if not isinstance(data.get("meta"), dict):
        raise DeployError(f"Artifact '{artifact_id}' payload is missing meta.")
    if not isinstance(data.get("products"), dict):
        raise DeployError(f"Artifact '{artifact_id}' payload is missing products.")
    return data


def _load_product_route_context_for_apply(*, product_id: str) -> tuple[str, str]:
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import Product
    from app.services.public_routing import require_product_route_slug

    try:
        normalized_product_id = str(UUID(str(product_id).strip()))
    except ValueError as exc:
        raise DeployError(f"Invalid product_id '{product_id}' in funnel artifact source_ref.") from exc

    session = SessionLocal()
    try:
        product = session.scalars(select(Product).where(Product.id == normalized_product_id)).first()
    finally:
        session.close()

    if not product:
        raise DeployError(
            f"Product '{normalized_product_id}' referenced by funnel artifact workload was not found."
        )
    return str(product.client_id), require_product_route_slug(product=product)


def _normalize_legacy_publication_source_ref_for_apply(*, workload: dict[str, Any]) -> bool:
    name = str(workload.get("name") or "").strip() or "<unnamed>"
    source_ref = workload.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError(
            f"Workload '{name}' source_ref must be an object for source_type='funnel_publication'."
        )

    changed = False
    public_id = str(source_ref.get("public_id") or "").strip()
    if not public_id:
        raise DeployError(
            f"Workload '{name}' uses source_type='funnel_publication' but source_ref.public_id is missing."
        )

    upstream_base_url = str(source_ref.get("upstream_base_url") or "").strip().rstrip("/")
    if not upstream_base_url:
        upstream_base_url = str(settings.DEPLOY_PUBLIC_BASE_URL or "").strip().rstrip("/")
        if not upstream_base_url:
            legacy_api = str(source_ref.get("upstream_api_base_url") or "").strip().rstrip("/")
            if legacy_api:
                parsed = urlsplit(legacy_api)
                if parsed.scheme and parsed.netloc:
                    upstream_base_url = f"{parsed.scheme}://{parsed.netloc}"
        if not upstream_base_url:
            raise DeployError(
                f"Workload '{name}' is missing source_ref.upstream_base_url. "
                "Set DEPLOY_PUBLIC_BASE_URL or update the plan workload."
            )
        source_ref["upstream_base_url"] = upstream_base_url
        changed = True

    upstream_api_base_url = str(source_ref.get("upstream_api_base_url") or "").strip().rstrip("/")
    if not upstream_api_base_url:
        upstream_api_base_url = str(settings.DEPLOY_PUBLIC_API_BASE_URL or "").strip().rstrip("/")
        if not upstream_api_base_url:
            upstream_api_base_url = f"{upstream_base_url}/api"
        source_ref["upstream_api_base_url"] = upstream_api_base_url
        changed = True

    if not upstream_base_url.startswith(("http://", "https://")):
        raise DeployError(
            f"Workload '{name}' has invalid source_ref.upstream_base_url '{upstream_base_url}'."
        )
    if not upstream_api_base_url.startswith(("http://", "https://")):
        raise DeployError(
            f"Workload '{name}' has invalid source_ref.upstream_api_base_url '{upstream_api_base_url}'."
        )

    if changed:
        workload["source_ref"] = source_ref
    return changed


def _normalize_legacy_artifact_source_ref_for_apply(*, workload: dict[str, Any]) -> bool:
    name = str(workload.get("name") or "").strip() or "<unnamed>"
    source_ref = workload.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError(
            f"Workload '{name}' source_ref must be an object for source_type='funnel_artifact'."
        )

    changed = False
    client_id = str(source_ref.get("client_id") or "").strip()
    product_id = str(source_ref.get("product_id") or "").strip()

    # Legacy fallback path: source_type was historically set to funnel_artifact while carrying
    # publication proxy payload (`public_id`) without artifact references.
    if not client_id and not product_id and str(source_ref.get("public_id") or "").strip():
        workload["source_type"] = "funnel_publication"
        changed |= _normalize_legacy_publication_source_ref_for_apply(workload=workload)
        return True

    if not client_id:
        if product_id:
            resolved_client_id, _ = _load_product_route_context_for_apply(product_id=product_id)
            source_ref["client_id"] = resolved_client_id
            client_id = resolved_client_id
            changed = True
        else:
            artifact = source_ref.get("artifact")
            if isinstance(artifact, dict):
                meta = artifact.get("meta")
                if isinstance(meta, dict):
                    meta_client_id = str(meta.get("clientId") or meta.get("client_id") or "").strip()
                    if meta_client_id:
                        source_ref["client_id"] = meta_client_id
                        client_id = meta_client_id
                        changed = True

    if not client_id:
        raise DeployError(
            f"Workload '{name}' uses source_type='funnel_artifact' but source_ref.client_id is missing."
        )

    upstream_api_base_root = str(source_ref.get("upstream_api_base_root") or "").strip().rstrip("/")
    if not upstream_api_base_root:
        legacy_api = str(source_ref.get("upstream_api_base_url") or settings.DEPLOY_PUBLIC_API_BASE_URL or "").strip().rstrip("/")
        if not legacy_api:
            raise DeployError(
                f"Workload '{name}' is missing source_ref.upstream_api_base_root. "
                "Set DEPLOY_PUBLIC_API_BASE_URL or update the plan workload."
            )
        source_ref["upstream_api_base_root"] = legacy_api
        upstream_api_base_root = legacy_api
        changed = True

    if not upstream_api_base_root.startswith(("http://", "https://")):
        raise DeployError(
            f"Workload '{name}' has invalid source_ref.upstream_api_base_root '{upstream_api_base_root}'."
        )

    runtime_dist_path = str(source_ref.get("runtime_dist_path") or "").strip()
    if not runtime_dist_path:
        source_ref["runtime_dist_path"] = settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH
        changed = True

    artifact = source_ref.get("artifact")
    if not isinstance(artifact, dict):
        raise DeployError(
            f"Workload '{name}' source_ref.artifact must be an object for source_type='funnel_artifact'."
        )

    if not isinstance(artifact.get("meta"), dict):
        artifact["meta"] = {}
        changed = True

    if not isinstance(artifact.get("products"), dict):
        legacy_funnels = artifact.get("funnels")
        if isinstance(legacy_funnels, dict):
            if not product_id:
                meta = artifact.get("meta")
                if isinstance(meta, dict):
                    product_id = str(meta.get("productId") or meta.get("product_id") or "").strip()
            if not product_id:
                raise DeployError(
                    f"Workload '{name}' has legacy source_ref.artifact.funnels but source_ref.product_id is missing."
                )
            _resolved_client_id, product_slug = _load_product_route_context_for_apply(product_id=product_id)
            artifact["products"] = {
                product_slug: {
                    "meta": {
                        "productId": product_id,
                        "productSlug": product_slug,
                    },
                    "funnels": legacy_funnels,
                }
            }
            changed = True
        else:
            artifact["products"] = {}
            changed = True

    source_ref["artifact"] = artifact
    workload["source_ref"] = source_ref
    return changed


def _materialize_funnel_artifacts_for_apply(*, plan_file: Path) -> Path:
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec")
    if not isinstance(new_spec, dict):
        raise DeployError("Plan new_spec must be an object.")
    instances = new_spec.get("instances")
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    has_changes = False
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        workloads = inst.get("workloads")
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            source_type = str(workload.get("source_type") or "").strip().lower()
            if source_type == "funnel_publication":
                if _normalize_legacy_publication_source_ref_for_apply(workload=workload):
                    has_changes = True
                continue
            if source_type != "funnel_artifact":
                continue
            if _normalize_legacy_artifact_source_ref_for_apply(workload=workload):
                has_changes = True
            source_ref = workload.get("source_ref")
            if not isinstance(source_ref, dict):
                raise DeployError(
                    f"Workload '{workload.get('name')}' source_ref must be an object for source_type='funnel_artifact'."
                )
            artifact = source_ref.get("artifact")
            if (
                isinstance(artifact, dict)
                and isinstance(artifact.get("products"), dict)
                and bool(artifact.get("products"))
            ):
                continue
            artifact_id = str(source_ref.get("artifact_id") or "").strip()
            if not artifact_id:
                # Some existing plans may carry placeholder inline artifacts with empty products and
                # no DB artifact reference yet. Leave those unchanged here.
                continue
            source_ref["artifact"] = _load_funnel_runtime_artifact_payload_for_apply(artifact_id=artifact_id)
            workload["source_ref"] = source_ref
            has_changes = True

    if not has_changes:
        return plan_file

    materialized_path = (
        _cloudhand_dir()
        / f"apply-materialized-{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%SZ')}-{uuid4().hex[:8]}.json"
    )
    try:
        materialized_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    except Exception as exc:
        raise DeployError(f"Failed to write materialized apply plan: {exc}") from exc
    return materialized_path


async def apply_plan(*, plan_path: str | None = None) -> dict[str, Any]:
    """
    Apply a plan using the embedded Cloudhand engine (Terraform + SSH deploy).

    Mirrors the control-plane behavior: writes state under DEPLOY_ROOT_DIR and returns
    consolidated logs + server IPs (when available).
    """

    # Token is required for Terraform provider auth. We keep it simple for now:
    # require a process env var so it never needs to traverse the UI.
    if not os.getenv("HCLOUD_TOKEN") and not os.getenv("TF_VAR_hcloud_token"):
        raise DeployError("HCLOUD_TOKEN is not set. Terraform apply cannot run.")

    ch_dir = _cloudhand_dir()
    tf_dir = _terraform_dir()
    ch_dir.mkdir(parents=True, exist_ok=True)

    # Pick plan file
    if plan_path:
        plan_file = _assert_under_cloudhand(Path(plan_path))
    else:
        plan_file = _find_latest_plan()

    if not plan_file or not plan_file.exists():
        raise DeployError("No plan found.")

    requested_plan_file = plan_file
    plan_file = _materialize_funnel_artifacts_for_apply(plan_file=plan_file)

    # Run Cloudhand apply in a subprocess so we can stream/capture Terraform output.
    env = os.environ.copy()
    project_id = settings.DEPLOY_PROJECT_ID
    terraform_bin = _resolve_terraform_bin()

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "cloudhand.cli",
        "--project",
        project_id,
        "apply",
        str(plan_file),
        "--auto-approve",
        "--terraform-bin",
        terraform_bin,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        # Cloudhand assumes the project root is cwd and uses ./cloudhand/ for artifacts/state.
        cwd=str(_cloudhand_dir().parent),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    logs: list[str] = []
    assert proc.stdout
    async for raw in proc.stdout:
        logs.append(raw.decode(errors="ignore"))

    rc = await proc.wait()

    # Try to read terraform outputs for convenience
    server_ips: dict[str, str] = {}
    live_url: Optional[str] = None
    tf_out: dict[str, Any] = {}

    if tf_dir.exists():
        try:
            proc2 = await asyncio.create_subprocess_exec(
                terraform_bin,
                "output",
                "-json",
                cwd=str(tf_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc2.communicate()
            if proc2.returncode == 0:
                tf_out = json.loads(out.decode() or "{}")
            else:
                logs.append(f"Warning: terraform output failed: {err.decode(errors='ignore')}\n")
        except Exception as exc:  # pragma: no cover
            logs.append(f"Warning: failed to read terraform outputs: {exc}\n")

    if isinstance(tf_out.get("server_ips"), dict):
        val = tf_out["server_ips"].get("value")
        if isinstance(val, dict):
            # best-effort type narrowing
            server_ips = {str(k): str(v) for k, v in val.items()}
            if server_ips:
                live_url = f"http://{next(iter(server_ips.values()))}"

    return {
        "returncode": rc,
        "plan_path": str(requested_plan_file),
        "materialized_plan_path": str(plan_file),
        "server_ips": server_ips,
        "live_url": live_url,
        "logs": "".join(logs),
    }


def _normalize_access_urls(urls: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls or []:
        if not isinstance(raw, str):
            continue
        url = raw.strip()
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _normalize_bunny_pull_zone_name_component(*, value: str, label: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", (value or "").strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        raise DeployError(
            f"Bunny pull zone name component '{label}' is empty after normalization. "
            f"Received value='{value}'."
        )
    return normalized


def _build_bunny_pull_zone_name(*, org_id: str) -> str:
    org_component = _normalize_bunny_pull_zone_name_component(
        value=org_id,
        label="org_id",
    )
    return org_component


def _bunny_api_request(*, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    api_key = str(settings.BUNNY_API_KEY or "").strip()
    if not api_key:
        raise DeployError("Bunny pull zone provisioning requires BUNNY_API_KEY.")

    base_url = str(settings.BUNNY_API_BASE_URL or "").strip().rstrip("/")
    if not base_url:
        raise DeployError("BUNNY_API_BASE_URL must be configured for Bunny pull zone provisioning.")

    normalized_method = (method or "").strip().upper()
    if not normalized_method:
        raise DeployError("Bunny API request method is required.")

    endpoint = f"{base_url}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                normalized_method,
                endpoint,
                headers={"AccessKey": api_key, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise DeployError(f"Bunny API request failed ({normalized_method} {path}): {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            message = body.get("Message") or body.get("Error") or body.get("detail") or body.get("message")
            if isinstance(message, str) and message.strip():
                detail = message.strip()
            elif not detail:
                detail = json.dumps(body, ensure_ascii=True)
        elif not detail:
            detail = "<empty response body>"
        raise DeployError(
            f"Bunny API request failed ({normalized_method} {path}) "
            f"with status {response.status_code}: {detail}"
        )

    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise DeployError(
            f"Bunny API request returned non-JSON response ({normalized_method} {path})."
        ) from exc


def _list_bunny_pull_zones() -> list[dict[str, Any]]:
    payload = _bunny_api_request(method="GET", path="/pullzone")
    items: Any
    if isinstance(payload, dict):
        items = payload.get("Items")
    elif isinstance(payload, list):
        # Some Bunny accounts/environments return the collection directly.
        items = payload
    else:
        raise DeployError(
            "Bunny list pull zones response must be an object with Items or an array."
        )
    if not isinstance(items, list):
        raise DeployError("Bunny list pull zones response must contain an array of pull zones.")
    zones: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise DeployError(f"Bunny list pull zones response item at index {idx} is invalid.")
        zones.append(item)
    return zones


def _find_bunny_pull_zone_by_name(*, zone_name: str) -> dict[str, Any] | None:
    normalized_target = zone_name.strip().lower()
    matches: list[dict[str, Any]] = []
    for zone in _list_bunny_pull_zones():
        candidate = str(zone.get("Name") or "").strip().lower()
        if candidate == normalized_target:
            matches.append(zone)
    if len(matches) > 1:
        raise DeployError(f"Multiple Bunny pull zones found for name '{zone_name}'.")
    return matches[0] if matches else None


def _coerce_bunny_pull_zone_id(*, zone: dict[str, Any]) -> int:
    raw_id = zone.get("Id")
    try:
        zone_id = int(raw_id)
    except Exception as exc:
        raise DeployError("Bunny pull zone payload is missing a valid Id.") from exc
    if zone_id <= 0:
        raise DeployError("Bunny pull zone Id must be greater than zero.")
    return zone_id


def _normalize_hostname(*, value: str, context: str) -> str:
    normalized = (value or "").strip().lower().rstrip(".")
    if not normalized:
        raise DeployError(f"{context} hostname is required.")
    if "://" in normalized or "/" in normalized or "?" in normalized or "#" in normalized:
        raise DeployError(
            f"{context} hostname '{value}' is invalid. Use a bare hostname (for example: shop.example.com)."
        )
    if not _HOSTNAME_RE.match(normalized):
        raise DeployError(f"{context} hostname '{value}' is invalid.")
    return normalized


def _normalize_workload_server_names(*, server_names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in server_names:
        hostname = _normalize_hostname(value=raw, context="Workload")
        if hostname in seen:
            continue
        seen.add(hostname)
        out.append(hostname)
    return out


def _extract_bunny_pull_zone_hostname_values(zone: dict[str, Any]) -> list[str]:
    hostnames = zone.get("Hostnames")
    if hostnames is None:
        return []
    if not isinstance(hostnames, list):
        raise DeployError("Bunny pull zone response field Hostnames must be an array when provided.")

    values: list[str] = []
    seen: set[str] = set()
    for idx, hostname in enumerate(hostnames):
        if not isinstance(hostname, dict):
            raise DeployError(f"Bunny pull zone hostname at index {idx} is invalid.")
        value = str(hostname.get("Value") or "").strip().lower()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _extract_bunny_pull_zone_dns_target_hostname(zone: dict[str, Any]) -> str:
    hostname_values = _extract_bunny_pull_zone_hostname_values(zone)
    for value in hostname_values:
        if value.endswith(".b-cdn.net"):
            return value
    raise DeployError(
        "Bunny pull zone response does not include a default '*.b-cdn.net' hostname for CNAME target."
    )


def _get_bunny_pull_zone(*, zone_id: int) -> dict[str, Any]:
    payload = _bunny_api_request(method="GET", path=f"/pullzone/{zone_id}")
    if not isinstance(payload, dict):
        raise DeployError("Bunny get pull zone response must be an object.")
    return payload


def _ensure_bunny_pull_zone_hostname(*, zone_id: int, hostname: str) -> dict[str, Any]:
    normalized_hostname = _normalize_hostname(value=hostname, context="Bunny custom domain")
    zone = _get_bunny_pull_zone(zone_id=zone_id)
    existing = _extract_bunny_pull_zone_hostname_values(zone)
    if normalized_hostname in existing:
        return {"hostname": normalized_hostname, "status": "existing"}

    response = _bunny_api_request(
        method="POST",
        path=f"/pullzone/{zone_id}/addHostname",
        payload={"Hostname": normalized_hostname},
    )
    if response is not None and not isinstance(response, (dict, bool, str)):
        raise DeployError("Bunny add hostname response must be an object, bool, or string when present.")
    return {"hostname": normalized_hostname, "status": "created"}


def _ensure_bunny_pull_zone_auto_ssl_enabled(*, zone_id: int) -> None:
    response = _bunny_api_request(
        method="POST",
        path=f"/pullzone/{zone_id}",
        payload={"EnableAutoSSL": True, "DisableLetsEncrypt": False},
    )
    if response is not None and not isinstance(response, (dict, bool, str)):
        raise DeployError("Bunny pull zone SSL update response must be an object, bool, or string when present.")


def _request_bunny_pull_zone_certificate(*, zone_id: int, hostname: str) -> dict[str, Any] | None:
    _ = zone_id
    normalized_hostname = _normalize_hostname(value=hostname, context="Bunny certificate")
    response = _bunny_api_request(
        method="GET",
        path=f"/pullzone/loadFreeCertificate?hostname={quote(normalized_hostname, safe='')}",
    )
    if response is None:
        return None
    if isinstance(response, dict):
        return response
    if isinstance(response, bool):
        return {"ok": response}
    if isinstance(response, str):
        return {"message": response}
    raise DeployError("Bunny free certificate response must be an object, bool, or string when present.")


def _provision_bunny_custom_domains(
    *,
    bunny_zone: dict[str, Any],
    server_names: list[str],
    request_ssl: bool = True,
) -> dict[str, Any]:
    normalized_server_names = _normalize_workload_server_names(server_names=server_names)
    if not normalized_server_names:
        return {
            "dnsTargetHostname": None,
            "domains": [],
            "pullZoneHostnames": _extract_bunny_pull_zone_hostname_values(bunny_zone),
        }

    zone_id = _coerce_bunny_pull_zone_id(zone=bunny_zone)
    dns_target_hostname = _extract_bunny_pull_zone_dns_target_hostname(bunny_zone)
    if request_ssl:
        _ensure_bunny_pull_zone_auto_ssl_enabled(zone_id=zone_id)

    domain_results: list[dict[str, Any]] = []
    for hostname in normalized_server_names:
        try:
            dns_record = namecheap_dns_service.upsert_cname_record(
                hostname=hostname,
                target_hostname=dns_target_hostname,
            )
        except namecheap_dns_service.NamecheapDnsError as exc:
            raise DeployError(str(exc)) from exc

        hostname_result = _ensure_bunny_pull_zone_hostname(zone_id=zone_id, hostname=hostname)
        certificate_result: dict[str, Any] | None = None
        ssl_status = "pending_publish"
        if request_ssl:
            certificate_result = _request_bunny_pull_zone_certificate(zone_id=zone_id, hostname=hostname)
            ssl_status = "requested"
        domain_results.append(
            {
                "hostname": hostname,
                "dns": dns_record,
                "bunnyHostname": hostname_result,
                "ssl": {
                    "provider": "bunny",
                    "status": ssl_status,
                    "certificateRequest": certificate_result,
                },
            }
        )

    refreshed_zone = _get_bunny_pull_zone(zone_id=zone_id)
    return {
        "dnsTargetHostname": dns_target_hostname,
        "domains": domain_results,
        "pullZoneHostnames": _extract_bunny_pull_zone_hostname_values(refreshed_zone),
    }


def _resolve_bunny_pull_zone_origin_url(
    *,
    requested_origin_ip: Any,
    workload_port: int | None = None,
) -> str:
    requested = str(requested_origin_ip or "").strip()
    configured_default = str(settings.BUNNY_PULLZONE_ORIGIN_IP or "").strip()
    origin_input = requested or configured_default
    resolved_port: int | None = None
    if workload_port is not None:
        resolved_port = _coerce_service_port(raw_port=workload_port, context="Workload")

    if not origin_input:
        raise DeployError(
            "Bunny pull zone origin IP is required. "
            "Set deploy.bunnyPullZoneOriginIp or BUNNY_PULLZONE_ORIGIN_IP."
        )

    if origin_input.startswith(("http://", "https://")):
        parsed = urlsplit(origin_input)
        if not parsed.scheme or not parsed.netloc:
            raise DeployError(
                "Bunny pull zone origin URL is invalid. Expected http(s)://<host>."
            )
        return origin_input.rstrip("/")

    if " " in origin_input or "/" in origin_input:
        raise DeployError(
            "Bunny pull zone origin must be a bare host/IP or a full http(s) URL."
        )
    if resolved_port is not None and ":" not in origin_input:
        return f"http://{origin_input}:{resolved_port}"
    return f"http://{origin_input}"


def _extract_bunny_pull_zone_access_urls(zone: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for value in _extract_bunny_pull_zone_hostname_values(zone):
        urls.append(f"https://{value}/")
    return _normalize_access_urls(urls)


def _resolve_bunny_origin_context_for_workload(
    *,
    workload: dict[str, Any],
    workload_name: str,
    instance_name: str | None,
    resolve_port_from_latest_spec: bool,
    require_port_when_no_domains: bool,
) -> tuple[list[str], int | None, str | None]:
    server_names = _extract_workload_server_names(
        workload=workload,
        context=f"Workload '{workload_name}'",
    )
    workload_port = _extract_primary_service_port(
        workload=workload,
        context=f"Workload '{workload_name}'",
    )
    workload_port_source: str | None = "plan" if workload_port is not None else None

    if workload_port is None and not server_names and resolve_port_from_latest_spec:
        try:
            workload_port = _workload_port_from_latest_spec(
                workload_name=workload_name,
                instance_name=instance_name,
            )
            workload_port_source = "spec"
        except DeployError as exc:
            if require_port_when_no_domains:
                raise DeployError(
                    f"Workload '{workload_name}' has no server_names and no assigned service port "
                    "after apply; cannot build Bunny pull zone origin URL."
                ) from exc

    if workload_port is None and not server_names and require_port_when_no_domains:
        raise DeployError(
            f"Workload '{workload_name}' has no server_names and no assigned service port; "
            "cannot build Bunny pull zone origin URL."
        )

    return server_names, workload_port, workload_port_source


def _ensure_bunny_pull_zone(*, org_id: str, origin_url: str) -> dict[str, Any]:
    zone_name = _build_bunny_pull_zone_name(org_id=org_id)
    existing_zone = _find_bunny_pull_zone_by_name(zone_name=zone_name)

    zone: dict[str, Any]
    if existing_zone is None:
        created = _bunny_api_request(
            method="POST",
            path="/pullzone",
            payload={"Name": zone_name, "OriginUrl": origin_url},
        )
        if not isinstance(created, dict):
            raise DeployError("Bunny create pull zone response must be an object.")
        zone = created
    else:
        existing_zone_id = _coerce_bunny_pull_zone_id(zone=existing_zone)
        current_origin = str(existing_zone.get("OriginUrl") or "").strip()
        if current_origin != origin_url:
            updated = _bunny_api_request(
                method="POST",
                path=f"/pullzone/{existing_zone_id}",
                payload={"OriginUrl": origin_url},
            )
            if not isinstance(updated, dict):
                raise DeployError("Bunny update pull zone response must be an object.")
            zone = updated
        else:
            zone = existing_zone

    if not isinstance(zone.get("Hostnames"), list):
        zone_id = _coerce_bunny_pull_zone_id(zone=zone)
        return _get_bunny_pull_zone(zone_id=zone_id)
    return zone


def _load_workload_from_plan(
    *,
    workload_name: str,
    plan_path: str | None,
    instance_name: str | None,
) -> tuple[dict[str, Any], str]:
    name = (workload_name or "").strip()
    if not name:
        raise DeployError("workload_name is required.")

    base_plan_path = _assert_under_cloudhand(Path(plan_path)) if plan_path else _find_latest_plan()
    if not base_plan_path or not base_plan_path.exists():
        raise DeployError("No plan found.")

    try:
        plan = json.loads(base_plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec") or {}
    instances = new_spec.get("instances") or []
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    matches: list[dict[str, Any]] = []
    for inst in instances:
        if instance_name and inst.get("name") != instance_name:
            continue
        workloads = inst.get("workloads") or []
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            if (workload.get("name") or "").strip() != name:
                continue
            matches.append(workload)

    if not matches:
        raise DeployError(f"No workload named '{name}' found in plan.")
    if len(matches) > 1 and not (instance_name or "").strip():
        raise DeployError(
            f"Multiple workloads named '{name}' found in plan. Specify instance_name."
        )
    return matches[0], str(base_plan_path)


def configure_bunny_pull_zone_for_workload(
    *,
    org_id: str,
    workload_name: str,
    plan_path: str | None,
    instance_name: str | None,
    requested_origin_ip: str | None = None,
    server_names: list[str] | None = None,
) -> dict[str, Any]:
    workload, resolved_plan_path = _load_workload_from_plan(
        workload_name=workload_name,
        plan_path=plan_path,
        instance_name=instance_name,
    )

    source_type = str(workload.get("source_type") or "").strip().lower()
    if source_type != "funnel_artifact":
        raise DeployError(
            "Bunny pull zone provisioning from deploy domain save requires source_type 'funnel_artifact'."
        )

    workload_server_names, workload_port, workload_port_source = _resolve_bunny_origin_context_for_workload(
        workload=workload,
        workload_name=workload_name,
        instance_name=instance_name,
        resolve_port_from_latest_spec=False,
        require_port_when_no_domains=False,
    )
    if server_names is not None:
        workload_server_names = _normalize_workload_server_names(server_names=server_names)
    port_pending = bool(not workload_server_names and workload_port is None)
    if port_pending:
        workload_port_source = "pending"

    origin_url = _resolve_bunny_pull_zone_origin_url(
        requested_origin_ip=requested_origin_ip,
        workload_port=workload_port,
    )
    bunny_zone = _ensure_bunny_pull_zone(
        org_id=org_id,
        origin_url=origin_url,
    )
    domain_provisioning = _provision_bunny_custom_domains(
        bunny_zone=bunny_zone,
        server_names=workload_server_names,
        request_ssl=False,
    )

    zone_for_access_urls = dict(bunny_zone)
    provisioned_hostnames = domain_provisioning.get("pullZoneHostnames")
    if isinstance(provisioned_hostnames, list):
        zone_for_access_urls["Hostnames"] = [
            {"Value": value}
            for value in provisioned_hostnames
            if isinstance(value, str)
        ]
    bunny_access_urls = _extract_bunny_pull_zone_access_urls(zone_for_access_urls)
    return {
        "provider": "bunny",
        "plan_path": resolved_plan_path,
        "pull_zone": {
            "id": bunny_zone.get("Id"),
            "name": bunny_zone.get("Name"),
            "originUrl": bunny_zone.get("OriginUrl"),
            "accessUrls": bunny_access_urls,
            "workloadPort": workload_port,
            "workloadPortSource": workload_port_source,
            "workloadPortPending": port_pending,
            "dnsTargetHostname": domain_provisioning.get("dnsTargetHostname"),
            "domainProvisioning": domain_provisioning.get("domains"),
        },
    }


def _reconcile_bunny_pull_zone_for_published_workload(
    *,
    org_id: str,
    workload_name: str,
    plan_path: str | None,
    instance_name: str | None,
    requested_origin_ip: str | None,
    require_port_when_no_domains: bool,
    server_names: list[str] | None = None,
) -> dict[str, Any]:
    workload, resolved_plan_path = _load_workload_from_plan(
        workload_name=workload_name,
        plan_path=plan_path,
        instance_name=instance_name,
    )

    source_type = str(workload.get("source_type") or "").strip().lower()
    if source_type != "funnel_artifact":
        raise DeployError(
            "Bunny pull zone provisioning from publish requires source_type 'funnel_artifact'."
        )

    workload_server_names, workload_port, workload_port_source = _resolve_bunny_origin_context_for_workload(
        workload=workload,
        workload_name=workload_name,
        instance_name=instance_name,
        resolve_port_from_latest_spec=True,
        require_port_when_no_domains=require_port_when_no_domains,
    )
    if server_names is not None:
        workload_server_names = _normalize_workload_server_names(server_names=server_names)

    origin_url = _resolve_bunny_pull_zone_origin_url(
        requested_origin_ip=requested_origin_ip,
        workload_port=workload_port,
    )
    bunny_zone = _ensure_bunny_pull_zone(
        org_id=org_id,
        origin_url=origin_url,
    )
    domain_provisioning = _provision_bunny_custom_domains(
        bunny_zone=bunny_zone,
        server_names=workload_server_names,
        request_ssl=True,
    )

    zone_for_access_urls = dict(bunny_zone)
    provisioned_hostnames = domain_provisioning.get("pullZoneHostnames")
    if isinstance(provisioned_hostnames, list):
        zone_for_access_urls["Hostnames"] = [
            {"Value": value}
            for value in provisioned_hostnames
            if isinstance(value, str)
        ]
    bunny_access_urls = _extract_bunny_pull_zone_access_urls(zone_for_access_urls)
    return {
        "provider": "bunny",
        "plan_path": resolved_plan_path,
        "pull_zone": {
            "id": bunny_zone.get("Id"),
            "name": bunny_zone.get("Name"),
            "originUrl": bunny_zone.get("OriginUrl"),
            "accessUrls": bunny_access_urls,
            "workloadPort": workload_port,
            "workloadPortSource": workload_port_source,
            "workloadPortPending": bool(not workload_server_names and workload_port is None),
            "dnsTargetHostname": domain_provisioning.get("dnsTargetHostname"),
            "domainProvisioning": domain_provisioning.get("domains"),
        },
    }


def _latest_spec_path() -> Path:
    return _cloudhand_dir() / "spec.json"


def _workload_port_from_latest_spec(*, workload_name: str, instance_name: str | None) -> int:
    spec_path = _latest_spec_path()
    if not spec_path.exists():
        raise DeployError(
            "Cloudhand spec.json was not found after apply; cannot determine deployed workload port."
        )

    try:
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read Cloudhand spec.json: {exc}") from exc

    if isinstance(payload.get("new_spec"), dict):
        new_spec = payload["new_spec"]
    elif isinstance(payload, dict):
        new_spec = payload
    else:
        raise DeployError("Cloudhand spec.json is invalid (expected JSON object).")

    instances = new_spec.get("instances")
    if not isinstance(instances, list):
        raise DeployError("Cloudhand spec.json is invalid (instances must be a list).")

    target_instance_name = (instance_name or "").strip()
    candidate_instances: list[dict[str, Any]] = []
    if target_instance_name:
        for inst in instances:
            if isinstance(inst, dict) and str(inst.get("name") or "").strip() == target_instance_name:
                candidate_instances.append(inst)
        if not candidate_instances:
            raise DeployError(
                f"Instance '{target_instance_name}' was not found in Cloudhand spec.json."
            )
    else:
        candidate_instances = [inst for inst in instances if isinstance(inst, dict)]

    matches: list[int] = []
    for inst in candidate_instances:
        workloads = inst.get("workloads")
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            if str(workload.get("name") or "").strip() != workload_name:
                continue
            service_cfg = workload.get("service_config")
            if not isinstance(service_cfg, dict):
                raise DeployError(
                    f"Workload '{workload_name}' has no valid service_config in Cloudhand spec.json."
                )
            ports = service_cfg.get("ports")
            if not isinstance(ports, list) or not ports:
                raise DeployError(
                    f"Workload '{workload_name}' has no assigned ports in Cloudhand spec.json."
                )
            try:
                first_port = int(ports[0])
            except Exception as exc:
                raise DeployError(
                    f"Workload '{workload_name}' has an invalid port in Cloudhand spec.json."
                ) from exc
            matches.append(first_port)

    if not matches:
        raise DeployError(
            f"Workload '{workload_name}' was not found in Cloudhand spec.json."
        )
    if len(matches) > 1 and not target_instance_name:
        raise DeployError(
            f"Workload '{workload_name}' appears in multiple instances; provide instance_name."
        )
    return matches[0]


def _infer_external_access_urls(
    *,
    server_ips: dict[str, Any],
    workload_name: str,
    instance_name: str | None,
) -> list[str]:
    if not isinstance(server_ips, dict) or not server_ips:
        raise DeployError("Terraform outputs did not include server IPs for external access URL generation.")

    port = _workload_port_from_latest_spec(workload_name=workload_name, instance_name=instance_name)
    urls: list[str] = []
    for value in server_ips.values():
        ip = str(value or "").strip()
        if not ip:
            continue
        if port == 80:
            urls.append(f"http://{ip}/")
        else:
            urls.append(f"http://{ip}:{port}/")

    resolved = _normalize_access_urls(urls)
    if not resolved:
        raise DeployError("External access URL generation failed because no valid server IPs were available.")
    return resolved


def _summarize_apply_result(result: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    rc = int(result.get("returncode", 1))
    summary: dict[str, Any] = {
        "returncode": rc,
        "plan_path": result.get("plan_path"),
        "materialized_plan_path": result.get("materialized_plan_path"),
        "server_ips": result.get("server_ips"),
        "live_url": result.get("live_url"),
    }
    logs = result.get("logs")
    if isinstance(logs, str) and logs:
        summary["logs_tail"] = logs[-_DEPLOY_JOB_LOG_TAIL_CHARS:]
    return rc, summary


async def _run_apply_plan_job(job_id: str) -> None:
    job = _read_job(job_id)
    path = _job_path(job_id)
    plan_path = str(job.get("plan_path") or "").strip()
    if not plan_path:
        job["status"] = "failed"
        job["error"] = "Job is missing plan_path."
        job["finished_at"] = _utc_now_iso()
        _write_json_atomic(path, job)
        return

    job["status"] = "running"
    job["started_at"] = _utc_now_iso()
    _write_json_atomic(path, job)

    try:
        result = await apply_plan(plan_path=plan_path)
        rc, summary = _summarize_apply_result(result)

        access_urls = _normalize_access_urls(job.get("access_urls"))
        job["result"] = summary
        job["access_urls"] = access_urls
        if rc == 0:
            job["status"] = "succeeded"
            job["error"] = None
        else:
            job["status"] = "failed"
            job["error"] = f"Apply failed with return code {rc}."
    except DeployError as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        job["status"] = "failed"
        job["error"] = f"Unexpected deploy failure: {exc}"

    job["finished_at"] = _utc_now_iso()
    _write_json_atomic(path, job)


async def _run_funnel_publish_job(job_id: str) -> None:
    from app.db.base import SessionLocal
    from app.db.repositories.org_deploy_domains import OrgDeployDomainsRepository
    from app.services.funnels import publish_funnel

    job = _read_publish_job(job_id)
    path = _publish_job_path(job_id)
    job["status"] = "running"
    job["started_at"] = _utc_now_iso()
    _write_json_atomic(path, job)

    org_id = str(job.get("org_id") or "").strip()
    user_id = str(job.get("user_id") or "").strip()
    funnel_id = str(job.get("funnel_id") or "").strip()
    deploy_request = job.get("deploy_request")
    result_payload: dict[str, Any] = {}
    access_urls = _normalize_access_urls(job.get("access_urls"))

    if not org_id or not user_id or not funnel_id:
        job["status"] = "failed"
        job["error"] = "Publish job is missing org_id, user_id, or funnel_id."
        job["finished_at"] = _utc_now_iso()
        _write_json_atomic(path, job)
        return

    try:
        session = SessionLocal()
        try:
            publication = publish_funnel(session=session, org_id=org_id, user_id=user_id, funnel_id=funnel_id)
            result_payload["publicationId"] = str(publication.id)

            if deploy_request is not None:
                if not isinstance(deploy_request, dict):
                    raise DeployError("Invalid publish deploy request payload.")

                workload_patch = deploy_request.get("workload_patch")
                if not isinstance(workload_patch, dict):
                    raise DeployError("Publish deploy request is missing workload_patch.")

                workload_patch = hydrate_funnel_artifact_workload_patch(
                    session=session,
                    org_id=org_id,
                    funnel_id=funnel_id,
                    publication_id=str(publication.id),
                    workload_patch=workload_patch,
                    created_by_user_id=user_id,
                )

                hydrated_source_ref = workload_patch.get("source_ref")
                if isinstance(hydrated_source_ref, dict):
                    artifact_id = str(hydrated_source_ref.get("artifact_id") or "").strip()
                    artifact_version = hydrated_source_ref.get("artifact_version")
                    client_id = str(hydrated_source_ref.get("client_id") or "").strip()
                    if not artifact_id:
                        raise DeployError(
                            "Hydrated funnel deploy workload is missing source_ref.artifact_id."
                        )
                    runtime_artifact_payload: dict[str, Any] = {
                        "id": artifact_id,
                        "clientId": client_id,
                    }
                    if isinstance(artifact_version, int):
                        runtime_artifact_payload["version"] = artifact_version
                    result_payload["runtimeArtifact"] = runtime_artifact_payload

                plan_resolution = ensure_plan_for_funnel_publish_workload(
                    workload_patch=workload_patch,
                    plan_path=deploy_request.get("plan_path"),
                    instance_name=deploy_request.get("instance_name"),
                )

                patch_result = patch_workload_in_plan(
                    org_id=org_id,
                    workload_patch=workload_patch,
                    plan_path=plan_resolution["plan_path"],
                    instance_name=deploy_request.get("instance_name"),
                    create_if_missing=bool(deploy_request.get("create_if_missing", True)),
                    in_place=bool(deploy_request.get("in_place", False)),
                )
                deploy_response: dict[str, Any] = {"patch": patch_result}
                if plan_resolution.get("bootstrapped"):
                    deploy_response["bootstrap"] = {
                        "created": True,
                        "plan_path": plan_resolution["plan_path"],
                    }
                access_urls = _normalize_access_urls(deploy_request.get("access_urls"))

                apply_plan_enabled = bool(deploy_request.get("apply_plan", True))
                if apply_plan_enabled:
                    apply_result = await apply_plan(plan_path=patch_result["updated_plan_path"])
                    return_code, summary = _summarize_apply_result(apply_result)
                    deploy_response["apply"] = summary
                    if return_code != 0:
                        result_payload["deploy"] = deploy_response
                        job["result"] = result_payload
                        job["access_urls"] = access_urls
                        job["status"] = "failed"
                        job["error"] = f"Funnel published but deploy apply failed with return code {return_code}."
                        job["finished_at"] = _utc_now_iso()
                        _write_json_atomic(path, job)
                        return
                    if not access_urls:
                        workload_name = str(workload_patch.get("name") or "").strip()
                        if not workload_name:
                            raise DeployError("Publish deploy workload patch is missing workload name.")
                        access_urls = _infer_external_access_urls(
                            server_ips=summary.get("server_ips") or {},
                            workload_name=workload_name,
                            instance_name=deploy_request.get("instance_name"),
                        )
                    summary["access_urls"] = access_urls
                    deploy_response["apply"] = summary

                if bool(deploy_request.get("bunny_pull_zone", False)):
                    workload_name = str(workload_patch.get("name") or "").strip()
                    if not workload_name:
                        raise DeployError("Publish deploy workload patch is missing workload name.")
                    org_server_names = OrgDeployDomainsRepository(session).list_hostnames(org_id=org_id)
                    bunny_config = _reconcile_bunny_pull_zone_for_published_workload(
                        org_id=org_id,
                        workload_name=workload_name,
                        plan_path=patch_result.get("updated_plan_path"),
                        instance_name=deploy_request.get("instance_name"),
                        requested_origin_ip=deploy_request.get("bunny_pull_zone_origin_ip"),
                        require_port_when_no_domains=apply_plan_enabled,
                        server_names=org_server_names,
                    )
                    bunny_pull_zone_payload = bunny_config.get("pull_zone")
                    if isinstance(bunny_pull_zone_payload, dict) and isinstance(
                        bunny_pull_zone_payload.get("accessUrls"), list
                    ):
                        bunny_access_urls = bunny_pull_zone_payload.get("accessUrls")
                    else:
                        bunny_access_urls = []
                    access_urls = _normalize_access_urls(access_urls + bunny_access_urls)
                    deploy_response["cdn"] = bunny_config

                result_payload["deploy"] = deploy_response
        finally:
            session.close()

        job["result"] = result_payload
        job["access_urls"] = access_urls
        job["status"] = "succeeded"
        job["error"] = None
    except ValueError as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        if result_payload:
            job["result"] = result_payload
        job["access_urls"] = access_urls
    except DeployError as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        if result_payload:
            job["result"] = result_payload
        job["access_urls"] = access_urls
    except Exception as exc:  # pragma: no cover - defensive
        job["status"] = "failed"
        job["error"] = f"Unexpected publish/deploy failure: {exc}"
        if result_payload:
            job["result"] = result_payload
        job["access_urls"] = access_urls

    job["finished_at"] = _utc_now_iso()
    _write_json_atomic(path, job)


def start_apply_plan_job(
    *,
    plan_path: str | None = None,
    access_urls: list[str] | None = None,
) -> dict[str, Any]:
    if plan_path:
        plan_file = _assert_under_cloudhand(Path(plan_path))
    else:
        plan_file = _find_latest_plan()
    if not plan_file or not plan_file.exists():
        raise DeployError("No plan found.")

    job_id = str(uuid4())
    job = {
        "id": job_id,
        "status": "queued",
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "plan_path": str(plan_file),
        "access_urls": _normalize_access_urls(access_urls),
        "result": None,
        "error": None,
    }
    _write_json_atomic(_job_path(job_id), job)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        raise DeployError("No running event loop available to start async deploy job.") from exc

    loop.create_task(_run_apply_plan_job(job_id))
    return job


def get_apply_plan_job(*, job_id: str) -> dict[str, Any]:
    return _read_job(job_id)


def start_funnel_publish_job(
    *,
    org_id: str,
    user_id: str,
    funnel_id: str,
    deploy_request: dict[str, Any] | None,
    access_urls: list[str] | None = None,
) -> dict[str, Any]:
    safe_org_id = (org_id or "").strip()
    safe_user_id = (user_id or "").strip()
    safe_funnel_id = (funnel_id or "").strip()
    if not safe_org_id:
        raise DeployError("org_id is required.")
    if not safe_user_id:
        raise DeployError("user_id is required.")
    if not safe_funnel_id:
        raise DeployError("funnel_id is required.")

    if deploy_request is not None and not isinstance(deploy_request, dict):
        raise DeployError("deploy_request must be an object when provided.")

    job_id = str(uuid4())
    job = {
        "id": job_id,
        "status": "queued",
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "org_id": safe_org_id,
        "user_id": safe_user_id,
        "funnel_id": safe_funnel_id,
        "deploy_request": deploy_request,
        "access_urls": _normalize_access_urls(access_urls),
        "result": None,
        "error": None,
    }
    _write_json_atomic(_publish_job_path(job_id), job)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        raise DeployError("No running event loop available to start async publish job.") from exc

    loop.create_task(_run_funnel_publish_job(job_id))
    return job


def get_funnel_publish_job(*, job_id: str, org_id: str, funnel_id: str) -> dict[str, Any]:
    job = _read_publish_job(job_id)
    if str(job.get("org_id") or "") != (org_id or "").strip():
        raise DeployError(f"Publish job '{job_id}' not found.")
    if str(job.get("funnel_id") or "") != (funnel_id or "").strip():
        raise DeployError(f"Publish job '{job_id}' not found.")
    return job
