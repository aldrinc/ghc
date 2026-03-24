"""Tests for the Sites API endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import Client, Funnel, FunnelPage, FunnelPageVersion, Product


@pytest.fixture(autouse=True)
def _fake_media_storage(monkeypatch):
    """Patch MediaStorage to avoid S3 calls during tests."""
    import app.services.funnels as funnels_service

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
    """Create a test client/workspace."""
    response = api_client.post("/clients", json={"name": name, "industry": "Ecommerce"})
    assert response.status_code == 201
    return response.json()["id"]


def _create_product(api_client: TestClient, *, client_id: str, title: str) -> str:
    """Create a test product."""
    response = api_client.post(
        "/products",
        json={"clientId": client_id, "title": title},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_list_site_families_returns_medusa_b2b_starter(api_client: TestClient):
    """Test that listing site families includes the medusa-b2b-starter family."""
    response = api_client.get("/sites/families")

    assert response.status_code == 200
    families = response.json()
    family_ids = {f["family"] for f in families}

    assert "medusa-b2b-starter" in family_ids

    # Verify the medusa-b2b-starter family has expected properties
    medusa_family = next(f for f in families if f["family"] == "medusa-b2b-starter")
    assert medusa_family["name"] == "Medusa B2B Starter"
    assert medusa_family["siteType"] == "ecommerce"
    assert medusa_family["commerceProvider"] == "medusa"
    assert medusa_family["pageCount"] == 5  # home, category, pdp, cart, checkout


def test_get_site_family_detail_returns_page_blueprints(api_client: TestClient):
    """Test that getting a site family detail returns all page blueprints."""
    response = api_client.get("/sites/families/medusa-b2b-starter")

    assert response.status_code == 200
    family = response.json()

    assert family["family"] == "medusa-b2b-starter"
    assert family["name"] == "Medusa B2B Starter"
    assert len(family["pageBlueprints"]) == 5

    # Verify page types - commerce-core pages only
    page_types = {bp["pageType"] for bp in family["pageBlueprints"]}
    expected_page_types = {
        "home",
        "category",
        "product_detail",
        "cart",
        "checkout",
    }
    assert page_types == expected_page_types

    # Verify entry page
    entry_pages = [bp for bp in family["pageBlueprints"] if bp["isEntry"]]
    assert len(entry_pages) == 1
    assert entry_pages[0]["pageType"] == "home"

    # Verify provenance notes
    assert len(family["provenanceNotes"]) > 0
    assert any("Medusa B2B" in note for note in family["provenanceNotes"])


def test_get_site_family_not_found(api_client: TestClient):
    """Test that requesting a non-existent family returns 404."""
    response = api_client.get("/sites/families/non-existent-family")

    assert response.status_code == 404


def test_create_site_requires_product(api_client: TestClient):
    """Test that creating a site without a product returns a validation error."""
    client_id = _create_client(api_client, name="Test Site Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Should Fail",
            "description": "Missing product",
        },
    )

    # Pydantic returns 422 for missing required fields
    assert response.status_code == 422
    # Check that productId is mentioned in the validation error
    errors = response.json().get("detail", [])
    field_names = [e.get("loc", []) for e in errors if isinstance(e, dict)]
    assert any("productId" in str(loc) for loc in field_names), (
        f"Expected productId in validation errors, got: {errors}"
    )


def test_create_site_validates_product_ownership(api_client: TestClient):
    """Test that creating a site validates product belongs to the workspace."""
    client_id_1 = _create_client(api_client, name="Workspace 1")
    client_id_2 = _create_client(api_client, name="Workspace 2")
    product_id = _create_product(api_client, client_id=client_id_1, title="Product for Workspace 1")

    # Try to create site in workspace 2 with product from workspace 1
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id_2,
            "family": "medusa-b2b-starter",
            "name": "Should Fail",
            "productId": product_id,
        },
    )

    assert response.status_code == 404
    assert "Product not found" in response.json()["detail"]


def test_create_site_succeeds_with_product(api_client: TestClient, db_session):
    """Test that creating a site from medusa-b2b-starter succeeds with a product."""
    client_id = _create_client(api_client, name="Test Site Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Test Product")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "My B2B Store",
            "description": "A test B2B ecommerce site",
            "productId": product_id,
        },
    )

    assert response.status_code == 201
    site = response.json()

    # Verify site metadata
    assert site["clientId"] == client_id
    assert site["name"] == "My B2B Store"
    assert site["description"] == "A test B2B ecommerce site"
    assert site["status"] == "draft"
    assert site["experienceKind"] == "site"
    assert site["siteType"] == "ecommerce"
    assert site["siteFamily"] == "medusa-b2b-starter"
    assert site["commerceProvider"] == "medusa"
    assert site["productId"] == product_id

    # Verify pages were created
    assert len(site["pages"]) == 5

    # Verify page types - commerce-core pages only
    page_types = {page["pageType"] for page in site["pages"]}
    expected_page_types = {
        "home",
        "category",
        "product_detail",
        "cart",
        "checkout",
    }
    assert page_types == expected_page_types

    # Verify entry page
    entry_pages = [page for page in site["pages"] if page["isEntry"]]
    assert len(entry_pages) == 1
    assert entry_pages[0]["pageType"] == "home"
    assert site["entryPageId"] == entry_pages[0]["id"]

    # Verify template IDs
    for page in site["pages"]:
        assert page["templateId"] is not None
        assert page["templateId"].startswith("medusa-b2b-")


def test_create_site_has_correct_site_metadata(api_client: TestClient, db_session):
    """Test that created site has correct site metadata in the database."""
    client_id = _create_client(api_client, name="Site Metadata Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Metadata Test Product")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Metadata Test Site",
            "productId": product_id,
        },
    )

    assert response.status_code == 201
    site = response.json()

    # Verify database records
    funnel = db_session.query(Funnel).filter(Funnel.id == uuid.UUID(site["id"])).first()
    assert funnel is not None
    assert funnel.experience_kind == "site"
    assert funnel.site_type == "ecommerce"
    assert funnel.site_family == "medusa-b2b-starter"
    assert funnel.commerce_provider == "medusa"
    assert str(funnel.product_id) == product_id

    # Verify pages have page_type
    pages = db_session.query(FunnelPage).filter(FunnelPage.funnel_id == funnel.id).all()
    assert len(pages) == 5

    page_types = {page.page_type for page in pages}
    expected_page_types = {
        "home",
        "category",
        "product_detail",
        "cart",
        "checkout",
    }
    assert page_types == expected_page_types

    # Verify each page has a draft version
    for page in pages:
        version = (
            db_session.query(FunnelPageVersion).filter(FunnelPageVersion.page_id == page.id).first()
        )
        assert version is not None
        assert version.puck_data is not None


def test_create_site_rewrites_internal_page_links(api_client: TestClient, db_session):
    """Test that created site rewrites placeholder page IDs to real page IDs."""
    client_id = _create_client(api_client, name="Link Rewrite Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Link Rewrite Product")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Link Rewrite Test",
            "productId": product_id,
        },
    )

    assert response.status_code == 201
    site = response.json()

    # Build page type to ID mapping
    page_id_map = {page["pageType"]: page["id"] for page in site["pages"]}

    # Get the home page and check its puck_data for rewritten links
    home_page = next((p for p in site["pages"] if p["pageType"] == "home"), None)
    assert home_page is not None

    # Get the version to check puck_data
    version = (
        db_session.query(FunnelPageVersion)
        .filter(FunnelPageVersion.page_id == uuid.UUID(home_page["id"]))
        .first()
    )
    assert version is not None
    puck_data = version.puck_data

    # Check that at least one internal CTA link is rewritten to a real page ID
    # The templates use __PAGE_CATEGORY__, __PAGE_CART__, etc. placeholders
    # After rewriting, these should be real UUIDs
    found_rewritten_link = False
    content = puck_data.get("content", [])

    def walk_for_target_page_id(node):
        nonlocal found_rewritten_link
        if isinstance(node, dict):
            target_page_id = node.get("targetPageId")
            if isinstance(target_page_id, str) and target_page_id:
                # Check if it's a real UUID (not a placeholder)
                try:
                    uuid.UUID(target_page_id)
                    # If it's a UUID, check it matches one of our page IDs
                    if target_page_id in page_id_map.values():
                        found_rewritten_link = True
                except ValueError:
                    pass
            for value in node.values():
                walk_for_target_page_id(value)
        elif isinstance(node, list):
            for item in node:
                walk_for_target_page_id(item)

    walk_for_target_page_id(content)
    assert found_rewritten_link, (
        "Expected at least one internal CTA link to be rewritten to a real page ID"
    )


def test_create_site_generates_all_expected_pages_with_correct_page_types(api_client: TestClient):
    """Test that created site generates all expected pages with correct page types and template IDs."""
    client_id = _create_client(api_client, name="Page Generation Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Page Generation Test")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Page Generation Test",
            "productId": product_id,
        },
    )

    assert response.status_code == 201
    site = response.json()

    # Expected page configurations - commerce-core pages only
    expected_pages = [
        {
            "pageType": "home",
            "templateId": "medusa-b2b-home",
            "name": "Home",
            "slug": "home",
            "ordering": 0,
            "isEntry": True,
        },
        {
            "pageType": "category",
            "templateId": "medusa-b2b-category",
            "name": "Category",
            "slug": "category",
            "ordering": 1,
            "isEntry": False,
        },
        {
            "pageType": "product_detail",
            "templateId": "medusa-b2b-pdp",
            "name": "Product Detail",
            "slug": "product",
            "ordering": 2,
            "isEntry": False,
        },
        {
            "pageType": "cart",
            "templateId": "medusa-b2b-cart",
            "name": "Cart",
            "slug": "cart",
            "ordering": 3,
            "isEntry": False,
        },
        {
            "pageType": "checkout",
            "templateId": "medusa-b2b-checkout",
            "name": "Checkout",
            "slug": "checkout",
            "ordering": 4,
            "isEntry": False,
        },
    ]

    for expected in expected_pages:
        matching_pages = [p for p in site["pages"] if p["pageType"] == expected["pageType"]]
        assert len(matching_pages) == 1, (
            f"Expected exactly one page with pageType {expected['pageType']}"
        )

        page = matching_pages[0]
        assert page["templateId"] == expected["templateId"]
        assert page["name"] == expected["name"]
        assert page["slug"] == expected["slug"]
        assert page["ordering"] == expected["ordering"]
        assert page["isEntry"] == expected["isEntry"]


def test_list_sites_returns_only_sites_for_workspace(api_client: TestClient):
    """Test that listing sites returns only sites for the specified workspace."""
    client_id_1 = _create_client(api_client, name="Workspace 1")
    client_id_2 = _create_client(api_client, name="Workspace 2")
    product_id_1 = _create_product(api_client, client_id=client_id_1, title="Product 1")
    product_id_2 = _create_product(api_client, client_id=client_id_2, title="Product 2")

    # Create sites for both workspaces
    response1 = api_client.post(
        "/sites",
        json={
            "clientId": client_id_1,
            "family": "medusa-b2b-starter",
            "name": "Site for Workspace 1",
            "productId": product_id_1,
        },
    )
    assert response1.status_code == 201

    response2 = api_client.post(
        "/sites",
        json={
            "clientId": client_id_2,
            "family": "medusa-b2b-starter",
            "name": "Site for Workspace 2",
            "productId": product_id_2,
        },
    )
    assert response2.status_code == 201

    # List sites for workspace 1
    response = api_client.get(f"/sites?clientId={client_id_1}")
    assert response.status_code == 200
    sites = response.json()

    assert len(sites) == 1
    assert sites[0]["clientId"] == client_id_1
    assert sites[0]["name"] == "Site for Workspace 1"


def test_get_site_detail_returns_pages(api_client: TestClient):
    """Test that getting site detail returns all pages with correct metadata."""
    client_id = _create_client(api_client, name="Site Detail Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Detail Test Product")

    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Detail Test Site",
            "productId": product_id,
        },
    )
    assert create_response.status_code == 201
    site_id = create_response.json()["id"]

    # Get site detail
    response = api_client.get(f"/sites/{site_id}?clientId={client_id}")
    assert response.status_code == 200
    site = response.json()

    assert site["id"] == site_id
    assert site["name"] == "Detail Test Site"
    assert site["siteFamily"] == "medusa-b2b-starter"
    assert len(site["pages"]) == 5

    # Verify entry page is marked
    entry_pages = [p for p in site["pages"] if p["isEntry"]]
    assert len(entry_pages) == 1
    assert entry_pages[0]["pageType"] == "home"
    assert site["entryPageId"] == entry_pages[0]["id"]


def test_get_site_validates_workspace_ownership(api_client: TestClient):
    """Test that getting site detail validates workspace ownership."""
    client_id_1 = _create_client(api_client, name="Owner Workspace")
    client_id_2 = _create_client(api_client, name="Other Workspace")
    product_id = _create_product(api_client, client_id=client_id_1, title="Product")

    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id_1,
            "family": "medusa-b2b-starter",
            "name": "Test Site",
            "productId": product_id,
        },
    )
    assert create_response.status_code == 201
    site_id = create_response.json()["id"]

    # Try to get site with wrong workspace
    response = api_client.get(f"/sites/{site_id}?clientId={client_id_2}")
    assert response.status_code == 403
    assert "does not belong to this workspace" in response.json()["detail"]


def test_non_site_funnel_behavior_remains_intact(api_client: TestClient):
    """Test that non-site funnels (regular funnels) are not affected by site changes."""
    client_id = _create_client(api_client, name="Funnel Integrity Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Test Product")

    # Create a regular funnel (not a site)
    funnel_response = api_client.post(
        "/funnels",
        json={
            "clientId": client_id,
            "productId": product_id,
            "name": "Regular Funnel",
        },
    )
    assert funnel_response.status_code == 201
    funnel = funnel_response.json()

    # Verify the funnel is not a site
    assert funnel.get("experienceKind") is None or funnel.get("experienceKind") == "funnel"
    assert funnel.get("siteType") is None
    assert funnel.get("siteFamily") is None
    assert funnel.get("commerceProvider") is None

    # Create a site and verify it doesn't affect the regular funnel
    site_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Test Site",
            "productId": product_id,
        },
    )
    assert site_response.status_code == 201

    # List sites - should only return the site, not the regular funnel
    sites_response = api_client.get(f"/sites?clientId={client_id}")
    assert sites_response.status_code == 200
    sites = sites_response.json()
    assert len(sites) == 1
    assert sites[0]["id"] != funnel["id"]
    assert sites[0]["name"] == "Test Site"


def test_create_site_with_unknown_family_returns_error(api_client: TestClient):
    """Test that creating a site with an unknown family returns an error."""
    client_id = _create_client(api_client, name="Unknown Family Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Product")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "unknown-family",
            "name": "Should Fail",
            "productId": product_id,
        },
    )

    assert response.status_code == 400
    assert "Unknown site family" in response.json()["detail"]


def test_create_site_without_client_id_returns_error(api_client: TestClient):
    """Test that creating a site without a client ID returns an error."""
    product_id = _create_product(
        api_client, client_id=_create_client(api_client, name="Temp"), title="Product"
    )

    response = api_client.post(
        "/sites",
        json={
            "family": "medusa-b2b-starter",
            "name": "Should Fail",
            "productId": product_id,
        },
    )

    assert response.status_code == 422  # Validation error


def test_templates_have_no_unsupported_claims():
    """Test that templates don't contain unsupported business claims."""
    import json
    from pathlib import Path

    templates_dir = Path(__file__).parent.parent / "app" / "templates" / "funnels"
    b2b_templates = [
        "medusa-b2b-home.json",
        "medusa-b2b-category.json",
        "medusa-b2b-pdp.json",
        "medusa-b2b-cart.json",
        "medusa-b2b-checkout.json",
    ]

    unsupported_claims = [
        "guaranteed",
        "1 business day",
        "NET 30",
        "dedicated account manager",
        "dedicated support",
        "automatically processed",
        "will be dynamically rendered",
    ]

    for template_name in b2b_templates:
        template_path = templates_dir / template_name
        if not template_path.exists():
            continue

        content = json.loads(template_path.read_text())
        puck_data = json.dumps(content.get("puckData", {}))

        for claim in unsupported_claims:
            assert claim.lower() not in puck_data.lower(), (
                f"Template {template_name} contains unsupported claim: '{claim}'"
            )


