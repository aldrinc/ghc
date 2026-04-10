from __future__ import annotations

from contextlib import contextmanager
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from temporalio.exceptions import ApplicationError

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


def _fake_brief_scope() -> SimpleNamespace:
    return SimpleNamespace(funnel_id=None, campaign_delivery_config=None)


def _fake_linked_ad_copy_pack_context(*, angle: str = "Clinical proof") -> dict[str, object]:
    return {
        "artifactId": "copy-artifact-1",
        "copyPackId": "copy-pack-1",
        "copyPack": {
            "id": "copy-pack-1",
            "requirementIndex": 0,
            "channel": "facebook",
            "format": "image",
            "funnelStage": "bottom-of-funnel",
            "angle": angle,
            "hook": angle,
            "creativeConcept": "Concept",
            "metaPrimaryText": "Baseline copy",
            "metaHeadline": "Baseline headline",
            "metaDescription": "Baseline description",
            "claimsGuardrails": ["Do not promise medical outcomes."],
        },
    }


def _part_data(part: object) -> bytes | None:
    inline_data = getattr(part, "inline_data", None)
    if inline_data is not None:
        return getattr(inline_data, "data", None)
    return getattr(part, "data", None)


def test_ensure_gemini_client_uses_settings_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeHttpOptions:
        def __init__(
            self,
            *,
            timeout: int,
            clientArgs: dict[str, object] | None = None,
            asyncClientArgs: dict[str, object] | None = None,
        ) -> None:
            self.timeout = timeout
            self.clientArgs = clientArgs
            self.asyncClientArgs = asyncClientArgs
            captured["timeout"] = timeout
            captured["clientArgs"] = clientArgs
            captured["asyncClientArgs"] = asyncClientArgs

    class _FakeClient:
        def __init__(self, *, api_key: str, http_options: object) -> None:
            self.api_key = api_key
            self.http_options = http_options
            captured["api_key"] = api_key
            captured["http_options"] = http_options

    monkeypatch.setattr(swipe_activity, "_GEMINI_CLIENT", None)
    monkeypatch.setattr(swipe_activity, "genai", SimpleNamespace(Client=_FakeClient))
    monkeypatch.setattr(
        swipe_activity,
        "genai_types",
        SimpleNamespace(HttpOptions=_FakeHttpOptions),
    )
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(swipe_activity.settings, "SWIPE_GEMINI_TIMEOUT_SECONDS", 300)

    client = swipe_activity._ensure_gemini_client()

    assert isinstance(client, _FakeClient)
    assert captured["api_key"] == "test-gemini-key"
    assert captured["timeout"] == 300_000
    sync_timeout = captured["clientArgs"]["timeout"]
    async_timeout = captured["asyncClientArgs"]["timeout"]
    assert isinstance(sync_timeout, httpx.Timeout)
    assert sync_timeout.connect == 30.0
    assert sync_timeout.read == 300.0
    assert sync_timeout.write == 300.0
    assert sync_timeout.pool == 300.0
    assert async_timeout is sync_timeout


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


