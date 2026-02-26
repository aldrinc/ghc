from app.strategy_v2 import StrategyV2MissingContextError
from app.temporal.activities.strategy_v2_activities import _build_avatar_brief_runtime_payload


def test_avatar_brief_parser_extracts_demographics_with_markdown_bullets() -> None:
    step6_content = """
    Segment profile:
    - Age range: HYPOTHESIS 25-40
    - Gender distribution: HYPOTHESIS majority women
    - Platform habits: TikTok, Instagram, YouTube
    - Content patterns: short-form videos, checklists
    """
    payload = _build_avatar_brief_runtime_payload(
        step6_content=step6_content,
        step6_summary="Safety-focused caregivers.",
    )

    assert payload["demographics"]["age_range"].startswith("HYPOTHESIS 25-40")
    assert "majority women" in payload["demographics"]["gender_skew"].lower()
    assert payload["platform_habits"]
    assert payload["content_consumption_patterns"]


def test_avatar_brief_parser_handles_unicode_bullets_and_emphasis() -> None:
    step6_content = """
    B) Demographics
    — **Age range**: 30-55 (inferred)
    — **Gender skew**: Mostly women
    • Platforms: Reddit | YouTube
    • Content patterns: long-form explainers; Q&A threads
    """
    payload = _build_avatar_brief_runtime_payload(
        step6_content=step6_content,
        step6_summary="Chronic-condition managers.",
    )

    assert payload["demographics"]["age_range"].startswith("30-55")
    assert "mostly women" in payload["demographics"]["gender_skew"].lower()
    assert any("reddit" in item.lower() for item in payload["platform_habits"])
    assert any("q&a" in item.lower() or "long-form" in item.lower() for item in payload["content_consumption_patterns"])


def test_avatar_brief_parser_raises_when_required_fields_are_missing() -> None:
    step6_content = """
    Segment overview only.
    Platforms: YouTube
    Content patterns: short-form
    """
    try:
        _build_avatar_brief_runtime_payload(
            step6_content=step6_content,
            step6_summary="Too thin.",
        )
    except StrategyV2MissingContextError as exc:
        assert "age_range" in str(exc)
        assert "gender_skew" in str(exc)
    else:
        raise AssertionError("Expected StrategyV2MissingContextError for missing demographics")
