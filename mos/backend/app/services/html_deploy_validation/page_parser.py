from __future__ import annotations

from html.parser import HTMLParser

from app.services.html_deploy_validation.urls import html_deploy_srcset_urls


class HtmlDeployOptimizationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict[str, str]] = []
        self.sources: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.script_srcs: list[str] = []
        self.render_optimization_style_count = 0

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {
            str(name or "").strip().lower(): str(value or "").strip()
            for name, value in attrs
            if str(name or "").strip()
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = str(tag or "").strip().lower()
        attr_lookup = self._attrs(attrs)
        if tag_name == "img":
            self.images.append(attr_lookup)
            return
        if tag_name == "source":
            self.sources.append(attr_lookup)
            return
        if tag_name == "link":
            self.links.append(attr_lookup)
            return
        if tag_name == "script":
            src = str(attr_lookup.get("src") or "").strip()
            if src:
                self.script_srcs.append(src)
            return
        if (
            tag_name == "style"
            and str(attr_lookup.get("data-mos-render-optimization") or "").strip().lower() == "true"
        ):
            self.render_optimization_style_count += 1


def html_deploy_image_reference_urls(*, parser: HtmlDeployOptimizationParser) -> list[str]:
    urls: list[str] = []
    for image in parser.images:
        src = str(image.get("src") or "").strip()
        if src:
            urls.append(src)
        urls.extend(html_deploy_srcset_urls(str(image.get("srcset") or "")))
    for source in parser.sources:
        urls.extend(html_deploy_srcset_urls(str(source.get("srcset") or "")))
    for link in parser.links:
        as_value = str(link.get("as") or "").lower()
        if as_value == "image":
            href = str(link.get("href") or "").strip()
            if href:
                urls.append(href)
            urls.extend(html_deploy_srcset_urls(str(link.get("imagesrcset") or "")))

    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        normalized = str(url or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def html_deploy_resource_reference_urls(
    *, parser: HtmlDeployOptimizationParser
) -> list[dict[str, str]]:
    resources: list[dict[str, str]] = []

    for raw_url in html_deploy_image_reference_urls(parser=parser):
        resources.append({"url": raw_url, "kind": "image"})

    for link in parser.links:
        rel_tokens = {
            token.strip().lower()
            for token in str(link.get("rel") or "").replace(",", " ").split()
            if token.strip()
        }
        as_value = str(link.get("as") or "").strip().lower()
        href = str(link.get("href") or "").strip()
        if not href:
            continue
        kind = ""
        if "stylesheet" in rel_tokens:
            kind = "stylesheet"
        elif "modulepreload" in rel_tokens:
            kind = "script"
        elif "preload" in rel_tokens:
            kind = as_value or "preload"
        elif {"icon", "shortcut", "apple-touch-icon"} & rel_tokens:
            kind = "image"
        elif "manifest" in rel_tokens:
            kind = "manifest"
        if kind:
            resources.append({"url": href, "kind": kind})

    for src in parser.script_srcs:
        resources.append({"url": src, "kind": "script"})

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for resource in resources:
        raw_url = str(resource.get("url") or "").strip()
        kind = str(resource.get("kind") or "resource").strip().lower() or "resource"
        key = (raw_url, kind)
        if not raw_url or key in seen:
            continue
        seen.add(key)
        deduped.append({"url": raw_url, "kind": kind})
    return deduped
