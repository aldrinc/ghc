from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Generator, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AgentRunStatusEnum
from app.db.models import (
    AgentArtifact,
    AgentRun,
    Client,
    Product,
    Site,
    SitePage,
    SitePageVersion,
)
from app.db.repositories.agent_artifacts import AgentArtifactsRepository
from app.db.repositories.agent_runs import AgentRunsRepository
from app.db.repositories.agent_threads import (
    AgentThreadsRepository,
    ApprovalItemsRepository,
    RuntimeSessionsRepository,
    SitePageContextBindingsRepository,
)
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.services.hermes_sidecar import HermesSidecarError, HermesSidecarService
from app.services.site_import_archive import (
    backfill_imported_runtime_override_slots,
    refresh_imported_page_copy_slots,
)
from app.services.site_page_ai import is_imported_template_page_data
from app.services.site_page_copy_agent import (
    SitePageCopyAgentError,
    SitePageCopyAgentResult,
    SitePageCopySlot,
    SitePageCopySlotBatch,
    build_site_page_copy_prompt,
    chunk_site_page_copy_batches,
    extract_site_page_copy_slots,
    group_site_page_copy_slots,
    parse_site_page_copy_agent_response,
    summarize_site_page_copy_assignments,
)
from app.services.site_templates import normalize_medusa_one_product_puck_data
from app.services.skills_runtime_registry import SkillsRuntimeRegistryService


class AgentThreadsServiceError(ValueError):
    """Raised when the local Hermes prototype request is invalid."""


PAGE_AGENT_OBJECTIVE_TYPES = {"page_copy_agent"}
PAGE_CHAT_OBJECTIVE_TYPES = {"page_orchestrator"}
SITE_BOUND_OBJECTIVE_TYPES = PAGE_AGENT_OBJECTIVE_TYPES | PAGE_CHAT_OBJECTIVE_TYPES
PAGE_COPY_MAX_SLOTS_PER_BATCH = 8


