import re
from typing import cast

from llm import Llm
from loop.analyzer_prompt import (
    ANALYZER_SYSTEM_INSTRUCTION,
    OUTLINE_ANALYZER_SYSTEM_INSTRUCTION,
    build_outline_analyzer_prompt,
    build_analyzer_prompt,
)
from loop.contracts import (
    BlueprintOutlineSpec,
    BlueprintOutlineEntry,
    BlueprintWrapperOutline,
    BlueprintValidationReport,
    LiveReferenceDomEvidenceItem,
    ReferenceBundle,
    RequirementsSpec,
    ValidationReport,
)
from loop.gemini import (
    GeminiPart,
    data_url_to_part,
    generate_structured_output,
    text_part,
)


class LoopAnalyzer:
    def __init__(self, gemini_api_key: str):
        self._gemini_api_key = gemini_api_key
        self._model_name = "gemini-3.1-pro-preview"

    async def analyze(
        self,
        reference_bundle: ReferenceBundle,
        current_html: str | None = None,
        prior_requirements: RequirementsSpec | None = None,
        prior_validation: ValidationReport | None = None,
        prior_blueprint_validation: BlueprintValidationReport | None = None,
    ) -> RequirementsSpec:
        outline = await self._analyze_outline(
            reference_bundle=reference_bundle,
            prior_blueprint_validation=prior_blueprint_validation,
        )
        parts = self._build_media_parts(
            reference_bundle,
            include_live_renders=False,
        )
        parts.insert(
            0,
            text_part(
                build_analyzer_prompt(
                    reference_bundle,
                    current_html,
                    prior_requirements,
                    prior_validation,
                    prior_blueprint_validation,
                    approved_outline=outline,
                )
            ),
        )
        return await generate_structured_output(
            api_key=self._gemini_api_key,
            model_name=self._model_name,
            thinking_level="high",
            system_instruction=ANALYZER_SYSTEM_INSTRUCTION,
            parts=parts,
            response_schema=RequirementsSpec,
        )

    async def _analyze_outline(
        self,
        *,
        reference_bundle: ReferenceBundle,
        prior_blueprint_validation: BlueprintValidationReport | None,
    ) -> BlueprintOutlineSpec:
        seed_outline = _seed_outline_from_reference_bundle(reference_bundle)
        parts = self._build_media_parts(
            reference_bundle,
            include_live_renders=False,
        )
        parts.insert(
            0,
            text_part(
                build_outline_analyzer_prompt(
                    reference_bundle=reference_bundle,
                    prior_outline=seed_outline,
                    prior_blueprint_validation=prior_blueprint_validation,
                )
            ),
        )
        outline = await generate_structured_output(
            api_key=self._gemini_api_key,
            model_name=self._model_name,
            thinking_level="high",
            system_instruction=OUTLINE_ANALYZER_SYSTEM_INSTRUCTION,
            parts=parts,
            response_schema=BlueprintOutlineSpec,
        )
        return _merge_outline_with_seed(outline, seed_outline)

    def _build_media_parts(
        self,
        reference_bundle: ReferenceBundle,
        *,
        include_live_renders: bool = True,
    ) -> list[GeminiPart]:
        parts: list[GeminiPart] = []

        for index, image in enumerate(reference_bundle.images, start=1):
            parts.append(text_part(f"Reference image {index}:"))
            parts.append(data_url_to_part(image))

        if reference_bundle.live_reference is not None and include_live_renders:
            renders = reference_bundle.live_reference.renders
            for index, render in enumerate(renders, start=1):
                parts.append(
                    text_part(
                        f"Live browser render {index} ({render.label}) from {reference_bundle.live_reference.url}:"
                    )
                )
                parts.append(data_url_to_part(render.data_url))

        for index, video in enumerate(reference_bundle.videos, start=1):
            parts.append(text_part(f"Reference video {index}:"))
            parts.append(data_url_to_part(video))

        if (
            reference_bundle.input_mode == "text"
            and not reference_bundle.images
            and not reference_bundle.videos
            and (
                reference_bundle.live_reference is None
                or not reference_bundle.live_reference.renders
            )
        ):
            parts.append(text_part("There is no reference media for this request."))

        return parts

    @property
    def model(self) -> Llm:
        return Llm.GEMINI_3_1_PRO_PREVIEW_HIGH


