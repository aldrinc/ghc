import json
from datetime import datetime, timezone
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.db.models import Campaign, Client, Product, ProductOffer, ProductVariant
from app.temporal.activities import campaign_intent_activities as cia
from app.temporal.activities.campaign_intent_activities import (
    _collect_image_generation_errors,
    _is_empty_page_generation_error,
    _run_generate_page_draft_with_retries,
    _should_run_funnel_ai_processing,
)


def test_is_empty_page_generation_error_matches_wrapped_tool_error():
    exc = RuntimeError(
        "Tool draft.generate_page failed: AI generation produced an empty page (no content). details={...}"
    )
    assert _is_empty_page_generation_error(exc) is True


def test_run_generate_page_draft_with_retries_retries_empty_page_then_succeeds():
    attempts = {"count": 0}
    retry_attempts: list[int] = []

    def _generate():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("AI generation produced an empty page (no content).")
        return {"draftVersionId": "draft-123"}

    result = _run_generate_page_draft_with_retries(
        run_generation=_generate,
        max_attempts=3,
        on_retry=lambda attempt, _exc: retry_attempts.append(attempt),
    )

    assert result["draftVersionId"] == "draft-123"
    assert attempts["count"] == 3
    assert retry_attempts == [1, 2]


def test_run_generate_page_draft_with_retries_does_not_retry_non_empty_error():
    attempts = {"count": 0}

    def _generate():
        attempts["count"] += 1
        raise RuntimeError("Draft validation failed: missing component")

    with pytest.raises(RuntimeError, match="Draft validation failed"):
        _run_generate_page_draft_with_retries(run_generation=_generate, max_attempts=3)

    assert attempts["count"] == 1


def test_run_generate_page_draft_with_retries_raises_after_max_empty_page_attempts():
    attempts = {"count": 0}
    retry_attempts: list[int] = []

    def _generate():
        attempts["count"] += 1
        raise RuntimeError("AI generation produced an empty page (no content).")

    with pytest.raises(RuntimeError, match="empty page"):
        _run_generate_page_draft_with_retries(
            run_generation=_generate,
            max_attempts=3,
            on_retry=lambda attempt, _exc: retry_attempts.append(attempt),
        )

    assert attempts["count"] == 3
    assert retry_attempts == [1, 2]


def test_collect_image_generation_errors_returns_structured_entries():
    generated_images = [
        {"assetPublicId": "abc"},
        {"error": "Unsplash search returned 0 results"},
        {"error": "  CDN timeout  "},
        "not-an-object",
        {"error": ""},
    ]

    errors = _collect_image_generation_errors(
        generated_images=generated_images,
        funnel_id="funnel-1",
        page_id="page-1",
        page_name="Sales",
        template_id="sales-pdp",
    )

    assert errors == [
        {
            "type": "image_generation",
            "severity": "warning",
            "funnel_id": "funnel-1",
            "page_id": "page-1",
            "page_name": "Sales",
            "template_id": "sales-pdp",
            "message": "Unsplash search returned 0 results",
        },
        {
            "type": "image_generation",
            "severity": "warning",
            "funnel_id": "funnel-1",
            "page_id": "page-1",
            "page_name": "Sales",
            "template_id": "sales-pdp",
            "message": "CDN timeout",
        },
    ]


def test_collect_image_generation_errors_ignores_non_list_inputs():
    errors = _collect_image_generation_errors(
        generated_images={"error": "boom"},
        funnel_id="funnel-1",
        page_id="page-1",
        page_name="Sales",
        template_id=None,
    )
    assert errors == []


