from __future__ import annotations

import base64
import concurrent.futures
import copy
import io
import json
import os
import random
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional, cast
from uuid import uuid4

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import SessionLocal
from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum
from app.db.models import Asset, Funnel, FunnelPage, FunnelPageVersion, Product
from app.llm.client import LLMClient, LLMGenerationParams
from app.services.funnels import create_funnel_image_asset, create_funnel_upload_asset
from app.services.funnel_ai import _load_product_context
from app.services.claude_files import call_claude_structured_message
from app.services.funnel_metadata import normalize_public_page_metadata_for_context
from app.services.funnels import _walk_json as walk_json
from app.services.media_storage import MediaStorage
from app.testimonial_renderer.renderer import ThreadedTestimonialRenderer
from app.testimonial_renderer.validate import TestimonialRenderError


class TestimonialGenerationError(RuntimeError):
    pass


class TestimonialGenerationNotFoundError(RuntimeError):
    pass


@dataclass
class _ConfigContext:
    props: dict[str, Any]
    key: str
    parsed: dict[str, Any]
    dirty: bool = False


@dataclass
class _TestimonialRenderTarget:
    image: dict[str, Any]
    label: str
    template: str
    context: _ConfigContext | None = None


@dataclass
class _TestimonialGroup:
    label: str
    renders: list[_TestimonialRenderTarget]
    slide: dict[str, Any] | None = None
    context: _ConfigContext | None = None


@dataclass
class _SalesPdpCarouselTarget:
    image: dict[str, Any]
    label: str
    slot_index: int
    context: _ConfigContext | None = None


_DATE_FORMAT = "%Y-%m-%d"
_TESTIMONIAL_TEMPLATES = {"review_card", "social_comment", "testimonial_media"}
_REVIEW_WALL_SOCIAL_RATIO = 0.60
_REVIEW_WALL_REVIEW_RATIO = 0.40
_SOCIAL_CARD_VARIANTS = ("social_comment", "social_comment_instagram", "social_comment_no_header")
_POV_OPTIONS = ("front-camera selfie", "rear-camera observer")
_SCENE_MODE_WITH_PEOPLE = "with_people"
_SCENE_MODE_NO_PEOPLE = "no_people"
_MEDIA_SCENE_MODE_CYCLE = (
    _SCENE_MODE_WITH_PEOPLE,
    _SCENE_MODE_NO_PEOPLE,
    _SCENE_MODE_NO_PEOPLE,
)
_SINGLE_SCENE_MODE_CYCLE = (_SCENE_MODE_WITH_PEOPLE, _SCENE_MODE_NO_PEOPLE)
_MAX_TESTIMONIAL_IDENTITY_ATTEMPTS = int(os.getenv("FUNNEL_TESTIMONIAL_IDENTITY_ATTEMPTS", "1"))
_TESTIMONIAL_ASSET_MAX_CONCURRENCY = max(1, settings.FUNNEL_IMAGE_GENERATION_MAX_CONCURRENCY)
_TESTIMONIAL_RENDER_WORKERS = max(1, int(os.getenv("FUNNEL_TESTIMONIAL_RENDER_WORKERS", "2")))
_TESTIMONIAL_RENDER_RESPONSE_TIMEOUT_MS = max(
    30_000, int(os.getenv("FUNNEL_TESTIMONIAL_RENDER_RESPONSE_TIMEOUT_MS", "90000"))
)
_TESTIMONIAL_CLAUDE_STRUCTURED_TIMEOUT_SECONDS = max(
    30, int(os.getenv("FUNNEL_TESTIMONIAL_CLAUDE_STRUCTURED_TIMEOUT_SECONDS", "240"))
)
_TESTIMONIAL_CLAUDE_STRUCTURED_MAX_ATTEMPTS = max(
    1, int(os.getenv("FUNNEL_TESTIMONIAL_CLAUDE_STRUCTURED_MAX_ATTEMPTS", "2"))
)
_SALES_PDP_CAROUSEL_CORE_SLOT_INDEX = 0
_SALES_PDP_CAROUSEL_VARIANTS: tuple[dict[str, str], ...] = (
    {
        "variantId": "standard_ugc",
        "template": "pdp_ugc_standard",
        "sampleInput": "testimonial-renderer/samples/inputs/pdp_example1_standard_ugc_nano.json",
        "archetype": "candid customer selfie with product clearly visible and believable everyday context.",
    },
    {
        "variantId": "qa_ugc",
        "template": "pdp_qa_ugc",
        "sampleInput": "testimonial-renderer/samples/inputs/pdp_example2_qa_nano.json",
        "archetype": "question-answer vibe where customer points to the product while reacting to a concern/objection.",
    },
    {
        "variantId": "bold_claim",
        "template": "pdp_bold_claim",
        "sampleInput": "testimonial-renderer/samples/inputs/pdp_example3_bold_claim_nano.json",
        "archetype": "product-forward frame with strong but compliant social-proof style comment.",
    },
    {
        "variantId": "personal_highlight",
        "template": "pdp_personal_highlight",
        "sampleInput": "testimonial-renderer/samples/inputs/pdp_example4_personal_highlight_nano.json",
        "archetype": "personal highlight moment showing the customer and product together.",
    },
    {
        "variantId": "dorm_selfie",
        "template": "pdp_ugc_standard",
        "sampleInput": "testimonial-renderer/samples/inputs/pdp_example5_dorm_selfie_nano.json",
        "archetype": "younger smartphone selfie vibe in a lived-in room, messy and authentic (not polished).",
    },
)
_SALES_PDP_CAROUSEL_TOTAL_SLOTS = 1 + len(_SALES_PDP_CAROUSEL_VARIANTS)
_SALES_PDP_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _clean_single_line(text: str) -> str:
    return " ".join(text.strip().split())


def _truncate(text: str, *, limit: int) -> str:
    compact = _clean_single_line(text)
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_DISALLOWED_NAME_SUFFIX_RE = re.compile(r"\(\d+\)\s*$")
_TOPIC_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "was",
    "were",
    "are",
    "have",
    "has",
    "had",
    "but",
    "not",
    "you",
    "your",
    "i",
    "im",
    "ive",
    "its",
    "it's",
    "they",
    "them",
    "their",
    "our",
    "we",
    "me",
    "my",
    "so",
    "just",
    "very",
    "really",
    "also",
    "from",
    "than",
    "then",
    "into",
    "over",
    "after",
    "before",
    "when",
    "while",
    "because",
    "been",
    "will",
    "would",
    "could",
    "should",
    "can",
    "cant",
    "can't",
    "did",
    "does",
    "doing",
    "use",
    "using",
    "used",
    "make",
    "made",
    "get",
    "got",
    "one",
    "two",
    "three",
    "product",
}


def _derive_review_title(review: str) -> str:
    compact = _clean_single_line(review)
    if not compact:
        return "Review"

    cutoff = None
    for sep in (".", "!", "?"):
        idx = compact.find(sep)
        if idx != -1 and idx >= 18:
            cutoff = idx
            break
    if cutoff is not None:
        compact = compact[:cutoff].strip()

    words = compact.split()
    title = " ".join(words[:8]).strip()
    if not title:
        return "Review"
    if len(title) > 80:
        title = title[:80].rstrip()
    return title


def _extract_topics(reviews: list[str], *, limit: int = 12) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """
    Deterministic topic extraction for synthetic reviews.

    Returns:
    - topics: list of {id,label,count}
    - per-review topicIds (subset of topic ids)
    """

    counts: Counter[str] = Counter()
    token_sets: list[set[str]] = []
    for review in reviews:
        tokens = [t.lower() for t in _WORD_RE.findall(review or "")]
        filtered = [t for t in tokens if t not in _TOPIC_STOPWORDS]
        token_set = set(filtered)
        token_sets.append(token_set)
        counts.update(filtered)

    top = [word for word, _ in counts.most_common(limit)]
    topics = [{"id": word, "label": word, "count": int(counts[word])} for word in top]

    per_review: list[list[str]] = []
    for token_set in token_sets:
        selected = [word for word in top if word in token_set][:4]
        per_review.append(selected)
    return topics, per_review


