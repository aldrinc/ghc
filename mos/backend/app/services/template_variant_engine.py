"""
Template Variant Engine Service.

Generates derived template variants from existing variants using
deterministic, conversion-focused mutation presets.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from app.services.template_synthesis import SUPPORTED_FAMILIES
from app.services.template_variant_governance import build_derive_provenance


class VariantEngineError(Exception):
    """Error during variant generation."""

    pass


class PresetNotApplicableError(VariantEngineError):
    """Raised when a preset cannot be applied to a variant."""

    pass


# =============================================================================
# Mutation Preset Catalog
# =============================================================================

# Preset applicability by family
PRESET_FAMILY_SUPPORT: dict[str, set[str]] = {
    "headline_hierarchy": {"sales-pdp", "listicle-presell", "pre-sales-listicle"},
    "proof_density": {"sales-pdp", "listicle-presell", "pre-sales-listicle"},
    "cta_emphasis": {"sales-pdp", "listicle-presell", "pre-sales-listicle"},
    "product_media_order": {"sales-pdp"},
    "comparison_placement": {"sales-pdp"},
    "testimonial_mix": {"sales-pdp", "listicle-presell", "pre-sales-listicle"},
}


@dataclass(frozen=True)
class MutationPreset:
    """A mutation preset that can be applied to a variant."""

    id: str
    label: str
    description: str
    families: list[str]
    effects: list[str]


# The preset catalog - conversion-focused mutations
MUTATION_PRESETS: dict[str, MutationPreset] = {
    "headline_hierarchy": MutationPreset(
        id="headline_hierarchy",
        label="Headline Hierarchy",
        description="Adjust headline emphasis and hierarchy for stronger visual impact.",
        families=["sales-pdp", "listicle-presell", "pre-sales-listicle"],
        effects=[
            "Increases hero title prominence",
            "Adjusts subtitle weight",
            "Reorders headline elements for scanability",
        ],
    ),
    "proof_density": MutationPreset(
        id="proof_density",
        label="Proof Density",
        description="Increase or decrease visible proof modules for trust building.",
        families=["sales-pdp", "listicle-presell", "pre-sales-listicle"],
        effects=[
            "Adjusts number of visible proof elements",
            "Modifies proof copy density",
            "Reorders proof sections for impact",
        ],
    ),
    "cta_emphasis": MutationPreset(
        id="cta_emphasis",
        label="CTA Emphasis",
        description="Strengthen call-to-action visibility and urgency.",
        families=["sales-pdp", "listicle-presell", "pre-sales-listicle"],
        effects=[
            "Increases floating CTA prominence",
            "Adjusts CTA button labels for urgency",
            "Modifies purchase CTA placement",
        ],
    ),
    "product_media_order": MutationPreset(
        id="product_media_order",
        label="Product Media Order",
        description="Reorder gallery/media for different conversion strategies.",
        families=["sales-pdp"],
        effects=[
            "Reorders gallery slides",
            "Adjusts media prominence",
            "Optimizes for different viewing patterns",
        ],
    ),
    "comparison_placement": MutationPreset(
        id="comparison_placement",
        label="Comparison Placement",
        description="Move comparison block earlier or later in the page flow.",
        families=["sales-pdp"],
        effects=[
            "Moves comparison table position",
            "Adjusts comparison visibility",
            "Optimizes for different buyer journeys",
        ],
    ),
    "testimonial_mix": MutationPreset(
        id="testimonial_mix",
        label="Testimonial Mix",
        description="Adjust testimonial wall composition and emphasis.",
        families=["sales-pdp", "listicle-presell", "pre-sales-listicle"],
        effects=[
            "Reorders review/testimonial modules",
            "Adjusts testimonial density",
            "Modifies social proof emphasis",
        ],
    ),
}


def list_mutation_presets(family: str | None = None) -> list[MutationPreset]:
    """
    List available mutation presets, optionally filtered by family.

    Args:
        family: Optional family filter. If provided, only returns presets
            applicable to that family.

    Returns:
        List of MutationPreset objects.
    """
    if family is None:
        return list(MUTATION_PRESETS.values())

    return [
        p for p in MUTATION_PRESETS.values() if family in PRESET_FAMILY_SUPPORT.get(p.id, set())
    ]


def get_preset(preset_id: str) -> MutationPreset | None:
    """Get a specific preset by ID."""
    return MUTATION_PRESETS.get(preset_id)


def is_preset_applicable(preset_id: str, family: str) -> bool:
    """Check if a preset is applicable to a family."""
    supported_families = PRESET_FAMILY_SUPPORT.get(preset_id, set())
    return family in supported_families


def _get_mutable_page_content(puck_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the primary mutable content list for storefront puck data."""
    content = puck_data.get("content", [])
    if not isinstance(content, list):
        raise VariantEngineError("Invalid puckData: content must be a list.")

    for block in content:
        if not isinstance(block, dict):
            continue
        if "Page" in str(block.get("type", "")):
            props = block.get("props", {})
            if not isinstance(props, dict):
                raise VariantEngineError("Invalid puckData: page block props must be an object.")
            page_content = props.get("content", [])
            if not isinstance(page_content, list):
                raise VariantEngineError("Invalid puckData: page content must be a list.")
            return page_content

    return content


