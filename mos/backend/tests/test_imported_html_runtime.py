import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import settings
from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum
from app.db.models import Client, Funnel, FunnelPage, FunnelPageVersion, Product
from app.db.models import ProductVariant
from app.services.imported_html_runtime import (
    ImportedHtmlRuntimeValidationError,
    imported_html_instrumentation_schema,
    resolve_funnel_page_stage,
    validate_imported_html_document_manifest,
)
from app.services.deploy import build_client_funnel_runtime_artifact_payload
from app.services.funnels import publish_funnel
from tests.conftest import TEST_ORG_ID


def test_validate_imported_html_document_manifest_accepts_sales_checkout_binding():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <button id="buy-now">Start my protocol</button>
      </body>
    </html>
    """
    variant = ProductVariant(
        product_id="product-1",
        title="Default",
        price=4900,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    variant.id = "variant-1"
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "sales",
        "pageStage": "sales",
        "bindings": [
            {
                "id": "primary-buy",
                "type": "checkout",
                "selector": "#buy-now",
                "event": "click",
                "trackEventType": "sales_to_checkout_click",
                "checkout": {
                    "mode": "public_checkout",
                    "variantResolver": {"type": "fixed", "variantId": "variant-1"},
                },
            }
        ],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="sales",
        current_page_id="page-sales",
        available_target_page_ids={"page-sales"},
        checkout_ready_variants=[variant],
        require_stage_bindings=True,
    )

    assert normalized["bindings"][0]["checkout"]["variantResolver"]["variantId"] == "variant-1"


def test_validate_imported_html_document_manifest_requires_quiz_answer_metadata():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <section id="lead">Lead</section>
        <section id="q1">Question one</section>
        <button id="o1">Often</button>
        <a id="to-sales">Continue</a>
      </body>
    </html>
    """
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "quiz",
        "pageStage": "pre_sales",
        "quizId": "test-quiz",
        "quizVersion": "v1",
        "quizVariant": "control",
        "quizLeads": [{"id": "lead", "selector": "#lead"}],
        "quizQuestions": [
            {
                "id": "q1",
                "selector": "#q1",
                "questionId": "q1",
                "questionText": "Question one",
                "questionIndex": 1,
                "questionType": "single_select",
            }
        ],
        "quizOptions": [
            {
                "id": "o1",
                "selector": "#o1",
                "questionId": "q1",
                "optionId": "o1",
                "optionText": "Often",
                "optionIndex": 1,
                "selectionOrder": 1,
                "submitOnSelect": True,
            }
        ],
        "ctas": [{"id": "to-sales", "selector": "#to-sales", "ctaPosition": 1}],
        "bindings": [
            {
                "id": "to-sales",
                "type": "internal_navigation",
                "selector": "#to-sales",
                "targetPageId": "page-sales",
                "trackEventType": "pre_sales_to_sales_click",
            }
        ],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="pre_sales",
        current_page_id="page-quiz",
        next_page_id="page-sales",
        available_target_page_ids={"page-quiz", "page-sales"},
        checkout_ready_variants=[],
        require_stage_bindings=True,
    )

    assert normalized["quizQuestions"][0]["questionText"] == "Question one"
    assert normalized["quizOptions"][0]["selectionOrder"] == 1

    missing_text_manifest = json.loads(json.dumps(manifest))
    del missing_text_manifest["quizOptions"][0]["optionText"]
    with pytest.raises(ImportedHtmlRuntimeValidationError, match="optionText"):
        validate_imported_html_document_manifest(
            html_document=html_document,
            instrumentation_manifest=missing_text_manifest,
            current_page_stage="pre_sales",
            current_page_id="page-quiz",
            next_page_id="page-sales",
            available_target_page_ids={"page-quiz", "page-sales"},
            checkout_ready_variants=[],
            require_stage_bindings=True,
        )

    missing_selection_manifest = json.loads(json.dumps(manifest))
    del missing_selection_manifest["quizOptions"][0]["selectionOrder"]
    with pytest.raises(ImportedHtmlRuntimeValidationError, match="selectionOrder"):
        validate_imported_html_document_manifest(
            html_document=html_document,
            instrumentation_manifest=missing_selection_manifest,
            current_page_stage="pre_sales",
            current_page_id="page-quiz",
            next_page_id="page-sales",
            available_target_page_ids={"page-quiz", "page-sales"},
            checkout_ready_variants=[],
            require_stage_bindings=True,
        )


