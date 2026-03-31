from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

class SiteImportArchiveError(ValueError):
    """Raised when an uploaded archive cannot be imported into the standard import flow."""


@dataclass(frozen=True)
class ArchiveImportAnalysis:
    title: str | None
    meta_description: str | None
    source_url: str
    input_mode: str
    upstream_request_payload: dict[str, Any]
    upstream_transcript: list[dict[str, Any]]
    upstream_variants: list[dict[str, Any]]
    upstream_metadata: dict[str, Any]
    html_snapshot: str
    capture_metadata: dict[str, Any]
    suggested_template_family: str
    resolved_site_family: str
    resolved_page_type: str
    resolved_template_id: str | None
    theme_candidate: dict[str, Any]
    normalized_sections: list[dict[str, Any]]
    adapted_site: dict[str, Any]
    adapted_pages: list[dict[str, Any]]
    adapted_puck_data: dict[str, Any]


_MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
_IMPORTED_TEMPLATE_FAMILY = "imported-template"
_ALLOWED_PAGE_TYPES = {
    "home": "home",
    "landing": "landing",
    "category": "category",
    "collection": "collection",
    "product": "product_detail",
    "product_detail": "product_detail",
    "pdp": "product_detail",
    "cart": "cart",
    "checkout": "checkout",
    "pre_sell": "pre_sell",
    "pre-sell": "pre_sell",
    "presell": "pre_sell",
    "listicle": "pre_sell",
}
_SECTION_BLACKLIST: set[str] = set()
_SECTION_WINDOW_BEFORE = 1400
_SECTION_WINDOW_AFTER = 2600
_QUOTED_STRING_RE = re.compile(r"""(["'])(.*?)(?<!\\)\1""", re.DOTALL)
_URL_RE = re.compile(r"""https?://[^\s"'`<>()]+""")
_ALLOWED_RUNTIME_IMPORT_SOURCES = {"react", "react-dom", "react-dom/client"}
_SYSTEM_UI_FONT_FALLBACK = (
    'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial, '
    'Apple Color Emoji, Segoe UI Emoji'
)


def analyze_site_import_archive(
    *,
    archive_name: str,
    archive_bytes: bytes,
    page_type_hint: str | None,
    site_family_hint: str | None,
) -> ArchiveImportAnalysis:
    if not archive_name or not archive_name.strip():
        raise SiteImportArchiveError("Archive upload is missing a filename.")
    if not archive_name.lower().endswith(".zip"):
        raise SiteImportArchiveError("Archive import requires a .zip file.")
    if not archive_bytes:
        raise SiteImportArchiveError("Archive file is empty.")
    if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
        raise SiteImportArchiveError(
            f"Archive exceeds {_MAX_ARCHIVE_BYTES // (1024 * 1024)} MB import limit."
        )

    files = _read_archive_text_files(archive_bytes)
    package_json_text = _get_required_file(files, "package.json")
    package_data = _parse_package_json(package_json_text)
    project_name = str(package_data.get("name") or "").strip() or None
    index_html = _get_required_file(files, "index.html")
    app_path = _resolve_first_existing(
        files,
        ["src/App.tsx", "src/App.jsx", "src/App.ts", "src/App.js"],
    )
    if app_path is None:
        raise SiteImportArchiveError("Archive is missing required file: src/App")
    app_source = files[app_path]
    main_path = _resolve_first_existing(
        files,
        ["src/main.tsx", "src/main.jsx", "src/main.ts", "src/main.js"],
        required=False,
    )
    tailwind_path = _resolve_first_existing(
        files,
        ["tailwind.config.js", "tailwind.config.ts"],
        required=False,
    )
    index_css_path = _resolve_first_existing(
        files,
        ["src/index.css", "src/app.css", "src/styles.css"],
        required=False,
    )
    design_system_path = _resolve_first_existing(
        files,
        ["design-system/design-system.html", "design-system.html"],
        required=False,
    )
    if not index_css_path:
        raise SiteImportArchiveError(
            "Archive import requires a stylesheet entry file for fidelity-preserving translation. "
            "Expected one of: src/index.css, src/app.css, src/styles.css."
        )

    extracted_theme_candidate = _extract_theme_candidate(
        tailwind_source=files.get(tailwind_path) if tailwind_path else None,
        index_css_source=files.get(index_css_path) if index_css_path else None,
        design_system_source=files.get(design_system_path) if design_system_path else None,
        design_system_path=design_system_path,
        brand_name=project_name,
    )
    extracted_sections = _extract_normalized_sections(app_source)
    if not extracted_sections:
        raise SiteImportArchiveError(
            "Archive import could not extract any normalized sections from src/App. "
            "Expected data-section-id markers in the React export."
        )
    resolved_family = _resolve_import_template_family(site_family_hint=site_family_hint)
    resolved_page_type = _resolve_page_type(
        page_type_hint=page_type_hint,
        app_source=app_source,
        sections=extracted_sections,
    )

    title = _extract_title(app_source, extracted_sections)
    meta_description = _extract_meta_description(extracted_sections)
    source_url = f"archive://{archive_name.strip()}"
    resolved_template_id = None
    page_title = title or project_name or _humanize_page_type(resolved_page_type)
    brand = extracted_theme_candidate.get("brand")
    if isinstance(brand, dict) and not str(brand.get("name") or "").strip():
        brand["name"] = page_title
    code_bundle = _build_code_bundle(
        files=files,
        ordered_paths=[
            "package.json",
            tailwind_path,
            index_css_path,
            "index.html",
            main_path,
            app_path,
        ],
    )
    compiled_css = _compile_archive_css(
        files=files,
        tailwind_path=tailwind_path,
        index_css_path=index_css_path,
        content_paths=[
            path for path in [app_path, main_path, "index.html"] if isinstance(path, str) and path.strip()
        ],
    )
    head_assets = _build_imported_head_assets(index_html=index_html, compiled_css=compiled_css)
    runtime_source = _build_runtime_source(app_source=app_source)
    adapted_puck_data = _build_imported_template_puck_data(
        title=page_title,
        description=source_url,
        page_type=resolved_page_type,
        theme_candidate=extracted_theme_candidate,
        normalized_sections=extracted_sections,
        runtime_source=runtime_source,
        head_assets=head_assets,
    )
    page_slug = resolved_page_type.replace("_", "-")
    adapted_pages = [
        {
            "page_type": resolved_page_type,
            "name": page_title,
            "slug": page_slug,
            "ordering": 0,
            "puck_data": adapted_puck_data,
            "generated_code": code_bundle,
            "outbound_links": [],
        }
    ]
    adapted_site = {
        "site_family": resolved_family,
        "site_type": _derive_site_type(resolved_page_type),
        "commerce_provider": None,
        "entry_page_type": resolved_page_type,
        "completeness_state": "complete",
    }

    upstream_request_payload = {
        "requestSource": "archive_upload",
        "pipeline": "site_import_synthesis",
        "generatedCodeConfig": "react_tailwind",
        "archiveFileName": archive_name,
        "projectName": project_name,
        "entryFile": app_path,
    }
    upstream_transcript = [
        {
            "type": "status",
            "value": "Received archive upload",
            "variantIndex": 0,
        },
        {
            "type": "status",
            "value": "Parsed React/Tailwind export",
            "variantIndex": 0,
        },
        {
            "type": "setCode",
            "value": code_bundle,
            "variantIndex": 0,
        },
        {
            "type": "status",
            "value": "Loaded trusted screenshot-to-code archive output",
            "variantIndex": 0,
        },
        {
            "type": "variantComplete",
            "variantIndex": 0,
            "data": {
                "source": "archive_upload",
                "family": resolved_family,
                "pageType": resolved_page_type,
                "templateId": resolved_template_id,
            },
        },
    ]
    upstream_variants = [
        {
            "variantIndex": 0,
            "status": "completed",
            "source": "archive_upload",
            "code": code_bundle,
        }
    ]

    capture_metadata = {
        "source": "archive_upload",
        "archiveFileName": archive_name,
        "projectName": project_name,
        "entryFile": app_path,
        "pipeline": "site_import_template_translation",
        "sectionCandidates": [
            {
                "tag": "section",
                "id": section["id"],
                "selector": section["keyStyles"].get("selector"),
                "textPreview": section["keyText"][0] if section["keyText"] else "",
                "boundingBox": None,
                "computedStyles": {},
            }
            for section in extracted_sections
        ],
        "palette": extracted_theme_candidate.get("palette", {}),
        "fonts": extracted_theme_candidate.get("fonts", {}),
        "spacing": extracted_theme_candidate.get("spacing", {}),
        "cta": extracted_theme_candidate.get("cta", {}),
        "screenshotsAvailable": False,
    }

    theme_candidate = extracted_theme_candidate
    normalized_sections = extracted_sections

    upstream_metadata = {
        "generatorSystem": "screenshot-to-code",
        "stack": "react_tailwind",
        "variantCount": 1,
        "archiveFileName": archive_name,
        "projectName": project_name,
        "entryFile": app_path,
        "fileCount": len(files),
        "importMode": "archive",
        "archiveSource": True,
        "reviewOnly": False,
        "runtimeTranslation": "source_runtime_editable",
        "sourceTemplateFamily": _IMPORTED_TEMPLATE_FAMILY,
    }

    return ArchiveImportAnalysis(
        title=title or project_name,
        meta_description=meta_description,
        source_url=source_url,
        input_mode="archive",
        upstream_request_payload=upstream_request_payload,
        upstream_transcript=upstream_transcript,
        upstream_variants=upstream_variants,
        upstream_metadata=upstream_metadata,
        html_snapshot=index_html,
        capture_metadata=capture_metadata,
        suggested_template_family=_IMPORTED_TEMPLATE_FAMILY,
        resolved_site_family=resolved_family,
        resolved_page_type=resolved_page_type,
        resolved_template_id=resolved_template_id,
        theme_candidate=theme_candidate,
        normalized_sections=normalized_sections,
        adapted_site=adapted_site,
        adapted_pages=adapted_pages,
        adapted_puck_data=adapted_puck_data,
    )


