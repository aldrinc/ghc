from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, TypeVar
from urllib.parse import unquote, urlparse

import google.generativeai as legacy_genai
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency/runtime specific
    genai = None
    genai_types = None
    _GENAI_IMPORT_ERROR = exc

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif"}
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_PLACEHOLDER_TEXTS = {"enter text...", "[insert review app]"}
_IGNORE_TEXT_KEYS = {
    "__v",
    "classGlobalStyling",
    "collapseIcon",
    "expandIcon",
    "icon",
    "iconPos",
    "name",
    "placeholder",
}
_SECTION_ROOT_TYPES = {"Section"}
_MAX_NEARBY_TEXT_SNIPPETS = 10
_MAX_SECTION_TEXT_SNIPPETS = 16
_MAX_PAGE_OUTLINE_SECTIONS = 24
_MAX_REFERENCE_SLOTS = 3
_GEMINI_JSON_MAX_ATTEMPTS = 8
_T = TypeVar("_T")


@dataclass
class PageFlyImageSlot:
    slot_id: str
    item_id: str
    item_type: str
    root_order: int
    json_path: str
    url: str
    local_path: str
    content_type: str | None
    width: int | None
    height: int | None
    alt_text: str | None
    ancestor_types: list[str] = field(default_factory=list)
    ancestor_ids: list[str] = field(default_factory=list)
    nearby_text: list[str] = field(default_factory=list)
    section_text: list[str] = field(default_factory=list)
    section_root_id: str | None = None
    section_root_type: str | None = None
    analysis: "PageFlySlotAnalysis | None" = None
    decision: "PageFlySlotDecision | None" = None
    selection_score: float | None = None
    selected_as_sample: bool = False

    @property
    def file_name(self) -> str:
        return Path(self.local_path).name

    def llm_summary(self) -> dict[str, Any]:
        return {
            "slotId": self.slot_id,
            "itemId": self.item_id,
            "itemType": self.item_type,
            "rootOrder": self.root_order,
            "jsonPath": self.json_path,
            "imageUrl": self.url,
            "fileName": self.file_name,
            "dimensions": {"width": self.width, "height": self.height},
            "altText": self.alt_text,
            "ancestorTypes": self.ancestor_types,
            "sectionRootId": self.section_root_id,
            "sectionRootType": self.section_root_type,
            "nearbyText": self.nearby_text,
            "sectionText": self.section_text,
        }

    def manifest_summary(self) -> dict[str, Any]:
        payload = self.llm_summary()
        payload.update(
            {
                "contentType": self.content_type,
                "localPath": self.local_path,
                "analysis": self.analysis.model_dump(mode="json", by_alias=True) if self.analysis else None,
                "decision": self.decision.model_dump(mode="json", by_alias=True) if self.decision else None,
                "selectionScore": self.selection_score,
                "selectedAsSample": self.selected_as_sample,
            }
        )
        return payload


class PageFlySlotAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slot_id: str = Field(alias="slotId")
    section_purpose: Literal[
        "hero",
        "comparison",
        "feature",
        "testimonial",
        "badge",
        "gallery",
        "infographic",
        "faq",
        "cta",
        "logo",
        "bundle",
        "other",
    ] = Field(default="other", alias="sectionPurpose")
    image_intent: str = Field(default="unknown", alias="imageIntent", min_length=1, max_length=64)
    render_mode: Literal["context_only", "requires_reference"] = Field(alias="renderMode")
    should_use_product_reference: bool = Field(alias="shouldUseProductReference")
    reference_prominence: Literal["primary", "secondary", "none"] = Field(
        default="none",
        alias="referenceProminence",
    )
    is_product_reference_candidate: bool = Field(alias="isProductReferenceCandidate")
    candidate_strength: Literal["primary", "supporting", "secondary", "none"] = Field(
        default="none",
        alias="candidateStrength",
    )
    visual_goal: str = Field(alias="visualGoal", min_length=1, max_length=240)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = Field(default="[UNKNOWN]", min_length=1, max_length=240)
    status: Literal["ready", "needs_review"] = "ready"


class PageFlySlotAnalysisBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analyses: list[PageFlySlotAnalysis]


class PageFlyPlanningResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    analyses: list[PageFlySlotAnalysis]


class PageFlySlotDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(alias="slotId")
    render_mode: Literal["context_only", "requires_reference"] = Field(alias="renderMode")
    should_use_product_reference: bool = Field(alias="shouldUseProductReference")
    reference_prominence: Literal["primary", "secondary", "none"] = Field(alias="referenceProminence")
    visual_goal: str = Field(alias="visualGoal", min_length=1, max_length=240)
    status: Literal["ready", "needs_review"]
    reason: str = Field(min_length=1, max_length=240)


class PageFlyReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_slot_ids: list[str] = Field(alias="referenceSlotIds")
    slot_decisions: list[PageFlySlotDecision] = Field(alias="slotDecisions")
    notes: list[str]


