from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from temporalio import activity

from app.config import settings
from app.db.base import session_scope
from app.db.enums import WorkflowStatusEnum
from app.db.repositories.animated_templates import AnimatedTemplatesRepository
from app.db.repositories.swipes import CompanySwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.services.animated_templates.media import (
    extract_animated_source_metadata,
    normalize_media_content_type,
)
from app.services.animated_templates.renderer import render_source_passthrough
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage


_ANIMATED_TEMPLATE_MAX_BYTES = 50 * 1024 * 1024
_ANIMATED_IMAGE_TYPES = {"image/gif", "image/webp"}


def _optional_content_type(value: str | None) -> str:
    try:
        return normalize_media_content_type(value)
    except RuntimeError:
        return ""


def _max_source_bytes() -> int:
    return int(getattr(settings, "ANIMATED_TEMPLATE_MAX_SOURCE_BYTES", None) or _ANIMATED_TEMPLATE_MAX_BYTES)


def _source_download_timeout_seconds() -> float:
    return float(getattr(settings, "ANIMATED_TEMPLATE_SOURCE_DOWNLOAD_TIMEOUT_SECONDS", None) or 30.0)


def _download_source_url(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"Animated template sourceUrl must be http or https. sourceUrl={url}")

    max_bytes = _max_source_bytes()
    with httpx.Client(follow_redirects=True, timeout=_source_download_timeout_seconds()) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = normalize_media_content_type(response.headers.get("content-type"))
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes(8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(
                        "Animated template source media exceeds the configured byte limit. "
                        f"size_bytes>{max_bytes}"
                    )
                chunks.append(chunk)
            return b"".join(chunks), content_type


def _pick_company_swipe_media(media_items: list[Any], company_swipe_media_id: str | None) -> Any:
    if company_swipe_media_id:
        for media in media_items:
            if str(getattr(media, "id", "") or "") == company_swipe_media_id:
                return media
        raise RuntimeError(f"Company swipe media not found: {company_swipe_media_id}")

    if len(media_items) == 1:
        return media_items[0]

    animated_candidates = [
        media
        for media in media_items
        if _optional_content_type(getattr(media, "mime_type", None)) in _ANIMATED_IMAGE_TYPES
    ]
    if len(animated_candidates) == 1:
        return animated_candidates[0]
    raise RuntimeError(
        "companySwipeMediaId is required when a company swipe has multiple media items "
        "and exactly one animated GIF/WebP candidate cannot be identified from metadata."
    )


def _load_company_swipe_media_bytes(media: Any) -> tuple[bytes, str, str | None]:
    media_mime_type = normalize_media_content_type(getattr(media, "mime_type", None))
    path_value = str(getattr(media, "path", "") or "").strip() or None

    for candidate in (
        str(getattr(media, "download_url", "") or "").strip() or None,
        str(getattr(media, "url", "") or "").strip() or None,
        path_value if path_value and urlparse(path_value).scheme in {"http", "https"} else None,
    ):
        if candidate:
            data, downloaded_content_type = _download_source_url(candidate)
            if downloaded_content_type != media_mime_type:
                raise RuntimeError(
                    "Company swipe media content type does not match its stored metadata. "
                    f"stored={media_mime_type}, downloaded={downloaded_content_type}"
                )
            return data, media_mime_type, candidate

    if not path_value:
        raise RuntimeError("Company swipe media is missing a readable URL or storage path.")

    storage = MediaStorage()
    data, stored_content_type = storage.download_bytes(key=path_value)
    content_type = normalize_media_content_type(stored_content_type or media_mime_type)
    if content_type != media_mime_type:
        raise RuntimeError(
            "Company swipe media storage content type does not match its stored metadata. "
            f"stored={media_mime_type}, downloaded={content_type}"
        )
    return data, content_type, None


def _resolve_source_media(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params.get("org_id") or "").strip()
    company_swipe_id = str(params.get("company_swipe_id") or "").strip() or None
    company_swipe_media_id = str(params.get("company_swipe_media_id") or "").strip() or None
    source_url = str(params.get("source_url") or "").strip() or None
    source_label = str(params.get("source_label") or "").strip() or None

    if not org_id:
        raise RuntimeError("org_id is required for animated template source analysis.")
    if bool(company_swipe_id) == bool(source_url):
        raise RuntimeError("Provide exactly one of company_swipe_id or source_url.")
    if company_swipe_media_id and not company_swipe_id:
        raise RuntimeError("company_swipe_media_id requires company_swipe_id.")

    if source_url:
        content, content_type = _download_source_url(source_url)
        return {
            "sourceKind": "direct_url",
            "sourceUrl": source_url,
            "sourceLabel": source_label,
            "content": content,
            "contentType": content_type,
        }

    with session_scope() as session:
        repo = CompanySwipesRepository(session)
        swipe = repo.get_asset(org_id=org_id, swipe_id=company_swipe_id or "")
        if swipe is None:
            raise RuntimeError(f"Company swipe not found: {company_swipe_id}")
        media_items = repo.list_media(org_id=org_id, swipe_asset_id=str(swipe.id))
        if not media_items:
            raise RuntimeError(f"Company swipe has no media: {company_swipe_id}")
        media = _pick_company_swipe_media(media_items, company_swipe_media_id)
        content, content_type, resolved_url = _load_company_swipe_media_bytes(media)
        return {
            "sourceKind": "company_swipe",
            "companySwipeId": str(swipe.id),
            "companySwipeMediaId": str(media.id),
            "sourceUrl": resolved_url,
            "sourceLabel": source_label or getattr(swipe, "title", None),
            "content": content,
            "contentType": content_type,
        }


def _log_workflow_activity(
    *,
    workflow_run_id: str | None,
    step: str,
    status: str,
    payload_in: dict[str, Any] | None = None,
    payload_out: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    if not workflow_run_id:
        return
    with session_scope() as session:
        WorkflowsRepository(session).log_activity(
            workflow_run_id=workflow_run_id,
            step=step,
            status=status,
            payload_in=payload_in,
            payload_out=payload_out,
            error=error,
        )


def _mark_render_run_failed(
    *,
    org_id: str,
    run_id: str,
    workflow_run_id: str | None,
    error_code: str,
    error_message: str,
) -> None:
    with session_scope() as session:
        repo = AnimatedTemplatesRepository(session)
        run = repo.get_run(org_id=org_id, run_id=run_id)
        if run is None:
            raise RuntimeError(f"Animated template run not found: {run_id}")
        repo.mark_run_failed(run=run, error_code=error_code, error_message=error_message)
        if workflow_run_id:
            WorkflowsRepository(session).set_status(
                org_id=org_id,
                workflow_run_id=workflow_run_id,
                status=WorkflowStatusEnum.failed,
                finished_at=run.completed_at,
            )
        session.commit()


def _source_params_from_manifest(manifest: Any) -> dict[str, Any]:
    return {
        "org_id": str(manifest.org_id),
        "company_swipe_id": str(manifest.company_swipe_id) if manifest.company_swipe_id else None,
        "company_swipe_media_id": (
            str(manifest.company_swipe_media_id) if manifest.company_swipe_media_id else None
        ),
        "source_url": manifest.source_url,
        "source_label": manifest.source_label,
    }


@activity.defn(name="swipes.analyze_animated_template_source")
def analyze_animated_template_source_activity(params: dict[str, Any]) -> dict[str, Any]:
    workflow_run_id = str(params.get("workflow_run_id") or "").strip() or None
    safe_params = {key: value for key, value in params.items() if key != "content"}
    _log_workflow_activity(
        workflow_run_id=workflow_run_id,
        step="animated_template_source_metadata",
        status="started",
        payload_in=safe_params,
    )
    try:
        source = _resolve_source_media(params)
        metadata = extract_animated_source_metadata(
            content=source["content"],
            content_type=source["contentType"],
        )
        result = {
            "analysisStatus": "metadata_extracted",
            "analyzerVersion": str(params.get("analyzer_version") or "animated-template-analyzer-v1"),
            "source": {
                key: value
                for key, value in source.items()
                if key not in {"content", "contentType"}
            },
            "metadata": metadata,
            "nextAction": {
                "code": "LAYER_ANALYSIS_NOT_IMPLEMENTED",
                "message": (
                    "Source metadata was extracted. Layer detection and manifest construction "
                    "must run before a renderable manifest can be created."
                ),
            },
        }
        _log_workflow_activity(
            workflow_run_id=workflow_run_id,
            step="animated_template_source_metadata",
            status="completed",
            payload_out=result,
        )
        return result
    except Exception as exc:
        _log_workflow_activity(
            workflow_run_id=workflow_run_id,
            step="animated_template_source_metadata",
            status="failed",
            error=str(exc),
        )
        raise


@activity.defn(name="swipes.render_animated_template")
def render_animated_template_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params.get("org_id") or "").strip()
    run_id = str(params.get("run_id") or "").strip()
    manifest_id = str(params.get("manifest_id") or "").strip()
    workflow_run_id = str(params.get("workflow_run_id") or "").strip() or None
    if not org_id:
        raise RuntimeError("org_id is required for animated template rendering.")
    if not run_id:
        raise RuntimeError("run_id is required for animated template rendering.")
    if not manifest_id:
        raise RuntimeError("manifest_id is required for animated template rendering.")

    with session_scope() as session:
        repo = AnimatedTemplatesRepository(session)
        run = repo.get_run(org_id=org_id, run_id=run_id)
        if run is None:
            raise RuntimeError(f"Animated template run not found: {run_id}")
        manifest = repo.get_manifest(org_id=org_id, manifest_id=manifest_id)
        if manifest is None:
            raise RuntimeError(f"Animated template manifest not found: {manifest_id}")

        render_plan = run.render_plan or {}
        renderer_strategy = str(render_plan.get("rendererStrategy") or "").strip()
        if renderer_strategy != "source_passthrough":
            message = (
                "Animated template rendering is not implemented yet for rendererStrategy="
                f"{renderer_strategy or '[missing]'}. The deterministic compositor must be "
                "implemented before this template can produce assets."
            )
            repo.mark_run_failed(
                run=run,
                error_code="RENDERER_NOT_IMPLEMENTED",
                error_message=message,
            )
            if workflow_run_id:
                WorkflowsRepository(session).set_status(
                    org_id=org_id,
                    workflow_run_id=workflow_run_id,
                    status=WorkflowStatusEnum.failed,
                    finished_at=run.completed_at,
                )
            session.commit()
            raise RuntimeError(message)

        source_params = _source_params_from_manifest(manifest)
        manifest_payload = manifest.manifest
        expected_source_sha256 = manifest.source_sha256
        output_formats = list((run.render_request or {}).get("outputFormats") or ["gif"])

    try:
        source = _resolve_source_media(source_params)
        storage = MediaStorage()
        artifact_ids: list[str] = []
        artifact_payloads: list[dict[str, Any]] = []
        for output_format in output_formats:
            rendered = render_source_passthrough(
                source_content=source["content"],
                source_content_type=source["contentType"],
                manifest=manifest_payload,
                output_format=str(output_format),
                expected_source_sha256=expected_source_sha256,
            )
            storage_key = storage.build_key(
                sha256=rendered.sha256,
                ext=rendered.output_format,
                kind="prev",
            )
            if not storage.object_exists(bucket=storage.bucket, key=storage_key):
                storage.upload_bytes(
                    bucket=storage.bucket,
                    key=storage_key,
                    data=rendered.content,
                    content_type=rendered.content_type,
                    cache_control=IMMUTABLE_CACHE_CONTROL,
                    extra_metadata={"sha256": rendered.sha256},
                )
            artifact_payloads.append(
                {
                    "artifact_kind": f"rendered_{rendered.output_format}",
                    "storage_key": storage_key,
                    "content_type": rendered.content_type,
                    "size_bytes": rendered.size_bytes,
                    "metadata_json": rendered.metadata
                    | {
                        "outputFormat": rendered.output_format,
                        "contentSha256": rendered.sha256,
                    },
                }
            )

        with session_scope() as session:
            repo = AnimatedTemplatesRepository(session)
            run = repo.get_run(org_id=org_id, run_id=run_id)
            if run is None:
                raise RuntimeError(f"Animated template run not found: {run_id}")
            for payload in artifact_payloads:
                artifact = repo.create_artifact(
                    org_id=org_id,
                    manifest_id=manifest_id,
                    run_id=run_id,
                    **payload,
                )
                artifact_ids.append(str(artifact.id))
            repo.mark_run_succeeded(
                run=run,
                output_artifact_ids=artifact_ids,
                cost_actual={"modelCalls": 0, "modelCostUsd": "0.00"},
                qa_report={
                    "status": "passed",
                    "checks": ["source_passthrough_hash_verified"],
                },
            )
            if workflow_run_id:
                WorkflowsRepository(session).set_status(
                    org_id=org_id,
                    workflow_run_id=workflow_run_id,
                    status=WorkflowStatusEnum.completed,
                    finished_at=run.completed_at,
                )
            session.commit()
        return {
            "status": "succeeded",
            "runId": run_id,
            "manifestId": manifest_id,
            "outputArtifactIds": artifact_ids,
            "outputCount": len(artifact_ids),
        }
    except Exception as exc:
        _mark_render_run_failed(
            org_id=org_id,
            run_id=run_id,
            workflow_run_id=workflow_run_id,
            error_code="RENDER_FAILED",
            error_message=str(exc),
        )
        raise