def test_validate_imported_html_document_manifest_accepts_custom_content_page():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <main>
          <h1>About Tenor</h1>
          <p>Company content copied from a published footer page.</p>
        </main>
      </body>
    </html>
    """
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "custom",
        "pageStage": "custom",
        "bindings": [],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="custom",
        current_page_id="page-about",
        available_target_page_ids={"page-about"},
        checkout_ready_variants=[],
        require_stage_bindings=False,
    )

    assert normalized["htmlArtifactKind"] == "custom"
    assert normalized["pageStage"] == "custom"


def test_validate_imported_html_document_manifest_accepts_sales_add_to_cart_target():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <button id="add-to-cart">Try it now</button>
        <button id="secure-checkout">Secure checkout</button>
      </body>
    </html>
    """
    variant = ProductVariant(
        product_id="product-1",
        title="Default",
        price=4900,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    variant.id = "variant-1"
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "sales",
        "pageStage": "sales",
        "addToCartTargets": [
            {
                "id": "primary-add-to-cart",
                "selector": "#add-to-cart",
                "event": "click",
                "trackEventType": "add_to_cart",
                "label": "Primary add to cart",
            }
        ],
        "bindings": [
            {
                "id": "secure-checkout",
                "type": "checkout",
                "selector": "#secure-checkout",
                "event": "click",
                "trackEventType": "sales_to_checkout_click",
                "checkout": {
                    "mode": "public_checkout",
                    "variantResolver": {"type": "fixed", "variantId": "variant-1"},
                },
            }
        ],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="sales",
        current_page_id="page-sales",
        available_target_page_ids={"page-sales"},
        checkout_ready_variants=[variant],
        require_stage_bindings=True,
    )

    assert normalized["addToCartTargets"][0]["trackEventType"] == "add_to_cart"
    assert normalized["bindings"][0]["selector"] == "#secure-checkout"


def test_validate_imported_html_document_manifest_accepts_checkout_started_binding():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <button id="secure-checkout">Secure checkout</button>
      </body>
    </html>
    """
    variant = ProductVariant(
        product_id="product-1",
        title="Default",
        price=4900,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    variant.id = "variant-1"
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "sales",
        "pageStage": "sales",
        "bindings": [
            {
                "id": "secure-checkout",
                "type": "checkout",
                "selector": "#secure-checkout",
                "event": "click",
                "trackEventType": "checkout_started",
                "checkout": {
                    "mode": "public_checkout",
                    "variantResolver": {"type": "fixed", "variantId": "variant-1"},
                },
            }
        ],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="sales",
        current_page_id="page-sales",
        available_target_page_ids={"page-sales"},
        checkout_ready_variants=[variant],
        require_stage_bindings=True,
    )

    assert normalized["bindings"][0]["trackEventType"] == "checkout_started"


def test_validate_imported_html_document_manifest_accepts_checkout_binding_matching_multiple_ctas():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <a class="buy-cta" href="#">Try Ember Today</a>
        <a class="buy-cta" href="#">Try Ember Today</a>
      </body>
    </html>
    """
    variant = ProductVariant(
        product_id="product-1",
        title="Default",
        price=4900,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    variant.id = "variant-1"
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "sales",
        "pageStage": "sales",
        "bindings": [
            {
                "id": "all-buy-ctas",
                "type": "checkout",
                "selector": "a.buy-cta",
                "event": "click",
                "trackEventType": "sales_to_checkout_click",
                "checkout": {
                    "mode": "public_checkout",
                    "variantResolver": {"type": "fixed", "variantId": "variant-1"},
                },
            }
        ],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="sales",
        current_page_id="page-sales",
        available_target_page_ids={"page-sales"},
        checkout_ready_variants=[variant],
        require_stage_bindings=True,
    )

    assert normalized["bindings"][0]["selector"] == "a.buy-cta"


