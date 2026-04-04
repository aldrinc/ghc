from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.campaign_creative_context import CampaignManualCreativeContextUpsertRequest


class EmberImportAdapterError(ValueError):
    pass


_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(?P<item>.+?)\s*$", re.MULTILINE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class EmberArtifactBundle:
    ember_root: Path
    knowledge_base: Path
    signal_report: Path
    cso: Path
    offer_document: Path
    headline_pool: Path
    presell_page: Path
    sales_page: Path

    @classmethod
    def from_path(cls, path: str | Path) -> "EmberArtifactBundle":
        candidate = Path(path).expanduser().resolve()
        ember_root = _resolve_ember_root(candidate)
        bundle = cls(
            ember_root=ember_root,
            knowledge_base=ember_root / "EMBER-KNOWLEDGE-BASE.md",
            signal_report=ember_root / "signal-hunter" / "SIGNAL-HUNTER-REPORT-EMBER.md",
            cso=ember_root / "cso" / "EMBER-CSO.md",
            offer_document=ember_root / "offer" / "EMBER-OFFER-DOCUMENT.json",
            headline_pool=ember_root / "headlines" / "HEADLINE-POOL-EMBER-BRAIN-FUEL-DEFICIT.md",
            presell_page=ember_root / "pages" / "EMBER-PRESALE-ADVERTORIAL.md",
            sales_page=ember_root / "pages" / "EMBER-SALES-PAGE.md",
        )
        missing = [str(file_path) for file_path in bundle.__dict__.values() if isinstance(file_path, Path) and not file_path.exists()]
        if missing:
            raise EmberImportAdapterError(
                "EMBER artifact bundle is incomplete. Missing required files:\n"
                + "\n".join(f"- {item}" for item in missing)
            )
        return bundle