def _fake_swipe_stage1_rag_docs_with_json_content() -> list[dict[str, object]]:
    docs = _fake_swipe_stage1_rag_docs()
    for doc in docs:
        doc_key = str(doc["doc_key"])
        doc["content_bytes"] = json.dumps(
            {
                "docKey": doc_key,
                "headline": f"{doc_key} headline",
                "quoted": '"quoted value"',
            },
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
    return docs


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


def test_collect_blind_angle_forbidden_terms_skips_single_generic_taxonomy_words():
    terms = swipe_activity._collect_blind_angle_forbidden_terms(
        "Interaction-First Safety Checker",
        "Interaction-First Safety Checker framed for Contraindications-First Monographs",
    )

    assert "interaction first safety checker" in terms
    assert "interaction first safety" in terms
    assert "interaction" not in terms
    assert "safety" not in terms


def test_build_swipe_stage1_destination_context_uses_manual_artifact_names():
    destination_context = swipe_activity._build_swipe_stage1_destination_context(
        destination_type_slug="pre-sales",
        resolved_destination_url="https://example.com/presell",
        gemini_rag_doc_keys=[
            "swipe_stage1_campaign_asset_brief",
            "swipe_stage1_campaign_loaded_copy",
            "swipe_stage1_campaign_creative_context",
        ],
    )

    assert destination_context is not None
    assert "Destination page type: Pre-Sales Landing Page (pre-sales)" in destination_context
    assert "Resolved destination URL: https://example.com/presell" in destination_context
    assert "Swipe Stage1 Campaign Asset Brief" in destination_context
    assert "Swipe Stage1 Campaign Loaded Copy" in destination_context
    assert "Swipe Stage1 Campaign Creative Context" in destination_context
    assert "presell or pre-sales page content" in destination_context
    assert "pull it from those artifacts instead of inventing it" in destination_context


def test_build_swipe_stage1_destination_context_uses_strategy_artifact_names():
    destination_context = swipe_activity._build_swipe_stage1_destination_context(
        destination_type_slug="sales",
        resolved_destination_url=None,
        gemini_rag_doc_keys=[
            "swipe_stage1_campaign_asset_brief",
            "swipe_stage1_strategy_v2_copy",
            "swipe_stage1_strategy_v2_copy_context",
        ],
    )

    assert destination_context is not None
    assert "Destination page type: Sales Page (sales)" in destination_context
    assert "Swipe Stage1 Strategy V2 Copy" in destination_context
    assert "Swipe Stage1 Strategy V2 Copy Context" in destination_context
    assert "sales page content as the post-click continuity anchor" in destination_context


def test_build_swipe_stage1_prompt_input_includes_workspace_brand_colors_fonts():
    rendered = swipe_activity._build_swipe_stage1_prompt_input(
        prompt_template="Base swipe prompt",
        brand_name="Ember",
        angle="Clinical proof",
        destination_context="Destination page type: Sales Page (sales)",
        brand_colors_fonts="Heading font: Bookmania | Body font: Proxima Nova | Brand color: #C41423",
    )

    assert "Base swipe prompt" in rendered
    assert "RUNTIME INPUTS (INJECTED)" in rendered
    assert "Brand: Ember" in rendered
    assert "Angle: Clinical proof" in rendered
    assert "Brand colors/fonts: Heading font: Bookmania | Body font: Proxima Nova | Brand color: #C41423" in rendered
    assert "Destination page type: Sales Page (sales)" in rendered
    assert "Competitor swipe image is attached as image input." in rendered


def test_validate_swipe_copy_blind_angle_blackout_rejects_exact_internal_angle_phrase():
    copy_pack = swipe_activity.SwipeAdCopyPack.model_validate(
        {
            "platform": "meta",
            "requirementIndex": 0,
            "channel": "facebook",
            "format": "image",
            "funnelStage": "mid",
            "angle": "Interaction-First Safety Checker",
            "hook": "Interaction-First Safety Checker framed for Contraindications-First Monographs",
            "destinationType": "presell",
            "selectedVariation": "Variation 1: Interaction First Safety Checker",
            "formattedVariationsMarkdown": (
                "```text\n"
                "**Variation 1: Interaction First Safety Checker**\n\n"
                "**Primary Text:**\n"
                "This interaction first safety checker shows you what to do before you add anything new.\n\n"
                "**Headline:** Interaction First Safety Checker\n"
                "**Description:** See the exact warning now.\n"
                "**CTA:** Learn More\n"
                "```"
            ),
            "metaPrimaryText": "This interaction first safety checker shows you what to do before you add anything new.",
            "metaHeadline": "Interaction First Safety Checker",
            "metaDescription": "See the exact warning now.",
            "metaCta": "Learn More",
            "claimsGuardrails": ["Do not promise medical outcomes."],
        }
    )

    with pytest.raises(ValueError, match="interaction first safety checker"):
        swipe_activity._validate_swipe_copy_blind_angle_blackout(
            copy_pack=copy_pack,
            forbidden_terms=swipe_activity._collect_blind_angle_forbidden_terms(
                "Interaction-First Safety Checker",
                "Interaction-First Safety Checker framed for Contraindications-First Monographs",
            ),
        )


def test_generate_swipe_stage1_copy_pack_allows_generic_safety_language_for_honest_herbalist(monkeypatch):
    captured_prompts: list[str] = []
    original_build_prompt = swipe_activity._build_swipe_copy_stage1_prompt

    def _fake_build_prompt(**kwargs):
        prompt = original_build_prompt(**kwargs)
        captured_prompts.append(prompt)
        return prompt

    parsed_payload = {
        "selectedVariation": "Variation 1: The Missing Warning",
        "formattedVariationsMarkdown": (
            "```text\n"
            "**Variation 1: The Missing Warning**\n\n"
            "**Primary Text:**\n"
            "You can feel fine and still miss the one detail that changes everything.\n\n"
            "For women juggling daily prescriptions, that missing detail can quietly turn a simple routine into a bigger problem.\n\n"
            "Before you add one more capsule, see the safety gap almost nobody warns you about.\n\n"
            "Tap below to see what to look for first.\n\n"
            "**Headline:** The Warning Most Women Never See\n"
            "**Description:** Catch the red flag before it compounds.\n"
            "**CTA:** Learn More\n"
            "```"
        ),
        "metaPrimaryText": (
            "You can feel fine and still miss the one detail that changes everything.\n\n"
            "For women juggling daily prescriptions, that missing detail can quietly turn a simple routine into a bigger problem.\n\n"
            "Before you add one more capsule, see the safety gap almost nobody warns you about.\n\n"
            "Tap below to see what to look for first."
        ),
        "metaHeadline": "The Warning Most Women Never See",
        "metaDescription": "Catch the red flag before it compounds.",
        "metaCta": "Learn More",
        "claimsGuardrails": ["Do not promise medical outcomes."],
    }

    monkeypatch.setattr(swipe_activity, "_resolve_destination_type", lambda **_kwargs: "presell")
    monkeypatch.setattr(swipe_activity, "_build_swipe_copy_stage1_prompt", _fake_build_prompt)
    monkeypatch.setattr(
        swipe_activity,
        "_call_swipe_copy_gemini_json_message",
        lambda **_kwargs: {
            "parsed": parsed_payload,
            "text": "",
            "stop_reason": "STOP",
            "output_tokens": 111,
        },
    )
    monkeypatch.setattr(
        swipe_activity,
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
    )

    validated, response, model = swipe_activity._generate_swipe_stage1_copy_pack(
        session=object(),
        brief={"id": "brief-1"},
        requirement_index=0,
        requirement={
            "channel": "facebook",
            "format": "image",
            "angle": "Interaction-First Safety Checker",
            "hook": "Interaction-First Safety Checker framed for Contraindications-First Monographs",
            "funnelStage": "mid",
        },
        copy_model="models/gemini-2.5-flash",
        gemini_store_names=["fileSearchStores/context-store"],
        swipe_bytes=b"image-bytes",
        swipe_mime_type="image/png",
        swipe_source_url="https://example.com/swipe.png",
        swipe_source_label="10.png",
        product_prompt_image_bytes=None,
        product_prompt_image_mime_type=None,
    )

    assert "safety gap" in (validated.meta_primary_text or "").lower()
    assert "internal taxonomy labels" in captured_prompts[0]
    assert response["output_tokens"] == 111
    assert model == "models/gemini-2.5-flash"


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


def test_resolve_gemini_store_names_builds_markdown_bundles(
    api_client, db_session, auth_context, monkeypatch
):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client, suffix="markdown-bundle"
    )
    workspace_id = client_id
    uploaded: list[dict[str, object]] = []

    monkeypatch.setattr(
        swipe_activity,
        "_load_required_swipe_stage1_rag_docs",
        lambda **_kwargs: _fake_swipe_stage1_rag_docs_with_json_content(),
    )

    def _fake_seed(**kwargs):
        uploaded.append(kwargs)
        return f"fileSearchStores/foundation-store/documents/{kwargs['doc_key']}"

    monkeypatch.setattr(swipe_activity, "ensure_uploaded_to_gemini_file_search", _fake_seed)

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

    brand_foundation = next(
        row for row in uploaded if row["doc_key"] == "swipe_stage1_bundle_brand_foundation"
    )
    bundle_text = brand_foundation["content_bytes"].decode("utf-8")

    assert brand_foundation["mime_type"] == "text/markdown"
    assert brand_foundation["filename"] == "swipe_stage1_bundle_brand_foundation.md"
    assert "# Swipe Stage1 Bundle: Brand Foundation" in bundle_text
    assert "## Swipe Stage1 Client Canon" in bundle_text
    assert '"docKey": "swipe_stage1_client_canon"' in bundle_text
    assert '\\"docKey\\"' not in bundle_text


