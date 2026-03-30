from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.db.models import Site, SitePage, SitePageVersion
from app.llm.client import LLMClient, LLMGenerationParams
from app.services import funnel_ai


_IMPORTED_TEMPLATE_ALLOWED_TYPES = {
    "ImportedPage",
    "ImportedSection",
    "ImportedRuntimeSection",
    "ImportedNarrativeBlock",
    "ImportedItemGrid",
    "ImportedBadgeStrip",
    "ImportedOfferSelector",
    "ImportedTestimonialsGrid",
    "ImportedComparisonTable",
    "ImportedAccordion",
    "ImportedFooterLinks",
}


class SitePageAiError(ValueError):
    """Raised when site-page AI generation cannot be completed."""


def _sanitize_imported_component_tree(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        block_type = raw.get("type")
        props = raw.get("props")
        if (
            not isinstance(block_type, str)
            or block_type not in _IMPORTED_TEMPLATE_ALLOWED_TYPES
            or not isinstance(props, dict)
        ):
            continue

        if block_type in {"ImportedPage", "ImportedSection"}:
            props["content"] = _sanitize_imported_component_tree(props.get("content"))
        elif block_type == "ImportedRuntimeSection":
            if not isinstance(props.get("textOverrides"), list):
                props["textOverrides"] = []
            if not isinstance(props.get("buttonOverrides"), list):
                props["buttonOverrides"] = []
            if not isinstance(props.get("imageOverrides"), list):
                props["imageOverrides"] = []
        elif block_type == "ImportedNarrativeBlock":
            if not isinstance(props.get("badges"), list):
                props["badges"] = []
            if not isinstance(props.get("buttons"), list):
                props["buttons"] = []
        elif block_type == "ImportedItemGrid":
            if not isinstance(props.get("items"), list):
                props["items"] = []
        elif block_type == "ImportedBadgeStrip":
            if not isinstance(props.get("items"), list):
                props["items"] = []
        elif block_type == "ImportedOfferSelector":
            if not isinstance(props.get("galleryImages"), list):
                props["galleryImages"] = []
            if not isinstance(props.get("benefits"), list):
                props["benefits"] = []
            if not isinstance(props.get("offers"), list):
                props["offers"] = []
        elif block_type == "ImportedTestimonialsGrid":
            if not isinstance(props.get("items"), list):
                props["items"] = []
        elif block_type == "ImportedComparisonTable":
            if not isinstance(props.get("rows"), list):
                props["rows"] = []
        elif block_type == "ImportedAccordion":
            if not isinstance(props.get("items"), list):
                props["items"] = []
        elif block_type == "ImportedFooterLinks":
            if not isinstance(props.get("links"), list):
                props["links"] = []

        cleaned.append(raw)

    return cleaned


def _is_imported_template_page_data(puck_data: dict[str, Any] | None) -> bool:
    if not isinstance(puck_data, dict):
        return False
    content = puck_data.get("content")
    if not isinstance(content, list) or not content:
        return False
    first = content[0]
    return isinstance(first, dict) and first.get("type") == "ImportedPage"


def _build_site_page_context(session: Session, *, site_id: str) -> list[dict[str, str]]:
    pages = list(
        session.scalars(
            select(SitePage)
            .where(SitePage.site_id == site_id)
            .order_by(SitePage.ordering.asc(), SitePage.created_at.asc())
        ).all()
    )
    return [{"id": str(page.id), "name": page.name, "slug": page.slug} for page in pages]


def _imported_template_component_docs() -> str:
    return (
        "Available imported-template components (component types) and their props:\n"
        "1) ImportedPage: props { id, pageName, pageType?, theme?, themeJson?, renderMode?, sharedRuntimeSource?, sharedHeadAssets?, content? }\n"
        "   - Use ImportedPage as the ONLY top-level block in puckData.content.\n"
        "   - Preserve renderMode, sharedRuntimeSource, and sharedHeadAssets for runtime-backed imported pages.\n"
        "   - ImportedPage.props.content is a slot: ComponentData[] of ImportedSection blocks.\n"
        "2) ImportedSection: props { id, displayName, sourceSectionId, sectionKey, sectionType?, semanticTagsText?, surface?, renderMode?, content? }\n"
        "   - Keep ImportedSection order stable unless the user explicitly requests a structural reorder.\n"
        "   - Preserve sourceSectionId and sectionKey for existing sections.\n"
        "   - ImportedSection.props.content is a slot: ComponentData[] of imported content blocks.\n"
        "3) ImportedRuntimeSection: props { id, sectionLabel?, componentName?, sectionTargetId?, textOverrides?, buttonOverrides?, imageOverrides? }\n"
        "   - Preserve runtimeSource, headAssets, componentName, and sectionTargetId for existing runtime-backed sections.\n"
        "   - textOverrides: [{ label?, originalText, text }]\n"
        "   - buttonOverrides: [{ label?, originalText, text, href }]\n"
        "   - imageOverrides: [{ label?, originalSrc, src, alt }]\n"
        "   - Prefer editing override arrays instead of replacing a runtime-backed section with generic content blocks.\n"
        "4) ImportedNarrativeBlock: props { id, eyebrow?, title?, body?, quote?, imageSrc?, imageAlt?, mediaPosition?, align?, badges?, buttons? }\n"
        "   - buttons: [{ label, href }]\n"
        "   - badges: [{ label }]\n"
        "5) ImportedItemGrid: props { id, title?, body?, columns?, items? }\n"
        "   - items: [{ label?, title?, text?, value? }]\n"
        "6) ImportedBadgeStrip: props { id, title?, items? }\n"
        "   - items: [{ label }]\n"
        "7) ImportedOfferSelector: props { id, eyebrow?, title?, body?, reviewText?, ctaLabel?, galleryImages?, benefits?, offers? }\n"
        "   - galleryImages: [{ src, alt }]\n"
        "   - benefits: [{ text }]\n"
        "   - offers: [{ title?, subtitle?, price?, total?, regularPrice?, savings?, badge? }]\n"
        "8) ImportedTestimonialsGrid: props { id, title?, body?, items? }\n"
        "   - items: [{ name?, quote?, role?, imageSrc? }]\n"
        "9) ImportedComparisonTable: props { id, title?, body?, primaryLabel?, secondaryLabel?, tertiaryLabel?, rows? }\n"
        "   - rows: [{ feature?, primaryValue?, secondaryValue?, tertiaryValue? }]\n"
        "10) ImportedAccordion: props { id, title?, body?, items? }\n"
        "   - items: [{ question?, answer? }]\n"
        "11) ImportedFooterLinks: props { id, brandName?, body?, legalText?, links? }\n"
        "   - links: [{ label?, href? }]\n"
    )


def _build_site_ai_prompt(
    *,
    site: Site,
    page: SitePage,
    base_puck: dict[str, Any],
    page_context: list[dict[str, str]],
    prompt: str,
    messages: list[dict[str, str]] | None,
) -> str:
    system_content = (
        "You are editing a first-party imported template page in a Puck editor.\n\n"
        "You MUST output valid JSON only (no markdown, no code fences, no commentary).\n"
        "Return exactly ONE JSON object with this shape:\n"
        '{ "assistantMessage": string, "puckData": string }\n'
        "puckData must be a JSON-encoded string for this object shape:\n"
        '{ "root": { "props": object }, "content": ComponentData[], "zones": object }\n\n'
        "Editing rules:\n"
        "- Keep ImportedPage as the only top-level block in puckData.content.\n"
        "- Keep ImportedSection blocks as the section model for the page.\n"
        "- Preserve existing ImportedSection.sourceSectionId and sectionKey values.\n"
        "- Keep the current section order unless the user explicitly asks to reorder sections.\n"
        "- Do not switch this page into SalesPdp, PreSales, or generic Section/Heading/Text primitives.\n"
        "- When a section already uses ImportedRuntimeSection, preserve the runtime-backed structure and edit override arrays first.\n"
        "- Do not invent product, pricing, testimonial, or compliance facts.\n"
        "- Use concise, editable copy and keep CTAs specific.\n"
        "- Prefer changing textOverrides, buttonOverrides, and imageOverrides over replacing a source-faithful section.\n\n"
        "Structure guidance:\n"
        "- ImportedPage.props.content should contain ImportedSection blocks.\n"
        "- ImportedSection.props.content should contain imported content blocks only.\n"
        "- Prefer editing existing section blocks over deleting and recreating the whole page.\n\n"
        "ComponentData shape:\n"
        "- Every component must be an object with keys: type, props.\n"
        "- props should include a string id unique per component.\n"
        "- Do NOT double-encode JSON anywhere except the outer puckData string.\n\n"
        f"{_imported_template_component_docs()}\n"
        "Root props (optional):\n"
        "- root.props.title\n"
        "- root.props.description\n\n"
        "Site page context:\n"
        f"- Site name: {site.name}\n"
        f"- Current page: {page.name} ({page.slug})\n"
        f"- Other site pages: {json.dumps(page_context, ensure_ascii=False)}\n\n"
        "Current page puckData:\n"
        f"{json.dumps(base_puck, ensure_ascii=False)}"
    )

    conversation: list[dict[str, str]] = []
    for message in messages or []:
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            conversation.append({"role": role, "content": content.strip()})
    if prompt.strip():
        conversation.append({"role": "user", "content": prompt.strip()})
    if not conversation:
        raise SitePageAiError("AI prompt is empty.")

    base_prompt_parts = [system_content] + [
        f"{message['role'].upper()}: {message['content']}" for message in conversation
    ]
    return "\n\n".join(base_prompt_parts + ["Return JSON now."])


def generate_site_page_draft(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    site_id: str,
    page_id: str,
    prompt: str,
    messages: list[dict[str, str]] | None = None,
    current_puck_data: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    attached_assets: list[dict[str, Any]] | None = None,
    generate_images: bool = False,
) -> tuple[str, SitePageVersion, dict[str, Any]]:
    if attached_assets:
        raise SitePageAiError("Image attachments are not supported for site-page AI yet.")
    if generate_images:
        raise SitePageAiError("Image generation is not supported for site-page AI yet.")

    site = session.scalars(
        select(Site).where(Site.org_id == org_id, Site.id == site_id)
    ).first()
    if not site:
        raise SitePageAiError("Site not found.")

    page = session.scalars(
        select(SitePage).where(SitePage.site_id == site_id, SitePage.id == page_id)
    ).first()
    if not page:
        raise SitePageAiError("Page not found.")

    sites_repo = SitesRuntimeRepository(session)
    latest_draft = sites_repo.latest_version_for_page(page_id=page_id, status="draft")
    base_puck = current_puck_data or (latest_draft.puck_data if latest_draft else None) or page.adapted_puck_data
    if not isinstance(base_puck, dict) or not _is_imported_template_page_data(base_puck):
        raise SitePageAiError(
            "Site-page AI currently supports imported-template pages only. Rebuild this page from the import-native flow first."
        )

    llm = LLMClient()
    model_id = model or llm.default_model
    page_context = _build_site_page_context(session, site_id=site_id)
    compiled_prompt = _build_site_ai_prompt(
        site=site,
        page=page,
        base_puck=base_puck,
        page_context=page_context,
        prompt=prompt,
        messages=messages,
    )

    params = LLMGenerationParams(
        model=model_id,
        max_tokens=funnel_ai._coerce_max_tokens(model_id, max_tokens),
        temperature=temperature,
        use_reasoning=True,
        use_web_search=False,
        response_format=funnel_ai._puck_response_format(),
    )
    raw_output = llm.generate_text(compiled_prompt, params=params)
    parsed = funnel_ai._extract_json_object(raw_output)

    assistant_message = funnel_ai._coerce_assistant_message(parsed.get("assistantMessage"))
    puck_data_raw = funnel_ai._coerce_puck_data(parsed.get("puckData"))
    puck_data = funnel_ai._sanitize_puck_data(puck_data_raw)
    puck_data["content"] = _sanitize_imported_component_tree(puck_data.get("content"))
    zones = puck_data.get("zones")
    if isinstance(zones, dict):
        for key, value in list(zones.items()):
            zones[key] = _sanitize_imported_component_tree(value)
    funnel_ai._ensure_block_ids(puck_data)

    if not _is_imported_template_page_data(puck_data):
        raise SitePageAiError(
            "AI returned an invalid imported-template page. The response must keep ImportedPage as the top-level block."
        )

    page.adapted_puck_data = puck_data
    sites_repo.update_page(page=page)
    version = sites_repo.create_page_version(
        page_id=page_id,
        puck_data=puck_data,
        provenance={
            "source": "ai",
            "site_id": site_id,
            "page_id": page_id,
            "model": model_id,
            "assistant_message": assistant_message,
        },
        status="draft",
        source_type="ai",
        source_id=user_id,
        ai_metadata={
            "scope": "site",
            "model": model_id,
            "prompt": prompt,
        },
    )
    session.commit()
    session.refresh(version)
    session.refresh(page)
    return assistant_message, version, puck_data
