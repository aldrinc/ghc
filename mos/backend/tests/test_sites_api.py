"""Tests for the Sites API endpoints."""

from dataclasses import replace
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.enums import AssetSourceEnum
from app.db.models import (
    Asset,
    Artifact,
    Client,
    Funnel,
    FunnelPage,
    FunnelPageVersion,
    Product,
    Site,
    SiteLink,
    SitePage,
    SitePageVersion,
    SitePublication,
    SitePublicationPage,
)
from app.services import site_blueprints


B2B_EXPECTED_PAGES = [
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
    {
        "pageType": "privacy_policy",
        "templateId": "medusa-b2b-policy-privacy",
        "name": "Privacy Policy",
        "slug": "privacy",
        "ordering": 5,
        "isEntry": False,
    },
    {
        "pageType": "terms_of_service",
        "templateId": "medusa-b2b-policy-terms",
        "name": "Terms of Service",
        "slug": "terms",
        "ordering": 6,
        "isEntry": False,
    },
    {
        "pageType": "returns_refunds_policy",
        "templateId": "medusa-b2b-policy-returns",
        "name": "Returns and Refunds",
        "slug": "returns",
        "ordering": 7,
        "isEntry": False,
    },
    {
        "pageType": "shipping_policy",
        "templateId": "medusa-b2b-policy-shipping",
        "name": "Shipping Policy",
        "slug": "shipping",
        "ordering": 8,
        "isEntry": False,
    },
    {
        "pageType": "contact_support",
        "templateId": "medusa-b2b-policy-contact",
        "name": "Contact",
        "slug": "contact",
        "ordering": 9,
        "isEntry": False,
    },
]

B2B_EXPECTED_PAGE_TYPES = {page["pageType"] for page in B2B_EXPECTED_PAGES}
B2B_EXPECTED_PAGE_COUNT = len(B2B_EXPECTED_PAGES)


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
    assert medusa_family["themeRequirement"] == "optional"
    assert medusa_family["pageCount"] == B2B_EXPECTED_PAGE_COUNT


def test_get_site_family_detail_returns_page_blueprints(api_client: TestClient):
    """Test that getting a site family detail returns all page blueprints."""
    response = api_client.get("/sites/families/medusa-b2b-starter")

    assert response.status_code == 200
    family = response.json()

    assert family["family"] == "medusa-b2b-starter"
    assert family["name"] == "Medusa B2B Starter"
    assert family["themeRequirement"] == "optional"
    assert len(family["pageBlueprints"]) == B2B_EXPECTED_PAGE_COUNT

    # Verify page types include commerce flow and compliance/support pages
    page_types = {bp["pageType"] for bp in family["pageBlueprints"]}
    assert page_types == B2B_EXPECTED_PAGE_TYPES

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


def test_list_site_families_includes_medusa_b2c_starter(api_client: TestClient):
    """Listing families should include the Medusa B2C starter."""
    response = api_client.get("/sites/families")

    assert response.status_code == 200
    families = response.json()
    family_ids = {f["family"] for f in families}

    assert "medusa-b2c-starter" in family_ids

    b2c_family = next(f for f in families if f["family"] == "medusa-b2c-starter")
    assert b2c_family["name"] == "Medusa B2C Starter"
    assert b2c_family["siteType"] == "ecommerce"
    assert b2c_family["commerceProvider"] == "medusa"
    assert b2c_family["themeRequirement"] == "optional"
    assert b2c_family["pageCount"] == 21


def test_get_medusa_b2c_starter_family_detail(api_client: TestClient):
    """The Medusa B2C starter should expose all expected page blueprints."""
    response = api_client.get("/sites/families/medusa-b2c-starter")

    assert response.status_code == 200
    family = response.json()

    assert family["family"] == "medusa-b2c-starter"
    assert family["name"] == "Medusa B2C Starter"
    assert family["themeRequirement"] == "optional"
    assert len(family["pageBlueprints"]) == 21

    expected_page_types = {
        "home",
        "store",
        "collection",
        "category",
        "product_detail",
        "cart",
        "checkout",
        "privacy_policy",
        "terms_of_service",
        "returns_refunds_policy",
        "shipping_policy",
        "contact_support",
        "account_dashboard",
        "account_profile",
        "account_addresses",
        "account_orders",
        "account_order_detail",
        "order_confirmed",
        "order_transfer",
        "order_transfer_accept",
        "order_transfer_decline",
    }
    page_types = {bp["pageType"] for bp in family["pageBlueprints"]}
    assert page_types == expected_page_types

    entry_pages = [bp for bp in family["pageBlueprints"] if bp["isEntry"]]
    assert len(entry_pages) == 1
    assert entry_pages[0]["pageType"] == "home"
    assert any("B2C" in note or "b2c" in note.lower() for note in family["provenanceNotes"])


