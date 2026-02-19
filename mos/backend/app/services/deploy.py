from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.config import settings


class DeployError(RuntimeError):
    pass


_DEPLOY_JOB_LOG_TAIL_CHARS = 12000


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
    plans = sorted(ch_dir.glob("plan-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
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
                f"Product route slug '{product_slug}' is used by multiple products. Set unique product handles."
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

    return {
        "meta": {
            "clientId": str(client_id),
            "updatedFromFunnelId": updated_from_funnel_id,
            "updatedFromPublicationId": updated_from_publication_id,
        },
        "products": products_payload,
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

        try:
            validated = ApplicationSpec.model_validate(workload_patch)
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
            if source_type != "funnel_artifact":
                continue
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
                raise DeployError(
                    f"Workload '{workload.get('name')}' is missing source_ref.artifact_id while artifact payload is empty."
                )
            source_ref["artifact"] = _load_funnel_runtime_artifact_payload_for_apply(artifact_id=artifact_id)
            workload["source_ref"] = source_ref
            has_changes = True

    if not has_changes:
        return plan_file

    materialized_path = _cloudhand_dir() / f"plan-apply-{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%SZ')}-{uuid4().hex[:8]}.json"
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
                    if artifact_id:
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
