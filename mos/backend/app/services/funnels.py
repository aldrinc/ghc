from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import hashlib
import os
import re
import mimetypes
import time
from typing import Any, Optional

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.enums import (
    AssetSourceEnum,
    AssetStatusEnum,
    FunnelPageVersionSourceEnum,
    FunnelPageVersionStatusEnum,
    FunnelPublicationLinkKindEnum,
    FunnelStatusEnum,
)
from app.db.models import (
    Campaign,
    Funnel,
    Asset,
    FunnelPage,
    FunnelPageVersion,
    FunnelPublication,
    FunnelPublicationLink,
    FunnelPublicationPage,
)
from app.services.media_storage import MediaStorage


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "page"


def default_puck_data() -> dict[str, Any]:
    return {"root": {"props": {"title": "", "description": ""}}, "content": [], "zones": {}}


def _walk_json(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


@dataclass(frozen=True)
class InternalLink:
    to_page_id: str
    label: Optional[str] = None
    kind: str = "cta"
    meta: dict[str, Any] | None = None


def extract_internal_links(puck_data: dict[str, Any]) -> list[InternalLink]:
    links: list[InternalLink] = []
    for obj in _walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "Button":
            continue
        props = obj.get("props") if isinstance(obj.get("props"), dict) else {}
        if props.get("linkType") != "funnelPage":
            continue
        target = props.get("targetPageId")
        if not isinstance(target, str) or not target:
            continue
        label = props.get("label")
        if not isinstance(label, str):
            label = None
        meta: dict[str, Any] = {}
        block_id = obj.get("id")
        if not isinstance(block_id, str) or not block_id:
            block_id = props.get("id") if isinstance(props.get("id"), str) else None
        if isinstance(block_id, str) and block_id:
            meta["blockId"] = block_id
        links.append(InternalLink(to_page_id=target, label=label, kind="cta", meta=meta))
    return links


def rewrite_internal_target_ids(puck_data: dict[str, Any], id_map: dict[str, str]) -> dict[str, Any]:
    cloned = deepcopy(puck_data)
    for obj in _walk_json(cloned):
        if not isinstance(obj, dict):
            continue
        if "targetPageId" in obj and isinstance(obj["targetPageId"], str):
            old = obj["targetPageId"]
            if old in id_map:
                obj["targetPageId"] = id_map[old]
        props = obj.get("props")
        if isinstance(props, dict) and "targetPageId" in props and isinstance(props["targetPageId"], str):
            old = props["targetPageId"]
            if old in id_map:
                props["targetPageId"] = id_map[old]
    return cloned


def generate_unique_slug(
    session: Session, *, funnel_id: str, desired_slug: str, exclude_page_id: Optional[str] = None
) -> str:
    base = slugify(desired_slug)
    suffix = 0
    while True:
        slug = base if suffix == 0 else f"{base}-{suffix + 1}"
        stmt = select(FunnelPage.id).where(FunnelPage.funnel_id == funnel_id, FunnelPage.slug == slug)
        if exclude_page_id:
            stmt = stmt.where(FunnelPage.id != exclude_page_id)
        exists = session.execute(stmt).first()
        if not exists:
            return slug
        suffix += 1


def generate_unique_funnel_route_slug(
    session: Session, *, desired_slug: str, exclude_funnel_id: Optional[str] = None
) -> str:
    base = slugify(desired_slug) or "funnel"
    suffix = 0
    while True:
        slug = base if suffix == 0 else f"{base}-{suffix + 1}"
        stmt = select(Funnel.id).where(Funnel.route_slug == slug)
        if exclude_funnel_id:
            stmt = stmt.where(Funnel.id != exclude_funnel_id)
        exists = session.execute(stmt).first()
        if not exists:
            return slug
        suffix += 1


def publish_funnel(*, session: Session, org_id: str, user_id: str, funnel_id: str) -> FunnelPublication:
    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise ValueError("Funnel not found")
    if funnel.status == FunnelStatusEnum.disabled:
        raise ValueError("Funnel is disabled")

    pages = list(
        session.scalars(
            select(FunnelPage)
            .where(FunnelPage.funnel_id == funnel.id)
            .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
        ).all()
    )
    if not pages:
        raise ValueError("Funnel has no pages")

    if not funnel.entry_page_id:
        raise ValueError("Entry page not set")
    page_id_set = {str(page.id) for page in pages}
    if str(funnel.entry_page_id) not in page_id_set:
        raise ValueError("Entry page does not belong to funnel")

    version_by_page: dict[str, FunnelPageVersion] = {}
    for page in pages:
        draft = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page.id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
            )
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        ).first()
        approved = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page.id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.approved,
            )
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        ).first()
        version = draft or approved
        if not version:
            raise ValueError(f"Page '{page.name}' has no saved version to publish")
        # Compliance gate: prevent publishing synthetic testimonials in production.
        if settings.ENVIRONMENT.lower() in {"prod", "production"} and not settings.ALLOW_SYNTHETIC_TESTIMONIALS_IN_PRODUCTION:
            md = version.ai_metadata if isinstance(version.ai_metadata, dict) else {}
            is_synthetic = False
            if md.get("kind") == "testimonial_generation" and md.get("synthetic") is True:
                is_synthetic = True
            prov = md.get("testimonialsProvenance")
            if isinstance(prov, dict) and prov.get("source") == "synthetic":
                is_synthetic = True
            if is_synthetic:
                raise ValueError(
                    f"Page '{page.name}' contains synthetic testimonials and cannot be published in production. "
                    "Replace with production testimonials or remove testimonials before publishing."
                )
        version_by_page[str(page.id)] = version

    publication = FunnelPublication(
        funnel_id=funnel.id,
        entry_page_id=funnel.entry_page_id,
        created_by=user_id,
    )
    session.add(publication)
    session.flush()

    extracted_links: list[tuple[str, InternalLink]] = []
    for page in pages:
        version = version_by_page[str(page.id)]
        for link in extract_internal_links(version.puck_data):
            if link.to_page_id not in page_id_set:
                raise ValueError(f"Invalid internal link target: {link.to_page_id}")
            extracted_links.append((str(page.id), link))
    for page in pages:
        if not page.next_page_id:
            continue
        next_page_id = str(page.next_page_id)
        if next_page_id == str(page.id):
            raise ValueError("Next page cannot reference itself")
        if next_page_id not in page_id_set:
            raise ValueError("Next page does not belong to funnel")
        auto_link = InternalLink(
            to_page_id=next_page_id,
            label="Next page",
            kind="auto",
            meta={"source": "next_page"},
        )
        extracted_links.append((str(page.id), auto_link))

    for page in pages:
        session.add(
            FunnelPublicationPage(
                publication_id=publication.id,
                page_id=page.id,
                page_version_id=version_by_page[str(page.id)].id,
                slug_at_publish=page.slug,
            )
        )

    for from_page_id, link in extracted_links:
        kind = FunnelPublicationLinkKindEnum.cta
        if link.kind:
            kind = FunnelPublicationLinkKindEnum(link.kind)
        session.add(
            FunnelPublicationLink(
                publication_id=publication.id,
                from_page_id=from_page_id,
                to_page_id=link.to_page_id,
                kind=kind,
                label=link.label,
                meta=link.meta or {},
            )
        )

    funnel.active_publication_id = publication.id
    funnel.status = FunnelStatusEnum.published

    session.commit()
    session.refresh(publication)
    return publication