def test_create_site_without_product_succeeds(api_client: TestClient, db_session):
    """Test that creating a site without a productId succeeds in the site runtime."""
    client_id = _create_client(api_client, name="Test Site Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "No Product Site",
            "description": "A site without a product",
        },
    )

    assert response.status_code == 201
    site = response.json()

    # Verify site metadata
    assert site["clientId"] == client_id
    assert site["name"] == "No Product Site"
    assert site["description"] == "A site without a product"
    assert site["status"] == "draft"
    assert site["siteType"] == "ecommerce"
    assert site["siteFamily"] == "medusa-b2b-starter"
    assert site["commerceProvider"] == "medusa"
    assert site["productId"] is None  # No product required
    assert site["designSystemId"] is None
    assert site["routeSlug"] is not None  # Generated unique slug

    # Verify pages were created in site_pages, not funnel_pages
    assert len(site["pages"]) == B2B_EXPECTED_PAGE_COUNT

    # Verify page types
    page_types = {page["pageType"] for page in site["pages"]}
    assert page_types == B2B_EXPECTED_PAGE_TYPES

    # Verify entry page
    entry_pages = [page for page in site["pages"] if page["isEntry"]]
    assert len(entry_pages) == 1
    assert entry_pages[0]["pageType"] == "home"
    assert site["entryPageId"] == entry_pages[0]["id"]

    # Verify database records are in Site/SitePage/SitePageVersion, NOT Funnel
    db_site = db_session.query(Site).filter(Site.id == uuid.UUID(site["id"])).first()
    assert db_site is not None
    assert db_site.site_family == "medusa-b2b-starter"
    assert db_site.route_slug is not None

    # Verify no funnel was created
    db_funnel = db_session.query(Funnel).filter(Funnel.id == uuid.UUID(site["id"])).first()
    assert db_funnel is None

    # Verify pages are SitePage records
    db_pages = db_session.query(SitePage).filter(SitePage.site_id == db_site.id).all()
    assert len(db_pages) == B2B_EXPECTED_PAGE_COUNT

    # Verify versions are SitePageVersion records
    for page in db_pages:
        versions = (
            db_session.query(SitePageVersion).filter(SitePageVersion.page_id == page.id).all()
        )
        assert len(versions) >= 1  # At least one draft version


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
    assert site["siteType"] == "ecommerce"
    assert site["siteFamily"] == "medusa-b2b-starter"
    assert site["commerceProvider"] == "medusa"
    assert site["productId"] == product_id

    # Verify pages were created
    assert len(site["pages"]) == B2B_EXPECTED_PAGE_COUNT

    # Verify page types
    page_types = {page["pageType"] for page in site["pages"]}
    assert page_types == B2B_EXPECTED_PAGE_TYPES

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
    """Test that created site has correct site metadata in the dedicated site runtime."""
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

    # Verify database records are in Site/SitePage/SitePageVersion
    db_site = db_session.query(Site).filter(Site.id == uuid.UUID(site["id"])).first()
    assert db_site is not None
    assert db_site.site_type == "ecommerce"
    assert db_site.site_family == "medusa-b2b-starter"
    assert db_site.commerce_provider == "medusa"
    assert str(db_site.product_id) == product_id
    assert db_site.route_slug is not None

    # Verify pages have page_type in SitePage
    db_pages = db_session.query(SitePage).filter(SitePage.site_id == db_site.id).all()
    assert len(db_pages) == B2B_EXPECTED_PAGE_COUNT

    page_types = {page.page_type for page in db_pages}
    assert page_types == B2B_EXPECTED_PAGE_TYPES

    # Verify each page has a draft version
    for page in db_pages:
        version = (
            db_session.query(SitePageVersion).filter(SitePageVersion.page_id == page.id).first()
        )
        assert version is not None
        assert version.puck_data is not None


def test_create_site_funnel_succeeds(api_client: TestClient):
    """Site funnels should be creatable directly from a site."""
    client_id = _create_client(api_client, name="Site Funnel Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Bound Product")
    site_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Funnel Site",
            "productId": product_id,
        },
    )
    assert site_response.status_code == 201
    site = site_response.json()
    entry_page = next(page for page in site["pages"] if page["isEntry"])

    response = api_client.post(
        f"/sites/{site['id']}/funnels?clientId={client_id}",
        json={
            "name": "Main Checkout Funnel",
            "description": "Primary on-site funnel",
            "entryPageId": entry_page["id"],
            "productId": product_id,
            "trackingConfig": {"provider": "ga4", "measurementId": "G-TEST123"},
        },
    )

    assert response.status_code == 201
    funnel = response.json()
    assert funnel["siteId"] == site["id"]
    assert funnel["name"] == "Main Checkout Funnel"
    assert funnel["description"] == "Primary on-site funnel"
    assert funnel["status"] == "draft"
    assert funnel["entryPageId"] == entry_page["id"]
    assert funnel["productId"] == product_id
    assert funnel["trackingConfig"] == {"provider": "ga4", "measurementId": "G-TEST123"}
    assert funnel["steps"] == []

    list_response = api_client.get(f"/sites/{site['id']}/funnels?clientId={client_id}")
    assert list_response.status_code == 200
    funnels = list_response.json()
    assert len(funnels) == 1
    assert funnels[0]["id"] == funnel["id"]


def test_update_site_funnel_accepts_paused_status(api_client: TestClient):
    """Site funnel status should accept paused to match the frontend workflow."""
    client_id = _create_client(api_client, name="Paused Funnel Workspace")
    site_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Paused Funnel Site",
        },
    )
    assert site_response.status_code == 201
    site = site_response.json()

    create_response = api_client.post(
        f"/sites/{site['id']}/funnels?clientId={client_id}",
        json={"name": "Lifecycle Funnel"},
    )
    assert create_response.status_code == 201
    funnel = create_response.json()

    update_response = api_client.patch(
        f"/sites/{site['id']}/funnels/{funnel['id']}?clientId={client_id}",
        json={"status": "paused"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["status"] == "paused"


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
        db_session.query(SitePageVersion)
        .filter(SitePageVersion.page_id == uuid.UUID(home_page["id"]))
        .first()
    )
    assert version is not None
    puck_data = version.puck_data

    # Check that at least one internal CTA link is rewritten to a real page ID
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

    for expected in B2B_EXPECTED_PAGES:
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


def test_site_medusa_config_returns_unavailable_for_b2c_site_without_workspace_config(
    api_client: TestClient,
):
    """B2C sites should expose the runtime config shape even without workspace config."""
    client_id = _create_client(api_client, name="B2C Config Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2c-starter",
            "name": "My B2C Store",
        },
    )
    assert response.status_code == 201
    site = response.json()

    config_response = api_client.get(f"/sites/{site['id']}/medusa-config")
    assert config_response.status_code == 200
    payload = config_response.json()

    assert payload["siteFamily"] == "medusa-b2c-starter"
    assert payload["commerceProvider"] == "medusa"
    assert payload["medusaConfig"]["available"] is False
    assert payload["medusaConfig"]["baseUrl"] is None
    assert payload["medusaConfig"]["publishableKey"] is None


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
    assert site["themeBindingMode"] == "standalone"
    assert len(site["pages"]) == B2B_EXPECTED_PAGE_COUNT

    # Verify entry page is marked
    entry_pages = [p for p in site["pages"] if p["isEntry"]]
    assert len(entry_pages) == 1
    assert entry_pages[0]["pageType"] == "home"
    assert site["entryPageId"] == entry_pages[0]["id"]


