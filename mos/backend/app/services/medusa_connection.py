"""Medusa Admin API connection management.

This module provides workspace-level Medusa connection configuration and status checking.
It makes direct HTTP calls to the Medusa Admin API using workspace-entered credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import ClientMedusaConfig, StripeAccountProfile


UNSET = object()


_MEDUSA_URL_RE = re.compile(
    r"^https?://"
    r"("
    r"localhost"  # localhost
    r"|127\.0\.0\.1"  # IPv4 loopback
    r"|\[?::1\]?"  # IPv6 loopback
    r"|[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9][a-z0-9\-]*)+\.[a-z]{2,63}"  # hostname with TLD
    r"|[a-z0-9][a-z0-9\-]*:\d+"  # hostname without TLD but with port (local dev)
    r")"
    r"(?::\d+)?"  # Optional port (for TLD hostnames)
    r"(?:/[a-z0-9\-]*)*$",
    re.IGNORECASE,
)

# Medusa Admin API endpoints
_MEDUSA_ADMIN_PRODUCTS_PATH = "/admin/products"
_MEDUSA_ADMIN_PRODUCTS_DETAIL_PATH = "/admin/products/{product_id}"
_MEDUSA_ADMIN_VARIANTS_PATH = "/admin/products/{product_id}/variants"
_MEDUSA_ADMIN_VARIANT_DETAIL_PATH = "/admin/products/{product_id}/variants/{variant_id}"
_MEDUSA_ADMIN_STORE_PATH = "/admin/store"
_MEDUSA_ADMIN_AUTH_PATH = "/auth/user/emailpass"

# Default option title for products without explicit options
_DEFAULT_OPTION_TITLE = "Variant"


@dataclass(frozen=True)
class MedusaAdminToken:
    """Result of a Medusa admin login."""

    token: str
    user_id: str | None = None
    expires_at: datetime | None = None


def medusa_admin_login(
    *,
    base_url: str,
    email: str,
    password: str,
    timeout_seconds: float = 30.0,
) -> MedusaAdminToken:
    """Log in to Medusa Admin API and obtain a JWT token.

    This function authenticates with email/password against the Medusa Admin API
    and returns the JWT token for subsequent authenticated requests.

    Args:
        base_url: Medusa backend URL (e.g., http://localhost:9000)
        email: Admin user email
        password: Admin user password
        timeout_seconds: Request timeout

    Returns:
        MedusaAdminToken with the JWT token

    Raises:
        HTTPException: If authentication fails
    """
    headers = {
        "Content-Type": "application/json",
    }

    payload = {
        "email": email,
        "password": password,
    }

    url = f"{base_url.rstrip('/')}{_MEDUSA_ADMIN_AUTH_PATH}"
    request_timeout = httpx.Timeout(
        timeout=timeout_seconds,
        connect=min(timeout_seconds, 10.0),
    )

    try:
        with httpx.Client(timeout=request_timeout) as client:
            response = client.post(
                url=url,
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Medusa auth request timed out after {timeout_seconds:.1f}s.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Medusa auth request failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail = _error_detail_from_response(response)
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Medusa authentication failed: Invalid credentials. {detail}",
            )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Medusa auth error: {detail}",
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa auth returned invalid JSON.",
        ) from exc

    # Medusa v2 returns the token in different formats depending on version
    # Try common response structures
    token = None
    user_id = None

    if isinstance(result, dict):
        # Format: { "token": "..." }
        token = result.get("token") or result.get("access_token") or result.get("jwt_token")
        # Format: { "user": { "id": "..." } }
        user_data = result.get("user", {})
        if isinstance(user_data, dict):
            user_id = user_data.get("id")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Medusa auth response missing token: {result}",
        )

    return MedusaAdminToken(
        token=token,
        user_id=user_id,
    )


@dataclass(frozen=True)
class MedusaConnectionStatus:
    state: str
    message: str
    base_url: str | None = None
    last_check_at: datetime | None = None


def _normalize_medusa_url(raw_url: str) -> str:
    """Normalize and validate a Medusa backend URL."""
    if not isinstance(raw_url, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Medusa base URL must be a string.",
        )

    cleaned = raw_url.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Medusa base URL cannot be empty.",
        )

    # Ensure https
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"

    # Remove trailing slash
    cleaned = cleaned.rstrip("/")

    if not _MEDUSA_URL_RE.match(cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Medusa base URL must be a valid HTTP(S) URL (e.g., https://my-store.medusa.example.com).",
        )

    return cleaned


def _error_detail_from_response(response: httpx.Response) -> str:
    """Extract error detail from HTTP response."""
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text or response.reason_phrase or f"HTTP {response.status_code}"

    if isinstance(body, dict):
        # Medusa error format
        detail = body.get("message") or body.get("detail") or body.get("error")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str):
                return message
        # Fallback to string representation
        if "errors" in body:
            errors = body["errors"]
            if isinstance(errors, list) and errors:
                first_error = errors[0]
                if isinstance(first_error, dict):
                    return first_error.get("message", str(first_error))
                return str(first_error)
        return str(body)

    return str(body)


def _make_medusa_admin_request(
    *,
    base_url: str,
    api_key: str,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> Any:
    """Make a direct HTTP request to the Medusa Admin API.

    Uses the workspace-entered base URL and admin API key for authentication.
    The admin token is sent via Bearer auth for Admin API calls.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    url = f"{base_url}{path}"
    request_timeout = httpx.Timeout(
        timeout=timeout_seconds,
        connect=min(timeout_seconds, 10.0),
    )

    try:
        with httpx.Client(timeout=request_timeout) as client:
            response = client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Medusa API request timed out after {timeout_seconds:.1f}s ({method} {path}).",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Medusa API request failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail = _error_detail_from_response(response)
        # Map common Medusa errors to appropriate HTTP status codes
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Medusa authentication failed: {detail}",
            )
        if response.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Medusa permission denied: {detail}",
            )
        if response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Medusa resource not found: {detail}",
            )
        if response.status_code == 409:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Medusa conflict: {detail}",
            )
        if response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Medusa server error: {detail}",
            )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Medusa API error: {detail}",
        )

    # Handle empty responses
    if response.status_code == 204:
        return None

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid JSON.",
        ) from exc


