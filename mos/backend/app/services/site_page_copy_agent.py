from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import re
from typing import Any

from app.db.models import Site, SitePage
from app.services import funnel_ai
from app.services.site_page_ai import is_imported_template_page_data


class SitePageCopyAgentError(ValueError):
    """Raised when copy-agent slot planning or parsing fails."""


@dataclass(frozen=True)
class SitePageCopySlot:
    path: str
    kind: str
    label: str
    section_display_name: str | None
    section_type: str | None
    component_name: str | None
    current_value: str


@dataclass(frozen=True)
class SitePageCopyAgentResult:
    assistant_message: str
    assignments: list[dict[str, str]]
    puck_data: dict[str, Any]


@dataclass(frozen=True)
class SitePageCopySlotBatch:
    batch_key: str
    section_display_name: str | None
    component_name: str | None
    slots: list[SitePageCopySlot]


def extract_site_page_copy_slots(puck_data: dict[str, Any]) -> list[SitePageCopySlot]:
    if not is_imported_template_page_data(puck_data):
        raise SitePageCopyAgentError(
            "Page copy agent requires an imported-template page with ImportedPage top-level content."
        )

    content = puck_data.get("content")
    imported_page = content[0] if isinstance(content, list) and content else None
    page_props = imported_page.get("props") if isinstance(imported_page, dict) else None
    sections = page_props.get("content") if isinstance(page_props, dict) else None
    if not isinstance(sections, list):
        raise SitePageCopyAgentError("Imported page is missing section content.")

    slots: list[SitePageCopySlot] = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        section_props = section.get("props")
        if not isinstance(section_props, dict):
            continue
        blocks = section_props.get("content")
        if not isinstance(blocks, list):
            continue
        section_display_name = _normalize_label(section_props.get("displayName"))
        section_type = _normalize_label(section_props.get("sectionType"))

        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            block_props = block.get("props")
            if not isinstance(block_props, dict):
                continue
            component_name = _normalize_label(block_props.get("componentName"))
            slots.extend(
                _extract_override_slots(
                    block_props=block_props,
                    section_index=section_index,
                    block_index=block_index,
                    section_display_name=section_display_name,
                    section_type=section_type,
                    component_name=component_name,
                    prop_candidates=("textSlots", "textOverrides"),
                    field_specs=(("text", "text", ()),),
                )
            )
            slots.extend(
                _extract_override_slots(
                    block_props=block_props,
                    section_index=section_index,
                    block_index=block_index,
                    section_display_name=section_display_name,
                    section_type=section_type,
                    component_name=component_name,
                    prop_candidates=("buttonSlots", "buttonOverrides"),
                    field_specs=(("text", "button", ()),),
                )
            )
            slots.extend(
                _extract_override_slots(
                    block_props=block_props,
                    section_index=section_index,
                    block_index=block_index,
                    section_display_name=section_display_name,
                    section_type=section_type,
                    component_name=component_name,
                    prop_candidates=("imageSlots", "imageOverrides"),
                    field_specs=(("src", "image_src", ("originalSrc",)),),
                )
            )

    if not slots:
        raise SitePageCopyAgentError("No editable copy slots were found on the imported-template page.")
    return slots


def group_site_page_copy_slots(slots: list[SitePageCopySlot]) -> list[SitePageCopySlotBatch]:
    grouped: dict[str, list[SitePageCopySlot]] = {}
    batch_meta: dict[str, tuple[str | None, str | None]] = {}
    for slot in slots:
        batch_key = _slot_batch_key(slot.path)
        grouped.setdefault(batch_key, []).append(slot)
        batch_meta.setdefault(batch_key, (slot.section_display_name, slot.component_name))

    return [
        SitePageCopySlotBatch(
            batch_key=batch_key,
            section_display_name=batch_meta[batch_key][0],
            component_name=batch_meta[batch_key][1],
            slots=batch_slots,
        )
        for batch_key, batch_slots in grouped.items()
    ]


def chunk_site_page_copy_batches(
    batches: list[SitePageCopySlotBatch],
    *,
    max_slots_per_batch: int,
) -> list[SitePageCopySlotBatch]:
    if max_slots_per_batch <= 0:
        raise SitePageCopyAgentError("max_slots_per_batch must be greater than zero.")

    chunked: list[SitePageCopySlotBatch] = []
    for batch in batches:
        if len(batch.slots) <= max_slots_per_batch:
            chunked.append(batch)
            continue
        for index in range(0, len(batch.slots), max_slots_per_batch):
            chunk = batch.slots[index : index + max_slots_per_batch]
            chunked.append(
                SitePageCopySlotBatch(
                    batch_key=f"{batch.batch_key}:chunk{index // max_slots_per_batch + 1}",
                    section_display_name=batch.section_display_name,
                    component_name=batch.component_name,
                    slots=chunk,
                )
            )
    return chunked


