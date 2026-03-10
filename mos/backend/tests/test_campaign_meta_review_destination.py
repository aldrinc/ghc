from app.routers.campaigns import _resolve_meta_review_destination_url


def test_resolve_meta_review_destination_url_prefers_review_paths() -> None:
    assert (
        _resolve_meta_review_destination_url(
            destination_page="pre-sales",
            review_paths={"pre-sales": "/f/product/funnel/pre-sales"},
        )
        == "/f/product/funnel/pre-sales"
    )
    assert (
        _resolve_meta_review_destination_url(
            destination_page="https://example.com/offer",
            review_paths={"pre-sales": "/f/product/funnel/pre-sales"},
        )
        == "https://example.com/offer"
    )
