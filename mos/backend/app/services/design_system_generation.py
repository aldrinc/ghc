from __future__ import annotations

import colorsys
import json
import re
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
            "- Set dataTheme to 'light' (do NOT use 'dark'). Our funnel templates are designed for light backgrounds and do not support dark mode yet.",
            "- cssVars MUST include ALL keys in requiredCssVars (exact spelling).",
            "- cssVars values MUST be strings or numbers. Use CSS units where needed (e.g. '16px').",
            "- Do NOT leave placeholder values like 'Acme' except where explicitly allowed.",
            "- brand.logoAssetPublicId MUST be a non-empty string placeholder '__LOGO_ASSET_PUBLIC_ID__' (it will be replaced later).",
            "- Pick fonts that match the brand; use Google Fonts URLs in fontUrls.",
            "- Create a distinctive, cohesive theme: update typography, base palette, CTA styling, and section backgrounds. Avoid minor tweaks.",
            "- Maintain good contrast for readability and accessibility.",
            "- Use neutral ink colors for body copy: --color-text and --color-muted must NOT be set to var(--color-brand).",
            "- Keep --color-text highly legible on --color-bg and --color-muted clearly readable on --color-bg.",
            "- Keep primary page/surface backgrounds light. Do NOT use dark/near-black values for these tokens: "
            "--color-page-bg, --color-bg, --hero-bg, --badge-strip-bg, --pitch-bg, "
            "--reviews-card-bg, --wall-card-bg, --pdp-surface-soft, --pdp-surface-muted, --pdp-swatch-bg.",
            "- Dark accent bars/sections are allowed only when their paired text tokens stay accessible.",
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
    if data_theme.strip().lower() == "dark":
        raise DesignSystemGenerationError(
            "Design system tokens.dataTheme must not be 'dark'. This funnel template set currently requires light backgrounds."
        )

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

    _validate_light_background_tokens(css_vars)
    _validate_text_tokens(css_vars)
    _validate_required_contrast_pairs(css_vars)

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


_VAR_FUNCTION_RE = re.compile(r"^var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*(.+?)\s*)?\)$")
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FUNC_COLOR_RE = re.compile(r"(?:rgba?|hsla?)\([^)]+\)")

_LIGHT_BACKGROUND_TOKEN_KEYS = (
    "--color-page-bg",
    "--color-bg",
    "--hero-bg",
    "--badge-strip-bg",
    "--pitch-bg",
    "--reviews-card-bg",
    "--wall-card-bg",
    "--pdp-surface-soft",
    "--pdp-surface-muted",
    "--pdp-swatch-bg",
)

# "Light" but still flexible enough to allow pastel brand backgrounds.
_MIN_BACKGROUND_RELATIVE_LUMINANCE = 0.65

_TEXT_TOKEN_RULES = (
    ("--color-text", 7.0),
    ("--color-muted", 4.5),
)

_TEXT_TOKENS_MUST_DIFFER_FROM = "--color-brand"

_REQUIRED_CONTRAST_PAIRS = (
    ("--color-text", "--color-bg", 7.0),
    ("--color-muted", "--color-bg", 4.5),
    ("--color-brand", "--color-bg", 4.5),
    ("--pdp-brand-strong", "--color-bg", 4.5),
    ("--marquee-text", "--marquee-bg", 4.5),
    ("--color-cta-text", "--color-cta", 3.0),
)


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


def _validate_text_tokens(css_vars: dict[str, Any]) -> None:
    bg_raw = css_vars.get("--color-bg")
    if not isinstance(bg_raw, (str, int, float)):
        raise DesignSystemGenerationError(
            "Design system cssVars[--color-bg] must be a string or number to validate text contrast."
        )
    bg_resolved = _resolve_css_var_value(css_vars=css_vars, value=str(bg_raw), stack=["--color-bg"])
    bg_rgba = _parse_css_color(bg_resolved)
    bg_rgb = _blend_over_background(fg=bg_rgba, bg=(255, 255, 255, 1.0))

    brand_raw = css_vars.get(_TEXT_TOKENS_MUST_DIFFER_FROM)
    if not isinstance(brand_raw, (str, int, float)):
        raise DesignSystemGenerationError(
            f"Design system cssVars[{_TEXT_TOKENS_MUST_DIFFER_FROM}] must be a string or number to validate text tokens."
        )
    brand_resolved = _resolve_css_var_value(
        css_vars=css_vars, value=str(brand_raw), stack=[_TEXT_TOKENS_MUST_DIFFER_FROM]
    )
    brand_rgb = _blend_over_background(fg=_parse_css_color(brand_resolved), bg=bg_rgba)

    for key, min_ratio in _TEXT_TOKEN_RULES:
        raw_value = css_vars.get(key)
        if raw_value is None:
            continue
        if not isinstance(raw_value, (str, int, float)):
            raise DesignSystemGenerationError(
                f"Design system cssVars[{key}] must be a string or number. Received: {type(raw_value).__name__}."
            )
        resolved_value = _resolve_css_var_value(css_vars=css_vars, value=str(raw_value), stack=[key])
        rendered_rgb = _blend_over_background(fg=_parse_css_color(resolved_value), bg=bg_rgba)
        ratio = _contrast_ratio(a=rendered_rgb, b=bg_rgb)
        if ratio < min_ratio:
            raise DesignSystemGenerationError(
                f"Design system cssVars[{key}] resolved to '{resolved_value}' with contrast ratio {ratio:.2f} "
                f"against --color-bg; expected >= {min_ratio:.2f}."
            )
        if rendered_rgb == brand_rgb:
            raise DesignSystemGenerationError(
                f"Design system cssVars[{key}] must not resolve to the same rendered color as "
                f"{_TEXT_TOKENS_MUST_DIFFER_FROM}. Use a neutral ink color for body copy."
            )