def get_client_medusa_config(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> ClientMedusaConfig | None:
    """Get the Medusa configuration for a workspace."""
    from sqlalchemy import select

    return session.scalar(
        select(ClientMedusaConfig).where(
            ClientMedusaConfig.org_id == org_id,
            ClientMedusaConfig.client_id == client_id,
        )
    )


def upsert_client_medusa_config(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    base_url: str,
    admin_api_key: str | None | object = UNSET,
    publishable_key: str | None | object = UNSET,
    stripe_account_profile_id: str | None | object = UNSET,
    default_payment_provider_id: str | None | object = UNSET,
    allowed_payment_provider_ids: list[str] | None | object = UNSET,
    webhook_routing_mode: str | None | object = UNSET,
) -> ClientMedusaConfig:
    """Create or update a workspace's Medusa configuration."""
    normalized_url = _normalize_medusa_url(base_url)

    existing = get_client_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )

    now = datetime.now(timezone.utc)

    if existing:
        existing.base_url = normalized_url
        if admin_api_key is not UNSET:
            existing.admin_api_key_encrypted = admin_api_key
        if publishable_key is not UNSET:
            existing.publishable_key_encrypted = publishable_key
        if stripe_account_profile_id is not UNSET:
            existing.stripe_account_profile_id = stripe_account_profile_id
        if default_payment_provider_id is not UNSET:
            existing.default_payment_provider_id = default_payment_provider_id
        if allowed_payment_provider_ids is not UNSET:
            existing.allowed_payment_provider_ids = allowed_payment_provider_ids
        if webhook_routing_mode is not UNSET:
            existing.webhook_routing_mode = webhook_routing_mode
        existing.updated_at = now
        existing.connection_status = "not_tested"
        existing.last_connection_error = None
        session.add(existing)
        session.flush()
        return existing

    config = ClientMedusaConfig(
        org_id=org_id,
        client_id=client_id,
        base_url=normalized_url,
        admin_api_key_encrypted=admin_api_key if admin_api_key is not UNSET else None,
        publishable_key_encrypted=publishable_key if publishable_key is not UNSET else None,
        connection_status="not_tested",
        stripe_account_profile_id=(
            stripe_account_profile_id if stripe_account_profile_id is not UNSET else None
        ),
        default_payment_provider_id=(
            default_payment_provider_id if default_payment_provider_id is not UNSET else None
        ),
        allowed_payment_provider_ids=(
            allowed_payment_provider_ids if allowed_payment_provider_ids is not UNSET else []
        ),
        webhook_routing_mode=(
            webhook_routing_mode if webhook_routing_mode is not UNSET else "shared_ingress"
        ),
    )
    session.add(config)
    session.flush()
    return config