def _sync_sales_pdp_reviews_from_testimonials(
    puck_data: dict[str, Any],
    *,
    product: Product,
    validated_testimonials: list[dict[str, Any]],
    today: str,
    review_media_images: Optional[list[dict[str, Any]]] = None,
) -> None:
    if not validated_testimonials:
        return

    # Build a ReviewsResponse-compatible payload.
    review_texts = [t.get("review") or "" for t in validated_testimonials]
    topics, per_review_topic_ids = _extract_topics(review_texts, limit=12)

    reviews: list[dict[str, Any]] = []
    media_gallery: list[dict[str, Any]] = []
    rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total_rating = 0.0

    base_date = datetime.strptime(today, _DATE_FORMAT).date()
    for idx, t in enumerate(validated_testimonials):
        rating = int(t["rating"])
        rating_counts[rating] = rating_counts.get(rating, 0) + 1
        total_rating += float(rating)

        meta_date = None
        meta = t.get("meta")
        if isinstance(meta, dict):
            candidate = meta.get("date")
            if isinstance(candidate, str) and candidate.strip():
                meta_date = candidate.strip()
        if meta_date:
            created_at = f"{meta_date}T00:00:00.000Z"
        else:
            created_at = f"{(base_date - timedelta(days=idx)).isoformat()}T00:00:00.000Z"

        media: list[dict[str, Any]] = []
        if review_media_images and idx < len(review_media_images):
            image = review_media_images[idx]
            asset_public_id = image.get("assetPublicId")
            if isinstance(asset_public_id, str) and asset_public_id.strip():
                url = _public_asset_url(asset_public_id.strip())
                alt = image.get("alt") if isinstance(image.get("alt"), str) else None
                media_item = {
                    "id": f"review_media_{idx + 1}",
                    "type": "image",
                    "url": url,
                    **({"alt": alt} if alt else {}),
                }
                media.append(media_item)
                if len(media_gallery) < 8:
                    media_gallery.append({**media_item, "id": f"gallery_{idx + 1}"})

        reviews.append(
            {
                "id": f"synthetic_review_{idx + 1}",
                "rating": rating,
                "title": _derive_review_title(t["review"]),
                "body": t["review"],
                "createdAt": created_at,
                "author": {
                    "name": t["name"],
                    "verifiedBuyer": bool(t["verified"]),
                },
                **({"topicIds": per_review_topic_ids[idx]} if per_review_topic_ids[idx] else {}),
                **({"media": media} if media else {}),
                "helpfulCount": int(t["reply"]["reactionCount"]),
            }
        )

    total_reviews = len(reviews)
    avg = (total_rating / total_reviews) if total_reviews else 0.0
    breakdown = [{"rating": r, "count": int(rating_counts[r])} for r in (5, 4, 3, 2, 1)]
    customers_say = ""
    if topics:
        labels = [t["label"] for t in topics[:3]]
        if len(labels) >= 3:
            customers_say = f"Customers often mention {labels[0]}, {labels[1]}, and {labels[2]}."
        elif len(labels) == 2:
            customers_say = f"Customers often mention {labels[0]} and {labels[1]}."
        else:
            customers_say = f"Customers often mention {labels[0]}."
    else:
        customers_say = "Customers share positive experiences with the product."

    product_id = product.handle.strip() if isinstance(product.handle, str) and product.handle.strip() else str(product.id)

    page_size = 10
    total_pages = max(1, (total_reviews + page_size - 1) // page_size)

    response: dict[str, Any] = {
        "productId": product_id,
        "summary": {
            "averageRating": round(avg, 1),
            "totalReviews": total_reviews,
            "breakdown": breakdown,
            "customersSay": customers_say,
            "topics": topics,
            "mediaGallery": media_gallery,
        },
        "filters": {
            "ratings": [{"value": r, "label": str(r), "count": int(rating_counts[r])} for r in (5, 4, 3, 2, 1)],
            "countries": [],
            "sorts": [
                {"value": "most_recent", "label": "Most recent"},
                {"value": "highest_rating", "label": "Highest rating"},
                {"value": "lowest_rating", "label": "Lowest rating"},
                {"value": "most_helpful", "label": "Most helpful"},
            ],
        },
        "pagination": {
            "page": 1,
            "pageSize": page_size,
            "totalReviews": total_reviews,
            "totalPages": total_pages,
        },
        "reviews": reviews,
    }

    # Apply to any SalesPdpReviews blocks in the page puck data.
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "SalesPdpReviews":
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue

        raw = props.get("configJson")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise TestimonialGenerationError(
                    f"SalesPdpReviews.configJson must be valid JSON: {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise TestimonialGenerationError("SalesPdpReviews.configJson must decode to a JSON object.")
            if not isinstance(parsed.get("id"), str) or not parsed["id"].strip():
                raise TestimonialGenerationError("SalesPdpReviews.config.id must be a non-empty string.")
            parsed["data"] = response
            props["configJson"] = json.dumps(parsed, ensure_ascii=False)
            continue

        config = props.get("config")
        if not isinstance(config, dict):
            raise TestimonialGenerationError("SalesPdpReviews is missing config/configJson.")
        if not isinstance(config.get("id"), str) or not config["id"].strip():
            raise TestimonialGenerationError("SalesPdpReviews.config.id must be a non-empty string.")
        config["data"] = response


def _seed_value(*parts: str) -> int:
    value = 0
    for part in parts:
        for ch in part:
            value += ord(ch)
    return value


def _normalize_identity_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _assert_no_numeric_disambiguation_suffix(*, field_label: str, value: str) -> None:
    if _DISALLOWED_NAME_SUFFIX_RE.search(value):
        raise TestimonialGenerationError(
            f"{field_label} cannot use numeric disambiguation suffixes like '(2)'."
        )


def _assert_distinct_testimonial_identities(validated_testimonials: list[dict[str, Any]]) -> None:
    seen_names: dict[str, int] = {}
    seen_personas: dict[str, int] = {}

    def register_identity(*, label: str, raw_value: str, idx: int, seen: dict[str, int]) -> None:
        key = _normalize_identity_key(raw_value)
        if key in seen:
            prev = seen[key] + 1
            current = idx + 1
            raise TestimonialGenerationError(
                f"Duplicate testimonial {label} detected at positions {prev} and {current}: {raw_value!r}. "
                f"All testimonial {label}s must be distinct."
            )
        seen[key] = idx

    for idx, testimonial in enumerate(validated_testimonials):
        name = testimonial["name"]
        persona = testimonial["persona"]
        reply = testimonial["reply"]
        reply_name = reply["name"]
        reply_persona = reply["persona"]

        register_identity(label="name", raw_value=name, idx=idx, seen=seen_names)
        register_identity(label="persona", raw_value=persona, idx=idx, seen=seen_personas)
        register_identity(label="name", raw_value=reply_name, idx=idx, seen=seen_names)
        register_identity(label="persona", raw_value=reply_persona, idx=idx, seen=seen_personas)


def _repair_distinct_testimonial_identities(
    validated_testimonials: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    repaired = copy.deepcopy(validated_testimonials)

    def _normalize_space(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.strip().split())

    def _hint(value: Any, *, max_words: int = 4, max_len: int = 28) -> str | None:
        compact = _normalize_space(value)
        if not compact:
            return None
        compact = re.sub(r"[^A-Za-z0-9 '&-]", "", compact)
        if not compact:
            return None
        words = compact.split()
        if not words:
            return None
        return " ".join(words[:max_words])[:max_len].strip()

    def _candidate_name(base: str, hint_text: str) -> str:
        candidate = f"{base} ({hint_text})"
        if len(candidate) > 80:
            overflow = len(candidate) - 80
            trimmed_hint = hint_text[:-overflow].strip() if overflow < len(hint_text) else ""
            candidate = f"{base} ({trimmed_hint})" if trimmed_hint else base
        return candidate

    def _candidate_persona(base: str, hint_text: str) -> str:
        candidate = f"{base} | {hint_text}"
        if len(candidate) > 220:
            overflow = len(candidate) - 220
            trimmed_hint = hint_text[:-overflow].strip() if overflow < len(hint_text) else ""
            candidate = f"{base} | {trimmed_hint}" if trimmed_hint else base
        return candidate

    seen_names: set[str] = set()
    seen_personas: set[str] = set()

    for testimonial in repaired:
        reply = testimonial.get("reply")
        if not isinstance(reply, dict):
            return None

        base_name = _normalize_space(testimonial.get("name"))
        base_persona = _normalize_space(testimonial.get("persona"))
        reply_name = _normalize_space(reply.get("name"))
        reply_persona = _normalize_space(reply.get("persona"))
        if not base_name or not base_persona or not reply_name or not reply_persona:
            return None

        meta = testimonial.get("meta")
        location_hint = _hint(meta.get("location")) if isinstance(meta, dict) else None
        primary_name_hints = [
            location_hint,
            _hint(testimonial.get("persona"), max_words=3),
            _hint(reply.get("name"), max_words=2),
            _hint(reply.get("persona"), max_words=3),
            _hint(testimonial.get("review"), max_words=3),
        ]
        primary_persona_hints = [
            location_hint,
            _hint(testimonial.get("name"), max_words=3),
            _hint(reply.get("persona"), max_words=3),
            _hint(reply.get("name"), max_words=2),
        ]
        reply_name_hints = [
            location_hint,
            _hint(reply.get("persona"), max_words=3),
            _hint(testimonial.get("name"), max_words=2),
            _hint(testimonial.get("persona"), max_words=3),
        ]
        reply_persona_hints = [
            location_hint,
            _hint(reply.get("name"), max_words=2),
            _hint(testimonial.get("persona"), max_words=3),
            _hint(testimonial.get("name"), max_words=2),
        ]

        def _resolve_name(value: str, hints: list[str | None], seen: set[str]) -> str | None:
            normalized = _normalize_identity_key(value)
            if normalized not in seen:
                seen.add(normalized)
                return value
            for raw_hint in hints:
                if not raw_hint:
                    continue
                candidate = _candidate_name(value, raw_hint)
                candidate = _normalize_space(candidate)
                if not candidate:
                    continue
                try:
                    _assert_no_numeric_disambiguation_suffix(field_label="Testimonial name", value=candidate)
                except TestimonialGenerationError:
                    continue
                normalized_candidate = _normalize_identity_key(candidate)
                if normalized_candidate in seen:
                    continue
                seen.add(normalized_candidate)
                return candidate
            return None

        def _resolve_persona(value: str, hints: list[str | None], seen: set[str]) -> str | None:
            normalized = _normalize_identity_key(value)
            if normalized not in seen:
                seen.add(normalized)
                return value
            for raw_hint in hints:
                if not raw_hint:
                    continue
                candidate = _candidate_persona(value, raw_hint)
                candidate = _normalize_space(candidate)
                if not candidate:
                    continue
                normalized_candidate = _normalize_identity_key(candidate)
                if normalized_candidate in seen:
                    continue
                seen.add(normalized_candidate)
                return candidate
            return None

        resolved_name = _resolve_name(base_name, primary_name_hints, seen_names)
        resolved_persona = _resolve_persona(base_persona, primary_persona_hints, seen_personas)
        resolved_reply_name = _resolve_name(reply_name, reply_name_hints, seen_names)
        resolved_reply_persona = _resolve_persona(reply_persona, reply_persona_hints, seen_personas)
        if not resolved_name or not resolved_persona or not resolved_reply_name or not resolved_reply_persona:
            return None

        if _normalize_identity_key(resolved_name) == _normalize_identity_key(resolved_reply_name):
            return None
        if _normalize_identity_key(resolved_persona) == _normalize_identity_key(resolved_reply_persona):
            return None

        testimonial["name"] = resolved_name
        testimonial["persona"] = resolved_persona
        reply["name"] = resolved_reply_name
        reply["persona"] = resolved_reply_persona

    return repaired


def _select_pov(*parts: str) -> str:
    seed = _seed_value(*parts)
    return _POV_OPTIONS[seed % len(_POV_OPTIONS)]


def _derive_setting(*, validated: dict[str, Any], fallback_text: str) -> str:
    meta = validated.get("meta")
    if isinstance(meta, dict):
        location = meta.get("location")
        if isinstance(location, str) and location.strip():
            return _truncate(
                f"{location.strip()} with natural clutter, imperfect background details, and lived-in realism.",
                limit=220,
            )
    return _truncate(fallback_text, limit=220)


def _derive_action(*, primary_direction: str, review: str) -> str:
    combined = f"{primary_direction}. {review}"
    return _truncate(combined, limit=220)


def _select_media_scene_mode(index: int) -> str:
    if index < 0:
        raise TestimonialGenerationError("Media scene mode index cannot be negative.")
    return _MEDIA_SCENE_MODE_CYCLE[index % len(_MEDIA_SCENE_MODE_CYCLE)]


def _select_single_scene_mode(index: int) -> str:
    if index < 0:
        raise TestimonialGenerationError("Single scene mode index cannot be negative.")
    return _SINGLE_SCENE_MODE_CYCLE[index % len(_SINGLE_SCENE_MODE_CYCLE)]


def _select_social_comment_without_attachment_indices(total: int, *, seed: int) -> set[int]:
    if total < 0:
        raise TestimonialGenerationError("Social comment total cannot be negative.")
    if total <= 1:
        return set()
    desired = max(1, int(total * 0.25))
    desired = min(desired, total - 1)  # Ensure at least one comment keeps an attachment.
    rng = random.Random(seed)
    return set(rng.sample(range(total), desired))


def _select_review_card_without_hero_indices(total: int, *, seed: int) -> set[int]:
    if total < 0:
        raise TestimonialGenerationError("Review card total cannot be negative.")
    if total <= 1:
        return set()
    desired = max(1, int(total * 0.15))
    desired = min(desired, total - 1)  # Ensure at least one review keeps a hero image.
    rng = random.Random(seed)
    return set(rng.sample(range(total), desired))


def _build_product_image_prompt(
    *,
    render_label: str,
    persona: str,
    setting: str,
    action: str,
    direction: str,
    identity_name: str | None = None,
    identity_anchor: str | None = None,
    require_subject_match: bool = False,
    prohibit_visible_text: bool = True,
) -> str:
    pov = _select_pov(render_label, persona, setting, action, direction)
    identity_lines = ""
    if identity_name or identity_anchor:
        details = []
        if identity_name:
            details.append(f'name "{identity_name}"')
        if identity_anchor:
            details.append(f"identity cues: {identity_anchor}")
        identity_lines = (
            "IDENTITY ANCHOR: "
            + "; ".join(details)
            + ". "
            + (
                "If a human subject appears, it must be this same person and must not drift to a different ethnicity, age impression, facial structure, hair pattern, or body type.\n\n"
                if require_subject_match
                else "Maintain identity consistency if a human subject appears.\n\n"
            )
        )
    text_policy = (
        "TEXT POLICY: absolutely no visible text in the image. "
        "No captions, subtitles, labels, logos, UI overlays, timestamps, watermark text, or packaging text.\n\n"
        if prohibit_visible_text
        else ""
    )
    return (
        "VERTICAL 9:16 hyper-real smartphone photo, looks like an unplanned UGC shot (NOT cinematic).\n"
        f"POV: {pov}. Device: iPhone-style smartphone capture, slight shadow noise, realistic exposure behavior, natural color, no LUT.\n\n"
        f"SUBJECT/PERSONA: fictional person, {persona}. Natural skin texture, subtle under-eye detail, believable hair flyaways. "
        "Expression: candid, mid-thought, slightly imperfect (no \"model pose\").\n\n"
        f"{identity_lines}"
        f"SETTING: {setting}.\n\n"
        "COMPOSITION: slightly crooked framing, off-center crop, mild headroom error, shoulder/arm partly clipped if selfie. "
        "Distance feels like a real phone: ~30-60cm for selfie / ~1-2m for rear-cam. One minor autofocus pulse or slight motion blur is okay.\n\n"
        f"ACTION: {action}. Minimal gestures, no hands near lens.\n\n"
        f"{text_policy}"
        "REALISM LOCKS: realistic pores and fabric texture, natural room reflections, believable phone HDR (not extreme), no plastic skin, "
        "no perfect studio lighting, no hyper-sharp edges, no AI gloss.\n\n"
        "AVOID: extra fingers, warped hands, melted jewelry, duplicated facial features, over-smoothing, beauty filter, cinematic depth-of-field, "
        "heavy grain, over-saturated colors, perfect symmetry, influencer staging, fake lens flares, watermark, text artifacts, captions, subtitles, logos, UI text.\n\n"
        f"Direction: {direction}\n"
        "Output testimonial photo of the product attached following the prompt."
    )


def _build_non_user_ugc_prompt(
    *,
    render_label: str,
    persona: str,
    setting: str,
    action: str,
    direction: str,
    include_text_screen_line: bool,
    prohibit_visible_text: bool,
) -> str:
    pov = _select_pov(render_label, persona, setting, action, direction, "non_user")
    text_screen_line = (
        "IF TEXT/SCREEN IS VISIBLE (optional): show ONLY 1-2 lines of BIG high-contrast text, held steady, readable, "
        "no dense UI, no tiny legal text, no sensitive personal numbers. Keep prop 1.5-2 feet from camera.\n\n"
        if include_text_screen_line
        else ""
    )
    text_policy = (
        "TEXT POLICY: absolutely no visible text in the image. "
        "No captions, subtitles, labels, logos, UI overlays, timestamps, watermark text, or packaging text.\n\n"
        if prohibit_visible_text
        else ""
    )
    return (
        "VERTICAL 9:16 hyper-real smartphone photo, looks like an unplanned UGC shot (NOT cinematic).\n"
        f"POV: {pov}. Device: iPhone-style smartphone capture, slight shadow noise, realistic exposure behavior, natural color, no LUT.\n\n"
        f"STYLE CONTEXT: persona cues are allowed only for atmosphere ({persona}); do not depict any person.\n\n"
        "SUBJECT: the product and surrounding environment only.\n"
        "NO PEOPLE POLICY: absolutely no humans, faces, skin, hands, silhouettes, or reflected bodies in mirrors/glass.\n\n"
        f"SETTING: {setting}.\n\n"
        "COMPOSITION: candid handheld framing with mild imperfection, off-center crop, and realistic phone focus behavior. "
        "Keep the product clearly visible with supporting props only.\n\n"
        f"ACTION: {action}. Communicate use via product placement, environmental clues, or in-progress setup without showing any person.\n\n"
        f"{text_screen_line}"
        f"{text_policy}"
        "REALISM LOCKS: realistic material textures, natural room reflections, believable phone HDR (not extreme), "
        "no perfect studio lighting, no hyper-sharp edges, no AI gloss.\n\n"
        "AVOID: any human presence, hands, face reflections, beauty-filter look, cinematic depth-of-field, heavy grain, "
        "over-saturated colors, perfect symmetry, influencer staging, fake lens flares, watermark, text artifacts.\n\n"
        f"Direction: {direction}\n"
        "Output testimonial photo of the product attached following the prompt."
    )


def _build_testimonial_scene_prompt(
    *,
    scene_mode: str,
    render_label: str,
    persona: str,
    setting: str,
    action: str,
    direction: str,
    identity_name: str | None = None,
    identity_anchor: str | None = None,
    require_subject_match: bool = False,
    include_text_screen_line: bool = False,
    prohibit_visible_text: bool = True,
) -> str:
    if scene_mode == _SCENE_MODE_WITH_PEOPLE:
        return _build_product_image_prompt(
            render_label=render_label,
            persona=persona,
            setting=setting,
            action=action,
            direction=direction,
            identity_name=identity_name,
            identity_anchor=identity_anchor,
            require_subject_match=require_subject_match,
            prohibit_visible_text=prohibit_visible_text,
        )
    if scene_mode == _SCENE_MODE_NO_PEOPLE:
        return _build_non_user_ugc_prompt(
            render_label=render_label,
            persona=persona,
            setting=setting,
            action=action,
            direction=direction,
            include_text_screen_line=include_text_screen_line,
            prohibit_visible_text=prohibit_visible_text,
        )
    raise TestimonialGenerationError(f"Unsupported testimonial scene mode: {scene_mode}")


def _build_distinct_avatar_prompt(
    *,
    render_label: str,
    display_name: str,
    persona: str,
    direction: str,
    variant_label: str,
) -> str:
    pov = _select_pov(render_label, display_name, persona, direction, variant_label, "avatar")
    return (
        "SQUARE 1:1 hyper-real smartphone portrait photo, looks like an unplanned UGC profile shot (NOT cinematic).\n"
        f"POV: {pov}. Device: iPhone-style smartphone capture, realistic exposure behavior, natural color, no LUT.\n\n"
        f"SUBJECT/PERSONA: fictional person named {display_name}. {persona}\n"
        "Natural skin texture, subtle under-eye detail, believable hair flyaways, candid expression.\n\n"
        "COMPOSITION: tight head-and-shoulders framing, slight framing imperfection, casual real-world posture, not studio-lit.\n"
        "BACKGROUND: normal lived-in environment with mild blur from phone optics; no staged set dressing.\n\n"
        "TEXT POLICY: no visible text, logos, labels, or watermark overlays.\n\n"
        "REALISM LOCKS: believable pores, realistic skin tone, natural fabric detail, no beauty filter, no AI gloss.\n\n"
        "IDENTITY LOCKS: avatar must stay consistent with the provided name/persona cues and must not conflict with the described identity.\n"
        "Identity constraint: this must be a distinct person from any other avatar in this render set.\n\n"
        "AVOID: extra fingers, warped facial features, duplicated features, plastic skin, influencer glam styling, fake lens flares, watermark, text artifacts.\n\n"
        f"Direction: {direction}"
    )


def _load_reference_asset_bytes(asset: Asset) -> tuple[bytes, str]:
    if not asset.storage_key:
        raise TestimonialGenerationError("Product primary image asset is missing storage_key.")
    try:
        storage = MediaStorage()
        image_bytes, mime_type = storage.download_bytes(key=asset.storage_key)
    except Exception as exc:  # noqa: BLE001
        raise TestimonialGenerationError("Unable to load product primary image bytes.") from exc
    if not image_bytes:
        raise TestimonialGenerationError("Product primary image bytes are empty.")
    resolved_mime = mime_type or asset.content_type
    if not isinstance(resolved_mime, str) or not resolved_mime.strip():
        raise TestimonialGenerationError("Product primary image MIME type is required.")
    return image_bytes, resolved_mime.split(";")[0].strip()


def _square_center_crop_png(image_bytes: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgba = img.convert("RGBA")
            width, height = rgba.size
            if width <= 0 or height <= 0:
                raise TestimonialGenerationError("Source image has invalid dimensions.")
            side = min(width, height)
            left = (width - side) // 2
            top = (height - side) // 2
            square = rgba.crop((left, top, left + side, top + side))
            if square.size != (1080, 1080):
                resampling = getattr(Image, "Resampling", Image)
                square = square.resize((1080, 1080), resampling.LANCZOS)
            output = io.BytesIO()
            square.save(output, format="PNG", optimize=True)
            result = output.getvalue()
            if not result:
                raise TestimonialGenerationError("Square product image transform produced empty bytes.")
            return result
    except TestimonialGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TestimonialGenerationError(
            "Unable to convert product primary image into square carousel format."
        ) from exc


def _create_sales_pdp_square_core_asset(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    funnel_id: str,
    page_id: str,
    source_asset: Asset,
    source_alt: str,
    product_id: str | None,
) -> Asset:
    source_bytes, _ = _load_reference_asset_bytes(source_asset)
    square_png = _square_center_crop_png(source_bytes)
    return create_funnel_upload_asset(
        session=session,
        org_id=org_id,
        client_id=client_id,
        content_bytes=square_png,
        filename=f"sales-pdp-carousel-{page_id}-core-square.png",
        content_type="image/png",
        alt=source_alt,
        usage_context={
            "kind": "sales_pdp_carousel_core_square",
            "funnelId": funnel_id,
            "pageId": page_id,
            "sourceAssetId": str(source_asset.id),
            "sourcePublicId": str(source_asset.public_id),
        },
        funnel_id=funnel_id,
        product_id=product_id,
        tags=["funnel", "testimonial", "sales_pdp_carousel", "core_product_image", "square_core"],
    )


def _should_soft_fail_gemini_missing_inline_data(exc: BaseException) -> bool:
    """Treat Gemini 'no inline image data' responses as non-fatal in rendering flows.

    We do NOT treat quota (429) as soft-fail; that should surface clearly so credits/limits
    can be addressed in GCP. This only covers the case where Gemini returns 200 but doesn't
    include an output image payload (often with finishReason=MALFORMED_FUNCTION_CALL).
    """

    msg = str(exc).lower()
    if "status=429" in msg or "too many requests" in msg or "resource_exhausted" in msg:
        return False
    return "inline image data" in msg and ("did not include" in msg or "did not return" in msg)


def _wall_template_sequence(total: int) -> list[str]:
    if total < 0:
        raise TestimonialGenerationError("Review wall image count cannot be negative.")
    if total == 0:
        return []
    ratio_sum = _REVIEW_WALL_SOCIAL_RATIO + _REVIEW_WALL_REVIEW_RATIO
    if abs(ratio_sum - 1.0) > 1e-9:
        raise TestimonialGenerationError(
            "Review wall testimonial ratios must sum to 1.0."
        )
    social_target = int((total * _REVIEW_WALL_SOCIAL_RATIO) + 0.5)
    if social_target > total:
        raise TestimonialGenerationError("Computed social review wall target exceeds total slots.")
    review_target = total - social_target
    templates: list[str] = []
    social_assigned = 0
    review_assigned = 0
    for _ in range(total):
        social_progress = (
            social_assigned / social_target if social_target > 0 else float("inf")
        )
        review_progress = (
            review_assigned / review_target if review_target > 0 else float("inf")
        )
        if social_assigned < social_target and social_progress <= review_progress:
            templates.append("social_comment")
            social_assigned += 1
            continue
        if review_assigned < review_target:
            templates.append("review_card")
            review_assigned += 1
            continue
        raise TestimonialGenerationError("Unable to allocate testimonial template mix for review wall.")
    return templates


def _next_social_card_variant(index: int) -> str:
    if index < 0:
        raise TestimonialGenerationError("Social card variant index cannot be negative.")
    return _SOCIAL_CARD_VARIANTS[index % len(_SOCIAL_CARD_VARIANTS)]

def _require_public_asset_base_url() -> str:
    base_url = settings.PUBLIC_ASSET_BASE_URL
    if not isinstance(base_url, str) or not base_url.strip():
        raise TestimonialGenerationError(
            "PUBLIC_ASSET_BASE_URL is required to build public asset URLs."
        )
    return base_url.rstrip("/")


def _public_asset_url(public_id: str) -> str:
    base_url = _require_public_asset_base_url()
    return f"{base_url}/public/assets/{public_id}"


def _asset_data_url(asset: Asset) -> str:
    """
    Build a data: URL for an image asset by reading bytes directly from object storage.

    This avoids relying on PUBLIC_ASSET_BASE_URL/http fetches during Playwright rendering,
    which can be flaky in worker environments.
    """

    if not asset.storage_key:
        raise TestimonialGenerationError("Asset is missing storage_key (cannot build data URL).")
    storage = MediaStorage()
    data, content_type = storage.download_bytes(key=asset.storage_key)
    if not data:
        raise TestimonialGenerationError(
            f"Downloaded asset bytes are empty (publicId={asset.public_id})."
        )
    mime = (asset.content_type or content_type or "application/octet-stream").split(";")[0].strip()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@dataclass
class _GeneratedTestimonialAsset:
    public_id: str
    asset_id: str
    storage_key: str | None
    content_type: str | None


def _generated_testimonial_asset(asset: Asset) -> _GeneratedTestimonialAsset:
    return _GeneratedTestimonialAsset(
        public_id=str(asset.public_id),
        asset_id=str(asset.id),
        storage_key=asset.storage_key,
        content_type=asset.content_type,
    )


def _asset_data_url_from_generated(asset: _GeneratedTestimonialAsset) -> str:
    if not asset.storage_key:
        raise TestimonialGenerationError(
            "Generated testimonial asset is missing storage_key (cannot build data URL)."
        )
    storage = MediaStorage()
    data, content_type = storage.download_bytes(key=asset.storage_key)
    if not data:
        raise TestimonialGenerationError(
            f"Downloaded asset bytes are empty (publicId={asset.public_id})."
        )
    mime = (asset.content_type or content_type or "application/octet-stream").split(";")[0].strip()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _generate_testimonial_image_asset(
    *,
    org_id: str,
    client_id: str,
    prompt: str,
    aspect_ratio: Optional[str] = None,
    usage_context: Optional[dict[str, Any]] = None,
    reference_image_bytes: Optional[bytes] = None,
    reference_image_mime_type: Optional[str] = None,
    reference_asset_public_id: Optional[str] = None,
    reference_asset_id: Optional[str] = None,
    funnel_id: Optional[str] = None,
    product_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> _GeneratedTestimonialAsset:
    with SessionLocal() as thread_session:
        asset = create_funnel_image_asset(
            session=thread_session,
            org_id=org_id,
            client_id=client_id,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            usage_context=usage_context,
            reference_image_bytes=reference_image_bytes,
            reference_image_mime_type=reference_image_mime_type,
            reference_asset_public_id=reference_asset_public_id,
            reference_asset_id=reference_asset_id,
            funnel_id=funnel_id,
            product_id=product_id,
            tags=tags,
        )
        return _generated_testimonial_asset(asset)


def generate_shopify_theme_testimonial_image_asset(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    slot_path: str,
    payload: dict[str, Any],
    product_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    renderer: ThreadedTestimonialRenderer | None = None,
) -> Asset:
    normalized_slot_path = _clean_single_line(slot_path or "")
    if not normalized_slot_path:
        raise TestimonialGenerationError(
            "slot_path is required to generate a Shopify testimonial image asset."
        )
    if not isinstance(payload, dict) or not payload:
        raise TestimonialGenerationError(
            "payload is required to generate a Shopify testimonial image asset."
        )
    template = payload.get("template")
    if not isinstance(template, str) or template.strip() != "review_card":
        raise TestimonialGenerationError(
            "Shopify testimonial image generation currently supports review_card payloads only."
        )

    configured_image_model = str(settings.TESTIMONIAL_RENDERER_IMAGE_MODEL or "").strip()
    if not configured_image_model:
        raise TestimonialRenderError(
            "TESTIMONIAL_RENDERER_IMAGE_MODEL is required for Shopify testimonial image generation."
        )

    resolved_usage_context = {
        "kind": "shopify_theme_testimonial_render",
        "slotPath": normalized_slot_path,
        "source": "testimonial_renderer",
        "model": configured_image_model,
        "modelSource": "TESTIMONIAL_RENDERER_IMAGE_MODEL",
        "template": "review_card",
    }
    resolved_tags = [
        "shopify_theme_sync",
        "component_image",
        "testimonial",
        "testimonial_renderer",
    ]
    if isinstance(tags, list):
        for raw_tag in tags:
            if not isinstance(raw_tag, str):
                continue
            normalized_tag = raw_tag.strip()
            if not normalized_tag or normalized_tag in resolved_tags:
                continue
            resolved_tags.append(normalized_tag)

    if renderer is None:
        with ThreadedTestimonialRenderer() as active_renderer:
            render_bytes = active_renderer.render_png(payload)
    else:
        render_bytes = renderer.render_png(payload)

    reviewer_name = _clean_single_line(str(payload.get("name") or "Customer"))
    alt_text = f"Review from {reviewer_name}" if reviewer_name else "Customer review"
    return create_funnel_upload_asset(
        session=session,
        org_id=org_id,
        client_id=client_id,
        content_bytes=render_bytes,
        filename=f"shopify-theme-testimonial-{uuid4().hex}.png",
        content_type="image/png",
        alt=alt_text,
        usage_context=resolved_usage_context,
        product_id=product_id,
        tags=resolved_tags,
    )


def _resolve_testimonial_template(image: dict[str, Any]) -> str:
    raw = image.get("testimonialTemplate") or image.get("testimonial_template") or image.get("testimonial_type")
    if raw is None:
        return "review_card"
    if not isinstance(raw, str) or not raw.strip():
        raise TestimonialGenerationError("testimonialTemplate must be a non-empty string when provided.")
    template = raw.strip()
    if template not in _TESTIMONIAL_TEMPLATES:
        allowed = ", ".join(sorted(_TESTIMONIAL_TEMPLATES))
        raise TestimonialGenerationError(
            f"testimonialTemplate must be one of: {allowed}. Received: {template}"
        )
    return template


def _resolve_product_primary_image(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
) -> Asset:
    if not product.primary_asset_id:
        raise TestimonialGenerationError(
            "Product primary image is required to render testimonial hero images."
        )
    asset = session.scalars(
        select(Asset).where(
            Asset.org_id == org_id,
            Asset.client_id == client_id,
            Asset.id == product.primary_asset_id,
        )
    ).first()
    if not asset:
        raise TestimonialGenerationError("Product primary image asset not found.")
    if asset.product_id and str(asset.product_id) != str(product.id):
        raise TestimonialGenerationError("Product primary image asset does not belong to the product.")
    if asset.asset_kind != "image":
        raise TestimonialGenerationError("Product primary asset must be an image.")
    if asset.file_status and asset.file_status != "ready":
        raise TestimonialGenerationError("Product primary image asset is not ready.")
    if not asset.public_id:
        raise TestimonialGenerationError("Product primary image asset is missing public_id.")
    return asset


def _parse_config_context(props: dict[str, Any]) -> tuple[dict[str, Any] | None, _ConfigContext | None]:
    raw = props.get("configJson")
    if raw is not None:
        if not isinstance(raw, str) or not raw.strip():
            raise TestimonialGenerationError("configJson must be a non-empty JSON string.")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TestimonialGenerationError(f"configJson must be valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise TestimonialGenerationError("configJson must decode to a JSON object.")
        return parsed, _ConfigContext(props=props, key="configJson", parsed=parsed)

    config = props.get("config")
    if isinstance(config, dict):
        return config, None
    return None, None


def _collect_sales_pdp_targets(
    config: dict[str, Any], *, context: _ConfigContext | None
) -> list[_TestimonialGroup]:
    groups: list[_TestimonialGroup] = []
    review_wall = config.get("reviewWall")
    if isinstance(review_wall, dict):
        tiles = review_wall.get("tiles")
        if not isinstance(tiles, list) or not tiles:
            raise TestimonialGenerationError("Sales PDP reviewWall.tiles must be a non-empty list.")
        for idx, tile in enumerate(tiles):
            if not isinstance(tile, dict):
                raise TestimonialGenerationError("Sales PDP reviewWall.tiles must be objects.")
            image = tile.get("image")
            if not isinstance(image, dict):
                raise TestimonialGenerationError(
                    f"Sales PDP reviewWall.tiles[{idx}].image must be an object."
                )
            label = f"sales_pdp.reviewWall.tiles[{idx}]"
            render = _TestimonialRenderTarget(
                image=image,
                label=label,
                template=_resolve_testimonial_template(image),
                context=context,
            )
            groups.append(_TestimonialGroup(label=label, renders=[render], context=context))

    review_slider = config.get("reviewSlider")
    if isinstance(review_slider, dict):
        slides = review_slider.get("slides")
        if not isinstance(slides, list) or not slides:
            raise TestimonialGenerationError("Sales PDP reviewSlider.slides must be a non-empty list.")
        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                raise TestimonialGenerationError("Sales PDP reviewSlider.slides must be objects.")
            label = f"sales_pdp.reviewSlider.slides[{idx}]"
            render = _TestimonialRenderTarget(
                image=slide,
                label=label,
                template=_resolve_testimonial_template(slide),
                context=context,
            )
            groups.append(_TestimonialGroup(label=label, renders=[render], context=context))
    return groups


def _collect_sales_pdp_carousel_targets(
    config: dict[str, Any],
    *,
    context: _ConfigContext | None,
    expected_count: int,
) -> list[list[_SalesPdpCarouselTarget]]:
    hero = config.get("hero") if "hero" in config else config
    if not isinstance(hero, dict):
        raise TestimonialGenerationError("Sales PDP hero config must be an object.")
    gallery = hero.get("gallery")
    if not isinstance(gallery, dict):
        raise TestimonialGenerationError("Sales PDP hero.gallery must be an object.")
    slides = gallery.get("slides")
    if not isinstance(slides, list):
        raise TestimonialGenerationError("Sales PDP hero.gallery.slides must be a list.")
    if len(slides) < expected_count:
        for idx in range(len(slides), expected_count):
            slides.append({"alt": f"Sales PDP carousel image {idx + 1}"})
        if context:
            context.dirty = True
    if len(slides) > expected_count:
        del slides[expected_count:]
        if context:
            context.dirty = True

    slot_targets: list[list[_SalesPdpCarouselTarget]] = [[] for _ in range(expected_count)]
    for idx in range(expected_count):
        slide = slides[idx]
        if not isinstance(slide, dict):
            raise TestimonialGenerationError(f"Sales PDP hero.gallery.slides[{idx}] must be an object.")
        label = f"sales_pdp.hero.gallery.slides[{idx}]"
        slot_targets[idx].append(
            _SalesPdpCarouselTarget(
                image=slide,
                label=label,
                slot_index=idx,
                context=context,
            )
        )
    return slot_targets


def _collect_pre_sales_targets(
    config: dict[str, Any], *, context: _ConfigContext | None
) -> list[_TestimonialGroup]:
    groups: list[_TestimonialGroup] = []
    reviews = config.get("reviews")
    if isinstance(reviews, dict):
        slides = reviews.get("slides")
        if not isinstance(slides, list) or not slides:
            raise TestimonialGenerationError("Pre-sales reviews.slides must be a non-empty list.")
        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                raise TestimonialGenerationError("Pre-sales reviews.slides must be objects.")
            images = slide.get("images")
            if isinstance(images, list) and images:
                renders: list[_TestimonialRenderTarget] = []
                for img_idx, image in enumerate(images):
                    if not isinstance(image, dict):
                        raise TestimonialGenerationError(
                            f"Pre-sales reviews.slides[{idx}].images[{img_idx}] must be an object."
                        )
                    render_label = f"pre_sales.reviews.slides[{idx}].images[{img_idx}]"
                    renders.append(
                        _TestimonialRenderTarget(
                            image=image,
                            label=render_label,
                            template=_resolve_testimonial_template(image),
                            context=context,
                        )
                    )
                groups.append(
                    _TestimonialGroup(
                        label=f"pre_sales.reviews.slides[{idx}]",
                        renders=renders,
                        slide=slide,
                        context=context,
                    )
                )
            else:
                image = slide.get("image")
                if not isinstance(image, dict):
                    raise TestimonialGenerationError(
                        f"Pre-sales reviews.slides[{idx}].images must be a non-empty list."
                    )
                label = f"pre_sales.reviews.slides[{idx}]"
                render = _TestimonialRenderTarget(
                    image=image,
                    label=label,
                    template=_resolve_testimonial_template(image),
                    context=context,
                )
                groups.append(
                    _TestimonialGroup(label=label, renders=[render], slide=slide, context=context)
                )

    review_wall = config.get("reviewsWall")
    if isinstance(review_wall, dict):
        columns = review_wall.get("columns")
        if not isinstance(columns, list) or not columns:
            raise TestimonialGenerationError("Pre-sales reviewsWall.columns must be a non-empty list.")
        for col_idx, column in enumerate(columns):
            if not isinstance(column, list) or not column:
                raise TestimonialGenerationError("Pre-sales reviewsWall.columns must contain lists.")
            for row_idx, item in enumerate(column):
                if not isinstance(item, dict):
                    raise TestimonialGenerationError("Pre-sales reviewsWall.columns entries must be objects.")
                image = item.get("image")
                if not isinstance(image, dict):
                    raise TestimonialGenerationError(
                        f"Pre-sales reviewsWall.columns[{col_idx}][{row_idx}].image must be an object."
                    )
                label = f"pre_sales.reviewsWall.columns[{col_idx}][{row_idx}]"
                render = _TestimonialRenderTarget(
                    image=image,
                    label=label,
                    template=_resolve_testimonial_template(image),
                    context=context,
                )
                groups.append(_TestimonialGroup(label=label, renders=[render], context=context))
    return groups


def _collect_testimonial_targets(
    puck_data: dict[str, Any], template_kind: str
) -> tuple[list[_TestimonialGroup], list[_ConfigContext]]:
    groups: list[_TestimonialGroup] = []
    contexts: list[_ConfigContext] = []
    seen_images: set[int] = set()
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if not isinstance(comp_type, str) or not isinstance(props, dict):
            continue

        if comp_type in ("SalesPdpReviewWall", "SalesPdpReviewSlider", "SalesPdpTemplate") and template_kind == "sales-pdp":
            config, ctx = _parse_config_context(props)
            if not config:
                raise TestimonialGenerationError(f"{comp_type} is missing config/configJson.")
            if ctx:
                contexts.append(ctx)
            if comp_type == "SalesPdpTemplate":
                groups.extend(_collect_sales_pdp_targets(config, context=ctx))
            elif comp_type == "SalesPdpReviewWall":
                groups.extend(_collect_sales_pdp_targets({"reviewWall": config}, context=ctx))
            elif comp_type == "SalesPdpReviewSlider":
                groups.extend(_collect_sales_pdp_targets({"reviewSlider": config}, context=ctx))

        if comp_type in ("PreSalesReviews", "PreSalesReviewWall", "PreSalesTemplate") and template_kind == "pre-sales-listicle":
            config, ctx = _parse_config_context(props)
            if not config:
                raise TestimonialGenerationError(f"{comp_type} is missing config/configJson.")
            if ctx:
                contexts.append(ctx)
            if comp_type == "PreSalesTemplate":
                groups.extend(_collect_pre_sales_targets(config, context=ctx))
            elif comp_type == "PreSalesReviews":
                groups.extend(_collect_pre_sales_targets({"reviews": config}, context=ctx))
            elif comp_type == "PreSalesReviewWall":
                groups.extend(_collect_pre_sales_targets({"reviewsWall": config}, context=ctx))

    if not groups:
        expected: set[str] = set()
        if template_kind == "sales-pdp":
            expected = {"SalesPdpReviewWall", "SalesPdpReviewSlider", "SalesPdpTemplate"}
        elif template_kind == "pre-sales-listicle":
            expected = {"PreSalesReviews", "PreSalesReviewWall", "PreSalesTemplate"}
        counts = {key: 0 for key in expected}
        for obj in walk_json(puck_data):
            if not isinstance(obj, dict):
                continue
            comp_type = obj.get("type")
            if comp_type in counts:
                counts[comp_type] += 1
        found_summary = ", ".join(
            f"{comp_type}={count}" for comp_type, count in sorted(counts.items()) if count
        )
        if not found_summary:
            found_summary = "none"
        expected_summary = ", ".join(sorted(expected)) if expected else "unknown"
        raise TestimonialGenerationError(
            "No testimonial image slots found for this template. "
            f"templateKind={template_kind}. "
            f"Expected at least one of: {expected_summary}. "
            f"Found: {found_summary}."
        )
    for group in groups:
        for render in group.renders:
            image_id = id(render.image)
            if image_id in seen_images:
                raise TestimonialGenerationError(
                    f"Duplicate testimonial image slot detected: {render.label}"
                )
            seen_images.add(image_id)
    return groups, contexts


def _collect_sales_pdp_carousel_slots(
    puck_data: dict[str, Any],
    *,
    expected_count: int,
) -> tuple[list[list[_SalesPdpCarouselTarget]], list[_ConfigContext]]:
    if expected_count <= 0:
        raise TestimonialGenerationError("Sales PDP carousel expected_count must be greater than zero.")

    slot_targets: list[list[_SalesPdpCarouselTarget]] = [[] for _ in range(expected_count)]
    contexts: list[_ConfigContext] = []
    seen_image_ids: set[int] = set()
    found_component = False

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        if comp_type not in {"SalesPdpHero", "SalesPdpTemplate"}:
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        found_component = True
        config, ctx = _parse_config_context(props)
        if not isinstance(config, dict):
            raise TestimonialGenerationError(f"{comp_type} is missing config/configJson.")
        if ctx:
            contexts.append(ctx)
        component_slots = _collect_sales_pdp_carousel_targets(
            config=config,
            context=ctx,
            expected_count=expected_count,
        )
        for idx, targets in enumerate(component_slots):
            for target in targets:
                image_id = id(target.image)
                if image_id in seen_image_ids:
                    continue
                seen_image_ids.add(image_id)
                slot_targets[idx].append(target)

    if not found_component:
        raise TestimonialGenerationError(
            "No Sales PDP hero component found for carousel generation. "
            "Expected SalesPdpHero or SalesPdpTemplate."
        )
    for idx, targets in enumerate(slot_targets):
        if not targets:
            raise TestimonialGenerationError(
                f"Sales PDP carousel slot {idx} does not map to any hero.gallery slide targets."
            )
    return slot_targets, contexts


def _force_pre_sales_review_media_templates(puck_data: dict[str, Any]) -> None:
    def update_reviews_config(reviews: dict[str, Any]) -> None:
        slides = reviews.get("slides")
        if not isinstance(slides, list) or not slides:
            raise TestimonialGenerationError("Pre-sales reviews.slides must be a non-empty list.")
        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                raise TestimonialGenerationError("Pre-sales reviews.slides must be objects.")
            images = slide.get("images")
            if not isinstance(images, list) or len(images) < 3:
                raise TestimonialGenerationError(
                    f"Pre-sales reviews.slides[{idx}].images must include 3 image objects."
                )
            for image in images:
                if isinstance(image, dict):
                    image["testimonialTemplate"] = "testimonial_media"

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        if comp_type not in ("PreSalesReviews", "PreSalesTemplate"):
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        config = props.get("config")
        if isinstance(config, dict):
            if comp_type == "PreSalesReviews":
                update_reviews_config(config)
            else:
                reviews = config.get("reviews")
                if isinstance(reviews, dict):
                    update_reviews_config(reviews)
        raw = props.get("configJson")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise TestimonialGenerationError(
                    f"{comp_type}.configJson must be valid JSON: {exc}"
                ) from exc
            if isinstance(parsed, dict):
                if comp_type == "PreSalesReviews":
                    update_reviews_config(parsed)
                else:
                    reviews = parsed.get("reviews")
                    if isinstance(reviews, dict):
                        update_reviews_config(reviews)
                props["configJson"] = json.dumps(parsed, ensure_ascii=False)


def _apply_review_wall_template_mix(puck_data: dict[str, Any], template_kind: str) -> None:
    def assign_templates(images: list[dict[str, Any]]) -> None:
        templates = _wall_template_sequence(len(images))
        for image, template in zip(images, templates):
            image["testimonialTemplate"] = template

    def update_pre_sales_wall(config: dict[str, Any]) -> None:
        reviews_wall = config.get("reviewsWall") if "reviewsWall" in config else config
        if not isinstance(reviews_wall, dict):
            return
        columns = reviews_wall.get("columns")
        if not isinstance(columns, list):
            return
        images: list[dict[str, Any]] = []
        for column in columns:
            if not isinstance(column, list):
                continue
            for item in column:
                if not isinstance(item, dict):
                    continue
                image = item.get("image")
                if isinstance(image, dict):
                    images.append(image)
        assign_templates(images)

    def update_sales_wall(config: dict[str, Any]) -> None:
        review_wall = config.get("reviewWall") if "reviewWall" in config else config
        if not isinstance(review_wall, dict):
            return
        tiles = review_wall.get("tiles")
        if not isinstance(tiles, list):
            return
        images: list[dict[str, Any]] = []
        for tile in tiles:
            if not isinstance(tile, dict):
                continue
            image = tile.get("image")
            if isinstance(image, dict):
                images.append(image)
        assign_templates(images)

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        if template_kind == "pre-sales-listicle" and comp_type in ("PreSalesReviewWall", "PreSalesTemplate"):
            config = props.get("config")
            if isinstance(config, dict):
                if comp_type == "PreSalesReviewWall":
                    update_pre_sales_wall(config)
                else:
                    reviews_wall = config.get("reviewsWall")
                    if isinstance(reviews_wall, dict):
                        update_pre_sales_wall({"reviewsWall": reviews_wall})
            raw = props.get("configJson")
            if isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise TestimonialGenerationError(
                        f"{comp_type}.configJson must be valid JSON: {exc}"
                    ) from exc
                if isinstance(parsed, dict):
                    if comp_type == "PreSalesReviewWall":
                        update_pre_sales_wall(parsed)
                    else:
                        reviews_wall = parsed.get("reviewsWall")
                        if isinstance(reviews_wall, dict):
                            update_pre_sales_wall({"reviewsWall": reviews_wall})
                    props["configJson"] = json.dumps(parsed, ensure_ascii=False)

        if template_kind == "sales-pdp" and comp_type in ("SalesPdpReviewWall", "SalesPdpTemplate"):
            config = props.get("config")
            if isinstance(config, dict):
                if comp_type == "SalesPdpReviewWall":
                    update_sales_wall(config)
                else:
                    review_wall = config.get("reviewWall")
                    if isinstance(review_wall, dict):
                        update_sales_wall({"reviewWall": review_wall})
            raw = props.get("configJson")
            if isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise TestimonialGenerationError(
                        f"{comp_type}.configJson must be valid JSON: {exc}"
                    ) from exc
                if isinstance(parsed, dict):
                    if comp_type == "SalesPdpReviewWall":
                        update_sales_wall(parsed)
                    else:
                        review_wall = parsed.get("reviewWall")
                        if isinstance(review_wall, dict):
                            update_sales_wall({"reviewWall": review_wall})
                    props["configJson"] = json.dumps(parsed, ensure_ascii=False)


def _collect_sales_pdp_review_wall_images(groups: list[_TestimonialGroup]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for group in groups:
        for render in group.renders:
            if render.label.startswith("sales_pdp.reviewWall.tiles"):
                images.append(render.image)
    return images


def _collect_sales_pdp_review_slider_images(groups: list[_TestimonialGroup]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for group in groups:
        for render in group.renders:
            if render.label.startswith("sales_pdp.reviewSlider.slides"):
                images.append(render.image)
    return images


def _select_sales_pdp_reviews_payload_testimonials(
    *,
    groups: list[_TestimonialGroup],
    validated_testimonials: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(groups) != len(validated_testimonials):
        raise TestimonialGenerationError(
            "Unable to build SalesPdpReviews payload because testimonial target count does not match generated testimonials."
        )

    slider_only: list[dict[str, Any]] = []
    for idx, group in enumerate(groups):
        if group.label.startswith("sales_pdp.reviewSlider.slides"):
            slider_only.append(copy.deepcopy(validated_testimonials[idx]))
    if slider_only:
        return slider_only

    # If there is no review-slider-specific testimonial set, derive a distinct reviews feed
    # from reply identities/text so SalesPdpReviews does not mirror risk-free wall entries.
    derived: list[dict[str, Any]] = []
    for testimonial in validated_testimonials:
        item = copy.deepcopy(testimonial)
        reply = item.get("reply")
        if isinstance(reply, dict):
            reply_name = reply.get("name")
            if isinstance(reply_name, str) and reply_name.strip():
                item["name"] = reply_name.strip()
            reply_persona = reply.get("persona")
            if isinstance(reply_persona, str) and reply_persona.strip():
                item["persona"] = reply_persona.strip()
            reply_text = reply.get("text")
            if isinstance(reply_text, str) and reply_text.strip():
                item["review"] = reply_text.strip()
            reply_avatar_prompt = reply.get("avatarPrompt")
            if isinstance(reply_avatar_prompt, str) and reply_avatar_prompt.strip():
                item["avatarPrompt"] = reply_avatar_prompt.strip()
        derived.append(item)
    return derived


def _sync_sales_pdp_guarantee_feed_images(
    puck_data: dict[str, Any],
    *,
    review_wall_images: list[dict[str, Any]],
) -> None:
    guarantee_props: list[dict[str, Any]] = []
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "SalesPdpGuarantee":
            continue
        props = obj.get("props")
        if isinstance(props, dict):
            guarantee_props.append(props)

    if not guarantee_props:
        return

    if not review_wall_images:
        raise TestimonialGenerationError(
            "SalesPdpGuarantee requires SalesPdpReviewWall tiles to populate review feed images."
        )

    primary_image = copy.deepcopy(review_wall_images[0])
    if not isinstance(primary_image, dict):
        raise TestimonialGenerationError(
            "SalesPdpGuarantee feed image payload is invalid: first review wall image must be an object."
        )
    if not isinstance(primary_image.get("testimonialTemplate"), str) or not str(
        primary_image.get("testimonialTemplate")
    ).strip():
        primary_image["testimonialTemplate"] = "review_card"

    for props in guarantee_props:
        feed_images = copy.deepcopy(review_wall_images)
        raw_feed_json = props.get("feedImagesJson")
        if isinstance(raw_feed_json, str):
            props["feedImagesJson"] = json.dumps(feed_images, ensure_ascii=False)
            props["feedImages"] = feed_images
        else:
            props["feedImages"] = feed_images
            if "feedImagesJson" in props:
                props.pop("feedImagesJson", None)

        config = props.get("config")
        if isinstance(config, dict):
            right = config.get("right")
            if not isinstance(right, dict):
                right = {}
                config["right"] = right
            right["image"] = copy.deepcopy(primary_image)

        raw_config_json = props.get("configJson")
        if isinstance(raw_config_json, str):
            try:
                parsed = json.loads(raw_config_json)
            except json.JSONDecodeError as exc:
                raise TestimonialGenerationError(
                    f"SalesPdpGuarantee.configJson must be valid JSON: {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise TestimonialGenerationError(
                    "SalesPdpGuarantee.configJson must decode to a JSON object."
                )
            right = parsed.get("right")
            if not isinstance(right, dict):
                right = {}
                parsed["right"] = right
            right["image"] = copy.deepcopy(primary_image)
            props["configJson"] = json.dumps(parsed, ensure_ascii=False)


def _extract_copy_lines(puck_data: dict[str, Any]) -> str:
    excluded_keys = {
        "id",
        "assetPublicId",
        "src",
        "href",
        "imageSource",
        "referenceAssetPublicId",
        "targetPageId",
        "anchorId",
        "layout",
        "variant",
        "size",
        "align",
        "radius",
        "width",
        "height",
        "prompt",
        "configJson",
        "copyJson",
        "themeJson",
        "modalsJson",
    }

    def looks_like_url(value: str) -> bool:
        lowered = value.lower()
        if lowered.startswith(("http://", "https://", "file://")):
            return True
        if lowered.startswith("/assets/") or lowered.startswith("/public/"):
            return True
        return False

    lines: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in excluded_keys:
                    continue
                if isinstance(item, str):
                    candidate = item.strip()
                    if not candidate or looks_like_url(candidate):
                        continue
                    lines.append(candidate)
                else:
                    walk(item)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
            return

    walk(puck_data)
    seen: set[str] = set()
    unique_lines: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        unique_lines.append(line)
    text = "\n".join(unique_lines)
    if len(text) > 5000:
        text = text[:5000] + "..."
    return text


def _testimonial_output_schema(count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "testimonials": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 80},
                        "verified": {"type": "boolean"},
                        "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                        "review": {"type": "string", "minLength": 1, "maxLength": 800},
                        "persona": {"type": "string", "minLength": 1, "maxLength": 240},
                        "avatarPrompt": {"type": "string", "minLength": 1, "maxLength": 500},
                        "heroImagePrompt": {"type": "string", "minLength": 1, "maxLength": 600},
                        "mediaPrompts": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "items": {"type": "string", "minLength": 1, "maxLength": 300},
                        },
                        "reply": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "minLength": 1, "maxLength": 80},
                                "persona": {"type": "string", "minLength": 1, "maxLength": 240},
                                "text": {"type": "string", "minLength": 1, "maxLength": 600},
                                "avatarPrompt": {"type": "string", "minLength": 1, "maxLength": 500},
                                "time": {"type": "string", "minLength": 1, "maxLength": 24},
                                "reactionCount": {"type": "integer", "minimum": 0},
                            },
                            "required": [
                                "name",
                                "persona",
                                "text",
                                "avatarPrompt",
                                "time",
                                "reactionCount",
                            ],
                        },
                        "meta": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "location": {"type": "string", "minLength": 1, "maxLength": 120},
                                "date": {"type": "string"},
                            },
                            "required": ["location", "date"],
                        },
                    },
                    "required": [
                        "name",
                        "verified",
                        "rating",
                        "review",
                        "persona",
                        "avatarPrompt",
                        "heroImagePrompt",
                        "mediaPrompts",
                        "reply",
                        "meta",
                    ],
                },
            }
        },
        "required": ["testimonials"],
    }


