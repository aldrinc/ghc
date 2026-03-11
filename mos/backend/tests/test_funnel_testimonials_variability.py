import json
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.db.enums import AssetSourceEnum, AssetStatusEnum, FunnelStatusEnum
from app.db.models import Asset, Funnel, Product
from app.services import funnel_ai, funnel_testimonials


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


def _carousel_comment(handle: str, text: str, *, verified: bool = True) -> dict[str, object]:
    return {
        "handle": handle,
        "text": text,
        "verified": verified,
    }


def _sample_sales_pdp_page_puck() -> dict[str, object]:
    return {
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {
                            "type": "SalesPdpHero",
                            "props": {
                                "config": {
                                    "purchase": {
                                        "cta": {"labelTemplate": "Get the handbook - {price}"},
                                        "offer": {
                                            "options": [
                                                {"id": "single_book", "title": "Single Book", "price": 49.0},
                                                {"id": "bundle", "title": "Bundle", "price": 79.0},
                                            ]
                                        },
                                    }
                                }
                            },
                        },
                        {
                            "type": "SalesPdpReviews",
                            "props": {
                                "config": {
                                    "data": {
                                        "summary": {
                                            "averageRating": 4.9,
                                            "totalReviews": 2243,
                                        }
                                    }
                                }
                            },
                        },
                    ]
                },
            }
        ]
    }


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


def test_collect_testimonial_targets_includes_hidden_sales_review_wall_for_guarantee_feed():
    puck_data = _sample_sales_pdp_page_puck()
    puck_data["content"][0]["props"]["content"].append(
        {
            "type": "SalesPdpReviewWall",
            "props": {
                "hidden": True,
                "config": {
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
                },
            },
        }
    )

    groups, contexts = funnel_testimonials._collect_testimonial_targets(
        puck_data=puck_data,
        template_kind="sales-pdp",
    )

    assert len(groups) == 1
    assert groups[0].label == "sales_pdp.reviewWall.tiles[0]"
    assert len(contexts) == 0


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


def test_apply_sales_pdp_carousel_slot_asset_overwrites_stale_alt_text():
    target = funnel_testimonials._SalesPdpCarouselTarget(
        image={"assetPublicId": "old-public-id", "alt": "Placeholder slide"},
        label="sales_pdp.hero.gallery.slides[1]",
        slot_index=1,
        context=None,
    )

    funnel_testimonials._apply_sales_pdp_carousel_slot_asset(
        targets=[target],
        asset_public_id="new-public-id",
        default_alt="Sales PDP carousel image 2",
    )

    assert target.image["assetPublicId"] == "new-public-id"
    assert target.image["thumbAssetPublicId"] == "new-public-id"
    assert target.image["alt"] == "Sales PDP carousel image 2"


def test_select_sales_pdp_core_offer_image_prefers_default_offer_option():
    puck_data = {
        "content": [
            {
                "type": "SalesPdpHero",
                "props": {
                    "config": {
                        "purchase": {
                            "offer": {
                                "options": [
                                    {
                                        "id": "single",
                                        "title": "Single Book",
                                        "image": {"alt": "Single", "assetPublicId": "single-public-id"},
                                    },
                                    {
                                        "id": "bundle",
                                        "title": "2-Book Bundle",
                                        "image": {"alt": "Bundle", "assetPublicId": "bundle-public-id"},
                                    },
                                ]
                            },
                            "variantSchema": {
                                "defaults": {
                                    "offerId": "bundle",
                                }
                            },
                        }
                    }
                },
            }
        ]
    }

    selection = funnel_testimonials._select_sales_pdp_core_offer_image(puck_data)

    assert selection.asset_public_id == "bundle-public-id"
    assert selection.offer_id == "bundle"
    assert selection.offer_title == "2-Book Bundle"


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
        "testimonial-renderer/samples/inputs/pdp_example2_double_comment_nano.json",
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
                "comments": [
                    _carousel_comment("user_one", "Great fit for my routine."),
                ],
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
                "template": "pdp_ugc_standard",
                "logoText": "Brand",
                "stripBgColor": "#123456",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.9/5",
                "ratingDetailText": "Rated by users",
                "ctaText": "See why",
                "comments": [
                    _carousel_comment("user_two", "Does it actually work or is it hype?"),
                    _carousel_comment("trusted_reply", "It gives me a real screening workflow, not hype."),
                ],
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
                "comments": [
                    _carousel_comment("user_three", "Best value in my stack."),
                ],
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
                "comments": [
                    _carousel_comment("user_four", "This is my keep-using-it product."),
                ],
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
                "comments": [
                    _carousel_comment("user_five", "Dorm vibe test"),
                ],
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


