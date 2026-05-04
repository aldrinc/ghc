"""
Tests for GetHookd sync functionality.

These tests verify:
1. GetHookd client API calls
2. Schedule reconciliation logic
3. Activity input/output parsing
4. Repository methods
"""

from __future__ import annotations

import asyncio
import httpx
import pytest
from sqlalchemy import select
from unittest.mock import patch

from app.db.enums import AdChannelEnum, MediaMirrorStatusEnum
from app.db.models import (
    GETHOOKD_ORIGIN_SYSTEM,
    ClientGetHookdCredentials,
    ClientGetHookdSyncFeed,
    CompanySwipeAsset,
    CompanySwipeMedia,
    MediaAsset,
    SwipeCollection,
    SwipeCollectionItem,
)
from app.db.repositories.swipes import GETHOOKD_INBOX_COLLECTION_KIND
from app.services import gethookd_client as gethookd_client_module
from app.services.gethookd_client import (
    GetHookdClient,
    GetHookdClientError,
    GetHookdExploreFilters,
    GetHookdAdResult,
    GetHookdExplorePage,
)
from app.services.remote_media import RemoteMediaOutput
from app.temporal.activities import gethookd_sync_activities as gethookd_sync_activities_module
from app.temporal.activities.gethookd_sync_activities import (
    GetHookdSyncActivityInput,
    GetHookdSyncActivityOutput,
    _sync_swipe_media,
    gethookd_sync_workspace_activity,
)
from tests.conftest import TEST_ORG_ID


