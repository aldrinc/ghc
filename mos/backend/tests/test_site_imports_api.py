"""Tests for site import API endpoints."""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_capture_result():
    """Mock capture result for testing."""
    return {
        "html_snapshot": "<html><body><h1>Test Site</h1></body></html>",
        "desktop_screenshot_data_url": "data:image/png;base64,mock",
        "mobile_screenshot_data_url": "data:image/png;base64,mock",
        "title": "Test Site",
        "meta_description": "A test site",
        "capture_metadata": {
            "palette": {"primary": "rgb(0,0,0)", "background": "rgb(255,255,255)"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable"},
            "cta": {"style": "solid"},
            "sectionCandidates": [
                {
                    "tag": "section",
                    "selector": "section.hero",
                    "textPreview": "Welcome to our site",
                    "boundingBox": {"x": 0, "y": 0, "width": 1200, "height": 600},
                    "computedStyles": {
                        "backgroundColor": "rgb(255,255,255)",
                        "color": "rgb(0,0,0)",
                    },
                }
            ],
        },
    }


@pytest.fixture
def mock_normalize_result():
    """Mock normalization result for testing."""
    return {
        "title": "Test Site",
        "meta_description": "A test site",
        "theme_candidate": {
            "palette": {"primary": "rgb(0,0,0)", "background": "rgb(255,255,255)"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable", "scale": []},
            "cta": {"style": "solid"},
        },
        "normalized_sections": [
            {
                "id": "section_001",
                "sectionType": "hero",
                "confidence": 0.9,
                "keyText": ["Welcome"],
                "keyMedia": [],
                "keyStyles": {},
                "boundingBox": {"x": 0, "y": 0, "width": 1200, "height": 600},
            }
        ],
        "suggested_template_family": "sales-pdp",
    }


def test_list_imports_empty(api_client):
    """Test listing imports when none exist."""
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.get(f"/storefront/templates/imports?clientId={client_id}")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 0


def test_create_import_requires_url(api_client):
    """Test that creating an import requires a source URL."""
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": ""},
    )

    # Should fail validation
    assert response.status_code == 422


def test_create_import_validates_workspace(api_client):
    """Test that creating an import validates the workspace exists."""
    response = api_client.post(
        "/storefront/templates/imports?clientId=nonexistent",
        json={"sourceUrl": "https://example.com"},
    )

    assert response.status_code == 404


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_create_import_success(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test successful import creation with mocked capture."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com", "pageTypeHint": "product"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["sourceUrl"] == "https://example.com"
    assert payload["pageTypeHint"] == "product"
    assert payload["status"] in ["running", "completed", "failed"]


def test_get_import_detail_not_found(api_client):
    """Test getting a non-existent import returns 404."""
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.get(f"/storefront/templates/imports/nonexistent-id?clientId={client_id}")

    assert response.status_code == 404


def test_list_variants_empty(api_client):
    """Test listing variants when none exist."""
    response = api_client.post(
        "/clients", json={"name": "Test Variant Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.get(f"/storefront/templates/variants?clientId={client_id}")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 0


def test_list_variants_validates_workspace(api_client):
    """Test that listing variants validates the workspace exists."""
    response = api_client.get("/storefront/templates/variants?clientId=nonexistent")

    assert response.status_code == 404


def test_create_import_malformed_url(api_client):
    """Test that creating an import with malformed URL returns 422."""
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    # Test various malformed URLs
    malformed_urls = [
        "not-a-url",
        "htp://example.com",  # typo in scheme
        "://example.com",  # missing scheme
        "example.com",  # missing scheme
    ]

    for url in malformed_urls:
        response = api_client.post(
            f"/storefront/templates/imports?clientId={client_id}",
            json={"sourceUrl": url},
        )
        assert response.status_code == 422, f"Expected 422 for URL: {url}"


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_get_import_detail_success(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test getting import detail returns normalized sections with bounding boxes."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get import detail
    response = api_client.get(f"/storefront/templates/imports/{import_id}?clientId={client_id}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == import_id
    assert payload["status"] == "completed"
    assert len(payload["normalizedSections"]) > 0

    # Check bounding box is included
    section = payload["normalizedSections"][0]
    assert "boundingBox" in section
    assert section["boundingBox"] is not None
    assert "width" in section["boundingBox"]
    assert "height" in section["boundingBox"]


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_get_import_snapshot_success(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test getting import snapshot returns screenshots and metadata."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get import snapshot
    response = api_client.get(
        f"/storefront/templates/imports/{import_id}/snapshot?clientId={client_id}"
    )
    assert response.status_code == 200
    payload = response.json()

    assert "htmlSnapshot" in payload
    assert "desktopScreenshotDataUrl" in payload
    assert "mobileScreenshotDataUrl" in payload
    assert "captureMetadata" in payload
    # Verify screenshot data URLs are properly formatted
    assert payload["desktopScreenshotDataUrl"].startswith("data:image/png;base64,")
    assert payload["mobileScreenshotDataUrl"].startswith("data:image/png;base64,")


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_convert_import_success(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test successful conversion of import to variant."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get the import to find section IDs
    response = api_client.get(f"/storefront/templates/imports/{import_id}?clientId={client_id}")
    assert response.status_code == 200
    sections = response.json()["normalizedSections"]
    section_id = sections[0]["id"]

    # Convert import
    response = api_client.post(
        f"/storefront/templates/imports/{import_id}/convert?clientId={client_id}",
        json={
            "name": "My Variant",
            "family": "sales-pdp",
            "pageType": "product_detail",
            "acceptedSectionIds": [section_id],
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["name"] == "My Variant"
    assert payload["family"] == "sales-pdp"
    assert payload["pageType"] == "product_detail"
    assert payload["siteImportId"] == import_id
    assert len(payload["acceptedSections"]) > 0


def test_convert_import_empty_section_ids(api_client):
    """Test that convert fails with empty acceptedSectionIds."""
    # Create client
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    # Try to convert with empty section IDs - need a valid import
    # Since we can't easily create a completed import without mocking,
    # we test the validation at the API level
    response = api_client.post(
        f"/storefront/templates/imports/00000000-0000-0000-0000-000000000001/convert?clientId={client_id}",
        json={
            "name": "My Variant",
            "family": "sales-pdp",
            "pageType": "product_detail",
            "acceptedSectionIds": [],
        },
    )
    # Should return 422 for empty acceptedSectionIds
    assert response.status_code == 422


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_get_import_detail_includes_synthesis_output(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test that import detail includes synthesis output when status is completed."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get import detail - should include synthesis output
    response = api_client.get(f"/storefront/templates/imports/{import_id}?clientId={client_id}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "completed"
    # synthesis field should be present and non-null
    assert "synthesis" in payload
    assert payload["synthesis"] is not None
    synthesis = payload["synthesis"]
    assert "targetFamily" in synthesis
    assert "blockCoverage" in synthesis
    assert "synthesizedPuckData" in synthesis


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_get_import_detail_synthesis_with_target_family(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test that synthesis preview uses target family from query params."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get import detail with target family
    response = api_client.get(
        f"/storefront/templates/imports/{import_id}?clientId={client_id}&targetFamily=listicle-presell&targetPageType=pre_sell"
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "completed"
    assert payload["synthesis"] is not None
    # Should use the target family from query params
    assert payload["synthesis"]["targetFamily"] == "listicle-presell"
    assert payload["synthesis"]["targetPageType"] == "pre_sell"


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_get_import_detail_synthesis_with_accepted_sections(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test that synthesis preview filters to accepted section IDs."""
    # Add more sections to the mock
    mock_normalize_result_with_sections = {
        "title": "Test Site",
        "meta_description": "A test site",
        "theme_candidate": {
            "palette": {"primary": "rgb(0,0,0)", "background": "rgb(255,255,255)"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable", "scale": []},
            "cta": {"style": "solid"},
        },
        "normalized_sections": [
            {
                "id": "section_001",
                "sectionType": "hero",
                "confidence": 0.9,
                "keyText": ["Welcome"],
                "keyMedia": [],
                "keyStyles": {},
                "boundingBox": {"x": 0, "y": 0, "width": 1200, "height": 600},
            },
            {
                "id": "section_002",
                "sectionType": "proof_bar",
                "confidence": 0.9,
                "keyText": ["Guarantee"],
                "keyMedia": [],
                "keyStyles": {},
                "boundingBox": {"x": 0, "y": 600, "width": 1200, "height": 100},
            },
            {
                "id": "section_003",
                "sectionType": "footer",
                "confidence": 0.95,
                "keyText": ["Copyright"],
                "keyMedia": [],
                "keyStyles": {},
                "boundingBox": {"x": 0, "y": 700, "width": 1200, "height": 200},
            },
        ],
        "suggested_template_family": "sales-pdp",
    }

    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type(
        "NormalizationResult", (), mock_normalize_result_with_sections
    )()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get current import detail first so we can use the real stored section id
    response = api_client.get(f"/storefront/templates/imports/{import_id}?clientId={client_id}")
    assert response.status_code == 200
    stored_sections = response.json()["normalizedSections"]
    accepted_section_id = stored_sections[0]["id"]

    # Get import detail with only one accepted section - specify family to ensure mapping works
    response = api_client.get(
        f"/storefront/templates/imports/{import_id}?clientId={client_id}&targetFamily=sales-pdp&acceptedSectionIds={accepted_section_id}"
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "completed"
    assert payload["synthesis"] is not None
    # Should only have 1 section in coverage (the accepted one)
    assert payload["synthesis"]["blockCoverage"]["totalSections"] == 1


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_get_import_detail_invalid_family_returns_400(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test that invalid family returns 400 error."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get import detail with invalid family
    response = api_client.get(
        f"/storefront/templates/imports/{import_id}?clientId={client_id}&targetFamily=invalid-family"
    )
    assert response.status_code == 400
    assert "Unsupported template family" in response.json()["detail"]


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_get_import_detail_invalid_accepted_section_ids_returns_400(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Preview should reject invalid accepted section ids just like convert does."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    response = api_client.get(
        f"/storefront/templates/imports/{import_id}?clientId={client_id}&acceptedSectionIds=missing-section"
    )
    assert response.status_code == 400
    assert "Invalid section IDs" in response.json()["detail"]


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_convert_invalid_family_returns_400(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test that convert with invalid family returns a clean 400 error."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    response = api_client.get(f"/storefront/templates/imports/{import_id}?clientId={client_id}")
    assert response.status_code == 200
    section_id = response.json()["normalizedSections"][0]["id"]

    response = api_client.post(
        f"/storefront/templates/imports/{import_id}/convert?clientId={client_id}",
        json={
            "name": "My Variant",
            "family": "invalid-family",
            "pageType": "product_detail",
            "acceptedSectionIds": [section_id],
        },
    )

    assert response.status_code == 400
    assert "Unsupported template family" in response.json()["detail"]


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_import_normalize.normalize_capture")
def test_convert_provenance_includes_synthesized_puck_data(
    mock_normalize, mock_capture, api_client, mock_capture_result, mock_normalize_result
):
    """Test that convert provenance includes synthesizedPuckData."""
    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), mock_normalize_result)()

    # Create client and import
    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    # Get the import to find section IDs
    response = api_client.get(f"/storefront/templates/imports/{import_id}?clientId={client_id}")
    assert response.status_code == 200
    sections = response.json()["normalizedSections"]
    section_id = sections[0]["id"]

    # Convert import
    response = api_client.post(
        f"/storefront/templates/imports/{import_id}/convert?clientId={client_id}",
        json={
            "name": "My Variant",
            "family": "sales-pdp",
            "pageType": "product_detail",
            "acceptedSectionIds": [section_id],
        },
    )
    assert response.status_code == 200
    payload = response.json()

    # Check provenance includes synthesizedPuckData
    provenance = payload.get("provenance", {})
    assert "synthesis" in provenance
    synthesis = provenance["synthesis"]
    assert "synthesized_puck_data" in synthesis
    assert synthesis["synthesized_puck_data"] is not None


@patch("app.services.site_imports.capture_site")
@patch("app.services.site_imports.normalize_capture")
def test_convert_provenance_preserves_missing_block_request_context(
    mock_normalize, mock_capture, api_client, mock_capture_result
):
    """Test that convert provenance keeps source selector and text preview for missing blocks."""
    normalize_result = {
        "title": "Test Site",
        "meta_description": "A test site",
        "theme_candidate": {
            "palette": {"primary": "rgb(0,0,0)", "background": "rgb(255,255,255)"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable", "scale": []},
            "cta": {"style": "solid"},
        },
        "normalized_sections": [
            {
                "id": "section_collection",
                "sectionType": "collection_grid",
                "confidence": 0.9,
                "keyText": ["Shop all products"],
                "keyMedia": [],
                "keyStyles": {"selector": ".products-grid"},
                "boundingBox": {"x": 0, "y": 0, "width": 1200, "height": 400},
            }
        ],
        "suggested_template_family": "sales-pdp",
    }

    mock_capture.return_value = type(
        "CaptureResult",
        (),
        mock_capture_result,
    )()
    mock_normalize.return_value = type("NormalizationResult", (), normalize_result)()

    response = api_client.post(
        "/clients", json={"name": "Test Import Workspace", "industry": "Pets"}
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports?clientId={client_id}",
        json={"sourceUrl": "https://example.com"},
    )
    assert response.status_code == 201
    import_id = response.json()["id"]

    response = api_client.post(
        f"/storefront/templates/imports/{import_id}/convert?clientId={client_id}",
        json={
            "name": "Collection Variant",
            "family": "sales-pdp",
            "pageType": "product_detail",
            "acceptedSectionIds": ["section_collection"],
        },
    )
    assert response.status_code == 200

    synthesis = response.json()["provenance"]["synthesis"]
    missing_requests = synthesis["missing_block_requests"]
    assert len(missing_requests) == 1
    assert missing_requests[0]["source_selector"] == ".products-grid"
    assert missing_requests[0]["text_preview"] == "Shop all products"
