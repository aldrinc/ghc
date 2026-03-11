from __future__ import annotations

import json
import re
from typing import Any, Literal, Mapping

from pydantic import Field

from app.strategy_v2.contracts import (
    CopyContextFiles,
    ProductBriefStage3,
    SCHEMA_VERSION_V2,
    StrictContract,
)
from app.strategy_v2.copy_contract_spec import (
    CopyContractProfile,
    CopyPageContract,
    default_copy_contract_profile,
    get_copy_quality_thresholds,
)
from app.strategy_v2.errors import StrategyV2MissingContextError


_HEADLINE_PROMPT_LIMITS = {
    "stage3_json": 30000,
    "hook_lines_json": 8000,
    "audience_product_markdown": 30000,
    "awareness_angle_matrix_markdown": 24000,
    "brand_voice_markdown": 12000,
    "compliance_markdown": 20000,
    "mental_models_markdown": 28000,
}

_PAGE_PROMPT_LIMITS = {
    "promise_contract_json": 6000,
    "stage3_json": 30000,
    "copy_context_json": 70000,
    "page_contract_json": 14000,
}
_HEADLINE_KEYWORD_STOPWORDS = {
    "about",
    "after",
    "before",
    "from",
    "have",
    "into",
    "most",
    "that",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "your",
}


class CopyStage4InputPacket(StrictContract):
    schema_version: Literal["2.0.0"] = SCHEMA_VERSION_V2
    profile_id: str = Field(min_length=1)
    source_of_truth_paths: list[str] = Field(min_length=1)
    stage3: dict[str, Any]
    copy_context: CopyContextFiles
    hook_lines: list[str] = Field(min_length=1)


class CopyStage4PromptBlocks(StrictContract):
    stage3_json: str = Field(min_length=2)
    hook_lines_json: str = Field(min_length=2)
    audience_product_markdown: str = Field(min_length=1)
    awareness_angle_matrix_markdown: str = Field(min_length=1)
    brand_voice_markdown: str = Field(min_length=1)
    promise_contract_json: str = Field(min_length=2)
    copy_context_json: str = Field(min_length=2)
    page_contract_json: str = Field(min_length=2)


def _count_markdown_bullets(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if line.strip().startswith("- "))


def _require_headings(*, field_name: str, markdown: str, required_headings: list[str]) -> None:
    missing = [heading for heading in required_headings if heading not in markdown]
    if missing:
        raise StrategyV2MissingContextError(
            f"Copy context '{field_name}' is missing required headings: {', '.join(missing)}. "
            "Remediation: regenerate copy_context from stage3 + awareness matrix before Stage 4."
        )


def _require_min_bullets(*, field_name: str, markdown: str, minimum: int) -> None:
    bullet_count = _count_markdown_bullets(markdown)
    if bullet_count < minimum:
        raise StrategyV2MissingContextError(
            f"Copy context '{field_name}' has {bullet_count} bullet lines; required>={minimum}. "
            "Remediation: regenerate copy_context with explicit list detail for Stage 4 grounding."
        )


def _require_stage3_copy_readiness(stage3: ProductBriefStage3) -> None:
    if len(stage3.value_stack_summary) < 3:
        raise StrategyV2MissingContextError(
            "Stage 3 value_stack_summary must include at least 3 items before Stage 4. "
            "Remediation: pick an offer variant with complete value-stack detail."
        )
    top_quotes = [quote.quote.strip() for quote in stage3.selected_angle.evidence.top_quotes if quote.quote.strip()]
    if len(top_quotes) < 5:
        raise StrategyV2MissingContextError(
            "Stage 3 selected_angle requires at least 5 top_quotes before Stage 4. "
            "Remediation: select an angle with sufficient evidence quotes."
        )
    underspecified = [quote for quote in top_quotes if len(quote) < 24]
    if underspecified:
        raise StrategyV2MissingContextError(
            "Stage 3 selected_angle top_quotes include underspecified entries (<24 chars). "
            "Remediation: provide fuller VOC quote text before Stage 4."
        )


