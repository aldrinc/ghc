from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import FunnelPageVersionStatusEnum
from app.db.models import (
    Asset,
    Campaign,
    Funnel,
    FunnelEvent,
    FunnelPage,
    FunnelPageSlugRedirect,
    FunnelPageVersion,
    FunnelPublication,
    FunnelPublicationLink,
    FunnelPublicationPage,
)


class FunnelsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        *,
        org_id: str,
        client_id: Optional[str] = None,
        product_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        campaign_is_null: Optional[bool] = None,
        experiment_spec_id: Optional[str] = None,
    ) -> list[Funnel]:
        stmt = select(Funnel).where(Funnel.org_id == org_id)
        if client_id:
            stmt = stmt.where(Funnel.client_id == client_id)
        if product_id:
            stmt = stmt.where(Funnel.product_id == product_id)
        if campaign_is_null is True:
            stmt = stmt.where(Funnel.campaign_id.is_(None))
        elif campaign_id is not None:
            stmt = stmt.where(Funnel.campaign_id == campaign_id)
        if experiment_spec_id:
            stmt = stmt.where(Funnel.experiment_spec_id == experiment_spec_id)
        stmt = stmt.order_by(Funnel.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def get(self, *, org_id: str, funnel_id: str) -> Optional[Funnel]:
        stmt = select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)
        return self.session.scalars(stmt).first()

    def get_by_public_id(self, *, public_id: str) -> Optional[Funnel]:
        stmt = select(Funnel).where(Funnel.public_id == public_id)
        return self.session.scalars(stmt).first()

    def create(self, *, org_id: str, client_id: str, name: str, **fields: Any) -> Funnel:
        funnel = Funnel(org_id=org_id, client_id=client_id, name=name, **fields)
        self.session.add(funnel)
        self.session.commit()
        self.session.refresh(funnel)
        return funnel

    def update(self, *, org_id: str, funnel_id: str, **fields: Any) -> Optional[Funnel]:
        funnel = self.get(org_id=org_id, funnel_id=funnel_id)
        if not funnel:
            return None
        for key, value in fields.items():
            setattr(funnel, key, value)
        self.session.commit()
        self.session.refresh(funnel)
        return funnel


class FunnelPagesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, *, funnel_id: str) -> list[FunnelPage]:
        stmt = select(FunnelPage).where(FunnelPage.funnel_id == funnel_id).order_by(
            FunnelPage.ordering.asc(), FunnelPage.created_at.asc()
        )
        return list(self.session.scalars(stmt).all())

    def get(self, *, funnel_id: str, page_id: str) -> Optional[FunnelPage]:
        stmt = select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        funnel_id: str,
        name: str,
        slug: str,
        ordering: int,
        template_id: Optional[str] = None,
        design_system_id: Optional[str] = None,
        next_page_id: Optional[str] = None,
    ) -> FunnelPage:
        page = FunnelPage(
            funnel_id=funnel_id,
            name=name,
            slug=slug,
            ordering=ordering,
            template_id=template_id,
            design_system_id=design_system_id,
            next_page_id=next_page_id,
        )
        self.session.add(page)
        self.session.commit()
        self.session.refresh(page)
        return page

    def update(self, *, page_id: str, **fields: Any) -> Optional[FunnelPage]:
        stmt = select(FunnelPage).where(FunnelPage.id == page_id)
        page = self.session.scalars(stmt).first()
        if not page:
            return None
        for key, value in fields.items():
            setattr(page, key, value)
        self.session.commit()
        self.session.refresh(page)
        return page


class FunnelPageVersionsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest_for_page(
        self, *, page_id: str, status: FunnelPageVersionStatusEnum
    ) -> Optional[FunnelPageVersion]:
        stmt = (
            select(FunnelPageVersion)
            .where(FunnelPageVersion.page_id == page_id, FunnelPageVersion.status == status)
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        )
        return self.session.scalars(stmt).first()


class FunnelPublicRepository:
    """
    Public read-path helpers for active publications.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_publication(self, *, funnel_id: str, publication_id: str) -> Optional[FunnelPublication]:
        stmt = select(FunnelPublication).where(
            FunnelPublication.funnel_id == funnel_id, FunnelPublication.id == publication_id
        )
        return self.session.scalars(stmt).first()

    def list_publication_pages(self, *, publication_id: str) -> list[FunnelPublicationPage]:
        stmt = select(FunnelPublicationPage).where(FunnelPublicationPage.publication_id == publication_id)
        return list(self.session.scalars(stmt).all())

    def get_publication_page_by_slug(
        self, *, publication_id: str, slug: str
    ) -> Optional[FunnelPublicationPage]:
        stmt = select(FunnelPublicationPage).where(
            FunnelPublicationPage.publication_id == publication_id,
            FunnelPublicationPage.slug_at_publish == slug,
        )
        return self.session.scalars(stmt).first()

    def list_publication_links(self, *, publication_id: str) -> list[FunnelPublicationLink]:
        stmt = select(FunnelPublicationLink).where(FunnelPublicationLink.publication_id == publication_id)
        return list(self.session.scalars(stmt).all())

    def get_redirect(self, *, funnel_id: str, from_slug: str) -> Optional[FunnelPageSlugRedirect]:
        stmt = select(FunnelPageSlugRedirect).where(
            FunnelPageSlugRedirect.funnel_id == funnel_id,
            FunnelPageSlugRedirect.from_slug == from_slug,
        )
        return self.session.scalars(stmt).first()

    def get_page_version(self, *, version_id: str) -> Optional[FunnelPageVersion]:
        stmt = select(FunnelPageVersion).where(FunnelPageVersion.id == version_id)
        return self.session.scalars(stmt).first()

    def get_campaign(self, *, org_id: str, campaign_id: str) -> Optional[Campaign]:
        stmt = select(Campaign).where(Campaign.org_id == org_id, Campaign.id == campaign_id)
        return self.session.scalars(stmt).first()

    def get_asset_by_public_id(self, *, public_id: str) -> Optional[Asset]:
        stmt = select(Asset).where(Asset.public_id == public_id)
        return self.session.scalars(stmt).first()

    def create_event(self, *, event: FunnelEvent) -> FunnelEvent:
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event
