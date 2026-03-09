from __future__ import annotations

import ast
import hashlib
from pathlib import Path

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


def test_run_prompt_json_object_rejects_over_budget_gpt_input(monkeypatch: pytest.MonkeyPatch) -> None:
    asset = resolve_prompt_asset(
        pattern="Copywriting Agent */04_prompt_templates/promise_contract_extraction.md",
        context="promise template",
    )

    monkeypatch.setattr(strategy_v2_activities, "_model_prompt_input_token_budget", lambda **_kwargs: 100)
    monkeypatch.setattr(strategy_v2_activities, "_estimate_prompt_input_tokens", lambda _prompt: 101)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_llm_generate_text",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("_llm_generate_text should not be called")),
    )

    with pytest.raises(StrategyV2MissingContextError, match="Prompt input exceeds model budget"):
        strategy_v2_activities._run_prompt_json_object(
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


def test_enforce_strict_openai_json_schema_preserves_explicit_object_constraints() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["dimensions"],
        "properties": {
            "dimensions": {
                "type": "object",
                "additionalProperties": True,
            }
        },
    }

    normalized = strategy_v2_activities._enforce_strict_openai_json_schema(schema)
    dimensions = normalized["properties"]["dimensions"]

    assert dimensions["additionalProperties"] is True
    assert "required" not in dimensions
    assert normalized["required"] == ["dimensions"]


def test_template_payload_validation_errors_remain_retryable() -> None:
    assert (
        strategy_v2_activities._is_non_retryable_sales_payload_failure(
            "TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; errors=problem.title: String should have at least 1 character"
        )
        is False
    )


def test_offer_step05_response_schema_enforces_bounded_compact_contract() -> None:
    schema = strategy_v2_activities._offer_step05_response_schema()
    revision_notes = schema["properties"]["revision_notes"]

    assert revision_notes["maxLength"] == strategy_v2_activities._STEP05_REVISION_NOTES_MAX_CHARS
    assert revision_notes["minLength"] == 1

    variants = schema["properties"]["evaluation"]["properties"]["variants"]
    assert variants["minItems"] == len(strategy_v2_activities._OFFER_VARIANT_IDS)
    assert variants["maxItems"] == len(strategy_v2_activities._OFFER_VARIANT_IDS)

    dimensions = variants["items"]["properties"]["dimensions"]
    assert dimensions["additionalProperties"] is False
    assert dimensions["required"] == list(strategy_v2_activities._OFFER_COMPOSITE_DIMENSIONS)

    for dimension_name in strategy_v2_activities._OFFER_COMPOSITE_DIMENSIONS:
        dimension_schema = dimensions["properties"][dimension_name]
        kill_condition = dimension_schema["properties"]["kill_condition"]
        assert kill_condition["maxLength"] == strategy_v2_activities._STEP05_KILL_CONDITION_MAX_CHARS
        assert dimension_schema["required"] == [
            "raw_score",
            "evidence_quality",
            "kill_condition",
            "competitor_baseline",
        ]


def test_voc_agent00b_response_schema_closes_configuration_objects() -> None:
    schema = strategy_v2_activities._voc_agent00b_response_schema()
    configuration_item = schema["properties"]["configurations"]["items"]

    assert schema["required"] == ["platform_priorities", "configurations", "handoff_block"]
    assert configuration_item["additionalProperties"] is False
    assert configuration_item["required"] == ["config_id", "platform", "mode", "actor_id", "input"]
    assert set(configuration_item["properties"]) == {"config_id", "platform", "mode", "actor_id", "input"}
    assert "metadata" not in configuration_item["properties"]


def test_voc_agent01_file_assessment_schema_discriminates_observe_and_exclude_rows() -> None:
    schema = strategy_v2_activities._VOC_AGENT01_FILE_ASSESSMENT_SCHEMA
    variants = schema["anyOf"]

    assert len(variants) == 3

    exclude_variant = next(
        variant
        for variant in variants
        if variant["properties"]["decision"]["enum"] == ["EXCLUDE"]
    )
    observe_variant = next(
        variant
        for variant in variants
        if variant["properties"]["decision"]["enum"] == ["OBSERVE"]
        and variant["properties"]["include_in_mining_plan"]["enum"] == [False]
    )
    mined_observe_variant = next(
        variant
        for variant in variants
        if variant["properties"]["decision"]["enum"] == ["OBSERVE"]
        and variant["properties"]["include_in_mining_plan"]["enum"] == [True]
    )

    assert exclude_variant["properties"]["url_pattern"]["type"] == "null"
    assert exclude_variant["properties"]["rank_score"]["type"] == "null"
    assert exclude_variant["properties"]["estimated_yield"]["type"] == "null"

    assert observe_variant["properties"]["url_pattern"]["type"] == "string"
    assert observe_variant["properties"]["rank_score"]["type"] == "integer"
    assert observe_variant["properties"]["estimated_yield"]["type"] == "integer"
    assert observe_variant["properties"]["priority_rank"]["type"] == "null"
    assert observe_variant["properties"]["target_voc_types"]["maxItems"] == 0

    assert mined_observe_variant["properties"]["priority_rank"]["type"] == "integer"
    assert mined_observe_variant["properties"]["target_voc_types"]["minItems"] == 1
    assert mined_observe_variant["properties"]["sampling_strategy"]["type"] == "string"
    assert mined_observe_variant["properties"]["platform_behavior_note"]["type"] == "string"


