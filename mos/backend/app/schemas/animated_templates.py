from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


AnimatedTemplateStatus = Literal["draft", "needs_review", "approved", "rejected", "superseded"]
AnimatedTemplateLayerPolicy = Literal[
    "locked_source",
    "deterministic_rebuild",
    "editable_text",
    "product_swap",
    "generative_region",
]
AnimatedTemplateRenderOwner = Literal[
    "source_pixels",
    "deterministic_renderer",
    "product_compositor",
    "ai_region_model",
]


class AnimatedTemplateEvidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    kind: str
    source_frame_indexes: list[int] = Field(
        default_factory=list,
        validation_alias="sourceFrameIndexes",
        serialization_alias="sourceFrameIndexes",
    )
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnimatedTemplateBox(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    x: float
    y: float
    width: float
    height: float
    rotation: float = 0

    @model_validator(mode="after")
    def _validate_dimensions(self) -> "AnimatedTemplateBox":
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Layer geometry width and height must be positive.")
        return self


class AnimatedTemplateMask(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    kind: Literal["box", "polygon", "alpha_asset"]
    box: AnimatedTemplateBox | None = None
    polygon: list[tuple[float, float]] | None = None
    asset_storage_key: str | None = Field(
        None,
        validation_alias="assetStorageKey",
        serialization_alias="assetStorageKey",
    )
    sha256: str | None = None

    @model_validator(mode="after")
    def _validate_mask_shape(self) -> "AnimatedTemplateMask":
        if self.kind == "box" and self.box is None:
            raise ValueError("box masks require box geometry.")
        if self.kind == "polygon" and not self.polygon:
            raise ValueError("polygon masks require polygon coordinates.")
        if self.kind == "alpha_asset" and not self.asset_storage_key:
            raise ValueError("alpha_asset masks require assetStorageKey.")
        return self


class AnimatedTemplateProductSlot(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    status: Literal["candidate", "approved", "rejected", "not_detected", "uncertain"] = "candidate"
    geometry: AnimatedTemplateBox | None = None
    mask: AnimatedTemplateMask | None = None
    evidence: list[AnimatedTemplateEvidence] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class AnimatedTemplateProductReplacement(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    has_competitor_product_slot: bool = Field(
        False,
        validation_alias="hasCompetitorProductSlot",
        serialization_alias="hasCompetitorProductSlot",
    )
    slots: list[AnimatedTemplateProductSlot] = Field(default_factory=list)
    negative_evidence: list[AnimatedTemplateEvidence] = Field(
        default_factory=list,
        validation_alias="negativeEvidence",
        serialization_alias="negativeEvidence",
    )

    @model_validator(mode="after")
    def _validate_product_slot_evidence(self) -> "AnimatedTemplateProductReplacement":
        approved_slots = [slot for slot in self.slots if slot.status == "approved"]
        if self.has_competitor_product_slot and not approved_slots:
            raise ValueError("hasCompetitorProductSlot requires at least one approved product slot.")
        if not self.has_competitor_product_slot and approved_slots:
            raise ValueError("Approved product slots require hasCompetitorProductSlot=true.")
        for slot in approved_slots:
            if slot.geometry is None and slot.mask is None:
                raise ValueError("Approved product slots require geometry or a mask.")
            if not slot.evidence:
                raise ValueError("Approved product slots require source evidence.")
        return self


class AnimatedTemplateLayer(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    type: str
    policy: AnimatedTemplateLayerPolicy
    render_owner: AnimatedTemplateRenderOwner = Field(
        "deterministic_renderer",
        validation_alias="renderOwner",
        serialization_alias="renderOwner",
    )
    role: str | None = None
    geometry: AnimatedTemplateBox | None = None
    mask: AnimatedTemplateMask | None = None
    text: str | None = None
    product_slot_id: str | None = Field(
        None,
        validation_alias="productSlotId",
        serialization_alias="productSlotId",
    )
    source_frame_indexes: list[int] = Field(
        default_factory=list,
        validation_alias="sourceFrameIndexes",
        serialization_alias="sourceFrameIndexes",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_layer_policy(self) -> "AnimatedTemplateLayer":
        if self.policy == "generative_region" and self.mask is None:
            raise ValueError("generative_region layers require a mask.")
        if self.policy != "generative_region" and self.render_owner == "ai_region_model":
            raise ValueError("Locked layers cannot be assigned to ai_region_model.")
        if self.policy == "product_swap" and not self.product_slot_id:
            raise ValueError("product_swap layers require productSlotId.")
        return self


class AnimatedTemplateManifestDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: int = Field(
        1,
        ge=1,
        validation_alias="schemaVersion",
        serialization_alias="schemaVersion",
    )
    canvas: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, Any] = Field(default_factory=dict)
    layers: list[AnimatedTemplateLayer] = Field(default_factory=list)
    product_replacement: AnimatedTemplateProductReplacement = Field(
        default_factory=AnimatedTemplateProductReplacement,
        validation_alias="productReplacement",
        serialization_alias="productReplacement",
    )
    text_roles: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="textRoles",
        serialization_alias="textRoles",
    )
    color_roles: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="colorRoles",
        serialization_alias="colorRoles",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_manifest(self) -> "AnimatedTemplateManifestDocument":
        layer_ids = [layer.id for layer in self.layers]
        if len(layer_ids) != len(set(layer_ids)):
            raise ValueError("Animated template layer IDs must be unique.")
        product_slot_ids = {slot.id for slot in self.product_replacement.slots}
        for layer in self.layers:
            if layer.product_slot_id and layer.product_slot_id not in product_slot_ids:
                raise ValueError(f"Layer {layer.id} references an unknown productSlotId.")
            if (
                layer.policy == "product_swap"
                and not self.product_replacement.has_competitor_product_slot
            ):
                raise ValueError("product_swap layers require source product-slot evidence.")
        return self


class AnimatedTemplateSourcePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    company_swipe_id: str | None = Field(
        None,
        validation_alias="companySwipeId",
        serialization_alias="companySwipeId",
    )
    company_swipe_media_id: str | None = Field(
        None,
        validation_alias="companySwipeMediaId",
        serialization_alias="companySwipeMediaId",
    )
    source_url: str | None = Field(
        None,
        validation_alias="sourceUrl",
        serialization_alias="sourceUrl",
    )
    source_label: str | None = Field(
        None,
        validation_alias="sourceLabel",
        serialization_alias="sourceLabel",
    )
    source_sha256: str = Field(
        ...,
        min_length=16,
        validation_alias="sourceSha256",
        serialization_alias="sourceSha256",
    )
    source_mime_type: str = Field(
        ...,
        validation_alias="sourceMimeType",
        serialization_alias="sourceMimeType",
    )

    @model_validator(mode="after")
    def _validate_source(self) -> "AnimatedTemplateSourcePayload":
        if bool(self.company_swipe_id) == bool(self.source_url):
            raise ValueError("Provide exactly one of companySwipeId or sourceUrl.")
        if self.company_swipe_media_id and not self.company_swipe_id:
            raise ValueError("companySwipeMediaId requires companySwipeId.")
        return self


class AnimatedTemplateManifestCreateRequest(AnimatedTemplateSourcePayload):
    client_id: str | None = Field(
        None,
        validation_alias="clientId",
        serialization_alias="clientId",
    )
    product_id: str | None = Field(
        None,
        validation_alias="productId",
        serialization_alias="productId",
    )
    campaign_id: str | None = Field(
        None,
        validation_alias="campaignId",
        serialization_alias="campaignId",
    )
    workflow_run_id: str | None = Field(
        None,
        validation_alias="workflowRunId",
        serialization_alias="workflowRunId",
    )
    analyzer_version: str = Field(
        "manual_manifest_v1",
        validation_alias="analyzerVersion",
        serialization_alias="analyzerVersion",
    )
    idempotency_key: str | None = Field(
        None,
        validation_alias="idempotencyKey",
        serialization_alias="idempotencyKey",
    )
    supersedes_manifest_id: str | None = Field(
        None,
        validation_alias="supersedesManifestId",
        serialization_alias="supersedesManifestId",
    )
    manifest: AnimatedTemplateManifestDocument


class AnimatedTemplateManifestApprovalRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    approval_notes: str | None = Field(
        None,
        validation_alias="approvalNotes",
        serialization_alias="approvalNotes",
    )


class AnimatedTemplateManifestUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    manifest: AnimatedTemplateManifestDocument
    update_notes: str | None = Field(
        None,
        validation_alias="updateNotes",
        serialization_alias="updateNotes",
    )


class AnimatedTemplateManifestRejectRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    reason: str = Field(..., min_length=1)


class AnimatedTemplateRenderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    output_formats: list[Literal["gif", "webp", "mp4"]] = Field(
        default_factory=lambda: ["gif"],
        validation_alias="outputFormats",
        serialization_alias="outputFormats",
    )
    render_mode: Literal["deterministic", "hybrid"] = Field(
        "deterministic",
        validation_alias="renderMode",
        serialization_alias="renderMode",
    )
    model_selection: dict[str, Any] | None = Field(
        None,
        validation_alias="modelSelection",
        serialization_alias="modelSelection",
    )
    product_replacement_requested: bool = Field(
        False,
        validation_alias="productReplacementRequested",
        serialization_alias="productReplacementRequested",
    )
    final_copy: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="finalCopy",
        serialization_alias="finalCopy",
    )
    idempotency_key: str | None = Field(
        None,
        validation_alias="idempotencyKey",
        serialization_alias="idempotencyKey",
    )

    @model_validator(mode="after")
    def _validate_output_formats(self) -> "AnimatedTemplateRenderRequest":
        if len(set(self.output_formats)) != len(self.output_formats):
            raise ValueError("outputFormats must be unique.")
        return self


class AnimatedTemplateAnalyzeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    company_swipe_id: str | None = Field(
        None,
        validation_alias="companySwipeId",
        serialization_alias="companySwipeId",
    )
    company_swipe_media_id: str | None = Field(
        None,
        validation_alias="companySwipeMediaId",
        serialization_alias="companySwipeMediaId",
    )
    source_url: str | None = Field(
        None,
        validation_alias="sourceUrl",
        serialization_alias="sourceUrl",
    )
    source_label: str | None = Field(
        None,
        validation_alias="sourceLabel",
        serialization_alias="sourceLabel",
    )
    client_id: str | None = Field(
        None,
        validation_alias="clientId",
        serialization_alias="clientId",
    )
    product_id: str | None = Field(
        None,
        validation_alias="productId",
        serialization_alias="productId",
    )
    campaign_id: str | None = Field(
        None,
        validation_alias="campaignId",
        serialization_alias="campaignId",
    )
    analyzer_version: str | None = Field(
        None,
        validation_alias="analyzerVersion",
        serialization_alias="analyzerVersion",
    )
    idempotency_key: str | None = Field(
        None,
        validation_alias="idempotencyKey",
        serialization_alias="idempotencyKey",
    )

    @model_validator(mode="after")
    def _validate_source(self) -> "AnimatedTemplateAnalyzeRequest":
        if bool(self.company_swipe_id) == bool(self.source_url):
            raise ValueError("Provide exactly one of companySwipeId or sourceUrl.")
        if self.company_swipe_media_id and not self.company_swipe_id:
            raise ValueError("companySwipeMediaId requires companySwipeId.")
        return self


class AnimatedTemplateWorkflowStartResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    workflow_run_id: str = Field(..., validation_alias="workflowRunId", serialization_alias="workflowRunId")
    temporal_workflow_id: str = Field(
        ...,
        validation_alias="temporalWorkflowId",
        serialization_alias="temporalWorkflowId",
    )


class AnimatedTemplateRenderRunResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    run_id: str | UUID = Field(validation_alias="runId", serialization_alias="runId")
    manifest_id: str | UUID = Field(validation_alias="manifestId", serialization_alias="manifestId")
    status: str
    workflow_run_id: str | UUID | None = Field(
        None,
        validation_alias="workflowRunId",
        serialization_alias="workflowRunId",
    )
    temporal_workflow_id: str | None = Field(
        None,
        validation_alias="temporalWorkflowId",
        serialization_alias="temporalWorkflowId",
    )
    render_plan: dict[str, Any] = Field(
        validation_alias="renderPlan",
        serialization_alias="renderPlan",
    )
    cost_estimate: dict[str, Any] = Field(
        validation_alias="costEstimate",
        serialization_alias="costEstimate",
    )
    output_artifact_ids: list[str] = Field(
        default_factory=list,
        validation_alias="outputArtifactIds",
        serialization_alias="outputArtifactIds",
    )


class AnimatedTemplateCostEstimateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    manifest_id: str | UUID = Field(validation_alias="manifestId", serialization_alias="manifestId")
    validation: dict[str, Any]
    render_plan: dict[str, Any] = Field(
        validation_alias="renderPlan",
        serialization_alias="renderPlan",
    )
    cost_estimate: dict[str, Any] = Field(
        validation_alias="costEstimate",
        serialization_alias="costEstimate",
    )


class AnimatedTemplateAiRegionPromptResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    manifest_id: str | UUID = Field(validation_alias="manifestId", serialization_alias="manifestId")
    prompt: dict[str, Any]


class AnimatedTemplateValidationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    status: Literal["valid", "valid_with_review", "invalid"]
    blocking_errors: list[dict[str, Any]] = Field(
        default_factory=list,
        validation_alias="blockingErrors",
        serialization_alias="blockingErrors",
    )
    review_reasons: list[str] = Field(
        default_factory=list,
        validation_alias="reviewReasons",
        serialization_alias="reviewReasons",
    )
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class AnimatedTemplateManifestResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str | UUID
    org_id: str | UUID = Field(validation_alias="orgId", serialization_alias="orgId")
    client_id: str | UUID | None = Field(None, validation_alias="clientId", serialization_alias="clientId")
    product_id: str | UUID | None = Field(
        None,
        validation_alias="productId",
        serialization_alias="productId",
    )
    campaign_id: str | UUID | None = Field(
        None,
        validation_alias="campaignId",
        serialization_alias="campaignId",
    )
    company_swipe_id: str | UUID | None = Field(
        None,
        validation_alias="companySwipeId",
        serialization_alias="companySwipeId",
    )
    company_swipe_media_id: str | UUID | None = Field(
        None,
        validation_alias="companySwipeMediaId",
        serialization_alias="companySwipeMediaId",
    )
    source_kind: str = Field(validation_alias="sourceKind", serialization_alias="sourceKind")
    source_url: str | None = Field(None, validation_alias="sourceUrl", serialization_alias="sourceUrl")
    source_label: str | None = Field(
        None,
        validation_alias="sourceLabel",
        serialization_alias="sourceLabel",
    )
    source_sha256: str = Field(validation_alias="sourceSha256", serialization_alias="sourceSha256")
    source_mime_type: str = Field(
        validation_alias="sourceMimeType",
        serialization_alias="sourceMimeType",
    )
    manifest_schema_version: int = Field(
        validation_alias="manifestSchemaVersion",
        serialization_alias="manifestSchemaVersion",
    )
    analyzer_version: str = Field(
        validation_alias="analyzerVersion",
        serialization_alias="analyzerVersion",
    )
    status: AnimatedTemplateStatus
    manifest_sha256: str = Field(
        validation_alias="manifestSha256",
        serialization_alias="manifestSha256",
    )
    manifest: dict[str, Any]
    validation: dict[str, Any]
    summary: dict[str, Any]
    approved_by_user_id: str | None = Field(
        None,
        validation_alias="approvedByUserId",
        serialization_alias="approvedByUserId",
    )
    approved_at: datetime | None = Field(
        None,
        validation_alias="approvedAt",
        serialization_alias="approvedAt",
    )
    rejected_by_user_id: str | None = Field(
        None,
        validation_alias="rejectedByUserId",
        serialization_alias="rejectedByUserId",
    )
    rejected_at: datetime | None = Field(
        None,
        validation_alias="rejectedAt",
        serialization_alias="rejectedAt",
    )
    rejection_reason: str | None = Field(
        None,
        validation_alias="rejectionReason",
        serialization_alias="rejectionReason",
    )
    supersedes_manifest_id: str | UUID | None = Field(
        None,
        validation_alias="supersedesManifestId",
        serialization_alias="supersedesManifestId",
    )
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")
