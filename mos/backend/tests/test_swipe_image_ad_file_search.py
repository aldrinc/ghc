from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from app.db.enums import GeminiContextFileStatusEnum
from app.db.models import GeminiContextFile
from app.temporal.activities import swipe_image_ad_activities as swipe_activity


def _create_campaign_with_product(api_client: TestClient, *, suffix: str) -> tuple[str, str, str]:
    client_resp = api_client.post("/clients", json={"name": f"Swipe Client {suffix}", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": f"Swipe Product {suffix}"},
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    campaign_resp = api_client.post(
        "/campaigns",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "name": f"Swipe Campaign {suffix}",
            "channels": ["meta"],
            "asset_brief_types": ["image"],
        },
    )
    assert campaign_resp.status_code == 201
    campaign_id = campaign_resp.json()["id"]
    return client_id, product_id, campaign_id


def test_resolve_gemini_store_names_uses_existing_files(api_client, db_session, auth_context, monkeypatch):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client, suffix="existing-store"
    )
    workspace_id = client_id

    record = GeminiContextFile(
        org_id=UUID(auth_context.org_id),
        idea_workspace_id=workspace_id,
        client_id=UUID(client_id),
        product_id=UUID(product_id),
        campaign_id=UUID(campaign_id),
        doc_key="foundation-doc",
        doc_title="Foundation Doc",
        source_kind="foundation",
        step_key=None,
        sha256="sha-existing-store",
        gemini_store_name="fileSearchStores/foundation-store",
        gemini_file_name=None,
        gemini_document_name="fileSearchStores/foundation-store/documents/foundation-doc",
        filename="foundation.md",
        mime_type="text/plain",
        size_bytes=256,
        drive_doc_id=None,
        drive_url=None,
        status=GeminiContextFileStatusEnum.ready,
    )
    db_session.add(record)
    db_session.commit()

    stores = swipe_activity._resolve_gemini_file_search_store_names(
        session=db_session,
        org_id=auth_context.org_id,
        idea_workspace_id=workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        client_name="Test Brand",
        product_title="Test Product",
        canon={"icps": []},
        design_system_tokens={},
        swipe_context_block="context",
        offer_context_block="offer",
    )
    assert stores == ["fileSearchStores/foundation-store"]


def test_resolve_gemini_store_names_seeds_when_missing(api_client, db_session, auth_context, monkeypatch):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client, suffix="seed-store"
    )
    workspace_id = client_id
    seeded_store = "fileSearchStores/seeded-store"
    seeded_doc = f"{seeded_store}/documents/seeded-doc"

    called: dict[str, bool] = {"value": False}

    def _fake_seed(**kwargs):
        called["value"] = True
        seeded = GeminiContextFile(
            org_id=UUID(kwargs["org_id"]),
            idea_workspace_id=kwargs["idea_workspace_id"],
            client_id=UUID(kwargs["client_id"]) if kwargs.get("client_id") else None,
            product_id=UUID(kwargs["product_id"]) if kwargs.get("product_id") else None,
            campaign_id=UUID(kwargs["campaign_id"]) if kwargs.get("campaign_id") else None,
            doc_key=kwargs["doc_key"],
            doc_title=kwargs["doc_title"],
            source_kind=kwargs["source_kind"],
            step_key=kwargs["step_key"],
            sha256="sha-seeded-store",
            gemini_store_name=seeded_store,
            gemini_file_name=None,
            gemini_document_name=seeded_doc,
            filename=kwargs["filename"],
            mime_type=kwargs["mime_type"],
            size_bytes=len(kwargs["content_bytes"]),
            drive_doc_id=None,
            drive_url=None,
            status=GeminiContextFileStatusEnum.ready,
        )
        db_session.add(seeded)
        db_session.commit()
        return seeded_doc

    monkeypatch.setattr(swipe_activity, "ensure_uploaded_to_gemini_file_search", _fake_seed)

    stores = swipe_activity._resolve_gemini_file_search_store_names(
        session=db_session,
        org_id=auth_context.org_id,
        idea_workspace_id=workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        client_name="Seed Brand",
        product_title="Seed Product",
        canon={"summary": "canon"},
        design_system_tokens={"cssVars": {"--color-brand": "#123456"}},
        swipe_context_block="context",
        offer_context_block="offer",
    )

    assert called["value"] is True
    assert stores == [seeded_store]


