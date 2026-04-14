from __future__ import annotations

from copy import deepcopy
import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from app.config import settings
from app.services.site_import_section_translation import (
    normalize_imported_section_translation,
    translate_imported_source_section,
)

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


@dataclass(frozen=True)
class ImportedSectionMaterialization:
    blocks: list[dict[str, Any]]
    surface: str
    render_mode: str


_MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
_IMPORTED_TEMPLATE_FAMILY = "imported-template"
_RUNTIME_PRESERVED_COMPONENT_NAMES = {"ProductPurchaseSection"}
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
    index_html = _get_required_file(files, "index.html")
    app_path = _resolve_first_existing(
        files,
        ["src/App.tsx", "src/App.jsx", "src/App.ts", "src/App.js"],
    )
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
    if not index_css_path:
        raise SiteImportArchiveError(
            "Archive import requires a stylesheet entry file for fidelity-preserving translation. "
            "Expected one of: src/index.css, src/app.css, src/styles.css."
        )

    extracted_theme_candidate = _extract_theme_candidate(
        tailwind_source=files.get(tailwind_path) if tailwind_path else None,
        index_css_source=files.get(index_css_path) if index_css_path else None,
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
    project_name = str(package_data.get("name") or "").strip() or None
    source_url = f"archive://{archive_name.strip()}"
    resolved_template_id = None
    page_title = title or project_name or _humanize_page_type(resolved_page_type)
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
    adapted_puck_data = rebuild_imported_template_puck_data(
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
) -> dict[str, Any]:
    source = "\n".join(part for part in (tailwind_source, index_css_source) if part)
    palette = {
        "primary": _search(source, r"primary\s*:\s*\{[^}]*DEFAULT:\s*'([^']+)'"),
        "secondary": _search(source, r"primary\s*:\s*\{[^}]*dark:\s*'([^']+)'"),
        "surface": _search(source, r"bg\s*:\s*\{[^}]*card:\s*'([^']+)'"),
        "accent": _search(source, r"sale\s*:\s*\{[^}]*red:\s*'([^']+)'"),
        "text": _search(source, r"text\s*:\s*\{[^}]*dark:\s*'([^']+)'"),
        "background": _search(source, r"bg\s*:\s*\{[^}]*light:\s*'([^']+)'"),
    }
    fonts = {
        "heading": _search(source, r"sans\s*:\s*\[\s*'([^']+)'"),
        "body": _search(source, r"sans\s*:\s*\[\s*'([^']+)'"),
        "cta": _search(source, r"sans\s*:\s*\[\s*'([^']+)'"),
    }
    border_radius = _search(source, r"pill'\s*:\s*'([^']+)'")
    return {
        "palette": palette,
        "fonts": fonts,
        "spacing": {"density": "comfortable", "scale": []},
        "cta": {
            "style": "solid",
            "borderRadius": border_radius,
            "padding": None,
        },
    }


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
    results.extend(_extract_jsx_text_fragments(snippet))
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


def _extract_jsx_text_fragments(snippet: str) -> list[str]:
    cleaned = re.sub(r"\{/\*.*?\*/\}", "\n", snippet, flags=re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", "\n", cleaned)
    cleaned = re.sub(r"\{[^{}]*\}", "\n", cleaned)

    results: list[str] = []
    for raw_line in cleaned.splitlines():
        normalized = " ".join(raw_line.strip().split())
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered.startswith(("const ", "return", "export ", "import ", "from ", "globalthis.")):
            continue
        if _looks_like_human_text(normalized):
            results.append(normalized)
    return results


def _extract_button_labels(snippet: str) -> list[str]:
    return [button["label"] for button in _extract_buttons(snippet)]


def _extract_buttons(snippet: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for tag_name in ("button", "a"):
        for match in re.finditer(
            rf"<{tag_name}\b([^>]*)>(.*?)</{tag_name}>",
            snippet,
            re.DOTALL,
        ):
            attrs = match.group(1)
            inner_html = match.group(2)
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
    raw = re.sub(r",\s*$", "", raw)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        payload = json.loads(f"[{raw}]")
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _looks_like_human_text(value: str) -> bool:
    if len(value) < 4 or len(value) > 400:
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
            "classname",
            "auto=format",
            "fit=crop",
            "mix-blend",
            "clip-path",
            "transition-",
            "object-cover",
            ".map(",
            "setselected",
            "setmainimage",
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
            if _looks_like_utility_token(token)
        )
        if utility_like >= max(2, len(tokens) // 2):
            return False
    if re.fullmatch(r"[a-z0-9_.:/-]+", lowered) and re.search(r"[0-9_./:-]", lowered):
        return False
    return True


def _looks_like_utility_token(token: str) -> bool:
    stripped = (token or "").strip().lower()
    if not stripped:
        return False
    if stripped in {
        "flex",
        "grid",
        "block",
        "inline",
        "inline-block",
        "relative",
        "absolute",
        "fixed",
        "sticky",
        "hidden",
    }:
        return True
    if any(marker in stripped for marker in ("[", "]", "/", ":")):
        return True
    return bool(
        re.match(
            r"^(w|h|min|max|px|py|pt|pb|pl|pr|mx|my|mt|mb|ml|mr|gap|flex|grid|bg|text|font|rounded|border|object|justify|items|content|tracking|leading|shadow|opacity|z|top|right|left|bottom|inset|hover|focus|sm|md|lg|xl|2xl)-",
            stripped,
        )
    )


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
            index=index,
            runtime_source=runtime_source,
        )
        for index, section in enumerate(normalized_sections)
    ]

    page_props: dict[str, Any] = {
        "pageName": title,
        "pageType": page_type,
        "theme": theme_candidate,
        "renderMode": "source",
        "content": section_nodes,
    }
    if runtime_source.strip():
        page_props["sharedRuntimeSource"] = runtime_source
    if head_assets:
        page_props["sharedHeadAssets"] = head_assets

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
                **page_props,
            )
        ],
        "zones": {},
    }


def rebuild_imported_template_puck_data(
    *,
    title: str,
    description: str,
    page_type: str,
    theme_candidate: dict[str, Any] | None,
    normalized_sections: list[dict[str, Any]],
    runtime_source: str | None = None,
    head_assets: dict[str, Any] | None = None,
    existing_puck_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shared_runtime_source = runtime_source
    if not isinstance(shared_runtime_source, str) or not shared_runtime_source.strip():
        shared_runtime_source = _extract_imported_page_shared_runtime_source(existing_puck_data)

    shared_head_assets = head_assets
    if not isinstance(shared_head_assets, dict) or not shared_head_assets:
        shared_head_assets = _extract_imported_page_shared_head_assets(existing_puck_data)

    return _build_imported_template_puck_data(
        title=title,
        description=description,
        page_type=page_type,
        theme_candidate=theme_candidate or {},
        normalized_sections=normalized_sections,
        runtime_source=shared_runtime_source or "",
        head_assets=shared_head_assets or {},
    )


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
    index: int,
    runtime_source: str,
) -> dict[str, Any]:
    semantic_tags = section.get("semanticTags") or []
    semantic_tags_text = ", ".join(
        tag.strip() for tag in semantic_tags if isinstance(tag, str) and tag.strip()
    )
    section_build = _materialize_imported_section(section=section, index=index, runtime_source=runtime_source)

    return _make_imported_block(
        "ImportedSection",
        displayName=section.get("displayName") or _humanize_identifier(str(section.get("id") or "Section")),
        sourceSectionId=section.get("id") or "",
        sectionKey=section.get("sectionKey") or _slugify_token(str(section.get("id") or "section")),
        sectionType=section.get("sectionType") or "generic_content",
        semanticTagsText=semantic_tags_text,
        surface=section_build.surface,
        renderMode=section_build.render_mode,
        content=section_build.blocks,
    )


