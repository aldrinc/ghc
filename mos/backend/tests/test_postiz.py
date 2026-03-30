"""Tests for Postiz integration."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.db.models import (
    ClientPostizChannel,
    ClientPostizCredentials,
    ClientPostizPostingProfile,
    PostizPublication,
    User,
)
from app.db.repositories.postiz import (
    PostizChannelRepository,
    PostizCredentialsRepository,
    PostizPostingProfileRepository,
    PostizPublicationRepository,
)
from app.routers.postiz import _derive_postiz_browser_password
from app.services.postiz_client import (
    PostizBrowserClient,
    PostizBrowserProvisioningError,
    PostizBrowserOrg,
    PostizBrowserSession,
    PostizChannel,
    PostizClient,
    PostizClientError,
    PostizIntegration,
    PostizMissingProviderSettingsError,
    PostizNotFoundError,
    PostizSocialConnectUrl,
    PostizUploadedMedia,
    PostizPost,
)
from tests.conftest import TEST_ORG_ID


# =============================================================================
# PostizClient unit tests (with monkeypatch/fakes)
# =============================================================================


def _make_fake_httpx_response(
    json_data: object,
    status_code: int = 200,
    *,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Create a fake httpx.Response object."""
    response = MagicMock()
    response.status_code = status_code
    response.is_success = 200 <= status_code < 300
    response.json.return_value = json_data
    response.text = str(json_data)
    response.cookies = cookies or {}
    response.headers = headers or {}
    return response


def _make_fake_httpx_error(message: str) -> Exception:
    """Create a fake httpx.HTTPError."""
    return PostizClientError(message)