def _iter_strategy_v2_run_prompt_json_schemas():
    source_path = Path(strategy_v2_activities.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def _enclosing_function(node: ast.AST) -> ast.FunctionDef | None:
        current = parents.get(node)
        while current is not None and not isinstance(current, ast.FunctionDef):
            current = parents.get(current)
        return current if isinstance(current, ast.FunctionDef) else None

    def _build_local_scope(function_node: ast.FunctionDef | None, *, lineno: int) -> dict[str, object]:
        if function_node is None:
            return {}
        local_scope: dict[str, object] = {}
        for stmt in function_node.body:
            stmt_lineno = getattr(stmt, "lineno", None)
            if stmt_lineno is not None and stmt_lineno >= lineno:
                break
            target_name: str | None = None
            value_node: ast.AST | None = None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                target_name = stmt.targets[0].id
                value_node = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                target_name = stmt.target.id
                value_node = stmt.value
            if not target_name or value_node is None:
                continue
            expr = ast.get_source_segment(source, value_node)
            if not expr:
                continue
            try:
                local_scope[target_name] = eval(expr, strategy_v2_activities.__dict__, dict(local_scope))
            except Exception:
                continue
        return local_scope

    def _resolve_local_name(function_node: ast.FunctionDef | None, *, name: str, lineno: int) -> object:
        if function_node is None:
            raise NameError(name)
        latest_lineno = -1
        latest_value: ast.AST | None = None
        for child in ast.walk(function_node):
            child_lineno = getattr(child, "lineno", -1)
            if child_lineno >= lineno:
                continue
            if isinstance(child, ast.Assign) and len(child.targets) == 1 and isinstance(child.targets[0], ast.Name):
                if child.targets[0].id == name and child_lineno > latest_lineno:
                    latest_lineno = child_lineno
                    latest_value = child.value
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and child.value is not None:
                if child.target.id == name and child_lineno > latest_lineno:
                    latest_lineno = child_lineno
                    latest_value = child.value
        if latest_value is None:
            raise NameError(name)
        expr = ast.get_source_segment(source, latest_value)
        if not expr:
            raise NameError(name)
        return eval(expr, strategy_v2_activities.__dict__, {})

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "_run_prompt_json_object":
            continue

        schema_name: str | None = None
        schema_expr: str | None = None
        for kw in node.keywords:
            if kw.arg == "schema_name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                schema_name = kw.value.value
            elif kw.arg == "schema":
                schema_expr = ast.get_source_segment(source, kw.value)
        if not schema_name or not schema_expr:
            continue

        function_node = _enclosing_function(node)
        local_scope = _build_local_scope(function_node, lineno=node.lineno)
        try:
            schema = eval(schema_expr, strategy_v2_activities.__dict__, local_scope)
        except NameError:
            if not schema_expr.isidentifier():
                raise
            schema = _resolve_local_name(function_node, name=schema_expr, lineno=node.lineno)
        yield node.lineno, schema_name, schema


def _collect_openai_strict_schema_issues(node: object, *, path: str = "$") -> list[str]:
    issues: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            raw_properties = node.get("properties")
            properties = raw_properties if isinstance(raw_properties, dict) else {}
            if node.get("additionalProperties") is not False:
                issues.append(f"{path}: additionalProperties must be false")
            if properties:
                required = node.get("required")
                if not isinstance(required, list):
                    issues.append(f"{path}: required must be a list")
                else:
                    missing = [key for key in properties if key not in required]
                    extra = [key for key in required if key not in properties]
                    if missing or extra:
                        issues.append(f"{path}: required mismatch missing={missing} extra={extra}")
            for key, child in properties.items():
                issues.extend(_collect_openai_strict_schema_issues(child, path=f"{path}.properties.{key}"))

        items = node.get("items")
        if isinstance(items, (dict, list)):
            issues.extend(_collect_openai_strict_schema_issues(items, path=f"{path}.items"))

        for combiner_key in ("anyOf", "oneOf", "allOf"):
            combiner = node.get(combiner_key)
            if isinstance(combiner, list):
                for idx, child in enumerate(combiner):
                    issues.extend(_collect_openai_strict_schema_issues(child, path=f"{path}.{combiner_key}[{idx}]"))

        negated = node.get("not")
        if isinstance(negated, dict):
            issues.extend(_collect_openai_strict_schema_issues(negated, path=f"{path}.not"))
    elif isinstance(node, list):
        for idx, child in enumerate(node):
            issues.extend(_collect_openai_strict_schema_issues(child, path=f"{path}[{idx}]"))
    return issues


def test_strategy_v2_run_prompt_json_schemas_are_openai_strict() -> None:
    failures: list[str] = []

    for lineno, schema_name, schema in _iter_strategy_v2_run_prompt_json_schemas():
        normalized = strategy_v2_activities._enforce_strict_openai_json_schema(schema)
        issues = _collect_openai_strict_schema_issues(normalized)
        if issues:
            failures.append(f"{schema_name}@{lineno}")
            failures.extend(f"  - {issue}" for issue in issues)

    assert not failures, "\n".join(failures)


def test_run_agent2_extractor_accepts_single_pass_output(monkeypatch: pytest.MonkeyPatch) -> None:
    agent02_asset = resolve_prompt_asset(
        pattern="VOC + Angle Engine (2-21-26)/prompts/agent-02b-voc-extractor.md",
        context="agent2 extractor",
    )

    monkeypatch.setattr(strategy_v2_activities.activity, "heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_upload_openai_prompt_json_files",
        lambda **_kwargs: (
            {
                "EVIDENCE_ROWS_JSON": "file_test_123",
                "AGENT2_INPUT_MANIFEST_JSON": "file_test_manifest_123",
            },
            ["file_test_123", "file_test_manifest_123"],
        ),
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_cleanup_openai_prompt_files",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_prompt_json_object",
        lambda **_kwargs: (
            {
                "mode": "DUAL",
                "input_count": 1,
                "output_count": 2,
                "voc_observations": [
                    {
                        "evidence_id": "E1111111111111111",
                        "source_type": "REDDIT",
                        "source_url": "https://example.com/post/1",
                        "source_author": "user-1",
                        "source_date": "2026-02-01",
                        "evidence_ref": "row-1",
                        "quote": "I need safer guidance.",
                        "source": "",
                    }
                ],
                "rejected_items": [],
                "validation_errors": [],
            },
            "{}",
            {"prompt_path": agent02_asset.relative_path, "prompt_sha256": agent02_asset.sha256, "model_name": "gpt-test"},
        ),
    )

    result = strategy_v2_activities._run_agent2_extractor(
        agent02_asset=agent02_asset,
        model="gpt-test",
        workflow_run_id="wf_test_001",
        mode="DUAL",
        evidence_rows=[
            {
                "evidence_id": "E1111111111111111",
                "source_type": "REDDIT",
                "source_url": "https://example.com/post/1",
                "author": "user-1",
                "date": "2026-02-01",
                "context": "Example context",
                "verbatim": "I need safer guidance.",
                "evidence_ref": "row-1",
                "habitat_name": "reddit.com/r/example",
                "habitat_type": "Reddit",
                "strategy_target_id": "HT-001",
            }
        ],
        agent01_output={"mining_plan": []},
        habitat_scored={},
        stage1_data={},
        avatar_brief_payload={},
        competitor_analysis={},
        saturated_angles=[],
        foundational_step_contents={},
        foundational_step_summaries={},
        activity_name="strategy_v2.run_voc_agent2_extraction",
    )

    assert result["mode"] == "DUAL"
    assert len(result["voc_observations"]) == 1
    assert result["voc_observations"][0]["voc_id"] == "V0001"
    assert result["voc_observations"][0]["source"] == "REDDIT::https://example.com/post/1"
    assert result["voc_observations"][0]["evidence_id"] == "E1111111111111111"
    assert result["extraction_summary"]["input_count"] == 1
    assert result["extraction_summary"]["output_count"] == 1


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


def test_json_schema_response_format_preserves_explicit_object_constraints() -> None:
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
    assert schema["additionalProperties"] is True
    assert schema["required"] == ["alpha"]
    nested = schema["properties"]["nested"]
    assert nested["additionalProperties"] is True
    assert nested["required"] == ["inner"]
    freeform = schema["properties"]["freeform"]
    assert freeform["additionalProperties"] is True
    assert freeform["properties"] == {}
    assert "required" not in freeform


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


def test_map_offer_pipeline_input_with_price_resolution_fails_when_price_is_tbd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake_map_offer_pipeline_input(**kwargs):
        stage2 = kwargs["stage2"]
        calls.append(stage2.price)
        return {"price_used": stage2.price}

    monkeypatch.setattr(strategy_v2_activities, "map_offer_pipeline_input", _fake_map_offer_pipeline_input)

    stage2 = _build_stage2_with_price("TBD")
    with pytest.raises(
        StrategyV2MissingContextError,
        match="fallback price scraping is disabled",
    ):
        strategy_v2_activities._map_offer_pipeline_input_with_price_resolution(
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

    assert calls == []