def duplicate_funnel(
    *,
    session: Session,
    org_id: str,
    source_funnel_id: str,
    target_campaign_id: Optional[str],
    name: Optional[str],
    copy_mode: str,
) -> Funnel:
    source = session.scalars(
        select(Funnel).where(Funnel.org_id == org_id, Funnel.id == source_funnel_id)
    ).first()
    if not source:
        raise ValueError("Funnel not found")

    target_campaign: Optional[Campaign] = None
    if target_campaign_id:
        target_campaign = session.scalars(
            select(Campaign).where(Campaign.org_id == org_id, Campaign.id == target_campaign_id)
        ).first()
        if not target_campaign:
            raise ValueError("Target campaign not found")
        if str(target_campaign.client_id) != str(source.client_id):
            raise ValueError("Target campaign must belong to the same client")

    new_funnel = Funnel(
        org_id=source.org_id,
        client_id=source.client_id,
        campaign_id=target_campaign.id if target_campaign else None,
        experiment_spec_id=source.experiment_spec_id
        if target_campaign and str(target_campaign.id) == str(source.campaign_id)
        else None,
        design_system_id=source.design_system_id,
        product_id=source.product_id,
        selected_offer_id=source.selected_offer_id,
        name=name or f"{source.name} (Copy)",
        description=source.description,
        status=FunnelStatusEnum.draft,
        route_slug=generate_unique_funnel_route_slug(session, desired_slug=name or f"{source.name} (Copy)"),
        active_publication_id=None,
    )
    session.add(new_funnel)
    session.flush()

    source_pages = list(
        session.scalars(
            select(FunnelPage)
            .where(FunnelPage.funnel_id == source.id)
            .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
        ).all()
    )
    id_map: dict[str, str] = {}
    new_pages: dict[str, FunnelPage] = {}
    for page in source_pages:
        new_page = FunnelPage(
            funnel_id=new_funnel.id,
            name=page.name,
            slug=page.slug,
            ordering=page.ordering,
            template_id=page.template_id,
            design_system_id=page.design_system_id,
        )
        session.add(new_page)
        session.flush()
        id_map[str(page.id)] = str(new_page.id)
        new_pages[str(page.id)] = new_page

    for page in source_pages:
        if not page.next_page_id:
            continue
        new_page = new_pages.get(str(page.id))
        next_page_id = id_map.get(str(page.next_page_id))
        if new_page and next_page_id:
            new_page.next_page_id = next_page_id

    if source.entry_page_id and str(source.entry_page_id) in id_map:
        new_funnel.entry_page_id = id_map[str(source.entry_page_id)]

    def latest_version(page_id: str, status: FunnelPageVersionStatusEnum) -> Optional[FunnelPageVersion]:
        return session.scalars(
            select(FunnelPageVersion)
            .where(FunnelPageVersion.page_id == page_id, FunnelPageVersion.status == status)
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        ).first()

    publication_pages_by_page_id: dict[str, str] = {}
    if copy_mode == "activePublication" and source.active_publication_id:
        pub_pages = list(
            session.scalars(
                select(FunnelPublicationPage).where(
                    FunnelPublicationPage.publication_id == source.active_publication_id
                )
            ).all()
        )
        publication_pages_by_page_id = {str(pp.page_id): str(pp.page_version_id) for pp in pub_pages}

    for page in source_pages:
        new_page_id = id_map[str(page.id)]
        versions_to_copy: list[FunnelPageVersion] = []
        if publication_pages_by_page_id:
            version_id = publication_pages_by_page_id.get(str(page.id))
            if version_id:
                v = session.scalars(select(FunnelPageVersion).where(FunnelPageVersion.id == version_id)).first()
                if v:
                    versions_to_copy.append(v)
        else:
            approved = latest_version(str(page.id), FunnelPageVersionStatusEnum.approved)
            if approved:
                versions_to_copy.append(approved)
            draft = latest_version(str(page.id), FunnelPageVersionStatusEnum.draft)
            if draft and (not approved or str(draft.id) != str(approved.id)):
                versions_to_copy.append(draft)

        for v in versions_to_copy:
            session.add(
                FunnelPageVersion(
                    page_id=new_page_id,
                    status=v.status,
                    puck_data=rewrite_internal_target_ids(v.puck_data, id_map),
                    source=FunnelPageVersionSourceEnum.duplicate,
                    ai_metadata=v.ai_metadata,
                    created_at=datetime.now(timezone.utc),
                )
            )

    session.commit()
    session.refresh(new_funnel)
    return new_funnel


