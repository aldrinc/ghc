from __future__ import annotations

from typing import Dict

from app.ads.apify_client import ApifyClient
from app.ads.ingestors.base import ChannelIngestor
from app.ads.ingestors.meta_ads_library import MetaAdsLibraryIngestor
from app.db.enums import AdChannelEnum


class IngestorRegistry:
    """Simple registry to resolve ingestors by channel."""

    def __init__(self, apify_client: ApifyClient) -> None:
        self._ingestors: Dict[AdChannelEnum, ChannelIngestor] = {
            AdChannelEnum.META_ADS_LIBRARY: MetaAdsLibraryIngestor(apify_client),
        }

    def get(self, channel: AdChannelEnum) -> ChannelIngestor:
        if channel not in self._ingestors:
            raise KeyError(f"No ingestor registered for channel {channel}")
        return self._ingestors[channel]
