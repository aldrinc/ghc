from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency/runtime specific
    genai = None
    genai_types = None
    _GENAI_IMPORT_ERROR = exc

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.env_loader import load_backend_env_files


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_backend_env_files(_BACKEND_ROOT)


_ALLOWED_BLOCK_TYPES = (
    "ImportedHeaderSection",
    "ImportedHeroSection",
    "ImportedProofBarSection",
    "ImportedFeatureSection",
    "ImportedOfferSection",
    "ImportedTestimonialsSection",
    "ImportedComparisonSection",
    "ImportedFaqSection",
    "ImportedFooterSection",
)
_DEFAULT_TRANSLATION_MODEL = os.getenv(
    "SITE_IMPORT_SECTION_TRANSLATION_MODEL",
    "gemini-2.5-flash",
)
_TRANSLATION_MAX_OUTPUT_TOKENS = 8192
_GEMINI_CLIENT: Any | None = None
_TRANSLATION_CACHE_DIR = Path(
    os.getenv(
        "SITE_IMPORT_SECTION_TRANSLATION_CACHE_DIR",
        str(_BACKEND_ROOT / ".tmp" / "site-import-section-translation-cache"),
    )
)


class ImportedSectionTextSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    original_text: str = Field(alias="originalText", min_length=1)
    text: str = Field(default="", max_length=4000)


class ImportedSectionButtonSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    original_text: str = Field(alias="originalText", min_length=1)
    text: str = Field(default="", max_length=1000)
    href: str = Field(default="", max_length=4000)


class ImportedSectionImageSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    original_src: str = Field(alias="originalSrc", default="", max_length=4000)
    original_text: str = Field(alias="originalText", default="", max_length=1000)
    src: str = Field(default="", max_length=4000)
    alt: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_original_anchor(self) -> "ImportedSectionImageSlot":
        if not self.original_src.strip() and not self.original_text.strip():
            raise ValueError("Image slots require either originalSrc or originalText.")
        return self


class ImportedSectionTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_type: Literal[
        "ImportedHeaderSection",
        "ImportedHeroSection",
        "ImportedProofBarSection",
        "ImportedFeatureSection",
        "ImportedOfferSection",
        "ImportedTestimonialsSection",
        "ImportedComparisonSection",
        "ImportedFaqSection",
        "ImportedFooterSection",
    ] = Field(alias="blockType")
    text_slots: list[ImportedSectionTextSlot] = Field(default_factory=list, alias="textSlots")
    button_slots: list[ImportedSectionButtonSlot] = Field(default_factory=list, alias="buttonSlots")
    image_slots: list[ImportedSectionImageSlot] = Field(default_factory=list, alias="imageSlots")


def _ensure_gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    if genai is None or genai_types is None:
        detail = str(_GENAI_IMPORT_ERROR) if _GENAI_IMPORT_ERROR else "unknown import error"
        raise RuntimeError(
            "google-genai dependency is unavailable for imported section translation. "
            f"Original error: {detail}"
        )
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required for imported section translation.")
    _GEMINI_CLIENT = genai.Client(api_key=api_key)
    return _GEMINI_CLIENT


def _normalize_model_name(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        raise RuntimeError("Gemini model name is required for imported section translation.")
    if normalized.startswith("models/"):
        return normalized.split("/", 1)[1]
    return normalized


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list):
        return ""
    chunks: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None)
        if not isinstance(parts, list):
            continue
        for part in parts:
            value = getattr(part, "text", None)
            if isinstance(value, str) and value.strip():
                chunks.append(value)
    return "\n".join(chunks).strip()