@dataclass
class PageFlySlotPlanningResult:
    slots: list[PageFlyImageSlot]
    reconciliation: PageFlyReconciliation
    reference_slots: list[PageFlyImageSlot]

    def selected_slot(self, slot_id: str) -> PageFlyImageSlot:
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        raise RuntimeError(f"Unknown PageFly slot_id in planning result: {slot_id}")


_GEMINI_CLIENT: Any | None = None


def _ensure_gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    if genai is None or genai_types is None:
        detail = str(_GENAI_IMPORT_ERROR) if _GENAI_IMPORT_ERROR else "unknown import error"
        raise RuntimeError(
            "google-genai dependency is unavailable for PageFly slot planning. "
            f"Original error: {detail}"
        )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured for PageFly slot planning.")
    _GEMINI_CLIENT = genai.Client(api_key=api_key)
    return _GEMINI_CLIENT


def _ensure_legacy_gemini_configured() -> None:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY is required for PageFly slot planning.")
    legacy_genai.configure(api_key=api_key)


def _normalize_model_name(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        raise ValueError("Gemini model name is required for PageFly slot planning.")
    if normalized.startswith("models/"):
        return normalized.split("/", 1)[1]
    return normalized


def _normalize_legacy_model_name(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        raise ValueError("Gemini model name is required for PageFly slot planning.")
    if normalized.startswith("models/"):
        return normalized
    return f"models/{normalized}"


def _is_remote_image_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    suffix = Path(unquote(parsed.path)).suffix.lower()
    return suffix in _IMAGE_EXTENSIONS


def _normalize_text(value: str) -> str:
    cleaned = unescape(_HTML_TAG_RE.sub(" ", value or ""))
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def _looks_like_noise(value: str) -> bool:
    if not value:
        return True
    lowered = value.lower()
    if lowered in _PLACEHOLDER_TEXTS:
        return True
    if value.startswith("http://") or value.startswith("https://"):
        return True
    if re.fullmatch(r"[A-Za-z0-9_.-]+\.(png|jpg|jpeg|webp|gif|svg|avif)", value, flags=re.IGNORECASE):
        return True
    if value.startswith("pf-"):
        return True
    return False


def _extract_text_snippets(node: Any, *, parent_key: str | None = None) -> list[str]:
    snippets: list[str] = []

    def walk(current: Any, current_key: str | None = None) -> None:
        if isinstance(current, dict):
            for key, value in current.items():
                walk(value, key)
            return
        if isinstance(current, list):
            for value in current:
                walk(value, current_key)
            return
        if not isinstance(current, str):
            return
        if current_key in _IGNORE_TEXT_KEYS:
            return
        cleaned = _normalize_text(current)
        if not cleaned or _looks_like_noise(cleaned):
            return
        snippets.append(cleaned)

    walk(node, parent_key)
    deduped: list[str] = []
    seen: set[str] = set()
    for snippet in snippets:
        if snippet in seen:
            continue
        seen.add(snippet)
        deduped.append(snippet)
    return deduped


def _iter_image_entries(node: Any, *, path: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            matches.extend(_iter_image_entries(value, path=child_path))
        return matches
    if isinstance(node, list):
        for index, value in enumerate(node):
            child_path = f"{path}[{index}]"
            matches.extend(_iter_image_entries(value, path=child_path))
        return matches
    if isinstance(node, str) and _is_remote_image_url(node):
        matches.append((path, node))
    return matches


def _build_page_maps(page_data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str], dict[str, list[str]], list[str], dict[str, list[str]]]:
    items = page_data.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("PageFly export must define a non-empty top-level items array.")

    item_by_id: dict[str, dict[str, Any]] = {}
    parent_by_id: dict[str, str] = {}
    children_by_id: dict[str, list[str]] = defaultdict(list)
    ordered_ids: list[str] = []
    item_paths: dict[str, list[str]] = defaultdict(list)

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise RuntimeError(f"PageFly item at index {index} is not an object.")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise RuntimeError(f"PageFly item at index {index} is missing a valid id.")
        normalized_id = item_id.strip()
        if normalized_id in item_by_id:
            raise RuntimeError(f"Duplicate PageFly item id detected: {normalized_id}")
        item_by_id[normalized_id] = item
        ordered_ids.append(normalized_id)
        item_paths[normalized_id].append(f"$.items[{index}]")

    for item_id in ordered_ids:
        item = item_by_id[item_id]
        raw_children = item.get("children")
        if not isinstance(raw_children, list):
            continue
        for child_id in raw_children:
            if not isinstance(child_id, str) or child_id not in item_by_id:
                continue
            if child_id in parent_by_id:
                raise RuntimeError(f"PageFly child item {child_id} has multiple parents; expected a tree.")
            parent_by_id[child_id] = item_id
            children_by_id[item_id].append(child_id)

    root_ids = [item_id for item_id in ordered_ids if item_id not in parent_by_id]
    if not root_ids:
        raise RuntimeError("PageFly export does not contain any root items.")
    return items, item_by_id, parent_by_id, children_by_id, root_ids, item_paths


def _find_section_root(
    *,
    item_id: str,
    item_by_id: dict[str, dict[str, Any]],
    parent_by_id: dict[str, str],
) -> str:
    current_id = item_id
    candidate = item_id
    while True:
        parent_id = parent_by_id.get(current_id)
        if parent_id is None:
            return candidate
        candidate = parent_id
        parent_type = str(item_by_id[parent_id].get("type") or "").strip()
        if parent_type in _SECTION_ROOT_TYPES:
            return parent_id
        current_id = parent_id


def _dfs_item_ids(root_id: str, children_by_id: dict[str, list[str]]) -> list[str]:
    ordered: list[str] = []

    def walk(item_id: str) -> None:
        ordered.append(item_id)
        for child_id in children_by_id.get(item_id, []):
            walk(child_id)

    walk(root_id)
    return ordered


def _dedupe_preserve_order(values: list[str], *, max_items: int | None = None) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
        if isinstance(max_items, int) and max_items > 0 and len(deduped) >= max_items:
            break
    return deduped


def _chunked(values: list[_T], size: int) -> list[list[_T]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [values[index : index + size] for index in range(0, len(values), size)]


def extract_pagefly_image_slots(
    *,
    page_data: dict[str, Any],
    downloaded_images: list[Any],
) -> list[PageFlyImageSlot]:
    _items, item_by_id, parent_by_id, children_by_id, root_ids, item_paths = _build_page_maps(page_data)

    download_by_url: dict[str, Any] = {}
    for record in downloaded_images:
        url = getattr(record, "url", None)
        if not isinstance(url, str) or not url.strip():
            continue
        download_by_url[url] = record

    item_texts: dict[str, list[str]] = {}
    for item_id, item in item_by_id.items():
        snippets = _extract_text_snippets(item.get("data"))
        label = item.get("type")
        if isinstance(label, str) and label.strip():
            snippets = _dedupe_preserve_order([*snippets], max_items=12)
        item_texts[item_id] = snippets

    section_item_order: dict[str, list[str]] = {}
    for root_id in root_ids:
        section_item_order[root_id] = _dfs_item_ids(root_id, children_by_id)
    for item_id in list(item_by_id.keys()):
        section_root_id = _find_section_root(item_id=item_id, item_by_id=item_by_id, parent_by_id=parent_by_id)
        if section_root_id not in section_item_order:
            section_item_order[section_root_id] = _dfs_item_ids(section_root_id, children_by_id)

    root_order_by_id = {root_id: index for index, root_id in enumerate(root_ids)}

    slots: list[PageFlyImageSlot] = []
    slot_counter = 0
    for item_id, item in item_by_id.items():
        image_entries = _iter_image_entries(item.get("data"), path=item_paths[item_id][0] + ".data")
        if not image_entries:
            continue

        ancestor_ids: list[str] = []
        current_id = item_id
        while current_id in parent_by_id:
            parent_id = parent_by_id[current_id]
            ancestor_ids.append(parent_id)
            current_id = parent_id
        ancestor_ids.reverse()
        ancestor_types = [
            str(item_by_id[ancestor_id].get("type") or "").strip()
            for ancestor_id in ancestor_ids
            if isinstance(item_by_id.get(ancestor_id), dict)
        ]

        section_root_id = _find_section_root(item_id=item_id, item_by_id=item_by_id, parent_by_id=parent_by_id)
        section_root = item_by_id.get(section_root_id, {})
        section_root_type = str(section_root.get("type") or "").strip() or None
        section_order = section_item_order.get(section_root_id, [item_id])
        section_index = section_order.index(item_id) if item_id in section_order else 0
        nearby_ids = section_order[max(0, section_index - 8) : section_index + 9]
        nearby_text = _dedupe_preserve_order(
            [text for nearby_id in nearby_ids for text in item_texts.get(nearby_id, [])],
            max_items=_MAX_NEARBY_TEXT_SNIPPETS,
        )
        section_text = _dedupe_preserve_order(
            [text for section_item_id in section_order for text in item_texts.get(section_item_id, [])],
            max_items=_MAX_SECTION_TEXT_SNIPPETS,
        )

        root_candidate = ancestor_ids[0] if ancestor_ids else item_id
        root_order = root_order_by_id.get(root_candidate, len(root_order_by_id))
        alt_text = None
        data = item.get("data")
        if isinstance(data, dict):
            alt_raw = data.get("alt")
            if isinstance(alt_raw, str):
                cleaned_alt = _normalize_text(alt_raw.split("__PID:", 1)[0])
                if cleaned_alt and not _looks_like_noise(cleaned_alt):
                    alt_text = cleaned_alt

        seen_paths: set[tuple[str, str]] = set()
        for image_path, image_url in image_entries:
            key = (image_path, image_url)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            download_record = download_by_url.get(image_url)
            if download_record is None:
                raise RuntimeError(
                    "PageFly slot extraction found an image URL that was not downloaded: "
                    f"{image_url}"
                )
            local_path = getattr(download_record, "local_path", None)
            if not isinstance(local_path, str) or not local_path.strip():
                raise RuntimeError(
                    "Downloaded image record is missing local_path for PageFly slot: "
                    f"{image_url}"
                )
            slot_counter += 1
            slot_id = f"slot-{slot_counter:03d}-{item_id[:8]}"
            slots.append(
                PageFlyImageSlot(
                    slot_id=slot_id,
                    item_id=item_id,
                    item_type=str(item.get("type") or "").strip() or "unknown",
                    root_order=root_order,
                    json_path=image_path,
                    url=image_url,
                    local_path=local_path,
                    content_type=getattr(download_record, "content_type", None),
                    width=getattr(download_record, "width", None),
                    height=getattr(download_record, "height", None),
                    alt_text=alt_text,
                    ancestor_types=ancestor_types,
                    ancestor_ids=ancestor_ids,
                    nearby_text=nearby_text,
                    section_text=section_text,
                    section_root_id=section_root_id,
                    section_root_type=section_root_type,
                )
            )

    if not slots:
        raise RuntimeError("No PageFly image slots were extracted from the export.")
    slots.sort(key=lambda slot: (slot.root_order, slot.json_path, slot.slot_id))
    return slots


def _page_outline(slots: list[PageFlyImageSlot]) -> list[dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for slot in slots:
        key = slot.section_root_id or slot.slot_id
        if key not in sections:
            sections[key] = {
                "sectionRootId": slot.section_root_id,
                "sectionRootType": slot.section_root_type,
                "rootOrder": slot.root_order,
                "headlineSnippets": list(slot.section_text[:4]),
                "slotIds": [],
            }
            ordered_keys.append(key)
        sections[key]["slotIds"].append(slot.slot_id)

    outline = [sections[key] for key in ordered_keys]
    outline.sort(key=lambda entry: (entry.get("rootOrder") if isinstance(entry.get("rootOrder"), int) else 9999))
    return outline[:_MAX_PAGE_OUTLINE_SECTIONS]


def _load_slot_image_part(slot: PageFlyImageSlot) -> tuple[bytes, str]:
    path = Path(slot.local_path)
    mime_type = (slot.content_type or "").strip().lower()
    if mime_type in {"image/png", "image/jpeg", "image/webp"}:
        return path.read_bytes(), mime_type

    with Image.open(path) as image:
        first_frame = image.convert("RGBA")
        buffer = BytesIO()
        first_frame.save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list):
        return ""
    texts: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                texts.append(part_text.strip())
    return "\n".join(texts).strip()


def _extract_legacy_gemini_text(result: Any) -> str | None:
    try:
        text = getattr(result, "text", None)
    except Exception:
        text = None
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(result, "candidates", None)
    if not candidates:
        return None
    first = candidates[0]
    content = getattr(first, "content", None) if first else None
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return None

    texts: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str) and part_text.strip():
            texts.append(part_text.strip())
    joined = "\n".join(texts).strip()
    return joined or None


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_first_json_object_from_text(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise RuntimeError("PageFly Gemini planning response did not contain a JSON object.")

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : idx + 1]
                return json.loads(candidate)

    raise RuntimeError("PageFly Gemini planning response contained malformed JSON.")


def _repair_truncated_json(text: str) -> str | None:
    stripped = text.rstrip()
    if not stripped.startswith("{"):
        return None

    closing_stack: list[str] = []
    in_string = False
    escape = False
    for char in stripped:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            closing_stack.append("}")
            continue
        if char == "[":
            closing_stack.append("]")
            continue
        if char in {"}", "]"}:
            if not closing_stack or char != closing_stack[-1]:
                return None
            closing_stack.pop()

    if in_string or not closing_stack:
        return None
    return stripped + "".join(reversed(closing_stack))


def _call_legacy_gemini_json(
    *,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    _ensure_legacy_gemini_configured()
    model_client = legacy_genai.GenerativeModel(
        model_name=_normalize_legacy_model_name(model),
        generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
    )

    last_error: RuntimeError | None = None
    for attempt in range(1, _GEMINI_JSON_MAX_ATTEMPTS + 1):
        try:
            response = model_client.generate_content([prompt], request_options={"timeout": 180})
        except Exception as exc:  # noqa: BLE001
            last_error = RuntimeError(f"PageFly Gemini planning call failed: {exc}")
            if attempt >= _GEMINI_JSON_MAX_ATTEMPTS:
                raise last_error from exc
            continue

        raw = _strip_json_fence(_extract_legacy_gemini_text(response) or "")
        if not raw:
            last_error = RuntimeError("PageFly Gemini planning call returned no text.")
            if attempt >= _GEMINI_JSON_MAX_ATTEMPTS:
                raise last_error
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(raw)
            if repaired is not None:
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = None
            else:
                parsed = None
            if parsed is None:
                try:
                    parsed = _extract_first_json_object_from_text(raw)
                except RuntimeError as exc:
                    preview = raw[:1200]
                    last_error = RuntimeError(
                        "PageFly Gemini planning call returned invalid JSON. "
                        f"Raw response preview: {preview!r}"
                    )
                    if attempt >= _GEMINI_JSON_MAX_ATTEMPTS:
                        raise last_error from exc
                    continue
        if not isinstance(parsed, dict):
            last_error = RuntimeError("PageFly Gemini planning call returned a non-object JSON payload.")
            if attempt >= _GEMINI_JSON_MAX_ATTEMPTS:
                raise last_error
            continue
        return parsed

    if last_error is not None:
        raise last_error
    raise RuntimeError("PageFly Gemini planning call failed without returning a parsed payload.")


def _call_gemini_json(
    *,
    model: str,
    system_instruction: str,
    contents: list[Any],
    response_schema: Any,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    client = _ensure_gemini_client()
    normalized_model = _normalize_model_name(model)
    config_kwargs: dict[str, Any] = {
        "systemInstruction": system_instruction,
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
        "responseMimeType": "application/json",
    }
    if hasattr(response_schema, "model_json_schema"):
        config_kwargs["responseJsonSchema"] = response_schema.model_json_schema()
    else:
        config_kwargs["responseJsonSchema"] = response_schema
    last_error: RuntimeError | None = None
    for attempt in range(1, _GEMINI_JSON_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=normalized_model,
                contents=contents,
                config=genai_types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:  # noqa: BLE001
            last_error = RuntimeError(f"PageFly Gemini planning call failed: {exc}")
            if attempt >= _GEMINI_JSON_MAX_ATTEMPTS:
                raise last_error from exc
            continue

        parsed = getattr(response, "parsed", None)
        if parsed is not None and hasattr(parsed, "model_dump"):
            parsed = parsed.model_dump(mode="json", by_alias=True, exclude_none=False)
        if parsed is None:
            raw = _strip_json_fence(_extract_response_text(response))
            if not raw:
                last_error = RuntimeError(
                    "PageFly Gemini planning call returned neither parsed JSON nor text."
                )
                if attempt >= _GEMINI_JSON_MAX_ATTEMPTS:
                    raise last_error
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                repaired = _repair_truncated_json(raw)
                if repaired is not None:
                    try:
                        parsed = json.loads(repaired)
                    except json.JSONDecodeError:
                        parsed = None
                    else:
                        if not isinstance(parsed, dict):
                            raise RuntimeError("PageFly Gemini planning call returned a non-object JSON payload.")
                else:
                    parsed = None
            if parsed is None:
                try:
                    parsed = _extract_first_json_object_from_text(raw)
                except RuntimeError as exc:
                    preview = raw[:1200]
                    last_error = RuntimeError(
                        "PageFly Gemini planning call returned invalid JSON. "
                        f"Raw response preview: {preview!r}"
                    )
                    if attempt >= _GEMINI_JSON_MAX_ATTEMPTS:
                        raise last_error from exc
                    continue
        if not isinstance(parsed, dict):
            raise RuntimeError("PageFly Gemini planning call returned a non-object JSON payload.")
        return parsed

    if last_error is not None:
        raise last_error
    raise RuntimeError("PageFly Gemini planning call failed without returning a parsed payload.")


def _build_text_batch_analysis_prompt(
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    slots: list[PageFlyImageSlot],
    page_outline: list[dict[str, Any]],
) -> str:
    payload = {
        "brandName": brand_name,
        "productName": product_name,
        "angle": angle,
        "hook": hook,
        "pageOutline": page_outline,
        "slots": [slot.llm_summary() for slot in slots],
    }
    return (
        "Analyze each PageFly image slot below using page-context evidence only.\n\n"
        "You do NOT see the image pixels in this pass.\n"
        "Use nearby copy, section copy, filenames, alt text, dimensions, and page position.\n\n"
        "Decision rules:\n"
        "- sectionPurpose describes the section's role on the page: hero, comparison, feature, testimonial, badge, gallery, infographic, faq, cta, logo, bundle, or other.\n"
        "- imageIntent describes what the image itself is doing: product_identity, product_support, social_proof, education, decorative, badge, logo, or unknown.\n"
        "- If the image is a seal, badge, icon strip, or trust marker, use sectionPurpose=badge and imageIntent=badge or logo.\n"
        "- Never use feature, gallery, comparison, testimonial, faq, cta, bundle, or other as imageIntent values.\n"
        "- renderMode=requires_reference only when the adapted output must preserve recognizable product identity.\n"
        "- renderMode=context_only when Gemini can generate a relevant replacement from the section meaning alone.\n"
        "- shouldUseProductReference=true only when the adapted output needs recognizable product identity.\n"
        "- shouldUseProductReference must exactly match renderMode: requires_reference=true, context_only=false.\n"
        "- referenceProminence=primary means the product should be the main visual subject.\n"
        "- referenceProminence=secondary means the product should appear but not dominate.\n"
        "- referenceProminence=none means no product reference imagery is needed.\n"
        "- referenceProminence must be none when renderMode=context_only.\n"
        "- isProductReferenceCandidate=true only when the slot likely contains a canonical product identity image.\n"
        "- candidateStrength=primary only for the clearest likely product identity slots.\n"
        "- visualGoal must be one short sentence describing what the new image should communicate visually.\n"
        "- If page-context evidence is insufficient without seeing the image, set status=needs_review.\n"
        "- Keep reason to one short sentence under 160 characters.\n"
        "- Return one analysis entry for every slotId exactly once.\n\n"
        "Return JSON only with this shape:\n"
        "{\n"
        '  "analyses": [ ... ]\n'
        "}\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _build_full_page_planning_prompt(
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    slots: list[PageFlyImageSlot],
    page_outline: list[dict[str, Any]],
) -> str:
    payload = {
        "brandName": brand_name,
        "productName": product_name,
        "angle": angle,
        "hook": hook,
        "pageOutline": page_outline,
        "slots": [slot.llm_summary() for slot in slots],
    }
    return (
        "Analyze the full PageFly page below and produce final slot-level product-reference planning.\n\n"
        "You do NOT see the image pixels in this planner pass.\n"
        "Use the JSON/page evidence only: nearby copy, section copy, filenames, alt text, dimensions, and page position.\n\n"
        "Your job:\n"
        "- Return one final analysis entry for every slotId exactly once.\n"
        "- Decide whether each slot's adapted output needs recognizable product identity.\n"
        "- Decide whether each slot is itself a likely product-reference candidate.\n"
        "- Keep similar/repeated sections consistent.\n"
        "- Keep the response compact. Extended explanations are not needed.\n\n"
        "Decision rules:\n"
        "- renderMode=requires_reference only when the adapted output must preserve recognizable product identity.\n"
        "- renderMode=context_only when Gemini can generate a relevant replacement from the section meaning alone.\n"
        "- shouldUseProductReference=true only when the adapted output needs recognizable product identity.\n"
        "- shouldUseProductReference must exactly match renderMode: requires_reference=true, context_only=false.\n"
        "- referenceProminence=primary means the product should be the main visual subject.\n"
        "- referenceProminence=secondary means the product should appear but not dominate.\n"
        "- referenceProminence=none means no product reference imagery is needed.\n"
        "- referenceProminence must be none when renderMode=context_only.\n"
        "- isProductReferenceCandidate=true only when the slot likely contains a canonical product identity image.\n"
        "- candidateStrength=primary only for the clearest likely product identity slots.\n\n"
        "- visualGoal must be one short sentence under 18 words describing what the new image should communicate visually.\n"
        "- confidence should be a compact decimal like 0.82.\n"
        "- reason must be one short sentence under 18 words.\n\n"
        "Return JSON only with this exact top-level shape:\n"
        "{\n"
        '  "analyses": [ ... ]\n'
        "}\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _build_section_planning_prompt(
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    section_slots: list[PageFlyImageSlot],
    page_outline: list[dict[str, Any]],
) -> str:
    if not section_slots:
        raise ValueError("section_slots must be non-empty")
    section_root_id = section_slots[0].section_root_id or section_slots[0].slot_id
    section_root_type = section_slots[0].section_root_type or "unknown"
    payload = {
        "brandName": brand_name,
        "productName": product_name,
        "angle": angle,
        "hook": hook,
        "pageOutline": page_outline,
        "section": {
            "sectionRootId": section_root_id,
            "sectionRootType": section_root_type,
            "rootOrder": section_slots[0].root_order,
            "slotIds": [slot.slot_id for slot in section_slots],
            "slots": [slot.llm_summary() for slot in section_slots],
        },
    }
    return (
        "Analyze one PageFly section and produce final slot-level product-reference planning for that section only.\n\n"
        "You do NOT see the image pixels in this planner pass.\n"
        "Use the JSON/page evidence only: nearby copy, section copy, filenames, alt text, dimensions, and page position.\n\n"
        "Your job:\n"
        "- Return one final analysis entry for every slotId in this section exactly once.\n"
        "- Decide whether each slot's adapted output needs recognizable product identity.\n"
        "- Decide whether each slot is itself a likely product-reference candidate.\n"
        "- Keep the response compact. Extended explanations are not needed.\n\n"
        "Decision rules:\n"
        "- renderMode=requires_reference only when the adapted output must preserve recognizable product identity.\n"
        "- renderMode=context_only when Gemini can generate a relevant replacement from the section meaning alone.\n"
        "- shouldUseProductReference=true only when the adapted output needs recognizable product identity.\n"
        "- shouldUseProductReference must exactly match renderMode: requires_reference=true, context_only=false.\n"
        "- referenceProminence=primary means the product should be the main visual subject.\n"
        "- referenceProminence=secondary means the product should appear but not dominate.\n"
        "- referenceProminence=none means no product reference imagery is needed.\n"
        "- referenceProminence must be none when renderMode=context_only.\n"
        "- isProductReferenceCandidate=true only when the slot likely contains a canonical product identity image.\n"
        "- candidateStrength=primary only for the clearest likely product identity slots.\n\n"
        "- visualGoal must be one short sentence describing what the new image should communicate visually.\n\n"
        "Return JSON only with this exact top-level shape:\n"
        "{\n"
        '  "analyses": [\n'
        "    {\n"
        '      "slotId": "slot-123",\n'
        '      "sectionPurpose": "hero|comparison|feature|testimonial|badge|gallery|infographic|faq|cta|logo|bundle|other",\n'
        '      "imageIntent": "product_identity|product_support|social_proof|education|decorative|badge|logo|unknown",\n'
        '      "renderMode": "context_only|requires_reference",\n'
        '      "shouldUseProductReference": true,\n'
        '      "referenceProminence": "primary|secondary|none",\n'
        '      "isProductReferenceCandidate": false,\n'
        '      "candidateStrength": "primary|supporting|secondary|none",\n'
        '      "visualGoal": "One short sentence.",\n'
        '      "confidence": 0.84,\n'
        '      "reason": "One short sentence under 160 characters.",\n'
        '      "status": "ready|needs_review"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Every analysis object must include every field above exactly once.\n"
        "Do not omit sectionPurpose, imageIntent, confidence, reason, or status.\n"
        "Keep the response compact and valid JSON.\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _build_slot_analysis_prompt(
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    slot: PageFlyImageSlot,
    page_outline: list[dict[str, Any]],
    draft_analysis: PageFlySlotAnalysis | None = None,
) -> str:
    payload = {
        "brandName": brand_name,
        "productName": product_name,
        "angle": angle,
        "hook": hook,
        "pageOutline": page_outline,
        "slot": slot.llm_summary(),
        "draftAnalysis": draft_analysis.model_dump(mode="json", by_alias=True) if draft_analysis else None,
    }
    return (
        "Visually verify the PageFly image slot below.\n\n"
        "You are given a draft slot analysis from page-context evidence. Use the attached image to confirm or correct it.\n"
        "Decide whether this slot must use a canonical product reference image when adapting the slot into a new swipe-based ad image.\n"
        "Use the visual image itself plus the slot's nearby copy and page position.\n\n"
        "Decision rules:\n"
        "- renderMode=requires_reference only when the adapted output must preserve recognizable product identity.\n"
        "- renderMode=context_only when Gemini can generate a relevant replacement from the section meaning alone.\n"
        "- shouldUseProductReference=true only when the actual product identity must stay recognizable in the adapted output.\n"
        "- shouldUseProductReference must exactly match renderMode: requires_reference=true, context_only=false.\n"
        "- Use referenceProminence=primary when the product itself should be the main visual subject.\n"
        "- Use referenceProminence=secondary when the product should appear but not dominate.\n"
        "- Use referenceProminence=none when the slot should not use product reference imagery.\n"
        "- referenceProminence must be none when renderMode=context_only.\n"
        "- isProductReferenceCandidate=true only if this image itself is a strong canonical product identity reference.\n"
        "- candidateStrength=primary only for the best, clearest product identity images.\n"
        "- visualGoal must be one short sentence describing what the new image should communicate visually.\n"
        "- Logos, icons, decorative textures, trust badges, screenshots, and generic lifestyle/supporting visuals are not product reference candidates.\n"
        "- If the evidence is ambiguous, set status=needs_review.\n"
        "- Keep reason to one short sentence under 160 characters.\n\n"
        "Return JSON only.\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _validate_slot_analysis_consistency(analysis: PageFlySlotAnalysis) -> None:
    expected_reference_usage = analysis.render_mode == "requires_reference"
    if analysis.should_use_product_reference != expected_reference_usage:
        raise RuntimeError(
            "PageFly planner returned inconsistent reference usage. "
            f"slot_id={analysis.slot_id} render_mode={analysis.render_mode} "
            f"shouldUseProductReference={analysis.should_use_product_reference}"
        )
    if analysis.render_mode == "context_only" and analysis.reference_prominence != "none":
        raise RuntimeError(
            "PageFly planner returned invalid context_only referenceProminence. "
            f"slot_id={analysis.slot_id} referenceProminence={analysis.reference_prominence}"
        )
    if analysis.render_mode == "requires_reference" and analysis.reference_prominence == "none":
        raise RuntimeError(
            "PageFly planner returned invalid requires_reference referenceProminence=none. "
            f"slot_id={analysis.slot_id}"
        )
    if analysis.is_product_reference_candidate and analysis.candidate_strength == "none":
        raise RuntimeError(
            "PageFly planner marked a slot as a reference candidate without candidateStrength. "
            f"slot_id={analysis.slot_id}"
        )
    if not analysis.is_product_reference_candidate and analysis.candidate_strength != "none":
        raise RuntimeError(
            "PageFly planner returned candidateStrength for a non-reference candidate slot. "
            f"slot_id={analysis.slot_id} candidateStrength={analysis.candidate_strength}"
        )


def _build_reconciliation_prompt(
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    page_outline: list[dict[str, Any]],
    slot_analyses: list[dict[str, Any]],
) -> str:
    payload = {
        "brandName": brand_name,
        "productName": product_name,
        "angle": angle,
        "hook": hook,
        "pageOutline": page_outline,
        "slotAnalyses": slot_analyses,
    }
    return (
        "Reconcile the slot-level product-reference decisions across the full PageFly page.\n\n"
        "Your job:\n"
        "- Pick the best canonical product reference slot ids for this page.\n"
        "- Ensure repeated or similar sections are treated consistently.\n"
        "- Return a slot decision for every slot id.\n"
        "- If a slot probably needs product identity but the evidence is weak, mark that slot as needs_review.\n"
        "- Keep referenceSlotIds limited to the clearest 1-3 canonical product identity images.\n"
        "- Keep every reason to one short sentence under 160 characters.\n\n"
        "Return JSON only.\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def plan_pagefly_product_references(
    *,
    model: str,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    slots: list[PageFlyImageSlot],
) -> PageFlySlotPlanningResult:
    if not slots:
        raise ValueError("No PageFly slots were provided for product-reference planning.")

    page_outline = _page_outline(slots)
    analyses_by_slot: dict[str, PageFlySlotAnalysis] = {}
    ordered_sections: list[tuple[str, list[PageFlyImageSlot]]] = []
    section_slots_by_id: dict[str, list[PageFlyImageSlot]] = {}
    for slot in slots:
        section_id = slot.section_root_id or slot.slot_id
        if section_id not in section_slots_by_id:
            section_slots_by_id[section_id] = []
            ordered_sections.append((section_id, section_slots_by_id[section_id]))
        section_slots_by_id[section_id].append(slot)

    for section_id, section_slots in ordered_sections:
        planning_parsed = _call_legacy_gemini_json(
            model=model,
            prompt=_build_section_planning_prompt(
                brand_name=brand_name,
                product_name=product_name,
                angle=angle,
                hook=hook,
                section_slots=section_slots,
                page_outline=page_outline,
            ),
            max_tokens=8000,
            temperature=0.0,
        )
        planning = PageFlyPlanningResponse.model_validate(planning_parsed)
        expected_slot_ids = {slot.slot_id for slot in section_slots}
        returned_slot_ids = {analysis.slot_id for analysis in planning.analyses}
        if returned_slot_ids != expected_slot_ids:
            missing = sorted(expected_slot_ids - returned_slot_ids)
            extra = sorted(returned_slot_ids - expected_slot_ids)
            raise RuntimeError(
                "PageFly section planning response returned the wrong slot ids. "
                f"section_id={section_id} missing={missing} extra={extra}"
            )
        for analysis in planning.analyses:
            _validate_slot_analysis_consistency(analysis)
            if analysis.slot_id in analyses_by_slot:
                raise RuntimeError(f"Duplicate PageFly slot analysis for slot {analysis.slot_id}")
            analyses_by_slot[analysis.slot_id] = analysis

    missing_analyses = sorted({slot.slot_id for slot in slots} - set(analyses_by_slot.keys()))
    extra_analyses = sorted(set(analyses_by_slot.keys()) - {slot.slot_id for slot in slots})
    if missing_analyses or extra_analyses:
        raise RuntimeError(
            "PageFly planning response returned the wrong slot ids. "
            f"missing={missing_analyses} extra={extra_analyses}"
        )

    decisions_by_slot: dict[str, PageFlySlotDecision] = {}
    for slot in slots:
        analysis = analyses_by_slot[slot.slot_id]
        slot.analysis = analysis
        decision = PageFlySlotDecision.model_validate(
            {
                "slotId": analysis.slot_id,
                "renderMode": analysis.render_mode,
                "shouldUseProductReference": analysis.should_use_product_reference,
                "referenceProminence": analysis.reference_prominence,
                "visualGoal": analysis.visual_goal,
                "status": analysis.status,
                "reason": analysis.reason,
            }
        )
        decisions_by_slot[decision.slot_id] = decision
        slot.decision = decision

    reference_slot_candidates = [
        slot
        for slot in slots
        if slot.analysis is not None
        and slot.analysis.is_product_reference_candidate
        and slot.analysis.candidate_strength in {"primary", "supporting", "secondary"}
    ]
    reference_slot_candidates.sort(
        key=lambda slot: (
            0 if slot.analysis and slot.analysis.candidate_strength == "primary" else 1,
            slot.root_order,
            slot.slot_id,
        )
    )
    derived_reference_slot_ids = [slot.slot_id for slot in reference_slot_candidates[:_MAX_REFERENCE_SLOTS]]
    derived_notes = [
        "Hybrid generation plan was derived from section-level Gemini page-context analysis.",
        "Reference slot ids were derived from page-context candidateStrength outputs.",
    ]
    reconciliation = PageFlyReconciliation.model_validate(
        {
            "referenceSlotIds": derived_reference_slot_ids,
            "slotDecisions": [
                decision.model_dump(mode="json", by_alias=True) for decision in decisions_by_slot.values()
            ],
            "notes": derived_notes,
        }
    )

    reference_slots: list[PageFlyImageSlot] = []
    seen_reference_slot_ids: set[str] = set()
    for slot_id in reconciliation.reference_slot_ids[:_MAX_REFERENCE_SLOTS]:
        if slot_id in seen_reference_slot_ids:
            continue
        seen_reference_slot_ids.add(slot_id)
        matching = [slot for slot in slots if slot.slot_id == slot_id]
        if not matching:
            raise RuntimeError(f"PageFly reconciliation returned an unknown reference slot id: {slot_id}")
        reference_slots.append(matching[0])

    return PageFlySlotPlanningResult(
        slots=slots,
        reconciliation=reconciliation,
        reference_slots=reference_slots,
    )