def test_validate_imported_html_document_manifest_accepts_rmbc_view_targets():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <section id="hero"><a id="hero-cta" href="#">Try it now</a></section>
        <section id="proof">1,000+ reviews</section>
      </body>
    </html>
    """
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "listicle",
        "pageStage": "pre_sales",
        "sections": [
            {"id": "hero", "selector": "#hero", "label": "Hero"},
        ],
        "proofs": [
            {"id": "reviews", "selector": "#proof", "proofType": "social_proof", "sectionId": "hero"},
        ],
        "ctas": [
            {"id": "hero-cta", "selector": "#hero-cta", "ctaPosition": 1},
        ],
        "bindings": [
            {
                "id": "hero-to-sales",
                "type": "internal_navigation",
                "selector": "#hero-cta",
                "event": "click",
                "targetPageId": "page-sales",
                "trackEventType": "pre_sales_to_sales_click",
            }
        ],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="pre_sales",
        current_page_id="page-presales",
        available_target_page_ids={"page-sales"},
        checkout_ready_variants=[],
        require_stage_bindings=True,
    )

    assert normalized["sections"][0]["id"] == "hero"
    assert normalized["proofs"][0]["proofType"] == "social_proof"
    assert normalized["ctas"][0]["ctaPosition"] == 1


def test_validate_imported_html_document_manifest_allows_purchase_mode_checkout_context():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <button id="buy-now">Start my protocol</button>
        <input id="mos-selected-pack" value="2x" />
        <input id="mos-selected-purchase-mode" value="subscribe" />
      </body>
    </html>
    """
    variant = ProductVariant(
        product_id="product-1",
        title="2 Pack",
        price=7800,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    variant.id = "variant-1"
    variant.option_values = {"Pack": "2x"}
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "sales",
        "pageStage": "sales",
        "bindings": [
            {
                "id": "primary-buy",
                "type": "checkout",
                "selector": "#buy-now",
                "event": "click",
                "trackEventType": "sales_to_checkout_click",
                "checkout": {
                    "mode": "public_checkout",
                    "variantResolver": {
                        "type": "option_values",
                        "optionSelectors": [
                            {"name": "Pack", "selector": "#mos-selected-pack", "source": "value"},
                            {
                                "name": "PurchaseMode",
                                "selector": "#mos-selected-purchase-mode",
                                "source": "value",
                            },
                        ],
                    },
                },
            }
        ],
    }

    normalized = validate_imported_html_document_manifest(
        html_document=html_document,
        instrumentation_manifest=manifest,
        current_page_stage="sales",
        current_page_id="page-sales",
        available_target_page_ids={"page-sales"},
        checkout_ready_variants=[variant],
        require_stage_bindings=True,
    )

    assert normalized["bindings"][0]["checkout"]["variantResolver"]["optionSelectors"][1]["name"] == "PurchaseMode"


def test_validate_imported_html_document_manifest_rejects_unsupported_selector():
    html_document = """
    <!doctype html>
    <html>
      <body>
        <a class="cta primary">Continue</a>
      </body>
    </html>
    """
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": "listicle",
        "pageStage": "pre_sales",
        "bindings": [
            {
                "id": "to-sales",
                "type": "internal_navigation",
                "selector": "main .cta",
                "event": "click",
                "targetPageId": "page-sales",
                "trackEventType": "pre_sales_to_sales_click",
            }
        ],
    }

    try:
        validate_imported_html_document_manifest(
            html_document=html_document,
            instrumentation_manifest=manifest,
            current_page_stage="pre_sales",
            current_page_id="page-pre",
            next_page_id="page-sales",
            available_target_page_ids={"page-pre", "page-sales"},
            require_stage_bindings=True,
        )
    except ImportedHtmlRuntimeValidationError as exc:
        assert "Supported selector syntax" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected unsupported selector validation to fail.")