def _find_first_block(page_content: list[dict[str, Any]], block_type: str) -> dict[str, Any] | None:
    for block in page_content:
        if block.get("type") == block_type:
            return block
    return None


def _resolve_preset_not_applicable_reason(
    preset_id: str,
    family: str,
    puck_data: dict[str, Any] | None,
) -> str | None:
    if not is_preset_applicable(preset_id, family):
        return f"Preset '{preset_id}' is not applicable to family '{family}'"

    if puck_data is None:
        return "Variant has no synthesized puckData to mutate"

    page_content = _get_mutable_page_content(puck_data)

    if preset_id == "headline_hierarchy":
        if family == "sales-pdp":
            hero = _find_first_block(page_content, "SalesPdpHero")
            purchase = (((hero or {}).get("props") or {}).get("config") or {}).get("purchase")
            if not isinstance(purchase, dict) or not isinstance(purchase.get("title"), str):
                return "Preset requires a SalesPdpHero purchase title."
        else:
            hero = _find_first_block(page_content, "PreSalesHero")
            hero_config = (((hero or {}).get("props") or {}).get("config") or {}).get("hero")
            if not isinstance(hero_config, dict) or not isinstance(hero_config.get("title"), str):
                return "Preset requires a PreSalesHero title."

    elif preset_id == "proof_density":
        if family == "sales-pdp":
            has_proof = any(
                block.get("type") in {"SalesPdpMarquee", "SalesPdpReviewWall"}
                for block in page_content
            )
        else:
            has_proof = any(
                block.get("type") in {"PreSalesMarquee", "PreSalesReviewWall"}
                for block in page_content
            )
        if not has_proof:
            return "Preset requires at least one proof block to mutate."

    elif preset_id == "cta_emphasis":
        if family == "sales-pdp":
            hero = _find_first_block(page_content, "SalesPdpHero")
            cta = (
                (((hero or {}).get("props") or {}).get("config") or {})
                .get("purchase", {})
                .get("cta")
            )
            if not isinstance(cta, dict) or not isinstance(cta.get("labelTemplate"), str):
                return "Preset requires a SalesPdpHero purchase CTA."
        else:
            floating_cta = _find_first_block(page_content, "PreSalesFloatingCta")
            pitch = _find_first_block(page_content, "PreSalesPitch")
            floating_label = (((floating_cta or {}).get("props") or {}).get("config") or {}).get(
                "label"
            )
            pitch_cta = (((pitch or {}).get("props") or {}).get("config") or {}).get("cta")
            if not isinstance(floating_label, str) and not (
                isinstance(pitch_cta, dict) and isinstance(pitch_cta.get("label"), str)
            ):
                return "Preset requires a visible pre-sales CTA block."

    elif preset_id == "product_media_order":
        hero = _find_first_block(page_content, "SalesPdpHero")
        slides = (
            (((hero or {}).get("props") or {}).get("config") or {}).get("gallery", {}).get("slides")
        )
        if not isinstance(slides, list) or len(slides) < 2:
            return "Preset requires at least two SalesPdpHero gallery slides."

    elif preset_id == "comparison_placement":
        hero_index = next(
            (i for i, block in enumerate(page_content) if block.get("type") == "SalesPdpHero"), None
        )
        comparison_index = next(
            (
                i
                for i, block in enumerate(page_content)
                if block.get("type") == "SalesPdpComparison"
            ),
            None,
        )
        if hero_index is None or comparison_index is None:
            return "Preset requires both a SalesPdpHero and SalesPdpComparison block."
        if comparison_index == hero_index + 1:
            return "Comparison block is already placed directly after the hero."

    elif preset_id == "testimonial_mix":
        review_blocks = [
            block
            for block in page_content
            if block.get("type") in {"SalesPdpReviews", "SalesPdpReviewWall", "PreSalesReviewWall"}
        ]
        if not review_blocks:
            return "Preset requires at least one review or testimonial block."

    mutation_fn = PRESET_MUTATIONS.get(preset_id)
    if mutation_fn is not None:
        mutated_puck_data = mutation_fn(copy.deepcopy(puck_data))
        if mutated_puck_data == puck_data:
            return "Preset would not change the current synthesized puckData."

    return None