def _validate_testimonial_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise TestimonialGenerationError("Testimonial name must be a non-empty string.")
    cleaned_name = name.strip()
    if len(cleaned_name) > 80:
        raise TestimonialGenerationError("Testimonial name must be 80 characters or fewer.")
    _assert_no_numeric_disambiguation_suffix(field_label="Testimonial name", value=cleaned_name)
    review = payload.get("review")
    if not isinstance(review, str) or not review.strip():
        raise TestimonialGenerationError("Testimonial review must be a non-empty string.")
    if len(review.strip()) > 800:
        raise TestimonialGenerationError("Testimonial review must be 800 characters or fewer.")
    persona = payload.get("persona")
    if not isinstance(persona, str) or not persona.strip():
        raise TestimonialGenerationError("Testimonial persona must be a non-empty string.")
    persona_cleaned = persona.strip()
    if len(persona_cleaned) > 240:
        persona_cleaned = persona_cleaned[:240].rstrip()
        if not persona_cleaned:
            raise TestimonialGenerationError("Testimonial persona must be 240 characters or fewer.")
    avatar_prompt = payload.get("avatarPrompt")
    if not isinstance(avatar_prompt, str) or not avatar_prompt.strip():
        raise TestimonialGenerationError("Testimonial avatarPrompt must be a non-empty string.")
    if len(avatar_prompt.strip()) > 500:
        raise TestimonialGenerationError("Testimonial avatarPrompt must be 500 characters or fewer.")
    hero_prompt = payload.get("heroImagePrompt")
    if not isinstance(hero_prompt, str) or not hero_prompt.strip():
        raise TestimonialGenerationError("Testimonial heroImagePrompt must be a non-empty string.")
    if len(hero_prompt.strip()) > 600:
        raise TestimonialGenerationError("Testimonial heroImagePrompt must be 600 characters or fewer.")
    media_prompts = payload.get("mediaPrompts")
    if not isinstance(media_prompts, list) or len(media_prompts) != 3:
        raise TestimonialGenerationError("Testimonial mediaPrompts must be an array of 3 strings.")
    cleaned_media_prompts: list[str] = []
    for idx, prompt in enumerate(media_prompts):
        if not isinstance(prompt, str) or not prompt.strip():
            raise TestimonialGenerationError(
                f"Testimonial mediaPrompts[{idx}] must be a non-empty string."
            )
        if len(prompt.strip()) > 300:
            raise TestimonialGenerationError(
                f"Testimonial mediaPrompts[{idx}] must be 300 characters or fewer."
            )
        cleaned_media_prompts.append(prompt.strip())
    reply = payload.get("reply")
    if not isinstance(reply, dict):
        raise TestimonialGenerationError("Testimonial reply must be an object.")
    reply_name = reply.get("name")
    if not isinstance(reply_name, str) or not reply_name.strip():
        raise TestimonialGenerationError("Testimonial reply.name must be a non-empty string.")
    cleaned_reply_name = reply_name.strip()
    if len(cleaned_reply_name) > 80:
        raise TestimonialGenerationError("Testimonial reply.name must be 80 characters or fewer.")
    _assert_no_numeric_disambiguation_suffix(
        field_label="Testimonial reply.name",
        value=cleaned_reply_name,
    )
    reply_persona = reply.get("persona")
    if not isinstance(reply_persona, str) or not reply_persona.strip():
        raise TestimonialGenerationError("Testimonial reply.persona must be a non-empty string.")
    reply_persona_cleaned = reply_persona.strip()
    if len(reply_persona_cleaned) > 240:
        reply_persona_cleaned = reply_persona_cleaned[:240].rstrip()
        if not reply_persona_cleaned:
            raise TestimonialGenerationError("Testimonial reply.persona must be 240 characters or fewer.")
    reply_text = reply.get("text")
    if not isinstance(reply_text, str) or not reply_text.strip():
        raise TestimonialGenerationError("Testimonial reply.text must be a non-empty string.")
    if len(reply_text.strip()) > 600:
        raise TestimonialGenerationError("Testimonial reply.text must be 600 characters or fewer.")
    reply_avatar_prompt = reply.get("avatarPrompt")
    if not isinstance(reply_avatar_prompt, str) or not reply_avatar_prompt.strip():
        raise TestimonialGenerationError("Testimonial reply.avatarPrompt must be a non-empty string.")
    if len(reply_avatar_prompt.strip()) > 500:
        raise TestimonialGenerationError(
            "Testimonial reply.avatarPrompt must be 500 characters or fewer."
        )
    reply_time = reply.get("time")
    if not isinstance(reply_time, str) or not reply_time.strip():
        raise TestimonialGenerationError("Testimonial reply.time must be a non-empty string.")
    if len(reply_time.strip()) > 24:
        raise TestimonialGenerationError("Testimonial reply.time must be 24 characters or fewer.")
    reply_reaction_count = reply.get("reactionCount")
    if (
        not isinstance(reply_reaction_count, int)
        or isinstance(reply_reaction_count, bool)
        or reply_reaction_count < 0
    ):
        raise TestimonialGenerationError(
            "Testimonial reply.reactionCount must be a non-negative integer."
        )
    if _normalize_identity_key(cleaned_reply_name) == _normalize_identity_key(cleaned_name):
        raise TestimonialGenerationError(
            "Testimonial reply.name must be different from the primary testimonial name."
        )
    if _normalize_identity_key(reply_persona_cleaned) == _normalize_identity_key(persona_cleaned):
        raise TestimonialGenerationError(
            "Testimonial reply.persona must be different from the primary testimonial persona."
        )
    verified = payload.get("verified")
    if not isinstance(verified, bool):
        raise TestimonialGenerationError("Testimonial verified must be a boolean.")
    rating = payload.get("rating")
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise TestimonialGenerationError("Testimonial rating must be an integer between 1 and 5.")
    meta = payload.get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            raise TestimonialGenerationError("Testimonial meta must be an object when provided.")
        location = meta.get("location")
        if location is not None:
            if not isinstance(location, str) or not location.strip():
                raise TestimonialGenerationError("meta.location must be a non-empty string when provided.")
            if len(location.strip()) > 120:
                raise TestimonialGenerationError("meta.location must be 120 characters or fewer.")
        date = meta.get("date")
        if date is not None:
            if not isinstance(date, str):
                raise TestimonialGenerationError("meta.date must be a string when provided.")
            try:
                datetime.strptime(date, _DATE_FORMAT)
            except ValueError as exc:
                raise TestimonialGenerationError("meta.date must be YYYY-MM-DD.") from exc
    return {
        "name": cleaned_name,
        "verified": verified,
        "rating": rating,
        "review": review.strip(),
        "persona": persona_cleaned,
        "avatarPrompt": avatar_prompt.strip(),
        "heroImagePrompt": hero_prompt.strip(),
        "mediaPrompts": cleaned_media_prompts,
        "reply": {
            "name": cleaned_reply_name,
            "persona": reply_persona_cleaned,
            "text": reply_text.strip(),
            "avatarPrompt": reply_avatar_prompt.strip(),
            "time": reply_time.strip(),
            "reactionCount": reply_reaction_count,
        },
        "meta": meta,
    }