def _read_archive_text_files(archive_bytes: bytes) -> dict[str, str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise SiteImportArchiveError("Uploaded file is not a valid zip archive.") from exc

    files: dict[str, str] = {}
    prefix = _resolve_common_prefix(archive.namelist())
    for member in archive.infolist():
        if member.is_dir():
            continue
        normalized_path = _normalize_archive_path(member.filename, prefix=prefix)
        if not normalized_path:
            continue
        try:
            decoded = archive.read(member).decode("utf-8")
        except UnicodeDecodeError:
            continue
        files[normalized_path] = decoded

    return files


def _resolve_common_prefix(names: list[str]) -> str | None:
    visible_names = [
        name
        for name in names
        if name and not name.startswith("__MACOSX/") and not name.endswith("/")
    ]
    if not visible_names:
        return None
    first_parts = {
        PurePosixPath(name).parts[0]
        for name in visible_names
        if PurePosixPath(name).parts
    }
    if len(first_parts) != 1:
        return None
    return next(iter(first_parts))


def _normalize_archive_path(name: str, *, prefix: str | None) -> str | None:
    if not name or name.startswith("__MACOSX/"):
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise SiteImportArchiveError("Archive contains an unsafe file path.")
    parts = list(path.parts)
    if prefix and parts and parts[0] == prefix:
        parts = parts[1:]
    if not parts:
        return None
    return str(PurePosixPath(*parts))


def _get_required_file(files: dict[str, str], path: str) -> str:
    try:
        return files[path]
    except KeyError as exc:
        raise SiteImportArchiveError(f"Archive is missing required file: {path}") from exc


def _resolve_first_existing(
    files: dict[str, str],
    paths: list[str],
    *,
    required: bool = True,
) -> str | None:
    for path in paths:
        if path in files:
            return path
    if required:
        raise SiteImportArchiveError(
            f"Archive is missing required file. Expected one of: {', '.join(paths)}"
        )
    return None


def _parse_package_json(package_json_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(package_json_text)
    except json.JSONDecodeError as exc:
        raise SiteImportArchiveError("Archive package.json is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise SiteImportArchiveError("Archive package.json must be a JSON object.")
    return payload


def _resolve_import_template_family(*, site_family_hint: str | None) -> str:
    if site_family_hint and site_family_hint.strip().lower() != _IMPORTED_TEMPLATE_FAMILY:
        raise SiteImportArchiveError(
            "Archive imports no longer accept legacy site family hints. "
            "Leave the family hint empty or use 'imported-template'."
        )
    return _IMPORTED_TEMPLATE_FAMILY


def _resolve_page_type(
    *,
    page_type_hint: str | None,
    app_source: str,
    sections: list[dict[str, Any]],
) -> str:
    resolved_page_type = (
        _ALLOWED_PAGE_TYPES.get(page_type_hint.strip().lower())
        if page_type_hint and page_type_hint.strip()
        else None
    )
    if page_type_hint and not resolved_page_type:
        raise SiteImportArchiveError(
            "Archive imports support only these page type hints: "
            + ", ".join(sorted(_ALLOWED_PAGE_TYPES))
            + "."
        )
    if resolved_page_type:
        return resolved_page_type

    lowered = app_source.lower()
    section_types = {str(section.get("sectionType") or "") for section in sections}

    if {"bundle_selector", "sticky_offer_rail"} & section_types or "add to cart" in lowered:
        return "product_detail"
    if any(marker in lowered for marker in ("checkout", "order confirmed", "payment method")):
        return "checkout"
    if any(marker in lowered for marker in ("cart summary", "shopping cart", "your cart")):
        return "cart"
    if "collection" in lowered or "category" in lowered:
        return "category"
    if any(marker in lowered for marker in ("advertorial", "pre-sell", "presell", "listicle")):
        return "pre_sell"
    return "landing"


def _extract_theme_candidate(
    *,
    tailwind_source: str | None,
    index_css_source: str | None,
    design_system_source: str | None,
    design_system_path: str | None,
    brand_name: str | None,
) -> dict[str, Any]:
    source = "\n".join(part for part in (tailwind_source, index_css_source, design_system_source) if part)
    design_system_doc = _extract_design_system_document(source=design_system_source, path=design_system_path)
    design_palette = design_system_doc.get("palette") if isinstance(design_system_doc, dict) else {}
    extracted_palette = {
        "primary": _search(source, r"primary\s*:\s*\{[^}]*DEFAULT:\s*'([^']+)'"),
        "secondary": _search(source, r"primary\s*:\s*\{[^}]*dark:\s*'([^']+)'"),
        "surface": _search(source, r"bg\s*:\s*\{[^}]*card:\s*'([^']+)'"),
        "accent": _search(source, r"sale\s*:\s*\{[^}]*red:\s*'([^']+)'"),
        "text": _search(source, r"text\s*:\s*\{[^}]*dark:\s*'([^']+)'"),
        "background": _search(source, r"bg\s*:\s*\{[^}]*light:\s*'([^']+)'"),
    }
    palette = {
        role: _first_non_empty(
            design_palette.get(role) if isinstance(design_palette, dict) else None,
            extracted_palette.get(role),
        )
        for role in ("primary", "secondary", "surface", "accent", "text", "background")
    }

    extracted_primary_font = _search(source, r"sans\s*:\s*\[\s*'([^']+)'")
    design_fonts = design_system_doc.get("fonts") if isinstance(design_system_doc, dict) else {}
    primary_font = _first_non_empty(
        design_fonts.get("primary") if isinstance(design_fonts, dict) else None,
        extracted_primary_font,
    )
    fonts = {
        "primary": primary_font,
        "heading": _first_non_empty(
            design_fonts.get("heading") if isinstance(design_fonts, dict) else None,
            primary_font,
        ),
        "body": _first_non_empty(
            design_fonts.get("body") if isinstance(design_fonts, dict) else None,
            primary_font,
        ),
        "cta": _first_non_empty(
            design_fonts.get("cta") if isinstance(design_fonts, dict) else None,
            primary_font,
        ),
    }
    border_radius = _first_non_empty(
        design_system_doc.get("ctaBorderRadius") if isinstance(design_system_doc, dict) else None,
        _search(source, r"pill'\s*:\s*'([^']+)'"),
    )
    font_urls = design_system_doc.get("fontUrls") if isinstance(design_system_doc, dict) else []
    font_css = design_system_doc.get("fontCss") if isinstance(design_system_doc, dict) else None
    data_theme = _first_non_empty(
        design_system_doc.get("dataTheme") if isinstance(design_system_doc, dict) else None,
        "light",
    )

    base_tokens = deepcopy(_load_base_design_system_tokens_template())
    css_vars = deepcopy(base_tokens.get("cssVars", {})) if isinstance(base_tokens.get("cssVars"), dict) else {}

    background = _first_non_empty(palette.get("background"), palette.get("surface"), css_vars.get("--color-page-bg"))
    surface = _first_non_empty(palette.get("surface"), background, css_vars.get("--hero-bg"))
    brand_color = _first_non_empty(palette.get("secondary"), palette.get("primary"), css_vars.get("--color-brand"))
    body_text = _first_non_empty(palette.get("text"), brand_color, css_vars.get("--color-text"))
    cta_color = _first_non_empty(palette.get("primary"), brand_color, css_vars.get("--color-cta"))
    cta_text = _choose_text_color(cta_color) if isinstance(cta_color, str) and cta_color.strip() else css_vars.get("--color-cta-text")

    heading_font_stack = _build_font_stack(fonts.get("heading"))
    body_font_stack = _build_font_stack(fonts.get("body"))
    cta_font_stack = _build_font_stack(fonts.get("cta"))
    if body_font_stack:
        css_vars["--font-sans"] = body_font_stack
    if heading_font_stack:
        css_vars["--font-heading"] = heading_font_stack
    if cta_font_stack:
        css_vars["--font-cta"] = cta_font_stack

    if isinstance(brand_color, str) and brand_color.strip():
        css_vars["--color-brand"] = brand_color
        css_vars["--pdp-brand-strong"] = brand_color
        brand_rgb = _parse_simple_rgb(brand_color)
        if brand_rgb is not None:
            css_vars["--color-border"] = _rgba_string(brand_rgb, 0.18)
            css_vars["--focus-outline-color"] = _rgba_string(brand_rgb, 0.35)
            css_vars["--focus-outline-color-soft"] = _rgba_string(brand_rgb, 0.25)
            css_vars["--pdp-brand-05"] = _rgba_string(brand_rgb, 0.05)
            css_vars["--pdp-brand-08"] = _rgba_string(brand_rgb, 0.08)
            css_vars["--pdp-brand-12"] = _rgba_string(brand_rgb, 0.12)
    if isinstance(body_text, str) and body_text.strip():
        css_vars["--color-text"] = body_text
        text_rgb = _parse_simple_rgb(body_text)
        if text_rgb is not None:
            css_vars["--color-muted"] = _rgba_string(text_rgb, 0.76)
    if isinstance(background, str) and background.strip():
        css_vars["--color-bg"] = background
        css_vars["--color-page-bg"] = background
    if isinstance(surface, str) and surface.strip():
        css_vars["--color-page-bg-secondary"] = surface
        css_vars["--hero-bg"] = surface
        css_vars["--pitch-bg"] = surface
        css_vars["--color-soft"] = surface
    if isinstance(cta_color, str) and cta_color.strip():
        css_vars["--color-cta"] = cta_color
        css_vars["--pdp-cta-bg"] = cta_color
    if isinstance(cta_text, str) and cta_text.strip():
        css_vars["--color-cta-text"] = cta_text
    if isinstance(brand_color, str) and brand_color.strip():
        css_vars["--color-cta-icon"] = brand_color
    if isinstance(border_radius, str) and border_radius.strip():
        css_vars["--radius-full"] = border_radius.strip()
        css_vars["--pdp-radius-pill"] = border_radius.strip()

    candidate = {
        "dataTheme": data_theme or "light",
        "fontUrls": font_urls if isinstance(font_urls, list) else [],
        "cssVars": css_vars,
        "funnelDefaults": deepcopy(base_tokens.get("funnelDefaults", {})),
        "brand": {
            "name": _first_non_empty(
                brand_name,
                design_system_doc.get("title") if isinstance(design_system_doc, dict) else None,
                "Imported Brand",
            ),
        },
        "palette": palette,
        "fonts": {role: fonts.get(role) for role in ("primary", "heading", "body", "cta")},
        "spacing": {"density": "comfortable", "scale": []},
        "cta": {
            "style": "solid",
            "borderRadius": border_radius,
            "padding": None,
        },
        "diagnostics": {
            "sourceInputs": {
                "hasTailwindSource": bool(tailwind_source and tailwind_source.strip()),
                "hasIndexCssSource": bool(index_css_source and index_css_source.strip()),
                "designSystemHtmlPath": design_system_path,
            },
            "fidelity": {
                "fontDelivery": "document_supplied" if font_urls or font_css else "family_name_only",
                "backgroundStrategy": "page and section surfaces derive from background and surface roles; accent is excluded from hero and pitch backgrounds",
            },
            "promotionReadiness": {
                "ready": False,
                "missingFields": ["brand.logoAssetPublicId"],
                "notes": [
                    "Candidate matches design-system token shape closely but still requires a real logo asset before promotion into a runtime design system.",
                ],
            },
        },
    }
    if isinstance(font_css, str) and font_css.strip():
        candidate["fontCss"] = font_css.strip()
    return candidate


def _build_font_stack(font_name: str | None) -> str | None:
    if not isinstance(font_name, str) or not font_name.strip():
        return None
    cleaned = _normalize_font_name(font_name)
    quoted = f'"{cleaned}"' if " " in cleaned else cleaned
    return f"{quoted}, {_SYSTEM_UI_FONT_FALLBACK}"


def _normalize_font_name(value: str) -> str:
    cleaned = value.strip().strip("\"'")
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[0].strip().strip("\"'")
    return cleaned


def _choose_text_color(color: str) -> str:
    rgb = _parse_simple_rgb(color)
    if rgb is None:
        return "#ffffff"
    brightness = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000
    return "#061a70" if brightness >= 175 else "#ffffff"


def _rgba_string(rgb: tuple[int, int, int], alpha: float) -> str:
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha:.2f})"


def _parse_simple_rgb(value: str) -> tuple[int, int, int] | None:
    raw = value.strip().lower()
    hex_match = re.fullmatch(r"#([0-9a-f]{6})", raw)
    if hex_match:
        body = hex_match.group(1)
        return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)
    short_hex_match = re.fullmatch(r"#([0-9a-f]{3})", raw)
    if short_hex_match:
        body = short_hex_match.group(1)
        return int(body[0] * 2, 16), int(body[1] * 2, 16), int(body[2] * 2, 16)
    rgb_match = re.fullmatch(r"rgba?\(([^)]+)\)", raw)
    if rgb_match:
        parts = [part.strip() for part in rgb_match.group(1).split(",")]
        if len(parts) >= 3:
            try:
                r = max(0, min(255, int(round(float(parts[0])))))
                g = max(0, min(255, int(round(float(parts[1])))))
                b = max(0, min(255, int(round(float(parts[2])))))
                return r, g, b
            except ValueError:
                return None
    if raw == "white":
        return 255, 255, 255
    if raw == "black":
        return 0, 0, 0
    return None