# =============================================================================
# Mutation Functions
# =============================================================================


def _apply_headline_hierarchy(puck_data: dict[str, Any]) -> dict[str, Any]:
    """
    Apply headline hierarchy mutation.

    Adjusts visible headline copy for stronger hierarchy.
    """
    result = copy.deepcopy(puck_data)

    content = _get_mutable_page_content(result)
    for block in content:
        block_type = block.get("type", "")

        # SalesPdpHero: promote visible purchase headline and CTA copy.
        if block_type == "SalesPdpHero":
            props = block.get("props", {})
            config = props.get("config", {})
            if "purchase" in config and isinstance(config["purchase"], dict):
                purchase = config["purchase"]
                title = purchase.get("title")
                if isinstance(title, str) and title.strip():
                    purchase["title"] = title.strip().upper()
                cta = purchase.get("cta")
                if isinstance(cta, dict):
                    label_template = cta.get("labelTemplate")
                    if isinstance(label_template, str) and label_template.strip():
                        cta["labelTemplate"] = label_template.strip().upper()

        # PreSalesHero: promote visible hero title while tightening subtitle casing.
        elif block_type == "PreSalesHero":
            props = block.get("props", {})
            config = props.get("config", {})
            if "hero" in config and isinstance(config["hero"], dict):
                hero = config["hero"]
                title = hero.get("title")
                if isinstance(title, str) and title.strip():
                    hero["title"] = title.strip().upper()
                subtitle = hero.get("subtitle")
                if isinstance(subtitle, str) and subtitle.strip():
                    hero["subtitle"] = subtitle.strip().capitalize()

    return result


def _apply_proof_density(puck_data: dict[str, Any]) -> dict[str, Any]:
    """
    Apply proof density mutation.

    Increases visible proof density using supported runtime fields.
    """
    result = copy.deepcopy(puck_data)

    content = _get_mutable_page_content(result)
    for block in content:
        block_type = block.get("type", "")

        # SalesPdpMarquee: duplicate top proof items and increase repeat.
        if block_type == "SalesPdpMarquee":
            props = block.get("props", {})
            config = props.get("config", {})
            items = config.get("items")
            if isinstance(items, list) and items:
                config["items"] = [*items, *items[: min(2, len(items))]]
                repeat = config.get("repeat")
                config["repeat"] = repeat + 1 if isinstance(repeat, int) else 3

        # PreSalesMarquee: repeat top social-proof strings.
        elif block_type == "PreSalesMarquee":
            props = block.get("props", {})
            config = props.get("config")
            if isinstance(config, list) and config:
                props["config"] = [*config, *config[: min(2, len(config))]]

        # Review walls: reveal/duplicate existing testimonials.
        elif block_type in ("SalesPdpReviewWall", "PreSalesReviewWall"):
            props = block.get("props", {})
            config = props.get("config", {})
            if block_type == "SalesPdpReviewWall":
                props["hidden"] = False
                tiles = config.get("tiles")
                if isinstance(tiles, list) and tiles:
                    config["tiles"] = [*tiles, *tiles[: min(2, len(tiles))]]
            else:
                columns = config.get("columns")
                if isinstance(columns, list) and columns:
                    config["columns"] = [*columns, *copy.deepcopy(columns[:1])]

    return result