def _require_copy_context_readiness(copy_context: CopyContextFiles) -> None:
    _require_headings(
        field_name="audience_product_markdown",
        markdown=copy_context.audience_product_markdown,
        required_headings=[
            "## Audience",
            "## Product",
            "## Selected Angle",
            "## Offer Core",
            "## Value Stack",
        ],
    )
    _require_headings(
        field_name="awareness_angle_matrix_markdown",
        markdown=copy_context.awareness_angle_matrix_markdown,
        required_headings=[
            "## Unaware",
            "## Problem-Aware",
            "## Solution-Aware",
            "## Product-Aware",
            "## Most-Aware",
        ],
    )
    _require_headings(
        field_name="brand_voice_markdown",
        markdown=copy_context.brand_voice_markdown,
        required_headings=["# Brand Voice"],
    )
    _require_headings(
        field_name="compliance_markdown",
        markdown=copy_context.compliance_markdown,
        required_headings=["# Compliance"],
    )
    _require_headings(
        field_name="mental_models_markdown",
        markdown=copy_context.mental_models_markdown,
        required_headings=["# Mental Models"],
    )
    _require_min_bullets(
        field_name="audience_product_markdown",
        markdown=copy_context.audience_product_markdown,
        minimum=8,
    )
    _require_min_bullets(
        field_name="awareness_angle_matrix_markdown",
        markdown=copy_context.awareness_angle_matrix_markdown,
        minimum=6,
    )
    _require_min_bullets(
        field_name="compliance_markdown",
        markdown=copy_context.compliance_markdown,
        minimum=3,
    )


def _serialize_json_strict(*, payload: object, field_name: str, max_chars: int) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, indent=2)
    observed_chars = len(serialized)
    if observed_chars > max_chars:
        raise StrategyV2MissingContextError(
            f"Prompt input '{field_name}' exceeds size budget ({observed_chars}>{max_chars}). "
            "Remediation: reduce upstream payload size (segment detail should stay structured, not raw-dumped)."
        )
    return serialized


def _require_text_budget(*, field_name: str, text: str, max_chars: int) -> str:
    observed_chars = len(text)
    if observed_chars > max_chars:
        raise StrategyV2MissingContextError(
            f"Prompt input '{field_name}' exceeds size budget ({observed_chars}>{max_chars}). "
            "Remediation: tighten upstream context shaping before Stage 4 prompt execution."
        )
    return text


def build_copy_stage4_input_packet(
    *,
    stage3: ProductBriefStage3,
    copy_context_payload: Mapping[str, Any],
    hook_lines: list[str],
    profile: CopyContractProfile | None = None,
) -> CopyStage4InputPacket:
    selected_profile = profile or default_copy_contract_profile()

    cleaned_hook_lines = [line.strip() for line in hook_lines if isinstance(line, str) and line.strip()]
    if not cleaned_hook_lines:
        raise StrategyV2MissingContextError(
            "Stage 3 selected angle has no usable hook lines for headline generation. "
            "Remediation: select an angle with non-empty hook starters."
        )

    copy_context = CopyContextFiles.model_validate(dict(copy_context_payload))
    _require_stage3_copy_readiness(stage3)
    _require_copy_context_readiness(copy_context)

    return CopyStage4InputPacket.model_validate(
        {
            "schema_version": SCHEMA_VERSION_V2,
            "profile_id": selected_profile.profile_id,
            "source_of_truth_paths": list(selected_profile.source_of_truth_paths),
            "stage3": stage3.model_dump(mode="python"),
            "copy_context": copy_context,
            "hook_lines": cleaned_hook_lines,
        }
    )


