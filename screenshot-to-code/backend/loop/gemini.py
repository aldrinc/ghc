import base64
import json
import re
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
        return _coerce_structured_response_text(response_text, response_schema)

    raise ValueError("Gemini did not return parseable structured output")


def _coerce_structured_response_text(
    response_text: str,
    response_schema: type[StructuredModel],
) -> StructuredModel:
    last_error: Exception | None = None
    for candidate in _strict_json_candidates(response_text):
        try:
            return response_schema.model_validate_json(candidate)
        except ValidationError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("Gemini did not return parseable structured output")


def _coerce_repaired_structured_response_text(
    response_text: str,
    response_schema: type[StructuredModel],
) -> StructuredModel:
    last_error: Exception | None = None
    for candidate in _json_repair_candidates(response_text):
        try:
            return response_schema.model_validate_json(candidate)
        except ValidationError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("Gemini did not return parseable structured output")


def _json_repair_candidates(response_text: str) -> list[str]:
    candidates: list[str] = []

    def add(candidate: str) -> None:
        normalized = candidate.strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    add(response_text)
    extracted = _extract_json_object(response_text)
    if extracted is not None:
        add(extracted)

    add(_close_truncated_json(response_text))
    if extracted is not None:
        add(_close_truncated_json(extracted))
    return candidates


def _strict_json_candidates(response_text: str) -> list[str]:
    candidates: list[str] = []

    def add(candidate: str) -> None:
        normalized = candidate.strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    add(response_text)
    extracted = _extract_json_object(response_text)
    if extracted is not None:
        add(extracted)
    return candidates


def _extract_json_object(response_text: str) -> str | None:
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response_text, re.DOTALL)
    if fenced_match is not None:
        return fenced_match.group(1)

    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return response_text[start : end + 1]


def _close_truncated_json(response_text: str) -> str:
    text = response_text.strip()
    if not text:
        return text

    chars: list[str] = []
    stack: list[str] = []
    in_string = False
    escape = False

    for char in text:
        chars.append(char)
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in {"}", "]"} and stack:
            if stack[-1] == char:
                stack.pop()

    repaired = "".join(chars).rstrip()
    while repaired and repaired[-1] in {":", ","}:
        repaired = repaired[:-1].rstrip()

    if in_string:
        repaired += '"'

    while stack:
        closer = stack.pop()
        repaired = repaired.rstrip()
        if repaired.endswith(","):
            repaired = repaired[:-1].rstrip()
        repaired += closer

    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return repaired


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


def _retry_instruction(response_schema: type[StructuredModel]) -> dict[str, str]:
    return text_part(
        "Start over and return only valid compact JSON matching this schema. "
        "Do not include markdown, commentary, or partial strings. "
        "If necessary, omit lower-priority optional detail rather than returning invalid JSON.\n\n"
        "Schema:\n"
        + json.dumps(response_schema.model_json_schema(), indent=2)
    )


def _is_malformed_json_error(exc: Exception) -> bool:
    if isinstance(exc, ValidationError):
        return any(error.get("type") == "json_invalid" for error in exc.errors())
    return isinstance(exc, ValueError)


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
    except (ValidationError, ValueError) as exc:
        if not _is_malformed_json_error(exc):
            raise

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
        try:
            return _coerce_structured_response(repair_response, response_schema)
        except (ValidationError, ValueError) as repair_exc:
            if not _is_malformed_json_error(repair_exc):
                raise

            retry_response = await client.aio.models.generate_content(
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=cast(Any, [_retry_instruction(response_schema), *parts]),
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You return valid structured JSON only. "
                        "When output size is at risk, prefer a shorter but valid answer over an invalid or truncated one."
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
            try:
                return _coerce_structured_response(retry_response, response_schema)
            except (ValidationError, ValueError) as retry_exc:
                if not _is_malformed_json_error(retry_exc):
                    raise

                for fallback_text in (
                    getattr(retry_response, "text", None),
                    getattr(repair_response, "text", None),
                ):
                    if isinstance(fallback_text, str) and fallback_text.strip():
                        try:
                            return _coerce_repaired_structured_response_text(
                                fallback_text,
                                response_schema,
                            )
                        except (ValidationError, ValueError):
                            continue
                raise