def _extract_first_inline_image(response_json: dict[str, Any]) -> tuple[bytes, str]:
    candidates = response_json.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") if isinstance(cand, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            data = inline.get("data")
            mime_type = inline.get("mimeType") or inline.get("mime_type") or "image/png"
            if isinstance(data, str) and data:
                return base64.b64decode(data), str(mime_type)
    raise RuntimeError("Gemini response did not include inline image data")


def _summarize_gemini_response_for_debug(response_json: Any) -> str:
    if not isinstance(response_json, dict):
        return f"type={type(response_json).__name__}"
    try:
        top_keys = sorted(list(response_json.keys()))[:20]
        candidates = response_json.get("candidates") or []
        candidate_count = len(candidates) if isinstance(candidates, list) else 0

        finish_reasons: list[str] = []
        part_kinds: list[str] = []
        if isinstance(candidates, list):
            for cand in candidates[:3]:
                if not isinstance(cand, dict):
                    continue
                finish = cand.get("finishReason") or cand.get("finish_reason")
                if isinstance(finish, str):
                    finish_reasons.append(finish)
                content = cand.get("content") if isinstance(cand.get("content"), dict) else None
                parts = content.get("parts") if isinstance(content, dict) else None
                if isinstance(parts, list):
                    for part in parts[:6]:
                        if not isinstance(part, dict):
                            continue
                        if "inlineData" in part or "inline_data" in part:
                            part_kinds.append("inlineData")
                        elif "text" in part:
                            part_kinds.append("text")
                        else:
                            part_kinds.append(",".join(sorted(part.keys()))[:60])

        prompt_feedback = response_json.get("promptFeedback") or response_json.get("prompt_feedback")
        block_reason = None
        if isinstance(prompt_feedback, dict):
            block_reason = prompt_feedback.get("blockReason") or prompt_feedback.get("block_reason")

        bits = [
            f"topKeys={top_keys}",
            f"candidateCount={candidate_count}",
            f"finishReasons={finish_reasons[:3]}",
            f"partKinds={part_kinds[:12]}",
        ]
        if isinstance(block_reason, str) and block_reason.strip():
            bits.append(f"blockReason={block_reason.strip()}")
        return " ".join(bits)
    except Exception as exc:  # noqa: BLE001
        return f"failed_to_summarize_response error={type(exc).__name__}"