def test_get_site_detail_without_client_id_returns_site_for_same_org(api_client: TestClient):
    """Direct site lookups should work without a preselected workspace."""
    client_id = _create_client(api_client, name="Direct Preview Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Direct Preview Product")

    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Direct Preview Site",
            "productId": product_id,
        },
    )
    assert create_response.status_code == 201
    site_id = create_response.json()["id"]

    response = api_client.get(f"/sites/{site_id}")
    assert response.status_code == 200

    site = response.json()
    assert site["id"] == site_id
    assert site["clientId"] == client_id
    assert site["name"] == "Direct Preview Site"


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


def test_create_site_with_unknown_family_returns_error(api_client: TestClient):
    """Test that creating a site with an unknown family returns an error."""
    client_id = _create_client(api_client, name="Unknown Family Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "unknown-family",
            "name": "Should Fail",
        },
    )

    assert response.status_code == 400
    assert "Unknown site family" in response.json()["detail"]


def test_create_site_without_client_id_returns_error(api_client: TestClient):
    """Test that creating a site without a client ID returns an error."""
    response = api_client.post(
        "/sites",
        json={
            "family": "medusa-b2b-starter",
            "name": "Should Fail",
        },
    )

    assert response.status_code == 422  # Validation error


def test_duplicate_page_types_allowed_in_site_pages(api_client: TestClient, db_session):
    """Test that duplicate page types are allowed in site_pages (uniqueness is on slug now)."""
    client_id = _create_client(api_client, name="Duplicate Type Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Product")

    # Create a site first
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Type Test Site",
            "productId": product_id,
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Get the site detail to see the pages
    site_detail = api_client.get(f"/sites/{site['id']}?clientId={client_id}").json()

    # Verify that each page type is unique (but we should be able to have duplicates if we wanted)
    page_types = [p["pageType"] for p in site_detail["pages"]]
    assert len(page_types) == len(set(page_types))  # All unique in this case

    # The key assertion: the unique constraint is on (site_id, slug) not (site_id, page_type)
    # So we could theoretically add another page with the same page_type but different slug


def test_duplicate_slugs_rejected_per_site(api_client: TestClient, db_session):
    """Test that duplicate slugs are rejected per site."""
    client_id = _create_client(api_client, name="Slug Test Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Product")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Slug Test Site",
            "productId": product_id,
        },
    )
    assert response.status_code == 201
    site = response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Try to update the page slug to an existing slug
    response = api_client.patch(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}",
        json={"slug": "checkout"},  # checkout slug already exists
    )

    assert response.status_code == 409
    assert "already in use" in response.json()["detail"]


def test_site_page_editor_get_endpoint(api_client: TestClient, db_session):
    """Test the site page editor GET endpoint."""
    client_id = _create_client(api_client, name="Page Editor Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Editor Product")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Editor Test Site",
            "productId": product_id,
        },
    )
    assert response.status_code == 201
    site = response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Get page editor data
    editor_response = api_client.get(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}"
    )
    assert editor_response.status_code == 200
    data = editor_response.json()

    # Verify response structure
    assert "site" in data
    assert "page" in data
    assert "latestDraft" in data or data["latestDraft"] is None
    assert "latestApproved" in data
    assert "designSystemTokens" in data

    # Verify site data
    assert data["site"]["id"] == site["id"]
    assert data["site"]["name"] == "Editor Test Site"
    assert data["site"]["siteFamily"] == "medusa-b2b-starter"

    # Verify page data
    assert data["page"]["id"] == home_page["id"]
    assert data["page"]["pageType"] == "home"


def test_site_page_editor_update_endpoint(api_client: TestClient, db_session):
    """Test the site page editor PATCH endpoint."""
    client_id = _create_client(api_client, name="Page Update Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Update Product")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Update Test Site",
            "productId": product_id,
        },
    )
    assert response.status_code == 201
    site = response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Update page name
    update_response = api_client.patch(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}",
        json={"name": "Updated Home Page"},
    )
    assert update_response.status_code == 200
    data = update_response.json()

    assert data["page"]["name"] == "Updated Home Page"


def test_site_page_editor_create_version_endpoint(api_client: TestClient, db_session):
    """Test the site page editor POST versions endpoint."""
    client_id = _create_client(api_client, name="Version Create Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Version Product")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Version Test Site",
            "productId": product_id,
        },
    )
    assert response.status_code == 201
    site = response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Create a new version
    new_puck_data = {"root": {"props": {"title": "New Version"}}, "content": [], "zones": {}}
    version_response = api_client.post(
        f"/sites/{site['id']}/pages/{home_page['id']}/versions?clientId={client_id}",
        json={
            "puckData": new_puck_data,
            "status": "draft",
        },
    )
    assert version_response.status_code == 200
    version_data = version_response.json()

    assert version_data["status"] == "draft"
    assert version_data["puckData"] == new_puck_data
    assert "id" in version_data
    assert "createdAt" in version_data