class TestPostizClientValidateConnection:
    """Tests for PostizClient.validate_connection()."""

    def test_validate_connection_success(self) -> None:
        """Should return (True, None) when Postiz returns connected: true."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        fake_response = _make_fake_httpx_response({"connected": True, "message": "ok"})
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_client_cls.return_value = mock_client

            is_valid, error = client.validate_connection()

        assert is_valid is True
        assert error is None

    def test_validate_connection_invalid_key(self) -> None:
        """Should return (False, message) when API returns 401."""
        client = PostizClient(api_key="bad-key", base_url="https://postiz.example.com")

        fake_response = _make_fake_httpx_response({"error": "Unauthorized"}, status_code=401)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_client_cls.return_value = mock_client

            is_valid, error = client.validate_connection()

        assert is_valid is False
        assert "Invalid Postiz API key" in error


class TestPostizBrowserClient:
    """Tests for PostizBrowserClient browser-authenticated flows."""

    def test_browser_password_stays_within_postiz_limit(self) -> None:
        with patch("app.routers.postiz.settings.POSTIZ_BROWSER_LOGIN_SECRET", "test-secret"):
            password = _derive_postiz_browser_password(
                user_id="user_36iTMtClnkSdcRBDFuqvcD72Dwt",
                email="aldrin.clement@gmail.com",
            )

        assert password.startswith("mos-postiz-")
        assert len(password) <= 64

    def test_create_session_uses_api_base_and_local_provider_token(self) -> None:
        client = PostizBrowserClient(base_url="http://localhost:4007/api")

        login_response = _make_fake_httpx_response(
            {"login": True},
            cookies={"auth": "postiz-auth-token"},
            headers={"reload": "true"},
        )
        self_response = _make_fake_httpx_response({"orgId": "org-1", "publicApi": "org-api-key"})
        orgs_response = _make_fake_httpx_response(
            [{"id": "org-1", "name": "Org One", "apiKey": "org-api-key"}]
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = login_response
            mock_client.get.side_effect = [self_response, orgs_response]
            mock_client_cls.return_value = mock_client

            session = client.create_session(
                email="owner@example.com",
                password="secret-password",
                company="ACME",
                allow_register=False,
            )

        mock_client_cls.assert_called_once_with(base_url="http://localhost:4007/api", timeout=30.0)
        mock_client.post.assert_called_once_with(
            "/auth/login",
            json={
                "provider": "LOCAL",
                "providerToken": "",
                "email": "owner@example.com",
                "password": "secret-password",
            },
        )
        assert mock_client.get.call_args_list[0].args == ("/user/self",)
        assert mock_client.get.call_args_list[1].args == ("/user/organizations",)
        assert session == PostizBrowserSession(
            auth_token="postiz-auth-token",
            orgs=[PostizBrowserOrg(id="org-1", name="Org One", api_key="org-api-key")],
            current_org_id="org-1",
            current_public_api="org-api-key",
        )

    def test_create_session_registers_with_local_provider_token_when_login_fails(self) -> None:
        client = PostizBrowserClient(base_url="http://localhost:4007/api")

        login_response = _make_fake_httpx_response(
            {"message": "Invalid user name or password"},
            status_code=400,
        )
        register_response = _make_fake_httpx_response(
            {"register": True},
            cookies={"auth": "postiz-auth-token"},
        )
        self_response = _make_fake_httpx_response({"orgId": "org-1", "publicApi": "org-api-key"})
        orgs_response = _make_fake_httpx_response(
            [{"id": "org-1", "name": "Org One", "apiKey": "org-api-key"}]
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = [login_response, register_response]
            mock_client.get.side_effect = [self_response, orgs_response]
            mock_client_cls.return_value = mock_client

            session = client.create_session(
                email="owner@example.com",
                password="secret-password",
                company="ACME",
                allow_register=True,
            )

        assert mock_client.post.call_args_list[1].kwargs == {
            "json": {
                "provider": "LOCAL",
                "providerToken": "",
                "email": "owner@example.com",
                "password": "secret-password",
                "company": "ACME",
            }
        }
        assert session.auth_token == "postiz-auth-token"

    def test_create_session_surfaces_array_validation_messages(self) -> None:
        client = PostizBrowserClient(base_url="http://localhost:4007/api")

        login_response = _make_fake_httpx_response(
            {"message": "Invalid user name or password"},
            status_code=400,
        )
        register_response = _make_fake_httpx_response(
            {
                "message": ["password must be shorter than or equal to 64 characters"],
                "error": "Bad Request",
            },
            status_code=400,
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = [login_response, register_response]
            mock_client_cls.return_value = mock_client

            with pytest.raises(
                PostizBrowserProvisioningError,
                match="password must be shorter than or equal to 64 characters",
            ):
                client.create_session(
                    email="owner@example.com",
                    password="secret-password",
                    company="ACME",
                    allow_register=True,
                )


class TestPostizClientListIntegrations:
    """Tests for PostizClient.list_integrations()."""

    def test_list_integrations_success(self) -> None:
        """Should parse integrations from API response (direct array)."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        # Postiz returns integrations as a direct array, not {data: [...]}
        fake_payload = [
            {
                "id": "int-1",
                "name": "Instagram",
                "identifier": "instagram",
                "picture": "https://example.com/instagram.png",
                "profile": "acmegram",
                "disabled": False,
            },
            {
                "id": "int-2",
                "name": "Twitter",
                "identifier": "twitter",
                "picture": None,
                "profile": "acmex",
                "disabled": True,
            },
        ]
        fake_response = _make_fake_httpx_response(fake_payload)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_client_cls.return_value = mock_client

            integrations = client.list_integrations()

        assert len(integrations) == 2
        assert integrations[0].id == "int-1"
        assert integrations[0].name == "Instagram"
        assert integrations[0].picture_url == "https://example.com/instagram.png"
        assert integrations[0].profile == "acmegram"
        assert integrations[0].disabled is False
        assert integrations[1].id == "int-2"
        assert integrations[1].name == "Twitter"
        assert integrations[1].disabled is True


