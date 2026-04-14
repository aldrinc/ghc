import uuid

import pytest
from fastapi.testclient import TestClient

import app.services.funnels as funnels_service
from app.db.models import ClientMedusaConfig, Product


@pytest.fixture(autouse=True)
def fake_media_storage(monkeypatch):
    class _FakeStorage:
        bucket = "test-bucket"

        def build_key(self, *, sha256: str, ext: str, kind: str) -> str:
            return f"{kind}/{sha256}.{ext}"

        def object_exists(self, *, bucket: str, key: str) -> bool:
            return False

        def upload_bytes(
            self, *, bucket: str, key: str, data: bytes, content_type=None, cache_control=None
        ):
            return None

    monkeypatch.setattr(funnels_service, "MediaStorage", _FakeStorage)


def _create_client(api_client: TestClient, *, name: str) -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Pets"})
    assert response.status_code == 201
    return response.json()["id"]


def _create_product(api_client: TestClient, *, client_id: str, title: str) -> str:
    response = api_client.post(
        "/products",
        json={"clientId": client_id, "title": title},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_connected_medusa_workspace(
    db_session, *, client_id: str, product_id: str | None = None
) -> None:
    client_uuid = uuid.UUID(client_id)
    config = ClientMedusaConfig(
        org_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        client_id=client_uuid,
        base_url="https://medusa.example.com",
        admin_api_key_encrypted="test-key",
        connection_status="connected",
    )
    db_session.add(config)
    if product_id:
        product = db_session.query(Product).filter(Product.id == uuid.UUID(product_id)).first()
        if product is not None:
            product.medusa_product_id = "prod_test_medusa"
            db_session.add(product)
    db_session.commit()


def _create_variant(
    api_client: TestClient,
    *,
    product_id: str,
    title: str,
    provider: str,
    external_price_id: str,
    inventory_quantity: int | None = None,
) -> str:
    payload: dict[str, object] = {
        "title": title,
        "price": 9900,
        "currency": "usd",
        "provider": provider,
        "externalPriceId": external_price_id,
    }
    if inventory_quantity is not None:
        payload["inventoryQuantity"] = inventory_quantity
    response = api_client.post(f"/products/{product_id}/variants", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def test_list_storefront_templates_exposes_generalized_templates(api_client: TestClient):
    response = api_client.get("/storefront/templates")

    assert response.status_code == 200
    payload = response.json()
    template_ids = {item["id"] for item in payload}
    assert {"sales-pdp", "pre-sales-listicle"}.issubset(template_ids)

    sales_template = next(item for item in payload if item["id"] == "sales-pdp")
    assert sales_template["family"] == "sales-pdp"
    assert sales_template["pageType"] == "product_detail"
    assert "checkout_action" in sales_template["requiredBindingKeys"]


def test_get_storefront_template_detail_returns_binding_and_style_metadata(api_client: TestClient):
    response = api_client.get("/storefront/templates/pre-sales-listicle")

    assert response.status_code == 200
    payload = response.json()
    assert payload["family"] == "listicle-presell"
    assert payload["variant"] == "editorial-proof"
    assert payload["importProvenance"]["sourceTemplateId"] == "pre-sales-listicle"
    assert payload["stylePolicy"]["lockedTokenGroups"]
    assert any(binding["key"] == "checkout_action" for binding in payload["requiredBindings"])


def test_binding_preview_marks_medusa_variant_ready(api_client: TestClient):
    client_id = _create_client(api_client, name="Storefront Medusa Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Puppy Pads")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Starter Pack",
        provider="medusa",
        external_price_id="medusa_variant_123",
        inventory_quantity=24,
    )

    response = api_client.get(
        f"/storefront/templates/sales-pdp/binding-preview?clientId={client_id}&productId={product_id}&variantId={variant_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    checkout_requirement = next(
        requirement
        for requirement in payload["requirements"]
        if requirement["key"] == "checkout_action"
    )
    assert checkout_requirement["status"] == "ready"
    assert payload["variantProvider"] == "medusa"


def test_binding_preview_marks_non_medusa_checkout_as_unsupported(api_client: TestClient):
    client_id = _create_client(api_client, name="Storefront Shopify Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Reusable Pad")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Core Pack",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
        inventory_quantity=12,
    )

    response = api_client.get(
        f"/storefront/templates/sales-pdp/binding-preview?clientId={client_id}&productId={product_id}&variantId={variant_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    checkout_requirement = next(
        requirement
        for requirement in payload["requirements"]
        if requirement["key"] == "checkout_action"
    )
    assert checkout_requirement["status"] == "unsupported"
    assert "Medusa-managed variant" in checkout_requirement["detail"]


