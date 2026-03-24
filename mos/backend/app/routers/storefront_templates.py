from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Client, Product, ProductVariant
from app.schemas.storefront_templates import (
    ApproveForPublishRequest,
    ApproveForPublishResponse,
    AssetValidationResult,
    BlockCoverageDetail,
    BlockCoverageSummary,
    ConvertImportRequest,
    CreateDraftFromTemplateRequest,
    CreateDraftFromTemplateResponse,
    CreateSiteImportRequest,
    GenerateVariantsRequest,
    GenerateVariantsResponse,
    GeneratedVariantSummary,
    GovernanceReport,
    MissingBlockRequest,
    MutationPresetPreview,
    MutationPresetSummary,
    NormalizedSection,
    ProvenanceEvent,
    PuckDataStructureResult,
    SiteImportDetail,
    SiteImportSnapshotResponse,
    SiteImportSummary,
    StorefrontBindingPreviewRequirement,
    StorefrontBindingPreviewResponse,
    StorefrontTemplateBindingRequirement,
    StorefrontTemplateDetail,
    StorefrontTemplateImportProvenance,
    StorefrontTemplateStylePolicy,
    StorefrontTemplateSummary,
    StyleAuditFinding,
    StyleAuditResult,
    SynthesisOutput,
    TemplateStylePresetResponse,
    TemplateVariantDetail,
    TemplateVariantDetailExtended,
    TemplateVariantSummary,
)
from app.services.medusa_storefront_bindings import build_storefront_binding_preview
from app.services.site_imports import (
    SiteImportError,
    convert_import_to_variant,
    convert_import_to_variant_with_synthesis,
    create_draft_from_template,
    create_import_job,
    get_import_detail,
    get_import_snapshot,
    get_import_synthesis,
    list_imports,
    list_variant_drafts,
)
from app.services.storefront_templates import (
    StorefrontTemplateDescriptor,
    get_storefront_template,
    list_storefront_templates,
)
from app.db.repositories.storefront_imports import StorefrontImportsRepository
from app.db.repositories.assets import AssetsRepository
from app.services.template_synthesis import UnsupportedFamilyError
from app.services.template_variant_governance import (
    compute_governance_report,
    build_approval_provenance,
)
from app.services.medusa_connection import get_client_medusa_config

router = APIRouter(prefix="/storefront/templates", tags=["storefront"])


def _get_workspace_or_404(session: Session, client_id: str, org_id: str) -> Client:
    """Validate workspace exists and belongs to the org."""
    # Validate client_id is a valid UUID format before DB query
    try:
        uuid.UUID(client_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    client = session.scalars(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    ).first()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return client


def _validate_import_id(import_id: str) -> None:
    """Validate import_id is a valid UUID format."""
    try:
        uuid.UUID(import_id)
    except (ValueError, AttributeError):
        # Return 404 for invalid ID format - the resource simply doesn't exist
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import not found.",
        )


# =============================================================================
# Site Import Endpoints - must come before template routes to avoid /imports
# being matched as /{template_id}
# =============================================================================


@router.post("/imports", response_model=SiteImportSummary, status_code=status.HTTP_201_CREATED)
async def create_import(
    request: CreateSiteImportRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportSummary:
    """Create a new site import job."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate URL format - return 422 for malformed URLs
    try:
        from app.services.site_imports import _validate_url

        _validate_url(request.sourceUrl)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    import_job = await create_import_job(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        source_url=request.sourceUrl,
        page_type_hint=request.pageTypeHint,
        created_by_user_external_id=auth.user_id,
    )

    return SiteImportSummary(
        id=str(import_job.id),
        sourceUrl=import_job.source_url,
        sourceHostname=import_job.source_hostname,
        pageTypeHint=import_job.page_type_hint,
        status=import_job.status,
        title=import_job.title,
        suggestedTemplateFamily=import_job.suggested_template_family,
        createdAt=import_job.created_at,
        updatedAt=import_job.updated_at,
    )


@router.get("/imports", response_model=list[SiteImportSummary])
def list_imports_endpoint(
    clientId: str,
    limit: int = 25,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteImportSummary]:
    """List site imports for a workspace."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    imports = list_imports(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        limit=limit,
    )

    return [
        SiteImportSummary(
            id=str(imp.id),
            sourceUrl=imp.source_url,
            sourceHostname=imp.source_hostname,
            pageTypeHint=imp.page_type_hint,
            status=imp.status,
            title=imp.title,
            suggestedTemplateFamily=imp.suggested_template_family,
            createdAt=imp.created_at,
            updatedAt=imp.updated_at,
        )
        for imp in imports
    ]


