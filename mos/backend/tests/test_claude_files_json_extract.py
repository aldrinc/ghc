import pytest

from app.services.claude_files import (
    _extract_first_json_object,
    _extract_puck_content_count,
    _structured_output_summary,
)


def test_extract_first_json_object_plain():
    assert _extract_first_json_object('{"a": 1}') == {"a": 1}


def test_extract_first_json_object_with_preamble_and_suffix():
    text = "Sure, here you go:\\n\\n{\"a\": 1, \"b\": {\"c\": 2}}\\n\\nThanks!"
    assert _extract_first_json_object(text) == {"a": 1, "b": {"c": 2}}


def test_extract_first_json_object_ignores_braces_in_strings():
    text = 'prefix {"a": "value with } brace", "b": {"c": "{nested} ok"}} suffix'
    assert _extract_first_json_object(text) == {"a": "value with } brace", "b": {"c": "{nested} ok"}}


def test_extract_first_json_object_raises_when_missing():
    with pytest.raises(ValueError):
        _extract_first_json_object("no json here")


def test_extract_puck_content_count_from_stringified_puck_data():
    parsed = {"assistantMessage": "ok", "puckData": '{"root":{"props":{}},"content":[{"type":"Text","props":{}}],"zones":{}}'}
    assert _extract_puck_content_count(parsed) == 1


def test_structured_output_summary_includes_puck_content_count_when_available():
    payload = {"stop_reason": "end_turn"}
    parsed = {"assistantMessage": "ok", "puckData": '{"root":{"props":{}},"content":[],"zones":{}}'}
    summary = _structured_output_summary(payload=payload, parsed=parsed, text_content='{"assistantMessage":"ok"}')
    assert summary["stopReason"] == "end_turn"
    assert summary["hasParsed"] is True
    assert summary["puckContentCount"] == 0
