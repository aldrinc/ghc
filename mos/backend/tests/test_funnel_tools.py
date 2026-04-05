import json

import pytest

from app.agent.funnel_tools import (
    ContextLoadFunnelArgs,
    ContextLoadFunnelTool,
    DraftApplyOverridesArgs,
    DraftApplyOverridesTool,
    DraftGeneratePageArgs,
    DraftGeneratePageTool,
    DraftPersistVersionArgs,
    DraftPersistVersionTool,
    _build_html_template_seed_puck_data,
    _build_puck_prompt_seed,
    _coerce_sales_pdp_import_comparison_config,
    _coerce_sales_pdp_import_guarantee_config,
    _coerce_sales_pdp_import_review_wall_config,
    _coerce_sales_pdp_import_story_config,
    _coerce_sales_pdp_import_videos_config,
    _ensure_sales_pdp_import_guarantee_image_prompt,
    _ensure_sales_pdp_import_review_wall_image_prompts,
    _ensure_sales_pdp_guarantee_icon_prompt,
    _ensure_sales_pdp_free_gifts_icon_prompt,
    _normalize_sales_pdp_import_template_tree,
    _persist_synced_object_prop,
    _resolve_base_puck_data,
)
from app.agent.types import ToolContext
from app.db.enums import FunnelPageReviewStatusEnum, FunnelPageVersionStatusEnum
from app.db.models import Client, Funnel, FunnelPage, FunnelPageVersion, Product
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

    assert source == "htmlTemplateSeed"
    assert base_puck == _build_html_template_seed_puck_data()