def test_medusa_connection(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> MedusaConnectionStatus:
    """Test the Medusa connection for a workspace and update status.

    Makes a direct call to the Medusa Admin API to verify credentials.
    """
    config = get_client_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )

    if not config:
        return MedusaConnectionStatus(
            state="not_configured",
            message="Medusa connection is not configured for this workspace.",
        )

    if not config.admin_api_key_encrypted:
        return MedusaConnectionStatus(
            state="not_configured",
            message="Medusa admin API key is not set.",
            base_url=config.base_url,
        )

    now = datetime.now(timezone.utc)

    try:
        # Test connection with a lightweight Admin API request.
        result = _make_medusa_admin_request(
            base_url=config.base_url,
            api_key=config.admin_api_key_encrypted,
            method="GET",
            path=f"{_MEDUSA_ADMIN_PRODUCTS_PATH}?limit=1",
            timeout_seconds=10.0,
        )

        # Validate response structure
        if not isinstance(result, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Medusa API returned invalid store info.",
            )

        # Update status to connected
        config.connection_status = "connected"
        config.last_connection_check_at = now
        config.last_connection_error = None
        config.updated_at = now
        session.add(config)
        session.flush()

        return MedusaConnectionStatus(
            state="connected",
            message="Medusa connection is active.",
            base_url=config.base_url,
            last_check_at=now,
        )

    except HTTPException as exc:
        error_detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        config.connection_status = "error"
        config.last_connection_check_at = now
        config.last_connection_error = error_detail
        config.updated_at = now
        session.add(config)
        session.flush()

        return MedusaConnectionStatus(
            state="error",
            message=f"Medusa connection failed: {error_detail}",
            base_url=config.base_url,
            last_check_at=now,
        )


def get_medusa_connection_status(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> MedusaConnectionStatus:
    """Get the current Medusa connection status without testing."""
    config = get_client_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )

    if not config:
        return MedusaConnectionStatus(
            state="not_configured",
            message="Medusa connection is not configured for this workspace.",
        )

    if not config.admin_api_key_encrypted:
        return MedusaConnectionStatus(
            state="not_configured",
            message="Medusa admin API key is not set.",
            base_url=config.base_url,
        )

    state = config.connection_status or "not_tested"
    message = "Medusa connection status unknown."

    if state == "connected":
        message = "Medusa connection is active."
    elif state == "error":
        message = config.last_connection_error or "Medusa connection failed."

    return MedusaConnectionStatus(
        state=state,
        message=message,
        base_url=config.base_url,
        last_check_at=config.last_connection_check_at,
    )


def mask_medusa_config(config: ClientMedusaConfig) -> dict[str, Any]:
    """Return a masked version of Medusa config for API responses."""
    return {
        "id": str(config.id),
        "baseUrl": config.base_url,
        "hasAdminApiKey": bool(config.admin_api_key_encrypted),
        "hasPublishableKey": bool(config.publishable_key_encrypted),
        "connectionStatus": config.connection_status,
        "lastConnectionCheckAt": config.last_connection_check_at.isoformat()
        if config.last_connection_check_at
        else None,
        "lastConnectionError": config.last_connection_error,
        "stripeAccountProfileId": str(config.stripe_account_profile_id)
        if config.stripe_account_profile_id
        else None,
        "defaultPaymentProviderId": config.default_payment_provider_id,
        "allowedPaymentProviderIds": list(config.allowed_payment_provider_ids or []),
        "webhookRoutingMode": config.webhook_routing_mode,
        "createdAt": config.created_at.isoformat(),
        "updatedAt": config.updated_at.isoformat(),
    }


