from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, ORJSONResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session, init_db
from app.models import OAuthState, ProcessedWebhookEvent, ShopInstallation
from app.schemas import (
    AuditThemeBrandRequest,
    AuditThemeBrandResponse,
    AutoProvisionStorefrontTokenRequest,
    CatalogProductVariant,
    CatalogProductSummary,
    CreateCatalogProductRequest,
    CreateCatalogProductResponse,
    CreatedCatalogVariant,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    ExportThemeBrandResponse,
    ForwardOrderPayload,
    GetProductRequest,
    GetProductResponse,
    EmbeddedSessionResponse,
    InstallationResponse,
    LinkWorkspaceRequest,
    ListThemeBrandTemplateSlotsRequest,
    ListThemeBrandTemplateSlotsResponse,
    ThemeTemplateImageSlot,
    ThemeTemplateTextSlot,
    ListProductsRequest,
    ListProductsResponse,
    ResolveImageUrlsToShopifyFilesRequest,
    ResolveImageUrlsToShopifyFilesResponse,
    SyncThemeBrandRequest,
    SyncThemeBrandResponse,
    UpsertedPolicyPage,
    UpsertPolicyPagesRequest,
    UpsertPolicyPagesResponse,
    UpdateCatalogVariantRequest,
    UpdateCatalogVariantResponse,
    VerifyProductRequest,
    VerifyProductResponse,
    UpdateInstallationRequest,
)
from app.security import (
    normalize_shop_domain,
    require_internal_api_token,
    require_shopify_session_shop_domain,
    verify_oauth_hmac,
    verify_webhook_hmac,
)
from app.shopify_api import ShopifyApiClient, ShopifyApiError

app = FastAPI(title="Marketi Shopify Funnel App", default_response_class=ORJSONResponse)
shopify_api = ShopifyApiClient()

_SHOPIFY_COMPLIANCE_TOPICS = frozenset(
    {"customers/data_request", "customers/redact", "shop/redact"}
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/", include_in_schema=False)
def app_url_entrypoint(request: Request):
    """
    Shopify-owned entrypoint for the configured App URL.

    Behavior:
    - When launched from Shopify admin with a host param, route into /app.
    - When launched with a shop param (install context), route into /auth/install.
    - Otherwise return a non-error informational page.
    """
    raw_shop = request.query_params.get("shop")
    raw_host = request.query_params.get("host")
    raw_client_id = request.query_params.get("client_id")

    host = raw_host.strip() if isinstance(raw_host, str) else ""
    if host:
        query: dict[str, str] = {"host": host}
        if isinstance(raw_shop, str) and raw_shop.strip():
            query["shop"] = normalize_shop_domain(raw_shop)
        return RedirectResponse(
            url=f"{settings.app_base_url}/app?{urlencode(query)}",
            status_code=302,
        )

    if isinstance(raw_shop, str) and raw_shop.strip():
        query = {"shop": normalize_shop_domain(raw_shop)}
        if isinstance(raw_client_id, str) and raw_client_id.strip():
            query["client_id"] = raw_client_id.strip()
        return RedirectResponse(
            url=f"{settings.app_base_url}/auth/install?{urlencode(query)}",
            status_code=302,
        )

    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>mOS Shopify App</title>
  </head>
  <body>
    <main style="max-width:760px;margin:40px auto;padding:0 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
      <h1>mOS Shopify App</h1>
      <p>This URL is reserved for Shopify app launch and install flows.</p>
      <p>Install or open the app from Shopify Admin to continue.</p>
    </main>
  </body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


def _reject_direct_theme_write_operations() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Direct theme write operations are disabled. "
            "Use template ZIP export and extension-based rollout for storefront updates."
        ),
    )


def _reject_manual_theme_export_operations() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Theme file export for manual storefront code changes is disabled. "
            "Use theme app extensions for storefront updates."
        ),
    )


def _serialize_embedded_session(
    *,
    shop_domain: str,
    installation: ShopInstallation | None,
) -> EmbeddedSessionResponse:
    if not installation or installation.uninstalled_at is not None:
        return EmbeddedSessionResponse(
            shopDomain=shop_domain,
            isInstalled=False,
            linkedWorkspaceId=None,
            hasStorefrontAccessToken=False,
            installationState="not_installed",
        )

    has_storefront_access_token = bool(installation.storefront_access_token)
    installation_state = (
        "installed" if has_storefront_access_token else "installed_missing_storefront_token"
    )
    return EmbeddedSessionResponse(
        shopDomain=shop_domain,
        isInstalled=True,
        linkedWorkspaceId=installation.client_id,
        hasStorefrontAccessToken=has_storefront_access_token,
        installationState=installation_state,
    )


