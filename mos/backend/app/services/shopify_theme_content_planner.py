from __future__ import annotations

import json
from typing import Any

from app.db.models import Asset, Product, ProductOffer
from app.llm.client import LLMClient, LLMGenerationParams
from app.services.claude_files import call_claude_structured_message

_MAX_IMAGE_SLOTS = 80
_MAX_TEXT_SLOTS = 120
_MAX_IMAGE_ASSETS = 40


def _clip_text_to_max_length(*, value: str, max_length: int | None) -> str:
    if not isinstance(max_length, int) or max_length <= 0:
        return value
    if len(value) <= max_length:
        return value
    clipped = value[:max_length].rstrip()
    if clipped:
        return clipped
    return value[:max_length]


def _score_asset_for_slot(
    *,
    slot_role: str,
    slot_recommended_aspect: str,
    asset_orientation: str,
) -> int:
    score = 0
    if slot_recommended_aspect == "any":
        score += 1
    elif slot_recommended_aspect == asset_orientation:
        score += 5
    elif slot_recommended_aspect in {"landscape", "portrait"} and asset_orientation == "square":
        score += 2
    elif slot_recommended_aspect == "square" and asset_orientation in {"landscape", "portrait"}:
        score += 1

    if slot_role == "hero" and asset_orientation == "landscape":
        score += 2
    elif slot_role == "gallery" and asset_orientation in {"square", "landscape"}:
        score += 2
    elif slot_role == "supporting" and asset_orientation in {"square", "portrait"}:
        score += 1
    return score


def _rebalance_image_assignments(
    *,
    component_image_asset_map: dict[str, str],
    image_slots: list[dict[str, Any]],
    image_assets: list[dict[str, Any]],
) -> dict[str, str]:
    slot_paths = [
        str(slot["path"])
        for slot in image_slots
        if isinstance(slot, dict)
        and isinstance(slot.get("path"), str)
        and str(slot["path"]).strip()
    ]
    if len(slot_paths) <= 1:
        return component_image_asset_map

    unique_assets_in_order: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    for asset in image_assets:
        if not isinstance(asset, dict):
            continue
        public_id = asset.get("publicId")
        if not isinstance(public_id, str) or not public_id.strip():
            continue
        normalized_public_id = public_id.strip()
        if normalized_public_id in seen_asset_ids:
            continue
        seen_asset_ids.add(normalized_public_id)
        unique_assets_in_order.append(asset)

    if len(unique_assets_in_order) <= 1:
        return component_image_asset_map

    expected_unique = min(len(slot_paths), len(unique_assets_in_order))
    current_unique = len(
        {
            component_image_asset_map[path]
            for path in slot_paths
            if isinstance(component_image_asset_map.get(path), str)
            and component_image_asset_map[path].strip()
        }
    )
    if current_unique >= expected_unique:
        return component_image_asset_map

    usage_by_asset_public_id: dict[str, int] = {}
    rebalanced: dict[str, str] = {}

    for slot in image_slots:
        if not isinstance(slot, dict):
            continue
        raw_path = slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        path = raw_path.strip()
        slot_role = (
            str(slot.get("role")).strip().lower()
            if isinstance(slot.get("role"), str)
            else "generic"
        )
        slot_recommended_aspect = (
            str(slot.get("recommendedAspect")).strip().lower()
            if isinstance(slot.get("recommendedAspect"), str)
            else "any"
        )
        if slot_recommended_aspect not in {"landscape", "portrait", "square", "any"}:
            slot_recommended_aspect = "any"

        best_asset_public_id: str | None = None
        best_score: tuple[int, int, int] | None = None
        for index, asset in enumerate(unique_assets_in_order):
            raw_public_id = asset.get("publicId")
            if not isinstance(raw_public_id, str) or not raw_public_id.strip():
                continue
            asset_public_id = raw_public_id.strip()
            asset_orientation = (
                str(asset.get("orientation")).strip().lower()
                if isinstance(asset.get("orientation"), str)
                else "unknown"
            )
            usage_count = usage_by_asset_public_id.get(asset_public_id, 0)
            unused_bonus = 100 if usage_count == 0 else 0
            suitability = _score_asset_for_slot(
                slot_role=slot_role,
                slot_recommended_aspect=slot_recommended_aspect,
                asset_orientation=asset_orientation,
            )
            candidate_score = (
                unused_bonus + suitability - (usage_count * 10),
                -usage_count,
                -index,
            )
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                best_asset_public_id = asset_public_id

        if not best_asset_public_id:
            raise ValueError(
                f"Theme content planner could not assign an image asset for slot {path}."
            )
        rebalanced[path] = best_asset_public_id
        usage_by_asset_public_id[best_asset_public_id] = (
            usage_by_asset_public_id.get(best_asset_public_id, 0) + 1
        )

    if set(rebalanced.keys()) != set(slot_paths):
        missing_paths = sorted(set(slot_paths) - set(rebalanced.keys()))
        raise ValueError(
            "Theme content planner did not assign all image slots after rebalancing: "
            + ", ".join(missing_paths)
        )
    return rebalanced


