from app.agent.funnel_tools import DraftPersistVersionArgs, DraftPersistVersionTool
from app.agent.types import ToolContext
from app.db.enums import FunnelPageReviewStatusEnum, FunnelPageVersionStatusEnum
from app.db.models import Client, Funnel, FunnelPage, FunnelPageVersion
from tests.conftest import TEST_ORG_ID


def test_draft_persist_version_loads_funnel_context(db_session, monkeypatch):
    client = Client(org_id=TEST_ORG_ID, name="Test Client", industry="Wellness")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    funnel = Funnel(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        name="Test Funnel",
        route_slug="test-funnel-tools",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    page = FunnelPage(
        funnel_id=funnel.id,
        name="Landing",
        slug="landing",
    )
    db_session.add(page)
    db_session.commit()
    db_session.refresh(page)

    captured: dict[str, str] = {}

    def _normalize(**kwargs):
        captured["funnel_id"] = str(kwargs["funnel"].id)
        return kwargs["puck_data"]

    monkeypatch.setattr("app.agent.funnel_tools.normalize_public_page_metadata_for_context", _normalize)

    tool = DraftPersistVersionTool()
    ctx = ToolContext(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        user_id="test-user",
        run_id="test-run",
        tool_call_id="tool-call-1",
    )
    args = DraftPersistVersionArgs(
        orgId=str(TEST_ORG_ID),
        userId="test-user",
        funnelId=str(funnel.id),
        pageId=str(page.id),
        prompt="prompt",
        messages=[],
        puckData={"content": [], "root": {}},
        assistantMessage="done",
        model="baseten:moonshotai/Kimi-K2.5",
        temperature=0.7,
    )

    result = tool.run(ctx=ctx, args=args)

    db_session.refresh(page)
    version = db_session.query(FunnelPageVersion).filter(FunnelPageVersion.page_id == page.id).one()

    assert captured["funnel_id"] == str(funnel.id)
    assert page.review_status == FunnelPageReviewStatusEnum.review
    assert version.status == FunnelPageVersionStatusEnum.draft
    assert result.ui_details["draftVersionId"] == str(version.id)
