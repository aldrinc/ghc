from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any

from pydantic import Field, ValidationError, field_validator

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

_REQUIRED_MAPPED_SECTION_KEYS = {
    "hero_stack",
    "problem_recap",
    "mechanism_comparison",
    "guarantee",
    "faq",
}


class TemplateFitPackComparisonRow(StrictContract):
    label: str = Field(min_length=1, max_length=80)
    pup: str = Field(min_length=1, max_length=180)
    disposable: str = Field(min_length=1, max_length=180)


class TemplateFitPackStoryBullet(StrictContract):
    title: str = Field(min_length=1, max_length=90)
    body: str = Field(min_length=1, max_length=240)


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


class TemplateFitPackFaqItem(StrictContract):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class TemplateFitPackHero(StrictContract):
    purchase_title: str = Field(min_length=1)
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
    paragraphs: list[str] = Field(min_length=1)
    emphasis_line: str = Field(min_length=1)


class TemplateFitPackMechanism(StrictContract):
    title: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1)
    bullets: list[TemplateFitPackStoryBullet] = Field(min_length=4, max_length=6)
    callout: TemplateFitPackMechanismCallout
    comparison: TemplateFitPackComparison


class TemplateFitPackSocialProof(StrictContract):
    badge: str = Field(min_length=1)
    title: str = Field(min_length=1)
    rating_label: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class TemplateFitPackWhatsInside(StrictContract):
    benefits: list[str] = Field(min_length=1, max_length=6)
    offer_helper_text: str = Field(min_length=1)

    @field_validator("benefits")
    @classmethod
    def _validate_benefits(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, value in enumerate(values):
            item = value.strip()
            if not item:
                raise ValueError(f"benefits[{index}] must be non-empty.")
            if len(item) > 140:
                raise ValueError(
                    f"benefits[{index}] exceeds 140 characters "
                    f"(observed={len(item)})."
                )
            cleaned.append(item)
        return cleaned


class TemplateFitPackBonus(StrictContract):
    free_gifts_title: str = Field(min_length=1)
    free_gifts_body: str = Field(min_length=1, max_length=220)


class TemplateFitPackGuarantee(StrictContract):
    title: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1)
    why_title: str = Field(min_length=1)
    why_body: str = Field(min_length=1)
    closing_line: str = Field(min_length=1)


class TemplateFitPackFaq(StrictContract):
    title: str = Field(min_length=1)
    items: list[TemplateFitPackFaqItem] = Field(min_length=1)


class TemplateFitPack(StrictContract):
    hero: TemplateFitPackHero
    problem: TemplateFitPackProblem
    mechanism: TemplateFitPackMechanism
    social_proof: TemplateFitPackSocialProof
    whats_inside: TemplateFitPackWhatsInside
    bonus: TemplateFitPackBonus
    guarantee: TemplateFitPackGuarantee
    faq: TemplateFitPackFaq
    cta_close: str = Field(min_length=1)


class PreSalesReasonFitPack(StrictContract):
    number: int = Field(ge=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)


class PreSalesHeroFitPack(StrictContract):
    title: str = Field(min_length=1)
    subtitle: str = Field(min_length=1)
    badges: list["PreSalesHeroBadgeFitPack"] = Field(min_length=1)


class PreSalesHeroBadgeFitPack(StrictContract):
    label: str = Field(min_length=1)
    value: str | None = None


class PreSalesPitchFitPack(StrictContract):
    title: str = Field(min_length=1)
    bullets: list[str] = Field(min_length=1)
    cta_label: str = Field(min_length=1)


class PreSalesReviewWallFitPack(StrictContract):
    title: str = Field(min_length=1)
    button_label: str = Field(min_length=1)


class PreSalesFloatingCtaFitPack(StrictContract):
    label: str = Field(min_length=1)


class PreSalesReviewSlideFitPack(StrictContract):
    text: str = Field(min_length=1)
    author: str = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    verified: bool | None = None


class PreSalesListicleFitPack(StrictContract):
    hero: PreSalesHeroFitPack
    reasons: list[PreSalesReasonFitPack] = Field(min_length=1)
    marquee: list[str] = Field(min_length=1)
    pitch: PreSalesPitchFitPack
    reviews: list[PreSalesReviewSlideFitPack] = Field(min_length=3)
    review_wall: PreSalesReviewWallFitPack
    floating_cta: PreSalesFloatingCtaFitPack


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
    try:
        if template_id == "sales-pdp":
            return TemplateFitPack.model_validate(payload_fields).model_dump(mode="python")
        if template_id == "pre-sales-listicle":
            return PreSalesListicleFitPack.model_validate(payload_fields).model_dump(mode="python")
    except ValidationError as exc:
        raise StrategyV2DecisionError(
            "TEMPLATE_PAYLOAD_VALIDATION: "
            f"template_id={template_id}; "
            f"errors={_format_pydantic_validation_errors(exc)}. "
            "Remediation: return template_payload that exactly matches the required template contract."
        ) from exc
    supported = ", ".join(sorted(_SUPPORTED_TEMPLATE_IDS))
    raise StrategyV2DecisionError(
        f"Unsupported template_id for Strategy V2 template payload validation: {template_id}. "
        f"Supported template IDs: {supported}."
    )