def test_build_swipe_stage1_destination_context_uses_manual_artifact_names():
    destination_context = swipe_activity._build_swipe_stage1_destination_context(
        destination_type_slug="pre-sales",
        resolved_destination_url="https://example.com/presell",
        gemini_rag_doc_keys=[
            "swipe_stage1_campaign_asset_brief",
            "swipe_stage1_campaign_loaded_copy",
            "swipe_stage1_campaign_creative_context",
        ],
    )

    assert destination_context is not None
    assert "Destination page type: Pre-Sales Landing Page (pre-sales)" in destination_context
    assert "Resolved destination URL: https://example.com/presell" in destination_context
    assert "Swipe Stage1 Campaign Asset Brief" in destination_context
    assert "Swipe Stage1 Campaign Loaded Copy" in destination_context
    assert "Swipe Stage1 Campaign Creative Context" in destination_context
    assert "presell or pre-sales page content" in destination_context
    assert "pull it from those artifacts instead of inventing it" in destination_context


def test_build_swipe_stage1_destination_context_uses_strategy_artifact_names():
    destination_context = swipe_activity._build_swipe_stage1_destination_context(
        destination_type_slug="sales",
        resolved_destination_url=None,
        gemini_rag_doc_keys=[
            "swipe_stage1_campaign_asset_brief",
            "swipe_stage1_strategy_v2_copy",
            "swipe_stage1_strategy_v2_copy_context",
        ],
    )

    assert destination_context is not None
    assert "Destination page type: Sales Page (sales)" in destination_context
    assert "Swipe Stage1 Strategy V2 Copy" in destination_context
    assert "Swipe Stage1 Strategy V2 Copy Context" in destination_context
    assert "sales page content as the post-click continuity anchor" in destination_context


def test_resolve_gemini_store_names_uploads_markdown_bundles(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client, suffix="markdown-bundle"
    )
    workspace_id = client_id
    uploaded: list[dict[str, object]] = []

    monkeypatch.setattr(
        swipe_activity,
        "_load_required_swipe_stage1_rag_docs",
        lambda **_kwargs: _fake_swipe_stage1_rag_docs_with_json_content(),
    )

    def _fake_seed(**kwargs):
        uploaded.append(kwargs)
        return f"fileSearchStores/foundation-store/documents/{kwargs['doc_key']}"

    monkeypatch.setattr(swipe_activity, "ensure_uploaded_to_gemini_file_search", _fake_seed)

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

    brand_foundation = next(
        row for row in uploaded if row["doc_key"] == "swipe_stage1_bundle_brand_foundation"
    )
    bundle_text = brand_foundation["content_bytes"].decode("utf-8")

    assert brand_foundation["mime_type"] == "text/markdown"
    assert brand_foundation["filename"] == "swipe_stage1_bundle_brand_foundation.md"
    assert "# Swipe Stage1 Bundle: Brand Foundation" in bundle_text
    assert "## Swipe Stage1 Client Canon" in bundle_text
    assert '"docKey": "swipe_stage1_client_canon"' in bundle_text
    assert '\\"docKey\\"' not in bundle_text


