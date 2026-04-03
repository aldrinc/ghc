from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


MAX_HTML_REFERENCE_CHARS = 250_000
MAX_HTML_PREVIEW_CHARS = 2_000
MAX_TEXT_PREVIEW_CHARS = 1_200
MAX_SECTION_ORDER_ITEMS = 20
MAX_HEADINGS = 20
MAX_CTA_TEXTS = 16
MAX_FAQ_QUESTIONS = 12
MAX_LANDMARKS = 12
MAX_IMAGE_ALT_TEXTS = 12
MAX_FORM_FIELD_HINTS = 16
MAX_VISIBLE_TEXT_CHUNKS = 120

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_CTA_KEYWORDS = (
    "add to cart",
    "buy",
    "claim",
    "checkout",
    "continue",
    "discover",
    "download",
    "get",
    "join",
    "learn",
    "order",
    "read",
    "see",
    "shop",
    "start",
    "subscribe",
    "try",
    "unlock",
    "view",
)
_PROOF_KEYWORD_SIGNALS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("review", "reviews", "rated", "rating", "stars", "star"), "Reviews / ratings"),
    (("testimonial", "testimonials", "success stories"), "Testimonials"),
    (("guarantee", "money back", "refund"), "Guarantee / refund"),
    (("shipping", "delivery"), "Shipping"),
    (("trusted", "featured", "as seen"), "Trust badges / press"),
    (("faq", "questions"), "FAQ"),
)
_GENERIC_SECTION_WORDS = {
    "app",
    "body",
    "card",
    "col",
    "column",
    "container",
    "content",
    "grid",
    "inner",
    "layout",
    "main",
    "module",
    "page",
    "panel",
    "root",
    "row",
    "section",
    "shell",
    "wrapper",
}


class HtmlReferenceError(ValueError):
    pass


class HtmlReferenceHeading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=1, le=6)
    text: str = Field(min_length=1, max_length=240)


class HtmlReferenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = Field(default=None, max_length=200)
    sha256: str = Field(min_length=64, max_length=64)
    characterCount: int = Field(ge=1)
    title: Optional[str] = Field(default=None, max_length=240)
    metaDescription: Optional[str] = Field(default=None, max_length=320)
    sectionOrder: list[str] = Field(default_factory=list)
    headings: list[HtmlReferenceHeading] = Field(default_factory=list)
    ctaTexts: list[str] = Field(default_factory=list)
    faqQuestions: list[str] = Field(default_factory=list)
    proofSignals: list[str] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    imageCount: int = Field(ge=0)
    imageAltTexts: list[str] = Field(default_factory=list)
    formCount: int = Field(ge=0)
    formFieldHints: list[str] = Field(default_factory=list)
    textPreview: str = Field(default="", max_length=MAX_TEXT_PREVIEW_CHARS)
    htmlPreview: str = Field(default="", max_length=MAX_HTML_PREVIEW_CHARS)


@dataclass
class _CaptureState:
    tag: str
    attrs: dict[str, str]
    parts: list[str]