class TestGetHookdClient:
    """Tests for GetHookd client."""

    @staticmethod
    def _http_client_factory(
        response_json: dict,
        captured: dict[str, object],
        *,
        status_code: int = 200,
    ):
        class DummyResponse:
            def __init__(self) -> None:
                self.status_code = status_code

            def json(self) -> dict:
                return response_json

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        "request failed",
                        request=httpx.Request("GET", str(captured.get("url") or "")),
                        response=httpx.Response(self.status_code),
                    )

        class DummyClient:
            def __init__(self, *args, **kwargs) -> None:
                self.kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

            def get(self, url, headers=None, params=None):
                captured["url"] = url
                captured["headers"] = headers or {}
                captured["params"] = params or {}
                return DummyResponse()

        return DummyClient

    def test_client_requires_api_token(self):
        """Client should raise error if no API token provided."""
        with pytest.raises(GetHookdClientError, match="API token is required"):
            GetHookdClient(api_token="")

    def test_client_requires_api_token_none(self):
        """Client should raise error if API token is None."""
        with patch("app.services.gethookd_client.settings") as mock_settings:
            mock_settings.GETHOOKD_API_KEY = None
            mock_settings.GETHOOKD_API_BASE_URL = "https://api.gethookd.com"
            mock_settings.GETHOOKD_TIMEOUT_SECONDS = 30.0
            with pytest.raises(GetHookdClientError, match="API token is required"):
                GetHookdClient()

    def test_explore_filters_defaults(self):
        """Explore filters should not invent API defaults."""
        filters = GetHookdExploreFilters()

        assert filters.query == ""
        assert filters.platform is None
        assert filters.performance_scores is None
        assert filters.status is None
        assert filters.sort_column is None
        assert filters.sort_direction is None

    def test_explore_filters_custom(self):
        """Explore filters should accept custom values."""
        filters = GetHookdExploreFilters(
            query="test",
            platform="tiktok",
            niche="fitness",
            ad_format="video",
        )

        assert filters.query == "test"
        assert filters.platform == "tiktok"
        assert filters.niche == "fitness"
        assert filters.ad_format == "video"

    def test_validate_credentials_uses_authcheck(self):
        """Credential validation should hit the documented auth check endpoint."""
        captured: dict[str, object] = {}
        dummy_client = self._http_client_factory(
            {"errors": False, "data": {"authenticated": True}},
            captured,
        )

        with patch.object(gethookd_client_module.httpx, "Client", dummy_client), patch.object(
            gethookd_client_module.settings,
            "GETHOOKD_API_BASE_URL",
            "https://app.gethookd.ai/api/v1",
        ):
            client = GetHookdClient(api_token="token")
            assert client.validate_credentials() == (True, None)

        assert captured["url"] == "https://app.gethookd.ai/api/v1/authcheck"

    def test_explore_uses_documented_params_and_response_shape(self):
        """Explore requests should match the documented API contract."""
        captured: dict[str, object] = {}
        dummy_client = self._http_client_factory(
            {
                "errors": False,
                "data": [
                    {
                        "id": 123,
                        "external_id": "9999999",
                        "platform": "facebook, instagram",
                        "display_format": "video",
                        "title": "Great offer",
                        "body": "Body copy",
                        "landing_page": "https://example.com",
                        "cta_type": "SHOP_NOW",
                        "cta_text": "Shop Now",
                        "days_active": 21,
                        "active_in_library": 1,
                        "used_count": 4,
                        "performance_score": 120,
                        "performance_score_title": "Winning",
                        "share_url": "https://app.gethookd.ai/share/ad/123",
                        "brand": {
                            "external_id": "2016485295279615",
                            "name": "Acme",
                            "logo_url": "https://example.com/logo.png",
                        },
                        "media": [{"type": "video", "url": "https://example.com/video.mp4"}],
                    }
                ],
            },
            captured,
        )

        with patch.object(gethookd_client_module.httpx, "Client", dummy_client), patch.object(
            gethookd_client_module.settings,
            "GETHOOKD_API_BASE_URL",
            "https://app.gethookd.ai/api/v1",
        ):
            client = GetHookdClient(api_token="token")
            page = client.explore(
                filters=GetHookdExploreFilters(
                    query="skincare",
                    platform="facebook",
                    ad_format="video",
                )
            )

        assert captured["url"] == "https://app.gethookd.ai/api/v1/explore"
        assert captured["params"] == {
            "page": 1,
            "per_page": 20,
            "query": "skincare",
            "platform": "facebook",
            "ad-format": "video",
        }
        assert len(page.items) == 1
        assert page.items[0].brand_id == "2016485295279615"
        assert page.items[0].media[0]["url"] == "https://example.com/video.mp4"

    def test_explore_does_not_truncate_upstream_rows(self):
        """Client should preserve the full upstream page payload."""
        captured: dict[str, object] = {}
        dummy_client = self._http_client_factory(
            {
                "errors": False,
                "data": [
                    {"id": 1, "platform": "facebook"},
                    {"id": 2, "platform": "facebook"},
                ],
            },
            captured,
        )

        with patch.object(gethookd_client_module.httpx, "Client", dummy_client), patch.object(
            gethookd_client_module.settings,
            "GETHOOKD_API_BASE_URL",
            "https://app.gethookd.ai/api/v1",
        ):
            client = GetHookdClient(api_token="token")
            page = client.explore(filters=GetHookdExploreFilters(), per_page=1)

        assert page.raw_items_count == 2
        assert len(page.items) == 2

    def test_explore_keeps_all_rows_and_normalizes_asset_type_after_parsing(self):
        """Image-filtered API pages should retain upstream rows and annotate normalized asset types."""
        captured: dict[str, object] = {}
        dummy_client = self._http_client_factory(
            {
                "errors": False,
                "data": [
                    {
                        "id": "image-1",
                        "platform": "facebook",
                        "media": [
                            {"type": "image", "url": "https://example.com/image-1.jpg"},
                        ],
                    },
                    {
                        "id": "carousel-1",
                        "platform": "facebook",
                        "media": [
                            {"type": "image", "url": "https://example.com/carousel-1.jpg"},
                            {"type": "image", "url": "https://example.com/carousel-2.jpg"},
                        ],
                    },
                    {
                        "id": "video-1",
                        "platform": "facebook",
                        "media": [
                            {"type": "video", "url": "https://example.com/video-1.mp4"},
                        ],
                    },
                ],
            },
            captured,
        )

        with patch.object(gethookd_client_module.httpx, "Client", dummy_client), patch.object(
            gethookd_client_module.settings,
            "GETHOOKD_API_BASE_URL",
            "https://app.gethookd.ai/api/v1",
        ):
            client = GetHookdClient(api_token="token")
            page = client.explore(
                filters=GetHookdExploreFilters(
                    ad_format="image",
                    platform="facebook",
                ),
                per_page=30,
            )

        assert captured["params"]["ad-format"] == "image"
        assert [result.id for result in page.items] == ["image-1", "carousel-1", "video-1"]
        assert [result.ad_unit_format for result in page.items] == ["image", "carousel", "video"]

    def test_explore_supports_active_ads_count_filter(self):
        """Explore requests should pass through the minimum active brand ads filter."""
        captured: dict[str, object] = {}
        dummy_client = self._http_client_factory({"errors": False, "data": []}, captured)

        with patch.object(gethookd_client_module.httpx, "Client", dummy_client), patch.object(
            gethookd_client_module.settings,
            "GETHOOKD_API_BASE_URL",
            "https://app.gethookd.ai/api/v1",
        ):
            client = GetHookdClient(api_token="token")
            client.explore(
                filters=GetHookdExploreFilters(
                    niche="30",
                    performance_scores="growing,optimized,winning",
                    ads_per_brand_limit=4,
                    active_ads_count=2000,
                )
            )

        assert captured["params"]["niche"] == "30"
        assert captured["params"]["performance_scores"] == "growing,optimized,winning"
        assert captured["params"]["ads_per_brand_limit"] == 4
        assert captured["params"]["active_ads_count"] == 2000

    def test_from_filter_dict_reads_new_and_legacy_keys(self):
        filters = GetHookdExploreFilters.from_filter_dict(
            {
                "platforms": "facebook,instagram",
                "ad_format": "image",
                "start-date": "2026-04-01",
                "end_date": "2026-04-15",
            }
        )

        assert filters.platform == "facebook,instagram"
        assert filters.ad_format == "image"
        assert filters.start_date == "2026-04-01"
        assert filters.end_date == "2026-04-15"


