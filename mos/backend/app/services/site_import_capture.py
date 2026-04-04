from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureResult:
    """Result of capturing a website."""

    html_snapshot: str
    desktop_screenshot_data_url: str
    mobile_screenshot_data_url: str
    title: str | None
    meta_description: str | None
    capture_metadata: dict[str, Any]


def _extract_hostname(url: str) -> str | None:
    """Extract hostname from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        return None


async def _extract_page_metadata(page) -> dict[str, Any]:
    """Extract metadata from the page."""
    metadata: dict[str, Any] = {}

    try:
        metadata["title"] = await page.title() or ""
    except Exception:
        pass

    try:
        metadata["meta_description"] = (
            await page.evaluate(
                'document.querySelector("meta[name=\\"description\\"]")?.content || ""'
            )
            or ""
        )
    except Exception:
        pass

    try:
        metadata["lang"] = await page.evaluate("document.documentElement.lang || ''")
    except Exception:
        pass

    return metadata


async def _extract_color_palette(page) -> dict[str, str | None]:
    """Extract color palette from computed styles."""
    palette: dict[str, str | None] = {
        "primary": None,
        "secondary": None,
        "surface": None,
        "accent": None,
        "text": None,
        "background": None,
    }

    try:
        # Extract primary color from common selectors
        primary_color = await page.evaluate(
            """
            (() => {
                const selectors = [
                    'header a', '.nav a', '.logo', 'h1', 'h2', 'h3',
                    '[class*="primary"]', '[style*="color"]'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const style = window.getComputedStyle(el);
                        const color = style.color;
                        if (color && color !== 'rgb(0, 0, 0)' && color !== 'rgba(0, 0, 0, 0)') {
                            return color;
                        }
                    }
                }
                return null;
            })()
            """
        )
        if primary_color:
            palette["primary"] = primary_color
    except Exception:
        pass

    try:
        # Extract background color
        bg_color = await page.evaluate(
            """
            (() => {
                const body = document.body;
                const style = window.getComputedStyle(body);
                return style.backgroundColor || null;
            })()
            """
        )
        if bg_color and bg_color != "rgba(0, 0, 0, 0)" and bg_color != "rgb(255, 255, 255)":
            palette["background"] = bg_color
    except Exception:
        pass

    return palette


async def _extract_fonts(page) -> dict[str, str | None]:
    """Extract font families from computed styles."""
    fonts: dict[str, str | None] = {
        "heading": None,
        "body": None,
        "cta": None,
    }

    try:
        heading_font = await page.evaluate(
            """
            (() => {
                const h1 = document.querySelector('h1') || document.querySelector('h2');
                if (h1) {
                    const style = window.getComputedStyle(h1);
                    return style.fontFamily || null;
                }
                return null;
            })()
            """
        )
        if heading_font:
            fonts["heading"] = heading_font
    except Exception:
        pass

    try:
        body_font = await page.evaluate(
            """
            (() => {
                const body = document.body;
                const style = window.getComputedStyle(body);
                return style.fontFamily || null;
            })()
            """
        )
        if body_font:
            fonts["body"] = body_font
    except Exception:
        pass

    return fonts


async def _extract_cta_styles(page) -> dict[str, str | None]:
    """Extract CTA/button styling."""
    cta_styles: dict[str, str | None] = {
        "style": "solid",
        "borderRadius": None,
        "padding": None,
    }

    try:
        button = await page.evaluate(
            """
            (() => {
                const btn = document.querySelector('button') || document.querySelector('[class*="button"]') || document.querySelector('[class*="btn"]') || document.querySelector('a.button') || document.querySelector('a.btn');
                if (btn) {
                    const style = window.getComputedStyle(btn);
                    return {
                        borderRadius: style.borderRadius,
                        padding: style.padding,
                        backgroundColor: style.backgroundColor,
                        color: style.color
                    };
                }
                return null;
            })()
            """
        )
        if button:
            cta_styles["borderRadius"] = button.get("borderRadius")
            cta_styles["padding"] = button.get("padding")
            if (
                button.get("backgroundColor")
                and button.get("backgroundColor") != "rgba(0, 0, 0, 0)"
            ):
                cta_styles["style"] = "solid"
            else:
                cta_styles["style"] = "outline"
    except Exception:
        pass

    return cta_styles


async def _extract_spacing_info(page) -> dict[str, Any]:
    """Extract spacing density information."""
    spacing: dict[str, Any] = {
        "density": "comfortable",
        "scale": [],
    }

    try:
        # Check common spacing patterns
        density_check = await page.evaluate(
            """
            (() => {
                const body = document.body;
                const style = window.getComputedStyle(body);
                const fontSize = parseFloat(style.fontSize) || 16;
                const lineHeight = parseFloat(style.lineHeight) || 24;
                const ratio = lineHeight / fontSize;
                
                if (ratio < 1.3) return "compact";
                if (ratio > 1.8) return "spacious";
                return "comfortable";
            })()
            """
        )
        spacing["density"] = density_check or "comfortable"
    except Exception:
        pass

    return spacing


async def _extract_section_candidates(page) -> list[dict[str, Any]]:
    """
    Extract candidate sections with structured DOM/computed-style metadata.

    Returns a list of section candidates with tag, selector/path-ish identifier,
    text preview, bounding box, and computed-style values.
    """
    section_candidates: list[dict[str, Any]] = []

    try:
        candidates = await page.evaluate(
            """
            (() => {
                const candidates = [];
                
                // Helper to get computed styles for an element
                const getComputedStyles = (el) => {
                    try {
                        const style = window.getComputedStyle(el);
                        return {
                            backgroundColor: style.backgroundColor,
                            color: style.color,
                            fontFamily: style.fontFamily,
                            fontSize: style.fontSize,
                            padding: style.padding,
                            margin: style.margin,
                            display: style.display,
                            position: style.position,
                        };
                    } catch (e) {
                        return {};
                    }
                };

                // Helper to get a path-ish selector
                const getPath = (el) => {
                    const path = [];
                    let current = el;
                    while (current && current !== document.body && current !== document.documentElement) {
                        let selector = current.tagName.toLowerCase();
                        if (current.id) {
                            selector += `#${current.id}`;
                            path.unshift(selector);
                            break;
                        } else if (current.className && typeof current.className === 'string') {
                            const classes = current.className.split(' ').filter(c => c).slice(0, 2);
                            if (classes.length) {
                                selector += '.' + classes.join('.');
                            }
                        }
                        path.unshift(selector);
                        current = current.parentElement;
                        if (path.length > 4) break;
                    }
                    return path.join(' > ');
                };

                // Helper to get text preview
                const getTextPreview = (el) => {
                    const text = el.innerText || '';
                    return text.trim().slice(0, 100);
                };

                // Helper to get bounding box
                const getBoundingBox = (el) => {
                    try {
                        const rect = el.getBoundingClientRect();
                        return {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height,
                            top: rect.top,
                            left: rect.left,
                            right: rect.right,
                            bottom: rect.bottom,
                        };
                    } catch (e) {
                        return null;
                    }
                };

                // Find major structural elements
                const selectors = [
                    'header', 'nav', 'main', 'section', 'article',
                    'div[class*="hero"]', 'div[class*="banner"]',
                    'div[class*="footer"]', 'div[class*="header"]',
                    'div[class*="nav"]', 'div[class*="feature"]',
                    'div[class*="testimonial"]', 'div[class*="faq"]',
                    'div[class*="product"]', 'div[class*="collection"]',
                ];

                const seenPaths = new Set();

                for (const sel of selectors) {
                    const elements = document.querySelectorAll(sel);
                    for (const el of elements) {
                        const path = getPath(el);
                        if (seenPaths.has(path)) continue;
                        seenPaths.add(path);

                        const rect = getBoundingBox(el);
                        if (!rect || rect.width < 50 || rect.height < 30) continue;

                        candidates.push({
                            tag: el.tagName.toLowerCase(),
                            selector: path,
                            textPreview: getTextPreview(el),
                            boundingBox: rect,
                            computedStyles: getComputedStyles(el),
                        });

                        if (candidates.length >= 15) break;
                    }
                    if (candidates.length >= 15) break;
                }

                return candidates;
            })()
            """
        )

        if candidates:
            section_candidates = candidates
    except Exception as e:
        logger.warning(f"Failed to extract section candidates: {e}")

    return section_candidates


# Default capture function - can be monkeypatched in tests
_capture_impl: Any = None


def set_capture_implementation(func: Any) -> None:
    """Set the capture implementation. Used for testing with monkeypatching."""
    global _capture_impl
    _capture_impl = func


def clear_capture_implementation() -> None:
    """Clear the capture implementation."""
    global _capture_impl
    _capture_impl = None


async def capture_site(url: str) -> CaptureResult:
    """
    Capture a website using Playwright.

    This function can be monkeypatched in tests using set_capture_implementation().

    Raises:
        Exception: If critical capture steps (navigation, screenshots) fail.
    """
    if _capture_impl is not None:
        return await _capture_impl(url)

    # Import here to avoid requiring playwright in tests that mock the implementation
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Navigate to the URL - this is a critical step
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                raise RuntimeError(f"Failed to navigate to URL: {url}") from e

            # Get HTML snapshot - critical step
            try:
                html_snapshot = await page.content()
            except Exception as e:
                raise RuntimeError("Failed to capture HTML snapshot") from e

            # Take desktop screenshot - critical step
            try:
                desktop_screenshot_bytes = await page.screenshot(full_page=True, type="png")
                desktop_screenshot_b64 = base64.b64encode(desktop_screenshot_bytes).decode("utf-8")
                desktop_screenshot_data_url = f"data:image/png;base64,{desktop_screenshot_b64}"
            except Exception as e:
                raise RuntimeError("Failed to capture desktop screenshot") from e

            # Take mobile screenshot - critical step
            try:
                await page.set_viewport_size({"width": 375, "height": 812})
                mobile_screenshot_bytes = await page.screenshot(full_page=True, type="png")
                mobile_screenshot_b64 = base64.b64encode(mobile_screenshot_bytes).decode("utf-8")
                mobile_screenshot_data_url = f"data:image/png;base64,{mobile_screenshot_b64}"
            except Exception as e:
                raise RuntimeError("Failed to capture mobile screenshot") from e

            # Extract metadata - non-critical, can continue if these fail
            title = None
            meta_description = None

            try:
                title = await page.title()
            except Exception:
                logger.warning("Failed to extract page title")

            try:
                meta_description = await page.evaluate(
                    'document.querySelector("meta[name=\\"description\\"]")?.content || ""'
                )
            except Exception:
                logger.warning("Failed to extract meta description")

            # Extract additional metadata - non-critical
            page_metadata: dict[str, Any] = {}
            palette: dict[str, str | None] = {}
            fonts: dict[str, str | None] = {}
            cta_styles: dict[str, str | None] = {}
            spacing: dict[str, Any] = {}
            section_candidates: list[dict[str, Any]] = []

            try:
                page_metadata = await _extract_page_metadata(page)
            except Exception:
                logger.warning("Failed to extract page metadata")

            try:
                palette = await _extract_color_palette(page)
            except Exception:
                logger.warning("Failed to extract color palette")

            try:
                fonts = await _extract_fonts(page)
            except Exception:
                logger.warning("Failed to extract fonts")

            try:
                cta_styles = await _extract_cta_styles(page)
            except Exception:
                logger.warning("Failed to extract CTA styles")

            try:
                spacing = await _extract_spacing_info(page)
            except Exception:
                logger.warning("Failed to extract spacing info")

            try:
                section_candidates = await _extract_section_candidates(page)
            except Exception:
                logger.warning("Failed to extract section candidates")

            # Build capture metadata (ensure JSON serializable)
            capture_metadata: dict[str, Any] = {
                "hostname": _extract_hostname(url),
                "page": page_metadata,
                "palette": palette,
                "fonts": fonts,
                "cta": cta_styles,
                "spacing": spacing,
                "sectionCandidates": section_candidates,
            }

            return CaptureResult(
                html_snapshot=html_snapshot,
                desktop_screenshot_data_url=desktop_screenshot_data_url,
                mobile_screenshot_data_url=mobile_screenshot_data_url,
                title=title,
                meta_description=meta_description or None,
                capture_metadata=capture_metadata,
            )

        finally:
            await browser.close()