def _build_translation_system_instruction() -> str:
    return (
        "You translate one imported React/Tailwind section into the exact source-backed Puck block contract.\n"
        "This is not a rewrite task. Preserve exact original source text, href, and image anchors.\n"
        "Never invent content, URLs, assets, labels, or section structure.\n"
        "Only include content that belongs to the target section. If the provided snippet includes adjacent sections, ignore them.\n"
        "Return JSON only.\n\n"
        "Allowed blockType values:\n"
        "- ImportedHeaderSection: top navigation or site header.\n"
        "- ImportedHeroSection: hero/header content with primary message.\n"
        "- ImportedProofBarSection: trust strip, evidence section, proof stats, certification section.\n"
        "- ImportedFeatureSection: feature, benefits, educational, or general content section.\n"
        "- ImportedOfferSection: offer, pricing, selector, sticky CTA, or bundle section.\n"
        "- ImportedTestimonialsSection: reviews, testimonials, social proof wall.\n"
        "- ImportedComparisonSection: comparison matrix or vs table.\n"
        "- ImportedFaqSection: FAQ or accordion section.\n"
        "- ImportedFooterSection: footer or legal links section.\n\n"
        "Extraction rules:\n"
        "- You must choose originalText values only from availableTextAnchors.\n"
        "- You must choose button originalText/href values only from availableButtonAnchors.\n"
        "- You must choose image originalSrc/originalText values only from availableImageAnchors.\n"
        "- textSlots: include every user-editable visible text item that should be editable in the section.\n"
        "- For FAQ sections, include each question and each answer separately.\n"
        "- For comparison sections, include column labels, row labels, and textual cell values. Do not emit boolean checkmarks as text.\n"
        "- For proof/stat sections, include each stat value like 80% and each stat description separately.\n"
        "- If availableTextAnchors contains percent values, include every percent value exactly once.\n"
        "- If availableStatPairs is present, create exactly two text slots per pair: Stat N value and Stat N description, in source order.\n"
        "- If availableFaqPairs is present, include every question and every answer from those pairs.\n"
        "- For buttons, include visible CTA/button labels in buttonSlots, with href only if explicitly present.\n"
        "- For text-only brand marks or logos that should be replaceable with an image, emit both a text slot for the visible text and an image slot with originalText and empty originalSrc.\n"
        "- For real images, emit image slots with originalSrc.\n"
        "- Use concise stable labels like Headline, Body copy, Link label 1, FAQ 1 question, FAQ 1 answer, Stat 1 value, Stat 1 description.\n"
        "- Preserve source order.\n"
        "- Do not include duplicate slots.\n"
        "- Do not include code identifiers, variable names, or content from neighboring sections.\n"
    )


