from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StorefrontTemplateBindingRequirement(BaseModel):
    key: str
    label: str
    source: str
    description: str
    required: bool = True


class StorefrontTemplateStylePolicy(BaseModel):
    lockedTokenGroups: list[str] = Field(default_factory=list)
    editableTokenGroups: list[str] = Field(default_factory=list)


class StorefrontTemplateImportProvenance(BaseModel):
    sourceType: str
    sourceTemplateId: str
    notes: list[str] = Field(default_factory=list)


class StorefrontTemplateSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    previewImage: str | None = None
    family: str
    variant: str
    version: str
    pageType: str
    configSlots: list[str] = Field(default_factory=list)
    requiredBindingKeys: list[str] = Field(default_factory=list)


class StorefrontTemplateDetail(StorefrontTemplateSummary):
    requiredBindings: list[StorefrontTemplateBindingRequirement] = Field(default_factory=list)
    stylePolicy: StorefrontTemplateStylePolicy
    importProvenance: StorefrontTemplateImportProvenance
    puckData: dict[str, Any]


class StorefrontBindingPreviewRequirement(BaseModel):
    key: str
    label: str
    source: str
    required: bool
    status: str
    detail: str


class StorefrontBindingPreviewResponse(BaseModel):
    templateId: str
    clientId: str
    productId: str | None = None
    productTitle: str | None = None
    variantId: str | None = None
    variantTitle: str | None = None
    variantProvider: str | None = None
    ready: bool
    requirements: list[StorefrontBindingPreviewRequirement] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# Site Import Schemas
class ThemePalette(BaseModel):
    primary: str | None = None
    secondary: str | None = None
    surface: str | None = None
    accent: str | None = None
    text: str | None = None
    background: str | None = None


class ThemeFonts(BaseModel):
    heading: str | None = None
    body: str | None = None
    cta: str | None = None


class ThemeSpacing(BaseModel):
    density: str = "comfortable"
    scale: list[str] = Field(default_factory=list)


class ThemeCTA(BaseModel):
    style: str = "solid"
    borderRadius: str | None = None
    padding: str | None = None


class ThemeCandidate(BaseModel):
    palette: ThemePalette = Field(default_factory=ThemePalette)
    fonts: ThemeFonts = Field(default_factory=ThemeFonts)
    spacing: ThemeSpacing = Field(default_factory=ThemeSpacing)
    cta: ThemeCTA = Field(default_factory=ThemeCTA)


class NormalizedSection(BaseModel):
    id: str
    sectionType: str
    confidence: float
    keyText: list[str] = Field(default_factory=list)
    keyMedia: list[str] = Field(default_factory=list)
    keyStyles: dict[str, Any] = Field(default_factory=dict)
    boundingBox: dict[str, float] | None = None


class SiteImportSummary(BaseModel):
    id: str
    sourceUrl: str
    sourceHostname: str | None = None
    pageTypeHint: str | None = None
    status: str
    title: str | None = None
    suggestedTemplateFamily: str | None = None
    createdAt: datetime
    updatedAt: datetime


class SiteImportDetail(BaseModel):
    id: str
    sourceUrl: str
    sourceHostname: str | None = None
    pageTypeHint: str | None = None
    status: str
    title: str | None = None
    metaDescription: str | None = None
    suggestedTemplateFamily: str | None = None
    themeCandidate: dict[str, Any] = Field(default_factory=dict)
    normalizedSections: list[NormalizedSection] = Field(default_factory=list)
    synthesis: SynthesisOutput | None = None
    captureError: str | None = None
    createdAt: datetime
    updatedAt: datetime


class SiteImportSnapshotResponse(BaseModel):
    id: str
    htmlSnapshot: str
    desktopScreenshotDataUrl: str
    mobileScreenshotDataUrl: str
    captureMetadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime


class CreateSiteImportRequest(BaseModel):
    sourceUrl: str = Field(..., min_length=1, description="URL of the site to import")
    pageTypeHint: str | None = None


class ConvertImportRequest(BaseModel):
    name: str
    family: str
    pageType: str
    acceptedSectionIds: list[str]
    reviewNotes: str | None = None


class TemplateVariantSummary(BaseModel):
    id: str
    name: str
    family: str
    pageType: str
    status: str
    sourceType: str | None = None
    parentVariantId: str | None = None
    mutationPresetLabel: str | None = None
    createdAt: datetime
    updatedAt: datetime


class TemplateVariantDetail(BaseModel):
    id: str
    name: str
    family: str
    pageType: str
    status: str
    siteImportId: str | None = None
    stylePresetId: str | None = None
    acceptedSections: list[NormalizedSection] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    reviewNotes: str | None = None
    createdAt: datetime
    updatedAt: datetime


class TemplateStylePresetResponse(BaseModel):
    id: str
    name: str
    status: str
    tokens: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
    updatedAt: datetime


# Synthesis Schemas
class BlockCoverageDetail(BaseModel):
    sectionId: str
    sectionType: str
    mappedBlock: str | None = None
    coverage: str  # "exact", "partial", "missing"
    confidence: float


