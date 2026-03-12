from __future__ import annotations

from app.temporal.activities import strategy_v2_launch_activities as launch_activities


def test_build_launch_workspace_context_docs_uses_campaign_scoped_doc_keys() -> None:
    campaign_id = "campaign-123"
    docs = launch_activities._build_launch_workspace_context_docs(
        campaign_id=campaign_id,
        source_stage3={"stage": 3},
        source_offer={"offer": True},
        source_copy={"headline": "Approved"},
        source_copy_context={"context": "value"},
        strategy_sheet={"goal": "Launch"},
        experiment_spec_payload={"experiment_specs": [{"id": "exp-1"}]},
        asset_brief_payload={"asset_briefs": [{"id": "brief-1"}]},
    )

    assert [doc["doc_key"] for doc in docs] == [
        "strategy_v2_stage3",
        "strategy_v2_offer",
        "strategy_v2_copy",
        "strategy_v2_copy_context",
        f"strategy_sheet:{campaign_id}",
        f"experiment_specs:{campaign_id}",
        f"asset_briefs:{campaign_id}",
    ]
    assert [doc["source_kind"] for doc in docs] == [
        "strategy_v2_stage3",
        "strategy_v2_offer",
        "strategy_v2_copy",
        "strategy_v2_copy_context",
        "strategy_sheet",
        "experiment_specs",
        "asset_briefs",
    ]


def test_persist_launch_workspace_context_docs_uploads_all_docs(monkeypatch) -> None:
    claude_calls: list[dict[str, object]] = []
    gemini_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        launch_activities,
        "ensure_uploaded_to_claude",
        lambda **kwargs: claude_calls.append(kwargs) or f"file-{len(claude_calls)}",
    )
    monkeypatch.setattr(launch_activities, "is_gemini_file_search_enabled", lambda: True)
    monkeypatch.setattr(
        launch_activities,
        "ensure_uploaded_to_gemini_file_search",
        lambda **kwargs: gemini_calls.append(kwargs),
    )

    docs = launch_activities._build_launch_workspace_context_docs(
        campaign_id="campaign-123",
        source_stage3={"stage": 3},
        source_offer={"offer": True},
        source_copy={"headline": "Approved"},
        source_copy_context={"context": "value"},
        strategy_sheet={"goal": "Launch"},
        experiment_spec_payload={"experiment_specs": [{"id": "exp-1"}]},
        asset_brief_payload={"asset_briefs": [{"id": "brief-1"}]},
    )

    launch_activities._persist_launch_workspace_context_docs(
        org_id="org-1",
        client_id="client-1",
        product_id="product-1",
        campaign_id="campaign-123",
        docs=docs,
        allow_claude_stub=True,
    )

    assert len(claude_calls) == 7
    assert len(gemini_calls) == 7
    assert {call["doc_key"] for call in claude_calls} == {doc["doc_key"] for doc in docs}
    assert all(call["idea_workspace_id"] == "campaign-123" for call in claude_calls)
    assert all(call["campaign_id"] == "campaign-123" for call in claude_calls)
    assert all(call["allow_stub"] is True for call in claude_calls)
