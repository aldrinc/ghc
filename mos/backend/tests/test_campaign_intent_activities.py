import pytest

from app.temporal.activities.campaign_intent_activities import (
    _collect_image_generation_errors,
    _is_empty_page_generation_error,
    _run_generate_page_draft_with_retries,
)


def test_is_empty_page_generation_error_matches_wrapped_tool_error():
    exc = RuntimeError(
        "Tool draft.generate_page failed: AI generation produced an empty page (no content). details={...}"
    )
    assert _is_empty_page_generation_error(exc) is True


def test_run_generate_page_draft_with_retries_retries_empty_page_then_succeeds():
    attempts = {"count": 0}
    retry_attempts: list[int] = []

    def _generate():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("AI generation produced an empty page (no content).")
        return {"draftVersionId": "draft-123"}

    result = _run_generate_page_draft_with_retries(
        run_generation=_generate,
        max_attempts=3,
        on_retry=lambda attempt, _exc: retry_attempts.append(attempt),
    )

    assert result["draftVersionId"] == "draft-123"
    assert attempts["count"] == 3
    assert retry_attempts == [1, 2]


def test_run_generate_page_draft_with_retries_does_not_retry_non_empty_error():
    attempts = {"count": 0}

    def _generate():
        attempts["count"] += 1
        raise RuntimeError("Draft validation failed: missing component")

    with pytest.raises(RuntimeError, match="Draft validation failed"):
        _run_generate_page_draft_with_retries(run_generation=_generate, max_attempts=3)

    assert attempts["count"] == 1


def test_run_generate_page_draft_with_retries_raises_after_max_empty_page_attempts():
    attempts = {"count": 0}
    retry_attempts: list[int] = []

    def _generate():
        attempts["count"] += 1
        raise RuntimeError("AI generation produced an empty page (no content).")

    with pytest.raises(RuntimeError, match="empty page"):
        _run_generate_page_draft_with_retries(
            run_generation=_generate,
            max_attempts=3,
            on_retry=lambda attempt, _exc: retry_attempts.append(attempt),
        )

    assert attempts["count"] == 3
    assert retry_attempts == [1, 2]


def test_collect_image_generation_errors_returns_structured_entries():
    generated_images = [
        {"assetPublicId": "abc"},
        {"error": "Unsplash search returned 0 results"},
        {"error": "  CDN timeout  "},
        "not-an-object",
        {"error": ""},
    ]

    errors = _collect_image_generation_errors(
        generated_images=generated_images,
        funnel_id="funnel-1",
        page_id="page-1",
        page_name="Sales",
        template_id="sales-pdp",
    )

    assert errors == [
        {
            "type": "image_generation",
            "severity": "warning",
            "funnel_id": "funnel-1",
            "page_id": "page-1",
            "page_name": "Sales",
            "template_id": "sales-pdp",
            "message": "Unsplash search returned 0 results",
        },
        {
            "type": "image_generation",
            "severity": "warning",
            "funnel_id": "funnel-1",
            "page_id": "page-1",
            "page_name": "Sales",
            "template_id": "sales-pdp",
            "message": "CDN timeout",
        },
    ]


def test_collect_image_generation_errors_ignores_non_list_inputs():
    errors = _collect_image_generation_errors(
        generated_images={"error": "boom"},
        funnel_id="funnel-1",
        page_id="page-1",
        page_name="Sales",
        template_id=None,
    )
    assert errors == []