def test_derive_sales_pdp_shared_banner_copy_uses_sales_page_config():
    shared_banner = funnel_testimonials._derive_sales_pdp_shared_banner_copy(_sample_sales_pdp_page_puck())

    assert shared_banner == {
        "ratingValueText": "4.9/5",
        "ratingDetailText": "Rated by 2,243 readers",
        "ctaText": "Get the handbook - $49",
    }


def test_normalize_sales_pdp_carousel_plan_unifies_bottom_banner_fields():
    payload = {
        "slides": [
            {
                "variantId": "standard_ugc",
                "template": "pdp_ugc_standard",
                "logoText": "Brand",
                "stripBgColor": "#2d4a3e",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.8/5",
                "ratingDetailText": "Slide one detail",
                "ctaText": "Slide one CTA",
                "comments": [
                    _carousel_comment("user_one", "Great fit for my routine."),
                ],
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
                "template": "pdp_ugc_standard",
                "logoText": "Brand",
                "stripBgColor": "#3b5c8a",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.7/5",
                "ratingDetailText": "Slide two detail",
                "ctaText": "Slide two CTA",
                "comments": [
                    _carousel_comment("user_two", "Does it actually work or is it hype?"),
                    _carousel_comment("trusted_reply", "It gives me a clearer process instead of shrugging."),
                ],
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
                "stripBgColor": "#1a3a2a",
                "stripTextColor": "#f5f0e8",
                "ratingValueText": "4.6/5",
                "ratingDetailText": "Slide three detail",
                "ctaText": "Slide three CTA",
                "comments": [
                    _carousel_comment("user_three", "Best value in my stack."),
                ],
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
                "stripBgColor": "#5c3d1e",
                "stripTextColor": "#fdf6ec",
                "ratingValueText": "4.5/5",
                "ratingDetailText": "Slide four detail",
                "ctaText": "Slide four CTA",
                "comments": [
                    _carousel_comment("user_four", "This is my keep-using-it product."),
                ],
                "backgroundPromptVars": {
                    "product": "Product with customer",
                    "subject": "Customer hugging product",
                    "scene": "Home office",
                    "extra": "Personal milestone moment.",
                    "avoid": ["watermarks"],
                },
            },
            {
                "variantId": "dorm_selfie",
                "template": "pdp_ugc_standard",
                "logoText": "Brand",
                "stripBgColor": "#4a3728",
                "stripTextColor": "#ffffff",
                "ratingValueText": "4.4/5",
                "ratingDetailText": "Slide five detail",
                "ctaText": "Slide five CTA",
                "comments": [
                    _carousel_comment("user_five", "Dorm vibe test"),
                ],
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

    validated = funnel_testimonials._validate_sales_pdp_carousel_plan(payload)
    normalized = funnel_testimonials._normalize_sales_pdp_carousel_plan(
        validated,
        shared_banner_copy={
            "ratingValueText": "4.9/5",
            "ratingDetailText": "Rated by 2,243 readers",
            "ctaText": "Get the handbook - $49",
        },
    )

    assert {slide["stripBgColor"] for slide in normalized} == {"#2d4a3e"}
    assert {slide["stripTextColor"] for slide in normalized} == {"#ffffff"}
    assert {slide["ratingValueText"] for slide in normalized} == {"4.9/5"}
    assert {slide["ratingDetailText"] for slide in normalized} == {"Rated by 2,243 readers"}
    assert {slide["ctaText"] for slide in normalized} == {"Get the handbook - $49"}


def test_should_use_on_dark_logo_for_sales_pdp_strip_prefers_dark_surfaces():
    assert funnel_testimonials._should_use_on_dark_logo_for_sales_pdp_strip("#0f3b2e") is True
    assert funnel_testimonials._should_use_on_dark_logo_for_sales_pdp_strip("#f7efe4") is False


def test_resolve_sales_pdp_design_system_logo_selection_uses_on_dark_variant():
    selection = funnel_testimonials._resolve_sales_pdp_design_system_logo_selection(
        tokens={
            "brand": {
                "logoAssetPublicId": "default-logo-public-id",
                "logoOnDarkAssetPublicId": "dark-logo-public-id",
            }
        },
        strip_bg_color="#0f3b2e",
    )

    assert selection is not None
    assert selection.asset_public_id == "dark-logo-public-id"
    assert selection.variant == "onDark"
    assert selection.source == "design_system"


def test_resolve_sales_pdp_design_system_logo_selection_raises_when_dark_logo_missing():
    with pytest.raises(
        funnel_testimonials.TestimonialGenerationError,
        match="logoOnDarkAssetPublicId is missing",
    ):
        funnel_testimonials._resolve_sales_pdp_design_system_logo_selection(
            tokens={"brand": {"logoAssetPublicId": "default-logo-public-id"}},
            strip_bg_color="#0f3b2e",
        )


def test_resolve_sales_pdp_design_system_logo_selection_uses_default_variant_on_light_surface():
    selection = funnel_testimonials._resolve_sales_pdp_design_system_logo_selection(
        tokens={
            "brand": {
                "logoAssetPublicId": "default-logo-public-id",
                "logoOnDarkAssetPublicId": "dark-logo-public-id",
            }
        },
        strip_bg_color="#f7efe4",
    )

    assert selection is not None
    assert selection.asset_public_id == "default-logo-public-id"
    assert selection.variant == "default"
    assert selection.source == "design_system"


def test_collect_sales_pdp_sample_guidance_reads_example_input():
    guidance = funnel_testimonials._collect_sales_pdp_sample_guidance(
        "testimonial-renderer/samples/inputs/pdp_example1_standard_ugc_nano.json"
    )

    assert guidance["brandNotes"] == "Everyday UGC with natural lighting and realistic skin detail."
    assert guidance["samplePromptFile"] == "testimonial-renderer/samples/prompts/pdp_example1_standard_ugc_nano.md"
    assert guidance["samplePrompt"].startswith("A casual, unposed smartphone photo")
    assert "source-brief subject" in guidance["samplePrompt"]
    assert "distorted hands" in guidance["backgroundAvoid"]


def test_compose_sales_pdp_background_prompt_uses_system_copy_and_v2_structure():
    prompt = funnel_testimonials._compose_sales_pdp_background_prompt(
        prompt_vars={
            "product": "a matte black supplement bottle with a green label",
            "subject": "a tired-looking dad in a gray hoodie",
            "scene": "messy kitchen at sunrise",
            "extra": "Hold the bottle near the lens with stable fingers and believable phone framing.",
            "avoid": ["stock-photo lighting", "watermarks"],
        },
        sample_prompt=(
            "A casual, unposed smartphone photo of a 55-65 year old woman holding a pink supplement bottle.\n"
            "Avoid: on-image captions; distorted hands."
        ),
    )

    assert prompt.startswith("Use SAMPLE STRUCTURE only for framing, style, realism, and negative-space guidance.")
    assert "REFERENCE IDENTITY LOCK" in prompt
    assert "Use the attached reference image(s) as the exact same product identity." in prompt
    assert "Do not invent interior pages" in prompt
    assert "Product: a matte black supplement bottle with a green label" in prompt
    assert "Subject: a tired-looking dad in a gray hoodie" in prompt
    assert "Scene: messy kitchen at sunrise" in prompt
    assert "Extra: Hold the bottle near the lens with stable fingers and believable phone framing." in prompt
    assert "Avoid: stock-photo lighting; watermarks" in prompt
    assert "A casual, unposed smartphone photo of a 55-65 year old woman holding a pink supplement bottle." in prompt


def test_resolve_sales_pdp_background_reference_assets_uses_original_source_first(db_session, seed_data):
    client = seed_data["client"]

    source_asset = Asset(
        org_id=client.org_id,
        client_id=client.id,
        source_type=AssetSourceEnum.upload,
        status=AssetStatusEnum.approved,
        public_id=uuid4(),
        asset_kind="image",
        channel_id="funnel",
        format="image",
        content={},
        file_source="upload",
        file_status="ready",
    )
    db_session.add(source_asset)
    db_session.commit()
    db_session.refresh(source_asset)

    rendered_asset = Asset(
        org_id=client.org_id,
        client_id=client.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.approved,
        public_id=uuid4(),
        asset_kind="image",
        channel_id="funnel",
        format="image",
        content={},
        file_source="ai",
        file_status="ready",
        ai_metadata={"referenceAssetPublicId": str(source_asset.public_id)},
    )
    db_session.add(rendered_asset)
    db_session.commit()
    db_session.refresh(rendered_asset)

    references = funnel_testimonials._resolve_sales_pdp_background_reference_assets(
        session=db_session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        core_product_asset=rendered_asset,
    )

    assert [str(asset.public_id) for asset in references] == [
        str(source_asset.public_id),
        str(rendered_asset.public_id),
    ]


def test_product_context_and_testimonial_primary_image_refresh_stale_product_state(db_session, seed_data):
    client = seed_data["client"]

    product = Product(
        org_id=client.org_id,
        client_id=client.id,
        title="Handbook",
        description="Printed handbook",
        product_type="book",
        primary_asset_id=None,
    )
    db_session.add(product)
    db_session.flush()

    funnel = Funnel(
        org_id=client.org_id,
        client_id=client.id,
        campaign_id=seed_data["campaign"].id,
        product_id=product.id,
        name="Launch",
        route_slug="launch",
        status=FunnelStatusEnum.draft,
    )
    db_session.add(funnel)
    db_session.flush()

    stale_product, _, _ = funnel_ai._load_product_context(
        session=db_session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        funnel=funnel,
    )
    assert stale_product is not None
    assert stale_product.primary_asset_id is None

    asset = Asset(
        org_id=client.org_id,
        client_id=client.id,
        source_type=AssetSourceEnum.upload,
        status=AssetStatusEnum.approved,
        public_id=uuid4(),
        asset_kind="image",
        channel_id="funnel",
        format="image",
        content={},
        file_source="upload",
        file_status="ready",
        product_id=product.id,
        storage_key="dev/orig/test-product-primary.png",
        content_type="image/png",
    )
    db_session.add(asset)
    db_session.flush()

    db_session.execute(
        sa.text("update products set primary_asset_id = :asset_id where id = :product_id"),
        {"asset_id": str(asset.id), "product_id": str(product.id)},
    )
    db_session.flush()

    refreshed_product, _, _ = funnel_ai._load_product_context(
        session=db_session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        funnel=funnel,
    )
    assert refreshed_product is not None
    assert str(refreshed_product.primary_asset_id) == str(asset.id)

    resolved_asset = funnel_testimonials._resolve_product_primary_image(
        session=db_session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        product=stale_product,
    )
    assert str(resolved_asset.id) == str(asset.id)


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

    assert len(selected) == 2
    assert selected[0]["name"] == "Slider Name"
    assert selected[0]["review"] == "Slider review"
    assert selected[0] is not testimonials[1]
    assert selected[1]["name"] == "Wall Reply"
    assert selected[1]["review"] == "Wall reply text"


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
        match="smaller than the image target count",
    ):
        funnel_testimonials._select_sales_pdp_reviews_payload_testimonials(
            groups=groups,
            validated_testimonials=testimonials,
        )


def test_sales_pdp_reviews_payload_appends_extra_reviews_beyond_image_targets():
    testimonials = [
        _sample_testimonial(
            name="Wall Name",
            review="Wall review",
            reply_name="Wall Reply",
            reply_persona="Wall persona",
            reply_text="Wall reply text",
        ),
        _sample_testimonial(
            name="Extra Name",
            review="Extra review",
            reply_name="Extra Reply",
            reply_persona="Extra persona",
            reply_text="Extra reply text",
        ),
    ]
    groups = [_group("sales_pdp.reviewWall.tiles[0].image")]

    selected = funnel_testimonials._select_sales_pdp_reviews_payload_testimonials(
        groups=groups,
        validated_testimonials=testimonials,
    )

    assert len(selected) == 2
    assert selected[0]["name"] == "Wall Reply"
    assert selected[0]["review"] == "Wall reply text"
    assert selected[1]["name"] == "Extra Name"
    assert selected[1]["review"] == "Extra review"


def test_build_strategy_v2_testimonial_grounding_includes_voc_and_guardrails():
    outputs = {
        "stage3": {
            "primary_segment": {
                "name": "Practical parents",
                "key_differentiator": "They want clear next steps without hype.",
            },
            "bottleneck": "Conflicting advice causes hesitation.",
            "core_promise": "Make safer home-remedy decisions faster.",
            "ums": "Medication-aware reference checks",
            "selected_angle": {
                "angle_name": "Safety-first clarity",
                "definition": {
                    "trigger": "Worried about interactions and misinformation.",
                    "mechanism_why": "Structured checks reduce second-guessing.",
                },
                "evidence": {
                    "top_quotes": [
                        {"quote": "I want one place to check this before I try anything."},
                        {"quote": "The mixed advice is what makes me freeze."},
                    ]
                },
            },
            "compliance_constraints": {"overall_risk": "YELLOW"},
        },
        "copy_context": {
            "brand_voice_markdown": "# Brand Voice\n\n- Calm and practical\n- Never dramatic",
            "compliance_markdown": "# Compliance\n\n- Avoid medical promises\n- Keep claims educational",
            "audience_product_markdown": "# Audience + Product\n\n### Curated VOC Quotes\n- \"Backup quote\"\n\n## Product",
        },
    }

    grounding = funnel_testimonials._build_strategy_v2_testimonial_grounding(outputs)

    assert "Strategy V2 grounding" in grounding
    assert "Primary segment: Practical parents" in grounding
    assert "VOC evidence quotes:" in grounding
    assert 'I want one place to check this before I try anything.' in grounding
    assert "Brand voice cues:" in grounding
    assert "Compliance cues:" in grounding


def test_testimonial_generation_count_enforces_sales_pdp_minimum():
    assert funnel_testimonials._testimonial_generation_count(template_kind="sales-pdp", image_target_count=12) == 75
    assert funnel_testimonials._testimonial_generation_count(template_kind="sales-pdp", image_target_count=90) == 90
    assert (
        funnel_testimonials._testimonial_generation_count(
            template_kind="pre-sales-listicle",
            image_target_count=12,
        )
        == 12
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


def test_sync_sales_pdp_guarantee_feed_images_noops_without_review_wall_images():
    puck_data = {
        "content": [
            {
                "type": "SalesPdpGuarantee",
                "props": {
                    "config": {"right": {"image": {"src": "/assets/old.webp", "alt": "Old"}}},
                    "feedImages": [{"src": "/assets/old-feed.webp", "alt": "Old feed"}],
                },
            }
        ],
        "zones": {},
    }
    original = json.loads(json.dumps(puck_data))

    funnel_testimonials._sync_sales_pdp_guarantee_feed_images(
        puck_data,
        review_wall_images=[],
    )

    assert puck_data == original
