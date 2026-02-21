from __future__ import annotations

import colorsys
import json
import re
from dataclasses import dataclass
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

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


def _build_full_prompt(
    *,
    ctx: DesignSystemGenerationContext,
    required_css_vars: list[str],
) -> str:
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
            "",
            f"Brand/product context JSON:\n{context_json}",
            "",
            f"requiredCssVars (must include all):\n{required_css_vars_json}",
        ]
    )


_MAX_TEMPLATE_PATCH_CSS_VAR_OVERRIDES = 40


def _theme_lever_css_vars_snapshot(template_css_vars: dict[str, Any]) -> dict[str, Any]:
    """
    Small subset of template tokens the model can use as an anchor when producing a patch.
    This keeps prompts smaller while still providing the "what are we starting from" context.
    """

    lever_keys = [
        # Core palette/surfaces
        "--color-brand",
        "--color-text",
        "--color-muted",
        "--color-border",
        "--color-soft",
        "--color-page-bg",
        "--color-bg",
        # Conversion accents
        "--color-cta",
        "--color-cta-text",
        "--color-cta-icon",
        "--pdp-cta-bg",
        "--pdp-check-bg",
        # Accent bars/strips
        "--marquee-bg",
        "--marquee-text",
        "--badge-strip-bg",
        "--badge-text-color",
        "--badge-strip-border",
        # Main section surfaces
        "--hero-bg",
        "--pitch-bg",
    ]
    return {key: template_css_vars.get(key) for key in lever_keys if key in template_css_vars}


def _build_template_patch_prompt(
    *,
    ctx: DesignSystemGenerationContext,
    template_tokens: dict[str, Any],
    template_css_var_keys: list[str],
) -> str:
    template_css_vars = template_tokens.get("cssVars")
    if not isinstance(template_css_vars, dict) or not template_css_vars:
        raise DesignSystemGenerationError("Design system base template must include a non-empty cssVars object.")

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

    template_keys_json = json.dumps(template_css_var_keys, ensure_ascii=True)
    base_levers_json = json.dumps(_theme_lever_css_vars_snapshot(template_css_vars), ensure_ascii=True)
    context_json = json.dumps(context_obj, ensure_ascii=True)

    return "\n".join(
        [
            "You are updating our design system by PATCHING a base template (small deltas), not redesigning from scratch.",
            "Output ONLY valid JSON.",
            "",
            "Output schema (JSON):",
            "{ fontUrls?: string[], fontCss?: string, cssVars: [{ key: string, value: string|number }, ...] }",
            "",
            "Hard requirements:",
            "- Return ONLY overrides in cssVars. Do NOT output every template token.",
            "- Each cssVars[].key MUST be one of templateCssVarKeys (exact spelling).",
            f"- Keep overrides small: ideally 6-16 keys, hard limit {_MAX_TEMPLATE_PATCH_CSS_VAR_OVERRIDES} keys.",
            "- Values MUST be strings or numbers. Use CSS units where needed (e.g. '16px').",
            "",
            "Guidance (choose what to change based on brand context):",
            "- Start by considering these groups, but only override what you need:",
            "  - CTA: --color-cta, --color-cta-icon (and only if needed: --pdp-cta-bg, --pdp-check-bg, --color-cta-text)",
            "  - Marquee: --marquee-bg, --marquee-text",
            "  - Badges: --badge-strip-bg, --badge-text-color, --badge-strip-border",
            "  - Section backgrounds: --hero-bg, --pitch-bg (optional: --color-page-bg)",
            "- Beauty/skincare/cosmetics brands: avoid 'utility green' CTAs; prefer blush/mauve/berry accents and warm champagne bars.",
            "",
            f"Brand/product context JSON:\n{context_json}",
            "",
            f"Base theme lever snapshot (current values):\n{base_levers_json}",
            "",
            f"templateCssVarKeys (allowed keys):\n{template_keys_json}",
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


def _patch_response_schema() -> dict[str, Any]:
    # Patch schema: small set of overrides, represented as an array of {key,value} objects.
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "fontUrls": {"type": "array", "items": {"type": "string"}},
            "fontCss": {"type": "string"},
            "cssVars": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"oneOf": [{"type": "string"}, {"type": "number"}]},
                    },
                    "required": ["key", "value"],
                },
            },
        },
        "required": ["cssVars"],
    }


