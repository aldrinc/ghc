from __future__ import annotations

import io
import hashlib
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.db.enums import WorkflowKindEnum, WorkflowStatusEnum
from app.db.models import ActivityLog, AnimatedTemplateArtifact, AnimatedTemplateRun, WorkflowRun
from app.schemas.animated_templates import (
    AnimatedTemplateAnalyzeRequest,
    AnimatedTemplateManifestCreateRequest,
    AnimatedTemplateManifestDocument,
)
from app.services.animated_templates.media import extract_animated_source_metadata, sample_frame_indexes
from app.temporal.activities import swipe_animated_template_activities
from app.temporal.activities.swipe_image_ad_activities import _is_animated_swipe_image


_SOURCE_SHA = "a" * 64


def _chart_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "canvas": {"width": 996, "height": 996},
        "timeline": {"durationMs": 2860, "frameCount": 16},
        "productReplacement": {
            "hasCompetitorProductSlot": False,
            "negativeEvidence": [{"kind": "no_product_packshot_detected", "confidence": 0.95}],
        },
        "layers": [
            {
                "id": "axis_label_y",
                "type": "text",
                "policy": "deterministic_rebuild",
                "renderOwner": "deterministic_renderer",
                "text": "ENERGY LEVEL",
                "geometry": {"x": 52, "y": 236, "width": 30, "height": 360, "rotation": -90},
                "sourceFrameIndexes": [0],
            },
            {
                "id": "chart_line_primary",
                "type": "path",
                "policy": "deterministic_rebuild",
                "renderOwner": "deterministic_renderer",
                "sourceFrameIndexes": [0, 1],
                "metadata": {"colorRole": "tenor_red"},
            },
        ],
    }


def _hybrid_manifest() -> dict:
    manifest = _chart_manifest()
    manifest["layers"].append(
        {
            "id": "masked_lifestyle_motion",
            "type": "video_region",
            "policy": "generative_region",
            "renderOwner": "ai_region_model",
            "mask": {
                "kind": "box",
                "box": {"x": 120, "y": 120, "width": 400, "height": 320},
            },
        }
    )
    return manifest


def _source_passthrough_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "canvas": {"width": 8, "height": 8},
        "timeline": {"durationMs": 200, "frameCount": 2},
        "productReplacement": {
            "hasCompetitorProductSlot": False,
            "negativeEvidence": [{"kind": "no_product_packshot_detected", "confidence": 0.95}],
        },
        "layers": [
            {
                "id": "locked_source_pixels",
                "type": "source_frames",
                "policy": "locked_source",
                "renderOwner": "source_pixels",
                "sourceFrameIndexes": [0, 1],
            }
        ],
    }


def _animated_gif_bytes() -> bytes:
    first = Image.new("RGB", (8, 8), "white")
    second = Image.new("RGB", (8, 8), "black")
    animated = io.BytesIO()
    first.save(animated, format="GIF", save_all=True, append_images=[second], duration=100, loop=0)
    return animated.getvalue()


def _create_manifest_payload(**overrides) -> dict:
    payload = {
        "sourceUrl": "https://example.com/source.gif",
        "sourceSha256": _SOURCE_SHA,
        "sourceMimeType": "image/gif",
        "sourceLabel": "source.gif",
        "manifest": _chart_manifest(),
    }
    payload.update(overrides)
    return payload


def test_animated_template_manifest_schema_blocks_product_swap_without_source_slot() -> None:
    manifest = _chart_manifest()
    manifest["productReplacement"]["slots"] = [
        {
            "id": "slot_1",
            "status": "candidate",
            "geometry": {"x": 10, "y": 10, "width": 100, "height": 140},
            "evidence": [{"kind": "candidate_box", "confidence": 0.5}],
        }
    ]
    manifest["layers"].append(
        {
            "id": "bad_product_swap",
            "type": "image",
            "policy": "product_swap",
            "renderOwner": "product_compositor",
            "productSlotId": "slot_1",
        }
    )

    with pytest.raises(ValidationError) as exc:
        AnimatedTemplateManifestDocument.model_validate(manifest)

    assert "product_swap layers require source product-slot evidence" in str(exc.value)


def test_animated_template_manifest_schema_blocks_locked_ai_owner() -> None:
    manifest = _chart_manifest()
    manifest["layers"][0]["renderOwner"] = "ai_region_model"

    with pytest.raises(ValidationError) as exc:
        AnimatedTemplateManifestDocument.model_validate(manifest)

    assert "Locked layers cannot be assigned to ai_region_model" in str(exc.value)