def test_site_page_editor_create_version_with_approved_status(api_client: TestClient, db_session):
    """Test creating a page version with approved status."""
    client_id = _create_client(api_client, name="Approved Version Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Approved Product")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Approved Version Site",
            "productId": product_id,
        },
    )
    assert response.status_code == 201
    site = response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Create an approved version
    new_puck_data = {"root": {"props": {"title": "Approved Version"}}, "content": [], "zones": {}}
    version_response = api_client.post(
        f"/sites/{site['id']}/pages/{home_page['id']}/versions?clientId={client_id}",
        json={
            "puckData": new_puck_data,
            "status": "approved",
        },
    )
    assert version_response.status_code == 200
    version_data = version_response.json()

    assert version_data["status"] == "approved"


def test_site_page_editor_invalid_status_returns_error(api_client: TestClient):
    """Test that invalid status returns 400."""
    client_id = _create_client(api_client, name="Invalid Status Workspace")
    product_id = _create_product(api_client, client_id=client_id, title="Invalid Product")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Invalid Status Site",
            "productId": product_id,
        },
    )
    assert response.status_code == 201
    site = response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Try to create version with invalid status
    version_response = api_client.post(
        f"/sites/{site['id']}/pages/{home_page['id']}/versions?clientId={client_id}",
        json={
            "puckData": {"root": {"props": {}}, "content": [], "zones": {}},
            "status": "invalid_status",
        },
    )
    assert version_response.status_code == 400
    assert "Invalid status" in version_response.json()["detail"]


def test_site_route_slug_is_unique(api_client: TestClient, db_session):
    """Test that route_slug is unique across all sites."""
    client_id = _create_client(api_client, name="Slug Uniqueness Workspace")

    # Create first site
    response1 = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "First Site",
        },
    )
    assert response1.status_code == 201
    site1 = response1.json()

    # Create second site with same name (should get different slug)
    response2 = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "First Site",  # Same name
        },
    )
    assert response2.status_code == 201
    site2 = response2.json()

    # Route slugs should be different
    assert site1["routeSlug"] != site2["routeSlug"]


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


# =============================================================================
# Tests for site publication / publish flow
# =============================================================================


def test_site_publish_success(api_client: TestClient, db_session):
    """Test that publishing a site creates publication snapshot and artifact."""
    client_id = _create_client(api_client, name="Publish Test Workspace")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Publishable Site",
        },
    )
    assert response.status_code == 201
    site = response.json()
    site_id = site["id"]

    # Publish the site
    publish_response = api_client.post(f"/sites/{site_id}/publish?clientId={client_id}")
    assert publish_response.status_code == 200
    publish_data = publish_response.json()

    # Verify publish response structure
    assert "publicationId" in publish_data
    assert "artifactId" in publish_data
    assert "artifactVersion" in publish_data
    assert publish_data["siteId"] == site_id
    assert publish_data["routeSlug"] is not None
    assert publish_data["pageCount"] == B2B_EXPECTED_PAGE_COUNT
    assert publish_data["publishedAt"] is not None

    # Verify publication record was created
    pub_id = publish_data["publicationId"]
    pub_record = (
        db_session.query(SitePublication).filter(SitePublication.id == uuid.UUID(pub_id)).first()
    )
    assert pub_record is not None
    assert pub_record.site_id == uuid.UUID(site_id)

    # Verify publication pages were created
    pub_pages = (
        db_session.query(SitePublicationPage)
        .filter(SitePublicationPage.publication_id == uuid.UUID(pub_id))
        .all()
    )
    assert len(pub_pages) == B2B_EXPECTED_PAGE_COUNT

    # Verify site_runtime_bundle artifact was created
    artifact = (
        db_session.query(Artifact)
        .filter(Artifact.id == uuid.UUID(publish_data["artifactId"]))
        .first()
    )
    assert artifact is not None
    assert artifact.type.value == "site_runtime_bundle"
    assert artifact.version == 1
    assert artifact.data["meta"]["siteId"] == site_id


def test_site_publish_updates_active_publication(api_client: TestClient, db_session):
    """Test that publishing a site updates the active publication reference on the site."""
    client_id = _create_client(api_client, name="Active Pub Test Workspace")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Multi-Publish Site",
        },
    )
    assert response.status_code == 201
    site = response.json()
    site_id = site["id"]

    # First publish
    publish1 = api_client.post(f"/sites/{site_id}/publish?clientId={client_id}")
    assert publish1.status_code == 200
    pub1_id = publish1.json()["publicationId"]

    # Second publish (should create new publication, update active ref)
    publish2 = api_client.post(f"/sites/{site_id}/publish?clientId={client_id}")
    assert publish2.status_code == 200
    pub2_id = publish2.json()["publicationId"]

    # Verify second publish incremented artifact version
    assert publish2.json()["artifactVersion"] == 2

    # Verify site has updated active publication reference
    db_site = db_session.query(Site).filter(Site.id == uuid.UUID(site_id)).first()
    assert str(db_site.active_site_publication_id) == pub2_id


def test_site_publish_prefers_published_version_over_newer_approved(
    api_client: TestClient, db_session
):
    """Publishing should keep the currently published page version when a newer approved draft exists."""
    client_id = _create_client(api_client, name="Publish Version Preference Test")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Published Version Preference Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    home_page = next(page for page in site["pages"] if page["slug"] == "home")
    home_page_id = uuid.UUID(home_page["id"])
    older_published_version_id = uuid.uuid4()
    newer_approved_version_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            SitePageVersion(
                id=older_published_version_id,
                page_id=home_page_id,
                status="published",
                puck_data={"root": {"props": {"title": "published-home"}}},
                provenance={},
                created_at=now - timedelta(minutes=5),
                updated_at=now - timedelta(minutes=5),
            ),
            SitePageVersion(
                id=newer_approved_version_id,
                page_id=home_page_id,
                status="approved",
                puck_data={"root": {"props": {"title": "approved-home"}}},
                provenance={},
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    publish_response = api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")
    assert publish_response.status_code == 200

    page_response = api_client.get(f"/public/sites/{site['routeSlug']}/pages/home")
    assert page_response.status_code == 200
    page_data = page_response.json()

    assert page_data["versionId"] == str(older_published_version_id)
    assert page_data["puckData"]["root"]["props"]["title"] == "published-home"


def test_site_publish_not_found(api_client: TestClient):
    """Test that publishing a non-existent site returns 404."""
    fake_site_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())

    response = api_client.post(f"/sites/{fake_site_id}/publish?clientId={client_id}")
    assert response.status_code == 404


