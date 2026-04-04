from __future__ import annotations

from sqlalchemy import select

from app.db.models import CompanySwipeAsset, SwipeCollectionItem
from app.routers import swipes as swipes_router
from tests.conftest import TEST_ORG_ID


def _seed_company_swipe(
    db_session,
    *,
    title: str,
    source_kind: str = "catalog",
    analysis_status: str = "ready",
) -> CompanySwipeAsset:
    swipe = CompanySwipeAsset(
        org_id=TEST_ORG_ID,
        title=title,
        source_kind=source_kind,
        analysis_status=analysis_status,
    )
    db_session.add(swipe)
    db_session.commit()
    db_session.refresh(swipe)
    return swipe


def test_swipe_collections_list_create_and_clone(api_client, db_session) -> None:
    catalog_swipe = _seed_company_swipe(db_session, title="Catalog Swipe")
    _seed_company_swipe(db_session, title="Uploaded Swipe", source_kind="upload")

    collections_response = api_client.get("/swipes/collections")
    assert collections_response.status_code == 200, collections_response.text
    collections = collections_response.json()

    default_collection = next(item for item in collections if item["kind"] == "default")
    assert default_collection["name"] == "Default"
    assert default_collection["writable"] is False
    assert default_collection["item_count"] == 1
    assert default_collection["analysis_counts"] == {"ready": 1}

    default_detail_response = api_client.get(f"/swipes/collections/{default_collection['id']}")
    assert default_detail_response.status_code == 200, default_detail_response.text
    default_detail = default_detail_response.json()
    assert [item["id"] for item in default_detail["swipes"]] == [str(catalog_swipe.id)]

    create_response = api_client.post(
        "/swipes/collections",
        json={"name": "Uploader Inbox", "kind": "uploaded"},
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["name"] == "Uploader Inbox"
    assert created["kind"] == "uploaded"
    assert created["writable"] is True
    assert created["item_count"] == 0

    clone_response = api_client.post(
        f"/swipes/collections/{default_collection['id']}/clone",
        json={"name": "Default Clone"},
    )
    assert clone_response.status_code == 201, clone_response.text
    cloned = clone_response.json()
    assert cloned["name"] == "Default Clone"
    assert cloned["kind"] == "curated"
    assert cloned["cloned_from_collection_id"] == default_collection["id"]
    assert cloned["item_count"] == 1

    cloned_detail_response = api_client.get(f"/swipes/collections/{cloned['id']}")
    assert cloned_detail_response.status_code == 200, cloned_detail_response.text
    cloned_detail = cloned_detail_response.json()
    assert [item["id"] for item in cloned_detail["swipes"]] == [str(catalog_swipe.id)]


def test_swipe_collection_item_membership_and_taxonomy_patch(api_client, db_session) -> None:
    swipe = _seed_company_swipe(db_session, title="Editable Swipe")

    create_response = api_client.post(
        "/swipes/collections",
        json={"name": "Review Set", "kind": "curated"},
    )
    assert create_response.status_code == 201, create_response.text
    collection_id = create_response.json()["id"]

    add_response = api_client.post(
        f"/swipes/collections/{collection_id}/items",
        json={"swipeAssetIds": [str(swipe.id)]},
    )
    assert add_response.status_code == 201, add_response.text
    added_collection = add_response.json()
    assert added_collection["item_count"] == 1

    membership = db_session.scalars(
        select(SwipeCollectionItem).where(
            SwipeCollectionItem.collection_id == collection_id,
            SwipeCollectionItem.swipe_asset_id == swipe.id,
        )
    ).first()
    assert membership is not None

    patch_response = api_client.patch(
        f"/swipes/{swipe.id}",
        json={
            "channel": "meta",
            "funnel_stage": "cold",
            "angle_family": "problem",
            "product_image_policy": "either",
        },
    )
    assert patch_response.status_code == 200, patch_response.text
    updated_swipe = patch_response.json()
    assert updated_swipe["channel"] == "meta"
    assert updated_swipe["funnel_stage"] == "cold"
    assert updated_swipe["angle_family"] == "problem"
    assert updated_swipe["product_image_policy"] == "either"
    assert updated_swipe["analysis_updated_at"] is not None

    remove_response = api_client.delete(f"/swipes/collections/{collection_id}/items/{swipe.id}")
    assert remove_response.status_code == 200, remove_response.text
    removed_collection = remove_response.json()
    assert removed_collection["item_count"] == 0


def test_upload_swipes_to_collection_creates_assets_and_starts_taxonomy_workflows(
    api_client,
    db_session,
    fake_temporal,
    monkeypatch,
) -> None:
    create_response = api_client.post(
        "/swipes/collections",
        json={"name": "Upload Batch", "kind": "uploaded"},
    )
    assert create_response.status_code == 201, create_response.text
    collection_id = create_response.json()["id"]

    monkeypatch.setattr(swipes_router.settings, "SWIPE_TAXONOMY_MODEL", "gemini-test")

    def _fake_store_swipe_upload_media(*, content_bytes: bytes, filename: str | None, content_type: str):
        safe_name = (filename or "upload").replace(" ", "-")
        return swipes_router._StoredSwipeUpload(
            storage_key=f"orig/test/{safe_name}",
            mime_type=content_type,
            size_bytes=len(content_bytes),
            width=1080,
            height=1350,
        )

    monkeypatch.setattr(swipes_router, "_store_swipe_upload_media", _fake_store_swipe_upload_media)
    monkeypatch.setattr(
        swipes_router,
        "_build_media_access_url",
        lambda media: f"https://assets.example.com/{media.path}",
    )

    upload_response = api_client.post(
        f"/swipes/collections/{collection_id}/uploads",
        files=[
            ("files", ("first.png", b"first-image", "image/png")),
            ("files", ("second.png", b"second-image", "image/png")),
        ],
    )
    assert upload_response.status_code == 201, upload_response.text
    payload = upload_response.json()
    assert payload["collection_id"] == collection_id
    assert len(payload["created_swipes"]) == 2

    created_swipes = payload["created_swipes"]
    assert all(item["source_kind"] == "upload" for item in created_swipes)
    assert all(item["origin_system"] == "manual_upload" for item in created_swipes)
    assert all(item["analysis_status"] == "queued" for item in created_swipes)
    assert all(item["analysis_model"] == "gemini-test" for item in created_swipes)
    assert all(item["ad_unit_format"] == "image" for item in created_swipes)
    assert all(item["placement_shape"] == "portrait_4_5" for item in created_swipes)
    assert all(item["media"][0]["url"].startswith("https://assets.example.com/orig/test/") for item in created_swipes)

    stored_uploads = db_session.scalars(
        select(CompanySwipeAsset).where(
            CompanySwipeAsset.org_id == TEST_ORG_ID,
            CompanySwipeAsset.source_kind == "upload",
        )
    ).all()
    assert len(stored_uploads) == 2

    stored_asset_ids = {str(item.id) for item in stored_uploads}
    collection_memberships = db_session.scalars(
        select(SwipeCollectionItem).where(
            SwipeCollectionItem.collection_id == collection_id,
            SwipeCollectionItem.swipe_asset_id.in_(list(stored_asset_ids)),
        )
    ).all()
    assert len(collection_memberships) == 2

    assert len(fake_temporal.started) == 2
    assert all(workflow_id.startswith("swipe-taxonomy-") for workflow_id in fake_temporal.started)
