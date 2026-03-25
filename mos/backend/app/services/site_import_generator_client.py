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
    pass


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

    request_payload: dict[str, Any] = {
        "generatedCodeConfig": "react_tailwind",
        "generationType": "create",
        "inputMode": "image",
        "requestSource": "mos_import",
        "modelSlots": model_slots,
        "prompt": {
            "text": _build_prompt(source_url=source_url, page_type_hint=page_type_hint),
            "images": [screenshot_data_url],
            "videos": [],
        },
    }

    transcript: list[dict[str, Any]] = []
    variant_models: list[str] = []
    variants_by_index: dict[int, dict[str, Any]] = {}
    error_message: str | None = None

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
                        "Timed out waiting for screenshot-to-code response."
                    ) from exc
                except websockets.ConnectionClosedOK:
                    break
                except websockets.ConnectionClosedError as exc:
                    if error_message:
                        raise SiteImportGeneratorError(error_message) from exc
                    raise SiteImportGeneratorError(
                        f"screenshot-to-code websocket closed unexpectedly: {exc}"
                    ) from exc

                message = json.loads(raw_message)
                # Annotate each transcript entry with capture timestamp for UI
                message["capturedAt"] = datetime.now(timezone.utc).isoformat()
                message["localSequence"] = len(transcript)
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
                    variant_entry["error"] = message.get("value")
                elif message.get("type") == "error":
                    error_message = str(
                        message.get("value") or "screenshot-to-code generation failed"
                    )
    except SiteImportGeneratorError:
        raise
    except Exception as exc:  # pragma: no cover - defensive networking wrapper
        raise SiteImportGeneratorError(f"Failed to connect to screenshot-to-code: {exc}") from exc

    if error_message:
        raise SiteImportGeneratorError(error_message)

    variants = [variants_by_index[index] for index in sorted(variants_by_index)]
    if not variants:
        raise SiteImportGeneratorError("screenshot-to-code returned no variants.")

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


def _build_prompt(*, source_url: str, page_type_hint: str | None) -> str:
    page_hint = (
        page_type_hint.strip()
        if isinstance(page_type_hint, str) and page_type_hint.strip()
        else "unspecified"
    )
    return (
        "Generate a React + Tailwind implementation from this website screenshot. "
        "Preserve the visual structure and content intent. "
        f"Source URL: {source_url}. "
        f"Requested page role hint: {page_hint}."
    )
