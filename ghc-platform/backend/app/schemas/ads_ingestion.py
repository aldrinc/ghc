from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ads.normalization import (
    derive_primary_domain,
    normalize_brand_name,
    normalize_facebook_page_url,
    normalize_url,
)
from app.db.enums import AdChannelEnum, BrandRoleEnum


class MetaAdsLibraryIdentity(BaseModel):
    facebook_page_urls: List[str] = []

    model_config = ConfigDict(extra="ignore")

    @field_validator("facebook_page_urls", mode="after")
    @classmethod
    def _normalize_urls(cls, urls: List[str]) -> List[str]:
        normalized: List[str] = []
        for url in urls or []:
            canonical = normalize_facebook_page_url(url)
            if canonical and canonical not in normalized:
                normalized.append(canonical)
        return normalized


class BrandChannels(BaseModel):
    meta_ads_library: Optional[MetaAdsLibraryIdentity] = Field(
        default=None, alias=AdChannelEnum.META_ADS_LIBRARY.value
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def as_dict(self) -> Dict[AdChannelEnum, MetaAdsLibraryIdentity]:
        mapping: Dict[AdChannelEnum, MetaAdsLibraryIdentity] = {}
        if self.meta_ads_library:
            mapping[AdChannelEnum.META_ADS_LIBRARY] = self.meta_ads_library
        return mapping


class DiscoveredBrand(BaseModel):
    name: str
    website: Optional[str] = None
    role: BrandRoleEnum
    channels: BrandChannels

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("website")
    @classmethod
    def _normalize_website(cls, value: Optional[str]) -> Optional[str]:
        return normalize_url(value)

    @property
    def normalized_name(self) -> str:
        return normalize_brand_name(self.name)

    @property
    def primary_domain(self) -> Optional[str]:
        return derive_primary_domain(self.website)


class BrandDiscovery(BaseModel):
    brands: List[DiscoveredBrand] = []

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("brands", mode="after")
    @classmethod
    def _dedupe(cls, brands: List[DiscoveredBrand]) -> List[DiscoveredBrand]:
        deduped: List[DiscoveredBrand] = []
        seen_keys = set()
        for brand in brands or []:
            key = (brand.primary_domain, brand.normalized_name)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(brand)
        return deduped
