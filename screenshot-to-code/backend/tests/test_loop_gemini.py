# pyright: reportUnknownVariableType=false
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from loop.gemini import generate_structured_output


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
