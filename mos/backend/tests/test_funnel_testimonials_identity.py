import pytest
from app.services import funnel_testimonials


def _testimonial(
    *,
    name: str,
    persona: str,
    reply_name: str,
    reply_persona: str,
) -> dict[str, object]:
    return {
        "name": name,
        "verified": True,
        "rating": 5,
        "review": "Useful product and great experience.",
        "persona": persona,
        "avatarPrompt": "Natural portrait in daylight.",
        "heroImagePrompt": "Holding the product in a home setting.",
        "mediaPrompts": [
            "Using the product in a bedroom.",
            "Product by a mirror with natural light.",
            "Close-up of product in hand.",
        ],
        "reply": {
            "name": reply_name,
            "persona": reply_persona,
            "text": "I had a similar experience.",
            "avatarPrompt": "Casual portrait in kitchen.",
            "time": "2d",
            "reactionCount": 3,
        },
        "meta": {"location": "Austin, TX", "date": "2026-02-11"},
    }


def test_assert_distinct_testimonial_identities_rejects_duplicates():
    testimonials = [
        _testimonial(
            name="Marcus Chen",
            persona="Busy parent seeking easier routines.",
            reply_name="Dana Flores",
            reply_persona="Friend comparing evening routines.",
        ),
        _testimonial(
            name="Marcus Chen",
            persona="Busy parent seeking easier routines.",
            reply_name="Dana Flores",
            reply_persona="Friend comparing evening routines.",
        ),
    ]

    with pytest.raises(funnel_testimonials.TestimonialGenerationError, match="Duplicate testimonial name"):
        funnel_testimonials._assert_distinct_testimonial_identities(testimonials)


def test_assert_distinct_testimonial_identities_accepts_unique_values():
    testimonials = [
        _testimonial(
            name="Marcus Chen",
            persona="Busy parent seeking easier routines.",
            reply_name="Dana Flores",
            reply_persona="Friend comparing evening routines.",
        ),
        _testimonial(
            name="Avery Patel",
            persona="Night-shift nurse balancing skin care.",
            reply_name="Nina Brooks",
            reply_persona="Coworker comparing before-bed habits.",
        ),
    ]

    funnel_testimonials._assert_distinct_testimonial_identities(testimonials)
    assert testimonials[0]["name"] == "Marcus Chen"
    assert testimonials[1]["name"] == "Avery Patel"


def test_validate_testimonial_payload_rejects_numeric_suffix_in_name():
    payload = _testimonial(
        name="Marcus Chen (2)",
        persona="Busy parent seeking easier routines.",
        reply_name="Dana Flores",
        reply_persona="Friend comparing evening routines.",
    )

    with pytest.raises(
        funnel_testimonials.TestimonialGenerationError,
        match=r"Testimonial name cannot use numeric disambiguation suffixes",
    ):
        funnel_testimonials._validate_testimonial_payload(payload)


def test_validate_testimonial_payload_rejects_numeric_suffix_in_reply_name():
    payload = _testimonial(
        name="Marcus Chen",
        persona="Busy parent seeking easier routines.",
        reply_name="Dana Flores (2)",
        reply_persona="Friend comparing evening routines.",
    )

    with pytest.raises(
        funnel_testimonials.TestimonialGenerationError,
        match=r"Testimonial reply\.name cannot use numeric disambiguation suffixes",
    ):
        funnel_testimonials._validate_testimonial_payload(payload)


def test_scene_mode_cycles_for_single_and_media_slots():
    assert funnel_testimonials._select_single_scene_mode(0) == "with_people"
    assert funnel_testimonials._select_single_scene_mode(1) == "no_people"
    assert funnel_testimonials._select_single_scene_mode(2) == "with_people"

    assert funnel_testimonials._select_media_scene_mode(0) == "with_people"
    assert funnel_testimonials._select_media_scene_mode(1) == "no_people"
    assert funnel_testimonials._select_media_scene_mode(2) == "no_people"
    assert funnel_testimonials._select_media_scene_mode(3) == "with_people"


def test_scene_mode_rejects_negative_indexes():
    with pytest.raises(funnel_testimonials.TestimonialGenerationError):
        funnel_testimonials._select_single_scene_mode(-1)

    with pytest.raises(funnel_testimonials.TestimonialGenerationError):
        funnel_testimonials._select_media_scene_mode(-1)


def test_non_user_prompt_requires_no_people():
    prompt = funnel_testimonials._build_non_user_ugc_prompt(
        render_label="sales_pdp.reviewWall.tiles[0]",
        persona="Early-30s parent balancing work and bedtime routines.",
        setting="Apartment kitchen counter with normal clutter",
        action="Product resting beside a half-filled glass of water",
        direction="Close framing on the product with natural morning light",
        include_text_screen_line=False,
        prohibit_visible_text=True,
    )

    assert "NO PEOPLE POLICY" in prompt
    assert "absolutely no humans" in prompt
    assert "TEXT POLICY: absolutely no visible text in the image." in prompt
