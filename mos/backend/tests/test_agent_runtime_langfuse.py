from app.agent.runtime import AgentRuntime


def test_parse_error_details_extracts_dict_suffix():
    message = (
        "AI generation produced an empty page (no content). "
        "details={'runId': 'r1', 'toolCallId': 't1', 'compiledPromptSha256': 'abc'}"
    )
    parsed = AgentRuntime._parse_error_details(message)
    assert parsed == {"runId": "r1", "toolCallId": "t1", "compiledPromptSha256": "abc"}


def test_parse_error_details_returns_none_without_marker():
    assert AgentRuntime._parse_error_details("Draft validation failed") is None


def test_tool_error_metadata_includes_structured_details_when_present():
    exc = RuntimeError(
        "Tool draft.generate_page failed: AI generation produced an empty page (no content). "
        "details={'model': 'claude-sonnet-4-5', 'templateKind': 'sales-pdp'}"
    )
    metadata = AgentRuntime._tool_error_metadata(exc)
    assert metadata["toolErrorType"] == "RuntimeError"
    assert metadata["toolErrorMessage"] == str(exc)
    assert metadata["toolErrorDetails"] == {"model": "claude-sonnet-4-5", "templateKind": "sales-pdp"}

