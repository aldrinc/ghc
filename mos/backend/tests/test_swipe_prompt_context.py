from app.services.swipe_prompt import build_swipe_context_block


def test_swipe_context_block_includes_creative_brief_context() -> None:
    block = build_swipe_context_block(
        brand_name="Brand A",
        product_name="Product A",
        audience="Adults 35+",
        brand_colors_fonts="Brand color: #061a70",
        must_avoid_claims=["No medical claims"],
        assets={"PRODUCT_PACKSHOT_1": "https://example.com/packshot.png"},
        creative_concept="Eye comfort drives consistency for LED mask usage.",
        channel="facebook",
        angle="Consistency through comfort",
        hook="The reason LED masks end up in drawers: they ignore your eyes",
        constraints=["Needs confirmation: eye safety testing or certifications"],
        tone_guidelines=["Problem-aware and empathetic"],
        visual_guidelines=["Split visual: uncomfortable vs comfortable eye experience"],
    )

    assert "## CREATIVE BRIEF CONTEXT" in block
    assert "Creative concept: Eye comfort drives consistency for LED mask usage." in block
    assert "Channel: facebook" in block
    assert "Format: image." in block
    assert "Angle: Consistency through comfort" in block
    assert "Hook: The reason LED masks end up in drawers: they ignore your eyes" in block
    assert "Constraints:" in block
    assert "- Needs confirmation: eye safety testing or certifications" in block
    assert "Tone guidelines:" in block
    assert "- Problem-aware and empathetic" in block
    assert "Visual guidelines:" in block
    assert "- Split visual: uncomfortable vs comfortable eye experience" in block


def test_swipe_context_block_marks_missing_brief_values_as_unknown() -> None:
    block = build_swipe_context_block(
        brand_name="Brand A",
        product_name="Product A",
        creative_concept=None,
        channel=None,
        angle=None,
        hook=None,
        constraints=None,
        tone_guidelines=None,
        visual_guidelines=None,
    )

    assert "Creative concept: [UNKNOWN]" in block
    assert "Channel: [UNKNOWN]" in block
    assert "Angle: [UNKNOWN]" in block
    assert "Hook: [UNKNOWN]" in block
    assert "Constraints:\n- [UNKNOWN]" in block
    assert "Tone guidelines:\n- [UNKNOWN]" in block
    assert "Visual guidelines:\n- [UNKNOWN]" in block
