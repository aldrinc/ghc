from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.temporal.activities import swipe_image_ad_activities as swipe_activity


@pytest.fixture(autouse=True)
def _stub_genai_types_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    if swipe_activity.genai_types is not None:
        return

    class _FakePart:
        def __init__(self, *, data: bytes, mime_type: str) -> None:
            self.data = data
            self.mime_type = mime_type

        @classmethod
        def from_bytes(cls, *, data: bytes, mime_type: str):
            return cls(data=data, mime_type=mime_type)

    class _FakeFileSearch:
        def __init__(self, *, file_search_store_names):
            self.file_search_store_names = file_search_store_names

    class _FakeTool:
        def __init__(self, *, file_search):
            self.file_search = file_search

    class _FakeGenerateContentConfig:
        def __init__(
            self,
            *,
            temperature: float,
            max_output_tokens: int,
            tools=None,
            system_instruction: str | None = None,
            response_mime_type: str | None = None,
            response_json_schema=None,
        ):
            self.temperature = temperature
            self.max_output_tokens = max_output_tokens
            self.tools = tools
            self.system_instruction = system_instruction
            self.response_mime_type = response_mime_type
            self.response_json_schema = response_json_schema

    monkeypatch.setattr(
        swipe_activity,
        "genai_types",
        SimpleNamespace(
            Part=_FakePart,
            FileSearch=_FakeFileSearch,
            Tool=_FakeTool,
            GenerateContentConfig=_FakeGenerateContentConfig,
        ),
    )


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


def _fake_swipe_stage1_rag_docs() -> list[dict[str, object]]:
    doc_keys = [
        "swipe_stage1_client_canon",
        "swipe_stage1_design_system",
        "swipe_stage1_product_profile",
        "swipe_stage1_offer_pricing",
        "swipe_stage1_strategy_v2_offer",
        "swipe_stage1_strategy_v2_stage0",
        "swipe_stage1_strategy_v2_stage1",
        "swipe_stage1_strategy_v2_stage2",
        "swipe_stage1_strategy_v2_stage3",
        "swipe_stage1_strategy_v2_awareness_angle_matrix",
        "swipe_stage1_strategy_v2_copy_context",
        "swipe_stage1_strategy_v2_copy",
        "swipe_stage1_campaign_strategy_sheet",
        "swipe_stage1_campaign_experiment_spec",
        "swipe_stage1_campaign_asset_brief",
    ]
    return [
        {
            "doc_key": doc_key,
            "doc_title": doc_key.replace("_", " ").title(),
            "source_kind": "test",
            "mime_type": "text/plain",
            "content_bytes": f"{doc_key} content".encode("utf-8"),
        }
        for doc_key in doc_keys
    ]


def _fake_file_search_context(**_kwargs):
    return (["fileSearchStores/context-store"], [], [], [])


def _fake_swipe_copy_pack_parsed(*, angle: str) -> dict[str, object]:
    return {
        "selectedVariation": "Variation 1",
        "formattedVariationsMarkdown": (
            "```markdown\n"
            "Variation 1\n"
            "Meta Primary Text: Nights keep breaking down for the same hidden reason.\n"
            "Meta Headline: Fix the routine bottleneck\n"
            "Meta Description: Learn what actually changes the pattern\n"
            "Meta CTA: Learn More\n"
            "```\n"
        ),
        "metaPrimaryText": f"{angle} with a compliant curiosity-led hook.",
        "metaHeadline": "Fix the routine bottleneck",
        "metaDescription": "Learn what actually changes the pattern",
        "metaCta": "Learn More",
        "claimsGuardrails": ["Do not promise medical outcomes."],
    }