def _apply_cta_emphasis(puck_data: dict[str, Any]) -> dict[str, Any]:
    """
    Apply CTA emphasis mutation.

    Strengthens visible call-to-action copy.
    """
    result = copy.deepcopy(puck_data)

    content = _get_mutable_page_content(result)
    for block in content:
        block_type = block.get("type", "")

        # SalesPdpHero: strengthen CTA label and urgency message.
        if block_type == "SalesPdpHero":
            props = block.get("props", {})
            config = props.get("config", {})
            if "purchase" in config and isinstance(config["purchase"], dict):
                purchase = config["purchase"]
                cta = purchase.get("cta")
                if isinstance(cta, dict):
                    label_template = cta.get("labelTemplate")
                    if isinstance(label_template, str) and label_template.strip():
                        cta["labelTemplate"] = f"BUY NOW • {label_template.strip()}"
                    urgency = cta.get("urgency")
                    if isinstance(urgency, dict):
                        message = urgency.get("message")
                        if (
                            isinstance(message, str)
                            and message.strip()
                            and "Act now" not in message
                        ):
                            urgency["message"] = f"Act now — {message.strip()}"

        # Pre-sales CTA blocks: strengthen visible CTA labels.
        elif block_type == "PreSalesFloatingCta":
            props = block.get("props", {})
            config = props.get("config", {})
            label = config.get("label")
            if isinstance(label, str) and label.strip():
                config["label"] = label.strip().upper()

        elif block_type == "PreSalesPitch":
            props = block.get("props", {})
            config = props.get("config", {})
            cta = config.get("cta")
            if isinstance(cta, dict):
                label = cta.get("label")
                if isinstance(label, str) and label.strip():
                    cta["label"] = label.strip().upper()

    return result


def _apply_product_media_order(puck_data: dict[str, Any]) -> dict[str, Any]:
    """
    Apply product media order mutation.

    Reorders gallery slides for different conversion strategies.
    """
    result = copy.deepcopy(puck_data)

    content = _get_mutable_page_content(result)
    for block in content:
        block_type = block.get("type", "")

        if block_type == "SalesPdpHero":
            props = block.get("props", {})
            config = props.get("config", {})
            if "gallery" in config and isinstance(config["gallery"], dict):
                gallery = config["gallery"]
                slides = gallery.get("slides", [])
                if isinstance(slides, list) and len(slides) > 1:
                    # Reorder: move second slide to first position for variety
                    # This is a deterministic transformation
                    reordered = slides[1:] + slides[:1]
                    gallery["slides"] = reordered

    return result


def _apply_comparison_placement(puck_data: dict[str, Any]) -> dict[str, Any]:
    """
    Apply comparison placement mutation.

    Moves comparison table earlier in the page flow.
    """
    result = copy.deepcopy(puck_data)

    page_content = _get_mutable_page_content(result)

    if not isinstance(page_content, list) or len(page_content) < 2:
        return result

    # Find comparison block index
    comparison_idx = None
    for idx, block in enumerate(page_content):
        if block.get("type") == "SalesPdpComparison":
            comparison_idx = idx
            break

    hero_idx = None
    for idx, block in enumerate(page_content):
        if block.get("type") == "SalesPdpHero":
            hero_idx = idx
            break

    if comparison_idx is None or hero_idx is None:
        return result

    desired_index = hero_idx + 1
    if comparison_idx == desired_index:
        return result

    # Move comparison directly after hero.
    comparison_block = page_content.pop(comparison_idx)
    if comparison_idx < desired_index:
        desired_index -= 1
    page_content.insert(desired_index, comparison_block)

    return result


