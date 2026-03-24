"""
Template Variant Governance Service.

Computes governance reports and handles approve-for-publish for template variants.
Phase 5: Governance and scale.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.db.enums import AssetStatusEnum
from app.services.design_system_audit import AuditFinding, audit_design_system_tokens


class GovernanceError(Exception):
    """Error during governance validation."""

    pass


class AssetValidationError(GovernanceError):
    """Raised when asset validation fails."""

    pass


class StyleAuditError(GovernanceError):
    """Raised when style audit fails."""

    pass


# =============================================================================
# Asset Reference Extraction
# =============================================================================

ASSET_REFERENCE_KEYS = {
    "assetPublicId",
    "referenceAssetPublicId",
    "iconAssetPublicId",
    "posterAssetPublicId",
}


@dataclass(frozen=True)
class AssetReference:
    """A reference to an asset within puckData."""

    public_id: str
    field_path: list[str]
    block_type: str | None = None
    block_id: str | None = None


def extract_asset_references(puck_data: dict[str, Any]) -> list[AssetReference]:
    """
    Recursively scan puckData for asset references.

    Searches for assetPublicId, referenceAssetPublicId, iconAssetPublicId,
    and posterAssetPublicId fields throughout the puckData structure.

    Args:
        puck_data: The synthesized puckData to scan.

    Returns:
        List of AssetReference objects found in the puckData.
    """
    references: list[AssetReference] = []
    _extract_asset_references_recursive(puck_data, [], None, None, references)
    return references


def _extract_asset_references_recursive(
    obj: Any,
    path: list[str],
    block_type: str | None,
    block_id: str | None,
    references: list[AssetReference],
) -> None:
    """Recursively extract asset references from an object."""
    if isinstance(obj, dict):
        # Track block type and id when we encounter them
        if "type" in obj:
            block_type = obj.get("type")
        if "id" in obj:
            block_id = obj.get("id")

        for key, value in obj.items():
            new_path = path + [key]

            if key in ASSET_REFERENCE_KEYS and isinstance(value, str) and value:
                references.append(
                    AssetReference(
                        public_id=value,
                        field_path=new_path,
                        block_type=block_type,
                        block_id=block_id,
                    )
                )
            else:
                _extract_asset_references_recursive(
                    value, new_path, block_type, block_id, references
                )
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _extract_asset_references_recursive(
                item, path + [str(idx)], block_type, block_id, references
            )


# =============================================================================
# Provenance Event Helpers
# =============================================================================


def make_provenance_event(
    event_type: str,
    actor: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a provenance event record.

    Args:
        event_type: Type of event (e.g., 'convert', 'derive', 'approve').
        actor: User or system that triggered the event.
        metadata: Additional event-specific metadata.

    Returns:
        A provenance event dict.
    """
    return {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "metadata": metadata or {},
    }


