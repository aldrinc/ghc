from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.funnel_tools import (
    _build_imported_html_document_puck_data,
    _build_strategy_prompt_context,
    _compact_prompt_payload,
    _coerce_text_replacements,
    _truncate_prompt_text,
)
from app.db.models import Campaign, ProductVariant, Site, SiteFunnel, SiteFunnelStep, SitePage
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.llm.client import LLMClient, LLMGenerationParams
from app.services import funnel_ai
from app.services.campaign_creative_context import load_campaign_creative_context
from app.services.claude_files import call_claude_structured_message
from app.services.funnels import slugify
from app.services.html_funnel_reference import (
    HtmlReferenceError,
    HtmlStructureMismatchError,
    apply_html_text_replacements,
    assert_html_text_only_rewrite,
    build_html_reference_prompt_context,
    extract_editable_html_text_nodes,
    summarize_html_reference,
)
from app.services.imported_html_runtime import (
    ImportedHtmlRuntimeValidationError,
    build_imported_html_generation_context,
    coerce_imported_html_instrumentation_manifest,
    imported_html_instrumentation_schema,
    imported_html_selector_hint,
    validate_imported_html_document_manifest,
)
from app.services.paid_ads_qa import clean_optional_text, normalize_tracking_provider
from app.services.site_funnels import get_funnel
from app.services.site_funnel_template_imports import get_template_import


class SiteFunnelPreparationError(ValueError):
    pass


_TemplateKind = Literal["sales-pdp", "pre-sales-listicle"]
_PageIntent = Literal["sales", "pre_sales"]
_GeneratedCopySource = Literal["campaign_materialized", "generated_for_selected_angle"]