def test_site_page_type_mapping_in_public_page_response(api_client: TestClient, db_session):
    """Test that public page responses include pageTypeMap for site experiences."""
    client_id = _create_client(api_client, name="PageTypeMap Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="PageTypeMap Product")

    # Create a site
    site_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "PageTypeMap Test Site",
            "productId": product_id,
        },
    )
    assert site_response.status_code == 201
    site = site_response.json()

    # Get the home page
    home_page = next((p for p in site["pages"] if p["pageType"] == "home"), None)
    assert home_page is not None

    # Publish the site
    publish_response = api_client.post(f"/funnels/{site['id']}/publish")
    assert publish_response.status_code == 201

    # Get the funnel to find its route_slug
    funnel_response = api_client.get(f"/funnels/{site['id']}")
    assert funnel_response.status_code == 200
    funnel = funnel_response.json()
    route_slug = funnel["route_slug"]

    # Product slug is the short UUID prefix
    product_slug = product_id[:8].lower()

    # Get the public page
    public_page_response = api_client.get(
        f"/public/funnels/{product_slug}/{route_slug}/pages/{home_page['slug']}"
    )
    assert public_page_response.status_code == 200
    public_page = public_page_response.json()

    # Verify pageTypeMap is present and contains expected mappings
    assert "pageTypeMap" in public_page
    page_type_map = public_page["pageTypeMap"]
    assert isinstance(page_type_map, dict)

    # Verify all site page types are mapped
    page_types_in_map = set(page_type_map.values())
    expected_page_types = {"home", "category", "product_detail", "cart", "checkout"}
    assert page_types_in_map == expected_page_types, (
        f"Expected page types {expected_page_types}, got {page_types_in_map}"
    )

    # Verify the home page is correctly mapped
    home_page_id = home_page["id"]
    assert home_page_id in page_type_map
    assert page_type_map[home_page_id] == "home"


