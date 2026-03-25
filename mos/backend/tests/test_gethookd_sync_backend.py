"""Tests for GetHookd sync backend features."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import (
    GETHOOKD_ORIGIN_SYSTEM,
    Campaign,
    Client,
    CompanySwipeAsset,
    SwipeCollection,
)
from app.db.repositories.swipes import (
    GETHOOKD_REVIEW_STATUS_APPROVED,
    GETHOOKD_REVIEW_STATUS_PENDING,
    GETHOOKD_REVIEW_STATUS_REJECTED,
)
from tests.conftest import TEST_ORG_ID


def _seed_gethookd_swipe(
    db_session,
    *,
    title: str,
    review_status: str | None = None,
) -> CompanySwipeAsset:
    """Seed a GetHookd swipe asset."""
    swipe = CompanySwipeAsset(
        org_id=TEST_ORG_ID,
        title=title,
        source_kind="catalog",
        origin_system=GETHOOKD_ORIGIN_SYSTEM,
        review_status=review_status,
    )
    db_session.add(swipe)
    db_session.commit()
    db_session.refresh(swipe)
    return swipe


def _seed_catalog_swipe(db_session, *, title: str) -> CompanySwipeAsset:
    """Seed a catalog (non-GetHookd) swipe asset."""
    swipe = CompanySwipeAsset(
        org_id=TEST_ORG_ID,
        title=title,
        source_kind="catalog",
        origin_system="internal_seed_set",
    )
    db_session.add(swipe)
    db_session.commit()
    db_session.refresh(swipe)
    return swipe


def test_gethookd_inbox_list(api_client, db_session) -> None:
    """Test GetHookd inbox listing."""
    # Seed GetHookd swipes
    gethookd_swipe1 = _seed_gethookd_swipe(db_session, title="GetHookd Swipe 1")
    gethookd_swipe2 = _seed_gethookd_swipe(
        db_session, title="GetHookd Swipe 2", review_status=GETHOOKD_REVIEW_STATUS_PENDING
    )
    _seed_gethookd_swipe(
        db_session, title="GetHookd Swipe 3", review_status=GETHOOKD_REVIEW_STATUS_APPROVED
    )
    # Seed catalog swipe (should not appear in GetHookd inbox)
    _seed_catalog_swipe(db_session, title="Catalog Swipe")

    # List all GetHookd inbox
    response = api_client.get("/swipes/gethookd/inbox")
    assert response.status_code == 200, response.text
    inbox = response.json()
    assert len(inbox) == 3

    # List only pending
    response = api_client.get("/swipes/gethookd/inbox?review_status=pending")
    assert response.status_code == 200, response.text
    inbox = response.json()
    assert len(inbox) == 1
    assert inbox[0]["title"] == "GetHookd Swipe 2"


def test_swipe_review_approve(api_client, db_session) -> None:
    """Test approving a swipe asset."""
    swipe = _seed_gethookd_swipe(db_session, title="To Approve")

    response = api_client.post(f"/swipes/gethookd/{swipe.id}/approve")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["review_status"] == GETHOOKD_REVIEW_STATUS_APPROVED


def test_swipe_review_reject(api_client, db_session) -> None:
    """Test rejecting a swipe asset."""
    swipe = _seed_gethookd_swipe(db_session, title="To Reject")

    response = api_client.post(f"/swipes/gethookd/{swipe.id}/reject")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["review_status"] == GETHOOKD_REVIEW_STATUS_REJECTED


def test_swipe_review_mark_pending(api_client, db_session) -> None:
    """Test marking a swipe as pending."""
    swipe = _seed_gethookd_swipe(
        db_session, title="To Mark Pending", review_status=GETHOOKD_REVIEW_STATUS_APPROVED
    )

    response = api_client.post(f"/swipes/gethookd/{swipe.id}/mark-pending")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["review_status"] == GETHOOKD_REVIEW_STATUS_PENDING


def test_default_collection_excludes_gethookd(api_client, db_session) -> None:
    """Test that default collection excludes GetHookd assets."""
    # Seed a GetHookd swipe
    _seed_gethookd_swipe(db_session, title="GetHookd Swipe")
    # Seed a catalog swipe
    catalog_swipe = _seed_catalog_swipe(db_session, title="Catalog Swipe")

    # Get default collection
    response = api_client.get("/swipes/collections")
    assert response.status_code == 200, response.text
    collections = response.json()
    default_collection = next(item for item in collections if item["kind"] == "default")

    # Should only contain the catalog swipe, not the GetHookd one
    assert default_collection["item_count"] == 1

    detail_response = api_client.get(f"/swipes/collections/{default_collection['id']}")
    assert detail_response.status_code == 200, response.text
    detail = detail_response.json()
    swipe_ids = [item["id"] for item in detail["swipes"]]
    assert str(catalog_swipe.id) in swipe_ids


def test_campaign_swipe_default_get(api_client, db_session, seed_data) -> None:
    """Test getting campaign swipe default."""
    campaign = seed_data["campaign"]

    # Get swipe default - should return null (no explicit default)
    response = api_client.get(f"/campaigns/{campaign.id}/swipe-default")
    assert response.status_code in (200, 409), response.text  # 409 if no client swipes exist

    # Now set a default collection
    collection = SwipeCollection(
        org_id=TEST_ORG_ID,
        name="Test Collection",
        kind="curated",
    )
    db_session.add(collection)
    db_session.commit()
    db_session.refresh(collection)

    campaign.default_swipe_collection_id = collection.id
    db_session.commit()

    # Get swipe default - should return the collection
    response = api_client.get(f"/campaigns/{campaign.id}/swipe-default")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["swipeCollectionId"] == str(collection.id)
    assert result["swipeCollectionName"] == "Test Collection"


def test_campaign_swipe_default_put(api_client, db_session, seed_data) -> None:
    """Test updating campaign swipe default."""
    campaign = seed_data["campaign"]

    collection = SwipeCollection(
        org_id=TEST_ORG_ID,
        name="New Collection",
        kind="curated",
    )
    db_session.add(collection)
    db_session.commit()
    db_session.refresh(collection)

    # Set swipe default
    response = api_client.put(
        f"/campaigns/{campaign.id}/swipe-default",
        json={"swipeCollectionId": str(collection.id)},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["swipeCollectionId"] == str(collection.id)

    # Clear swipe default
    response = api_client.put(
        f"/campaigns/{campaign.id}/swipe-default",
        json={"swipeCollectionId": None},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["swipeCollectionId"] is None