class _DesignSystemDocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.stylesheet_hrefs: list[str] = []
        self.inline_styles: list[str] = []
        self._capture_title = False
        self._capture_style = False
        self._title_chunks: list[str] = []
        self._style_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "title":
            self._capture_title = True
            self._title_chunks = []
            return
        if tag == "style":
            self._capture_style = True
            self._style_chunks = []
            return
        if tag != "link":
            return
        rel = attributes.get("rel", "").lower()
        href = attributes.get("href", "").strip()
        if "stylesheet" in rel and _is_external_asset_url(href):
            self.stylesheet_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._capture_title:
            title = "".join(self._title_chunks).strip()
            if title:
                self.title = title
            self._capture_title = False
            self._title_chunks = []
        if tag == "style" and self._capture_style:
            style = "".join(self._style_chunks).strip()
            if style:
                self.inline_styles.append(style)
            self._capture_style = False
            self._style_chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_chunks.append(data)
        if self._capture_style:
            self._style_chunks.append(data)


def _extract_design_system_document(*, source: str | None, path: str | None) -> dict[str, Any]:
    if not isinstance(source, str) or not source.strip():
        return {}

    parser = _DesignSystemDocumentParser()
    parser.feed(source)
    css_source = "\n".join(parser.inline_styles)
    css_vars = {
        key.strip().lower(): value.strip()
        for key, value in re.findall(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;}{]+);", css_source)
        if key.strip() and value.strip()
    }
    font_urls = _ordered_unique(
        parser.stylesheet_hrefs
        + [
            match.strip().strip("\"'")
            for match in re.findall(r"@import\s+url\(([^)]+)\)", css_source, re.IGNORECASE)
            if _is_external_asset_url(match.strip().strip("\"'"))
        ]
    )
    font_css_blocks = re.findall(r"@font-face\s*\{[^{}]*\}", css_source, re.IGNORECASE | re.DOTALL)
    font_css_imports = [
        match.strip()
        for match in re.findall(r"@import\s+[^;]+;", css_source, re.IGNORECASE)
        if "font" in match.lower()
    ]
    font_css = "\n\n".join([*font_css_imports, *font_css_blocks]).strip() or None
    data_theme = "dark" if re.search(r"data-theme\s*=\s*[\"']dark[\"']", source, re.IGNORECASE) else "light"
    palette = {
        "primary": _resolve_design_system_value(css_vars, [r"--(?:color-)?primary$", r"--brand$", r"--cta$"]),
        "secondary": _resolve_design_system_value(css_vars, [r"--(?:color-)?secondary$", r"--primary-dark$", r"--brand-dark$", r"--navy$"]),
        "surface": _resolve_design_system_value(css_vars, [r"--(?:color-)?surface$", r"--card$", r"--panel$"]),
        "accent": _resolve_design_system_value(css_vars, [r"--(?:color-)?accent$", r"--sale$", r"--danger$", r"--highlight$", r"--red$"]),
        "text": _resolve_design_system_value(css_vars, [r"--(?:color-)?text$", r"--foreground$", r"--ink$", r"--copy$"]),
        "background": _resolve_design_system_value(css_vars, [r"--(?:color-)?background$", r"--page-bg$", r"--canvas$", r"--light$"]),
    }
    fonts = {
        "primary": _extract_primary_font_name(
            _resolve_design_system_value(css_vars, [r"--font-primary$", r"--font-sans$", r"--font-family$"])
            or _search(css_source, r"font-family\s*:\s*([^;}{]+)")
        ),
        "heading": _extract_primary_font_name(_resolve_design_system_value(css_vars, [r"--font-heading$", r"--heading-font$"])),
        "body": _extract_primary_font_name(_resolve_design_system_value(css_vars, [r"--font-body$", r"--body-font$", r"--font-copy$"])),
        "cta": _extract_primary_font_name(_resolve_design_system_value(css_vars, [r"--font-cta$", r"--button-font$"])),
    }
    cta_border_radius = _first_non_empty(
        _resolve_design_system_value(css_vars, [r"--button-radius$", r"--cta-radius$", r"--pill$", r"--radius-full$"]),
        _search(css_source, r"button[^\{]*\{[^}]*border-radius\s*:\s*([^;}{]+)"),
    )
    return {
        "path": path,
        "title": parser.title,
        "dataTheme": data_theme,
        "palette": palette,
        "fonts": fonts,
        "ctaBorderRadius": cta_border_radius,
        "fontUrls": font_urls,
        "fontCss": font_css,
    }


