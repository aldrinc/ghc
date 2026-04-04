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

from loop.contracts import (
    BlueprintValidationIssue,
    BlueprintValidationReport,
    DesignSystemPreflight,
    DesignTokenSet,
    InteractionCheckpoint,
    LiveReferenceContext,
    ReferenceBundle,
    RequirementsSpec,
    SectionRequirement,
    SectionValidationResult,
    ValidationIssue,
    ValidationReport,
)

MAX_REQUIREMENTS_TEXT_CHARS = 500
MAX_REQUIREMENTS_SUMMARY_CHARS = 1_000
MAX_REQUIREMENTS_LIST_ITEMS = 10
MAX_SECTION_COUNT = 8
MAX_SECTION_LIST_ITEMS = 6
MAX_ISSUE_COUNT = 8
MAX_PATCH_INSTRUCTION_COUNT = 10
MAX_CURRENT_HTML_CHARS = 20_000


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
    payload: dict[str, object] = {
        "url": live_reference.url,
        "page_title": _truncate_text(
            live_reference.design_system.page_title,
            160,
        ),
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
                max_items=10,
                max_chars=220,
            ),
            "components": _truncate_list(
                live_reference.design_system.components,
                max_items=10,
                max_chars=220,
            ),
            "raw_observations": _truncate_list(
                live_reference.design_system.raw_observations,
                max_items=10,
                max_chars=220,
            ),
        },
    }
    return truncate_json_context(json.dumps(payload, indent=2), max_chars=8_000)


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
    if token_names:
        lines.append(
            "- Centralized theme tokens that must be declared in code: "
            + ", ".join(token_names[:12])
        )
    if usage_tokens:
        lines.append(
            "- These theme tokens must also be actively used via CSS variables in the implementation: "
            + ", ".join(f"var({name})" for name in usage_tokens[:10])
        )
    lines.append(
        "- Do not substitute different font families, bypass the theme variables with unrelated hardcoded styling, or omit the extracted tokens from the implementation."
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
        purpose=_truncate_text(section.purpose, 200),
        layout=_truncate_text(section.layout, 260),
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
            max_items=MAX_REQUIREMENTS_LIST_ITEMS,
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
        "hard_constraints": compact.hard_constraints,
        "preserve_requirements": compact.preserve_requirements,
        "design_tokens": compact.design_tokens.model_dump(mode="json"),
        "section_requirements": [
            section.model_dump(mode="json") for section in compact.section_requirements
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
