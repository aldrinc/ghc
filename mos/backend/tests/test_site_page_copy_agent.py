from app.services.site_page_copy_agent import (
    SitePageCopyAgentError,
    apply_site_page_copy_assignments,
    chunk_site_page_copy_batches,
    extract_site_page_copy_slots,
    group_site_page_copy_slots,
    parse_site_page_copy_agent_response,
)
import pytest


def _build_imported_page_puck() -> dict:
    return {
        "root": {"props": {"title": "OMNI Creatine Gummy"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "OMNI Creatine Gummy",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "comparison-section",
                                "displayName": "Why Choose OMNI?",
                                "sourceSectionId": "us-vs-them",
                                "sectionType": "comparison_table",
                                "content": [
                                    {
                                        "type": "ImportedComparisonSection",
                                        "props": {
                                            "id": "comparison-block",
                                            "componentName": "UsVsThem",
                                            "textSlots": [
                                                {
                                                    "label": "Headline part 1",
                                                    "originalText": "Why Choose",
                                                    "text": "Why Choose",
                                                },
                                                {
                                                    "label": "Headline part 2",
                                                    "originalText": "OMNI?",
                                                    "text": "OMNI?",
                                                },
                                                {
                                                    "label": "Column 1",
                                                    "originalText": "OMNI Gummies",
                                                    "text": "OMNI Gummies",
                                                },
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "proof-section",
                                "displayName": "Snackable. Packable. Backed by Studies.",
                                "sourceSectionId": "snackable-packable",
                                "sectionType": "proof_bar",
                                "content": [
                                    {
                                        "type": "ImportedProofBarSection",
                                        "props": {
                                            "id": "proof-block",
                                            "componentName": "SnackablePackable",
                                            "textSlots": [
                                                {
                                                    "label": "Stat 1 value",
                                                    "originalText": "80%",
                                                    "text": "80%",
                                                },
                                                {
                                                    "label": "Stat 1 description",
                                                    "originalText": "Demonstrated increases in strength or power output.",
                                                    "text": "Demonstrated increases in strength or power output.",
                                                },
                                            ],
                                            "buttonSlots": [
                                                {
                                                    "label": "Primary CTA",
                                                    "originalText": "TRY OMNI NOW",
                                                    "text": "TRY OMNI NOW",
                                                    "href": "",
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "faq-section",
                                "displayName": "Any Last Questions?",
                                "sourceSectionId": "any-last-questions",
                                "sectionType": "faq",
                                "content": [
                                    {
                                        "type": "ImportedFaqSection",
                                        "props": {
                                            "id": "faq-block",
                                            "componentName": "AnyLastQuestions",
                                            "textSlots": [
                                                {
                                                    "label": "FAQ 1 question",
                                                    "originalText": "How many gummies should I take daily?",
                                                    "text": "How many gummies should I take daily?",
                                                },
                                                {
                                                    "label": "FAQ 1 answer",
                                                    "originalText": "Take 3 gummies daily.",
                                                    "text": "Take 3 gummies daily.",
                                                },
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "runtime-section",
                                "displayName": "Product Purchase",
                                "sourceSectionId": "product-purchase-section",
                                "sectionType": "bundle_selector",
                                "content": [
                                    {
                                        "type": "ImportedRuntimeSection",
                                        "props": {
                                            "id": "runtime-block",
                                            "componentName": "ProductPurchaseSection",
                                            "textOverrides": [
                                                {
                                                    "label": "Headline",
                                                    "originalText": "OMNI Creatine Gummy",
                                                    "text": "OMNI Creatine Gummy",
                                                }
                                            ],
                                            "buttonOverrides": [
                                                {
                                                    "label": "Buy now",
                                                    "originalText": "BUY NOW",
                                                    "text": "BUY NOW",
                                                    "href": "#shop",
                                                }
                                            ],
                                            "imageOverrides": [
                                                {
                                                    "label": "Hero cover",
                                                    "originalSrc": "https://cdn.example.com/omni-cover.jpg",
                                                    "src": "",
                                                    "alt": "",
                                                }
                                            ],
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


def test_extract_site_page_copy_slots_includes_source_backed_imported_blocks():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())

    by_path = {slot.path: slot for slot in slots}

    comparison_path = "/content/0/props/content/0/props/content/0/props/textSlots/2/text"
    proof_stat_path = "/content/0/props/content/1/props/content/0/props/textSlots/0/text"
    proof_button_path = "/content/0/props/content/1/props/content/0/props/buttonSlots/0/text"
    faq_path = "/content/0/props/content/2/props/content/0/props/textSlots/1/text"
    runtime_path = "/content/0/props/content/3/props/content/0/props/textOverrides/0/text"
    runtime_image_path = "/content/0/props/content/3/props/content/0/props/imageOverrides/0/src"

    assert comparison_path in by_path
    assert proof_stat_path in by_path
    assert proof_button_path in by_path
    assert faq_path in by_path
    assert runtime_path in by_path
    assert runtime_image_path in by_path

    assert by_path[comparison_path].current_value == "OMNI Gummies"
    assert by_path[proof_stat_path].current_value == "80%"
    assert by_path[proof_button_path].current_value == "TRY OMNI NOW"
    assert by_path[faq_path].current_value == "Take 3 gummies daily."
    assert by_path[runtime_path].current_value == "OMNI Creatine Gummy"
    assert by_path[runtime_image_path].current_value == "https://cdn.example.com/omni-cover.jpg"


def test_apply_site_page_copy_assignments_updates_imported_text_slots_and_legacy_overrides():
    puck_data = _build_imported_page_puck()

    updated = apply_site_page_copy_assignments(
        base_puck_data=puck_data,
        assignments=[
            {
                "path": "/content/0/props/content/0/props/content/0/props/textSlots/2/text",
                "value": "The Honest Herbalist Handbook",
            },
            {
                "path": "/content/0/props/content/1/props/content/0/props/textSlots/0/text",
                "value": "300+",
            },
            {
                "path": "/content/0/props/content/1/props/content/0/props/buttonSlots/0/text",
                "value": "GET THE HANDBOOK",
            },
            {
                "path": "/content/0/props/content/2/props/content/0/props/textSlots/0/text",
                "value": "How much should I take?",
            },
            {
                "path": "/content/0/props/content/3/props/content/0/props/textOverrides/0/text",
                "value": "Handbook + Bonus Guide",
            },
            {
                "path": "/content/0/props/content/3/props/content/0/props/imageOverrides/0/src",
                "value": "https://cdn.example.com/handbook-cover.jpg",
            },
        ],
    )

    content = updated["content"][0]["props"]["content"]
    assert content[0]["props"]["content"][0]["props"]["textSlots"][2]["text"] == "The Honest Herbalist Handbook"
    assert content[1]["props"]["content"][0]["props"]["textSlots"][0]["text"] == "300+"
    assert content[1]["props"]["content"][0]["props"]["buttonSlots"][0]["text"] == "GET THE HANDBOOK"
    assert content[2]["props"]["content"][0]["props"]["textSlots"][0]["text"] == "How much should I take?"
    assert content[3]["props"]["content"][0]["props"]["textOverrides"][0]["text"] == "Handbook + Bonus Guide"
    assert content[3]["props"]["content"][0]["props"]["imageOverrides"][0]["src"] == "https://cdn.example.com/handbook-cover.jpg"


def test_parse_site_page_copy_agent_response_errors_cleanly_on_non_json_output():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())

    with pytest.raises(SitePageCopyAgentError, match="required JSON object"):
        parse_site_page_copy_agent_response(
            raw_output="I wrote the assignments to a file instead.",
            base_puck_data=_build_imported_page_puck(),
            slots=slots,
        )


def test_chunk_site_page_copy_batches_splits_large_sections_without_reordering_slots():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())
    batches = group_site_page_copy_slots(slots)

    chunked = chunk_site_page_copy_batches(batches, max_slots_per_batch=1)

    assert len(chunked) == len(slots)
    assert [chunk.slots[0].path for chunk in chunked] == [slot.path for slot in slots]
    assert chunked[0].batch_key.endswith(":chunk1")


def test_chunk_site_page_copy_batches_keeps_button_slots_with_section_context():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())
    batches = group_site_page_copy_slots(slots)

    chunked = chunk_site_page_copy_batches(batches, max_slots_per_batch=3)

    runtime_chunks = [
        chunk for chunk in chunked if chunk.component_name == "ProductPurchaseSection"
    ]

    assert len(runtime_chunks) == 1
    assert [slot.kind for slot in runtime_chunks[0].slots] == ["text", "button", "image_src"]
    assert [slot.path for slot in runtime_chunks[0].slots] == [
        "/content/0/props/content/3/props/content/0/props/textOverrides/0/text",
        "/content/0/props/content/3/props/content/0/props/buttonOverrides/0/text",
        "/content/0/props/content/3/props/content/0/props/imageOverrides/0/src",
    ]
