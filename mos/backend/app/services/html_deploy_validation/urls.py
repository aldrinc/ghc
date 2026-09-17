from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from uuid import uuid4

from app.services.deploy_errors import DeployError
from app.services.html_deploy_validation.constants import (
    HTML_DEPLOY_BROWSER_RESOURCE_TYPES,
    HTML_DEPLOY_CANDIDATE_RELEASE_ID_RE,
    HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM,
    HTML_DEPLOY_CDN_CACHE_BUST_QUERY_PARAM,
    HTML_DEPLOY_VALIDATION_CACHE_BUST_QUERY_PARAM,
)


def validate_html_deploy_candidate_release_id(release_id: str) -> str:
    normalized = str(release_id or "").strip()
    if not HTML_DEPLOY_CANDIDATE_RELEASE_ID_RE.fullmatch(normalized):
        raise DeployError(
            "HTML deploy candidate release id must be 1-128 characters of letters, "
            "numbers, '.', '_', or '-', and must start with a letter or number."
        )
    return normalized


def append_url_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlsplit(str(url or "").strip())
    query_pairs: list[tuple[str, str]] = []
    if parsed.query:
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
            for value in values:
                query_pairs.append((key, value))
    for key, value in params.items():
        if value is None:
            continue
        query_pairs.append((str(key), str(value)))
    return parsed._replace(query=urlencode(query_pairs)).geturl()


def html_deploy_page_fetch_url(*, page_url: str, candidate_release_id: str) -> str:
    if not candidate_release_id:
        return page_url
    return append_url_query_params(
        page_url,
        {
            HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM: validate_html_deploy_candidate_release_id(
                candidate_release_id
            ),
            HTML_DEPLOY_VALIDATION_CACHE_BUST_QUERY_PARAM: uuid4().hex,
            HTML_DEPLOY_CDN_CACHE_BUST_QUERY_PARAM: uuid4().hex,
        },
    )


def html_deploy_no_trailing_slash_url(raw_url: str) -> str:
    parsed = urlsplit(str(raw_url or "").strip())
    path = parsed.path
    if path and path != "/" and path.endswith("/"):
        return parsed._replace(path=path.rstrip("/")).geturl()
    return parsed.geturl()


def html_deploy_route_asset_prefix_for_page_url(page_url: str) -> str:
    parsed = urlsplit(str(page_url or "").strip())
    route_path = parsed.path.rstrip("/")
    if not route_path:
        return ""
    return f"{route_path}/assets/"


def html_deploy_route_asset_prefixes_for_path_plan(*, path_plan: dict[str, Any]) -> list[str]:
    prefixes: list[str] = ["/assets/", "/_standalone-assets/"]
    for page_key in ("start_page", "sales_page"):
        page = path_plan.get(page_key)
        if not isinstance(page, dict):
            continue
        parsed = urlsplit(str(page.get("url") or "").strip())
        product_slug = next((part for part in parsed.path.split("/") if part), "")
        if product_slug:
            product_prefix = f"/{product_slug}/assets/"
            if product_prefix not in prefixes:
                prefixes.append(product_prefix)
        prefix = html_deploy_route_asset_prefix_for_page_url(str(page.get("url") or ""))
        if prefix and prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


def html_deploy_browser_resource_failure_message(
    *,
    origin: str,
    request_url: str,
    resource_type: str,
    status: int | None = None,
    failure: str = "",
    route_asset_prefixes: list[str],
) -> str:
    normalized_type = str(resource_type or "").strip().lower()
    if normalized_type not in HTML_DEPLOY_BROWSER_RESOURCE_TYPES:
        return ""
    parsed_origin = urlsplit(str(origin or "").strip())
    parsed_url = urlsplit(str(request_url or "").strip())
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.netloc != parsed_origin.netloc
    ):
        return ""

    path = parsed_url.path
    if (
        "/assets/" in path
        and not path.startswith("/public/assets/")
        and not path.startswith("/api/public/assets/")
        and not any(path.startswith(prefix) for prefix in route_asset_prefixes)
    ):
        return f"{request_url} ({normalized_type}: outside route asset prefix)"

    if status is not None and status >= 400:
        return f"{request_url} ({normalized_type}: HTTP {status})"
    if failure:
        return f"{request_url} ({normalized_type}: {failure})"
    return ""


def html_deploy_srcset_urls(raw_srcset: str) -> list[str]:
    urls: list[str] = []
    for raw_candidate in str(raw_srcset or "").split(","):
        candidate = raw_candidate.strip()
        if not candidate:
            continue
        url = candidate.split()[0].strip()
        if url:
            urls.append(url)
    return urls


def html_deploy_is_data_or_empty_url(raw_url: str) -> bool:
    value = str(raw_url or "").strip().lower()
    return not value or value.startswith("data:")


def html_deploy_is_svg_url(raw_url: str) -> bool:
    return urlsplit(str(raw_url or "").strip()).path.lower().endswith(".svg")


def html_deploy_is_raster_image_url(raw_url: str) -> bool:
    return not html_deploy_is_data_or_empty_url(raw_url) and not html_deploy_is_svg_url(raw_url)


def html_deploy_should_validate_resource_url(*, page_url: str, raw_url: str) -> bool:
    normalized = str(raw_url or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if (
        lowered.startswith("data:")
        or lowered.startswith("blob:")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
        or lowered.startswith("javascript:")
        or lowered.startswith("#")
    ):
        return False

    page = urlsplit(page_url)
    resource = urlsplit(urljoin(page_url, normalized))
    if resource.scheme not in {"http", "https"} or not resource.netloc:
        return False
    if resource.netloc == page.netloc:
        return True
    # Shopify-hosted page media should have been localized by html-deploy-v1.
    return "/cdn/shop/files/" in resource.path.lower()
