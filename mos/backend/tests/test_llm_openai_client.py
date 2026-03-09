from types import SimpleNamespace
import app.llm.client as llm_client_module
import pytest

from app.llm.client import LLMClient, LLMGenerationParams
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
    with pytest.raises(
        llm_client_module.LLMClientConfigError,
        match=r"OPENAI_BASE_URL must be a fully qualified http\(s\) URL",
    ):
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


def test_generate_with_openai_passes_configured_tools(monkeypatch) -> None:
    class _DummyResponses:
        def __init__(self) -> None:
            self.last_create_kwargs: dict[str, object] | None = None

        def create(self, **kwargs):  # noqa: ANN003
            self.last_create_kwargs = kwargs
            return SimpleNamespace(id="resp_test", status="completed", output_text='{"ok": true}')

    class _DummyOpenAIClient:
        def __init__(self) -> None:
            self.responses = _DummyResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test")

    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._openai_client = _DummyOpenAIClient()  # type: ignore[assignment]

    params = LLMGenerationParams(
        model="gpt-5.2-2025-12-11",
        use_reasoning=True,
        reasoning_effort="xhigh",
        openai_tools=[{"type": "code_interpreter", "container": {"type": "auto"}}],
        openai_tool_choice="auto",
        openai_context_management=[{"type": "compaction", "compact_threshold": 200000}],
    )
    output = llm.generate_text("Return JSON", params=params)

    assert output == '{"ok": true}'
    assert llm._openai_client.responses.last_create_kwargs is not None  # type: ignore[union-attr]
    tools = llm._openai_client.responses.last_create_kwargs.get("tools")  # type: ignore[union-attr]
    assert isinstance(tools, list)
    assert {"type": "code_interpreter", "container": {"type": "auto"}} in tools
    assert llm._openai_client.responses.last_create_kwargs.get("tool_choice") == "auto"  # type: ignore[union-attr]
    assert llm._openai_client.responses.last_create_kwargs.get("reasoning") == {"effort": "xhigh"}  # type: ignore[union-attr]
    assert llm._openai_client.responses.last_create_kwargs.get("extra_body") == {  # type: ignore[union-attr]
        "context_management": [{"type": "compaction", "compact_threshold": 200000}]
    }


def test_generate_with_openai_retries_transient_response_server_error(monkeypatch) -> None:
    class _DummyResponses:
        def __init__(self) -> None:
            self.create_calls = 0

        def create(self, **kwargs):  # noqa: ANN003
            self.create_calls += 1
            if self.create_calls == 1:
                return SimpleNamespace(
                    id="resp_fail_once",
                    status="failed",
                    output_text=None,
                    error=SimpleNamespace(code="server_error", message="temporary"),
                    incomplete_details=None,
                )
            return SimpleNamespace(
                id="resp_success",
                status="completed",
                output_text='{"ok": true}',
                error=None,
                incomplete_details=None,
            )

    class _DummyOpenAIClient:
        def __init__(self) -> None:
            self.responses = _DummyResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr("app.llm.client._MAX_RETRIES", 2)
    monkeypatch.setattr("app.llm.client.time.sleep", lambda *_args, **_kwargs: None)

    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._openai_client = _DummyOpenAIClient()  # type: ignore[assignment]

    params = LLMGenerationParams(
        model="gpt-5.2-2025-12-11",
        use_reasoning=True,
    )
    output = llm.generate_text("Return JSON", params=params)

    assert output == '{"ok": true}'
    assert llm._openai_client.responses.create_calls == 2  # type: ignore[union-attr]


def test_generate_with_openai_resumes_existing_response_id(monkeypatch) -> None:
    class _DummyResponses:
        def __init__(self) -> None:
            self.create_calls = 0
            self.retrieve_calls: list[tuple[str, object | None]] = []

        def create(self, **kwargs):  # noqa: ANN003
            self.create_calls += 1
            raise AssertionError("responses.create should not be called when resuming an existing response")

        def retrieve(self, response_id: str, include=None):  # noqa: ANN001
            self.retrieve_calls.append((response_id, include))
            return SimpleNamespace(status="completed", output_text='{"ok": true}')

    class _DummyOpenAIClient:
        def __init__(self) -> None:
            self.responses = _DummyResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test")

    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._openai_client = _DummyOpenAIClient()  # type: ignore[assignment]

    params = LLMGenerationParams(
        model="gpt-5.2-2025-12-11",
        use_reasoning=True,
        existing_openai_response_id="resp_resume_123",
    )
    output = llm.generate_text("Return JSON", params=params)

    assert output == '{"ok": true}'
    assert llm._openai_client.responses.create_calls == 0  # type: ignore[union-attr]
    assert llm._openai_client.responses.retrieve_calls == [("resp_resume_123", None)]  # type: ignore[union-attr]