def test_animated_template_manifest_request_requires_one_source() -> None:
    payload = _create_manifest_payload(companySwipeId="swipe-1")

    with pytest.raises(ValidationError) as exc:
        AnimatedTemplateManifestCreateRequest.model_validate(payload)

    assert "Provide exactly one of companySwipeId or sourceUrl" in str(exc.value)


def test_animated_template_analyze_request_does_not_require_precomputed_source_hash() -> None:
    request = AnimatedTemplateAnalyzeRequest.model_validate(
        {
            "sourceUrl": "https://example.com/template.gif",
            "sourceLabel": "template.gif",
        }
    )

    assert request.source_url == "https://example.com/template.gif"


def test_animated_source_metadata_extracts_gif_timeline() -> None:
    first = Image.new("RGB", (8, 8), "white")
    second = Image.new("RGB", (8, 8), "black")
    animated = io.BytesIO()
    first.save(
        animated,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=[80, 120],
        loop=0,
    )

    metadata = extract_animated_source_metadata(
        content=animated.getvalue(),
        content_type="image/gif",
    )

    assert metadata["contentType"] == "image/gif"
    assert metadata["format"] == "gif"
    assert metadata["width"] == 8
    assert metadata["height"] == 8
    assert metadata["frameCount"] == 2
    assert metadata["isAnimated"] is True
    assert metadata["durationMs"] == 200
    assert metadata["sampleFrameIndexes"] == [0, 1]
    assert [frame["frameIndex"] for frame in metadata["sampleFrames"]] == [0, 1]
    assert all(frame["contentType"] == "image/png" for frame in metadata["sampleFrames"])


def test_animated_source_sample_frame_indexes_are_stable() -> None:
    assert sample_frame_indexes(20, sample_count=5) == [0, 5, 10, 14, 19]


def test_animated_template_analyze_endpoint_starts_temporal_workflow(
    api_client: TestClient,
    fake_temporal,
    db_session,
) -> None:
    response = api_client.post(
        "/swipes/animated-templates/analyze",
        json={
            "sourceUrl": "https://example.com/template.gif",
            "sourceLabel": "template.gif",
            "analyzerVersion": "animated-template-analyzer-test",
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["temporalWorkflowId"].startswith("swipe-animated-template-analysis-")
    assert fake_temporal.started == [payload["temporalWorkflowId"]]

    run = db_session.get(WorkflowRun, payload["workflowRunId"])
    assert run is not None
    assert run.kind == WorkflowKindEnum.swipe_animated_template_analysis
    logs = db_session.query(ActivityLog).filter(ActivityLog.workflow_run_id == run.id).all()
    assert [(log.step, log.status) for log in logs] == [("animated_template_analysis", "started")]


def test_animated_template_manifest_lifecycle(api_client: TestClient, fake_temporal, db_session) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(),
    )

    assert create_response.status_code == 201
    created = create_response.json()
    manifest_id = created["id"]
    assert created["status"] == "needs_review"
    assert created["summary"]["hasCompetitorProductSlot"] is False
    assert created["summary"]["renderableWithoutAi"] is True

    cost_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/cost-estimate",
        json={"outputFormats": ["gif", "webp"], "renderMode": "deterministic"},
    )
    assert cost_response.status_code == 200
    cost_payload = cost_response.json()
    assert cost_payload["costEstimate"]["pricingStatus"] == "not_required"
    assert cost_payload["costEstimate"]["modelCalls"] == 0
    assert cost_payload["renderPlan"]["requiresAiModel"] is False
    assert "chart_line_primary" in cost_payload["renderPlan"]["layersByOwner"]["deterministic_renderer"]

    render_before_approval = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/render",
        json={"outputFormats": ["gif"], "renderMode": "deterministic"},
    )
    assert render_before_approval.status_code == 409
    assert render_before_approval.json()["detail"]["code"] == "MANIFEST_NOT_APPROVED"

    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/approve",
        json={"approvalNotes": "Chart template: no product slot."},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    model_on_deterministic_manifest = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/render",
        json={
            "outputFormats": ["gif"],
            "renderMode": "deterministic",
            "modelSelection": {"provider": "creative_service", "modelId": "sora-2"},
        },
    )
    assert model_on_deterministic_manifest.status_code == 409
    validation = model_on_deterministic_manifest.json()["detail"]["validation"]
    assert validation["blockingErrors"][0]["code"] == "UNUSED_MODEL_SELECTION"

    render_payload = {"outputFormats": ["gif"], "renderMode": "deterministic", "idempotencyKey": "chart-render-1"}
    render_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/render",
        json=render_payload,
    )
    assert render_response.status_code == 202
    render_run = render_response.json()
    assert render_run["status"] == "running"
    assert render_run["temporalWorkflowId"].startswith("swipe-animated-template-render-")
    assert fake_temporal.started == [render_run["temporalWorkflowId"]]

    repeated_render = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/render",
        json=render_payload,
    )
    assert repeated_render.status_code == 202
    assert repeated_render.json()["runId"] == render_run["runId"]
    assert fake_temporal.started == [render_run["temporalWorkflowId"]]

    persisted_render_run = db_session.get(AnimatedTemplateRun, render_run["runId"])
    assert persisted_render_run is not None
    assert persisted_render_run.status == "running"
    persisted_workflow_run = db_session.get(WorkflowRun, render_run["workflowRunId"])
    assert persisted_workflow_run is not None
    assert persisted_workflow_run.kind == WorkflowKindEnum.swipe_animated_template_render

    fetched_run = api_client.get(f"/swipes/animated-templates/runs/{render_run['runId']}")
    assert fetched_run.status_code == 200
    assert fetched_run.json()["runId"] == render_run["runId"]
    listed_runs = api_client.get(f"/swipes/animated-templates/manifests/{manifest_id}/runs")
    assert listed_runs.status_code == 200
    assert [run["runId"] for run in listed_runs.json()] == [render_run["runId"]]


