from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.llm.client import LLMClient, LLMGenerationParams
from app.services.claude_files import call_claude_structured_message


class DesignSystemGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DesignSystemGenerationContext:
    org_id: str
    client_id: str
    product_id: str
    client_name: str
    client_industry: str | None
    brand_story: str
    product_name: str
    product_description: str | None
    product_category: str | None
    primary_benefits: list[str]
    feature_bullets: list[str]
    guarantee_text: str | None
    disclaimers: list[str]
    goals: list[str]
    funnel_notes: str | None
    competitor_urls: list[str]
    precanon_step_summaries: dict[str, str]


def _design_system_templates_dir() -> Path:
    # backend/app/services -> backend/app/templates/design_systems
    return Path(__file__).resolve().parents[1] / "templates" / "design_systems"


@lru_cache(maxsize=1)
def load_base_tokens_template() -> dict[str, Any]:
    path = _design_system_templates_dir() / "base_tokens.json"
    if not path.exists():
        raise DesignSystemGenerationError(
            f"Missing design system base template at {path}. Expected a JSON file with top-level keys "
            "{dataTheme,fontUrls,cssVars,funnelDefaults,brand}."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DesignSystemGenerationError(f"Design system base template is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DesignSystemGenerationError("Design system base template must decode to a JSON object.")
    css_vars = data.get("cssVars")
    if not isinstance(css_vars, dict) or not css_vars:
        raise DesignSystemGenerationError("Design system base template must include a non-empty cssVars object.")
    return data


def _required_css_var_keys() -> list[str]:
    template = load_base_tokens_template()
    css_vars = template.get("cssVars")
    if not isinstance(css_vars, dict):
        raise DesignSystemGenerationError("Design system base template cssVars must be a JSON object.")
    return sorted(str(k) for k in css_vars.keys())


def _build_prompt(*, ctx: DesignSystemGenerationContext, required_css_vars: list[str]) -> str:
    # Keep the prompt explicit: we want a full theme, not a small delta.
    # We provide key list and context; the model must output the full JSON.
    context_obj: dict[str, Any] = {
        "brand": {
            "name": ctx.client_name,
            "industry": ctx.client_industry,
            "story": ctx.brand_story,
        },
        "product": {
            "id": ctx.product_id,
            "name": ctx.product_name,
            "description": ctx.product_description,
            "category": ctx.product_category,
            "primary_benefits": ctx.primary_benefits,
            "feature_bullets": ctx.feature_bullets,
            "guarantee_text": ctx.guarantee_text,
            "disclaimers": ctx.disclaimers,
        },
        "business": {
            "goals": ctx.goals,
            "funnel_notes": ctx.funnel_notes,
            "competitor_urls": ctx.competitor_urls,
        },
        "research": {
            "precanon_step_summaries": ctx.precanon_step_summaries,
        },
    }

    # Provide the exact css var keys that must exist, but do not provide the old values.
    # This nudges the model to create a cohesive theme from scratch.
    required_css_vars_json = json.dumps(required_css_vars, ensure_ascii=True)
    context_json = json.dumps(context_obj, ensure_ascii=True)
    return "\n".join(
        [
            "Generate a full custom design system tokens JSON for a brand. Output ONLY valid JSON.",
            "",
            "Hard requirements:",
            "- Output must match this schema exactly: { dataTheme, fontUrls, fontCss?, cssVars, funnelDefaults, brand }.",
            "- cssVars MUST include ALL keys in requiredCssVars (exact spelling).",
            "- cssVars values MUST be strings or numbers. Use CSS units where needed (e.g. '16px').",
            "- Do NOT leave placeholder values like 'Acme' except where explicitly allowed.",
            "- brand.logoAssetPublicId MUST be a non-empty string placeholder '__LOGO_ASSET_PUBLIC_ID__' (it will be replaced later).",
            "- Pick fonts that match the brand; use Google Fonts URLs in fontUrls.",
            "- Create a distinctive, cohesive theme: update typography, base palette, CTA styling, and section backgrounds. Avoid minor tweaks.",
            "- Maintain good contrast for readability and accessibility.",
            "",
            f"Brand/product context JSON:\n{context_json}",
            "",
            f"requiredCssVars (must include all):\n{required_css_vars_json}",
        ]
    )


def _response_schema() -> dict[str, Any]:
    # Minimal schema: we validate semantic constraints in Python (required css var keys, etc.).
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "dataTheme": {"type": "string"},
            "fontUrls": {"type": "array", "items": {"type": "string"}},
            "fontCss": {"type": "string"},
            "cssVars": {
                "type": "object",
                "additionalProperties": {"oneOf": [{"type": "string"}, {"type": "number"}]},
            },
            "funnelDefaults": {"type": "object", "additionalProperties": True},
            "brand": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string"},
                    "logoAssetPublicId": {"type": "string"},
                    "logoAlt": {"type": "string"},
                },
                "required": ["name", "logoAssetPublicId"],
            },
        },
        "required": ["dataTheme", "fontUrls", "cssVars", "funnelDefaults", "brand"],
    }


def _claude_response_schema() -> dict[str, Any]:
    """
    Claude structured outputs do not support additionalProperties=true. To keep the generation strict
    while allowing \"dynamic\" css var keys, represent cssVars as an array of {key,value} pairs and
    convert to a dict after parsing.
    """

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dataTheme": {"type": "string"},
            "fontUrls": {"type": "array", "items": {"type": "string"}},
            "fontCss": {"type": "string"},
            "cssVars": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            },
            "funnelDefaults": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "containerWidth": {"type": "string"},
                    "sectionPadding": {"type": "string"},
                },
                "required": ["containerWidth", "sectionPadding"],
            },
            "brand": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "logoAssetPublicId": {"type": "string"},
                    "logoAlt": {"type": "string"},
                },
                "required": ["name", "logoAssetPublicId"],
            },
        },
        "required": ["dataTheme", "fontUrls", "cssVars", "funnelDefaults", "brand"],
    }