# =============================================================================
# Stripe Account Profile Operations
# =============================================================================


def list_stripe_account_profiles(
    *,
    session: Session,
    org_id: str,
) -> list[StripeAccountProfile]:
    """List all Stripe account profiles for an org."""
    from sqlalchemy import select

    return list(
        session.scalars(
            select(StripeAccountProfile)
            .where(StripeAccountProfile.org_id == org_id)
            .order_by(StripeAccountProfile.created_at.asc())
        ).all()
    )


def get_stripe_account_profile(
    *,
    session: Session,
    org_id: str,
    profile_id: str,
) -> StripeAccountProfile | None:
    """Get a Stripe account profile by ID, verifying org ownership."""
    from sqlalchemy import select

    return session.scalar(
        select(StripeAccountProfile).where(
            StripeAccountProfile.id == profile_id,
            StripeAccountProfile.org_id == org_id,
        )
    )


def get_stripe_account_profile_by_id(
    *,
    session: Session,
    profile_id: str,
) -> StripeAccountProfile | None:
    """Get a Stripe account profile by ID without org filter."""
    from sqlalchemy import select

    return session.scalar(select(StripeAccountProfile).where(StripeAccountProfile.id == profile_id))


def create_stripe_account_profile(
    *,
    session: Session,
    org_id: str,
    label: str,
    stripe_account_id: str | None = None,
    secret_key_ref: str | None = None,
    webhook_secret_ref: str | None = None,
    mode: str = "shared",
) -> StripeAccountProfile:
    """Create a new Stripe account profile for an org."""
    profile = StripeAccountProfile(
        org_id=org_id,
        label=label,
        stripe_account_id=stripe_account_id,
        secret_key_ref=secret_key_ref,
        webhook_secret_ref=webhook_secret_ref,
        mode=mode,
        status="active",
    )
    session.add(profile)
    session.flush()
    return profile


def update_stripe_account_profile(
    *,
    session: Session,
    org_id: str,
    profile_id: str,
    label: str | None = None,
    stripe_account_id: str | None = None,
    secret_key_ref: str | None = None,
    webhook_secret_ref: str | None = None,
    mode: str | None = None,
    status: str | None = None,
) -> StripeAccountProfile:
    """Update an existing Stripe account profile."""
    profile = get_stripe_account_profile(
        session=session,
        org_id=org_id,
        profile_id=profile_id,
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stripe account profile not found.",
        )

    now = datetime.now(timezone.utc)

    if label is not None:
        profile.label = label
    if stripe_account_id is not None:
        profile.stripe_account_id = stripe_account_id
    if secret_key_ref is not None:
        profile.secret_key_ref = secret_key_ref
    if webhook_secret_ref is not None:
        profile.webhook_secret_ref = webhook_secret_ref
    if mode is not None:
        profile.mode = mode
    if status is not None:
        profile.status = status

    profile.updated_at = now
    session.add(profile)
    session.flush()
    return profile


def count_workspaces_using_stripe_profile(
    *,
    session: Session,
    stripe_account_profile_id: str,
    exclude_client_id: str | None = None,
) -> int:
    """Count how many workspaces are using a given Stripe profile."""
    from sqlalchemy import func, select

    query = (
        select(func.count())
        .select_from(ClientMedusaConfig)
        .where(ClientMedusaConfig.stripe_account_profile_id == stripe_account_profile_id)
    )
    if exclude_client_id:
        query = query.where(ClientMedusaConfig.client_id != exclude_client_id)

    return session.scalar(query) or 0