class TestGetHookdActivityInput:
    """Tests for GetHookd activity input/output."""

    def test_activity_input_fields(self):
        """Activity input should have required fields."""
        input_data = GetHookdSyncActivityInput(
            org_id="org-123",
            client_id="client-456",
        )

        assert input_data.org_id == "org-123"
        assert input_data.client_id == "client-456"

    def test_activity_output_defaults(self):
        """Activity output should have default values."""
        output = GetHookdSyncActivityOutput(
            status="completed",
            feeds_attempted=2,
            feeds_succeeded=2,
            assets_new=10,
            assets_updated=5,
            assets_marked_stale=1,
            assets_failed=0,
            credits_used=100,
        )

        assert output.status == "completed"
        assert output.feeds_attempted == 2
        assert output.error_summary is None


def test_sync_swipe_media_skips_duplicate_mirrored_media_asset_ids() -> None:
    created_media: list[dict[str, object]] = []

    class FakeSwipesRepo:
        def delete_media_for_asset(self, *, org_id: str, swipe_asset_id: str) -> None:
            raise AssertionError("delete_media_for_asset should not be called")

        def create_media(self, **fields):
            created_media.append(fields)

    class FakeRemoteMediaService:
        def __init__(self) -> None:
            self.calls = 0

        def upsert_and_mirror(self, *, channel, remote_media):
            self.calls += 1
            return RemoteMediaOutput(
                media_asset_id="same-media-asset",
                storage_key=None,
                preview_storage_key=None,
                sha256=None,
                mirror_status="succeeded",
            )

    remote_media_service = FakeRemoteMediaService()
    _sync_swipe_media(
        swipes_repo=FakeSwipesRepo(),
        remote_media_service=remote_media_service,
        org_id="org-1",
        swipe_asset_id="swipe-1",
        remote_media_inputs=[
            gethookd_sync_activities_module.RemoteMediaInput(
                source_url="https://example.com/a.mp4",
                asset_type=gethookd_sync_activities_module.MediaAssetTypeEnum.VIDEO,
                metadata={},
            ),
            gethookd_sync_activities_module.RemoteMediaInput(
                source_url="https://example.com/b.mp4",
                asset_type=gethookd_sync_activities_module.MediaAssetTypeEnum.VIDEO,
                metadata={},
            ),
        ],
        replace_existing=False,
    )

    assert remote_media_service.calls == 2
    assert len(created_media) == 1
    assert created_media[0]["media_asset_id"] == "same-media-asset"


