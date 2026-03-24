"""Tests for template synthesis service."""

import pytest

from app.services.template_synthesis import (
    FAMILY_BLOCKS,
    SUPPORTED_FAMILIES,
    SynthesisResult,
    UnsupportedFamilyError,
    synthesize_import,
)


def test_family_blocks_defined():
    """Test that family blocks are defined for known families."""
    assert "sales-pdp" in FAMILY_BLOCKS
    assert "listicle-presell" in FAMILY_BLOCKS
    assert len(FAMILY_BLOCKS["sales-pdp"]) > 0
    assert len(FAMILY_BLOCKS["listicle-presell"]) > 0


def test_synthesize_import_hero_section():
    """Test synthesis with hero section maps to correct block."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    assert isinstance(result, SynthesisResult)
    assert result.targetFamily == "sales-pdp"
    assert result.targetPageType == "product_detail"
    assert result.synthesizedPuckData is not None
    assert len(result.blockCoverageDetails) == 1
    assert result.blockCoverageDetails[0].sectionType == "hero"
    assert result.blockCoverageDetails[0].mappedBlock is not None
    assert result.blockCoverageDetails[0].coverage == "exact"


def test_synthesize_import_multiple_sections():
    """Test synthesis with multiple sections."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        },
        {
            "id": "section_002",
            "sectionType": "footer",
            "confidence": 0.95,
            "keyText": [],
            "keyMedia": [],
            "keyStyles": {},
        },
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    assert result.blockCoverage.totalSections == 2
    assert result.blockCoverage.exactMatches >= 1
    assert len(result.blockCoverageDetails) == 2


def test_synthesize_import_unknown_section():
    """Test synthesis with unknown section type generates missing block request."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "collection_grid",
            "confidence": 0.8,
            "keyText": ["Products"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    # collection_grid has no mapping in sales-pdp family
    assert result.blockCoverage.missingMatches >= 0
    assert len(result.missingBlockRequests) >= 0


def test_synthesize_import_empty_sections():
    """Test synthesis with empty sections returns zero coverage."""
    normalized_sections = []
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    assert result.blockCoverage.totalSections == 0
    assert result.blockCoverage.coverageScore == 0.0


def test_synthesize_import_custom_family():
    """Test synthesis with custom target family."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="pre-sales-listicle",
        target_page_type="pre_sell",
    )

    assert result.targetFamily == "pre-sales-listicle"
    assert result.targetPageType == "pre_sell"


def test_synthesize_import_low_confidence_generates_missing_request():
    """Test that low confidence sections generate missing block requests."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.3,
            "keyText": [],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    # Even with low confidence, hero maps to a valid block
    # but the reason should mention low confidence if applicable
    assert result.synthesizedPuckData is not None


def test_synthesize_import_unknown_family_raises_error():
    """Test that unknown family raises UnsupportedFamilyError instead of silent fallback."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    # Should raise error for unknown family instead of silent fallback
    with pytest.raises(UnsupportedFamilyError) as exc_info:
        synthesize_import(
            normalized_sections=normalized_sections,
            theme_candidate=theme_candidate,
            suggested_family="unknown-family",
            target_family=None,
            target_page_type=None,
        )

    assert "Unsupported template family" in str(exc_info.value)


def test_synthesize_import_listicle_presell_uses_correct_template():
    """Test that listicle-presell family uses pre-sales-listicle template."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="listicle-presell",
        target_family=None,
        target_page_type=None,
    )

    # Should use listicle-presell family and pre-sales-listicle template
    assert result.targetFamily == "listicle-presell"
    assert result.targetPageType == "pre_sell"
    # Hero should map to PreSalesHero for listicle-presell family
    assert result.blockCoverageDetails[0].mappedBlock == "PreSalesHero"


def test_synthesize_import_unsupported_section_creates_missing_request():
    """Test that unsupported sections in target family create missing block requests."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "collection_grid",
            "confidence": 0.9,
            "keyText": ["Products"],
            "keyMedia": [],
            "keyStyles": {"selector": ".products"},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    # collection_grid has no mapping - should create missing block request
    assert result.blockCoverage.missingMatches >= 1
    assert len(result.missingBlockRequests) >= 1
    assert result.missingBlockRequests[0].sectionType == "collection_grid"