@router.get("/imports/{import_id}", response_model=SiteImportDetail)
def get_import_detail_endpoint(
    import_id: str,
    clientId: str,
    targetFamily: str | None = None,
    targetPageType: str | None = None,
    acceptedSectionIds: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportDetail:
    """Get detailed import information including normalized sections, theme candidate, and synthesis output."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate import_id format before DB query
    _validate_import_id(import_id)

    site_import = get_import_detail(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        site_import_id=import_id,
    )
    if site_import is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found.")

    normalized_sections = [
        NormalizedSection(
            id=s.get("id", ""),
            sectionType=s.get("sectionType", "generic_content"),
            confidence=s.get("confidence", 0.0),
            keyText=s.get("keyText", []),
            keyMedia=s.get("keyMedia", []),
            keyStyles=s.get("keyStyles", {}),
            boundingBox=s.get("boundingBox"),
        )
        for s in (site_import.normalized_sections or [])
    ]

    # Parse accepted section IDs if provided
    parsed_accepted_section_ids: list[str] | None = None
    if acceptedSectionIds:
        parsed_accepted_section_ids = acceptedSectionIds.split(",")

    # Get synthesis if import is completed
    synthesis_output: SynthesisOutput | None = None
    if site_import.status == "completed":
        try:
            synthesis = get_import_synthesis(
                session,
                org_id=auth.org_id,
                client_id=clientId,
                site_import_id=import_id,
                target_family=targetFamily,
                target_page_type=targetPageType,
                accepted_section_ids=parsed_accepted_section_ids,
            )
        except (UnsupportedFamilyError, SiteImportError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        if synthesis:
            synthesis_output = SynthesisOutput(
                targetFamily=synthesis.targetFamily,
                targetPageType=synthesis.targetPageType,
                blockCoverage=BlockCoverageSummary(
                    totalSections=synthesis.blockCoverage.totalSections,
                    exactMatches=synthesis.blockCoverage.exactMatches,
                    partialMatches=synthesis.blockCoverage.partialMatches,
                    missingMatches=synthesis.blockCoverage.missingMatches,
                    coverageScore=synthesis.blockCoverage.coverageScore,
                ),
                blockCoverageDetails=[
                    BlockCoverageDetail(
                        sectionId=d.sectionId,
                        sectionType=d.sectionType,
                        mappedBlock=d.mappedBlock,
                        coverage=d.coverage,
                        confidence=d.confidence,
                    )
                    for d in synthesis.blockCoverageDetails
                ],
                missingBlockRequests=[
                    MissingBlockRequest(
                        requestId=r.requestId,
                        sectionType=r.sectionType,
                        reason=r.reason,
                        sourceSelector=r.sourceSelector,
                        textPreview=r.textPreview,
                        suggestedFamily=r.suggestedFamily,
                        suggestedPageType=r.suggestedPageType,
                    )
                    for r in synthesis.missingBlockRequests
                ],
                synthesizedPuckData=synthesis.synthesizedPuckData,
            )

    return SiteImportDetail(
        id=str(site_import.id),
        sourceUrl=site_import.source_url,
        sourceHostname=site_import.source_hostname,
        pageTypeHint=site_import.page_type_hint,
        status=site_import.status,
        title=site_import.title,
        metaDescription=site_import.meta_description,
        suggestedTemplateFamily=site_import.suggested_template_family,
        themeCandidate=site_import.theme_candidate or {},
        normalizedSections=normalized_sections,
        captureError=site_import.capture_error,
        createdAt=site_import.created_at,
        updatedAt=site_import.updated_at,
        synthesis=synthesis_output,
    )


@router.get("/imports/{import_id}/snapshot", response_model=SiteImportSnapshotResponse)
def get_import_snapshot_endpoint(
    import_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportSnapshotResponse:
    """Get the snapshot for an import including screenshots."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate import_id format before DB query
    _validate_import_id(import_id)

    site_import = get_import_detail(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        site_import_id=import_id,
    )
    if site_import is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found.")

    snapshot = get_import_snapshot(session, site_import_id=import_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found.")

    return SiteImportSnapshotResponse(
        id=str(snapshot.id),
        htmlSnapshot=snapshot.html_snapshot,
        desktopScreenshotDataUrl=snapshot.desktop_screenshot_data_url,
        mobileScreenshotDataUrl=snapshot.mobile_screenshot_data_url,
        captureMetadata=snapshot.capture_metadata,
        createdAt=snapshot.created_at,
    )


@router.post("/imports/{import_id}/convert", response_model=TemplateVariantDetail)
def convert_import_endpoint(
    import_id: str,
    request: ConvertImportRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TemplateVariantDetail:
    """Convert an import into a draft template variant with synthesis."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate import_id format before DB query
    _validate_import_id(import_id)

    # Validate acceptedSectionIds is non-empty
    if not request.acceptedSectionIds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="acceptedSectionIds must contain at least one section ID",
        )

    try:
        result = convert_import_to_variant_with_synthesis(
            session,
            org_id=auth.org_id,
            client_id=clientId,
            site_import_id=import_id,
            name=request.name,
            family=request.family,
            page_type=request.pageType,
            accepted_section_ids=request.acceptedSectionIds,
            review_notes=request.reviewNotes,
            created_by_user_external_id=auth.user_id,
        )
    except (SiteImportError, UnsupportedFamilyError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    variant = result["variant"]
    style_preset = result["style_preset"]

    accepted_sections = [
        NormalizedSection(
            id=s.get("id", ""),
            sectionType=s.get("sectionType", "generic_content"),
            confidence=s.get("confidence", 0.0),
            keyText=s.get("keyText", []),
            keyMedia=s.get("keyMedia", []),
            keyStyles=s.get("keyStyles", {}),
            boundingBox=s.get("boundingBox"),
        )
        for s in (variant.accepted_sections or [])
    ]

    return TemplateVariantDetail(
        id=str(variant.id),
        name=variant.name,
        family=variant.family,
        pageType=variant.page_type,
        status=variant.status,
        siteImportId=str(variant.site_import_id) if variant.site_import_id else None,
        stylePresetId=str(style_preset.id) if style_preset else None,
        acceptedSections=accepted_sections,
        provenance=variant.provenance or {},
        reviewNotes=variant.review_notes,
        createdAt=variant.created_at,
        updatedAt=variant.updated_at,
    )


@router.get("/variants", response_model=list[TemplateVariantSummary])
def list_variants_endpoint(
    clientId: str,
    limit: int = 25,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[TemplateVariantSummary]:
    """List template variant drafts for a workspace."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    variants = list_variant_drafts(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        limit=limit,
    )

    return [
        TemplateVariantSummary(
            id=str(v.id),
            name=v.name,
            family=v.family,
            pageType=v.page_type,
            status=v.status,
            sourceType=(v.provenance or {}).get("source_type"),
            parentVariantId=(v.provenance or {}).get("parent_variant_id"),
            mutationPresetLabel=(v.provenance or {}).get("mutation_preset_label"),
            createdAt=v.created_at,
            updatedAt=v.updated_at,
        )
        for v in variants
    ]


def _validate_variant_id(variant_id: str) -> None:
    """Validate variant_id is a valid UUID format."""
    try:
        uuid.UUID(variant_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found.",
        )


@router.get("/variants/{variant_id}", response_model=TemplateVariantDetailExtended)
def get_variant_detail_endpoint(
    variant_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TemplateVariantDetailExtended:
    """Get detailed information about a specific variant."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate variant_id format
    _validate_variant_id(variant_id)

    repo = StorefrontImportsRepository(session)
    variant = repo.get_variant(org_id=auth.org_id, client_id=clientId, variant_id=variant_id)

    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    # Extract synthesized puckData from provenance
    provenance = variant.provenance or {}
    synthesis = provenance.get("synthesis", {})
    synthesized_puck_data = (
        synthesis.get("synthesized_puck_data") if isinstance(synthesis, dict) else None
    )

    accepted_sections = [
        NormalizedSection(
            id=s.get("id", ""),
            sectionType=s.get("sectionType", "generic_content"),
            confidence=s.get("confidence", 0.0),
            keyText=s.get("keyText", []),
            keyMedia=s.get("keyMedia", []),
            keyStyles=s.get("keyStyles", {}),
            boundingBox=s.get("boundingBox"),
        )
        for s in (variant.accepted_sections or [])
    ]

    return TemplateVariantDetailExtended(
        id=str(variant.id),
        name=variant.name,
        family=variant.family,
        pageType=variant.page_type,
        status=variant.status,
        siteImportId=str(variant.site_import_id) if variant.site_import_id else None,
        stylePresetId=str(variant.style_preset_id) if variant.style_preset_id else None,
        acceptedSections=accepted_sections,
        provenance=provenance,
        reviewNotes=variant.review_notes,
        createdAt=variant.created_at,
        updatedAt=variant.updated_at,
        synthesizedPuckData=synthesized_puck_data,
    )


@router.get("/variants/{variant_id}/presets", response_model=list[MutationPresetPreview])
def list_variant_presets_endpoint(
    variant_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MutationPresetPreview]:
    """List mutation presets available for a variant."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate variant_id format
    _validate_variant_id(variant_id)

    repo = StorefrontImportsRepository(session)
    variant = repo.get_variant(org_id=auth.org_id, client_id=clientId, variant_id=variant_id)

    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    # Import here to avoid circular imports
    from app.services.template_variant_engine import preview_presets_for_variant

    # Convert variant to dict for the engine
    variant_dict = {
        "id": str(variant.id),
        "family": variant.family,
        "page_type": variant.page_type,
        "provenance": variant.provenance or {},
    }

    previews = preview_presets_for_variant(variant_dict)

    return [
        MutationPresetPreview(
            presetId=p.presetId,
            presetLabel=p.presetLabel,
            presetDescription=p.presetDescription,
            applicable=p.applicable,
            notApplicableReason=p.notApplicableReason,
            effects=list(p.effects),
        )
        for p in previews
    ]


@router.get("/presets", response_model=list[MutationPresetSummary])
def list_presets_endpoint(
    family: str | None = None,
    auth: AuthContext = Depends(get_current_user),
) -> list[MutationPresetSummary]:
    """List all available mutation presets, optionally filtered by family."""
    from app.services.template_variant_engine import list_mutation_presets

    presets = list_mutation_presets(family)

    return [
        MutationPresetSummary(
            id=p.id,
            label=p.label,
            description=p.description,
            families=list(p.families),
            effects=list(p.effects),
        )
        for p in presets
    ]


@router.post(
    "/variants/{variant_id}/generate",
    response_model=GenerateVariantsResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_variants_endpoint(
    variant_id: str,
    request: GenerateVariantsRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GenerateVariantsResponse:
    """Generate derived variants from a base variant using mutation presets."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate variant_id format
    _validate_variant_id(variant_id)

    repo = StorefrontImportsRepository(session)
    variant = repo.get_variant(org_id=auth.org_id, client_id=clientId, variant_id=variant_id)

    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    # Validate preset IDs
    from app.services.template_variant_engine import (
        PresetNotApplicableError,
        VariantEngineError,
        apply_multiple_presets_to_variant,
        get_preset,
    )

    for preset_id in request.presetIds:
        preset = get_preset(preset_id)
        if preset is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown preset: {preset_id}",
            )

    # Validate generated_names length matches preset_ids if provided
    if request.generatedNames is not None and len(request.generatedNames) != len(request.presetIds):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Number of generated names must match number of preset IDs.",
        )

    # Convert variant to dict for the engine
    variant_dict = {
        "id": str(variant.id),
        "name": variant.name,
        "family": variant.family,
        "page_type": variant.page_type,
        "provenance": variant.provenance or {},
    }

    # Apply presets
    try:
        generated = apply_multiple_presets_to_variant(
            variant=variant_dict,
            preset_ids=request.presetIds,
            generated_names=request.generatedNames,
            actor=auth.user_id,
        )
    except PresetNotApplicableError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except VariantEngineError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Persist generated variants
    created_variants = []
    for gen in generated:
        # Get parent's style preset if available
        parent_style_preset_id = variant.style_preset_id

        created = repo.create_derived_variant_draft(
            org_id=auth.org_id,
            client_id=clientId,
            parent_variant_id=variant_id,
            style_preset_id=parent_style_preset_id,
            name=gen.name,
            family=gen.family,
            page_type=gen.pageType,
            provenance=gen.provenance,
            created_by_user_external_id=auth.user_id,
            commit=False,
        )
        created_variants.append(created)

    try:
        session.commit()
        for v in created_variants:
            session.refresh(v)
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist generated variants.",
        ) from exc

    return GenerateVariantsResponse(
        generatedVariants=[
            GeneratedVariantSummary(
                id=str(v.id),
                name=v.name,
                family=v.family,
                pageType=v.page_type,
                status=v.status,
                parentVariantId=variant_id,
                mutationPresetId=gen.mutationPresetId,
                mutationPresetLabel=gen.mutationPresetLabel,
                mutationSummary=gen.mutationSummary,
                createdAt=v.created_at,
                updatedAt=v.updated_at,
            )
            for v, gen in zip(created_variants, generated)
        ]
    )


# =============================================================================
# Template Endpoints
# =============================================================================


def _serialize_summary(template: StorefrontTemplateDescriptor) -> StorefrontTemplateSummary:
    return StorefrontTemplateSummary(
        id=template.template_id,
        name=template.name,
        description=template.description,
        previewImage=template.preview_image,
        family=template.family,
        variant=template.variant,
        version=template.version,
        pageType=template.page_type,
        configSlots=list(template.config_slots),
        requiredBindingKeys=[binding.key for binding in template.required_bindings],
    )


def _serialize_detail(template: StorefrontTemplateDescriptor) -> StorefrontTemplateDetail:
    return StorefrontTemplateDetail(
        **_serialize_summary(template).model_dump(),
        requiredBindings=[
            StorefrontTemplateBindingRequirement(
                key=binding.key,
                label=binding.label,
                source=binding.source,
                description=binding.description,
                required=binding.required,
            )
            for binding in template.required_bindings
        ],
        stylePolicy=StorefrontTemplateStylePolicy(
            lockedTokenGroups=list(template.style_policy.locked_token_groups),
            editableTokenGroups=list(template.style_policy.editable_token_groups),
        ),
        importProvenance=StorefrontTemplateImportProvenance(
            sourceType=template.import_provenance.source_type,
            sourceTemplateId=template.import_provenance.source_template_id,
            notes=list(template.import_provenance.notes),
        ),
        puckData=template.puck_data,
    )


def _get_template_or_404(template_id: str) -> StorefrontTemplateDescriptor:
    template = get_storefront_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Storefront template not found."
        )
    return template


@router.get("", response_model=list[StorefrontTemplateSummary])
def list_templates(
    _auth: AuthContext = Depends(get_current_user),
) -> list[StorefrontTemplateSummary]:
    return [_serialize_summary(template) for template in list_storefront_templates()]


@router.get("/{template_id}", response_model=StorefrontTemplateDetail)
def get_template(
    template_id: str, _auth: AuthContext = Depends(get_current_user)
) -> StorefrontTemplateDetail:
    return _serialize_detail(_get_template_or_404(template_id))


@router.get("/{template_id}/binding-preview", response_model=StorefrontBindingPreviewResponse)
def get_binding_preview(
    template_id: str,
    clientId: str,
    productId: str | None = None,
    variantId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StorefrontBindingPreviewResponse:
    template = _get_template_or_404(template_id)

    client = session.scalars(
        select(Client).where(Client.id == clientId, Client.org_id == auth.org_id)
    ).first()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    if variantId and not productId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="variantId requires productId.",
        )

    product = None
    if productId:
        product = session.scalars(
            select(Product).where(
                Product.id == productId,
                Product.client_id == client.id,
                Product.org_id == auth.org_id,
            )
        ).first()
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    variant = None
    if variantId:
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="variantId requires productId.",
            )
        variant = session.scalars(
            select(ProductVariant).where(
                ProductVariant.id == variantId,
                ProductVariant.product_id == product.id,
            )
        ).first()
        if variant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    preview = build_storefront_binding_preview(
        template=template,
        client_id=str(client.id),
        product=product,
        variant=variant,
    )
    return StorefrontBindingPreviewResponse(
        templateId=preview.template_id,
        clientId=preview.client_id,
        productId=preview.product_id,
        productTitle=preview.product_title,
        variantId=preview.variant_id,
        variantTitle=preview.variant_title,
        variantProvider=preview.variant_provider,
        ready=preview.ready,
        requirements=[
            StorefrontBindingPreviewRequirement(
                key=requirement.key,
                label=requirement.label,
                source=requirement.source,
                required=requirement.required,
                status=requirement.status,
                detail=requirement.detail,
            )
            for requirement in preview.requirements
        ],
        notes=list(preview.notes),
    )


@router.post(
    "/{template_id}/drafts",
    response_model=CreateDraftFromTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_draft_from_template_endpoint(
    template_id: str,
    request: CreateDraftFromTemplateRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CreateDraftFromTemplateResponse:
    """Create a draft variant from a built-in storefront template."""
    template = _get_template_or_404(template_id)

    # Validate workspace exists
    client = _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate product exists
    product = session.scalars(
        select(Product).where(
            Product.id == request.productId,
            Product.client_id == client.id,
            Product.org_id == auth.org_id,
        )
    ).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    # Validate variant exists
    variant = session.scalars(
        select(ProductVariant).where(
            ProductVariant.id == request.variantId,
            ProductVariant.product_id == product.id,
        )
    ).first()
    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    # Build binding preview to check Medusa readiness
    preview = build_storefront_binding_preview(
        template=template,
        client_id=str(client.id),
        product=product,
        variant=variant,
    )

    if str(variant.provider or "").strip().lower() == "medusa":
        medusa_config = get_client_medusa_config(
            session=session,
            org_id=auth.org_id,
            client_id=clientId,
        )
        if medusa_config is None or medusa_config.connection_status != "connected":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create draft: workspace Medusa connection is not healthy.",
            )
        if not getattr(product, "medusa_product_id", None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create draft: selected product is not mapped to a Medusa product yet.",
            )

    # Reject if not Medusa-ready
    if not preview.ready:
        missing_requirements = [
            req for req in preview.requirements if req.required and req.status != "ready"
        ]
        error_details = "; ".join(f"{req.label}: {req.detail}" for req in missing_requirements)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create draft: binding requirements not ready. {error_details}",
        )

    # Create the draft
    try:
        result = create_draft_from_template(
            session,
            org_id=auth.org_id,
            client_id=clientId,
            template_id=template_id,
            name=request.name,
            family=template.family,
            page_type=template.page_type,
            puck_data=template.puck_data,
            review_notes=request.reviewNotes,
            created_by_user_external_id=auth.user_id,
            product_id=request.productId,
            variant_id=request.variantId,
            variant_provider=preview.variant_provider,
            variant_external_id=str(variant.external_price_id)
            if variant and variant.external_price_id
            else None,
            product=product,
            variant=variant,
        )
    except SiteImportError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    variant_record = result["variant"]
    style_preset = result["style_preset"]

    # Extract synthesized puckData from provenance
    provenance = variant_record.provenance or {}
    synthesis = provenance.get("synthesis", {})
    synthesized_puck_data = (
        synthesis.get("synthesized_puck_data") if isinstance(synthesis, dict) else None
    )

    return CreateDraftFromTemplateResponse(
        variant=TemplateVariantDetailExtended(
            id=str(variant_record.id),
            name=variant_record.name,
            family=variant_record.family,
            pageType=variant_record.page_type,
            status=variant_record.status,
            siteImportId=str(variant_record.site_import_id)
            if variant_record.site_import_id
            else None,
            stylePresetId=str(style_preset.id) if style_preset else None,
            acceptedSections=[],
            provenance=provenance,
            reviewNotes=variant_record.review_notes,
            createdAt=variant_record.created_at,
            updatedAt=variant_record.updated_at,
            synthesizedPuckData=synthesized_puck_data,
        ),
        bindingPreview=StorefrontBindingPreviewResponse(
            templateId=preview.template_id,
            clientId=preview.client_id,
            productId=preview.product_id,
            productTitle=preview.product_title,
            variantId=preview.variant_id,
            variantTitle=preview.variant_title,
            variantProvider=preview.variant_provider,
            ready=preview.ready,
            requirements=[
                StorefrontBindingPreviewRequirement(
                    key=requirement.key,
                    label=requirement.label,
                    source=requirement.source,
                    required=requirement.required,
                    status=requirement.status,
                    detail=requirement.detail,
                )
                for requirement in preview.requirements
            ],
            notes=list(preview.notes),
        ),
    )


# =============================================================================
# Governance Endpoints (Phase 5)
# =============================================================================


def _serialize_governance_report(report) -> GovernanceReport:
    """
    Serialize a governance report to the response schema.

    This helper reduces duplication between GET and POST approval endpoints.
    """
    return GovernanceReport(
        variantId=report.variant_id,
        readyForPublish=report.ready_for_publish,
        blockers=list(report.blockers),
        warnings=list(report.warnings),
        assetValidations=[
            AssetValidationResult(
                publicId=av.public_id,
                fieldPath=list(av.field_path),
                blockType=av.block_type,
                blockId=av.block_id,
                status=av.status,
                assetId=av.asset_id,
            )
            for av in report.asset_validations
        ],
        styleAudit=StyleAuditResult(
            presetId=report.style_audit.preset_id if report.style_audit else None,
            presetName=report.style_audit.preset_name if report.style_audit else None,
            findings=[
                StyleAuditFinding(
                    checkId=f.check_id,
                    status=f.status,
                    message=f.message,
                    location=f.location,
                    foreground=f.foreground,
                    background=f.background,
                    contrastRatio=f.contrast_ratio,
                    threshold=f.threshold,
                )
                for f in (report.style_audit.findings if report.style_audit else [])
            ],
            passed=report.style_audit.passed if report.style_audit else False,
        )
        if report.style_audit
        else None,
        puckDataStructure=PuckDataStructureResult(
            valid=report.puck_data_structure.valid if report.puck_data_structure else False,
            errors=list(report.puck_data_structure.errors) if report.puck_data_structure else [],
            warnings=list(report.puck_data_structure.warnings)
            if report.puck_data_structure
            else [],
        )
        if report.puck_data_structure
        else None,
        provenanceEvents=[
            ProvenanceEvent(
                eventType=pe.get("event_type", ""),
                timestamp=pe.get("timestamp", ""),
                actor=pe.get("actor"),
                metadata=pe.get("metadata", {}),
            )
            for pe in report.provenance_events
        ],
    )


@router.get("/variants/{variant_id}/governance", response_model=GovernanceReport)
def get_variant_governance(
    variant_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GovernanceReport:
    """Get governance report for a variant."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate variant_id format
    _validate_variant_id(variant_id)

    repo = StorefrontImportsRepository(session)
    variant = repo.get_variant(org_id=auth.org_id, client_id=clientId, variant_id=variant_id)

    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    # Get synthesized puckData from provenance
    provenance = variant.provenance or {}
    synthesis = provenance.get("synthesis", {})
    synthesized_puck_data = (
        synthesis.get("synthesized_puck_data") if isinstance(synthesis, dict) else None
    )

    # Get style preset if linked
    style_preset_id = str(variant.style_preset_id) if variant.style_preset_id else None
    style_preset_tokens = None
    style_preset_name = None

    if style_preset_id:
        style_preset = repo.get_style_preset(
            org_id=auth.org_id, client_id=clientId, preset_id=style_preset_id
        )
        if style_preset:
            style_preset_tokens = style_preset.tokens
            style_preset_name = style_preset.name

    # Compute governance report with family for family-specific validation
    assets_repo = AssetsRepository(session)
    report = compute_governance_report(
        variant_id=str(variant.id),
        synthesized_puck_data=synthesized_puck_data,
        style_preset_id=style_preset_id,
        style_preset_tokens=style_preset_tokens,
        style_preset_name=style_preset_name,
        provenance=provenance,
        assets_repo=assets_repo,
        org_id=auth.org_id,
        client_id=clientId,
        family=variant.family,
    )

    return _serialize_governance_report(report)


@router.post("/variants/{variant_id}/approve", response_model=ApproveForPublishResponse)
def approve_variant_for_publish(
    variant_id: str,
    request: ApproveForPublishRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ApproveForPublishResponse:
    """Approve a variant for publish."""
    # Validate workspace exists
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate variant_id format
    _validate_variant_id(variant_id)

    repo = StorefrontImportsRepository(session)
    variant = repo.get_variant(org_id=auth.org_id, client_id=clientId, variant_id=variant_id)

    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    # Check variant status - allow draft or already approved (idempotent)
    if variant.status not in ("draft", "approved"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve variant with status: {variant.status}",
        )

    # Idempotent: if already approved, return current state without modification
    if variant.status == "approved":
        # Get synthesized puckData from provenance for governance report
        provenance = variant.provenance or {}
        synthesis = provenance.get("synthesis", {})
        synthesized_puck_data = (
            synthesis.get("synthesized_puck_data") if isinstance(synthesis, dict) else None
        )

        # Get style preset if linked
        style_preset_id = str(variant.style_preset_id) if variant.style_preset_id else None
        style_preset_tokens = None
        style_preset_name = None

        if style_preset_id:
            style_preset = repo.get_style_preset(
                org_id=auth.org_id, client_id=clientId, preset_id=style_preset_id
            )
            if style_preset:
                style_preset_tokens = style_preset.tokens
                style_preset_name = style_preset.name

        # Compute governance report for response
        assets_repo = AssetsRepository(session)
        report = compute_governance_report(
            variant_id=str(variant.id),
            synthesized_puck_data=synthesized_puck_data,
            style_preset_id=style_preset_id,
            style_preset_tokens=style_preset_tokens,
            style_preset_name=style_preset_name,
            provenance=provenance,
            assets_repo=assets_repo,
            org_id=auth.org_id,
            client_id=clientId,
            family=variant.family,
        )

        return ApproveForPublishResponse(
            variantId=str(variant.id),
            status=variant.status,
            provenance=variant.provenance or {},
            governanceReport=_serialize_governance_report(report),
        )

    # Get synthesized puckData from provenance
    provenance = variant.provenance or {}
    synthesis = provenance.get("synthesis", {})
    synthesized_puck_data = (
        synthesis.get("synthesized_puck_data") if isinstance(synthesis, dict) else None
    )

    # Get style preset if linked
    style_preset_id = str(variant.style_preset_id) if variant.style_preset_id else None
    style_preset_tokens = None
    style_preset_name = None

    if style_preset_id:
        style_preset = repo.get_style_preset(
            org_id=auth.org_id, client_id=clientId, preset_id=style_preset_id
        )
        if style_preset:
            style_preset_tokens = style_preset.tokens
            style_preset_name = style_preset.name

    # Compute governance report
    assets_repo = AssetsRepository(session)
    report = compute_governance_report(
        variant_id=str(variant.id),
        synthesized_puck_data=synthesized_puck_data,
        style_preset_id=style_preset_id,
        style_preset_tokens=style_preset_tokens,
        style_preset_name=style_preset_name,
        provenance=provenance,
        assets_repo=assets_repo,
        org_id=auth.org_id,
        client_id=clientId,
        family=variant.family,
    )

    # Check for blockers
    if report.blockers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve variant with governance blockers: {'; '.join(report.blockers)}",
        )

    # Use authenticated user for the approval audit trail; never trust client-supplied actor data.
    approved_by = auth.user_id
    updated_provenance = build_approval_provenance(
        provenance=provenance,
        actor=approved_by,
        governance_report=report,
    )

    # Update variant status
    updated_variant = repo.approve_variant_for_publish(
        org_id=auth.org_id,
        client_id=clientId,
        variant_id=variant_id,
        approved_by_user_external_id=approved_by,
        provenance_update=updated_provenance,
    )

    if updated_variant is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update variant status.",
        )

    updated_report = compute_governance_report(
        variant_id=str(updated_variant.id),
        synthesized_puck_data=synthesized_puck_data,
        style_preset_id=style_preset_id,
        style_preset_tokens=style_preset_tokens,
        style_preset_name=style_preset_name,
        provenance=updated_variant.provenance or {},
        assets_repo=assets_repo,
        org_id=auth.org_id,
        client_id=clientId,
        family=updated_variant.family,
    )

    return ApproveForPublishResponse(
        variantId=str(updated_variant.id),
        status=updated_variant.status,
        provenance=updated_variant.provenance or {},
        governanceReport=_serialize_governance_report(updated_report),
    )