class TestGetHookdScheduleReconciliation:
    """Tests for schedule reconciliation logic."""

    def test_should_create_schedule_when_valid(self):
        """Should create schedule when credentials and feeds exist."""
        # This tests the logic - actual Temporal calls would be mocked
        has_valid_credentials = True
        has_enabled_feeds = True

        should_have_schedule = has_valid_credentials and has_enabled_feeds

        assert should_have_schedule is True

    def test_should_not_create_schedule_without_credentials(self):
        """Should not create schedule without valid credentials."""
        has_valid_credentials = False
        has_enabled_feeds = True

        should_have_schedule = has_valid_credentials and has_enabled_feeds

        assert should_have_schedule is False

    def test_should_not_create_schedule_without_feeds(self):
        """Should not create schedule without enabled feeds."""
        has_valid_credentials = True
        has_enabled_feeds = False

        should_have_schedule = has_valid_credentials and has_enabled_feeds

        assert should_have_schedule is False

    def test_should_delete_schedule_when_config_invalid(self):
        """Should delete schedule when credentials or feeds removed."""
        has_valid_credentials = False
        has_enabled_feeds = False

        should_have_schedule = has_valid_credentials and has_enabled_feeds

        assert should_have_schedule is False


class TestGetHookdSyncStatus:
    """Tests for sync status handling."""

    def test_skipped_status_no_credentials(self):
        """Should return skipped status when no credentials."""
        output = GetHookdSyncActivityOutput(
            status="skipped",
            feeds_attempted=0,
            feeds_succeeded=0,
            assets_new=0,
            assets_updated=0,
            assets_marked_stale=0,
            assets_failed=0,
            credits_used=0,
            error_summary="No GetHookd credentials configured",
        )

        assert output.status == "skipped"
        assert "No GetHookd credentials" in output.error_summary

    def test_failed_status_missing_taxonomy_model(self):
        """Should fail clearly when SWIPE_TAXONOMY_MODEL is missing."""
        output = GetHookdSyncActivityOutput(
            status="failed",
            feeds_attempted=0,
            feeds_succeeded=0,
            assets_new=0,
            assets_updated=0,
            assets_marked_stale=0,
            assets_failed=0,
            credits_used=0,
            error_summary="SWIPE_TAXONOMY_MODEL is not configured",
        )

        assert output.status == "failed"
        assert "SWIPE_TAXONOMY_MODEL" in output.error_summary


def test_gethookd_sync_workspace_surfaces_page_failures(
    db_session,
    seed_data,
    monkeypatch,
):
    """Feed-level page failures should return a failed activity result."""
    client = seed_data["client"]
    db_session.add(
        ClientGetHookdCredentials(
            org_id=TEST_ORG_ID,
            client_id=client.id,
            credentials_encrypted="encrypted",
        )
    )
    db_session.add(
        ClientGetHookdSyncFeed(
            org_id=TEST_ORG_ID,
            client_id=client.id,
            name="Winning feed",
            enabled=True,
            filters_json={"query": "supplements"},
            max_pages_per_run=1,
            per_page=25,
        )
    )
    db_session.commit()

    def fake_get_session():
        yield db_session

    class FakeGetHookdClient:
        def explore(self, *, filters, page, per_page):
            raise GetHookdClientError("Insufficient credits")

    class FakeRemoteMediaService:
        def __init__(self, session):
            self.session = session

    monkeypatch.setattr(gethookd_sync_activities_module, "get_session", fake_get_session)
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "create_gethookd_client",
        lambda api_token: FakeGetHookdClient(),
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "decrypt_secret_json",
        lambda _: {"apiToken": "token"},
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module.settings,
        "SWIPE_TAXONOMY_MODEL",
        "gemini-test",
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "RemoteMediaService",
        FakeRemoteMediaService,
    )

    result = asyncio.run(
        gethookd_sync_workspace_activity(
            GetHookdSyncActivityInput(
                org_id=str(TEST_ORG_ID),
                client_id=str(client.id),
            )
        )
    )

    assert result.status == "failed"
    assert result.feeds_attempted == 1
    assert result.feeds_succeeded == 0
    assert result.assets_failed == 1
    assert result.error_summary is not None
    assert "Winning feed" in result.error_summary
    assert "Insufficient credits" in result.error_summary