def prepare_site_funnel_template(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    site_id: str,
    funnel_id: str,
    created_by_user_external_id: str | None,
) -> SiteFunnel:
    site = session.scalars(
        select(Site).where(
            Site.id == site_id,
            Site.org_id == org_id,
            Site.client_id == client_id,
        )
    ).first()
    if site is None:
        raise SiteFunnelPreparationError("Site not found.")

    funnel = get_funnel(session, site_id, funnel_id)
    if funnel is None:
        raise SiteFunnelPreparationError("Funnel not found.")

    template_import_id = str(funnel.template_import_id or "").strip()
    if not template_import_id:
        raise SiteFunnelPreparationError("Template import is required before preparation.")

    template_import = get_template_import(
        session,
        site_id=site_id,
        template_import_id=template_import_id,
    )
    if template_import is None:
        raise SiteFunnelPreparationError("Template import not found.")

    page_intent = _require_page_intent(funnel.page_intent)
    if not funnel.product_id:
        raise SiteFunnelPreparationError("productId is required before preparation.")
    if not funnel.campaign_id:
        raise SiteFunnelPreparationError("campaignId is required before preparation.")
    selected_angle_id = str(funnel.selected_angle_id or "").strip()
    if not selected_angle_id:
        raise SiteFunnelPreparationError("selectedAngleId is required before preparation.")

    template_kind: _TemplateKind = "sales-pdp" if page_intent == "sales" else "pre-sales-listicle"
    current_page_stage = page_intent

    campaign = session.scalars(
        select(Campaign).where(
            Campaign.id == funnel.campaign_id,
            Campaign.client_id == site.client_id,
        )
    ).first()
    if campaign is None:
        raise SiteFunnelPreparationError("Campaign not found for this site funnel.")

    strategy_outputs = load_campaign_creative_context(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product_id=str(funnel.product_id),
        campaign_id=str(funnel.campaign_id),
    )
    product_context = _load_site_funnel_product_context(
        session=session,
        org_id=org_id,
        client_id=client_id,
        site_funnel=funnel,
    )
    strategy_prompt_context, strategy_copy_source = _resolve_strategy_prompt_context_for_site_funnel(
        strategy_outputs=strategy_outputs,
        selected_angle_id=selected_angle_id,
        template_kind=template_kind,
        page_intent=page_intent,
        product_context=product_context,
    )

    sites_repo = SitesRuntimeRepository(session)
    prepared_page = _resolve_or_create_prepared_page(
        session=session,
        sites_repo=sites_repo,
        site=site,
        funnel=funnel,
        page_intent=page_intent,
    )

    current_step, ordered_steps = _ensure_current_step(
        session=session,
        funnel=funnel,
        prepared_page=prepared_page,
    )

    next_page = _resolve_next_page(
        session=session,
        ordered_steps=ordered_steps,
        current_step=current_step,
        current_page_stage=current_page_stage,
    )

    checkout_ready_variants = _load_checkout_ready_variants(session=session, funnel=funnel)
    if current_page_stage == "sales" and not checkout_ready_variants:
        raise SiteFunnelPreparationError(
            "Sales template preparation requires at least one checkout-ready product variant."
        )

    if current_page_stage == "pre_sales" and next_page is None:
        raise SiteFunnelPreparationError(
            "Pre-sales template preparation requires a downstream funnel step targeting the next page."
        )

    html_summary = summarize_html_reference(
        reference_html=template_import.html_snapshot,
        label=template_import.source_label,
    )
    html_reference_prompt_context = build_html_reference_prompt_context(html_summary)
    page_targets = _build_page_targets(
        session=session,
        ordered_steps=ordered_steps,
        current_page_id=str(prepared_page.id),
    )
    imported_runtime_context = build_imported_html_generation_context(
        current_page_stage=current_page_stage,
        current_page_id=str(prepared_page.id),
        next_page_id=str(next_page.id) if next_page else None,
        page_targets=page_targets,
        checkout_ready_variants=checkout_ready_variants,
    )

    rewritten_html, instrumentation_manifest, assistant_message = _prepare_imported_html_document(
        template_import_html=template_import.html_snapshot,
        page_name=prepared_page.name,
        current_page_stage=current_page_stage,
        current_page_id=str(prepared_page.id),
        next_page_id=str(next_page.id) if next_page else None,
        page_targets=page_targets,
        checkout_ready_variants=checkout_ready_variants,
        html_reference_prompt_context=html_reference_prompt_context,
        product_context=product_context,
        strategy_prompt_context=strategy_prompt_context,
    )

    puck_data = _build_imported_html_document_puck_data(
        html_document=rewritten_html,
        page_name=prepared_page.name,
        reference_label=template_import.source_label,
        instrumentation_manifest=instrumentation_manifest,
    )
    funnel_ai._ensure_block_ids(puck_data)

    prepared_page.page_type = page_intent
    prepared_page.page_role = page_intent
    prepared_page.adapted_puck_data = puck_data
    prepared_page.updated_at = datetime.now(timezone.utc)
    sites_repo.update_page(page=prepared_page)

    ai_metadata = {
        "source": "site_funnel_template_import",
        "templateImportId": str(template_import.id),
        "templateImportSha256": template_import.html_sha256,
        "campaignId": str(funnel.campaign_id),
        "selectedAngleId": selected_angle_id,
        "selectedAngleName": strategy_prompt_context.get("selectedAngle", {}).get("angleName"),
        "pageIntent": page_intent,
        "strategyCopySource": strategy_copy_source,
        "assistantMessage": assistant_message,
        "instrumentationManifest": instrumentation_manifest,
    }
    draft_version = sites_repo.create_page_version(
        page_id=str(prepared_page.id),
        puck_data=puck_data,
        provenance={
            "source": "site_funnel_template_import",
            "siteFunnelId": str(funnel.id),
            "templateImportId": str(template_import.id),
            "campaignId": str(funnel.campaign_id),
            "selectedAngleId": selected_angle_id,
        },
        status="draft",
        source_type="site_funnel_template_import",
        source_id=str(template_import.id),
        ai_metadata=ai_metadata,
        diff_summary=assistant_message,
    )
    approved_version = sites_repo.create_page_version(
        page_id=str(prepared_page.id),
        puck_data=puck_data,
        provenance={
            "source": "site_funnel_template_import",
            "siteFunnelId": str(funnel.id),
            "templateImportId": str(template_import.id),
            "campaignId": str(funnel.campaign_id),
            "selectedAngleId": selected_angle_id,
            "approvedByPreparation": True,
        },
        status="approved",
        source_type="site_funnel_template_import",
        source_id=str(template_import.id),
        ai_metadata=ai_metadata,
        diff_summary=assistant_message,
    )

    funnel.prepared_page_id = str(prepared_page.id)
    funnel.latest_prepared_version_id = str(approved_version.id)
    funnel.entry_page_id = str(prepared_page.id)
    funnel.prepared_at = datetime.now(timezone.utc)
    funnel.preparation_readiness = _build_preparation_readiness(
        funnel=funnel,
        prepared_page=prepared_page,
        approved_version_id=str(approved_version.id),
        template_import=template_import,
        current_page_stage=current_page_stage,
        next_page=next_page,
        checkout_ready_variants=checkout_ready_variants,
        strategy_copy_source=strategy_copy_source,
        selected_angle_name=clean_optional_text(
            cast(dict[str, Any], strategy_prompt_context.get("selectedAngle") or {}).get("angleName")
        ),
        tracking=_resolve_public_meta_tracking(org_id=org_id, client_id=client_id, session=session),
    )
    funnel.updated_at = datetime.now(timezone.utc)
    session.add(funnel)
    session.flush()
    session.refresh(funnel)
    return funnel


