from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentThread, Site, SitePage, SitePageVersion
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.services.agent_threads import AgentThreadsService, PAGE_CHAT_OBJECTIVE_TYPES
from app.services.site_import_archive import (
    backfill_imported_runtime_override_slots,
    refresh_imported_page_copy_slots,
)
from app.services.site_page_ai import is_imported_template_page_data
from app.services.site_templates import normalize_medusa_one_product_puck_data


class PageEditorRuntimeError(ValueError):
    """Raised when the explicit page editor tool layer cannot fulfill a request."""


class PageEditOperation(BaseModel):
    op: Literal["replace", "set"] = "replace"
    path: str = Field(min_length=1)
    value: Any


@dataclass(frozen=True)
class PageEditorTarget:
    thread: AgentThread
    site: Site
    page: SitePage


class PageEditorRuntimeService:
    def __init__(self, *, session: Session, thread_id: str) -> None:
        self.session = session
        self.thread_id = thread_id
        self.target = self._load_target(thread_id=thread_id)
        self.agent_threads = AgentThreadsService(
            session=session,
            org_id=str(self.target.thread.org_id),
            user_id=self.target.thread.user_id,
        )
        self.sites_repo = SitesRuntimeRepository(session)

    def get_page_context(
        self,
        *,
        include_puck_data: bool = True,
        include_editable_bindings: bool = True,
    ) -> dict[str, Any]:
        working_puck_data, working_version_id, working_status = self._load_working_puck_data()
        latest_draft = self.sites_repo.latest_version_for_page(
            page_id=str(self.target.page.id),
            status="draft",
        )
        latest_approved = self.sites_repo.latest_version_for_page(
            page_id=str(self.target.page.id),
            status="approved",
        )

        payload: dict[str, Any] = {
            "threadId": str(self.target.thread.id),
            "objectiveType": self.target.thread.objective_type,
            "site": {
                "id": str(self.target.site.id),
                "name": self.target.site.name,
            },
            "page": {
                "id": str(self.target.page.id),
                "name": self.target.page.name,
                "slug": self.target.page.slug,
                "pageType": self.target.page.page_type,
                "pageRole": self.target.page.page_role,
            },
            "baseVersionId": working_version_id,
            "baseVersionStatus": working_status,
            "latestDraftVersionId": str(latest_draft.id) if latest_draft else None,
            "latestApprovedVersionId": str(latest_approved.id) if latest_approved else None,
            "pageSummary": AgentThreadsService._summarize_puck_data(working_puck_data),
            "sitePages": self.agent_threads._build_site_page_listing(site_id=str(self.target.site.id)),
        }
        if include_editable_bindings:
            editable_bindings = self._extract_editable_bindings(working_puck_data)
            payload["editableBindings"] = editable_bindings
            payload["editableSectionIndex"] = self._build_editable_section_index(editable_bindings)
        if include_puck_data:
            payload["puckData"] = working_puck_data
        return payload

    def apply_page_edits(
        self,
        *,
        edits: list[PageEditOperation],
        change_summary: str,
        expected_base_version_id: str | None = None,
    ) -> dict[str, Any]:
        if not edits:
            raise PageEditorRuntimeError("apply_page_edits requires at least one explicit edit operation.")
        summary = change_summary.strip()
        if not summary:
            raise PageEditorRuntimeError("apply_page_edits requires a non-empty change_summary.")

        working_puck_data, working_version_id, working_status = self._load_working_puck_data()
        if expected_base_version_id and expected_base_version_id != working_version_id:
            raise PageEditorRuntimeError(
                "The page changed since the last read. "
                f"Expected base version '{expected_base_version_id}', current base version is '{working_version_id}'."
            )

        next_puck_data = deepcopy(working_puck_data)
        applied_edits: list[dict[str, Any]] = []
        for edit in edits:
            if edit.op not in {"replace", "set"}:
                raise PageEditorRuntimeError(
                    f"Unsupported edit op '{edit.op}'. Only 'replace' and 'set' are allowed."
                )
            previous_value = self._read_json_pointer(next_puck_data, edit.path)
            if previous_value == edit.value:
                continue
            self._write_json_pointer(next_puck_data, edit.path, deepcopy(edit.value))
            applied_edits.append(
                {
                    "op": edit.op,
                    "path": edit.path,
                    "previousValue": previous_value,
                    "value": edit.value,
                }
            )

        if not applied_edits:
            raise PageEditorRuntimeError("Requested page edits were a no-op. No draft page version was created.")

        normalized_puck_data = normalize_medusa_one_product_puck_data(deepcopy(next_puck_data))
        refreshed_puck_data = refresh_imported_page_copy_slots(normalized_puck_data) or normalized_puck_data
        finalized_puck_data = (
            backfill_imported_runtime_override_slots(refreshed_puck_data)
            or refreshed_puck_data
        )
        page_summary = AgentThreadsService._summarize_puck_data(finalized_puck_data)

        page_version = self.sites_repo.create_page_version(
            page_id=str(self.target.page.id),
            puck_data=deepcopy(finalized_puck_data),
            provenance={
                "source": "hermes_sidecar",
                "threadId": str(self.target.thread.id),
                "changeSummary": summary,
                "outputMode": "page_orchestrator_tool_patch",
                "baseVersionId": working_version_id,
                "baseVersionStatus": working_status,
            },
            status="draft",
            source_type="hermes_sidecar",
            source_id=str(self.target.thread.id),
            ai_metadata={
                "threadId": str(self.target.thread.id),
                "changeSummary": summary,
                "outputMode": "page_orchestrator_tool_patch",
                "baseVersionId": working_version_id,
                "baseVersionStatus": working_status,
                "appliedAt": datetime.now(timezone.utc).isoformat(),
            },
            diff_summary=summary,
        )
        return {
            "threadId": str(self.target.thread.id),
            "resultingSitePageVersionId": str(page_version.id),
            "pageId": str(self.target.page.id),
            "appliedEditCount": len(applied_edits),
            "appliedEdits": applied_edits,
            "pageSummary": page_summary,
            "puckData": finalized_puck_data,
        }

    def _load_target(self, *, thread_id: str) -> PageEditorTarget:
        thread = self.session.scalars(
            select(AgentThread).where(AgentThread.id == UUID(thread_id))
        ).first()
        if not thread:
            raise PageEditorRuntimeError("Page editor runtime could not find the requested agent thread.")
        if thread.objective_type not in PAGE_CHAT_OBJECTIVE_TYPES:
            raise PageEditorRuntimeError(
                f"Thread '{thread_id}' is not a conversational page-orchestrator thread."
            )
        if not thread.page_id or not thread.site_id:
            raise PageEditorRuntimeError(
                f"Thread '{thread_id}' is not bound to a site page and cannot use page-edit tools."
            )
        agent_threads = AgentThreadsService(
            session=self.session,
            org_id=str(thread.org_id),
            user_id=thread.user_id,
        )
        site, page = agent_threads._require_site_page(
            site_id=str(thread.site_id),
            page_id=str(thread.page_id),
            client_id=str(thread.client_id),
        )
        if site is None or page is None:
            raise PageEditorRuntimeError(
                f"Thread '{thread_id}' is missing its bound site or page."
            )
        return PageEditorTarget(thread=thread, site=site, page=page)

    def _load_working_puck_data(self) -> tuple[dict[str, Any], str | None, str]:
        latest_draft = self.sites_repo.latest_version_for_page(
            page_id=str(self.target.page.id),
            status="draft",
        )
        if latest_draft and isinstance(latest_draft.puck_data, dict):
            puck_data = deepcopy(latest_draft.puck_data)
            refreshed = refresh_imported_page_copy_slots(puck_data) or puck_data
            finalized = backfill_imported_runtime_override_slots(refreshed) or refreshed
            return finalized, str(latest_draft.id), "draft"

        latest_approved = self.sites_repo.latest_version_for_page(
            page_id=str(self.target.page.id),
            status="approved",
        )
        if latest_approved and isinstance(latest_approved.puck_data, dict):
            puck_data = deepcopy(latest_approved.puck_data)
            refreshed = refresh_imported_page_copy_slots(puck_data) or puck_data
            finalized = backfill_imported_runtime_override_slots(refreshed) or refreshed
            return finalized, str(latest_approved.id), "approved"

        if isinstance(self.target.page.adapted_puck_data, dict) and self.target.page.adapted_puck_data:
            puck_data = deepcopy(self.target.page.adapted_puck_data)
            refreshed = refresh_imported_page_copy_slots(puck_data) or puck_data
            finalized = backfill_imported_runtime_override_slots(refreshed) or refreshed
            return finalized, None, "page"

        raise PageEditorRuntimeError(
            f"Page '{self.target.page.id}' does not have a canonical puckData payload to edit."
        )

    @staticmethod
    def _extract_editable_bindings(puck_data: dict[str, Any]) -> list[dict[str, Any]]:
        if not is_imported_template_page_data(puck_data):
            return []

        content = puck_data.get("content")
        imported_page = content[0] if isinstance(content, list) and content else None
        page_props = imported_page.get("props") if isinstance(imported_page, dict) else None
        sections = page_props.get("content") if isinstance(page_props, dict) else None
        if not isinstance(sections, list):
            return []

        bindings: list[dict[str, Any]] = []
        for section_index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            section_props = section.get("props")
            if not isinstance(section_props, dict):
                continue
            blocks = section_props.get("content")
            if not isinstance(blocks, list):
                continue
            section_display_name = str(section_props.get("displayName") or "").strip() or None
            section_type = str(section_props.get("sectionType") or "").strip() or None

            for block_index, block in enumerate(blocks):
                if not isinstance(block, dict):
                    continue
                block_props = block.get("props")
                if not isinstance(block_props, dict):
                    continue
                component_name = str(block_props.get("componentName") or "").strip() or None

                bindings.extend(
                    PageEditorRuntimeService._extract_binding_group(
                        block_props=block_props,
                        section_index=section_index,
                        block_index=block_index,
                        section_display_name=section_display_name,
                        section_type=section_type,
                        component_name=component_name,
                        prop_candidates=("textSlots", "textOverrides"),
                        field_specs=(("text", "text"),),
                    )
                )
                bindings.extend(
                    PageEditorRuntimeService._extract_binding_group(
                        block_props=block_props,
                        section_index=section_index,
                        block_index=block_index,
                        section_display_name=section_display_name,
                        section_type=section_type,
                        component_name=component_name,
                        prop_candidates=("buttonSlots", "buttonOverrides"),
                        field_specs=(("text", "button_text"), ("href", "button_href")),
                    )
                )
                bindings.extend(
                    PageEditorRuntimeService._extract_binding_group(
                        block_props=block_props,
                        section_index=section_index,
                        block_index=block_index,
                        section_display_name=section_display_name,
                        section_type=section_type,
                        component_name=component_name,
                        prop_candidates=("imageSlots", "imageOverrides"),
                        field_specs=(("src", "image_src"), ("alt", "image_alt")),
                    )
                )
        return bindings

    @staticmethod
    def _build_editable_section_index(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        section_map: dict[tuple[str, str, str], dict[str, Any]] = {}
        section_order: list[tuple[str, str, str]] = []

        for binding in bindings:
            section_display_name = str(binding.get("sectionDisplayName") or "").strip()
            section_type = str(binding.get("sectionType") or "").strip()
            component_name = str(binding.get("componentName") or "").strip()
            key = (section_display_name, section_type, component_name)
            if key not in section_map:
                section_map[key] = {
                    "sectionDisplayName": section_display_name or None,
                    "sectionType": section_type or None,
                    "componentName": component_name or None,
                    "bindingCount": 0,
                    "bindingLabels": [],
                    "kinds": [],
                }
                section_order.append(key)

            entry = section_map[key]
            entry["bindingCount"] += 1

            label = str(binding.get("label") or "").strip()
            if label and label not in entry["bindingLabels"]:
                entry["bindingLabels"].append(label)

            kind = str(binding.get("kind") or "").strip()
            if kind and kind not in entry["kinds"]:
                entry["kinds"].append(kind)

        results: list[dict[str, Any]] = []
        for index, key in enumerate(section_order):
            entry = section_map[key]
            results.append(
                {
                    "sectionOrder": index,
                    **entry,
                }
            )
        return results

    @staticmethod
    def _extract_binding_group(
        *,
        block_props: dict[str, Any],
        section_index: int,
        block_index: int,
        section_display_name: str | None,
        section_type: str | None,
        component_name: str | None,
        prop_candidates: tuple[str, ...],
        field_specs: tuple[tuple[str, str], ...],
    ) -> list[dict[str, Any]]:
        group_key = next(
            (
                candidate
                for candidate in prop_candidates
                if isinstance(block_props.get(candidate), list)
            ),
            None,
        )
        items = block_props.get(group_key) if group_key else None
        if not isinstance(items, list):
            return []

        bindings: list[dict[str, Any]] = []
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip() or f"Item {item_index + 1}"
            original_text = str(item.get("originalText") or "").strip() or None
            original_src = str(item.get("originalSrc") or "").strip() or None

            for field_name, kind in field_specs:
                if field_name not in item:
                    continue
                current_value = item.get(field_name)
                if current_value is None:
                    continue
                path = (
                    f"/content/0/props/content/{section_index}"
                    f"/props/content/{block_index}/props/{group_key}/{item_index}/{field_name}"
                )
                bindings.append(
                    {
                        "path": path,
                        "kind": kind,
                        "slotGroup": group_key,
                        "field": field_name,
                        "label": (
                            f"{label} {field_name.replace('_', ' ').title()}"
                            if kind != "text"
                            else label
                        ),
                        "sectionDisplayName": section_display_name,
                        "sectionType": section_type,
                        "componentName": component_name,
                        "currentValue": current_value,
                        "originalText": original_text,
                        "originalSrc": original_src,
                    }
                )
        return bindings

    @staticmethod
    def _read_json_pointer(payload: Any, path: str) -> Any:
        current = payload
        for segment in PageEditorRuntimeService._json_pointer_segments(path):
            if isinstance(current, list):
                index = PageEditorRuntimeService._list_index(segment, path=path)
                try:
                    current = current[index]
                except IndexError as exc:
                    raise PageEditorRuntimeError(
                        f"JSON pointer path '{path}' does not exist at list index {index}."
                    ) from exc
                continue
            if isinstance(current, dict):
                if segment not in current:
                    raise PageEditorRuntimeError(
                        f"JSON pointer path '{path}' does not exist at key '{segment}'."
                    )
                current = current[segment]
                continue
            raise PageEditorRuntimeError(
                f"JSON pointer path '{path}' enters a non-container value before completion."
            )
        return current

    @staticmethod
    def _write_json_pointer(payload: Any, path: str, value: Any) -> None:
        segments = PageEditorRuntimeService._json_pointer_segments(path)
        if not segments:
            raise PageEditorRuntimeError("Editing the root puckData object is not supported.")

        current = payload
        for segment in segments[:-1]:
            if isinstance(current, list):
                index = PageEditorRuntimeService._list_index(segment, path=path)
                try:
                    current = current[index]
                except IndexError as exc:
                    raise PageEditorRuntimeError(
                        f"JSON pointer path '{path}' does not exist at list index {index}."
                    ) from exc
                continue
            if isinstance(current, dict):
                if segment not in current:
                    raise PageEditorRuntimeError(
                        f"JSON pointer path '{path}' does not exist at key '{segment}'."
                    )
                current = current[segment]
                continue
            raise PageEditorRuntimeError(
                f"JSON pointer path '{path}' enters a non-container value before completion."
            )

        last = segments[-1]
        if isinstance(current, list):
            index = PageEditorRuntimeService._list_index(last, path=path)
            try:
                current[index] = value
            except IndexError as exc:
                raise PageEditorRuntimeError(
                    f"JSON pointer path '{path}' does not exist at list index {index}."
                ) from exc
            return
        if isinstance(current, dict):
            if last not in current:
                raise PageEditorRuntimeError(
                    f"JSON pointer path '{path}' does not exist at key '{last}'."
                )
            current[last] = value
            return
        raise PageEditorRuntimeError(
            f"JSON pointer path '{path}' enters a non-container value before completion."
        )

    @staticmethod
    def _json_pointer_segments(path: str) -> list[str]:
        if not isinstance(path, str) or not path.startswith("/"):
            raise PageEditorRuntimeError(
                f"Invalid JSON pointer path '{path}'. Paths must start with '/'."
            )
        if path == "/":
            return [""]
        return [
            segment.replace("~1", "/").replace("~0", "~")
            for segment in path.lstrip("/").split("/")
        ]

    @staticmethod
    def _list_index(segment: str, *, path: str) -> int:
        try:
            return int(segment)
        except ValueError as exc:
            raise PageEditorRuntimeError(
                f"JSON pointer path '{path}' expected a list index but found '{segment}'."
            ) from exc
