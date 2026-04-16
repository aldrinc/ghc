"""Shared prompt helpers for validated-loop agents.

Role-specific prompt text lives in:
- loop/analyzer_prompt.py
- loop/validator_prompt.py
- loop/executor_prompt.py
"""

import json
from html.parser import HTMLParser
import re
from typing import cast

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from loop.contracts import (
    BlueprintValidationIssue,
    BlueprintValidationReport,
    DesignSystemPreflight,
    DesignTokenSet,
    InteractionCheckpoint,
    LiveReferenceDomEvidenceCatalog,
    LiveReferenceDomEvidenceItem,
    LiveReferenceDomRelationship,
    LiveReferenceContext,
    ReferenceBundle,
    RequirementsSpec,
    SectionRequirement,
    SectionValidationResult,
    ValidationIssue,
    ValidationReport,
    WrapperRequirement,
)

MAX_REQUIREMENTS_TEXT_CHARS = 500
MAX_REQUIREMENTS_SUMMARY_CHARS = 1_000
MAX_REQUIREMENTS_LIST_ITEMS = 10
MAX_SECTION_COUNT = 8
MAX_SECTION_LIST_ITEMS = 6
MAX_ISSUE_COUNT = 8
MAX_PATCH_INSTRUCTION_COUNT = 10
MAX_CURRENT_HTML_CHARS = 20_000
MAX_LIVE_REFERENCE_JSON_CHARS = 60_000
MAX_OUTLINE_JSON_CHARS = 40_000


class _HtmlLandmarkParser(HTMLParser):
    def __init__(self, *, max_items: int) -> None:
        super().__init__(convert_charrefs=True)
        self._max_items = max_items
        self._stack: list[dict[str, object]] = []
        self.landmarks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        class_names: list[str] = []
        data_attrs: list[str] = []
        attr_map: dict[str, str] = {}

        for name, raw_value in attrs:
            value = (raw_value or "").strip()
            attr_map[name] = value
            if name == "class" and value:
                class_names = [part for part in value.split() if part][:3]
            if name.startswith("data-"):
                data_attrs.append(
                    f'{name}="{_truncate_text(value, 60)}"' if value else name
                )

        is_interesting = bool(
            attr_map.get("id")
            or class_names
            or data_attrs
            or attr_map.get("role")
            or tag
            in {
                "header",
                "nav",
                "main",
                "section",
                "footer",
                "button",
                "a",
                "form",
                "input",
                "textarea",
                "dialog",
            }
        )

        self._stack.append(
            {
                "tag": tag,
                "id": attr_map.get("id", ""),
                "classes": class_names,
                "data_attrs": data_attrs[:2],
                "role": attr_map.get("role", ""),
                "text": "",
                "interesting": is_interesting,
            }
        )

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return

        for entry in reversed(self._stack):
            if entry["interesting"] and not entry["text"]:
                entry["text"] = _truncate_text(text, 90)
                return

    def handle_endtag(self, tag: str) -> None:
        if not self._stack or len(self.landmarks) >= self._max_items:
            return

        entry = self._stack.pop()
        landmark = self._format_landmark(entry)
        if landmark and landmark not in self.landmarks:
            self.landmarks.append(landmark)

    @staticmethod
    def _format_landmark(entry: dict[str, object]) -> str | None:
        if not entry["interesting"]:
            return None

        tag = str(entry["tag"])
        parts = [f"<{tag}>"]

        element_id = str(entry["id"])
        if element_id:
            parts.append(f"#{element_id}")

        class_names = cast(list[str], entry["classes"])
        if class_names:
            parts.append("".join(f".{class_name}" for class_name in class_names))

        data_attrs = cast(list[str], entry["data_attrs"])
        if data_attrs:
            parts.append(" ".join(f"[{name}]" for name in data_attrs))

        role = str(entry["role"])
        if role:
            parts.append(f'role="{role}"')

        text = str(entry["text"])
        if text:
            parts.append(f'text="{text}"')

        return " ".join(parts)


def reference_summary(reference_bundle: ReferenceBundle) -> str:
    lines = [
        f"Input mode: {reference_bundle.input_mode}",
        f"User request: {reference_bundle.user_text or '(none provided)'}",
        f"Image count: {len(reference_bundle.images)}",
        f"Video count: {len(reference_bundle.videos)}",
    ]

    if reference_bundle.reference_url:
        lines.append(f"Live reference URL: {reference_bundle.reference_url}")

    if reference_bundle.live_reference is not None:
        lines.append(
            f"Live browser renders: {len(reference_bundle.live_reference.renders)}"
        )
    if reference_bundle.design_system_preflight is not None:
        lines.append("Required design-system preflight: ready")

    return "\n".join(lines)


