from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.config import settings
from app.llm_ops import fetch_prompt_text

def load_swipe_to_image_ad_prompt() -> Tuple[str, str]:
    """
    Load the swipe -> image-ad prompt template and compute its SHA256.
    """
    prompt_key = "prompts/swipe/swipe_to_image_ad.md"
    if settings.AGENTA_ENABLED:
        return fetch_prompt_text(prompt_key)

    backend_app_root = Path(__file__).resolve().parents[1]
    prompt_path = backend_app_root / "prompts" / "swipe" / "swipe_to_image_ad.md"
    text = prompt_path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, sha


def _normalize_unknown(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "[UNKNOWN]"


def build_swipe_context_block(
    *,
    brand_name: str,
    product_name: str,
    audience: str | None = None,
    brand_colors_fonts: str | None = None,
    must_avoid_claims: List[str] | None = None,
    assets: Dict[str, str] | None = None,
    creative_concept: str | None = None,
    channel: str | None = None,
    angle: str | None = None,
    hook: str | None = None,
    constraints: List[str] | None = None,
    tone_guidelines: List[str] | None = None,
    visual_guidelines: List[str] | None = None,
) -> str:
    if not isinstance(brand_name, str) or not brand_name.strip():
        raise ValueError("brand_name is required to build swipe context block")
    if not isinstance(product_name, str) or not product_name.strip():
        raise ValueError("product_name is required to build swipe context block")

    lines: List[str] = []
    lines.append("## SWIPE CONTEXT")
    lines.append(f"Brand name: {_normalize_unknown(brand_name)}")
    lines.append(f"Product: {_normalize_unknown(product_name)}")
    lines.append(f"Audience: {_normalize_unknown(audience)}")
    lines.append(f"Brand colors/fonts: {_normalize_unknown(brand_colors_fonts)}")

    claims = [c.strip() for c in (must_avoid_claims or []) if isinstance(c, str) and c.strip()]
    lines.append("Must-avoid claims:")
    if claims:
        for claim in claims:
            lines.append(f"- {claim}")
    else:
        lines.append("- [UNKNOWN]")

    asset_map = assets or {}
    cleaned_assets = {str(k).strip(): str(v).strip() for k, v in asset_map.items() if str(k).strip() and str(v).strip()}
    lines.append("Assets:")
    if cleaned_assets:
        for key in sorted(cleaned_assets.keys()):
            lines.append(f"- {key}: {cleaned_assets[key]}")
    else:
        lines.append("- [UNKNOWN]")

    lines.append("")
    lines.append("## CREATIVE BRIEF CONTEXT")
    lines.append(f"Creative concept: {_normalize_unknown(creative_concept)}")
    lines.append(f"Channel: {_normalize_unknown(channel)}")
    lines.append("Format: image.")
    lines.append(f"Angle: {_normalize_unknown(angle)}")
    lines.append(f"Hook: {_normalize_unknown(hook)}")

    cleaned_constraints = [item.strip() for item in (constraints or []) if isinstance(item, str) and item.strip()]
    lines.append("Constraints:")
    if cleaned_constraints:
        for item in cleaned_constraints:
            lines.append(f"- {item}")
    else:
        lines.append("- [UNKNOWN]")

    cleaned_tone_guidelines = [
        item.strip() for item in (tone_guidelines or []) if isinstance(item, str) and item.strip()
    ]
    lines.append("Tone guidelines:")
    if cleaned_tone_guidelines:
        for item in cleaned_tone_guidelines:
            lines.append(f"- {item}")
    else:
        lines.append("- [UNKNOWN]")

    cleaned_visual_guidelines = [
        item.strip() for item in (visual_guidelines or []) if isinstance(item, str) and item.strip()
    ]
    lines.append("Visual guidelines:")
    if cleaned_visual_guidelines:
        for item in cleaned_visual_guidelines:
            lines.append(f"- {item}")
    else:
        lines.append("- [UNKNOWN]")

    lines.append(
        "If a required detail is missing or unclear, output [UNKNOWN] or [UNREADABLE] rather than guessing."
    )
    return "\n".join(lines).strip()


_CODE_FENCE_RE = re.compile(
    r"```(?P<lang>[^\n`]*)\n(?P<code>.*?)(?:\n)?```",
    re.DOTALL,
)
_ALLOWED_PROMPT_FENCE_LANGS = {"text", "markdown", ""}
_RENDER_PLACEHOLDER_TOKEN_RE = re.compile(r"\[([A-Z0-9_]{2,})\]")
_PLACEHOLDER_HEADING_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*placeholders?(?:\s+key)?\s*:?\s*(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_PLACEHOLDER_MAPPING_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?\[(?P<key>[A-Z0-9_]{2,})\](?:\*\*)?\s*(?:[:=]\s*|\-\s*)(?P<value>.+?)\s*$"
)
_PLACEHOLDER_SECTION_MAPPING_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?\[(?P<key>[A-Z0-9_]{2,})\](?:\*\*)?\s+(?P<value>.+?)\s*$"
)


