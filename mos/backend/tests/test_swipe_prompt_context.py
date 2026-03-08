import pytest

from app.services.swipe_prompt import (
    SwipePromptParseError,
    build_swipe_context_block,
    extract_new_image_prompt_from_markdown,
    inline_swipe_render_placeholders,
)


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


def test_extract_new_image_prompt_allows_placeholder_tokens_prior_to_inline() -> None:
    markdown = """
```text
A clean ad concept with [BRAND_LOGO] in the corner.
```
"""
    extracted = extract_new_image_prompt_from_markdown(markdown)
    assert "[BRAND_LOGO]" in extracted


def test_extract_new_image_prompt_allows_non_placeholder_brackets() -> None:
    markdown = """
```text
[A split-screen ad composition in 1:1] with concrete copy and no unresolved tokens.
```
"""
    extracted = extract_new_image_prompt_from_markdown(markdown)
    assert "split-screen ad composition" in extracted


def test_extract_new_image_prompt_accepts_markdown_fence_language() -> None:
    markdown = """
```markdown
A realistic 1:1 static ad composition with exact copy and clear CTA text.
```
"""
    extracted = extract_new_image_prompt_from_markdown(markdown)
    assert "realistic 1:1 static ad composition" in extracted


def test_extract_new_image_prompt_accepts_empty_fence_language() -> None:
    markdown = """
```
A concrete ad prompt with no unresolved placeholders and no language label.
```
"""
    extracted = extract_new_image_prompt_from_markdown(markdown)
    assert "no language label" in extracted


def test_extract_new_image_prompt_rejects_multiple_valid_fences() -> None:
    markdown = """
```text
Prompt block one.
```

```markdown
Prompt block two.
```
"""
    with pytest.raises(SwipePromptParseError, match="Ambiguous prompt output"):
        extract_new_image_prompt_from_markdown(markdown)


def test_extract_new_image_prompt_rejects_no_valid_fence_language() -> None:
    markdown = """
```python
print("not a render prompt")
```
"""
    with pytest.raises(SwipePromptParseError, match="No valid prompt code fence found"):
        extract_new_image_prompt_from_markdown(markdown)


def test_inline_swipe_render_placeholders_replaces_tokens_and_removes_placeholder_section() -> None:
    prompt = """
Typography Zones:
- [HEADLINE] is large and bold.
- [CTA] is a bright blue rounded button.

Placeholders:
[HEADLINE] = What I Discovered at 55 Finally Stopped The Panic.
[CTA] = Learn More
""".strip()

    inlined, mapping = inline_swipe_render_placeholders(prompt)
    assert "[HEADLINE]" not in inlined
    assert "[CTA]" not in inlined
    assert "What I Discovered at 55 Finally Stopped The Panic." in inlined
    assert "Learn More is a bright blue rounded button." in inlined
    assert "Placeholders:" not in inlined
    assert mapping == {
        "HEADLINE": "What I Discovered at 55 Finally Stopped The Panic.",
        "CTA": "Learn More",
    }


def test_inline_swipe_render_placeholders_errors_when_tokens_remain_unresolved() -> None:
    prompt = """
Typography Zones:
- [HEADLINE] is large and bold.
""".strip()

    with pytest.raises(SwipePromptParseError, match="unresolved bracket placeholders"):
        inline_swipe_render_placeholders(prompt)
