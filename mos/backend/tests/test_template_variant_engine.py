"""Tests for template variant engine service."""

import pytest
from typing import Any, cast

from app.services.template_variant_engine import (
    MUTATION_PRESETS,
    PRESET_FAMILY_SUPPORT,
    GeneratedVariant,
    MutationPreset,
    PresetNotApplicableError,
    PresetPreview,
    VariantEngineError,
    apply_multiple_presets_to_variant,
    apply_preset_to_variant,
    get_preset,
    get_variant_puck_data,
    is_preset_applicable,
    list_mutation_presets,
    preview_presets_for_variant,
)


def make_variant(
    variant_id: str = "test-variant-id",
    name: str = "Test Variant",
    family: str = "sales-pdp",
    page_type: str = "product_detail",
    provenance: dict | None = None,
) -> dict:
    """Create a test variant dict."""
    return {
        "id": variant_id,
        "name": name,
        "family": family,
        "page_type": page_type,
        "provenance": provenance or {},
    }


def make_puck_data_with_hero(title: str = "Test Title") -> dict:
    """Create test puckData with a hero block."""
    return {
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {
                            "type": "SalesPdpHero",
                            "props": {
                                "id": "hero_001",
                                "config": {
                                    "purchase": {"title": title},
                                    "gallery": {"slides": [{"src": "https://example.com/img.jpg"}]},
                                },
                            },
                        },
                        {
                            "type": "SalesPdpMarquee",
                            "props": {
                                "id": "marquee_001",
                                "config": {"items": ["Item 1", "Item 2"]},
                            },
                        },
                        {
                            "type": "SalesPdpFooter",
                            "props": {
                                "id": "footer_001",
                                "config": {"copyright": "Test"},
                            },
                        },
                    ]
                },
            }
        ]
    }


def make_puck_data_with_comparison() -> dict:
    """Create test puckData with comparison block."""
    return {
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {
                            "type": "SalesPdpHero",
                            "props": {"id": "hero_001", "config": {"purchase": {"title": "Test"}}},
                        },
                        {
                            "type": "SalesPdpMarquee",
                            "props": {"id": "marquee_001", "config": {"items": ["Item 1"]}},
                        },
                        {
                            "type": "SalesPdpComparison",
                            "props": {
                                "id": "comparison_001",
                                "config": {
                                    "title": "Compare",
                                    "rows": [
                                        {"label": "Feature", "pup": "Good", "disposable": "Bad"}
                                    ],
                                },
                            },
                        },
                        {
                            "type": "SalesPdpFooter",
                            "props": {"id": "footer_001", "config": {"copyright": "Test"}},
                        },
                    ]
                },
            }
        ]
    }


def make_puck_data_with_header_and_comparison() -> dict:
    """Create test puckData with a header, hero, and later comparison block."""
    return {
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {"type": "SalesPdpHeader", "props": {"id": "header_001", "config": {}}},
                        {
                            "type": "SalesPdpHero",
                            "props": {"id": "hero_001", "config": {"purchase": {"title": "Test"}}},
                        },
                        {
                            "type": "SalesPdpMarquee",
                            "props": {"id": "marquee_001", "config": {"items": ["Item 1"]}},
                        },
                        {
                            "type": "SalesPdpComparison",
                            "props": {
                                "id": "comparison_001",
                                "config": {
                                    "title": "Compare",
                                    "rows": [
                                        {"label": "Feature", "pup": "Good", "disposable": "Bad"}
                                    ],
                                },
                            },
                        },
                    ]
                },
            }
        ]
    }


def make_presales_review_wall_variant() -> dict:
    """Create test puckData with a PreSalesReviewWall block."""
    return {
        "content": [
            {
                "type": "PreSalesPage",
                "props": {
                    "content": [
                        {
                            "type": "PreSalesReviewWall",
                            "props": {
                                "id": "review_wall_001",
                                "config": {
                                    "title": "Reviews",
                                    "buttonLabel": "View reviews",
                                    "columns": [[{"text": "Great"}], [{"text": "Amazing"}]],
                                },
                            },
                        }
                    ]
                },
            }
        ]
    }


