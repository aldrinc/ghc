from __future__ import annotations

import hashlib
import mimetypes
import os
import time
from typing import Any, Dict, List, Tuple

import httpx
import google.generativeai as genai
from temporalio import activity

from app.config import settings
from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum
from app.db.models import DesignSystem
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.swipes import CompanySwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.services.creative_service_client import (
    CreativeServiceClient,
    CreativeServiceConfigError,
    CreativeServiceRequestError,
)
from app.services.swipe_prompt import (
    SwipePromptParseError,
    build_swipe_context_block,
    extract_new_image_prompt_from_markdown,
    load_swipe_to_image_ad_prompt,
)

# Reuse existing asset generation helpers to keep asset storage + product reference syncing consistent.
from app.temporal.activities.asset_activities import (  # noqa: E402
    _build_image_reference_text,
    _create_generated_asset_from_url,
    _ensure_remote_reference_asset_ids,
    _extract_brief,
    _retention_expires_at,
    _select_product_reference_assets,
    _stable_idempotency_key,
    _validate_brief_scope,
)


_GEMINI_CONFIGURED = False


def _ensure_gemini_configured() -> None:
    global _GEMINI_CONFIGURED
    if _GEMINI_CONFIGURED:
        return
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)
    _GEMINI_CONFIGURED = True


def _download_bytes(url: str, *, max_bytes: int, timeout_seconds: float) -> Tuple[bytes, str]:
    with httpx.Client(follow_redirects=True, timeout=timeout_seconds) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if not content_type:
                raise RuntimeError(f"Swipe image response missing content-type header (url={url})")
            chunks: List[bytes] = []
            total = 0
            for chunk in resp.iter_bytes(8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"swipe_image_too_large: {total} bytes (limit {max_bytes})")
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                raise RuntimeError(f"Swipe image download returned empty bytes (url={url})")
            return data, content_type


def _resolve_swipe_image(
    *,
    session,
    org_id: str,
    company_swipe_id: str | None,
    swipe_image_url: str | None,
) -> Tuple[bytes, str, str]:
    """
    Return (bytes, mime_type, source_url) for the competitor swipe image.
    """
    if bool(company_swipe_id) == bool(swipe_image_url):
        raise ValueError("Exactly one of company_swipe_id or swipe_image_url must be provided.")

    if swipe_image_url:
        data, mime_type = _download_bytes(
            swipe_image_url,
            max_bytes=int(os.getenv("SWIPE_IMAGE_MAX_BYTES", str(18 * 1024 * 1024))),
            timeout_seconds=float(os.getenv("SWIPE_IMAGE_DOWNLOAD_TIMEOUT", "30")),
        )
        return data, mime_type, swipe_image_url

    repo = CompanySwipesRepository(session)
    swipe = repo.get_asset(org_id=org_id, swipe_id=company_swipe_id or "")
    if not swipe:
        raise ValueError(f"Company swipe not found: {company_swipe_id}")
    media = repo.list_media(org_id=org_id, swipe_asset_id=str(swipe.id))
    if not media:
        raise ValueError(f"Company swipe has no media: {company_swipe_id}")

    # Prefer image media.
    selected = None
    for item in media:
        mt = (getattr(item, "mime_type", None) or "").lower()
        if mt.startswith("image/"):
            selected = item
            break
    if not selected:
        selected = media[0]

    url = (
        getattr(selected, "download_url", None)
        or getattr(selected, "url", None)
        or getattr(selected, "thumbnail_url", None)
    )
    if not url:
        raise ValueError(f"Swipe media is missing a usable url (company_swipe_id={company_swipe_id})")

    data, mime_type = _download_bytes(
        url,
        max_bytes=int(os.getenv("SWIPE_IMAGE_MAX_BYTES", str(18 * 1024 * 1024))),
        timeout_seconds=float(os.getenv("SWIPE_IMAGE_DOWNLOAD_TIMEOUT", "30")),
    )
    return data, mime_type, str(url)


