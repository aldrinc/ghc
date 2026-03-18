from datetime import datetime, timezone
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
    MetaPublishSelection,
    MetaPublishRun,
    MetaPublishRunItem,
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

    def update_creative_spec(self, record: MetaCreativeSpec, **fields) -> MetaCreativeSpec:
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
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

    def get_adset_spec(self, *, org_id: str, adset_spec_id: str) -> Optional[MetaAdSetSpec]:
        stmt = select(MetaAdSetSpec).where(
            MetaAdSetSpec.org_id == org_id,
            MetaAdSetSpec.id == adset_spec_id,
        )
        return self.session.scalars(stmt).first()

    def update_adset_spec(self, record: MetaAdSetSpec, **fields) -> MetaAdSetSpec:
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_publish_selections(
        self,
        *,
        org_id: str,
        campaign_id: str,
        generation_key: str,
        decision: Optional[str] = None,
    ) -> list[MetaPublishSelection]:
        stmt = (
            select(MetaPublishSelection)
            .where(
                MetaPublishSelection.org_id == org_id,
                MetaPublishSelection.campaign_id == campaign_id,
                MetaPublishSelection.generation_key == generation_key,
            )
            .order_by(MetaPublishSelection.created_at.asc(), MetaPublishSelection.asset_id.asc())
        )
        if decision is not None:
            stmt = stmt.where(MetaPublishSelection.decision == decision)
        return list(self.session.scalars(stmt).all())

    def get_publish_selection(
        self,
        *,
        org_id: str,
        campaign_id: str,
        generation_key: str,
        asset_id: str,
    ) -> Optional[MetaPublishSelection]:
        stmt = select(MetaPublishSelection).where(
            MetaPublishSelection.org_id == org_id,
            MetaPublishSelection.campaign_id == campaign_id,
            MetaPublishSelection.generation_key == generation_key,
            MetaPublishSelection.asset_id == asset_id,
        )
        return self.session.scalars(stmt).first()

    def create_publish_selection(self, **fields) -> MetaPublishSelection:
        record = MetaPublishSelection(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_publish_selection(self, record: MetaPublishSelection, **fields) -> MetaPublishSelection:
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def delete_publish_selection(self, record: MetaPublishSelection) -> None:
        self.session.delete(record)
        self.session.commit()

    def list_publish_runs(self, *, org_id: str, campaign_id: str) -> list[MetaPublishRun]:
        stmt = (
            select(MetaPublishRun)
            .where(
                MetaPublishRun.org_id == org_id,
                MetaPublishRun.campaign_id == campaign_id,
            )
            .order_by(MetaPublishRun.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_publish_run(self, *, org_id: str, publish_run_id: str) -> Optional[MetaPublishRun]:
        stmt = select(MetaPublishRun).where(
            MetaPublishRun.org_id == org_id,
            MetaPublishRun.id == publish_run_id,
        )
        return self.session.scalars(stmt).first()

    def create_publish_run(self, **fields) -> MetaPublishRun:
        record = MetaPublishRun(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_publish_run(self, record: MetaPublishRun, **fields) -> MetaPublishRun:
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_publish_run_items(self, *, org_id: str, publish_run_id: str) -> list[MetaPublishRunItem]:
        stmt = (
            select(MetaPublishRunItem)
            .where(
                MetaPublishRunItem.org_id == org_id,
                MetaPublishRunItem.publish_run_id == publish_run_id,
            )
            .order_by(MetaPublishRunItem.created_at.asc(), MetaPublishRunItem.asset_id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def create_publish_run_item(self, **fields) -> MetaPublishRunItem:
        record = MetaPublishRunItem(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_publish_run_item(self, record: MetaPublishRunItem, **fields) -> MetaPublishRunItem:
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