class AgentThreadsService:
    def __init__(self, *, session: Session, org_id: str, user_id: str) -> None:
        self.session = session
        self.org_id = org_id
        self.user_id = user_id
        self.threads_repo = AgentThreadsRepository(session)
        self.runtime_repo = RuntimeSessionsRepository(session)
        self.bindings_repo = SitePageContextBindingsRepository(session)
        self.approvals_repo = ApprovalItemsRepository(session)
        self.runs_repo = AgentRunsRepository(session)
        self.artifacts_repo = AgentArtifactsRepository(session)
        self.sites_repo = SitesRuntimeRepository(session)
        self.hermes = HermesSidecarService()

    def create_thread(
        self,
        *,
        client_id: str,
        product_id: str,
        agent_profile: str,
        objective_type: str,
        bundle_key: str,
        runtime_profile_key: str | None = None,
        strategy_bundle_id: str | None = None,
        title: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        site_id: str | None = None,
        page_id: str | None = None,
    ) -> dict[str, Any]:
        client = self._require_client(client_id=client_id)
        product = self._require_product(product_id=product_id, client_id=client_id)
        site, page = self._require_site_page(site_id=site_id, page_id=page_id, client_id=client_id)
        if objective_type in SITE_BOUND_OBJECTIVE_TYPES and (not site or not page):
            raise AgentThreadsServiceError(
                f"Objective type '{objective_type}' requires a site-bound page target."
            )
        if objective_type in PAGE_AGENT_OBJECTIVE_TYPES and page:
            base_puck = self._load_page_agent_base_puck_data(page=page)
            if not is_imported_template_page_data(base_puck):
                raise AgentThreadsServiceError(
                    "Page copy agent requires an imported-template page with ImportedPage top-level content."
                )

        thread_uuid = uuid4()
        existing_binding = (
            self.bindings_repo.get_by_page(page_id=str(page.id), org_id=self.org_id)
            if page is not None
            else None
        )
        resolved_runtime_profile_key = runtime_profile_key or (
            existing_binding.runtime_profile_key if existing_binding else None
        )
        resolved_strategy_bundle_id = strategy_bundle_id or (
            str(existing_binding.strategy_bundle_id) if existing_binding and existing_binding.strategy_bundle_id else None
        )
        if (
            resolved_runtime_profile_key is None
            and objective_type in PAGE_AGENT_OBJECTIVE_TYPES
            and resolved_strategy_bundle_id is not None
        ):
            resolved_runtime_profile_key = "page-copy"
        page_context = (
            self._build_page_context(
                site=site,
                page=page,
                strategy_bundle_id=resolved_strategy_bundle_id,
                runtime_profile_key=resolved_runtime_profile_key,
            )
            if site and page
            else None
        )
        projection, bundle_manifest, runtime_bundle_export_id = self._resolve_projection(
            client_id=client_id,
            product_id=product_id,
            thread_id=str(thread_uuid),
            agent_profile=agent_profile,
            bundle_key=bundle_key,
            runtime_profile_key=resolved_runtime_profile_key,
            strategy_bundle_id=resolved_strategy_bundle_id,
            objective_type=objective_type,
            page_context=page_context,
        )
        if page_context is not None:
            self._sync_runtime_page_context(
                runtime_home=projection.runtime_home,
                page_context=page_context,
            )
        resolved_toolsets = self._resolve_runtime_toolsets(
            thread=SimpleNamespace(objective_type=objective_type, page_id=page_id),
            projection_toolsets=projection.toolsets,
        )

        thread = self.threads_repo.create_thread(
            thread_id=str(thread_uuid),
            org_id=self.org_id,
            user_id=self.user_id,
            client_id=client_id,
            product_id=product_id,
            site_id=site_id,
            page_id=page_id,
            agent_profile=agent_profile,
            objective_type=objective_type,
            title=title,
            bundle_key=bundle_key,
            runtime_profile_key=resolved_runtime_profile_key,
            strategy_bundle_id=resolved_strategy_bundle_id,
            bundle_manifest=bundle_manifest,
            metadata_json={
                **(metadata_json or {}),
                "runtimeBundleExportId": runtime_bundle_export_id,
            },
        )
        runtime_session = self.runtime_repo.create_session(
            thread_id=str(thread.id),
            org_id=self.org_id,
            client_id=client_id,
            product_id=product_id,
            agent_profile=agent_profile,
            scope_key=f"{self.org_id}:{client_id}:{product_id}:{agent_profile}:{thread.id}",
            runtime_home=str(projection.runtime_home),
            projection_hash=projection.projection_hash,
            toolsets=resolved_toolsets,
        )

        if site and page:
            self.bindings_repo.upsert_binding(
                org_id=self.org_id,
                client_id=client_id,
                product_id=product_id,
                site_id=str(site.id),
                page_id=str(page.id),
                bundle_key=bundle_key,
                strategy_bundle_id=resolved_strategy_bundle_id,
                runtime_profile_key=resolved_runtime_profile_key,
                binding_json=page_context or {},
            )

        self.session.commit()
        return self.get_thread_detail(thread_id=str(thread.id))

    def get_or_create_page_thread(
        self,
        *,
        client_id: str,
        product_id: str,
        site_id: str,
        page_id: str,
        agent_profile: str,
        objective_type: str,
        title: str | None = None,
        bundle_key: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        force_new: bool = False,
    ) -> dict[str, Any]:
        existing_thread = self.threads_repo.find_latest_for_page(
            org_id=self.org_id,
            client_id=client_id,
            product_id=product_id,
            site_id=site_id,
            page_id=page_id,
            objective_type=objective_type,
            agent_profile=agent_profile,
        )
        if not force_new:
            if existing_thread is not None:
                return self.get_thread_detail(thread_id=str(existing_thread.id))

        binding = self.bindings_repo.get_by_page(page_id=page_id, org_id=self.org_id)
        binding_is_active = binding is not None and binding.status == "active"
        resolved_bundle_key = (
            bundle_key
            or (binding.bundle_key if binding else None)
            or (existing_thread.bundle_key if existing_thread else None)
            or ""
        ).strip() or None
        if resolved_bundle_key is None:
            raise AgentThreadsServiceError(
                "No active page runtime binding was found for this site page. Bind the page to a runtime bundle before starting the page agent."
            )
        if binding is not None and not binding_is_active and existing_thread is None:
            raise AgentThreadsServiceError(
                "The page runtime binding exists but is not active. Reactivate the binding before starting the page agent."
            )

        return self.create_thread(
            client_id=client_id,
            product_id=product_id,
            agent_profile=agent_profile,
            objective_type=objective_type,
            bundle_key=resolved_bundle_key,
            runtime_profile_key=(
                binding.runtime_profile_key
                if binding_is_active
                else existing_thread.runtime_profile_key if binding is None and existing_thread else None
            ),
            strategy_bundle_id=(
                str(binding.strategy_bundle_id)
                if binding_is_active and binding.strategy_bundle_id
                else str(existing_thread.strategy_bundle_id)
                if binding is None and existing_thread and existing_thread.strategy_bundle_id
                else None
            ),
            title=title,
            metadata_json=metadata_json,
            site_id=site_id,
            page_id=page_id,
        )

    def reset_runtime_session(self, *, thread_id: str) -> dict[str, Any]:
        self._require_thread(thread_id=thread_id)
        runtime_session = self.runtime_repo.get_by_thread(thread_id=thread_id)
        if not runtime_session:
            raise AgentThreadsServiceError("Runtime session not found for thread.")

        runtime_session.hermes_session_id = None
        runtime_session.status = "ready"
        runtime_session.last_error = None
        self.runtime_repo.update_session(runtime_session=runtime_session)
        self.session.commit()
        return self.get_thread_detail(thread_id=thread_id)

    def get_thread_detail(self, *, thread_id: str) -> dict[str, Any]:
        thread = self._require_thread(thread_id=thread_id)
        runtime_session = self.runtime_repo.get_by_thread(thread_id=thread_id)
        if not runtime_session:
            raise AgentThreadsServiceError("Runtime session not found for thread.")
        turns = self.threads_repo.list_turns(thread_id=thread_id)
        approvals = self.approvals_repo.list_for_thread(thread_id=thread_id)
        return {
            "thread": self._serialize_thread(thread),
            "runtimeSession": self._serialize_runtime_session(runtime_session),
            "turns": [self._serialize_turn(turn) for turn in turns],
            "approvals": [self._serialize_approval(item) for item in approvals],
        }

    def get_thread_validation(self, *, thread_id: str) -> dict[str, Any]:
        thread = self._require_thread(thread_id=thread_id)
        runtime_session = self.runtime_repo.get_by_thread(thread_id=thread_id)
        if not runtime_session:
            raise AgentThreadsServiceError("Runtime session not found for thread.")

        turns = self.threads_repo.list_turns(thread_id=thread_id)
        approvals = self.approvals_repo.list_for_thread(thread_id=thread_id)
        page_binding = None
        if thread.page_id:
            binding = self.bindings_repo.get_by_page(page_id=str(thread.page_id), org_id=self.org_id)
            if binding:
                page_binding = {
                    "id": str(binding.id),
                    "status": binding.status,
                    "bundleKey": binding.bundle_key,
                    "strategyBundleId": str(binding.strategy_bundle_id) if binding.strategy_bundle_id else None,
                    "runtimeProfileKey": binding.runtime_profile_key,
                    "binding": binding.binding_json or {},
                    "createdAt": binding.created_at.isoformat(),
                    "updatedAt": binding.updated_at.isoformat(),
                }

        validation_runs: list[dict[str, Any]] = []
        for index, turn in enumerate(turns):
            if turn.role != "assistant" or not turn.run_id:
                continue
            run = self.runs_repo.get(run_id=str(turn.run_id), org_id=self.org_id)
            artifact = self._load_artifact(artifact_id=str(turn.artifact_id)) if turn.artifact_id else None
            site_page_version = (
                self.sites_repo.get_version(version_id=str(turn.site_page_version_id))
                if turn.site_page_version_id
                else None
            )
            user_turn = next(
                (candidate for candidate in reversed(turns[:index]) if candidate.role == "user"),
                None,
            )

            artifact_data = artifact.data_json if artifact else {}
            artifact_content = artifact_data.get("content") if artifact else None
            artifact_puck_data = artifact_data.get("puckData") if artifact else None
            page_body = self._extract_site_page_version_body(site_page_version) if site_page_version else None
            output_mode = (
                ((run.outputs_json or {}).get("outputMode") if run else None)
                or artifact_data.get("outputMode")
                or "markdown"
            )
            assistant_content = turn.content.strip()
            validation_runs.append(
                {
                    "run": self._serialize_run(run) if run else None,
                    "userTurn": self._serialize_turn(user_turn) if user_turn else None,
                    "assistantTurn": self._serialize_turn(turn),
                    "artifact": self._serialize_artifact(artifact) if artifact else None,
                    "sitePageVersion": self._serialize_site_page_version(site_page_version)
                    if site_page_version
                    else None,
                    "checks": {
                        "outputMode": output_mode,
                        "assistantStartsWithH1": assistant_content.startswith("# ")
                        if output_mode == "markdown" and thread.page_id
                        else None,
                        "assistantMatchesArtifact": assistant_content == artifact_content
                        if output_mode == "markdown" and artifact_content is not None
                        else None,
                        "assistantMatchesSitePageVersion": assistant_content == page_body
                        if output_mode == "markdown" and page_body is not None
                        else None,
                        "assistantMessagePresent": bool(assistant_content)
                        if output_mode == "page_copy_slots"
                        else None,
                        "artifactHasPuckData": isinstance(artifact_puck_data, dict)
                        if output_mode == "page_copy_slots"
                        else None,
                        "assignmentCount": len(artifact_data.get("slotAssignments") or [])
                        if output_mode == "page_copy_slots"
                        else None,
                        "assignmentCountMatchesSlotCount": len(artifact_data.get("slotAssignments") or [])
                        == artifact_data.get("slotCount")
                        if output_mode == "page_copy_slots"
                        else None,
                        "artifactPuckDataMatchesSitePageVersion": artifact_puck_data
                        == (site_page_version.puck_data if site_page_version else None)
                        if output_mode == "page_copy_slots" and site_page_version is not None
                        else None,
                        "sitePageIsImportedTemplate": is_imported_template_page_data(
                            site_page_version.puck_data if site_page_version else None
                        )
                        if output_mode == "page_copy_slots" and site_page_version is not None
                        else None,
                    },
                }
            )

        return {
            "thread": self._serialize_thread(thread),
            "runtimeSession": self._serialize_runtime_session(runtime_session),
            "turns": [self._serialize_turn(turn) for turn in turns],
            "approvals": [self._serialize_approval(item) for item in approvals],
            "validation": {
                "runtime": {
                    **self.hermes.runtime_summary(),
                    "runtimeHome": runtime_session.runtime_home,
                    "hermesSessionId": runtime_session.hermes_session_id,
                    "projectionHash": runtime_session.projection_hash,
                    "toolsets": runtime_session.toolsets or [],
                    "lastError": runtime_session.last_error,
                    "lastUsedAt": runtime_session.last_used_at.isoformat(),
                },
                "pageContextBinding": page_binding,
                "runs": validation_runs,
            },
        }

    def post_message(self, *, thread_id: str, content: str) -> dict[str, Any]:
        thread = self._require_thread(thread_id=thread_id)
        runtime_session = self.runtime_repo.get_by_thread(thread_id=thread_id)
        if not runtime_session:
            raise AgentThreadsServiceError("Runtime session not found for thread.")

        page_context = None
        site = None
        page = None
        binding = None
        if thread.site_id and thread.page_id:
            site, page = self._require_site_page(
                site_id=str(thread.site_id),
                page_id=str(thread.page_id),
                client_id=str(thread.client_id),
            )
            if not site or not page:
                raise AgentThreadsServiceError("Page-bound thread is missing its site or page.")
            binding = self.bindings_repo.get_by_page(page_id=str(page.id), org_id=self.org_id)
            if not binding or binding.status != "active":
                raise AgentThreadsServiceError(
                    "Active site_page_context_binding not found for this page-bound thread."
                )
            page_context = self._build_page_context(
                site=site,
                page=page,
                strategy_bundle_id=(
                    str(thread.strategy_bundle_id)
                    if thread.strategy_bundle_id
                    else (str(binding.strategy_bundle_id) if binding and binding.strategy_bundle_id else None)
                ),
                runtime_profile_key=thread.runtime_profile_key or (binding.runtime_profile_key if binding else None),
            )

        projection, bundle_manifest, runtime_bundle_export_id = self._resolve_projection(
            client_id=str(thread.client_id),
            product_id=str(thread.product_id),
            thread_id=str(thread.id),
            agent_profile=thread.agent_profile,
            bundle_key=thread.bundle_key,
            runtime_profile_key=thread.runtime_profile_key or (binding.runtime_profile_key if binding else None),
            strategy_bundle_id=(
                str(thread.strategy_bundle_id)
                if thread.strategy_bundle_id
                else (str(binding.strategy_bundle_id) if binding and binding.strategy_bundle_id else None)
            ),
            objective_type=thread.objective_type,
            page_context=page_context,
        )
        if page_context is not None:
            self._sync_runtime_page_context(
                runtime_home=projection.runtime_home,
                page_context=page_context,
            )
        resolved_toolsets = self._resolve_runtime_toolsets(
            thread=thread,
            projection_toolsets=projection.toolsets,
        )
        runtime_session.runtime_home = str(projection.runtime_home)
        runtime_session.projection_hash = projection.projection_hash
        runtime_session.toolsets = resolved_toolsets
        runtime_session.status = "ready"
        runtime_session.last_error = None
        self.runtime_repo.update_session(runtime_session=runtime_session)
        thread.bundle_manifest = bundle_manifest
        thread.metadata_json = {
            **(thread.metadata_json or {}),
            "runtimeBundleExportId": runtime_bundle_export_id,
        }
        self.threads_repo.update_thread(thread=thread)

        output_mode = self._resolve_output_mode(thread=thread)
        base_puck = None
        slots = None
        slot_batches = None
        if output_mode == "page_copy_slots":
            if page is None or site is None:
                raise AgentThreadsServiceError("Page copy agent requires a bound site page.")
            base_puck = self._load_page_agent_base_puck_data(page=page)
            slots = extract_site_page_copy_slots(base_puck)
            slot_batches = chunk_site_page_copy_batches(
                group_site_page_copy_slots(slots),
                max_slots_per_batch=PAGE_COPY_MAX_SLOTS_PER_BATCH,
            )
            query = content.strip()
        else:
            query = self._build_query(
                thread_id=thread_id,
                thread=thread,
                content=content,
                runtime_home=projection.runtime_home,
                site=site,
                page=page,
            )
        user_seq = self.threads_repo.next_turn_seq(thread_id=thread_id)
        self.threads_repo.create_turn(
            thread_id=thread_id,
            seq=user_seq,
            role="user",
            content=content.strip(),
        )
        runtime_summary = {
            **self.hermes.runtime_summary(),
            "resolvedToolsets": resolved_toolsets,
        }

        run = self.runs_repo.create_run(
            org_id=self.org_id,
            user_id=self.user_id,
            client_id=str(thread.client_id),
            objective_type=thread.objective_type,
            model=runtime_summary["model"],
            ruleset_version="hermes-sidecar-v1",
            inputs_json={
                "threadId": thread_id,
                "bundleKey": thread.bundle_key,
                "agentProfile": thread.agent_profile,
                "pageBound": bool(thread.page_id),
                "outputMode": output_mode,
                "prompt": query,
                "slotCount": len(slots) if slots is not None else None,
                "slotBatchCount": len(slot_batches) if slot_batches is not None else None,
                "runtime": runtime_summary,
            },
        )

        page_result: SitePageCopyAgentResult | None = None
        run_usage = self._empty_usage()
        try:
            if output_mode == "page_copy_slots":
                if base_puck is None or slots is None or slot_batches is None or site is None or page is None:
                    raise AgentThreadsServiceError("Page copy agent did not initialize its slot batches.")
                page_result, batch_metadata, hermes_session_id, raw_output_preview, run_usage = self._run_page_copy_batches(
                    thread_id=thread_id,
                    thread=thread,
                    user_content=content,
                    runtime_home=projection.runtime_home,
                    hermes_session_id=runtime_session.hermes_session_id,
                    site=site,
                    page=page,
                    base_puck_data=base_puck,
                    slots=slots,
                    slot_batches=slot_batches,
                )
                raw_response_text = page_result.assistant_message
            else:
                run_result = self.hermes.run_turn(
                    runtime_home=projection.runtime_home,
                    query=query,
                    hermes_session_id=runtime_session.hermes_session_id,
                    toolsets=resolved_toolsets,
                )
                hermes_session_id = run_result.hermes_session_id
                raw_response_text = run_result.response_text
                raw_output_preview = run_result.raw_output[:2000]
                run_usage = run_result.usage
                batch_metadata = None
        except (HermesSidecarError, SitePageCopyAgentError) as exc:
            runtime_session.status = "error"
            runtime_session.last_error = str(exc)
            self.runtime_repo.update_session(runtime_session=runtime_session)
            self.runs_repo.finish_run(
                run_id=str(run.id),
                status=AgentRunStatusEnum.failed,
                error=str(exc),
            )
            self.session.commit()
            raise AgentThreadsServiceError(str(exc)) from exc

        runtime_session.hermes_session_id = hermes_session_id
        runtime_session.status = "ready"
        runtime_session.last_error = None
        self.runtime_repo.update_session(runtime_session=runtime_session)

        response_text = None
        response_normalization: dict[str, Any] = {}
        page_summary = None

        if output_mode == "page_copy_slots":
            if page is None or slots is None or page_result is None:
                raise AgentThreadsServiceError("Page copy agent requires a bound site page.")
            normalized_puck_data = normalize_medusa_one_product_puck_data(
                deepcopy(page_result.puck_data)
            )
            page_result = SitePageCopyAgentResult(
                assistant_message=page_result.assistant_message,
                assignments=page_result.assignments,
                puck_data=normalized_puck_data,
            )
            page_summary = self._summarize_puck_data(page_result.puck_data)
            artifact = self.artifacts_repo.create(
                run_id=str(run.id),
                kind="page_copy_puck_draft",
                key=f"thread:{thread_id}",
                data_json={
                    "threadId": thread_id,
                    "objectiveType": thread.objective_type,
                    "outputMode": output_mode,
                    "assistantMessage": page_result.assistant_message,
                    "puckData": page_result.puck_data,
                    "pageSummary": page_summary,
                    "slotCount": len(slots),
                    "slotAssignments": summarize_site_page_copy_assignments(
                        slots=slots,
                        assignments=page_result.assignments,
                    ),
                    "slotBatches": batch_metadata,
                    "usage": run_usage,
                    "bundleKey": thread.bundle_key,
                    "hermesSessionId": hermes_session_id,
                },
            )
            page_version = self._create_structured_page_draft_version(
                page_id=str(thread.page_id),
                puck_data=page_result.puck_data,
                assistant_message=page_result.assistant_message,
                thread_id=thread_id,
                run_id=str(run.id),
                hermes_session_id=hermes_session_id,
            )
            assistant_content = page_result.assistant_message
            response_preview = assistant_content[:2000]
        else:
            response_text = self._normalize_response_text(
                response_text=raw_response_text,
                require_h1=bool(thread.page_id and thread.objective_type not in PAGE_CHAT_OBJECTIVE_TYPES),
            )
            response_normalization = {
                "requiredH1": bool(thread.page_id and thread.objective_type not in PAGE_CHAT_OBJECTIVE_TYPES),
                "trimmedLeadingText": response_text != raw_response_text.strip(),
            }
            page_version = None
            page_summary = None
            materialized_puck_data = None
            try:
                if (
                    thread.page_id
                    and thread.objective_type in PAGE_CHAT_OBJECTIVE_TYPES
                    and page is not None
                    and page_context is not None
                ):
                    if self._runtime_page_context_was_mutated(
                        runtime_home=projection.runtime_home,
                        original_page_context=page_context,
                    ):
                        raise AgentThreadsServiceError(
                            "Hermes mutated runtime/page_context.json during a page-orchestrator run. "
                            "Direct page edits must go through the explicit MCP page editor tools."
                        )
                    page_version = self._resolve_page_orchestrator_tool_page_version(
                        page=page,
                        thread_id=thread_id,
                        run_started_at=run.started_at,
                    )
                    if page_version and isinstance(page_version.puck_data, dict):
                        materialized_puck_data = deepcopy(page_version.puck_data)
                        page_summary = self._summarize_puck_data(materialized_puck_data)
            except AgentThreadsServiceError as exc:
                runtime_session.status = "error"
                runtime_session.last_error = str(exc)
                self.runtime_repo.update_session(runtime_session=runtime_session)
                self.runs_repo.finish_run(
                    run_id=str(run.id),
                    status=AgentRunStatusEnum.failed,
                    error=str(exc),
                )
                self.session.commit()
                raise
            artifact = self.artifacts_repo.create(
                run_id=str(run.id),
                kind=(
                    "page_chat_response"
                    if thread.page_id and thread.objective_type in PAGE_CHAT_OBJECTIVE_TYPES
                    else "copy_markdown_draft"
                ),
                key=f"thread:{thread_id}",
                data_json={
                    "threadId": thread_id,
                    "objectiveType": thread.objective_type,
                    "outputMode": output_mode,
                    "content": response_text,
                    "bundleKey": thread.bundle_key,
                    "hermesSessionId": hermes_session_id,
                    "usage": run_usage,
                    "normalization": response_normalization,
                    "puckData": materialized_puck_data,
                    "pageSummary": page_summary,
                    "materializedPageEdit": bool(page_version),
                },
            )
            if thread.page_id and thread.objective_type not in PAGE_CHAT_OBJECTIVE_TYPES:
                page_version = self._create_page_draft_version(
                    page_id=str(thread.page_id),
                    response_text=response_text,
                    thread_id=thread_id,
                    run_id=str(run.id),
                    hermes_session_id=hermes_session_id,
                )
            assistant_content = response_text
            response_preview = response_text[:2000]

        assistant_seq = self.threads_repo.next_turn_seq(thread_id=thread_id)
        self.threads_repo.create_turn(
            thread_id=thread_id,
            seq=assistant_seq,
            role="assistant",
            content=assistant_content,
            run_id=str(run.id),
            artifact_id=str(artifact.id),
            site_page_version_id=str(page_version.id) if page_version else None,
            metadata_json={
                "bundleKey": thread.bundle_key,
                "hermesSessionId": hermes_session_id,
                "outputMode": output_mode,
                "rawOutputPreview": raw_output_preview,
                "rawAssistantResponsePreview": raw_response_text[:2000],
                "usage": run_usage,
                "responseNormalization": response_normalization,
                "pageSummary": page_summary,
                "slotBatches": batch_metadata,
            },
        )

        self.runs_repo.finish_run(
            run_id=str(run.id),
            status=AgentRunStatusEnum.completed,
            outputs_json={
                "artifactId": str(artifact.id),
                "sitePageVersionId": str(page_version.id) if page_version else None,
                "hermesSessionId": hermes_session_id,
                "outputMode": output_mode,
                "responsePreview": response_preview,
                "assistantMessagePreview": assistant_content[:2000],
                "usage": run_usage,
                "normalization": response_normalization,
                "pageSummary": page_summary,
                "slotBatches": batch_metadata,
                "slotCount": len(artifact.data_json.get("slotAssignments") or [])
                if output_mode == "page_copy_slots"
                else None,
            },
        )

        self.session.commit()
        return self.get_thread_detail(thread_id=thread_id)

    def stream_message(self, *, thread_id: str, content: str) -> Generator[dict[str, Any], None, None]:
        thread = self._require_thread(thread_id=thread_id)
        runtime_session = self.runtime_repo.get_by_thread(thread_id=thread_id)
        if not runtime_session:
            raise AgentThreadsServiceError("Runtime session not found for thread.")

        output_mode = self._resolve_output_mode(thread=thread)
        if output_mode == "page_copy_slots":
            raise AgentThreadsServiceError(
                "Live streaming is only supported for the conversational Hermes page-orchestrator path."
            )

        page_context = None
        site = None
        page = None
        binding = None
        if thread.site_id and thread.page_id:
            site, page = self._require_site_page(
                site_id=str(thread.site_id),
                page_id=str(thread.page_id),
                client_id=str(thread.client_id),
            )
            if not site or not page:
                raise AgentThreadsServiceError("Page-bound thread is missing its site or page.")
            binding = self.bindings_repo.get_by_page(page_id=str(page.id), org_id=self.org_id)
            if not binding or binding.status != "active":
                raise AgentThreadsServiceError(
                    "Active site_page_context_binding not found for this page-bound thread."
                )
            page_context = self._build_page_context(
                site=site,
                page=page,
                strategy_bundle_id=(
                    str(thread.strategy_bundle_id)
                    if thread.strategy_bundle_id
                    else (str(binding.strategy_bundle_id) if binding and binding.strategy_bundle_id else None)
                ),
                runtime_profile_key=thread.runtime_profile_key or (binding.runtime_profile_key if binding else None),
            )

        yield {
            "type": "status",
            "stage": "prepare",
            "message": "Preparing the Hermes runtime for this page thread.",
        }

        projection, bundle_manifest, runtime_bundle_export_id = self._resolve_projection(
            client_id=str(thread.client_id),
            product_id=str(thread.product_id),
            thread_id=thread_id,
            agent_profile=thread.agent_profile,
            bundle_key=thread.bundle_key,
            runtime_profile_key=thread.runtime_profile_key or (binding.runtime_profile_key if binding else None),
            strategy_bundle_id=(
                str(thread.strategy_bundle_id)
                if thread.strategy_bundle_id
                else (str(binding.strategy_bundle_id) if binding and binding.strategy_bundle_id else None)
            ),
            objective_type=thread.objective_type,
            page_context=page_context,
        )
        if page_context is not None:
            self._sync_runtime_page_context(
                runtime_home=projection.runtime_home,
                page_context=page_context,
            )
        resolved_toolsets = self._resolve_runtime_toolsets(
            thread=thread,
            projection_toolsets=projection.toolsets,
        )
        runtime_session.runtime_home = str(projection.runtime_home)
        runtime_session.projection_hash = projection.projection_hash
        runtime_session.toolsets = resolved_toolsets
        runtime_session.status = "ready"
        runtime_session.last_error = None
        self.runtime_repo.update_session(runtime_session=runtime_session)
        thread.bundle_manifest = bundle_manifest
        thread.metadata_json = {
            **(thread.metadata_json or {}),
            "runtimeBundleExportId": runtime_bundle_export_id,
        }
        self.threads_repo.update_thread(thread=thread)

        query = self._build_query(
            thread_id=thread_id,
            thread=thread,
            content=content,
            runtime_home=projection.runtime_home,
            site=site,
            page=page,
        )
        user_seq = self.threads_repo.next_turn_seq(thread_id=thread_id)
        self.threads_repo.create_turn(
            thread_id=thread_id,
            seq=user_seq,
            role="user",
            content=content.strip(),
        )
        runtime_summary = {
            **self.hermes.runtime_summary(),
            "resolvedToolsets": resolved_toolsets,
        }

        run = self.runs_repo.create_run(
            org_id=self.org_id,
            user_id=self.user_id,
            client_id=str(thread.client_id),
            objective_type=thread.objective_type,
            model=runtime_summary["model"],
            ruleset_version="hermes-sidecar-v1",
            inputs_json={
                "threadId": thread_id,
                "bundleKey": thread.bundle_key,
                "agentProfile": thread.agent_profile,
                "pageBound": bool(thread.page_id),
                "outputMode": output_mode,
                "prompt": query,
                "runtime": runtime_summary,
            },
        )

        self.session.commit()
        yield {
            "type": "start",
            "threadId": thread_id,
            "runId": str(run.id),
            "objectiveType": thread.objective_type,
            "outputMode": output_mode,
            "message": "Hermes is working on the page.",
        }

        try:
            run_result = yield from self.hermes.stream_turn(
                runtime_home=projection.runtime_home,
                query=query,
                hermes_session_id=runtime_session.hermes_session_id,
                toolsets=resolved_toolsets,
            )
        except HermesSidecarError as exc:
            runtime_session.status = "error"
            runtime_session.last_error = str(exc)
            self.runtime_repo.update_session(runtime_session=runtime_session)
            self.runs_repo.finish_run(
                run_id=str(run.id),
                status=AgentRunStatusEnum.failed,
                error=str(exc),
            )
            self.session.commit()
            yield {
                "type": "error",
                "runId": str(run.id),
                "message": str(exc),
            }
            return

        runtime_session.hermes_session_id = run_result.hermes_session_id
        runtime_session.status = "ready"
        runtime_session.last_error = None
        self.runtime_repo.update_session(runtime_session=runtime_session)

        response_text = self._normalize_response_text(
            response_text=run_result.response_text,
            require_h1=bool(thread.page_id and thread.objective_type not in PAGE_CHAT_OBJECTIVE_TYPES),
        )
        response_normalization = {
            "requiredH1": bool(thread.page_id and thread.objective_type not in PAGE_CHAT_OBJECTIVE_TYPES),
            "trimmedLeadingText": response_text != run_result.response_text.strip(),
        }
        page_version = None
        page_summary = None
        materialized_puck_data = None
        try:
            if (
                thread.page_id
                and thread.objective_type in PAGE_CHAT_OBJECTIVE_TYPES
                and page is not None
                and page_context is not None
            ):
                if self._runtime_page_context_was_mutated(
                    runtime_home=projection.runtime_home,
                    original_page_context=page_context,
                ):
                    raise AgentThreadsServiceError(
                        "Hermes mutated runtime/page_context.json during a page-orchestrator run. "
                        "Direct page edits must go through the explicit MCP page editor tools."
                    )
                page_version = self._resolve_page_orchestrator_tool_page_version(
                    page=page,
                    thread_id=thread_id,
                    run_started_at=run.started_at,
                )
                if page_version and isinstance(page_version.puck_data, dict):
                    materialized_puck_data = deepcopy(page_version.puck_data)
                    page_summary = self._summarize_puck_data(materialized_puck_data)
        except AgentThreadsServiceError as exc:
            runtime_session.status = "error"
            runtime_session.last_error = str(exc)
            self.runtime_repo.update_session(runtime_session=runtime_session)
            self.runs_repo.finish_run(
                run_id=str(run.id),
                status=AgentRunStatusEnum.failed,
                error=str(exc),
            )
            self.session.commit()
            yield {
                "type": "error",
                "runId": str(run.id),
                "message": str(exc),
            }
            return
        artifact = self.artifacts_repo.create(
            run_id=str(run.id),
            kind=(
                "page_chat_response"
                if thread.page_id and thread.objective_type in PAGE_CHAT_OBJECTIVE_TYPES
                else "copy_markdown_draft"
            ),
            key=f"thread:{thread_id}",
            data_json={
                "threadId": thread_id,
                "objectiveType": thread.objective_type,
                "outputMode": output_mode,
                "content": response_text,
                "bundleKey": thread.bundle_key,
                "hermesSessionId": run_result.hermes_session_id,
                "usage": run_result.usage,
                "normalization": response_normalization,
                "puckData": materialized_puck_data,
                "pageSummary": page_summary,
                "materializedPageEdit": bool(page_version),
            },
        )
        if thread.page_id and thread.objective_type not in PAGE_CHAT_OBJECTIVE_TYPES:
            page_version = self._create_page_draft_version(
                page_id=str(thread.page_id),
                response_text=response_text,
                thread_id=thread_id,
                run_id=str(run.id),
                hermes_session_id=run_result.hermes_session_id,
            )

        assistant_seq = self.threads_repo.next_turn_seq(thread_id=thread_id)
        self.threads_repo.create_turn(
            thread_id=thread_id,
            seq=assistant_seq,
            role="assistant",
            content=response_text,
            run_id=str(run.id),
            artifact_id=str(artifact.id),
            site_page_version_id=str(page_version.id) if page_version else None,
            metadata_json={
                "bundleKey": thread.bundle_key,
                "hermesSessionId": run_result.hermes_session_id,
                "outputMode": output_mode,
                "rawOutputPreview": run_result.raw_output[:2000],
                "rawAssistantResponsePreview": run_result.response_text[:2000],
                "usage": run_result.usage,
                "responseNormalization": response_normalization,
                "pageSummary": page_summary,
            },
        )

        self.runs_repo.finish_run(
            run_id=str(run.id),
            status=AgentRunStatusEnum.completed,
            outputs_json={
                "artifactId": str(artifact.id),
                "sitePageVersionId": str(page_version.id) if page_version else None,
                "hermesSessionId": run_result.hermes_session_id,
                "outputMode": output_mode,
                "responsePreview": response_text[:2000],
                "assistantMessagePreview": response_text[:2000],
                "usage": run_result.usage,
                "normalization": response_normalization,
                "pageSummary": page_summary,
            },
        )

        self.session.commit()
        yield {
            "type": "done",
            "runId": str(run.id),
            "threadId": thread_id,
            "hermesSessionId": run_result.hermes_session_id,
            "usage": run_result.usage,
            "detail": self.get_thread_detail(thread_id=thread_id),
        }

    def resolve_approval(
        self,
        *,
        thread_id: str,
        target_kind: str,
        target_id: str,
        decision: str,
        notes: str | None,
    ) -> dict[str, Any]:
        thread = self._require_thread(thread_id=thread_id)
        artifact = None
        site_page_version = None

        if target_kind == "artifact":
            artifact = self._require_thread_artifact(thread_id=thread_id, artifact_id=target_id)
        elif target_kind == "site_page_version":
            site_page_version = self._require_thread_page_version(thread=thread, page_version_id=target_id)
        else:
            raise AgentThreadsServiceError(
                f"Unsupported targetKind '{target_kind}'. Expected 'artifact' or 'site_page_version'."
            )

        approval = self.approvals_repo.create(
            org_id=self.org_id,
            thread_id=thread_id,
            target_kind=target_kind,
            artifact_id=str(artifact.id) if artifact else None,
            site_page_version_id=str(site_page_version.id) if site_page_version else None,
        )
        approval.status = "resolved"
        approval.decision = decision
        approval.resolved_by_user_id = self.user_id
        approval.resolution_notes = notes
        approval.resolved_at = datetime.now(timezone.utc)
        self.approvals_repo.update(item=approval)

        if decision == "approved":
            if artifact is not None:
                approved_resolved_at = cast(datetime | None, approval.resolved_at)
                final_kind = (
                    "page_copy_puck_final"
                    if artifact.kind == "page_copy_puck_draft"
                    else "copy_markdown_final"
                )
                self.artifacts_repo.create(
                    run_id=str(artifact.run_id),
                    kind=final_kind,
                    key=f"thread:{thread_id}",
                    data_json={
                        **artifact.data_json,
                        "approvedFromArtifactId": str(artifact.id),
                        "approvedAt": (
                            approved_resolved_at.isoformat()
                            if approved_resolved_at is not None
                            else None
                        ),
                    },
                )
            if site_page_version is not None:
                self.sites_repo.create_page_version(
                    page_id=str(site_page_version.page_id),
                    puck_data=site_page_version.puck_data,
                    provenance={
                        **(site_page_version.provenance or {}),
                        "approvedFromPageVersionId": str(site_page_version.id),
                        "approvalItemId": str(approval.id),
                        "approvedByUserId": self.user_id,
                    },
                    status="approved",
                    source_type=site_page_version.source_type,
                    source_id=site_page_version.source_id,
                    ai_metadata=site_page_version.ai_metadata,
                    diff_summary=site_page_version.diff_summary,
                )
            thread.status = "approved"
        elif decision == "rejected":
            thread.status = "open"

        self.threads_repo.update_thread(thread=thread)
        self.session.commit()
        return self.get_thread_detail(thread_id=thread_id)

    def _require_thread(self, *, thread_id: str):
        thread = self.threads_repo.get(thread_id=thread_id, org_id=self.org_id)
        if not thread:
            raise AgentThreadsServiceError("Agent thread not found.")
        return thread

    def _require_client(self, *, client_id: str) -> Client:
        client = self.session.scalars(
            select(Client).where(
                Client.id == UUID(client_id),
                Client.org_id == UUID(self.org_id),
            )
        ).first()
        if not client:
            raise AgentThreadsServiceError("Workspace not found or does not belong to this organization.")
        return client

    def _require_product(self, *, product_id: str, client_id: str) -> Product:
        product = self.session.scalars(
            select(Product).where(
                Product.id == UUID(product_id),
                Product.client_id == UUID(client_id),
            )
        ).first()
        if not product:
            raise AgentThreadsServiceError("Product not found for the requested workspace.")
        return product

    def _require_site_page(
        self,
        *,
        site_id: str | None,
        page_id: str | None,
        client_id: str,
    ) -> tuple[Site | None, SitePage | None]:
        if not site_id and not page_id:
            return None, None
        if not site_id or not page_id:
            raise AgentThreadsServiceError("Both siteId and pageId are required for a page-bound thread.")

        site = self.sites_repo.get_site(
            org_id=self.org_id,
            client_id=client_id,
            site_id=site_id,
        )
        if not site:
            raise AgentThreadsServiceError("Site not found for the requested workspace.")

        page = self.sites_repo.get_page(site_id=site_id, page_id=page_id)
        if not page:
            raise AgentThreadsServiceError("Site page not found.")
        return site, page

    def _build_page_context(
        self,
        *,
        site: Site,
        page: SitePage,
        strategy_bundle_id: str | None = None,
        runtime_profile_key: str | None = None,
    ) -> dict[str, Any]:
        latest_approved = self.sites_repo.latest_version_for_page(page_id=str(page.id), status="approved")
        return {
            "siteId": str(site.id),
            "siteName": site.name,
            "pageId": str(page.id),
            "pageName": page.name,
            "pageSlug": page.slug,
            "pageType": page.page_type,
            "pageRole": page.page_role,
            "strategyBundleId": strategy_bundle_id,
            "runtimeProfileKey": runtime_profile_key,
            "latestApprovedVersionId": str(latest_approved.id) if latest_approved else None,
            "latestApprovedPuckData": latest_approved.puck_data if latest_approved else None,
        }

    @staticmethod
    def _runtime_page_context_path(*, runtime_home: Path) -> Path:
        return runtime_home / "runtime" / "page_context.json"

    def _sync_runtime_page_context(
        self,
        *,
        runtime_home: Path,
        page_context: dict[str, Any],
    ) -> None:
        page_context_path = self._runtime_page_context_path(runtime_home=runtime_home)
        page_context_path.parent.mkdir(parents=True, exist_ok=True)
        page_context_path.write_text(
            json.dumps(page_context, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_runtime_page_context(self, *, runtime_home: Path) -> dict[str, Any]:
        page_context_path = self._runtime_page_context_path(runtime_home=runtime_home)
        if not page_context_path.exists():
            raise AgentThreadsServiceError(
                f"Hermes runtime page context is missing: {page_context_path}"
            )
        try:
            payload = json.loads(page_context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentThreadsServiceError(
                f"Hermes runtime page context is unreadable: {page_context_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise AgentThreadsServiceError(
                f"Hermes runtime page context is invalid: {page_context_path}"
            )
        return payload

    def _runtime_page_context_was_mutated(
        self,
        *,
        runtime_home: Path,
        original_page_context: dict[str, Any],
    ) -> bool:
        original_puck_data = original_page_context.get("latestApprovedPuckData")
        if original_puck_data is None:
            return False
        if not isinstance(original_puck_data, dict):
            raise AgentThreadsServiceError(
                "Page-bound thread has invalid latestApprovedPuckData in page context."
            )
        page_context_path = self._runtime_page_context_path(runtime_home=runtime_home)
        if not page_context_path.exists():
            return False

        runtime_page_context = self._load_runtime_page_context(runtime_home=runtime_home)
        mutated_puck_data = runtime_page_context.get("latestApprovedPuckData")
        if mutated_puck_data is None:
            return False
        if not isinstance(mutated_puck_data, dict):
            raise AgentThreadsServiceError(
                "Hermes runtime page context returned invalid latestApprovedPuckData."
            )
        return mutated_puck_data != original_puck_data

    def _resolve_page_orchestrator_tool_page_version(
        self,
        *,
        page: SitePage,
        thread_id: str,
        run_started_at: datetime,
    ) -> SitePageVersion | None:
        stmt = (
            select(SitePageVersion)
            .where(
                SitePageVersion.page_id == UUID(str(page.id)),
                SitePageVersion.status == "draft",
                SitePageVersion.source_type == "hermes_sidecar",
                SitePageVersion.source_id == thread_id,
                SitePageVersion.created_at >= run_started_at,
            )
            .order_by(SitePageVersion.created_at.desc())
        )
        for version in self.session.scalars(stmt).all():
            ai_metadata = version.ai_metadata or {}
            if (
                ai_metadata.get("threadId") == thread_id
                and ai_metadata.get("outputMode") == "page_orchestrator_tool_patch"
            ):
                return version
        return None

    def _resolve_runtime_toolsets(self, *, thread, projection_toolsets: list[str]) -> list[str]:
        resolved: list[str] = []
        for toolset in projection_toolsets:
            normalized = toolset.strip()
            if normalized and normalized not in resolved:
                resolved.append(normalized)
        if thread.page_id and thread.objective_type in PAGE_CHAT_OBJECTIVE_TYPES:
            page_editor_toolset = self.hermes.page_editor_toolset_name()
            if page_editor_toolset not in resolved:
                resolved.append(page_editor_toolset)
        return resolved

    @staticmethod
    def _resolve_output_mode(*, thread) -> str:
        if thread.page_id and thread.objective_type in PAGE_AGENT_OBJECTIVE_TYPES:
            return "page_copy_slots"
        return "markdown"

    def _resolve_projection(
        self,
        *,
        client_id: str,
        product_id: str,
        thread_id: str,
        agent_profile: str,
        bundle_key: str,
        runtime_profile_key: str | None,
        strategy_bundle_id: str | None,
        objective_type: str,
        page_context: dict[str, Any] | None,
    ) -> tuple[Any, dict[str, Any], str | None]:
        if runtime_profile_key:
            if objective_type in PAGE_AGENT_OBJECTIVE_TYPES and not strategy_bundle_id:
                raise AgentThreadsServiceError(
                    "Page-bound Hermes threads require a strategyBundleId or an active page binding with a strategy bundle."
                )
            runtime_registry = SkillsRuntimeRegistryService(
                session=self.session,
                org_id=self.org_id,
                client_id=client_id,
                product_id=product_id,
                created_by_user=self.user_id,
            )
            exported_bundle = runtime_registry.export_runtime_bundle(
                bundle_key=bundle_key,
                runtime_profile_key=runtime_profile_key,
                project_doc_bundle_id=strategy_bundle_id,
            )
            projection = self.hermes.build_runtime_projection_from_manifest(
                bundle_manifest=exported_bundle["manifest"],
                org_id=self.org_id,
                client_id=client_id,
                product_id=product_id,
                thread_id=thread_id,
                agent_profile=agent_profile,
                page_context=page_context,
            )
            return projection, exported_bundle["manifest"], exported_bundle["id"]

        projection = self.hermes.build_runtime_projection(
            bundle_key=bundle_key,
            org_id=self.org_id,
            client_id=client_id,
            product_id=product_id,
            thread_id=thread_id,
            agent_profile=agent_profile,
            page_context=page_context,
        )
        return projection, projection.bundle_manifest, None

    def _build_query(
        self,
        *,
        thread_id: str,
        thread,
        content: str,
        runtime_home: Path,
        site: Site | None,
        page: SitePage | None,
    ) -> str:
        if self._resolve_output_mode(thread=thread) == "page_copy_slots":
            return self._build_page_copy_query(
                thread_id=thread_id,
                thread=thread,
                content=content,
                runtime_home=runtime_home,
                site=site,
                page=page,
            )
        return self._build_markdown_query(
            thread_id=thread_id,
            thread=thread,
            content=content,
            runtime_home=runtime_home,
        )

    def _build_markdown_query(self, *, thread_id: str, thread, content: str, runtime_home: Path) -> str:
        recent_turns = self.threads_repo.list_turns(thread_id=thread_id)[-6:]
        history_lines = ["Recent thread history:"]
        if recent_turns:
            for turn in recent_turns:
                preview = turn.content.strip()
                if len(preview) > 800:
                    preview = preview[:800] + "\n[truncated]"
                history_lines.append(f"{turn.role.upper()}: {preview}")
        else:
            history_lines.append("- none")

        if thread.page_id and thread.objective_type in PAGE_CHAT_OBJECTIVE_TYPES:
            page_note = (
                "This thread is a live page-orchestrator chat. Respond conversationally in markdown."
                " Use the projected bundle files plus the explicit page editor MCP tools to audit, explain, plan, and answer the user's request."
                " Do not force a full page draft unless the user explicitly asks for one."
                f" If the user explicitly asks you to make a direct page change, first call `mcp_{self.hermes.PAGE_EDITOR_MCP_SERVER_NAME}_get_page_context`"
                " to inspect the current canonical page state, editableSectionIndex, semanticBindings, and explicit editable paths."
                " Match the user's requested section against editableSectionIndex before editing."
                " If the requested change maps to a semanticBinding such as a multi-part hero headline, use that semanticBinding instead of editing member paths manually."
                f" Prefer `mcp_{self.hermes.PAGE_EDITOR_MCP_SERVER_NAME}_apply_semantic_page_edits` for semanticBindings."
                f" Use `mcp_{self.hermes.PAGE_EDITOR_MCP_SERVER_NAME}_apply_page_edits` only for raw paths that are not covered by a semanticBinding."
                " 'Header' means the Global Header / GlobalHeader section."
                " It does not mean the hero headline unless the user explicitly says hero or headline."
                " The get_page_context tool returns baseVersionId/baseVersionStatus for the pre-edit page state."
                " That baseVersionId is not the new draft version id."
                " When using a semanticBinding, never edit only one member path unless the user explicitly asks for a partial change."
                " If the latest user turn conflicts with older thread history, follow the latest user turn exactly."
                " Never edit runtime files or bundle files to change the page."
                " Never claim that the page was updated unless the MCP tool returned a successful resultingSitePageVersionId."
                " If you mention a sitePageVersionId in your response, copy the exact resultingSitePageVersionId returned by the page editor MCP tool."
            )
        elif thread.page_id:
            page_note = (
                "This thread is page-bound. Return a page draft in markdown with a single H1 and clear section headings. The first non-whitespace character of the response must be `#`."
            )
        else:
            page_note = "This thread is artifact-only. Return copy draft markdown only, with no preamble or status text."
        start_here_path = runtime_home / "runtime" / "START-HERE.md"
        manifest_path = runtime_home / "runtime" / "active_bundle" / "manifest.json"

        return "\n".join(
            [
                "You are operating inside the local mOS V3 Hermes sidecar prototype.",
                f"Use the installed `{self.hermes.RUNTIME_SKILL_NAME}` skill and the projected FutrGroup skill chain.",
                f"Read `{start_here_path}` and `{manifest_path}` before drafting.",
                "Prefer the projected bundle file paths under the runtime home.",
                "Use projected file paths exactly as written. Do not add shell escaping or backslashes.",
                "Treat the approved headlines file as already user-approved.",
                "Do not invent missing facts, scientific claims, testimonials, pricing, or approvals.",
                "If a required input is missing or contradictory, stop and explain the exact missing role.",
                page_note,
                "Do not include tooling notes, status notes, planning text, or code fences in the response.",
                "",
                *history_lines,
                "",
                "User request:",
                content.strip(),
            ]
        )

    def _build_page_copy_query(
        self,
        *,
        thread_id: str,
        thread,
        content: str,
        runtime_home: Path,
        site: Site | None,
        page: SitePage | None,
    ) -> str:
        if not site or not page:
            raise AgentThreadsServiceError("Page copy agent requires a bound site and page.")

        base_puck = self._load_page_agent_base_puck_data(page=page)
        if not is_imported_template_page_data(base_puck):
            raise AgentThreadsServiceError(
                "Page copy agent requires an imported-template page with ImportedPage top-level content."
            )

        start_here_path = runtime_home / "runtime" / "START-HERE.md"
        manifest_path = runtime_home / "runtime" / "active_bundle" / "manifest.json"
        prior_messages = [
            {"role": turn.role, "content": turn.content}
            for turn in self.threads_repo.list_turns(thread_id=thread_id)[-6:]
            if turn.role in {"user", "assistant"} and turn.content.strip()
        ]
        page_context = self._build_site_page_listing(site_id=str(site.id))
        slots = extract_site_page_copy_slots(base_puck)
        compiled_prompt = build_site_page_copy_prompt(
            site=site,
            page=page,
            puck_data=base_puck,
            page_context=page_context,
            prompt=content.strip(),
            messages=prior_messages,
            slots=slots,
        )
        return "\n".join(
            [
                "You are operating inside the local mOS V3 Hermes sidecar prototype.",
                f"Use the installed `{self.hermes.RUNTIME_SKILL_NAME}` skill and the projected FutrGroup skill chain.",
                f"Read `{start_here_path}` and `{manifest_path}` before editing the page.",
                "Treat the approved headlines file as already user-approved when present in the active bundle.",
                "Do not invent missing facts, scientific claims, testimonials, pricing, or approvals.",
                "Inherited source-template names in slot labels, section names, component names, current values, and JSON pointer paths are inert metadata only. They may still reference the original imported brand and are not contradictions.",
                "Rewrite the slot values for the active bundle product even when source-template metadata still uses the original product naming.",
                "If a required input is missing or contradictory, stop and explain the exact missing role.",
                "This is a copy-agent run. Keep the page template structure fixed and return slot assignments only.",
                "Do not use tools to count, draft, or store the slot assignments.",
                "Do not write the JSON payload to disk before answering.",
                "Return JSON only. Do not include markdown fences, tooling notes, or status text.",
                "",
                compiled_prompt,
            ]
        )

    def _run_page_copy_batches(
        self,
        *,
        thread_id: str,
        thread,
        user_content: str,
        runtime_home: Path,
        hermes_session_id: str | None,
        site: Site,
        page: SitePage,
        base_puck_data: dict[str, Any],
        slots: list[SitePageCopySlot],
        slot_batches: list[SitePageCopySlotBatch],
    ) -> tuple[SitePageCopyAgentResult, list[dict[str, Any]], str, str, dict[str, int]]:
        if not slot_batches:
            raise AgentThreadsServiceError("Page copy agent did not find any slot batches to execute.")

        page_context = self._build_site_page_listing(site_id=str(site.id))
        current_puck_data = deepcopy(base_puck_data)
        thread_session_id = hermes_session_id
        merged_assignments: list[dict[str, str]] = []
        batch_reports: list[dict[str, Any]] = []
        raw_output_previews: list[str] = []
        aggregate_usage = self._empty_usage()

        for index, batch in enumerate(slot_batches, start=1):
            current_slot_map = {
                slot.path: slot for slot in extract_site_page_copy_slots(current_puck_data)
            }
            batch_slots = [current_slot_map.get(slot.path) for slot in batch.slots]
            missing_paths = [
                slot.path
                for slot, current_slot in zip(batch.slots, batch_slots, strict=True)
                if current_slot is None
            ]
            if missing_paths:
                raise AgentThreadsServiceError(
                    "Page copy agent lost required slot bindings before batch execution: "
                    + ", ".join(missing_paths)
                )

            scoped_slots = [slot for slot in batch_slots if slot is not None]
            batch_note = self._describe_page_copy_batch(
                batch=batch,
                batch_index=index,
                batch_count=len(slot_batches),
            )
            compiled_prompt = build_site_page_copy_prompt(
                site=site,
                page=page,
                puck_data=current_puck_data,
                page_context=page_context,
                prompt=f"{user_content.strip()}\n\n{batch_note}",
                messages=None,
                slots=scoped_slots,
            )
            query = self._compose_page_copy_batch_query(
                runtime_home=runtime_home,
                compiled_prompt=compiled_prompt,
            )

            run_result, parsed_result, repair_count, batch_usage = self._execute_page_copy_batch(
                runtime_home=runtime_home,
                session_id=thread_session_id,
                base_puck_data=current_puck_data,
                scoped_slots=scoped_slots,
                query=query,
                batch_note=batch_note,
                site=site,
                page=page,
                page_context=page_context,
                user_content=user_content,
            )
            thread_session_id = run_result.hermes_session_id
            current_puck_data = parsed_result.puck_data
            merged_assignments.extend(parsed_result.assignments)
            aggregate_usage = self._merge_usage(aggregate_usage, batch_usage)
            raw_output_previews.append(
                f"{batch_note}\n{run_result.raw_output[:1200]}".strip()
            )
            batch_reports.append(
                {
                    "batchKey": batch.batch_key,
                    "batchIndex": index,
                    "batchCount": len(slot_batches),
                    "sectionDisplayName": batch.section_display_name,
                    "componentName": batch.component_name,
                    "slotCount": len(scoped_slots),
                    "assignmentCount": len(parsed_result.assignments),
                    "assistantMessage": parsed_result.assistant_message,
                    "slotPaths": [slot.path for slot in scoped_slots],
                    "repairCount": repair_count,
                    "rawOutputPreview": run_result.raw_output[:1200],
                    "usage": batch_usage,
                }
            )

        final_result = SitePageCopyAgentResult(
            assistant_message=self._build_page_copy_batch_summary(
                slot_batches=slot_batches,
                total_assignments=len(merged_assignments),
            ),
            assignments=merged_assignments,
            puck_data=current_puck_data,
        )
        return (
            final_result,
            batch_reports,
            thread_session_id or "",
            "\n\n".join(raw_output_previews)[:8000],
            aggregate_usage,
        )

    def _execute_page_copy_batch(
        self,
        *,
        runtime_home: Path,
        session_id: str | None,
        base_puck_data: dict[str, Any],
        scoped_slots: list[SitePageCopySlot],
        query: str,
        batch_note: str,
        site: Site,
        page: SitePage,
        page_context: list[dict[str, str]],
        user_content: str,
    ) -> tuple[Any, SitePageCopyAgentResult, int, dict[str, int]]:
        repair_count = 0
        last_error: SitePageCopyAgentError | None = None
        attempt_queries = [query]
        active_session_id = session_id
        usage_totals = self._empty_usage()

        for attempt_index, attempt_query in enumerate(attempt_queries, start=1):
            run_result = self.hermes.run_turn(
                runtime_home=runtime_home,
                query=attempt_query,
                hermes_session_id=active_session_id,
            )
            usage_totals = self._merge_usage(usage_totals, run_result.usage)
            active_session_id = run_result.hermes_session_id
            try:
                parsed_result = parse_site_page_copy_agent_response(
                    raw_output=run_result.response_text,
                    base_puck_data=base_puck_data,
                    slots=scoped_slots,
                )
                return run_result, parsed_result, repair_count, usage_totals
            except SitePageCopyAgentError as exc:
                last_error = exc
                if attempt_index > 1:
                    break
                repair_count = 1
                attempt_queries.append(
                    self._compose_page_copy_batch_repair_query(
                        runtime_home=runtime_home,
                        original_query=query,
                        validation_error=str(exc),
                    )
                )

        if len(scoped_slots) > 1:
            repaired_puck_data = deepcopy(base_puck_data)
            repaired_assignments: list[dict[str, str]] = []
            last_run_result = None
            for slot_index, original_slot in enumerate(scoped_slots, start=1):
                current_slot = next(
                    (
                        slot
                        for slot in extract_site_page_copy_slots(repaired_puck_data)
                        if slot.path == original_slot.path
                    ),
                    None,
                )
                if current_slot is None:
                    raise SitePageCopyAgentError(
                        f"{batch_note} slot repair could not find {original_slot.path} in the working puck data."
                    ) from last_error

                slot_note = (
                    f"{batch_note} Repair only slot {slot_index} of {len(scoped_slots)}: "
                    f"`{current_slot.label}` at `{current_slot.path}`."
                )
                slot_query = self._compose_single_slot_repair_query(
                    runtime_home=runtime_home,
                    site=site,
                    page=page,
                    slot=current_slot,
                    user_content=user_content,
                    slot_note=slot_note,
                )
                last_run_result = self.hermes.run_turn(
                    runtime_home=runtime_home,
                    query=slot_query,
                    hermes_session_id=active_session_id,
                )
                usage_totals = self._merge_usage(usage_totals, last_run_result.usage)
                active_session_id = last_run_result.hermes_session_id
                try:
                    slot_result = parse_site_page_copy_agent_response(
                        raw_output=last_run_result.response_text,
                        base_puck_data=repaired_puck_data,
                        slots=[current_slot],
                    )
                except SitePageCopyAgentError as exc:
                    raise SitePageCopyAgentError(
                        f"{batch_note} slot repair failed for {current_slot.path}: {exc}"
                    ) from exc
                repaired_puck_data = slot_result.puck_data
                repaired_assignments.extend(slot_result.assignments)
                repair_count += 1

            return (
                last_run_result,
                SitePageCopyAgentResult(
                    assistant_message=f"Repaired {len(repaired_assignments)} slot assignments for {batch_note}.",
                    assignments=repaired_assignments,
                    puck_data=repaired_puck_data,
                ),
                repair_count,
                usage_totals,
            )

        raise SitePageCopyAgentError(f"{batch_note} failed: {last_error}") from last_error

    def _compose_page_copy_batch_query(self, *, runtime_home: Path, compiled_prompt: str) -> str:
        start_here_path = runtime_home / "runtime" / "START-HERE.md"
        manifest_path = runtime_home / "runtime" / "active_bundle" / "manifest.json"
        return "\n".join(
            [
                "You are operating inside the local mOS V3 Hermes sidecar prototype.",
                f"Use the installed `{self.hermes.RUNTIME_SKILL_NAME}` skill and the projected FutrGroup skill chain.",
                f"Read `{start_here_path}` and `{manifest_path}` before editing the page.",
                "Ignore any earlier conversational formatting or prose expectations. This turn's JSON contract overrides prior turns.",
                "Treat the approved headlines file as already user-approved when present in the active bundle.",
                "Do not invent missing facts, scientific claims, testimonials, pricing, or approvals.",
                "Inherited source-template names in slot labels, section names, component names, current values, and JSON pointer paths are inert metadata only. They may still reference the original imported brand and are not contradictions.",
                "Rewrite the slot values for the active bundle product even when source-template metadata still uses the original product naming.",
                "If a required input is missing or contradictory, stop and explain the exact missing role.",
                "This is a copy-agent run. Keep the page template structure fixed and return slot assignments only.",
                "Do not use tools to count, draft, or store the slot assignments.",
                "Do not write the JSON payload to disk before answering.",
                "Return JSON only. Do not include markdown fences, tooling notes, or status text.",
                "",
                compiled_prompt,
            ]
        )

    def _compose_page_copy_batch_repair_query(
        self,
        *,
        runtime_home: Path,
        original_query: str,
        validation_error: str,
    ) -> str:
        return self._compose_page_copy_batch_query(
            runtime_home=runtime_home,
            compiled_prompt="\n".join(
                [
                    "The previous batch response was invalid.",
                    f"Validation error: {validation_error}",
                    "Return corrected JSON for the exact same batch now.",
                    "Do not omit any slot paths.",
                    "Do not include any extra slot paths.",
                    "",
                    original_query,
                ]
            ),
        )

    def _compose_single_slot_repair_query(
        self,
        *,
        runtime_home: Path,
        site: Site,
        page: SitePage,
        slot: SitePageCopySlot,
        user_content: str,
        slot_note: str,
    ) -> str:
        slot_payload = {
            "path": slot.path,
            "label": slot.label,
            "kind": slot.kind,
            "sectionDisplayName": slot.section_display_name,
            "componentName": slot.component_name,
            "currentValue": slot.current_value,
            "siteName": site.name,
            "pageName": page.name,
            "pageSlug": page.slug,
        }
        return self._compose_page_copy_batch_query(
            runtime_home=runtime_home,
            compiled_prompt="\n".join(
                [
                    "Single-slot repair.",
                    "Return valid JSON only with this exact shape:",
                    '{ "assistantMessage": string, "assignments": [{"path": string, "value": string}] }',
                    "There is exactly one required assignment.",
                    "Use the exact path provided.",
                    "Do not omit the assignment.",
                    "Do not include any extra assignments.",
                    "The slot label, section name, component name, current value, and path may still carry source-template brand names such as OMNI or creatine. Treat those names as inert source metadata only, not as contradictions.",
                    "Rewrite the value for the active bundle product even when the inherited source-template metadata still uses the original product naming.",
                    "If this slot is a stale source-only sale badge or discount remnant and the active bundle has no approved discount, rewrite it into short neutral positioning or trust language grounded in the bundle instead of refusing.",
                    "Do not preserve a fake percentage or fake promotional claim.",
                    "",
                    f"User request: {user_content.strip()}",
                    slot_note,
                    "Slot JSON:",
                    str(slot_payload),
                    "",
                    "Return JSON now.",
                ]
            ),
        )

    @staticmethod
    def _describe_page_copy_batch(
        *,
        batch: SitePageCopySlotBatch,
        batch_index: int,
        batch_count: int,
    ) -> str:
        section_name = batch.section_display_name or batch.component_name or batch.batch_key
        component_name = batch.component_name or "Imported section"
        return (
            f"Batch scope: section {batch_index} of {batch_count}."
            f" Rewrite only the provided slots for `{section_name}` (`{component_name}`)."
            " Do not return assignments for any slot outside this batch."
        )

    @staticmethod
    def _build_page_copy_batch_summary(
        *,
        slot_batches: list[SitePageCopySlotBatch],
        total_assignments: int,
    ) -> str:
        labels = [
            batch.section_display_name or batch.component_name or batch.batch_key
            for batch in slot_batches
        ]
        preview = ", ".join(labels[:6])
        if len(labels) > 6:
            preview = f"{preview}, +{len(labels) - 6} more"
        return (
            f"Updated {total_assignments} copy slots across {len(slot_batches)} section batches. "
            f"Sections: {preview}."
        )

    @staticmethod
    def _empty_usage() -> dict[str, int]:
        return {
            "promptTokens": 0,
            "completionTokens": 0,
            "totalTokens": 0,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "apiCallCount": 0,
        }

    @classmethod
    def _merge_usage(cls, left: dict[str, int], right: dict[str, int] | None) -> dict[str, int]:
        merged = dict(left)
        if right is None:
            return merged
        for key in cls._empty_usage():
            merged[key] = int(merged.get(key, 0)) + int(right.get(key, 0))
        return merged

    def _build_site_page_listing(self, *, site_id: str) -> list[dict[str, str]]:
        pages = self.sites_repo.list_pages(site_id=site_id)
        return [
            {
                "id": str(item.id),
                "name": item.name,
                "slug": item.slug,
            }
            for item in pages
        ]

    def _load_page_agent_base_puck_data(self, *, page: SitePage) -> dict[str, Any]:
        latest_draft = self.sites_repo.latest_version_for_page(page_id=str(page.id), status="draft")
        if latest_draft and isinstance(latest_draft.puck_data, dict):
            puck_data = deepcopy(latest_draft.puck_data)
            refreshed = refresh_imported_page_copy_slots(puck_data) or puck_data
            return backfill_imported_runtime_override_slots(refreshed) or refreshed
        latest_approved = self.sites_repo.latest_version_for_page(page_id=str(page.id), status="approved")
        if latest_approved and isinstance(latest_approved.puck_data, dict):
            puck_data = deepcopy(latest_approved.puck_data)
            refreshed = refresh_imported_page_copy_slots(puck_data) or puck_data
            return backfill_imported_runtime_override_slots(refreshed) or refreshed
        if isinstance(page.adapted_puck_data, dict) and page.adapted_puck_data:
            puck_data = deepcopy(page.adapted_puck_data)
            refreshed = refresh_imported_page_copy_slots(puck_data) or puck_data
            return backfill_imported_runtime_override_slots(refreshed) or refreshed
        raise AgentThreadsServiceError("Page copy agent could not find a valid base puckData for the bound page.")

    def _create_page_draft_version(
        self,
        *,
        page_id: str,
        response_text: str,
        thread_id: str,
        run_id: str,
        hermes_session_id: str,
    ) -> SitePageVersion:
        title = self._extract_title(response_text)
        puck_data = {
            "root": {
                "props": {
                    "title": title,
                    "description": None,
                }
            },
            "content": [
                {
                    "type": "ImportedPage",
                    "props": {
                        "id": "agent-thread-page",
                        "pageName": title,
                        "pageType": "agent-draft",
                        "renderMode": "draft",
                        "content": [
                            {
                                "type": "ImportedSection",
                                "props": {
                                    "id": "agent-thread-section",
                                    "displayName": "Agent Draft",
                                    "sourceSectionId": "agent-thread-section",
                                    "sectionKey": "agent-thread-draft",
                                    "sectionType": "narrative",
                                    "renderMode": "draft",
                                    "content": [
                                        {
                                            "type": "ImportedNarrativeBlock",
                                            "props": {
                                                "id": "agent-thread-block",
                                                "title": title,
                                                "body": response_text,
                                                "badges": [],
                                                "buttons": [],
                                            },
                                        }
                                    ],
                                },
                            }
                        ],
                    },
                }
            ],
            "zones": {},
        }
        return self.sites_repo.create_page_version(
            page_id=page_id,
            puck_data=puck_data,
            provenance={
                "source": "hermes_sidecar",
                "threadId": thread_id,
                "runId": run_id,
                "hermesSessionId": hermes_session_id,
            },
            status="draft",
            source_type="hermes_sidecar",
            source_id=thread_id,
            ai_metadata={
                "threadId": thread_id,
                "runId": run_id,
                "hermesSessionId": hermes_session_id,
            },
            diff_summary="Hermes sidecar draft page update",
        )

    def _create_structured_page_draft_version(
        self,
        *,
        page_id: str,
        puck_data: dict[str, Any],
        assistant_message: str,
        thread_id: str,
        run_id: str,
        hermes_session_id: str,
    ) -> SitePageVersion:
        return self.sites_repo.create_page_version(
            page_id=page_id,
            puck_data=deepcopy(puck_data),
            provenance={
                "source": "hermes_sidecar",
                "threadId": thread_id,
                "runId": run_id,
                "hermesSessionId": hermes_session_id,
                "assistantMessage": assistant_message,
                "outputMode": "page_copy_slots",
            },
            status="draft",
            source_type="hermes_sidecar",
            source_id=thread_id,
            ai_metadata={
                "threadId": thread_id,
                "runId": run_id,
                "hermesSessionId": hermes_session_id,
                "assistantMessage": assistant_message,
                "outputMode": "page_copy_slots",
            },
            diff_summary="Hermes sidecar copy-agent structured page update",
        )

    @staticmethod
    def _extract_title(response_text: str) -> str:
        for line in response_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip() or "Agent Draft"
            return stripped[:120]
        return "Agent Draft"

    @staticmethod
    def _normalize_response_text(*, response_text: str, require_h1: bool) -> str:
        normalized = response_text.strip()
        if not normalized:
            raise AgentThreadsServiceError("Hermes returned an empty assistant response.")
        if "```" in normalized:
            raise AgentThreadsServiceError(
                "Hermes returned fenced output. Refusing to persist a non-canonical draft."
            )
        if not require_h1:
            return normalized

        h1_match = re.search(r"^#\s+\S.*$", normalized, flags=re.MULTILINE)
        if not h1_match:
            raise AgentThreadsServiceError(
                "Hermes page-bound response did not contain the required H1 draft heading."
            )

        canonical = normalized[h1_match.start() :].strip()
        if not canonical.startswith("# "):
            raise AgentThreadsServiceError(
                "Hermes page-bound response normalization failed to produce a canonical H1 draft."
            )
        return canonical

    def _require_thread_artifact(self, *, thread_id: str, artifact_id: str) -> AgentArtifact:
        artifact = self._load_artifact(artifact_id=artifact_id)
        if not artifact:
            raise AgentThreadsServiceError("Draft artifact not found.")

        turns = self.threads_repo.list_turns(thread_id=thread_id)
        if not any(str(turn.artifact_id) == str(artifact.id) for turn in turns):
            raise AgentThreadsServiceError("Draft artifact does not belong to this thread.")
        return artifact

    def _load_artifact(self, *, artifact_id: str) -> AgentArtifact | None:
        return self.session.scalars(
            select(AgentArtifact)
            .join(AgentRun, AgentRun.id == AgentArtifact.run_id)
            .where(
                AgentArtifact.id == UUID(artifact_id),
                AgentRun.org_id == UUID(self.org_id),
            )
        ).first()

    def _require_thread_page_version(self, *, thread, page_version_id: str) -> SitePageVersion:
        if not thread.page_id:
            raise AgentThreadsServiceError("This thread is not bound to a site page.")
        page_version = self.session.scalars(
            select(SitePageVersion).where(
                SitePageVersion.id == UUID(page_version_id),
                SitePageVersion.page_id == UUID(str(thread.page_id)),
            )
        ).first()
        if not page_version:
            raise AgentThreadsServiceError("Draft page version not found for this thread.")
        return page_version

    @staticmethod
    def _serialize_thread(thread) -> dict[str, Any]:
        return {
            "id": str(thread.id),
            "clientId": str(thread.client_id),
            "productId": str(thread.product_id),
            "siteId": str(thread.site_id) if thread.site_id else None,
            "pageId": str(thread.page_id) if thread.page_id else None,
            "agentProfile": thread.agent_profile,
            "objectiveType": thread.objective_type,
            "title": thread.title,
            "bundleKey": thread.bundle_key,
            "runtimeProfileKey": thread.runtime_profile_key,
            "strategyBundleId": str(thread.strategy_bundle_id) if thread.strategy_bundle_id else None,
            "status": thread.status,
            "bundleManifest": thread.bundle_manifest,
            "metadata": thread.metadata_json or {},
            "createdAt": thread.created_at.isoformat(),
            "updatedAt": thread.updated_at.isoformat(),
        }

    @staticmethod
    def _serialize_runtime_session(runtime_session) -> dict[str, Any]:
        return {
            "id": str(runtime_session.id),
            "status": runtime_session.status,
            "runtimeHome": runtime_session.runtime_home,
            "hermesSessionId": runtime_session.hermes_session_id,
            "projectionHash": runtime_session.projection_hash,
            "toolsets": runtime_session.toolsets or [],
            "lastError": runtime_session.last_error,
            "lastUsedAt": runtime_session.last_used_at.isoformat(),
        }

    @staticmethod
    def _serialize_turn(turn) -> dict[str, Any]:
        return {
            "id": str(turn.id),
            "seq": turn.seq,
            "role": turn.role,
            "content": turn.content,
            "runId": str(turn.run_id) if turn.run_id else None,
            "artifactId": str(turn.artifact_id) if turn.artifact_id else None,
            "sitePageVersionId": str(turn.site_page_version_id) if turn.site_page_version_id else None,
            "metadata": turn.metadata_json or {},
            "createdAt": turn.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_approval(item) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "targetKind": item.target_kind,
            "artifactId": str(item.artifact_id) if item.artifact_id else None,
            "sitePageVersionId": str(item.site_page_version_id) if item.site_page_version_id else None,
            "status": item.status,
            "decision": item.decision,
            "resolutionNotes": item.resolution_notes,
            "createdAt": item.created_at.isoformat(),
            "resolvedAt": item.resolved_at.isoformat() if item.resolved_at else None,
        }

    @staticmethod
    def _serialize_run(run: AgentRun) -> dict[str, Any]:
        return {
            "id": str(run.id),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "objectiveType": run.objective_type,
            "model": run.model,
            "rulesetVersion": run.ruleset_version,
            "inputs": run.inputs_json or {},
            "outputs": run.outputs_json or {},
            "error": run.error,
            "startedAt": run.started_at.isoformat(),
            "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
        }

    @staticmethod
    def _serialize_artifact(artifact: AgentArtifact) -> dict[str, Any]:
        return {
            "id": str(artifact.id),
            "kind": artifact.kind,
            "key": artifact.key,
            "data": artifact.data_json or {},
            "createdAt": artifact.created_at.isoformat(),
        }

    def _serialize_site_page_version(self, site_page_version: SitePageVersion) -> dict[str, Any]:
        body = self._extract_site_page_version_body(site_page_version)
        puck_data = site_page_version.puck_data or {}
        return {
            "id": str(site_page_version.id),
            "pageId": str(site_page_version.page_id),
            "status": site_page_version.status,
            "title": self._extract_site_page_version_title(site_page_version=site_page_version),
            "body": body,
            "puckData": puck_data,
            "pageSummary": self._summarize_puck_data(puck_data) if isinstance(puck_data, dict) else None,
            "provenance": site_page_version.provenance or {},
            "sourceType": site_page_version.source_type,
            "sourceId": site_page_version.source_id,
            "aiMetadata": site_page_version.ai_metadata or {},
            "diffSummary": site_page_version.diff_summary,
            "createdAt": site_page_version.created_at.isoformat(),
            "updatedAt": site_page_version.updated_at.isoformat(),
        }

    @staticmethod
    def _extract_site_page_version_body(site_page_version: SitePageVersion) -> str | None:
        puck_data = site_page_version.puck_data or {}
        content = puck_data.get("content")
        if not isinstance(content, list) or not content:
            return None
        page_props = content[0].get("props") if isinstance(content[0], dict) else None
        if not isinstance(page_props, dict):
            return None
        sections = page_props.get("content")
        if not isinstance(sections, list) or not sections:
            return None
        section_props = sections[0].get("props") if isinstance(sections[0], dict) else None
        if not isinstance(section_props, dict):
            return None
        blocks = section_props.get("content")
        if not isinstance(blocks, list) or not blocks:
            return None
        block_props = blocks[0].get("props") if isinstance(blocks[0], dict) else None
        if not isinstance(block_props, dict):
            return None
        body = block_props.get("body")
        if not isinstance(body, str) or not body.strip():
            return None
        return body

    def _extract_site_page_version_title(self, *, site_page_version: SitePageVersion) -> str | None:
        body = self._extract_site_page_version_body(site_page_version)
        if body:
            return self._extract_title(body)
        puck_data = site_page_version.puck_data or {}
        root = puck_data.get("root")
        props = root.get("props") if isinstance(root, dict) else None
        title = props.get("title") if isinstance(props, dict) else None
        if isinstance(title, str) and title.strip():
            return title.strip()
        return None

    @staticmethod
    def _summarize_puck_data(puck_data: dict[str, Any]) -> dict[str, Any]:
        content = puck_data.get("content")
        top_level_types = [
            item.get("type")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("type"), str)
        ] if isinstance(content, list) else []

        summary: dict[str, Any] = {
            "topLevelTypes": top_level_types,
            "importedTemplate": is_imported_template_page_data(puck_data),
            "sectionCount": 0,
            "runtimeSectionCount": 0,
            "textOverrideCount": 0,
            "buttonOverrideCount": 0,
            "imageOverrideCount": 0,
            "sections": [],
        }
        if not is_imported_template_page_data(puck_data):
            return summary

        imported_page = content[0] if isinstance(content, list) and content else None
        page_props = imported_page.get("props") if isinstance(imported_page, dict) else None
        sections = page_props.get("content") if isinstance(page_props, dict) else None
        if not isinstance(sections, list):
            return summary

        section_summaries: list[dict[str, Any]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_props = section.get("props")
            if not isinstance(section_props, dict):
                continue
            section_blocks = section_props.get("content")
            if not isinstance(section_blocks, list):
                continue

            component_names: list[str] = []
            text_override_count = 0
            button_override_count = 0
            image_override_count = 0
            text_previews: list[str] = []

            for block in section_blocks:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                block_props = block.get("props")
                if not isinstance(block_props, dict):
                    continue
                if block_type == "ImportedRuntimeSection":
                    summary["runtimeSectionCount"] += 1
                    component_name = block_props.get("componentName")
                    if isinstance(component_name, str) and component_name.strip():
                        component_names.append(component_name.strip())
                else:
                    component_name = block_props.get("componentName")
                    if isinstance(component_name, str) and component_name.strip():
                        component_names.append(component_name.strip())

                text_items = AgentThreadsService._first_list_prop(
                    block_props,
                    "textSlots",
                    "textOverrides",
                )
                button_items = AgentThreadsService._first_list_prop(
                    block_props,
                    "buttonSlots",
                    "buttonOverrides",
                )
                image_items = AgentThreadsService._first_list_prop(
                    block_props,
                    "imageSlots",
                    "imageOverrides",
                )
                if isinstance(text_items, list):
                    text_override_count += len(text_items)
                    for item in text_items[:3]:
                        if not isinstance(item, dict):
                            continue
                        value = item.get("text")
                        if isinstance(value, str) and value.strip():
                            text_previews.append(value.strip())
                if isinstance(button_items, list):
                    button_override_count += len(button_items)
                if isinstance(image_items, list):
                    image_override_count += len(image_items)

            summary["textOverrideCount"] += text_override_count
            summary["buttonOverrideCount"] += button_override_count
            summary["imageOverrideCount"] += image_override_count
            section_summaries.append(
                {
                    "displayName": section_props.get("displayName"),
                    "sectionType": section_props.get("sectionType"),
                    "sectionKey": section_props.get("sectionKey"),
                    "componentNames": component_names,
                    "textOverrideCount": text_override_count,
                    "buttonOverrideCount": button_override_count,
                    "imageOverrideCount": image_override_count,
                    "textPreview": text_previews[:3],
                }
            )

        summary["sectionCount"] = len(section_summaries)
        summary["sections"] = section_summaries
        return summary

    @staticmethod
    def _first_list_prop(payload: dict[str, Any], *keys: str) -> list[Any] | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return None
