import json

import pytest

from app.services import funnel_testimonials


def _sample_testimonial(
    *,
    name: str,
    review: str,
    reply_name: str,
    reply_persona: str,
    reply_text: str,
    reply_avatar_prompt: str = "Reply avatar prompt",
) -> dict[str, object]:
    return {
        "name": name,
        "verified": True,
        "rating": 5,
        "review": review,
        "persona": "Persona",
        "avatarPrompt": "Avatar prompt",
        "heroImagePrompt": "Hero prompt",
        "reply": {
            "name": reply_name,
            "persona": reply_persona,
            "text": reply_text,
            "avatarPrompt": reply_avatar_prompt,
            "time": "2d",
            "reactionCount": 3,
        },
    }


def _group(label: str) -> funnel_testimonials._TestimonialGroup:
    render = funnel_testimonials._TestimonialRenderTarget(
        image={},
        label=label,
        template="review_card",
    )
    return funnel_testimonials._TestimonialGroup(
        label=label,
        renders=[render],
    )


def test_social_comment_without_attachment_indices_empty_for_small_totals():
    assert funnel_testimonials._select_social_comment_without_attachment_indices(0, seed=123) == set()
    assert funnel_testimonials._select_social_comment_without_attachment_indices(1, seed=123) == set()


def test_social_comment_without_attachment_indices_selects_some_but_not_all():
    indices = funnel_testimonials._select_social_comment_without_attachment_indices(8, seed=123)
    assert indices
    assert len(indices) < 8
    assert all(0 <= idx < 8 for idx in indices)
    assert indices == funnel_testimonials._select_social_comment_without_attachment_indices(8, seed=123)


def test_review_card_without_hero_indices_empty_for_small_totals():
    assert funnel_testimonials._select_review_card_without_hero_indices(0, seed=123) == set()
    assert funnel_testimonials._select_review_card_without_hero_indices(1, seed=123) == set()


def test_review_card_without_hero_indices_selects_some_but_not_all():
    indices = funnel_testimonials._select_review_card_without_hero_indices(10, seed=123)
    assert indices
    assert len(indices) < 10
    assert all(0 <= idx < 10 for idx in indices)
    assert indices == funnel_testimonials._select_review_card_without_hero_indices(10, seed=123)


def test_variability_index_selectors_reject_negative_totals():
    with pytest.raises(funnel_testimonials.TestimonialGenerationError):
        funnel_testimonials._select_social_comment_without_attachment_indices(-1, seed=123)

    with pytest.raises(funnel_testimonials.TestimonialGenerationError):
        funnel_testimonials._select_review_card_without_hero_indices(-1, seed=123)


def test_sales_pdp_reviews_payload_prefers_slider_groups():
    testimonials = [
        _sample_testimonial(
            name="Wall Name",
            review="Wall review",
            reply_name="Wall Reply",
            reply_persona="Wall persona",
            reply_text="Wall reply text",
        ),
        _sample_testimonial(
            name="Slider Name",
            review="Slider review",
            reply_name="Slider Reply",
            reply_persona="Slider persona",
            reply_text="Slider reply text",
        ),
    ]
    groups = [
        _group("sales_pdp.reviewWall.tiles[0].image"),
        _group("sales_pdp.reviewSlider.slides[0].images[0]"),
    ]

    selected = funnel_testimonials._select_sales_pdp_reviews_payload_testimonials(
        groups=groups,
        validated_testimonials=testimonials,
    )

    assert len(selected) == 1
    assert selected[0]["name"] == "Slider Name"
    assert selected[0]["review"] == "Slider review"
    assert selected[0] is not testimonials[1]


