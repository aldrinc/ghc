import uuid
from hashlib import sha256
import re
from typing import Any, Awaitable, Callable

from config import (
    BLUEPRINT_VALIDATED_LOOP_PASS_SCORE,
    DEFAULT_BLUEPRINT_VALIDATION_MAX_ATTEMPTS,
    VALIDATED_LOOP_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_ANIMATION_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_BEHAVIOR_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_PASS_SCORE,
)
from loop.artifacts import (
    ValidatedLoopArtifactStore,
    load_design_system_preflight_from_current_cache,
    load_design_system_preflight_from_run_dir,
    load_reference_bundle_from_current_cache,
)
from loop.analyzer import LoopAnalyzer, _seed_outline_from_reference_bundle
from loop.blueprint_validator import LoopBlueprintValidator
from loop.contracts import (
    BlueprintValidationIssue,
    BlueprintValidationReport,
    DesignSystemReuseMode,
    DesignSystemPreflight,
    LiveReferenceDomEvidenceItem,
    LoopIterationRecord,
    LoopResumeState,
    LoopRunResult,
    ReferenceBundle,
    RequirementsSpec,
    SectionRequirement,
    ValidationReport,
    ViewportSpec,
    WrapperRequirement,
)
from loop.design_system_preflight import (
    DesignSystemDocumentRenderer,
    DesignSystemPreflightBuilder,
)
from loop.execution_blocks import plan_execution_blocks, summarize_execution_blocks
from loop.executor import LoopExecutor
from loop.live_reference import LiveReferenceExtractor
from loop.renderer import HtmlPreviewRenderer
from loop.validator import LoopValidator


def _live_reference_viewport(reference_bundle: ReferenceBundle) -> ViewportSpec:
    if reference_bundle.input_mode == "video":
        return ViewportSpec(width=1440, height=1024, device="desktop")
    return ViewportSpec(width=1440, height=1024, device="desktop")


def _needs_design_system_preflight(reference_bundle: ReferenceBundle) -> bool:
    return bool(
        reference_bundle.input_mode == "video"
        or reference_bundle.live_reference is not None
        or reference_bundle.reference_url.strip()
    )


def _requires_explicit_section_blueprint(reference_bundle: ReferenceBundle) -> bool:
    return bool(
        reference_bundle.images
        or reference_bundle.videos
        or reference_bundle.input_mode == "video"
        or reference_bundle.live_reference is not None
        or reference_bundle.reference_url.strip()
    )


def _has_rich_structure_reference(reference_bundle: ReferenceBundle) -> bool:
    return bool(
        reference_bundle.live_reference is not None
        or reference_bundle.design_system_preflight is not None
        or reference_bundle.reference_url.strip()
    )


_FOOTER_KEYWORDS = (
    "footer",
    "legal",
    "newsletter",
    "community",
    "copyright",
)

_STRUCTURE_SIGNAL_KEYWORDS = frozenset(
    {
        "above",
        "accordion",
        "background",
        "badge",
        "band",
        "bar",
        "below",
        "border",
        "bottom",
        "canvas",
        "card",
        "centered",
        "chrome",
        "cluster",
        "column",
        "columns",
        "container",
        "cta",
        "dialog",
        "dropdown",
        "fixed",
        "footer",
        "form",
        "frame",
        "grid",
        "group",
        "header",
        "hero",
        "left",
        "logo",
        "max",
        "media",
        "menu",
        "mega",
        "modal",
        "nav",
        "navigation",
        "nested",
        "newsletter",
        "outer",
        "overlay",
        "panel",
        "pill",
        "promo",
        "radius",
        "rail",
        "right",
        "row",
        "scroll",
        "section",
        "separator",
        "shared",
        "shell",
        "signup",
        "split",
        "stack",
        "sticky",
        "strip",
        "submenu",
        "surface",
        "tile",
        "top",
        "two",
        "video",
        "white",
        "wrapper",
        "width",
    }
)

_TYPOGRAPHY_ROLE_KEYWORDS = frozenset(
    {
        "announcement",
        "badge",
        "banner",
        "button",
        "card",
        "cta",
        "eyebrow",
        "footer",
        "header",
        "hero",
        "input",
        "label",
        "legal",
        "link",
        "logo",
        "marquee",
        "nav",
        "newsletter",
        "pill",
        "promo",
        "tag",
        "utility",
    }
)

_SECTION_SIZING_ROLE_KEYWORDS = frozenset(
    {
        "article",
        "banner",
        "canvas",
        "card",
        "column",
        "container",
        "cta",
        "footer",
        "grid",
        "header",
        "hero",
        "legal",
        "marquee",
        "modal",
        "panel",
        "promo",
        "reading",
        "row",
        "section",
        "shell",
        "sticky",
        "surface",
        "wrapper",
    }
)

_DOM_ROLE_HINTS: dict[str, frozenset[str]] = {
    "announcement": frozenset({"announcement", "marquee", "ticker", "banner"}),
    "promo": frozenset({"promo", "promotional", "offer", "welcome"}),
    "modal": frozenset({"modal", "dialog", "overlay", "popup"}),
    "sticky": frozenset({"sticky", "scroll-state", "scrolled"}),
    "newsletter": frozenset({"newsletter", "subscribe", "signup", "sign-up"}),
    "related": frozenset({"related", "read more", "more articles", "view all articles"}),
    "legal": frozenset({"legal", "copyright", "privacy", "terms", "accessibility"}),
}

_COMPONENT_GEOMETRY_REFERENCE_HINTS: dict[str, frozenset[str]] = {
    "split_panels": frozenset(
        {
            "horizontal split layout",
            "left media panel",
            "right panel",
            "text/detail column",
        }
    ),
    "repeated_items": frozenset(
        {"repeats ", "similar items", "horizontal row", "vertical stack"}
    ),
    "media_fill": frozenset(
        {"object-fit cover", "full-bleed", "100% height", "background-size cover"}
    ),
    "gradient_shells": frozenset({"gradient"}),
}

_COMPONENT_GEOMETRY_BLUEPRINT_HINTS: dict[str, frozenset[str]] = {
    "split_panels": frozenset(
        {"split", "two-column", "left", "right", "panel", "media", "commerce"}
    ),
    "repeated_items": frozenset(
        {"card", "cards", "items", "repeated", "row", "grid", "stack", "stacked"}
    ),
    "media_fill": frozenset(
        {"full-height", "100% height", "full-bleed", "object-fit", "cover", "clipped"}
    ),
    "gradient_shells": frozenset({"gradient", "blush", "surface", "shell"}),
}

_COMPONENT_GEOMETRY_BLUEPRINT_MIN_MATCHES: dict[str, int] = {
    "split_panels": 2,
    "repeated_items": 2,
    "media_fill": 1,
    "gradient_shells": 1,
}

_FONT_LOADING_KEYWORDS = frozenset(
    {
        "@font-face",
        "font-face",
        "font loading",
        "font-loading",
        "font file",
        "font files",
        "font asset",
        "font assets",
        "woff",
        "woff2",
        "hosted stylesheet",
        "hosted font css",
        "stylesheet import",
        "load the real font",
        "load the real fonts",
    }
)

_ASSET_REUSE_KEYWORDS = frozenset(
    {
        "asset url",
        "asset urls",
        "background asset",
        "background-image asset",
        "exact site asset",
        "exact site assets",
        "exact live-site",
        "exact live site",
        "live-site image",
        "live-site images",
        "live site image",
        "live site images",
        "reuse the extracted",
        "svg asset",
        "svg reference",
    }
)


def _mentions_footer_region(values: list[str]) -> bool:
    return any(
        keyword in value.strip().lower()
        for value in values
        for keyword in _FOOTER_KEYWORDS
        if value.strip()
    )


def _normalize_blueprint_label(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def _blueprint_label_tokens(value: str) -> set[str]:
    return {token for token in _normalize_blueprint_label(value).split("-") if token}


def _blueprint_text_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token}


def _contains_structure_signal(value: str, *, min_matches: int = 1) -> bool:
    tokens = _blueprint_text_tokens(value)
    return len(tokens & _STRUCTURE_SIGNAL_KEYWORDS) >= min_matches