def _resolve_design_system_value(css_vars: dict[str, str], patterns: list[str]) -> str | None:
    for pattern in patterns:
        matcher = re.compile(pattern, re.IGNORECASE)
        for key, value in css_vars.items():
            if matcher.search(key) and isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_primary_font_name(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    for candidate in [part.strip().strip("\"'") for part in value.split(",")]:
        if not candidate:
            continue
        if candidate.lower() in {"sans-serif", "serif", "monospace", "system-ui", "ui-sans-serif"}:
            continue
        return candidate
    return None


def _extract_normalized_sections(app_source: str) -> list[dict[str, Any]]:
    section_ids = _ordered_unique(re.findall(r'data-section-id="([^"]+)"', app_source))
    sections: list[dict[str, Any]] = []

    for section_id in section_ids:
        if section_id in _SECTION_BLACKLIST:
            continue
        anchor = f'data-section-id="{section_id}"'
        index = app_source.find(anchor)
        if index < 0:
            continue
        component_name, snippet = _extract_section_source(app_source, index)
        section_type, confidence = _classify_section(section_id=section_id, snippet=snippet)
        key_text = _extract_text_candidates(snippet)[:12]
        key_media = _ordered_unique(_URL_RE.findall(snippet))[:6]
        parsed_data = _extract_section_structured_data(section_id=section_id, snippet=snippet)
        display_name = _resolve_section_display_name(
            section_id=section_id,
            section_type=section_type,
            component_name=component_name,
            key_text=key_text,
            parsed_data=parsed_data,
        )
        section_key = _slugify_token(component_name or display_name or section_id)
        semantic_tags = _build_section_semantic_tags(
            section_id=section_id,
            section_type=section_type,
            parsed_data=parsed_data,
        )
        sections.append(
            {
                "id": section_id,
                "displayName": display_name,
                "sectionKey": section_key,
                "componentName": component_name,
                "semanticTags": semantic_tags,
                "sectionType": section_type,
                "confidence": confidence,
                "keyText": key_text,
                "keyMedia": key_media,
                "parsedData": parsed_data,
                "keyStyles": {
                    "selector": f'[data-section-id="{section_id}"]',
                    "source": "archive_upload",
                },
                "boundingBox": None,
            }
        )

    return _reorder_sections_by_app_render_order(app_source=app_source, sections=sections)


def _extract_named_component_source(app_source: str, component_name: str) -> str | None:
    if not component_name:
        return None

    for pattern, delimiter in (
        (
            re.compile(
                rf"(?m)(?:const\s+{re.escape(component_name)}\s*=\s*\([^)]*\)\s*=>\s*\{{|function\s+{re.escape(component_name)}\s*\([^)]*\)\s*\{{)"
            ),
            ("{", "}"),
        ),
        (
            re.compile(
                rf"(?m)const\s+{re.escape(component_name)}\s*=\s*\([^)]*\)\s*=>\s*\("
            ),
            ("(", ")"),
        ),
    ):
        match = pattern.search(app_source)
        if not match:
            continue
        open_index = match.end() - 1
        close_index = _find_matching_delimiter(
            app_source,
            open_index,
            open_char=delimiter[0],
            close_char=delimiter[1],
        )
        if close_index is None:
            return None
        return app_source[match.start() : close_index + 1]

    return None


def _reorder_sections_by_app_render_order(
    *, app_source: str, sections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(sections) <= 1:
        return sections

    app_component_source = _extract_named_component_source(app_source, "App")
    if not app_component_source:
        return sections

    placements: list[tuple[int, int]] = []
    unmatched_indices: list[int] = []

    for index, section in enumerate(sections):
        component_name = str(section.get("componentName") or "").strip()
        section_id = str(section.get("id") or "").strip()
        match_start: int | None = None

        if component_name and component_name != "App":
            component_pattern = re.compile(rf"<{re.escape(component_name)}(?:\s|/|>)")
            component_match = component_pattern.search(app_component_source)
            if component_match:
                match_start = component_match.start()
        elif section_id:
            section_pattern = re.compile(rf'data-section-id="{re.escape(section_id)}"')
            section_match = section_pattern.search(app_component_source)
            if section_match:
                match_start = section_match.start()

        if match_start is None:
            unmatched_indices.append(index)
        else:
            placements.append((match_start, index))

    if not placements:
        return sections

    ordered_indices = [index for _, index in sorted(placements, key=lambda item: item[0])]
    ordered_indices.extend(unmatched_indices)
    return [sections[index] for index in ordered_indices]


_ARROW_COMPONENT_START_RE = re.compile(
    r"(?m)const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\([^)]*\)\s*=>\s*\{"
)
_CONCISE_ARROW_COMPONENT_START_RE = re.compile(
    r"(?m)const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\([^)]*\)\s*=>\s*\("
)
_FUNCTION_COMPONENT_START_RE = re.compile(
    r"(?m)function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{"
)


def _extract_section_source(app_source: str, anchor_index: int) -> tuple[str | None, str]:
    component_name, snippet = _extract_component_source(app_source, anchor_index)
    if snippet:
        return component_name, snippet
    fallback = app_source[
        max(0, anchor_index - _SECTION_WINDOW_BEFORE) : min(
            len(app_source), anchor_index + _SECTION_WINDOW_AFTER
        )
    ]
    return component_name, fallback


def _extract_component_source(app_source: str, anchor_index: int) -> tuple[str | None, str | None]:
    candidate_matches = [
        *list(_ARROW_COMPONENT_START_RE.finditer(app_source[: anchor_index + 1])),
        *list(_CONCISE_ARROW_COMPONENT_START_RE.finditer(app_source[: anchor_index + 1])),
        *list(_FUNCTION_COMPONENT_START_RE.finditer(app_source[: anchor_index + 1])),
    ]
    if not candidate_matches:
        return None, None

    match = max(candidate_matches, key=lambda candidate: candidate.start())
    component_name = next(
        (
            group
            for group_index in range(1, (match.lastindex or 0) + 1)
            if isinstance((group := match.group(group_index)), str) and group
        ),
        None,
    )
    open_char = app_source[match.end() - 1]
    if open_char == "{":
        close_index = _find_matching_delimiter(app_source, match.end() - 1, open_char="{", close_char="}")
    elif open_char == "(":
        close_index = _find_matching_delimiter(app_source, match.end() - 1, open_char="(", close_char=")")
    else:
        return component_name, None
    if close_index is None:
        return component_name, None
    return component_name, app_source[match.start() : close_index + 1]


def _find_matching_brace(source: str, open_brace_index: int) -> int | None:
    return _find_matching_delimiter(source, open_brace_index, open_char="{", close_char="}")


def _find_matching_delimiter(
    source: str, open_index: int, *, open_char: str, close_char: str
) -> int | None:
    depth = 0
    in_string: str | None = None
    escaped = False
    for index in range(open_index, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == in_string:
                in_string = None
            continue
        if char in {'"', "'", "`"}:
            in_string = char
            continue
        if char == open_char:
            depth += 1
            continue
        if char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return None


def _classify_section(*, section_id: str, snippet: str) -> tuple[str, float]:
    lowered_id = section_id.lower()
    lowered_snippet = snippet.lower()

    if "footer" in lowered_id:
        return "footer", 0.98
    if "question" in lowered_id or "faq" in lowered_id:
        return "faq", 0.98
    if "vs" in lowered_id or "comparison" in lowered_id or "why choose" in lowered_snippet:
        return "comparison_table", 0.94
    if any(token in lowered_id for token in ("review", "testimonial")) or "real people" in lowered_snippet:
        return "testimonial_wall", 0.93
    if "purchase" in lowered_id or "add to cart" in lowered_snippet or "choose flavor" in lowered_snippet:
        return "bundle_selector", 0.95
    if "hero" in lowered_id:
        return "hero", 0.99
    if "marquee" in lowered_id:
        return "proof_bar", 0.95
    if any(
        token in lowered_snippet
        for token in ("backed by", "studies", "evidence", "3rd party tested", "lab results")
    ):
        return "proof_bar", 0.78
    if any(
        token in lowered_snippet
        for token in (
            "optimize",
            "routine",
            "mental clarity",
            "quality",
            "community",
            "expert designed",
        )
    ):
        return "feature_stack", 0.72
    return "generic_content", 0.6


def _extract_text_candidates(snippet: str) -> list[str]:
    results: list[str] = []
    results.extend(_extract_heading_candidates(snippet))
    results.extend(_extract_paragraphs(snippet))
    results.extend(_extract_button_labels(snippet))
    results.extend(_extract_inline_text_nodes(snippet))
    for _, candidate in _QUOTED_STRING_RE.findall(snippet):
        normalized = " ".join(candidate.strip().split())
        if _looks_like_human_text(normalized):
            results.append(normalized)
    return _ordered_unique(results)


def _extract_heading_candidates(snippet: str) -> list[str]:
    results: list[str] = []
    for level in ("h1", "h2", "h3"):
        matches = re.findall(rf"<{level}[^>]*>(.*?)</{level}>", snippet, re.DOTALL)
        for match in matches:
            normalized = _normalize_markup_text(match)
            if _looks_like_human_text(normalized):
                results.append(normalized)
    return results


def _extract_paragraphs(snippet: str) -> list[str]:
    results: list[str] = []
    for match in re.findall(r"<p[^>]*>(.*?)</p>", snippet, re.DOTALL):
        normalized = _normalize_markup_text(match)
        if _looks_like_human_text(normalized):
            results.append(normalized)
    return results


def _extract_inline_text_nodes(snippet: str) -> list[str]:
    results: list[str] = []
    for match in re.findall(r">([^<>{][^<>]{0,180})<", snippet):
        normalized = _normalize_markup_text(match)
        if _looks_like_human_text(normalized):
            results.append(normalized)
    return results


def _extract_button_labels(snippet: str) -> list[str]:
    return [button["label"] for button in _extract_buttons(snippet)]


def _extract_buttons(snippet: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for tag_name, attrs, inner_html in re.findall(
        r"<(button|a)([^>]*)>(.*?)</(?:button|a)>",
        snippet,
        re.DOTALL,
    ):
        label = _normalize_markup_text(inner_html)
        if not _looks_like_human_text(label):
            continue
        href_match = re.search(r'href="([^"]+)"', attrs)
        href = href_match.group(1).strip() if href_match else ""
        results.append({"label": label, "href": href, "tag": tag_name})
    unique_results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        key = (result["label"], result["href"])
        if key in seen:
            continue
        seen.add(key)
        unique_results.append(result)
    return unique_results


def _normalize_markup_text(value: str) -> str:
    if not value:
        return ""
    stripped = re.sub(r"\{/\*.*?\*/\}", " ", value, flags=re.DOTALL)
    stripped = re.sub(r"<br\s*/?>", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = stripped.replace("&copy;", " ")
    stripped = stripped.replace("{new Date().getFullYear()}", "")
    stripped = re.sub(r"\{[^{}]*\}", " ", stripped)
    return " ".join(stripped.strip().split())


def _extract_section_structured_data(*, section_id: str, snippet: str) -> dict[str, Any]:
    title = _first_non_empty(_extract_heading_candidates(snippet))
    paragraphs = _extract_paragraphs(snippet)
    buttons = _extract_buttons(snippet)
    media = _ordered_unique(_URL_RE.findall(snippet))
    data: dict[str, Any] = {}

    if title:
        data["title"] = title
    if paragraphs:
        data["body"] = paragraphs[0]
        data["paragraphs"] = paragraphs
    if buttons:
        data["buttons"] = [button["label"] for button in buttons]
        data["buttonActions"] = buttons
    if media:
        data["media"] = media[:8]

    array_payloads = _extract_js_arrays(snippet)
    for variable_name, payload in array_payloads.items():
        for key, value in _classify_array_payload(variable_name=variable_name, payload=payload).items():
            if not value:
                continue
            if isinstance(value, list):
                existing = list(data.get(key, []) or [])
                for item in value:
                    if item not in existing:
                        existing.append(item)
                data[key] = existing
            else:
                data[key] = value

    badge_candidates = _extract_badge_candidates(
        snippet,
        excluded_texts={
            *(data.get("buttons") or []),
            *(data.get("paragraphs") or []),
            *(data.get("title") and [data["title"]] or []),
        },
    )
    if badge_candidates:
        data["badges"] = badge_candidates

    links = [
        {
            "label": _normalize_markup_text(label),
            "href": href,
        }
        for href, label in re.findall(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', snippet, re.DOTALL)
        if _normalize_markup_text(label)
    ]
    if links:
        data["links"] = links

    if "galleryImages" not in data and media:
        if "purchase" in section_id or "gallery" in section_id or "shop" in section_id:
            data["galleryImages"] = media[:6]

    if "tiers" in data and "flavorOptions" not in data:
        flavor_options = [
            button["label"]
            for button in buttons
            if button["label"].strip().lower() not in {"shop omni now", "try omni now", "shop now"}
        ]
        if flavor_options:
            data["flavorOptions"] = flavor_options[:4]

    return data


def _extract_js_arrays(snippet: str) -> dict[str, list[Any]]:
    arrays: dict[str, list[Any]] = {}
    for match in re.finditer(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\[", snippet):
        variable_name = match.group(1)
        ignored_keys = {"icon"} if any(
            token in variable_name.lower() for token in ("feature", "marquee", "item")
        ) else set()
        payload = _parse_js_array(snippet, variable_name, ignored_keys=ignored_keys)
        if payload:
            arrays[variable_name] = payload
    return arrays


def _classify_array_payload(*, variable_name: str, payload: list[Any]) -> dict[str, Any]:
    if not payload:
        return {}

    lowered_name = variable_name.lower()
    if all(isinstance(item, str) for item in payload):
        values = [str(item).strip() for item in payload if str(item).strip()]
        if not values:
            return {}
        if all(value.startswith(("http://", "https://")) for value in values):
            return {"galleryImages": values[:8]}
        if "check" in lowered_name:
            return {"checklist": values}
        if any(token in lowered_name for token in ("marquee", "badge", "pill")):
            return {"badges": values}
        return {"strings": values}

    objects = [item for item in payload if isinstance(item, dict)]
    if not objects:
        return {}

    keys = {str(key) for item in objects for key in item.keys()}
    if {"question", "answer"} <= keys:
        return {"faqs": objects}
    if "feature" in keys and any(
        key in keys for key in ("omni", "powder", "other", "competitor", "gummies")
    ):
        return {"comparisons": objects}
    if any(key in keys for key in ("price", "regularPrice", "savings", "total")):
        return {"tiers": objects}
    if any(key in keys for key in ("image", "review", "quote", "name")) and any(
        key in keys for key in ("review", "quote", "name")
    ):
        return {"testimonials": objects}
    if any(key in keys for key in ("percent", "value", "omni", "placebo")):
        return {"stats": objects}
    if "text" in keys and any(token in lowered_name for token in ("marquee", "badge", "item")):
        badges = [
            str(item.get("text", "")).strip()
            for item in objects
            if isinstance(item.get("text"), str) and str(item.get("text")).strip()
        ]
        return {"badges": badges}
    if {"title", "description"} <= keys or "features" in lowered_name:
        return {"features": objects}
    return {"items": objects}


def _extract_badge_candidates(snippet: str, *, excluded_texts: set[str]) -> list[str]:
    candidates = [
        candidate
        for candidate in _extract_inline_text_nodes(snippet)
        if candidate not in excluded_texts
        and len(candidate.split()) <= 5
        and candidate.upper() == candidate
        and _looks_like_human_text(candidate)
    ]
    return _ordered_unique(candidates)[:8]


def _parse_js_string_array(snippet: str, variable_name: str) -> list[str]:
    payload = _parse_js_array(snippet, variable_name)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, str) and item.strip()]


def _parse_js_object_array(
    snippet: str,
    variable_name: str,
    *,
    ignored_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    payload = _parse_js_array(snippet, variable_name, ignored_keys=ignored_keys)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _parse_js_array(
    snippet: str,
    variable_name: str,
    *,
    ignored_keys: set[str] | None = None,
) -> list[Any]:
    match = re.search(
        rf"const\s+{re.escape(variable_name)}\s*=\s*\[(.*?)\]\s*;",
        snippet,
        re.DOTALL,
    )
    if not match:
        return []

    raw = match.group(1)
    ignored_keys = ignored_keys or set()
    for key in ignored_keys:
        raw = re.sub(
            rf"{re.escape(key)}\s*:\s*[A-Za-z_][A-Za-z0-9_]*\s*(?=[,}}])",
            f"{key}: null",
            raw,
        )

    raw = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', raw)
    raw = re.sub(
        r':\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=[,}])',
        lambda m: f': {m.group(1)}'
        if m.group(1) in {"true", "false", "null"}
        else ': null',
        raw,
    )
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        payload = json.loads(f"[{raw}]")
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _looks_like_human_text(value: str) -> bool:
    if len(value) < 4 or len(value) > 180:
        return False
    if not re.search(r"[A-Za-z]", value):
        return False
    lowered = value.lower()
    if any(
        token in lowered
        for token in (
            "http://",
            "https://",
            "rgb(",
            "xmlns",
            "viewbox",
            "class",
            "data-section-id",
            "auto=format",
            "fit=crop",
            "mix-blend",
            "clip-path",
            "transition-",
            "object-cover",
        )
    ):
        return False
    if any(
        token in value
        for token in (
            "{",
            "}",
            "<",
            ">",
            "=>",
            "::",
            "w-",
            "h-",
            "px-",
            "py-",
            "md:",
            "lg:",
            "sm:",
            "text-[",
            "rounded-[",
            "border-[",
            "gap-",
            "flex-",
            "grid-",
            "bg-",
            "font-",
        )
    ):
        return False
    if value.count(" ") >= 1:
        tokens = value.split()
        utility_like = sum(
            1
            for token in tokens
            if any(marker in token for marker in ("-", "[", "]", "/", ":"))
        )
        if utility_like >= max(2, len(tokens) // 2):
            return False
    if re.fullmatch(r"[a-z0-9_.:/-]+", lowered):
        return False
    return True


def _extract_title(app_source: str, sections: list[dict[str, Any]]) -> str | None:
    heading_matches = re.findall(r"<h[12][^>]*>\s*([^<{][^<]{1,120})\s*</h[12]>", app_source)
    best_heading = _pick_best_title_candidate(heading_matches)
    if best_heading:
        return best_heading
    return _pick_best_title_candidate(
        [
            candidate
            for section in sections
            for candidate in section.get("keyText", [])
        ]
    )


def _pick_best_title_candidate(candidates: list[str]) -> str | None:
    best_candidate: tuple[int, str] | None = None
    for raw_candidate in candidates:
        candidate = " ".join(raw_candidate.strip().split())
        lowered = candidate.lower()
        if any(token in lowered for token in ("shop now", "try omni now", "get started")):
            continue
        if "$" in candidate:
            continue
        if re.match(r"^\d+\b", candidate):
            continue
        if any(
            token in lowered
            for token in ("day supply", "save ", "best value", "reviews", "orders delivered")
        ):
            continue
        if len(candidate.split()) < 2:
            continue

        word_count = len(candidate.split())
        score = word_count
        if any(token in lowered for token in ("omni", "creatine", "gummy", "formula")):
            score += 6
        if word_count <= 4:
            score += 4
        if not re.search(r"[.!?]", candidate):
            score += 3
        if candidate == candidate.title() or candidate.isupper():
            score += 2

        if best_candidate is None or score > best_candidate[0]:
            best_candidate = (score, candidate)
    return best_candidate[1] if best_candidate else None


def _extract_meta_description(sections: list[dict[str, Any]]) -> str | None:
    for section in sections:
        parsed = section.get("parsedData") or {}
        paragraphs = parsed.get("paragraphs")
        if isinstance(paragraphs, list):
            for candidate in paragraphs:
                if isinstance(candidate, str) and len(candidate.split()) >= 8:
                    return candidate
        for candidate in section.get("keyText", []):
            if len(candidate.split()) >= 8:
                return candidate
    return None


def _resolve_section_display_name(
    *,
    section_id: str,
    section_type: str,
    component_name: str | None,
    key_text: list[str],
    parsed_data: dict[str, Any],
) -> str:
    title = parsed_data.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    if component_name and component_name != "App":
        return _humanize_identifier(component_name)
    if key_text:
        first_candidate = next(
            (
                candidate
                for candidate in key_text
                if len(candidate.split()) >= 2
                and len(candidate) <= 90
                and not _looks_like_cta(candidate)
            ),
            None,
        )
        if first_candidate:
            return first_candidate
    if section_id:
        return _humanize_identifier(section_id)
    return _humanize_identifier(section_type or "Imported Section")


def _build_section_semantic_tags(
    *,
    section_id: str,
    section_type: str,
    parsed_data: dict[str, Any],
) -> list[str]:
    tags = [section_type]
    lowered_id = section_id.lower()
    if "purchase" in lowered_id or "shop" in lowered_id:
        tags.append("purchase")
    if parsed_data.get("tiers"):
        tags.append("offers")
    if parsed_data.get("galleryImages"):
        tags.append("gallery")
    if parsed_data.get("faqs"):
        tags.append("accordion")
    if parsed_data.get("comparisons"):
        tags.append("comparison")
    if parsed_data.get("testimonials"):
        tags.append("testimonials")
    if parsed_data.get("links"):
        tags.append("links")
    return _ordered_unique([tag for tag in tags if tag])


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


def _build_code_bundle(*, files: dict[str, str], ordered_paths: list[str | None]) -> str:
    output_parts: list[str] = []
    seen: set[str] = set()
    for maybe_path in ordered_paths:
        if not maybe_path or maybe_path in seen or maybe_path not in files:
            continue
        seen.add(maybe_path)
        output_parts.append(f"// FILE: {maybe_path}\n{files[maybe_path]}")
    return "\n\n".join(output_parts)


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _search(source: str, pattern: str) -> str | None:
    if not source:
        return None
    match = re.search(pattern, source, re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _humanize_page_type(page_type: str) -> str:
    return " ".join(token.capitalize() for token in page_type.split("_") if token) or "Imported Page"


def _humanize_identifier(value: str) -> str:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value or "")
    tokens = re.split(r"[_\-\s]+", normalized)
    spaced = " ".join(token for token in tokens if token)
    if spaced and spaced.isupper():
        return spaced
    return spaced.title() if spaced else "Imported Section"


def _slugify_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "imported-section"


def _derive_site_type(page_type: str) -> str:
    if page_type in {"product_detail", "category", "collection", "cart", "checkout"}:
        return "ecommerce"
    if page_type in {"pre_sell", "landing"}:
        return "landing"
    return "content"


def _load_base_design_system_tokens_template() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "templates" / "design_systems" / "base_tokens.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SiteImportArchiveError(
            f"Missing design system base template at {path}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SiteImportArchiveError(
            f"Design system base template is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SiteImportArchiveError("Design system base template must decode to a JSON object.")
    return payload


def _frontend_root() -> Path:
    return Path(__file__).resolve().parents[3] / "frontend"


def _compile_archive_css(
    *,
    files: dict[str, str],
    tailwind_path: str | None,
    index_css_path: str,
    content_paths: list[str],
) -> str:
    frontend_root = _frontend_root()
    tailwind_bin_name = "tailwindcss.cmd" if os.name == "nt" else "tailwindcss"
    tailwind_bin = frontend_root / "node_modules" / ".bin" / tailwind_bin_name
    if not tailwind_bin.exists():
        raise SiteImportArchiveError(
            "Frontend Tailwind compiler is not available. Install frontend dependencies before importing archives."
        )

    with tempfile.TemporaryDirectory(prefix="mos-archive-import-") as temp_dir:
        temp_root = Path(temp_dir)
        for archive_path, content in files.items():
            destination = temp_root / archive_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")

        output_path = temp_root / "compiled-import.css"
        command = [
            str(tailwind_bin),
            "--input",
            str(temp_root / index_css_path),
            "--output",
            str(output_path),
            "--content",
            ",".join(str(temp_root / path) for path in content_paths if path in files),
            "--minify",
        ]
        if tailwind_path:
            command.extend(["--config", str(temp_root / tailwind_path)])

        result = subprocess.run(
            command,
            cwd=temp_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise SiteImportArchiveError(
                "Failed to compile archive Tailwind CSS into a first-party runtime artifact."
                + (f" {stderr}" if stderr else "")
            )
        css = output_path.read_text(encoding="utf-8")
        if not css.strip():
            raise SiteImportArchiveError(
                "Archive Tailwind CSS compilation produced empty output."
            )
        return css


class _ArchiveHeadAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stylesheet_hrefs: list[str] = []
        self.script_srcs: list[str] = []
        self.inline_styles: list[str] = []
        self.inline_scripts: list[str] = []
        self.body_class_name = ""
        self._capture_style = False
        self._capture_script = False
        self._style_chunks: list[str] = []
        self._script_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "body" and attributes.get("class", "").strip():
            self.body_class_name = attributes["class"].strip()
        if tag == "link":
            rel = attributes.get("rel", "").lower()
            href = attributes.get("href", "").strip()
            if "stylesheet" in rel and _is_external_asset_url(href):
                self.stylesheet_hrefs.append(href)
            return
        if tag == "style":
            self._capture_style = True
            self._style_chunks = []
            return
        if tag != "script":
            return

        script_type = attributes.get("type", "").strip().lower()
        script_src = attributes.get("src", "").strip()
        if script_src:
            if script_type != "module" and _is_external_asset_url(script_src):
                self.script_srcs.append(script_src)
            self._capture_script = False
            self._script_chunks = []
            return

        if script_type == "module":
            self._capture_script = False
            self._script_chunks = []
            return

        self._capture_script = True
        self._script_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._capture_style:
            style = "".join(self._style_chunks).strip()
            if style:
                self.inline_styles.append(style)
            self._capture_style = False
            self._style_chunks = []
        if tag == "script" and self._capture_script:
            script = "".join(self._script_chunks).strip()
            if script:
                self.inline_scripts.append(script)
            self._capture_script = False
            self._script_chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture_style:
            self._style_chunks.append(data)
        if self._capture_script:
            self._script_chunks.append(data)


def _is_external_asset_url(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith(("http://", "https://", "//", "data:"))


def _build_imported_head_assets(*, index_html: str, compiled_css: str) -> dict[str, Any]:
    parser = _ArchiveHeadAssetParser()
    parser.feed(index_html)
    inline_styles = [compiled_css]
    inline_styles.extend(style for style in parser.inline_styles if style.strip())
    return {
        "scriptSrcs": parser.script_srcs,
        "stylesheetHrefs": parser.stylesheet_hrefs,
        "inlineStyles": inline_styles,
        "inlineScripts": parser.inline_scripts,
        "bodyClassName": parser.body_class_name,
    }


def _build_runtime_source(*, app_source: str) -> str:
    source = app_source.replace("\r\n", "\n")

    import_sources = [
        *re.findall(r'^\s*import\s+.*?from\s+["\']([^"\']+)["\']\s*;?\s*$', source, re.MULTILINE),
        *re.findall(r'^\s*import\s+["\']([^"\']+)["\']\s*;?\s*$', source, re.MULTILINE),
    ]
    unsupported_imports = [
        import_source
        for import_source in import_sources
        if import_source.strip() not in _ALLOWED_RUNTIME_IMPORT_SOURCES
    ]
    if unsupported_imports:
        raise SiteImportArchiveError(
            "Archive App.tsx contains unsupported imports for first-party runtime translation: "
            + ", ".join(sorted(set(unsupported_imports)))
            + ". Inline local dependencies into src/App.tsx before importing."
        )

    source = re.sub(r'^\s*import\s+.*?;\s*$', "", source, flags=re.MULTILINE)
    source = re.sub(r"^\s*//\s*@ts-nocheck\s*$", "", source, flags=re.MULTILINE)
    source = re.sub(
        r"\bconst\s+root\s*=\s*ReactDOM\.createRoot\((?:.|\n)*?\);\s*",
        "",
        source,
        flags=re.MULTILINE,
    )
    source = re.sub(
        r"\bReactDOM\.createRoot\((?:.|\n)*?\)\.render\((?:.|\n)*?\);\s*",
        "",
        source,
        flags=re.MULTILINE,
    )
    source = re.sub(
        r"\broot\.render\((?:.|\n)*?\);\s*",
        "",
        source,
        flags=re.MULTILINE,
    )

    if re.search(r"\bexport\s+default\s+function\s+[A-Za-z0-9_]+\b", source):
        source = re.sub(
            r"\bexport\s+default\s+function\s+([A-Za-z0-9_]+)\b",
            r"function \1",
            source,
            count=1,
        )
    elif re.search(r"\bconst\s+App\s*=", source) or re.search(r"\bfunction\s+App\s*\(", source):
        source = re.sub(r"\bexport\s+default\s+App\s*;?\s*$", "", source, flags=re.MULTILINE)
    else:
        raise SiteImportArchiveError(
            "Archive App.tsx must export a default App component for first-party runtime translation."
        )

    remaining_export = re.search(r"^\s*export\s+", source, flags=re.MULTILINE)
    if remaining_export:
        raise SiteImportArchiveError(
            "Archive App.tsx contains additional exports that are not supported by the first-party runtime translation."
        )

    cleaned = source.strip()
    component_names = sorted(
        {
            match.group(1)
            for match in re.finditer(
                r"(?m)^(?:const|function)\s+([A-Z][A-Za-z0-9_]*)\b",
                cleaned,
            )
        }
    )
    registry_entries = ", ".join(component_names)
    suffix_lines = []
    if registry_entries:
        suffix_lines.append(
            f"globalThis.__mosImportedRuntimeComponents = {{ {registry_entries} }};"
        )
    if "App" in component_names:
        suffix_lines.append("const ImportedSection = App;")
    return cleaned + ("\n\n" + "\n".join(suffix_lines) if suffix_lines else "") + "\n"


def _build_imported_template_puck_data(
    *,
    title: str,
    description: str,
    page_type: str,
    theme_candidate: dict[str, Any],
    normalized_sections: list[dict[str, Any]],
    runtime_source: str,
    head_assets: dict[str, Any],
) -> dict[str, Any]:
    section_nodes = [
        _build_imported_section_block(
            section=section,
        )
        for section in normalized_sections
    ]

    return {
        "root": {
            "props": {
                "title": title,
                "description": description,
            }
        },
        "content": [
            _make_imported_block(
                "ImportedPage",
                pageName=title,
                pageType=page_type,
                theme=theme_candidate,
                renderMode="source",
                sharedRuntimeSource=runtime_source,
                sharedHeadAssets=head_assets,
                content=section_nodes,
            )
        ],
        "zones": {},
    }


def _make_imported_block(block_type: str, **props: Any) -> dict[str, Any]:
    return {
        "type": block_type,
        "props": {
            "id": f"imported-{uuid4().hex[:10]}",
            **props,
        },
    }


def _build_imported_section_block(
    *,
    section: dict[str, Any],
) -> dict[str, Any]:
    semantic_tags = section.get("semanticTags") or []
    semantic_tags_text = ", ".join(
        tag.strip() for tag in semantic_tags if isinstance(tag, str) and tag.strip()
    )
    component_name = str(section.get("componentName") or "").strip() or "App"
    section_id = str(section.get("id") or "").strip()

    return _make_imported_block(
        "ImportedSection",
        displayName=section.get("displayName") or _humanize_identifier(str(section.get("id") or "Section")),
        sourceSectionId=section.get("id") or "",
        sectionKey=section.get("sectionKey") or _slugify_token(str(section.get("id") or "section")),
        sectionType=section.get("sectionType") or "generic_content",
        semanticTagsText=semantic_tags_text,
        surface="source",
        renderMode="source",
        content=[
            _make_imported_block(
                "ImportedRuntimeSection",
                sectionLabel=section.get("displayName") or _humanize_identifier(section_id or "Section"),
                componentName=component_name,
                sectionTargetId=section_id if component_name == "App" else "",
                textOverrides=_build_text_override_items(section=section),
                buttonOverrides=_build_button_override_items(section=section),
                imageOverrides=_build_image_override_items(section=section),
            )
        ],
    )


def _build_text_override_items(*, section: dict[str, Any]) -> list[dict[str, str]]:
    parsed_data = section.get("parsedData") or {}
    button_texts = {
        str(button.get("label") or "").strip()
        for button in (parsed_data.get("buttonActions") or [])
        if isinstance(button, dict) and str(button.get("label") or "").strip()
    }

    labeled_candidates: list[tuple[str, str]] = []
    title = parsed_data.get("title")
    if isinstance(title, str) and title.strip():
        labeled_candidates.append(("Headline", title.strip()))

    body = parsed_data.get("body")
    if isinstance(body, str) and body.strip():
        labeled_candidates.append(("Body copy", body.strip()))

    paragraphs = parsed_data.get("paragraphs") or []
    if isinstance(paragraphs, list):
        for index, value in enumerate(paragraphs, start=1):
            if isinstance(value, str) and value.strip():
                labeled_candidates.append((f"Paragraph {index}", value.strip()))

    badges = parsed_data.get("badges") or []
    if isinstance(badges, list):
        for index, value in enumerate(badges, start=1):
            if isinstance(value, str) and value.strip():
                labeled_candidates.append((f"Badge {index}", value.strip()))

    checklist = parsed_data.get("checklist") or []
    if isinstance(checklist, list):
        for index, value in enumerate(checklist, start=1):
            if isinstance(value, str) and value.strip():
                labeled_candidates.append((f"Checklist item {index}", value.strip()))

    strings = parsed_data.get("strings") or []
    if isinstance(strings, list):
        for index, value in enumerate(strings, start=1):
            if isinstance(value, str) and value.strip():
                labeled_candidates.append((f"Text {index}", value.strip()))

    if not labeled_candidates:
        for index, candidate in enumerate(section.get("keyText") or [], start=1):
            if isinstance(candidate, str) and candidate.strip():
                labeled_candidates.append((f"Text {index}", candidate.strip()))

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, (label, candidate) in enumerate(labeled_candidates, start=1):
        if candidate in button_texts or candidate in seen:
            continue
        seen.add(candidate)
        results.append(
            {
                "key": f"text-{index}",
                "label": label,
                "originalText": candidate,
                "text": candidate,
            }
        )
    return results


def _build_button_override_items(*, section: dict[str, Any]) -> list[dict[str, str]]:
    parsed_data = section.get("parsedData") or {}
    actions = parsed_data.get("buttonActions") or []
    results: list[dict[str, str]] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        label = str(action.get("label") or "").strip()
        href = str(action.get("href") or "").strip()
        if not label:
            continue
        results.append(
            {
                "key": f"button-{index + 1}",
                "label": f"Button {index + 1}",
                "originalText": label,
                "text": label,
                "href": href,
            }
        )
    return results


def _build_image_override_items(*, section: dict[str, Any]) -> list[dict[str, str]]:
    parsed_data = section.get("parsedData") or {}
    candidates: list[str] = []
    for key in ("galleryImages", "media"):
        values = parsed_data.get(key) or []
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
    for value in section.get("keyMedia") or []:
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if candidate in seen:
            continue
        seen.add(candidate)
        results.append(
            {
                "key": f"image-{index + 1}",
                "label": f"Image {index + 1}",
                "originalSrc": candidate,
                "src": candidate,
                "alt": "",
            }
        )
    return results


def _build_imported_section_content(*, section: dict[str, Any], index: int) -> list[dict[str, Any]]:
    section_type = str(section.get("sectionType") or "generic_content")
    parsed_data = section.get("parsedData") or {}
    section_id = str(section.get("id") or "")

    if section_type == "proof_bar" and (
        "marquee" in section_id or "feature-marquee" in section_id or not parsed_data
    ):
        badges = _build_badge_items(section)
        if badges:
            return [_build_badge_strip_block(section=section, badges=badges)]

    if section_type in {"bundle_selector", "sticky_offer_rail"}:
        return [_build_offer_selector_block(section=section)]

    if section_type == "testimonial_wall" or parsed_data.get("testimonials"):
        return [_build_testimonials_block(section=section)]

    if section_type == "comparison_table" or parsed_data.get("comparisons"):
        return [_build_comparison_block(section=section)]

    if section_type == "faq" or parsed_data.get("faqs"):
        return [_build_accordion_block(section=section)]

    if section_type == "footer":
        return [_build_footer_links_block(section=section)]

    blocks: list[dict[str, Any]] = []
    narrative_block = _build_narrative_block(section=section, index=index)
    if narrative_block is not None:
        blocks.append(narrative_block)

    item_grid_block = _build_item_grid_block(section=section)
    if item_grid_block is not None:
        blocks.append(item_grid_block)

    return blocks


def _build_narrative_block(*, section: dict[str, Any], index: int) -> dict[str, Any] | None:
    title = _section_title(section)
    body = _section_body(section)
    image_src = _section_primary_media(section)
    buttons = _section_buttons(section)
    badges = _build_badge_items(section)
    quote = _section_quote(section)

    if not any((title, body, image_src, buttons, quote, badges)):
        return None

    return _make_imported_block(
        "ImportedNarrativeBlock",
        eyebrow=_section_eyebrow(section),
        title=title,
        body=body,
        quote=quote,
        imageSrc=image_src or "",
        imageAlt=title or section.get("displayName") or "Imported image",
        mediaPosition="left" if index % 2 else "right",
        align="center" if not image_src else "left",
        badges=[{"label": badge} for badge in badges[:4]],
        buttons=buttons,
    )


def _build_item_grid_block(*, section: dict[str, Any]) -> dict[str, Any] | None:
    parsed_data = section.get("parsedData") or {}
    items = _normalize_grid_items(parsed_data)
    if not items:
        return None

    return _make_imported_block(
        "ImportedItemGrid",
        title=_section_title(section),
        body=_section_body(section),
        columns=min(4, max(2, len(items))),
        items=items,
    )


def _build_badge_strip_block(*, section: dict[str, Any], badges: list[str]) -> dict[str, Any]:
    return _make_imported_block(
        "ImportedBadgeStrip",
        title=_section_title(section),
        items=[{"label": badge} for badge in badges[:8]],
    )


def _build_offer_selector_block(*, section: dict[str, Any]) -> dict[str, Any]:
    parsed_data = section.get("parsedData") or {}
    gallery_images = parsed_data.get("galleryImages") or parsed_data.get("media") or section.get("keyMedia") or []
    tiers = parsed_data.get("tiers") or []
    benefits = _normalize_benefit_items(parsed_data)
    review_text = _section_review_text(section)

    return _make_imported_block(
        "ImportedOfferSelector",
        eyebrow=_section_eyebrow(section),
        title=_section_title(section),
        body=_section_body(section),
        reviewText=review_text,
        ctaLabel=_section_primary_button_label(section) or "Shop now",
        galleryImages=[
            {"src": image, "alt": f"{_section_title(section) or 'Imported product'} image {index + 1}"}
            for index, image in enumerate(gallery_images[:8])
            if isinstance(image, str) and image.strip()
        ],
        benefits=[{"text": item} for item in benefits[:6]],
        offers=_normalize_offer_items(tiers),
    )


def _build_testimonials_block(*, section: dict[str, Any]) -> dict[str, Any]:
    parsed_data = section.get("parsedData") or {}
    testimonials = parsed_data.get("testimonials") or []
    items = []
    for testimonial in testimonials:
        if not isinstance(testimonial, dict):
            continue
        items.append(
            {
                "name": str(testimonial.get("name") or testimonial.get("title") or "Customer"),
                "quote": str(
                    testimonial.get("review")
                    or testimonial.get("quote")
                    or testimonial.get("description")
                    or ""
                ),
                "role": str(testimonial.get("subtitle") or ""),
                "imageSrc": str(testimonial.get("image") or ""),
            }
        )

    if not items:
        fallback_quote = _section_body(section)
        if fallback_quote:
            items = [{"name": _section_title(section) or "Customer", "quote": fallback_quote, "role": "", "imageSrc": ""}]

    return _make_imported_block(
        "ImportedTestimonialsGrid",
        title=_section_title(section),
        body=_section_body(section),
        items=items,
    )


def _build_comparison_block(*, section: dict[str, Any]) -> dict[str, Any]:
    comparisons = (section.get("parsedData") or {}).get("comparisons") or []
    rows = []
    primary_label = "Primary"
    secondary_label = "Option 2"
    tertiary_label = "Option 3"
    if comparisons and isinstance(comparisons[0], dict):
        comparison_keys = [
            key for key in comparisons[0].keys() if key not in {"feature", "label", "title"}
        ]
        if comparison_keys:
            primary_label = _humanize_identifier(comparison_keys[0])
        if len(comparison_keys) > 1:
            secondary_label = _humanize_identifier(comparison_keys[1])
        if len(comparison_keys) > 2:
            tertiary_label = _humanize_identifier(comparison_keys[2])
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                continue
            values = [
                _stringify_comparison_value(comparison.get(key))
                for key in comparison_keys[:3]
            ]
            while len(values) < 3:
                values.append("")
            rows.append(
                {
                    "feature": str(
                        comparison.get("feature") or comparison.get("label") or comparison.get("title") or "Feature"
                    ),
                    "primaryValue": values[0],
                    "secondaryValue": values[1],
                    "tertiaryValue": values[2],
                }
            )

    return _make_imported_block(
        "ImportedComparisonTable",
        title=_section_title(section),
        body=_section_body(section),
        primaryLabel=primary_label,
        secondaryLabel=secondary_label,
        tertiaryLabel=tertiary_label,
        rows=rows,
    )


def _build_accordion_block(*, section: dict[str, Any]) -> dict[str, Any]:
    faqs = (section.get("parsedData") or {}).get("faqs") or []
    items = [
        {
            "question": str(faq.get("question") or "Question"),
            "answer": str(faq.get("answer") or ""),
        }
        for faq in faqs
        if isinstance(faq, dict)
    ]
    if not items and _section_body(section):
        items = [{"question": _section_title(section) or "Question", "answer": _section_body(section) or ""}]
    return _make_imported_block(
        "ImportedAccordion",
        title=_section_title(section),
        body=_section_body(section),
        items=items,
    )


def _build_footer_links_block(*, section: dict[str, Any]) -> dict[str, Any]:
    parsed_data = section.get("parsedData") or {}
    links = parsed_data.get("links") or []
    return _make_imported_block(
        "ImportedFooterLinks",
        brandName=_section_brand_name(section),
        body=_section_body(section),
        legalText=_section_legal_text(section),
        links=[
            {
                "label": str(link.get("label") or "Link"),
                "href": str(link.get("href") or ""),
            }
            for link in links
            if isinstance(link, dict)
        ],
    )


def _normalize_grid_items(parsed_data: dict[str, Any]) -> list[dict[str, str]]:
    if parsed_data.get("features"):
        return [
            {
                "label": "",
                "title": str(item.get("title") or "Feature"),
                "text": str(item.get("description") or item.get("text") or ""),
                "value": "",
            }
            for item in parsed_data["features"]
            if isinstance(item, dict)
        ]
    if parsed_data.get("stats"):
        return [
            {
                "label": str(item.get("label") or ""),
                "title": str(item.get("title") or item.get("percent") or item.get("value") or ""),
                "text": str(item.get("description") or ""),
                "value": str(item.get("percent") or item.get("value") or ""),
            }
            for item in parsed_data["stats"]
            if isinstance(item, dict)
        ]
    if parsed_data.get("checklist"):
        return [
            {
                "label": "",
                "title": str(item),
                "text": "",
                "value": "",
            }
            for item in parsed_data["checklist"]
            if isinstance(item, str) and item.strip()
        ]
    if parsed_data.get("items"):
        return [
            {
                "label": str(item.get("label") or ""),
                "title": str(item.get("title") or item.get("text") or "Item"),
                "text": str(item.get("description") or item.get("body") or ""),
                "value": str(item.get("value") or ""),
            }
            for item in parsed_data["items"]
            if isinstance(item, dict)
        ]
    return []


def _normalize_benefit_items(parsed_data: dict[str, Any]) -> list[str]:
    if parsed_data.get("checklist"):
        return [str(item) for item in parsed_data["checklist"] if isinstance(item, str) and item.strip()]
    if parsed_data.get("features"):
        return [
            str(item.get("title") or "")
            for item in parsed_data["features"]
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
    if parsed_data.get("badges"):
        return [str(item) for item in parsed_data["badges"] if isinstance(item, str) and item.strip()]
    return []


def _normalize_offer_items(tiers: list[Any]) -> list[dict[str, str]]:
    offer_items = []
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        offer_items.append(
            {
                "title": str(tier.get("title") or "Offer"),
                "subtitle": str(tier.get("subtitle") or ""),
                "price": str(tier.get("price") or ""),
                "total": str(tier.get("total") or ""),
                "regularPrice": str(tier.get("regularPrice") or ""),
                "savings": str(tier.get("savings") or ""),
                "badge": str(tier.get("badge") or ""),
            }
        )
    return offer_items


def _build_badge_items(section: dict[str, Any]) -> list[str]:
    parsed_data = section.get("parsedData") or {}
    badge_candidates: list[str] = []
    for key in ("badges", "checklist"):
        values = parsed_data.get(key) or []
        for value in values:
            if isinstance(value, str) and value.strip():
                badge_candidates.append(value.strip())
    for candidate in section.get("keyText") or []:
        if not isinstance(candidate, str):
            continue
        stripped = candidate.strip()
        if stripped.upper() != stripped or len(stripped.split()) > 6:
            continue
        badge_candidates.append(stripped)
    return _ordered_unique(badge_candidates)


def _section_title(section: dict[str, Any]) -> str:
    parsed_data = section.get("parsedData") or {}
    title = parsed_data.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    display_name = str(section.get("displayName") or "").strip()
    if display_name and not _looks_like_cta(display_name):
        return display_name
    for candidate in section.get("keyText") or []:
        if (
            isinstance(candidate, str)
            and candidate.strip()
            and len(candidate.split()) >= 2
            and not _looks_like_cta(candidate)
        ):
            return candidate.strip()
    return display_name


def _section_body(section: dict[str, Any]) -> str:
    parsed_data = section.get("parsedData") or {}
    body = parsed_data.get("body")
    if isinstance(body, str) and body.strip():
        return body.strip()
    title = _section_title(section)
    for candidate in section.get("keyText") or []:
        if not isinstance(candidate, str):
            continue
        stripped = candidate.strip()
        if stripped and stripped != title and len(stripped.split()) >= 6:
            return stripped
    return ""


def _section_eyebrow(section: dict[str, Any]) -> str:
    parsed_data = section.get("parsedData") or {}
    badges = parsed_data.get("badges") or []
    for badge in badges:
        if isinstance(badge, str) and badge.strip():
            return badge.strip()
    title = _section_title(section)
    body = _section_body(section)
    for candidate in section.get("keyText") or []:
        if not isinstance(candidate, str):
            continue
        stripped = candidate.strip()
        if stripped and stripped not in {title, body} and len(stripped.split()) <= 5 and stripped.upper() == stripped:
            return stripped
    return ""


def _section_primary_media(section: dict[str, Any]) -> str | None:
    parsed_data = section.get("parsedData") or {}
    for key in ("media", "galleryImages"):
        values = parsed_data.get(key) or []
        if isinstance(values, list):
            first_value = next((value for value in values if isinstance(value, str) and value.strip()), None)
            if first_value:
                return first_value
    media = section.get("keyMedia") or []
    return next((value for value in media if isinstance(value, str) and value.strip()), None)


def _section_buttons(section: dict[str, Any]) -> list[dict[str, str]]:
    parsed_data = section.get("parsedData") or {}
    button_actions = parsed_data.get("buttonActions") or []
    buttons = []
    for button in button_actions:
        if not isinstance(button, dict):
            continue
        label = str(button.get("label") or "").strip()
        if not label:
            continue
        buttons.append(
            {
                "label": label,
                "href": str(button.get("href") or "").strip(),
            }
        )
    return buttons[:3]


def _section_primary_button_label(section: dict[str, Any]) -> str | None:
    buttons = _section_buttons(section)
    if buttons:
        return buttons[0]["label"]
    return None


def _section_quote(section: dict[str, Any]) -> str:
    body = _section_body(section)
    return body if body.startswith('"') or body.startswith("“") else ""


def _section_review_text(section: dict[str, Any]) -> str:
    for candidate in section.get("keyText") or []:
        if isinstance(candidate, str) and "review" in candidate.lower():
            return candidate
    return ""


def _section_brand_name(section: dict[str, Any]) -> str:
    for candidate in section.get("keyText") or []:
        if not isinstance(candidate, str):
            continue
        stripped = candidate.strip()
        if stripped.isupper() and len(stripped.split()) <= 2 and len(stripped) <= 20:
            return stripped
    display_name = str(section.get("displayName") or "").strip()
    return display_name.split()[0].upper() if display_name else ""


def _section_legal_text(section: dict[str, Any]) -> str:
    parsed_data = section.get("parsedData") or {}
    paragraphs = parsed_data.get("paragraphs") or []
    for paragraph in paragraphs:
        if isinstance(paragraph, str) and len(paragraph.split()) >= 8:
            return paragraph
    return _section_body(section)


def _resolve_section_surface(*, section_type: str, index: int) -> str:
    if section_type in {"proof_bar", "sticky_offer_rail"}:
        return "primary"
    if section_type in {"hero", "testimonial_wall", "comparison_table"}:
        return "muted" if index % 2 else "default"
    return "default"


def _stringify_comparison_value(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return ""
    return str(value)


def _looks_like_cta(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return any(
        token in lowered
        for token in (
            "shop now",
            "shop omni now",
            "try omni today",
            "try omni now",
            "add to cart",
            "subscribe",
            "learn more",
            "contact us",
        )
    )
