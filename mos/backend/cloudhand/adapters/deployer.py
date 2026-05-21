import base64
import binascii
import hashlib
import io
import json
import math
import os
import posixpath
import re
import shlex
import socketserver
import subprocess
import tarfile
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape, unescape
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import UUID
from pathlib import Path
import paramiko
from typing import Any, Dict, Iterator, List, Optional  # noqa: F401

from ..models import (
    ApplicationSourceType,
    ApplicationSpec,
    FunnelArtifactRenderMode,
    FunnelArtifactSourceSpec,
    FunnelPublicationSourceSpec,
    RuntimeType,
)

_NGINX_PROXY_CONNECT_TIMEOUT = "60s"
_NGINX_PROXY_SEND_TIMEOUT = "3600s"
_NGINX_PROXY_READ_TIMEOUT = "3600s"
# Leave headroom above the 200 MiB backend product-asset limit for multipart framing.
_NGINX_APP_CLIENT_MAX_BODY_SIZE = "250m"
_RUNTIME_CACHE_DIR = "/opt/apps/.cloudhand-runtime-cache"
_FUNNEL_ARTIFACT_RELEASES_DIRNAME = "site-releases"
_FUNNEL_ARTIFACT_LIVE_DIRNAME = "site"
_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX = "/__mos/html-deploy-candidates"
_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM = "mos_deploy_candidate_release"
_FUNNEL_ARTIFACT_ACTIVATION_MODE_CANDIDATE_ONLY = "candidate_only"
_HTML_DEPLOY_BRIDGE_VERSION = "inline-html-deploy-bridge-v1"
_STANDALONE_IMPORTED_HTML_BRIDGE_VERSION = _HTML_DEPLOY_BRIDGE_VERSION
_SHORT_UUID_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{8}$")
_ENTRY_PRELOAD_COMPONENT_TYPES = {
    "PreSalesHero",
    "PreSalesTemplate",
    "SalesPdpHero",
    "SalesPdpTemplate",
}
_ENV_ASSIGNMENT_PATTERN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_PUBLIC_ASSET_URL_PATTERN = re.compile(r"/(?:api/)?public/assets/([0-9a-fA-F-]{36})(?:[/?#]|$)")
_ABSOLUTE_PUBLIC_ASSET_URL_PATTERN = re.compile(
    r"(?P<origin>https?://[^\"'\s>]+)/(?:api/)?public/assets/([0-9a-fA-F-]{36})(?P<suffix>(?:[/?#][^\"'\s>]*)?)",
    flags=re.IGNORECASE,
)
_ABSOLUTE_URL_PATTERN = re.compile(r"https?://[^\"'\s<>()]+", flags=re.IGNORECASE)
_TAILWIND_CDN_SCRIPT_PATTERN = re.compile(
    r"<script\b[^>]*\bsrc=(?:\"https://cdn\.tailwindcss\.com(?:\?[^\"<>]*)?\"|'https://cdn\.tailwindcss\.com(?:\?[^'<>]*)?')[^>]*>\s*</script>",
    flags=re.IGNORECASE,
)
_INLINE_SCRIPT_AT_POSITION_PATTERN = re.compile(
    r"\s*<script\b(?![^>]*\bsrc=)[^>]*>(?P<body>[\s\S]*?)</script>",
    flags=re.IGNORECASE,
)
_EXTERNAL_ORIGIN_HINT_HOSTS = {
    "api.fontshare.com",
    "cdnjs.cloudflare.com",
    "connect.facebook.net",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "img.funnelish.com",
    "assets.checkoutchamp.com",
}
_EXTERNAL_STYLESHEET_PRELOAD_HOSTS = {
    "api.fontshare.com",
    "cdn.fontshare.com",
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
}
_FONTSHARE_STYLESHEET_HOSTS = {
    "api.fontshare.com",
    "cdn.fontshare.com",
}
_GOOGLE_FONTS_STYLESHEET_HOSTS = {
    "fonts.googleapis.com",
}
_FONTAWESOME_STYLESHEET_HOSTS = {
    "cdnjs.cloudflare.com",
}
_LEGACY_INSECURE_PUBLIC_ASSET_HOSTS = {
    "api.moshq.app",
}
_MOS_PUBLIC_ASSET_HOSTS = {
    "moshq.app",
    *_LEGACY_INSECURE_PUBLIC_ASSET_HOSTS,
}
_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX = "/_standalone-assets"
_STANDALONE_FONT_ASSET_ROUTE_PREFIX = f"{_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}/fonts"
_STANDALONE_COMPRESSED_IMAGE_ROUTE_PREFIX = f"{_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}/compressed"
_STANDALONE_RESPONSIVE_VARIANT_ROUTE_PREFIX = (
    f"{_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}/responsive"
)
_STANDALONE_LOCAL_IMAGE_ASSET_ROOTS = (
    Path(__file__).resolve().parents[2] / "app" / "templates" / "funnels",
)
_TENOR_PRODUCT_SLUG = "8b89a76d"
_TENOR_FAVICON_SVG_BYTES = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
    b'role="img" aria-label="Tenor">\n'
    b'  <rect width="64" height="64" rx="14" fill="#0F0F0F"/>\n'
    b'  <text x="32" y="39" text-anchor="middle" '
    b'font-family="Arial Black, Impact, sans-serif" font-size="23" '
    b'font-weight="900" fill="#FFFFFF">T</text>\n'
    b'  <rect x="19" y="46" width="26" height="5" rx="2.5" fill="#EE1F2D"/>\n'
    b"</svg>\n"
)
_TENOR_FAVICON_32_PNG_BYTES = base64.b64decode("""
iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAABmJLR0QA/wD/AP+gvaeTAAAB20lEQVRYhe2XMWzT
QBSGv+dLGkdN5A6hUmbStYKMmRmQ6EqXspAtisQYiTVTdkZkZipVLMCeIVMkVAbwQDJFmQpD7LhSXSU2Q5KqKoXa
Vdxj6D+d/O7e/9n3Tr4nXFKhUNhWSr0CngE7wCbr0SnwQ0Q+z2azN77vn6wCshpYlvUcsIHimkz/pilQd1336AJg
aX54GShlRcC+67pHsvzsQ9J/86vy5vN5ReXz+dfAkzs2B8gppc4MYE+DOQBRFO0ZwENdAEDFAAoaAYqGRnMA7gEy
SRfYtk2pVLo2Nh6PaTab6QLUajXK5fK1scFgkDRdcoBGo4FpmlSrVVqtFgDtdhvHcfB9P32Abrf7x7N+v0+v10ts
Dv9BEd4DaAdIXIQrDYdDOp0OAKPR6NYAYllWdOvVa5D2LdAOEKsGHmdyvNt8wJbE451EIS9Pf/J1Ftw4N1bGXbUR
2xxgSwx21UasuRkW9/R/3ojfn/sYwLahYiU9Ceccnsf6L3hiWdYx8ChW5vXr2BCRT5rMEZGPOhsTNwzDirFsFOss
2qW7UiQi9el0+ksBBEHgmKb5HXgK5FI2d0XkYDKZfAC4KOsgCJxsNmsrpc5YbEcRiHeWbpYPfBORt2EYvvA878sq
8BtVWoRZRRomLwAAAABJRU5ErkJggg==
""")
_TENOR_APPLE_TOUCH_ICON_PNG_BYTES = base64.b64decode("""
iVBORw0KGgoAAAANSUhEUgAAALQAAAC0CAYAAAA9zQYyAAAABmJLR0QA/wD/AP+gvaeTAAAJHElEQVR4nO3dX4xU
ZxnH8d9zZnZ3hsK8Z1lWpCVAmwg3CKat9gY1hdabRgMtQi/ahgSjjcXExPgnvTbcaNRgwWjohW0Tqy3lwsQmpdCi
adJorQJK3EZKNduWyP6Z92xXzpnZOa8X/FtwWXbmnJl395nf54bszJxznpBvJu/MnDkj6KxCpVK5U0Q2AFjnnFsr
IncAuAVA/6V/ezs8E2VTAzAJYBzApHPuXREZAvAOgBPW2r8AaHRqGGn3AZYuXboyTdPtALY45z4HoNLuY9K8Yp1z
vw+C4GihUHhxdHT0/XYerC1Br1y5shxF0XYReQzAZgBBO45DC04DwDHn3DNRFL0IIM77ALkGPTg4uLher+9O0/Q7
InJrnvsmdc6LyAER+fH4+LjNa6d5Bd1jjPkmgO8BWJrTPqk7jInI3mq1ug9APevOMgfd39//2TRNDwBYn3Vf1NWG
AOyx1r6aZSdZ1rYlY8z+NE2PgzFTdusAvBKG4T4Afa3upKVn6DAM1zjnngdwT6sHJprF2865nVEU/bPZDZsO2hhz
H4BD4Ntv1F4WwIPW2mPNbNTUkiMMw20AfgvGTO1nALxsjNnZzEaFOe/dmK8CeAZAT5ODEbWqAODBUqn0YZIkb891
g5sKw3ArgF/O9fFEORIAD5RKpX8kSfL3uTx4VsaYzQB+hwyvPIlyUAPwRWvtK7M9aNagK5XKJ0TkLXDNTPODBXCX
tfbMjR4w24vCPhF5HoyZ5g8D4NeYZbVwwzWxMWYfgC+1YSiiLG4tl8smjuOXZ7pzxiXHpY+zj9/ofiLPnIjcW61W
j19/x0xLjmKapk+BMdP8Jc65pzDDW8j/t+QwxnwLwCOdmIoog4+Vy+XxOI7fnH7jNc/Cg4ODi2u12nsABjo5GVGL
Rnt7e9ecP3/+o8s3XLPkqNVqT4Ax08IxUK/Xvzb9hunP0KUwDN91zq3o8FBEWZxbsmTJHcPDwxeAac/QYRjuYMy0
AH08iqJtl/+4ErRz7lE/8xBlIyJX2hUAGBgYuG1qaupf4MlHtDClxWJx1ejo6PsBADQajS+DMdPCFdTr9W3A1SXH
Fo/DEGUmIpuBi0EXnHObPM9DlNW9AApSqVQ+LSJ/9D0NUQ7uDkRko+8piPIgIhsCAGt9D0KUB+fc2sA5t873IEQ5
WReIyBrfUxDl5PYAF7/WQqSBCQAs8T0FUU6WBAAW+56CKCdLAvA3TUiPPv5UBKnCoEkVBk2qMGhShUGTKgyaVGHQ
pAqDJlUYNKnCoEkVBk2qMGhShUGTKgyaVGHQpAqDJlUYNKnCoEkVBk2qMGhShUGTKgyaVGHQpErR9wDzwfr167Fj
xw7fY2Syd+9exHHsewzvxBjjfA/h2/bt23Hw4EHfY2SyevVqWGt9j+EdlxykCoMmVRg0qcKgSRUGTaowaFKFQZMq
DJpUYdCkCoMmVRg0qcJzOQAYY7Bq1aqWt1+2bBkOHz7c8vZnzpzBrl27Wt4eAE6fPo1Go5FpHxrwbDsA1lqcOnWq
5e1XrFiR6fhJkmQ6Pl3FJQepwqBJFQZNqjBoUoVBkyoMmlRh0KQKgyZVGDSpwqBJFQZNqjBoUoVBkyoMmlRh0KQK
gyZVGDSpwqBJFQZNqjBoUoVBkyoMmlRh0KQKgyZVGDSpwqBJFQZNqjBoUoVBkyoMmlRh0KQKgyZVGDSpwqBJFQZN
qjBoUoVBkyr8WTdShc/QpAqDJlUYNKnCoEkVBk2qMGhShUGTKgyaVGHQpAqDJlUYNKnCoEkVBk2qMGhShUGTKkXf
A3TK/T1l7O6rYEOxF2WI73E64gIcTkzVcDCOcHTqgu9xOqIrTvD/bjnE430V32N4tT+2+GFsfY/RduqXHPf3lLs+
ZgB4omSwpafse4y2Ux/0bsZ8RTf8X6gP+pPFXt8jzBsbCvr/L9QHTVepf7GELgj65FTN9wjzxslG4nuEtlMf9ME4
8j3CvPF0MuF7hLZTH/TRqQvY3wVvV93MT2OLY3X970V3xfvQALDl0gcrG4u9WNQlH6z8Fw5/nUrwdDLRFTEDXRQ0
dQf1Sw7qLgyaVGHQpAqDJlUYNKkSAOBHaaRFEgD4yPcURDmZCADo/zyUusVEAICfC5MWNnDOved7CqKcnA1EZMj3
FEQ5GQoAMGhSQUSGAufcSd+DEOXBOXdSABSMMSMAQt8DEWVQtdYuCwA0nHN/8D0NUUavAWgEABAEwVHPwxBl4pw7
Clw6l6NYLL4AoOF1IqLWNRqNxiHgUtAjIyMfADjmdSSi1h2ZnJw8B0w7284596y/eYhaN73dK0FHUfSCc+4DPyMR
texcpVI5fPmP6edDxyLyEw8DEbVMRH4wPDx85Svt15zgXyqVDgAY6fhURK0Z7enp+cX0GwrT/5icnKyXy+UUwBc6
OhZRC0TkybGxsWs+Q5npiitFY8xbADZ2ZiyilvzNWnsngPr0G2f6TuFUEAR70B0Xq6SFyYnIHlwXM3DdkuOyOI7/
XS6XBwDc0+7JiJrlnNtnrf35TPfNdpG3PmPMGwDuas9YRC35k7V2E27w5e7ZLmOQANgJfkWL5o8qLjZ5wysVzHpd
DmvtGRHZCiDOeTCiZtUA7LDWnp3tQTe90Ey1Wn1dRB4GT14if1IAj1hrj9zsgTO+KLxeHMdDpVLpQwAPYPZ1N1He
GgAet9Y+N5cHNxVnGIZbnXO/AlBqZTKiJiUAHrPW/mauGzT9bGuM2QzgJQCm2W2JmlAVkW3VavX1ZjZq+mKN1tpj
IrIRwJvNbks0R38GcHezMQNzXENfL45jmyTJc+Vy2QD4DLiupnw459y+KIoeTpKkpZPkMofY39+/KU3T/QA2ZN0X
dbWTaZp+fWJi4o0sO8nrmbUYhuE3nHNPAliW0z6pO4yIyPer1ep+AFNZd5brUmH58uW3JEnyFefctwHclue+SZ3/
iMjPgiD40djYWG6/jtqutW+pUqk8JCKPArgPLa7VSZ0GgCPOuWejKHoJbfgEuu0v5hYtWrSiWCw+JCJbAHweQH+7
j0nzyjiA4865VxuNxqHL385ul06/O1EwxmwUkU8559YCWAvgdgAVXLwU2WIAvR2eibKp4eKvQFQBRADOAnhHRIac
cyestSfQwdMm/gf/XFEFWrVEcQAAAABJRU5ErkJggg==
""")
_TENOR_PRODUCT_FAVICON_ASSETS = (
    {
        "routePath": f"/{_TENOR_PRODUCT_SLUG}/assets/tenor-favicon.svg",
        "contentType": "image/svg+xml",
        "payload": _TENOR_FAVICON_SVG_BYTES,
    },
    {
        "routePath": f"/{_TENOR_PRODUCT_SLUG}/assets/tenor-favicon-32.png",
        "contentType": "image/png",
        "payload": _TENOR_FAVICON_32_PNG_BYTES,
    },
    {
        "routePath": f"/{_TENOR_PRODUCT_SLUG}/assets/tenor-apple-touch-icon.png",
        "contentType": "image/png",
        "payload": _TENOR_APPLE_TOUCH_ICON_PNG_BYTES,
    },
)
_IMAGE_URL_SUFFIXES = (".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp")
_CSS_URL_REFERENCE_PATTERN = re.compile(r"url\((?P<quote>['\"]?)(?P<url>[^)\"']+)(?P=quote)\)")
_HTML_CLASS_ATTRIBUTE_PATTERN = re.compile(
    r"\bclass\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s/>]+))",
    flags=re.IGNORECASE | re.DOTALL,
)
_IMAGE_CONTENT_TYPE_EXTENSION_MAP = {
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
_BINARY_ASSET_CONTENT_TYPE_EXTENSION_MAP = {
    **_IMAGE_CONTENT_TYPE_EXTENSION_MAP,
    "application/font-sfnt": ".ttf",
    "application/font-woff": ".woff",
    "application/font-woff2": ".woff2",
    "application/octet-stream": "",
    "application/x-font-ttf": ".ttf",
    "application/x-font-woff": ".woff",
    "application/x-font-woff2": ".woff2",
    "font/otf": ".otf",
    "font/ttf": ".ttf",
    "font/woff": ".woff",
    "font/woff2": ".woff2",
}
_FONT_ASSET_URL_SUFFIXES = (".eot", ".otf", ".ttf", ".woff", ".woff2")
_LOCAL_STATIC_ASSET_URL_SUFFIXES = (
    *_IMAGE_URL_SUFFIXES,
    *_FONT_ASSET_URL_SUFFIXES,
    ".css",
    ".js",
    ".json",
    ".mjs",
    ".webmanifest",
)
_LOCAL_STATIC_ASSET_REFERENCE_PATTERN = re.compile(
    r"(?<![/A-Za-z0-9_.-])(?P<url>(?:\./|\.\./|assets/)[^\s\"'`<>)]*)",
    flags=re.IGNORECASE,
)
_FONTAWESOME_FAMILY_SPECS = {
    "fa-solid": {
        "font_family": "Font Awesome 6 Free",
        "font_weight": "900",
        "font_style": "normal",
    },
    "fa-regular": {
        "font_family": "Font Awesome 6 Free",
        "font_weight": "400",
        "font_style": "normal",
    },
    "fa-brands": {
        "font_family": "Font Awesome 6 Brands",
        "font_weight": "400",
        "font_style": "normal",
    },
}
_RESPONSIVE_VARIANT_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_STANDALONE_IMAGE_LAYOUT_VIEWPORTS = (
    ("desktop", {"width": 1440, "height": 2200, "device_scale_factor": 1, "is_mobile": False}),
    ("mobile", {"width": 390, "height": 844, "device_scale_factor": 3, "is_mobile": True}),
)
_STANDALONE_IMAGE_VARIANT_FACTORS = (1, 2)
_STANDALONE_DEFAULT_JPEG_COMPRESSION_QUALITIES = (96, 94, 92)
_STANDALONE_PRESALES_JPEG_COMPRESSION_QUALITIES = (82, 76, 70)
_STANDALONE_DEFAULT_WEBP_COMPRESSION_QUALITIES = (96, 94)
_STANDALONE_PRESALES_WEBP_COMPRESSION_QUALITIES = (82, 76, 70)
_STANDALONE_PRESALES_PNG_WEBP_COMPRESSION_QUALITIES = (86, 80, 74)
_STANDALONE_DEFAULT_RESPONSIVE_WEBP_QUALITY = 96
_STANDALONE_PRESALES_RESPONSIVE_WEBP_QUALITY = 72
_STANDALONE_PARITY_DIFF_CHANNEL_THRESHOLD = 8
_STANDALONE_PARITY_MAX_CHANGED_PERCENT = 0.05
_STANDALONE_PARITY_MAX_HEIGHT_DELTA_PX = 8
_STANDALONE_COMPRESSED_IMAGE_MIN_BYTES = 64 * 1024
_STANDALONE_MIN_COMPRESSED_IMAGE_SAVINGS_BYTES = 4 * 1024
_STANDALONE_MIN_COMPRESSED_IMAGE_SAVINGS_RATIO = 0.03
_STANDALONE_TINY_IMAGE_RESPONSIVE_MIN_BYTES = 16 * 1024
# The deployer should make an HTML artifact deployable, not silently redesign or optimize it.
# Keep optimization off until the optimization pipeline and validator are rebuilt as a stable,
# explicit pre-deploy transform.
_STANDALONE_ENABLE_HTML_DEPLOY_OPTIMIZATION = False
_STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES = 0
_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES = 0
_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES = 0
_STANDALONE_META_PIXEL_DEFER_TIMEOUT_MS = 2500
_STANDALONE_MODERN_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
_STANDALONE_PRESALES_MIN_PSNR_DB = 33.0
_STANDALONE_PRESALES_MIN_RESPONSIVE_PSNR_DB = 31.0
_STANDALONE_MIN_RESPONSIVE_SOURCE_WIDTH_DELTA = 64
_STANDALONE_PRESALES_MIN_RESPONSIVE_SOURCE_WIDTH_DELTA = 1


@dataclass(frozen=True)
class _StandaloneServedAsset:
    content: bytes
    content_type: str


@dataclass(frozen=True)
class _StandaloneImageSource:
    route_path: str
    content: bytes
    content_type: str
    width: int
    height: int
    image_format: str


_RASTER_IMAGE_FORMAT_CONTENT_TYPE_MAP = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _safe_inline_json(value: Any) -> str:
    return (
        json.dumps(value, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _resolve_standalone_upstream_api_origin(*, upstream_api_base_root: str) -> tuple[str, str]:
    normalized = str(upstream_api_base_root or "").strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError(
            "HTML deploy artifacts require source_ref.upstream_api_base_root to be an absolute http(s) URL."
        )

    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            "HTML deploy artifacts require source_ref.upstream_api_base_root to include a scheme and host."
        )
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(
            "HTML deploy artifacts require source_ref.upstream_api_base_root to be an origin URL without a path, "
            f"query, or fragment; got '{normalized}'."
        )

    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")), parsed.netloc


def _funnel_artifact_release_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _validate_funnel_artifact_release_id(release_id: str) -> str:
    normalized = str(release_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", normalized):
        raise ValueError(
            "HTML deploy candidate release id must be 1-128 characters of letters, "
            "numbers, '.', '_', or '-', and must start with a letter or number."
        )
    return normalized


def _resolve_funnel_artifact_release_id(*, source: FunnelArtifactSourceSpec) -> str:
    release_metadata = source.release_metadata if isinstance(source.release_metadata, dict) else {}
    requested_release_id = str(
        release_metadata.get("htmlDeployCandidateReleaseId")
        or release_metadata.get("candidateReleaseId")
        or ""
    ).strip()
    if requested_release_id:
        return _validate_funnel_artifact_release_id(requested_release_id)
    return _funnel_artifact_release_id()


def _should_defer_funnel_artifact_activation(*, source: FunnelArtifactSourceSpec) -> bool:
    release_metadata = source.release_metadata if isinstance(source.release_metadata, dict) else {}
    activation_mode = str(
        release_metadata.get("htmlDeployActivationMode")
        or release_metadata.get("activationMode")
        or ""
    ).strip()
    return activation_mode == _FUNNEL_ARTIFACT_ACTIVATION_MODE_CANDIDATE_ONLY


def _normalize_html_deploy_redirect_path(*, value: str, field_label: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        raise ValueError(f"HTML deploy redirect {field_label} must be non-empty.")
    parsed = urlsplit(raw_value)
    if parsed.scheme or parsed.netloc:
        raise ValueError(
            f"HTML deploy redirect {field_label} must be a same-origin absolute path, got '{raw_value}'."
        )
    path = parsed.path.strip()
    if not path.startswith("/"):
        raise ValueError(
            f"HTML deploy redirect {field_label} must start with '/', got '{raw_value}'."
        )
    normalized_path = posixpath.normpath(path)
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path = f"{normalized_path}/"
    if normalized_path != path:
        raise ValueError(
            f"HTML deploy redirect {field_label} must be normalized, got '{raw_value}'."
        )
    return normalized_path


def _html_deploy_legacy_redirect_specs(*, source: FunnelArtifactSourceSpec) -> list[dict[str, Any]]:
    release_metadata = source.release_metadata if isinstance(source.release_metadata, dict) else {}
    route_manifest = release_metadata.get("htmlDeployRouteManifest")
    if not isinstance(route_manifest, dict):
        route_manifest = release_metadata.get("routeManifest")
    raw_redirects = (
        route_manifest.get("legacyRedirects") if isinstance(route_manifest, dict) else None
    )
    if raw_redirects is None:
        raw_redirects = release_metadata.get("htmlDeployLegacyRedirects")
    if raw_redirects is None:
        return []
    if not isinstance(raw_redirects, list):
        raise ValueError("HTML deploy legacy redirects must be a list.")
    redirects: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for index, raw_redirect in enumerate(raw_redirects):
        if not isinstance(raw_redirect, dict):
            raise ValueError(f"HTML deploy legacy redirect at index {index} must be an object.")
        source_path = _normalize_html_deploy_redirect_path(
            value=str(raw_redirect.get("from") or raw_redirect.get("source") or ""),
            field_label=f"from at index {index}",
        )
        target_path = _normalize_html_deploy_redirect_path(
            value=str(raw_redirect.get("to") or raw_redirect.get("target") or ""),
            field_label=f"to at index {index}",
        )
        if source_path in seen_sources:
            raise ValueError(f"HTML deploy legacy redirect duplicates source path '{source_path}'.")
        if source_path == target_path:
            raise ValueError(
                f"HTML deploy legacy redirect source and target cannot match: '{source_path}'."
            )
        seen_sources.add(source_path)
        status_code = int(raw_redirect.get("status") or 302)
        if status_code not in {301, 302, 307, 308}:
            raise ValueError(
                f"HTML deploy legacy redirect '{source_path}' has unsupported status {status_code}."
            )
        redirects.append(
            {
                "from": source_path,
                "to": target_path,
                "status": status_code,
                "preserveQuery": raw_redirect.get("preserveQuery") is not False,
            }
        )
    return redirects


def _html_deploy_route_alias_specs(*, source: FunnelArtifactSourceSpec) -> list[dict[str, str]]:
    release_metadata = source.release_metadata if isinstance(source.release_metadata, dict) else {}
    route_manifest = release_metadata.get("htmlDeployRouteManifest")
    if not isinstance(route_manifest, dict):
        route_manifest = release_metadata.get("routeManifest")
    raw_aliases = route_manifest.get("routeAliases") if isinstance(route_manifest, dict) else None
    if raw_aliases is None and isinstance(route_manifest, dict):
        raw_aliases = route_manifest.get("legacyAliases")
    if raw_aliases is None:
        raw_aliases = release_metadata.get("htmlDeployRouteAliases")
    if raw_aliases is None:
        return []
    if not isinstance(raw_aliases, list):
        raise ValueError("HTML deploy route aliases must be a list.")
    aliases: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    for index, raw_alias in enumerate(raw_aliases):
        if not isinstance(raw_alias, dict):
            raise ValueError(f"HTML deploy route alias at index {index} must be an object.")
        source_path = _normalize_html_deploy_redirect_path(
            value=str(raw_alias.get("from") or raw_alias.get("source") or ""),
            field_label=f"alias from at index {index}",
        )
        target_path = _normalize_html_deploy_redirect_path(
            value=str(raw_alias.get("to") or raw_alias.get("target") or ""),
            field_label=f"alias to at index {index}",
        )
        if source_path in seen_sources:
            raise ValueError(f"HTML deploy route alias duplicates source path '{source_path}'.")
        if source_path == target_path:
            raise ValueError(
                f"HTML deploy route alias source and target cannot match: '{source_path}'."
            )
        seen_sources.add(source_path)
        aliases.append({"from": source_path, "to": target_path})
    return aliases


def _normalize_html_deploy_funnel_path_alias_token(*, value: str, field_label: str) -> str:
    token = str(value or "").strip().lower()
    if not token:
        raise ValueError(f"HTML deploy funnel path alias {field_label} must be non-empty.")
    if "/" in token or "\\" in token:
        raise ValueError(
            f"HTML deploy funnel path alias {field_label} must be a single path segment, got '{value}'."
        )
    if quote(token, safe="") != token:
        raise ValueError(
            f"HTML deploy funnel path alias {field_label} must already be URL-safe, got '{value}'."
        )
    return token


def _html_deploy_funnel_path_alias_specs(
    *, source: FunnelArtifactSourceSpec
) -> list[dict[str, str]]:
    release_metadata = source.release_metadata if isinstance(source.release_metadata, dict) else {}
    route_manifest = release_metadata.get("htmlDeployRouteManifest")
    if not isinstance(route_manifest, dict):
        route_manifest = release_metadata.get("routeManifest")
    raw_aliases = (
        route_manifest.get("funnelPathAliases") if isinstance(route_manifest, dict) else None
    )
    if raw_aliases is None:
        raw_aliases = release_metadata.get("htmlDeployFunnelPathAliases")
    if raw_aliases is None:
        return []
    if not isinstance(raw_aliases, list):
        raise ValueError("HTML deploy funnel path aliases must be a list.")

    aliases: list[dict[str, str]] = []
    seen_aliases: set[tuple[str, str, str]] = set()
    for index, raw_alias in enumerate(raw_aliases):
        if isinstance(raw_alias, str):
            alias_spec = {"alias": raw_alias}
        elif isinstance(raw_alias, dict):
            alias_spec = raw_alias
        else:
            raise ValueError(
                f"HTML deploy funnel path alias at index {index} must be a string or object."
            )
        alias = _normalize_html_deploy_funnel_path_alias_token(
            value=str(
                alias_spec.get("alias")
                or alias_spec.get("pathToken")
                or alias_spec.get("funnelPathToken")
                or ""
            ),
            field_label=f"alias at index {index}",
        )
        product_slug = str(alias_spec.get("productSlug") or "").strip().lower()
        funnel_slug = str(alias_spec.get("funnelSlug") or "").strip().lower()
        funnel_id = str(alias_spec.get("funnelId") or "").strip().lower()
        publication_id = str(alias_spec.get("publicationId") or "").strip().lower()
        key = (product_slug, funnel_slug or funnel_id or publication_id, alias)
        if key in seen_aliases:
            raise ValueError(
                f"HTML deploy funnel path alias duplicates alias '{alias}' at index {index}."
            )
        seen_aliases.add(key)
        aliases.append(
            {
                "alias": alias,
                "productSlug": product_slug,
                "funnelSlug": funnel_slug,
                "funnelId": funnel_id,
                "publicationId": publication_id,
            }
        )
    return aliases


def _html_deploy_index_path_for_route(*, site_dir: str, route_path: str) -> str:
    normalized_path = str(route_path or "").strip()
    if normalized_path == "/":
        return f"{site_dir}/index.html"
    return f"{site_dir}/{normalized_path.strip('/')}/index.html"


def _normalize_uploaded_env_line(raw_line: str) -> str | None:
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    match = _ENV_ASSIGNMENT_PATTERN.match(stripped)
    if match is None:
        raise ValueError("expected KEY=value syntax")

    key, raw_value = match.groups()
    value = raw_value.strip()
    if not value or value.startswith("#"):
        return f"{key}="

    if value[0] in {'"', "'"}:
        quote = value[0]
        closing_index = 1
        while closing_index < len(value):
            if value[closing_index] == quote and value[closing_index - 1] != "\\":
                break
            closing_index += 1
        if closing_index >= len(value):
            raise ValueError(f"{key} has an unterminated quoted value")
        suffix = value[closing_index + 1 :].strip()
        if suffix and not suffix.startswith("#"):
            raise ValueError(f"{key} has unsupported trailing content after the quoted value")
        value = value[1:closing_index]
        return f"{key}={value}"

    inline_comment_match = re.search(r"\s+#", value)
    if inline_comment_match is not None:
        value = value[: inline_comment_match.start()].rstrip()
    return f"{key}={value}"


def _normalize_uploaded_env_content(*, content: str, source_label: str) -> str:
    normalized_lines: List[str] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        try:
            normalized = _normalize_uploaded_env_line(raw_line)
        except ValueError as exc:
            raise ValueError(
                f"Invalid environment file entry in {source_label}:{line_number}: {exc}"
            ) from exc
        if normalized is not None:
            normalized_lines.append(normalized)
    return "\n".join(normalized_lines) + ("\n" if normalized_lines else "")


def _extract_public_asset_public_id_from_url(raw_url: object) -> str | None:
    if not isinstance(raw_url, str):
        return None
    candidate = raw_url.strip()
    if not candidate:
        return None
    parsed = urlsplit(candidate)
    path = parsed.path if parsed.scheme or parsed.netloc else candidate
    match = _PUBLIC_ASSET_URL_PATTERN.search(path)
    if not match:
        return None
    try:
        return str(UUID(match.group(1).strip()))
    except ValueError:
        return None


_DECORATIVE_IMAGE_ALT_MARKERS = (
    "avatar",
    "badge",
    "check",
    "flag",
    "icon",
    "logo",
    "rating",
    "ratings",
    "star",
    "stars",
    "verified",
)
_DECORATIVE_IMAGE_CLASS_MARKERS = (
    "w-4",
    "h-4",
    "w-5",
    "h-5",
    "w-6",
    "h-6",
    "w-8",
    "h-8",
    "w-10",
    "h-10",
    "w-12",
    "h-12",
    "w-[32px]",
    "h-[32px]",
    "w-[45px]",
    "h-[45px]",
    "w-[100px]",
    "h-[100px]",
)


def _is_probably_decorative_imported_html_image(raw_tag: str) -> bool:
    raw_src = str(_read_html_tag_attribute(raw_tag, "src") or "").strip().lower()
    alt_text = str(_read_html_tag_attribute(raw_tag, "alt") or "").strip().lower()
    class_text = str(_read_html_tag_attribute(raw_tag, "class") or "").strip().lower()
    alt_words = {word for word in re.split(r"[^a-z0-9]+", alt_text) if word}
    if raw_src.startswith("data:image/"):
        return True
    if alt_words and any(marker in alt_words for marker in _DECORATIVE_IMAGE_ALT_MARKERS):
        return True
    if class_text and any(marker in class_text for marker in _DECORATIVE_IMAGE_CLASS_MARKERS):
        return True
    return False


def _resolve_imported_html_priority_image_index(html_document: str) -> int | None:
    fallback_index: int | None = None
    preferred_index: int | None = None
    for image_index, match in enumerate(
        re.finditer(r"<img\b[^>]*>", html_document, flags=re.IGNORECASE)
    ):
        raw_tag = match.group(0)
        existing_loading = str(_read_html_tag_attribute(raw_tag, "loading") or "").strip().lower()
        existing_fetchpriority = (
            str(_read_html_tag_attribute(raw_tag, "fetchpriority") or "").strip().lower()
        )
        if existing_loading == "eager" or existing_fetchpriority == "high":
            return image_index
        if fallback_index is None:
            fallback_index = image_index
        if preferred_index is None and not _is_probably_decorative_imported_html_image(raw_tag):
            preferred_index = image_index
    return preferred_index if preferred_index is not None else fallback_index


def _read_html_tag_attribute(raw_tag: str, attribute_name: str) -> str | None:
    pattern = re.compile(
        rf"\b{re.escape(attribute_name)}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s/>]+))",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(raw_tag)
    if not match:
        return None
    for group in match.groups():
        if group is not None:
            return group
    return None


def _html_link_rel_tokens(raw_tag: str) -> set[str]:
    rel_value = str(_read_html_tag_attribute(raw_tag, "rel") or "")
    return {token.strip().lower() for token in rel_value.replace(",", " ").split() if token.strip()}


def _is_html_favicon_link_tag(raw_tag: str) -> bool:
    rel_tokens = _html_link_rel_tokens(raw_tag)
    return bool({"icon", "apple-touch-icon", "mask-icon"} & rel_tokens)


def _strip_html_favicon_link_tags(html_document: str) -> str:
    def _replace_link(match: re.Match[str]) -> str:
        raw_tag = match.group(0)
        return "" if _is_html_favicon_link_tag(raw_tag) else raw_tag

    return re.sub(r"<link\b[^>]*>", _replace_link, html_document, flags=re.IGNORECASE)


def _tenor_product_favicon_head_block() -> str:
    return (
        f'<link rel="icon" type="image/svg+xml" '
        f'href="/{_TENOR_PRODUCT_SLUG}/assets/tenor-favicon.svg" '
        f'data-mos-product-favicon="true">'
        f'<link rel="icon" type="image/png" sizes="32x32" '
        f'href="/{_TENOR_PRODUCT_SLUG}/assets/tenor-favicon-32.png" '
        f'data-mos-product-favicon="true">'
        f'<link rel="apple-touch-icon" sizes="180x180" '
        f'href="/{_TENOR_PRODUCT_SLUG}/assets/tenor-apple-touch-icon.png" '
        f'data-mos-product-favicon="true">'
    )


def _is_absolute_url_candidate(raw_url: str, *, skip_hosts: set[str] | None = None) -> bool:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return False
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return False
    normalized_host = parsed.netloc.strip().lower()
    if normalized_host in {
        str(host or "").strip().lower() for host in (skip_hosts or set()) if str(host or "").strip()
    }:
        return False
    return True


def _extract_absolute_image_urls_from_img_tags(
    html_document: str,
    *,
    skip_hosts: set[str] | None = None,
) -> list[str]:
    candidate_urls: list[str] = []
    seen_urls: set[str] = set()

    def _record(candidate_url: str) -> None:
        normalized = str(candidate_url or "").strip()
        if not normalized or normalized in seen_urls:
            return
        if not _is_absolute_url_candidate(normalized, skip_hosts=skip_hosts):
            return
        seen_urls.add(normalized)
        candidate_urls.append(normalized)

    for match in re.finditer(r"<img\b[^>]*>", html_document, flags=re.IGNORECASE):
        raw_tag = match.group(0)
        raw_src = str(_read_html_tag_attribute(raw_tag, "src") or "").strip()
        if raw_src and not raw_src.lower().startswith("data:image/"):
            _record(raw_src)

        raw_srcset = str(_read_html_tag_attribute(raw_tag, "srcset") or "").strip()
        if not raw_srcset:
            continue
        for raw_candidate in raw_srcset.split(","):
            srcset_token = raw_candidate.strip()
            if not srcset_token:
                continue
            src_url = srcset_token.split()[0].strip()
            if src_url and not src_url.lower().startswith("data:image/"):
                _record(src_url)

    return candidate_urls


def _extract_relative_image_urls_from_img_tags(html_document: str) -> list[str]:
    candidate_urls: list[str] = []
    seen_urls: set[str] = set()

    def _record(candidate_url: str) -> None:
        normalized = str(candidate_url or "").strip()
        if not normalized or normalized in seen_urls:
            return
        lowered = normalized.lower()
        if lowered.startswith(("data:image/", "http://", "https://", "//")):
            return
        if lowered.startswith(("javascript:", "mailto:", "tel:", "#")):
            return
        parsed = urlsplit(normalized)
        if parsed.scheme or parsed.netloc:
            return
        path = parsed.path or normalized
        if not any(path.lower().endswith(suffix) for suffix in _IMAGE_URL_SUFFIXES):
            return
        seen_urls.add(normalized)
        candidate_urls.append(normalized)

    for match in re.finditer(r"<img\b[^>]*>", html_document, flags=re.IGNORECASE):
        raw_tag = match.group(0)
        raw_src = str(_read_html_tag_attribute(raw_tag, "src") or "").strip()
        if raw_src:
            _record(raw_src)

        raw_srcset = str(_read_html_tag_attribute(raw_tag, "srcset") or "").strip()
        if not raw_srcset:
            continue
        for raw_candidate in raw_srcset.split(","):
            srcset_token = raw_candidate.strip()
            if not srcset_token:
                continue
            src_url = srcset_token.split()[0].strip()
            if src_url:
                _record(src_url)

    return candidate_urls


def _is_relative_standalone_asset_reference(
    raw_url: str,
    *,
    suffixes: tuple[str, ...],
) -> bool:
    normalized = str(raw_url or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered.startswith(("data:", "blob:", "http://", "https://", "//")):
        return False
    if lowered.startswith(("javascript:", "mailto:", "tel:", "#")):
        return False
    parsed = urlsplit(normalized)
    if parsed.scheme or parsed.netloc:
        return False
    path = str(parsed.path or normalized).strip()
    if not path.startswith(("./", "../", "assets/")):
        return False
    normalized_route = _normalize_standalone_static_asset_reference_route(path).lower()
    if not normalized_route.startswith("/assets/"):
        return False
    return normalized_route.endswith(tuple(suffix.lower() for suffix in suffixes))


def _extract_relative_standalone_asset_urls_from_html_document(
    html_document: str,
    *,
    suffixes: tuple[str, ...],
) -> list[str]:
    candidate_urls: list[str] = []
    seen_urls: set[str] = set()

    def _record(candidate_url: str) -> None:
        normalized = str(candidate_url or "").strip()
        if not normalized or normalized in seen_urls:
            return
        if not _is_relative_standalone_asset_reference(normalized, suffixes=suffixes):
            return
        seen_urls.add(normalized)
        candidate_urls.append(normalized)

    for match in _LOCAL_STATIC_ASSET_REFERENCE_PATTERN.finditer(str(html_document or "")):
        _record(match.group("url"))
    for match in _CSS_URL_REFERENCE_PATTERN.finditer(str(html_document or "")):
        _record(match.group("url"))

    return candidate_urls


def _extract_relative_image_urls_from_html_document(html_document: str) -> list[str]:
    return _extract_relative_standalone_asset_urls_from_html_document(
        html_document,
        suffixes=_IMAGE_URL_SUFFIXES,
    )


def _candidate_standalone_static_asset_routes(
    route_path: str,
    *,
    asset_route_prefixes: tuple[str, ...],
) -> list[str]:
    normalized_route = _normalize_standalone_static_asset_reference_route(route_path)
    if not normalized_route.startswith("/assets/"):
        return [normalized_route]
    relative_asset_path = normalized_route.removeprefix("/assets/")
    candidates: list[str] = []

    def _add(candidate: str) -> None:
        normalized_candidate = posixpath.normpath(candidate)
        if candidate.endswith("/") and not normalized_candidate.endswith("/"):
            normalized_candidate += "/"
        if normalized_candidate not in candidates:
            candidates.append(normalized_candidate)

    _add(normalized_route)
    for raw_prefix in asset_route_prefixes:
        prefix = str(raw_prefix or "").strip()
        if not prefix:
            continue
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        _add(f"{prefix}{relative_asset_path}")
    return candidates


def _rewrite_relative_standalone_static_asset_references(
    html_document: str,
    *,
    standalone_served_assets: dict[str, _StandaloneServedAsset],
    context_label: str,
    asset_route_prefixes: tuple[str, ...] = ("/assets/",),
) -> str:
    rewritten_document = str(html_document or "")
    unresolved: list[str] = []
    for raw_url in _extract_relative_standalone_asset_urls_from_html_document(
        rewritten_document,
        suffixes=_LOCAL_STATIC_ASSET_URL_SUFFIXES,
    ):
        parsed = urlsplit(raw_url)
        route_path = _normalize_standalone_static_asset_reference_route(parsed.path or raw_url)
        replacement_route = next(
            (
                candidate_route
                for candidate_route in _candidate_standalone_static_asset_routes(
                    route_path,
                    asset_route_prefixes=asset_route_prefixes,
                )
                if candidate_route in standalone_served_assets
            ),
            "",
        )
        if not replacement_route:
            unresolved.append(raw_url)
            continue
        replacement_url = urlunsplit(("", "", replacement_route, parsed.query, parsed.fragment))
        rewritten_document = rewritten_document.replace(raw_url, replacement_url)
    if unresolved:
        raise ValueError(
            f"{context_label} contains relative local asset reference(s) that were not present "
            f"in the html-deploy asset payload: {sorted(set(unresolved))!r}."
        )
    return rewritten_document


def _html_tag_has_attribute(raw_tag: str, attribute_name: str) -> bool:
    return _read_html_tag_attribute(raw_tag, attribute_name) is not None


def _append_html_tag_attributes(raw_tag: str, attributes: list[tuple[str, str]]) -> str:
    if not attributes:
        return raw_tag
    closing = "/>" if raw_tag.rstrip().endswith("/>") else ">"
    closing_index = raw_tag.rfind(closing)
    if closing_index < 0:
        raise ValueError(f"Could not append attributes to malformed HTML tag: {raw_tag[:80]}")
    suffix = "".join(f' {name}="{escape(str(value), quote=True)}"' for name, value in attributes)
    return f"{raw_tag[:closing_index]}{suffix}{raw_tag[closing_index:]}"


def _set_html_tag_attribute(raw_tag: str, attribute_name: str, attribute_value: str) -> str:
    replacement = f'{attribute_name}="{escape(str(attribute_value), quote=True)}"'
    pattern = re.compile(
        rf"\b{re.escape(attribute_name)}\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s/>]+)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if pattern.search(raw_tag):
        return pattern.sub(replacement, raw_tag, count=1)
    return _append_html_tag_attributes(raw_tag, [(attribute_name, attribute_value)])


def _find_nth_img_tag(html_document: str, target_index: int) -> str | None:
    for image_index, match in enumerate(
        re.finditer(r"<img\b[^>]*>", html_document, flags=re.IGNORECASE)
    ):
        if image_index == target_index:
            return match.group(0)
    return None


def _replace_nth_img_tag(html_document: str, target_index: int, replacement_tag: str) -> str:
    image_index = -1

    def _replace(match: re.Match[str]) -> str:
        nonlocal image_index
        image_index += 1
        if image_index == target_index:
            return replacement_tag
        return match.group(0)

    return re.sub(r"<img\b[^>]*>", _replace, html_document, flags=re.IGNORECASE)


def _optimize_standalone_imported_html_document(html_document: str) -> str:
    priority_image_index = _resolve_imported_html_priority_image_index(html_document)
    image_index = -1

    def _replace_image(match: re.Match[str]) -> str:
        nonlocal image_index
        image_index += 1

        raw_tag = match.group(0)
        existing_loading = str(_read_html_tag_attribute(raw_tag, "loading") or "").strip().lower()
        existing_fetchpriority = (
            str(_read_html_tag_attribute(raw_tag, "fetchpriority") or "").strip().lower()
        )
        should_remain_eager = (
            existing_loading == "eager"
            or existing_fetchpriority == "high"
            or (priority_image_index is not None and image_index == priority_image_index)
        )

        attributes_to_add: list[tuple[str, str]] = []
        if not existing_loading:
            attributes_to_add.append(("loading", "eager" if should_remain_eager else "lazy"))
        if _html_tag_has_attribute(raw_tag, "decoding"):
            raw_tag = _set_html_tag_attribute(raw_tag, "decoding", "async")
        else:
            attributes_to_add.append(("decoding", "async"))
        if not existing_fetchpriority:
            attributes_to_add.append(("fetchpriority", "high" if should_remain_eager else "low"))

        return _append_html_tag_attributes(raw_tag, attributes_to_add)

    return re.sub(r"<img\b[^>]*>", _replace_image, html_document, flags=re.IGNORECASE)


def _build_standalone_render_optimization_css(*, page_stage: str | None) -> str:
    normalized_stage = str(page_stage or "").strip().lower().replace("-", "_")
    if normalized_stage == "sales":
        return (
            "@supports (content-visibility:auto){"
            "body>section:nth-of-type(n+3),body>footer{"
            "content-visibility:auto;"
            "contain-intrinsic-size:auto 960px;"
            "}}"
        )
    if normalized_stage in {"pre_sales", "presales"}:
        return (
            "@supports (content-visibility:auto){"
            "body>div:nth-of-type(n+3):not(.fixed){"
            "content-visibility:auto;"
            "contain-intrinsic-size:auto 720px;"
            "}"
            ".article-body>*:nth-child(n+13){"
            "content-visibility:auto;"
            "}"
            ".article-body>p:nth-child(n+13),"
            ".article-body>ul:nth-child(n+13),"
            ".article-body>ol:nth-child(n+13),"
            ".article-body>blockquote:nth-child(n+13){"
            "contain-intrinsic-size:auto 112px;"
            "}"
            ".article-body>h2:nth-child(n+13),"
            ".article-body>h3:nth-child(n+13){"
            "contain-intrinsic-size:auto 64px;"
            "}"
            ".article-body>figure:nth-child(n+13){"
            "contain-intrinsic-size:auto 420px;"
            "}"
            ".article-body>div:nth-child(n+13){"
            "contain-intrinsic-size:auto 180px;"
            "}"
            "}"
        )
    return ""


def _minify_standalone_imported_html_document(html_document: str) -> str:
    normalized = str(html_document or "").strip()
    if not normalized:
        return normalized
    normalized = re.sub(
        r"<!--(?!\s*\[if|\s*<!\[endif|\s*MOS_HTML_DEPLOY_BRIDGE_)[\s\S]*?-->",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r">\s+<", "><", normalized)
    return normalized.strip()


def _has_meaningful_compression_savings(*, original_bytes: int, candidate_bytes: int) -> bool:
    if candidate_bytes <= 0 or original_bytes <= 0 or candidate_bytes >= original_bytes:
        return False
    minimum_savings = max(
        _STANDALONE_MIN_COMPRESSED_IMAGE_SAVINGS_BYTES,
        int(round(original_bytes * _STANDALONE_MIN_COMPRESSED_IMAGE_SAVINGS_RATIO)),
    )
    return (original_bytes - candidate_bytes) >= minimum_savings


def _is_presales_stage(page_stage: str | None) -> bool:
    normalized = str(page_stage or "").strip().lower().replace("-", "_")
    return normalized in {"pre_sales", "presales"}


def _normalize_remote_standalone_fetch_url(raw_url: str) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return candidate
    parsed = urlsplit(candidate)
    if (
        parsed.scheme.lower() == "https"
        and parsed.netloc.strip().lower() in _LEGACY_INSECURE_PUBLIC_ASSET_HOSTS
        and _PUBLIC_ASSET_URL_PATTERN.search(parsed.path or "")
    ):
        return urlunsplit(("http", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return candidate


def _calculate_image_psnr_db(*, reference_image: Any, candidate_image: Any) -> float:
    from PIL import ImageChops, ImageStat

    if reference_image.size != candidate_image.size:
        raise ValueError("reference and candidate images must share dimensions to calculate PSNR")
    candidate_mode = (
        "RGBA" if "A" in reference_image.getbands() or "A" in candidate_image.getbands() else "RGB"
    )
    reference = reference_image.convert(candidate_mode)
    candidate = candidate_image.convert(candidate_mode)
    diff = ImageChops.difference(reference, candidate)
    stat = ImageStat.Stat(diff)
    rms_components = [float(value or 0.0) for value in getattr(stat, "rms", [])]
    if not rms_components:
        return float("inf")
    mean_square_error = sum(component * component for component in rms_components) / float(
        len(rms_components)
    )
    if mean_square_error <= 0:
        return float("inf")
    return 20.0 * math.log10(255.0 / math.sqrt(mean_square_error))


def _resolve_imported_html_preload_image_href(html_document: str) -> str | None:
    preload_spec = _resolve_imported_html_preload_image_spec(html_document)
    if preload_spec is None:
        return None
    return preload_spec["href"]


def _resolve_imported_html_preload_image_spec(html_document: str) -> dict[str, str] | None:
    fallback_src: str | None = None
    fallback_srcset: str | None = None
    fallback_sizes: str | None = None
    preferred_src: str | None = None
    preferred_srcset: str | None = None
    preferred_sizes: str | None = None
    for match in re.finditer(r"<img\b[^>]*>", html_document, flags=re.IGNORECASE):
        raw_tag = match.group(0)
        raw_src = _read_html_tag_attribute(raw_tag, "src") or _read_html_tag_attribute(
            raw_tag, "data-src"
        )
        normalized_src = str(raw_src or "").strip()
        if not normalized_src or normalized_src.lower().startswith("data:image/"):
            continue
        normalized_srcset = str(_read_html_tag_attribute(raw_tag, "srcset") or "").strip()
        normalized_sizes = str(_read_html_tag_attribute(raw_tag, "sizes") or "").strip()
        existing_loading = str(_read_html_tag_attribute(raw_tag, "loading") or "").strip().lower()
        existing_fetchpriority = (
            str(_read_html_tag_attribute(raw_tag, "fetchpriority") or "").strip().lower()
        )
        if existing_loading == "eager" or existing_fetchpriority == "high":
            result = {"href": normalized_src}
            if normalized_srcset:
                result["imagesrcset"] = normalized_srcset
            if normalized_sizes:
                result["imagesizes"] = normalized_sizes
            return result
        if fallback_src is None:
            fallback_src = normalized_src
            fallback_srcset = normalized_srcset or None
            fallback_sizes = normalized_sizes or None
        if preferred_src is None and not _is_probably_decorative_imported_html_image(raw_tag):
            preferred_src = normalized_src
            preferred_srcset = normalized_srcset or None
            preferred_sizes = normalized_sizes or None
    selected_src = preferred_src or fallback_src
    if not selected_src:
        return None
    result = {"href": selected_src}
    selected_srcset = preferred_srcset if preferred_src else fallback_srcset
    selected_sizes = preferred_sizes if preferred_src else fallback_sizes
    if selected_srcset:
        result["imagesrcset"] = selected_srcset
    if selected_sizes:
        result["imagesizes"] = selected_sizes
    return result


def _normalize_standalone_public_asset_urls(
    html_document: str,
    *,
    allowed_hosts: set[str] | None = None,
) -> str:
    normalized_hosts = {
        str(host or "").strip().lower()
        for host in (allowed_hosts or set())
        if str(host or "").strip()
    }

    def _replace(match: re.Match[str]) -> str:
        if normalized_hosts:
            origin = str(match.group("origin") or "").strip()
            host = urlsplit(origin).netloc.strip().lower()
            if host not in normalized_hosts and host not in _MOS_PUBLIC_ASSET_HOSTS:
                return match.group(0)
        return f"/public/assets/{match.group(2)}{match.group('suffix') or ''}"

    return _ABSOLUTE_PUBLIC_ASSET_URL_PATTERN.sub(_replace, html_document)


def _is_mirrorable_absolute_image_url(
    raw_url: str,
    *,
    skip_hosts: set[str] | None = None,
) -> bool:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return False
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return False
    normalized_host = parsed.netloc.strip().lower()
    if normalized_host in {
        str(host or "").strip().lower() for host in (skip_hosts or set()) if str(host or "").strip()
    }:
        return False
    normalized_path = parsed.path.strip().lower()
    if _PUBLIC_ASSET_URL_PATTERN.search(parsed.path):
        return True
    return normalized_path.endswith(_IMAGE_URL_SUFFIXES)


def _resolve_mirrored_image_extension(*, content_type: str, source_url: str) -> str:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    extension = _IMAGE_CONTENT_TYPE_EXTENSION_MAP.get(normalized_content_type)
    if extension:
        return extension
    normalized_path = urlsplit(source_url).path.strip().lower()
    for suffix in _IMAGE_URL_SUFFIXES:
        if normalized_path.endswith(suffix):
            return suffix
    raise ValueError(
        f"Could not determine mirrored image extension for '{source_url}' with content type '{content_type}'."
    )


def _resolve_mirrored_binary_extension(*, content_type: str, source_url: str) -> str:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    extension = _BINARY_ASSET_CONTENT_TYPE_EXTENSION_MAP.get(normalized_content_type)
    if extension:
        return extension
    normalized_path = urlsplit(source_url).path.strip().lower()
    for suffix in (*_IMAGE_URL_SUFFIXES, *_FONT_ASSET_URL_SUFFIXES):
        if normalized_path.endswith(suffix):
            return suffix
    raise ValueError(
        f"Could not determine mirrored asset extension for '{source_url}' with content type '{content_type}'."
    )


def _resolve_binary_asset_content_type(*, source_url: str, response_content_type: str) -> str:
    normalized_content_type = str(response_content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type and normalized_content_type != "application/octet-stream":
        return normalized_content_type
    normalized_path = urlsplit(source_url).path.strip().lower()
    if normalized_path.endswith(".woff2"):
        return "font/woff2"
    if normalized_path.endswith(".woff"):
        return "font/woff"
    if normalized_path.endswith(".ttf"):
        return "font/ttf"
    if normalized_path.endswith(".otf"):
        return "font/otf"
    if normalized_path.endswith(".svg"):
        return "image/svg+xml"
    return normalized_content_type or "application/octet-stream"


def _detect_raster_image_content_type(
    *,
    payload: bytes,
    hinted_content_type: str,
) -> str:
    normalized_hint = str(hinted_content_type or "").split(";", 1)[0].strip().lower()
    if normalized_hint == "image/svg+xml":
        return normalized_hint
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            normalized_format = str(image.format or "").strip().upper()
    except Exception:  # noqa: BLE001
        return normalized_hint or "application/octet-stream"
    return _RASTER_IMAGE_FORMAT_CONTENT_TYPE_MAP.get(
        normalized_format, normalized_hint or "application/octet-stream"
    )


def _decode_stylesheet_payload(*, payload: bytes, source_url: str, context_label: str) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"{context_label} failed to decode stylesheet bytes from '{source_url}' using a supported text encoding."
    )


def _build_font_preload_tag(*, href: str, content_type: str) -> str:
    normalized_href = str(href or "").strip()
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if not normalized_href:
        raise ValueError("Font preload href must be non-empty.")
    type_attr = (
        f' type="{escape(normalized_content_type, quote=True)}"' if normalized_content_type else ""
    )
    return (
        f'<link rel="preload" as="font" href="{escape(normalized_href, quote=True)}"'
        f'{type_attr} crossorigin="anonymous" data-mos-font-preload="true">'
    )


def _html_deploy_directory_slash_redirect_nginx_block() -> str:
    return """        set $mos_html_deploy_directory_redirect "";
        if ($uri ~ "^(.+[^/])$") {
            set $mos_html_deploy_directory_redirect $uri;
        }
        if (!-d $request_filename) {
            set $mos_html_deploy_directory_redirect "";
        }
        if ($mos_html_deploy_directory_redirect != "") {
            return 302 $mos_html_deploy_directory_redirect/$is_args$args;
        }
"""


def _preferred_font_asset_url(urls: list[str]) -> str:
    normalized_urls = [str(url or "").strip() for url in urls if str(url or "").strip()]
    if not normalized_urls:
        raise ValueError("Preferred font asset URL requires at least one candidate.")
    for suffix in (".woff2", ".woff", ".ttf", ".otf"):
        for candidate in normalized_urls:
            if urlsplit(candidate).path.lower().endswith(suffix):
                return candidate
    return normalized_urls[0]


def _extract_css_property(*, block_body: str, property_name: str) -> str | None:
    pattern = re.compile(rf"\b{re.escape(property_name)}\s*:\s*([^;]+)", flags=re.IGNORECASE)
    match = pattern.search(block_body)
    if match is None:
        return None
    return str(match.group(1) or "").strip().strip("\"'")


def _extract_fontawesome_icon_usage_from_html(html_document: str) -> dict[str, set[str]]:
    usage: dict[str, set[str]] = {family: set() for family in _FONTAWESOME_FAMILY_SPECS}
    for match in _HTML_CLASS_ATTRIBUTE_PATTERN.finditer(html_document):
        raw_value = next((group for group in match.groups() if group is not None), "")
        class_tokens = [token.strip() for token in str(raw_value or "").split() if token.strip()]
        if not class_tokens:
            continue
        family_class = next(
            (token for token in class_tokens if token in _FONTAWESOME_FAMILY_SPECS), None
        )
        icon_classes = [
            token
            for token in class_tokens
            if token.startswith("fa-") and token not in _FONTAWESOME_FAMILY_SPECS
        ]
        if not icon_classes:
            continue
        resolved_family = family_class or "fa-solid"
        usage.setdefault(resolved_family, set()).update(icon_classes)
    return {family: icons for family, icons in usage.items() if icons}


def _parse_fontawesome_icon_codepoints(stylesheet_text: str) -> dict[str, int]:
    icon_codepoints: dict[str, int] = {}
    for match in re.finditer(
        r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*content\s*:\s*[\"']\\{1,2}(?P<code>[0-9a-fA-F]+)[\"'][^{}]*)\}",
        stylesheet_text,
        flags=re.IGNORECASE,
    ):
        selectors = str(match.group("selectors") or "")
        codepoint = int(str(match.group("code") or "0"), 16)
        for selector_class in re.findall(r"\.([A-Za-z0-9-]+)::?before", selectors):
            if selector_class.startswith("fa-") and selector_class not in _FONTAWESOME_FAMILY_SPECS:
                icon_codepoints.setdefault(selector_class, codepoint)
    return icon_codepoints


def _parse_css_font_face_blocks(stylesheet_text: str) -> list[dict[str, Any]]:
    font_faces: list[dict[str, Any]] = []
    for match in re.finditer(
        r"@font-face\s*{(?P<body>[^}]*)}", stylesheet_text, flags=re.IGNORECASE | re.DOTALL
    ):
        body = str(match.group("body") or "")
        family_name = _extract_css_property(block_body=body, property_name="font-family")
        font_weight = _extract_css_property(block_body=body, property_name="font-weight")
        font_style = _extract_css_property(block_body=body, property_name="font-style") or "normal"
        font_display = (
            _extract_css_property(block_body=body, property_name="font-display") or "swap"
        )
        unicode_range = _extract_css_property(block_body=body, property_name="unicode-range")
        urls: list[str] = []
        for url_match in _CSS_URL_REFERENCE_PATTERN.finditer(body):
            raw_url = str(url_match.group("url") or "").strip()
            if raw_url and not raw_url.lower().startswith("data:"):
                urls.append(raw_url)
        if not family_name or not urls:
            continue
        font_faces.append(
            {
                "body": body,
                "family_name": family_name,
                "font_weight": (font_weight or "").strip() or "400",
                "font_style": font_style,
                "font_display": font_display,
                "unicode_range": unicode_range,
                "urls": urls,
            }
        )
    return font_faces


def _strip_css_font_face_blocks(stylesheet_text: str) -> str:
    return re.sub(r"@font-face\s*{[^}]*}\s*", "", stylesheet_text, flags=re.IGNORECASE | re.DOTALL)


def _extract_html_text_codepoints(html_document: str) -> set[int]:
    scrubbed_document = re.sub(
        r"<(script|style|noscript)\b[^>]*>[\s\S]*?</\1>",
        " ",
        str(html_document or ""),
        flags=re.IGNORECASE,
    )
    raw_text = unescape(re.sub(r"<[^>]+>", " ", scrubbed_document))

    attribute_values: list[str] = []
    for attribute_name in ("alt", "aria-label", "placeholder", "title", "value"):
        for match in re.finditer(
            rf"\b{re.escape(attribute_name)}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s/>]+))",
            scrubbed_document,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            raw_value = next((group for group in match.groups() if group is not None), "")
            if raw_value:
                attribute_values.append(unescape(str(raw_value)))

    normalized_text = re.sub(r"\s+", " ", " ".join([raw_text, *attribute_values])).strip()
    return {ord(character) for character in normalized_text}


def _parse_css_unicode_ranges(unicode_range: str | None) -> list[tuple[int, int]]:
    normalized = str(unicode_range or "").strip()
    if not normalized:
        return []

    parsed_ranges: list[tuple[int, int]] = []
    for raw_token in normalized.split(","):
        token = str(raw_token or "").strip().upper()
        if not token:
            continue
        if not token.startswith("U+"):
            raise ValueError(f"Unsupported CSS unicode-range token {token!r}.")
        token_value = token[2:]
        if "?" in token_value:
            start = int(token_value.replace("?", "0"), 16)
            end = int(token_value.replace("?", "F"), 16)
        elif "-" in token_value:
            start_token, end_token = token_value.split("-", 1)
            start = int(start_token, 16)
            end = int(end_token, 16)
        else:
            start = end = int(token_value, 16)
        parsed_ranges.append((start, end))
    return parsed_ranges


def _filter_codepoints_for_unicode_range(
    *, codepoints: set[int], unicode_range: str | None
) -> set[int]:
    parsed_ranges = _parse_css_unicode_ranges(unicode_range)
    if not parsed_ranges:
        return set(codepoints)
    return {
        codepoint
        for codepoint in codepoints
        if any(start <= codepoint <= end for start, end in parsed_ranges)
    }


def _preferred_font_subset_source_url(urls: list[str]) -> str:
    normalized_urls = [str(url or "").strip() for url in urls if str(url or "").strip()]
    if not normalized_urls:
        raise ValueError("Preferred font subset source URL requires at least one candidate.")
    for suffix in (".ttf", ".otf", ".woff2", ".woff"):
        for candidate in normalized_urls:
            if urlsplit(candidate).path.lower().endswith(suffix):
                return candidate
    return normalized_urls[0]


def _origin_hint_markup_for_html_document(html_document: str) -> str:
    external_origins: list[tuple[str, bool]] = []
    seen_origins: set[str] = set()
    has_localized_fontshare = 'data-mos-local-fontshare="true"' in html_document
    has_localized_google_fonts = 'data-mos-local-google-fonts="true"' in html_document
    has_localized_fontawesome = 'data-mos-local-font-awesome="true"' in html_document
    for match in re.finditer(r"https://([A-Za-z0-9.-]+)(?::\d+)?(?:/|\"|'|$)", html_document):
        host = str(match.group(1) or "").strip().lower()
        if host not in _EXTERNAL_ORIGIN_HINT_HOSTS:
            continue
        if has_localized_fontshare and host in _FONTSHARE_STYLESHEET_HOSTS:
            continue
        if has_localized_google_fonts and host in (
            _GOOGLE_FONTS_STYLESHEET_HOSTS | {"fonts.gstatic.com"}
        ):
            continue
        if has_localized_fontawesome and host in _FONTAWESOME_STYLESHEET_HOSTS:
            continue
        origin = f"https://{host}"
        if origin in seen_origins:
            continue
        seen_origins.add(origin)
        external_origins.append((origin, host == "fonts.gstatic.com"))

    if not external_origins:
        external_origins = []

    blocks: list[str] = []
    for origin, needs_crossorigin in external_origins:
        crossorigin_attr = ' crossorigin="anonymous"' if needs_crossorigin else ""
        blocks.append(f'<link rel="dns-prefetch" href="{origin}">')
        blocks.append(f'<link rel="preconnect" href="{origin}"{crossorigin_attr}>')

    seen_stylesheet_hrefs: set[str] = set()
    for match in re.finditer(r"<link\b[^>]*>", html_document, flags=re.IGNORECASE):
        raw_tag = match.group(0)
        rel_value = str(_read_html_tag_attribute(raw_tag, "rel") or "").strip().lower()
        href_value = str(_read_html_tag_attribute(raw_tag, "href") or "").strip()
        if rel_value != "stylesheet" or not href_value:
            continue
        parsed = urlsplit(href_value if "://" in href_value else f"https://{href_value}")
        host = parsed.netloc.strip().lower()
        if host not in _EXTERNAL_STYLESHEET_PRELOAD_HOSTS:
            continue
        if has_localized_fontshare and host in _FONTSHARE_STYLESHEET_HOSTS:
            continue
        if has_localized_google_fonts and host in _GOOGLE_FONTS_STYLESHEET_HOSTS:
            continue
        if has_localized_fontawesome and host in _FONTAWESOME_STYLESHEET_HOSTS:
            continue
        normalized_href = href_value
        if normalized_href in seen_stylesheet_hrefs:
            continue
        seen_stylesheet_hrefs.add(normalized_href)
        crossorigin_attr = ' crossorigin="anonymous"' if host == "cdnjs.cloudflare.com" else ""
        blocks.append(
            f'<link rel="preload" as="style" href="{escape(normalized_href, quote=True)}"'
            f'{crossorigin_attr} data-mos-style-preload="true">'
        )
    return "".join(blocks)


def _inject_head_html_block(*, html_document: str, block: str) -> str:
    if not block:
        return html_document
    if block in html_document:
        return html_document
    if "</head>" not in html_document.lower():
        return html_document
    return re.sub(
        r"</head>",
        lambda match: f"{block}{match.group(0)}",
        html_document,
        count=1,
        flags=re.IGNORECASE,
    )


def _extract_html_document_head_inner(html_document: str) -> str | None:
    match = re.search(
        r"<head\b[^>]*>(?P<inner>[\s\S]*?)</head>", html_document, flags=re.IGNORECASE
    )
    if match is None:
        return None
    return str(match.group("inner") or "")


def _extract_html_document_body_opening_tag(html_document: str) -> str | None:
    match = re.search(r"<body\b[^>]*>", html_document, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.group(0)


def _extract_first_html_tag_block(html_document: str, tag_name: str) -> str | None:
    match = re.search(
        rf"<{re.escape(tag_name)}\b[^>]*>[\s\S]*?</{re.escape(tag_name)}>",
        html_document,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return match.group(0)


def _extract_last_html_tag_block(html_document: str, tag_name: str) -> str | None:
    matches = list(
        re.finditer(
            rf"<{re.escape(tag_name)}\b[^>]*>[\s\S]*?</{re.escape(tag_name)}>",
            html_document,
            flags=re.IGNORECASE,
        )
    )
    if not matches:
        return None
    return matches[-1].group(0)


def _strip_html_tags(raw_html: str) -> str:
    normalized = re.sub(r"<[^>]+>", " ", str(raw_html or ""))
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _sanitize_supporting_page_head_html(*, supporting_html_document: str, page_title: str) -> str:
    head_inner = _extract_html_document_head_inner(supporting_html_document)
    if head_inner is None:
        raise ValueError("Supporting imported HTML page must contain a <head> element.")

    sanitized = re.sub(
        r"<title\b[^>]*>[\s\S]*?</title>",
        "",
        head_inner,
        count=1,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"<script\b[^>]*>[\s\S]*?</script>",
        "",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"<link\b[^>]*\bdata-mos-standalone-entry-preload=\"true\"[^>]*>",
        "",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"<link\b[^>]*\brel=(?:\"preload\"|'preload')[^>]*\bas=(?:\"image\"|'image')[^>]*>",
        "",
        sanitized,
        flags=re.IGNORECASE,
    )
    return f"<title>{escape(page_title)}</title>{sanitized}"


def _rewrite_standalone_compliance_navigation_links(
    *,
    html_fragment: str,
    shop_path: str,
    footer_terms: str,
    footer_privacy: str,
    footer_refund: str,
    footer_contact: str,
) -> str:
    shop_target = f"{shop_path}#shop"
    label_targets = {
        "contact": footer_contact,
        "contact us": footer_contact,
        "shop": shop_target,
        "shop now": shop_target,
        "terms": footer_terms,
        "privacy": footer_privacy,
        "refunds": footer_refund,
    }
    href_targets = {
        "contact": footer_contact,
        "contact-us": footer_contact,
        "shop": shop_target,
        "terms": footer_terms,
        "terms-of-service": footer_terms,
        "privacy": footer_privacy,
        "privacy-policy": footer_privacy,
        "refunds": footer_refund,
        "refund-policy": footer_refund,
    }

    def _replace_anchor(match: re.Match[str]) -> str:
        raw_tag = match.group(0)
        href_value = str(_read_html_tag_attribute(raw_tag, "href") or "").strip()
        inner_html = str(match.group("inner") or "")
        label = _strip_html_tags(inner_html).lower()
        replacement_href: str | None = None
        href_path = urlsplit(href_value).path.strip().lower() if href_value else ""
        href_key = href_path.removeprefix("./").strip("/")

        if href_value in {"#shop", "/#shop"}:
            replacement_href = shop_target
        elif href_value in {"#", ""}:
            replacement_href = label_targets.get(label)
        elif href_key and not href_value.startswith("/"):
            replacement_href = href_targets.get(href_key)

        if not replacement_href:
            return raw_tag

        opening_match = re.match(r"<a\b[^>]*>", raw_tag, flags=re.IGNORECASE)
        if opening_match is None:
            return raw_tag
        opening_tag = _set_html_tag_attribute(opening_match.group(0), "href", replacement_href)
        return f"{opening_tag}{inner_html}</a>"

    return re.sub(
        r"<a\b[^>]*>(?P<inner>[\s\S]*?)</a>",
        _replace_anchor,
        html_fragment,
        flags=re.IGNORECASE,
    )


def _normalize_html_image_source_route(raw_src: str) -> str:
    candidate = str(raw_src or "").strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return parsed.path or ""
    return candidate


def _normalize_standalone_static_asset_reference_route(raw_src: str) -> str:
    candidate = str(raw_src or "").strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        path = parsed.path or ""
    else:
        path = parsed.path or candidate
    path = str(path or "").strip()
    if not path:
        return ""
    if path.startswith("./"):
        path = path[1:]
    if not path.startswith("/"):
        path = f"/{path}"
    normalized = posixpath.normpath(path)
    if path.endswith("/") and not normalized.endswith("/"):
        normalized += "/"
    return normalized


def _resolve_responsive_image_sizes_attr(*, viewport_widths: dict[str, int]) -> str | None:
    desktop_width = int(viewport_widths.get("desktop") or 0)
    mobile_width = int(viewport_widths.get("mobile") or 0)
    if desktop_width > 0 and mobile_width > 0 and abs(desktop_width - mobile_width) > 8:
        return f"(min-width: 768px) {desktop_width}px, {mobile_width}px"
    largest_width = max(desktop_width, mobile_width)
    if largest_width > 0:
        return f"{largest_width}px"
    return None


def _resolve_responsive_variant_widths(
    *, original_width: int, viewport_widths: dict[str, int]
) -> tuple[int, ...]:
    if original_width <= 0:
        return ()
    widths: set[int] = set()
    for measured_width in viewport_widths.values():
        normalized_width = max(0, int(measured_width or 0))
        if normalized_width <= 0:
            continue
        for factor in _STANDALONE_IMAGE_VARIANT_FACTORS:
            widths.add(min(original_width, max(1, normalized_width * factor)))
    normalized = tuple(sorted(width for width in widths if width > 0))
    if normalized == (original_width,):
        return ()
    return normalized


def _html_tag_has_aspect_ratio_class(raw_tag: str) -> bool:
    class_value = str(_read_html_tag_attribute(raw_tag, "class") or "").strip()
    if not class_value:
        return False
    class_tokens = [token.strip().lower() for token in class_value.split() if token.strip()]
    return any(token == "aspect-square" or token.startswith("aspect-") for token in class_tokens)


def _html_tag_has_explicit_box_size_classes(raw_tag: str) -> bool:
    class_value = str(_read_html_tag_attribute(raw_tag, "class") or "").strip()
    if not class_value:
        return False
    class_tokens = [token.strip().lower() for token in class_value.split() if token.strip()]
    has_width_class = any(
        token.startswith("w-")
        and not token.startswith("w-fit")
        and not token.startswith("w-auto")
        and not token.startswith("w-full")
        and not token.startswith("w-screen")
        for token in class_tokens
    )
    has_height_class = any(
        token.startswith("h-")
        and not token.startswith("h-fit")
        and not token.startswith("h-auto")
        and not token.startswith("h-full")
        and not token.startswith("h-screen")
        for token in class_tokens
    )
    return has_width_class and has_height_class


def _preferred_fontawesome_subset_source_url(source_url: str) -> str:
    parsed = urlsplit(str(source_url or "").strip())
    host = parsed.netloc.strip().lower()
    path = parsed.path or ""
    if host in _FONTAWESOME_STYLESHEET_HOSTS and path.lower().endswith(".woff2"):
        rewritten_path = re.sub(r"\.woff2$", ".ttf", path, flags=re.IGNORECASE)
        return urlunsplit(
            (parsed.scheme, parsed.netloc, rewritten_path, parsed.query, parsed.fragment)
        )
    return source_url


class ServerDeployer:
    """SSH-based deployer that configures apps without replacing servers."""

    def __init__(
        self,
        ip: str,
        private_key_str: str,
        user: str = "root",
        local_root: Optional[Path] = None,
    ):
        self.ip = ip
        self.user = user
        self.key = paramiko.RSAKey.from_private_key(io.StringIO(private_key_str))
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.local_root = Path(local_root).expanduser().resolve() if local_root else None
        self._sftp_client: Any | None = None
        self._remote_directory_cache: set[str] = {"/"}

    def connect(self):
        self._reset_sftp_client()
        for _ in range(10):
            try:
                self.client.connect(self.ip, username=self.user, pkey=self.key, timeout=10)
                return
            except Exception:
                time.sleep(5)
        raise ConnectionError(f"Could not connect to {self.ip}")

    def _reset_sftp_client(self) -> None:
        existing = getattr(self, "_sftp_client", None)
        if existing is not None:
            try:
                existing.close()
            except Exception:
                pass
        self._sftp_client = None

    def _remote_dir_cache(self) -> set[str]:
        cache = getattr(self, "_remote_directory_cache", None)
        if not isinstance(cache, set):
            cache = {"/"}
            self._remote_directory_cache = cache
        cache.add("/")
        return cache

    def _ensure_transport(self) -> None:
        transport = self.client.get_transport()
        if transport is None or not transport.is_active():
            self.connect()

    def _get_sftp_client(self):
        self._ensure_transport()
        sftp = getattr(self, "_sftp_client", None)
        if sftp is None:
            sftp = self.client.open_sftp()
            self._sftp_client = sftp
        return sftp

    def run(self, cmd: str, cwd: str = None, mask: Optional[List[str]] = None) -> str:
        self._ensure_transport()

        final_cmd = f"cd {cwd} && {cmd}" if cwd else cmd
        display_cmd = final_cmd
        for m in mask or []:
            if m:
                display_cmd = display_cmd.replace(m, "***")
        print(f"[{self.ip}] Running: {display_cmd}")
        stdin, stdout, stderr = self.client.exec_command(final_cmd)
        try:
            stdin.close()
        except Exception:
            pass

        channel = stdout.channel
        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []
        while True:
            while channel.recv_ready():
                out_chunks.append(channel.recv(65536))
            while channel.recv_stderr_ready():
                err_chunks.append(channel.recv_stderr(65536))
            if channel.exit_status_ready():
                break
            time.sleep(0.05)

        exit_code = channel.recv_exit_status()
        while channel.recv_ready():
            out_chunks.append(channel.recv(65536))
        while channel.recv_stderr_ready():
            err_chunks.append(channel.recv_stderr(65536))
        out = b"".join(out_chunks).decode(errors="replace").strip()
        err = b"".join(err_chunks).decode(errors="replace").strip()

        if exit_code != 0:
            raise Exception(f"Command failed: {final_cmd}\nError: {err}")
        return out

    def upload_file(self, content: str, remote_path: str):
        try:
            sftp = self._get_sftp_client()
            self._ensure_remote_parent_directory(sftp=sftp, remote_path=remote_path)
            with sftp.file(remote_path, "w") as f:
                f.write(content)
        except OSError as exc:
            self._reset_sftp_client()
            raise ValueError(f"Failed to upload remote file '{remote_path}': {exc}") from exc

    def upload_bytes(self, content: bytes, remote_path: str):
        try:
            sftp = self._get_sftp_client()
            self._ensure_remote_parent_directory(sftp=sftp, remote_path=remote_path)
            with sftp.file(remote_path, "wb") as f:
                f.write(content)
        except OSError as exc:
            self._reset_sftp_client()
            raise ValueError(f"Failed to upload remote file '{remote_path}': {exc}") from exc

    def _ensure_remote_parent_directory(self, *, sftp: Any, remote_path: str) -> None:
        parent_dir = posixpath.dirname(str(remote_path or "").strip())
        if not parent_dir or parent_dir == "/":
            return

        remote_dir_cache = self._remote_dir_cache()
        if parent_dir in remote_dir_cache:
            return

        pending_dirs: list[str] = []
        current_dir = parent_dir
        while current_dir and current_dir != "/":
            if current_dir in remote_dir_cache:
                break
            try:
                sftp.stat(current_dir)
                remote_dir_cache.add(current_dir)
                break
            except OSError:
                pending_dirs.append(current_dir)
                current_dir = posixpath.dirname(current_dir)
        for missing_dir in reversed(pending_dirs):
            try:
                sftp.mkdir(missing_dir)
            except OSError:
                try:
                    sftp.stat(missing_dir)
                except OSError as exc:
                    raise ValueError(
                        f"Failed to create remote directory '{missing_dir}' for '{remote_path}': {exc}"
                    ) from exc
            remote_dir_cache.add(missing_dir)

    def _upload_local_directory(self, *, local_dir: Path, remote_dir: str) -> None:
        if not local_dir.is_dir():
            raise ValueError(f"Local runtime directory does not exist: {local_dir}")

        self._ensure_transport()

        archive_stream = io.BytesIO()
        with tarfile.open(fileobj=archive_stream, mode="w:gz") as tar:
            for child in sorted(local_dir.rglob("*")):
                if child.is_dir():
                    continue
                if child.name.startswith("."):
                    continue
                if child.suffix == ".map":
                    continue
                tar.add(str(child), arcname=child.relative_to(local_dir).as_posix())
        archive_stream.seek(0)

        remote_archive = f"/tmp/cloudhand-runtime-{int(time.time() * 1000)}.tar.gz"
        sftp = self._get_sftp_client()
        try:
            with sftp.file(remote_archive, "wb") as remote_file:
                remote_file.write(archive_stream.read())
        except OSError as exc:
            self._reset_sftp_client()
            raise ValueError(f"Failed to upload runtime archive '{remote_archive}': {exc}") from exc

        remote_dir_q = shlex.quote(remote_dir)
        remote_archive_q = shlex.quote(remote_archive)
        self.run(f"tar -xzf {remote_archive_q} -C {remote_dir_q}")
        self.run(f"rm -f {remote_archive_q}")

    def _normalize_server_names(self, server_names: Optional[List[str]]) -> List[str]:
        names: List[str] = []
        for name in server_names or []:
            cleaned = (name or "").strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)
        return names

    def _server_name_directive(self, server_names: List[str]) -> str:
        return " ".join(server_names) if server_names else "_"

    def _resolve_local_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            base = self.local_root or Path.cwd()
            path = base / path
        return path.resolve()

    def _resolve_local_workspace_root(self) -> Path:
        if self.local_root is not None:
            return Path(self.local_root).expanduser().resolve()
        return Path(__file__).resolve().parents[4]

    def _resolve_standalone_tailwind_frontend_roots(self) -> list[Path]:
        workspace_root = self._resolve_local_workspace_root()
        candidates: list[Path] = []
        seen: set[Path] = set()

        def add_candidate(path: Path) -> None:
            resolved = path.expanduser().resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            candidates.append(resolved)

        add_candidate(workspace_root / "mos" / "frontend")
        add_candidate(workspace_root / "frontend")

        raw_extra_roots = str(os.getenv("MOS_STANDALONE_TAILWIND_FRONTEND_ROOTS") or "").strip()
        if raw_extra_roots:
            for raw_entry in raw_extra_roots.split(os.pathsep):
                cleaned = str(raw_entry or "").strip()
                if not cleaned:
                    continue
                add_candidate(Path(cleaned))

        for raw_path in (
            "/opt/apps/mos-api/mos/frontend",
            "/opt/apps/mos-ui/mos/frontend",
        ):
            add_candidate(Path(raw_path))

        return candidates

    def _compile_html_deploy_tailwind_css(self, *, html_document: str) -> str | None:
        if not _TAILWIND_CDN_SCRIPT_PATTERN.search(html_document):
            return None

        toolchain_frontend_root: Path | None = None
        tailwind_entry: Path | None = None
        postcss_entry: Path | None = None
        for frontend_root in self._resolve_standalone_tailwind_frontend_roots():
            candidate_tailwind_entry = (
                frontend_root / "node_modules" / "tailwindcss" / "lib" / "index.js"
            )
            candidate_postcss_entry = (
                frontend_root / "node_modules" / "postcss" / "lib" / "postcss.js"
            )
            if candidate_tailwind_entry.is_file() and candidate_postcss_entry.is_file():
                toolchain_frontend_root = frontend_root
                tailwind_entry = candidate_tailwind_entry
                postcss_entry = candidate_postcss_entry
                break
        if toolchain_frontend_root is None or tailwind_entry is None or postcss_entry is None:
            return None

        compile_script = """
import fs from "node:fs";
import vm from "node:vm";
import { pathToFileURL } from "node:url";

const [, , htmlPath, outputPath, postcssPath, tailwindPath] = process.argv;
const html = fs.readFileSync(htmlPath, "utf8");

let resolvedConfig = {};
for (const match of html.matchAll(/<script\\b(?![^>]*\\bsrc=)[^>]*>([\\s\\S]*?)<\\/script>/gi)) {
  const body = String(match[1] || "");
  if (!/tailwind\\s*\\.\\s*config\\s*=/.test(body)) {
    continue;
  }
  const context = { tailwind: {} };
  vm.runInNewContext(body, context, { timeout: 1000 });
  if (context.tailwind && typeof context.tailwind.config === "object" && context.tailwind.config) {
    resolvedConfig = context.tailwind.config;
    break;
  }
}

const postcssModule = await import(pathToFileURL(postcssPath).href);
const tailwindModule = await import(pathToFileURL(tailwindPath).href);
const postcss = postcssModule.default || postcssModule;
const tailwindcss = tailwindModule.default || tailwindModule;
const config = {
  ...resolvedConfig,
  content: [{ raw: html, extension: "html" }],
};
const result = await postcss([tailwindcss(config)]).process(
  "@tailwind base;@tailwind components;@tailwind utilities;",
  { from: undefined },
);
fs.writeFileSync(outputPath, result.css, "utf8");
""".strip()

        try:
            with tempfile.TemporaryDirectory(prefix="mos-standalone-tailwind-") as tmp_dir:
                tmp_path = Path(tmp_dir)
                html_path = tmp_path / "input.html"
                output_path = tmp_path / "output.css"
                script_path = tmp_path / "compile-tailwind.mjs"
                html_path.write_text(html_document, encoding="utf-8")
                script_path.write_text(compile_script, encoding="utf-8")
                completed = subprocess.run(
                    [
                        "node",
                        str(script_path),
                        str(html_path),
                        str(output_path),
                        str(postcss_entry),
                        str(tailwind_entry),
                    ],
                    cwd=str(toolchain_frontend_root),
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=60,
                )
                if completed.returncode != 0 or not output_path.is_file():
                    return None
                compiled_css = output_path.read_text(encoding="utf-8").strip()
                return compiled_css or None
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None

    def _compile_standalone_imported_html_tailwind_css(self, *, html_document: str) -> str | None:
        return self._compile_html_deploy_tailwind_css(html_document=html_document)

    def _replace_html_deploy_tailwind_runtime(self, *, html_document: str) -> str:
        tailwind_match = _TAILWIND_CDN_SCRIPT_PATTERN.search(html_document)
        if tailwind_match is None:
            return html_document

        compiled_css = self._compile_html_deploy_tailwind_css(html_document=html_document)
        if not compiled_css:
            return html_document

        replacement_start = tailwind_match.start()
        replacement_end = tailwind_match.end()
        while True:
            inline_match = _INLINE_SCRIPT_AT_POSITION_PATTERN.match(html_document, replacement_end)
            if inline_match is None:
                break
            inline_body = str(inline_match.group("body") or "")
            if "tailwind.config" not in inline_body:
                break
            replacement_end = inline_match.end()

        safe_css = compiled_css.replace("</style", "<\\/style")
        compiled_style_block = f'<style data-mos-compiled-tailwind="true">{safe_css}</style>'
        html_without_tailwind_runtime = (
            f"{html_document[:replacement_start]}{html_document[replacement_end:]}"
        )

        head_close_index = html_without_tailwind_runtime.lower().rfind("</head>")
        if head_close_index == -1:
            return f"{html_document[:replacement_start]}{compiled_style_block}{html_document[replacement_end:]}"

        return (
            f"{html_without_tailwind_runtime[:head_close_index]}"
            f"{compiled_style_block}"
            f"{html_without_tailwind_runtime[head_close_index:]}"
        )

    def _replace_standalone_imported_html_tailwind_runtime(self, *, html_document: str) -> str:
        return self._replace_html_deploy_tailwind_runtime(html_document=html_document)

    def _fetch_remote_standalone_binary_asset(
        self,
        *,
        url: str,
        context_label: str,
        accept: str = "*/*",
        user_agent: str | None = None,
    ) -> tuple[bytes, str]:
        fetch_url = _normalize_remote_standalone_fetch_url(url)
        request = Request(
            fetch_url,
            headers={
                "User-Agent": str(user_agent or "").strip()
                or "Mozilla/5.0 (compatible; CloudhandStandaloneMirror/1.0)",
                "Accept": accept,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                content_type = _resolve_binary_asset_content_type(
                    source_url=fetch_url,
                    response_content_type=response.headers.get_content_type(),
                )
                payload = response.read()
        except HTTPError as exc:
            raise ValueError(
                f"{context_label} failed to fetch asset '{url}': upstream returned HTTP {exc.code}."
            ) from exc
        except URLError as exc:
            raise ValueError(
                f"{context_label} failed to fetch asset '{url}': {exc.reason}."
            ) from exc
        except TimeoutError as exc:
            raise ValueError(
                f"{context_label} failed to fetch asset '{url}': request timed out."
            ) from exc
        except OSError as exc:
            raise ValueError(f"{context_label} failed to fetch asset '{url}': {exc}.") from exc

        if not payload:
            raise ValueError(
                f"{context_label} failed to fetch asset '{url}': response body was empty."
            )
        return payload, content_type

    def _subset_font_awesome_font_payload(
        self,
        *,
        payload: bytes,
        content_type: str,
        used_codepoints: set[int],
        context_label: str,
        source_url: str,
        output_flavor: str | None = "woff2",
    ) -> tuple[bytes, str]:
        if not used_codepoints:
            raise ValueError(
                f"{context_label} could not determine any Font Awesome codepoints for '{source_url}'."
            )
        try:
            from fontTools.subset import Options, Subsetter
            from fontTools.ttLib import TTFont
        except ImportError as exc:  # pragma: no cover - enforced by package dependency
            raise ValueError(
                f"{context_label} requires the 'fonttools' package to subset Font Awesome assets."
            ) from exc

        try:
            font = TTFont(io.BytesIO(payload), recalcTimestamp=False)
            options = Options()
            options.ignore_missing_glyphs = True
            subsetter = Subsetter(options=options)
            subsetter.populate(unicodes=sorted({int(codepoint) for codepoint in used_codepoints}))
            subsetter.subset(font)
            output = io.BytesIO()
            normalized_flavor = str(output_flavor or "").strip().lower() or None
            font.flavor = normalized_flavor
            font.save(output)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{context_label} failed to subset Font Awesome font '{source_url}': {exc}"
            ) from exc

        subset_payload = output.getvalue()
        if not subset_payload:
            raise ValueError(
                f"{context_label} generated an empty Font Awesome subset for '{source_url}'."
            )
        if normalized_flavor == "woff2":
            return subset_payload, "font/woff2"
        if normalized_flavor == "woff":
            return subset_payload, "font/woff"
        return subset_payload, content_type

    def _subset_text_font_payload(
        self,
        *,
        payload: bytes,
        content_type: str,
        used_codepoints: set[int],
        context_label: str,
        source_url: str,
        output_flavor: str | None = "woff2",
    ) -> tuple[bytes, str]:
        if not used_codepoints:
            raise ValueError(
                f"{context_label} could not determine any used glyphs for '{source_url}'."
            )
        try:
            from fontTools.subset import Options, Subsetter
            from fontTools.ttLib import TTFont
        except ImportError as exc:  # pragma: no cover - enforced by package dependency
            raise ValueError(
                f"{context_label} requires the 'fonttools' package to subset localized font assets."
            ) from exc

        try:
            font = TTFont(io.BytesIO(payload), recalcTimestamp=False)
            options = Options()
            options.ignore_missing_glyphs = True
            subsetter = Subsetter(options=options)
            subsetter.populate(unicodes=sorted({int(codepoint) for codepoint in used_codepoints}))
            subsetter.subset(font)
            output = io.BytesIO()
            normalized_flavor = str(output_flavor or "").strip().lower() or None
            font.flavor = normalized_flavor
            font.save(output)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{context_label} failed to subset localized font '{source_url}': {exc}"
            ) from exc

        subset_payload = output.getvalue()
        if not subset_payload:
            raise ValueError(
                f"{context_label} generated an empty localized font subset for '{source_url}'."
            )
        if normalized_flavor == "woff2":
            return subset_payload, "font/woff2"
        if normalized_flavor == "woff":
            return subset_payload, "font/woff"
        return subset_payload, content_type

    def _build_localized_fontshare_stylesheet(
        self,
        *,
        site_dir: str,
        source_url: str,
        html_document: str,
        context_label: str,
        mirrored_asset_url_cache: dict[str, str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
    ) -> tuple[str, list[tuple[str, str]]]:
        source_host = urlsplit(source_url).netloc.strip().lower()
        stylesheet_user_agent = (
            _STANDALONE_MODERN_BROWSER_USER_AGENT
            if source_host in _GOOGLE_FONTS_STYLESHEET_HOSTS
            else None
        )
        payload, _content_type = self._fetch_remote_standalone_binary_asset(
            url=source_url,
            context_label=context_label,
            accept="text/css,*/*;q=0.1",
            user_agent=stylesheet_user_agent,
        )
        stylesheet_text = _decode_stylesheet_payload(
            payload=payload,
            source_url=source_url,
            context_label=context_label,
        )
        font_face_blocks = _parse_css_font_face_blocks(stylesheet_text)
        if not font_face_blocks:
            return stylesheet_text, []

        used_text_codepoints = _extract_html_text_codepoints(html_document)
        if not used_text_codepoints:
            raise ValueError(
                f"{context_label} could not determine any text glyphs from the imported HTML document."
            )

        localized_font_faces: list[str] = []
        fetched_font_payloads: dict[str, tuple[bytes, str]] = {}
        for font_face in font_face_blocks:
            unicode_range = str(font_face.get("unicode_range") or "").strip()
            block_codepoints = _filter_codepoints_for_unicode_range(
                codepoints=used_text_codepoints,
                unicode_range=unicode_range,
            )
            if not block_codepoints:
                continue

            subset_source_url = urljoin(
                source_url,
                _preferred_font_subset_source_url(list(font_face["urls"])),
            )
            original_font_payload, original_content_type = fetched_font_payloads.get(
                subset_source_url, (b"", "")
            )
            if not original_font_payload:
                original_font_payload, original_content_type = (
                    self._fetch_remote_standalone_binary_asset(
                        url=subset_source_url,
                        context_label=context_label,
                        accept="font/ttf,font/otf,font/woff2,font/woff,*/*;q=0.1",
                    )
                )
                fetched_font_payloads[subset_source_url] = (
                    original_font_payload,
                    original_content_type,
                )

            subset_payload, subset_content_type = self._subset_text_font_payload(
                payload=original_font_payload,
                content_type=original_content_type,
                used_codepoints=block_codepoints,
                context_label=context_label,
                source_url=subset_source_url,
                output_flavor="woff2",
            )
            extension = _resolve_mirrored_binary_extension(
                content_type=subset_content_type,
                source_url=subset_source_url,
            )
            digest_input = (
                subset_payload
                + f":{font_face['family_name']}:{font_face['font_weight']}:{font_face['font_style']}:{unicode_range}".encode(
                    "utf-8"
                )
            )
            route_path = f"{_STANDALONE_FONT_ASSET_ROUTE_PREFIX}/{hashlib.sha256(digest_input).hexdigest()[:32]}{extension}"
            self._write_standalone_route_asset(
                site_dir=site_dir,
                route_path=route_path,
                payload=subset_payload,
                content_type=subset_content_type,
                uploaded_target_paths=mirrored_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
                context_label=context_label,
            )

            if route_path.lower().endswith(".woff2"):
                format_label = "woff2"
            elif route_path.lower().endswith(".woff"):
                format_label = "woff"
            elif route_path.lower().endswith(".ttf"):
                format_label = "truetype"
            elif route_path.lower().endswith(".otf"):
                format_label = "opentype"
            else:
                format_label = "woff2"
            unicode_range_css = f"unicode-range:{unicode_range};" if unicode_range else ""
            localized_font_faces.append(
                "@font-face{"
                f"font-family:'{font_face['family_name']}';"
                f"font-style:{font_face['font_style']};"
                f"font-weight:{font_face['font_weight']};"
                f"font-display:{font_face['font_display']};"
                f"src:url('{route_path}') format('{format_label}');"
                f"{unicode_range_css}"
                "}"
            )

        if not localized_font_faces:
            raise ValueError(
                f"{context_label} could not match any localized font faces to the imported HTML text."
            )

        stylesheet_without_faces = _strip_css_font_face_blocks(stylesheet_text).strip()
        localized_stylesheet = "".join(localized_font_faces)
        if stylesheet_without_faces:
            localized_stylesheet += stylesheet_without_faces
        return localized_stylesheet, []

    def _build_localized_fontawesome_stylesheet(
        self,
        *,
        site_dir: str,
        source_url: str,
        html_document: str,
        context_label: str,
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
    ) -> tuple[str, list[tuple[str, str]]]:
        payload, _content_type = self._fetch_remote_standalone_binary_asset(
            url=source_url,
            context_label=context_label,
            accept="text/css,*/*;q=0.1",
        )
        stylesheet_text = _decode_stylesheet_payload(
            payload=payload,
            source_url=source_url,
            context_label=context_label,
        )
        icon_usage = _extract_fontawesome_icon_usage_from_html(html_document)
        if not icon_usage:
            return "", []

        icon_codepoints = _parse_fontawesome_icon_codepoints(stylesheet_text)
        font_face_blocks = _parse_css_font_face_blocks(stylesheet_text)
        font_face_lookup = {
            (
                str(block["family_name"]).strip(),
                str(block["font_weight"]).strip(),
                str(block["font_style"]).strip(),
            ): block
            for block in font_face_blocks
        }
        preload_specs: list[tuple[str, str]] = []
        localized_font_faces: list[str] = []
        fetched_font_payloads: dict[str, tuple[bytes, str]] = {}

        for family_class, used_icons in icon_usage.items():
            family_spec = _FONTAWESOME_FAMILY_SPECS[family_class]
            lookup_key = (
                str(family_spec["font_family"]),
                str(family_spec["font_weight"]),
                str(family_spec["font_style"]),
            )
            font_face = font_face_lookup.get(lookup_key)
            if font_face is None:
                raise ValueError(
                    f"{context_label} could not find a Font Awesome @font-face block for {lookup_key!r}."
                )
            used_codepoints: set[int] = set()
            missing_icons: list[str] = []
            for icon_class in sorted(used_icons):
                codepoint = icon_codepoints.get(icon_class)
                if codepoint is None:
                    missing_icons.append(icon_class)
                    continue
                used_codepoints.add(int(codepoint))
            if missing_icons:
                raise ValueError(
                    f"{context_label} could not resolve Font Awesome glyph codepoints for: {', '.join(missing_icons)}."
                )

            source_font_url = ""
            for candidate_url in font_face["urls"]:
                absolute_candidate = urljoin(source_url, str(candidate_url))
                if absolute_candidate.lower().endswith(".woff2"):
                    source_font_url = absolute_candidate
                    break
                if not source_font_url:
                    source_font_url = absolute_candidate
            if not source_font_url:
                raise ValueError(
                    f"{context_label} Font Awesome @font-face block for {lookup_key!r} did not expose any font URLs."
                )

            subset_source_url = _preferred_fontawesome_subset_source_url(source_font_url)
            original_font_payload, original_content_type = fetched_font_payloads.get(
                subset_source_url, (b"", "")
            )
            if not original_font_payload:
                original_font_payload, original_content_type = (
                    self._fetch_remote_standalone_binary_asset(
                        url=subset_source_url,
                        context_label=context_label,
                        accept="font/ttf,font/woff2,font/woff,*/*;q=0.1",
                    )
                )
                fetched_font_payloads[subset_source_url] = (
                    original_font_payload,
                    original_content_type,
                )

            subset_payload, subset_content_type = self._subset_font_awesome_font_payload(
                payload=original_font_payload,
                content_type=original_content_type,
                used_codepoints=used_codepoints,
                context_label=context_label,
                source_url=subset_source_url,
                output_flavor="woff2",
            )
            extension = _resolve_mirrored_binary_extension(
                content_type=subset_content_type,
                source_url=subset_source_url,
            )
            digest_input = subset_payload + f":{family_class}".encode("utf-8")
            route_path = f"{_STANDALONE_FONT_ASSET_ROUTE_PREFIX}/{hashlib.sha256(digest_input).hexdigest()[:32]}{extension}"
            self._write_standalone_route_asset(
                site_dir=site_dir,
                route_path=route_path,
                payload=subset_payload,
                content_type=subset_content_type,
                uploaded_target_paths=mirrored_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
                context_label=context_label,
            )
            if family_class == "fa-solid":
                preload_specs.append((route_path, subset_content_type))
            if route_path.lower().endswith(".woff2"):
                format_label = "woff2"
            elif route_path.lower().endswith(".woff"):
                format_label = "woff"
            elif route_path.lower().endswith(".ttf"):
                format_label = "truetype"
            elif route_path.lower().endswith(".otf"):
                format_label = "opentype"
            else:
                format_label = "woff2"
            font_display = str(font_face.get("font_display") or "block").strip()
            localized_font_faces.append(
                "@font-face{"
                f"font-family:'{family_spec['font_family']}';"
                f"font-style:{family_spec['font_style']};"
                f"font-weight:{family_spec['font_weight']};"
                f"font-display:{font_display};"
                f"src:url('{route_path}') format('{format_label}');"
                "}"
            )

        stylesheet_without_faces = _strip_css_font_face_blocks(stylesheet_text).strip()
        localized_stylesheet = "".join(localized_font_faces)
        if stylesheet_without_faces:
            localized_stylesheet += stylesheet_without_faces
        return localized_stylesheet, preload_specs

    def _localize_standalone_imported_html_stylesheets(
        self,
        *,
        site_dir: str,
        html_document: str,
        context_label: str,
        mirrored_asset_url_cache: dict[str, str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
    ) -> str:
        rewritten_document = html_document
        font_preload_blocks: list[str] = []
        seen_preload_routes: set[str] = set()

        for match in list(re.finditer(r"<link\b[^>]*>", html_document, flags=re.IGNORECASE)):
            raw_tag = match.group(0)
            rel_value = str(_read_html_tag_attribute(raw_tag, "rel") or "").strip().lower()
            href_value = str(_read_html_tag_attribute(raw_tag, "href") or "").strip()
            if rel_value != "stylesheet" or not _is_absolute_url_candidate(href_value):
                continue
            parsed = urlsplit(href_value)
            host = parsed.netloc.strip().lower()
            localized_css = ""
            marker_attr = ""
            preload_specs: list[tuple[str, str]] = []
            if host in _FONTSHARE_STYLESHEET_HOSTS:
                localized_css, preload_specs = self._build_localized_fontshare_stylesheet(
                    site_dir=site_dir,
                    source_url=href_value,
                    html_document=rewritten_document,
                    context_label=context_label,
                    mirrored_asset_url_cache=mirrored_asset_url_cache,
                    mirrored_target_paths=mirrored_target_paths,
                    standalone_served_assets=standalone_served_assets,
                    standalone_image_sources=standalone_image_sources,
                )
                marker_attr = ' data-mos-local-fontshare="true"'
            elif host in _GOOGLE_FONTS_STYLESHEET_HOSTS:
                localized_css, preload_specs = self._build_localized_fontshare_stylesheet(
                    site_dir=site_dir,
                    source_url=href_value,
                    html_document=rewritten_document,
                    context_label=context_label,
                    mirrored_asset_url_cache=mirrored_asset_url_cache,
                    mirrored_target_paths=mirrored_target_paths,
                    standalone_served_assets=standalone_served_assets,
                    standalone_image_sources=standalone_image_sources,
                )
                marker_attr = ' data-mos-local-google-fonts="true"'
            elif host in _FONTAWESOME_STYLESHEET_HOSTS and "font-awesome" in parsed.path.lower():
                localized_css, preload_specs = self._build_localized_fontawesome_stylesheet(
                    site_dir=site_dir,
                    source_url=href_value,
                    html_document=rewritten_document,
                    context_label=context_label,
                    mirrored_target_paths=mirrored_target_paths,
                    standalone_served_assets=standalone_served_assets,
                    standalone_image_sources=standalone_image_sources,
                )
                marker_attr = ' data-mos-local-font-awesome="true"'
            else:
                continue

            for route_path, content_type in preload_specs:
                if route_path in seen_preload_routes:
                    continue
                seen_preload_routes.add(route_path)
                font_preload_blocks.append(
                    _build_font_preload_tag(href=route_path, content_type=content_type)
                )

            safe_css = localized_css.replace("</style", "<\\/style")
            style_block = f"<style{marker_attr}>{safe_css}</style>" if localized_css else ""
            rewritten_document = rewritten_document.replace(raw_tag, style_block, 1)

        if font_preload_blocks:
            rewritten_document = _inject_head_html_block(
                html_document=rewritten_document,
                block="".join(font_preload_blocks),
            )
        return rewritten_document

    def _mirror_remote_standalone_binary_asset(
        self,
        *,
        site_dir: str,
        source_url: str,
        route_prefix: str,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        mirrored_target_paths: set[str],
        context_label: str,
        mirrored_asset_url_cache: dict[str, str],
        accept: str = "*/*",
    ) -> tuple[str, str]:
        cached_route = mirrored_asset_url_cache.get(source_url)
        if cached_route is not None:
            asset = standalone_served_assets.get(cached_route)
            if asset is None:
                raise ValueError(
                    f"{context_label} cached mirrored asset route '{cached_route}' for '{source_url}' "
                    "was not present in the standalone served asset map."
                )
            return cached_route, asset.content_type

        payload, content_type = self._fetch_remote_standalone_binary_asset(
            url=source_url,
            context_label=context_label,
            accept=accept,
        )
        extension = _resolve_mirrored_binary_extension(
            content_type=content_type,
            source_url=source_url,
        )
        digest = hashlib.sha256(payload).hexdigest()[:32]
        route_path = f"{route_prefix}/{digest}{extension}"
        target_path = f"{site_dir}{route_path}"
        if target_path not in mirrored_target_paths:
            self.upload_bytes(payload, target_path)
            mirrored_target_paths.add(target_path)
        self._register_standalone_served_asset(
            served_assets=standalone_served_assets,
            route_path=route_path,
            payload=payload,
            content_type=content_type,
            context_label=context_label,
        )
        mirrored_asset_url_cache[source_url] = route_path
        return route_path, content_type

    def _fetch_remote_standalone_image_asset(
        self,
        *,
        url: str,
        context_label: str,
    ) -> tuple[bytes, str]:
        payload, content_type = self._fetch_remote_standalone_binary_asset(
            url=url,
            context_label=context_label,
            accept="image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        )
        content_type = _detect_raster_image_content_type(
            payload=payload,
            hinted_content_type=content_type,
        )
        if not content_type or not str(content_type).strip().lower().startswith("image/"):
            raise ValueError(
                f"{context_label} failed to mirror image asset '{url}': expected image/* content type, got '{content_type or 'unknown'}'."
            )
        return payload, str(content_type).strip().lower()

    def _resolve_local_standalone_image_asset(
        self,
        *,
        asset_url: str,
        context_label: str,
    ) -> tuple[bytes, str, str]:
        normalized_url = str(asset_url or "").strip()
        if not normalized_url:
            raise ValueError(f"{context_label} local image asset URL must be non-empty.")

        parsed = urlsplit(normalized_url)
        relative_path = parsed.path or normalized_url
        normalized_relative_path = relative_path.lstrip("/")
        if not normalized_relative_path:
            raise ValueError(f"{context_label} local image asset URL '{asset_url}' is invalid.")

        for root in _STANDALONE_LOCAL_IMAGE_ASSET_ROOTS:
            candidate_path = root / normalized_relative_path
            if not candidate_path.is_file():
                continue
            payload = candidate_path.read_bytes()
            if not payload:
                raise ValueError(
                    f"{context_label} local image asset '{candidate_path}' resolved from '{asset_url}' is empty."
                )
            content_type = _detect_raster_image_content_type(
                payload=payload,
                hinted_content_type=None,
            )
            if not content_type or not str(content_type).strip().lower().startswith("image/"):
                raise ValueError(
                    f"{context_label} local image asset '{candidate_path}' resolved from '{asset_url}' "
                    f"did not decode as an image."
                )
            extension = _resolve_mirrored_image_extension(
                content_type=str(content_type).strip().lower(),
                source_url=normalized_relative_path,
            )
            digest = hashlib.sha256(payload).hexdigest()[:32]
            route_path = f"{_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}/{digest}{extension}"
            return payload, str(content_type).strip().lower(), route_path

        searched_roots = ", ".join(str(root) for root in _STANDALONE_LOCAL_IMAGE_ASSET_ROOTS)
        raise ValueError(
            f"{context_label} local image asset '{asset_url}' was not found under standalone asset roots: "
            f"{searched_roots}."
        )

    def _mirror_standalone_imported_html_image_assets(
        self,
        *,
        site_dir: str,
        html_document: str,
        skip_hosts: set[str],
        static_asset_route_prefixes: tuple[str, ...] = ("/assets/",),
        mirrored_url_map: dict[str, str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
        context_label: str,
    ) -> str:
        candidate_urls: list[str] = []
        seen_urls: set[str] = set()
        for match in _ABSOLUTE_URL_PATTERN.finditer(html_document):
            candidate_url = match.group(0)
            if candidate_url in seen_urls:
                continue
            if not _is_mirrorable_absolute_image_url(candidate_url, skip_hosts=skip_hosts):
                continue
            seen_urls.add(candidate_url)
            candidate_urls.append(candidate_url)
        for candidate_url in _extract_absolute_image_urls_from_img_tags(
            html_document,
            skip_hosts=skip_hosts,
        ):
            if candidate_url in seen_urls:
                continue
            seen_urls.add(candidate_url)
            candidate_urls.append(candidate_url)
        for candidate_url in _extract_relative_image_urls_from_html_document(html_document):
            if candidate_url in seen_urls:
                continue
            seen_urls.add(candidate_url)
            candidate_urls.append(candidate_url)

        if not candidate_urls:
            return html_document

        mirror_root = f"{site_dir}{_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}"
        self.run(f"mkdir -p {shlex.quote(mirror_root)}")

        rewritten_document = html_document
        for candidate_url in candidate_urls:
            local_url = mirrored_url_map.get(candidate_url)
            if local_url is None:
                if _is_absolute_url_candidate(candidate_url, skip_hosts=skip_hosts):
                    payload, content_type = self._fetch_remote_standalone_image_asset(
                        url=candidate_url,
                        context_label=context_label,
                    )
                    extension = _resolve_mirrored_image_extension(
                        content_type=content_type,
                        source_url=candidate_url,
                    )
                    digest = hashlib.sha256(payload).hexdigest()[:32]
                    local_url = f"{_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}/{digest}{extension}"
                    target_path = f"{site_dir}{local_url}"
                    if target_path not in mirrored_target_paths:
                        self.upload_bytes(payload, target_path)
                        mirrored_target_paths.add(target_path)
                    self._register_standalone_served_asset(
                        served_assets=standalone_served_assets,
                        route_path=local_url,
                        payload=payload,
                        content_type=content_type,
                        context_label=context_label,
                    )
                    self._register_standalone_image_source(
                        image_sources=standalone_image_sources,
                        route_path=local_url,
                        payload=payload,
                        content_type=content_type,
                        context_label=context_label,
                    )
                else:
                    static_asset_route = _normalize_standalone_static_asset_reference_route(
                        candidate_url
                    )
                    served_static_asset_route = next(
                        (
                            candidate_route
                            for candidate_route in _candidate_standalone_static_asset_routes(
                                static_asset_route,
                                asset_route_prefixes=static_asset_route_prefixes,
                            )
                            if candidate_route in standalone_served_assets
                        ),
                        "",
                    )
                    if served_static_asset_route:
                        local_url = served_static_asset_route
                    else:
                        payload, content_type, local_url = (
                            self._resolve_local_standalone_image_asset(
                                asset_url=candidate_url,
                                context_label=context_label,
                            )
                        )
                        self._write_standalone_route_asset(
                            site_dir=site_dir,
                            route_path=local_url,
                            payload=payload,
                            content_type=content_type,
                            uploaded_target_paths=mirrored_target_paths,
                            standalone_served_assets=standalone_served_assets,
                            standalone_image_sources=standalone_image_sources,
                            context_label=context_label,
                        )
                mirrored_url_map[candidate_url] = local_url
            rewritten_document = rewritten_document.replace(candidate_url, local_url)

        return rewritten_document

    def _register_standalone_served_asset(
        self,
        *,
        served_assets: dict[str, _StandaloneServedAsset],
        route_path: str,
        payload: bytes,
        content_type: str,
        context_label: str,
    ) -> None:
        normalized_route_path = str(route_path or "").strip()
        if not normalized_route_path.startswith("/"):
            raise ValueError(f"{context_label} asset route '{route_path}' must start with '/'.")
        existing = served_assets.get(normalized_route_path)
        if existing is not None and (
            existing.content != payload or existing.content_type != content_type
        ):
            raise ValueError(
                f"{context_label} attempted to register conflicting standalone asset bytes for '{normalized_route_path}'."
            )
        served_assets[normalized_route_path] = _StandaloneServedAsset(
            content=payload,
            content_type=content_type,
        )

    def _build_standalone_image_source(
        self,
        *,
        route_path: str,
        payload: bytes,
        content_type: str,
        context_label: str,
    ) -> _StandaloneImageSource | None:
        normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
        if normalized_content_type and not normalized_content_type.startswith("image/"):
            return None
        if normalized_content_type == "image/svg+xml":
            return None

        from PIL import Image, ImageOps

        try:
            with Image.open(io.BytesIO(payload)) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
                width, height = image.size
                image_format = str(source.format or "").strip().upper()
                is_animated = bool(
                    getattr(source, "is_animated", False) or getattr(source, "n_frames", 1) > 1
                )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{context_label} failed to inspect image bytes for '{route_path}': {exc}"
            ) from exc

        if width <= 0 or height <= 0:
            raise ValueError(
                f"{context_label} image '{route_path}' resolved to invalid dimensions ({width}x{height})."
            )
        if is_animated:
            return None
        normalized_content_type = _RASTER_IMAGE_FORMAT_CONTENT_TYPE_MAP.get(
            image_format, normalized_content_type
        )
        if normalized_content_type not in _RESPONSIVE_VARIANT_CONTENT_TYPES:
            return None
        if image_format not in {"JPEG", "PNG", "WEBP"}:
            return None
        return _StandaloneImageSource(
            route_path=route_path,
            content=payload,
            content_type=normalized_content_type,
            width=width,
            height=height,
            image_format=image_format,
        )

    def _register_standalone_image_source(
        self,
        *,
        image_sources: dict[str, _StandaloneImageSource],
        route_path: str,
        payload: bytes,
        content_type: str,
        context_label: str,
    ) -> None:
        image_source = self._build_standalone_image_source(
            route_path=route_path,
            payload=payload,
            content_type=content_type,
            context_label=context_label,
        )
        if image_source is None:
            return
        existing = image_sources.get(route_path)
        if existing is not None and existing.content != image_source.content:
            raise ValueError(
                f"{context_label} attempted to register conflicting standalone image source bytes for '{route_path}'."
            )
        image_sources[route_path] = image_source

    def _is_standalone_image_candidate_quality_acceptable(
        self,
        *,
        image_source: _StandaloneImageSource,
        candidate_payload: bytes,
        candidate_content_type: str,
        context_label: str,
        page_stage: str | None = None,
        target_width: int | None = None,
    ) -> bool:
        if not _is_presales_stage(page_stage):
            return True

        from PIL import Image, ImageOps

        try:
            with Image.open(io.BytesIO(image_source.content)) as reference_source:
                reference_source.load()
                reference_image = ImageOps.exif_transpose(reference_source)
            with Image.open(io.BytesIO(candidate_payload)) as candidate_source:
                candidate_source.load()
                candidate_image = ImageOps.exif_transpose(candidate_source)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{context_label} failed to inspect a presales candidate image for '{image_source.route_path}': {exc}"
            ) from exc

        effective_target_width = max(0, int(target_width or 0))
        if effective_target_width > 0:
            if reference_image.width != effective_target_width:
                reference_height = max(
                    1,
                    int(
                        round(
                            reference_image.height
                            * (effective_target_width / float(reference_image.width))
                        )
                    ),
                )
                reference_image = reference_image.resize(
                    (effective_target_width, reference_height),
                    Image.Resampling.LANCZOS,
                )
            if candidate_image.width != effective_target_width:
                candidate_height = max(
                    1,
                    int(
                        round(
                            candidate_image.height
                            * (effective_target_width / float(candidate_image.width))
                        )
                    ),
                )
                candidate_image = candidate_image.resize(
                    (effective_target_width, candidate_height),
                    Image.Resampling.LANCZOS,
                )

        if reference_image.size != candidate_image.size:
            return False

        min_psnr_db = (
            _STANDALONE_PRESALES_MIN_RESPONSIVE_PSNR_DB
            if effective_target_width > 0 and effective_target_width < image_source.width
            else _STANDALONE_PRESALES_MIN_PSNR_DB
        )
        psnr_db = _calculate_image_psnr_db(
            reference_image=reference_image, candidate_image=candidate_image
        )
        if not math.isfinite(psnr_db):
            return True
        return psnr_db >= min_psnr_db

    def _generate_standalone_image_variant_payload(
        self,
        *,
        image_source: _StandaloneImageSource,
        target_width: int,
        context_label: str,
        preferred_output_format: str | None = None,
        quality: int | None = None,
    ) -> tuple[bytes, str]:
        if target_width <= 0:
            raise ValueError(f"{context_label} responsive variant width must be greater than zero.")
        if target_width >= image_source.width:
            return image_source.content, image_source.content_type

        from PIL import Image, ImageOps

        target_height = max(
            1, int(round(image_source.height * (target_width / float(image_source.width))))
        )
        try:
            with Image.open(io.BytesIO(image_source.content)) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
                image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                output_format = (
                    str(preferred_output_format or image_source.image_format or "").strip().upper()
                )
                if output_format == "JPEG":
                    if image.mode not in {"RGB", "L"}:
                        image = image.convert("RGB")
                    image.save(
                        output,
                        format="JPEG",
                        quality=max(1, min(100, int(quality or 100))),
                        subsampling=0,
                        optimize=True,
                        progressive=True,
                    )
                    encoded_content_type = "image/jpeg"
                elif output_format == "PNG":
                    if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA"}:
                        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    image.save(output, format="PNG", optimize=True, compress_level=9)
                    encoded_content_type = "image/png"
                elif output_format == "WEBP":
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    image.save(
                        output,
                        format="WEBP",
                        quality=max(1, min(100, int(quality or 100))),
                        method=6,
                    )
                    encoded_content_type = "image/webp"
                else:
                    raise ValueError(
                        f"{context_label} does not support responsive variants for image format '{output_format or image_source.image_format}'."
                    )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{context_label} failed to generate responsive variant for '{image_source.route_path}' at width {target_width}: {exc}"
            ) from exc

        payload = output.getvalue()
        if not payload:
            raise ValueError(
                f"{context_label} generated an empty responsive variant for '{image_source.route_path}' at width {target_width}."
            )
        return payload, encoded_content_type

    def _generate_standalone_image_compression_candidates(
        self,
        *,
        image_source: _StandaloneImageSource,
        context_label: str,
        page_stage: str | None = None,
    ) -> list[tuple[bytes, str, str]]:
        if len(image_source.content) < _STANDALONE_COMPRESSED_IMAGE_MIN_BYTES:
            return []

        from PIL import Image, ImageOps

        try:
            with Image.open(io.BytesIO(image_source.content)) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
                image.load()
                normalized_format = str(image_source.image_format or "").strip().upper()
                candidates: list[tuple[bytes, str, str]] = []
                seen_digests: set[str] = set()

                def _append_candidate(payload: bytes, content_type: str, label: str) -> None:
                    if not payload:
                        return
                    if not _has_meaningful_compression_savings(
                        original_bytes=len(image_source.content),
                        candidate_bytes=len(payload),
                    ):
                        return
                    digest = hashlib.sha256(payload).hexdigest()
                    if digest in seen_digests:
                        return
                    seen_digests.add(digest)
                    candidates.append((payload, content_type, label))

                presales_profile = _is_presales_stage(page_stage)

                if normalized_format == "PNG":
                    output = io.BytesIO()
                    image.save(output, format="PNG", optimize=True, compress_level=9)
                    _append_candidate(output.getvalue(), "image/png", "png-opt")

                    output = io.BytesIO()
                    if image.mode not in {"RGB", "RGBA"}:
                        image_for_webp = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    else:
                        image_for_webp = image
                    image_for_webp.save(output, format="WEBP", lossless=True, method=6)
                    _append_candidate(output.getvalue(), "image/webp", "webp-lossless")
                    if presales_profile:
                        for quality in _STANDALONE_PRESALES_PNG_WEBP_COMPRESSION_QUALITIES:
                            output = io.BytesIO()
                            image_for_webp.save(
                                output,
                                format="WEBP",
                                quality=quality,
                                method=6,
                            )
                            _append_candidate(output.getvalue(), "image/webp", f"webp-q{quality}")
                elif normalized_format == "JPEG":
                    image_for_jpeg = (
                        image.convert("RGB") if image.mode not in {"RGB", "L"} else image
                    )
                    jpeg_qualities = (
                        _STANDALONE_PRESALES_JPEG_COMPRESSION_QUALITIES
                        if presales_profile
                        else _STANDALONE_DEFAULT_JPEG_COMPRESSION_QUALITIES
                    )
                    for quality in jpeg_qualities:
                        output = io.BytesIO()
                        image_for_jpeg.save(
                            output,
                            format="JPEG",
                            quality=quality,
                            subsampling=0,
                            optimize=True,
                            progressive=True,
                        )
                        _append_candidate(output.getvalue(), "image/jpeg", f"jpeg-q{quality}")
                    image_for_webp = (
                        image.convert("RGB") if image.mode not in {"RGB", "RGBA"} else image
                    )
                    webp_qualities = (
                        _STANDALONE_PRESALES_WEBP_COMPRESSION_QUALITIES
                        if presales_profile
                        else _STANDALONE_DEFAULT_WEBP_COMPRESSION_QUALITIES
                    )
                    for quality in webp_qualities:
                        output = io.BytesIO()
                        image_for_webp.save(
                            output,
                            format="WEBP",
                            quality=quality,
                            method=6,
                        )
                        _append_candidate(output.getvalue(), "image/webp", f"webp-q{quality}")
                elif normalized_format == "WEBP":
                    image_for_webp = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    if presales_profile:
                        webp_qualities = _STANDALONE_PRESALES_WEBP_COMPRESSION_QUALITIES
                    else:
                        webp_qualities = _STANDALONE_DEFAULT_WEBP_COMPRESSION_QUALITIES
                        output = io.BytesIO()
                        image_for_webp.save(output, format="WEBP", lossless=True, method=6)
                        _append_candidate(output.getvalue(), "image/webp", "webp-lossless")
                    for quality in webp_qualities:
                        output = io.BytesIO()
                        image_for_webp.save(
                            output,
                            format="WEBP",
                            quality=quality,
                            method=6,
                        )
                        _append_candidate(output.getvalue(), "image/webp", f"webp-q{quality}")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{context_label} failed to generate compressed image candidates for '{image_source.route_path}': {exc}"
            ) from exc

        if _is_presales_stage(page_stage):
            candidates.sort(key=lambda item: len(item[0]))
        return candidates

    def _write_standalone_route_asset(
        self,
        *,
        site_dir: str,
        route_path: str,
        payload: bytes,
        content_type: str,
        uploaded_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
        context_label: str,
    ) -> None:
        target_path = f"{site_dir}{route_path}"
        if target_path not in uploaded_target_paths:
            self.upload_bytes(payload, target_path)
            uploaded_target_paths.add(target_path)
        self._register_standalone_served_asset(
            served_assets=standalone_served_assets,
            route_path=route_path,
            payload=payload,
            content_type=content_type,
            context_label=context_label,
        )
        self._register_standalone_image_source(
            image_sources=standalone_image_sources,
            route_path=route_path,
            payload=payload,
            content_type=content_type,
            context_label=context_label,
        )

    def _standardize_html_deploy_product_favicons(
        self,
        *,
        site_dir: str,
        product_slug: str,
        html_document: str,
        uploaded_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
        context_label: str,
    ) -> str:
        if product_slug != _TENOR_PRODUCT_SLUG:
            return html_document
        if "</head>" not in html_document.lower():
            raise ValueError(
                f"{context_label} cannot standardize the Tenor favicon because the document is missing </head>."
            )

        for asset in _TENOR_PRODUCT_FAVICON_ASSETS:
            self._write_standalone_route_asset(
                site_dir=site_dir,
                route_path=str(asset["routePath"]),
                payload=bytes(asset["payload"]),
                content_type=str(asset["contentType"]),
                uploaded_target_paths=uploaded_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
                context_label=f"{context_label} Tenor product favicon",
            )

        without_page_favicons = _strip_html_favicon_link_tags(html_document)
        return _inject_head_html_block(
            html_document=without_page_favicons,
            block=_tenor_product_favicon_head_block(),
        )

    @contextmanager
    def _serve_standalone_html_validation_site(
        self,
        *,
        before_html: str,
        after_html: str | None,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
    ) -> Iterator[str]:
        import http.server

        before_bytes = before_html.encode("utf-8")
        after_bytes = after_html.encode("utf-8") if after_html is not None else None
        served_assets = dict(standalone_served_assets)

        class _Handler(http.server.BaseHTTPRequestHandler):
            def _write_response(
                self, *, status: int, content_type: str, payload: bytes = b""
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD" and payload:
                    self.wfile.write(payload)

            def _handle_html(self) -> bool:
                path = urlsplit(self.path).path
                if path in {"/__mos_before__", "/__mos_before__/", "/__mos_before__/index.html"}:
                    self._write_response(
                        status=200, content_type="text/html; charset=utf-8", payload=before_bytes
                    )
                    return True
                if after_bytes is not None and path in {
                    "/__mos_after__",
                    "/__mos_after__/",
                    "/__mos_after__/index.html",
                }:
                    self._write_response(
                        status=200, content_type="text/html; charset=utf-8", payload=after_bytes
                    )
                    return True
                return False

            def do_GET(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                if self._handle_html():
                    return
                if path.startswith("/api/"):
                    payload = b"{}"
                    self._write_response(
                        status=200, content_type="application/json; charset=utf-8", payload=payload
                    )
                    return
                asset = served_assets.get(path)
                if asset is not None:
                    self._write_response(
                        status=200, content_type=asset.content_type, payload=asset.content
                    )
                    return
                if path == "/favicon.ico":
                    self._write_response(status=204, content_type="image/x-icon")
                    return
                self._write_response(
                    status=404, content_type="text/plain; charset=utf-8", payload=b"Not found"
                )

            def do_HEAD(self) -> None:  # noqa: N802
                self.do_GET()

            def do_POST(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                if path.startswith("/api/"):
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    if length > 0:
                        self.rfile.read(length)
                    self._write_response(
                        status=200, content_type="application/json; charset=utf-8", payload=b"{}"
                    )
                    return
                self._write_response(
                    status=404, content_type="text/plain; charset=utf-8", payload=b"Not found"
                )

            def log_message(self, _format: str, *_args: object) -> None:
                return

        class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        server = _ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def _measure_html_deploy_image_layouts(
        self,
        *,
        html_document: str,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        context_label: str,
    ) -> dict[int, dict[str, int]]:
        from playwright.sync_api import sync_playwright

        measurements: dict[int, dict[str, int]] = {}
        with self._serve_standalone_html_validation_site(
            before_html=html_document,
            after_html=None,
            standalone_served_assets=standalone_served_assets,
        ) as base_url:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    for viewport_label, viewport in _STANDALONE_IMAGE_LAYOUT_VIEWPORTS:
                        context = browser.new_context(
                            viewport={"width": viewport["width"], "height": viewport["height"]},
                            device_scale_factor=viewport["device_scale_factor"],
                            is_mobile=viewport["is_mobile"],
                        )
                        try:
                            page = context.new_page()
                            page.goto(
                                f"{base_url}/__mos_before__/",
                                wait_until="domcontentloaded",
                                timeout=30_000,
                            )
                            page.evaluate(
                                "document.fonts ? document.fonts.ready.then(() => true) : true"
                            )
                            page.wait_for_timeout(500)
                            raw_measurements = page.evaluate("""
() => Array.from(document.querySelectorAll("img")).map((img, index) => {
  const rect = img.getBoundingClientRect();
  return {
    index,
    renderedWidth: Math.round(rect.width || 0),
  };
})
""")
                        finally:
                            context.close()

                        if not isinstance(raw_measurements, list):
                            raise ValueError(
                                f"{context_label} image layout measurement returned an invalid payload for viewport '{viewport_label}'."
                            )
                        for entry in raw_measurements:
                            if not isinstance(entry, dict):
                                continue
                            image_index = int(entry.get("index") or 0)
                            rendered_width = max(0, int(entry.get("renderedWidth") or 0))
                            measurements.setdefault(image_index, {})[
                                viewport_label
                            ] = rendered_width
                finally:
                    browser.close()
        return measurements

    def _measure_standalone_imported_html_image_layouts(
        self,
        *,
        html_document: str,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        context_label: str,
    ) -> dict[int, dict[str, int]]:
        return self._measure_html_deploy_image_layouts(
            html_document=html_document,
            standalone_served_assets=standalone_served_assets,
            context_label=context_label,
        )

    def _validate_html_deploy_visual_parity(
        self,
        *,
        before_html: str,
        after_html: str,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        context_label: str,
    ) -> None:
        from PIL import Image, ImageChops
        from playwright.sync_api import sync_playwright

        with self._serve_standalone_html_validation_site(
            before_html=before_html,
            after_html=after_html,
            standalone_served_assets=standalone_served_assets,
        ) as base_url:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    for viewport_label, viewport in _STANDALONE_IMAGE_LAYOUT_VIEWPORTS:
                        context = browser.new_context(
                            viewport={"width": viewport["width"], "height": viewport["height"]},
                            device_scale_factor=viewport["device_scale_factor"],
                            is_mobile=viewport["is_mobile"],
                        )
                        try:
                            before_page = context.new_page()
                            before_page.goto(
                                f"{base_url}/__mos_before__/",
                                wait_until="domcontentloaded",
                                timeout=30_000,
                            )
                            before_page.evaluate(
                                "document.fonts ? document.fonts.ready.then(() => true) : true"
                            )
                            before_page.wait_for_timeout(750)
                            before_bytes = before_page.screenshot(full_page=True, type="png")

                            after_page = context.new_page()
                            after_page.goto(
                                f"{base_url}/__mos_after__/",
                                wait_until="domcontentloaded",
                                timeout=30_000,
                            )
                            after_page.evaluate(
                                "document.fonts ? document.fonts.ready.then(() => true) : true"
                            )
                            after_page.wait_for_timeout(750)
                            after_bytes = after_page.screenshot(full_page=True, type="png")
                        finally:
                            context.close()

                        with (
                            Image.open(io.BytesIO(before_bytes)) as before_image,
                            Image.open(io.BytesIO(after_bytes)) as after_image,
                        ):
                            before_rgba = before_image.convert("RGBA")
                            after_rgba = after_image.convert("RGBA")
                            if before_rgba.size != after_rgba.size:
                                width_delta = abs(before_rgba.size[0] - after_rgba.size[0])
                                height_delta = abs(before_rgba.size[1] - after_rgba.size[1])
                                if (
                                    width_delta > 0
                                    or height_delta > _STANDALONE_PARITY_MAX_HEIGHT_DELTA_PX
                                ):
                                    raise ValueError(
                                        f"{context_label} visual parity failed for viewport '{viewport_label}': "
                                        f"rendered dimensions changed from {before_rgba.size} to {after_rgba.size}."
                                    )
                                min_width = min(before_rgba.size[0], after_rgba.size[0])
                                min_height = min(before_rgba.size[1], after_rgba.size[1])
                                before_rgba = before_rgba.crop((0, 0, min_width, min_height))
                                after_rgba = after_rgba.crop((0, 0, min_width, min_height))
                            diff = ImageChops.difference(before_rgba, after_rgba)
                            changed_pixels = 0
                            total_pixels = max(1, before_rgba.size[0] * before_rgba.size[1])
                            for pixel in diff.getdata():
                                if max(pixel) > _STANDALONE_PARITY_DIFF_CHANNEL_THRESHOLD:
                                    changed_pixels += 1
                            changed_percent = (changed_pixels / float(total_pixels)) * 100.0
                            if changed_percent > _STANDALONE_PARITY_MAX_CHANGED_PERCENT:
                                raise ValueError(
                                    f"{context_label} visual parity failed for viewport '{viewport_label}': "
                                    f"{changed_percent:.3f}% of pixels changed "
                                    f"(allowed <= {_STANDALONE_PARITY_MAX_CHANGED_PERCENT:.3f}%)."
                                )
                finally:
                    browser.close()

    def _validate_standalone_imported_html_visual_parity(
        self,
        *,
        before_html: str,
        after_html: str,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        context_label: str,
    ) -> None:
        self._validate_html_deploy_visual_parity(
            before_html=before_html,
            after_html=after_html,
            standalone_served_assets=standalone_served_assets,
            context_label=context_label,
        )

    def _rewrite_standalone_imported_html_compressed_images(
        self,
        *,
        site_dir: str,
        html_document: str,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
        uploaded_target_paths: set[str],
        context_label: str,
        page_stage: str | None = None,
    ) -> str:
        if str(site_dir or "").startswith("/tmp/mos-standalone-preflight"):
            return html_document
        if not standalone_image_sources or _STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES <= 0:
            return html_document

        route_usages: dict[str, list[int]] = {}
        for image_index, match in enumerate(
            re.finditer(r"<img\b[^>]*>", html_document, flags=re.IGNORECASE)
        ):
            raw_tag = match.group(0)
            raw_src = str(_read_html_tag_attribute(raw_tag, "src") or "").strip()
            if not raw_src or raw_src.lower().startswith("data:image/"):
                continue
            normalized_route = _normalize_html_image_source_route(raw_src)
            image_source = standalone_image_sources.get(normalized_route)
            if image_source is None:
                continue
            if len(image_source.content) < _STANDALONE_COMPRESSED_IMAGE_MIN_BYTES:
                continue
            route_usages.setdefault(normalized_route, []).append(image_index)

        if not route_usages:
            return html_document

        route_plans = sorted(
            (
                {
                    "route": route_path,
                    "indices": tuple(image_indices),
                    "benefit_score": len(standalone_image_sources[route_path].content)
                    * max(1, len(image_indices)),
                }
                for route_path, image_indices in route_usages.items()
                if route_path in standalone_image_sources
            ),
            key=lambda plan: int(plan["benefit_score"]),
            reverse=True,
        )[:_STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES]

        compressed_route_cache: dict[tuple[str, str], str] = {}
        rewritten_document = html_document

        for route_plan in route_plans:
            image_indices = tuple(int(index) for index in route_plan["indices"])
            current_route = ""
            for image_index in image_indices:
                current_tag = _find_nth_img_tag(rewritten_document, image_index)
                if current_tag is None:
                    continue
                current_src = str(_read_html_tag_attribute(current_tag, "src") or "").strip()
                current_route = _normalize_html_image_source_route(current_src)
                if current_route:
                    break
            if not current_route:
                continue
            image_source = standalone_image_sources.get(current_route)
            if image_source is None:
                continue
            try:
                compression_candidates = self._generate_standalone_image_compression_candidates(
                    image_source=image_source,
                    context_label=context_label,
                    page_stage=page_stage,
                )
            except ValueError:
                continue
            if not compression_candidates:
                continue

            accepted = False
            for payload, content_type, label in compression_candidates:
                try:
                    quality_ok = self._is_standalone_image_candidate_quality_acceptable(
                        image_source=image_source,
                        candidate_payload=payload,
                        candidate_content_type=content_type,
                        context_label=context_label,
                        page_stage=page_stage,
                    )
                except ValueError:
                    continue
                if not quality_ok:
                    continue
                cache_key = (current_route, label)
                compressed_route = compressed_route_cache.get(cache_key)
                if compressed_route is None:
                    extension = _resolve_mirrored_image_extension(
                        content_type=content_type,
                        source_url=image_source.route_path,
                    )
                    digest_input = payload + f":{label}:{current_route}:{content_type}".encode(
                        "utf-8"
                    )
                    compressed_route = (
                        f"{_STANDALONE_COMPRESSED_IMAGE_ROUTE_PREFIX}/"
                        f"{hashlib.sha256(digest_input).hexdigest()[:32]}-{label}{extension}"
                    )
                    self._write_standalone_route_asset(
                        site_dir=site_dir,
                        route_path=compressed_route,
                        payload=payload,
                        content_type=content_type,
                        uploaded_target_paths=uploaded_target_paths,
                        standalone_served_assets=standalone_served_assets,
                        standalone_image_sources=standalone_image_sources,
                        context_label=context_label,
                    )
                    compressed_route_cache[cache_key] = compressed_route

                trial_document = rewritten_document
                for image_index in image_indices:
                    current_tag = _find_nth_img_tag(trial_document, image_index)
                    if current_tag is None:
                        continue
                    current_src = str(_read_html_tag_attribute(current_tag, "src") or "").strip()
                    if _normalize_html_image_source_route(current_src) != current_route:
                        continue
                    candidate_tag = _set_html_tag_attribute(current_tag, "src", compressed_route)
                    trial_document = _replace_nth_img_tag(
                        trial_document, image_index, candidate_tag
                    )
                if trial_document == rewritten_document:
                    continue
                rewritten_document = trial_document
                accepted = True
                break

            if not accepted:
                continue

        if rewritten_document == html_document and not compressed_route_cache:
            return html_document
        referenced_routes = {
            route_path
            for route_path in compressed_route_cache.values()
            if route_path in rewritten_document
        }
        for route_path in set(compressed_route_cache.values()) - referenced_routes:
            standalone_served_assets.pop(route_path, None)
            standalone_image_sources.pop(route_path, None)
            target_path = f"{site_dir}{route_path}"
            if target_path in uploaded_target_paths:
                self.run(f"rm -f {shlex.quote(target_path)}")
                uploaded_target_paths.discard(target_path)
        return rewritten_document

    def _rewrite_standalone_imported_html_responsive_images(
        self,
        *,
        site_dir: str,
        html_document: str,
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
        uploaded_target_paths: set[str],
        context_label: str,
        page_stage: str | None = None,
    ) -> str:
        if str(site_dir or "").startswith("/tmp/mos-standalone-preflight"):
            return html_document
        if not standalone_image_sources or (
            _STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES <= 0
            and _STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES <= 0
        ):
            return html_document

        image_layouts = self._measure_html_deploy_image_layouts(
            html_document=html_document,
            standalone_served_assets=standalone_served_assets,
            context_label=context_label,
        )
        minimum_width_delta = (
            _STANDALONE_PRESALES_MIN_RESPONSIVE_SOURCE_WIDTH_DELTA
            if _is_presales_stage(page_stage)
            else _STANDALONE_MIN_RESPONSIVE_SOURCE_WIDTH_DELTA
        )
        variant_route_cache: dict[tuple[str, int], str] = {}
        route_usages: dict[str, dict[str, Any]] = {}
        image_plans: list[dict[str, Any]] = []

        def _target_height_for_width(
            *, image_source: _StandaloneImageSource, target_width: int
        ) -> int:
            return max(
                1, int(round(image_source.height * (target_width / float(image_source.width))))
            )

        def _route_variant_route(
            *,
            image_source: _StandaloneImageSource,
            target_width: int,
            variant_kind: str,
        ) -> str:
            use_presales_webp = _is_presales_stage(page_stage) and image_source.image_format in {
                "JPEG",
                "PNG",
                "WEBP",
            }
            preferred_output_format = "WEBP" if use_presales_webp else None
            preferred_quality = (
                _STANDALONE_PRESALES_RESPONSIVE_WEBP_QUALITY if use_presales_webp else None
            )
            cache_key = (
                f"{variant_kind}:{image_source.route_path}:{preferred_output_format or image_source.image_format}:{preferred_quality or 'default'}",
                target_width,
            )
            cached_route = variant_route_cache.get(cache_key)
            if cached_route is not None:
                return cached_route

            payload, content_type = self._generate_standalone_image_variant_payload(
                image_source=image_source,
                target_width=target_width,
                context_label=context_label,
                preferred_output_format=preferred_output_format,
                quality=preferred_quality,
            )
            if not self._is_standalone_image_candidate_quality_acceptable(
                image_source=image_source,
                candidate_payload=payload,
                candidate_content_type=content_type,
                context_label=context_label,
                page_stage=page_stage,
                target_width=target_width,
            ):
                raise ValueError(
                    f"{context_label} rejected responsive variant for '{image_source.route_path}' at width {target_width} "
                    "because the compressed image quality fell below the presales threshold."
                )
            extension = _resolve_mirrored_image_extension(
                content_type=content_type,
                source_url=image_source.route_path,
            )
            digest_input = (
                image_source.content
                + f":{variant_kind}:{target_width}:{content_type}".encode("utf-8")
            )
            digest = hashlib.sha256(digest_input).hexdigest()[:32]
            variant_route = f"{_STANDALONE_RESPONSIVE_VARIANT_ROUTE_PREFIX}/{digest}-{variant_kind}-w{target_width}{extension}"
            self._write_standalone_route_asset(
                site_dir=site_dir,
                route_path=variant_route,
                payload=payload,
                content_type=content_type,
                uploaded_target_paths=uploaded_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
                context_label=context_label,
            )
            variant_route_cache[cache_key] = variant_route
            return variant_route

        def _build_rewritten_route_tag(
            *,
            raw_tag: str,
            image_source: _StandaloneImageSource,
            target_width: int,
            variant_route: str,
        ) -> str:
            rewritten_tag = _set_html_tag_attribute(raw_tag, "src", variant_route)
            if not (
                _html_tag_has_aspect_ratio_class(raw_tag)
                or _html_tag_has_explicit_box_size_classes(raw_tag)
            ):
                rewritten_tag = _set_html_tag_attribute(rewritten_tag, "width", str(target_width))
                rewritten_tag = _set_html_tag_attribute(
                    rewritten_tag,
                    "height",
                    str(
                        _target_height_for_width(
                            image_source=image_source, target_width=target_width
                        )
                    ),
                )
            return rewritten_tag

        def _build_rewritten_tag(
            *,
            raw_tag: str,
            image_index: int,
            image_source: _StandaloneImageSource,
            viewport_widths: dict[str, int],
        ) -> str:
            raw_src = str(_read_html_tag_attribute(raw_tag, "src") or "").strip()
            if not raw_src or raw_src.lower().startswith("data:image/"):
                return raw_tag
            sizes_attr = _resolve_responsive_image_sizes_attr(viewport_widths=viewport_widths)
            variant_widths = _resolve_responsive_variant_widths(
                original_width=image_source.width,
                viewport_widths=viewport_widths,
            )

            rewritten_tag = raw_tag
            if not (
                _html_tag_has_aspect_ratio_class(raw_tag)
                or _html_tag_has_explicit_box_size_classes(raw_tag)
            ):
                rewritten_tag = _set_html_tag_attribute(
                    rewritten_tag, "width", str(image_source.width)
                )
                rewritten_tag = _set_html_tag_attribute(
                    rewritten_tag, "height", str(image_source.height)
                )
            if sizes_attr:
                rewritten_tag = _set_html_tag_attribute(rewritten_tag, "sizes", sizes_attr)

            if not variant_widths:
                return rewritten_tag

            srcset_entries: list[str] = []
            selected_src = image_source.route_path
            for target_width in variant_widths:
                if target_width >= image_source.width:
                    variant_route = image_source.route_path
                else:
                    try:
                        variant_route = _route_variant_route(
                            image_source=image_source,
                            target_width=target_width,
                            variant_kind="responsive",
                        )
                    except ValueError:
                        continue
                srcset_entries.append(f"{variant_route} {target_width}w")
                selected_src = variant_route

            if not srcset_entries:
                return raw_tag
            rewritten_tag = _set_html_tag_attribute(rewritten_tag, "src", selected_src)
            rewritten_tag = _set_html_tag_attribute(
                rewritten_tag, "srcset", ", ".join(srcset_entries)
            )
            return rewritten_tag

        for image_index, match in enumerate(
            re.finditer(r"<img\b[^>]*>", html_document, flags=re.IGNORECASE)
        ):
            raw_tag = match.group(0)
            raw_src = str(_read_html_tag_attribute(raw_tag, "src") or "").strip()
            if not raw_src or raw_src.lower().startswith("data:image/"):
                continue
            normalized_route = _normalize_html_image_source_route(raw_src)
            image_source = standalone_image_sources.get(normalized_route)
            if image_source is None:
                if normalized_route in standalone_served_assets:
                    continue
                raise ValueError(
                    f"{context_label} could not resolve source bytes for image '{raw_src}'. "
                    "Standalone responsive export requires every <img> source to be present in the artifact asset set "
                    "or mirrorable from its original URL."
                )
            viewport_widths = image_layouts.get(image_index, {})
            route_usage = route_usages.setdefault(
                normalized_route,
                {
                    "indices": [],
                    "max_measured_width": 0,
                },
            )
            route_usage["indices"].append(image_index)
            route_usage["max_measured_width"] = max(
                int(route_usage["max_measured_width"]),
                max((int(width or 0) for width in viewport_widths.values()), default=0),
            )
            variant_widths = _resolve_responsive_variant_widths(
                original_width=image_source.width,
                viewport_widths=viewport_widths,
            )
            max_variant_width = max(variant_widths or (0,))
            max_measured_width = max(
                (int(width or 0) for width in viewport_widths.values()), default=0
            )
            image_bytes = len(image_source.content)
            tiny_rendered_image = max_measured_width < 96
            tiny_source_image = image_source.width < 256
            if (
                not variant_widths
                or (
                    tiny_rendered_image
                    and image_bytes < _STANDALONE_TINY_IMAGE_RESPONSIVE_MIN_BYTES
                )
                or (tiny_source_image and image_bytes < _STANDALONE_TINY_IMAGE_RESPONSIVE_MIN_BYTES)
                or len(image_source.content) < 8 * 1024
                or (image_source.width - max_variant_width) < minimum_width_delta
            ):
                continue
            candidate_tag = _build_rewritten_tag(
                raw_tag=raw_tag,
                image_index=image_index,
                image_source=image_source,
                viewport_widths=viewport_widths,
            )
            if candidate_tag == raw_tag:
                continue
            benefit_score = max(1, image_source.width - max_variant_width) * max(
                1, len(image_source.content)
            )
            image_plans.append(
                {
                    "image_index": image_index,
                    "route": normalized_route,
                    "viewport_widths": viewport_widths,
                    "benefit_score": benefit_score,
                }
            )

        image_plans.sort(key=lambda plan: int(plan["benefit_score"]), reverse=True)
        rewritten_document = html_document
        route_plans: list[dict[str, Any]] = []
        for route_path, usage in route_usages.items():
            image_source = standalone_image_sources.get(route_path)
            if image_source is None:
                continue
            max_measured_width = int(usage["max_measured_width"] or 0)
            if max_measured_width <= 0 or max_measured_width > 96:
                continue
            image_bytes = len(image_source.content)
            if image_bytes < _STANDALONE_TINY_IMAGE_RESPONSIVE_MIN_BYTES:
                continue
            target_width = min(image_source.width, max(96, max_measured_width * 2))
            if (image_source.width - target_width) < minimum_width_delta:
                continue
            route_plans.append(
                {
                    "route": route_path,
                    "indices": tuple(int(index) for index in usage["indices"]),
                    "target_width": target_width,
                    "benefit_score": image_bytes
                    * max(1, image_source.width - target_width)
                    * max(1, len(usage["indices"])),
                }
            )
        route_plans.sort(key=lambda plan: int(plan["benefit_score"]), reverse=True)
        route_plans = route_plans[:_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES]
        for route_plan in route_plans:
            route_path = str(route_plan["route"])
            image_source = standalone_image_sources.get(route_path)
            if image_source is None:
                continue
            target_width = int(route_plan["target_width"])
            try:
                variant_route = _route_variant_route(
                    image_source=image_source,
                    target_width=target_width,
                    variant_kind="tiny",
                )
            except ValueError:
                continue
            trial_document = rewritten_document
            for image_index in route_plan["indices"]:
                current_tag = _find_nth_img_tag(trial_document, int(image_index))
                if current_tag is None:
                    continue
                current_src = str(_read_html_tag_attribute(current_tag, "src") or "").strip()
                if _normalize_html_image_source_route(current_src) != route_path:
                    continue
                candidate_tag = _build_rewritten_route_tag(
                    raw_tag=current_tag,
                    image_source=image_source,
                    target_width=target_width,
                    variant_route=variant_route,
                )
                if candidate_tag == current_tag:
                    continue
                trial_document = _replace_nth_img_tag(
                    trial_document,
                    int(image_index),
                    candidate_tag,
                )
            if trial_document == rewritten_document:
                continue
            rewritten_document = trial_document

        image_plans = image_plans[:_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES]
        for image_plan in image_plans:
            image_index = int(image_plan["image_index"])
            current_tag = _find_nth_img_tag(rewritten_document, image_index)
            if current_tag is None:
                continue
            raw_src = str(_read_html_tag_attribute(current_tag, "src") or "").strip()
            if not raw_src:
                continue
            normalized_route = _normalize_html_image_source_route(raw_src)
            image_source = standalone_image_sources.get(normalized_route)
            if image_source is None:
                continue
            candidate_tag = _build_rewritten_tag(
                raw_tag=current_tag,
                image_index=image_index,
                image_source=image_source,
                viewport_widths=dict(image_plan["viewport_widths"]),
            )
            if candidate_tag == current_tag:
                continue
            trial_document = _replace_nth_img_tag(
                rewritten_document,
                image_index,
                candidate_tag,
            )
            rewritten_document = trial_document
        if rewritten_document == html_document and not variant_route_cache:
            return html_document
        referenced_variant_routes = {
            route_path
            for route_path in variant_route_cache.values()
            if route_path in rewritten_document
        }
        for route_path in set(variant_route_cache.values()) - referenced_variant_routes:
            standalone_served_assets.pop(route_path, None)
            standalone_image_sources.pop(route_path, None)
            target_path = f"{site_dir}{route_path}"
            if target_path in uploaded_target_paths:
                self.run(f"rm -f {shlex.quote(target_path)}")
                uploaded_target_paths.discard(target_path)
        return rewritten_document

    def _env_lines_from_map(self, env_map: Dict[str, str]) -> List[str]:
        lines: List[str] = []
        for key, value in env_map.items():
            if value is None:
                continue
            lines.append(f"{key}={str(value).strip()}")
        return lines

    def _upload_env_content(self, content: str, remote_path: str) -> None:
        remote_dir = os.path.dirname(remote_path)
        if remote_dir:
            self.run(f"mkdir -p {remote_dir}")
        self.upload_file(content, remote_path)
        self.run(f"chmod 600 {remote_path}")

    def _write_env_file(self, app: ApplicationSpec, path: Optional[str] = None) -> Optional[str]:
        lines = self._env_lines_from_map(app.service_config.environment)
        if not lines:
            return None

        target = path or f"/etc/cloudhand/env/{app.name}.env"
        self._upload_env_content("\n".join(lines) + "\n", target)
        return target

    def _parse_env_file_path(self, raw_path: str, app_dir: str) -> Optional[tuple[str, bool]]:
        cleaned = (raw_path or "").strip()
        if not cleaned:
            return None
        optional = cleaned.startswith("-")
        if optional:
            cleaned = cleaned[1:]
        if cleaned.startswith("/"):
            resolved = cleaned
        else:
            resolved = f"{app_dir}/{cleaned}"
        return resolved, optional

    def _resolve_env_file(self, raw_path: str, app_dir: str) -> Optional[str]:
        parsed = self._parse_env_file_path(raw_path, app_dir)
        if not parsed:
            return None
        resolved, optional = parsed
        return f"-{resolved}" if optional else resolved

    def _env_file_directives(self, app: ApplicationSpec, app_dir: str) -> str:
        env_files: List[str] = []
        env_map_consumed = False

        if app.service_config.environment_file_upload:
            local_path = self._resolve_local_path(app.service_config.environment_file_upload)
            if not local_path.exists():
                raise FileNotFoundError(f"Environment file not found at {local_path}")
            content = _normalize_uploaded_env_content(
                content=local_path.read_text(encoding="utf-8"),
                source_label=str(local_path),
            )

            extra_lines = self._env_lines_from_map(app.service_config.environment)
            if extra_lines:
                content += "\n".join(extra_lines) + "\n"
                env_map_consumed = True

            target_raw = app.service_config.environment_file or f"/etc/cloudhand/env/{app.name}.env"
            parsed = self._parse_env_file_path(target_raw, app_dir)
            if not parsed:
                raise ValueError("environment_file_upload set but no target path resolved")
            target_path, optional = parsed
            self._upload_env_content(content, target_path)
            env_files.append(f"-{target_path}" if optional else target_path)
        elif app.service_config.environment_file:
            resolved = self._resolve_env_file(app.service_config.environment_file, app_dir)
            if resolved:
                env_files.append(resolved)

        if app.service_config.environment and not env_map_consumed:
            generated = self._write_env_file(app)
            if generated:
                env_files.append(generated)

        if not env_files:
            return ""

        return "\n".join(f"EnvironmentFile={path}" for path in env_files)

    def _configure_systemd(self, app: ApplicationSpec, app_dir: str):
        env_str = self._env_file_directives(app, app_dir)
        unit = f"""[Unit]
Description={app.name}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={app_dir}
ExecStart={app.service_config.command}
Restart=always
{env_str}

[Install]
WantedBy=multi-user.target
"""
        self.upload_file(unit, f"/etc/systemd/system/{app.name}.service")
        self.run("systemctl daemon-reload")
        self.run(f"systemctl enable {app.name}")
        self.run(f"systemctl restart {app.name}")

    def _disable_service_unit(self, service_name: str) -> None:
        service_unit = f"{service_name}.service"
        safe_service_unit = shlex.quote(service_unit)
        service_exists = self._service_unit_exists(service_name)
        if service_exists:
            self.run(f"systemctl stop {safe_service_unit}")
            self.run(f"systemctl disable {safe_service_unit}")

        unit_removed = self._remove_path_if_exists(f"/etc/systemd/system/{service_unit}")
        if service_exists or unit_removed:
            self.run("systemctl daemon-reload")

    def _run_bash_lc(self, script: str) -> str:
        return self.run("bash -lc " + shlex.quote(script))

    def _service_unit_exists(self, service_name: str) -> bool:
        safe_service_unit = shlex.quote(f"{service_name}.service")
        out = self._run_bash_lc(
            f"systemctl cat {safe_service_unit} >/dev/null 2>&1 && echo yes || true"
        )
        return out.strip() == "yes"

    def _path_exists(self, path: str) -> bool:
        safe_path = shlex.quote(path)
        out = self._run_bash_lc(f"test -e {safe_path} && echo yes || true")
        return out.strip() == "yes"

    def _remove_path_if_exists(self, path: str, *, recursive: bool = False) -> bool:
        if not self._path_exists(path):
            return False
        safe_path = shlex.quote(path)
        if recursive:
            self.run(f"rm -rf {safe_path}")
        else:
            self.run(f"rm -f {safe_path}")
        return True

    def _run_local_command(self, args: List[str], *, cwd: Path) -> None:
        try:
            proc = subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ValueError(
                f"Required local command is unavailable: '{args[0]}'. Install it on the MOS API host."
            ) from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = stderr or stdout or "no output"
            raise ValueError(f"Local command failed: {' '.join(args)} (cwd={cwd})\n{detail}")

    def _hash_local_directory(self, local_dir: Path) -> str:
        hasher = hashlib.sha256()
        for path in sorted(local_dir.rglob("*")):
            if path.is_dir():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix == ".map":
                continue
            rel = path.relative_to(local_dir).as_posix()
            hasher.update(rel.encode("utf-8"))
            with path.open("rb") as file:
                while True:
                    chunk = file.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def _find_local_repo_root(self) -> Optional[Path]:
        candidates: List[Path] = []
        if self.local_root:
            candidates.append(self.local_root.resolve())
        candidates.append(Path.cwd().resolve())
        candidates.append(Path(__file__).resolve())

        seen: set[Path] = set()
        for start in candidates:
            for candidate in [start, *start.parents]:
                if candidate in seen:
                    continue
                seen.add(candidate)
                if (candidate / "mos" / "frontend" / "package.json").is_file():
                    return candidate
        return None

    def _iter_local_runtime_source_files(self, frontend_dir: Path) -> Iterator[Path]:
        excluded_dir_names = {
            ".git",
            ".yarn",
            "coverage",
            "dist",
            "node_modules",
            "playwright-report",
            "test-results",
        }

        for root, dirnames, filenames in os.walk(frontend_dir):
            dirnames[:] = [name for name in dirnames if name not in excluded_dir_names]
            for filename in filenames:
                if filename == ".DS_Store":
                    continue
                yield Path(root) / filename

    def _latest_local_file_mtime(self, files: Iterator[Path]) -> float:
        latest_mtime = 0.0
        for path in files:
            try:
                if not path.is_file():
                    continue
                latest_mtime = max(latest_mtime, path.stat().st_mtime)
            except FileNotFoundError:
                continue
        return latest_mtime

    def _local_runtime_dist_needs_rebuild(self, *, frontend_dir: Path, dist_dir: Path) -> bool:
        if not dist_dir.is_dir():
            return True

        latest_dist_mtime = self._latest_local_file_mtime(dist_dir.rglob("*"))
        if latest_dist_mtime <= 0:
            return True

        latest_source_mtime = self._latest_local_file_mtime(
            self._iter_local_runtime_source_files(frontend_dir)
        )
        return latest_source_mtime > latest_dist_mtime

    def _ensure_local_runtime_dist(self, runtime_dist_path: str) -> Path | None:
        raw_path = Path(runtime_dist_path)
        dist_candidates: List[Path] = []
        if raw_path.is_absolute():
            dist_candidates.append(raw_path)
        else:
            dist_candidates.append(self._resolve_local_path(runtime_dist_path))
            repo_root = self._find_local_repo_root()
            if repo_root is not None:
                dist_candidates.append((repo_root / runtime_dist_path).resolve())

        unique_dist_candidates: List[Path] = []
        seen: set[Path] = set()
        for candidate in dist_candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique_dist_candidates.append(resolved)

        frontend_candidates: List[Path] = []
        for candidate in unique_dist_candidates:
            if candidate.name == "dist" and (candidate.parent / "package.json").is_file():
                if candidate.parent not in frontend_candidates:
                    frontend_candidates.append(candidate.parent)

        repo_root = self._find_local_repo_root()
        if repo_root:
            repo_frontend = (repo_root / "mos" / "frontend").resolve()
            if (
                repo_frontend / "package.json"
            ).is_file() and repo_frontend not in frontend_candidates:
                frontend_candidates.append(repo_frontend)

        existing_dist = next(
            (candidate for candidate in unique_dist_candidates if candidate.is_dir()), None
        )
        if existing_dist is not None:
            frontend_dir: Path | None = None
            if existing_dist.name == "dist" and (existing_dist.parent / "package.json").is_file():
                frontend_dir = existing_dist.parent
            elif len(frontend_candidates) == 1:
                frontend_dir = frontend_candidates[0]

            if frontend_dir is None or not self._local_runtime_dist_needs_rebuild(
                frontend_dir=frontend_dir,
                dist_dir=existing_dist,
            ):
                return existing_dist

            print(f"[{self.ip}] Local runtime dist stale; rebuilding frontend in {frontend_dir}")
            self._run_local_command(["npm", "ci"], cwd=frontend_dir)
            self._run_local_command(["npm", "run", "build"], cwd=frontend_dir)
            return existing_dist

        if not frontend_candidates:
            return None

        frontend_dir = frontend_candidates[0]
        print(f"[{self.ip}] Local runtime dist missing; building frontend in {frontend_dir}")
        self._run_local_command(["npm", "ci"], cwd=frontend_dir)
        self._run_local_command(["npm", "run", "build"], cwd=frontend_dir)

        for candidate in unique_dist_candidates:
            if candidate.is_dir():
                return candidate

        fallback_dist = frontend_dir / "dist"
        if fallback_dist.is_dir():
            return fallback_dist

        raise ValueError(
            "Frontend build completed but no dist directory was produced for "
            f"runtime_dist_path={runtime_dist_path!r}."
        )

    def _port_is_listening(self, port: int) -> bool:
        out = self.run(f"bash -lc \"ss -ltnH '( sport = :{port} )' | head -n 1 || true\"")
        return bool(out.strip())

    def _assert_ports_available(self, app: ApplicationSpec):
        for port in sorted(set(app.service_config.ports)):
            if not self._port_is_listening(port):
                continue
            if self._service_unit_exists(app.name):
                # Allow rolling restarts for an existing managed workload on the same port.
                continue
            raise ValueError(
                f"Port {port} is already in use on server {self.ip}; cannot deploy workload '{app.name}'."
            )

    def _enable_https(self, server_names: List[str]):
        names = self._normalize_server_names(server_names)
        if not names:
            print(
                f"[{self.ip}] HTTPS requested but no server_names configured; skipping certificate setup."
            )
            return

        domain_args = " ".join(f"-d {name}" for name in names)
        cert_cmd = self.run("command -v certbox || command -v certbot || true").strip()
        if not cert_cmd:
            self.run(
                "DEBIAN_FRONTEND=noninteractive apt-get update && "
                "DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx"
            )
            cert_cmd = "certbot"

        cmd_name = os.path.basename(cert_cmd)
        if cmd_name == "certbot":
            email = os.getenv("CERTBOT_EMAIL") or os.getenv("LETSENCRYPT_EMAIL") or ""
            email_flag = f"--email {email}" if email else "--register-unsafely-without-email"
            self.run(
                f"{cert_cmd} --nginx {domain_args} --non-interactive --agree-tos {email_flag} --redirect"
            )
        else:
            # Assume certbox is certbot-compatible.
            self.run(
                f"{cert_cmd} --nginx {domain_args} --non-interactive --agree-tos --redirect "
                "--register-unsafely-without-email"
            )

    def _ensure_nginx(self):
        # Ensure nginx exists (Hetzner cloud-init installs it in our Terraform, but be defensive)
        nginx_bin = self.run("command -v nginx || true").strip()
        if not nginx_bin:
            self.run(
                "DEBIAN_FRONTEND=noninteractive apt-get update && "
                "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx"
            )

        self.run("mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled")
        self.run("systemctl enable nginx || true")
        self.run("systemctl start nginx || true")

    def _configure_funnel_publication_proxy(self, app: ApplicationSpec):
        source = app.source_ref
        if source is None:
            raise ValueError("source_ref is required when source_type='funnel_publication'.")
        if not isinstance(source, FunnelPublicationSourceSpec):
            raise ValueError(
                "source_ref must be FunnelPublicationSourceSpec when source_type='funnel_publication'."
            )

        server_names = self._normalize_server_names(app.service_config.server_names)
        server_name_line = self._server_name_directive(server_names)
        if server_names:
            listen_port = 80
        else:
            ports = list(app.service_config.ports or [])
            if not ports:
                raise ValueError(
                    "service_config.ports must include one port for source_type='funnel_publication' "
                    "when server_names is empty."
                )
            listen_port = int(ports[0])

        public_id = source.public_id
        upstream_base_url = source.upstream_base_url.rstrip("/")
        upstream_api_base_url = source.upstream_api_base_url.rstrip("/")

        conf = f"""server {{
    listen {listen_port};
    server_name {server_name_line};
    client_max_body_size 25m;
    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};
    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};
    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};

    location = / {{
        return 302 /f/{public_id}$is_args$args;
    }}

    location = /f/{public_id} {{
        proxy_pass {upstream_base_url}/f/{public_id};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Accept-Encoding "";
        sub_filter_once off;
        sub_filter_types text/html text/css application/javascript text/javascript application/json;
        sub_filter '{upstream_api_base_url}' '/api';
    }}

    location ^~ /f/{public_id}/ {{
        proxy_pass {upstream_base_url};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Accept-Encoding "";
        sub_filter_once off;
        sub_filter_types text/html text/css application/javascript text/javascript application/json;
        sub_filter '{upstream_api_base_url}' '/api';
    }}

    location ^~ /api/ {{
        proxy_pass {upstream_api_base_url}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location ^~ /assets/ {{
        proxy_pass {upstream_base_url}/assets/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Accept-Encoding "";
        sub_filter_once off;
        sub_filter_types text/css application/javascript text/javascript application/json;
        sub_filter '{upstream_api_base_url}' '/api';
    }}

    location = /favicon.ico {{
        proxy_pass {upstream_base_url}/favicon.ico;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location / {{
        return 302 /f/{public_id}$request_uri;
    }}
}}"""
        self.upload_file(conf, f"/etc/nginx/sites-available/{app.name}")
        self.run(
            f"ln -sf /etc/nginx/sites-available/{app.name} /etc/nginx/sites-enabled/{app.name}"
        )
        self.run("rm -f /etc/nginx/sites-enabled/default")
        self.run("systemctl reload nginx")
        if app.service_config.https:
            self._enable_https(server_names)

    def _replace_api_base_tokens(self, *, site_dir: str, upstream_api_base_root: str) -> None:
        if not upstream_api_base_root:
            return
        if not upstream_api_base_root.startswith(("http://", "https://")):
            raise ValueError("upstream_api_base_root must start with http:// or https://.")

        script = (
            "import pathlib\n"
            f"SITE = pathlib.Path({site_dir!r})\n"
            f"FROM = {upstream_api_base_root!r}\n"
            "TO = '/api'\n"
            "if not SITE.exists():\n"
            "    raise SystemExit(0)\n"
            "for path in SITE.rglob('*'):\n"
            "    if not path.is_file():\n"
            "        continue\n"
            "    if path.suffix.lower() not in {'.js', '.css', '.html', '.json'}:\n"
            "        continue\n"
            "    try:\n"
            "        raw = path.read_text(encoding='utf-8')\n"
            "    except Exception:\n"
            "        continue\n"
            "    replaced = raw.replace(FROM, TO)\n"
            "    if replaced != raw:\n"
            "        path.write_text(replaced, encoding='utf-8')\n"
        )
        self.run(f"python3 -c {shlex.quote(script)}")

    def _iter_puck_components(self, node: object):
        if isinstance(node, dict):
            node_type = node.get("type")
            props = node.get("props")
            if isinstance(node_type, str) and isinstance(props, dict):
                yield node_type, props
            for value in node.values():
                yield from self._iter_puck_components(value)
            return
        if isinstance(node, list):
            for item in node:
                yield from self._iter_puck_components(item)

    def _normalize_uuid_token(self, *, raw_value: object, context_label: str) -> str:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"{context_label} must be a non-empty UUID string.")
        cleaned = raw_value.strip().lower()
        try:
            return str(UUID(cleaned))
        except ValueError as exc:
            raise ValueError(f"{context_label} '{cleaned}' is not a valid UUID.") from exc

    def _resolve_component_config(
        self,
        *,
        component_type: str,
        props: Dict[str, Any],
        context_label: str,
    ) -> Optional[dict[str, object]]:
        raw_config = props.get("config")
        if isinstance(raw_config, dict):
            return raw_config

        raw_config_json = props.get("configJson")
        if raw_config_json is None:
            return None
        if not isinstance(raw_config_json, str):
            raise ValueError(
                f"{context_label} component '{component_type}' configJson must be a string when provided."
            )
        trimmed = raw_config_json.strip()
        if not trimmed:
            return None
        try:
            parsed = json.loads(trimmed)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{context_label} component '{component_type}' configJson must be valid JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                f"{context_label} component '{component_type}' configJson must decode to a JSON object."
            )
        return parsed

    def _extract_presales_entry_asset_public_id(
        self,
        *,
        config: Dict[str, Any],
        context_label: str,
    ) -> Optional[str]:
        hero = config.get("hero")
        if not isinstance(hero, dict):
            return None
        media = hero.get("media")
        if not isinstance(media, dict):
            return None
        raw_asset_public_id = media.get("assetPublicId")
        if raw_asset_public_id is None:
            return None
        return self._normalize_uuid_token(
            raw_value=raw_asset_public_id,
            context_label=f"{context_label} hero.media.assetPublicId",
        )

    def _extract_sales_entry_asset_public_id(
        self,
        *,
        config: Dict[str, Any],
        context_label: str,
    ) -> Optional[str]:
        hero_config = config
        nested_hero = config.get("hero")
        if isinstance(nested_hero, dict):
            hero_config = nested_hero
        gallery = hero_config.get("gallery")
        if not isinstance(gallery, dict):
            return None
        slides = gallery.get("slides")
        if not isinstance(slides, list) or not slides:
            return None
        first_slide = slides[0]
        if not isinstance(first_slide, dict):
            raise ValueError(f"{context_label} hero.gallery.slides[0] must be an object.")
        raw_asset_public_id = first_slide.get("assetPublicId")
        if raw_asset_public_id is None:
            return None
        return self._normalize_uuid_token(
            raw_value=raw_asset_public_id,
            context_label=f"{context_label} hero.gallery.slides[0].assetPublicId",
        )

    def _resolve_entry_preload_asset_public_id(
        self, *, page_payload: Dict[str, Any], context_label: str
    ) -> Optional[str]:
        puck_data = page_payload.get("puckData")
        if not isinstance(puck_data, dict):
            raise ValueError(f"{context_label} puckData must be an object.")

        for component_type, props in self._iter_puck_components(puck_data):
            if component_type not in _ENTRY_PRELOAD_COMPONENT_TYPES:
                continue
            resolved_config = self._resolve_component_config(
                component_type=component_type,
                props=props,
                context_label=context_label,
            )
            if not resolved_config:
                continue

            if component_type in {"PreSalesHero", "PreSalesTemplate"}:
                pre_sales_asset_public_id = self._extract_presales_entry_asset_public_id(
                    config=resolved_config,
                    context_label=context_label,
                )
                if pre_sales_asset_public_id:
                    return pre_sales_asset_public_id

            if component_type in {"SalesPdpHero", "SalesPdpTemplate"}:
                sales_asset_public_id = self._extract_sales_entry_asset_public_id(
                    config=resolved_config,
                    context_label=context_label,
                )
                if sales_asset_public_id:
                    return sales_asset_public_id

        return None

    def _resolve_funnel_path_tokens(
        self,
        *,
        product_slug: str,
        funnel_slug: str,
        funnel_meta: Dict[str, Any],
    ) -> list[str]:
        funnel_path_tokens = [funnel_slug]
        funnel_id_token = str(funnel_meta.get("funnelId") or "").strip()
        if funnel_id_token:
            if "/" in funnel_id_token or "\\" in funnel_id_token:
                raise ValueError(
                    f"Invalid artifact funnelId '{funnel_id_token}' for '{product_slug}/{funnel_slug}'."
                )
            if funnel_id_token != funnel_slug:
                funnel_path_tokens.append(funnel_id_token)
            try:
                short_funnel_id_token = str(UUID(funnel_id_token)).split("-", 1)[0]
            except ValueError:
                short_funnel_id_token = ""
            if short_funnel_id_token and short_funnel_id_token not in funnel_path_tokens:
                funnel_path_tokens.append(short_funnel_id_token)
        return funnel_path_tokens

    def _resolve_funnel_path_tokens_for_source(
        self,
        *,
        source: FunnelArtifactSourceSpec,
        product_slug: str,
        funnel_slug: str,
        funnel_meta: Dict[str, Any],
    ) -> list[str]:
        funnel_path_tokens = self._resolve_funnel_path_tokens(
            product_slug=product_slug,
            funnel_slug=funnel_slug,
            funnel_meta=funnel_meta,
        )
        funnel_id_token = str(funnel_meta.get("funnelId") or "").strip().lower()
        publication_id_token = str(funnel_meta.get("publicationId") or "").strip().lower()
        short_funnel_id_token = ""
        try:
            short_funnel_id_token = str(UUID(funnel_id_token)).split("-", 1)[0]
        except ValueError:
            short_funnel_id_token = ""
        funnel_match_tokens = {
            str(funnel_slug or "").strip().lower(),
            str(funnel_meta.get("funnelSlug") or "").strip().lower(),
            funnel_id_token,
            short_funnel_id_token,
        }
        funnel_match_tokens.discard("")

        for alias_spec in _html_deploy_funnel_path_alias_specs(source=source):
            alias_product_slug = str(alias_spec.get("productSlug") or "").strip().lower()
            if alias_product_slug and alias_product_slug != str(product_slug).strip().lower():
                continue
            alias_funnel_slug = str(alias_spec.get("funnelSlug") or "").strip().lower()
            if alias_funnel_slug and alias_funnel_slug not in funnel_match_tokens:
                continue
            alias_funnel_id = str(alias_spec.get("funnelId") or "").strip().lower()
            if alias_funnel_id and alias_funnel_id not in {funnel_id_token, short_funnel_id_token}:
                continue
            alias_publication_id = str(alias_spec.get("publicationId") or "").strip().lower()
            if alias_publication_id and alias_publication_id != publication_id_token:
                continue
            alias = str(alias_spec.get("alias") or "").strip().lower()
            if alias and alias not in funnel_path_tokens:
                funnel_path_tokens.append(alias)

        return funnel_path_tokens

    def _canonical_funnel_artifact_page_slug(self, raw_slug: object) -> str:
        normalized_slug = str(raw_slug or "").strip().lower()
        if normalized_slug == "pre-sales":
            return "presales"
        return normalized_slug

    def _canonicalize_funnel_artifact_meta(self, *, funnel_meta: Dict[str, Any]) -> Dict[str, Any]:
        canonical_meta = dict(funnel_meta)
        canonical_entry_slug = self._canonical_funnel_artifact_page_slug(
            canonical_meta.get("entrySlug")
        )
        if canonical_entry_slug:
            canonical_meta["entrySlug"] = canonical_entry_slug

        pages = canonical_meta.get("pages")
        if isinstance(pages, list):
            canonical_pages: list[Dict[str, Any]] = []
            for raw_page in pages:
                if not isinstance(raw_page, dict):
                    raise ValueError("Artifact funnel meta.pages entries must be objects.")
                canonical_page = dict(raw_page)
                canonical_page_slug = self._canonical_funnel_artifact_page_slug(
                    canonical_page.get("slug")
                )
                if canonical_page_slug:
                    canonical_page["slug"] = canonical_page_slug
                canonical_pages.append(canonical_page)
            canonical_meta["pages"] = canonical_pages

        return canonical_meta

    def _canonicalize_funnel_artifact_page_payload(
        self,
        *,
        page_slug: str,
        page_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        canonical_payload = dict(page_payload)
        canonical_slug = self._canonical_funnel_artifact_page_slug(page_slug)
        if canonical_slug:
            canonical_payload["slug"] = canonical_slug

        page_map = canonical_payload.get("pageMap")
        if isinstance(page_map, dict):
            canonical_payload["pageMap"] = {
                str(page_id): self._canonical_funnel_artifact_page_slug(slug_value)
                for page_id, slug_value in page_map.items()
            }

        return canonical_payload

    def _resolve_funnel_artifact_default_page_slug(
        self,
        *,
        funnel_meta: Dict[str, Any],
        funnel_payload: Dict[str, Any],
        default_route_policy: str = "entry_page",
        default_page_slug: str | None = None,
    ) -> str:
        entry_slug = self._canonical_funnel_artifact_page_slug(funnel_meta.get("entrySlug"))
        if not entry_slug:
            return ""

        available_page_slugs: set[str] = set()

        pages = funnel_payload.get("pages")
        if isinstance(pages, dict):
            for raw_page_slug in pages.keys():
                canonical_page_slug = self._canonical_funnel_artifact_page_slug(raw_page_slug)
                if canonical_page_slug:
                    available_page_slugs.add(canonical_page_slug)

        meta_pages = funnel_meta.get("pages")
        if isinstance(meta_pages, list):
            for raw_page in meta_pages:
                if not isinstance(raw_page, dict):
                    continue
                canonical_page_slug = self._canonical_funnel_artifact_page_slug(
                    raw_page.get("slug")
                )
                if canonical_page_slug:
                    available_page_slugs.add(canonical_page_slug)

        policy = str(default_route_policy or "entry_page").strip().lower()
        if policy == "none":
            return ""
        if policy == "entry_page":
            return entry_slug
        if policy == "explicit_slug":
            explicit_slug = self._canonical_funnel_artifact_page_slug(default_page_slug)
            if not explicit_slug:
                raise ValueError(
                    "source_ref.default_page_slug is required when default_route_policy='explicit_slug'."
                )
            if explicit_slug not in available_page_slugs:
                raise ValueError(
                    f"source_ref.default_page_slug '{explicit_slug}' was not found in artifact pages."
                )
            return explicit_slug
        if policy != "prefer_sales":
            raise ValueError(
                "source_ref.default_route_policy must be one of: entry_page, prefer_sales, explicit_slug, none."
            )

        for candidate_slug in ("sales-page", "sales"):
            if candidate_slug in available_page_slugs:
                return candidate_slug

        return entry_slug

    def _build_entry_image_preload_map(self, *, source: FunnelArtifactSourceSpec) -> Dict[str, str]:
        artifact = source.artifact or {}
        products = artifact.get("products")
        if not isinstance(products, dict):
            return {}

        preload_map: Dict[str, str] = {}
        for raw_product_slug, product_payload in products.items():
            product_slug = str(raw_product_slug or "").strip().lower()
            if not product_slug:
                continue
            if not isinstance(product_payload, dict):
                continue
            funnels = product_payload.get("funnels")
            if not isinstance(funnels, dict):
                continue

            for raw_funnel_slug, funnel_payload in funnels.items():
                funnel_slug = str(raw_funnel_slug or "").strip().lower()
                if not funnel_slug:
                    continue
                if not isinstance(funnel_payload, dict):
                    continue
                funnel_meta = funnel_payload.get("meta")
                pages = funnel_payload.get("pages")
                if not isinstance(funnel_meta, dict) or not isinstance(pages, dict):
                    continue

                default_page_slug = self._resolve_funnel_artifact_default_page_slug(
                    funnel_meta=funnel_meta,
                    funnel_payload=funnel_payload,
                    default_route_policy=source.default_route_policy,
                    default_page_slug=source.default_page_slug,
                )
                if not default_page_slug:
                    continue

                default_page_payload: Optional[Dict[str, Any]] = None
                for raw_page_slug, page_payload in pages.items():
                    page_slug = self._canonical_funnel_artifact_page_slug(raw_page_slug)
                    if page_slug != default_page_slug:
                        continue
                    if not isinstance(page_payload, dict):
                        raise ValueError(
                            f"Artifact page payload for '{product_slug}/{funnel_slug}/{default_page_slug}' must be an object."
                        )
                    default_page_payload = page_payload
                    break

                if default_page_payload is None:
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' default page slug "
                        f"'{default_page_slug}' was not found in pages."
                    )

                preload_asset_public_id = self._resolve_entry_preload_asset_public_id(
                    page_payload=default_page_payload,
                    context_label=f"Artifact funnel '{product_slug}/{funnel_slug}/{default_page_slug}'",
                )
                if not preload_asset_public_id:
                    continue

                for funnel_path_token in self._resolve_funnel_path_tokens_for_source(
                    source=source,
                    product_slug=product_slug,
                    funnel_slug=funnel_slug,
                    funnel_meta=funnel_meta,
                ):
                    normalized_funnel_path_token = str(funnel_path_token or "").strip().lower()
                    if not normalized_funnel_path_token:
                        continue
                    route_key = f"{product_slug}/{normalized_funnel_path_token}/{default_page_slug}"
                    existing_asset = preload_map.get(route_key)
                    if existing_asset and existing_asset != preload_asset_public_id:
                        raise ValueError(
                            f"Entry preload route '{route_key}' maps to multiple asset ids ('{existing_asset}' and "
                            f"'{preload_asset_public_id}')."
                        )
                    preload_map[route_key] = preload_asset_public_id

        return preload_map

    def _resolve_funnel_artifact_default_route(
        self, *, source: FunnelArtifactSourceSpec
    ) -> Optional[tuple[str, str, str]]:
        resolved_target = self._resolve_funnel_artifact_runtime_target(source=source)
        if not resolved_target:
            return None
        return (
            str(resolved_target["productSlug"]),
            str(resolved_target["funnelSlug"]),
            str(resolved_target.get("defaultPageSlug") or resolved_target["entrySlug"]),
        )

    def _funnel_artifact_declares_posthog_tracking(
        self, *, source: FunnelArtifactSourceSpec
    ) -> bool:
        (
            _artifact,
            _meta,
            products,
            _asset_items,
            _static_asset_items,
        ) = self._resolve_funnel_artifact_payload_sections(source=source)
        for product_payload in products.values():
            if not isinstance(product_payload, dict):
                continue
            funnels = product_payload.get("funnels")
            if not isinstance(funnels, dict):
                continue
            for funnel_payload in funnels.values():
                if not isinstance(funnel_payload, dict):
                    continue
                pages = funnel_payload.get("pages")
                if not isinstance(pages, dict):
                    continue
                for page_payload in pages.values():
                    if not isinstance(page_payload, dict):
                        continue
                    tracking = page_payload.get("tracking")
                    if not isinstance(tracking, dict):
                        continue
                    api_key = str(tracking.get("posthogProjectApiKey") or "").strip()
                    api_host = str(tracking.get("posthogApiHost") or "").strip()
                    if api_key and api_host:
                        return True
        return False

    def _funnel_artifact_declares_meta_tracking(self, *, source: FunnelArtifactSourceSpec) -> bool:
        (
            _artifact,
            _meta,
            products,
            _asset_items,
            _static_asset_items,
        ) = self._resolve_funnel_artifact_payload_sections(source=source)
        for product_payload in products.values():
            if not isinstance(product_payload, dict):
                continue
            funnels = product_payload.get("funnels")
            if not isinstance(funnels, dict):
                continue
            for funnel_payload in funnels.values():
                if not isinstance(funnel_payload, dict):
                    continue
                pages = funnel_payload.get("pages")
                if not isinstance(pages, dict):
                    continue
                for page_payload in pages.values():
                    if not isinstance(page_payload, dict):
                        continue
                    tracking = page_payload.get("tracking")
                    if not isinstance(tracking, dict):
                        continue
                    pixel_id = str(tracking.get("metaPixelId") or "").strip()
                    if pixel_id:
                        return True
        return False

    def _remote_tree_contains_text(self, *, root_path: str, text: str) -> bool:
        safe_root = shlex.quote(root_path)
        safe_text = shlex.quote(text)
        out = self.run(
            f"grep -R -F -q -- {safe_text} {safe_root} >/dev/null 2>&1 && echo yes || true"
        )
        return out.strip() == "yes"

    def _validate_html_deploy_release_asset_closure(
        self,
        *,
        site_dir: str,
    ) -> None:
        script = r'''
import json
import os
import posixpath
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit

site_dir = os.path.abspath(sys.argv[1])
report_path = os.path.join(site_dir, "mos-release-integrity-report.json")
required_prefixes = (
    "/assets/",
    "/public/assets/",
    "/api/public/assets/",
    "/_standalone-assets/",
    "/cdn/shop/files/",
    "/favicon",
)
fragment_only_roots = {
    "/assets",
    "/public/assets",
    "/api/public/assets",
    "/_standalone-assets",
    "/cdn/shop/files",
}
extension_candidates = (
    "",
    ".webp",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".avif",
    ".css",
    ".js",
    ".mjs",
    ".woff2",
    ".woff",
    ".ttf",
    ".otf",
    ".eot",
    ".ico",
    ".json",
)
scan_extensions = (".html", ".css", ".js", ".mjs", ".json", ".svg")
report_file_names = {
    "mos-release-integrity-report.json",
    "mos-release-static-assets-report.json",
}
attr_url_re = re.compile(
    r"""(?:src|href|poster|data-src|data-href|srcset|imagesrcset)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
css_url_re = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.IGNORECASE)
quoted_path_re = re.compile(
    r"""["']((?:/(?:assets|public/assets|api/public/assets|_standalone-assets|cdn/shop/files)/|/favicon)[^"']*)["']""",
    re.IGNORECASE,
)


def clean_reference(raw):
    value = str(raw or "").strip()
    if not value:
        return ""
    lower = value.lower()
    if any(
        marker in lower
        for marker in (
            "/assets/#",
            "/public/assets/#",
            "/api/public/assets/#",
            "/_standalone-assets/#",
            "/cdn/shop/files/#",
        )
    ):
        return ""
    if (
        lower.startswith("data:")
        or lower.startswith("blob:")
        or lower.startswith("mailto:")
        or lower.startswith("tel:")
        or lower.startswith("javascript:")
        or lower.startswith("#")
    ):
        return ""
    return value


def split_srcset(raw):
    for candidate in str(raw or "").split(","):
        token = candidate.strip().split()
        if token:
            yield token[0]


def path_from_reference(raw, *, base_path):
    value = clean_reference(raw)
    if not value:
        return ""
    parsed = urlsplit(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
    path = unquote(path.strip())
    if not path:
        return ""
    path = path.split()[0]
    if not path.startswith("/"):
        joined_path = posixpath.normpath(posixpath.join(posixpath.dirname(base_path), path))
        path = joined_path if joined_path.startswith("/") else "/" + joined_path
    if not path.startswith("/"):
        return ""
    lower_path = path.lower()
    if parsed.fragment and lower_path.rstrip("/") in fragment_only_roots:
        return ""
    if not should_validate_asset_path(path):
        return ""
    return path


def should_validate_asset_path(path):
    lower_path = str(path or "").lower()
    _base, ext = os.path.splitext(lower_path)
    has_deployable_extension = bool(ext and ext in extension_candidates)
    if lower_path.startswith("/assets/"):
        return has_deployable_extension
    if lower_path.startswith(("/_standalone-assets/", "/cdn/shop/files/")):
        return has_deployable_extension
    if lower_path.startswith(("/public/assets/", "/api/public/assets/", "/favicon")):
        return True
    if "/assets/" in lower_path and not lower_path.startswith("/cdn/shop/t/"):
        return has_deployable_extension
    return False


def candidate_paths(path):
    candidates = []

    def add(candidate):
        if candidate not in candidates:
            candidates.append(candidate)

    add(path)
    if path.startswith("/public/assets/"):
        add("/api" + path)
    if path.startswith("/api/public/assets/"):
        add(path.removeprefix("/api"))
    base, ext = os.path.splitext(path)
    if not ext:
        for extension in extension_candidates:
            add(path + extension)
            if path.startswith("/public/assets/"):
                add("/api" + path + extension)
            if path.startswith("/api/public/assets/"):
                add(path.removeprefix("/api") + extension)
    return [os.path.join(site_dir, candidate.lstrip("/")) for candidate in candidates]


def exists_locally(path):
    return any(os.path.isfile(candidate) for candidate in candidate_paths(path))


missing = []
scanned_files = 0
checked_references = 0
for root, _dirs, files in os.walk(site_dir):
    for file_name in files:
        if file_name in report_file_names:
            continue
        if not file_name.lower().endswith(scan_extensions):
            continue
        file_path = os.path.join(root, file_name)
        rel_path = "/" + os.path.relpath(file_path, site_dir)
        try:
            text = open(file_path, "r", encoding="utf-8", errors="ignore").read()
        except OSError as exc:
            missing.append({"file": rel_path, "url": "<read>", "reason": str(exc)})
            continue
        scanned_files += 1
        raw_refs = []
        raw_refs.extend(match.group(1) for match in attr_url_re.finditer(text))
        raw_refs.extend(match.group(1) for match in css_url_re.finditer(text))
        raw_refs.extend(match.group(1) for match in quoted_path_re.finditer(text))
        expanded_refs = []
        for raw_ref in raw_refs:
            if "," in str(raw_ref) and ("srcset" in text.lower() or "imagesrcset" in text.lower()):
                expanded_refs.extend(split_srcset(raw_ref))
            expanded_refs.append(raw_ref)
        seen_paths = set()
        for raw_ref in expanded_refs:
            path = path_from_reference(raw_ref, base_path=rel_path)
            if not path:
                continue
            if "#" in path:
                continue
            if path in seen_paths:
                continue
            seen_paths.add(path)
            checked_references += 1
            if not exists_locally(path):
                missing.append({"file": rel_path, "url": path, "reason": "missing local release asset"})

status = "failed" if missing else "passed"
report = {
    "status": status,
    "scannedFiles": scanned_files,
    "checkedReferences": checked_references,
    "missing": missing[:100],
}
with open(report_path, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
if missing:
    print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)
print(json.dumps(report, sort_keys=True))
'''
        self.run("python3 - " + shlex.quote(site_dir) + " <<'PY'\n" + script + "\nPY")

    def _materialize_html_deploy_release_static_dependencies(
        self,
        *,
        site_dir: str,
        public_server_names: list[str],
    ) -> None:
        origins: list[str] = []
        seen_origins: set[str] = set()
        for raw_name in public_server_names:
            server_name = str(raw_name or "").strip()
            if not server_name:
                continue
            parsed = urlsplit(server_name if "://" in server_name else f"https://{server_name}")
            host = parsed.netloc.strip().lower()
            if not host:
                continue
            scheme = parsed.scheme.strip().lower() or "https"
            origin = f"{scheme}://{host}".rstrip("/")
            if origin in seen_origins:
                continue
            seen_origins.add(origin)
            origins.append(origin)
        script = r'''
import glob
import json
import mimetypes
import os
import posixpath
import re
import shutil
import sys
import urllib.error
import urllib.request
from urllib.parse import unquote, urljoin, urlsplit

site_dir = os.path.abspath(sys.argv[1])
origins = json.loads(sys.argv[2])
report_path = os.path.join(site_dir, "mos-release-static-assets-report.json")
required_prefixes = (
    "/assets/",
    "/public/assets/",
    "/api/public/assets/",
    "/_standalone-assets/",
    "/cdn/shop/files/",
    "/favicon",
)
fragment_only_roots = {
    "/assets",
    "/public/assets",
    "/api/public/assets",
    "/_standalone-assets",
    "/cdn/shop/files",
}
materializable_prefixes = (
    "/assets/",
    "/public/assets/",
    "/api/public/assets/",
    "/_standalone-assets/",
    "/cdn/shop/files/",
    "/favicon",
)
extension_candidates = (
    "",
    ".webp",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".avif",
    ".css",
    ".js",
    ".mjs",
    ".woff2",
    ".woff",
    ".ttf",
    ".otf",
    ".eot",
    ".ico",
    ".json",
)
scan_extensions = (".html", ".css", ".js", ".mjs", ".json", ".svg")
report_file_names = {
    "mos-release-integrity-report.json",
    "mos-release-static-assets-report.json",
}
attr_url_re = re.compile(
    r"""(?:src|href|poster|data-src|data-href|srcset|imagesrcset)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
css_url_re = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.IGNORECASE)
quoted_path_re = re.compile(
    r"""["']((?:/(?:assets|public/assets|api/public/assets|_standalone-assets|cdn/shop/files)/|/favicon)[^"']*)["']""",
    re.IGNORECASE,
)


def clean_reference(raw):
    value = str(raw or "").strip()
    if not value:
        return ""
    lower = value.lower()
    if any(
        marker in lower
        for marker in (
            "/assets/#",
            "/public/assets/#",
            "/api/public/assets/#",
            "/_standalone-assets/#",
            "/cdn/shop/files/#",
        )
    ):
        return ""
    if (
        lower.startswith("data:")
        or lower.startswith("blob:")
        or lower.startswith("mailto:")
        or lower.startswith("tel:")
        or lower.startswith("javascript:")
        or lower.startswith("#")
    ):
        return ""
    return value


def split_srcset(raw):
    for candidate in str(raw or "").split(","):
        token = candidate.strip().split()
        if token:
            yield token[0]


def path_from_reference(raw, *, base_path):
    value = clean_reference(raw)
    if not value:
        return ""
    parsed = urlsplit(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
    path = unquote(path.strip())
    if not path:
        return ""
    path = path.split()[0]
    if not path.startswith("/"):
        joined_path = posixpath.normpath(posixpath.join(posixpath.dirname(base_path), path))
        path = joined_path if joined_path.startswith("/") else "/" + joined_path
    if not path.startswith("/"):
        return ""
    lower_path = path.lower()
    if parsed.fragment and lower_path.rstrip("/") in fragment_only_roots:
        return ""
    if not should_validate_asset_path(path):
        return ""
    return path


def should_validate_asset_path(path):
    lower_path = str(path or "").lower()
    _base, ext = os.path.splitext(lower_path)
    has_deployable_extension = bool(ext and ext in extension_candidates)
    if lower_path.startswith("/assets/"):
        return has_deployable_extension
    if lower_path.startswith(("/_standalone-assets/", "/cdn/shop/files/")):
        return has_deployable_extension
    if lower_path.startswith(("/public/assets/", "/api/public/assets/", "/favicon")):
        return True
    if "/assets/" in lower_path and not lower_path.startswith("/cdn/shop/t/"):
        return has_deployable_extension
    return False


def route_local_asset_equivalent(path):
    normalized_path = str(path or "")
    marker = "/assets/"
    if normalized_path.startswith(marker):
        return None
    marker_index = normalized_path.find(marker)
    if marker_index <= 0:
        return None
    return normalized_path[marker_index:]


def should_materialize_asset_path(path):
    lower_path = str(path or "").lower()
    if any(lower_path.startswith(prefix) for prefix in materializable_prefixes):
        return True
    if lower_path.startswith("/cdn/shop/t/"):
        return False
    return route_local_asset_equivalent(lower_path) is not None


def candidate_paths(path):
    candidates = []

    def add(candidate):
        if candidate not in candidates:
            candidates.append(candidate)

    add(path)
    if path.startswith("/public/assets/"):
        add("/api" + path)
    if path.startswith("/api/public/assets/"):
        add(path.removeprefix("/api"))
    base, ext = os.path.splitext(path)
    if not ext:
        for extension in extension_candidates:
            add(path + extension)
            if path.startswith("/public/assets/"):
                add("/api" + path + extension)
            if path.startswith("/api/public/assets/"):
                add(path.removeprefix("/api") + extension)
    return [os.path.join(site_dir, candidate.lstrip("/")) for candidate in candidates]


def exists_locally(path):
    return any(os.path.isfile(candidate) for candidate in candidate_paths(path))


def scan_missing():
    missing = []
    scanned_files = 0
    checked_references = 0
    for root, _dirs, files in os.walk(site_dir):
        for file_name in files:
            if file_name in report_file_names:
                continue
            if not file_name.lower().endswith(scan_extensions):
                continue
            file_path = os.path.join(root, file_name)
            rel_path = "/" + os.path.relpath(file_path, site_dir)
            try:
                text = open(file_path, "r", encoding="utf-8", errors="ignore").read()
            except OSError as exc:
                missing.append({"file": rel_path, "url": "<read>", "reason": str(exc)})
                continue
            scanned_files += 1
            raw_refs = []
            raw_refs.extend(match.group(1) for match in attr_url_re.finditer(text))
            raw_refs.extend(match.group(1) for match in css_url_re.finditer(text))
            raw_refs.extend(match.group(1) for match in quoted_path_re.finditer(text))
            expanded_refs = []
            for raw_ref in raw_refs:
                if "," in str(raw_ref) and ("srcset" in text.lower() or "imagesrcset" in text.lower()):
                    expanded_refs.extend(split_srcset(raw_ref))
                expanded_refs.append(raw_ref)
            seen_paths = set()
            for raw_ref in expanded_refs:
                path = path_from_reference(raw_ref, base_path=rel_path)
                if not path:
                    continue
                if "#" in path:
                    continue
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                checked_references += 1
                if not exists_locally(path):
                    missing.append({"file": rel_path, "url": path, "reason": "missing local release asset"})
    return {
        "scannedFiles": scanned_files,
        "checkedReferences": checked_references,
        "missing": missing,
    }


def write_report(status, *, scanned, checked, missing, materialized, unresolved):
    report = {
        "status": status,
        "origins": origins,
        "scannedFiles": scanned,
        "checkedReferences": checked,
        "materializedCount": len(materialized),
        "materialized": materialized[:200],
        "unresolvedCount": len(unresolved),
        "unresolved": unresolved[:200],
        "remainingMissingCount": len(missing),
        "remainingMissing": missing[:200],
    }
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    return report


def reject_html_payload(path, content_type):
    lower_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if not lower_type:
        return False
    if lower_type != "text/html":
        return False
    lower_path = path.lower()
    return not lower_path.endswith((".html", ".htm"))


def fetch_to_path(path):
    if not origins:
        return None
    accept = "*/*"
    if path.lower().endswith((".css", ".js", ".mjs", ".json")):
        accept = "text/css,application/javascript,application/json,*/*;q=0.1"
    elif path.lower().endswith((".woff2", ".woff", ".ttf", ".otf", ".eot")):
        accept = "font/woff2,font/woff,font/ttf,font/otf,application/octet-stream,*/*;q=0.1"
    elif path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg", ".ico")):
        accept = "image/avif,image/webp,image/svg+xml,image/*,*/*;q=0.1"
    errors = []
    for origin in origins:
        url = urljoin(origin.rstrip("/") + "/", path.lstrip("/"))
        request = urllib.request.Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": "MOS-html-deploy-v1-static-materializer/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = getattr(response, "status", 200)
                content_type = response.headers.get("Content-Type", "")
                payload = response.read()
        except Exception as exc:  # noqa: BLE001 - report every attempted origin.
            errors.append(f"{url}: {exc}")
            continue
        if status < 200 or status >= 300:
            errors.append(f"{url}: HTTP {status}")
            continue
        if not payload:
            errors.append(f"{url}: empty response")
            continue
        if reject_html_payload(path, content_type):
            errors.append(f"{url}: refused HTML response for static asset")
            continue
        normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
        target_path = path
        if path.startswith(("/public/assets/", "/api/public/assets/")) and not os.path.splitext(path)[1]:
            if normalized_content_type == "image/webp":
                target_path = path + ".webp"
            elif normalized_content_type in {"image/jpeg", "image/jpg"}:
                target_path = path + ".jpg"
            elif normalized_content_type == "image/png":
                target_path = path + ".png"
            elif normalized_content_type == "image/gif":
                target_path = path + ".gif"
            elif normalized_content_type == "image/svg+xml":
                target_path = path + ".svg"
            elif normalized_content_type == "image/avif":
                target_path = path + ".avif"
        target = os.path.join(site_dir, target_path.lstrip("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(payload)
        if path.startswith("/public/assets/"):
            api_target = os.path.join(site_dir, "api", target_path.lstrip("/"))
            os.makedirs(os.path.dirname(api_target), exist_ok=True)
            shutil.copyfile(target, api_target)
        elif path.startswith("/api/public/assets/"):
            public_target = os.path.join(site_dir, target_path.removeprefix("/api").lstrip("/"))
            os.makedirs(os.path.dirname(public_target), exist_ok=True)
            shutil.copyfile(target, public_target)
        return {"url": path, "source": url, "contentType": content_type or mimetypes.guess_type(path)[0] or "application/octet-stream", "sizeBytes": len(payload)}
    return {"url": path, "error": "; ".join(errors) or "no origin succeeded"}


def copy_equivalent_asset(path):
    candidates = []
    if path.startswith("/cdn/shop/files/"):
        name = os.path.basename(path)
        stem, ext = os.path.splitext(name)
        if not stem:
            return None
        asset_dir = os.path.join(site_dir, "assets")
        exact_asset = os.path.join(asset_dir, name)
        if os.path.isfile(exact_asset):
            candidates.append(exact_asset)
        if ext:
            candidates.extend(sorted(glob.glob(os.path.join(asset_dir, f"{stem}-*{ext}"))))
    equivalent_asset_path = route_local_asset_equivalent(path)
    if equivalent_asset_path:
        equivalent_source = os.path.join(site_dir, equivalent_asset_path.lstrip("/"))
        if os.path.isfile(equivalent_source):
            candidates.append(equivalent_source)
    for source_path in candidates:
        if not os.path.isfile(source_path):
            continue
        target = os.path.join(site_dir, path.lstrip("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source_path, target)
        return {
            "url": path,
            "source": "/" + os.path.relpath(source_path, site_dir),
            "contentType": mimetypes.guess_type(source_path)[0] or "application/octet-stream",
            "sizeBytes": os.path.getsize(target),
        }
    return None


materialized = []
unresolved = []
last_scan = scan_missing()
for _iteration in range(4):
    missing_paths = []
    seen = set()
    for item in last_scan["missing"]:
        path = str(item.get("url") or "")
        if not path or path in seen:
            continue
        if "#" in path:
            continue
        if not should_materialize_asset_path(path):
            continue
        seen.add(path)
        missing_paths.append(path)
    if not missing_paths:
        break
    changed = False
    missing_paths.sort(key=lambda value: (0 if value.startswith("/assets/") else 1, value))
    for path in missing_paths:
        if exists_locally(path):
            continue
        copied = copy_equivalent_asset(path)
        if copied is not None:
            materialized.append(copied)
            changed = True
            continue
        fetched = fetch_to_path(path)
        if fetched and "error" not in fetched:
            materialized.append(fetched)
            changed = True
        elif fetched:
            unresolved.append(fetched)
    next_scan = scan_missing()
    if len(next_scan["missing"]) >= len(last_scan["missing"]) and not changed:
        last_scan = next_scan
        break
    last_scan = next_scan

remaining = last_scan["missing"]
status = "passed" if not remaining else "failed"
report = write_report(
    status,
    scanned=last_scan["scannedFiles"],
    checked=last_scan["checkedReferences"],
    missing=remaining,
    materialized=materialized,
    unresolved=unresolved,
)
if remaining:
    print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)
print(json.dumps(report, sort_keys=True))
'''
        self.run(
            "python3 - "
            + shlex.quote(site_dir)
            + " "
            + shlex.quote(json.dumps(origins))
            + " <<'PY'\n"
            + script
            + "\nPY"
        )

    def _validate_funnel_artifact_site_output(
        self,
        *,
        site_dir: str,
        source: FunnelArtifactSourceSpec,
        render_mode: FunnelArtifactRenderMode,
    ) -> None:
        if render_mode == FunnelArtifactRenderMode.RUNTIME_BUNDLE:
            index_path = f"{site_dir}/index.html"
            if not self._path_exists(index_path):
                raise ValueError(
                    f"Funnel artifact runtime bundle export did not produce '{index_path}'."
                )
            return

        default_route = self._resolve_funnel_artifact_default_route(source=source)
        if default_route:
            default_index_path = f"{site_dir}/{'/'.join(default_route)}/index.html"
            if not self._path_exists(default_index_path):
                raise ValueError(
                    "HTML deploy artifact export did not produce the default route entry page "
                    f"at '{default_index_path}'."
                )

        if not self._remote_tree_contains_text(
            root_path=site_dir,
            text="MOS_HTML_DEPLOY_BRIDGE_START",
        ):
            raise ValueError(
                "HTML deploy artifact export is missing the imported HTML bridge marker. "
                "The site was not activated."
            )

        unresolved_tokens = (
            "__MOS_HTML_DEPLOY_CONFIG__",
            "__MOS_STANDALONE_META_PIXEL_DEFER_TIMEOUT_MS__",
        )
        for token in unresolved_tokens:
            if self._remote_tree_contains_text(root_path=site_dir, text=token):
                raise ValueError(
                    "HTML deploy artifact export still contains unresolved runtime placeholders "
                    f"('{token}'). The site was not activated."
                )

        if self._funnel_artifact_declares_posthog_tracking(
            source=source
        ) and not self._remote_tree_contains_text(
            root_path=site_dir,
            text="window.posthog.init(",
        ):
            raise ValueError(
                "HTML deploy artifact export declared PostHog tracking but did not emit the PostHog bootstrap. "
                "The site was not activated."
            )
        if self._funnel_artifact_declares_posthog_tracking(source=source):
            if self._remote_tree_contains_text(root_path=site_dir, text="capture_pageview: false"):
                raise ValueError(
                    "HTML deploy artifact export declared PostHog tracking but disabled capture_pageview. "
                    "The site was not activated."
                )
            if self._remote_tree_contains_text(root_path=site_dir, text="capture_pageleave: false"):
                raise ValueError(
                    "HTML deploy artifact export declared PostHog tracking but disabled capture_pageleave. "
                    "The site was not activated."
                )
            for token in (
                "getCanonicalPostHogDistinctId",
                "funnel_session_id",
                "restorePostHogIdentity(instance);",
            ):
                if not self._remote_tree_contains_text(root_path=site_dir, text=token):
                    raise ValueError(
                        "HTML deploy artifact export declared PostHog tracking but did not emit "
                        f"the required identity continuity token {token!r}. The site was not activated."
                    )
        if self._funnel_artifact_declares_meta_tracking(source=source):
            if not self._remote_tree_contains_text(
                root_path=site_dir,
                text="https://connect.facebook.net/en_US/fbevents.js",
            ):
                raise ValueError(
                    "HTML deploy artifact export declared Meta tracking but did not emit the direct Meta Pixel script. "
                    "The site was not activated."
                )
            if not self._remote_tree_contains_text(
                root_path=site_dir,
                text='window.fbq("init", pixelId);',
            ):
                raise ValueError(
                    "HTML deploy artifact export declared Meta tracking but did not emit the Meta Pixel bootstrap. "
                    "The site was not activated."
                )

    def _activate_funnel_artifact_site_release(
        self,
        *,
        app_dir: str,
        live_site_dir: str,
        built_site_dir: str,
    ) -> None:
        next_link_path = f"{app_dir}/{_FUNNEL_ARTIFACT_LIVE_DIRNAME}.__next__"
        release_id = str(Path(built_site_dir).name or "").strip() or _funnel_artifact_release_id()
        legacy_site_dir = f"{app_dir}/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/legacy-{release_id}"
        self.run(
            "bash -lc "
            + shlex.quote(
                "\n".join(
                    [
                        "set -euo pipefail",
                        f"live_site={shlex.quote(live_site_dir)}",
                        f"built_site={shlex.quote(built_site_dir)}",
                        f"next_link={shlex.quote(next_link_path)}",
                        f"legacy_site={shlex.quote(legacy_site_dir)}",
                        'rm -f "$next_link"',
                        'if [ ! -d "$built_site" ]; then',
                        '  echo "missing built standalone site: $built_site" >&2',
                        "  exit 1",
                        "fi",
                        'if [ ! -s "$built_site/mos-release-manifest.json" ]; then',
                        '  echo "missing html-deploy release manifest: $built_site/mos-release-manifest.json" >&2',
                        "  exit 1",
                        "fi",
                        'if [ ! -s "$built_site/mos-release-integrity-report.json" ]; then',
                        '  echo "missing html-deploy release integrity report: $built_site/mos-release-integrity-report.json" >&2',
                        "  exit 1",
                        "fi",
                        "python3 - \"$built_site/mos-release-integrity-report.json\" <<'PY'",
                        "import json, sys",
                        "report_path = sys.argv[1]",
                        "with open(report_path, 'r', encoding='utf-8') as handle:",
                        "    report = json.load(handle)",
                        "if report.get('status') != 'passed':",
                        '    print(f"html-deploy release integrity did not pass: {report_path}", file=sys.stderr)',
                        "    sys.exit(1)",
                        "PY",
                        'if [ -e "$live_site" ] && [ ! -L "$live_site" ]; then',
                        '  rm -rf "$legacy_site"',
                        '  mv "$live_site" "$legacy_site"',
                        "fi",
                        'ln -sfn "$built_site" "$next_link"',
                        'mv -Tf "$next_link" "$live_site"',
                    ]
                )
            )
        )

    def activate_funnel_artifact_candidate_release(
        self,
        *,
        app_name: str,
        destination_path: str,
        release_id: str,
    ) -> None:
        normalized_app_name = str(app_name or "").strip()
        if not normalized_app_name:
            raise ValueError("HTML deploy candidate activation requires a workload name.")
        normalized_destination_path = str(destination_path or "").strip().rstrip("/") or "/opt/apps"
        normalized_release_id = _validate_funnel_artifact_release_id(release_id)
        app_dir = f"{normalized_destination_path}/{normalized_app_name}"
        self._activate_funnel_artifact_site_release(
            app_dir=app_dir,
            live_site_dir=f"{app_dir}/{_FUNNEL_ARTIFACT_LIVE_DIRNAME}",
            built_site_dir=(
                f"{app_dir}/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/{normalized_release_id}"
            ),
        )

    def _resolve_funnel_artifact_runtime_target(
        self, *, source: FunnelArtifactSourceSpec
    ) -> Optional[Dict[str, Any]]:
        artifact = source.artifact or {}
        products = artifact.get("products")
        if not isinstance(products, dict):
            return None

        artifact_meta = artifact.get("meta")
        preferred_funnel_id = ""
        preferred_publication_id = ""
        if isinstance(artifact_meta, dict):
            preferred_funnel_id = (
                str(artifact_meta.get("updatedFromFunnelId") or "").strip().lower()
            )
            preferred_publication_id = (
                str(artifact_meta.get("updatedFromPublicationId") or "").strip().lower()
            )

        fallback_target: Optional[Dict[str, Any]] = None
        for raw_product_slug, product_payload in products.items():
            product_slug = str(raw_product_slug or "").strip()
            if not product_slug:
                continue
            if not isinstance(product_payload, dict):
                continue
            funnels = product_payload.get("funnels")
            if not isinstance(funnels, dict):
                continue

            for raw_funnel_slug, funnel_payload in funnels.items():
                funnel_slug = str(raw_funnel_slug or "").strip()
                if not funnel_slug:
                    continue
                if not isinstance(funnel_payload, dict):
                    continue

                funnel_meta = funnel_payload.get("meta")
                if not isinstance(funnel_meta, dict):
                    return None

                canonical_funnel_meta = self._canonicalize_funnel_artifact_meta(
                    funnel_meta=funnel_meta
                )
                entry_slug = self._canonical_funnel_artifact_page_slug(
                    canonical_funnel_meta.get("entrySlug")
                )
                if not entry_slug:
                    return None

                canonical_funnel_slug = (
                    str(canonical_funnel_meta.get("funnelSlug") or "").strip() or funnel_slug
                )
                funnel_id_token = str(canonical_funnel_meta.get("funnelId") or "").strip().lower()

                candidate = {
                    "productSlug": product_slug,
                    "funnelSlug": canonical_funnel_slug,
                    "entrySlug": entry_slug,
                    "defaultPageSlug": self._resolve_funnel_artifact_default_page_slug(
                        funnel_meta=canonical_funnel_meta,
                        funnel_payload=funnel_payload,
                        default_route_policy=source.default_route_policy,
                        default_page_slug=source.default_page_slug,
                    ),
                    "funnelMeta": canonical_funnel_meta,
                    "funnelPayload": funnel_payload,
                }
                if fallback_target is None:
                    fallback_target = candidate

                publication_id_token = (
                    str(canonical_funnel_meta.get("publicationId") or "").strip().lower()
                )
                if preferred_funnel_id and funnel_id_token == preferred_funnel_id:
                    return candidate
                if (
                    preferred_publication_id
                    and publication_id_token
                    and publication_id_token == preferred_publication_id
                ):
                    return candidate

        return fallback_target

    def _resolve_preferred_funnel_artifact_export_target(
        self, *, source: FunnelArtifactSourceSpec
    ) -> Optional[Dict[str, Any]]:
        artifact = source.artifact or {}
        artifact_meta = artifact.get("meta")
        if not isinstance(artifact_meta, dict):
            return None
        preferred_funnel_id = str(artifact_meta.get("updatedFromFunnelId") or "").strip()
        preferred_publication_id = str(artifact_meta.get("updatedFromPublicationId") or "").strip()
        if not preferred_funnel_id and not preferred_publication_id:
            return None
        return self._resolve_funnel_artifact_runtime_target(source=source)

    def _build_preloaded_funnel_runtime_payload(
        self, *, source: FunnelArtifactSourceSpec
    ) -> Optional[Dict[str, object]]:
        resolved_target = self._resolve_funnel_artifact_runtime_target(source=source)
        if not resolved_target:
            return None

        product_slug = str(resolved_target["productSlug"])
        funnel_slug = str(resolved_target["funnelSlug"])
        funnel_meta = resolved_target.get("funnelMeta")
        resolved_funnel_payload = resolved_target.get("funnelPayload")
        pages = (
            resolved_funnel_payload.get("pages")
            if isinstance(resolved_funnel_payload, dict)
            else None
        )
        if not isinstance(funnel_meta, dict) or not isinstance(pages, dict):
            return None

        canonical_meta = dict(funnel_meta)
        canonical_pages: Dict[str, Dict[str, Any]] = {}
        for raw_page_slug, page_payload in pages.items():
            if not isinstance(page_payload, dict):
                raise ValueError(
                    f"Artifact page payload for '{product_slug}/{funnel_slug}/{raw_page_slug}' must be an object."
                )
            canonical_slug = self._canonical_funnel_artifact_page_slug(str(raw_page_slug or ""))
            if not canonical_slug:
                continue
            canonical_pages[canonical_slug] = self._canonicalize_funnel_artifact_page_payload(
                page_slug=str(raw_page_slug or ""),
                page_payload=page_payload,
            )
        default_page_slug = str(resolved_target.get("defaultPageSlug") or "").strip()
        if not default_page_slug:
            raise ValueError(
                f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a canonical default page slug for runtime preload."
            )
        default_page_payload = canonical_pages.get(default_page_slug)
        if not isinstance(default_page_payload, dict):
            raise ValueError(
                f"Artifact funnel '{product_slug}/{funnel_slug}' default page slug "
                f"'{default_page_slug}' was not found in pages."
            )
        return {
            "productSlug": product_slug,
            "funnelSlug": funnel_slug,
            "meta": {
                **canonical_meta,
                "funnelSlug": funnel_slug,
            },
            # Keep the deploy-time inline runtime lean so mobile webviews only pay for the default landing page.
            "pages": {default_page_slug: default_page_payload},
        }

    def _inject_funnel_runtime_config(
        self, *, site_dir: str, source: FunnelArtifactSourceSpec
    ) -> None:
        runtime_config: Dict[str, object] = {"bundleMode": True}
        default_route = self._resolve_funnel_artifact_default_route(source=source)
        if default_route:
            product_slug, funnel_slug, entry_slug = default_route
            runtime_config["defaultProductSlug"] = product_slug
            runtime_config["defaultFunnelSlug"] = funnel_slug
            runtime_config["defaultEntrySlug"] = entry_slug

        entry_image_preload_map = self._build_entry_image_preload_map(source=source)
        if entry_image_preload_map:
            runtime_config["entryImagePreloadMap"] = entry_image_preload_map

        preloaded_funnel = self._build_preloaded_funnel_runtime_payload(source=source)
        if preloaded_funnel:
            runtime_config["preloadedFunnel"] = preloaded_funnel

        config_json = _safe_inline_json(runtime_config)
        runtime_script = (
            "<script>"
            f"window.__MOS_DEPLOY_RUNTIME__={config_json};"
            "(function(){"
            "var config=window.__MOS_DEPLOY_RUNTIME__;"
            "if(!config||typeof config!=='object'){return;}"
            "var preloadMap=config.entryImagePreloadMap;"
            "if(!preloadMap||typeof preloadMap!=='object'){return;}"
            "var pathname=(window.location&&typeof window.location.pathname==='string')?window.location.pathname:'';"
            "if(!pathname){return;}"
            "var decodedPathname=pathname;"
            "try{decodedPathname=decodeURIComponent(pathname);}catch(_){decodedPathname=pathname;}"
            "var normalizedPath=decodedPathname.trim().toLowerCase().replace(/^\\/+|\\/+$/g,'');"
            "if(!normalizedPath){return;}"
            "var assetPublicId=preloadMap[normalizedPath];"
            "if(typeof assetPublicId!=='string'||!assetPublicId.trim()){return;}"
            "var href='/api/public/assets/'+encodeURIComponent(assetPublicId.trim().toLowerCase());"
            'document.write(\'<link rel="preload" as="image" fetchpriority="high" href="\'+href+\'" data-mos-entry-preload="true">\');'
            "})();"
            "</script>"
        )
        block = (
            "<!-- MOS_DEPLOY_RUNTIME_START -->"
            f"{runtime_script}"
            "<!-- MOS_DEPLOY_RUNTIME_END -->"
        )
        script = (
            "import pathlib\n"
            f"index_path = pathlib.Path({(site_dir + '/index.html')!r})\n"
            "if not index_path.exists():\n"
            "    raise SystemExit(0)\n"
            f"block = {block!r}\n"
            "start_marker = '<!-- MOS_DEPLOY_RUNTIME_START -->'\n"
            "end_marker = '<!-- MOS_DEPLOY_RUNTIME_END -->'\n"
            "raw = index_path.read_text(encoding='utf-8')\n"
            "if start_marker in raw and end_marker in raw:\n"
            "    start_idx = raw.index(start_marker)\n"
            "    end_idx = raw.index(end_marker) + len(end_marker)\n"
            "    raw = raw[:start_idx] + block + raw[end_idx:]\n"
            "elif '<script type=\"module\"' in raw:\n"
            "    raw = raw.replace('<script type=\"module\"', block + '<script type=\"module\"', 1)\n"
            "elif '</head>' in raw:\n"
            "    raw = raw.replace('</head>', block + '</head>', 1)\n"
            "else:\n"
            "    raw = block + raw\n"
            "index_path.write_text(raw, encoding='utf-8')\n"
        )
        remote_script_path = f"/tmp/cloudhand-runtime-config-{int(time.time() * 1000)}.py"
        self.upload_file(script, remote_script_path)
        try:
            self.run(f"python3 {shlex.quote(remote_script_path)}")
        finally:
            self.run(f"rm -f {shlex.quote(remote_script_path)}")

    def _resolve_funnel_artifact_payload_sections(
        self,
        *,
        source: FunnelArtifactSourceSpec,
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, object],
        dict[str, object],
    ]:
        artifact = source.artifact or {}
        meta = artifact.get("meta")
        products = artifact.get("products")
        assets = artifact.get("assets")
        if not isinstance(meta, dict):
            raise ValueError("source_ref.artifact.meta must be an object.")
        if not isinstance(products, dict):
            raise ValueError("source_ref.artifact.products must be an object.")

        if assets is not None and not isinstance(assets, dict):
            raise ValueError("source_ref.artifact.assets must be an object when provided.")

        asset_items: dict[str, object] = {}
        static_asset_items: dict[str, object] = {}
        if isinstance(assets, dict):
            raw_items = assets.get("items")
            if raw_items is None:
                asset_items = {}
            elif isinstance(raw_items, dict):
                asset_items = raw_items
            else:
                raise ValueError(
                    "source_ref.artifact.assets.items must be an object when provided."
                )
            raw_static_items = assets.get("staticItems")
            if raw_static_items is None:
                static_asset_items = {}
            elif isinstance(raw_static_items, dict):
                static_asset_items = raw_static_items
            else:
                raise ValueError(
                    "source_ref.artifact.assets.staticItems must be an object when provided."
                )

        return artifact, meta, products, asset_items, static_asset_items

    def _write_funnel_artifact_assets(
        self,
        *,
        site_dir: str,
        source: FunnelArtifactSourceSpec,
        uploaded_target_paths: set[str] | None = None,
        standalone_served_assets: dict[str, _StandaloneServedAsset] | None = None,
        standalone_image_sources: dict[str, _StandaloneImageSource] | None = None,
    ) -> None:
        (
            _artifact,
            _meta,
            _products,
            asset_items,
            static_asset_items,
        ) = self._resolve_funnel_artifact_payload_sections(source=source)

        assets_roots = (
            f"{site_dir}/api/public/assets",
            f"{site_dir}/public/assets",
        )
        for assets_root in assets_roots:
            self.run(f"mkdir -p {shlex.quote(assets_root)}")
        for raw_public_id, raw_asset_payload in asset_items.items():
            public_id = str(raw_public_id or "").strip().lower()
            if not public_id:
                raise ValueError("Artifact assets.items keys must be non-empty UUID strings.")
            try:
                normalized_public_id = str(UUID(public_id))
            except ValueError as exc:
                raise ValueError(f"Invalid artifact asset public id '{public_id}'.") from exc
            if not isinstance(raw_asset_payload, dict):
                raise ValueError(
                    f"Artifact asset payload for '{normalized_public_id}' must be an object."
                )
            raw_content_type = raw_asset_payload.get("contentType")
            if not isinstance(raw_content_type, str) or not raw_content_type.strip():
                raise ValueError(
                    f"Artifact asset '{normalized_public_id}' must include non-empty contentType."
                )
            content_type = raw_content_type.strip().lower()
            if not content_type.startswith("image/"):
                raise ValueError(
                    f"Artifact asset '{normalized_public_id}' has unsupported contentType '{raw_content_type}'."
                )
            raw_bytes_base64 = raw_asset_payload.get("bytesBase64")
            if not isinstance(raw_bytes_base64, str) or not raw_bytes_base64.strip():
                raise ValueError(
                    f"Artifact asset '{normalized_public_id}' must include non-empty bytesBase64."
                )
            try:
                decoded_bytes = base64.b64decode(raw_bytes_base64, validate=True)
            except binascii.Error as exc:
                raise ValueError(
                    f"Artifact asset '{normalized_public_id}' has invalid bytesBase64."
                ) from exc
            if not decoded_bytes:
                raise ValueError(f"Artifact asset '{normalized_public_id}' decoded to empty bytes.")
            declared_size = raw_asset_payload.get("sizeBytes")
            if declared_size is not None:
                if not isinstance(declared_size, int) or declared_size < 0:
                    raise ValueError(
                        f"Artifact asset '{normalized_public_id}' sizeBytes must be a non-negative integer."
                    )
                if declared_size != len(decoded_bytes):
                    raise ValueError(
                        f"Artifact asset '{normalized_public_id}' sizeBytes ({declared_size}) does not match decoded byte length ({len(decoded_bytes)})."
                    )
            extension = ""
            if content_type == "image/webp":
                extension = ".webp"
            elif content_type in {"image/jpeg", "image/jpg"}:
                extension = ".jpg"
            elif content_type == "image/png":
                extension = ".png"
            for assets_root in assets_roots:
                target_path = f"{assets_root}/{normalized_public_id}{extension}"
                if uploaded_target_paths is None or target_path not in uploaded_target_paths:
                    self.upload_bytes(decoded_bytes, target_path)
                    if uploaded_target_paths is not None:
                        uploaded_target_paths.add(target_path)
            if standalone_served_assets is not None:
                self._register_standalone_served_asset(
                    served_assets=standalone_served_assets,
                    route_path=f"/public/assets/{normalized_public_id}",
                    payload=decoded_bytes,
                    content_type=content_type,
                    context_label=f"Artifact asset '{normalized_public_id}'",
                )
            if standalone_image_sources is not None:
                self._register_standalone_image_source(
                    image_sources=standalone_image_sources,
                    route_path=f"/public/assets/{normalized_public_id}",
                    payload=decoded_bytes,
                    content_type=content_type,
                    context_label=f"Artifact asset '{normalized_public_id}'",
                )

        allowed_static_prefixes = (
            "/_standalone-assets/",
            "/assets/",
            "/cdn/shop/files/",
            "/favicon",
        )
        route_scoped_static_asset_re = re.compile(
            r"^/[A-Za-z0-9][A-Za-z0-9_-]*"
            r"/[A-Za-z0-9][A-Za-z0-9_-]*"
            r"/[A-Za-z0-9][A-Za-z0-9_-]*/assets/"
        )
        product_scoped_static_asset_re = re.compile(r"^/[A-Za-z0-9][A-Za-z0-9_-]*/assets/")
        for raw_asset_path, raw_asset_payload in static_asset_items.items():
            asset_path = str(raw_asset_path or "").strip()
            has_allowed_static_prefix = any(
                asset_path.lower().startswith(prefix) for prefix in allowed_static_prefixes
            )
            has_route_scoped_static_prefix = (
                route_scoped_static_asset_re.match(asset_path) is not None
            )
            has_product_scoped_static_prefix = (
                product_scoped_static_asset_re.match(asset_path) is not None
            )
            if (
                not asset_path.startswith("/")
                or "://" in asset_path
                or asset_path.startswith("//")
                or "?" in asset_path
                or "#" in asset_path
                or posixpath.normpath(asset_path) != asset_path
                or (
                    not has_allowed_static_prefix
                    and not has_route_scoped_static_prefix
                    and not has_product_scoped_static_prefix
                )
            ):
                raise ValueError(
                    f"Invalid artifact static asset path '{asset_path}'. Expected a normalized "
                    "same-origin path under /assets/, /cdn/shop/files/, /favicon, or "
                    "/<product>/assets/ or /<product>/<funnel>/<page>/assets/."
                )
            if not isinstance(raw_asset_payload, dict):
                raise ValueError(
                    f"Artifact static asset payload for '{asset_path}' must be an object."
                )
            raw_content_type = raw_asset_payload.get("contentType")
            if not isinstance(raw_content_type, str) or not raw_content_type.strip():
                raise ValueError(
                    f"Artifact static asset '{asset_path}' must include non-empty contentType."
                )
            content_type = raw_content_type.strip().lower()
            raw_bytes_base64 = raw_asset_payload.get("bytesBase64")
            if not isinstance(raw_bytes_base64, str) or not raw_bytes_base64.strip():
                raise ValueError(f"Artifact static asset '{asset_path}' must include bytesBase64.")
            try:
                decoded_bytes = base64.b64decode(raw_bytes_base64, validate=True)
            except binascii.Error as exc:
                raise ValueError(
                    f"Artifact static asset '{asset_path}' has invalid bytesBase64."
                ) from exc
            if not decoded_bytes:
                raise ValueError(f"Artifact static asset '{asset_path}' decoded to empty bytes.")
            declared_size = raw_asset_payload.get("sizeBytes")
            if declared_size is not None:
                if not isinstance(declared_size, int) or declared_size < 0:
                    raise ValueError(
                        f"Artifact static asset '{asset_path}' sizeBytes must be a non-negative integer."
                    )
                if declared_size != len(decoded_bytes):
                    raise ValueError(
                        f"Artifact static asset '{asset_path}' sizeBytes ({declared_size}) does not match decoded byte length ({len(decoded_bytes)})."
                    )
            declared_sha256 = str(raw_asset_payload.get("sha256") or "").strip().lower()
            actual_sha256 = hashlib.sha256(decoded_bytes).hexdigest()
            if declared_sha256 and declared_sha256 != actual_sha256:
                raise ValueError(
                    f"Artifact static asset '{asset_path}' sha256 does not match bytes."
                )

            target_path = f"{site_dir}{asset_path}"
            if uploaded_target_paths is None or target_path not in uploaded_target_paths:
                self.upload_bytes(decoded_bytes, target_path)
                if uploaded_target_paths is not None:
                    uploaded_target_paths.add(target_path)
            if standalone_served_assets is not None:
                self._register_standalone_served_asset(
                    served_assets=standalone_served_assets,
                    route_path=asset_path,
                    payload=decoded_bytes,
                    content_type=content_type,
                    context_label=f"Artifact static asset '{asset_path}'",
                )
            if standalone_image_sources is not None and content_type.startswith("image/"):
                self._register_standalone_image_source(
                    image_sources=standalone_image_sources,
                    route_path=asset_path,
                    payload=decoded_bytes,
                    content_type=content_type,
                    context_label=f"Artifact static asset '{asset_path}'",
                )

    def _extract_standalone_imported_html_props(
        self,
        *,
        product_slug: str,
        funnel_slug: str,
        page_slug: str,
        page_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        context_label = f"Artifact funnel '{product_slug}/{funnel_slug}/{page_slug}'"
        puck_data = page_payload.get("puckData")
        if not isinstance(puck_data, dict):
            raise ValueError(f"{context_label} puckData must be an object for HTML deploy export.")

        content = puck_data.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise ValueError(
                f"{context_label} must contain exactly one HTML deploy-supported content block for HTML deploy export."
            )

        block = content[0]
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            raise ValueError(
                f"{context_label} must contain a HTML deploy-supported content block for HTML deploy export."
            )
        if block.get("type") != "ImportedHtmlDocument":
            raise ValueError(
                f"{context_label} must contain an ImportedHtmlDocument block for HTML deploy export."
            )

        props = block.get("props")
        if not isinstance(props, dict):
            raise ValueError(
                f"{context_label} ImportedHtmlDocument.props must be an object for HTML deploy export."
            )

        html_document = props.get("htmlDocument")
        if not isinstance(html_document, str) or not html_document.strip():
            raise ValueError(
                f"{context_label} ImportedHtmlDocument.props.htmlDocument must be a non-empty string."
            )

        from app.services.imported_html_runtime import coerce_imported_html_instrumentation_manifest

        try:
            instrumentation_manifest = coerce_imported_html_instrumentation_manifest(
                props.get("instrumentationManifest")
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{context_label} ImportedHtmlDocument.props.instrumentationManifest is required "
                f"and must be valid for HTML deploy export. {exc}"
            ) from exc

        return {
            **props,
            "htmlDocument": html_document,
            "instrumentationManifest": instrumentation_manifest,
        }

    def _extract_standalone_compliance_page_props(
        self,
        *,
        product_slug: str,
        funnel_slug: str,
        page_slug: str,
        page_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        context_label = f"Artifact funnel '{product_slug}/{funnel_slug}/{page_slug}'"
        puck_data = page_payload.get("puckData")
        if not isinstance(puck_data, dict):
            raise ValueError(f"{context_label} puckData must be an object for HTML deploy export.")

        content = puck_data.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise ValueError(
                f"{context_label} must contain exactly one HTML deploy-supported content block for HTML deploy export."
            )

        block = content[0]
        if not isinstance(block, dict) or block.get("type") != "FunnelCompliancePage":
            raise ValueError(
                f"{context_label} must contain a FunnelCompliancePage block for standalone compliance export."
            )

        props = block.get("props")
        if not isinstance(props, dict):
            raise ValueError(
                f"{context_label} FunnelCompliancePage.props must be an object for standalone compliance export."
            )

        page_key = str(props.get("pageKey") or "").strip()
        if not page_key:
            raise ValueError(
                f"{context_label} FunnelCompliancePage.props.pageKey must be a non-empty string."
            )

        return {
            **props,
            "pageKey": page_key,
            "pageTitle": str(props.get("pageTitle") or "").strip() or None,
        }

    def _resolve_standalone_public_funnel_token(
        self,
        *,
        funnel_slug: str,
        funnel_meta: Dict[str, Any],
    ) -> str:
        for token in self._resolve_funnel_path_tokens(
            product_slug="__product__",
            funnel_slug=funnel_slug,
            funnel_meta=funnel_meta,
        ):
            if _SHORT_UUID_TOKEN_PATTERN.fullmatch(str(token or "").strip()):
                return str(token).strip()
        return funnel_slug

    def _fetch_standalone_compliance_policy_page(
        self,
        *,
        upstream_api_base_root: str,
        product_slug: str,
        public_funnel_token: str,
        page_key: str,
        website_url: str,
    ) -> Dict[str, Any]:
        normalized_api_base_root = str(upstream_api_base_root or "").strip().rstrip("/")
        if not normalized_api_base_root.startswith(("http://", "https://")):
            raise ValueError(
                "Standalone compliance export requires source_ref.upstream_api_base_root to be an absolute http(s) URL."
            )

        relative_path = (
            f"/public/funnels/{quote(product_slug, safe='')}/{quote(public_funnel_token, safe='')}"
            f"/policy-pages/{quote(page_key, safe='')}"
        )
        query = urlencode({"website_url": website_url})
        request = Request(
            f"{normalized_api_base_root}{relative_path}?{query}",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(
                request, timeout=30
            ) as response:  # noqa: S310 - controlled deploy-time fetch
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore").strip()
            raise ValueError(
                "Standalone compliance export failed to fetch "
                f"'{page_key}' from {relative_path}: HTTP {exc.code}"
                + (f" ({detail})" if detail else "")
            ) from exc
        except URLError as exc:
            raise ValueError(
                f"Standalone compliance export failed to fetch '{page_key}' from {relative_path}: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Standalone compliance export received invalid JSON for '{page_key}' from {relative_path}."
            ) from exc

        title = payload.get("title")
        markdown = payload.get("markdown")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                f"Standalone compliance export received an invalid title for '{page_key}' from {relative_path}."
            )
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError(
                f"Standalone compliance export received empty markdown for '{page_key}' from {relative_path}."
            )
        return {
            "title": title.strip(),
            "markdown": markdown,
        }

    def _render_standalone_compliance_page_html(
        self,
        *,
        product_slug: str,
        funnel_slug: str,
        funnel_meta: Dict[str, Any],
        funnel_path_token: str,
        page_slug: str,
        page_payload: Dict[str, Any],
        funnel_payload: Dict[str, Any],
        source: FunnelArtifactSourceSpec,
        public_server_names: list[str],
        supporting_imported_html_documents: dict[str, str],
    ) -> str:
        context_label = f"Artifact funnel '{product_slug}/{funnel_slug}/{page_slug}'"
        props = self._extract_standalone_compliance_page_props(
            product_slug=product_slug,
            funnel_slug=funnel_slug,
            page_slug=page_slug,
            page_payload=page_payload,
        )

        page_id = str(page_payload.get("pageId") or "").strip()
        if not page_id:
            raise ValueError(
                f"{context_label} pageId is required for standalone compliance export."
            )

        page_map = page_payload.get("pageMap")
        if not isinstance(page_map, dict) or not page_map:
            raise ValueError(
                f"{context_label} pageMap is required for standalone compliance export."
            )
        page_stage_map = page_payload.get("pageStageMap")
        if not isinstance(page_stage_map, dict) or not page_stage_map:
            raise ValueError(
                f"{context_label} pageStageMap is required for standalone compliance export."
            )

        page_path_by_id = self._build_standalone_imported_html_page_paths(
            product_slug=product_slug,
            funnel_path_token=funnel_path_token,
            page_map=page_map,
        )
        if not page_path_by_id:
            raise ValueError(
                f"{context_label} could not resolve any page paths for standalone compliance export."
            )

        page_path_by_slug: Dict[str, str] = {}
        for raw_page_id, raw_page_slug in page_map.items():
            resolved_page_id = str(raw_page_id or "").strip()
            canonical_page_slug = self._canonical_funnel_artifact_page_slug(raw_page_slug)
            resolved_path = page_path_by_id.get(resolved_page_id)
            if resolved_page_id and canonical_page_slug and resolved_path:
                page_path_by_slug[canonical_page_slug] = resolved_path

        sales_page_id = next(
            (
                str(raw_page_id or "").strip()
                for raw_page_id, raw_stage in page_stage_map.items()
                if str(raw_stage or "").strip() == "sales"
            ),
            "",
        )
        shop_path = (
            page_path_by_id.get(sales_page_id)
            or page_path_by_slug.get("sales-page")
            or page_path_by_slug.get("presales")
            or next(iter(page_path_by_id.values()), None)
            or f"/{quote(product_slug, safe='')}/{quote(funnel_path_token, safe='')}/"
        )

        public_funnel_token = self._resolve_standalone_public_funnel_token(
            funnel_slug=funnel_slug,
            funnel_meta=funnel_meta,
        )
        policy_api_path = (
            f"/api/public/funnels/{quote(product_slug, safe='')}/{quote(public_funnel_token, safe='')}"
            f"/policy-pages/{quote(str(props['pageKey']), safe='')}"
        )
        design_system_tokens = page_payload.get("designSystemTokens")
        if not isinstance(design_system_tokens, dict):
            design_system_tokens = {}
        brand_tokens = design_system_tokens.get("brand")
        if not isinstance(brand_tokens, dict):
            brand_tokens = {}
        support_email_override = (
            str(props.get("supportEmail") or "").strip()
            or str(brand_tokens.get("supportEmail") or "").strip()
        )
        page_title = str(props.get("pageTitle") or props["pageKey"]).strip() or "Policy"

        footer_terms = page_path_by_slug.get("terms-of-service", "#")
        footer_privacy = page_path_by_slug.get("privacy-policy", "#")
        footer_refund = page_path_by_slug.get("refund-policy", "#")
        footer_contact = page_path_by_slug.get("contact-us", "#")
        pages = funnel_payload.get("pages")
        if not isinstance(pages, dict):
            raise ValueError(
                f"{context_label} funnel pages are required for standalone compliance export."
            )

        supporting_page_slug = (
            "sales-page"
            if "sales-page" in supporting_imported_html_documents
            else "presales" if "presales" in supporting_imported_html_documents else ""
        )
        if not supporting_page_slug:
            for candidate_slug, candidate_payload in pages.items():
                if not isinstance(candidate_payload, dict):
                    continue
                candidate_puck_data = candidate_payload.get("puckData")
                candidate_content = (
                    candidate_puck_data.get("content")
                    if isinstance(candidate_puck_data, dict)
                    else None
                )
                candidate_block = (
                    candidate_content[0]
                    if isinstance(candidate_content, list)
                    and len(candidate_content) == 1
                    and isinstance(candidate_content[0], dict)
                    else None
                )
                if str(candidate_block.get("type") or "").strip() == "ImportedHtmlDocument":
                    supporting_page_slug = str(candidate_slug or "").strip()
                    break

        supporting_html_document = supporting_imported_html_documents.get(supporting_page_slug)
        if not supporting_page_slug or not supporting_html_document:
            raise ValueError(
                f"{context_label} requires a supporting ImportedHtmlDocument sales or presales page for standalone compliance export."
            )

        supporting_head_html = _sanitize_supporting_page_head_html(
            supporting_html_document=supporting_html_document,
            page_title=page_title,
        )
        supporting_body_opening_tag = _extract_html_document_body_opening_tag(
            supporting_html_document
        )
        if supporting_body_opening_tag is None:
            raise ValueError(
                f"{context_label} supporting imported HTML page must contain a <body> element."
            )
        supporting_header_html = _extract_first_html_tag_block(supporting_html_document, "header")
        if supporting_header_html is None:
            raise ValueError(
                f"{context_label} supporting imported HTML page must contain a <header> element."
            )
        supporting_footer_html = _extract_last_html_tag_block(supporting_html_document, "footer")
        if supporting_footer_html is None:
            raise ValueError(
                f"{context_label} supporting imported HTML page must contain a <footer> element."
            )

        supporting_header_html = _rewrite_standalone_compliance_navigation_links(
            html_fragment=supporting_header_html,
            shop_path=shop_path,
            footer_terms=footer_terms,
            footer_privacy=footer_privacy,
            footer_refund=footer_refund,
            footer_contact=footer_contact,
        )
        supporting_footer_html = _rewrite_standalone_compliance_navigation_links(
            html_fragment=supporting_footer_html,
            shop_path=shop_path,
            footer_terms=footer_terms,
            footer_privacy=footer_privacy,
            footer_refund=footer_refund,
            footer_contact=footer_contact,
        )

        page_title_json = _safe_inline_json(page_title)
        policy_api_path_json = _safe_inline_json(policy_api_path)
        shop_path_json = _safe_inline_json(shop_path)
        support_email_override_json = _safe_inline_json(
            support_email_override
            if support_email_override and "@" in support_email_override
            else None
        )

        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    {supporting_head_html}
    <style>
      .mos-standalone-compliance-root {{
        min-height: 100vh;
        display: flex;
        flex-direction: column;
      }}
      .mos-standalone-compliance-main {{
        flex: 1;
        width: 100%;
        padding: 48px 16px 72px;
      }}
      .mos-standalone-compliance-container {{
        max-width: 880px;
        margin: 0 auto;
      }}
      .mos-standalone-compliance-card {{
        background-color: rgba(255, 255, 255, 0.96);
        border: 1px solid rgba(15, 15, 15, 0.12);
        border-radius: 16px;
        padding: 40px clamp(24px, 4vw, 56px);
        box-shadow: 0 8px 24px rgba(15, 15, 15, 0.08);
      }}
      .mos-standalone-compliance-content h1,
      .mos-standalone-compliance-content h2 {{
        color: #0F0F0F;
        letter-spacing: -0.02em;
      }}
      .mos-standalone-compliance-content h1 {{
        font-size: clamp(36px, 5vw, 48px);
        font-weight: 700;
        margin: 0 0 28px;
        line-height: 1.15;
      }}
      .mos-standalone-compliance-content h2 {{
        font-size: 22px;
        font-weight: 700;
        margin: 36px 0 14px;
        line-height: 1.25;
        color: #E51E25;
        letter-spacing: 0.01em;
        text-transform: uppercase;
      }}
      .mos-standalone-compliance-content p,
      .mos-standalone-compliance-content li {{
        font-size: 17px;
        line-height: 1.65;
        color: #191919;
        font-weight: 400;
      }}
      .mos-standalone-compliance-content a {{
        color: #E51E25;
        text-decoration: underline;
        text-underline-offset: 2px;
      }}
      .mos-standalone-compliance-content p {{ margin: 0 0 14px; }}
      .mos-standalone-compliance-content ul {{ margin: 0 0 18px; padding-left: 22px; }}
      .mos-standalone-compliance-content li {{ margin-bottom: 8px; }}
      .mos-standalone-compliance-content strong {{ color: #0F0F0F; font-weight: 700; }}
      .mos-standalone-compliance-loading {{
        color: rgba(25, 25, 25, 0.72);
      }}
      .mos-standalone-compliance-error {{
        color: #9F1D1D;
      }}
      @media (min-width: 768px) {{
        .mos-standalone-compliance-main {{ padding: 64px 32px 96px; }}
      }}
    </style>
  </head>
  {supporting_body_opening_tag}
    <div class="mos-standalone-compliance-root">
      {supporting_header_html}
      <main class="mos-standalone-compliance-main">
        <div class="mos-standalone-compliance-container">
          <article
            id="mos-standalone-policy-content"
            class="mos-standalone-compliance-card mos-standalone-compliance-content"
          >
            <h1>{escape(page_title)}</h1>
            <p class="mos-standalone-compliance-loading">Loading policy content...</p>
          </article>
        </div>
      </main>
      {supporting_footer_html}
    </div>
    <script>
      (() => {{
        const article = document.getElementById("mos-standalone-policy-content");
        const fallbackTitle = {page_title_json};
        const policyApiPath = {policy_api_path_json};
        const shopPath = {shop_path_json};
        const supportEmailOverride = {support_email_override_json};

        async function run() {{
          if (!article) return;

          try {{
            const params = new URLSearchParams();
            params.set("website_url", `${{window.location.origin}}${{shopPath}}`);
            if (typeof supportEmailOverride === "string" && supportEmailOverride) {{
              params.set("support_email", supportEmailOverride);
            }}

            const response = await fetch(`${{policyApiPath}}?${{params.toString()}}`, {{
              headers: {{ Accept: "application/json" }},
            }});
            if (!response.ok) {{
              throw new Error(`HTTP ${{response.status}}`);
            }}

            const payload = await response.json();
            const title = String(payload.title || fallbackTitle || "").trim() || fallbackTitle;
            const html = typeof payload.html === "string" ? payload.html.trim() : "";
            if (!html) {{
              throw new Error("Missing policy html");
            }}

            document.title = title;
            article.innerHTML = html;
          }} catch (_error) {{
            article.innerHTML =
              `<h1>${{fallbackTitle}}</h1>` +
              '<p class="mos-standalone-compliance-error">We couldn\\'t load this policy page right now.</p>' +
              `<p><a href="${{shopPath}}">Return to the sales page</a></p>`;
          }}
        }}

        run();
      }})();
    </script>
  </body>
</html>
"""

    def _serialize_standalone_imported_html_variants(
        self,
        *,
        funnel_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        commerce = funnel_payload.get("commerce")
        if not isinstance(commerce, dict):
            return []
        product = commerce.get("product")
        if not isinstance(product, dict):
            return []
        raw_variants = product.get("variants")
        if not isinstance(raw_variants, list):
            return []

        serialized_variants: List[Dict[str, Any]] = []
        for raw_variant in raw_variants:
            if not isinstance(raw_variant, dict):
                continue
            variant_id = str(raw_variant.get("id") or "").strip()
            if not variant_id:
                continue

            provider = raw_variant.get("provider")
            normalized_provider = (
                str(provider).strip().lower()
                if isinstance(provider, str) and provider.strip()
                else None
            )
            currency = raw_variant.get("currency")
            normalized_currency = (
                str(currency).strip() if isinstance(currency, str) and currency.strip() else None
            )
            price = raw_variant.get("price")
            normalized_price = price if isinstance(price, (int, float)) else None
            option_values = raw_variant.get("option_values")
            normalized_option_values: Dict[str, str] = {}
            if isinstance(option_values, dict):
                for raw_key, raw_value in option_values.items():
                    key = str(raw_key or "").strip()
                    value = str(raw_value or "").strip()
                    if key and value:
                        normalized_option_values[key] = value

            serialized_variants.append(
                {
                    "id": variant_id,
                    "provider": normalized_provider,
                    "price": normalized_price,
                    "currency": normalized_currency,
                    "optionValues": normalized_option_values,
                }
            )
        return serialized_variants

    def _render_standalone_funnel_artifact_page(
        self,
        *,
        site_dir: str,
        product_slug: str,
        funnel_slug: str,
        funnel_meta: Dict[str, Any],
        funnel_path_token: str,
        page_slug: str,
        page_payload: Dict[str, Any],
        funnel_payload: Dict[str, Any],
        source: FunnelArtifactSourceSpec,
        public_server_names: list[str],
        mirrored_url_map: dict[str, str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
        prepared_imported_html_document: str | None = None,
        prepared_imported_html_documents: dict[str, str] | None = None,
    ) -> str:
        puck_data = page_payload.get("puckData")
        content = puck_data.get("content") if isinstance(puck_data, dict) else None
        block = (
            content[0]
            if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
            else None
        )
        block_type = str(block.get("type") or "").strip() if isinstance(block, dict) else ""

        if block_type == "ImportedHtmlDocument":
            return self._inject_standalone_imported_html_bridge(
                site_dir=site_dir,
                product_slug=product_slug,
                funnel_slug=funnel_slug,
                funnel_path_token=funnel_path_token,
                page_slug=page_slug,
                page_payload=page_payload,
                funnel_payload=funnel_payload,
                server_names=public_server_names,
                mirrored_url_map=mirrored_url_map,
                mirrored_target_paths=mirrored_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
                prepared_html_document=prepared_imported_html_document,
                upstream_api_base_root=str(source.upstream_api_base_root or ""),
            )
        if block_type == "FunnelCompliancePage":
            return self._render_standalone_compliance_page_html(
                product_slug=product_slug,
                funnel_slug=funnel_slug,
                funnel_meta=funnel_meta,
                funnel_path_token=funnel_path_token,
                page_slug=page_slug,
                page_payload=page_payload,
                funnel_payload=funnel_payload,
                source=source,
                public_server_names=public_server_names,
                supporting_imported_html_documents=prepared_imported_html_documents or {},
            )

        raise ValueError(
            f"Artifact funnel '{product_slug}/{funnel_slug}/{page_slug}' uses unsupported standalone page block type '{block_type or 'unknown'}'."
        )

    def _build_standalone_imported_html_page_paths(
        self,
        *,
        product_slug: str,
        funnel_path_token: str,
        page_map: Dict[str, Any],
    ) -> Dict[str, str]:
        page_paths: Dict[str, str] = {}
        product_path = quote(product_slug, safe="")
        funnel_path = quote(funnel_path_token, safe="")
        for raw_page_id, raw_slug in page_map.items():
            page_id = str(raw_page_id or "").strip()
            canonical_page_slug = self._canonical_funnel_artifact_page_slug(raw_slug)
            if not page_id or not canonical_page_slug:
                continue
            page_paths[page_id] = (
                f"/{product_path}/{funnel_path}/{quote(canonical_page_slug, safe='')}/"
            )
        return page_paths

    def _inject_standalone_imported_html_bridge(
        self,
        *,
        site_dir: str,
        product_slug: str,
        funnel_slug: str,
        funnel_path_token: str,
        page_slug: str,
        page_payload: Dict[str, Any],
        funnel_payload: Dict[str, Any],
        server_names: list[str],
        mirrored_url_map: dict[str, str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
        prepared_html_document: str | None = None,
        upstream_api_base_root: str | None = None,
    ) -> str:
        context_label = f"Artifact funnel '{product_slug}/{funnel_slug}/{page_slug}'"
        props = self._extract_standalone_imported_html_props(
            product_slug=product_slug,
            funnel_slug=funnel_slug,
            page_slug=page_slug,
            page_payload=page_payload,
        )

        page_id = str(page_payload.get("pageId") or "").strip()
        if not page_id:
            raise ValueError(f"{context_label} pageId is required for HTML deploy export.")
        funnel_meta = funnel_payload.get("meta")
        funnel_publication_id = (
            str(funnel_meta.get("publicationId") or "").strip()
            if isinstance(funnel_meta, dict)
            else ""
        )
        publication_id = (
            funnel_publication_id or str(page_payload.get("publicationId") or "").strip()
        )
        if not publication_id:
            raise ValueError(f"{context_label} publicationId is required for HTML deploy export.")
        page_stage = str(page_payload.get("stage") or "").strip()
        if not page_stage:
            raise ValueError(f"{context_label} stage is required for HTML deploy export.")

        page_map = page_payload.get("pageMap")
        if not isinstance(page_map, dict) or not page_map:
            raise ValueError(f"{context_label} pageMap is required for HTML deploy export.")
        page_stage_map = page_payload.get("pageStageMap")
        if not isinstance(page_stage_map, dict) or not page_stage_map:
            raise ValueError(f"{context_label} pageStageMap is required for HTML deploy export.")

        page_path_by_id = self._build_standalone_imported_html_page_paths(
            product_slug=product_slug,
            funnel_path_token=funnel_path_token,
            page_map=page_map,
        )
        if not page_path_by_id:
            raise ValueError(
                f"{context_label} could not resolve any page paths for HTML deploy export."
            )

        tracking = page_payload.get("tracking")
        if not isinstance(tracking, dict):
            tracking = None

        script_config = {
            "apiBasePath": "/api",
            "productSlug": product_slug,
            "funnelSlug": str(page_payload.get("funnelSlug") or funnel_slug).strip() or funnel_slug,
            "pageId": page_id,
            "pageSlug": page_slug,
            "pageStage": page_stage,
            "funnelId": str(funnel_payload.get("funnelId") or ""),
            "publicationId": publication_id,
            "tracking": tracking,
            "manifest": props["instrumentationManifest"],
            "htmlArtifactKind": props["instrumentationManifest"].get("htmlArtifactKind"),
            "htmlDeploySchemaVersion": props["instrumentationManifest"].get("schemaVersion"),
            "variants": self._serialize_standalone_imported_html_variants(
                funnel_payload=funnel_payload
            ),
            "pagePathById": page_path_by_id,
            "pageStageById": {
                str(raw_key or "").strip(): str(raw_value or "").strip()
                for raw_key, raw_value in page_stage_map.items()
                if str(raw_key or "").strip() and str(raw_value or "").strip()
            },
        }

        runtime_script = """
<script>
(() => {
  const config = __MOS_HTML_DEPLOY_CONFIG__;
  const META_PIXEL_SCRIPT_ID = "mos-meta-pixel-script";
  const META_PIXEL_SCRIPT_SRC = "https://connect.facebook.net/en_US/fbevents.js";
	  const META_PIXEL_DEFER_TIMEOUT_MS = __MOS_STANDALONE_META_PIXEL_DEFER_TIMEOUT_MS__;
	  const POSTHOG_INSTANCE_NAME = "mosFunnel";
		  const META_ATTRIBUTION_WAIT_TIMEOUT_MS = 1500;
		  const META_ATTRIBUTION_WAIT_POLL_MS = 50;
		  const META_EMAIL_HASH_STORAGE_KEY = "mos_meta_em";
		  const TRACKING_NAVIGATION_FLUSH_DELAY_MS = 250;
		  const META_PIXEL_EVENT_LOAD_TIMEOUT_MS = 2000;
		  const META_PIXEL_EVENT_NETWORK_WINDOW_MS = 1500;
		  const POSTHOG_NAVIGATION_EVENT_LOAD_TIMEOUT_MS = 8000;
		  const POSTHOG_NAVIGATION_EVENT_NETWORK_WINDOW_MS = 1000;
			  const SESSION_PARAM = "session_id";
			  const VISITOR_PARAM = "visitor_id";
			  const CLICK_PARAM = "click_id";
			  const LEGACY_SESSION_PARAM = "rmbc_session_id";
			  const LEGACY_VISITOR_PARAM = "rmbc_anonymous_id";
			  const LEGACY_CLICK_PARAM = "rmbc_click_id";
			  const SESSION_PARAM_NAMES = [SESSION_PARAM, LEGACY_SESSION_PARAM];
			  const VISITOR_PARAM_NAMES = [VISITOR_PARAM, LEGACY_VISITOR_PARAM];
			  const CLICK_PARAM_NAMES = [CLICK_PARAM, LEGACY_CLICK_PARAM];
	  const PRESALE_SOURCE_PARAM = "src";
  const PRESALE_SOURCE_VALUE = "presale";
  const EVENTS_ENDPOINT = String(config.apiBasePath || "/api") + "/public/events";
  let pageLifecycleFinalizing = false;

  const cleanText = (value) => {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    return trimmed || null;
  };
  const normalizeText = (value) => String(value || "").replace(/\\s+/g, " ").trim();
  const isRecord = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const isNonEmptyRecord = (value) => isRecord(value) && Object.keys(value).length > 0;
  let metaPixelScriptLoadPromise = null;
  let metaPixelLastTrackedAt = 0;
  const posthogNavigationFlushPromises = [];
  const waitMs = (durationMs) =>
    new Promise((resolve) => {
      window.setTimeout(resolve, Math.max(0, Number(durationMs) || 0));
    });
  const waitForTrackingNavigationFlush = async () => {
    await waitMs(TRACKING_NAVIGATION_FLUSH_DELAY_MS);
    await Promise.allSettled([
      waitForPostHogNavigationEventFlush(),
      waitForMetaPixelTrackedEventFlush(),
    ]);
  };
  const readCookie = (name) => {
    const prefix = String(name || "") + "=";
    const match = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix));
    return match ? cleanText(match.slice(prefix.length)) : null;
  };
  const assignCleanProp = (target, key, value) => {
    const cleaned = cleanText(value);
    if (cleaned) target[key] = cleaned;
  };
  const assignNumberProp = (target, key, value) => {
    if (value === null || value === undefined || value === "") return;
    const numberValue = Number(value);
    if (Number.isFinite(numberValue)) target[key] = numberValue;
  };
  const assignBooleanProp = (target, key, value) => {
    if (typeof value === "boolean") target[key] = value;
  };
  const assignStringListProp = (target, key, value) => {
    if (!Array.isArray(value)) return;
    const cleaned = value.map((item) => cleanText(item)).filter(Boolean);
    if (cleaned.length) target[key] = cleaned;
  };
  const readFirstSearchParam = (searchParams, names) => {
    if (!searchParams || !Array.isArray(names)) return null;
    for (const name of names) {
      const value = cleanText(searchParams.get(name));
      if (value) return value;
    }
    return null;
  };
  const buildDeclaredTargetProps = (target) => {
    const props = {};
    if (!target || typeof target !== "object") return props;
    assignCleanProp(props, "quizId", target.quizId);
    assignCleanProp(props, "quiz_id", target.quizId);
    assignCleanProp(props, "quizVersion", target.quizVersion);
    assignCleanProp(props, "quiz_version", target.quizVersion);
    assignCleanProp(props, "quizVariant", target.quizVariant);
    assignCleanProp(props, "quiz_variant", target.quizVariant);
    assignCleanProp(props, "questionId", target.questionId);
    assignCleanProp(props, "question_id", target.questionId);
    assignCleanProp(props, "questionText", target.questionText);
    assignCleanProp(props, "question_text", target.questionText);
    assignNumberProp(props, "questionIndex", target.questionIndex);
    assignNumberProp(props, "question_index", target.questionIndex);
    assignCleanProp(props, "questionType", target.questionType);
    assignCleanProp(props, "question_type", target.questionType);
    assignCleanProp(props, "questionRole", target.questionRole);
    assignCleanProp(props, "question_role", target.questionRole);
    assignBooleanProp(props, "isRequired", target.isRequired);
    assignBooleanProp(props, "is_required", target.isRequired);
    assignCleanProp(props, "optionId", target.optionId);
    assignCleanProp(props, "option_id", target.optionId);
    assignCleanProp(props, "optionText", target.optionText);
    assignCleanProp(props, "option_text", target.optionText);
    assignNumberProp(props, "optionIndex", target.optionIndex);
    assignNumberProp(props, "option_index", target.optionIndex);
    assignNumberProp(props, "optionPosition", target.optionPosition || target.optionIndex);
    assignNumberProp(props, "option_position", target.optionPosition || target.optionIndex);
    assignCleanProp(props, "optionRole", target.optionRole);
    assignCleanProp(props, "option_role", target.optionRole);
    assignNumberProp(props, "selectionOrder", target.selectionOrder);
    assignNumberProp(props, "selection_order", target.selectionOrder);
    assignBooleanProp(props, "submitOnSelect", target.submitOnSelect);
    assignBooleanProp(props, "submit_on_select", target.submitOnSelect);
    assignCleanProp(props, "resultId", target.resultId);
    assignCleanProp(props, "result_id", target.resultId);
    assignCleanProp(props, "segmentId", target.segmentId);
    assignCleanProp(props, "segment_id", target.segmentId);
    assignCleanProp(props, "recommendationId", target.recommendationId);
    assignCleanProp(props, "recommendation_id", target.recommendationId);
    assignCleanProp(props, "answerPathId", target.answerPathId);
    assignCleanProp(props, "answer_path_id", target.answerPathId);
    assignCleanProp(props, "angle", target.angle);
    assignCleanProp(props, "awarenessLevel", target.awarenessLevel);
    assignCleanProp(props, "awareness_level", target.awarenessLevel);
    assignCleanProp(props, "sophisticationLevel", target.sophisticationLevel);
    assignCleanProp(props, "sophistication_level", target.sophisticationLevel);
    assignCleanProp(props, "angleFamily", target.angleFamily);
    assignCleanProp(props, "angle_family", target.angleFamily);
    assignCleanProp(props, "hookId", target.hookId);
    assignCleanProp(props, "hook_id", target.hookId);
    assignCleanProp(props, "promiseId", target.promiseId);
    assignCleanProp(props, "promise_id", target.promiseId);
    assignCleanProp(props, "mechanismName", target.mechanismName);
    assignCleanProp(props, "mechanism_name", target.mechanismName);
    assignCleanProp(props, "offerId", target.offerId);
    assignCleanProp(props, "offer_id", target.offerId);
    assignCleanProp(props, "sku", target.sku);
    assignCleanProp(props, "bundleId", target.bundleId);
    assignCleanProp(props, "bundle_id", target.bundleId);
    assignStringListProp(props, "contentIds", target.contentIds);
    assignStringListProp(props, "content_ids", target.content_ids || target.contentIds);
    assignNumberProp(props, "numItems", target.numItems);
    assignNumberProp(props, "num_items", target.num_items || target.numItems);
    assignCleanProp(props, "pricePoint", target.pricePoint);
    assignCleanProp(props, "price_point", target.pricePoint);
    assignCleanProp(props, "guaranteeId", target.guaranteeId);
    assignCleanProp(props, "guarantee_id", target.guaranteeId);
    assignCleanProp(props, "guaranteeType", target.guaranteeType);
    assignCleanProp(props, "guarantee_type", target.guaranteeType);
    assignCleanProp(props, "guaranteeDuration", target.guaranteeDuration);
    assignCleanProp(props, "guarantee_duration", target.guaranteeDuration);
    assignNumberProp(props, "valueTotal", target.valueTotal);
    assignNumberProp(props, "value_total", target.valueTotal);
    assignNumberProp(props, "actualPrice", target.actualPrice);
    assignNumberProp(props, "actual_price", target.actualPrice);
    assignNumberProp(props, "valueRatio", target.valueRatio);
    assignNumberProp(props, "value_ratio", target.valueRatio);
    assignCleanProp(props, "clickType", target.clickType);
    assignCleanProp(props, "click_type", target.clickType);
    assignCleanProp(props, "targetOfferId", target.targetOfferId);
    assignCleanProp(props, "target_offer_id", target.targetOfferId);
    assignCleanProp(props, "destinationUrl", target.destinationUrl);
    assignCleanProp(props, "destination_url", target.destinationUrl);
    assignCleanProp(props, "elementId", target.elementId);
    assignCleanProp(props, "element_id", target.elementId);
    assignCleanProp(props, "interactionType", target.interactionType);
    assignCleanProp(props, "interaction_type", target.interactionType);
    assignCleanProp(props, "selectedValue", target.selectedValue);
    assignCleanProp(props, "selected_value", target.selectedValue);
    assignBooleanProp(props, "subscriptionFlag", target.subscriptionFlag);
    assignBooleanProp(props, "subscription_flag", target.subscriptionFlag);
    return props;
  };
  const firstManifestTarget = (key) => {
    const manifest = config.manifest && typeof config.manifest === "object" ? config.manifest : {};
    const targets = manifest[key];
    if (!Array.isArray(targets)) return null;
    return targets.find((target) => target && typeof target === "object") || null;
  };
  const mergeMissingProps = (...sources) => {
    const merged = {};
    sources.forEach((source) => {
      if (!source || typeof source !== "object") return;
      Object.entries(source).forEach(([key, value]) => {
        if ((merged[key] === undefined || merged[key] === null || merged[key] === "") && value !== undefined && value !== null && value !== "") {
          merged[key] = value;
        }
      });
    });
    return merged;
  };
  const quizAnswerStateByQuestionId = {};
  const manifestTargets = (key) => {
    const manifest = config.manifest && typeof config.manifest === "object" ? config.manifest : {};
    const targets = manifest[key];
    return Array.isArray(targets) ? targets.filter((target) => target && typeof target === "object") : [];
  };
  const firstCleanProp = (source, names) => {
    if (!source || typeof source !== "object" || !Array.isArray(names)) return null;
    for (const name of names) {
      const value = cleanText(source[name]);
      if (value) return value;
    }
    return null;
  };
  const targetQuestionId = (target) => firstCleanProp(target, ["questionId", "question_id", "id"]);
  const targetOptionId = (target) => firstCleanProp(target, ["optionId", "option_id", "id"]);
  const findQuizQuestionTarget = (questionId) => {
    const normalizedQuestionId = cleanText(questionId);
    if (!normalizedQuestionId) return null;
    const questions = manifestTargets("quizQuestions");
    return questions.find((target) => targetQuestionId(target) === normalizedQuestionId) || null;
  };
  const findQuizOptionTarget = (optionId, questionId) => {
    const normalizedOptionId = cleanText(optionId);
    const normalizedQuestionId = cleanText(questionId);
    const options = manifestTargets("quizOptions");
    if (normalizedOptionId) {
      const match = options.find((target) => (
        targetOptionId(target) === normalizedOptionId &&
        (!normalizedQuestionId || targetQuestionId(target) === normalizedQuestionId)
      ));
      if (match) return match;
    }
    return null;
  };
  const quizOptionTextForId = (questionId, optionId) => {
    const normalizedQuestionId = cleanText(questionId);
    const normalizedOptionId = cleanText(optionId);
    if (!normalizedOptionId) return null;
    const match = manifestTargets("quizOptions").find((target) => (
      targetOptionId(target) === normalizedOptionId &&
      (!normalizedQuestionId || targetQuestionId(target) === normalizedQuestionId)
    ));
    return firstCleanProp(match, ["optionText", "option_text"]);
  };
  const normalizeQuestionType = (value) => {
    const normalized = cleanText(value);
    if (!normalized) return "single_select";
    return normalized.toLowerCase().replace(/[\s-]+/g, "_");
  };
  const isMultiSelectQuestion = (questionTarget, props) => {
    const explicitType = firstCleanProp(props, ["questionType", "question_type"]) ||
      firstCleanProp(questionTarget, ["questionType", "question_type"]);
    const normalizedType = normalizeQuestionType(explicitType);
    return (
      normalizedType === "multi_select" ||
      normalizedType === "multiple_select" ||
      normalizedType === "checkbox" ||
      normalizedType === "checkbox_group"
    );
  };
  const cleanStringArray = (value) => {
    if (!Array.isArray(value)) return [];
    return value.map((item) => cleanText(item)).filter(Boolean);
  };
  const readSelectedOptionIds = (props, optionProps) => {
    const fromProps = cleanStringArray(props && (props.selected_option_ids || props.selectedOptionIds));
    if (fromProps.length) return fromProps;
    const optionId = firstCleanProp(optionProps, ["option_id", "optionId"]);
    return optionId ? [optionId] : [];
  };
  const readSelectedOptionTexts = (props, optionProps, questionId, selectedOptionIds) => {
    const fromProps = cleanStringArray(props && (props.selected_option_texts || props.selectedOptionTexts));
    if (fromProps.length) return fromProps;
    const optionText = firstCleanProp(optionProps, ["option_text", "optionText"]);
    if (optionText) return [optionText];
    return cleanStringArray(selectedOptionIds).map((optionId) => quizOptionTextForId(questionId, optionId) || optionId);
  };
  const buildQuizAnswerSnapshot = (questionId, state) => {
    if (!questionId || !state) return null;
    const selectedOptionIds = cleanStringArray(state.selected_option_ids);
    const selectedOptionTexts = cleanStringArray(state.selected_option_texts);
    return {
      question_id: questionId,
      questionId,
      question_text: cleanText(state.question_text),
      questionText: cleanText(state.question_text),
      question_index: state.question_index,
      questionIndex: state.question_index,
      question_type: cleanText(state.question_type),
      questionType: cleanText(state.question_type),
      selected_option_ids: selectedOptionIds,
      selectedOptionIds: selectedOptionIds,
      selected_option_texts: selectedOptionTexts,
      selectedOptionTexts: selectedOptionTexts,
    };
  };
  const allQuizAnswers = () => Object.keys(quizAnswerStateByQuestionId)
    .map((questionId) => buildQuizAnswerSnapshot(questionId, quizAnswerStateByQuestionId[questionId]))
    .filter(Boolean);
  const answerStateProps = (questionId) => {
    const state = questionId ? quizAnswerStateByQuestionId[questionId] : null;
    const answers = allQuizAnswers();
    const snapshot = buildQuizAnswerSnapshot(questionId, state);
    return {
      ...(snapshot || {}),
      ...(answers.length ? {
        answers,
        answersByQuestion: quizAnswerStateByQuestionId,
        answers_by_question: quizAnswerStateByQuestionId,
        questionCountAnswered: answers.length,
        question_count_answered: answers.length,
      } : {}),
    };
  };
  const updateQuizAnswerState = (eventType, props, questionTarget, optionTarget) => {
    const normalizedEventType = cleanText(eventType);
    const questionProps = buildDeclaredTargetProps(questionTarget);
    const optionProps = buildDeclaredTargetProps(optionTarget);
    const questionId = firstCleanProp(props, ["question_id", "questionId"]) ||
      firstCleanProp(optionProps, ["question_id", "questionId"]) ||
      firstCleanProp(questionProps, ["question_id", "questionId"]);
    if (!questionId) return {};
    const questionText = firstCleanProp(props, ["question_text", "questionText"]) ||
      firstCleanProp(questionProps, ["question_text", "questionText"]);
    const questionIndex = Number(
      (props && (props.question_index || props.questionIndex)) ||
      questionProps.question_index ||
      questionProps.questionIndex ||
      0
    ) || undefined;
    const questionType = normalizeQuestionType(
      firstCleanProp(props, ["question_type", "questionType"]) ||
      firstCleanProp(questionProps, ["question_type", "questionType"])
    );
    const current = quizAnswerStateByQuestionId[questionId] || {
      question_id: questionId,
      question_text: questionText,
      question_index: questionIndex,
      question_type: questionType,
      selected_option_ids: [],
      selected_option_texts: [],
    };
    current.question_text = current.question_text || questionText;
    current.question_index = current.question_index || questionIndex;
    current.question_type = current.question_type || questionType;
    if (
      normalizedEventType === "quiz_option_selected" ||
      normalizedEventType === "QuizOptionSelected"
    ) {
      const selectedOptionIds = readSelectedOptionIds(props, optionProps);
      const selectedOptionTexts = readSelectedOptionTexts(props, optionProps, questionId, selectedOptionIds);
      if (isMultiSelectQuestion(questionTarget, props)) {
        selectedOptionIds.forEach((optionId, index) => {
          if (!current.selected_option_ids.includes(optionId)) {
            current.selected_option_ids.push(optionId);
            current.selected_option_texts.push(selectedOptionTexts[index] || optionId);
          }
        });
      } else {
        current.selected_option_ids = selectedOptionIds;
        current.selected_option_texts = selectedOptionTexts;
      }
      quizAnswerStateByQuestionId[questionId] = current;
    }
    if (
      normalizedEventType === "quiz_option_deselected" ||
      normalizedEventType === "QuizOptionDeselected"
    ) {
      const deselectedIds = readSelectedOptionIds(props, optionProps);
      current.selected_option_ids = current.selected_option_ids.filter((optionId) => !deselectedIds.includes(optionId));
      current.selected_option_texts = current.selected_option_ids.map((optionId, index) => current.selected_option_texts[index] || optionId);
      quizAnswerStateByQuestionId[questionId] = current;
    }
    if (
      normalizedEventType === "quiz_question_submitted" ||
      normalizedEventType === "QuizQuestionSubmitted"
    ) {
      const selectedOptionIds = readSelectedOptionIds(props, optionProps);
      if (selectedOptionIds.length) {
        const selectedOptionTexts = readSelectedOptionTexts(props, optionProps, questionId, selectedOptionIds);
        current.selected_option_ids = selectedOptionIds;
        current.selected_option_texts = selectedOptionTexts;
      }
      quizAnswerStateByQuestionId[questionId] = current;
    }
    return answerStateProps(questionId);
  };
  const resolveQuizManifestEventDefaults = (eventType, props) => {
    if (cleanText(config.htmlArtifactKind) !== "quiz") return {};
    const manifest = config.manifest && typeof config.manifest === "object" ? config.manifest : {};
    const normalizedEventType = cleanText(eventType);
    const quizId = cleanText(manifest.quizId || manifest.quiz_id);
    const quizVersion = cleanText(manifest.quizVersion || manifest.quiz_version);
    const quizVariant = cleanText(manifest.quizVariant || manifest.quiz_variant);
    const quizIdentity = {
      ...(quizId ? { quizId, quiz_id: quizId } : {}),
      ...(quizVersion ? { quizVersion, quiz_version: quizVersion } : {}),
      ...(quizVariant ? { quizVariant, quiz_variant: quizVariant } : {}),
    };
    const leadProps = buildDeclaredTargetProps(firstManifestTarget("quizLeads"));
    const requestedQuestionId = firstCleanProp(props, ["question_id", "questionId"]);
    const requestedOptionId = firstCleanProp(props, ["option_id", "optionId"]);
    const optionTarget = findQuizOptionTarget(requestedOptionId, requestedQuestionId);
    const questionTarget = findQuizQuestionTarget(
      requestedQuestionId ||
        (optionTarget ? firstCleanProp(optionTarget, ["questionId", "question_id"]) : null)
    );
    const questionProps = buildDeclaredTargetProps(questionTarget);
    const optionProps = buildDeclaredTargetProps(optionTarget);
    const resultProps = buildDeclaredTargetProps(firstManifestTarget("quizResults"));
    const recommendationProps = buildDeclaredTargetProps(firstManifestTarget("quizRecommendations"));
    const ctaProps = buildDeclaredTargetProps(firstManifestTarget("ctas"));
    const bindingProps = buildDeclaredTargetProps(firstManifestTarget("bindings"));
    const offerProps = mergeMissingProps(ctaProps, recommendationProps, resultProps);
    const questionCount = Array.isArray(manifest.quizQuestions) ? manifest.quizQuestions.length : 0;
    const completionProps = questionCount > 0
      ? { questionCountAnswered: questionCount, question_count_answered: questionCount }
      : {};
    if (normalizedEventType === "quiz_lead_viewed" || normalizedEventType === "QuizLeadViewed") {
      return mergeMissingProps(quizIdentity, leadProps);
    }
    if (normalizedEventType === "quiz_question_viewed" || normalizedEventType === "QuizQuestionViewed") {
      return mergeMissingProps(quizIdentity, questionProps);
    }
    if (
      normalizedEventType === "quiz_option_presented" ||
      normalizedEventType === "QuizOptionPresented" ||
      normalizedEventType === "quiz_option_selected" ||
      normalizedEventType === "QuizOptionSelected"
    ) {
      return mergeMissingProps(
        quizIdentity,
        questionProps,
        optionProps,
        updateQuizAnswerState(normalizedEventType, props || {}, questionTarget, optionTarget)
      );
    }
    if (normalizedEventType === "quiz_question_submitted" || normalizedEventType === "QuizQuestionSubmitted") {
      return mergeMissingProps(
        quizIdentity,
        questionProps,
        optionProps,
        updateQuizAnswerState(normalizedEventType, props || {}, questionTarget, optionTarget)
      );
    }
    if (normalizedEventType === "quiz_completed" || normalizedEventType === "QuizCompleted") {
      return mergeMissingProps(quizIdentity, resultProps, recommendationProps, answerStateProps(requestedQuestionId), completionProps);
    }
    if (normalizedEventType === "quiz_result_viewed" || normalizedEventType === "QuizResultViewed") {
      return mergeMissingProps(quizIdentity, resultProps);
    }
    if (normalizedEventType === "quiz_recommendation_viewed" || normalizedEventType === "QuizRecommendationViewed") {
      return mergeMissingProps(quizIdentity, recommendationProps, resultProps);
    }
    if (normalizedEventType === "quiz_cta_viewed" || normalizedEventType === "QuizCtaViewed") {
      return mergeMissingProps(quizIdentity, ctaProps, bindingProps, offerProps);
    }
    if (normalizedEventType === "pre_sales_to_sales_click" || normalizedEventType === "PreSalesToSalesClick" || normalizedEventType === "cta_click") {
      return mergeMissingProps(quizIdentity, ctaProps, bindingProps, offerProps, answerStateProps(requestedQuestionId));
    }
    return quizIdentity;
  };
	  const readStoredMetaEmailHash = () => {
	    try {
	      return cleanText(window.localStorage && window.localStorage.getItem(META_EMAIL_HASH_STORAGE_KEY));
	    } catch (_) {
	      return null;
	    }
	  };
	  const resolvePresaleSourcePageType = (source) => {
	    const normalized = cleanText(source);
	    if (!normalized) return null;
	    const value = normalized.toLowerCase().replace(/-/g, "_");
	    if (value === "quiz" || value === "quiz_funnel" || value === "quiz_presell") return "quiz_presell";
	    if (value === "listical" || value === "listicle" || value === "listicle_hybrid" || value === "listical_presell" || value === "listicle_presell") return "listical_presell";
	    if (value === "presale" || value === "presales" || value === "pre_sales") return "presell";
	    return normalized;
	  };
		  const resolvePresaleBridgeContext = (eventSourceUrl, pageStage) => {
	    let currentUrl;
	    try {
	      currentUrl = new URL(cleanText(eventSourceUrl) || window.location.href, window.location.href);
	    } catch (_) {
	      currentUrl = new URL(window.location.href);
	    }
	    const props = {};
	    const resolvedPageStage = cleanText(pageStage);
		    const inboundSessionId = readFirstSearchParam(currentUrl.searchParams, SESSION_PARAM_NAMES);
		    const inboundVisitorId = readFirstSearchParam(currentUrl.searchParams, VISITOR_PARAM_NAMES);
		    const sessionIdValue = inboundSessionId || cleanText(sessionId);
		    const visitorIdValue = inboundVisitorId || cleanText(visitorId);
		    const clickId = readFirstSearchParam(currentUrl.searchParams, CLICK_PARAM_NAMES);
		    assignCleanProp(props, "session_id", sessionIdValue);
		    assignCleanProp(props, "sessionId", sessionIdValue);
		    assignCleanProp(props, "funnel_session_id", sessionIdValue);
		    assignCleanProp(props, "funnelSessionId", sessionIdValue);
		    assignCleanProp(props, "visitor_id", visitorIdValue);
		    assignCleanProp(props, "visitorId", visitorIdValue);
		    assignCleanProp(props, "click_id", clickId);
	    assignCleanProp(props, "clickId", clickId);
	    if (resolvedPageStage === "pre_sales") {
	      const sourcePageType = resolvePresaleSourcePageType(config.htmlArtifactKind);
	      if (!sourcePageType) {
	        throw new Error("HTML deploy pre-sales analytics requires a known htmlArtifactKind.");
	      }
	      assignCleanProp(props, "source_page_type", sourcePageType);
	      assignCleanProp(props, "sourcePageType", sourcePageType);
	      return props;
	    }
	    if (resolvedPageStage !== "sales") return props;
	    const hasPresaleBridge =
	      Boolean(inboundSessionId || inboundVisitorId || clickId) ||
	      currentUrl.searchParams.get(PRESALE_SOURCE_PARAM) === PRESALE_SOURCE_VALUE;
	    if (!hasPresaleBridge) return props;
	    const sourcePageType =
	      resolvePresaleSourcePageType(currentUrl.searchParams.get("source_page_type")) ||
	      resolvePresaleSourcePageType(currentUrl.searchParams.get("from"));
	    assignCleanProp(props, "source_page_type", sourcePageType);
	    assignCleanProp(props, "sourcePageType", sourcePageType);
	    props.from_stage = "pre_sales";
	    props.fromStage = "pre_sales";
	    props.to_stage = "sales";
	    props.toStage = "sales";
	    return props;
	  };
	  const resolveMetaExternalId = () => cleanText(visitorId);
	  const resolveMetaAdvancedMatchingProps = () => {
	    const props = {};
	    assignCleanProp(props, "external_id", resolveMetaExternalId());
	    assignCleanProp(props, "em", readStoredMetaEmailHash());
    return props;
  };
	  const resolveMetaAttributionProps = (eventSourceUrl) => {
	    const props = { action_source: "website" };
		    assignCleanProp(props, "external_id", resolveMetaExternalId());
		    assignCleanProp(props, "em", readStoredMetaEmailHash());
		    assignCleanProp(props, "fbp", readCookie("_fbp"));
		    assignCleanProp(props, "fbc", readCookie("_fbc"));
			    const currentUrl = new URL(cleanText(eventSourceUrl) || window.location.href);
			    assignCleanProp(props, "session_id", sessionId);
			    assignCleanProp(props, "sessionId", sessionId);
			    assignCleanProp(props, "visitor_id", visitorId);
			    assignCleanProp(props, "visitorId", visitorId);
			    assignCleanProp(props, "fbclid", currentUrl.searchParams.get("fbclid"));
				    const currentClickId = readFirstSearchParam(currentUrl.searchParams, CLICK_PARAM_NAMES);
				    assignCleanProp(props, "click_id", currentClickId);
				    assignCleanProp(props, "clickId", currentClickId);
				    Object.assign(props, resolveFirstClassAttribution());
				    Object.assign(props, resolvePresaleBridgeContext(currentUrl.href, config.pageStage));
			    assignCleanProp(props, "event_source_url", currentUrl.href);
			    assignCleanProp(props, "$raw_user_agent", window.navigator && window.navigator.userAgent);
			    return props;
			  };
		  const resolveMetaAttributionReady = (eventSourceUrl) => {
		    const eventUrl = new URL(cleanText(eventSourceUrl) || window.location.href);
		    const hasFbclid = Boolean(cleanText(eventUrl.searchParams.get("fbclid")));
		    const hasFbp = Boolean(readCookie("_fbp"));
		    const hasFbc = Boolean(readCookie("_fbc"));
		    return hasFbp && (!hasFbclid || hasFbc);
		  };
		  const waitForMetaAttribution = (eventSourceUrl) => {
		    const startedAt = Date.now();
		    return new Promise((resolve) => {
		      const poll = () => {
		        const elapsedMs = Date.now() - startedAt;
		        if (resolveMetaAttributionReady(eventSourceUrl)) {
		          resolve({ elapsedMs, timedOut: false });
		          return;
		        }
		        if (elapsedMs >= META_ATTRIBUTION_WAIT_TIMEOUT_MS) {
		          resolve({ elapsedMs, timedOut: true });
		          return;
		        }
		        window.setTimeout(poll, META_ATTRIBUTION_WAIT_POLL_MS);
		      };
		      window.setTimeout(poll, META_ATTRIBUTION_WAIT_POLL_MS);
		    });
		  };
  const randomEventIdSegment = () => {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  };
  const buildMetaEventId = (eventName, eventType, index) => {
    return [
      cleanText(eventName) || "meta",
      cleanText(eventType) || "event",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      cleanText(sessionId) || "session",
      String(index),
      randomEventIdSegment(),
    ].join(":");
  };
  const buildMetaAddToCartHandoffEventId = (variantId) => {
    return [
      "mos",
      "meta",
      "AddToCart",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      cleanText(sessionId) || "session",
      cleanText(variantId) || "variant",
      randomEventIdSegment(),
    ].join(":");
  };
  const buildMetaInitiateCheckoutHandoffEventId = (transitionId) => {
    const cleanedTransitionId = cleanText(transitionId);
    return cleanedTransitionId ? "checkout_started:" + cleanedTransitionId : "";
  };
  const metaAddToCartCheckoutEventIds = {};
  const metaAddToCartNextEventIds = {};
  const metaAddToCartVariantKey = (variantId) => cleanText(variantId) || "default";
  const resolveMetaAddToCartCheckoutEventId = (variantId) => {
    const key = metaAddToCartVariantKey(variantId);
    if (!metaAddToCartCheckoutEventIds[key]) {
      metaAddToCartCheckoutEventIds[key] =
        metaAddToCartNextEventIds[key] || buildMetaAddToCartHandoffEventId(variantId);
      metaAddToCartNextEventIds[key] = metaAddToCartCheckoutEventIds[key];
    }
    return metaAddToCartCheckoutEventIds[key];
  };
  const consumeMetaAddToCartTrackingEventId = (variantId) => {
    const key = metaAddToCartVariantKey(variantId);
    const eventId = metaAddToCartNextEventIds[key] || resolveMetaAddToCartCheckoutEventId(variantId);
    if (!metaAddToCartCheckoutEventIds[key]) {
      metaAddToCartCheckoutEventIds[key] = eventId;
    }
    metaAddToCartNextEventIds[key] = buildMetaAddToCartHandoffEventId(variantId);
    return eventId;
  };
  const CLICK_ID_KEYS = ["fbclid", "gclid", "ttclid", "msclkid", "twclid", "li_fat_id"];
  const ATTRIBUTION_PARAM_GROUPS = [
    { keys: ["campaign_id", "campaignId"], params: ["campaign_id", "campaignId", "utm_campaign"] },
    { keys: ["ad_id", "adId"], params: ["ad_id", "adId", "utm_ad_id", "ad"] },
    { keys: ["adset_id", "adsetId"], params: ["adset_id", "adsetId", "ad_set_id", "adSetId", "utm_adset_id"] },
    { keys: ["utm_source", "utmSource"], params: ["utm_source"] },
    { keys: ["utm_medium", "utmMedium"], params: ["utm_medium"] },
    { keys: ["utm_campaign", "utmCampaign"], params: ["utm_campaign"] },
    { keys: ["utm_content", "utmContent"], params: ["utm_content"] },
    { keys: ["utm_term", "utmTerm"], params: ["utm_term"] },
  ];
  const buildCanonicalEventId = (eventType) => {
    return [
      "mos",
      cleanText(eventType) || "event",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      cleanText(sessionId) || "session",
      randomEventIdSegment(),
    ].join(":");
  };
  const resolveClickAttribution = () => {
    const params = new URLSearchParams(window.location.search);
    const clickId = readFirstSearchParam(params, CLICK_PARAM_NAMES);
    if (clickId) {
      const attribution = {
        clickId,
        click_id: clickId,
        clickIdType: CLICK_PARAM,
        click_id_type: CLICK_PARAM,
      };
      for (const key of CLICK_ID_KEYS) {
        const value = cleanText(params.get(key));
        if (value) {
          attribution.paidClickId = value;
          attribution.paid_click_id = value;
          attribution.paidClickIdType = key;
          attribution.paid_click_id_type = key;
          attribution[key] = value;
          break;
        }
      }
      return attribution;
    }
    for (const key of CLICK_ID_KEYS) {
      const value = cleanText(params.get(key));
      if (value) {
        return {
          clickId: value,
          clickIdType: key,
          [key]: value,
        };
      }
    }
    return {};
  };
  const resolveFirstClassAttribution = () => {
    const params = new URLSearchParams(window.location.search);
    const attribution = {};
    for (const group of ATTRIBUTION_PARAM_GROUPS) {
      const value = readFirstSearchParam(params, group.params);
      if (!value) continue;
      for (const key of group.keys) {
        attribution[key] = value;
      }
    }
    return attribution;
  };
  const resolvePageType = (stage) => {
    if (stage === "pre_sales") return "presell";
    if (stage === "sales") return "offer";
    if (stage === "checkout") return "checkout";
    if (stage === "thank_you") return "thank_you";
    return "custom";
  };
  const resolveExperimentId = () => {
    const params = new URLSearchParams(window.location.search);
    return (
      cleanText(params.get("experiment_id")) ||
      cleanText(params.get("experiment")) ||
      cleanText(params.get("exp"))
    );
  };
  const resolveDeviceType = () => {
    const width = window.innerWidth || (document.documentElement && document.documentElement.clientWidth) || 0;
    if (width > 0 && width < 768) return "mobile";
    if (width >= 768 && width < 1024) return "tablet";
    return "desktop";
  };
  const resolveRuntimeContextProps = (props) => {
    const manifest = config.manifest && typeof config.manifest === "object" ? config.manifest : {};
    const pageStage = cleanText((props && props.pageStage) || config.pageStage);
    const experimentId = resolveExperimentId();
    const externalId = resolveMetaExternalId();
    const emailHash = readStoredMetaEmailHash();
    const pageType = resolvePageType(pageStage);
    const pageVariant = cleanText(config.pageSlug);
    const resolvedVisitorId = cleanText(visitorId);
	    const resolvedSessionId = cleanText(sessionId);
	    const resolvedFunnelSessionId = cleanText(sessionId);
	    const deviceType = resolveDeviceType();
	    const clickAttribution = resolveClickAttribution();
	    const firstClassAttribution = resolveFirstClassAttribution();
		    const inboundPresaleBridgeContext = resolvePresaleBridgeContext(window.location.href, pageStage);
    const quizId = cleanText((props && (props.quizId || props.quiz_id)) || manifest.quizId || manifest.quiz_id);
    const quizVersion = cleanText((props && (props.quizVersion || props.quiz_version)) || manifest.quizVersion || manifest.quiz_version);
    const quizVariant = cleanText((props && (props.quizVariant || props.quiz_variant)) || manifest.quizVariant || manifest.quiz_variant);
	    return {
      productSlug: cleanText(config.productSlug),
      product_slug: cleanText(config.productSlug),
      funnelSlug: cleanText(config.funnelSlug),
      funnel_slug: cleanText(config.funnelSlug),
      publicationId: cleanText(config.publicationId),
      publication_id: cleanText(config.publicationId),
      pageId: cleanText(config.pageId),
      page_id: cleanText(config.pageId),
      pageSlug: cleanText(config.pageSlug),
      page_slug: cleanText(config.pageSlug),
      pageStage,
      page_stage: pageStage,
      pageType,
      page_type: pageType,
      htmlArtifactKind: cleanText(config.htmlArtifactKind),
      html_artifact_kind: cleanText(config.htmlArtifactKind),
      htmlDeploySchemaVersion: cleanText(config.htmlDeploySchemaVersion),
      html_deploy_schema_version: cleanText(config.htmlDeploySchemaVersion),
      pageVariant,
      page_variant: pageVariant,
      distinct_id: getCanonicalPostHogDistinctId(),
      visitorId: resolvedVisitorId,
      visitor_id: resolvedVisitorId,
      sessionId: resolvedSessionId,
      session_id: resolvedSessionId,
      funnelSessionId: resolvedFunnelSessionId,
      funnel_session_id: resolvedFunnelSessionId,
      path: window.location.pathname + window.location.search,
      referrer: document.referrer || undefined,
      deviceType,
      device_type: deviceType,
      browserUserAgent: window.navigator && window.navigator.userAgent,
      browser_user_agent: window.navigator && window.navigator.userAgent,
      ...(externalId ? { external_id: externalId } : {}),
      ...(emailHash ? { em: emailHash } : {}),
      ...(quizId ? { quizId, quiz_id: quizId } : {}),
      ...(quizVersion ? { quizVersion, quiz_version: quizVersion } : {}),
      ...(quizVariant ? { quizVariant, quiz_variant: quizVariant } : {}),
	      ...(experimentId ? { experimentId, experiment_id: experimentId } : {}),
	      ...firstClassAttribution,
	      ...clickAttribution,
	      ...(clickAttribution.clickId ? { click_id: clickAttribution.clickId } : {}),
	      ...(clickAttribution.clickIdType ? { click_id_type: clickAttribution.clickIdType } : {}),
	      ...inboundPresaleBridgeContext,
		    };
		  };
  const posthogTrackingConfig = isRecord(config.tracking) ? config.tracking : null;
  const createFallbackId = (prefix) =>
    prefix + "-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  const getFirstSearchParam = (names) => {
    try {
      return readFirstSearchParam(new URLSearchParams(window.location.search), names);
    } catch (_) {
      return null;
    }
  };
  const getOrCreateStoredId = (storage, key, prefix, preferredId) => {
    const cleanedPreferredId = cleanText(preferredId);
    try {
      if (cleanedPreferredId) {
        storage.setItem(key, cleanedPreferredId);
        return cleanedPreferredId;
      }
      const existing = storage.getItem(key);
      if (existing) return existing;
      const nextId =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : createFallbackId(prefix);
      storage.setItem(key, nextId);
      return nextId;
    } catch (_) {
      return cleanedPreferredId || createFallbackId(prefix);
    }
  };

  const visitorId = getOrCreateStoredId(
    window.localStorage,
    "funnel_visitor_id",
    "funnel-visitor",
	    getFirstSearchParam(VISITOR_PARAM_NAMES),
  );
  const sessionId = getOrCreateStoredId(
    window.sessionStorage,
    "funnel_session_id:" + String(config.productSlug || "unknown") + ":" + String(config.funnelSlug || "unknown"),
    "funnel-session",
	    getFirstSearchParam(SESSION_PARAM_NAMES),
  );
  const POSTHOG_IDENTIFIED_EMAIL_STORAGE_KEY = "mos_funnel_identified_email";
  const POSTHOG_IDENTIFIED_SESSION_STORAGE_KEY = "mos_funnel_identified_session_id";
  const POSTHOG_IDENTIFIED_EMAIL_HASH_STORAGE_KEY = "mos_funnel_identified_email_sha256";
  const getCanonicalPostHogDistinctId = () =>
    cleanText(sessionId) || cleanText(visitorId) || "anonymous-funnel-visitor";
  const readStoredPostHogIdentity = () => {
    try {
      const email = cleanText(window.localStorage.getItem(POSTHOG_IDENTIFIED_EMAIL_STORAGE_KEY));
      if (!email) return null;
      const storedSessionId = cleanText(window.localStorage.getItem(POSTHOG_IDENTIFIED_SESSION_STORAGE_KEY));
      if (storedSessionId && storedSessionId !== cleanText(sessionId)) return null;
      return {
        email,
        emailHash: cleanText(window.localStorage.getItem(POSTHOG_IDENTIFIED_EMAIL_HASH_STORAGE_KEY)),
      };
    } catch (_) {
      return null;
    }
  };
  const persistPostHogIdentity = (email, emailHash) => {
    const normalizedEmail = cleanText(email) ? String(email).trim().toLowerCase() : null;
    if (!normalizedEmail) return;
    try {
      window.localStorage.setItem(POSTHOG_IDENTIFIED_EMAIL_STORAGE_KEY, normalizedEmail);
      window.localStorage.setItem(POSTHOG_IDENTIFIED_SESSION_STORAGE_KEY, cleanText(sessionId));
      const cleanedEmailHash = cleanText(emailHash);
      if (cleanedEmailHash) {
        window.localStorage.setItem(POSTHOG_IDENTIFIED_EMAIL_HASH_STORAGE_KEY, cleanedEmailHash);
      }
    } catch (_) {
      // Ignore storage write failures; the active page still identifies immediately below.
    }
  };
  const resolvePostHogPersonProps = (email, emailHash, extraProps) => {
    const props = {
      email: cleanText(email),
      product_slug: cleanText(config.productSlug),
      funnel_slug: cleanText(config.funnelSlug),
      page_slug: cleanText(config.pageSlug),
      page_stage: cleanText(config.pageStage),
      page_id: cleanText(config.pageId),
      publication_id: cleanText(config.publicationId),
      visitor_id: cleanText(visitorId),
      visitorId: cleanText(visitorId),
      session_id: cleanText(sessionId),
      sessionId: cleanText(sessionId),
      funnel_session_id: cleanText(sessionId),
      funnelSessionId: cleanText(sessionId),
      external_id: resolveMetaExternalId(),
      ...(extraProps || {}),
    };
    assignCleanProp(props, "em", emailHash);
    assignCleanProp(props, "email_sha256", emailHash);
    return props;
  };
  const restorePostHogIdentity = (instance) => {
    if (!instance || typeof instance.identify !== "function") return;
    const storedIdentity = readStoredPostHogIdentity();
    if (!storedIdentity) return;
    const restoreKey = storedIdentity.email + ":" + cleanText(sessionId);
    if (instance.__mosFunnelRestoredIdentityFor === restoreKey) return;
    instance.__mosFunnelRestoredIdentityFor = restoreKey;
    instance.identify(
      storedIdentity.email,
      resolvePostHogPersonProps(storedIdentity.email, storedIdentity.emailHash),
    );
  };

  const getUtmParams = () => {
    const params = new URLSearchParams(window.location.search);
    const utm = {};
    for (const [key, value] of params.entries()) {
      if (key.startsWith("utm_")) utm[key] = value;
    }
    return utm;
  };
  const getUrlParams = () => {
    const params = new URLSearchParams(window.location.search);
    const out = {};
    for (const [key, value] of params.entries()) {
      out[key] = value;
    }
    return out;
  };
  const isDeployTrackingValidationSession = () => {
    try {
      return Boolean(cleanText(new URLSearchParams(window.location.search).get("mos_deploy_validation_id")));
    } catch (_) {
      return false;
    }
  };
  const isPresaleToSalesNavigation = (fromStage, toStage) =>
    cleanText(fromStage) === "pre_sales" && cleanText(toStage) === "sales";
  const presaleAttributionStorageKey = () => {
    const product = cleanText(config.productSlug);
    const funnel = cleanText(config.funnelSlug);
    if (!product || !funnel) return null;
    return "from_presale:" + product + ":" + funnel;
  };
  const markPresaleAttribution = () => {
    const key = presaleAttributionStorageKey();
    if (!key) return;
    try {
      window.sessionStorage.setItem(key, "1");
    } catch (_) {
      // ignore storage write failures
    }
  };
  const hasPresaleSourceParam = () =>
    new URLSearchParams(window.location.search).get(PRESALE_SOURCE_PARAM) === PRESALE_SOURCE_VALUE;
  const hasStoredPresaleAttribution = () => {
    const key = presaleAttributionStorageKey();
    if (!key) return false;
    try {
      return window.sessionStorage.getItem(key) === "1";
    } catch (_) {
      return false;
    }
  };
  const hasPresaleReferrerAttribution = () => {
    if (!document.referrer) return false;
    try {
      const referrerUrl = new URL(document.referrer, window.location.href);
      if (referrerUrl.origin !== window.location.origin) {
        return false;
      }
      const preSalesPaths = Object.entries(config.pageStageById || {})
        .filter(([, stage]) => cleanText(stage) === "pre_sales")
        .map(([pageId]) => cleanText(config.pagePathById && config.pagePathById[pageId]))
        .filter(Boolean);
      return preSalesPaths.some((path) => new URL(path, window.location.href).pathname === referrerUrl.pathname);
    } catch (_) {
      return false;
    }
  };
  const resolvePresaleAttribution = () => {
    if (hasPresaleSourceParam()) return "url";
    if (hasStoredPresaleAttribution()) return "session";
    if (hasPresaleReferrerAttribution()) return "referrer";
    return null;
  };
  const checkoutStatusFromLocation = () => {
    const checkoutStatus = new URL(window.location.href).searchParams.get("checkout");
    return checkoutStatus === "success" || checkoutStatus === "cancel" ? checkoutStatus : null;
  };
  const clearCheckoutQueryParam = (href) => {
    const nextUrl = new URL(href, window.location.href);
    nextUrl.searchParams.delete("checkout");
    return nextUrl.toString();
  };
  const buildBridgeClickId = (bindingId, ctaPosition) => {
    return [
      "click",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      cleanText(bindingId) || "cta",
      String(ctaPosition || 1),
      randomEventIdSegment(),
    ].join("_");
  };
  const buildInternalNavigationUrl = (targetPath, options) => {
    const normalizedTargetPath = cleanText(targetPath);
    if (!normalizedTargetPath) return window.location.href;
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.delete("checkout");
    const nextUrl = new URL(normalizedTargetPath, window.location.href);
    nextUrl.search = currentUrl.search;
	    if (isPresaleToSalesNavigation(options && options.fromStage, options && options.toStage)) {
	      nextUrl.searchParams.set(PRESALE_SOURCE_PARAM, PRESALE_SOURCE_VALUE);
	      const sourceArtifactKind = cleanText(config.htmlArtifactKind);
	      const sourcePageType = resolvePresaleSourcePageType(sourceArtifactKind);
	      if (!sourcePageType) {
	        throw new Error("HTML deploy pre-sales navigation requires a known htmlArtifactKind.");
	      }
	      if (sourceArtifactKind) nextUrl.searchParams.set("from", sourceArtifactKind);
	      nextUrl.searchParams.set("source_page_type", sourcePageType);
	      nextUrl.searchParams.set("from_stage", "pre_sales");
	      nextUrl.searchParams.set("to_stage", "sales");
	      const bridgeSessionId = cleanText(options && options.sessionId) || cleanText(sessionId);
	      const bridgeAnonymousId = cleanText(options && options.anonymousId) || cleanText(visitorId);
	      const bridgeClickId = cleanText(options && options.clickId);
	      if (bridgeSessionId) nextUrl.searchParams.set(SESSION_PARAM, bridgeSessionId);
	      if (bridgeAnonymousId) nextUrl.searchParams.set(VISITOR_PARAM, bridgeAnonymousId);
	      if (bridgeClickId) nextUrl.searchParams.set(CLICK_PARAM, bridgeClickId);
    }
    return nextUrl.toString();
  };
  const resolveSameDocumentHashTarget = (element) => {
    if (!(element instanceof HTMLAnchorElement)) return null;
    const rawHref = cleanText(element.getAttribute("href"));
    if (!rawHref || !rawHref.startsWith("#") || rawHref === "#") return null;
    const targetId = cleanText(rawHref.slice(1));
    if (!targetId) return null;
    const target = document.getElementById(targetId);
    return target instanceof HTMLElement ? target : null;
  };
  const hasPaidEntryAttribution = () => {
    const params = new URLSearchParams(window.location.search);
    const clickIdKeys = ["fbclid", "gclid", "ttclid", "msclkid", "twclid", "li_fat_id"];
    for (const key of clickIdKeys) {
      const value = params.get(key);
      if (typeof value === "string" && value.trim()) return true;
    }
    const utmKeys = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
    for (const key of utmKeys) {
      const value = params.get(key);
      if (typeof value === "string" && value.trim()) return true;
    }
    return false;
  };
  const pendingMetaPurchaseStorageKey = (resolvedSessionId, resolvedFunnelSlug) => {
    const cleanSessionId = cleanText(resolvedSessionId);
    const cleanFunnelSlug = cleanText(resolvedFunnelSlug);
    if (!cleanSessionId || !cleanFunnelSlug) return null;
    return "mos-meta-purchase:" + cleanSessionId + ":" + cleanFunnelSlug;
  };
  const writePendingMetaPurchase = (key, purchase) => {
    if (!key) return;
    try {
      window.sessionStorage.setItem(
        key,
        JSON.stringify({
          ...purchase,
          createdAt: Date.now(),
        }),
      );
    } catch (_) {
      // ignore storage write failures
    }
  };
  const readPendingMetaPurchase = (key) => {
    if (!key) return null;
    try {
      const raw = window.sessionStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return isRecord(parsed) ? parsed : null;
    } catch (_) {
      return null;
    }
  };
  const clearPendingMetaPurchase = (key) => {
    if (!key) return;
    try {
      window.sessionStorage.removeItem(key);
    } catch (_) {
      // ignore storage delete failures
    }
  };
  const buildPurchaseEventParams = (purchase) => {
    if (!isRecord(purchase)) return undefined;
    const params = {};
    const currency = cleanText(purchase.currency);
    if (currency) params.currency = currency;
    if (typeof purchase.value === "number") params.value = purchase.value;
    const variantId = cleanText(purchase.variantId);
    if (variantId) {
      params.content_ids = [variantId];
      params.content_type = "product";
    }
    params.num_items = typeof purchase.quantity === "number" ? purchase.quantity : 1;
    return params;
  };
  const loadMetaPixelScript = () => {
    if (metaPixelScriptLoadPromise) return metaPixelScriptLoadPromise;
    const existingScript = document.getElementById(META_PIXEL_SCRIPT_ID);
    if (existingScript) return Promise.resolve();
    metaPixelScriptLoadPromise = new Promise((resolve) => {
      const script = document.createElement("script");
      let settled = false;
      const settle = () => {
        if (settled) return;
        settled = true;
        resolve();
      };
      script.id = META_PIXEL_SCRIPT_ID;
      script.async = true;
      script.src = META_PIXEL_SCRIPT_SRC;
      script.addEventListener("load", settle, { once: true });
      script.addEventListener("error", settle, { once: true });
      document.head.appendChild(script);
    });
    return metaPixelScriptLoadPromise;
  };
  const waitForMetaPixelScriptLoad = async () => {
    const loadPromise = metaPixelScriptLoadPromise || loadMetaPixelScript();
    await Promise.race([
      loadPromise,
      waitMs(META_PIXEL_EVENT_LOAD_TIMEOUT_MS),
    ]);
  };
  const waitForMetaPixelTrackedEventFlush = async () => {
    if (!metaPixelLastTrackedAt) return;
    await waitForMetaPixelScriptLoad();
    const elapsedMs = Date.now() - metaPixelLastTrackedAt;
    const remainingMs = META_PIXEL_EVENT_NETWORK_WINDOW_MS - elapsedMs;
    if (remainingMs > 0) {
      await waitMs(remainingMs);
    }
  };
  const waitForPostHogNavigationEventFlush = async () => {
    const pending = posthogNavigationFlushPromises.splice(0);
    if (!pending.length) return;
    await Promise.race([
      Promise.allSettled(pending),
      waitMs(POSTHOG_NAVIGATION_EVENT_LOAD_TIMEOUT_MS),
    ]);
    await waitMs(POSTHOG_NAVIGATION_EVENT_NETWORK_WINDOW_MS);
  };
  const scheduleMetaPixelScriptLoad = () => {
    if (window.__mosMetaPixelLoadScheduled || document.getElementById(META_PIXEL_SCRIPT_ID)) {
      return;
    }
    window.__mosMetaPixelLoadScheduled = true;
    let timeoutId = null;
    let idleCallbackId = null;
    const flush = () => {
      if (!window.__mosMetaPixelLoadScheduled) {
        return;
      }
      window.__mosMetaPixelLoadScheduled = false;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
      }
      if (idleCallbackId !== null && typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(idleCallbackId);
        idleCallbackId = null;
      }
      void loadMetaPixelScript();
    };
    const listenerOptions = { capture: true, once: true };
    window.addEventListener("pointerdown", flush, listenerOptions);
    window.addEventListener("keydown", flush, listenerOptions);
    window.addEventListener("touchstart", flush, listenerOptions);
    window.addEventListener("scroll", flush, { capture: true, once: true, passive: true });
    window.addEventListener("load", flush, { once: true });
    window.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        flush();
      }
    }, { once: true });
    window.addEventListener("pagehide", flush, { once: true });
    if (typeof window.requestIdleCallback === "function") {
      idleCallbackId = window.requestIdleCallback(flush, {
        timeout: META_PIXEL_DEFER_TIMEOUT_MS,
      });
    }
    timeoutId = window.setTimeout(flush, META_PIXEL_DEFER_TIMEOUT_MS);
  };
  const ensureMetaPixelBootstrap = () => {
    if (!config.tracking || !config.tracking.metaPixelId) {
      return null;
    }
    const pixelId = String(config.tracking.metaPixelId || "").trim();
    if (!pixelId) return null;
    if (!window.fbq) {
      const fbq = function (...args) {
        const activeFbq = window.fbq;
        if (activeFbq && activeFbq !== fbq && typeof activeFbq.callMethod === "function") {
          activeFbq.callMethod(...args);
          return;
        }
        if (typeof fbq.callMethod === "function") {
          fbq.callMethod(...args);
          return;
        }
        fbq.queue = fbq.queue || [];
        fbq.queue.push(args);
      };
      fbq.queue = [];
      fbq.loaded = true;
      fbq.version = "2.0";
      window.fbq = fbq;
      window._fbq = fbq;
    }
    scheduleMetaPixelScriptLoad();
    if (!Array.isArray(window.__mosMetaPixelIds)) {
      window.__mosMetaPixelIds = [];
    }
    if (!window.__mosMetaPixelIds.includes(pixelId)) {
      const advancedMatching = resolveMetaAdvancedMatchingProps();
      if (isNonEmptyRecord(advancedMatching)) {
        window.fbq("init", pixelId, advancedMatching);
      } else {
        window.fbq("init", pixelId);
      }
      window.__mosMetaPixelIds.push(pixelId);
    }
    return pixelId;
  };
  const ensurePostHogInstance = () => {
    const apiKey = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogProjectApiKey);
    const apiHost = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogApiHost);
    const uiHost = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogUiHost);
    if (!apiKey || !apiHost) return null;
    const defaults = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogDefaults) || "2026-01-30";
    const personProfiles =
      cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogPersonProfiles) || "identified_only";
    const distinctId = getCanonicalPostHogDistinctId();
    !function(t,e){var o,n,p,r,d;e.__SV||(window.posthog&&window.posthog.__loaded)||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0])&&r.parentNode?r.parentNode.insertBefore(p,r):(d=t.head||t.body||t.documentElement)&&d.appendChild(p);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="Ir Sr init jr $r Ci qr Hr Dr capture calculateEventProperties Wr register register_once register_for_session unregister unregister_for_session Qr getFeatureFlag getFeatureFlagPayload getFeatureFlagResult isFeatureEnabled reloadFeatureFlags updateFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSurveysLoaded onSessionId getSurveys getActiveMatchingSurveys renderSurvey displaySurvey cancelPendingSurvey canRenderSurvey canRenderSurveyAsync tn identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset setIdentity clearIdentity get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException captureLog startExceptionAutocapture stopExceptionAutocapture loadToolbar get_property getSessionProperty Jr Yr createPersonProfile setInternalOrTestUser Kr Pr nn opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing get_explicit_consent_status is_capturing clear_opt_in_out_capturing zr debug ki Xr getPageViewId captureTraceFeedback captureTraceMetric Mr".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
    const existingInstance = window.posthog && window.posthog[POSTHOG_INSTANCE_NAME];
    if (
      existingInstance &&
      (existingInstance.__mosFunnelConfigured === "true" || window.__mosFunnelPostHogConfigured === "true")
    ) {
      window.__mosFunnelPostHogConfigured = "true";
      restorePostHogIdentity(existingInstance);
      return existingInstance;
    }
    window.posthog.init(
      apiKey,
      {
        api_host: apiHost,
        ...(uiHost ? { ui_host: uiHost } : {}),
        defaults,
        person_profiles: personProfiles,
        autocapture: false,
        capture_pageview: true,
        capture_pageleave: true,
        ...(isDeployTrackingValidationSession() ? { opt_out_useragent_filter: true } : {}),
        bootstrap: {
          distinctID: distinctId,
          isIdentifiedID: false,
        },
      },
      POSTHOG_INSTANCE_NAME,
    );
    const instance = window.posthog && window.posthog[POSTHOG_INSTANCE_NAME];
    if (!instance) return null;
    if (typeof instance.register === "function") {
      instance.register({
        productSlug: cleanText(config.productSlug),
        funnelSlug: cleanText(config.funnelSlug),
        publicationId: cleanText(config.publicationId),
        funnel_session_id: cleanText(sessionId),
        funnelSessionId: cleanText(sessionId),
      });
    }
    restorePostHogIdentity(instance);
    instance.__mosFunnelConfigured = "true";
    window.__mosFunnelPostHogConfigured = "true";
    return instance;
	  };
	  const trackPostHogEvent = (eventType, props, mappedCaptures) => {
		    const eventSourceUrl = window.location.href;
		    const baseEventProps = {
		      ...resolveRuntimeContextProps(props),
	      utm: getUtmParams(),
	    };
			    const navigationCritical = isNavigationCriticalPostHogEvent(eventType);
	    const directTransportPreferred = navigationCritical || isDirectPostHogTransportEvent(eventType);
		    let resolveNavigationFlush = null;
		    const navigationFlushPromise = navigationCritical
		      ? new Promise((resolve) => {
		          resolveNavigationFlush = resolve;
		        })
		      : null;
		    if (navigationFlushPromise) {
		      posthogNavigationFlushPromises.push(navigationFlushPromise);
		      window.setTimeout(() => {
		        if (typeof resolveNavigationFlush === "function") {
		          resolveNavigationFlush();
		          resolveNavigationFlush = null;
		        }
		      }, POSTHOG_NAVIGATION_EVENT_LOAD_TIMEOUT_MS);
		    }
		    const markNavigationFlushReady = () => {
		      if (typeof resolveNavigationFlush === "function") {
		        resolveNavigationFlush();
		        resolveNavigationFlush = null;
		      }
		    };
		    const emitCaptures = (additionalEventProps) => {
		      const captures = resolvePostHogCaptures(eventType, props, baseEventProps, mappedCaptures, eventSourceUrl);
		      if (!captures.length) {
		        markNavigationFlushReady();
		        return;
		      }
		      let sent = false;
		      const sendDirectNavigationCaptures = () => {
		        if (!directTransportPreferred) return false;
		        const apiKey = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogProjectApiKey);
		        const apiHost = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogApiHost);
		        if (!apiKey || !apiHost) return false;
		        const endpoint = apiHost.replace(/\/+$/, "") + "/capture/";
		        const directPayloads = [];
		        captures.forEach((capture) => {
		          const directProperties = {
		            ...capture.eventProps,
		            ...(additionalEventProps || {}),
		          };
		          if (!cleanText(directProperties.distinct_id)) {
		            directProperties.distinct_id = getCanonicalPostHogDistinctId();
		          }
		          const payload = JSON.stringify({
		            api_key: apiKey,
		            event: capture.eventName,
		            distinct_id: directProperties.distinct_id,
		            properties: directProperties,
		          });
		          directPayloads.push(payload);
		        });
		        if (!directPayloads.length) return false;
		        if (window.fetch) {
		          Promise.allSettled(directPayloads.map((payload) => {
		            const fetchOptions = {
		              method: "POST",
		              headers: { "Content-Type": "application/json" },
		              body: payload,
		            };
		            if (!navigationCritical) {
		              fetchOptions.keepalive = true;
		            }
		            return window.fetch(endpoint, fetchOptions).catch(() => {});
		          })).finally(markNavigationFlushReady);
		          return true;
		        }
		        let attemptedBeacon = false;
		        directPayloads.forEach((payload) => {
		          try {
		            if (navigator.sendBeacon) {
		              const blob = new Blob([payload], { type: "application/json" });
		              if (navigator.sendBeacon(endpoint, blob)) attemptedBeacon = true;
		            }
		          } catch (_error) {}
		        });
		        if (attemptedBeacon) markNavigationFlushReady();
		        return attemptedBeacon;
		      };
		      const sendCaptures = () => {
		        if (sent) return;
		        if (directTransportPreferred && sendDirectNavigationCaptures()) {
		          sent = true;
		          return;
		        }
		        const posthog = ensurePostHogInstance();
		        if (!posthog || posthog.__loaded !== true || typeof posthog.capture !== "function") {
		          if (sendDirectNavigationCaptures()) {
		            sent = true;
		          }
		          return;
		        }
		        sent = true;
		        captures.forEach((capture) => {
		          posthog.capture(capture.eventName, {
		            ...capture.eventProps,
		            ...(additionalEventProps || {}),
		          });
		        });
		        markNavigationFlushReady();
		      };
		      sendCaptures();
		      if (!sent) {
		        window.setTimeout(sendCaptures, 100);
		        window.setTimeout(sendCaptures, 500);
		        window.setTimeout(sendCaptures, 1500);
		        window.setTimeout(sendCaptures, 3000);
		        window.setTimeout(sendCaptures, 5000);
		      }
		    };
			    if (
			      Array.isArray(mappedCaptures) &&
			      mappedCaptures.length &&
			      !resolveMetaAttributionReady(eventSourceUrl) &&
			      !navigationCritical
			    ) {
		      waitForMetaAttribution(eventSourceUrl).then(({ elapsedMs, timedOut }) => {
	        emitCaptures({
		          meta_cookie_wait_ms: elapsedMs,
	          ...(timedOut ? { meta_cookie_wait_timed_out: true } : {}),
	        });
	      });
	      return navigationFlushPromise || Promise.resolve();
	    }
	    emitCaptures();
	    return navigationFlushPromise || Promise.resolve();
	  };
  const resolveMetaPixelPageStage = (props) => {
    const pageStage = cleanText(props && props.pageStage);
    return pageStage || cleanText(config.pageStage);
  };
  const resolvePostHogContentCategory = (pageStage) => {
    if (pageStage === "pre_sales") return "pre_sales_page";
    if (pageStage === "sales") return "sales_page";
    if (pageStage === "checkout") return "checkout_page";
    if (pageStage === "thank_you") return "thank_you_page";
    if (pageStage === "custom") return "custom_page";
    return null;
  };
  const buildPostHogEventId = (eventName, eventType, index) => {
    return [
      cleanText(eventName) || "capture",
      cleanText(eventType) || "event",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      cleanText(sessionId) || "session",
      String(index),
      String(Date.now()),
    ].join(":");
  };
  const sanitizePostHogProps = (props) => {
    if (!isRecord(props)) return {};
    const nextProps = { ...props };
    delete nextProps.fromPresale;
    return nextProps;
  };
  const trackMetaPixel = (method, eventName, params, eventId) => {
    if (typeof window.fbq !== "function") return;
    const options = cleanText(eventId) ? { eventID: cleanText(eventId) } : null;
    if (isNonEmptyRecord(params)) {
      if (options) {
        window.fbq(method, eventName, params, options);
        return;
      }
      window.fbq(method, eventName, params);
      return;
    }
    if (options) {
      window.fbq(method, eventName, {}, options);
      return;
    }
    window.fbq(method, eventName);
  };
  const resolveProductMetaParams = (props) => {
    const explicitContentIds = cleanStringArray(props && (props.content_ids || props.contentIds));
    const variantId = cleanText(
      props &&
        (
          props.variantId ||
          props.variant_id ||
          props.contentId ||
          props.content_id
        ),
    );
    const contentIds = explicitContentIds.length ? explicitContentIds : (variantId ? [variantId] : []);
    const explicitNumItems = Number(props && (props.num_items || props.numItems));
    const params = {
      content_type: "product",
      num_items: Number.isFinite(explicitNumItems) && explicitNumItems > 0
        ? explicitNumItems
        : Math.max(1, contentIds.length || 1),
    };
    if (contentIds.length) {
      params.content_ids = contentIds;
    }
    const value = props && typeof props.value === "number" ? props.value : null;
    const currency = cleanText(props && props.currency);
    if (value !== null) {
      params.value = value;
    }
    if (currency) {
      params.currency = currency;
    }
    return params;
  };
  const resolveMappedMetaEvents = (eventType, props) => {
    const pageStage = resolveMetaPixelPageStage(props);
    const pageViewParams = pageStage ? { page_stage: pageStage } : undefined;
    if (eventType === "presell_page_view") {
      return [
        { method: "trackCustom", eventName: "EnteredPresales", params: pageViewParams },
        { method: "trackCustom", eventName: "Entered Presales Page", params: pageViewParams },
      ];
    }
    if (eventType === "pre_sales_page_view" || eventType === "custom_page_view") {
      return [{ method: "track", eventName: "PageView", params: pageViewParams }];
    }
    if (eventType === "sales_page_view") {
      return [
        { method: "track", eventName: "PageView", params: pageViewParams },
        { method: "trackCustom", eventName: "Entered Sales Page", params: pageViewParams },
        { method: "trackCustom", eventName: "EnteredSales", params: pageViewParams },
        { method: "track", eventName: "ViewContent", params: pageViewParams },
      ];
    }
    if (eventType === "checkout_page_view" || eventType === "thank_you_page_view") {
      return [{ method: "track", eventName: "PageView", params: pageViewParams }];
    }
    if (eventType === "pre_sales_to_sales_click") {
      return [{
        method: "trackCustom",
        eventName: "PreSalesToSalesClick",
        params: {
          from_stage: "pre_sales",
          to_stage: "sales",
        },
      }];
    }
    if (eventType === "add_to_cart") {
      const metaAddToCartEventId = cleanText(
        props && (props.metaAddToCartEventId || props.meta_add_to_cart_event_id),
      );
      return [{
        method: "track",
        eventName: "AddToCart",
        params: resolveProductMetaParams(props),
        ...(metaAddToCartEventId ? { eventId: metaAddToCartEventId } : {}),
      }];
    }
    if (eventType === "sales_to_checkout_click") {
      const variantId = cleanText(props && props.variantId);
      const transitionId = cleanText(props && (props.transitionId || props.transition_id));
      const checkoutUrl = cleanText(props && (props.checkoutUrl || props.checkout_url));
      const salesToCheckoutParams = {
        ...resolveProductMetaParams(props),
        from_stage: "sales",
        to_stage: "checkout",
        ...(transitionId ? { transition_id: transitionId } : {}),
        ...(checkoutUrl ? { checkout_url: checkoutUrl } : {}),
      };
      return [
        {
          method: "trackCustom",
          eventName: "SalesToCheckoutClick",
          params: salesToCheckoutParams,
        },
        {
          method: "trackCustom",
          eventName: "SalesToCheckoutClicked",
          params: salesToCheckoutParams,
        },
      ];
    }
    if (eventType === "checkout_started") {
      const transitionId = cleanText(props && (props.transitionId || props.transition_id));
      const metaInitiateCheckoutEventId =
        cleanText(props && (props.metaInitiateCheckoutEventId || props.meta_initiate_checkout_event_id)) ||
        buildMetaInitiateCheckoutHandoffEventId(transitionId);
      return [{
        method: "track",
        eventName: "InitiateCheckout",
        params: resolveProductMetaParams(props),
        ...(metaInitiateCheckoutEventId ? { eventId: metaInitiateCheckoutEventId } : {}),
      }];
    }
    return [];
  };
	  const resolveCanonicalPostHogEventNames = (eventType) => {
	    const normalized = cleanText(eventType);
	    if (!normalized) return [];
    const rmbcAliasesByEventType = {
      quiz_lead_viewed: ["QuizLeadViewed"],
      quiz_question_viewed: ["QuizQuestionViewed"],
      quiz_option_presented: ["QuizOptionPresented"],
      quiz_option_selected: ["QuizOptionSelected"],
      quiz_option_deselected: ["QuizOptionDeselected"],
      quiz_question_submitted: ["QuizQuestionSubmitted"],
      quiz_completed: ["QuizCompleted"],
      quiz_result_viewed: ["QuizResultViewed"],
      quiz_mechanism_viewed: ["QuizMechanismViewed"],
      quiz_proof_viewed: ["QuizProofViewed"],
      quiz_recommendation_viewed: ["QuizRecommendationViewed"],
      quiz_cta_viewed: ["QuizCtaViewed"],
    };
    const names = [normalized];
    if (normalized === "pre_sales_page_view") {
      names.push("presell_page_view");
    }
    if (normalized === "pre_sales_to_sales_click") {
      names.push("PreSalesToSalesClick", "cta_click");
    }
    if (normalized === "sales_to_checkout_click") {
      names.push("SalesToCheckoutClick", "SalesToCheckoutClicked", "checkout_click");
    }
    if (Array.isArray(rmbcAliasesByEventType[normalized])) {
      rmbcAliasesByEventType[normalized].forEach((alias) => names.push(alias));
	    }
	    return names;
	  };
	  const isNavigationCriticalPostHogEvent = (eventType) => {
	    const normalized = cleanText(eventType);
	    return (
	      normalized === "pre_sales_to_sales_click" ||
	      normalized === "sales_to_checkout_click" ||
	      normalized === "checkout_started" ||
	      normalized === "quiz_completed"
	    );
	  };
  const isDirectPostHogTransportEvent = (eventType) => {
    const normalized = cleanText(eventType);
    return (
      normalized === "quiz_option_selected" ||
      normalized === "quiz_question_submitted" ||
      normalized === "quiz_completed" ||
      normalized === "quiz_cta_viewed"
    );
  };
	  const resolvePostHogCaptures = (eventType, props, baseEventProps, providedMappedCaptures, eventSourceUrl) => {
    const sanitizedProps = sanitizePostHogProps(props);
    const canonicalEventId = cleanText(props && props.eventId);
    const pageStage = cleanText((props && props.pageStage) || config.pageStage);
    const contentCategory = resolvePostHogContentCategory(pageStage);
    const attributionProps = resolveMetaAttributionProps(eventSourceUrl);
    const canonicalEventNames = resolveCanonicalPostHogEventNames(eventType);
    const mappedCaptures = Array.isArray(providedMappedCaptures)
      ? providedMappedCaptures
      : resolveMappedMetaEvents(eventType, props);
	    const buildEventProps = (eventName, role, eventId, extraProps) => {
	      const eventProps = {
	        ...baseEventProps,
	        ...attributionProps,
	        ...sanitizedProps,
	        ...(isRecord(extraProps) ? extraProps : {}),
	        internal_event_type: eventType,
	        canonical_event_type: role === "platform_alias" ? eventType : eventName,
	        posthog_event_role: role,
	        ...(canonicalEventId ? { mos_event_id: canonicalEventId } : {}),
	        $event_id: eventId,
	      };
      if (contentCategory) {
        eventProps.content_category = contentCategory;
      }
      if (eventType === "sales_page_view") {
        eventProps.from_presale = props && props.fromPresale === true;
      }
      return eventProps;
    };
    const captures = canonicalEventNames.map((eventName, index) => {
      const eventId = index === 0 && canonicalEventId
        ? canonicalEventId
        : buildPostHogEventId(eventName, eventType, index);
      return {
        eventName,
        eventProps: buildEventProps(eventName, index === 0 ? "canonical" : "rmbc_alias", eventId),
      };
    });
    mappedCaptures.forEach((capture, index) => {
      if (canonicalEventNames.includes(capture.eventName)) {
        return;
      }
      const metaEventId = cleanText(capture.eventId) || buildMetaEventId(capture.eventName, eventType, index);
      captures.push({
        eventName: capture.eventName,
        eventProps: {
          ...buildEventProps(capture.eventName, "platform_alias", metaEventId, capture.params),
          canonical_event_type: eventType,
          meta_event_name: capture.eventName,
          meta_event_id: metaEventId,
        },
      });
    });
    return captures;
  };
  const trackMetaPixelCaptures = (mappedCaptures, eventProps) => {
    const pixelId = ensureMetaPixelBootstrap();
    if (!pixelId || typeof window.fbq !== "function") return;
    if (Array.isArray(mappedCaptures) && mappedCaptures.length) {
      metaPixelLastTrackedAt = Date.now();
      void loadMetaPixelScript();
    }
    const eventParamProps = {
      ...resolveRuntimeContextProps(eventProps),
      ...(isRecord(eventProps) ? eventProps : {}),
    };
    const attributionParams = resolveMetaAttributionProps(window.location.href);
	    mappedCaptures.forEach((capture) => {
	      trackMetaPixel(capture.method, capture.eventName, {
	        ...attributionParams,
	        ...eventParamProps,
	        ...(isRecord(capture.params) ? capture.params : {}),
	      }, capture.eventId);
	    });
  };
  const postTrackingPayload = (payload, options) => {
    if (typeof payload !== "string" || !payload) return;
    const preferFetch = Boolean(options && options.preferFetch === true);
    if (!preferFetch && typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      try {
        const queued = navigator.sendBeacon(
          EVENTS_ENDPOINT,
          new Blob([payload], { type: "application/json" }),
        );
        if (queued) {
          return Promise.resolve();
        }
      } catch (error) {
        if (!pageLifecycleFinalizing) {
          console.error("[HtmlDeployArtifact] Tracking failed.", error);
        }
      }
    }
    try {
      return fetch(EVENTS_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
      }).catch((error) => {
        if (!pageLifecycleFinalizing) {
          console.error("[HtmlDeployArtifact] Tracking failed.", error);
        }
      });
    } catch (error) {
      if (!pageLifecycleFinalizing) {
        console.error("[HtmlDeployArtifact] Tracking failed.", error);
      }
    }
  };
  const recordInternalTrackingValidationPayload = (payload) => {
    try {
      if (typeof payload !== "string" || !payload) return;
      const validationState = window.__mosDeployTrackingValidation;
      if (!validationState || typeof validationState !== "object") return;
      const parsed = JSON.parse(payload);
      const events = Array.isArray(parsed && parsed.events) ? parsed.events : [];
      if (!events.length) return;
      if (!Array.isArray(validationState.internal)) {
        validationState.internal = [];
      }
      events.forEach((event) => {
        const eventType = cleanText(event && event.eventType);
        if (!eventType) return;
        validationState.internal.push({
          eventType,
          props: isRecord(event && event.props) ? event.props : null,
        });
      });
      try {
        window.sessionStorage &&
          window.sessionStorage.setItem(
            "__mos_deploy_tracking_validation__",
            JSON.stringify(validationState),
          );
      } catch (_error) {}
    } catch (_error) {}
  };
  const quizCompletedDedupeKeys = {};
  const addToCartDedupeKeys = {};
  const QUIZ_COMPLETED_DEDUPE_STORAGE_KEY = "__mos_quiz_completed_dedupe__";
  const readStoredQuizCompletedDedupeKeys = () => {
    try {
      const raw = window.sessionStorage && window.sessionStorage.getItem(QUIZ_COMPLETED_DEDUPE_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch (_error) {
      return {};
    }
  };
  const writeStoredQuizCompletedDedupeKey = (dedupeKey) => {
    try {
      if (!window.sessionStorage) return;
      const storedKeys = readStoredQuizCompletedDedupeKeys();
      storedKeys[dedupeKey] = true;
      window.sessionStorage.setItem(QUIZ_COMPLETED_DEDUPE_STORAGE_KEY, JSON.stringify(storedKeys));
    } catch (_error) {}
  };
  const buildQuizCompletedDedupeKey = (props) => [
    cleanText(props && (props.session_id || props.sessionId)) || cleanText(sessionId) || "session",
    cleanText(props && (props.quiz_id || props.quizId)) ||
      cleanText(config.manifest && (config.manifest.quizId || config.manifest.quiz_id)) ||
      "quiz",
    cleanText(props && (props.quiz_version || props.quizVersion)) ||
      cleanText(config.manifest && (config.manifest.quizVersion || config.manifest.quiz_version)) ||
      "version",
  ].join(":");
  const shouldSuppressDuplicateQuizCompleted = (eventType, eventProps) => {
    const normalizedEventType = cleanText(eventType);
    if (normalizedEventType !== "quiz_completed" && normalizedEventType !== "QuizCompleted") {
      return false;
    }
    const dedupeKey = buildQuizCompletedDedupeKey(eventProps || {});
    const storedDedupeKeys = readStoredQuizCompletedDedupeKeys();
    if (quizCompletedDedupeKeys[dedupeKey] === true || storedDedupeKeys[dedupeKey] === true) {
      window.__mosQuizCompletedDuplicateCount = (window.__mosQuizCompletedDuplicateCount || 0) + 1;
      return true;
    }
    quizCompletedDedupeKeys[dedupeKey] = true;
    writeStoredQuizCompletedDedupeKey(dedupeKey);
    eventProps.dedupe_key = dedupeKey;
    eventProps.dedupeKey = dedupeKey;
    eventProps.dedupe_strategy = "session_quiz_completion";
    return false;
  };
  const buildAddToCartDedupeKey = (props) => [
    cleanText(props && (props.session_id || props.sessionId)) || cleanText(sessionId) || "session",
    cleanText(props && (props.variant_id || props.variantId || props.content_id || props.contentId)) || "variant",
    cleanText(props && (props.button_text || props.buttonText || props.cta_text || props.ctaText)) || "button",
  ].join(":");
  const shouldSuppressDuplicateAddToCart = (eventType, eventProps) => {
    const normalizedEventType = cleanText(eventType);
    if (normalizedEventType !== "add_to_cart" && normalizedEventType !== "AddToCart") {
      return false;
    }
    const dedupeKey = buildAddToCartDedupeKey(eventProps || {});
    const now = Date.now();
    const lastTrackedAt = addToCartDedupeKeys[dedupeKey] || 0;
    if (lastTrackedAt && now - lastTrackedAt < 1000) {
      window.__mosAddToCartDuplicateCount = (window.__mosAddToCartDuplicateCount || 0) + 1;
      return true;
    }
    addToCartDedupeKeys[dedupeKey] = now;
    eventProps.dedupe_key = dedupeKey;
    eventProps.dedupeKey = dedupeKey;
    eventProps.dedupe_strategy = "session_add_to_cart_click";
    return false;
  };
  const trackEvent = (eventType, props) => {
    const canonicalEventId = cleanText(props && props.eventId) || buildCanonicalEventId(eventType);
    const eventProps = {
      eventId: canonicalEventId,
      ...resolveQuizManifestEventDefaults(eventType, props || {}),
      ...(props || {}),
    };
    if (shouldSuppressDuplicateQuizCompleted(eventType, eventProps)) {
      return;
    }
    if (shouldSuppressDuplicateAddToCart(eventType, eventProps)) {
      return;
    }
    const mappedCaptures = resolveMappedMetaEvents(eventType, eventProps).map((capture, index) => ({
      ...capture,
      eventId: cleanText(capture.eventId) || buildMetaEventId(capture.eventName, eventType, index),
    }));
    trackMetaPixelCaptures(mappedCaptures, eventProps);
    const posthogFlushPromise = trackPostHogEvent(eventType, eventProps, mappedCaptures);
    const internalTrackingPayload = JSON.stringify({
        events: [
          {
            eventId: canonicalEventId,
            eventType,
            occurredAt: new Date().toISOString(),
            publicationId: config.publicationId,
            pageId: config.pageId,
            visitorId,
            sessionId,
            path: window.location.pathname + window.location.search,
            referrer: document.referrer || undefined,
            utm: getUtmParams(),
            props: {
              ...resolveRuntimeContextProps(eventProps),
              ...resolveMetaAttributionProps(window.location.href),
              fromPageId: config.pageId,
              slug: config.pageSlug,
              pageStage: config.pageStage,
              artifactMode: "html_deploy",
              htmlArtifactKind: cleanText(config.htmlArtifactKind),
              htmlDeploySchemaVersion: cleanText(config.htmlDeploySchemaVersion),
              metaEvents: mappedCaptures.map((capture) => ({
                eventName: capture.eventName,
                eventId: capture.eventId,
              })),
              ...eventProps,
            },
          },
        ],
      });
    recordInternalTrackingValidationPayload(internalTrackingPayload);
    const internalTrackingPromise = postTrackingPayload(
      internalTrackingPayload,
      { preferFetch: cleanText(eventType) === "pre_sales_to_sales_click" },
    );
    if (isNavigationCriticalPostHogEvent(eventType)) {
      return Promise.race([
        Promise.allSettled([
          internalTrackingPromise || Promise.resolve(),
          posthogFlushPromise || Promise.resolve(),
          waitForMetaPixelTrackedEventFlush(),
        ]),
        waitMs(POSTHOG_NAVIGATION_EVENT_LOAD_TIMEOUT_MS),
      ]);
    }
    return Promise.resolve();
  };
  const installTrackEventBridge = () => {
    if (window.__mosStandaloneTrackEventBridgeInstalled) return;
    window.__mosStandaloneTrackEventBridgeInstalled = true;
    window.MOSStandaloneAnalytics = {
      trackEvent,
      waitForNavigationFlush: waitForTrackingNavigationFlush,
    };
    window.addEventListener("mos:track-event", (event) => {
      const detail = event && event.detail;
      if (!isRecord(detail)) return;
      const eventType = cleanText(detail.eventType);
      if (!eventType) return;
      const props = isRecord(detail.props) ? detail.props : {};
      trackEvent(eventType, props);
    });
  };
  const resolveWebVitalRating = (metricName, metricValue) => {
    const thresholds = {
      FCP: [1800, 3000],
      LCP: [2500, 4000],
      CLS: [0.1, 0.25],
      INP: [200, 500],
      TTFB: [800, 1800],
    };
    const metricThresholds = thresholds[String(metricName || "").trim().toUpperCase()];
    if (!metricThresholds || typeof metricValue !== "number" || !Number.isFinite(metricValue)) {
      return null;
    }
    if (metricValue <= metricThresholds[0]) return "good";
    if (metricValue <= metricThresholds[1]) return "needs_improvement";
    return "poor";
  };
  const trackWebVital = (() => {
    const sentMetricNames = new Set();
    return (metricName, metricValue, extraProps) => {
      const normalizedMetricName = cleanText(metricName && String(metricName).toUpperCase());
      if (!normalizedMetricName) return;
      if (typeof metricValue !== "number" || !Number.isFinite(metricValue)) return;
      if (sentMetricNames.has(normalizedMetricName)) return;
      sentMetricNames.add(normalizedMetricName);
      const normalizedMetricValue =
        normalizedMetricName === "CLS"
          ? Number(metricValue.toFixed(4))
          : Number(metricValue.toFixed(2));
      trackEvent("web_vital_recorded", {
        pageStage: config.pageStage,
        metricName: normalizedMetricName,
        metricValue: normalizedMetricValue,
        metricUnit: normalizedMetricName === "CLS" ? "unitless" : "ms",
        metricRating: resolveWebVitalRating(normalizedMetricName, metricValue),
        ...(isRecord(extraProps) ? extraProps : {}),
      });
    };
  })();
  const initializeWebVitalsTracking = () => {
    if (window.__mosStandaloneImportedHtmlWebVitalsInitialized) return;
    window.__mosStandaloneImportedHtmlWebVitalsInitialized = true;

    const supportedEntryTypes =
      typeof PerformanceObserver === "function" &&
      Array.isArray(PerformanceObserver.supportedEntryTypes)
      ? PerformanceObserver.supportedEntryTypes
      : [];
    const supportsEntryType = (entryType) => supportedEntryTypes.includes(entryType);
    const lifecycleListeners = [];
    const registerFinalize = (handler) => {
      if (typeof handler !== "function") return;
      lifecycleListeners.push(handler);
    };
    const flushFinalizers = () => {
      pageLifecycleFinalizing = true;
      while (lifecycleListeners.length) {
        const listener = lifecycleListeners.shift();
        try {
          listener && listener();
        } catch (error) {
          console.error("[HtmlDeployArtifact] Failed to finalize web vital.", error);
        }
      }
    };

    window.addEventListener("pagehide", flushFinalizers, { once: true });
    document.addEventListener(
      "visibilitychange",
      () => {
        if (document.visibilityState === "hidden") {
          flushFinalizers();
        }
      },
      { once: true },
    );

    try {
      const navEntry =
        typeof performance.getEntriesByType === "function"
          ? performance.getEntriesByType("navigation")[0]
          : null;
      if (navEntry && typeof navEntry.responseStart === "number" && navEntry.responseStart >= 0) {
        trackWebVital("TTFB", navEntry.responseStart);
      }
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to record TTFB.", error);
    }

    if (typeof PerformanceObserver !== "function") return;

    if (supportsEntryType("paint")) {
      try {
        const fcpObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry && entry.name === "first-contentful-paint" && typeof entry.startTime === "number") {
              trackWebVital("FCP", entry.startTime);
              fcpObserver.disconnect();
              break;
            }
          }
        });
        fcpObserver.observe({ type: "paint", buffered: true });
      } catch (error) {
        console.error("[HtmlDeployArtifact] Failed to observe FCP.", error);
      }
    }

    if (supportsEntryType("largest-contentful-paint")) {
      try {
        let lcpValue = null;
        const lcpObserver = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const lastEntry = entries[entries.length - 1];
          if (lastEntry && typeof lastEntry.startTime === "number") {
            lcpValue = lastEntry.startTime;
          }
        });
        lcpObserver.observe({ type: "largest-contentful-paint", buffered: true });
        registerFinalize(() => {
          lcpObserver.disconnect();
          if (typeof lcpValue === "number") {
            trackWebVital("LCP", lcpValue);
          }
        });
      } catch (error) {
        console.error("[HtmlDeployArtifact] Failed to observe LCP.", error);
      }
    }

    if (supportsEntryType("layout-shift")) {
      try {
        let clsValue = 0;
        const clsObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (!entry || entry.hadRecentInput) continue;
            if (typeof entry.value === "number" && Number.isFinite(entry.value)) {
              clsValue += entry.value;
            }
          }
        });
        clsObserver.observe({ type: "layout-shift", buffered: true });
        registerFinalize(() => {
          clsObserver.disconnect();
          trackWebVital("CLS", clsValue);
        });
      } catch (error) {
        console.error("[HtmlDeployArtifact] Failed to observe CLS.", error);
      }
    }

    if (supportsEntryType("event")) {
      try {
        let inpValue = null;
        const inpObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            const duration = entry && typeof entry.duration === "number" ? entry.duration : null;
            if (duration === null || !Number.isFinite(duration)) continue;
            if (inpValue === null || duration > inpValue) {
              inpValue = duration;
            }
          }
        });
        inpObserver.observe({ type: "event", buffered: true, durationThreshold: 40 });
        registerFinalize(() => {
          inpObserver.disconnect();
          if (typeof inpValue === "number") {
            trackWebVital("INP", inpValue);
          }
        });
      } catch (error) {
        console.error("[HtmlDeployArtifact] Failed to observe INP.", error);
      }
    }
  };
  const normalizeSelection = (selection) => {
    if (!isRecord(selection)) return null;
    const entries = Object.entries(selection)
      .map(([key, value]) => {
        const normalizedKey = cleanText(key);
        const normalizedValue = cleanText(typeof value === "string" ? value : String(value || ""));
        if (!normalizedKey || !normalizedValue) return null;
        return [normalizedKey, normalizedValue];
      })
      .filter(Boolean);
    if (!entries.length) return null;
    return Object.fromEntries(entries);
  };
  const normalizePurchaseMode = (value) => {
    const normalized = cleanText(typeof value === "string" ? value : null);
    if (!normalized) return null;
    const lowered = normalized.toLowerCase();
    if (lowered === "subscribe") return "subscribe";
    if (["one-time", "one_time", "one time", "onetime"].includes(lowered)) return "one-time";
    return null;
  };
  const detectCheckoutPurchaseMode = () => {
    const hiddenInput = document.getElementById("mos-selected-purchase-mode");
    if (
      hiddenInput instanceof HTMLInputElement ||
      hiddenInput instanceof HTMLTextAreaElement ||
      hiddenInput instanceof HTMLSelectElement
    ) {
      const hiddenMode = normalizePurchaseMode(hiddenInput.value);
      if (hiddenMode) return hiddenMode;
    }
    const quantitySelector = document.getElementById("quantity-selector");
    if (quantitySelector instanceof HTMLElement) {
      const attributeMode = normalizePurchaseMode(quantitySelector.getAttribute("data-mode"));
      if (attributeMode) return attributeMode;
    }
    return null;
  };
  const augmentSelectionWithCheckoutContext = (selection) => {
    const normalizedSelection = normalizeSelection(selection) || {};
    const explicitPurchaseMode = normalizePurchaseMode(normalizedSelection.PurchaseMode);
    if (explicitPurchaseMode) {
      return {
        ...normalizedSelection,
        PurchaseMode: explicitPurchaseMode,
      };
    }
    const detectedPurchaseMode = detectCheckoutPurchaseMode();
    if (detectedPurchaseMode) {
      return {
        ...normalizedSelection,
        PurchaseMode: detectedPurchaseMode,
      };
    }
    return Object.keys(normalizedSelection).length ? normalizedSelection : null;
  };
  const stripCheckoutSelectionContext = (selection) => {
    const normalizedSelection = normalizeSelection(selection);
    if (!normalizedSelection) return null;
    const entries = Object.entries(normalizedSelection).filter(
      ([key]) => key.trim().toLowerCase() !== "purchasemode",
    );
    if (!entries.length) return null;
    return Object.fromEntries(entries);
  };
  const normalizeVariant = (variant) => {
    if (!isRecord(variant)) return null;
    const id = cleanText(variant.id);
    if (!id) return null;
    return {
      id,
      provider: cleanText(typeof variant.provider === "string" ? variant.provider.toLowerCase() : null),
      price: typeof variant.price === "number" ? variant.price : null,
      currency: cleanText(variant.currency),
      optionValues: normalizeSelection(variant.optionValues || variant.option_values || null),
    };
  };
  const variants = Array.isArray(config.variants)
    ? config.variants.map(normalizeVariant).filter(Boolean)
    : [];
  const preparedCheckoutCache = {};
  const preparedCheckoutInFlight = {};
  const preparedCheckoutTransitionIds = {};
  const PREPARED_CHECKOUT_TTL_MS = 10 * 60 * 1000;
  const PREPARED_CHECKOUT_POLL_INTERVAL_MS = 150;
  const PREPARED_CHECKOUT_POLL_TIMEOUT_MS = 10 * 1000;
  let warmCheckoutBindingsTimeout = null;
  let checkoutWarmListenersBound = false;
  const resolvePageViewEventType = () => {
    if (config.pageStage === "pre_sales") return "pre_sales_page_view";
    if (config.pageStage === "sales") return "sales_page_view";
    if (config.pageStage === "checkout") return "checkout_page_view";
    if (config.pageStage === "thank_you") return "thank_you_page_view";
    return "custom_page_view";
  };
  const trackInitialPageView = () => {
    const trackedPageViewIds = window.__mosStandaloneImportedHtmlTrackedPageViewIds || [];
    if (trackedPageViewIds.includes(config.pageId)) return;
    trackedPageViewIds.push(config.pageId);
    window.__mosStandaloneImportedHtmlTrackedPageViewIds = trackedPageViewIds;
    const presaleSignal = config.pageStage === "sales" ? resolvePresaleAttribution() : null;
    const pageViewProps = {
      pageStage: config.pageStage,
      ...(presaleSignal ? { fromPresale: true, presaleSignal } : {}),
    };
    trackEvent(resolvePageViewEventType(), pageViewProps);
    if (config.pageStage === "pre_sales") {
      trackEvent("presell_page_view", {
        ...pageViewProps,
        rmbcEventName: "EnteredPresales",
      });
    }
    if (config.pageStage === "sales") {
      trackEvent("offer_page_view", pageViewProps);
    }
  };
  const SCROLL_DEPTH_MILESTONES = [10, 25, 50, 75, 90, 100];
  const QUALIFIED_ACTIVE_TIME_MS = 3000;
  const QUALIFIED_SCROLL_DEPTH_PCT = 25;
  const scrollDepthStateByKey = {};
  const observedViewTargetKeys = {};
  const interactionListenerKeys = {};
  let interactionSequence = 0;
  let maxScrollDepthPct = 0;
  let scrollTrackingScheduled = false;
  let qualifiedSessionTracked = false;
  let engagementTrackingInitialized = false;
  let activeStartedAt = Date.now();
  let activeAccumulatedMs = 0;
  const currentActiveTimeMs = () => {
    if (document.visibilityState === "hidden") return activeAccumulatedMs;
    return activeAccumulatedMs + Math.max(0, Date.now() - activeStartedAt);
  };
  const pauseActiveTime = () => {
    if (document.visibilityState === "hidden") return;
    activeAccumulatedMs = currentActiveTimeMs();
  };
  const resumeActiveTime = () => {
    activeStartedAt = Date.now();
  };
  const trackQualifiedSession = (reason) => {
    if (qualifiedSessionTracked) return;
    qualifiedSessionTracked = true;
    trackEvent("qualified_session", {
      reason,
      activeTimeMs: Math.round(currentActiveTimeMs()),
      maxScrollDepthPct,
      qualificationActiveTimeMs: QUALIFIED_ACTIVE_TIME_MS,
      qualificationScrollDepthPct: QUALIFIED_SCROLL_DEPTH_PCT,
    });
  };
  const evaluateQualifiedSession = (reason) => {
    if (currentActiveTimeMs() >= QUALIFIED_ACTIVE_TIME_MS || maxScrollDepthPct >= QUALIFIED_SCROLL_DEPTH_PCT) {
      trackQualifiedSession(reason);
    }
  };
  let lastScrollDepthElement = null;
  const resolveScrollDepthStateKey = () => {
    return [
      cleanText(config.pageId) || "page",
      window.location.pathname || "",
      window.location.search || "",
      window.location.hash || "",
    ].join("|");
  };
  const resolveScrollDepthState = () => {
    const key = resolveScrollDepthStateKey();
    if (!scrollDepthStateByKey[key]) {
      scrollDepthStateByKey[key] = {
        maxScrollDepthPct: 0,
        trackedMilestones: {},
      };
    }
    return scrollDepthStateByKey[key];
  };
  const calculateElementScrollDepthPct = (element) => {
    if (!(element instanceof HTMLElement)) return null;
    if (element.isConnected === false) return null;
    const scrollHeight = element.scrollHeight || 0;
    const viewportHeight = element.clientHeight || 0;
    if (!scrollHeight || !viewportHeight) return null;
    if (viewportHeight >= scrollHeight) return null;
    const scrollTop = element.scrollTop || 0;
    return Math.max(0, Math.min(100, Math.round(((scrollTop + viewportHeight) / scrollHeight) * 100)));
  };
  const calculateWindowScrollDepthPct = () => {
    const doc = document.documentElement;
    const body = document.body;
    const scrollTop = window.scrollY || doc.scrollTop || (body && body.scrollTop) || 0;
    const viewportHeight = window.innerHeight || doc.clientHeight || 0;
    const scrollHeight = Math.max(
      doc.scrollHeight || 0,
      body ? body.scrollHeight || 0 : 0,
      doc.offsetHeight || 0,
      body ? body.offsetHeight || 0 : 0,
      viewportHeight,
    );
    if (!scrollHeight || viewportHeight >= scrollHeight) return null;
    return Math.max(0, Math.min(100, Math.round(((scrollTop + viewportHeight) / scrollHeight) * 100)));
  };
  const calculateScrollDepthPct = () => {
    const windowPct = calculateWindowScrollDepthPct();
    const elementPct = calculateElementScrollDepthPct(lastScrollDepthElement);
    if (typeof elementPct === "number" && Number.isFinite(elementPct)) {
      return typeof windowPct === "number" && Number.isFinite(windowPct)
        ? Math.max(windowPct, elementPct)
        : elementPct;
    }
    return windowPct;
  };
  const resolveScrollDepthElement = (event) => {
    const target = event && event.target;
    if (!(target instanceof HTMLElement)) return null;
    const maxScroll = Math.max(0, (target.scrollHeight || 0) - (target.clientHeight || 0));
    if (maxScroll <= 8) return null;
    return target;
  };
  const handleScrollDepthTracking = () => {
    scrollTrackingScheduled = false;
    const scrollDepthPct = calculateScrollDepthPct();
    if (typeof scrollDepthPct !== "number" || !Number.isFinite(scrollDepthPct)) {
      return;
    }
    const scrollDepthState = resolveScrollDepthState();
    scrollDepthState.maxScrollDepthPct = Math.max(
      scrollDepthState.maxScrollDepthPct,
      scrollDepthPct,
    );
    maxScrollDepthPct = Math.max(maxScrollDepthPct, scrollDepthState.maxScrollDepthPct);
    for (const milestone of SCROLL_DEPTH_MILESTONES) {
      if (
        scrollDepthState.maxScrollDepthPct >= milestone &&
        scrollDepthState.trackedMilestones[milestone] !== true
      ) {
        scrollDepthState.trackedMilestones[milestone] = true;
        trackEvent("scroll_depth", {
          scrollDepthPct: milestone,
          maxScrollDepthPct: scrollDepthState.maxScrollDepthPct,
          activeTimeMs: Math.round(currentActiveTimeMs()),
        });
      }
    }
    evaluateQualifiedSession("scroll_depth");
  };
  const scheduleScrollDepthTracking = (event) => {
    const scrollElement = resolveScrollDepthElement(event);
    if (scrollElement) {
      lastScrollDepthElement = scrollElement;
    }
    if (scrollTrackingScheduled) return;
    scrollTrackingScheduled = true;
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(handleScrollDepthTracking);
      return;
    }
    window.setTimeout(handleScrollDepthTracking, 0);
  };
  const initializeEngagementTracking = () => {
    if (engagementTrackingInitialized) return;
    engagementTrackingInitialized = true;
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        pauseActiveTime();
        return;
      }
      resumeActiveTime();
    });
    window.addEventListener("pagehide", pauseActiveTime);
    window.addEventListener("scroll", scheduleScrollDepthTracking, { passive: true, capture: true });
    document.addEventListener("scroll", scheduleScrollDepthTracking, { passive: true, capture: true });
    window.addEventListener("resize", scheduleScrollDepthTracking);
    window.setInterval(() => evaluateQualifiedSession("active_time"), 1000);
  };
  const observationTargetsFromManifest = () => {
    const targets = [];
    const addTarget = (eventType, kind, target) => {
      if (!target || typeof target !== "object") return;
      const id = cleanText(target.id);
      const selector = cleanText(target.selector);
      if (!id || !selector) return;
      targets.push({
        eventType,
        kind,
        id,
        selector,
        label: cleanText(target.label),
        proofType: cleanText(target.proofType),
        sectionId: cleanText(target.sectionId),
        ctaPosition: Number.isFinite(Number(target.ctaPosition)) ? Number(target.ctaPosition) : undefined,
        declaredProps: buildDeclaredTargetProps(target),
      });
    };
    const manifest = config.manifest || {};
    const htmlArtifactKind = cleanText(config.htmlArtifactKind);
    const hasExplicitCtaTargets = Array.isArray(manifest.ctas) && manifest.ctas.length > 0;
    if (Array.isArray(manifest.sections)) {
      manifest.sections.forEach((target) => addTarget("section_view", "section", target));
    }
    if (Array.isArray(manifest.proofs)) {
      manifest.proofs.forEach((target) => addTarget("proof_view", "proof", target));
      if (htmlArtifactKind === "quiz") {
        manifest.proofs.forEach((target) => addTarget("quiz_proof_viewed", "quiz_proof", target));
      }
    }
    if (Array.isArray(manifest.ctas)) {
      manifest.ctas.forEach((target) => addTarget("cta_view", "cta", target));
      if (htmlArtifactKind === "quiz") {
        manifest.ctas.forEach((target) => addTarget("quiz_cta_viewed", "quiz_cta", target));
      }
    }
    if (Array.isArray(manifest.offerStacks)) {
      manifest.offerStacks.forEach((target) => addTarget("offer_stack_view", "offer_stack", target));
    }
    if (Array.isArray(manifest.valueStacks)) {
      manifest.valueStacks.forEach((target) => addTarget("value_stack_view", "value_stack", target));
    }
    if (Array.isArray(manifest.priceReveals)) {
      manifest.priceReveals.forEach((target) => addTarget("price_reveal_view", "price_reveal", target));
    }
    if (Array.isArray(manifest.guarantees)) {
      manifest.guarantees.forEach((target) => addTarget("guarantee_view", "guarantee", target));
    }
    if (Array.isArray(manifest.trustElements)) {
      manifest.trustElements.forEach((target) => addTarget("trust_element_view", "trust_element", target));
    }
    if (Array.isArray(manifest.quizLeads)) {
      manifest.quizLeads.forEach((target) => addTarget("quiz_lead_viewed", "quiz_lead", target));
    }
    if (Array.isArray(manifest.quizQuestions)) {
      manifest.quizQuestions.forEach((target) => addTarget("quiz_question_viewed", "quiz_question", target));
    }
    if (Array.isArray(manifest.quizOptions)) {
      manifest.quizOptions.forEach((target) => addTarget("quiz_option_presented", "quiz_option", target));
    }
    if (Array.isArray(manifest.quizResults)) {
      manifest.quizResults.forEach((target) => addTarget("quiz_result_viewed", "quiz_result", target));
    }
    if (Array.isArray(manifest.quizMechanisms)) {
      manifest.quizMechanisms.forEach((target) => addTarget("quiz_mechanism_viewed", "quiz_mechanism", target));
    }
    if (Array.isArray(manifest.quizRecommendations)) {
      manifest.quizRecommendations.forEach((target) => addTarget("quiz_recommendation_viewed", "quiz_recommendation", target));
    }
    if (!hasExplicitCtaTargets && Array.isArray(manifest.bindings)) {
      manifest.bindings.forEach((binding) => {
        if (!binding || typeof binding !== "object") return;
        const id = cleanText(binding.id);
        const selector = cleanText(binding.selector);
        if (!id || !selector) return;
        targets.push({
          eventType: "cta_view",
          kind: "cta",
          id,
          selector,
          bindingType: cleanText(binding.type),
          trackEventType: cleanText(binding.trackEventType),
        });
      });
    }
    return targets;
  };
  const trackObservedViewTarget = (target, element, index) => {
    const key = [target.eventType, target.id, String(index)].join(":");
    if (observedViewTargetKeys[key] === true) return;
    observedViewTargetKeys[key] = true;
    trackEvent(target.eventType, {
      targetKind: target.kind,
      targetId: target.id,
      selector: target.selector,
      label: target.label || undefined,
      bindingType: target.bindingType || undefined,
      trackEventType: target.trackEventType || undefined,
      text: normalizeText(element.textContent || "").slice(0, 160) || undefined,
      activeTimeMs: Math.round(currentActiveTimeMs()),
      maxScrollDepthPct,
      depthPct: maxScrollDepthPct,
      depth_pct: maxScrollDepthPct,
      ...(target.kind === "cta"
        ? {
            ctaId: target.id,
            cta_id: target.id,
            ctaPosition: target.ctaPosition || index + 1,
            cta_position: target.ctaPosition || index + 1,
          }
        : {}),
      ...(target.kind === "section"
        ? {
            sectionId: target.sectionId || target.id,
            section_id: target.sectionId || target.id,
          }
        : {}),
      ...(target.kind === "proof"
        ? {
            proofId: target.id,
            proof_id: target.id,
            proofType: target.proofType || undefined,
            proof_type: target.proofType || undefined,
            sectionId: target.sectionId || undefined,
            section_id: target.sectionId || undefined,
          }
        : {}),
      ...(target.kind === "offer_stack" ? { offerStackId: target.id, offer_id: target.id } : {}),
      ...(target.kind === "value_stack" ? { valueStackId: target.id } : {}),
      ...(target.kind === "price_reveal" ? { priceRevealId: target.id } : {}),
      ...(target.kind === "guarantee" ? { guaranteeId: target.id, guarantee_id: target.id } : {}),
      ...(target.kind === "trust_element" ? { trustElementId: target.id } : {}),
      ...(target.kind === "quiz_lead" ? { quizLeadId: target.id, quiz_lead_id: target.id } : {}),
      ...(target.kind === "quiz_question" ? { questionId: target.id, question_id: target.id } : {}),
      ...(target.kind === "quiz_option" ? { optionId: target.id, option_id: target.id } : {}),
      ...(target.kind === "quiz_result" ? { resultId: target.id, result_id: target.id } : {}),
      ...(target.kind === "quiz_mechanism" ? { mechanismId: target.id, mechanism_id: target.id } : {}),
      ...(target.kind === "quiz_proof" ? { proofId: target.id, proof_id: target.id } : {}),
      ...(target.kind === "quiz_recommendation"
        ? { recommendationId: target.id, recommendation_id: target.id }
        : {}),
      ...(target.kind === "quiz_cta"
        ? {
            ctaId: target.id,
            cta_id: target.id,
            ctaPosition: target.ctaPosition || index + 1,
            cta_position: target.ctaPosition || index + 1,
          }
        : {}),
      ...(target.declaredProps || {}),
    });
  };
  const initializeViewTracking = () => {
    if (typeof window.IntersectionObserver !== "function") return;
    const targets = observationTargetsFromManifest();
    if (!targets.length) return;
    const observer = new window.IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting || entry.intersectionRatio < 0.5) return;
          const targetConfig = entry.target.__mosViewTrackingTarget;
          const targetIndex = entry.target.__mosViewTrackingIndex || 0;
          if (targetConfig) {
            trackObservedViewTarget(targetConfig, entry.target, targetIndex);
          }
          observer.unobserve(entry.target);
        });
      },
      { threshold: [0.5] },
    );
    targets.forEach((target) => {
      const matches = Array.from(document.querySelectorAll(target.selector));
      matches.forEach((element, index) => {
        if (!(element instanceof HTMLElement)) return;
        const key = [target.eventType, target.id, String(index)].join(":");
        if (observedViewTargetKeys[key] === true) return;
        element.__mosViewTrackingTarget = target;
        element.__mosViewTrackingIndex = index;
        observer.observe(element);
      });
    });
  };
  const interactionTargetsFromManifest = () => {
    const targets = [];
    const addTarget = (eventType, kind, target) => {
      if (!target || typeof target !== "object") return;
      const id = cleanText(target.id);
      const selector = cleanText(target.selector);
      if (!id || !selector) return;
      targets.push({
        eventType,
        kind,
        id,
        selector,
        label: cleanText(target.label),
        event: target.event === "input" || target.event === "change" ? target.event : "click",
        source: target.source === "text" || target.source === "checked" ? target.source : "value",
        interactionType: cleanText(target.interactionType) || kind,
        submitOnSelect: target.submitOnSelect === true,
        declaredProps: buildDeclaredTargetProps(target),
      });
    };
    const manifest = config.manifest || {};
    if (Array.isArray(manifest.quizOptions)) {
      manifest.quizOptions.forEach((target) => addTarget("quiz_option_selected", "quiz_option", target));
    }
    if (Array.isArray(manifest.quizSubmissions)) {
      manifest.quizSubmissions.forEach((target) => addTarget("quiz_question_submitted", "quiz_submission", target));
    }
    if (Array.isArray(manifest.selectors)) {
      manifest.selectors.forEach((target) => addTarget("selector_interaction", "selector", target));
    }
    if (Array.isArray(manifest.productDetails)) {
      manifest.productDetails.forEach((target) =>
        addTarget("product_detail_interaction", "product_detail", target),
      );
    }
    return targets;
  };
  const readInteractionValue = (element, source) => {
    if (source === "checked") {
      return element instanceof HTMLInputElement ? (element.checked ? "checked" : "unchecked") : undefined;
    }
    if (source === "text") {
      return normalizeText(element.textContent || "") || undefined;
    }
    if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
      return normalizeText(element.value || "") || undefined;
    }
    return normalizeText(element.textContent || "") || undefined;
  };
  const selectedValueLooksSubscribed = (value) => {
    const normalized = String(value || "").trim().toLowerCase();
    return normalized === "subscribe" || normalized === "subscription" || normalized.includes("subscribe");
  };
  const trackInteractionTarget = (target, element) => {
    interactionSequence += 1;
    const selectedValue = readInteractionValue(element, target.source);
    const props = {
      targetKind: target.kind,
      targetId: target.id,
      selector: target.selector,
      label: target.label || undefined,
      interactionType: target.interactionType,
      ...(target.declaredProps || {}),
      selectedValue,
      selected_value: selectedValue,
      text: normalizeText(element.textContent || "").slice(0, 160) || undefined,
      activeTimeMs: Math.round(currentActiveTimeMs()),
      maxScrollDepthPct,
      interactionSequence,
      ...(target.kind === "selector" ? { selectorId: target.id } : {}),
      ...(target.kind === "product_detail" ? { productDetailId: target.id } : {}),
      ...(target.kind === "quiz_option" ? { optionId: target.id, option_id: target.id } : {}),
      ...(target.kind === "quiz_submission" ? { questionSubmitId: target.id, question_submit_id: target.id } : {}),
    };
    trackEvent(target.eventType, props);
    if (target.eventType === "quiz_option_selected") {
      const autoSubmit = target.submitOnSelect === true || !isMultiSelectQuestion(null, props);
      if (autoSubmit) {
        trackEvent("quiz_question_submitted", props);
      }
    }
    if (target.eventType === "selector_interaction" && selectedValueLooksSubscribed(selectedValue)) {
      trackEvent("subscription_selected", {
        ...props,
        subscription_flag: true,
      });
    }
    evaluateQualifiedSession("element_interaction");
  };
  const initializeInteractionTracking = () => {
    const targets = interactionTargetsFromManifest();
    if (!targets.length) return;
    targets.forEach((target) => {
      const matches = Array.from(document.querySelectorAll(target.selector));
      matches.forEach((element, index) => {
        if (!(element instanceof HTMLElement)) return;
        const key = [target.eventType, target.id, String(index), target.event].join(":");
        if (interactionListenerKeys[key] === true) return;
        interactionListenerKeys[key] = true;
        if (target.kind === "quiz_option" || target.kind === "quiz_submission") {
          element.dataset.mosDirectControlTracking = "true";
        }
        element.addEventListener(target.event, () => trackInteractionTarget(target, element), {
          passive: true,
        });
      });
    });
  };
  const addToCartTargetsFromManifest = () => {
    const manifest = config.manifest || {};
    const rawTargets = Array.isArray(manifest.addToCartTargets)
      ? manifest.addToCartTargets
      : (Array.isArray(manifest.add_to_cart_targets) ? manifest.add_to_cart_targets : []);
    return rawTargets
      .map((target) => {
        if (!target || typeof target !== "object") return null;
        const id = cleanText(target.id);
        const selector = cleanText(target.selector);
        if (!id || !selector) return null;
        return {
          id,
          selector,
          label: cleanText(target.label),
          event: target.event === "input" || target.event === "change" ? target.event : "click",
          trackEventType: cleanText(target.trackEventType || target.track_event_type) || "add_to_cart",
          ctaPosition: Number.isFinite(Number(target.ctaPosition || target.cta_position))
            ? Number(target.ctaPosition || target.cta_position)
            : undefined,
          variantId: cleanText(target.variantId || target.variant_id || target.productVariantId || target.product_variant_id),
          declaredProps: buildDeclaredTargetProps(target),
        };
      })
      .filter(Boolean);
  };
  const resolveAddToCartTargetVariantId = (target, element) => {
    const targetVariantId = cleanText(target && target.variantId);
    if (targetVariantId) return targetVariantId;
    if (!(element instanceof HTMLElement)) return "";
    return cleanText(
      element.getAttribute("data-variant-id") ||
        element.getAttribute("data-product-variant-id") ||
        element.getAttribute("data-price-point-id") ||
        element.dataset.variantId ||
        element.dataset.productVariantId ||
        element.dataset.pricePointId,
    );
  };
  const resolveAddToCartTargetVariant = (target, element, variantId) => {
    const exactVariantId = cleanText(variantId);
    if (exactVariantId) {
      const exactVariant = variants.find((candidate) => candidate.id === exactVariantId) || null;
      if (exactVariant) return exactVariant;
    }
    const manifest = config.manifest || {};
    const checkoutBindings = Array.isArray(manifest.bindings)
      ? manifest.bindings.filter((binding) => binding && binding.type === "checkout" && binding.checkout)
      : [];
    for (const binding of checkoutBindings) {
      try {
        const checkoutState = resolveCheckoutState(binding);
        if (checkoutState && checkoutState.variant) return checkoutState.variant;
      } catch (_error) {
        // Checkout activation reports resolver failures; add-to-cart keeps its own event deterministic.
      }
    }
    if (variants.length === 1) return variants[0];
    return null;
  };
  const trackAddToCartTarget = (target, element, index) => {
    const buttonText = normalizeText(element.textContent || "");
    const variantId = resolveAddToCartTargetVariantId(target, element);
    const variant = resolveAddToCartTargetVariant(target, element, variantId);
    const ctaPosition = target.ctaPosition || index + 1;
    const metaAddToCartEventId = consumeMetaAddToCartTrackingEventId(variantId);
    trackEvent(target.trackEventType || "add_to_cart", {
      fromStage: config.pageStage,
      from_stage: config.pageStage,
      toStage: "cart",
      to_stage: "cart",
      targetId: target.id,
      target_id: target.id,
      selector: target.selector,
      label: target.label || undefined,
      bindingId: target.id,
      binding_id: target.id,
      ctaId: target.id,
      cta_id: target.id,
      ctaPosition,
      cta_position: ctaPosition,
      ctaText: buttonText || undefined,
      cta_text: buttonText || undefined,
      buttonText: buttonText || undefined,
      button_text: buttonText || undefined,
      activeTimeMs: Math.round(currentActiveTimeMs()),
      maxScrollDepthPct,
      metaAddToCartEventId,
      meta_add_to_cart_event_id: metaAddToCartEventId,
      ...(variantId ? { variantId, variant_id: variantId, contentId: variantId, content_id: variantId } : {}),
      ...(variant && typeof variant.price === "number" ? { value: Math.round(variant.price) / 100 } : {}),
      ...(variant && variant.currency ? { currency: variant.currency } : {}),
      ...(target.declaredProps || {}),
    });
  };
  const initializeAddToCartTracking = () => {
    const targets = addToCartTargetsFromManifest();
    if (!targets.length) return;
    targets.forEach((target) => {
      const windowKey = [target.id, target.selector, target.event, "window"].join(":");
      window.__mosAddToCartWindowTargetKeys = window.__mosAddToCartWindowTargetKeys || {};
      if (window.__mosAddToCartWindowTargetKeys[windowKey] !== true) {
        window.__mosAddToCartWindowTargetKeys[windowKey] = true;
        window.addEventListener(target.event, (event) => {
          try {
            const eventTarget = event && event.target;
            const element = eventTarget instanceof Element ? eventTarget.closest(target.selector) : null;
            if (element instanceof HTMLElement) {
              trackAddToCartTarget(target, element, 0);
            }
          } catch (_error) {
            // Invalid selectors are reported by the explicit querySelectorAll check below.
          }
        }, {
          capture: true,
          passive: true,
        });
      }
      const matches = Array.from(document.querySelectorAll(target.selector));
      if (matches.length < 1) {
        console.error(
          "[HtmlDeployArtifact] Add-to-cart target '" +
            String(target.id || "unknown") +
            "' selector '" +
            target.selector +
            "' matched no elements.",
        );
        return;
      }
      matches.forEach((element, index) => {
        if (!(element instanceof HTMLElement)) return;
        const key = [target.id, target.selector, String(index), target.event].join(":");
        if (element.dataset.mosAddToCartTargetBound === key) return;
        element.dataset.mosAddToCartTargetBound = key;
        element.addEventListener(target.event, () => trackAddToCartTarget(target, element, index), {
          capture: true,
          passive: true,
        });
      });
    });
  };
  const initializeEngagementTrackingSafely = () => {
    try {
      initializeEngagementTracking();
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to initialize engagement tracking.", error);
    }
  };
  const initializeViewTrackingSafely = () => {
    try {
      initializeViewTracking();
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to initialize view tracking.", error);
    }
  };
  const initializeInteractionTrackingSafely = () => {
    try {
      initializeInteractionTracking();
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to initialize interaction tracking.", error);
    }
  };
  const initializeAddToCartTrackingSafely = () => {
    try {
      initializeAddToCartTracking();
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to initialize add-to-cart tracking.", error);
    }
  };
  const handleCheckoutReturn = () => {
    const checkoutStatus = checkoutStatusFromLocation();
    if (!checkoutStatus) return;
    const pendingPurchaseKey = pendingMetaPurchaseStorageKey(sessionId, config.funnelSlug);
    const pendingPurchase = readPendingMetaPurchase(pendingPurchaseKey);
    if (checkoutStatus === "success") {
      trackEvent("thank_you_page_view", {
        pageStage: "thank_you",
        checkoutStatus,
        provider: pendingPurchase && cleanText(pendingPurchase.provider),
      });
      if (pendingPurchase && cleanText(pendingPurchase.provider) === "stripe") {
        trackMetaPixel("track", "Purchase", buildPurchaseEventParams(pendingPurchase));
        trackPostHogEvent("Purchase", buildPurchaseEventParams(pendingPurchase));
      }
    }
    clearPendingMetaPurchase(pendingPurchaseKey);
    window.history.replaceState(window.history.state, "", clearCheckoutQueryParam(window.location.href));
  };
  const parseResponseError = async (response) => {
    try {
      const payload = await response.clone().json();
      const firstError = Array.isArray(payload && payload.errors) ? payload.errors[0] : null;
      const errorDetail = cleanText(firstError && firstError.detail);
      if (errorDetail) return errorDetail;
      const errorTitle = cleanText(firstError && firstError.title);
      if (errorTitle) return errorTitle;
      const detail = cleanText(payload && payload.detail);
      if (detail) return detail;
      const message = cleanText(payload && payload.message);
      if (message) return message;
    } catch (_) {
      // ignore and fall back to plain text
    }
    try {
      const text = cleanText(await response.text());
      if (text) return text;
    } catch (_) {
      // ignore and fall back to status text
    }
    return cleanText(response.statusText) || "Request failed.";
  };
  const resolveExternalCheckoutUrlForVariant = (items, variantId) => {
    if (!Array.isArray(items) || !variantId) return null;
    const match = items.find((item) => item && item.variantId === variantId && typeof item.url === "string");
    return match ? cleanText(match.url) : null;
  };
  const selectionsMatch = (left, right) => {
    const normalizedLeft = stripCheckoutSelectionContext(left);
    const normalizedRight = stripCheckoutSelectionContext(right);
    if (!normalizedLeft || !normalizedRight) return false;
    const leftEntries = Object.entries(normalizedLeft);
    const rightEntries = Object.entries(normalizedRight);
    if (leftEntries.length !== rightEntries.length) return false;
    return leftEntries.every(([key, value]) => normalizedRight[key] === value);
  };
  const readNodeValue = (node, source) => {
    if (!node) return "";
    if (source === "text") return normalizeText(node.textContent || "");
    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
      return normalizeText(node.value || "");
    }
    return normalizeText(node.textContent || "");
  };
  const readSelectionFromResolver = (resolver, bindingId) => {
    if (!resolver || resolver.type !== "option_values") return {};
    const selection = {};
    const optionSelectors = Array.isArray(resolver.optionSelectors) ? resolver.optionSelectors : [];
    for (const option of optionSelectors) {
      const selector = cleanText(option && option.selector);
      const optionName = cleanText(option && option.name);
      const source = option && option.source === "text" ? "text" : "value";
      if (!selector || !optionName) {
        throw new Error("Checkout binding '" + bindingId + "' has an invalid option selector.");
      }
      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length !== 1) {
        throw new Error(
          "Checkout binding '" +
            bindingId +
            "' option selector '" +
            selector +
            "' matched " +
            String(matches.length) +
            " elements.",
        );
      }
      const value = readNodeValue(matches[0], source);
      if (!value) {
        throw new Error(
          "Checkout binding '" + bindingId + "' could not resolve a non-empty option value for '" + optionName + "'.",
        );
      }
      selection[optionName] = value;
    }
    return selection;
  };
  const resolveCheckoutVariant = (checkout, selectionFromDom) => {
    const resolver = checkout && checkout.variantResolver;
    if (!resolver || typeof resolver.type !== "string") {
      throw new Error("Checkout binding is missing a variantResolver.");
    }
    if (resolver.type === "fixed") {
      const variantId = cleanText(resolver.variantId);
      const variant = variants.find((candidate) => candidate.id === variantId) || null;
      return {
        variantId,
        variant,
        selection: selectionFromDom || (variant && variant.optionValues ? variant.optionValues : null),
      };
    }
    if (resolver.type === "option_values") {
      const variant = variants.find((candidate) => selectionsMatch(candidate.optionValues, selectionFromDom)) || null;
      const variantId = cleanText(variant && variant.id);
      if (!variantId) {
        throw new Error("Checkout binding could not resolve a variant from the selected options.");
      }
      return { variantId, variant, selection: selectionFromDom };
    }
    throw new Error("Unsupported checkout resolver type.");
  };
  const buildPreparedCheckoutCacheKey = (variantId, selection) => {
    const normalizedSelection = normalizeSelection(selection) || {};
    const selectionEntries = Object.entries(normalizedSelection).sort(([left], [right]) =>
      left.localeCompare(right),
    );
    return JSON.stringify({
      variantId: cleanText(variantId) || "",
      selection: selectionEntries,
    });
  };
  const getPreparedCheckoutRecord = (cacheKey) => {
    const record = cacheKey ? preparedCheckoutCache[cacheKey] : null;
    if (!record) return null;
    if (Date.now() - record.createdAt > PREPARED_CHECKOUT_TTL_MS) {
      delete preparedCheckoutCache[cacheKey];
      return null;
    }
    return record;
  };
  const delay = (durationMs) =>
    new Promise((resolve) => {
      window.setTimeout(resolve, durationMs);
    });
  const serializeCheckoutAttributeValue = (value) => {
    if (value === undefined || value === null) return null;
    if (typeof value === "string") return cleanText(value);
    return JSON.stringify(value);
  };
	  const checkoutAttributionProps = ({ ctaId, transitionId, variantId } = {}) => {
	    const metaProps = resolveMetaAttributionProps(window.location.href);
	    const clickProps = resolveClickAttribution();
		    const bridgeProps = resolvePresaleBridgeContext(window.location.href, config.pageStage);
		    const experimentId = resolveExperimentId();
        const metaAddToCartEventId = resolveMetaAddToCartCheckoutEventId(variantId);
        const metaInitiateCheckoutEventId = buildMetaInitiateCheckoutHandoffEventId(transitionId);
		    return {
		      ...(bridgeProps.session_id ? { sessionId: bridgeProps.session_id, session_id: bridgeProps.session_id } : {}),
		      ...(bridgeProps.visitor_id ? { visitorId: bridgeProps.visitor_id, visitor_id: bridgeProps.visitor_id } : {}),
		      ...(clickProps.clickId ? { clickId: clickProps.clickId, click_id: clickProps.clickId, clickIdType: clickProps.clickIdType, click_id_type: clickProps.clickIdType } : {}),
		      ...(bridgeProps.source_page_type ? { sourcePageType: bridgeProps.source_page_type, source_page_type: bridgeProps.source_page_type } : {}),
		      ...(bridgeProps.from_stage ? { fromStage: bridgeProps.from_stage, from_stage: bridgeProps.from_stage } : {}),
		      ...(bridgeProps.to_stage ? { toStage: bridgeProps.to_stage, to_stage: bridgeProps.to_stage } : {}),
	      ...(metaProps.fbp ? { fbp: metaProps.fbp } : {}),
      ...(metaProps.fbc ? { fbc: metaProps.fbc } : {}),
      ...(metaProps.external_id ? { externalId: metaProps.external_id } : {}),
      ...(metaProps.em ? { em: metaProps.em } : {}),
      ...(metaProps.event_source_url ? { eventSourceUrl: metaProps.event_source_url } : {}),
      pageVariant: cleanText(config.pageSlug),
      ...(experimentId ? { experimentId } : {}),
      ...(cleanText(ctaId) ? { ctaId: cleanText(ctaId) } : {}),
      ...(cleanText(transitionId) ? { transitionId: cleanText(transitionId) } : {}),
      ...(metaAddToCartEventId ? { mosMetaAddToCartEventId: metaAddToCartEventId } : {}),
      ...(metaInitiateCheckoutEventId ? { mosMetaInitiateCheckoutEventId: metaInitiateCheckoutEventId } : {}),
    };
  };
  const checkoutAttributeMap = ({ variantId, selection, ctaId, transitionId }) => {
    const attribution = checkoutAttributionProps({ ctaId, transitionId, variantId });
    const checkoutAttributeVariantId =
      cleanText(document.querySelector(".mos-sales-checkout-button[data-variant-id]")?.getAttribute("data-variant-id")) ||
      cleanText(document.querySelector("[data-price-point-id]")?.getAttribute("data-price-point-id")) ||
      cleanText(variantId);
    return {
      funnel_slug: cleanText(config.funnelSlug),
      funnel_id: cleanText(config.funnelId),
      publication_id: cleanText(config.publicationId),
      page_id: cleanText(config.pageId),
      visitor_id: cleanText(visitorId),
      session_id: cleanText(sessionId),
      variant_id: checkoutAttributeVariantId,
      price_point_id: checkoutAttributeVariantId,
      selection: selection || {},
      utm: getUtmParams(),
      url_params: getUrlParams(),
      quantity: "1",
      click_id: attribution.clickId,
      click_id_type: attribution.clickIdType,
      fbp: attribution.fbp,
      fbc: attribution.fbc,
      external_id: attribution.externalId,
      em: attribution.em,
      event_source_url: attribution.eventSourceUrl,
      page_variant: attribution.pageVariant,
      experiment_id: attribution.experimentId,
      cta_id: attribution.ctaId,
      transition_id: attribution.transitionId,
      mos_meta_add_to_cart_event_id: attribution.mosMetaAddToCartEventId,
      mos_meta_initiate_checkout_event_id: attribution.mosMetaInitiateCheckoutEventId,
    };
  };
  const appendCheckoutAttributesToCartUrl = (checkoutUrl, attributes) => {
    const href = cleanText(checkoutUrl);
    if (!href) return href;
    let url;
    try {
      url = new URL(href, window.location.href);
    } catch (_) {
      return href;
    }
    if (!url.pathname.startsWith("/cart/")) return href;
    Object.entries(attributes || {}).forEach(([key, value]) => {
      const serialized = serializeCheckoutAttributeValue(value);
      if (serialized) {
        url.searchParams.set("attributes[" + key + "]", serialized);
      }
    });
    return url.toString();
  };
  const appendCurrentUrlParams = (targetUrl) => {
    const href = cleanText(targetUrl);
    if (!href) return href;
    const url = new URL(href, window.location.href);
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of params.entries()) {
      url.searchParams.set(key, value);
    }
    return url.toString();
  };
  const createCheckoutPayload = ({ variantId, selection, ctaId, transitionId }) => {
    const successUrl = new URL(window.location.href);
    const cancelUrl = new URL(window.location.href);
    successUrl.searchParams.set("checkout", "success");
    cancelUrl.searchParams.set("checkout", "cancel");
    return {
      funnelSlug: config.funnelSlug,
      variantId: variantId || undefined,
      selection: selection || {},
      quantity: 1,
      successUrl: successUrl.toString(),
      cancelUrl: cancelUrl.toString(),
      pageId: config.pageId,
      visitorId,
      sessionId,
      utm: getUtmParams(),
      urlParams: getUrlParams(),
      ...checkoutAttributionProps({ ctaId, transitionId, variantId }),
    };
  };
  const normalizePreparedCheckoutResponse = (data) => {
    if (!isRecord(data)) {
      throw new Error("Prepared checkout response is invalid.");
    }
    const preparedCheckoutId = cleanText(data.preparedCheckoutId);
    const status = cleanText(data.status);
    if (!preparedCheckoutId || !status) {
      throw new Error("Prepared checkout response is incomplete.");
    }
    return {
      preparedCheckoutId,
      status,
      checkoutUrl: cleanText(data.checkoutUrl),
      sessionId: cleanText(data.sessionId),
      error: cleanText(data.error),
      pollAfterMs: typeof data.pollAfterMs === "number" ? data.pollAfterMs : PREPARED_CHECKOUT_POLL_INTERVAL_MS,
    };
  };
  const requestCheckout = async ({ variantId, selection, ctaId, transitionId }) => {
    const response = await fetch(String(config.apiBasePath || "/api") + "/public/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(createCheckoutPayload({ variantId, selection, ctaId, transitionId })),
    });
    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }
    const data = await response.json();
    const checkoutUrl = cleanText(data && data.checkoutUrl);
    if (!checkoutUrl) {
      throw new Error("Checkout URL is missing.");
    }
    return {
      checkoutUrl,
      sessionId: cleanText(data && data.sessionId) || null,
    };
  };
  const requestPreparedCheckout = async ({ variantId, selection, ctaId, transitionId }) => {
    const response = await fetch(String(config.apiBasePath || "/api") + "/public/checkout/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(createCheckoutPayload({ variantId, selection, ctaId, transitionId })),
    });
    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }
    return normalizePreparedCheckoutResponse(await response.json());
  };
  const requestPreparedCheckoutStatus = async (preparedCheckoutId) => {
    const response = await fetch(
      String(config.apiBasePath || "/api") + "/public/checkout/prepare/" + encodeURIComponent(preparedCheckoutId),
      {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      },
    );
    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }
    return normalizePreparedCheckoutResponse(await response.json());
  };
  const consumePreparedCheckout = async (preparedCheckoutId) => {
    const response = await fetch(
      String(config.apiBasePath || "/api") +
        "/public/checkout/prepare/" +
        encodeURIComponent(preparedCheckoutId) +
        "/consume",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
    );
    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }
    const data = await response.json();
    const checkoutUrl = cleanText(data && data.checkoutUrl);
    if (!checkoutUrl) {
      throw new Error("Checkout URL is missing.");
    }
    return {
      checkoutUrl,
      sessionId: cleanText(data && data.sessionId) || null,
    };
  };
  const finalizePreparedCheckoutRecord = ({ cacheKey, preparedCheckout, variantId, selection }) => {
    const checkoutUrl = cleanText(preparedCheckout && preparedCheckout.checkoutUrl);
    if (!checkoutUrl) {
      throw new Error("Prepared checkout is missing checkoutUrl.");
    }
    const record = {
      preparedCheckoutId: cleanText(preparedCheckout.preparedCheckoutId) || "",
      checkoutUrl,
      sessionId: cleanText(preparedCheckout.sessionId) || null,
      variantId: variantId || "",
      selection: selection || {},
      createdAt: Date.now(),
    };
    preparedCheckoutCache[cacheKey] = record;
    return record;
  };
  const waitForPreparedCheckoutStatus = async (preparedCheckoutId, initialPollAfterMs) => {
    const deadline = Date.now() + PREPARED_CHECKOUT_POLL_TIMEOUT_MS;
    let pollAfterMs = initialPollAfterMs || PREPARED_CHECKOUT_POLL_INTERVAL_MS;
    while (Date.now() < deadline) {
      await delay(pollAfterMs);
      const preparedCheckout = await requestPreparedCheckoutStatus(preparedCheckoutId);
      if (preparedCheckout.status === "ready") {
        return preparedCheckout;
      }
      if (preparedCheckout.status === "failed") {
        throw new Error(preparedCheckout.error || "Prepared checkout failed.");
      }
      if (preparedCheckout.status === "expired") {
        throw new Error("Prepared checkout expired before it was used.");
      }
      pollAfterMs = preparedCheckout.pollAfterMs || PREPARED_CHECKOUT_POLL_INTERVAL_MS;
    }
    throw new Error("Prepared checkout timed out.");
  };
  const prepareCheckoutInBackground = async ({ variantId, variant, selection, cacheKey, ctaId, transitionId }) => {
    if (!cacheKey || !variant || variant.provider !== "shopify") {
      return null;
    }
    const cachedRecord = getPreparedCheckoutRecord(cacheKey);
    if (cachedRecord) {
      return cachedRecord;
    }
    if (preparedCheckoutInFlight[cacheKey]) {
      return preparedCheckoutInFlight[cacheKey];
    }
    const promise = (async () => {
      try {
        let preparedCheckout = await requestPreparedCheckout({ variantId, selection, ctaId, transitionId });
        if (preparedCheckout.status === "pending") {
          preparedCheckout = await waitForPreparedCheckoutStatus(
            preparedCheckout.preparedCheckoutId,
            preparedCheckout.pollAfterMs,
          );
        }
        if (preparedCheckout.status !== "ready") {
          throw new Error(preparedCheckout.error || "Prepared checkout is unavailable.");
        }
        return finalizePreparedCheckoutRecord({ cacheKey, preparedCheckout, variantId, selection });
      } catch (error) {
        console.error("[HtmlDeployArtifact] Failed to prepare checkout in background.", error);
        return null;
      }
    })().finally(() => {
      delete preparedCheckoutInFlight[cacheKey];
    });
    preparedCheckoutInFlight[cacheKey] = promise;
    return promise;
  };
  const waitForPreparedCheckout = async (cacheKey) => {
    if (!cacheKey || !preparedCheckoutInFlight[cacheKey]) {
      return null;
    }
    return preparedCheckoutInFlight[cacheKey];
  };
  const resolveCheckoutState = (binding) => {
    const bindingId = String(binding.id || "unknown");
    const resolvedSelection = augmentSelectionWithCheckoutContext(
      readSelectionFromResolver(binding.checkout.variantResolver, bindingId),
    );
    const { variantId, variant, selection } = resolveCheckoutVariant(binding.checkout, resolvedSelection);
    const cacheKey = buildPreparedCheckoutCacheKey(variantId, selection);
    if (cacheKey && !preparedCheckoutTransitionIds[cacheKey]) {
      preparedCheckoutTransitionIds[cacheKey] = buildCanonicalEventId("checkout_transition");
    }
    return {
      variantId,
      variant,
      selection,
      ctaId: bindingId,
      cacheKey,
      transitionId: cacheKey ? preparedCheckoutTransitionIds[cacheKey] : buildCanonicalEventId("checkout_transition"),
    };
  };
  const ensurePreparedCheckoutForClick = async ({ variantId, variant, selection, cacheKey, ctaId, transitionId }) => {
    const isWarmableShopifyCheckout = Boolean(cacheKey) && Boolean(variant) && variant.provider === "shopify";
    if (!isWarmableShopifyCheckout) {
      return requestCheckout({ variantId, selection, ctaId, transitionId });
    }
    let preparedCheckout = getPreparedCheckoutRecord(cacheKey);
    if (preparedCheckout) {
      return consumePreparedCheckout(preparedCheckout.preparedCheckoutId);
    }
    preparedCheckout =
      (await waitForPreparedCheckout(cacheKey)) ||
      (await prepareCheckoutInBackground({ variantId, variant, selection, cacheKey, ctaId, transitionId }));
    if (!preparedCheckout) {
      throw new Error("Prepared checkout is unavailable.");
    }
    const consumedCheckout = await consumePreparedCheckout(preparedCheckout.preparedCheckoutId);
    preparedCheckoutCache[cacheKey] = {
      ...preparedCheckout,
      ...consumedCheckout,
    };
    return consumedCheckout;
  };
  const CHECKOUT_INLINE_LABEL_SELECTOR =
    "[data-tenor-cart-checkout-label], [data-mos-checkout-label], [data-checkout-label]";
  const CHECKOUT_INLINE_LOADING_LABEL = "Loading...";
  const checkoutInlineLoadingLabel = (labelElement, label) => {
    if (labelElement && labelElement.hasAttribute("data-tenor-cart-checkout-label")) {
      return CHECKOUT_INLINE_LOADING_LABEL;
    }
    return cleanText(label) || CHECKOUT_INLINE_LOADING_LABEL;
  };
  const setCheckoutElementVisualWaiting = (element, waiting, label) => {
    if (!(element instanceof HTMLElement)) return;
    const labelTargets = Array.from(element.querySelectorAll(CHECKOUT_INLINE_LABEL_SELECTOR)).filter(
      (target) => target instanceof HTMLElement,
    );
    if (waiting) {
      if (!("mosSavedIsLoadingClass" in element.dataset)) {
        element.dataset.mosSavedIsLoadingClass = element.classList.contains("is-loading") ? "true" : "false";
      }
      if (!("mosSavedLoadingClass" in element.dataset)) {
        element.dataset.mosSavedLoadingClass = element.classList.contains("loading") ? "true" : "false";
      }
      element.classList.add("is-loading");
      if (element.querySelector(".loading__spinner")) {
        element.classList.add("loading");
      }
      labelTargets.forEach((target) => {
        if (!("mosSavedCheckoutLabel" in target.dataset)) {
          target.dataset.mosSavedCheckoutLabel = target.textContent || "";
        }
        target.textContent = checkoutInlineLoadingLabel(target, label);
      });
      return;
    }
    if (element.dataset.mosSavedIsLoadingClass !== "true") {
      element.classList.remove("is-loading");
    }
    if (element.dataset.mosSavedLoadingClass !== "true") {
      element.classList.remove("loading");
    }
    delete element.dataset.mosSavedIsLoadingClass;
    delete element.dataset.mosSavedLoadingClass;
    labelTargets.forEach((target) => {
      if ("mosSavedCheckoutLabel" in target.dataset) {
        target.textContent = target.dataset.mosSavedCheckoutLabel || "";
        delete target.dataset.mosSavedCheckoutLabel;
      }
    });
  };
  const setElementBusy = (element, busy, label) => {
    if (!(element instanceof HTMLElement)) return;
    if (busy) {
      if (!("mosSavedPointerEvents" in element.dataset)) {
        element.dataset.mosSavedPointerEvents = element.style.pointerEvents || "";
      }
      if (!("mosSavedOpacity" in element.dataset)) {
        element.dataset.mosSavedOpacity = element.style.opacity || "";
      }
      if (!("mosSavedCursor" in element.dataset)) {
        element.dataset.mosSavedCursor = element.style.cursor || "";
      }
      if (element instanceof HTMLButtonElement && !("mosSavedDisabled" in element.dataset)) {
        element.dataset.mosSavedDisabled = element.disabled ? "true" : "false";
      }
      element.setAttribute("aria-busy", "true");
      element.setAttribute("aria-disabled", "true");
      element.style.pointerEvents = "none";
      element.style.opacity = "0.72";
      element.style.cursor = "progress";
      if (element instanceof HTMLButtonElement) {
        element.disabled = true;
      }
      setCheckoutElementVisualWaiting(element, true, label);
      return;
    }
    setCheckoutElementVisualWaiting(element, false, label);
    element.removeAttribute("aria-busy");
    element.removeAttribute("aria-disabled");
    element.style.pointerEvents = element.dataset.mosSavedPointerEvents || "";
    element.style.opacity = element.dataset.mosSavedOpacity || "";
    element.style.cursor = element.dataset.mosSavedCursor || "";
    delete element.dataset.mosSavedPointerEvents;
    delete element.dataset.mosSavedOpacity;
    delete element.dataset.mosSavedCursor;
    if (element instanceof HTMLButtonElement) {
      const wasDisabled = element.dataset.mosSavedDisabled === "true";
      element.disabled = wasDisabled;
      delete element.dataset.mosSavedDisabled;
    }
  };
  const resetBusyBoundElements = () => {
    const candidates = Array.from(
      document.querySelectorAll(
        [
          "[data-mos-standalone-bridge-bound='true'][aria-busy='true']",
          "[data-mos-standalone-bridge-bound='true'][aria-disabled='true']",
          "[data-mos-saved-pointer-events]",
          "[data-mos-saved-opacity]",
          "[data-mos-saved-cursor]",
          "[data-mos-saved-disabled]",
          "[data-mos-saved-is-loading-class]",
          "[data-mos-saved-loading-class]",
        ].join(","),
      ),
    );
    for (const element of candidates) {
      if (element instanceof HTMLElement) {
        setElementBusy(element, false);
      }
    }
  };
  const EMAIL_CAPTURE_LOADING_LABEL = "Saving your email...";
  const EMAIL_CAPTURE_SUCCESS_LABEL = "You're subscribed.";
  const EMAIL_CAPTURE_ERROR_LABEL = "We couldn't save your email. Please try again.";
  const KLAVIYO_CLIENT_SUBSCRIPTION_ENDPOINT = "https://a.klaviyo.com/client/subscriptions";
  const isLikelyEmailAddress = (value) => {
    const text = String(value || "");
    if (!text) return false;
    for (let index = 0; index < text.length; index += 1) {
      const code = text.charCodeAt(index);
      if (code <= 32 || code === 127) return false;
    }
    const parts = text.split("@");
    if (parts.length !== 2) return false;
    const local = parts[0];
    const domain = parts[1];
    return Boolean(local && domain && domain.includes(".") && !domain.startsWith(".") && !domain.endsWith("."));
  };
  const isPrivateKlaviyoApiKey = (value) => cleanText(value).toLowerCase().startsWith("pk_");
  const ensureEmailCaptureStatusNote = (bindingId, element) => {
    const existingId = cleanText(element.dataset.mosEmailCaptureStatusNoteId);
    if (existingId) {
      const existing = document.getElementById(existingId);
      if (existing) return existing;
    }
    const noteId =
      "mos-email-capture-status-" +
      String(bindingId || "unknown") +
      "-" +
      String(Date.now()) +
      "-" +
      String(Math.floor(Math.random() * 100000));
    const note = document.createElement("p");
    note.id = noteId;
    note.style.display = "none";
    note.style.width = "100%";
    note.style.margin = "0.65rem 0 0";
    note.style.fontSize = "0.875rem";
    note.style.lineHeight = "1.35";
    note.style.fontWeight = "600";
    note.style.letterSpacing = "normal";
    note.style.textTransform = "none";
    note.style.color = "inherit";
    note.setAttribute("aria-live", "polite");
    element.insertAdjacentElement("afterend", note);
    element.dataset.mosEmailCaptureStatusNoteId = noteId;
    return note;
  };
  const setEmailCaptureStatus = (bindingId, element, status, message) => {
    const note = ensureEmailCaptureStatusNote(bindingId, element);
    const cleanedMessage = cleanText(message);
    if (!status || !cleanedMessage) {
      note.textContent = "";
      note.style.display = "none";
      note.removeAttribute("role");
      return;
    }
    note.textContent = cleanedMessage;
    note.style.display = "block";
    note.style.color = status === "error" ? "#b42318" : status === "success" ? "#047857" : "inherit";
    note.setAttribute("role", status === "error" ? "alert" : "status");
  };
  const setEmailCaptureSubmitting = (element, busy) => {
    if (!(element instanceof HTMLElement)) return;
    const controls = Array.from(
      element.querySelectorAll("button[type='submit'], button:not([type]), input[type='submit']"),
    );
    element.setAttribute("aria-busy", busy ? "true" : "false");
    controls.forEach((control) => {
      if (!(control instanceof HTMLElement)) return;
      if (busy) {
        if (!("mosEmailCaptureSavedDisabled" in control.dataset)) {
          const disabled =
            control instanceof HTMLButtonElement || control instanceof HTMLInputElement
              ? control.disabled
              : control.getAttribute("aria-disabled") === "true";
          control.dataset.mosEmailCaptureSavedDisabled = disabled ? "true" : "false";
        }
        control.setAttribute("aria-disabled", "true");
        control.setAttribute("aria-busy", "true");
        if (control instanceof HTMLButtonElement || control instanceof HTMLInputElement) {
          control.disabled = true;
        }
        return;
      }
      const wasDisabled = control.dataset.mosEmailCaptureSavedDisabled === "true";
      control.removeAttribute("aria-busy");
      if (wasDisabled) {
        control.setAttribute("aria-disabled", "true");
      } else {
        control.removeAttribute("aria-disabled");
      }
      if (control instanceof HTMLButtonElement || control instanceof HTMLInputElement) {
        control.disabled = wasDisabled;
      }
      delete control.dataset.mosEmailCaptureSavedDisabled;
    });
    if (!busy) {
      element.removeAttribute("aria-busy");
    }
  };
  const queryEmailCaptureElement = (rootElement, selector, label) => {
    const cleanedSelector = cleanText(selector);
    if (!cleanedSelector) {
      throw new Error(label + " selector is missing.");
    }
    try {
      if (rootElement && typeof rootElement.querySelector === "function") {
        const scopedMatch = rootElement.querySelector(cleanedSelector);
        if (scopedMatch) return scopedMatch;
      }
      return document.querySelector(cleanedSelector);
    } catch (_) {
      throw new Error(label + " selector '" + cleanedSelector + "' is invalid.");
    }
  };
  const readEmailCaptureElementValue = (element, source) => {
    if (
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement ||
      element instanceof HTMLSelectElement
    ) {
      return cleanText(element.value);
    }
    if (source === "text") {
      return cleanText(element.textContent || "");
    }
    return cleanText(element.getAttribute("value")) || cleanText(element.textContent || "");
  };
  const readEmailCaptureEmail = (binding, element) => {
    const emailCapture = binding && binding.emailCapture;
    if (!emailCapture || emailCapture.provider !== "klaviyo") {
      throw new Error("Email capture binding '" + String(binding && binding.id ? binding.id : "unknown") + "' is missing Klaviyo configuration.");
    }
    const emailElement = queryEmailCaptureElement(element, emailCapture.emailSelector, "Email capture email");
    const email = readEmailCaptureElementValue(emailElement, "value");
    if (!email || !isLikelyEmailAddress(email)) {
      throw new Error("Please enter a valid email address.");
    }
    return email.toLowerCase();
  };
  const readEmailCaptureProfileProperties = (binding, element) => {
    const emailCapture = binding && binding.emailCapture;
    const fields = Array.isArray(emailCapture && emailCapture.profileFields) ? emailCapture.profileFields : [];
    const properties = {};
    fields.forEach((field) => {
      const name = cleanText(field && field.name);
      const selector = cleanText(field && field.selector);
      if (!name || !selector) return;
      const fieldElement = queryEmailCaptureElement(element, selector, "Email capture profile field '" + name + "'");
      const value = readEmailCaptureElementValue(fieldElement, field.source === "text" ? "text" : "value");
      if (value) {
        properties[name] = value;
      }
    });
    return properties;
  };
  const buildKlaviyoSubscriptionPayload = (binding, element, email) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const emailCapture = binding && binding.emailCapture;
    if (!emailCapture || emailCapture.provider !== "klaviyo") {
      throw new Error("Email capture binding '" + bindingId + "' is missing Klaviyo configuration.");
    }
    const source = cleanText(emailCapture.source);
    if (!source) {
      throw new Error("Email capture binding '" + bindingId + "' is missing a Klaviyo source.");
    }
    const profileProperties = {
      source,
      capture_source: source,
      product_slug: cleanText(config.productSlug),
      funnel_slug: cleanText(config.funnelSlug),
      page_slug: cleanText(config.pageSlug),
      page_stage: cleanText(config.pageStage),
      page_id: cleanText(config.pageId),
      publication_id: cleanText(config.publicationId),
      visitor_id: cleanText(visitorId),
      session_id: cleanText(sessionId),
      binding_id: bindingId,
      url: window.location.href,
      utm: getUtmParams(),
      url_params: getUrlParams(),
      ...readEmailCaptureProfileProperties(binding, element),
    };
    const payload = {
      data: {
        type: "subscription",
        attributes: {
          custom_source: source,
          profile: {
            data: {
              type: "profile",
              attributes: {
                email,
                properties: profileProperties,
                subscriptions: {
                  email: {
                    marketing: {
                      consent: "SUBSCRIBED",
                    },
                  },
                },
              },
            },
          },
        },
      },
    };
    const listId = cleanText(emailCapture.klaviyo && emailCapture.klaviyo.listId);
    if (listId) {
      payload.data.relationships = {
        list: {
          data: {
            type: "list",
            id: listId,
          },
        },
      };
    }
    return payload;
  };
  const requestKlaviyoEmailSubscription = async (binding, element, email) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const emailCapture = binding && binding.emailCapture;
    const klaviyo = emailCapture && emailCapture.klaviyo;
    const publicApiKey = cleanText(klaviyo && klaviyo.publicApiKey);
    if (!publicApiKey) {
      throw new Error("Email capture binding '" + bindingId + "' is missing the Klaviyo public API key.");
    }
    if (isPrivateKlaviyoApiKey(publicApiKey)) {
      throw new Error("Email capture binding '" + bindingId + "' must use the Klaviyo public Site ID, not a private API key.");
    }
    const revision = cleanText(klaviyo && klaviyo.revision);
    if (!revision) {
      throw new Error("Email capture binding '" + bindingId + "' is missing the Klaviyo API revision.");
    }
    const url = new URL(KLAVIYO_CLIENT_SUBSCRIPTION_ENDPOINT);
    url.searchParams.set("company_id", publicApiKey);
    const response = await fetch(url.toString(), {
      method: "POST",
      headers: {
        Accept: "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        revision,
      },
      body: JSON.stringify(buildKlaviyoSubscriptionPayload(binding, element, email)),
    });
    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }
  };
  const loadKlaviyoOnsiteScript = (publicApiKey) => {
    const key = cleanText(publicApiKey);
    if (!key) return;
    if (isPrivateKlaviyoApiKey(key)) return;
    if (!window.klaviyo) {
      window.klaviyo = [];
    }
    const scriptId = "mos-klaviyo-onsite-" + key.replace(/[^A-Za-z0-9_-]/g, "-");
    if (document.getElementById(scriptId)) return;
    const script = document.createElement("script");
    script.id = scriptId;
    script.async = true;
    script.type = "text/javascript";
    script.src = "https://static.klaviyo.com/onsite/js/" + encodeURIComponent(key) + "/klaviyo.js";
    (document.body || document.head || document.documentElement).appendChild(script);
  };
  const loadKlaviyoOnsiteScriptForBinding = (binding) => {
    const key =
      binding &&
      binding.emailCapture &&
      binding.emailCapture.klaviyo &&
      binding.emailCapture.klaviyo.publicApiKey;
    loadKlaviyoOnsiteScript(key);
  };
  const sendKlaviyoBrowserSignals = (binding, email) => {
    const source = cleanText(binding && binding.emailCapture && binding.emailCapture.source);
    const props = {
      email,
      source,
      capture_source: source,
      product_slug: cleanText(config.productSlug),
      funnel_slug: cleanText(config.funnelSlug),
      page_slug: cleanText(config.pageSlug),
      page_stage: cleanText(config.pageStage),
      binding_id: String(binding && binding.id ? binding.id : "unknown"),
    };
    try {
      const klaviyo = window.klaviyo;
      if (Array.isArray(klaviyo)) {
        klaviyo.push(["identify", { email }]);
        klaviyo.push(["track", "Email Capture Submitted", props]);
        return;
      }
      if (klaviyo && typeof klaviyo.identify === "function") {
        klaviyo.identify({ email });
      }
      if (klaviyo && typeof klaviyo.track === "function") {
        klaviyo.track("Email Capture Submitted", props);
      }
    } catch (error) {
      console.error("[HtmlDeployArtifact] Klaviyo browser signal failed.", error);
    }
  };
  const sha256Hex = async (value) => {
    if (!window.crypto || !window.crypto.subtle || typeof TextEncoder === "undefined") {
      throw new Error("Browser SHA-256 hashing is unavailable.");
    }
    const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  };
  const persistMetaEmailHash = async (email) => {
    const normalizedEmail = cleanText(email) ? String(email).trim().toLowerCase() : null;
    if (!normalizedEmail) return null;
    let emailHash = null;
    try {
      emailHash = await sha256Hex(normalizedEmail);
      window.localStorage.setItem(META_EMAIL_HASH_STORAGE_KEY, emailHash);
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to persist Meta email hash.", error);
    }
    return emailHash;
  };
  const identifyPostHogEmailCapture = (binding, email, emailHash) => {
    const normalizedEmail = cleanText(email) ? String(email).trim().toLowerCase() : null;
    if (!normalizedEmail) return;
    const posthog = ensurePostHogInstance();
    if (!posthog || typeof posthog.identify !== "function") return;
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const source = cleanText(binding && binding.emailCapture && binding.emailCapture.source);
    const personProps = resolvePostHogPersonProps(normalizedEmail, emailHash, {
      capture_source: source,
      binding_id: bindingId,
    });
    persistPostHogIdentity(normalizedEmail, emailHash);
    posthog.identify(normalizedEmail, personProps);
  };
  const completeEmailCaptureSuccess = (binding, element) => {
    const emailCapture = binding && binding.emailCapture;
    if (
      element instanceof HTMLFormElement &&
      emailCapture &&
      emailCapture.successBehavior === "redispatch_submit"
    ) {
      element.dataset.mosEmailCaptureSucceeded = "true";
      element.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      if (element.dataset.mosEmailCaptureSucceeded === "true") {
        delete element.dataset.mosEmailCaptureSucceeded;
      }
      return;
    }
    setEmailCaptureStatus(
      String(binding && binding.id ? binding.id : "unknown"),
      element,
      "success",
      cleanText(emailCapture && emailCapture.successMessage) || EMAIL_CAPTURE_SUCCESS_LABEL,
    );
  };
  const handleEmailCaptureSubmit = async (binding, element, event) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    if (event && event.__mosEmailCaptureBypass === true) {
      return;
    }
    if (element.dataset.mosEmailCaptureSucceeded === "true") {
      if (event) {
        event.__mosEmailCaptureBypass = true;
      }
      delete element.dataset.mosEmailCaptureSucceeded;
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") {
      event.stopImmediatePropagation();
    }
    if (element instanceof HTMLFormElement && typeof element.reportValidity === "function" && !element.reportValidity()) {
      return;
    }
    const emailCapture = binding && binding.emailCapture;
    const source = cleanText(emailCapture && emailCapture.source) || bindingId;
    try {
      const email = readEmailCaptureEmail(binding, element);
      setEmailCaptureSubmitting(element, true);
      setEmailCaptureStatus(bindingId, element, "loading", EMAIL_CAPTURE_LOADING_LABEL);
      trackEvent(binding.trackEventType || "email_capture_submit", {
        bindingId,
        source,
        provider: "klaviyo",
      });
      await requestKlaviyoEmailSubscription(binding, element, email);
      const emailHash = await persistMetaEmailHash(email);
      identifyPostHogEmailCapture(binding, email, emailHash);
      sendKlaviyoBrowserSignals(binding, email);
      trackEvent("email_capture_success", {
        bindingId,
        source,
        provider: "klaviyo",
      });
      completeEmailCaptureSuccess(binding, element);
    } catch (error) {
      console.error("[HtmlDeployArtifact] Email capture binding '" + bindingId + "' failed.", error);
      trackEvent("email_capture_failed", {
        bindingId,
        source,
        provider: "klaviyo",
        errorMessage: cleanText(error && error.message) || "Email capture failed.",
      });
      setEmailCaptureStatus(
        bindingId,
        element,
        "error",
        cleanText(emailCapture && emailCapture.errorMessage) || EMAIL_CAPTURE_ERROR_LABEL,
      );
    } finally {
      setEmailCaptureSubmitting(element, false);
    }
  };
  const emailCaptureFormBindings = [];
  let emailCaptureDocumentSubmitListenerBound = false;
  const registerEmailCaptureSubmitBinding = (binding, element) => {
    emailCaptureFormBindings.push({ binding, element });
    if (!emailCaptureDocumentSubmitListenerBound) {
      emailCaptureDocumentSubmitListenerBound = true;
      document.addEventListener("submit", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLFormElement)) return;
        const match = emailCaptureFormBindings.find((entry) => entry && entry.element === target);
        if (!match) return;
        void handleEmailCaptureSubmit(match.binding, match.element, event);
      }, true);
    }
    element.addEventListener("submit", (event) => {
      void handleEmailCaptureSubmit(binding, element, event);
    }, true);
  };
  const bindManifest = () => {
    const manifest = config.manifest;
    if (!manifest || !Array.isArray(manifest.bindings)) return;
    for (const binding of manifest.bindings) {
      if (!binding || typeof binding !== "object") continue;
      const selector = cleanText(binding.selector);
      if (!selector) continue;
      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length < 1) {
        console.error(
          "[HtmlDeployArtifact] Binding '" +
            String(binding.id || "unknown") +
            "' selector '" +
            selector +
            "' matched no elements.",
        );
        continue;
      }
      for (const [matchIndex, element] of matches.entries()) {
        if (!(element instanceof HTMLElement)) continue;
        if (element.__mosStandaloneBridgeBound === true) continue;
        element.__mosStandaloneBridgeBound = true;
        element.dataset.mosStandaloneBridgeBound = "true";
        if (binding.type === "checkout" && binding.checkout && binding.checkout.mode !== "external_checkout_url") {
          element.addEventListener("pointerenter", () => scheduleWarmCheckoutBindings(75), { passive: true });
          element.addEventListener("touchstart", () => scheduleWarmCheckoutBindings(0), { passive: true });
          element.addEventListener("mousedown", () => scheduleWarmCheckoutBindings(0), { passive: true });
          element.addEventListener("focus", () => scheduleWarmCheckoutBindings(0));
        }
        if (binding.type === "internal_navigation" && element instanceof HTMLAnchorElement) {
          const targetPath = cleanText(config.pagePathById && config.pagePathById[String(binding.targetPageId || "")]);
          const targetStage = cleanText(config.pageStageById && config.pageStageById[String(binding.targetPageId || "")]);
          if (targetPath) {
            element.href = buildInternalNavigationUrl(targetPath, {
              fromStage: config.pageStage,
              toStage: targetStage || "custom",
              sessionId,
              anonymousId: visitorId,
            });
          }
        }
        if (binding.type === "email_capture") {
          if (!(element instanceof HTMLFormElement)) {
            console.error(
              "[HtmlDeployArtifact] Email capture binding '" +
                String(binding.id || "unknown") +
                "' must target a form element.",
            );
            continue;
          }
          loadKlaviyoOnsiteScriptForBinding(binding);
          registerEmailCaptureSubmitBinding(binding, element);
          continue;
        }
        const handleBindingClick = async (event) => {
          if (event.__mosStandaloneBindingHandled === true) return;
          event.__mosStandaloneBindingHandled = true;
          const modifiedClick =
            event instanceof MouseEvent &&
            (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0);
          if (binding.type === "internal_navigation" && modifiedClick) {
            return;
          }
          const sameDocumentHashTarget =
            binding.type === "checkout" ? resolveSameDocumentHashTarget(element) : null;
          if (sameDocumentHashTarget) {
            trackEvent("custom_page_click", {
              fromStage: config.pageStage,
              toStage: config.pageStage,
              pageId: config.pageId,
              buttonText: normalizeText(element.textContent || "") || undefined,
              bindingId: binding.id,
              targetHash: cleanText(element.getAttribute("href")) || undefined,
            });
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          const buttonText = normalizeText(element.textContent || "");
          try {
            if (binding.type === "internal_navigation") {
              const targetPath = cleanText(config.pagePathById && config.pagePathById[String(binding.targetPageId || "")]);
              const targetStage = cleanText(config.pageStageById && config.pageStageById[String(binding.targetPageId || "")]);
              if (!targetPath) {
                throw new Error("Target page path is missing for binding '" + String(binding.id || "unknown") + "'.");
              }
              const ctaPosition = matchIndex + 1;
              const isPresaleSalesClick = isPresaleToSalesNavigation(config.pageStage, targetStage || "custom");
              const bridgeClickId = isPresaleSalesClick ? buildBridgeClickId(binding.id, ctaPosition) : null;
              const bridgeSourcePageType = isPresaleSalesClick
                ? resolvePresaleSourcePageType(config.htmlArtifactKind)
                : null;
              const destinationUrl = buildInternalNavigationUrl(targetPath, {
                fromStage: config.pageStage,
                toStage: targetStage || "custom",
                sessionId,
                anonymousId: visitorId,
                clickId: bridgeClickId,
              });
              if (isPresaleSalesClick && cleanText(config.htmlArtifactKind) === "quiz") {
                trackEvent("quiz_cta_viewed", {
                  fromStage: "pre_sales",
                  from_stage: "pre_sales",
                  toStage: "sales",
                  to_stage: "sales",
                  targetPageId: binding.targetPageId,
                  bindingId: binding.id,
                  binding_id: binding.id,
                  ctaId: binding.id,
                  cta_id: binding.id,
                  ctaPosition,
                  cta_position: ctaPosition,
                  ctaText: buttonText || undefined,
                  cta_text: buttonText || undefined,
                  buttonText: buttonText || undefined,
                  button_text: buttonText || undefined,
                  destinationUrl,
                  destination_url: destinationUrl,
                  ...(bridgeClickId
                    ? {
                        clickId: bridgeClickId,
                        click_id: bridgeClickId,
                        clickIdType: CLICK_PARAM,
                        click_id_type: CLICK_PARAM,
                      }
                    : {}),
                  sessionId: sessionId,
                  session_id: sessionId,
                  visitorId: visitorId,
                  visitor_id: visitorId,
                  sourcePageType: bridgeSourcePageType,
                  source_page_type: bridgeSourcePageType,
                });
                await trackEvent("quiz_completed", {
                  fromStage: "pre_sales",
                  from_stage: "pre_sales",
                  toStage: "sales",
                  to_stage: "sales",
                  targetPageId: binding.targetPageId,
                  bindingId: binding.id,
                  binding_id: binding.id,
                  ctaId: binding.id,
                  cta_id: binding.id,
                  ctaPosition,
                  cta_position: ctaPosition,
                  ctaText: buttonText || undefined,
                  cta_text: buttonText || undefined,
                  buttonText: buttonText || undefined,
                  button_text: buttonText || undefined,
                  destinationUrl,
                  destination_url: destinationUrl,
                  ...(bridgeClickId
                    ? {
                        clickId: bridgeClickId,
                        click_id: bridgeClickId,
                        clickIdType: CLICK_PARAM,
                        click_id_type: CLICK_PARAM,
                      }
                    : {}),
                  sessionId: sessionId,
                  session_id: sessionId,
                  visitorId: visitorId,
                  visitor_id: visitorId,
                  sourcePageType: bridgeSourcePageType,
                  source_page_type: bridgeSourcePageType,
                });
              }
              trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                toStage: targetStage || "custom",
                targetPageId: binding.targetPageId,
                bindingId: binding.id,
                ctaId: binding.id,
                cta_id: binding.id,
                ctaPosition,
                cta_position: ctaPosition,
                ctaText: buttonText || undefined,
                cta_text: buttonText || undefined,
                buttonText: buttonText || undefined,
                destinationUrl,
                destination_url: destinationUrl,
	                ...(bridgeClickId
	                  ? {
	                      clickId: bridgeClickId,
	                      click_id: bridgeClickId,
	                      clickIdType: CLICK_PARAM,
	                      click_id_type: CLICK_PARAM,
	                    }
	                  : {}),
	                ...(isPresaleSalesClick
	                  ? {
	                      sessionId: sessionId,
	                      session_id: sessionId,
	                      visitorId: visitorId,
	                      visitor_id: visitorId,
	                      sourcePageType: bridgeSourcePageType,
	                      source_page_type: bridgeSourcePageType,
	                      fromStage: "pre_sales",
	                      from_stage: "pre_sales",
	                      toStage: "sales",
	                      to_stage: "sales",
	                    }
	                  : {}),
              });
              if (isPresaleSalesClick) {
                markPresaleAttribution();
              }
              await waitForTrackingNavigationFlush();
              window.location.href = destinationUrl;
              return;
            }
            if (binding.type === "track_only") {
              const ctaPosition = matchIndex + 1;
              trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                pageId: config.pageId,
                buttonText: buttonText || undefined,
                bindingId: binding.id,
                ctaId: binding.id,
                cta_id: binding.id,
                ctaPosition,
                cta_position: ctaPosition,
                ctaText: buttonText || undefined,
                cta_text: buttonText || undefined,
              });
              return;
            }
            if (binding.type !== "checkout" || !binding.checkout) {
              throw new Error("Unsupported binding type.");
            }
            setElementBusy(element, true);
            const { variantId, variant, selection, cacheKey, transitionId: resolvedTransitionId } = resolveCheckoutState(binding);
            const bindingId = String(binding.id || "unknown");
            const transitionId = cleanText(resolvedTransitionId) || buildCanonicalEventId("checkout_transition");
	            const checkoutEventProps = {
	              fromStage: config.pageStage,
	              from_stage: config.pageStage,
	              toStage: "checkout",
	              to_stage: "checkout",
	              bindingId,
	              binding_id: bindingId,
	              ctaId: bindingId,
	              cta_id: bindingId,
	              transitionId,
	              transition_id: transitionId,
	              buttonText: buttonText || undefined,
	              button_text: buttonText || undefined,
	              ...(variantId ? { variantId } : {}),
	              ...(variantId ? { variant_id: variantId, contentId: variantId, content_id: variantId } : {}),
	              ...(variant && typeof variant.price === "number" ? { value: Math.round(variant.price) / 100 } : {}),
	              ...(variant && variant.currency ? { currency: variant.currency } : {}),
	            };
            const checkoutTrackEventType =
              cleanText(window.__mosCheckoutTrackEventTypeOverride) ||
              binding.trackEventType ||
              "sales_to_checkout_click";
            if (cleanText(window.__mosCheckoutTrackEventTypeOverride)) {
              window.__mosCheckoutTrackEventTypeOverride = "";
            }
            if (binding.checkout.mode === "external_checkout_url") {
              const checkoutUrl = resolveExternalCheckoutUrlForVariant(
                binding.checkout.externalUrlsByVariant || [],
                variantId,
              );
              if (!checkoutUrl) {
                throw new Error("Missing external checkout URL for binding '" + String(binding.id || "unknown") + "'.");
              }
              if (variant && variant.provider === "stripe") {
                const pendingKey = pendingMetaPurchaseStorageKey(sessionId, config.funnelSlug);
                writePendingMetaPurchase(pendingKey, {
                  funnelSlug: config.funnelSlug,
                  pageId: config.pageId,
                  variantId: variant.id,
                  value: typeof variant.price === "number" ? variant.price : null,
                  currency: variant.currency || null,
                  quantity: 1,
                  provider: variant.provider,
                });
              }
              const resolvedCheckoutUrl = appendCurrentUrlParams(
                appendCheckoutAttributesToCartUrl(
                  checkoutUrl,
                  checkoutAttributeMap({
                    variantId,
                    selection,
                    ctaId: bindingId,
                    transitionId,
                  }),
                ),
              );
              trackEvent(checkoutTrackEventType, {
                ...checkoutEventProps,
                checkoutUrl: resolvedCheckoutUrl,
                checkout_url: resolvedCheckoutUrl,
              });
              await waitForTrackingNavigationFlush();
              window.location.href = resolvedCheckoutUrl;
              return;
            }
            const checkout = await ensurePreparedCheckoutForClick({
              variantId,
              variant,
              selection,
              cacheKey,
              ctaId: bindingId,
              transitionId,
            });
            if (variant && variant.provider === "stripe") {
              const pendingKey = pendingMetaPurchaseStorageKey(sessionId, config.funnelSlug);
              writePendingMetaPurchase(pendingKey, {
                funnelSlug: config.funnelSlug,
                pageId: config.pageId,
                variantId: variant.id,
                value: typeof variant.price === "number" ? variant.price : null,
                currency: variant.currency || null,
                quantity: 1,
                provider: variant.provider,
              });
            }
            const resolvedCheckoutUrl = appendCurrentUrlParams(checkout.checkoutUrl);
            trackEvent(checkoutTrackEventType, {
              ...checkoutEventProps,
              checkoutUrl: resolvedCheckoutUrl,
              checkout_url: resolvedCheckoutUrl,
            });
            await waitForTrackingNavigationFlush();
            window.location.href = resolvedCheckoutUrl;
          } catch (error) {
            console.error(
              "[HtmlDeployArtifact] Binding '" + String(binding.id || "unknown") + "' failed.",
              error,
            );
            setElementBusy(element, false);
          }
        };
        if (binding.type === "internal_navigation") {
          if (element.__mosStandaloneClickOverrideBound !== true) {
            element.__mosStandaloneClickOverrideBound = true;
            try {
              element.click = () => {
                const syntheticClick = new MouseEvent("click", {
                  bubbles: true,
                  cancelable: true,
                  view: window,
                });
                void handleBindingClick(syntheticClick);
              };
            } catch (_error) {}
          }
          document.addEventListener("click", (event) => {
            const target = event && event.target instanceof Element
              ? event.target.closest(selector)
              : null;
            if (!target) return;
            void handleBindingClick(event);
          }, { capture: true });
        }
        element.addEventListener("click", handleBindingClick, { capture: true });
      }
    }
  };
  const warmCheckoutBindings = async () => {
    const manifest = config.manifest;
    if (!manifest || !Array.isArray(manifest.bindings)) return;
    await Promise.all(
      manifest.bindings.map(async (binding) => {
        if (!binding || typeof binding !== "object") return;
        if (binding.type !== "checkout" || !binding.checkout) return;
        if (binding.checkout.mode === "external_checkout_url") return;
        try {
          const checkoutState = resolveCheckoutState(binding);
          if (!checkoutState.variant || checkoutState.variant.provider !== "shopify") {
            return;
          }
          await prepareCheckoutInBackground(checkoutState);
        } catch (error) {
          console.error(
            "[HtmlDeployArtifact] Failed to warm checkout binding '" +
              String(binding.id || "unknown") +
              "'.",
            error,
          );
        }
      }),
    );
  };
  const warmCheckoutBindingsSafely = () => {
    try {
      void warmCheckoutBindings();
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to warm checkout bindings.", error);
    }
  };
  const scheduleWarmCheckoutBindings = (delayMs = 75) => {
    if (warmCheckoutBindingsTimeout !== null) {
      window.clearTimeout(warmCheckoutBindingsTimeout);
    }
    warmCheckoutBindingsTimeout = window.setTimeout(() => {
      warmCheckoutBindingsTimeout = null;
      warmCheckoutBindingsSafely();
    }, delayMs);
  };
  const scheduleInitialWarmCheckoutBindings = () => {
    scheduleWarmCheckoutBindings(0);
    window.setTimeout(() => scheduleWarmCheckoutBindings(0), 250);
    window.setTimeout(() => scheduleWarmCheckoutBindings(0), 1000);
  };
  const bindCheckoutWarmListeners = () => {
    if (checkoutWarmListenersBound) return;
    checkoutWarmListenersBound = true;
    document.addEventListener("input", () => scheduleWarmCheckoutBindings(), true);
    document.addEventListener("change", () => scheduleWarmCheckoutBindings(), true);
  };
  const initialize = () => {
    installTrackEventBridge();
    try {
      resetBusyBoundElements();
      initializeWebVitalsTracking();
      bindManifest();
      bindCheckoutWarmListeners();
      scheduleInitialWarmCheckoutBindings();
      handleCheckoutReturn();
      if (!(config.pageStage === "sales" && checkoutStatusFromLocation())) {
        trackInitialPageView();
      }
      initializeEngagementTrackingSafely();
      initializeViewTrackingSafely();
      initializeInteractionTrackingSafely();
      initializeAddToCartTrackingSafely();
    } catch (error) {
      console.error("[HtmlDeployArtifact] Failed to initialize.", error);
    }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
  window.addEventListener("pageshow", () => {
    resetBusyBoundElements();
  });
})();
            </script>""".replace(
            "__MOS_HTML_DEPLOY_CONFIG__", _safe_inline_json(script_config)
        ).replace(
            "__MOS_STANDALONE_META_PIXEL_DEFER_TIMEOUT_MS__",
            str(_STANDALONE_META_PIXEL_DEFER_TIMEOUT_MS),
        )

        block = (
            "<!-- MOS_HTML_DEPLOY_BRIDGE_START -->"
            f"{runtime_script}"
            "<!-- MOS_HTML_DEPLOY_BRIDGE_END -->"
        )
        if prepared_html_document is None:
            html_document = self._prepare_html_deploy_document(
                site_dir=site_dir,
                product_slug=product_slug,
                funnel_slug=funnel_slug,
                page_slug=page_slug,
                page_payload=page_payload,
                server_names=server_names,
                upstream_api_base_root=upstream_api_base_root,
                mirrored_url_map=mirrored_url_map,
                mirrored_target_paths=mirrored_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
            )
        else:
            html_document = prepared_html_document
        start_marker = "<!-- MOS_HTML_DEPLOY_BRIDGE_START -->"
        end_marker = "<!-- MOS_HTML_DEPLOY_BRIDGE_END -->"
        if start_marker in html_document and end_marker in html_document:
            start_idx = html_document.index(start_marker)
            end_idx = html_document.index(end_marker) + len(end_marker)
            return _minify_standalone_imported_html_document(
                html_document[:start_idx] + block + html_document[end_idx:]
            )
        if "</body>" in html_document.lower():
            return _minify_standalone_imported_html_document(
                re.sub(
                    r"</body>",
                    lambda match: f"{block}{match.group(0)}",
                    html_document,
                    count=1,
                    flags=re.IGNORECASE,
                )
            )
        if "</html>" in html_document.lower():
            return _minify_standalone_imported_html_document(
                re.sub(
                    r"</html>",
                    lambda match: f"{block}{match.group(0)}",
                    html_document,
                    count=1,
                    flags=re.IGNORECASE,
                )
            )
        return _minify_standalone_imported_html_document(f"{html_document}{block}")

    def _prepare_html_deploy_document(
        self,
        *,
        site_dir: str,
        product_slug: str,
        funnel_slug: str,
        page_slug: str,
        page_payload: Dict[str, Any],
        server_names: list[str],
        upstream_api_base_root: str | None = None,
        mirrored_url_map: dict[str, str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
    ) -> str:
        context_label = f"Artifact funnel '{product_slug}/{funnel_slug}/{page_slug}'"
        props = self._extract_standalone_imported_html_props(
            product_slug=product_slug,
            funnel_slug=funnel_slug,
            page_slug=page_slug,
            page_payload=page_payload,
        )
        page_stage = str(page_payload.get("stage") or "").strip()
        if not page_stage:
            raise ValueError(f"{context_label} stage is required for HTML deploy export.")

        html_document = str(props["htmlDocument"])
        normalized_server_hosts: set[str] = set()
        for raw_server_name in server_names:
            server_name = str(raw_server_name or "").strip()
            if not server_name:
                continue
            parsed = urlsplit(server_name if "://" in server_name else f"https://{server_name}")
            host = parsed.netloc.strip().lower()
            if host:
                normalized_server_hosts.add(host)
        upstream_api_root = str(upstream_api_base_root or "").strip()
        if upstream_api_root:
            parsed = urlsplit(
                upstream_api_root if "://" in upstream_api_root else f"https://{upstream_api_root}"
            )
            host = parsed.netloc.strip().lower()
            if host:
                normalized_server_hosts.add(host)
        if page_stage in {"sales", "pre_sales"}:
            html_document = _normalize_standalone_public_asset_urls(
                html_document,
                allowed_hosts=normalized_server_hosts,
            )
        static_asset_route_prefixes = (
            "/assets/",
            f"/{product_slug}/{funnel_slug}/{page_slug}/assets/",
            f"/{product_slug}/assets/",
        )
        html_document = self._mirror_standalone_imported_html_image_assets(
            site_dir=site_dir,
            html_document=html_document,
            skip_hosts=normalized_server_hosts,
            static_asset_route_prefixes=static_asset_route_prefixes,
            mirrored_url_map=mirrored_url_map,
            mirrored_target_paths=mirrored_target_paths,
            standalone_served_assets=standalone_served_assets,
            standalone_image_sources=standalone_image_sources,
            context_label=context_label,
        )
        html_document = _rewrite_relative_standalone_static_asset_references(
            html_document,
            standalone_served_assets=standalone_served_assets,
            context_label=context_label,
            asset_route_prefixes=static_asset_route_prefixes,
        )
        if page_stage in {"sales", "pre_sales"}:
            html_document = self._replace_html_deploy_tailwind_runtime(html_document=html_document)
            html_document = self._localize_standalone_imported_html_stylesheets(
                site_dir=site_dir,
                html_document=html_document,
                context_label=context_label,
                mirrored_asset_url_cache=mirrored_url_map,
                mirrored_target_paths=mirrored_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
            )
            origin_hints = _origin_hint_markup_for_html_document(html_document)
            if origin_hints:
                html_document = _inject_head_html_block(
                    html_document=html_document, block=origin_hints
                )
        html_document = self._standardize_html_deploy_product_favicons(
            site_dir=site_dir,
            product_slug=product_slug,
            html_document=html_document,
            uploaded_target_paths=mirrored_target_paths,
            standalone_served_assets=standalone_served_assets,
            standalone_image_sources=standalone_image_sources,
            context_label=context_label,
        )
        if _STANDALONE_ENABLE_HTML_DEPLOY_OPTIMIZATION and page_stage != "sales":
            image_rewrite_baseline_html = html_document
            html_document = self._rewrite_standalone_imported_html_compressed_images(
                site_dir=site_dir,
                html_document=html_document,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
                uploaded_target_paths=mirrored_target_paths,
                context_label=context_label,
                page_stage=page_stage,
            )
            html_document = self._rewrite_standalone_imported_html_responsive_images(
                site_dir=site_dir,
                html_document=html_document,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
                uploaded_target_paths=mirrored_target_paths,
                context_label=context_label,
                page_stage=page_stage,
            )
            if not _is_presales_stage(page_stage) and html_document != image_rewrite_baseline_html:
                self._validate_html_deploy_visual_parity(
                    before_html=image_rewrite_baseline_html,
                    after_html=html_document,
                    standalone_served_assets=standalone_served_assets,
                    context_label=context_label,
                )
        if _STANDALONE_ENABLE_HTML_DEPLOY_OPTIMIZATION:
            html_document = _optimize_standalone_imported_html_document(html_document)
            render_optimization_css = _build_standalone_render_optimization_css(
                page_stage=page_stage
            )
            if render_optimization_css:
                html_document = _inject_head_html_block(
                    html_document=html_document,
                    block=f'<style data-mos-render-optimization="true">{render_optimization_css}</style>',
                )
            preload_image_spec = _resolve_imported_html_preload_image_spec(html_document)
            if preload_image_spec:
                preload_href = escape(str(preload_image_spec.get("href") or ""), quote=True)
                preload_imagesrcset_value = str(preload_image_spec.get("imagesrcset") or "").strip()
                preload_imagesizes_value = str(preload_image_spec.get("imagesizes") or "").strip()
                preload_imagesrcset = (
                    f'imagesrcset="{escape(preload_imagesrcset_value, quote=True)}" '
                    if preload_imagesrcset_value
                    else ""
                )
                preload_imagesizes = (
                    f'imagesizes="{escape(preload_imagesizes_value, quote=True)}" '
                    if preload_imagesizes_value
                    else ""
                )
                preload_block = (
                    f'<link rel="preload" as="image" fetchpriority="high" '
                    f'href="{preload_href}" '
                    f"{preload_imagesrcset}"
                    f"{preload_imagesizes}"
                    'data-mos-standalone-entry-preload="true">'
                )
                html_document = _inject_head_html_block(
                    html_document=html_document, block=preload_block
                )
        html_document = _rewrite_relative_standalone_static_asset_references(
            html_document,
            standalone_served_assets=standalone_served_assets,
            context_label=context_label,
            asset_route_prefixes=static_asset_route_prefixes,
        )
        return html_document

    def _prepare_standalone_imported_html_document(
        self,
        *,
        site_dir: str,
        product_slug: str,
        funnel_slug: str,
        page_slug: str,
        page_payload: Dict[str, Any],
        server_names: list[str],
        upstream_api_base_root: str | None = None,
        mirrored_url_map: dict[str, str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
    ) -> str:
        return self._prepare_html_deploy_document(
            site_dir=site_dir,
            product_slug=product_slug,
            funnel_slug=funnel_slug,
            page_slug=page_slug,
            page_payload=page_payload,
            server_names=server_names,
            upstream_api_base_root=upstream_api_base_root,
            mirrored_url_map=mirrored_url_map,
            mirrored_target_paths=mirrored_target_paths,
            standalone_served_assets=standalone_served_assets,
            standalone_image_sources=standalone_image_sources,
        )

    def _write_funnel_artifact_standalone_html_routes(
        self,
        *,
        site_dir: str,
        source: FunnelArtifactSourceSpec,
        public_server_names: list[str],
        mirrored_target_paths: set[str],
        standalone_served_assets: dict[str, _StandaloneServedAsset],
        standalone_image_sources: dict[str, _StandaloneImageSource],
    ) -> None:
        (
            _artifact,
            _meta,
            products,
            _asset_items,
            _static_asset_items,
        ) = self._resolve_funnel_artifact_payload_sections(source=source)
        preferred_export_target = self._resolve_preferred_funnel_artifact_export_target(
            source=source
        )
        preferred_product_slug = ""
        preferred_funnel_payload: Optional[Dict[str, Any]] = None
        if preferred_export_target is not None:
            preferred_product_slug = str(preferred_export_target.get("productSlug") or "").strip()
            if isinstance(preferred_export_target.get("funnelPayload"), dict):
                preferred_funnel_payload = preferred_export_target["funnelPayload"]

        written_route_paths: set[str] = set()
        route_html_by_path: dict[str, str] = {}
        mirrored_url_map: dict[str, str] = {}
        for raw_product_slug, product_payload in products.items():
            product_slug = str(raw_product_slug or "").strip()
            if not product_slug:
                continue
            if preferred_product_slug and product_slug != preferred_product_slug:
                continue
            if "/" in product_slug or "\\" in product_slug:
                raise ValueError(f"Invalid artifact product slug '{product_slug}'.")
            if not isinstance(product_payload, dict):
                raise ValueError(
                    f"Artifact product payload for '{product_slug}' must be an object."
                )

            product_meta = product_payload.get("meta")
            funnels = product_payload.get("funnels")
            if not isinstance(product_meta, dict):
                raise ValueError(f"Artifact product '{product_slug}' is missing a meta object.")
            if not isinstance(funnels, dict):
                raise ValueError(f"Artifact product '{product_slug}' is missing a funnels object.")

            seen_funnel_path_tokens: set[str] = set()
            for raw_funnel_slug, funnel_payload in funnels.items():
                funnel_slug = str(raw_funnel_slug or "").strip()
                if not funnel_slug:
                    continue
                if (
                    preferred_funnel_payload is not None
                    and funnel_payload is not preferred_funnel_payload
                ):
                    continue
                if "/" in funnel_slug or "\\" in funnel_slug:
                    raise ValueError(
                        f"Invalid artifact funnel slug '{funnel_slug}' for product '{product_slug}'."
                    )
                if not isinstance(funnel_payload, dict):
                    raise ValueError(
                        f"Artifact funnel payload for '{product_slug}/{funnel_slug}' must be an object."
                    )

                funnel_meta = funnel_payload.get("meta")
                pages = funnel_payload.get("pages")
                if not isinstance(funnel_meta, dict):
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a meta object."
                    )
                if not isinstance(pages, dict):
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a pages object."
                    )

                canonical_funnel_meta = self._canonicalize_funnel_artifact_meta(
                    funnel_meta=funnel_meta
                )
                entry_slug = self._canonical_funnel_artifact_page_slug(
                    canonical_funnel_meta.get("entrySlug")
                )
                if not entry_slug:
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a canonical entry slug for HTML deploy export."
                    )

                canonical_page_payloads: dict[str, Dict[str, Any]] = {}
                prepared_imported_html_documents: dict[str, str] = {}
                for raw_page_slug, raw_page_payload in pages.items():
                    page_slug = str(raw_page_slug or "").strip()
                    if not page_slug:
                        continue
                    if "/" in page_slug or "\\" in page_slug:
                        raise ValueError(
                            f"Invalid artifact page slug '{page_slug}' for funnel '{product_slug}/{funnel_slug}'."
                        )
                    if not isinstance(raw_page_payload, dict):
                        raise ValueError(
                            f"Artifact page payload for '{product_slug}/{funnel_slug}/{page_slug}' must be an object."
                        )

                    canonical_page_slug = self._canonical_funnel_artifact_page_slug(page_slug)
                    if not canonical_page_slug:
                        continue
                    if canonical_page_slug in canonical_page_payloads:
                        raise ValueError(
                            f"Artifact funnel '{product_slug}/{funnel_slug}' duplicates page slug '{canonical_page_slug}'."
                        )

                    canonical_page_payloads[canonical_page_slug] = (
                        self._canonicalize_funnel_artifact_page_payload(
                            page_slug=page_slug,
                            page_payload=raw_page_payload,
                        )
                    )
                    canonical_page_payload = canonical_page_payloads[canonical_page_slug]
                    puck_data = canonical_page_payload.get("puckData")
                    content = puck_data.get("content") if isinstance(puck_data, dict) else None
                    block = (
                        content[0]
                        if isinstance(content, list)
                        and len(content) == 1
                        and isinstance(content[0], dict)
                        else None
                    )
                    if str(block.get("type") or "").strip() == "ImportedHtmlDocument":
                        prepared_imported_html_documents[canonical_page_slug] = (
                            self._prepare_html_deploy_document(
                                site_dir=site_dir,
                                product_slug=product_slug,
                                funnel_slug=funnel_slug,
                                page_slug=canonical_page_slug,
                                page_payload=canonical_page_payload,
                                server_names=public_server_names,
                                upstream_api_base_root=str(source.upstream_api_base_root or ""),
                                mirrored_url_map=mirrored_url_map,
                                mirrored_target_paths=mirrored_target_paths,
                                standalone_served_assets=standalone_served_assets,
                                standalone_image_sources=standalone_image_sources,
                            )
                        )

                if entry_slug not in canonical_page_payloads:
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' entrySlug '{entry_slug}' was not found in pages."
                    )

                funnel_path_tokens = self._resolve_funnel_path_tokens_for_source(
                    source=source,
                    product_slug=product_slug,
                    funnel_slug=funnel_slug,
                    funnel_meta=canonical_funnel_meta,
                )
                for funnel_path_token in funnel_path_tokens:
                    if funnel_path_token in seen_funnel_path_tokens:
                        raise ValueError(
                            f"Artifact product '{product_slug}' duplicates funnel path token '{funnel_path_token}'."
                        )
                    seen_funnel_path_tokens.add(funnel_path_token)

                    rendered_pages: dict[str, str] = {}
                    for page_slug, page_payload in canonical_page_payloads.items():
                        rendered_pages[page_slug] = self._render_standalone_funnel_artifact_page(
                            site_dir=site_dir,
                            product_slug=product_slug,
                            funnel_slug=funnel_slug,
                            funnel_meta=canonical_funnel_meta,
                            funnel_path_token=funnel_path_token,
                            page_slug=page_slug,
                            page_payload=page_payload,
                            funnel_payload=funnel_payload,
                            source=source,
                            public_server_names=public_server_names,
                            mirrored_url_map=mirrored_url_map,
                            mirrored_target_paths=mirrored_target_paths,
                            standalone_served_assets=standalone_served_assets,
                            standalone_image_sources=standalone_image_sources,
                            prepared_imported_html_document=prepared_imported_html_documents.get(
                                page_slug
                            ),
                            prepared_imported_html_documents=prepared_imported_html_documents,
                        )
                    entry_html_document = rendered_pages.get(entry_slug)
                    if entry_html_document is None:
                        raise ValueError(
                            f"Artifact funnel '{product_slug}/{funnel_slug}' entrySlug '{entry_slug}' was not found in rendered standalone pages."
                        )

                    entry_route_dir = f"{site_dir}/{product_slug}/{funnel_path_token}"
                    entry_route_path = f"{entry_route_dir}/index.html"
                    if entry_route_path in written_route_paths:
                        raise ValueError(
                            f"Standalone artifact route '{entry_route_path}' was generated more than once."
                        )
                    self.upload_file(entry_html_document, entry_route_path)
                    written_route_paths.add(entry_route_path)
                    route_html_by_path[entry_route_path] = entry_html_document

                    for page_slug, html_document in rendered_pages.items():
                        page_route_dir = f"{entry_route_dir}/{page_slug}"
                        page_route_path = f"{page_route_dir}/index.html"
                        if page_route_path in written_route_paths:
                            raise ValueError(
                                f"Standalone artifact route '{page_route_path}' was generated more than once."
                            )
                        self.upload_file(html_document, page_route_path)
                        written_route_paths.add(page_route_path)
                        route_html_by_path[page_route_path] = html_document

        for alias in _html_deploy_route_alias_specs(source=source):
            source_index_path = _html_deploy_index_path_for_route(
                site_dir=site_dir,
                route_path=alias["from"],
            )
            target_index_path = _html_deploy_index_path_for_route(
                site_dir=site_dir,
                route_path=alias["to"],
            )
            if source_index_path in written_route_paths:
                raise ValueError(
                    f"HTML deploy route alias source '{alias['from']}' conflicts with a generated route."
                )
            target_html_document = route_html_by_path.get(target_index_path)
            if target_html_document is None:
                raise ValueError(
                    f"HTML deploy route alias '{alias['from']}' targets missing route '{alias['to']}'."
                )
            self.upload_file(target_html_document, source_index_path)
            written_route_paths.add(source_index_path)
            route_html_by_path[source_index_path] = target_html_document

    def _write_funnel_artifact_payload(
        self, *, site_dir: str, source: FunnelArtifactSourceSpec
    ) -> None:
        (
            _artifact,
            _meta,
            products,
            _asset_items,
            _static_asset_items,
        ) = self._resolve_funnel_artifact_payload_sections(source=source)
        self._write_funnel_artifact_assets(site_dir=site_dir, source=source)

        base_root = f"{site_dir}/api/public/funnels"
        self.run(f"mkdir -p {shlex.quote(base_root)}")

        for raw_product_slug, product_payload in products.items():
            product_slug = str(raw_product_slug or "").strip()
            if not product_slug:
                continue
            if "/" in product_slug or "\\" in product_slug:
                raise ValueError(f"Invalid artifact product slug '{product_slug}'.")
            if not isinstance(product_payload, dict):
                raise ValueError(
                    f"Artifact product payload for '{product_slug}' must be an object."
                )

            product_meta = product_payload.get("meta")
            funnels = product_payload.get("funnels")
            if not isinstance(product_meta, dict):
                raise ValueError(f"Artifact product '{product_slug}' is missing a meta object.")
            if not isinstance(funnels, dict):
                raise ValueError(f"Artifact product '{product_slug}' is missing a funnels object.")

            product_dir = f"{base_root}/{product_slug}"
            self.upload_file(
                json.dumps(product_meta, ensure_ascii=False), f"{product_dir}/meta.json"
            )
            seen_funnel_path_tokens: set[str] = set()

            for raw_funnel_slug, funnel_payload in funnels.items():
                funnel_slug = str(raw_funnel_slug or "").strip()
                if not funnel_slug:
                    continue
                if "/" in funnel_slug or "\\" in funnel_slug:
                    raise ValueError(
                        f"Invalid artifact funnel slug '{funnel_slug}' for product '{product_slug}'."
                    )
                if not isinstance(funnel_payload, dict):
                    raise ValueError(
                        f"Artifact funnel payload for '{product_slug}/{funnel_slug}' must be an object."
                    )

                funnel_meta = funnel_payload.get("meta")
                pages = funnel_payload.get("pages")
                commerce = funnel_payload.get("commerce")
                if not isinstance(funnel_meta, dict):
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a meta object."
                    )
                if not isinstance(pages, dict):
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a pages object."
                    )

                canonical_funnel_meta = self._canonicalize_funnel_artifact_meta(
                    funnel_meta=funnel_meta
                )

                funnel_path_tokens = self._resolve_funnel_path_tokens(
                    product_slug=product_slug,
                    funnel_slug=funnel_slug,
                    funnel_meta=canonical_funnel_meta,
                )

                for funnel_path_token in funnel_path_tokens:
                    if funnel_path_token in seen_funnel_path_tokens:
                        raise ValueError(
                            f"Artifact product '{product_slug}' duplicates funnel path token '{funnel_path_token}'."
                        )
                    seen_funnel_path_tokens.add(funnel_path_token)

                    funnel_dir = f"{product_dir}/{funnel_path_token}"
                    pages_dir = f"{funnel_dir}/pages"
                    self.upload_file(
                        json.dumps(canonical_funnel_meta, ensure_ascii=False),
                        f"{funnel_dir}/meta.json",
                    )

                    if isinstance(commerce, dict):
                        self.upload_file(
                            json.dumps(commerce, ensure_ascii=False), f"{funnel_dir}/commerce.json"
                        )

                    written_page_slugs: set[str] = set()
                    for raw_page_slug, page_payload in pages.items():
                        page_slug = str(raw_page_slug or "").strip()
                        if not page_slug:
                            continue
                        if "/" in page_slug or "\\" in page_slug:
                            raise ValueError(
                                f"Invalid artifact page slug '{page_slug}' for funnel '{product_slug}/{funnel_slug}'."
                            )
                        if not isinstance(page_payload, dict):
                            raise ValueError(
                                f"Artifact page payload for '{product_slug}/{funnel_slug}/{page_slug}' must be an object."
                            )
                        canonical_page_slug = self._canonical_funnel_artifact_page_slug(page_slug)
                        if not canonical_page_slug:
                            continue
                        if canonical_page_slug in written_page_slugs:
                            raise ValueError(
                                f"Artifact funnel '{product_slug}/{funnel_slug}' duplicates page slug '{canonical_page_slug}'."
                            )
                        canonical_page_payload = self._canonicalize_funnel_artifact_page_payload(
                            page_slug=page_slug,
                            page_payload=page_payload,
                        )
                        self.upload_file(
                            json.dumps(canonical_page_payload, ensure_ascii=False),
                            f"{pages_dir}/{canonical_page_slug}.json",
                        )
                        written_page_slugs.add(canonical_page_slug)

    def _build_funnel_artifact_release_manifest(
        self,
        *,
        app: ApplicationSpec,
        source: FunnelArtifactSourceSpec,
        render_mode: FunnelArtifactRenderMode,
    ) -> Dict[str, Any]:
        artifact = source.artifact if isinstance(source.artifact, dict) else {}
        artifact_meta = artifact.get("meta") if isinstance(artifact.get("meta"), dict) else {}
        products = artifact.get("products") if isinstance(artifact.get("products"), dict) else {}
        default_route = self._resolve_funnel_artifact_default_route(source=source)
        upstream_host = urlsplit(source.upstream_api_base_root.rstrip("/")).netloc
        release_metadata = (
            source.release_metadata if isinstance(source.release_metadata, dict) else {}
        )

        funnels_manifest: List[Dict[str, Any]] = []
        html_artifact_kinds: set[str] = set()
        has_posthog = False
        has_meta_pixel = False
        for product_slug, product_payload in products.items():
            if not isinstance(product_payload, dict):
                continue
            funnels = product_payload.get("funnels")
            if not isinstance(funnels, dict):
                continue
            for funnel_token, funnel_payload in funnels.items():
                if not isinstance(funnel_payload, dict):
                    continue
                funnel_meta = (
                    funnel_payload.get("meta")
                    if isinstance(funnel_payload.get("meta"), dict)
                    else {}
                )
                pages = (
                    funnel_payload.get("pages")
                    if isinstance(funnel_payload.get("pages"), dict)
                    else {}
                )
                pages_manifest: List[Dict[str, Any]] = []
                for page_slug, page_payload in pages.items():
                    if not isinstance(page_payload, dict):
                        continue
                    tracking = page_payload.get("tracking")
                    if isinstance(tracking, dict):
                        has_posthog = has_posthog or bool(
                            str(tracking.get("posthogProjectApiKey") or "").strip()
                        )
                        has_meta_pixel = has_meta_pixel or bool(
                            str(tracking.get("metaPixelId") or "").strip()
                        )
                    instrumentation_manifest: Dict[str, Any] = {}
                    puck_data = page_payload.get("puckData")
                    content = puck_data.get("content") if isinstance(puck_data, dict) else None
                    block = (
                        content[0]
                        if isinstance(content, list)
                        and len(content) == 1
                        and isinstance(content[0], dict)
                        else None
                    )
                    props = block.get("props") if isinstance(block, dict) else None
                    if isinstance(props, dict) and isinstance(
                        props.get("instrumentationManifest"), dict
                    ):
                        instrumentation_manifest = props["instrumentationManifest"]
                    html_artifact_kind = str(
                        instrumentation_manifest.get("htmlArtifactKind") or ""
                    ).strip()
                    if html_artifact_kind:
                        html_artifact_kinds.add(html_artifact_kind)
                    pages_manifest.append(
                        {
                            "pageId": str(page_payload.get("pageId") or "").strip(),
                            "slug": str(page_slug),
                            "stage": str(page_payload.get("stage") or "").strip() or "custom",
                            "htmlArtifactKind": html_artifact_kind or None,
                            "htmlDeploySchemaVersion": (
                                str(instrumentation_manifest.get("schemaVersion") or "").strip()
                                or None
                            ),
                        }
                    )
                funnels_manifest.append(
                    {
                        "productSlug": str(product_slug),
                        "funnelToken": str(funnel_token),
                        "funnelId": str(funnel_meta.get("funnelId") or "").strip(),
                        "publicationId": str(funnel_meta.get("publicationId") or "").strip(),
                        "entrySlug": str(funnel_meta.get("entrySlug") or "").strip(),
                        "pages": pages_manifest,
                    }
                )

        static_scan = release_metadata.get("staticScan")
        if not isinstance(static_scan, dict):
            static_scan = (
                artifact_meta.get("staticScan")
                if isinstance(artifact_meta.get("staticScan"), dict)
                else {}
            )
        if not static_scan:
            static_scan = {"status": "not_configured"}

        manifest: Dict[str, Any] = {
            "manifestVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "deployJobId": str(release_metadata.get("deployJobId") or "").strip() or None,
            "sourceCommit": str(release_metadata.get("sourceCommit") or "").strip() or None,
            "artifactId": source.artifact_id
            or str(artifact_meta.get("artifactId") or "").strip()
            or None,
            "artifactVersion": source.artifact_version,
            "renderMode": render_mode.value if hasattr(render_mode, "value") else str(render_mode),
            "htmlDeploySchemaVersion": (
                "html-deploy-v1"
                if render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML
                else None
            ),
            "htmlArtifactKinds": sorted(html_artifact_kinds) if html_artifact_kinds else None,
            "workloadName": app.name,
            "clientId": source.client_id,
            "defaultRoute": {
                "policy": source.default_route_policy,
                "defaultPageSlug": source.default_page_slug,
                "segments": default_route,
                "path": "/" + "/".join(default_route) + "/" if default_route else None,
            },
            "routeManifest": {
                "legacyRedirects": _html_deploy_legacy_redirect_specs(source=source),
                "routeAliases": _html_deploy_route_alias_specs(source=source),
                "funnelPathAliases": _html_deploy_funnel_path_alias_specs(source=source),
            },
            "upstreamApiOriginHost": upstream_host or None,
            "tracking": {
                "posthog": has_posthog,
                "metaPixel": has_meta_pixel,
            },
            "bridge": {
                "version": (
                    _STANDALONE_IMPORTED_HTML_BRIDGE_VERSION
                    if render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML
                    else None
                )
            },
            "staticScan": static_scan,
            "identityAudit": (
                artifact_meta.get("identityAudit") if isinstance(artifact_meta, dict) else None
            ),
            "publicationOverrides": (
                artifact_meta.get("publicationOverrides")
                if isinstance(artifact_meta.get("publicationOverrides"), list)
                else []
            ),
            "funnels": funnels_manifest,
        }
        return {key: value for key, value in manifest.items() if value is not None}

    def _write_funnel_artifact_release_manifest(
        self,
        *,
        site_dir: str,
        app: ApplicationSpec,
        source: FunnelArtifactSourceSpec,
        render_mode: FunnelArtifactRenderMode,
    ) -> None:
        manifest = self._build_funnel_artifact_release_manifest(
            app=app,
            source=source,
            render_mode=render_mode,
        )
        self.upload_file(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            f"{site_dir}/mos-release-manifest.json",
        )

    def _configure_funnel_artifact_site(self, app: ApplicationSpec):
        source = app.source_ref
        if source is None:
            raise ValueError("source_ref is required when source_type='funnel_artifact'.")
        if not isinstance(source, FunnelArtifactSourceSpec):
            raise ValueError(
                "source_ref must be FunnelArtifactSourceSpec when source_type='funnel_artifact'."
            )

        render_mode = source.artifact_render_mode

        app_dir = f"{app.destination_path}/{app.name}"
        site_dir = f"{app_dir}/{_FUNNEL_ARTIFACT_LIVE_DIRNAME}"
        app_dir_q = shlex.quote(app_dir)
        site_dir_q = shlex.quote(site_dir)
        build_site_dir = site_dir
        standalone_release_id = ""
        standalone_activation_deferred = False
        if render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML:
            releases_dir = f"{app_dir}/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}"
            standalone_release_id = _resolve_funnel_artifact_release_id(source=source)
            standalone_activation_deferred = _should_defer_funnel_artifact_activation(source=source)
            build_site_dir = f"{releases_dir}/{standalone_release_id}"
            self.run(f"mkdir -p {app_dir_q}")
            self.run(f"mkdir -p {shlex.quote(releases_dir)}")
            self.run(f"rm -rf {shlex.quote(build_site_dir)}")
            self.run(f"mkdir -p {shlex.quote(build_site_dir)}")
        else:
            self.run(f"mkdir -p {app_dir_q}")
            self.run(f"rm -rf {site_dir_q}")
            self.run(f"mkdir -p {site_dir_q}")
        standalone_uploaded_target_paths: set[str] = set()
        standalone_served_assets: dict[str, _StandaloneServedAsset] = {}
        standalone_image_sources: dict[str, _StandaloneImageSource] = {}
        if render_mode == FunnelArtifactRenderMode.RUNTIME_BUNDLE:
            runtime_dist_path = (source.runtime_dist_path or "").strip()
            if not runtime_dist_path:
                raise ValueError(
                    "source_ref.runtime_dist_path must be non-empty for source_type='funnel_artifact'."
                )

            if self._path_exists(runtime_dist_path):
                dist_q = shlex.quote(runtime_dist_path)
                self.run(f"cp -R {dist_q}/. {site_dir_q}/")
            else:
                local_dist = self._ensure_local_runtime_dist(runtime_dist_path)
                if local_dist is None:
                    raise ValueError(
                        "source_ref.runtime_dist_path was not found on target server or local control-plane host: "
                        f"{runtime_dist_path}. Build/copy the runtime bundle there or set "
                        "DEPLOY_ARTIFACT_RUNTIME_DIST_PATH to a valid path."
                    )
                runtime_hash = self._hash_local_directory(local_dist)
                cached_runtime_dir = f"{_RUNTIME_CACHE_DIR}/{runtime_hash}"
                if not self._path_exists(cached_runtime_dir):
                    self.run(f"mkdir -p {shlex.quote(_RUNTIME_CACHE_DIR)}")
                    self.run(f"mkdir -p {shlex.quote(cached_runtime_dir)}")
                    self._upload_local_directory(
                        local_dir=local_dist, remote_dir=cached_runtime_dir
                    )
                cached_runtime_q = shlex.quote(cached_runtime_dir)
                self.run(f"cp -R {cached_runtime_q}/. {site_dir_q}/")
            self._inject_funnel_runtime_config(site_dir=site_dir, source=source)
            self._write_funnel_artifact_payload(site_dir=site_dir, source=source)
            self._write_funnel_artifact_release_manifest(
                site_dir=site_dir,
                app=app,
                source=source,
                render_mode=render_mode,
            )
            self._replace_api_base_tokens(
                site_dir=site_dir, upstream_api_base_root=source.upstream_api_base_root
            )
            self._validate_funnel_artifact_site_output(
                site_dir=site_dir,
                source=source,
                render_mode=render_mode,
            )
        elif render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML:
            public_server_names = self._normalize_server_names(
                app.workspace_server_names
            ) or self._normalize_server_names(app.service_config.server_names)
            self._write_funnel_artifact_assets(
                site_dir=build_site_dir,
                source=source,
                uploaded_target_paths=standalone_uploaded_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
            )
            self._write_funnel_artifact_standalone_html_routes(
                site_dir=build_site_dir,
                source=source,
                public_server_names=public_server_names,
                mirrored_target_paths=standalone_uploaded_target_paths,
                standalone_served_assets=standalone_served_assets,
                standalone_image_sources=standalone_image_sources,
            )
            self._write_funnel_artifact_release_manifest(
                site_dir=build_site_dir,
                app=app,
                source=source,
                render_mode=render_mode,
            )
            self._materialize_html_deploy_release_static_dependencies(
                site_dir=build_site_dir,
                public_server_names=public_server_names,
            )
            self._validate_html_deploy_release_asset_closure(site_dir=build_site_dir)
            self._validate_funnel_artifact_site_output(
                site_dir=build_site_dir,
                source=source,
                render_mode=render_mode,
            )
        else:  # pragma: no cover - defensive guard for future enum drift
            raise ValueError(f"Unsupported funnel artifact render mode '{render_mode}'.")

        server_names = self._normalize_server_names(app.service_config.server_names)
        server_name_line = self._server_name_directive(server_names)
        if server_names:
            listen_port = 80
        else:
            ports = list(app.service_config.ports or [])
            if not ports:
                raise ValueError(
                    "service_config.ports must include one port for source_type='funnel_artifact' "
                    "when server_names is empty."
                )
            listen_port = int(ports[0])

        upstream_api_base_root = source.upstream_api_base_root.rstrip("/")
        upstream_api_proxy_base = upstream_api_base_root
        upstream_api_proxy_host_header = "$host"
        if render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML:
            (
                upstream_api_proxy_base,
                upstream_api_proxy_host_header,
            ) = _resolve_standalone_upstream_api_origin(
                upstream_api_base_root=source.upstream_api_base_root,
            )
        canonical_redirect_host = None
        canonical_redirect_scheme = "http"
        workspace_server_names = self._normalize_server_names(app.workspace_server_names)
        if workspace_server_names:
            canonical_redirect_host = workspace_server_names[0]
            canonical_redirect_scheme = "https"
        elif server_names:
            canonical_redirect_host = server_names[0]
            canonical_redirect_scheme = "https" if app.service_config.https else "http"

        canonical_host_guard = ""
        if (
            render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML
            and canonical_redirect_host
        ):
            canonical_redirect_origin = f"{canonical_redirect_scheme}://{canonical_redirect_host}"
            canonical_host_guard = f"""    set $mos_direct_ip_request 0;
    if ($http_host ~* "^[0-9]{{1,3}}(?:\\.[0-9]{{1,3}}){{3}}(?::[0-9]+)?$") {{
        set $mos_direct_ip_request 1;
    }}
    if ($http_via ~* "BunnyCDN") {{
        set $mos_direct_ip_request 0;
    }}
    if ($mos_direct_ip_request = 1) {{
        return 302 {canonical_redirect_origin}$request_uri;
    }}

"""

        default_route_location = ""
        legacy_redirect_locations = ""
        if render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML:
            route_aliases = _html_deploy_route_alias_specs(source=source)
            has_root_route_alias = any(alias["from"] == "/" for alias in route_aliases)
            default_route = self._resolve_funnel_artifact_default_route(source=source)
            if has_root_route_alias:
                default_route_location = (
                    "    location = / {\n" "        try_files /index.html =404;\n" "    }\n\n"
                )
            elif default_route:
                default_route_path = "/" + "/".join(
                    quote(segment, safe="") for segment in default_route
                )
                redirect_target = f"{default_route_path}$is_args$args"
                if canonical_redirect_host:
                    redirect_target = (
                        f"{canonical_redirect_scheme}://{canonical_redirect_host}"
                        f"{default_route_path}$is_args$args"
                    )
                default_route_location = (
                    "    location = / {\n"
                    '        add_header Cache-Control "no-store" always;\n'
                    f"        return 302 {redirect_target};\n"
                    "    }\n\n"
                )
            legacy_redirect_blocks: list[str] = []
            for redirect in _html_deploy_legacy_redirect_specs(source=source):
                source_path = str(redirect["from"])
                target_path = str(redirect["to"])
                status_code = int(redirect["status"])
                redirect_target = target_path
                if canonical_redirect_host:
                    redirect_target = (
                        f"{canonical_redirect_scheme}://{canonical_redirect_host}" f"{target_path}"
                    )
                if bool(redirect.get("preserveQuery", True)):
                    redirect_target = f"{redirect_target}$is_args$args"
                legacy_redirect_blocks.append(
                    "    location = "
                    + source_path
                    + " {\n"
                    + '        add_header Cache-Control "no-store" always;\n'
                    + f"        return {status_code} {redirect_target};\n"
                    + "    }\n\n"
                )
            legacy_redirect_locations = "".join(legacy_redirect_blocks)

        candidate_release_nginx_pattern = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
        candidate_route_location = ""
        candidate_query_rewrite = ""
        api_public_asset_location = """    location ^~ /api/public/assets/ {
        try_files $uri $uri.webp $uri.jpg $uri.jpeg $uri.png =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
"""
        public_asset_location = """    location ^~ /public/assets/ {
        try_files /api$uri /api$uri.webp /api$uri.jpg /api$uri.jpeg /api$uri.png =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
"""
        root_asset_location = """    location ^~ /assets/ {
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
"""
        standalone_asset_location = f"""    location ^~ {_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}/ {{
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }}
"""
        directory_slash_redirect = ""
        if render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML:
            directory_slash_redirect = _html_deploy_directory_slash_redirect_nginx_block()
            releases_root = f"{app_dir}/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}"
            api_public_asset_location = f"""    location ^~ /api/public/assets/ {{
        set $mos_candidate_asset_prefix "";
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=({candidate_release_nginx_pattern})(?:[&#]|$)") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($http_referer ~ "{_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/({candidate_release_nginx_pattern})/") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}/$1 last;
        }}
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=(?<mos_referer_candidate_release>{candidate_release_nginx_pattern})(?:[&#]|$)") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$mos_referer_candidate_release/$1 last;
        }}
        root {app_dir};
        try_files $mos_candidate_asset_prefix$uri $mos_candidate_asset_prefix$uri.webp $mos_candidate_asset_prefix$uri.jpg $mos_candidate_asset_prefix$uri.jpeg $mos_candidate_asset_prefix$uri.png /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.webp /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.jpg /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.jpeg /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.png =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }}
"""
            public_asset_location = f"""    location ^~ /public/assets/ {{
        set $mos_candidate_asset_prefix "";
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=({candidate_release_nginx_pattern})(?:[&#]|$)") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($http_referer ~ "{_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/({candidate_release_nginx_pattern})/") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}/$1 last;
        }}
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=(?<mos_referer_candidate_release>{candidate_release_nginx_pattern})(?:[&#]|$)") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$mos_referer_candidate_release/$1 last;
        }}
        root {app_dir};
        try_files $mos_candidate_asset_prefix/api$uri $mos_candidate_asset_prefix/api$uri.webp $mos_candidate_asset_prefix/api$uri.jpg $mos_candidate_asset_prefix/api$uri.jpeg $mos_candidate_asset_prefix/api$uri.png $mos_candidate_asset_prefix$uri $mos_candidate_asset_prefix$uri.webp $mos_candidate_asset_prefix$uri.jpg $mos_candidate_asset_prefix$uri.jpeg $mos_candidate_asset_prefix$uri.png /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}/api$uri /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}/api$uri.webp /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}/api$uri.jpg /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}/api$uri.jpeg /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}/api$uri.png /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.webp /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.jpg /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.jpeg /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri.png =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }}
"""
            root_asset_location = f"""    location ^~ /assets/ {{
        set $mos_candidate_asset_prefix "";
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=({candidate_release_nginx_pattern})(?:[&#]|$)") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($http_referer ~ "{_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/({candidate_release_nginx_pattern})/") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}/$1 last;
        }}
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=(?<mos_referer_candidate_release>{candidate_release_nginx_pattern})(?:[&#]|$)") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$mos_referer_candidate_release/$1 last;
        }}
        root {app_dir};
        try_files $mos_candidate_asset_prefix$uri /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }}
"""
            candidate_route_location = f"""
    location ~ "^{_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/(?<mos_candidate_release>{candidate_release_nginx_pattern})/" {{
        add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
        add_header Cache-Control "no-store" always;
        rewrite ^{_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/(.*)$ /$1 break;
        root {releases_root};
        try_files $uri $uri.webp $uri.jpg $uri.jpeg $uri.png $uri/index.html $uri/ =404;
    }}

"""
            candidate_query_rewrite = f"""        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}/$1 last;
        }}
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=(?<mos_referer_candidate_release>{candidate_release_nginx_pattern})(?:[&#]|$)") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$mos_referer_candidate_release/$1 last;
        }}
        if ($http_referer ~ "{_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/(?<mos_ref_path_rel>{candidate_release_nginx_pattern})/") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$mos_ref_path_rel/$1 last;
        }}
"""
            standalone_asset_location = f"""    location ^~ {_STANDALONE_MIRRORED_ASSET_ROUTE_PREFIX}/ {{
        set $mos_candidate_asset_prefix "";
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=({candidate_release_nginx_pattern})(?:[&#]|$)") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($http_referer ~ "{_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/({candidate_release_nginx_pattern})/") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$1";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            set $mos_candidate_asset_prefix "/{_FUNNEL_ARTIFACT_RELEASES_DIRNAME}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}";
        }}
        if ($arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM} ~ "^{candidate_release_nginx_pattern}$") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$arg_{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}/$1 last;
        }}
        if ($http_referer ~ "[?&]{_FUNNEL_ARTIFACT_CANDIDATE_QUERY_PARAM}=(?<mos_referer_candidate_release>{candidate_release_nginx_pattern})(?:[&#]|$)") {{
            rewrite ^/(.*)$ {_FUNNEL_ARTIFACT_CANDIDATE_ROUTE_PREFIX}/$mos_referer_candidate_release/$1 last;
        }}
        root {app_dir};
        try_files $mos_candidate_asset_prefix$uri /{_FUNNEL_ARTIFACT_LIVE_DIRNAME}$uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }}
"""

        conf = f"""server {{
    listen {listen_port};
    server_name {server_name_line};
    root {site_dir};
    index index.html;
    client_max_body_size 25m;
    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};
    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};
    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/javascript application/javascript application/json application/xml image/svg+xml;

{canonical_host_guard}\
{api_public_asset_location}
{public_asset_location}
{root_asset_location}
{standalone_asset_location}
{candidate_route_location}\
    location ^~ /api/ {{
        proxy_pass {upstream_api_proxy_base}/;
        proxy_http_version 1.1;
        proxy_set_header Host {upstream_api_proxy_host_header};
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

{default_route_location}
{legacy_redirect_locations}
    location / {{
{directory_slash_redirect}\
{candidate_query_rewrite}\
        try_files $uri $uri/index.html $uri/ =404;
    }}
}}"""
        if render_mode == FunnelArtifactRenderMode.RUNTIME_BUNDLE:
            conf = conf.replace(
                "try_files $uri $uri/index.html $uri/ =404;",
                "try_files $uri /index.html;",
                1,
            )
        self.upload_file(conf, f"/etc/nginx/sites-available/{app.name}")
        self.run(
            f"ln -sf /etc/nginx/sites-available/{app.name} /etc/nginx/sites-enabled/{app.name}"
        )
        self.run("rm -f /etc/nginx/sites-enabled/default")
        self.run("nginx -t")
        self.run("systemctl reload nginx")
        if app.service_config.https:
            self._enable_https(server_names)
        if (
            render_mode == FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML
            and not standalone_activation_deferred
        ):
            self._activate_funnel_artifact_site_release(
                app_dir=app_dir,
                live_site_dir=site_dir,
                built_site_dir=build_site_dir,
            )

    def _configure_nginx(self, app: ApplicationSpec):
        if app.source_type == ApplicationSourceType.FUNNEL_PUBLICATION:
            self._ensure_nginx()
            self._configure_funnel_publication_proxy(app)
            return
        if app.source_type == ApplicationSourceType.FUNNEL_ARTIFACT:
            self._ensure_nginx()
            self._configure_funnel_artifact_site(app)
            return

        if not app.service_config.ports:
            return

        self._ensure_nginx()

        port = app.service_config.ports[0]
        server_names = self._normalize_server_names(app.service_config.server_names)
        server_name_line = self._server_name_directive(server_names)
        conf = f"""server {{
    listen 80;
    server_name {server_name_line};
    client_max_body_size {_NGINX_APP_CLIENT_MAX_BODY_SIZE};
    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};
    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};
    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }}
}}"""
        self.upload_file(conf, f"/etc/nginx/sites-available/{app.name}")
        self.run(
            f"ln -sf /etc/nginx/sites-available/{app.name} /etc/nginx/sites-enabled/{app.name}"
        )
        self.run("rm -f /etc/nginx/sites-enabled/default")
        self.run("systemctl reload nginx")
        if app.service_config.https:
            self._enable_https(server_names)

    def _configure_git_static_site(self, app: ApplicationSpec, app_dir: str):
        raw_static_root = (app.service_config.static_root or "").strip()
        if not raw_static_root:
            raise ValueError(
                "service_config.static_root is required for git static site deployments."
            )

        static_root_path = (
            raw_static_root if raw_static_root.startswith("/") else f"{app_dir}/{raw_static_root}"
        )
        if not self._path_exists(static_root_path):
            raise ValueError(
                f"Static site root '{static_root_path}' does not exist after build for workload '{app.name}'."
            )

        self._ensure_nginx()

        server_names = self._normalize_server_names(app.service_config.server_names)
        server_name_line = self._server_name_directive(server_names)
        if server_names:
            listen_port = 80
        else:
            ports = list(app.service_config.ports or [])
            if not ports:
                raise ValueError(
                    "service_config.ports must include one port for git static site workloads "
                    "when server_names is empty."
                )
            listen_port = int(ports[0])

        spa_try_files = "try_files $uri $uri/ /index.html;"
        if not app.service_config.spa_fallback:
            spa_try_files = "try_files $uri $uri/ =404;"

        conf = f"""server {{
    listen {listen_port};
    server_name {server_name_line};
    root {static_root_path};
    index index.html;
    client_max_body_size {_NGINX_APP_CLIENT_MAX_BODY_SIZE};
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/javascript application/javascript application/json application/xml image/svg+xml;

    location / {{
        {spa_try_files}
    }}
}}"""
        self.upload_file(conf, f"/etc/nginx/sites-available/{app.name}")
        self.run(
            f"ln -sf /etc/nginx/sites-available/{app.name} /etc/nginx/sites-enabled/{app.name}"
        )
        self.run("rm -f /etc/nginx/sites-enabled/default")
        self.run("nginx -t")
        self.run("systemctl reload nginx")
        if app.service_config.https:
            self._enable_https(server_names)

    def configure_combined_nginx(self, apps: List[ApplicationSpec]):
        """Create a single site config that proxies UI root and API paths on one host."""
        candidates = [a for a in apps if a.service_config.ports]
        if not candidates:
            return

        # Prefer an app named *ui* as the root site; otherwise first app.
        root_app = next((a for a in candidates if "ui" in a.name.lower()), candidates[0])
        root_port = root_app.service_config.ports[0]

        locations = []
        for app in candidates:
            port = app.service_config.ports[0]
            if app is root_app:
                continue
            name = app.name.lower()
            prefix = "/api/" if "api" in name else f"/{app.name}/"
            if not prefix.startswith("/"):
                prefix = f"/{prefix}"
            if not prefix.endswith("/"):
                prefix = f"{prefix}/"
            locations.append(f"""    location {prefix} {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}""")

        server_names: List[str] = []
        https_enabled = False
        for app in candidates:
            server_names.extend(app.service_config.server_names)
            https_enabled = https_enabled or app.service_config.https

        server_names = self._normalize_server_names(server_names)
        server_name_line = self._server_name_directive(server_names)

        config = [
            "server {",
            "    listen 80;",
            f"    server_name {server_name_line};",
            "    client_max_body_size 25m;",
            f"    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};",
            f"    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};",
            f"    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};",
            "    location / {",
            f"        proxy_pass http://127.0.0.1:{root_port}/;",
            "        proxy_http_version 1.1;",
            "        proxy_set_header Upgrade $http_upgrade;",
            "        proxy_set_header Connection 'upgrade';",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "    }",
        ]
        config.extend(locations)
        config.append("}")
        conf = "\n".join(config)
        self.upload_file(conf, "/etc/nginx/sites-available/cloudhand")
        self.run("ln -sf /etc/nginx/sites-available/cloudhand /etc/nginx/sites-enabled/cloudhand")
        self.run("rm -f /etc/nginx/sites-enabled/default || true")
        self.run("systemctl reload nginx")
        if https_enabled:
            self._enable_https(server_names)

    def remove_workload(self, app: ApplicationSpec):
        app_name = (app.name or "").strip()
        if not app_name:
            raise ValueError("Workload name is required for removal.")

        self._disable_service_unit(app_name)

        nginx_removed = False
        if self._remove_path_if_exists(f"/etc/nginx/sites-enabled/{app_name}"):
            nginx_removed = True
        if self._remove_path_if_exists(f"/etc/nginx/sites-available/{app_name}"):
            nginx_removed = True
        if nginx_removed:
            self.run("nginx -t")
            self.run("systemctl reload nginx")

        destination = (app.destination_path or "").rstrip("/")
        if destination:
            app_dir = f"{destination}/{app_name}"
            self._remove_path_if_exists(app_dir, recursive=True)

    def deploy(self, app: ApplicationSpec, configure_nginx: bool = True):
        app_dir = f"{app.destination_path}/{app.name}"

        # 1. System Deps
        if app.build_config.system_packages:
            self.run(
                f"DEBIAN_FRONTEND=noninteractive apt-get update && "
                f"DEBIAN_FRONTEND=noninteractive apt-get install -y {' '.join(app.build_config.system_packages)}"
            )
        if app.source_type in {
            ApplicationSourceType.FUNNEL_PUBLICATION,
            ApplicationSourceType.FUNNEL_ARTIFACT,
        }:
            # Funnel publication/artifact workloads should update in place so the
            # current site keeps serving until the replacement proxy or artifact
            # has been fully written and validated.
            self._disable_service_unit(app.name)
            if configure_nginx:
                self._configure_nginx(app)
            return

        if app.runtime == RuntimeType.NODEJS:
            # Ensure a modern Node runtime regardless of base image defaults.
            self.run(
                "DEBIAN_FRONTEND=noninteractive apt-get purge -y nodejs npm libnode-dev libnode72 || true"
            )
            self.run("DEBIAN_FRONTEND=noninteractive apt-get autoremove -y || true")
            self.run('bash -lc "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -"')
            self.run("DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs")

        if not (app.service_config.static_root and app.service_config.server_names):
            self._assert_ports_available(app)

        # 2. Git Sync
        repo_url = (app.repo_url or "").strip()
        if not repo_url:
            raise ValueError(f"Workload '{app.name}' requires repo_url for source_type='git'.")

        gh_token = (
            os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_PAT") or ""
        )
        try:
            self.run(f"test -d {app_dir}")
            fetch_cmd = f"git fetch origin && git reset --hard origin/{app.branch}"
            if gh_token:
                fetch_cmd = (
                    f'git -c http.extraheader="Authorization: Bearer {gh_token}" '
                    f'fetch origin && git -c http.extraheader="Authorization: Bearer {gh_token}" '
                    f"reset --hard origin/{app.branch}"
                )
            self.run(fetch_cmd, cwd=app_dir, mask=[gh_token] if gh_token else None)
        except Exception:
            # Clean any partial checkout and reclone.
            self.run(f"rm -rf {app_dir}")
            self.run(f"mkdir -p {app.destination_path}")
            clone_url = repo_url
            if gh_token:
                clone_url = repo_url.replace("https://", f"https://{gh_token}@")
            self.run(
                f"git clone --branch {app.branch} {clone_url} {app_dir}",
                mask=[gh_token] if gh_token else None,
            )

        # 3. Build
        if app.build_config.install_command:
            self.run(app.build_config.install_command, cwd=app_dir)
        if app.build_config.build_command:
            self.run(app.build_config.build_command, cwd=app_dir)

        # 4. Services
        if app.service_config.static_root:
            self._disable_service_unit(app.name)
            if configure_nginx:
                self._configure_git_static_site(app, app_dir)
            return

        self._configure_systemd(app, app_dir)
        if configure_nginx:
            self._configure_nginx(app)
