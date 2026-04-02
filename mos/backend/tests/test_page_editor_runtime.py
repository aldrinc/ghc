from app.agent_platform.page_editor_runtime import (
    PageEditorRuntimeError,
    PageEditorRuntimeService,
)


def _build_imported_page_puck() -> dict:
    return {
        "root": {"props": {"title": "Imported Page"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "Imported Page",
                    "pageType": "home",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "header-section",
                                "displayName": "Header",
                                "sourceSectionId": "header",
                                "sectionType": "header",
                                "content": [
                                    {
                                        "type": "ImportedHeaderSection",
                                        "props": {
                                            "id": "header-block",
                                            "componentName": "HeaderSection",
                                            "textSlots": [
                                                {
                                                    "label": "Logo text",
                                                    "originalText": "OMNI",
                                                    "text": "The Honest Herbalist",
                                                }
                                            ],
                                            "buttonSlots": [
                                                {
                                                    "label": "Shop button",
                                                    "originalText": "SHOP NOW",
                                                    "text": "Get Your Copy",
                                                    "href": "#product-purchase-section",
                                                }
                                            ],
                                            "imageSlots": [
                                                {
                                                    "label": "Logo image",
                                                    "originalText": "OMNI",
                                                    "originalSrc": "",
                                                    "src": "",
                                                    "alt": "The Honest Herbalist",
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


def _build_imported_page_with_split_hero_puck() -> dict:
    return {
        "root": {"props": {"title": "Imported Page"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "Imported Page",
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
                                                    "label": "Headline part 1 of 2",
                                                    "originalText": "Creatine For",
                                                    "text": "Creatine For",
                                                },
                                                {
                                                    "label": "Headline part 2 of 2",
                                                    "originalText": "Body & Mind",
                                                    "text": "Body & Mind",
                                                },
                                            ],
                                            "buttonSlots": [],
                                            "imageSlots": [],
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


def test_extract_editable_bindings_includes_text_button_and_image_fields():
    bindings = PageEditorRuntimeService._extract_editable_bindings(_build_imported_page_puck())
    binding_map = {item["path"]: item for item in bindings}

    assert "/content/0/props/content/0/props/content/0/props/textSlots/0/text" in binding_map
    assert "/content/0/props/content/0/props/content/0/props/buttonSlots/0/text" in binding_map
    assert "/content/0/props/content/0/props/content/0/props/buttonSlots/0/href" in binding_map
    assert "/content/0/props/content/0/props/content/0/props/imageSlots/0/src" in binding_map
    assert "/content/0/props/content/0/props/content/0/props/imageSlots/0/alt" in binding_map
    assert binding_map["/content/0/props/content/0/props/content/0/props/buttonSlots/0/href"]["kind"] == "button_href"


def test_build_editable_section_index_groups_bindings_by_section():
    bindings = PageEditorRuntimeService._extract_editable_bindings(_build_imported_page_puck())
    section_index = PageEditorRuntimeService._build_editable_section_index(bindings)

    assert len(section_index) == 1
    entry = section_index[0]
    assert entry["sectionDisplayName"] == "Header"
    assert entry["componentName"] == "HeaderSection"
    assert entry["bindingCount"] == 5
    assert "Logo text" in entry["bindingLabels"]
    assert "Shop button Href" in entry["bindingLabels"]
    assert "image_src" in entry["kinds"]


def test_write_json_pointer_rejects_missing_path():
    payload = {"content": [{"props": {"title": "Hello"}}]}

    try:
        PageEditorRuntimeService._write_json_pointer(
            payload,
            "/content/0/props/missing/title",
            "Updated",
        )
    except PageEditorRuntimeError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("Expected PageEditorRuntimeError for a missing JSON pointer path.")


def test_extract_semantic_bindings_groups_split_hero_headline():
    bindings = PageEditorRuntimeService._extract_editable_bindings(_build_imported_page_with_split_hero_puck())
    semantic_bindings = PageEditorRuntimeService._extract_semantic_bindings(bindings)

    assert semantic_bindings == [
        {
            "groupId": "hero_headline",
            "kind": "semantic_text",
            "applyStrategy": "split_text_parts",
            "label": "Hero headline",
            "sectionDisplayName": "Hero",
            "sectionType": "hero",
            "componentName": "HeroSection",
            "memberPaths": [
                "/content/0/props/content/0/props/content/0/props/textSlots/0/text",
                "/content/0/props/content/0/props/content/0/props/textSlots/1/text",
            ],
            "memberLabels": [
                "Headline part 1 of 2",
                "Headline part 2 of 2",
            ],
            "currentValue": "Creatine For\nBody & Mind",
        }
    ]


def test_expand_semantic_edit_clears_trailing_members_for_single_line_replacement():
    expanded = PageEditorRuntimeService._expand_semantic_edit(
        binding={
            "groupId": "hero_headline",
            "applyStrategy": "split_text_parts",
            "memberPaths": [
                "/content/0/props/content/0/props/content/0/props/textSlots/0/text",
                "/content/0/props/content/0/props/content/0/props/textSlots/1/text",
            ],
        },
        value="Honest Herbalist Reference",
    )

    assert [edit.path for edit in expanded] == [
        "/content/0/props/content/0/props/content/0/props/textSlots/0/text",
        "/content/0/props/content/0/props/content/0/props/textSlots/1/text",
    ]
    assert [edit.value for edit in expanded] == [
        "Honest Herbalist Reference",
        "",
    ]