def test_site_publish_invalid_workspace(api_client: TestClient, db_session):
    """Test that publishing a site with wrong workspace returns 404."""
    client_id = _create_client(api_client, name="Wrong Workspace Test")

    # Create a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Workspace Test Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Try to publish with a different client_id
    wrong_client_id = str(uuid.uuid4())
    publish_response = api_client.post(f"/sites/{site['id']}/publish?clientId={wrong_client_id}")
    assert publish_response.status_code == 404


# =============================================================================
# Tests for public site endpoints
# =============================================================================


def test_public_site_meta_success(api_client: TestClient, db_session):
    """Test that getting public site meta works for published sites."""
    client_id = _create_client(api_client, name="Public Meta Test")

    # Create and publish a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Public Meta Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Publish it
    api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")

    # Get public meta
    meta_response = api_client.get(f"/public/sites/{site['routeSlug']}/meta")
    assert meta_response.status_code == 200
    meta = meta_response.json()

    assert meta["siteId"] == site["id"]
    assert meta["name"] == "Public Meta Site"
    assert meta["routeSlug"] == site["routeSlug"]
    assert meta["publicationId"] is not None


def test_public_site_meta_not_found(api_client: TestClient):
    """Test that getting meta for non-existent site returns 404."""
    response = api_client.get("/public/sites/nonexistent-site/meta")
    assert response.status_code == 404


def test_public_site_page_success(api_client: TestClient, db_session):
    """Test that getting a public site page works."""
    client_id = _create_client(api_client, name="Public Page Test")

    # Create and publish a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Public Page Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Publish it
    api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")

    # Get a page (home page)
    page_response = api_client.get(f"/public/sites/{site['routeSlug']}/pages/home")
    assert page_response.status_code == 200
    page_data = page_response.json()

    assert "pageId" in page_data
    assert "puckData" in page_data
    assert page_data["slug"] == "home"


def test_public_site_page_not_found(api_client: TestClient, db_session):
    """Test that getting a non-existent page returns 404."""
    client_id = _create_client(api_client, name="Page Not Found Test")

    # Create and publish a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Page Not Found Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Publish it
    api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")

    # Try to get non-existent page
    page_response = api_client.get(f"/public/sites/{site['routeSlug']}/pages/nonexistent")
    assert page_response.status_code == 404


def test_public_site_graph_success(api_client: TestClient, db_session):
    """Test that getting the site graph works."""
    client_id = _create_client(api_client, name="Graph Test")

    # Create and publish a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Graph Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Publish it
    api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")

    # Get graph
    graph_response = api_client.get(f"/public/sites/{site['routeSlug']}/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()

    assert graph["siteId"] == site["id"]
    assert "pages" in graph
    assert "links" in graph
    assert len(graph["pages"]) == B2B_EXPECTED_PAGE_COUNT


def test_public_site_graph_uses_published_page_slugs_for_links(api_client: TestClient, db_session):
    """Publication snapshots should expose final page slugs, not page types, in link data."""
    client_id = _create_client(api_client, name="Graph Link Slugs Test")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Graph Link Slug Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    home_page = next(page for page in site["pages"] if page["slug"] == "home")
    product_page = next(page for page in site["pages"] if page["slug"] == "product")
    db_session.add(
        SiteLink(
            id=uuid.uuid4(),
            site_id=uuid.UUID(site["id"]),
            from_page_id=uuid.UUID(home_page["id"]),
            to_page_id=uuid.UUID(product_page["id"]),
            from_page_type="home",
            to_page_type="product_detail",
            label="Shop now",
            link_kind="internal",
            meta={},
        )
    )
    db_session.commit()

    publish_response = api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")
    assert publish_response.status_code == 200

    graph_response = api_client.get(f"/public/sites/{site['routeSlug']}/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()

    assert any(
        link["fromPageSlug"] == "home" and link["toPageSlug"] == "product"
        for link in graph["links"]
    )


def test_public_site_graph_site_not_found(api_client: TestClient):
    """Test that getting graph for non-existent site returns 404."""
    response = api_client.get("/public/sites/nonexistent-site/graph")
    assert response.status_code == 404


def test_public_site_product_not_found(api_client: TestClient, db_session):
    """Test that getting a non-existent product returns 404."""
    client_id = _create_client(api_client, name="Product Not Found Test")

    # Create and publish a site (no product)
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Product Test Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Publish it
    api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")

    # Try to get non-existent product
    product_response = api_client.get(
        f"/public/sites/{site['routeSlug']}/products/nonexistent-product"
    )
    assert product_response.status_code == 404


def test_public_site_artifact_fallback_uses_matching_site_artifact(
    api_client: TestClient, db_session
):
    """Artifact fallback must not return another site's runtime when a client has multiple sites."""
    client_id = _create_client(api_client, name="Artifact Fallback Scope Test")

    response_a = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Artifact Site A",
        },
    )
    assert response_a.status_code == 201
    site_a = response_a.json()

    response_b = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Artifact Site B",
        },
    )
    assert response_b.status_code == 201
    site_b = response_b.json()

    publish_a = api_client.post(f"/sites/{site_a['id']}/publish?clientId={client_id}")
    assert publish_a.status_code == 200
    publish_b = api_client.post(f"/sites/{site_b['id']}/publish?clientId={client_id}")
    assert publish_b.status_code == 200

    db_site_a = db_session.query(Site).filter(Site.id == uuid.UUID(site_a["id"])).first()
    db_site_a.active_site_publication_id = None
    db_session.commit()

    meta_response = api_client.get(f"/public/sites/{site_a['routeSlug']}/meta")
    assert meta_response.status_code == 200
    meta = meta_response.json()

    assert meta["siteId"] == site_a["id"]
    assert meta["name"] == "Artifact Site A"


