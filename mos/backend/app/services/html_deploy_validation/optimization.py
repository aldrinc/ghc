from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.services.deploy_errors import DeployError
from app.services.html_deploy_validation.constants import (
    FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML,
)
from app.services.html_deploy_validation.page_parser import (
    HtmlDeployOptimizationParser,
    html_deploy_image_reference_urls,
    html_deploy_resource_reference_urls,
)
from app.services.html_deploy_validation.targets import html_deploy_validation_targets
from app.services.html_deploy_validation.urls import (
    html_deploy_is_data_or_empty_url,
    html_deploy_is_raster_image_url,
    html_deploy_page_fetch_url,
    html_deploy_should_validate_resource_url,
)


def assert_html_deploy_resource_urls_resolve(
    *,
    client: httpx.Client,
    page_url: str,
    parser: HtmlDeployOptimizationParser,
    candidate_release_id: str = "",
) -> int:
    checked = 0
    failures: list[str] = []
    for resource in html_deploy_resource_reference_urls(parser=parser):
        raw_url = str(resource.get("url") or "").strip()
        kind = str(resource.get("kind") or "resource").strip().lower() or "resource"
        if not html_deploy_should_validate_resource_url(page_url=page_url, raw_url=raw_url):
            continue
        asset_url = urljoin(page_url, raw_url)
        if candidate_release_id and urlsplit(asset_url).netloc == urlsplit(page_url).netloc:
            asset_url = html_deploy_page_fetch_url(
                page_url=asset_url,
                candidate_release_id=candidate_release_id,
            )
        try:
            response = client.get(asset_url)
            response.raise_for_status()
            content_type = str(response.headers.get("content-type") or "").split(";", 1)[0]
            if kind == "image" and content_type and not content_type.lower().startswith("image/"):
                raise DeployError(
                    f"expected image/* content-type, got '{content_type or 'unknown'}'"
                )
            checked += 1
        except Exception as exc:
            failures.append(f"{asset_url} ({kind}): {exc}")
    if failures:
        preview = "; ".join(failures[:8])
        extra = "" if len(failures) <= 8 else f"; +{len(failures) - 8} more"
        raise DeployError(
            "HTML deploy optimization validation failed: linked resources or image assets did not resolve "
            f"for '{page_url}'. {preview}{extra}"
        )
    return checked


def assert_html_deploy_image_urls_resolve(
    *,
    client: httpx.Client,
    page_url: str,
    parser: HtmlDeployOptimizationParser,
    candidate_release_id: str = "",
) -> int:
    checked = 0
    failures: list[str] = []
    for raw_url in html_deploy_image_reference_urls(parser=parser):
        if html_deploy_is_data_or_empty_url(raw_url):
            continue
        asset_url = urljoin(page_url, raw_url)
        if candidate_release_id:
            asset_url = html_deploy_page_fetch_url(
                page_url=asset_url,
                candidate_release_id=candidate_release_id,
            )
        try:
            response = client.get(asset_url)
            response.raise_for_status()
            content_type = str(response.headers.get("content-type") or "").split(";", 1)[0]
            if not content_type.lower().startswith("image/"):
                raise DeployError(
                    f"expected image/* content-type, got '{content_type or 'unknown'}'"
                )
            checked += 1
        except Exception as exc:
            failures.append(f"{asset_url}: {exc}")
    if failures:
        preview = "; ".join(failures[:8])
        extra = "" if len(failures) <= 8 else f"; +{len(failures) - 8} more"
        raise DeployError(
            "HTML deploy optimization validation failed: image assets did not resolve "
            f"for '{page_url}'. {preview}{extra}"
        )
    return checked