def _coerce_css_vars_pairs(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, list):
        raise DesignSystemGenerationError("Design system tokens.cssVars must be an array of {key,value} objects.")
    out: dict[str, Any] = {}
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DesignSystemGenerationError(f"Design system tokens.cssVars[{idx}] must be an object.")
        key = item.get("key")
        value = item.get("value")
        if not isinstance(key, str) or not key.strip():
            raise DesignSystemGenerationError(f"Design system tokens.cssVars[{idx}].key must be a non-empty string.")
        if value is None:
            raise DesignSystemGenerationError(f"Design system tokens.cssVars[{idx}].value must not be null.")
        if not isinstance(value, (str, int, float)):
            raise DesignSystemGenerationError(
                f"Design system tokens.cssVars[{idx}].value must be a string or number. Received: {type(value).__name__}."
            )
        if isinstance(value, str) and not value.strip():
            raise DesignSystemGenerationError(f"Design system tokens.cssVars[{idx}].value must not be an empty string.")
        key_clean = key.strip()
        if key_clean in out:
            raise DesignSystemGenerationError(f"Design system tokens.cssVars contains duplicate key: {key_clean}.")
        out[key_clean] = value
    return out


def _validate_tokens(tokens: Any, *, required_css_vars: list[str]) -> dict[str, Any]:
    if not isinstance(tokens, dict):
        raise DesignSystemGenerationError("Design system generation output must be a JSON object.")

    data_theme = tokens.get("dataTheme")
    if not isinstance(data_theme, str) or not data_theme.strip():
        raise DesignSystemGenerationError("Design system tokens.dataTheme must be a non-empty string.")

    font_urls = tokens.get("fontUrls")
    if not isinstance(font_urls, list) or not all(isinstance(u, str) and u.strip() for u in font_urls):
        raise DesignSystemGenerationError("Design system tokens.fontUrls must be a list of non-empty strings.")

    css_vars = tokens.get("cssVars")
    if not isinstance(css_vars, dict):
        raise DesignSystemGenerationError("Design system tokens.cssVars must be a JSON object.")
    missing = [k for k in required_css_vars if k not in css_vars]
    if missing:
        preview = ", ".join(missing[:25])
        suffix = "" if len(missing) <= 25 else f" (+{len(missing) - 25} more)"
        raise DesignSystemGenerationError(f"Design system tokens.cssVars missing required keys: {preview}{suffix}.")
    for key, value in css_vars.items():
        if not isinstance(key, str) or not key.strip():
            raise DesignSystemGenerationError("Design system tokens.cssVars keys must be non-empty strings.")
        if value is None:
            raise DesignSystemGenerationError(f"Design system cssVars[{key}] must not be null.")
        if not isinstance(value, (str, int, float)):
            raise DesignSystemGenerationError(
                f"Design system cssVars[{key}] must be a string or number. Received: {type(value).__name__}."
            )
        if isinstance(value, str) and not value.strip():
            raise DesignSystemGenerationError(f"Design system cssVars[{key}] must not be an empty string.")

    funnel_defaults = tokens.get("funnelDefaults")
    if not isinstance(funnel_defaults, dict):
        raise DesignSystemGenerationError("Design system tokens.funnelDefaults must be a JSON object.")

    brand = tokens.get("brand")
    if not isinstance(brand, dict):
        raise DesignSystemGenerationError("Design system tokens.brand must be a JSON object.")
    brand_name = brand.get("name")
    if not isinstance(brand_name, str) or not brand_name.strip():
        raise DesignSystemGenerationError("Design system tokens.brand.name must be a non-empty string.")
    logo_public_id = brand.get("logoAssetPublicId")
    if not isinstance(logo_public_id, str):
        raise DesignSystemGenerationError("Design system tokens.brand.logoAssetPublicId must be a string.")

    return tokens


def generate_design_system_tokens(
    *,
    ctx: DesignSystemGenerationContext,
    model: str | None = None,
    max_output_tokens: int = 9000,
) -> dict[str, Any]:
    required_css_vars = _required_css_var_keys()
    prompt = _build_prompt(ctx=ctx, required_css_vars=required_css_vars)

    llm = LLMClient()
    model_id = model or llm.default_model

    # Claude is the default model in this codebase. Use Claude structured outputs directly to
    # avoid brittle \"JSON in markdown fences\" parsing and keep behavior strict.
    if model_id.lower().startswith("claude"):
        try:
            response = call_claude_structured_message(
                model=model_id,
                system=None,
                user_content=[{"type": "text", "text": prompt}],
                output_schema=_claude_response_schema(),
                max_tokens=max_output_tokens,
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            raise DesignSystemGenerationError(f"Claude structured design system generation failed: {exc}") from exc
        tokens = response.get("parsed")
        if not isinstance(tokens, dict):
            raise DesignSystemGenerationError("Claude structured design system generation returned non-object tokens.")
        tokens["cssVars"] = _coerce_css_vars_pairs(tokens.get("cssVars"))
    else:
        params = LLMGenerationParams(
            model=model_id,
            max_tokens=max_output_tokens,
            temperature=0.2,
            use_reasoning=True,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "DesignSystemTokens",
                    "strict": True,
                    "schema": _response_schema(),
                },
            },
        )
        raw = llm.generate_text(prompt, params=params)
        try:
            tokens = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DesignSystemGenerationError(f"Design system generation returned invalid JSON: {exc}") from exc

    tokens = _validate_tokens(tokens, required_css_vars=required_css_vars)
    return tokens
