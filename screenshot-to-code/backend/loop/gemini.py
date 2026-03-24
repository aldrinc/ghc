import base64
import json
from typing import Any, Sequence, TypeVar, cast

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError


DEFAULT_VIDEO_FPS = 10

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
GeminiPart = types.Part | dict[str, str]


def text_part(text: str) -> dict[str, str]:
    return {"text": text}


def data_url_to_part(data_url: str) -> types.Part:
    if not data_url.startswith("data:"):
        raise ValueError("Expected an inline data URL")

    header, encoded = data_url.split(",", 1)
    mime_type = header.split(";")[0].split(":")[1]
    media_bytes = base64.b64decode(encoded)

    if mime_type.startswith("video/"):
        return types.Part(
            inline_data=types.Blob(data=media_bytes, mime_type=mime_type),
            video_metadata=types.VideoMetadata(fps=DEFAULT_VIDEO_FPS),
            media_resolution=types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        )

    return types.Part.from_bytes(
        data=media_bytes,
        mime_type=mime_type,
        media_resolution=types.PartMediaResolutionLevel.MEDIA_RESOLUTION_ULTRA_HIGH,
    )


def _coerce_structured_response(
    response: Any,
    response_schema: type[StructuredModel],
) -> StructuredModel:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, response_schema):
        return parsed
    if isinstance(parsed, dict):
        return response_schema.model_validate(parsed)

    response_text = getattr(response, "text", None)
    if isinstance(response_text, str) and response_text.strip():
        return response_schema.model_validate_json(response_text)

    raise ValueError("Gemini did not return parseable structured output")


def _schema_instruction(response_schema: type[StructuredModel]) -> dict[str, str]:
    return text_part(
        "Return only valid JSON matching this schema:\n"
        + json.dumps(response_schema.model_json_schema(), indent=2)
    )


def _repair_instruction(
    response_schema: type[StructuredModel], invalid_response_text: str
) -> dict[str, str]:
    return text_part(
        "The previous response was not valid JSON matching the schema. "
        "Rewrite it as compact valid JSON only. Do not include markdown or explanation.\n\n"
        "Schema:\n"
        + json.dumps(response_schema.model_json_schema(), indent=2)
        + "\n\nPrevious invalid JSON:\n"
        + invalid_response_text
    )


async def generate_structured_output(
    *,
    api_key: str,
    model_name: str,
    thinking_level: str,
    system_instruction: str,
    parts: Sequence[GeminiPart],
    response_schema: type[StructuredModel],
    temperature: float = 0.2,
    max_output_tokens: int = 8192,
) -> StructuredModel:
    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=[
            types.Content(
                role="user",
                parts=cast(Any, [_schema_instruction(response_schema), *parts]),
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(
                thinking_level=cast(Any, thinking_level),
                include_thoughts=False,
            ),
        ),
    )
    try:
        return _coerce_structured_response(response, response_schema)
    except (ValidationError, ValueError):
        invalid_response_text = getattr(response, "text", None)
        if not isinstance(invalid_response_text, str) or not invalid_response_text.strip():
            raise

        repair_response = await client.aio.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=cast(
                        Any,
                        [_repair_instruction(response_schema, invalid_response_text)],
                    ),
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You repair malformed JSON outputs. Return only valid JSON "
                    "matching the requested schema."
                ),
                temperature=0.0,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level=cast(Any, thinking_level),
                    include_thoughts=False,
                ),
            ),
        )
        return _coerce_structured_response(repair_response, response_schema)