def summarize_live_reference_for_prompt(live_reference: LiveReferenceContext) -> str:
    full_dom_landmarks = live_reference.design_system.dom_landmarks
    full_section_inventory = live_reference.design_system.section_inventory
    full_chrome_layers = live_reference.design_system.chrome_layers
    full_heading_hierarchy = live_reference.design_system.heading_hierarchy
    full_shell_relationships = live_reference.design_system.shell_relationships
    full_asset_inventory = live_reference.design_system.asset_inventory

    payload: dict[str, object] = {
        "url": live_reference.url,
        "page_title": _truncate_text(
            live_reference.design_system.page_title,
            160,
        ),
        "full_dom_html_chars": len(live_reference.full_dom_html.strip()),
        "render_labels": [
            _truncate_text(render.label, 80) for render in live_reference.renders[:6]
        ],
        "design_system": {
            "typography": _truncate_list(
                live_reference.design_system.typography,
                max_items=10,
                max_chars=180,
            ),
            "colors": _truncate_list(
                live_reference.design_system.colors,
                max_items=12,
                max_chars=160,
            ),
            "spacing": _truncate_list(
                live_reference.design_system.spacing,
                max_items=10,
                max_chars=160,
            ),
            "radii": _truncate_list(
                live_reference.design_system.radii,
                max_items=8,
                max_chars=160,
            ),
            "shadows": _truncate_list(
                live_reference.design_system.shadows,
                max_items=8,
                max_chars=180,
            ),
            "layout": _truncate_list(
                live_reference.design_system.layout,
                max_items=12,
                max_chars=320,
            ),
            "components": _truncate_list(
                live_reference.design_system.components,
                max_items=12,
                max_chars=320,
            ),
            "asset_inventory": _truncate_list(
                full_asset_inventory,
                max_items=max(12, len(full_asset_inventory)),
                max_chars=340,
            ),
            "dom_landmarks": _truncate_list(
                full_dom_landmarks,
                max_items=max(12, len(full_dom_landmarks)),
                max_chars=320,
            ),
            "section_inventory": _truncate_list(
                full_section_inventory,
                max_items=max(12, len(full_section_inventory)),
                max_chars=340,
            ),
            "chrome_layers": _truncate_list(
                full_chrome_layers,
                max_items=max(12, len(full_chrome_layers)),
                max_chars=320,
            ),
            "heading_hierarchy": _truncate_list(
                full_heading_hierarchy,
                max_items=max(14, len(full_heading_hierarchy)),
                max_chars=320,
            ),
            "shell_relationships": _truncate_list(
                full_shell_relationships,
                max_items=max(12, len(full_shell_relationships)),
                max_chars=320,
            ),
            "dom_evidence": _summarize_dom_evidence_for_prompt(
                live_reference.design_system.dom_evidence
            ),
            "raw_observations": _truncate_list(
                live_reference.design_system.raw_observations,
                max_items=12,
                max_chars=260,
            ),
        },
    }
    return truncate_json_context(
        json.dumps(payload, indent=2), max_chars=MAX_LIVE_REFERENCE_JSON_CHARS
    )


def full_live_dom_for_prompt(full_dom_html: str) -> str:
    normalized = full_dom_html.strip()
    if not normalized:
        return "(no full live DOM snapshot available)"
    return _normalize_full_dom_for_prompt(normalized)


def _normalize_full_dom_for_prompt(full_dom_html: str) -> str:
    soup = BeautifulSoup(full_dom_html, "html.parser")
    lines: list[str] = []

    removed_counts = {
        "script": 0,
        "style": 0,
        "noscript": 0,
        "template": 0,
    }
    for tag_name in removed_counts:
        for node in soup.find_all(tag_name):
            removed_counts[tag_name] += 1
            node.decompose()

    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()

    node_count = len(soup.find_all(True))
    removed_summary = ", ".join(
        f"{name}={count}" for name, count in removed_counts.items() if count
    )
    lines.append(
        "Normalized full DOM snapshot "
        f"(element_count={node_count}"
        + (f", removed={removed_summary}" if removed_summary else "")
        + ")"
    )

    root_nodes = [child for child in soup.contents if _should_emit_dom_node(child)]
    for child in root_nodes:
        _append_dom_node(child, lines, depth=0)

    return "\n".join(lines)