def has_direct_webhook_workspace(
    *,
    session: Session,
    stripe_account_profile_id: str,
    exclude_client_id: str | None = None,
) -> bool:
    """Return whether any workspace on the profile uses direct webhook routing."""
    from sqlalchemy import select

    query = select(ClientMedusaConfig.id).where(
        ClientMedusaConfig.stripe_account_profile_id == stripe_account_profile_id,
        ClientMedusaConfig.webhook_routing_mode == "direct",
    )
    if exclude_client_id:
        query = query.where(ClientMedusaConfig.client_id != exclude_client_id)

    return session.scalar(query.limit(1)) is not None


def mask_stripe_account_profile(profile: StripeAccountProfile) -> dict[str, Any]:
    """Return a masked version of Stripe account profile for API responses."""
    return {
        "id": str(profile.id),
        "orgId": str(profile.org_id),
        "label": profile.label,
        "stripeAccountId": profile.stripe_account_id,
        "hasSecretKeyRef": bool(profile.secret_key_ref),
        "hasWebhookSecretRef": bool(profile.webhook_secret_ref),
        "mode": profile.mode,
        "status": profile.status,
        "createdAt": profile.created_at.isoformat(),
        "updatedAt": profile.updated_at.isoformat(),
    }


# =============================================================================
# Medusa Admin API Operations
# =============================================================================


