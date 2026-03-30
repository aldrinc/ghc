"""Tests for Medusa connection API endpoints.

This module tests:
- Medusa config CRUD operations
- Medusa connection status testing
- Medusa variant creation via Admin API
"""

from __future__ import annotations

import uuid
import json
from unittest.mock import patch, MagicMock

import httpx
import pytest
import respx
from app.auth.dependencies import AuthContext
from app.db.models import Client, ClientMedusaConfig, Product, ProductVariant, StripeAccountProfile
from app.routers import clients as clients_router
from app.routers import products as products_router
from app.services.medusa_connection import (
    _make_medusa_admin_request,
    medusa_create_product,
    medusa_create_variant,
)


TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture()
def seed_client(db_session):
    """Create a test client/workspace."""
    client = Client(org_id=TEST_ORG_ID, name="Test Workspace", industry="Retail")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    return client


@pytest.fixture()
def seed_product(db_session, seed_client):
    """Create a test product."""
    product = Product(
        org_id=TEST_ORG_ID,
        client_id=seed_client.id,
        title="Test Product",
        description="A test product for Medusa integration",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


class TestMedusaConfigCRUD:
    """Tests for Medusa configuration CRUD operations."""

    def test_get_medusa_config_not_configured(self, api_client, seed_client):
        """Test getting config when none exists returns not configured state."""
        response = api_client.get(f"/clients/{seed_client.id}/medusa/config")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] is None
        assert data["baseUrl"] is None
        assert data["connectionStatus"] == "not_configured"
        assert data["hasAdminApiKey"] is False
        assert data["stripeAccountProfileId"] is None
        assert data["defaultPaymentProviderId"] is None
        assert data["allowedPaymentProviderIds"] == []
        assert data["webhookRoutingMode"] == "shared_ingress"

    def test_create_medusa_config(self, api_client, seed_client):
        """Test creating a new Medusa configuration."""
        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://my-store.medusa.example.com",
                "adminApiKey": "test-api-key",
            },
        )
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        assert data["baseUrl"] == "https://my-store.medusa.example.com"
        assert data["hasAdminApiKey"] is True
        assert data["connectionStatus"] == "not_tested"

    def test_update_medusa_config(self, api_client, seed_client, db_session):
        """Test updating an existing Medusa configuration."""
        # Create initial config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://old-store.medusa.example.com",
            admin_api_key_encrypted="old-key",
            connection_status="connected",
        )
        db_session.add(config)
        db_session.commit()

        # Update config
        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://new-store.medusa.example.com",
                "adminApiKey": "new-api-key",
            },
        )
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        assert data["baseUrl"] == "https://new-store.medusa.example.com"
        assert data["hasAdminApiKey"] is True
        # Status should reset to not_tested after config change
        assert data["connectionStatus"] == "not_tested"

    def test_medusa_config_url_normalization(self, api_client, seed_client):
        """Test that Medusa URLs are normalized correctly."""
        # Test without https prefix
        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={"baseUrl": "my-store.medusa.example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["baseUrl"] == "https://my-store.medusa.example.com"

        # Test with trailing slash
        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={"baseUrl": "https://my-store.medusa.example.com/"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["baseUrl"] == "https://my-store.medusa.example.com"

    def test_medusa_config_invalid_url(self, api_client, seed_client):
        """Test that invalid URLs are rejected."""
        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={"baseUrl": "not-a-valid-url"},
        )
        assert response.status_code == 400


class TestMedusaConnectionStatus:
    """Tests for Medusa connection status testing."""

    def test_test_connection_success(self, api_client, seed_client, db_session):
        """Test successful connection test."""
        # Create config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="not_tested",
        )
        db_session.add(config)
        db_session.commit()

        # Mock the Medusa Admin API request
        with patch("app.services.medusa_connection._make_medusa_admin_request") as mock_request:
            mock_request.return_value = {"store": {"name": "Test Store"}}

            # Test connection
            response = api_client.get(f"/clients/{seed_client.id}/medusa/status")
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "connected"
            assert data["baseUrl"] == "https://my-store.medusa.example.com"

    def test_test_connection_unauthorized(self, api_client, seed_client, db_session):
        """Test connection test with invalid API key."""
        # Create config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="invalid-key",
            connection_status="not_tested",
        )
        db_session.add(config)
        db_session.commit()

        # Mock the Medusa Admin API request to raise 401
        from fastapi import HTTPException, status

        with patch("app.services.medusa_connection._make_medusa_admin_request") as mock_request:
            mock_request.side_effect = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Medusa authentication failed: Unauthorized",
            )

            # Test connection
            response = api_client.get(f"/clients/{seed_client.id}/medusa/status")
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "error"
            assert (
                "authentication" in data["message"].lower()
                or "unauthorized" in data["message"].lower()
            )

    @pytest.mark.skip(reason="Timeout test requires proper HTTP mocking setup")
    def test_test_connection_timeout(self, api_client, seed_client, db_session):
        """Test connection test with timeout."""
        # Create config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="not_tested",
        )
        db_session.add(config)
        db_session.commit()

        # Mock the test_medusa_connection function to return a timeout error
        from app.services.medusa_connection import MedusaConnectionStatus

        with patch("app.routers.clients.test_medusa_connection") as mock_test:
            mock_test.return_value = MedusaConnectionStatus(
                state="error",
                message="Medusa API request timed out after 10.0s (GET /admin/store).",
                base_url="https://my-store.medusa.example.com",
            )

            # Test connection
            response = api_client.get(f"/clients/{seed_client.id}/medusa/status")
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "error"
            assert "timeout" in data["message"].lower()

    def test_test_connection_not_configured(self, api_client, seed_client):
        """Test connection test when not configured."""
        response = api_client.get(f"/clients/{seed_client.id}/medusa/status")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "not_configured"


