#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "mos" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import session_scope
from app.services.media_storage import MediaStorage
from app.services.swipe_prompt import load_swipe_to_image_ad_prompt
from app.temporal.activities.swipe_image_ad_activities import (
    _GLOBAL_BLIND_ANGLE_REVEAL_TERMS,
    _build_swipe_copy_stage1_prompt,
    _collect_blind_angle_forbidden_terms,
    _resolve_swipe_copy_asset_type,
)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> Any:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return _safe_str(value)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _slugify(value: str, *, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned:
        cleaned = "item"
    return cleaned[:max_len].rstrip("-._") or "item"


def _basename_from_urlish(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    path = parsed.path if parsed.scheme or parsed.netloc else value.strip()
    name = Path(unquote(path)).name.strip()
    return name or None


def _guess_ext(*, content_type: str | None, preferred_name: str | None = None) -> str:
    if preferred_name and "." in preferred_name:
        ext = preferred_name.rsplit(".", 1)[-1].strip().lower()
        if ext:
            return ext
    guessed = mimetypes.guess_extension(_safe_str(content_type).strip() or "") if content_type else None
    if guessed:
        return guessed.lstrip(".")
    return "bin"


def _relpath(path: Path, *, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _preview(value: str, *, max_chars: int = 180) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1] + "…"


def _html_pre(value: str | None) -> str:
    return html.escape(value or "")


def _html_json(value: Any) -> str:
    return _html_pre(_json_pretty(value))


def _badge(text_value: str, kind: str = "default") -> str:
    return f'<span class="badge badge-{html.escape(kind)}">{html.escape(text_value)}</span>'


def _bool_badge(label: str, value: bool | None) -> str:
    if value is True:
        return _badge(f"{label}: yes", "good")
    if value is False:
        return _badge(f"{label}: no", "warn")
    return _badge(f"{label}: unknown", "muted")


def _load_prompt_template_versions() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    working_text, working_sha = load_swipe_to_image_ad_prompt()
    working_version = {
        "key": "prompts/swipe/swipe_to_image_ad.md",
        "sha256": working_sha,
        "text": working_text,
        "source": "working_copy",
    }
    versions = {working_sha: working_version}

    head_relpath = "mos/backend/app/prompts/swipe/swipe_to_image_ad.md"
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"HEAD:{head_relpath}"],
            capture_output=True,
            text=True,
            check=True,
        )
        head_text = proc.stdout
        if head_text:
            head_sha = _sha256_text(head_text)
            versions.setdefault(
                head_sha,
                {
                    "key": "prompts/swipe/swipe_to_image_ad.md",
                    "sha256": head_sha,
                    "text": head_text,
                    "source": "git_HEAD",
                },
            )
    except Exception:
        pass

    return working_version, versions


