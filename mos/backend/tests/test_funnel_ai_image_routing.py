import ast
import json
from types import SimpleNamespace

import pytest

from app.services import funnel_ai


def _puck_with_images(images: list[dict[str, object]]) -> dict[str, object]:
    return {
        "root": {"props": {}},
        "content": [{"type": "Image", "props": image} for image in images],
        "zones": {},
    }


def _pre_sales_hero_puck(*, badge_icon_src: str | None) -> dict[str, object]:
    badge: dict[str, object] = {
        "iconAlt": "Trust badge",
        "label": "FAST SHIPPING",
    }
    if badge_icon_src is not None:
        badge["iconSrc"] = badge_icon_src
    return {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [badge],
                    },
                },
            }
        ],
        "zones": {},
    }


def _icon_design_tokens() -> dict[str, object]:
    return {
        "cssVars": {
            "--color-brand": "#061a70",
            "--color-cta": "#3b8c33",
            "--color-cta-icon": "#2f6f29",
            "--badge-strip-bg": "#e9fbff",
            "--color-bg": "#ffffff",
        }
    }


def test_auto_routes_generic_lifestyle_prompts_to_unsplash():
    puck_data = _puck_with_images(
        [
            {
                "id": "hero-image",
                "alt": "Lifestyle scene",
                "prompt": "Candid lifestyle portrait in a bright kitchen with natural light.",
            }
        ]
    )

    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=[])
    planned = funnel_ai._ensure_unsplash_usage(plans, puck_data=puck_data, config_contexts=[])

    assert len(planned) == 1
    assert planned[0]["imageSource"] == "unsplash"
    assert puck_data["content"][0]["props"]["imageSource"] == "unsplash"


def test_routes_overly_specific_stock_scene_to_ai():
    puck_data = _puck_with_images(
        [
            {
                "id": "concept-scene",
                "alt": "Concept scene",
                "prompt": (
                    "Lifestyle flat lay of a calendar with skincare routine tracking, "
                    "LED face mask visible in corner, gradual progress concept, "
                    "natural light, clean aesthetic, square 1:1 aspect ratio."
                ),
            }
        ]
    )

    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=[])
    planned = funnel_ai._ensure_unsplash_usage(plans, puck_data=puck_data, config_contexts=[])

    assert len(planned) == 1
    assert planned[0]["imageSource"] == "ai"
    assert planned[0]["routingSuggestedImageSource"] == "ai"
    assert "too specific for reliable stock search" in planned[0]["routingReason"]
    assert "imageSource" not in puck_data["content"][0]["props"]


def test_collect_image_plans_unsplash_reference_error_includes_details():
    puck_data = _puck_with_images(
        [
            {
                "id": "hero-image",
                "alt": "Lifestyle scene",
                "prompt": "Candid lifestyle portrait in a bright kitchen with natural light.",
                "imageSource": "unsplash",
                "referenceAssetPublicId": "reference-public-id",
            }
        ]
    )

    with pytest.raises(funnel_ai.AiAttachmentError) as exc_info:
        funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=[])

    message = str(exc_info.value)
    assert "Unsplash images do not support referenceAssetPublicId." in message
    assert "details=" in message

    details = ast.literal_eval(message.split("details=", maxsplit=1)[1])
    assert details["path"] == "puckData.content[0].props"
    assert details["assetKey"] == "assetPublicId"
    assert details["imageSource"] == "unsplash"
    assert details["referenceAssetPublicId"] == "reference-public-id"
    assert details["hasPrompt"] is True


def test_pre_sales_badge_icons_are_repaired_from_fallback_template():
    puck_data = _pre_sales_hero_puck(badge_icon_src=None)
    fallback_puck = _pre_sales_hero_puck(badge_icon_src="/assets/free-shipping-icon.webp")

    funnel_ai._ensure_pre_sales_badge_icons(
        puck_data=puck_data,
        config_contexts=[],
        fallback_puck_data=fallback_puck,
    )

    badges = puck_data["content"][0]["props"]["config"]["badges"]
    assert badges[0]["iconSrc"] == "/assets/free-shipping-icon.webp"
    funnel_ai._validate_required_template_images(puck_data=puck_data, config_contexts=[])


