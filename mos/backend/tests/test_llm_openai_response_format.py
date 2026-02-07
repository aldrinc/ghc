import pytest

from app.llm.client import LLMClient


def test_openai_text_format_lifts_chat_completions_json_schema() -> None:
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "PuckDraft", "strict": True, "schema": {"type": "object"}},
    }

    fmt = LLMClient._openai_text_format_from_response_format(response_format)

    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "PuckDraft"
    assert fmt["schema"] == {"type": "object"}
    assert "json_schema" not in fmt


def test_openai_text_format_passes_through_responses_shape() -> None:
    response_format = {"type": "json_schema", "name": "PuckDraft", "schema": {"type": "object"}, "strict": True}

    fmt = LLMClient._openai_text_format_from_response_format(response_format)

    assert fmt == response_format


def test_openai_text_format_errors_on_missing_name() -> None:
    response_format = {"type": "json_schema", "json_schema": {"strict": True, "schema": {"type": "object"}}}

    with pytest.raises(ValueError, match=r"text\.format\.name"):
        LLMClient._openai_text_format_from_response_format(response_format)


def test_openai_text_format_errors_on_missing_schema() -> None:
    response_format = {"type": "json_schema", "json_schema": {"name": "PuckDraft", "strict": True}}

    with pytest.raises(ValueError, match=r"text\.format\.schema"):
        LLMClient._openai_text_format_from_response_format(response_format)
