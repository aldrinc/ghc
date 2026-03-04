from __future__ import annotations

from app.strategy_v2.downstream import build_strategy_v2_downstream_packet


def test_build_downstream_packet_includes_template_payloads() -> None:
    template_payloads = {
        "sales-pdp": {
            "template_id": "sales-pdp",
            "payload_version": "v1",
            "fields": {"hero": {"purchase_title": "Title"}},
            "template_patch": [{"component_type": "SalesPdpHero", "field_path": "props.config.purchase.title", "value": "Title"}],
        }
    }
    packet = build_strategy_v2_downstream_packet(
        stage3={
            "selected_angle": {"angle_id": "a1", "angle_name": "Angle", "evidence": {"supporting_voc_count": 5}},
            "ump": "UMP",
            "ums": "UMS",
            "core_promise": "Promise",
            "value_stack_summary": ["A"],
            "guarantee_type": "30-day",
            "pricing_rationale": "one-time",
            "variant_selected": "v1",
            "composite_score": 7.0,
        },
        offer={"decision": {"variant_id": "v1"}},
        copy={
            "headline": "Headline",
            "promise_contract": {"specific_promise": "Promise"},
            "presell_markdown": "presell",
            "sales_page_markdown": "sales",
            "quality_gate_report": {"ok": True},
            "semantic_gates": {"ok": True},
            "congruency": {"ok": True},
            "template_payloads": template_payloads,
            "angle_run_id": "wf:a1",
        },
        copy_context={"audience_product_markdown": "ctx"},
        awareness_angle_matrix={"angle_name": "Angle"},
        artifact_ids={
            "stage3": "s3",
            "offer": "offer",
            "copy": "copy",
            "copy_context": "ctx",
            "awareness_angle_matrix": "matrix",
        },
    )

    assert packet is not None
    assert packet["copy"]["template_payloads"] == template_payloads
    assert packet["template_payloads"] == template_payloads


def test_build_downstream_packet_exposes_offer_artifact_payload_fields() -> None:
    packet = build_strategy_v2_downstream_packet(
        stage3={
            "selected_angle": {"angle_id": "a1", "angle_name": "Angle", "evidence": {"supporting_voc_count": 5}},
            "ump": "UMP",
            "ums": "UMS",
            "core_promise": "Promise",
            "value_stack_summary": ["A"],
            "guarantee_type": "30-day",
            "pricing_rationale": "one-time",
            "variant_selected": "v1",
            "composite_score": 7.0,
        },
        offer={
            "decision": {"variant_id": "v1"},
            "selected_variant": {"variant_id": "v1", "core_promise": "Promise"},
            "selected_variant_score": {"variant_id": "v1", "composite_safety_adjusted": 7.0},
            "product_offer_id": "offer-db-id",
            "product_offer": {"id": "offer-db-id", "name": "Promise"},
        },
        copy={
            "headline": "Headline",
            "promise_contract": {"specific_promise": "Promise"},
            "presell_markdown": "presell",
            "sales_page_markdown": "sales",
            "quality_gate_report": {"ok": True},
            "semantic_gates": {"ok": True},
            "congruency": {"ok": True},
        },
        copy_context={"audience_product_markdown": "ctx"},
        awareness_angle_matrix={"angle_name": "Angle"},
        artifact_ids={
            "stage3": "s3",
            "offer": "offer",
            "copy": "copy",
            "copy_context": "ctx",
            "awareness_angle_matrix": "matrix",
        },
    )

    assert packet is not None
    assert packet["offer"]["selected_variant"]["variant_id"] == "v1"
    assert packet["offer"]["product_offer_id"] == "offer-db-id"
    assert packet["offer"]["product_offer"]["name"] == "Promise"
