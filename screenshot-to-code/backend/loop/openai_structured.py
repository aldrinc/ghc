from typing import Any, Sequence, TypeVar, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from agent.providers.openai import (
    _convert_message_to_responses_input,
    _make_responses_schema_strict,
)
from llm import Llm, get_openai_api_name, get_openai_reasoning_effort


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


async def generate_structured_output_openai(
    *,
    api_key: str,
    model: Llm,
    system_instruction: str,
    prompt_messages: Sequence[ChatCompletionMessageParam],
    response_schema: type[StructuredModel],
    openai_base_url: str | None = None,
    max_output_tokens: int = 50_000,
) -> StructuredModel:
    client = AsyncOpenAI(api_key=api_key, base_url=openai_base_url)
    input_items = [
        _convert_message_to_responses_input(message) for message in prompt_messages
    ]

    params: dict[str, Any] = {
        "model": get_openai_api_name(model),
        "instructions": system_instruction,
        "input": input_items,
        "max_output_tokens": max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "structured_response",
                "schema": _make_responses_schema_strict(
                    response_schema.model_json_schema()
                ),
                "strict": True,
            }
        },
    }
    reasoning_effort = get_openai_reasoning_effort(model)
    if reasoning_effort:
        params["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}

    response = cast(Any, await client.responses.create(**params))
    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise ValueError("OpenAI did not return parseable structured output")

    return response_schema.model_validate_json(output_text)