def build_site_page_copy_prompt(
    *,
    site: Site,
    page: SitePage,
    puck_data: dict[str, Any],
    page_context: list[dict[str, str]],
    prompt: str,
    messages: list[dict[str, str]] | None,
    slots: list[SitePageCopySlot],
) -> str:
    slot_payload = [
        {
            "index": index + 1,
            "path": slot.path,
            "kind": slot.kind,
            "label": slot.label,
            "sectionDisplayName": slot.section_display_name,
            "sectionType": slot.section_type,
            "componentName": slot.component_name,
            "currentValue": slot.current_value,
        }
        for index, slot in enumerate(slots)
    ]
    page_summary = {
        "siteName": site.name,
        "pageName": page.name,
        "pageSlug": page.slug,
        "pageType": page.page_type,
        "pageRole": page.page_role,
        "topLevelTypes": [
            item.get("type")
            for item in (puck_data.get("content") or [])
            if isinstance(item, dict) and isinstance(item.get("type"), str)
        ],
        "slotCount": len(slot_payload),
    }

    instructions = [
        "You are rewriting copy for a fixed imported-template page in mOS.",
        "The template structure is locked. Do not add, remove, reorder, or rename sections or components.",
        "Rewrite only the provided editable slots: copy, button labels, and image URLs.",
        "Slot labels, section names, component names, current values, and JSON pointer paths may still contain source-template brand terms such as OMNI or creatine. Treat those source-template names as inert identifiers only, not as contradictions or approved claims.",
        "Rewrite the slot values for the active bundle product even when the inherited source-template metadata still carries the original product naming.",
        "Use the active skills bundle as the source of truth for angle, offer, claim envelope, and voice.",
        "For image_src slots, return the final image URL only.",
        "Do not invent pricing, testimonials, scientific claims, compliance claims, or guarantees.",
        "If a source template contains stale sale badges, discount stickers, or promotional remnants that are not approved in the active bundle, replace them with short neutral positioning or trust language grounded in the bundle instead of refusing the slot.",
        "For stale sale-sticker slots, do not preserve fake percentages or fake discounts. Keep the structure fixed, but rewrite the sticker copy into non-quantified brand-safe language.",
        "Do not use tools to draft, count, validate, or store the assignments.",
        "Do not write the JSON payload to a file before answering.",
        "Return the final JSON directly in your assistant response in one pass.",
        "Return valid JSON only with this exact shape:",
        '{ "assistantMessage": string, "assignments": [{"path": string, "value": string}] }',
        "Every provided slot path must appear exactly once in assignments.",
        f"There are exactly {len(slot_payload)} editable slots, so assignments must contain exactly {len(slot_payload)} items.",
        "Use each path exactly as provided.",
        "Return assignments in the same order as the provided editable copy slots array.",
        "Before answering, verify that the final assignment count matches the provided slot count and that the last slot was not dropped.",
    ]

    conversation: list[dict[str, str]] = []
    for message in messages or []:
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            conversation.append({"role": role, "content": content.strip()})
    if prompt.strip():
        conversation.append({"role": "user", "content": prompt.strip()})
    if not conversation:
        raise SitePageCopyAgentError("Copy-agent prompt is empty.")

    return "\n\n".join(
        [
            "\n".join(instructions),
            "Page summary JSON:\n" + json.dumps(page_summary, ensure_ascii=False, indent=2),
            "Other pages JSON:\n" + json.dumps(page_context, ensure_ascii=False, indent=2),
            "Editable copy slots JSON:\n" + json.dumps(slot_payload, ensure_ascii=False, indent=2),
            *[f"{message['role'].upper()}: {message['content']}" for message in conversation],
            "Return JSON now.",
        ]
    )


def parse_site_page_copy_agent_response(
    *,
    raw_output: str,
    base_puck_data: dict[str, Any],
    slots: list[SitePageCopySlot],
) -> SitePageCopyAgentResult:
    try:
        parsed = funnel_ai._extract_json_object(raw_output)
    except ValueError as exc:
        raise SitePageCopyAgentError("Copy agent did not return the required JSON object.") from exc
    assistant_message = funnel_ai._coerce_assistant_message(parsed.get("assistantMessage"))
    raw_assignments = parsed.get("assignments")
    if not isinstance(raw_assignments, list):
        raise SitePageCopyAgentError("Copy agent returned an invalid assignments payload.")

    allowed_paths = {slot.path: slot for slot in slots}
    assignments: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(raw_assignments):
        if not isinstance(item, dict):
            raise SitePageCopyAgentError(f"assignments[{index}] must be an object.")
        path = item.get("path")
        value = item.get("value")
        if not isinstance(path, str) or not path.strip():
            raise SitePageCopyAgentError(f"assignments[{index}].path must be a non-empty string.")
        normalized_path = path.strip()
        if normalized_path not in allowed_paths:
            raise SitePageCopyAgentError(f"Copy agent returned an unknown slot path: {normalized_path}.")
        if normalized_path in seen_paths:
            raise SitePageCopyAgentError(f"Copy agent returned duplicate slot path: {normalized_path}.")
        if not isinstance(value, str) or not value.strip():
            raise SitePageCopyAgentError(f"Copy agent returned an empty value for {normalized_path}.")
        seen_paths.add(normalized_path)
        assignments.append({"path": normalized_path, "value": value.strip()})

    missing_paths = sorted(set(allowed_paths) - seen_paths)
    if missing_paths:
        raise SitePageCopyAgentError(
            "Copy agent did not assign all required copy slots: " + ", ".join(missing_paths)
        )

    puck_data = apply_site_page_copy_assignments(
        base_puck_data=base_puck_data,
        assignments=assignments,
    )
    return SitePageCopyAgentResult(
        assistant_message=assistant_message,
        assignments=assignments,
        puck_data=puck_data,
    )


