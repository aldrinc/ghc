from __future__ import annotations

from types import SimpleNamespace

from app.agent import funnel_objectives


def _sample_import_v1_sales_puck() -> dict[str, object]:
    return {
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "schemaVersion": "import-v1",
                    "content": [
                        {
                            "type": "SalesPdpHero",
                            "props": {
                                "config": {
                                    "gallery": {
                                        "slides": [
                                            {"alt": f"Sales PDP carousel image {idx + 1}"}
                                            for idx in range(6)
                                        ]
                                    },
                                    "purchase": {
                                        "cta": {"labelTemplate": "Get started - {price}"},
                                        "offer": {
                                            "options": [
                                                {
                                                    "id": "offer-1",
                                                    "title": "1x Pack",
                                                    "price": 38.0,
                                                    "image": {
                                                        "alt": "1x Pack",
                                                        "assetPublicId": "offer-image-public-id",
                                                    },
                                                }
                                            ]
                                        },
                                    },
                                }
                            },
                        },
                        {
                            "type": "SalesPdpReviewWall",
                            "props": {
                                "config": {
                                    "headline": "What women are saying",
                                    "reviews": [
                                        {
                                            "body": "My focus came back within days.",
                                            "author": "Tanya",
                                            "rating": 5,
                                            "image": {
                                                "alt": "Swipe-style testimonial card",
                                                "testimonialTemplate": "review_card",
                                            },
                                        }
                                    ],
                                }
                            },
                        },
                        {
                            "type": "SalesPdpReviews",
                            "props": {
                                "config": {
                                    "data": {
                                        "productId": "product-1",
                                        "summary": {
                                            "averageRating": 4.9,
                                            "totalReviews": 1824,
                                        },
                                    }
                                }
                            },
                        },
                    ],
                },
            }
        ]
    }


class _FakeRuntime:
    last: "_FakeRuntime | None" = None

    def __init__(self, *args, **kwargs):
        self.calls: list[str] = []
        self.finished: dict[str, object] | None = None
        self.base_puck = _sample_import_v1_sales_puck()
        _FakeRuntime.last = self

    def begin_run(self, **kwargs):
        return SimpleNamespace(run_id="run-import-v1")

    def finish_run(self, **kwargs):
        self.finished = kwargs

    def invoke_tool_stream(self, *, tool, raw_args, **kwargs):
        tool_name = type(tool).__name__
        self.calls.append(tool_name)

        if tool_name == "ContextLoadFunnelTool":
            ui_details = {
                "clientId": "client-1",
                "productId": "product-1",
                "pageName": "Sales Page",
                "templateId": "sales-pdp",
                "templateKind": "sales-pdp",
                "templateMode": True,
                "pageContext": [],
                "basePuckData": self.base_puck,
                "allowedTypes": [],
                "requiredTypes": [],
                "pageIdSet": [],
            }
        elif tool_name == "ContextLoadProductOfferTool":
            ui_details = {"productContext": "Product context"}
        elif tool_name == "ContextLoadDesignTokensTool":
            ui_details = {"designSystemTokens": {}, "brandLogoAssetPublicId": None}
        elif tool_name == "ContextLoadBrandDocsTool":
            ui_details = {"documentBlocks": []}
        elif tool_name == "DraftApplyOverridesTool":
            ui_details = {"puckData": raw_args["puckData"], "applied": []}
        elif tool_name == "DraftValidateTool":
            ui_details = {"ok": True, "errors": []}
        elif tool_name == "ImagesPlanTool":
            ui_details = {"puckData": raw_args["puckData"], "imagePlans": []}
        elif tool_name == "ImagesGenerateTool":
            ui_details = {"puckData": raw_args["puckData"], "generatedImages": []}
        elif tool_name == "DraftPersistVersionTool":
            ui_details = {"draftVersionId": "draft-persist"}
        elif tool_name == "TestimonialsGenerateAndApplyTool":
            ui_details = {
                "draftVersionId": "draft-testimonials",
                "puckData": self.base_puck,
                "generatedTestimonials": [{"target": "sales_pdp.reviewWall.reviews[0]"}],
            }
        elif tool_name == "SalesPdpCarouselGenerateAndApplyTool":
            ui_details = {
                "draftVersionId": "draft-carousel",
                "puckData": self.base_puck,
                "generatedCarouselImages": [{"target": "sales_pdp.hero.gallery.slides[1]"}],
            }
        else:
            raise AssertionError(f"Unexpected tool call: {tool_name}")

        if False:
            yield None
        return SimpleNamespace(ui_details=ui_details)


def test_import_v1_sales_pages_still_run_testimonials_and_carousel_generation(db_session, monkeypatch):
    monkeypatch.setattr(funnel_objectives, "AgentRuntime", _FakeRuntime)
    monkeypatch.setattr(
        funnel_objectives,
        "LLMClient",
        lambda: SimpleNamespace(default_model="claude-sonnet"),
    )

    stream = funnel_objectives.run_generate_page_draft_stream(
        session=db_session,
        org_id="org-1",
        user_id="user-1",
        funnel_id="funnel-1",
        page_id="page-1",
        prompt="Refresh the imported sales page.",
        generate_images=True,
        generate_testimonials=True,
        skip_draft_generation=True,
        template_id="sales-pdp",
    )

    events: list[dict[str, object]] = []
    try:
        while True:
            events.append(next(stream))
    except StopIteration as stop:
        result = stop.value

    runtime = _FakeRuntime.last
    assert runtime is not None
    assert "TestimonialsGenerateAndApplyTool" in runtime.calls
    assert "SalesPdpCarouselGenerateAndApplyTool" in runtime.calls
    assert result["generatedCarouselImages"] == [{"target": "sales_pdp.hero.gallery.slides[1]"}]
    assert not any(
        event.get("type") == "status" and "Skipping legacy" in str(event.get("message") or "")
        for event in events
    )
