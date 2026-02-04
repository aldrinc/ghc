from __future__ import annotations

import logging
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


class MediaStorage:
    """
    Thin wrapper around S3-compatible storage (Hetzner) for uploads + presigned GETs.

    NOTE: This intentionally omits any delete helpers to respect the "never delete" requirement.
    """

    def __init__(self) -> None:
        if not settings.MEDIA_STORAGE_BUCKET:
            raise RuntimeError("MEDIA_STORAGE_BUCKET is required")
        if not settings.MEDIA_STORAGE_ENDPOINT:
            raise RuntimeError("MEDIA_STORAGE_ENDPOINT is required")
        if not settings.MEDIA_STORAGE_ACCESS_KEY or not settings.MEDIA_STORAGE_SECRET_KEY:
            raise RuntimeError("MEDIA_STORAGE_ACCESS_KEY and MEDIA_STORAGE_SECRET_KEY are required")

        addressing_style = "path" if settings.MEDIA_STORAGE_FORCE_PATH_STYLE else "auto"
        self.bucket = settings.MEDIA_STORAGE_BUCKET
        self.preview_bucket = settings.MEDIA_STORAGE_PREVIEW_BUCKET or self.bucket
        self.prefix = (settings.MEDIA_STORAGE_PREFIX or "").strip("/")
        self.presign_ttl = int(settings.MEDIA_STORAGE_PRESIGN_TTL_SECONDS or 900)

        session = boto3.session.Session()
        self.client = session.client(
            "s3",
            endpoint_url=settings.MEDIA_STORAGE_ENDPOINT,
            aws_access_key_id=settings.MEDIA_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.MEDIA_STORAGE_SECRET_KEY,
            region_name=settings.MEDIA_STORAGE_REGION or "us-east-1",
            use_ssl=bool(settings.MEDIA_STORAGE_USE_SSL),
            config=Config(
                s3={"addressing_style": addressing_style},
                signature_version="s3v4",
            ),
        )

    def build_key(self, *, sha256: str, ext: str, kind: str = "orig") -> str:
        """
        Content-addressed keys: <prefix>/<kind>/<sha[:2]>/<sha>.<ext>
        """
        ext_clean = ext.lstrip(".") if ext else "bin"
        parts = [p for p in [self.prefix, "orig" if kind == "orig" else "prev"] if p]
        parts.append(sha256[:2])
        filename = f"{sha256}.{ext_clean}"
        return "/".join(parts + [filename])

    def object_exists(self, *, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:  # noqa: PERF203
            code = exc.response.get("Error", {}).get("Code") if hasattr(exc, "response") else None
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def upload_bytes(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: Optional[str],
        cache_control: Optional[str] = None,
        extra_metadata: Optional[dict[str, str]] = None,
    ) -> None:
        kwargs = {
            "Bucket": bucket,
            "Key": key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        if cache_control:
            kwargs["CacheControl"] = cache_control
        if extra_metadata:
            kwargs["Metadata"] = extra_metadata
        self.client.put_object(**kwargs)

    def presign_get(self, *, bucket: str, key: str, expires_in: Optional[int] = None) -> str:
        ttl = int(expires_in or self.presign_ttl or 900)
        return self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=ttl,
        )

    def download_bytes(self, *, key: str, bucket: Optional[str] = None) -> tuple[bytes, Optional[str]]:
        bucket_name = bucket or self.bucket
        obj = self.client.get_object(Bucket=bucket_name, Key=key)
        body = obj.get("Body")
        content_type = obj.get("ContentType")
        data = body.read() if body else b""
        return data, content_type