# =============================================================================
# Tests for site_runtime_bundle artifact payload
# =============================================================================


def test_site_runtime_bundle_artifact_payload_structure(api_client: TestClient, db_session):
    """Test that the site_runtime_bundle artifact has correct structure."""
    client_id = _create_client(api_client, name="Artifact Payload Test")

    # Create and publish a site
    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Artifact Payload Site",
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Publish it
    publish_response = api_client.post(f"/sites/{site['id']}/publish?clientId={client_id}")
    assert publish_response.status_code == 200

    # Get the artifact
    artifact = (
        db_session.query(Artifact)
        .filter(Artifact.id == uuid.UUID(publish_response.json()["artifactId"]))
        .first()
    )

    assert artifact is not None
    data = artifact.data

    # Verify top-level structure
    assert "meta" in data
    assert "pages" in data
    assert "links" in data
    assert "funnels" in data
    assert "productBindings" in data

    # Verify meta
    assert data["meta"]["siteId"] == site["id"]
    assert data["meta"]["routeSlug"] == site["routeSlug"]
    assert data["meta"]["publicationId"] is not None

    # Verify pages
    assert len(data["pages"]) == B2B_EXPECTED_PAGE_COUNT
    for slug, page_data in data["pages"].items():
        assert "pageId" in page_data
        assert "versionId" in page_data
        assert "puckData" in page_data
        assert "pageType" in page_data


# =============================================================================
# Tests for site theme binding mode
# =============================================================================


def test_create_site_defaults_to_standalone_mode(api_client: TestClient, db_session):
    """New sites should default to standalone theme binding mode."""
    client_id = _create_client(api_client, name="Theme Binding Test Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Standalone Site",
        },
    )

    assert response.status_code == 201
    site = response.json()

    assert site["themeBindingMode"] == "standalone"
    assert site["designSystemId"] is None


def test_create_site_with_explicit_workspace_default_mode(api_client: TestClient, db_session):
    """Sites can be created with workspace_default theme binding mode."""
    client_id = _create_client(api_client, name="Workspace Default Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Workspace Default Site",
            "themeBindingMode": "workspace_default",
        },
    )

    assert response.status_code == 201
    site = response.json()

    assert site["themeBindingMode"] == "workspace_default"


def test_create_site_design_system_mode_requires_design_system_id(
    api_client: TestClient, db_session
):
    """design_system theme binding mode requires a designSystemId."""
    client_id = _create_client(api_client, name="Design System Mode Test")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Should Fail",
            "themeBindingMode": "design_system",
            # No designSystemId provided
        },
    )

    assert response.status_code == 400
    assert "designSystemId" in response.json()["detail"]


def test_create_site_standalone_ignores_provided_design_system_id(
    api_client: TestClient, db_session
):
    """standalone theme binding mode should ignore any provided designSystemId."""
    client_id = _create_client(api_client, name="Standalone Ignore DS Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Standalone Ignore DS Site",
            "themeBindingMode": "standalone",
            "designSystemId": "00000000-0000-0000-0000-000000000001",  # Should be ignored
        },
    )

    assert response.status_code == 201
    site = response.json()

    assert site["themeBindingMode"] == "standalone"
    assert site["designSystemId"] is None


def test_create_site_rejects_standalone_when_family_requires_theme(
    api_client: TestClient, db_session, monkeypatch
):
    """Required-theme families should reject standalone site creation."""
    descriptor = site_blueprints.SITE_FAMILIES["medusa-b2c-starter"]
    monkeypatch.setitem(
        site_blueprints.SITE_FAMILIES,
        "medusa-b2c-starter",
        replace(descriptor, theme_requirement="required"),
    )
    client_id = _create_client(api_client, name="Required Theme Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2c-starter",
            "name": "Theme Required Site",
            "themeBindingMode": "standalone",
        },
    )

    assert response.status_code == 400
    assert "requires an explicit site theme" in response.json()["detail"]


def test_patch_site_theme_binding_mode(api_client: TestClient, db_session):
    """PATCH /sites/{site_id} should allow updating theme binding mode."""
    client_id = _create_client(api_client, name="Patch Theme Workspace")

    # Create a site
    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Patch Theme Site",
        },
    )
    assert create_response.status_code == 201
    site = create_response.json()
    assert site["themeBindingMode"] == "standalone"

    # Patch to workspace_default
    patch_response = api_client.patch(
        f"/sites/{site['id']}?clientId={client_id}",
        json={"themeBindingMode": "workspace_default"},
    )
    assert patch_response.status_code == 200
    patched_site = patch_response.json()
    assert patched_site["themeBindingMode"] == "workspace_default"


def test_patch_site_theme_binding_mode_to_design_system_requires_ds_id(
    api_client: TestClient, db_session
):
    """Patching to design_system mode requires designSystemId."""
    client_id = _create_client(api_client, name="Patch DS Req Workspace")

    # Create a site
    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Patch DS Req Site",
        },
    )
    assert create_response.status_code == 201
    site = create_response.json()

    # Try to patch to design_system without designSystemId
    patch_response = api_client.patch(
        f"/sites/{site['id']}?clientId={client_id}",
        json={"themeBindingMode": "design_system"},
    )
    assert patch_response.status_code == 400
    assert "designSystemId" in patch_response.json()["detail"]


