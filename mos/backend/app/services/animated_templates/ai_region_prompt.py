from __future__ import annotations

import json
from typing import Any

from app.schemas.animated_templates import AnimatedTemplateRenderRequest
from app.services.animated_templates.manifest_validation import validate_render_request


def build_ai_region_generation_prompt(
    *,
    manifest: dict[str, Any],
    render_request: AnimatedTemplateRenderRequest,
) -> dict[str, Any]:
    validation = validate_render_request(manifest, render_request)
    if validation.get("blockingErrors"):
        raise RuntimeError("Cannot build AI-region prompt for an invalid animated render request.")

    layers = [layer for layer in manifest.get("layers") or [] if isinstance(layer, dict)]
    ai_region_layers = [layer for layer in layers if layer.get("policy") == "generative_region"]
    if not ai_region_layers:
        raise RuntimeError("AI-region prompt requires at least one generative_region layer.")

    locked_layers = [layer for layer in layers if layer.get("policy") != "generative_region"]
    product_replacement = manifest.get("productReplacement") or {}
    has_product_slot = bool(product_replacement.get("hasCompetitorProductSlot"))
    product_instruction = (
        "Only replace a competitor product inside approved product_swap slots. "
        "Do not introduce a product packshot, bottle, box, logo, or product mention anywhere else."
        if has_product_slot and render_request.product_replacement_requested
        else "Do not introduce product imagery. The approved manifest has no requested product replacement."
    )

    contract = {
        "canvas": manifest.get("canvas") or {},
        "timeline": manifest.get("timeline") or {},
        "colorRoles": manifest.get("colorRoles") or {},
        "textRoles": manifest.get("textRoles") or {},
        "aiRegionLayers": [
            {
                "id": layer.get("id"),
                "type": layer.get("type"),
                "mask": layer.get("mask"),
                "geometry": layer.get("geometry"),
                "sourceFrameIndexes": layer.get("sourceFrameIndexes") or [],
                "metadata": layer.get("metadata") or {},
            }
            for layer in ai_region_layers
        ],
        "lockedLayerIds": [layer.get("id") for layer in locked_layers],
        "productReplacement": {
            "hasCompetitorProductSlot": has_product_slot,
            "requested": render_request.product_replacement_requested,
        },
        "finalCopy": render_request.final_copy,
        "outputFormats": render_request.output_formats,
    }

    system_prompt = (
        "You generate ONLY the pixels for explicitly masked AI-owned regions in an animated template. "
        "The source template, masks, timing, geometry, text roles, and color roles are authoritative. "
        "Do not redraw, reinterpret, move, resize, recolor, add text to, or remove any locked layer. "
        "Do not add chart points, axis labels, legends, badges, captions, claims, or brand phrases unless "
        "they are present in finalCopy for an editable or AI-owned region. "
        f"{product_instruction} "
        "Return assets aligned to the provided region layer IDs; the deterministic renderer will composite "
        "the final animation."
    )
    user_prompt = (
        "Generate masked animated-region assets using this JSON contract. "
        "Use attached source frame samples and masks as visual references. "
        "Do not modify pixels outside the masks.\n\n"
        f"{json.dumps(contract, ensure_ascii=False, sort_keys=True)}"
    )

    return {
        "schemaVersion": 1,
        "promptKind": "animated_template_ai_region_generation_v1",
        "regionLayerIds": [str(layer.get("id")) for layer in ai_region_layers],
        "modelSelection": render_request.model_selection,
        "system": system_prompt,
        "user": user_prompt,
        "contract": contract,
    }