def medusa_create_product(
    *,
    base_url: str,
    api_key: str,
    title: str,
    description: str = "",
    handle: str | None = None,
    options: list[dict[str, Any]] | None = None,
    product_status: str = "draft",
    sales_channel_ids: list[str] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Create a product in Medusa via Admin API.

    The Medusa v2 API expects the product object directly in the request body,
    not wrapped in a "product" key.

    Args:
        base_url: Medusa backend URL
        api_key: Admin API key
        title: Product title (required)
        description: Product description
        handle: Optional URL handle (auto-generated if not provided)
        options: Product options list, e.g. [{"title": "Size", "values": ["S"]}]
        product_status: Product status (draft or published)
        sales_channel_ids: Optional list of sales channel IDs to associate
        timeout_seconds: Request timeout

    Returns:
        The created product data including the product ID.
    """
    # Build the product payload - Medusa v2 expects the object directly
    payload: dict[str, Any] = {
        "title": title,
        "status": product_status,
    }

    if description:
        payload["description"] = description
    if handle:
        payload["handle"] = handle

    # Options are required for Medusa products
    # If not provided, use a default option that allows variants to be created
    if options:
        payload["options"] = options
    else:
        payload["options"] = [{"title": _DEFAULT_OPTION_TITLE, "values": [_DEFAULT_OPTION_TITLE]}]

    # Sales channels are required for products to be visible in Store API
    if sales_channel_ids:
        payload["sales_channels"] = [{"id": sid} for sid in sales_channel_ids]

    result = _make_medusa_admin_request(
        base_url=base_url,
        api_key=api_key,
        method="POST",
        path=_MEDUSA_ADMIN_PRODUCTS_PATH,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid product response.",
        )

    # Medusa v2 returns the product directly
    product = result.get("product") or result
    if not isinstance(product, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid product data.",
        )

    return product


def medusa_get_product(
    *,
    base_url: str,
    api_key: str,
    product_id: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Fetch a product from Medusa by ID."""
    path = _MEDUSA_ADMIN_PRODUCTS_DETAIL_PATH.format(product_id=product_id)

    result = _make_medusa_admin_request(
        base_url=base_url,
        api_key=api_key,
        method="GET",
        path=path,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid product response.",
        )

    product = result.get("product") or result
    if not isinstance(product, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid product data.",
        )

    return product


def medusa_update_product_sales_channels(
    *,
    base_url: str,
    api_key: str,
    product_id: str,
    sales_channel_ids: list[str],
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Update a product's sales channels in Medusa via Admin API.

    This is required for products to be visible in the Store API.

    Args:
        base_url: Medusa backend URL
        api_key: Admin API key
        product_id: Medusa product ID
        sales_channel_ids: List of sales channel IDs to associate
        timeout_seconds: Request timeout

    Returns:
        The updated product data.
    """
    payload = {"sales_channels": [{"id": sid} for sid in sales_channel_ids]}

    path = _MEDUSA_ADMIN_PRODUCTS_DETAIL_PATH.format(product_id=product_id)

    result = _make_medusa_admin_request(
        base_url=base_url,
        api_key=api_key,
        method="POST",
        path=path,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid product response.",
        )

    product = result.get("product") or result
    if not isinstance(product, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid product data.",
        )

    return product


def medusa_create_variant(
    *,
    base_url: str,
    api_key: str,
    product_id: str,
    title: str,
    prices: list[dict[str, Any]],
    sku: str | None = None,
    barcode: str | None = None,
    inventory_quantity: int | None = None,
    inventory_policy: str | None = None,
    options: dict[str, str] | None = None,
    region_ids: list[str] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Create a variant for a product in Medusa via Admin API.

    The Medusa v2 API expects the variant object directly in the request body,
    not wrapped in a "variant" key.

    Args:
        base_url: Medusa backend URL
        api_key: Admin API key
        product_id: Medusa product ID
        title: Variant title
        prices: List of price objects with 'amount' (in cents) and 'currency_code'
        sku: Optional SKU
        barcode: Optional barcode
        inventory_quantity: Optional initial inventory quantity
        options: Optional variant options as key-value pairs (option_title -> value)
        region_ids: Optional list of region IDs to associate with prices (for region-specific pricing)
        timeout_seconds: Request timeout

    Returns:
        The created variant data including the variant ID.
    """
    # Build the variant payload - Medusa v2 expects the object directly
    # If region_ids provided, add them to each price for region-specific pricing
    processed_prices = prices
    if region_ids:
        processed_prices = []
        for price in prices:
            for region_id in region_ids:
                processed_price = price.copy()
                processed_price["region_id"] = region_id
                processed_prices.append(processed_price)

    payload: dict[str, Any] = {
        "title": title,
        "prices": processed_prices,
        "manage_inventory": inventory_quantity is not None,
    }

    if sku:
        payload["sku"] = sku
    if barcode:
        payload["barcode"] = barcode
    if inventory_quantity is not None:
        payload["allow_backorder"] = (inventory_policy or "deny") == "continue"
    elif inventory_policy is not None:
        payload["allow_backorder"] = inventory_policy == "continue"
    if options:
        payload["options"] = options

    path = _MEDUSA_ADMIN_VARIANTS_PATH.format(product_id=product_id)

    result = _make_medusa_admin_request(
        base_url=base_url,
        api_key=api_key,
        method="POST",
        path=path,
        json_body=payload,  # Send directly, not wrapped
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid variant response.",
        )

    variant = result.get("variant") or result
    if (not isinstance(variant, dict) or not str(variant.get("id") or "").strip()) and isinstance(
        result.get("product"), dict
    ):
        product = result["product"]
        variants = product.get("variants")
        if isinstance(variants, list):
            normalized_title = title.strip().lower()
            matched_variants = [
                item
                for item in variants
                if isinstance(item, dict) and str(item.get("title") or "").strip().lower() == normalized_title
            ]
            if matched_variants:
                variant = matched_variants[-1]
    if not isinstance(variant, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid variant data.",
        )

    return variant


def medusa_update_variant(
    *,
    base_url: str,
    api_key: str,
    product_id: str,
    variant_id: str,
    fields: dict[str, Any],
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Update a variant in Medusa via Admin API."""
    path = _MEDUSA_ADMIN_VARIANT_DETAIL_PATH.format(
        product_id=product_id,
        variant_id=variant_id,
    )

    result = _make_medusa_admin_request(
        base_url=base_url,
        api_key=api_key,
        method="POST",
        path=path,
        json_body=fields,  # Send directly for updates
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid variant update response.",
        )

    variant = result.get("variant") or result
    if not isinstance(variant, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid variant data.",
        )

    return variant


def medusa_get_product_options(
    *,
    base_url: str,
    api_key: str,
    product_id: str,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """Fetch product options from Medusa.

    Returns the list of option configurations for the product.
    """
    product = medusa_get_product(
        base_url=base_url,
        api_key=api_key,
        product_id=product_id,
        timeout_seconds=timeout_seconds,
    )

    options = product.get("options", [])
    if not isinstance(options, list):
        return []

    return options