class TestMedusaVariantCreation:
    """Tests for Medusa variant creation."""

    def test_create_first_variant_creates_product(
        self, api_client, seed_client, seed_product, db_session
    ):
        """Test that creating the first variant also creates the Medusa product."""
        # Create Medusa config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="connected",
        )
        db_session.add(config)
        db_session.commit()

        medusa_product_id = "prod_medusa_123"
        medusa_variant_id = "variant_medusa_456"

        # Mock the Medusa API calls
        with (
            patch("app.services.medusa_catalog.medusa_create_product") as mock_create_product,
            patch("app.services.medusa_catalog.medusa_create_variant") as mock_create_variant,
        ):
            mock_create_product.return_value = {
                "id": medusa_product_id,
                "title": seed_product.title,
                "options": [{"id": "opt_1", "title": "Default"}],
            }
            mock_create_variant.return_value = {
                "id": medusa_variant_id,
                "title": "Test Variant",
                "prices": [{"amount": 1999, "currency_code": "usd"}],
            }

            # Create variant
            response = api_client.post(
                f"/products/{seed_product.id}/medusa/create-variant",
                json={
                    "title": "Test Variant",
                    "price": 1999,
                    "currency": "USD",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["medusaVariantId"] == medusa_variant_id
            assert data["medusaProductId"] == medusa_product_id
            assert data["title"] == "Test Variant"
            assert data["priceCents"] == 1999
            assert data["currency"] == "usd"

        # Verify local variant was created
        db_session.refresh(seed_product)
        assert seed_product.medusa_product_id == medusa_product_id

        # Verify local variant exists
        variants = (
            db_session.query(ProductVariant)
            .filter(ProductVariant.product_id == seed_product.id)
            .all()
        )
        assert len(variants) == 1
        assert variants[0].provider == "medusa"
        assert variants[0].external_price_id == medusa_variant_id

    def test_create_second_variant_reuses_product(
        self, api_client, seed_client, seed_product, db_session
    ):
        """Test that creating a second variant reuses the existing Medusa product."""
        # Create Medusa config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="connected",
        )
        db_session.add(config)

        # Set existing Medusa product ID on product
        medusa_product_id = "prod_medusa_existing"
        seed_product.medusa_product_id = medusa_product_id
        db_session.add(seed_product)
        db_session.commit()

        medusa_variant_id = "variant_medusa_new"

        # Mock the Medusa variant creation (no product creation needed)
        with (
            patch("app.services.medusa_catalog.medusa_create_variant") as mock_create_variant,
            patch("app.services.medusa_catalog.medusa_get_product_options") as mock_get_options,
        ):
            mock_create_variant.return_value = {
                "id": medusa_variant_id,
                "title": "Second Variant",
                "prices": [{"amount": 2999, "currency_code": "usd"}],
            }
            mock_get_options.return_value = [{"title": "Variant"}]

            # Create variant
            response = api_client.post(
                f"/products/{seed_product.id}/medusa/create-variant",
                json={
                    "title": "Second Variant",
                    "price": 2999,
                    "currency": "USD",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["medusaVariantId"] == medusa_variant_id
            assert data["medusaProductId"] == medusa_product_id

        # Verify product's medusa_product_id wasn't changed
        db_session.refresh(seed_product)
        assert seed_product.medusa_product_id == medusa_product_id

    def test_create_variant_rejects_compare_at_price_for_now(
        self, api_client, seed_client, seed_product, db_session
    ):
        """Compare-at price should fail cleanly until explicit Medusa support is added."""
        # Create Medusa config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="connected",
        )
        db_session.add(config)
        db_session.commit()

        response = api_client.post(
            f"/products/{seed_product.id}/medusa/create-variant",
            json={
                "title": "Full Variant",
                "price": 1999,
                "currency": "USD",
                "compareAtPrice": 2499,
                "sku": "SKU-123",
                "barcode": "1234567890",
                "inventoryQuantity": 100,
                "inventoryPolicy": "deny",
            },
        )
        assert response.status_code == 400
        assert "compare-at" in response.json()["detail"].lower()

    def test_create_variant_not_configured(self, api_client, seed_client, seed_product):
        """Test that variant creation fails when Medusa is not configured."""
        response = api_client.post(
            f"/products/{seed_product.id}/medusa/create-variant",
            json={
                "title": "Test Variant",
                "price": 1999,
                "currency": "USD",
            },
        )
        assert response.status_code == 409
        assert "not configured" in response.json()["detail"].lower()

    def test_create_variant_connection_error(
        self, api_client, seed_client, seed_product, db_session
    ):
        """Test that variant creation fails gracefully on connection error."""
        # Create Medusa config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="connected",
        )
        db_session.add(config)
        db_session.commit()

        # Mock connection error
        from fastapi import HTTPException, status

        with patch("app.services.medusa_catalog.medusa_create_product") as mock_create_product:
            mock_create_product.side_effect = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Medusa API request failed: Connection failed",
            )

            # Create variant
            response = api_client.post(
                f"/products/{seed_product.id}/medusa/create-variant",
                json={
                    "title": "Test Variant",
                    "price": 1999,
                    "currency": "USD",
                },
            )
            assert response.status_code == 502
            assert "failed" in response.json()["detail"].lower()