def make_puck_data_with_reviews() -> dict:
    """Create test puckData with review blocks."""
    return {
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {
                            "type": "SalesPdpHero",
                            "props": {"id": "hero_001", "config": {"purchase": {"title": "Test"}}},
                        },
                        {
                            "type": "SalesPdpMarquee",
                            "props": {"id": "marquee_001", "config": {"items": ["Item 1"]}},
                        },
                        {
                            "type": "SalesPdpReviews",
                            "props": {
                                "id": "reviews_001",
                                "config": {
                                    "data": {
                                        "summary": {"customersSay": "Great product"},
                                        "reviews": [{"body": "Amazing!"}],
                                    }
                                },
                            },
                        },
                        {
                            "type": "SalesPdpReviewWall",
                            "props": {
                                "id": "review_wall_001",
                                "config": {"title": "Reviews", "tiles": []},
                            },
                        },
                        {
                            "type": "SalesPdpFooter",
                            "props": {"id": "footer_001", "config": {"copyright": "Test"}},
                        },
                    ]
                },
            }
        ]
    }


def make_full_sales_puck_data() -> dict:
    """Create a fuller sales PDP puckData fixture covering all mutation targets."""
    return {
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {"type": "SalesPdpHeader", "props": {"id": "header_001", "config": {}}},
                        {
                            "type": "SalesPdpHero",
                            "props": {
                                "id": "hero_001",
                                "config": {
                                    "purchase": {
                                        "title": "Test Title",
                                        "cta": {
                                            "labelTemplate": "Add to cart - {price}",
                                            "subBullets": [],
                                            "urgency": {"message": "Ships soon", "rows": []},
                                        },
                                    },
                                    "gallery": {
                                        "slides": [{"src": "img1.jpg"}, {"src": "img2.jpg"}]
                                    },
                                },
                            },
                        },
                        {
                            "type": "SalesPdpMarquee",
                            "props": {
                                "id": "marquee_001",
                                "config": {"items": ["Item 1", "Item 2"]},
                            },
                        },
                        {
                            "type": "SalesPdpComparison",
                            "props": {
                                "id": "comparison_001",
                                "config": {
                                    "title": "Compare",
                                    "rows": [
                                        {"label": "Feature", "pup": "Good", "disposable": "Bad"}
                                    ],
                                },
                            },
                        },
                        {
                            "type": "SalesPdpReviews",
                            "props": {
                                "id": "reviews_001",
                                "config": {
                                    "data": {
                                        "summary": {"customersSay": "Great"},
                                        "reviews": [{"body": "Amazing"}],
                                    }
                                },
                            },
                        },
                        {
                            "type": "SalesPdpReviewWall",
                            "props": {
                                "id": "review_wall_001",
                                "hidden": True,
                                "config": {
                                    "title": "Reviews",
                                    "tiles": [{"image": {"src": "img.jpg"}}],
                                },
                            },
                        },
                        {
                            "type": "SalesPdpFooter",
                            "props": {"id": "footer_001", "config": {"copyright": "Test"}},
                        },
                    ]
                },
            }
        ]
    }


class TestMutationPresets:
    """Tests for mutation preset catalog."""

    def test_presets_defined(self):
        """Test that presets are defined."""
        assert len(MUTATION_PRESETS) >= 6
        assert "headline_hierarchy" in MUTATION_PRESETS
        assert "proof_density" in MUTATION_PRESETS
        assert "cta_emphasis" in MUTATION_PRESETS
        assert "product_media_order" in MUTATION_PRESETS
        assert "comparison_placement" in MUTATION_PRESETS
        assert "testimonial_mix" in MUTATION_PRESETS

    def test_preset_structure(self):
        """Test that presets have required fields."""
        for preset_id, preset in MUTATION_PRESETS.items():
            assert preset.id == preset_id
            assert preset.label
            assert preset.description
            assert preset.families
            assert preset.effects

    def test_list_presets_all(self):
        """Test listing all presets."""
        presets = list_mutation_presets()
        assert len(presets) == len(MUTATION_PRESETS)

    def test_list_presets_by_family(self):
        """Test filtering presets by family."""
        sales_presets = list_mutation_presets(family="sales-pdp")
        assert len(sales_presets) >= 6  # All presets apply to sales-pdp

        listicle_presets = list_mutation_presets(family="listicle-presell")
        # headline_hierarchy, proof_density, cta_emphasis, testimonial_mix
        assert len(listicle_presets) >= 4

    def test_get_preset(self):
        """Test getting a specific preset."""
        preset = get_preset("headline_hierarchy")
        assert preset is not None
        assert preset.id == "headline_hierarchy"

        preset = get_preset("nonexistent")
        assert preset is None

    def test_is_preset_applicable(self):
        """Test preset applicability check."""
        assert is_preset_applicable("headline_hierarchy", "sales-pdp") is True
        assert is_preset_applicable("headline_hierarchy", "listicle-presell") is True
        assert is_preset_applicable("product_media_order", "sales-pdp") is True
        assert is_preset_applicable("product_media_order", "listicle-presell") is False
        assert is_preset_applicable("comparison_placement", "sales-pdp") is True
        assert is_preset_applicable("comparison_placement", "listicle-presell") is False