def _claude_patch_response_schema() -> dict[str, Any]:
    # Keep this aligned with _patch_response_schema(), but use value: string to match Anthropic constraints.
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
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
        },
        "required": ["cssVars"],
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
    if not isinstance(logo_public_id, str) or not logo_public_id.strip():
        raise DesignSystemGenerationError(
            "Design system tokens.brand.logoAssetPublicId must be a non-empty string."
        )

    return tokens


_VAR_FUNCTION_RE = re.compile(r"^var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*(.+?)\s*)?\)$")


def _resolve_css_var_value(*, css_vars: dict[str, Any], value: str, stack: list[str]) -> str:
    raw = value.strip()
    match = _VAR_FUNCTION_RE.match(raw)
    if not match:
        return raw

    ref_key = match.group(1)
    fallback = match.group(2)
    if ref_key in stack:
        path = " -> ".join([*stack, ref_key])
        raise DesignSystemGenerationError(f"Design system cssVars contain a circular var() reference: {path}.")

    ref_val = css_vars.get(ref_key)
    if ref_val is None:
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        raise DesignSystemGenerationError(
            f"Design system cssVars reference missing key {ref_key} via var(), and no fallback value was provided."
        )
    if not isinstance(ref_val, (str, int, float)):
        raise DesignSystemGenerationError(
            f"Design system cssVars[{ref_key}] must be a string or number to be used via var(). Received: {type(ref_val).__name__}."
        )
    return _resolve_css_var_value(css_vars=css_vars, value=str(ref_val), stack=[*stack, ref_key])


def _blend_over_background(*, fg: tuple[int, int, int, float], bg: tuple[int, int, int, float]) -> tuple[int, int, int]:
    fg_r, fg_g, fg_b, fg_a = fg
    bg_r, bg_g, bg_b, bg_a = bg

    # Text colors are evaluated as rendered over the page background.
    # If background alpha is present, resolve it as if composited over white.
    bg_r_blend = int(round(bg_a * bg_r + (1.0 - bg_a) * 255))
    bg_g_blend = int(round(bg_a * bg_g + (1.0 - bg_a) * 255))
    bg_b_blend = int(round(bg_a * bg_b + (1.0 - bg_a) * 255))

    out_r = int(round(fg_a * fg_r + (1.0 - fg_a) * bg_r_blend))
    out_g = int(round(fg_a * fg_g + (1.0 - fg_a) * bg_g_blend))
    out_b = int(round(fg_a * fg_b + (1.0 - fg_a) * bg_b_blend))
    return out_r, out_g, out_b


