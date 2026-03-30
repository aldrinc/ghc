"""Postiz integration API routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
import app.config as app_config
from app.db.deps import get_session
from app.db.models import User
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.postiz import (
    PostizChannelRepository,
    PostizCredentialsRepository,
    PostizPostingProfileRepository,
    PostizPublicationRepository,
)
from app.schemas.postiz import (
    PostizBrowserLaunchRequest,
    PostizBrowserLaunchResponse,
    PostizConnectUrlRequest,
    PostizConnectUrlResponse,
    PostizCreatePostRequest,
    PostizCredentialsRequest,
    PostizCredentialsResponse,
    PostizChannelResponse,
    PostizPostListResponse,
    PostizPostResponse,
    PostizPostingProfileCreateRequest,
    PostizPostingProfileResponse,
    PostizPostingProfileUpdateRequest,
    PostizSyncResponse,
)
from app.services.integration_secrets import (
    IntegrationSecretError,
    decrypt_secret_json,
    encrypt_secret_json,
)
from app.services.postiz_client import (
    PostizClient,
    PostizBrowserClient,
    PostizBrowserOrg,
    PostizClientError,
    PostizBrowserAuthError,
    PostizBrowserProvisioningError,
    PostizMissingProviderSettingsError,
    PostizNotFoundError,
    create_postiz_browser_client,
    create_postiz_client,
)

router = APIRouter(prefix="/clients/{client_id}/postiz", tags=["postiz"])


class _SettingsProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(app_config.settings, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(app_config.settings, name, value)

    def __delattr__(self, name: str) -> None:
        setattr(app_config.settings, name, None)


settings = _SettingsProxy()


def _require_client(session: Session, *, org_id: str, client_id: str) -> None:
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


def _get_client(session: Session, org_id: str, client_id: str):
    """Get client credentials and return a Postiz client instance."""
    creds_repo = PostizCredentialsRepository(session)
    creds = creds_repo.get(org_id=org_id, client_id=client_id)
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Postiz credentials not configured. Add credentials first.",
        )

    try:
        decrypted = decrypt_secret_json(creds.credentials_encrypted)
    except IntegrationSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to decrypt Postiz credentials: {exc}",
        ) from exc

    api_key = decrypted.get("apiKey")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Postiz credentials are malformed.",
        )

    return create_postiz_client(api_key=api_key, base_url=creds.base_url), creds_repo


def _serialize_channel(channel) -> PostizChannelResponse:
    return PostizChannelResponse.model_validate(
        {
            "id": str(channel.id),
            "postizIntegrationId": channel.postiz_integration_id,
            "postizChannelId": channel.postiz_channel_id,
            "identifier": channel.identifier,
            "name": channel.name,
            "profile": channel.profile,
            "pictureUrl": channel.picture_url,
            "disabled": bool(channel.disabled),
            "isDefault": bool(channel.is_default),
            "metadata": channel.metadata_json or {},
            "lastSyncedAt": channel.last_synced_at,
            "createdAt": channel.created_at,
            "updatedAt": channel.updated_at,
        }
    )


def _serialize_posting_profile(profile) -> PostizPostingProfileResponse:
    return PostizPostingProfileResponse.model_validate(
        {
            "id": str(profile.id),
            "name": profile.name,
            "isDefault": bool(profile.is_default),
            "defaultChannelIds": list(profile.default_channel_ids or []),
            "timezone": profile.timezone,
            "shortLink": profile.short_link,
            "providerSettings": profile.provider_settings_json or {},
            "postizPostingProfileId": profile.postiz_posting_profile_id,
            "metadata": profile.metadata_json or {},
            "createdAt": profile.created_at,
            "updatedAt": profile.updated_at,
        }
    )


def _serialize_publication(pub) -> PostizPostResponse:
    return PostizPostResponse.model_validate(
        {
            "id": str(pub.id),
            "postizPostId": pub.postiz_post_id,
            "postizPostIds": list(pub.postiz_post_ids_json or []),
            "content": pub.content,
            "postType": pub.post_type,
            "scheduledFor": pub.scheduled_for,
            "targetChannels": pub.target_channels_json or {},
            "mediaUrls": list(pub.media_urls_json or []),
            "linkUrl": pub.link_url,
            "status": pub.status,
            "postizPostStatus": pub.postiz_post_status,
            "releaseUrls": list(pub.release_urls_json or []),
            "errorPayload": pub.error_payload_json,
            "lastSyncedAt": pub.last_synced_at,
            "createdAt": pub.created_at,
            "updatedAt": pub.updated_at,
        }
    )


def _normalize_postiz_status(status_value: str | None) -> str | None:
    if not status_value:
        return None

    normalized = str(status_value).strip().upper()
    status_aliases = {
        "QUEUED": "QUEUE",
        "SCHEDULED": "QUEUE",
        "SUCCESS": "PUBLISHED",
        "FAILED": "ERROR",
    }
    return status_aliases.get(normalized, normalized)


def _summarize_postiz_posts(posts: list[Any]) -> tuple[str | None, list[str]]:
    statuses: set[str] = set()
    release_urls: list[str] = []

    for post in posts:
        normalized_status = _normalize_postiz_status(getattr(post, "status", None))
        if normalized_status:
            statuses.add(normalized_status)

        release_url = getattr(post, "release_url", None)
        if release_url and release_url not in release_urls:
            release_urls.append(release_url)

    if not statuses:
        return None, release_urls
    if "ERROR" in statuses:
        return "ERROR", release_urls
    if "QUEUE" in statuses:
        return "QUEUE", release_urls
    if statuses == {"PUBLISHED"}:
        return "PUBLISHED", release_urls
    if statuses == {"DRAFT"}:
        return "DRAFT", release_urls

    return ",".join(sorted(statuses)), release_urls


def _local_publication_status_for_post_type(post_type: str) -> str:
    if post_type == "schedule":
        return "scheduled"
    if post_type == "draft":
        return "draft"
    return "queued"


def _local_publication_status_for_synced_post(post_type: str, postiz_status: str | None) -> str | None:
    normalized_status = _normalize_postiz_status(postiz_status)
    if normalized_status == "ERROR":
        return "failed"
    if normalized_status == "PUBLISHED":
        return "published"
    if normalized_status == "DRAFT":
        return "draft"
    if normalized_status == "QUEUE":
        return _local_publication_status_for_post_type(post_type)
    return None


def _extract_workspace_api_key(creds) -> str | None:
    try:
        decrypted = decrypt_secret_json(creds.credentials_encrypted)
    except IntegrationSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to decrypt Postiz credentials: {exc}",
        ) from exc

    api_key = decrypted.get("apiKey")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    return None


def _resolve_mos_user_email(
    session: Session,
    auth: AuthContext,
    *,
    request_email: str | None = None,
) -> str:
    if auth.email:
        return auth.email

    stmt = select(User.email).where(User.org_id == auth.org_id, User.clerk_user_id == auth.user_id)
    email = session.execute(stmt).scalar_one_or_none()
    if isinstance(email, str) and email.strip():
        return email.strip()

    if isinstance(request_email, str) and request_email.strip():
        return request_email.strip()

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "The current MOS user does not expose an email address in the auth token, the MOS database, "
            "or the current frontend session, so Postiz browser sign-in cannot be prepared."
        ),
    )


def _derive_postiz_browser_password(*, user_id: str, email: str) -> str:
    secret = settings.POSTIZ_BROWSER_LOGIN_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="POSTIZ_BROWSER_LOGIN_SECRET is not configured, so automatic Postiz browser sign-in is unavailable.",
        )

    digest = hmac.new(
        secret.encode("utf-8"),
        f"{user_id}:{email.lower()}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"mos-postiz-{encoded}"


def _is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _postiz_browser_launch_url(
    *,
    api_base_url: str,
    request_host: str | None,
) -> tuple[str, bool]:
    parsed = urlparse(api_base_url.rstrip("/"))
    path = parsed.path.rstrip("/")
    if path.endswith("/api"):
        path = path[:-4]

    hostname = parsed.hostname
    if request_host and hostname and hostname != request_host:
        if _is_loopback_hostname(hostname) and _is_loopback_hostname(request_host):
            parsed = parsed._replace(netloc=f"{request_host}:{parsed.port}" if parsed.port else request_host)
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Automatic Postiz browser sign-in only works when MOS and Postiz share the same browser host. "
                    f"MOS is using host '{request_host}', but Postiz is configured for '{hostname}'."
                ),
            )

    launch_path = f"{path}/launches" if path else "/launches"
    launch_url = urlunparse(parsed._replace(path=launch_path, params="", query="", fragment=""))
    return launch_url, parsed.scheme == "https"


def _pick_postiz_org_for_workspace(
    *,
    orgs: list[PostizBrowserOrg],
    workspace_api_key: str | None,
) -> tuple[PostizBrowserOrg, bool]:
    if workspace_api_key:
        for org in orgs:
            if org.api_key == workspace_api_key:
                return org, False
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The current Postiz user is not a member of the organization that owns this workspace's Postiz API key."
            ),
        )

    if len(orgs) == 1:
        return orgs[0], True

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "This workspace is not linked to Postiz yet, and the current Postiz user belongs to multiple organizations. "
            "Save workspace credentials first so MOS can target the correct Postiz organization."
        ),
    )


def _set_postiz_browser_cookie(response: Response, *, key: str, value: str, secure: bool) -> None:
    response.set_cookie(
        key=key,
        value=value,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
        path="/",
    )


# =============================================================================
# Credentials
# =============================================================================


@router.get("/credentials")
def get_credentials(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Get Postiz credentials status for a workspace."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = PostizCredentialsRepository(session)
    creds = repo.get(org_id=auth.org_id, client_id=client_id)
    return jsonable_encoder(
        PostizCredentialsResponse.model_validate(
            {
                "hasCredentials": creds is not None,
                "baseUrl": creds.base_url if creds else settings.POSTIZ_DEFAULT_BASE_URL,
                "authType": creds.auth_type if creds else None,
                "lastValidatedAt": getattr(creds, "last_validated_at", None),
                "lastValidationError": getattr(creds, "last_validation_error", None),
            }
        )
    )


@router.put("/credentials")
def put_credentials(
    client_id: str,
    payload: PostizCredentialsRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Save Postiz credentials for a workspace."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)

    # Validate credentials by attempting to connect
    try:
        client = create_postiz_client(api_key=payload.api_key, base_url=payload.base_url)
        is_valid, error_message = client.validate_connection()
    except PostizClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to validate Postiz credentials: {exc}",
        ) from exc

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_message or "Postiz credential validation failed.",
        )

    try:
        encrypted = encrypt_secret_json({"apiKey": payload.api_key})
    except IntegrationSecretError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    repo = PostizCredentialsRepository(session)
    creds = repo.upsert(
        org_id=auth.org_id,
        client_id=client_id,
        base_url=payload.base_url,
        credentials_encrypted=encrypted,
    )
    repo.update_validation(
        org_id=auth.org_id,
        client_id=client_id,
        last_validated_at=datetime.now(timezone.utc),
        last_validation_error=None,
    )
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonable_encoder(
        PostizCredentialsResponse.model_validate(
            {
                "hasCredentials": True,
                "baseUrl": creds.base_url,
                "authType": creds.auth_type,
                "lastValidatedAt": creds.last_validated_at or datetime.now(timezone.utc),
                "lastValidationError": None,
            }
        )
    )


@router.post("/validate")
def validate_credentials(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Validate existing Postiz credentials for a workspace and update storage."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)

    try:
        client, creds_repo = _get_client(session, org_id=auth.org_id, client_id=client_id)
        is_valid, error_message = client.validate_connection()
    except HTTPException:
        raise
    except PostizClientError as exc:
        # Update validation error in storage
        creds_repo.update_validation(
            org_id=auth.org_id,
            client_id=client_id,
            last_validated_at=datetime.now(timezone.utc),
            last_validation_error=str(exc),
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to validate Postiz credentials: {exc}",
        ) from exc

    now = datetime.now(timezone.utc)
    if is_valid:
        creds_repo.update_validation(
            org_id=auth.org_id,
            client_id=client_id,
            last_validated_at=now,
            last_validation_error=None,
        )
    else:
        creds_repo.update_validation(
            org_id=auth.org_id,
            client_id=client_id,
            last_validated_at=now,
            last_validation_error=error_message,
        )

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_message or "Postiz credential validation failed.",
        )

    return {"valid": True, "message": "Postiz credentials are valid."}


@router.post("/launch")
def prepare_postiz_browser_launch(
    client_id: str,
    response: Response,
    request: Request,
    payload: PostizBrowserLaunchRequest | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Prepare a browser-authenticated Postiz launch for the current workspace."""
    client_record = ClientsRepository(session).get(org_id=auth.org_id, client_id=client_id)
    if client_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    creds_repo = PostizCredentialsRepository(session)
    creds = creds_repo.get(org_id=auth.org_id, client_id=client_id)
    resolved_base_url = creds.base_url if creds else settings.POSTIZ_DEFAULT_BASE_URL
    if not resolved_base_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No Postiz base URL is configured for this workspace. Save workspace credentials or set "
                "POSTIZ_DEFAULT_BASE_URL first."
            ),
        )

    workspace_api_key = _extract_workspace_api_key(creds) if creds else None
    user_email = _resolve_mos_user_email(
        session,
        auth,
        request_email=payload.email if payload else None,
    )
    browser_password = _derive_postiz_browser_password(user_id=auth.user_id, email=user_email)

    browser_client: PostizBrowserClient = create_postiz_browser_client(base_url=resolved_base_url)
    try:
        browser_session = browser_client.create_session(
            email=user_email,
            password=browser_password,
            company=client_record.name,
            allow_register=True,
        )
    except (PostizBrowserAuthError, PostizBrowserProvisioningError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PostizClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to prepare Postiz browser session: {exc}",
        ) from exc

    target_org, auto_configured_credentials = _pick_postiz_org_for_workspace(
        orgs=browser_session.orgs,
        workspace_api_key=workspace_api_key,
    )
    if not target_org.api_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected Postiz organization does not expose a public API key.",
        )

    if auto_configured_credentials:
        try:
            encrypted = encrypt_secret_json({"apiKey": target_org.api_key})
        except IntegrationSecretError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        public_client = create_postiz_client(api_key=target_org.api_key, base_url=resolved_base_url)
        is_valid, error_message = public_client.validate_connection()
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_message or "The selected Postiz organization could not be validated.",
            )

        creds = creds_repo.upsert(
            org_id=auth.org_id,
            client_id=client_id,
            base_url=resolved_base_url,
            credentials_encrypted=encrypted,
        )
        creds_repo.update_validation(
            org_id=auth.org_id,
            client_id=client_id,
            last_validated_at=datetime.now(timezone.utc),
            last_validation_error=None,
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise

    launch_url, secure_cookie = _postiz_browser_launch_url(
        api_base_url=resolved_base_url,
        request_host=request.url.hostname,
    )
    _set_postiz_browser_cookie(
        response,
        key="auth",
        value=browser_session.auth_token,
        secure=secure_cookie,
    )
    _set_postiz_browser_cookie(
        response,
        key="showorg",
        value=target_org.id,
        secure=secure_cookie,
    )

    return jsonable_encoder(
        PostizBrowserLaunchResponse.model_validate(
            {
                "launchUrl": launch_url,
                "autoConfiguredCredentials": auto_configured_credentials,
            }
        )
    )


# =============================================================================
# Channels
# =============================================================================


@router.get("/channels")
def list_channels(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """List synced Postiz channels for a workspace."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = PostizChannelRepository(session)
    channels = repo.list(org_id=auth.org_id, client_id=client_id)
    return jsonable_encoder([_serialize_channel(c) for c in channels])


@router.post("/channels/sync")
def sync_channels(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Sync Postiz channels from the API into MOS storage using upsert.

    Preserves existing is_default values by checking before upserting.
    """
    _require_client(session, org_id=auth.org_id, client_id=client_id)

    try:
        client, creds_repo = _get_client(session, org_id=auth.org_id, client_id=client_id)
    except HTTPException:
        raise

    channel_repo = PostizChannelRepository(session)

    # Get integrations (Postiz returns connected integrations directly)
    synced_count = 0
    errors: list[str] = []

    try:
        integrations = client.list_integrations()
    except PostizClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list Postiz integrations: {exc}",
        ) from exc

    for integration in integrations:
        # Check for existing channel to preserve is_default
        existing = channel_repo.get_by_postiz_ids(
            org_id=auth.org_id,
            client_id=client_id,
            postiz_integration_id=integration.id,
            postiz_channel_id=integration.id,
        )
        existing_is_default = existing.is_default if existing else False

        try:
            channel = channel_repo.upsert(
                org_id=auth.org_id,
                client_id=client_id,
                postiz_integration_id=integration.id,
                postiz_channel_id=integration.id,
                identifier=integration.identifier,
                name=integration.name,
                profile=integration.profile,
                picture_url=integration.picture_url,
                disabled=integration.disabled,
                is_default=existing_is_default,
                metadata_json={"profile": integration.profile},
            )
            synced_count += 1
        except Exception as exc:
            errors.append(f"Failed to sync integration {integration.name}: {exc}")

    channel_repo.mark_missing_as_disabled(
        org_id=auth.org_id,
        client_id=client_id,
        active_postiz_integration_ids={integration.id for integration in integrations},
    )

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonable_encoder(
        {
            "syncedCount": synced_count,
            "errors": errors,
        }
    )


@router.post("/connect-url")
def get_connect_url(
    client_id: str,
    payload: PostizConnectUrlRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Get OAuth URL for connecting a Postiz social channel."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)

    try:
        client, _ = _get_client(session, org_id=auth.org_id, client_id=client_id)
        connect_url = client.get_social_connect_url(integration=payload.integration)
    except HTTPException:
        raise
    except PostizClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to get Postiz connect URL: {exc}",
        ) from exc

    return jsonable_encoder(
        PostizConnectUrlResponse(
            connectUrl=connect_url.url,
            integration=connect_url.integration,
        )
    )


# =============================================================================
# Posting Profiles
# =============================================================================


@router.get("/posting-profiles")
def list_posting_profiles(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """List Postiz posting profiles for a workspace."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = PostizPostingProfileRepository(session)
    profiles = repo.list(org_id=auth.org_id, client_id=client_id)
    return jsonable_encoder([_serialize_posting_profile(p) for p in profiles])


@router.post("/posting-profiles", status_code=status.HTTP_201_CREATED)
def create_posting_profile(
    client_id: str,
    payload: PostizPostingProfileCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Create a Postiz posting profile for a workspace."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = PostizPostingProfileRepository(session)
    profile = repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        name=payload.name,
        is_default=payload.is_default,
        default_channel_ids=payload.default_channel_ids,
        timezone=payload.timezone,
        short_link=payload.short_link,
        provider_settings_json=payload.provider_settings_json,
    )
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return jsonable_encoder(_serialize_posting_profile(profile))


@router.put("/posting-profiles/{profile_id}")
def update_posting_profile(
    client_id: str,
    profile_id: str,
    payload: PostizPostingProfileUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Update a Postiz posting profile."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = PostizPostingProfileRepository(session)
    existing = repo.get(org_id=auth.org_id, profile_id=profile_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Postiz posting profile not found.",
        )

    update_fields = payload.model_dump(exclude_none=True, by_alias=False)
    if "providerSettingsJson" in update_fields:
        update_fields["provider_settings_json"] = update_fields.pop("providerSettingsJson")
    if "defaultChannelIds" in update_fields:
        update_fields["default_channel_ids"] = update_fields.pop("defaultChannelIds")
    if "isDefault" in update_fields:
        update_fields["is_default"] = update_fields.pop("isDefault")
    if "timezone" in update_fields:
        update_fields["timezone"] = update_fields.pop("timezone")
    if "shortLink" in update_fields:
        update_fields["short_link"] = update_fields.pop("shortLink")

    profile = repo.update(org_id=auth.org_id, profile_id=profile_id, **update_fields)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Postiz posting profile not found.",
        )

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return jsonable_encoder(_serialize_posting_profile(profile))


# =============================================================================
# Posts
# =============================================================================


@router.get("/posts")
def list_posts(
    client_id: str,
    limit: int = 50,
    offset: int = 0,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """List Postiz publication history for a workspace."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = PostizPublicationRepository(session)
    publications, total = repo.list(
        org_id=auth.org_id,
        client_id=client_id,
        limit=limit,
        offset=offset,
    )
    return jsonable_encoder(
        PostizPostListResponse(
            posts=[_serialize_publication(p) for p in publications],
            total=total,
        )
    )


@router.post("/posts")
def create_post(
    client_id: str,
    payload: PostizCreatePostRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """
    Create and optionally schedule a Postiz post.

    Flow:
    1. Resolve local channel UUIDs to Postiz integration IDs.
    2. If media URLs are provided, upload them to Postiz first.
    3. Create the post via Postiz API.
    4. Store the publication record locally.
    """
    _require_client(session, org_id=auth.org_id, client_id=client_id)

    try:
        client, _ = _get_client(session, org_id=auth.org_id, client_id=client_id)
    except HTTPException:
        raise

    # Resolve local channel UUIDs to synced Postiz targets only.
    channel_repo = PostizChannelRepository(session)
    postiz_targets: list[dict[str, str]] = []
    for channel_id in payload.channel_ids:
        channel = channel_repo.get(org_id=auth.org_id, channel_id=channel_id)
        if channel is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Postiz channel '{channel_id}' is not synced for this workspace.",
            )
        if channel.disabled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Postiz channel '{channel.name}' is disabled or stale. Resync channels first.",
            )
        postiz_targets.append(
            {
                "integration_id": channel.postiz_integration_id,
                "identifier": channel.identifier,
            }
        )

    if not postiz_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid Postiz channel IDs could be resolved.",
        )

    if payload.link_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "linkUrl is not mapped into Postiz provider settings. "
                "Put provider-specific link fields inside providerSettingsByIdentifier instead."
            ),
        )

    # Upload media if URLs are provided
    uploaded_media = []
    if payload.media_urls:
        try:
            for media_url in payload.media_urls:
                uploaded = client.upload_media_from_url(url=media_url)
                uploaded_media.append(uploaded)
        except PostizClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to upload media to Postiz: {exc}",
            ) from exc

    # Resolve posting profile if provided
    posting_profile_id = payload.posting_profile_id
    resolved_short_link = False
    resolved_provider_settings = dict(payload.provider_settings_by_identifier or {})
    if posting_profile_id:
        profile_repo = PostizPostingProfileRepository(session)
        profile = profile_repo.get(org_id=auth.org_id, profile_id=posting_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Postiz posting profile not found.",
            )
        resolved_short_link = bool(profile.short_link)
        resolved_provider_settings = {
            **(profile.provider_settings_json or {}),
            **resolved_provider_settings,
        }

    # Build request payload for storage (store original channel IDs)
    request_payload = {
        "content": payload.content,
        "postType": payload.post_type,
        "scheduledFor": payload.scheduled_for.isoformat() if payload.scheduled_for else None,
        "channelIds": payload.channel_ids,  # Original MOS channel UUIDs
        "postizTargets": postiz_targets,
        "mediaUrls": payload.media_urls,
        "linkUrl": payload.link_url,
        "shortLink": resolved_short_link,
        "providerSettingsByIdentifier": resolved_provider_settings,
    }

    # Create publication record first (in pending state)
    pub_repo = PostizPublicationRepository(session)
    publication = pub_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        content=payload.content,
        post_type=payload.post_type,
        scheduled_for=payload.scheduled_for,
        target_channels_json={"channel_ids": payload.channel_ids},
        media_urls_json=payload.media_urls,
        link_url=payload.link_url,
        provider_settings_by_identifier_json=resolved_provider_settings,
        request_payload_json=request_payload,
        postiz_posting_profile_id=posting_profile_id,
    )

    # Create post in Postiz (uses resolved Postiz channel IDs)
    try:
        post_results = client.create_post(
            content=payload.content,
            targets=postiz_targets,
            post_type=payload.post_type,
            scheduled_for=payload.scheduled_for,
            media=uploaded_media if uploaded_media else None,
            short_link=resolved_short_link,
            provider_settings_by_identifier=resolved_provider_settings,
        )

        # Handle multi-channel response: extract all post IDs and release URLs
        all_post_ids = [p.post_id for p in post_results if p.post_id]
        summarized_postiz_status, all_release_urls = _summarize_postiz_posts(post_results)
        primary_post_id = all_post_ids[0] if all_post_ids else None
        response_json = [p.raw_json for p in post_results if isinstance(p.raw_json, dict)]

        # Update publication with success
        pub_repo.update_on_success(
            org_id=auth.org_id,
            publication_id=str(publication.id),
            postiz_post_id=primary_post_id,
            postiz_post_ids_json=all_post_ids,
            response_payload_json=response_json[0] if len(response_json) == 1 else response_json,
            status=_local_publication_status_for_post_type(payload.post_type),
            release_urls_json=all_release_urls,
            postiz_post_status=summarized_postiz_status,
        )
    except PostizMissingProviderSettingsError as exc:
        # Clean error - provider settings are missing
        pub_repo.update_on_error(
            org_id=auth.org_id,
            publication_id=str(publication.id),
            error_payload_json={"error": str(exc), "type": "missing_provider_settings"},
            status="failed",
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except PostizClientError as exc:
        # Other API errors
        pub_repo.update_on_error(
            org_id=auth.org_id,
            publication_id=str(publication.id),
            error_payload_json={"error": str(exc), "type": "api_error"},
            status="failed",
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create Postiz post: {exc}",
        ) from exc

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    # Refresh and return
    updated = pub_repo.get(org_id=auth.org_id, publication_id=str(publication.id))
    return jsonable_encoder(_serialize_publication(updated))


@router.delete("/posts/{post_id}")
def delete_post(
    client_id: str,
    post_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Delete a Postiz post by publication ID."""
    _require_client(session, org_id=auth.org_id, client_id=client_id)

    pub_repo = PostizPublicationRepository(session)
    publication = pub_repo.get(org_id=auth.org_id, publication_id=post_id)
    if publication is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Postiz publication not found.",
        )

    postiz_ids = list(publication.postiz_post_ids_json or [])
    if publication.postiz_post_id and publication.postiz_post_id not in postiz_ids:
        postiz_ids.insert(0, publication.postiz_post_id)

    if not postiz_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete this publication remotely: it has no Postiz post ID. "
                "The post may not have been created successfully. "
                "Delete the local record only."
            ),
        )

    try:
        client, _ = _get_client(session, org_id=auth.org_id, client_id=client_id)
        client.delete_post(postiz_ids[0])
    except PostizNotFoundError:
        # Post already gone from Postiz - that's fine
        pass
    except PostizClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete Postiz post: {exc}",
        ) from exc

    deleted = pub_repo.delete(org_id=auth.org_id, publication_id=post_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Postiz publication not found.",
        )

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    return {"deleted": True}


@router.post("/posts/{post_id}/sync")
def sync_post(
    client_id: str,
    post_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """
    Sync a Postiz post status by querying Postiz list posts within a bounded
    date window around the publication timestamp.
    """
    _require_client(session, org_id=auth.org_id, client_id=client_id)

    pub_repo = PostizPublicationRepository(session)
    publication = pub_repo.get(org_id=auth.org_id, publication_id=post_id)
    if publication is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Postiz publication not found.",
        )

    postiz_ids = set(publication.postiz_post_ids_json or [])
    if publication.postiz_post_id:
        postiz_ids.add(publication.postiz_post_id)
    if not postiz_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot sync: this publication has no Postiz post ID.",
        )

    try:
        client, _ = _get_client(session, org_id=auth.org_id, client_id=client_id)
    except HTTPException:
        raise

    # Use a bounded date window around the publication timestamp
    # Default to created_at if scheduled_for is not set
    base_time = publication.scheduled_for or publication.created_at
    # Go back 1 day and forward 7 days to catch scheduling variance
    from datetime import timedelta

    start_date = base_time - timedelta(days=1)
    end_date = base_time + timedelta(days=7)

    # Query Postiz for posts within the date window
    all_posts = client.list_posts(start_date=start_date, end_date=end_date)
    matched_posts = [post for post in all_posts if post.post_id in postiz_ids]

    if not matched_posts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Postiz post(s) {sorted(postiz_ids)} not found in Postiz.",
        )

    summarized_postiz_status, release_urls = _summarize_postiz_posts(matched_posts)
    pub_repo.update_sync(
        org_id=auth.org_id,
        publication_id=post_id,
        postiz_post_status=summarized_postiz_status,
        release_urls_json=release_urls,
        status=_local_publication_status_for_synced_post(
            publication.post_type,
            summarized_postiz_status,
        ),
    )

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    updated = pub_repo.get(org_id=auth.org_id, publication_id=post_id)
    return jsonable_encoder(_serialize_publication(updated))