def _sales_patch_operation_dicts_from_fit_pack(fit_pack: TemplateFitPack) -> list[dict[str, Any]]:
    return [
        {"component_type": "SalesPdpHero", "field_path": "props.config.purchase.title", "value": fit_pack.hero.purchase_title},
        {"component_type": "SalesPdpHeader", "field_path": "props.config.cta.label", "value": fit_pack.hero.primary_cta_label},
        {"component_type": "SalesPdpHero", "field_path": "props.config.header.cta.label", "value": fit_pack.hero.primary_cta_label},
        {"component_type": "SalesPdpHero", "field_path": "props.config.purchase.cta.labelTemplate", "value": fit_pack.hero.primary_cta_label},
        {"component_type": "SalesPdpHero", "field_path": "props.config.purchase.cta.subBullets", "value": fit_pack.hero.primary_cta_subbullets},
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
        }
        for reason in fit_pack.reasons
    ]
    badges = [
        {
            "label": badge.label,
            **({"value": badge.value} if isinstance(badge.value, str) and badge.value.strip() else {}),
        }
        for badge in fit_pack.hero.badges
    ]
    reviews = [slide.model_dump(mode="python", exclude_none=True) for slide in fit_pack.reviews]
    return [
        {"component_type": "PreSalesHero", "field_path": "props.config.hero.title", "value": fit_pack.hero.title},
        {"component_type": "PreSalesHero", "field_path": "props.config.hero.subtitle", "value": fit_pack.hero.subtitle},
        {"component_type": "PreSalesHero", "field_path": "props.config.badges", "value": badges},
        {"component_type": "PreSalesReasons", "field_path": "props.config", "value": reasons},
        {"component_type": "PreSalesReviews", "field_path": "props.config.slides", "value": reviews},
        {"component_type": "PreSalesMarquee", "field_path": "props.config", "value": fit_pack.marquee},
        {"component_type": "PreSalesPitch", "field_path": "props.config.title", "value": fit_pack.pitch.title},
        {"component_type": "PreSalesPitch", "field_path": "props.config.bullets", "value": fit_pack.pitch.bullets},
        {"component_type": "PreSalesReviewWall", "field_path": "props.config.title", "value": fit_pack.review_wall.title},
        {"component_type": "PreSalesReviewWall", "field_path": "props.config.buttonLabel", "value": fit_pack.review_wall.button_label},
        {"component_type": "PreSalesFloatingCta", "field_path": "props.config.label", "value": fit_pack.floating_cta.label},
    ]


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
            fit_pack = PreSalesListicleFitPack.model_validate(payload_fields)
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
            if operation["value"] not in ("", [], None)
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
            *(hero_section.get("paragraphs") or []),
            headline.strip(),
            str(hero_section.get("title") or ""),
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

    cta_close_section = normalized_sections.get("cta_3_ps")
    cta_close_value = ""
    if isinstance(cta_close_section, dict):
        close_links = cta_close_section.get("links") or []
        cta_close_value = _first_non_empty([str(link.get("label") or "") for link in close_links])
        if not cta_close_value:
            cta_close_value = _first_non_empty(cta_close_section.get("paragraphs") or [])
    if not cta_close_value:
        cta_close_value = primary_cta_label

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
        if len(mechanism_bullets) >= 6:
            break
        mechanism_bullets.append(
            {
                "title": row["label"],
                "body": f"{comparison_columns['pup']}: {row['pup']}. {comparison_columns['disposable']}: {row['disposable']}.",
            }
        )
    if len(mechanism_bullets) < 4:
        raise StrategyV2DecisionError(
            "Template bridge requires at least four mechanism bullets with titles. "
            "Remediation: include >=4 bullets in Mechanism + Comparison."
        )
    mechanism_bullets = mechanism_bullets[:6]

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
                    "badge": "SIDE-BY-SIDE COMPARISON",
                    "title": _strip_markdown_inline(str(mechanism_section.get("title") or "Mechanism + Comparison")),
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
                "benefits": list((whats_inside_section.get("bullets") or [])[:6]),
                "offer_helper_text": _first_non_empty(whats_inside_section.get("paragraphs") or []),
            },
            "bonus": {
                "free_gifts_title": _strip_markdown_inline(str(bonus_section.get("title") or "Bonus Stack + Value")),
                "free_gifts_body": _first_non_empty(bonus_section.get("paragraphs") or []),
            },
            "guarantee": {
                "title": _strip_markdown_inline(str(guarantee_section.get("title") or "Guarantee")),
                "paragraphs": guarantee_paragraph_text,
                "why_title": why_title,
                "why_body": why_body,
                "closing_line": guarantee_paragraph_text[-1],
            },
            "faq": {
                "title": _strip_markdown_inline(str(faq_section.get("title") or "FAQ")),
                "items": faq_items_raw,
            },
            "cta_close": cta_close_value,
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
