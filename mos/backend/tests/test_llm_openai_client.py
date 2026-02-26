import pytest
from types import SimpleNamespace

from app.llm.client import LLMClient, LLMClientConfigError
from app.services.deep_research import extract_output_text


def test_openai_client_defaults_base_url_when_env_blank(monkeypatch) -> None:
    captured_kwargs: dict[str, object] = {}

    class _DummyOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured_kwargs.update(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setattr("app.llm.client.get_openai_client_class", lambda: _DummyOpenAI)

    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._ensure_openai_client()

    assert captured_kwargs["base_url"] == "https://api.openai.com/v1"


def test_openai_client_rejects_invalid_base_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "localhost:1234/v1")

    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    with pytest.raises(LLMClientConfigError, match=r"OPENAI_BASE_URL must be a fully qualified http\(s\) URL"):
        llm._ensure_openai_client()


def test_extract_response_text_supports_dict_output_shape() -> None:
    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    response = {
        "output_text": "",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "hello "},
                    {"type": "output_text", "text": "world"},
                ],
            }
        ],
    }
    assert llm._extract_response_text(response) == "hello world"


def test_extract_response_text_supports_mixed_object_dict_shape() -> None:
    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                content=[
                    {"type": "output_text", "text": "from dict"},
                    SimpleNamespace(text=" and object"),
                ]
            )
        ],
    )
    assert llm._extract_response_text(response) == "from dict and object"


def test_deep_research_extract_output_text_supports_dict_output_shape() -> None:
    response = {
        "output_text": "",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "alpha"},
                    {"type": "output_text", "text": " beta"},
                ],
            }
        ],
    }
    assert extract_output_text(response) == "alpha beta"


def test_poll_openai_response_returns_completed_text() -> None:
    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    response = SimpleNamespace(status="completed", output_text='{"ok": true}')

    assert llm._poll_openai_response(
        "resp_completed",
        initial_response=response,
        poll_timeout_seconds=1,
    ) == '{"ok": true}'


def test_poll_openai_response_rejects_incomplete_output() -> None:
    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    response = SimpleNamespace(
        status="incomplete",
        output_text='{"angle_candidates": [',
        error=None,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )

    with pytest.raises(RuntimeError, match=r"incomplete output.*max_output_tokens"):
        llm._poll_openai_response(
            "resp_incomplete",
            initial_response=response,
            poll_timeout_seconds=1,
        )