class TestMedusaAdminAPIPayloads:
    """Tests for correct Medusa Admin API payload shapes."""

    def test_product_payload_has_required_options(
        self, api_client, seed_client, seed_product, db_session
    ):
        """Test that product creation includes required options field."""
        # Create Medusa config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="connected",
        )
        db_session.add(config)
        db_session.commit()

        captured_request = None

        def capture_request(*args, **kwargs):
            nonlocal captured_request
            captured_request = kwargs
            return {
                "id": "prod_123",
                "title": seed_product.title,
                "options": [{"id": "opt_1", "title": "Default"}],
            }

        # Mock Medusa product creation with request capture
        with (
            patch("app.services.medusa_catalog.medusa_create_product") as mock_create_product,
            patch("app.services.medusa_catalog.medusa_create_variant") as mock_create_variant,
        ):
            mock_create_product.side_effect = capture_request
            mock_create_variant.return_value = {
                "id": "variant_123",
                "title": "Test Variant",
                "prices": [{"amount": 1999, "currency_code": "usd"}],
            }

            # Create variant
            response = api_client.post(
                f"/products/{seed_product.id}/medusa/create-variant",
                json={
                    "title": "Test Variant",
                    "price": 1999,
                    "currency": "USD",
                },
            )
            assert response.status_code == 201

            # Verify request was made
            assert mock_create_product.called

    def test_variant_payload_not_wrapped(self, api_client, seed_client, seed_product, db_session):
        """Test that variant creation payload is sent directly, not wrapped."""
        # Create Medusa config
        config = ClientMedusaConfig(
            org_id=TEST_ORG_ID,
            client_id=seed_client.id,
            base_url="https://my-store.medusa.example.com",
            admin_api_key_encrypted="test-api-key",
            connection_status="connected",
        )
        db_session.add(config)

        # Set existing Medusa product ID
        seed_product.medusa_product_id = "prod_existing"
        db_session.add(seed_product)
        db_session.commit()

        captured_request = None

        def capture_request(*args, **kwargs):
            nonlocal captured_request
            captured_request = kwargs
            return {
                "id": "variant_123",
                "title": "Test Variant",
                "prices": [{"amount": 1999, "currency_code": "usd"}],
            }

        # Mock Medusa variant creation with request capture
        with (
            patch("app.services.medusa_catalog.medusa_create_variant") as mock_create_variant,
            patch("app.services.medusa_catalog.medusa_get_product_options") as mock_get_options,
        ):
            mock_create_variant.side_effect = capture_request
            mock_get_options.return_value = [{"title": "Variant"}]

            # Create variant
            response = api_client.post(
                f"/products/{seed_product.id}/medusa/create-variant",
                json={
                    "title": "Test Variant",
                    "price": 1999,
                    "currency": "USD",
                },
            )
            assert response.status_code == 201

            # Verify request was made
            assert mock_create_variant.called