def _should_emit_dom_node(node: object) -> bool:
    if isinstance(node, Tag):
        return True
    if isinstance(node, NavigableString):
        return bool(_normalize_dom_text(str(node)))
    return False


def _append_dom_node(node: object, lines: list[str], *, depth: int) -> None:
    indent = "  " * depth
    if isinstance(node, NavigableString):
        text = _normalize_dom_text(str(node))
        if text:
            lines.append(f'{indent}#text "{_truncate_text(text, 180)}"')
        return

    if not isinstance(node, Tag):
        return

    attrs = _format_dom_attrs(node)
    direct_text = _normalize_dom_direct_text(node)
    opening = f"<{node.name}"
    if attrs:
        opening += f" {attrs}"
    if direct_text:
        opening += f' text="{_truncate_text(direct_text, 180)}"'
    opening += ">"
    lines.append(f"{indent}{opening}")

    for child in node.children:
        if _should_emit_dom_node(child):
            _append_dom_node(child, lines, depth=depth + 1)


def _format_dom_attrs(node: Tag) -> str:
    preferred_order = [
        "id",
        "class",
        "role",
        "href",
        "src",
        "alt",
        "aria-label",
        "aria-labelledby",
        "type",
        "name",
        "placeholder",
        "title",
        "value",
        "data-section-id",
        "data-wrapper-id",
    ]
    attrs: list[str] = []
    seen: set[str] = set()

    def append_attr(name: str, raw_value: object) -> None:
        if name in seen:
            return
        seen.add(name)
        value = _normalize_dom_attr_value(name, raw_value)
        if value:
            attrs.append(f'{name}="{value}"')

    for name in preferred_order:
        if name in node.attrs:
            append_attr(name, node.attrs.get(name))

    data_attr_names = sorted(
        name
        for name in node.attrs.keys()
        if isinstance(name, str)
        and name.startswith("data-")
        and name not in seen
    )
    for name in data_attr_names[:6]:
        append_attr(name, node.attrs.get(name))

    return " ".join(attrs)


def _normalize_dom_attr_value(name: str, raw_value: object) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, list):
        value = " ".join(str(part) for part in raw_value if str(part).strip())
    else:
        value = str(raw_value)
    value = " ".join(value.split())
    if not value:
        return ""

    if name == "class":
        classes = value.split()
        return _truncate_text(" ".join(classes[:8]), 120)

    if value.startswith("data:"):
        return "[data-url]"
    if len(value) > 180:
        return _truncate_text(value, 180)
    return value


def _normalize_dom_direct_text(node: Tag) -> str:
    texts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            normalized = _normalize_dom_text(str(child))
            if normalized:
                texts.append(normalized)
    return " ".join(texts[:3])


