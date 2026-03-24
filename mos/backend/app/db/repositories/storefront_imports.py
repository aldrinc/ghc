from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SiteImport, SiteImportSnapshot, TemplateStylePreset, TemplateVariant
from app.db.repositories.base import Repository


class StorefrontImportsRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def list_imports(self, *, org_id: str, client_id: str, limit: int = 25) -> list[SiteImport]:
        safe_limit = max(1, min(limit, 100))
        stmt = (
            select(SiteImport)
            .where(SiteImport.org_id == org_id, SiteImport.client_id == client_id)
            .order_by(SiteImport.created_at.desc())
            .limit(safe_limit)
        )
        return list(self.session.scalars(stmt).all())

    def get_import(self, *, org_id: str, client_id: str, site_import_id: str) -> SiteImport | None:
        stmt = select(SiteImport).where(
            SiteImport.id == site_import_id,
            SiteImport.org_id == org_id,
            SiteImport.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def get_import_snapshot(self, *, site_import_id: str) -> SiteImportSnapshot | None:
        stmt = select(SiteImportSnapshot).where(SiteImportSnapshot.site_import_id == site_import_id)
        return self.session.scalars(stmt).first()

    def create_import(
        self,
        *,
        org_id: str,
        client_id: str,
        source_url: str,
        source_hostname: str | None,
        page_type_hint: str | None,
        created_by_user_external_id: str | None,
    ) -> SiteImport:
        now = datetime.now(timezone.utc)
        site_import = SiteImport(
            org_id=org_id,
            client_id=client_id,
            source_url=source_url,
            source_hostname=source_hostname,
            page_type_hint=page_type_hint,
            status="running",
            created_by_user_external_id=created_by_user_external_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(site_import)
        self.session.commit()
        self.session.refresh(site_import)
        return site_import

    def create_snapshot(
        self,
        *,
        site_import: SiteImport,
        html_snapshot: str,
        desktop_screenshot_data_url: str,
        mobile_screenshot_data_url: str,
        capture_metadata: dict[str, Any],
    ) -> SiteImportSnapshot:
        snapshot = SiteImportSnapshot(
            site_import_id=site_import.id,
            org_id=site_import.org_id,
            client_id=site_import.client_id,
            html_snapshot=html_snapshot,
            desktop_screenshot_data_url=desktop_screenshot_data_url,
            mobile_screenshot_data_url=mobile_screenshot_data_url,
            capture_metadata=capture_metadata,
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def mark_import_completed(
        self,
        *,
        site_import: SiteImport,
        title: str | None,
        meta_description: str | None,
        suggested_template_family: str | None,
        theme_candidate: dict[str, Any],
        normalized_sections: list[dict[str, Any]],
    ) -> SiteImport:
        site_import.status = "completed"
        site_import.title = title
        site_import.meta_description = meta_description
        site_import.suggested_template_family = suggested_template_family
        site_import.theme_candidate = theme_candidate
        site_import.normalized_sections = normalized_sections
        site_import.capture_error = None
        site_import.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(site_import)
        return site_import

    def mark_import_failed(self, *, site_import: SiteImport, capture_error: str) -> SiteImport:
        site_import.status = "failed"
        site_import.capture_error = capture_error
        site_import.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(site_import)
        return site_import

    def list_variant_drafts(
        self, *, org_id: str, client_id: str, limit: int = 25
    ) -> list[TemplateVariant]:
        safe_limit = max(1, min(limit, 100))
        stmt = (
            select(TemplateVariant)
            .where(TemplateVariant.org_id == org_id, TemplateVariant.client_id == client_id)
            .order_by(TemplateVariant.created_at.desc())
            .limit(safe_limit)
        )
        return list(self.session.scalars(stmt).all())

    def get_variant_draft(
        self, *, org_id: str, client_id: str, variant_id: str
    ) -> TemplateVariant | None:
        stmt = select(TemplateVariant).where(
            TemplateVariant.id == variant_id,
            TemplateVariant.org_id == org_id,
            TemplateVariant.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def create_style_preset(
        self,
        *,
        org_id: str,
        client_id: str,
        site_import_id: str | None = None,
        name: str,
        tokens: dict[str, Any],
        commit: bool = True,
    ) -> TemplateStylePreset:
        now = datetime.now(timezone.utc)
        preset = TemplateStylePreset(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            name=name,
            status="draft",
            tokens=tokens,
            created_at=now,
            updated_at=now,
        )
        self.session.add(preset)
        self.session.flush()
        if commit:
            self.session.commit()
        self.session.refresh(preset)
        return preset

    def create_variant_draft(
        self,
        *,
        org_id: str,
        client_id: str,
        site_import_id: str | None,
        style_preset_id: str | None,
        name: str,
        family: str,
        page_type: str,
        accepted_sections: list[dict[str, Any]],
        provenance: dict[str, Any],
        review_notes: str | None,
        created_by_user_external_id: str | None,
        commit: bool = True,
    ) -> TemplateVariant:
        now = datetime.now(timezone.utc)
        variant = TemplateVariant(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            style_preset_id=style_preset_id,
            name=name,
            family=family,
            page_type=page_type,
            status="draft",
            accepted_sections=accepted_sections,
            provenance=provenance,
            review_notes=review_notes,
            created_by_user_external_id=created_by_user_external_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(variant)
        self.session.flush()
        if commit:
            self.session.commit()
        self.session.refresh(variant)
        return variant

    def create_derived_variant_draft(
        self,
        *,
        org_id: str,
        client_id: str,
        parent_variant_id: str,
        style_preset_id: str | None,
        name: str,
        family: str,
        page_type: str,
        provenance: dict[str, Any],
        created_by_user_external_id: str | None,
        commit: bool = True,
    ) -> TemplateVariant:
        """Create a derived variant draft from a parent variant mutation."""
        now = datetime.now(timezone.utc)
        variant = TemplateVariant(
            org_id=org_id,
            client_id=client_id,
            site_import_id=None,  # Derived variants don't have direct import
            style_preset_id=style_preset_id,
            name=name,
            family=family,
            page_type=page_type,
            status="draft",
            accepted_sections=[],  # Derived variants don't have sections directly
            provenance=provenance,
            review_notes=None,
            created_by_user_external_id=created_by_user_external_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(variant)
        self.session.flush()
        if commit:
            self.session.commit()
        self.session.refresh(variant)
        return variant

    def get_variant(
        self, *, org_id: str, client_id: str, variant_id: str
    ) -> TemplateVariant | None:
        """Get a single variant by ID with workspace validation."""
        stmt = select(TemplateVariant).where(
            TemplateVariant.id == variant_id,
            TemplateVariant.org_id == org_id,
            TemplateVariant.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def get_style_preset(
        self, *, org_id: str, client_id: str, preset_id: str
    ) -> TemplateStylePreset | None:
        """Get a style preset by ID with workspace validation."""
        stmt = select(TemplateStylePreset).where(
            TemplateStylePreset.id == preset_id,
            TemplateStylePreset.org_id == org_id,
            TemplateStylePreset.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def update_variant_status(
        self,
        *,
        org_id: str,
        client_id: str,
        variant_id: str,
        new_status: str,
        provenance_update: dict[str, Any] | None = None,
    ) -> TemplateVariant | None:
        """
        Atomically update variant status and optionally provenance.

        Args:
            org_id: Organization ID.
            client_id: Client/workspace ID.
            variant_id: Variant ID.
            new_status: New status value (e.g., 'approved', 'published').
            provenance_update: Optional updated provenance dict.

        Returns:
            Updated variant or None if not found.
        """
        variant = self.get_variant(org_id=org_id, client_id=client_id, variant_id=variant_id)
        if variant is None:
            return None

        variant.status = new_status
        variant.updated_at = datetime.now(timezone.utc)

        if provenance_update is not None:
            variant.provenance = provenance_update

        self.session.commit()
        self.session.refresh(variant)
        return variant

    def approve_variant_for_publish(
        self,
        *,
        org_id: str,
        client_id: str,
        variant_id: str,
        approved_by_user_external_id: str | None = None,
        provenance_update: dict[str, Any] | None = None,
    ) -> TemplateVariant | None:
        """
        Mark a variant as approved for publish.

        If the variant is already approved, returns the current variant
        without modifying provenance (idempotent operation).

        Args:
            org_id: Organization ID.
            client_id: Client/workspace ID.
            variant_id: Variant ID.
            approved_by_user_external_id: User who approved.
            provenance_update: Updated provenance with approval event.

        Returns:
            Updated variant or None if not found.
        """
        variant = self.get_variant(org_id=org_id, client_id=client_id, variant_id=variant_id)
        if variant is None:
            return None

        # Idempotent: if already approved, return current state without modification
        if variant.status == "approved":
            return variant

        variant.status = "approved"
        variant.updated_at = datetime.now(timezone.utc)

        if provenance_update is not None:
            variant.provenance = provenance_update

        self.session.commit()
        self.session.refresh(variant)
        return variant