def _query_one(session, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    row = session.execute(text(sql), params).mappings().first()
    if row is None:
        raise RuntimeError(f"Query returned no rows: {sql}")
    return dict(row)


def _query_all(session, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in session.execute(text(sql), params).mappings().all()]


def _download_storage_asset(
    *,
    storage: MediaStorage,
    storage_key: str,
    content_type: str | None,
    preferred_name: str,
    target_dir: Path,
    output_root: Path,
) -> dict[str, Any]:
    ext = _guess_ext(content_type=content_type, preferred_name=preferred_name)
    file_name = f"{_slugify(preferred_name, max_len=120)}.{ext}"
    output_path = target_dir / file_name
    final_content_type = content_type
    if not output_path.exists():
        data, downloaded_content_type = storage.download_bytes(key=storage_key)
        final_content_type = downloaded_content_type or content_type
        ext = _guess_ext(content_type=final_content_type, preferred_name=preferred_name)
        file_name = f"{_slugify(preferred_name, max_len=120)}.{ext}"
        output_path = target_dir / file_name
        output_path.write_bytes(data)
    return {
        "path": _relpath(output_path, root=output_root),
        "contentType": final_content_type,
        "sizeBytes": output_path.stat().st_size,
        "storageKey": storage_key,
    }


def _download_url_asset(
    *,
    url: str,
    preferred_name: str,
    target_dir: Path,
    output_root: Path,
) -> dict[str, Any]:
    content_type = None
    ext = _guess_ext(content_type=content_type, preferred_name=preferred_name)
    file_name = f"{_slugify(preferred_name, max_len=120)}.{ext}"
    output_path = target_dir / file_name
    if not output_path.exists():
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("content-type")
        ext = _guess_ext(content_type=content_type, preferred_name=preferred_name)
        file_name = f"{_slugify(preferred_name, max_len=120)}.{ext}"
        output_path = target_dir / file_name
        output_path.write_bytes(response.content)
    return {
        "path": _relpath(output_path, root=output_root),
        "contentType": content_type,
        "sizeBytes": output_path.stat().st_size,
        "url": url,
    }


def _load_campaign_payload(campaign_id: str) -> dict[str, Any]:
    with session_scope() as session:
        campaign = _query_one(
            session,
            """
            SELECT
              c.id::text AS id,
              c.org_id::text AS org_id,
              c.client_id::text AS client_id,
              c.product_id::text AS product_id,
              c.name,
              c.channels,
              c.asset_brief_types,
              c.goal_description,
              c.objective_type,
              c.created_at,
              cl.name AS client_name,
              p.name AS product_name
            FROM campaigns c
            JOIN clients cl ON cl.id = c.client_id
            LEFT JOIN products p ON p.id = c.product_id
            WHERE c.id = :campaign_id
            """,
            {"campaign_id": campaign_id},
        )

        artifacts = _query_all(
            session,
            """
            SELECT
              id::text AS id,
              type::text AS type,
              version,
              created_at,
              data
            FROM artifacts
            WHERE campaign_id = :campaign_id
            ORDER BY created_at ASC, id ASC
            """,
            {"campaign_id": campaign_id},
        )

        assets = _query_all(
            session,
            """
            SELECT
              id::text AS id,
              org_id::text AS org_id,
              client_id::text AS client_id,
              COALESCE(campaign_id::text, '') AS campaign_id,
              COALESCE(product_id::text, '') AS product_id,
              COALESCE(experiment_id::text, '') AS experiment_id,
              COALESCE(asset_brief_artifact_id::text, '') AS asset_brief_artifact_id,
              variant_id,
              source_type::text AS source_type,
              status::text AS status,
              channel_id,
              format,
              created_at,
              storage_key,
              content_type,
              size_bytes,
              width,
              height,
              content,
              ai_metadata
            FROM assets
            WHERE campaign_id = :campaign_id
            ORDER BY created_at ASC, id ASC
            """,
            {"campaign_id": campaign_id},
        )

        creative_specs = _query_all(
            session,
            """
            SELECT
              id::text AS id,
              COALESCE(experiment_id::text, '') AS experiment_id,
              asset_id::text AS asset_id,
              name,
              primary_text,
              headline,
              description,
              call_to_action_type,
              destination_url,
              status,
              metadata,
              created_at,
              updated_at
            FROM meta_creative_specs
            WHERE campaign_id = :campaign_id
            ORDER BY created_at ASC, id ASC
            """,
            {"campaign_id": campaign_id},
        )

        product_ref_ids: list[str] = []
        for asset in assets:
            metadata = _coerce_dict(asset.get("ai_metadata"))
            for ref_id in _coerce_list(metadata.get("swipeProductReferenceLocalAssetIds")):
                clean_ref = _safe_str(ref_id).strip()
                if clean_ref and clean_ref not in product_ref_ids:
                    product_ref_ids.append(clean_ref)

        product_ref_assets: list[dict[str, Any]] = []
        if product_ref_ids:
            product_ref_assets = _query_all(
                session,
                """
                SELECT
                  id::text AS id,
                  storage_key,
                  content_type,
                  size_bytes,
                  width,
                  height,
                  content,
                  ai_metadata,
                  created_at,
                  asset_kind,
                  source_type::text AS source_type
                FROM assets
                WHERE id::text = ANY(:asset_ids)
                ORDER BY created_at ASC, id ASC
                """,
                {"asset_ids": product_ref_ids},
            )

        gemini_store_names: list[str] = []
        for asset in assets:
            metadata = _coerce_dict(asset.get("ai_metadata"))
            for name in _coerce_list(metadata.get("swipeGeminiStoreNames")):
                clean_name = _safe_str(name).strip()
                if clean_name and clean_name not in gemini_store_names:
                    gemini_store_names.append(clean_name)

        gemini_context_files: list[dict[str, Any]] = []
        if gemini_store_names:
            gemini_context_files = _query_all(
                session,
                """
                SELECT
                  id::text AS id,
                  gemini_store_name,
                  gemini_document_name,
                  gemini_file_name,
                  doc_key,
                  doc_title,
                  source_kind,
                  step_key,
                  filename,
                  mime_type,
                  size_bytes,
                  sha256,
                  drive_url,
                  created_at,
                  updated_at
                FROM gemini_context_files
                WHERE org_id = :org_id
                  AND status = 'ready'
                  AND gemini_store_name = ANY(:store_names)
                ORDER BY gemini_store_name ASC, source_kind ASC, doc_key ASC, created_at ASC
                """,
                {
                    "org_id": campaign["org_id"],
                    "store_names": gemini_store_names,
                },
            )

    return {
        "campaign": campaign,
        "artifacts": artifacts,
        "assets": assets,
        "creative_specs": creative_specs,
        "product_ref_assets": product_ref_assets,
        "gemini_context_files": gemini_context_files,
    }


def _index_artifacts(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts_by_id = {artifact["id"]: artifact for artifact in artifacts}

    brief_by_id: dict[str, dict[str, Any]] = {}
    brief_by_artifact_id: dict[str, list[dict[str, Any]]] = {}
    ad_copy_pack_by_artifact_id: dict[str, dict[str, Any]] = {}
    ad_copy_pack_item_by_id: dict[str, dict[str, Any]] = {}
    plan_artifacts: list[dict[str, Any]] = []
    plan_item_by_id: dict[str, dict[str, Any]] = {}

    for artifact in artifacts:
        artifact_type = _safe_str(artifact.get("type")).strip()
        payload = _coerce_dict(artifact.get("data"))
        artifact_id = _safe_str(artifact.get("id")).strip()
        if artifact_type == "asset_brief":
            entries = [entry for entry in _coerce_list(payload.get("asset_briefs")) if isinstance(entry, dict)]
            brief_by_artifact_id[artifact_id] = entries
            for entry in entries:
                brief_id = _safe_str(entry.get("id")).strip()
                if brief_id:
                    brief_by_id[brief_id] = entry
        elif artifact_type == "ad_copy_pack":
            ad_copy_pack_by_artifact_id[artifact_id] = artifact
            for item in _coerce_list(payload.get("copyPacks")):
                if not isinstance(item, dict):
                    continue
                item_id = _safe_str(item.get("id")).strip()
                if item_id:
                    ad_copy_pack_item_by_id[item_id] = {
                        "artifactId": artifact_id,
                        "artifactCreatedAt": artifact.get("created_at"),
                        "artifactPayload": payload,
                        "copyPack": item,
                    }
        elif artifact_type == "creative_generation_plan":
            plan_artifacts.append(artifact)
            for item in _coerce_list(payload.get("items")):
                if not isinstance(item, dict):
                    continue
                item_id = _safe_str(item.get("id")).strip()
                if item_id:
                    plan_item_by_id[item_id] = {
                        "artifactId": artifact_id,
                        "artifactCreatedAt": artifact.get("created_at"),
                        "item": item,
                    }

    return {
        "artifacts_by_id": artifacts_by_id,
        "brief_by_id": brief_by_id,
        "brief_by_artifact_id": brief_by_artifact_id,
        "ad_copy_pack_by_artifact_id": ad_copy_pack_by_artifact_id,
        "ad_copy_pack_item_by_id": ad_copy_pack_item_by_id,
        "plan_artifacts": plan_artifacts,
        "plan_item_by_id": plan_item_by_id,
    }


def _reconstruct_swipe_copy_prompt(
    *,
    brief: dict[str, Any] | None,
    requirement_index: int | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if brief is None:
        return {
            "status": "missing_brief",
            "error": "Asset brief could not be resolved for this asset.",
        }
    if requirement_index is None or requirement_index < 0:
        return {
            "status": "missing_requirement_index",
            "error": "Requirement index is missing for this asset.",
        }

    requirements = _coerce_list(brief.get("requirements"))
    if requirement_index >= len(requirements):
        return {
            "status": "requirement_out_of_range",
            "error": f"Requirement index {requirement_index} is outside brief requirements.",
        }

    requirement = requirements[requirement_index]
    if not isinstance(requirement, dict):
        return {
            "status": "invalid_requirement",
            "error": f"Requirement at index {requirement_index} is not an object.",
        }

    swipe_copy_inputs = _coerce_dict(metadata.get("swipeCopyInputs"))
    ad_image = _coerce_dict(swipe_copy_inputs.get("adImageOrVideo"))
    platform = _safe_str(swipe_copy_inputs.get("platform")).strip()
    destination_type = _safe_str(swipe_copy_inputs.get("destinationPage")).strip()
    swipe_source_label = _safe_str(ad_image.get("sourceLabel") or metadata.get("swipeSourceLabel")).strip()
    swipe_source_url = _safe_str(ad_image.get("sourceUrl") or metadata.get("swipeSourceUrl")).strip()
    swipe_mime_type = _safe_str(ad_image.get("mimeType") or metadata.get("swipePromptImageMimeType")).strip()
    stored_sha = _safe_str(metadata.get("swipeCopyPromptSha256")).strip()
    stored_prompt_text = _safe_str(metadata.get("swipeCopyPromptText")).strip()

    if stored_prompt_text:
        rebuilt_sha = _sha256_text(stored_prompt_text)
        return {
            "status": "ok",
            "storedSha256": stored_sha or None,
            "rebuiltSha256": rebuilt_sha,
            "shaMatch": bool(stored_sha and stored_sha == rebuilt_sha),
            "promptText": stored_prompt_text,
            "source": "stored_prompt_text",
        }

    if not platform:
        return {
            "status": "missing_platform",
            "error": "Swipe copy platform is missing.",
            "storedSha256": stored_sha or None,
        }
    if not destination_type:
        return {
            "status": "missing_destination_type",
            "error": "Swipe copy destination type is missing.",
            "storedSha256": stored_sha or None,
        }
    if not swipe_source_url:
        return {
            "status": "missing_swipe_source_url",
            "error": "Swipe source URL is missing.",
            "storedSha256": stored_sha or None,
        }
    if not swipe_mime_type:
        return {
            "status": "missing_swipe_mime_type",
            "error": "Swipe mime type is missing.",
            "storedSha256": stored_sha or None,
        }

    forbidden_terms = sorted(
        {
            *_GLOBAL_BLIND_ANGLE_REVEAL_TERMS,
            *_collect_blind_angle_forbidden_terms(
                requirement.get("angle") if isinstance(requirement.get("angle"), str) else None,
                requirement.get("hook") if isinstance(requirement.get("hook"), str) else None,
            ),
        },
        key=lambda item: (-len(item), item),
    )
    prompt_text = _build_swipe_copy_stage1_prompt(
        brief=brief,
        requirement_index=requirement_index,
        requirement=requirement,
        platform=platform,
        destination_type=destination_type,
        swipe_asset_type=_resolve_swipe_copy_asset_type(mime_type=swipe_mime_type),
        swipe_mime_type=swipe_mime_type,
        swipe_source_label=swipe_source_label or None,
        swipe_source_url=swipe_source_url,
        forbidden_terms=forbidden_terms,
        retry_feedback=None,
    )
    rebuilt_sha = _sha256_text(prompt_text)
    return {
        "status": "ok",
        "storedSha256": stored_sha or None,
        "rebuiltSha256": rebuilt_sha,
        "shaMatch": bool(stored_sha and stored_sha == rebuilt_sha),
        "promptText": prompt_text,
        "source": "rebuilt_legacy_prompt",
    }


def export_campaign_forensic_review(*, campaign_id: str, output_root: Path) -> Path:
    bundle = _load_campaign_payload(campaign_id)
    artifact_index = _index_artifacts(bundle["artifacts"])
    campaign = bundle["campaign"]
    assets = bundle["assets"]
    creative_specs = bundle["creative_specs"]
    product_ref_assets = bundle["product_ref_assets"]
    gemini_context_files = bundle["gemini_context_files"]

    output_dir_name = f"{campaign_id}-{_slugify(_safe_str(campaign.get('name')), max_len=72)}"
    output_dir = output_root / output_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)

    media_dir = output_dir / "media"
    generated_dir = media_dir / "generated"
    swipe_dir = media_dir / "source-swipes"
    product_ref_dir = media_dir / "product-refs"
    generated_dir.mkdir(parents=True, exist_ok=True)
    swipe_dir.mkdir(parents=True, exist_ok=True)
    product_ref_dir.mkdir(parents=True, exist_ok=True)

    storage = MediaStorage()
    prompt_template_working, prompt_template_versions = _load_prompt_template_versions()

    product_ref_assets_by_id = {row["id"]: row for row in product_ref_assets}
    creative_spec_by_asset_id = {row["asset_id"]: row for row in creative_specs}

    generated_count_by_channel = Counter()
    source_swipe_cache: dict[str, dict[str, Any]] = {}
    product_ref_cache: dict[str, dict[str, Any]] = {}
    asset_entries: list[dict[str, Any]] = []
    warnings: list[str] = []

    for asset in assets:
        metadata = _coerce_dict(asset.get("ai_metadata"))
        content = _coerce_dict(asset.get("content"))
        asset_id = _safe_str(asset.get("id")).strip()
        channel_id = _safe_str(asset.get("channel_id")).strip()
        generated_count_by_channel[channel_id] += 1
        requirement_index_raw = metadata.get("requirementIndex")
        requirement_index: int | None
        try:
            requirement_index = int(requirement_index_raw) if requirement_index_raw is not None else None
        except (TypeError, ValueError):
            requirement_index = None

        brief_id = _safe_str(metadata.get("assetBriefId")).strip()
        brief_artifact_id = (
            _safe_str(asset.get("asset_brief_artifact_id")).strip()
            or _safe_str(metadata.get("assetBriefArtifactId")).strip()
        )
        brief = None
        if brief_artifact_id:
            for candidate_brief in artifact_index["brief_by_artifact_id"].get(brief_artifact_id, []):
                if _safe_str(candidate_brief.get("id")).strip() == brief_id:
                    brief = candidate_brief
                    break
        if brief is None and brief_id:
            brief = artifact_index["brief_by_id"].get(brief_id)
        ad_copy_pack_id = _safe_str(metadata.get("adCopyPackId")).strip()
        ad_copy_pack_artifact_id = _safe_str(metadata.get("adCopyPackArtifactId")).strip()
        linked_ad_copy_pack = artifact_index["ad_copy_pack_item_by_id"].get(ad_copy_pack_id)
        creative_generation_plan_item_id = _safe_str(metadata.get("creativeGenerationPlanItemId")).strip()
        linked_plan_item = artifact_index["plan_item_by_id"].get(creative_generation_plan_item_id)

        source_filename = (
            _safe_str(metadata.get("swipeSourceFilename")).strip()
            or _safe_str(metadata.get("swipeSourceLabel")).strip()
            or _basename_from_urlish(_safe_str(metadata.get("swipeSourceUrl")).strip())
            or asset_id
        )
        swipe_source_url = _safe_str(metadata.get("swipeSourceUrl")).strip()

        asset_errors: list[str] = []

        generated_media: dict[str, Any] | None = None
        storage_key = _safe_str(asset.get("storage_key")).strip()
        if storage_key:
            try:
                generated_media = _download_storage_asset(
                    storage=storage,
                    storage_key=storage_key,
                    content_type=_safe_str(asset.get("content_type")).strip() or None,
                    preferred_name=f"{asset_id}-generated",
                    target_dir=generated_dir,
                    output_root=output_dir,
                )
            except Exception as exc:
                asset_errors.append(f"Failed to download generated asset from storage: {exc}")
        else:
            asset_errors.append("Generated asset is missing storage_key.")

        source_swipe_media: dict[str, Any] | None = None
        if swipe_source_url:
            cached = source_swipe_cache.get(swipe_source_url)
            if cached is not None:
                source_swipe_media = cached
            else:
                try:
                    downloaded = _download_url_asset(
                        url=swipe_source_url,
                        preferred_name=f"{_slugify(source_filename, max_len=96)}-source",
                        target_dir=swipe_dir,
                        output_root=output_dir,
                    )
                    source_swipe_cache[swipe_source_url] = downloaded
                    source_swipe_media = downloaded
                except Exception as exc:
                    asset_errors.append(f"Failed to download swipe source image: {exc}")
        else:
            asset_errors.append("Swipe source URL is missing.")

        product_ref_entries: list[dict[str, Any]] = []
        for product_ref_id in _coerce_list(metadata.get("swipeProductReferenceLocalAssetIds")):
            clean_ref_id = _safe_str(product_ref_id).strip()
            if not clean_ref_id:
                continue
            cached = product_ref_cache.get(clean_ref_id)
            if cached is not None:
                product_ref_entries.append(cached)
                continue
            product_ref_row = product_ref_assets_by_id.get(clean_ref_id)
            if product_ref_row is None:
                asset_errors.append(f"Missing product reference asset row: {clean_ref_id}")
                continue
            ref_storage_key = _safe_str(product_ref_row.get("storage_key")).strip()
            if not ref_storage_key:
                asset_errors.append(f"Product reference asset is missing storage_key: {clean_ref_id}")
                continue
            try:
                downloaded_ref = _download_storage_asset(
                    storage=storage,
                    storage_key=ref_storage_key,
                    content_type=_safe_str(product_ref_row.get("content_type")).strip() or None,
                    preferred_name=f"{clean_ref_id}-product-ref",
                    target_dir=product_ref_dir,
                    output_root=output_dir,
                )
                downloaded_ref["assetId"] = clean_ref_id
                product_ref_cache[clean_ref_id] = downloaded_ref
                product_ref_entries.append(downloaded_ref)
            except Exception as exc:
                asset_errors.append(f"Failed to download product reference asset {clean_ref_id}: {exc}")

        prompt_template_sha_asset = _safe_str(metadata.get("swipePromptTemplateSha256")).strip()
        prompt_template_version = prompt_template_versions.get(prompt_template_sha_asset) if prompt_template_sha_asset else None
        if prompt_template_version is None:
            prompt_template_version = prompt_template_working

        swipe_copy_prompt = _reconstruct_swipe_copy_prompt(
            brief=brief,
            requirement_index=requirement_index,
            metadata=metadata,
        )
        if swipe_copy_prompt.get("status") != "ok":
            warnings.append(f"{asset_id}: could not reconstruct swipe copy prompt ({swipe_copy_prompt.get('status')}).")
        elif swipe_copy_prompt.get("shaMatch") is False:
            warnings.append(f"{asset_id}: reconstructed swipe copy prompt sha did not match stored sha.")

        swipe_copy_pack = _coerce_dict(metadata.get("swipeCopyPack"))
        creative_spec = creative_spec_by_asset_id.get(asset_id)
        creative_spec_matches_swipe_copy = None
        if creative_spec is not None and swipe_copy_pack:
            creative_spec_matches_swipe_copy = all(
                [
                    _safe_str(creative_spec.get("primary_text")) == _safe_str(swipe_copy_pack.get("metaPrimaryText")),
                    _safe_str(creative_spec.get("headline")) == _safe_str(swipe_copy_pack.get("metaHeadline")),
                    _safe_str(creative_spec.get("description")) == _safe_str(swipe_copy_pack.get("metaDescription")),
                    _safe_str(creative_spec.get("call_to_action_type")) == _safe_str(swipe_copy_pack.get("metaCta")),
                ]
            )
            if creative_spec_matches_swipe_copy is False:
                warnings.append(f"{asset_id}: current campaign creative spec does not match swipeCopyPack.")
        elif creative_spec is None:
            warnings.append(f"{asset_id}: no current campaign creative spec exists.")

        if linked_ad_copy_pack is None and ad_copy_pack_id:
            warnings.append(f"{asset_id}: ad copy pack id {ad_copy_pack_id} was not found in campaign artifacts.")

        plan_item = linked_plan_item["item"] if isinstance(linked_plan_item, dict) else None
        brief_requirement = None
        if brief is not None and requirement_index is not None:
            requirements = _coerce_list(brief.get("requirements"))
            if 0 <= requirement_index < len(requirements) and isinstance(requirements[requirement_index], dict):
                brief_requirement = requirements[requirement_index]

        created_at = asset.get("created_at")
        created_at_str = created_at.isoformat() if created_at is not None else ""

        entry = {
            "assetId": asset_id,
            "anchorId": f"asset-{asset_id}",
            "searchText": " ".join(
                filter(
                    None,
                    [
                        asset_id,
                        channel_id,
                        _safe_str(asset.get("format")).strip(),
                        _safe_str(metadata.get("swipeSourceLabel")).strip(),
                        _safe_str(metadata.get("swipeSourceFilename")).strip(),
                        _safe_str(swipe_copy_pack.get("metaHeadline")).strip(),
                        _safe_str((creative_spec or {}).get("headline")).strip(),
                        source_filename,
                    ],
                )
            ).lower(),
            "createdAt": created_at_str,
            "channelId": channel_id,
            "format": _safe_str(asset.get("format")).strip(),
            "status": _safe_str(asset.get("status")).strip(),
            "sourceType": _safe_str(asset.get("source_type")).strip(),
            "variantId": _safe_str(asset.get("variant_id")).strip() or None,
            "requirementIndex": requirement_index,
            "storageKey": storage_key or None,
            "contentType": _safe_str(asset.get("content_type")).strip() or None,
            "sizeBytes": asset.get("size_bytes"),
            "dimensions": {
                "width": asset.get("width"),
                "height": asset.get("height"),
            },
            "briefId": brief_id or None,
            "briefArtifactId": brief_artifact_id or None,
            "brief": brief,
            "briefRequirement": brief_requirement,
            "adCopyPackId": ad_copy_pack_id or None,
            "adCopyPackArtifactId": ad_copy_pack_artifact_id or None,
            "linkedAdCopyPack": linked_ad_copy_pack,
            "creativeGenerationPlanItemId": creative_generation_plan_item_id or None,
            "linkedPlanItem": plan_item,
            "swipeSource": {
                "label": _safe_str(metadata.get("swipeSourceLabel")).strip() or None,
                "filename": _safe_str(metadata.get("swipeSourceFilename")).strip() or None,
                "url": swipe_source_url or None,
                "companySwipeId": _safe_str(metadata.get("swipeCompanyId")).strip() or None,
                "requiresProductImage": metadata.get("swipeRequiresProductImage"),
                "productImagePolicySource": _safe_str(metadata.get("swipeRequiresProductImagePolicySource")).strip() or None,
                "download": source_swipe_media,
            },
            "generatedMedia": generated_media,
            "productReferenceMedia": product_ref_entries,
            "swipeCopyPack": swipe_copy_pack,
            "swipeCopyInputs": _coerce_dict(metadata.get("swipeCopyInputs")),
            "swipeCopyPrompt": swipe_copy_prompt,
            "promptTemplate": {
                "storedSha256": prompt_template_sha_asset or None,
                "resolvedSha256": prompt_template_version["sha256"],
                "resolvedSource": prompt_template_version["source"],
                "text": prompt_template_version["text"],
                "shaMatch": bool(prompt_template_sha_asset and prompt_template_sha_asset == prompt_template_version["sha256"]),
            },
            "promptChain": {
                "stage1InputText": _safe_str(metadata.get("swipePromptInputText")) or None,
                "stage1Markdown": _safe_str(metadata.get("swipePromptMarkdown") or metadata.get("swipePromptMarkdownPreview")) or None,
                "stage1MarkdownIsFull": bool(_safe_str(metadata.get("swipePromptMarkdown")).strip()),
                "stage1ExtractedRaw": _safe_str(metadata.get("swipePromptExtractedRaw")) or None,
                "stage2RenderPromptUsed": _safe_str(metadata.get("promptUsed")) or None,
                "generatedPrompt": _safe_str(content.get("prompt")) or None,
                "note": "No distinct persisted swipe stage-two prompt object exists in this flow. The final renderer prompt used is shown as stage2RenderPromptUsed.",
            },
            "creativeSpec": creative_spec,
            "creativeSpecMatchesSwipeCopy": creative_spec_matches_swipe_copy,
            "geminiStoreNames": [name for name in _coerce_list(metadata.get("swipeGeminiStoreNames")) if _safe_str(name).strip()],
            "geminiRagDocKeys": [item for item in _coerce_list(metadata.get("swipeGeminiRagDocKeys")) if _safe_str(item).strip()],
            "geminiRagBundleDocKeys": [item for item in _coerce_list(metadata.get("swipeGeminiRagBundleDocKeys")) if _safe_str(item).strip()],
            "geminiRagDocumentNames": [item for item in _coerce_list(metadata.get("swipeGeminiRagDocumentNames")) if _safe_str(item).strip()],
            "rawContent": content,
            "rawAiMetadata": metadata,
            "errors": asset_errors,
        }
        asset_entries.append(entry)

    ad_copy_pack_artifacts: list[dict[str, Any]] = []
    for artifact in bundle["artifacts"]:
        if _safe_str(artifact.get("type")).strip() != "ad_copy_pack":
            continue
        payload = _coerce_dict(artifact.get("data"))
        copy_pack_items = []
        for copy_pack in _coerce_list(payload.get("copyPacks")):
            if not isinstance(copy_pack, dict):
                continue
            copy_pack_id = _safe_str(copy_pack.get("id")).strip()
            linked_assets = [asset["assetId"] for asset in asset_entries if asset.get("adCopyPackId") == copy_pack_id]
            copy_pack_items.append(
                {
                    "copyPack": copy_pack,
                    "linkedAssetIds": linked_assets,
                }
            )
        ad_copy_pack_artifacts.append(
            {
                "artifactId": artifact["id"],
                "createdAt": artifact["created_at"].isoformat() if artifact.get("created_at") is not None else "",
                "payload": payload,
                "copyPackItems": copy_pack_items,
            }
        )

    creative_generation_plans: list[dict[str, Any]] = []
    for artifact in artifact_index["plan_artifacts"]:
        payload = _coerce_dict(artifact.get("data"))
        items = []
        for item in _coerce_list(payload.get("items")):
            if not isinstance(item, dict):
                continue
            item_id = _safe_str(item.get("id")).strip()
            linked_asset_ids = [
                asset["assetId"]
                for asset in asset_entries
                if _safe_str(asset.get("creativeGenerationPlanItemId")).strip() == item_id
            ]
            item_copy = dict(item)
            item_copy["linkedAssetIds"] = linked_asset_ids
            items.append(item_copy)
        creative_generation_plans.append(
            {
                "artifactId": artifact["id"],
                "createdAt": artifact["created_at"].isoformat() if artifact.get("created_at") is not None else "",
                "payload": payload,
                "items": items,
            }
        )

    bundle_payload = {
        "campaign": {
            **campaign,
            "created_at": campaign["created_at"].isoformat() if campaign.get("created_at") is not None else "",
        },
        "summary": {
            "assetCount": len(asset_entries),
            "creativeSpecCount": len(creative_specs),
            "adCopyPackArtifactCount": len(ad_copy_pack_artifacts),
            "creativeGenerationPlanCount": len(creative_generation_plans),
            "productReferenceAssetCount": len(product_ref_assets),
            "sourceSwipeCount": len(source_swipe_cache),
            "generatedByChannel": dict(generated_count_by_channel),
            "warningCount": len(warnings),
        },
        "artifacts": [
            {
                "id": artifact["id"],
                "type": artifact["type"],
                "version": artifact.get("version"),
                "createdAt": artifact["created_at"].isoformat() if artifact.get("created_at") is not None else "",
                "data": artifact.get("data"),
            }
            for artifact in bundle["artifacts"]
        ],
        "promptTemplate": prompt_template_working,
        "adCopyPackArtifacts": ad_copy_pack_artifacts,
        "creativeGenerationPlans": creative_generation_plans,
        "assets": asset_entries,
        "creativeSpecs": [
            {
                **spec,
                "created_at": spec["created_at"].isoformat() if spec.get("created_at") is not None else "",
                "updated_at": spec["updated_at"].isoformat() if spec.get("updated_at") is not None else "",
            }
            for spec in creative_specs
        ],
        "geminiContextFiles": [
            {
                **row,
                "created_at": row["created_at"].isoformat() if row.get("created_at") is not None else "",
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") is not None else "",
            }
            for row in gemini_context_files
        ],
        "warnings": warnings,
    }
    bundle_json_path = output_dir / "bundle.json"
    bundle_json_path.write_text(_json_pretty(bundle_payload), encoding="utf-8")

    artifact_rows_html = []
    for artifact in bundle_payload["artifacts"]:
        artifact_rows_html.append(
            "<tr>"
            f"<td>{html.escape(_safe_str(artifact.get('id')))}</td>"
            f"<td>{html.escape(_safe_str(artifact.get('type')))}</td>"
            f"<td>{html.escape(_safe_str(artifact.get('version')))}</td>"
            f"<td>{html.escape(_safe_str(artifact.get('createdAt')))}</td>"
            "</tr>"
        )

    warning_items_html = "".join(
        f"<li>{html.escape(warning)}</li>" for warning in warnings
    ) or "<li>No warnings were recorded.</li>"

    ad_copy_pack_sections: list[str] = []
    for artifact in ad_copy_pack_artifacts:
        copy_pack_cards = []
        for item in artifact["copyPackItems"]:
            copy_pack = item["copyPack"]
            linked_assets = item["linkedAssetIds"]
            copy_pack_meta_badges = " ".join(
                [
                    _badge(_safe_str(copy_pack.get("channel")) or "[no channel]", "info"),
                    _badge(_safe_str(copy_pack.get("format")) or "[no format]", "muted"),
                    _badge(f"requirementIndex={_safe_str(copy_pack.get('requirementIndex'))}", "muted"),
                ]
            )
            copy_pack_cards.append(
                "\n".join(
                    [
                        '<div class="copy-pack-card">',
                        f"<h4>{html.escape(_safe_str(copy_pack.get('id')))}</h4>",
                        f"<p>{copy_pack_meta_badges}</p>",
                        f"<p><b>Angle:</b> {html.escape(_safe_str(copy_pack.get('angle')))}</p>",
                        f"<p><b>Hook:</b> {html.escape(_safe_str(copy_pack.get('hook')))}</p>",
                        f"<p><b>Creative Concept:</b> {html.escape(_safe_str(copy_pack.get('creativeConcept')))}</p>",
                        f"<p><b>Meta Headline:</b> {html.escape(_safe_str(copy_pack.get('metaHeadline')))}</p>",
                        f"<p><b>Meta Description:</b> {html.escape(_safe_str(copy_pack.get('metaDescription')))}</p>",
                        "<details><summary>Meta Primary Text</summary>"
                        f"<pre>{_html_pre(_safe_str(copy_pack.get('metaPrimaryText')))}</pre></details>",
                        "<details><summary>Claims Guardrails</summary>"
                        f"<pre>{_html_json(copy_pack.get('claimsGuardrails'))}</pre></details>",
                        "<details><summary>Linked Generated Assets</summary>"
                        f"<pre>{_html_json(linked_assets)}</pre></details>",
                        "<details><summary>Raw Copy Pack JSON</summary>"
                        f"<pre>{_html_json(copy_pack)}</pre></details>",
                        "</div>",
                    ]
                )
            )
        ad_copy_pack_sections.append(
            "\n".join(
                [
                    '<section class="panel section-anchor">',
                    f'<h3 id="ad-copy-pack-{html.escape(artifact["artifactId"])}">Ad Copy Pack Artifact {html.escape(artifact["artifactId"])}</h3>',
                    "<p>"
                    + " ".join(
                        [
                            _badge("artifact", "info"),
                            _badge(artifact["createdAt"], "muted"),
                            _badge(f"copy packs={len(artifact['copyPackItems'])}", "muted"),
                        ]
                    )
                    + "</p>",
                    "<details><summary>Raw Artifact JSON</summary>"
                    f"<pre>{_html_json(artifact['payload'])}</pre></details>",
                    '<div class="copy-pack-grid">',
                    "".join(copy_pack_cards) or "<p>No copy packs were found in this artifact.</p>",
                    "</div>",
                    "</section>",
                ]
            )
        )

    plan_sections: list[str] = []
    for plan in creative_generation_plans:
        planned_channels = Counter(
            _safe_str(item.get("channel")).strip()
            for item in plan["items"]
            if _safe_str(item.get("channel")).strip()
        )
        plan_badges = " ".join(
            [
                _badge(plan["createdAt"], "muted"),
                _badge(f"items={len(plan['items'])}", "muted"),
                _badge(f"channels={dict(planned_channels)}", "muted"),
            ]
        )
        plan_rows = []
        for item in plan["items"]:
            linked_asset_links = ", ".join(
                f'<a href="#asset-{html.escape(asset_id)}">{html.escape(asset_id)}</a>'
                for asset_id in item.get("linkedAssetIds") or []
            ) or "[none]"
            plan_rows.append(
                "<tr>"
                f"<td>{html.escape(_safe_str(item.get('id')))}</td>"
                f"<td>{html.escape(_safe_str(item.get('channel')))}</td>"
                f"<td>{html.escape(_safe_str(item.get('copyPackId')))}</td>"
                f"<td>{html.escape(_safe_str(item.get('sourceLabel')))}</td>"
                f"<td>{html.escape(_safe_str(item.get('companySwipeId')))}</td>"
                f"<td>{linked_asset_links}</td>"
                "</tr>"
            )
        plan_sections.append(
            "\n".join(
                [
                    '<section class="panel section-anchor">',
                    f'<h3 id="creative-plan-{html.escape(plan["artifactId"])}">Creative Generation Plan {html.escape(plan["artifactId"])}</h3>',
                    f"<p>{plan_badges}</p>",
                    "<details><summary>Plan Items</summary>",
                    '<table class="compact-table"><thead><tr><th>item id</th><th>channel</th><th>copyPackId</th><th>sourceLabel</th><th>companySwipeId</th><th>linked asset</th></tr></thead><tbody>',
                    "".join(plan_rows) or '<tr><td colspan="6">No plan items found.</td></tr>',
                    "</tbody></table></details>",
                    "<details><summary>Raw Plan JSON</summary>"
                    f"<pre>{_html_json(plan['payload'])}</pre></details>",
                    "</section>",
                ]
            )
        )

    gemini_rows_html = []
    for row in bundle_payload["geminiContextFiles"]:
        drive_url = _safe_str(row.get("drive_url")).strip()
        drive_cell = (
            f'<a href="{html.escape(drive_url)}" target="_blank" rel="noopener noreferrer">{html.escape(drive_url)}</a>'
            if drive_url
            else "[none]"
        )
        gemini_rows_html.append(
            "<tr>"
            f"<td>{html.escape(_safe_str(row.get('gemini_store_name')))}</td>"
            f"<td>{html.escape(_safe_str(row.get('doc_key')))}</td>"
            f"<td>{html.escape(_safe_str(row.get('doc_title')))}</td>"
            f"<td>{html.escape(_safe_str(row.get('source_kind')))}</td>"
            f"<td>{html.escape(_safe_str(row.get('step_key')))}</td>"
            f"<td>{html.escape(_safe_str(row.get('filename')))}</td>"
            f"<td>{html.escape(_safe_str(row.get('mime_type')))}</td>"
            f"<td>{html.escape(_safe_str(row.get('size_bytes')))}</td>"
            f"<td>{drive_cell}</td>"
            "</tr>"
        )

    asset_nav_links: list[str] = []
    asset_cards: list[str] = []
    for asset in asset_entries:
        asset_id = asset["assetId"]
        anchor_id = asset["anchorId"]
        swipe_copy_pack = _coerce_dict(asset.get("swipeCopyPack"))
        creative_spec = asset.get("creativeSpec")
        source_swipe = _coerce_dict(asset.get("swipeSource"))
        source_download = _coerce_dict(source_swipe.get("download"))
        generated_media = _coerce_dict(asset.get("generatedMedia"))
        product_reference_media = [item for item in _coerce_list(asset.get("productReferenceMedia")) if isinstance(item, dict)]
        prompt_chain = _coerce_dict(asset.get("promptChain"))
        prompt_template = _coerce_dict(asset.get("promptTemplate"))
        linked_ad_copy_pack = asset.get("linkedAdCopyPack")
        linked_ad_copy_pack_item = _coerce_dict(linked_ad_copy_pack.get("copyPack")) if isinstance(linked_ad_copy_pack, dict) else {}
        linked_plan_item = _coerce_dict(asset.get("linkedPlanItem"))
        swipe_copy_prompt = _coerce_dict(asset.get("swipeCopyPrompt"))

        spec_badge = (
            _badge("creative spec: missing", "warn")
            if creative_spec is None
            else _badge("creative spec: matches swipe copy", "good")
            if asset.get("creativeSpecMatchesSwipeCopy") is True
            else _badge("creative spec: differs from swipe copy", "danger")
            if asset.get("creativeSpecMatchesSwipeCopy") is False
            else _badge("creative spec: present", "info")
        )
        prompt_sha_badge = (
            _badge("swipe copy prompt sha: match", "good")
            if swipe_copy_prompt.get("shaMatch") is True
            else _badge("swipe copy prompt sha: mismatch", "danger")
            if swipe_copy_prompt.get("status") == "ok"
            else _badge(f"swipe copy prompt: {swipe_copy_prompt.get('status')}", "warn")
        )
        prompt_template_status_badge = _badge(
            "stored template sha matches current" if prompt_template.get("shaMatch") else "stored template sha differs from current",
            "good" if prompt_template.get("shaMatch") else "warn",
        )
        prompt_error_html = (
            f'<p class="error">{html.escape(_safe_str(swipe_copy_prompt.get("error")))}</p>'
            if _safe_str(swipe_copy_prompt.get("error")).strip()
            else ""
        )

        asset_nav_links.append(
            f'<a class="asset-link" data-search="{html.escape(asset["searchText"])}" href="#{html.escape(anchor_id)}">'
            f"<span>{html.escape(asset_id)}</span>"
            f"<small>{html.escape(_safe_str(asset.get('channelId')))} · {html.escape(_safe_str(source_swipe.get('filename') or source_swipe.get('label')))}</small>"
            "</a>"
        )

        product_ref_gallery = []
        for product_ref in product_reference_media:
            rel_path = _safe_str(product_ref.get("path")).strip()
            if rel_path:
                product_ref_gallery.append(
                    '<figure class="thumb">'
                    f'<img src="{html.escape(rel_path)}" alt="{html.escape(_safe_str(product_ref.get("assetId")))}" loading="lazy" />'
                    f'<figcaption>{html.escape(_safe_str(product_ref.get("assetId")))}</figcaption>'
                    "</figure>"
                )
        if not product_ref_gallery:
            product_ref_gallery.append('<div class="empty-state">No product reference images were attached for this asset.</div>')

        asset_cards.append(
            "\n".join(
                [
                    f'<section id="{html.escape(anchor_id)}" class="panel asset-card section-anchor" data-search="{html.escape(asset["searchText"])}">',
                    '<div class="asset-header">',
                    f"<h3>{html.escape(asset_id)}</h3>",
                    '<div class="badges">',
                    _badge(_safe_str(asset.get("channelId")) or "[no channel]", "info"),
                    _badge(_safe_str(asset.get("format")) or "[no format]", "muted"),
                    _badge(f"requirementIndex={_safe_str(asset.get('requirementIndex'))}", "muted"),
                    _badge(_safe_str(asset.get("createdAt")) or "[no created_at]", "muted"),
                    spec_badge,
                    prompt_sha_badge,
                    _bool_badge("product ref attached", bool(product_reference_media) if product_reference_media else False),
                    "</div>",
                    "</div>",
                    '<div class="media-grid">',
                    '<div class="media-panel">',
                    "<h4>Generated Ad Image</h4>",
                    (
                        f'<img src="{html.escape(_safe_str(generated_media.get("path")))}" alt="{html.escape(asset_id)} generated" loading="lazy" />'
                        if _safe_str(generated_media.get("path")).strip()
                        else '<div class="empty-state">Generated image could not be downloaded.</div>'
                    ),
                    f"<p><b>storageKey:</b> {html.escape(_safe_str(asset.get('storageKey')) or '[none]')}</p>",
                    "</div>",
                    '<div class="media-panel">',
                    "<h4>Source Swipe Image</h4>",
                    (
                        f'<img src="{html.escape(_safe_str(source_download.get("path")))}" alt="{html.escape(_safe_str(source_swipe.get("filename") or source_swipe.get("label")))}" loading="lazy" />'
                        if _safe_str(source_download.get("path")).strip()
                        else '<div class="empty-state">Source swipe image could not be downloaded.</div>'
                    ),
                    f"<p><b>label:</b> {html.escape(_safe_str(source_swipe.get('label') or source_swipe.get('filename')) or '[none]')}</p>",
                    f"<p><b>companySwipeId:</b> {html.escape(_safe_str(source_swipe.get('companySwipeId')) or '[none]')}</p>",
                    f"<p><b>sourceUrl:</b> {html.escape(_safe_str(source_swipe.get('url')) or '[none]')}</p>",
                    "</div>",
                    '<div class="media-panel">',
                    "<h4>Product Reference Images</h4>",
                    '<div class="thumb-grid">',
                    "".join(product_ref_gallery),
                    "</div>",
                    "</div>",
                    "</div>",
                    '<div class="details-grid">',
                    '<div class="detail-block">',
                    "<h4>Current Campaign Copy</h4>",
                    (
                        "\n".join(
                            [
                                f"<p><b>Creative Spec ID:</b> {html.escape(_safe_str(creative_spec.get('id')))}</p>",
                                f"<p><b>Status:</b> {html.escape(_safe_str(creative_spec.get('status')))}</p>",
                                f"<p><b>Headline:</b> {html.escape(_safe_str(creative_spec.get('headline')))}</p>",
                                f"<p><b>Description:</b> {html.escape(_safe_str(creative_spec.get('description')))}</p>",
                                f"<p><b>CTA:</b> {html.escape(_safe_str(creative_spec.get('call_to_action_type')))}</p>",
                                "<details><summary>Primary Text</summary>"
                                f"<pre>{_html_pre(_safe_str(creative_spec.get('primary_text')))}</pre></details>",
                                "<details><summary>Creative Spec Metadata JSON</summary>"
                                f"<pre>{_html_json(creative_spec.get('metadata'))}</pre></details>",
                            ]
                        )
                        if creative_spec is not None
                        else "<p>No `meta_creative_spec` exists for this asset in the current campaign.</p>"
                    ),
                    "</div>",
                    '<div class="detail-block">',
                    "<h4>Swipe Copy Pack</h4>",
                    f"<p><b>Headline:</b> {html.escape(_safe_str(swipe_copy_pack.get('metaHeadline')))}</p>",
                    f"<p><b>Description:</b> {html.escape(_safe_str(swipe_copy_pack.get('metaDescription')))}</p>",
                    f"<p><b>CTA:</b> {html.escape(_safe_str(swipe_copy_pack.get('metaCta')))}</p>",
                    "<details><summary>Primary Text</summary>"
                    f"<pre>{_html_pre(_safe_str(swipe_copy_pack.get('metaPrimaryText')))}</pre></details>",
                    "<details><summary>Formatted Variations Markdown</summary>"
                    f"<pre>{_html_pre(_safe_str(swipe_copy_pack.get('formattedVariationsMarkdown')))}</pre></details>",
                    "<details><summary>Swipe Copy Pack JSON</summary>"
                    f"<pre>{_html_json(swipe_copy_pack)}</pre></details>",
                    "</div>",
                    '<div class="detail-block">',
                    "<h4>Requirement-Level Ad Copy Pack</h4>",
                    (
                        "\n".join(
                            [
                                f"<p><b>Artifact ID:</b> {html.escape(_safe_str(linked_ad_copy_pack.get('artifactId')))}</p>",
                                f"<p><b>Copy Pack ID:</b> {html.escape(_safe_str(linked_ad_copy_pack_item.get('id')))}</p>",
                                f"<p><b>Headline:</b> {html.escape(_safe_str(linked_ad_copy_pack_item.get('metaHeadline')))}</p>",
                                f"<p><b>Description:</b> {html.escape(_safe_str(linked_ad_copy_pack_item.get('metaDescription')))}</p>",
                                "<details><summary>Primary Text</summary>"
                                f"<pre>{_html_pre(_safe_str(linked_ad_copy_pack_item.get('metaPrimaryText')))}</pre></details>",
                                "<details><summary>Ad Copy Pack JSON</summary>"
                                f"<pre>{_html_json(linked_ad_copy_pack_item)}</pre></details>",
                            ]
                        )
                        if linked_ad_copy_pack_item
                        else "<p>No linked `ad_copy_pack` item was found for this asset.</p>"
                    ),
                    "</div>",
                    "</div>",
                    '<div class="detail-block full-width">',
                    "<h4>Prompt Chain</h4>",
                    f"<p>{prompt_sha_badge} {_badge(_safe_str(prompt_template.get('resolvedSource')) or '[template source unknown]', 'muted')} {prompt_template_status_badge}</p>",
                    f"<p><b>Note:</b> {html.escape(_safe_str(prompt_chain.get('note')))}</p>",
                    "<details><summary>Swipe Copy Prompt (reconstructed exact prompt text)</summary>"
                    f"<pre>{_html_pre(_safe_str(swipe_copy_prompt.get('promptText')))}</pre>"
                    f"<p><b>stored sha:</b> {html.escape(_safe_str(swipe_copy_prompt.get('storedSha256')) or '[none]')}</p>"
                    f"<p><b>rebuilt sha:</b> {html.escape(_safe_str(swipe_copy_prompt.get('rebuiltSha256')) or '[none]')}</p>"
                    f"{prompt_error_html}"
                    "</details>",
                    "<details><summary>Prompt Template Text (`prompts/swipe/swipe_to_image_ad.md`)</summary>"
                    f"<pre>{_html_pre(_safe_str(prompt_template.get('text')))}</pre></details>",
                    "<details><summary>Stage 1 Input Text (`swipePromptInputText`)</summary>"
                    f"<pre>{_html_pre(_safe_str(prompt_chain.get('stage1InputText')))}</pre></details>",
                    "<details><summary>Stage 1 Output Markdown (`swipePromptMarkdown`)</summary>"
                    f"<pre>{_html_pre(_safe_str(prompt_chain.get('stage1Markdown')))}</pre>"
                    f"<p><b>full markdown persisted:</b> {html.escape('yes' if prompt_chain.get('stage1MarkdownIsFull') else 'no')}</p>"
                    "</details>",
                    "<details><summary>Stage 1 Extracted Raw Prompt (`swipePromptExtractedRaw`)</summary>"
                    f"<pre>{_html_pre(_safe_str(prompt_chain.get('stage1ExtractedRaw')))}</pre></details>",
                    "<details><summary>Stage 2 / Final Renderer Prompt Used (`promptUsed`)</summary>"
                    f"<pre>{_html_pre(_safe_str(prompt_chain.get('stage2RenderPromptUsed')))}</pre></details>",
                    "<details><summary>Generated Prompt Stored On Asset Content</summary>"
                    f"<pre>{_html_pre(_safe_str(prompt_chain.get('generatedPrompt')))}</pre></details>",
                    "</div>",
                    '<div class="detail-block full-width">',
                    "<h4>Plan + Raw Metadata</h4>",
                    "<details><summary>Linked Creative Generation Plan Item</summary>"
                    f"<pre>{_html_json(linked_plan_item or {})}</pre></details>",
                    "<details><summary>Gemini Context Keys</summary>"
                    f"<pre>{_html_json({'stores': asset.get('geminiStoreNames'), 'docKeys': asset.get('geminiRagDocKeys'), 'bundleDocKeys': asset.get('geminiRagBundleDocKeys'), 'documentNames': asset.get('geminiRagDocumentNames')})}</pre></details>",
                    "<details><summary>Asset Brief Requirement</summary>"
                    f"<pre>{_html_json(asset.get('briefRequirement') or {})}</pre></details>",
                    "<details><summary>Raw ai_metadata JSON</summary>"
                    f"<pre>{_html_json(asset.get('rawAiMetadata'))}</pre></details>",
                    "<details><summary>Raw content JSON</summary>"
                    f"<pre>{_html_json(asset.get('rawContent'))}</pre></details>",
                    (
                        "<details><summary>Asset Errors</summary>"
                        f"<pre>{_html_json(asset.get('errors'))}</pre></details>"
                        if asset.get("errors")
                        else ""
                    ),
                    "</div>",
                    "</section>",
                ]
            )
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Campaign Forensic Review</title>
  <style>
    :root {{
      --bg: #0f1115;
      --panel: #171a21;
      --panel-2: #1d2330;
      --line: #30384a;
      --text: #e8ecf3;
      --muted: #9da8bb;
      --accent: #7dc4ff;
      --good: #2ecc71;
      --warn: #f5a623;
      --danger: #ff6b6b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #0b0d12 0%, #111621 100%);
      color: var(--text);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .app {{
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      position: sticky;
      top: 0;
      align-self: start;
      height: 100vh;
      overflow: auto;
      padding: 20px 16px;
      border-right: 1px solid var(--line);
      background: rgba(9, 12, 18, 0.92);
      backdrop-filter: blur(8px);
    }}
    .sidebar h1 {{
      margin: 0 0 8px;
      font-size: 20px;
      line-height: 1.2;
    }}
    .sidebar p {{
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .sidebar .summary {{
      margin: 16px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .sidebar input {{
      width: 100%;
      margin: 12px 0 16px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #0d1118;
      color: var(--text);
    }}
    .nav-group {{
      margin-bottom: 20px;
    }}
    .nav-title {{
      margin-bottom: 8px;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .nav-group a {{
      display: block;
      padding: 8px 10px;
      margin-bottom: 6px;
      border: 1px solid transparent;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.02);
    }}
    .nav-group a:hover {{
      border-color: var(--line);
      background: rgba(255, 255, 255, 0.04);
      text-decoration: none;
    }}
    .asset-link span {{
      display: block;
      font-size: 13px;
      line-height: 1.3;
    }}
    .asset-link small {{
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 11px;
    }}
    main {{
      padding: 24px;
    }}
    .panel {{
      background: rgba(23, 26, 33, 0.96);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      margin-bottom: 18px;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
    }}
    .section-anchor {{
      scroll-margin-top: 24px;
    }}
    h2, h3, h4 {{
      margin: 0 0 10px;
    }}
    h2 {{
      font-size: 22px;
    }}
    h3 {{
      font-size: 18px;
    }}
    h4 {{
      font-size: 14px;
      color: #d4deee;
    }}
    p {{
      margin: 0 0 10px;
      line-height: 1.45;
    }}
    .badge {{
      display: inline-block;
      margin: 0 6px 6px 0;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 11px;
      line-height: 1;
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
    }}
    .badge-good {{ border-color: rgba(46, 204, 113, 0.45); color: #98f0be; }}
    .badge-warn {{ border-color: rgba(245, 166, 35, 0.45); color: #ffd089; }}
    .badge-danger {{ border-color: rgba(255, 107, 107, 0.45); color: #ffb0b0; }}
    .badge-muted {{ color: var(--muted); }}
    .badge-info {{ color: #c3e4ff; }}
    .compact-table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
    }}
    .compact-table th,
    .compact-table td {{
      padding: 8px 10px;
      border: 1px solid var(--line);
      vertical-align: top;
      font-size: 12px;
      text-align: left;
    }}
    .compact-table th {{
      background: rgba(255, 255, 255, 0.04);
    }}
    .copy-pack-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    .copy-pack-card {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.02);
    }}
    .asset-header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 14px;
    }}
    .asset-header .badges {{
      text-align: right;
      flex-shrink: 0;
    }}
    .media-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }}
    .media-panel {{
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.02);
    }}
    .media-panel img {{
      display: block;
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #0b0e14;
      margin-bottom: 10px;
    }}
    .thumb-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 10px;
    }}
    .thumb {{
      margin: 0;
    }}
    .thumb img {{
      margin-bottom: 6px;
    }}
    .thumb figcaption {{
      font-size: 11px;
      color: var(--muted);
      word-break: break-word;
    }}
    .details-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }}
    .detail-block {{
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.02);
    }}
    .full-width {{
      grid-column: 1 / -1;
    }}
    details {{
      margin-top: 8px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      padding-top: 8px;
    }}
    summary {{
      cursor: pointer;
      color: #dbe8f6;
      font-weight: 600;
    }}
    pre {{
      margin-top: 10px;
      padding: 12px;
      border-radius: 12px;
      background: #0b0f17;
      color: #dff5ff;
      border: 1px solid #243040;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12px;
      line-height: 1.45;
    }}
    ul {{
      margin: 10px 0 0 20px;
    }}
    .empty-state {{
      padding: 16px;
      border: 1px dashed var(--line);
      border-radius: 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    .error {{
      color: #ffb0b0;
    }}
    @media (max-width: 1180px) {{
      .app {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: static;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }}
      .media-grid,
      .details-grid {{
        grid-template-columns: 1fr;
      }}
      .asset-header {{
        flex-direction: column;
      }}
      .asset-header .badges {{
        text-align: left;
      }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <h1>Campaign Forensic Review</h1>
      <p><b>{html.escape(_safe_str(campaign.get("name")))}</b></p>
      <p>Campaign ID: {html.escape(_safe_str(campaign.get("id")))}</p>
      <p>Client: {html.escape(_safe_str(campaign.get("client_name")))}</p>
      <p>Product: {html.escape(_safe_str(campaign.get("product_name")))}</p>
      <p>Open the raw export: <a href="bundle.json">bundle.json</a></p>
      <div class="summary">
        {_badge(f"assets={bundle_payload['summary']['assetCount']}", 'info')}
        {_badge(f"creative specs={bundle_payload['summary']['creativeSpecCount']}", 'info')}
        {_badge(f"ad copy pack artifacts={bundle_payload['summary']['adCopyPackArtifactCount']}", 'muted')}
        {_badge(f"plan artifacts={bundle_payload['summary']['creativeGenerationPlanCount']}", 'muted')}
        {_badge(f"warnings={bundle_payload['summary']['warningCount']}", 'warn' if warnings else 'good')}
      </div>
      <input id="asset-search" type="search" placeholder="Filter assets by id, source, channel, headline..." />

      <div class="nav-group">
        <div class="nav-title">Sections</div>
        <a href="#overview">Overview</a>
        <a href="#artifacts">Artifacts</a>
        <a href="#ad-copy-packs">Ad Copy Packs</a>
        <a href="#creative-plans">Creative Plans</a>
        <a href="#gemini-context">Gemini Context Files</a>
        <a href="#assets">Generated Assets</a>
      </div>

      <div class="nav-group">
        <div class="nav-title">Assets</div>
        <div id="asset-nav">
          {''.join(asset_nav_links)}
        </div>
      </div>
    </aside>

    <main>
      <section id="overview" class="panel section-anchor">
        <h2>Overview</h2>
        <p>{_badge(_safe_str(campaign.get('objective_type')) or '[no objective]', 'info')} {_badge(_safe_str(campaign.get('created_at').isoformat() if campaign.get('created_at') is not None else ''), 'muted')}</p>
        <p><b>Goal:</b> {html.escape(_safe_str(campaign.get('goal_description')) or '[no goal description]')}</p>
        <p><b>Channels:</b> {html.escape(_safe_str(campaign.get('channels')))}</p>
        <p><b>Asset Brief Types:</b> {html.escape(_safe_str(campaign.get('asset_brief_types')))}</p>
        <p><b>Prompt note:</b> The swipe flow does not persist a distinct named “stage two prompt” object. This export shows the real prompt chain that exists in storage: reconstructed swipe-copy prompt, stage-1 input text, stage-1 markdown output, stage-1 extracted raw prompt, and final renderer prompt used.</p>
        <details open>
          <summary>Warnings</summary>
          <ul>{warning_items_html}</ul>
        </details>
      </section>

      <section id="artifacts" class="panel section-anchor">
        <h2>Artifacts</h2>
        <table class="compact-table">
          <thead>
            <tr><th>artifact id</th><th>type</th><th>version</th><th>created at</th></tr>
          </thead>
          <tbody>
            {''.join(artifact_rows_html) if artifact_rows_html else '<tr><td colspan="4">No artifacts found.</td></tr>'}
          </tbody>
        </table>
      </section>

      <section id="ad-copy-packs" class="section-anchor">
        <h2>Ad Copy Packs</h2>
        {''.join(ad_copy_pack_sections) or '<div class="panel"><p>No ad copy pack artifacts were found.</p></div>'}
      </section>

      <section id="creative-plans" class="section-anchor">
        <h2>Creative Generation Plans</h2>
        {''.join(plan_sections) or '<div class="panel"><p>No creative generation plan artifacts were found.</p></div>'}
      </section>

      <section id="gemini-context" class="panel section-anchor">
        <h2>Gemini Context Files</h2>
        <table class="compact-table">
          <thead>
            <tr><th>store</th><th>doc key</th><th>doc title</th><th>source kind</th><th>step key</th><th>filename</th><th>mime type</th><th>size bytes</th><th>drive url</th></tr>
          </thead>
          <tbody>
            {''.join(gemini_rows_html) if gemini_rows_html else '<tr><td colspan="9">No Gemini context files were resolved for this campaign’s generated assets.</td></tr>'}
          </tbody>
        </table>
      </section>

      <section id="assets" class="section-anchor">
        <h2>Generated Assets</h2>
        {''.join(asset_cards) if asset_cards else '<div class="panel"><p>No generated assets were found for this campaign.</p></div>'}
      </section>
    </main>
  </div>

  <script>
    const searchInput = document.getElementById('asset-search');
    const cards = Array.from(document.querySelectorAll('.asset-card'));
    const navLinks = Array.from(document.querySelectorAll('.asset-link'));

    function applyAssetFilter() {{
      const query = (searchInput.value || '').trim().toLowerCase();
      cards.forEach((card) => {{
        const text = card.dataset.search || '';
        const visible = !query || text.includes(query);
        card.style.display = visible ? '' : 'none';
      }});
      navLinks.forEach((link) => {{
        const text = link.dataset.search || '';
        const visible = !query || text.includes(query);
        link.style.display = visible ? '' : 'none';
      }});
    }}

    searchInput.addEventListener('input', applyAssetFilter);
  </script>
</body>
</html>
"""

    index_path = output_dir / "index.html"
    index_path.write_text(html_doc, encoding="utf-8")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a campaign-level forensic review bundle for swipe-generated ad creatives."
    )
    parser.add_argument("campaign_id", help="Campaign UUID to export.")
    parser.add_argument(
        "--output-root",
        default=str(REPO_ROOT / "docs" / "campaign-forensics"),
        help="Root folder for the export bundle (default: docs/campaign-forensics).",
    )
    args = parser.parse_args()

    output_dir = export_campaign_forensic_review(
        campaign_id=args.campaign_id,
        output_root=Path(args.output_root).expanduser().resolve(),
    )
    print(f"exported_dir={output_dir}")
    print(f"index={output_dir / 'index.html'}")
    print(f"bundle={output_dir / 'bundle.json'}")


if __name__ == "__main__":
    main()