def _normalize_dom_text(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized


def _summarize_dom_evidence_for_prompt(
    dom_evidence: LiveReferenceDomEvidenceCatalog,
) -> dict[str, object]:
    return {
        "section_candidates": [
            _compact_dom_evidence_item(item)
            for item in dom_evidence.section_candidates
        ],
        "chrome_candidates": [
            _compact_dom_evidence_item(item)
            for item in dom_evidence.chrome_candidates
        ],
        "footer_bands": [
            _compact_dom_evidence_item(item) for item in dom_evidence.footer_bands
        ],
        "form_candidates": [
            _compact_dom_evidence_item(item) for item in dom_evidence.form_candidates
        ],
        "repeated_groups": [
            _compact_dom_evidence_item(item) for item in dom_evidence.repeated_groups
        ],
        "state_variants": [
            _compact_dom_evidence_item(item) for item in dom_evidence.state_variants
        ],
        "wrapper_relationships": [
            _compact_dom_evidence_relationship(item)
            for item in dom_evidence.wrapper_relationships
        ],
    }


def _compact_dom_evidence_item(item: LiveReferenceDomEvidenceItem) -> dict[str, object]:
    return {
        "evidence_id": _truncate_text(item.evidence_id, 80),
        "kind": item.kind,
        "label": _truncate_text(item.label, 180),
        "selector": _truncate_text(item.selector, 220),
        "parent_selector": _truncate_text(item.parent_selector, 220),
        "tag": item.tag,
        "role": _truncate_text(item.role, 80),
        "heading_text": _truncate_text(item.heading_text, 180),
        "text_sample": _truncate_text(item.text_sample, 220),
        "top_offset_px": item.top_offset_px,
        "height_px": item.height_px,
        "position": _truncate_text(item.position, 40),
        "background": _truncate_text(item.background, 200),
        "border_radius": _truncate_text(item.border_radius, 80),
        "max_width": _truncate_text(item.max_width, 80),
        "asset_urls": _truncate_list(item.asset_urls, max_items=6, max_chars=220),
        "notes": _truncate_list(item.notes, max_items=6, max_chars=240),
        "html_excerpt": _truncate_text(item.html_excerpt, 1000),
    }


def _compact_dom_evidence_relationship(
    item: LiveReferenceDomRelationship,
) -> dict[str, object]:
    return {
        "child_evidence_id": _truncate_text(item.child_evidence_id, 80),
        "child_selector": _truncate_text(item.child_selector, 220),
        "parent_evidence_id": _truncate_text(item.parent_evidence_id, 80),
        "parent_selector": _truncate_text(item.parent_selector, 220),
        "relationship": _truncate_text(item.relationship, 320),
        "notes": _truncate_list(item.notes, max_items=4, max_chars=220),
    }


def build_live_design_system_rules(
    reference_bundle: ReferenceBundle, requirements: RequirementsSpec
) -> str:
    design_system = reference_bundle.design_system_preflight
    if design_system is None and reference_bundle.live_reference is None:
        return ""

    token_names = _extract_design_token_names(requirements)
    font_names = _extract_design_system_font_names(
        design_system, reference_bundle.live_reference
    )
    usage_tokens = [
        name
        for name in token_names
        if name.startswith("--font-")
        or name.startswith("--color-")
        or name.startswith("--radius-")
    ]

    lines = [
        "Live design-system enforcement:",
        "- The implementation must use the extracted live design system as a centralized theme, not as optional inspiration.",
    ]
    if font_names:
        lines.append(
            "- Exact extracted font-family names that must appear in code: "
            + ", ".join(font_names)
        )
        lines.append(
            "- If fallbacks are needed, append them after the exact extracted names; do not replace the extracted names."
        )
        lines.append(
            "- If those fonts are not standard web-safe families, include a working font-loading mechanism such as `@font-face`, imported hosted font CSS, or explicit font asset URLs. Naming the family without loading it is insufficient."
        )
    if token_names:
        lines.append(
            "- Centralized theme tokens that must be declared in code: "
            + ", ".join(token_names[:12])
        )
    if (
        reference_bundle.live_reference is not None
        and reference_bundle.live_reference.design_system.asset_inventory
    ):
        lines.append(
            "- Reuse the extracted live-site image, SVG, and background asset URLs directly for the matching sections instead of substituting placeholder blocks, generated imagery, or unrelated stock assets."
        )
        lines.append(
            "- Representative extracted asset references to preserve: "
            + "; ".join(
                _truncate_text(value, 160)
                for value in reference_bundle.live_reference.design_system.asset_inventory[
                    :4
                ]
            )
        )
    if usage_tokens:
        lines.append(
            "- These theme tokens must also be actively used via CSS variables in the implementation: "
            + ", ".join(f"var({name})" for name in usage_tokens[:10])
        )
    lines.append(
        "- Do not substitute different font families, bypass the theme variables with unrelated hardcoded styling, or omit the extracted tokens from the implementation."
    )
    lines.append(
        "- Treat measured typography and section sizing from the live design system as implementation targets, especially for hero headlines, header/nav text, CTA labels, promo bars, and footer/newsletter content."
    )
    return "\n".join(lines)


def summarize_design_system_preflight_for_prompt(
    design_system: DesignSystemPreflight,
) -> str:
    payload: dict[str, object] = {
        "title": _truncate_text(design_system.title, 160),
        "summary": _truncate_text(design_system.summary, 400),
        "philosophy": _truncate_list(
            design_system.philosophy, max_items=8, max_chars=180
        ),
        "typography": _truncate_list(
            design_system.typography, max_items=10, max_chars=180
        ),
        "section_typography": _truncate_list(
            design_system.section_typography, max_items=12, max_chars=220
        ),
        "colors": _truncate_list(design_system.colors, max_items=12, max_chars=160),
        "spacing": _truncate_list(
            design_system.spacing, max_items=10, max_chars=160
        ),
        "radii": _truncate_list(design_system.radii, max_items=8, max_chars=160),
        "layout": _truncate_list(design_system.layout, max_items=10, max_chars=220),
        "section_sizing": _truncate_list(
            design_system.section_sizing, max_items=10, max_chars=220
        ),
        "components": _truncate_list(
            design_system.components, max_items=10, max_chars=220
        ),
        "motion": _truncate_list(design_system.motion, max_items=10, max_chars=220),
        "motion_components": _truncate_list(
            design_system.motion_components, max_items=10, max_chars=220
        ),
        "brand": _truncate_list(design_system.brand, max_items=8, max_chars=180),
        "source_notes": _truncate_list(
            design_system.source_notes, max_items=8, max_chars=220
        ),
    }
    return truncate_json_context(json.dumps(payload, indent=2), max_chars=10_000)


def _truncate_text(value: str, max_chars: int) -> str:
    normalized = value.strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 26].rstrip() + " ...[truncated for prompt]"