def _apply_testimonial_mix(puck_data: dict[str, Any]) -> dict[str, Any]:
    """
    Apply testimonial mix mutation.

    Adjusts testimonial ordering and wall visibility.
    """
    result = copy.deepcopy(puck_data)

    page_content = _get_mutable_page_content(result)

    if not isinstance(page_content, list):
        return result

    # Find review/testimonial blocks
    review_blocks = []
    other_blocks = []
    for block in page_content:
        block_type = block.get("type", "")
        if block_type in ("SalesPdpReviews", "SalesPdpReviewWall", "PreSalesReviewWall"):
            review_blocks.append(block)
        else:
            other_blocks.append(block)

    if len(review_blocks) < 1:
        return result

    # Reorder: move review blocks earlier if they're late in the page.
    insert_position = 1
    for idx, block in enumerate(other_blocks):
        block_type = block.get("type", "")
        if block_type not in ("SalesPdpHeader", "SalesPdpHero", "PreSalesHero"):
            insert_position = idx
            break

    for review_block in review_blocks:
        if review_block.get("type") == "SalesPdpReviewWall":
            props = review_block.get("props", {})
            if isinstance(props, dict):
                props["hidden"] = False

    for review_block in reversed(review_blocks):
        other_blocks.insert(insert_position, review_block)

    page_content[:] = other_blocks

    return result


# Mapping from preset ID to mutation function
PRESET_MUTATIONS: dict[str, "Callable[[dict[str, Any]], dict[str, Any]]"] = {
    "headline_hierarchy": _apply_headline_hierarchy,
    "proof_density": _apply_proof_density,
    "cta_emphasis": _apply_cta_emphasis,
    "product_media_order": _apply_product_media_order,
    "comparison_placement": _apply_comparison_placement,
    "testimonial_mix": _apply_testimonial_mix,
}


# =============================================================================
# Variant Generation
# =============================================================================


@dataclass(frozen=True)
class PresetPreview:
    """Preview of a preset's applicability and effects."""

    presetId: str
    presetLabel: str
    presetDescription: str
    applicable: bool
    notApplicableReason: str | None
    effects: list[str]


@dataclass(frozen=True)
class GeneratedVariant:
    """A generated variant from mutation."""

    id: str
    name: str
    family: str
    pageType: str
    status: str
    parentVariantId: str
    mutationPresetId: str
    mutationPresetLabel: str
    mutationSummary: str
    synthesizedPuckData: dict[str, Any]
    provenance: dict[str, Any]


def get_variant_puck_data(variant: dict[str, Any]) -> dict[str, Any] | None:
    """
    Extract synthesized puckData from a variant's provenance.

    Args:
        variant: TemplateVariant dict with provenance field.

    Returns:
        The synthesized puckData if available, None otherwise.
    """
    provenance = variant.get("provenance", {})
    if not isinstance(provenance, dict):
        return None

    synthesis = provenance.get("synthesis", {})
    if not isinstance(synthesis, dict):
        return None

    return synthesis.get("synthesized_puck_data")


def preview_presets_for_variant(
    variant: dict[str, Any],
) -> list[PresetPreview]:
    """
    Preview all presets for a variant, showing applicability.

    Args:
        variant: TemplateVariant dict with family and provenance.

    Returns:
        List of PresetPreview objects for each preset.
    """
    family = variant.get("family", "")
    puck_data = get_variant_puck_data(variant)

    previews = []
    for preset in MUTATION_PRESETS.values():
        not_applicable_reason = _resolve_preset_not_applicable_reason(preset.id, family, puck_data)
        applicable = not_applicable_reason is None

        previews.append(
            PresetPreview(
                presetId=preset.id,
                presetLabel=preset.label,
                presetDescription=preset.description,
                applicable=applicable,
                notApplicableReason=not_applicable_reason,
                effects=preset.effects,
            )
        )

    return previews


