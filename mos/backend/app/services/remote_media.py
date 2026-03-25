"""
Shared remote media helper for upserting and mirroring remote media.

This service extracts the reusable media-only logic from the Meta ads path
so GetHookd sync can reuse media_assets + MediaMirrorService instead of
AdsRepository.upsert_ad_with_assets.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import MediaAssetTypeEnum, MediaMirrorStatusEnum
from app.db.models import MediaAsset
from app.services.media_mirror import MediaMirrorService

logger = logging.getLogger(__name__)


@dataclass
class RemoteMediaInput:
    """Input for a remote media item."""

    source_url: str
    asset_type: MediaAssetTypeEnum
    metadata: dict[str, Any]
    role: Optional[str] = None  # e.g., "primary", "secondary"


@dataclass
class RemoteMediaOutput:
    """Output for a successfully upserted remote media item."""

    media_asset_id: str
    storage_key: Optional[str]
    preview_storage_key: Optional[str]
    sha256: Optional[str]
    mirror_status: str


class RemoteMediaService:
    """
    Shared helper for upserting remote media into media_assets table
    and mirroring them through MediaMirrorService.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.mirror_service = MediaMirrorService(session)

    def upsert_and_mirror(
        self,
        *,
        channel: str,
        remote_media: RemoteMediaInput,
    ) -> RemoteMediaOutput:
        """
        Upsert a remote media item into media_assets and mirror it.

        Returns the canonical MediaAsset after mirroring.
        """
        # Check for existing by sha256 (if we can get it)
        media = self._find_existing(remote_media.source_url)

        if media is None:
            # Create new MediaAsset
            media = MediaAsset(
                channel=channel,
                asset_type=remote_media.asset_type,
                source_url=remote_media.source_url,
                mirror_status=MediaMirrorStatusEnum.pending,
                metadata_json=remote_media.metadata or {},
            )
            self.session.add(media)
            self.session.flush()

        # Mirror the asset (this may dedupe and replace the media)
        mirrored = self.mirror_service.mirror_asset(media)

        return RemoteMediaOutput(
            media_asset_id=str(mirrored.id),
            storage_key=mirrored.storage_key,
            preview_storage_key=mirrored.preview_storage_key,
            sha256=mirrored.sha256,
            mirror_status=mirrored.mirror_status.value if mirrored.mirror_status else None,
        )

    def upsert_batch(
        self,
        *,
        channel: str,
        remote_media_list: list[RemoteMediaInput],
    ) -> list[RemoteMediaOutput]:
        """
        Upsert and mirror a batch of remote media items.
        """
        results = []
        for remote_media in remote_media_list:
            try:
                result = self.upsert_and_mirror(
                    channel=channel,
                    remote_media=remote_media,
                )
                results.append(result)
            except Exception as exc:
                logger.warning(
                    "remote_media.upsert_failed",
                    extra={
                        "source_url": remote_media.source_url,
                        "error": str(exc),
                    },
                )
                # Continue with next item
                results.append(
                    RemoteMediaOutput(
                        media_asset_id="",
                        storage_key=None,
                        preview_storage_key=None,
                        sha256=None,
                        mirror_status="failed",
                    )
                )

        self.session.commit()
        return results

    def _find_existing(self, source_url: str) -> Optional[MediaAsset]:
        """Find existing MediaAsset by source URL."""
        return self.session.scalar(
            select(MediaAsset).where(
                MediaAsset.source_url == source_url,
            )
        )
