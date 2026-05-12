from __future__ import annotations

import hashlib
import json
from typing import Any

from app.schemas.animated_templates import AnimatedTemplateRenderRequest


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    product_replacement = manifest.get("productReplacement") or {}
    layers = manifest.get("layers") or []
    generative_regions = [
        layer for layer in layers if isinstance(layer, dict) and layer.get("policy") == "generative_region"
    ]
    product_swap_layers = [
        layer for layer in layers if isinstance(layer, dict) and layer.get("policy") == "product_swap"
    ]
    return {
        "schemaVersion": manifest.get("schemaVersion"),
        "layerCount": len(layers),
        "lockedLayerCount": len(layers) - len(generative_regions),
        "generativeRegionCount": len(generative_regions),
        "productSwapLayerCount": len(product_swap_layers),
        "hasCompetitorProductSlot": bool(
            product_replacement.get("hasCompetitorProductSlot")
        ),
        "aiRequired": bool(generative_regions),
        "renderableWithoutAi": not bool(generative_regions),
    }


def validate_manifest_payload(
    manifest: dict[str, Any],
    *,
    profile: str = "draft",
) -> dict[str, Any]:
    blocking_errors: list[dict[str, Any]] = []
    review_reasons: list[str] = []
    warnings: list[dict[str, Any]] = []

    layers = manifest.get("layers") or []
    product_replacement = manifest.get("productReplacement") or {}
    has_product_slot = bool(product_replacement.get("hasCompetitorProductSlot"))
    product_slots = product_replacement.get("slots") or []
    approved_product_slots = [
        slot for slot in product_slots if isinstance(slot, dict) and slot.get("status") == "approved"
    ]

    layer_ids: set[str] = set()
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            blocking_errors.append(
                {
                    "code": "INVALID_LAYER",
                    "message": f"Layer at index {index} must be an object.",
                }
            )
            continue

        layer_id = str(layer.get("id") or "").strip()
        if not layer_id:
            blocking_errors.append(
                {
                    "code": "MISSING_LAYER_ID",
                    "message": f"Layer at index {index} is missing id.",
                }
            )
        elif layer_id in layer_ids:
            blocking_errors.append(
                {
                    "code": "DUPLICATE_LAYER_ID",
                    "message": f"Layer id {layer_id} appears more than once.",
                    "layerId": layer_id,
                }
            )
        else:
            layer_ids.add(layer_id)

        policy = layer.get("policy")
        render_owner = layer.get("renderOwner")
        if policy != "generative_region" and render_owner == "ai_region_model":
            blocking_errors.append(
                {
                    "code": "LOCKED_LAYER_AI_OWNER_FORBIDDEN",
                    "message": "Locked template layers must be rendered deterministically.",
                    "layerId": layer_id or None,
                }
            )
        if policy == "generative_region" and not layer.get("mask"):
            blocking_errors.append(
                {
                    "code": "GENERATIVE_REGION_MISSING_MASK",
                    "message": "Generative region layers require an explicit mask.",
                    "layerId": layer_id or None,
                }
            )
        if policy == "product_swap":
            if not has_product_slot:
                blocking_errors.append(
                    {
                        "code": "PRODUCT_SLOT_REQUIRED",
                        "message": "Product swap layers require source product-slot evidence.",
                        "layerId": layer_id or None,
                    }
                )
            if not layer.get("productSlotId"):
                blocking_errors.append(
                    {
                        "code": "PRODUCT_SWAP_SLOT_ID_REQUIRED",
                        "message": "Product swap layers require productSlotId.",
                        "layerId": layer_id or None,
                    }
                )

        source_frame_indexes = layer.get("sourceFrameIndexes") or []
        metadata = layer.get("metadata") if isinstance(layer.get("metadata"), dict) else {}
        has_source_evidence = bool(source_frame_indexes) or bool(metadata.get("sourceEvidence"))
        if policy in {"locked_source", "deterministic_rebuild", "editable_text", "product_swap"}:
            if profile in {"approval", "render"} and not has_source_evidence:
                blocking_errors.append(
                    {
                        "code": "SOURCE_EVIDENCE_REQUIRED",
                        "message": (
                            "Source-locked and deterministic layers require source-frame evidence "
                            "before approval or rendering."
                        ),
                        "layerId": layer_id or None,
                    }
                )
            elif profile == "draft" and not has_source_evidence:
                warnings.append(
                    {
                        "code": "SOURCE_EVIDENCE_RECOMMENDED",
                        "message": (
                            "Add sourceFrameIndexes or metadata.sourceEvidence before approval."
                        ),
                        "layerId": layer_id or None,
                    }
                )

    if has_product_slot and not approved_product_slots:
        blocking_errors.append(
            {
                "code": "PRODUCT_SLOT_REVIEW_REQUIRED",
                "message": "hasCompetitorProductSlot requires at least one approved slot.",
            }
        )
    for slot in approved_product_slots:
        if not slot.get("evidence"):
            blocking_errors.append(
                {
                    "code": "PRODUCT_SLOT_MISSING_EVIDENCE",
                    "message": "Approved product slots require source evidence.",
                    "slotId": slot.get("id"),
                }
            )
        if not slot.get("geometry") and not slot.get("mask"):
            blocking_errors.append(
                {
                    "code": "PRODUCT_SLOT_MISSING_GEOMETRY",
                    "message": "Approved product slots require geometry or a mask.",
                    "slotId": slot.get("id"),
                }
            )

    if profile == "approval" and not blocking_errors:
        review_reasons.append("approval_required_before_render")
    elif profile == "draft":
        review_reasons.append("manifest_review_required")

    status = "invalid" if blocking_errors else ("valid_with_review" if review_reasons else "valid")
    return {
        "status": status,
        "blockingErrors": blocking_errors,
        "reviewReasons": review_reasons,
        "warnings": warnings,
    }


def validate_render_request(
    manifest: dict[str, Any],
    render_request: AnimatedTemplateRenderRequest,
) -> dict[str, Any]:
    validation = validate_manifest_payload(manifest, profile="render")
    blocking_errors = list(validation.get("blockingErrors") or [])
    warnings = list(validation.get("warnings") or [])

    product_replacement = manifest.get("productReplacement") or {}
    has_product_slot = bool(product_replacement.get("hasCompetitorProductSlot"))
    layers = manifest.get("layers") or []
    ai_regions = [
        layer for layer in layers if isinstance(layer, dict) and layer.get("policy") == "generative_region"
    ]

    if render_request.product_replacement_requested and not has_product_slot:
        blocking_errors.append(
            {
                "code": "PRODUCT_SLOT_REQUIRED",
                "message": (
                    "Product replacement was requested, but the approved manifest does not "
                    "contain a competitor product slot."
                ),
            }
        )
    if render_request.render_mode == "deterministic" and ai_regions:
        blocking_errors.append(
            {
                "code": "RENDER_MODE_INCOMPATIBLE",
                "message": "deterministic render mode cannot render generative regions.",
            }
        )
    if render_request.render_mode == "hybrid" and ai_regions and not render_request.model_selection:
        blocking_errors.append(
            {
                "code": "MODEL_SELECTION_REQUIRED",
                "message": "hybrid render mode requires modelSelection when the manifest has AI-owned regions.",
            }
        )
    if render_request.model_selection and not ai_regions:
        blocking_errors.append(
            {
                "code": "UNUSED_MODEL_SELECTION",
                "message": "A model was selected, but this manifest has no AI-owned regions.",
            }
        )

    return {
        "status": "invalid" if blocking_errors else "valid",
        "blockingErrors": blocking_errors,
        "reviewReasons": [],
        "warnings": warnings,
    }