def _build_testimonial_prompt(
    *,
    count: int,
    copy: str,
    product_context: str,
    today: str,
    uniqueness_nonce: str | None = None,
    reserved_names: list[str] | None = None,
) -> str:
    nonce_instruction = ""
    if isinstance(uniqueness_nonce, str) and uniqueness_nonce.strip():
        nonce_instruction = (
            "- Uniqueness nonce: "
            f"{uniqueness_nonce.strip()}. Use it only as an internal variation cue and never output it.\n"
        )

    reserved_instruction = ""
    if reserved_names:
        seen_reserved: set[str] = set()
        cleaned_reserved: list[str] = []
        for raw in reserved_names:
            if not isinstance(raw, str):
                continue
            cleaned = _clean_single_line(raw)
            if not cleaned:
                continue
            key = _normalize_identity_key(cleaned)
            if key in seen_reserved:
                continue
            seen_reserved.add(key)
            cleaned_reserved.append(cleaned[:80])
            if len(cleaned_reserved) >= 80:
                break
        if cleaned_reserved:
            reserved_lines = "\n".join(f"- {name}" for name in cleaned_reserved)
            reserved_instruction = (
                "Reserved names (do not use any of these names anywhere in the output, "
                "including reply names):\n"
                f"{reserved_lines}\n\n"
            )
    return (
        "You are generating synthetic customer testimonials for a landing page.\n"
        "Output JSON only. Do not include markdown or commentary.\n"
        "Your response must be a single JSON object that starts with '{' and ends with '}'.\n"
        f"Return exactly {count} testimonials.\n\n"
        f"{reserved_instruction}"
        "Rules:\n"
        "- Each review must be 1-3 sentences, <= 600 characters.\n"
        "- Names must be <= 80 characters.\n"
        "- rating is an integer 1-5.\n"
        "- verified is a boolean.\n"
        "- All names must be globally unique across the entire output, including both reviewer names and reply names.\n"
        "- No reply name may match any reviewer name.\n"
        "- Make each testimonial distinct (different personas, locations, and scenes).\n"
        "- persona should be a 1-2 sentence description of the reviewer (age range, context, motivation).\n"
        "- avatarPrompt should describe a realistic, candid portrait of that persona (no brand logos).\n"
        "- heroImagePrompt should describe a realistic lifestyle/product scene relevant to the review.\n"
        "- reply must describe a SECOND commenter identity with fields: name, persona, text, avatarPrompt, time, reactionCount.\n"
        "- reply.name and reply.persona must be different from the primary name/persona.\n"
        "- reply.avatarPrompt must describe the reply person's portrait and must stay consistent with reply name/persona.\n"
        "- mediaPrompts must include 3 short image prompts tied to the review; keep them general and product-agnostic (refer to 'the product' instead of specific brand names).\n"
        "- If the review references the product, include the product in at least one mediaPrompt using generic wording.\n"
        "- Do not reference photos/pictures/screenshots/attachments in the review or reply text (the testimonial may render with or without media).\n"
        "- avatarPrompt and heroImagePrompt must be unique per testimonial.\n"
        "- Do not reuse names or personas across testimonials (reviewers or replies).\n"
        "- Never append numeric disambiguation suffixes to names (for example: '(2)', '(3)').\n"
        "- meta.location should be <= 120 characters.\n"
        f"- meta.date must be YYYY-MM-DD; today is {today}.\n"
        "- Keep claims compliant; avoid medical promises or unrealistic outcomes.\n"
        f"{nonce_instruction}"
        "- Do not mention being AI or synthetic.\n\n"
        "Product context:\n"
        f"{product_context}\n"
        "Page copy:\n"
        f"{copy}\n\n"
        "Return JSON with this exact shape:\n"
        '{ "testimonials": [ { "name": "...", "verified": true, "rating": 5, "review": "...", "persona": "...", "avatarPrompt": "...", "heroImagePrompt": "...", "mediaPrompts": ["...", "...", "..."], "reply": { "name": "...", "persona": "...", "text": "...", "avatarPrompt": "...", "time": "2d", "reactionCount": 2 }, "meta": { "location": "...", "date": "YYYY-MM-DD" } } ] }\n'
    )


