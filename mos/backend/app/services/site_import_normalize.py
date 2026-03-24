from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Canonical section types as defined in the plan
CANONICAL_SECTION_TYPES = (
    "hero",
    "proof_bar",
    "feature_stack",
    "comparison_table",
    "testimonial_wall",
    "faq",
    "sticky_offer_rail",
    "footer",
    "collection_grid",
    "bundle_selector",
    "generic_content",
)

# Mapping from detected patterns to canonical types
# Navigation and header are not canonical - map to hero or generic_content
SECTION_TYPE_MAPPING = {
    "navigation": "generic_content",
    "header": "hero",
    "nav": "generic_content",
}


def _generate_section_id() -> str:
    """Generate a unique section ID."""
    return f"section_{uuid.uuid4().hex[:8]}"


def _extract_text_content(html: str, selector: str) -> list[str]:
    """Extract text content from HTML using simple regex patterns."""
    # Very simple extraction - in production would use BeautifulSoup
    text_matches = re.findall(r"<[^>]*>([^<]*)</[^>]*>", html)
    return [t.strip() for t in text_matches if t.strip()][:10]


def _detect_section_type(html: str, capture_metadata: dict[str, Any]) -> tuple[str, float]:
    """
    Detect the section type from HTML content.
    Returns (section_type, confidence_score).
    """
    html_lower = html.lower()

    # Hero section detection
    if any(
        marker in html_lower
        for marker in ["hero", "banner", "jumbotron", 'id="hero"', 'class="hero"']
    ):
        return ("hero", 0.9)

    # Proof bar detection
    if any(
        marker in html_lower
        for marker in [
            "proof",
            "trust",
            "guarantee",
            "review",
            "rating",
            "testimonial",
            "customer",
        ]
    ):
        if any(marker in html_lower for marker in ["bar", "strip", "badge", "logo"]):
            return ("proof_bar", 0.85)

    # Feature stack detection
    if any(
        marker in html_lower
        for marker in [
            "feature",
            "benefit",
            "why",
            "choose",
            "advantage",
            "capability",
        ]
    ):
        if any(marker in html_lower for marker in ["grid", "list", "card", "item"]):
            return ("feature_stack", 0.8)

    # Comparison table detection
    if any(marker in html_lower for marker in ["comparison", "compare", "vs", "versus", "table"]):
        return ("comparison_table", 0.85)

    # Testimonial wall detection
    if any(
        marker in html_lower
        for marker in [
            "testimonial",
            "review",
            "feedback",
            "quote",
            "customer",
            "story",
        ]
    ):
        if any(
            marker in html_lower for marker in ["wall", "grid", "carousel", "slider", "multiple"]
        ):
            return ("testimonial_wall", 0.8)

    # FAQ detection
    if any(marker in html_lower for marker in ["faq", "question", "accordion", "help", "support"]):
        return ("faq", 0.85)

    # Sticky offer rail detection
    if any(
        marker in html_lower
        for marker in [
            "sticky",
            "fixed",
            "bar",
            "offer",
            "cart",
            "checkout",
            "purchase",
        ]
    ):
        return ("sticky_offer_rail", 0.75)

    # Footer detection
    if any(
        marker in html_lower for marker in ["footer", "site-info", "copyright", "links", "sitemap"]
    ):
        return ("footer", 0.95)

    # Collection grid detection
    if any(
        marker in html_lower
        for marker in [
            "collection",
            "product",
            "grid",
            "shop",
            "store",
            "catalog",
        ]
    ):
        if any(marker in html_lower for marker in ["grid", "list", "card", "item"]):
            return ("collection_grid", 0.8)

    # Bundle selector detection
    if any(
        marker in html_lower
        for marker in [
            "bundle",
            "package",
            "combo",
            "set",
            "deal",
            "offer",
            "select",
        ]
    ):
        return ("bundle_selector", 0.75)

    # Default to generic content
    return ("generic_content", 0.5)


def _extract_key_media(html: str) -> list[str]:
    """Extract key media URLs from HTML."""
    media_urls: list[str] = []

    # Extract img src
    img_matches = re.findall(r'<img[^>]+src="([^"]+)"', html)
    media_urls.extend(img_matches[:5])

    # Extract background-image
    bg_matches = re.findall(r'background-image:\s*url\("([^"]+)"\)', html)
    media_urls.extend(bg_matches[:3])

    # Extract video sources
    video_matches = re.findall(r'<video[^>]+src="([^"]+)"', html)
    media_urls.extend(video_matches[:2])

    return list(set(media_urls))  # Deduplicate