def _require_page_intent(raw: str | None) -> _PageIntent:
    normalized = str(raw or "").strip()
    if normalized not in {"sales", "pre_sales"}:
        raise SiteFunnelPreparationError("pageIntent must be set to 'sales' or 'pre_sales' before preparation.")
    return cast(_PageIntent, normalized)


def _resolve_strategy_prompt_context_for_site_funnel(
    *,
    strategy_outputs: dict[str, Any],
    selected_angle_id: str,
    template_kind: _TemplateKind,
    page_intent: _PageIntent,
    product_context: str,
) -> tuple[dict[str, Any], _GeneratedCopySource]:
    selected_angle = _require_selected_angle_entry(
        strategy_outputs=strategy_outputs,
        selected_angle_id=selected_angle_id,
    )
    materialized_selected_angle_id = _materialized_selected_angle_id(strategy_outputs=strategy_outputs)
    if materialized_selected_angle_id == selected_angle_id:
        return (
            _build_strategy_prompt_context(
                outputs=strategy_outputs,
                template_kind=template_kind,
            ),
            "campaign_materialized",
        )

    generated_copy = _generate_selected_angle_copy_packet(
        strategy_outputs=strategy_outputs,
        selected_angle=selected_angle,
        template_kind=template_kind,
        page_intent=page_intent,
        product_context=product_context,
    )
    return (
        _build_strategy_prompt_context_from_generated_copy(
            strategy_outputs=strategy_outputs,
            selected_angle=selected_angle,
            generated_copy=generated_copy,
            template_kind=template_kind,
        ),
        "generated_for_selected_angle",
    )


def _require_selected_angle_entry(*, strategy_outputs: dict[str, Any], selected_angle_id: str) -> dict[str, Any]:
    angles = strategy_outputs.get("angles")
    if not isinstance(angles, dict):
        raise SiteFunnelPreparationError(
            "Campaign creative context is missing the angles document required for template preparation."
        )
    angle_library = angles.get("angleLibrary")
    if not isinstance(angle_library, list):
        raise SiteFunnelPreparationError(
            "Campaign creative context is missing angleLibrary required for template preparation."
        )
    matching_angle = next(
        (
            entry
            for entry in angle_library
            if isinstance(entry, dict) and str(entry.get("angleId") or "").strip() == selected_angle_id
        ),
        None,
    )
    if matching_angle is None:
        raise SiteFunnelPreparationError(
            f"selectedAngleId '{selected_angle_id}' does not exist in this campaign's creative-context angle library."
        )
    return matching_angle


def _materialized_selected_angle_id(*, strategy_outputs: dict[str, Any]) -> str:
    angles = strategy_outputs.get("angles")
    if not isinstance(angles, dict):
        return ""
    return str(angles.get("selectedAngleId") or "").strip()


def _selected_angle_copy_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "promiseContract": {
                "type": "object",
                "properties": {
                    "loopQuestion": {"type": "string"},
                    "specificPromise": {"type": "string"},
                    "deliveryTest": {"type": "string"},
                    "minimumDelivery": {"type": "string"},
                },
                "required": ["loopQuestion", "specificPromise", "deliveryTest", "minimumDelivery"],
                "additionalProperties": False,
            },
            "pageMarkdown": {"type": "string"},
        },
        "required": ["headline", "promiseContract", "pageMarkdown"],
        "additionalProperties": False,
    }


def _selected_angle_copy_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "site_funnel_selected_angle_copy",
            "schema": _selected_angle_copy_output_schema(),
            "strict": True,
        },
    }