def test_create_funnel_drafts_activity_uses_pinned_template_patch_for_legacy_presell_payload(
    monkeypatch,
    db_session,
):
    test_org_id = UUID("00000000-0000-0000-0000-000000000001")
    client = Client(org_id=test_org_id, name="Legacy Strategy V2 Client")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(
        org_id=test_org_id,
        client_id=client.id,
        title="Herbal Safety Handbook",
        product_type="digital",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    campaign = Campaign(
        org_id=test_org_id,
        client_id=client.id,
        product_id=product.id,
        name="Pinned Launch Campaign",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    legacy_reasons = [
        {
            "number": 1,
            "title": "Most Herb Guides Ignore Prescription Drug Interactions",
            "body": "Many guides list benefits without spelling out the medication conflicts that matter most. That leaves readers guessing when the stakes are highest.",
            "image": {"alt": "Open notes beside medication bottles"},
        },
        {
            "number": 2,
            "title": "Scattered Online Info Leaves You Guessing at the Worst Moments",
            "body": "Safety details are buried across tabs, comments, and vague listicles. You need one practical place to check the red flags before you act.",
            "image": {"alt": "Research tabs and handwritten safety notes"},
        },
        {
            "number": 3,
            "title": "The 'Natural Equals Safe' Assumption Is the Core Danger",
            "body": "Natural products can still create serious problems when you mix them casually. A safety-first process keeps you from confusing familiar with harmless.",
            "image": {"alt": "Checklist with highlighted caution markers"},
        },
    ]
    pre_sales_payload_entry = {
        "payload_version": "v1",
        "template_id": "pre-sales-listicle",
        "angle_run_id": "workflow:angle-1",
        "fields": {
            "hero": {
                "title": "Herbalism Without the Woo",
                "subtitle": "A practical read before your next herb and medication decision.",
                "badges": [
                    {
                        "label": "5-Star Reviews",
                        "value": "2,400",
                        "icon": {"alt": "Five-star review icon", "prompt": "clean editorial five-star rating icon"},
                    },
                    {
                        "label": "Customer Support",
                        "value": "24/7",
                        "icon": {"alt": "Customer support icon", "prompt": "editorial customer support headset icon"},
                    },
                    {
                        "label": "Risk Free Trial",
                        "icon": {"alt": "Guarantee badge icon", "prompt": "editorial shield check icon"},
                    },
                ],
            },
            "reasons": legacy_reasons,
            "marquee": ["Medication aware", "No hype", "Safety first"],
            "pitch": {
                "title": "Use one practical framework before you decide",
                "bullets": [
                    "Spot interaction risks faster",
                    "Know when to pause",
                    "Prepare sharper questions",
                    "Keep one reference handy",
                ],
                "cta_label": "Learn more",
                "image": {"alt": "Handbook open beside a cup of tea"},
            },
            "reviews": [],
            "review_wall": {
                "title": "Trusted by careful herbal readers",
                "button_label": "Open full reviews",
            },
            "floating_cta": {"label": "Learn more"},
        },
        "template_patch": [
            {
                "component_type": "PreSalesReasons",
                "field_path": "props.config",
                "value": legacy_reasons,
            }
        ],
    }
    sales_payload_entry = {
        "payload_version": "v1",
        "template_id": "sales-pdp",
        "angle_run_id": "workflow:angle-1",
        "template_patch": [
            {
                "component_type": "SalesPdpHero",
                "field_path": "props.config.purchase.title",
                "value": "Herbal Safety Handbook",
            }
        ],
    }

    @contextmanager
    def _session_scope_override():
        yield db_session

    captured_copy_packs: list[tuple[str | None, dict[str, object]]] = []

    def _run_generate_page_draft_stub(**kwargs):
        copy_pack = kwargs.get("copy_pack")
        assert isinstance(copy_pack, str) and copy_pack
        captured_copy_packs.append(
            (
                kwargs.get("template_id"),
                json.loads(copy_pack),
            )
        )
        return {"draftVersionId": f"draft-{len(captured_copy_packs)}", "generatedImages": []}

    monkeypatch.setattr(cia, "session_scope", _session_scope_override)
    monkeypatch.setattr(
        cia,
        "apply_template_assets",
        lambda **kwargs: kwargs["template"].puck_data,
    )
    monkeypatch.setattr(cia, "resolve_design_system_tokens", lambda **_kwargs: None)
    monkeypatch.setattr(cia, "normalize_public_page_metadata_for_context", lambda **_kwargs: None)
    monkeypatch.setattr(
        cia,
        "_align_sales_pdp_purchase_options_for_selected_offer",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        cia,
        "_build_policy_footer_payload",
        lambda **_kwargs: (
            [
                {"label": "Privacy", "href": "https://example.com/privacy"},
                {"label": "Terms", "href": "https://example.com/terms"},
                {"label": "Returns", "href": "https://example.com/returns"},
                {"label": "Shipping", "href": "https://example.com/shipping"},
            ],
            "© 2026 Test Brand",
            [],
        ),
    )
    monkeypatch.setattr(cia, "run_generate_page_draft", _run_generate_page_draft_stub)

    result = cia.create_funnel_drafts_activity(
        {
            "org_id": str(test_org_id),
            "client_id": str(client.id),
            "campaign_id": str(campaign.id),
            "product_id": str(product.id),
            "experiment_spec_id": "experiment-1",
            "funnel_name": "Launch",
            "pages": [
                {"template_id": "pre-sales-listicle", "name": "Pre-Sales", "slug": "pre-sales"},
                {"template_id": "sales-pdp", "name": "Sales", "slug": "sales"},
            ],
            "experiment": {"id": "experiment-1", "name": "Angle Test", "hypothesis": "Pinned copy wins"},
            "variant": {"id": "variant-a", "name": "Control", "description": "Pinned Strategy V2 copy"},
            "strategy_sheet": {"goal": "Launch", "hypothesis": "Pinned copy"},
            "asset_briefs": [],
            "strategy_v2_packet": {
                "template_payloads": {
                    "pre-sales-listicle": pre_sales_payload_entry,
                    "sales-pdp": sales_payload_entry,
                }
            },
            "strategy_v2_copy_context": {},
            "generate_ai_drafts": False,
            "generate_testimonials": False,
        }
    )

    assert len(result["pages"]) == 2
    assert len(captured_copy_packs) == 2
    pre_sales_copy_pack = next(
        payload for template_id, payload in captured_copy_packs if template_id == "pre-sales-listicle"
    )
    assert len(pre_sales_copy_pack["fields"]["reasons"]) == 3
    assert pre_sales_copy_pack["template_patch"][0]["component_type"] == "PreSalesReasons"
    assert len(pre_sales_copy_pack["template_patch"][0]["value"]) == 3


def test_build_policy_footer_payload_returns_links_brand_year_and_icons(monkeypatch):
    profile = SimpleNamespace(
        privacy_policy_url="https://example.com/privacy",
        terms_of_service_url="https://example.com/terms",
        returns_refunds_policy_url="https://example.com/returns",
        shipping_policy_url="https://example.com/shipping",
        subscription_terms_and_cancellation_url="https://example.com/subscription",
        operating_entity_name="Fallback Entity",
        legal_business_name="Fallback Legal",
        client_id="client-123",
    )
    design_system = SimpleNamespace(tokens={"brand": {"name": "The Honest Herbalist"}})

    @contextmanager
    def _session_scope_override():
        yield object()

    class _ComplianceRepo:
        def __init__(self, _session):
            pass

        def get(self, *, org_id, client_id):
            assert org_id == "org-123"
            assert client_id == "client-123"
            return profile

    class _DesignRepo:
        def __init__(self, _session):
            pass

        def list(self, *, org_id, client_id):
            assert org_id == "org-123"
            assert client_id == "client-123"
            return [design_system]

    monkeypatch.setattr(cia, "session_scope", _session_scope_override)
    monkeypatch.setattr(cia, "ClientComplianceProfilesRepository", _ComplianceRepo)
    monkeypatch.setattr(cia, "DesignSystemsRepository", _DesignRepo)

    links, copyright_text, icon_keys = cia._build_policy_footer_payload(
        org_id="org-123",
        client_id="client-123",
    )

    assert links == [
        {"label": "Privacy", "href": "https://example.com/privacy"},
        {"label": "Terms", "href": "https://example.com/terms"},
        {"label": "Returns", "href": "https://example.com/returns"},
        {"label": "Shipping", "href": "https://example.com/shipping"},
        {"label": "Subscription", "href": "https://example.com/subscription"},
    ]
    assert copyright_text == f"© {datetime.now(timezone.utc).year} The Honest Herbalist"
    assert icon_keys == cia._FOOTER_PAYMENT_ICON_KEYS


@pytest.mark.parametrize(
    ("generate_ai_drafts", "strategy_v2_payload_applied", "expected"),
    [
        (False, False, False),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ],
)
def test_should_run_funnel_ai_processing(
    generate_ai_drafts: bool,
    strategy_v2_payload_applied: bool,
    expected: bool,
):
    assert (
        _should_run_funnel_ai_processing(
            generate_ai_drafts=generate_ai_drafts,
            strategy_v2_payload_applied=strategy_v2_payload_applied,
        )
        is expected
    )


def test_assert_sales_payload_matches_product_type_rejects_digital_helper_text_for_book():
    with pytest.raises(ValueError, match="offer_helper_text"):
        cia._assert_sales_payload_matches_product_type(
            template_id="sales-pdp",
            product_type="book",
            payload_fields={
                "hero": {"primary_cta_label": "Buy the handbook"},
                "whats_inside": {"offer_helper_text": "Instant digital access with printable worksheets."},
            },
        )


def test_assert_sales_payload_matches_product_type_rejects_digital_cta_for_book():
    with pytest.raises(ValueError, match="hero.primary_cta_label"):
        cia._assert_sales_payload_matches_product_type(
            template_id="sales-pdp",
            product_type="book",
            payload_fields={
                "hero": {"primary_cta_label": "Get Instant Access - {price}"},
                "whats_inside": {"offer_helper_text": "Printed handbook with quick-reference pages."},
            },
        )


def test_normalize_sales_payload_for_product_type_keeps_book_helper_text_with_mixed_delivery():
    payload = {
        "hero": {"primary_cta_label": "Buy the handbook"},
        "whats_inside": {
            "offer_helper_text": "Everything ships in one handbook. No apps to download, no subscriptions to manage."
        },
    }

    normalized = cia._normalize_sales_payload_for_product_type(
        template_id="sales-pdp",
        product_type="book",
        payload_fields=payload,
    )

    assert (
        normalized["whats_inside"]["offer_helper_text"]
        == "Everything ships in one handbook. No apps to download, no subscriptions to manage."
    )
    cia._assert_sales_payload_matches_product_type(
        template_id="sales-pdp",
        product_type="book",
        payload_fields=normalized,
    )


def test_assert_sales_payload_matches_product_type_allows_book_plus_digital_bonus_helper_text():
    cia._assert_sales_payload_matches_product_type(
        template_id="sales-pdp",
        product_type="book",
        payload_fields={
            "hero": {"primary_cta_label": "Buy the handbook"},
            "whats_inside": {
                "offer_helper_text": (
                    "One printed handbook shipped to your door plus instant digital access "
                    "to all three bonus tools."
                )
            },
        },
    )


def test_normalize_sales_payload_for_product_type_rewrites_book_cta():
    payload = {
        "hero": {"primary_cta_label": "Get Instant Access - {price}"},
        "whats_inside": {"offer_helper_text": "Printed handbook with quick-reference pages."},
    }

    normalized = cia._normalize_sales_payload_for_product_type(
        template_id="sales-pdp",
        product_type="book",
        payload_fields=payload,
    )

    assert normalized["hero"]["primary_cta_label"] == "Get the Book - {price}"
    cia._assert_sales_payload_matches_product_type(
        template_id="sales-pdp",
        product_type="book",
        payload_fields=normalized,
    )


def test_assert_strategy_v2_offer_product_type_matches_product_rejects_mismatch():
    with pytest.raises(ValueError, match="product_type does not match"):
        cia._assert_strategy_v2_offer_product_type_matches_product(
            product_type="book",
            strategy_v2_packet={"offer": {"selected_variant": {"product_type": "digital"}}},
        )


def test_assert_shopify_launch_readiness_rejects_remote_product_type_mismatch(monkeypatch, db_session):
    test_org_id = UUID("00000000-0000-0000-0000-000000000001")
    client = Client(org_id=test_org_id, name="Book Client")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(
        org_id=test_org_id,
        client_id=client.id,
        title="The Honest Herbalist Handbook",
        product_type="book",
        shopify_product_gid="gid://shopify/Product/123",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    offer = ProductOffer(
        org_id=test_org_id,
        client_id=client.id,
        product_id=product.id,
        name="Book offer",
        business_model="DTC",
    )
    db_session.add(offer)
    db_session.commit()
    db_session.refresh(offer)

    for offer_id, price in (
        ("single_device", 4900),
        ("share_and_save", 7900),
        ("family_bundle", 9900),
    ):
        db_session.add(
            ProductVariant(
                offer_id=offer.id,
                product_id=product.id,
                title=offer_id,
                price=price,
                currency="USD",
                provider="shopify",
                external_price_id=f"gid://shopify/ProductVariant/{offer_id}",
                option_values={"offerId": offer_id},
            )
        )
    db_session.commit()

    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(cia, "session_scope", _session_scope_override)
    monkeypatch.setattr(
        cia,
        "get_client_shopify_connection_status",
        lambda client_id: {"state": "ready", "shopDomain": "example.myshopify.com"},
    )
    monkeypatch.setattr(
        cia,
        "get_client_shopify_product",
        lambda **_kwargs: {
            "productType": "digital",
            "variants": [{"requiresShipping": True}],
        },
    )

    with pytest.raises(ValueError, match="productType"):
        cia._assert_shopify_launch_readiness(
            org_id=str(test_org_id),
            client_id=str(client.id),
            product_id=str(product.id),
            selected_offer_id=str(offer.id),
        )


def test_assert_shopify_launch_readiness_requires_shipping_for_books(monkeypatch, db_session):
    test_org_id = UUID("00000000-0000-0000-0000-000000000001")
    client = Client(org_id=test_org_id, name="Book Client")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(
        org_id=test_org_id,
        client_id=client.id,
        title="The Honest Herbalist Handbook",
        product_type="book",
        shopify_product_gid="gid://shopify/Product/123",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    offer = ProductOffer(
        org_id=test_org_id,
        client_id=client.id,
        product_id=product.id,
        name="Book offer",
        business_model="DTC",
    )
    db_session.add(offer)
    db_session.commit()
    db_session.refresh(offer)

    for offer_id, price in (
        ("single_device", 4900),
        ("share_and_save", 7900),
        ("family_bundle", 9900),
    ):
        db_session.add(
            ProductVariant(
                offer_id=offer.id,
                product_id=product.id,
                title=offer_id,
                price=price,
                currency="USD",
                provider="shopify",
                external_price_id=f"gid://shopify/ProductVariant/{offer_id}",
                option_values={"offerId": offer_id},
            )
        )
    db_session.commit()

    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(cia, "session_scope", _session_scope_override)
    monkeypatch.setattr(
        cia,
        "get_client_shopify_connection_status",
        lambda client_id: {"state": "ready", "shopDomain": "example.myshopify.com"},
    )
    monkeypatch.setattr(
        cia,
        "get_client_shopify_product",
        lambda **_kwargs: {
            "productType": "book",
            "variants": [
                {"requiresShipping": True},
                {"requiresShipping": False},
            ],
        },
    )

    with pytest.raises(ValueError, match="require shipping"):
        cia._assert_shopify_launch_readiness(
            org_id=str(test_org_id),
            client_id=str(client.id),
            product_id=str(product.id),
            selected_offer_id=str(offer.id),
        )