class BlockCoverageSummary(BaseModel):
    totalSections: int
    exactMatches: int
    partialMatches: int
    missingMatches: int
    coverageScore: float


class MissingBlockRequest(BaseModel):
    requestId: str
    sectionType: str
    reason: str
    sourceSelector: str | None = None
    textPreview: str | None = None
    suggestedFamily: str
    suggestedPageType: str


class SynthesisOutput(BaseModel):
    """Synthesis output included in import detail and convert responses."""

    targetFamily: str
    targetPageType: str
    blockCoverage: BlockCoverageSummary
    blockCoverageDetails: list[BlockCoverageDetail] = Field(default_factory=list)
    missingBlockRequests: list[MissingBlockRequest] = Field(default_factory=list)
    synthesizedPuckData: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Variant Mutation Preset Schemas
# =============================================================================


class MutationPresetSummary(BaseModel):
    """Summary of a mutation preset."""

    id: str
    label: str
    description: str
    families: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)


class MutationPresetPreview(BaseModel):
    """Preview of a preset's applicability for a variant."""

    presetId: str
    presetLabel: str
    presetDescription: str
    applicable: bool
    notApplicableReason: str | None = None
    effects: list[str] = Field(default_factory=list)


class VariantProvenance(BaseModel):
    """Provenance information for a variant."""

    sourceType: str
    sourceUrl: str | None = None
    sourceHostname: str | None = None
    importedAt: str | None = None
    pageTypeHint: str | None = None
    parentVariantId: str | None = None
    parentVariantName: str | None = None
    mutationPresetId: str | None = None
    mutationPresetLabel: str | None = None
    mutationSummary: str | None = None
    synthesis: dict[str, Any] | None = None


class TemplateVariantDetailExtended(TemplateVariantDetail):
    """Extended variant detail with synthesized puckData."""

    synthesizedPuckData: dict[str, Any] | None = None


class GenerateVariantsRequest(BaseModel):
    """Request to generate derived variants from a base variant."""

    presetIds: list[str] = Field(..., min_length=1, description="List of preset IDs to apply")
    generatedNames: list[str] | None = Field(
        None, description="Optional names for each generated variant"
    )


class GeneratedVariantSummary(BaseModel):
    """Summary of a generated variant."""

    id: str
    name: str
    family: str
    pageType: str
    status: str
    parentVariantId: str
    mutationPresetId: str
    mutationPresetLabel: str
    mutationSummary: str
    createdAt: datetime
    updatedAt: datetime


class GenerateVariantsResponse(BaseModel):
    """Response from generating derived variants."""

    generatedVariants: list[GeneratedVariantSummary] = Field(default_factory=list)


# =============================================================================
# Governance Schemas (Phase 5)
# =============================================================================


class AssetValidationResult(BaseModel):
    """Result of validating a single asset reference."""

    publicId: str
    fieldPath: list[str] = Field(default_factory=list)
    blockType: str | None = None
    blockId: str | None = None
    status: str  # "approved", "pending", "rejected", "not_found"
    assetId: str | None = None


class StyleAuditFinding(BaseModel):
    """A single style audit finding."""

    checkId: str
    status: str
    message: str
    location: str
    foreground: str | None = None
    background: str | None = None
    contrastRatio: float | None = None
    threshold: float | None = None


class StyleAuditResult(BaseModel):
    """Result of style preset audit."""

    presetId: str | None = None
    presetName: str | None = None
    findings: list[StyleAuditFinding] = Field(default_factory=list)
    passed: bool


class PuckDataStructureResult(BaseModel):
    """Result of puckData structure validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProvenanceEvent(BaseModel):
    """A single provenance event."""

    eventType: str
    timestamp: str
    actor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceReport(BaseModel):
    """Complete governance report for a variant."""

    variantId: str
    readyForPublish: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assetValidations: list[AssetValidationResult] = Field(default_factory=list)
    styleAudit: StyleAuditResult | None = None
    puckDataStructure: PuckDataStructureResult | None = None
    provenanceEvents: list[ProvenanceEvent] = Field(default_factory=list)


class ApproveForPublishRequest(BaseModel):
    """Request to approve a variant for publish."""

    pass


class ApproveForPublishResponse(BaseModel):
    """Response from approving a variant for publish."""

    variantId: str
    status: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    governanceReport: GovernanceReport


# =============================================================================
# Create Draft from Template Schemas
# =============================================================================


class CreateDraftFromTemplateRequest(BaseModel):
    """Request to create a draft variant from a built-in storefront template."""

    name: str = Field(..., min_length=1, description="Name for the draft variant")
    productId: str = Field(..., description="Product ID for binding")
    variantId: str = Field(..., description="Product variant ID for binding")
    reviewNotes: str | None = Field(None, description="Optional review notes")


class CreateDraftFromTemplateResponse(BaseModel):
    """Response from creating a draft variant from a built-in template."""

    variant: TemplateVariantDetailExtended
    bindingPreview: StorefrontBindingPreviewResponse