def _parse_json_object_response(raw: str | None, *, model_id: str, label: str) -> dict[str, Any]:
    if raw is None:
        raise TestimonialGenerationError(f"{label} response was empty (model={model_id}).")
    text = raw.strip()
    if not text:
        raise TestimonialGenerationError(f"{label} response was empty (model={model_id}).")

    def _try_parse(candidate: str) -> Optional[dict[str, Any]]:
        if not candidate:
            return None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    parsed = _try_parse(text)
    if parsed is not None:
        return parsed

    if "```" in text:
        start = text.find("```")
        while start != -1:
            end = text.find("```", start + 3)
            if end == -1:
                break
            block = text[start + 3 : end].strip()
            if block.lower().startswith("json"):
                block = block[4:].strip()
            parsed = _try_parse(block)
            if parsed is not None:
                return parsed
            start = text.find("```", end + 3)

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        parsed = _try_parse(text[first : last + 1])
        if parsed is not None:
            return parsed

    snippet = text[:300].replace("\n", "\\n")
    raise TestimonialGenerationError(
        f"{label} response was not valid JSON (model={model_id}). Snippet: {snippet}"
    )


def _parse_testimonials_response(raw: str, *, model_id: str) -> dict[str, Any]:
    return _parse_json_object_response(raw, model_id=model_id, label="Testimonials")


def _sales_pdp_carousel_output_schema() -> dict[str, Any]:
    variant_ids = [spec["variantId"] for spec in _SALES_PDP_CAROUSEL_VARIANTS]
    templates = sorted({spec["template"] for spec in _SALES_PDP_CAROUSEL_VARIANTS})
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "slides": {
                "type": "array",
                "minItems": len(_SALES_PDP_CAROUSEL_VARIANTS),
                "maxItems": len(_SALES_PDP_CAROUSEL_VARIANTS),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "variantId": {"type": "string", "enum": variant_ids},
                        "template": {"type": "string", "enum": templates},
                        "logoText": {"type": "string"},
                        "stripBgColor": {"type": "string"},
                        "stripTextColor": {"type": "string"},
                        "ratingValueText": {"type": "string"},
                        "ratingDetailText": {"type": "string"},
                        "ctaText": {"type": "string"},
                        "qaQuestionText": {"type": "string"},
                        "commentHandle": {"type": "string"},
                        "commentText": {"type": "string"},
                        "commentVerified": {"type": "boolean"},
                        "backgroundPromptVars": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "product": {"type": "string"},
                                "subject": {"type": "string"},
                                "scene": {"type": "string"},
                                "extra": {"type": "string"},
                                "avoid": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["product", "scene", "extra", "avoid"],
                        },
                    },
                    "required": [
                        "variantId",
                        "template",
                        "logoText",
                        "stripBgColor",
                        "stripTextColor",
                        "ratingValueText",
                        "ratingDetailText",
                        "ctaText",
                        "commentHandle",
                        "commentText",
                        "commentVerified",
                        "backgroundPromptVars",
                    ],
                },
            }
        },
        "required": ["slides"],
    }


def _build_sales_pdp_carousel_prompt(
    *,
    product_context: str,
    copy: str,
    today: str,
    brand_name: str | None,
) -> str:
    variant_lines = "\n".join(
        (
            f"- {spec['variantId']} ({spec['template']}): {spec.get('archetype', 'product-focused user-generated style scene.')} "
            f"Sample family: {spec.get('sampleInput', 'n/a')}."
        )
        for spec in _SALES_PDP_CAROUSEL_VARIANTS
    )
    required_variant_ids = ", ".join(spec["variantId"] for spec in _SALES_PDP_CAROUSEL_VARIANTS)
    brand_hint = f"Brand hint: {brand_name}.\n" if isinstance(brand_name, str) and brand_name.strip() else ""

    return (
        "You are generating Sales PDP carousel card specs for one product.\n"
        "Output JSON only. No markdown.\n"
        "Return one slide spec for each required variant listed below.\n\n"
        "Required variants (exactly one each):\n"
        f"{variant_lines}\n\n"
        "Rules:\n"
        f"- You MUST return exactly these variantIds once each: {required_variant_ids}.\n"
        "- Each variant must clearly match its sample family archetype listed above.\n"
        "- Keep all copy and prompts brand/product specific using Product context and Page copy below.\n"
        "- Never use generic placeholder product descriptions (for example 'hair skin nails gummy').\n"
        "- Keep claims compliant and realistic; avoid medical guarantees or impossible outcomes.\n"
        "- commentText must be <= 220 characters, natural, and specific.\n"
        "- commentHandle must be <= 40 characters and look like a plausible social handle.\n"
        "- ratingValueText must be <= 16 characters (for example: '4.8/5').\n"
        "- ratingDetailText must be <= 60 characters.\n"
        "- ctaText must be <= 60 characters.\n"
        "- logoText must be <= 24 characters.\n"
        "- For variantId=qa_ugc, qaQuestionText is REQUIRED (<= 120 chars) and should read like a real customer objection/question.\n"
        "- stripBgColor and stripTextColor must be valid hex colors (e.g. #0f3b2e, #ffffff).\n"
        "- backgroundPromptVars.product/scene/extra must be concrete, not generic.\n"
        "- For non-bold-claim templates, backgroundPromptVars.subject is required and must match the intended persona.\n"
        "- avoid must be a non-empty list of concise constraints (e.g. no text overlays/watermarks/distorted hands).\n"
        "- Make all 5 slides distinct in persona, scene, and copy.\n"
        f"- today is {today}.\n\n"
        f"{brand_hint}"
        "Product context:\n"
        f"{product_context}\n\n"
        "Page copy:\n"
        f"{copy}\n\n"
        "Return JSON with this exact top-level shape:\n"
        '{ "slides": [ { "variantId": "...", "template": "...", "logoText": "...", "stripBgColor": "#...", "stripTextColor": "#...", "ratingValueText": "...", "ratingDetailText": "...", "ctaText": "...", "commentHandle": "...", "commentText": "...", "commentVerified": true, "backgroundPromptVars": { "product": "...", "subject": "...", "scene": "...", "extra": "...", "avoid": ["...", "..."] } } ] }\n'
    )