def test_generate_swipe_image_ad_activity_uses_file_search_tools(monkeypatch):
    captured: dict[str, object] = {}
    captured_calls: list[dict[str, object]] = []

    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            captured_calls.append({"model": model, "contents": contents, "config": config})
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
    monkeypatch.setattr(swipe_activity, "_validate_brief_scope", lambda **_kwargs: _fake_brief_scope())
    monkeypatch.setattr(
        swipe_activity,
        "_extract_brand_context",
        lambda **_kwargs: {
            "client_name": "Brand Name",
            "product_title": "Product Name",
            "canon": {"constraints": {"legal": ["No medical claims"]}},
            "design_system_tokens": {
                "cssVars": {
                    "--font-heading": "Bookmania, 'Times New Roman', serif",
                    "--font-sans": "'Proxima Nova', Helvetica, Arial, sans-serif",
                    "--color-brand": "#C41423",
                }
            },
        },
    )
    monkeypatch.setattr(
        swipe_activity,
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_linked_ad_copy_pack_context",
        lambda **_kwargs: _fake_linked_ad_copy_pack_context(angle="Clinical proof and fast results"),
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
        lambda url, *, max_bytes, timeout_seconds: (
            (b"product-bytes", "image/png")
            if url == "https://example.com/product-1.png"
            else (b"rendered-image-bytes", "image/png")
        ),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_resolve_swipe_stage1_gemini_file_search_context",
        lambda **_kwargs: (
            ["fileSearchStores/context-store"],
            [
                "swipe_stage1_campaign_asset_brief",
                "swipe_stage1_campaign_loaded_copy",
                "swipe_stage1_campaign_creative_context",
            ],
            [],
            [],
        ),
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
            "creative_generation_batch_id": "batch-1",
            "creative_generation_plan_artifact_id": "plan-artifact-1",
            "creative_generation_plan_item_id": "plan-item-1",
            "ad_copy_pack_artifact_id": "copy-artifact-1",
            "ad_copy_pack_id": "copy-pack-1",
            "model": "models/gemini-2.5-flash",
            "count": 1,
            "aspect_ratio": "1:1",
            "render_model_id": "gemini-3-pro-image-preview",
        }
    )

    assert result["asset_ids"] == ["asset-1"]
    assert result["stores_attached"] == 1
    assert len(captured_calls) == 2
    assert captured_calls[0]["model"] == "gemini-2.5-flash"
    assert captured["creative_payload_count"] == 1
    assert captured["creative_payload_reference_asset_ids"] == ["local-product-asset-1"]
    assert captured["creative_payload_reference_image_urls"] == []
    assert captured["creative_payload_model_id"] == "models/gemini-3-pro-image-preview"
    prompt_input = captured_calls[0]["contents"][0]
    assert isinstance(prompt_input, str)
    assert "Brand name: [BRAND_NAME]" in prompt_input
    assert "Product: [PRODUCT]" in prompt_input
    assert "RUNTIME INPUTS (INJECTED)" in prompt_input
    assert "Brand: Brand Name" in prompt_input
    assert "Angle: Clinical proof and fast results" in prompt_input
    assert (
        "Brand colors/fonts: Heading font: Bookmania, 'Times New Roman', serif | "
        "Body font: 'Proxima Nova', Helvetica, Arial, sans-serif | Brand color: #C41423"
    ) in prompt_input
    assert "Destination page type: Sales Page (sales)" in prompt_input
    assert "Swipe Stage1 Campaign Asset Brief" in prompt_input
    assert "Swipe Stage1 Campaign Loaded Copy" in prompt_input
    assert "Swipe Stage1 Campaign Creative Context" in prompt_input
    assert "pull it from those artifacts instead of inventing it" in prompt_input
    assert "Competitor swipe image is attached as image input." in prompt_input
    assert len(captured_calls[0]["contents"]) == 3
    rendered_copy_prompt = captured_calls[1]["contents"][0]
    assert isinstance(rendered_copy_prompt, str)
    assert "The attached image is the final generated ad asset for this specific creative." in rendered_copy_prompt
    assert "Requirement Copy Baseline" in rendered_copy_prompt
    assert captured_calls[1]["contents"][1] == "Ad Image or Video asset:"
    assert _part_data(captured_calls[1]["contents"][2]) == b"rendered-image-bytes"
    extra_ai_metadata = captured["extra_ai_metadata"]
    assert extra_ai_metadata["swipeCopyPipelineVersion"] == 2
    assert extra_ai_metadata["swipeCopyInputs"]["adImageOrVideo"]["sourceKind"] == "rendered_output"
    assert extra_ai_metadata["swipeCopyInputs"]["adImageOrVideo"]["sourceUrl"] == "https://example.com/generated.png"
    assert extra_ai_metadata["swipeCopyInputs"]["sourceSwipe"]["sourceUrl"] == "https://example.com/swipe.png"
    assert "swipeCopyPromptText" in extra_ai_metadata
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
    assert extra_ai_metadata["creativeGenerationBatchId"] == "batch-1"
    assert extra_ai_metadata["creativeGenerationPlanArtifactId"] == "plan-artifact-1"
    assert extra_ai_metadata["creativeGenerationPlanItemId"] == "plan-item-1"
    assert extra_ai_metadata["adCopyPackArtifactId"] == "copy-artifact-1"
    assert extra_ai_metadata["adCopyPackId"] == "copy-pack-1"
    config = captured_calls[0]["config"]
    assert hasattr(config, "tools")
    assert len(config.tools) == 1
    file_search_tool = config.tools[0]
    assert file_search_tool.file_search.file_search_store_names == ["fileSearchStores/context-store"]