def test_local_sales_omni_template_manifest_validates():
    template_path = Path(__file__).resolve().parents[1] / "app/templates/funnels/sales_omni_template.json"
    payload = json.loads(template_path.read_text())
    props = payload["puckData"]["content"][0]["props"]

    variant = ProductVariant(
        product_id="product-1",
        title="3 Pack Watermelon",
        price=8900,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    variant.id = "33333333-3333-3333-3333-333333333333"
    variant.option_values = {"Pack": "3x", "Flavor": "watermelon"}

    normalized = validate_imported_html_document_manifest(
        html_document=props["htmlDocument"],
        instrumentation_manifest=props["instrumentationManifest"],
        current_page_stage="sales",
        current_page_id="11111111-1111-1111-1111-111111111111",
        available_target_page_ids={"11111111-1111-1111-1111-111111111111"},
        checkout_ready_variants=[variant],
        require_stage_bindings=True,
    )

    assert len(normalized["bindings"]) == 2


def test_local_presales_omni_template_manifest_validates():
    template_path = Path(__file__).resolve().parents[1] / "app/templates/funnels/presales_omni_template.json"
    payload = json.loads(template_path.read_text())
    props = payload["puckData"]["content"][0]["props"]
    manifest = props["instrumentationManifest"]
    target_page_ids = {binding["targetPageId"] for binding in manifest["bindings"]}
    next_page_id = next(iter(target_page_ids))

    normalized = validate_imported_html_document_manifest(
        html_document=props["htmlDocument"],
        instrumentation_manifest=manifest,
        current_page_stage="pre_sales",
        current_page_id="44444444-4444-4444-4444-444444444444",
        next_page_id=next_page_id,
        available_target_page_ids={"44444444-4444-4444-4444-444444444444", next_page_id},
        checkout_ready_variants=[],
        require_stage_bindings=True,
    )

    assert len(normalized["bindings"]) == 2


def test_resolve_funnel_page_stage_prefers_template_id():
    assert resolve_funnel_page_stage(template_id="sales-pdp") == "sales"
    assert resolve_funnel_page_stage(template_id="pre-sales-listicle") == "pre_sales"


def test_imported_html_instrumentation_schema_is_embeddable():
    schema = imported_html_instrumentation_schema()

    def _walk(node):
        if isinstance(node, dict):
            assert "$defs" not in node
            assert "$ref" not in node
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)