def _require_trimmed_string(value: Any, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise TestimonialGenerationError(f"{field} must be a string.")
    cleaned = value.strip()
    if not cleaned:
        raise TestimonialGenerationError(f"{field} must be a non-empty string.")
    if len(cleaned) > max_length:
        raise TestimonialGenerationError(f"{field} must be <= {max_length} characters.")
    return cleaned


def _validate_sales_pdp_hex_color(value: Any, field: str) -> str:
    color = _require_trimmed_string(value, field, 24)
    if not _SALES_PDP_COLOR_RE.match(color):
        raise TestimonialGenerationError(f"{field} must be a hex color value (#rgb or #rrggbb).")
    return color


def _validate_sales_pdp_background_prompt_vars(payload: Any, field_prefix: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TestimonialGenerationError(f"{field_prefix} must be an object.")
    allowed_keys = {"product", "subject", "scene", "extra", "avoid"}
    for key in payload.keys():
        if key not in allowed_keys:
            raise TestimonialGenerationError(f"{field_prefix} contains unsupported key: {key}")

    product = _require_trimmed_string(payload.get("product"), f"{field_prefix}.product", 220)
    subject = payload.get("subject")
    if subject is not None and not isinstance(subject, str):
        raise TestimonialGenerationError(f"{field_prefix}.subject must be a string when provided.")
    subject_clean = subject.strip() if isinstance(subject, str) and subject.strip() else None
    if subject_clean is not None and len(subject_clean) > 220:
        raise TestimonialGenerationError(f"{field_prefix}.subject must be <= 220 characters.")
    scene = _require_trimmed_string(payload.get("scene"), f"{field_prefix}.scene", 220)
    extra = _require_trimmed_string(payload.get("extra"), f"{field_prefix}.extra", 600)
    avoid_raw = payload.get("avoid")
    if not isinstance(avoid_raw, list) or not avoid_raw:
        raise TestimonialGenerationError(f"{field_prefix}.avoid must be a non-empty array of strings.")
    avoid = [_require_trimmed_string(item, f"{field_prefix}.avoid[{idx}]", 160) for idx, item in enumerate(avoid_raw)]
    return {
        "product": product,
        "subject": subject_clean,
        "scene": scene,
        "extra": extra,
        "avoid": avoid,
    }


def _validate_sales_pdp_carousel_plan(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise TestimonialGenerationError("Sales PDP carousel plan must be a JSON object.")
    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list):
        raise TestimonialGenerationError("Sales PDP carousel plan must include a slides array.")
    if len(raw_slides) != len(_SALES_PDP_CAROUSEL_VARIANTS):
        raise TestimonialGenerationError(
            f"Sales PDP carousel plan must include exactly {len(_SALES_PDP_CAROUSEL_VARIANTS)} slides."
        )

    expected_templates = {
        spec["variantId"]: spec["template"] for spec in _SALES_PDP_CAROUSEL_VARIANTS
    }
    by_variant: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(raw_slides):
        if not isinstance(raw, dict):
            raise TestimonialGenerationError(f"slides[{idx}] must be an object.")
        variant_id = _require_trimmed_string(raw.get("variantId"), f"slides[{idx}].variantId", 80)
        if variant_id not in expected_templates:
            raise TestimonialGenerationError(
                f"slides[{idx}].variantId is unsupported: {variant_id!r}."
            )
        if variant_id in by_variant:
            raise TestimonialGenerationError(f"Duplicate variantId in carousel plan: {variant_id}.")
        template = _require_trimmed_string(raw.get("template"), f"slides[{idx}].template", 80)
        expected_template = expected_templates[variant_id]
        if template != expected_template:
            raise TestimonialGenerationError(
                f"slides[{idx}].template for variant {variant_id!r} must be {expected_template!r}."
            )
        prompt_vars = _validate_sales_pdp_background_prompt_vars(
            raw.get("backgroundPromptVars"),
            field_prefix=f"slides[{idx}].backgroundPromptVars",
        )
        if template != "pdp_bold_claim" and not prompt_vars.get("subject"):
            raise TestimonialGenerationError(
                f"slides[{idx}].backgroundPromptVars.subject is required for template {template}."
            )

        verified_raw = raw.get("commentVerified")
        if not isinstance(verified_raw, bool):
            raise TestimonialGenerationError(f"slides[{idx}].commentVerified must be a boolean.")
        qa_question = raw.get("qaQuestionText")
        qa_question_clean: str | None = None
        if variant_id == "qa_ugc":
            qa_question_clean = _require_trimmed_string(
                qa_question,
                f"slides[{idx}].qaQuestionText",
                120,
            )
        elif qa_question is not None:
            raise TestimonialGenerationError(
                f"slides[{idx}].qaQuestionText is only allowed for variantId='qa_ugc'."
            )

        by_variant[variant_id] = {
            "variantId": variant_id,
            "template": template,
            "logoText": _require_trimmed_string(raw.get("logoText"), f"slides[{idx}].logoText", 24),
            "stripBgColor": _validate_sales_pdp_hex_color(raw.get("stripBgColor"), f"slides[{idx}].stripBgColor"),
            "stripTextColor": _validate_sales_pdp_hex_color(
                raw.get("stripTextColor"), f"slides[{idx}].stripTextColor"
            ),
            "ratingValueText": _require_trimmed_string(
                raw.get("ratingValueText"), f"slides[{idx}].ratingValueText", 16
            ),
            "ratingDetailText": _require_trimmed_string(
                raw.get("ratingDetailText"), f"slides[{idx}].ratingDetailText", 60
            ),
            "ctaText": _require_trimmed_string(raw.get("ctaText"), f"slides[{idx}].ctaText", 60),
            "commentHandle": _require_trimmed_string(raw.get("commentHandle"), f"slides[{idx}].commentHandle", 40),
            "commentText": _require_trimmed_string(raw.get("commentText"), f"slides[{idx}].commentText", 220),
            "commentVerified": verified_raw,
            "qaQuestionText": qa_question_clean,
            "backgroundPromptVars": prompt_vars,
        }

    ordered: list[dict[str, Any]] = []
    for spec in _SALES_PDP_CAROUSEL_VARIANTS:
        variant_id = spec["variantId"]
        if variant_id not in by_variant:
            raise TestimonialGenerationError(f"Sales PDP carousel plan is missing variantId: {variant_id}.")
        ordered.append(by_variant[variant_id])
    return ordered


def _extract_sales_pdp_brand_name(puck_data: dict[str, Any]) -> str | None:
    def normalize_brand_name(raw: str) -> str | None:
        cleaned = _clean_single_line(raw)
        if not cleaned:
            return None
        for sep in ("—", "-", "|"):
            if sep in cleaned:
                candidate = cleaned.split(sep, 1)[0].strip()
                if candidate:
                    cleaned = candidate
                    break
        if len(cleaned) > 80:
            cleaned = cleaned[:80].rstrip()
        return cleaned or None

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if comp_type not in {"SalesPdpHeader", "SalesPdpHero"} or not isinstance(props, dict):
            continue
        config, _ = _parse_config_context(props)
        if not isinstance(config, dict):
            continue
        header = config
        if comp_type == "SalesPdpHero":
            header = config.get("header") if isinstance(config.get("header"), dict) else {}
        logo = header.get("logo") if isinstance(header.get("logo"), dict) else {}
        alt = logo.get("alt")
        if isinstance(alt, str):
            normalized = normalize_brand_name(alt)
            if normalized:
                return normalized
        purchase = config.get("purchase") if isinstance(config.get("purchase"), dict) else {}
        title = purchase.get("title")
        if isinstance(title, str):
            normalized = normalize_brand_name(title)
            if normalized:
                return normalized
    return None


def _find_sales_pdp_logo_asset_public_id(puck_data: dict[str, Any]) -> str | None:
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if comp_type not in {"SalesPdpHeader", "SalesPdpHero"} or not isinstance(props, dict):
            continue
        config, _ = _parse_config_context(props)
        if not isinstance(config, dict):
            continue
        header = config
        if comp_type == "SalesPdpHero":
            header = config.get("header") if isinstance(config.get("header"), dict) else {}
        logo = header.get("logo") if isinstance(header.get("logo"), dict) else {}
        raw_public_id = logo.get("assetPublicId")
        if isinstance(raw_public_id, str) and raw_public_id.strip():
            return raw_public_id.strip()
    return None


def _apply_sales_pdp_carousel_slot_asset(
    *,
    targets: list[_SalesPdpCarouselTarget],
    asset_public_id: str,
    default_alt: str,
) -> None:
    for target in targets:
        target.image["assetPublicId"] = asset_public_id
        target.image["thumbAssetPublicId"] = asset_public_id
        target.image.pop("src", None)
        target.image.pop("thumbSrc", None)
        existing_alt = target.image.get("alt")
        if not isinstance(existing_alt, str) or not existing_alt.strip():
            target.image["alt"] = default_alt
        if target.context:
            target.context.dirty = True


def generate_sales_pdp_carousel_images(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    draft_version_id: Optional[str] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    max_duration_seconds: Optional[int] = None,
) -> tuple[FunnelPageVersion, dict[str, Any], list[dict[str, Any]]]:
    if max_duration_seconds is not None and max_duration_seconds <= 0:
        raise TestimonialGenerationError("maxDurationSeconds must be > 0 when provided.")
    deadline_ts = (
        time.monotonic() + float(max_duration_seconds)
        if max_duration_seconds is not None
        else None
    )

    def ensure_within_budget(step: str) -> None:
        if deadline_ts is not None and time.monotonic() >= deadline_ts:
            raise TestimonialGenerationError(
                f"Sales PDP carousel step exceeded configured time budget while {step}."
            )

    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise TestimonialGenerationNotFoundError("Funnel not found")

    page = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
    ).first()
    if not page:
        raise TestimonialGenerationNotFoundError("Page not found")

    base_puck = current_puck_data
    if base_puck is None and draft_version_id:
        draft = session.scalars(
            select(FunnelPageVersion).where(
                FunnelPageVersion.page_id == page_id,
                FunnelPageVersion.id == draft_version_id,
            )
        ).first()
        if not draft:
            raise TestimonialGenerationNotFoundError("Draft version not found")
        base_puck = draft.puck_data
    if base_puck is None:
        raise TestimonialGenerationError(
            "currentPuckData or draftVersionId is required to generate Sales PDP carousel images."
        )
    if not isinstance(base_puck, dict):
        raise TestimonialGenerationError("puckData must be a JSON object.")

    resolved_template_id = template_id or page.template_id
    if resolved_template_id != "sales-pdp":
        raise TestimonialGenerationError(
            f"Sales PDP carousel generation only supports templateId='sales-pdp'. Received: {resolved_template_id!r}."
        )

    expected_count = _SALES_PDP_CAROUSEL_TOTAL_SLOTS

    slot_targets, contexts = _collect_sales_pdp_carousel_slots(
        base_puck,
        expected_count=expected_count,
    )

    product, _, product_context = _load_product_context(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        funnel=funnel,
    )
    if not product:
        raise TestimonialGenerationError("Product context is required to generate Sales PDP carousel images.")
    product_primary_asset = _resolve_product_primary_image(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        product=product,
    )
    copy_text = _extract_copy_lines(base_puck)
    if not copy_text.strip():
        raise TestimonialGenerationError("Unable to extract page copy for Sales PDP carousel generation.")

    brand_name = _extract_sales_pdp_brand_name(base_puck)
    logo_public_id = _find_sales_pdp_logo_asset_public_id(base_puck)
    logo_data_url: str | None = None
    if isinstance(logo_public_id, str) and logo_public_id:
        logo_asset = session.scalars(
            select(Asset).where(
                Asset.org_id == org_id,
                Asset.client_id == str(funnel.client_id),
                Asset.public_id == logo_public_id,
            )
        ).first()
        if not logo_asset:
            raise TestimonialGenerationError(
                f"Sales PDP header logo asset not found (assetPublicId={logo_public_id})."
            )
        if logo_asset.asset_kind != "image":
            raise TestimonialGenerationError(
                f"Sales PDP header logo asset must be an image (assetPublicId={logo_public_id})."
            )
        if logo_asset.file_status and logo_asset.file_status != "ready":
            raise TestimonialGenerationError(
                f"Sales PDP header logo asset is not ready (assetPublicId={logo_public_id})."
            )
        logo_data_url = _asset_data_url(logo_asset)

    llm = LLMClient()
    model_id = model or llm.default_model
    today = datetime.now(timezone.utc).date().isoformat()

    ensure_within_budget("requesting Sales PDP carousel plan")
    prompt = _build_sales_pdp_carousel_prompt(
        product_context=product_context,
        copy=copy_text,
        today=today,
        brand_name=brand_name,
    )

    if isinstance(model_id, str) and model_id.lower().startswith("claude"):
        claude_max_tokens = int(max_tokens) if max_tokens else 8_000
        resp = call_claude_structured_message(
            model=model_id,
            system=None,
            user_content=[{"type": "text", "text": prompt}],
            output_schema=_sales_pdp_carousel_output_schema(),
            max_tokens=claude_max_tokens,
            temperature=temperature,
            http_timeout_seconds=_TESTIMONIAL_CLAUDE_STRUCTURED_TIMEOUT_SECONDS,
            max_attempts=_TESTIMONIAL_CLAUDE_STRUCTURED_MAX_ATTEMPTS,
        )
        parsed_value = resp.get("parsed") if isinstance(resp, dict) else None
        if not isinstance(parsed_value, dict):
            raise TestimonialGenerationError("Claude structured Sales PDP carousel response was not a JSON object.")
        raw_plan = parsed_value
    else:
        params = LLMGenerationParams(
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            use_reasoning=True,
            use_web_search=False,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "SalesPdpCarouselPlan",
                    "strict": True,
                    "schema": _sales_pdp_carousel_output_schema(),
                },
            },
        )
        raw = llm.generate_text(prompt, params=params)
        raw_plan = _parse_json_object_response(raw, model_id=model_id, label="Sales PDP carousel")

    validated_plan = _validate_sales_pdp_carousel_plan(raw_plan)
    variant_spec_by_id = {spec["variantId"]: spec for spec in _SALES_PDP_CAROUSEL_VARIANTS}

    core_product_asset = product_primary_asset
    product_primary_is_square = (
        isinstance(product_primary_asset.width, int)
        and isinstance(product_primary_asset.height, int)
        and product_primary_asset.width == product_primary_asset.height
    )
    if not product_primary_is_square:
        ensure_within_budget("normalizing core product image to square")
        core_product_asset = _create_sales_pdp_square_core_asset(
            session=session,
            org_id=org_id,
            client_id=str(funnel.client_id),
            funnel_id=funnel_id,
            page_id=page_id,
            source_asset=product_primary_asset,
            source_alt=(f"{product.title} product image" if isinstance(product.title, str) else "Product image"),
            product_id=str(funnel.product_id) if funnel.product_id else None,
        )

    product_primary_public_id = str(core_product_asset.public_id)
    product_reference_data_url = _asset_data_url(product_primary_asset)
    generated: list[dict[str, Any]] = []

    core_slot_targets = slot_targets[_SALES_PDP_CAROUSEL_CORE_SLOT_INDEX]
    core_label = f"sales_pdp.hero.gallery.slides[{_SALES_PDP_CAROUSEL_CORE_SLOT_INDEX}]"
    _apply_sales_pdp_carousel_slot_asset(
        targets=core_slot_targets,
        asset_public_id=product_primary_public_id,
        default_alt=(f"{product.title} product image" if isinstance(product.title, str) else "Product image"),
    )
    generated.append(
        {
            "target": core_label,
            "targets": [target.label for target in core_slot_targets],
            "kind": "core_product_image",
            "publicId": product_primary_public_id,
            "assetId": str(core_product_asset.id),
            "template": (
                "core_product_image_square"
                if str(core_product_asset.id) != str(product_primary_asset.id)
                else "core_product_image"
            ),
            **(
                {
                    "sourcePublicId": str(product_primary_asset.public_id),
                    "sourceAssetId": str(product_primary_asset.id),
                }
                if str(core_product_asset.id) != str(product_primary_asset.id)
                else {}
            ),
        }
    )

    render_jobs: list[dict[str, Any]] = []
    for idx, slide_plan in enumerate(validated_plan):
        slot_index = idx + 1
        slot_label = f"sales_pdp.hero.gallery.slides[{slot_index}]"
        render_jobs.append(
            {
                "slot_index": slot_index,
                "slot_label": slot_label,
                "target_labels": [target.label for target in slot_targets[slot_index]],
                "slide_plan": slide_plan,
                "render_payload": {
                    "template": slide_plan["template"],
                    "output": {"preset": "square"},
                    "brand": {
                        "logoText": slide_plan["logoText"],
                        "stripBgColor": slide_plan["stripBgColor"],
                        "stripTextColor": slide_plan["stripTextColor"],
                        **({"name": brand_name} if brand_name else {}),
                        **({"logoUrl": logo_data_url} if logo_data_url else {}),
                    },
                    "rating": {
                        "valueText": slide_plan["ratingValueText"],
                        "detailText": slide_plan["ratingDetailText"],
                    },
                    "cta": {"text": slide_plan["ctaText"]},
                    "background": {
                        "promptVars": slide_plan["backgroundPromptVars"],
                        "referenceImages": [product_reference_data_url],
                        "referenceFirst": True,
                        "imageConfig": {"aspectRatio": "1:1"},
                    },
                    "comment": {
                        "handle": slide_plan["commentHandle"],
                        "text": slide_plan["commentText"],
                        **(
                            {"questionText": slide_plan["qaQuestionText"]}
                            if isinstance(slide_plan.get("qaQuestionText"), str)
                            else {}
                        ),
                        "verified": slide_plan["commentVerified"],
                    },
                },
            }
        )

    try:
        render_workers = min(_TESTIMONIAL_RENDER_WORKERS, len(render_jobs)) if render_jobs else 1
        rendered_bytes_by_slot: dict[int, bytes] = {}
        with ThreadedTestimonialRenderer(
            worker_count=render_workers,
            response_timeout_ms=_TESTIMONIAL_RENDER_RESPONSE_TIMEOUT_MS,
        ) as renderer:
            with concurrent.futures.ThreadPoolExecutor(max_workers=render_workers) as pool:
                render_futures: dict[int, concurrent.futures.Future[bytes]] = {}
                for job in render_jobs:
                    slot_index = cast(int, job["slot_index"])
                    render_payload = cast(dict[str, Any], job["render_payload"])
                    ensure_within_budget(f"queuing carousel slot render {slot_index + 1}")
                    render_futures[slot_index] = pool.submit(renderer.render_png, render_payload)

                for job in render_jobs:
                    slot_index = cast(int, job["slot_index"])
                    ensure_within_budget(f"waiting for carousel slot render {slot_index + 1}")
                    future = render_futures[slot_index]
                    try:
                        if deadline_ts is None:
                            rendered_bytes_by_slot[slot_index] = future.result()
                        else:
                            remaining = deadline_ts - time.monotonic()
                            if remaining <= 0:
                                raise TestimonialGenerationError(
                                    "Sales PDP carousel step exceeded configured time budget while waiting for render "
                                    f"slot {slot_index + 1}."
                                )
                            rendered_bytes_by_slot[slot_index] = future.result(timeout=remaining)
                    except concurrent.futures.TimeoutError as exc:
                        raise TestimonialGenerationError(
                            f"Sales PDP carousel step exceeded configured time budget while rendering slot {slot_index + 1}."
                        ) from exc

        for job in render_jobs:
            slot_index = cast(int, job["slot_index"])
            slot_label = cast(str, job["slot_label"])
            target_labels = cast(list[str], job["target_labels"])
            slide_plan = cast(dict[str, Any], job["slide_plan"])
            render_payload = cast(dict[str, Any], job["render_payload"])
            image_bytes = rendered_bytes_by_slot[slot_index]
            asset = create_funnel_upload_asset(
                session=session,
                org_id=org_id,
                client_id=str(funnel.client_id),
                content_bytes=image_bytes,
                filename=f"sales-pdp-carousel-{page_id}-{slot_index + 1}.png",
                content_type="image/png",
                alt=f"Sales PDP carousel image {slot_index + 1}",
                usage_context={
                    "kind": "sales_pdp_carousel_render",
                    "funnelId": funnel_id,
                    "pageId": page_id,
                    "target": slot_label,
                    "variantId": slide_plan["variantId"],
                },
                funnel_id=funnel_id,
                product_id=str(funnel.product_id) if funnel.product_id else None,
                tags=[
                    "funnel",
                    "testimonial",
                    "sales_pdp_carousel",
                    str(render_payload.get("template") or ""),
                    str(slide_plan["variantId"]),
                ],
            )

            _apply_sales_pdp_carousel_slot_asset(
                targets=slot_targets[slot_index],
                asset_public_id=str(asset.public_id),
                default_alt=f"Sales PDP carousel image {slot_index + 1}",
            )

            generated.append(
                {
                    "target": slot_label,
                    "targets": target_labels,
                    "kind": "generated_pdp_carousel",
                    "variantId": slide_plan["variantId"],
                    "sampleInput": variant_spec_by_id.get(slide_plan["variantId"], {}).get("sampleInput"),
                    "template": str(render_payload.get("template")),
                    "publicId": str(asset.public_id),
                    "assetId": str(asset.id),
                    "renderPayload": {
                        "template": render_payload["template"],
                        "outputPreset": "square",
                        "sampleInput": variant_spec_by_id.get(slide_plan["variantId"], {}).get("sampleInput"),
                        "brand": {
                            "logoText": slide_plan["logoText"],
                            "stripBgColor": slide_plan["stripBgColor"],
                            "stripTextColor": slide_plan["stripTextColor"],
                            **({"name": brand_name} if brand_name else {}),
                        },
                        "rating": render_payload["rating"],
                        "cta": render_payload["cta"],
                        "comment": render_payload["comment"],
                        **(
                            {"qaQuestionText": slide_plan["qaQuestionText"]}
                            if isinstance(slide_plan.get("qaQuestionText"), str)
                            else {}
                        ),
                        "backgroundPromptVars": slide_plan["backgroundPromptVars"],
                    },
                }
            )
    except TestimonialRenderError as exc:
        raise TestimonialGenerationError(str(exc)) from exc

    for ctx in contexts:
        if ctx.dirty:
            ctx.props[ctx.key] = json.dumps(ctx.parsed, ensure_ascii=False)

    ai_metadata = {
        "kind": "sales_pdp_carousel_generation",
        "model": model_id,
        "temperature": temperature,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "generatedCarouselImages": generated,
        "carouselPlan": validated_plan,
        "actorUserId": user_id,
        "ideaWorkspaceId": idea_workspace_id,
        "templateId": resolved_template_id,
    }

    normalize_public_page_metadata_for_context(
        session=session,
        org_id=org_id,
        funnel=funnel,
        page=page,
        puck_data=base_puck,
    )

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=base_puck,
        source=FunnelPageVersionSourceEnum.ai,
        created_at=datetime.now(timezone.utc),
        ai_metadata=ai_metadata,
    )
    session.add(version)
    session.commit()
    session.refresh(version)

    return version, base_puck, generated


def _generate_validated_synthetic_testimonials(
    *,
    count: int,
    copy_text: str,
    product_context: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    max_duration_seconds: int | None = None,
    uniqueness_scope: str,
) -> tuple[list[dict[str, Any]], str]:
    if count < 0:
        raise TestimonialGenerationError("count must be non-negative.")
    if count == 0:
        llm = LLMClient()
        return [], (model or llm.default_model)
    if max_duration_seconds is not None and max_duration_seconds <= 0:
        raise TestimonialGenerationError("maxDurationSeconds must be > 0 when provided.")

    llm = LLMClient()
    model_id = model or llm.default_model
    deadline_ts = (
        time.monotonic() + float(max_duration_seconds)
        if max_duration_seconds is not None
        else None
    )

    def ensure_within_budget(step: str) -> None:
        if deadline_ts is not None and time.monotonic() >= deadline_ts:
            raise TestimonialGenerationError(
                f"Testimonials step exceeded configured time budget while {step}."
            )

    if _MAX_TESTIMONIAL_IDENTITY_ATTEMPTS <= 0:
        raise TestimonialGenerationError(
            "FUNNEL_TESTIMONIAL_IDENTITY_ATTEMPTS must be greater than zero."
        )

    today = datetime.now(timezone.utc).date().isoformat()
    batch_size = 6
    validated_testimonials: list[dict[str, Any]] = []
    for identity_attempt in range(1, _MAX_TESTIMONIAL_IDENTITY_ATTEMPTS + 1):
        ensure_within_budget("generating testimonial identities")
        candidate_validated: list[dict[str, Any]] = []
        reserved_names: list[str] = []
        reserved_name_keys: set[str] = set()
        batch_validation_error: TestimonialGenerationError | None = None
        attempt_temperature = min(max(float(temperature), 0.0) + 0.1 * (identity_attempt - 1), 0.9)
        attempt_nonce = f"{uniqueness_scope}:{identity_attempt}:{uuid4().hex[:8]}"

        for batch_idx, start in enumerate(range(0, count, batch_size)):
            ensure_within_budget("requesting testimonial LLM batches")
            batch_count = min(batch_size, count - start)
            prompt = _build_testimonial_prompt(
                count=batch_count,
                copy=copy_text,
                product_context=product_context,
                today=today,
                uniqueness_nonce=f"{attempt_nonce}:batch:{batch_idx}",
                reserved_names=reserved_names,
            )

            parsed: dict[str, Any]
            if isinstance(model_id, str) and model_id.lower().startswith("claude"):
                resp = call_claude_structured_message(
                    model=model_id,
                    system=None,
                    user_content=[{"type": "text", "text": prompt}],
                    output_schema=_testimonial_output_schema(batch_count),
                    max_tokens=int(max_tokens) if max_tokens else 16_000,
                    temperature=attempt_temperature,
                    http_timeout_seconds=_TESTIMONIAL_CLAUDE_STRUCTURED_TIMEOUT_SECONDS,
                    max_attempts=_TESTIMONIAL_CLAUDE_STRUCTURED_MAX_ATTEMPTS,
                )
                parsed_value = resp.get("parsed") if isinstance(resp, dict) else None
                if not isinstance(parsed_value, dict):
                    raise TestimonialGenerationError(
                        "Claude structured testimonials response was not a JSON object."
                    )
                parsed = parsed_value
            else:
                params = LLMGenerationParams(
                    model=model_id,
                    max_tokens=max_tokens,
                    temperature=attempt_temperature,
                    use_reasoning=True,
                    use_web_search=False,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "Testimonials",
                            "strict": True,
                            "schema": _testimonial_output_schema(batch_count),
                        },
                    },
                )
                raw = llm.generate_text(prompt, params=params)
                parsed = _parse_testimonials_response(raw, model_id=model_id)
            batch_items = parsed.get("testimonials")
            if not isinstance(batch_items, list):
                raise TestimonialGenerationError(
                    "Testimonials response must include a testimonials array."
                )
            if len(batch_items) != batch_count:
                raise TestimonialGenerationError(
                    f"Expected {batch_count} testimonials, received {len(batch_items)}."
                )

            batch_validated: list[dict[str, Any]] = []
            for idx, raw in enumerate(batch_items):
                global_pos = len(candidate_validated) + idx + 1
                try:
                    batch_validated.append(_validate_testimonial_payload(raw or {}))
                except TestimonialGenerationError as exc:
                    batch_validation_error = TestimonialGenerationError(
                        f"Invalid testimonial payload at position {global_pos}: {exc}"
                    )
                    break
            if batch_validation_error is not None:
                break
            candidate_validated.extend(batch_validated)

            for item in batch_validated:
                primary = item.get("name")
                if isinstance(primary, str) and primary.strip():
                    key = _normalize_identity_key(primary)
                    if key and key not in reserved_name_keys:
                        reserved_name_keys.add(key)
                        reserved_names.append(primary.strip())
                reply = item.get("reply")
                if isinstance(reply, dict):
                    reply_name = reply.get("name")
                    if isinstance(reply_name, str) and reply_name.strip():
                        key = _normalize_identity_key(reply_name)
                        if key and key not in reserved_name_keys:
                            reserved_name_keys.add(key)
                            reserved_names.append(reply_name.strip())

        if batch_validation_error is not None:
            if identity_attempt >= _MAX_TESTIMONIAL_IDENTITY_ATTEMPTS:
                raise batch_validation_error
            continue

        try:
            _assert_distinct_testimonial_identities(candidate_validated)
        except TestimonialGenerationError as exc:
            is_duplicate_identity_error = "duplicate testimonial" in str(exc).lower()
            if not is_duplicate_identity_error:
                raise

            repaired_identities = _repair_distinct_testimonial_identities(
                candidate_validated
            )
            if repaired_identities is not None:
                _assert_distinct_testimonial_identities(repaired_identities)
                candidate_validated = repaired_identities
            elif identity_attempt >= _MAX_TESTIMONIAL_IDENTITY_ATTEMPTS:
                raise
            else:
                continue

        validated_testimonials = candidate_validated
        break

    if not validated_testimonials:
        raise TestimonialGenerationError(
            "Unable to generate distinct testimonial identities after configured retries."
        )
    return validated_testimonials, model_id