def test_icon_remix_uses_existing_badge_icon_asset_and_brand_colors():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/5-stars-reviews-icon.webp",
                                "iconAlt": "5 star reviews",
                                "label": "5-STAR REVIEWS",
                                "iconAssetPublicId": "base-icon-public-id",
                                "prompt": "Trust badge icon with stars and paw",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }
    design_tokens = {
        "cssVars": {
            "--color-brand": "#061a70",
            "--color-cta": "#3b8c33",
            "--color-cta-icon": "#2f6f29",
            "--badge-strip-bg": "#e9fbff",
            "--color-bg": "#ffffff",
        }
    }

    funnel_ai._apply_icon_remix_overrides_for_ai(
        puck_data=puck_data,
        config_contexts=[],
        fallback_puck_data=None,
        design_system_tokens=design_tokens,
    )

    badge = puck_data["content"][0]["props"]["config"]["badges"][0]
    assert badge["referenceAssetPublicId"] == "base-icon-public-id"
    assert "iconAssetPublicId" not in badge
    assert "brand color palette" in badge["prompt"]
    assert "#061a70" in badge["prompt"]
    assert "#3b8c33" in badge["prompt"]


def test_icon_remix_resolves_reference_from_template_icon_src():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/free-shipping-icon.webp",
                                "iconAlt": "Free shipping",
                                "label": "FAST SHIPPING",
                                "prompt": "Shipping icon with delivery motion lines",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }
    fallback_puck = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/free-shipping-icon.webp",
                                "iconAlt": "Free shipping",
                                "label": "FAST SHIPPING",
                                "iconAssetPublicId": "template-free-shipping-id",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }
    design_tokens = {
        "cssVars": {
            "--color-brand": "#061a70",
            "--color-cta": "#3b8c33",
            "--color-cta-icon": "#2f6f29",
            "--badge-strip-bg": "#e9fbff",
            "--color-bg": "#ffffff",
        }
    }

    funnel_ai._apply_icon_remix_overrides_for_ai(
        puck_data=puck_data,
        config_contexts=[],
        fallback_puck_data=fallback_puck,
        design_system_tokens=design_tokens,
    )

    badge = puck_data["content"][0]["props"]["config"]["badges"][0]
    assert badge["referenceAssetPublicId"] == "template-free-shipping-id"


def test_icon_prompt_normalization_uses_context_subject_for_pre_sales_badge():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/free-shipping-icon.webp",
                                "iconAlt": "Free shipping",
                                "label": "FAST SHIPPING",
                                "prompt": "Shipping icon with delivery motion lines",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }

    design_tokens = _icon_design_tokens()

    funnel_ai._ensure_flat_vector_icon_prompts(
        puck_data=puck_data,
        config_contexts=[],
        design_system_tokens=design_tokens,
    )

    badge = puck_data["content"][0]["props"]["config"]["badges"][0]
    assert badge["prompt"].startswith(funnel_ai._ICON_STYLE_PROMPT_TEMPLATE.format(subject="Free shipping"))
    assert "Use this exact brand color palette for the icon:" in badge["prompt"]
    assert "#061a70" in badge["prompt"]
    assert badge["aspectRatio"] == "1:1"


def test_icon_prompt_normalization_uses_context_subject_for_free_gifts_overlay():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "SalesPdpHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "gallery": {
                            "freeGifts": {
                                "icon": {
                                    "iconSrc": "",
                                    "alt": "Free gift icon",
                                    "prompt": "Simple flat icon of gift box with ribbon, transparent background",
                                },
                                "title": "3 Free Gifts Today Only",
                                "body": "Preview the gifts.",
                                "ctaLabel": "Preview",
                            }
                        }
                    },
                },
            }
        ],
        "zones": {},
    }

    design_tokens = _icon_design_tokens()

    funnel_ai._ensure_flat_vector_icon_prompts(
        puck_data=puck_data,
        config_contexts=[],
        design_system_tokens=design_tokens,
    )

    icon = puck_data["content"][0]["props"]["config"]["gallery"]["freeGifts"]["icon"]
    assert icon["prompt"].startswith(funnel_ai._ICON_STYLE_PROMPT_TEMPLATE.format(subject="Free gift"))
    assert "Use this exact brand color palette for the icon:" in icon["prompt"]
    assert "#061a70" in icon["prompt"]
    assert icon["aspectRatio"] == "1:1"