def _extract_brand_context(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
) -> Dict[str, Any]:
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=org_id, client_id=client_id)
    if not client:
        raise ValueError(f"Client not found: {client_id}")

    product = ProductsRepository(session).get(org_id=org_id, product_id=product_id)
    if not product:
        raise ValueError(f"Product not found: {product_id}")
    if str(getattr(product, "client_id", "")) != str(client_id):
        raise ValueError("Product does not belong to the provided client_id.")

    artifacts_repo = ArtifactsRepository(session)
    canon_artifact = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.client_canon,
    )
    if not canon_artifact or not isinstance(canon_artifact.data, dict):
        raise ValueError("Client canon (creative brief) is required but was not found for this client/product.")
    canon = canon_artifact.data

    design_system_tokens: Dict[str, Any] = {}
    design_system_id = getattr(client, "design_system_id", None)
    if design_system_id:
        ds = session.get(DesignSystem, design_system_id)
        if ds and isinstance(ds.tokens, dict):
            design_system_tokens = ds.tokens

    return {
        "client_name": getattr(client, "name", None),
        "product_title": getattr(product, "title", None),
        "canon": canon,
        "design_system_tokens": design_system_tokens,
    }


def _format_audience_from_canon(canon: Dict[str, Any]) -> str | None:
    icps = canon.get("icps")
    if not isinstance(icps, list) or not icps:
        return None
    first = icps[0] if isinstance(icps[0], dict) else None
    if not first:
        return None
    name = first.get("name") if isinstance(first.get("name"), str) else None
    pains = first.get("pains") if isinstance(first.get("pains"), list) else []
    gains = first.get("gains") if isinstance(first.get("gains"), list) else []
    jobs = first.get("jobsToBeDone") if isinstance(first.get("jobsToBeDone"), list) else []
    parts: List[str] = []
    if name and name.strip():
        parts.append(f"ICP: {name.strip()}")
    if pains:
        pains_str = "; ".join(str(p).strip() for p in pains if isinstance(p, str) and p.strip())
        if pains_str:
            parts.append(f"Pains: {pains_str}")
    if gains:
        gains_str = "; ".join(str(g).strip() for g in gains if isinstance(g, str) and g.strip())
        if gains_str:
            parts.append(f"Gains: {gains_str}")
    if jobs:
        jobs_str = "; ".join(str(j).strip() for j in jobs if isinstance(j, str) and j.strip())
        if jobs_str:
            parts.append(f"Jobs: {jobs_str}")
    return " | ".join(parts) if parts else None


def _research_copy_bank_from_canon(canon: Dict[str, Any]) -> List[str]:
    out: List[str] = []

    voc = canon.get("voiceOfCustomer")
    if isinstance(voc, dict):
        for key in ("quotes", "objections", "triggers", "languagePatterns"):
            items = voc.get(key)
            if isinstance(items, list):
                out.extend([str(x).strip() for x in items if isinstance(x, str) and x.strip()])

    research_highlights = canon.get("research_highlights")
    if isinstance(research_highlights, dict):
        for step_key in sorted(research_highlights.keys()):
            value = research_highlights.get(step_key)
            if isinstance(value, str) and value.strip():
                out.append(f"[precanon:{step_key}] {value.strip()}")

    precanon = canon.get("precanon_research")
    if isinstance(precanon, dict):
        step_summaries = precanon.get("step_summaries")
        if isinstance(step_summaries, dict):
            for step_key in sorted(step_summaries.keys()):
                value = step_summaries.get(step_key)
                if isinstance(value, str) and value.strip():
                    out.append(f"[precanon:{step_key}] {value.strip()}")

    return out


def _brand_colors_fonts_from_design_tokens(tokens: Dict[str, Any]) -> str | None:
    if not isinstance(tokens, dict) or not tokens:
        return None
    css_vars = tokens.get("cssVars")
    if not isinstance(css_vars, dict):
        css_vars = {}

    font_heading = css_vars.get("--font-heading")
    font_body = css_vars.get("--font-sans") or css_vars.get("--font-body")
    color_brand = css_vars.get("--color-brand")
    color_page_bg = css_vars.get("--color-page-bg")
    color_bg = css_vars.get("--color-bg")

    parts: List[str] = []
    if isinstance(font_heading, str) and font_heading.strip():
        parts.append(f"Heading font: {font_heading.strip()}")
    if isinstance(font_body, str) and font_body.strip():
        parts.append(f"Body font: {font_body.strip()}")
    if isinstance(color_brand, str) and color_brand.strip():
        parts.append(f"Brand color: {color_brand.strip()}")
    if isinstance(color_page_bg, str) and color_page_bg.strip():
        parts.append(f"Page bg: {color_page_bg.strip()}")
    if isinstance(color_bg, str) and color_bg.strip():
        parts.append(f"Surface bg: {color_bg.strip()}")

    return " | ".join(parts) if parts else None


