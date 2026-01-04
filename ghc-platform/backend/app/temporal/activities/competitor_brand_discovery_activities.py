from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from temporalio import activity

from app.ads.normalization import normalize_url
from app.db.enums import BrandRoleEnum
from app.schemas.ads_ingestion import BrandChannels, BrandDiscovery, DiscoveredBrand, MetaAdsLibraryIdentity
from app.schemas.competitors import CompetitorRow


_VALID_HOST_RE = re.compile(r"^[a-z0-9.-]+$", re.IGNORECASE)


def _extract_facebook_page_ids(raw_url: str) -> List[str]:
    """
    Extract numeric page IDs from common Ads Library / Facebook URLs.
    Supports:
      - view_all_page_id, page_id, or id query params
      - Numeric path segment (e.g., /123456789/)
    """
    ids: List[str] = []
    parsed = urlparse(raw_url)
    qs = parse_qs(parsed.query or "")
    for key in ("view_all_page_id", "page_id", "id"):
        for val in qs.get(key, []):
            cleaned = (val or "").strip()
            if cleaned.isdigit() and cleaned not in ids:
                ids.append(cleaned)

    path_parts = [p for p in (parsed.path or "").split("/") if p]
    for part in reversed(path_parts):
        if part.isdigit() and part not in ids:
            ids.append(part)
            break

    return ids


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
        fb_url = str(row.facebook_page_url) if row.facebook_page_url else None
        fb_id_from_row = (row.facebook_page_id or "").strip() if hasattr(row, "facebook_page_id") else None

        facebook_list: List[str] = []
        facebook_ids: List[str] = []
        if fb_url:
            facebook_list.append(fb_url)
            facebook_urls.append(fb_url)
            facebook_ids = _extract_facebook_page_ids(fb_url)
            if fb_id_from_row and fb_id_from_row.isdigit() and fb_id_from_row not in facebook_ids:
                facebook_ids.append(fb_id_from_row)
            if facebook_ids:
                # Add a canonical page URL built from the ID to help ingestion.
                page_url_from_id = f"https://www.facebook.com/{facebook_ids[0]}"
                if page_url_from_id not in facebook_list:
                    facebook_list.append(page_url_from_id)

        if facebook_list:
            meta_identity = MetaAdsLibraryIdentity(
                facebook_page_urls=facebook_list,
                facebook_page_ids=facebook_ids,
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
        missing = ", ".join(brands_missing_facebook)
        raise RuntimeError(
            f"No Facebook page URLs/IDs found for any competitors: {missing}. "
            "Facebook resolution must return at least one valid page so ads ingestion can run."
        )

    discovery = BrandDiscovery(brands=brands)
    return {
        "brand_discovery": discovery.model_dump(mode="json"),
        "facebook_urls": facebook_urls,
    }
