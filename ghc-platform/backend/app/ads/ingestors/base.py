from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.ads.types import IngestRequest, NormalizedAdWithAssets, RawAdItem, NormalizeContext
from app.db.enums import AdChannelEnum
from app.db.models import BrandChannelIdentity


class ChannelIngestor(ABC):
    channel: AdChannelEnum

    @abstractmethod
    def build_requests(self, identity: BrandChannelIdentity, *, results_limit: int | None = None) -> List[IngestRequest]:
        raise NotImplementedError

    @abstractmethod
    def run(self, request: IngestRequest) -> list[RawAdItem]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw: RawAdItem, ctx: NormalizeContext) -> NormalizedAdWithAssets:
        raise NotImplementedError