async def _forward_compliance_to_mos(
    *,
    topic: str,
    shop_domain: str,
    event_id: str,
    payload: dict[str, Any],
) -> None:
    if not settings.SHOPIFY_ENABLE_COMPLIANCE_FORWARDING:
        return

    headers = {
        "Content-Type": "application/json",
        "x-marketi-webhook-secret": settings.MOS_WEBHOOK_SHARED_SECRET or "",
    }
    forward_payload = {
        "topic": topic,
        "shopDomain": shop_domain,
        "eventId": event_id,
        "payload": payload,
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.SHOPIFY_REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                settings.mos_compliance_webhook_url,
                json=forward_payload,
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to forward compliance webhook to mOS backend: {exc}",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "mOS compliance ingestion failed "
                f"({response.status_code}): {response.text}"
            ),
        )


def _serialize_installation(installation: ShopInstallation) -> InstallationResponse:
    scopes = [
        scope.strip() for scope in installation.scopes.split(",") if scope.strip()
    ]
    return InstallationResponse(
        shopDomain=installation.shop_domain,
        clientId=installation.client_id,
        hasStorefrontAccessToken=bool(installation.storefront_access_token),
        scopes=scopes,
        installedAt=installation.installed_at,
        updatedAt=installation.updated_at,
        uninstalledAt=installation.uninstalled_at,
    )


def _build_shopify_oauth_url(*, shop_domain: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.SHOPIFY_APP_API_KEY,
            "scope": settings.admin_scopes_csv,
            "redirect_uri": f"{settings.app_base_url}/auth/callback",
            "state": state,
        }
    )
    return f"https://{shop_domain}/admin/oauth/authorize?{query}"


async def _register_required_webhooks(
    *, shop_domain: str, admin_access_token: str
) -> None:
    webhooks: list[tuple[str, str]] = [
        ("APP_UNINSTALLED", f"{settings.app_base_url}/webhooks/app/uninstalled"),
    ]
    if settings.SHOPIFY_ENABLE_ORDER_FORWARDING:
        webhooks.append(
            ("ORDERS_CREATE", f"{settings.app_base_url}/webhooks/orders/create")
        )

    for topic, callback_url in webhooks:
        await shopify_api.register_webhook(
            shop_domain=shop_domain,
            access_token=admin_access_token,
            topic=topic,
            callback_url=callback_url,
        )


async def _provision_storefront_token_if_missing(
    *,
    installation: ShopInstallation,
    session: Session,
) -> bool:
    if installation.storefront_access_token:
        return False

    if not installation.admin_access_token:
        raise ShopifyApiError(
            message=(
                "Cannot auto-provision storefront token because installation "
                "admin_access_token is missing."
            ),
            status_code=409,
        )

    storefront_access_token = await shopify_api.create_storefront_access_token(
        shop_domain=installation.shop_domain,
        access_token=installation.admin_access_token,
    )
    installation.storefront_access_token = storefront_access_token
    installation.updated_at = datetime.now(timezone.utc)
    session.add(installation)
    session.commit()
    session.refresh(installation)
    return True


@app.get("/auth/install")
def auth_install(
    shop: str,
    client_id: str | None = None,
    session: Session = Depends(get_session),
):
    shop_domain = normalize_shop_domain(shop)
    state = uuid4().hex
    oauth_state = OAuthState(state=state, shop_domain=shop_domain, client_id=client_id)
    session.add(oauth_state)
    session.commit()

    return RedirectResponse(
        url=_build_shopify_oauth_url(shop_domain=shop_domain, state=state),
        status_code=302,
    )


@app.get("/auth/callback")
async def auth_callback(request: Request, session: Session = Depends(get_session)):
    query_items = list(request.query_params.multi_items())
    if not verify_oauth_hmac(query_items):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth HMAC"
        )

    shop = request.query_params.get("shop")
    code = request.query_params.get("code")
    state_value = request.query_params.get("state")
    if not shop or not code or not state_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required OAuth callback params: shop, code, state",
        )

    shop_domain = normalize_shop_domain(shop)
    oauth_state = session.get(OAuthState, state_value)
    if not oauth_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state"
        )
    if oauth_state.shop_domain != shop_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state does not match the shop domain",
        )

    auto_provision_error: str | None = None
    auto_provisioned = False
    try:
        admin_access_token, scopes_csv = (
            await shopify_api.exchange_code_for_access_token(
                shop_domain=shop_domain,
                code=code,
            )
        )

        installation = session.scalars(
            select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
        ).first()
        if installation is None:
            installation = ShopInstallation(
                shop_domain=shop_domain,
                client_id=oauth_state.client_id,
                admin_access_token=admin_access_token,
                scopes=scopes_csv,
                uninstalled_at=None,
            )
            session.add(installation)
        else:
            installation.admin_access_token = admin_access_token
            installation.scopes = scopes_csv
            installation.uninstalled_at = None
            if oauth_state.client_id:
                installation.client_id = oauth_state.client_id
            installation.updated_at = datetime.now(timezone.utc)

        await _register_required_webhooks(
            shop_domain=shop_domain,
            admin_access_token=admin_access_token,
        )
        await shopify_api.ensure_catalog_collection_route_is_available(
            shop_domain=shop_domain,
            access_token=admin_access_token,
        )
        session.delete(oauth_state)
        session.commit()
        session.refresh(installation)

    except ShopifyApiError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        auto_provisioned = await _provision_storefront_token_if_missing(
            installation=installation,
            session=session,
        )
    except ShopifyApiError as exc:
        session.rollback()
        auto_provision_error = str(exc)

    if settings.SHOPIFY_INSTALL_SUCCESS_REDIRECT_URL:
        redirect_query: dict[str, str] = {"shop": shop_domain}
        if auto_provision_error:
            redirect_query["storefront_token_status"] = "failed"
        elif installation.storefront_access_token:
            redirect_query["storefront_token_status"] = "ready"
        success_url = (
            f"{str(settings.SHOPIFY_INSTALL_SUCCESS_REDIRECT_URL).rstrip('/')}"
            f"?{urlencode(redirect_query)}"
        )
        return RedirectResponse(url=success_url, status_code=302)

    redirect_query = {"shop": shop_domain}
    host = request.query_params.get("host")
    if isinstance(host, str) and host.strip():
        redirect_query["host"] = host.strip()
    return RedirectResponse(
        url=f"{settings.app_base_url}/app?{urlencode(redirect_query)}",
        status_code=302,
    )


