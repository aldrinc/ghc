from __future__ import annotations

import hashlib

import pytest

from app.strategy_v2.contracts import ProductBriefStage0, ProductBriefStage2
from app.strategy_v2.errors import StrategyV2MissingContextError
from app.strategy_v2.prompt_runtime import (
    render_prompt_template,
    resolve_prompt_asset,
)
from app.strategy_v2.translation import transform_step4_entries_to_agent2_corpus
from app.temporal.activities import strategy_v2_activities


def test_resolve_prompt_asset_returns_stable_metadata() -> None:
    asset = resolve_prompt_asset(
        pattern="Copywriting Agent */04_prompt_templates/headline_generation.md",
        context="headline template",
    )
    assert asset.relative_path.endswith("04_prompt_templates/headline_generation.md")
    assert asset.text.startswith("# Prompt Template: Headline Generation")
    expected_sha = hashlib.sha256(asset.absolute_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    assert asset.sha256 == expected_sha


def test_render_prompt_template_requires_all_placeholders() -> None:
    template = "Hello {{NAME}} from {{PLACE}}"
    with pytest.raises(StrategyV2MissingContextError):
        render_prompt_template(
            template=template,
            variables={"NAME": "Alice"},
            context="unit-test-template",
        )


def test_run_prompt_json_object_returns_parsed_payload_and_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    asset = resolve_prompt_asset(
        pattern="Copywriting Agent */04_prompt_templates/promise_contract_extraction.md",
        context="promise template",
    )

    monkeypatch.setattr(
        strategy_v2_activities,
        "_llm_generate_text",
        lambda **_kwargs: '{"loop_question":"What?","specific_promise":"Specific promise",'
        '"delivery_test":"Test body delivery","minimum_delivery":"Section 1"}',
    )

    parsed, raw_output, provenance = strategy_v2_activities._run_prompt_json_object(
        asset=asset,
        context="strategy_v2.copy.promise_contract",
        model="gpt-5.2-2025-12-11",
        runtime_instruction="Return promise contract JSON.",
        schema_name="strategy_v2_copy_promise_contract_test",
        schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "loop_question": {"type": "string"},
                "specific_promise": {"type": "string"},
                "delivery_test": {"type": "string"},
                "minimum_delivery": {"type": "string"},
            },
            "required": ["loop_question", "specific_promise", "delivery_test", "minimum_delivery"],
        },
        use_reasoning=False,
        use_web_search=False,
    )

    assert parsed["loop_question"] == "What?"
    assert "specific_promise" in parsed
    assert raw_output.startswith("{")
    assert provenance["prompt_path"].endswith("04_prompt_templates/promise_contract_extraction.md")
    assert provenance["prompt_sha256"]
    assert provenance["model_name"] == "gpt-5.2-2025-12-11"


def test_run_prompt_json_object_persists_claude_conversation_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    asset = resolve_prompt_asset(
        pattern="Copywriting Agent */04_prompt_templates/promise_contract_extraction.md",
        context="promise template",
    )
    captured_claude_messages: dict[str, object] = {}

    def _fake_llm_generate_text(**kwargs):
        captured_claude_messages["messages"] = kwargs.get("claude_messages")
        return (
            '{"loop_question":"What?","specific_promise":"Specific promise",'
            '"delivery_test":"Test body delivery","minimum_delivery":"Section 1"}'
        )

    monkeypatch.setattr(strategy_v2_activities, "_llm_generate_text", _fake_llm_generate_text)

    conversation_messages: list[dict[str, object]] = [
        {"role": "user", "content": [{"type": "text", "text": "Initial draft request."}]},
        {"role": "assistant", "content": [{"type": "text", "text": '{"markdown":"draft"}'}]},
    ]
    strategy_v2_activities._run_prompt_json_object(
        asset=asset,
        context="strategy_v2.copy.promise_contract",
        model="claude-haiku-4-5-20251001",
        runtime_instruction="Return promise contract JSON.",
        schema_name="strategy_v2_copy_promise_contract_test",
        schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "loop_question": {"type": "string"},
                "specific_promise": {"type": "string"},
                "delivery_test": {"type": "string"},
                "minimum_delivery": {"type": "string"},
            },
            "required": ["loop_question", "specific_promise", "delivery_test", "minimum_delivery"],
        },
        use_reasoning=False,
        use_web_search=False,
        conversation_messages=conversation_messages,
    )

    sent_messages = captured_claude_messages.get("messages")
    assert isinstance(sent_messages, list)
    assert len(sent_messages) == 3
    assert sent_messages[-1]["role"] == "user"
    assert len(conversation_messages) == 4
    assert conversation_messages[-2]["role"] == "user"
    assert conversation_messages[-1]["role"] == "assistant"


