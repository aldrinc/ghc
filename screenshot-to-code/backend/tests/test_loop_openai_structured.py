from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from llm import Llm
from loop.contracts import RequirementsSpec
from loop.openai_structured import generate_structured_output_openai
from agent.providers.openai import _make_responses_schema_strict


class ExampleStructuredResponse(BaseModel):
    verdict: str


@pytest.mark.asyncio
async def test_generate_structured_output_openai_uses_gpt_5_4_schema_and_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text='{"verdict":"pass"}')

    class FakeClient:
        def __init__(self, api_key: str, base_url: str | None = None):
            self.api_key = api_key
            self.base_url = base_url
            self.responses = FakeResponses()

    monkeypatch.setattr("loop.openai_structured.AsyncOpenAI", FakeClient)

    result = await generate_structured_output_openai(
        api_key="key",
        model=Llm.GPT_5_4_2026_03_05_HIGH,
        system_instruction="Return JSON.",
        prompt_messages=[{"role": "user", "content": "Analyze this."}],
        response_schema=ExampleStructuredResponse,
    )

    assert result.verdict == "pass"
    assert calls[0]["model"] == "gpt-5.4-2026-03-05"
    assert calls[0]["reasoning"] == {"effort": "high", "summary": "auto"}
    text_format = calls[0]["text"]
    assert isinstance(text_format, dict)
    assert text_format["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_generate_structured_output_openai_raises_without_output_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponses:
        async def create(self, **kwargs):
            return SimpleNamespace(output_text=None)

    class FakeClient:
        def __init__(self, api_key: str, base_url: str | None = None):
            self.responses = FakeResponses()

    monkeypatch.setattr("loop.openai_structured.AsyncOpenAI", FakeClient)

    with pytest.raises(ValueError, match="OpenAI did not return parseable"):
        await generate_structured_output_openai(
            api_key="key",
            model=Llm.GPT_5_4_2026_03_05_HIGH,
            system_instruction="Return JSON.",
            prompt_messages=[{"role": "user", "content": "Analyze this."}],
            response_schema=ExampleStructuredResponse,
        )


def test_make_responses_schema_strict_adds_required_fields_to_nested_defs() -> None:
    strict_schema = _make_responses_schema_strict(RequirementsSpec.model_json_schema())

    design_tokens_schema = strict_schema["$defs"]["DesignTokenSet"]
    viewport_schema = strict_schema["$defs"]["ViewportSpec"]

    assert design_tokens_schema["required"] == [
        "colors",
        "typography",
        "spacing",
        "radii",
        "shadows",
        "motion",
    ]
    assert viewport_schema["required"] == ["width", "height", "device"]