def test_resolve_gemini_store_names_uses_existing_files(api_client, db_session, auth_context, monkeypatch):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client, suffix="existing-store"
    )
    workspace_id = client_id

    monkeypatch.setattr(
        swipe_activity,
        "_load_required_swipe_stage1_rag_docs",
        lambda **_kwargs: _fake_swipe_stage1_rag_docs(),
    )
    monkeypatch.setattr(
        swipe_activity,
        "ensure_uploaded_to_gemini_file_search",
        lambda **kwargs: f"fileSearchStores/foundation-store/documents/{kwargs['doc_key']}",
    )

    stores, source_doc_keys, bundle_doc_keys, document_names = (
        swipe_activity._resolve_swipe_stage1_gemini_file_search_context(
            session=db_session,
            org_id=auth_context.org_id,
            idea_workspace_id=workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            funnel_id=None,
            asset_brief_artifact_id="brief-1",
        )
    )

    assert stores == ["fileSearchStores/foundation-store"]
    assert len(source_doc_keys) == 15
    assert len(bundle_doc_keys) == 5
    assert len(document_names) == 5


def test_resolve_gemini_store_names_seeds_when_missing(api_client, db_session, auth_context, monkeypatch):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client, suffix="seed-store"
    )
    workspace_id = client_id
    seeded_store = "fileSearchStores/seeded-store"
    seeded_doc = f"{seeded_store}/documents/seeded-doc"

    called: dict[str, bool] = {"value": False}

    monkeypatch.setattr(
        swipe_activity,
        "_load_required_swipe_stage1_rag_docs",
        lambda **_kwargs: _fake_swipe_stage1_rag_docs(),
    )

    def _fake_seed(**_kwargs):
        called["value"] = True
        return seeded_doc

    monkeypatch.setattr(swipe_activity, "ensure_uploaded_to_gemini_file_search", _fake_seed)

    stores, _source_doc_keys, bundle_doc_keys, document_names = (
        swipe_activity._resolve_swipe_stage1_gemini_file_search_context(
            session=db_session,
            org_id=auth_context.org_id,
            idea_workspace_id=workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            funnel_id=None,
            asset_brief_artifact_id="brief-1",
        )
    )

    assert called["value"] is True
    assert stores == [seeded_store]
    assert len(bundle_doc_keys) == 5
    assert len(document_names) == 5


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
            if len(contents) >= 2 and contents[1] == "Ad Image or Video asset:":
                return SimpleNamespace(
                    parsed=_fake_swipe_copy_pack_parsed(angle="Clinical proof and fast results"),
                    text="",
                    usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
                )
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
    monkeypatch.setattr(swipe_activity, "get_image_render_provider", lambda **_kwargs: "creative_service")
    monkeypatch.setattr(swipe_activity, "build_image_render_client", lambda **_kwargs: _FakeCreativeClient())
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
                    "requirements": [
                        {
                            "channel": "meta",
                            "format": "image",
                            "angle": "Clinical proof and fast results",
                            "funnelStage": "bottom-of-funnel",
                        }
                    ],
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
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
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
        "_resolve_swipe_stage1_gemini_file_search_context",
        _fake_file_search_context,
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
    assert captured["creative_payload_reference_asset_ids"] == ["local-product-asset-1"]
    assert captured["creative_payload_reference_image_urls"] == []
    assert captured["creative_payload_model_id"] == "models/gemini-3-pro-image-preview"
    prompt_input = captured["contents"][0]
    assert isinstance(prompt_input, str)
    assert "Brand name: [BRAND_NAME]" in prompt_input
    assert "Product: [PRODUCT]" in prompt_input
    assert "RUNTIME INPUTS (INJECTED)" in prompt_input
    assert "Brand: Brand Name" in prompt_input
    assert "Angle: Clinical proof and fast results" in prompt_input
    assert "Competitor swipe image is attached as image input." in prompt_input
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
            if len(contents) >= 2 and contents[1] == "Ad Image or Video asset:":
                return SimpleNamespace(
                    parsed=_fake_swipe_copy_pack_parsed(angle="Clinical proof"),
                    text="",
                    usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=22),
                )
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
    monkeypatch.setattr(swipe_activity, "get_image_render_provider", lambda **_kwargs: "higgsfield")
    monkeypatch.setattr(swipe_activity, "build_image_render_client", lambda **_kwargs: _FakeCreativeClient())
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
                    "requirements": [
                        {
                            "channel": "meta",
                            "format": "image",
                            "angle": "Clinical proof",
                            "funnelStage": "bottom-of-funnel",
                        }
                    ],
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
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
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
        "_resolve_swipe_stage1_gemini_file_search_context",
        _fake_file_search_context,
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