def _must_avoid_claims_from_canon(canon: Dict[str, Any]) -> List[str]:
    constraints = canon.get("constraints")
    if not isinstance(constraints, dict):
        return []
    out: List[str] = []
    for key in ("legal", "compliance", "bannedTopics", "bannedPhrases"):
        items = constraints.get(key)
        if isinstance(items, list):
            out.extend([str(x).strip() for x in items if isinstance(x, str) and x.strip()])
    return out


def _poll_image_job(
    *,
    creative_client: CreativeServiceClient,
    job_id: str,
) -> Any:
    poll_interval = float(settings.CREATIVE_SERVICE_POLL_INTERVAL_SECONDS or 2.0)
    poll_timeout = float(settings.CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS or 300.0)
    if poll_interval <= 0:
        raise ValueError("CREATIVE_SERVICE_POLL_INTERVAL_SECONDS must be greater than zero.")
    if poll_timeout <= 0:
        raise ValueError("CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS must be greater than zero.")

    started = time.monotonic()
    while True:
        job = creative_client.get_image_ads_job(job_id=job_id)
        if job.status in ("succeeded", "failed"):
            return job
        if (time.monotonic() - started) > poll_timeout:
            raise RuntimeError(
                f"Timed out waiting for image ads job completion (job_id={job_id}, timeout_seconds={poll_timeout})"
            )
        time.sleep(poll_interval)