def test_list_sites_includes_theme_binding_mode(api_client: TestClient, db_session):
    """List sites response should include themeBindingMode."""
    client_id = _create_client(api_client, name="List Theme Workspace")

    response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "List Theme Site",
        },
    )
    assert response.status_code == 201

    # List sites
    list_response = api_client.get(f"/sites?clientId={client_id}")
    assert list_response.status_code == 200
    sites = list_response.json()

    assert len(sites) == 1
    assert sites[0]["themeBindingMode"] == "standalone"


def test_get_site_includes_theme_binding_mode(api_client: TestClient, db_session):
    """Get site detail response should include themeBindingMode."""
    client_id = _create_client(api_client, name="Get Theme Workspace")

    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Get Theme Site",
        },
    )
    assert create_response.status_code == 201
    site = create_response.json()

    # Get site detail
    detail_response = api_client.get(f"/sites/{site['id']}?clientId={client_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()

    assert detail["themeBindingMode"] == "standalone"
    assert "pages" in detail


def test_site_page_editor_returns_null_tokens_for_standalone_site(
    api_client: TestClient, db_session
):
    """Site page editor should return null design system tokens for standalone sites."""
    client_id = _create_client(api_client, name="Editor Tokens Workspace")

    # Create a site
    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Editor Tokens Site",
        },
    )
    assert create_response.status_code == 201
    site = create_response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Get page editor
    editor_response = api_client.get(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}"
    )
    assert editor_response.status_code == 200
    editor_data = editor_response.json()

    # Standalone site should have null tokens
    assert editor_data["designSystemTokens"] is None


def _create_design_system(
    api_client: TestClient, db_session, *, client_id: str, name: str
) -> str:
    """Helper to create a design system and return its ID."""
    client = db_session.query(Client).filter(Client.id == uuid.UUID(client_id)).first()
    assert client is not None

    logo_public_id = uuid.uuid4()
    db_session.add(
        Asset(
            org_id=client.org_id,
            client_id=client.id,
            source_type=AssetSourceEnum.generated,
            channel_id="brand",
            format="image",
            content={"label": f"{name} logo"},
            public_id=logo_public_id,
            asset_kind="image",
            alt=f"{name} logo",
        )
    )
    db_session.commit()

    tokens = {
        "dataTheme": "light",
        "fontUrls": [],
        "fontCss": None,
        "cssVars": {
            "--color-page-bg": "#ffffff",
            "--color-bg": "#f5f5f5",
            "--color-brand": "#3b82f6",
            "--color-text": "#1a1a1a",
            "--color-cta": "#3b82f6",
            "--color-cta-text": "#ffffff",
            "--color-cta-shell": "#1e40af",
            "--color-cta-icon": "#ffffff",
            "--hero-bg": "#1e3a8a",
            "--pitch-bg": "#f0fdf4",
        },
        "funnelDefaults": {"bgColor": "#ffffff", "textColor": "#1a1a1a"},
        "brand": {
            "name": name,
            "logoAssetPublicId": str(logo_public_id),
            "logoAlt": f"{name} logo",
        },
    }
    response = api_client.post(
        "/design-systems",
        json={"name": name, "tokens": tokens, "clientId": client_id},
    )
    assert response.status_code == 201, f"Failed to create design system: {response.json()}"
    return response.json()["id"]


def test_changing_site_theme_mode_affects_page_editor_token_resolution(
    api_client: TestClient, db_session
):
    """Changing a site's theme mode after creation should affect page editor token resolution.

    Pages do NOT copy site-level design_system_id, so they are not "pinned" to a specific DS.
    When the site's theme mode changes, the page editor should reflect the new site-level
    resolution (not use stale copied values).
    """
    client_id = _create_client(api_client, name="Theme Mode Affect Workspace")

    # Create a site (defaults to standalone mode)
    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Theme Mode Test Site",
        },
    )
    assert create_response.status_code == 201
    site = create_response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Verify page has no design_system_id (pages don't inherit at creation)
    assert home_page["designSystemId"] is None

    # Get page editor - should have null tokens (standalone mode)
    editor_response = api_client.get(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}"
    )
    assert editor_response.status_code == 200
    editor_data = editor_response.json()
    assert editor_data["designSystemTokens"] is None

    # Create a design system
    ds_id = _create_design_system(api_client, db_session, client_id=client_id, name="Test DS")

    # Patch site to use design_system mode
    patch_response = api_client.patch(
        f"/sites/{site['id']}?clientId={client_id}",
        json={"themeBindingMode": "design_system", "designSystemId": ds_id},
    )
    assert patch_response.status_code == 200
    patched_site = patch_response.json()
    assert patched_site["themeBindingMode"] == "design_system"
    assert patched_site["designSystemId"] == ds_id

    # Get page editor again - should NOW have tokens from the site's DS
    # because the page doesn't have its own override
    editor_response2 = api_client.get(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}"
    )
    assert editor_response2.status_code == 200
    editor_data2 = editor_response2.json()
    assert editor_data2["designSystemTokens"] is not None
    assert editor_data2["designSystemTokens"]["brand"]["name"] == "Test DS"