def _seed_outline_from_reference_bundle(
    reference_bundle: ReferenceBundle,
) -> BlueprintOutlineSpec | None:
    live_reference = reference_bundle.live_reference
    if live_reference is None:
        return None

    dom_evidence = live_reference.design_system.dom_evidence

    page_outline: list[BlueprintOutlineEntry] = []
    page_outline.extend(
        _outline_entries_from_items(
            dom_evidence.chrome_candidates,
            allowed_kinds={"chrome"},
        )
    )
    page_outline.extend(
        _outline_entries_from_items(
            dom_evidence.section_candidates,
            allowed_kinds={"section"},
        )
    )
    page_outline.extend(
        _outline_entries_from_items(
            dom_evidence.footer_bands,
            allowed_kinds={"footer_band"},
        )
    )
    page_outline.extend(
        _outline_entries_from_items(
            dom_evidence.state_variants,
            allowed_kinds={"state_variant"},
        )
    )

    deduped_outline: list[BlueprintOutlineEntry] = []
    seen_section_ids: set[str] = set()
    for entry in sorted(
        page_outline,
        key=lambda item: (
            _outline_top_offset(reference_bundle, item.source_evidence_ids),
            item.section_id,
        ),
    ):
        if entry.section_id in seen_section_ids:
            continue
        seen_section_ids.add(entry.section_id)
        deduped_outline.append(entry)

    wrapper_outline = _wrapper_outline_from_reference(reference_bundle, deduped_outline)
    parent_wrapper_by_section: dict[str, str] = {}
    for wrapper in wrapper_outline:
        if len(wrapper.participant_section_ids) < 2:
            continue
        for section_id in wrapper.participant_section_ids:
            parent_wrapper_by_section.setdefault(section_id, wrapper.wrapper_id)
    for entry in deduped_outline:
        if not entry.parent_wrapper_id and entry.section_id in parent_wrapper_by_section:
            entry.parent_wrapper_id = parent_wrapper_by_section[entry.section_id]

    closing_sections = [entry.name for entry in deduped_outline[-5:]]
    footer_entries = [
        entry for entry in deduped_outline if "footer" in entry.section_id or "community" in entry.section_id
    ]

    return BlueprintOutlineSpec(
        page_outline=deduped_outline,
        closing_sections=closing_sections,
        footer_present=bool(footer_entries),
        footer_description=", ".join(entry.name for entry in footer_entries[:3]),
        coverage_notes=[
            "Seed outline derived from structured DOM evidence before model planning."
        ],
        wrapper_outline=wrapper_outline,
        state_notes=[
            entry.name
            for entry in deduped_outline
            if entry.kind in {"modal", "state_variant"}
        ],
    )


def _outline_entries_from_items(
    items: list[LiveReferenceDomEvidenceItem],
    *,
    allowed_kinds: set[str],
) -> list[BlueprintOutlineEntry]:
    grouped: dict[str, LiveReferenceDomEvidenceItem] = {}
    for item in items:
        if item.kind not in allowed_kinds:
            continue
        if _should_ignore_evidence_item(item):
            continue
        if not _should_include_outline_item(item):
            continue
        label = _canonical_outline_name(item)
        if not label:
            continue
        key = _normalize_outline_key(label)
        current = grouped.get(key)
        if current is None or _prefer_outline_item(item, current):
            grouped[key] = item

    entries: list[BlueprintOutlineEntry] = []
    for item in grouped.values():
        label = _canonical_outline_name(item)
        section_kind = cast(
            str,
            "modal"
            if item.kind == "state_variant" and _looks_like_modal(item)
            else item.kind,
        )
        notes = list(item.notes[:3])
        if item.html_excerpt:
            notes.append(f"excerpt: {item.html_excerpt[:220]}")
        entries.append(
            BlueprintOutlineEntry(
                name=label,
                kind=cast(
                    str,
                    "chrome" if item.kind == "chrome" else section_kind,
                ),
                source_evidence_ids=[item.evidence_id] if item.evidence_id else [],
                notes=notes[:4],
            )
        )
    return entries