def test_generate_with_openai_does_not_retry_non_transient_response_failure(monkeypatch) -> None:
    class _DummyResponses:
        def __init__(self) -> None:
            self.create_calls = 0

        def create(self, **kwargs):  # noqa: ANN003
            self.create_calls += 1
            return SimpleNamespace(
                id="resp_invalid",
                status="failed",
                output_text=None,
                error=SimpleNamespace(code="invalid_request_error", message="bad input"),
                incomplete_details=None,
            )

    class _DummyOpenAIClient:
        def __init__(self) -> None:
            self.responses = _DummyResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr("app.llm.client._MAX_RETRIES", 3)
    monkeypatch.setattr("app.llm.client.time.sleep", lambda *_args, **_kwargs: None)

    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._openai_client = _DummyOpenAIClient()  # type: ignore[assignment]

    params = LLMGenerationParams(
        model="gpt-5.2-2025-12-11",
        use_reasoning=True,
    )
    with pytest.raises(RuntimeError, match=r"error_code=invalid_request_error"):
        llm.generate_text("Return JSON", params=params)

    assert llm._openai_client.responses.create_calls == 1  # type: ignore[union-attr]


def test_upload_openai_file_bytes_returns_uploaded_file_id(monkeypatch) -> None:
    class _DummyFiles:
        def __init__(self) -> None:
            self.last_filename: str | None = None
            self.last_content: bytes | None = None
            self.last_purpose: str | None = None

        def create(self, *, file, purpose):  # noqa: ANN001
            self.last_filename = str(getattr(file, "name", "") or "")
            self.last_content = file.read()
            self.last_purpose = purpose
            return SimpleNamespace(id="file_abc123")

    class _DummyOpenAIClient:
        def __init__(self) -> None:
            self.files = _DummyFiles()

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._openai_client = _DummyOpenAIClient()  # type: ignore[assignment]

    file_id = llm.upload_openai_file_bytes(
        filename="strategy-v2-test.json",
        content_bytes=b'{"hello":"world"}',
        purpose="assistants",
    )

    assert file_id == "file_abc123"
    assert llm._openai_client.files.last_filename == "strategy-v2-test.json"  # type: ignore[union-attr]
    assert llm._openai_client.files.last_content == b'{"hello":"world"}'  # type: ignore[union-attr]
    assert llm._openai_client.files.last_purpose == "assistants"  # type: ignore[union-attr]


def test_explicit_baseten_provider_stream_collects_chat_completions_and_default_base_url(monkeypatch) -> None:
    captured_client_kwargs: dict[str, object] = {}
    created_clients: list[object] = []
    progress_events: list[dict[str, object]] = []

    class _DummyChatCompletionStream:
        def __iter__(self):
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="baseten "))],
                usage=None,
                _request_id="req_baseten_123",
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5, total_tokens=17),
                _request_id="req_baseten_123",
            )

    class _DummyChatCompletions:
        def __init__(self) -> None:
            self.last_create_kwargs: dict[str, object] | None = None

        def create(self, **kwargs):  # noqa: ANN003
            self.last_create_kwargs = kwargs
            return _DummyChatCompletionStream()

    class _DummyChat:
        def __init__(self) -> None:
            self.completions = _DummyChatCompletions()

    class _DummyOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured_client_kwargs.update(kwargs)
            self.chat = _DummyChat()
            created_clients.append(self)

    monkeypatch.setenv("BASETEN_API_KEY", "test-baseten-key")
    monkeypatch.setenv("BASETEN_BASE_URL", "")
    monkeypatch.setattr("app.llm.client.get_openai_client_class", lambda: _DummyOpenAI)

    llm = LLMClient(default_model="baseten:moonshotai/Kimi-K2.5")
    output = llm.generate_text(
        "Return a headline",
        params=LLMGenerationParams(
            model="baseten:moonshotai/Kimi-K2.5",
            use_reasoning=True,
            progress_callback=progress_events.append,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "headline_result",
                    "schema": {
                        "type": "object",
                        "properties": {"headline": {"type": "string"}},
                        "required": ["headline"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
        ),
    )

    assert output == "baseten hello"
    assert captured_client_kwargs["base_url"] == "https://inference.baseten.co/v1"
    assert created_clients
    request_kwargs = created_clients[0].chat.completions.last_create_kwargs  # type: ignore[attr-defined]
    assert request_kwargs is not None
    assert request_kwargs["model"] == "moonshotai/Kimi-K2.5"
    assert request_kwargs["stream"] is True
    assert request_kwargs["stream_options"] == {
        "include_usage": True,
        "continuous_usage_stats": True,
    }
    assert request_kwargs["extra_body"] == {"chat_template_args": {"enable_thinking": True}}
    assert request_kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "headline_result",
            "schema": {
                "type": "object",
                "properties": {"headline": {"type": "string"}},
                "required": ["headline"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
    assert progress_events == [
        {
            "status": "completed",
            "request_id": "req_baseten_123",
            "input_tokens": 12,
            "output_tokens": 5,
            "total_tokens": 17,
        }
    ]


def test_delete_openai_file_invokes_openai_delete(monkeypatch) -> None:
    class _DummyFiles:
        def __init__(self) -> None:
            self.deleted_file_id: str | None = None

        def delete(self, file_id: str):  # noqa: ANN001
            self.deleted_file_id = file_id
            return SimpleNamespace(id=file_id, deleted=True)

    class _DummyOpenAIClient:
        def __init__(self) -> None:
            self.files = _DummyFiles()

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    llm = LLMClient(default_model="gpt-5.2-2025-12-11")
    llm._openai_client = _DummyOpenAIClient()  # type: ignore[assignment]

    llm.delete_openai_file(file_id="file_xyz789")

    assert llm._openai_client.files.deleted_file_id == "file_xyz789"  # type: ignore[union-attr]