class SwipePromptParseError(RuntimeError):
    pass


def _register_placeholder_mapping(
    mappings: Dict[str, str],
    *,
    key: str,
    value: str,
) -> None:
    normalized_key = key.strip().upper()
    normalized_value = value.strip()
    if not normalized_key or not normalized_value:
        raise SwipePromptParseError(
            f"Invalid placeholder mapping encountered for key [{key}]."
        )
    existing = mappings.get(normalized_key)
    if existing is not None and existing != normalized_value:
        raise SwipePromptParseError(
            "Conflicting placeholder mappings detected for "
            f"[{normalized_key}]: {existing!r} vs {normalized_value!r}."
        )
    mappings[normalized_key] = normalized_value


def inline_swipe_render_placeholders(prompt: str) -> tuple[str, Dict[str, str]]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise SwipePromptParseError("Render prompt is empty; cannot inline placeholder values.")

    lines = prompt.splitlines()
    mapping_lines: set[int] = set()
    placeholder_mappings: Dict[str, str] = {}
    in_placeholder_section = False

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if _PLACEHOLDER_HEADING_RE.match(stripped):
            mapping_lines.add(idx)
            in_placeholder_section = True
            continue

        explicit_mapping = _PLACEHOLDER_MAPPING_RE.match(line)
        if explicit_mapping:
            _register_placeholder_mapping(
                placeholder_mappings,
                key=explicit_mapping.group("key"),
                value=explicit_mapping.group("value"),
            )
            mapping_lines.add(idx)
            continue

        if not in_placeholder_section:
            continue

        if not stripped:
            mapping_lines.add(idx)
            continue

        section_mapping = _PLACEHOLDER_SECTION_MAPPING_RE.match(line)
        if section_mapping:
            _register_placeholder_mapping(
                placeholder_mappings,
                key=section_mapping.group("key"),
                value=section_mapping.group("value"),
            )
            mapping_lines.add(idx)
            continue

        in_placeholder_section = False

    inlined = "\n".join(line for idx, line in enumerate(lines) if idx not in mapping_lines).strip()

    for key, value in placeholder_mappings.items():
        inlined = re.sub(rf"\[{re.escape(key)}\]", value, inlined)

    unresolved_tokens = sorted({match.group(0) for match in _RENDER_PLACEHOLDER_TOKEN_RE.finditer(inlined)})
    if unresolved_tokens:
        raise SwipePromptParseError(
            "Render prompt contains unresolved bracket placeholders after inlining: "
            f"{', '.join(unresolved_tokens)}."
        )

    return inlined, placeholder_mappings


def extract_new_image_prompt_from_markdown(markdown: str) -> str:
    if not isinstance(markdown, str) or not markdown.strip():
        raise SwipePromptParseError(
            "Swipe prompt output is empty; expected markdown with exactly one fenced code block "
            "(```text``` or ```markdown```) containing the image prompt"
        )

    matches = list(_CODE_FENCE_RE.finditer(markdown))
    if not matches:
        raise SwipePromptParseError(
            "No markdown code fences found; expected exactly one fenced code block "
            "(```text``` or ```markdown```) for the image prompt"
        )

    valid_blocks: list[tuple[str, str]] = []
    seen_langs: list[str] = []
    for match in matches:
        lang = (match.group("lang") or "").strip().lower()
        code = (match.group("code") or "").strip()
        if lang not in seen_langs:
            seen_langs.append(lang)
        if not code:
            continue
        if lang in _ALLOWED_PROMPT_FENCE_LANGS:
            valid_blocks.append((lang or "(empty)", code))

    if not valid_blocks:
        lang_display = ", ".join(seen_langs) if seen_langs else "[none]"
        raise SwipePromptParseError(
            "No valid prompt code fence found; expected exactly one non-empty fenced block with language "
            f"`text` or `markdown`. Found fence languages: {lang_display}"
        )
    if len(valid_blocks) > 1:
        langs = ", ".join(lang for lang, _code in valid_blocks)
        raise SwipePromptParseError(
            "Ambiguous prompt output; expected exactly one non-empty valid fenced block "
            f"but found {len(valid_blocks)} (`{langs}`)"
        )

    return valid_blocks[0][1]