def test_generate_swipe_image_ad_activity_uses_file_search_tools(monkeypatch):
    captured: dict[str, object] = {}

    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return SimpleNamespace(
                text="```text\nDense generation-ready prompt.\n```",
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    class _FakeCreativeClient:
        def create_image_ads(self, payload, idempotency_key):
            captured["creative_payload_prompt"] = payload.prompt
            captured["creative_payload_count"] = payload.count
            captured["creative_payload_reference_asset_ids"] = list(payload.reference_asset_ids or [])
            captured["creative_payload_reference_image_urls"] = list(payload.reference_image_urls or [])
            captured["creative_payload_reference_text"] = payload.reference_text
            captured["creative_payload_model_id"] = payload.model_id
            captured["creative_idempotency_key"] = idempotency_key
            return SimpleNamespace(id="job-123")

        def get_image_ads_job(self, job_id):
            assert job_id == "job-123"
            return SimpleNamespace(
                id=job_id,
                status="succeeded",
                error_detail=None,
                model_id="gemini-3-pro-image-preview",
                references=[],
                outputs=[
                    SimpleNamespace(
                        output_index=0,
                        asset_id="remote-asset-1",
                        prompt_used="Dense generation-ready prompt.",
                        primary_url="https://example.com/generated.png",
                    )
                ],
            )

    monkeypatch.setattr(swipe_activity, "session_scope", _fake_session_scope)
    monkeypatch.setattr(swipe_activity, "get_image_render_provider", lambda: "creative_service")
    monkeypatch.setattr(swipe_activity, "build_image_render_client", lambda: _FakeCreativeClient())
    monkeypatch.setattr(swipe_activity, "CreativeServiceClient", lambda: _FakeCreativeClient())
    monkeypatch.setattr(
        swipe_activity,
        "load_swipe_to_image_ad_prompt",
        lambda: (
            "\n".join(
                [
                    "You make ONE static image ad from ONE competitor swipe image.",
                    "Brand name: [BRAND_NAME]",
                    "Product: [PRODUCT]",
                    "Audience: [AUDIENCE] (optional)",
                    "Brand colors/fonts: [UNKNOWN if not given]",
                    "Must-avoid claims: [UNKNOWN if not given]",
                    "Assets: [PACKSHOT? LOGO?] (optional)",
                    "[User uploads image]",
                    "Use [BRAND_NAME] and [PRODUCT].",
                    "---",
                    "But with the items shown in brackets populated with our product/brand specific info.",
                ]
            ),
            "prompt-sha",
        ),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_extract_brief",
        lambda **_kwargs: (
            {
                "creativeConcept": "Concept",
                "requirements": [{"channel": "meta", "format": "image", "angle": "Clinical proof and fast results"}],
                "constraints": [],
                "toneGuidelines": [],
                "visualGuidelines": [],
            },
            "brief-artifact-id",
        ),
    )
    monkeypatch.setattr(swipe_activity, "_validate_brief_scope", lambda **_kwargs: None)
    monkeypatch.setattr(
        swipe_activity,
        "_extract_brand_context",
        lambda **_kwargs: {
            "client_name": "Brand Name",
            "product_title": "Product Name",
            "canon": {"constraints": {"legal": ["No medical claims"]}},
            "design_system_tokens": {},
        },
    )
    monkeypatch.setattr(
        swipe_activity,
        "_build_product_offer_context_block",
        lambda **_kwargs: ("offer-context", "offer-signature", {"offerId": "offer-1", "pricePoints": []}),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_select_product_reference_assets",
        lambda **_kwargs: [
            SimpleNamespace(
                local_asset_id="local-product-asset-1",
                primary_url="https://example.com/product-1.png",
                title="Product 1",
                remote_asset_id=None,
            )
        ],
    )
    monkeypatch.setattr(
        swipe_activity,
        "_ensure_remote_reference_asset_ids",
        lambda **_kwargs: ["remote-product-asset-1"],
    )
    monkeypatch.setattr(
        swipe_activity,
        "_build_image_reference_text",
        lambda _references: "Use product reference image 1.",
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_swipe_image",
        lambda **_kwargs: (b"image-bytes", "image/png", "https://example.com/swipe.png"),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_download_bytes",
        lambda _url, *, max_bytes, timeout_seconds: (b"product-bytes", "image/png"),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_gemini_file_search_store_names",
        lambda **_kwargs: ["fileSearchStores/context-store"],
    )
    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())
    def _fake_create_generated_asset_from_url(**kwargs):
        captured["extra_ai_metadata"] = kwargs.get("extra_ai_metadata") or {}
        return "asset-1"

    monkeypatch.setattr(swipe_activity, "_create_generated_asset_from_url", _fake_create_generated_asset_from_url)

    result = swipe_activity.generate_swipe_image_ad_activity(
        {
            "org_id": "00000000-0000-0000-0000-000000000001",
            "client_id": "00000000-0000-0000-0000-000000000011",
            "product_id": "00000000-0000-0000-0000-000000000022",
            "campaign_id": "00000000-0000-0000-0000-000000000033",
            "asset_brief_id": "asset-brief-1",
            "requirement_index": 0,
            "company_swipe_id": "swipe-1",
            "model": "models/gemini-2.5-flash",
            "count": 1,
            "aspect_ratio": "1:1",
            "render_model_id": "gemini-3-pro-image-preview",
        }
    )

    assert result["asset_ids"] == ["asset-1"]
    assert result["stores_attached"] == 1
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["creative_payload_count"] == 1
    assert captured["creative_payload_reference_asset_ids"] == ["remote-product-asset-1"]
    assert captured["creative_payload_reference_image_urls"] == ["https://example.com/product-1.png"]
    assert captured["creative_payload_reference_text"] == "Use product reference image 1."
    assert captured["creative_payload_model_id"] == "models/gemini-3-pro-image-preview"
    prompt_input = captured["contents"][0]
    assert isinstance(prompt_input, str)
    assert "Brand name: Brand Name" in prompt_input
    assert "Product: Product Name" in prompt_input
    assert "Audience: [UNKNOWN] (optional)" in prompt_input
    assert "Brand colors/fonts: [UNKNOWN]" in prompt_input
    assert "Must-avoid claims: No medical claims" in prompt_input
    assert "Assets: PACKSHOT: Product 1; LOGO: [UNKNOWN] (optional)" in prompt_input
    assert "Angle: Clinical proof and fast results" in prompt_input
    assert (
        "Use emotional, raw, visceral VOCC from research documents around the primary precision, "
        "safety, dosage angle and secondary angles. Should be a punch in the gut style."
    ) in prompt_input
    assert "[BRAND_NAME]" not in prompt_input
    assert "[PRODUCT]" not in prompt_input
    assert "[AUDIENCE]" not in prompt_input
    assert "[User uploads image]" not in prompt_input
    assert "But with the items shown in brackets populated with our product/brand specific info." not in prompt_input
    assert "## SWIPE CONTEXT" not in prompt_input
    assert "<product_packshot_image>" in prompt_input
    assert len(captured["contents"]) == 3
    extra_ai_metadata = captured["extra_ai_metadata"]
    assert extra_ai_metadata["swipePromptImageAttached"] is True
    assert extra_ai_metadata["swipePromptImageMimeType"] == "image/png"
    assert extra_ai_metadata["swipePromptImageSourceUrl"] == "https://example.com/swipe.png"
    assert isinstance(extra_ai_metadata["swipePromptImageSizeBytes"], int)
    assert isinstance(extra_ai_metadata["swipePromptImageSha256"], str)
    assert len(extra_ai_metadata["swipePromptImageSha256"]) == 64
    assert extra_ai_metadata["swipePromptProductImageAttached"] is True
    assert extra_ai_metadata["swipePromptProductImageSourceUrl"] == "https://example.com/product-1.png"
    assert extra_ai_metadata["swipePromptProductImageMimeType"] == "image/png"
    assert isinstance(extra_ai_metadata["swipePromptProductImageSizeBytes"], int)
    assert isinstance(extra_ai_metadata["swipePromptProductImageSha256"], str)
    assert len(extra_ai_metadata["swipePromptProductImageSha256"]) == 64
    config = captured["config"]
    assert hasattr(config, "tools")
    assert config.tools
    assert config.tools[0].file_search.file_search_store_names == ["fileSearchStores/context-store"]