@pytest.mark.parametrize("template_id", ["sales-pdp", "pre-sales-listicle"])
def test_context_load_funnel_uses_exact_imported_html_component_for_template_mode(db_session, template_id: str):
    client = Client(org_id=TEST_ORG_ID, name="Test Client", industry="Wellness")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(org_id=TEST_ORG_ID, client_id=client.id, title="Ember")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    funnel = Funnel(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        name="HTML Import Funnel",
        route_slug="html-import-funnel",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    page = FunnelPage(
        funnel_id=funnel.id,
        name="Landing",
        slug="landing",
        template_id="sales-pdp",
    )
    db_session.add(page)
    db_session.commit()
    db_session.refresh(page)

    tool = ContextLoadFunnelTool()
    ctx = ToolContext(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        user_id="test-user",
        run_id="test-run",
        tool_call_id="tool-call-1",
    )
    result = tool.run(
        ctx=ctx,
        args=ContextLoadFunnelArgs(
            orgId=str(TEST_ORG_ID),
            funnelId=str(funnel.id),
            pageId=str(page.id),
            templateId=template_id,
            referenceHtmlMode="template",
        ),
    )

    assert result.ui_details["templateMode"] is False
    assert result.ui_details["templateKind"] == template_id
    assert result.ui_details["basePuckSource"] == "htmlTemplateSeed"
    assert result.ui_details["allowedTypes"] == ["ImportedHtmlDocument"]
    assert "SalesPdpPage" not in result.ui_details["allowedTypes"]
    assert "PreSalesPage" not in result.ui_details["allowedTypes"]
    assert result.ui_details["requiredTypes"] == ["ImportedHtmlDocument"]


def test_draft_generate_page_imported_html_mode_rewrites_exact_html_document(db_session, monkeypatch):
    captured: dict[str, str] = {}
    reference_html = (
        "<!doctype html><html><body><section class='hero'><h1>Original title</h1>"
        "<p>Original body.</p></section></body></html>"
    )
    rewritten_html = (
        "<!doctype html><html><body><section class='hero'><h1>Updated title</h1>"
        "<p>Updated body.</p></section></body></html>"
    )

    class _FakeLLM:
        def __init__(self) -> None:
            self.default_model = "gpt-test"

        @staticmethod
        def _response(prompt_text: str) -> str:
            captured["prompt"] = prompt_text
            return json.dumps(
                {
                    "assistantMessage": "Ember page preview.",
                    "htmlDocument": rewritten_html,
                }
            )

        def generate_text(self, prompt_text: str, params=None) -> str:
            return self._response(prompt_text)

        def stream_text(self, prompt_text: str, params=None):
            yield self._response(prompt_text)

    monkeypatch.setattr("app.agent.funnel_tools.LLMClient", _FakeLLM)
    monkeypatch.setattr("app.agent.funnel_tools._persist_agent_artifact", lambda **kwargs: None)

    tool = DraftGeneratePageTool()
    ctx = ToolContext(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        user_id="test-user",
        run_id="test-run",
        tool_call_id="tool-call-1",
    )
    gen = tool.run_stream(
        ctx=ctx,
        args=DraftGeneratePageArgs(
            orgId=str(TEST_ORG_ID),
            funnelId="funnel-id",
            pageId="page-id",
            pageName="Landing",
            prompt="Generate the page from the uploaded HTML.",
            messages=[],
            model="gpt-test",
            templateId="sales-pdp",
            templateKind="sales-pdp",
            templateMode=False,
            pageContext=[],
            basePuckData=_build_html_template_seed_puck_data(),
            productContext="Product context",
            brandDocuments=[],
            attachmentSummaries=[],
            referenceHtmlMode="template",
            referenceHtml=reference_html,
            htmlReferencePromptContext={
                "label": "page-1.html",
                "sectionOrder": ["Hero", "Proof", "FAQ"],
                "ctaTexts": ["Buy now"],
                "htmlPreview": "<section><h1>Hero</h1><p>Proof</p></section>",
            },
        ),
    )
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            result = stop.value
            break

    saved_component = result.ui_details["puckData"]["content"][0]
    assert saved_component["type"] == "ImportedHtmlDocument"
    assert saved_component["props"]["htmlDocument"] == rewritten_html
    assert "Only replace human-facing copy text inside existing text nodes" in captured["prompt"]
    assert "Preserve the exact tag order, nesting, attributes, classes, ids" in captured["prompt"]
    assert "Uploaded HTML document to rewrite in place" in captured["prompt"]
    assert reference_html in captured["prompt"]


def test_draft_apply_overrides_preserves_imported_html_freeform_structure(db_session, monkeypatch):
    client = Client(org_id=TEST_ORG_ID, name="Test Client", industry="Wellness")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(org_id=TEST_ORG_ID, client_id=client.id, title="Ember")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    funnel = Funnel(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        name="HTML Import Funnel",
        route_slug="html-import-overrides",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    page = FunnelPage(
        funnel_id=funnel.id,
        name="Landing",
        slug="landing",
        template_id="sales-pdp",
    )
    db_session.add(page)
    db_session.commit()
    db_session.refresh(page)

    monkeypatch.setattr("app.agent.funnel_tools.funnel_ai._apply_brand_logo_overrides_for_ai", lambda **kwargs: None)
    monkeypatch.setattr("app.agent.funnel_tools.funnel_ai._apply_product_image_overrides_for_ai", lambda **kwargs: None)
    monkeypatch.setattr("app.agent.funnel_tools.funnel_ai._sync_sales_pdp_header_cta_labels", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.agent.funnel_tools.funnel_ai._enforce_sales_pdp_guarantee_testimonial_only_images",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("app.agent.funnel_tools.funnel_ai._ensure_flat_vector_icon_prompts", lambda **kwargs: None)
    monkeypatch.setattr("app.agent.funnel_tools.funnel_ai._sync_config_json_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.agent.funnel_tools.funnel_ai._enforce_sales_pdp_urgency_month_rows", lambda **kwargs: None)

    tool = DraftApplyOverridesTool()
    ctx = ToolContext(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        user_id="test-user",
        run_id="test-run",
        tool_call_id="tool-call-1",
    )
    result = tool.run(
        ctx=ctx,
        args=DraftApplyOverridesArgs(
            orgId=str(TEST_ORG_ID),
            clientId=str(client.id),
            funnelId=str(funnel.id),
            pageId=str(page.id),
            puckData={
                "root": {"props": {}},
                "content": [
                    {
                        "type": "ImportedHtmlDocument",
                        "props": {
                            "id": "imported-html-document",
                            "title": "Imported Hero",
                            "htmlDocument": "<!doctype html><html><body><h1>Imported Hero</h1></body></html>",
                        },
                    }
                ],
                "zones": {},
            },
            basePuckData=_build_html_template_seed_puck_data(),
            templateKind="sales-pdp",
            referenceHtmlMode="template",
            productId=str(product.id),
        ),
    )

    assert result.ui_details["droppedExtraSectionCount"] == 0
    assert result.ui_details["restoredSectionCount"] == 0
    assert result.ui_details["puckData"]["content"][0]["type"] == "ImportedHtmlDocument"


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


def test_persist_synced_object_prop_updates_config_and_config_json():
    props = {
        "config": {
            "headline": "90-Day Risk Free Guarantee",
            "iconAlt": "Guarantee seal",
            "iconAssetPublicId": "",
        },
        "configJson": json.dumps(
            {
                "headline": "90-Day Risk Free Guarantee",
                "iconAlt": "Guarantee seal",
                "iconAssetPublicId": "",
            }
        ),
    }
    value = {
        "headline": "90-Day Risk Free Guarantee",
        "iconAlt": "Guarantee seal",
        "iconAssetPublicId": "",
        "prompt": "Minimal flat vector ecommerce guarantee icon representing Guarantee seal.",
        "aspectRatio": "1:1",
    }

    _persist_synced_object_prop(
        props,
        source="configJson",
        object_key="config",
        json_key="configJson",
        value=value,
    )

    assert props["config"] == value
    assert json.loads(props["configJson"]) == value


def test_normalize_sales_pdp_import_template_tree_updates_zone_guarantee_icon_prompt():
    puck_data = {
        "zones": {
            "sales-pdp-page:content": [
                {
                    "type": "SalesPdpGuarantee",
                    "props": {
                        "id": "sales-pdp-guarantee",
                        "config": {
                            "headline": "The Complete Clarity Promise",
                            "iconAlt": "Guarantee seal",
                            "iconSrc": "",
                            "iconAssetPublicId": "",
                        },
                    },
                }
            ]
        }
    }

    changed = _normalize_sales_pdp_import_template_tree(
        puck_data=puck_data,
        product_title="Ember: Brain Clarity Protocol",
    )

    assert changed == 1
    config = puck_data["zones"]["sales-pdp-page:content"][0]["props"]["config"]
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


def test_ensure_sales_pdp_import_review_wall_image_prompts_fills_placeholders():
    config = {
        "reviews": [
            {
                "title": "Sharper mornings",
                "body": "I feel clear and steady before work now.",
                "image": {
                    "alt": "Customer portrait",
                    "src": "/assets/ph-3x4.svg",
                },
            }
        ]
    }

    changed = _ensure_sales_pdp_import_review_wall_image_prompts(
        config=config,
        product_title="Ember: Brain Clarity Protocol",
    )

    assert changed is True
    image = config["reviews"][0]["image"]
    assert "Sharper mornings" in image["prompt"]
    assert image["aspectRatio"] == "3:4"