def truncate_html_context(value: str) -> str:
    normalized = value.strip()
    if len(normalized) <= MAX_CURRENT_HTML_CHARS:
        return normalized

    half = MAX_CURRENT_HTML_CHARS // 2
    head = normalized[:half].rstrip()
    tail = normalized[-half:].lstrip()
    return f"""{head}
...[truncated current HTML context]...
{tail}"""


def truncate_json_context(value: str, *, max_chars: int = 16_000) -> str:
    normalized = value.strip()
    if len(normalized) <= max_chars:
        return normalized

    half = max_chars // 2
    head = normalized[:half].rstrip()
    tail = normalized[-half:].lstrip()
    return f"""{head}
...[truncated JSON context]...
{tail}"""


def summarize_html_landmarks(value: str, *, max_items: int = 18) -> str:
    if not value.strip():
        return "(no current HTML landmarks available)"

    parser = _HtmlLandmarkParser(max_items=max_items)
    parser.feed(value)
    parser.close()

    if not parser.landmarks:
        return "(no stable selectors or landmark text were extracted from the current HTML)"

    return "\n".join(f"- {landmark}" for landmark in parser.landmarks[:max_items])


def summarize_executor_file_evidence(value: str) -> str:
    if not value.strip():
        return "(no current file evidence available)"

    section_marker_patterns = [
        r'data-section-id\s*=\s*"([^"]+)"',
        r"data-section-id\s*=\s*'([^']+)'",
        r'data-section-id\s*=\s*\{\s*"([^"]+)"\s*\}',
        r"data-section-id\s*=\s*\{\s*'([^']+)'\s*\}",
    ]
    section_markers: list[str] = []
    seen_markers: set[str] = set()
    for pattern in section_marker_patterns:
        for match in re.findall(pattern, value):
            normalized = match.strip()
            if not normalized or normalized in seen_markers:
                continue
            seen_markers.add(normalized)
            section_markers.append(normalized)

    wrapper_marker_patterns = [
        r'data-wrapper-id\s*=\s*"([^"]+)"',
        r"data-wrapper-id\s*=\s*'([^']+)'",
        r'data-wrapper-id\s*=\s*\{\s*"([^"]+)"\s*\}',
        r"data-wrapper-id\s*=\s*\{\s*'([^']+)'\s*\}",
    ]
    wrapper_markers: list[str] = []
    seen_wrappers: set[str] = set()
    for pattern in wrapper_marker_patterns:
        for match in re.findall(pattern, value):
            normalized = match.strip()
            if not normalized or normalized in seen_wrappers:
                continue
            seen_wrappers.add(normalized)
            wrapper_markers.append(normalized)

    component_patterns = [
        r"\bfunction\s+([A-Z][A-Za-z0-9_]*)\s*\(",
        r"\bconst\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(",
        r"\bconst\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_]+)\s*=>",
    ]
    component_names: list[str] = []
    seen_components: set[str] = set()
    for pattern in component_patterns:
        for match in re.findall(pattern, value):
            normalized = match.strip()
            if not normalized or normalized in seen_components:
                continue
            seen_components.add(normalized)
            component_names.append(normalized)

    evidence_lines: list[str] = []
    if section_markers:
        evidence_lines.append(
            "Verified section markers present in the current file: "
            + ", ".join(section_markers[:24])
        )
    if wrapper_markers:
        evidence_lines.append(
            "Verified wrapper markers present in the current file: "
            + ", ".join(wrapper_markers[:20])
        )
    if component_names:
        evidence_lines.append(
            "Verified component/function boundaries present in the current file: "
            + ", ".join(component_names[:20])
        )

    landmarks = summarize_html_landmarks(value, max_items=12)
    if not landmarks.startswith("(no "):
        evidence_lines.append("Current file landmarks:")
        evidence_lines.append(landmarks)

    if not evidence_lines:
        return "(no stable current file evidence extracted)"

    return "\n".join(evidence_lines)