def assert_html_deploy_optimization_markers(
    *,
    page: dict[str, Any],
    page_url: str,
    html_document: str,
    parser: HtmlDeployOptimizationParser,
    resolved_image_count: int,
) -> dict[str, Any]:
    failures: list[str] = []
    page_stage = str(page.get("stage") or "").strip().lower().replace("-", "_")
    artifact_kind = str(page.get("html_artifact_kind") or "").strip()
    if (
        page_stage in {"sales", "pre_sales", "presales"}
        and not parser.render_optimization_style_count
    ):
        failures.append("missing data-mos-render-optimization critical CSS")
    if re.search(r"https?://cdn\.tailwindcss\.com\b", html_document, flags=re.IGNORECASE):
        failures.append("Tailwind CDN runtime script was not replaced")

    legacy_script_srcs = [
        src
        for src in parser.script_srcs
        if re.search(r"(?:^|[./_-])im8(?:[./_-]|$)|im8health", src, flags=re.IGNORECASE)
    ]
    if legacy_script_srcs:
        failures.append(f"legacy IM8 script URLs remain: {legacy_script_srcs!r}")

    raster_images = [
        image
        for image in parser.images
        if html_deploy_is_raster_image_url(str(image.get("src") or ""))
    ]
    optimized_image_failures: list[str] = []
    lazy_image_count = 0
    high_priority_image_count = 0
    eager_image_count = 0
    responsive_image_count = 0
    for index, image in enumerate(raster_images):
        loading = str(image.get("loading") or "").strip().lower()
        decoding = str(image.get("decoding") or "").strip().lower()
        fetchpriority = str(image.get("fetchpriority") or "").strip().lower()
        srcset = str(image.get("srcset") or "").strip()
        if not loading:
            optimized_image_failures.append(f"img[{index}] missing loading")
        if decoding != "async":
            optimized_image_failures.append(f"img[{index}] missing decoding=async")
        if not fetchpriority:
            optimized_image_failures.append(f"img[{index}] missing fetchpriority")
        if loading == "lazy":
            lazy_image_count += 1
        if loading == "eager":
            eager_image_count += 1
        if fetchpriority == "high":
            high_priority_image_count += 1
        if srcset:
            responsive_image_count += 1
    responsive_image_count += sum(
        1 for source in parser.sources if str(source.get("srcset") or "").strip()
    )

    image_preload_links = [
        link
        for link in parser.links
        if str(link.get("as") or "").strip().lower() == "image"
        and "preload" in str(link.get("rel") or "").strip().lower()
    ]
    font_preload_count = sum(
        1
        for link in parser.links
        if str(link.get("data-mos-font-preload") or "").strip().lower() == "true"
    )
    origin_hint_count = sum(
        1
        for link in parser.links
        if str(link.get("rel") or "").strip().lower() in {"preconnect", "dns-prefetch"}
    )

    if optimized_image_failures:
        failures.append("; ".join(optimized_image_failures[:8]))
    if raster_images:
        if not image_preload_links:
            failures.append("missing LCP image preload")
        if high_priority_image_count < 1:
            failures.append("missing high-priority eager image")
        if len(raster_images) > 1 and lazy_image_count < 1:
            failures.append("missing lazy loading for below-fold images")
        if len(raster_images) > 1 and responsive_image_count < 1:
            failures.append("missing responsive image srcset/source candidates")
    if failures:
        raise DeployError(
            f"HTML deploy optimization validation failed for '{page_url}': " + "; ".join(failures)
        )

    return {
        "url": page_url,
        "pageStage": page_stage or None,
        "artifactKind": artifact_kind or None,
        "resolvedImageReferences": resolved_image_count,
        "rasterImageCount": len(raster_images),
        "responsiveImageCount": responsive_image_count,
        "lazyImageCount": lazy_image_count,
        "eagerImageCount": eager_image_count,
        "highPriorityImageCount": high_priority_image_count,
        "imagePreloadCount": len(image_preload_links),
        "fontPreloadCount": font_preload_count,
        "originHintCount": origin_hint_count,
        "renderOptimizationCss": bool(parser.render_optimization_style_count),
        "tailwindRuntimeRemoved": "cdn.tailwindcss.com" not in html_document.lower(),
        "legacyIm8ScriptsRemoved": not legacy_script_srcs,
    }


def run_html_deploy_optimization_validation_sync(
    *,
    validation_plan: dict[str, Any],
) -> dict[str, Any] | None:
    if validation_plan.get("render_mode") != FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
        return None

    candidate_release_id = str(validation_plan.get("candidate_release_id") or "").strip()
    pages: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for target in html_deploy_validation_targets(validation_plan=validation_plan):
            page = target["page"]
            fetch_url = str(target["url"])
            response = client.get(fetch_url)
            response.raise_for_status()
            html_document = response.text
            parser = HtmlDeployOptimizationParser()
            parser.feed(html_document)
            resolved_resource_count = assert_html_deploy_resource_urls_resolve(
                client=client,
                page_url=fetch_url,
                parser=parser,
                candidate_release_id=candidate_release_id,
            )
            resolved_image_count = assert_html_deploy_image_urls_resolve(
                client=client,
                page_url=fetch_url,
                parser=parser,
                candidate_release_id=candidate_release_id,
            )
            pages.append(
                assert_html_deploy_optimization_markers(
                    page=page,
                    page_url=fetch_url,
                    html_document=html_document,
                    parser=parser,
                    resolved_image_count=resolved_image_count,
                )
            )
            pages[-1]["validationContext"] = target.get("context")
            pages[-1]["resolvedResourceReferences"] = resolved_resource_count

    return {
        "status": "passed",
        "candidateReleaseId": candidate_release_id or None,
        "pages": pages,
    }