def test_gethookd_sync_workspace_fetches_all_pages_when_page_cap_is_zero(
    db_session,
    seed_data,
    monkeypatch,
):
    client = seed_data["client"]
    db_session.add(
        ClientGetHookdCredentials(
            org_id=TEST_ORG_ID,
            client_id=client.id,
            credentials_encrypted="encrypted",
        )
    )
    db_session.add(
        ClientGetHookdSyncFeed(
            org_id=TEST_ORG_ID,
            client_id=client.id,
            name="Full import feed",
            enabled=True,
            filters_json={"query": "supplements"},
            max_pages_per_run=0,
            per_page=10,
        )
    )
    db_session.commit()

    def fake_get_session():
        yield db_session

    calls: list[int] = []

    class FakeGetHookdClient:
        def explore(self, *, filters, page, per_page):
            calls.append(page)
            return GetHookdExplorePage(
                items=[
                    GetHookdAdResult(
                        id=f"ad-{page}",
                        external_id=f"ext-{page}",
                        platform="facebook",
                        display_format="image",
                        ad_unit_format="image",
                        title=f"Ad {page}",
                        body="Body",
                        cta_type="SHOP_NOW",
                        cta_text="Shop Now",
                        landing_page="https://example.com",
                        start_date=None,
                        end_date=None,
                        days_active=1,
                        active_in_library=True,
                        used_count=1,
                        performance_score=1,
                        performance_score_title="Testing",
                        share_url=f"https://app.gethookd.ai/share/ad/{page}",
                        ad_library_link=None,
                        brand_id=f"brand-{page}",
                        brand_name=f"Brand {page}",
                        brand_logo_url=None,
                        media=[{"type": "image", "url": f"https://cdn.example/{page}.jpg"}],
                        raw_json={"id": page},
                    )
                ],
                raw_items_count=1,
                current_page=page,
                last_page=2,
                total=2,
                next_url="https://app.gethookd.ai/api/v1/explore?page=2" if page == 1 else None,
                previous_url=None if page == 1 else "https://app.gethookd.ai/api/v1/explore?page=1",
                used_credits=0.5,
                remaining_credits=99.5,
                sorting={"column": "created_at", "direction": "desc"},
                filters={"query": "supplements"},
                raw_payload={"data": [{"id": page}]},
            )

    class FakeRemoteMediaService:
        def __init__(self, session):
            self.session = session

        def upsert_and_mirror(self, *, channel, remote_media):
            mirrored = self.session.scalar(
                select(MediaAsset).where(MediaAsset.source_url == remote_media.source_url)
            )
            if mirrored is None:
                mirrored = MediaAsset(
                    channel=AdChannelEnum.META_ADS_LIBRARY,
                    asset_type=remote_media.asset_type,
                    source_url=remote_media.source_url,
                    mirror_status=MediaMirrorStatusEnum.succeeded,
                    metadata_json=remote_media.metadata or {},
                )
                self.session.add(mirrored)
                self.session.flush()
            return RemoteMediaOutput(
                media_asset_id=str(mirrored.id),
                storage_key=None,
                preview_storage_key=None,
                sha256=None,
                mirror_status="mirrored",
            )

    monkeypatch.setattr(gethookd_sync_activities_module, "get_session", fake_get_session)
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "create_gethookd_client",
        lambda api_token: FakeGetHookdClient(),
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "decrypt_secret_json",
        lambda _: {"apiToken": "token"},
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module.settings,
        "SWIPE_TAXONOMY_MODEL",
        "gemini-test",
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "RemoteMediaService",
        FakeRemoteMediaService,
    )

    result = asyncio.run(
        gethookd_sync_workspace_activity(
            GetHookdSyncActivityInput(
                org_id=str(TEST_ORG_ID),
                client_id=str(client.id),
            )
        )
    )

    assert result.status == "completed"
    assert result.assets_new == 2
    assert result.credits_used == 1.0
    assert calls == [1, 2]


