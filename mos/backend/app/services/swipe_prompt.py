from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_PROMPT_CACHE: Dict[str, Tuple[str, str]] = {}


def load_swipe_to_image_ad_prompt() -> Tuple[str, str]:
    """
    Load the swipe -> image-ad prompt template and compute its SHA256.
    """
    cache_key = "swipe_to_image_ad"
    if cache_key in _PROMPT_CACHE:
        return _PROMPT_CACHE[cache_key]

    backend_app_root = Path(__file__).resolve().parents[1]
    prompt_path = backend_app_root / "prompts" / "swipe" / "swipe_to_image_ad.md"
    text = prompt_path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    _PROMPT_CACHE[cache_key] = (text, sha)
    return text, sha


def _normalize_unknown(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "[UNKNOWN]"


def build_swipe_context_block(
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    audience: str | None = None,
    brand_colors_fonts: str | None = None,
    must_avoid_claims: List[str] | None = None,
    assets: Dict[str, str] | None = None,
    research_copy_bank: List[str] | None = None,
) -> str:
    if not isinstance(brand_name, str) or not brand_name.strip():
        raise ValueError("brand_name is required to build swipe context block")
    if not isinstance(product_name, str) or not product_name.strip():
        raise ValueError("product_name is required to build swipe context block")
    if not isinstance(angle, str) or not angle.strip():
        raise ValueError("angle is required to build swipe context block")

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

    lines.append(f"Angle: {angle.strip()}")

    copy_bank = [s.strip() for s in (research_copy_bank or []) if isinstance(s, str) and s.strip()]
    lines.append("Research copy bank (use for emotional, visceral, stop-the-scroll phrasing; do not invent facts):")
    if copy_bank:
        for entry in copy_bank[:50]:
            lines.append(f"- {entry}")
        if len(copy_bank) > 50:
            lines.append(f"- [TRUNCATED: {len(copy_bank) - 50} more lines]")
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


class SwipePromptParseError(RuntimeError):
    pass


def extract_new_image_prompt_from_markdown(markdown: str) -> str:
    if not isinstance(markdown, str) or not markdown.strip():
        raise SwipePromptParseError("Swipe prompt output is empty; expected markdown with a ```text code fence")

    matches = list(_CODE_FENCE_RE.finditer(markdown))
    if not matches:
        raise SwipePromptParseError("No markdown code fences found; expected a ```text fenced block for the image prompt")

    text_blocks: list[str] = []
    other_blocks: list[str] = []
    for match in matches:
        lang = (match.group("lang") or "").strip().lower()
        code = (match.group("code") or "").strip()
        if not code:
            continue
        if lang == "text":
            text_blocks.append(code)
        else:
            other_blocks.append(code)

    if text_blocks:
        return text_blocks[0]
    raise SwipePromptParseError(
        "No ```text code fence found in swipe prompt output; cannot extract the generation-ready image prompt"
    )
