from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.services.funnel_templates import get_funnel_template


# Mapping from family to template ID (family names are not always template IDs)
FAMILY_TO_TEMPLATE_ID: dict[str, str] = {
    "sales-pdp": "sales-pdp",
    "listicle-presell": "pre-sales-listicle",
    "pre-sales-listicle": "pre-sales-listicle",
    "medusa-b2b-starter": "medusa-b2b-starter",
    "medusa-b2c-starter": "medusa-b2c-starter",
}

# Supported families - explicit list for validation
SUPPORTED_FAMILIES: set[str] = {
    "sales-pdp",
    "listicle-presell",
    "pre-sales-listicle",
    "medusa-b2b-starter",
    "medusa-b2c-starter",
}


class UnsupportedFamilyError(Exception):
    """Raised when an unsupported template family is requested."""

    pass


# Mapping from canonical section types to Puck blocks (family-agnostic candidates)
SECTION_TO_BLOCK_MAPPING: dict[str, list[str]] = {
    "hero": ["SalesPdpHero", "PreSalesHero"],
    "proof_bar": ["SalesPdpMarquee", "PreSalesMarquee", "SalesPdpGuarantee"],
    "feature_stack": ["SalesPdpStorySolution", "PreSalesReasons"],
    "comparison_table": ["SalesPdpComparison"],
    "testimonial_wall": ["SalesPdpReviews", "SalesPdpReviewWall", "PreSalesReviewWall"],
    "faq": ["SalesPdpFaq"],
    "sticky_offer_rail": ["SalesPdpHero", "PreSalesFloatingCta"],
    "footer": ["SalesPdpFooter", "PreSalesFooter"],
    "collection_grid": [],
    "bundle_selector": ["SalesPdpHero"],
    "generic_content": ["SalesPdpStoryProblem", "SalesPdpStorySolution", "PreSalesPitch"],
}

# Blocks supported by each template family
# Note: Both "listicle-presell" and "pre-sales-listicle" map to the same template (pre-sales-listicle)
# so we include both family names for consistency
FAMILY_BLOCKS: dict[str, list[str]] = {
    "sales-pdp": [
        "SalesPdpPage",
        "SalesPdpHeader",
        "SalesPdpHero",
        "SalesPdpVideos",
        "SalesPdpMarquee",
        "SalesPdpStoryProblem",
        "SalesPdpStorySolution",
        "SalesPdpComparison",
        "SalesPdpGuarantee",
        "SalesPdpFaq",
        "SalesPdpReviews",
        "SalesPdpReviewWall",
        "SalesPdpFooter",
    ],
    "listicle-presell": [
        "PreSalesPage",
        "PreSalesHero",
        "PreSalesReasons",
        "PreSalesMarquee",
        "PreSalesPitch",
        "PreSalesReviewWall",
        "PreSalesFooter",
        "PreSalesFloatingCta",
    ],
    "pre-sales-listicle": [
        "PreSalesPage",
        "PreSalesHero",
        "PreSalesReasons",
        "PreSalesMarquee",
        "PreSalesPitch",
        "PreSalesReviewWall",
        "PreSalesFooter",
        "PreSalesFloatingCta",
    ],
    # Commerce-core blocks for Medusa B2B site family
    "medusa-b2b-starter": [
        "Section",
        "Columns",
        "FeatureGrid",
        "Testimonials",
        "FAQ",
        "Heading",
        "Text",
        "Button",
        "Image",
        "Spacer",
        "CommerceCatalogHero",
        "CommerceProductGrid",
        "CommerceProductDetail",
        "CommerceCart",
        "CommerceCheckout",
        "CommerceCategoryList",
        "CommerceCartSummary",
    ],
    # Full B2C storefront blocks for Medusa B2C site family
    "medusa-b2c-starter": [
        # Shell blocks
        "MedusaB2CHomePage",
        "MedusaB2CStorePage",
        "MedusaB2CCollectionPage",
        "MedusaB2CCategoryPage",
        "MedusaB2CProductPage",
        "MedusaB2CCartPage",
        "MedusaB2CCheckoutPage",
        "MedusaB2CAccountDashboardPage",
        "MedusaB2CAccountProfilePage",
        "MedusaB2CAccountAddressesPage",
        "MedusaB2CAccountOrdersPage",
        "MedusaB2CAccountOrderDetailPage",
        "MedusaB2COrderConfirmedPage",
        "MedusaB2COrderTransferPage",
        "MedusaB2COrderTransferAcceptPage",
        "MedusaB2COrderTransferDeclinePage",
        # Commerce primitives (shared)
        "CommerceCatalogHero",
        "CommerceProductGrid",
        "CommerceProductDetail",
        "CommerceCart",
        "CommerceCartSummary",
        "CommerceCheckout",
        "CommerceCategoryList",
        "Section",
        "Columns",
        "Heading",
        "Text",
        "Button",
        "Image",
    ],
}