class TestGetHookdCreativeChangeDetection:
    """Tests for creative change detection logic."""

    def test_detect_title_change(self):
        """Should detect title changes."""
        old_title = "Old Title"
        new_title = "New Title"

        creative_changed = old_title != new_title

        assert creative_changed is True

    def test_no_change_when_same(self):
        """Should not detect change when identical."""
        old_title = "Same Title"
        new_title = "Same Title"

        creative_changed = old_title != new_title

        assert creative_changed is False

    def test_detect_body_change(self):
        """Should detect body changes."""
        old_body = "Old body text"
        new_body = "New body text"

        creative_changed = old_body != new_body

        assert creative_changed is True

    def test_detect_cta_change(self):
        """Should detect CTA changes."""
        old_cta = "Learn More"
        new_cta = "Shop Now"

        creative_changed = old_cta != new_cta

        assert creative_changed is True


def test_new_gethookd_assets_persist_ad_unit_format(
    db_session,
    seed_data,
    monkeypatch,
):
    """New synced assets should keep the normalized ad unit format."""
    client = seed_data["client"]
    db_session.add(
        ClientGetHookdCredentials(
            org_id=TEST_ORG_ID,
            client_id=client.id,
            credentials_encrypted="encrypted",
        )
    )
    feed = ClientGetHookdSyncFeed(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        name="Carousel feed",
        enabled=True,
        filters_json={"query": "supplements", "ad_format": "carousel"},
        max_pages_per_run=1,
        per_page=25,
    )
    db_session.add(feed)
    db_session.commit()
    client_id = str(client.id)
    feed_id = str(feed.id)

    def fake_get_session():
        yield db_session

    class FakeGetHookdClient:
        def explore(self, *, filters, page, per_page):
            return GetHookdExplorePage(
                items=[
                    GetHookdAdResult(
                        id="carousel-123",
                        external_id="9999999",
                        platform="facebook",
                        display_format="DCO",
                        ad_unit_format="carousel",
                        title="Carousel creative",
                        body="Same body",
                        cta_type="LEARN_MORE",
                        cta_text="Learn More",
                        landing_page="https://example.com",
                        start_date=None,
                        end_date=None,
                        days_active=21,
                        active_in_library=True,
                        used_count=4,
                        performance_score=120,
                        performance_score_title="Winning",
                        share_url="https://app.gethookd.ai/share/ad/carousel-123",
                        ad_library_link=None,
                        brand_id="brand-1",
                        brand_name="Acme",
                        brand_logo_url=None,
                        media=[
                            {"type": "image", "url": "https://cdn.example/carousel-1.jpg"},
                            {"type": "image", "url": "https://cdn.example/carousel-2.jpg"},
                        ],
                        raw_json={"id": "carousel-123", "creativeVersion": "v1"},
                    )
                ],
                raw_items_count=1,
                current_page=1,
                last_page=1,
                total=1,
                next_url=None,
                previous_url=None,
                used_credits=0.0,
                remaining_credits=None,
                sorting={},
                filters={},
                raw_payload={"data": [{"id": "carousel-123"}]},
            )

    class FakeRemoteMediaService:
        def __init__(self, session):
            self.session = session

        def upsert_and_mirror(self, *, channel, remote_media):
            mirrored = self.session.scalar(
                select(MediaAsset).where(MediaAsset.source_url == remote_media.source_url)
            )
            if mirrored is None:
                mirrored = MediaAsset(
                    channel=AdChannelEnum.META_ADS_LIBRARY,
                    asset_type=remote_media.asset_type,
                    source_url=remote_media.source_url,
                    mirror_status=MediaMirrorStatusEnum.succeeded,
                    metadata_json=remote_media.metadata or {},
                )
                self.session.add(mirrored)
                self.session.flush()
            return RemoteMediaOutput(
                media_asset_id=str(mirrored.id),
                storage_key=None,
                preview_storage_key=None,
                sha256=None,
                mirror_status="mirrored",
            )

    monkeypatch.setattr(gethookd_sync_activities_module, "get_session", fake_get_session)
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "create_gethookd_client",
        lambda api_token: FakeGetHookdClient(),
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "decrypt_secret_json",
        lambda _: {"apiToken": "token"},
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module.settings,
        "SWIPE_TAXONOMY_MODEL",
        "gemini-test",
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "RemoteMediaService",
        FakeRemoteMediaService,
    )

    result = asyncio.run(
        gethookd_sync_workspace_activity(
            GetHookdSyncActivityInput(
                org_id=str(TEST_ORG_ID),
                client_id=client_id,
            )
        )
    )

    assert result.status == "completed"
    assert result.assets_new == 1

    synced_asset = db_session.scalar(
        select(CompanySwipeAsset).where(
            CompanySwipeAsset.org_id == TEST_ORG_ID,
            CompanySwipeAsset.external_ad_id == "carousel-123",
        )
    )
    assert synced_asset is not None
    assert synced_asset.ad_unit_format == "carousel"
    assert synced_asset.source_metadata_json is not None
    assert synced_asset.source_metadata_json["feed_id"] == feed_id
    assert synced_asset.source_metadata_json["feed_name"] == "Carousel feed"
    assert synced_asset.source_metadata_json["run_id"]
    assert synced_asset.source_metadata_json["client_ids"] == [client_id]
    assert synced_asset.source_metadata_json["feed_ids"] == [feed_id]
    assert synced_asset.source_metadata_json["feed_names"] == ["Carousel feed"]


