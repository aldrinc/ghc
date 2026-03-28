# pyright: reportUnknownVariableType=false
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from loop.gemini import (
    _coerce_repaired_structured_response_text,
    generate_structured_output,
)


class ExampleStructuredResponse(BaseModel):
    verdict: str


@pytest.mark.asyncio
async def test_generate_structured_output_repairs_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    responses = [
        SimpleNamespace(parsed=None, text='{"verdict":"revise'),
        SimpleNamespace(parsed=None, text='{"verdict":"pass"}'),
    ]

    class FakeModels:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr("loop.gemini.genai.Client", FakeClient)

    result = await generate_structured_output(
        api_key="key",
        model_name="gemini-3.1-pro-preview",
        thinking_level="high",
        system_instruction="Return JSON.",
        parts=[{"text": "Analyze this."}],
        response_schema=ExampleStructuredResponse,
    )

    assert result.verdict == "pass"
    assert len(calls) == 2


def test_coerce_repaired_structured_response_text_repairs_truncated_json() -> None:
    result = _coerce_repaired_structured_response_text(
        '{"verdict":"revise',
        ExampleStructuredResponse,
    )

    assert result.verdict == "revise"


@pytest.mark.asyncio
async def test_generate_structured_output_retries_from_scratch_when_repair_is_still_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    responses = [
        SimpleNamespace(parsed=None, text='{"verdict":"revise'),
        SimpleNamespace(parsed=None, text='{"verdict":"still broken'),
        SimpleNamespace(parsed=None, text='{"verdict":"pass"}'),
    ]

    class FakeModels:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr("loop.gemini.genai.Client", FakeClient)

    result = await generate_structured_output(
        api_key="key",
        model_name="gemini-3.1-pro-preview",
        thinking_level="high",
        system_instruction="Return JSON.",
        parts=[{"text": "Analyze this."}],
        response_schema=ExampleStructuredResponse,
    )

    assert result.verdict == "pass"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_generate_structured_output_falls_back_to_local_truncation_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    responses = [
        SimpleNamespace(parsed=None, text='{"verdict":"revise'),
        SimpleNamespace(parsed=None, text='{"verdict":"still broken'),
        SimpleNamespace(parsed=None, text='{"verdict":"pass'),
    ]

    class FakeModels:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr("loop.gemini.genai.Client", FakeClient)

    result = await generate_structured_output(
        api_key="key",
        model_name="gemini-3.1-pro-preview",
        thinking_level="high",
        system_instruction="Return JSON.",
        parts=[{"text": "Analyze this."}],
        response_schema=ExampleStructuredResponse,
    )

    assert result.verdict == "pass"
    assert len(calls) == 3