@dataclass(frozen=True)
class BlockCoverageDetail:
    """Coverage detail for a single section."""

    sectionId: str
    sectionType: str
    mappedBlock: str | None
    coverage: str  # "exact", "partial", "missing"
    confidence: float


@dataclass(frozen=True)
class BlockCoverageSummary:
    """Aggregate coverage summary."""

    totalSections: int
    exactMatches: int
    partialMatches: int
    missingMatches: int
    coverageScore: float


@dataclass(frozen=True)
class MissingBlockRequest:
    """Request for a missing block implementation."""

    requestId: str
    sectionType: str
    reason: str
    sourceSelector: str | None
    textPreview: str | None
    suggestedFamily: str
    suggestedPageType: str


@dataclass(frozen=True)
class SynthesisResult:
    """Result of synthesizing normalized sections into puckData."""

    synthesizedPuckData: dict[str, Any]
    blockCoverage: BlockCoverageSummary
    blockCoverageDetails: list[BlockCoverageDetail]
    missingBlockRequests: list[MissingBlockRequest]
    targetFamily: str
    targetPageType: str


def _get_supported_blocks(family: str) -> list[str]:
    """Get the list of supported blocks for a template family."""
    return FAMILY_BLOCKS.get(family, [])


def _map_section_to_block(section_type: str, family: str) -> tuple[str | None, float]:
    """
    Map a canonical section type to a Puck block.

    Returns (block_name, confidence) or (None, 0.0) if no mapping exists.
    Only returns blocks that are actually supported by the target family.
    """
    supported_blocks = _get_supported_blocks(family)
    candidate_blocks = SECTION_TO_BLOCK_MAPPING.get(section_type, [])

    # Find exact match in supported blocks only
    for block in candidate_blocks:
        if block in supported_blocks:
            return block, 1.0

    # No match found - do NOT return partial matches that aren't in supported blocks
    return None, 0.0


def _compute_coverage_score(exact: int, partial: int, missing: int, total: int) -> float:
    """Compute coverage score from match counts."""
    if total == 0:
        return 0.0
    # Weight: exact = 1.0, partial = 0.5, missing = 0.0
    return (exact * 1.0 + partial * 0.5) / total