def test_create_draft_from_template_succeeds_with_medusa_ready_variant(
    api_client: TestClient, db_session
):
    """Test creating a draft from a built-in template with a Medusa-ready variant."""
    client_id = _create_client(api_client, name="Template Draft Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Premium Product")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Premium Variant",
        provider="medusa",
        external_price_id="medusa_variant_premium",
        inventory_quantity=100,
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "My Sales PDP Draft",
            "productId": product_id,
            "variantId": variant_id,
            "reviewNotes": "Initial draft from template",
        },
    )

    assert response.status_code == 201
    payload = response.json()

    # Check variant response
    assert "variant" in payload
    variant = payload["variant"]
    assert variant["name"] == "My Sales PDP Draft"
    assert variant["family"] == "sales-pdp"
    assert variant["pageType"] == "product_detail"
    assert variant["status"] == "draft"
    assert variant["siteImportId"] is None  # No site import for template drafts

    # Check provenance
    provenance = variant["provenance"]
    assert provenance["source_type"] == "storefront_template"
    assert provenance["template_id"] == "sales-pdp"
    assert provenance["template_family"] == "sales-pdp"
    assert provenance["template_page_type"] == "product_detail"
    assert "synthesis" in provenance
    assert "synthesized_puck_data" in provenance["synthesis"]

    # Check binding context in provenance
    assert provenance["product_id"] == product_id
    assert provenance["variant_id"] == variant_id
    assert provenance["variant_provider"] == "medusa"

    # Check events
    assert "events" in provenance
    events = provenance["events"]
    assert len(events) >= 1
    template_draft_event = next((e for e in events if e["event_type"] == "template_draft"), None)
    assert template_draft_event is not None
    assert template_draft_event["metadata"]["template_id"] == "sales-pdp"
    assert template_draft_event["metadata"]["product_id"] == product_id
    assert template_draft_event["metadata"]["variant_id"] == variant_id

    # Check synthesized puckData in extended response
    assert variant["synthesizedPuckData"] is not None

    # Check binding preview in response
    assert "bindingPreview" in payload
    binding_preview = payload["bindingPreview"]
    assert binding_preview["ready"] is True
    assert binding_preview["variantProvider"] == "medusa"


def test_create_draft_from_template_fails_with_non_medusa_variant(api_client: TestClient):
    """Test that creating a draft fails with a non-Medusa variant."""
    client_id = _create_client(api_client, name="Template Draft Non-Medusa Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Shopify Product")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Shopify Variant",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/999",
        inventory_quantity=50,
    )

    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "Should Fail",
            "productId": product_id,
            "variantId": variant_id,
        },
    )

    assert response.status_code == 400
    error_detail = response.json()["detail"]
    assert "binding requirements not ready" in error_detail.lower()


def test_create_draft_from_template_fails_without_variant(api_client: TestClient):
    """Test that creating a draft fails without a variant selected."""
    import uuid

    client_id = _create_client(api_client, name="Template Draft No Variant Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Product Without Variant")
    # Use a valid UUID format that doesn't exist
    non_existent_variant_id = str(uuid.uuid4())

    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "Should Fail",
            "productId": product_id,
            "variantId": non_existent_variant_id,
        },
    )

    assert response.status_code == 404  # Variant not found


def test_create_draft_from_template_creates_style_preset(api_client: TestClient, db_session):
    """Test that creating a draft from template creates a style preset with meaningful tokens."""
    client_id = _create_client(api_client, name="Template Draft Style Preset Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Style Test Product")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Style Test Variant",
        provider="medusa",
        external_price_id="medusa_style_test",
        inventory_quantity=10,
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "Style Preset Test Draft",
            "productId": product_id,
            "variantId": variant_id,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    variant = payload["variant"]

    # Style preset should be linked
    assert variant["stylePresetId"] is not None

    # Verify we can fetch the variant and it has the style preset
    variant_id_response = variant["id"]
    variant_detail_response = api_client.get(
        f"/storefront/templates/variants/{variant_id_response}?clientId={client_id}"
    )
    assert variant_detail_response.status_code == 200
    variant_detail = variant_detail_response.json()
    assert variant_detail["stylePresetId"] == variant["stylePresetId"]

    # Fetch governance to verify style preset tokens are valid
    governance_response = api_client.get(
        f"/storefront/templates/variants/{variant_id_response}/governance?clientId={client_id}"
    )
    assert governance_response.status_code == 200
    governance = governance_response.json()

    # Style audit should pass (tokens should have palette and fonts)
    assert governance["styleAudit"] is not None
    assert governance["styleAudit"]["passed"] is True, (
        f"Style audit failed: {governance['styleAudit']['findings']}"
    )

    # Check that there are no blockers related to missing token groups
    token_blockers = [
        b
        for b in governance["blockers"]
        if "token" in b.lower() or "palette" in b.lower() or "fonts" in b.lower()
    ]
    assert len(token_blockers) == 0, f"Token blockers found: {token_blockers}"


