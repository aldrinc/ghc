from __future__ import annotations

import json
from typing import Any

from app.db.models import Product, ProductOffer
from app.llm.client import LLMClient, LLMGenerationParams
from app.services.claude_files import call_claude_structured_message

_MAX_TEXT_SLOTS = 120
_MAX_GUIDELINES = 20
_MAX_GUIDELINE_LENGTH = 180


def _clip_text_to_max_length(*, value: str, max_length: int | None) -> str:
    if not isinstance(max_length, int) or max_length <= 0:
        return value
    if len(value) <= max_length:
        return value
    clipped = value[:max_length].rstrip()
    if clipped:
        return clipped
    return value[:max_length]


def _normalize_optional_string_list(*, field_name: str, values: list[str] | None) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list of strings.")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(values):
        if not isinstance(raw, str):
            raise ValueError(f"{field_name}[{index}] must be a string.")
        cleaned = raw.strip()
        if not cleaned:
            raise ValueError(f"{field_name}[{index}] cannot be empty.")
        if len(cleaned) > _MAX_GUIDELINE_LENGTH:
            raise ValueError(
                f"{field_name}[{index}] exceeds maximum length {_MAX_GUIDELINE_LENGTH}."
            )
        dedupe_key = cleaned.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(cleaned)
    if len(normalized) > _MAX_GUIDELINES:
        raise ValueError(f"{field_name} exceeds maximum item count {_MAX_GUIDELINES}.")
    return normalized


def _normalize_optional_string(
    *,
    field_name: str,
    value: str | None,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} exceeds maximum length {max_length}.")
    return cleaned


def _copy_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "textAssignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "minLength": 1},
                        "value": {"type": "string", "minLength": 1},
                    },
                    "required": ["path", "value"],
                },
            }
        },
        "required": ["textAssignments"],
    }


def _build_copy_prompt(
    *,
    product: Product,
    offers: list[ProductOffer],
    text_slots: list[dict[str, Any]],
    tone_guidelines: list[str],
    must_avoid_claims: list[str],
    cta_style: str | None,
    reading_level: str | None,
    locale: str | None,
) -> str:
    product_payload = {
        "id": str(product.id),
        "title": str(product.title or "").strip(),
        "description": str(product.description or "").strip(),
        "productType": str(product.product_type or "").strip(),
        "primaryBenefits": [
            item.strip()
            for item in (product.primary_benefits or [])
            if isinstance(item, str) and item.strip()
        ],
        "featureBullets": [
            item.strip()
            for item in (product.feature_bullets or [])
            if isinstance(item, str) and item.strip()
        ],
        "guaranteeText": str(product.guarantee_text or "").strip(),
        "disclaimers": [
            item.strip()
            for item in (product.disclaimers or [])
            if isinstance(item, str) and item.strip()
        ],
        "offers": [
            {
                "name": str(offer.name or "").strip(),
                "description": str(offer.description or "").strip(),
                "differentiationBullets": [
                    item.strip()
                    for item in (offer.differentiation_bullets or [])
                    if isinstance(item, str) and item.strip()
                ],
                "guaranteeText": str(offer.guarantee_text or "").strip(),
            }
            for offer in offers[:10]
        ],
    }
    copy_controls = {
        "toneGuidelines": tone_guidelines,
        "mustAvoidClaims": must_avoid_claims,
        "ctaStyle": cta_style,
        "readingLevel": reading_level,
        "locale": locale,
    }

    instructions = [
        "You are writing Shopify theme component copy for one product page.",
        "Write concise, conversion-focused copy for every text slot.",
        "Respect each slot maxLength exactly.",
        "Never invent unsupported medical, legal, or compliance claims.",
        "Keep phrasing product-specific and consistent across the page.",
        "Return ONLY JSON that matches the schema.",
    ]

    return (
        "\n".join(instructions)
        + "\n\nCopy controls JSON:\n"
        + json.dumps(copy_controls, ensure_ascii=False, indent=2)
        + "\n\nProduct context JSON:\n"
        + json.dumps(product_payload, ensure_ascii=False, indent=2)
        + "\n\nText slots JSON:\n"
        + json.dumps(text_slots, ensure_ascii=False, indent=2)
    )