def test_transform_step4_entries_to_agent2_corpus_maps_dimensions() -> None:
    corpus = transform_step4_entries_to_agent2_corpus(
        [
            {
                "source": "reddit.com/r/example",
                "category": "C",
                "emotion": "hope",
                "buyer_stage": "problem aware",
                "segment_hint": "caregivers",
                "quote": "I want a plan that finally works.",
            },
            {
                "source": "forum.example.com/thread-1",
                "category": "H",
                "emotion": "frustration",
                "buyer_stage": "solution aware",
                "segment_hint": "parents",
                "quote": "Nothing I tried fixed the nightly issue.",
            },
        ]
    )

    assert len(corpus) == 2
    first = corpus[0]
    assert first["desired_outcome"] != "NONE"
    assert first["emotional_valence"] == "HOPE"
    assert first["flags"] == ["EXISTING_CORPUS"]


def test_competitor_analysis_schema_uses_strict_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_schema: dict[str, object] = {}

    def _fake_run_prompt_json_object(**kwargs):
        captured_schema.update(kwargs["schema"])
        return (
            {
                "asset_observation_sheets": [
                    {
                        "asset_id": "asset-1",
                        "competitor_name": "Competitor A",
                        "brand": "Brand A",
                        "primary_angle": "angle",
                        "core_claim": "claim",
                        "implied_mechanism": "mechanism",
                        "target_segment_description": "segment",
                        "hook_type": "hook",
                        "source_ref": "https://example.com/a",
                    }
                ],
                "compliance_landscape": {"red_pct": 0.1, "yellow_pct": 0.2, "overall": {"red_pct": 0.1, "yellow_pct": 0.2}},
                "saturation_map": [],
            },
            "{}",
            {},
        )

    monkeypatch.setattr(strategy_v2_activities, "_run_prompt_json_object", _fake_run_prompt_json_object)

    strategy_v2_activities._generate_competitor_analysis_json(
        stage0=ProductBriefStage0.model_validate(
            {
                "schema_version": "2.0.0",
                "stage": 0,
                "product_name": "Test Product",
                "description": "Desc",
                "price": "$49",
                "competitor_urls": ["https://seed.example"],
                "product_customizable": False,
            }
        ),
        category_niche="Herbal Remedies",
        step1_summary="summary",
        step1_content="content",
        confirmed_competitor_assets=[
            "https://a.example",
            "https://b.example",
            "https://c.example",
        ],
    )

    assert captured_schema["required"] == ["asset_observation_sheets", "compliance_landscape", "saturation_map"]
    properties = captured_schema["properties"]
    assert isinstance(properties, dict)
    sheets = properties["asset_observation_sheets"]["items"]
    compliance = properties["compliance_landscape"]
    saturation_item = properties["saturation_map"]["items"]
    assert sheets["required"] == [
        "asset_id",
        "competitor_name",
        "brand",
        "primary_angle",
        "core_claim",
        "implied_mechanism",
        "target_segment_description",
        "hook_type",
        "source_ref",
    ]
    assert compliance["required"] == ["red_pct", "yellow_pct", "overall"]
    assert compliance["properties"]["overall"]["required"] == ["red_pct", "yellow_pct"]
    assert saturation_item["required"] == ["angle", "angle_name", "driver", "status", "competitor_count"]


def test_json_schema_response_format_enforces_openai_strict_rules() -> None:
    response_format = strategy_v2_activities._json_schema_response_format(
        name="strategy_v2_schema_guard_test",
        schema={
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "alpha": {"type": "string"},
                "nested": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "inner": {"type": "string"},
                    },
                },
                "freeform": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            "required": ["alpha"],
        },
    )
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["alpha", "nested", "freeform"]
    nested = schema["properties"]["nested"]
    assert nested["additionalProperties"] is False
    assert nested["required"] == ["inner"]
    freeform = schema["properties"]["freeform"]
    assert freeform["additionalProperties"] is False
    assert freeform["properties"] == {}
    assert freeform["required"] == []