def _materialize_imported_section(
    *,
    section: dict[str, Any],
    index: int,
    runtime_source: str,
) -> ImportedSectionMaterialization:
    component_name = str(section.get("componentName") or "").strip() or "App"

    if component_name in _RUNTIME_PRESERVED_COMPONENT_NAMES:
        return ImportedSectionMaterialization(
            blocks=[_build_imported_runtime_section_block(section=section, runtime_source=runtime_source)],
            surface="source",
            render_mode="source",
        )

    return ImportedSectionMaterialization(
        blocks=[_build_source_backed_section_block(section=section, runtime_source=runtime_source)],
        surface="source",
        render_mode="source",
    )


def _build_imported_runtime_section_block(*, section: dict[str, Any], runtime_source: str) -> dict[str, Any]:
    component_name = str(section.get("componentName") or "").strip() or "App"
    section_id = str(section.get("id") or "").strip()
    block = _make_imported_block(
        "ImportedRuntimeSection",
        sectionLabel=section.get("displayName") or _humanize_identifier(section_id or "Section"),
        componentName=component_name,
        sectionTargetId=section_id if component_name == "App" else "",
        textOverrides=_build_text_override_items(section=section),
        buttonOverrides=_build_button_override_items(section=section),
        imageOverrides=_build_image_override_items(section=section),
    )
    block_props = block.get("props")
    if isinstance(block_props, dict):
        _populate_imported_runtime_override_slots(
            block_props=block_props,
            section=section,
            runtime_source=runtime_source,
        )
    return block