def test_animated_template_cost_estimate_requires_model_for_hybrid_ai_regions(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(manifest=_hybrid_manifest()),
    )
    assert create_response.status_code == 201
    manifest_id = create_response.json()["id"]

    missing_model = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/cost-estimate",
        json={"outputFormats": ["gif"], "renderMode": "hybrid"},
    )
    assert missing_model.status_code == 409
    assert (
        missing_model.json()["detail"]["validation"]["blockingErrors"][0]["code"]
        == "MODEL_SELECTION_REQUIRED"
    )

    with_model = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/cost-estimate",
        json={
            "outputFormats": ["gif"],
            "renderMode": "hybrid",
            "modelSelection": {"provider": "creative_service", "modelId": "sora-2"},
        },
    )
    assert with_model.status_code == 200
    cost = with_model.json()["costEstimate"]
    assert cost["pricingStatus"] == "requires_provider_pricing"
    assert cost["modelCalls"] == 1
    assert cost["modelCostUsd"] is None


def test_animated_template_render_activity_marks_not_implemented_failure(
    api_client: TestClient,
    fake_temporal,
    db_session,
    auth_context,
    monkeypatch,
) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(),
    )
    assert create_response.status_code == 201
    manifest_id = create_response.json()["id"]
    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/approve",
        json={"approvalNotes": "Approved for render failure contract."},
    )
    assert approve_response.status_code == 200
    render_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/render",
        json={"outputFormats": ["gif"], "renderMode": "deterministic"},
    )
    assert render_response.status_code == 202
    render_payload = render_response.json()

    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(swipe_animated_template_activities, "session_scope", _session_scope_override)

    with pytest.raises(RuntimeError, match="deterministic compositor must be implemented"):
        swipe_animated_template_activities.render_animated_template_activity(
            {
                "org_id": auth_context.org_id,
                "manifest_id": manifest_id,
                "run_id": render_payload["runId"],
                "workflow_run_id": render_payload["workflowRunId"],
            }
        )

    db_session.expire_all()
    render_run = db_session.get(AnimatedTemplateRun, render_payload["runId"])
    assert render_run is not None
    assert render_run.status == "failed"
    assert render_run.error_code == "RENDERER_NOT_IMPLEMENTED"
    workflow_run = db_session.get(WorkflowRun, render_payload["workflowRunId"])
    assert workflow_run is not None
    assert workflow_run.status == WorkflowStatusEnum.failed