@app.get("/app", response_class=HTMLResponse)
def embedded_app_shell() -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>mOS Shopify App</title>
    <meta name="shopify-api-key" content="{settings.SHOPIFY_APP_API_KEY}" />
    <style>
      body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #f6f6f7;
        color: #111827;
      }}
      .card {{
        max-width: 720px;
        margin: 24px auto;
        padding: 24px;
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
      }}
      .status {{
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 12px;
        white-space: pre-wrap;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 8px;
        padding: 12px;
      }}
      .actions {{
        margin-top: 16px;
        display: grid;
        grid-template-columns: 1fr;
        gap: 10px;
      }}
      .actions input {{
        width: 100%;
        box-sizing: border-box;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 14px;
      }}
      .actions-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }}
      .actions button {{
        border: 0;
        border-radius: 8px;
        padding: 9px 12px;
        background: #111827;
        color: #fff;
        font-size: 13px;
        cursor: pointer;
      }}
      .actions button.secondary {{
        background: #374151;
      }}
      .note {{
        margin-top: 10px;
        font-size: 13px;
        color: #374151;
      }}
    </style>
    <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
  </head>
  <body>
    <div class="card">
      <h1>mOS Shopify App</h1>
      <p>Embedded admin session is active. Complete workspace linking and storefront token setup here.</p>
      <div id="status" class="status">Loading embedded session…</div>
      <div class="actions">
        <input id="workspaceId" type="text" placeholder="Workspace ID (UUID)" />
        <div class="actions-row">
          <button id="linkBtn" type="button">Link Workspace</button>
          <button id="storefrontBtn" type="button" class="secondary">Provision Storefront Token</button>
          <button id="refreshBtn" type="button" class="secondary">Refresh</button>
        </div>
      </div>
      <div class="note">No manual shop-domain entry is required. This app uses Shopify launch context.</div>
    </div>
    <script>
      (async function bootstrap() {{
        const statusEl = document.getElementById("status");
        const workspaceInput = document.getElementById("workspaceId");
        const linkBtn = document.getElementById("linkBtn");
        const storefrontBtn = document.getElementById("storefrontBtn");
        const refreshBtn = document.getElementById("refreshBtn");
        let sessionState = null;

        async function apiCall(path, init) {{
          const response = await fetch(path, {{
            credentials: "same-origin",
            ...(init || {{}})
          }});
          let body = null;
          try {{
            body = await response.json();
          }} catch (_) {{
            body = null;
          }}
          if (!response.ok) {{
            throw new Error(body && body.detail ? body.detail : `Request failed (${{response.status}})`);
          }}
          if (!body || typeof body !== "object") {{
            throw new Error("Unexpected API response.");
          }}
          return body;
        }}

        function renderSession() {{
          statusEl.textContent = JSON.stringify(sessionState, null, 2);
          if (sessionState && typeof sessionState.linkedWorkspaceId === "string" && sessionState.linkedWorkspaceId) {{
            workspaceInput.value = sessionState.linkedWorkspaceId;
          }}
        }}

        async function refreshSession() {{
          sessionState = await apiCall("/app/api/session");
          renderSession();
        }}

        try {{
          const params = new URLSearchParams(window.location.search);
          const host = params.get("host");
          if (!host) {{
            throw new Error("Missing host query parameter for embedded app context.");
          }}
          await refreshSession();

          linkBtn.addEventListener("click", async function () {{
            try {{
              const value = workspaceInput.value.trim();
              if (!value) {{
                throw new Error("Workspace ID is required.");
              }}
              sessionState = await apiCall("/app/api/link-workspace", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{ clientId: value }})
              }});
              renderSession();
            }} catch (err) {{
              const message = err instanceof Error ? err.message : String(err);
              statusEl.textContent = `Embedded app error: ${{message}}`;
            }}
          }});

          storefrontBtn.addEventListener("click", async function () {{
            try {{
              const value = workspaceInput.value.trim();
              const payload = value ? {{ clientId: value }} : {{}};
              sessionState = await apiCall("/app/api/storefront-token/auto", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify(payload)
              }});
              renderSession();
            }} catch (err) {{
              const message = err instanceof Error ? err.message : String(err);
              statusEl.textContent = `Embedded app error: ${{message}}`;
            }}
          }});

          refreshBtn.addEventListener("click", async function () {{
            try {{
              await refreshSession();
            }} catch (err) {{
              const message = err instanceof Error ? err.message : String(err);
              statusEl.textContent = `Embedded app error: ${{message}}`;
            }}
          }});
        }} catch (err) {{
          const message = err instanceof Error ? err.message : String(err);
          statusEl.textContent = `Embedded app error: ${{message}}`;
        }}
      }})();
    </script>
  </body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/app/api/session", response_model=EmbeddedSessionResponse)
