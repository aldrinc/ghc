from __future__ import annotations

from typing import Any, Optional

from pydantic import AnyUrl, BaseModel


class PublicCheckoutRequest(BaseModel):
    funnelSlug: str
    variantId: Optional[str] = None
    selection: dict[str, Any]
    quantity: int
    successUrl: AnyUrl
    cancelUrl: AnyUrl
    pageId: Optional[str] = None
    visitorId: Optional[str] = None
    sessionId: Optional[str] = None
    utm: Optional[dict[str, Any]] = None


# =============================================================================
# Medusa Store API Response Schemas
# =============================================================================


class MedusaRegion(BaseModel):
    """Medusa region data from Store API."""

    id: str
    name: str
    currency_code: str
    tax_rate: Optional[float] = None
    countries: list[dict[str, Any]] = []


class MedusaProductVariant(BaseModel):
    """Medusa product variant data from Store API."""

    id: str
    title: str
    sku: Optional[str] = None
    barcode: Optional[str] = None
    allow_backorder: bool = False
    manage_inventory: bool = True
    inventory_quantity: Optional[int] = None
    prices: list[dict[str, Any]] = []
    options: dict[str, str] = {}


class MedusaProduct(BaseModel):
    """Medusa product data from Store API."""

    id: str
    title: str
    handle: str
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    status: str = "published"
    variants: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    collection_id: Optional[str] = None
    categories: list[dict[str, Any]] = []


class MedusaCollection(BaseModel):
    """Medusa collection data from Store API."""

    id: str
    title: str
    handle: str
    products: list[dict[str, Any]] = []


class MedusaCategory(BaseModel):
    """Medusa product category data from Store API."""

    id: str
    name: str
    handle: str
    description: Optional[str] = None
    parent_category_id: Optional[str] = None
    category_children: list[dict[str, Any]] = []


class MedusaCartAddress(BaseModel):
    """Medusa cart address data."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: Optional[str] = None
    phone: Optional[str] = None


class MedusaCartLineItem(BaseModel):
    """Medusa cart line item data."""

    id: str
    cart_id: str
    title: str
    description: Optional[str] = None
    variant_id: str
    quantity: int
    unit_price: int
    subtotal: Optional[int] = None
    tax_total: Optional[int] = None
    total: Optional[int] = None
    variant: Optional[dict[str, Any]] = None


class MedusaCart(BaseModel):
    """Medusa cart data from Store API."""

    id: str
    email: Optional[str] = None
    region_id: str
    shipping_address: Optional[dict[str, Any]] = None
    billing_address: Optional[dict[str, Any]] = None
    items: list[dict[str, Any]] = []
    shipping_methods: list[dict[str, Any]] = []
    subtotal: Optional[int] = None
    tax_total: Optional[int] = None
    shipping_total: Optional[int] = None
    discount_total: Optional[int] = None
    total: Optional[int] = None
    currency_code: str


class MedusaShippingOption(BaseModel):
    """Medusa shipping option data."""

    id: str
    name: str
    price_type: str
    amount: Optional[int] = None
    currency_code: Optional[str] = None
    region_id: str


class MedusaPaymentProvider(BaseModel):
    """Medusa payment provider data."""

    id: str


class MedusaPaymentSession(BaseModel):
    """Medusa payment session data."""

    id: str
    provider_id: str
    status: str
    amount: int
    data: dict[str, Any] = {}


class MedusaPaymentCollection(BaseModel):
    """Medusa payment collection data."""

    id: str
    status: str
    amount: int
    currency_code: str
    payment_sessions: list[dict[str, Any]] = []


# =============================================================================
# Site Commerce API Request/Response Schemas
# =============================================================================


class SiteCommerceCartCreateRequest(BaseModel):
    """Request to create a new cart."""

    region_id: str
    country_code: Optional[str] = None
    email: Optional[str] = None
    shipping_address: Optional[dict[str, Any]] = None
    items: Optional[list[dict[str, Any]]] = None


class SiteCommerceCartUpdateRequest(BaseModel):
    """Request to update a cart."""

    email: Optional[str] = None
    shipping_address: Optional[dict[str, Any]] = None
    billing_address: Optional[dict[str, Any]] = None


class SiteCommerceLineItemAddRequest(BaseModel):
    """Request to add a line item to cart."""

    variant_id: str
    quantity: int = 1


class SiteCommerceLineItemUpdateRequest(BaseModel):
    """Request to update a line item quantity."""

    quantity: int


class SiteCommerceShippingMethodRequest(BaseModel):
    """Request to add a shipping method."""

    cart_id: str
    option_id: str


class SiteCommercePaymentSessionRequest(BaseModel):
    """Request to initialize a payment session."""

    provider_id: str


class SiteCommerceProductQuery(BaseModel):
    """Query parameters for fetching products."""

    product_id: Optional[str] = None
    product_handle: Optional[str] = None
    collection_id: Optional[str] = None
    category_id: Optional[str] = None
    limit: int = 100
    offset: int = 0


class SiteCommerceData(BaseModel):
    """Rich commerce data for site pages."""

    # Site metadata
    siteFamily: Optional[str] = None
    commerceProvider: Optional[str] = None

    # Catalog data
    regions: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    collections: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []

    # Current product (if specified)
    currentProduct: Optional[dict[str, Any]] = None

    # Cart data (if cart_id provided)
    cart: Optional[dict[str, Any]] = None

    # Shipping options (if cart_id provided)
    shippingOptions: list[dict[str, Any]] = []

    # Payment providers (if region_id provided)
    paymentProviders: list[dict[str, Any]] = []

    # Default payment provider (if region_id provided)
    defaultPaymentProviderId: Optional[str] = None


class SiteCommerceCartResponse(BaseModel):
    """Response for cart operations."""

    cart: dict[str, Any]


class SiteCommerceShippingOptionsResponse(BaseModel):
    """Response for shipping options."""

    shipping_options: list[dict[str, Any]]


class SiteCommercePaymentProvidersResponse(BaseModel):
    """Response for payment providers."""

    payment_providers: list[dict[str, Any]]
    default_payment_provider_id: Optional[str] = None


class SiteCommercePaymentSessionResponse(BaseModel):
    """Response for payment session initialization."""

    payment_collection: dict[str, Any]


class SiteCommerceCompleteResponse(BaseModel):
    """Response for cart completion."""

    type: str
    order: Optional[dict[str, Any]] = None
    cart: Optional[dict[str, Any]] = None
