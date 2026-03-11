from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import re
from typing import Any

from pydantic import Field, ValidationError, field_validator, model_validator

from app.services import funnel_ai
from app.services.funnel_templates import get_funnel_template
from app.strategy_v2.contracts import StrictContract
from app.strategy_v2.copy_contract_spec import default_copy_contract_profile, get_page_contract
from app.strategy_v2.errors import StrategyV2DecisionError


_SUPPORTED_TEMPLATE_IDS = {"sales-pdp", "pre-sales-listicle"}
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MARKDOWN_BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<value>.+\S)\s*$")
_MARKDOWN_H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_FAQ_QUESTION_RE = re.compile(r"^\s*\**\s*Q[:\s]+\s*(?P<value>.+?)\s*\**\s*$", re.IGNORECASE)
_FAQ_ANSWER_RE = re.compile(r"^\s*\**\s*A[:\s]+\s*(?P<value>.+?)\s*\**\s*$", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"[.!?]+")
_SENTENCE_CHUNK_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
_WORD_RE = re.compile(r"\b[^\s]+\b")
_LITERAL_PRICE_RE = re.compile(r"\$\s*\d")
_HERO_BENEFIT_COUNT = 4
_HERO_BENEFIT_MAX_CHARS = 38
_HERO_BENEFIT_MAX_WORDS = 6
_MECHANISM_PARAGRAPH_MAX_CHARS = 180
_MIN_FAQ_ITEMS = 8
_VS_SPLIT_RE = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)
_HERO_BENEFIT_FORBIDDEN_PUNCTUATION_RE = re.compile(r"[,:;.!?()\[\]{}]")
_HERO_BENEFIT_FORBIDDEN_ENDINGS = {
    "workflow",
    "guide",
    "reference",
    "checklist",
    "worksheet",
    "worksheets",
    "page",
    "pages",
    "note",
    "notes",
    "database",
    "databases",
    "prompt",
    "prompts",
    "script",
    "scripts",
}
_PRE_SALES_REVIEW_COUNT_MIN = 12
_PRE_SALES_REVIEW_COUNT_MAX = 15000
_PRE_SALES_STANDARD_BADGES: tuple[dict[str, str], ...] = (
    {
        "label": "5-Star Reviews",
        "icon_alt": "5 star reviews",
        "icon_prompt": "icon of 5 star reviews",
    },
    {
        "value": "24/7",
        "label": "Customer Support",
        "icon_alt": "24/7 customer support",
        "icon_prompt": "icon of 24/7 customer support",
    },
    {
        "label": "Risk Free Trial",
        "icon_alt": "risk free trial",
        "icon_prompt": "icon of risk free trial",
    },
)

_REQUIRED_MAPPED_SECTION_KEYS = {
    "hero_stack",
    "problem_recap",
    "mechanism_comparison",
    "guarantee",
    "faq",
}


def _format_pre_sales_review_wall_title(count: int) -> str:
    return f"Over {count:,} — 5 Star Reviews"


def _derive_pre_sales_review_count(payload_fields: dict[str, Any]) -> int:
    seed_payload = {
        "hero": payload_fields.get("hero"),
        "reasons": payload_fields.get("reasons"),
        "reviews": payload_fields.get("reviews"),
        "review_wall": payload_fields.get("review_wall"),
        "floating_cta": payload_fields.get("floating_cta"),
    }
    seed_source = json.dumps(seed_payload, ensure_ascii=False, sort_keys=True)
    normalized = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:8], 16)
    span = _PRE_SALES_REVIEW_COUNT_MAX - _PRE_SALES_REVIEW_COUNT_MIN + 1
    return _PRE_SALES_REVIEW_COUNT_MIN + (normalized % span)


def _normalize_pre_sales_template_payload_fields(payload_fields: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(payload_fields)
    hero = normalized.get("hero")
    review_wall = normalized.get("review_wall")
    if not isinstance(hero, dict) or not isinstance(review_wall, dict):
        return normalized

    review_count = _derive_pre_sales_review_count(normalized)
    badges: list[dict[str, Any]] = []
    for index, spec in enumerate(_PRE_SALES_STANDARD_BADGES):
        badge: dict[str, Any] = {
            "label": spec["label"],
            "icon": {
                "alt": spec["icon_alt"],
                "prompt": spec["icon_prompt"],
            },
        }
        if index == 0:
            badge["value"] = f"{review_count:,}"
        elif "value" in spec:
            badge["value"] = spec["value"]
        badges.append(badge)

    hero["badges"] = badges
    review_wall["title"] = _format_pre_sales_review_wall_title(review_count)
    return normalized


class TemplateFitPackComparisonRow(StrictContract):
    label: str = Field(min_length=1, max_length=80)
    pup: str = Field(min_length=1, max_length=180)
    disposable: str = Field(min_length=1, max_length=180)


class TemplateFitPackStoryBullet(StrictContract):
    title: str = Field(min_length=1, max_length=56)
    body: str = Field(min_length=1, max_length=160)


class TemplateFitPackMechanismCallout(StrictContract):
    left_title: str = Field(min_length=1, max_length=120)
    left_body: str = Field(min_length=1, max_length=240)
    right_title: str = Field(min_length=1, max_length=120)
    right_body: str = Field(min_length=1, max_length=240)


class TemplateFitPackComparisonColumns(StrictContract):
    pup: str = Field(min_length=1, max_length=80)
    disposable: str = Field(min_length=1, max_length=80)


class TemplateFitPackComparison(StrictContract):
    badge: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    swipe_hint: str = Field(min_length=1, max_length=120)
    columns: TemplateFitPackComparisonColumns
    rows: list[TemplateFitPackComparisonRow] = Field(min_length=1, max_length=8)

    @field_validator("badge")
    @classmethod
    def _validate_badge(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower() != "us vs them":
            raise ValueError("badge must be exactly 'US vs THEM'.")
        return "US vs THEM"

    @model_validator(mode="after")
    def _normalize_title_orientation(self) -> "TemplateFitPackComparison":
        self.title = _normalize_comparison_title(
            raw_title=self.title,
            columns=self.columns.model_dump(mode="python"),
        )
        return self


class TemplateFitPackFaqItem(StrictContract):
    question: str = Field(min_length=1, max_length=120)
    answer: str = Field(min_length=1, max_length=280)

    @field_validator("answer")
    @classmethod
    def _validate_answer(cls, value: str) -> str:
        cleaned = value.strip()
        sentence_count = len([part for part in _SENTENCE_RE.split(cleaned) if part.strip()])
        if sentence_count > 3:
            raise ValueError(f"answer exceeds 3 sentences (observed={sentence_count}).")
        return cleaned


class TemplateFitPackFaqPill(StrictContract):
    label: str = Field(min_length=1, max_length=120)
    answer: str = Field(min_length=1, max_length=420)


class TemplateFitPackHero(StrictContract):
    purchase_title: str = Field(min_length=1, max_length=64)
    primary_cta_label: str = Field(min_length=1)
    primary_cta_subbullets: list[str] = Field(min_length=2, max_length=2)

    @field_validator("primary_cta_subbullets")
    @classmethod
    def _validate_primary_cta_subbullets(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"primary_cta_subbullets[{index}] must be non-empty.")
            if len(item) > 90:
                raise ValueError(
                    f"primary_cta_subbullets[{index}] exceeds 90 characters "
                    f"(observed={len(item)})."
                )
            cleaned.append(item)
        return cleaned


class TemplateFitPackProblem(StrictContract):
    title: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1, max_length=2)
    emphasis_line: str = Field(min_length=1)

    @field_validator("paragraphs")
    @classmethod
    def _validate_paragraphs(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"paragraphs[{index}] must be non-empty.")
            if len(item) > 320:
                raise ValueError(
                    f"paragraphs[{index}] exceeds 320 characters "
                    f"(observed={len(item)})."
                )
            cleaned.append(item)
        return cleaned


class TemplateFitPackMechanism(StrictContract):
    title: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1, max_length=1)
    bullets: list[TemplateFitPackStoryBullet] = Field(min_length=5, max_length=5)
    callout: TemplateFitPackMechanismCallout
    comparison: TemplateFitPackComparison

    @field_validator("paragraphs")
    @classmethod
    def _validate_paragraphs(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"paragraphs[{index}] must be non-empty.")
            if len(item) > _MECHANISM_PARAGRAPH_MAX_CHARS:
                raise ValueError(
                    f"paragraphs[{index}] exceeds {_MECHANISM_PARAGRAPH_MAX_CHARS} characters "
                    f"(observed={len(item)})."
                )
            sentence_count = len([part for part in _SENTENCE_RE.split(item) if part.strip()])
            if sentence_count > 2:
                raise ValueError(
                    f"paragraphs[{index}] exceeds 2 sentences (observed={sentence_count})."
                )
            cleaned.append(item)
        return cleaned


class TemplateFitPackSocialProof(StrictContract):
    badge: str = Field(min_length=1)
    title: str = Field(min_length=1)
    rating_label: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class TemplateFitPackWhatsInside(StrictContract):
    benefits: list[str] = Field(min_length=_HERO_BENEFIT_COUNT, max_length=_HERO_BENEFIT_COUNT)
    offer_helper_text: str = Field(min_length=1, max_length=180)

    @field_validator("benefits")
    @classmethod
    def _validate_benefits(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"benefits[{index}] must be non-empty.")
            if len(item) > _HERO_BENEFIT_MAX_CHARS:
                raise ValueError(
                    f"benefits[{index}] exceeds {_HERO_BENEFIT_MAX_CHARS} characters "
                    f"(observed={len(item)})."
                )
            word_count = len(_WORD_RE.findall(item))
            if word_count < 2 or word_count > _HERO_BENEFIT_MAX_WORDS:
                raise ValueError(
                    f"benefits[{index}] must be a one-bite phrase with 2-"
                    f"{_HERO_BENEFIT_MAX_WORDS} words (observed={word_count})."
                )
            if _HERO_BENEFIT_FORBIDDEN_PUNCTUATION_RE.search(item) or "->" in item:
                raise ValueError(
                    f"benefits[{index}] must avoid explanatory punctuation. "
                    "Use a compact phrase, not a sentence fragment."
                )
            terminal_word = re.sub(r"[^a-z]+", "", item.split()[-1].lower())
            if terminal_word in _HERO_BENEFIT_FORBIDDEN_ENDINGS:
                raise ValueError(
                    f"benefits[{index}] must end on an outcome, not a feature label like '{terminal_word}'."
                )
            cleaned.append(item)
        return cleaned

    @field_validator("offer_helper_text")
    @classmethod
    def _validate_offer_helper_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("offer_helper_text must be non-empty.")
        sentence_count = len([part for part in _SENTENCE_RE.split(cleaned) if part.strip()])
        if sentence_count > 2:
            raise ValueError(
                f"offer_helper_text exceeds 2 sentences (observed={sentence_count})."
            )
        return cleaned


class TemplateFitPackBonus(StrictContract):
    free_gifts_title: str = Field(min_length=1)
    free_gifts_body: str = Field(min_length=1, max_length=220)


class TemplateFitPackGuarantee(StrictContract):
    title: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1, max_length=1)
    why_title: str = Field(min_length=1)
    why_body: str = Field(min_length=1, max_length=220)
    closing_line: str = Field(min_length=1, max_length=140)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = _normalize_guarantee_title(value)
        if "risk free guarantee" not in cleaned.lower():
            raise ValueError(
                "title must use 'Risk Free Guarantee' language. "
                "Include the day count if relevant, for example '45-Day Risk Free Guarantee'."
            )
        return cleaned

    @field_validator("paragraphs")
    @classmethod
    def _validate_paragraphs(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"paragraphs[{index}] must be non-empty.")
            if len(item) > 260:
                raise ValueError(
                    f"paragraphs[{index}] exceeds 260 characters "
                    f"(observed={len(item)})."
                )
            cleaned.append(item)
        return cleaned


class TemplateFitPackFaq(StrictContract):
    title: str = Field(min_length=1)
    items: list[TemplateFitPackFaqItem] = Field(min_length=_MIN_FAQ_ITEMS, max_length=12)


class TemplateFitPack(StrictContract):
    hero: TemplateFitPackHero
    problem: TemplateFitPackProblem
    mechanism: TemplateFitPackMechanism
    social_proof: TemplateFitPackSocialProof
    whats_inside: TemplateFitPackWhatsInside
    bonus: TemplateFitPackBonus
    guarantee: TemplateFitPackGuarantee
    faq: TemplateFitPackFaq
    faq_pills: list[TemplateFitPackFaqPill] = Field(min_length=_MIN_FAQ_ITEMS, max_length=12)
    marquee_items: list[str] = Field(min_length=1, max_length=12)
    cta_close: str = Field(min_length=1)
    urgency_message: str = Field(min_length=1, max_length=220)

    @field_validator("marquee_items")
    @classmethod
    def _validate_marquee_items(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"marquee_items[{index}] must be non-empty.")
            if len(item) > 24:
                raise ValueError(
                    f"marquee_items[{index}] exceeds 24 characters "
                    f"(observed={len(item)})."
                )
            word_count = len(_WORD_RE.findall(item))
            if word_count < 1 or word_count > 3:
                raise ValueError(
                    f"marquee_items[{index}] must contain 1-3 words (observed={word_count})."
                )
            cleaned.append(item)
        return cleaned


class PreSalesReasonImageFitPack(StrictContract):
    alt: str = Field(min_length=1, max_length=240)
    prompt: str | None = Field(default=None, min_length=1, max_length=420)