def test_sales_pdp_reviews_payload_derives_distinct_reviews_without_slider():
    testimonials = [
        _sample_testimonial(
            name="Original Name 1",
            review="Original review 1",
            reply_name="Reply Name 1",
            reply_persona="Reply persona 1",
            reply_text="Reply review 1",
            reply_avatar_prompt="Reply avatar 1",
        ),
        _sample_testimonial(
            name="Original Name 2",
            review="Original review 2",
            reply_name="Reply Name 2",
            reply_persona="Reply persona 2",
            reply_text="Reply review 2",
            reply_avatar_prompt="Reply avatar 2",
        ),
    ]
    groups = [
        _group("sales_pdp.reviewWall.tiles[0].image"),
        _group("sales_pdp.reviewWall.tiles[1].image"),
    ]

    selected = funnel_testimonials._select_sales_pdp_reviews_payload_testimonials(
        groups=groups,
        validated_testimonials=testimonials,
    )

    assert len(selected) == 2
    assert selected[0]["name"] == "Reply Name 1"
    assert selected[0]["persona"] == "Reply persona 1"
    assert selected[0]["review"] == "Reply review 1"
    assert selected[0]["avatarPrompt"] == "Reply avatar 1"
    assert selected[1]["name"] == "Reply Name 2"
    assert selected[1]["review"] == "Reply review 2"
    assert testimonials[0]["name"] == "Original Name 1"
    assert testimonials[0]["review"] == "Original review 1"


def test_sales_pdp_reviews_payload_rejects_count_mismatch():
    testimonials = [
        _sample_testimonial(
            name="Name",
            review="Review",
            reply_name="Reply",
            reply_persona="Persona",
            reply_text="Reply text",
        )
    ]
    groups = [
        _group("sales_pdp.reviewWall.tiles[0].image"),
        _group("sales_pdp.reviewSlider.slides[0].images[0]"),
    ]

    with pytest.raises(
        funnel_testimonials.TestimonialGenerationError,
        match="target count does not match",
    ):
        funnel_testimonials._select_sales_pdp_reviews_payload_testimonials(
            groups=groups,
            validated_testimonials=testimonials,
        )


def test_sync_sales_pdp_guarantee_feed_images_updates_primary_guarantee_image():
    puck_data = {
        "content": [
            {
                "type": "SalesPdpGuarantee",
                "props": {
                    "config": {"right": {"image": {"src": "/assets/old.webp", "alt": "Old"}}},
                    "configJson": json.dumps({"right": {"image": {"src": "/assets/old-json.webp", "alt": "Old JSON"}}}),
                    "feedImages": [{"src": "/assets/old-feed.webp", "alt": "Old feed"}],
                    "feedImagesJson": json.dumps([{"src": "/assets/old-feed-json.webp", "alt": "Old feed JSON"}]),
                },
            }
        ],
        "zones": {},
    }
    review_wall_images = [
        {
            "src": "/assets/new-1.webp",
            "alt": "Customer review 1",
            "assetPublicId": "public-id-1",
            "testimonialTemplate": "social_comment",
        },
        {
            "src": "/assets/new-2.webp",
            "alt": "Customer review 2",
            "assetPublicId": "public-id-2",
            "testimonialTemplate": "review_card",
        },
    ]

    funnel_testimonials._sync_sales_pdp_guarantee_feed_images(
        puck_data,
        review_wall_images=review_wall_images,
    )

    props = puck_data["content"][0]["props"]
    assert props["feedImages"] == review_wall_images
    assert json.loads(props["feedImagesJson"]) == review_wall_images
    assert props["config"]["right"]["image"] == review_wall_images[0]
    assert json.loads(props["configJson"])["right"]["image"] == review_wall_images[0]


def test_sync_sales_pdp_guarantee_feed_images_defaults_primary_template_when_missing():
    puck_data = {
        "content": [
            {
                "type": "SalesPdpGuarantee",
                "props": {
                    "config": {"right": {"image": {"src": "/assets/old.webp", "alt": "Old"}}},
                },
            }
        ],
        "zones": {},
    }
    review_wall_images = [{"src": "/assets/new-1.webp", "alt": "Customer review 1", "assetPublicId": "public-id-1"}]

    funnel_testimonials._sync_sales_pdp_guarantee_feed_images(
        puck_data,
        review_wall_images=review_wall_images,
    )

    primary_image = puck_data["content"][0]["props"]["config"]["right"]["image"]
    assert primary_image["testimonialTemplate"] == "review_card"
