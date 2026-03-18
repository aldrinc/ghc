from __future__ import annotations

from app.db.enums import ArtifactTypeEnum, WorkflowKindEnum, WorkflowStatusEnum
from app.db.models import Artifact, ResearchArtifact, StrategyV2Launch, WorkflowRun
from tests.conftest import TEST_ORG_ID


def _stage1_payload() -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "stage": 1,
        "product_name": "Launch Context Product",
        "description": "Launch Context Product helps customers evaluate offers.",
        "price": "$49",
        "competitor_urls": ["https://example.com/competitor"],
        "product_customizable": False,
        "category_niche": "Herbal wellness",
        "product_category_keywords": ["wellness", "supplements"],
        "market_maturity_stage": "Growth",
        "primary_segment": {
            "name": "Adults comparing alternative wellness offers",
            "size_estimate": "Large niche audience",
            "key_differentiator": "Need structure before buying",
        },
        "bottleneck": "Customers do not trust generic supplement claims.",
        "positioning_gaps": ["Competitors do not explain the decision process clearly."],
        "competitor_count_validated": 1,
        "primary_icps": ["Research-driven wellness buyers"],
    }


def seed_ready_launch_context_for_campaign(
    db_session,
    *,
    client_id: str,
    product_id: str,
    campaign_id: str,
    org_id: str = TEST_ORG_ID,
    launch_key: str = "sv2-launch:test:ready-context",
) -> None:
    source_run = WorkflowRun(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        temporal_workflow_id=f"strategy-v2-source-{campaign_id}",
        temporal_run_id=f"strategy-v2-source-{campaign_id}-run",
        kind=WorkflowKindEnum.strategy_v2,
        status=WorkflowStatusEnum.completed,
    )
    db_session.add(source_run)
    db_session.commit()
    db_session.refresh(source_run)

    stage1_artifact = Artifact(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        type=ArtifactTypeEnum.strategy_v2_stage1,
        data=_stage1_payload(),
    )
    stage3_artifact = Artifact(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        type=ArtifactTypeEnum.strategy_v2_stage3,
        data={
            "selected_angle": {
                "angle_id": "A01",
                "angle_name": "Angle One",
                "evidence": {
                    "supporting_voc_count": 3,
                    "top_quotes": [{"quote": "Finally, a clearer buying path."}],
                    "triangulation_status": "MULTI",
                    "velocity_status": "STEADY",
                    "contradiction_count": 0,
                },
            },
            "ump": "Root-cause framing",
            "ums": "Mechanism-first solution",
            "core_promise": "Clear outcome promise",
            "value_stack_summary": ["Value stack"],
            "guarantee_type": "standard",
            "pricing_rationale": "Reasoned",
            "variant_selected": "variant-1",
            "composite_score": 0.91,
        },
    )
    offer_artifact = Artifact(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        type=ArtifactTypeEnum.strategy_v2_offer,
        data={
            "decision": {"winner": "offer-1"},
            "selected_variant": {"id": "variant-1", "name": "Offer Variant"},
            "selected_variant_score": {"score": 0.93},
            "product_offer_id": "offer-1",
            "product_offer": {"id": "offer-1", "name": "Offer One"},
        },
    )
    copy_context_artifact = Artifact(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        type=ArtifactTypeEnum.strategy_v2_copy_context,
        data={"context": True},
    )
    approved_copy_artifact = Artifact(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        type=ArtifactTypeEnum.strategy_v2_copy,
        data={
            "angle_run_id": "angle-run-1",
            "headline": "Approved headline",
            "presell_markdown": "Presell copy",
            "sales_page_markdown": "Sales copy",
            "quality_gate_report": {"passed": True},
            "semantic_gates": {"passed": True},
            "congruency": {"passed": True},
            "decision": {"approved": True},
            "template_payloads": {
                "pre-sales-listicle": {"template_patch": [{"op": "replace", "path": "/hero/title", "value": "A"}]},
                "sales-pdp": {"template_patch": [{"op": "replace", "path": "/hero/title", "value": "B"}]},
            },
        },
    )
    db_session.add_all(
        [
            stage1_artifact,
            stage3_artifact,
            offer_artifact,
            copy_context_artifact,
            approved_copy_artifact,
        ]
    )
    db_session.commit()
    for artifact in (stage1_artifact, stage3_artifact, offer_artifact, copy_context_artifact, approved_copy_artifact):
        db_session.refresh(artifact)

    step_payload_rows = {
        "v2-06": {
            "stage1_artifact_id": str(stage1_artifact.id),
            "ranked_candidates": [{"angle": {"angle_id": "A01", "angle_name": "Angle One"}}],
        },
        "v2-08": {
            "offer_input": {
                "product_brief": {
                    "business_model": "d2c",
                    "funnel_position": "mid",
                    "target_platforms": ["meta"],
                    "target_regions": ["us"],
                    "constraints": {
                        "existing_proof_assets": ["proof-1"],
                        "brand_voice_notes": "clear notes",
                    },
                }
            }
        },
        "v2-09": {
            "stage3_artifact_id": str(stage3_artifact.id),
            "offer_artifact_id": str(offer_artifact.id),
            "copy_context_artifact_id": str(copy_context_artifact.id),
        },
        "v2-11": {
            "decision": {"approved": True},
            "approved_artifact_id": str(approved_copy_artifact.id),
        },
    }
    for step_key, payload in step_payload_rows.items():
        artifact = Artifact(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            type=ArtifactTypeEnum.strategy_v2_step_payload,
            data={"step_key": step_key, "payload": payload},
        )
        db_session.add(artifact)
        db_session.commit()
        db_session.refresh(artifact)
        db_session.add(
            ResearchArtifact(
                org_id=org_id,
                workflow_run_id=source_run.id,
                step_key=step_key,
                title=f"Step {step_key}",
                doc_id=str(artifact.id),
                doc_url=f"artifact://{artifact.id}",
                prompt_sha256=None,
                summary=None,
            )
        )
        db_session.commit()

    launch_row = StrategyV2Launch(
        org_id=org_id,
        source_strategy_v2_workflow_run_id=source_run.id,
        source_strategy_v2_temporal_workflow_id=source_run.temporal_workflow_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        funnel_id=None,
        angle_id="A01",
        angle_run_id="angle-run-1",
        selected_ums_id="ums-1",
        selected_variant_id="variant-1",
        source_stage3_artifact_id=stage3_artifact.id,
        source_offer_artifact_id=offer_artifact.id,
        source_copy_artifact_id=approved_copy_artifact.id,
        source_copy_context_artifact_id=copy_context_artifact.id,
        launch_type="initial_angle",
        launch_key=launch_key,
        launch_index=1,
        launch_workflow_run_id=None,
        launch_temporal_workflow_id=None,
        created_by_user="test-user",
    )
    db_session.add(launch_row)
    db_session.commit()