class TestPostizClientCreatePost:
    """Tests for PostizClient.create_post()."""

    def test_create_post_success(self) -> None:
        """Should create a post and return list of PostizPost (one per channel)."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        # Postiz returns an array of {postId, integration} objects
        fake_payload = [
            {
                "postId": "post-123",
                "integration": {"id": "int-1"},
                "releaseUrl": "https://example.com/post/123",
            },
            {
                "postId": "post-456",
                "integration": {"id": "int-2"},
                "releaseUrl": "https://example.com/post/456",
            },
        ]
        fake_response = _make_fake_httpx_response(fake_payload)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            results = client.create_post(
                content="Hello world",
                targets=[
                    {"integration_id": "int-1", "identifier": "threads"},
                    {"integration_id": "int-2", "identifier": "threads"},
                ],
                post_type="now",
            )

        assert len(results) == 2
        assert results[0].post_id == "post-123"
        assert results[0].status == "QUEUE"
        assert results[0].release_url == "https://example.com/post/123"
        assert results[1].post_id == "post-456"
        assert results[1].release_url == "https://example.com/post/456"

    def test_create_post_missing_provider_settings_raises(self) -> None:
        """Should raise PostizMissingProviderSettingsError when API reports missing settings."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        with pytest.raises(PostizMissingProviderSettingsError):
            client.create_post(
                content="Hello world",
                targets=[{"integration_id": "int-1", "identifier": "x"}],
                post_type="now",
            )

    def test_create_post_single_channel(self) -> None:
        """Should handle single channel post response."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        fake_payload = [
            {
                "postId": "post-single",
                "integration": {"id": "int-1"},
                "releaseUrl": "https://example.com/post/single",
            },
        ]
        fake_response = _make_fake_httpx_response(fake_payload)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            results = client.create_post(
                content="Single channel post",
                targets=[{"integration_id": "int-1", "identifier": "threads"}],
                post_type="now",
            )

        assert len(results) == 1
        assert results[0].post_id == "post-single"


class TestPostizClientListPosts:
    """Tests for PostizClient.list_posts()."""

    def test_list_posts_success(self) -> None:
        """Should parse posts from {posts: [...]} response with startDate/endDate."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        fake_payload = {
            "posts": [
                {
                    "id": "post-1",
                    "content": "Hello world",
                    "type": "now",
                    "state": "PUBLISHED",
                    "publishDate": "2026-03-26T10:00:00Z",
                    "releaseURL": "https://example.com/post/1",
                    "integration": {"providerIdentifier": "instagram"},
                },
                {
                    "id": "post-2",
                    "content": "Second post",
                    "type": "schedule",
                    "state": "QUEUED",
                    "publishDate": "2026-03-27T10:00:00Z",
                    "releaseURL": "https://example.com/post/2",
                    "integration": {"providerIdentifier": "twitter"},
                },
            ]
        }
        fake_response = _make_fake_httpx_response(fake_payload)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_client_cls.return_value = mock_client

            start = datetime(2026, 3, 1, tzinfo=timezone.utc)
            end = datetime(2026, 3, 31, tzinfo=timezone.utc)
            posts = client.list_posts(start_date=start, end_date=end)

        assert len(posts) == 2
        assert posts[0].post_id == "post-1"
        assert posts[0].content == "Hello world"
        assert posts[0].status == "PUBLISHED"
        assert posts[0].release_url == "https://example.com/post/1"
        assert posts[1].post_id == "post-2"
        assert posts[1].status == "QUEUED"