def _build_shopify_theme_testimonial_product_context(*, product: Product) -> str:
    payload = {
        "product": {
            "id": str(product.id),
            "title": str(product.title or "").strip(),
            "description": str(product.description or "").strip(),
            "productType": str(product.product_type or "").strip(),
            "primaryBenefits": [
                item.strip()
                for item in (product.primary_benefits or [])
                if isinstance(item, str) and item.strip()
            ],
            "featureBullets": [
                item.strip()
                for item in (product.feature_bullets or [])
                if isinstance(item, str) and item.strip()
            ],
            "guaranteeText": str(product.guarantee_text or "").strip(),
            "disclaimers": [
                item.strip()
                for item in (product.disclaimers or [])
                if isinstance(item, str) and item.strip()
            ],
        }
    }
    return (
        "Product context (source of truth; do not invent missing details):\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def generate_shopify_theme_review_card_payloads(
    *,
    product: Product,
    slot_paths: list[str],
    general_prompt_context: str | None = None,
    slot_prompt_context_by_path: dict[str, str] | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    max_duration_seconds: int | None = None,
) -> tuple[dict[str, dict[str, Any]], str]:
    normalized_slot_paths: list[str] = []
    seen_slot_paths: set[str] = set()
    for raw_slot_path in slot_paths:
        if not isinstance(raw_slot_path, str) or not raw_slot_path.strip():
            continue
        normalized_slot_path = raw_slot_path.strip()
        if normalized_slot_path in seen_slot_paths:
            continue
        seen_slot_paths.add(normalized_slot_path)
        normalized_slot_paths.append(normalized_slot_path)

    if not normalized_slot_paths:
        return {}, (model or LLMClient().default_model)

    configured_image_model = str(settings.TESTIMONIAL_RENDERER_IMAGE_MODEL or "").strip()
    if not configured_image_model:
        raise TestimonialRenderError(
            "TESTIMONIAL_RENDERER_IMAGE_MODEL is required for Shopify testimonial image generation."
        )

    copy_segments: list[str] = []
    normalized_general_prompt_context = _clean_single_line(general_prompt_context or "")
    if normalized_general_prompt_context:
        copy_segments.append(normalized_general_prompt_context)
    for slot_path in normalized_slot_paths:
        slot_prompt_context = _clean_single_line(
            (slot_prompt_context_by_path or {}).get(slot_path, "")
        )
        if not slot_prompt_context:
            continue
        copy_segments.append(
            f"Review image objective for {slot_path}: {slot_prompt_context}"
        )
    copy_text = "\n".join(copy_segments).strip()
    if len(copy_text) > 5000:
        copy_text = copy_text[:5000].rstrip()

    validated_testimonials, model_id = _generate_validated_synthetic_testimonials(
        count=len(normalized_slot_paths),
        copy_text=copy_text,
        product_context=_build_shopify_theme_testimonial_product_context(product=product),
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_duration_seconds=max_duration_seconds,
        uniqueness_scope=f"shopify-theme:{product.id}",
    )
    payload_by_slot_path: dict[str, dict[str, Any]] = {}
    for slot_path, testimonial in zip(
        normalized_slot_paths, validated_testimonials, strict=True
    ):
        payload: dict[str, Any] = {
            "template": "review_card",
            "name": testimonial["name"],
            "verified": testimonial["verified"],
            "rating": testimonial["rating"],
            "review": testimonial["review"],
            "avatarPrompt": testimonial["avatarPrompt"],
            "heroImagePrompt": testimonial["heroImagePrompt"],
            "imageModel": configured_image_model,
        }
        meta = testimonial.get("meta")
        if isinstance(meta, dict):
            payload["meta"] = meta
        payload_by_slot_path[slot_path] = payload
    return payload_by_slot_path, model_id


