from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException
from temporalio import activity
from sqlalchemy import select

from app.services import funnel_ai
from app.db.base import session_scope
from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum, FunnelStatusEnum
from app.db.models import Campaign, Funnel, FunnelPage, FunnelPageVersion, Product, ProductOffer, ProductVariant
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.client_compliance_profiles import ClientComplianceProfilesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.funnels import FunnelsRepository, FunnelPagesRepository
from app.services.funnels import generate_unique_slug
from app.services.funnel_templates import get_funnel_template, apply_template_assets
from app.agent.funnel_objectives import run_generate_page_draft
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum
from app.db.repositories.design_systems import DesignSystemsRepository
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnel_metadata import normalize_public_page_metadata_for_context
from app.services.product_types import canonical_product_type, is_book_product_type, product_type_matches
from app.services.shopify_connection import get_client_shopify_connection_status, get_client_shopify_product
from app.strategy_v2.downstream import load_strategy_v2_outputs
from app.strategy_v2.template_bridge import (
    apply_strategy_v2_template_patch,
)


_DEFAULT_AI_DRAFT_EMPTY_PAGE_MAX_ATTEMPTS = 3
_EMPTY_PAGE_ERROR_MARKERS = (
    "ai generation produced an empty page",
    "empty page (no content)",
)
_FOOTER_PAYMENT_ICON_KEYS: list[str] = [
    "american_express",
    "apple_pay",
    "google_pay",
    "maestro",
    "mastercard",
    "paypal",
    "visa",
]
_BOOK_HELPER_TEXT_DISALLOWED_PHRASES: tuple[str, ...] = (
    "instant digital access",
    "digital access",
    "searchable pdf",
    "single device",
    "download",
    "pdf",
)
_BOOK_HELPER_TEXT_CORE_BOOK_SIGNALS: tuple[str, ...] = (
    "book",
    "books",
    "field guide",
    "guide",
    "guidebook",
    "handbook",
    "manual",
)
_BOOK_HELPER_TEXT_DIGITAL_BOOK_PHRASES: tuple[str, ...] = (
    "digital book",
    "digital books",
    "digital field guide",
    "digital guide",
    "digital guidebook",
    "digital handbook",
    "digital manual",
    "downloadable book",
    "downloadable field guide",
    "downloadable guide",
    "downloadable handbook",
    "downloadable manual",
    "ebook",
    "e-book",
    "pdf book",
    "pdf field guide",
    "pdf guide",
    "pdf handbook",
    "pdf manual",
)
_BOOK_CTA_DISALLOWED_PHRASES: tuple[str, ...] = (
    "get instant access",
    "instant access",
    "download now",
    "instant digital access",
)
_BOOK_HELPER_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_BOOK_HELPER_CLAUSE_SPLIT_RE = re.compile(r"\s*[,;]\s*")
_BOOK_TEXT_WHITESPACE_RE = re.compile(r"\s+")
_BOOK_CTA_LABELS: tuple[tuple[str, str], ...] = (
    ("field guide", "Field Guide"),
    ("handbook", "Handbook"),
    ("guide", "Guide"),
    ("manual", "Manual"),
    ("book", "Book"),
)
_FUNNEL_DRAFT_HEARTBEAT_INTERVAL_SECONDS = 20.0


def _activity_heartbeat_safe(payload: dict[str, Any]) -> None:
    try:
        activity.heartbeat(payload)
    except RuntimeError:
        # Unit tests execute these helpers outside a Temporal activity context.
        return


@contextmanager
def _activity_heartbeat_loop(
    *,
    payload_factory: Callable[[], dict[str, Any]],
    interval_seconds: float | None = None,
):
    interval = (
        float(interval_seconds)
        if interval_seconds is not None
        else float(_FUNNEL_DRAFT_HEARTBEAT_INTERVAL_SECONDS)
    )
    _activity_heartbeat_safe(payload_factory())
    stop_event = threading.Event()

    def _run() -> None:
        while not stop_event.wait(interval):
            _activity_heartbeat_safe(payload_factory())

    thread = threading.Thread(
        target=_run,
        name="campaign-intent-heartbeat",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=max(1.0, interval))