def test_category_handle_parameter_in_site_commerce(api_client: TestClient, db_session):
    """Test that category_handle parameter is supported in site commerce endpoint."""
    client_id = _create_client(api_client, name="CategoryHandle Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="CategoryHandle Product")

    # Create a site
    site_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "CategoryHandle Test Site",
            "productId": product_id,
        },
    )
    assert site_response.status_code == 201
    site = site_response.json()

    # Publish the site
    publish_response = api_client.post(f"/funnels/{site['id']}/publish")
    assert publish_response.status_code == 201

    # Get the funnel to find its route_slug
    funnel_response = api_client.get(f"/funnels/{site['id']}")
    assert funnel_response.status_code == 200
    funnel = funnel_response.json()
    route_slug = funnel["route_slug"]

    # Product slug is the short UUID prefix
    product_slug = product_id[:8].lower()

    # Request site commerce with category_handle parameter
    # This should not fail even if Medusa is not configured
    commerce_response = api_client.get(
        f"/public/funnels/{product_slug}/{route_slug}/site/commerce?category_handle=test-category"
    )

    # The endpoint should return 409 because Medusa is not configured
    # but it should accept the category_handle parameter
    assert commerce_response.status_code == 409
    assert "Medusa" in commerce_response.json()["detail"]


def test_product_handle_parameter_in_site_commerce(api_client: TestClient, db_session):
    """Test that product_handle parameter is supported in site commerce endpoint."""
    client_id = _create_client(api_client, name="ProductHandle Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="ProductHandle Product")

    # Create a site
    site_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "ProductHandle Test Site",
            "productId": product_id,
        },
    )
    assert site_response.status_code == 201
    site = site_response.json()

    # Publish the site
    publish_response = api_client.post(f"/funnels/{site['id']}/publish")
    assert publish_response.status_code == 201

    # Get the funnel to find its route_slug
    funnel_response = api_client.get(f"/funnels/{site['id']}")
    assert funnel_response.status_code == 200
    funnel = funnel_response.json()
    route_slug = funnel["route_slug"]

    # Product slug is the short UUID prefix
    product_slug = product_id[:8].lower()

    # Request site commerce with product_handle parameter
    commerce_response = api_client.get(
        f"/public/funnels/{product_slug}/{route_slug}/site/commerce?product_handle=test-product"
    )

    # The endpoint should return 409 because Medusa is not configured
    # but it should accept the product_handle parameter
    assert commerce_response.status_code == 409
    assert "Medusa" in commerce_response.json()["detail"]
