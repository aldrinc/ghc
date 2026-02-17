from app.llm.client import LLMClient, LLMGenerationParams


class _DummyResponsesStream:
    def __init__(self) -> None:
        self._events: list[object] = []

    def __enter__(self):  # noqa: ANN001
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    def __iter__(self):
        return iter(self._events)


class _DummyResponses:
    def __init__(self) -> None:
        self.last_stream_kwargs: dict[str, object] | None = None

    def stream(self, **kwargs):  # noqa: ANN003
        self.last_stream_kwargs = kwargs
        return _DummyResponsesStream()


class _DummyOpenAIClient:
    def __init__(self) -> None:
        self.responses = _DummyResponses()


def test_stream_text_responses_omits_temperature(monkeypatch) -> None:
    # LLMClient requires OPENAI_API_KEY to be set even when we stub the client.
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._openai_client = _DummyOpenAIClient()  # type: ignore[assignment]

    params = LLMGenerationParams(
        model="gpt-5.2-2025-12-11",
        temperature=0.2,
        use_reasoning=True,
        use_web_search=False,
    )

    # Exhaust the generator to force the OpenAI request to be built.
    _ = "".join(llm.stream_text("hi", params=params))

    assert llm._openai_client.responses.last_stream_kwargs is not None  # type: ignore[union-attr]
    assert "temperature" not in llm._openai_client.responses.last_stream_kwargs  # type: ignore[union-attr]