def generate_funnel_page_testimonials(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    draft_version_id: Optional[str] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    max_duration_seconds: Optional[int] = None,
    synthetic: bool = True,
) -> tuple[FunnelPageVersion, dict[str, Any], list[dict[str, Any]]]:
    if not synthetic:
        raise TestimonialGenerationError("Non-synthetic testimonial generation is not supported yet.")

    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise TestimonialGenerationNotFoundError("Funnel not found")

    page = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
    ).first()
    if not page:
        raise TestimonialGenerationNotFoundError("Page not found")

    base_puck = current_puck_data
    if base_puck is None and draft_version_id:
        draft = session.scalars(
            select(FunnelPageVersion).where(
                FunnelPageVersion.page_id == page_id,
                FunnelPageVersion.id == draft_version_id,
            )
        ).first()
        if not draft:
            raise TestimonialGenerationNotFoundError("Draft version not found")
        base_puck = draft.puck_data
    if base_puck is None:
        raise TestimonialGenerationError(
            "currentPuckData or draftVersionId is required to generate testimonials."
        )
    if not isinstance(base_puck, dict):
        raise TestimonialGenerationError("puckData must be a JSON object.")

    resolved_template_id = template_id or page.template_id
    if not resolved_template_id:
        raise TestimonialGenerationError("templateId is required to generate testimonials.")
    template_kind = None
    if resolved_template_id == "sales-pdp":
        template_kind = "sales-pdp"
    elif resolved_template_id == "pre-sales-listicle":
        template_kind = "pre-sales-listicle"
    else:
        raise TestimonialGenerationError(f"Template {resolved_template_id} is not supported for testimonials.")

    if template_kind == "pre-sales-listicle":
        _force_pre_sales_review_media_templates(base_puck)
    _apply_review_wall_template_mix(base_puck, template_kind)

    groups, contexts = _collect_testimonial_targets(base_puck, template_kind)

    product, _, product_context = _load_product_context(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        funnel=funnel,
    )
    if not product:
        raise TestimonialGenerationError("Product context is required to generate testimonials.")

    # Validate that the product has a primary image configured (required by business rules).
    product_primary_asset = _resolve_product_primary_image(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        product=product,
    )
    product_reference_bytes, product_reference_mime = _load_reference_asset_bytes(product_primary_asset)

    copy_text = _extract_copy_lines(base_puck)
    if not copy_text.strip():
        raise TestimonialGenerationError("Unable to extract page copy for testimonial generation.")

    if max_duration_seconds is not None and max_duration_seconds <= 0:
        raise TestimonialGenerationError("maxDurationSeconds must be > 0 when provided.")
    deadline_ts = (
        time.monotonic() + float(max_duration_seconds)
        if max_duration_seconds is not None
        else None
    )

    def ensure_within_budget(step: str) -> None:
        if deadline_ts is not None and time.monotonic() >= deadline_ts:
            raise TestimonialGenerationError(
                f"Testimonials step exceeded configured time budget while {step}."
            )

    model_id: str
    today = datetime.now(timezone.utc).date().isoformat()
    sales_review_wall_social_index = 0
    social_card_variant_index = 0
    review_card_scene_index = 0
    social_attachment_scene_index = 0
    total_social_comment_renders = sum(
        1 for group in groups for render in group.renders if render.template == "social_comment"
    )
    total_review_card_renders = sum(
        1 for group in groups for render in group.renders if render.template == "review_card"
    )
    selection_seed = _seed_value(funnel_id, page_id, resolved_template_id)
    social_without_attachment = _select_social_comment_without_attachment_indices(
        total_social_comment_renders, seed=_seed_value(str(selection_seed), "social_without_attachment")
    )
    review_without_hero = _select_review_card_without_hero_indices(
        total_review_card_renders, seed=_seed_value(str(selection_seed), "review_without_hero")
    )
    social_comment_index = 0
    review_card_index = 0

    remaining_duration_seconds: int | None = None
    if deadline_ts is not None:
        remaining_duration_seconds = max(
            1,
            int(deadline_ts - time.monotonic()),
        )
    validated_testimonials, model_id = _generate_validated_synthetic_testimonials(
        count=len(groups),
        copy_text=copy_text,
        product_context=product_context,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_duration_seconds=remaining_duration_seconds,
        uniqueness_scope=f"{funnel_id}:{page_id}:{resolved_template_id}",
    )

    generated: list[dict[str, Any]] = []
    try:
        with ThreadedTestimonialRenderer(
            worker_count=1,
            response_timeout_ms=_TESTIMONIAL_RENDER_RESPONSE_TIMEOUT_MS,
        ) as renderer:
            def render_with_budget(render_payload: dict[str, Any], *, label: str) -> bytes:
                ensure_within_budget(f"rendering {label}")
                timeout_ms = _TESTIMONIAL_RENDER_RESPONSE_TIMEOUT_MS
                if deadline_ts is not None:
                    remaining_seconds = deadline_ts - time.monotonic()
                    if remaining_seconds <= 0:
                        raise TestimonialGenerationError(
                            f"Testimonials step exceeded configured time budget while rendering {label}."
                        )
                    timeout_ms = max(1_000, min(int(remaining_seconds * 1000), timeout_ms))
                return renderer.render_png(render_payload, timeout_ms=timeout_ms)

            for idx, group in enumerate(groups):
                ensure_within_budget("rendering testimonial groups")
                validated = validated_testimonials[idx]

                if group.slide is not None:
                    group.slide["text"] = validated["review"]
                    group.slide["author"] = validated["name"]
                    group.slide["rating"] = validated["rating"]
                    group.slide["verified"] = validated["verified"]
                    if group.context:
                        group.context.dirty = True

                media_targets = [
                    render for render in group.renders if render.template == "testimonial_media"
                ]
                media_prompt_iter: Optional[Iterator[tuple[int, str]]] = None
                if media_targets:
                    if len(media_targets) != 3:
                        raise TestimonialGenerationError(
                            "testimonial_media requires exactly 3 image slots for each review slide."
                        )
                    media_prompts = validated["mediaPrompts"]
                    if len(media_prompts) != len(media_targets):
                        raise TestimonialGenerationError(
                            "mediaPrompts must include exactly 3 prompts for testimonial media images."
                        )
                    media_prompt_iter = iter(enumerate(media_prompts))

                for render in group.renders:
                    ensure_within_budget(f"rendering {render.label}")
                    setting_value = _derive_setting(
                        validated=validated,
                        fallback_text=validated["heroImagePrompt"],
                    )
                    action_value = _derive_action(
                        primary_direction=validated["heroImagePrompt"],
                        review=validated["review"],
                    )
                    direction_value = _truncate(validated["heroImagePrompt"], limit=260)

                    if render.template == "testimonial_media":
                        if media_prompt_iter is None:
                            raise TestimonialGenerationError(
                                "mediaPrompts are required for testimonial_media renders."
                            )
                        try:
                            media_index, prompt = next(media_prompt_iter)
                        except StopIteration as exc:
                            raise TestimonialGenerationError(
                                "Insufficient mediaPrompts provided for testimonial_media renders."
                            ) from exc

                        media_scene_mode = _select_media_scene_mode(media_index)
                        media_prompt = _build_testimonial_scene_prompt(
                            scene_mode=media_scene_mode,
                            render_label=render.label,
                            persona=validated["persona"],
                            setting=setting_value,
                            action=action_value,
                            direction=_truncate(prompt, limit=260),
                            identity_name=validated["name"],
                            identity_anchor=validated["avatarPrompt"],
                            require_subject_match=True,
                            include_text_screen_line=False,
                            prohibit_visible_text=True,
                        )
                        media_asset = _generate_testimonial_image_asset(
                            org_id=org_id,
                            client_id=str(funnel.client_id),
                            prompt=media_prompt,
                            aspect_ratio="9:16",
                            usage_context={
                                "kind": "testimonial_media_image",
                                "funnelId": funnel_id,
                                "pageId": page_id,
                                "target": render.label,
                            },
                            reference_image_bytes=product_reference_bytes,
                            reference_image_mime_type=product_reference_mime,
                            reference_asset_public_id=str(product_primary_asset.public_id),
                            reference_asset_id=str(product_primary_asset.id),
                            funnel_id=funnel_id,
                            product_id=str(funnel.product_id) if funnel.product_id else None,
                            tags=["funnel", "testimonial", "testimonial_media", "source"],
                        )

                        payload = {
                            "template": "testimonial_media",
                            "imageUrl": _public_asset_url(media_asset.public_id),
                            "alt": f"Customer scene for {validated['name']}",
                        }
                        render_payload = dict(payload)
                        render_payload["imageUrl"] = _asset_data_url_from_generated(media_asset)
                        image_bytes = render_with_budget(render_payload, label=render.label)
                        asset = create_funnel_upload_asset(
                            session=session,
                            org_id=org_id,
                            client_id=str(funnel.client_id),
                            content_bytes=image_bytes,
                            filename=f"testimonial-media-{page_id}-{idx + 1}.png",
                            content_type="image/png",
                            alt=f"Customer scene for {validated['name']}",
                            usage_context={
                                "kind": "testimonial_media_render",
                                "funnelId": funnel_id,
                                "pageId": page_id,
                                "target": render.label,
                            },
                            funnel_id=funnel_id,
                            product_id=str(funnel.product_id) if funnel.product_id else None,
                            tags=["funnel", "testimonial", "testimonial_media"],
                        )
                        render.image["assetPublicId"] = str(asset.public_id)
                        if "alt" not in render.image or not render.image.get("alt"):
                            render.image["alt"] = f"Customer scene for {validated['name']}"
                        if render.context:
                            render.context.dirty = True
                        generated.append(
                            {
                                "target": render.label,
                                "payload": payload,
                                "publicId": str(asset.public_id),
                                "assetId": str(asset.id),
                                "mediaSourcePublicId": media_asset.public_id,
                                "mediaPrompt": media_prompt,
                                "sceneMode": media_scene_mode,
                            }
                        )
                        continue

                    if render.template == "social_comment" and len(validated["review"]) > 600:
                        raise TestimonialGenerationError(
                            "Testimonial review must be 600 characters or fewer for social_comment renders."
                        )

                    if render.template == "review_card":
                        omit_hero = review_card_index in review_without_hero
                        review_card_index += 1
                        review_scene_mode = _select_single_scene_mode(review_card_scene_index)
                        review_card_scene_index += 1
                        review_hero_prompt = None
                        hero_asset: Optional[_GeneratedTestimonialAsset] = None
                        hero_error: str | None = None
                        if not omit_hero:
                            review_hero_prompt = _build_testimonial_scene_prompt(
                                scene_mode=review_scene_mode,
                                render_label=render.label,
                                persona=validated["persona"],
                                setting=setting_value,
                                action=action_value,
                                direction=direction_value,
                                identity_name=validated["name"],
                                identity_anchor=validated["avatarPrompt"],
                                require_subject_match=True,
                                include_text_screen_line=False,
                                prohibit_visible_text=True,
                            )
                        review_avatar_prompt = _build_distinct_avatar_prompt(
                            render_label=render.label,
                            display_name=validated["name"],
                            persona=validated["persona"],
                            direction=validated["avatarPrompt"],
                            variant_label="review-card-avatar",
                        )
                        review_avatar_asset: Optional[_GeneratedTestimonialAsset] = None
                        avatar_error: str | None = None
                        asset_jobs: dict[str, concurrent.futures.Future[_GeneratedTestimonialAsset]] = {}
                        if not omit_hero:
                            if review_hero_prompt is None:
                                raise TestimonialGenerationError(
                                    "Review card hero prompt was not generated even though hero rendering is enabled."
                                )
                        ensure_within_budget(f"generating source assets for {render.label}")
                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=min(_TESTIMONIAL_ASSET_MAX_CONCURRENCY, 2)
                        ) as pool:
                            if not omit_hero:
                                asset_jobs["hero"] = pool.submit(
                                    _generate_testimonial_image_asset,
                                    org_id=org_id,
                                    client_id=str(funnel.client_id),
                                    prompt=cast(str, review_hero_prompt),
                                    aspect_ratio="9:16",
                                    usage_context={
                                        "kind": "testimonial_review_hero",
                                        "funnelId": funnel_id,
                                        "pageId": page_id,
                                        "target": render.label,
                                    },
                                    reference_image_bytes=product_reference_bytes,
                                    reference_image_mime_type=product_reference_mime,
                                    reference_asset_public_id=str(product_primary_asset.public_id),
                                    reference_asset_id=str(product_primary_asset.id),
                                    funnel_id=funnel_id,
                                    product_id=str(funnel.product_id) if funnel.product_id else None,
                                    tags=["funnel", "testimonial", "review_card", "hero"],
                                )
                            asset_jobs["avatar"] = pool.submit(
                                _generate_testimonial_image_asset,
                                org_id=org_id,
                                client_id=str(funnel.client_id),
                                prompt=review_avatar_prompt,
                                aspect_ratio="1:1",
                                usage_context={
                                    "kind": "testimonial_review_avatar",
                                    "funnelId": funnel_id,
                                    "pageId": page_id,
                                    "target": render.label,
                                },
                                funnel_id=funnel_id,
                                product_id=str(funnel.product_id) if funnel.product_id else None,
                                tags=["funnel", "testimonial", "review_card", "avatar"],
                            )
                            for key, future in asset_jobs.items():
                                try:
                                    result = future.result()
                                except Exception as exc:  # noqa: BLE001
                                    if _should_soft_fail_gemini_missing_inline_data(exc):
                                        if key == "hero":
                                            hero_error = str(exc)
                                        if key == "avatar":
                                            avatar_error = str(exc)
                                        continue
                                    raise
                                if key == "hero":
                                    hero_asset = result
                                if key == "avatar":
                                    review_avatar_asset = result

                        payload: dict[str, Any] = {
                            "template": "review_card",
                            "name": validated["name"],
                            "verified": validated["verified"],
                            "rating": validated["rating"],
                            "review": validated["review"],
                        }
                        if review_avatar_asset is not None:
                            payload["avatarUrl"] = _public_asset_url(review_avatar_asset.public_id)
                        if hero_asset is not None:
                            payload["heroImageUrl"] = _public_asset_url(hero_asset.public_id)
                        if validated.get("meta") is not None:
                            payload["meta"] = validated["meta"]
                        payload["renderContext"] = {
                            "userContext": validated["persona"],
                            "pageCopy": copy_text,
                            "productContext": product_context,
                        }

                        render_payload = dict(payload)
                        if review_avatar_asset is not None:
                            render_payload["avatarUrl"] = _asset_data_url_from_generated(review_avatar_asset)
                        if hero_asset is not None:
                            render_payload["heroImageUrl"] = _asset_data_url_from_generated(hero_asset)

                        image_bytes = render_with_budget(render_payload, label=render.label)
                        asset = create_funnel_upload_asset(
                            session=session,
                            org_id=org_id,
                            client_id=str(funnel.client_id),
                            content_bytes=image_bytes,
                            filename=f"testimonial-{page_id}-{idx + 1}.png",
                            content_type="image/png",
                            alt=f"Testimonial from {validated['name']}",
                            usage_context={
                                "kind": "testimonial_render",
                                "funnelId": funnel_id,
                                "pageId": page_id,
                                "target": render.label,
                            },
                            funnel_id=funnel_id,
                            product_id=str(funnel.product_id) if funnel.product_id else None,
                            tags=["funnel", "testimonial", "review_card"],
                        )
                        render.image["assetPublicId"] = str(asset.public_id)
                        if "alt" not in render.image or not render.image.get("alt"):
                            render.image["alt"] = f"Review from {validated['name']}"
                        if render.context:
                            render.context.dirty = True
                        generated.append(
                            {
                                "target": render.label,
                                "payload": payload,
                                "publicId": str(asset.public_id),
                                "assetId": str(asset.id),
                                "heroSourcePublicId": (
                                    hero_asset.public_id if hero_asset is not None else None
                                ),
                                "avatarSourcePublicId": (
                                    review_avatar_asset.public_id
                                    if review_avatar_asset is not None
                                    else None
                                ),
                                "heroPrompt": review_hero_prompt,
                                "avatarPrompt": review_avatar_prompt,
                                "heroSceneMode": (review_scene_mode if hero_asset is not None else None),
                                "reviewHeroOmitted": bool(omit_hero),
                                "heroGenerationError": hero_error,
                                "avatarGenerationError": avatar_error,
                            }
                        )
                        continue

                    omit_attachment = social_comment_index in social_without_attachment
                    social_comment_index += 1
                    social_avatar_prompt = _build_distinct_avatar_prompt(
                        render_label=render.label,
                        display_name=validated["name"],
                        persona=validated["persona"],
                        direction=validated["avatarPrompt"],
                        variant_label="social-main-avatar",
                    )
                    social_scene_mode = _select_single_scene_mode(social_attachment_scene_index)
                    social_attachment_scene_index += 1
                    social_attachment_prompt = _build_testimonial_scene_prompt(
                        scene_mode=social_scene_mode,
                        render_label=render.label,
                        persona=validated["persona"],
                        setting=setting_value,
                        action=action_value,
                        direction=direction_value,
                        identity_name=validated["name"],
                        identity_anchor=validated["avatarPrompt"],
                        require_subject_match=True,
                        include_text_screen_line=False,
                        prohibit_visible_text=True,
                    )
                    avatar_asset: Optional[_GeneratedTestimonialAsset] = None
                    avatar_error: str | None = None
                    attachment_asset: Optional[_GeneratedTestimonialAsset] = None
                    attachment_error: str | None = None
                    social_jobs: dict[str, concurrent.futures.Future[_GeneratedTestimonialAsset]] = {}
                    ensure_within_budget(f"generating source assets for {render.label}")
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=min(_TESTIMONIAL_ASSET_MAX_CONCURRENCY, 2 if not omit_attachment else 1)
                    ) as pool:
                        social_jobs["avatar"] = pool.submit(
                            _generate_testimonial_image_asset,
                            org_id=org_id,
                            client_id=str(funnel.client_id),
                            prompt=social_avatar_prompt,
                            aspect_ratio="1:1",
                            usage_context={
                                "kind": "testimonial_social_avatar",
                                "funnelId": funnel_id,
                                "pageId": page_id,
                                "target": render.label,
                            },
                            funnel_id=funnel_id,
                            product_id=str(funnel.product_id) if funnel.product_id else None,
                            tags=["funnel", "testimonial", "social_comment", "avatar"],
                        )
                        if not omit_attachment:
                            social_jobs["attachment"] = pool.submit(
                                _generate_testimonial_image_asset,
                                org_id=org_id,
                                client_id=str(funnel.client_id),
                                prompt=social_attachment_prompt,
                                aspect_ratio="9:16",
                                usage_context={
                                    "kind": "testimonial_social_attachment",
                                    "funnelId": funnel_id,
                                    "pageId": page_id,
                                    "target": render.label,
                                },
                                reference_image_bytes=product_reference_bytes,
                                reference_image_mime_type=product_reference_mime,
                                reference_asset_public_id=str(product_primary_asset.public_id),
                                reference_asset_id=str(product_primary_asset.id),
                                funnel_id=funnel_id,
                                product_id=str(funnel.product_id) if funnel.product_id else None,
                                tags=["funnel", "testimonial", "social_comment", "attachment"],
                            )
                        for key, future in social_jobs.items():
                            try:
                                result = future.result()
                            except Exception as exc:  # noqa: BLE001
                                if _should_soft_fail_gemini_missing_inline_data(exc):
                                    if key == "avatar":
                                        avatar_error = str(exc)
                                    if key == "attachment":
                                        attachment_error = str(exc)
                                    continue
                                raise
                            if key == "avatar":
                                avatar_asset = result
                            if key == "attachment":
                                attachment_asset = result
                    time_value = today
                    if isinstance(validated.get("meta"), dict):
                        meta_date = validated["meta"].get("date")
                        if isinstance(meta_date, str) and meta_date.strip():
                            time_value = meta_date.strip()

                    seed = sum(ord(ch) for ch in render.label) + idx
                    variant = seed % 3
                    replies_public: list[dict[str, Any]] | None = None
                    replies_render: list[dict[str, Any]] | None = None
                    view_replies_text = None
                    reaction_count = 3 + (seed % 17)
                    follow_label = "Follow" if variant == 1 else None
                    reply_payload = validated["reply"]
                    reply_avatar_asset: Optional[_GeneratedTestimonialAsset] = None
                    reply_avatar_error: str | None = None

                    def ensure_reply_avatar_asset() -> Optional[_GeneratedTestimonialAsset]:
                        nonlocal reply_avatar_asset, reply_avatar_error
                        if reply_avatar_asset is not None or reply_avatar_error is not None:
                            return reply_avatar_asset
                        reply_avatar_prompt = _build_distinct_avatar_prompt(
                            render_label=render.label,
                            display_name=reply_payload["name"],
                            persona=reply_payload["persona"],
                            direction=reply_payload["avatarPrompt"],
                            variant_label="social-reply-avatar",
                        )
                        try:
                            reply_avatar_asset = _generate_testimonial_image_asset(
                                org_id=org_id,
                                client_id=str(funnel.client_id),
                                prompt=reply_avatar_prompt,
                                aspect_ratio="1:1",
                                usage_context={
                                    "kind": "testimonial_social_reply_avatar",
                                    "funnelId": funnel_id,
                                    "pageId": page_id,
                                    "target": render.label,
                                },
                                funnel_id=funnel_id,
                                product_id=str(funnel.product_id) if funnel.product_id else None,
                                tags=["funnel", "testimonial", "social_comment", "reply_avatar"],
                            )
                        except Exception as exc:  # noqa: BLE001
                            if _should_soft_fail_gemini_missing_inline_data(exc):
                                reply_avatar_asset = None
                                reply_avatar_error = str(exc)
                            else:
                                raise
                        return reply_avatar_asset

                    is_sales_review_wall = (
                        template_kind == "sales-pdp"
                        and "sales_pdp.reviewWall.tiles" in render.label
                    )
                    if is_sales_review_wall:
                        force_reply = sales_review_wall_social_index % 2 == 0
                        sales_review_wall_social_index += 1
                        if force_reply:
                            reply_avatar = ensure_reply_avatar_asset()
                            reply_entry_public: dict[str, Any] = {
                                "name": reply_payload["name"],
                                "text": reply_payload["text"],
                                "meta": {"time": reply_payload["time"]},
                                "reactionCount": reply_payload["reactionCount"],
                            }
                            reply_entry_render = dict(reply_entry_public)
                            if reply_avatar is not None:
                                reply_entry_public["avatarUrl"] = _public_asset_url(reply_avatar.public_id)
                                reply_entry_render["avatarUrl"] = _asset_data_url_from_generated(reply_avatar)
                            replies_public = [reply_entry_public]
                            replies_render = [reply_entry_render]
                            view_replies_text = "View 1 reply"

                    if variant == 0:
                        reply_avatar = ensure_reply_avatar_asset()
                        reply_entry_public = {
                            "name": reply_payload["name"],
                            "text": reply_payload["text"],
                            "meta": {"time": reply_payload["time"]},
                            "reactionCount": reply_payload["reactionCount"],
                        }
                        reply_entry_render = dict(reply_entry_public)
                        if reply_avatar is not None:
                            reply_entry_public["avatarUrl"] = _public_asset_url(reply_avatar.public_id)
                            reply_entry_render["avatarUrl"] = _asset_data_url_from_generated(reply_avatar)
                        replies_public = [reply_entry_public]
                        replies_render = [reply_entry_render]
                        view_replies_text = "View 1 reply"

                    primary_comment_public = {
                        "name": validated["name"],
                        "text": validated["review"],
                        "meta": {
                            "time": time_value,
                            **({"followLabel": follow_label} if follow_label else {}),
                        },
                        "reactionCount": reaction_count,
                        **(
                            {"replies": replies_public, "viewRepliesText": view_replies_text}
                            if replies_public
                            else {}
                        ),
                    }
                    primary_comment_render = {
                        **primary_comment_public,
                        **(
                            {"replies": replies_render, "viewRepliesText": view_replies_text}
                            if replies_render
                            else {}
                        ),
                    }
                    if avatar_asset is not None:
                        primary_comment_public["avatarUrl"] = _public_asset_url(avatar_asset.public_id)
                        primary_comment_render["avatarUrl"] = _asset_data_url_from_generated(avatar_asset)
                    if attachment_asset is not None:
                        primary_comment_public["attachmentUrl"] = _public_asset_url(attachment_asset.public_id)
                        primary_comment_render["attachmentUrl"] = _asset_data_url_from_generated(attachment_asset)

                    social_template = _next_social_card_variant(social_card_variant_index)
                    social_card_variant_index += 1
                    if social_template == "social_comment_instagram":
                        username = _clean_single_line(validated["name"]).lower().replace(" ", ".")
                        if not username:
                            raise TestimonialGenerationError("Instagram social template requires a non-empty username.")
                        location_value = ""
                        if isinstance(validated.get("meta"), dict):
                            location_raw = validated["meta"].get("location")
                            if isinstance(location_raw, str) and location_raw.strip():
                                location_value = location_raw.strip()
                        post_payload: dict[str, Any] = {
                            "username": username,
                            "likeCount": max(1, reaction_count * 3),
                            "dateLabel": time_value,
                        }
                        post_payload_render = dict(post_payload)
                        if avatar_asset is not None:
                            post_payload["avatarUrl"] = _public_asset_url(avatar_asset.public_id)
                            post_payload_render["avatarUrl"] = _asset_data_url_from_generated(avatar_asset)
                        if location_value:
                            post_payload["location"] = location_value
                            post_payload_render["location"] = location_value
                        payload = {
                            "template": "social_comment_instagram",
                            "post": post_payload,
                            "comments": [primary_comment_public],
                        }
                        render_payload = {
                            "template": "social_comment_instagram",
                            "post": post_payload_render,
                            "comments": [primary_comment_render],
                        }
                    elif social_template == "social_comment_no_header":
                        payload = {
                            "template": "social_comment_no_header",
                            "comments": [primary_comment_public],
                        }
                        render_payload = {
                            "template": "social_comment_no_header",
                            "comments": [primary_comment_render],
                        }
                    else:
                        payload = {
                            "template": "social_comment",
                            "header": {"title": "All comments", "showSortIcon": variant != 2},
                            "comments": [primary_comment_public],
                        }
                        render_payload = {
                            "template": "social_comment",
                            "header": {"title": "All comments", "showSortIcon": variant != 2},
                            "comments": [primary_comment_render],
                        }
                    image_bytes = render_with_budget(render_payload, label=render.label)
                    asset = create_funnel_upload_asset(
                        session=session,
                        org_id=org_id,
                        client_id=str(funnel.client_id),
                        content_bytes=image_bytes,
                        filename=f"testimonial-{page_id}-{idx + 1}.png",
                        content_type="image/png",
                        alt=f"Social comment from {validated['name']}",
                        usage_context={
                            "kind": "testimonial_render",
                            "funnelId": funnel_id,
                            "pageId": page_id,
                            "target": render.label,
                        },
                        funnel_id=funnel_id,
                        product_id=str(funnel.product_id) if funnel.product_id else None,
                        tags=["funnel", "testimonial", "social_comment", social_template],
                    )
                    render.image["assetPublicId"] = str(asset.public_id)
                    if "alt" not in render.image or not render.image.get("alt"):
                        render.image["alt"] = f"Social comment from {validated['name']}"
                    if render.context:
                        render.context.dirty = True
                    generated.append(
                        {
                            "target": render.label,
                            "payload": payload,
                            "publicId": str(asset.public_id),
                            "assetId": str(asset.id),
                            "avatarPublicId": (
                                avatar_asset.public_id if avatar_asset is not None else None
                            ),
                            "attachmentPublicId": (
                                attachment_asset.public_id if attachment_asset is not None else None
                            ),
                            "replyAvatarPublicId": (
                                reply_avatar_asset.public_id if reply_avatar_asset else None
                            ),
                            "replyName": (reply_payload["name"] if replies_public else None),
                            "replyPersona": (reply_payload["persona"] if replies_public else None),
                            "socialTemplate": social_template,
                            "attachmentPrompt": (social_attachment_prompt if attachment_asset is not None else None),
                            "attachmentSceneMode": (social_scene_mode if attachment_asset is not None else None),
                            "socialAttachmentOmitted": bool(omit_attachment),
                            "avatarGenerationError": avatar_error,
                            "attachmentGenerationError": attachment_error,
                            "replyAvatarGenerationError": reply_avatar_error,
                        }
                    )
    except TestimonialRenderError as exc:
        raise TestimonialGenerationError(str(exc)) from exc

    missing_assets: list[str] = []
    for group in groups:
        for render in group.renders:
            asset_public_id = render.image.get("assetPublicId")
            if not isinstance(asset_public_id, str) or not asset_public_id.strip():
                missing_assets.append(render.label)
    if missing_assets:
        sample = "\n".join(f"- {label}" for label in missing_assets[:12])
        raise TestimonialGenerationError(
            "Testimonial generation did not populate all image slots:\n"
            f"{sample}"
        )

    if template_kind == "sales-pdp":
        review_wall_images = _collect_sales_pdp_review_wall_images(groups)
        review_slider_images = _collect_sales_pdp_review_slider_images(groups)
        reviews_payload_testimonials = _select_sales_pdp_reviews_payload_testimonials(
            groups=groups,
            validated_testimonials=validated_testimonials,
        )
        _sync_sales_pdp_guarantee_feed_images(
            base_puck,
            review_wall_images=review_wall_images,
        )
        _sync_sales_pdp_reviews_from_testimonials(
            base_puck,
            product=product,
            validated_testimonials=reviews_payload_testimonials,
            today=today,
            review_media_images=review_slider_images,
        )

    for ctx in contexts:
        if ctx.dirty:
            ctx.props[ctx.key] = json.dumps(ctx.parsed, ensure_ascii=False)

    ai_metadata = {
        "kind": "testimonial_generation",
        "model": model_id,
        "temperature": temperature,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "synthetic": synthetic,
        "testimonialsProvenance": {"source": "synthetic" if synthetic else "production"},
        "generatedTestimonials": generated,
        "identityRepairs": [],
        "actorUserId": user_id,
        "ideaWorkspaceId": idea_workspace_id,
        "templateId": resolved_template_id,
    }

    normalize_public_page_metadata_for_context(
        session=session,
        org_id=org_id,
        funnel=funnel,
        page=page,
        puck_data=base_puck,
    )

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=base_puck,
        source=FunnelPageVersionSourceEnum.ai,
        created_at=datetime.now(timezone.utc),
        ai_metadata=ai_metadata,
    )
    session.add(version)
    session.commit()
    session.refresh(version)

    return version, base_puck, generated