def build_ember_manual_creative_context_request(
    ember_path: str | Path,
    *,
    experiment_id: str | None = None,
    experiment_name: str | None = None,
    variant_id: str | None = None,
    variant_name: str | None = None,
    channel: str = "facebook",
) -> CampaignManualCreativeContextUpsertRequest:
    bundle = EmberArtifactBundle.from_path(ember_path)
    kb_text = _read_text(bundle.knowledge_base)
    signal_report_text = _read_text(bundle.signal_report)
    cso_text = _read_text(bundle.cso)
    presell_text = _read_text(bundle.presell_page)
    sales_text = _read_text(bundle.sales_page)
    headline_pool_text = _read_text(bundle.headline_pool)
    offer = _read_json(bundle.offer_document)

    angle_name = _extract_cso_field(cso_text, "angle_name")
    if not angle_name:
        raise EmberImportAdapterError("Unable to resolve angle_name from EMBER CSO.")
    angle_id = _slugify(angle_name)

    audience_state = _extract_cso_field(cso_text, "audience_state")
    desired_outcome = _extract_cso_field(cso_text, "desired_outcome")
    belief_shift = _extract_cso_field(cso_text, "belief_shift")
    mechanism_frame = _extract_cso_field(cso_text, "mechanism_frame")
    proof_stack_lines = _extract_numbered_lines(_extract_cso_field(cso_text, "proof_stack"))
    offer_frame = _extract_cso_field(cso_text, "offer_frame")
    cta_goal = _extract_cso_field(cso_text, "cta_goal")
    inference_boundary = _extract_cso_field(cso_text, "inference_boundary")

    presell_headline = _extract_bold_field(presell_text, "Headline")
    sales_headline = _extract_bold_field(sales_text, "Headline")
    product_name = _extract_bold_field(kb_text, "Full product name")
    active_ingredient = _extract_bold_field(kb_text, "Active ingredient")
    format_name = _extract_bold_field(kb_text, "Format")
    guarantee_name = _extract_bold_field(kb_text, "Guarantee")
    founder_voice = _extract_bold_field(kb_text, "Voice register")
    founder_key_line = _extract_bold_field(kb_text, "Key line")

    selected_variant = _select_default_bundle(offer)
    bundle_tiers = offer.get("bundle_tiers") or []
    if not isinstance(bundle_tiers, list) or not bundle_tiers:
        raise EmberImportAdapterError("Offer document bundle_tiers are missing or invalid.")

    primary_evidence = proof_stack_lines[:5] or [
        "Women carry significantly lower creatine stores than men.",
        "Creatine supports ATP recharge and cognitive performance.",
        "VOC repeatedly shows dementia fear, doctor dismissal, and identity loss.",
    ]
    if not primary_evidence:
        primary_evidence = _extract_bullets(signal_report_text)[:3]

    description = (
        "Perimenopause brain fog is reframed as a creatine-backed brain fuel deficit "
        "instead of aging, stress, or early dementia."
    )

    core_promise = (
        "Trust your own brain again by refueling the energy pathway perimenopause quietly drains away."
    )
    selected_variant_name = str(selected_variant.get("tier_name") or "").strip()
    if not selected_variant_name:
        raise EmberImportAdapterError("Offer document default bundle tier is missing tier_name.")
    selected_variant_id = _slugify(selected_variant_name)

    resolved_experiment_id = experiment_id or angle_id
    resolved_experiment_name = experiment_name or angle_name
    resolved_variant_id = variant_id or f"{angle_id}-story-hook"
    resolved_variant_name = variant_name or "Story Hook"

    audience_product_markdown = _build_audience_product_markdown(
        audience_state=audience_state,
        product_name=product_name,
        format_name=format_name,
        active_ingredient=active_ingredient,
        angle_name=angle_name,
        angle_description=description,
        belief_shift=belief_shift,
        core_promise=core_promise,
        cta_goal=cta_goal,
        selected_variant=selected_variant,
        offer=offer,
    )
    brand_voice_markdown = _build_brand_voice_markdown(
        founder_voice=founder_voice,
        founder_key_line=founder_key_line,
        product_name=product_name,
        headline_pool_text=headline_pool_text,
    )
    compliance_markdown = _build_compliance_markdown(
        inference_boundary=inference_boundary,
        guarantee_name=guarantee_name,
        presell_text=presell_text,
    )
    mental_models_markdown = _build_mental_models_markdown(
        audience_state=audience_state,
        desired_outcome=desired_outcome,
        signal_report_text=signal_report_text,
        belief_shift=belief_shift,
    )
    awareness_angle_matrix_markdown = _build_awareness_angle_matrix_markdown(
        angle_name=angle_name,
        presell_headline=presell_headline,
        sales_headline=sales_headline,
        cta_goal=cta_goal,
    )

    payload = {
        "schemaVersion": 1,
        "provider": "manual",
        "angles": {
            "selectedAngleId": angle_id,
            "angleLibrary": [
                {
                    "angleId": angle_id,
                    "angleName": angle_name,
                    "description": description,
                    "evidence": primary_evidence,
                }
            ],
        },
        "offer": {
            "ump": "Restore the brain fuel perimenopause quietly drains away.",
            "ums": (
                "A 5g clinical-dose Creapure creatine gummy that supports ATP recharge in "
                "a format women will actually take consistently."
            ),
            "corePromise": core_promise,
            "valueStackSummary": _build_value_stack_summary(offer, selected_variant_name, guarantee_name),
            "guaranteeType": guarantee_name or None,
            "pricingRationale": _build_pricing_rationale(offer),
            "selectedVariantId": selected_variant_id,
            "selectedVariantName": selected_variant_name,
            "offerDetailsMarkdown": _render_offer_details_markdown(
                offer=offer,
                offer_frame=offer_frame,
                selected_variant_name=selected_variant_name,
            ),
        },
        "copyDocument": {
            "headline": presell_headline,
            "promiseContract": {
                "loopQuestion": (
                    "Why does perimenopause brain fog feel like dementia when the real problem "
                    "may be a fuel deficit your doctor never named?"
                ),
                "specificPromise": (
                    "Restore sharper recall, steadier focus, and the confidence to trust your "
                    "own brain again by replenishing the creatine-backed fuel pathway."
                ),
                "deliveryTest": (
                    "The buyer should feel the fog thinning, words arriving faster, and normal "
                    "mental tasks taking less effort over the first 30 days."
                ),
                "minimumDelivery": (
                    "Finish the first 30 Day Supply; if she does not notice her words coming back "
                    "faster, her focus holding longer, or the cotton-wool feeling lifting, she gets a full refund."
                ),
            },
            "presellMarkdown": presell_text,
            "salesPageMarkdown": sales_text,
            "templatePayloads": {
                "presell": {
                    "sourceDoc": bundle.presell_page.name,
                    "headline": presell_headline,
                    "pageType": "advertorial",
                },
                "sales": {
                    "sourceDoc": bundle.sales_page.name,
                    "headline": sales_headline,
                    "pageType": "sales",
                },
            },
        },
        "copyContext": {
            "audienceProductMarkdown": audience_product_markdown,
            "brandVoiceMarkdown": brand_voice_markdown,
            "complianceMarkdown": compliance_markdown,
            "mentalModelsMarkdown": mental_models_markdown,
            "awarenessAngleMatrixMarkdown": awareness_angle_matrix_markdown,
        },
        "experimentSpecs": [
            {
                "id": resolved_experiment_id,
                "name": resolved_experiment_name,
                "hypothesis": (
                    "Framing perimenopause brain fog as a fuel deficit instead of decline will "
                    "increase qualified click-through and conversion intent."
                ),
                "metricIds": ["ctr", "lpv", "cvr"],
                "variants": [
                    {
                        "id": resolved_variant_id,
                        "name": resolved_variant_name,
                        "description": presell_headline,
                        "channels": [channel],
                        "guardrails": [
                            "Do not claim Ember diagnoses, treats, cures, or prevents disease.",
                            "Do not claim a perimenopause-specific creatine cognition trial exists.",
                            "Frame the mechanism as research-backed support, not guaranteed medical treatment.",
                        ],
                    }
                ],
            }
        ],
    }
    return CampaignManualCreativeContextUpsertRequest.model_validate(payload)