def test_call_gemini_generate_content_with_retries_treats_daily_quota_as_non_retryable():
    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: "
                "generativelanguage.googleapis.com/generate_requests_per_model_per_day, "
                "quotaId=GenerateRequestsPerDayPerProjectPerModel. Please retry in 5h."
            )

    client = SimpleNamespace(models=_FakeModels())

    with pytest.raises(ApplicationError, match="Swipe prompt generation failed with Gemini") as exc_info:
        swipe_activity._call_gemini_generate_content_with_retries(
            gemini_client=client,
            model="gemini-3.1-pro-preview",
            contents=["prompt"],
            config=SimpleNamespace(),
            operation_name="Swipe prompt generation",
            file_search_model_error_message="File Search model mismatch.",
        )

    assert exc_info.value.type == "GeminiQuotaExceeded"
    assert exc_info.value.non_retryable is True


def test_call_swipe_copy_gemini_json_message_repairs_literal_newlines_in_json_strings(monkeypatch):
    raw_response = """```json
{
  "selectedVariation": "Variation 1",
  "formattedVariationsMarkdown": "```text
**Variation 1**

**Primary Text:** This keeps the blind-angle hook intact.
**Headline:** Fix the routine bottleneck
**Description:** Learn what changes the pattern
**CTA:** Learn More
```",
  "metaPrimaryText": "Clinical proof and fast results with a compliant curiosity-led hook.",
  "metaHeadline": "Fix the routine bottleneck",
  "metaDescription": "Learn what changes the pattern",
  "metaCta": "Learn More",
  "claimsGuardrails": ["Do not promise medical outcomes."]
}
```"""

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            return SimpleNamespace(
                parsed=None,
                text=raw_response,
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=["fileSearchStores/context-store"],
        max_tokens=2048,
        temperature=0.2,
        response_schema=None,
    )

    assert result["parsed"]["selectedVariation"] == "Variation 1"
    assert "Variation 1" in result["parsed"]["formattedVariationsMarkdown"]
    assert result["parsed"]["metaHeadline"] == "Fix the routine bottleneck"
    assert result["output_tokens"] == 222


def test_call_swipe_copy_gemini_json_message_repairs_truncated_json_strings(monkeypatch):
    raw_response = """```json
{
  "selectedVariation": "Variation 1",
  "formattedVariationsMarkdown": "```text
**Variation 1**

**Primary Text:** Read this before mixing supplements with prescriptions.
```"""

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            return SimpleNamespace(
                parsed=None,
                text=raw_response,
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=["fileSearchStores/context-store"],
        max_tokens=2048,
        temperature=0.2,
        response_schema=None,
    )

    assert result["parsed"]["selectedVariation"] == "Variation 1"
    assert "Read this before mixing" in result["parsed"]["formattedVariationsMarkdown"]
    assert result["output_tokens"] == 222


def test_call_swipe_copy_gemini_json_message_repairs_truncated_json_with_opening_fence_only(monkeypatch):
    raw_response = """```json
{
  "selectedVariation": "Variation 1: The Warning / Shocking Reveal",
  "formattedVariationsMarkdown": "```text\\n**Variation 1: The Warning / Shocking Reveal**\\n\\n**Primary Text:** You see ads for natural remedies promising to turn back the clock.\\n\\nBut if you take daily prescriptions, mixing th"""

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            return SimpleNamespace(
                parsed=None,
                text=raw_response,
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=["fileSearchStores/context-store"],
        max_tokens=2048,
        temperature=0.2,
        response_schema=None,
    )

    assert result["parsed"]["selectedVariation"] == "Variation 1: The Warning / Shocking Reveal"
    assert "mixing th" in result["parsed"]["formattedVariationsMarkdown"]
    assert result["output_tokens"] == 222


def test_call_swipe_copy_gemini_json_message_repairs_truncated_json_with_trailing_comma(monkeypatch):
    raw_response = """```json
{
  "passes": false,
  "violations": [
    "Reveals the specific drug (gabapentin) and the exact nature of the safety gap."
  ],
"""

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            return SimpleNamespace(
                parsed=None,
                text=raw_response,
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=[],
        max_tokens=2048,
        temperature=0.0,
        response_schema={
            "type": "object",
            "properties": {
                "passes": {"type": "boolean"},
                "violations": {"type": "array", "items": {"type": "string"}},
                "retryFeedback": {"type": ["string", "null"]},
            },
            "required": ["passes", "violations", "retryFeedback"],
        },
    )

    assert result["parsed"]["passes"] is False
    assert result["parsed"]["violations"] == [
        "Reveals the specific drug (gabapentin) and the exact nature of the safety gap."
    ]
    assert result["output_tokens"] == 222


def test_call_swipe_copy_gemini_json_message_extracts_partial_payload_before_truncated_next_key(monkeypatch):
    raw_response = """```json
{
  "selectedVariation": "Variation 1: The 'Deal With It' Warning",
  "formattedVariationsMarkdown": "```text\\n**Variation 1: The 'Deal With It' Warning**\\n\\n**Primary Text:**\\nIf your doctor just told you to \\"deal with it\\" or handed you another prescription you didn't ask for, read this.\\n\\nSee why so many are using this to finally take back control.",
  "metaPrim
"""

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            return SimpleNamespace(
                parsed=None,
                text=raw_response,
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=["fileSearchStores/context-store"],
        max_tokens=2048,
        temperature=0.2,
        response_schema=None,
    )

    assert result["parsed"]["selectedVariation"] == "Variation 1: The 'Deal With It' Warning"
    assert 'told you to "deal with it"' in result["parsed"]["formattedVariationsMarkdown"]
    assert "metaPrimaryText" not in result["parsed"]
    assert result["output_tokens"] == 222