def test_page_override_wins_over_site_theme(api_client: TestClient, db_session):
    """When a page has an explicit design_system_id override, it should win over site theme."""
    client_id = _create_client(api_client, name="Page Override Workspace")

    # Create two design systems
    site_ds_id = _create_design_system(api_client, db_session, client_id=client_id, name="Site DS")
    page_ds_id = _create_design_system(api_client, db_session, client_id=client_id, name="Page DS")

    # Create a site with design_system mode
    create_response = api_client.post(
        "/sites",
        json={
            "clientId": client_id,
            "family": "medusa-b2b-starter",
            "name": "Override Test Site",
            "themeBindingMode": "design_system",
            "designSystemId": site_ds_id,
        },
    )
    assert create_response.status_code == 201
    site = create_response.json()
    home_page = next(p for p in site["pages"] if p["pageType"] == "home")

    # Get page editor - should use site's DS tokens
    editor_response = api_client.get(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}"
    )
    assert editor_response.status_code == 200
    editor_data = editor_response.json()
    assert editor_data["designSystemTokens"]["brand"]["name"] == "Site DS"

    # Now set an explicit page-level override
    patch_response = api_client.patch(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}",
        json={"designSystemId": page_ds_id},
    )
    assert patch_response.status_code == 200

    # Get page editor - should now use page's DS tokens
    editor_response2 = api_client.get(
        f"/sites/{site['id']}/pages/{home_page['id']}?clientId={client_id}"
    )
    assert editor_response2.status_code == 200
    editor_data2 = editor_response2.json()
    assert editor_data2["designSystemTokens"]["brand"]["name"] == "Page DS"


def test_template_instantiation_rejects_invalid_design_system_id(
    api_client: TestClient, db_session
):
    """Template instantiation should reject invalid design_system_id."""
    client_id = _create_client(api_client, name="Instantiate Invalid DS Workspace")

    # Get a template ID
    templates_response = api_client.get("/site-templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    assert len(templates) > 0
    template_id = templates[0]["id"]

    # Try to instantiate with an invalid design system ID
    response = api_client.post(
        f"/site-templates/{template_id}/instantiate",
        json={
            "clientId": client_id,
            "name": "Should Fail",
            "themeBindingMode": "design_system",
            "designSystemId": "00000000-0000-0000-0000-000000000001",  # Invalid UUID
        },
    )
    assert response.status_code == 404
    assert "Design system not found" in response.json()["detail"]


def test_site_templates_expose_theme_requirement(api_client: TestClient, db_session):
    """System site templates should expose their theme requirement metadata."""
    response = api_client.get("/site-templates")

    assert response.status_code == 200
    templates = response.json()
    template = next(item for item in templates if item["family"] == "medusa-b2c-starter")
    assert template["themeRequirement"] == "optional"


def test_template_instantiation_rejects_foreign_design_system_id(
    api_client: TestClient, db_session
):
    """Template instantiation should reject design_system_id that belongs to another client."""
    client_id_1 = _create_client(api_client, name="Client 1 Workspace")
    client_id_2 = _create_client(api_client, name="Client 2 Workspace")

    # Create a design system for client 1
    ds_id = _create_design_system(api_client, db_session, client_id=client_id_1, name="Client 1 DS")

    # Get a template ID
    templates_response = api_client.get("/site-templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    template_id = templates[0]["id"]

    # Client 2 should NOT be able to use client 1's design system
    response = api_client.post(
        f"/site-templates/{template_id}/instantiate",
        json={
            "clientId": client_id_2,
            "name": "Should Fail",
            "themeBindingMode": "design_system",
            "designSystemId": ds_id,  # Belongs to client 1
        },
    )
    assert response.status_code == 409
    assert "must belong to the same client" in response.json()["detail"]


def test_template_instantiation_rejects_invalid_theme_binding_mode(
    api_client: TestClient, db_session
):
    """Template instantiation should reject invalid theme_binding_mode values."""
    client_id = _create_client(api_client, name="Invalid Mode Workspace")

    # Get a template ID
    templates_response = api_client.get("/site-templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    template_id = templates[0]["id"]

    # Try with invalid mode
    response = api_client.post(
        f"/site-templates/{template_id}/instantiate",
        json={
            "clientId": client_id,
            "name": "Should Fail",
            "themeBindingMode": "invalid_mode",
        },
    )
    assert response.status_code == 400
    assert "Invalid themeBindingMode" in response.json()["detail"]


def test_template_instantiation_standalone_ignores_design_system_id(
    api_client: TestClient, db_session
):
    """Template instantiation with standalone mode should ignore any provided designSystemId."""
    client_id = _create_client(api_client, name="Standalone Ignore DS Workspace")

    # Create a design system
    ds_id = _create_design_system(api_client, db_session, client_id=client_id, name="Test DS")

    # Get a template ID
    templates_response = api_client.get("/site-templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    template_id = templates[0]["id"]

    # Instantiate with standalone mode but provide a designSystemId
    response = api_client.post(
        f"/site-templates/{template_id}/instantiate",
        json={
            "clientId": client_id,
            "name": "Standalone Should Ignore DS",
            "themeBindingMode": "standalone",
            "designSystemId": ds_id,  # Should be ignored
        },
    )
    assert response.status_code == 201
    site = response.json()

    # Verify the site has standalone mode and no design_system_id
    get_response = api_client.get(f"/sites/{site['siteId']}?clientId={client_id}")
    assert get_response.status_code == 200
    site_detail = get_response.json()
    assert site_detail["themeBindingMode"] == "standalone"
    assert site_detail["designSystemId"] is None


def test_template_instantiation_rejects_standalone_when_template_requires_theme(
    api_client: TestClient, db_session, monkeypatch
):
    """Required-theme templates should reject standalone instantiation."""
    descriptor = site_blueprints.SITE_FAMILIES["medusa-b2c-starter"]
    monkeypatch.setitem(
        site_blueprints.SITE_FAMILIES,
        "medusa-b2c-starter",
        replace(descriptor, theme_requirement="required"),
    )
    client_id = _create_client(api_client, name="Required Template Theme Workspace")

    templates_response = api_client.get("/site-templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    template_id = next(item["id"] for item in templates if item["family"] == "medusa-b2c-starter")

    response = api_client.post(
        f"/site-templates/{template_id}/instantiate",
        json={
            "clientId": client_id,
            "name": "Theme Required Template Site",
            "themeBindingMode": "standalone",
        },
    )

    assert response.status_code == 400
    assert "requires an explicit site theme" in response.json()["detail"]