def _extract_gemini_text(result: Any) -> str | None:
    """
    Extract text from a google.generativeai generation result.

    Note: In some library versions, `result.text` raises instead of returning a string.
    """
    try:
        text = getattr(result, "text", None)
    except Exception:
        text = None
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(result, "candidates", None)
    if not candidates:
        return None
    first = candidates[0]
    if not first:
        return None
    content = getattr(first, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return None

    texts: List[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str) and part_text:
            texts.append(part_text)
    joined = "\n".join(texts).strip()
    return joined or None


@activity.defn(name="swipes.generate_swipe_image_ad")
def generate_swipe_image_ad_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate ONE (or N) image ad(s) by adapting a competitor swipe image.

    Flow:
      1) Use Gemini (vision) with the swipe prompt template to produce a dense generation-ready image prompt.
      2) Send that prompt + reference images to the creative service (Freestyle) to render the final image(s).
      3) Persist generated assets attached to the provided asset brief.
    """

    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params["product_id"]
    campaign_id = params.get("campaign_id")
    asset_brief_id = params["asset_brief_id"]
    requirement_index = int(params.get("requirement_index") or 0)
    workflow_run_id = params.get("workflow_run_id")

    company_swipe_id: str | None = params.get("company_swipe_id")
    swipe_image_url: str | None = params.get("swipe_image_url")

    model = params.get("model") or os.getenv("SWIPE_PROMPT_MODEL")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model is required (provide params.model or set SWIPE_PROMPT_MODEL).")

    max_output_tokens = int(params.get("max_output_tokens") or os.getenv("SWIPE_PROMPT_MAX_OUTPUT_TOKENS") or "6000")
    aspect_ratio = (params.get("aspect_ratio") or "1:1").strip()
    count = int(params.get("count") or 1)
    if count <= 0:
        raise ValueError("count must be >= 1 for swipe image ad generation.")
    render_count = max(6, count)

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as log_session:
            WorkflowsRepository(log_session).log_activity(
                workflow_run_id=str(workflow_run_id),
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

        log_activity(
            "swipe_image_ad",
            "started",
            payload_in={
            "asset_brief_id": asset_brief_id,
            "campaign_id": campaign_id,
            "company_swipe_id": company_swipe_id,
            "swipe_image_url": swipe_image_url,
            "model": model,
            "count": count,
            "render_count": render_count,
            "aspect_ratio": aspect_ratio,
            "requirement_index": requirement_index,
        },
    )

    try:
        creative_client = CreativeServiceClient()
    except CreativeServiceConfigError as exc:
        raise RuntimeError(str(exc)) from exc

    prompt_template, prompt_sha = load_swipe_to_image_ad_prompt()

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        brief, brief_artifact_id = _extract_brief(
            artifacts_repo=artifacts_repo,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
        )
        funnel_id = _validate_brief_scope(
            session=session,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
            brief=brief,
        )

        requirements_raw = brief.get("requirements") or []
        if not isinstance(requirements_raw, list) or not requirements_raw:
            raise ValueError("Asset brief has no requirements.")
        if requirement_index < 0 or requirement_index >= len(requirements_raw):
            raise ValueError(
                f"requirement_index out of range for asset brief {asset_brief_id}. "
                f"expected 0..{len(requirements_raw) - 1} got {requirement_index}"
            )
        requirement = requirements_raw[requirement_index]
        if not isinstance(requirement, dict):
            raise ValueError("Asset brief requirement must be an object.")

        channel_id = (requirement.get("channel") or "meta").strip()
        fmt = (requirement.get("format") or "image").strip()
        angle = requirement.get("angle")
        if not isinstance(angle, str) or not angle.strip():
            raise ValueError("Asset brief requirement is missing angle (required for swipe prompt generation).")
        hook = requirement.get("hook")

        # Creative brief / brand context.
        brand_ctx = _extract_brand_context(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
        )
        client_name = brand_ctx.get("client_name") or ""
        product_title = brand_ctx.get("product_title") or ""
        canon = brand_ctx.get("canon") if isinstance(brand_ctx.get("canon"), dict) else {}
        tokens = brand_ctx.get("design_system_tokens") if isinstance(brand_ctx.get("design_system_tokens"), dict) else {}

        audience = _format_audience_from_canon(canon)
        brand_colors_fonts = _brand_colors_fonts_from_design_tokens(tokens)
        must_avoid_claims = _must_avoid_claims_from_canon(canon)
        research_copy_bank = _research_copy_bank_from_canon(canon)
        if not research_copy_bank:
            raise ValueError(
                "No research copy bank found in client canon (voiceOfCustomer/research_highlights/precanon_research). "
                "Cannot generate research-grounded emotional copy."
            )

        # Swipe image bytes.
        swipe_bytes, swipe_mime_type, swipe_source_url = _resolve_swipe_image(
            session=session,
            org_id=org_id,
            company_swipe_id=company_swipe_id,
            swipe_image_url=swipe_image_url,
        )

        # Build the LLM prompt context.
        context_block = build_swipe_context_block(
            brand_name=str(client_name),
            product_name=str(product_title),
            angle=(angle.strip() + (f" | Hook: {hook.strip()}" if isinstance(hook, str) and hook.strip() else "")),
            audience=audience,
            brand_colors_fonts=brand_colors_fonts,
            must_avoid_claims=must_avoid_claims,
            assets=None,
            research_copy_bank=research_copy_bank,
        )

        # Run Gemini to generate the generation-ready image prompt.
        _ensure_gemini_configured()
        model_name = model if model.startswith("models/") else f"models/{model}"
        generation_config = {
            "temperature": 0.2,
            "max_output_tokens": max_output_tokens,
        }
        model_client = genai.GenerativeModel(model_name=model_name, generation_config=generation_config)
        contents: List[Any] = [context_block, prompt_template, {"mime_type": swipe_mime_type, "data": swipe_bytes}]

        try:
            result = model_client.generate_content(contents, request_options={"timeout": 120})
            raw_output = _extract_gemini_text(result)
            if not raw_output:
                raise RuntimeError("Gemini returned no text for swipe prompt generation")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Swipe prompt generation failed: {exc}") from exc

        try:
            image_prompt = extract_new_image_prompt_from_markdown(raw_output)
        except SwipePromptParseError as exc:
            raise RuntimeError(f"Failed to parse swipe prompt output: {exc}") from exc

        # Prepare creative service references (product + swipe).
        product_reference_assets = _select_product_reference_assets(
            session=session,
            org_id=org_id,
            product_id=product_id,
        )
        product_reference_remote_ids = _ensure_remote_reference_asset_ids(
            session=session,
            org_id=org_id,
            creative_client=creative_client,
            references=product_reference_assets,
        )
        product_reference_text = _build_image_reference_text(product_reference_assets)

        # Upload swipe image to creative service.
        ext = mimetypes.guess_extension(swipe_mime_type) or ".bin"
        if ext == ".bin":
            raise RuntimeError(f"Unable to infer file extension for swipe image mime type: {swipe_mime_type}")
        swipe_file_name = f"swipe_{company_swipe_id or 'url'}{ext}"
        uploaded_swipe = creative_client.upload_asset(
            kind="image",
            source="upload",
            file_name=swipe_file_name,
            file_bytes=swipe_bytes,
            content_type=swipe_mime_type,
            title="Competitor swipe reference",
            description="Competitor swipe reference for layout/composition (do not copy branding)",
            metadata_json={"source": "competitor_swipe", "companySwipeId": company_swipe_id, "sourceUrl": swipe_source_url},
            generate_proxy=True,
        )
        swipe_remote_asset_id = (uploaded_swipe.id or "").strip()
        if not swipe_remote_asset_id:
            raise RuntimeError("Creative service returned an empty asset id for uploaded swipe reference image")

        reference_asset_ids = [swipe_remote_asset_id, *product_reference_remote_ids]
        reference_text = "\n\n".join(
            [
                product_reference_text,
                f"Competitor swipe layout reference (do not copy branding): {swipe_source_url}",
            ]
        ).strip()

        idempotency_key = _stable_idempotency_key(
            org_id,
            client_id,
            str(campaign_id or ""),
            asset_brief_id,
            "swipe_image_ad_v1",
            str(requirement_index),
            str(company_swipe_id or swipe_source_url or ""),
            aspect_ratio,
            str(render_count),
            model,
            prompt_sha,
        )

        image_payload = CreativeServiceImageAdsCreateIn(
            prompt=image_prompt,
            reference_text=reference_text,
            reference_asset_ids=reference_asset_ids,
            count=render_count,
            aspect_ratio=aspect_ratio,
            client_request_id=idempotency_key,
        )

        try:
            created_job = creative_client.create_image_ads(payload=image_payload, idempotency_key=idempotency_key)
        except (CreativeServiceRequestError, RuntimeError) as exc:
            raise RuntimeError(f"Image ad generation request failed: {exc}") from exc

        completed_job = _poll_image_job(creative_client=creative_client, job_id=created_job.id)
        if completed_job.status != "succeeded":
            raise RuntimeError(f"Image generation failed (job_id={completed_job.id}): {completed_job.error_detail or 'unknown error'}")

        if len(completed_job.outputs) < count:
            raise RuntimeError(
                "Image generation returned fewer outputs than requested. "
                f"requested={count} returned={len(completed_job.outputs)}"
            )

        retention_expires_at = _retention_expires_at()
        created_asset_ids: List[str] = []

        for local_index, output in enumerate(completed_job.outputs[:count]):
            if not output.primary_url:
                raise RuntimeError(
                    f"Image generation output missing primary_url (job_id={completed_job.id}, output_index={local_index})"
                )

            extra_ai_metadata: Dict[str, Any] = {
                "remoteJobId": completed_job.id,
                "remoteOutputIndex": output.output_index,
                "remoteAssetId": output.asset_id,
                "promptUsed": output.prompt_used,
                "swipeCompanyId": company_swipe_id,
                "swipeSourceUrl": swipe_source_url,
                "swipeRemoteAssetId": swipe_remote_asset_id,
                "swipePromptModel": model,
                "swipePromptTemplateSha256": prompt_sha,
                "swipePromptMarkdownSha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
                "swipePromptMarkdownPreview": raw_output[:4000],
            }

            local_asset_id = _create_generated_asset_from_url(
                session=session,
                org_id=org_id,
                client_id=client_id,
                campaign_id=campaign_id,
                product_id=product_id,
                funnel_id=funnel_id,
                brief_artifact_id=brief_artifact_id,
                asset_brief_id=asset_brief_id,
                variant_id=brief.get("variantId") or brief.get("variant_id"),
                variant_index=None,
                channel_id=channel_id,
                fmt=fmt,
                requirement_index=requirement_index,
                requirement=requirement,
                primary_url=output.primary_url,
                prompt=image_prompt,
                source_kind="swipe_adaptation",
                expected_asset_kind="image",
                retention_expires_at=retention_expires_at,
                extra_ai_metadata=extra_ai_metadata,
                attach_to_product=True,
            )
            created_asset_ids.append(local_asset_id)

        log_activity(
            "swipe_image_ad",
            "succeeded",
            payload_out={
                "asset_ids": created_asset_ids,
                "job_id": completed_job.id,
                "prompt_sha256": prompt_sha,
                "swipe_prompt_model": model,
            },
        )

        return {
            "asset_ids": created_asset_ids,
            "job_id": completed_job.id,
            "image_prompt": image_prompt,
            "swipe_prompt_markdown": raw_output,
            "swipe_prompt_model": model,
            "prompt_template_sha256": prompt_sha,
            "reference_asset_ids": reference_asset_ids,
        }