def test_create_draft_from_template_with_pre_sales_listicle(api_client: TestClient, db_session):
    """Test creating a draft from the pre-sales listicle template."""
    client_id = _create_client(api_client, name="Pre-sales Template Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Pre-sales Product")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Pre-sales Variant",
        provider="medusa",
        external_price_id="medusa_presales",
        inventory_quantity=25,
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    response = api_client.post(
        f"/storefront/templates/pre-sales-listicle/drafts?clientId={client_id}",
        json={
            "name": "My Pre-sales Draft",
            "productId": product_id,
            "variantId": variant_id,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    variant = payload["variant"]

    assert variant["name"] == "My Pre-sales Draft"
    assert variant["family"] == "listicle-presell"
    assert variant["pageType"] == "pre_sell"
    assert variant["provenance"]["template_id"] == "pre-sales-listicle"


def test_create_draft_from_template_with_missing_inventory_fails(
    api_client: TestClient, db_session
):
    """Test that creating a draft fails when inventory is missing for sales-pdp template."""
    client_id = _create_client(api_client, name="Missing Inventory Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="No Inventory Product")
    # Create variant without inventory
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="No Inventory Variant",
        provider="medusa",
        external_price_id="medusa_no_inv",
        # No inventory_quantity
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "Should Fail - No Inventory",
            "productId": product_id,
            "variantId": variant_id,
        },
    )

    # Should fail because inventory binding is required for sales-pdp
    assert response.status_code == 400
    error_detail = response.json()["detail"].lower()
    assert "inventory" in error_detail or "not ready" in error_detail


def test_variant_summary_exposes_source_type(api_client: TestClient, db_session):
    """Test that variant summaries expose sourceType for UI filtering."""
    client_id = _create_client(api_client, name="Source Type Summary Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Source Type Product")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Source Type Variant",
        provider="medusa",
        external_price_id="medusa_source_type",
        inventory_quantity=50,
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    # Create a draft from template
    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "Source Type Test Draft",
            "productId": product_id,
            "variantId": variant_id,
        },
    )
    assert response.status_code == 201

    # List variants and check sourceType is exposed
    list_response = api_client.get(f"/storefront/templates/variants?clientId={client_id}")
    assert list_response.status_code == 200
    variants = list_response.json()

    # Find our created variant
    created_variant = next((v for v in variants if v["name"] == "Source Type Test Draft"), None)
    assert created_variant is not None

    # Check sourceType is exposed
    assert "sourceType" in created_variant
    assert created_variant["sourceType"] == "storefront_template"


def test_create_draft_hydrates_product_context(api_client: TestClient, db_session):
    """Test that created draft puckData is hydrated with product/variant context."""
    client_id = _create_client(api_client, name="Hydration Test Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Custom Product Name")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Custom Variant",
        provider="medusa",
        external_price_id="medusa_hydration_test",
        inventory_quantity=100,
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "Hydration Test Draft",
            "productId": product_id,
            "variantId": variant_id,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    variant = payload["variant"]

    # Get the synthesized puckData from provenance
    provenance = variant["provenance"]
    synthesized_puck_data = provenance.get("synthesis", {}).get("synthesized_puck_data")

    assert synthesized_puck_data is not None, "synthesizedPuckData should be present"

    # Check that PuppyPad references have been replaced with product name
    # The puckData should not contain "PuppyPad" in obvious places
    content = synthesized_puck_data.get("content", [])

    # Find hero section and check title
    hero_title = None
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpHero":
                    purchase = child.get("props", {}).get("config", {}).get("purchase", {})
                    hero_title = purchase.get("title")
                    break

    # The hero title should contain the product name, not PuppyPad
    assert hero_title is not None, "Hero title should be present"
    assert "PuppyPad" not in hero_title, f"Hero title should not contain 'PuppyPad': {hero_title}"
    assert "Custom Product Name" in hero_title, (
        f"Hero title should contain product name: {hero_title}"
    )

    offer_title = None
    offer_price = None
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpHero":
                    offer_options = (
                        child.get("props", {})
                        .get("config", {})
                        .get("purchase", {})
                        .get("offer", {})
                        .get("options", [])
                    )
                    if offer_options:
                        offer_title = offer_options[0].get("title")
                        offer_price = offer_options[0].get("price")
                    break

    assert offer_title == "Custom Variant"
    assert offer_price == 99