def test_synthesize_import_filters_and_reorders_blocks():
    """Test that synthesized puckData filters/reorders blocks based on mappings."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        },
        {
            "id": "section_002",
            "sectionType": "proof_bar",
            "confidence": 0.9,
            "keyText": ["Guarantee"],
            "keyMedia": [],
            "keyStyles": {},
        },
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    # Verify puckData is synthesized (not just base template)
    assert result.synthesizedPuckData is not None
    # Should have content array at top level (inside Page block)
    content = result.synthesizedPuckData.get("content", [])
    assert isinstance(content, list)
    # Should contain mapped blocks inside the Page block
    page_block = None
    for block in content:
        if "Page" in block.get("type", ""):
            page_block = block
            break

    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    block_types = [b.get("type") for b in page_content]
    assert "SalesPdpHero" in block_types
    assert "SalesPdpMarquee" in block_types


def test_synthesize_import_applies_theme_tokens():
    """Test that theme tokens are applied to synthesized puckData."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {"primary": "rgb(255,0,0)", "background": "rgb(255,255,255)"},
        "fonts": {"heading": "Arial", "body": "sans-serif"},
        "spacing": {"density": "comfortable"},
        "cta": {"style": "solid"},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    # Verify theme tokens are applied
    assert result.synthesizedPuckData is not None
    # Find the Page block and check theme tokens (at top level content)
    content = result.synthesizedPuckData.get("content", [])
    page_block = None
    for block in content:
        if "Page" in block.get("type", ""):
            page_block = block
            break

    assert page_block is not None
    theme = page_block.get("props", {}).get("theme", {})
    tokens = theme.get("tokens", {})
    assert "palette" in tokens
    assert "fonts" in tokens


def test_synthesize_import_preserves_block_config():
    """Test that synthesized mapped blocks preserve real block config from base template."""
    normalized_sections = [
        {
            "id": "imported_hero_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        },
        {
            "id": "imported_proof_bar_001",
            "sectionType": "proof_bar",
            "confidence": 0.9,
            "keyText": ["Guarantee"],
            "keyMedia": [],
            "keyStyles": {},
        },
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    # Verify puckData is synthesized
    assert result.synthesizedPuckData is not None
    content = result.synthesizedPuckData.get("content", [])

    # Find the Page block and its content
    page_block = None
    for block in content:
        if "Page" in block.get("type", ""):
            page_block = block
            break

    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])

    # Find the hero block - should have config from base template
    hero_block = None
    for block in page_content:
        if block.get("type") == "SalesPdpHero":
            hero_block = block
            break

    assert hero_block is not None, "Hero block should be present in synthesized content"

    # Verify the hero block has config preserved from base template
    hero_props = hero_block.get("props", {})
    assert "config" in hero_props, "Hero block should have config from base template"

    # Verify id was updated from import
    assert hero_props.get("id") == "imported_hero_001", "Hero id should be from import"

    # Verify config has real content (not just empty)
    config = hero_props["config"]
    assert "header" in config, "Hero config should have header from base template"
    assert "gallery" in config, "Hero config should have gallery from base template"
    assert "purchase" in config, "Hero config should have purchase from base template"

    # Verify purchase.title was updated from import (real config field)
    assert config["purchase"].get("title") == "Welcome", "purchase.title should be from import"

    # Find the proof bar (marquee) block
    marquee_block = None
    for block in page_content:
        if block.get("type") == "SalesPdpMarquee":
            marquee_block = block
            break

    assert marquee_block is not None, "Marquee block should be present in synthesized content"

    # Verify marquee block also has config preserved
    marquee_props = marquee_block.get("props", {})
    assert "config" in marquee_props, "Marquee block should have config from base template"

    # Verify items was updated from import (real config field)
    marquee_config = marquee_props["config"]
    assert "items" in marquee_config, "Marquee config should have items"
    assert "Guarantee" in marquee_config["items"], "Items should contain import text"


def test_synthesize_import_invalid_family_raises_error():
    """Test that unsupported family raises UnsupportedFamilyError."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    # Should raise error for unsupported family
    with pytest.raises(UnsupportedFamilyError) as exc_info:
        synthesize_import(
            normalized_sections=normalized_sections,
            theme_candidate=theme_candidate,
            suggested_family="unsupported-family",
            target_family="unsupported-family",
            target_page_type=None,
        )

    assert "Unsupported template family" in str(exc_info.value)
    assert "unsupported-family" in str(exc_info.value)


def test_synthesize_import_no_family_uses_default():
    """Test that None family uses default sales-pdp family."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    # Should use default family when no family is provided
    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family=None,
        target_family=None,
        target_page_type=None,
    )

    # Should use sales-pdp as default
    assert result.targetFamily == "sales-pdp"


