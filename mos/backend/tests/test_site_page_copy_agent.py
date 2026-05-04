from app.services.site_page_copy_agent import (
    SitePageCopyAgentError,
    SitePageCopySlot,
    _validate_site_page_copy_assignment,
    apply_site_page_copy_assignments,
    build_site_page_copy_prompt,
    chunk_site_page_copy_batches,
    extract_site_page_copy_slots,
    group_site_page_copy_slots,
    parse_site_page_copy_agent_response,
)
import json
import pytest
from types import SimpleNamespace


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


def _build_feature_stack_puck() -> dict:
    return {
        "root": {"props": {"title": "Feature Stack Page"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "Feature Stack Page",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "feature-section",
                                "displayName": "Optimize Your Routine",
                                "sourceSectionId": "optimize-your-routine",
                                "sectionType": "feature_stack",
                                "content": [
                                    {
                                        "type": "ImportedFeatureStackSection",
                                        "props": {
                                            "id": "feature-block",
                                            "componentName": "OptimizeYourRoutine",
                                            "textSlots": [
                                                {
                                                    "label": "Feature 3 description",
                                                    "originalText": (
                                                        "Know what's safe before you use it, especially with kids, "
                                                        "medications, or during pregnancy. The handbook flags critical "
                                                        "interactions and when to see a clinician."
                                                    ),
                                                    "text": (
                                                        "Know what's safe before you use it, especially with kids, "
                                                        "medications, or during pregnancy. The handbook flags critical "
                                                        "interactions and when to see a clinician."
                                                    ),
                                                }
                                            ],
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


def _build_feature_stack_puck_with_verbose_current_text() -> dict:
    return {
        "root": {"props": {"title": "Feature Stack Page"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "Feature Stack Page",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "feature-section",
                                "displayName": "Optimize Your Routine",
                                "sourceSectionId": "optimize-your-routine",
                                "sectionType": "feature_stack",
                                "content": [
                                    {
                                        "type": "ImportedFeatureStackSection",
                                        "props": {
                                            "id": "feature-block",
                                            "componentName": "OptimizeYourRoutine",
                                            "textSlots": [
                                                {
                                                    "label": "Body copy",
                                                    "originalText": "Creatine supports cellular energy and daily stamina.",
                                                    "text": (
                                                        "Creatine supports cellular energy and daily stamina for demanding work. "
                                                        "Use it to restore focus, verbal fluency, meeting confidence, and day-long "
                                                        "mental resilience with third-party tested proof behind every serving."
                                                    ),
                                                }
                                            ],
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


def _build_feature_stack_title_overflow_puck() -> dict:
    return {
        "root": {"props": {"title": "Feature Stack Page"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "Feature Stack Page",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "feature-section",
                                "displayName": "Know What You're Actually Using",
                                "sourceSectionId": "know-what-youre-actually-using",
                                "sectionType": "feature_stack",
                                "content": [
                                    {
                                        "type": "ImportedFeatureStackSection",
                                        "props": {
                                            "id": "feature-block",
                                            "componentName": "KnowWhatYoureActuallyUsing",
                                            "textSlots": [
                                                {
                                                    "label": "Feature 3 title",
                                                    "originalText": (
                                                        "NSF testing confirms dosing and purity. No marketing fluff "
                                                        "just proof that what's on the label is actually in the bottle. "
                                                        "Built for knowledge workers who demand evidence, not hype."
                                                    ),
                                                    "text": (
                                                        "NSF testing confirms dosing and purity. No marketing fluff "
                                                        "just proof that what's on the label is actually in the bottle. "
                                                        "Built for knowledge workers who demand evidence, not hype."
                                                    ),
                                                }
                                            ],
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


def _build_hero_puck_with_body_in_section_name() -> dict:
    return {
        "root": {"props": {"title": "Hero Page"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "Hero Page",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "hero-section",
                                "displayName": "Creatine For Body & Mind",
                                "sourceSectionId": "hero-section",
                                "sectionType": "hero",
                                "content": [
                                    {
                                        "type": "ImportedHeroSection",
                                        "props": {
                                            "id": "hero-block",
                                            "componentName": "HeroSection",
                                            "textSlots": [
                                                {
                                                    "label": "Headline Part 1",
                                                    "originalText": "The Honest Herbal",
                                                    "text": "The Honest Herbal",
                                                },
                                                {
                                                    "label": "Body Copy",
                                                    "originalText": (
                                                        "Organized dosing guidance, interaction warnings, and clear "
                                                        "safety notes in one place."
                                                    ),
                                                    "text": (
                                                        "Organized dosing guidance, interaction warnings, and clear "
                                                        "safety notes in one place."
                                                    ),
                                                },
                                                {
                                                    "label": "Guarantee Text",
                                                    "originalText": "60-day read-it-use-it-decide guarantee",
                                                    "text": "60-day read-it-use-it-decide guarantee",
                                                },
                                            ],
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


def _build_proof_bar_feature_puck() -> dict:
    return {
        "root": {"props": {"title": "Proof Bar"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "Proof Bar",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "proof-section",
                                "displayName": "Fresh & Light Taste",
                                "sourceSectionId": "proof-section",
                                "sectionType": "proof_bar",
                                "content": [
                                    {
                                        "type": "ImportedProofBarSection",
                                        "props": {
                                            "id": "proof-block",
                                            "componentName": "App",
                                            "textSlots": [
                                                {
                                                    "label": "Feature 1",
                                                    "originalText": "Fresh & Light Taste",
                                                    "text": "Fresh & Light Taste",
                                                }
                                            ],
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
    assert by_path[proof_stat_path].source_value == "80%"
    assert by_path[proof_button_path].current_value == "TRY OMNI NOW"
    assert by_path[proof_button_path].source_value == "TRY OMNI NOW"
    assert by_path[faq_path].current_value == "Take 3 gummies daily."
    assert by_path[faq_path].source_value == "Take 3 gummies daily."
    assert by_path[runtime_path].current_value == "OMNI Creatine Gummy"
    assert by_path[runtime_path].source_value == "OMNI Creatine Gummy"
    assert by_path[runtime_image_path].current_value == "https://cdn.example.com/omni-cover.jpg"
    assert by_path[runtime_image_path].source_value == "https://cdn.example.com/omni-cover.jpg"
    assert by_path[proof_stat_path].max_chars is not None
    assert by_path[proof_button_path].max_chars is not None
    assert by_path[faq_path].max_chars is not None
    assert by_path[runtime_image_path].max_chars is None
    assert by_path[proof_button_path].max_chars < by_path[faq_path].max_chars


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


def test_build_site_page_copy_prompt_includes_slot_limits():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())
    prompt = build_site_page_copy_prompt(
        site=SimpleNamespace(name="Ember Gummies"),
        page=SimpleNamespace(
            name="Home",
            slug="home",
            page_type="home",
            page_role="home",
        ),
        puck_data=_build_imported_page_puck(),
        page_context=[{"id": "page-1", "slug": "home", "name": "Home"}],
        prompt="Rewrite the page.",
        messages=None,
        slots=slots,
    )

    assert '"maxChars"' in prompt
    assert '"maxWords"' in prompt
    assert '"sourceValue"' in prompt
    assert "hard copy limits" in prompt


def test_feature_stack_body_copy_limits_follow_original_source_density():
    slots = extract_site_page_copy_slots(_build_feature_stack_puck_with_verbose_current_text())

    assert len(slots) == 1
    assert slots[0].section_type == "feature_stack"
    assert slots[0].source_value == "Creatine supports cellular energy and daily stamina."
    assert slots[0].max_chars is not None
    assert slots[0].max_words is not None
    assert slots[0].max_chars < len(slots[0].current_value)
    assert slots[0].max_words < len(slots[0].current_value.split())


def test_proof_bar_feature_slots_stay_tight_for_strip_layouts():
    slots = extract_site_page_copy_slots(_build_proof_bar_feature_puck())

    assert len(slots) == 1
    slot = slots[0]
    assert slot.section_type == "proof_bar"
    assert slot.max_chars == 26
    assert slot.max_words == 5


def test_split_headline_fragments_stay_close_to_source_length():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())
    by_label = {slot.label: slot for slot in slots}

    headline_prefix = by_label["Why Choose OMNI? / UsVsThem / Headline part 1"]
    headline_suffix = by_label["Why Choose OMNI? / UsVsThem / Headline part 2"]

    assert headline_prefix.limit_note is not None
    assert "split headline fragment" in headline_prefix.limit_note.lower()
    assert headline_prefix.max_chars == 21
    assert headline_prefix.max_words == 4
    assert headline_suffix.limit_note is not None
    assert "split headline fragment" in headline_suffix.limit_note.lower()
    assert headline_suffix.max_chars == 14
    assert headline_suffix.max_words == 3


def test_feature_stack_structural_title_slot_stays_short_even_when_source_text_is_long():
    slots = extract_site_page_copy_slots(_build_feature_stack_title_overflow_puck())

    assert len(slots) == 1
    slot = slots[0]
    assert slot.label.endswith("Feature 3 title")
    assert slot.limit_note is not None
    assert "short title label" in slot.limit_note.lower()
    assert slot.max_chars is not None
    assert slot.max_words is not None
    assert slot.max_chars <= 56
    assert slot.max_words <= 8
    assert slot.max_chars < len(slot.current_value)
    assert slot.max_words < len(slot.current_value.split())


def test_hero_headline_limit_uses_slot_label_not_section_title_keywords():
    slots = extract_site_page_copy_slots(_build_hero_puck_with_body_in_section_name())
    by_label = {slot.label: slot for slot in slots}

    headline = by_label["Creatine For Body & Mind / HeroSection / Headline Part 1"]
    body = by_label["Creatine For Body & Mind / HeroSection / Body Copy"]
    guarantee = by_label["Creatine For Body & Mind / HeroSection / Guarantee Text"]

    assert headline.limit_note is not None
    assert "headline" in headline.limit_note.lower()
    assert body.limit_note is not None
    assert "paragraph density" in body.limit_note.lower()
    assert guarantee.limit_note is not None
    assert "support line" in guarantee.limit_note.lower()
    assert headline.max_chars is not None
    assert body.max_chars is not None
    assert guarantee.max_words is not None
    assert headline.max_chars < body.max_chars
    assert guarantee.max_words >= 8


def test_parse_site_page_copy_agent_response_rejects_over_limit_copy():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())
    assignments = [{"path": slot.path, "value": slot.current_value} for slot in slots]
    button_assignment = next(
        item
        for item in assignments
        if item["path"] == "/content/0/props/content/1/props/content/0/props/buttonSlots/0/text"
    )
    button_assignment["value"] = "GET THE FULL EMBER BRAIN CLARITY PROTOCOL HANDBOOK RIGHT NOW"

    with pytest.raises(SitePageCopyAgentError, match="character limit"):
        parse_site_page_copy_agent_response(
            raw_output=json.dumps(
                {
                    "assistantMessage": "Updated slots.",
                    "assignments": assignments,
                }
            ),
            base_puck_data=_build_imported_page_puck(),
            slots=slots,
        )


def test_parse_site_page_copy_agent_response_allows_minor_copy_overage_within_tolerance():
    slots = extract_site_page_copy_slots(_build_imported_page_puck())
    assignments = [{"path": slot.path, "value": slot.current_value} for slot in slots]
    button_assignment = next(
        item
        for item in assignments
        if item["path"] == "/content/0/props/content/1/props/content/0/props/buttonSlots/0/text"
    )
    button_assignment["value"] = "GET YOUR HANDBOOK NOW"

    result = parse_site_page_copy_agent_response(
        raw_output=json.dumps(
            {
                "assistantMessage": "Updated slots.",
                "assignments": assignments,
            }
        ),
        base_puck_data=_build_imported_page_puck(),
        slots=slots,
    )

    assert any(
        item["path"] == "/content/0/props/content/1/props/content/0/props/buttonSlots/0/text"
        and item["value"] == "GET YOUR HANDBOOK NOW"
        for item in result.assignments
    )


def test_validate_site_page_copy_assignment_rejects_short_ui_copy_that_only_fits_by_old_tolerance():
    slot = SitePageCopySlot(
        path="/proof/feature-1",
        kind="text",
        label="Fresh & Light Taste / App / Feature 1",
        section_display_name="Fresh & Light Taste",
        section_type="proof_bar",
        component_name="App",
        source_value="Fresh & Light Taste",
        current_value="Fresh & Light Taste",
        max_chars=26,
        max_words=5,
        limit_note="Keep this compact strip/checklist label extremely short so the original layout does not clip.",
    )

    with pytest.raises(SitePageCopyAgentError, match="character limit"):
        _validate_site_page_copy_assignment(
            slot=slot,
            value="Creatine for brain energy, not fitness",
        )


def test_validate_site_page_copy_assignment_rejects_duplicate_years_in_copyright_slots():
    slot = SitePageCopySlot(
        path="/footer/copyright",
        kind="text",
        label="Global Footer / GlobalFooter / Copyright Text",
        section_display_name="Global Footer",
        section_type="footer",
        component_name="GlobalFooter",
        source_value="Omni Creatine. All rights reserved.",
        current_value="Omni Creatine. All rights reserved.",
        max_chars=38,
        max_words=6,
        limit_note="Keep this copyright line concise. Do not repeat a year if the surrounding component already renders one.",
    )

    with pytest.raises(SitePageCopyAgentError, match="duplicated a year"):
        _validate_site_page_copy_assignment(
            slot=slot,
            value="Ember © 2026. All rights reserved.",
        )


def test_validate_site_page_copy_assignment_rejects_duplicate_copyright_marks_in_copyright_slots():
    slot = SitePageCopySlot(
        path="/footer/copyright",
        kind="text",
        label="Global Footer / GlobalFooter / Copyright Text",
        section_display_name="Global Footer",
        section_type="footer",
        component_name="GlobalFooter",
        source_value="Ember. All rights reserved.",
        current_value="Ember. All rights reserved.",
        max_chars=38,
        max_words=6,
        limit_note="Keep this copyright line concise. Do not repeat a year if the surrounding component already renders one.",
    )

    with pytest.raises(SitePageCopyAgentError, match="duplicated a copyright mark"):
        _validate_site_page_copy_assignment(
            slot=slot,
            value="Ember © All rights reserved.",
        )


def test_parse_site_page_copy_agent_response_rejects_body_copy_in_structural_title_slot():
    slots = extract_site_page_copy_slots(_build_feature_stack_title_overflow_puck())

    with pytest.raises(SitePageCopyAgentError, match="character limit"):
        parse_site_page_copy_agent_response(
            raw_output=json.dumps(
                {
                    "assistantMessage": "Updated slots.",
                    "assignments": [
                        {
                            "path": slots[0].path,
                            "value": (
                                "NSF testing confirms dosing and purity. No marketing fluff just proof that "
                                "what's on the label is actually in the bottle. Built for knowledge workers "
                                "who demand evidence, not hype."
                            ),
                        }
                    ],
                }
            ),
            base_puck_data=_build_feature_stack_title_overflow_puck(),
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