def build_copy_stage4_prompt_blocks(
    *,
    packet: CopyStage4InputPacket,
    promise_contract: Mapping[str, Any],
    page_contract: CopyPageContract,
) -> CopyStage4PromptBlocks:
    copy_context = packet.copy_context
    page_contract_payload = {
        "page_type": page_contract.page_type,
        "required_sections": [section.model_dump(mode="python") for section in page_contract.required_sections],
        "expected_belief_sequence": list(page_contract.expected_belief_sequence),
        "min_markdown_links": int(page_contract.min_markdown_links),
        "first_cta_section_max": int(page_contract.first_cta_section_max),
        "require_guarantee_near_cta": bool(page_contract.require_guarantee_near_cta),
    }

    return CopyStage4PromptBlocks.model_validate(
        {
            "stage3_json": _serialize_json_strict(
                payload=packet.stage3,
                field_name="stage3_json",
                max_chars=_HEADLINE_PROMPT_LIMITS["stage3_json"],
            ),
            "hook_lines_json": _serialize_json_strict(
                payload=packet.hook_lines,
                field_name="hook_lines_json",
                max_chars=_HEADLINE_PROMPT_LIMITS["hook_lines_json"],
            ),
            "audience_product_markdown": _require_text_budget(
                field_name="audience_product_markdown",
                text=copy_context.audience_product_markdown,
                max_chars=_HEADLINE_PROMPT_LIMITS["audience_product_markdown"],
            ),
            "awareness_angle_matrix_markdown": _require_text_budget(
                field_name="awareness_angle_matrix_markdown",
                text=copy_context.awareness_angle_matrix_markdown,
                max_chars=_HEADLINE_PROMPT_LIMITS["awareness_angle_matrix_markdown"],
            ),
            "brand_voice_markdown": _require_text_budget(
                field_name="brand_voice_markdown",
                text=copy_context.brand_voice_markdown,
                max_chars=_HEADLINE_PROMPT_LIMITS["brand_voice_markdown"],
            ),
            "promise_contract_json": _serialize_json_strict(
                payload=dict(promise_contract),
                field_name="promise_contract_json",
                max_chars=_PAGE_PROMPT_LIMITS["promise_contract_json"],
            ),
            "copy_context_json": _serialize_json_strict(
                payload=copy_context.model_dump(mode="python"),
                field_name="copy_context_json",
                max_chars=_PAGE_PROMPT_LIMITS["copy_context_json"],
            ),
            "page_contract_json": _serialize_json_strict(
                payload=page_contract_payload,
                field_name="page_contract_json",
                max_chars=_PAGE_PROMPT_LIMITS["page_contract_json"],
            ),
        }
    )


def render_copy_headline_runtime_instruction(
    *,
    packet: CopyStage4InputPacket,
) -> str:
    copy_context = packet.copy_context
    stage3_json = _serialize_json_strict(
        payload=packet.stage3,
        field_name="stage3_json",
        max_chars=_HEADLINE_PROMPT_LIMITS["stage3_json"],
    )
    hook_lines_json = _serialize_json_strict(
        payload=packet.hook_lines,
        field_name="hook_lines_json",
        max_chars=_HEADLINE_PROMPT_LIMITS["hook_lines_json"],
    )
    audience_product_markdown = _require_text_budget(
        field_name="audience_product_markdown",
        text=copy_context.audience_product_markdown,
        max_chars=_HEADLINE_PROMPT_LIMITS["audience_product_markdown"],
    )
    awareness_angle_matrix_markdown = _require_text_budget(
        field_name="awareness_angle_matrix_markdown",
        text=copy_context.awareness_angle_matrix_markdown,
        max_chars=_HEADLINE_PROMPT_LIMITS["awareness_angle_matrix_markdown"],
    )
    brand_voice_markdown = _require_text_budget(
        field_name="brand_voice_markdown",
        text=copy_context.brand_voice_markdown,
        max_chars=_HEADLINE_PROMPT_LIMITS["brand_voice_markdown"],
    )
    compliance_markdown = _require_text_budget(
        field_name="compliance_markdown",
        text=copy_context.compliance_markdown,
        max_chars=_HEADLINE_PROMPT_LIMITS["compliance_markdown"],
    )
    mental_models_markdown = _require_text_budget(
        field_name="mental_models_markdown",
        text=copy_context.mental_models_markdown,
        max_chars=_HEADLINE_PROMPT_LIMITS["mental_models_markdown"],
    )
    return (
        "## Runtime Input Block\n"
        f"COPY_PROFILE_ID:\n{packet.profile_id}\n\n"
        f"SOURCE_OF_TRUTH_PATHS:\n{_serialize_json_strict(payload=packet.source_of_truth_paths, field_name='source_of_truth_paths', max_chars=12000)}\n\n"
        f"STAGE3_JSON:\n{stage3_json}\n\n"
        f"HOOK_LINES_JSON:\n{hook_lines_json}\n\n"
        f"AUDIENCE_PRODUCT_MARKDOWN:\n{audience_product_markdown}\n\n"
        f"AWARENESS_MATRIX_MARKDOWN:\n{awareness_angle_matrix_markdown}\n\n"
        f"BRAND_VOICE_MARKDOWN:\n{brand_voice_markdown}\n\n"
        f"COMPLIANCE_MARKDOWN:\n{compliance_markdown}\n\n"
        f"MENTAL_MODELS_MARKDOWN:\n{mental_models_markdown}\n\n"
        "## Runtime Output Contract\n"
        "Return JSON with headline_candidates array (3-12 candidates)."
    )