def _wrapper_outline_from_reference(
    reference_bundle: ReferenceBundle,
    outline: list[BlueprintOutlineEntry],
) -> list[BlueprintWrapperOutline]:
    live_reference = reference_bundle.live_reference
    if live_reference is None:
        return []

    section_by_evidence_id = {
        evidence_id: entry.section_id
        for entry in outline
        for evidence_id in entry.source_evidence_ids
    }
    wrapper_groups: dict[str, BlueprintWrapperOutline] = {}
    for relationship in live_reference.design_system.dom_evidence.wrapper_relationships:
        child_id = section_by_evidence_id.get(relationship.child_evidence_id)
        parent_id = _normalize_outline_key(relationship.parent_evidence_id or relationship.parent_selector)
        if not child_id or not parent_id:
            continue
        if _is_root_wrapper(parent_id):
            continue
        wrapper = wrapper_groups.get(parent_id)
        if wrapper is None:
            wrapper = BlueprintWrapperOutline(
                name=relationship.parent_selector or relationship.parent_evidence_id or "Shared Wrapper",
                wrapper_id=parent_id,
                participant_section_ids=[],
                source_relationships=[],
                notes=[],
            )
            wrapper_groups[parent_id] = wrapper
        if child_id not in wrapper.participant_section_ids:
            wrapper.participant_section_ids.append(child_id)
        if relationship.relationship and relationship.relationship not in wrapper.source_relationships:
            wrapper.source_relationships.append(relationship.relationship)
        for note in relationship.notes[:3]:
            if note not in wrapper.notes:
                wrapper.notes.append(note)

    footer_participants = [
        entry.section_id
        for entry in outline
        if any(
            keyword in entry.section_id
            for keyword in ("community", "newsletter", "footer", "legal")
        )
    ]
    if len(footer_participants) >= 2:
        footer_wrapper = BlueprintWrapperOutline(
            name="Footer Closing Shell",
            wrapper_id="footer-closing-shell",
            kind="shared_shell",
            participant_section_ids=footer_participants,
            source_relationships=["seeded-footer-group"],
            notes=[
                "Keep the closing newsletter/community and footer/legal regions inside one shared footer shell when the DOM evidence exposes both layers."
            ],
        )
        wrapper_groups[footer_wrapper.wrapper_id] = footer_wrapper

    wrappers = [
        wrapper
        for wrapper in wrapper_groups.values()
        if len(wrapper.participant_section_ids) >= 2
    ]
    return wrappers[:12]


def _normalize_outline_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _outline_label(item: LiveReferenceDomEvidenceItem) -> str:
    for candidate in (item.heading_text, item.label, item.text_sample):
        cleaned = " ".join(candidate.split()).strip()
        if cleaned:
            if len(cleaned) > 80:
                cleaned = cleaned[:77].rstrip() + "..."
            return cleaned
    return ""


def _canonical_outline_name(item: LiveReferenceDomEvidenceItem) -> str:
    haystack = _evidence_haystack(item)
    footer_like = item.kind == "footer_band" or "footer" in haystack

    if footer_like:
        if any(keyword in haystack for keyword in ("newsletter", "join the community", "subscribe")):
            return "Community Signup"
        if any(
            keyword in haystack
            for keyword in ("content-bottom", "all rights reserved", "terms", "privacy", "refunds", "food and drug administration")
        ):
            return "Footer Legal"
        return "Site Footer"

    if item.kind == "state_variant":
        if _looks_like_modal(item):
            return "Modal State"
        if any(keyword in haystack for keyword in ("sticky", "scrolled", "drawer")):
            return "Sticky State"

    if any(
        keyword in haystack
        for keyword in ("redesign_hero", "section-redesign-hero", "creatine forbody", "creatine for body")
    ):
        return "Hero"
    if any(keyword in haystack for keyword in ("section-header", "header-wrapper", "log in cart")):
        return "Site Header"
    if any(keyword in haystack for keyword in ("marquee", "bioavailable formula", "fresh light taste")):
        return "Marquee"
    if any(
        keyword in haystack
        for keyword in ("image_with_text_v1", "section-benefits", "optimize your routine")
    ):
        return "Benefits"
    if any(
        keyword in haystack
        for keyword in ("image_with_text_v2", "section-science", "results start with evidence")
    ):
        return "Science"
    if any(
        keyword in haystack
        for keyword in ("redesign_counter", "section-counter", "snackable", "backed by studies")
    ):
        return "Stats Grid"
    if any(keyword in haystack for keyword in ("redesign_trust", "section-trust", "quality you can trust")):
        return "Trust"
    if any(
        keyword in haystack
        for keyword in ("featured_product", "section-featured-product", "product__info", "omni creatine gummy")
    ):
        return "Product Showcase"
    if any(keyword in haystack for keyword in ("icon_and_text", "gmo free", "3rd party tested")):
        return "Badges Strip"
    if any(keyword in haystack for keyword in ("video_review", "real people, real results")):
        return "Testimonials"
    if any(keyword in haystack for keyword in ("compare_table", "us vs. them")):
        return "Comparison"
    if any(keyword in haystack for keyword in ("section_text", "be creatine-powered")):
        return "CTA Banner"
    if any(keyword in haystack for keyword in ("doctor_review", "expert designed gummies")):
        return "Expert Review"
    if any(keyword in haystack for keyword in ("redesign_faq", "any last questions")):
        return "FAQ"
    return _outline_label(item)