class PreSalesReasonFitPack(StrictContract):
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=72)
    body: str = Field(min_length=1, max_length=420)
    image: PreSalesReasonImageFitPack

    @field_validator("body")
    @classmethod
    def _validate_body(cls, value: str) -> str:
        cleaned = value.strip()
        sentence_count = len([part for part in _SENTENCE_RE.split(cleaned) if part.strip()])
        if sentence_count > 3:
            raise ValueError(f"body exceeds 3 sentences (observed={sentence_count}).")
        return cleaned


class PreSalesHeroFitPack(StrictContract):
    title: str = Field(min_length=1, max_length=90)
    subtitle: str = Field(min_length=1, max_length=140)
    badges: list["PreSalesHeroBadgeFitPack"] = Field(min_length=1)

    @field_validator("subtitle")
    @classmethod
    def _validate_subtitle(cls, value: str) -> str:
        cleaned = value.strip()
        sentence_count = len([part for part in _SENTENCE_RE.split(cleaned) if part.strip()])
        if sentence_count > 2:
            raise ValueError(f"subtitle exceeds 2 sentences (observed={sentence_count}).")
        return cleaned


class PreSalesHeroBadgeIconFitPack(StrictContract):
    alt: str = Field(min_length=1, max_length=240)
    prompt: str = Field(min_length=1, max_length=420)


class PreSalesHeroBadgeFitPack(StrictContract):
    label: str = Field(min_length=1)
    value: str | None = Field(default=None, max_length=24)
    icon: PreSalesHeroBadgeIconFitPack


class PreSalesPitchImageFitPack(StrictContract):
    alt: str = Field(min_length=1, max_length=240)
    prompt: str | None = Field(default=None, min_length=1, max_length=420)


class PreSalesPitchFitPack(StrictContract):
    title: str = Field(min_length=1, max_length=78)
    bullets: list[str] = Field(min_length=4, max_length=4)
    cta_label: str = Field(min_length=1)
    image: PreSalesPitchImageFitPack

    @field_validator("bullets")
    @classmethod
    def _validate_bullets(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"bullets[{index}] must be non-empty.")
            if len(item) > 90:
                raise ValueError(
                    f"bullets[{index}] exceeds 90 characters "
                    f"(observed={len(item)})."
                )
            cleaned.append(item)
        return cleaned

    @field_validator("cta_label")
    @classmethod
    def _normalize_cta_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("cta_label must be non-empty.")
        return "Learn more"


class PreSalesReviewWallFitPack(StrictContract):
    title: str = Field(min_length=1)
    button_label: str = Field(min_length=1)


class PreSalesFloatingCtaFitPack(StrictContract):
    label: str = Field(min_length=1)

    @field_validator("label")
    @classmethod
    def _normalize_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("label must be non-empty.")
        return "Learn more"


class PreSalesReviewSlideFitPack(StrictContract):
    text: str = Field(min_length=1)
    author: str = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    verified: bool | None = None


class PreSalesListicleFitPack(StrictContract):
    hero: PreSalesHeroFitPack
    reasons: list[PreSalesReasonFitPack] = Field(min_length=5)
    marquee: list[str] = Field(min_length=1)
    pitch: PreSalesPitchFitPack
    reviews: list[PreSalesReviewSlideFitPack] = Field(default_factory=list)
    review_wall: PreSalesReviewWallFitPack
    floating_cta: PreSalesFloatingCtaFitPack

    @field_validator("marquee")
    @classmethod
    def _validate_marquee(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"marquee[{index}] must be non-empty.")
            if len(item) > 24:
                raise ValueError(
                    f"marquee[{index}] exceeds 24 characters "
                    f"(observed={len(item)})."
                )
            word_count = len(_WORD_RE.findall(item))
            if word_count < 1 or word_count > 4:
                raise ValueError(
                    f"marquee[{index}] must contain 1-4 words (observed={word_count})."
                )
            cleaned.append(item)
        return cleaned


class TemplatePatchOperation(StrictContract):
    component_type: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    value: Any


class StrategyV2TemplateBridgeV1(StrictContract):
    bridge_version: str = Field(min_length=1)
    angle_run_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    source: dict[str, Any]
    normalized_sections: dict[str, Any]
    template_fit_pack: TemplateFitPack
    template_patch: list[TemplatePatchOperation] = Field(min_length=1)
    copy_pack: dict[str, Any]
    residual_copy: dict[str, Any]
    validation_report: dict[str, Any]
    provenance: dict[str, Any]


def _template_contract_model_for_template_id(template_id: str):
    if template_id == "sales-pdp":
        return TemplateFitPack
    if template_id == "pre-sales-listicle":
        return PreSalesListicleFitPack
    supported = ", ".join(sorted(_SUPPORTED_TEMPLATE_IDS))
    raise StrategyV2DecisionError(
        f"Unsupported template_id for Strategy V2 template payload validation: {template_id}. "
        f"Supported template IDs: {supported}."
    )


def inspect_strategy_v2_template_payload_validation(
    *,
    template_id: str,
    payload_fields: dict[str, Any],
    max_items: int = 200,
) -> dict[str, Any]:
    model_cls = _template_contract_model_for_template_id(template_id)
    try:
        validated_fields = model_cls.model_validate(payload_fields).model_dump(mode="python")
    except ValidationError as exc:
        full_errors = exc.errors()
        reported_errors: list[dict[str, str]] = []
        for row in full_errors[:max_items]:
            location = ".".join(str(part) for part in row.get("loc", [])) or "<root>"
            message = str(row.get("msg") or "invalid value")
            error_type = str(row.get("type") or "unknown")
            reported_errors.append(
                {
                    "loc": location,
                    "msg": message,
                    "type": error_type,
                }
            )
        return {
            "valid": False,
            "validated_fields": None,
            "error_count": len(full_errors),
            "truncated_error_count": max(0, len(full_errors) - len(reported_errors)),
            "error_types": dict(Counter(str(row.get("type") or "unknown") for row in full_errors)),
            "errors": reported_errors,
        }
    return {
        "valid": True,
        "validated_fields": validated_fields,
        "error_count": 0,
        "truncated_error_count": 0,
        "error_types": {},
        "errors": [],
    }


def _format_pydantic_validation_errors(exc: ValidationError, *, max_items: int = 8) -> str:
    fragments: list[str] = []
    for row in exc.errors()[:max_items]:
        location = ".".join(str(part) for part in row.get("loc", [])) or "<root>"
        message = str(row.get("msg") or "invalid value")
        fragments.append(f"{location}: {message}")
    if not fragments:
        return "unknown validation error"
    if len(exc.errors()) > max_items:
        fragments.append(f"... +{len(exc.errors()) - max_items} more")
    return "; ".join(fragments)


def validate_strategy_v2_template_payload_fields(
    *,
    template_id: str,
    payload_fields: dict[str, Any],
) -> dict[str, Any]:
    report = inspect_strategy_v2_template_payload_validation(
        template_id=template_id,
        payload_fields=payload_fields,
        max_items=8,
    )
    if bool(report.get("valid")):
        validated_fields = report.get("validated_fields")
        if isinstance(validated_fields, dict):
            if template_id == "pre-sales-listicle":
                return _normalize_pre_sales_template_payload_fields(validated_fields)
            hero = validated_fields.get("hero")
            if isinstance(hero, dict):
                primary_cta_label = str(hero.get("primary_cta_label") or "").strip()
                if primary_cta_label:
                    if "{price}" in primary_cta_label and "$" in primary_cta_label:
                        raise StrategyV2DecisionError(
                            "TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; "
                            "errors=hero.primary_cta_label: use the exact {price} token without a literal dollar sign. "
                            "Remediation: write CTA labels like 'Get the handbook - {price}', not '... - ${price}'."
                        )
                    if _LITERAL_PRICE_RE.search(primary_cta_label) and "{price}" not in primary_cta_label:
                        raise StrategyV2DecisionError(
                            "TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; "
                            "errors=hero.primary_cta_label: literal CTA prices are not allowed; use the exact {price} token. "
                            "Remediation: write CTA labels like 'Get the handbook - {price}', not '... - $49'."
                        )
            return validated_fields
        raise StrategyV2DecisionError(
            "Template payload validator returned valid=True without normalized fields."
        )
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    fragments = [
        f"{row.get('loc')}: {row.get('msg')}"
        for row in errors
        if isinstance(row, dict)
    ]
    truncated_count = int(report.get("truncated_error_count") or 0)
    if truncated_count > 0:
        fragments.append(f"... +{truncated_count} more")
    summary = "; ".join(fragment for fragment in fragments if fragment) or "unknown validation error"
    raise StrategyV2DecisionError(
        "TEMPLATE_PAYLOAD_VALIDATION: "
        f"template_id={template_id}; "
        f"errors={summary}. "
        "Remediation: return template_payload that exactly matches the required template contract."
    )


def _coerce_non_empty_text(value: Any) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return ""