def test_animated_template_render_activity_persists_source_passthrough_artifact(
    api_client: TestClient,
    fake_temporal,
    db_session,
    auth_context,
    monkeypatch,
) -> None:
    source = _animated_gif_bytes()
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(
            manifest=_source_passthrough_manifest(),
            sourceSha256=hashlib.sha256(source).hexdigest(),
            sourceMimeType="image/gif",
        ),
    )
    assert create_response.status_code == 201
    manifest_id = create_response.json()["id"]
    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/approve",
        json={"approvalNotes": "Source passthrough approved."},
    )
    assert approve_response.status_code == 200
    render_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/render",
        json={"outputFormats": ["gif"], "renderMode": "deterministic"},
    )
    assert render_response.status_code == 202
    render_payload = render_response.json()

    @contextmanager
    def _session_scope_override():
        yield db_session

    class _FakeStorage:
        bucket = "test-bucket"

        def __init__(self) -> None:
            self.uploads: dict[str, bytes] = {}

        def build_key(self, *, sha256: str, ext: str, kind: str = "orig") -> str:
            return f"{kind}/{sha256}.{ext}"

        def object_exists(self, *, bucket: str, key: str) -> bool:
            return key in self.uploads

        def upload_bytes(self, *, bucket: str, key: str, data: bytes, **_kwargs) -> None:
            self.uploads[key] = data

    fake_storage = _FakeStorage()
    monkeypatch.setattr(swipe_animated_template_activities, "session_scope", _session_scope_override)
    monkeypatch.setattr(swipe_animated_template_activities, "MediaStorage", lambda: fake_storage)
    monkeypatch.setattr(
        swipe_animated_template_activities,
        "_resolve_source_media",
        lambda _params: {"content": source, "contentType": "image/gif"},
    )

    result = swipe_animated_template_activities.render_animated_template_activity(
        {
            "org_id": auth_context.org_id,
            "manifest_id": manifest_id,
            "run_id": render_payload["runId"],
            "workflow_run_id": render_payload["workflowRunId"],
        }
    )

    assert result["status"] == "succeeded"
    assert result["outputCount"] == 1
    db_session.expire_all()
    render_run = db_session.get(AnimatedTemplateRun, render_payload["runId"])
    assert render_run is not None
    assert render_run.status == "succeeded"
    assert len(render_run.output_artifact_ids) == 1
    artifact = db_session.get(AnimatedTemplateArtifact, render_run.output_artifact_ids[0])
    assert artifact is not None
    assert artifact.artifact_kind == "rendered_gif"
    assert artifact.content_type == "image/gif"
    assert fake_storage.uploads[artifact.storage_key] == source
    workflow_run = db_session.get(WorkflowRun, render_payload["workflowRunId"])
    assert workflow_run is not None
    assert workflow_run.status == WorkflowStatusEnum.completed


def test_animated_template_ai_region_prompt_is_masked_and_model_agnostic(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(manifest=_hybrid_manifest()),
    )
    assert create_response.status_code == 201
    manifest_id = create_response.json()["id"]
    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/approve",
        json={"approvalNotes": "Hybrid region approved."},
    )
    assert approve_response.status_code == 200

    prompt_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/ai-region-prompt",
        json={
            "outputFormats": ["gif"],
            "renderMode": "hybrid",
            "modelSelection": {"provider": "creative_service", "modelId": "sora-2"},
        },
    )

    assert prompt_response.status_code == 200
    prompt = prompt_response.json()["prompt"]
    assert prompt["promptKind"] == "animated_template_ai_region_generation_v1"
    assert prompt["regionLayerIds"] == ["masked_lifestyle_motion"]
    assert "Do not modify pixels outside the masks" in prompt["user"]
    assert "Do not redraw, reinterpret, move, resize, recolor" in prompt["system"]
    assert "Do not introduce product imagery" in prompt["system"]
    assert "axis_label_y" in prompt["contract"]["lockedLayerIds"]


def test_animated_template_ai_region_prompt_blocks_deterministic_manifest(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(),
    )
    assert create_response.status_code == 201
    manifest_id = create_response.json()["id"]
    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/approve",
        json={"approvalNotes": "Deterministic manifest."},
    )
    assert approve_response.status_code == 200

    prompt_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/ai-region-prompt",
        json={"outputFormats": ["gif"], "renderMode": "deterministic"},
    )

    assert prompt_response.status_code == 409
    assert prompt_response.json()["detail"]["code"] == "ANIMATED_TEMPLATE_AI_PROMPT_BLOCKED"


