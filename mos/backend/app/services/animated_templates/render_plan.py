from __future__ import annotations

from typing import Any

from app.schemas.animated_templates import AnimatedTemplateRenderRequest
from app.services.animated_templates.manifest_validation import validate_render_request


_RENDER_OWNER_KEYS = (
    "source_pixels",
    "deterministic_renderer",
    "product_compositor",
    "ai_region_model",
)


def _renderer_strategy(layers: list[Any], ai_region_layer_ids: list[str]) -> str:
    if ai_region_layer_ids:
        return "hybrid_composite"
    if layers and all(
        isinstance(layer, dict)
        and layer.get("policy") == "locked_source"
        and layer.get("renderOwner") == "source_pixels"
        for layer in layers
    ):
        return "source_passthrough"
    return "deterministic_composite"


def estimate_render_cost(
    *,
    manifest: dict[str, Any],
    render_request: AnimatedTemplateRenderRequest,
) -> dict[str, Any]:
    layers = manifest.get("layers") or []
    ai_regions = [
        layer for layer in layers if isinstance(layer, dict) and layer.get("policy") == "generative_region"
    ]
    output_formats = list(render_request.output_formats)
    if not ai_regions:
        return {
            "pricingStatus": "not_required",
            "modelCalls": 0,
            "modelCostUsd": "0.00",
            "outputFormats": output_formats,
            "notes": ["No AI-owned regions are present; deterministic rendering requires no model call."],
        }

    model_selection = render_request.model_selection or {}
    return {
        "pricingStatus": "requires_provider_pricing",
        "modelCalls": len(ai_regions),
        "modelCostUsd": None,
        "outputFormats": output_formats,
        "modelSelection": model_selection,
        "notes": [
            "AI-region pricing is not hardcoded. Wire an authorized provider pricing source before "
            "displaying estimated model cost."
        ],
    }


def build_render_plan(
    *,
    manifest: dict[str, Any],
    render_request: AnimatedTemplateRenderRequest,
) -> dict[str, Any]:
    validation = validate_render_request(manifest, render_request)
    if validation.get("blockingErrors"):
        raise RuntimeError("Animated template render plan cannot be built for an invalid render request.")

    layers = manifest.get("layers") or []
    layers_by_owner: dict[str, list[str]] = {owner: [] for owner in _RENDER_OWNER_KEYS}
    product_swap_layer_ids: list[str] = []
    ai_region_layer_ids: list[str] = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_id = str(layer.get("id") or "").strip()
        if not layer_id:
            continue
        render_owner = str(layer.get("renderOwner") or "deterministic_renderer")
        if render_owner not in layers_by_owner:
            layers_by_owner[render_owner] = []
        layers_by_owner[render_owner].append(layer_id)
        if layer.get("policy") == "product_swap":
            product_swap_layer_ids.append(layer_id)
        if layer.get("policy") == "generative_region":
            ai_region_layer_ids.append(layer_id)

    return {
        "schemaVersion": 1,
        "renderMode": render_request.render_mode,
        "outputFormats": list(render_request.output_formats),
        "canvas": manifest.get("canvas") or {},
        "timeline": manifest.get("timeline") or {},
        "layerCount": len(layers),
        "layersByOwner": layers_by_owner,
        "productSwapLayerIds": product_swap_layer_ids,
        "aiRegionLayerIds": ai_region_layer_ids,
        "rendererStrategy": _renderer_strategy(layers, ai_region_layer_ids),
        "requiresAiModel": bool(ai_region_layer_ids),
        "requiresProductReplacement": bool(render_request.product_replacement_requested),
        "modelSelection": render_request.model_selection,
        "costEstimate": estimate_render_cost(
            manifest=manifest,
            render_request=render_request,
        ),
    }
