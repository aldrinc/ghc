from __future__ import annotations

import hashlib
import ipaddress
import logging
import mimetypes
import socket
import subprocess
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Sequence, Tuple
from urllib.parse import urlparse

import httpx
from PIL import Image
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db.enums import MediaAssetTypeEnum, MediaMirrorStatusEnum
from app.db.models import AdAssetLink, MediaAsset
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    content: bytes
    sha256: str
    content_type: Optional[str]
    size_bytes: int
    url: str


class MediaMirrorService:
    """
    Download external media, push to Hetzner S3 (no delete), and persist keys on MediaAsset rows.
    """

    def __init__(self, session: Session, storage: Optional[MediaStorage] = None) -> None:
        self.session = session
        self.storage = storage or MediaStorage()
        self.max_bytes = int(settings.MEDIA_MIRROR_MAX_BYTES or 50 * 1024 * 1024)
        self.timeout_seconds = float(settings.MEDIA_MIRROR_TIMEOUT_SECONDS or 15.0)
        self.preview_dim = int(settings.MEDIA_MIRROR_PREVIEW_MAX_DIMENSION or 512)

    def mirror_assets(self, media_assets: Sequence[MediaAsset]) -> None:
        for asset in media_assets:
            self.mirror_asset(asset)
        self.session.commit()

    def _dedupe_media_asset(self, media: MediaAsset, existing: MediaAsset) -> MediaAsset:
        if media.id == existing.id:
            return existing

        source_url = media.source_url
        stored_url = media.stored_url

        link_rows = list(
            self.session.execute(
                select(AdAssetLink.ad_id, AdAssetLink.role).where(
                    AdAssetLink.media_asset_id == media.id
                )
            ).all()
        )
        for ad_id, role in link_rows:
            stmt = (
                insert(AdAssetLink)
                .values(ad_id=ad_id, media_asset_id=existing.id, role=role)
                .on_conflict_do_nothing(index_elements=[AdAssetLink.ad_id, AdAssetLink.media_asset_id])
            )
            self.session.execute(stmt)

        self.session.execute(delete(AdAssetLink).where(AdAssetLink.media_asset_id == media.id))
        self.session.execute(delete(MediaAsset).where(MediaAsset.id == media.id))
        self.session.flush()

        if source_url and not existing.source_url:
            existing.source_url = source_url
        if stored_url and not existing.stored_url:
            existing.stored_url = stored_url
        self.session.add(existing)
        self.session.flush()
        return existing

    def mirror_asset(self, media: MediaAsset) -> MediaAsset:
        now = datetime.now(timezone.utc)
        if media.mirror_status == MediaMirrorStatusEnum.succeeded and media.storage_key:
            return media
        if not media.source_url:
            media.mirror_status = MediaMirrorStatusEnum.failed
            media.mirror_error = "missing_source_url"
            media.mirrored_at = now
            self.session.add(media)
            self.session.flush()
            return media

        try:
            download = self._download(media.source_url)
            mime = download.content_type or self._guess_mime(media.source_url, media.asset_type)
            ext = self._guess_extension(mime)

            # Reuse existing storage if another asset already mirrored this sha.
            existing = self.session.scalar(
                select(MediaAsset).where(
                    MediaAsset.sha256 == download.sha256,
                    MediaAsset.id != media.id,
                )
            )
            if existing:
                media = self._dedupe_media_asset(media, existing)
                if media.mirror_status == MediaMirrorStatusEnum.succeeded and media.storage_key:
                    return media

            storage_key = self.storage.build_key(sha256=download.sha256, ext=ext, kind="orig")
            if not self.storage.object_exists(bucket=self.storage.bucket, key=storage_key):
                self.storage.upload_bytes(
                    bucket=self.storage.bucket,
                    key=storage_key,
                    data=download.content,
                    content_type=mime,
                    cache_control=IMMUTABLE_CACHE_CONTROL,
                )

            preview_bytes: Optional[bytes] = None
            preview_ext = "jpg"
            preview_size: Tuple[int, int] | None = None
            preview_kind = media.asset_type or MediaAssetTypeEnum.OTHER

            if preview_kind in (MediaAssetTypeEnum.IMAGE, MediaAssetTypeEnum.SCREENSHOT):
                preview_bytes, preview_size = self._build_image_preview(download.content)
            elif preview_kind == MediaAssetTypeEnum.VIDEO:
                preview_bytes, preview_size = self._build_video_preview(download.content)

            preview_key: Optional[str] = None
            if preview_bytes:
                preview_key = self.storage.build_key(
                    sha256=download.sha256,
                    ext=preview_ext,
                    kind="prev",
                )
                if not self.storage.object_exists(bucket=self.storage.preview_bucket, key=preview_key):
                    self.storage.upload_bytes(
                        bucket=self.storage.preview_bucket,
                        key=preview_key,
                        data=preview_bytes,
                        content_type="image/jpeg",
                        cache_control=IMMUTABLE_CACHE_CONTROL,
                    )

            status = MediaMirrorStatusEnum.succeeded
            error_msg = None
            if preview_bytes is None:
                if preview_kind == MediaAssetTypeEnum.VIDEO:
                    status = MediaMirrorStatusEnum.partial
                    error_msg = "preview_generation_skipped"
                else:
                    status = MediaMirrorStatusEnum.failed
                    error_msg = "preview_generation_failed"

            media.sha256 = download.sha256
            media.mime_type = media.mime_type or mime
            media.size_bytes = media.size_bytes or download.size_bytes
            if preview_size and not (media.width and media.height):
                media.width, media.height = preview_size
            media.storage_key = media.storage_key or storage_key
            media.preview_storage_key = media.preview_storage_key or preview_key
            media.bucket = media.bucket or self.storage.bucket
            media.preview_bucket = media.preview_bucket or self.storage.preview_bucket
            media.mirror_status = status
            media.mirror_error = error_msg
            media.mirrored_at = now
            self.session.add(media)
            self.session.flush()
        except IntegrityError as exc:
            # Handle races on sha256 uniqueness by reusing the existing asset.
            self.session.rollback()
            existing = self.session.scalar(select(MediaAsset).where(MediaAsset.sha256 == download.sha256))
            if existing:
                return self._dedupe_media_asset(media, existing)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "media_mirror.failed",
                extra={
                    "media_asset_id": str(getattr(media, "id", "")),
                    "source_url": getattr(media, "source_url", None),
                    "asset_type": getattr(media, "asset_type", None),
                },
            )
            # Keep the session clean for callers.
            self.session.rollback()
            media.mirror_status = MediaMirrorStatusEnum.failed
            media.mirror_error = str(exc)[:500]
            media.mirrored_at = now
            self.session.add(media)
            self.session.flush()
        return media

    def _download(self, url: str) -> DownloadResult:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("unsupported_scheme")
        if not parsed.hostname:
            raise RuntimeError("invalid_url")
        self._assert_public_hostname(parsed.hostname)

        timeout = httpx.Timeout(self.timeout_seconds, read=self.timeout_seconds)
        # Facebook CDN occasionally rejects atypical UAs; use a common browser UA to reduce 403s.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=timeout) as resp:
            resp.raise_for_status()
            hasher = hashlib.sha256()
            data = bytearray()
            size = 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > self.max_bytes:
                    raise RuntimeError("media_too_large")
                hasher.update(chunk)
                data.extend(chunk)

            content_type = resp.headers.get("content-type")
            if content_type:
                content_type = content_type.split(";")[0].strip()
            return DownloadResult(
                content=bytes(data),
                sha256=hasher.hexdigest(),
                content_type=content_type or None,
                size_bytes=size,
                url=str(resp.url),
            )

    def _assert_public_hostname(self, hostname: str) -> None:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:  # noqa: PERF203
            raise RuntimeError(f"dns_lookup_failed:{hostname}") from exc
        for _, _, _, _, sockaddr in infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast:
                raise RuntimeError("blocked_private_network")

    def _guess_mime(self, url: str, asset_type: MediaAssetTypeEnum) -> Optional[str]:
        mime, _ = mimetypes.guess_type(url)
        if mime:
            return mime
        if asset_type == MediaAssetTypeEnum.VIDEO:
            return "video/mp4"
        if asset_type in (MediaAssetTypeEnum.IMAGE, MediaAssetTypeEnum.SCREENSHOT):
            return "image/jpeg"
        return None

    def _guess_extension(self, mime: Optional[str]) -> str:
        if not mime:
            return "bin"
        ext = mimetypes.guess_extension(mime)
        if ext:
            return ext.lstrip(".")
        if mime.startswith("image/"):
            return mime.split("/", 1)[1]
        if mime.startswith("video/"):
            return mime.split("/", 1)[1]
        return "bin"

    def _build_image_preview(self, data: bytes) -> tuple[Optional[bytes], Optional[tuple[int, int]]]:
        try:
            with Image.open(BytesIO(data)) as img:
                img = img.convert("RGB")
                orig_size = img.size
                img.thumbnail((self.preview_dim, self.preview_dim), Image.LANCZOS)
                buf = BytesIO()
                img.save(buf, format="JPEG", optimize=True, quality=85)
                return buf.getvalue(), orig_size
        except Exception as exc:  # noqa: BLE001
            logger.warning("media_mirror.preview_image_failed", extra={"error": str(exc)})
            return None, None

    def _build_video_preview(self, data: bytes) -> tuple[Optional[bytes], Optional[tuple[int, int]]]:
        if not shutil.which("ffmpeg"):
            return None, None

        with tempfile.NamedTemporaryFile(suffix=".mp4") as src, tempfile.NamedTemporaryFile(suffix=".jpg") as dst:
            src.write(data)
            src.flush()
            cmd = [
                "ffmpeg",
                "-ss",
                "1.5",
                "-i",
                src.name,
                "-frames:v",
                "1",
                "-vf",
                f"scale='min({self.preview_dim},iw)':-2",
                "-y",
                dst.name,
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                preview_bytes = Path(dst.name).read_bytes()
                with Image.open(dst.name) as img:
                    return preview_bytes, (img.width, img.height)
            except Exception as exc:  # noqa: BLE001
                logger.warning("media_mirror.preview_video_failed", extra={"error": str(exc)})
                return None, None