def _contrast_ratio(*, a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la = _relative_luminance_srgb(*a)
    lb = _relative_luminance_srgb(*b)
    lighter, darker = (la, lb) if la >= lb else (lb, la)
    return (lighter + 0.05) / (darker + 0.05)


def validate_design_system_tokens(tokens: Any) -> dict[str, Any]:
    """
    Shared strict validator for generated and persisted design system tokens.
    """
    return _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def _parse_hex_channel(hex_part: str) -> int:
    return int(hex_part, 16)


def _parse_css_color(value: str) -> tuple[int, int, int, float]:
    raw = value.strip()
    if not raw:
        raise DesignSystemGenerationError("Cannot parse empty color string.")

    lowered = raw.lower()
    if lowered == "transparent":
        return 0, 0, 0, 0.0
    if lowered == "white":
        return 255, 255, 255, 1.0
    if lowered == "black":
        return 0, 0, 0, 1.0

    if lowered.startswith("#"):
        hex_body = lowered[1:]
        if len(hex_body) in (3, 4):
            r = _parse_hex_channel(hex_body[0] * 2)
            g = _parse_hex_channel(hex_body[1] * 2)
            b = _parse_hex_channel(hex_body[2] * 2)
            a = _parse_hex_channel(hex_body[3] * 2) / 255.0 if len(hex_body) == 4 else 1.0
            return r, g, b, a
        if len(hex_body) in (6, 8):
            r = _parse_hex_channel(hex_body[0:2])
            g = _parse_hex_channel(hex_body[2:4])
            b = _parse_hex_channel(hex_body[4:6])
            a = _parse_hex_channel(hex_body[6:8]) / 255.0 if len(hex_body) == 8 else 1.0
            return r, g, b, a
        raise DesignSystemGenerationError(f"Unsupported hex color format: {raw}.")

    func_match = re.match(r"^(rgba?|hsla?)\((.*)\)$", lowered)
    if not func_match:
        raise DesignSystemGenerationError(f"Unsupported CSS color format: {raw}.")

    func = func_match.group(1)
    inner = func_match.group(2).strip()

    alpha: float = 1.0
    if "/" in inner:
        before, after = inner.split("/", 1)
        inner = before.strip()
        alpha_raw = after.strip()
        if alpha_raw.endswith("%"):
            alpha = float(alpha_raw[:-1].strip()) / 100.0
        else:
            alpha = float(alpha_raw)

    parts = inner.replace(",", " ").split()
    if func in ("rgb", "rgba"):
        if len(parts) == 4 and "/" not in func_match.group(2):
            # legacy rgba(r,g,b,a) form without '/' split above
            alpha_raw = parts[3].strip()
            if alpha_raw.endswith("%"):
                alpha = float(alpha_raw[:-1].strip()) / 100.0
            else:
                alpha = float(alpha_raw)
            parts = parts[:3]
        if len(parts) != 3:
            raise DesignSystemGenerationError(f"Invalid {func}() color: {raw}.")

        def parse_rgb_channel(p: str) -> float:
            p = p.strip()
            if p.endswith("%"):
                return float(p[:-1].strip()) * 255.0 / 100.0
            return float(p)

        r_f, g_f, b_f = (parse_rgb_channel(p) for p in parts)
        r = max(0, min(255, int(round(r_f))))
        g = max(0, min(255, int(round(g_f))))
        b = max(0, min(255, int(round(b_f))))
        alpha = max(0.0, min(1.0, float(alpha)))
        return r, g, b, alpha

    # HSL
    if len(parts) == 4 and "/" not in func_match.group(2):
        alpha_raw = parts[3].strip()
        if alpha_raw.endswith("%"):
            alpha = float(alpha_raw[:-1].strip()) / 100.0
        else:
            alpha = float(alpha_raw)
        parts = parts[:3]
    if len(parts) != 3:
        raise DesignSystemGenerationError(f"Invalid {func}() color: {raw}.")

    h_raw, s_raw, l_raw = (p.strip() for p in parts)
    if h_raw.endswith("deg"):
        h = float(h_raw[:-3].strip())
    else:
        h = float(h_raw)
    if not s_raw.endswith("%") or not l_raw.endswith("%"):
        raise DesignSystemGenerationError(f"Invalid {func}() color (expected percent s/l): {raw}.")
    s = float(s_raw[:-1].strip()) / 100.0
    l = float(l_raw[:-1].strip()) / 100.0
    alpha = max(0.0, min(1.0, float(alpha)))

    # colorsys uses HLS (h, l, s), where h is 0..1
    r_f, g_f, b_f = colorsys.hls_to_rgb((h % 360.0) / 360.0, l, s)
    return int(round(r_f * 255)), int(round(g_f * 255)), int(round(b_f * 255)), alpha


def _relative_luminance_srgb(r: int, g: int, b: int) -> float:
    def to_linear(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r_lin = to_linear(r)
    g_lin = to_linear(g)
    b_lin = to_linear(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def generate_design_system_tokens(
    *,
    ctx: DesignSystemGenerationContext,
    model: str | None = None,
    max_output_tokens: int = 9000,
    mode: str = "template_patch",
) -> dict[str, Any]:
    mode_clean = (mode or "").strip().lower()
    if mode_clean in ("template_patch", "patch", "delta", "template"):
        template_tokens = load_base_tokens_template()
        template_css_var_keys = _required_css_var_keys()
        prompt = _build_template_patch_prompt(
            ctx=ctx,
            template_tokens=template_tokens,
            template_css_var_keys=template_css_var_keys,
        )
        response_schema = _patch_response_schema()
        claude_schema = _claude_patch_response_schema()
        apply_patch_to_template = True
    elif mode_clean in ("full", "from_scratch", "scratch"):
        required_css_vars = _required_css_var_keys()
        prompt = _build_full_prompt(
            ctx=ctx,
            required_css_vars=required_css_vars,
        )
        response_schema = _response_schema()
        claude_schema = _claude_response_schema()
        apply_patch_to_template = False
    else:
        raise DesignSystemGenerationError(
            f"Unsupported design system generation mode: {mode!r}. Expected 'template_patch' or 'full'."
        )

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
                output_schema=claude_schema,
                max_tokens=max_output_tokens,
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            raise DesignSystemGenerationError(f"Claude structured design system generation failed: {exc}") from exc
        tokens = response.get("parsed")
        if not isinstance(tokens, dict):
            raise DesignSystemGenerationError("Claude structured design system generation returned non-object tokens.")
        if not apply_patch_to_template:
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
                    "schema": response_schema,
                },
            },
        )
        raw = llm.generate_text(prompt, params=params)
        try:
            tokens = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DesignSystemGenerationError(f"Design system generation returned invalid JSON: {exc}") from exc

    if apply_patch_to_template:
        template_tokens = load_base_tokens_template()
        if not isinstance(tokens, dict):
            raise DesignSystemGenerationError("Design system patch generation returned non-object output.")

        patch_font_urls = tokens.get("fontUrls")
        patch_font_css = tokens.get("fontCss")
        patch_css_vars = _coerce_css_vars_pairs(tokens.get("cssVars"))

        if not patch_css_vars:
            raise DesignSystemGenerationError("Design system patch must include at least one cssVars override.")
        if len(patch_css_vars) > _MAX_TEMPLATE_PATCH_CSS_VAR_OVERRIDES:
            raise DesignSystemGenerationError(
                "Design system patch includes too many cssVars overrides. "
                f"Received {len(patch_css_vars)}; expected <= {_MAX_TEMPLATE_PATCH_CSS_VAR_OVERRIDES}."
            )

        template_css_vars = template_tokens.get("cssVars")
        if not isinstance(template_css_vars, dict) or not template_css_vars:
            raise DesignSystemGenerationError("Design system base template must include a non-empty cssVars object.")

        unknown = sorted(key for key in patch_css_vars.keys() if key not in template_css_vars)
        if unknown:
            preview = ", ".join(unknown[:25])
            suffix = "" if len(unknown) <= 25 else f" (+{len(unknown) - 25} more)"
            raise DesignSystemGenerationError(
                "Design system patch contains cssVars keys that do not exist in the base template. "
                f"Unknown keys: {preview}{suffix}."
            )

        out = deepcopy(template_tokens)
        out["dataTheme"] = "light"

        if patch_font_urls is not None:
            if not isinstance(patch_font_urls, list) or not all(
                isinstance(u, str) and u.strip() for u in patch_font_urls
            ):
                raise DesignSystemGenerationError("Design system patch fontUrls must be a list of non-empty strings.")
            out["fontUrls"] = [u.strip() for u in patch_font_urls]

        if patch_font_css is not None:
            if not isinstance(patch_font_css, str) or not patch_font_css.strip():
                raise DesignSystemGenerationError(
                    "Design system patch fontCss must be a non-empty string when provided (or omit it)."
                )
            out["fontCss"] = patch_font_css

        out_css_vars = out.get("cssVars")
        if not isinstance(out_css_vars, dict):
            raise DesignSystemGenerationError("Design system base template cssVars must be a JSON object.")
        for key, value in patch_css_vars.items():
            out_css_vars[key] = value

        brand = out.get("brand")
        if not isinstance(brand, dict):
            raise DesignSystemGenerationError("Design system base template must include a brand object.")
        brand["name"] = ctx.client_name

        return validate_design_system_tokens(out)

    tokens = validate_design_system_tokens(tokens)
    return tokens