def apply_preset_to_variant(
    variant: dict[str, Any],
    preset_id: str,
    generated_name: str | None = None,
    actor: str | None = None,
) -> GeneratedVariant:
    """
    Apply a mutation preset to a variant, generating a derived variant.

    Args:
        variant: TemplateVariant dict with family and provenance.
        preset_id: ID of the preset to apply.
        generated_name: Optional name for the generated variant.

    Returns:
        GeneratedVariant with mutated puckData.

    Raises:
        PresetNotApplicableError: If preset cannot be applied.
        VariantEngineError: If variant lacks required data.
    """
    # Validate preset exists
    preset = get_preset(preset_id)
    if preset is None:
        raise PresetNotApplicableError(f"Unknown preset: {preset_id}")

    # Validate family
    family = variant.get("family", "")
    if family not in SUPPORTED_FAMILIES:
        raise VariantEngineError(f"Unsupported family: {family}")

    if not is_preset_applicable(preset_id, family):
        raise PresetNotApplicableError(
            f"Preset '{preset.label}' is not applicable to family '{family}'. "
            f"Supported families: {preset.families}"
        )

    # Get puckData from provenance
    puck_data = get_variant_puck_data(variant)
    if puck_data is None:
        raise VariantEngineError(
            "Variant has no synthesized puckData in provenance. "
            "Only converted variants with synthesis can be mutated."
        )

    not_applicable_reason = _resolve_preset_not_applicable_reason(preset_id, family, puck_data)
    if not_applicable_reason is not None:
        raise PresetNotApplicableError(not_applicable_reason)

    # Apply mutation
    mutation_fn = PRESET_MUTATIONS.get(preset_id)
    if mutation_fn is None:
        raise VariantEngineError(f"No mutation function for preset: {preset_id}")

    mutated_puck_data = mutation_fn(puck_data)

    # Build provenance for derived variant using the helper function
    parent_id = str(variant.get("id", ""))
    parent_name = variant.get("name", "")
    original_provenance = variant.get("provenance", {})

    derived_provenance = build_derive_provenance(
        parent_variant_id=parent_id,
        parent_variant_name=parent_name,
        mutation_preset_id=preset_id,
        mutation_preset_label=preset.label,
        synthesized_puck_data=mutated_puck_data,
        original_provenance=original_provenance,
        actor=actor,
    )

    # Generate name if not provided
    if generated_name is None:
        generated_name = f"{parent_name} - {preset.label}"

    # Build mutation summary
    mutation_summary = f"Applied {preset.label} mutation: {preset.description}"

    return GeneratedVariant(
        id=str(uuid.uuid4()),
        name=generated_name,
        family=family,
        pageType=variant.get("page_type", ""),
        status="draft",
        parentVariantId=parent_id,
        mutationPresetId=preset_id,
        mutationPresetLabel=preset.label,
        mutationSummary=mutation_summary,
        synthesizedPuckData=mutated_puck_data,
        provenance=derived_provenance,
    )


def apply_multiple_presets_to_variant(
    variant: dict[str, Any],
    preset_ids: list[str],
    generated_names: list[str] | None = None,
    actor: str | None = None,
) -> list[GeneratedVariant]:
    """
    Apply multiple presets to a variant, generating multiple derived variants.

    Each preset is applied independently to the original variant,
    not chained (each derived variant starts from the same base).

    Args:
        variant: TemplateVariant dict with family and provenance.
        preset_ids: List of preset IDs to apply.
        generated_names: Optional list of names for each generated variant.

    Returns:
        List of GeneratedVariant objects.

    Raises:
        PresetNotApplicableError: If any preset cannot be applied.
        VariantEngineError: If variant lacks required data.
    """
    if generated_names is not None and len(generated_names) != len(preset_ids):
        raise VariantEngineError(
            f"Number of names ({len(generated_names)}) must match number of presets ({len(preset_ids)})"
        )

    results = []
    for idx, preset_id in enumerate(preset_ids):
        name = generated_names[idx] if generated_names else None
        result = apply_preset_to_variant(variant, preset_id, name, actor=actor)
        results.append(result)

    return results