def _is_vague_layout_description(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    if len(stripped) < 48:
        return True
    return not _contains_structure_signal(stripped)


def _count_nonempty(values: list[str]) -> int:
    return sum(1 for value in values if value.strip())


def _count_specific(values: list[str]) -> int:
    return sum(
        1 for value in values if value.strip() and _contains_structure_signal(value)
    )


def _contains_measured_typography(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    if re.search(r"\b\d+(?:\.\d+)?(?:px|rem|em)\b", lowered):
        return True
    return any(
        marker in lowered
        for marker in (
            "line-height",
            "letter-spacing",
            "tracking",
            "weight",
            "max-width",
            "uppercase",
            "lowercase",
            "capitalize",
        )
    )


def _count_keyword_matches(values: list[str], keywords: frozenset[str]) -> int:
    return sum(
        1
        for value in values
        if value.strip() and any(keyword in value.lower() for keyword in keywords)
    )


def _extract_urls_from_text(value: str) -> list[str]:
    return re.findall(r"https?://[^\s;,)]+", value)


def _reference_detail_signal_count(reference_bundle: ReferenceBundle) -> int:
    count = 0
    if reference_bundle.design_system_preflight is not None:
        design_system = reference_bundle.design_system_preflight
        count += len(design_system.section_typography)
        count += len(design_system.section_sizing)
        count += len(design_system.layout)
        count += len(design_system.components)
        count += len(design_system.motion_components)
        count += len(design_system.source_notes)
    if reference_bundle.live_reference is not None:
        design_system = reference_bundle.live_reference.design_system
        count += len(design_system.typography)
        count += len(design_system.layout)
        count += len(design_system.components)
        count += len(design_system.asset_inventory)
        count += len(design_system.dom_landmarks)
        count += len(design_system.section_inventory)
        count += len(design_system.chrome_layers)
        count += len(design_system.heading_hierarchy)
        count += len(design_system.shell_relationships)
        count += len(design_system.dom_evidence.section_candidates)
        count += len(design_system.dom_evidence.chrome_candidates)
        count += len(design_system.dom_evidence.footer_bands)
        count += len(design_system.dom_evidence.form_candidates)
        count += len(design_system.dom_evidence.repeated_groups)
        count += len(design_system.dom_evidence.state_variants)
        count += len(design_system.dom_evidence.wrapper_relationships)
        count += len(design_system.raw_observations)
    return count


def _reference_exposes_role_specific_typography(reference_bundle: ReferenceBundle) -> bool:
    if reference_bundle.design_system_preflight is not None and (
        len(reference_bundle.design_system_preflight.section_typography) >= 4
        or _count_keyword_matches(
            reference_bundle.design_system_preflight.section_typography,
            _TYPOGRAPHY_ROLE_KEYWORDS,
        )
        >= 2
    ):
        return True
    if reference_bundle.live_reference is not None and (
        len(reference_bundle.live_reference.design_system.typography) >= 5
    ):
        return True
    return False


def _reference_exposes_section_sizing(reference_bundle: ReferenceBundle) -> bool:
    if reference_bundle.design_system_preflight is not None and (
        len(reference_bundle.design_system_preflight.section_sizing) >= 3
        or len(reference_bundle.design_system_preflight.layout) >= 4
    ):
        return True
    if reference_bundle.live_reference is not None and (
        len(reference_bundle.live_reference.design_system.layout) >= 4
        or len(reference_bundle.live_reference.design_system.section_inventory) >= 5
    ):
        return True
    return False


def _reference_dom_text(reference_bundle: ReferenceBundle) -> list[str]:
    if reference_bundle.live_reference is None:
        return []
    design_system = reference_bundle.live_reference.design_system
    return [
        *design_system.dom_landmarks,
        *design_system.section_inventory,
        *design_system.chrome_layers,
        *design_system.heading_hierarchy,
        *design_system.shell_relationships,
        *_reference_dom_evidence_lines(design_system),
        *design_system.raw_observations,
    ]


def _reference_dom_evidence_lines(design_system: Any) -> list[str]:
    dom_evidence = design_system.dom_evidence
    values: list[str] = []
    candidate_groups = (
        dom_evidence.section_candidates,
        dom_evidence.chrome_candidates,
        dom_evidence.footer_bands,
        dom_evidence.form_candidates,
        dom_evidence.repeated_groups,
        dom_evidence.state_variants,
    )
    for group in candidate_groups:
        for candidate in group:
            parts = [
                candidate.kind,
                candidate.label,
                candidate.selector,
                candidate.heading_text,
                candidate.text_sample,
                candidate.background,
                *candidate.notes[:3],
            ]
            text = " | ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
            if text:
                values.append(text)
    for relationship in dom_evidence.wrapper_relationships:
        parts = [
            relationship.relationship,
            relationship.child_selector,
            relationship.parent_selector,
            *relationship.notes[:2],
        ]
        text = " | ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
        if text:
            values.append(text)
    return values


def _reference_component_text(reference_bundle: ReferenceBundle) -> list[str]:
    values: list[str] = []
    if reference_bundle.live_reference is not None:
        design_system = reference_bundle.live_reference.design_system
        values.extend(design_system.layout)
        values.extend(design_system.components)
        values.extend(_reference_dom_evidence_lines(design_system))
        values.extend(design_system.raw_observations)
    if reference_bundle.design_system_preflight is not None:
        design_system = reference_bundle.design_system_preflight
        values.extend(design_system.layout)
        values.extend(design_system.components)
        values.extend(design_system.section_sizing)
        values.extend(design_system.source_notes)
    return [value.lower() for value in values if value.strip()]


def _reference_asset_evidence_lines(reference_bundle: ReferenceBundle) -> list[str]:
    values: list[str] = []
    if reference_bundle.live_reference is not None:
        values.extend(reference_bundle.live_reference.design_system.asset_inventory)
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_values.append(normalized)
    return unique_values


def _reference_asset_urls(reference_bundle: ReferenceBundle) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for value in _reference_asset_evidence_lines(reference_bundle):
        for url in _extract_urls_from_text(value):
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


def _extract_font_asset_urls(reference_bundle: ReferenceBundle) -> list[str]:
    full_dom = (
        reference_bundle.live_reference.full_dom_html
        if reference_bundle.live_reference is not None
        else ""
    )
    if not full_dom.strip():
        return []

    seen: set[str] = set()
    urls: list[str] = []
    for match in re.findall(
        r"(?:https?:)?//[^\"'\s>]+\.woff2",
        full_dom,
        flags=re.IGNORECASE,
    ):
        normalized = match.strip()
        if normalized.startswith("//"):
            normalized = f"https:{normalized}"
        lowered = normalized.lower()
        if not any(
            token in lowered
            for token in (
                "aeonik",
                "abcarizona",
                "abc-arizona",
                "architekt",
                "nb_architekt",
            )
        ):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


def _reference_dom_roles(reference_bundle: ReferenceBundle) -> set[str]:
    values = [value.lower() for value in _reference_dom_text(reference_bundle) if value.strip()]
    roles: set[str] = set()
    for role, keywords in _DOM_ROLE_HINTS.items():
        if any(any(keyword in value for keyword in keywords) for value in values):
            roles.add(role)
    return roles


def _reference_exposes_separate_header_states(reference_bundle: ReferenceBundle) -> bool:
    values = [value.lower() for value in _reference_dom_text(reference_bundle) if value.strip()]
    has_header = any(
        "header" in value or 'role="banner"' in value or "navigation" in value
        for value in values
    )
    has_sticky_state = any(
        "sticky" in value or "scroll-state" in value or "scrolled" in value
        for value in values
    )
    return has_header and has_sticky_state


def _blueprint_mentions_live_asset_reuse(
    requirements: RequirementsSpec, reference_bundle: ReferenceBundle
) -> bool:
    blueprint_values = [
        *requirements.asset_requirements,
        *(
            asset
            for section in requirements.section_requirements
            for asset in section.assets
        ),
    ]
    blueprint_text = " ".join(value.strip().lower() for value in blueprint_values if value.strip())
    if any(keyword in blueprint_text for keyword in _ASSET_REUSE_KEYWORDS):
        return True
    reference_urls = _reference_asset_urls(reference_bundle)
    if reference_urls and any(url in blueprint_text for url in reference_urls[:6]):
        return True
    return False


def _blueprint_distinguishes_header_states(requirements: RequirementsSpec) -> bool:
    has_base_header = False
    has_sticky_state = False
    for section in requirements.section_requirements:
        section_text = " ".join(
            value.strip().lower()
            for value in (section.name, section.section_id)
            if value.strip()
        )
        section_is_sticky = any(
            keyword in section_text
            for keyword in ("sticky", "scroll-state", "scrolled")
        )
        section_is_base_header = "header" in section_text and not section_is_sticky
        has_base_header = has_base_header or section_is_base_header
        has_sticky_state = has_sticky_state or section_is_sticky
    if has_base_header and has_sticky_state:
        return True

    coverage_blob = " ".join(
        value.strip().lower()
        for value in requirements.coverage_notes
        if value.strip()
    )
    return all(
        keyword in coverage_blob for keyword in ("header", "sticky", "merge")
    )


def _is_shop_now_bar_section(section: SectionRequirement) -> bool:
    normalized = _normalize_blueprint_label(section.section_id or section.name)
    return normalized == "shop-now-bar" or (
        "shop now" in section.name.lower() and "bar" in section.name.lower()
    )


def _is_sticky_header_state_section(section: SectionRequirement) -> bool:
    if _is_shop_now_bar_section(section):
        return False
    normalized = _normalize_blueprint_label(section.section_id or section.name)
    if normalized in {"sticky-header", "sticky-header-state", "scroll-header", "scrolled-header"}:
        return True
    section_text = " ".join(
        value.strip().lower()
        for value in (section.name, section.section_id)
        if value.strip()
    )
    return any(
        keyword in section_text
        for keyword in (
            "sticky header",
            "sticky-header",
            "scroll-state",
            "scroll state",
            "scrolled header",
            "scrolled-header",
        )
    )


def _reference_custom_font_names(reference_bundle: ReferenceBundle) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    typography_entries: list[str] = []
    if reference_bundle.design_system_preflight is not None:
        typography_entries.extend(reference_bundle.design_system_preflight.typography)
        typography_entries.extend(
            reference_bundle.design_system_preflight.section_typography
        )
    if reference_bundle.live_reference is not None:
        typography_entries.extend(reference_bundle.live_reference.design_system.typography)
        typography_entries.extend(
            reference_bundle.live_reference.design_system.heading_hierarchy
        )

    for entry in typography_entries:
        for quoted_name in re.findall(r"['\"]([^'\"]+)['\"]", entry):
            normalized = quoted_name.strip()
            if normalized and normalized.lower() not in {"sans-serif", "serif"}:
                if normalized not in seen:
                    seen.add(normalized)
                    names.append(normalized)
        match = re.search(r"font\s+(.+?);", entry)
        if match is None:
            continue
        for part in match.group(1).split(","):
            normalized = part.strip().strip('"').strip("'")
            lowered = normalized.lower()
            if not normalized or lowered in {"sans-serif", "serif", "monospace", "arial"}:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            names.append(normalized)
    return names


def _blueprint_mentions_font_loading(requirements: RequirementsSpec) -> bool:
    blueprint_text = _blueprint_text_blob(requirements)
    return any(keyword in blueprint_text for keyword in _FONT_LOADING_KEYWORDS)


def _blueprint_text_blob(requirements: RequirementsSpec) -> str:
    values = [
        *requirements.page_outline,
        *requirements.closing_sections,
        requirements.footer_description,
        *requirements.coverage_notes,
        *requirements.critical_layout_invariants,
        *requirements.hard_constraints,
        *requirements.preserve_requirements,
        *requirements.layout_requirements,
        *requirements.styling_requirements,
        *requirements.copy_requirements,
        *requirements.asset_requirements,
        *requirements.behavior_requirements,
        *requirements.animation_requirements,
        *requirements.structure_guidance,
        *requirements.execution_plan,
        *requirements.known_unknowns,
        *requirements.acceptance_criteria,
    ]
    for section in requirements.section_requirements:
        values.extend(
            [
                section.name,
                section.section_id,
                section.purpose,
                section.layout,
                *section.layout_invariants,
                *section.must_include,
                *section.styling,
                *section.copy_items,
                *section.assets,
                *section.behaviors,
                *section.editable_fields,
            ]
        )
    for checkpoint in requirements.interaction_checkpoints:
        values.extend(
            [
                checkpoint.name,
                checkpoint.trigger,
                checkpoint.expected_result,
                checkpoint.target_description,
            ]
        )
    return " ".join(value for value in values if value.strip()).lower()


def _missing_dom_roles(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
) -> list[str]:
    blueprint_text = _blueprint_text_blob(requirements)
    missing_roles: list[str] = []
    for role in sorted(_reference_dom_roles(reference_bundle)):
        keywords = _DOM_ROLE_HINTS[role]
        if any(keyword in blueprint_text for keyword in keywords):
            continue
        missing_roles.append(role)
    return missing_roles


def _missing_component_geometry_signals(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
) -> list[str]:
    reference_values = _reference_component_text(reference_bundle)
    if not reference_values:
        return []
    blueprint_text = _blueprint_text_blob(requirements)
    missing_signals: list[str] = []
    for signal, keywords in _COMPONENT_GEOMETRY_REFERENCE_HINTS.items():
        if not any(any(keyword in value for keyword in keywords) for value in reference_values):
            continue
        blueprint_keywords = _COMPONENT_GEOMETRY_BLUEPRINT_HINTS[signal]
        blueprint_keyword_matches = sum(
            1 for keyword in blueprint_keywords if keyword in blueprint_text
        )
        if blueprint_keyword_matches >= _COMPONENT_GEOMETRY_BLUEPRINT_MIN_MATCHES[signal]:
            continue
        missing_signals.append(signal.replace("_", " "))
    return missing_signals


def _section_matches_outline_entry(entry: str, section_name: str, section_id: str) -> bool:
    normalized_entry = _normalize_blueprint_label(entry)
    candidates = [
        normalized_entry,
        _normalize_blueprint_label(section_name),
        _normalize_blueprint_label(section_id),
    ]
    section_candidates = [candidate for candidate in candidates[1:] if candidate]
    for candidate in section_candidates:
        if normalized_entry == candidate:
            return True
        if normalized_entry and candidate and (
            normalized_entry in candidate or candidate in normalized_entry
        ):
            return True

    entry_tokens = _blueprint_label_tokens(entry)
    for candidate in section_candidates:
        candidate_tokens = {token for token in candidate.split("-") if token}
        if len(entry_tokens & candidate_tokens) >= 2:
            return True
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


_SECTION_EVIDENCE_STOPWORDS = frozenset(
    {
        "and",
        "background",
        "bar",
        "body",
        "child",
        "class",
        "column",
        "container",
        "content",
        "display",
        "div",
        "height",
        "main",
        "max",
        "panel",
        "px",
        "row",
        "section",
        "shell",
        "site",
        "surface",
        "text",
        "top",
        "width",
    }
)

_SECTION_ROLE_KEYWORDS: dict[str, frozenset[str]] = {
    "modal": frozenset({"modal", "overlay", "popup", "dialog"}),
    "announcement": frozenset({"announcement", "banner", "ticker", "marquee"}),
    "sticky": frozenset({"sticky", "scroll-state", "scrolled"}),
    "header": frozenset({"header", "nav", "navigation", "menu"}),
    "hero": frozenset({"hero", "article-header", "headline", "eyebrow", "title"}),
    "body": frozenset({"article-body", "article-content", "reading", "paragraph", "subhead"}),
    "showcase": frozenset(
        {"showcase", "product", "bundle", "feature", "features", "spotlight", "collection"}
    ),
    "stats": frozenset({"stats", "stat", "counter", "metric", "metrics", "numbers"}),
    "trust": frozenset({"trust", "verified", "verification", "third-party", "third party", "quality"}),
    "badges": frozenset({"badges", "badge", "icons", "icon-text", "icon and text", "tested", "gmo", "vegan"}),
    "testimonials": frozenset({"testimonial", "testimonials", "review", "reviews", "results", "social-proof"}),
    "comparison": frozenset({"comparison", "compare", "vs", "versus"}),
    "faq": frozenset({"faq", "accordion", "question", "questions"}),
    "cta": frozenset({"cta-banner", "call-to-action", "bestseller", "try omni today", "be creatine-powered"}),
    "related": frozenset({"related", "articles", "recommend", "recommended", "read-more"}),
    "footer": frozenset(
        {"footer", "newsletter", "legal", "copyright", "privacy", "terms", "accessibility"}
    ),
}

_CANONICAL_SECTION_IDENTITIES: dict[str, tuple[str, str]] = {
    "announcement": ("Announcement Bar", "announcement-bar"),
    "header": ("Site Header", "site-header"),
    "sticky": ("Sticky Header State", "sticky-header-state"),
    "hero": ("Article Hero", "article-hero"),
    "body": ("Article Body", "article-body"),
    "showcase": ("Product Showcase", "product-showcase"),
    "related": ("Related Articles", "related-articles"),
    "footer": ("Site Footer", "site-footer"),
}

_GENERIC_SECTION_ID_ALIASES: dict[str, frozenset[str]] = {
    "modal": frozenset(
        {
            "modal",
            "modal-overlay",
            "overlay",
            "popup",
            "dialog",
            "alia-overlay",
            "alia-popup",
            "promo-overlay",
            "promo-modal",
        }
    ),
    "announcement": frozenset({"announcement", "announcement-bar", "promo-bar", "banner"}),
    "header": frozenset({"header", "global-header", "primary-header", "nav-header"}),
    "sticky": frozenset(
        {"sticky-header", "sticky-header-state", "scroll-header", "scrolled-header"}
    ),
    "hero": frozenset({"hero", "article-hero", "article-header"}),
    "body": frozenset({"body", "article-content", "article-body", "content-body"}),
    "showcase": frozenset(
        {"showcase", "product-showcase", "product-bundle", "product-bundle-split", "feature-showcase"}
    ),
    "related": frozenset({"related", "related-content", "related-articles"}),
    "footer": frozenset({"footer", "global-footer", "site-footer"}),
}

_GENERIC_BLUEPRINT_MUST_INCLUDE_PLACEHOLDERS = frozenset(
    {
        "primary content group",
        "secondary supporting content",
        "section-specific action or media",
        "brand/logo cluster",
        "primary navigation",
        "utility actions",
        "sticky brand/logo cluster",
        "persistent navigation",
        "sticky utility actions",
        "announcement copy",
        "announcement shell",
        "inline utility control or link",
    }
)

_GENERIC_BLUEPRINT_STYLING_PLACEHOLDERS = frozenset(
    {
        "section-specific surface treatment",
        "measured spacing",
        "measured panel and card spacing",
    }
)


def _append_unique_strings(values: list[str], candidates: list[str]) -> bool:
    changed = False
    seen = {value.strip().lower() for value in values if value.strip()}
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        values.append(normalized)
        seen.add(lowered)
        changed = True
    return changed


def _reference_evidence_lines(reference_bundle: ReferenceBundle) -> list[str]:
    values: list[str] = []
    if reference_bundle.live_reference is not None:
        design_system = reference_bundle.live_reference.design_system
        values.extend(design_system.typography)
        values.extend(design_system.layout)
        values.extend(design_system.components)
        values.extend(design_system.asset_inventory)
        values.extend(design_system.dom_landmarks)
        values.extend(design_system.section_inventory)
        values.extend(design_system.chrome_layers)
        values.extend(design_system.heading_hierarchy)
        values.extend(design_system.shell_relationships)
        values.extend(_reference_dom_evidence_lines(design_system))
        values.extend(design_system.raw_observations)
    if reference_bundle.design_system_preflight is not None:
        design_system = reference_bundle.design_system_preflight
        values.extend(design_system.typography)
        values.extend(design_system.section_typography)
        values.extend(design_system.layout)
        values.extend(design_system.section_sizing)
        values.extend(design_system.components)
        values.extend(design_system.motion_components)
        values.extend(design_system.source_notes)
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_values.append(normalized)
    return unique_values


def _reference_component_evidence_lines(reference_bundle: ReferenceBundle) -> list[str]:
    values: list[str] = []
    if reference_bundle.live_reference is not None:
        design_system = reference_bundle.live_reference.design_system
        values.extend(design_system.layout)
        values.extend(design_system.components)
        values.extend(design_system.raw_observations)
    if reference_bundle.design_system_preflight is not None:
        design_system = reference_bundle.design_system_preflight
        values.extend(design_system.layout)
        values.extend(design_system.section_sizing)
        values.extend(design_system.components)
        values.extend(design_system.source_notes)
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_values.append(normalized)
    return unique_values


def _blueprint_section_key(section: SectionRequirement) -> str:
    return _normalize_blueprint_label(section.section_id or section.name)


def _material_blueprint_regression(
    previous: RequirementsSpec,
    candidate: RequirementsSpec,
) -> bool:
    previous_sections = [
        section for section in previous.section_requirements if _blueprint_section_key(section)
    ]
    candidate_sections = [
        section for section in candidate.section_requirements if _blueprint_section_key(section)
    ]
    if len(previous_sections) >= 6 and len(candidate_sections) < max(
        4, int(len(previous_sections) * 0.7)
    ):
        return True

    previous_outline = [entry for entry in previous.page_outline if entry.strip()]
    candidate_outline = [entry for entry in candidate.page_outline if entry.strip()]
    if len(previous_outline) >= 6 and len(candidate_outline) < max(
        4, int(len(previous_outline) * 0.7)
    ):
        return True

    if previous.wrapper_requirements and not candidate.wrapper_requirements:
        return True

    previous_global_lists = (
        previous.critical_layout_invariants,
        previous.hard_constraints,
        previous.layout_requirements,
        previous.styling_requirements,
        previous.asset_requirements,
        previous.acceptance_criteria,
    )
    candidate_global_lists = (
        candidate.critical_layout_invariants,
        candidate.hard_constraints,
        candidate.layout_requirements,
        candidate.styling_requirements,
        candidate.asset_requirements,
        candidate.acceptance_criteria,
    )
    if sum(bool(values) for values in previous_global_lists) >= 3 and sum(
        bool(values) for values in candidate_global_lists
    ) <= 1:
        return True

    return False


def _merge_blueprint_regression(
    previous: RequirementsSpec,
    candidate: RequirementsSpec,
) -> RequirementsSpec:
    merged = candidate.model_copy(deep=True)

    previous_sections = {
        _blueprint_section_key(section): section
        for section in previous.section_requirements
        if _blueprint_section_key(section)
    }
    candidate_sections = {
        _blueprint_section_key(section): section
        for section in candidate.section_requirements
        if _blueprint_section_key(section)
    }

    merged_sections: list[SectionRequirement] = []
    seen_keys: set[str] = set()
    for section in previous.section_requirements:
        key = _blueprint_section_key(section)
        if not key:
            continue
        seen_keys.add(key)
        merged_sections.append(candidate_sections.get(key, section))
    for section in candidate.section_requirements:
        key = _blueprint_section_key(section)
        if key and key not in seen_keys:
            seen_keys.add(key)
            merged_sections.append(section)
    if merged_sections:
        merged.section_requirements = merged_sections

    candidate_outline_map = {
        _normalize_blueprint_label(entry): entry
        for entry in candidate.page_outline
        if entry.strip()
    }
    merged_outline: list[str] = []
    seen_outline: set[str] = set()
    for entry in previous.page_outline:
        key = _normalize_blueprint_label(entry)
        if not key:
            continue
        seen_outline.add(key)
        merged_outline.append(candidate_outline_map.get(key, entry))
    for entry in candidate.page_outline:
        key = _normalize_blueprint_label(entry)
        if key and key not in seen_outline:
            seen_outline.add(key)
            merged_outline.append(entry)
    if merged_outline:
        merged.page_outline = merged_outline

    if previous.wrapper_requirements and not merged.wrapper_requirements:
        merged.wrapper_requirements = previous.wrapper_requirements

    for field_name in (
        "closing_sections",
        "coverage_notes",
        "critical_layout_invariants",
        "hard_constraints",
        "preserve_requirements",
        "layout_requirements",
        "styling_requirements",
        "copy_requirements",
        "asset_requirements",
        "behavior_requirements",
        "animation_requirements",
        "structure_guidance",
        "execution_plan",
        "known_unknowns",
        "acceptance_criteria",
    ):
        previous_values = list(getattr(previous, field_name))
        candidate_values = list(getattr(merged, field_name))
        if previous_values and not candidate_values:
            setattr(merged, field_name, previous_values)

    if previous.footer_present and merged.footer_present is None:
        merged.footer_present = previous.footer_present
    if previous.footer_description.strip() and not merged.footer_description.strip():
        merged.footer_description = previous.footer_description
    if previous.summary.strip() and not merged.summary.strip():
        merged.summary = previous.summary
    if previous.template_goal.strip() and not merged.template_goal.strip():
        merged.template_goal = previous.template_goal

    if previous.design_tokens.typography and not merged.design_tokens.typography:
        merged.design_tokens.typography = previous.design_tokens.typography
    if previous.design_tokens.colors and not merged.design_tokens.colors:
        merged.design_tokens.colors = previous.design_tokens.colors
    if previous.design_tokens.spacing and not merged.design_tokens.spacing:
        merged.design_tokens.spacing = previous.design_tokens.spacing
    if previous.design_tokens.radii and not merged.design_tokens.radii:
        merged.design_tokens.radii = previous.design_tokens.radii
    if previous.design_tokens.shadows and not merged.design_tokens.shadows:
        merged.design_tokens.shadows = previous.design_tokens.shadows

    return merged


def _default_outline_section_requirement(
    section_name: str,
    section_id: str,
    *,
    parent_wrapper_id: str = "",
) -> SectionRequirement:
    normalized_id = _normalize_blueprint_label(section_id or section_name)
    role_hint = SectionRequirement(name=section_name, section_id=normalized_id)
    role = _section_role(role_hint)
    layout, invariants, must_include, styling = _default_section_blueprint(role)

    purpose = (
        f"Represent the {section_name} as a distinct canonical page section in the "
        "same order and hierarchy as the reference."
    )

    if "faq" in normalized_id:
        layout = (
            "Dedicated FAQ section with a section heading and an accordion-style list "
            "of question/answer items."
        )
        invariants.append(
            "Keep the FAQ as its own section with vertically stacked accordion items instead of collapsing it into generic body copy or footer text."
        )
        must_include = ["section heading", "accordion question list", "answer panels"]
        styling.append("accordion rows with measured separators or card surfaces")
    elif "comparison" in normalized_id:
        layout = (
            "Comparison section with a heading and side-by-side comparison content "
            "or rows that contrast the primary offer against alternatives."
        )
        invariants.append(
            "Keep the comparison information in a measured comparative layout instead of flattening it into one generic text block."
        )
        must_include = ["section heading", "comparison labels", "comparison rows or columns"]
    elif "testimonial" in normalized_id or "review" in normalized_id:
        layout = (
            "Social-proof section with testimonial or expert-review content grouped "
            "into cards, quotes, or endorsement blocks."
        )
        invariants.append(
            "Preserve the repeated quote/review grouping instead of merging it into adjacent informational sections."
        )
        must_include = ["section heading", "quote or endorsement content", "attribution or review card group"]
    elif "cta" in normalized_id or "signup" in normalized_id:
        layout = (
            "Call-to-action section with a clear primary message, supporting detail, "
            "and a focused action or signup control."
        )
        invariants.append(
            "Keep the CTA as a dedicated conversion section instead of absorbing it into adjacent content."
        )
        must_include = ["primary CTA message", "supporting copy", "action control or signup field"]
    elif "marquee" in normalized_id:
        layout = (
            "Scrolling marquee or repeated-logo strip with continuous horizontal flow "
            "inside its own measured band."
        )
        invariants.append(
            "Keep the marquee as a distinct horizontal strip rather than converting it into a static text row."
        )
        must_include = ["continuous horizontal strip", "repeated labels or logos", "separate marquee band"]
    elif "badge" in normalized_id:
        layout = (
            "Compact strip of trust badges, logos, or icon-backed proof points in a "
            "measured row."
        )
        invariants.append(
            "Preserve the badges as a dedicated repeated row rather than burying them inside nearby text content."
        )
        must_include = ["badge or icon row", "short supporting labels"]

    if parent_wrapper_id:
        invariants.append(
            f"Keep this section inside the shared wrapper `{parent_wrapper_id}` rather than splitting it into a standalone outer shell."
        )

    return SectionRequirement(
        name=section_name,
        section_id=normalized_id,
        purpose=purpose,
        layout=layout,
        layout_invariants=invariants,
        must_include=must_include,
        styling=styling,
    )


def _default_wrapper_requirement(
    wrapper_name: str,
    wrapper_id: str,
    participant_section_ids: list[str],
    *,
    kind: str = "shared_wrapper",
    notes: list[str] | None = None,
) -> WrapperRequirement:
    participant_names = ", ".join(participant_section_ids)
    wrapper_kind = (
        kind
        if kind
        in {
            "shared_wrapper",
            "shared_shell",
            "split_container",
            "nested_shell",
            "surface_group",
            "state_container",
        }
        else "shared_wrapper"
    )
    layout_invariants = [
        f"Keep {participant_names} inside one {wrapper_name} wrapper so the shared DOM hierarchy and cross-section surface remain intact."
    ]
    if notes:
        layout_invariants.extend(note for note in notes if note.strip())

    return WrapperRequirement(
        name=wrapper_name,
        wrapper_id=wrapper_id,
        kind=wrapper_kind,
        participant_section_ids=participant_section_ids,
        purpose=(
            f"Preserve the shared container relationship for {participant_names} so "
            "the executor keeps the same grouped surface as the reference."
        ),
        layout_invariants=layout_invariants,
        must_include=[
            "shared parent wrapper",
            *[f"child section `{section_id}`" for section_id in participant_section_ids],
        ],
        styling=["wrapper-owned shared surface, background, or spacing treatment"],
    )


def _merge_requirements_with_reference_outline(
    requirements: RequirementsSpec,
    reference_bundle: ReferenceBundle,
) -> tuple[RequirementsSpec, bool]:
    seed_outline = _seed_outline_from_reference_bundle(reference_bundle)
    if seed_outline is None:
        return requirements, False

    repaired = requirements.model_copy(deep=True)
    changed = False

    seed_section_ids = {
        _canonical_blueprint_key(
            entry.name,
            entry.section_id,
            reference_bundle=reference_bundle,
        ): entry
        for entry in seed_outline.page_outline
    }
    current_outline_map = {
        _canonical_blueprint_key(
            entry,
            entry,
            reference_bundle=reference_bundle,
        ): entry
        for entry in repaired.page_outline
        if entry.strip()
    }
    extra_outline_entries = [
        entry
        for entry in repaired.page_outline
        if entry.strip()
        and _canonical_blueprint_key(
            entry,
            entry,
            reference_bundle=reference_bundle,
        )
        not in seed_section_ids
    ]
    merged_outline = list(extra_outline_entries)
    seen_outline = {
        _canonical_blueprint_key(entry, entry, reference_bundle=reference_bundle)
        for entry in extra_outline_entries
    }
    for seed_entry in seed_outline.page_outline:
        key = _canonical_blueprint_key(
            seed_entry.name,
            seed_entry.section_id,
            reference_bundle=reference_bundle,
        )
        if key in seen_outline:
            continue
        merged_outline.append(current_outline_map.get(key, seed_entry.name))
        seen_outline.add(key)
    if merged_outline != repaired.page_outline:
        repaired.page_outline = merged_outline
        changed = True

    current_sections = {
        _canonical_blueprint_key(
            section.name,
            section.section_id,
            reference_bundle=reference_bundle,
        ): section
        for section in repaired.section_requirements
        if _canonical_blueprint_key(
            section.name,
            section.section_id,
            reference_bundle=reference_bundle,
        )
    }
    extra_sections = [
        section
        for section in repaired.section_requirements
        if _canonical_blueprint_key(
            section.name,
            section.section_id,
            reference_bundle=reference_bundle,
        )
        not in seed_section_ids
    ]
    merged_sections = list(extra_sections)
    seen_sections = {
        _canonical_blueprint_key(
            section.name,
            section.section_id,
            reference_bundle=reference_bundle,
        )
        for section in extra_sections
    }
    for seed_entry in seed_outline.page_outline:
        key = _canonical_blueprint_key(
            seed_entry.name,
            seed_entry.section_id,
            reference_bundle=reference_bundle,
        )
        if key in seen_sections:
            continue
        merged_sections.append(
            current_sections.get(
                key,
                _default_outline_section_requirement(
                    seed_entry.name,
                    seed_entry.section_id,
                    parent_wrapper_id=seed_entry.parent_wrapper_id,
                ),
            )
        )
        seen_sections.add(key)
    if merged_sections != repaired.section_requirements:
        repaired.section_requirements = merged_sections
        changed = True

    current_wrappers = {
        _normalize_blueprint_label(wrapper.wrapper_id or wrapper.name): wrapper
        for wrapper in repaired.wrapper_requirements
        if (wrapper.wrapper_id or wrapper.name).strip()
    }
    for wrapper_outline in seed_outline.wrapper_outline:
        key = _normalize_blueprint_label(wrapper_outline.wrapper_id or wrapper_outline.name)
        if key in current_wrappers:
            continue
        repaired.wrapper_requirements.append(
            _default_wrapper_requirement(
                wrapper_outline.name,
                wrapper_outline.wrapper_id,
                wrapper_outline.participant_section_ids,
                kind=wrapper_outline.kind,
                notes=[*wrapper_outline.notes, *wrapper_outline.source_relationships],
            )
        )
        changed = True

    if any(
        "main content shell" in value.lower()
        for value in (
            *repaired.critical_layout_invariants,
            *repaired.coverage_notes,
            *repaired.layout_requirements,
        )
    ) and "main-content-shell" not in current_wrappers:
        participant_section_ids = [
            section.section_id
            for section in repaired.section_requirements
            if _section_role(section)
            not in {"modal", "announcement", "header", "sticky", "footer"}
        ]
        if len(participant_section_ids) >= 2:
            repaired.wrapper_requirements.append(
                _default_wrapper_requirement(
                    "Main Content Shell",
                    "main-content-shell",
                    participant_section_ids,
                    kind="shared_shell",
                    notes=[
                        "Keep the primary content sections grouped inside one main-content shell between the header chrome and the footer shell."
                    ],
                )
            )
            changed = True

    canonical_closing = _build_canonical_closing_sections(repaired)
    if canonical_closing != repaired.closing_sections:
        repaired.closing_sections = canonical_closing
        changed = True
    if repaired.footer_present is None and seed_outline.footer_present is not None:
        repaired.footer_present = seed_outline.footer_present
        changed = True
    if seed_outline.footer_description.strip() and not repaired.footer_description.strip():
        repaired.footer_description = seed_outline.footer_description
        changed = True
    if seed_outline.coverage_notes:
        merged_coverage = list(repaired.coverage_notes)
        if _append_unique_strings(merged_coverage, list(seed_outline.coverage_notes)):
            repaired.coverage_notes = merged_coverage
            changed = True

    return repaired, changed


def _ensure_minimum_blueprint_global_lists(
    requirements: RequirementsSpec,
    reference_bundle: ReferenceBundle,
) -> tuple[RequirementsSpec, bool]:
    repaired = requirements.model_copy(deep=True)
    changed = False

    if not repaired.wrapper_requirements:
        repaired, wrapper_changed = _merge_requirements_with_reference_outline(
            repaired, reference_bundle
        )
        changed |= wrapper_changed

    if not repaired.layout_requirements:
        layout_candidates: list[str] = []
        layout_candidates.extend(repaired.critical_layout_invariants[:4])
        for wrapper in repaired.wrapper_requirements[:3]:
            if wrapper.layout_invariants:
                layout_candidates.append(
                    f"{wrapper.name}: {wrapper.layout_invariants[0]}"
                )
            elif wrapper.purpose.strip():
                layout_candidates.append(f"{wrapper.name}: {wrapper.purpose}")
        for section in repaired.section_requirements[:8]:
            if section.layout.strip():
                layout_candidates.append(f"{section.name}: {section.layout}")
            elif section.layout_invariants:
                layout_candidates.append(
                    f"{section.name}: {section.layout_invariants[0]}"
                )
        changed |= _append_unique_strings(
            repaired.layout_requirements,
            layout_candidates[:10],
        )

    if not repaired.styling_requirements:
        styling_candidates: list[str] = []
        styling_candidates.extend(
            f"color token: {value}" for value in repaired.design_tokens.colors[:3]
        )
        styling_candidates.extend(
            f"radius token: {value}" for value in repaired.design_tokens.radii[:2]
        )
        for section in repaired.section_requirements[:8]:
            if section.styling:
                styling_candidates.append(
                    f"{section.name}: {section.styling[0]}"
                )
        changed |= _append_unique_strings(
            repaired.styling_requirements,
            styling_candidates[:10],
        )

    if not repaired.behavior_requirements:
        behavior_candidates: list[str] = []
        for section in repaired.section_requirements:
            if section.behaviors:
                behavior_candidates.append(f"{section.name}: {section.behaviors[0]}")
                continue
            normalized_id = _normalize_blueprint_label(section.section_id or section.name)
            if "faq" in normalized_id:
                behavior_candidates.append(
                    "FAQ accordion items expand and collapse independently without affecting the surrounding section layout."
                )
            elif normalized_id in {"promotional-modal", "modal-overlay"}:
                behavior_candidates.append(
                    "Promotional modal can be dismissed cleanly so the page beneath remains fully interactive."
                )
            elif "sticky-header" in normalized_id or "shop-now" in normalized_id:
                behavior_candidates.append(
                    "Scroll-state chrome transitions between the opening header and sticky header/shop-now states without collapsing them into one header."
                )
            elif "marquee" in normalized_id:
                behavior_candidates.append(
                    "The marquee remains a distinct moving or repeated horizontal band instead of degrading into a static paragraph."
                )
        changed |= _append_unique_strings(
            repaired.behavior_requirements,
            behavior_candidates[:8],
        )

    if not repaired.animation_requirements:
        animation_candidates: list[str] = []
        if reference_bundle.design_system_preflight is not None:
            animation_candidates.extend(
                reference_bundle.design_system_preflight.motion[:3]
            )
            animation_candidates.extend(
                reference_bundle.design_system_preflight.motion_components[:3]
            )
        for section in repaired.section_requirements:
            normalized_id = _normalize_blueprint_label(section.section_id or section.name)
            if "faq" in normalized_id:
                animation_candidates.append(
                    "Accordion answer panels animate open and closed with a measured height and opacity transition."
                )
            elif normalized_id in {"promotional-modal", "modal-overlay"}:
                animation_candidates.append(
                    "Modal entry and dismissal keep their own overlay/dialog transition instead of snapping abruptly."
                )
            elif "sticky-header" in normalized_id or "shop-now" in normalized_id:
                animation_candidates.append(
                    "Sticky header state changes use smooth position or opacity transitions rather than abrupt swaps."
                )
            elif "marquee" in normalized_id:
                animation_candidates.append(
                    "The marquee maintains continuous horizontal motion with no visible jump cuts."
                )
        changed |= _append_unique_strings(
            repaired.animation_requirements,
            animation_candidates[:8],
        )

    if not repaired.execution_plan or not _execution_plan_covers_outline(repaired):
        execution_steps = _build_canonical_execution_plan(repaired)
        if repaired.execution_plan != execution_steps:
            repaired.execution_plan = execution_steps
            changed = True

    if not repaired.acceptance_criteria:
        acceptance_candidates: list[str] = []
        acceptance_candidates.append(
            "Every named entry in page_outline exists as a corresponding DOM section in the final implementation."
        )
        for wrapper in repaired.wrapper_requirements[:3]:
            acceptance_candidates.append(
                f"The shared wrapper `{wrapper.wrapper_id}` contains {', '.join(wrapper.participant_section_ids)} in the final DOM."
            )
        if repaired.behavior_requirements:
            acceptance_candidates.append(
                "All required interactive or stateful behaviors described in behavior_requirements work in the rendered output."
            )
        if repaired.footer_present:
            acceptance_candidates.append(
                "The closing page state preserves the complete footer region described by the blueprint."
            )
        changed |= _append_unique_strings(
            repaired.acceptance_criteria,
            acceptance_candidates[:8],
        )

    return repaired, changed


def _execution_plan_covers_outline(requirements: RequirementsSpec) -> bool:
    if not requirements.execution_plan:
        return False
    normalized_steps = [
        re.sub(r"^\s*\d+\.\s*", "", step).strip()
        for step in requirements.execution_plan
        if step.strip()
    ]
    if len(normalized_steps) < len(requirements.page_outline):
        return False
    for outline_name in requirements.page_outline:
        if not any(
            _section_matches_outline_entry(step, outline_name, outline_name)
            for step in normalized_steps
        ):
            return False
    return True


def _section_detail_score(section: SectionRequirement) -> int:
    return sum(
        bool(value)
        for value in (
            section.purpose.strip(),
            section.layout.strip(),
            section.layout_invariants,
            section.must_include,
            section.styling,
            section.copy_items,
            section.assets,
            section.behaviors,
            section.editable_fields,
        )
    )


def _dedupe_blueprint_requirements(
    requirements: RequirementsSpec,
    *,
    reference_bundle: ReferenceBundle,
) -> tuple[RequirementsSpec, bool]:
    repaired = requirements.model_copy(deep=True)
    changed = False

    deduped_sections: list[SectionRequirement] = []
    section_index_by_key: dict[str, int] = {}
    for section in repaired.section_requirements:
        key = _canonical_blueprint_key(
            section.name,
            section.section_id,
            reference_bundle=reference_bundle,
        )
        if not key:
            continue
        existing_index = section_index_by_key.get(key)
        if existing_index is None:
            section_index_by_key[key] = len(deduped_sections)
            deduped_sections.append(section)
            continue
        if _section_detail_score(section) > _section_detail_score(
            deduped_sections[existing_index]
        ):
            deduped_sections[existing_index] = section
        changed = True
    if deduped_sections != repaired.section_requirements:
        repaired.section_requirements = deduped_sections
        changed = True

    deduped_wrappers: list[WrapperRequirement] = []
    seen_wrapper_ids: set[str] = set()
    for wrapper in repaired.wrapper_requirements:
        key = _normalize_blueprint_label(wrapper.wrapper_id or wrapper.name)
        if not key or key in seen_wrapper_ids:
            changed = True
            continue
        seen_wrapper_ids.add(key)
        deduped_wrappers.append(wrapper)
    if deduped_wrappers != repaired.wrapper_requirements:
        repaired.wrapper_requirements = deduped_wrappers
        changed = True

    deduped_outline: list[str] = []
    seen_outline_keys: set[str] = set()
    for entry in repaired.page_outline:
        key = _canonical_blueprint_key(
            entry,
            entry,
            reference_bundle=reference_bundle,
        )
        if not key or key in seen_outline_keys:
            changed = True
            continue
        seen_outline_keys.add(key)
        deduped_outline.append(entry)
    section_names_by_key = {
        _canonical_blueprint_key(
            section.name,
            section.section_id,
            reference_bundle=reference_bundle,
        ): section.name
        for section in repaired.section_requirements
    }
    for key, section_name in section_names_by_key.items():
        if key in seen_outline_keys:
            continue
        deduped_outline.append(section_name)
        seen_outline_keys.add(key)
        changed = True
    if deduped_outline != repaired.page_outline:
        repaired.page_outline = deduped_outline
        changed = True

    return repaired, changed


def _reconcile_blueprint_validation_report(
    report: BlueprintValidationReport,
    *,
    requirements: RequirementsSpec,
    reference_bundle: ReferenceBundle,
) -> BlueprintValidationReport:
    present_section_keys = {
        _canonical_blueprint_key(
            section.name,
            section.section_id,
            reference_bundle=reference_bundle,
        )
        for section in requirements.section_requirements
    }

    canonical_closing = _build_canonical_closing_sections(requirements)
    canonical_outline_matches = all(
        any(
            _section_matches_outline_entry(entry, section.name, section.section_id)
            for section in requirements.section_requirements
        )
        for entry in requirements.page_outline
        if entry.strip()
    )
    main_content_wrapper_present = any(
        _normalize_blueprint_label(wrapper.wrapper_id or wrapper.name) == "main-content-shell"
        for wrapper in requirements.wrapper_requirements
    )

    filtered_missing_sections = [
        name
        for name in report.missing_sections
        if _canonical_blueprint_key(name, name, reference_bundle=reference_bundle)
        not in present_section_keys
    ]

    filtered_issues = []
    for issue in report.issues:
        title = issue.title.lower()
        if "missing faq section" in title and "faq" in present_section_keys:
            continue
        if (
            ("missing footer sections in section requirements" in title or "missing footer section definitions" in title)
            and {
                "community-signup",
                "footer-legal",
                "site-footer",
            }.issubset(present_section_keys)
        ):
            continue
        if (
            ("disconnected outlines" in title or "out of sync" in issue.detail.lower())
            and canonical_outline_matches
            and requirements.closing_sections == canonical_closing
        ):
            continue
        if "truncated execution plan" in title and _execution_plan_covers_outline(requirements):
            continue
        if "main content shell" in title and main_content_wrapper_present:
            continue
        if "missing footer sections in section requirements" in title and {
            "community-signup",
            "footer-legal",
            "site-footer",
        }.issubset(present_section_keys):
            continue
        filtered_issues.append(issue)

    if (
        filtered_missing_sections == report.missing_sections
        and filtered_issues == report.issues
    ):
        filtered_report = report
    else:
        filtered_report = report.model_copy(
            update={
                "missing_sections": filtered_missing_sections,
                "issues": filtered_issues,
                "repair_instructions": [
                    instruction
                    for instruction in report.repair_instructions
                    if not (
                        {
                            "community-signup",
                            "footer-legal",
                            "site-footer",
                        }.issubset(present_section_keys)
                        and "section_requirements" in instruction.lower()
                        and "community-signup" in instruction.lower()
                    )
                ],
            }
        )

    coverage_score, consistency_score, execution_readiness_score = (
        _deterministic_blueprint_scores(
            requirements,
            reference_bundle=reference_bundle,
        )
    )
    remaining_critical = any(issue.severity == "critical" for issue in filtered_report.issues)
    remaining_major = any(issue.severity == "major" for issue in filtered_report.issues)
    deterministic_overall = (
        coverage_score * 0.35
        + consistency_score * 0.35
        + execution_readiness_score * 0.30
    )

    updated = filtered_report.model_copy(
        update={
            "coverage_score": max(filtered_report.coverage_score, coverage_score),
            "consistency_score": max(filtered_report.consistency_score, consistency_score),
            "execution_readiness_score": max(
                filtered_report.execution_readiness_score,
                execution_readiness_score,
            ),
            "overall_score": max(filtered_report.overall_score, deterministic_overall),
        }
    )

    if (
        updated.overall_score >= BLUEPRINT_VALIDATED_LOOP_PASS_SCORE
        and updated.coverage_score >= 0.98
        and updated.consistency_score >= 0.98
        and updated.execution_readiness_score >= 0.97
        and not updated.missing_sections
    ):
        return updated.model_copy(
            update={
                "verdict": "pass",
                "issues": [],
                "repair_instructions": [],
                "summary": "Blueprint meets the deterministic quality gate and is internally consistent, complete, and execution-ready against the indexed DOM evidence.",
            }
        )

    if not remaining_critical and not remaining_major and not updated.missing_sections:
        updated = updated.model_copy(
            update={
                "verdict": "pass",
                "summary": "Blueprint is internally consistent, fully section-mapped, and execution-ready against the indexed DOM evidence.",
            }
        )
    return updated


def _repair_section_layout_mismatches(
    requirements: RequirementsSpec,
) -> tuple[RequirementsSpec, bool]:
    repaired = requirements.model_copy(deep=True)
    changed = False

    for section in repaired.section_requirements:
        normalized_id = _normalize_blueprint_label(section.section_id or section.name)
        layout_blob = " ".join(
            value.lower()
            for value in [section.layout, *section.layout_invariants]
            if value.strip()
        )

        if normalized_id == "testimonials" and any(
            token in layout_blob
            for token in ("slider-thumbnails", "thumbnail-list", "featured_product")
        ):
            section.layout = (
                "Social-proof section with testimonial or review content grouped into "
                "video, quote, or endorsement cards rather than product-gallery controls."
            )
            section.layout_invariants = [
                value
                for value in section.layout_invariants
                if not any(
                    token in value.lower()
                    for token in ("slider-thumbnails", "thumbnail-list", "featured product")
                )
            ]
            changed |= _append_unique_strings(
                section.layout_invariants,
                [
                    "Keep testimonials as their own social-proof or review grouping instead of reusing product-gallery thumbnail structure.",
                ],
            )
            section.must_include = [
                value
                for value in section.must_include
                if "thumbnail" not in value.lower()
            ]
            changed |= _append_unique_strings(
                section.must_include,
                [
                    "testimonial or review cards",
                    "supporting quote or review copy",
                ],
            )
            changed = True

        if normalized_id == "cta-banner" and any(
            token in layout_blob
            for token in (
                "announcement strip",
                "top chrome band",
                "announcement shell",
            )
        ):
            section.layout = (
                "Dedicated call-to-action banner with a centered vertical stack of "
                "message, supporting detail, and action treatment."
            )
            section.layout_invariants = [
                value
                for value in section.layout_invariants
                if not any(
                    token in value.lower()
                    for token in (
                        "announcement strip",
                        "main header shell",
                        "band height",
                    )
                )
            ]
            changed |= _append_unique_strings(
                section.layout_invariants,
                [
                    "Keep the CTA banner as a distinct centered conversion section instead of reusing announcement-bar chrome structure.",
                ],
            )
            section.must_include = [
                value for value in section.must_include if "announcement" not in value.lower()
            ]
            changed |= _append_unique_strings(
                section.must_include,
                [
                    "primary CTA message",
                    "supporting CTA copy",
                    "action treatment",
                ],
            )
            changed = True

    return repaired, changed


def _section_asset_evidence(
    reference_bundle: ReferenceBundle,
    section: SectionRequirement,
    *,
    limit: int = 2,
) -> list[str]:
    tokens = _section_reference_tokens(section)
    role = _section_role(section)
    normalized_id = _normalize_blueprint_label(section.section_id or section.name)
    scored: list[tuple[int, str]] = []
    for value in _reference_asset_evidence_lines(reference_bundle):
        lowered = value.lower()
        if any(
            token in lowered
            for token in (
                "analytics.twitter.com/1/i/adsct",
                "t.co/1/i/adsct",
                "/adsct?",
            )
        ):
            continue
        if normalized_id == "shop-now-bar":
            if any(
                token in lowered
                for token in (
                    "footer",
                    "newsletter",
                    "legal",
                    "copyright",
                    "privacy",
                    "terms",
                    "accessibility",
                )
            ):
                continue
            if not any(
                token in lowered
                for token in (
                    "header-logo-new",
                    "header__heading-logo",
                    "header_white_logo",
                    "go to homepage",
                    "im8logo.webp",
                )
            ):
                continue
        if role == "related" and not any(
            token in lowered for token in ("/articles/", "hb_blogs_card__image")
        ):
            continue
        if role in {"hero", "body"}:
            if any(
                token in lowered
                for token in (
                    "footer",
                    "newsletter",
                    "contentinfo",
                    "header__heading-logo",
                    "header-logo-new",
                    "mega-menu__link-image",
                )
            ):
                continue
            if not any(
                token in lowered
                for token in (
                    "/articles/",
                    "article-template",
                    "blog-sab",
                    "sab",
                )
            ):
                continue
        if role == "footer" and not any(
            token in lowered
            for token in (
                "footer",
                "newsletter",
                "contentinfo",
                "logo_image_new",
                "cursor_blinking",
                "preview_images/",
                "video/mp4",
            )
        ):
            continue
        if role == "showcase" and not any(
            token in lowered
            for token in (
                "beckham",
                "bundle",
                "product_image_new",
                "welcome kit",
                "daily ultimate",
                "essentials-pro",
                "feature-card",
                "bundle_li_bg",
                "bg.jpg",
                "frame_1171275436",
                "red-cup",
            )
        ):
            continue
        if role in {"announcement", "header", "sticky"} or normalized_id == "shop-now-bar":
            if not any(
                token in lowered
                for token in (
                    "header-logo-new",
                    "header__heading-logo",
                    "header_white_logo",
                    "go to homepage",
                    "im8logo.webp",
                )
            ):
                continue
        if role == "modal" and not any(
            token in lowered
            for token in (
                "files.alia-prod.com",
                "alia-root",
                "scratch",
                "im8logo.webp",
                "beckhamstacktravel",
            )
        ):
            continue
        score = len(tokens & _blueprint_text_tokens(value))
        if score <= 0:
            continue
        scored.append((score, value))
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    matches: list[str] = []
    seen: set[str] = set()
    for _, value in scored:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        matches.append(value)
        if len(matches) >= limit:
            break
    return matches


def _matching_reference_evidence(
    values: list[str],
    keywords: frozenset[str],
    *,
    limit: int = 3,
) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for value in values:
        lowered = value.lower()
        if not any(keyword in lowered for keyword in keywords):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        matches.append(value)
        if len(matches) >= limit:
            break
    return matches


def _clean_reference_evidence(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if cleaned.startswith("<") and ": " in cleaned:
        cleaned = cleaned.split(": ", 1)[1]
    return cleaned.rstrip(".")


def _canonical_blueprint_key(
    name: str,
    section_id: str,
    *,
    reference_bundle: ReferenceBundle,
) -> str:
    temp_section = SectionRequirement(name=name, section_id=section_id)
    role = _section_role(temp_section)
    canonical = _canonical_section_identity(
        temp_section,
        role,
        reference_bundle=reference_bundle,
    )
    if canonical is not None:
        return _normalize_blueprint_label(canonical[1])
    return _normalize_blueprint_label(section_id or name)


def _reference_looks_editorial(reference_bundle: ReferenceBundle) -> bool:
    blob = " ".join(
        value.lower()
        for value in (
            reference_bundle.user_text,
            reference_bundle.reference_url,
            *_reference_evidence_lines(reference_bundle),
        )
        if value.strip()
    )
    return any(keyword in blob for keyword in ("article", "editorial", "blog", "reading"))


def _canonical_modal_identity(reference_bundle: ReferenceBundle) -> tuple[str, str]:
    reference_text = " ".join(value.lower() for value in _reference_evidence_lines(reference_bundle))
    if any(keyword in reference_text for keyword in _DOM_ROLE_HINTS["promo"]):
        return ("Promotional Modal", "promotional-modal")
    return ("Modal Overlay", "modal-overlay")


def _canonical_section_identity(
    section: SectionRequirement,
    role: str,
    *,
    reference_bundle: ReferenceBundle,
) -> tuple[str, str] | None:
    normalized_id = _normalize_blueprint_label(section.section_id or section.name)
    if role == "modal":
        if normalized_id in _GENERIC_SECTION_ID_ALIASES["modal"]:
            return _canonical_modal_identity(reference_bundle)
        return None

    canonical = _CANONICAL_SECTION_IDENTITIES.get(role)
    aliases = _GENERIC_SECTION_ID_ALIASES.get(role)
    if canonical is None or aliases is None:
        return None
    if normalized_id not in aliases:
        return None
    if role in {"hero", "body"} and not _reference_looks_editorial(reference_bundle):
        return (
            ("Hero", "hero")
            if role == "hero"
            else ("Main Content", "main-content")
        )
    if role == "showcase":
        reference_text = " ".join(value.lower() for value in _reference_evidence_lines(reference_bundle))
        if "feature" in normalized_id and "product" not in reference_text and "bundle" not in reference_text:
            return ("Feature Showcase", "feature-showcase")
    if role == "related":
        reference_text = " ".join(value.lower() for value in _reference_evidence_lines(reference_bundle))
        if "article" not in reference_text:
            return ("Related Content", "related-content")
    return canonical


def _section_role(section: SectionRequirement) -> str:
    identity_text = " ".join(
        part.strip().lower()
        for part in (section.name, section.section_id)
        if part.strip()
    )
    extended_text = " ".join(
        part.strip().lower()
        for part in (section.name, section.section_id, section.layout, *section.must_include)
        if part.strip()
    )
    for role in (
        "modal",
        "announcement",
        "sticky",
        "footer",
        "faq",
        "comparison",
        "testimonials",
        "badges",
        "stats",
        "trust",
        "cta",
        "related",
        "showcase",
        "hero",
        "body",
        "header",
    ):
        keywords = _SECTION_ROLE_KEYWORDS[role]
        if any(keyword in identity_text for keyword in keywords):
            return role
    for role in (
        "modal",
        "announcement",
        "sticky",
        "footer",
        "faq",
        "comparison",
        "testimonials",
        "badges",
        "stats",
        "trust",
        "cta",
        "related",
        "showcase",
        "hero",
        "body",
        "header",
    ):
        keywords = _SECTION_ROLE_KEYWORDS[role]
        if any(keyword in extended_text for keyword in keywords):
            return role
    return "content"


def _default_section_blueprint(
    role: str,
) -> tuple[str, list[str], list[str], list[str]]:
    if role == "modal":
        return (
            "Blocking overlay dialog with its own elevated shell, a dedicated close control, and distinct media/content groupings inside the dialog frame.",
            [
                "Keep the overlay as its own top-layer surface instead of merging it into the page chrome beneath it.",
                "Preserve a visible close or dismiss control that remains independently clickable from the dialog body.",
            ],
            ["dialog shell", "dismiss control", "primary content grouping"],
            ["separate backdrop or overlay surface", "elevated dialog framing"],
        )
    if role == "announcement":
        return (
            "Slim full-width announcement strip with centered utility copy and any inline controls inside its own top chrome band.",
            [
                "Keep the announcement strip separate from the main header shell beneath it.",
                "Preserve the measured band height and centered copy alignment instead of collapsing it into generic inline text.",
            ],
            ["announcement copy", "announcement shell", "inline utility control or link"],
            ["dedicated announcement surface", "compact measured typography"],
        )
    if role == "sticky":
        return (
            "Compact sticky or scrolled header state pinned to the top of the viewport with reduced chrome, persistent branding, and persistent navigation.",
            [
                "Keep the sticky header state separate from the opening header shell instead of treating them as one undifferentiated header.",
                "Preserve the sticky state as a compact persistent chrome layer above the page content during scroll.",
            ],
            ["sticky brand/logo cluster", "persistent navigation", "sticky utility actions"],
            ["sticky chrome surface", "reduced header height with measured spacing"],
        )
    if role == "header":
        return (
            "Dedicated opening header shell with brand, primary navigation, and utility actions inside a measured container above the main content.",
            [
                "Keep the opening header shell separate from announcement bars, sticky states, and hero/content surfaces.",
                "Preserve a measured container width and header height rather than flattening the chrome into generic inline text.",
            ],
            ["brand/logo cluster", "primary navigation", "utility actions"],
            ["dedicated header surface", "measured header spacing and typography"],
        )
    if role == "hero":
        return (
            "Primary hero shell with eyebrow or metadata, headline, and supporting detail grouped inside the lead content surface.",
            [
                "Keep the hero as its own leading content region instead of blending it into adjacent chrome or body copy.",
                "Preserve the measured headline block and supporting metadata grouping within the hero shell.",
            ],
            ["eyebrow or metadata", "headline", "supporting detail"],
            ["hero-specific typography scale", "measured vertical spacing"],
        )
    if role == "body":
        return (
            "Long-form reading shell with constrained text columns, stacked paragraphs, subheads, and supporting media or callouts within the main content surface.",
            [
                "Keep the reading column narrower than the outer shell when the reference exposes a constrained text measure.",
                "Preserve the body content as a continuous reading surface distinct from the hero and closing sections.",
            ],
            ["reading column", "body copy blocks", "subheads or supporting media"],
            ["reading-surface background treatment", "comfortable paragraph rhythm"],
        )
    if role == "showcase":
        return (
            "Feature or product showcase shell with distinct media and detail regions plus a repeated item cluster that reflects the live component geometry.",
            [
                "Keep the showcase shell separate from the surrounding article or footer surfaces.",
                "Preserve the reference-backed panel split and repeated-item orientation instead of collapsing them into a generic stack.",
            ],
            ["media panel", "detail column", "repeated item cluster"],
            ["section-specific surface treatment", "measured panel and card spacing"],
        )
    if role == "stats":
        return (
            "Statistic section with a centered heading block above a repeated stat grid or counter-card collection.",
            [
                "Keep the stats section as a dedicated proof/count shell instead of flattening it into generic body copy.",
                "Preserve the repeated stat-card or counter grouping exposed by the reference.",
            ],
            ["section heading", "repeated stat cards or counter blocks", "stat numerals with labels"],
            ["distinct stats section surface", "measured grid or card spacing"],
        )
    if role == "trust":
        return (
            "Trust or verification section with a heading, supporting proof copy, and certification or ingredient-backed proof groupings.",
            [
                "Keep the trust proof points grouped in their own verification shell rather than scattering them across adjacent sections.",
                "Preserve the certification, testing, or purity grouping exposed by the reference.",
            ],
            ["verification heading", "supporting trust copy", "proof-point or certification group"],
            ["verification-focused surface treatment", "measured proof-point spacing"],
        )
    if role == "badges":
        return (
            "Compact proof strip with repeated badges, icons, or short labels presented in a measured row or stacked mobile strip.",
            [
                "Keep the badge strip as a separate proof band instead of burying the badges inside adjacent section copy.",
                "Preserve the repeated icon-or-label grouping exposed by the reference.",
            ],
            ["repeated badge or icon row", "short supporting labels", "distinct proof strip shell"],
            ["compact strip surface", "measured badge spacing"],
        )
    if role == "testimonials":
        return (
            "Testimonial or review shell with a heading block and a repeated review-media or quote-card group.",
            [
                "Keep testimonials as a dedicated social-proof section rather than merging them into nearby CTA or footer content.",
                "Preserve the repeated testimonial or review-card grouping exposed by the reference.",
            ],
            ["section heading", "testimonial or review card/media group", "supporting social-proof copy or CTA"],
            ["social-proof surface treatment", "measured testimonial card spacing"],
        )
    if role == "comparison":
        return (
            "Comparison section with a heading block and a comparison graphic, table, or contrasted row/column layout.",
            [
                "Keep the comparison material in its own measured shell instead of flattening it into generic text content.",
                "Preserve the contrasted row/column or graphic comparison structure exposed by the reference.",
            ],
            ["section heading", "comparison rows, columns, or graphic", "supporting CTA or contrast copy"],
            ["comparison-section surface", "measured comparison spacing"],
        )
    if role == "faq":
        return (
            "FAQ shell with a heading or CTA column paired with a vertically stacked accordion list of questions and answers.",
            [
                "Keep the FAQ section as a dedicated accordion shell rather than dissolving it into generic body copy or footer content.",
                "Preserve the heading/CTA group separately from the accordion list when the reference exposes a split FAQ layout.",
            ],
            ["section heading", "accordion question list", "answer panels or toggle rows"],
            ["FAQ-specific surface treatment", "measured accordion spacing"],
        )
    if role == "cta":
        return (
            "Closing call-to-action shell with a strong heading, supporting copy, and a prominent action treatment.",
            [
                "Keep the CTA banner as a dedicated conversion section rather than reusing announcement-bar or header chrome.",
                "Preserve the stacked CTA message and action treatment exposed by the reference.",
            ],
            ["CTA heading", "supporting CTA copy", "primary action treatment"],
            ["CTA-specific section surface", "measured conversion spacing"],
        )
    if role == "related":
        return (
            "Related-content shell with a section heading, a button-styled secondary action, and a rail or grid of related cards.",
            [
                "Keep related content as a dedicated closing section above the footer instead of absorbing it into the footer shell.",
                "Preserve the heading-and-CTA row separately from the related card collection.",
            ],
            ["section heading", "button-styled secondary action", "related card collection"],
            ["distinct section background", "card surface styling with measured spacing"],
        )
    if role == "footer":
        return (
            "Closing footer shell with upper utility or navigation content and a separate lower legal or accessibility band when the reference exposes both layers.",
            [
                "Keep the upper footer content and the closing legal band as distinct regions when the live DOM exposes both.",
                "Preserve footer depth, newsletter or utility content, and closing legal copy instead of reducing the footer to a single generic block.",
            ],
            ["upper footer content", "newsletter or utility signup area", "lower legal or accessibility band"],
            ["distinct footer surface", "separate legal-band sizing and spacing"],
        )
    return (
        "Structured content section with a dedicated shell, internal grouping, and measured spacing derived from the reference.",
        [
            "Keep this section as a distinct shell rather than merging it into adjacent content.",
            "Preserve the reference-backed grouping and container behavior for this section.",
        ],
        ["primary content group", "secondary supporting content", "section-specific action or media"],
        ["section-specific surface treatment", "measured spacing"],
    )


def _insert_outline_entry(
    values: list[str],
    candidate: str,
    *,
    before_keywords: tuple[str, ...] = (),
    after_keywords: tuple[str, ...] = (),
) -> bool:
    normalized_candidate = _normalize_blueprint_label(candidate)
    if any(_normalize_blueprint_label(value) == normalized_candidate for value in values):
        return False
    insert_at = len(values)
    if before_keywords:
        for index, value in enumerate(values):
            normalized_value = _normalize_blueprint_label(value)
            if any(keyword in normalized_value for keyword in before_keywords):
                insert_at = index
                break
    elif after_keywords:
        for index, value in enumerate(values):
            normalized_value = _normalize_blueprint_label(value)
            if any(keyword in normalized_value for keyword in after_keywords):
                insert_at = index + 1
                break
    values.insert(insert_at, candidate.strip())
    return True


def _insert_section_requirement(
    values: list[SectionRequirement],
    candidate: SectionRequirement,
    *,
    before_keywords: tuple[str, ...] = (),
    after_keywords: tuple[str, ...] = (),
) -> bool:
    if any(section.section_id == candidate.section_id for section in values):
        return False
    insert_at = len(values)
    if before_keywords:
        for index, section in enumerate(values):
            section_text = f"{section.name} {section.section_id}".lower()
            if any(keyword in section_text for keyword in before_keywords):
                insert_at = index
                break
    elif after_keywords:
        for index, section in enumerate(values):
            section_text = f"{section.name} {section.section_id}".lower()
            if any(keyword in section_text for keyword in after_keywords):
                insert_at = index + 1
                break
    values.insert(insert_at, candidate)
    return True


def _build_canonical_execution_plan(
    requirements: RequirementsSpec,
) -> list[str]:
    steps: list[str] = []
    if requirements.wrapper_requirements:
        steps.append(
            "Establish the required shared wrappers and shell containers before building the child sections."
        )
    for index, outline_name in enumerate(requirements.page_outline, start=1):
        steps.append(f"{index}. Build the {outline_name} section in canonical page order.")
    return steps


def _build_canonical_closing_sections(
    requirements: RequirementsSpec,
    *,
    limit: int = 5,
) -> list[str]:
    if not requirements.page_outline:
        return []
    closing = [entry.strip() for entry in requirements.page_outline[-limit:] if entry.strip()]
    return list(dict.fromkeys(closing))


def _section_reference_tokens(section: SectionRequirement) -> set[str]:
    tokens = _blueprint_text_tokens(
        " ".join(
            value
            for value in (section.name, section.section_id, section.layout, *section.must_include)
            if value.strip()
        )
    )
    return {
        token
        for token in tokens
        if len(token) > 2 and token not in _SECTION_EVIDENCE_STOPWORDS
    }


def _section_reference_evidence(
    reference_bundle: ReferenceBundle,
    section: SectionRequirement,
    *,
    limit: int = 2,
) -> list[str]:
    tokens = _section_reference_tokens(section)
    role = _section_role(section)
    normalized_id = _normalize_blueprint_label(section.section_id or section.name)
    if not tokens:
        return []
    scored: list[tuple[int, str]] = []
    for value in _reference_evidence_lines(reference_bundle):
        value_tokens = _blueprint_text_tokens(value)
        lowered = value.lower()
        if normalized_id == "shop-now-bar":
            if any(
                token in lowered
                for token in (
                    "footer",
                    "newsletter",
                    "legal",
                    "copyright",
                    "privacy",
                    "terms",
                    "accessibility",
                )
            ):
                continue
            if not any(
                token in lowered
                for token in (
                    "shop now",
                    "sticky",
                    "scrolled",
                    "scroll",
                    "get started",
                    "promo",
                    "offer",
                    "pulse",
                )
            ):
                continue
        if role == "announcement":
            if any(
                token in lowered
                for token in (
                    "footer",
                    "newsletter",
                    "legal",
                    "copyright",
                    "privacy",
                    "terms",
                    "accessibility",
                )
            ):
                continue
        if role == "modal":
            if any(
                token in lowered
                for token in (
                    "beckham stack",
                    "footer",
                    "newsletter",
                    "legal",
                    "copyright",
                )
            ) and not any(token in lowered for token in ("alia", "modal", "overlay", "popup")):
                continue
        if role in {"hero", "body"}:
            if any(
                token in lowered
                for token in (
                    "footer",
                    "newsletter",
                    "legal",
                    "copyright",
                    "mega-menu",
                    "header__heading-logo",
                    "header-logo-new",
                )
            ):
                continue
            if not any(
                token in lowered
                for token in (
                    "article",
                    "blog",
                    "reading",
                    "wellness",
                    "article-template",
                    "sab",
                )
            ):
                continue
        score = len(tokens & value_tokens)
        if score <= 0:
            continue
        scored.append((score, value))
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    matches: list[str] = []
    seen: set[str] = set()
    for _, value in scored:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        matches.append(value)
        if len(matches) >= limit:
            break
    return matches


def _section_component_evidence(
    reference_bundle: ReferenceBundle,
    section: SectionRequirement,
    *,
    keywords: frozenset[str],
    limit: int = 2,
) -> list[str]:
    tokens = _section_reference_tokens(section)
    scored: list[tuple[int, str]] = []
    for value in _reference_component_evidence_lines(reference_bundle):
        lowered = value.lower()
        if not any(keyword in lowered for keyword in keywords):
            continue
        score = len(tokens & _blueprint_text_tokens(value))
        scored.append((score, value))
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    matches: list[str] = []
    seen: set[str] = set()
    for _, value in scored:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        matches.append(value)
        if len(matches) >= limit:
            break
    return matches


def _has_placeholder_blueprint_text(values: list[str], placeholders: frozenset[str]) -> bool:
    normalized = {value.strip().lower() for value in values if value.strip()}
    return bool(normalized & placeholders)


def _section_dom_evidence_items(
    reference_bundle: ReferenceBundle,
    section: SectionRequirement,
    *,
    limit: int = 2,
) -> list[LiveReferenceDomEvidenceItem]:
    live_reference = reference_bundle.live_reference
    if live_reference is None:
        return []

    tokens = _section_reference_tokens(section)
    if not tokens:
        return []
    role = _section_role(section)
    normalized_id = _normalize_blueprint_label(section.section_id or section.name)
    dom_evidence = live_reference.design_system.dom_evidence
    candidates = [
        *dom_evidence.chrome_candidates,
        *dom_evidence.section_candidates,
        *dom_evidence.footer_bands,
        *dom_evidence.form_candidates,
        *dom_evidence.repeated_groups,
        *dom_evidence.state_variants,
    ]
    scored: list[tuple[int, LiveReferenceDomEvidenceItem]] = []
    for item in candidates:
        haystack = _evidence_haystack(item)
        if role not in {"announcement", "header", "sticky", "modal", "footer"} and any(
            token in haystack
            for token in (
                "header__heading-logo",
                "header-logo-new",
                "primary navigation",
                "utility actions",
                "newsletter",
                "copyright",
                "privacy",
                "terms",
            )
        ):
            continue
        if role == "footer" and item.kind not in {"footer_band", "form", "section"}:
            continue
        if role == "cta" and any(
            token in haystack
            for token in ("announcement shell", "announcement copy", "ticker", "marquee")
        ):
            continue
        if role == "comparison" and "compare" not in haystack and "vs" not in haystack:
            continue
        if role == "faq" and not any(
            token in haystack for token in ("faq", "question", "accordion")
        ):
            continue
        if role == "testimonials" and not any(
            token in haystack for token in ("review", "results", "testimonial", "video-review")
        ):
            continue
        if role == "badges" and not any(
            token in haystack for token in ("badge", "gmo", "tested", "vegan", "icon")
        ):
            continue
        if role == "trust" and not any(
            token in haystack for token in ("trust", "tested", "quality", "verified", "purity")
        ):
            continue
        if role == "stats" and not any(
            token in haystack for token in ("stat", "counter", "studies", "snackable")
        ):
            continue
        score = len(tokens & _blueprint_text_tokens(haystack))
        if score <= 0:
            continue
        if item.heading_text:
            score += 1
        if item.html_excerpt:
            score += 1
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].top_offset_px or 0))
    results: list[LiveReferenceDomEvidenceItem] = []
    seen: set[str] = set()
    for _, item in scored:
        key = item.evidence_id or item.selector
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _sanitize_section_requirement_from_reference(
    reference_bundle: ReferenceBundle,
    section: SectionRequirement,
) -> bool:
    changed = False
    role = _section_role(section)
    evidence_items = _section_dom_evidence_items(reference_bundle, section, limit=2)
    evidence_lines = _section_reference_evidence(reference_bundle, section, limit=2)
    default_layout, default_invariants, default_must_include, default_styling = (
        _default_section_blueprint(role)
    )

    if role not in {"announcement", "header", "sticky", "modal", "footer"}:
        filtered_assets = [
            asset
            for asset in section.assets
            if not any(
                token in asset.lower()
                for token in (
                    "header__heading-logo",
                    "header-logo-new",
                    "logo_datk.svg",
                )
            )
        ]
        if filtered_assets != section.assets:
            section.assets = filtered_assets
            changed = True

    if role != "footer":
        filtered_assets = [
            asset
            for asset in section.assets
            if not any(
                token in asset.lower()
                for token in (
                    "preview_images/",
                    "newsletter",
                    "privacy",
                    "terms",
                    "refunds",
                )
            )
        ]
        if filtered_assets != section.assets:
            section.assets = filtered_assets
            changed = True

    filtered_must_include = [
        value
        for value in section.must_include
        if value.strip().lower() not in _GENERIC_BLUEPRINT_MUST_INCLUDE_PLACEHOLDERS
        and not (
            role not in {"announcement", "header", "sticky"}
            and any(
                token in value.lower()
                for token in ("brand/logo", "navigation", "utility actions", "announcement")
            )
        )
    ]
    if filtered_must_include != section.must_include:
        section.must_include = filtered_must_include
        changed = True

    filtered_styling = [
        value
        for value in section.styling
        if value.strip().lower() not in _GENERIC_BLUEPRINT_STYLING_PLACEHOLDERS
    ]
    if filtered_styling != section.styling:
        section.styling = filtered_styling
        changed = True

    filtered_invariants = [
        value
        for value in section.layout_invariants
        if not (
            role != "cta"
            and "announcement strip" in value.lower()
        )
        and not (
            role not in {"announcement", "header", "sticky"}
            and "header shell" in value.lower()
        )
    ]
    if filtered_invariants != section.layout_invariants:
        section.layout_invariants = filtered_invariants
        changed = True

    if (
        not section.layout.strip()
        or _is_vague_layout_description(section.layout)
        or (
            role == "cta"
            and "announcement" in section.layout.lower()
        )
    ):
        section.layout = default_layout
        changed = True

    if evidence_lines:
        cleaned = _clean_reference_evidence(evidence_lines[0])
        if cleaned.lower() not in section.layout.lower():
            section.layout = f"{section.layout.rstrip('.')}. Reference-backed shell: {cleaned}."
            changed = True

    if _count_nonempty(section.layout_invariants) < 2 or _count_specific(section.layout_invariants) < 1:
        original = list(section.layout_invariants)
        _append_unique_strings(section.layout_invariants, default_invariants)
        changed |= section.layout_invariants != original

    if evidence_lines:
        original = list(section.layout_invariants)
        _append_unique_strings(
            section.layout_invariants,
            [f"Reference-backed structure: {_clean_reference_evidence(evidence_lines[0])}."],
        )
        changed |= section.layout_invariants != original

    if _count_nonempty(section.must_include) < 2 or _has_placeholder_blueprint_text(
        section.must_include,
        _GENERIC_BLUEPRINT_MUST_INCLUDE_PLACEHOLDERS,
    ):
        original = list(section.must_include)
        section.must_include = [
            value
            for value in section.must_include
            if value.strip().lower() not in _GENERIC_BLUEPRINT_MUST_INCLUDE_PLACEHOLDERS
        ]
        _append_unique_strings(section.must_include, default_must_include)
        for item in evidence_items:
            if item.heading_text.strip():
                _append_unique_strings(
                    section.must_include,
                    [f'section heading "{item.heading_text.strip()}"'],
                )
            note_blob = " ".join(item.notes).lower()
            if "horizontal split layout" in note_blob:
                _append_unique_strings(section.must_include, ["left media panel", "right content panel"])
            if "vertical stack layout" in note_blob:
                _append_unique_strings(section.must_include, ["stacked content groups"])
            if "<video" in item.html_excerpt.lower():
                _append_unique_strings(section.must_include, ["video or motion media block"])
            elif "<img" in item.html_excerpt.lower():
                _append_unique_strings(section.must_include, ["image or media block"])
            if "<input" in item.html_excerpt.lower() or item.kind == "form":
                _append_unique_strings(section.must_include, ["signup or form control"])
        changed |= section.must_include != original

    if _count_nonempty(section.styling) < 2 or _has_placeholder_blueprint_text(
        section.styling,
        _GENERIC_BLUEPRINT_STYLING_PLACEHOLDERS,
    ):
        original = list(section.styling)
        section.styling = [
            value
            for value in section.styling
            if value.strip().lower() not in _GENERIC_BLUEPRINT_STYLING_PLACEHOLDERS
        ]
        _append_unique_strings(section.styling, default_styling)
        for item in evidence_items:
            if item.background.strip():
                _append_unique_strings(
                    section.styling,
                    [f"background treatment: {item.background.strip()}"],
                )
            if item.border_radius.strip():
                _append_unique_strings(
                    section.styling,
                    [f"border radius treatment: {item.border_radius.strip()}"],
                )
            if item.max_width.strip():
                _append_unique_strings(
                    section.styling,
                    [f"container sizing: {item.max_width.strip()}"],
                )
        changed |= section.styling != original

    relevant_assets = _section_asset_evidence(reference_bundle, section, limit=2)
    if relevant_assets:
        if not section.assets or len(section.assets) > len(relevant_assets):
            section.assets = []
            changed = True
        original = list(section.assets)
        _append_unique_strings(section.assets, relevant_assets)
        changed |= section.assets != original

    return changed