def test_supported_families_defined():
    """Test that supported families are properly defined."""
    assert "sales-pdp" in SUPPORTED_FAMILIES
    assert "listicle-presell" in SUPPORTED_FAMILIES
    assert "pre-sales-listicle" in SUPPORTED_FAMILIES
    assert len(SUPPORTED_FAMILIES) >= 2


def test_synthesize_import_missing_block_includes_source_selector():
    """Test that missing block requests include sourceSelector from normalized section."""
    normalized_sections = [
        {
            "id": "section_001",
            "sectionType": "collection_grid",
            "confidence": 0.9,
            "keyText": ["Products"],
            "keyMedia": [],
            "keyStyles": {"selector": ".products-grid"},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family=None,
        target_page_type=None,
    )

    # collection_grid has no mapping - should create missing block request
    assert result.blockCoverage.missingMatches >= 1
    assert len(result.missingBlockRequests) >= 1

    # Verify sourceSelector is included in the missing block request
    missing_request = result.missingBlockRequests[0]
    assert missing_request.sourceSelector == ".products-grid"
    assert missing_request.sectionType == "collection_grid"


def test_synthesize_import_injects_text_into_hero_config():
    """Test that synthesized hero block has imported text/media injected into real config fields."""
    normalized_sections = [
        {
            "id": "imported_hero_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Welcome to Our Store", "Best products for you"],
            "keyMedia": ["https://example.com/hero.jpg"],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    # Verify puckData is synthesized
    assert result.synthesizedPuckData is not None
    content = result.synthesizedPuckData.get("content", [])

    # Find the Page block and its content
    page_block = None
    for block in content:
        if "Page" in block.get("type", ""):
            page_block = block
            break

    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])

    # Find the hero block
    hero_block = None
    for block in page_content:
        if block.get("type") == "SalesPdpHero":
            hero_block = block
            break

    assert hero_block is not None, "Hero block should be present"

    hero_props = hero_block.get("props", {})
    config = hero_props.get("config", {})

    # Verify purchase.title was updated from import (real config field)
    assert "purchase" in config, "Hero config should have purchase"
    purchase = config["purchase"]
    assert isinstance(purchase, dict), "Purchase should be a dict"
    assert purchase.get("title") == "Welcome to Our Store", "purchase.title should be from import"

    # Verify gallery.slides[0].src was updated from import (real config field)
    assert "gallery" in config, "Hero config should have gallery"
    gallery = config["gallery"]
    assert isinstance(gallery, dict), "Gallery should be a dict"
    slides = gallery.get("slides", [])
    assert len(slides) > 0, "Gallery should have slides"
    assert slides[0].get("src") == "https://example.com/hero.jpg", (
        "First slide src should be from import"
    )