def _asset_orientation(*, width: int | None, height: int | None) -> str:
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return "unknown"
    ratio = width / height
    if ratio >= 1.25:
        return "landscape"
    if ratio <= 0.8:
        return "portrait"
    return "square"


def _planner_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "imageAssignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "minLength": 1},
                        "assetPublicId": {"type": "string", "minLength": 1},
                    },
                    "required": ["path", "assetPublicId"],
                },
            },
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
            },
        },
        "required": ["imageAssignments", "textAssignments"],
    }


def _build_planner_prompt(
    *,
    product: Product,
    offers: list[ProductOffer],
    image_assets: list[dict[str, Any]],
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
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

    instructions = [
        "You are selecting Shopify theme content for a single product.",
        "Choose image assets for each image slot, matching role and recommended aspect ratio.",
        "Write concise product-specific copy for each text slot. Do not invent unsupported medical or legal claims.",
        "Respect each text slot maxLength exactly.",
        "Use diverse images across slots; do not reuse one image everywhere unless only one asset exists.",
        "Return ONLY JSON that matches the schema.",
    ]

    return (
        "\n".join(instructions)
        + "\n\nProduct context JSON:\n"
        + json.dumps(product_payload, ensure_ascii=False, indent=2)
        + "\n\nAvailable image assets JSON:\n"
        + json.dumps(image_assets, ensure_ascii=False, indent=2)
        + "\n\nImage slots JSON:\n"
        + json.dumps(image_slots, ensure_ascii=False, indent=2)
        + "\n\nText slots JSON:\n"
        + json.dumps(text_slots, ensure_ascii=False, indent=2)
    )


def _parse_and_validate_planner_output(
    *,
    parsed: Any,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
    asset_public_ids: set[str],
) -> dict[str, dict[str, str]]:
    if not isinstance(parsed, dict):
        raise ValueError("Theme content planner returned a non-object response.")

    raw_image_assignments = parsed.get("imageAssignments")
    raw_text_assignments = parsed.get("textAssignments")
    if not isinstance(raw_image_assignments, list) or not isinstance(raw_text_assignments, list):
        raise ValueError("Theme content planner returned invalid assignments payload.")

    image_slot_paths = {str(slot["path"]) for slot in image_slots}
    text_slots_by_path: dict[str, dict[str, Any]] = {str(slot["path"]): slot for slot in text_slots}

    component_image_asset_map: dict[str, str] = {}
    for assignment in raw_image_assignments:
        if not isinstance(assignment, dict):
            raise ValueError("Theme content planner returned an invalid image assignment entry.")
        path = assignment.get("path")
        asset_public_id = assignment.get("assetPublicId")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(
                "Theme content planner returned an image assignment with invalid path."
            )
        if not isinstance(asset_public_id, str) or not asset_public_id.strip():
            raise ValueError(
                f"Theme content planner returned an image assignment with invalid asset id at {path}."
            )
        normalized_path = path.strip()
        normalized_asset_public_id = asset_public_id.strip()
        if normalized_path not in image_slot_paths:
            raise ValueError(
                f"Theme content planner returned an unknown image slot path: {normalized_path}."
            )
        if normalized_asset_public_id not in asset_public_ids:
            raise ValueError(
                f"Theme content planner returned an unknown image asset id ({normalized_asset_public_id}) "
                f"for path {normalized_path}."
            )
        if normalized_path in component_image_asset_map:
            raise ValueError(
                f"Theme content planner returned duplicate image assignment for path {normalized_path}."
            )
        component_image_asset_map[normalized_path] = normalized_asset_public_id

    if image_slot_paths and set(component_image_asset_map.keys()) != image_slot_paths:
        missing = sorted(image_slot_paths - set(component_image_asset_map.keys()))
        raise ValueError(
            f"Theme content planner did not assign all image slots: {', '.join(missing)}."
        )

    component_text_values: dict[str, str] = {}
    for assignment in raw_text_assignments:
        if not isinstance(assignment, dict):
            raise ValueError("Theme content planner returned an invalid text assignment entry.")
        path = assignment.get("path")
        value = assignment.get("value")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Theme content planner returned a text assignment with invalid path.")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Theme content planner returned an empty text value at path {path}.")
        normalized_path = path.strip()
        normalized_value = value.strip()
        slot = text_slots_by_path.get(normalized_path)
        if slot is None:
            raise ValueError(
                f"Theme content planner returned an unknown text slot path: {normalized_path}."
            )
        max_length = slot.get("maxLength")
        normalized_value = _clip_text_to_max_length(
            value=normalized_value,
            max_length=max_length,
        )
        if normalized_path in component_text_values:
            raise ValueError(
                f"Theme content planner returned duplicate text assignment for path {normalized_path}."
            )
        component_text_values[normalized_path] = normalized_value

    text_slot_paths = set(text_slots_by_path.keys())
    if text_slot_paths and set(component_text_values.keys()) != text_slot_paths:
        missing = sorted(text_slot_paths - set(component_text_values.keys()))
        raise ValueError(
            f"Theme content planner did not assign all text slots: {', '.join(missing)}."
        )

    return {
        "componentImageAssetMap": component_image_asset_map,
        "componentTextValues": component_text_values,
    }


