import pytest

from app.agent.funnel_tools import StrategyCopyError, _build_strategy_prompt_context


def test_build_strategy_prompt_context_uses_page_specific_copy_blueprint():
    outputs = {
        "stage3": {
            "selected_angle": {
                "angle_id": "angle-1",
                "angle_name": "Mechanism clarity",
                "evidence": {
                    "supporting_voc_count": 7,
                    "top_quotes": [
                        {"quote": "This finally made the process feel clear."},
                        {"quote": "I stopped second-guessing every step."},
                    ],
                },
            },
            "ump": "Mechanism-first promise",
            "ums": "Structured routine",
            "core_promise": "Feel confident following the next step",
            "value_stack_summary": ["Checklist", "Quick-start guide"],
            "guarantee_type": "30-day guarantee",
            "pricing_rationale": "Replaces scattered research time",
        },
        "offer": {
            "selected_variant": {"id": "variant-1", "name": "Starter"},
            "product_offer": {"id": "offer-1", "name": "Starter Bundle"},
        },
        "copy": {
            "headline": "Stop second-guessing your next step",
            "promise_contract": {
                "specific_promise": "Feel confident following the next step",
                "delivery_test": "Clear within the first read",
            },
            "sales_page_markdown": "## Hero\nLead with the mechanism.\n\n## CTA\nBuy now.",
            "presell_markdown": "## Problem\nSet up the story.",
            "template_payloads": {
                "sales-pdp": {"template_patch": [{"op": "replace", "path": "/hero/title", "value": "Hero"}]},
                "pre-sales-listicle": {"template_patch": [{"op": "replace", "path": "/hero/title", "value": "Story"}]},
            },
            "quality_gate_report": {"passed": True},
            "semantic_gates": {"passed": True},
            "congruency": {"passed": True},
        },
        "copy_context": {"voice": "direct", "constraints": ["stay compliant"]},
        "artifact_ids": {"stage3": "stage3-1", "offer": "offer-1", "copy": "copy-1", "copy_context": "ctx-1"},
    }

    context = _build_strategy_prompt_context(outputs=outputs, template_kind="sales-pdp")

    assert context["templateKind"] == "sales-pdp"
    assert context["selectedAngle"]["angleId"] == "angle-1"
    assert context["selectedAngle"]["topQuotes"] == [
        "This finally made the process feel clear.",
        "I stopped second-guessing every step.",
    ]
    assert context["offer"]["corePromise"] == "Feel confident following the next step"
    assert context["copy"]["pageMarkdown"].startswith("## Hero")
    assert context["copy"]["templatePatchOperationCount"] == 1
    assert context["artifactIds"]["copy"] == "copy-1"


def test_build_strategy_prompt_context_requires_latest_page_markdown():
    outputs = {
        "stage3": {"selected_angle": {}, "ump": "UMP", "ums": "UMS", "core_promise": "Promise"},
        "offer": {"selected_variant": {"id": "variant-1"}},
        "copy": {
            "headline": "Headline",
            "promise_contract": {"specific_promise": "Promise"},
            "sales_page_markdown": "",
            "template_payloads": {"sales-pdp": {"template_patch": [{"op": "replace", "path": "/hero/title", "value": "Hero"}]}},
        },
        "copy_context": {"voice": "direct"},
        "artifact_ids": {"copy": "copy-1"},
    }

    with pytest.raises(StrategyCopyError, match="sales_page_markdown"):
        _build_strategy_prompt_context(outputs=outputs, template_kind="sales-pdp")


def test_build_strategy_prompt_context_supports_manual_campaign_creative_context_without_template_payloads():
    outputs = {
        "provider": "manual",
        "angles": {
            "selectedAngleId": "angle-1",
            "angleLibrary": [
                {
                    "angleId": "angle-1",
                    "angleName": "Brain Fuel Deficit",
                    "description": "Reframe the fog as depletion, not decline.",
                    "evidence": [
                        "Doctors keep dismissing the symptom cluster.",
                        "Women fear they are losing their minds.",
                    ],
                }
            ],
        },
        "offer": {
            "ump": "Restore the brain fuel perimenopause drains away.",
            "ums": "Clinical-dose creatine in a format she will actually take.",
            "corePromise": "Trust your own brain again.",
            "valueStackSummary": "60 Day Supply plus tracker",
            "guaranteeType": "Complete Clarity Promise",
            "pricingRationale": "Less than the monthly spend on nootropic stacks.",
            "selectedVariantId": "60-day-supply",
            "selectedVariantName": "60 Day Supply",
        },
        "copy": {
            "headline": "A little-known fuel deficit may explain the fog",
            "promiseContract": {
                "loopQuestion": "Why does it feel like dementia when it may be a fuel deficit?",
                "specificPromise": "Trust your own brain again.",
                "deliveryTest": "Feel the fog thinning across the first 30 days.",
                "minimumDelivery": "Finish the first 30 Day Supply.",
            },
            "salesPageMarkdown": "## Hero\nLead with the fuel-deficit reframe.",
            "presellMarkdown": "## Story\nOpen on the disappearing-word moment.",
            "templatePayloads": None,
        },
        "copy_context": {
            "brandVoiceMarkdown": "Clinical expertise softened by personal vulnerability.",
            "complianceMarkdown": "No disease claims.",
        },
        "artifact_ids": {
            "angles": "angles-1",
            "offer": "offer-1",
            "copy": "copy-1",
            "copy_context": "ctx-1",
            "creative_context": "aggregate-1",
        },
    }

    context = _build_strategy_prompt_context(outputs=outputs, template_kind="sales-pdp")

    assert context["source"] == "campaign_creative_context.manual"
    assert context["selectedAngle"]["angleId"] == "angle-1"
    assert context["selectedAngle"]["supportingPoints"] == [
        "Doctors keep dismissing the symptom cluster.",
        "Women fear they are losing their minds.",
    ]
    assert context["offer"]["corePromise"] == "Trust your own brain again."
    assert context["copy"]["templatePatchOperationCount"] == 0
    assert context["artifactIds"]["creative_context"] == "aggregate-1"
