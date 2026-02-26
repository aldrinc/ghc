import pytest

from app.llm.client import LLMClient, LLMGenerationParams


def test_anthropic_client_defaults_base_url_when_env_blank(monkeypatch) -> None:
    captured_kwargs: dict[str, object] = {}

    class _DummyResponse:
        def __init__(self) -> None:
            self.content = [type("TextBlock", (), {"text": "OK", "type": "text"})()]
            self.usage = None

    class _DummyAnthropic:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured_kwargs.update(kwargs)
            self.messages = self

        def create(self, **_kwargs):  # noqa: ANN003
            return _DummyResponse()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_BASE_URL", "")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "")
    monkeypatch.setattr("app.llm.client.Anthropic", _DummyAnthropic)

    llm = LLMClient(default_model="claude-sonnet-4-5")
    text = llm.generate_text(
        "Respond with OK",
        params=LLMGenerationParams(model="claude-sonnet-4-5", temperature=0, max_tokens=32),
    )

    assert text == "OK"
    assert captured_kwargs["base_url"] == "https://api.anthropic.com"


def test_anthropic_generation_surfaces_underlying_exception(monkeypatch) -> None:
    class _DummyAnthropic:
        def __init__(self, **_kwargs):  # noqa: ANN003
            self.messages = self

        def create(self, **_kwargs):  # noqa: ANN003
            raise RuntimeError("connection boom")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("app.llm.client.Anthropic", _DummyAnthropic)

    llm = LLMClient(default_model="claude-sonnet-4-5")
    with pytest.raises(RuntimeError, match=r"Anthropic generation failed for model claude-sonnet-4-5: connection boom"):
        llm.generate_text(
            "Ping",
            params=LLMGenerationParams(model="claude-sonnet-4-5", temperature=0, max_tokens=16),
        )
