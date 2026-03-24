from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.db.models import SiteImport, SiteImportSnapshot
from app.db.repositories.storefront_imports import StorefrontImportsRepository
from app.services.site_import_capture import CaptureResult, capture_site
from app.services.site_import_normalize import normalize_capture
from app.services.template_synthesis import synthesize_import, SynthesisResult
from app.services.template_variant_governance import (
    build_convert_provenance,
    build_template_draft_provenance,
)

logger = logging.getLogger(__name__)


def _extract_hostname(url: str) -> str | None:
    """Extract hostname from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        return None


def _validate_url(url: str) -> None:
    """Validate URL format."""
    try:
        result = urlparse(url)
        if not result.scheme:
            raise ValueError("URL must include a scheme (http:// or https://)")
        if result.scheme not in ("http", "https"):
            raise ValueError("URL must use http:// or https:// scheme")
        if not result.netloc:
            raise ValueError("URL must include a valid domain")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}") from e


class SiteImportError(Exception):
    """Error during site import."""

    pass


async def create_import_job(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    source_url: str,
    page_type_hint: str | None,
    created_by_user_external_id: str | None,
) -> SiteImport:
    """
    Create a new site import job.

    This creates the import record and immediately runs the capture process.
    """
    # Validate URL
    _validate_url(source_url)

    # Extract hostname
    source_hostname = _extract_hostname(source_url)

    # Create repository
    repo = StorefrontImportsRepository(session)

    # Create import record
    site_import = repo.create_import(
        org_id=org_id,
        client_id=client_id,
        source_url=source_url,
        source_hostname=source_hostname,
        page_type_hint=page_type_hint,
        created_by_user_external_id=created_by_user_external_id,
    )

    # Run capture
    try:
        capture_result = await capture_site(source_url)

        # Normalize the capture
        normalization_result = normalize_capture(
            html_snapshot=capture_result.html_snapshot,
            capture_metadata=capture_result.capture_metadata,
            page_type_hint=page_type_hint,
            title=capture_result.title,
            meta_description=capture_result.meta_description,
        )

        # Create snapshot
        repo.create_snapshot(
            site_import=site_import,
            html_snapshot=capture_result.html_snapshot,
            desktop_screenshot_data_url=capture_result.desktop_screenshot_data_url,
            mobile_screenshot_data_url=capture_result.mobile_screenshot_data_url,
            capture_metadata=capture_result.capture_metadata,
        )

        # Mark import as completed with normalized data
        repo.mark_import_completed(
            site_import=site_import,
            title=normalization_result.title,
            meta_description=normalization_result.meta_description,
            suggested_template_family=normalization_result.suggested_template_family,
            theme_candidate=normalization_result.theme_candidate,
            normalized_sections=normalization_result.normalized_sections,
        )

    except Exception as e:
        logger.exception(f"Failed to capture site: {source_url}")
        error_message = str(e) if str(e) else "Capture failed"
        repo.mark_import_failed(site_import=site_import, capture_error=error_message)

    # Refresh to get updated state
    session.refresh(site_import)
    return site_import


def list_imports(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    limit: int = 25,
) -> list[SiteImport]:
    """List site imports for a workspace."""
    repo = StorefrontImportsRepository(session)
    return repo.list_imports(org_id=org_id, client_id=client_id, limit=limit)


def get_import_detail(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
) -> SiteImport | None:
    """Get detailed import information including snapshot."""
    repo = StorefrontImportsRepository(session)
    return repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)


def get_import_snapshot(
    session: Session,
    *,
    site_import_id: str,
) -> SiteImportSnapshot | None:
    """Get the snapshot for an import."""
    repo = StorefrontImportsRepository(session)
    return repo.get_import_snapshot(site_import_id=site_import_id)


def convert_import_to_variant(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    name: str,
    family: str,
    page_type: str,
    accepted_section_ids: list[str],
    review_notes: str | None,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """
    Convert an import into a draft template variant.

    This creates:
    1. A style preset from the theme candidate
    2. A template variant with the accepted sections
    """
    repo = StorefrontImportsRepository(session)

    # Get the import
    site_import = repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)
    if site_import is None:
        raise SiteImportError("Import not found")

    if site_import.status != "completed":
        raise SiteImportError(f"Cannot convert import with status: {site_import.status}")

    # Validate accepted section IDs
    normalized_sections = site_import.normalized_sections or []
    section_ids = {s.get("id") for s in normalized_sections}
    invalid_ids = set(accepted_section_ids) - section_ids
    if invalid_ids:
        raise SiteImportError(f"Invalid section IDs: {invalid_ids}. Valid IDs: {section_ids}")

    # Filter to accepted sections
    accepted_sections = [s for s in normalized_sections if s.get("id") in accepted_section_ids]

    theme_candidate = site_import.theme_candidate or {}
    # Create provenance record using the helper function
    # Note: This path does not include synthesis, so we pass an empty synthesis dict
    provenance = build_convert_provenance(
        source_url=site_import.source_url,
        source_hostname=site_import.source_hostname,
        imported_at=site_import.created_at.isoformat() if site_import.created_at else None,
        page_type_hint=site_import.page_type_hint,
        synthesis={},  # No synthesis for basic convert
        actor=created_by_user_external_id,
    )

    try:
        style_preset = repo.create_style_preset(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            name=f"{name} - Style",
            tokens=theme_candidate,
            commit=False,
        )

        variant = repo.create_variant_draft(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            style_preset_id=style_preset.id,
            name=name,
            family=family,
            page_type=page_type,
            accepted_sections=accepted_sections,
            provenance=provenance,
            review_notes=review_notes,
            created_by_user_external_id=created_by_user_external_id,
            commit=False,
        )
        session.commit()
        session.refresh(style_preset)
        session.refresh(variant)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to persist template variant draft.") from exc

    return {
        "variant": variant,
        "style_preset": style_preset,
    }


def list_variant_drafts(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    limit: int = 25,
) -> list:
    """List template variant drafts for a workspace."""
    repo = StorefrontImportsRepository(session)
    return repo.list_variant_drafts(org_id=org_id, client_id=client_id, limit=limit)


def get_import_synthesis(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    target_family: str | None = None,
    target_page_type: str | None = None,
    accepted_section_ids: list[str] | None = None,
) -> SynthesisResult | None:
    """
    Get synthesis result for an import.

    Synthesizes normalized sections into structured puckData with
    block coverage scoring and missing block requests.
    """
    repo = StorefrontImportsRepository(session)
    site_import = repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)

    if site_import is None:
        return None

    if site_import.status != "completed":
        return None

    normalized_sections = site_import.normalized_sections or []
    theme_candidate = site_import.theme_candidate or {}
    suggested_family = site_import.suggested_template_family

    # Filter to accepted sections if provided (for preview matching convert behavior)
    if accepted_section_ids:
        section_ids = {s.get("id") for s in normalized_sections}
        invalid_ids = set(accepted_section_ids) - section_ids
        if invalid_ids:
            raise SiteImportError(f"Invalid section IDs: {invalid_ids}. Valid IDs: {section_ids}")
        normalized_sections = [
            s for s in normalized_sections if s.get("id") in accepted_section_ids
        ]

    return synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family=suggested_family,
        target_family=target_family,
        target_page_type=target_page_type,
    )


def convert_import_to_variant_with_synthesis(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    name: str,
    family: str,
    page_type: str,
    accepted_section_ids: list[str],
    review_notes: str | None,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """
    Convert an import into a draft template variant with synthesis.

    This creates:
    1. A style preset from the theme candidate
    2. A template variant with the accepted sections
    3. Synthesis output stored in provenance
    """
    repo = StorefrontImportsRepository(session)

    # Get the import
    site_import = repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)
    if site_import is None:
        raise SiteImportError("Import not found")

    if site_import.status != "completed":
        raise SiteImportError(f"Cannot convert import with status: {site_import.status}")

    # Validate accepted section IDs
    normalized_sections = site_import.normalized_sections or []
    section_ids = {s.get("id") for s in normalized_sections}
    invalid_ids = set(accepted_section_ids) - section_ids
    if invalid_ids:
        raise SiteImportError(f"Invalid section IDs: {invalid_ids}. Valid IDs: {section_ids}")

    # Filter to accepted sections
    accepted_sections = [s for s in normalized_sections if s.get("id") in accepted_section_ids]

    theme_candidate = site_import.theme_candidate or {}

    # Run synthesis using ACCEPTED sections (reviewer-approved), not all normalized sections
    synthesis = synthesize_import(
        normalized_sections=accepted_sections,
        theme_candidate=theme_candidate,
        suggested_family=site_import.suggested_template_family,
        target_family=family,
        target_page_type=page_type,
    )

    # Build synthesis dict for provenance
    synthesis_dict = {
        "target_family": synthesis.targetFamily,
        "target_page_type": synthesis.targetPageType,
        "block_coverage": {
            "total_sections": synthesis.blockCoverage.totalSections,
            "exact_matches": synthesis.blockCoverage.exactMatches,
            "partial_matches": synthesis.blockCoverage.partialMatches,
            "missing_matches": synthesis.blockCoverage.missingMatches,
            "coverage_score": synthesis.blockCoverage.coverageScore,
        },
        "missing_block_requests": [
            {
                "request_id": req.requestId,
                "section_type": req.sectionType,
                "reason": req.reason,
                "source_selector": req.sourceSelector,
                "text_preview": req.textPreview,
                "suggested_family": req.suggestedFamily,
                "suggested_page_type": req.suggestedPageType,
            }
            for req in synthesis.missingBlockRequests
        ],
        "synthesized_puck_data": synthesis.synthesizedPuckData,
    }

    # Create provenance record using the helper function
    provenance = build_convert_provenance(
        source_url=site_import.source_url,
        source_hostname=site_import.source_hostname,
        imported_at=site_import.created_at.isoformat() if site_import.created_at else None,
        page_type_hint=site_import.page_type_hint,
        synthesis=synthesis_dict,
        actor=created_by_user_external_id,
    )

    try:
        style_preset = repo.create_style_preset(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            name=f"{name} - Style",
            tokens=theme_candidate,
            commit=False,
        )

        variant = repo.create_variant_draft(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            style_preset_id=style_preset.id,
            name=name,
            family=family,
            page_type=page_type,
            accepted_sections=accepted_sections,
            provenance=provenance,
            review_notes=review_notes,
            created_by_user_external_id=created_by_user_external_id,
            commit=False,
        )
        session.commit()
        session.refresh(style_preset)
        session.refresh(variant)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to persist synthesized template variant draft.") from exc

    return {
        "variant": variant,
        "style_preset": style_preset,
        "synthesis": synthesis,
    }


def create_draft_from_template(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    template_id: str,
    name: str,
    family: str,
    page_type: str,
    puck_data: dict[str, Any],
    review_notes: str | None,
    created_by_user_external_id: str | None,
    product_id: str | None = None,
    variant_id: str | None = None,
    variant_provider: str | None = None,
    variant_external_id: str | None = None,
    product: Any = None,
    variant: Any = None,
) -> dict[str, Any]:
    """
    Create a draft variant from a built-in storefront template.

    This creates:
    1. A style preset with base design system tokens
    2. A template variant with the template's puckData in provenance

    Args:
        session: Database session.
        org_id: Organization ID.
        client_id: Client/workspace ID.
        template_id: Template ID (e.g., 'sales-pdp').
        name: Name for the draft variant.
        family: Template family.
        page_type: Template page type.
        puck_data: The template's puckData.
        review_notes: Optional review notes.
        created_by_user_external_id: User who created the draft.
        product_id: Product ID for binding context.
        variant_id: Variant ID for binding context.
        variant_provider: Variant provider (e.g., 'medusa').
        variant_external_id: External Medusa variant ID.
        product: Product ORM object for hydration.
        variant: Variant ORM object for hydration.

    Returns:
        Dict with 'variant' and 'style_preset' keys.
    """
    from app.services.design_system_generation import load_base_tokens_template
    from app.services.funnel_templates import get_funnel_template
    from app.services.template_hydration import (
        hydrate_template_puckdata,
        materialize_template_assets,
    )

    repo = StorefrontImportsRepository(session)

    # Get the funnel template for asset materialization
    funnel_template = get_funnel_template(template_id)

    # Step 1: Hydrate puckData with product/variant context
    hydrated_puck_data = puck_data
    if product is not None:
        hydrated_puck_data = hydrate_template_puckdata(
            puck_data=puck_data,
            product=product,
            variant=variant,
        )

    # Step 2: Materialize assets (upload and get public IDs)
    materialized_puck_data = hydrated_puck_data
    if funnel_template is not None:
        materialized_puck_data = materialize_template_assets(
            session=session,
            org_id=org_id,
            client_id=client_id,
            template=funnel_template,
            puck_data=hydrated_puck_data,
        )

    # Build provenance for template draft with binding context
    provenance = build_template_draft_provenance(
        template_id=template_id,
        template_family=family,
        template_page_type=page_type,
        synthesized_puck_data=materialized_puck_data,
        actor=created_by_user_external_id,
        product_id=product_id,
        variant_id=variant_id,
        variant_provider=variant_provider,
        variant_external_id=variant_external_id,
    )

    # Create style preset from base tokens template
    # The base tokens have a flat cssVars structure; we need to structure them
    # into the expected groups (palette, fonts) for governance validation.
    base_tokens = load_base_tokens_template()
    css_vars = base_tokens.get("cssVars", {})

    # Derive storefront token groups from actual base token values
    # These groups are required by validate_token_presence in governance
    storefront_tokens = {
        # Palette: extract color-related CSS variables
        "palette": {
            "brand": css_vars.get("--color-brand"),
            "bg": css_vars.get("--color-bg"),
            "text": css_vars.get("--color-text"),
            "pageBg": css_vars.get("--color-page-bg"),
            "muted": css_vars.get("--color-muted"),
            "border": css_vars.get("--color-border"),
            "soft": css_vars.get("--color-soft"),
            "cta": css_vars.get("--color-cta"),
            "ctaText": css_vars.get("--color-cta-text"),
        },
        # Fonts: extract font-related CSS variables
        "fonts": {
            "sans": css_vars.get("--font-sans"),
            "heading": css_vars.get("--font-heading"),
            "cta": css_vars.get("--font-cta"),
        },
        # Preserve the full cssVars for complete token coverage
        "cssVars": css_vars,
        "dataTheme": base_tokens.get("dataTheme"),
        "fontUrls": base_tokens.get("fontUrls", []),
        "funnelDefaults": base_tokens.get("funnelDefaults", {}),
        "brand": base_tokens.get("brand", {}),
    }

    try:
        style_preset = repo.create_style_preset(
            org_id=org_id,
            client_id=client_id,
            site_import_id=None,  # No site import for template drafts
            name=f"{name} - Style",
            tokens=storefront_tokens,
            commit=False,
        )

        variant = repo.create_variant_draft(
            org_id=org_id,
            client_id=client_id,
            site_import_id=None,  # No site import for template drafts
            style_preset_id=style_preset.id,
            name=name,
            family=family,
            page_type=page_type,
            accepted_sections=[],  # Template drafts don't have sections from import
            provenance=provenance,
            review_notes=review_notes,
            created_by_user_external_id=created_by_user_external_id,
            commit=False,
        )
        session.commit()
        session.refresh(style_preset)
        session.refresh(variant)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to persist template draft variant.") from exc

    return {
        "variant": variant,
        "style_preset": style_preset,
    }