def plan_shopify_theme_component_content(
    *,
    product: Product,
    offers: list[ProductOffer],
    product_image_assets: list[Asset],
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    if not image_slots and not text_slots:
        raise ValueError(
            "No candidate image or text slots were discovered in the Shopify theme templates."
        )
    if not product_image_assets and image_slots:
        raise ValueError("No product image assets were provided for image slot planning.")

    truncated_image_slots = image_slots[:_MAX_IMAGE_SLOTS]
    truncated_text_slots = text_slots[:_MAX_TEXT_SLOTS]
    truncated_assets = product_image_assets[:_MAX_IMAGE_ASSETS]

    image_assets_payload = [
        {
            "publicId": str(asset.public_id),
            "width": asset.width,
            "height": asset.height,
            "orientation": _asset_orientation(width=asset.width, height=asset.height),
            "alt": str(asset.alt or "").strip() or None,
            "tags": [tag for tag in (asset.tags or []) if isinstance(tag, str) and tag.strip()][
                :20
            ],
            "aiMetadata": (asset.ai_metadata if isinstance(asset.ai_metadata, dict) else None),
        }
        for asset in truncated_assets
        if asset.public_id
    ]
    if not image_assets_payload and truncated_image_slots:
        raise ValueError("No valid product image assets were available after normalization.")

    prompt = _build_planner_prompt(
        product=product,
        offers=offers,
        image_assets=image_assets_payload,
        image_slots=truncated_image_slots,
        text_slots=truncated_text_slots,
    )

    llm = LLMClient()
    model_id = llm.default_model
    output_schema = _planner_output_schema()

    try:
        if model_id.lower().startswith("claude"):
            response = call_claude_structured_message(
                model=model_id,
                system=None,
                user_content=[{"type": "text", "text": prompt}],
                output_schema=output_schema,
                max_tokens=7000,
                temperature=0.1,
            )
            parsed = response.get("parsed")
        else:
            raw = llm.generate_text(
                prompt,
                params=LLMGenerationParams(
                    model=model_id,
                    max_tokens=7000,
                    temperature=0.1,
                    use_reasoning=True,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ShopifyThemeComponentPlan",
                            "strict": True,
                            "schema": output_schema,
                        },
                    },
                ),
            )
            parsed = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Theme content planner failed: {exc}") from exc

    asset_public_ids = {str(asset["publicId"]) for asset in image_assets_payload}
    parsed_output = _parse_and_validate_planner_output(
        parsed=parsed,
        image_slots=truncated_image_slots,
        text_slots=truncated_text_slots,
        asset_public_ids=asset_public_ids,
    )
    component_image_asset_map = parsed_output.get("componentImageAssetMap") or {}
    rebalanced_image_asset_map = _rebalance_image_assignments(
        component_image_asset_map=component_image_asset_map,
        image_slots=truncated_image_slots,
        image_assets=image_assets_payload,
    )
    if len(truncated_image_slots) >= 2 and len(asset_public_ids) >= 2:
        unique_asset_count = len(set(rebalanced_image_asset_map.values()))
        if unique_asset_count < 2:
            raise ValueError(
                "Theme content planner assigned the same image to all slots despite multiple assets. "
                "Use varied assets."
            )
    parsed_output["componentImageAssetMap"] = rebalanced_image_asset_map
    return parsed_output