class TestGetVariantPuckData:
    """Tests for extracting puckData from variant provenance."""

    def test_get_puck_data_success(self):
        """Test extracting puckData from valid provenance."""
        puck_data = {"content": [{"type": "SalesPdpPage"}]}
        variant = make_variant(provenance={"synthesis": {"synthesized_puck_data": puck_data}})

        result = get_variant_puck_data(variant)
        assert result == puck_data

    def test_get_puck_data_missing_synthesis(self):
        """Test extracting puckData when synthesis is missing."""
        variant = make_variant(provenance={})
        result = get_variant_puck_data(variant)
        assert result is None

    def test_get_puck_data_missing_puck_data(self):
        """Test extracting puckData when puck_data is missing."""
        variant = make_variant(provenance={"synthesis": {}})
        result = get_variant_puck_data(variant)
        assert result is None

    def test_get_puck_data_invalid_provenance(self):
        """Test extracting puckData with invalid provenance type."""
        variant = make_variant(provenance=cast(dict[str, Any], "not a dict"))
        result = get_variant_puck_data(variant)
        assert result is None


class TestPreviewPresetsForVariant:
    """Tests for previewing presets for a variant."""

    def test_preview_presets_sales_pdp(self):
        """Test preview for sales-pdp variant."""
        puck_data = make_full_sales_puck_data()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        previews = preview_presets_for_variant(variant)

        assert len(previews) == len(MUTATION_PRESETS)
        for preview in previews:
            assert isinstance(preview, PresetPreview)
            assert preview.presetId
            assert preview.presetLabel
            assert preview.applicable is not None

            # Check applicability matches family support
            expected_applicable = is_preset_applicable(preview.presetId, "sales-pdp")
            assert preview.applicable == expected_applicable

    def test_preview_presets_listicle_presell(self):
        """Test preview for listicle-presell variant."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="listicle-presell",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        previews = preview_presets_for_variant(variant)

        # product_media_order and comparison_placement should not be applicable
        for preview in previews:
            if preview.presetId in ("product_media_order", "comparison_placement"):
                assert preview.applicable is False
                assert preview.notApplicableReason is not None

    def test_preview_presets_no_puck_data(self):
        """Test preview when variant has no puckData."""
        variant = make_variant(family="sales-pdp", provenance={})

        previews = preview_presets_for_variant(variant)

        # All presets should be not applicable
        for preview in previews:
            assert preview.applicable is False
            assert preview.notApplicableReason is not None
            assert "no synthesized puckData" in preview.notApplicableReason


class TestApplyPresetToVariant:
    """Tests for applying presets to variants."""

    def test_apply_headline_hierarchy(self):
        """Test applying headline_hierarchy preset."""
        puck_data = make_puck_data_with_hero(title="Original Title")
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(variant, "headline_hierarchy")

        assert isinstance(result, GeneratedVariant)
        assert result.family == "sales-pdp"
        assert result.mutationPresetId == "headline_hierarchy"
        assert result.parentVariantId == "test-variant-id"
        assert "Headline Hierarchy" in result.name

        # Check that puckData was mutated
        assert result.synthesizedPuckData is not None
        hero_block = result.synthesizedPuckData["content"][0]["props"]["content"][0]
        assert hero_block["props"]["config"]["purchase"]["title"] == "ORIGINAL TITLE"

    def test_apply_proof_density(self):
        """Test applying proof_density preset."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(variant, "proof_density")

        assert result.mutationPresetId == "proof_density"
        assert result.synthesizedPuckData is not None

    def test_apply_cta_emphasis(self):
        """Test applying cta_emphasis preset."""
        puck_data = make_puck_data_with_hero()
        puck_data["content"][0]["props"]["content"][0]["props"]["config"]["purchase"]["cta"] = {
            "labelTemplate": "Add to cart - {price}",
            "subBullets": [],
            "urgency": {"message": "Ships soon", "rows": []},
        }
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(variant, "cta_emphasis")

        assert result.mutationPresetId == "cta_emphasis"
        hero_block = result.synthesizedPuckData["content"][0]["props"]["content"][0]
        cta = hero_block["props"]["config"]["purchase"]["cta"]
        assert cta["labelTemplate"].startswith("BUY NOW •")
        assert cta["urgency"]["message"].startswith("Act now —")

    def test_apply_product_media_order(self):
        """Test applying product_media_order preset."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {
                                    "config": {
                                        "gallery": {
                                            "slides": [
                                                {"src": "img1.jpg"},
                                                {"src": "img2.jpg"},
                                                {"src": "img3.jpg"},
                                            ]
                                        }
                                    }
                                },
                            }
                        ]
                    },
                }
            ]
        }
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(variant, "product_media_order")

        assert result.mutationPresetId == "product_media_order"
        # Check that slides were reordered
        page_block = result.synthesizedPuckData["content"][0]
        hero_block = page_block["props"]["content"][0]
        slides = hero_block["props"]["config"]["gallery"]["slides"]
        assert slides[0]["src"] == "img2.jpg"  # Second slide moved to first

    def test_apply_comparison_placement(self):
        """Test applying comparison_placement preset."""
        puck_data = make_puck_data_with_header_and_comparison()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(variant, "comparison_placement")

        assert result.mutationPresetId == "comparison_placement"
        # Check that comparison was moved directly after hero, not before it.
        page_block = result.synthesizedPuckData["content"][0]
        content = page_block["props"]["content"]
        assert [block["type"] for block in content[:3]] == [
            "SalesPdpHeader",
            "SalesPdpHero",
            "SalesPdpComparison",
        ]

    def test_apply_testimonial_mix(self):
        """Test applying testimonial_mix preset."""
        puck_data = make_puck_data_with_reviews()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(variant, "testimonial_mix")

        assert result.mutationPresetId == "testimonial_mix"

    def test_apply_proof_density_presales_review_wall_keeps_columns_flat(self):
        """Test proof density keeps pre-sales review wall columns as a flat list of columns."""
        variant = make_variant(
            family="pre-sales-listicle",
            provenance={
                "synthesis": {"synthesized_puck_data": make_presales_review_wall_variant()}
            },
        )

        result = apply_preset_to_variant(variant, "proof_density")

        page_block = result.synthesizedPuckData["content"][0]
        wall_block = page_block["props"]["content"][0]
        columns = wall_block["props"]["config"]["columns"]
        assert isinstance(columns, list)
        assert all(isinstance(column, list) for column in columns)

    def test_apply_preset_custom_name(self):
        """Test applying preset with custom name."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(
            variant, "headline_hierarchy", generated_name="Custom Variant Name"
        )

        assert result.name == "Custom Variant Name"

    def test_apply_preset_not_applicable(self):
        """Test applying non-applicable preset raises error."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="listicle-presell",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        with pytest.raises(PresetNotApplicableError) as exc_info:
            apply_preset_to_variant(variant, "product_media_order")

        assert "not applicable" in str(exc_info.value)

    def test_apply_preset_unknown_preset(self):
        """Test applying unknown preset raises error."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        with pytest.raises(PresetNotApplicableError) as exc_info:
            apply_preset_to_variant(variant, "unknown_preset")

        assert "Unknown preset" in str(exc_info.value)

    def test_apply_preset_no_puck_data(self):
        """Test applying preset to variant without puckData raises error."""
        variant = make_variant(family="sales-pdp", provenance={})

        with pytest.raises(VariantEngineError) as exc_info:
            apply_preset_to_variant(variant, "headline_hierarchy")

        assert "no synthesized puckData" in str(exc_info.value)

    def test_apply_preset_unsupported_family(self):
        """Test applying preset to unsupported family raises error."""
        variant = make_variant(family="unsupported-family", provenance={})

        with pytest.raises(VariantEngineError) as exc_info:
            apply_preset_to_variant(variant, "headline_hierarchy")

        assert "Unsupported family" in str(exc_info.value)

    def test_apply_preset_preserves_provenance(self):
        """Test that provenance is preserved in derived variant."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="sales-pdp",
            provenance={
                "source_type": "site_import",
                "source_url": "https://example.com",
                "synthesis": {
                    "synthesized_puck_data": puck_data,
                    "block_coverage": {"total_sections": 5},
                },
            },
        )

        result = apply_preset_to_variant(variant, "headline_hierarchy")

        assert result.provenance["source_type"] == "variant_mutation"
        assert result.provenance["parent_variant_id"] == "test-variant-id"
        assert result.provenance["mutation_preset_id"] == "headline_hierarchy"
        assert result.provenance["original_source_type"] == "site_import"
        assert result.provenance["original_source_url"] == "https://example.com"
        assert result.provenance["synthesis"]["block_coverage"]["total_sections"] == 5

    def test_apply_preset_rejects_no_op_mutation(self):
        """Test that presets reject unchanged puckData instead of generating fake variants."""
        puck_data = make_puck_data_with_hero(title="ALREADY UPPERCASE")
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        with pytest.raises(PresetNotApplicableError) as exc_info:
            apply_preset_to_variant(variant, "headline_hierarchy")

        assert "would not change" in str(exc_info.value)

    def test_apply_preset_records_actor_in_provenance_event(self):
        """Derived variants should capture the acting user in provenance."""
        puck_data = make_full_sales_puck_data()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        result = apply_preset_to_variant(variant, "headline_hierarchy", actor="user-123")

        events = result.provenance.get("events", [])
        assert events
        assert events[-1]["event_type"] == "derive"
        assert events[-1]["actor"] == "user-123"


class TestApplyMultiplePresets:
    """Tests for applying multiple presets."""

    def test_apply_multiple_presets(self):
        """Test applying multiple presets to a variant."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        results = apply_multiple_presets_to_variant(
            variant, ["headline_hierarchy", "proof_density"]
        )

        assert len(results) == 2
        assert results[0].mutationPresetId == "headline_hierarchy"
        assert results[1].mutationPresetId == "proof_density"

    def test_apply_multiple_presets_custom_names(self):
        """Test applying multiple presets with custom names."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        results = apply_multiple_presets_to_variant(
            variant,
            ["headline_hierarchy", "proof_density"],
            generated_names=["Custom Name 1", "Custom Name 2"],
        )

        assert results[0].name == "Custom Name 1"
        assert results[1].name == "Custom Name 2"

    def test_apply_multiple_presets_name_count_mismatch(self):
        """Test that name count mismatch raises error."""
        puck_data = make_puck_data_with_hero()
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        with pytest.raises(VariantEngineError) as exc_info:
            apply_multiple_presets_to_variant(
                variant,
                ["headline_hierarchy", "proof_density"],
                generated_names=["Only one name"],
            )

        assert "must match" in str(exc_info.value)

    def test_apply_multiple_presets_independent(self):
        """Test that each preset is applied to original variant independently."""
        puck_data = make_puck_data_with_hero(title="Original")
        variant = make_variant(
            family="sales-pdp",
            provenance={"synthesis": {"synthesized_puck_data": puck_data}},
        )

        results = apply_multiple_presets_to_variant(
            variant, ["headline_hierarchy", "proof_density"]
        )

        # Both should start from the same original puckData
        # Each mutation is independent, not chained
        assert results[0].parentVariantId == "test-variant-id"
        assert results[1].parentVariantId == "test-variant-id"


class TestPresetFamilySupport:
    """Tests for preset family support mapping."""

    def test_family_support_defined(self):
        """Test that family support is defined for all presets."""
        for preset_id in MUTATION_PRESETS:
            assert preset_id in PRESET_FAMILY_SUPPORT

    def test_family_support_values(self):
        """Test that family support values are valid families."""
        valid_families = {"sales-pdp", "listicle-presell", "pre-sales-listicle"}

        for preset_id, families in PRESET_FAMILY_SUPPORT.items():
            for family in families:
                assert family in valid_families, f"Invalid family {family} for preset {preset_id}"