def test_call_swipe_copy_gemini_json_message_strips_invalid_apostrophe_escapes(monkeypatch):
    raw_response = """```json
{
  "selectedVariation": "Variation 1",
  "formattedVariationsMarkdown": "**Variation 1**\\nDon\\'t mix supplements blindly."
}
```"""

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            return SimpleNamespace(
                parsed=None,
                text=raw_response,
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=["fileSearchStores/context-store"],
        max_tokens=2048,
        temperature=0.2,
        response_schema=None,
    )

    assert result["parsed"]["formattedVariationsMarkdown"] == "**Variation 1**\nDon't mix supplements blindly."
    assert result["output_tokens"] == 222


def test_call_swipe_copy_gemini_json_message_retries_retryable_gemini_errors(monkeypatch):
    sleep_calls: list[float] = []

    class _FakeGeminiError(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.status_code = 429
            self.response = SimpleNamespace(headers={"Retry-After": "3"})

    class _FakeModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *, model, contents, config):
            self.calls += 1
            if self.calls == 1:
                raise _FakeGeminiError(
                    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Failed to embed content.'}}"
                )
            return SimpleNamespace(
                parsed={
                    "selectedVariation": "Variation 1",
                    "formattedVariationsMarkdown": "```text\n**Variation 1**\n```",
                    "metaPrimaryText": "Primary text",
                    "metaHeadline": "Headline",
                    "metaDescription": "Description",
                    "metaCta": "Learn More",
                    "claimsGuardrails": ["Do not promise medical outcomes."],
                },
                text="",
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())
    monkeypatch.setattr(swipe_activity, "_SWIPE_COPY_GEMINI_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(swipe_activity.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=["fileSearchStores/context-store"],
        max_tokens=2048,
        temperature=0.2,
        response_schema=None,
    )

    assert result["parsed"]["metaHeadline"] == "Headline"
    assert result["output_tokens"] == 222
    assert sleep_calls == [3.0]