def _merge_section_data(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge multiple import sections that map onto the same storefront block."""
    merged = deepcopy(existing)

    existing_text = list(merged.get("keyText", []) or [])
    incoming_text = list(incoming.get("keyText", []) or [])
    merged["keyText"] = [
        *existing_text,
        *[item for item in incoming_text if item not in existing_text],
    ]

    existing_media = list(merged.get("keyMedia", []) or [])
    incoming_media = list(incoming.get("keyMedia", []) or [])
    merged["keyMedia"] = [
        *existing_media,
        *[item for item in incoming_media if item not in existing_media],
    ]

    merged_styles = dict(merged.get("keyStyles", {}) or {})
    incoming_styles = dict(incoming.get("keyStyles", {}) or {})
    merged["keyStyles"] = {**merged_styles, **incoming_styles}

    if not merged.get("boundingBox") and incoming.get("boundingBox"):
        merged["boundingBox"] = incoming.get("boundingBox")

    return merged


def synthesize_import(
    normalized_sections: list[dict[str, Any]],
    theme_candidate: dict[str, Any],
    suggested_family: str | None,
    target_family: str | None,
    target_page_type: str | None,
) -> SynthesisResult:
    """
    Synthesize normalized sections into structured puckData.

    Takes normalized sections from a site import and maps them to
    Puck blocks from the target template family.

    Args:
        normalized_sections: List of normalized sections from import
        theme_candidate: Theme candidate tokens from import
        suggested_family: Suggested template family from normalization
        target_family: Target template family (overrides suggested)
        target_page_type: Target page type

    Returns:
        SynthesisResult with puckData, coverage scores, and missing block requests
    """
    import uuid

    # Determine target family - use default only when no explicit family provided
    family = target_family or suggested_family

    # Validate family is supported - fail cleanly instead of silent coercion
    # Only fail if an explicit unsupported family was provided
    if family is not None and family not in SUPPORTED_FAMILIES:
        raise UnsupportedFamilyError(
            f"Unsupported template family: '{family}'. "
            f"Supported families are: {', '.join(sorted(SUPPORTED_FAMILIES))}"
        )

    # If no family provided, use default (sales-pdp) for preview purposes
    if family is None:
        family = "sales-pdp"

    if family == "medusa-b2c-starter":
        raise UnsupportedFamilyError(
            "Import synthesis for 'medusa-b2c-starter' is intentionally blocked until dedicated B2C section-to-block mappings are implemented. "
            "Use explicit B2C page blueprints/templates instead of generic import synthesis for now."
        )

    # Map family to template ID
    template_id = FAMILY_TO_TEMPLATE_ID.get(family, family)

    # Get base template
    template = get_funnel_template(template_id)
    if template is None:
        raise UnsupportedFamilyError(
            f"No base template found for family: '{family}'. "
            f"Supported families are: {', '.join(sorted(SUPPORTED_FAMILIES))}"
        )

    # Clone the base puckData
    base_puck_data = deepcopy(template.puck_data)

    # Build coverage details and missing block requests
    coverage_details: list[BlockCoverageDetail] = []
    missing_requests: list[MissingBlockRequest] = []
    exact_count = 0
    partial_count = 0
    missing_count = 0

    # Track mapped blocks in order for synthesis
    mapped_blocks: list[tuple[str, dict[str, Any]]] = []

    for section in normalized_sections:
        section_id = section.get("id", "")
        section_type = section.get("sectionType", "generic_content")
        confidence = section.get("confidence", 0.0)
        key_text = section.get("keyText", [])
        key_media = section.get("keyMedia", [])
        key_styles = section.get("keyStyles", {})

        # Map section to block
        mapped_block, mapping_confidence = _map_section_to_block(section_type, family)

        if mapped_block is not None:
            # Determine coverage level
            if mapping_confidence >= 1.0:
                coverage = "exact"
                exact_count += 1
            else:
                coverage = "partial"
                partial_count += 1

            # Add to mapped blocks for synthesis, merging if multiple sections map to one block.
            existing_index = next(
                (
                    index
                    for index, (block_name, _) in enumerate(mapped_blocks)
                    if block_name == mapped_block
                ),
                None,
            )
            if existing_index is None:
                mapped_blocks.append((mapped_block, section))
            else:
                block_name, existing_section = mapped_blocks[existing_index]
                mapped_blocks[existing_index] = (
                    block_name,
                    _merge_section_data(existing_section, section),
                )
        else:
            coverage = "missing"
            missing_count += 1

            # Generate missing block request - use real sourceSelector from keyStyles
            source_selector = key_styles.get("selector")
            reason = f"No Puck block found for section type '{section_type}' in family '{family}'"
            if confidence < 0.5:
                reason += f" (low confidence: {confidence:.0%})"

            request = MissingBlockRequest(
                requestId=f"missing_{uuid.uuid4().hex[:8]}",
                sectionType=section_type,
                reason=reason,
                sourceSelector=source_selector,
                textPreview=key_text[0] if key_text else None,
                suggestedFamily=family,
                suggestedPageType=target_page_type or "product_detail",
            )
            missing_requests.append(request)

        detail = BlockCoverageDetail(
            sectionId=section_id,
            sectionType=section_type,
            mappedBlock=mapped_block,
            coverage=coverage,
            confidence=mapping_confidence,
        )
        coverage_details.append(detail)

    # Compute coverage score
    total = len(normalized_sections)
    coverage_score = _compute_coverage_score(exact_count, partial_count, missing_count, total)

    # Determine page type
    if target_page_type:
        page_type = target_page_type
    elif family == "sales-pdp":
        page_type = "product_detail"
    elif family in {"listicle-presell", "pre-sales-listicle"}:
        page_type = "pre_sell"
    else:
        page_type = "unknown"

    # Build synthesized puckData by filtering/reordering blocks
    synthesized_puck_data = _build_synthesized_puck_data(
        base_puck_data=base_puck_data,
        mapped_blocks=mapped_blocks,
        family=family,
    )

    # Apply theme tokens if available
    if theme_candidate:
        synthesized_puck_data = _apply_theme_tokens(synthesized_puck_data, theme_candidate)

    # Build summary
    summary = BlockCoverageSummary(
        totalSections=total,
        exactMatches=exact_count,
        partialMatches=partial_count,
        missingMatches=missing_count,
        coverageScore=coverage_score,
    )

    return SynthesisResult(
        synthesizedPuckData=synthesized_puck_data,
        blockCoverage=summary,
        blockCoverageDetails=coverage_details,
        missingBlockRequests=missing_requests,
        targetFamily=family,
        targetPageType=page_type,
    )


def _inject_imported_content(
    block_props: dict[str, Any],
    block_type: str,
    section_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Inject imported text/media into block config fields.

    Updates block props with imported content for common block types,
    targeting the real config shapes from base templates.
    """
    cloned = deepcopy(block_props)

    key_text = section_data.get("keyText", [])
    key_media = section_data.get("keyMedia", [])

    # Get text content
    primary_text = key_text[0] if key_text else ""
    secondary_text = key_text[1] if len(key_text) > 1 else ""
    tertiary_text = key_text[2] if len(key_text) > 2 else ""

    # Ensure config exists
    if "config" not in cloned:
        cloned["config"] = {}

    config = cloned["config"]

    # Inject content based on block type - targeting real config shapes
    if block_type == "SalesPdpHero":
        # SalesPdpHero: props.config.purchase.title and gallery.slides[0].src
        if "purchase" in config and isinstance(config["purchase"], dict):
            config["purchase"]["title"] = primary_text
        if key_media and "gallery" in config and isinstance(config["gallery"], dict):
            slides = config["gallery"].get("slides", [])
            if slides and isinstance(slides, list) and len(slides) > 0:
                slides[0]["src"] = key_media[0]

    elif block_type == "PreSalesHero":
        # PreSalesHero: props.config.hero.title/subtitle/media.src
        if "hero" in config and isinstance(config["hero"], dict):
            config["hero"]["title"] = primary_text
            if secondary_text:
                config["hero"]["subtitle"] = secondary_text
            if (
                key_media
                and "media" in config["hero"]
                and isinstance(config["hero"]["media"], dict)
            ):
                config["hero"]["media"]["src"] = key_media[0]

    elif block_type == "SalesPdpMarquee":
        # SalesPdpMarquee: props.config.items is a list of strings
        if primary_text:
            # Derive marquee items from key text (split by common delimiters or use as single item)
            items = [primary_text]
            if secondary_text:
                items.append(secondary_text)
            if tertiary_text:
                items.append(tertiary_text)
            config["items"] = items

    elif block_type == "PreSalesMarquee":
        # PreSalesMarquee: props.config itself is a list of strings
        if primary_text:
            items = [primary_text]
            if secondary_text:
                items.append(secondary_text)
            if tertiary_text:
                items.append(tertiary_text)
            # Replace config entirely with the list
            cloned["config"] = items

    elif block_type == "SalesPdpStorySolution":
        # SalesPdpStorySolution: props.config.title, paragraphs[0], bullets[0], image.src
        if primary_text:
            config["title"] = primary_text
        if secondary_text and "paragraphs" in config and isinstance(config["paragraphs"], list):
            if len(config["paragraphs"]) > 0:
                config["paragraphs"][0] = secondary_text
        if tertiary_text and "bullets" in config and isinstance(config["bullets"], list):
            if len(config["bullets"]) > 0 and isinstance(config["bullets"][0], dict):
                config["bullets"][0]["title"] = tertiary_text
        if key_media and "image" in config and isinstance(config["image"], dict):
            config["image"]["src"] = key_media[0]

    elif block_type == "SalesPdpStoryProblem":
        # SalesPdpStoryProblem: props.config.title, paragraphs[0], emphasisLine, image.src
        if primary_text:
            config["title"] = primary_text
        if secondary_text and "paragraphs" in config and isinstance(config["paragraphs"], list):
            if len(config["paragraphs"]) > 0:
                config["paragraphs"][0] = secondary_text
        if tertiary_text and "emphasisLine" in config:
            config["emphasisLine"] = tertiary_text
        if key_media and "image" in config and isinstance(config["image"], dict):
            config["image"]["src"] = key_media[0]

    elif block_type == "SalesPdpComparison":
        # SalesPdpComparison: props.config.title and first row fields
        if primary_text:
            config["title"] = primary_text
        if "rows" in config and isinstance(config["rows"], list) and len(config["rows"]) > 0:
            first_row = config["rows"][0]
            if isinstance(first_row, dict):
                if primary_text:
                    first_row["label"] = primary_text
                if secondary_text:
                    first_row["pup"] = secondary_text
                if tertiary_text:
                    first_row["disposable"] = tertiary_text

    elif block_type == "PreSalesReasons":
        # PreSalesReasons: props.config is a list of reason objects
        if isinstance(config, list) and len(config) > 0:
            first_reason = config[0] if isinstance(config[0], dict) else {}
            if primary_text:
                first_reason["title"] = primary_text
            if secondary_text:
                first_reason["body"] = secondary_text
            if key_media and "image" in first_reason and isinstance(first_reason["image"], dict):
                first_reason["image"]["src"] = key_media[0]

    elif block_type == "PreSalesPitch":
        # PreSalesPitch: props.config.title, bullets[0], image.src
        if primary_text:
            config["title"] = primary_text
        if secondary_text and "bullets" in config and isinstance(config["bullets"], list):
            if len(config["bullets"]) > 0:
                config["bullets"][0] = secondary_text
        if key_media and "image" in config and isinstance(config["image"], dict):
            config["image"]["src"] = key_media[0]

    elif block_type == "SalesPdpReviewWall":
        # SalesPdpReviewWall: props.config.title, tiles[0].image.src
        if primary_text:
            config["title"] = primary_text
        if key_media and "tiles" in config and isinstance(config["tiles"], list):
            if len(config["tiles"]) > 0 and isinstance(config["tiles"][0], dict):
                tile = config["tiles"][0]
                if "image" in tile and isinstance(tile["image"], dict):
                    tile["image"]["src"] = key_media[0]

    elif block_type == "PreSalesReviewWall":
        # PreSalesReviewWall: props.config.title, columns[0][0].image.src
        if primary_text:
            config["title"] = primary_text
        if key_media and "columns" in config and isinstance(config["columns"], list):
            if len(config["columns"]) > 0 and isinstance(config["columns"][0], list):
                if len(config["columns"][0]) > 0 and isinstance(config["columns"][0][0], dict):
                    first_tile = config["columns"][0][0]
                    if "image" in first_tile and isinstance(first_tile["image"], dict):
                        first_tile["image"]["src"] = key_media[0]

    elif block_type == "SalesPdpReviews":
        # SalesPdpReviews: props.config.data.summary.customersSay, first review body, mediaGallery[0].url
        data = config.get("data")
        if isinstance(data, dict):
            summary = data.get("summary")
            if isinstance(summary, dict) and primary_text:
                summary["customersSay"] = primary_text
            reviews = data.get("reviews")
            if isinstance(reviews, list) and len(reviews) > 0 and isinstance(reviews[0], dict):
                if secondary_text:
                    reviews[0]["body"] = secondary_text
                elif primary_text:
                    reviews[0]["body"] = primary_text
            if key_media:
                media_gallery = data.get("mediaGallery")
                if (
                    isinstance(media_gallery, list)
                    and len(media_gallery) > 0
                    and isinstance(media_gallery[0], dict)
                ):
                    media_gallery[0]["url"] = key_media[0]

    elif block_type == "SalesPdpFaq":
        # SalesPdpFaq: props.config.title, items[0].question/answer
        if primary_text:
            config["title"] = primary_text
        if "items" in config and isinstance(config["items"], list):
            if len(config["items"]) > 0 and isinstance(config["items"][0], dict):
                config["items"][0]["question"] = primary_text
                if secondary_text:
                    config["items"][0]["answer"] = secondary_text

    elif block_type in ("SalesPdpFooter", "PreSalesFooter"):
        # Footer blocks: props.config.copyright
        if primary_text:
            config["copyright"] = primary_text

    elif block_type == "PreSalesFloatingCta":
        # PreSalesFloatingCta: props.config.label
        if primary_text:
            config["label"] = primary_text

    # Always update id from import
    cloned["id"] = section_data.get("id", "")

    return cloned


def _build_synthesized_puck_data(
    base_puck_data: dict[str, Any],
    mapped_blocks: list[tuple[str, dict[str, Any]]],
    family: str,
) -> dict[str, Any]:
    """
    Build synthesized puckData by filtering/reordering blocks based on mapped sections.

    Keeps shell blocks (Page, Header, Footer) and reorders content blocks based on
    mapped import sections. Mapped blocks are cloned from the base template to preserve
    their full config/props, with imported text/media injected into relevant config fields.
    """
    cloned = deepcopy(base_puck_data)

    # Get the content array - can be at top level or nested in Page block
    # First check top-level content
    content = cloned.get("content", [])

    # Check if content is nested inside a Page block
    page_block = None
    page_content = None

    if content and isinstance(content, list):
        for block in content:
            block_type = block.get("type", "")
            if "Page" in block_type:
                page_block = block
                page_content = block.get("props", {}).get("content", [])
                break

    # Determine which content array to work with
    target_content = page_content if page_content else content
    is_nested = page_block is not None

    if not target_content or not isinstance(target_content, list):
        # No content to synthesize, return base
        return cloned

    # Build a lookup map of block_type -> block from base template
    base_block_by_type: dict[str, dict[str, Any]] = {}
    for block in target_content:
        block_type = block.get("type", "")
        if block_type:
            base_block_by_type[block_type] = block

    # Identify shell blocks vs content blocks
    shell_block_types = {"SalesPdpHeader", "PreSalesHero", "SalesPdpFooter", "PreSalesFooter"}
    content_blocks: list[dict[str, Any]] = []
    shell_blocks: list[dict[str, Any]] = []

    for block in target_content:
        block_type = block.get("type", "")
        if block_type in shell_block_types:
            shell_blocks.append(block)
        else:
            content_blocks.append(block)

    # Build new content blocks from mapped sections
    new_content_blocks: list[dict[str, Any]] = []

    # Add header shell block if exists
    for block in shell_blocks:
        block_type = block.get("type", "")
        if "Header" in block_type:
            new_content_blocks.append(block)

    # Add mapped section blocks in order - clone from base template to preserve config
    for block_type, section_data in mapped_blocks:
        # Try to find the block in base template to clone its config
        base_block = base_block_by_type.get(block_type)
        if base_block:
            # Clone the base block
            cloned_block = deepcopy(base_block)
            # Inject imported content into block config
            cloned_block["props"] = _inject_imported_content(
                cloned_block["props"],
                block_type,
                section_data,
            )
            new_content_blocks.append(cloned_block)
        else:
            raise ValueError(
                f"Synthesis mapping resolved block '{block_type}' but the base template is missing that block."
            )

    # Add footer shell block if exists
    for block in shell_blocks:
        block_type = block.get("type", "")
        if "Footer" in block_type and not any(
            existing_block.get("type") == block_type for existing_block in new_content_blocks
        ):
            new_content_blocks.append(block)

    # Replace content in the appropriate location
    if is_nested and page_block:
        # Update nested content inside Page block
        page_props = page_block.get("props", {})
        page_props["content"] = new_content_blocks
        page_block["props"] = page_props
    else:
        # Update top-level content
        cloned["content"] = new_content_blocks

    return cloned


def _apply_theme_tokens(
    puck_data: dict[str, Any],
    theme_candidate: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply imported theme tokens into the puckData theme/token area.

    Updates the theme tokens in the Page block's props.
    """
    cloned = deepcopy(puck_data)

    # Extract relevant tokens from theme_candidate
    tokens_to_apply = {}

    # Apply palette colors
    palette = theme_candidate.get("palette", {})
    if palette:
        tokens_to_apply["palette"] = palette

    # Apply fonts
    fonts = theme_candidate.get("fonts", {})
    if fonts:
        tokens_to_apply["fonts"] = fonts

    # Apply spacing
    spacing = theme_candidate.get("spacing", {})
    if spacing:
        tokens_to_apply["spacing"] = spacing

    # Apply CTA styles
    cta = theme_candidate.get("cta", {})
    if cta:
        tokens_to_apply["cta"] = cta

    if not tokens_to_apply:
        return cloned

    # Find and update the Page block's theme tokens
    # Content can be at top level or nested in root
    content = cloned.get("content", [])
    if not content:
        root = cloned.get("root", {})
        content = root.get("props", {}).get("content", [])

    if content and isinstance(content, list):
        for block in content:
            block_type = block.get("type", "")
            # Check if this is a Page block
            if "Page" in block_type:
                block_props = block.get("props", {})
                if "theme" not in block_props:
                    block_props["theme"] = {}
                if "tokens" not in block_props["theme"]:
                    block_props["theme"]["tokens"] = {}

                # Merge tokens
                existing_tokens = block_props["theme"]["tokens"]
                block_props["theme"]["tokens"] = {**existing_tokens, **tokens_to_apply}
                block["props"] = block_props
                break

    return cloned