def _selector_depth(selector: str) -> int:
    return selector.count(">")


def _prefer_outline_item(
    candidate: LiveReferenceDomEvidenceItem,
    current: LiveReferenceDomEvidenceItem,
) -> bool:
    candidate_score = (
        1 if _looks_like_top_level_section(candidate) else 0,
        -_selector_depth(candidate.selector),
        -(candidate.top_offset_px or 0),
        -len(candidate.selector),
    )
    current_score = (
        1 if _looks_like_top_level_section(current) else 0,
        -_selector_depth(current.selector),
        -(current.top_offset_px or 0),
        -len(current.selector),
    )
    return candidate_score > current_score


def _looks_like_top_level_section(item: LiveReferenceDomEvidenceItem) -> bool:
    selector = item.selector.lower()
    evidence_id = item.evidence_id.lower()
    return (
        selector.startswith("#shopify-section")
        or "> section.shopify-section" in selector
        or evidence_id.startswith("section-main-child-section")
        or evidence_id.startswith("section-body-child")
        or item.kind in {"footer_band", "chrome"}
    )


def _should_ignore_evidence_item(item: LiveReferenceDomEvidenceItem) -> bool:
    haystack = " ".join(
        part.lower()
        for part in (
            item.evidence_id,
            item.label,
            item.selector,
            item.text_sample,
            item.heading_text,
        )
        if part
    )
    ignored_keywords = (
        "chat",
        "cookie",
        "accessibility",
        "support widget",
        "support launcher",
        "support-button",
        "launcher",
        "modal-opener",
        "open media",
        "lightbox",
        "quick-add",
    )
    if any(keyword in haystack for keyword in ignored_keywords):
        return True

    if item.kind == "chrome" and (item.top_offset_px or 0) > 2000:
        if not any(keyword in haystack for keyword in ("footer", "community", "newsletter")):
            return True
    return False


def _should_include_outline_item(item: LiveReferenceDomEvidenceItem) -> bool:
    haystack = _evidence_haystack(item)
    selector = item.selector.lower()
    evidence_id = item.evidence_id.lower()

    if item.kind == "section":
        if "nested" in evidence_id and not selector.startswith("#shopify-section"):
            return False
        if "overlay" in evidence_id:
            return False
        if not _looks_like_top_level_section(item) and not any(
            keyword in haystack
            for keyword in (
                "hero",
                "faq",
                "accordion",
                "comparison",
                "compare",
                "review",
                "testimonial",
                "community",
                "newsletter",
                "signup",
                "cta",
                "banner",
                "product",
                "benefit",
                "science",
                "stats",
                "trust",
                "article",
                "blog",
                "footer",
            )
        ):
            return False
        return True

    if item.kind == "chrome":
        return (
            (item.top_offset_px or 0) < 250
            and any(keyword in haystack for keyword in ("header", "shop now", "log in", "cart"))
            and "footer" not in haystack
            and "newsletter" not in haystack
        )

    if item.kind == "footer_band":
        if any(
            keyword in haystack
            for keyword in (
                "newsletterform",
                "newsletter__input",
                "footer-block__details-content",
                "footer-block.grid__item",
                "footer__blocks-wrapper",
            )
        ):
            return False
        return any(
            keyword in haystack
            for keyword in (
                "footer-block--newsletter-custom",
                "join the community",
                "footer__content-top",
                "footer__content-bottom",
                "footer color-scheme",
                "all rights reserved",
            )
        )

    if item.kind == "state_variant":
        return _looks_like_modal(item) or any(
            keyword in haystack for keyword in ("sticky", "drawer", "scrolled")
        )

    return False