def _clip_text(value: str, *, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned or max_len <= 0:
        return ""
    if len(cleaned) <= max_len:
        return cleaned
    clipped = cleaned[:max_len].rstrip()
    last_space = clipped.rfind(" ")
    if last_space >= max_len // 2:
        clipped = clipped[:last_space].rstrip()
    return clipped.rstrip(" ,;:-")


def _clip_sentences(value: str, *, max_sentences: int, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        return ""
    if max_sentences > 0:
        sentence_chunks = [
            match.group(0).strip()
            for match in _SENTENCE_CHUNK_RE.finditer(cleaned)
            if match.group(0).strip()
        ]
        if sentence_chunks:
            cleaned = " ".join(sentence_chunks[:max_sentences])
    return _clip_text(cleaned, max_len=max_len)


def _compact_phrase(value: str, *, max_words: int, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        return ""
    if max_words > 0:
        cleaned = " ".join(cleaned.split()[:max_words])
    return _clip_text(cleaned, max_len=max_len)


def _coerce_non_empty_text_list(
    value: Any,
    *,
    max_items: int | None = None,
) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            values.append(cleaned)
    elif isinstance(value, list):
        for item in value:
            cleaned = _coerce_non_empty_text(item)
            if cleaned:
                values.append(cleaned)
    if max_items is not None and max_items > 0:
        return values[:max_items]
    return values


def _coerce_story_bullets(raw: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if isinstance(item, dict):
            title = _first_non_empty(
                [
                    _coerce_non_empty_text(item.get("title")),
                    _coerce_non_empty_text(item.get("label")),
                    _coerce_non_empty_text(item.get("headline")),
                    _coerce_non_empty_text(item.get("feature")),
                ]
            )
            body = _first_non_empty(
                [
                    _coerce_non_empty_text(item.get("body")),
                    _coerce_non_empty_text(item.get("description")),
                    _coerce_non_empty_text(item.get("text")),
                    _coerce_non_empty_text(item.get("copy")),
                ]
            )
            if title and body:
                rows.append({"title": _clip_text(title, max_len=56), "body": _clip_text(body, max_len=160)})
                continue
        cleaned = _coerce_non_empty_text(item)
        if not cleaned:
            continue
        if ":" in cleaned:
            left, right = cleaned.split(":", 1)
            title = left.strip()
            body = right.strip()
            if title and body:
                rows.append({"title": _clip_text(title, max_len=56), "body": _clip_text(body, max_len=160)})
    return rows


def _looks_like_primary_solution_label(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    primary_tokens = (
        "our ",
        "ours",
        "workflow",
        "triage",
        "structured",
        "handbook",
        "approach",
        "system",
        "solution",
        "method",
        "new way",
    )
    return any(token in lowered for token in primary_tokens)


def _looks_like_alternative_solution_label(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    alternative_tokens = (
        "typical",
        "other",
        "alternative",
        "standard",
        "generic",
        "random",
        "scattered",
        "checking",
        "guide",
        "course",
        "old way",
        "marketplace",
        "legacy",
        "disposable",
    )
    return any(token in lowered for token in alternative_tokens)


def _resolve_comparison_pair(*, left_value: str, right_value: str) -> tuple[str, str]:
    left = left_value.strip()
    right = right_value.strip()
    if left and not right:
        return left, left
    if right and not left:
        return right, right
    if not left and not right:
        return "", ""

    left_is_primary = _looks_like_primary_solution_label(left)
    right_is_primary = _looks_like_primary_solution_label(right)
    left_is_alternative = _looks_like_alternative_solution_label(left)
    right_is_alternative = _looks_like_alternative_solution_label(right)

    if left_is_primary and not right_is_primary:
        return left, right
    if right_is_primary and not left_is_primary:
        return right, left
    if left_is_alternative and not right_is_alternative:
        return right, left
    if right_is_alternative and not left_is_alternative:
        return left, right
    # Default orientation: left is baseline, right is improved/system side.
    return right, left


def _normalize_comparison_title(*, raw_title: str, columns: dict[str, str]) -> str:
    cleaned = raw_title.strip()
    pup = _coerce_non_empty_text(columns.get("pup"))
    disposable = _coerce_non_empty_text(columns.get("disposable"))
    if not cleaned:
        if pup and disposable:
            return f"{pup} vs. {disposable}"
        return ""

    parts = _VS_SPLIT_RE.split(cleaned, maxsplit=1)
    if len(parts) != 2:
        return cleaned

    normalized_left, normalized_right = _resolve_comparison_pair(
        left_value=parts[0].strip(),
        right_value=parts[1].strip(),
    )
    left = normalized_left or pup or parts[0].strip()
    right = normalized_right or disposable or parts[1].strip()
    if not left or not right:
        return cleaned
    return f"{left} vs. {right}"


def _normalize_guarantee_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        return ""
    if re.search(r"workflow\s+fit", cleaned, re.IGNORECASE):
        day_match = re.search(r"(\d+)\s*[- ]?\s*day", cleaned, re.IGNORECASE)
        if day_match:
            return f"{day_match.group(1)}-Day Risk Free Guarantee"
        return "Risk Free Guarantee"
    return cleaned


def _coerce_comparison_columns(raw: Any) -> dict[str, str]:
    default_columns = {"pup": "OUR APPROACH", "disposable": "ALTERNATIVE"}
    if isinstance(raw, dict):
        explicit_pup = _coerce_non_empty_text(raw.get("pup"))
        explicit_disposable = _coerce_non_empty_text(raw.get("disposable"))
        if explicit_pup and explicit_disposable:
            return {"pup": explicit_pup, "disposable": explicit_disposable}

        left = _first_non_empty(
            [
                _coerce_non_empty_text(raw.get("left")),
                _coerce_non_empty_text(raw.get("col1")),
            ]
        )
        right = _first_non_empty(
            [
                _coerce_non_empty_text(raw.get("right")),
                _coerce_non_empty_text(raw.get("col2")),
            ]
        )
        inferred_pup, inferred_disposable = _resolve_comparison_pair(left_value=left, right_value=right)
        pup = _first_non_empty([explicit_pup, inferred_pup])
        disposable = _first_non_empty([explicit_disposable, inferred_disposable])
        return {
            "pup": pup or default_columns["pup"],
            "disposable": disposable or default_columns["disposable"],
        }
    if isinstance(raw, list) and len(raw) >= 2:
        left = _coerce_non_empty_text(raw[0])
        if len(raw) >= 3:
            right = _coerce_non_empty_text(raw[-1])
        else:
            right = _coerce_non_empty_text(raw[1])
        pup, disposable = _resolve_comparison_pair(left_value=left, right_value=right)
        return {
            "pup": pup or default_columns["pup"],
            "disposable": disposable or default_columns["disposable"],
        }
    return default_columns


def _coerce_comparison_rows(raw: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return rows
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            values = item.get("values")
            values_list = values if isinstance(values, list) else []
            values_left = _coerce_non_empty_text(values_list[0]) if len(values_list) >= 1 else ""
            values_right = _coerce_non_empty_text(values_list[-1]) if len(values_list) >= 2 else values_left
            label = _first_non_empty(
                [
                    _coerce_non_empty_text(item.get("label")),
                    _coerce_non_empty_text(item.get("feature")),
                    _coerce_non_empty_text(item.get("title")),
                    _coerce_non_empty_text(item.get("left")),
                    _coerce_non_empty_text(item.get("right")),
                ]
            )
            left_value = _first_non_empty(
                [
                    _coerce_non_empty_text(item.get("them")),
                    _coerce_non_empty_text(item.get("left")),
                    _coerce_non_empty_text(item.get("col1")),
                    _coerce_non_empty_text(item.get("disposable")),
                    values_left,
                ]
            )
            right_value = _first_non_empty(
                [
                    _coerce_non_empty_text(item.get("us")),
                    _coerce_non_empty_text(item.get("right")),
                    _coerce_non_empty_text(item.get("col2")),
                    _coerce_non_empty_text(item.get("pup")),
                    values_right,
                ]
            )
            inferred_pup, inferred_disposable = _resolve_comparison_pair(
                left_value=left_value,
                right_value=right_value,
            )
            pup = _first_non_empty([_coerce_non_empty_text(item.get("pup")), inferred_pup])
            disposable = _first_non_empty(
                [_coerce_non_empty_text(item.get("disposable")), inferred_disposable]
            )
            if not label and (pup or disposable):
                label = _first_non_empty([left_value, right_value, f"Comparison item {index + 1}"])
            if label and pup and disposable:
                rows.append({"label": label, "pup": pup, "disposable": disposable})
            continue
        if isinstance(item, list) and len(item) >= 2:
            # Support legacy row shape [disposable, pup] where no explicit label is provided.
            if len(item) == 2:
                label = _first_non_empty(
                    [
                        _coerce_non_empty_text(item[0]),
                        f"Comparison item {index + 1}",
                    ]
                )
                left_value = _coerce_non_empty_text(item[0])
                right_value = _coerce_non_empty_text(item[1])
            else:
                label = _coerce_non_empty_text(item[0])
                left_value = _coerce_non_empty_text(item[1])
                right_value = _coerce_non_empty_text(item[2])
            pup, disposable = _resolve_comparison_pair(left_value=left_value, right_value=right_value)
            if label and pup and disposable:
                rows.append({"label": label, "pup": pup, "disposable": disposable})
    return rows


def _coerce_faq_items(raw: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return items
    for row in raw:
        if not isinstance(row, dict):
            continue
        question = _first_non_empty(
            [
                _coerce_non_empty_text(row.get("question")),
                _coerce_non_empty_text(row.get("q")),
            ]
        )
        answer = _first_non_empty(
            [
                _coerce_non_empty_text(row.get("answer")),
                _coerce_non_empty_text(row.get("a")),
            ]
        )
        if question and answer:
            items.append({"question": question, "answer": answer})
    return items


def _coerce_faq_pills(raw: Any) -> list[dict[str, str]]:
    pills: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return pills
    for row in raw:
        if not isinstance(row, dict):
            continue
        label = _first_non_empty(
            [
                _coerce_non_empty_text(row.get("label")),
                _coerce_non_empty_text(row.get("question")),
                _coerce_non_empty_text(row.get("q")),
            ]
        )
        answer = _first_non_empty(
            [
                _coerce_non_empty_text(row.get("answer")),
                _coerce_non_empty_text(row.get("a")),
            ]
        )
        if label and answer:
            pills.append({"label": label, "answer": answer})
    return pills


def _prune_keys(payload: dict[str, Any], *, allowed: set[str]) -> dict[str, Any]:
    return {key: payload[key] for key in allowed if key in payload}


def upgrade_strategy_v2_template_payload_fields(
    *,
    template_id: str,
    payload_fields: dict[str, Any],
) -> dict[str, Any]:
    upgraded = deepcopy(payload_fields)
    if template_id == "pre-sales-listicle":
        hero = upgraded.get("hero")
        if not isinstance(hero, dict):
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: hero must be an object.")
        hero_title = _clip_text(_coerce_non_empty_text(hero.get("title")), max_len=90)
        if not hero_title:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: hero.title is required.")
        hero["title"] = hero_title
        hero_subtitle = _clip_sentences(
            _first_non_empty(
                [
                    _coerce_non_empty_text(hero.get("subtitle")),
                    hero_title,
                ]
            ),
            max_sentences=2,
            max_len=140,
        )
        if not hero_subtitle:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: hero.subtitle is required.")
        hero["subtitle"] = hero_subtitle
        badges = hero.get("badges")
        if not isinstance(badges, list) or not badges:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: hero.badges must be a non-empty list.")
        for idx, raw_badge in enumerate(badges):
            if not isinstance(raw_badge, dict):
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: hero.badges[{idx}] must be an object."
                )
            label = str(raw_badge.get("label") or "").strip()
            if not label:
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: hero.badges[{idx}].label is required."
                )
            icon = raw_badge.get("icon")
            if not isinstance(icon, dict):
                icon = {}
                raw_badge["icon"] = icon
            alt = str(icon.get("alt") or raw_badge.get("iconAlt") or f"{label} icon").strip()
            prompt = str(icon.get("prompt") or raw_badge.get("prompt") or f"icon of {label}").strip()
            if not alt:
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: hero.badges[{idx}].icon.alt is required."
                )
            if not prompt:
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: hero.badges[{idx}].icon.prompt is required."
                )
            icon["alt"] = _clip_text(alt, max_len=240)
            icon["prompt"] = _clip_text(prompt, max_len=420)
            value = _coerce_non_empty_text(raw_badge.get("value"))
            if value:
                raw_badge["value"] = _clip_text(value, max_len=24)
            else:
                raw_badge.pop("value", None)

        reasons = upgraded.get("reasons")
        if not isinstance(reasons, list) or not reasons:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: reasons must be a non-empty list.")
        for idx, raw_reason in enumerate(reasons):
            if not isinstance(raw_reason, dict):
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: reasons[{idx}] must be an object."
                )
            title = str(raw_reason.get("title") or "").strip()
            if not title:
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: reasons[{idx}].title is required."
                )
            raw_reason["title"] = _clip_text(title, max_len=72)
            body = _clip_sentences(
                _first_non_empty(
                    [
                        _coerce_non_empty_text(raw_reason.get("body")),
                        _coerce_non_empty_text(raw_reason.get("description")),
                        _coerce_non_empty_text(raw_reason.get("text")),
                        _coerce_non_empty_text(raw_reason.get("copy")),
                    ]
                ),
                max_sentences=3,
                max_len=360,
            )
            if not body:
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: reasons[{idx}].body is required."
                )
            raw_reason["body"] = body
            image = raw_reason.get("image")
            if not isinstance(image, dict):
                image = {}
                raw_reason["image"] = image
            alt = str(image.get("alt") or f"{title} visual").strip()
            if not alt:
                raise StrategyV2DecisionError(
                    f"Legacy pre-sales payload upgrade failed: reasons[{idx}].image.alt is required."
                )
            image["alt"] = _clip_text(alt, max_len=240)
            prompt = image.get("prompt")
            if isinstance(prompt, str) and prompt.strip():
                image["prompt"] = _clip_text(prompt.strip(), max_len=420)
            else:
                image.pop("prompt", None)

        pitch = upgraded.get("pitch")
        if not isinstance(pitch, dict):
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: pitch must be an object.")
        pitch_title = _clip_text(_coerce_non_empty_text(pitch.get("title")), max_len=78)
        if not pitch_title:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: pitch.title is required.")
        pitch["title"] = pitch_title
        pitch_bullets = [
            clipped
            for clipped in (
                _clip_text(item, max_len=90) for item in _coerce_non_empty_text_list(pitch.get("bullets"))
            )
            if clipped
        ]
        if len(pitch_bullets) < 4:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: pitch.bullets must include at least 4 items.")
        pitch["bullets"] = pitch_bullets[:4]
        pitch["cta_label"] = _first_non_empty(
            [
                _coerce_non_empty_text(pitch.get("cta_label")),
                _coerce_non_empty_text(pitch.get("ctaLabel")),
                "Learn more",
            ]
        )
        image = pitch.get("image")
        if not isinstance(image, dict):
            image = {}
            pitch["image"] = image
        pitch_title = str(pitch.get("title") or "").strip()
        alt = str(image.get("alt") or f"{pitch_title or 'Pitch'} visual").strip()
        if not alt:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: pitch.image.alt is required.")
        image["alt"] = _clip_text(alt, max_len=240)
        prompt = image.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            image["prompt"] = _clip_text(prompt.strip(), max_len=420)
        else:
            image.pop("prompt", None)
        marquee_rows = _coerce_non_empty_text_list(upgraded.get("marquee"))
        normalized_marquee: list[str] = []
        seen_marquee: set[str] = set()
        for row in marquee_rows:
            compact = _compact_phrase(row, max_words=3, max_len=24)
            if not compact:
                continue
            dedupe_key = compact.lower()
            if dedupe_key in seen_marquee:
                continue
            seen_marquee.add(dedupe_key)
            normalized_marquee.append(compact)
        if not normalized_marquee:
            raise StrategyV2DecisionError("Legacy pre-sales payload upgrade failed: marquee must include at least one compact item.")
        upgraded["marquee"] = normalized_marquee
        return upgraded

    if template_id == "sales-pdp":
        hero = upgraded.get("hero")
        if not isinstance(hero, dict):
            hero = {}
            upgraded["hero"] = hero
        hero["purchase_title"] = _first_non_empty(
            [
                _coerce_non_empty_text(hero.get("purchase_title")),
                _coerce_non_empty_text(hero.get("headline")),
                _coerce_non_empty_text(hero.get("title")),
            ]
        )
        hero["primary_cta_label"] = _first_non_empty(
            [
                _coerce_non_empty_text(hero.get("primary_cta_label")),
                _coerce_non_empty_text(
                    ((upgraded.get("cta_primary") or {}) if isinstance(upgraded.get("cta_primary"), dict) else {}).get(
                        "label"
                    )
                ),
                _coerce_non_empty_text(
                    ((upgraded.get("cta_close") or {}) if isinstance(upgraded.get("cta_close"), dict) else {}).get(
                        "cta_label"
                    )
                ),
            ]
        )
        hero_subbullets = hero.get("primary_cta_subbullets")
        if not isinstance(hero_subbullets, list) or len(hero_subbullets) < 2:
            hero_subbullets = _coerce_non_empty_text_list(
                ((upgraded.get("whats_inside") or {}) if isinstance(upgraded.get("whats_inside"), dict) else {}).get(
                    "benefits"
                ),
                max_items=2,
            )
        if len(hero_subbullets) >= 2:
            hero["primary_cta_subbullets"] = hero_subbullets[:2]
        hero.pop("headline", None)
        hero.pop("subheadline", None)
        hero.pop("primary_cta_url", None)
        hero.pop("trust_badges", None)

        problem = upgraded.get("problem")
        if not isinstance(problem, dict):
            legacy_problem = upgraded.get("problem_recap")
            problem = dict(legacy_problem) if isinstance(legacy_problem, dict) else {}
            upgraded["problem"] = problem
        problem["title"] = _first_non_empty(
            [
                _coerce_non_empty_text(problem.get("title")),
                _coerce_non_empty_text(problem.get("heading")),
                _coerce_non_empty_text(problem.get("headline")),
            ]
        )
        paragraphs = _coerce_non_empty_text_list(problem.get("paragraphs"))
        if not paragraphs:
            paragraphs = _coerce_non_empty_text_list(problem.get("body"))
        if not paragraphs:
            errors = problem.get("errors")
            if isinstance(errors, list):
                derived: list[str] = []
                for row in errors:
                    if not isinstance(row, dict):
                        continue
                    number = row.get("number")
                    prefix = f"Error {number}: " if isinstance(number, int) else ""
                    title = _coerce_non_empty_text(row.get("title"))
                    body = _coerce_non_empty_text(row.get("body"))
                    sentence = _first_non_empty(
                        [
                            f"{prefix}{title}: {body}" if title and body else "",
                            f"{prefix}{body}" if body else "",
                            f"{prefix}{title}" if title else "",
                        ]
                    )
                    if sentence:
                        derived.append(sentence)
                if derived:
                    paragraphs = derived
        if not paragraphs:
            paragraphs = _coerce_non_empty_text_list(upgraded.get("pain_bullets"))
        if paragraphs:
            problem["paragraphs"] = paragraphs
            problem["emphasis_line"] = _first_non_empty(
                [
                    _coerce_non_empty_text(problem.get("emphasis_line")),
                    _coerce_non_empty_text(problem.get("headline")),
                    paragraphs[-1],
                ]
            )
        problem.pop("heading", None)
        problem.pop("headline", None)
        problem.pop("body", None)
        problem.pop("errors", None)
        problem.pop("problem_image_alt", None)

        mechanism = upgraded.get("mechanism")
        if not isinstance(mechanism, dict):
            mechanism = {}
            upgraded["mechanism"] = mechanism
        mechanism["title"] = _first_non_empty(
            [
                _coerce_non_empty_text(mechanism.get("title")),
                _coerce_non_empty_text(mechanism.get("heading")),
                _coerce_non_empty_text(mechanism.get("headline")),
            ]
        )
        mechanism_paragraphs = _coerce_non_empty_text_list(mechanism.get("paragraphs"))
        if not mechanism_paragraphs:
            mechanism_paragraphs = _coerce_non_empty_text_list(mechanism.get("intro"))
        if not mechanism_paragraphs:
            mechanism_paragraphs = _coerce_non_empty_text_list(mechanism.get("subheadline"))
        if not mechanism_paragraphs:
            mechanism_paragraphs = _coerce_non_empty_text_list(mechanism.get("body"))
        if mechanism_paragraphs:
            mechanism["paragraphs"] = mechanism_paragraphs
        bullets = _coerce_story_bullets(mechanism.get("bullets"))
        if bullets:
            mechanism["bullets"] = bullets[:6]
        if not mechanism_paragraphs and bullets:
            first_bullet = bullets[0]
            fallback_paragraph = _coerce_non_empty_text(first_bullet.get("body"))
            if fallback_paragraph:
                mechanism["paragraphs"] = [fallback_paragraph]
        callout = mechanism.get("callout")
        if not isinstance(callout, dict):
            callout = {}
            mechanism["callout"] = callout
        callout["left_title"] = _first_non_empty(
            [
                _coerce_non_empty_text(callout.get("left_title")),
                _coerce_non_empty_text(callout.get("leftTitle")),
            ]
        )
        callout["left_body"] = _first_non_empty(
            [
                _coerce_non_empty_text(callout.get("left_body")),
                _coerce_non_empty_text(callout.get("leftBody")),
            ]
        )
        callout["right_title"] = _first_non_empty(
            [
                _coerce_non_empty_text(callout.get("right_title")),
                _coerce_non_empty_text(callout.get("rightTitle")),
            ]
        )
        callout["right_body"] = _first_non_empty(
            [
                _coerce_non_empty_text(callout.get("right_body")),
                _coerce_non_empty_text(callout.get("rightBody")),
            ]
        )
        callout.pop("leftTitle", None)
        callout.pop("leftBody", None)
        callout.pop("rightTitle", None)
        callout.pop("rightBody", None)
        comparison = mechanism.get("comparison")
        if not isinstance(comparison, dict):
            comparison = {}
            mechanism["comparison"] = comparison
        comparison["badge"] = "US vs THEM"
        comparison["title"] = _first_non_empty(
            [
                _coerce_non_empty_text(comparison.get("title")),
                _coerce_non_empty_text(mechanism.get("title")),
            ]
        )
        comparison["swipe_hint"] = _first_non_empty(
            [
                _coerce_non_empty_text(comparison.get("swipe_hint")),
                _coerce_non_empty_text(comparison.get("swipeHint")),
                "Swipe right to see comparison ->",
            ]
        )
        comparison.pop("swipeHint", None)
        comparison["columns"] = _coerce_comparison_columns(comparison.get("columns"))
        comparison["title"] = _normalize_comparison_title(
            raw_title=_coerce_non_empty_text(comparison.get("title")),
            columns=comparison["columns"],
        )
        comparison_rows = _coerce_comparison_rows(comparison.get("rows"))
        if comparison_rows:
            comparison["rows"] = comparison_rows
        callout["left_title"] = _first_non_empty(
            [
                _coerce_non_empty_text(callout.get("left_title")),
                _coerce_non_empty_text(comparison["columns"].get("disposable")),
            ]
        )
        callout["right_title"] = _first_non_empty(
            [
                _coerce_non_empty_text(callout.get("right_title")),
                _coerce_non_empty_text(comparison["columns"].get("pup")),
            ]
        )
        if comparison_rows:
            if not _coerce_non_empty_text(callout.get("left_body")):
                callout["left_body"] = f"{comparison_rows[0]['label']}: {comparison_rows[0]['disposable']}"
            if not _coerce_non_empty_text(callout.get("right_body")):
                callout["right_body"] = f"{comparison_rows[0]['label']}: {comparison_rows[0]['pup']}"
        mechanism.pop("heading", None)
        mechanism.pop("headline", None)
        mechanism.pop("intro", None)
        mechanism.pop("subheadline", None)
        mechanism.pop("body", None)

        social_proof = upgraded.get("social_proof")
        if not isinstance(social_proof, dict):
            social_proof = {}
            upgraded["social_proof"] = social_proof
        social_proof["badge"] = _first_non_empty(
            [
                _coerce_non_empty_text(social_proof.get("badge")),
                "SOCIAL PROOF",
            ]
        )
        social_proof["title"] = _first_non_empty(
            [
                _coerce_non_empty_text(social_proof.get("title")),
                _coerce_non_empty_text(social_proof.get("heading")),
                _coerce_non_empty_text(social_proof.get("headline")),
            ]
        )
        social_proof["rating_label"] = _first_non_empty(
            [
                _coerce_non_empty_text(social_proof.get("rating_label")),
                _coerce_non_empty_text(social_proof.get("ratingLabel")),
                "Verified customer feedback",
            ]
        )
        social_proof_summary = _coerce_non_empty_text(social_proof.get("summary"))
        if not social_proof_summary:
            testimonials = social_proof.get("testimonials")
            if isinstance(testimonials, list):
                for row in testimonials:
                    if not isinstance(row, dict):
                        continue
                    social_proof_summary = _first_non_empty(
                        [
                            _coerce_non_empty_text(row.get("quote")),
                            _coerce_non_empty_text(row.get("text")),
                        ]
                    )
                    if social_proof_summary:
                        break
        if not social_proof_summary:
            social_proof_summary = _coerce_non_empty_text(social_proof.get("proof_note"))
        if social_proof_summary:
            social_proof["summary"] = social_proof_summary
        social_proof.pop("heading", None)
        social_proof.pop("headline", None)
        social_proof.pop("intro", None)
        social_proof.pop("proof_bar", None)
        social_proof.pop("testimonials", None)
        social_proof.pop("proof_note", None)
        social_proof.pop("proof_bar_items", None)

        whats_inside = upgraded.get("whats_inside")
        if not isinstance(whats_inside, dict):
            whats_inside = {}
            upgraded["whats_inside"] = whats_inside
        normalized_benefits: list[str] = []
        benefits = whats_inside.get("benefits")
        if isinstance(benefits, list):
            for row in benefits:
                if isinstance(row, dict):
                    question = _coerce_non_empty_text(row.get("question"))
                    answer = _coerce_non_empty_text(row.get("answer"))
                    value = _first_non_empty(
                        [
                            _coerce_non_empty_text(row.get("title")),
                            _coerce_non_empty_text(row.get("body")),
                            _coerce_non_empty_text(row.get("text")),
                            _coerce_non_empty_text(row.get("description")),
                            _coerce_non_empty_text(row.get("label")),
                            question,
                            answer,
                        ]
                    )
                else:
                    value = _coerce_non_empty_text(row)
                if value:
                    normalized_benefits.append(value)
            if normalized_benefits:
                whats_inside["benefits"] = normalized_benefits[:_HERO_BENEFIT_COUNT]
        whats_inside["offer_helper_text"] = _first_non_empty(
            [
                _coerce_non_empty_text(whats_inside.get("offer_helper_text")),
                _coerce_non_empty_text(whats_inside.get("offerHelperText")),
                _coerce_non_empty_text(whats_inside.get("intro")),
                _coerce_non_empty_text(whats_inside.get("headline")),
                normalized_benefits[0] if normalized_benefits else "",
            ]
        )
        whats_inside.pop("heading", None)
        whats_inside.pop("headline", None)
        whats_inside.pop("subheadline", None)
        whats_inside.pop("intro", None)
        whats_inside.pop("main_product_title", None)
        whats_inside.pop("main_product_body", None)

        bonus = upgraded.get("bonus")
        if not isinstance(bonus, dict):
            bonus = {}
            upgraded["bonus"] = bonus
        bonus["free_gifts_title"] = _first_non_empty(
            [
                _coerce_non_empty_text(bonus.get("free_gifts_title")),
                _coerce_non_empty_text(bonus.get("heading")),
                _coerce_non_empty_text(bonus.get("headline")),
                "Bonus Stack + Value",
            ]
        )
        bonus_body = _coerce_non_empty_text(bonus.get("free_gifts_body"))
        if not bonus_body:
            bonus_body = _coerce_non_empty_text(
                _first_non_empty(
                    _coerce_non_empty_text_list(
                        [bonus.get("body"), bonus.get("description"), bonus.get("intro")]
                    )
                )
            )
        if not bonus_body:
            bonus_body = _coerce_non_empty_text(bonus.get("total_value_statement"))
        if not bonus_body:
            bonus_items = bonus.get("free_gifts") or bonus.get("items")
            if isinstance(bonus_items, list):
                item_names: list[str] = []
                for item in bonus_items:
                    if not isinstance(item, dict):
                        continue
                    name = _first_non_empty(
                        [
                            _coerce_non_empty_text(item.get("title")),
                            _coerce_non_empty_text(item.get("name")),
                            _coerce_non_empty_text(item.get("label")),
                        ]
                    )
                    if name:
                        item_names.append(name)
                if item_names:
                    bonus_body = f"Includes: {', '.join(item_names[:4])}."
        if bonus_body:
            bonus["free_gifts_body"] = bonus_body[:220].rstrip()
        bonus.pop("heading", None)
        bonus.pop("headline", None)
        bonus.pop("items", None)
        bonus.pop("free_gifts", None)
        bonus.pop("total_value", None)
        bonus.pop("total_value_statement", None)
        bonus.pop("your_price", None)
        bonus.pop("price_today", None)
        bonus.pop("free_gifts_label", None)

        guarantee = upgraded.get("guarantee")
        if not isinstance(guarantee, dict):
            guarantee = {}
            upgraded["guarantee"] = guarantee
        guarantee["title"] = _first_non_empty(
            [
                _normalize_guarantee_title(_coerce_non_empty_text(guarantee.get("title"))),
                _normalize_guarantee_title(_coerce_non_empty_text(guarantee.get("heading"))),
                _normalize_guarantee_title(_coerce_non_empty_text(guarantee.get("headline"))),
                _normalize_guarantee_title(_coerce_non_empty_text(guarantee.get("badge_text"))),
            ]
        )
        guarantee_paragraphs = _coerce_non_empty_text_list(guarantee.get("paragraphs"))
        if not guarantee_paragraphs:
            guarantee_paragraphs = _coerce_non_empty_text_list(guarantee.get("body"))
        if guarantee_paragraphs:
            guarantee["paragraphs"] = guarantee_paragraphs
            guarantee["why_title"] = _first_non_empty(
                [
                    _coerce_non_empty_text(guarantee.get("why_title")),
                    "Why this guarantee exists",
                ]
            )
            guarantee["why_body"] = _first_non_empty(
                [
                    _coerce_non_empty_text(guarantee.get("why_body")),
                    guarantee_paragraphs[-1],
                ]
            )
            guarantee["closing_line"] = _first_non_empty(
                [
                    _coerce_non_empty_text(guarantee.get("closing_line")),
                    guarantee_paragraphs[-1],
                ]
            )
        guarantee.pop("heading", None)
        guarantee.pop("headline", None)
        guarantee.pop("body", None)
        guarantee.pop("duration_days", None)
        guarantee.pop("type", None)
        guarantee.pop("badge_label", None)
        guarantee.pop("badge_text", None)
        guarantee.pop("cta_label", None)
        guarantee.pop("cta_url", None)

        faq = upgraded.get("faq")
        if not isinstance(faq, dict):
            faq = {}
            upgraded["faq"] = faq
        faq["title"] = _first_non_empty(
            [
                _coerce_non_empty_text(faq.get("title")),
                _coerce_non_empty_text(faq.get("heading")),
                _coerce_non_empty_text(faq.get("headline")),
                "FAQ",
            ]
        )
        faq_items = _coerce_faq_items(faq.get("items"))
        if faq_items:
            faq["items"] = faq_items
        faq.pop("heading", None)
        faq.pop("headline", None)

        cta_close = upgraded.get("cta_close")
        if isinstance(cta_close, dict):
            upgraded["cta_close"] = _first_non_empty(
                [
                    _coerce_non_empty_text(cta_close.get("cta_label")),
                    _coerce_non_empty_text(cta_close.get("label")),
                    _coerce_non_empty_text(cta_close.get("headline")),
                    _coerce_non_empty_text(cta_close.get("heading")),
                    _coerce_non_empty_text(cta_close.get("body")),
                    _coerce_non_empty_text(cta_close.get("ps")),
                ]
            )
        if not isinstance(upgraded.get("cta_close"), str) or not str(upgraded.get("cta_close") or "").strip():
            upgraded["cta_close"] = _first_non_empty(
                [
                    _coerce_non_empty_text(
                        ((upgraded.get("cta_primary") or {}) if isinstance(upgraded.get("cta_primary"), dict) else {}).get(
                            "label"
                        )
                    ),
                    _coerce_non_empty_text(hero.get("primary_cta_label")),
                ]
            )

        hero_subbullets = (
            hero.get("primary_cta_subbullets")
            if isinstance(hero.get("primary_cta_subbullets"), list)
            else []
        )
        if len(hero_subbullets) < 2:
            derived_subbullet_candidates: list[str] = []
            if isinstance(whats_inside.get("benefits"), list):
                derived_subbullet_candidates.extend(
                    _coerce_non_empty_text(row) for row in whats_inside.get("benefits") if _coerce_non_empty_text(row)
                )
            pain_bullets = upgraded.get("pain_bullets")
            if isinstance(pain_bullets, list):
                derived_subbullet_candidates.extend(
                    _coerce_non_empty_text(row) for row in pain_bullets if _coerce_non_empty_text(row)
                )
            trust_badges = hero.get("trust_badges")
            if isinstance(trust_badges, list):
                derived_subbullet_candidates.extend(
                    _coerce_non_empty_text(row) for row in trust_badges if _coerce_non_empty_text(row)
                )
            deduped: list[str] = []
            for row in derived_subbullet_candidates:
                if len(row) > 90:
                    continue
                if row and row not in deduped:
                    deduped.append(row)
                if len(deduped) >= 2:
                    break
            if len(deduped) >= 2:
                hero["primary_cta_subbullets"] = deduped[:2]

        # Remove known drift keys that violate strict contract.
        upgraded.pop("schema", None)
        upgraded.pop("template_id", None)
        upgraded.pop("product_name", None)
        upgraded.pop("product_subtitle", None)
        upgraded.pop("problem_recap", None)
        upgraded.pop("cta_primary", None)
        upgraded.pop("pricing", None)
        upgraded.pop("legal_disclaimer", None)
        upgraded.pop("problem_image_alt", None)
        upgraded.pop("pain_bullets", None)

        faq = upgraded.get("faq")
        faq_items = _coerce_faq_items(faq.get("items") if isinstance(faq, dict) else None)
        faq_pills = _coerce_faq_pills(upgraded.get("faq_pills"))
        if not faq_items and faq_pills:
            faq_items = [{"question": row["label"], "answer": row["answer"]} for row in faq_pills]
        if not faq_pills and faq_items:
            faq_pills = [{"label": row["question"], "answer": row["answer"]} for row in faq_items]
        if not faq_items or not faq_pills:
            raise StrategyV2DecisionError(
                "Legacy sales payload upgrade failed: faq_pills is missing and faq.items is unavailable."
            )
        if isinstance(faq, dict):
            faq["items"] = faq_items
        upgraded["faq_pills"] = faq_pills

        marquee_items = upgraded.get("marquee_items")
        if not isinstance(marquee_items, list) or not marquee_items:
            mechanism = upgraded.get("mechanism")
            whats_inside = upgraded.get("whats_inside")
            candidates: list[str] = []
            if isinstance(mechanism, dict):
                bullets = mechanism.get("bullets")
                if isinstance(bullets, list):
                    for bullet in bullets:
                        if isinstance(bullet, dict):
                            title = str(bullet.get("title") or "").strip()
                            if title:
                                candidates.append(title)
            if isinstance(whats_inside, dict):
                benefits = whats_inside.get("benefits")
                if isinstance(benefits, list):
                    candidates.extend(str(value).strip() for value in benefits if isinstance(value, str) and value.strip())
            upgraded["marquee_items"] = _derive_marquee_items(candidates=candidates, min_items=4, max_items=12)

        urgency_message = upgraded.get("urgency_message")
        if not isinstance(urgency_message, str) or not urgency_message.strip():
            urgency_source = _first_non_empty(
                [
                    str(upgraded.get("cta_close") or ""),
                    str(((upgraded.get("social_proof") or {}) if isinstance(upgraded.get("social_proof"), dict) else {}).get("summary") or ""),
                    str(((upgraded.get("hero") or {}) if isinstance(upgraded.get("hero"), dict) else {}).get("purchase_title") or ""),
                ]
            )
            urgency_message = _normalize_sales_urgency_message(urgency_source)
            if not urgency_message:
                raise StrategyV2DecisionError(
                    "Legacy sales payload upgrade failed: could not derive urgency_message."
                )
            upgraded["urgency_message"] = urgency_message
        else:
            upgraded["urgency_message"] = _normalize_sales_urgency_message(urgency_message)

        # Final strict pruning to keep only contract fields and avoid recurrent schema drift.
        mechanism = upgraded.get("mechanism")
        if isinstance(mechanism, dict):
            callout = mechanism.get("callout")
            if isinstance(callout, dict):
                mechanism["callout"] = _prune_keys(
                    callout,
                    allowed={"left_title", "left_body", "right_title", "right_body"},
                )
            comparison = mechanism.get("comparison")
            if isinstance(comparison, dict):
                mechanism["comparison"] = _prune_keys(
                    comparison,
                    allowed={"badge", "title", "swipe_hint", "columns", "rows"},
                )
            mechanism["bullets"] = _coerce_story_bullets(mechanism.get("bullets"))
            mechanism = _prune_keys(
                mechanism,
                allowed={"title", "paragraphs", "bullets", "callout", "comparison"},
            )
            upgraded["mechanism"] = mechanism

        faq = upgraded.get("faq")
        if isinstance(faq, dict):
            faq["items"] = _coerce_faq_items(faq.get("items"))
        hero_purchase_title = _clip_text(_coerce_non_empty_text(hero.get("purchase_title")), max_len=64)
        if not hero_purchase_title:
            raise StrategyV2DecisionError("Legacy sales payload upgrade failed: hero.purchase_title is required.")
        hero["purchase_title"] = hero_purchase_title
        hero_subbullets = [
            clipped
            for clipped in (
                _clip_text(_coerce_non_empty_text(row), max_len=90)
                for row in (hero.get("primary_cta_subbullets") if isinstance(hero.get("primary_cta_subbullets"), list) else [])
            )
            if clipped
        ]
        if len(hero_subbullets) < 2:
            raise StrategyV2DecisionError(
                "Legacy sales payload upgrade failed: hero.primary_cta_subbullets must include at least 2 items."
            )
        hero["primary_cta_subbullets"] = hero_subbullets[:2]

        problem_paragraphs = [
            clipped
            for clipped in (
                _clip_sentences(_coerce_non_empty_text(row), max_sentences=2, max_len=320)
                for row in (problem.get("paragraphs") if isinstance(problem.get("paragraphs"), list) else [])
            )
            if clipped
        ]
        if not problem_paragraphs:
            raise StrategyV2DecisionError("Legacy sales payload upgrade failed: problem.paragraphs is required.")
        problem["paragraphs"] = problem_paragraphs[:2]
        problem["emphasis_line"] = _clip_text(_coerce_non_empty_text(problem.get("emphasis_line")), max_len=160)

        mechanism_paragraphs = [
            clipped
            for clipped in (
                _clip_sentences(
                    _coerce_non_empty_text(row),
                    max_sentences=2,
                    max_len=_MECHANISM_PARAGRAPH_MAX_CHARS,
                )
                for row in (mechanism.get("paragraphs") if isinstance(mechanism.get("paragraphs"), list) else [])
            )
            if clipped
        ]
        if not mechanism_paragraphs:
            raise StrategyV2DecisionError("Legacy sales payload upgrade failed: mechanism.paragraphs is required.")
        mechanism["paragraphs"] = mechanism_paragraphs[:1]

        social_proof["summary"] = _clip_sentences(
            _coerce_non_empty_text(social_proof.get("summary")),
            max_sentences=2,
            max_len=260,
        )
        whats_inside["benefits"] = [
            clipped
            for clipped in (
                _clip_text(_coerce_non_empty_text(row), max_len=140)
                for row in (whats_inside.get("benefits") if isinstance(whats_inside.get("benefits"), list) else [])
            )
            if clipped
        ][:_HERO_BENEFIT_COUNT]
        whats_inside["offer_helper_text"] = _clip_sentences(
            _coerce_non_empty_text(whats_inside.get("offer_helper_text")),
            max_sentences=2,
            max_len=180,
        )

        guarantee_paragraph_rows = [
            clipped
            for clipped in (
                _clip_sentences(_coerce_non_empty_text(row), max_sentences=2, max_len=260)
                for row in (guarantee.get("paragraphs") if isinstance(guarantee.get("paragraphs"), list) else [])
            )
            if clipped
        ]
        if not guarantee_paragraph_rows:
            raise StrategyV2DecisionError("Legacy sales payload upgrade failed: guarantee.paragraphs is required.")
        guarantee["paragraphs"] = guarantee_paragraph_rows[:1]
        guarantee["why_body"] = _clip_sentences(
            _coerce_non_empty_text(guarantee.get("why_body")),
            max_sentences=2,
            max_len=220,
        )
        guarantee["closing_line"] = _clip_text(
            _coerce_non_empty_text(guarantee.get("closing_line")),
            max_len=140,
        )

        faq_items = faq.get("items") if isinstance(faq.get("items"), list) else []
        normalized_faq_items: list[dict[str, str]] = []
        for row in faq_items:
            if not isinstance(row, dict):
                continue
            question = _clip_text(_coerce_non_empty_text(row.get("question")), max_len=120)
            answer = _clip_sentences(_coerce_non_empty_text(row.get("answer")), max_sentences=3, max_len=280)
            if question and answer:
                normalized_faq_items.append({"question": question, "answer": answer})
        if not normalized_faq_items:
            raise StrategyV2DecisionError("Legacy sales payload upgrade failed: faq.items is required.")
        if len(normalized_faq_items) < _MIN_FAQ_ITEMS:
            raise StrategyV2DecisionError(
                f"Legacy sales payload upgrade failed: faq.items must include at least {_MIN_FAQ_ITEMS} entries."
            )
        faq["items"] = normalized_faq_items[:12]

        normalized_faq_pills: list[dict[str, str]] = []
        for row in _coerce_faq_pills(upgraded.get("faq_pills")):
            label = _clip_text(_coerce_non_empty_text(row.get("label")), max_len=120)
            answer = _clip_sentences(_coerce_non_empty_text(row.get("answer")), max_sentences=3, max_len=420)
            if label and answer:
                normalized_faq_pills.append({"label": label, "answer": answer})
        if not normalized_faq_pills:
            normalized_faq_pills = [
                {"label": _clip_text(item["question"], max_len=120), "answer": _clip_sentences(item["answer"], max_sentences=3, max_len=420)}
                for item in normalized_faq_items
                if _clip_text(item["question"], max_len=120)
                and _clip_sentences(item["answer"], max_sentences=3, max_len=420)
            ]
        if len(normalized_faq_pills) < _MIN_FAQ_ITEMS:
            raise StrategyV2DecisionError(
                f"Legacy sales payload upgrade failed: faq_pills must include at least {_MIN_FAQ_ITEMS} entries."
            )
        upgraded["faq_pills"] = normalized_faq_pills[:12]

        normalized_marquee_items: list[str] = []
        seen_marquee_items: set[str] = set()
        for row in _coerce_non_empty_text_list(upgraded.get("marquee_items"), max_items=12):
            compact = _compact_phrase(row, max_words=3, max_len=24)
            if not compact:
                continue
            dedupe_key = compact.lower()
            if dedupe_key in seen_marquee_items:
                continue
            seen_marquee_items.add(dedupe_key)
            normalized_marquee_items.append(compact)
        if not normalized_marquee_items:
            raise StrategyV2DecisionError("Legacy sales payload upgrade failed: marquee_items is required.")
        upgraded["marquee_items"] = normalized_marquee_items
        upgraded["cta_close"] = _clip_text(_coerce_non_empty_text(upgraded.get("cta_close")), max_len=80)
        upgraded["urgency_message"] = _clip_text(
            _coerce_non_empty_text(upgraded.get("urgency_message")),
            max_len=220,
        )
        if isinstance(faq, dict):
            upgraded["faq"] = _prune_keys(faq, allowed={"title", "items"})
        upgraded["hero"] = _prune_keys(hero, allowed={"purchase_title", "primary_cta_label", "primary_cta_subbullets"})
        upgraded["problem"] = _prune_keys(problem, allowed={"title", "paragraphs", "emphasis_line"})
        upgraded["social_proof"] = _prune_keys(
            social_proof,
            allowed={"badge", "title", "rating_label", "summary"},
        )
        upgraded["whats_inside"] = _prune_keys(whats_inside, allowed={"benefits", "offer_helper_text"})
        upgraded["bonus"] = _prune_keys(bonus, allowed={"free_gifts_title", "free_gifts_body"})
        upgraded["guarantee"] = _prune_keys(
            guarantee,
            allowed={"title", "paragraphs", "why_title", "why_body", "closing_line"},
        )
        upgraded = _prune_keys(
            upgraded,
            allowed={
                "hero",
                "problem",
                "mechanism",
                "social_proof",
                "whats_inside",
                "bonus",
                "guarantee",
                "faq",
                "faq_pills",
                "marquee_items",
                "cta_close",
                "urgency_message",
            },
        )
        return upgraded

    supported = ", ".join(sorted(_SUPPORTED_TEMPLATE_IDS))
    raise StrategyV2DecisionError(
        f"Unsupported template_id for Strategy V2 payload upgrade: {template_id}. Supported template IDs: {supported}."
    )


def _sales_patch_operation_dicts_from_fit_pack(fit_pack: TemplateFitPack) -> list[dict[str, Any]]:
    return [
        {"component_type": "SalesPdpHero", "field_path": "props.config.purchase.title", "value": fit_pack.hero.purchase_title},
        {"component_type": "SalesPdpHeader", "field_path": "props.config.cta.label", "value": fit_pack.hero.primary_cta_label},
        {"component_type": "SalesPdpHero", "field_path": "props.config.header.cta.label", "value": fit_pack.hero.primary_cta_label},
        {"component_type": "SalesPdpHero", "field_path": "props.config.purchase.cta.labelTemplate", "value": fit_pack.hero.primary_cta_label},
        {"component_type": "SalesPdpHero", "field_path": "props.config.purchase.cta.subBullets", "value": fit_pack.hero.primary_cta_subbullets},
        {
            "component_type": "SalesPdpHero",
            "field_path": "props.config.purchase.faqPills",
            "value": [item.model_dump(mode="python") for item in fit_pack.faq_pills],
        },
        {"component_type": "SalesPdpHero", "field_path": "props.config.purchase.cta.urgency.message", "value": fit_pack.urgency_message},
        {"component_type": "SalesPdpMarquee", "field_path": "props.config.items", "value": fit_pack.marquee_items},
        {"component_type": "SalesPdpStoryProblem", "field_path": "props.config.title", "value": fit_pack.problem.title},
        {"component_type": "SalesPdpStoryProblem", "field_path": "props.config.paragraphs", "value": fit_pack.problem.paragraphs},
        {"component_type": "SalesPdpStoryProblem", "field_path": "props.config.emphasisLine", "value": fit_pack.problem.emphasis_line},
        {"component_type": "SalesPdpStorySolution", "field_path": "props.config.title", "value": fit_pack.mechanism.title},
        {"component_type": "SalesPdpStorySolution", "field_path": "props.config.paragraphs", "value": fit_pack.mechanism.paragraphs},
        {
            "component_type": "SalesPdpStorySolution",
            "field_path": "props.config.bullets",
            "value": [bullet.model_dump(mode="python") for bullet in fit_pack.mechanism.bullets],
        },
        {
            "component_type": "SalesPdpStorySolution",
            "field_path": "props.config.callout.leftTitle",
            "value": fit_pack.mechanism.callout.left_title,
        },
        {
            "component_type": "SalesPdpStorySolution",
            "field_path": "props.config.callout.leftBody",
            "value": fit_pack.mechanism.callout.left_body,
        },
        {
            "component_type": "SalesPdpStorySolution",
            "field_path": "props.config.callout.rightTitle",
            "value": fit_pack.mechanism.callout.right_title,
        },
        {
            "component_type": "SalesPdpStorySolution",
            "field_path": "props.config.callout.rightBody",
            "value": fit_pack.mechanism.callout.right_body,
        },
        {
            "component_type": "SalesPdpComparison",
            "field_path": "props.config.badge",
            "value": fit_pack.mechanism.comparison.badge,
        },
        {
            "component_type": "SalesPdpComparison",
            "field_path": "props.config.title",
            "value": fit_pack.mechanism.comparison.title,
        },
        {
            "component_type": "SalesPdpComparison",
            "field_path": "props.config.swipeHint",
            "value": fit_pack.mechanism.comparison.swipe_hint,
        },
        {
            "component_type": "SalesPdpComparison",
            "field_path": "props.config.columns.pup",
            "value": fit_pack.mechanism.comparison.columns.pup,
        },
        {
            "component_type": "SalesPdpComparison",
            "field_path": "props.config.columns.disposable",
            "value": fit_pack.mechanism.comparison.columns.disposable,
        },
        {
            "component_type": "SalesPdpComparison",
            "field_path": "props.config.rows",
            "value": [row.model_dump(mode="python") for row in fit_pack.mechanism.comparison.rows],
        },
        {"component_type": "SalesPdpReviewWall", "field_path": "props.config.badge", "value": fit_pack.social_proof.badge},
        {"component_type": "SalesPdpReviewWall", "field_path": "props.config.title", "value": fit_pack.social_proof.title},
        {"component_type": "SalesPdpReviewWall", "field_path": "props.config.ratingLabel", "value": fit_pack.social_proof.rating_label},
        {
            "component_type": "SalesPdpReviews",
            "field_path": "props.config.data.summary.customersSay",
            "value": fit_pack.social_proof.summary,
        },
        {
            "component_type": "SalesPdpHero",
            "field_path": "props.config.purchase.benefits",
            "value": [{"text": benefit} for benefit in fit_pack.whats_inside.benefits],
        },
        {
            "component_type": "SalesPdpHero",
            "field_path": "props.config.purchase.offer.helperText",
            "value": fit_pack.whats_inside.offer_helper_text,
        },
        {
            "component_type": "SalesPdpHero",
            "field_path": "props.config.purchase.offer.seeWhyLabel",
            "value": "",
        },
        {
            "component_type": "SalesPdpHero",
            "field_path": "props.config.gallery.freeGifts.title",
            "value": fit_pack.bonus.free_gifts_title,
        },
        {
            "component_type": "SalesPdpHero",
            "field_path": "props.config.gallery.freeGifts.body",
            "value": fit_pack.bonus.free_gifts_body,
        },
        {
            "component_type": "SalesPdpGuarantee",
            "field_path": "props.config.title",
            "value": fit_pack.guarantee.title,
        },
        {
            "component_type": "SalesPdpGuarantee",
            "field_path": "props.config.paragraphs",
            "value": fit_pack.guarantee.paragraphs,
        },
        {
            "component_type": "SalesPdpGuarantee",
            "field_path": "props.config.whyTitle",
            "value": fit_pack.guarantee.why_title,
        },
        {
            "component_type": "SalesPdpGuarantee",
            "field_path": "props.config.whyBody",
            "value": fit_pack.guarantee.why_body,
        },
        {
            "component_type": "SalesPdpGuarantee",
            "field_path": "props.config.closingLine",
            "value": fit_pack.guarantee.closing_line,
        },
        {"component_type": "SalesPdpFaq", "field_path": "props.config.title", "value": fit_pack.faq.title},
        {
            "component_type": "SalesPdpFaq",
            "field_path": "props.config.items",
            "value": [item.model_dump(mode="python") for item in fit_pack.faq.items],
        },
    ]


def _pre_sales_patch_operation_dicts_from_fit_pack(fit_pack: PreSalesListicleFitPack) -> list[dict[str, Any]]:
    reasons = [
        {
            "number": int(reason.number),
            "title": reason.title,
            "body": reason.body,
            "image": reason.image.model_dump(mode="python", exclude_none=True),
        }
        for reason in fit_pack.reasons
    ]
    badges = [
        {
            "label": badge.label,
            **({"value": badge.value} if isinstance(badge.value, str) and badge.value.strip() else {}),
            "iconAlt": badge.icon.alt,
            "prompt": badge.icon.prompt,
        }
        for badge in fit_pack.hero.badges
    ]
    operations: list[dict[str, Any]] = [
        {"component_type": "PreSalesHero", "field_path": "props.config.hero.title", "value": fit_pack.hero.title},
        {"component_type": "PreSalesHero", "field_path": "props.config.hero.subtitle", "value": fit_pack.hero.subtitle},
        {"component_type": "PreSalesHero", "field_path": "props.config.badges", "value": badges},
        {"component_type": "PreSalesReasons", "field_path": "props.config", "value": reasons},
        {"component_type": "PreSalesMarquee", "field_path": "props.config", "value": fit_pack.marquee},
        {"component_type": "PreSalesPitch", "field_path": "props.config.title", "value": fit_pack.pitch.title},
        {"component_type": "PreSalesPitch", "field_path": "props.config.bullets", "value": fit_pack.pitch.bullets},
        {"component_type": "PreSalesPitch", "field_path": "props.config.cta.label", "value": fit_pack.pitch.cta_label},
        {"component_type": "PreSalesPitch", "field_path": "props.config.image.alt", "value": fit_pack.pitch.image.alt},
        {"component_type": "PreSalesReviewWall", "field_path": "props.config.title", "value": fit_pack.review_wall.title},
        {"component_type": "PreSalesReviewWall", "field_path": "props.config.buttonLabel", "value": fit_pack.review_wall.button_label},
        {"component_type": "PreSalesFloatingCta", "field_path": "props.config.label", "value": fit_pack.floating_cta.label},
    ]
    if isinstance(fit_pack.pitch.image.prompt, str) and fit_pack.pitch.image.prompt.strip():
        operations.append(
            {
                "component_type": "PreSalesPitch",
                "field_path": "props.config.image.prompt",
                "value": fit_pack.pitch.image.prompt.strip(),
            }
        )
    return operations


def build_strategy_v2_template_patch_operations(
    *,
    template_id: str,
    payload_fields: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        if template_id == "sales-pdp":
            fit_pack = TemplateFitPack.model_validate(payload_fields)
            operation_dicts = _sales_patch_operation_dicts_from_fit_pack(fit_pack)
        elif template_id == "pre-sales-listicle":
            normalized_fields = _normalize_pre_sales_template_payload_fields(
                PreSalesListicleFitPack.model_validate(payload_fields).model_dump(mode="python")
            )
            fit_pack = PreSalesListicleFitPack.model_validate(normalized_fields)
            operation_dicts = _pre_sales_patch_operation_dicts_from_fit_pack(fit_pack)
        else:
            supported = ", ".join(sorted(_SUPPORTED_TEMPLATE_IDS))
            raise StrategyV2DecisionError(
                f"Unsupported template_id for Strategy V2 patch generation: {template_id}. "
                f"Supported template IDs: {supported}."
            )

        operations = [
            TemplatePatchOperation.model_validate(operation)
            for operation in operation_dicts
            if operation["value"] not in ([], None)
        ]
        return [operation.model_dump(mode="python") for operation in operations]
    except ValidationError as exc:
        raise StrategyV2DecisionError(
            "TEMPLATE_PATCH_BUILD_FAILURE: "
            f"template_id={template_id}; "
            f"errors={_format_pydantic_validation_errors(exc)}. "
            "Remediation: emit complete template_payload values required by mapped template paths."
        ) from exc


def _strip_markdown_inline(text: str) -> str:
    value = text.strip()
    value = _MARKDOWN_BOLD_RE.sub(r"\1", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", value)
    return value.strip()


def _parse_h2_sections(markdown: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip("\n")
        match = _MARKDOWN_H2_RE.match(line.strip())
        if match:
            if current_title is not None:
                sections.append({"title": current_title, "lines": list(current_lines)})
            current_title = match.group("title").strip()
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        sections.append({"title": current_title, "lines": list(current_lines)})

    return sections


def _extract_paragraphs(lines: list[str]) -> list[str]:
    paragraphs: list[str] = []
    bucket: list[str] = []

    for raw in lines:
        line = raw.strip()
        if not line:
            if bucket:
                paragraphs.append(_strip_markdown_inline(" ".join(bucket)))
                bucket = []
            continue
        if line == "---":
            continue
        if line.startswith("|"):
            continue
        if _MARKDOWN_BULLET_RE.match(line):
            continue
        if _MARKDOWN_LINK_RE.search(line):
            continue
        bucket.append(line)

    if bucket:
        paragraphs.append(_strip_markdown_inline(" ".join(bucket)))

    return [paragraph for paragraph in paragraphs if paragraph]


def _extract_bullets(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    for raw in lines:
        match = _MARKDOWN_BULLET_RE.match(raw.strip())
        if not match:
            continue
        value = _strip_markdown_inline(match.group("value"))
        if value:
            bullets.append(value)
    return bullets


def _extract_links(markdown: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for label, href in _MARKDOWN_LINK_RE.findall(markdown):
        cleaned_label = _strip_markdown_inline(label)
        cleaned_href = href.strip()
        if cleaned_label and cleaned_href:
            links.append({"label": cleaned_label, "href": cleaned_href})
    return links


def _extract_faq_items(lines: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    current_question: str | None = None
    current_answer_lines: list[str] = []

    for raw in lines:
        line = _strip_markdown_inline(raw)
        if not line:
            continue

        question_match = _FAQ_QUESTION_RE.match(line)
        if question_match:
            if current_question and current_answer_lines:
                items.append(
                    {
                        "question": current_question.strip(),
                        "answer": " ".join(current_answer_lines).strip(),
                    }
                )
            current_question = question_match.group("value").strip()
            current_answer_lines = []
            continue
        # Accept markdown FAQ format where each question is a bold sentence ending in `?`
        # followed by one or more answer lines.
        if line.endswith("?"):
            if current_question and current_answer_lines:
                items.append(
                    {
                        "question": current_question.strip(),
                        "answer": " ".join(current_answer_lines).strip(),
                    }
                )
            current_question = line.strip()
            current_answer_lines = []
            continue

        answer_match = _FAQ_ANSWER_RE.match(line)
        if answer_match and current_question:
            current_answer_lines.append(answer_match.group("value").strip())
            continue

        if current_question:
            current_answer_lines.append(line)

    if current_question and current_answer_lines:
        items.append(
            {
                "question": current_question.strip(),
                "answer": " ".join(current_answer_lines).strip(),
            }
        )

    return [item for item in items if item.get("question") and item.get("answer")]


def _parse_markdown_table_rows(lines: list[str]) -> list[list[str]]:
    table_lines = [line.strip() for line in lines if line.strip().startswith("|")]
    if not table_lines:
        return []

    parsed_rows: list[list[str]] = []
    for line in table_lines:
        row = [cell.strip() for cell in line.strip("|").split("|")]
        if len(row) < 3:
            continue
        if all(set(cell) <= {"-", ":"} for cell in row):
            continue
        parsed_rows.append(row[:3])
    return parsed_rows


def _extract_comparison_columns(lines: list[str]) -> dict[str, str]:
    parsed_rows = _parse_markdown_table_rows(lines)
    if not parsed_rows:
        return {
            "pup": "OUR APPROACH",
            "disposable": "ALTERNATIVE",
        }
    header = parsed_rows[0]
    pup = _strip_markdown_inline(header[1]) if len(header) > 1 else ""
    disposable = _strip_markdown_inline(header[2]) if len(header) > 2 else ""
    return {
        "pup": pup or "OUR APPROACH",
        "disposable": disposable or "ALTERNATIVE",
    }


def _extract_comparison_rows(lines: list[str]) -> list[dict[str, str]]:
    parsed_rows = _parse_markdown_table_rows(lines)
    if len(parsed_rows) <= 1:
        return []

    rows: list[dict[str, str]] = []
    for row in parsed_rows[1:]:
        label, pup, disposable = (_strip_markdown_inline(cell) for cell in row)
        if label and pup and disposable:
            rows.append({"label": label, "pup": pup, "disposable": disposable})
    return rows


def _derive_story_bullets(raw_bullets: list[str]) -> list[dict[str, str]]:
    derived: list[dict[str, str]] = []
    for raw in raw_bullets:
        value = _strip_markdown_inline(raw)
        if not value:
            continue
        title = ""
        body = ""
        if ":" in value:
            left, right = value.split(":", 1)
            title = left.strip()
            body = right.strip()
        elif " - " in value:
            left, right = value.split(" - ", 1)
            title = left.strip()
            body = right.strip()
        if not title:
            words = [word for word in re.split(r"\s+", value) if word]
            title = " ".join(words[:4]).strip().rstrip(".,;:!?")
            body = value
        title = title or "Core point"
        body = body or value
        derived.append({"title": title, "body": body})
    return derived


def _canonical_section_key(*, title: str) -> str | None:
    lowered_title = title.lower()
    contract = get_page_contract(profile=default_copy_contract_profile(), page_type="sales_page_warm")
    for section in contract.required_sections:
        for marker in section.title_markers:
            if marker in lowered_title:
                return section.section_key
    return None


def _require_section(
    *,
    section_map: dict[str, dict[str, Any]],
    section_key: str,
) -> dict[str, Any]:
    section = section_map.get(section_key)
    if isinstance(section, dict):
        return section
    raise StrategyV2DecisionError(
        "Template bridge failed required section mapping. "
        f"Missing section_key={section_key}. "
        "Remediation: ensure canonical sales sections are present in copy output."
    )


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return ""


def _derive_marquee_items(
    *,
    candidates: list[str],
    min_items: int = 4,
    max_items: int = 8,
) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        cleaned = _strip_markdown_inline(str(raw or ""))
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,.")
        if not cleaned:
            continue
        word_count = len(_WORD_RE.findall(cleaned))
        if len(cleaned) > 24 or word_count < 1 or word_count > 3:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(cleaned)
        if len(items) >= max_items:
            break
    if len(items) < min_items:
        raise StrategyV2DecisionError(
            "Template bridge requires at least four distinct marquee items derived from sales content."
        )
    return items


def _normalize_sales_urgency_message(value: str) -> str:
    cleaned = _strip_markdown_inline(value).strip()
    if not cleaned:
        return ""
    sellout_prefix = "Selling out faster than expected."
    lowered = cleaned.lower()
    has_sellout = "sell out" in lowered or "selling out" in lowered or "sold out" in lowered
    if has_sellout:
        normalized = cleaned
    else:
        # Prefix so truncation never drops the urgency signal.
        normalized = f"{sellout_prefix} {cleaned.rstrip('.')}"
    lowered_normalized = normalized.lower()
    if "sell out" not in lowered_normalized and "selling out" not in lowered_normalized and "sold out" not in lowered_normalized:
        remaining = 220 - len(sellout_prefix) - 1
        if remaining <= 0:
            return sellout_prefix[:220]
        tail = cleaned[:remaining].rstrip()
        normalized = f"{sellout_prefix} {tail}".rstrip()
    return normalized


def _component_instances(node: Any, *, component_type: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == component_type and isinstance(value.get("props"), dict):
                matches.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return matches


def _path_exists(node: Any, *, field_path: str) -> bool:
    current = node
    for part in field_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return False
    return True


def _set_path(node: Any, *, field_path: str, value: Any) -> None:
    parts = field_path.split(".")
    current = node
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise StrategyV2DecisionError(
                "Template bridge patch path is invalid. "
                f"Missing segment '{part}' in path '{field_path}'."
            )
        current = current[part]
    tail = parts[-1]
    if not isinstance(current, dict) or tail not in current:
        raise StrategyV2DecisionError(
            "Template bridge patch path is invalid. "
            f"Missing terminal segment '{tail}' in path '{field_path}'."
        )
    current[tail] = value


def _validate_patch_paths(
    *,
    base_puck_data: dict[str, Any],
    operations: list[TemplatePatchOperation],
) -> None:
    for operation in operations:
        components = _component_instances(base_puck_data, component_type=operation.component_type)
        if not components:
            raise StrategyV2DecisionError(
                "Template bridge component-path validation failed. "
                f"Component '{operation.component_type}' not found in template."
            )
        if not _path_exists(components[0], field_path=operation.field_path):
            raise StrategyV2DecisionError(
                "Template bridge component-path validation failed. "
                f"Path '{operation.component_type}.{operation.field_path}' does not exist in template."
            )


def apply_strategy_v2_template_patch(
    *,
    base_puck_data: dict[str, Any],
    operations: list[dict[str, Any]] | list[TemplatePatchOperation],
    template_id: str,
) -> dict[str, Any]:
    if template_id not in _SUPPORTED_TEMPLATE_IDS:
        supported = ", ".join(sorted(_SUPPORTED_TEMPLATE_IDS))
        raise StrategyV2DecisionError(
            f"Unsupported template_id for Strategy V2 bridge patch: {template_id}. "
            f"Supported template IDs: {supported}."
        )

    normalized_ops = [
        operation
        if isinstance(operation, TemplatePatchOperation)
        else TemplatePatchOperation.model_validate(operation)
        for operation in operations
    ]
    patched = deepcopy(base_puck_data)
    if template_id == "pre-sales-listicle":
        _hydrate_presales_patch_values(base_puck_data=patched, operations=normalized_ops)
    _validate_patch_paths(base_puck_data=patched, operations=normalized_ops)
    for operation in normalized_ops:
        components = _component_instances(patched, component_type=operation.component_type)
        _set_path(components[0], field_path=operation.field_path, value=operation.value)

    if template_id == "sales-pdp":
        funnel_ai._validate_sales_pdp_component_configs(patched)
    elif template_id == "pre-sales-listicle":
        funnel_ai._validate_pre_sales_listicle_component_configs(patched)
    return patched


def _hydrate_presales_patch_values(
    *,
    base_puck_data: dict[str, Any],
    operations: list[TemplatePatchOperation],
) -> None:
    for operation in operations:
        if operation.component_type == "PreSalesHero" and operation.field_path == "props.config.badges":
            operation.value = _hydrate_presales_badges(
                base_puck_data=base_puck_data,
                incoming_value=operation.value,
            )
        if operation.component_type == "PreSalesReviews" and operation.field_path == "props.config.slides":
            operation.value = _hydrate_presales_review_slides(
                base_puck_data=base_puck_data,
                incoming_value=operation.value,
            )


def _hydrate_presales_badges(
    *,
    base_puck_data: dict[str, Any],
    incoming_value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(incoming_value, list) or not incoming_value:
        raise StrategyV2DecisionError(
            "Template bridge pre-sales badge patch must contain a non-empty badges array."
        )

    components = _component_instances(base_puck_data, component_type="PreSalesHero")
    if not components:
        raise StrategyV2DecisionError(
            "Template bridge pre-sales badge patch failed: PreSalesHero component not found."
        )
    hero_config = components[0].get("props", {}).get("config")
    if not isinstance(hero_config, dict):
        raise StrategyV2DecisionError(
            "Template bridge pre-sales badge patch failed: PreSalesHero config is invalid."
        )
    existing_badges = hero_config.get("badges")
    if not isinstance(existing_badges, list) or not existing_badges:
        raise StrategyV2DecisionError(
            "Template bridge pre-sales badge patch failed: template is missing default badge entries."
        )

    merged_badges: list[dict[str, Any]] = []
    for index, raw_badge in enumerate(incoming_value):
        if not isinstance(raw_badge, dict):
            raise StrategyV2DecisionError(
                f"Template bridge pre-sales badge patch failed: badges[{index}] must be an object."
            )
        label = str(raw_badge.get("label") or "").strip()
        if not label:
            raise StrategyV2DecisionError(
                f"Template bridge pre-sales badge patch failed: badges[{index}].label is required."
            )
        base_badge_raw = existing_badges[index if index < len(existing_badges) else len(existing_badges) - 1]
        base_badge = deepcopy(base_badge_raw) if isinstance(base_badge_raw, dict) else {}
        base_badge["label"] = label
        value = raw_badge.get("value")
        if isinstance(value, str) and value.strip():
            base_badge["value"] = value.strip()
        else:
            base_badge.pop("value", None)
        icon_alt = raw_badge.get("iconAlt")
        if not isinstance(icon_alt, str) or not icon_alt.strip():
            raise StrategyV2DecisionError(
                f"Template bridge pre-sales badge patch failed: badges[{index}].iconAlt is required."
            )
        base_badge["iconAlt"] = icon_alt.strip()
        prompt = raw_badge.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise StrategyV2DecisionError(
                f"Template bridge pre-sales badge patch failed: badges[{index}].prompt is required."
            )
        base_badge["prompt"] = prompt.strip()
        merged_badges.append(base_badge)
    return merged_badges


def _hydrate_presales_review_slides(
    *,
    base_puck_data: dict[str, Any],
    incoming_value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(incoming_value, list) or len(incoming_value) < 3:
        raise StrategyV2DecisionError(
            "Template bridge pre-sales review patch must contain at least 3 review slides."
        )

    components = _component_instances(base_puck_data, component_type="PreSalesReviews")
    if not components:
        raise StrategyV2DecisionError(
            "Template bridge pre-sales review patch failed: PreSalesReviews component not found."
        )
    reviews_config = components[0].get("props", {}).get("config")
    if not isinstance(reviews_config, dict):
        raise StrategyV2DecisionError(
            "Template bridge pre-sales review patch failed: PreSalesReviews config is invalid."
        )
    existing_slides = reviews_config.get("slides")
    if not isinstance(existing_slides, list) or not existing_slides:
        raise StrategyV2DecisionError(
            "Template bridge pre-sales review patch failed: template is missing default review slides."
        )

    merged_slides: list[dict[str, Any]] = []
    for index, raw_slide in enumerate(incoming_value):
        if not isinstance(raw_slide, dict):
            raise StrategyV2DecisionError(
                f"Template bridge pre-sales review patch failed: reviews[{index}] must be an object."
            )
        text = str(raw_slide.get("text") or "").strip()
        author = str(raw_slide.get("author") or "").strip()
        if not text:
            raise StrategyV2DecisionError(
                f"Template bridge pre-sales review patch failed: reviews[{index}].text is required."
            )
        if not author:
            raise StrategyV2DecisionError(
                f"Template bridge pre-sales review patch failed: reviews[{index}].author is required."
            )
        base_slide_raw = existing_slides[index if index < len(existing_slides) else len(existing_slides) - 1]
        if not isinstance(base_slide_raw, dict):
            raise StrategyV2DecisionError(
                "Template bridge pre-sales review patch failed: template review slide structure is invalid."
            )
        base_images = base_slide_raw.get("images")
        if not isinstance(base_images, list) or not base_images:
            raise StrategyV2DecisionError(
                "Template bridge pre-sales review patch failed: template review slide is missing images."
            )
        merged_slide = deepcopy(base_slide_raw)
        merged_slide["text"] = text
        merged_slide["author"] = author
        rating = raw_slide.get("rating")
        if isinstance(rating, int):
            merged_slide["rating"] = rating
        verified = raw_slide.get("verified")
        if isinstance(verified, bool):
            merged_slide["verified"] = verified
        merged_slides.append(merged_slide)
    return merged_slides


def build_strategy_v2_template_bridge_v1(
    *,
    angle_run_id: str,
    template_id: str,
    headline: str,
    promise_contract: dict[str, Any],
    sales_page_markdown: str,
    presell_markdown: str,
) -> dict[str, Any]:
    if template_id != "sales-pdp":
        supported = "sales-pdp"
        raise StrategyV2DecisionError(
            f"Unsupported template_id for Strategy V2 bridge: {template_id}. "
            f"Supported template IDs: {supported}."
        )

    template = get_funnel_template(template_id)
    if template is None:
        raise StrategyV2DecisionError(
            f"Funnel template not found for bridge mapping: {template_id}. "
            "Remediation: ensure template exists before copy-to-funnel bridge."
        )

    sales_sections = _parse_h2_sections(sales_page_markdown)
    if not sales_sections:
        raise StrategyV2DecisionError(
            "Copy bridge failed because sales_page_markdown has no H2 sections. "
            "Remediation: generate canonical 12-section sales markdown before bridge."
        )

    normalized_sections: dict[str, Any] = {}
    duplicate_sections: dict[str, list[str]] = {}
    unmapped_titles: list[str] = []
    for section in sales_sections:
        title = str(section.get("title") or "").strip()
        lines = [str(line) for line in section.get("lines", [])]
        key = _canonical_section_key(title=title)
        if not key:
            unmapped_titles.append(title)
            continue
        payload = {
            "title": title,
            "lines": lines,
            "paragraphs": _extract_paragraphs(lines),
            "bullets": _extract_bullets(lines),
            "links": _extract_links("\n".join(lines)),
            "raw_markdown": "\n".join(lines).strip(),
        }
        if key in normalized_sections:
            duplicate_sections.setdefault(key, []).append(title)
            continue
        normalized_sections[key] = payload

    missing_required = sorted(section for section in _REQUIRED_MAPPED_SECTION_KEYS if section not in normalized_sections)
    if missing_required:
        raise StrategyV2DecisionError(
            "Template bridge required section mapping failed. "
            f"Missing sections: {', '.join(missing_required)}. "
            "Remediation: keep canonical section headings in sales output."
        )
    has_primary_cta = "cta_1" in normalized_sections or "cta_2" in normalized_sections
    if not has_primary_cta:
        raise StrategyV2DecisionError(
            "Template bridge requires at least one mapped CTA section (cta_1 or cta_2). "
            "Remediation: include canonical CTA #1 or CTA #2 section in sales markdown."
        )

    hero_section = _require_section(section_map=normalized_sections, section_key="hero_stack")
    problem_section = _require_section(section_map=normalized_sections, section_key="problem_recap")
    mechanism_section = _require_section(section_map=normalized_sections, section_key="mechanism_comparison")
    social_section = _require_section(section_map=normalized_sections, section_key="social_proof")
    whats_inside_section = _require_section(section_map=normalized_sections, section_key="whats_inside")
    bonus_section = _require_section(section_map=normalized_sections, section_key="bonus_stack")
    guarantee_section = _require_section(section_map=normalized_sections, section_key="guarantee")
    faq_section = _require_section(section_map=normalized_sections, section_key="faq")

    cta_sources = []
    for key in ("hero_stack", "cta_1", "cta_2", "cta_3_ps"):
        section = normalized_sections.get(key)
        if isinstance(section, dict):
            cta_sources.extend(section.get("links") or [])
    primary_cta_label = _first_non_empty([str(link.get("label") or "") for link in cta_sources])
    if not primary_cta_label:
        raise StrategyV2DecisionError(
            "Template bridge could not extract a CTA link label from sales sections. "
            "Remediation: include markdown CTA links in Hero/CTA sections."
        )

    hero_title = _first_non_empty(
        [
            headline.strip(),
            str(hero_section.get("title") or ""),
            *(hero_section.get("paragraphs") or []),
        ]
    )
    if not hero_title:
        raise StrategyV2DecisionError(
            "Template bridge could not extract hero purchase title from sales output."
        )

    problem_paragraphs = problem_section.get("paragraphs") or []
    mechanism_paragraphs = mechanism_section.get("paragraphs") or []
    guarantee_paragraphs = guarantee_section.get("paragraphs") or []
    if not problem_paragraphs or not mechanism_paragraphs or not guarantee_paragraphs:
        raise StrategyV2DecisionError(
            "Template bridge requires non-empty paragraphs for problem/mechanism/guarantee sections."
        )

    faq_items_raw = _extract_faq_items(faq_section.get("lines") or [])
    if not faq_items_raw:
        raise StrategyV2DecisionError(
            "Template bridge could not parse FAQ Q/A items. "
            "Remediation: keep FAQ entries in `Q:` / `A:` format."
        )
    if len(faq_items_raw) < _MIN_FAQ_ITEMS:
        raise StrategyV2DecisionError(
            f"Template bridge requires at least {_MIN_FAQ_ITEMS} FAQ items. "
            "Remediation: include 8 or more Q:/A: entries in the FAQ section."
        )

    cta_close_section = normalized_sections.get("cta_3_ps")
    cta_close_value = ""
    if isinstance(cta_close_section, dict):
        close_links = cta_close_section.get("links") or []
        cta_close_value = _first_non_empty([str(link.get("label") or "") for link in close_links])
        if not cta_close_value:
            cta_close_value = _first_non_empty(cta_close_section.get("paragraphs") or [])
    if not cta_close_value:
        cta_close_value = primary_cta_label
    urgency_source = ""
    if isinstance(cta_close_section, dict):
        urgency_source = _first_non_empty(cta_close_section.get("paragraphs") or [])
    if not urgency_source:
        urgency_source = cta_close_value
    if not urgency_source:
        urgency_source = _first_non_empty(social_section.get("paragraphs") or [])
    urgency_message = _normalize_sales_urgency_message(urgency_source)
    if not urgency_message:
        raise StrategyV2DecisionError(
            "Template bridge could not derive urgency message copy from CTA/social sections."
        )

    cta_subbullets = [value for value in (whats_inside_section.get("bullets") or []) if isinstance(value, str) and value.strip()]
    if len(cta_subbullets) < 2:
        raise StrategyV2DecisionError(
            "Template bridge requires at least two CTA support bullets from the What's Inside section. "
            "Remediation: include at least two concise bullets in What's Inside."
        )

    guarantee_paragraph_text = [str(value) for value in guarantee_paragraphs if isinstance(value, str) and value.strip()]
    why_title = "Why this guarantee exists"
    why_body = ""
    for paragraph in guarantee_paragraph_text:
        if paragraph.lower().startswith("why"):
            why_title = paragraph
            continue
        if not why_body and "because" in paragraph.lower():
            why_body = paragraph
    if not why_body:
        why_body = guarantee_paragraph_text[-1]

    comparison_rows = _extract_comparison_rows(mechanism_section.get("lines") or [])
    if not comparison_rows:
        raise StrategyV2DecisionError(
            "Template bridge requires a populated comparison markdown table in Mechanism + Comparison. "
            "Remediation: include comparison rows with label, your approach, and alternative columns."
        )
    comparison_columns = _extract_comparison_columns(mechanism_section.get("lines") or [])

    mechanism_bullets = _derive_story_bullets(mechanism_section.get("bullets") or [])
    for row in comparison_rows:
        if len(mechanism_bullets) >= 5:
            break
        mechanism_bullets.append(
            {
                "title": row["label"],
                "body": f"{comparison_columns['pup']}: {row['pup']}. {comparison_columns['disposable']}: {row['disposable']}.",
            }
        )
    if len(mechanism_bullets) < 5:
        raise StrategyV2DecisionError(
            "Template bridge requires at least five mechanism bullets with titles. "
            "Remediation: include >=5 bullets in Mechanism + Comparison."
        )
    mechanism_bullets = mechanism_bullets[:5]

    callout_left_lines = [
        f"{row['label']}: {row['disposable']}"
        for row in comparison_rows[:2]
        if row.get("label") and row.get("disposable")
    ]
    callout_right_lines = [
        f"{row['label']}: {row['pup']}"
        for row in comparison_rows[:2]
        if row.get("label") and row.get("pup")
    ]
    callout_left_body = _first_non_empty(callout_left_lines)
    callout_right_body = _first_non_empty(callout_right_lines)
    if not callout_left_body or not callout_right_body:
        raise StrategyV2DecisionError(
            "Template bridge could not derive mechanism callout copy from comparison rows. "
            "Remediation: ensure comparison rows include non-empty label/pup/disposable values."
        )

    marquee_candidates: list[str] = []
    marquee_candidates.extend([bullet.get("title", "") for bullet in mechanism_bullets if isinstance(bullet, dict)])
    marquee_candidates.extend([str(value) for value in (whats_inside_section.get("bullets") or []) if isinstance(value, str)])
    marquee_candidates.extend([str(row.get("label") or "") for row in comparison_rows if isinstance(row, dict)])
    marquee_items = _derive_marquee_items(candidates=marquee_candidates)
    faq_pills = [{"label": item["question"], "answer": item["answer"]} for item in faq_items_raw]

    fit_pack = TemplateFitPack.model_validate(
        {
            "hero": {
                "purchase_title": hero_title,
                "primary_cta_label": primary_cta_label,
                "primary_cta_subbullets": cta_subbullets[:2],
            },
            "problem": {
                "title": _strip_markdown_inline(str(problem_section.get("title") or "Problem")),
                "paragraphs": problem_paragraphs,
                "emphasis_line": _first_non_empty(problem_paragraphs[-1:]) or problem_paragraphs[0],
            },
            "mechanism": {
                "title": _strip_markdown_inline(str(mechanism_section.get("title") or "Mechanism + Comparison")),
                "paragraphs": mechanism_paragraphs,
                "bullets": mechanism_bullets,
                "callout": {
                    "left_title": comparison_columns["disposable"],
                    "left_body": callout_left_body,
                    "right_title": comparison_columns["pup"],
                    "right_body": callout_right_body,
                },
                "comparison": {
                    "badge": "US vs THEM",
                    "title": _normalize_comparison_title(
                        raw_title=_strip_markdown_inline(
                            str(mechanism_section.get("title") or "Mechanism + Comparison")
                        ),
                        columns=comparison_columns,
                    ),
                    "swipe_hint": "Swipe right to see comparison ->",
                    "columns": comparison_columns,
                    "rows": comparison_rows,
                },
            },
            "social_proof": {
                "badge": "SOCIAL PROOF",
                "title": _strip_markdown_inline(str(social_section.get("title") or "Social Proof")),
                "rating_label": "Verified customer feedback",
                "summary": _first_non_empty(social_section.get("paragraphs") or []),
            },
            "whats_inside": {
                "benefits": list((whats_inside_section.get("bullets") or [])[:_HERO_BENEFIT_COUNT]),
                "offer_helper_text": _first_non_empty(whats_inside_section.get("paragraphs") or []),
            },
            "bonus": {
                "free_gifts_title": _strip_markdown_inline(str(bonus_section.get("title") or "Bonus Stack + Value")),
                "free_gifts_body": _first_non_empty(bonus_section.get("paragraphs") or []),
            },
                "guarantee": {
                    "title": _normalize_guarantee_title(
                        _strip_markdown_inline(str(guarantee_section.get("title") or "Guarantee"))
                    ),
                    "paragraphs": guarantee_paragraph_text,
                    "why_title": why_title,
                    "why_body": why_body,
                    "closing_line": _first_non_empty([cta_close_value, guarantee_paragraph_text[-1]]),
                },
            "faq": {
                "title": _strip_markdown_inline(str(faq_section.get("title") or "FAQ")),
                "items": faq_items_raw,
            },
            "faq_pills": faq_pills,
            "marquee_items": marquee_items,
            "cta_close": cta_close_value,
            "urgency_message": urgency_message,
        }
    )

    operations = [
        TemplatePatchOperation.model_validate(operation)
        for operation in build_strategy_v2_template_patch_operations(
            template_id=template_id,
            payload_fields=fit_pack.model_dump(mode="python"),
        )
    ]

    _validate_patch_paths(base_puck_data=template.puck_data, operations=operations)
    patched_puck_data = apply_strategy_v2_template_patch(
        base_puck_data=template.puck_data,
        operations=operations,
        template_id=template_id,
    )

    mapped_keys = sorted(list(normalized_sections.keys()))
    residual_copy = {
        "identity_bridge": normalized_sections.get("identity_bridge", {}).get("raw_markdown", ""),
        "cta_3_ps": normalized_sections.get("cta_3_ps", {}).get("raw_markdown", ""),
        "unmapped_titles": unmapped_titles,
        "duplicates": duplicate_sections,
    }
    copy_pack = {
        "headline": headline.strip(),
        "promise_contract": promise_contract,
        "template_fit_pack": fit_pack.model_dump(mode="python"),
        "residual_copy": residual_copy,
        "cta": {
            "primary": fit_pack.hero.primary_cta_label,
            "close": fit_pack.cta_close,
        },
    }

    patch_hash = hashlib.sha256(
        json.dumps([operation.model_dump(mode="python") for operation in operations], sort_keys=True, ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()

    bridge_payload = StrategyV2TemplateBridgeV1.model_validate(
        {
            "bridge_version": "v1",
            "angle_run_id": angle_run_id,
            "template_id": template_id,
            "source": {
                "headline": headline.strip(),
                "promise_contract": promise_contract,
                "sales_page_markdown": sales_page_markdown,
                "presell_markdown": presell_markdown,
            },
            "normalized_sections": normalized_sections,
            "template_fit_pack": fit_pack.model_dump(mode="python"),
            "template_patch": [operation.model_dump(mode="python") for operation in operations],
            "copy_pack": copy_pack,
            "residual_copy": residual_copy,
            "validation_report": {
                "required_sections_present": sorted(list(_REQUIRED_MAPPED_SECTION_KEYS)),
                "mapped_section_keys": mapped_keys,
                "unmapped_titles": unmapped_titles,
                "duplicate_sections": duplicate_sections,
                "patch_operation_count": len(operations),
                "patch_hash": patch_hash,
                "template_validator": "passed",
            },
            "provenance": {
                "template_id": template_id,
                "template_name": template.name,
                "template_patch_hash": patch_hash,
                "template_validation": "sales_pdp_component_configs",
                "patched_component_count": len(
                    {operation.component_type for operation in operations}
                ),
                "patched_puck_data_sha256": hashlib.sha256(
                    json.dumps(patched_puck_data, sort_keys=True, ensure_ascii=True).encode("utf-8")
                ).hexdigest(),
            },
        }
    )
    return bridge_payload.model_dump(mode="python")
