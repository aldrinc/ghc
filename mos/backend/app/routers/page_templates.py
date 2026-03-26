"""Page Templates API endpoints.

Canonical endpoints for page template management using the storefront template registry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.schemas.storefront_templates import (
    StorefrontTemplateSummary,
    StorefrontTemplateDetail,
)
from app.services.storefront_templates import (
    get_storefront_template,
    list_storefront_templates,
)

router = APIRouter(prefix="/page-templates", tags=["page-templates"])


def _serialize_summary(template) -> StorefrontTemplateSummary:
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


def _serialize_detail(template) -> StorefrontTemplateDetail:
    from app.schemas.storefront_templates import (
        StorefrontTemplateBindingRequirement,
        StorefrontTemplateStylePolicy,
        StorefrontTemplateImportProvenance,
    )

    return StorefrontTemplateDetail(
        id=template.template_id,
        name=template.name,
        description=template.description,
        previewImage=template.preview_image,
        family=template.family,
        variant=template.variant,
        version=template.version,
        pageType=template.page_type,
        configSlots=list(template.config_slots),
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


def _get_template_or_404(template_id: str):
    """Get template or raise 404."""
    template = get_storefront_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page template not found.",
        )
    return template


@router.get("", response_model=list[StorefrontTemplateSummary])
def list_page_templates(
    _auth: AuthContext = Depends(get_current_user),
) -> list[StorefrontTemplateSummary]:
    """List all available page templates."""
    return [_serialize_summary(template) for template in list_storefront_templates()]


@router.get("/{template_id}", response_model=StorefrontTemplateDetail)
def get_page_template(
    template_id: str,
    _auth: AuthContext = Depends(get_current_user),
) -> StorefrontTemplateDetail:
    """Get detailed information about a page template."""
    template = _get_template_or_404(template_id)
    return _serialize_detail(template)