class TestPostizClientDeletePost:
    """Tests for PostizClient.delete_post()."""

    def test_delete_post_success(self) -> None:
        """Should return True on successful deletion."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        fake_response = _make_fake_httpx_response({"success": True}, status_code=200)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.delete.return_value = fake_response
            mock_client_cls.return_value = mock_client

            result = client.delete_post("post-123")

        assert result is True

    def test_delete_post_not_found_raises(self) -> None:
        """Should raise PostizNotFoundError when API returns 404."""
        client = PostizClient(api_key="test-key", base_url="https://postiz.example.com")

        fake_response = _make_fake_httpx_response({"error": "Not found"}, status_code=404)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.delete.return_value = fake_response
            mock_client_cls.return_value = mock_client

            with pytest.raises(PostizNotFoundError):
                client.delete_post("post-999")


# =============================================================================
# Repository tests
# =============================================================================


def _seed_postiz_credentials(db_session, client_uuid) -> ClientPostizCredentials:
    """Seed Postiz credentials for a client."""
    from app.services.integration_secrets import encrypt_secret_json

    encrypted = encrypt_secret_json({"apiKey": "test-key"})
    creds = ClientPostizCredentials(
        org_id=TEST_ORG_ID,
        client_id=client_uuid,
        base_url="https://postiz.example.com",
        credentials_encrypted=encrypted,
    )
    db_session.add(creds)
    db_session.commit()
    db_session.refresh(creds)
    return creds


def _seed_mos_user(db_session, *, email: str = "owner@example.com") -> User:
    user = User(
        org_id=TEST_ORG_ID,
        clerk_user_id="test-user",
        email=email,
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestPostizCredentialsRepository:
    """Tests for PostizCredentialsRepository."""

    def test_upsert_and_get(self, db_session, seed_data) -> None:
        """Should upsert and retrieve credentials."""
        from app.services.integration_secrets import encrypt_secret_json

        client_uuid = seed_data["client"].id
        repo = PostizCredentialsRepository(db_session)
        encrypted = encrypt_secret_json({"apiKey": "new-key"})
        result = repo.upsert(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            base_url="https://postiz.example.com",
            credentials_encrypted=encrypted,
        )

        assert result.org_id == TEST_ORG_ID
        assert result.client_id == client_uuid

        retrieved = repo.get(org_id=TEST_ORG_ID, client_id=client_uuid)
        assert retrieved is not None
        assert retrieved.base_url == "https://postiz.example.com"

    def test_update_validation(self, db_session, seed_data) -> None:
        """Should update validation timestamp and error."""
        client_uuid = seed_data["client"].id
        creds = _seed_postiz_credentials(db_session, client_uuid)
        repo = PostizCredentialsRepository(db_session)

        now = datetime.now(timezone.utc)
        updated = repo.update_validation(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            last_validated_at=now,
            last_validation_error=None,
        )

        assert updated is not None
        assert updated.last_validated_at == now
        assert updated.last_validation_error is None


class TestPostizChannelRepository:
    """Tests for PostizChannelRepository."""

    def test_upsert_and_list(self, db_session, seed_data) -> None:
        """Should upsert and list channels."""
        client_uuid = seed_data["client"].id
        repo = PostizChannelRepository(db_session)

        channel = repo.upsert(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            postiz_integration_id="int-1",
            postiz_channel_id="ch-1",
            identifier="instagram",
            name="Instagram Account",
            profile="personal",
            picture_url="https://example.com/pic.jpg",
            disabled=False,
            is_default=True,
            metadata_json={"foo": "bar"},
        )

        assert channel.org_id == TEST_ORG_ID
        assert channel.name == "Instagram Account"

        channels = repo.list(org_id=TEST_ORG_ID, client_id=client_uuid)
        assert len(channels) == 1
        assert channels[0].name == "Instagram Account"

    def test_clear_for_client(self, db_session, seed_data) -> None:
        """Should delete all channels for a client."""
        client_uuid = seed_data["client"].id
        repo = PostizChannelRepository(db_session)

        repo.upsert(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            postiz_integration_id="int-1",
            postiz_channel_id="ch-1",
            identifier="instagram",
            name="Instagram Account",
        )
        repo.upsert(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            postiz_integration_id="int-2",
            postiz_channel_id="ch-2",
            identifier="twitter",
            name="Twitter Account",
        )

        count = repo.clear_for_client(org_id=TEST_ORG_ID, client_id=client_uuid)
        assert count == 2

        remaining = repo.list(org_id=TEST_ORG_ID, client_id=client_uuid)
        assert len(remaining) == 0


class TestPostizPostingProfileRepository:
    """Tests for PostizPostingProfileRepository."""

    def test_create_and_get_default(self, db_session, seed_data) -> None:
        """Should create and retrieve default profile."""
        client_uuid = seed_data["client"].id
        repo = PostizPostingProfileRepository(db_session)

        profile = repo.create(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            name="Default Profile",
            is_default=True,
            default_channel_ids=["ch-1", "ch-2"],
            provider_settings_json={"twitter": {"access_token": "abc"}},
        )

        assert profile.name == "Default Profile"
        assert profile.is_default is True

        default = repo.get_default(org_id=TEST_ORG_ID, client_id=client_uuid)
        assert default is not None
        assert default.name == "Default Profile"

    def test_update_clears_other_defaults(self, db_session, seed_data) -> None:
        """Updating a profile to is_default=True should clear other defaults."""
        client_uuid = seed_data["client"].id
        repo = PostizPostingProfileRepository(db_session)

        profile1 = repo.create(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            name="Profile 1",
            is_default=True,
        )
        profile2 = repo.create(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            name="Profile 2",
            is_default=False,
        )

        # Update profile2 to be default
        repo.update(
            org_id=TEST_ORG_ID,
            profile_id=str(profile2.id),
            is_default=True,
        )

        # Refresh profile1
        db_session.refresh(profile1)
        assert profile1.is_default is False
        assert profile2.is_default is True


class TestPostizPublicationRepository:
    """Tests for PostizPublicationRepository."""

    def test_create_and_list(self, db_session, seed_data) -> None:
        """Should create and list publications."""
        client_uuid = seed_data["client"].id
        repo = PostizPublicationRepository(db_session)

        pub = repo.create(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            content="Hello world",
            post_type="now",
            target_channels_json={"channel_ids": ["ch-1"]},
            request_payload_json={"content": "Hello world"},
        )

        assert pub.content == "Hello world"
        assert pub.status == "pending"

        pubs, total = repo.list(org_id=TEST_ORG_ID, client_id=client_uuid)
        assert len(pubs) == 1
        assert total == 1

    def test_update_on_success(self, db_session, seed_data) -> None:
        """Should update publication on successful Postiz response."""
        client_uuid = seed_data["client"].id
        repo = PostizPublicationRepository(db_session)

        pub = repo.create(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            content="Hello world",
            post_type="now",
            target_channels_json={"channel_ids": ["ch-1"]},
            request_payload_json={"content": "Hello world"},
        )

        updated = repo.update_on_success(
            org_id=TEST_ORG_ID,
            publication_id=str(pub.id),
            postiz_post_id="post-123",
            response_payload_json={"postId": "post-123", "status": "QUEUED"},
            status="published",
            release_urls_json=["https://example.com/post/123"],
            postiz_post_status="QUEUED",
        )

        assert updated is not None
        assert updated.postiz_post_id == "post-123"
        assert updated.status == "published"
        assert "https://example.com/post/123" in updated.release_urls_json

    def test_update_on_error(self, db_session, seed_data) -> None:
        """Should update publication on API error."""
        client_uuid = seed_data["client"].id
        repo = PostizPublicationRepository(db_session)

        pub = repo.create(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            content="Hello world",
            post_type="now",
            target_channels_json={"channel_ids": ["ch-1"]},
            request_payload_json={"content": "Hello world"},
        )

        updated = repo.update_on_error(
            org_id=TEST_ORG_ID,
            publication_id=str(pub.id),
            error_payload_json={"error": "rate limited", "type": "api_error"},
            status="failed",
        )

        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_payload_json["error"] == "rate limited"


class TestPostizApi:
    """API-level tests for Postiz routes."""

    def test_get_credentials_uses_default_base_url_when_unconfigured(
        self, api_client, seed_data, monkeypatch
    ) -> None:
        """Credentials endpoint should surface the configured default Postiz URL."""
        from app.config import settings

        client_uuid = seed_data["client"].id
        monkeypatch.setattr(settings, "POSTIZ_DEFAULT_BASE_URL", "http://localhost:4007/api")

        response = api_client.get(f"/clients/{client_uuid}/postiz/credentials")

        assert response.status_code == 200
        assert response.json() == {
            "hasCredentials": False,
            "baseUrl": "http://localhost:4007/api",
            "authType": None,
            "lastValidatedAt": None,
            "lastValidationError": None,
        }

    def test_create_post_returns_queued_status_until_postiz_confirms_publish(
        self, api_client, db_session, seed_data, monkeypatch
    ) -> None:
        """Create post should record queued delivery, not immediate publish success."""
        client_uuid = seed_data["client"].id
        _seed_postiz_credentials(db_session, client_uuid)
        channel = PostizChannelRepository(db_session).upsert(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            postiz_integration_id="int-1",
            postiz_channel_id="int-1",
            identifier="instagram",
            name="Instagram",
        )
        db_session.commit()

        class FakePostizClient:
            def create_post(self, **_kwargs):
                return [
                    PostizPost(
                        post_id="post-123",
                        content="Hello world",
                        type="now",
                        status="QUEUE",
                        scheduled_for=None,
                        release_url="https://example.com/post/123",
                        provider_identifier="instagram",
                        raw_json={"postId": "post-123"},
                    )
                ]

        monkeypatch.setattr("app.routers.postiz.create_postiz_client", lambda **_kwargs: FakePostizClient())

        response = api_client.post(
            f"/clients/{client_uuid}/postiz/posts",
            json={
                "content": "Hello world",
                "postType": "now",
                "channelIds": [str(channel.id)],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "queued"
        assert payload["postizPostStatus"] == "QUEUE"
        assert payload["releaseUrls"] == ["https://example.com/post/123"]

    def test_create_post_rejects_generic_link_url_until_provider_mapping_exists(
        self, api_client, db_session, seed_data, monkeypatch
    ) -> None:
        """Create post should fail clearly instead of silently ignoring linkUrl."""
        client_uuid = seed_data["client"].id
        _seed_postiz_credentials(db_session, client_uuid)
        channel = PostizChannelRepository(db_session).upsert(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            postiz_integration_id="int-1",
            postiz_channel_id="int-1",
            identifier="facebook",
            name="Facebook",
        )
        db_session.commit()

        class FakePostizClient:
            def create_post(self, **_kwargs):
                raise AssertionError("create_post should not be called when linkUrl is rejected")

        monkeypatch.setattr("app.routers.postiz.create_postiz_client", lambda **_kwargs: FakePostizClient())

        response = api_client.post(
            f"/clients/{client_uuid}/postiz/posts",
            json={
                "content": "Hello world",
                "postType": "now",
                "channelIds": [str(channel.id)],
                "linkUrl": "https://example.com",
            },
        )

        assert response.status_code == 422
        assert "providerSettingsByIdentifier" in response.json()["detail"]

    def test_sync_post_aggregates_release_urls_and_external_state(
        self, api_client, db_session, seed_data, monkeypatch
    ) -> None:
        """Sync should aggregate all matched Postiz posts for one MOS publication."""
        client_uuid = seed_data["client"].id
        _seed_postiz_credentials(db_session, client_uuid)
        publication = PostizPublicationRepository(db_session).create(
            org_id=TEST_ORG_ID,
            client_id=client_uuid,
            content="Scheduled post",
            post_type="schedule",
            scheduled_for=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
            target_channels_json={"channel_ids": ["channel-1", "channel-2"]},
            request_payload_json={"content": "Scheduled post"},
        )
        PostizPublicationRepository(db_session).update_on_success(
            org_id=TEST_ORG_ID,
            publication_id=str(publication.id),
            postiz_post_id="post-1",
            postiz_post_ids_json=["post-1", "post-2"],
            status="scheduled",
            postiz_post_status="QUEUE",
        )
        db_session.commit()

        class FakePostizClient:
            def list_posts(self, **_kwargs):
                return [
                    PostizPost(
                        post_id="post-1",
                        content="Scheduled post",
                        type="schedule",
                        status="QUEUE",
                        scheduled_for=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
                        release_url="https://example.com/post/1",
                        provider_identifier="instagram",
                        raw_json={"id": "post-1"},
                    ),
                    PostizPost(
                        post_id="post-2",
                        content="Scheduled post",
                        type="schedule",
                        status="PUBLISHED",
                        scheduled_for=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
                        release_url="https://example.com/post/2",
                        provider_identifier="facebook",
                        raw_json={"id": "post-2"},
                    ),
                ]

        monkeypatch.setattr("app.routers.postiz.create_postiz_client", lambda **_kwargs: FakePostizClient())

        response = api_client.post(f"/clients/{client_uuid}/postiz/posts/{publication.id}/sync")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "scheduled"
        assert payload["postizPostStatus"] == "QUEUE"
        assert payload["releaseUrls"] == [
            "https://example.com/post/1",
            "https://example.com/post/2",
        ]

    def test_prepare_launch_auto_configures_workspace_and_sets_cookies(
        self, api_client, db_session, seed_data, monkeypatch
    ) -> None:
        client_uuid = str(seed_data["client"].id)

        from app.config import settings
        from app.services.integration_secrets import decrypt_secret_json

        monkeypatch.setattr(settings, "POSTIZ_DEFAULT_BASE_URL", "http://localhost:4007/api")
        monkeypatch.setattr(settings, "POSTIZ_BROWSER_LOGIN_SECRET", "test-postiz-browser-secret")

        class FakeBrowserClient:
            def create_session(self, **_kwargs):
                return PostizBrowserSession(
                    auth_token="postiz-auth-token",
                    orgs=[PostizBrowserOrg(id="org-1", name="Org One", api_key="org-api-key")],
                    current_org_id="org-1",
                    current_public_api="org-api-key",
                )

        class FakePostizPublicClient:
            def validate_connection(self):
                return True, None

        monkeypatch.setattr("app.routers.postiz.create_postiz_browser_client", lambda **_kwargs: FakeBrowserClient())
        monkeypatch.setattr("app.routers.postiz.create_postiz_client", lambda **_kwargs: FakePostizPublicClient())

        response = api_client.post(
            f"/clients/{client_uuid}/postiz/launch",
            json={"email": "owner@example.com"},
            headers={"host": "localhost:8008"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "launchUrl": "http://localhost:4007/launches",
            "autoConfiguredCredentials": True,
        }
        assert response.cookies.get("auth") == "postiz-auth-token"
        assert response.cookies.get("showorg") == "org-1"

        stored = PostizCredentialsRepository(db_session).get(org_id=TEST_ORG_ID, client_id=client_uuid)
        assert stored is not None
        assert stored.base_url == "http://localhost:4007/api"
        assert decrypt_secret_json(stored.credentials_encrypted)["apiKey"] == "org-api-key"
        assert stored.last_validated_at is not None
        assert stored.last_validation_error is None

    def test_prepare_launch_rejects_when_no_email_source_is_available(
        self, api_client, seed_data, monkeypatch
    ) -> None:
        client_uuid = str(seed_data["client"].id)

        from app.config import settings

        monkeypatch.setattr(settings, "POSTIZ_DEFAULT_BASE_URL", "http://localhost:4007/api")
        monkeypatch.setattr(settings, "POSTIZ_BROWSER_LOGIN_SECRET", "test-postiz-browser-secret")

        response = api_client.post(
            f"/clients/{client_uuid}/postiz/launch",
            headers={"host": "localhost:8008"},
        )

        assert response.status_code == 409
        assert "does not expose an email address" in response.json()["detail"]

    def test_prepare_launch_rejects_org_mismatch_for_configured_workspace(
        self, api_client, db_session, seed_data, monkeypatch
    ) -> None:
        client_uuid = str(seed_data["client"].id)
        _seed_mos_user(db_session)
        _seed_postiz_credentials(db_session, client_uuid)

        from app.config import settings

        monkeypatch.setattr(settings, "POSTIZ_BROWSER_LOGIN_SECRET", "test-postiz-browser-secret")

        class FakeBrowserClient:
            def create_session(self, **_kwargs):
                return PostizBrowserSession(
                    auth_token="postiz-auth-token",
                    orgs=[PostizBrowserOrg(id="org-2", name="Other Org", api_key="different-api-key")],
                    current_org_id="org-2",
                    current_public_api="different-api-key",
                )

        monkeypatch.setattr("app.routers.postiz.create_postiz_browser_client", lambda **_kwargs: FakeBrowserClient())

        response = api_client.post(
            f"/clients/{client_uuid}/postiz/launch",
            headers={"host": "localhost:8008"},
        )

        assert response.status_code == 409
        assert "not a member" in response.json()["detail"]