def test_icon_prompt_normalization_requires_clear_subject():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "Image",
                "props": {
                    "id": "icon",
                    "iconSrc": "",
                    "prompt": "High-quality flat design icon. Solid white background. No text, no blur.",
                },
            }
        ],
        "zones": {},
    }

    with pytest.raises(ValueError, match="Unable to infer subject"):
        funnel_ai._ensure_flat_vector_icon_prompts(puck_data=puck_data, config_contexts=[])


def test_icon_prompt_normalization_requires_brand_palette_tokens():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/free-shipping-icon.webp",
                                "iconAlt": "Free shipping",
                                "label": "FAST SHIPPING",
                                "prompt": "Shipping icon with delivery motion lines",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }

    with pytest.raises(ValueError, match="Icon generation requires brand color tokens"):
        funnel_ai._ensure_flat_vector_icon_prompts(
            puck_data=puck_data,
            config_contexts=[],
            design_system_tokens=None,
        )


def test_icon_remix_can_reuse_existing_reference_asset_ids_from_template():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/free-shipping-icon.webp",
                                "iconAlt": "Free shipping",
                                "label": "FAST SHIPPING",
                                "prompt": "Shipping icon with delivery motion lines",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }
    fallback_puck = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/free-shipping-icon.webp",
                                "iconAlt": "Free shipping",
                                "label": "FAST SHIPPING",
                                "referenceAssetPublicId": "template-reference-id",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }
    design_tokens = {
        "cssVars": {
            "--color-brand": "#061a70",
            "--color-cta": "#3b8c33",
            "--color-cta-icon": "#2f6f29",
            "--badge-strip-bg": "#e9fbff",
            "--color-bg": "#ffffff",
        }
    }

    funnel_ai._apply_icon_remix_overrides_for_ai(
        puck_data=puck_data,
        config_contexts=[],
        fallback_puck_data=fallback_puck,
        design_system_tokens=design_tokens,
    )

    badge = puck_data["content"][0]["props"]["config"]["badges"][0]
    assert badge["referenceAssetPublicId"] == "template-reference-id"


def test_icon_remix_requires_brand_colors():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/free-shipping-icon.webp",
                                "iconAlt": "Free shipping",
                                "label": "FAST SHIPPING",
                                "iconAssetPublicId": "template-free-shipping-id",
                                "prompt": "Shipping icon with delivery motion lines",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }

    with pytest.raises(ValueError, match="Icon remix generation requires brand color tokens"):
        funnel_ai._apply_icon_remix_overrides_for_ai(
            puck_data=puck_data,
            config_contexts=[],
            fallback_puck_data=None,
            design_system_tokens=None,
        )


def test_icon_remix_requires_template_icon_reference():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesHero",
                "props": {
                    "id": "hero",
                    "config": {
                        "hero": {"title": "Title", "subtitle": "Subtitle"},
                        "badges": [
                            {
                                "iconSrc": "/assets/unknown-icon.webp",
                                "iconAlt": "Unknown icon",
                                "label": "MISSING",
                                "prompt": "Unknown badge icon",
                            }
                        ],
                    },
                },
            }
        ],
        "zones": {},
    }
    design_tokens = {
        "cssVars": {
            "--color-brand": "#061a70",
            "--color-cta": "#3b8c33",
            "--color-cta-icon": "#2f6f29",
            "--badge-strip-bg": "#e9fbff",
            "--color-bg": "#ffffff",
        }
    }

    with pytest.raises(ValueError, match="Unable to resolve referenceAssetPublicId"):
        funnel_ai._apply_icon_remix_overrides_for_ai(
            puck_data=puck_data,
            config_contexts=[],
            fallback_puck_data=None,
            design_system_tokens=design_tokens,
        )