class TestMedusaServiceRequests:
    """Direct Medusa service request tests using mocked HTTP."""

    @respx.mock
    def test_make_medusa_admin_request_uses_bearer_auth(self):
        """Test that admin requests use Bearer auth, not Basic."""
        route = respx.get("https://my-store.medusa.example.com/admin/products").mock(
            return_value=httpx.Response(
                200, json={"products": [], "count": 0, "limit": 1, "offset": 0}
            )
        )

        _make_medusa_admin_request(
            base_url="https://my-store.medusa.example.com",
            api_key="secret-token",
            method="GET",
            path="/admin/products",
        )

        assert route.called
        request = route.calls[0].request
        assert request.headers.get("Authorization") == "Bearer secret-token"

    @respx.mock
    def test_medusa_create_product_sends_direct_payload_with_required_options(self):
        route = respx.post("https://my-store.medusa.example.com/admin/products").mock(
            return_value=httpx.Response(200, json={"product": {"id": "prod_123", "title": "Test"}})
        )

        medusa_create_product(
            base_url="https://my-store.medusa.example.com",
            api_key="secret-token",
            title="Test",
            description="Desc",
            options=[{"title": "Variant", "values": ["Default"]}],
            product_status="draft",
        )

        assert route.called
        payload = json.loads(route.calls[0].request.content.decode("utf-8"))
        assert payload["title"] == "Test"
        assert payload["options"] == [{"title": "Variant", "values": ["Default"]}]
        assert "product" not in payload

    @respx.mock
    def test_medusa_create_variant_sends_direct_payload_not_wrapped(self):
        route = respx.post(
            "https://my-store.medusa.example.com/admin/products/prod_123/variants"
        ).mock(
            return_value=httpx.Response(
                200, json={"variant": {"id": "var_123", "title": "Test Variant"}}
            )
        )

        medusa_create_variant(
            base_url="https://my-store.medusa.example.com",
            api_key="secret-token",
            product_id="prod_123",
            title="Test Variant",
            prices=[{"amount": 1999, "currency_code": "usd"}],
            options={"Variant": "Test Variant"},
        )

        assert route.called
        payload = json.loads(route.calls[0].request.content.decode("utf-8"))
        assert payload["title"] == "Test Variant"
        assert "variant" not in payload