def _collect_image_generation_errors(
    *,
    generated_images: Any,
    funnel_id: str,
    page_id: str,
    page_name: str,
    template_id: str | None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(generated_images, list):
        return errors
    for item in generated_images:
        if not isinstance(item, dict):
            continue
        message = item.get("error")
        if not isinstance(message, str) or not message.strip():
            continue
        error_entry: dict[str, Any] = {
            "type": "image_generation",
            "severity": "warning",
            "funnel_id": funnel_id,
            "page_id": page_id,
            "page_name": page_name,
            "message": message.strip(),
        }
        if template_id:
            error_entry["template_id"] = template_id
        errors.append(error_entry)
    return errors


def _find_disallowed_phrase(text: str | None, disallowed_phrases: tuple[str, ...]) -> str | None:
    if not isinstance(text, str):
        return None
    normalized = text.strip().lower()
    if not normalized:
        return None
    for phrase in disallowed_phrases:
        if phrase in normalized:
            return phrase
    return None


def _normalize_book_text_whitespace(text: str) -> str:
    return _BOOK_TEXT_WHITESPACE_RE.sub(" ", text).strip()


def _book_offer_helper_mentions_core_book(text: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in _BOOK_HELPER_TEXT_DIGITAL_BOOK_PHRASES):
        return False
    return any(signal in lowered for signal in _BOOK_HELPER_TEXT_CORE_BOOK_SIGNALS)


def _normalize_book_offer_helper_text(text: str) -> str:
    cleaned = _normalize_book_text_whitespace(text)
    if not cleaned:
        return ""
    if _find_disallowed_phrase(cleaned, _BOOK_HELPER_TEXT_DISALLOWED_PHRASES) is None:
        return cleaned
    if _book_offer_helper_mentions_core_book(cleaned):
        return cleaned

    sentences = [part.strip() for part in _BOOK_HELPER_SENTENCE_SPLIT_RE.split(cleaned) if part.strip()]
    if not sentences:
        sentences = [cleaned]

    normalized_sentences: list[str] = []
    for sentence in sentences:
        ending = sentence[-1] if sentence[-1] in ".!?" else ""
        sentence_core = sentence[:-1] if ending else sentence
        clauses = [
            clause.strip(" ,;")
            for clause in _BOOK_HELPER_CLAUSE_SPLIT_RE.split(sentence_core)
            if clause.strip(" ,;")
        ]
        filtered_clauses = [
            clause
            for clause in clauses
            if _find_disallowed_phrase(clause, _BOOK_HELPER_TEXT_DISALLOWED_PHRASES) is None
        ]
        if not filtered_clauses:
            continue
        rebuilt = _normalize_book_text_whitespace(", ".join(filtered_clauses))
        if rebuilt and rebuilt[0].islower():
            rebuilt = rebuilt[0].upper() + rebuilt[1:]
        if ending and rebuilt[-1] not in ".!?":
            rebuilt = f"{rebuilt}{ending}"
        normalized_sentences.append(rebuilt)

    normalized = " ".join(normalized_sentences).strip()
    if normalized:
        return normalized
    raise ValueError(
        "Sales template payload uses only digital-only delivery language for a book product. "
        "field=whats_inside.offer_helper_text. Remediation: describe the physical book offer."
    )


def _normalize_book_cta_label(text: str) -> str:
    cleaned = _normalize_book_text_whitespace(text)
    if not cleaned:
        return ""
    if _find_disallowed_phrase(cleaned, _BOOK_CTA_DISALLOWED_PHRASES) is None:
        return cleaned
    noun_label = "Book"
    lowered = cleaned.lower()
    for needle, label in _BOOK_CTA_LABELS:
        if needle in lowered:
            noun_label = label
            break
    price_suffix = " - {price}" if "{price}" in cleaned else ""
    return f"Get the {noun_label}{price_suffix}"


def _normalize_sales_payload_for_product_type(
    *,
    template_id: str,
    payload_fields: dict[str, Any],
    product_type: str | None,
) -> dict[str, Any]:
    if template_id != "sales-pdp" or not is_book_product_type(product_type):
        return payload_fields

    hero = payload_fields.get("hero")
    if isinstance(hero, dict):
        cta_label = str(hero.get("primary_cta_label") or "").strip()
        if cta_label:
            hero["primary_cta_label"] = _normalize_book_cta_label(cta_label)

    whats_inside = payload_fields.get("whats_inside")
    if isinstance(whats_inside, dict):
        helper_text = str(whats_inside.get("offer_helper_text") or "").strip()
        if helper_text:
            whats_inside["offer_helper_text"] = _normalize_book_offer_helper_text(helper_text)

    return payload_fields


def _assert_strategy_v2_offer_product_type_matches_product(
    *,
    product_type: str | None,
    strategy_v2_packet: dict[str, Any],
) -> None:
    offer_payload = strategy_v2_packet.get("offer")
    if not isinstance(offer_payload, dict):
        return
    selected_variant = offer_payload.get("selected_variant")
    if not isinstance(selected_variant, dict):
        return
    variant_product_type = canonical_product_type(str(selected_variant.get("product_type") or ""))
    expected_product_type = canonical_product_type(product_type)
    if expected_product_type and variant_product_type and expected_product_type != variant_product_type:
        raise ValueError(
            "Strategy V2 selected offer product_type does not match the persisted product record. "
            f"product={expected_product_type} strategy_v2_offer={variant_product_type}. "
            "Remediation: regenerate the offer after correcting the product type."
        )


def _assert_sales_payload_matches_product_type(
    *,
    template_id: str,
    payload_fields: dict[str, Any],
    product_type: str | None,
) -> None:
    if template_id != "sales-pdp" or not is_book_product_type(product_type):
        return

    whats_inside = payload_fields.get("whats_inside")
    hero = payload_fields.get("hero")
    helper_text = str(whats_inside.get("offer_helper_text") or "").strip() if isinstance(whats_inside, dict) else ""
    cta_label = str(hero.get("primary_cta_label") or "").strip() if isinstance(hero, dict) else ""

    helper_phrase = _find_disallowed_phrase(helper_text, _BOOK_HELPER_TEXT_DISALLOWED_PHRASES)
    if helper_phrase and not _book_offer_helper_mentions_core_book(helper_text):
        raise ValueError(
            "Sales template payload uses digital-only delivery language for a book product. "
            f"field=whats_inside.offer_helper_text phrase={helper_phrase!r}. "
            "Remediation: describe the physical book offer, not digital delivery."
        )

    cta_phrase = _find_disallowed_phrase(cta_label, _BOOK_CTA_DISALLOWED_PHRASES)
    if cta_phrase:
        raise ValueError(
            "Sales template CTA uses digital-only language for a book product. "
            f"field=hero.primary_cta_label phrase={cta_phrase!r}. "
            "Remediation: use purchase language that matches a physical book offer."
        )


def _align_sales_pdp_purchase_options_for_selected_offer(
    *,
    session,
    org_id: str,
    product_id: str,
    selected_offer_id: str | None,
    puck_data: dict[str, Any],
) -> bool:
    if not isinstance(puck_data, dict):
        raise ValueError("puck_data must be a JSON object for sales offer alignment.")

    selected_offer = None
    selected_offer_options_schema: dict[str, Any] | None = None
    if isinstance(selected_offer_id, str) and selected_offer_id.strip():
        selected_offer = session.scalars(
            select(ProductOffer).where(
                ProductOffer.org_id == org_id,
                ProductOffer.id == selected_offer_id.strip(),
                ProductOffer.product_id == product_id,
            )
        ).first()
        if selected_offer is None:
            raise ValueError(
                "Cannot align sales offer options because the selected product offer was not found."
            )
        if isinstance(selected_offer.options_schema, dict):
            selected_offer_options_schema = selected_offer.options_schema

    variants_stmt = select(ProductVariant).where(ProductVariant.product_id == product_id)
    if selected_offer is not None:
        variants_stmt = variants_stmt.where(ProductVariant.offer_id == selected_offer.id)
    variants = list(session.scalars(variants_stmt).all())
    if not variants:
        raise ValueError(
            "Cannot align sales offer options because no price point variants were found for the selected product offer."
        )

    variant_inputs = [
        {
            "id": str(variant.id),
            "title": variant.title,
            "amount_cents": variant.price,
            "compare_at_cents": variant.compare_at_price,
            "option_values": variant.option_values,
        }
        for variant in variants
    ]
    normalized_variants, variant_schema = funnel_ai._normalize_sales_pdp_variant_option_values(
        variants=variant_inputs,
        options_schema=selected_offer_options_schema,
    )

    aligned = False
    found_sales_hero = False
    for _index, props, config, source in funnel_ai._iter_sales_pdp_hero_configs(puck_data):
        found_sales_hero = True
        purchase = config.get("purchase")
        if not isinstance(purchase, dict):
            raise ValueError("SalesPdpHero.config.purchase must be an object for offer alignment.")
        if funnel_ai._align_sales_pdp_purchase_options_to_variants(
            purchase=purchase,
            variants=variant_inputs,
            options_schema=selected_offer_options_schema,
            normalized_variants=normalized_variants,
            variant_schema=variant_schema,
        ):
            aligned = True
            if source == "configJson":
                props["configJson"] = json.dumps(config, ensure_ascii=False)
            else:
                props["config"] = config

    if not found_sales_hero:
        raise ValueError("SalesPdpHero block is missing from sales template puck data.")
    return aligned


def _is_empty_page_generation_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    return any(marker in message for marker in _EMPTY_PAGE_ERROR_MARKERS)


def _run_generate_page_draft_with_retries(
    *,
    run_generation: Callable[[], Dict[str, Any]],
    max_attempts: int,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Dict[str, Any]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1.")

    for attempt in range(1, max_attempts + 1):
        try:
            return run_generation()
        except Exception as exc:  # noqa: BLE001
            should_retry = _is_empty_page_generation_error(exc) and attempt < max_attempts
            if not should_retry:
                raise
            if on_retry is not None:
                on_retry(attempt, exc)

    raise RuntimeError("AI draft generation failed after retries without returning a result.")


def _should_run_funnel_ai_processing(
    *,
    generate_ai_drafts: bool,
    strategy_v2_payload_applied: bool,
) -> bool:
    return generate_ai_drafts or strategy_v2_payload_applied


def _resolve_strategy_v2_selected_offer_id(
    *,
    strategy_v2_packet: dict[str, Any],
) -> str | None:
    offer_payload = strategy_v2_packet.get("offer")
    if not isinstance(offer_payload, dict):
        return None
    raw_offer_id = offer_payload.get("product_offer_id")
    if not isinstance(raw_offer_id, str) or not raw_offer_id.strip():
        return None
    return raw_offer_id.strip()


def _apply_pinned_strategy_v2_template_payload(
    *,
    template_id: str,
    payload_entry: dict[str, Any],
    base_puck_data: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    payload_template_id = str(payload_entry.get("template_id") or "").strip()
    if payload_template_id != template_id:
        raise ValueError(
            "Strategy V2 template payload template_id mismatch for funnel page generation. "
            f"Expected={template_id}, received={payload_template_id or '<empty>'}."
        )

    patch_operations = payload_entry.get("template_patch")
    if not isinstance(patch_operations, list) or not patch_operations:
        raise ValueError(
            f"Strategy V2 template payload for {template_id} is missing template_patch operations."
        )

    try:
        patched_puck_data = apply_strategy_v2_template_patch(
            base_puck_data=base_puck_data,
            operations=patch_operations,
            template_id=template_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"Strategy V2 template payload patch could not be applied for {template_id}. "
            f"Details: {exc}"
        ) from exc

    return patched_puck_data, json.dumps(payload_entry, ensure_ascii=True)


def _validate_selected_offer_for_funnel(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    selected_offer_id: str,
) -> None:
    offer = session.scalars(
        select(ProductOffer).where(
            ProductOffer.id == selected_offer_id,
            ProductOffer.org_id == org_id,
        )
    ).first()
    if offer is None:
        raise ValueError(
            "Strategy V2 selected offer could not be found for funnel generation. "
            f"selected_offer_id={selected_offer_id}"
        )
    if str(offer.client_id) != str(client_id) or str(offer.product_id or "") != str(product_id):
        raise ValueError(
            "Strategy V2 selected offer does not belong to the current client/product scope. "
            f"selected_offer_id={selected_offer_id}"
        )


def _clean_url_for_footer(value: object) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return ""
    return cleaned


def _build_policy_footer_payload(*, org_id: str, client_id: str) -> tuple[list[dict[str, str]], str, list[str]]:
    with session_scope() as session:
        profile = ClientComplianceProfilesRepository(session).get(org_id=org_id, client_id=client_id)
        design_systems = DesignSystemsRepository(session).list(org_id=org_id, client_id=client_id)
    if profile is None:
        raise ValueError(
            "Missing client compliance profile. "
            "Remediation: configure and sync policy pages before funnel generation."
        )

    privacy_url = _clean_url_for_footer(profile.privacy_policy_url)
    terms_url = _clean_url_for_footer(profile.terms_of_service_url)
    returns_url = _clean_url_for_footer(profile.returns_refunds_policy_url)
    shipping_url = _clean_url_for_footer(profile.shipping_policy_url)
    subscription_url = _clean_url_for_footer(profile.subscription_terms_and_cancellation_url)

    missing_policy_keys: list[str] = []
    if not privacy_url:
        missing_policy_keys.append("privacy_policy_url")
    if not terms_url:
        missing_policy_keys.append("terms_of_service_url")
    if not returns_url:
        missing_policy_keys.append("returns_refunds_policy_url")
    if not shipping_url:
        missing_policy_keys.append("shipping_policy_url")
    if missing_policy_keys:
        raise ValueError(
            "Missing required policy page URLs for footer rendering: "
            f"{', '.join(missing_policy_keys)}. "
            "Remediation: sync Shopify policy pages and retry."
        )

    links: list[dict[str, str]] = [
        {"label": "Privacy", "href": privacy_url},
        {"label": "Terms", "href": terms_url},
        {"label": "Returns", "href": returns_url},
        {"label": "Shipping", "href": shipping_url},
    ]
    if subscription_url:
        links.append({"label": "Subscription", "href": subscription_url})

    brand_name = ""
    for design_system in design_systems:
        tokens = design_system.tokens if isinstance(design_system.tokens, dict) else {}
        brand = tokens.get("brand")
        if not isinstance(brand, dict):
            continue
        candidate = str(brand.get("name") or "").strip()
        if candidate:
            brand_name = candidate
            break
    if not brand_name:
        brand_name = (
            str(profile.operating_entity_name or "").strip()
            or str(profile.legal_business_name or "").strip()
            or str(profile.client_id or "").strip()
        )
    if not brand_name:
        raise ValueError(
            "Unable to determine brand name for footer copyright. "
            "Remediation: set design system brand.name or compliance profile entity fields."
        )

    year = datetime.now(timezone.utc).year
    return links, f"\u00a9 {year} {brand_name}", list(_FOOTER_PAYMENT_ICON_KEYS)


def _assert_shopify_launch_readiness(
    *,
    org_id: str,
    client_id: str,
    product_id: str,
    selected_offer_id: str | None,
) -> None:
    status_payload = get_client_shopify_connection_status(client_id=client_id)
    state = str(status_payload.get("state") or "").strip()
    if state != "ready":
        raise ValueError(
            "Shopify connection is not ready for Strategy V2 launch funnel generation. "
            f"state={state or '<empty>'} message={status_payload.get('message')!r}. "
            "Remediation: connect Shopify for this workspace and ensure required scopes + storefront token are present."
        )

    with session_scope() as session:
        product = session.scalars(
            select(Product).where(Product.org_id == org_id, Product.id == product_id)
        ).first()
        if product is None:
            raise ValueError("Product not found for Shopify readiness validation.")
        if not isinstance(product.shopify_product_gid, str) or not product.shopify_product_gid.strip():
            raise ValueError(
                "Product is not connected to Shopify. Missing products.shopify_product_gid. "
                "Remediation: connect Shopify product and sync it before launching."
            )
        expected_product_type = canonical_product_type(str(product.product_type or ""))

        selected_offer = None
        selected_offer_options_schema: dict[str, Any] | None = None
        if isinstance(selected_offer_id, str) and selected_offer_id.strip():
            selected_offer = session.scalars(
                select(ProductOffer).where(
                    ProductOffer.org_id == org_id,
                    ProductOffer.id == selected_offer_id.strip(),
                    ProductOffer.product_id == product_id,
                )
            ).first()
            if selected_offer is None:
                raise ValueError(
                    "Selected offer was not found during Shopify readiness validation."
                )
            if isinstance(selected_offer.options_schema, dict):
                selected_offer_options_schema = selected_offer.options_schema

        variants_stmt = select(ProductVariant).where(ProductVariant.product_id == product_id)
        if isinstance(selected_offer_id, str) and selected_offer_id.strip():
            variants_stmt = variants_stmt.where(ProductVariant.offer_id == selected_offer_id.strip())
        variants = list(session.scalars(variants_stmt).all())
        if not variants:
            raise ValueError(
                "No product variants are available for Shopify launch readiness. "
                "Remediation: sync Shopify variants for this product/offer before launching."
            )

        ready_variants = [
            variant
            for variant in variants
            if isinstance(variant.provider, str)
            and variant.provider.strip().lower() == "shopify"
            and isinstance(variant.external_price_id, str)
            and variant.external_price_id.strip().startswith("gid://shopify/ProductVariant/")
            and isinstance(variant.option_values, dict)
            and bool(variant.option_values)
        ]
        if not ready_variants:
            raise ValueError(
                "Shopify launch readiness failed: no variants are fully connected for checkout "
                "(provider=shopify + external_price_id + option_values). "
                "Remediation: sync Shopify variants and option mappings before launching."
            )

        variant_inputs = [
            {
                "id": str(variant.id),
                "title": variant.title,
                "amount_cents": variant.price,
                "compare_at_cents": variant.compare_at_price,
                "option_values": variant.option_values,
            }
            for variant in ready_variants
        ]
        try:
            normalized_variants, _ = funnel_ai._normalize_sales_pdp_variant_option_values(
                variants=variant_inputs,
                options_schema=selected_offer_options_schema,
            )
        except ValueError as exc:
            raise ValueError(
                "Shopify launch readiness failed because synced variant option mappings are invalid. "
                f"Details: {exc}"
            ) from exc

        if isinstance(selected_offer_id, str) and selected_offer_id.strip():
            offer_ids = {str(row.get("offerId") or "").strip().lower() for row in normalized_variants}
            if offer_ids != {"single_device", "share_and_save", "family_bundle"}:
                raise ValueError(
                    "Shopify launch readiness failed because the selected offer is missing the canonical offer tiers. "
                    f"Observed offerIds={sorted(offer_ids)}. "
                    "Remediation: sync Shopify variants and map option_values.offerId for single_device/share_and_save/family_bundle."
                )

        resolved_shop_domain = (
            str(status_payload.get("shopDomain") or "").strip().lower()
            if isinstance(status_payload.get("shopDomain"), str)
            else None
        )
        try:
            shopify_product = get_client_shopify_product(
                client_id=client_id,
                product_gid=product.shopify_product_gid.strip(),
                shop_domain=resolved_shop_domain,
            )
        except HTTPException as exc:
            raise ValueError(
                "Shopify launch readiness failed while verifying the mapped Shopify product. "
                f"Details: {exc.detail if isinstance(exc.detail, str) else str(exc.detail)}"
            ) from exc

        remote_product_type = canonical_product_type(
            str(shopify_product.get("productType") or "")
        )
        if expected_product_type and remote_product_type and not product_type_matches(
            expected_product_type,
            remote_product_type,
        ):
            raise ValueError(
                "Shopify launch readiness failed because MOS product_type does not match the mapped Shopify productType. "
                f"mos={expected_product_type} shopify={remote_product_type}. "
                "Remediation: fix the MOS product type or Shopify productType before launching."
            )

        if is_book_product_type(expected_product_type):
            remote_variants = shopify_product.get("variants")
            if not isinstance(remote_variants, list) or not remote_variants:
                raise ValueError(
                    "Shopify launch readiness failed because the mapped Shopify book product returned no variants."
                )
            if not all(
                isinstance(variant, dict) and bool(variant.get("requiresShipping"))
                for variant in remote_variants
            ):
                raise ValueError(
                    "Shopify launch readiness failed because book variants in Shopify must require shipping. "
                    "Remediation: set the mapped Shopify product/variants to physical-shipping behavior before launching."
                )


@activity.defn
def create_campaign_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    name = params.get("campaign_name")
    product_id = params.get("product_id")
    channels = params.get("channels") or []
    asset_brief_types = params.get("asset_brief_types") or []
    if not name or not str(name).strip():
        raise ValueError("campaign_name is required to create a campaign")
    if not product_id:
        raise ValueError("product_id is required to create a campaign")
    if not channels or not all(isinstance(ch, str) and ch.strip() for ch in channels):
        raise ValueError("channels must include at least one non-empty value.")
    if not asset_brief_types or not all(isinstance(t, str) and t.strip() for t in asset_brief_types):
        raise ValueError("asset_brief_types must include at least one non-empty value.")

    with session_scope() as session:
        repo = CampaignsRepository(session)
        campaign = repo.create(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            name=str(name).strip(),
            channels=channels,
            asset_brief_types=asset_brief_types,
            goal_description=params.get("goal_description"),
            objective_type=params.get("objective_type"),
            numeric_target=params.get("numeric_target"),
            baseline=params.get("baseline"),
            timeframe_days=params.get("timeframe_days"),
            budget_min=params.get("budget_min"),
            budget_max=params.get("budget_max"),
        )
        temporal_workflow_id = params.get("temporal_workflow_id")
        temporal_run_id = params.get("temporal_run_id")
        if temporal_workflow_id and temporal_run_id:
            workflows_repo = WorkflowsRepository(session)
            run = workflows_repo.get_by_temporal_ids(
                org_id=org_id,
                temporal_workflow_id=str(temporal_workflow_id),
                temporal_run_id=str(temporal_run_id),
            )
            if run and not run.campaign_id:
                run.campaign_id = campaign.id
                session.commit()
        return {"campaign_id": str(campaign.id)}


@activity.defn
def create_funnel_drafts_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    product_id = params.get("product_id")
    experiment_spec_id = params.get("experiment_spec_id")
    funnel_name = params.get("funnel_name")
    pages: List[Dict[str, Any]] = params.get("pages") or []
    experiment = params.get("experiment")
    variant = params.get("variant")
    strategy_sheet = params.get("strategy_sheet") or {}
    asset_briefs = params.get("asset_briefs") or []
    strategy_v2_packet_raw = params.get("strategy_v2_packet")
    strategy_v2_copy_context_raw = params.get("strategy_v2_copy_context")
    strategy_v2_packet = (
        strategy_v2_packet_raw if isinstance(strategy_v2_packet_raw, dict) else {}
    )
    strategy_v2_copy_context = (
        strategy_v2_copy_context_raw if isinstance(strategy_v2_copy_context_raw, dict) else {}
    )
    strategy_v2_copy_payload = (
        strategy_v2_packet.get("copy")
        if isinstance(strategy_v2_packet.get("copy"), dict)
        else {}
    )
    strategy_v2_template_payloads = (
        strategy_v2_copy_payload.get("template_payloads")
        if isinstance(strategy_v2_copy_payload.get("template_payloads"), dict)
        else strategy_v2_packet.get("template_payloads")
        if isinstance(strategy_v2_packet.get("template_payloads"), dict)
        else None
    )
    strategy_v2_context_present = bool(strategy_v2_packet)
    strategy_v2_selected_offer_id = (
        _resolve_strategy_v2_selected_offer_id(strategy_v2_packet=strategy_v2_packet)
        if strategy_v2_context_present
        else None
    )
    idea_workspace_id = params.get("idea_workspace_id")
    actor_user_id = params.get("actor_user_id") or "workflow"
    generate_ai_drafts = bool(params.get("generate_ai_drafts", False))
    generate_testimonials = bool(params.get("generate_testimonials", False))
    async_media_enrichment = bool(params.get("async_media_enrichment", True))
    workflow_run_id = params.get("workflow_run_id")
    raw_ai_draft_max_attempts = params.get("ai_draft_max_attempts")
    if raw_ai_draft_max_attempts is None:
        ai_draft_max_attempts = _DEFAULT_AI_DRAFT_EMPTY_PAGE_MAX_ATTEMPTS
    else:
        try:
            ai_draft_max_attempts = int(raw_ai_draft_max_attempts)
        except (TypeError, ValueError) as exc:
            raise ValueError("ai_draft_max_attempts must be an integer >= 1 when provided.") from exc
        if ai_draft_max_attempts < 1:
            raise ValueError("ai_draft_max_attempts must be >= 1.")

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as log_session:
            WorkflowsRepository(log_session).log_activity(
                workflow_run_id=workflow_run_id,
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

    if not campaign_id:
        raise ValueError("campaign_id is required to create funnel drafts")
    if not pages:
        raise ValueError("pages are required to create funnel drafts")
    if generate_ai_drafts and (
        not isinstance(experiment, dict)
        or not experiment
        or not isinstance(variant, dict)
        or not variant
    ):
        raise ValueError("experiment and variant are required when generate_ai_drafts is enabled")

    if not product_id:
        raise ValueError("product_id is required to create funnel drafts")

    with session_scope() as session:
        campaign = session.scalars(
            select(Campaign).where(Campaign.org_id == org_id, Campaign.id == campaign_id)
        ).first()
        if not campaign:
            raise ValueError("Campaign not found for funnel draft creation")
        if campaign.product_id and str(campaign.product_id) != str(product_id):
            raise ValueError("product_id does not match campaign product_id")
        product = session.scalars(
            select(Product).where(Product.org_id == org_id, Product.id == product_id)
        ).first()
        if product is None:
            raise ValueError("Product not found for funnel draft creation")
        product_type = canonical_product_type(str(product.product_type or ""))
        if strategy_v2_context_present:
            _assert_strategy_v2_offer_product_type_matches_product(
                product_type=product_type,
                strategy_v2_packet=strategy_v2_packet,
            )
        if strategy_v2_selected_offer_id:
            _validate_selected_offer_for_funnel(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=str(product_id),
                selected_offer_id=str(strategy_v2_selected_offer_id),
            )

        design_systems_repo = DesignSystemsRepository(session)

        def resolve_template_tokens(page_spec: Dict[str, Any]) -> Optional[dict[str, Any]]:
            design_system_id = page_spec.get("design_system_id") or page_spec.get("designSystemId")
            if design_system_id:
                design_system = design_systems_repo.get(
                    org_id=org_id,
                    design_system_id=str(design_system_id),
                )
                if not design_system:
                    raise ValueError(f"Design system not found: {design_system_id}")
                tokens = design_system.tokens
                if tokens is None:
                    raise ValueError("Design system tokens are required to apply brand assets.")
                if not isinstance(tokens, dict):
                    raise ValueError("Design system tokens must be a JSON object.")
                return tokens
            tokens = resolve_design_system_tokens(session=session, org_id=org_id, client_id=client_id)
            if tokens is not None and not isinstance(tokens, dict):
                raise ValueError("Design system tokens must be a JSON object.")
            return tokens

        funnels_repo = FunnelsRepository(session)
        pages_repo = FunnelPagesRepository(session)
        resolved_funnel_name = funnel_name or "Launch"
        existing_funnel = session.scalars(
            select(Funnel)
            .where(
                Funnel.org_id == org_id,
                Funnel.client_id == client_id,
                Funnel.campaign_id == campaign_id,
                Funnel.experiment_spec_id == experiment_spec_id,
                Funnel.name == resolved_funnel_name,
            )
            .order_by(Funnel.created_at.desc())
        ).first()

        funnel = existing_funnel
        if not funnel:
            funnel = funnels_repo.create(
                org_id=org_id,
                client_id=client_id,
                campaign_id=campaign_id,
                product_id=product_id,
                experiment_spec_id=experiment_spec_id,
                selected_offer_id=strategy_v2_selected_offer_id,
                name=resolved_funnel_name,
                status=FunnelStatusEnum.draft,
            )
        elif strategy_v2_selected_offer_id and str(funnel.selected_offer_id or "") != str(strategy_v2_selected_offer_id):
            funnel = funnels_repo.update(
                org_id=org_id,
                funnel_id=str(funnel.id),
                selected_offer_id=strategy_v2_selected_offer_id,
            ) or funnel
        effective_selected_offer_id = str(funnel.selected_offer_id or "").strip() or None

        existing_pages = pages_repo.list(funnel_id=str(funnel.id)) if funnel else []
        existing_pages_by_slug = {page.slug: page for page in existing_pages}

        created_pages: list[dict[str, str]] = []
        resolved_pages: list[FunnelPage] = []
        non_fatal_errors: list[dict[str, Any]] = []
        media_enrichment_jobs: list[dict[str, Any]] = []
        for idx, page_spec in enumerate(pages):
            template_id = page_spec.get("template_id") or page_spec.get("templateId")
            if not template_id:
                raise ValueError("template_id is required for each funnel page")
            template = get_funnel_template(template_id)
            if not template:
                raise ValueError(f"Funnel template not found: {template_id}")

            page_name = page_spec.get("name") or template.name
            desired_slug = page_spec.get("slug") or page_name
            slug = desired_slug
            page = existing_pages_by_slug.get(desired_slug)
            if not page:
                slug = generate_unique_slug(session, funnel_id=str(funnel.id), desired_slug=desired_slug)
            design_system_tokens = resolve_template_tokens(page_spec)
            puck_data = apply_template_assets(
                session=session,
                org_id=org_id,
                client_id=client_id,
                template=template,
                design_system_tokens=design_system_tokens,
            )
            template_payload_json: str | None = None
            strategy_v2_payload_applied = False
            if template_id in {"sales-pdp", "pre-sales-listicle"} and strategy_v2_context_present:
                if not isinstance(strategy_v2_template_payloads, dict):
                    raise ValueError(
                        "Strategy V2 template_payloads are required for template-based funnel generation "
                        "when strategy_v2_packet is provided."
                    )
                payload_entry = strategy_v2_template_payloads.get(template_id)
                if not isinstance(payload_entry, dict):
                    raise ValueError(
                        "Strategy V2 template payload is missing for page template "
                        f"{template_id}."
                    )
                puck_data, template_payload_json = _apply_pinned_strategy_v2_template_payload(
                    template_id=template_id,
                    payload_entry=payload_entry,
                    base_puck_data=puck_data,
                )
                strategy_v2_payload_applied = True
                footer_links, footer_copyright, footer_icons = _build_policy_footer_payload(
                    org_id=org_id,
                    client_id=client_id,
                )
                if template_id == "pre-sales-listicle":
                    footer_patch_operations = [
                        {
                            "component_type": "PreSalesFooter",
                            "field_path": "props.config.links",
                            "value": footer_links,
                        },
                        {
                            "component_type": "PreSalesFooter",
                            "field_path": "props.config.paymentIcons",
                            "value": footer_icons,
                        },
                        {
                            "component_type": "PreSalesFooter",
                            "field_path": "props.config.copyright",
                            "value": footer_copyright,
                        },
                    ]
                elif template_id == "sales-pdp":
                    footer_patch_operations = [
                        {
                            "component_type": "SalesPdpFooter",
                            "field_path": "props.config.links",
                            "value": footer_links,
                        },
                        {
                            "component_type": "SalesPdpFooter",
                            "field_path": "props.config.paymentIcons",
                            "value": footer_icons,
                        },
                        {
                            "component_type": "SalesPdpFooter",
                            "field_path": "props.config.copyright",
                            "value": footer_copyright,
                        },
                    ]
                else:
                    footer_patch_operations = []
                if footer_patch_operations:
                    puck_data = apply_strategy_v2_template_patch(
                        base_puck_data=puck_data,
                        operations=footer_patch_operations,
                        template_id=template_id,
                    )
                if template_id == "sales-pdp":
                    _align_sales_pdp_purchase_options_for_selected_offer(
                        session=session,
                        org_id=org_id,
                        product_id=str(product_id),
                        selected_offer_id=effective_selected_offer_id,
                        puck_data=puck_data,
                    )
            elif template_id == "sales-pdp" and effective_selected_offer_id:
                _align_sales_pdp_purchase_options_for_selected_offer(
                    session=session,
                    org_id=org_id,
                    product_id=str(product_id),
                    selected_offer_id=effective_selected_offer_id,
                    puck_data=puck_data,
                )

            if page:
                if page.template_id != template_id:
                    page = pages_repo.update(page_id=str(page.id), template_id=template_id) or page
                if page.ordering != idx:
                    page = pages_repo.update(page_id=str(page.id), ordering=idx) or page
            else:
                page = pages_repo.create(
                    funnel_id=str(funnel.id),
                    name=page_name,
                    slug=slug,
                    ordering=idx,
                    template_id=template_id,
                    design_system_id=page_spec.get("design_system_id") or page_spec.get("designSystemId"),
                )

            version_ai_metadata: dict[str, Any] | None = None
            if strategy_v2_payload_applied:
                strategy_v2_provenance = (
                    strategy_v2_packet.get("provenance")
                    if isinstance(strategy_v2_packet.get("provenance"), dict)
                    else {}
                )
                strategy_v2_launch_metadata = (
                    strategy_v2_packet.get("launch_metadata")
                    if isinstance(strategy_v2_packet.get("launch_metadata"), dict)
                    else None
                )
                version_ai_metadata = {
                    "strategy_v2_provenance": strategy_v2_provenance,
                    "strategy_v2_launch": strategy_v2_launch_metadata,
                    "template_id": template_id,
                }

            normalize_public_page_metadata_for_context(
                session=session,
                org_id=org_id,
                funnel=funnel,
                page=page,
                puck_data=puck_data,
            )

            version = FunnelPageVersion(
                page_id=page.id,
                status=FunnelPageVersionStatusEnum.draft,
                puck_data=puck_data,
                source=FunnelPageVersionSourceEnum.human,
                ai_metadata=version_ai_metadata,
                created_at=datetime.now(timezone.utc),
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            created_pages.append({"page_id": str(page.id), "draft_version_id": str(version.id)})
            resolved_pages.append(page)

            should_run_funnel_ai_processing = _should_run_funnel_ai_processing(
                generate_ai_drafts=generate_ai_drafts,
                strategy_v2_payload_applied=strategy_v2_payload_applied,
            )
            if should_run_funnel_ai_processing:
                if (
                    not isinstance(experiment, dict)
                    or not experiment
                    or not isinstance(variant, dict)
                    or not variant
                ):
                    raise ValueError(
                        "experiment and variant are required when funnel AI processing is enabled "
                        "(generate_ai_drafts=true or strategy_v2 template payloads are applied)."
                    )
                prompt = _build_funnel_prompt(
                    strategy_sheet=strategy_sheet,
                    experiment=experiment,
                    variant=variant,
                    asset_briefs=asset_briefs,
                    strategy_v2_packet=strategy_v2_packet,
                    strategy_v2_copy_context=strategy_v2_copy_context,
                    page_name=page_name,
                    template_id=template_id,
                )
                log_activity(
                    "funnel_page_draft",
                    "started",
                    payload_in={
                        "page_id": str(page.id),
                        "template_id": template_id,
                        "funnel_id": str(funnel.id),
                    },
                )
                if generate_testimonials:
                    if not async_media_enrichment:
                        log_activity(
                            "funnel_page_testimonials",
                            "started",
                            payload_in={"page_id": str(page.id), "funnel_id": str(funnel.id)},
                        )
                try:
                    heartbeat_started_at = time.monotonic()

                    def _heartbeat_payload() -> dict[str, Any]:
                        return {
                            "phase": "funnel_page_generation",
                            "funnel_id": str(funnel.id),
                            "page_id": str(page.id),
                            "template_id": str(template_id),
                            "elapsed_seconds": int(time.monotonic() - heartbeat_started_at),
                        }

                    with _activity_heartbeat_loop(payload_factory=_heartbeat_payload):
                        result = _run_generate_page_draft_with_retries(
                            run_generation=lambda: run_generate_page_draft(
                                session=session,
                                org_id=org_id,
                                user_id=str(actor_user_id),
                                funnel_id=str(funnel.id),
                                page_id=str(page.id),
                                prompt=prompt,
                                current_puck_data=puck_data,
                                template_id=template_id,
                                idea_workspace_id=idea_workspace_id,
                                generate_images=not async_media_enrichment,
                                generate_testimonials=generate_testimonials and not async_media_enrichment,
                                skip_draft_generation=strategy_v2_payload_applied,
                                copy_pack=template_payload_json,
                            ),
                            max_attempts=ai_draft_max_attempts,
                            on_retry=lambda attempt, exc: log_activity(
                                "funnel_page_draft",
                                "retrying",
                                payload_in={
                                    "page_id": str(page.id),
                                    "template_id": template_id,
                                    "funnel_id": str(funnel.id),
                                    "attempt": attempt,
                                    "max_attempts": ai_draft_max_attempts,
                                    "reason": "empty_page_generation",
                                    "error": str(exc),
                                },
                            ),
                        )
                    draft_version_id = result.get("draftVersionId") or ""
                    generated_images = result.get("generatedImages") or []
                    if not draft_version_id:
                        raise RuntimeError("AI draft generation returned no draftVersionId.")
                    image_errors = _collect_image_generation_errors(
                        generated_images=generated_images,
                        funnel_id=str(funnel.id),
                        page_id=str(page.id),
                        page_name=page_name,
                        template_id=template_id,
                    )
                    if image_errors:
                        non_fatal_errors.extend(image_errors)
                    if async_media_enrichment:
                        media_enrichment_jobs.append(
                            {
                                "funnel_id": str(funnel.id),
                                "page_id": str(page.id),
                                "page_name": page_name,
                                "template_id": template_id,
                                "prompt": prompt,
                                "idea_workspace_id": idea_workspace_id,
                                "actor_user_id": str(actor_user_id),
                                "generate_testimonials": bool(generate_testimonials),
                                "workflow_run_id": workflow_run_id,
                            }
                        )
                        log_activity(
                            "funnel_page_media_enrichment",
                            "queued",
                            payload_in={
                                "page_id": str(page.id),
                                "funnel_id": str(funnel.id),
                                "template_id": template_id,
                                "generate_testimonials": bool(generate_testimonials),
                            },
                        )
                except Exception as exc:  # noqa: BLE001
                    log_activity(
                        "funnel_page_draft",
                        "failed",
                        error=str(exc),
                        payload_in={
                            "page_id": str(page.id),
                            "template_id": template_id,
                            "funnel_id": str(funnel.id),
                        },
                    )
                    if generate_testimonials:
                        error_text = str(exc)
                        if async_media_enrichment:
                            log_activity(
                                "funnel_page_testimonials",
                                "skipped",
                                payload_in={
                                    "page_id": str(page.id),
                                    "funnel_id": str(funnel.id),
                                    "reason": "Draft generation failed before async testimonial enrichment.",
                                },
                            )
                        elif "testimonial" in error_text.lower():
                            log_activity(
                                "funnel_page_testimonials",
                                "failed",
                                error=error_text,
                                payload_in={"page_id": str(page.id), "funnel_id": str(funnel.id)},
                            )
                        else:
                            log_activity(
                                "funnel_page_testimonials",
                                "skipped",
                                payload_in={
                                    "page_id": str(page.id),
                                    "funnel_id": str(funnel.id),
                                    "reason": "Draft generation failed before testimonial step.",
                                },
                            )
                    raise
                else:
                    log_activity(
                        "funnel_page_draft",
                        "completed",
                        payload_out={
                            "page_id": str(page.id),
                            "draft_version_id": draft_version_id,
                            "funnel_id": str(funnel.id),
                            "image_error_count": len(image_errors),
                            "image_errors": [entry["message"] for entry in image_errors],
                        },
                    )
                    if generate_testimonials:
                        if async_media_enrichment:
                            log_activity(
                                "funnel_page_testimonials",
                                "queued",
                                payload_in={
                                    "page_id": str(page.id),
                                    "funnel_id": str(funnel.id),
                                    "draft_version_id": draft_version_id,
                                    "mode": "async_media_enrichment",
                                },
                            )
                        else:
                            log_activity(
                                "funnel_page_testimonials",
                                "completed",
                                payload_out={
                                    "page_id": str(page.id),
                                    "funnel_id": str(funnel.id),
                                    "draft_version_id": draft_version_id,
                                    "mode": "inline_page_draft",
                                },
                            )
                    else:
                        log_activity(
                            "funnel_page_testimonials",
                            "skipped",
                            payload_in={
                                "page_id": str(page.id),
                                "funnel_id": str(funnel.id),
                                "reason": "Synthetic testimonials generation disabled for this run.",
                            },
                        )
        if created_pages:
            funnels_repo.update(
                org_id=org_id,
                funnel_id=str(funnel.id),
                entry_page_id=created_pages[0]["page_id"],
            )

        if resolved_pages:
            pre_sales_pages = [page for page in resolved_pages if page.template_id == "pre-sales-listicle"]
            sales_pages = [page for page in resolved_pages if page.template_id == "sales-pdp"]
            if pre_sales_pages:
                if len(sales_pages) != 1:
                    raise ValueError(
                        "Default next page wiring requires exactly one sales page. "
                        "Add a sales page or set nextPageId explicitly."
                    )
                sales_page_id = str(sales_pages[0].id)
                for page in pre_sales_pages:
                    if page.next_page_id:
                        continue
                    pages_repo.update(page_id=str(page.id), next_page_id=sales_page_id)

        return {
            "funnel_id": str(funnel.id),
            "entry_page_id": created_pages[0]["page_id"] if created_pages else None,
            "pages": created_pages,
            "non_fatal_errors": non_fatal_errors,
            "media_enrichment_jobs": media_enrichment_jobs,
        }


def _build_funnel_prompt(
    *,
    strategy_sheet: Dict[str, Any],
    experiment: Dict[str, Any],
    variant: Dict[str, Any],
    asset_briefs: List[Dict[str, Any]],
    strategy_v2_packet: Dict[str, Any],
    strategy_v2_copy_context: Dict[str, Any],
    page_name: str,
    template_id: Optional[str],
) -> str:
    experiment_name = experiment.get("name") or experiment.get("id")
    variant_name = variant.get("name") or variant.get("id")
    strategy_v2_packet_summary = json.dumps(strategy_v2_packet, ensure_ascii=True)[:6000] if strategy_v2_packet else "{}"
    strategy_v2_copy_context_summary = (
        json.dumps(strategy_v2_copy_context, ensure_ascii=True)[:4000]
        if strategy_v2_copy_context
        else "{}"
    )
    return f"""
You are generating funnel page copy for a marketing experiment.

Campaign goal: {strategy_sheet.get("goal")}
Campaign hypothesis: {strategy_sheet.get("hypothesis")}
Channel plan: {strategy_sheet.get("channelPlan") or []}
Messaging pillars: {strategy_sheet.get("messaging") or []}
Risks: {strategy_sheet.get("risks") or []}
Mitigations: {strategy_sheet.get("mitigations") or []}

Experiment: {experiment_name}
Experiment hypothesis: {experiment.get("hypothesis")}
Variant: {variant_name}
Variant description: {variant.get("description")}
Variant channels: {variant.get("channels") or []}
Variant guardrails: {variant.get("guardrails") or []}

Asset briefs (requirements + concepts):
{asset_briefs}
Strategy V2 downstream packet:
{strategy_v2_packet_summary}
Strategy V2 copy context:
{strategy_v2_copy_context_summary}

Page to generate: {page_name}
Template: {template_id}

Instructions:
- Align copy and structure to the experiment variant angle.
- Use brand voice, constraints, and claims from the attached context documents.
- Treat Strategy V2 downstream packet + copy context as source-of-truth context when present.
- Keep claims compliant and avoid medical promises.
- Do NOT invent product facts or policy specifics (warranty length, return window, price, FDA status, clinical study outcomes, time-to-results, session length, brightness levels).
- Do NOT include any numbers anywhere unless the number is explicitly present in the attached product/offer context (if absent, rewrite without numbers).
- If the base template contains numeric placeholders (review counts, star ratings, trial durations, discounts), remove or replace them with non-numeric phrasing.
- Provide concrete, conversion-focused copy for the template sections.
"""


@activity.defn
def enrich_funnel_page_media_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    funnel_id = params.get("funnel_id")
    page_id = params.get("page_id")
    page_name = params.get("page_name") or "Page"
    template_id = params.get("template_id")
    prompt = params.get("prompt") or "Media enrichment run"
    idea_workspace_id = params.get("idea_workspace_id")
    actor_user_id = params.get("actor_user_id") or "workflow"
    generate_testimonials = bool(params.get("generate_testimonials", False))
    workflow_run_id = params.get("workflow_run_id")

    if not funnel_id:
        raise ValueError("funnel_id is required for media enrichment")
    if not page_id:
        raise ValueError("page_id is required for media enrichment")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required for media enrichment")

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as session:
            wf_repo = WorkflowsRepository(session)
            wf_repo.log_activity(
                workflow_run_id=workflow_run_id,
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

    log_activity(
        "funnel_page_media_enrichment",
        "started",
        payload_in={
            "funnel_id": str(funnel_id),
            "page_id": str(page_id),
            "template_id": template_id,
            "generate_testimonials": generate_testimonials,
        },
    )
    if generate_testimonials:
        log_activity(
            "funnel_page_testimonials",
            "started",
            payload_in={
                "funnel_id": str(funnel_id),
                "page_id": str(page_id),
                "mode": "async_media_enrichment",
            },
        )

    with session_scope() as session:
        try:
            result = run_generate_page_draft(
                session=session,
                org_id=org_id,
                user_id=str(actor_user_id),
                funnel_id=str(funnel_id),
                page_id=str(page_id),
                prompt=str(prompt),
                template_id=str(template_id) if template_id else None,
                idea_workspace_id=str(idea_workspace_id) if idea_workspace_id else None,
                generate_images=True,
                generate_testimonials=generate_testimonials,
                skip_draft_generation=True,
            )
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            log_activity(
                "funnel_page_media_enrichment",
                "failed",
                error=error_text,
                payload_in={
                    "funnel_id": str(funnel_id),
                    "page_id": str(page_id),
                    "template_id": template_id,
                },
            )
            if generate_testimonials:
                if "testimonial" in error_text.lower():
                    log_activity(
                        "funnel_page_testimonials",
                        "failed",
                        error=error_text,
                        payload_in={
                            "funnel_id": str(funnel_id),
                            "page_id": str(page_id),
                            "mode": "async_media_enrichment",
                        },
                    )
                else:
                    log_activity(
                        "funnel_page_testimonials",
                        "skipped",
                        payload_in={
                            "funnel_id": str(funnel_id),
                            "page_id": str(page_id),
                            "mode": "async_media_enrichment",
                            "reason": "Media enrichment failed before testimonials completed.",
                        },
                    )
            raise

    generated_images = result.get("generatedImages") or []
    image_errors = _collect_image_generation_errors(
        generated_images=generated_images,
        funnel_id=str(funnel_id),
        page_id=str(page_id),
        page_name=str(page_name),
        template_id=str(template_id) if template_id else None,
    )
    log_activity(
        "funnel_page_media_enrichment",
        "completed",
        payload_out={
            "funnel_id": str(funnel_id),
            "page_id": str(page_id),
            "draft_version_id": result.get("draftVersionId"),
            "image_error_count": len(image_errors),
            "image_errors": [entry["message"] for entry in image_errors],
        },
    )
    if generate_testimonials:
        log_activity(
            "funnel_page_testimonials",
            "completed",
            payload_out={
                "funnel_id": str(funnel_id),
                "page_id": str(page_id),
                "draft_version_id": result.get("draftVersionId"),
                "mode": "async_media_enrichment",
            },
        )
    else:
        log_activity(
            "funnel_page_testimonials",
            "skipped",
            payload_in={
                "funnel_id": str(funnel_id),
                "page_id": str(page_id),
                "mode": "async_media_enrichment",
                "reason": "Synthetic testimonials generation disabled for this run.",
            },
        )

    return {
        "funnel_id": str(funnel_id),
        "page_id": str(page_id),
        "page_name": str(page_name),
        "template_id": str(template_id) if template_id else None,
        "draft_version_id": result.get("draftVersionId"),
        "generated_images": generated_images,
        "non_fatal_errors": image_errors,
        "agent_run_id": result.get("runId"),
    }


@activity.defn
def create_funnels_from_experiments_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    campaign_id = params.get("campaign_id")
    experiment_specs: List[Dict[str, Any]] = params.get("experiment_specs") or []
    pages: List[Dict[str, Any]] = params.get("pages") or []
    funnel_name_prefix = params.get("funnel_name_prefix")
    idea_workspace_id = params.get("idea_workspace_id")
    actor_user_id = params.get("actor_user_id") or "workflow"
    generate_ai_drafts = bool(params.get("generate_ai_drafts", False))
    generate_testimonials = bool(params.get("generate_testimonials", False))
    async_media_enrichment = bool(params.get("async_media_enrichment", True))
    temporal_workflow_id = params.get("temporal_workflow_id")
    temporal_run_id = params.get("temporal_run_id")
    require_pinned_strategy_v2_context = bool(params.get("require_pinned_strategy_v2_context", False))
    require_shopify_connection = bool(params.get("require_shopify_connection", False))
    provided_strategy_v2_packet_raw = params.get("strategy_v2_packet")
    provided_strategy_v2_copy_context_raw = params.get("strategy_v2_copy_context")
    provided_strategy_v2_packet = (
        provided_strategy_v2_packet_raw
        if isinstance(provided_strategy_v2_packet_raw, dict)
        else None
    )
    provided_strategy_v2_copy_context = (
        provided_strategy_v2_copy_context_raw
        if isinstance(provided_strategy_v2_copy_context_raw, dict)
        else None
    )

    workflow_run_id: Optional[str] = None
    if temporal_workflow_id and temporal_run_id:
        with session_scope() as session:
            wf_repo = WorkflowsRepository(session)
            run = wf_repo.get_by_temporal_ids(
                org_id=org_id,
                temporal_workflow_id=str(temporal_workflow_id),
                temporal_run_id=str(temporal_run_id),
            )
            if run:
                workflow_run_id = str(run.id)

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as session:
            wf_repo = WorkflowsRepository(session)
            wf_repo.log_activity(
                workflow_run_id=workflow_run_id,
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

    if not campaign_id:
        raise ValueError("campaign_id is required to create funnels from experiments")
    if not product_id:
        raise ValueError("product_id is required to create funnels from experiments")
    if not experiment_specs:
        raise ValueError("experiment_specs are required to create funnels from experiments")
    if not pages:
        raise ValueError("pages are required to create funnels from experiments")
    if require_pinned_strategy_v2_context and provided_strategy_v2_packet is None:
        raise ValueError(
            "strategy_v2_packet is required when require_pinned_strategy_v2_context=true."
        )
    if require_pinned_strategy_v2_context and provided_strategy_v2_copy_context is None:
        raise ValueError(
            "strategy_v2_copy_context is required when require_pinned_strategy_v2_context=true."
        )

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        strategy = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id, campaign_id=campaign_id, artifact_type=ArtifactTypeEnum.strategy_sheet
        )
        briefs_artifact = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id, campaign_id=campaign_id, artifact_type=ArtifactTypeEnum.asset_brief
        )
        strategy_v2_outputs: dict[str, Any] = {}
        if provided_strategy_v2_packet is None or provided_strategy_v2_copy_context is None:
            strategy_v2_outputs = load_strategy_v2_outputs(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
            )

    if not strategy:
        raise ValueError("Strategy sheet not found for funnel generation")

    strategy_sheet = strategy.data if isinstance(strategy.data, dict) else {}
    strategy_v2_packet = (
        provided_strategy_v2_packet
        if isinstance(provided_strategy_v2_packet, dict)
        else strategy_v2_outputs.get("downstream_packet")
        if isinstance(strategy_v2_outputs.get("downstream_packet"), dict)
        else {}
    )
    strategy_v2_copy_context = (
        provided_strategy_v2_copy_context
        if isinstance(provided_strategy_v2_copy_context, dict)
        else strategy_v2_outputs.get("copy_context")
        if isinstance(strategy_v2_outputs.get("copy_context"), dict)
        else {}
    )
    strategy_v2_selected_offer_id = _resolve_strategy_v2_selected_offer_id(
        strategy_v2_packet=strategy_v2_packet,
    )
    if require_pinned_strategy_v2_context:
        template_payloads = strategy_v2_packet.get("template_payloads")
        if not isinstance(template_payloads, dict):
            raise ValueError(
                "strategy_v2_packet.template_payloads is required for pinned launch funnel generation."
            )
        for template_id in ("pre-sales-listicle", "sales-pdp"):
            entry = template_payloads.get(template_id)
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Pinned strategy_v2_packet is missing template payload for {template_id}."
                )
            patch_ops = entry.get("template_patch")
            if not isinstance(patch_ops, list) or not patch_ops:
                raise ValueError(
                    f"Pinned strategy_v2 template payload for {template_id} is missing template_patch operations."
                )
        if not strategy_v2_selected_offer_id:
            raise ValueError(
                "Pinned strategy_v2_packet is missing offer.product_offer_id. "
                "Remediation: rerun Strategy V2 winner + copy pipeline so offer linkage is preserved."
            )
    if require_shopify_connection:
        _assert_shopify_launch_readiness(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            selected_offer_id=strategy_v2_selected_offer_id,
        )
    asset_briefs_all: list[dict[str, Any]] = []
    if briefs_artifact and isinstance(briefs_artifact.data, dict):
        raw_briefs = briefs_artifact.data.get("asset_briefs") or []
        if isinstance(raw_briefs, list):
            asset_briefs_all = [b for b in raw_briefs if isinstance(b, dict)]

    results = []
    non_fatal_errors: list[dict[str, Any]] = []
    media_enrichment_jobs: list[dict[str, Any]] = []
    for experiment in experiment_specs:
        if not isinstance(experiment, dict):
            raise ValueError("Experiment specs must be objects.")
        experiment_id = experiment.get("id")
        if not experiment_id:
            raise ValueError("Experiment spec missing id.")
        variants = experiment.get("variants") or []
        if not variants:
            raise ValueError(f"Experiment {experiment_id} has no variants.")
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError(f"Variant spec for experiment {experiment_id} must be an object.")
            variant_id = variant.get("id")
            if not variant_id:
                raise ValueError(f"Variant missing id for experiment {experiment_id}.")

            funnel_label = funnel_name_prefix or "Funnel"
            funnel_name = (
                f"{funnel_label} · {experiment.get('name') or experiment_id} · "
                f"{variant.get('name') or variant_id}"
            )

            log_activity(
                "funnel_draft",
                "started",
                payload_in={
                    "experiment_id": experiment_id,
                    "variant_id": variant_id,
                    "funnel_name": funnel_name,
                    "template_ids": [page.get("template_id") or page.get("templateId") for page in pages],
                },
            )
            try:
                matching_briefs = [
                    b
                    for b in asset_briefs_all
                    if b.get("experimentId") == experiment_id and b.get("variantId") == variant_id
                ]
                funnel_result = create_funnel_drafts_activity(
                    {
                        "org_id": org_id,
                        "client_id": client_id,
                        "product_id": product_id,
                        "campaign_id": campaign_id,
                        "experiment_spec_id": experiment_id,
                        "funnel_name": funnel_name,
                        "pages": pages,
                        "experiment": experiment,
                        "variant": variant,
                        "strategy_sheet": strategy_sheet,
                        "asset_briefs": matching_briefs,
                        "strategy_v2_packet": strategy_v2_packet,
                        "strategy_v2_copy_context": strategy_v2_copy_context,
                        "idea_workspace_id": idea_workspace_id,
                        "actor_user_id": actor_user_id,
                        "generate_ai_drafts": generate_ai_drafts,
                        "generate_testimonials": generate_testimonials,
                        "async_media_enrichment": async_media_enrichment,
                        "ai_draft_max_attempts": params.get("ai_draft_max_attempts"),
                        "workflow_run_id": workflow_run_id,
                    }
                )
                log_activity(
                    "funnel_draft",
                    "completed",
                    payload_out={
                        "experiment_id": experiment_id,
                        "variant_id": variant_id,
                        "funnel_id": funnel_result.get("funnel_id") if isinstance(funnel_result, dict) else None,
                        "non_fatal_error_count": (
                            len(funnel_result.get("non_fatal_errors") or [])
                            if isinstance(funnel_result, dict)
                            else 0
                        ),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log_activity(
                    "funnel_draft",
                    "failed",
                    error=str(exc),
                    payload_in={
                        "experiment_id": experiment_id,
                        "variant_id": variant_id,
                        "funnel_name": funnel_name,
                    },
                )
                raise

            funnel_non_fatal = (
                funnel_result.get("non_fatal_errors")
                if isinstance(funnel_result, dict)
                else None
            )
            if isinstance(funnel_non_fatal, list):
                for entry in funnel_non_fatal:
                    if not isinstance(entry, dict):
                        continue
                    non_fatal_errors.append(
                        {
                            **entry,
                            "experiment_id": experiment_id,
                            "variant_id": variant_id,
                        }
                    )

            funnel_media_jobs = (
                funnel_result.get("media_enrichment_jobs")
                if isinstance(funnel_result, dict)
                else None
            )
            if isinstance(funnel_media_jobs, list):
                for entry in funnel_media_jobs:
                    if not isinstance(entry, dict):
                        continue
                    media_enrichment_jobs.append(
                        {
                            **entry,
                            "experiment_id": experiment_id,
                            "variant_id": variant_id,
                        }
                    )

            results.append({"experiment_id": experiment_id, "variant_id": variant_id, "funnel": funnel_result})

    return {
        "funnels": results,
        "non_fatal_errors": non_fatal_errors,
        "media_enrichment_jobs": media_enrichment_jobs,
    }