def _build_translation_prompt(payload: dict[str, Any]) -> str:
    return (
        "Translate this imported source section into the exact Puck block JSON shape.\n\n"
        "Return this shape exactly:\n"
        "{\n"
        '  "blockType": "...",\n'
        '  "textSlots": [{"label":"...","originalText":"...","text":"..."}],\n'
        '  "buttonSlots": [{"label":"...","originalText":"...","text":"...","href":"..."}],\n'
        '  "imageSlots": [{"label":"...","originalSrc":"...","originalText":"...","src":"...","alt":"..."}]\n'
        "}\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _call_gemini_translation(*, model: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = _ensure_gemini_client()
    response = client.models.generate_content(
        model=_normalize_model_name(model),
        contents=[_build_translation_prompt(payload)],
        config=genai_types.GenerateContentConfig(
            systemInstruction=_build_translation_system_instruction(),
            temperature=0,
            maxOutputTokens=_TRANSLATION_MAX_OUTPUT_TOKENS,
            responseMimeType="application/json",
            responseJsonSchema=ImportedSectionTranslation.model_json_schema(),
        ),
    )

    parsed = getattr(response, "parsed", None)
    if parsed is not None and hasattr(parsed, "model_dump"):
        parsed = parsed.model_dump(mode="json", by_alias=True, exclude_none=False)
    if parsed is None:
        raw = _extract_response_text(response)
        if not raw:
            raise RuntimeError("Gemini imported section translation returned no JSON payload.")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            preview = raw[:1200]
            raise RuntimeError(
                "Gemini imported section translation returned invalid JSON. "
                f"Raw response preview: {preview!r}"
            ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini imported section translation returned a non-object JSON payload.")
    translation = ImportedSectionTranslation.model_validate(parsed)
    return normalize_imported_section_translation(
        translation.model_dump(mode="json", by_alias=True, exclude_none=False)
    )


def _translation_cache_file(*, model: str, payload_json: str) -> Path:
    digest = hashlib.sha256(f"{model}\n{payload_json}".encode("utf-8")).hexdigest()
    return _TRANSLATION_CACHE_DIR / f"{digest}.json"


def _load_translation_cache(*, model: str, payload_json: str) -> dict[str, Any] | None:
    cache_file = _translation_cache_file(model=model, payload_json=payload_json)
    if not cache_file.exists():
        return None
    parsed = json.loads(cache_file.read_text(encoding="utf-8"))
    translation = ImportedSectionTranslation.model_validate(parsed)
    return normalize_imported_section_translation(
        translation.model_dump(mode="json", by_alias=True, exclude_none=False)
    )


def _store_translation_cache(*, model: str, payload_json: str, translation: dict[str, Any]) -> None:
    cache_file = _translation_cache_file(model=model, payload_json=payload_json)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(translation, indent=2), encoding="utf-8")


def normalize_imported_section_translation(translation: dict[str, Any]) -> dict[str, Any]:
    hydrated = dict(translation)

    text_slots = []
    for entry in translation.get("textSlots") or []:
        if not isinstance(entry, dict):
            continue
        normalized = dict(entry)
        original_text = str(normalized.get("originalText") or "").strip()
        text = str(normalized.get("text") or "")
        if original_text and not text.strip():
            normalized["text"] = original_text
        text_slots.append(normalized)

    button_slots = []
    for entry in translation.get("buttonSlots") or []:
        if not isinstance(entry, dict):
            continue
        normalized = dict(entry)
        original_text = str(normalized.get("originalText") or "").strip()
        text = str(normalized.get("text") or "")
        if original_text and not text.strip():
            normalized["text"] = original_text
        button_slots.append(normalized)

    image_slots = []
    for entry in translation.get("imageSlots") or []:
        if not isinstance(entry, dict):
            continue
        normalized = dict(entry)
        original_text = str(normalized.get("originalText") or "").strip()
        alt = str(normalized.get("alt") or "")
        if original_text and not alt.strip():
            normalized["alt"] = original_text
        image_slots.append(normalized)

    hydrated["textSlots"] = text_slots
    hydrated["buttonSlots"] = button_slots
    hydrated["imageSlots"] = image_slots
    return hydrated


@lru_cache(maxsize=256)
def _translate_cached(model: str, payload_json: str) -> dict[str, Any]:
    cached = _load_translation_cache(model=model, payload_json=payload_json)
    if cached is not None:
        return cached
    payload = json.loads(payload_json)
    translation = _call_gemini_translation(model=model, payload=payload)
    _store_translation_cache(model=model, payload_json=payload_json, translation=translation)
    return translation


def translate_imported_source_section(
    *,
    section_id: str,
    display_name: str,
    component_name: str,
    section_type_hint: str,
    block_type_hint: str,
    semantic_tags: list[str],
    source_extraction_mode: str,
    section_source: str,
    available_text_anchors: list[str],
    available_button_anchors: list[dict[str, str]],
    available_image_anchors: list[dict[str, str]],
    available_stat_pairs: list[dict[str, str]],
    available_faq_pairs: list[dict[str, str]],
) -> dict[str, Any]:
    if not section_source.strip():
        raise RuntimeError(f"Imported section '{section_id or display_name or component_name}' is missing section source.")
    payload = {
        "sectionId": section_id,
        "displayName": display_name,
        "componentName": component_name,
        "sectionTypeHint": section_type_hint,
        "blockTypeHint": block_type_hint,
        "semanticTags": semantic_tags,
        "sourceExtractionMode": source_extraction_mode,
        "availableTextAnchors": available_text_anchors,
        "availableButtonAnchors": available_button_anchors,
        "availableImageAnchors": available_image_anchors,
        "availableStatPairs": available_stat_pairs,
        "availableFaqPairs": available_faq_pairs,
        "sectionSource": section_source,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return json.loads(json.dumps(_translate_cached(_DEFAULT_TRANSLATION_MODEL, payload_json)))