def test_call_swipe_copy_gemini_json_message_uses_high_demand_backoff_for_503(monkeypatch):
    sleep_calls: list[float] = []

    class _FakeGeminiError(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.status_code = 503

    class _FakeModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *, model, contents, config):
            self.calls += 1
            if self.calls == 1:
                raise _FakeGeminiError(
                    "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. "
                    "Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}"
                )
            return SimpleNamespace(
                parsed={
                    "selectedVariation": "Variation 1",
                    "formattedVariationsMarkdown": "```text\n**Variation 1**\n```",
                    "metaPrimaryText": "Primary text",
                    "metaHeadline": "Headline",
                    "metaDescription": "Description",
                    "metaCta": "Learn More",
                    "claimsGuardrails": ["Do not promise medical outcomes."],
                },
                text="",
                usage_metadata=SimpleNamespace(prompt_token_count=111, candidates_token_count=222),
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())
    monkeypatch.setattr(swipe_activity, "_SWIPE_COPY_GEMINI_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(swipe_activity, "_SWIPE_GEMINI_GENERATE_CONTENT_SEMAPHORE_STATE", None)
    monkeypatch.setattr(swipe_activity.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = swipe_activity._call_swipe_copy_gemini_json_message(
        model="models/gemini-2.5-flash",
        system_instruction="Return JSON only.",
        contents=["prompt"],
        store_names=["fileSearchStores/context-store"],
        max_tokens=2048,
        temperature=0.2,
        response_schema=None,
    )

    assert result["parsed"]["metaHeadline"] == "Headline"
    assert sleep_calls == [15.0]


def test_call_swipe_copy_gemini_json_message_raises_after_retry_budget_exhausted(monkeypatch):
    sleep_calls: list[float] = []

    class _FakeGeminiError(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.status_code = 429

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            raise _FakeGeminiError(
                "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Failed to embed content.'}}"
            )

    class _FakeGeminiClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(swipe_activity, "_ensure_gemini_client", lambda: _FakeGeminiClient())
    monkeypatch.setattr(swipe_activity, "_SWIPE_COPY_GEMINI_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(swipe_activity.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    with pytest.raises(RuntimeError, match="Swipe Stage 1 copy generation failed with Gemini: 429 RESOURCE_EXHAUSTED"):
        swipe_activity._call_swipe_copy_gemini_json_message(
            model="models/gemini-2.5-flash",
            system_instruction="Return JSON only.",
            contents=["prompt"],
            store_names=["fileSearchStores/context-store"],
            max_tokens=2048,
            temperature=0.2,
            response_schema=None,
        )

    assert sleep_calls == [2.0]


def test_load_swipe_product_image_profiles_reads_catalog(tmp_path, monkeypatch):
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(
        '{"entries":[{"filename":"7.png","requires_product_image":true}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("SWIPE_PRODUCT_IMAGE_PROFILES_PATH", str(profile_path))
    monkeypatch.setattr(swipe_activity, "_SWIPE_PRODUCT_IMAGE_PROFILE_CACHE", None)

    assert swipe_activity._load_swipe_product_image_profiles() == {"7.png": True}


def test_generate_swipe_stage1_copy_pack_retries_when_meta_fields_missing(monkeypatch):
    retry_feedbacks: list[str | None] = []
    responses = iter(
        [
            {
                "parsed": {
                    "selectedVariation": "Variation 1",
                    "formattedVariationsMarkdown": "```text\n**Variation 1**\n```",
                    "claimsGuardrails": ["Do not promise medical outcomes."],
                },
                "text": "",
                "stop_reason": "STOP",
                "output_tokens": 111,
            },
            {
                "parsed": _fake_swipe_copy_pack_parsed(angle="Clinical proof"),
                "text": "",
                "stop_reason": "STOP",
                "output_tokens": 222,
            },
        ]
    )

    def _fake_build_prompt(*, retry_feedback=None, **_kwargs):
        retry_feedbacks.append(retry_feedback)
        return "prompt"

    monkeypatch.setattr(swipe_activity, "_build_swipe_copy_stage1_prompt", _fake_build_prompt)
    monkeypatch.setattr(swipe_activity, "_resolve_destination_type", lambda **_kwargs: "presell")
    monkeypatch.setattr(
        swipe_activity,
        "_call_swipe_copy_gemini_json_message",
        lambda **_kwargs: next(responses),
    )
    monkeypatch.setattr(
        swipe_activity,
        "_validate_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        swipe_activity,
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
    )

    validated, response, model = swipe_activity._generate_swipe_stage1_copy_pack(
        session=object(),
        brief={"id": "brief-1"},
        requirement_index=0,
        requirement={
            "channel": "meta",
            "format": "image",
            "angle": "Clinical proof",
            "hook": "Hidden issue",
            "funnelStage": "mid",
        },
        copy_model="models/gemini-2.5-flash",
        gemini_store_names=["fileSearchStores/context-store"],
        swipe_bytes=b"image-bytes",
        swipe_mime_type="image/png",
        swipe_source_url="https://example.com/swipe.png",
        swipe_source_label="10.png",
        product_prompt_image_bytes=None,
        product_prompt_image_mime_type=None,
    )

    assert validated.meta_primary_text == "Clinical proof with a compliant curiosity-led hook."
    assert response["output_tokens"] == 222
    assert model == "models/gemini-2.5-flash"
    assert retry_feedbacks[0] is None
    assert "missing required Meta fields" in (retry_feedbacks[1] or "")
    assert "metaPrimaryText" in (retry_feedbacks[1] or "")


def test_generate_swipe_stage1_copy_pack_hydrates_meta_fields_from_selected_variation_markdown(monkeypatch):
    retry_feedbacks: list[str | None] = []

    def _fake_build_prompt(*, retry_feedback=None, **_kwargs):
        retry_feedbacks.append(retry_feedback)
        return "prompt"

    monkeypatch.setattr(swipe_activity, "_build_swipe_copy_stage1_prompt", _fake_build_prompt)
    monkeypatch.setattr(swipe_activity, "_resolve_destination_type", lambda **_kwargs: "presell")
    monkeypatch.setattr(
        swipe_activity,
        "_call_swipe_copy_gemini_json_message",
        lambda **_kwargs: {
            "parsed": {
                "selectedVariation": "Variation 1: The Dismissal Warning",
                "formattedVariationsMarkdown": (
                    "```text\n"
                    "**Variation 1: The Dismissal Warning**\n\n"
                    "**Primary Text:**\n"
                    "They tell you to just suffer through the sleepless nights and hot flashes.\n\n"
                    "Or worse, they hand you a heavy prescription without running a single test.\n\n"
                    "But if you are looking for natural relief, there is a glaring safety gap they aren't warning you about.\n\n"
                    "Discover the missing piece that finally puts you back in control.\n\n"
                    "Tap below to see what they left out.\n\n"
                    "**Headline:** The Missing Piece For Perimenopause Relief\n"
                    "**Description:** Read the breaking reveal before it's gone.\n"
                    "**CTA:** Learn More\n\n"
                    "---\n\n"
                    "**Variation 2: The Heavy Prescription Leak**\n"
                    "```"
                ),
                "claimsGuardrails": ["Do not promise medical outcomes."],
            },
            "text": "",
            "stop_reason": "STOP",
            "output_tokens": 333,
        },
    )
    monkeypatch.setattr(
        swipe_activity,
        "_validate_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        swipe_activity,
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
    )

    validated, response, model = swipe_activity._generate_swipe_stage1_copy_pack(
        session=object(),
        brief={"id": "brief-1"},
        requirement_index=0,
        requirement={
            "channel": "facebook",
            "format": "image_ad",
            "angle": "Doctor-dismissal backlash",
            "hook": "Hidden issue",
            "funnelStage": "mid",
        },
        copy_model="models/gemini-2.5-flash",
        gemini_store_names=["fileSearchStores/context-store"],
        swipe_bytes=b"image-bytes",
        swipe_mime_type="image/png",
        swipe_source_url="https://example.com/swipe.png",
        swipe_source_label="10.png",
        product_prompt_image_bytes=None,
        product_prompt_image_mime_type=None,
    )

    assert validated.meta_primary_text == (
        "They tell you to just suffer through the sleepless nights and hot flashes.\n\n"
        "Or worse, they hand you a heavy prescription without running a single test.\n\n"
        "But if you are looking for natural relief, there is a glaring safety gap they aren't warning you about.\n\n"
        "Discover the missing piece that finally puts you back in control.\n\n"
        "Tap below to see what they left out."
    )
    assert validated.meta_headline == "The Missing Piece For Perimenopause Relief"
    assert validated.meta_description == "Read the breaking reveal before it's gone."
    assert validated.meta_cta == "Learn More"
    assert response["output_tokens"] == 333
    assert model == "models/gemini-2.5-flash"
    assert retry_feedbacks == [None]


def test_extract_meta_fields_from_selected_variation_markdown_accepts_meta_labels_and_variation_prefix():
    extracted = swipe_activity._extract_meta_fields_from_selected_variation_markdown(
        formatted_variations_markdown=(
            "```text\n"
            "- **Variation 1: The Dismissal Warning**\n\n"
            "- **Meta Primary Text:**\n"
            "They brushed off the question like it did not matter.\n\n"
            "Now there is one detail she refuses to ignore.\n\n"
            "`Meta Headline:` What They Refused To Look At\n"
            "`Meta Description:` Read the warning before it disappears.\n"
            "`Meta CTA:` Learn More\n\n"
            "---\n\n"
            "**Variation 2: Another Angle**\n"
            "```"
        ),
        selected_variation="Variation 1",
    )

    assert extracted == {
        "metaPrimaryText": (
            "They brushed off the question like it did not matter.\n\n"
            "Now there is one detail she refuses to ignore."
        ),
        "metaHeadline": "What They Refused To Look At",
        "metaDescription": "Read the warning before it disappears.",
        "metaCta": "Learn More",
    }


def test_generate_swipe_stage1_copy_pack_hydrates_meta_alias_fields_before_validation(monkeypatch):
    monkeypatch.setattr(swipe_activity, "_build_swipe_copy_stage1_prompt", lambda **_kwargs: "prompt")
    monkeypatch.setattr(swipe_activity, "_resolve_destination_type", lambda **_kwargs: "presell")
    monkeypatch.setattr(
        swipe_activity,
        "_call_swipe_copy_gemini_json_message",
        lambda **_kwargs: {
            "parsed": {
                "selectedVariation": "Variation 1",
                "formattedVariationsMarkdown": (
                    "```text\n"
                    "**Variation 1: The Dismissal Warning**\n\n"
                    "**Primary Text:**\n"
                    "They dismissed the concern before they even looked closer.\n\n"
                    "Now there is one question she wishes she asked sooner.\n\n"
                    "**Headline:** The Question They Skipped\n"
                    "**Description:** Read the warning before it's gone.\n"
                    "**CTA:** Learn More\n"
                    "```"
                ),
                "primaryText": (
                    "They dismissed the concern before they even looked closer.\n\n"
                    "Now there is one question she wishes she asked sooner."
                ),
                "headline": "The Question They Skipped",
                "description": "Read the warning before it's gone.",
                "cta": "Learn More",
                "claimsGuardrails": ["Do not promise medical outcomes."],
            },
            "text": "",
            "stop_reason": "STOP",
            "output_tokens": 444,
        },
    )
    monkeypatch.setattr(
        swipe_activity,
        "_validate_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        swipe_activity,
        "_audit_swipe_copy_blind_angle_blackout",
        lambda **_kwargs: (True, None),
    )

    validated, response, model = swipe_activity._generate_swipe_stage1_copy_pack(
        session=object(),
        brief={"id": "brief-1"},
        requirement_index=0,
        requirement={
            "channel": "facebook",
            "format": "image_ad",
            "angle": "Doctor-dismissal backlash",
            "hook": "Hidden issue",
            "funnelStage": "mid",
        },
        copy_model="models/gemini-2.5-flash",
        gemini_store_names=["fileSearchStores/context-store"],
        swipe_bytes=b"image-bytes",
        swipe_mime_type="image/png",
        swipe_source_url="https://example.com/swipe.png",
        swipe_source_label="10.png",
        product_prompt_image_bytes=None,
        product_prompt_image_mime_type=None,
    )

    assert validated.meta_primary_text == (
        "They dismissed the concern before they even looked closer.\n\n"
        "Now there is one question she wishes she asked sooner."
    )
    assert validated.meta_headline == "The Question They Skipped"
    assert validated.meta_description == "Read the warning before it's gone."
    assert validated.meta_cta == "Learn More"
    assert response["output_tokens"] == 444
    assert model == "models/gemini-2.5-flash"


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
    monkeypatch.setattr(swipe_activity, "_validate_brief_scope", lambda **_kwargs: _fake_brief_scope())
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
        "_resolve_linked_ad_copy_pack_context",
        lambda **_kwargs: _fake_linked_ad_copy_pack_context(),
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
        lambda url, *, max_bytes, timeout_seconds: (
            (_ for _ in ()).throw(
                AssertionError("product reference image should not be downloaded when no product assets are present")
            )
            if url != "https://example.com/generated.png"
            else (b"rendered-image-bytes", "image/png")
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
    assert len(captured["contents"]) == 3


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
    monkeypatch.setattr(swipe_activity, "_validate_brief_scope", lambda **_kwargs: _fake_brief_scope())
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
        "_resolve_linked_ad_copy_pack_context",
        lambda **_kwargs: _fake_linked_ad_copy_pack_context(),
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
        lambda url, *, max_bytes, timeout_seconds: (
            (_ for _ in ()).throw(
                AssertionError("product image should not be downloaded when swipe_requires_product_image=false")
            )
            if url != "https://example.com/generated.png"
            else (b"rendered-image-bytes", "image/png")
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
    assert len(captured["contents"]) == 3


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
                    "requirements": [
                        {
                            "channel": "meta",
                            "format": "image",
                            "destinationType": "sales",
                        }
                    ],
                    "constraints": [],
                    "toneGuidelines": [],
                    "visualGuidelines": [],
                },
            "brief-artifact-id",
        ),
    )
    monkeypatch.setattr(swipe_activity, "_validate_brief_scope", lambda **_kwargs: _fake_brief_scope())
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
