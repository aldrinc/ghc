from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from temporalio import activity

from app.ads.normalization import normalize_facebook_page_url, normalize_url
from app.db.enums import BrandRoleEnum
from app.schemas.ads_ingestion import BrandChannels, BrandDiscovery, DiscoveredBrand, MetaAdsLibraryIdentity
from app.schemas.competitors import CompetitorRow


_VALID_HOST_RE = re.compile(r"^[a-z0-9.-]+$", re.IGNORECASE)
def _clean_website(raw: Optional[str]) -> Optional[str]:
    """
    Normalize noisy website strings that may include backticks or duplicated schemes.
    Returns None when we cannot produce a safe, parseable URL (to avoid domain collisions).
    """
    if not raw:
        return None

    candidate = str(raw).strip().strip("`'\"")
    candidate = candidate.replace("`", "").replace(" ", "").rstrip(".")

    # Collapse double-prefixed schemes such as "https://https:/example.com"
    candidate = re.sub(r"^https?://https?:/?", "https://", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^https:/([^/])", r"https://\\1", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^http:/([^/])", r"http://\\1", candidate, flags=re.IGNORECASE)

    normalized = normalize_url(candidate)
    if not normalized:
        return None

    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if not host or "." not in host or not _VALID_HOST_RE.match(host):
        return None

    return normalized


@activity.defn
def build_competitor_brand_discovery_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build BrandDiscovery from enriched CompetitorRow entries (no markdown parsing).
    """
    raw_competitors = params.get("competitors") or []
    competitors: List[CompetitorRow] = []
    for item in raw_competitors:
        try:
            competitors.append(CompetitorRow.model_validate(item))
        except Exception:
            continue

    brands: List[DiscoveredBrand] = []
    facebook_urls: List[str] = []
    brands_missing_facebook: List[str] = []

    for row in competitors:
        name = row.name or (row.website or "Unknown brand")
        website = _clean_website(row.website)
        if row.website and not website:
            activity.logger.warning(
                "competitor_brand_discovery.invalid_website",
                extra={"raw_website": row.website},
            )
        fb_url = normalize_facebook_page_url(str(row.facebook_page_url)) if row.facebook_page_url else None

        facebook_list: List[str] = []
        if fb_url:
            facebook_list.append(fb_url)
            facebook_urls.append(fb_url)

        if facebook_list:
            meta_identity = MetaAdsLibraryIdentity(
                facebook_page_urls=facebook_list,
            )
        else:
            meta_identity = None
            brands_missing_facebook.append(name or (website or "Unknown brand"))

        brands.append(
            DiscoveredBrand(
                name=name,
                website=website,
                role=BrandRoleEnum.peer,
                channels=BrandChannels(meta_ads_library=meta_identity),
            )
        )

    if not brands:
        return {"brand_discovery": None, "facebook_urls": []}

    if len(brands_missing_facebook) == len(brands):
        # Do not fail the broader research workflow; ads ingestion can be skipped and retried later.
        activity.logger.warning(
            "competitor_brand_discovery.no_facebook_pages",
            extra={"missing_count": len(brands_missing_facebook), "missing_names": brands_missing_facebook[:25]},
        )

    discovery = BrandDiscovery(brands=brands)
    return {
        "brand_discovery": discovery.model_dump(mode="json"),
        "facebook_urls": facebook_urls,
    }
