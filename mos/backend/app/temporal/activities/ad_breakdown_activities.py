from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import tempfile
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import httpx
import google.generativeai as genai
from temporalio import activity

from app.db.base import session_scope
from app.db.models import Ad, Brand
from app.db.repositories.ads import AdsRepository
from app.db.repositories.jobs import (
    JobsRepository,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    JOB_TYPE_ADD_CREATIVE_BREAKDOWN,
    SUBJECT_TYPE_AD,
)
from app.db.repositories.teardowns import TeardownsRepository
from app.schemas.teardowns import (
    TeardownAssertionInput,
    TeardownEvidenceInput,
    TeardownUpsertRequest,
)
from app.services.ad_breakdown import (
    build_ad_context_block,
    build_media_summary,
    extract_storyboard_rows,
    extract_teardown_header_fields,
    extract_transcript_rows,
    load_ad_breakdown_prompt,
    segment_ad_breakdown_output,
    summarize_raw_json,
)
from app.services.media_storage import MediaStorage

logger = logging.getLogger(__name__)

_GEMINI_CONFIGURED = False

AD_BREAKDOWN_MODEL = os.getenv("AD_BREAKDOWN_MODEL", "gemini-2.5-flash")
AD_BREAKDOWN_MAX_OUTPUT_TOKENS = int(os.getenv("AD_BREAKDOWN_MAX_OUTPUT_TOKENS", "24000"))
AD_BREAKDOWN_INLINE_MAX_BYTES = int(os.getenv("AD_BREAKDOWN_INLINE_MAX_BYTES", str(18 * 1024 * 1024)))
AD_BREAKDOWN_DOWNLOAD_TIMEOUT = float(os.getenv("AD_BREAKDOWN_DOWNLOAD_TIMEOUT", "30"))
AD_BREAKDOWN_VIDEO_CLIP_SECONDS = int(os.getenv("AD_BREAKDOWN_VIDEO_CLIP_SECONDS", "60"))
AD_BREAKDOWN_VIDEO_FPS = int(os.getenv("AD_BREAKDOWN_VIDEO_FPS", "2"))


@lru_cache()
def _media_storage() -> MediaStorage:
    return MediaStorage()


def _ensure_gemini_configured() -> None:
    global _GEMINI_CONFIGURED
    if _GEMINI_CONFIGURED:
        return
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)
    _GEMINI_CONFIGURED = True


def _download_media(url: str, *, max_bytes: int, timeout_seconds: float) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=timeout_seconds) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: List[bytes] = []
            total = 0
            for chunk in resp.iter_bytes(8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"media_too_large: {total} bytes (limit {max_bytes})")
                chunks.append(chunk)
            return b"".join(chunks)