def _evidence_haystack(item: LiveReferenceDomEvidenceItem) -> str:
    return " ".join(
        part.lower()
        for part in (
            item.evidence_id,
            item.label,
            item.selector,
            item.text_sample,
            item.heading_text,
        )
        if part
    )


def _is_root_wrapper(wrapper_id: str) -> bool:
    return wrapper_id in {
        "maincontent",
        "body-gradient",
        "body",
        "main",
    }


def _looks_like_modal(item: LiveReferenceDomEvidenceItem) -> bool:
    haystack = " ".join(
        part.lower() for part in (item.label, item.selector, item.text_sample) if part
    )
    return any(keyword in haystack for keyword in ("modal", "popup", "overlay"))


def _outline_top_offset(reference_bundle: ReferenceBundle, evidence_ids: list[str]) -> int:
    live_reference = reference_bundle.live_reference
    if live_reference is None or not evidence_ids:
        return 0
    by_id: dict[str, int] = {}
    for group in (
        live_reference.design_system.dom_evidence.chrome_candidates,
        live_reference.design_system.dom_evidence.section_candidates,
        live_reference.design_system.dom_evidence.footer_bands,
        live_reference.design_system.dom_evidence.state_variants,
    ):
        for item in group:
            if item.evidence_id:
                by_id[item.evidence_id] = item.top_offset_px or 0
    return min(by_id.get(evidence_id, 0) for evidence_id in evidence_ids)


def _merge_outline_with_seed(
    outline: BlueprintOutlineSpec,
    seed_outline: BlueprintOutlineSpec | None,
) -> BlueprintOutlineSpec:
    if seed_outline is None:
        return outline

    merged_entries: list[BlueprintOutlineEntry] = []
    by_section_id = {entry.section_id: entry for entry in outline.page_outline}
    seed_entries_by_id = {entry.section_id: entry for entry in seed_outline.page_outline}

    for seed_entry in seed_outline.page_outline:
        merged_entries.append(by_section_id.get(seed_entry.section_id, seed_entry))

    for entry in outline.page_outline:
        if entry.section_id not in seed_entries_by_id:
            merged_entries.append(entry)

    merged_wrappers: list[BlueprintWrapperOutline] = []
    seen_wrapper_ids: set[str] = set()
    for source in (outline.wrapper_outline, seed_outline.wrapper_outline):
        for wrapper in source:
            if wrapper.wrapper_id in seen_wrapper_ids:
                continue
            seen_wrapper_ids.add(wrapper.wrapper_id)
            merged_wrappers.append(wrapper)

    closing_sections = list(outline.closing_sections)
    for section_name in seed_outline.closing_sections:
        if section_name not in closing_sections:
            closing_sections.append(section_name)
    if len(closing_sections) > 5:
        closing_sections = closing_sections[-5:]

    coverage_notes = list(outline.coverage_notes)
    if any(
        seed_entry.section_id not in by_section_id
        for seed_entry in seed_outline.page_outline
    ):
        coverage_notes.append(
            "Merged structured DOM seed outline back into the model outline to preserve page coverage discovered by the indexed evidence catalog."
        )

    return BlueprintOutlineSpec(
        page_outline=merged_entries,
        closing_sections=closing_sections,
        footer_present=outline.footer_present
        if outline.footer_present is not None
        else seed_outline.footer_present,
        footer_description=outline.footer_description or seed_outline.footer_description,
        coverage_notes=coverage_notes,
        wrapper_outline=merged_wrappers,
        state_notes=list(dict.fromkeys(outline.state_notes + seed_outline.state_notes)),
    )
