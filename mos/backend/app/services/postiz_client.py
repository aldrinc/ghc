"""
Postiz API client service.

Provides methods for interacting with Postiz public API endpoints:
- GET /public/v1/is-connected
- GET /public/v1/integrations
- GET /public/v1/social/{integration}
- POST /public/v1/upload-from-url
- POST /public/v1/posts
- GET /public/v1/posts
- DELETE /public/v1/posts/{id}

Note: Postiz public API does NOT expose integration-settings or integration-trigger
endpoints. MOS must accept/store explicit provider-settings JSON keyed by provider
identifier and return clean errors when a provider requires settings that are missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class PostizClientError(RuntimeError):
    """Base exception for Postiz client errors."""

    pass


class PostizAuthenticationError(PostizClientError):
    """Raised when authentication fails."""

    pass


class PostizNotConnectedError(PostizClientError):
    """Raised when Postiz reports not connected."""

    pass


class PostizMissingProviderSettingsError(PostizClientError):
    """Raised when provider settings are required but missing."""

    pass


class PostizNotFoundError(PostizClientError):
    """Raised when a resource is not found in Postiz."""

    pass


class PostizBrowserAuthError(PostizClientError):
    """Raised when Postiz browser authentication fails."""

    pass


class PostizBrowserProvisioningError(PostizClientError):
    """Raised when MOS cannot provision a Postiz browser user/session."""

    pass


@dataclass
class PostizIntegration:
    """Represents a Postiz integration (social network connection)."""

    id: str
    name: str
    identifier: str
    profile: str | None
    picture_url: str | None
    disabled: bool


@dataclass
class PostizChannel:
    """Represents a Postiz channel (connected social media account)."""

    id: str
    integration_id: str
    identifier: str
    name: str
    profile: str | None
    picture_url: str | None
    is_disabled: bool


@dataclass
class PostizSocialConnectUrl:
    """Represents OAuth URL for connecting a social account."""

    url: str
    integration: str


@dataclass
class PostizUploadedMedia:
    """Represents an uploaded media item in Postiz."""

    id: str
    path: str


@dataclass
class PostizPost:
    """Represents a Postiz post."""

    post_id: str
    content: str
    type: str
    status: str
    scheduled_for: datetime | None
    release_url: str | None
    provider_identifier: str | None
    raw_json: dict[str, Any]


@dataclass
class PostizBrowserOrg:
    """Authenticated Postiz organization available to the current user."""

    id: str
    name: str
    api_key: str | None


@dataclass
class PostizBrowserSession:
    """Authenticated Postiz browser session prepared by MOS."""

    auth_token: str
    orgs: list[PostizBrowserOrg]
    current_org_id: str | None
    current_public_api: str | None


class PostizClient:
    """Client for Postiz public API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _api_base(self) -> str:
        return f"{self.base_url}/public/v1"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise appropriate exception for HTTP error."""
        if response.status_code == 401:
            raise PostizAuthenticationError("Invalid Postiz API key.")
        if response.status_code == 404:
            raise PostizNotFoundError(f"Postiz resource not found: {response.text}")
        if response.status_code >= 400:
            raise PostizClientError(f"Postiz API error ({response.status_code}): {response.text}")

    def validate_connection(self) -> tuple[bool, Optional[str]]:
        """
        Validate credentials by calling GET /public/v1/is-connected.
        Returns (is_valid, error_message).
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self._api_base()}/is-connected",
                    headers=self._headers(),
                )
                if response.status_code == 401:
                    return False, "Invalid Postiz API key."
                if response.status_code == 403:
                    return False, "Insufficient permissions for Postiz API."
                if response.status_code >= 400:
                    return False, f"Postiz API error: {response.text}"
                payload = response.json()
                if isinstance(payload, dict) and payload.get("connected") is True:
                    return True, None
                message = payload.get("message") if isinstance(payload, dict) else None
                if isinstance(message, str) and message.strip():
                    return False, message.strip()
                return False, "Postiz credential validation failed."
        except httpx.TimeoutException:
            return False, "Request timed out while validating Postiz connection."
        except httpx.HTTPError as exc:
            return False, f"HTTP error while validating Postiz connection: {exc}"

    def list_integrations(self) -> list[PostizIntegration]:
        """
        List available Postiz integrations.
        GET /public/v1/integrations
        """
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    f"{self._api_base()}/integrations",
                    headers=self._headers(),
                )
                self._raise_for_status(response)
                payload = response.json()
                results = payload if isinstance(payload, list) else []
                integrations = []
                for item in results:
                    integrations.append(
                        PostizIntegration(
                            id=str(item.get("id", "")),
                            name=item.get("name", ""),
                            identifier=item.get("identifier", ""),
                            profile=item.get("profile"),
                            picture_url=item.get("picture"),
                            disabled=bool(item.get("disabled")),
                        )
                    )
                return integrations
        except httpx.HTTPError as exc:
            raise PostizClientError(f"Failed to list Postiz integrations: {exc}") from exc

    def get_social_connect_url(self, integration: str) -> PostizSocialConnectUrl:
        """
        Get OAuth URL for connecting a social account.
        GET /public/v1/social/{integration}
        """
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    f"{self._api_base()}/social/{integration}",
                    headers=self._headers(),
                )
                self._raise_for_status(response)
                payload = response.json()
                data = payload if isinstance(payload, dict) else {}
                return PostizSocialConnectUrl(
                    url=data.get("url", ""),
                    integration=integration,
                )
        except httpx.HTTPError as exc:
            raise PostizClientError(
                f"Failed to get Postiz social connect URL for {integration}: {exc}"
            ) from exc

    def upload_media_from_url(self, url: str) -> PostizUploadedMedia:
        """
        Upload media to Postiz from a URL.
        POST /public/v1/upload-from-url
        """
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self._api_base()}/upload-from-url",
                    headers=self._headers(),
                    json={"url": url},
                )
                self._raise_for_status(response)
                payload = response.json()
                data = payload if isinstance(payload, dict) else {}
                return PostizUploadedMedia(
                    id=data.get("id", ""),
                    path=data.get("path", ""),
                )
        except httpx.HTTPError as exc:
            raise PostizClientError(f"Failed to upload media to Postiz: {exc}") from exc

    def create_post(
        self,
        content: str,
        targets: list[dict[str, str]],
        post_type: str = "now",
        scheduled_for: datetime | None = None,
        media: list[PostizUploadedMedia] | None = None,
        short_link: bool = False,
        provider_settings_by_identifier: dict[str, Any] | None = None,
    ) -> list[PostizPost]:
        """
        Create a post in Postiz.
        POST /public/v1/posts

        Args:
            content: Post text content.
            targets: List of target dicts with integration_id and identifier.
            post_type: "now", "schedule", or "draft".
            scheduled_for: Required when post_type is "schedule".
            media: Optional uploaded Postiz media items to attach.
            short_link: Whether Postiz should shorten links.
            provider_settings_by_identifier: Provider-specific settings keyed by
                provider identifier. Raises PostizMissingProviderSettingsError if
                a provider requires settings that are missing.

        Returns:
            List of PostizPost objects, one per channel.
        """
        if post_type == "schedule" and scheduled_for is None:
            raise PostizClientError(
                "scheduledFor is required when creating a scheduled Postiz post."
            )

        simple_providers = {
            "threads",
            "mastodon",
            "bluesky",
            "telegram",
            "nostr",
            "vk",
            "kick",
            "linkedin",
            "linkedin-page",
            "facebook",
            "gmb",
        }
        posts_entries: list[dict[str, Any]] = []
        missing_settings: list[str] = []
        for target in targets:
            integration_id = target.get("integration_id", "")
            identifier = target.get("identifier", "")
            value_entry: dict[str, Any] = {"content": content, "image": []}
            if media:
                value_entry["image"] = [{"id": item.id, "path": item.path} for item in media]
            entry = {
                "integration": {"id": integration_id},
                "value": [value_entry],
            }

            settings = (provider_settings_by_identifier or {}).get(identifier)
            if settings is None and identifier in simple_providers:
                settings = {"__type": identifier}
            if settings is None:
                missing_settings.append(identifier)
            else:
                entry["settings"] = settings
            posts_entries.append(entry)

        if missing_settings:
            raise PostizMissingProviderSettingsError(
                "Missing provider settings for: " + ", ".join(sorted(set(missing_settings)))
            )

        # Build request payload per Postiz docs
        post_payload: dict[str, Any] = {
            "type": post_type,
            "date": (scheduled_for or datetime.now(timezone.utc)).isoformat(),
            "shortLink": bool(short_link),
            "tags": [],
            "posts": posts_entries,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self._api_base()}/posts",
                    headers=self._headers(),
                    json=post_payload,
                )
                # Parse response first to check for business logic errors
                payload = response.json()

                # Check if Postiz returned an error about missing provider settings
                if isinstance(payload, dict):
                    if payload.get("error") or payload.get("status") == "error":
                        error_msg = payload.get("message", payload.get("error", "Unknown error"))
                        if "settings" in str(error_msg).lower():
                            raise PostizMissingProviderSettingsError(
                                f"Postiz reports missing provider settings: {error_msg}. "
                                "Ensure providerSettingsByIdentifier is provided for all required providers."
                            )
                        raise PostizClientError(f"Postiz post creation failed: {error_msg}")

                # Now check HTTP status
                self._raise_for_status(response)

                # Response is an array of { postId, integration } objects
                results: list[PostizPost] = []
                items = payload if isinstance(payload, list) else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    results.append(
                        PostizPost(
                            post_id=str(item.get("postId", "")),
                            content=content,
                            type=post_type,
                            status="QUEUE",
                            scheduled_for=scheduled_for,
                            release_url=item.get("releaseUrl"),
                            provider_identifier=None,
                            raw_json=item,
                        )
                    )
                return results
        except httpx.HTTPError as exc:
            raise PostizClientError(f"Failed to create Postiz post: {exc}") from exc

    def list_posts(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[PostizPost]:
        """
        List posts from Postiz within a date range.
        GET /public/v1/posts?startDate=...&endDate=...

        Returns list of PostizPost objects.
        """
        params: dict[str, Any] = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    f"{self._api_base()}/posts",
                    headers=self._headers(),
                    params=params,
                )
                self._raise_for_status(response)
                payload = response.json()
                data = payload if isinstance(payload, dict) else {}
                results = data.get("posts", []) if isinstance(data, dict) else []

                posts = []
                for item in results if isinstance(results, list) else []:
                    scheduled_str = item.get("publishDate") or item.get("scheduledFor")
                    scheduled_dt = None
                    if scheduled_str:
                        try:
                            scheduled_dt = datetime.fromisoformat(
                                scheduled_str.replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass

                    # Extract integration identifier
                    integration_info = item.get("integration", {})
                    integration_id = ""
                    if isinstance(integration_info, dict):
                        integration_id = integration_info.get("providerIdentifier", "")

                    posts.append(
                        PostizPost(
                            post_id=str(item.get("id", "")),
                            content=item.get("content", ""),
                            type=item.get("type", "unknown"),
                            status=str(item.get("state", "unknown")).upper(),
                            scheduled_for=scheduled_dt,
                            release_url=item.get("releaseURL"),
                            provider_identifier=integration_id or None,
                            raw_json=item,
                        )
                    )
                return posts
        except httpx.HTTPError as exc:
            raise PostizClientError(f"Failed to list Postiz posts: {exc}") from exc

    def delete_post(self, post_id: str) -> bool:
        """
        Delete a post from Postiz.
        DELETE /public/v1/posts/{id}

        Returns True if deleted, raises PostizNotFoundError if not found.
        """
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.delete(
                    f"{self._api_base()}/posts/{post_id}",
                    headers=self._headers(),
                )
                if response.status_code == 404:
                    raise PostizNotFoundError(f"Postiz post not found: {post_id}")
                self._raise_for_status(response)
                return True
        except httpx.HTTPError as exc:
            raise PostizClientError(f"Failed to delete Postiz post: {exc}") from exc


class PostizBrowserClient:
    """Client for Postiz browser-authenticated routes."""

    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _extract_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            for key in ("message", "detail", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, list):
                    messages = [item.strip() for item in value if isinstance(item, str) and item.strip()]
                    if messages:
                        return "; ".join(messages)
        text = response.text.strip()
        return text or f"Postiz returned HTTP {response.status_code}."

    def _auth_headers(self, auth_token: str) -> dict[str, str]:
        return {"auth": auth_token}

    def create_session(
        self,
        *,
        email: str,
        password: str,
        company: str,
        allow_register: bool,
    ) -> PostizBrowserSession:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            auth_token = self._login(client, email=email, password=password)
            if auth_token is None and allow_register:
                auth_token = self._register(client, email=email, password=password, company=company)
            if auth_token is None:
                raise PostizBrowserAuthError("Postiz login failed and registration is disabled.")

            current_org_id, current_public_api = self._get_self(client, auth_token=auth_token)
            orgs = self._get_orgs(client, auth_token=auth_token)
            return PostizBrowserSession(
                auth_token=auth_token,
                orgs=orgs,
                current_org_id=current_org_id,
                current_public_api=current_public_api,
            )

    def _login(self, client: httpx.Client, *, email: str, password: str) -> str | None:
        response = client.post(
            "/auth/login",
            json={
                "provider": "LOCAL",
                "providerToken": "",
                "email": email,
                "password": password,
            },
        )
        if response.is_success:
            auth_token = response.cookies.get("auth") or client.cookies.get("auth")
            if auth_token:
                return auth_token
            raise PostizBrowserAuthError("Postiz login succeeded but no auth cookie was issued.")

        if response.status_code in {400, 401}:
            return None
        raise PostizBrowserAuthError(self._extract_message(response))

    def _register(
        self,
        client: httpx.Client,
        *,
        email: str,
        password: str,
        company: str,
    ) -> str:
        response = client.post(
            "/auth/register",
            json={
                "provider": "LOCAL",
                "providerToken": "",
                "email": email,
                "password": password,
                "company": company,
            },
        )
        if not response.is_success:
            raise PostizBrowserProvisioningError(self._extract_message(response))
        if response.headers.get("activate") == "true":
            raise PostizBrowserProvisioningError(
                "Postiz requires email activation before browser sign-in can complete."
            )
        auth_token = response.cookies.get("auth") or client.cookies.get("auth")
        if not auth_token:
            raise PostizBrowserProvisioningError(
                "Postiz registration succeeded but no auth cookie was issued."
            )
        return auth_token

    def _get_self(self, client: httpx.Client, *, auth_token: str) -> tuple[str | None, str | None]:
        response = client.get("/user/self", headers=self._auth_headers(auth_token))
        if not response.is_success:
            raise PostizBrowserAuthError(self._extract_message(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise PostizBrowserAuthError("Postiz returned an invalid /user/self payload.")
        org_id = payload.get("orgId")
        public_api = payload.get("publicApi")
        return (
            str(org_id).strip() if isinstance(org_id, str) and org_id.strip() else None,
            str(public_api).strip() if isinstance(public_api, str) and public_api.strip() else None,
        )

    def _get_orgs(self, client: httpx.Client, *, auth_token: str) -> list[PostizBrowserOrg]:
        response = client.get("/user/organizations", headers=self._auth_headers(auth_token))
        if not response.is_success:
            raise PostizBrowserAuthError(self._extract_message(response))
        payload = response.json()
        if not isinstance(payload, list):
            raise PostizBrowserAuthError("Postiz returned an invalid /user/organizations payload.")

        orgs: list[PostizBrowserOrg] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            org_id = item.get("id")
            name = item.get("name")
            if not isinstance(org_id, str) or not org_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = "Postiz organization"
            api_key = item.get("apiKey")
            orgs.append(
                PostizBrowserOrg(
                    id=org_id.strip(),
                    name=name.strip(),
                    api_key=api_key.strip() if isinstance(api_key, str) and api_key.strip() else None,
                )
            )
        return orgs


def create_postiz_client(
    api_key: str,
    base_url: str,
    timeout_seconds: float | None = None,
) -> PostizClient:
    """Factory function to create Postiz client."""
    return PostizClient(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout_seconds or settings.POSTIZ_TIMEOUT_SECONDS,
    )


def create_postiz_browser_client(
    base_url: str,
    timeout_seconds: float | None = None,
) -> PostizBrowserClient:
    """Factory function to create a browser-authenticated Postiz client."""
    return PostizBrowserClient(
        base_url=base_url,
        timeout_seconds=timeout_seconds or settings.POSTIZ_TIMEOUT_SECONDS,
    )