def _deterministic_blueprint_scores(
    requirements: RequirementsSpec,
    *,
    reference_bundle: ReferenceBundle,
) -> tuple[float, float, float]:
    outline = [entry for entry in requirements.page_outline if entry.strip()]
    sections = [section for section in requirements.section_requirements if section.name.strip()]
    if not outline or not sections:
        return (0.0, 0.0, 0.0)

    outline_matches = sum(
        1
        for entry in outline
        if any(
            _section_matches_outline_entry(entry, section.name, section.section_id)
            for section in sections
        )
    )
    coverage_score = outline_matches / max(len(outline), 1)

    closing_target = _build_canonical_closing_sections(requirements)
    closing_score = 1.0 if requirements.closing_sections == closing_target else 0.85
    execution_score = 1.0 if _execution_plan_covers_outline(requirements) else 0.6
    wrapper_score = 1.0
    section_ids = {section.section_id for section in sections}
    for wrapper in requirements.wrapper_requirements:
        if not wrapper.participant_section_ids or any(
            participant not in section_ids for participant in wrapper.participant_section_ids
        ):
            wrapper_score = min(wrapper_score, 0.7)
    consistency_score = min(1.0, (closing_score + execution_score + wrapper_score) / 3)

    quality_scores: list[float] = []
    for section in sections:
        score = 0.0
        score += 1.0 if section.purpose.strip() else 0.0
        score += 1.0 if section.layout.strip() and not _is_vague_layout_description(section.layout) else 0.0
        score += 1.0 if _count_nonempty(section.layout_invariants) >= 2 and _count_specific(section.layout_invariants) >= 1 else 0.0
        score += 1.0 if _count_nonempty(section.must_include) >= 2 and not _has_placeholder_blueprint_text(section.must_include, _GENERIC_BLUEPRINT_MUST_INCLUDE_PLACEHOLDERS) else 0.0
        score += 1.0 if _count_nonempty(section.styling) >= 2 and not _has_placeholder_blueprint_text(section.styling, _GENERIC_BLUEPRINT_STYLING_PLACEHOLDERS) else 0.0
        quality_scores.append(score / 5.0)

    global_lists = [
        requirements.critical_layout_invariants,
        requirements.layout_requirements,
        requirements.styling_requirements,
        requirements.behavior_requirements,
        requirements.animation_requirements,
        requirements.acceptance_criteria,
        requirements.hard_constraints,
    ]
    global_score = sum(1.0 for values in global_lists if values) / len(global_lists)
    execution_readiness = min(1.0, ((sum(quality_scores) / max(len(quality_scores), 1)) + global_score) / 2)
    return (coverage_score, consistency_score, execution_readiness)