def app_api_session(
    shop_domain: str = Depends(require_shopify_session_shop_domain),
    session: Session = Depends(get_session),
):
    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    return _serialize_embedded_session(shop_domain=shop_domain, installation=installation)


@app.post("/app/api/link-workspace", response_model=EmbeddedSessionResponse)
def app_api_link_workspace(
    payload: LinkWorkspaceRequest,
    shop_domain: str = Depends(require_shopify_session_shop_domain),
    session: Session = Depends(get_session),
):
    client_id = payload.clientId.strip()
    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    if not installation or installation.uninstalled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop installation not found. Install the app first.",
        )
    if installation.client_id and installation.client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This Shopify store is already linked to a different mOS workspace. "
                f"linkedWorkspaceId={installation.client_id}"
            ),
        )

    if installation.client_id != client_id:
        installation.client_id = client_id
        installation.updated_at = datetime.now(timezone.utc)
        session.add(installation)
        session.commit()
        session.refresh(installation)

    return _serialize_embedded_session(shop_domain=shop_domain, installation=installation)


@app.post("/app/api/storefront-token/auto", response_model=EmbeddedSessionResponse)
async def app_api_auto_provision_storefront_token(
    payload: AutoProvisionStorefrontTokenRequest,
    shop_domain: str = Depends(require_shopify_session_shop_domain),
    session: Session = Depends(get_session),
):
    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    if not installation or installation.uninstalled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop installation not found. Install the app first.",
        )

    requested_client_id = (
        payload.clientId.strip() if isinstance(payload.clientId, str) else None
    )
    if requested_client_id:
        if installation.client_id and installation.client_id != requested_client_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This Shopify store is already linked to a different mOS workspace. "
                    f"linkedWorkspaceId={installation.client_id}"
                ),
            )
        if installation.client_id != requested_client_id:
            installation.client_id = requested_client_id
            installation.updated_at = datetime.now(timezone.utc)
            session.add(installation)
            session.commit()
            session.refresh(installation)

    try:
        await _provision_storefront_token_if_missing(
            installation=installation,
            session=session,
        )
        await shopify_api.ensure_catalog_collection_route_is_available(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
        )
    except ShopifyApiError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return _serialize_embedded_session(shop_domain=shop_domain, installation=installation)


@app.get("/admin/installations", dependencies=[Depends(require_internal_api_token)])
def list_installations(session: Session = Depends(get_session)):
    installations = session.scalars(
        select(ShopInstallation).order_by(ShopInstallation.updated_at.desc())
    ).all()
    return [_serialize_installation(installation) for installation in installations]


@app.patch(
    "/admin/installations/{shop_domain}",
    dependencies=[Depends(require_internal_api_token)],
)
def update_installation(
    shop_domain: str,
    payload: UpdateInstallationRequest,
    session: Session = Depends(get_session),
):
    normalized_shop = normalize_shop_domain(shop_domain)
    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == normalized_shop)
    ).first()
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shop installation not found"
        )

    fields_set = payload.model_fields_set
    if "clientId" in fields_set:
        installation.client_id = payload.clientId

    if "storefrontAccessToken" in fields_set:
        token = payload.storefrontAccessToken
        if token is not None:
            token = token.strip()
        installation.storefront_access_token = token or None

    installation.updated_at = datetime.now(timezone.utc)
    session.add(installation)
    session.commit()
    session.refresh(installation)
    return _serialize_installation(installation)