def test_sales_guarantee_images_are_locked_to_testimonial_only_sources():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "SalesPdpGuarantee",
                "props": {
                    "id": "guarantee",
                    "configJson": json.dumps(
                        {
                            "id": "guarantee",
                            "badge": "NO RISK PROMISE",
                            "title": "Try Risk-Free",
                            "paragraphs": ["A", "B"],
                            "whyTitle": "Why",
                            "whyBody": "Because",
                            "closingLine": "Close",
                            "right": {
                                "image": {
                                    "alt": "Customer photo",
                                    "prompt": "Lifestyle customer photo",
                                    "imageSource": "unsplash",
                                },
                                "reviewCard": {
                                    "name": "A",
                                    "verifiedLabel": "Verified",
                                    "rating": 5,
                                    "text": "Great",
                                },
                                "commentThread": {"label": "Scroll", "comments": []},
                            },
                        }
                    ),
                    "feedImagesJson": json.dumps(
                        [
                            {
                                "alt": "Feed 1",
                                "prompt": "UGC selfie",
                                "imageSource": "unsplash",
                                "referenceAssetPublicId": "should-be-cleared",
                            }
                        ]
                    ),
                },
            }
        ],
        "zones": {},
    }
    config_contexts = funnel_ai._collect_config_json_contexts_all(puck_data)
    funnel_ai._enforce_sales_pdp_guarantee_testimonial_only_images(
        puck_data=puck_data,
        config_contexts=config_contexts,
    )
    funnel_ai._sync_config_json_contexts(config_contexts)

    guarantee_props = puck_data["content"][0]["props"]
    config = json.loads(guarantee_props["configJson"])
    guarantee_image = config["right"]["image"]
    feed_images = json.loads(guarantee_props["feedImagesJson"])

    assert guarantee_image["testimonialTemplate"] == "review_card"
    assert "prompt" not in guarantee_image
    assert "imageSource" not in guarantee_image

    assert feed_images[0]["testimonialTemplate"] == "review_card"
    assert "prompt" not in feed_images[0]
    assert "imageSource" not in feed_images[0]
    assert "referenceAssetPublicId" not in feed_images[0]

    plan_contexts = funnel_ai._collect_config_json_contexts_all(puck_data)
    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=plan_contexts)
    assert plans == []


def test_collect_image_plans_normalizes_sales_guarantee_slots_to_testimonial_targets():
    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "SalesPdpGuarantee",
                "props": {
                    "id": "guarantee",
                    "configJson": json.dumps(
                        {
                            "id": "guarantee",
                            "badge": "NO RISK PROMISE",
                            "title": "Try Risk-Free",
                            "paragraphs": ["A", "B"],
                            "whyTitle": "Why",
                            "whyBody": "Because",
                            "closingLine": "Close",
                            "right": {
                                "image": {
                                    "alt": "Customer photo",
                                    "prompt": "Lifestyle customer photo",
                                    "imageSource": "unsplash",
                                },
                                "reviewCard": {
                                    "name": "A",
                                    "verifiedLabel": "Verified",
                                    "rating": 5,
                                    "text": "Great",
                                },
                                "commentThread": {"label": "Scroll", "comments": []},
                            },
                        }
                    ),
                    "feedImagesJson": json.dumps(
                        [
                            {
                                "alt": "Feed 1",
                                "prompt": "UGC selfie",
                                "imageSource": "unsplash",
                            }
                        ]
                    ),
                },
            }
        ],
        "zones": {},
    }

    config_contexts = funnel_ai._collect_config_json_contexts_all(puck_data)
    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=config_contexts)
    funnel_ai._sync_config_json_contexts(config_contexts)

    assert plans == []
    config = json.loads(puck_data["content"][0]["props"]["configJson"])
    feed_images = json.loads(puck_data["content"][0]["props"]["feedImagesJson"])
    assert config["right"]["image"]["testimonialTemplate"] == "review_card"
    assert "prompt" not in config["right"]["image"]
    assert feed_images[0]["testimonialTemplate"] == "review_card"
    assert "prompt" not in feed_images[0]


def test_keeps_ai_for_product_specific_prompts():
    puck_data = _puck_with_images(
        [
            {
                "id": "product-image",
                "alt": "Product in use",
                "prompt": "Contextual lifestyle scene. Include the product prominently.",
            }
        ]
    )

    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=[])
    planned = funnel_ai._ensure_unsplash_usage(plans, puck_data=puck_data, config_contexts=[])

    assert len(planned) == 1
    assert planned[0]["imageSource"] == "ai"
    assert planned[0]["routingExplicit"] is False
    assert planned[0]["routingSuggestedImageSource"] == "ai"
    assert "imageSource" not in puck_data["content"][0]["props"]


