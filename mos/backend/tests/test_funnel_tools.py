import json

from app.agent.funnel_tools import (
    DraftPersistVersionArgs,
    DraftPersistVersionTool,
    _build_puck_prompt_seed,
    _resolve_base_puck_data,
)
from app.agent.types import ToolContext
from app.db.enums import FunnelPageReviewStatusEnum, FunnelPageVersionStatusEnum
from app.db.models import Client, Funnel, FunnelPage, FunnelPageVersion
from app.services.funnel_templates import get_funnel_template
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
        htmlReferenceSummary={
            "label": "sleep-guide.html",
            "sha256": "a" * 64,
            "characterCount": 1024,
            "title": "Sleep Guide",
            "metaDescription": "A better bedtime sales page.",
            "sectionOrder": ["Hero", "Proof", "FAQ"],
            "headings": [{"level": 1, "text": "Sleep better tonight"}],
            "ctaTexts": ["Get My Guide"],
            "faqQuestions": ["Is it printable?"],
            "proofSignals": ["Reviews / ratings"],
            "landmarks": ["header", "main", "footer"],
            "imageCount": 1,
            "imageAltTexts": ["Guide cover"],
            "formCount": 1,
            "formFieldHints": ["email: Email address"],
            "textPreview": "Sleep better tonight with a printable guide.",
            "htmlPreview": "<html><body><h1>Sleep better tonight</h1></body></html>",
        },
    )

    result = tool.run(ctx=ctx, args=args)

    db_session.refresh(page)
    version = db_session.query(FunnelPageVersion).filter(FunnelPageVersion.page_id == page.id).one()

    assert captured["funnel_id"] == str(funnel.id)
    assert page.review_status == FunnelPageReviewStatusEnum.review
    assert version.status == FunnelPageVersionStatusEnum.draft
    assert version.ai_metadata["htmlReference"]["label"] == "sleep-guide.html"
    assert version.ai_metadata["htmlReference"]["sectionOrder"] == ["Hero", "Proof", "FAQ"]
    assert result.ui_details["draftVersionId"] == str(version.id)


def test_resolve_base_puck_data_prefers_template_for_html_template_mode():
    template = get_funnel_template("sales-pdp")
    assert template is not None

    base_puck, source = _resolve_base_puck_data(
        current_puck_data={"content": [{"type": "Text", "props": {"id": "current", "text": "Current"}}]},
        latest_draft_puck_data={"content": [{"type": "Text", "props": {"id": "draft", "text": "Draft"}}]},
        template_puck_data=template.puck_data,
        reference_html_mode="template",
    )

    assert source == "template"
    assert base_puck == template.puck_data


def test_build_puck_prompt_seed_omits_template_copy_content():
    template = get_funnel_template("sales-pdp")
    assert template is not None

    prompt_seed = _build_puck_prompt_seed(template.puck_data)

    assert isinstance(prompt_seed, dict)
    serialized_seed = json.dumps(prompt_seed, ensure_ascii=False).lower()
    assert "salespdppage" in serialized_seed
    assert "puppypad" not in serialized_seed