@app.post(
    "/admin/installations/{shop_domain}/storefront-token/auto",
    response_model=InstallationResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def auto_provision_installation_storefront_token(
    shop_domain: str,
    payload: AutoProvisionStorefrontTokenRequest,
    session: Session = Depends(get_session),
):
    normalized_shop = normalize_shop_domain(shop_domain)
    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == normalized_shop)
    ).first()
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shop installation not found"
        )
    if installation.uninstalled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shop installation is not active.",
        )

    requested_client_id = (
        payload.clientId.strip() if isinstance(payload.clientId, str) else None
    )
    if requested_client_id:
        if installation.client_id and installation.client_id != requested_client_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This Shopify store is already connected to a different workspace. "
                    f"connectedWorkspaceId={installation.client_id}"
                ),
            )
        if installation.client_id != requested_client_id:
            installation.client_id = requested_client_id
            installation.updated_at = datetime.now(timezone.utc)
            session.add(installation)
            session.commit()
            session.refresh(installation)

    try:
        await _provision_storefront_token_if_missing(
            installation=installation,
            session=session,
        )
        await shopify_api.ensure_catalog_collection_route_is_available(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
        )
    except ShopifyApiError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return _serialize_installation(installation)


def _resolve_active_installation(
    *,
    client_id: str | None,
    shop_domain: str | None,
    session: Session,
) -> ShopInstallation:
    if client_id:
        matches = session.scalars(
            select(ShopInstallation).where(
                ShopInstallation.client_id == client_id,
                ShopInstallation.uninstalled_at.is_(None),
            )
        ).all()
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active Shopify installation found for clientId={client_id}",
            )
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Multiple active Shopify installations found for this clientId. "
                    "Provide shopDomain explicitly."
                ),
            )
        return matches[0]

    normalized_shop = normalize_shop_domain(shop_domain or "")
    installation = session.scalars(
        select(ShopInstallation).where(
            ShopInstallation.shop_domain == normalized_shop,
            ShopInstallation.uninstalled_at.is_(None),
        )
    ).first()
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active Shopify installation found for shopDomain={normalized_shop}",
        )
    return installation


def _resolve_checkout_installation(
    *,
    request: CreateCheckoutRequest,
    session: Session,
) -> ShopInstallation:
    installation = _resolve_active_installation(
        client_id=request.clientId,
        shop_domain=request.shopDomain,
        session=session,
    )

    if not installation.storefront_access_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Installation is missing storefront_access_token. "
                "Retry auto setup via POST /admin/installations/{shop_domain}/storefront-token/auto "
                "or set it via PATCH /admin/installations/{shop_domain}."
            ),
        )
    return installation