def render_copy_page_runtime_instruction(
    *,
    packet: CopyStage4InputPacket,
    headline: str,
    promise_contract: Mapping[str, Any],
    page_contract: CopyPageContract,
    repair_directives: str | None = None,
) -> str:
    cleaned_headline = headline.strip()
    if not cleaned_headline:
        raise StrategyV2MissingContextError(
            "Copy page generation requires a non-empty headline. "
            "Remediation: complete headline QA pass before page generation."
        )

    blocks = build_copy_stage4_prompt_blocks(
        packet=packet,
        promise_contract=promise_contract,
        page_contract=page_contract,
    )
    quality_profile = get_copy_quality_thresholds(page_type=page_contract.page_type)
    headline_keywords = _extract_headline_keywords(cleaned_headline)
    headline_keyword_hint = (
        ", ".join(headline_keywords)
        if headline_keywords
        else "use concrete nouns/verbs from the headline"
    )
    stage3_json_page = _serialize_json_strict(
        payload=packet.stage3,
        field_name="stage3_json",
        max_chars=_PAGE_PROMPT_LIMITS["stage3_json"],
    )
    if page_contract.page_type == "presell_advertorial":
        hard_quality_constraints = (
            f"- Output {quality_profile.word_floor}-{quality_profile.word_ceiling} total words.\n"
            f"- Use at least {quality_profile.min_sections} `##` H2 sections.\n"
            f"- Include {quality_profile.cta_min}-{quality_profile.cta_max} canonical CTA sections (headings containing `CTA` or `Continue to Offer`).\n"
            f"- Include at least {quality_profile.mechanism_depth_floor or 0} words in mechanism-focused sections.\n"
            f"- Include at least {quality_profile.offer_depth_floor or 0} words in offer/CTA bridge sections.\n"
            f"- Include at least {page_contract.min_markdown_links} markdown links using `[text](url)` format.\n"
            "- Use section headings that map clearly to the required page contract sections."
        )
        template_payload_rules = (
            "## Template Payload Rules (strict)\n"
            "- `template_payload` must match `pre-sales-listicle` shape exactly.\n"
            "- Required keys: hero, reasons, marquee, pitch, reviews, review_wall, floating_cta.\n"
            "- `hero` requires non-empty title, subtitle, and `badges`.\n"
            "- `hero.badges` must be exactly 3 items and must map to: "
            "(1) `{ value: <12-15000 review count>, label: '5-Star Reviews' }`, "
            "(2) `{ value: '24/7', label: 'Customer Support' }`, "
            "(3) `{ label: 'Risk Free Trial' }`.\n"
            "- Every hero badge icon prompt must describe a distinct icon subject; do not repeat the same prompt.\n"
            "- `reasons` items require integer number + non-empty title/body + image object ({alt, optional prompt}).\n"
            "- `reasons[].image.prompt` must stay editorial and non-salesy. Before the marquee, do not depict the product, packaging, exact book cover, or any product reference image.\n"
            "- `reviews` requires at least 3 objects with non-empty `text` and `author` (optional `rating`, `verified`).\n"
            "- `pitch` requires title, bullets array, cta_label, and image object ({alt, optional prompt}).\n"
            "- `pitch.image.prompt` is the first place where product-aware imagery is allowed after the marquee.\n"
            "- `review_wall` requires `title` and `button_label`.\n"
            "- Return only real copy content; do not invent placeholders."
        )
        runtime_output_contract = (
            "Return JSON with keys `markdown` and `template_payload`. "
            "Use section headings that align to PAGE_SECTION_CONTRACT_JSON."
        )
    else:
        hard_quality_constraints = (
            f"- Output {quality_profile.word_floor}-{quality_profile.word_ceiling} total words.\n"
            f"- Use at least {quality_profile.min_sections} `##` H2 sections.\n"
            f"- Include {quality_profile.cta_min}-{quality_profile.cta_max} canonical CTA sections (headings containing `CTA` or `Continue to Offer`).\n"
            f"- Include at least {quality_profile.proof_depth_floor or 0} words in proof/evidence/testimonial sections.\n"
            f"- Include at least {quality_profile.guarantee_depth_floor or 0} words in guarantee/risk-reversal sections.\n"
            f"- Include at least {page_contract.min_markdown_links} markdown links using `[text](url)` format.\n"
            "- Use section headings that map clearly to the required page contract sections."
        )
        template_payload_rules = (
            "## Template Payload Rules (strict)\n"
            "- `template_payload_json` must be a JSON-serialized object that matches `sales-pdp` shape exactly.\n"
            "- Top-level keys allowed: hero, problem, mechanism, social_proof, whats_inside, bonus, guarantee, faq, faq_pills, marquee_items, urgency_message, cta_close.\n"
            "- Do NOT emit alternative schema keys like schema, template_id, product_name, product_subtitle, problem_recap, cta_primary, pricing, legal_disclaimer.\n"
            "- `hero.primary_cta_subbullets` must contain exactly 2 concise bullets.\n"
            "- `mechanism.paragraphs` must contain exactly 1 short intro paragraph before bullets.\n"
            "- `mechanism.bullets` must be exactly 5 objects with `title` + `body`.\n"
            "- `mechanism.callout` must include left_title/left_body/right_title/right_body.\n"
            "- `mechanism.comparison` must include badge/title/swipe_hint/columns/rows.\n"
            "- `mechanism.comparison.badge` must be exactly `US vs THEM`.\n"
            "- `mechanism.comparison.title` must put your approach first: `<your approach> vs. <alternative>`.\n"
            "- `mechanism.comparison.columns` must be an object with exactly two keys: `pup` and `disposable`.\n"
            "- `mechanism.comparison.rows[]` must use exactly `label`, `pup`, and `disposable` keys.\n"
            "- Do not use legacy comparison row keys like `feature`, `us`, `them`, `left`, `right`, `col1`, `col2`, or `values`.\n"
            "- `guarantee.title` must use `Risk Free Guarantee` language. If you include a timeframe, format it like `<X>-Day Risk Free Guarantee`.\n"
            "- Do not use `Workflow Fit Guarantee` phrasing anywhere.\n"
            f"- `faq.items` must contain at least 8 entries.\n"
            f"- `faq_pills` must contain at least 8 entries and use {{label, answer}}; these drive the moving FAQ pills in the purchase module.\n"
            "- `marquee_items` must be non-empty and specific to this product angle (no template carryover text).\n"
            "- `urgency_message` must be specific to this campaign and explicitly convey sell-out urgency.\n"
            "- `whats_inside.benefits` must be exactly 4 short, outcome-led purchase-module bullets.\n"
            "- Each `whats_inside.benefits[]` item must be 2-6 words, <= 38 chars, and instantly scannable.\n"
            "- `whats_inside.benefits[]` must describe the result/ease/action, not an internal asset or document label.\n"
            "- Do not end `whats_inside.benefits[]` on feature labels like workflow, guide, reference, checklist, worksheet, pages, notes, prompts, or scripts.\n"
            "- Do not use parentheses, colons, arrows, commas, or sentence-style explanation in `whats_inside.benefits[]`.\n"
            "- Keep `bonus.free_gifts_body` concise and scannable.\n"
            "- Return only real copy content; do not invent placeholders."
        )
        runtime_output_contract = (
            "Return JSON with keys `markdown` and `template_payload_json`. "
            "`template_payload_json` must be a JSON-serialized string object (no markdown fences) "
            "that conforms to the strict sales template payload contract. "
            "Use section headings that align to PAGE_SECTION_CONTRACT_JSON."
        )

    cta_budget_rules = (
        "## CTA Budget Rules (strict)\n"
        f"- Keep total canonical CTA sections between {quality_profile.cta_min} and {quality_profile.cta_max}; never exceed {quality_profile.cta_max}.\n"
        "- Canonical CTA sections are identified by headings containing `CTA` or `Continue to Offer`.\n"
        "- URL path tokens alone do not count as CTA intent.\n"
        "- Non-CTA sections may include informational links, but explicit purchase directives belong in canonical CTA sections.\n"
        "- Explicit purchase directives include buy/order/checkout/add-to-cart/complete-purchase language."
    )

    heading_rules = (
        "## Section Heading Format (strict)\n"
        "- Every `##` heading must start with the canonical section marker from PAGE_SECTION_CONTRACT_JSON.\n"
        "- After the canonical marker, add a topical phrase tied to the headline.\n"
        "- Format: `## <Canonical Marker>: <Topical Phrase>`.\n"
        f"- At least 60% of headings should include one of these headline terms: {headline_keyword_hint}.\n"
        "- Do not use marker-only headings like `## Hook/Lead` with no topical phrase."
    )

    promise_timing_rules = (
        "## Promise Delivery Rules\n"
        "- DELIVERY_TEST content is binding and must be delivered, not paraphrased away.\n"
        "- Begin paying the promise in early sections and keep it before the structural pivot.\n"
        "- If MINIMUM_DELIVERY references section 1/2 timing, ensure concrete promise terms appear in sections 1-2.\n"
        "- Include at least one explicit sentence that mirrors DELIVERY_TEST semantics."
    )

    repair_block = ""
    if repair_directives:
        repair_block = (
            "## Repair Directives (must fix all)\n"
            f"{repair_directives.strip()}\n\n"
        )

    return (
        "## Runtime Input Block\n"
        f"COPY_PROFILE_ID:\n{packet.profile_id}\n\n"
        f"PAGE_TYPE:\n{page_contract.page_type}\n\n"
        f"HEADLINE:\n{cleaned_headline}\n\n"
        f"PROMISE_CONTRACT_JSON:\n{blocks.promise_contract_json}\n\n"
        f"PAGE_SECTION_CONTRACT_JSON:\n{blocks.page_contract_json}\n\n"
        f"STAGE3_JSON:\n{stage3_json_page}\n\n"
        f"COPY_CONTEXT_JSON:\n{blocks.copy_context_json}\n\n"
        f"SOURCE_OF_TRUTH_PATHS:\n{_serialize_json_strict(payload=packet.source_of_truth_paths, field_name='source_of_truth_paths', max_chars=12000)}\n\n"
        "## Hard Quality Constraints (must satisfy all)\n"
        f"{hard_quality_constraints}\n\n"
        f"{cta_budget_rules}\n\n"
        f"{heading_rules}\n\n"
        f"{promise_timing_rules}\n\n"
        f"{template_payload_rules}\n\n"
        f"{repair_block}"
        "## Runtime Output Contract\n"
        f"{runtime_output_contract}"
    )