def _build_stage2_with_price(price: str) -> ProductBriefStage2:
    return ProductBriefStage2.model_validate(
        {
            "schema_version": "2.0.0",
            "stage": 2,
            "product_name": "Test Product",
            "description": "Test description",
            "price": price,
            "competitor_urls": ["https://offer.example"],
            "product_customizable": True,
            "category_niche": "Health & Wellness",
            "market_maturity_stage": "Growth",
            "primary_segment": {
                "name": "Safety-focused caregivers",
                "size_estimate": "Large",
                "key_differentiator": "High risk sensitivity",
            },
            "bottleneck": "Trust",
            "positioning_gaps": ["Clear contraindication flow"],
            "competitor_count_validated": 3,
            "primary_icps": ["Caregivers"],
            "selected_angle": {
                "angle_id": "A1",
                "angle_name": "Safety-first buying",
                "definition": {
                    "who": "Caregivers",
                    "pain_desire": "Avoid unsafe recommendations",
                    "mechanism_why": "Current offers skip risk checks",
                    "belief_shift": {
                        "before": "Generic guides are enough",
                        "after": "Safety checks are required",
                    },
                    "trigger": "conflicting online advice",
                },
                "evidence": {
                    "supporting_voc_count": 5,
                    "top_quotes": [
                        {
                            "voc_id": "V1",
                            "quote": "I need a safety checklist.",
                            "adjusted_score": 72.0,
                        }
                    ],
                    "triangulation_status": "DUAL",
                    "velocity_status": "STEADY",
                    "contradiction_count": 0,
                },
                "hook_starters": [
                    {
                        "visual": "Checklist by supplement bottles",
                        "opening_line": "Most guides skip interaction warnings.",
                        "lever": "risk reduction",
                    }
                ],
            },
        }
    )


def test_resolve_price_from_reference_urls_prefers_offer_price_over_shipping(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __init__(self, html: str) -> None:
            self._html = html

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return self._html.encode("utf-8")

    def _fake_urlopen(_request, timeout: int = 0) -> _FakeResponse:
        assert timeout == 20
        return _FakeResponse(
            "<html><body>"
            "<p>Shipping is only $9.99 today</p>"
            "<p>Secure your copy now only $37</p>"
            "</body></html>"
        )

    monkeypatch.setattr(strategy_v2_activities.urllib.request, "urlopen", _fake_urlopen)
    price = strategy_v2_activities._resolve_price_from_reference_urls(urls=["https://offer.example"])
    assert price == "$37"


def test_map_offer_pipeline_input_with_price_resolution_retries_when_price_is_tbd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake_map_offer_pipeline_input(**kwargs):
        stage2 = kwargs["stage2"]
        calls.append(stage2.price)
        if stage2.price == "TBD":
            raise StrategyV2MissingContextError(
                "Unable to parse numeric price for Offer pipeline input mapping. "
                "Remediation: provide stage2.price in a parseable format like '$49' or '49.99'."
            )
        return {"price_used": stage2.price}

    monkeypatch.setattr(strategy_v2_activities, "map_offer_pipeline_input", _fake_map_offer_pipeline_input)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_resolve_price_from_reference_urls",
        lambda *, urls: "$37",
    )

    stage2 = _build_stage2_with_price("TBD")
    result = strategy_v2_activities._map_offer_pipeline_input_with_price_resolution(
        stage2=stage2,
        selected_angle_payload=stage2.selected_angle.model_dump(mode="python"),
        competitor_teardowns="{}",
        voc_research="{}",
        purple_ocean_research="{}",
        business_model="info-product",
        funnel_position="top",
        target_platforms=["meta"],
        target_regions=["US"],
        existing_proof_assets=["ugc"],
        brand_voice_notes="direct and practical",
        compliance_sensitivity="medium",
        llm_model="gpt-5.2-2025-12-11",
        max_iterations=2,
        score_threshold=5.5,
    )

    assert calls == ["TBD", "$37"]
    assert result == {"price_used": "$37"}