def backfill_imported_runtime_override_slots(puck_data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(puck_data, dict):
        return puck_data

    next_puck = deepcopy(puck_data)
    content = next_puck.get("content")
    if not isinstance(content, list) or not content:
        return next_puck

    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "ImportedPage":
        return next_puck

    page_props = first.get("props")
    if not isinstance(page_props, dict):
        return next_puck

    runtime_source = str(page_props.get("sharedRuntimeSource") or "").strip()
    sections = page_props.get("content")
    if not runtime_source or not isinstance(sections, list):
        return next_puck

    for section in sections:
        if not isinstance(section, dict) or section.get("type") != "ImportedSection":
            continue
        section_props = section.get("props")
        if not isinstance(section_props, dict):
            continue
        blocks = section_props.get("content")
        if not isinstance(blocks, list):
            continue

        semantic_tags = [
            candidate.strip()
            for candidate in str(section_props.get("semanticTagsText") or "").split(",")
            if candidate.strip()
        ]
        section_descriptor = {
            "id": str(
                section_props.get("sourceSectionId")
                or section_props.get("sectionKey")
                or section_props.get("id")
                or ""
            ).strip(),
            "displayName": str(section_props.get("displayName") or "").strip(),
            "sectionType": str(section_props.get("sectionType") or "generic_content").strip(),
            "semanticTags": semantic_tags,
        }

        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "ImportedRuntimeSection":
                continue
            block_props = block.get("props")
            if not isinstance(block_props, dict):
                continue

            component_name = str(block_props.get("componentName") or "").strip() or "App"
            descriptor = {
                **section_descriptor,
                "componentName": component_name,
            }
            _populate_imported_runtime_override_slots(
                block_props=block_props,
                section=descriptor,
                runtime_source=runtime_source,
            )

    return next_puck


def refresh_imported_page_copy_slots(puck_data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(puck_data, dict):
        return puck_data

    next_puck = backfill_imported_runtime_override_slots(puck_data)
    if not isinstance(next_puck, dict):
        return next_puck

    content = next_puck.get("content")
    if not isinstance(content, list) or not content:
        return next_puck

    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "ImportedPage":
        return next_puck

    page_props = first.get("props")
    if not isinstance(page_props, dict):
        return next_puck

    runtime_source = str(page_props.get("sharedRuntimeSource") or "").strip()
    sections = page_props.get("content")
    if not runtime_source or not isinstance(sections, list):
        return next_puck

    for section in sections:
        if not isinstance(section, dict) or section.get("type") != "ImportedSection":
            continue
        section_props = section.get("props")
        if not isinstance(section_props, dict):
            continue
        blocks = section_props.get("content")
        if not isinstance(blocks, list):
            continue

        semantic_tags = [
            candidate.strip()
            for candidate in str(section_props.get("semanticTagsText") or "").split(",")
            if candidate.strip()
        ]
        section_descriptor = {
            "id": str(
                section_props.get("sourceSectionId")
                or section_props.get("sectionKey")
                or section_props.get("id")
                or ""
            ).strip(),
            "displayName": str(section_props.get("displayName") or "").strip(),
            "sectionType": str(section_props.get("sectionType") or "generic_content").strip(),
            "semanticTags": semantic_tags,
        }

        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip()
            if block_type in {"", "ImportedPage", "ImportedSection", "ImportedRuntimeSection"}:
                continue
            if not block_type.startswith("Imported"):
                continue

            block_props = block.get("props")
            if not isinstance(block_props, dict):
                continue

            descriptor = {
                **section_descriptor,
                "componentName": str(block_props.get("componentName") or "").strip() or "App",
            }
            refreshed_block = _build_source_backed_section_block(
                section=descriptor,
                runtime_source=runtime_source,
            )
            blocks[block_index] = _merge_refreshed_source_backed_block(
                existing_block=block,
                refreshed_block=refreshed_block,
            )

    return next_puck


def _populate_imported_runtime_override_slots(
    *,
    block_props: dict[str, Any],
    section: dict[str, Any],
    runtime_source: str,
) -> None:
    try:
        section_source, _ = _resolve_source_backed_section_source(
            section=section,
            runtime_source=runtime_source,
        )
    except SiteImportArchiveError:
        return

    button_anchors = _extract_translation_button_anchors(section_source=section_source)
    component_name = str(section.get("componentName") or "").strip()
    if component_name in _RUNTIME_PRESERVED_COMPONENT_NAMES:
        text_anchors = _extract_runtime_preserved_text_anchors(
            section_source=section_source,
            button_anchors=button_anchors,
        )
    else:
        text_anchors = _extract_translation_text_anchors(section_source=section_source)
    image_anchors = _extract_translation_image_anchors(
        section=section,
        section_source=section_source,
        text_anchors=text_anchors,
    )

    block_props["textOverrides"] = _merge_imported_runtime_text_overrides(
        block_props.get("textOverrides"),
        text_anchors,
    )
    existing_button_overrides = block_props.get("buttonOverrides")
    if (
        component_name in _RUNTIME_PRESERVED_COMPONENT_NAMES
        and isinstance(existing_button_overrides, list)
        and existing_button_overrides
    ):
        block_props["buttonOverrides"] = deepcopy(existing_button_overrides)
    else:
        block_props["buttonOverrides"] = _merge_imported_runtime_button_overrides(
            existing_button_overrides,
            button_anchors,
        )
    block_props["imageOverrides"] = _merge_imported_runtime_image_overrides(
        block_props.get("imageOverrides"),
        image_anchors,
    )


def _extract_runtime_preserved_text_anchors(
    *,
    section_source: str,
    button_anchors: list[dict[str, str]],
) -> list[str]:
    button_labels = {
        str(anchor.get("label") or "").strip()
        for anchor in button_anchors
        if isinstance(anchor, dict) and str(anchor.get("label") or "").strip()
    }
    results: list[str] = []
    for candidate in _extract_text_candidates(section_source):
        normalized = str(candidate or "").strip()
        if (
            not normalized
            or normalized in button_labels
            or _looks_like_reference_text(normalized)
            or _looks_like_anchor_identifier_text(candidate=normalized, section_source=section_source)
            or _looks_like_image_alt_text(candidate=normalized, section_source=section_source)
        ):
            continue
        results.append(normalized)
    return _ordered_unique(results)


def _merge_refreshed_source_backed_block(
    *,
    existing_block: dict[str, Any],
    refreshed_block: dict[str, Any],
) -> dict[str, Any]:
    next_block = deepcopy(refreshed_block)
    next_props = next_block.get("props")
    existing_props = existing_block.get("props")
    if not isinstance(next_props, dict) or not isinstance(existing_props, dict):
        return next_block

    existing_id = str(existing_props.get("id") or "").strip()
    if existing_id:
        next_props["id"] = existing_id

    next_props["textSlots"] = _merge_refreshed_text_slots(
        existing_items=existing_props.get("textSlots"),
        refreshed_items=next_props.get("textSlots"),
    )
    next_props["buttonSlots"] = _merge_refreshed_button_slots(
        existing_items=existing_props.get("buttonSlots"),
        refreshed_items=next_props.get("buttonSlots"),
    )
    next_props["imageSlots"] = _merge_refreshed_image_slots(
        existing_items=existing_props.get("imageSlots"),
        refreshed_items=next_props.get("imageSlots"),
    )
    return next_block


def _merge_refreshed_text_slots(*, existing_items: Any, refreshed_items: Any) -> list[dict[str, Any]]:
    existing_by_anchor: dict[str, dict[str, Any]] = {}
    for item in existing_items if isinstance(existing_items, list) else []:
        if not isinstance(item, dict):
            continue
        anchor = str(item.get("originalText") or "").strip()
        if anchor:
            existing_by_anchor[anchor] = item

    merged: list[dict[str, Any]] = []
    for item in refreshed_items if isinstance(refreshed_items, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = deepcopy(item)
        anchor = str(normalized.get("originalText") or "").strip()
        existing = existing_by_anchor.get(anchor)
        if existing and isinstance(existing.get("text"), str):
            normalized["text"] = str(existing.get("text"))
        merged.append(normalized)
    return merged


def _merge_refreshed_button_slots(*, existing_items: Any, refreshed_items: Any) -> list[dict[str, Any]]:
    existing_by_anchor: dict[tuple[str, str], dict[str, Any]] = {}
    existing_by_text: dict[str, dict[str, Any]] = {}
    for item in existing_items if isinstance(existing_items, list) else []:
        if not isinstance(item, dict):
            continue
        original_text = str(item.get("originalText") or "").strip()
        href = str(item.get("href") or "").strip()
        if original_text:
            existing_by_anchor[(original_text, href)] = item
            existing_by_text.setdefault(original_text, item)

    merged: list[dict[str, Any]] = []
    for item in refreshed_items if isinstance(refreshed_items, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = deepcopy(item)
        original_text = str(normalized.get("originalText") or "").strip()
        href = str(normalized.get("href") or "").strip()
        existing = existing_by_anchor.get((original_text, href)) or existing_by_text.get(original_text)
        if existing and isinstance(existing.get("text"), str) and str(existing.get("text")).strip():
            normalized["text"] = str(existing.get("text")).strip()
        merged.append(normalized)
    return merged


def _merge_refreshed_image_slots(*, existing_items: Any, refreshed_items: Any) -> list[dict[str, Any]]:
    existing_by_anchor: dict[tuple[str, str], dict[str, Any]] = {}
    for item in existing_items if isinstance(existing_items, list) else []:
        if not isinstance(item, dict):
            continue
        original_src = str(item.get("originalSrc") or "").strip()
        original_text = str(item.get("originalText") or "").strip()
        if original_src or original_text:
            existing_by_anchor[(original_src, original_text)] = item

    merged: list[dict[str, Any]] = []
    for item in refreshed_items if isinstance(refreshed_items, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = deepcopy(item)
        original_src = str(normalized.get("originalSrc") or "").strip()
        original_text = str(normalized.get("originalText") or "").strip()
        existing = existing_by_anchor.get((original_src, original_text))
        if existing:
            src = str(existing.get("src") or "").strip()
            alt = str(existing.get("alt") or "").strip()
            if src:
                normalized["src"] = src
            if alt:
                normalized["alt"] = alt
        merged.append(normalized)
    return merged


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

    links = parsed_data.get("links") or []
    if isinstance(links, list):
        for index, value in enumerate(links, start=1):
            if not isinstance(value, dict):
                continue
            label = str(value.get("label") or "").strip()
            if label:
                labeled_candidates.append((f"Link label {index}", label))

    faqs = parsed_data.get("faqs") or []
    if isinstance(faqs, list):
        for index, faq in enumerate(faqs, start=1):
            if not isinstance(faq, dict):
                continue
            question = str(faq.get("question") or "").strip()
            answer = str(faq.get("answer") or "").strip()
            if question:
                labeled_candidates.append((f"FAQ {index} question", question))
            if answer:
                labeled_candidates.append((f"FAQ {index} answer", answer))

    comparisons = parsed_data.get("comparisons") or []
    if isinstance(comparisons, list) and comparisons:
        comparison_keys: list[str] = []
        first_row = comparisons[0]
        if isinstance(first_row, dict):
            comparison_keys = [
                str(key).strip()
                for key in first_row.keys()
                if str(key).strip() and key not in {"feature", "label", "title"}
            ]
            for index, key in enumerate(comparison_keys, start=1):
                labeled_candidates.append((f"Comparison column {index}", _humanize_identifier(key)))
        for row_index, comparison in enumerate(comparisons, start=1):
            if not isinstance(comparison, dict):
                continue
            feature = str(
                comparison.get("feature") or comparison.get("label") or comparison.get("title") or ""
            ).strip()
            if feature:
                labeled_candidates.append((f"Comparison row {row_index} feature", feature))
            for column_index, key in enumerate(comparison_keys, start=1):
                value = comparison.get(key)
                if isinstance(value, bool):
                    continue
                rendered_value = _stringify_comparison_value(value).strip()
                if rendered_value:
                    labeled_candidates.append(
                        (f"Comparison row {row_index} value {column_index}", rendered_value)
                    )

    if not labeled_candidates:
        for index, candidate in enumerate(section.get("keyText") or [], start=1):
            if isinstance(candidate, str) and candidate.strip() and not _looks_like_reference_text(candidate):
                labeled_candidates.append((f"Text {index}", candidate.strip()))

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, (label, candidate) in enumerate(labeled_candidates, start=1):
        if (
            candidate in button_texts
            or candidate in seen
            or _looks_like_reference_text(candidate)
        ):
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


def _merge_imported_runtime_text_overrides(
    existing_items: Any,
    text_anchors: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_anchors = {
        str(anchor).strip()
        for anchor in _ordered_unique(text_anchors)
        if isinstance(anchor, str) and str(anchor).strip()
    }

    for item in existing_items if isinstance(existing_items, list) else []:
        if not isinstance(item, dict):
            continue
        original_text = str(item.get("originalText") or "").strip()
        if not original_text or original_text in seen or original_text not in allowed_anchors:
            continue
        seen.add(original_text)
        normalized = deepcopy(item)
        normalized["originalText"] = original_text
        normalized["text"] = (
            str(item.get("text")).strip()
            if isinstance(item.get("text"), str) and str(item.get("text")).strip()
            else original_text
        )
        if not str(normalized.get("key") or "").strip():
            normalized["key"] = f"text-{len(results) + 1}"
        if not str(normalized.get("label") or "").strip():
            normalized["label"] = f"Text {len(results) + 1}"
        results.append(normalized)

    for anchor in _ordered_unique(text_anchors):
        original_text = str(anchor or "").strip()
        if not original_text or original_text in seen or _looks_like_reference_text(original_text):
            continue
        seen.add(original_text)
        results.append(
            {
                "key": f"text-{len(results) + 1}",
                "label": f"Text {len(results) + 1}",
                "originalText": original_text,
                "text": original_text,
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


def _merge_imported_runtime_button_overrides(
    existing_items: Any,
    button_anchors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    allowed_anchors = {
        (str(anchor.get("label") or "").strip(), str(anchor.get("href") or "").strip())
        for anchor in button_anchors
        if isinstance(anchor, dict) and str(anchor.get("label") or "").strip()
    }
    allowed_labels = {label for label, _ in allowed_anchors}

    for item in existing_items if isinstance(existing_items, list) else []:
        if not isinstance(item, dict):
            continue
        original_text = str(item.get("originalText") or "").strip()
        href = str(item.get("href") or "").strip()
        if (
            not original_text
            or (original_text, href) in seen
            or (
                (original_text, href) not in allowed_anchors
                and not ((original_text, "") in allowed_anchors or original_text in allowed_labels)
            )
        ):
            continue
        seen.add((original_text, href))
        normalized = deepcopy(item)
        normalized["originalText"] = original_text
        normalized["text"] = (
            str(item.get("text")).strip()
            if isinstance(item.get("text"), str) and str(item.get("text")).strip()
            else original_text
        )
        normalized["href"] = href
        if not str(normalized.get("key") or "").strip():
            normalized["key"] = f"button-{len(results) + 1}"
        if not str(normalized.get("label") or "").strip():
            normalized["label"] = f"Button {len(results) + 1}"
        results.append(normalized)

    for anchor in button_anchors:
        if not isinstance(anchor, dict):
            continue
        original_text = str(anchor.get("label") or "").strip()
        href = str(anchor.get("href") or "").strip()
        if not original_text or (original_text, href) in seen:
            continue
        seen.add((original_text, href))
        results.append(
            {
                "key": f"button-{len(results) + 1}",
                "label": f"Button {len(results) + 1}",
                "originalText": original_text,
                "text": original_text,
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
        if candidate in seen or _looks_like_non_asset_image_value(candidate):
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

    if not results and _section_matches_header(
        section_type=str(section.get("sectionType") or "generic_content").strip(),
        section_id=str(section.get("id") or "").strip().lower(),
        component_name=str(section.get("componentName") or "").strip().lower(),
        semantic_tokens={
            str(tag).strip().lower()
            for tag in (section.get("semanticTags") or [])
            if isinstance(tag, str) and tag.strip()
        },
    ):
        logo_text = _resolve_logo_text_candidate(section)
        if logo_text:
            results.append(
                {
                    "key": "image-logo-1",
                    "label": "Logo image",
                    "originalSrc": "",
                    "originalText": logo_text,
                    "src": "",
                    "alt": logo_text,
                }
            )
    return results


def _build_source_backed_section_block(*, section: dict[str, Any], runtime_source: str) -> dict[str, Any]:
    if not settings.SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED:
        return _build_legacy_source_backed_section_block(section=section)

    component_name = str(section.get("componentName") or "").strip() or "App"
    section_id = str(section.get("id") or "").strip()
    translation = _translate_source_backed_section(section=section, runtime_source=runtime_source)
    text_slots = translation.get("textSlots") or []
    button_slots = translation.get("buttonSlots") or []
    image_slots = translation.get("imageSlots") or []
    if not any((text_slots, button_slots, image_slots)):
        raise SiteImportArchiveError(
            "Archive import could not expose editable slots for source-backed section "
            f"'{section_id or section.get('displayName') or 'section'}'."
        )

    return _make_imported_block(
        str(translation.get("blockType") or "").strip() or _resolve_source_backed_section_block_type(section=section),
        sectionLabel=section.get("displayName") or _humanize_identifier(section_id or "Section"),
        componentName=component_name,
        sectionTargetId=section_id if component_name == "App" else "",
        textSlots=text_slots,
        buttonSlots=button_slots,
        imageSlots=image_slots,
    )


def _build_legacy_source_backed_section_block(*, section: dict[str, Any]) -> dict[str, Any]:
    component_name = str(section.get("componentName") or "").strip() or "App"
    section_id = str(section.get("id") or "").strip()
    text_slots = _normalize_legacy_imported_slot_items(_build_text_override_items(section=section))
    button_slots = _normalize_legacy_imported_slot_items(_build_button_override_items(section=section))
    image_slots = _normalize_legacy_imported_slot_items(_build_image_override_items(section=section))
    if not any((text_slots, button_slots, image_slots)):
        raise SiteImportArchiveError(
            "Archive import could not expose editable slots for source-backed section "
            f"'{section_id or section.get('displayName') or 'section'}'."
        )

    return _make_imported_block(
        _resolve_source_backed_section_block_type(section=section),
        sectionLabel=section.get("displayName") or _humanize_identifier(section_id or "Section"),
        componentName=component_name,
        sectionTargetId=section_id if component_name == "App" else "",
        textSlots=text_slots,
        buttonSlots=button_slots,
        imageSlots=image_slots,
    )


def _normalize_legacy_imported_slot_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cleaned = {
            key: value
            for key, value in item.items()
            if key in {"label", "originalText", "text", "href", "originalSrc", "src", "alt"}
        }
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _translate_source_backed_section(*, section: dict[str, Any], runtime_source: str) -> dict[str, Any]:
    section_id = str(section.get("id") or "").strip()
    display_name = str(section.get("displayName") or "").strip() or _humanize_identifier(section_id or "Section")
    component_name = str(section.get("componentName") or "").strip() or "App"
    block_type_hint = _resolve_source_backed_section_block_type(section=section)
    section_source, source_extraction_mode = _resolve_source_backed_section_source(
        section=section,
        runtime_source=runtime_source,
    )
    available_text_anchors = _extract_translation_text_anchors(section_source=section_source)
    available_button_anchors = _extract_translation_button_anchors(section_source=section_source)
    available_image_anchors = _extract_translation_image_anchors(
        section=section,
        section_source=section_source,
        text_anchors=available_text_anchors,
    )
    available_stat_pairs = _extract_translation_stat_pairs(section_source=section_source)
    available_faq_pairs = _extract_translation_faq_pairs(section_source=section_source)
    translation = translate_imported_source_section(
        section_id=section_id,
        display_name=display_name,
        component_name=component_name,
        section_type_hint=str(section.get("sectionType") or "generic_content").strip() or "generic_content",
        block_type_hint=block_type_hint,
        semantic_tags=[
            str(tag).strip()
            for tag in (section.get("semanticTags") or [])
            if isinstance(tag, str) and tag.strip()
        ],
        source_extraction_mode=source_extraction_mode,
        section_source=section_source,
        available_text_anchors=available_text_anchors,
        available_button_anchors=available_button_anchors,
        available_image_anchors=available_image_anchors,
        available_stat_pairs=available_stat_pairs,
        available_faq_pairs=available_faq_pairs,
    )
    translation = normalize_imported_section_translation(translation)
    translation = _sanitize_translated_source_backed_section(
        translation=translation,
        available_text_anchors=available_text_anchors,
        available_button_anchors=available_button_anchors,
        available_image_anchors=available_image_anchors,
    )
    _validate_translated_source_backed_section(
        section=section,
        section_source=section_source,
        translation=translation,
        available_text_anchors=available_text_anchors,
        available_button_anchors=available_button_anchors,
        available_image_anchors=available_image_anchors,
        available_stat_pairs=available_stat_pairs,
        available_faq_pairs=available_faq_pairs,
    )
    return translation


def _sanitize_translated_source_backed_section(
    *,
    translation: dict[str, Any],
    available_text_anchors: list[str],
    available_button_anchors: list[dict[str, str]],
    available_image_anchors: list[dict[str, str]],
) -> dict[str, Any]:
    sanitized = deepcopy(translation)
    allowed_text_anchor_set = {
        str(anchor).strip()
        for anchor in available_text_anchors
        if isinstance(anchor, str) and str(anchor).strip()
    }
    allowed_button_hrefs: dict[str, set[str]] = {}
    for anchor in available_button_anchors:
        if not isinstance(anchor, dict):
            continue
        label = str(anchor.get("label") or "").strip()
        href = str(anchor.get("href") or "").strip()
        if not label:
            continue
        allowed_button_hrefs.setdefault(label, set()).add(href)
    allowed_image_anchors = {
        (str(anchor.get("originalSrc") or "").strip(), str(anchor.get("originalText") or "").strip())
        for anchor in available_image_anchors
        if isinstance(anchor, dict)
        and (
            str(anchor.get("originalSrc") or "").strip()
            or str(anchor.get("originalText") or "").strip()
        )
    }

    cleaned_text_slots: list[dict[str, Any]] = []
    seen_text_anchors: set[str] = set()
    for entry in sanitized.get("textSlots") or []:
        if not isinstance(entry, dict):
            continue
        normalized = deepcopy(entry)
        original_text = str(normalized.get("originalText") or "").strip()
        if not original_text:
            continue
        resolved_anchors = (
            [original_text]
            if original_text in allowed_text_anchor_set
            else _split_composite_translation_anchor(
                original_text=original_text,
                allowed_text_anchors=list(allowed_text_anchor_set),
            )
        )
        if not resolved_anchors:
            continue
        for part_index, anchor in enumerate(resolved_anchors, start=1):
            if anchor in seen_text_anchors:
                continue
            part_slot = deepcopy(normalized)
            part_slot["originalText"] = anchor
            part_slot["text"] = anchor
            if len(resolved_anchors) > 1:
                base_label = str(normalized.get("label") or "").strip() or "Text"
                part_slot["label"] = _make_split_slot_label(
                    base_label=base_label,
                    part_index=part_index,
                    part_count=len(resolved_anchors),
                )
            seen_text_anchors.add(anchor)
            cleaned_text_slots.append(part_slot)

    cleaned_button_slots: list[dict[str, Any]] = []
    seen_button_anchors: set[tuple[str, str]] = set()
    for entry in sanitized.get("buttonSlots") or []:
        if not isinstance(entry, dict):
            continue
        normalized = deepcopy(entry)
        original_text = str(normalized.get("originalText") or "").strip()
        href = str(normalized.get("href") or "").strip()
        allowed_hrefs = allowed_button_hrefs.get(original_text)
        if not original_text or not allowed_hrefs:
            continue
        if href not in allowed_hrefs:
            if len(allowed_hrefs) == 1:
                href = next(iter(allowed_hrefs))
            elif "" in allowed_hrefs:
                href = ""
            else:
                continue
            normalized["href"] = href
        anchor_key = (original_text, href)
        if anchor_key in seen_button_anchors:
            continue
        seen_button_anchors.add(anchor_key)
        cleaned_button_slots.append(normalized)

    cleaned_image_slots: list[dict[str, Any]] = []
    seen_image_anchors: set[tuple[str, str]] = set()
    for entry in sanitized.get("imageSlots") or []:
        if not isinstance(entry, dict):
            continue
        normalized = deepcopy(entry)
        original_src = str(normalized.get("originalSrc") or "").strip()
        original_text = str(normalized.get("originalText") or "").strip()
        anchor_key = (original_src, original_text)
        if anchor_key not in allowed_image_anchors or anchor_key in seen_image_anchors:
            continue
        seen_image_anchors.add(anchor_key)
        cleaned_image_slots.append(normalized)

    sanitized["textSlots"] = cleaned_text_slots
    sanitized["buttonSlots"] = cleaned_button_slots
    sanitized["imageSlots"] = cleaned_image_slots
    return sanitized


def _resolve_source_backed_section_source(*, section: dict[str, Any], runtime_source: str) -> tuple[str, str]:
    normalized_runtime_source = str(runtime_source or "").strip()
    if not normalized_runtime_source:
        raise SiteImportArchiveError(
            "Archive import cannot translate source-backed sections without shared runtime source."
        )

    component_name = str(section.get("componentName") or "").strip()
    if component_name and component_name != "App":
        component_source = _extract_named_component_source(normalized_runtime_source, component_name)
        if component_source and component_source.strip():
            return _trim_source_to_target_section(
                source=component_source.strip(),
                section_id=str(section.get("id") or "").strip(),
            ), "exact_component"

    section_id = str(section.get("id") or "").strip()
    if section_id:
        anchor = f'data-section-id="{section_id}"'
        anchor_index = normalized_runtime_source.find(anchor)
        if anchor_index >= 0:
            _, snippet = _extract_section_source(normalized_runtime_source, anchor_index)
            if snippet.strip():
                return _trim_source_to_target_section(
                    source=snippet.strip(),
                    section_id=section_id,
                ), "anchored_snippet"

    raise SiteImportArchiveError(
        "Archive import could not resolve section source for source-backed section "
        f"'{section_id or section.get('displayName') or component_name or 'section'}'."
    )


def _validate_translated_source_backed_section(
    *,
    section: dict[str, Any],
    section_source: str,
    translation: dict[str, Any],
    available_text_anchors: list[str],
    available_button_anchors: list[dict[str, str]],
    available_image_anchors: list[dict[str, str]],
    available_stat_pairs: list[dict[str, str]],
    available_faq_pairs: list[dict[str, str]],
) -> None:
    block_type = str(translation.get("blockType") or "").strip()
    if block_type not in {
        "ImportedHeaderSection",
        "ImportedHeroSection",
        "ImportedProofBarSection",
        "ImportedFeatureSection",
        "ImportedOfferSection",
        "ImportedTestimonialsSection",
        "ImportedComparisonSection",
        "ImportedFaqSection",
        "ImportedFooterSection",
    }:
        raise SiteImportArchiveError(
            "Archive import Gemini translation returned an invalid source-backed block type "
            f"for section '{section.get('id') or section.get('displayName') or 'section'}': {block_type or '<empty>'}."
        )

    available_text_anchor_set = {
        str(value).strip()
        for value in available_text_anchors
        if isinstance(value, str) and str(value).strip()
    }
    available_button_anchor_set = {
        (str(entry.get("label") or "").strip(), str(entry.get("href") or "").strip())
        for entry in available_button_anchors
        if isinstance(entry, dict) and str(entry.get("label") or "").strip()
    }
    available_image_srcs = {
        str(entry.get("originalSrc") or "").strip()
        for entry in available_image_anchors
        if isinstance(entry, dict) and str(entry.get("originalSrc") or "").strip()
    }
    available_image_texts = {
        str(entry.get("originalText") or "").strip()
        for entry in available_image_anchors
        if isinstance(entry, dict) and str(entry.get("originalText") or "").strip()
    }
    text_slots = translation.get("textSlots") or []
    button_slots = translation.get("buttonSlots") or []
    image_slots = translation.get("imageSlots") or []

    def ensure_present(value: str, *, kind: str, allowed_values: set[str]) -> None:
        stripped = str(value or "").strip()
        if not stripped:
            raise SiteImportArchiveError(
                "Archive import Gemini translation returned an empty "
                f"{kind} anchor for section '{section.get('id') or section.get('displayName') or 'section'}'."
            )
        if stripped not in allowed_values:
            raise SiteImportArchiveError(
                "Archive import Gemini translation returned a "
                f"{kind} anchor not present in allowed section anchors for section "
                f"'{section.get('id') or section.get('displayName') or 'section'}': {stripped!r}."
            )

    for entry in text_slots:
        if not isinstance(entry, dict):
            raise SiteImportArchiveError("Archive import Gemini translation returned a non-object text slot.")
        ensure_present(
            str(entry.get("originalText") or ""),
            kind="text",
            allowed_values=available_text_anchor_set,
        )
    for entry in button_slots:
        if not isinstance(entry, dict):
            raise SiteImportArchiveError("Archive import Gemini translation returned a non-object button slot.")
        original_text = str(entry.get("originalText") or "").strip()
        href = str(entry.get("href") or "").strip()
        if not original_text:
            raise SiteImportArchiveError("Archive import Gemini translation returned a button slot without originalText.")
        if (original_text, href) not in available_button_anchor_set and (original_text, "") not in available_button_anchor_set:
            raise SiteImportArchiveError(
                "Archive import Gemini translation returned a button anchor not present in allowed section anchors for section "
                f"'{section.get('id') or section.get('displayName') or 'section'}': {(original_text, href)!r}."
            )
    for entry in image_slots:
        if not isinstance(entry, dict):
            raise SiteImportArchiveError("Archive import Gemini translation returned a non-object image slot.")
        original_src = str(entry.get("originalSrc") or "").strip()
        original_text = str(entry.get("originalText") or "").strip()
        if original_src:
            ensure_present(original_src, kind="image", allowed_values=available_image_srcs)
        elif original_text:
            ensure_present(original_text, kind="image", allowed_values=available_image_texts)
        else:
            raise SiteImportArchiveError("Archive import Gemini translation returned an image slot without an anchor.")

    translated_texts = {
        str(entry.get("originalText") or "").strip()
        for entry in text_slots
        if isinstance(entry, dict) and str(entry.get("originalText") or "").strip()
    }
    missing_stat_values = [
        pair["percent"]
        for pair in available_stat_pairs
        if str(pair.get("percent") or "").strip() and str(pair.get("percent") or "").strip() not in translated_texts
    ]
    missing_stat_descriptions = [
        pair["description"]
        for pair in available_stat_pairs
        if str(pair.get("description") or "").strip()
        and str(pair.get("description") or "").strip() not in translated_texts
    ]
    if missing_stat_values or missing_stat_descriptions:
        raise SiteImportArchiveError(
            "Archive import Gemini translation failed to expose all stat pairs for section "
            f"'{section.get('id') or section.get('displayName') or 'section'}': "
            + ", ".join([*missing_stat_values, *missing_stat_descriptions])
        )

    missing_faq_questions = [
        pair["question"]
        for pair in available_faq_pairs
        if str(pair.get("question") or "").strip() and str(pair.get("question") or "").strip() not in translated_texts
    ]
    missing_faq_answers = [
        pair["answer"]
        for pair in available_faq_pairs
        if str(pair.get("answer") or "").strip() and str(pair.get("answer") or "").strip() not in translated_texts
    ]
    if missing_faq_questions or missing_faq_answers:
        raise SiteImportArchiveError(
            "Archive import Gemini translation failed to expose all FAQ pairs for section "
            f"'{section.get('id') or section.get('displayName') or 'section'}': "
            + ", ".join([*missing_faq_questions, *missing_faq_answers])
        )


def _extract_translation_text_anchors(*, section_source: str) -> list[str]:
    results = [
        candidate
        for candidate in _extract_text_candidates(section_source)
        if isinstance(candidate, str) and candidate.strip() and not _looks_like_reference_text(candidate)
    ]
    results.extend(_extract_translation_array_text_candidates(section_source=section_source))
    for pair in _extract_translation_stat_pairs(section_source=section_source):
        percent = str(pair.get("percent") or "").strip()
        description = str(pair.get("description") or "").strip()
        if percent:
            results.append(percent)
        if description:
            results.append(description)
    for pair in _extract_translation_faq_pairs(section_source=section_source):
        question = str(pair.get("question") or "").strip()
        answer = str(pair.get("answer") or "").strip()
        if question:
            results.append(question)
        if answer:
            results.append(answer)
    for inner_html in re.findall(r"<(?:span|div)[^>]*>(.*?)</(?:span|div)>", section_source, re.DOTALL):
        normalized = _normalize_markup_text(inner_html)
        if normalized and not _looks_like_reference_text(normalized):
            results.append(normalized)
    for candidate in re.findall(r"\d+%", section_source):
        stripped = candidate.strip()
        if stripped:
            results.append(stripped)
    for _, label in re.findall(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', section_source, re.DOTALL):
        normalized = _normalize_markup_text(label)
        if normalized and not _looks_like_reference_text(normalized):
            results.append(normalized)
    results.extend(_expand_compound_text_candidates(results))
    return _ordered_unique(results)


def _extract_translation_array_text_candidates(*, section_source: str) -> list[str]:
    results: list[str] = []
    for variable_name, payload in _extract_js_arrays(section_source).items():
        classified = _classify_array_payload(variable_name=variable_name, payload=payload)
        for key, value in classified.items():
            if key in {"checklist", "badges", "strings"} and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        normalized = " ".join(item.strip().split())
                        if normalized and _looks_like_human_text(normalized):
                            results.append(normalized)
                continue
            if key == "faqs" and isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    for field_name in ("question", "answer"):
                        normalized = " ".join(str(item.get(field_name) or "").strip().split())
                        if normalized and _looks_like_human_text(normalized):
                            results.append(normalized)
                continue
            if key == "comparisons" and isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    for field_name, field_value in item.items():
                        if field_name in {"feature", "label", "title"} and isinstance(field_value, str):
                            normalized = " ".join(field_value.strip().split())
                            if normalized and _looks_like_human_text(normalized):
                                results.append(normalized)
                continue
            if key == "stats" and isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    for field_name in ("percent", "value", "description", "label", "title", "name"):
                        normalized = " ".join(str(item.get(field_name) or "").strip().split())
                        if normalized and _looks_like_human_text(normalized):
                            results.append(normalized)
                continue
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    for field_value in item.values():
                        if isinstance(field_value, str):
                            normalized = " ".join(field_value.strip().split())
                            if normalized and _looks_like_human_text(normalized):
                                results.append(normalized)
    return _ordered_unique(results)


def _expand_compound_text_candidates(candidates: list[str]) -> list[str]:
    normalized_candidates = [
        str(candidate).strip()
        for candidate in candidates
        if isinstance(candidate, str) and str(candidate).strip()
    ]
    results: list[str] = []
    for candidate in normalized_candidates:
        for other in normalized_candidates:
            if other == candidate or len(other) >= len(candidate):
                continue
            if candidate.startswith(f"{other} "):
                remainder = candidate[len(other) :].strip(" |:-")
                if _looks_like_human_text(remainder):
                    results.append(remainder)
            if candidate.endswith(f" {other}"):
                remainder = candidate[: -len(other)].strip(" |:-")
                if _looks_like_human_text(remainder):
                    results.append(remainder)
    return _ordered_unique(results)


def _extract_translation_button_anchors(*, section_source: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for action in _extract_buttons(section_source):
        label = str(action.get("label") or "").strip()
        href = str(action.get("href") or "").strip()
        if not label:
            continue
        key = (label, href)
        if key in seen:
            continue
        seen.add(key)
        results.append({"label": label, "href": href})
    return results


def _split_composite_translation_anchor(
    *,
    original_text: str,
    allowed_text_anchors: list[str],
) -> list[str] | None:
    normalized_target = " ".join(str(original_text or "").split())
    if not normalized_target:
        return None

    normalized_anchors = [
        (" ".join(anchor.split()), anchor)
        for anchor in allowed_text_anchors
        if isinstance(anchor, str) and anchor.strip()
    ]

    def _search(remainder: str, *, depth: int) -> list[str] | None:
        if not remainder:
            return []
        if depth >= 4:
            return None
        for normalized_anchor, raw_anchor in normalized_anchors:
            if remainder == normalized_anchor:
                return [raw_anchor]
            if not remainder.startswith(f"{normalized_anchor} "):
                continue
            tail = remainder[len(normalized_anchor) :].strip()
            suffix = _search(tail, depth=depth + 1)
            if suffix is not None:
                return [raw_anchor, *suffix]
        return None

    resolved = _search(normalized_target, depth=0)
    if resolved and len(resolved) > 1:
        return resolved
    return None


def _make_split_slot_label(*, base_label: str, part_index: int, part_count: int) -> str:
    return f"{base_label} part {part_index} of {part_count}"


def _extract_translation_image_anchors(
    *,
    section: dict[str, Any],
    section_source: str,
    text_anchors: list[str],
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen_srcs: set[str] = set()
    for candidate in _ordered_unique(_URL_RE.findall(section_source)):
        if candidate in seen_srcs or _looks_like_non_asset_image_value(candidate):
            continue
        seen_srcs.add(candidate)
        results.append({"originalSrc": candidate, "originalText": ""})

    if _section_matches_header(
        section_type=str(section.get("sectionType") or "generic_content").strip(),
        section_id=str(section.get("id") or "").strip().lower(),
        component_name=str(section.get("componentName") or "").strip().lower(),
        semantic_tokens={
            str(tag).strip().lower()
            for tag in (section.get("semanticTags") or [])
            if isinstance(tag, str) and tag.strip()
        },
    ):
        logo_text = _resolve_logo_text_candidate_from_text_anchors(text_anchors)
        if logo_text:
            results.append({"originalSrc": "", "originalText": logo_text})
    return results


def _merge_imported_runtime_image_overrides(
    existing_items: Any,
    image_anchors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    allowed_anchors = {
        (str(anchor.get("originalSrc") or "").strip(), str(anchor.get("originalText") or "").strip())
        for anchor in image_anchors
        if isinstance(anchor, dict)
        and (
            str(anchor.get("originalSrc") or "").strip()
            or str(anchor.get("originalText") or "").strip()
        )
    }

    for item in existing_items if isinstance(existing_items, list) else []:
        if not isinstance(item, dict):
            continue
        original_src = str(item.get("originalSrc") or "").strip()
        original_text = str(item.get("originalText") or "").strip()
        if not original_src and not original_text:
            continue
        key = (original_src, original_text)
        if key in seen or key not in allowed_anchors:
            continue
        seen.add(key)
        normalized = deepcopy(item)
        normalized["originalSrc"] = original_src
        if original_text:
            normalized["originalText"] = original_text
        if not str(normalized.get("key") or "").strip():
            normalized["key"] = f"image-{len(results) + 1}"
        if not str(normalized.get("label") or "").strip():
            normalized["label"] = f"Image {len(results) + 1}"
        normalized["src"] = (
            str(item.get("src")).strip()
            if isinstance(item.get("src"), str) and str(item.get("src")).strip()
            else original_src
        )
        normalized["alt"] = str(item.get("alt") or "")
        results.append(normalized)

    for anchor in image_anchors:
        if not isinstance(anchor, dict):
            continue
        original_src = str(anchor.get("originalSrc") or "").strip()
        original_text = str(anchor.get("originalText") or "").strip()
        if not original_src and not original_text:
            continue
        key = (original_src, original_text)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "key": f"image-{len(results) + 1}",
                "label": f"Image {len(results) + 1}",
                "originalSrc": original_src,
                "originalText": original_text,
                "src": original_src,
                "alt": "",
            }
        )

    return results


def _extract_translation_stat_pairs(*, section_source: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for percent, description in re.findall(
        r'percent\s*:\s*"([^"]+)"\s*,\s*description\s*:\s*"([^"]+)"',
        section_source,
        re.DOTALL,
    ):
        normalized_percent = str(percent or "").strip()
        normalized_description = str(description or "").strip()
        if not normalized_percent or not normalized_description:
            continue
        results.append(
            {
                "percent": normalized_percent,
                "description": normalized_description,
            }
        )
    return results


def _extract_translation_faq_pairs(*, section_source: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for question, answer in re.findall(
        r'question\s*:\s*"([^"]+)"\s*,\s*answer\s*:\s*"([^"]+)"',
        section_source,
        re.DOTALL,
    ):
        normalized_question = str(question or "").strip()
        normalized_answer = str(answer or "").strip()
        if not normalized_question or not normalized_answer:
            continue
        results.append(
            {
                "question": normalized_question,
                "answer": normalized_answer,
            }
        )
    return results


def _resolve_logo_text_candidate_from_text_anchors(candidates: list[str]) -> str | None:
    preferred = [
        candidate.strip()
        for candidate in candidates
        if isinstance(candidate, str)
        and candidate.strip()
        and len(candidate.strip().split()) <= 3
        and len(candidate.strip()) <= 24
        and not _looks_like_cta(candidate.strip())
    ]
    if not preferred:
        return None
    exact_upper = [candidate for candidate in preferred if candidate.upper() == candidate]
    if exact_upper:
        exact_upper.sort(key=lambda candidate: (len(candidate.split()), len(candidate)))
        return exact_upper[0]
    preferred.sort(key=lambda candidate: (len(candidate.split()), len(candidate)))
    return preferred[0]


def _trim_source_to_target_section(*, source: str, section_id: str) -> str:
    if not source.strip() or not section_id.strip():
        return source
    anchor = f'data-section-id="{section_id}"'
    anchor_index = source.find(anchor)
    if anchor_index < 0:
        return source
    next_anchor_index = source.find('data-section-id="', anchor_index + len(anchor))
    if next_anchor_index < 0:
        return source
    return source[:next_anchor_index].rstrip()


def _resolve_source_backed_section_block_type(*, section: dict[str, Any]) -> str:
    section_type = str(section.get("sectionType") or "generic_content").strip()
    section_id = str(section.get("id") or "").strip().lower()
    component_name = str(section.get("componentName") or "").strip().lower()
    semantic_tokens = {
        str(tag).strip().lower()
        for tag in (section.get("semanticTags") or [])
        if isinstance(tag, str) and tag.strip()
    }

    if _section_matches_header(
        section_type=section_type,
        section_id=section_id,
        component_name=component_name,
        semantic_tokens=semantic_tokens,
    ):
        return "ImportedHeaderSection"
    if _section_matches_footer(
        section_type=section_type,
        section_id=section_id,
        component_name=component_name,
        semantic_tokens=semantic_tokens,
    ):
        return "ImportedFooterSection"
    if section_type == "hero" or "hero" in section_id or "hero" in component_name or "hero" in semantic_tokens:
        return "ImportedHeroSection"
    if (
        section_type == "proof_bar"
        or "proof" in section_id
        or "marquee" in section_id
        or "proof_bar" in semantic_tokens
    ):
        return "ImportedProofBarSection"
    if (
        section_type == "testimonial_wall"
        or "testimonial" in section_id
        or "testimonial_wall" in semantic_tokens
    ):
        return "ImportedTestimonialsSection"
    if (
        section_type == "comparison_table"
        or "comparison" in section_id
        or "comparison_table" in semantic_tokens
    ):
        return "ImportedComparisonSection"
    if section_type == "faq" or "faq" in section_id or "faq" in semantic_tokens:
        return "ImportedFaqSection"
    if section_type in {"bundle_selector", "sticky_offer_rail"}:
        return "ImportedOfferSection"
    return "ImportedFeatureSection"


def _section_matches_header(
    *,
    section_type: str,
    section_id: str,
    component_name: str,
    semantic_tokens: set[str],
) -> bool:
    if section_type == "header":
        return True
    if "header" in section_id or component_name.endswith("header") or component_name == "header":
        return True
    return bool({"header", "navigation", "nav"} & semantic_tokens)


def _section_matches_footer(
    *,
    section_type: str,
    section_id: str,
    component_name: str,
    semantic_tokens: set[str],
) -> bool:
    if section_type == "footer":
        return True
    if "footer" in section_id or component_name.endswith("footer") or component_name == "footer":
        return True
    return bool({"footer", "legal"} & semantic_tokens)


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
    parsed_data = section.get("parsedData") or {}
    links = parsed_data.get("links") or []
    for link in links:
        if not isinstance(link, dict):
            continue
        label = str(link.get("label") or "").strip()
        if label and not _looks_like_cta(label):
            return label
    for candidate in section.get("keyText") or []:
        if not isinstance(candidate, str):
            continue
        stripped = candidate.strip()
        if stripped.isupper() and len(stripped.split()) <= 2 and len(stripped) <= 20:
            return stripped
    display_name = str(section.get("displayName") or "").strip()
    return display_name.split()[0].upper() if display_name else ""


def _extract_imported_page_shared_runtime_source(puck_data: dict[str, Any] | None) -> str | None:
    if not isinstance(puck_data, dict):
        return None
    content = puck_data.get("content")
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "ImportedPage":
        return None
    props = first.get("props")
    if not isinstance(props, dict):
        return None
    runtime_source = props.get("sharedRuntimeSource")
    if isinstance(runtime_source, str) and runtime_source.strip():
        return runtime_source
    return None


def _extract_imported_page_shared_head_assets(
    puck_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(puck_data, dict):
        return None
    content = puck_data.get("content")
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "ImportedPage":
        return None
    props = first.get("props")
    if not isinstance(props, dict):
        return None
    head_assets = props.get("sharedHeadAssets")
    if isinstance(head_assets, dict) and head_assets:
        return head_assets
    return None


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


def _looks_like_reference_text(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return True
    if stripped.startswith("#") and not re.search(r"\s", stripped):
        return True
    return bool(_URL_RE.fullmatch(stripped))


def _looks_like_anchor_identifier_text(*, candidate: str, section_source: str) -> bool:
    stripped = (candidate or "").strip()
    if not stripped or not re.fullmatch(r"[a-z0-9-]+", stripped):
        return False
    return any(
        marker in section_source
        for marker in (
            f'href="#{stripped}"',
            f"id=\"{stripped}\"",
            f"href='#{stripped}'",
            f"id='{stripped}'",
        )
    )


def _looks_like_image_alt_text(*, candidate: str, section_source: str) -> bool:
    stripped = (candidate or "").strip()
    if not stripped:
        return False
    return any(
        marker in section_source
        for marker in (
            f'alt="{stripped}"',
            f"alt='{stripped}'",
        )
    )


def _looks_like_non_asset_image_value(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return True
    if stripped == "http://www.w3.org/2000/svg":
        return True
    return False


def _resolve_logo_text_candidate(section: dict[str, Any]) -> str | None:
    parsed_data = section.get("parsedData") or {}
    links = parsed_data.get("links") or []
    for link in links:
        if not isinstance(link, dict):
            continue
        label = str(link.get("label") or "").strip()
        if label and not _looks_like_cta(label) and not _looks_like_reference_text(label):
            return label
    for candidate in section.get("keyText") or []:
        if not isinstance(candidate, str):
            continue
        stripped = candidate.strip()
        if not stripped or _looks_like_cta(stripped) or _looks_like_reference_text(stripped):
            continue
        if len(stripped.split()) <= 4:
            return stripped
    return None