def parse_minimum_delivery_section_index(*, minimum_delivery: str, total_sections: int) -> int:
    if total_sections <= 0:
        return 1

    normalized = minimum_delivery.strip().lower()
    if not normalized:
        return max(1, (total_sections + 1) // 2)

    # Prefer resolution boundary when both begin + resolve sections are specified.
    resolved_match = re.search(r"(?:resolved|resolve|complete|substantially)\s+by\s+section\s*(\d+)", normalized)
    if resolved_match is not None:
        requested = int(resolved_match.group(1))
        return max(1, min(total_sections, requested))

    generic_by_match = re.search(r"\bby\s+section\s*(\d+)", normalized)
    if generic_by_match is not None:
        requested = int(generic_by_match.group(1))
        return max(1, min(total_sections, requested))

    section_numbers = [int(value) for value in re.findall(r"section\s*(\d+)", normalized)]
    if section_numbers:
        requested = max(section_numbers)
        return max(1, min(total_sections, requested))

    if "first section" in normalized or "opening" in normalized or "first third" in normalized:
        return max(1, (total_sections + 2) // 3)
    if "midpoint" in normalized or "mid-point" in normalized or "middle" in normalized:
        return max(1, (total_sections + 1) // 2)

    return max(1, (total_sections + 1) // 2)


def _extract_headline_keywords(headline: str, *, max_terms: int = 8) -> list[str]:
    words = re.findall(r"[a-zA-Z]{4,}", headline.lower())
    deduped: list[str] = []
    for word in words:
        if word in _HEADLINE_KEYWORD_STOPWORDS:
            continue
        if word in deduped:
            continue
        deduped.append(word)
        if len(deduped) >= max_terms:
            break
    return deduped