def test_generate_swipe_image_ad_activity_omits_product_images_when_policy_false(monkeypatch):
    captured: dict[str, object] = {}

    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["contents"] = contents
            if len(contents) >= 2 and contents[1] == "Ad Image or Video asset:":
                return SimpleNamespace(
                    parsed=_fake_swipe_copy_pack_parsed(angle="Clinical proof"),
                    text="",
                    usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=22),
                )
            return SimpleNamespace(
                text="```text\nDense generation-ready prompt.\n```",
                usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=22),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    class _FakeRenderClient:
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
    monkeypatch.setattr(swipe_activity, "get_image_render_provider", lambda **_kwargs: "higgsfield")
    monkeypatch.setattr(swipe_activity, "build_image_render_client", lambda **_kwargs: _FakeRenderClient())
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
                    "requirements": [
                        {
                            "channel": "meta",
                            "format": "image",
                            "angle": "Clinical proof",
                            "funnelStage": "bottom-of-funnel",
                        }
                    ],
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
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_select_product_reference_assets",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("product references should not be selected when swipe_requires_product_image=false")
        ),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_swipe_image",
        lambda **_kwargs: (b"image-bytes", "image/png", "https://example.com/women_health.jpg"),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_download_bytes",
        lambda _url, *, max_bytes, timeout_seconds: (_ for _ in ()).throw(
            AssertionError("product image should not be downloaded when swipe_requires_product_image=false")
        ),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_swipe_stage1_gemini_file_search_context",
        _fake_file_search_context,
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
            "swipe_requires_product_image": False,
            "model": "models/gemini-2.5-flash",
            "count": 1,
            "aspect_ratio": "1:1",
            "render_model_id": "nano-banana-pro",
        }
    )

    assert result["asset_ids"] == ["asset-1"]
    assert captured["creative_payload_reference_image_urls"] == []
    assert len(captured["contents"]) == 2


def test_generate_swipe_image_ad_activity_errors_when_policy_true_and_no_product_assets(monkeypatch):
    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeGeminiClient:
        def __init__(self):
            self.models = SimpleNamespace(generate_content=lambda **_kwargs: None)

    class _FakeRenderClient:
        def create_image_ads(self, payload, idempotency_key):  # pragma: no cover
            raise AssertionError("render call should not happen when product policy validation fails early")

    monkeypatch.setattr(swipe_activity, "session_scope", _fake_session_scope)
    monkeypatch.setattr(swipe_activity, "get_image_render_provider", lambda **_kwargs: "higgsfield")
    monkeypatch.setattr(swipe_activity, "build_image_render_client", lambda **_kwargs: _FakeRenderClient())
    monkeypatch.setattr(
        swipe_activity,
        "load_swipe_to_image_ad_prompt",
        lambda: ("Brand name: [BRAND_NAME]\nProduct: [PRODUCT]\n[User uploads image]", "prompt-sha"),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_extract_brief",
        lambda **_kwargs: (
            {
                "creativeConcept": "Concept",
                "requirements": [{"channel": "meta", "format": "image"}],
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
        "_resolve_swipe_image",
        lambda **_kwargs: (b"image-bytes", "image/png", "https://example.com/5.png"),
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
        "_resolve_swipe_stage1_gemini_file_search_context",
        _fake_file_search_context,
    )
    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())
    monkeypatch.setattr(swipe_activity, "_create_generated_asset_from_url", lambda **_kwargs: "asset-1")

    try:
        swipe_activity.generate_swipe_image_ad_activity(
            {
                "org_id": "00000000-0000-0000-0000-000000000001",
                "client_id": "00000000-0000-0000-0000-000000000011",
                "product_id": "00000000-0000-0000-0000-000000000022",
                "campaign_id": "00000000-0000-0000-0000-000000000033",
                "asset_brief_id": "asset-brief-1",
                "requirement_index": 0,
                "company_swipe_id": "swipe-1",
                "swipe_requires_product_image": True,
                "model": "models/gemini-2.5-flash",
                "count": 1,
                "aspect_ratio": "1:1",
                "render_model_id": "nano-banana-pro",
            }
        )
    except ValueError as exc:
        assert "Swipe requires product image references" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError when swipe_requires_product_image=true and no product assets exist")