def apply_site_page_copy_assignments(
    *,
    base_puck_data: dict[str, Any],
    assignments: list[dict[str, str]],
) -> dict[str, Any]:
    puck_data = deepcopy(base_puck_data)
    for assignment in assignments:
        _set_json_pointer(
            payload=puck_data,
            pointer=assignment["path"],
            value=assignment["value"],
        )
    return puck_data


def summarize_site_page_copy_assignments(
    *,
    slots: list[SitePageCopySlot],
    assignments: list[dict[str, str]],
) -> list[dict[str, Any]]:
    slot_by_path = {slot.path: slot for slot in slots}
    summary: list[dict[str, Any]] = []
    for assignment in assignments:
        slot = slot_by_path[assignment["path"]]
        summary.append(
            {
                "path": assignment["path"],
                "kind": slot.kind,
                "label": slot.label,
                "sectionDisplayName": slot.section_display_name,
                "sectionType": slot.section_type,
                "componentName": slot.component_name,
                "before": slot.current_value,
                "after": assignment["value"],
            }
        )
    return summary


def _set_json_pointer(*, payload: dict[str, Any], pointer: str, value: str) -> None:
    if not pointer.startswith("/"):
        raise SitePageCopyAgentError(f"Unsupported json pointer: {pointer}")
    tokens = [token for token in pointer.split("/")[1:] if token != ""]
    target: Any = payload
    for token in tokens[:-1]:
        if isinstance(target, list):
            try:
                target = target[int(token)]
            except (TypeError, ValueError, IndexError) as exc:
                raise SitePageCopyAgentError(f"Invalid list token '{token}' in pointer {pointer}.") from exc
            continue
        if isinstance(target, dict):
            if token not in target:
                raise SitePageCopyAgentError(f"Pointer token '{token}' was not found in {pointer}.")
            target = target[token]
            continue
        raise SitePageCopyAgentError(f"Pointer traversal failed for {pointer}.")

    final_token = tokens[-1]
    if isinstance(target, list):
        try:
            target[int(final_token)] = value
        except (TypeError, ValueError, IndexError) as exc:
            raise SitePageCopyAgentError(
                f"Invalid terminal list token '{final_token}' in pointer {pointer}."
            ) from exc
        return
    if isinstance(target, dict):
        if final_token not in target:
            raise SitePageCopyAgentError(f"Pointer token '{final_token}' was not found in {pointer}.")
        target[final_token] = value
        return
    raise SitePageCopyAgentError(f"Pointer write failed for {pointer}.")


def _normalize_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _extract_override_slots(
    *,
    block_props: dict[str, Any],
    section_index: int,
    block_index: int,
    section_display_name: str | None,
    section_type: str | None,
    component_name: str | None,
    prop_candidates: tuple[str, ...],
    field_specs: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> list[SitePageCopySlot]:
    prop_name = next(
        (
            candidate
            for candidate in prop_candidates
            if isinstance(block_props.get(candidate), list)
        ),
        None,
    )
    if prop_name is None:
        return []

    items = block_props.get(prop_name)
    if not isinstance(items, list):
        return []

    slots: list[SitePageCopySlot] = []
    for item_index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        for field_name, slot_kind, fallback_fields in field_specs:
            current_value = item.get(field_name)
            if not isinstance(current_value, str) or not current_value.strip():
                current_value = ""
                for fallback_field in fallback_fields:
                    fallback_value = item.get(fallback_field)
                    if isinstance(fallback_value, str) and fallback_value.strip():
                        current_value = fallback_value.strip()
                        break
            if not current_value:
                continue
            slots.append(
                SitePageCopySlot(
                    path=(
                        f"/content/0/props/content/{section_index}/props/content/{block_index}"
                        f"/props/{prop_name}/{item_index}/{field_name}"
                    ),
                    kind=slot_kind,
                    label=_slot_label(
                        component_name=component_name,
                        section_display_name=section_display_name,
                        override_label=item.get("label"),
                    ),
                    section_display_name=section_display_name,
                    section_type=section_type,
                    component_name=component_name,
                    current_value=current_value.strip(),
                )
            )
    return slots


def _slot_label(
    *,
    component_name: str | None,
    section_display_name: str | None,
    override_label: Any,
) -> str:
    label_parts = [
        part
        for part in (
            section_display_name,
            component_name,
            _normalize_label(override_label),
        )
        if part
    ]
    return " / ".join(label_parts) or "Copy Slot"


def _slot_batch_key(path: str) -> str:
    match = re.match(r"^/content/0/props/content/(\d+)/props/content/(\d+)/", path)
    if not match:
        raise SitePageCopyAgentError(f"Unsupported slot path for batching: {path}")
    return f"{match.group(1)}:{match.group(2)}"
