"""Service helpers for site funnel HTML template imports."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Site, SiteFunnelTemplateImport


class SiteFunnelTemplateImportError(Exception):
    """Error during site funnel template import operations."""


def list_template_imports(session: Session, site_id: str) -> list[SiteFunnelTemplateImport]:
    stmt = (
        select(SiteFunnelTemplateImport)
        .where(SiteFunnelTemplateImport.site_id == site_id)
        .order_by(SiteFunnelTemplateImport.created_at.desc())
    )
    return list(session.scalars(stmt).all())


def get_template_import(
    session: Session, *, site_id: str, template_import_id: str
) -> SiteFunnelTemplateImport | None:
    return session.scalars(
        select(SiteFunnelTemplateImport).where(
            SiteFunnelTemplateImport.id == template_import_id,
            SiteFunnelTemplateImport.site_id == site_id,
        )
    ).first()


def create_template_import(
    session: Session,
    *,
    site_id: str,
    source_label: str,
    html_document: str,
    created_by_user_external_id: str | None = None,
) -> SiteFunnelTemplateImport:
    site = session.scalars(select(Site).where(Site.id == site_id)).first()
    if not site:
        raise SiteFunnelTemplateImportError(f"Site not found: {site_id}")

    normalized_label = source_label.strip()
    if not normalized_label:
        raise SiteFunnelTemplateImportError("sourceLabel is required.")

    if not html_document.strip():
        raise SiteFunnelTemplateImportError("htmlDocument must be a non-empty HTML string.")

    now = datetime.now(timezone.utc)
    template_import = SiteFunnelTemplateImport(
        id=str(uuid4()),
        site_id=site_id,
        source_label=normalized_label,
        html_snapshot=html_document,
        html_sha256=hashlib.sha256(html_document.encode("utf-8")).hexdigest(),
        created_by_user_external_id=created_by_user_external_id,
        created_at=now,
        updated_at=now,
    )
    session.add(template_import)
    session.flush()
    session.refresh(template_import)
    return template_import
