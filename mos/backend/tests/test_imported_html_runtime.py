from uuid import uuid4

import pytest

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
        "schemaVersion": "imported-html-instrumentation-v1",
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
        "schemaVersion": "imported-html-instrumentation-v1",
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
        "schemaVersion": "imported-html-instrumentation-v1",
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


def test_deploy_artifact_includes_tracking_and_stage_map_for_imported_html(db_session):
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
                                "schemaVersion": "imported-html-instrumentation-v1",
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