def _validate_required_contrast_pairs(css_vars: dict[str, Any]) -> None:
    for fg_key, bg_key, min_ratio in _REQUIRED_CONTRAST_PAIRS:
        fg_raw = css_vars.get(fg_key)
        bg_raw = css_vars.get(bg_key)
        if fg_raw is None or bg_raw is None:
            raise DesignSystemGenerationError(
                f"Design system cssVars missing required contrast pair tokens: {fg_key} and/or {bg_key}."
            )
        if not isinstance(fg_raw, (str, int, float)):
            raise DesignSystemGenerationError(
                f"Design system cssVars[{fg_key}] must be a string or number for contrast validation."
            )
        if not isinstance(bg_raw, (str, int, float)):
            raise DesignSystemGenerationError(
                f"Design system cssVars[{bg_key}] must be a string or number for contrast validation."
            )

        fg_resolved = _resolve_css_var_value(css_vars=css_vars, value=str(fg_raw), stack=[fg_key])
        bg_resolved = _resolve_css_var_value(css_vars=css_vars, value=str(bg_raw), stack=[bg_key])
        fg_rgba = _parse_css_color(fg_resolved)
        bg_rgba = _parse_css_color(bg_resolved)
        bg_rgb = _blend_over_background(fg=bg_rgba, bg=(255, 255, 255, 1.0))
        fg_rgb = _blend_over_background(fg=fg_rgba, bg=bg_rgba)
        ratio = _contrast_ratio(a=fg_rgb, b=bg_rgb)
        if ratio < min_ratio:
            raise DesignSystemGenerationError(
                f"Design system contrast check failed for {fg_key} on {bg_key}: "
                f"resolved '{fg_resolved}' on '{bg_resolved}' with ratio {ratio:.2f}; "
                f"expected >= {min_ratio:.2f}."
            )


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


def _extract_gradient_color_tokens(value: str) -> list[str]:
    lowered = value.strip().lower()
    if "gradient(" not in lowered:
        return []

    found: list[str] = []
    found.extend(match.group(0) for match in _FUNC_COLOR_RE.finditer(value))
    found.extend(match.group(0) for match in _HEX_COLOR_RE.finditer(value))

    for keyword in ("transparent", "white", "black"):
        if re.search(rf"\b{keyword}\b", lowered):
            found.append(keyword)

    deduped: list[str] = []
    seen: set[str] = set()
    for token in found:
        key = token.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token.strip())
    return deduped


def _relative_luminance_srgb(r: int, g: int, b: int) -> float:
    def to_linear(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r_lin = to_linear(r)
    g_lin = to_linear(g)
    b_lin = to_linear(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def _validate_light_background_tokens(css_vars: dict[str, Any]) -> None:
    # These tokens define the base "canvas" and major surface fills across our funnel templates.
    # A dark value here will make pages unreadable because the component styles assume light mode.
    for key in _LIGHT_BACKGROUND_TOKEN_KEYS:
        raw_value = css_vars.get(key)
        if raw_value is None:
            # If it wasn't generated, it's already handled by required cssVars validation elsewhere.
            continue
        if not isinstance(raw_value, (str, int, float)):
            raise DesignSystemGenerationError(
                f"Design system cssVars[{key}] must be a string or number. Received: {type(raw_value).__name__}."
            )

        resolved_value = _resolve_css_var_value(css_vars=css_vars, value=str(raw_value), stack=[key])
        candidate_colors = _extract_gradient_color_tokens(resolved_value)
        color_samples = candidate_colors if candidate_colors else [resolved_value]
        min_lum = 1.0
        min_sample = ""
        for sample in color_samples:
            r, g, b, a = _parse_css_color(sample)

            # Treat semi-transparent backgrounds as if they are rendered over white.
            r_blend = int(round(a * r + (1.0 - a) * 255))
            g_blend = int(round(a * g + (1.0 - a) * 255))
            b_blend = int(round(a * b + (1.0 - a) * 255))
            lum = _relative_luminance_srgb(r_blend, g_blend, b_blend)
            if lum < min_lum:
                min_lum = lum
                min_sample = sample

        if min_lum < _MIN_BACKGROUND_RELATIVE_LUMINANCE:
            raise DesignSystemGenerationError(
                "Design system generated a dark background token that will break light-mode templates. "
                f"cssVars[{key}] resolved to '{resolved_value}' (min sampled color '{min_sample}' "
                f"relative luminance {min_lum:.3f}); expected >= {_MIN_BACKGROUND_RELATIVE_LUMINANCE:.2f}."
            )


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

    tokens = validate_design_system_tokens(tokens)
    return tokens