def append_provenance_event(
    provenance: dict[str, Any],
    event_type: str,
    actor: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append a provenance event to the provenance record.

    Args:
        provenance: Existing provenance dict.
        event_type: Type of event.
        actor: User or system that triggered the event.
        metadata: Additional event-specific metadata.

    Returns:
        Updated provenance dict with the new event appended.
    """
    result = copy.deepcopy(provenance)
    events = result.get("events", [])
    if not isinstance(events, list):
        events = []
    events.append(make_provenance_event(event_type, actor, metadata))
    result["events"] = events
    return result


def build_convert_provenance(
    source_url: str,
    source_hostname: str | None,
    imported_at: str | None,
    page_type_hint: str | None,
    synthesis: dict[str, Any],
    actor: str | None = None,
) -> dict[str, Any]:
    """
    Build provenance for a converted import.

    Args:
        source_url: URL of the imported site.
        source_hostname: Hostname of the imported site.
        imported_at: ISO timestamp of import.
        page_type_hint: Page type hint from import.
        synthesis: Synthesis output dict.
        actor: User who triggered the conversion.

    Returns:
        Provenance dict with convert event.
    """
    provenance: dict[str, Any] = {
        "source_type": "site_import",
        "source_url": source_url,
        "source_hostname": source_hostname,
        "imported_at": imported_at,
        "page_type_hint": page_type_hint,
        "synthesis": synthesis,
    }
    return append_provenance_event(
        provenance,
        "convert",
        actor=actor,
        metadata={
            "family": synthesis.get("target_family"),
            "page_type": synthesis.get("target_page_type"),
        },
    )


def build_derive_provenance(
    parent_variant_id: str,
    parent_variant_name: str,
    mutation_preset_id: str,
    mutation_preset_label: str,
    synthesized_puck_data: dict[str, Any],
    original_provenance: dict[str, Any] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """
    Build provenance for a derived variant.

    Args:
        parent_variant_id: ID of the parent variant.
        parent_variant_name: Name of the parent variant.
        mutation_preset_id: ID of the mutation preset.
        mutation_preset_label: Label of the mutation preset.
        synthesized_puck_data: Mutated puckData.
        original_provenance: Provenance from the parent variant.
        actor: User who triggered the derivation.

    Returns:
        Provenance dict with derive event.
    """
    provenance: dict[str, Any] = {
        "source_type": "variant_mutation",
        "parent_variant_id": parent_variant_id,
        "parent_variant_name": parent_variant_name,
        "mutation_preset_id": mutation_preset_id,
        "mutation_preset_label": mutation_preset_label,
        "synthesis": {
            "synthesized_puck_data": synthesized_puck_data,
            "mutation_applied": mutation_preset_id,
        },
    }

    # Preserve original source info if available
    if original_provenance:
        original_source_type = original_provenance.get(
            "original_source_type", original_provenance.get("source_type")
        )
        original_source_url = original_provenance.get(
            "original_source_url", original_provenance.get("source_url")
        )
        if original_source_type is not None:
            provenance["original_source_type"] = original_source_type
        if original_source_url is not None:
            provenance["original_source_url"] = original_source_url
        if "synthesis" in original_provenance and isinstance(
            original_provenance["synthesis"], dict
        ):
            if "block_coverage" in original_provenance["synthesis"]:
                provenance["synthesis"]["block_coverage"] = original_provenance["synthesis"][
                    "block_coverage"
                ]
        # Preserve prior events from the original provenance
        if "events" in original_provenance and isinstance(original_provenance["events"], list):
            provenance["events"] = copy.deepcopy(original_provenance["events"])

    return append_provenance_event(
        provenance,
        "derive",
        actor=actor,
        metadata={
            "parent_variant_id": parent_variant_id,
            "mutation_preset_id": mutation_preset_id,
        },
    )


# =============================================================================
# Governance Report
# =============================================================================


@dataclass(frozen=True)
class AssetValidationResult:
    """Result of validating a single asset reference."""

    public_id: str
    field_path: list[str]
    block_type: str | None
    block_id: str | None
    status: str  # "approved", "pending", "rejected", "not_found"
    asset_id: str | None = None


@dataclass(frozen=True)
class StyleAuditResult:
    """Result of style preset audit."""

    preset_id: str | None
    preset_name: str | None
    findings: list[AuditFinding]
    passed: bool


@dataclass(frozen=True)
class PuckDataStructureResult:
    """Result of puckData structure validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GovernanceReport:
    """Complete governance report for a variant."""

    variant_id: str
    ready_for_publish: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    asset_validations: list[AssetValidationResult] = field(default_factory=list)
    style_audit: StyleAuditResult | None = None
    puck_data_structure: PuckDataStructureResult | None = None
    provenance_events: list[dict[str, Any]] = field(default_factory=list)


def validate_assets(
    asset_references: list[AssetReference],
    assets_repo: Any,  # AssetsRepository
    org_id: str,
    client_id: str | None = None,
) -> list[AssetValidationResult]:
    """
    Validate asset references against the assets repository.

    Args:
        asset_references: List of asset references to validate.
        assets_repo: AssetsRepository instance.
        org_id: Organization ID.
        client_id: Optional client ID for scoping.

    Returns:
        List of AssetValidationResult objects.
    """
    results: list[AssetValidationResult] = []

    for ref in asset_references:
        asset = assets_repo.get_by_public_id(org_id, ref.public_id, client_id)

        if asset is None:
            results.append(
                AssetValidationResult(
                    public_id=ref.public_id,
                    field_path=ref.field_path,
                    block_type=ref.block_type,
                    block_id=ref.block_id,
                    status="not_found",
                )
            )
        elif asset.status == AssetStatusEnum.approved:
            results.append(
                AssetValidationResult(
                    public_id=ref.public_id,
                    field_path=ref.field_path,
                    block_type=ref.block_type,
                    block_id=ref.block_id,
                    status="approved",
                    asset_id=str(asset.id),
                )
            )
        elif asset.status == AssetStatusEnum.qa_passed:
            results.append(
                AssetValidationResult(
                    public_id=ref.public_id,
                    field_path=ref.field_path,
                    block_type=ref.block_type,
                    block_id=ref.block_id,
                    status="approved",  # qa_passed is also acceptable for publish
                    asset_id=str(asset.id),
                )
            )
        elif asset.status == AssetStatusEnum.rejected:
            results.append(
                AssetValidationResult(
                    public_id=ref.public_id,
                    field_path=ref.field_path,
                    block_type=ref.block_type,
                    block_id=ref.block_id,
                    status="rejected",
                    asset_id=str(asset.id),
                )
            )
        else:
            results.append(
                AssetValidationResult(
                    public_id=ref.public_id,
                    field_path=ref.field_path,
                    block_type=ref.block_type,
                    block_id=ref.block_id,
                    status="pending",
                    asset_id=str(asset.id),
                )
            )

    return results


def audit_style_preset(
    style_preset_id: str | None,
    style_preset_tokens: dict[str, Any] | None,
    preset_name: str | None = None,
) -> StyleAuditResult:
    """
    Audit a style preset's tokens.

    Args:
        style_preset_id: ID of the style preset.
        style_preset_tokens: Token dict from the preset.
        preset_name: Optional name of the preset.

    Returns:
        StyleAuditResult with findings and pass/fail status.
    """
    if style_preset_tokens is None:
        return StyleAuditResult(
            preset_id=style_preset_id,
            preset_name=preset_name,
            findings=[
                AuditFinding(
                    check_id="tokens.missing",
                    status="fail",
                    location="tokens",
                    message="No style preset tokens found.",
                )
            ],
            passed=False,
        )

    findings = audit_design_system_tokens(style_preset_tokens)
    passed = all(f.status == "pass" for f in findings)

    return StyleAuditResult(
        preset_id=style_preset_id,
        preset_name=preset_name,
        findings=findings,
        passed=passed,
    )


def validate_puck_data_structure(puck_data: dict[str, Any] | None) -> PuckDataStructureResult:
    """
    Validate the structure of synthesized puckData.

    Args:
        puck_data: The puckData to validate.

    Returns:
        PuckDataStructureResult with validation results.
    """
    if puck_data is None:
        return PuckDataStructureResult(
            valid=False,
            errors=["No synthesized puckData found."],
        )

    errors: list[str] = []
    warnings: list[str] = []

    # Check for required top-level content
    if "content" not in puck_data:
        errors.append("puckData missing required 'content' field.")
    elif not isinstance(puck_data.get("content"), list):
        errors.append("puckData 'content' must be a list.")
    elif len(puck_data.get("content", [])) == 0:
        warnings.append("puckData 'content' is empty.")

    # Check for Page block
    content = puck_data.get("content", [])
    if isinstance(content, list) and len(content) > 0:
        page_block = None
        for block in content:
            if isinstance(block, dict) and "Page" in str(block.get("type", "")):
                page_block = block
                break

        if page_block is None:
            warnings.append("No Page block found in puckData content.")
        else:
            page_props = page_block.get("props", {})
            if not isinstance(page_props, dict):
                errors.append("Page block missing 'props' object.")
            else:
                page_content = page_props.get("content", [])
                if not isinstance(page_content, list):
                    errors.append("Page block 'content' must be a list.")
                elif len(page_content) == 0:
                    warnings.append("Page block 'content' is empty.")

    return PuckDataStructureResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# =============================================================================
# Family-Aligned Block Validation
# =============================================================================


# Required block types for each storefront family
FAMILY_REQUIRED_BLOCKS: dict[str, dict[str, list[str]]] = {
    "sales-pdp": {
        "required": ["SalesPdpHero"],
        "recommended": ["SalesPdpMarquee", "SalesPdpFooter"],
    },
    "listicle-presell": {
        "required": ["PreSalesHero"],
        "recommended": ["PreSalesFloatingCta"],
    },
    "pre-sales-listicle": {
        "required": ["PreSalesHero"],
        "recommended": ["PreSalesFloatingCta"],
    },
}


def validate_family_blocks(
    puck_data: dict[str, Any] | None,
    family: str | None,
) -> tuple[list[str], list[str]]:
    """
    Validate that puckData contains family-aligned blocks.

    Args:
        puck_data: The puckData to validate.
        family: The template family.

    Returns:
        Tuple of (errors, warnings) lists.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if puck_data is None or family is None:
        return errors, warnings

    family_config = FAMILY_REQUIRED_BLOCKS.get(family)
    if family_config is None:
        # Unknown family - no specific block requirements
        return errors, warnings

    # Extract all block types from puckData
    block_types: set[str] = set()
    content = puck_data.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type:
                    block_types.add(block_type)
                # Also check nested content in Page blocks
                if "Page" in str(block_type):
                    page_content = block.get("props", {}).get("content", [])
                    if isinstance(page_content, list):
                        for nested_block in page_content:
                            if isinstance(nested_block, dict):
                                nested_type = nested_block.get("type", "")
                                if nested_type:
                                    block_types.add(nested_type)

    # Check required blocks
    for required_block in family_config.get("required", []):
        if required_block not in block_types:
            errors.append(
                f"Family '{family}' requires block type '{required_block}' but it was not found."
            )

    # Check recommended blocks (warnings only)
    for recommended_block in family_config.get("recommended", []):
        if recommended_block not in block_types:
            warnings.append(
                f"Family '{family}' typically includes '{recommended_block}' but it was not found."
            )

    return errors, warnings


def validate_provenance_fields(provenance: dict[str, Any] | None) -> list[str]:
    """
    Validate required provenance fields for publish readiness.

    Args:
        provenance: The provenance dict to validate.

    Returns:
        List of error messages for missing required fields.
    """
    errors: list[str] = []

    if provenance is None:
        errors.append("Variant missing required provenance.")
        return errors

    # Required source tracking fields
    if "source_type" not in provenance:
        errors.append("Provenance missing required 'source_type' field.")

    # Must have either source_url (for imports) or parent_variant_id (for mutations)
    has_source_url = "source_url" in provenance and provenance.get("source_url")
    has_parent = "parent_variant_id" in provenance and provenance.get("parent_variant_id")
    has_original_source = "original_source_url" in provenance and provenance.get(
        "original_source_url"
    )

    if provenance.get("source_type") == "site_import":
        if not has_source_url:
            errors.append("Import provenance missing required 'source_url' field.")
    elif provenance.get("source_type") == "variant_mutation":
        if not has_parent:
            errors.append("Mutation provenance missing required 'parent_variant_id' field.")
        # Should also have original source tracking
        if not has_original_source and not has_source_url:
            warnings_msg = "Mutation provenance should preserve original source tracking."
            # This is a warning, not an error - we'll add it separately

    return errors


def validate_token_presence(style_preset_tokens: dict[str, Any] | None) -> list[str]:
    """
    Validate required token/theme presence groups for storefront variants.

    Args:
        style_preset_tokens: Token dict from the style preset.

    Returns:
        List of error messages for missing required token groups.
    """
    errors: list[str] = []

    if style_preset_tokens is None:
        errors.append("Style preset tokens are required for publish.")
        return errors

    # Required token groups for storefront
    required_groups = ["palette", "fonts"]
    for group in required_groups:
        if group not in style_preset_tokens:
            errors.append(f"Style preset missing required token group '{group}'.")
        elif not isinstance(style_preset_tokens.get(group), dict):
            errors.append(f"Style preset token group '{group}' must be an object.")
        elif not style_preset_tokens.get(group):
            errors.append(f"Style preset token group '{group}' cannot be empty.")

    return errors


def compute_governance_report(
    variant_id: str,
    synthesized_puck_data: dict[str, Any] | None,
    style_preset_id: str | None,
    style_preset_tokens: dict[str, Any] | None,
    style_preset_name: str | None,
    provenance: dict[str, Any],
    assets_repo: Any,  # AssetsRepository
    org_id: str,
    client_id: str,
    family: str | None = None,
) -> GovernanceReport:
    """
    Compute a complete governance report for a variant.

    Args:
        variant_id: ID of the variant.
        synthesized_puck_data: The synthesized puckData.
        style_preset_id: ID of the linked style preset.
        style_preset_tokens: Tokens from the style preset.
        style_preset_name: Name of the style preset.
        provenance: Provenance dict from the variant.
        assets_repo: AssetsRepository instance.
        org_id: Organization ID.
        client_id: Client/workspace ID.
        family: Optional template family for family-specific validation.

    Returns:
        GovernanceReport with all validation results.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    # Extract and validate asset references
    asset_references = []
    if synthesized_puck_data:
        asset_references = extract_asset_references(synthesized_puck_data)

    asset_validations = validate_assets(asset_references, assets_repo, org_id, client_id)

    # Check for blocking asset issues
    for av in asset_validations:
        if av.status == "not_found":
            blockers.append(
                f"Asset '{av.public_id}' referenced in {av.block_type or 'unknown'} "
                f"({av.field_path[-1]}) not found."
            )
        elif av.status == "rejected":
            blockers.append(
                f"Asset '{av.public_id}' referenced in {av.block_type or 'unknown'} "
                f"({av.field_path[-1]}) is rejected."
            )
        elif av.status == "pending":
            # Pending/draft assets are blockers, not just warnings
            blockers.append(
                f"Asset '{av.public_id}' referenced in {av.block_type or 'unknown'} "
                f"({av.field_path[-1]}) is pending approval."
            )
        # referenceAssetPublicId values themselves are not publishable storefront assets.
        if av.field_path and av.field_path[-1] == "referenceAssetPublicId":
            blockers.append(
                f"referenceAssetPublicId '{av.public_id}' in {av.block_type or 'unknown'} "
                f"must be replaced with a publish-approved storefront asset before publish."
            )

    # Audit style preset
    style_audit = audit_style_preset(style_preset_id, style_preset_tokens, style_preset_name)
    if not style_audit.passed:
        for finding in style_audit.findings:
            if finding.status == "fail":
                blockers.append(f"Style audit failed: {finding.message}")

    # Validate puckData structure
    puck_data_structure = validate_puck_data_structure(synthesized_puck_data)
    if not puck_data_structure.valid:
        blockers.extend(puck_data_structure.errors)
    warnings.extend(puck_data_structure.warnings)

    # Validate provenance fields
    provenance_errors = validate_provenance_fields(provenance)
    blockers.extend(provenance_errors)

    # Validate token presence groups
    token_errors = validate_token_presence(style_preset_tokens)
    blockers.extend(token_errors)

    # Validate family-aligned blocks
    family_block_errors, family_block_warnings = validate_family_blocks(
        synthesized_puck_data, family
    )
    blockers.extend(family_block_errors)
    warnings.extend(family_block_warnings)

    # Extract provenance events
    provenance_events = provenance.get("events", [])
    if not isinstance(provenance_events, list):
        provenance_events = []

    ready_for_publish = len(blockers) == 0

    return GovernanceReport(
        variant_id=variant_id,
        ready_for_publish=ready_for_publish,
        blockers=blockers,
        warnings=warnings,
        asset_validations=asset_validations,
        style_audit=style_audit,
        puck_data_structure=puck_data_structure,
        provenance_events=provenance_events,
    )


def build_approval_provenance(
    provenance: dict[str, Any],
    actor: str | None = None,
    governance_report: GovernanceReport | None = None,
) -> dict[str, Any]:
    """
    Build provenance with approval event appended.

    Args:
        provenance: Existing provenance dict.
        actor: User who approved.
        governance_report: Governance report at time of approval.

    Returns:
        Updated provenance dict with approval event.
    """
    metadata: dict[str, Any] = {}
    if governance_report:
        metadata["blockers_at_approval"] = governance_report.blockers
        metadata["warnings_at_approval"] = governance_report.warnings

    return append_provenance_event(
        provenance,
        "approve",
        actor=actor,
        metadata=metadata,
    )


def build_template_draft_provenance(
    template_id: str,
    template_family: str,
    template_page_type: str,
    synthesized_puck_data: dict[str, Any],
    actor: str | None = None,
    product_id: str | None = None,
    variant_id: str | None = None,
    variant_provider: str | None = None,
    variant_external_id: str | None = None,
) -> dict[str, Any]:
    """
    Build provenance for a draft created from a built-in storefront template.

    Args:
        template_id: ID of the source template.
        template_family: Family of the source template.
        template_page_type: Page type of the source template.
        synthesized_puck_data: The puckData from the template.
        actor: User who created the draft.
        product_id: Product ID for binding context.
        variant_id: Variant ID for binding context.
        variant_provider: Variant provider (e.g., 'medusa').
        variant_external_id: External Medusa variant ID.

    Returns:
        Provenance dict with template_draft event.
    """
    provenance: dict[str, Any] = {
        "source_type": "storefront_template",
        "template_id": template_id,
        "template_family": template_family,
        "template_page_type": template_page_type,
        "synthesis": {
            "synthesized_puck_data": synthesized_puck_data,
        },
    }

    # Include binding context if available
    if product_id:
        provenance["product_id"] = product_id
    if variant_id:
        provenance["variant_id"] = variant_id
    if variant_provider:
        provenance["variant_provider"] = variant_provider
    if variant_external_id:
        provenance["variant_external_id"] = variant_external_id

    return append_provenance_event(
        provenance,
        "template_draft",
        actor=actor,
        metadata={
            "template_id": template_id,
            "family": template_family,
            "page_type": template_page_type,
            "product_id": product_id,
            "variant_id": variant_id,
            "variant_provider": variant_provider,
        },
    )