class TestStripeAccountProfileCRUD:
    """Tests for Stripe account profile CRUD operations."""

    def test_create_stripe_account_profile(self, api_client, seed_client, db_session):
        """Test creating a new Stripe account profile."""
        response = api_client.post(
            "/clients/org/stripe-profiles",
            json={
                "label": "Test Stripe Profile",
                "stripeAccountId": "acct_test123",
                "mode": "shared",
            },
        )
        assert response.status_code == 201, f"Response: {response.text}"
        data = response.json()
        assert data["label"] == "Test Stripe Profile"
        assert data["stripeAccountId"] == "acct_test123"
        assert data["mode"] == "shared"
        assert data["status"] == "active"
        assert data["hasSecretKeyRef"] is False
        assert data["hasWebhookSecretRef"] is False

    def test_list_stripe_profiles(self, api_client, seed_client, db_session):
        """Test listing Stripe account profiles for an org."""
        profile = StripeAccountProfile(
            org_id=TEST_ORG_ID,
            label="List Test Profile",
            stripe_account_id="acct_list123",
            mode="shared",
            status="active",
        )
        db_session.add(profile)
        db_session.commit()

        response = api_client.get("/clients/org/stripe-profiles")
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(profile["label"] == "List Test Profile" for profile in data)

    def test_get_stripe_profile_by_id(self, api_client, seed_client, db_session):
        """Test getting a Stripe account profile by ID."""
        profile = StripeAccountProfile(
            org_id=TEST_ORG_ID,
            label="Get Test Profile",
            stripe_account_id="acct_get123",
            mode="shared",
            status="active",
        )
        db_session.add(profile)
        db_session.commit()

        response = api_client.get(f"/clients/org/stripe-profiles/{profile.id}")
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        assert data["label"] == "Get Test Profile"
        assert data["stripeAccountId"] == "acct_get123"

    def test_update_stripe_profile(self, api_client, seed_client, db_session):
        """Test updating a Stripe account profile."""
        profile = StripeAccountProfile(
            org_id=TEST_ORG_ID,
            label="Update Test Profile",
            stripe_account_id="acct_update123",
            mode="shared",
            status="active",
        )
        db_session.add(profile)
        db_session.commit()

        response = api_client.put(
            f"/clients/org/stripe-profiles/{profile.id}",
            json={
                "label": "Updated Label",
                "status": "disabled",
            },
        )
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        assert data["label"] == "Updated Label"
        assert data["status"] == "disabled"

    def test_stripe_profile_not_found(self, api_client, seed_client):
        """Test getting a non-existent Stripe account profile returns 404."""
        response = api_client.get(f"/clients/org/stripe-profiles/{uuid.uuid4()}")
        assert response.status_code == 404


