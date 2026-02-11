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