def _gemini_image_references_enabled() -> bool:
    raw = os.getenv("GEMINI_IMAGE_REFERENCES_ENABLED", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_DEFAULT_FUNNEL_IMAGE_MODEL = "gemini-3-pro-image-preview"


def _resolve_funnel_image_model() -> str:
    model = os.getenv("FUNNEL_IMAGE_MODEL") or os.getenv("NANO_BANANA_MODEL") or _DEFAULT_FUNNEL_IMAGE_MODEL
    cleaned = str(model).strip()
    if not cleaned:
        raise RuntimeError(
            "Funnel image model is not configured. Set FUNNEL_IMAGE_MODEL or NANO_BANANA_MODEL."
        )
    return cleaned


def generate_gemini_image_bytes(
    *,
    prompt: str,
    aspect_ratio: Optional[str] = None,
    reference_image_bytes: Optional[bytes] = None,
    reference_image_mime_type: Optional[str] = None,
) -> tuple[bytes, str, str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    model = _resolve_funnel_image_model()

    parts: list[dict[str, Any]] = []
    if reference_image_bytes is not None:
        if not reference_image_bytes:
            raise RuntimeError("Reference image data is empty.")
        if not isinstance(reference_image_mime_type, str) or not reference_image_mime_type:
            raise RuntimeError("Reference image mime type is required.")
        if not _gemini_image_references_enabled():
            raise RuntimeError(
                "Reference images are not enabled. Set GEMINI_IMAGE_REFERENCES_ENABLED=true to use image references."
            )
        parts.append(
            {
                "inlineData": {
                    "mimeType": reference_image_mime_type,
                    "data": base64.b64encode(reference_image_bytes).decode("ascii"),
                }
            }
        )
    parts.append({"text": prompt})
    payload: dict[str, Any] = {"contents": [{"parts": parts}]}
    if aspect_ratio:
        payload["generationConfig"] = {"imageConfig": {"aspectRatio": aspect_ratio}}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    retries = 2
    last_summary: str | None = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 429 and attempt < retries:
                retry_after_raw = exc.response.headers.get("Retry-After") if exc.response is not None else None
                try:
                    retry_after = float(retry_after_raw) if retry_after_raw else 5.0 * (attempt + 1)
                except ValueError:
                    retry_after = 5.0 * (attempt + 1)
                time.sleep(max(retry_after, 1.0))
                continue
            body = exc.response.text if exc.response is not None else ""
            raise RuntimeError(f"Gemini image request failed (status={status}): {body}") from exc
        except Exception as exc:  # noqa: BLE001
            if attempt >= retries:
                raise RuntimeError(f"Gemini image request failed: {exc}") from exc
            time.sleep(0.6 * (attempt + 1))
            continue
        data = resp.json()
        try:
            image_bytes, mime_type = _extract_first_inline_image(data)
            return image_bytes, mime_type, model
        except Exception as exc:  # noqa: BLE001
            last_summary = _summarize_gemini_response_for_debug(data)
            if attempt >= retries:
                raise RuntimeError(
                    f"Gemini image model '{model}' response did not include inline image data "
                    f"(attempts={retries + 1}). {last_summary}"
                ) from exc
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError("Unreachable: Gemini image generation retry loop exhausted.")


def _unsplash_access_key() -> str:
    api_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not api_key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY not configured")
    return api_key


def _unsplash_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Client-ID {api_key}", "Accept-Version": "v1"}


def _unsplash_select_photo(query: str) -> dict[str, Any]:
    api_key = _unsplash_access_key()
    resp = httpx.get(
        "https://api.unsplash.com/search/photos",
        headers=_unsplash_headers(api_key),
        params={"query": query, "per_page": 1, "content_filter": "high"},
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        raise RuntimeError(f"Unsplash search returned 0 results for query: {query}")
    return results[0]


def _unsplash_track_download(photo: dict[str, Any]) -> None:
    download_location = (
        photo.get("links", {}).get("download_location") if isinstance(photo.get("links"), dict) else None
    )
    if not isinstance(download_location, str) or not download_location:
        return
    api_key = _unsplash_access_key()
    httpx.get(
        download_location,
        headers=_unsplash_headers(api_key),
        params={"client_id": api_key},
        timeout=10.0,
    )


def _unsplash_download_url(photo: dict[str, Any], max_width: int | None) -> str:
    urls = photo.get("urls") if isinstance(photo.get("urls"), dict) else None
    raw_url = urls.get("raw") if isinstance(urls, dict) else None
    if not isinstance(raw_url, str) or not raw_url:
        full_url = urls.get("full") if isinstance(urls, dict) else None
        if not isinstance(full_url, str) or not full_url:
            raise RuntimeError("Unsplash image result missing download URLs.")
        raw_url = full_url
    if not max_width:
        return raw_url
    parsed = httpx.URL(raw_url)
    params = dict(parsed.params)
    params.update({"auto": "format", "fit": "max", "w": str(max_width)})
    return str(parsed.copy_with(params=params))


def _inspect_image_bytes(image_bytes: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            fmt = img.format
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Unable to read image data from Unsplash download.") from exc
    if not fmt:
        raise RuntimeError("Unable to determine image format from Unsplash download.")
    return width, height, fmt


def _resolve_image_content_type(mime_type: Optional[str], fmt: str) -> str:
    if mime_type:
        return mime_type.split(";")[0].strip()
    fmt_lower = fmt.lower()
    if fmt_lower in ("jpeg", "jpg"):
        return "image/jpeg"
    if fmt_lower == "png":
        return "image/png"
    if fmt_lower == "webp":
        return "image/webp"
    raise RuntimeError("Unable to determine image content type for Unsplash download.")


def _resolve_image_ext(mime_type: Optional[str], fmt: str) -> str:
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type.split(";")[0].strip())
        if guessed:
            return guessed.lstrip(".")
    fmt_lower = fmt.lower()
    if fmt_lower in ("jpeg", "jpg"):
        return "jpg"
    if fmt_lower == "png":
        return "png"
    if fmt_lower == "webp":
        return "webp"
    raise RuntimeError("Unable to determine file extension for Unsplash download.")


def create_funnel_unsplash_asset(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    query: str,
    usage_context: Optional[dict[str, Any]] = None,
    funnel_id: Optional[str] = None,
    product_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    max_width: int = 1600,
) -> Asset:
    if not isinstance(query, str) or not query.strip():
        raise RuntimeError("Unsplash query must be a non-empty string.")
    cleaned_query = query.strip()
    photo = _unsplash_select_photo(cleaned_query)
    _unsplash_track_download(photo)
    download_url = _unsplash_download_url(photo, max_width=max_width)
    resp = httpx.get(download_url, timeout=60.0)
    resp.raise_for_status()
    image_bytes = resp.content
    if not image_bytes:
        raise RuntimeError("Unsplash download returned empty image data.")
    width, height, fmt = _inspect_image_bytes(image_bytes)
    mime_type = _resolve_image_content_type(resp.headers.get("Content-Type"), fmt)
    ext = _resolve_image_ext(mime_type, fmt)

    sha256 = hashlib.sha256(image_bytes).hexdigest()
    storage = MediaStorage()
    key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
    if not storage.object_exists(bucket=storage.bucket, key=key):
        storage.upload_bytes(
            bucket=storage.bucket,
            key=key,
            data=image_bytes,
            content_type=mime_type,
            cache_control="public, max-age=31536000, immutable",
        )

    unsplash_user = photo.get("user") if isinstance(photo.get("user"), dict) else {}
    unsplash_links = photo.get("links") if isinstance(photo.get("links"), dict) else {}
    content = {
        "source": "unsplash",
        "query": cleaned_query,
        "unsplash": {
            "id": photo.get("id"),
            "description": photo.get("description") or photo.get("alt_description"),
            "user": {
                "name": unsplash_user.get("name"),
                "username": unsplash_user.get("username"),
                "link": unsplash_user.get("links", {}).get("html") if isinstance(unsplash_user, dict) else None,
            },
            "links": {
                "html": unsplash_links.get("html"),
                "download": unsplash_links.get("download"),
                "downloadLocation": unsplash_links.get("download_location"),
            },
        },
    }

    asset = Asset(
        org_id=org_id,
        client_id=client_id,
        source_type=AssetSourceEnum.upload,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="funnel",
        format="image",
        content=content,
        funnel_id=funnel_id,
        product_id=product_id,
        storage_key=key,
        content_type=mime_type,
        size_bytes=len(image_bytes),
        width=width,
        height=height,
        file_source="unsplash",
        file_status="ready",
        ai_metadata={
            "usageContext": usage_context or {},
            "source": "unsplash",
            "downloadedAt": datetime.now(timezone.utc).isoformat(),
        },
        tags=tags or [],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def create_funnel_image_asset(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    prompt: str,
    aspect_ratio: Optional[str] = None,
    usage_context: Optional[dict[str, Any]] = None,
    reference_image_bytes: Optional[bytes] = None,
    reference_image_mime_type: Optional[str] = None,
    reference_asset_public_id: Optional[str] = None,
    reference_asset_id: Optional[str] = None,
    funnel_id: Optional[str] = None,
    product_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Asset:
    image_bytes, mime_type, image_model = generate_gemini_image_bytes(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        reference_image_bytes=reference_image_bytes,
        reference_image_mime_type=reference_image_mime_type,
    )
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    ext = "png" if "png" in (mime_type or "").lower() else "jpg"

    storage = MediaStorage()
    key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
    if not storage.object_exists(bucket=storage.bucket, key=key):
        storage.upload_bytes(
            bucket=storage.bucket,
            key=key,
            data=image_bytes,
            content_type=mime_type,
            cache_control="public, max-age=31536000, immutable",
        )

    width: Optional[int] = None
    height: Optional[int] = None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
    except Exception:
        width = None
        height = None

    ai_metadata = {
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "usageContext": usage_context or {},
        "model": image_model,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256,
    }
    if reference_asset_public_id:
        ai_metadata["referenceAssetPublicId"] = reference_asset_public_id
    if reference_asset_id:
        ai_metadata["referenceAssetId"] = reference_asset_id
    if reference_image_mime_type:
        ai_metadata["referenceMimeType"] = reference_image_mime_type

    asset = Asset(
        org_id=org_id,
        client_id=client_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="funnel",
        format="image",
        content={},
        funnel_id=funnel_id,
        product_id=product_id,
        storage_key=key,
        content_type=mime_type,
        size_bytes=len(image_bytes),
        width=width,
        height=height,
        file_source="ai",
        file_status="ready",
        ai_metadata=ai_metadata,
        tags=tags or [],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def create_funnel_upload_asset(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    content_bytes: bytes,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    alt: Optional[str] = None,
    usage_context: Optional[dict[str, Any]] = None,
    funnel_id: Optional[str] = None,
    product_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Asset:
    sha256 = hashlib.sha256(content_bytes).hexdigest()
    ext = None
    if content_type:
        ext = mimetypes.guess_extension(content_type) or None
    if not ext and filename:
        ext = os.path.splitext(filename)[1] or None
    ext = (ext or ".bin").lstrip(".")

    storage = MediaStorage()
    key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
    if not storage.object_exists(bucket=storage.bucket, key=key):
        storage.upload_bytes(
            bucket=storage.bucket,
            key=key,
            data=content_bytes,
            content_type=content_type,
            cache_control="public, max-age=31536000, immutable",
        )

    width: Optional[int] = None
    height: Optional[int] = None
    try:
        with Image.open(io.BytesIO(content_bytes)) as img:
            width, height = img.size
    except Exception:
        width = None
        height = None

    asset = Asset(
        org_id=org_id,
        client_id=client_id,
        source_type=AssetSourceEnum.upload,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="funnel",
        format="image",
        content={},
        funnel_id=funnel_id,
        product_id=product_id,
        storage_key=key,
        content_type=content_type,
        size_bytes=len(content_bytes),
        width=width,
        height=height,
        alt=alt,
        file_source="upload",
        file_status="ready",
        ai_metadata=usage_context or {},
        tags=tags or [],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset
