from copy import deepcopy
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from app.services.agent_threads import AgentThreadsService
from app.services.hermes_sidecar import HermesRunResult
from app.services.site_page_copy_agent import (
    chunk_site_page_copy_batches,
    extract_site_page_copy_slots,
    group_site_page_copy_slots,
)


def _build_imported_page_puck() -> dict:
    return {
        "root": {"props": {"title": "The Honest Herbalist Handbook"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "The Honest Herbalist Handbook",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "hero-section",
                                "displayName": "Hero",
                                "sourceSectionId": "hero",
                                "sectionType": "hero",
                                "content": [
                                    {
                                        "type": "ImportedHeroSection",
                                        "props": {
                                            "id": "hero-block",
                                            "componentName": "HeroSection",
                                            "textSlots": [
                                                {
                                                    "label": "Headline",
                                                    "originalText": "Old hero headline",
                                                    "text": "Old hero headline",
                                                }
                                            ],
                                            "buttonSlots": [],
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "proof-section",
                                "displayName": "Proof",
                                "sourceSectionId": "proof",
                                "sectionType": "proof_bar",
                                "content": [
                                    {
                                        "type": "ImportedProofBarSection",
                                        "props": {
                                            "id": "proof-block",
                                            "componentName": "ProofBar",
                                            "textSlots": [
                                                {
                                                    "label": "Stat",
                                                    "originalText": "Old proof stat",
                                                    "text": "Old proof stat",
                                                }
                                            ],
                                            "buttonSlots": [],
                                        },
                                    }
                                ],
                            },
                        },
                    ],
                },
            }
        ],
        "zones": {},
    }


def test_run_page_copy_batches_resumes_last_hermes_session(monkeypatch):
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    service.threads_repo.list_turns = lambda thread_id: []
    monkeypatch.setattr(service, "_build_site_page_listing", lambda site_id: [])

    base_puck = _build_imported_page_puck()
    slots = extract_site_page_copy_slots(base_puck)
    slot_batches = chunk_site_page_copy_batches(
        group_site_page_copy_slots(slots),
        max_slots_per_batch=1,
    )

    call_session_ids: list[str | None] = []

    def fake_run_turn(*, runtime_home, query, hermes_session_id):
        call_session_ids.append(hermes_session_id)
        batch = slot_batches[len(call_session_ids) - 1]
        slot = batch.slots[0]
        return HermesRunResult(
            response_text=(
                '{"assistantMessage":"batch complete","assignments":'
                f'[{{"path":"{slot.path}","value":"Updated {len(call_session_ids)}"}}]'
                "}"
            ),
            hermes_session_id="session-1",
            raw_output="ok",
            usage={
                "promptTokens": 10 * len(call_session_ids),
                "completionTokens": len(call_session_ids),
                "totalTokens": 11 * len(call_session_ids),
                "cacheReadTokens": 5 * len(call_session_ids),
                "cacheWriteTokens": 3 * len(call_session_ids),
                "apiCallCount": 1,
            },
        )

    monkeypatch.setattr(service.hermes, "run_turn", fake_run_turn)

    result, batch_reports, hermes_session_id, raw_output, aggregate_usage = service._run_page_copy_batches(
        thread_id="thread-1",
        thread=SimpleNamespace(id="thread-1"),
        user_content="Revise the stale imported copy.",
        runtime_home=Path("/tmp/runtime-home"),
        hermes_session_id=None,
        site=cast(Any, SimpleNamespace(id="site-1", name="Honest Herbalist")),
        page=cast(
            Any,
            SimpleNamespace(
            id="page-1",
            name="Home",
            slug="home",
            page_type="home",
            page_role="home",
        ),
        ),
        base_puck_data=base_puck,
        slots=slots,
        slot_batches=slot_batches,
    )

    assert call_session_ids == [None, "session-1"]
    assert hermes_session_id == "session-1"
    assert len(result.assignments) == 2
    assert len(batch_reports) == 2
    assert batch_reports[0]["usage"] == {
        "promptTokens": 10,
        "completionTokens": 1,
        "totalTokens": 11,
        "cacheReadTokens": 5,
        "cacheWriteTokens": 3,
        "apiCallCount": 1,
    }
    assert aggregate_usage == {
        "promptTokens": 30,
        "completionTokens": 3,
        "totalTokens": 33,
        "cacheReadTokens": 15,
        "cacheWriteTokens": 9,
        "apiCallCount": 2,
    }
    assert raw_output


def test_execute_page_copy_batch_uses_json_only_retry_for_single_slot_repairs(monkeypatch):
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    monkeypatch.setattr(service, "_build_site_page_listing", lambda site_id: [])

    base_puck = _build_imported_page_puck()
    slots = extract_site_page_copy_slots(base_puck)
    scoped_slots = slots[:2]
    captured_queries: list[str] = []
    responses = iter(
        [
            HermesRunResult(
                response_text="I tightened the section copy.",
                hermes_session_id="session-1",
                raw_output="I tightened the section copy.",
                usage={},
            ),
            HermesRunResult(
                response_text="Updated slot value only.",
                hermes_session_id="session-1",
                raw_output="Updated slot value only.",
                usage={},
            ),
            HermesRunResult(
                response_text="Still fixing the slot.",
                hermes_session_id="session-1",
                raw_output="Still fixing the slot.",
                usage={},
            ),
            HermesRunResult(
                response_text=(
                    '{"assistantMessage":"Updated slot.","assignments":'
                    f'[{{"path":"{scoped_slots[0].path}","value":"Sharper Hero"}}]'
                    "}"
                ),
                hermes_session_id="session-1",
                raw_output="ok",
                usage={},
            ),
            HermesRunResult(
                response_text=(
                    '{"assistantMessage":"Updated slot.","assignments":'
                    f'[{{"path":"{scoped_slots[1].path}","value":"Clean proof line"}}]'
                    "}"
                ),
                hermes_session_id="session-1",
                raw_output="ok",
                usage={},
            ),
        ]
    )

    def fake_run_turn(*, runtime_home, query, hermes_session_id):
        captured_queries.append(query)
        return next(responses)

    monkeypatch.setattr(service.hermes, "run_turn", fake_run_turn)

    _, result, repair_count, _ = service._execute_page_copy_batch(
        runtime_home=Path("/tmp/runtime-home"),
        session_id=None,
        base_puck_data=base_puck,
        scoped_slots=scoped_slots,
        query="Rewrite the current batch.",
        batch_note="Batch scope: section 1 of 2.",
        site=cast(Any, SimpleNamespace(name="Ember")),
        page=cast(Any, SimpleNamespace(name="Home", slug="home")),
        page_context=[],
        user_content="Keep this page concise.",
    )

    assert repair_count == 3
    assert len(result.assignments) == 2
    assert result.assignments[0]["value"] == "Sharper Hero"
    assert result.assignments[1]["value"] == "Clean proof line"
    assert len(captured_queries) == 5
    assert any(f'"path": "{scoped_slots[0].path}"' in query for query in captured_queries)


def test_get_or_create_page_thread_reuses_existing_thread():
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    existing_thread = SimpleNamespace(id="thread-1")
    service.threads_repo.find_latest_for_page = MagicMock(return_value=existing_thread)
    service.get_thread_detail = MagicMock(return_value={"thread": {"id": "thread-1"}})

    detail = service.get_or_create_page_thread(
        client_id="client-1",
        product_id="product-1",
        site_id="site-1",
        page_id="page-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
    )

    assert detail == {"thread": {"id": "thread-1"}}
    service.get_thread_detail.assert_called_once_with(thread_id="thread-1")


def test_get_or_create_page_thread_uses_active_binding_when_creating():
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    service.threads_repo.find_latest_for_page = MagicMock(return_value=None)
    binding = SimpleNamespace(
        bundle_key="honest_herbalist_v1",
        runtime_profile_key="page-copy",
        strategy_bundle_id="bundle-export-1",
        status="active",
    )
    service.bindings_repo.get_by_page = MagicMock(return_value=binding)
    service.create_thread = MagicMock(return_value={"thread": {"id": "thread-2"}})

    detail = service.get_or_create_page_thread(
        client_id="client-1",
        product_id="product-1",
        site_id="site-1",
        page_id="page-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
    )

    assert detail == {"thread": {"id": "thread-2"}}
    service.create_thread.assert_called_once_with(
        client_id="client-1",
        product_id="product-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
        bundle_key="honest_herbalist_v1",
        runtime_profile_key="page-copy",
        strategy_bundle_id="bundle-export-1",
        title=None,
        metadata_json=None,
        site_id="site-1",
        page_id="page-1",
    )


def test_get_or_create_page_thread_force_new_creates_fresh_thread():
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    service.threads_repo.find_latest_for_page = MagicMock(return_value=SimpleNamespace(id="thread-old"))
    binding = SimpleNamespace(
        bundle_key="honest_herbalist_v1",
        runtime_profile_key="page-copy",
        strategy_bundle_id="bundle-export-1",
        status="active",
    )
    service.bindings_repo.get_by_page = MagicMock(return_value=binding)
    service.create_thread = MagicMock(return_value={"thread": {"id": "thread-new"}})

    detail = service.get_or_create_page_thread(
        client_id="client-1",
        product_id="product-1",
        site_id="site-1",
        page_id="page-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
        force_new=True,
    )

    assert detail == {"thread": {"id": "thread-new"}}
    service.create_thread.assert_called_once()


def test_get_or_create_page_thread_force_new_reuses_existing_thread_runtime_context():
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    existing_thread = SimpleNamespace(
        id="thread-old",
        bundle_key="honest_herbalist_v1",
        runtime_profile_key="page-copy",
        strategy_bundle_id="bundle-export-1",
    )
    service.threads_repo.find_latest_for_page = MagicMock(return_value=existing_thread)
    service.bindings_repo.get_by_page = MagicMock(return_value=None)
    service.create_thread = MagicMock(return_value={"thread": {"id": "thread-new"}})

    detail = service.get_or_create_page_thread(
        client_id="client-1",
        product_id="product-1",
        site_id="site-1",
        page_id="page-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
        force_new=True,
    )

    assert detail == {"thread": {"id": "thread-new"}}
    service.create_thread.assert_called_once_with(
        client_id="client-1",
        product_id="product-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
        bundle_key="honest_herbalist_v1",
        runtime_profile_key="page-copy",
        strategy_bundle_id="bundle-export-1",
        title=None,
        metadata_json=None,
        site_id="site-1",
        page_id="page-1",
    )


def test_get_or_create_page_thread_force_new_prefers_active_binding_context_over_existing_thread():
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    existing_thread = SimpleNamespace(
        id="thread-old",
        bundle_key="honest_herbalist_v1",
        runtime_profile_key="page-copy",
        strategy_bundle_id="bundle-export-1",
    )
    active_binding = SimpleNamespace(
        bundle_key="honest_herbalist_v1",
        runtime_profile_key=None,
        strategy_bundle_id=None,
        status="active",
    )
    service.threads_repo.find_latest_for_page = MagicMock(return_value=existing_thread)
    service.bindings_repo.get_by_page = MagicMock(return_value=active_binding)
    service.create_thread = MagicMock(return_value={"thread": {"id": "thread-new"}})

    detail = service.get_or_create_page_thread(
        client_id="client-1",
        product_id="product-1",
        site_id="site-1",
        page_id="page-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
        force_new=True,
    )

    assert detail == {"thread": {"id": "thread-new"}}
    service.create_thread.assert_called_once_with(
        client_id="client-1",
        product_id="product-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
        bundle_key="honest_herbalist_v1",
        runtime_profile_key=None,
        strategy_bundle_id=None,
        title=None,
        metadata_json=None,
        site_id="site-1",
        page_id="page-1",
    )


def test_reset_runtime_session_clears_stale_hermes_state():
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    runtime_session = SimpleNamespace(
        hermes_session_id="session-1",
        status="error",
        last_error="stale session",
    )
    service._require_thread = MagicMock(return_value=SimpleNamespace(id="thread-1"))
    service.runtime_repo.get_by_thread = MagicMock(return_value=runtime_session)
    service.runtime_repo.update_session = MagicMock(return_value=runtime_session)
    service.get_thread_detail = MagicMock(return_value={"thread": {"id": "thread-1"}})

    detail = service.reset_runtime_session(thread_id="thread-1")

    assert detail == {"thread": {"id": "thread-1"}}
    assert runtime_session.hermes_session_id is None
    assert runtime_session.status == "ready"
    assert runtime_session.last_error is None
    service.runtime_repo.update_session.assert_called_once_with(runtime_session=runtime_session)
    service.get_thread_detail.assert_called_once_with(thread_id="thread-1")
    service.session.commit.assert_called_once()


def test_create_thread_does_not_force_page_copy_profile_without_strategy_bundle(monkeypatch):
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    client = SimpleNamespace(id="client-1")
    product = SimpleNamespace(id="product-1")
    site = SimpleNamespace(id="site-1")
    page = SimpleNamespace(id="page-1")
    thread_record = SimpleNamespace(id="thread-1")
    runtime_session = SimpleNamespace(id="runtime-1")
    service._require_client = MagicMock(return_value=client)
    service._require_product = MagicMock(return_value=product)
    service._require_site_page = MagicMock(return_value=(site, page))
    service._load_page_agent_base_puck_data = MagicMock(return_value=_build_imported_page_puck())
    service.bindings_repo.get_by_page = MagicMock(return_value=SimpleNamespace(runtime_profile_key=None, strategy_bundle_id=None))
    service._build_page_context = MagicMock(return_value={"pageId": "page-1"})
    service._resolve_projection = MagicMock(
        return_value=(SimpleNamespace(runtime_home=Path("/tmp/runtime"), projection_hash="hash-1", toolsets=[]), {}, None)
    )
    service.threads_repo.create_thread = MagicMock(return_value=thread_record)
    service.runtime_repo.create_session = MagicMock(return_value=runtime_session)
    service.get_thread_detail = MagicMock(return_value={"thread": {"id": "thread-1"}})

    detail = service.create_thread(
        client_id="client-1",
        product_id="product-1",
        agent_profile="copy",
        objective_type="page_copy_agent",
        bundle_key="honest_herbalist_v1",
        site_id="site-1",
        page_id="page-1",
    )

    assert detail == {"thread": {"id": "thread-1"}}
    _, kwargs = service._resolve_projection.call_args
    assert kwargs["runtime_profile_key"] is None
    assert kwargs["strategy_bundle_id"] is None


def test_resolve_runtime_toolsets_adds_page_editor_for_page_orchestrator():
    service = AgentThreadsService(session=MagicMock(), org_id="org-1", user_id="user-1")
    toolsets = service._resolve_runtime_toolsets(
        thread=SimpleNamespace(page_id="page-1", objective_type="page_orchestrator"),
        projection_toolsets=["file", "skills"],
    )

    assert toolsets == ["file", "skills", service.hermes.page_editor_toolset_name()]