def _extract_key_styles(capture_metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract key styles from capture metadata."""
    styles: dict[str, Any] = {}

    if "palette" in capture_metadata:
        styles["palette"] = capture_metadata["palette"]

    if "fonts" in capture_metadata:
        styles["fonts"] = capture_metadata["fonts"]

    if "cta" in capture_metadata:
        styles["cta"] = capture_metadata["cta"]

    if "spacing" in capture_metadata:
        styles["spacing"] = capture_metadata["spacing"]

    return styles


def _suggest_template_family(
    page_type_hint: str | None, normalized_sections: list[dict[str, Any]]
) -> str | None:
    """Suggest a template family based on page type hint and sections."""
    if page_type_hint:
        hint_lower = page_type_hint.lower()
        if "product" in hint_lower or "pdp" in hint_lower:
            return "sales-pdp"
        if "collection" in hint_lower:
            return "collection-story"
        if "home" in hint_lower:
            return "home-ugc"
        if "pre-sell" in hint_lower or "presell" in hint_lower:
            return "listicle-presell"

    # Infer from sections
    section_types = {s["sectionType"] for s in normalized_sections}

    if "hero" in section_types and "product" in str(section_types).lower():
        return "sales-pdp"
    if "collection_grid" in section_types:
        return "collection-story"
    if "testimonial_wall" in section_types and "proof_bar" in section_types:
        return "home-ugc"

    return None


@dataclass(frozen=True)
class NormalizedSectionResult:
    """A normalized section from the import."""

    id: str
    sectionType: str
    confidence: float
    keyText: list[str]
    keyMedia: list[str]
    keyStyles: dict[str, Any]
    boundingBox: dict[str, float] | None


@dataclass(frozen=True)
class NormalizationResult:
    """Result of normalizing a captured site."""

    title: str | None
    meta_description: str | None
    theme_candidate: dict[str, Any]
    normalized_sections: list[dict[str, Any]]
    suggested_template_family: str | None


def normalize_capture(
    html_snapshot: str,
    capture_metadata: dict[str, Any],
    page_type_hint: str | None,
    title: str | None,
    meta_description: str | None,
) -> NormalizationResult:
    """
    Normalize a captured site into structured sections and theme candidate.

    This is a deterministic function that can be easily tested.
    Uses structured metadata from capture (sectionCandidates) when available.
    """
    # Extract theme candidate from capture metadata
    theme_candidate: dict[str, Any] = {
        "palette": capture_metadata.get("palette", {}),
        "fonts": capture_metadata.get("fonts", {}),
        "spacing": capture_metadata.get("spacing", {"density": "comfortable", "scale": []}),
        "cta": capture_metadata.get("cta", {"style": "solid"}),
    }

    normalized_sections: list[dict[str, Any]] = []
    extraction_partial = False

    # Try to use structured section candidates from capture metadata
    section_candidates = capture_metadata.get("sectionCandidates", [])

    if section_candidates and isinstance(section_candidates, list):
        # Use structured metadata from capture
        for candidate in section_candidates:
            tag = candidate.get("tag", "div")
            selector = candidate.get("selector", "")
            text_preview = candidate.get("textPreview", "")
            bounding_box = candidate.get("boundingBox")
            computed_styles = candidate.get("computedStyles", {})

            # Detect section type from tag and selector
            detected_type, confidence = _detect_section_type_from_element(
                tag, selector, text_preview, html_snapshot
            )

            # Map to canonical type (avoid navigation, header, nav)
            mapped_type = SECTION_TYPE_MAPPING.get(detected_type, detected_type)

            # Only include canonical types
            if mapped_type not in CANONICAL_SECTION_TYPES:
                mapped_type = "generic_content"

            normalized_sections.append(
                {
                    "id": _generate_section_id(),
                    "sectionType": mapped_type,
                    "confidence": confidence,
                    "keyText": [text_preview] if text_preview else [],
                    "keyMedia": [],
                    "keyStyles": {
                        "selector": selector,
                        "backgroundColor": computed_styles.get("backgroundColor"),
                        "color": computed_styles.get("color"),
                        "fontFamily": computed_styles.get("fontFamily"),
                        "display": computed_styles.get("display"),
                        "position": computed_styles.get("position"),
                    },
                    "boundingBox": bounding_box,
                }
            )
    else:
        # Fallback to HTML-based detection
        extraction_partial = True
        section_type, confidence = _detect_section_type(html_snapshot, capture_metadata)

        # Map to canonical type
        mapped_type = SECTION_TYPE_MAPPING.get(section_type, section_type)
        if mapped_type not in CANONICAL_SECTION_TYPES:
            mapped_type = "generic_content"

        # Extract key text and media
        key_text = _extract_text_content(html_snapshot, "body")
        key_media = _extract_key_media(html_snapshot)
        key_styles = _extract_key_styles(capture_metadata)

        normalized_sections.append(
            {
                "id": _generate_section_id(),
                "sectionType": mapped_type,
                "confidence": confidence,
                "keyText": key_text,
                "keyMedia": key_media,
                "keyStyles": key_styles,
                "boundingBox": None,
            }
        )

    # Try to detect additional sections from HTML (only canonical types)
    # Look for footer
    if re.search(r"<footer", html_snapshot, re.IGNORECASE):
        # Check if we already have a footer section
        has_footer = any(s["sectionType"] == "footer" for s in normalized_sections)
        if not has_footer:
            normalized_sections.append(
                {
                    "id": _generate_section_id(),
                    "sectionType": "footer",
                    "confidence": 0.95,
                    "keyText": [],
                    "keyMedia": [],
                    "keyStyles": {},
                    "boundingBox": None,
                }
            )

    # Suggest template family
    suggested_family = _suggest_template_family(page_type_hint, normalized_sections)

    return NormalizationResult(
        title=title,
        meta_description=meta_description,
        theme_candidate=theme_candidate,
        normalized_sections=normalized_sections,
        suggested_template_family=suggested_family,
    )


def _detect_section_type_from_element(
    tag: str, selector: str, text_preview: str, html_snapshot: str
) -> tuple[str, float]:
    """
    Detect section type from element metadata.

    Returns (section_type, confidence_score).
    """
    selector_lower = selector.lower()
    text_lower = text_preview.lower()
    tag_lower = tag.lower()

    # Check selector and text for patterns
    combined = f"{selector_lower} {text_lower}"

    # Hero detection
    if any(marker in combined for marker in ["hero", "banner", "jumbotron"]):
        return ("hero", 0.9)

    # Footer detection
    if tag_lower == "footer" or "footer" in selector_lower:
        return ("footer", 0.95)

    # Navigation - map to generic_content (not a canonical type)
    if tag_lower == "nav" or "nav" in selector_lower:
        return ("navigation", 0.9)

    # Header - map to hero
    if tag_lower == "header" or "header" in selector_lower:
        return ("header", 0.85)

    # Proof bar detection
    if any(
        marker in combined
        for marker in ["proof", "trust", "guarantee", "review", "rating", "testimonial"]
    ):
        if any(marker in combined for marker in ["bar", "strip", "badge", "logo"]):
            return ("proof_bar", 0.85)

    # Feature stack detection
    if any(
        marker in combined
        for marker in ["feature", "benefit", "why", "choose", "advantage", "capability"]
    ):
        if any(marker in combined for marker in ["grid", "list", "card", "item"]):
            return ("feature_stack", 0.8)

    # Comparison table detection
    if any(marker in combined for marker in ["comparison", "compare", "vs", "versus", "table"]):
        return ("comparison_table", 0.85)

    # Testimonial wall detection
    if any(
        marker in combined
        for marker in ["testimonial", "review", "feedback", "quote", "customer", "story"]
    ):
        if any(marker in combined for marker in ["wall", "grid", "carousel", "slider"]):
            return ("testimonial_wall", 0.8)

    # FAQ detection
    if any(marker in combined for marker in ["faq", "question", "accordion", "help"]):
        return ("faq", 0.85)

    # Sticky offer rail detection
    if any(
        marker in combined
        for marker in ["sticky", "fixed", "offer", "cart", "checkout", "purchase"]
    ):
        return ("sticky_offer_rail", 0.75)

    # Collection grid detection
    if any(
        marker in combined
        for marker in ["collection", "product", "grid", "shop", "store", "catalog"]
    ):
        if any(marker in combined for marker in ["grid", "list", "card", "item"]):
            return ("collection_grid", 0.8)

    # Bundle selector detection
    if any(
        marker in combined for marker in ["bundle", "package", "combo", "set", "deal", "select"]
    ):
        return ("bundle_selector", 0.75)

    # Default to generic content
    return ("generic_content", 0.5)