def _coerce_generated_copy_packet(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SiteFunnelPreparationError("Generated selected-angle copy response was not a JSON object.")
    headline = clean_optional_text(raw.get("headline"))
    if not headline:
        raise SiteFunnelPreparationError("Generated selected-angle copy is missing headline.")
    promise_contract = raw.get("promiseContract")
    if not isinstance(promise_contract, dict):
        raise SiteFunnelPreparationError("Generated selected-angle copy is missing promiseContract.")
    normalized_promise_contract = {
        "loopQuestion": clean_optional_text(promise_contract.get("loopQuestion")),
        "specificPromise": clean_optional_text(promise_contract.get("specificPromise")),
        "deliveryTest": clean_optional_text(promise_contract.get("deliveryTest")),
        "minimumDelivery": clean_optional_text(promise_contract.get("minimumDelivery")),
    }
    if not all(normalized_promise_contract.values()):
        raise SiteFunnelPreparationError("Generated selected-angle promiseContract is missing required fields.")
    page_markdown = clean_optional_text(raw.get("pageMarkdown"))
    if not page_markdown:
        raise SiteFunnelPreparationError("Generated selected-angle copy is missing pageMarkdown.")
    return {
        "headline": headline,
        "promiseContract": normalized_promise_contract,
        "pageMarkdown": page_markdown,
    }


def _generate_selected_angle_copy_packet(
    *,
    strategy_outputs: dict[str, Any],
    selected_angle: dict[str, Any],
    template_kind: _TemplateKind,
    page_intent: _PageIntent,
    product_context: str,
) -> dict[str, Any]:
    offer = strategy_outputs.get("offer")
    copy = strategy_outputs.get("copy")
    copy_context = strategy_outputs.get("copy_context")
    if not isinstance(offer, dict) or not isinstance(copy_context, dict):
        raise SiteFunnelPreparationError(
            "Campaign creative context is missing offer or copy context required for selected-angle copy generation."
        )

    reference_copy = copy if isinstance(copy, dict) else {}
    page_intent_guidance = (
        "Page intent: pre-sales.\n"
        "- Make the copy engaging, curiosity-driven, and educational.\n"
        "- Reduce hard-close sales language, purchase urgency, and checkout framing.\n"
        "- Prefer softer CTA language that moves the reader forward without sounding transactional.\n"
    ) if page_intent == "pre_sales" else (
        "Page intent: sales.\n"
        "- Make the copy direct, conversion-oriented, and offer-aware.\n"
        "- It is acceptable to use stronger CTA language and checkout-oriented framing.\n"
        "- Keep the promise specific and commercially useful without adding unsupported claims.\n"
    )

    selected_angle_payload = {
        "angleId": selected_angle.get("angleId"),
        "angleName": selected_angle.get("angleName"),
        "description": selected_angle.get("description"),
        "evidence": selected_angle.get("evidence") if isinstance(selected_angle.get("evidence"), list) else [],
    }
    materialized_reference_payload = {
        "headline": reference_copy.get("headline"),
        "promiseContract": reference_copy.get("promiseContract"),
        "pageMarkdown": reference_copy.get("salesPageMarkdown" if template_kind == "sales-pdp" else "presellMarkdown"),
    }

    system_content = (
        "You are generating page-intent-aware funnel copy for an imported HTML template.\n\n"
        "You MUST output valid JSON only (no markdown fences, no commentary).\n"
        'Return exactly one JSON object with this shape: { "headline": string, "promiseContract": { "loopQuestion": string, "specificPromise": string, "deliveryTest": string, "minimumDelivery": string }, "pageMarkdown": string }\n\n'
        "Rules:\n"
        "- The selected angle below is the primary source of truth for the copy you generate.\n"
        "- The campaign's currently materialized copy may be for a different angle. Use it only as a tone and compliance reference.\n"
        "- Do not invent unsupported medical claims, unrealistic timelines, or guarantees.\n"
        f"- Generate copy for a {'sales page' if page_intent == 'sales' else 'pre-sales page'}.\n"
        f"{page_intent_guidance}\n"
        "Use these inputs:\n"
        f"Selected angle:\n{json.dumps(selected_angle_payload, ensure_ascii=False)}\n\n"
        f"Offer context:\n{json.dumps(offer, ensure_ascii=False)}\n\n"
        f"Copy context:\n{json.dumps(copy_context, ensure_ascii=False)}\n\n"
        f"Materialized campaign copy reference:\n{json.dumps(materialized_reference_payload, ensure_ascii=False)}\n\n"
        f"{product_context}"
    )
    compiled_prompt = "\n\n".join(
        [
            system_content,
            "USER: Generate the selected-angle copy packet now.",
            "Return JSON now.",
        ]
    )

    llm = LLMClient()
    model_id = llm.default_model
    max_tokens = funnel_ai._coerce_max_tokens(model_id, 4_000)
    is_claude_model = model_id.lower().startswith("claude")

    if is_claude_model:
        response = call_claude_structured_message(
            model=model_id,
            system=None,
            user_content=[{"type": "text", "text": compiled_prompt}],
            output_schema=_selected_angle_copy_output_schema(),
            max_tokens=min(max_tokens, funnel_ai._CLAUDE_MAX_OUTPUT_TOKENS),
            temperature=0.2,
        )
        parsed = response.get("parsed") if isinstance(response, dict) else None
        return _coerce_generated_copy_packet(parsed)

    out = llm.generate_text(
        compiled_prompt,
        params=LLMGenerationParams(
            model=model_id,
            max_tokens=max_tokens,
            temperature=0.2,
            use_reasoning=True,
            use_web_search=False,
            response_format=_selected_angle_copy_response_format(),
        ),
    )
    return _coerce_generated_copy_packet(funnel_ai._extract_json_object(out))


def _build_strategy_prompt_context_from_generated_copy(
    *,
    strategy_outputs: dict[str, Any],
    selected_angle: dict[str, Any],
    generated_copy: dict[str, Any],
    template_kind: _TemplateKind,
) -> dict[str, Any]:
    offer = strategy_outputs.get("offer")
    copy_context = strategy_outputs.get("copy_context")
    artifact_ids = strategy_outputs.get("artifact_ids")
    if not isinstance(offer, dict) or not isinstance(copy_context, dict):
        raise SiteFunnelPreparationError(
            "Campaign creative context is missing offer or copy context required for selected-angle template preparation."
        )

    evidence_points = [
        str(point).strip()
        for point in (selected_angle.get("evidence") if isinstance(selected_angle.get("evidence"), list) else [])
        if str(point).strip()
    ]
    return {
        "source": "campaign_creative_context.generated_selected_angle",
        "templateKind": template_kind,
        "artifactIds": artifact_ids if isinstance(artifact_ids, dict) else {},
        "selectedAngle": {
            "angleId": selected_angle.get("angleId"),
            "angleName": selected_angle.get("angleName"),
            "supportingVocCount": None,
            "topQuotes": [],
            "supportingPoints": evidence_points[:5],
        },
        "offer": {
            "headline": generated_copy.get("headline"),
            "ump": offer.get("ump"),
            "ums": offer.get("ums"),
            "corePromise": offer.get("corePromise"),
            "valueStackSummary": offer.get("valueStackSummary"),
            "guaranteeType": offer.get("guaranteeType"),
            "pricingRationale": offer.get("pricingRationale"),
            "selectedVariant": {
                "id": offer.get("selectedVariantId"),
                "name": offer.get("selectedVariantName"),
            },
            "productOffer": None,
        },
        "copy": {
            "headline": generated_copy.get("headline"),
            "promiseContract": generated_copy.get("promiseContract"),
            "pageMarkdown": _truncate_prompt_text(
                str(generated_copy.get("pageMarkdown") or ""),
                limit=16_000,
            ),
            "templatePatchOperationCount": 0,
            "qualityGateReport": None,
            "semanticGates": None,
            "congruency": None,
        },
        "copyContext": _compact_prompt_payload(copy_context, max_chars=6_000),
    }


def _load_site_funnel_product_context(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    site_funnel: SiteFunnel,
) -> str:
    _, _, product_context = funnel_ai._load_product_context(
        session=session,
        org_id=org_id,
        client_id=client_id,
        funnel=site_funnel,
    )
    return product_context


def _resolve_or_create_prepared_page(
    *,
    session: Session,
    sites_repo: SitesRuntimeRepository,
    site: Site,
    funnel: SiteFunnel,
    page_intent: _PageIntent,
) -> SitePage:
    existing_page_id = str(funnel.prepared_page_id or funnel.entry_page_id or "").strip()
    if existing_page_id:
        existing_page = sites_repo.get_page(site_id=str(site.id), page_id=existing_page_id)
        if existing_page is not None:
            return existing_page

    base_slug = slugify(funnel.name) or "funnel"
    suffix = "sales-page" if page_intent == "sales" else "pre-sales-page"
    desired_slug = f"{base_slug}-{suffix}"
    unique_slug = desired_slug
    counter = 2
    while not sites_repo.check_slug_unique(site_id=str(site.id), slug=unique_slug):
        unique_slug = f"{desired_slug}-{counter}"
        counter += 1

    page_name = f"{funnel.name} {'Sales Page' if page_intent == 'sales' else 'Pre-sales Page'}".strip()
    return sites_repo.create_page(
        site_id=str(site.id),
        name=page_name,
        slug=unique_slug,
        page_type=page_intent,
        page_role=page_intent,
        status="draft",
        adapted_puck_data={},
    )


def _ensure_current_step(
    *,
    session: Session,
    funnel: SiteFunnel,
    prepared_page: SitePage,
) -> tuple[SiteFunnelStep, list[SiteFunnelStep]]:
    steps = list(
        session.scalars(
            select(SiteFunnelStep)
            .where(SiteFunnelStep.site_funnel_id == funnel.id)
            .order_by(SiteFunnelStep.ordering.asc(), SiteFunnelStep.created_at.asc())
        ).all()
    )

    current_step = next(
        (step for step in steps if str(step.site_page_id) == str(prepared_page.id)),
        None,
    )
    if current_step is not None:
        return current_step, steps

    for step in sorted(steps, key=lambda item: item.ordering, reverse=True):
        step.ordering += 1
        session.add(step)

    current_step = SiteFunnelStep(
        site_funnel_id=str(funnel.id),
        site_page_id=str(prepared_page.id),
        ordering=0,
        step_role=funnel.page_intent,
        cta_label=None,
        created_at=datetime.now(timezone.utc),
    )
    session.add(current_step)
    session.flush()

    refreshed_steps = list(
        session.scalars(
            select(SiteFunnelStep)
            .where(SiteFunnelStep.site_funnel_id == funnel.id)
            .order_by(SiteFunnelStep.ordering.asc(), SiteFunnelStep.created_at.asc())
        ).all()
    )
    return current_step, refreshed_steps


def _resolve_next_page(
    *,
    session: Session,
    ordered_steps: list[SiteFunnelStep],
    current_step: SiteFunnelStep,
    current_page_stage: _PageIntent,
) -> SitePage | None:
    if current_page_stage != "pre_sales":
        return None

    for step in ordered_steps:
        if step.ordering <= current_step.ordering:
            continue
        candidate = session.scalars(select(SitePage).where(SitePage.id == step.site_page_id)).first()
        if candidate is not None:
            return candidate
    return None


def _load_checkout_ready_variants(*, session: Session, funnel: SiteFunnel) -> list[ProductVariant]:
    if not funnel.product_id:
        return []
    stmt = select(ProductVariant).where(ProductVariant.product_id == funnel.product_id)
    if funnel.selected_offer_id:
        stmt = stmt.where(ProductVariant.offer_id == funnel.selected_offer_id)
    variants = list(session.scalars(stmt).all())
    return [
        variant
        for variant in variants
        if str(variant.provider or "").strip().lower() and str(variant.external_price_id or "").strip()
    ]


def _build_page_targets(
    *,
    session: Session,
    ordered_steps: list[SiteFunnelStep],
    current_page_id: str,
) -> list[dict[str, Any]]:
    page_targets: list[dict[str, Any]] = []
    for step in ordered_steps:
        if str(step.site_page_id) == current_page_id:
            continue
        page = session.scalars(select(SitePage).where(SitePage.id == step.site_page_id)).first()
        if page is None:
            continue
        page_targets.append(
            {
                "id": str(page.id),
                "name": page.name,
                "slug": page.slug,
                "stage": page.page_role or page.page_type or "custom",
            }
        )
    return page_targets


def _prepare_imported_html_document(
    *,
    template_import_html: str,
    page_name: str,
    current_page_stage: _PageIntent,
    current_page_id: str,
    next_page_id: str | None,
    page_targets: list[dict[str, Any]],
    checkout_ready_variants: list[ProductVariant],
    html_reference_prompt_context: dict[str, Any],
    product_context: str,
    strategy_prompt_context: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    editable_text_nodes = extract_editable_html_text_nodes(html_document=template_import_html)
    if not editable_text_nodes:
        raise SiteFunnelPreparationError(
            "Imported HTML did not contain any editable visible text nodes."
        )

    editable_text_nodes_context = [
        {
            "nodeId": node.nodeId,
            "path": node.path,
            "originalText": node.originalText,
            "charCount": node.charCount,
        }
        for node in editable_text_nodes
    ]

    imported_runtime_context = build_imported_html_generation_context(
        current_page_stage=current_page_stage,
        current_page_id=current_page_id,
        next_page_id=next_page_id,
        page_targets=page_targets,
        checkout_ready_variants=checkout_ready_variants,
    )

    strategy_prompt_guidance = (
        "Latest strategy copy guidance:\n"
        "- Treat the structured strategy context below as the required source of truth for promise, offer framing, angle, and CTA language.\n"
        f"- Use the included {'sales page markdown' if current_page_stage == 'sales' else 'pre-sales markdown'} as the canonical copy blueprint for this page.\n"
        "- Preserve the promise contract and compliance boundaries. Do not invent claims or drift away from the selected angle.\n"
        f"{json.dumps(strategy_prompt_context, ensure_ascii=False)}\n\n"
    )

    system_content = (
        "You are updating an uploaded HTML template for a site funnel page.\n\n"
        "You MUST output valid JSON only (no markdown, no code fences, no commentary).\n"
        "Return exactly ONE JSON object with this shape:\n"
        '{ "assistantMessage": string, "textReplacements": [{ "nodeId": string, "text": string }], "instrumentationManifest": object }\n\n'
        "assistantMessage requirements:\n"
        "- Plain text only.\n"
        f"- Keep it under {funnel_ai._ASSISTANT_MESSAGE_MAX_CHARS} characters.\n"
        "- Summarize the rewritten page briefly and include a medical safety disclaimer.\n\n"
        "textReplacements requirements:\n"
        "- Return an array of objects with nodeId and text.\n"
        "- Use ONLY nodeIds from the editable text node list below.\n"
        "- Omit nodes that should remain unchanged.\n"
        "- Only replace human-facing copy text inside those existing text nodes.\n"
        "- Keep replacement text roughly similar in length so the layout stays visually identical.\n"
        "- Do NOT return HTML, CSS, JavaScript, markdown, selectors, or attribute edits inside text.\n"
        "- Do NOT attempt to change colors, layout, classes, ids, hrefs, src values, or any non-text attribute.\n"
        "- The server will apply your text replacements to the original HTML exactly.\n\n"
        "instrumentationManifest requirements:\n"
        f"- schemaVersion MUST be '{imported_runtime_context['schemaVersion']}'.\n"
        f"- pageStage MUST be '{current_page_stage}'.\n"
        "- Use the exact manifest JSON schema below.\n"
        f"- {imported_html_selector_hint()}\n"
        "- Every binding selector MUST match at least one existing element in the uploaded HTML.\n"
        "- If multiple visually identical CTA elements should share behavior, you may use one selector that intentionally matches all of them.\n"
        "- Option selectors inside checkout.variantResolver.type='option_values' MUST still match exactly one existing element each.\n"
        "- Do NOT invent ids, classes, attributes, hrefs, src values, or target page ids.\n"
        "- For pre-sales pages, bind the primary CTA to the configured next page with an internal_navigation binding.\n"
        "- For sales pages, bind the primary buy CTA with a checkout binding.\n"
        "- Prefer checkout.mode='public_checkout'. Use checkout.mode='external_checkout_url' only when an explicit per-variant external URL map is required.\n"
        "- If the page has variant/pack selectors, use an option_values resolver with selectors that read the live chosen values from the existing HTML controls.\n"
        "- If exactly one checkout-ready variant exists and there is no visible variant choice, use a fixed resolver with that variantId.\n\n"
        "Copy goals:\n"
        "- Keep the uploaded HTML visually identical.\n"
        "- Inject accurate product, offer, and strategy copy for this funnel.\n"
        "- Be specific and persuasive without making unsupported medical claims.\n\n"
        f"{strategy_prompt_guidance}"
        f"{product_context}"
        "Imported HTML runtime context:\n"
        f"{json.dumps(imported_runtime_context, ensure_ascii=False)}\n\n"
        "Editable text nodes that may be rewritten:\n"
        f"{json.dumps(editable_text_nodes_context, ensure_ascii=False)}\n\n"
        "instrumentationManifest JSON schema:\n"
        f"{json.dumps(imported_html_instrumentation_schema(), ensure_ascii=False)}\n\n"
        "HTML summary for orientation only:\n"
        f"{json.dumps(html_reference_prompt_context or {}, ensure_ascii=False)}\n\n"
        "Uploaded HTML document to preserve exactly while patching copy into the listed text nodes:\n"
        f"{template_import_html}"
    )

    compiled_prompt = "\n\n".join(
        [
            system_content,
            "USER: Rewrite the uploaded HTML with the correct funnel copy and bindings.",
            "Return JSON now.",
        ]
    )

    llm = LLMClient()
    model_id = llm.default_model
    max_tokens = funnel_ai._coerce_max_tokens(model_id, None)
    is_claude_model = model_id.lower().startswith("claude")

    if is_claude_model:
        response = call_claude_structured_message(
            model=model_id,
            system=None,
            user_content=[{"type": "text", "text": compiled_prompt}],
            output_schema=funnel_ai._html_rewrite_output_schema(),
            max_tokens=min(max_tokens, funnel_ai._CLAUDE_MAX_OUTPUT_TOKENS),
            temperature=0.2,
        )
        parsed = response.get("parsed") if isinstance(response, dict) else None
        if not isinstance(parsed, dict):
            raise SiteFunnelPreparationError("Claude structured response returned no parsed JSON.")
        obj = parsed
    else:
        out = llm.generate_text(
            compiled_prompt,
            params=LLMGenerationParams(
                model=model_id,
                max_tokens=max_tokens,
                temperature=0.2,
                use_reasoning=True,
                use_web_search=False,
                response_format=funnel_ai._html_rewrite_response_format(),
            ),
        )
        obj = funnel_ai._extract_json_object(out)

    assistant_message = funnel_ai._coerce_assistant_message(obj.get("assistantMessage"))
    text_replacements = _coerce_text_replacements(obj.get("textReplacements"))
    instrumentation_manifest = coerce_imported_html_instrumentation_manifest(obj.get("instrumentationManifest"))

    try:
        rewritten_html = apply_html_text_replacements(
            original_html=template_import_html,
            replacements=text_replacements,
        )
    except HtmlReferenceError as exc:
        raise SiteFunnelPreparationError(str(exc)) from exc

    try:
        assert_html_text_only_rewrite(
            original_html=template_import_html,
            rewritten_html=rewritten_html,
        )
    except HtmlStructureMismatchError as exc:
        raise SiteFunnelPreparationError(str(exc)) from exc

    try:
        instrumentation_manifest = validate_imported_html_document_manifest(
            html_document=rewritten_html,
            instrumentation_manifest=instrumentation_manifest,
            current_page_stage=current_page_stage,
            current_page_id=current_page_id,
            next_page_id=next_page_id,
            available_target_page_ids={str(target["id"]) for target in page_targets if target.get("id")},
            checkout_ready_variants=checkout_ready_variants,
            require_stage_bindings=current_page_stage in {"pre_sales", "sales"},
        )
    except ImportedHtmlRuntimeValidationError as exc:
        raise SiteFunnelPreparationError(str(exc)) from exc

    return rewritten_html, instrumentation_manifest, assistant_message


def _build_preparation_readiness(
    *,
    funnel: SiteFunnel,
    prepared_page: SitePage,
    approved_version_id: str,
    template_import,
    current_page_stage: _PageIntent,
    next_page: SitePage | None,
    checkout_ready_variants: list[ProductVariant],
    strategy_copy_source: _GeneratedCopySource,
    selected_angle_name: str | None,
    tracking: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "status": "prepared",
        "pageIntent": current_page_stage,
        "preparedPageId": str(prepared_page.id),
        "preparedPageSlug": prepared_page.slug,
        "latestPreparedVersionId": approved_version_id,
        "templateImportId": str(template_import.id),
        "templateImportSha256": template_import.html_sha256,
        "campaignId": str(funnel.campaign_id) if funnel.campaign_id else None,
        "selectedAngleId": str(funnel.selected_angle_id) if funnel.selected_angle_id else None,
        "selectedAngleName": selected_angle_name,
        "copy": {
            "required": True,
            "ready": True,
            "source": strategy_copy_source,
        },
        "navigation": {
            "required": current_page_stage == "pre_sales",
            "ready": current_page_stage != "pre_sales" or next_page is not None,
            "nextPageId": str(next_page.id) if next_page else None,
            "nextPageSlug": next_page.slug if next_page else None,
        },
        "checkout": {
            "required": current_page_stage == "sales",
            "ready": current_page_stage != "sales" or len(checkout_ready_variants) > 0,
            "variantCount": len(checkout_ready_variants),
            "variantIds": [str(variant.id) for variant in checkout_ready_variants],
        },
        "tracking": {
            "required": True,
            "ready": tracking is not None,
            "config": tracking,
        },
    }


def _resolve_public_meta_tracking(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> dict[str, str] | None:
    profile = PaidAdsQaRepository(session).get_platform_profile(
        org_id=org_id,
        client_id=client_id,
        platform="meta",
    )
    if profile is None:
        return None
    metadata_json = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    mos_tracking = metadata_json.get("mosMetaTracking")
    if not isinstance(mos_tracking, dict):
        return None
    if normalize_tracking_provider(mos_tracking.get("status")) != "active":
        return None
    if normalize_tracking_provider(mos_tracking.get("mode")) != "public_funnel_runtime":
        return None
    if normalize_tracking_provider(mos_tracking.get("channel")) != "meta":
        return None
    pixel_id = clean_optional_text(mos_tracking.get("pixelId")) or clean_optional_text(profile.pixel_id)
    if not pixel_id:
        return None
    return {
        "provider": "meta",
        "mode": "public_funnel_runtime",
        "metaPixelId": pixel_id,
    }