def test_post_message_page_orchestrator_attaches_tool_created_page_version(tmp_path):
    session = MagicMock()
    service = AgentThreadsService(session=session, org_id="org-1", user_id="user-1")

    thread = SimpleNamespace(
        id="thread-1",
        client_id="client-1",
        product_id="product-1",
        page_id="page-1",
        site_id="site-1",
        objective_type="page_orchestrator",
        agent_profile="copy",
        bundle_key="ember_skills_v1",
        runtime_profile_key=None,
        strategy_bundle_id=None,
        metadata_json={},
        title="Page agent",
    )
    runtime_session = SimpleNamespace(
        hermes_session_id="session-1",
        status="ready",
        last_error=None,
        runtime_home="",
        projection_hash="",
        toolsets=[],
        last_used_at=datetime.now(timezone.utc),
    )
    binding = SimpleNamespace(status="active", runtime_profile_key=None, strategy_bundle_id=None)
    page_context = {"latestApprovedPuckData": _build_imported_page_puck()}
    projection = SimpleNamespace(runtime_home=tmp_path / "runtime-home", projection_hash="hash-1", toolsets=["all"])
    site = SimpleNamespace(id="site-1", name="Honest Herbalist")
    page = SimpleNamespace(id="page-1", name="Home", slug="home", page_type="home", page_role="home")

    service._require_thread = MagicMock(return_value=thread)
    service.runtime_repo.get_by_thread = MagicMock(return_value=runtime_session)
    service._require_site_page = MagicMock(return_value=(site, page))
    service.bindings_repo.get_by_page = MagicMock(return_value=binding)
    service._build_page_context = MagicMock(return_value=page_context)
    service._resolve_projection = MagicMock(return_value=(projection, {}, None))
    service._runtime_page_context_was_mutated = MagicMock(return_value=False)
    service.runtime_repo.update_session = MagicMock()
    service.threads_repo.update_thread = MagicMock()
    service.threads_repo.next_turn_seq = MagicMock(side_effect=[1, 2])
    service.threads_repo.create_turn = MagicMock()
    service.hermes.runtime_summary = MagicMock(return_value={"model": "claude-haiku", "toolsets": ["file", "skills"]})
    service.runs_repo.create_run = MagicMock(
        return_value=SimpleNamespace(id="run-1", started_at=datetime.now(timezone.utc))
    )
    service.runs_repo.finish_run = MagicMock()

    mutated_puck_data = deepcopy(page_context["latestApprovedPuckData"])
    mutated_puck_data["content"][0]["props"]["content"][0]["props"]["content"][0]["props"]["textSlots"][0]["text"] = (
        "A Honest Herbal Reference"
    )

    def fake_run_turn(*, runtime_home, query, hermes_session_id, toolsets):
        assert service.hermes.page_editor_toolset_name() in toolsets
        return HermesRunResult(
            response_text="Done. Hero section headline updated.",
            hermes_session_id="session-2",
            raw_output="ok",
            usage={
                "promptTokens": 10,
                "completionTokens": 2,
                "totalTokens": 12,
                "cacheReadTokens": 0,
                "cacheWriteTokens": 0,
                "apiCallCount": 1,
            },
        )

    service.hermes.run_turn = fake_run_turn
    created_artifact = SimpleNamespace(id="artifact-1", kind="page_chat_response", key="thread:thread-1", data_json={})
    service.artifacts_repo.create = MagicMock(return_value=created_artifact)
    created_page_version = SimpleNamespace(
        id="version-1",
        page_id="page-1",
        puck_data=mutated_puck_data,
        status="draft",
        provenance={},
        source_type="hermes_sidecar",
        source_id="thread-1",
        ai_metadata={},
        diff_summary="",
    )
    service._resolve_page_orchestrator_tool_page_version = MagicMock(return_value=created_page_version)
    service.get_thread_detail = MagicMock(return_value={"thread": {"id": "thread-1"}})

    detail = service.post_message(thread_id="thread-1", content='Update the header to "A Honest Herbal Reference"')

    assert detail == {"thread": {"id": "thread-1"}}
    artifact_kwargs = service.artifacts_repo.create.call_args.kwargs
    assert artifact_kwargs["data_json"]["materializedPageEdit"] is True
    assert artifact_kwargs["data_json"]["puckData"] is not None
    assistant_turn_kwargs = service.threads_repo.create_turn.call_args_list[1].kwargs
    assert assistant_turn_kwargs["site_page_version_id"] == "version-1"
    assert runtime_session.hermes_session_id == "session-2"
