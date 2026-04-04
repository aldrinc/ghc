import json

from app.agent.funnel_tools import (
    DraftPersistVersionArgs,
    DraftPersistVersionTool,
    _build_puck_prompt_seed,
    _coerce_sales_pdp_import_comparison_config,
    _coerce_sales_pdp_import_guarantee_config,
    _coerce_sales_pdp_import_review_wall_config,
    _coerce_sales_pdp_import_story_config,
    _coerce_sales_pdp_import_videos_config,
    _ensure_sales_pdp_import_guarantee_image_prompt,
    _ensure_sales_pdp_guarantee_icon_prompt,
    _ensure_sales_pdp_free_gifts_icon_prompt,
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


def test_coerce_sales_pdp_import_videos_config_converts_legacy_shape():
    config = {
        "badge": "Watch the shift",
        "title": "How EMBER feels in real life",
        "videos": [
            {
                "id": "story-1",
                "thumbnail": {
                    "alt": "Morning energy story",
                    "src": "/assets/ph-3x4.svg",
                },
            },
            {
                "id": "story-2",
                "thumbnail": {
                    "alt": "Sharper focus story",
                    "assetPublicId": "asset-video-2",
                },
            },
        ],
    }

    changed = _coerce_sales_pdp_import_videos_config(config)

    assert changed is True
    assert config["badgeText"] == "Watch the shift"
    assert config["sectionTitle"] == "How EMBER feels in real life"
    assert "badge" not in config
    assert "title" not in config
    assert "videos" not in config
    assert config["cards"] == [
        {
            "id": "story-1",
            "title": "Morning energy story",
        },
        {
            "id": "story-2",
            "title": "Sharper focus story",
            "image": {
                "alt": "Sharper focus story",
                "assetPublicId": "asset-video-2",
            },
        },
    ]


def test_ensure_sales_pdp_free_gifts_icon_prompt_fills_placeholder_slot():
    gallery = {
        "freeGifts": {
            "title": "Bonus protocol guide",
            "icon": {
                "alt": "Bonus guide icon",
                "src": "/assets/ph-square.svg",
            },
        }
    }

    changed = _ensure_sales_pdp_free_gifts_icon_prompt(
        gallery=gallery,
        product_title="Ember: Brain Clarity Protocol",
    )

    assert changed is True
    icon = gallery["freeGifts"]["icon"]
    assert "Bonus guide icon" in icon["prompt"]
    assert icon["aspectRatio"] == "1:1"


def test_coerce_sales_pdp_import_story_config_converts_legacy_shape():
    config = {
        "badge": "THE PROBLEM",
        "title": "What is draining your focus",
        "paragraphs": [
            "Your brain keeps fighting low-grade stress.",
            "That leaves you foggy and depleted by noon.",
        ],
        "emphasisLine": "It does not have to feel this hard.",
        "bullets": [
            {
                "title": "Stress overload",
                "body": "Your system never gets to reset.",
            }
        ],
    }

    changed = _coerce_sales_pdp_import_story_config(config)

    assert changed is True
    assert config["eyebrow"] == "THE PROBLEM"
    assert config["headline"] == "What is draining your focus"
    assert config["body"] == [
        "Your brain keeps fighting low-grade stress.",
        "That leaves you foggy and depleted by noon.",
        "It does not have to feel this hard.",
    ]
    assert config["steps"] == [
        {
            "title": "Stress overload",
            "body": "Your system never gets to reset.",
        }
    ]


def test_coerce_sales_pdp_import_guarantee_config_converts_legacy_shape():
    config = {
        "badge": "RISK FREE GUARANTEE",
        "title": "90-Day Risk Free Guarantee",
        "paragraphs": [
            "Try EMBER for a full 90 days.",
            "If it is not a fit, we will refund you.",
        ],
        "whyTitle": "Why we can do this",
        "whyBody": "Because the protocol works when people actually follow it.",
        "closingLine": "You have nothing to lose but the brain fog.",
        "right": {
            "image": {
                "alt": "Customer with supplement box",
                "src": "https://cdn.example.com/guarantee.jpg",
            }
        },
        "iconSrc": "",
    }

    changed = _coerce_sales_pdp_import_guarantee_config(
        config=config,
        product_title="Ember: Brain Clarity Protocol",
    )

    assert changed is True
    assert config["badgeText"] == "RISK FREE GUARANTEE"
    assert config["headline"] == "90-Day Risk Free Guarantee"
    assert config["body"] == [
        "Try EMBER for a full 90 days.",
        "If it is not a fit, we will refund you.",
        "Why we can do this: Because the protocol works when people actually follow it.",
        "You have nothing to lose but the brain fog.",
    ]
    assert config["image"] == {
        "alt": "Customer with supplement box",
        "src": "https://cdn.example.com/guarantee.jpg",
    }
    assert config["iconAlt"] == "RISK FREE GUARANTEE icon"


def test_ensure_sales_pdp_guarantee_icon_prompt_fills_missing_icon_slot():
    config = {
        "headline": "90-Day Risk Free Guarantee",
        "iconAlt": "Guarantee seal",
        "iconAssetPublicId": None,
    }

    changed = _ensure_sales_pdp_guarantee_icon_prompt(
        config=config,
        product_title="Ember: Brain Clarity Protocol",
    )

    assert changed is True
    assert "Guarantee seal" in config["prompt"]
    assert config["aspectRatio"] == "1:1"


def test_coerce_sales_pdp_import_comparison_config_converts_legacy_shape():
    config = {
        "badge": "WHY EMBER WINS",
        "title": "EMBER vs the usual fixes",
        "swipeHint": "See the difference clearly",
        "columns": {
            "pup": "EMBER",
            "disposable": "Coffee + willpower",
        },
        "rows": [
            {
                "label": "Steady energy",
                "pup": "Daily support",
                "disposable": "Short-lived spike",
            }
        ],
    }

    changed = _coerce_sales_pdp_import_comparison_config(config)

    assert changed is True
    assert config["badgeText"] == "WHY EMBER WINS"
    assert config["headline"] == "EMBER vs the usual fixes"
    assert config["subheadline"] == "See the difference clearly"
    assert config["emberColumn"] == "EMBER"
    assert config["competitorColumn"] == "Coffee + willpower"
    assert config["rows"] == [
        {
            "label": "Steady energy",
            "pup": "Daily support",
            "disposable": "Short-lived spike",
            "ember": "Daily support",
            "competitor": "Short-lived spike",
        }
    ]


def test_ensure_sales_pdp_import_guarantee_image_prompt_fills_placeholder_image():
    config = {
        "headline": "90-Day Risk Free Guarantee",
        "image": {
            "alt": "Happy customer",
            "src": "/assets/ph-4x3.svg",
        },
    }

    changed = _ensure_sales_pdp_import_guarantee_image_prompt(
        config=config,
        product_title="Ember: Brain Clarity Protocol",
    )

    assert changed is True
    assert "90-Day Risk Free Guarantee" in config["image"]["prompt"]
    assert config["image"]["aspectRatio"] == "4:3"


def test_coerce_sales_pdp_import_review_wall_config_converts_legacy_shape():
    config = {
        "badge": "REAL RESULTS",
        "title": "What customers are saying",
        "ratingLabel": "4.9 out of 5 from verified buyers",
        "showMoreLabel": "See more reviews",
        "tiles": [
            {
                "id": "tile-1",
                "image": {
                    "alt": "Clearer thinking after two weeks",
                    "src": "https://cdn.example.com/review-1.jpg",
                },
            }
        ],
    }

    changed = _coerce_sales_pdp_import_review_wall_config(config)

    assert changed is True
    assert config["badgeText"] == "REAL RESULTS"
    assert config["headline"] == "What customers are saying"
    assert config["body"] == "4.9 out of 5 from verified buyers"
    assert config["ctaLabel"] == "See more reviews"
    assert config["reviews"] == [
        {
            "id": "tile-1",
            "body": "Clearer thinking after two weeks",
            "image": {
                "alt": "Clearer thinking after two weeks",
                "src": "https://cdn.example.com/review-1.jpg",
            },
        }
    ]