def test_publish_funnel_rejects_imported_html_without_manifest(db_session):
    client = Client(org_id=TEST_ORG_ID, name="Test Client", industry="Wellness")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(org_id=TEST_ORG_ID, client_id=client.id, title="Ember")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    funnel = Funnel(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        name="Imported HTML Funnel",
        route_slug="imported-html-publish",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    page = FunnelPage(
        funnel_id=funnel.id,
        name="Sales Page",
        slug="sales",
        template_id="sales-pdp",
    )
    db_session.add(page)
    db_session.commit()
    db_session.refresh(page)

    funnel.entry_page_id = page.id
    db_session.add(funnel)

    variant = ProductVariant(
        product_id=product.id,
        title="Default",
        price=4900,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    db_session.add(variant)
    db_session.commit()
    db_session.refresh(variant)
    db_session.add(
        FunnelPageVersion(
            id=uuid4(),
            page_id=page.id,
            status=FunnelPageVersionStatusEnum.draft,
            puck_data={
                "root": {"props": {"title": "Imported HTML"}},
                "content": [
                    {
                        "type": "ImportedHtmlDocument",
                        "props": {
                            "id": "imported-html-document",
                            "title": "Imported HTML",
                            "htmlDocument": "<!doctype html><html><body><button id='buy-now'>Buy</button></body></html>",
                        },
                    }
                ],
                "zones": {},
            },
            source=FunnelPageVersionSourceEnum.human,
            ai_metadata=None,
        )
    )
    db_session.commit()

    with pytest.raises(ValueError, match="runtime validation failed"):
        publish_funnel(
            session=db_session,
            org_id=str(TEST_ORG_ID),
            user_id="test-user",
            funnel_id=str(funnel.id),
        )


def test_deploy_artifact_includes_tracking_and_stage_map_for_imported_html(db_session, monkeypatch):
    monkeypatch.setattr(settings, "POSTHOG_FUNNELS_ENABLED", True)
    monkeypatch.setattr(settings, "POSTHOG_FUNNELS_PROJECT_API_KEY", "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk")
    monkeypatch.setattr(settings, "POSTHOG_FUNNELS_API_HOST", "https://us.i.posthog.com")
    monkeypatch.setattr(settings, "POSTHOG_FUNNELS_DEFAULTS", "2026-01-30")
    monkeypatch.setattr(settings, "POSTHOG_FUNNELS_PERSON_PROFILES", "identified_only")

    client = Client(org_id=TEST_ORG_ID, name="Deploy Client", industry="Wellness")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(org_id=TEST_ORG_ID, client_id=client.id, title="Ember")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    funnel = Funnel(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        name="Deployable Imported HTML Funnel",
        route_slug="deployable-imported-html",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    page = FunnelPage(
        funnel_id=funnel.id,
        name="Sales Page",
        slug="sales",
        template_id="sales-pdp",
    )
    db_session.add(page)
    db_session.commit()
    db_session.refresh(page)

    funnel.entry_page_id = page.id
    db_session.add(funnel)

    variant = ProductVariant(
        product_id=product.id,
        title="Default",
        price=4900,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
    )
    db_session.add(variant)
    db_session.commit()
    db_session.refresh(variant)
    db_session.add(
        FunnelPageVersion(
            id=uuid4(),
            page_id=page.id,
            status=FunnelPageVersionStatusEnum.draft,
            puck_data={
                "root": {"props": {"title": "Imported HTML"}},
                "content": [
                    {
                        "type": "ImportedHtmlDocument",
                        "props": {
                            "id": "imported-html-document",
                            "title": "Imported HTML",
                            "htmlDocument": "<!doctype html><html><body><button id='buy-now'>Buy</button></body></html>",
                            "instrumentationManifest": {
                                "schemaVersion": "html-deploy-v1",
                                "htmlArtifactKind": "sales",
                                "pageStage": "sales",
                                "bindings": [
                                    {
                                        "id": "primary-buy",
                                        "type": "checkout",
                                        "selector": "#buy-now",
                                        "event": "click",
                                        "trackEventType": "sales_to_checkout_click",
                                        "checkout": {
                                            "mode": "public_checkout",
                                            "variantResolver": {
                                                "type": "fixed",
                                                "variantId": str(variant.id),
                                            },
                                        },
                                    }
                                ],
                            },
                        },
                    }
                ],
                "zones": {},
            },
            source=FunnelPageVersionSourceEnum.human,
            ai_metadata=None,
        )
    )
    db_session.commit()

    publication = publish_funnel(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        user_id="test-user",
        funnel_id=str(funnel.id),
    )
    payload = build_client_funnel_runtime_artifact_payload(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        client_id=str(client.id),
        updated_from_funnel_id=str(funnel.id),
        updated_from_publication_id=str(publication.id),
    )

    sales_page = payload["products"][str(product.id)[:8]]["funnels"][funnel.route_slug]["pages"]["sales"]
    assert sales_page["stage"] == "sales"
    assert sales_page["pageStageMap"][str(page.id)] == "sales"
    assert "tracking" in sales_page
    assert sales_page["tracking"] == {
        "provider": "posthog",
        "mode": "public_funnel_runtime",
        "posthogProjectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
        "posthogApiHost": "https://us.i.posthog.com",
        "posthogDefaults": "2026-01-30",
        "posthogPersonProfiles": "identified_only",
    }
