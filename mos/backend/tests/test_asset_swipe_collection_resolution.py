from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.temporal.activities import asset_activities
from app.temporal.activities import swipe_image_ad_activities


def test_resolve_default_swipe_collection_activity_returns_ready_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeSwipeCollectionsRepository:
        def __init__(self, session) -> None:
            self.session = session

        def ensure_default_collection(self, *, org_id: str):
            assert org_id == "org-1"
            return SimpleNamespace(id="collection-1", name="Default")

        def ready_asset_ids(self, *, org_id: str, collection_id: str, ad_unit_formats=None) -> list[str]:
            assert org_id == "org-1"
            assert collection_id == "collection-1"
            assert ad_unit_formats == ["image"]
            return ["swipe-1", "swipe-2"]

    monkeypatch.setattr(asset_activities, "session_scope", _fake_session_scope)
    monkeypatch.setattr(
        asset_activities,
        "SwipeCollectionsRepository",
        _FakeSwipeCollectionsRepository,
    )

    result = asset_activities.resolve_default_swipe_collection_activity({"org_id": "org-1"})

    assert result == {
        "swipe_collection_id": "collection-1",
        "swipe_collection_name": "Default",
        "swipe_asset_ids": ["swipe-1", "swipe-2"],
    }


def test_resolve_default_swipe_collection_activity_requires_ready_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeSwipeCollectionsRepository:
        def __init__(self, session) -> None:
            self.session = session

        def ensure_default_collection(self, *, org_id: str):
            assert org_id == "org-1"
            return SimpleNamespace(id="collection-1", name="Default")

        def ready_asset_ids(self, *, org_id: str, collection_id: str, ad_unit_formats=None) -> list[str]:
            assert org_id == "org-1"
            assert collection_id == "collection-1"
            assert ad_unit_formats == ["image"]
            return []

    monkeypatch.setattr(asset_activities, "session_scope", _fake_session_scope)
    monkeypatch.setattr(
        asset_activities,
        "SwipeCollectionsRepository",
        _FakeSwipeCollectionsRepository,
    )

    with pytest.raises(
        ValueError,
        match="Default swipe collection has no ready static image swipe assets for creative generation.",
    ):
        asset_activities.resolve_default_swipe_collection_activity({"org_id": "org-1"})


def test_resolve_collection_swipe_sources_accepts_legacy_static_image_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeCompanySwipesRepository:
        def __init__(self, session) -> None:
            self.session = session

        def get_asset(self, *, org_id: str, swipe_id: str):
            assert org_id == "org-1"
            assert swipe_id == "swipe-1"
            return SimpleNamespace(
                id="swipe-1",
                title="Legacy static swipe",
                ad_unit_format=None,
                product_image_policy=None,
            )

        def list_media(self, *, org_id: str, swipe_asset_id: str):
            assert org_id == "org-1"
            assert swipe_asset_id == "swipe-1"
            return [
                SimpleNamespace(
                    type="IMAGE",
                    url="https://example.com/static-1.jpg",
                    download_url=None,
                    thumbnail_url=None,
                    path=None,
                    mime_type="image/jpeg",
                    video_length=None,
                )
            ]

    monkeypatch.setattr(asset_activities, "CompanySwipesRepository", _FakeCompanySwipesRepository)
    monkeypatch.setattr(
        swipe_image_ad_activities,
        "_resolve_swipe_requires_product_image_policy",
        lambda **_kwargs: (False, "test", "static-1.jpg"),
    )

    result = asset_activities._resolve_collection_swipe_sources(
        session=object(),
        org_id="org-1",
        swipe_asset_ids=["swipe-1"],
    )

    assert result == [
        asset_activities._DefaultSwipeSource(
            company_swipe_id="swipe-1",
            source_label="Legacy static swipe",
            source_media_url="https://example.com/static-1.jpg",
            product_image_policy=False,
        )
    ]


def test_resolve_collection_swipe_sources_rejects_legacy_video_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeCompanySwipesRepository:
        def __init__(self, session) -> None:
            self.session = session

        def get_asset(self, *, org_id: str, swipe_id: str):
            assert org_id == "org-1"
            assert swipe_id == "swipe-1"
            return SimpleNamespace(
                id="swipe-1",
                title="Legacy video swipe",
                ad_unit_format=None,
                product_image_policy=None,
            )

        def list_media(self, *, org_id: str, swipe_asset_id: str):
            assert org_id == "org-1"
            assert swipe_asset_id == "swipe-1"
            return [
                SimpleNamespace(
                    type="VIDEO",
                    url="https://example.com/video.mp4",
                    download_url=None,
                    thumbnail_url=None,
                    path=None,
                    mime_type="video/mp4",
                    video_length=12,
                )
            ]

    monkeypatch.setattr(asset_activities, "CompanySwipesRepository", _FakeCompanySwipesRepository)

    with pytest.raises(
        ValueError,
        match="Selected swipe collection contains non-static assets",
    ):
        asset_activities._resolve_collection_swipe_sources(
            session=object(),
            org_id="org-1",
            swipe_asset_ids=["swipe-1"],
        )