def _parse_and_validate_copy_output(
    *,
    parsed: Any,
    text_slots: list[dict[str, Any]],
) -> dict[str, str]:
    if not isinstance(parsed, dict):
        raise ValueError("Theme copy agent returned a non-object response.")
    raw_text_assignments = parsed.get("textAssignments")
    if not isinstance(raw_text_assignments, list):
        raise ValueError("Theme copy agent returned invalid assignments payload.")

    text_slots_by_path: dict[str, dict[str, Any]] = {
        str(slot["path"]): slot for slot in text_slots
    }
    component_text_values: dict[str, str] = {}
    for assignment in raw_text_assignments:
        if not isinstance(assignment, dict):
            raise ValueError("Theme copy agent returned an invalid text assignment entry.")
        path = assignment.get("path")
        value = assignment.get("value")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Theme copy agent returned a text assignment with invalid path.")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Theme copy agent returned an empty text value at path {path}.")
        normalized_path = path.strip()
        normalized_value = value.strip()
        slot = text_slots_by_path.get(normalized_path)
        if slot is None:
            raise ValueError(
                f"Theme copy agent returned an unknown text slot path: {normalized_path}."
            )
        max_length = slot.get("maxLength")
        normalized_value = _clip_text_to_max_length(
            value=normalized_value,
            max_length=max_length,
        )
        if normalized_path in component_text_values:
            raise ValueError(
                f"Theme copy agent returned duplicate text assignment for path {normalized_path}."
            )
        component_text_values[normalized_path] = normalized_value

    text_slot_paths = set(text_slots_by_path.keys())
    if text_slot_paths and set(component_text_values.keys()) != text_slot_paths:
        missing = sorted(text_slot_paths - set(component_text_values.keys()))
        raise ValueError(
            f"Theme copy agent did not assign all text slots: {', '.join(missing)}."
        )

    return component_text_values


def generate_shopify_theme_component_copy(
    *,
    product: Product,
    offers: list[ProductOffer],
    text_slots: list[dict[str, Any]],
    tone_guidelines: list[str] | None = None,
    must_avoid_claims: list[str] | None = None,
    cta_style: str | None = None,
    reading_level: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    truncated_text_slots = text_slots[:_MAX_TEXT_SLOTS]
    if not truncated_text_slots:
        return {"componentTextValues": {}, "model": None}

    normalized_tone_guidelines = _normalize_optional_string_list(
        field_name="tone_guidelines",
        values=tone_guidelines,
    )
    normalized_must_avoid_claims = _normalize_optional_string_list(
        field_name="must_avoid_claims",
        values=must_avoid_claims,
    )
    normalized_cta_style = _normalize_optional_string(
        field_name="cta_style",
        value=cta_style,
        max_length=32,
    )
    normalized_reading_level = _normalize_optional_string(
        field_name="reading_level",
        value=reading_level,
        max_length=32,
    )
    normalized_locale = _normalize_optional_string(
        field_name="locale",
        value=locale,
        max_length=16,
    )

    prompt = _build_copy_prompt(
        product=product,
        offers=offers,
        text_slots=truncated_text_slots,
        tone_guidelines=normalized_tone_guidelines,
        must_avoid_claims=normalized_must_avoid_claims,
        cta_style=normalized_cta_style,
        reading_level=normalized_reading_level,
        locale=normalized_locale,
    )

    llm = LLMClient()
    model_id = llm.default_model
    output_schema = _copy_output_schema()
    try:
        if model_id.lower().startswith("claude"):
            response = call_claude_structured_message(
                model=model_id,
                system=None,
                user_content=[{"type": "text", "text": prompt}],
                output_schema=output_schema,
                max_tokens=5000,
                temperature=0.2,
            )
            parsed = response.get("parsed")
        else:
            raw = llm.generate_text(
                prompt,
                params=LLMGenerationParams(
                    model=model_id,
                    max_tokens=5000,
                    temperature=0.2,
                    use_reasoning=True,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ShopifyThemeComponentCopyPlan",
                            "strict": True,
                            "schema": output_schema,
                        },
                    },
                ),
            )
            parsed = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Theme copy agent failed: {exc}") from exc

    component_text_values = _parse_and_validate_copy_output(
        parsed=parsed,
        text_slots=truncated_text_slots,
    )
    return {
        "componentTextValues": component_text_values,
        "model": model_id,
    }