def _truncate_list(items: list[str], *, max_items: int, max_chars: int) -> list[str]:
    return [
        _truncate_text(item, max_chars)
        for item in items[:max_items]
        if item.strip()
    ]


def _extract_design_token_names(requirements: RequirementsSpec) -> list[str]:
    token_values = [
        *requirements.design_tokens.colors,
        *requirements.design_tokens.typography,
        *requirements.design_tokens.spacing,
        *requirements.design_tokens.radii,
        *requirements.design_tokens.shadows,
        *requirements.design_tokens.motion,
    ]
    seen: set[str] = set()
    names: list[str] = []
    for token in token_values:
        match = re.match(r"\s*(--[a-zA-Z0-9_-]+)\s*:", token)
        if match is None:
            continue
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _extract_live_reference_font_names(live_reference: LiveReferenceContext) -> list[str]:
    seen: set[str] = set()
    font_names: list[str] = []
    for typography_entry in live_reference.design_system.typography:
        match = re.search(r"font\s+(.+?);", typography_entry)
        if match is None:
            continue
        for part in match.group(1).split(","):
            normalized = part.strip().strip('"').strip("'")
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in {"sans-serif", "serif", "monospace", "arial"}:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            font_names.append(normalized)
    return font_names


def _extract_live_reference_asset_urls(
    live_reference: LiveReferenceContext,
) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for entry in live_reference.design_system.asset_inventory:
        for match in re.findall(r"https?://[^\s;]+", entry):
            if match in seen:
                continue
            seen.add(match)
            urls.append(match)
    return urls


def _extract_design_system_font_names(
    design_system: DesignSystemPreflight | None,
    live_reference: LiveReferenceContext | None,
) -> list[str]:
    if design_system is not None:
        seen: set[str] = set()
        font_names: list[str] = []
        for token in [*design_system.typography, *design_system.section_typography]:
            for match in re.findall(r"['\"]([^'\"]+)['\"]", token):
                if match in seen:
                    continue
                seen.add(match)
                font_names.append(match)
        if font_names:
            return font_names
    if live_reference is not None:
        return _extract_live_reference_font_names(live_reference)
    return []


def _compact_design_tokens(design_tokens: DesignTokenSet) -> DesignTokenSet:
    return DesignTokenSet(
        colors=_truncate_list(
            design_tokens.colors,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=160,
        ),
        typography=_truncate_list(
            design_tokens.typography,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=160,
        ),
        spacing=_truncate_list(
            design_tokens.spacing,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=160,
        ),
        radii=_truncate_list(
            design_tokens.radii,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=160,
        ),
        shadows=_truncate_list(
            design_tokens.shadows,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=160,
        ),
        motion=_truncate_list(
            design_tokens.motion,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=200,
        ),
    )


def _compact_section(section: SectionRequirement) -> SectionRequirement:
    return SectionRequirement(
        name=_truncate_text(section.name, 120),
        section_id=section.section_id,
        purpose=_truncate_text(section.purpose, 200),
        layout=_truncate_text(section.layout, 260),
        layout_invariants=_truncate_list(
            section.layout_invariants,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=220,
        ),
        must_include=_truncate_list(
            section.must_include,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=180,
        ),
        styling=_truncate_list(
            section.styling,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=180,
        ),
        copy_items=_truncate_list(
            section.copy_items,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=180,
        ),
        assets=_truncate_list(
            section.assets,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=180,
        ),
        behaviors=_truncate_list(
            section.behaviors,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=220,
        ),
        editable_fields=_truncate_list(
            section.editable_fields,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=140,
        ),
    )