@app.post(
    "/v1/catalog/products/verify",
    response_model=VerifyProductResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def verify_catalog_product(
    payload: VerifyProductRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )

    try:
        product = await shopify_api.verify_product_exists(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            product_gid=payload.productGid,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return VerifyProductResponse(
        shopDomain=installation.shop_domain,
        productGid=product["id"],
        handle=product["handle"],
        title=product["title"],
    )


@app.post(
    "/v1/catalog/products/list",
    response_model=ListProductsResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def list_catalog_products(
    payload: ListProductsRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    query = (payload.query or "").strip() or None
    try:
        products = await shopify_api.list_products(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            query=query,
            limit=payload.limit,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ListProductsResponse(
        shopDomain=installation.shop_domain,
        products=[
            CatalogProductSummary(
                productGid=item["id"],
                title=item["title"],
                handle=item["handle"],
                status=item["status"],
            )
            for item in products
        ],
    )


@app.post(
    "/v1/catalog/products/get",
    response_model=GetProductResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def get_catalog_product(
    payload: GetProductRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        product = await shopify_api.get_product(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            product_gid=payload.productGid,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return GetProductResponse(
        shopDomain=installation.shop_domain,
        productGid=product["productGid"],
        title=product["title"],
        handle=product["handle"],
        status=product["status"],
        variants=[
            CatalogProductVariant(
                variantGid=item["variantGid"],
                title=item["title"],
                priceCents=item["priceCents"],
                currency=item["currency"],
                compareAtPriceCents=item.get("compareAtPriceCents"),
                sku=item.get("sku"),
                barcode=item.get("barcode"),
                taxable=item["taxable"],
                requiresShipping=item["requiresShipping"],
                inventoryPolicy=item.get("inventoryPolicy"),
                inventoryManagement=item.get("inventoryManagement"),
                inventoryQuantity=item.get("inventoryQuantity"),
                optionValues=item.get("optionValues") or {},
            )
            for item in product["variants"]
        ],
    )


@app.post(
    "/v1/catalog/products/create",
    response_model=CreateCatalogProductResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def create_catalog_product(
    payload: CreateCatalogProductRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        created = await shopify_api.create_product(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            title=payload.title,
            description=payload.description,
            handle=payload.handle,
            vendor=payload.vendor,
            product_type=payload.productType,
            tags=payload.tags,
            status=payload.status,
            variants=[variant.model_dump() for variant in payload.variants],
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return CreateCatalogProductResponse(
        shopDomain=installation.shop_domain,
        productGid=created["productGid"],
        title=created["title"],
        handle=created["handle"],
        status=created["status"],
        variants=[
            CreatedCatalogVariant(
                variantGid=item["variantGid"],
                title=item["title"],
                priceCents=item["priceCents"],
                currency=item["currency"],
            )
            for item in created["variants"]
        ],
    )


@app.patch(
    "/v1/catalog/variants",
    response_model=UpdateCatalogVariantResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def update_catalog_variant(
    payload: UpdateCatalogVariantRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )

    fields_set = payload.model_fields_set
    update_fields: dict[str, Any] = {}
    if "title" in fields_set:
        update_fields["title"] = payload.title
    if "priceCents" in fields_set:
        update_fields["priceCents"] = payload.priceCents
    if "compareAtPriceCents" in fields_set:
        update_fields["compareAtPriceCents"] = payload.compareAtPriceCents
    if "sku" in fields_set:
        update_fields["sku"] = payload.sku
    if "barcode" in fields_set:
        update_fields["barcode"] = payload.barcode
    if "inventoryPolicy" in fields_set:
        update_fields["inventoryPolicy"] = payload.inventoryPolicy
    if "inventoryManagement" in fields_set:
        update_fields["inventoryManagement"] = payload.inventoryManagement

    try:
        updated = await shopify_api.update_variant(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            variant_gid=payload.variantGid,
            fields=update_fields,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return UpdateCatalogVariantResponse(
        shopDomain=installation.shop_domain,
        productGid=updated["productGid"],
        variantGid=updated["variantGid"],
    )


@app.post(
    "/v1/policies/pages/upsert",
    response_model=UpsertPolicyPagesResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def upsert_policy_pages(
    payload: UpsertPolicyPagesRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        synced_pages = await shopify_api.upsert_policy_pages(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            pages=[page.model_dump() for page in payload.pages],
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return UpsertPolicyPagesResponse(
        shopDomain=installation.shop_domain,
        pages=[
            UpsertedPolicyPage(
                pageKey=item["pageKey"],
                pageId=item["pageId"],
                title=item["title"],
                handle=item["handle"],
                url=item["url"],
                operation=item["operation"],
            )
            for item in synced_pages
        ],
    )


@app.post(
    "/v1/files/images/resolve",
    response_model=ResolveImageUrlsToShopifyFilesResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def resolve_image_urls_to_shopify_files(
    payload: ResolveImageUrlsToShopifyFilesRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        resolved = await shopify_api.resolve_image_urls_to_shopify_files(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            image_urls=payload.imageUrls,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Unexpected Shopify file image URL resolve error "
                f"({type(exc).__name__}): {exc}"
            ),
        ) from exc

    return ResolveImageUrlsToShopifyFilesResponse(
        shopDomain=installation.shop_domain,
        resolvedImageUrls=resolved,
    )


@app.post(
    "/v1/themes/brand/sync",
    response_model=SyncThemeBrandResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def sync_theme_brand(
    payload: SyncThemeBrandRequest,
    session: Session = Depends(get_session),
):
    _reject_direct_theme_write_operations()
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        synced = await shopify_api.sync_theme_brand(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            workspace_name=payload.workspaceName,
            brand_name=payload.brandName,
            logo_url=payload.logoUrl,
            css_vars=payload.cssVars,
            font_urls=payload.fontUrls,
            component_image_urls=payload.componentImageUrls,
            component_text_values=payload.componentTextValues,
            auto_component_image_urls=payload.autoComponentImageUrls,
            data_theme=payload.dataTheme,
            theme_id=payload.themeId,
            theme_name=payload.themeName,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unexpected theme sync error ({type(exc).__name__}): {exc}",
        ) from exc

    return SyncThemeBrandResponse(
        shopDomain=installation.shop_domain,
        themeId=synced["themeId"],
        themeName=synced["themeName"],
        themeRole=synced["themeRole"],
        layoutFilename=synced["layoutFilename"],
        cssFilename=synced["cssFilename"],
        settingsFilename=synced.get("settingsFilename"),
        jobId=synced.get("jobId"),
        coverage=synced["coverage"],
        settingsSync=synced["settingsSync"],
    )


@app.post(
    "/v1/themes/brand/export",
    response_model=ExportThemeBrandResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def export_theme_brand(
    payload: SyncThemeBrandRequest,
    session: Session = Depends(get_session),
):
    _ = payload
    _ = session
    _reject_manual_theme_export_operations()


@app.post(
    "/v1/themes/brand/template-slots",
    response_model=ListThemeBrandTemplateSlotsResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def list_theme_brand_template_slots(
    payload: ListThemeBrandTemplateSlotsRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        discovered = await shopify_api.list_theme_brand_template_slots(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            theme_id=payload.themeId,
            theme_name=payload.themeName,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ListThemeBrandTemplateSlotsResponse(
        shopDomain=installation.shop_domain,
        themeId=discovered["themeId"],
        themeName=discovered["themeName"],
        themeRole=discovered["themeRole"],
        imageSlots=[
            ThemeTemplateImageSlot(
                path=item["path"],
                key=item["key"],
                currentValue=item.get("currentValue"),
                role=item["role"],
                recommendedAspect=item["recommendedAspect"],
            )
            for item in discovered["imageSlots"]
        ],
        textSlots=[
            ThemeTemplateTextSlot(
                path=item["path"],
                key=item["key"],
                currentValue=item.get("currentValue"),
                role=item["role"],
                maxLength=item["maxLength"],
            )
            for item in discovered["textSlots"]
        ],
    )


@app.post(
    "/v1/themes/brand/audit",
    response_model=AuditThemeBrandResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def audit_theme_brand(
    payload: AuditThemeBrandRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        audited = await shopify_api.audit_theme_brand(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            workspace_name=payload.workspaceName,
            css_vars=payload.cssVars,
            data_theme=payload.dataTheme,
            theme_id=payload.themeId,
            theme_name=payload.themeName,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return AuditThemeBrandResponse(
        shopDomain=installation.shop_domain,
        themeId=audited["themeId"],
        themeName=audited["themeName"],
        themeRole=audited["themeRole"],
        layoutFilename=audited["layoutFilename"],
        cssFilename=audited["cssFilename"],
        settingsFilename=audited.get("settingsFilename"),
        hasManagedMarkerBlock=audited["hasManagedMarkerBlock"],
        layoutIncludesManagedCssAsset=audited["layoutIncludesManagedCssAsset"],
        managedCssAssetExists=audited["managedCssAssetExists"],
        coverage=audited["coverage"],
        settingsAudit=audited["settingsAudit"],
        isReady=audited["isReady"],
    )


def _coerce_attribute_map(attributes: dict[str, str]) -> list[dict[str, str]]:
    serialized: list[dict[str, str]] = []
    for key, value in sorted(attributes.items()):
        cleaned_key = key.strip()
        cleaned_value = value.strip()
        if not cleaned_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cart attribute key cannot be empty",
            )
        serialized.append({"key": cleaned_key, "value": cleaned_value})
    return serialized


@app.post(
    "/v1/checkouts",
    response_model=CreateCheckoutResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def create_checkout(
    payload: CreateCheckoutRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_checkout_installation(request=payload, session=session)

    cart_input: dict[str, Any] = {
        "lines": [
            {
                "merchandiseId": line.merchandiseId,
                "quantity": line.quantity,
            }
            for line in payload.lines
        ]
    }
    if payload.discountCodes:
        cart_input["discountCodes"] = payload.discountCodes
    if payload.attributes:
        cart_input["attributes"] = _coerce_attribute_map(payload.attributes)
    if payload.note:
        cart_input["note"] = payload.note
    if payload.buyerIdentity:
        buyer_identity = payload.buyerIdentity.model_dump(exclude_none=True)
        if buyer_identity:
            cart_input["buyerIdentity"] = buyer_identity

    try:
        cart_id, checkout_url = await shopify_api.create_cart(
            shop_domain=installation.shop_domain,
            storefront_access_token=installation.storefront_access_token,
            cart_input=cart_input,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return CreateCheckoutResponse(
        shopDomain=installation.shop_domain,
        cartId=cart_id,
        checkoutUrl=checkout_url,
    )


def _coerce_note_attributes(order_payload: dict[str, Any]) -> dict[str, str]:
    raw = order_payload.get("note_attributes")
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order.note_attributes must be a list",
        )

    attributes: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each note_attribute entry must be an object",
            )
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="note_attribute.name must be a string",
            )
        if value is None:
            value = ""
        if not isinstance(value, str):
            value = str(value)
        attributes[name] = value
    return attributes


def _coerce_line_items(order_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = order_payload.get("line_items")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order.line_items must be a list",
        )

    line_items: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each line_items entry must be an object",
            )
        line_items.append(
            {
                "id": item.get("id"),
                "variantId": item.get("variant_id"),
                "quantity": item.get("quantity"),
                "sku": item.get("sku"),
                "title": item.get("title"),
            }
        )
    return line_items


async def _forward_order_to_mos(payload: ForwardOrderPayload) -> None:
    if not settings.SHOPIFY_ENABLE_ORDER_FORWARDING:
        return

    forward_url = (
        f"{str(settings.MOS_BACKEND_BASE_URL).rstrip('/')}/shopify/orders/webhook"
    )
    headers = {
        "Content-Type": "application/json",
        "x-marketi-webhook-secret": settings.MOS_WEBHOOK_SHARED_SECRET or "",
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.SHOPIFY_REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                forward_url, json=payload.model_dump(), headers=headers
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to forward Shopify order to MOS backend "
                f"({response.status_code}): {response.text}"
            ),
        )


@app.post("/webhooks/orders/create")
async def orders_create_webhook(
    request: Request, session: Session = Depends(get_session)
):
    body = await request.body()
    if not verify_webhook_hmac(
        body=body, supplied_hmac=request.headers.get("x-shopify-hmac-sha256")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook HMAC"
        )

    shop_header = request.headers.get("x-shopify-shop-domain")
    event_id = request.headers.get("x-shopify-event-id")
    if not shop_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-shop-domain header",
        )
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-event-id header",
        )

    shop_domain = normalize_shop_domain(shop_header)

    existing = session.scalars(
        select(ProcessedWebhookEvent).where(
            ProcessedWebhookEvent.shop_domain == shop_domain,
            ProcessedWebhookEvent.topic == "ORDERS_CREATE",
            ProcessedWebhookEvent.event_id == event_id,
        )
    ).first()
    if existing:
        return {"received": True, "duplicate": True}

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object",
        )

    note_attributes = _coerce_note_attributes(payload)
    if not note_attributes.get("funnel_id"):
        session.add(
            ProcessedWebhookEvent(
                shop_domain=shop_domain,
                topic="ORDERS_CREATE",
                event_id=event_id,
                status="ignored_missing_funnel_id",
            )
        )
        session.commit()
        return {
            "received": True,
            "ignored": True,
            "reason": "Order is missing funnel_id note attribute",
        }

    order_payload = ForwardOrderPayload(
        shopDomain=shop_domain,
        orderId=str(payload.get("id") or ""),
        orderName=payload.get("name"),
        currency=payload.get("currency"),
        totalPrice=payload.get("total_price"),
        createdAt=payload.get("created_at"),
        noteAttributes=note_attributes,
        lineItems=_coerce_line_items(payload),
    )
    if not order_payload.orderId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order payload is missing id",
        )

    await _forward_order_to_mos(order_payload)

    session.add(
        ProcessedWebhookEvent(
            shop_domain=shop_domain,
            topic="ORDERS_CREATE",
            event_id=event_id,
            status="forwarded",
        )
    )
    session.commit()
    return {"received": True}


@app.post("/webhooks/app/uninstalled")
async def app_uninstalled_webhook(
    request: Request, session: Session = Depends(get_session)
):
    body = await request.body()
    if not verify_webhook_hmac(
        body=body, supplied_hmac=request.headers.get("x-shopify-hmac-sha256")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook HMAC"
        )

    shop_header = request.headers.get("x-shopify-shop-domain")
    if not shop_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-shop-domain header",
        )
    shop_domain = normalize_shop_domain(shop_header)

    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    if installation:
        installation.uninstalled_at = datetime.now(timezone.utc)
        installation.admin_access_token = ""
        installation.storefront_access_token = None
        installation.updated_at = datetime.now(timezone.utc)
        session.add(installation)
        session.commit()

    return {"received": True}


@app.post("/webhooks/compliance")
async def compliance_webhook(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    if not verify_webhook_hmac(
        body=body, supplied_hmac=request.headers.get("x-shopify-hmac-sha256")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook HMAC"
        )

    topic_header = request.headers.get("x-shopify-topic")
    if not topic_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-topic header",
        )
    topic = topic_header.strip().lower()
    if topic not in _SHOPIFY_COMPLIANCE_TOPICS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported compliance webhook topic. "
                "Expected one of: customers/data_request, customers/redact, shop/redact."
            ),
        )

    shop_header = request.headers.get("x-shopify-shop-domain")
    event_id = request.headers.get("x-shopify-event-id")
    if not shop_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-shop-domain header",
        )
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-event-id header",
        )
    shop_domain = normalize_shop_domain(shop_header)

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object",
        )

    payload_shop_domain = payload.get("shop_domain")
    if not isinstance(payload_shop_domain, str) or not payload_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compliance payload must include shop_domain",
        )
    if normalize_shop_domain(payload_shop_domain) != shop_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compliance payload shop_domain does not match x-shopify-shop-domain",
        )

    if topic != "shop/redact":
        existing = session.scalars(
            select(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.shop_domain == shop_domain,
                ProcessedWebhookEvent.topic == topic,
                ProcessedWebhookEvent.event_id == event_id,
            )
        ).first()
        if existing:
            return {"received": True, "duplicate": True, "topic": topic}

    await _forward_compliance_to_mos(
        topic=topic,
        shop_domain=shop_domain,
        event_id=event_id,
        payload=payload,
    )

    if topic == "shop/redact":
        session.execute(
            delete(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.shop_domain == shop_domain
            )
        )
        session.execute(delete(OAuthState).where(OAuthState.shop_domain == shop_domain))
        session.execute(
            delete(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
        )
        session.commit()
        return {"received": True, "topic": topic, "shopDomain": shop_domain}

    status_value = (
        "no_local_customer_data_for_requested_customer"
        if topic == "customers/data_request"
        else "customer_redact_acknowledged_no_local_customer_data"
    )
    session.add(
        ProcessedWebhookEvent(
            shop_domain=shop_domain,
            topic=topic,
            event_id=event_id,
            status=status_value,
        )
    )
    session.commit()
    return {"received": True, "topic": topic, "shopDomain": shop_domain}