def _build_media_parts(
    media_rows: List[Tuple[Any, Optional[str]]],
) -> List[Dict[str, Any]]:
    """
    Build Gemini content parts for media assets.

    Current implementation:
      - Inlines media bytes up to AD_BREAKDOWN_INLINE_MAX_BYTES.
      - For larger assets, uploads via Gemini Files API and passes file handles.
      - Video assets longer than AD_BREAKDOWN_VIDEO_CLIP_SECONDS are skipped to
        avoid very long clips; FPS is exposed via AD_BREAKDOWN_VIDEO_FPS but
        sampling is left to the model defaults.
    """
    parts: List[Dict[str, Any]] = []
    def _guess_mime(media_obj: Any, fallback_asset_type: Optional[str]) -> Optional[str]:
        for candidate in (getattr(media_obj, "stored_url", None), getattr(media_obj, "source_url", None)):
            if not candidate:
                continue
            mime, _ = mimetypes.guess_type(candidate)
            if mime:
                return mime
        if fallback_asset_type == "VIDEO":
            return "video/mp4"
        if fallback_asset_type in {"IMAGE", "SCREENSHOT"}:
            return "image/jpeg"
        return None

    for media, role in media_rows:
        presigned_url = None
        storage_key = getattr(media, "storage_key", None)
        bucket = getattr(media, "bucket", None)
        if storage_key and bucket:
            try:
                presigned_url = _media_storage().presign_get(bucket=bucket, key=storage_key)
            except Exception as exc:  # noqa: BLE001
                activity.logger.info(
                    "ads_breakdown.presign_failed",
                    extra={"media_id": str(media.id), "error": str(exc)},
                )
        url = presigned_url or media.stored_url or media.source_url
        if not url:
            continue
        asset_type_value = getattr(media.asset_type, "value", "").upper()
        mime_type = media.mime_type
        if not mime_type or mime_type == "application/octet-stream":
            mime_type = _guess_mime(media, asset_type_value)
        if not mime_type:
            activity.logger.info(
                "ads_breakdown.skip_media_unknown_mime",
                extra={"media_id": str(media.id), "role": role, "source_url": url},
            )
            continue

        is_video = asset_type_value == "VIDEO" or mime_type.startswith("video/")

        # Skip overly long videos to keep analysis bounded.
        duration_ms = getattr(media, "duration_ms", None)
        if is_video and duration_ms is not None:
            if duration_ms > AD_BREAKDOWN_VIDEO_CLIP_SECONDS * 1000:
                activity.logger.info(
                    "ads_breakdown.video_skipped_due_to_duration",
                    extra={
                        "media_id": str(media.id),
                        "role": role,
                        "duration_ms": duration_ms,
                        "clip_seconds": AD_BREAKDOWN_VIDEO_CLIP_SECONDS,
                    },
                )
                continue

        size_bytes = getattr(media, "size_bytes", None)
        try:
            if size_bytes is not None and size_bytes <= AD_BREAKDOWN_INLINE_MAX_BYTES:
                # Inline bytes for small assets.
                data = _download_media(
                    url,
                    max_bytes=AD_BREAKDOWN_INLINE_MAX_BYTES,
                    timeout_seconds=AD_BREAKDOWN_DOWNLOAD_TIMEOUT,
                )
                parts.append({"mime_type": mime_type, "data": data})
            else:
                # Use Files API for larger assets.
                data = _download_media(
                    url,
                    max_bytes=AD_BREAKDOWN_INLINE_MAX_BYTES * 4,
                    timeout_seconds=AD_BREAKDOWN_DOWNLOAD_TIMEOUT,
                )
                with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as tmp:
                    tmp.write(data)
                    tmp.flush()
                    try:
                        file = genai.upload_file(path=tmp.name, mime_type=mime_type)
                        parts.append(file)
                    except Exception as exc:  # noqa: BLE001
                        activity.logger.warning(
                            "ads_breakdown.files_api_upload_failed",
                            extra={"media_id": str(media.id), "role": role, "error": str(exc)},
                        )
        except Exception as exc:  # noqa: BLE001
            activity.logger.warning(
                "ads_breakdown.media_download_failed",
                extra={"media_id": str(media.id), "role": role, "error": str(exc)},
            )
    return parts


