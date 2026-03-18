from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.enums import ArtifactTypeEnum, WorkflowKindEnum, WorkflowStatusEnum
from app.db.models import Artifact, Campaign, Client, Product, ResearchArtifact, StrategyV2Launch, WorkflowRun
from app.routers import workflows as workflows_router
from app.temporal.workflows import strategy_v2_launch as strategy_v2_launch_workflow
from app.strategy_v2 import launches as strategy_v2_launches
from app.strategy_v2.launches import load_strategy_v2_source_context
from tests.conftest import TEST_ORG_ID


class _CapturingTemporalHandle:
    def __init__(self, workflow_id: str) -> None:
        self.id = workflow_id
        self.first_execution_run_id = f"{workflow_id}-run"


class _CapturingTemporalClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def start_workflow(self, workflow, input, **kwargs):
        workflow_id = kwargs.get("id") or f"workflow-{uuid4()}"
        self.calls.append(
            {
                "workflow": workflow,
                "input": input,
                "kwargs": kwargs,
            }
        )
        return _CapturingTemporalHandle(workflow_id)


def _seed_strategy_v2_scope(db_session):
    client = Client(org_id=TEST_ORG_ID, name="Launch Client", industry="Health")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        title="Launch Product",
        description="Launch-ready product description.",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    source_run = WorkflowRun(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        temporal_workflow_id="strategy-v2-source",
        temporal_run_id="strategy-v2-source-run",
        kind=WorkflowKindEnum.strategy_v2,
        status=WorkflowStatusEnum.completed,
    )
    db_session.add(source_run)
    db_session.commit()
    db_session.refresh(source_run)

    campaign = Campaign(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        name="Launch Campaign",
        channels=["meta"],
        asset_brief_types=["image"],
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    return client, product, source_run, campaign


def _fake_source_context() -> SimpleNamespace:
    return SimpleNamespace(
        source_temporal_workflow_id="strategy-v2-source",
        selected_angle={"angle_id": "A01", "angle_name": "Mechanism-first relief"},
        selected_angle_id="A01",
        selected_angle_name="Mechanism-first relief",
        angle_run_id="angle-run-1",
        stage1={"product_name": "Launch Product"},
        ranked_angle_candidates=[{"angle": {"angle_id": "A02", "angle_name": "Second angle"}}],
        angle_synthesis_payload={"summary": "angle synthesis"},
        competitor_analysis={"summary": "competitor analysis"},
        voc_observations=[{"observation_id": "voc-1"}],
        voc_scored={"rows": [{"id": "voc-1"}]},
        proof_asset_candidates=[],
        offer_pipeline_payload={
            "pair_scoring": {
                "ranked_pairs": [
                    {
                        "pair_id": "pair-1",
                        "ums_id": "ums-1",
                        "ums_name": "UMS 1",
                        "ump_name": "UMP 1",
                    }
                ]
            }
        },
        source_stage3={"ums": "ums-primary", "variant_selected": "variant-1"},
        source_offer={"variant_selected": "variant-1"},
        source_copy={"headline": "Approved headline"},
        source_copy_context={"context": "value"},
        source_downstream_packet={
            "template_payloads": {
                "pre-sales-listicle": {"template_patch": [{"op": "replace", "path": "/hero/title", "value": "A"}]},
                "sales-pdp": {"template_patch": [{"op": "replace", "path": "/hero/title", "value": "B"}]},
            }
        },
        source_stage3_artifact_id=str(uuid4()),
        source_offer_artifact_id=str(uuid4()),
        source_copy_artifact_id=str(uuid4()),
        source_copy_context_artifact_id=str(uuid4()),
        source_awareness_matrix_artifact_id=None,
        offer_operator_inputs={
            "business_model": "d2c",
            "funnel_position": "mid",
            "target_platforms": ["meta"],
            "target_regions": ["us"],
            "existing_proof_assets": ["proof-1"],
            "brand_voice_notes": "Clear and specific.",
        },
        offer_winner_onboarding_payload_id=None,
        step_payloads={},
    )


def test_launch_angle_campaign_uses_created_workflow_run_id(api_client, db_session, monkeypatch):
    _, _, source_run, _ = _seed_strategy_v2_scope(db_session)

    temporal_client = _CapturingTemporalClient()

    async def _get_temporal_client():
        return temporal_client

    monkeypatch.setattr(workflows_router, "get_temporal_client", _get_temporal_client)
    monkeypatch.setattr(
        workflows_router,
        "_load_source_context_or_409",
        lambda **_kwargs: _fake_source_context(),
    )

    response = api_client.post(
        f"/workflows/{source_run.id}/actions/strategy-v2/launch-angle-campaign",
        json={
            "channels": ["meta"],
            "assetBriefTypes": ["image"],
            "experimentVariantPolicy": "angle_launch_standard_v1",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    launch_workflow_run_id = payload["launch_workflow_run_id"]
    assert launch_workflow_run_id

    assert len(temporal_client.calls) == 1
    temporal_input = temporal_client.calls[0]["input"]
    assert temporal_input.launch_workflow_run_id == launch_workflow_run_id
    assert temporal_input.launch_workflow_run_id != ""

    launch_run = db_session.get(WorkflowRun, launch_workflow_run_id)
    assert launch_run is not None
    assert launch_run.kind == WorkflowKindEnum.strategy_v2_angle_launch
    assert launch_run.temporal_run_id != "pending"


def test_launch_workflow_retries_funnel_generation_on_infra_failures_only():
    retry_policy = strategy_v2_launch_workflow._FUNNEL_GENERATION_RETRY_POLICY

    assert retry_policy.maximum_attempts == 3
    assert retry_policy.non_retryable_error_types is not None
    assert "TimeoutError" in retry_policy.non_retryable_error_types
    assert "ToolExecutionError" in retry_policy.non_retryable_error_types


def test_campaign_launch_history_endpoint_returns_launch_status(api_client, db_session):
    client, product, source_run, campaign = _seed_strategy_v2_scope(db_session)

    launch_run = WorkflowRun(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=campaign.id,
        temporal_workflow_id="strategy-v2-angle-launch-test",
        temporal_run_id="strategy-v2-angle-launch-test-run",
        kind=WorkflowKindEnum.strategy_v2_angle_launch,
        status=WorkflowStatusEnum.running,
    )
    db_session.add(launch_run)
    db_session.commit()
    db_session.refresh(launch_run)

    launch_row = StrategyV2Launch(
        org_id=TEST_ORG_ID,
        source_strategy_v2_workflow_run_id=source_run.id,
        source_strategy_v2_temporal_workflow_id=source_run.temporal_workflow_id,
        client_id=client.id,
        product_id=product.id,
        campaign_id=campaign.id,
        funnel_id=None,
        angle_id="A01",
        angle_run_id="angle-run-1",
        selected_ums_id="ums-1",
        selected_variant_id="variant-1",
        source_stage3_artifact_id=None,
        source_offer_artifact_id=None,
        source_copy_artifact_id=None,
        source_copy_context_artifact_id=None,
        launch_type="additional_ums",
        launch_key=f"sv2-launch:test:{uuid4()}",
        launch_index=None,
        launch_workflow_run_id=launch_run.id,
        launch_temporal_workflow_id=launch_run.temporal_workflow_id,
        created_by_user="test-user",
    )
    db_session.add(launch_row)
    db_session.commit()

    response = api_client.get(f"/campaigns/{campaign.id}/strategy-v2-launches")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["id"] == str(launch_row.id)
    assert rows[0]["campaign_id"] == str(campaign.id)
    assert rows[0]["launch_status"] == WorkflowStatusEnum.running.value


def test_launch_additional_angle_errors_when_idempotent_rows_span_multiple_launch_runs(
    api_client,
    db_session,
    monkeypatch,
):
    client, product, source_run, _ = _seed_strategy_v2_scope(db_session)

    source_context = _fake_source_context()
    source_context.ranked_angle_candidates = [
        {"angle": {"angle_id": "A02", "angle_name": "Second angle"}},
        {"angle": {"angle_id": "A03", "angle_name": "Third angle"}},
    ]
    monkeypatch.setattr(
        workflows_router,
        "_load_source_context_or_409",
        lambda **_kwargs: source_context,
    )

    launch_run_one = WorkflowRun(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        temporal_workflow_id="strategy-v2-angle-launch-one",
        temporal_run_id="strategy-v2-angle-launch-one-run",
        kind=WorkflowKindEnum.strategy_v2_angle_launch,
        status=WorkflowStatusEnum.completed,
    )
    launch_run_two = WorkflowRun(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        temporal_workflow_id="strategy-v2-angle-launch-two",
        temporal_run_id="strategy-v2-angle-launch-two-run",
        kind=WorkflowKindEnum.strategy_v2_angle_launch,
        status=WorkflowStatusEnum.completed,
    )
    db_session.add_all([launch_run_one, launch_run_two])
    db_session.commit()
    db_session.refresh(launch_run_one)
    db_session.refresh(launch_run_two)

    channels = ["meta"]
    asset_brief_types = ["image"]
    launch_key_a02 = strategy_v2_launches.build_launch_key(
        source_strategy_v2_workflow_run_id=str(source_run.id),
        launch_type="additional_angle",
        angle_id="A02",
        campaign_id=None,
        selected_ums_id=None,
        channels=channels,
        asset_brief_types=asset_brief_types,
        experiment_variant_policy="angle_branch_standard_v1",
    )
    launch_key_a03 = strategy_v2_launches.build_launch_key(
        source_strategy_v2_workflow_run_id=str(source_run.id),
        launch_type="additional_angle",
        angle_id="A03",
        campaign_id=None,
        selected_ums_id=None,
        channels=channels,
        asset_brief_types=asset_brief_types,
        experiment_variant_policy="angle_branch_standard_v1",
    )

    row_one = StrategyV2Launch(
        org_id=TEST_ORG_ID,
        source_strategy_v2_workflow_run_id=source_run.id,
        source_strategy_v2_temporal_workflow_id=source_run.temporal_workflow_id,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        funnel_id=None,
        angle_id="A02",
        angle_run_id="angle-run-2",
        selected_ums_id=None,
        selected_variant_id=None,
        source_stage3_artifact_id=None,
        source_offer_artifact_id=None,
        source_copy_artifact_id=None,
        source_copy_context_artifact_id=None,
        launch_type="additional_angle",
        launch_key=launch_key_a02,
        launch_index=1,
        launch_workflow_run_id=launch_run_one.id,
        launch_temporal_workflow_id=launch_run_one.temporal_workflow_id,
        created_by_user="test-user",
    )
    row_two = StrategyV2Launch(
        org_id=TEST_ORG_ID,
        source_strategy_v2_workflow_run_id=source_run.id,
        source_strategy_v2_temporal_workflow_id=source_run.temporal_workflow_id,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        funnel_id=None,
        angle_id="A03",
        angle_run_id="angle-run-3",
        selected_ums_id=None,
        selected_variant_id=None,
        source_stage3_artifact_id=None,
        source_offer_artifact_id=None,
        source_copy_artifact_id=None,
        source_copy_context_artifact_id=None,
        launch_type="additional_angle",
        launch_key=launch_key_a03,
        launch_index=1,
        launch_workflow_run_id=launch_run_two.id,
        launch_temporal_workflow_id=launch_run_two.temporal_workflow_id,
        created_by_user="test-user",
    )
    db_session.add_all([row_one, row_two])
    db_session.commit()

    response = api_client.post(
        f"/workflows/{source_run.id}/actions/strategy-v2/launch-additional-angle",
        json={
            "selectedAngleIds": ["A02", "A03"],
            "channels": channels,
            "assetBriefTypes": asset_brief_types,
        },
    )

    assert response.status_code == 409, response.text
    assert "span multiple launch workflows" in response.json()["detail"]


def test_launch_angle_campaign_rejects_unsupported_asset_brief_types(api_client, db_session, monkeypatch):
    _, _, source_run, _ = _seed_strategy_v2_scope(db_session)

    monkeypatch.setattr(
        workflows_router,
        "_load_source_context_or_409",
        lambda **_kwargs: _fake_source_context(),
    )

    response = api_client.post(
        f"/workflows/{source_run.id}/actions/strategy-v2/launch-angle-campaign",
        json={
            "channels": ["meta"],
            "assetBriefTypes": ["static-image"],
            "experimentVariantPolicy": "angle_launch_standard_v1",
        },
    )

    assert response.status_code == 422, response.text
    assert "Supported values: image, video." in response.text


def test_launch_source_context_resolves_canonical_run_for_continued_execution(db_session, monkeypatch):
    client, product, source_run, _ = _seed_strategy_v2_scope(db_session)

    alternate_run = WorkflowRun(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        temporal_workflow_id=source_run.temporal_workflow_id,
        temporal_run_id=f"{source_run.temporal_run_id}-alt",
        kind=WorkflowKindEnum.strategy_v2,
        status=WorkflowStatusEnum.completed,
    )
    db_session.add(alternate_run)
    db_session.commit()
    db_session.refresh(alternate_run)

    stage1_artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_stage1,
        data={"stage1": True},
    )
    stage3_artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_stage3,
        data={"selected_angle": {"angle_id": "A01", "angle_name": "Angle One"}, "ums": "ums-1", "variant_selected": "variant-1"},
    )
    offer_artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_offer,
        data={"offer": True},
    )
    copy_context_artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_copy_context,
        data={"context": True},
    )
    approved_copy_artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_copy,
        data={
            "angle_run_id": "angle-run-1",
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
    db_session.refresh(stage1_artifact)
    db_session.refresh(stage3_artifact)
    db_session.refresh(offer_artifact)
    db_session.refresh(copy_context_artifact)
    db_session.refresh(approved_copy_artifact)

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
                    "target_platforms": ["facebook"],
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
            org_id=TEST_ORG_ID,
            client_id=client.id,
            product_id=product.id,
            campaign_id=None,
            type=ArtifactTypeEnum.strategy_v2_step_payload,
            data={"step_key": step_key, "payload": payload},
        )
        db_session.add(artifact)
        db_session.commit()
        db_session.refresh(artifact)
        db_session.add(
            ResearchArtifact(
                org_id=TEST_ORG_ID,
                workflow_run_id=alternate_run.id,
                step_key=step_key,
                title=f"Step {step_key}",
                doc_id=str(artifact.id),
                doc_url=f"artifact://{artifact.id}",
                prompt_sha256=None,
                summary=None,
            )
        )
        db_session.commit()

    monkeypatch.setattr(strategy_v2_launches, "build_strategy_v2_downstream_packet", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(strategy_v2_launches.ProductBriefStage1, "model_validate", classmethod(lambda cls, value: value))

    resolved = load_strategy_v2_source_context(
        session=db_session,
        org_id=TEST_ORG_ID,
        source_run=source_run,
    )
    assert str(resolved.source_run.id) == str(alternate_run.id)
