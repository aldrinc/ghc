from typing import List, Optional
from pydantic import BaseModel, HttpUrl


class CompanySwipeBrandModel(BaseModel):
    id: str
    org_id: str
    external_brand_id: Optional[str] = None
    name: str
    slug: Optional[str] = None
    ad_library_link: Optional[HttpUrl] = None
    brand_page_link: Optional[HttpUrl] = None
    logo_url: Optional[HttpUrl] = None
    categories: Optional[list] = None


class CompanySwipeMediaModel(BaseModel):
    id: str
    org_id: str
    swipe_asset_id: str
    external_media_id: Optional[str] = None
    path: Optional[str] = None
    url: Optional[HttpUrl] = None
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[HttpUrl] = None
    disk: Optional[str] = None
    type: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    video_length: Optional[int] = None
    download_url: Optional[HttpUrl] = None


class CompanySwipeAssetModel(BaseModel):
    id: str
    org_id: str
    external_ad_id: Optional[str] = None
    external_platform_ad_id: Optional[str] = None
    brand_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    platforms: Optional[str] = None
    cta_type: Optional[str] = None
    cta_text: Optional[str] = None
    display_format: Optional[str] = None
    landing_page: Optional[str] = None
    link_description: Optional[str] = None
    ad_source_link: Optional[str] = None
    media: List[CompanySwipeMediaModel] = []


class ClientSwipeAssetModel(BaseModel):
    id: str
    org_id: str
    client_id: str
    company_swipe_id: Optional[str] = None
    custom_title: Optional[str] = None
    custom_body: Optional[str] = None
    custom_channel: Optional[str] = None
    custom_format: Optional[str] = None
    custom_landing_page: Optional[str] = None
    tags: List[str] = []
    notes: Optional[str] = None
    is_good_example: Optional[bool] = None
    is_bad_example: Optional[bool] = None
