from __future__ import annotations

from datetime import datetime, timezone
import mimetypes
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.ads.fingerprints import (
    CreativeFingerprintResult,
    MediaAssetInput,
    compute_creative_fingerprint,
)
from app.ads.facts import build_ad_facts_payload
from app.ads.score import compute_ad_score
from app.ads.normalization import derive_primary_domain, normalize_url
from app.ads.types import NormalizedAdWithAssets, NormalizedAsset
from app.db.enums import (
    AdChannelEnum,
    AdIngestStatusEnum,
    AdStatusEnum,
    BrandChannelVerificationStatusEnum,
    BrandRoleEnum,
    ProductBrandRelationshipSourceEnum,
    ProductBrandRelationshipTypeEnum,
    MediaAssetTypeEnum,
    MediaMirrorStatusEnum,
)
from app.db.models import (
    Ad,
    AdAssetLink,
    AdIngestRun,
    AdLibraryPageTotal,
    AdCreative,
    AdCreativeMembership,
    AdFacts,
    AdScore,
    Brand,
    BrandChannelIdentity,
    MediaAsset,
    ProductBrandRelationship,
    ResearchRun,
    ResearchRunBrand,
)
from app.db.repositories.base import Repository


class AdsRepository(Repository):
    """Helpers for brand + ad ingestion workflows."""

    def create_research_run(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: Optional[str],
        campaign_id: Optional[str],
        brand_discovery_payload: Optional[dict],
    ) -> ResearchRun:
        run = ResearchRun(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            brand_discovery_payload=brand_discovery_payload,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def upsert_brand(
        self,
        *,
        org_id: str,
        canonical_name: str,
        normalized_name: str,
        primary_website_url: Optional[str],
        primary_domain: Optional[str],
    ) -> Brand:
        brand: Optional[Brand] = None
        if primary_domain:
            brand = self.session.scalar(
                select(Brand).where(
                    Brand.org_id == org_id,
                    Brand.primary_domain == primary_domain,
                )
            )
        if brand is None:
            brand = self.session.scalar(
                select(Brand).where(
                    Brand.org_id == org_id,
                    Brand.primary_domain.is_(None),
                    Brand.normalized_name == normalized_name,
                )
            )

        if brand:
            brand.canonical_name = brand.canonical_name or canonical_name
            brand.primary_website_url = brand.primary_website_url or primary_website_url
            brand.primary_domain = brand.primary_domain or primary_domain
        else:
            brand = Brand(
                org_id=org_id,
                canonical_name=canonical_name,
                normalized_name=normalized_name,
                primary_website_url=primary_website_url,
                primary_domain=primary_domain,
            )
            self.session.add(brand)

        self.session.commit()
        self.session.refresh(brand)
        return brand

    def upsert_brand_channel_identity(
        self,
        *,
        brand_id: str,
        channel: AdChannelEnum,
        external_id: Optional[str],
        external_url: Optional[str],
        metadata: Optional[dict],
        verification_status: BrandChannelVerificationStatusEnum = BrandChannelVerificationStatusEnum.unverified,
    ) -> BrandChannelIdentity:
        conditions = [
            BrandChannelIdentity.brand_id == brand_id,
            BrandChannelIdentity.channel == channel,
        ]
        if external_id:
            conditions.append(BrandChannelIdentity.external_id == external_id)
        else:
            conditions.append(BrandChannelIdentity.external_id.is_(None))

        identity = self.session.scalar(select(BrandChannelIdentity).where(*conditions))
        if identity is None and external_url:
            identity = self.session.scalar(
                select(BrandChannelIdentity).where(
                    BrandChannelIdentity.brand_id == brand_id,
                    BrandChannelIdentity.channel == channel,
                    BrandChannelIdentity.external_url == external_url,
                )
            )

        if identity:
            identity.external_url = identity.external_url or external_url
            identity.external_id = identity.external_id or external_id
            identity.metadata_json = metadata or identity.metadata_json or {}
            if identity.verification_status == BrandChannelVerificationStatusEnum.unverified:
                identity.verification_status = verification_status
        else:
            identity = BrandChannelIdentity(
                brand_id=brand_id,
                channel=channel,
                external_id=external_id,
                external_url=external_url,
                metadata_json=metadata or {},
                verification_status=verification_status,
            )
            self.session.add(identity)

        self.session.commit()
        self.session.refresh(identity)
        return identity

    def add_research_run_brand(self, *, research_run_id: str, brand_id: str, role: BrandRoleEnum) -> ResearchRunBrand:
        existing = self.session.scalar(
            select(ResearchRunBrand).where(
                ResearchRunBrand.research_run_id == research_run_id,
                ResearchRunBrand.brand_id == brand_id,
            )
        )
        if existing:
            return existing

        link = ResearchRunBrand(research_run_id=research_run_id, brand_id=brand_id, role=role)
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link

    def ensure_product_brand_relationship(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        brand_id: str,
        relationship_type: ProductBrandRelationshipTypeEnum,
        source_type: ProductBrandRelationshipSourceEnum,
        source_id: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
    ) -> ProductBrandRelationship:
        existing = self.session.scalar(
            select(ProductBrandRelationship).where(
                ProductBrandRelationship.org_id == org_id,
                ProductBrandRelationship.client_id == client_id,
                ProductBrandRelationship.product_id == product_id,
                ProductBrandRelationship.brand_id == brand_id,
                ProductBrandRelationship.relationship_type == relationship_type,
            )
        )
        if existing:
            return existing

        relationship = ProductBrandRelationship(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            brand_id=brand_id,
            relationship_type=relationship_type,
            source_type=source_type,
            source_id=source_id,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(relationship)
        self.session.commit()
        self.session.refresh(relationship)
        return relationship

    def start_ingest_run(
        self,
        *,
        research_run_id: str,
        brand_channel_identity_id: str,
        channel: AdChannelEnum,
        requested_url: Optional[str],
        provider: str,
        results_limit: Optional[int],
    ) -> AdIngestRun:
        ingest = AdIngestRun(
            research_run_id=research_run_id,
            brand_channel_identity_id=brand_channel_identity_id,
            channel=channel,
            requested_url=requested_url,
            provider=provider,
            results_limit=results_limit,
        )
        self.session.add(ingest)
        self.session.commit()
        self.session.refresh(ingest)
        return ingest

    def mark_ingest_success(
        self,
        ingest_run_id: str,
        *,
        items_count: int,
        provider_run_id: Optional[str],
        provider_dataset_id: Optional[str],
        is_partial: bool,
    ) -> None:
        self.session.execute(
            update(AdIngestRun)
            .where(AdIngestRun.id == ingest_run_id)
            .values(
                status=AdIngestStatusEnum.SUCCEEDED,
                items_count=items_count,
                provider_run_id=provider_run_id,
                provider_dataset_id=provider_dataset_id,
                is_partial=is_partial,
                finished_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

    def mark_ingest_failure(self, ingest_run_id: str, *, error: str, provider_run_id: Optional[str] = None) -> None:
        self.session.execute(
            update(AdIngestRun)
            .where(AdIngestRun.id == ingest_run_id)
            .values(
                status=AdIngestStatusEnum.FAILED,
                error=error[:5000],
                provider_run_id=provider_run_id,
                finished_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

    def upsert_ad_library_page_total(
        self,
        *,
        org_id: str,
        research_run_id: str,
        brand_id: str,
        brand_channel_identity_id: str,
        channel: AdChannelEnum,
        query_key: str,
        active_status: Optional[str],
        input_url: str,
        total_count: int,
        page_id: Optional[str] = None,
        page_name: Optional[str] = None,
        provider: str = "APIFY",
        provider_actor_id: Optional[str] = None,
        provider_run_id: Optional[str] = None,
        provider_dataset_id: Optional[str] = None,
        actor_input: Optional[dict] = None,
        raw_result: Optional[dict] = None,
    ) -> AdLibraryPageTotal:
        """
        Persist a deterministic "total ads" snapshot for a given page identity and query.

        We key uniqueness by (research_run_id, brand_channel_identity_id, query_key) so the workflow
        can store multiple totals per run (e.g. active vs inactive, or different URL filters) without
        overwriting.
        """
        stmt = (
            insert(AdLibraryPageTotal)
            .values(
                org_id=org_id,
                research_run_id=research_run_id,
                brand_id=brand_id,
                brand_channel_identity_id=brand_channel_identity_id,
                channel=channel,
                query_key=query_key,
                active_status=active_status,
                input_url=input_url,
                total_count=total_count,
                page_id=page_id,
                page_name=page_name,
                provider=provider,
                provider_actor_id=provider_actor_id,
                provider_run_id=provider_run_id,
                provider_dataset_id=provider_dataset_id,
                actor_input=actor_input,
                raw_result=raw_result,
            )
            .on_conflict_do_update(
                index_elements=[
                    AdLibraryPageTotal.research_run_id,
                    AdLibraryPageTotal.brand_channel_identity_id,
                    AdLibraryPageTotal.query_key,
                ],
                set_={
                    "active_status": active_status,
                    "input_url": input_url,
                    "total_count": total_count,
                    "page_id": page_id,
                    "page_name": page_name,
                    "provider": provider,
                    "provider_actor_id": provider_actor_id,
                    "provider_run_id": provider_run_id,
                    "provider_dataset_id": provider_dataset_id,
                    "actor_input": actor_input,
                    "raw_result": raw_result,
                    "updated_at": func.now(),
                },
            )
            .returning(AdLibraryPageTotal)
        )
        row = self.session.execute(stmt).scalar_one()
        self.session.commit()
        self.session.refresh(row)
        return row

    def ad_library_page_totals_for_run(
        self, *, research_run_id: str, query_key: str
    ) -> list[AdLibraryPageTotal]:
        stmt = select(AdLibraryPageTotal).where(
            AdLibraryPageTotal.research_run_id == research_run_id,
            AdLibraryPageTotal.query_key == query_key,
        )
        return list(self.session.scalars(stmt).all())

    def upsert_ad_with_assets(
        self,
        *,
        brand_id: str,
        brand_channel_identity_id: str,
        channel: AdChannelEnum,
        normalized: NormalizedAdWithAssets,
    ) -> tuple[Ad, list[MediaAsset]]:
        now = datetime.now(timezone.utc)
        ad = self.session.scalar(
            select(Ad).where(Ad.channel == channel, Ad.external_ad_id == normalized.external_ad_id)
        )
        if ad is None:
            ad = Ad(
                brand_id=brand_id,
                brand_channel_identity_id=brand_channel_identity_id,
                channel=channel,
                external_ad_id=normalized.external_ad_id,
                ad_status=normalized.ad_status or AdStatusEnum.unknown,
                started_running_at=normalized.started_running_at,
                ended_running_at=normalized.ended_running_at,
                first_seen_at=normalized.first_seen_at or normalized.last_seen_at or now,
                last_seen_at=normalized.last_seen_at or now,
                body_text=normalized.body_text,
                headline=normalized.headline,
                cta_type=normalized.cta_type,
                cta_text=normalized.cta_text,
                landing_url=normalize_url(normalized.landing_url),
                destination_domain=normalized.destination_domain
                or derive_primary_domain(normalize_url(normalized.landing_url)),
                raw_json=normalized.raw_json,
            )
            self.session.add(ad)
            self.session.flush()
        else:
            ad.brand_id = brand_id
            ad.brand_channel_identity_id = brand_channel_identity_id
            ad.ad_status = normalized.ad_status or ad.ad_status or AdStatusEnum.unknown
            ad.started_running_at = ad.started_running_at or normalized.started_running_at
            ad.ended_running_at = normalized.ended_running_at or ad.ended_running_at
            ad.first_seen_at = ad.first_seen_at or normalized.first_seen_at or normalized.last_seen_at or now
            ad.last_seen_at = normalized.last_seen_at or now
            ad.body_text = normalized.body_text or ad.body_text
            ad.headline = normalized.headline or ad.headline
            ad.cta_type = normalized.cta_type or ad.cta_type
            ad.cta_text = normalized.cta_text or ad.cta_text
            ad.landing_url = normalize_url(normalized.landing_url) or ad.landing_url
            ad.destination_domain = (
                normalized.destination_domain
                or derive_primary_domain(normalize_url(normalized.landing_url))
                or ad.destination_domain
            )
            ad.raw_json = normalized.raw_json or ad.raw_json
            self.session.flush()

        media_assets: List[MediaAsset] = []
        for asset in normalized.assets:
            media_asset = self._get_or_create_media_asset(channel=channel, asset=asset)
            self._link_ad_asset(ad_id=ad.id, media_asset_id=media_asset.id, role=asset.role)
            media_assets.append(media_asset)

        self.session.flush()
        self._ensure_creative_membership(ad)
        facts_payload, media_count = self._upsert_ad_facts(ad)
        self._upsert_ad_score(ad=ad, facts_payload=facts_payload, media_count=media_count)
        self.session.commit()
        self.session.refresh(ad)
        return ad, media_assets

    def _get_or_create_media_asset(
        self, *, channel: AdChannelEnum, asset: NormalizedAsset
    ) -> MediaAsset:
        def _guess_mime(asset: NormalizedAsset) -> Optional[str]:
            for url in (asset.stored_url, asset.source_url):
                if not url:
                    continue
                mime, _ = mimetypes.guess_type(url)
                if mime:
                    return mime
            if asset.asset_type == MediaAssetTypeEnum.VIDEO:
                return "video/mp4"
            if asset.asset_type in (MediaAssetTypeEnum.IMAGE, MediaAssetTypeEnum.SCREENSHOT):
                return "image/jpeg"
            return None

        media: Optional[MediaAsset] = None
        if asset.sha256:
            media = self.session.scalar(select(MediaAsset).where(MediaAsset.sha256 == asset.sha256))
        if media is None and asset.source_url:
            media = self.session.scalar(
                select(MediaAsset).where(
                    MediaAsset.channel == channel,
                    MediaAsset.source_url == asset.source_url,
                )
            )

        if media:
            # Merge metadata but keep existing precedence.
            merged_metadata = {**asset.metadata, **(media.metadata_json or {})}
            media.metadata_json = merged_metadata
            inferred_mime = _guess_mime(asset)
            media.mime_type = media.mime_type or asset.mime_type or inferred_mime
            media.size_bytes = media.size_bytes or asset.size_bytes
            media.width = media.width or asset.width
            media.height = media.height or asset.height
            media.duration_ms = media.duration_ms or asset.duration_ms
            media.stored_url = media.stored_url or asset.stored_url
        else:
            inferred_mime = _guess_mime(asset)
            media = MediaAsset(
                channel=channel,
                asset_type=asset.asset_type or MediaAssetTypeEnum.OTHER,
                source_url=asset.source_url,
                stored_url=asset.stored_url,
                mirror_status=MediaMirrorStatusEnum.pending,
                sha256=asset.sha256,
                mime_type=asset.mime_type or inferred_mime,
                size_bytes=asset.size_bytes,
                width=asset.width,
                height=asset.height,
                duration_ms=asset.duration_ms,
                metadata_json=asset.metadata or {},
            )
            self.session.add(media)
            self.session.flush()
        return media

    def _link_ad_asset(self, *, ad_id: str, media_asset_id: str, role: Optional[str]) -> None:
        existing = self.session.scalar(
            select(AdAssetLink).where(
                AdAssetLink.ad_id == ad_id,
                AdAssetLink.media_asset_id == media_asset_id,
            )
        )
        if existing:
            return
        link = AdAssetLink(ad_id=ad_id, media_asset_id=media_asset_id, role=role)
        self.session.add(link)
        self.session.flush()

    def _ensure_creative_membership(self, ad: Ad) -> Optional[AdCreative]:
        brand = self.session.get(Brand, ad.brand_id)
        if not brand:
            return None

        assets = self._media_assets_for_ad(ad.id)
        copy_fields = {
            "primary_text": ad.body_text,
            "headline": ad.headline,
            "description": None,
            "cta_type": ad.cta_type,
            "cta_label": ad.cta_text,
            "destination_url": ad.landing_url,
        }
        fp: CreativeFingerprintResult = compute_creative_fingerprint(copy_fields=copy_fields, assets=assets)

        creative = self._upsert_creative(
            org_id=brand.org_id,
            brand_id=ad.brand_id,
            channel=ad.channel,
            fp=fp,
        )
        self._upsert_membership(ad_id=ad.id, creative_id=creative.id)
        return creative

    def _media_assets_for_ad(self, ad_id: str) -> list[MediaAssetInput]:
        stmt = (
            select(MediaAsset, AdAssetLink.role)
            .join(AdAssetLink, MediaAsset.id == AdAssetLink.media_asset_id)
            .where(AdAssetLink.ad_id == ad_id)
        )
        assets: list[MediaAssetInput] = []
        for media, role in self.session.execute(stmt).all():
            assets.append(
                MediaAssetInput(
                    id=str(media.id),
                    asset_type=media.asset_type,
                    role=role,
                    sha256=media.sha256,
                    storage_key=media.storage_key,
                    preview_storage_key=media.preview_storage_key,
                    stored_url=media.stored_url,
                    source_url=media.source_url,
                    size_bytes=media.size_bytes,
                    width=media.width,
                    height=media.height,
                )
            )
        return assets

    def _upsert_creative(self, *, org_id: str, brand_id: str, channel: AdChannelEnum, fp: CreativeFingerprintResult) -> AdCreative:
        stmt = (
            insert(AdCreative)
            .values(
                org_id=org_id,
                brand_id=brand_id,
                channel=channel,
                fingerprint_algo=fp.fingerprint_algo,
                creative_fingerprint=fp.creative_fingerprint,
                primary_media_asset_id=fp.primary_media_asset_id,
                media_fingerprint=fp.media_fingerprint,
                copy_fingerprint=fp.copy_fingerprint,
                metadata_json={},
            )
            .on_conflict_do_update(
                index_elements=[
                    AdCreative.org_id,
                    AdCreative.brand_id,
                    AdCreative.channel,
                    AdCreative.fingerprint_algo,
                    AdCreative.creative_fingerprint,
                ],
                set_={
                    "primary_media_asset_id": fp.primary_media_asset_id,
                    "media_fingerprint": fp.media_fingerprint,
                    "copy_fingerprint": fp.copy_fingerprint,
                    "updated_at": func.now(),
                },
            )
            .returning(AdCreative)
        )
        creative = self.session.execute(stmt).scalar_one()
        self.session.flush()
        return creative

    def _upsert_membership(self, *, ad_id: str, creative_id: str) -> None:
        stmt = (
            insert(AdCreativeMembership)
            .values(ad_id=ad_id, creative_id=creative_id)
            .on_conflict_do_update(
                index_elements=[AdCreativeMembership.ad_id],
                set_={"creative_id": creative_id, "created_at": func.now()},
            )
        )
        self.session.execute(stmt)
        self.session.flush()

    def _upsert_ad_facts(self, ad: Ad) -> tuple[dict[str, Any], int]:
        brand = self.session.get(Brand, ad.brand_id)
        if not brand:
            return {}, 0
        media_assets = (
            self.session.query(MediaAsset)
            .join(AdAssetLink, AdAssetLink.media_asset_id == MediaAsset.id)
            .filter(AdAssetLink.ad_id == ad.id)
            .all()
        )
        payload = build_ad_facts_payload(ad=ad, brand=brand, media_assets=media_assets)
        stmt = (
            insert(AdFacts)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=[AdFacts.ad_id],
                set_={key: value for key, value in payload.items() if key != "ad_id"}
                | {"updated_at": func.now()},
            )
        )
        self.session.execute(stmt)
        self.session.flush()
        return payload, len(media_assets)

    def update_ads_context(self, research_run_id: str, ads_context: dict) -> None:
        self.session.execute(
            update(ResearchRun)
            .where(ResearchRun.id == research_run_id)
            .values(
                ads_context=ads_context,
                ads_context_generated_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

    def backfill_ad_creatives(self, *, batch_size: int = 500) -> dict[str, int]:
        """Attach creatives + memberships for ads missing one. Idempotent."""
        updated_memberships = 0
        while True:
            batch = (
                self.session.query(Ad)
                .outerjoin(AdCreativeMembership, AdCreativeMembership.ad_id == Ad.id)
                .filter(AdCreativeMembership.id.is_(None))
                .limit(batch_size)
                .all()
            )
            if not batch:
                break

            for ad in batch:
                creative = self._ensure_creative_membership(ad)
                if creative:
                    updated_memberships += 1
            self.session.commit()

        return {"memberships_updated": updated_memberships}

    def _upsert_ad_score(self, *, ad: Ad, facts_payload: dict[str, Any], media_count: int) -> None:
        brand = self.session.get(Brand, ad.brand_id)
        if not brand:
            return
        score_payload = compute_ad_score(ad=ad, facts=facts_payload, media_count=media_count)
        stmt = (
            insert(AdScore)
            .values(
                ad_id=ad.id,
                org_id=brand.org_id,
                brand_id=ad.brand_id,
                channel=ad.channel,
                **score_payload,
            )
            .on_conflict_do_update(
                index_elements=[AdScore.ad_id],
                set_={**score_payload, "updated_at": func.now()},
            )
        )
        self.session.execute(stmt)
        self.session.flush()

    def backfill_ad_facts(self, *, org_id: Optional[str] = None, batch_size: int = 500) -> dict[str, int]:
        created = 0
        while True:
            query = (
                self.session.query(Ad)
                .join(Brand, Brand.id == Ad.brand_id)
                .outerjoin(AdFacts, AdFacts.ad_id == Ad.id)
                .filter(AdFacts.ad_id.is_(None))
                .order_by(Ad.created_at)
            )
            if org_id:
                query = query.filter(Brand.org_id == org_id)
            ads = query.limit(batch_size).all()
            if not ads:
                break
            for ad in ads:
                self._upsert_ad_facts(ad)
                created += 1
            self.session.commit()
        return {"facts_created": created}

    def backfill_ad_scores(self, *, org_id: Optional[str] = None, batch_size: int = 500) -> dict[str, int]:
        created = 0
        while True:
            query = (
                self.session.query(Ad)
                .join(Brand, Brand.id == Ad.brand_id)
                .outerjoin(AdScore, AdScore.ad_id == Ad.id)
                .filter(AdScore.ad_id.is_(None))
                .order_by(Ad.created_at)
            )
            if org_id:
                query = query.filter(Brand.org_id == org_id)
            ads = query.limit(batch_size).all()
            if not ads:
                break
            for ad in ads:
                facts_payload, media_count = self._upsert_ad_facts(ad)
                self._upsert_ad_score(ad=ad, facts_payload=facts_payload, media_count=media_count)
                created += 1
            self.session.commit()
        return {"scores_created": created}

    def latest_research_run_for_product(
        self, *, org_id: str, client_id: str, product_id: str
    ) -> Optional[ResearchRun]:
        return self.session.scalar(
            select(ResearchRun)
            .where(
                ResearchRun.org_id == org_id,
                ResearchRun.client_id == client_id,
                ResearchRun.product_id == product_id,
            )
            .order_by(ResearchRun.created_at.desc())
        )

    def identities_for_run(self, research_run_id: str) -> list[BrandChannelIdentity]:
        stmt = (
            select(BrandChannelIdentity)
            .join(Brand, Brand.id == BrandChannelIdentity.brand_id)
            .join(ResearchRunBrand, ResearchRunBrand.brand_id == Brand.id)
            .where(ResearchRunBrand.research_run_id == research_run_id)
        )
        return list(self.session.scalars(stmt).all())

    def ads_for_run(self, research_run_id: str) -> Iterable[Ad]:
        stmt = (
            select(Ad)
            .join(ResearchRunBrand, ResearchRunBrand.brand_id == Ad.brand_id)
            .where(ResearchRunBrand.research_run_id == research_run_id)
        )
        return list(self.session.scalars(stmt).all())

    def ad_with_media(self, ad_id: str) -> Tuple[Optional[Ad], list[Tuple[MediaAsset, Optional[str]]]]:
        """
        Fetch an ad with its linked media assets and roles.
        """
        ad = self.session.get(Ad, ad_id)
        if not ad:
            return None, []

        stmt = (
            select(MediaAsset, AdAssetLink.role)
            .join(AdAssetLink, MediaAsset.id == AdAssetLink.media_asset_id)
            .where(AdAssetLink.ad_id == ad_id)
        )
        rows: list[Tuple[MediaAsset, Optional[str]]] = list(self.session.execute(stmt).all())
        return ad, rows