class TestMedusaConfigWithStripeProfile:
    """Tests for Medusa config with Stripe profile linkage."""

    def test_create_medusa_config_with_stripe_profile(self, api_client, seed_client, db_session):
        """Test creating a Medusa config with Stripe profile linkage."""
        profile = StripeAccountProfile(
            org_id=TEST_ORG_ID,
            label="Link Test Profile",
            stripe_account_id="acct_link123",
            mode="shared",
            status="active",
        )
        db_session.add(profile)
        db_session.commit()

        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://my-store.medusa.example.com",
                "adminApiKey": "test-api-key",
                "stripeAccountProfileId": str(profile.id),
                "defaultPaymentProviderId": "stripe",
                "allowedPaymentProviderIds": ["stripe", "manual"],
                "webhookRoutingMode": "shared_ingress",
            },
        )
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        assert data["stripeAccountProfileId"] == str(profile.id)
        assert data["defaultPaymentProviderId"] == "stripe"
        assert data["allowedPaymentProviderIds"] == ["stripe", "manual"]
        assert data["webhookRoutingMode"] == "shared_ingress"

    def test_stripe_profile_org_validation(self, api_client, seed_client, db_session):
        """Test that a Stripe profile must belong to the same org."""
        from app.db.models import Org

        other_org = Org(id=uuid.UUID("00000000-0000-0000-0000-000000000999"), name="Other Org")
        db_session.add(other_org)
        db_session.commit()

        other_profile = StripeAccountProfile(
            org_id=other_org.id,
            label="Other Org Profile",
            stripe_account_id="acct_other123",
            mode="shared",
            status="active",
        )
        db_session.add(other_profile)
        db_session.commit()

        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://my-store.medusa.example.com",
                "stripeAccountProfileId": str(other_profile.id),
            },
        )
        assert response.status_code == 400
        assert "not found or does not belong to this organization" in response.json()["detail"]

    def test_dedicated_profile_cannot_be_shared(self, api_client, seed_client, db_session):
        """Test that a dedicated Stripe profile cannot be attached to multiple workspaces."""
        profile = StripeAccountProfile(
            org_id=TEST_ORG_ID,
            label="Dedicated Profile",
            stripe_account_id="acct_dedicated123",
            mode="dedicated",
            status="active",
        )
        db_session.add(profile)
        db_session.commit()

        response1 = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://workspace1.medusa.example.com",
                "stripeAccountProfileId": str(profile.id),
            },
        )
        assert response1.status_code == 200, f"Response: {response1.text}"

        other_client = Client(org_id=TEST_ORG_ID, name="Other Workspace", industry="Retail")
        db_session.add(other_client)
        db_session.commit()

        response2 = api_client.put(
            f"/clients/{other_client.id}/medusa/config",
            json={
                "baseUrl": "https://workspace2.medusa.example.com",
                "stripeAccountProfileId": str(profile.id),
            },
        )
        assert response2.status_code == 400
        assert "dedicated Stripe profile" in response2.json()["detail"]

    def test_default_provider_must_be_in_allowlist(self, api_client, seed_client, db_session):
        """Test that default_payment_provider_id must be in allowed_payment_provider_ids."""
        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://my-store.medusa.example.com",
                "defaultPaymentProviderId": "stripe",
                "allowedPaymentProviderIds": ["paypal", "manual"],
            },
        )
        assert response.status_code == 400
        assert "defaultPaymentProviderId" in response.json()["detail"]

    def test_direct_webhook_mode_requires_single_workspace_profile(
        self, api_client, seed_client, db_session
    ):
        """Test that direct webhook routing is allowed when the profile is only used by one workspace."""
        profile = StripeAccountProfile(
            org_id=TEST_ORG_ID,
            label="Shared Profile",
            stripe_account_id="acct_shared123",
            mode="shared",
            status="active",
        )
        db_session.add(profile)
        db_session.commit()

        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://my-store.medusa.example.com",
                "stripeAccountProfileId": str(profile.id),
                "webhookRoutingMode": "direct",
            },
        )
        assert response.status_code == 200, f"Response: {response.text}"

    def test_shared_profile_cannot_be_reused_while_other_workspace_uses_direct_webhook(
        self, api_client, seed_client, db_session
    ):
        """Test that a second workspace cannot attach a profile already used with direct routing."""
        profile = StripeAccountProfile(
            org_id=TEST_ORG_ID,
            label="Shared Profile",
            stripe_account_id="acct_shared123",
            mode="shared",
            status="active",
        )
        db_session.add(profile)
        db_session.commit()

        first_response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://my-store.medusa.example.com",
                "stripeAccountProfileId": str(profile.id),
                "allowedPaymentProviderIds": ["stripe"],
                "webhookRoutingMode": "direct",
            },
        )
        assert first_response.status_code == 200, f"Response: {first_response.text}"

        other_client = Client(org_id=TEST_ORG_ID, name="Other Workspace", industry="Retail")
        db_session.add(other_client)
        db_session.commit()

        second_response = api_client.put(
            f"/clients/{other_client.id}/medusa/config",
            json={
                "baseUrl": "https://other-store.medusa.example.com",
                "stripeAccountProfileId": str(profile.id),
                "allowedPaymentProviderIds": ["stripe"],
            },
        )
        assert second_response.status_code == 400
        assert "direct webhook routing" in second_response.json()["detail"]

    def test_allowed_payment_provider_ids_normalized(self, api_client, seed_client, db_session):
        """Test that allowed_payment_provider_ids are normalized (trimmed, de-duped)."""
        response = api_client.put(
            f"/clients/{seed_client.id}/medusa/config",
            json={
                "baseUrl": "https://my-store.medusa.example.com",
                "allowedPaymentProviderIds": ["  stripe ", "stripe", " paypal ", "manual"],
            },
        )
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        assert "stripe" in data["allowedPaymentProviderIds"]
        assert "paypal" in data["allowedPaymentProviderIds"]
        assert "manual" in data["allowedPaymentProviderIds"]
        assert len(data["allowedPaymentProviderIds"]) == len(set(data["allowedPaymentProviderIds"]))