@activity.defn(name="ads.generate_ad_breakdown")
def generate_ad_breakdown_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a structured ad breakdown for a single ad using Gemini.

    Stores raw markdown + segmented JSON in the generic jobs table.
    """
    org_id: str = params["org_id"]
    client_id: Optional[str] = params.get("client_id")
    research_run_id: Optional[str] = params.get("research_run_id")
    ad_id: str = params["ad_id"]
    model: str = params.get("model") or AD_BREAKDOWN_MODEL
    max_output_tokens: int = int(params.get("max_output_tokens") or AD_BREAKDOWN_MAX_OUTPUT_TOKENS)

    with session_scope() as session:
        ads_repo = AdsRepository(session)
        jobs_repo = JobsRepository(session)

        ad, media_rows = ads_repo.ad_with_media(ad_id)
        if not ad:
            error = f"Ad {ad_id} not found"
            activity.logger.error(
                "ads_breakdown.ad_missing",
                extra={"org_id": org_id, "client_id": client_id, "ad_id": ad_id},
            )
            return {
                "ad_id": ad_id,
                "status": JOB_STATUS_FAILED,
                "error": error,
            }

        brand = session.get(Brand, ad.brand_id) if ad.brand_id else None
        brand_name = getattr(brand, "canonical_name", None) if brand else None

        prompt_template, prompt_sha = load_ad_breakdown_prompt()
        dedupe_raw = f"{JOB_TYPE_ADD_CREATIVE_BREAKDOWN}:{SUBJECT_TYPE_AD}:{ad_id}:{model}:{prompt_sha}"
        dedupe_key = hashlib.sha256(dedupe_raw.encode("utf-8")).hexdigest()

        media_summary = build_media_summary(media_rows)
        raw_json_summary = summarize_raw_json(ad.raw_json or {})

        input_snapshot: Dict[str, Any] = {
            "job_type": JOB_TYPE_ADD_CREATIVE_BREAKDOWN,
            "subject_type": SUBJECT_TYPE_AD,
            "subject_id": str(ad.id),
            "org_id": org_id,
            "client_id": client_id,
            "research_run_id": research_run_id,
            "model": model,
            "prompt_sha256": prompt_sha,
            "prompt_template_name": "creative_analysis/ad_breakdown.md",
            "ad": {
                "brand_id": str(ad.brand_id),
                "brand_name": brand_name,
                "channel": getattr(ad.channel, "value", str(ad.channel)),
                "external_ad_id": ad.external_ad_id,
            },
            "media_assets": media_summary,
        }

        job, created = jobs_repo.get_or_create(
            org_id=org_id,
            client_id=client_id,
            research_run_id=research_run_id,
            job_type=JOB_TYPE_ADD_CREATIVE_BREAKDOWN,
            subject_type=SUBJECT_TYPE_AD,
            subject_id=str(ad.id),
            dedupe_key=dedupe_key,
            input_payload=input_snapshot,
        )

        if not created and job.status in (JOB_STATUS_SUCCEEDED, JOB_STATUS_RUNNING):
            activity.logger.info(
                "ads_breakdown.skip_existing_job",
                extra={
                    "job_id": str(job.id),
                    "ad_id": ad_id,
                    "status": job.status,
                },
            )
            return {
                "job_id": str(job.id),
                "ad_id": ad_id,
                "status": job.status,
                "skipped": True,
            }

        jobs_repo.mark_running(str(job.id))

        ad_context_block = build_ad_context_block(
            ad=ad,
            brand_name=brand_name,
            research_run_id=research_run_id,
            media_summary=media_summary,
            raw_json_summary=raw_json_summary,
        )

        _ensure_gemini_configured()
        model_name = model if model.startswith("models/") else f"models/{model}"
        generation_config = {
            "temperature": 0.2,
            "max_output_tokens": max_output_tokens,
        }
        model_client = genai.GenerativeModel(model_name=model_name, generation_config=generation_config)

        media_parts = _build_media_parts(media_rows)
        contents: List[Any] = [ad_context_block, prompt_template]
        contents.extend(media_parts)

        try:
            result = model_client.generate_content(contents, request_options={"timeout": 120})
            raw_output = getattr(result, "text", None)
            if not raw_output and getattr(result, "candidates", None):
                first = result.candidates[0]
                if first and getattr(first, "content", None) and getattr(first.content, "parts", None):
                    texts: List[str] = []
                    for part in first.content.parts:
                        text = getattr(part, "text", None)
                        if text:
                            texts.append(text)
                    raw_output = "\\n".join(texts) if texts else None
            if not raw_output:
                raise RuntimeError("Gemini returned no text for ad breakdown")

            structured = segment_ad_breakdown_output(raw_output)
            output_payload = {
                "ad_id": str(ad.id),
                "model": model,
                "prompt_sha256": prompt_sha,
                "media_assets": media_summary,
                "parsed": structured,
            }
            jobs_repo.mark_succeeded(str(job.id), output=output_payload, raw_output_text=raw_output)
            activity.logger.info(
                "ads_breakdown.completed",
                extra={"job_id": str(job.id), "ad_id": ad_id},
            )
            return {
                "job_id": str(job.id),
                "ad_id": ad_id,
                "status": JOB_STATUS_SUCCEEDED,
            }
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            jobs_repo.mark_failed(str(job.id), error=error_msg, output={"error": error_msg})
            activity.logger.error(
                "ads_breakdown.error",
                extra={"job_id": str(job.id), "ad_id": ad_id, "error": error_msg},
            )
            return {
                "job_id": str(job.id),
                "ad_id": ad_id,
                "status": JOB_STATUS_FAILED,
                "error": error_msg,
            }


@activity.defn(name="ads.persist_teardown_from_breakdown")
def persist_teardown_from_breakdown_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist an ad teardown record from a completed creative breakdown job.

    This uses the generic jobs table as the raw payload source and attaches
    the teardown to the ad's creative via AdCreativeMembership.
    """
    org_id: str = params["org_id"]
    client_id: Optional[str] = params.get("client_id")
    research_run_id: Optional[str] = params.get("research_run_id")
    ad_id: str = params["ad_id"]
    job_id: str = params["job_id"]

    with session_scope() as session:
        jobs_repo = JobsRepository(session)
        teardowns_repo = TeardownsRepository(session)
        ads_repo = AdsRepository(session)

        job = jobs_repo.get(job_id)
        if not job:
            error = f"job_not_found: {job_id}"
            activity.logger.error(
                "ads_teardown.job_missing",
                extra={"org_id": org_id, "client_id": client_id, "ad_id": ad_id, "job_id": job_id},
            )
            return {"ad_id": ad_id, "job_id": job_id, "status": "failed", "error": error}

        if job.job_type != JOB_TYPE_ADD_CREATIVE_BREAKDOWN or job.subject_type != SUBJECT_TYPE_AD:
            error = "job_type_mismatch"
            activity.logger.error(
                "ads_teardown.job_type_mismatch",
                extra={
                    "org_id": org_id,
                    "client_id": client_id,
                    "ad_id": ad_id,
                    "job_id": job_id,
                    "job_type": job.job_type,
                    "subject_type": job.subject_type,
                },
            )
            return {"ad_id": ad_id, "job_id": job_id, "status": "failed", "error": error}

        if job.status != JOB_STATUS_SUCCEEDED:
            error = f"job_not_succeeded: {job.status}"
            activity.logger.warning(
                "ads_teardown.job_not_succeeded",
                extra={
                    "org_id": org_id,
                    "client_id": client_id,
                    "ad_id": ad_id,
                    "job_id": job_id,
                    "status": job.status,
                },
            )
            return {"ad_id": ad_id, "job_id": job_id, "status": "skipped", "error": error}

        # Construct teardown header fields from segmented sections if available.
        output = job.output or {}
        parsed = output.get("parsed") or {}
        sections = parsed.get("sections") or {}
        header_fields = extract_teardown_header_fields(sections)
        one_liner = header_fields.get("one_liner")
        algorithmic_thesis = header_fields.get("algorithmic_thesis")
        hook_score = header_fields.get("hook_score")

        # Build ad copy evidence blocks from the underlying Ad record.
        ad: Optional[Ad] = ads_repo.session.get(Ad, job.subject_id)
        evidence_items: List[TeardownEvidenceInput] = []
        if ad:
            if ad.body_text:
                evidence_items.append(
                    TeardownEvidenceInput(
                        evidence_type="ad_copy_block",
                        copy_field="primary_text",
                        copy_text=ad.body_text,
                    )
                )
            if ad.headline:
                evidence_items.append(
                    TeardownEvidenceInput(
                        evidence_type="ad_copy_block",
                        copy_field="headline",
                        copy_text=ad.headline,
                    )
                )
            if ad.cta_text:
                evidence_items.append(
                    TeardownEvidenceInput(
                        evidence_type="ad_copy_block",
                        copy_field="cta_label",
                        copy_text=ad.cta_text,
                    )
                )
            if ad.landing_url:
                evidence_items.append(
                    TeardownEvidenceInput(
                        evidence_type="ad_copy_block",
                        copy_field="destination_url",
                        copy_text=ad.landing_url,
                    )
                )

        # Simple assertions derived from header fields.
        assertions: List[TeardownAssertionInput] = []
        if one_liner:
            assertions.append(
                TeardownAssertionInput(
                    assertion_type="why_it_wins",
                    assertion_text=one_liner,
                )
            )
        if algorithmic_thesis:
            assertions.append(
                TeardownAssertionInput(
                    assertion_type="algorithmic_thesis",
                    assertion_text=algorithmic_thesis,
                )
            )

        # Additional evidence derived from transcript and storyboard sections.
        transcript_rows = extract_transcript_rows(sections)
        storyboard_rows = extract_storyboard_rows(sections)

        speaker_map = {
            "NARRATOR": "narrator",
            "FOUNDER": "spokesperson",
            "CREATOR": "testimonial",
            "CUSTOMER": "testimonial",
            "ON-CAMERA": "actor",
        }

        for row in transcript_rows:
            speaker_label = (row.get("speaker_label") or "").upper() or None
            speaker_role = speaker_map.get(speaker_label, "unknown") if speaker_label else None
            evidence_items.append(
                TeardownEvidenceInput(
                    evidence_type="transcript_segment",
                    start_ms=row.get("start_ms"),
                    end_ms=row.get("end_ms"),
                    speaker_role=speaker_role,
                    spoken_text=row.get("spoken_text"),
                    onscreen_text=row.get("onscreen_text"),
                    audio_notes=row.get("audio_notes"),
                )
            )

        for row in storyboard_rows:
            scene_no = row.get("scene_no")
            if scene_no is None:
                continue
            evidence_items.append(
                TeardownEvidenceInput(
                    evidence_type="storyboard_scene",
                    start_ms=row.get("start_ms"),
                    end_ms=row.get("end_ms"),
                    scene_no=scene_no,
                    visual_description=row.get("visual_description"),
                    action_blocking=row.get("action_blocking"),
                    narrative_job=row.get("narrative_job"),
                    onscreen_text=row.get("onscreen_text"),
                )
            )

        # Construct payload using the job output as the canonical raw_payload.
        raw_payload: Dict[str, Any] = {
            "ad_breakdown_job": job.output or {},
            "raw_output_text": job.raw_output_text,
            "job_metadata": {
                "job_id": str(job.id),
                "job_type": job.job_type,
                "subject_type": job.subject_type,
                "subject_id": str(job.subject_id),
                "model": (job.input or {}).get("model"),
                "prompt_sha256": (job.input or {}).get("prompt_sha256"),
            },
        }

        teardown_request = TeardownUpsertRequest(
            ad_id=str(job.subject_id),
            client_id=client_id,
            campaign_id=None,
            research_run_id=research_run_id,
            schema_version=1,
            captured_at=None,
            funnel_stage=None,
            one_liner=one_liner,
            algorithmic_thesis=algorithmic_thesis,
            hook_score=hook_score,
            raw_payload=raw_payload,
            evidence_items=evidence_items,
            assertions=assertions,
        )

        try:
            result = teardowns_repo.upsert_teardown(
                org_id=org_id,
                payload=teardown_request,
                created_by_user_id=None,
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            activity.logger.error(
                "ads_teardown.persist_error",
                extra={"org_id": org_id, "client_id": client_id, "ad_id": ad_id, "job_id": job_id, "error": error},
            )
            return {"ad_id": ad_id, "job_id": job_id, "status": "failed", "error": error}

        activity.logger.info(
            "ads_teardown.persisted",
            extra={"org_id": org_id, "client_id": client_id, "ad_id": ad_id, "job_id": job_id, "teardown_id": result.id},
        )
        return {"ad_id": ad_id, "job_id": job_id, "status": "succeeded", "teardown_id": result.id}
