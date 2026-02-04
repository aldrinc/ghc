from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    MetaAd,
    MetaAdCreative,
    MetaAdSet,
    MetaAdSetSpec,
    MetaAssetUpload,
    MetaCampaign,
    MetaCreativeSpec,
)


class MetaAdsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_asset_upload_by_request(
        self, *, org_id: str, ad_account_id: str, request_id: str
    ) -> Optional[MetaAssetUpload]:
        stmt = select(MetaAssetUpload).where(
            MetaAssetUpload.org_id == org_id,
            MetaAssetUpload.ad_account_id == ad_account_id,
            MetaAssetUpload.request_id == request_id,
        )
        return self.session.scalars(stmt).first()

    def get_asset_upload(
        self, *, org_id: str, ad_account_id: str, asset_id: str
    ) -> Optional[MetaAssetUpload]:
        stmt = select(MetaAssetUpload).where(
            MetaAssetUpload.org_id == org_id,
            MetaAssetUpload.ad_account_id == ad_account_id,
            MetaAssetUpload.asset_id == asset_id,
        )
        return self.session.scalars(stmt).first()

    def create_asset_upload(self, **fields) -> MetaAssetUpload:
        record = MetaAssetUpload(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_creative_by_request(
        self, *, org_id: str, ad_account_id: str, request_id: str
    ) -> Optional[MetaAdCreative]:
        stmt = select(MetaAdCreative).where(
            MetaAdCreative.org_id == org_id,
            MetaAdCreative.ad_account_id == ad_account_id,
            MetaAdCreative.request_id == request_id,
        )
        return self.session.scalars(stmt).first()

    def create_creative(self, **fields) -> MetaAdCreative:
        record = MetaAdCreative(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_campaign_by_request(
        self, *, org_id: str, ad_account_id: str, request_id: str
    ) -> Optional[MetaCampaign]:
        stmt = select(MetaCampaign).where(
            MetaCampaign.org_id == org_id,
            MetaCampaign.ad_account_id == ad_account_id,
            MetaCampaign.request_id == request_id,
        )
        return self.session.scalars(stmt).first()

    def create_campaign(self, **fields) -> MetaCampaign:
        record = MetaCampaign(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_campaign_by_meta_id(
        self, *, org_id: str, ad_account_id: str, meta_campaign_id: str
    ) -> Optional[MetaCampaign]:
        stmt = select(MetaCampaign).where(
            MetaCampaign.org_id == org_id,
            MetaCampaign.ad_account_id == ad_account_id,
            MetaCampaign.meta_campaign_id == meta_campaign_id,
        )
        return self.session.scalars(stmt).first()

    def get_adset_by_request(
        self, *, org_id: str, ad_account_id: str, request_id: str
    ) -> Optional[MetaAdSet]:
        stmt = select(MetaAdSet).where(
            MetaAdSet.org_id == org_id,
            MetaAdSet.ad_account_id == ad_account_id,
            MetaAdSet.request_id == request_id,
        )
        return self.session.scalars(stmt).first()

    def create_adset(self, **fields) -> MetaAdSet:
        record = MetaAdSet(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_adset_by_meta_id(
        self, *, org_id: str, ad_account_id: str, meta_adset_id: str
    ) -> Optional[MetaAdSet]:
        stmt = select(MetaAdSet).where(
            MetaAdSet.org_id == org_id,
            MetaAdSet.ad_account_id == ad_account_id,
            MetaAdSet.meta_adset_id == meta_adset_id,
        )
        return self.session.scalars(stmt).first()

    def get_ad_by_request(self, *, org_id: str, ad_account_id: str, request_id: str) -> Optional[MetaAd]:
        stmt = select(MetaAd).where(
            MetaAd.org_id == org_id,
            MetaAd.ad_account_id == ad_account_id,
            MetaAd.request_id == request_id,
        )
        return self.session.scalars(stmt).first()

    def create_ad(self, **fields) -> MetaAd:
        record = MetaAd(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_creative_spec_by_asset(self, *, org_id: str, asset_id: str) -> Optional[MetaCreativeSpec]:
        stmt = select(MetaCreativeSpec).where(
            MetaCreativeSpec.org_id == org_id,
            MetaCreativeSpec.asset_id == asset_id,
        )
        return self.session.scalars(stmt).first()

    def list_creative_specs(
        self,
        *,
        org_id: str,
        campaign_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> list[MetaCreativeSpec]:
        stmt = select(MetaCreativeSpec).where(MetaCreativeSpec.org_id == org_id)
        if campaign_id:
            stmt = stmt.where(MetaCreativeSpec.campaign_id == campaign_id)
        if experiment_id:
            stmt = stmt.where(MetaCreativeSpec.experiment_id == experiment_id)
        if asset_id:
            stmt = stmt.where(MetaCreativeSpec.asset_id == asset_id)
        stmt = stmt.order_by(MetaCreativeSpec.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def create_creative_spec(self, **fields) -> MetaCreativeSpec:
        record = MetaCreativeSpec(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_adset_specs(
        self,
        *,
        org_id: str,
        campaign_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
    ) -> list[MetaAdSetSpec]:
        stmt = select(MetaAdSetSpec).where(MetaAdSetSpec.org_id == org_id)
        if campaign_id:
            stmt = stmt.where(MetaAdSetSpec.campaign_id == campaign_id)
        if experiment_id:
            stmt = stmt.where(MetaAdSetSpec.experiment_id == experiment_id)
        stmt = stmt.order_by(MetaAdSetSpec.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def create_adset_spec(self, **fields) -> MetaAdSetSpec:
        record = MetaAdSetSpec(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