def _compact_interaction_checkpoint(
    checkpoint: InteractionCheckpoint,
) -> InteractionCheckpoint:
    return InteractionCheckpoint(
        name=_truncate_text(checkpoint.name, 120),
        trigger=_truncate_text(checkpoint.trigger, 200),
        expected_result=_truncate_text(checkpoint.expected_result, 260),
        action_type=checkpoint.action_type,
        target_description=_truncate_text(checkpoint.target_description, 180),
    )


def _compact_wrapper_requirement(wrapper: WrapperRequirement) -> WrapperRequirement:
    return WrapperRequirement(
        name=_truncate_text(wrapper.name, 120),
        wrapper_id=wrapper.wrapper_id,
        kind=wrapper.kind,
        participant_section_ids=_truncate_list(
            wrapper.participant_section_ids,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=80,
        ),
        purpose=_truncate_text(wrapper.purpose, 220),
        layout_invariants=_truncate_list(
            wrapper.layout_invariants,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=220,
        ),
        must_include=_truncate_list(
            wrapper.must_include,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=180,
        ),
        styling=_truncate_list(
            wrapper.styling,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=180,
        ),
    )


def compact_requirements_for_prompt(requirements: RequirementsSpec) -> RequirementsSpec:
    return RequirementsSpec(
        summary=_truncate_text(requirements.summary, MAX_REQUIREMENTS_SUMMARY_CHARS),
        template_goal=_truncate_text(
            requirements.template_goal, MAX_REQUIREMENTS_SUMMARY_CHARS
        ),
        viewport=requirements.viewport,
        page_outline=_truncate_list(
            requirements.page_outline,
            max_items=10,
            max_chars=140,
        ),
        closing_sections=_truncate_list(
            requirements.closing_sections,
            max_items=5,
            max_chars=140,
        ),
        footer_present=requirements.footer_present,
        footer_description=_truncate_text(requirements.footer_description, 220),
        coverage_notes=_truncate_list(
            requirements.coverage_notes,
            max_items=6,
            max_chars=220,
        ),
        critical_layout_invariants=_truncate_list(
            requirements.critical_layout_invariants,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=260,
        ),
        hard_constraints=_truncate_list(
            requirements.hard_constraints,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=220,
        ),
        preserve_requirements=_truncate_list(
            requirements.preserve_requirements,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=220,
        ),
        design_tokens=_compact_design_tokens(requirements.design_tokens),
        section_requirements=[
            _compact_section(section)
            for section in requirements.section_requirements[:MAX_SECTION_COUNT]
        ],
        wrapper_requirements=[
            _compact_wrapper_requirement(wrapper)
            for wrapper in requirements.wrapper_requirements[:MAX_SECTION_COUNT]
        ],
        layout_requirements=_truncate_list(
            requirements.layout_requirements,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        styling_requirements=_truncate_list(
            requirements.styling_requirements,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        copy_requirements=_truncate_list(
            requirements.copy_requirements,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        asset_requirements=_truncate_list(
            requirements.asset_requirements,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        behavior_requirements=_truncate_list(
            requirements.behavior_requirements,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        animation_requirements=_truncate_list(
            requirements.animation_requirements,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        structure_guidance=_truncate_list(
            requirements.structure_guidance,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        execution_plan=_truncate_list(
            requirements.execution_plan,
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
            max_chars=MAX_REQUIREMENTS_TEXT_CHARS,
        ),
        known_unknowns=_truncate_list(
            requirements.known_unknowns,
            max_items=6,
            max_chars=220,
        ),
        interaction_checkpoints=[
            _compact_interaction_checkpoint(checkpoint)
            for checkpoint in requirements.interaction_checkpoints[:6]
        ],
        acceptance_criteria=_truncate_list(
            requirements.acceptance_criteria,
            max_items=8,
            max_chars=220,
        ),
    )


def compact_validator_requirements_for_prompt(
    requirements: RequirementsSpec,
) -> dict[str, object]:
    compact = compact_requirements_for_prompt(requirements)
    return {
        "summary": compact.summary,
        "viewport": compact.viewport.model_dump(mode="json"),
        "page_outline": compact.page_outline,
        "closing_sections": compact.closing_sections,
        "footer_present": compact.footer_present,
        "footer_description": compact.footer_description,
        "coverage_notes": compact.coverage_notes,
        "critical_layout_invariants": compact.critical_layout_invariants,
        "hard_constraints": compact.hard_constraints,
        "preserve_requirements": compact.preserve_requirements,
        "design_tokens": compact.design_tokens.model_dump(mode="json"),
        "section_requirements": [
            section.model_dump(mode="json") for section in compact.section_requirements
        ],
        "wrapper_requirements": [
            wrapper.model_dump(mode="json") for wrapper in compact.wrapper_requirements
        ],
        "behavior_requirements": compact.behavior_requirements,
        "animation_requirements": compact.animation_requirements,
        "interaction_checkpoints": [
            checkpoint.model_dump(mode="json")
            for checkpoint in compact.interaction_checkpoints
        ],
        "acceptance_criteria": compact.acceptance_criteria,
        "known_unknowns": compact.known_unknowns,
    }


def _compact_blueprint_validation_issue(
    issue: BlueprintValidationIssue,
) -> BlueprintValidationIssue:
    return BlueprintValidationIssue(
        severity=issue.severity,
        category=issue.category,
        title=_truncate_text(issue.title, 160),
        detail=_truncate_text(issue.detail, 320),
        affected_fields=_truncate_list(
            issue.affected_fields,
            max_items=6,
            max_chars=80,
        ),
        fix_instructions=_truncate_text(issue.fix_instructions, 320),
    )


def compact_blueprint_validation_report_for_prompt(
    validation_report: BlueprintValidationReport,
) -> BlueprintValidationReport:
    return BlueprintValidationReport(
        verdict=validation_report.verdict,
        overall_score=validation_report.overall_score,
        coverage_score=validation_report.coverage_score,
        consistency_score=validation_report.consistency_score,
        execution_readiness_score=validation_report.execution_readiness_score,
        summary=_truncate_text(validation_report.summary, MAX_REQUIREMENTS_SUMMARY_CHARS),
        strengths=_truncate_list(
            validation_report.strengths,
            max_items=6,
            max_chars=220,
        ),
        issues=[
            _compact_blueprint_validation_issue(issue)
            for issue in validation_report.issues[:MAX_ISSUE_COUNT]
        ],
        missing_sections=_truncate_list(
            validation_report.missing_sections,
            max_items=MAX_SECTION_LIST_ITEMS,
            max_chars=160,
        ),
        repair_instructions=_truncate_list(
            validation_report.repair_instructions,
            max_items=MAX_PATCH_INSTRUCTION_COUNT,
            max_chars=320,
        ),
    )


def _compact_validation_issue(issue: ValidationIssue) -> ValidationIssue:
    return ValidationIssue(
        severity=issue.severity,
        category=issue.category,
        title=_truncate_text(issue.title, 160),
        observed=_truncate_text(issue.observed, 260),
        expected=_truncate_text(issue.expected, 260),
        fix_instructions=_truncate_text(issue.fix_instructions, 320),
    )


def _compact_section_validation_result(
    result: SectionValidationResult,
) -> SectionValidationResult:
    return SectionValidationResult(
        name=_truncate_text(result.name, 80),
        status=result.status,
        quality_score=result.quality_score,
        summary=_truncate_text(result.summary, 220),
        fix_instructions=_truncate_text(result.fix_instructions, 240),
    )


def compact_validation_report_for_prompt(
    validation_report: ValidationReport,
) -> ValidationReport:
    return ValidationReport(
        verdict=validation_report.verdict,
        overall_score=validation_report.overall_score,
        visual_fidelity_score=validation_report.visual_fidelity_score,
        behavior_fidelity_score=validation_report.behavior_fidelity_score,
        animation_fidelity_score=validation_report.animation_fidelity_score,
        editability_score=validation_report.editability_score,
        summary=_truncate_text(validation_report.summary, MAX_REQUIREMENTS_SUMMARY_CHARS),
        strengths=_truncate_list(
            validation_report.strengths,
            max_items=6,
            max_chars=220,
        ),
        section_results=[
            _compact_section_validation_result(result)
            for result in validation_report.section_results[:MAX_SECTION_LIST_ITEMS]
        ],
        issues=[
            _compact_validation_issue(issue)
            for issue in validation_report.issues[:MAX_ISSUE_COUNT]
        ],
        patch_instructions=_truncate_list(
            validation_report.patch_instructions,
            max_items=MAX_PATCH_INSTRUCTION_COUNT,
            max_chars=320,
        ),
    )