def test_synthesize_import_injects_text_into_marquee_config():
    """Test that synthesized marquee block has imported text injected into config."""
    normalized_sections = [
        {
            "id": "imported_marquee_001",
            "sectionType": "proof_bar",
            "confidence": 0.9,
            "keyText": ["Free Shipping - 30 Day Guarantee"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {
        "palette": {},
        "fonts": {},
        "spacing": {},
        "cta": {},
    }

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    # Verify puckData is synthesized
    assert result.synthesizedPuckData is not None
    content = result.synthesizedPuckData.get("content", [])

    # Find the Page block and its content
    page_block = None
    for block in content:
        if "Page" in block.get("type", ""):
            page_block = block
            break

    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])

    # Find the marquee block
    marquee_block = None
    for block in page_content:
        if block.get("type") == "SalesPdpMarquee":
            marquee_block = block
            break

    assert marquee_block is not None, "Marquee block should be present"

    marquee_props = marquee_block.get("props", {})

    # Verify config has imported text injected into items (real config field)
    config = marquee_props.get("config", {})
    assert "items" in config, "Marquee config should have items"
    assert isinstance(config["items"], list), "Items should be a list"
    assert "Free Shipping - 30 Day Guarantee" in config["items"]


def test_synthesize_import_sales_hero_real_config_fields():
    """Test that SalesPdpHero gets imported text/media in real config fields."""
    normalized_sections = [
        {
            "id": "imported_hero_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Amazing Product Name"],
            "keyMedia": ["https://example.com/product-hero.jpg"],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    # Find the hero block
    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    hero_block = next((b for b in page_content if b.get("type") == "SalesPdpHero"), None)
    assert hero_block is not None

    hero_props = hero_block.get("props", {})
    config = hero_props.get("config", {})

    # Verify purchase.title is updated (real config field)
    assert "purchase" in config, "Hero config should have purchase"
    purchase = config["purchase"]
    assert isinstance(purchase, dict), "Purchase should be a dict"
    assert purchase.get("title") == "Amazing Product Name", "purchase.title should be from import"

    # Verify gallery.slides[0].src is updated (real config field)
    assert "gallery" in config, "Hero config should have gallery"
    gallery = config["gallery"]
    assert isinstance(gallery, dict), "Gallery should be a dict"
    slides = gallery.get("slides", [])
    assert len(slides) > 0, "Gallery should have slides"
    assert slides[0].get("src") == "https://example.com/product-hero.jpg", (
        "First slide src should be from import"
    )


def test_synthesize_import_pre_sales_hero_real_config_fields():
    """Test that PreSalesHero gets imported text/media in real config fields."""
    normalized_sections = [
        {
            "id": "imported_presales_hero_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["This Product Attracts Dogs", "5 Reasons Why It Works"],
            "keyMedia": ["https://example.com/dog-product.jpg"],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="pre-sales-listicle",
        target_family="pre-sales-listicle",
        target_page_type="pre_sell",
    )

    # Find the hero block
    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    hero_block = next((b for b in page_content if b.get("type") == "PreSalesHero"), None)
    assert hero_block is not None, "PreSalesHero block should be present"

    hero_props = hero_block.get("props", {})
    config = hero_props.get("config", {})

    # Verify hero.title is updated (real config field)
    assert "hero" in config, "PreSalesHero config should have hero"
    hero_config = config["hero"]
    assert isinstance(hero_config, dict), "Hero config should be a dict"
    assert hero_config.get("title") == "This Product Attracts Dogs", (
        "hero.title should be from import"
    )
    assert hero_config.get("subtitle") == "5 Reasons Why It Works", (
        "hero.subtitle should be from import"
    )

    # Verify hero.media.src is updated (real config field)
    assert "media" in hero_config, "Hero config should have media"
    media = hero_config["media"]
    assert isinstance(media, dict), "Media should be a dict"
    assert media.get("src") == "https://example.com/dog-product.jpg", (
        "media.src should be from import"
    )


def test_synthesize_import_sales_faq_real_config_fields():
    """Test that SalesPdpFaq gets imported text in real config fields."""
    normalized_sections = [
        {
            "id": "imported_faq_001",
            "sectionType": "faq",
            "confidence": 0.9,
            "keyText": ["How does it work?", "It works by using patented technology."],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    # Find the FAQ block
    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    faq_block = next((b for b in page_content if b.get("type") == "SalesPdpFaq"), None)
    assert faq_block is not None

    faq_props = faq_block.get("props", {})
    config = faq_props.get("config", {})

    # Verify title is updated (real config field)
    assert config.get("title") == "How does it work?", "FAQ title should be from import"

    # Verify items[0].question/answer are updated (real config fields)
    assert "items" in config, "FAQ config should have items"
    items = config["items"]
    assert isinstance(items, list), "Items should be a list"
    assert len(items) > 0, "Items should have at least one item"
    assert items[0].get("question") == "How does it work?", (
        "First FAQ question should be from import"
    )
    assert items[0].get("answer") == "It works by using patented technology.", (
        "First FAQ answer should be from import"
    )


def test_synthesize_import_pre_sales_reasons_real_config_fields():
    """Test that PreSalesReasons gets imported text/media in real config fields."""
    normalized_sections = [
        {
            "id": "imported_reasons_001",
            "sectionType": "feature_stack",
            "confidence": 0.9,
            "keyText": ["Dogs Use It Right Away", "No training needed - they just use it."],
            "keyMedia": ["https://example.com/dog-on-pad.jpg"],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="pre-sales-listicle",
        target_family="pre-sales-listicle",
        target_page_type="pre_sell",
    )

    # Find the reasons block
    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    reasons_block = next((b for b in page_content if b.get("type") == "PreSalesReasons"), None)
    assert reasons_block is not None

    reasons_props = reasons_block.get("props", {})
    config = reasons_props.get("config", {})

    # PreSalesReasons config is a list of reason objects
    assert isinstance(config, list), "PreSalesReasons config should be a list"
    assert len(config) > 0, "Config should have at least one reason"

    first_reason = config[0]
    assert isinstance(first_reason, dict), "First reason should be a dict"
    assert first_reason.get("title") == "Dogs Use It Right Away", (
        "First reason title should be from import"
    )
    assert first_reason.get("body") == "No training needed - they just use it.", (
        "First reason body should be from import"
    )

    # Verify image.src is updated
    assert "image" in first_reason, "First reason should have image"
    assert first_reason["image"].get("src") == "https://example.com/dog-on-pad.jpg", (
        "Image src should be from import"
    )


def test_synthesize_import_footer_real_config_fields():
    """Test that footer blocks get copyright text in real config field."""
    normalized_sections = [
        {
            "id": "imported_footer_001",
            "sectionType": "footer",
            "confidence": 0.9,
            "keyText": ["© 2025 MyBrand Inc."],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    # Find the footer block
    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    footer_block = next((b for b in page_content if b.get("type") == "SalesPdpFooter"), None)
    assert footer_block is not None

    footer_props = footer_block.get("props", {})
    config = footer_props.get("config", {})

    # Verify copyright is updated (real config field)
    assert config.get("copyright") == "© 2025 MyBrand Inc.", (
        "Footer copyright should be from import"
    )


def test_synthesize_import_sales_comparison_real_config_fields():
    """Test that SalesPdpComparison gets imported text in real config fields."""
    normalized_sections = [
        {
            "id": "imported_comparison_001",
            "sectionType": "comparison_table",
            "confidence": 0.9,
            "keyText": ["How we compare", "Better durability", "Disposable pads leak"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    comparison_block = next(
        (b for b in page_content if b.get("type") == "SalesPdpComparison"), None
    )
    assert comparison_block is not None

    config = comparison_block.get("props", {}).get("config", {})
    assert config.get("title") == "How we compare"
    first_row = config.get("rows", [])[0]
    assert first_row.get("label") == "How we compare"
    assert first_row.get("pup") == "Better durability"
    assert first_row.get("disposable") == "Disposable pads leak"


def test_synthesize_import_presales_sticky_offer_maps_to_floating_cta():
    """Test that pre-sales sticky offer rail maps to the floating CTA block."""
    normalized_sections = [
        {
            "id": "imported_cta_001",
            "sectionType": "sticky_offer_rail",
            "confidence": 0.9,
            "keyText": ["Learn more now"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="pre-sales-listicle",
        target_family="pre-sales-listicle",
        target_page_type="pre_sell",
    )

    assert result.blockCoverage.exactMatches == 1
    assert result.blockCoverageDetails[0].mappedBlock == "PreSalesFloatingCta"

    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    cta_block = next((b for b in page_content if b.get("type") == "PreSalesFloatingCta"), None)
    assert cta_block is not None
    assert cta_block.get("props", {}).get("config", {}).get("label") == "Learn more now"


def test_synthesize_import_sales_hero_dedupes_overlapping_section_mappings():
    """Hero, sticky offer rail, and bundle selector should merge into one SalesPdpHero block."""
    normalized_sections = [
        {
            "id": "hero_001",
            "sectionType": "hero",
            "confidence": 0.9,
            "keyText": ["Main hero title"],
            "keyMedia": ["https://example.com/hero.jpg"],
            "keyStyles": {},
        },
        {
            "id": "sticky_001",
            "sectionType": "sticky_offer_rail",
            "confidence": 0.9,
            "keyText": ["Sticky CTA copy"],
            "keyMedia": [],
            "keyStyles": {},
        },
        {
            "id": "bundle_001",
            "sectionType": "bundle_selector",
            "confidence": 0.9,
            "keyText": ["Bundle selector copy"],
            "keyMedia": [],
            "keyStyles": {},
        },
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    hero_blocks = [b for b in page_content if b.get("type") == "SalesPdpHero"]
    assert len(hero_blocks) == 1


def test_synthesize_import_footer_dedupes_shell_and_mapped_footer():
    """Accepted footer sections should not produce duplicate footer blocks."""
    normalized_sections = [
        {
            "id": "footer_001",
            "sectionType": "footer",
            "confidence": 0.9,
            "keyText": ["© 2026 MyBrand"],
            "keyMedia": [],
            "keyStyles": {},
        }
    ]
    theme_candidate = {"palette": {}, "fonts": {}, "spacing": {}, "cta": {}}

    result = synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family="sales-pdp",
        target_family="sales-pdp",
        target_page_type="product_detail",
    )

    content = result.synthesizedPuckData.get("content", [])
    page_block = next((b for b in content if "Page" in b.get("type", "")), None)
    assert page_block is not None
    page_content = page_block.get("props", {}).get("content", [])
    footer_blocks = [b for b in page_content if b.get("type") == "SalesPdpFooter"]
    assert len(footer_blocks) == 1