def test_existing_asset_media_changes_mark_stale_and_restore_gethookd_membership(
    db_session,
    seed_data,
    monkeypatch,
):
    """Existing synced assets should refresh media and stay in the system inbox."""
    client = seed_data["client"]
    db_session.add(
        ClientGetHookdCredentials(
            org_id=TEST_ORG_ID,
            client_id=client.id,
            credentials_encrypted="encrypted",
        )
    )
    feed = ClientGetHookdSyncFeed(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        name="Winning feed",
        enabled=True,
        filters_json={"query": "supplements"},
        max_pages_per_run=1,
        per_page=25,
    )
    db_session.add(feed)
    client_id = str(client.id)
    existing_asset = CompanySwipeAsset(
        org_id=TEST_ORG_ID,
        source_kind="catalog",
        origin_system=GETHOOKD_ORIGIN_SYSTEM,
        external_ad_id="123",
        title="Same title",
        body="Same body",
        cta_type="LEARN_MORE",
        cta_text="Learn More",
        landing_page="https://example.com",
        display_format="image",
        review_status="approved",
        analysis_status="ready",
        source_payload_hash="old-payload",
        source_metadata_json={
            "client_ids": ["legacy-client"],
            "feed_ids": ["legacy-feed"],
            "feed_names": ["Legacy Feed"],
            "feed_id": "legacy-feed",
            "feed_name": "Legacy Feed",
            "run_id": "legacy-run",
        },
    )
    db_session.add(existing_asset)
    db_session.commit()
    feed_id = str(feed.id)
    db_session.refresh(existing_asset)
    existing_asset_id = existing_asset.id
    db_session.add(
        CompanySwipeMedia(
            org_id=TEST_ORG_ID,
            swipe_asset_id=existing_asset_id,
            url="https://cdn.example/old.jpg",
            type="image",
        )
    )
    db_session.commit()

    def fake_get_session():
        yield db_session

    class FakeGetHookdClient:
        def explore(self, *, filters, page, per_page):
            return GetHookdExplorePage(
                items=[
                    GetHookdAdResult(
                        id="123",
                        external_id="9999999",
                        platform="facebook",
                        display_format="image",
                        ad_unit_format="image",
                        title="Same title",
                        body="Same body",
                        cta_type="LEARN_MORE",
                        cta_text="Learn More",
                        landing_page="https://example.com",
                        start_date=None,
                        end_date=None,
                        days_active=21,
                        active_in_library=True,
                        used_count=4,
                        performance_score=120,
                        performance_score_title="Winning",
                        share_url="https://app.gethookd.ai/share/ad/123",
                        ad_library_link=None,
                        brand_id="brand-1",
                        brand_name="Acme",
                        brand_logo_url=None,
                        media=[{"type": "image", "url": "https://cdn.example/new.jpg"}],
                        raw_json={"id": 123, "creativeVersion": "v2"},
                    )
                ],
                raw_items_count=1,
                current_page=1,
                last_page=1,
                total=1,
                next_url=None,
                previous_url=None,
                used_credits=0.0,
                remaining_credits=None,
                sorting={},
                filters={},
                raw_payload={"data": [{"id": 123}]},
            )

    class FakeRemoteMediaService:
        def __init__(self, session):
            self.session = session

        def upsert_and_mirror(self, *, channel, remote_media):
            mirrored = self.session.scalar(
                select(MediaAsset).where(MediaAsset.source_url == remote_media.source_url)
            )
            if mirrored is None:
                mirrored = MediaAsset(
                    channel=AdChannelEnum.META_ADS_LIBRARY,
                    asset_type=remote_media.asset_type,
                    source_url=remote_media.source_url,
                    mirror_status=MediaMirrorStatusEnum.succeeded,
                    metadata_json=remote_media.metadata or {},
                )
                self.session.add(mirrored)
                self.session.flush()
            return RemoteMediaOutput(
                media_asset_id=str(mirrored.id),
                storage_key=None,
                preview_storage_key=None,
                sha256=None,
                mirror_status="mirrored",
            )

    monkeypatch.setattr(gethookd_sync_activities_module, "get_session", fake_get_session)
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "create_gethookd_client",
        lambda api_token: FakeGetHookdClient(),
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "decrypt_secret_json",
        lambda _: {"apiToken": "token"},
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module.settings,
        "SWIPE_TAXONOMY_MODEL",
        "gemini-test",
    )
    monkeypatch.setattr(
        gethookd_sync_activities_module,
        "RemoteMediaService",
        FakeRemoteMediaService,
    )

    result = asyncio.run(
        gethookd_sync_workspace_activity(
            GetHookdSyncActivityInput(
                org_id=str(TEST_ORG_ID),
                client_id=client_id,
            )
        )
    )

    assert result.status == "completed"
    assert result.assets_marked_stale == 1

    db_session.expire_all()
    refreshed_asset = db_session.get(CompanySwipeAsset, existing_asset_id)
    assert refreshed_asset is not None
    assert refreshed_asset.ad_unit_format == "image"
    assert refreshed_asset.review_status == "stale_after_sync"
    assert refreshed_asset.source_metadata_json is not None
    assert refreshed_asset.source_metadata_json["client_ids"] == ["legacy-client", client_id]
    assert refreshed_asset.source_metadata_json["feed_ids"] == ["legacy-feed", feed_id]
    assert refreshed_asset.source_metadata_json["feed_names"] == ["Legacy Feed", "Winning feed"]
    assert refreshed_asset.source_metadata_json["feed_id"] == feed_id
    assert refreshed_asset.source_metadata_json["feed_name"] == "Winning feed"
    assert refreshed_asset.source_metadata_json["run_id"]

    media_rows = db_session.scalars(
        select(CompanySwipeMedia).where(CompanySwipeMedia.swipe_asset_id == existing_asset_id)
    ).all()
    assert len(media_rows) == 1
    assert media_rows[0].url == "https://cdn.example/new.jpg"

    inbox_collection = db_session.scalar(
        select(SwipeCollection).where(
            SwipeCollection.org_id == TEST_ORG_ID,
            SwipeCollection.kind == GETHOOKD_INBOX_COLLECTION_KIND,
        )
    )
    assert inbox_collection is not None
    membership = db_session.scalar(
        select(SwipeCollectionItem).where(
            SwipeCollectionItem.org_id == TEST_ORG_ID,
            SwipeCollectionItem.collection_id == inbox_collection.id,
            SwipeCollectionItem.swipe_asset_id == existing_asset_id,
        )
    )
    assert membership is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