def test_create_draft_materializes_assets(api_client: TestClient, db_session):
    """Test that created draft puckData attempts to materialize assets."""
    client_id = _create_client(api_client, name="Asset Materialization Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Asset Test Product")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Asset Test Variant",
        provider="medusa",
        external_price_id="medusa_asset_test",
        inventory_quantity=50,
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    response = api_client.post(
        f"/storefront/templates/sales-pdp/drafts?clientId={client_id}",
        json={
            "name": "Asset Materialization Test Draft",
            "productId": product_id,
            "variantId": variant_id,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    variant = payload["variant"]

    # Get the synthesized puckData from provenance
    provenance = variant["provenance"]
    synthesized_puck_data = provenance.get("synthesis", {}).get("synthesized_puck_data")

    assert synthesized_puck_data is not None, "synthesizedPuckData should be present"

    # Check that the puckData structure is correct
    # The template should have content blocks
    content = synthesized_puck_data.get("content", [])
    assert len(content) > 0, "puckData should have content blocks"

    # Find the SalesPdpPage block
    sales_pdp_page = None
    for block in content:
        if block.get("type") == "SalesPdpPage":
            sales_pdp_page = block
            break

    assert sales_pdp_page is not None, "Should have SalesPdpPage block"

    # Check that the page has content with blocks
    page_content = sales_pdp_page.get("props", {}).get("content", [])
    assert len(page_content) > 0, "SalesPdpPage should have content blocks"

    # Verify that the template structure is preserved
    # The hero block should have config with purchase section
    hero_block = None
    for block in page_content:
        if block.get("type") == "SalesPdpHero":
            hero_block = block
            break

    assert hero_block is not None, "Should have SalesPdpHero block"

    # Check that purchase config exists
    purchase = hero_block.get("props", {}).get("config", {}).get("purchase", {})
    assert "title" in purchase, "Purchase should have title"
    assert "offer" in purchase, "Purchase should have offer section"

    # The offer should have options
    offer_options = purchase.get("offer", {}).get("options", [])
    assert len(offer_options) > 0, "Offer should have options"
    first_image = offer_options[0].get("image", {})
    assert first_image.get("assetPublicId"), "Offer image should have a materialized assetPublicId"


def test_create_presales_draft_hydrates_hero_title(api_client: TestClient, db_session):
    """Test that created pre-sales draft has hydrated hero title."""
    client_id = _create_client(api_client, name="Presales Hydration Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="My Amazing Product")
    variant_id = _create_variant(
        api_client,
        product_id=product_id,
        title="Presales Variant",
        provider="medusa",
        external_price_id="medusa_presales_test",
        inventory_quantity=25,
    )
    _seed_connected_medusa_workspace(db_session, client_id=client_id, product_id=product_id)

    response = api_client.post(
        f"/storefront/templates/pre-sales-listicle/drafts?clientId={client_id}",
        json={
            "name": "Presales Hydration Test",
            "productId": product_id,
            "variantId": variant_id,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    variant = payload["variant"]

    # Get the synthesized puckData from provenance
    provenance = variant["provenance"]
    synthesized_puck_data = provenance.get("synthesis", {}).get("synthesized_puck_data")

    assert synthesized_puck_data is not None, "synthesizedPuckData should be present"

    # Find hero title in pre-sales template
    content = synthesized_puck_data.get("content", [])
    hero_title = None

    for block in content:
        if block.get("type") == "PreSalesPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "PreSalesHero":
                    hero = child.get("props", {}).get("config", {}).get("hero", {})
                    hero_title = hero.get("title")
                    break

    # The hero title should not contain "PuppyPad" as the main product reference
    assert hero_title is not None, "Hero title should be present"
    # PuppyPad should be replaced with the product name
    assert "PuppyPad" not in hero_title or "My Amazing Product" in hero_title, (
        f"Hero title should not have PuppyPad as main reference: {hero_title}"
    )