def _resolve_ember_root(path: Path) -> Path:
    if (path / "EMBER-KNOWLEDGE-BASE.md").exists():
        return path
    nested = path / "FutrGroup-Hookd-Project" / "EMBER"
    if nested.exists():
        return nested
    raise EmberImportAdapterError(
        f"Could not resolve EMBER artifact root from '{path}'. "
        "Pass either the EMBER folder itself or the mos_strategy_v3 workspace root."
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EmberImportAdapterError(f"Expected JSON object in {path}")
    return data


def _extract_bold_field(text: str, label: str) -> str:
    pattern = re.compile(rf"^\*\*{re.escape(label)}:\*\*\s*(?P<value>.+?)\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    return match.group("value").strip().strip('"')


def _extract_cso_field(text: str, field_name: str) -> str:
    pattern = re.compile(
        rf"^###\s+\d+\.\s+{re.escape(field_name)}\s*$\n(?P<body>.*?)(?=^###\s+\d+\.\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group("body").strip()


def _extract_numbered_lines(text: str) -> list[str]:
    lines = []
    for match in _LIST_ITEM_RE.finditer(text or ""):
        item = re.sub(r"\s+", " ", match.group("item")).strip()
        if item:
            lines.append(item)
    return lines


def _extract_bullets(text: str) -> list[str]:
    return _extract_numbered_lines(text)


def _slugify(value: str) -> str:
    lowered = value.lower().strip()
    collapsed = _NON_ALNUM_RE.sub("-", lowered).strip("-")
    return collapsed or "ember-import"


def _select_default_bundle(offer: dict[str, Any]) -> dict[str, Any]:
    bundle_tiers = offer.get("bundle_tiers") or []
    if not isinstance(bundle_tiers, list):
        raise EmberImportAdapterError("bundle_tiers must be a list.")
    for tier in bundle_tiers:
        if isinstance(tier, dict) and tier.get("is_default") is True:
            return tier
    for tier in bundle_tiers:
        if isinstance(tier, dict):
            return tier
    raise EmberImportAdapterError("No bundle tiers found in offer document.")


def _build_value_stack_summary(offer: dict[str, Any], selected_variant_name: str, guarantee_name: str) -> str:
    tiers = offer.get("bundle_tiers") or []
    summaries: list[str] = []
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        tier_name = str(tier.get("tier_name") or "").strip()
        contents = str(tier.get("contents") or "").strip()
        if tier_name and contents:
            summaries.append(f"{tier_name}: {contents}")
    guarantee = f" Backed by the {guarantee_name}." if guarantee_name else ""
    joined = " | ".join(summaries[:3])
    return f"Default offer is {selected_variant_name}. {joined}.{guarantee}".strip()


def _build_pricing_rationale(offer: dict[str, Any]) -> str:
    price_anchor = offer.get("price_anchor") or {}
    if not isinstance(price_anchor, dict):
        return "Pricing is framed against wasted spend on symptom-chasing solutions and repeated doctor visits."
    current_spend = str(price_anchor.get("current_spend") or "").strip()
    daily_cost_frame = str(price_anchor.get("daily_cost_frame") or "").strip()
    per_incident_frame = str(price_anchor.get("per_incident_frame") or "").strip()
    parts = [part for part in [current_spend, daily_cost_frame, per_incident_frame] if part]
    return " ".join(parts).strip()


def _render_offer_details_markdown(
    *,
    offer: dict[str, Any],
    offer_frame: str,
    selected_variant_name: str,
) -> str:
    lines = [
        "# Offer Details",
        "",
        "## Protocol",
        str(offer.get("protocol_description") or "").strip(),
        "",
        "## Offer Frame",
        offer_frame,
        "",
        "## Default Variant",
        f"- {selected_variant_name}",
        "",
        "## Bundle Tiers",
    ]
    for tier in offer.get("bundle_tiers") or []:
        if not isinstance(tier, dict):
            continue
        tier_name = str(tier.get("tier_name") or "").strip()
        contents = str(tier.get("contents") or "").strip()
        price = str(tier.get("price") or "").strip()
        compare_at = str(tier.get("compare_at") or "").strip()
        savings = str(tier.get("savings") or "").strip()
        per_day_cost = str(tier.get("per_day_cost") or "").strip()
        framing = str(tier.get("framing") or "").strip()
        badge = str(tier.get("badge") or "").strip()
        lines.append(f"### {tier_name}")
        for item in [
            f"- Price: {price}" if price else "",
            f"- Compare at: {compare_at}" if compare_at else "",
            f"- Savings: {savings}" if savings else "",
            f"- Per day: {per_day_cost}" if per_day_cost else "",
            f"- Framing: {framing}" if framing else "",
            f"- Badge: {badge}" if badge else "",
            f"- Includes: {contents}" if contents else "",
        ]:
            if item:
                lines.append(item)
        lines.append("")

    guarantee = offer.get("guarantee") or {}
    if isinstance(guarantee, dict):
        lines.extend(
            [
                "## Guarantee",
                f"- Name: {str(guarantee.get('name') or '').strip()}",
                f"- Terms: {str(guarantee.get('terms') or '').strip()}",
                f"- Confidence language: {str(guarantee.get('confidence_language') or '').strip()}",
                "",
            ]
        )

    upsell_structure = offer.get("upsell_structure") or {}
    if isinstance(upsell_structure, dict):
        lines.extend(
            [
                "## Upsell Structure",
                f"- Post purchase: {str(upsell_structure.get('post_purchase') or '').strip()}",
                f"- Cross sell: {str(upsell_structure.get('cross_sell') or '').strip()}",
                f"- Subscription frame: {str(upsell_structure.get('subscription_frame') or '').strip()}",
                "",
            ]
        )

    proof_requirements = offer.get("proof_requirements") or []
    if isinstance(proof_requirements, list) and proof_requirements:
        lines.append("## Proof Requirements")
        for item in proof_requirements:
            if isinstance(item, str) and item.strip():
                lines.append(f"- {item.strip()}")
        lines.append("")

    return "\n".join(line for line in lines if line is not None).strip()


def _build_audience_product_markdown(
    *,
    audience_state: str,
    product_name: str,
    format_name: str,
    active_ingredient: str,
    angle_name: str,
    angle_description: str,
    belief_shift: str,
    core_promise: str,
    cta_goal: str,
    selected_variant: dict[str, Any],
    offer: dict[str, Any],
) -> str:
    normalized_belief_shift = re.sub(r"\s+", " ", belief_shift).strip()
    selected_variant_name = str(selected_variant.get("tier_name") or "").strip()
    selected_variant_contents = str(selected_variant.get("contents") or "").strip()
    bundle_lines = []
    for tier in offer.get("bundle_tiers") or []:
        if not isinstance(tier, dict):
            continue
        tier_name = str(tier.get("tier_name") or "").strip()
        contents = str(tier.get("contents") or "").strip()
        if tier_name and contents:
            bundle_lines.append(f"- {tier_name}: {contents}")

    lines = [
        "## Audience",
        audience_state,
        "",
        "## Product",
        f"- Name: {product_name}",
        f"- Format: {format_name}",
        f"- Active ingredient: {active_ingredient}",
        f"- Default variant: {selected_variant_name}",
        f"- Default contents: {selected_variant_contents}",
        "",
        "## Selected Angle",
        f"- Name: {angle_name}",
        f"- Description: {angle_description}",
        f"- Belief shift: {normalized_belief_shift}",
        "",
        "## Offer Core",
        f"- Core promise: {core_promise}",
        f"- CTA goal: {cta_goal}",
        "",
        "## Value Stack",
        *bundle_lines,
    ]
    return "\n".join(lines).strip()


def _build_brand_voice_markdown(
    *,
    founder_voice: str,
    founder_key_line: str,
    product_name: str,
    headline_pool_text: str,
) -> str:
    story_hook = ""
    for line in headline_pool_text.splitlines():
        normalized = line.strip()
        if normalized.startswith('4. "'):
            story_hook = normalized.split('"', 1)[1].rsplit('"', 1)[0]
            break
    lines = [
        "# Brand Voice",
        "",
        "## Tone",
        founder_voice or "Clinical expertise softened by personal vulnerability.",
        "",
        "## Founder Frame",
        founder_key_line or "Lead with the trigger event before the credential.",
        "",
        "## Writing Rules",
        f"- Keep {product_name} framed as a protocol, not a generic supplement.",
        "- Lead with the wound, then the mechanism, then the protocol.",
        "- Sound calm, direct, and proof-aware. Avoid hype, miracle language, and bodybuilding cues.",
        "- Use founder authority after the story hook, not before it.",
        f"- Default story hook: {story_hook}" if story_hook else "- Default to story-led authority framing.",
    ]
    return "\n".join(lines).strip()


def _build_compliance_markdown(
    *,
    inference_boundary: str,
    guarantee_name: str,
    presell_text: str,
) -> str:
    disclaimer = ""
    if "## Disclaimer" in presell_text:
        disclaimer = presell_text.split("## Disclaimer", 1)[1].strip()
    lines = [
        "# Compliance",
        "",
        "## Claims Guardrails",
        "- Do not claim the product diagnoses, treats, cures, or prevents disease.",
        "- Do not say there is a direct perimenopause-specific creatine cognition trial.",
        "- Keep the mechanism framed as adjacent evidence and plausible biology, not settled clinical fact.",
        f"- Keep {guarantee_name or 'the guarantee'} framed as risk reversal, not proof of medical efficacy.",
        "",
        "## Evidence Boundary",
        inference_boundary,
    ]
    if disclaimer:
        lines.extend(["", "## Required Disclaimer", disclaimer])
    return "\n".join(lines).strip()


def _build_mental_models_markdown(
    *,
    audience_state: str,
    desired_outcome: str,
    signal_report_text: str,
    belief_shift: str,
) -> str:
    dominant_identity_line = ""
    marker = "### Dominant Buyer Identity (F3)"
    if marker in signal_report_text:
        dominant_identity_line = signal_report_text.split(marker, 1)[1].split("###", 1)[0].strip()
    lines = [
        "# Mental Models",
        "",
        "## Identity Recovery",
        desired_outcome,
        "",
        "## Gaslighting Relief",
        "Validate that the symptoms are real, the fear is rational, and the buyer was failed by the system before the offer appears.",
        "",
        "## Mechanism Before Miracle",
        re.sub(r"\s+", " ", belief_shift).strip(),
        "",
        "## Protocol Framing",
        "Present Ember as a daily clarity protocol that restores consistency and self-trust, not a one-off miracle supplement.",
        "",
        "## Buyer Context",
        dominant_identity_line or audience_state,
    ]
    return "\n".join(lines).strip()


def _build_awareness_angle_matrix_markdown(
    *,
    angle_name: str,
    presell_headline: str,
    sales_headline: str,
    cta_goal: str,
) -> str:
    lines = [
        "## Unaware",
        "Open with the founder's disappearing-word story and the hidden fuel-deficit reveal before naming the product.",
        "",
        "## Problem-Aware",
        f"Use '{presell_headline}' to reframe terrifying brain fog moments away from aging or dementia and toward a named deficit.",
        "",
        "## Solution-Aware",
        f"Introduce {angle_name} as the mechanism-first answer after failed HRT, generic supplements, and doctor dismissal.",
        "",
        "## Product-Aware",
        f"Use '{sales_headline}' to connect the protocol, the 5g clinical dose, and the selected bundle structure.",
        "",
        "## Most-Aware",
        f"Reinforce the guarantee, the value stack, and the CTA: {cta_goal}",
    ]
    return "\n".join(lines).strip()