def test_respects_explicit_image_source_over_auto_routing():
    puck_data = _puck_with_images(
        [
            {
                "id": "explicit-ai-image",
                "alt": "Scene",
                "prompt": "Lifestyle portrait in a home office.",
                "imageSource": "ai",
            }
        ]
    )

    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=[])
    planned = funnel_ai._ensure_unsplash_usage(plans, puck_data=puck_data, config_contexts=[])

    assert len(planned) == 1
    assert planned[0]["imageSource"] == "ai"
    assert planned[0]["routingExplicit"] is True
    assert "Explicit imageSource='ai'" in planned[0]["routingReason"]
    assert puck_data["content"][0]["props"]["imageSource"] == "ai"


def test_image_generation_count_enforces_hard_cap():
    images = [
        {
            "id": f"img-{idx}",
            "alt": "Scene",
            "prompt": f"Lifestyle stock scene {idx}",
        }
        for idx in range(51)
    ]
    puck_data = _puck_with_images(images)
    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=[])

    with pytest.raises(ValueError, match="Refusing to generate 51 images"):
        funnel_ai._resolve_image_generation_count(puck_data=puck_data, image_plans=plans)


def test_image_generation_count_allows_up_to_cap():
    images = [
        {
            "id": f"img-{idx}",
            "alt": "Scene",
            "prompt": f"Lifestyle stock scene {idx}",
        }
        for idx in range(50)
    ]
    puck_data = _puck_with_images(images)
    plans = funnel_ai._collect_image_plans(puck_data=puck_data, config_contexts=[])

    count = funnel_ai._resolve_image_generation_count(puck_data=puck_data, image_plans=plans)
    assert count == 50


def test_pre_sales_reasons_always_use_product_reference_image(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        funnel_ai,
        "_collect_product_image_public_ids",
        lambda **_: ["prod-ref-public-id"],
    )

    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "PreSalesReasons",
                "props": {
                    "id": "reasons",
                    "config": [
                        {
                            "number": 1,
                            "title": "Designed for nightly routines",
                            "body": "Relaxing evening use in a calm bedroom setting.",
                            "image": {
                                "prompt": "Lifestyle scene in a bedroom with warm lamps.",
                                "imageSource": "unsplash",
                            },
                        },
                        {
                            "number": 2,
                            "title": "Evidence backed treatment",
                            "body": "This mask is designed with clinically studied wavelengths.",
                            "image": {
                                "prompt": "Product close-up with clean white background.",
                                "imageSource": "unsplash",
                            },
                        },
                    ],
                },
            }
        ],
        "zones": {},
    }

    product = SimpleNamespace(
        id="product-1",
        primary_asset_id=None,
        product_type="skincare device",
        title="Radiant LED Mask",
        description="Cordless LED therapy face mask",
    )

    funnel_ai._apply_product_image_overrides_for_ai(
        session=None,
        org_id="org-1",
        client_id="client-1",
        puck_data=puck_data,
        config_contexts=[],
        template_kind="pre-sales-listicle",
        product=product,
    )

    reasons = puck_data["content"][0]["props"]["config"]
    for reason in reasons:
        image = reason["image"]
        assert image["referenceAssetPublicId"] == "prod-ref-public-id"
        assert image["imageSource"] == "ai"
        assert image["aspectRatio"] == "1:1"


def test_extract_image_prompt_target_normalizes_same_asset_and_reference_id():
    image = {
        "prompt": "Product scene in natural light.",
        "assetPublicId": "same-public-id",
        "referenceAssetPublicId": "same-public-id",
        "imageSource": "ai",
        "alt": "Product image",
    }

    target = funnel_ai._extract_image_prompt_target(image, "assetPublicId")

    assert target is not None
    prompt, reference_public_id, image_source, aspect_ratio = target
    assert prompt == "Product scene in natural light."
    assert reference_public_id == "same-public-id"
    assert image_source == "ai"
    assert aspect_ratio is None
    assert "assetPublicId" not in image
