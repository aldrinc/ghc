"""Tests for GetHookd sync backend features."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import (
    GETHOOKD_ORIGIN_SYSTEM,
    Campaign,
    Client,
    CompanySwipeAsset,
    GetHookdSyncRun,
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
    body: str | None = None,
    landing_page: str | None = None,
    ad_unit_format: str | None = "image",
    used_count: int | None = None,
    review_status: str | None = None,
    source_metadata_json: dict | None = None,
) -> CompanySwipeAsset:
    """Seed a GetHookd swipe asset."""
    swipe = CompanySwipeAsset(
        org_id=TEST_ORG_ID,
        title=title,
        body=body,
        landing_page=landing_page,
        source_kind="catalog",
        origin_system=GETHOOKD_ORIGIN_SYSTEM,
        ad_unit_format=ad_unit_format,
        used_count=used_count,
        review_status=review_status,
        source_metadata_json=source_metadata_json,
    )
    db_session.add(swipe)
    db_session.commit()
    db_session.refresh(swipe)
    return swipe


def _seed_gethookd_run(db_session, *, client_id: str, status: str = "completed") -> GetHookdSyncRun:
    run = GetHookdSyncRun(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        status=status,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


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


def test_company_swipes_can_filter_gethookd_assets_by_client(api_client, db_session, seed_data) -> None:
    client = seed_data["client"]
    other_client = Client(org_id=TEST_ORG_ID, name="Other Client", industry="Supplements")
    db_session.add(other_client)
    db_session.commit()
    db_session.refresh(other_client)

    matching = _seed_gethookd_swipe(
        db_session,
        title="Ember-only Swipe",
        source_metadata_json={"client_ids": [str(client.id)]},
    )
    _seed_gethookd_swipe(
        db_session,
        title="Other Workspace Swipe",
        source_metadata_json={"client_ids": [str(other_client.id)]},
    )
    _seed_gethookd_swipe(
        db_session,
        title="Unscoped Legacy Swipe",
        source_metadata_json=None,
    )

    response = api_client.get(f"/swipes/company?source=gethookd&client_id={client.id}")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert [item["id"] for item in payload] == [str(matching.id)]


def test_gethookd_review_inbox_dedupes_exact_static_duplicates(
    api_client, db_session, seed_data
) -> None:
    client = seed_data["client"]
    run = _seed_gethookd_run(db_session, client_id=str(client.id))
    metadata = {
        "client_ids": [str(client.id)],
        "run_id": str(run.id),
    }

    kept = _seed_gethookd_swipe(
        db_session,
        title="Women's Hair Growth Collection, Vitamins & Supplements | Viviscal",
        body="Same copy",
        landing_page="https://www.viviscal.co.uk/collections/for-women",
        used_count=9,
        source_metadata_json=metadata,
    )
    _seed_gethookd_swipe(
        db_session,
        title="Women's Hair Growth Collection, Vitamins & Supplements | Viviscal",
        body="Same copy",
        landing_page="https://www.viviscal.co.uk/collections/for-women",
        used_count=1,
        source_metadata_json=metadata,
    )
    _seed_gethookd_swipe(
        db_session,
        title="Another static",
        body="Different copy",
        landing_page="https://example.com/other",
        used_count=3,
        source_metadata_json=metadata,
    )

    response = api_client.get(f"/swipes/gethookd-inbox?client_id={client.id}&review_limit=10")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["summary"]["rawImportedCount"] == 3
    assert payload["summary"]["eligibleStaticImageCount"] == 3
    assert payload["summary"]["duplicateCollapsedCount"] == 1
    assert payload["summary"]["returnedCount"] == 2
    assert len(payload["swipes"]) == 2
    assert payload["swipes"][0]["id"] == str(kept.id)
    assert payload["swipes"][0]["used_count"] == 9


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
