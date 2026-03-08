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


def test_collect_testimonial_targets_prefers_config_json_over_stale_config_for_sales_review_wall():
    puck_data = {
        "content": [
            {
                "type": "SalesPdpReviewWall",
                "props": {
                    "config": {"id": "reviews", "tiles": []},
                    "configJson": json.dumps(
                        {
                            "id": "reviews",
                            "tiles": [
                                {
                                    "id": "tile-1",
                                    "image": {
                                        "alt": "Customer review",
                                        "testimonialTemplate": "review_card",
                                    },
                                }
                            ],
                        }
                    ),
                },
            }
        ]
    }

    groups, contexts = funnel_testimonials._collect_testimonial_targets(
        puck_data=puck_data,
        template_kind="sales-pdp",
    )

    assert len(groups) == 1
    assert groups[0].label == "sales_pdp.reviewWall.tiles[0]"
    assert groups[0].renders[0].label == "sales_pdp.reviewWall.tiles[0]"
    assert len(contexts) == 1


def test_collect_sales_pdp_carousel_slots_truncates_to_expected_count():
    puck_data = {
        "content": [
            {
                "type": "SalesPdpHero",
                "props": {
                    "config": {
                        "gallery": {
                            "slides": [
                                {"src": f"/assets/slide-{idx}.webp", "alt": f"Slide {idx}"}
                                for idx in range(7)
                            ]
                        }
                    }
                },
            }
        ]
    }

    slots, contexts = funnel_testimonials._collect_sales_pdp_carousel_slots(puck_data, expected_count=6)

    assert len(slots) == 6
    assert all(len(slot) == 1 for slot in slots)
    assert len(contexts) == 0
    slides = puck_data["content"][0]["props"]["config"]["gallery"]["slides"]
    assert len(slides) == 6
    assert slots[0][0].label == "sales_pdp.hero.gallery.slides[0]"
    assert slots[5][0].label == "sales_pdp.hero.gallery.slides[5]"


def test_collect_sales_pdp_carousel_slots_appends_missing_slides():
    puck_data = {
        "content": [
            {
                "type": "SalesPdpHero",
                "props": {
                    "config": {
                        "gallery": {
                            "slides": [
                                {"src": f"/assets/slide-{idx}.webp", "alt": f"Slide {idx}"}
                                for idx in range(4)
                            ]
                        }
                    }
                },
            }
        ]
    }

    slots, _ = funnel_testimonials._collect_sales_pdp_carousel_slots(puck_data, expected_count=6)

    assert len(slots) == 6
    assert all(len(slot) == 1 for slot in slots)
    slides = puck_data["content"][0]["props"]["config"]["gallery"]["slides"]
    assert len(slides) == 6
    assert slides[4]["alt"] == "Sales PDP carousel image 5"
    assert slides[5]["alt"] == "Sales PDP carousel image 6"


def test_sales_pdp_carousel_variant_contract_matches_requested_examples():
    variants = [spec["variantId"] for spec in funnel_testimonials._SALES_PDP_CAROUSEL_VARIANTS]
    assert variants == [
        "standard_ugc",
        "qa_ugc",
        "bold_claim",
        "personal_highlight",
        "dorm_selfie",
    ]

    sample_inputs = [spec["sampleInput"] for spec in funnel_testimonials._SALES_PDP_CAROUSEL_VARIANTS]
    assert sample_inputs == [
        "testimonial-renderer/samples/inputs/pdp_example1_standard_ugc_nano.json",
        "testimonial-renderer/samples/inputs/pdp_example2_qa_nano.json",
        "testimonial-renderer/samples/inputs/pdp_example3_bold_claim_nano.json",
        "testimonial-renderer/samples/inputs/pdp_example4_personal_highlight_nano.json",
        "testimonial-renderer/samples/inputs/pdp_example5_dorm_selfie_nano.json",
    ]


def test_validate_sales_pdp_carousel_plan_rejects_missing_variant_id():
    payload = {
        "slides": [
            {
                "variantId": "standard_ugc",
                "template": "pdp_ugc_standard",
                "logoText": "Brand",
                "stripBgColor": "#123456",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.9/5",
                "ratingDetailText": "Rated by users",
                "ctaText": "See why",
                "commentHandle": "user_one",
                "commentText": "Great fit for my routine.",
                "commentVerified": True,
                "backgroundPromptVars": {
                    "product": "Product in hand",
                    "subject": "Customer selfie",
                    "scene": "Kitchen morning light",
                    "extra": "Natural smartphone framing.",
                    "avoid": ["watermarks"],
                },
            },
            {
                "variantId": "qa_ugc",
                "template": "pdp_qa_ugc",
                "logoText": "Brand",
                "stripBgColor": "#123456",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.9/5",
                "ratingDetailText": "Rated by users",
                "ctaText": "See why",
                "qaQuestionText": "Does it actually work or is it hype?",
                "commentHandle": "user_two",
                "commentText": "I asked if it was hype and it wasn't.",
                "commentVerified": True,
                "backgroundPromptVars": {
                    "product": "Product bottle close-up",
                    "subject": "Customer pointing to product",
                    "scene": "Bedroom daylight",
                    "extra": "Question-answer reaction vibe.",
                    "avoid": ["watermarks"],
                },
            },
            {
                "variantId": "bold_claim",
                "template": "pdp_bold_claim",
                "logoText": "Brand",
                "stripBgColor": "#123456",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.9/5",
                "ratingDetailText": "Rated by users",
                "ctaText": "See why",
                "commentHandle": "user_three",
                "commentText": "Best value in my stack.",
                "commentVerified": True,
                "backgroundPromptVars": {
                    "product": "Product on countertop",
                    "scene": "Clean tabletop",
                    "extra": "Product-forward composition.",
                    "avoid": ["watermarks"],
                },
            },
            {
                "variantId": "personal_highlight",
                "template": "pdp_personal_highlight",
                "logoText": "Brand",
                "stripBgColor": "#123456",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.9/5",
                "ratingDetailText": "Rated by users",
                "ctaText": "See why",
                "commentHandle": "user_four",
                "commentText": "This is my keep-using-it product.",
                "commentVerified": True,
                "backgroundPromptVars": {
                    "product": "Product with customer",
                    "subject": "Customer hugging product",
                    "scene": "Home office",
                    "extra": "Personal milestone moment.",
                    "avoid": ["watermarks"],
                },
            },
            {
                # Duplicate standard_ugc means dorm_selfie is missing.
                "variantId": "standard_ugc",
                "template": "pdp_ugc_standard",
                "logoText": "Brand",
                "stripBgColor": "#123456",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.9/5",
                "ratingDetailText": "Rated by users",
                "ctaText": "See why",
                "commentHandle": "user_five",
                "commentText": "Dorm vibe test",
                "commentVerified": True,
                "backgroundPromptVars": {
                    "product": "Product on desk",
                    "subject": "Younger user selfie",
                    "scene": "Messy dorm room",
                    "extra": "Unpolished social selfie style.",
                    "avoid": ["watermarks"],
                },
            },
        ]
    }

    with pytest.raises(
        funnel_testimonials.TestimonialGenerationError,
        match="Duplicate variantId in carousel plan: standard_ugc",
    ):
        funnel_testimonials._validate_sales_pdp_carousel_plan(payload)


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