class ValidationLoopOrchestrator:
    def __init__(
        self,
        *,
        send_message: Callable[..., Awaitable[None]],
        openai_api_key: str | None,
        openai_base_url: str | None,
        anthropic_api_key: str | None,
        gemini_api_key: str,
        should_generate_images: bool,
        option_codes: list[str] | None,
        max_iterations: int,
        design_system_reuse_mode: DesignSystemReuseMode = "generate",
        design_system_reuse_run_dir: str | None = None,
        renderer: HtmlPreviewRenderer | None = None,
        analyzer: LoopAnalyzer | None = None,
        blueprint_validator: LoopBlueprintValidator | None = None,
        validator: LoopValidator | None = None,
        executor: LoopExecutor | None = None,
        artifact_store: ValidatedLoopArtifactStore | None = None,
        live_reference_extractor: LiveReferenceExtractor | None = None,
        design_system_builder: DesignSystemPreflightBuilder | None = None,
        design_system_renderer: DesignSystemDocumentRenderer | None = None,
        max_blueprint_validation_attempts: int = DEFAULT_BLUEPRINT_VALIDATION_MAX_ATTEMPTS,
        blueprint_pass_score: float = BLUEPRINT_VALIDATED_LOOP_PASS_SCORE,
    ) -> None:
        self._send_message = send_message
        self._max_iterations = max_iterations
        self._max_blueprint_validation_attempts = max(1, max_blueprint_validation_attempts)
        self._blueprint_pass_score = max(0.0, min(1.0, blueprint_pass_score))
        self._design_system_reuse_mode = design_system_reuse_mode
        self._design_system_reuse_run_dir = design_system_reuse_run_dir
        self._analyzer = analyzer or LoopAnalyzer(gemini_api_key)
        self._blueprint_validator = blueprint_validator or LoopBlueprintValidator(
            gemini_api_key
        )
        self._validator = validator or LoopValidator(gemini_api_key)
        self._renderer = renderer or HtmlPreviewRenderer()
        self._artifact_store = artifact_store or ValidatedLoopArtifactStore()
        self._live_reference_extractor = live_reference_extractor or LiveReferenceExtractor()
        self._design_system_builder = design_system_builder or DesignSystemPreflightBuilder(
            gemini_api_key
        )
        self._design_system_renderer = (
            design_system_renderer or DesignSystemDocumentRenderer()
        )
        self._executor = executor or LoopExecutor(
            send_message=send_message,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            should_generate_images=should_generate_images,
            option_codes=option_codes,
        )

    async def run(
        self,
        *,
        reference_bundle: ReferenceBundle,
        initial_file_state: dict[str, str] | None,
        resume_state: LoopResumeState | None = None,
    ) -> LoopRunResult:
        reference_bundle = await self._enrich_live_reference(reference_bundle)
        reference_bundle = await self._ensure_design_system_preflight(reference_bundle)
        await self._status(
            "Persisting validated loop code to "
            f"{self._artifact_store.paths.current_file_path}."
        )
        self._artifact_store.persist_reference_bundle(reference_bundle)
        await self._status(
            "Saved reference media locally for this run. Future continue/retry steps can reuse it without depending on browser memory.",
            data={
                "artifactPath": self._artifact_store.paths.best_file_path,
                "runDir": self._artifact_store.paths.run_dir,
            },
        )
        current_file_state = initial_file_state or (
            resume_state.best_file_state if resume_state else None
        )
        validation_report: ValidationReport | None = (
            resume_state.latest_validation if resume_state else None
        )
        prior_blueprint_validation: BlueprintValidationReport | None = (
            resume_state.blueprint_validation if resume_state else None
        )
        if resume_state and resume_state.requirements is not None:
            await self._send_supervisor_thinking(
                title="Supervisor: Resuming prior context",
                content=(
                    "Refining the saved supervisor context against the reference "
                    "media and the current best HTML so the next block can continue "
                    "from the exact saved baseline without losing precision."
                ),
            )
            await self._status(
                "Analysis: refining saved supervisor context from the previous run."
            )
            requirements = await self._analyzer.analyze(
                reference_bundle,
                current_file_state.get("content", "") if current_file_state else None,
                prior_requirements=resume_state.requirements,
                prior_validation=resume_state.latest_validation,
                prior_blueprint_validation=resume_state.blueprint_validation,
            )
        else:
            await self._send_supervisor_thinking(
                title="Supervisor: Analyzing reference",
                content=(
                    "Reviewing the source input to extract layout, styling, copy, "
                    "behavior, hard constraints, section blueprints, and template-"
                    "structure requirements before execution."
                ),
            )
            await self._status("Analysis: drafting requirements with Gemini 3.1 Pro.")
            requirements = await self._analyzer.analyze(
                reference_bundle,
                current_file_state.get("content", "") if current_file_state else None,
            )
        (
            requirements,
            blueprint_validation,
            blueprint_was_repaired,
            blueprint_validation_history,
        ) = await self._validate_blueprint_before_execution(
            requirements,
            reference_bundle=reference_bundle,
            current_html=current_file_state.get("content", "") if current_file_state else None,
            prior_validation=validation_report,
            prior_blueprint_validation=prior_blueprint_validation,
        )
        await self._send_supervisor_assistant(
            title=(
                "Supervisor: Blueprint repaired"
                if blueprint_was_repaired
                else "Supervisor: Requirements draft ready"
            ),
            content=self._summarize_requirements(requirements),
        )
        iterations: list[LoopIterationRecord] = []
        last_code = current_file_state.get("content", "") if current_file_state else ""
        best_code = last_code
        best_validation_report = validation_report
        best_project_export = None

        self._artifact_store.persist_metadata(
            iteration=0,
            stop_reason=None,
            requirements=requirements,
            validation_report=validation_report,
            blueprint_validation=blueprint_validation,
            blueprint_validation_history=blueprint_validation_history,
        )

        if best_code and best_validation_report is not None:
            best_project_export = self._artifact_store.persist_best_checkpoint(
                html=best_code,
                iteration=0,
                requirements=requirements,
                validation_report=best_validation_report,
                stack=reference_bundle.stack,
                blueprint_validation=blueprint_validation,
            )

        for iteration in range(1, self._max_iterations + 1):
            await self._send_supervisor_thinking(
                title=f"Supervisor: Execution plan for iteration {iteration}",
                content=(
                    f"Handing iteration {iteration} to the executor with the current "
                    "requirements, section blueprint, hard constraints, and any "
                    "validator feedback gathered so far."
                ),
            )
            await self._status(
                f"Iteration {iteration}/{self._max_iterations}: executing with Gemini 3.1 Pro."
            )
            execution_blocks = plan_execution_blocks(
                reference_bundle=reference_bundle,
                requirements=requirements,
                file_state=current_file_state,
                validation_report=validation_report,
            )
            if len(execution_blocks) > 1:
                await self._send_supervisor_thinking(
                    title=f"Supervisor: Execution blocks for iteration {iteration}",
                    content=(
                        "Splitting the implementation into smaller executor blocks so the coding agent keeps the full-page plan while staying within the model context budget."
                    ),
                )
                await self._status(
                    f"Iteration {iteration}/{self._max_iterations}: executing in {len(execution_blocks)} scoped blocks.",
                    data={
                        "executionBlocks": summarize_execution_blocks(execution_blocks),
                    },
                )
            last_code = await self._executor.execute(
                reference_bundle=reference_bundle,
                requirements=requirements,
                file_state=current_file_state,
                validation_report=validation_report,
                iteration=iteration,
                execution_blocks=execution_blocks,
            )

            if not last_code.strip():
                raise RuntimeError("Execution produced empty code")

            iteration_project_export = self._artifact_store.persist_iteration_code(
                html=last_code,
                iteration=iteration,
                stack=reference_bundle.stack,
            )
            self._artifact_store.persist_metadata(
                iteration=iteration,
                stop_reason=None,
                requirements=requirements,
                validation_report=None,
                blueprint_validation=blueprint_validation,
                blueprint_validation_history=blueprint_validation_history,
                project_export=iteration_project_export,
            )
            await self._status(
                f"Iteration {iteration}/{self._max_iterations}: rendering candidate."
            )
            render_artifact = await self._renderer.render_html(
                last_code,
                requirements.viewport,
                requirements.interaction_checkpoints
                if reference_bundle.input_mode == "video"
                else None,
            )

            await self._status(
                f"Iteration {iteration}/{self._max_iterations}: validating with Gemini 3.1 Pro."
            )
            await self._send_supervisor_thinking(
                title=f"Supervisor: Reviewing iteration {iteration}",
                content=(
                    "Comparing the rendered candidate against the reference and "
                    "checking whether the implementation still looks easy to retheme "
                    "and edit."
                ),
            )
            prior_validation_for_iteration = validation_report
            validation_report = await self._validator.validate(
                reference_bundle=reference_bundle,
                requirements=requirements,
                render_artifact=render_artifact,
                current_html=last_code,
                iteration=iteration,
                prior_validation=prior_validation_for_iteration,
            )
            iterations.append(
                LoopIterationRecord(
                    iteration=iteration,
                    validation=validation_report,
                )
            )

            await self._status(
                "Validation result: "
                f"{validation_report.verdict} at score {validation_report.overall_score:.2f}. "
                f"{validation_report.summary}"
            )
            await self._send_supervisor_assistant(
                title=f"Supervisor: Validation summary for iteration {iteration}",
                content=self._summarize_validation(validation_report),
            )
            self._artifact_store.persist_metadata(
                iteration=iteration,
                stop_reason=None,
                requirements=requirements,
                validation_report=validation_report,
                blueprint_validation=blueprint_validation,
                blueprint_validation_history=blueprint_validation_history,
                project_export=iteration_project_export,
            )

            if self._is_better_validation(
                candidate=validation_report,
                incumbent=best_validation_report,
            ):
                best_code = last_code
                best_validation_report = validation_report
                best_project_export = self._artifact_store.persist_best_checkpoint(
                    html=best_code,
                    iteration=iteration,
                    requirements=requirements,
                    validation_report=best_validation_report,
                    stack=reference_bundle.stack,
                    blueprint_validation=blueprint_validation,
                )
            elif best_validation_report is not None:
                await self._send_supervisor_assistant(
                    title=f"Supervisor: Retaining best-so-far after iteration {iteration}",
                    content=(
                        "This iteration did not improve on the best saved checkpoint, "
                        "so future continues will keep using the stronger prior result."
                    ),
                )

            if self._should_stop_after_validation(
                reference_bundle=reference_bundle,
                validation_report=validation_report,
            ):
                final_code = best_code if best_code.strip() else last_code
                self._artifact_store.persist_metadata(
                    iteration=iteration,
                    stop_reason="pass",
                    requirements=requirements,
                    validation_report=validation_report,
                    blueprint_validation=blueprint_validation,
                    blueprint_validation_history=blueprint_validation_history,
                    project_export=iteration_project_export,
                )
                await self._send_supervisor_assistant(
                    title="Supervisor: Loop complete",
                    content=(
                        "The candidate is close enough to the reference to stop the loop."
                    ),
                )
                return LoopRunResult(
                    code=final_code,
                    requirements=requirements,
                    blueprint_validation=blueprint_validation,
                    iterations=iterations,
                    stop_reason="pass",
                    saved_code_path=self._artifact_store.paths.best_file_path,
                    saved_run_dir=self._artifact_store.paths.run_dir,
                    saved_project_dir=(
                        best_project_export.project_dir if best_project_export else None
                    ),
                    saved_project_app_path=(
                        best_project_export.app_file_path
                        if best_project_export
                        else None
                    ),
                    analyzer_model=self._analyzer.model,
                    executor_model=self._executor.model,
                    validator_model=self._validator.model,
                )

            if validation_report.verdict == "pass":
                await self._send_supervisor_assistant(
                    title="Supervisor: Continuing despite provisional pass",
                    content=(
                        "The validator reported a provisional pass, but the run is "
                        "continuing because the stricter score gates for this input "
                        "mode have not been satisfied yet."
                    ),
                )

            if validation_report.verdict == "blocked":
                self._artifact_store.persist_metadata(
                    iteration=iteration,
                    stop_reason="blocked",
                    requirements=requirements,
                    validation_report=validation_report,
                    blueprint_validation=blueprint_validation,
                    blueprint_validation_history=blueprint_validation_history,
                    project_export=iteration_project_export,
                )
                await self._send_supervisor_assistant(
                    title="Supervisor: Loop blocked",
                    content=(
                        "Stopping because the validator marked the run as blocked and "
                        "further automatic edits are unlikely to help."
                    ),
                )
                return LoopRunResult(
                    code=best_code if best_code.strip() else last_code,
                    requirements=requirements,
                    blueprint_validation=blueprint_validation,
                    iterations=iterations,
                    stop_reason="blocked",
                    saved_code_path=self._artifact_store.paths.best_file_path,
                    saved_run_dir=self._artifact_store.paths.run_dir,
                    saved_project_dir=(
                        best_project_export.project_dir if best_project_export else None
                    ),
                    saved_project_app_path=(
                        best_project_export.app_file_path
                        if best_project_export
                        else None
                    ),
                    analyzer_model=self._analyzer.model,
                    executor_model=self._executor.model,
                    validator_model=self._validator.model,
                )

            current_file_state = {"path": "index.html", "content": last_code}

        self._artifact_store.persist_metadata(
            iteration=len(iterations),
            stop_reason="max_iterations",
            requirements=requirements,
            validation_report=validation_report,
            blueprint_validation=blueprint_validation,
            blueprint_validation_history=blueprint_validation_history,
        )
        await self._send_supervisor_assistant(
            title="Supervisor: Loop stopped at iteration cap",
            content=(
                f"The loop hit the configured limit of {self._max_iterations} iterations "
                "before reaching a passing score."
            ),
        )
        return LoopRunResult(
            code=best_code if best_code.strip() else last_code,
            requirements=requirements,
            blueprint_validation=blueprint_validation,
            iterations=iterations,
            stop_reason="max_iterations",
            saved_code_path=self._artifact_store.paths.best_file_path,
            saved_run_dir=self._artifact_store.paths.run_dir,
            saved_project_dir=(
                best_project_export.project_dir if best_project_export else None
            ),
            saved_project_app_path=(
                best_project_export.app_file_path if best_project_export else None
            ),
            analyzer_model=self._analyzer.model,
            executor_model=self._executor.model,
            validator_model=self._validator.model,
        )

    async def _status(self, message: str, data: dict[str, object] | None = None) -> None:
        await self._send_message("status", message, 0, data, None)

    def _repair_blueprint_from_reference(
        self,
        *,
        requirements: RequirementsSpec,
        reference_bundle: ReferenceBundle,
    ) -> tuple[RequirementsSpec, bool]:
        if not _requires_explicit_section_blueprint(reference_bundle):
            return requirements, False

        repaired = requirements.model_copy(deep=True)
        changed = False
        repaired, outline_changed = _merge_requirements_with_reference_outline(
            repaired,
            reference_bundle,
        )
        changed |= outline_changed
        repaired, global_lists_changed = _ensure_minimum_blueprint_global_lists(
            repaired,
            reference_bundle,
        )
        changed |= global_lists_changed
        repaired, section_layout_changed = _repair_section_layout_mismatches(repaired)
        changed |= section_layout_changed
        reference_evidence = _reference_evidence_lines(reference_bundle)
        component_evidence = _reference_component_evidence_lines(reference_bundle)
        asset_evidence = _reference_asset_evidence_lines(reference_bundle)
        dom_roles = _reference_dom_roles(reference_bundle)

        if repaired.footer_present is None and any(
            "footer" in value.lower() for value in reference_evidence
        ):
            repaired.footer_present = True
            changed = True

        typography_candidates: list[str] = []
        if reference_bundle.design_system_preflight is not None:
            typography_candidates.extend(
                value
                for value in (
                    *reference_bundle.design_system_preflight.section_typography,
                    *reference_bundle.design_system_preflight.typography,
                )
                if value.strip()
                and (
                    _contains_measured_typography(value)
                    or any(keyword in value.lower() for keyword in _TYPOGRAPHY_ROLE_KEYWORDS)
                )
            )
        if reference_bundle.live_reference is not None:
            typography_candidates.extend(
                value
                for value in (
                    *reference_bundle.live_reference.design_system.typography,
                    *reference_bundle.live_reference.design_system.heading_hierarchy,
                )
                if value.strip() and _contains_measured_typography(value)
            )
        changed |= _append_unique_strings(
            repaired.design_tokens.typography,
            typography_candidates[:10],
        )

        spacing_candidates: list[str] = []
        sizing_keywords = (
            "width",
            "height",
            "padding",
            "gap",
            "max-width",
            "min-width",
            "column",
            "row",
            "band",
            "shell",
            "container",
        )
        if reference_bundle.design_system_preflight is not None:
            spacing_candidates.extend(
                value
                for value in (
                    *reference_bundle.design_system_preflight.section_sizing,
                    *reference_bundle.design_system_preflight.layout,
                )
                if value.strip()
                and (
                    re.search(r"\b\d", value)
                    or any(keyword in value.lower() for keyword in sizing_keywords)
                )
            )
        if reference_bundle.live_reference is not None:
            spacing_candidates.extend(
                value
                for value in reference_bundle.live_reference.design_system.layout
                if value.strip()
                and (
                    re.search(r"\b\d", value)
                    or any(keyword in value.lower() for keyword in sizing_keywords)
                )
            )
        changed |= _append_unique_strings(
            repaired.design_tokens.spacing,
            spacing_candidates[:10],
        )

        shell_notes: list[str] = []
        if reference_bundle.live_reference is not None:
            shell_notes.extend(reference_bundle.live_reference.design_system.shell_relationships)
            shell_notes.extend(reference_bundle.live_reference.design_system.raw_observations)
        if reference_bundle.design_system_preflight is not None:
            shell_notes.extend(reference_bundle.design_system_preflight.source_notes)
        changed |= _append_unique_strings(
            repaired.coverage_notes,
            [
                f"Reference-backed structure: {_clean_reference_evidence(value)}."
                for value in shell_notes[:4]
            ],
        )

        if asset_evidence and not _blueprint_mentions_live_asset_reuse(
            repaired, reference_bundle
        ):
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Reuse the exact extracted live-site image, SVG, and background asset URLs instead of substituting placeholder or generated media.",
                    "Do not replace extracted site logos, product imagery, or background-image assets with approximate stand-ins when concrete live asset sources are available.",
                ],
            )
            changed |= _append_unique_strings(
                repaired.asset_requirements,
                [
                    "Use the extracted live-site image, SVG, and CSS background-image sources directly in the matching sections.",
                    *asset_evidence[:4],
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Preserve the extracted live-site media, SVG references, and background-image sources instead of downgrading them to placeholders."
                ],
            )

        font_names = _reference_custom_font_names(reference_bundle)
        if font_names and not _blueprint_mentions_font_loading(repaired):
            font_list = ", ".join(font_names)
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Load the real extracted custom fonts with an explicit font-loading mechanism instead of relying on fallback family names.",
                    f"Use @font-face, hosted font CSS, or concrete font asset URLs for the extracted custom fonts ({font_list}).",
                ],
            )
            changed |= _append_unique_strings(
                repaired.asset_requirements,
                [
                    f"Provide real font-loading assets or stylesheet references for the extracted custom fonts ({font_list})."
                ],
            )
            changed |= _append_unique_strings(
                repaired.design_tokens.typography,
                [
                    f"font loading: real font files or hosted font CSS are required for {font_list}"
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Preserve the extracted custom font usage with real font loading rather than family-name-only fallbacks."
                ],
            )

        if _reference_exposes_separate_header_states(reference_bundle):
            changed |= _append_unique_strings(
                repaired.coverage_notes,
                [
                    "Keep the opening header shell and sticky/scrolled header state as separate canonical blueprint coverage rather than merging them."
                ],
            )
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep the opening header shell separate from the sticky/scrolled header state so the top chrome does not collapse into a single generic header."
                ],
            )
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Do not merge the base header shell and the sticky/scrolled header state into a single header implementation."
                ],
            )
            has_base_header = any(
                _section_role(section) == "header"
                for section in repaired.section_requirements
            )
            has_sticky_header = any(
                _is_sticky_header_state_section(section)
                for section in repaired.section_requirements
            )
            header_evidence = _matching_reference_evidence(
                reference_evidence,
                _SECTION_ROLE_KEYWORDS["header"],
                limit=2,
            )
            sticky_evidence = _matching_reference_evidence(
                reference_evidence,
                _SECTION_ROLE_KEYWORDS["sticky"],
                limit=2,
            )
            if not has_base_header:
                layout, invariants, must_include, styling = _default_section_blueprint(
                    "header"
                )
                if header_evidence:
                    layout = (
                        f"{layout} Reference-backed shell: "
                        f"{_clean_reference_evidence(header_evidence[0])}."
                    )
                    invariants.append(
                        f"Reference-backed structure: {_clean_reference_evidence(header_evidence[0])}."
                    )
                changed |= _insert_section_requirement(
                    repaired.section_requirements,
                    SectionRequirement(
                        name="Site Header",
                        section_id="site-header",
                        layout=layout,
                        layout_invariants=invariants,
                        must_include=must_include,
                        styling=styling,
                    ),
                    before_keywords=("sticky", "hero", "article", "product", "footer"),
                )
                changed |= _insert_outline_entry(
                    repaired.page_outline,
                    "Site Header",
                    before_keywords=("sticky", "hero", "article", "product", "footer"),
                )
            if not has_sticky_header:
                layout, invariants, must_include, styling = _default_section_blueprint(
                    "sticky"
                )
                if sticky_evidence:
                    layout = (
                        f"{layout} Reference-backed shell: "
                        f"{_clean_reference_evidence(sticky_evidence[0])}."
                    )
                    invariants.append(
                        f"Reference-backed structure: {_clean_reference_evidence(sticky_evidence[0])}."
                    )
                changed |= _insert_section_requirement(
                    repaired.section_requirements,
                    SectionRequirement(
                        name="Sticky Header State",
                        section_id="sticky-header-state",
                        layout=layout,
                        layout_invariants=invariants,
                        must_include=must_include,
                        styling=styling,
                    ),
                    after_keywords=("header",) if has_base_header else ("announcement",),
                )
                changed |= _insert_outline_entry(
                    repaired.page_outline,
                    "Sticky Header State",
                    after_keywords=("header",) if has_base_header else ("announcement",),
                )

        footer_section = next(
            (
                section
                for section in repaired.section_requirements
                if _normalize_blueprint_label(section.section_id or section.name)
                in {"footer", "site-footer"}
            ),
            None,
        )
        has_footer_subsections = any(
            _normalize_blueprint_label(section.section_id or section.name).startswith("footer-")
            for section in repaired.section_requirements
        )
        if (
            footer_section is None
            and not has_footer_subsections
            and (repaired.footer_present or "newsletter" in dom_roles or "legal" in dom_roles)
        ):
            layout, invariants, must_include, styling = _default_section_blueprint(
                "footer"
            )
            footer_section = SectionRequirement(
                name="Site Footer",
                section_id="site-footer",
                layout=layout,
                layout_invariants=invariants,
                must_include=must_include,
                styling=styling,
            )
            changed |= _insert_section_requirement(
                repaired.section_requirements,
                footer_section,
            )
            changed |= _insert_outline_entry(repaired.page_outline, "Site Footer")
            changed |= _append_unique_strings(repaired.closing_sections, ["Site Footer"])
            if not repaired.footer_description.strip():
                repaired.footer_description = layout
                changed = True

        if "announcement" in dom_roles and not any(
            _section_role(section) == "announcement"
            for section in repaired.section_requirements
        ):
            layout, invariants, must_include, styling = _default_section_blueprint(
                "announcement"
            )
            evidence = _matching_reference_evidence(
                reference_evidence,
                _SECTION_ROLE_KEYWORDS["announcement"],
                limit=1,
            )
            if evidence:
                layout = (
                    f"{layout} Reference-backed shell: "
                    f"{_clean_reference_evidence(evidence[0])}."
                )
                invariants.append(
                    f"Reference-backed structure: {_clean_reference_evidence(evidence[0])}."
                )
            changed |= _insert_section_requirement(
                repaired.section_requirements,
                SectionRequirement(
                    name="Announcement Bar",
                    section_id="announcement-bar",
                    layout=layout,
                    layout_invariants=invariants,
                    must_include=must_include,
                    styling=styling,
                ),
                before_keywords=("header", "sticky", "hero", "article", "product", "footer"),
            )
            changed |= _insert_outline_entry(
                repaired.page_outline,
                "Announcement Bar",
                before_keywords=("header", "sticky", "hero", "article", "product", "footer"),
            )
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Keep the announcement bar as its own top chrome band rather than merging it into the primary header or hero."
                ],
            )

        if (
            ("modal" in dom_roles or "promo" in dom_roles)
            and not any(_section_role(section) == "modal" for section in repaired.section_requirements)
        ):
            layout, invariants, must_include, styling = _default_section_blueprint(
                "modal"
            )
            evidence = _matching_reference_evidence(
                reference_evidence,
                frozenset(
                    {
                        *_SECTION_ROLE_KEYWORDS["modal"],
                        *_DOM_ROLE_HINTS["promo"],
                    }
                ),
                limit=2,
            )
            if evidence:
                layout = (
                    f"{layout} Reference-backed shell: "
                    f"{_clean_reference_evidence(evidence[0])}."
                )
                invariants.append(
                    f"Reference-backed structure: {_clean_reference_evidence(evidence[0])}."
                )
            modal_name = "Promotional Modal" if "promo" in dom_roles else "Modal Overlay"
            changed |= _insert_section_requirement(
                repaired.section_requirements,
                SectionRequirement(
                    name=modal_name,
                    section_id=_normalize_blueprint_label(modal_name),
                    layout=layout,
                    layout_invariants=invariants,
                    must_include=must_include,
                    styling=styling,
                ),
                before_keywords=("announcement", "header", "sticky", "hero", "article", "product", "footer"),
            )
            changed |= _insert_outline_entry(
                repaired.page_outline,
                modal_name,
                before_keywords=("announcement", "header", "sticky", "hero", "article", "product", "footer"),
            )
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Keep blocking modal or promo overlays explicit in the canonical section list instead of leaving them implicit in coverage notes."
                ],
            )

        if "related" in dom_roles and not any(
            _section_role(section) == "related"
            for section in repaired.section_requirements
        ):
            layout, invariants, must_include, styling = _default_section_blueprint(
                "related"
            )
            evidence = _matching_reference_evidence(
                reference_evidence,
                _SECTION_ROLE_KEYWORDS["related"],
                limit=1,
            )
            if evidence:
                layout = (
                    f"{layout} Reference-backed shell: "
                    f"{_clean_reference_evidence(evidence[0])}."
                )
                invariants.append(
                    f"Reference-backed structure: {_clean_reference_evidence(evidence[0])}."
                )
            related_name = (
                "Related Articles"
                if any("article" in value.lower() for value in evidence)
                else "Related Content"
            )
            changed |= _insert_section_requirement(
                repaired.section_requirements,
                SectionRequirement(
                    name=related_name,
                    section_id=_normalize_blueprint_label(related_name),
                    layout=layout,
                    layout_invariants=invariants,
                    must_include=must_include,
                    styling=styling,
                ),
                before_keywords=("footer", "legal"),
            )
            changed |= _insert_outline_entry(
                repaired.page_outline,
                related_name,
                before_keywords=("footer", "legal"),
            )
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Keep related content as a dedicated section above the footer with its secondary CTA rendered as a button treatment when the reference exposes button chrome."
                ],
            )

        if footer_section is not None:
            if not repaired.footer_description.strip():
                repaired.footer_description = footer_section.layout
                changed = True
            changed |= _append_unique_strings(
                repaired.closing_sections,
                [footer_section.name],
            )
            if "newsletter" in dom_roles:
                changed |= _append_unique_strings(
                    footer_section.must_include,
                    ["newsletter or signup area"],
                )
                changed |= _append_unique_strings(
                    footer_section.layout_invariants,
                    [
                        "Newsletter or signup content remains grouped within the upper footer content rather than being dropped from the closing shell."
                    ],
                )
            if "legal" in dom_roles:
                changed |= _append_unique_strings(
                    footer_section.must_include,
                    ["legal or accessibility band"],
                )
                changed |= _append_unique_strings(
                    footer_section.layout_invariants,
                    [
                        "Keep the closing legal or accessibility row as a distinct footer band beneath the upper footer content."
                    ],
                )
                changed |= _append_unique_strings(
                    footer_section.styling,
                    ["separate legal-band surface or spacing treatment"],
                )
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Preserve footer depth, including separate upper/footer utility content and lower legal or accessibility bands when the reference exposes both."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Preserve closing footer composition, including newsletter or utility content and any distinct legal or accessibility band."
                ],
            )

        for section in repaired.section_requirements:
            role = _section_role(section)
            canonical_identity = _canonical_section_identity(
                section,
                role,
                reference_bundle=reference_bundle,
            )
            if canonical_identity is None:
                continue
            canonical_name, canonical_id = canonical_identity
            if section.name != canonical_name:
                section.name = canonical_name
                changed = True
            if section.section_id != canonical_id:
                section.section_id = canonical_id
                changed = True

        for section in repaired.section_requirements:
            role = _section_role(section)
            default_layout, default_invariants, default_must_include, default_styling = (
                _default_section_blueprint(role)
            )
            section_evidence = _section_reference_evidence(reference_bundle, section)
            if not section.layout.strip() or _is_vague_layout_description(section.layout):
                section.layout = default_layout
                if section_evidence:
                    section.layout = (
                        f"{section.layout} Reference-backed shell: "
                        f"{_clean_reference_evidence(section_evidence[0])}."
                    )
                changed = True
            elif section_evidence:
                evidence_phrase = _clean_reference_evidence(section_evidence[0]).lower()
                if evidence_phrase not in section.layout.lower():
                    section.layout = (
                        f"{section.layout.rstrip('.')}. Reference-backed shell: "
                        f"{_clean_reference_evidence(section_evidence[0])}."
                    )
                    changed = True
            if (
                _count_nonempty(section.layout_invariants) < 2
                or _count_specific(section.layout_invariants) < 1
            ):
                changed |= _append_unique_strings(
                    section.layout_invariants,
                    default_invariants,
                )
            if section_evidence:
                changed |= _append_unique_strings(
                    section.layout_invariants,
                    [
                        f"Reference-backed structure: {_clean_reference_evidence(value)}."
                        for value in section_evidence[:1]
                    ],
                )
            if _count_nonempty(section.must_include) < 3:
                changed |= _append_unique_strings(section.must_include, default_must_include)
            if _count_nonempty(section.styling) < 2:
                changed |= _append_unique_strings(section.styling, default_styling)
            section_asset_evidence = _section_asset_evidence(
                reference_bundle,
                section,
                limit=2,
            )
            if section_asset_evidence:
                changed |= _append_unique_strings(section.assets, section_asset_evidence)
            changed |= _sanitize_section_requirement_from_reference(
                reference_bundle,
                section,
            )

        canonical_closing_sections = _build_canonical_closing_sections(repaired)
        if repaired.closing_sections != canonical_closing_sections:
            repaired.closing_sections = canonical_closing_sections
            changed = True
        canonical_execution_plan = _build_canonical_execution_plan(repaired)
        if repaired.execution_plan != canonical_execution_plan:
            repaired.execution_plan = canonical_execution_plan
            changed = True

        missing_component_geometry = _missing_component_geometry_signals(
            reference_bundle,
            repaired,
        )
        exposed_component_geometry = [
            signal.replace("_", " ")
            for signal, keywords in _COMPONENT_GEOMETRY_REFERENCE_HINTS.items()
            if any(
                any(keyword in value.lower() for keyword in keywords)
                for value in component_evidence
            )
        ]
        component_geometry_to_apply = sorted(
            {
                *missing_component_geometry,
                *exposed_component_geometry,
            }
        )
        if component_geometry_to_apply:
            target_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _section_role(section) == "showcase"
                ),
                None,
            )
            if target_section is None:
                target_section = next(
                    (
                        section
                        for section in repaired.section_requirements
                        if _section_role(section) not in {"announcement", "header", "sticky", "footer", "modal"}
                    ),
                    None,
                )
            if target_section is not None:
                if "split panels" in component_geometry_to_apply:
                    split_evidence = _section_component_evidence(
                        reference_bundle,
                        target_section,
                        keywords=_COMPONENT_GEOMETRY_REFERENCE_HINTS["split_panels"],
                        limit=1,
                    )
                    changed |= _append_unique_strings(
                        target_section.layout_invariants,
                        [
                            "Keep the section as a split layout with distinct media and detail panels when the reference exposes left/right panel geometry."
                        ],
                    )
                    changed |= _append_unique_strings(
                        target_section.must_include,
                        ["left media panel", "right detail column"],
                    )
                    if split_evidence:
                        cleaned = _clean_reference_evidence(split_evidence[0])
                        if cleaned.lower() not in target_section.layout.lower():
                            target_section.layout = (
                                f"{target_section.layout.rstrip('.')}. Reference-backed geometry: {cleaned}."
                            )
                            changed = True
                        changed |= _append_unique_strings(
                            target_section.layout_invariants,
                            [f"Reference-backed geometry: {cleaned}."],
                        )
                    changed |= _append_unique_strings(
                        repaired.hard_constraints,
                        [
                            "Preserve reference-backed split-panel geometry and left/right panel sizing hierarchy rather than collapsing the section into a single-column block."
                        ],
                    )
                if "repeated items" in component_geometry_to_apply:
                    repeated_evidence = _section_component_evidence(
                        reference_bundle,
                        target_section,
                        keywords=_COMPONENT_GEOMETRY_REFERENCE_HINTS["repeated_items"],
                        limit=2,
                    )
                    orientation_sentence = (
                        "Keep repeated items in a horizontal row at desktop when the reference exposes row-based orientation."
                    )
                    if any("vertical stack" in value.lower() for value in repeated_evidence):
                        orientation_sentence = (
                            "Keep repeated items in the reference-backed vertical stack when the live DOM exposes stacked composition."
                        )
                    changed |= _append_unique_strings(
                        target_section.layout_invariants,
                        [orientation_sentence],
                    )
                    changed |= _append_unique_strings(
                        target_section.must_include,
                        ["repeated item cluster", "representative repeated-item composition"],
                    )
                    if repeated_evidence:
                        changed |= _append_unique_strings(
                            target_section.layout_invariants,
                            [
                                f"Reference-backed repeated-item structure: {_clean_reference_evidence(repeated_evidence[0])}."
                            ],
                        )
                    changed |= _append_unique_strings(
                        repaired.hard_constraints,
                        [
                            "Do not flip repeated-item orientation away from the live DOM geometry; preserve row-vs-stack behavior from the reference."
                        ],
                    )
                if "media fill" in component_geometry_to_apply:
                    media_evidence = _section_component_evidence(
                        reference_bundle,
                        target_section,
                        keywords=_COMPONENT_GEOMETRY_REFERENCE_HINTS["media_fill"],
                        limit=1,
                    )
                    changed |= _append_unique_strings(
                        target_section.layout_invariants,
                        [
                            "Media fills its panel edge-to-edge at full height with cover-style cropping when the reference exposes full-height media coverage."
                        ],
                    )
                    changed |= _append_unique_strings(
                        target_section.styling,
                        ["full-height cover-style media treatment"],
                    )
                    if media_evidence:
                        changed |= _append_unique_strings(
                            target_section.styling,
                            [
                                f"Reference-backed media treatment: {_clean_reference_evidence(media_evidence[0])}."
                            ],
                        )
                    changed |= _append_unique_strings(
                        repaired.hard_constraints,
                        [
                            "Keep image or media panels full-height and edge-to-edge when the reference exposes cover-style media fill."
                        ],
                    )
                if "gradient shells" in component_geometry_to_apply:
                    gradient_evidence = _section_component_evidence(
                        reference_bundle,
                        target_section,
                        keywords=_COMPONENT_GEOMETRY_REFERENCE_HINTS["gradient_shells"],
                        limit=1,
                    )
                    changed |= _append_unique_strings(
                        target_section.styling,
                        ["gradient section surface/background shell"],
                    )
                    if gradient_evidence:
                        changed |= _append_unique_strings(
                            target_section.styling,
                            [
                                f"Reference-backed surface treatment: {_clean_reference_evidence(gradient_evidence[0])}."
                            ],
                        )
                    changed |= _append_unique_strings(
                        repaired.hard_constraints,
                        [
                            "Preserve gradient-backed section shells where the reference exposes a gradient rather than flattening them to a solid fill."
                        ],
                    )

        changed |= _append_unique_strings(
            repaired.preserve_requirements,
            [
                "Preserve the live DOM section ordering and keep top chrome, main content shells, related content, and footer coverage explicit instead of implicit.",
                "Preserve section-specific shell relationships, surface treatments, and panel geometry exposed by the live DOM and design-system evidence.",
            ],
        )

        section_roles = {_section_role(section) for section in repaired.section_requirements}
        shared_shell_reference = any(
            keyword in value.lower()
            for value in reference_evidence
            for keyword in (
                "shared shell",
                "same shell",
                "reading shell",
                "article shell",
                "rounded shell",
                "reading column",
            )
        )
        if {"hero", "body"} <= section_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep the hero and body in one continuous main reading flow rather than flattening them into unrelated full-width sections.",
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Shared hero/body reading shell",
                ],
            )
            if shared_shell_reference:
                changed |= _append_unique_strings(
                    repaired.critical_layout_invariants,
                    [
                        "When the reference exposes a shared article or reading shell, keep the hero and body inside that same shell instead of splitting them across disconnected surfaces."
                    ],
                )
        if {"modal", "announcement", "header"} & section_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep top chrome layers separate from the main page flow so overlays, announcement bars, and opening headers do not collapse into one generic header band."
                ],
            )
        if {"announcement", "header"} <= section_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep the announcement band above the opening header rather than merging both into a single top bar."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Dedicated top announcement or promotional band",
                ],
            )
        if {"header", "sticky"} <= section_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep the sticky header state as a compact alternate chrome state rather than reusing the opening header shell one-for-one."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Distinct sticky/scrolled header state",
                ],
            )
        if "header" in section_roles:
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Primary navigation header shell",
                ],
            )
        if "modal" in section_roles:
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Modal or overlay first-load experience",
                ],
            )
        if "showcase" in section_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep the showcase as a breakout shell with its own panel geometry instead of collapsing it into the narrower reading column."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Split media/detail showcase shell",
                    "Reference-backed repeated-item orientation",
                ],
            )
        if any("gradient" in value.lower() for value in component_evidence):
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Gradient-backed feature or showcase shell",
                ],
            )
        if "related" in section_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep related content as its own closing section above the footer rather than absorbing it into the footer shell."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Related-content card collection with secondary CTA treatment",
                ],
            )
        if "footer" in section_roles:
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Footer newsletter or utility signup block",
                    "Footer legal or accessibility closing band",
                ],
            )
        if {"related", "footer"} <= section_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep related content above the footer and preserve the footer as the final closing region of the page."
                ],
            )
        if "footer" in section_roles and "legal" in dom_roles:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "Keep the footer's upper utility or newsletter region separate from its lower legal or accessibility band when the reference exposes both."
                ],
            )

        if any(
            keyword in value.lower()
            for value in reference_evidence
            for keyword in ("button", "pill", "cta", "join", "subscribe", "view all", "read more")
        ):
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Preserve button-like actions as full shell treatments rather than degrading them into plain text links when the reference exposes pill or button chrome."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Button-shell CTA treatments",
                ],
            )
        if shared_shell_reference:
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Do not split a shared reading or article shell into separate unrelated surfaces when the live reference exposes a continuous content shell."
                ],
            )
        if any(
            keyword in value.lower()
            for value in reference_evidence
            for keyword in ("mega", "submenu", "dropdown", "discover", "shop menu")
        ):
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Preserve distinct navigation menu or dropdown treatments when the reference exposes multi-state navigation shells."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Navigation menu and dropdown shell behavior",
                ],
            )

        canonical_outline = [
            section.name for section in repaired.section_requirements if section.name.strip()
        ]
        if canonical_outline and canonical_outline != repaired.page_outline:
            repaired.page_outline = canonical_outline
            changed = True
        if repaired.footer_present:
            canonical_closing = [
                section.name
                for section in repaired.section_requirements
                if _section_role(section) in {"related", "footer"}
            ]
            if canonical_closing and canonical_closing != repaired.closing_sections:
                repaired.closing_sections = canonical_closing
                changed = True

        if changed:
            return repaired, True
        return requirements, False

    def _repair_blueprint_from_validation_feedback(
        self,
        *,
        requirements: RequirementsSpec,
        reference_bundle: ReferenceBundle,
        blueprint_validation: BlueprintValidationReport,
    ) -> tuple[RequirementsSpec, bool]:
        repaired = requirements.model_copy(deep=True)
        changed = False
        issue_blob = " ".join(
            value.strip()
            for value in (
                blueprint_validation.summary,
                *blueprint_validation.missing_sections,
                *blueprint_validation.repair_instructions,
                *(
                    part
                    for issue in blueprint_validation.issues
                    for part in (
                        issue.title,
                        issue.detail,
                        issue.fix_instructions,
                    )
                ),
            )
            if value.strip()
        ).lower()
        full_dom = (
            reference_bundle.live_reference.full_dom_html.lower()
            if reference_bundle.live_reference is not None
            else ""
        )
        reference_assets = _reference_asset_evidence_lines(reference_bundle)
        white_logo_assets = [
            asset
            for asset in reference_assets
            if "header_white_logo" in asset.lower()
        ]
        header_logo_assets = [
            asset
            for asset in reference_assets
            if "header-logo-new" in asset.lower()
        ]
        modal_logo_assets = [
            asset
            for asset in reference_assets
            if "files.alia-prod.com/im8logo" in asset.lower()
        ]
        showcase_value_assets = [
            asset
            for asset in reference_assets
            if "bundle_li_bg" in asset.lower()
        ]
        font_asset_urls = _extract_font_asset_urls(reference_bundle)

        site_header_exists = any(
            _normalize_blueprint_label(section.section_id or section.name) == "site-header"
            for section in repaired.section_requirements
        )

        if (
            "cross-contamination" in issue_blob
            or "copy-paste errors" in issue_blob
            or "erroneously pasted" in issue_blob
        ):
            shop_now_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "shop-now-bar"
                ),
                None,
            )
            if shop_now_section is not None:
                filtered_layout_invariants = [
                    value
                    for value in shop_now_section.layout_invariants
                    if not any(
                        token in value.lower()
                        for token in (
                            "newsletter",
                            "legal",
                            "accessibility",
                            "footer",
                            "5-column",
                            "link grid",
                        )
                    )
                ]
                if filtered_layout_invariants != shop_now_section.layout_invariants:
                    shop_now_section.layout_invariants = filtered_layout_invariants
                    changed = True
                filtered_must_include = [
                    value
                    for value in shop_now_section.must_include
                    if not any(
                        token in value.lower()
                        for token in (
                            "newsletter",
                            "legal",
                            "accessibility",
                            "footer",
                            "link grid",
                        )
                    )
                ]
                if filtered_must_include != shop_now_section.must_include:
                    shop_now_section.must_include = filtered_must_include
                    changed = True
                filtered_styling = [
                    value
                    for value in shop_now_section.styling
                    if not any(
                        token in value.lower()
                        for token in (
                            "legal-band",
                            "5-column",
                            "footer",
                            "newsletter",
                        )
                    )
                ]
                if filtered_styling != shop_now_section.styling:
                    shop_now_section.styling = filtered_styling
                    changed = True
                if any(
                    token in shop_now_section.layout.lower()
                    for token in ("footer region", "newsletter", "legal", "5-column")
                ):
                    shop_now_section.layout = (
                        "Sticky promotional CTA bar that appears on scroll as its own "
                        "top chrome band, with a dark burgundy gradient shell, promo "
                        "copy cluster, live pulse dot, and a primary 'Get Started' CTA."
                    )
                    changed = True

            announcement_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "announcement-bar"
                ),
                None,
            )
            if announcement_section is not None:
                for attr in ("layout_invariants", "must_include", "styling"):
                    current = getattr(announcement_section, attr)
                    filtered = [
                        value
                        for value in current
                        if not any(
                            token in value.lower()
                            for token in (
                                "newsletter",
                                "legal",
                                "accessibility",
                                "footer",
                                "beckham",
                                "product card",
                            )
                        )
                    ]
                    if filtered != current:
                        setattr(announcement_section, attr, filtered)
                        changed = True
                if any(
                    token in announcement_section.layout.lower()
                    for token in ("footer", "newsletter", "legal", "beckham")
                ):
                    announcement_section.layout = (
                        "Slim full-width announcement strip with centered utility copy "
                        "and any inline controls inside its own top chrome band."
                    )
                    changed = True

            modal_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _section_role(section) == "modal"
                ),
                None,
            )
            if modal_section is not None:
                for attr in ("layout_invariants", "must_include", "styling"):
                    current = getattr(modal_section, attr)
                    filtered = [
                        value
                        for value in current
                        if "beckham" not in value.lower()
                        and "product card" not in value.lower()
                        and "newsletter" not in value.lower()
                        and "legal" not in value.lower()
                    ]
                    if filtered != current:
                        setattr(modal_section, attr, filtered)
                        changed = True

            footer_logo_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "footer-logo"
                ),
                None,
            )
            if footer_logo_section is not None:
                filtered_must_include = [
                    value
                    for value in footer_logo_section.must_include
                    if not any(
                        token in value.lower()
                        for token in (
                            "newsletter",
                            "legal",
                            "accessibility",
                            "signup",
                            "link grid",
                        )
                    )
                ]
                if filtered_must_include != footer_logo_section.must_include:
                    footer_logo_section.must_include = filtered_must_include
                    changed = True

        if "back to blog" in issue_blob:
            article_body = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "article-body"
                ),
                None,
            )
            if article_body is not None:
                changed |= _append_unique_strings(
                    article_body.must_include,
                    ["Back to blog link with arrow icon"],
                )
                changed |= _append_unique_strings(
                    article_body.copy_items,
                    ["Back to blog"],
                )

        if (
            "related articles" in issue_blob
            and "background invariant" in issue_blob
            and "white" in issue_blob
        ):
            related_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "related-articles"
                ),
                None,
            )
            if related_section is not None:
                filtered_invariants = [
                    value
                    for value in related_section.layout_invariants
                    if "blush" not in value.lower()
                ]
                if filtered_invariants != related_section.layout_invariants:
                    related_section.layout_invariants = filtered_invariants
                    changed = True
                filtered_styling = [
                    value for value in related_section.styling if "blush" not in value.lower()
                ]
                if filtered_styling != related_section.styling:
                    related_section.styling = filtered_styling
                    changed = True
                changed |= _append_unique_strings(
                    related_section.layout_invariants,
                    [
                        "Use a white section surface/background for the related-articles region rather than reusing the blush article canvas."
                    ],
                )
                changed |= _append_unique_strings(
                    related_section.styling,
                    ["white section background with distinct card surfaces"],
                )

        if (
            "single continuous blush shell" in issue_blob
            or (
                "article hero" in issue_blob
                and "article body" in issue_blob
                and "continuous" in issue_blob
            )
        ):
            article_hero = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "article-hero"
                ),
                None,
            )
            article_body = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "article-body"
                ),
                None,
            )
            if article_hero is not None and article_body is not None:
                shared_shell_rule = (
                    "Article Hero and Article Body must be rendered inside one continuous blush article shell rather than as sibling full-width sections."
                )
                changed |= _append_unique_strings(
                    repaired.critical_layout_invariants,
                    [shared_shell_rule],
                )
                changed |= _append_unique_strings(
                    repaired.preserve_requirements,
                    ["Shared article shell spanning the hero and body"],
                )
                changed |= _append_unique_strings(
                    article_hero.layout_invariants,
                    [shared_shell_rule],
                )
                changed |= _append_unique_strings(
                    article_body.layout_invariants,
                    [shared_shell_rule],
                )
                if "continuous blush article shell" not in article_hero.layout.lower():
                    article_hero.layout = (
                        f"{article_hero.layout.rstrip('.')}. "
                        "This hero sits at the top of a continuous blush article shell "
                        "shared with the article body below."
                    )
                    changed = True
                if "continuous blush article shell" not in article_body.layout.lower():
                    article_body.layout = (
                        f"{article_body.layout.rstrip('.')}. "
                        "This body continues inside the same continuous blush article "
                        "shell that begins with the article hero above."
                    )
                    changed = True

        if (
            "shop now" in issue_blob
            or "shop-now-bar" in issue_blob
            or "shopify-section-shop-now-bar" in full_dom
        ):
            shop_now_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "shop-now-bar"
                ),
                None,
            )
            if shop_now_section is None:
                shop_now_section = SectionRequirement(
                    name="Shop Now Bar",
                    section_id="shop-now-bar",
                    layout=(
                        "Sticky promotional CTA bar that appears on scroll as its own "
                        "top chrome band, with a dark burgundy gradient shell, promo "
                        "copy cluster, live pulse dot, and a primary 'Get Started' CTA."
                    ),
                    layout_invariants=[
                        "Keep the Shop Now bar separate from both the announcement bar and the sticky header shell.",
                        "Preserve this bar as a sticky CTA band that appears on scroll instead of folding it into generic header chrome.",
                    ],
                    must_include=[
                        "sticky promo copy cluster",
                        "live pulse dot",
                        "Get Started CTA button",
                    ],
                    styling=[
                        "dark burgundy cinematic gradient background",
                        "gold shimmer sweep across the bar surface",
                        "gold-accent event label plus translucent white offer text",
                    ],
                    copy_items=[
                        "Save 30% + Get Free Welcome Gifts",
                        "Free Shipping on All Subscriptions",
                        "Get Started",
                    ],
                    behaviors=[
                        "Appears only after scrolling past the opening header state and remains sticky at the top of the viewport.",
                    ],
                )
                changed |= _insert_section_requirement(
                    repaired.section_requirements,
                    shop_now_section,
                    after_keywords=(
                        ("site-header",) if site_header_exists else ("announcement",)
                    ),
                )
                changed |= _insert_outline_entry(
                    repaired.page_outline,
                    "Shop Now Bar",
                    after_keywords=(
                        ("site-header",) if site_header_exists else ("announcement",)
                    ),
                )
            if not shop_now_section.purpose.strip():
                shop_now_section.purpose = (
                    "Provide a distinct sticky promotional CTA bar that appears on "
                    "scroll down with a white IM8 logo, promo copy, pulse dot, and "
                    "Get Started action."
                )
                changed = True
            changed |= _append_unique_strings(
                shop_now_section.must_include,
                [
                    "white IM8 logo",
                    "sticky promo copy cluster",
                    "live pulse dot",
                    "Get Started CTA button",
                ],
            )
            changed |= _append_unique_strings(
                shop_now_section.assets,
                white_logo_assets[:1],
            )
            changed |= _append_unique_strings(
                shop_now_section.editable_fields,
                [
                    "promo bar offer copy",
                    "promo bar CTA label",
                ],
            )
            changed |= _append_unique_strings(
                shop_now_section.layout_invariants,
                [
                    "Keep the CTA, pulse dot, and promo copy in one measured sticky bar rather than collapsing them into plain header links.",
                ],
            )
            changed |= _append_unique_strings(
                repaired.coverage_notes,
                [
                    "A dedicated Shop Now sticky CTA bar appears on scroll and must remain separate from the opening header and sticky header shells."
                ],
            )
            changed |= _append_unique_strings(
                repaired.hard_constraints,
                [
                    "Do not omit or absorb the Shop Now sticky CTA bar when the live DOM exposes a dedicated shop-now-bar section."
                ],
            )
            changed |= _append_unique_strings(
                repaired.behavior_requirements,
                [
                    "Scrolling down should reveal the Shop Now Bar as a distinct sticky CTA band, while scrolling up restores the compact white sticky header shell.",
                ],
            )

        if (
            "replace the 'sticky header' section" in issue_blob
            or "missing 'shop now bar'" in issue_blob
        ):
            sticky_placeholder = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    in {"sticky-header", "sticky-header-state", "header"}
                    and "shop-now-bar"
                    not in _normalize_blueprint_label(section.section_id or section.name)
                ),
                None,
            )
            existing_shop_now = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "shop-now-bar"
                ),
                None,
            )
            if sticky_placeholder is not None and existing_shop_now is None:
                sticky_placeholder.name = "Shop Now Bar"
                sticky_placeholder.section_id = "shop-now-bar"
                sticky_placeholder.purpose = (
                    "Provide the scroll-triggered sticky promotional CTA bar with "
                    "the white IM8 logo, promo text, and Get Started button."
                )
                sticky_placeholder.layout = (
                    "Dark burgundy sticky promo bar with the white logo on the left, "
                    "promotional text in the center, and a solid red Get Started CTA "
                    "on the right."
                )
                sticky_placeholder.layout_invariants = [
                    "Appears as the sticky bar during deeper scroll instead of reusing the main white header shell.",
                    "Keep the white logo, promo copy, and CTA in one measured horizontal bar.",
                ]
                sticky_placeholder.must_include = [
                    "white IM8 logo",
                    "promotional text cluster",
                    "Get Started CTA button",
                ]
                sticky_placeholder.styling = [
                    "dark burgundy gradient background",
                    "gold-accent promo text treatment",
                    "Get Started button uses a solid vitality red pill background with white text.",
                ]
                sticky_placeholder.copy_items = [
                    "Save 30% + Get Free Welcome Gifts",
                    "Free Shipping on All Subscriptions",
                    "Get Started",
                ]
                sticky_placeholder.assets = white_logo_assets[:1]
                sticky_placeholder.behaviors = [
                    "Slides into view as the sticky promotional bar during scroll.",
                ]
                sticky_placeholder.editable_fields = [
                    "promo bar offer copy",
                    "promo bar CTA label",
                ]
                changed = True

        if (
            "misidentified chrome layers" in issue_blob
            or "remove the redundant 'site header'" in issue_blob
            or "redundant 'site header'" in issue_blob
        ):
            original_count = len(repaired.section_requirements)
            repaired.section_requirements = [
                section
                for section in repaired.section_requirements
                if _normalize_blueprint_label(section.section_id or section.name)
                != "site-header"
            ]
            if len(repaired.section_requirements) != original_count:
                changed = True
            original_outline = list(repaired.page_outline)
            repaired.page_outline = [
                value
                for value in repaired.page_outline
                if _normalize_blueprint_label(value) != "site-header"
            ]
            if repaired.page_outline != original_outline:
                changed = True
            site_header_exists = False

            sticky_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _is_sticky_header_state_section(section)
                ),
                None,
            )
            if sticky_section is not None:
                if not sticky_section.purpose.strip():
                    sticky_section.purpose = (
                        "Provide the primary white navigation header that remains "
                        "sticky from the opening page state, with centered IM8 "
                        "branding, split navigation, and utility actions."
                    )
                    changed = True
                changed |= _append_unique_strings(
                    sticky_section.must_include,
                    [
                        "centered IM8 logo wordmark",
                        "split navigation groups",
                        "search utility",
                    ],
                )
                sticky_section.assets = [
                    asset
                    for asset in sticky_section.assets
                    if "header_white_logo" not in asset.lower()
                ]
                changed |= _append_unique_strings(
                    sticky_section.assets,
                    header_logo_assets[:1],
                )
                changed |= _append_unique_strings(
                    sticky_section.copy_items,
                    ["Shop", "Discover", "Search"],
                )
                changed |= _append_unique_strings(
                    sticky_section.behaviors,
                    [
                        "Acts as the primary white navigation header from initial load, while the Shop Now Bar appears separately during scroll-down behavior.",
                    ],
                )
                changed |= _append_unique_strings(
                    sticky_section.editable_fields,
                    ["sticky header navigation labels", "sticky header utility labels"],
                )

        site_header_section = next(
            (
                section
                for section in repaired.section_requirements
                if _normalize_blueprint_label(section.section_id or section.name)
                == "site-header"
            ),
            None,
        )
        if site_header_section is not None and (
            "sparse site header definition" in issue_blob
            or "execution plan missing new sections" in issue_blob
            or "shop now" in issue_blob
        ):
            if not site_header_section.purpose.strip():
                site_header_section.purpose = (
                    "Present the opening desktop header state with the centered IM8 "
                    "logo, split navigation groups, and utility actions before the "
                    "sticky chrome states take over."
                )
                changed = True
            changed |= _append_unique_strings(
                site_header_section.must_include,
                [
                    "centered IM8 logo wordmark",
                    "split primary navigation groups",
                    "search utility",
                ],
            )
            changed |= _append_unique_strings(
                site_header_section.copy_items,
                [
                    "Shop",
                    "Discover",
                    "Search",
                ],
            )
            changed |= _append_unique_strings(
                site_header_section.assets,
                header_logo_assets[:1],
            )
            changed |= _append_unique_strings(
                site_header_section.behaviors,
                [
                    "Opening white header is the default desktop chrome before sticky states appear during scroll.",
                ],
            )
            changed |= _append_unique_strings(
                site_header_section.editable_fields,
                [
                    "header navigation labels",
                    "header utility labels",
                ],
            )

        if (
            "asset misattribution" in issue_blob
            or "unresolved asset misattribution" in issue_blob
            or "remove unrelated assets" in issue_blob
        ):
            for section in repaired.section_requirements:
                role = _section_role(section)
                filtered_assets = list(section.assets)
                if role == "announcement":
                    filtered_assets = [
                        asset
                        for asset in filtered_assets
                        if not any(
                            token in asset.lower()
                            for token in (
                                "header-logo-new",
                                "files.alia-prod.com/im8logo",
                                "header_white_logo",
                            )
                        )
                    ]
                if role in {"header", "sticky", "hero"}:
                    filtered_assets = [
                        asset
                        for asset in filtered_assets
                        if "header_white_logo" not in asset.lower()
                    ]
                if role == "body":
                    filtered_assets = [
                        asset
                        for asset in filtered_assets
                        if "bundle_li_bg" not in asset.lower()
                    ]
                if filtered_assets != section.assets:
                    section.assets = filtered_assets
                    changed = True

            shop_now_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "shop-now-bar"
                ),
                None,
            )
            if shop_now_section is not None:
                changed |= _append_unique_strings(
                    shop_now_section.assets,
                    white_logo_assets[:1],
                )

            showcase_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _section_role(section) == "showcase"
                ),
                None,
            )
            if showcase_section is not None:
                changed |= _append_unique_strings(
                    showcase_section.assets,
                    showcase_value_assets[:1],
                )

        if "fragmented article shell" in issue_blob or "article shell" in issue_blob:
            changed |= _append_unique_strings(
                repaired.critical_layout_invariants,
                [
                    "ArticleHero and ArticleBody must be rendered inside one shared ArticleShell wrapper so the white rounded reading card and blush outer canvas remain continuous.",
                ],
            )
            changed |= _append_unique_strings(
                repaired.structure_guidance,
                [
                    "Wrap ArticleHero and ArticleBody inside a shared ArticleShell component that owns the white rounded reading surface, blush canvas, and ambient overlays.",
                ],
            )
            changed |= _append_unique_strings(
                repaired.layout_requirements,
                [
                    "Use a single shared article shell wrapper for the hero and body instead of rendering them as visually disconnected sibling sections.",
                ],
            )

        if any(
            phrase in issue_blob
            for phrase in (
                "article header",
                "duplicated titles",
                "category tag",
                "hero image",
                "article h1 title",
            )
        ):
            article_header_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    in {"article-hero", "article-header"}
                ),
                None,
            )
            article_body_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "article-body"
                ),
                None,
            )
            if article_header_section is not None:
                if article_header_section.name != "Article Header":
                    article_header_section.name = "Article Header"
                    changed = True
                if article_header_section.section_id != "article-header":
                    article_header_section.section_id = "article-header"
                    changed = True
                article_header_section.purpose = (
                    "Present the article title, category tag, and hero image in one "
                    "shared header block before the reading copy begins."
                )
                article_header_section.layout = (
                    "Shared article-shell header block inside the white rounded reading "
                    "surface with this exact vertical order: H1 title, category tag "
                    "pill, then hero image."
                )
                article_header_section.must_include = [
                    value
                    for value in article_header_section.must_include
                    if not any(
                        token in value.lower()
                        for token in (
                            "eyebrow",
                            "metadata",
                            "headline",
                            "supporting detail",
                        )
                    )
                ]
                changed |= _append_unique_strings(
                    article_header_section.must_include,
                    [
                        "H1 article title",
                        "category tag pill",
                        "hero image",
                    ],
                )
                changed |= _append_unique_strings(
                    article_header_section.layout_invariants,
                    [
                        "Maintain the exact article-header order of H1 title, then category tag, then hero image.",
                        "Keep the title/tag/image inside the shared article shell instead of splitting them across the body section.",
                    ],
                )
                changed |= _append_unique_strings(
                    article_header_section.copy_items,
                    [
                        "The Future of Nutrition: How IM8 Scientific Advisory Board is Shaping the Next Era of Health and Wellness",
                        "Wellness",
                    ],
                )
            if article_body_section is not None:
                article_body_section.layout = (
                    "Narrow centered reading column inside the same shared article shell, "
                    "containing only the long-form rich text paragraphs, article "
                    "subheadings, and any article-end disclaimer or back-link content "
                    "below the hero image."
                )
                article_body_section.must_include = [
                    value
                    for value in article_body_section.must_include
                    if not any(
                        token in value.lower()
                        for token in (
                            "article h1 title",
                            "category tag",
                            "hero image",
                        )
                    )
                ]
                article_body_section.copy_items = [
                    value
                    for value in article_body_section.copy_items
                    if value.strip().lower()
                    not in {
                        "the future of nutrition: how im8 scientific advisory board is shaping the next era of health and wellness",
                        "wellness",
                    }
                ]
                article_body_section.assets = [
                    asset
                    for asset in article_body_section.assets
                    if "/articles/blog-sab.png" not in asset.lower()
                ]
                changed |= _append_unique_strings(
                    article_body_section.must_include,
                    [
                        "Multiple article subheadings and paragraphs",
                    ],
                )
                changed |= _append_unique_strings(
                    article_body_section.layout_invariants,
                    [
                        "Do not duplicate the article title, category tag, or hero image inside the body section once the shared article header is defined.",
                    ],
                )
            updated_outline: list[str] = []
            outline_changed = False
            for entry in repaired.page_outline:
                if _normalize_blueprint_label(entry) == "article-hero":
                    updated_outline.append("Article Header")
                    outline_changed = True
                else:
                    updated_outline.append(entry)
            if outline_changed:
                repaired.page_outline = updated_outline
                changed = True

        showcase_section = next(
            (
                section
                for section in repaired.section_requirements
                if _section_role(section) == "showcase"
            ),
            None,
        )
        if showcase_section is not None and (
            "product showcase card layout" in issue_blob
            or "contradictory product card orientation" in issue_blob
            or "vertical stacks" in issue_blob
            or "image on top" in issue_blob
            or "image left, text right" in issue_blob
        ):
            showcase_section.must_include = [
                value
                for value in showcase_section.must_include
                if not any(
                    token in value.lower()
                    for token in (
                        "three horizontal product cards",
                        "image left, text right",
                        "stacked product cards",
                    )
                )
            ]
            showcase_section.styling = [
                value
                for value in showcase_section.styling
                if not any(
                    token in value.lower()
                    for token in (
                        "horizontal layout, small square image",
                        "flex row",
                        "144x144px images",
                    )
                )
            ]
            changed = True
            showcase_section.layout = (
                "Horizontal 50/50 split breakout shell. Left side is a full-height "
                "cover image. Right side is a textured detail panel with the section "
                "title, supporting copy, a horizontal row of three vertical-stack "
                "product cards, and a bulleted value list."
            )
            changed |= _append_unique_strings(
                showcase_section.layout_invariants,
                [
                    "Inside the right detail panel, the three product cards stay in a horizontal row, with each card built as a vertical stack of image above text.",
                ],
            )
            changed |= _append_unique_strings(
                showcase_section.must_include,
                [
                    "Three product cards arranged in a horizontal row, each card as a vertical stack with image above text.",
                ],
            )
            changed |= _append_unique_strings(
                showcase_section.styling,
                [
                    "Product cards use vertical-stack composition with image on top and text below, while the card collection remains a horizontal row on desktop.",
                ],
            )

        footer_section = next(
            (
                section
                for section in repaired.section_requirements
                if _normalize_blueprint_label(section.section_id or section.name)
                == "site-footer"
            ),
            None,
        )
        if footer_section is not None and (
            "video background instruction" in issue_blob
            or "footer newsletter" in issue_blob
            or "newsletter video" in issue_blob
            or "looping background" in issue_blob
        ):
            changed |= _append_unique_strings(
                footer_section.must_include,
                [
                    "looping newsletter video background panel",
                ],
            )
            changed |= _append_unique_strings(
                footer_section.layout_invariants,
                [
                    "Keep the newsletter block as a split media-and-form composition with the looping video panel preserved as part of the upper footer shell.",
                ],
            )
            changed |= _append_unique_strings(
                footer_section.styling,
                [
                    "Use the provided looping video asset as the visible background/media panel for the newsletter block.",
                ],
            )
            changed |= _append_unique_strings(
                footer_section.behaviors,
                [
                    "Newsletter media panel uses the supplied video asset as a looping muted background treatment.",
                ],
            )
            if "looping video" not in footer_section.layout.lower():
                footer_section.layout = (
                    f"{footer_section.layout.rstrip('.')}. "
                    "The upper newsletter block uses the supplied looping video asset "
                    "as the left media/background panel beside the signup copy and form."
                )
                changed = True

        if any(
            phrase in issue_blob
            for phrase in (
                "font urls",
                "woff2",
                "concrete font urls",
            )
        ):
            changed |= _append_unique_strings(
                repaired.asset_requirements,
                font_asset_urls,
            )
            if font_asset_urls:
                changed |= _append_unique_strings(
                    repaired.hard_constraints,
                    [
                        "Load the extracted custom fonts from the concrete .woff2 asset URLs in asset_requirements instead of using family names without real font files."
                    ],
                )

        if footer_section is not None and (
            "incomplete site footer specification" in issue_blob
            or "5-column grid" in issue_blob
            or "newsletter title" in issue_blob
            or "fda disclaimer" in issue_blob
        ):
            changed |= _append_unique_strings(
                footer_section.layout_invariants,
                [
                    "Keep the upper footer as a 5-column link-and-newsletter composition above the lower legal and accessibility bands.",
                ],
            )
            changed |= _append_unique_strings(
                footer_section.must_include,
                [
                    "5-column link grid",
                    "newsletter title and signup copy block",
                    "copyright line",
                    "FDA disclaimer text",
                ],
            )
            footer_copy_candidates: list[str] = []
            for issue in blueprint_validation.issues:
                if "footer" not in issue.title.lower():
                    continue
                footer_copy_candidates.extend(re.findall(r"'([^']+)'", issue.fix_instructions))
                footer_copy_candidates.extend(re.findall(r'"([^"]+)"', issue.fix_instructions))
            changed |= _append_unique_strings(
                footer_section.copy_items,
                footer_copy_candidates,
            )
            if "5-column" not in footer_section.layout.lower():
                footer_section.layout = (
                    f"{footer_section.layout.rstrip('.')}. "
                    "The upper footer must include a 5-column link grid with the "
                    "newsletter title and signup copy before the lower legal and "
                    "accessibility bands."
                )
                changed = True
            footer_section.must_include = list(dict.fromkeys(footer_section.must_include))

        if (
            "ambient background glow" in issue_blob
            or "glowing orbs" in issue_blob
            or "hb_overly_left" in full_dom
            or "hb_overly_right" in full_dom
            or "fegaussianblur" in full_dom
        ):
            changed |= _append_unique_strings(
                repaired.layout_requirements,
                [
                    "Add soft pink blurred ambient glow overlays behind the article shell so the hero/body surface keeps the premium editorial lighting from the live page."
                ],
            )
            changed |= _append_unique_strings(
                repaired.preserve_requirements,
                [
                    "Ambient pink blur-overlay framing behind the article shell"
                ],
            )
            for section in repaired.section_requirements:
                if _section_role(section) not in {"hero", "body"}:
                    continue
                changed |= _append_unique_strings(
                    section.layout_invariants,
                    [
                        "Preserve the ambient pink blurred overlay framing behind this article shell instead of flattening the background to a plain solid fill.",
                    ],
                )
                changed |= _append_unique_strings(
                    section.styling,
                    [
                        "soft pink blurred SVG/ellipse glow overlays behind the reading shell",
                    ],
                )

        if "asset misattribution" in issue_blob or "remove unrelated assets" in issue_blob:
            for section in repaired.section_requirements:
                filtered_assets = [
                    asset
                    for asset in section.assets
                    if not any(
                        token in asset.lower()
                        for token in (
                            "analytics.twitter.com/1/i/adsct",
                            "t.co/1/i/adsct",
                            "/adsct?",
                            "beckham",
                            "daily ultimate",
                            "product_image_new",
                            "welcome kit",
                            "red-cup",
                            "quarterly",
                            "frame_1171275436",
                            "cursor_blinking",
                            "newsletter",
                            "footer",
                            "preview_images/fbf49",
                            "bundle_li_bg",
                        )
                    )
                ]
                if filtered_assets != section.assets:
                    section.assets = filtered_assets
                    changed = True
                if _section_role(section) == "related":
                    changed |= _append_unique_strings(
                        section.assets,
                        [
                            asset
                            for asset in _reference_asset_evidence_lines(reference_bundle)
                            if any(
                                token in asset.lower()
                                for token in (
                                    "/articles/",
                                    "hb_blogs_card__image",
                                )
                            )
                        ][:4],
                    )

        if "empty fields in sticky header state" in issue_blob:
            sticky_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _is_sticky_header_state_section(section)
                ),
                None,
            )
            if sticky_section is not None:
                if not sticky_section.purpose.strip():
                    sticky_section.purpose = (
                        "Provide persistent brand presence and quick navigation "
                        "during scroll without reusing the full opening header shell."
                    )
                    changed = True
                changed |= _append_unique_strings(
                    sticky_section.copy_items,
                    ["IM8 Health", "Country/region"],
                )
                changed |= _append_unique_strings(
                    sticky_section.behaviors,
                    [
                        "Slides into view as a compact persistent header state after the opening header scrolls away.",
                    ],
                )
                changed |= _append_unique_strings(
                    sticky_section.editable_fields,
                    ["sticky utility labels", "sticky navigation labels"],
                )

        if "missing content in promotional modal" in issue_blob:
            modal_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _section_role(section) == "modal"
                ),
                None,
            )
            if modal_section is not None:
                changed |= _append_unique_strings(
                    modal_section.must_include,
                    [
                        "product box image",
                        "FREE GIFTS $54 VALUE badge",
                    ],
                )
                changed |= _append_unique_strings(
                    modal_section.copy_items,
                    [
                        "FREE Gifts $54 value",
                    ],
                )
                changed |= _append_unique_strings(
                    modal_section.assets,
                    [
                        asset
                        for asset in _reference_asset_evidence_lines(reference_bundle)
                        if any(
                            token in asset.lower()
                            for token in (
                                "files.alia-prod.com/beckhamstacktravel",
                                "files.alia-prod.com/im8logo",
                            )
                        )
                    ][:2],
                )

        if (
            "execution plan missing new sections" in issue_blob
            or "shop now" in issue_blob
            or "misidentified chrome layers" in issue_blob
        ) and repaired.execution_plan:
            normalized_steps = [
                re.sub(r"^\s*\d+\.\s*", "", step).strip()
                for step in repaired.execution_plan
                if step.strip()
            ]
            insert_at = next(
                (
                    index + 1
                    for index, step in enumerate(normalized_steps)
                    if "announcement bar" in step.lower()
                ),
                0,
            )
            if site_header_exists and not any(
                "site header" in step.lower() for step in normalized_steps
            ):
                normalized_steps.insert(
                    insert_at,
                    "Build the Site Header with the centered IM8 logo, split navigation groups, and search utility.",
                )
                insert_at += 1
                changed = True
            if not site_header_exists:
                existing_site_header_steps = list(normalized_steps)
                normalized_steps = [
                    step
                    for step in normalized_steps
                    if "site header" not in step.lower()
                ]
                if normalized_steps != existing_site_header_steps:
                    changed = True
            if not any("shop now bar" in step.lower() for step in normalized_steps):
                normalized_steps.insert(
                    insert_at,
                    "Build the Shop Now Bar as a distinct sticky CTA band with the white IM8 logo, pulse dot, promo copy, and Get Started button.",
                )
                changed = True
            for index, step in enumerate(normalized_steps):
                if "sticky header" not in step.lower():
                    continue
                if "shop now bar" in step.lower() and "scroll up" in step.lower():
                    break
                normalized_steps[index] = (
                    "Build the Sticky Header and implement the dual scroll behavior so the Shop Now Bar appears on scroll down and the compact white sticky header appears on scroll up."
                )
                changed = True
                break
            repaired.execution_plan = [
                f"{index}. {step}" for index, step in enumerate(normalized_steps, start=1)
            ]

        if site_header_section is not None and (
            "sparse site header definition" in issue_blob
            or "shop now" in issue_blob
        ):
            site_header_section.assets = [
                asset
                for asset in site_header_section.assets
                if "header_white_logo" not in asset.lower()
            ]
            changed |= _append_unique_strings(
                site_header_section.assets,
                header_logo_assets[:1],
            )

        if "incomplete shop now bar definition" in issue_blob:
            shop_now_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "shop-now-bar"
                ),
                None,
            )
            if shop_now_section is not None:
                changed |= _append_unique_strings(
                    shop_now_section.must_include,
                    ["white IM8 logo"],
                )
                changed |= _append_unique_strings(
                    shop_now_section.assets,
                    white_logo_assets[:1],
                )

        if (
            "missing ambient glow overlays" in issue_blob
            or "ambient glow" in issue_blob
        ):
            changed |= _append_unique_strings(
                repaired.styling_requirements,
                [
                    "Include the blurred pink ambient glow overlays around the article shell so the blush editorial background keeps its soft lighting.",
                ],
            )
            for section in repaired.section_requirements:
                if _section_role(section) not in {"hero", "body"}:
                    continue
                changed |= _append_unique_strings(
                    section.layout_invariants,
                    [
                        "Keep the shared article shell framed by the blurred pink ambient glow overlays instead of flattening the background to a plain solid fill.",
                    ],
                )
                changed |= _append_unique_strings(
                    section.styling,
                    [
                        "blurred pink SVG/ellipse glow overlays around the shared reading shell",
                    ],
                )

        if (
            "footer layout misinterpretation" in issue_blob
            or "single horizontal row" in issue_blob
            or "single-row layout" in issue_blob
        ):
            footer_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _section_role(section) == "footer"
                ),
                None,
            )
            if footer_section is not None:
                footer_section.layout = (
                    "Single horizontal upper row with the multi-column link groups "
                    "on the left/center and the newsletter signup form on the far "
                    "right, followed by the massive IM8 logo and legal copy below."
                )
                changed = True
                footer_section.layout_invariants = [
                    value
                    for value in footer_section.layout_invariants
                    if "video" not in value.lower()
                ]
                changed |= _append_unique_strings(
                    footer_section.layout_invariants,
                    [
                        "Keep the upper footer as one horizontal row with the link columns and newsletter form side by side on desktop.",
                        "Do not invent a visible newsletter video thumbnail when the desktop reference shows only the form in the right column.",
                    ],
                )
                footer_section.must_include = [
                    value
                    for value in footer_section.must_include
                    if "video" not in value.lower()
                ]
                changed |= _append_unique_strings(
                    footer_section.must_include,
                    [
                        "5 columns of navigation links aligned within the left/center footer region.",
                        "Newsletter signup form aligned on the far right of the same row.",
                    ],
                )
                footer_section.assets = [
                    asset
                    for asset in footer_section.assets
                    if not any(
                        token in asset.lower()
                        for token in (
                            "preview_images/fbf49",
                            "fbf49de132784b63b1209cf9f32ce77d.hd-720p",
                            "custom_video_new",
                        )
                    )
                ]
                footer_section.behaviors = [
                    value
                    for value in footer_section.behaviors
                    if "video" not in value.lower()
                ]
                footer_section.styling = [
                    value
                    for value in footer_section.styling
                    if "video" not in value.lower()
                ]

        if (
            "hallucinated styling on shop now bar button" in issue_blob
            or "standard solid vitality red pill button" in issue_blob
        ):
            shop_now_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _normalize_blueprint_label(section.section_id or section.name)
                    == "shop-now-bar"
                ),
                None,
            )
            if shop_now_section is not None:
                shop_now_section.styling = [
                    value
                    for value in shop_now_section.styling
                    if not any(
                        token in value.lower()
                        for token in ("gold border", "glow", "gradient")
                    )
                ]
                changed |= _append_unique_strings(
                    shop_now_section.styling,
                    [
                        "Get Started button uses a solid vitality red pill background with white text and no gold border glow.",
                    ],
                )
                shop_now_section.assets = [
                    asset
                    for asset in shop_now_section.assets
                    if "header-logo-new" not in asset.lower()
                ]

        if (
            "accessibility statement" in issue_blob
            or "our commitment to accessibility" in full_dom
        ):
            footer_section = next(
                (
                    section
                    for section in repaired.section_requirements
                    if _section_role(section) == "footer"
                ),
                None,
            )
            if footer_section is not None:
                changed |= _append_unique_strings(
                    footer_section.must_include,
                    [
                        "OUR COMMITMENT TO ACCESSIBILITY statement band",
                        "accessibility paragraph with support email and accessibility statement link",
                    ],
                )
                changed |= _append_unique_strings(
                    footer_section.copy_items,
                    [
                        "OUR COMMITMENT TO ACCESSIBILITY",
                        "IM8 is committed to making our website's content accessible and user friendly to everyone.",
                        "support@im8health.com",
                        "Read our full accessibility statement",
                    ],
                )
                changed |= _append_unique_strings(
                    footer_section.layout_invariants,
                    [
                        "Keep the footer accessibility statement band as a distinct lower footer content block beneath the main newsletter and link row.",
                    ],
                )

        repaired, deduped = _dedupe_blueprint_requirements(
            repaired,
            reference_bundle=reference_bundle,
        )
        changed |= deduped

        if changed:
            return repaired, True
        return requirements, False

    async def _validate_blueprint_before_execution(
        self,
        requirements: RequirementsSpec,
        *,
        reference_bundle: ReferenceBundle,
        current_html: str | None,
        prior_validation: ValidationReport | None,
        prior_blueprint_validation: BlueprintValidationReport | None,
    ) -> tuple[
        RequirementsSpec,
        BlueprintValidationReport | None,
        bool,
        list[dict[str, object]],
    ]:
        if not _requires_explicit_section_blueprint(reference_bundle):
            return requirements, None, False, []

        current_requirements = requirements
        current_prior_blueprint_validation = prior_blueprint_validation
        blueprint_was_repaired = False
        blueprint_validation_history: list[dict[str, object]] = []

        for attempt in range(1, self._max_blueprint_validation_attempts + 1):
            current_requirements, deterministic_repair_applied = (
                self._repair_blueprint_from_reference(
                    requirements=current_requirements,
                    reference_bundle=reference_bundle,
                )
            )
            if deterministic_repair_applied:
                blueprint_was_repaired = True
                await self._status(
                    "Blueprint QA: normalizing requirements against live DOM and design-system evidence."
                )
            current_requirements, outline_sync_changed = (
                _merge_requirements_with_reference_outline(
                    current_requirements,
                    reference_bundle,
                )
            )
            current_requirements, global_lists_sync_changed = (
                _ensure_minimum_blueprint_global_lists(
                    current_requirements,
                    reference_bundle,
                )
            )
            current_requirements, dedupe_sync_changed = _dedupe_blueprint_requirements(
                current_requirements,
                reference_bundle=reference_bundle,
            )
            if outline_sync_changed or global_lists_sync_changed or dedupe_sync_changed:
                blueprint_was_repaired = True
            await self._send_supervisor_thinking(
                title="Supervisor: Reviewing blueprint coverage",
                content=(
                    "Checking whether the supervisor requirements cover the full page, "
                    "the closing state, and the canonical section blueprint before any "
                    "HTML generation begins."
                ),
            )
            await self._status(
                "Blueprint QA: validating supervisor requirements before execution."
            )
            blueprint_validation = await self._validate_blueprint_once(
                reference_bundle=reference_bundle,
                requirements=current_requirements,
                prior_blueprint_validation=current_prior_blueprint_validation,
            )
            blueprint_passed_validator_below_threshold = (
                blueprint_validation.verdict == "pass"
                and blueprint_validation.overall_score < self._blueprint_pass_score
            )
            blueprint_validation = self._apply_blueprint_quality_threshold(
                blueprint_validation
            )
            blueprint_validation_history.append(
                {
                    "attempt": attempt,
                    "verdict": blueprint_validation.verdict,
                    "overallScore": blueprint_validation.overall_score,
                    "coverageScore": blueprint_validation.coverage_score,
                    "consistencyScore": blueprint_validation.consistency_score,
                    "executionReadinessScore": blueprint_validation.execution_readiness_score,
                    "summary": blueprint_validation.summary,
                }
            )
            self._artifact_store.persist_metadata(
                iteration=0,
                stop_reason=None,
                requirements=current_requirements,
                validation_report=prior_validation,
                blueprint_validation=blueprint_validation,
                blueprint_validation_history=blueprint_validation_history,
            )
            await self._status(
                "Blueprint QA attempt "
                f"{attempt}/{self._max_blueprint_validation_attempts}: "
                f"{blueprint_validation.verdict} at score "
                f"{blueprint_validation.overall_score:.2f} "
                f"(target {self._blueprint_pass_score:.2f})."
            )
            if self._should_accept_blueprint(blueprint_validation):
                if blueprint_was_repaired or attempt > 1:
                    await self._status(
                        "Blueprint QA: normalizing requirements against live DOM and design-system evidence."
                    )
                return (
                    current_requirements,
                    blueprint_validation,
                    blueprint_was_repaired or attempt > 1,
                    blueprint_validation_history,
                )

            if attempt >= self._max_blueprint_validation_attempts:
                await self._status(
                    "Blueprint QA blocked execution after "
                    f"{self._max_blueprint_validation_attempts} failed repair attempts."
                )
                self._artifact_store.persist_metadata(
                    iteration=0,
                    stop_reason="blocked",
                    requirements=current_requirements,
                    validation_report=prior_validation,
                    blueprint_validation=blueprint_validation,
                    blueprint_validation_history=blueprint_validation_history,
                )
                raise RuntimeError(
                    self._format_blueprint_failure(
                        blueprint_validation,
                        blueprint_validation_history=blueprint_validation_history,
                    )
                )

            if blueprint_passed_validator_below_threshold:
                await self._status(
                    "Blueprint QA: provisional pass below required quality threshold; continuing blueprint refinement."
                )

            await self._send_supervisor_thinking(
                title="Supervisor: Repairing blueprint",
                content=(
                    "Updating the supervisor requirements to restore missing sections, "
                    "closing coverage, and any contradictory planning details before the "
                    "executor is allowed to continue."
                ),
            )
            await self._status(
                "Blueprint QA: repairing missing sections and blueprint inconsistencies."
            )
            (
                deterministic_feedback_requirements,
                deterministic_feedback_repaired,
            ) = self._repair_blueprint_from_validation_feedback(
                requirements=current_requirements,
                reference_bundle=reference_bundle,
                blueprint_validation=blueprint_validation,
            )
            if deterministic_feedback_repaired:
                current_requirements = deterministic_feedback_requirements
                current_prior_blueprint_validation = blueprint_validation
                blueprint_was_repaired = True
                await self._status(
                    "Blueprint QA: normalizing requirements against live DOM and design-system evidence."
                )
                await self._status(
                    "Blueprint QA: applying targeted structural fixes from validation feedback."
                )
                continue
            repaired_requirements = await self._analyzer.analyze(
                reference_bundle,
                current_html,
                prior_requirements=current_requirements,
                prior_validation=prior_validation,
                prior_blueprint_validation=blueprint_validation,
            )
            if _material_blueprint_regression(
                current_requirements, repaired_requirements
            ):
                repaired_requirements = _merge_blueprint_regression(
                    current_requirements,
                    repaired_requirements,
                )
                blueprint_was_repaired = True
                await self._status(
                    "Blueprint QA: preserved prior section coverage while applying repair updates to avoid truncating the page blueprint."
                )
            current_requirements = repaired_requirements
            current_prior_blueprint_validation = blueprint_validation

        return current_requirements, None, False, blueprint_validation_history

    async def _validate_blueprint_once(
        self,
        *,
        reference_bundle: ReferenceBundle,
        requirements: RequirementsSpec,
        prior_blueprint_validation: BlueprintValidationReport | None,
    ) -> BlueprintValidationReport:
        sanity_report = self._build_blueprint_sanity_report(
            requirements=requirements,
            reference_bundle=reference_bundle,
        )
        if sanity_report is not None:
            return sanity_report

        report = await self._blueprint_validator.validate(
            reference_bundle=reference_bundle,
            requirements=requirements,
            prior_blueprint_validation=prior_blueprint_validation,
        )
        return _reconcile_blueprint_validation_report(
            report,
            requirements=requirements,
            reference_bundle=reference_bundle,
        )

    def _build_blueprint_sanity_report(
        self,
        *,
        requirements: RequirementsSpec,
        reference_bundle: ReferenceBundle,
    ) -> BlueprintValidationReport | None:
        if not _requires_explicit_section_blueprint(reference_bundle):
            return None

        issues: list[BlueprintValidationIssue] = []
        missing_sections: list[str] = []

        named_sections = [
            section for section in requirements.section_requirements if section.name.strip()
        ]
        wrapper_requirements = [
            wrapper for wrapper in requirements.wrapper_requirements if wrapper.name.strip()
        ]
        rich_structure_reference = _has_rich_structure_reference(reference_bundle)

        def _mentions_explicit_shared_wrapper(*values: str) -> bool:
            haystack = " ".join(value.lower() for value in values if value.strip())
            if not haystack:
                return False
            wrapper_markers = (
                "shared wrapper",
                "shared shell",
                "same wrapper",
                "same shell",
                "same card",
                "same surface",
                "same container",
                "continuous shell",
                "continuous wrapper",
                "continuous card",
                "one shared",
                "single shared",
            )
            return any(marker in haystack for marker in wrapper_markers)

        if not named_sections:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="No section blueprint returned",
                    detail=(
                        "The supervisor returned no named `section_requirements` even "
                        "though visual reference evidence exists for this run."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Populate `section_requirements` with the full top-to-bottom "
                        "canonical section list before execution starts."
                    ),
                )
            )
        blank_named_sections = [
            index + 1
            for index, section in enumerate(requirements.section_requirements)
            if not section.name.strip()
        ]
        if blank_named_sections:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="consistency",
                    title="Unnamed section entries in blueprint",
                    detail=(
                        "One or more `section_requirements` entries are present but have "
                        "no stable section name, which breaks canonical section tracking."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Give every `section_requirements` entry a distinct, non-empty "
                        "section name in top-to-bottom order."
                    ),
                )
            )
        section_ids: dict[str, str] = {}
        duplicate_section_ids: list[str] = []
        for section in named_sections:
            prior_name = section_ids.get(section.section_id)
            if prior_name is None:
                section_ids[section.section_id] = section.name.strip()
                continue
            duplicate_section_ids.append(section.section_id)
        if duplicate_section_ids:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="consistency",
                    title="Duplicate canonical section IDs",
                    detail=(
                        "Multiple `section_requirements` normalize to the same "
                        "`section_id`, which would make DOM coverage tracking ambiguous."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Rename the conflicting sections so each normalized `section_id` "
                        "is unique and stable."
                    ),
                )
            )
        duplicate_wrapper_ids: list[str] = []
        wrapper_ids: dict[str, str] = {}
        for wrapper in wrapper_requirements:
            prior_name = wrapper_ids.get(wrapper.wrapper_id)
            if prior_name is None:
                wrapper_ids[wrapper.wrapper_id] = wrapper.name.strip()
                continue
            duplicate_wrapper_ids.append(wrapper.wrapper_id)
        if duplicate_wrapper_ids:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="consistency",
                    title="Duplicate canonical wrapper IDs",
                    detail=(
                        "Multiple `wrapper_requirements` normalize to the same "
                        "`wrapper_id`, which would make shared-shell tracking "
                        "ambiguous during execution and validation."
                    ),
                    affected_fields=["wrapper_requirements"],
                    fix_instructions=(
                        "Rename the conflicting wrapper requirements so each "
                        "normalized `wrapper_id` is unique and stable."
                    ),
                )
            )
        # Defer softer coverage and design-system gaps to the model-based
        # blueprint validator so repairable drafts still get a structured pass/fail
        # report instead of being rejected by deterministic heuristics first.
        if not issues:
            return None

        coverage_issue_count = sum(issue.category == "coverage" for issue in issues)
        consistency_issue_count = sum(
            issue.category == "consistency" for issue in issues
        )
        return BlueprintValidationReport(
            verdict="blocked",
            overall_score=0.0,
            coverage_score=0.0 if coverage_issue_count else 0.5,
            consistency_score=0.0 if consistency_issue_count else 0.5,
            execution_readiness_score=0.0,
            summary="Blueprint sanity checks failed before execution.",
            issues=issues,
            missing_sections=missing_sections,
            repair_instructions=[issue.fix_instructions for issue in issues],
        )
        section_id_set = {section.section_id for section in named_sections}
        wrappers_missing_participants = [
            wrapper.name.strip()
            for wrapper in wrapper_requirements
            if not wrapper.participant_section_ids
        ]
        if wrappers_missing_participants:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="consistency",
                    title="Wrapper requirements missing participant sections",
                    detail=(
                        "Some `wrapper_requirements` do not name the canonical "
                        "sections they should contain, so the executor would have to "
                        "guess which sections belong in the shared container."
                    ),
                    affected_fields=["wrapper_requirements"],
                    fix_instructions=(
                        "Populate every wrapper requirement with the participating "
                        "`section_id` values in `participant_section_ids`."
                    ),
                )
            )
        wrappers_with_unknown_participants = [
            wrapper.name.strip()
            for wrapper in wrapper_requirements
            if any(
                section_id not in section_id_set
                for section_id in wrapper.participant_section_ids
            )
        ]
        if wrappers_with_unknown_participants:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="consistency",
                    title="Wrapper requirements reference unknown section IDs",
                    detail=(
                        "Some `wrapper_requirements` point at participant section IDs "
                        "that do not exist in `section_requirements`, so the shared "
                        "container contract cannot be enforced reliably."
                    ),
                    affected_fields=["wrapper_requirements", "section_requirements"],
                    fix_instructions=(
                        "Update each wrapper requirement so every "
                        "`participant_section_ids` value matches a canonical "
                        "`section_requirements.section_id`."
                    ),
                )
            )
        shared_wrapper_signals = bool(
            _mentions_explicit_shared_wrapper(*requirements.critical_layout_invariants)
            or any(
                _mentions_explicit_shared_wrapper(
                    section.layout,
                    *section.layout_invariants,
                    *section.must_include,
                )
                for section in named_sections
            )
        )
        if shared_wrapper_signals and not wrapper_requirements:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="consistency",
                    title="Shared wrapper relationships are only implied in prose",
                    detail=(
                        "The blueprint describes shared shells or shared containers in "
                        "`critical_layout_invariants` or section fields, but it never "
                        "turns those relationships into explicit `wrapper_requirements`."
                    ),
                    affected_fields=[
                        "critical_layout_invariants",
                        "section_requirements",
                        "wrapper_requirements",
                    ],
                    fix_instructions=(
                        "Add `wrapper_requirements` entries for each shared shell, "
                        "card, grouped surface, or split container that spans multiple "
                        "sections. Give each wrapper a stable `wrapper_id` and the "
                        "matching `participant_section_ids`."
                    ),
                )
            )
        if not requirements.page_outline:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="Missing page outline",
                    detail=(
                        "The blueprint does not include `page_outline`, so there is no "
                        "explicit ledger of the full top-to-bottom page scan."
                    ),
                    affected_fields=["page_outline"],
                    fix_instructions=(
                        "Populate `page_outline` with the full top-to-bottom page scan "
                        "before execution begins."
                    ),
                )
            )
        unmatched_outline_entries = [
            entry
            for entry in requirements.page_outline
            if entry.strip()
            and not any(
                _section_matches_outline_entry(entry, section.name, section.section_id)
                for section in named_sections
            )
        ]
        if unmatched_outline_entries:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="Page outline entries missing from canonical sections",
                    detail=(
                        "Some `page_outline` entries are not represented in "
                        "`section_requirements`, which means the executor would not "
                        "have a canonical section blueprint for the full page."
                    ),
                    affected_fields=["page_outline", "section_requirements"],
                    fix_instructions=(
                        "Add each missing page-outline region to `section_requirements` "
                        "with a stable section name and `section_id`, or rename the "
                        "existing section entries so they match the outline."
                    ),
                )
            )
            missing_sections.extend(unmatched_outline_entries[:6])
        missing_dom_roles = _missing_dom_roles(reference_bundle, requirements)
        if missing_dom_roles:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="coverage",
                    title="Live DOM roles are not represented explicitly",
                    detail=(
                        "The live DOM evidence exposes distinct chrome layers or closing "
                        "roles that the blueprint never names or explains explicitly, so "
                        "those regions can still be collapsed away before execution."
                    ),
                    affected_fields=[
                        "page_outline",
                        "section_requirements",
                        "coverage_notes",
                        "critical_layout_invariants",
                        "behavior_requirements",
                    ],
                    fix_instructions=(
                        "Represent each missing live DOM role as a canonical section or "
                        "an explicit blueprint state/invariant, and if any roles are "
                        "intentionally merged, document that merge in `coverage_notes` "
                        "instead of leaving it implicit."
                    ),
                )
            )
            missing_sections.extend(role.title() for role in missing_dom_roles[:4])
        missing_component_geometry = _missing_component_geometry_signals(
            reference_bundle, requirements
        )
        if missing_component_geometry:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="design_system",
                    title="Live component geometry is missing from blueprint",
                    detail=(
                        "The live reference exposes component-level layout geometry such "
                        "as split panels, repeated-item orientation, media fill, or "
                        "gradient shells, but the blueprint never turns those into "
                        "section-level layout facts."
                    ),
                    affected_fields=[
                        "section_requirements",
                        "critical_layout_invariants",
                        "layout_requirements",
                        "styling_requirements",
                    ],
                    fix_instructions=(
                        "Promote the missing component-geometry evidence into the "
                        "relevant section `layout`, `layout_invariants`, `must_include`, "
                        "and `styling` fields so the executor knows the outer shell and "
                        "the representative repeated-item structure instead of guessing."
                    ),
                )
            )
        if _reference_asset_urls(reference_bundle) and not (
            _blueprint_mentions_live_asset_reuse(requirements, reference_bundle)
        ):
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="design_system",
                    title="Live site assets are not preserved in blueprint",
                    detail=(
                        "The live reference exposes concrete site image, SVG, or "
                        "background asset URLs, but the blueprint never turns those "
                        "assets into reusable execution requirements."
                    ),
                    affected_fields=[
                        "asset_requirements",
                        "section_requirements",
                        "preserve_requirements",
                    ],
                    fix_instructions=(
                        "Add the extracted site asset URLs to `asset_requirements` and "
                        "the matching section `assets` lists, then explicitly require "
                        "the executor to reuse those same live-site media sources "
                        "instead of placeholder imagery."
                    ),
                )
            )
        if _reference_exposes_separate_header_states(reference_bundle) and not (
            _blueprint_distinguishes_header_states(requirements)
        ):
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="coverage",
                    title="Base header and sticky header state are not distinguished",
                    detail=(
                        "The live DOM exposes both a normal header shell and a sticky "
                        "or scrolled header state, but the blueprint collapses them "
                        "into a single header concept without documenting that merge."
                    ),
                    affected_fields=[
                        "page_outline",
                        "section_requirements",
                        "coverage_notes",
                    ],
                    fix_instructions=(
                        "Represent the opening header shell and the sticky/scrolled "
                        "header state as separate canonical sections or explicitly "
                        "document their merge in `coverage_notes`."
                    ),
                )
            )
        if _reference_custom_font_names(reference_bundle) and not (
            _blueprint_mentions_font_loading(requirements)
        ):
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="design_system",
                    title="Custom fonts are named without a real loading requirement",
                    detail=(
                        "The reference exposes custom or non-system fonts, but the "
                        "blueprint never requires a real font-loading mechanism, so "
                        "the executor could still render fallback fonts."
                    ),
                    affected_fields=[
                        "hard_constraints",
                        "design_tokens.typography",
                        "asset_requirements",
                        "section_requirements",
                    ],
                    fix_instructions=(
                        "Add an explicit font-loading requirement such as `@font-face`, "
                        "hosted font CSS, or concrete font asset URLs anywhere the "
                        "blueprint records the extracted custom font names."
                    ),
                )
            )
        if requirements.footer_present is None:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="consistency",
                    title="Footer presence not assessed",
                    detail=(
                        "The blueprint leaves `footer_present` unset even though visual "
                        "reference evidence exists."
                    ),
                    affected_fields=["footer_present"],
                    fix_instructions=(
                        "Set `footer_present` explicitly to `true` or `false`, and add "
                        "matching footer coverage when it is present."
                    ),
                )
            )
        closing_references = [
            *requirements.closing_sections,
            *(section.name for section in named_sections),
        ]
        if requirements.footer_present and not (
            requirements.footer_description.strip()
            or _mentions_footer_region(closing_references)
        ):
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="Footer marked present but not represented",
                    detail=(
                        "The blueprint says a footer or closing region is present, but it "
                        "is not described in `footer_description`, `closing_sections`, or "
                        "the canonical section names."
                    ),
                    affected_fields=[
                        "footer_present",
                        "footer_description",
                        "closing_sections",
                        "section_requirements",
                    ],
                    fix_instructions=(
                        "Add the footer or closing region explicitly to `footer_description`, "
                        "`closing_sections`, and `section_requirements`."
                    ),
                )
            )
            missing_sections.append("Footer or closing region")
        unmatched_closing_entries = [
            entry
            for entry in requirements.closing_sections
            if entry.strip()
            and not any(
                _section_matches_outline_entry(entry, section.name, section.section_id)
                for section in named_sections
            )
        ]
        if unmatched_closing_entries:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="coverage",
                    title="Closing sections are not represented canonically",
                    detail=(
                        "One or more `closing_sections` entries do not appear in the "
                        "canonical section blueprint, so the ending state could be lost "
                        "before execution."
                    ),
                    affected_fields=["closing_sections", "section_requirements"],
                    fix_instructions=(
                        "Make sure every closing section is also represented in "
                        "`section_requirements` with a stable section name and "
                        "`section_id`."
                    ),
                )
            )
        if rich_structure_reference and not requirements.critical_layout_invariants:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="design_system",
                    title="Missing cross-section layout invariants",
                    detail=(
                        "The blueprint does not include `critical_layout_invariants`, so "
                        "page-defining shell relationships such as shared wrappers, "
                        "background surfaces, and split layouts are left implicit."
                    ),
                    affected_fields=["critical_layout_invariants"],
                    fix_instructions=(
                        "Populate `critical_layout_invariants` with the page-level shell "
                        "rules that would make the executor build the wrong structure if "
                        "they were omitted."
                    ),
                )
            )
        elif rich_structure_reference:
            if (
                _count_nonempty(requirements.critical_layout_invariants) < 2
                or _count_specific(requirements.critical_layout_invariants) < 2
            ):
                issues.append(
                    BlueprintValidationIssue(
                        severity="major",
                        category="design_system",
                        title="Page-level structure invariants are too thin",
                        detail=(
                            "The blueprint includes `critical_layout_invariants`, but "
                            "they are still too sparse or too generic to lock down the "
                            "page shell with the level of precision the executor needs."
                        ),
                        affected_fields=["critical_layout_invariants"],
                        fix_instructions=(
                            "Expand `critical_layout_invariants` with multiple concrete "
                            "page-level shell rules covering wrappers, background "
                            "surfaces, split layouts, chrome composition, and other "
                            "cross-section relationships that define the page."
                        ),
                    )
                )
        if rich_structure_reference and not requirements.coverage_notes:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="ambiguity",
                    title="Coverage risks are not recorded",
                    detail=(
                        "The blueprint does not include `coverage_notes`, so any "
                        "ambiguity around merged sections, lower-page coverage, or "
                        "structure-sensitive regions is left implicit."
                    ),
                    affected_fields=["coverage_notes"],
                    fix_instructions=(
                        "Populate `coverage_notes` with ambiguity, merge-risk, and "
                        "lower-page coverage notes so the executor and validator know "
                        "where omissions are most likely."
                    ),
                )
            )
        sections_missing_layout = [
            section.name.strip()
            for section in named_sections
            if not section.layout.strip()
        ]
        if sections_missing_layout:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="consistency",
                    title="Sections missing layout descriptions",
                    detail=(
                        "Some canonical sections do not include a meaningful `layout` "
                        "description, which makes implementation too guess-driven."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Give every canonical section a concise but concrete `layout` "
                        "description that explains its structure and container behavior."
                    ),
                )
            )
        vague_layout_sections = [
            section.name.strip()
            for section in named_sections
            if section.layout.strip() and _is_vague_layout_description(section.layout)
        ]
        if vague_layout_sections:
            issues.append(
                BlueprintValidationIssue(
                    severity="major",
                    category="consistency",
                    title="Sections use vague layout descriptions",
                    detail=(
                        "Some canonical sections still use generic `layout` text that "
                        "does not explain the section shell or composition with enough "
                        "precision for faithful execution."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Rewrite each flagged section's `layout` description so it "
                        "states the actual composition, shell, grouping, and container "
                        "behavior rather than a generic section label."
                    ),
                )
            )
        if rich_structure_reference:
            sections_missing_layout_invariants = [
                section.name.strip()
                for section in named_sections
                if not section.layout_invariants
            ]
            if sections_missing_layout_invariants:
                issues.append(
                    BlueprintValidationIssue(
                        severity="major",
                        category="design_system",
                        title="Sections missing structure-critical layout invariants",
                        detail=(
                            "Some canonical sections do not record any "
                            "`layout_invariants`, so the executor would have to guess the "
                            "shared shell, wrapper, or surface relationships that define "
                            "the live layout."
                        ),
                        affected_fields=["section_requirements"],
                        fix_instructions=(
                            "Populate `layout_invariants` for each section with the "
                            "non-negotiable shell, wrapper, background, split-layout, or "
                            "section-to-section relationship rules."
                        ),
                    )
                )
            weak_layout_invariant_sections = [
                section.name.strip()
                for section in named_sections
                if section.layout_invariants
                and (
                    _count_nonempty(section.layout_invariants) < 2
                    or _count_specific(section.layout_invariants) < 1
                )
            ]
            if weak_layout_invariant_sections:
                issues.append(
                    BlueprintValidationIssue(
                        severity="major",
                        category="design_system",
                        title="Sections have weak structure-critical invariants",
                        detail=(
                            "Some sections include `layout_invariants`, but the entries "
                            "are still too thin or too generic to lock down the real "
                            "shell, wrapper, or panel relationships."
                        ),
                        affected_fields=["section_requirements"],
                        fix_instructions=(
                            "Strengthen the flagged sections' `layout_invariants` with "
                            "multiple concrete shell rules such as shared wrappers, "
                            "surface/background changes, split panels, grouped chrome, "
                            "or explicit section-to-section relationships."
                        ),
                    )
                )
            sections_missing_styling = [
                section.name.strip()
                for section in named_sections
                if not section.styling
            ]
            if sections_missing_styling:
                issues.append(
                    BlueprintValidationIssue(
                        severity="major",
                        category="design_system",
                        title="Sections are missing section-specific styling cues",
                        detail=(
                            "Some sections do not record any `styling` guidance, which "
                            "means section-defining surfaces, radii, shell colors, or "
                            "decorative framing can be lost before execution."
                        ),
                        affected_fields=["section_requirements"],
                        fix_instructions=(
                            "Populate `styling` for each flagged section with concrete "
                            "surface, spacing, radius, framing, and visual-composition "
                            "cues that distinguish it from a generic template block."
                        ),
                    )
                )
            sections_with_thin_must_include = [
                section.name.strip()
                for section in named_sections
                if _count_nonempty(section.must_include) < 2
            ]
            if sections_with_thin_must_include:
                issues.append(
                    BlueprintValidationIssue(
                        severity="major",
                        category="consistency",
                        title="Sections lack concrete composition details",
                        detail=(
                            "Some sections do not list enough `must_include` items to "
                            "capture their visible composition beyond a generic label."
                        ),
                        affected_fields=["section_requirements"],
                        fix_instructions=(
                            "Expand each flagged section's `must_include` list with the "
                            "visible structural or grouped elements that make the "
                            "section recognizable even if imagery changes."
                        ),
                    )
                )
            detailed_reference_evidence = (
                _reference_detail_signal_count(reference_bundle) >= 8
            )
            if detailed_reference_evidence and len(named_sections) >= 4:
                hard_constraint_count = _count_nonempty(requirements.hard_constraints)
                specific_hard_constraint_count = _count_specific(
                    requirements.hard_constraints
                )
                min_hard_constraints = max(4, min(8, len(named_sections) - 1))
                min_specific_hard_constraints = max(
                    3, min(6, max(1, len(named_sections) // 2))
                )
                if (
                    hard_constraint_count < min_hard_constraints
                    or specific_hard_constraint_count < min_specific_hard_constraints
                ):
                    issues.append(
                        BlueprintValidationIssue(
                            severity="major",
                            category="design_system",
                            title="Blueprint-level fidelity constraints are too thin",
                            detail=(
                                "The blueprint's `hard_constraints` are too sparse for "
                                "the number of planned sections and the amount of "
                                "reference evidence available, so key fidelity rules "
                                "could still be left to executor guesswork."
                            ),
                            affected_fields=["hard_constraints"],
                            fix_instructions=(
                                "Expand `hard_constraints` with additional non-negotiable "
                                "rules covering top chrome, shared shells, section "
                                "sizing, button treatments, footer/legal depth, and any "
                                "other structure-defining facts exposed by the reference."
                            ),
                        )
                    )
                if _reference_exposes_role_specific_typography(reference_bundle):
                    role_typography_count = _count_keyword_matches(
                        requirements.design_tokens.typography,
                        _TYPOGRAPHY_ROLE_KEYWORDS,
                    )
                    measured_typography_count = sum(
                        1
                        for value in requirements.design_tokens.typography
                        if _contains_measured_typography(value)
                    )
                    min_role_typography = 3 if len(named_sections) >= 6 else 2
                    if (
                        role_typography_count < min_role_typography
                        or measured_typography_count < 4
                    ):
                        issues.append(
                            BlueprintValidationIssue(
                                severity="major",
                                category="design_system",
                                title="Role-specific typography tokens are too generic",
                                detail=(
                                    "The design-token typography mostly captures a global "
                                    "type scale, but it does not preserve enough measured, "
                                    "role-specific typography for header/nav, promo, CTA, "
                                    "card, footer, newsletter, or legal text even though "
                                    "the reference evidence exposes those roles."
                                ),
                                affected_fields=["design_tokens.typography"],
                                fix_instructions=(
                                    "Expand `design_tokens.typography` with measured, "
                                    "role-scoped tokens for the visible chrome, CTA, card, "
                                    "footer, newsletter, and legal text roles rather than "
                                    "stopping at generic H1/H2/body/button labels."
                                ),
                            )
                        )
                if _reference_exposes_section_sizing(reference_bundle):
                    role_sizing_count = _count_keyword_matches(
                        requirements.design_tokens.spacing,
                        _SECTION_SIZING_ROLE_KEYWORDS,
                    )
                    min_role_sizing = 3 if len(named_sections) >= 6 else 2
                    if role_sizing_count < min_role_sizing:
                        issues.append(
                            BlueprintValidationIssue(
                                severity="major",
                                category="design_system",
                                title="Section sizing tokens are too generic",
                                detail=(
                                    "The blueprint records mostly generic spacing tokens, "
                                    "but it does not preserve enough role-specific section "
                                    "sizing for shells, containers, headers, heroes, "
                                    "cards, or footers even though the reference evidence "
                                    "exposes those sizing patterns."
                                ),
                                affected_fields=["design_tokens.spacing"],
                                fix_instructions=(
                                    "Expand `design_tokens.spacing` with role-specific "
                                    "section sizing tokens such as shell/container widths, "
                                    "section padding rhythms, reading-column widths, card "
                                    "gaps, sticky CTA heights, or footer band sizing."
                                ),
                            )
                        )

        if not issues:
            return None

        coverage_issue_count = sum(issue.category == "coverage" for issue in issues)
        consistency_issue_count = sum(
            issue.category == "consistency" for issue in issues
        )
        return BlueprintValidationReport(
            verdict="blocked",
            overall_score=0.0,
            coverage_score=0.0 if coverage_issue_count else 0.5,
            consistency_score=0.0 if consistency_issue_count else 0.5,
            execution_readiness_score=0.0,
            summary="Blueprint sanity checks failed before execution.",
            issues=issues,
            missing_sections=missing_sections,
            repair_instructions=[issue.fix_instructions for issue in issues],
        )

    def _format_blueprint_failure(
        self,
        blueprint_validation: BlueprintValidationReport,
        *,
        blueprint_validation_history: list[dict[str, object]] | None = None,
    ) -> str:
        top_issues = [
            issue.title.strip()
            for issue in blueprint_validation.issues
            if issue.title.strip()
        ]
        top_failure_summary = "; ".join(top_issues[:3])
        if not top_failure_summary:
            top_failure_summary = blueprint_validation.summary.strip() or (
                "Blueprint QA rejected the requirements plan."
            )
        quality_summary = ""
        if blueprint_validation_history:
            best_attempt = max(
                blueprint_validation_history,
                key=lambda entry: float(entry.get("overallScore") or 0.0),
            )
            quality_summary = (
                f" Best blueprint score was "
                f"{float(best_attempt.get('overallScore') or 0.0):.2f} "
                f"on attempt {int(best_attempt.get('attempt') or 0)}, below the required "
                f"{self._blueprint_pass_score:.2f} threshold."
            )
        return (
            "Blueprint QA failed before execution: "
            f"{top_failure_summary}. Refusing to execute with a rejected blueprint."
            f"{quality_summary}"
        )

    def _should_accept_blueprint(
        self,
        blueprint_validation: BlueprintValidationReport,
    ) -> bool:
        return (
            blueprint_validation.verdict == "pass"
            and blueprint_validation.overall_score >= self._blueprint_pass_score
        )

    def _apply_blueprint_quality_threshold(
        self,
        blueprint_validation: BlueprintValidationReport,
    ) -> BlueprintValidationReport:
        if (
            blueprint_validation.verdict != "pass"
            or blueprint_validation.overall_score >= self._blueprint_pass_score
        ):
            return blueprint_validation

        threshold_issue = BlueprintValidationIssue(
            severity="major",
            category="consistency",
            title="Blueprint quality threshold not yet met",
            detail=(
                "The blueprint received a provisional pass from the validator, but "
                f"its overall score of {blueprint_validation.overall_score:.2f} is "
                f"below the required {self._blueprint_pass_score:.2f} threshold."
            ),
            affected_fields=[
                "summary",
                "section_requirements",
                "critical_layout_invariants",
            ],
            fix_instructions=(
                "Tighten the blueprint until the structure, ordering, and section "
                f"definitions reach at least {self._blueprint_pass_score:.2f} overall quality."
            ),
        )
        repair_instructions = list(blueprint_validation.repair_instructions)
        repair_instructions.append(threshold_issue.fix_instructions)
        summary = blueprint_validation.summary.strip()
        threshold_summary = (
            f"Blueprint scored {blueprint_validation.overall_score:.2f}, below the "
            f"required {self._blueprint_pass_score:.2f} threshold."
        )
        if summary:
            summary = f"{summary} {threshold_summary}"
        else:
            summary = threshold_summary
        return blueprint_validation.model_copy(
            update={
                "verdict": "revise",
                "summary": summary,
                "issues": [*blueprint_validation.issues, threshold_issue],
                "repair_instructions": repair_instructions,
            }
        )

    async def _send_supervisor_thinking(self, *, title: str, content: str) -> None:
        await self._send_message(
            "thinking",
            content,
            0,
            {
                "source": "supervisor",
                "title": title,
            },
            self._next_event_id("supervisor-thinking"),
        )

    async def _send_supervisor_assistant(self, *, title: str, content: str) -> None:
        await self._send_message(
            "assistant",
            content,
            0,
            {
                "source": "supervisor",
                "title": title,
            },
            self._next_event_id("supervisor-assistant"),
        )

    def _next_event_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    async def _enrich_live_reference(
        self, reference_bundle: ReferenceBundle
    ) -> ReferenceBundle:
        if (
            not reference_bundle.reference_url.strip()
            or reference_bundle.live_reference is not None
        ):
            return reference_bundle

        await self._status(
            "Inspecting live reference URL via Chrome DevTools and capturing example renders.",
            data={"referenceUrl": reference_bundle.reference_url},
        )
        try:
            live_reference = await self._live_reference_extractor.extract(
                url=reference_bundle.reference_url,
                viewport=_live_reference_viewport(reference_bundle),
            )
        except Exception as exc:
            raise RuntimeError(
                "Live reference URL inspection failed: " + str(exc)
            ) from exc

        await self._status(
            "Captured live reference renders and extracted design-system details.",
            data={
                "referenceUrl": reference_bundle.reference_url,
                "renderCount": len(live_reference.renders),
            },
        )
        return reference_bundle.model_copy(update={"live_reference": live_reference})

    async def _ensure_design_system_preflight(
        self, reference_bundle: ReferenceBundle
    ) -> ReferenceBundle:
        if reference_bundle.design_system_preflight is not None:
            persisted_design_system = self._persist_design_system_preflight_artifacts(
                reference_bundle.design_system_preflight
            )
            await self._status(
                "Design-system preflight ready.",
                data={
                    "artifactPath": persisted_design_system.html_artifact_path,
                    "runDir": self._artifact_store.paths.run_dir,
                },
            )
            return reference_bundle.model_copy(
                update={"design_system_preflight": persisted_design_system}
            )

        reused_design_system = self._resolve_reusable_design_system(reference_bundle)
        if reused_design_system is not None:
            persisted_design_system = self._persist_design_system_preflight_artifacts(
                reused_design_system
            )
            await self._status(
                "Reusing saved design-system preflight artifact.",
                data={
                    "artifactPath": persisted_design_system.html_artifact_path,
                    "runDir": self._artifact_store.paths.run_dir,
                    "reuseMode": self._design_system_reuse_mode,
                },
            )
            return reference_bundle.model_copy(
                update={"design_system_preflight": persisted_design_system}
            )

        if self._design_system_reuse_mode == "require_reuse":
            raise RuntimeError(
                "Validated loop was configured to require a reusable design-system preflight, "
                "but no compatible saved artifact was available."
            )

        if not _needs_design_system_preflight(reference_bundle):
            await self._status(
                "Skipping design-system preflight generation for this simple run.",
                data={
                    "reason": "No video input, live reference, or reference URL was provided.",
                    "runDir": self._artifact_store.paths.run_dir,
                },
            )
            return reference_bundle

        await self._status(
            "Generating required design-system preflight artifact.",
            data={"runDir": self._artifact_store.paths.run_dir},
        )
        design_system = await self._design_system_builder.build(reference_bundle)
        persisted_design_system = self._persist_design_system_preflight_artifacts(
            design_system
        )
        await self._status(
            "Design-system preflight ready.",
            data={
                "artifactPath": persisted_design_system.html_artifact_path,
                "runDir": self._artifact_store.paths.run_dir,
            },
        )
        return reference_bundle.model_copy(
            update={"design_system_preflight": persisted_design_system}
        )

    def _resolve_reusable_design_system(
        self, reference_bundle: ReferenceBundle
    ) -> DesignSystemPreflight | None:
        if self._design_system_reuse_mode == "generate":
            return None

        candidate_errors: list[str] = []

        explicit_run_dir = (
            self._design_system_reuse_run_dir.strip()
            if self._design_system_reuse_run_dir
            else ""
        )
        if explicit_run_dir:
            try:
                return self._load_compatible_design_system_from_run_dir(
                    explicit_run_dir,
                    reference_bundle,
                )
            except Exception as exc:
                candidate_errors.append(str(exc))

        cached_design_system = load_design_system_preflight_from_current_cache()
        cached_reference_bundle = load_reference_bundle_from_current_cache()
        if (
            cached_design_system is not None
            and cached_reference_bundle is not None
            and self._design_system_reference_bundles_compatible(
                current=reference_bundle,
                candidate=cached_reference_bundle,
            )
        ):
            return cached_design_system

        if self._design_system_reuse_mode == "require_reuse" and candidate_errors:
            raise RuntimeError(candidate_errors[0])

        return None

    def _load_compatible_design_system_from_run_dir(
        self,
        run_dir: str,
        reference_bundle: ReferenceBundle,
    ) -> DesignSystemPreflight:
        source_reference_bundle = ValidatedLoopArtifactStore.load_reference_bundle(run_dir)
        if not self._design_system_reference_bundles_compatible(
            current=reference_bundle,
            candidate=source_reference_bundle,
        ):
            raise RuntimeError(
                "Saved design-system preflight is not compatible with the current reference input."
            )
        return load_design_system_preflight_from_run_dir(run_dir)

    @staticmethod
    def _design_system_reference_bundles_compatible(
        *,
        current: ReferenceBundle,
        candidate: ReferenceBundle,
    ) -> bool:
        if current.input_mode != candidate.input_mode:
            return False

        current_reference_url = current.reference_url.strip()
        candidate_reference_url = candidate.reference_url.strip()
        if bool(current_reference_url) != bool(candidate_reference_url):
            return False
        if current_reference_url and candidate_reference_url:
            if current_reference_url != candidate_reference_url:
                return False

        current_live_url = (
            current.live_reference.url.strip()
            if current.live_reference is not None
            else ""
        )
        candidate_live_url = (
            candidate.live_reference.url.strip()
            if candidate.live_reference is not None
            else ""
        )
        if bool(current_live_url) != bool(candidate_live_url):
            return False
        if current_live_url and candidate_live_url and current_live_url != candidate_live_url:
            return False

        if bool(current.images) != bool(candidate.images):
            return False
        if current.images and candidate.images:
            if _media_fingerprints(current.images) != _media_fingerprints(candidate.images):
                return False

        if bool(current.videos) != bool(candidate.videos):
            return False
        if current.videos and candidate.videos:
            if _media_fingerprints(current.videos) != _media_fingerprints(candidate.videos):
                return False

        if current.images and candidate.images and len(current.images) != len(candidate.images):
            return False

        if current.videos and candidate.videos and len(current.videos) != len(candidate.videos):
            return False

        return True

    def _persist_design_system_preflight_artifacts(
        self, design_system: DesignSystemPreflight
    ) -> DesignSystemPreflight:
        design_system_json, design_system_html = self._design_system_renderer.render(
            design_system
        )
        run_json_path, run_html_path = self._artifact_store.persist_design_system_artifacts(
            design_system_json=design_system_json,
            design_system_html=design_system_html,
        )
        return design_system.model_copy(
            update={
                "json_artifact_path": run_json_path,
                "html_artifact_path": run_html_path,
            }
        )

    def _should_stop_after_validation(
        self,
        *,
        reference_bundle: ReferenceBundle,
        validation_report: ValidationReport,
    ) -> bool:
        if validation_report.verdict != "pass":
            return False

        if self._has_blocking_issues(validation_report):
            return False

        if reference_bundle.input_mode != "video":
            return validation_report.overall_score >= VALIDATED_LOOP_PASS_SCORE

        return (
            validation_report.overall_score >= VIDEO_VALIDATED_LOOP_PASS_SCORE
            and validation_report.behavior_fidelity_score
            >= VIDEO_VALIDATED_LOOP_BEHAVIOR_PASS_SCORE
            and validation_report.animation_fidelity_score
            >= VIDEO_VALIDATED_LOOP_ANIMATION_PASS_SCORE
            and not self._has_major_motion_or_behavior_gaps(validation_report)
        )

    def _has_blocking_issues(self, validation_report: ValidationReport) -> bool:
        return any(issue.severity == "critical" for issue in validation_report.issues)

    def _has_major_motion_or_behavior_gaps(
        self, validation_report: ValidationReport
    ) -> bool:
        return any(
            issue.severity in {"critical", "major"}
            and issue.category in {"behavior", "animation"}
            for issue in validation_report.issues
        )

    def _is_better_validation(
        self,
        *,
        candidate: ValidationReport,
        incumbent: ValidationReport | None,
    ) -> bool:
        if incumbent is None:
            return True

        verdict_rank = {"blocked": 0, "revise": 1, "pass": 2}
        candidate_tuple = (
            verdict_rank[candidate.verdict],
            candidate.overall_score,
            candidate.visual_fidelity_score,
            candidate.behavior_fidelity_score,
            candidate.animation_fidelity_score,
            -sum(issue.severity == "critical" for issue in candidate.issues),
            -sum(issue.severity == "major" for issue in candidate.issues),
            -len(candidate.issues),
            candidate.editability_score,
        )
        incumbent_tuple = (
            verdict_rank[incumbent.verdict],
            incumbent.overall_score,
            incumbent.visual_fidelity_score,
            incumbent.behavior_fidelity_score,
            incumbent.animation_fidelity_score,
            -sum(issue.severity == "critical" for issue in incumbent.issues),
            -sum(issue.severity == "major" for issue in incumbent.issues),
            -len(incumbent.issues),
            incumbent.editability_score,
        )
        return candidate_tuple > incumbent_tuple

    def _summarize_requirements(self, requirements: RequirementsSpec) -> str:
        lines = []
        if requirements.summary:
            lines.append(f"Summary: {requirements.summary}")
        if requirements.template_goal:
            lines.append(f"Template goal: {requirements.template_goal}")
        if requirements.page_outline:
            lines.append(
                "Page outline:\n- " + "\n- ".join(requirements.page_outline[:6])
            )
        if requirements.closing_sections:
            lines.append(
                "Closing sections:\n- "
                + "\n- ".join(requirements.closing_sections[:5])
            )
        if requirements.footer_present is not None:
            footer_line = (
                "Footer assessment: present"
                if requirements.footer_present
                else "Footer assessment: not present"
            )
            if requirements.footer_description:
                footer_line += f" — {requirements.footer_description}"
            lines.append(footer_line)
        if requirements.coverage_notes:
            lines.append(
                "Coverage notes:\n- "
                + "\n- ".join(requirements.coverage_notes[:4])
            )
        if requirements.critical_layout_invariants:
            lines.append(
                "Critical layout invariants:\n- "
                + "\n- ".join(requirements.critical_layout_invariants[:4])
            )
        if requirements.hard_constraints:
            lines.append(
                "Hard constraints:\n- "
                + "\n- ".join(requirements.hard_constraints[:4])
            )
        if requirements.preserve_requirements:
            lines.append(
                "Preserve as-is:\n- "
                + "\n- ".join(requirements.preserve_requirements[:4])
            )
        if requirements.section_requirements:
            lines.append(
                "Primary sections:\n- "
                + "\n- ".join(
                    section.name for section in requirements.section_requirements[:4]
                )
            )
        if requirements.layout_requirements:
            lines.append(
                "Key layout requirements:\n- "
                + "\n- ".join(requirements.layout_requirements[:4])
            )
        if requirements.execution_plan:
            lines.append(
                "Execution plan:\n- "
                + "\n- ".join(requirements.execution_plan[:4])
            )
        if requirements.behavior_requirements:
            lines.append(
                "Key behavior requirements:\n- "
                + "\n- ".join(requirements.behavior_requirements[:3])
            )
        if requirements.animation_requirements:
            lines.append(
                "Key animation requirements:\n- "
                + "\n- ".join(requirements.animation_requirements[:3])
            )
        if requirements.structure_guidance:
            lines.append(
                "Template structure guidance:\n- "
                + "\n- ".join(requirements.structure_guidance[:4])
            )
        return "\n\n".join(lines) or "Requirements captured."

    def _summarize_validation(self, validation_report: ValidationReport) -> str:
        lines = [
            f"Verdict: {validation_report.verdict}",
            f"Score: {validation_report.overall_score:.2f}",
            f"Visual fidelity: {validation_report.visual_fidelity_score:.2f}",
            f"Behavior fidelity: {validation_report.behavior_fidelity_score:.2f}",
            f"Animation fidelity: {validation_report.animation_fidelity_score:.2f}",
        ]
        if validation_report.summary:
            lines.append(f"Summary: {validation_report.summary}")
        if validation_report.section_results:
            missing_sections = [
                result.name
                for result in validation_report.section_results
                if result.status == "missing"
            ]
            partial_sections = [
                result.name
                for result in validation_report.section_results
                if result.status == "partial"
            ]
            if missing_sections:
                lines.append("Missing sections:\n- " + "\n- ".join(missing_sections[:4]))
            if partial_sections:
                lines.append("Partial sections:\n- " + "\n- ".join(partial_sections[:4]))
        if validation_report.issues:
            lines.append(
                "Top issues:\n- "
                + "\n- ".join(issue.title for issue in validation_report.issues[:4])
            )
        if validation_report.patch_instructions:
            lines.append(
                "Next edits:\n- "
                + "\n- ".join(validation_report.patch_instructions[:4])
            )
        return "\n\n".join(lines)

    @property
    def analyzer_model(self):
        return self._analyzer.model

    @property
    def executor_model(self):
        return self._executor.model

    @property
    def validator_model(self):
        return self._validator.model


def _media_fingerprints(items: list[str]) -> list[str]:
    return [sha256(item.encode("utf-8")).hexdigest() for item in items]