def test_generate_swipe_image_ad_activity_allows_missing_product_images(monkeypatch):
    captured: dict[str, object] = {}

    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return SimpleNamespace(
                text="```text\nDense generation-ready prompt.\n```",
                usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=22),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    class _FakeCreativeClient:
        def create_image_ads(self, payload, idempotency_key):
            captured["creative_payload_reference_image_urls"] = list(payload.reference_image_urls or [])
            return SimpleNamespace(id="job-123")

        def get_image_ads_job(self, job_id):
            assert job_id == "job-123"
            return SimpleNamespace(
                id=job_id,
                status="succeeded",
                error_detail=None,
                model_id="nano-banana-pro",
                references=[],
                outputs=[
                    SimpleNamespace(
                        output_index=0,
                        asset_id="remote-asset-1",
                        prompt_used="Dense generation-ready prompt.",
                        primary_url="https://example.com/generated.png",
                    )
                ],
            )

    monkeypatch.setattr(swipe_activity, "session_scope", _fake_session_scope)
    monkeypatch.setattr(swipe_activity, "get_image_render_provider", lambda: "higgsfield")
    monkeypatch.setattr(swipe_activity, "build_image_render_client", lambda: _FakeCreativeClient())
    monkeypatch.setattr(
        swipe_activity,
        "load_swipe_to_image_ad_prompt",
        lambda: (
            "\n".join(
                [
                    "You make ONE static image ad from ONE competitor swipe image.",
                    "Brand name: [BRAND_NAME]",
                    "Product: [PRODUCT]",
                    "Audience: [AUDIENCE] (optional)",
                    "Brand colors/fonts: [UNKNOWN if not given]",
                    "Must-avoid claims: [UNKNOWN if not given]",
                    "Assets: [PACKSHOT? LOGO?] (optional)",
                    "[User uploads image]",
                ]
            ),
            "prompt-sha",
        ),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_extract_brief",
        lambda **_kwargs: (
            {
                "creativeConcept": "Concept",
                "requirements": [{"channel": "meta", "format": "image", "angle": "Clinical proof"}],
                "constraints": [],
                "toneGuidelines": [],
                "visualGuidelines": [],
            },
            "brief-artifact-id",
        ),
    )
    monkeypatch.setattr(swipe_activity, "_validate_brief_scope", lambda **_kwargs: None)
    monkeypatch.setattr(
        swipe_activity,
        "_extract_brand_context",
        lambda **_kwargs: {
            "client_name": "Brand Name",
            "product_title": "Product Name",
            "canon": {"constraints": {"legal": []}},
            "design_system_tokens": {},
        },
    )
    monkeypatch.setattr(
        swipe_activity,
        "_select_product_reference_assets",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("No active source product images are available for creative generation references.")
        ),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_swipe_image",
        lambda **_kwargs: (b"image-bytes", "image/png", "https://example.com/swipe.png"),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_download_bytes",
        lambda _url, *, max_bytes, timeout_seconds: (_ for _ in ()).throw(
            AssertionError("product reference image should not be downloaded when no product assets are present")
        ),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_gemini_file_search_store_names",
        lambda **_kwargs: ["fileSearchStores/context-store"],
    )
    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())
    monkeypatch.setattr(swipe_activity, "_create_generated_asset_from_url", lambda **_kwargs: "asset-1")

    result = swipe_activity.generate_swipe_image_ad_activity(
        {
            "org_id": "00000000-0000-0000-0000-000000000001",
            "client_id": "00000000-0000-0000-0000-000000000011",
            "product_id": "00000000-0000-0000-0000-000000000022",
            "campaign_id": "00000000-0000-0000-0000-000000000033",
            "asset_brief_id": "asset-brief-1",
            "requirement_index": 0,
            "company_swipe_id": "swipe-1",
            "model": "models/gemini-2.5-flash",
            "count": 1,
            "aspect_ratio": "1:1",
            "render_model_id": "nano-banana-pro",
        }
    )

    assert result["asset_ids"] == ["asset-1"]
    assert captured["creative_payload_reference_image_urls"] == []
    assert len(captured["contents"]) == 2
