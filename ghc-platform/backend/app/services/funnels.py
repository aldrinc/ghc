from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import hashlib
import os
import re
from typing import Any, Optional

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import (
    FunnelAssetKindEnum,
    FunnelAssetSourceEnum,
    FunnelAssetStatusEnum,
    FunnelPageVersionSourceEnum,
    FunnelPageVersionStatusEnum,
    FunnelPublicationLinkKindEnum,
    FunnelStatusEnum,
)
from app.db.models import (
    Campaign,
    Funnel,
    FunnelAsset,
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

    approved_by_page: dict[str, FunnelPageVersion] = {}
    for page in pages:
        version = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page.id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.approved,
            )
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        ).first()
        if not version:
            raise ValueError(f"Page '{page.name}' is not approved")
        approved_by_page[str(page.id)] = version

    publication = FunnelPublication(
        funnel_id=funnel.id,
        entry_page_id=funnel.entry_page_id,
        created_by=user_id,
    )
    session.add(publication)
    session.flush()

    extracted_links: list[tuple[str, InternalLink]] = []
    for page in pages:
        version = approved_by_page[str(page.id)]
        for link in extract_internal_links(version.puck_data):
            if link.to_page_id not in page_id_set:
                raise ValueError(f"Invalid internal link target: {link.to_page_id}")
            extracted_links.append((str(page.id), link))

    for page in pages:
        session.add(
            FunnelPublicationPage(
                publication_id=publication.id,
                page_id=page.id,
                page_version_id=approved_by_page[str(page.id)].id,
                slug_at_publish=page.slug,
            )
        )

    for from_page_id, link in extracted_links:
        session.add(
            FunnelPublicationLink(
                publication_id=publication.id,
                from_page_id=from_page_id,
                to_page_id=link.to_page_id,
                kind=FunnelPublicationLinkKindEnum.cta,
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
        name=name or f"{source.name} (Copy)",
        description=source.description,
        status=FunnelStatusEnum.draft,
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
    for page in source_pages:
        new_page = FunnelPage(
            funnel_id=new_funnel.id,
            name=page.name,
            slug=page.slug,
            ordering=page.ordering,
        )
        session.add(new_page)
        session.flush()
        id_map[str(page.id)] = str(new_page.id)

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


def generate_gemini_image_bytes(*, prompt: str, aspect_ratio: Optional[str] = None) -> tuple[bytes, str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    payload: dict[str, Any] = {"contents": [{"parts": [{"text": prompt}]}]}
    if aspect_ratio:
        payload["generationConfig"] = {"aspectRatio": aspect_ratio}

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
    resp = httpx.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    image_bytes, mime_type = _extract_first_inline_image(data)
    return image_bytes, mime_type


def create_funnel_image_asset(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    prompt: str,
    aspect_ratio: Optional[str] = None,
    usage_context: Optional[dict[str, Any]] = None,
) -> FunnelAsset:
    image_bytes, mime_type = generate_gemini_image_bytes(prompt=prompt, aspect_ratio=aspect_ratio)
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

    asset = FunnelAsset(
        org_id=org_id,
        client_id=client_id,
        kind=FunnelAssetKindEnum.image,
        storage_key=key,
        content_type=mime_type,
        bytes=len(image_bytes),
        width=width,
        height=height,
        source=FunnelAssetSourceEnum.ai,
        ai_metadata={
            "prompt": prompt,
            "aspectRatio": aspect_ratio,
            "usageContext": usage_context or {},
            "model": "gemini-2.5-flash-image",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "sha256": sha256,
        },
        status=FunnelAssetStatusEnum.ready,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset
