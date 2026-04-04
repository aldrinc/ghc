from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.temporal.activities import asset_activities


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

        def ready_asset_ids(self, *, org_id: str, collection_id: str) -> list[str]:
            assert org_id == "org-1"
            assert collection_id == "collection-1"
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

        def ready_asset_ids(self, *, org_id: str, collection_id: str) -> list[str]:
            assert org_id == "org-1"
            assert collection_id == "collection-1"
            return []

    monkeypatch.setattr(asset_activities, "session_scope", _fake_session_scope)
    monkeypatch.setattr(
        asset_activities,
        "SwipeCollectionsRepository",
        _FakeSwipeCollectionsRepository,
    )

    with pytest.raises(
        ValueError,
        match="Default swipe collection has no ready swipe assets for creative generation.",
    ):
        asset_activities.resolve_default_swipe_collection_activity({"org_id": "org-1"})