def test_animated_template_approval_blocks_missing_source_evidence(api_client: TestClient) -> None:
    manifest = _chart_manifest()
    manifest["layers"][0].pop("sourceFrameIndexes")
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(manifest=manifest),
    )
    assert create_response.status_code == 201
    assert create_response.json()["validation"]["warnings"][0]["code"] == "SOURCE_EVIDENCE_RECOMMENDED"

    manifest_id = create_response.json()["id"]
    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/approve",
        json={"approvalNotes": "Should not approve without source evidence."},
    )

    assert approve_response.status_code == 409
    assert (
        approve_response.json()["detail"]["validation"]["blockingErrors"][0]["code"]
        == "SOURCE_EVIDENCE_REQUIRED"
    )


def test_animated_template_manifest_update_reopens_review(api_client: TestClient) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(),
    )
    assert create_response.status_code == 201
    manifest_id = create_response.json()["id"]

    patched_manifest = _chart_manifest()
    patched_manifest["layers"][0]["text"] = "TENOR ENERGY"
    update_response = api_client.patch(
        f"/swipes/animated-templates/manifests/{manifest_id}",
        json={"manifest": patched_manifest, "updateNotes": "Corrected axis copy."},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "needs_review"
    assert updated["manifest"]["layers"][0]["text"] == "TENOR ENERGY"


def test_animated_template_manifest_update_blocks_approved_in_place_edit(api_client: TestClient) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(),
    )
    assert create_response.status_code == 201
    manifest_id = create_response.json()["id"]
    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{manifest_id}/approve",
        json={"approvalNotes": "Approved."},
    )
    assert approve_response.status_code == 200

    patched_manifest = _chart_manifest()
    patched_manifest["layers"][0]["text"] = "TENOR ENERGY"
    update_response = api_client.patch(
        f"/swipes/animated-templates/manifests/{manifest_id}",
        json={"manifest": patched_manifest},
    )

    assert update_response.status_code == 409
    assert (
        update_response.json()["detail"]["code"]
        == "APPROVED_MANIFEST_UPDATE_REQUIRES_SUPERSEDING_VERSION"
    )


def test_animated_template_superseding_manifest_replaces_approved_version(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(),
    )
    assert create_response.status_code == 201
    original_id = create_response.json()["id"]
    approve_response = api_client.post(
        f"/swipes/animated-templates/manifests/{original_id}/approve",
        json={"approvalNotes": "Original approved."},
    )
    assert approve_response.status_code == 200

    replacement_manifest = _chart_manifest()
    replacement_manifest["layers"][0]["text"] = "TENOR ENERGY"
    replacement_response = api_client.post(
        "/swipes/animated-templates/manifests",
        json=_create_manifest_payload(
            manifest=replacement_manifest,
            supersedesManifestId=original_id,
            idempotencyKey="replacement-v1",
        ),
    )
    assert replacement_response.status_code == 201
    replacement_id = replacement_response.json()["id"]
    assert replacement_response.json()["supersedesManifestId"] == original_id

    replacement_approval = api_client.post(
        f"/swipes/animated-templates/manifests/{replacement_id}/approve",
        json={"approvalNotes": "Replacement approved."},
    )
    assert replacement_approval.status_code == 200

    original_after = api_client.get(f"/swipes/animated-templates/manifests/{original_id}")
    assert original_after.status_code == 200
    assert original_after.json()["status"] == "superseded"


def test_animated_template_manifest_create_is_idempotent(api_client: TestClient) -> None:
    payload = _create_manifest_payload(idempotencyKey="chart-template-1")

    first = api_client.post("/swipes/animated-templates/manifests", json=payload)
    second = api_client.post("/swipes/animated-templates/manifests", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_static_swipe_guard_detects_animated_gif() -> None:
    first = Image.new("RGB", (8, 8), "white")
    second = Image.new("RGB", (8, 8), "black")
    animated = io.BytesIO()
    first.save(animated, format="GIF", save_all=True, append_images=[second], duration=100, loop=0)

    assert _is_animated_swipe_image(animated.getvalue(), "image/gif") is True


def test_static_swipe_guard_allows_static_png() -> None:
    image = Image.new("RGB", (8, 8), "white")
    content = io.BytesIO()
    image.save(content, format="PNG")

    assert _is_animated_swipe_image(content.getvalue(), "image/png") is False