class _HtmlReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title: str | None = None
        self.meta_description: str | None = None
        self.meta_title: str | None = None
        self.headings: list[HtmlReferenceHeading] = []
        self.interactions: list[dict[str, str | None]] = []
        self.landmarks: list[str] = []
        self.section_candidates: list[str] = []
        self.image_count = 0
        self.image_alt_texts: list[str] = []
        self.form_count = 0
        self.form_field_hints: list[str] = []
        self.visible_text_chunks: list[str] = []
        self._capture_stack: list[_CaptureState] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attrs_dict = {str(key).lower(): (value or "").strip() for key, value in attrs}

        if normalized_tag in {"script", "style", "noscript", "template", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth > 0:
            return

        if normalized_tag in {"title", "a", "button", "summary", "label", "legend", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._capture_stack.append(_CaptureState(tag=normalized_tag, attrs=attrs_dict, parts=[]))

        if normalized_tag == "meta":
            self._handle_meta(attrs_dict)
        elif normalized_tag == "img":
            self.image_count += 1
            alt_text = _clip_text(attrs_dict.get("alt"), max_length=180)
            if alt_text:
                self.image_alt_texts.append(alt_text)
        elif normalized_tag == "form":
            self.form_count += 1
        elif normalized_tag in {"input", "textarea", "select"}:
            hint = _field_hint(attrs_dict)
            if hint:
                self.form_field_hints.append(hint)

        if normalized_tag in {"header", "main", "nav", "footer", "aside"}:
            descriptor = _landmark_descriptor(normalized_tag, attrs_dict)
            if descriptor:
                self.landmarks.append(descriptor)
        elif normalized_tag in {"section", "article"}:
            candidate = _section_candidate_label(attrs_dict)
            if candidate:
                self.section_candidates.append(candidate)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript", "template", "svg"}:
            if self.skip_depth > 0:
                self.skip_depth -= 1
            return
        if self.skip_depth > 0:
            return
        if not self._capture_stack or self._capture_stack[-1].tag != normalized_tag:
            return

        capture = self._capture_stack.pop()
        text = _clip_text(" ".join(capture.parts), max_length=240)
        if not text:
            return

        if normalized_tag == "title":
            if self.title is None:
                self.title = text
            return

        if normalized_tag.startswith("h") and len(normalized_tag) == 2 and normalized_tag[1].isdigit():
            if len(self.headings) < MAX_HEADINGS:
                self.headings.append(HtmlReferenceHeading(level=int(normalized_tag[1]), text=text))
            return

        if normalized_tag in {"a", "button", "summary", "label", "legend"}:
            self.interactions.append(
                {
                    "tag": normalized_tag,
                    "text": text,
                    "href": capture.attrs.get("href"),
                }
            )

    def handle_data(self, data: str) -> None:
        if self.skip_depth > 0:
            return
        cleaned = _clip_text(data, max_length=240)
        if not cleaned:
            return
        if len(self.visible_text_chunks) < MAX_VISIBLE_TEXT_CHUNKS:
            if not self.visible_text_chunks or self.visible_text_chunks[-1] != cleaned:
                self.visible_text_chunks.append(cleaned)
        for capture in self._capture_stack:
            capture.parts.append(cleaned)

    def error(self, message: str) -> None:  # pragma: no cover - html.parser callback
        raise HtmlReferenceError(message)

    def _handle_meta(self, attrs_dict: dict[str, str]) -> None:
        content = _clip_text(attrs_dict.get("content"), max_length=320)
        if not content:
            return
        name = (attrs_dict.get("name") or attrs_dict.get("property") or attrs_dict.get("itemprop") or "").lower()
        if not name:
            return
        if name in {"description", "og:description", "twitter:description"} and self.meta_description is None:
            self.meta_description = content
        elif name in {"og:title", "twitter:title"} and self.meta_title is None:
            self.meta_title = _clip_text(content, max_length=240)


def summarize_html_reference(*, reference_html: str, label: str | None = None) -> HtmlReferenceSummary:
    normalized_html = str(reference_html or "").strip()
    if not normalized_html:
        raise HtmlReferenceError("HTML reference must be a non-empty string.")
    if len(normalized_html) > MAX_HTML_REFERENCE_CHARS:
        raise HtmlReferenceError(
            f"HTML reference exceeds the {MAX_HTML_REFERENCE_CHARS:,}-character limit."
        )

    parser = _HtmlReferenceParser()
    parser.feed(normalized_html)
    parser.close()

    headings = _unique_headings(parser.headings)
    section_order = _derive_section_order(headings=headings, section_candidates=parser.section_candidates)
    cta_texts = _derive_cta_texts(parser.interactions)
    faq_questions = _derive_faq_questions(headings=headings, interactions=parser.interactions)
    proof_signals = _derive_proof_signals(
        headings=headings,
        interactions=parser.interactions,
        visible_text_chunks=parser.visible_text_chunks,
    )
    landmarks = _unique_texts(parser.landmarks, max_items=MAX_LANDMARKS)
    image_alt_texts = _unique_texts(parser.image_alt_texts, max_items=MAX_IMAGE_ALT_TEXTS)
    form_field_hints = _unique_texts(parser.form_field_hints, max_items=MAX_FORM_FIELD_HINTS)
    text_preview = _build_text_preview(parser.visible_text_chunks)
    title = parser.title or parser.meta_title

    if not any(
        [
            title,
            parser.meta_description,
            section_order,
            cta_texts,
            text_preview,
        ]
    ):
        raise HtmlReferenceError(
            "HTML reference did not contain enough visible content to guide funnel generation."
        )

    return HtmlReferenceSummary(
        label=_clip_text(label, max_length=200),
        sha256=hashlib.sha256(normalized_html.encode("utf-8")).hexdigest(),
        characterCount=len(normalized_html),
        title=_clip_text(title, max_length=240),
        metaDescription=_clip_text(parser.meta_description, max_length=320),
        sectionOrder=section_order,
        headings=headings,
        ctaTexts=cta_texts,
        faqQuestions=faq_questions,
        proofSignals=proof_signals,
        landmarks=landmarks,
        imageCount=parser.image_count,
        imageAltTexts=image_alt_texts,
        formCount=parser.form_count,
        formFieldHints=form_field_hints,
        textPreview=text_preview,
        htmlPreview=normalized_html[:MAX_HTML_PREVIEW_CHARS],
    )


def build_html_reference_prompt_context(summary: HtmlReferenceSummary | dict[str, Any]) -> dict[str, Any]:
    source = summary if isinstance(summary, HtmlReferenceSummary) else HtmlReferenceSummary.model_validate(summary)
    return {
        "label": source.label,
        "sha256": source.sha256,
        "title": source.title,
        "metaDescription": source.metaDescription,
        "sectionOrder": source.sectionOrder,
        "headings": [heading.model_dump(mode="json") for heading in source.headings[:12]],
        "ctaTexts": source.ctaTexts,
        "faqQuestions": source.faqQuestions,
        "proofSignals": source.proofSignals,
        "landmarks": source.landmarks,
        "imageCount": source.imageCount,
        "imageAltTexts": source.imageAltTexts[:8],
        "formCount": source.formCount,
        "formFieldHints": source.formFieldHints[:8],
        "textPreview": source.textPreview,
    }


def describe_html_reference_input(*, reference_html: str | None, label: str | None = None) -> dict[str, Any] | None:
    normalized_html = str(reference_html or "").strip()
    if not normalized_html:
        return None
    return {
        "label": _clip_text(label, max_length=200),
        "sha256": hashlib.sha256(normalized_html.encode("utf-8")).hexdigest(),
        "characterCount": len(normalized_html),
    }


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def _clip_text(value: str | None, *, max_length: int) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


def _normalize_label_token(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    candidate = _NON_ALNUM_RE.sub(" ", cleaned.lower()).strip()
    if not candidate:
        return None
    parts = [part for part in candidate.split() if part and part not in _GENERIC_SECTION_WORDS]
    if not parts:
        return None
    return " ".join(parts[:5]).title()


def _landmark_descriptor(tag: str, attrs_dict: dict[str, str]) -> str | None:
    label = _normalize_label_token(
        attrs_dict.get("aria-label")
        or attrs_dict.get("id")
        or attrs_dict.get("data-testid")
        or attrs_dict.get("class")
    )
    if label:
        return f"{tag}:{label}"
    return tag


def _section_candidate_label(attrs_dict: dict[str, str]) -> str | None:
    return _normalize_label_token(
        attrs_dict.get("aria-label")
        or attrs_dict.get("id")
        or attrs_dict.get("data-testid")
        or attrs_dict.get("class")
    )


def _field_hint(attrs_dict: dict[str, str]) -> str | None:
    field_type = _clean_text(attrs_dict.get("type")) or "text"
    label = _clip_text(
        attrs_dict.get("aria-label")
        or attrs_dict.get("placeholder")
        or attrs_dict.get("name")
        or attrs_dict.get("id"),
        max_length=80,
    )
    if label:
        return f"{field_type}: {label}"
    return _clip_text(field_type, max_length=80)


def _unique_texts(values: list[str], *, max_items: int) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _clip_text(raw, max_length=240)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(text)
        if len(results) >= max_items:
            break
    return results


def _unique_headings(headings: list[HtmlReferenceHeading]) -> list[HtmlReferenceHeading]:
    results: list[HtmlReferenceHeading] = []
    seen: set[tuple[int, str]] = set()
    for heading in headings:
        key = (heading.level, heading.text.lower())
        if key in seen:
            continue
        seen.add(key)
        results.append(heading)
        if len(results) >= MAX_HEADINGS:
            break
    return results


def _derive_section_order(
    *,
    headings: list[HtmlReferenceHeading],
    section_candidates: list[str],
) -> list[str]:
    ordered: list[str] = []
    for heading in headings:
        if heading.level > 3:
            continue
        normalized = _clip_text(heading.text, max_length=240)
        if normalized and normalized.lower() not in {value.lower() for value in ordered}:
            ordered.append(normalized)
        if len(ordered) >= MAX_SECTION_ORDER_ITEMS:
            return ordered
    for candidate in _unique_texts(section_candidates, max_items=MAX_SECTION_ORDER_ITEMS):
        if candidate.lower() in {value.lower() for value in ordered}:
            continue
        ordered.append(candidate)
        if len(ordered) >= MAX_SECTION_ORDER_ITEMS:
            break
    return ordered


def _is_cta_text(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in _CTA_KEYWORDS):
        return True
    return len(text) <= 36 and len(text.split()) <= 6


def _derive_cta_texts(interactions: list[dict[str, str | None]]) -> list[str]:
    ctas: list[str] = []
    seen: set[str] = set()
    for item in interactions:
        text = _clip_text(item.get("text"), max_length=120)
        if not text or not _is_cta_text(text):
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ctas.append(text)
        if len(ctas) >= MAX_CTA_TEXTS:
            break
    return ctas


def _derive_faq_questions(
    *,
    headings: list[HtmlReferenceHeading],
    interactions: list[dict[str, str | None]],
) -> list[str]:
    questions: list[str] = []
    seen: set[str] = set()

    def _append(text: str | None) -> None:
        clipped = _clip_text(text, max_length=200)
        if not clipped:
            return
        lowered = clipped.lower()
        if lowered in seen:
            return
        seen.add(lowered)
        questions.append(clipped)

    for heading in headings:
        if "faq" in heading.text.lower() and len(questions) < MAX_FAQ_QUESTIONS:
            _append(heading.text)
        if heading.text.endswith("?") and len(questions) < MAX_FAQ_QUESTIONS:
            _append(heading.text)
    for item in interactions:
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if text.endswith("?") or "faq" in text.lower():
            _append(text)
        if len(questions) >= MAX_FAQ_QUESTIONS:
            break
    return questions[:MAX_FAQ_QUESTIONS]


def _derive_proof_signals(
    *,
    headings: list[HtmlReferenceHeading],
    interactions: list[dict[str, str | None]],
    visible_text_chunks: list[str],
) -> list[str]:
    corpus = " ".join(
        [
            *(heading.text for heading in headings),
            *(str(item.get("text") or "") for item in interactions[:24]),
            *visible_text_chunks[:40],
        ]
    ).lower()
    signals: list[str] = []
    for keywords, label in _PROOF_KEYWORD_SIGNALS:
        if any(keyword in corpus for keyword in keywords):
            signals.append(label)
    return signals


def _build_text_preview(chunks: list[str]) -> str:
    preview_parts: list[str] = []
    current_length = 0
    seen: set[str] = set()
    for chunk in chunks:
        cleaned = _clip_text(chunk, max_length=180)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        separator = " " if preview_parts else ""
        projected_length = current_length + len(separator) + len(cleaned)
        if projected_length > MAX_TEXT_PREVIEW_CHARS:
            remaining = MAX_TEXT_PREVIEW_CHARS - current_length - len(separator)
            if remaining > 12:
                clipped = _clip_text(cleaned, max_length=remaining)
                if clipped:
                    preview_parts.append(separator + clipped if separator else clipped)
            break
        preview_parts.append(separator + cleaned if separator else cleaned)
        current_length = projected_length
    return "".join(preview_parts)
