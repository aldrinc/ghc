from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import websockets

from app.config import settings


@dataclass(frozen=True)
class GeneratorRunResult:
    request_payload: dict[str, Any]
    transcript: list[dict[str, Any]]
    variants: list[dict[str, Any]]
    metadata: dict[str, Any]


class SiteImportGeneratorError(Exception):
    def __init__(
        self,
        message: str,
        *,
        transcript: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.transcript = transcript or []


_GENERIC_GENERATOR_ERROR_MESSAGE = "Error generating code. Please contact support."
_MAX_GENERATION_ATTEMPTS = 3
_TRANSIENT_GENERATOR_ERROR_MARKERS = (
    "503 service unavailable",
    '"status": "unavailable"',
    "currently experiencing high demand",
)


def _build_request_payload(
    *,
    screenshot_data_url: str,
    source_url: str,
    page_type_hint: str | None,
    model_slots: list[int],
) -> dict[str, Any]:
    return {
        "generatedCodeConfig": "react_tailwind",
        "generationType": "create",
        "inputMode": "image",
        "requestSource": "mos_import",
        # MOS imports should adapt the captured site reference, not generate
        # replacement assets that then get pushed back into model context.
        "isImageGenerationEnabled": False,
        "modelSlots": model_slots,
        "prompt": {
            "text": _build_prompt(source_url=source_url, page_type_hint=page_type_hint),
            "images": [screenshot_data_url],
            "videos": [],
        },
    }


def _resolve_generator_error_message(
    *,
    error_message: str | None,
    variant_error_messages: list[str],
) -> str | None:
    normalized_error = error_message.strip() if isinstance(error_message, str) else None
    specific_variant_error = next(
        (
            candidate.strip()
            for candidate in reversed(variant_error_messages)
            if isinstance(candidate, str) and candidate.strip()
        ),
        None,
    )

    if not normalized_error:
        return None
    if normalized_error != _GENERIC_GENERATOR_ERROR_MESSAGE:
        return normalized_error
    return specific_variant_error or normalized_error


def _is_transient_generator_error(message: str | None) -> bool:
    if not isinstance(message, str) or not message.strip():
        return False
    normalized = message.lower()
    return any(marker in normalized for marker in _TRANSIENT_GENERATOR_ERROR_MARKERS)


async def _emit_retry_status_event(
    *,
    transcript: list[dict[str, Any]],
    error_message: str,
    next_attempt: int,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None,
) -> None:
    event = {
        "type": "status",
        "value": (
            f"Retrying screenshot-to-code after transient upstream failure "
            f"(attempt {next_attempt} of {_MAX_GENERATION_ATTEMPTS})."
        ),
        "variantIndex": 0,
        "data": {"reason": error_message},
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "localSequence": len(transcript),
    }
    transcript.append(event)
    if on_event is not None:
        await on_event(event)


async def _run_generation_attempt(
    *,
    request_payload: dict[str, Any],
    input_mode: str,
    model_slots: list[int],
    transcript_offset: int,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> GeneratorRunResult:
    transcript: list[dict[str, Any]] = []
    variant_models: list[str] = []
    variants_by_index: dict[int, dict[str, Any]] = {}
    error_message: str | None = None
    variant_error_messages: list[str] = []

    try:
        async with websockets.connect(
            str(settings.SCREENSHOT_TO_CODE_WS_URL), max_size=268435456
        ) as websocket:
            await websocket.send(json.dumps(request_payload))

            while True:
                try:
                    raw_message = await asyncio.wait_for(websocket.recv(), timeout=300)
                except asyncio.TimeoutError as exc:
                    raise SiteImportGeneratorError(
                        "Timed out waiting for screenshot-to-code response.",
                        transcript=transcript,
                    ) from exc
                except websockets.ConnectionClosedOK:
                    break
                except websockets.ConnectionClosedError as exc:
                    resolved_error = _resolve_generator_error_message(
                        error_message=error_message,
                        variant_error_messages=variant_error_messages,
                    )
                    if resolved_error:
                        raise SiteImportGeneratorError(
                            resolved_error,
                            transcript=transcript,
                        ) from exc
                    raise SiteImportGeneratorError(
                        f"screenshot-to-code websocket closed unexpectedly: {exc}",
                        transcript=transcript,
                    ) from exc

                message = json.loads(raw_message)
                message["capturedAt"] = datetime.now(timezone.utc).isoformat()
                message["localSequence"] = transcript_offset + len(transcript)
                transcript.append(message)
                if on_event is not None:
                    await on_event(message)

                variant_index = int(message.get("variantIndex", 0) or 0)
                variant_entry = variants_by_index.setdefault(
                    variant_index,
                    {"variantIndex": variant_index, "code": None, "status": "pending"},
                )

                if message.get("type") == "variantModels":
                    models = message.get("data", {}).get("models", [])
                    if isinstance(models, list):
                        variant_models = [str(model) for model in models]
                elif message.get("type") == "setCode":
                    variant_entry["code"] = message.get("value")
                elif message.get("type") == "variantComplete":
                    variant_entry["status"] = "completed"
                    if isinstance(message.get("data"), dict):
                        variant_entry["completion"] = message.get("data")
                elif message.get("type") == "variantError":
                    variant_entry["status"] = "failed"
                    variant_error = str(message.get("value") or "screenshot-to-code generation failed")
                    variant_entry["error"] = variant_error
                    variant_error_messages.append(variant_error)
                elif message.get("type") == "error":
                    candidate = str(
                        message.get("value") or "screenshot-to-code generation failed"
                    )
                    error_message = _resolve_generator_error_message(
                        error_message=candidate,
                        variant_error_messages=variant_error_messages,
                    )
    except SiteImportGeneratorError:
        raise
    except Exception as exc:  # pragma: no cover - defensive networking wrapper
        raise SiteImportGeneratorError(f"Failed to connect to screenshot-to-code: {exc}") from exc

    if error_message:
        raise SiteImportGeneratorError(error_message, transcript=transcript)

    variants = [variants_by_index[index] for index in sorted(variants_by_index)]
    if not variants:
        raise SiteImportGeneratorError(
            "screenshot-to-code returned no variants.",
            transcript=transcript,
        )

    for index, variant in enumerate(variants):
        slot = model_slots[index] if index < len(model_slots) else None
        variant["modelSlot"] = slot
        if index < len(variant_models):
            variant["modelId"] = variant_models[index]

    return GeneratorRunResult(
        request_payload=request_payload,
        transcript=transcript,
        variants=variants,
        metadata={
            "generatorSystem": "screenshot-to-code",
            "stack": "react_tailwind",
            "inputMode": input_mode,
            "variantCount": len(variants),
            "variantModels": variant_models,
        },
    )


async def generate_react_tailwind_from_screenshot(
    *,
    screenshot_data_url: str,
    source_url: str,
    page_type_hint: str | None,
    input_mode: str,
    model_slots: list[int],
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> GeneratorRunResult:
    if input_mode != "image":
        raise SiteImportGeneratorError(
            f"Unsupported import input mode: {input_mode}. URL imports currently support image mode only."
        )

    request_payload = _build_request_payload(
        screenshot_data_url=screenshot_data_url,
        source_url=source_url,
        page_type_hint=page_type_hint,
        model_slots=model_slots,
    )
    combined_transcript: list[dict[str, Any]] = []

    for attempt in range(1, _MAX_GENERATION_ATTEMPTS + 1):
        try:
            result = await _run_generation_attempt(
                request_payload=request_payload,
                input_mode=input_mode,
                model_slots=model_slots,
                transcript_offset=len(combined_transcript),
                on_event=on_event,
            )
        except SiteImportGeneratorError as exc:
            combined_transcript.extend(exc.transcript)
            if attempt < _MAX_GENERATION_ATTEMPTS and _is_transient_generator_error(str(exc)):
                await _emit_retry_status_event(
                    transcript=combined_transcript,
                    error_message=str(exc),
                    next_attempt=attempt + 1,
                    on_event=on_event,
                )
                await asyncio.sleep(2 * attempt)
                continue
            raise SiteImportGeneratorError(
                str(exc),
                transcript=combined_transcript,
            ) from exc

        combined_transcript.extend(result.transcript)
        metadata = dict(result.metadata)
        metadata["attemptCount"] = attempt
        return GeneratorRunResult(
            request_payload=request_payload,
            transcript=combined_transcript,
            variants=result.variants,
            metadata=metadata,
        )

    raise SiteImportGeneratorError(
        "screenshot-to-code generation exhausted all attempts.",
        transcript=combined_transcript,
    )


def _build_prompt(*, source_url: str, page_type_hint: str | None) -> str:
    page_hint = (
        page_type_hint.strip()
        if isinstance(page_type_hint, str) and page_type_hint.strip()
        else "unspecified"
    )
    return (
        "Generate a React + Tailwind implementation from this website screenshot. "
        "Preserve the visual structure and content intent. "
        "Do not call image generation tools, invent replacement artwork, or fabricate "
        "logos or product assets that are not visible in the screenshot. "
        "Use the provided screenshot as the only visual reference. "
        f"Source URL: {source_url}. "
        f"Requested page role hint: {page_hint}."
    )
