from __future__ import annotations

from types import SimpleNamespace

from app.db.repositories.swipes import infer_swipe_asset_ad_unit_format


def test_infer_swipe_asset_ad_unit_format_prefers_explicit_value() -> None:
    media_items = [
        SimpleNamespace(type="VIDEO", mime_type="video/mp4", video_length=30),
    ]

    assert (
        infer_swipe_asset_ad_unit_format(ad_unit_format="image", media_items=media_items) == "image"
    )


def test_infer_swipe_asset_ad_unit_format_detects_legacy_static_image() -> None:
    media_items = [
        SimpleNamespace(type="IMAGE", mime_type="image/jpeg", video_length=None),
    ]

    assert infer_swipe_asset_ad_unit_format(ad_unit_format=None, media_items=media_items) == "image"


def test_infer_swipe_asset_ad_unit_format_detects_legacy_video() -> None:
    media_items = [
        SimpleNamespace(type="VIDEO", mime_type="video/mp4", video_length=18),
    ]

    assert infer_swipe_asset_ad_unit_format(ad_unit_format=None, media_items=media_items) == "video"


def test_infer_swipe_asset_ad_unit_format_detects_legacy_carousel() -> None:
    media_items = [
        SimpleNamespace(type="image", mime_type="image/jpeg", video_length=None),
        SimpleNamespace(type="image", mime_type="image/png", video_length=None),
    ]

    assert (
        infer_swipe_asset_ad_unit_format(ad_unit_format=None, media_items=media_items)
        == "carousel"
    )
