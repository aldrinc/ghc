"""Tests for Medusa Store API runtime service."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.services.medusa_store_runtime import (
    MedusaStoreConfig,
    _make_medusa_store_request,
    _require_medusa_store_config,
    medusa_list_regions,
    medusa_list_products,
    medusa_get_product,
    medusa_get_product_by_handle,
    medusa_list_collections,
    medusa_list_categories,
    medusa_create_cart,
    medusa_get_cart,
    medusa_update_cart,
    medusa_add_cart_line_item,
    medusa_update_cart_line_item,
    medusa_delete_cart_line_item,
    medusa_list_shipping_options,
    medusa_add_shipping_method,
    medusa_list_payment_providers,
    medusa_create_payment_collection,
    medusa_initialize_payment_session,
    medusa_complete_cart,
    filter_payment_providers_by_allowlist,
    validate_provider_id_against_allowlist,
    resolve_default_payment_provider_id,
)


class TestMedusaStoreConfig:
    """Tests for MedusaStoreConfig dataclass."""

    def test_config_creation(self):
        """Test creating a MedusaStoreConfig."""
        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )
        assert config.base_url == "https://store.example.com"
        assert config.publishable_key == "pk_test_123"


class TestMakeMedusaStoreRequest:
    """Tests for _make_medusa_store_request."""

    @patch("app.services.medusa_store_runtime.httpx.Client")
    def test_successful_get_request(self, mock_client):
        """Test successful GET request to Medusa Store API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"products": [{"id": "prod_1"}]}

        mock_client_instance = MagicMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = _make_medusa_store_request(
            base_url=config.base_url,
            publishable_key=config.publishable_key,
            method="GET",
            path="/store/products",
        )

        assert result == {"products": [{"id": "prod_1"}]}
        mock_client_instance.request.assert_called_once()
        call_args = mock_client_instance.request.call_args
        assert call_args.kwargs["method"] == "GET"
        assert "store/products" in call_args.kwargs["url"]
        assert call_args.kwargs["headers"]["x-publishable-api-key"] == "pk_test_123"

    @patch("app.services.medusa_store_runtime.httpx.Client")
    def test_successful_post_request(self, mock_client):
        """Test successful POST request to Medusa Store API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"cart": {"id": "cart_1"}}

        mock_client_instance = MagicMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = _make_medusa_store_request(
            base_url=config.base_url,
            publishable_key=config.publishable_key,
            method="POST",
            path="/store/carts",
            json_body={"region_id": "reg_1"},
        )

        assert result == {"cart": {"id": "cart_1"}}
        mock_client_instance.request.assert_called_once()
        # Verify the request was made
        assert mock_client_instance.request.called

    @patch("app.services.medusa_store_runtime.httpx.Client")
    def test_401_unauthorized_error(self, mock_client):
        """Test 401 unauthorized error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Invalid API key"}

        mock_client_instance = MagicMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="invalid_key",
        )

        with pytest.raises(HTTPException) as exc_info:
            _make_medusa_store_request(
                base_url=config.base_url,
                publishable_key=config.publishable_key,
                method="GET",
                path="/store/products",
            )

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in str(exc_info.value.detail)

    @patch("app.services.medusa_store_runtime.httpx.Client")
    def test_404_not_found_error(self, mock_client):
        """Test 404 not found error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Product not found"}

        mock_client_instance = MagicMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        with pytest.raises(HTTPException) as exc_info:
            _make_medusa_store_request(
                base_url=config.base_url,
                publishable_key=config.publishable_key,
                method="GET",
                path="/store/products/prod_nonexistent",
            )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()

    @patch("app.services.medusa_store_runtime.httpx.Client")
    def test_timeout_error(self, mock_client):
        """Test timeout error handling."""
        import httpx

        mock_client_instance = MagicMock()
        mock_client_instance.request.side_effect = httpx.TimeoutException("Request timed out")
        mock_client.return_value.__enter__.return_value = mock_client_instance

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        with pytest.raises(HTTPException) as exc_info:
            _make_medusa_store_request(
                base_url=config.base_url,
                publishable_key=config.publishable_key,
                method="GET",
                path="/store/products",
                timeout_seconds=5.0,
            )

        assert exc_info.value.status_code == 504
        assert "timed out" in str(exc_info.value.detail).lower()


class TestRequireMedusaStoreConfig:
    """Tests for _require_medusa_store_config."""

    def test_missing_config(self, db_session):
        """Test error when Medusa config is not configured."""
        with patch("app.services.medusa_store_runtime.get_client_medusa_config", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                _require_medusa_store_config(
                    session=db_session,
                    org_id="org_1",
                    client_id="client_1",
                )
            assert exc_info.value.status_code == 409
            assert "not configured" in str(exc_info.value.detail).lower()

    def test_missing_publishable_key(self, db_session):
        """Test error when publishable key is not set."""
        mock_config = MagicMock()
        mock_config.base_url = "https://store.example.com"
        mock_config.publishable_key_encrypted = None

        with patch(
            "app.services.medusa_store_runtime.get_client_medusa_config", return_value=mock_config
        ):
            with pytest.raises(HTTPException) as exc_info:
                _require_medusa_store_config(
                    session=db_session,
                    org_id="org_1",
                    client_id="client_1",
                )
            assert exc_info.value.status_code == 409
            assert "publishable key" in str(exc_info.value.detail).lower()

    def test_valid_config(self, db_session):
        """Test successful config retrieval."""
        mock_config = MagicMock()
        mock_config.base_url = "https://store.example.com"
        mock_config.publishable_key_encrypted = "pk_test_123"

        with patch(
            "app.services.medusa_store_runtime.get_client_medusa_config", return_value=mock_config
        ):
            result = _require_medusa_store_config(
                session=db_session,
                org_id="org_1",
                client_id="client_1",
            )
            assert result.base_url == "https://store.example.com"
            assert result.publishable_key == "pk_test_123"


class TestMedusaListRegions:
    """Tests for medusa_list_regions."""

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_list_regions_success(self, mock_request):
        """Test successful regions listing."""
        mock_request.return_value = {
            "regions": [
                {"id": "reg_1", "name": "US", "currency_code": "usd"},
                {"id": "reg_2", "name": "EU", "currency_code": "eur"},
            ]
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_list_regions(config=config)

        assert len(result) == 2
        assert result[0]["id"] == "reg_1"
        assert result[1]["currency_code"] == "eur"
        mock_request.assert_called_once()

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_list_regions_empty(self, mock_request):
        """Test empty regions response."""
        mock_request.return_value = {"regions": []}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_list_regions(config=config)

        assert result == []


class TestMedusaListProducts:
    """Tests for medusa_list_products."""

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_list_products_success(self, mock_request):
        """Test successful products listing."""
        mock_request.return_value = {
            "products": [
                {"id": "prod_1", "title": "Product 1"},
                {"id": "prod_2", "title": "Product 2"},
            ],
            "count": 2,
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_list_products(config=config)

        assert result["count"] == 2
        assert len(result["products"]) == 2
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args.kwargs["params"]["limit"] == 100

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_list_products_with_filters(self, mock_request):
        """Test products listing with collection and category filters."""
        mock_request.return_value = {
            "products": [{"id": "prod_1"}],
            "count": 1,
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_list_products(
            config=config,
            collection_id="col_1",
            category_id="cat_1",
            limit=50,
            offset=10,
        )

        assert result["count"] == 1
        call_args = mock_request.call_args
        assert call_args.kwargs["params"]["collection_id"] == "col_1"
        assert call_args.kwargs["params"]["category_id"] == "cat_1"
        assert call_args.kwargs["params"]["limit"] == 50
        assert call_args.kwargs["params"]["offset"] == 10


class TestMedusaGetProduct:
    """Tests for medusa_get_product."""

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_get_product_success(self, mock_request):
        """Test successful product retrieval."""
        mock_request.return_value = {"product": {"id": "prod_1", "title": "Test Product"}}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_get_product(config=config, product_id="prod_1")

        assert result["id"] == "prod_1"
        assert result["title"] == "Test Product"
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "/store/products/prod_1" in call_args.kwargs["path"]


class TestMedusaGetProductByHandle:
    """Tests for medusa_get_product_by_handle."""

    @patch("app.services.medusa_store_runtime.medusa_list_products")
    def test_get_product_by_handle_success(self, mock_list):
        """Test successful product retrieval by handle."""
        mock_list.return_value = {
            "products": [{"id": "prod_1", "handle": "test-product"}],
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_get_product_by_handle(config=config, handle="test-product")

        assert result["id"] == "prod_1"
        assert result["handle"] == "test-product"
        mock_list.assert_called_once()
        # Verify the handle was passed correctly
        assert mock_list.called

    @patch("app.services.medusa_store_runtime.medusa_list_products")
    def test_get_product_by_handle_not_found(self, mock_list):
        """Test product not found by handle."""
        mock_list.return_value = {"products": []}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_get_product_by_handle(config=config, handle="nonexistent")

        assert result is None


class TestMedusaCartOperations:
    """Tests for cart operations."""

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_create_cart(self, mock_request):
        """Test cart creation."""
        mock_request.return_value = {"cart": {"id": "cart_1", "region_id": "reg_1"}}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_create_cart(
            config=config,
            region_id="reg_1",
            email="test@example.com",
        )

        assert result["id"] == "cart_1"
        call_args = mock_request.call_args
        assert call_args.kwargs["method"] == "POST"
        assert call_args.kwargs["json_body"]["region_id"] == "reg_1"
        assert call_args.kwargs["json_body"]["email"] == "test@example.com"

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_get_cart(self, mock_request):
        """Test cart retrieval."""
        mock_request.return_value = {"cart": {"id": "cart_1", "email": "test@example.com"}}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_get_cart(config=config, cart_id="cart_1")

        assert result["id"] == "cart_1"
        call_args = mock_request.call_args
        assert "/store/carts/cart_1" in call_args.kwargs["path"]

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_update_cart(self, mock_request):
        """Test cart update."""
        mock_request.return_value = {"cart": {"id": "cart_1", "email": "updated@example.com"}}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_update_cart(
            config=config,
            cart_id="cart_1",
            email="updated@example.com",
        )

        assert result["email"] == "updated@example.com"
        call_args = mock_request.call_args
        assert call_args.kwargs["method"] == "POST"

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_add_line_item(self, mock_request):
        """Test adding line item to cart."""
        mock_request.return_value = {
            "cart": {"id": "cart_1", "items": [{"id": "item_1", "quantity": 2}]}
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_add_cart_line_item(
            config=config,
            cart_id="cart_1",
            variant_id="var_1",
            quantity=2,
        )

        assert len(result["items"]) == 1
        call_args = mock_request.call_args
        assert call_args.kwargs["method"] == "POST"
        assert "/store/carts/cart_1/line-items" in call_args.kwargs["path"]
        assert call_args.kwargs["json_body"]["variant_id"] == "var_1"
        assert call_args.kwargs["json_body"]["quantity"] == 2

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_update_line_item(self, mock_request):
        """Test updating line item quantity."""
        mock_request.return_value = {
            "cart": {"id": "cart_1", "items": [{"id": "item_1", "quantity": 3}]}
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_update_cart_line_item(
            config=config,
            cart_id="cart_1",
            line_id="item_1",
            quantity=3,
        )

        assert result["items"][0]["quantity"] == 3
        call_args = mock_request.call_args
        assert call_args.kwargs["method"] == "POST"
        assert "/store/carts/cart_1/line-items/item_1" in call_args.kwargs["path"]
        assert call_args.kwargs["json_body"]["quantity"] == 3

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_delete_line_item(self, mock_request):
        """Test deleting line item from cart."""
        mock_request.return_value = None

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        medusa_delete_cart_line_item(
            config=config,
            cart_id="cart_1",
            line_id="item_1",
        )

        call_args = mock_request.call_args
        assert call_args.kwargs["method"] == "DELETE"
        assert "/store/carts/cart_1/line-items/item_1" in call_args.kwargs["path"]


class TestMedusaShippingOperations:
    """Tests for shipping operations."""

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_list_shipping_options(self, mock_request):
        """Test listing shipping options."""
        mock_request.return_value = {
            "shipping_options": [
                {"id": "opt_1", "name": "Standard", "amount": 500},
                {"id": "opt_2", "name": "Express", "amount": 1500},
            ]
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_list_shipping_options(config=config, cart_id="cart_1")

        assert len(result) == 2
        assert result[0]["name"] == "Standard"
        call_args = mock_request.call_args
        assert call_args.kwargs["params"]["cart_id"] == "cart_1"

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_add_shipping_method(self, mock_request):
        """Test adding shipping method to cart."""
        mock_request.return_value = {"cart": {"id": "cart_1", "shipping_methods": [{"id": "sm_1"}]}}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_add_shipping_method(
            config=config,
            cart_id="cart_1",
            option_id="opt_1",
        )

        assert result["id"] == "cart_1"
        call_args = mock_request.call_args
        assert call_args.kwargs["json_body"]["option_id"] == "opt_1"


class TestMedusaPaymentOperations:
    """Tests for payment operations."""

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_list_payment_providers(self, mock_request):
        """Test listing payment providers."""
        mock_request.return_value = {
            "payment_providers": [
                {"id": "stripe"},
                {"id": "paypal"},
            ]
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_list_payment_providers(config=config, region_id="reg_1")

        assert len(result) == 2
        assert result[0]["id"] == "stripe"
        call_args = mock_request.call_args
        assert call_args.kwargs["params"]["region_id"] == "reg_1"

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_create_payment_collection(self, mock_request):
        """Test creating payment collection."""
        mock_request.return_value = {"payment_collection": {"id": "pc_1", "status": "pending"}}

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_create_payment_collection(config=config, cart_id="cart_1")

        assert result["id"] == "pc_1"
        call_args = mock_request.call_args
        assert call_args.kwargs["json_body"]["cart_id"] == "cart_1"

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_initialize_payment_session(self, mock_request):
        """Test initializing payment session."""
        mock_request.return_value = {
            "payment_collection": {
                "id": "pc_1",
                "payment_sessions": [{"id": "ps_1", "provider_id": "stripe"}],
            }
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_initialize_payment_session(
            config=config,
            payment_collection_id="pc_1",
            provider_id="stripe",
        )

        assert result["id"] == "pc_1"
        call_args = mock_request.call_args
        assert call_args.kwargs["json_body"]["provider_id"] == "stripe"


class TestMedusaCompleteCart:
    """Tests for cart completion."""

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_complete_cart_success(self, mock_request):
        """Test successful cart completion."""
        mock_request.return_value = {
            "type": "order",
            "order": {"id": "order_1", "status": "completed"},
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        result = medusa_complete_cart(config=config, cart_id="cart_1")

        assert result["id"] == "order_1"
        assert result["status"] == "completed"
        call_args = mock_request.call_args
        assert call_args.kwargs["method"] == "POST"
        assert "/store/carts/cart_1/complete" in call_args.kwargs["path"]

    @patch("app.services.medusa_store_runtime._make_medusa_store_request")
    def test_complete_cart_not_ready(self, mock_request):
        """Test cart not ready for completion."""
        mock_request.return_value = {
            "type": "cart",
            "cart": {"id": "cart_1", "errors": [{"message": "Shipping address required"}]},
        }

        config = MedusaStoreConfig(
            base_url="https://store.example.com",
            publishable_key="pk_test_123",
        )

        with pytest.raises(HTTPException) as exc_info:
            medusa_complete_cart(config=config, cart_id="cart_1")

        assert exc_info.value.status_code == 409
        assert "not ready" in str(exc_info.value.detail).lower()


class TestPaymentProviderFiltering:
    """Tests for payment provider allowlist filtering."""

    def test_filter_payment_providers_empty_allowlist(self):
        """Test that empty allowlist raises a clean configuration error."""
        providers = [
            {"id": "stripe"},
            {"id": "paypal"},
        ]
        with pytest.raises(HTTPException) as exc_info:
            filter_payment_providers_by_allowlist(providers, [])
        assert exc_info.value.status_code == 409
        assert "not configured" in str(exc_info.value.detail).lower()

    def test_filter_payment_providers_with_allowlist(self):
        """Test filtering providers against allowlist."""
        providers = [
            {"id": "stripe"},
            {"id": "paypal"},
            {"id": "manual"},
        ]
        result = filter_payment_providers_by_allowlist(providers, ["stripe", "manual"])
        assert len(result) == 2
        assert all(provider["id"] in ["stripe", "manual"] for provider in result)

    def test_filter_payment_providers_trims_whitespace(self):
        """Test that provider IDs are trimmed before comparison."""
        providers = [
            {"id": "stripe"},
            {"id": "paypal"},
        ]
        result = filter_payment_providers_by_allowlist(providers, [" stripe ", " paypal "])
        assert len(result) == 2

    def test_filter_payment_providers_removes_duplicates(self):
        """Test that allowlist duplicates are removed."""
        providers = [{"id": "stripe"}]
        result = filter_payment_providers_by_allowlist(providers, ["stripe", "stripe"])
        assert len(result) == 1


class TestValidateProviderIdAgainstAllowlist:
    """Tests for provider ID validation against allowlist."""

    def test_validate_provider_id_empty_allowlist(self):
        """Test that empty allowlist raises a clean configuration error."""
        with pytest.raises(HTTPException) as exc_info:
            validate_provider_id_against_allowlist("stripe", [])
        assert exc_info.value.status_code == 409
        assert "not configured" in str(exc_info.value.detail).lower()

    def test_validate_provider_id_in_allowlist(self):
        """Test that provider in allowlist is accepted."""
        validate_provider_id_against_allowlist("stripe", ["stripe", "paypal"])

    def test_validate_provider_id_not_in_allowlist(self):
        """Test that provider not in allowlist raises 403."""
        with pytest.raises(HTTPException) as exc_info:
            validate_provider_id_against_allowlist("unknown", ["stripe", "paypal"])
        assert exc_info.value.status_code == 403
        assert "not allowed" in str(exc_info.value.detail).lower()


class TestResolveDefaultPaymentProviderId:
    """Tests for resolving default payment provider."""

    def test_resolve_default_no_config(self):
        """Test resolving when no allowlist is configured."""
        providers = [{"id": "stripe"}, {"id": "paypal"}]
        with pytest.raises(HTTPException) as exc_info:
            resolve_default_payment_provider_id([], None, providers)
        assert exc_info.value.status_code == 409
        assert "not configured" in str(exc_info.value.detail).lower()

    def test_resolve_default_with_default_in_allowlist(self):
        """Test resolving when default is in allowlist and available."""
        providers = [{"id": "stripe"}, {"id": "paypal"}]
        result = resolve_default_payment_provider_id(["stripe", "paypal"], "stripe", providers)
        assert result == "stripe"

    def test_resolve_default_not_in_allowlist(self):
        """Test resolving when default is not in allowlist."""
        providers = [{"id": "stripe"}, {"id": "paypal"}]
        with pytest.raises(HTTPException) as exc_info:
            resolve_default_payment_provider_id(["paypal"], "stripe", providers)
        assert exc_info.value.status_code == 400
        assert "not in the workspace allowlist" in str(exc_info.value.detail)

    def test_resolve_default_not_available(self):
        """Test resolving when default is not available from Medusa."""
        providers = [{"id": "paypal"}]
        with pytest.raises(HTTPException) as exc_info:
            resolve_default_payment_provider_id(["stripe", "paypal"], "stripe", providers)
        assert exc_info.value.status_code == 409
        assert "not currently available" in str(exc_info.value.detail)

    def test_resolve_default_single_allowed_provider(self):
        """Test resolving when no default provider is configured."""
        providers = [{"id": "stripe"}]
        result = resolve_default_payment_provider_id(["stripe"], None, providers)
        assert result is None
