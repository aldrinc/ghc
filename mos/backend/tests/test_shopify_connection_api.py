import base64
import io
import json
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from app.auth.dependencies import AuthContext
from app.routers import clients as clients_router
from app.db.enums import AssetSourceEnum
from app.db.models import Asset, Client, ShopifyThemeTemplateDraft, ShopifyThemeTemplateDraftVersion
from app.schemas.shopify_connection import (
    ShopifyThemeTemplateFeatureHighlights,
    ShopifyThemeTemplateGenerateImagesRequest,
)
from app.services.shopify_connection import ShopifyInstallation
from sqlalchemy import select


def _create_client(api_client, *, name: str = "Shopify Workspace") -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Retail"})
    assert response.status_code == 201
    return response.json()["id"]


def test_sanitize_theme_component_text_value_removes_unsupported_characters():
    raw_value = '  "Sleep <better>\n tonight\'s pick"  '
    assert (
        clients_router._sanitize_theme_component_text_value(raw_value)
        == "Sleep better tonight’s pick"
    )


def test_sanitize_theme_component_text_value_strips_inline_markup_tags():
    raw_value = "Boost <strong>energy</strong> and <em>focus</em> daily"
    assert (
        clients_router._sanitize_theme_component_text_value(raw_value)
        == "Boost energy and focus daily"
    )


def test_sanitize_theme_component_text_value_strips_block_html_tags():
    raw_value = (
        "<p>🌟 <strong>Our Mission</strong></p>"
        "<p>Bringing professional-grade LED light therapy to your home.</p>"
    )
    assert (
        clients_router._sanitize_theme_component_text_value(raw_value)
        == "🌟 Our Mission Bringing professional-grade LED light therapy to your home."
    )


def test_sanitize_theme_component_text_value_strips_orphan_closing_tag_fragments():
    raw_value = "Our Mission /em Bringing professional-grade LED therapy /strong to your home /p"
    assert (
        clients_router._sanitize_theme_component_text_value(raw_value)
        == "Our Mission Bringing professional-grade LED therapy to your home"
    )


def test_normalize_theme_export_text_file_content_rewrites_collection_test_links():
    normalized_content, rewritten_count = (
        clients_router._normalize_theme_export_text_file_content(
            filename="sections/custom-featured-collection.liquid",
            content=(
                '<a href="/collections/test">Shop</a>'
                '{"url":"/collections/test"}'
            ),
        )
    )
    assert rewritten_count == 2
    assert "/collections/test" not in normalized_content
    assert 'href="/"' in normalized_content
    assert '{"url":"/"}' in normalized_content


def test_normalize_theme_export_text_file_content_rewrites_risky_storefront_links():
    normalized_content, _ = clients_router._normalize_theme_export_text_file_content(
        filename="templates/index.json",
        content=json.dumps(
            {
                "product_link": "shopify://products/sample-product",
                "collection_link": "shopify://collections/featured",
                "collection_link_safe": "shopify://collections/all",
                "relative_product_link": "/products/sample-product",
                "relative_page_link": "/pages/contact",
                "relative_collection_link": "/collections/featured",
                "relative_collection_safe_link": "/collections/all",
                "external_docs": "https://help.shopify.com/manual/products/collections",
            }
        ),
    )

    assert "shopify://products/sample-product" not in normalized_content
    assert "shopify://collections/featured" not in normalized_content
    assert "shopify://collections/all" not in normalized_content
    assert "/products/sample-product" not in normalized_content
    assert "/pages/contact" not in normalized_content
    assert "/collections/featured" not in normalized_content
    assert normalized_content.count('"/"') >= 6
    assert "https://help.shopify.com/manual/products/collections" in normalized_content


def test_normalize_theme_export_text_file_content_rewrites_catalog_label_to_shop_in_header_drawer():
    normalized_content, rewritten_count = (
        clients_router._normalize_theme_export_text_file_content(
            filename="snippets/header-drawer.liquid",
            content=(
                '<ul><li><a class="drawer__menu-item" href="/collections/test">'
                "Catalog"
                "</a></li></ul>"
            ),
        )
    )

    assert rewritten_count == 1
    assert "Catalog" not in normalized_content
    assert ">Shop<" in normalized_content
    assert 'href="/"' in normalized_content


def test_normalize_theme_export_text_file_content_rewrites_catalog_label_to_shop_in_header_nav():
    normalized_content, _ = clients_router._normalize_theme_export_text_file_content(
        filename="snippets/header-nav-desktop.liquid",
        content=(
            "{%- liquid\n"
            "  echo link.title\n"
            "-%}\n"
            "<span>{{ link.title }}</span>\n"
        ),
    )

    assert "echo link.title | replace: 'Catalog', 'Shop'" in normalized_content
    assert "{{ link.title | replace: 'Catalog', 'Shop' }}" in normalized_content


def test_normalize_theme_export_text_file_content_rewrites_catalog_label_to_shop_in_header_nav_drawer():
    normalized_content, _ = clients_router._normalize_theme_export_text_file_content(
        filename="snippets/header-nav-drawer.liquid",
        content="<summary>{{- link.title | escape -}}</summary>\n",
    )

    assert "{{- link.title | replace: 'Catalog', 'Shop' | escape -}}" in normalized_content


def test_normalize_theme_export_text_file_content_removes_rich_text_footer_color_override():
    normalized_content, _ = clients_router._normalize_theme_export_text_file_content(
        filename="sections/rich-text.liquid",
        content=(
            "<style>\n"
            "  #shopify-section-{{ section.id }} {\n"
            "    --section-padding-top: {{ section.settings.padding_top }}px;\n"
            "    --section-padding-bottom: {{ section.settings.padding_bottom }}px;\n"
            "    {%- render 'section-variables', section: section -%}\n"
            "    --footer-text-color: {{ settings.footer_text }};\n"
            "    --color-foreground: {{ settings.footer_text.red }} {{ settings.footer_text.green }} {{ settings.footer_text.blue }};\n"
            "  }\n\n"
            "  #shopify-section-{{ section.id }} .rich-text {\n"
            "    color: var(--footer-text-color);\n"
            "  }\n"
            "</style>\n"
        ),
    )

    assert "{%- render 'section-variables', section: section -%}" in normalized_content
    assert "--footer-text-color" not in normalized_content
    assert "settings.footer_text.red" not in normalized_content
    assert "var(--footer-text-color)" not in normalized_content


def test_validate_required_theme_archive_files_in_export_rejects_missing_required_files():
    try:
        clients_router._validate_required_theme_archive_files_in_export(
            exported_filenames={"templates/collection.json"},
        )
        assert False, "Expected required archive file validation to reject missing files."
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "templates/index.json" in str(exc.detail)
        assert "sections/footer-group.json" in str(exc.detail)


def test_validate_template_file_format_uniqueness_in_export_rejects_json_liquid_collisions():
    try:
        clients_router._validate_template_file_format_uniqueness_in_export(
            exported_filenames={
                "templates/index.json",
                "templates/index.liquid",
                "templates/page.contact.json",
            },
        )
        assert False, "Expected template format uniqueness validation to fail on collision."
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "templates/index.json + templates/index.liquid" in str(exc.detail)


def test_theme_export_zip_write_order_prioritizes_section_dependencies():
    filenames = [
        "templates/index.json",
        "sections/footer-group.json",
        "sections/footer.liquid",
        "sections/ss-footer-4.liquid",
        "templates/collection.json",
    ]
    ordered = sorted(
        filenames,
        key=lambda filename: clients_router._theme_export_zip_write_order_key(
            filename=filename
        ),
    )
    assert ordered.index("sections/footer.liquid") < ordered.index(
        "sections/footer-group.json"
    )
    assert ordered.index("sections/ss-footer-4.liquid") < ordered.index(
        "sections/footer-group.json"
    )
    assert ordered.index("sections/ss-footer-4.liquid") < ordered.index(
        "templates/index.json"
    )
    assert ordered.index("sections/footer-group.json") < ordered.index(
        "templates/collection.json"
    )


def test_apply_local_theme_section_group_import_compatibility_rewrites_group_types():
    ordered_filenames = [
        "sections/header.liquid",
        "sections/footer.liquid",
        "sections/search-drawer.liquid",
        "sections/multicolumn-with-icons.liquid",
        "sections/ss-footer-4.liquid",
        "sections/header-group.json",
        "sections/footer-group.json",
        "sections/overlay-group.json",
    ]
    files_by_filename = {
        "sections/header.liquid": {"filename": "sections/header.liquid", "content": "header"},
        "sections/footer.liquid": {"filename": "sections/footer.liquid", "content": "footer"},
        "sections/search-drawer.liquid": {
            "filename": "sections/search-drawer.liquid",
            "content": "search drawer",
        },
        "sections/multicolumn-with-icons.liquid": {
            "filename": "sections/multicolumn-with-icons.liquid",
            "content": "multicolumn",
        },
        "sections/ss-footer-4.liquid": {
            "filename": "sections/ss-footer-4.liquid",
            "content": "ss footer",
        },
        "sections/header-group.json": {
            "filename": "sections/header-group.json",
            "content": json.dumps(
                {
                    "sections": {
                        "header": {
                            "type": "header",
                        }
                    }
                }
            ),
        },
        "sections/footer-group.json": {
            "filename": "sections/footer-group.json",
            "content": json.dumps(
                {
                    "sections": {
                        "footer": {"type": "footer"},
                        "promo": {"type": "multicolumn-with-icons"},
                        "custom": {"type": "ss-footer-4"},
                    }
                }
            ),
        },
        "sections/overlay-group.json": {
            "filename": "sections/overlay-group.json",
            "content": json.dumps(
                {
                    "sections": {
                        "drawer": {"type": "search-drawer"},
                    }
                }
            ),
        },
    }

    clients_router._apply_local_theme_section_group_import_compatibility(
        ordered_filenames=ordered_filenames,
        files_by_filename=files_by_filename,
    )

    assert "sections/a-header.liquid" in files_by_filename
    assert "sections/a-footer.liquid" in files_by_filename
    assert "sections/a-search-drawer.liquid" in files_by_filename
    assert "sections/a-multicolumn-with-icons.liquid" in files_by_filename
    assert "sections/a-ss-footer-4.liquid" in files_by_filename

    header_group = json.loads(files_by_filename["sections/header-group.json"]["content"])
    footer_group = json.loads(files_by_filename["sections/footer-group.json"]["content"])
    overlay_group = json.loads(files_by_filename["sections/overlay-group.json"]["content"])

    assert header_group["sections"]["header"]["type"] == "a-header"
    assert footer_group["sections"]["footer"]["type"] == "a-footer"
    assert footer_group["sections"]["promo"]["type"] == "a-multicolumn-with-icons"
    assert footer_group["sections"]["custom"]["type"] == "a-ss-footer-4"
    assert overlay_group["sections"]["drawer"]["type"] == "a-search-drawer"


def test_apply_theme_template_setting_values_to_local_files_coerces_richtext_markup():
    template_filename = "templates/index.json"
    files_by_filename = {
        template_filename: {
            "filename": template_filename,
            "content": json.dumps(
                {
                    "sections": {
                        "rich": {
                            "type": "rich-text",
                            "blocks": {
                                "text_block": {
                                    "type": "text",
                                    "settings": {
                                        "text": "<p>Existing text</p>",
                                    },
                                }
                            },
                        }
                    }
                }
            ),
        }
    }
    clients_router._apply_theme_template_setting_values_to_local_files(
        files_by_filename=files_by_filename,
        values_by_setting_path={
            "templates/index.json.sections.rich.blocks.text_block.settings.text": "Line one\nLine two",
        },
    )
    updated_template = json.loads(files_by_filename[template_filename]["content"])
    assert (
        updated_template["sections"]["rich"]["blocks"]["text_block"]["settings"]["text"]
        == "<p>Line one</p><p>Line two</p>"
    )


def test_merge_local_theme_export_css_replaces_all_duplicate_variable_declarations():
    merged_content = clients_router._merge_local_theme_export_css(
        existing_content=(
            ":root {\n"
            "  --font-navigation-size: var(--text-sm) !important;\n"
            "}\n"
            ":root {\n"
            "  --font-navigation-size: var(--text-sm);\n"
            "}\n"
        ),
        css_vars={"--font-navigation-size": "18px"},
        font_urls=[],
    )

    assert "--font-navigation-size: 18px !important;" in merged_content
    assert "--font-navigation-size: 18px;" in merged_content
    assert "--font-navigation-size: var(--text-sm)" not in merged_content


def test_apply_local_theme_export_default_navigation_size_sets_settings_data_value():
    settings_file_entry = {
        "filename": "config/settings_data.json",
        "content": json.dumps(
            {
                "current": {
                    "type_navigation_size": 13,
                }
            }
        ),
    }

    clients_router._apply_local_theme_export_default_navigation_size(
        settings_file_entry=settings_file_entry
    )
    settings_payload = json.loads(settings_file_entry["content"])
    assert settings_payload["current"]["type_navigation_size"] == 18


def test_apply_local_theme_rich_text_footer_color_styling_updates_section_colors_and_heading():
    files_by_filename = {
        "config/settings_data.json": {
            "filename": "config/settings_data.json",
            "content": json.dumps(
                {
                    "current": {
                        "footer_background": "#0f2618",
                        "color_image_background": "#ffffff",
                    }
                }
            ),
        },
        "templates/index.json": {
            "filename": "templates/index.json",
            "content": json.dumps(
                {
                    "sections": {
                        "rich_text_U6caVk": {
                            "type": "rich-text",
                            "settings": {
                                "color_background": "#f8f7f5",
                                "color_highlight": "rgba(15, 38, 24, 0.03)",
                            },
                            "blocks": {
                                "heading_PpFgCk": {
                                    "type": "heading",
                                    "settings": {
                                        "heading": "Natural Remedies for Every Health Goal",
                                        "highlighted_text": "none",
                                    },
                                }
                            },
                        }
                    }
                }
            ),
        },
    }

    clients_router._apply_local_theme_rich_text_footer_color_styling(
        files_by_filename=files_by_filename
    )

    template_payload = json.loads(files_by_filename["templates/index.json"]["content"])
    rich_text_section = template_payload["sections"]["rich_text_U6caVk"]
    assert rich_text_section["settings"]["color_background"] == "#0f2618"
    assert rich_text_section["settings"]["color_highlight"] == "#ffffff"
    assert (
        rich_text_section["blocks"]["heading_PpFgCk"]["settings"]["heading"]
        == "Natural Remedies for <em>Every Health Goal</em>"
    )
    assert (
        rich_text_section["blocks"]["heading_PpFgCk"]["settings"]["highlighted_text"]
        == "scribble"
    )


def test_require_local_theme_secondary_background_css_var_rejects_missing_token():
    try:
        clients_router._require_local_theme_secondary_background_css_var(
            css_vars={"--color-brand": "#123456"}
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "--color-page-bg-secondary" in str(exc.detail)
    else:
        raise AssertionError("Expected secondary background token requirement to reject missing token.")


def test_apply_local_theme_secondary_background_color_to_sections_rewrites_targets():
    files_by_filename = {
        "sections/ss-before-after-4.liquid": {
            "filename": "sections/ss-before-after-4.liquid",
            "content": (
                '<div style="background-color:{{ background_color }}; '
                "background-image: {{ background_gradient }};\">"
            ),
        },
        "sections/ss-before-after-image-4.liquid": {
            "filename": "sections/ss-before-after-image-4.liquid",
            "content": (
                '<div style="background-color:{{ background_color }}; '
                "background-image: {{ background_gradient }};\">"
            ),
        },
        "sections/ss-countdown-timer-4.liquid": {
            "filename": "sections/ss-countdown-timer-4.liquid",
            "content": (
                '<div style="background-color:{{ background_color }}; '
                'background-image: {{ background_gradient }};"></div>'
                '<path fill="{{ background_color }}"></path>'
            ),
        },
    }
    clients_router._apply_local_theme_secondary_background_color_to_sections(
        files_by_filename=files_by_filename
    )

    for filename in (
        "sections/ss-before-after-4.liquid",
        "sections/ss-before-after-image-4.liquid",
        "sections/ss-countdown-timer-4.liquid",
    ):
        content = files_by_filename[filename]["content"]
        assert "background-color: var(--color-page-bg-secondary);" in content
        assert "background-color:{{ background_color }};" not in content
        assert "background-image: none;" in content
        assert "background-image: {{ background_gradient }};" not in content

    assert (
        'fill="var(--color-page-bg-secondary)"'
        in files_by_filename["sections/ss-countdown-timer-4.liquid"]["content"]
    )
    assert (
        'fill="{{ background_color }}"'
        not in files_by_filename["sections/ss-countdown-timer-4.liquid"]["content"]
    )


def test_validate_collection_template_component_values_in_export_accepts_collection_mappings():
    image_path = (
        "templates/collection.json.sections.main-collection.blocks.promotion.settings.image"
    )
    text_path = (
        "templates/collection.json.sections.main-collection.blocks.promotion.settings.heading"
    )
    collection_template_content = json.dumps(
        {
            "sections": {
                "main-collection": {
                    "blocks": {
                        "promotion": {
                            "settings": {
                                "image": "shopify://shop_images/promo.png",
                                "heading": "<p>Glow brighter</p>",
                            }
                        }
                    }
                }
            }
        }
    )

    report = clients_router._validate_collection_template_component_values_in_export(
        exported_text_files_by_filename={
            "templates/collection.json": collection_template_content
        },
        component_image_urls={image_path: "https://assets.example.com/public/assets/promo"},
        component_text_values={text_path: "Glow brighter"},
    )

    assert report == {
        "validatedImagePaths": [image_path],
        "validatedTextPaths": [text_path],
    }


def test_validate_collection_template_component_values_in_export_requires_template_file():
    image_path = (
        "templates/collection.json.sections.main-collection.blocks.promotion.settings.image"
    )
    try:
        clients_router._validate_collection_template_component_values_in_export(
            exported_text_files_by_filename={},
            component_image_urls={image_path: "https://assets.example.com/public/assets/promo"},
            component_text_values={},
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "templates/collection.json" in str(exc.detail)
    else:
        raise AssertionError(
            "Expected collection template validation to fail when templates/collection.json is missing"
        )


def test_validate_required_collection_templates_in_export_accepts_shopify_comment_wrapped_json():
    collection_template_content = (
        "/* Shopify autogenerated comment */\n"
        "{"
        '"sections":{"main-collection-banner":{"type":"main-collection-banner"},'
        '"main-collection":{"type":"main-collection"}}'
        "}"
    )
    list_collections_template_content = (
        "/* Shopify autogenerated comment */\n"
        '{"sections":{"main":{"type":"main-list-collections"}},"order":["main"]}'
    )

    report = clients_router._validate_required_collection_templates_in_export(
        exported_text_files_by_filename={
            "templates/collection.json": collection_template_content,
            "templates/list-collections.json": list_collections_template_content,
        }
    )

    assert sorted(report["validatedTemplates"]) == [
        "templates/collection.json",
        "templates/list-collections.json",
    ]
    assert "main-collection-banner" in report["validatedCollectionSections"]
    assert "main-collection" in report["validatedCollectionSections"]


def test_validate_required_collection_templates_in_export_requires_template_files():
    try:
        clients_router._validate_required_collection_templates_in_export(
            exported_text_files_by_filename={}
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "templates/collection.json" in str(exc.detail)
        assert "templates/list-collections.json" in str(exc.detail)
    else:
        raise AssertionError(
            "Expected missing required collection template files to fail validation"
        )


def test_build_theme_sync_image_slot_text_hints_uses_adjacent_feature_copy():
    feature_image_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.image"
    )
    hints = clients_router._build_theme_sync_image_slot_text_hints(
        image_slots=[
            {"path": feature_image_path},
            {"path": "templates/index.json.sections.hero.settings.image"},
        ],
        text_slots=[
            {
                "path": (
                    "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                    "settings.title"
                ),
                "currentValue": "We deliver worldwide",
            },
            {
                "path": (
                    "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                    "settings.text"
                ),
                "currentValue": "Fast <strong>shipping</strong> for all orders",
            },
            {
                "path": "templates/index.json.sections.hero.settings.heading",
                "currentValue": "Hero heading",
            },
        ],
    )

    assert hints == {
        feature_image_path: "We deliver worldwide Fast shipping for all orders"
    }


def test_build_theme_sync_default_slot_prompt_context_by_path_enforces_feature_icon_direction():
    feature_image_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.image"
    )
    context_by_path = clients_router._build_theme_sync_default_slot_prompt_context_by_path(
        image_slots=[
            {
                "path": feature_image_path,
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "1:1",
            }
        ],
        text_slots=[
            {
                "path": (
                    "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                    "settings.title"
                ),
                "currentValue": "We deliver worldwide",
            },
            {
                "path": (
                    "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                    "settings.text"
                ),
                "currentValue": "Get your package anywhere!",
            },
        ],
    )

    feature_context = context_by_path[feature_image_path]
    assert "Creative format: icon-style feature illustration." in feature_context
    assert "Icon-style requirements:" in feature_context
    assert (
        "Feature message to represent as an icon: We deliver worldwide Get your package anywhere!."
        in feature_context
    )


def test_build_theme_sync_slot_image_prompt_applies_feature_icon_constraints():
    feature_image_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.image"
    )
    prompt = clients_router._build_theme_sync_slot_image_prompt(
        slot_role="supporting",
        slot_key="image",
        aspect_ratio="1:1",
        variant_index=1,
        slot_path=feature_image_path,
        slot_text_hint="We deliver worldwide Get your package anywhere!",
    )

    assert "Create a clean ecommerce feature icon" in prompt
    assert "Icon-style requirements:" in prompt
    assert "Background policy:" in prompt
    assert "always use a flat solid background" in prompt
    assert "--color-page-bg value provided in context" in prompt
    assert "Feature context: We deliver worldwide Get your package anywhere!." in prompt


def test_build_theme_sync_default_general_prompt_context_includes_page_background_token():
    context = clients_router._build_theme_sync_default_general_prompt_context(
        draft_data=SimpleNamespace(
            workspaceName="Workspace A",
            brandName="Brand A",
            themeName="Theme A",
            themeRole="main",
            cssVars={
                "--color-brand": "#123456",
                "--color-cta": "#abcdef",
                "--color-page-bg": "#f8f7f5",
            },
        ),
        product=SimpleNamespace(
            title="Product A",
            product_type="Supplement",
            description="Short product summary",
            primary_benefits=["Benefit 1", "Benefit 2"],
        ),
        brand_description="Brand description",
    )

    assert "Page background token (--color-page-bg): #f8f7f5." in context


def test_split_theme_text_slots_for_copy_generation_excludes_feature_highlights():
    feature_title_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.title"
    )
    non_feature_path = "templates/index.json.sections.hero.settings.heading"
    ai_slots, managed_feature_slots = clients_router._split_theme_text_slots_for_copy_generation(
        text_slots=[
            {"path": feature_title_path, "key": "title"},
            {"path": non_feature_path, "key": "heading"},
        ]
    )

    assert [slot["path"] for slot in ai_slots] == [non_feature_path]
    assert [slot["path"] for slot in managed_feature_slots] == [feature_title_path]


def test_resolve_theme_template_feature_highlights_maps_manual_and_seed_values():
    card1_title_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.title"
    )
    card1_text_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.text"
    )
    card2_title_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.title"
    )
    card2_text_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.text"
    )
    card3_title_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.title"
    )
    card3_text_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.text"
    )

    resolved_feature_highlights, component_text_values = (
        clients_router._resolve_theme_template_feature_highlights(
            feature_highlights=ShopifyThemeTemplateFeatureHighlights(
                card1={"header": "Manual Card 1 Header", "subtext": "Manual Card 1 Subtext"}
            ),
            existing_feature_highlights=ShopifyThemeTemplateFeatureHighlights(
                card2={"header": "Existing Header", "subtext": "Existing Subtext"}
            ),
            component_text_values={
                card2_title_path: "Component Card 2 Header",
                card2_text_path: "Component Card 2 Subtext",
            },
            text_slots=[
                {"path": card3_title_path, "currentValue": "Current Card 3 Header"},
                {"path": card3_text_path, "currentValue": "Current Card 3 Subtext"},
            ],
        )
    )

    assert resolved_feature_highlights is not None
    resolved_payload = resolved_feature_highlights.model_dump(mode="json", exclude_none=True)
    assert resolved_payload["card1"] == {
        "header": "Manual Card 1 Header",
        "subtext": "Manual Card 1 Subtext",
    }
    assert resolved_payload["card2"] == {
        "header": "Component Card 2 Header",
        "subtext": "Component Card 2 Subtext",
    }
    assert resolved_payload["card3"] == {
        "header": "Current Card 3 Header",
        "subtext": "Current Card 3 Subtext",
    }
    assert component_text_values[card1_title_path] == "Manual Card 1 Header"
    assert component_text_values[card1_text_path] == "Manual Card 1 Subtext"
    assert component_text_values[card2_title_path] == "Component Card 2 Header"
    assert component_text_values[card2_text_path] == "Component Card 2 Subtext"
    assert component_text_values[card3_title_path] == "Current Card 3 Header"
    assert component_text_values[card3_text_path] == "Current Card 3 Subtext"


def test_normalize_asset_public_id_handles_uuid_and_string():
    uuid_value = UUID("11111111-1111-1111-1111-111111111111")
    assert clients_router._normalize_asset_public_id(uuid_value) == "11111111-1111-1111-1111-111111111111"
    assert clients_router._normalize_asset_public_id("  abc-123  ") == "abc-123"
    assert clients_router._normalize_asset_public_id("") is None
    assert clients_router._normalize_asset_public_id(None) is None


def test_get_shopify_status_returns_service_payload(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        observed["client_id"] = client_id
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.get(f"/clients/{client_id}/shopify/status")

    assert response.status_code == 200
    assert observed["client_id"] == client_id
    assert response.json()["state"] == "ready"


def test_create_shopify_install_url_returns_url(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_build(*, client_id: str, shop_domain: str) -> dict[str, str]:
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        return {
            "installUrl": "https://shopify-public.local/auth/install?shop=example.myshopify.com&client_id=test",
        }

    monkeypatch.setattr(clients_router, "build_client_shopify_install_urls", fake_build)

    response = api_client.post(
        f"/clients/{client_id}/shopify/install-url",
        json={"shopDomain": "example.myshopify.com"},
    )

    assert response.status_code == 200
    assert observed == {"client_id": client_id, "shop_domain": "example.myshopify.com"}
    body = response.json()
    assert body["installUrl"].startswith("https://shopify-public.local/auth/install")


def test_update_shopify_installation_sets_token_and_returns_status(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_set_token(*, client_id: str, shop_domain: str, storefront_access_token: str) -> None:
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        observed["storefront_access_token"] = storefront_access_token

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "installed_missing_storefront_token",
            "message": "Shopify is installed but missing storefront access token.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "set_client_shopify_storefront_token", fake_set_token)
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.patch(
        f"/clients/{client_id}/shopify/installation",
        json={
            "shopDomain": "example.myshopify.com",
            "storefrontAccessToken": "shptka_123",
        },
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "shop_domain": "example.myshopify.com",
        "storefront_access_token": "shptka_123",
    }
    assert response.json()["state"] == "installed_missing_storefront_token"


def test_auto_provision_shopify_installation_storefront_token_returns_status(
    api_client, monkeypatch
):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_auto_provision(*, client_id: str, shop_domain: str) -> None:
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": ["example.myshopify.com"],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    monkeypatch.setattr(
        clients_router,
        "auto_provision_client_shopify_storefront_token",
        fake_auto_provision,
    )
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.post(
        f"/clients/{client_id}/shopify/installation/auto-storefront-token",
        json={"shopDomain": "example.myshopify.com"},
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "shop_domain": "example.myshopify.com",
    }
    assert response.json()["state"] == "ready"


def test_disconnect_shopify_installation_unlinks_workspace_and_returns_status(
    api_client, monkeypatch
):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_disconnect(*, client_id: str, shop_domain: str) -> None:
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "not_connected",
            "message": "Shopify is not connected for this workspace.",
            "shopDomain": None,
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "disconnect_client_shopify_store", fake_disconnect)
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.request(
        method="DELETE",
        url=f"/clients/{client_id}/shopify/installation",
        json={"shopDomain": "example.myshopify.com"},
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "shop_domain": "example.myshopify.com",
    }
    assert response.json()["state"] == "not_connected"


def test_list_shopify_products_returns_products(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, object] = {}

    def fake_list(*, client_id: str, query: str | None, limit: int, shop_domain: str | None):
        observed["client_id"] = client_id
        observed["query"] = query
        observed["limit"] = limit
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": "example.myshopify.com",
            "products": [
                {
                    "productGid": "gid://shopify/Product/123",
                    "title": "Sleep Drops",
                    "handle": "sleep-drops",
                    "status": "ACTIVE",
                }
            ],
        }

    monkeypatch.setattr(clients_router, "list_client_shopify_products", fake_list)

    response = api_client.get(
        f"/clients/{client_id}/shopify/products",
        params={"query": "sleep", "limit": 10, "shopDomain": "example.myshopify.com"},
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "query": "sleep",
        "limit": 10,
        "shop_domain": "example.myshopify.com",
    }
    payload = response.json()
    assert payload["shopDomain"] == "example.myshopify.com"
    assert payload["products"][0]["productGid"] == "gid://shopify/Product/123"


def test_set_default_shop_updates_status(api_client, monkeypatch):
    client_id = _create_client(api_client)

    def fake_installations():
        return [
            ShopifyInstallation(
                shop_domain="one.myshopify.com",
                client_id=client_id,
                has_storefront_access_token=True,
                scopes=[],
                uninstalled_at=None,
            )
        ]

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        assert client_id
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain,
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "list_shopify_installations", fake_installations)
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.put(
        f"/clients/{client_id}/shopify/default-shop",
        json={"shopDomain": "one.myshopify.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ready"
    assert body["selectedShopDomain"] == "one.myshopify.com"


def test_create_shopify_product_returns_created_payload(api_client, monkeypatch):
    client_id = _create_client(api_client)
    observed: dict[str, object] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain or "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_create(
        *,
        client_id: str,
        title: str,
        variants: list[dict],
        description: str | None,
        handle: str | None,
        vendor: str | None,
        product_type: str | None,
        tags: list[str] | None,
        status_text: str,
        shop_domain: str | None,
    ):
        observed["client_id"] = client_id
        observed["title"] = title
        observed["variants"] = variants
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/900",
            "title": "Sleep Drops",
            "handle": "sleep-drops",
            "status": "DRAFT",
            "variants": [
                {
                    "variantGid": "gid://shopify/ProductVariant/901",
                    "title": "Starter",
                    "priceCents": 4999,
                    "currency": "USD",
                }
            ],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router, "create_client_shopify_product", fake_create)

    response = api_client.post(
        f"/clients/{client_id}/shopify/products",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )

    assert response.status_code == 200
    assert observed["client_id"] == client_id
    assert observed["title"] == "Sleep Drops"
    assert observed["shop_domain"] is None
    payload = response.json()
    assert payload["productGid"] == "gid://shopify/Product/900"
    assert payload["variants"][0]["variantGid"] == "gid://shopify/ProductVariant/901"


def test_create_shopify_product_requires_ready_connection(api_client, monkeypatch):
    client_id = _create_client(api_client)

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "installed_missing_storefront_token",
            "message": "Shopify is installed but missing storefront access token.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.post(
        f"/clients/{client_id}/shopify/products",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )

    assert response.status_code == 409


def test_enqueue_shopify_theme_brand_sync_job_is_disabled(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_run_sync_job(job_id: str):
        observed["job_id"] = job_id

    monkeypatch.setattr(
        clients_router,
        "_run_client_shopify_theme_brand_sync_job",
        fake_run_sync_job,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync-async",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 409
    assert "Direct Shopify theme sync is disabled." in response.json()["detail"]


def test_enqueue_shopify_theme_template_build_job_returns_accepted(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_run_build_job(job_id: str):
        observed["job_id"] = job_id

    monkeypatch.setattr(
        clients_router,
        "_run_client_shopify_theme_template_build_job",
        fake_run_build_job,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/template/build-async",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert isinstance(payload["jobId"], str) and payload["jobId"]
    assert payload["status"] in {"queued", "running", "succeeded", "failed"}
    assert payload["statusPath"] == (
        f"/clients/{client_id}/shopify/theme/brand/template/build-jobs/{payload['jobId']}"
    )
    assert observed["job_id"] == payload["jobId"]

    status_response = api_client.get(
        f"/clients/{client_id}/shopify/theme/brand/template/build-jobs/{payload['jobId']}"
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["jobId"] == payload["jobId"]
    assert status_payload["status"] in {"queued", "running", "succeeded", "failed"}


def test_enqueue_shopify_theme_template_publish_job_is_disabled(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_run_publish_job(job_id: str):
        observed["job_id"] = job_id

    monkeypatch.setattr(
        clients_router,
        "_run_client_shopify_theme_template_publish_job",
        fake_run_publish_job,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/template/publish-async",
        json={"draftId": "draft-1"},
    )

    assert response.status_code == 409
    assert "Direct Shopify theme publish is disabled." in response.json()["detail"]


def test_update_shopify_theme_template_draft_creates_new_version(api_client, db_session, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    client = db_session.scalar(select(Client).where(Client.id == client_id))
    assert client is not None
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    image_asset_public_id = uuid4()
    text_asset_public_id = uuid4()
    db_session.add(
        Asset(
            org_id=client.org_id,
            client_id=client.id,
            source_type=AssetSourceEnum.generated,
            channel_id="meta",
            format="image",
            content={"label": "image one"},
            public_id=image_asset_public_id,
            asset_kind="image",
        )
    )
    db_session.add(
        Asset(
            org_id=client.org_id,
            client_id=client.id,
            source_type=AssetSourceEnum.generated,
            channel_id="meta",
            format="image",
            content={"label": "image two"},
            public_id=text_asset_public_id,
            asset_kind="image",
        )
    )

    draft = ShopifyThemeTemplateDraft(
        org_id=client.org_id,
        client_id=client.id,
        design_system_id=None,
        product_id=None,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/123",
        theme_name="legacy-theme-name",
        theme_role="MAIN",
        status="draft",
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(draft)
    db_session.flush()
    version = ShopifyThemeTemplateDraftVersion(
        draft_id=draft.id,
        org_id=client.org_id,
        client_id=client.id,
        version_number=1,
        source="build_job",
        payload={
            "shopDomain": "example.myshopify.com",
            "workspaceName": "Acme Workspace",
            "designSystemId": "design-system-1",
            "designSystemName": "Acme DS",
            "brandName": "Draft Snapshot Brand",
            "logoAssetPublicId": str(uuid4()),
            "logoUrl": "https://assets.example.com/public/assets/logo-1",
            "themeId": "gid://shopify/OnlineStoreTheme/123",
            "themeName": "legacy-theme-name",
            "themeRole": "MAIN",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "dataTheme": "light",
            "productId": None,
            "componentImageAssetMap": {
                "templates/index.json.sections.hero.settings.image": str(image_asset_public_id)
            },
            "componentTextValues": {
                "templates/index.json.sections.hero.settings.heading": "Old heading"
            },
            "imageSlots": [],
            "textSlots": [],
            "metadata": {},
        },
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()

    list_response = api_client.get(f"/clients/{client_id}/shopify/theme/brand/template/drafts")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["id"] == str(draft.id)
    assert list_payload[0]["latestVersion"]["versionNumber"] == 1

    update_response = api_client.put(
        f"/clients/{client_id}/shopify/theme/brand/template/drafts/{draft.id}",
        json={
            "componentImageAssetMap": {
                "templates/index.json.sections.hero.settings.image": str(text_asset_public_id)
            },
            "componentTextValues": {
                "templates/index.json.sections.hero.settings.heading": "New heading"
            },
            "featureHighlights": {
                "card1": {
                    "header": "Manual Card Header",
                    "subtext": "Manual Card Subtext",
                }
            },
            "notes": "Updated hero creative",
        },
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["id"] == str(draft.id)
    assert update_payload["latestVersion"]["versionNumber"] == 2
    assert update_payload["latestVersion"]["source"] == "manual_edit"
    assert update_payload["latestVersion"]["data"]["componentImageAssetMap"] == {
        "templates/index.json.sections.hero.settings.image": str(text_asset_public_id)
    }
    assert update_payload["latestVersion"]["data"]["componentTextValues"] == {
        "templates/index.json.sections.hero.settings.heading": "New heading",
        (
            "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV."
            "settings.title"
        ): "Manual Card Header",
        (
            "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV."
            "settings.text"
        ): "Manual Card Subtext",
    }
    feature_highlights_payload = update_payload["latestVersion"]["data"]["featureHighlights"]
    assert feature_highlights_payload["card1"] == {
        "header": "Manual Card Header",
        "subtext": "Manual Card Subtext",
    }
    assert feature_highlights_payload["card2"] is None
    assert feature_highlights_payload["card3"] is None
    assert feature_highlights_payload["card4"] is None


def test_export_shopify_theme_template_zip_returns_archive(api_client, db_session, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    client = db_session.scalar(select(Client).where(Client.id == client_id))
    assert client is not None
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    image_asset_public_id = uuid4()
    db_session.add(
        Asset(
            org_id=client.org_id,
            client_id=client.id,
            source_type=AssetSourceEnum.generated,
            channel_id="meta",
            format="image",
            content={"label": "hero image"},
            public_id=image_asset_public_id,
            asset_kind="image",
        )
    )
    draft = ShopifyThemeTemplateDraft(
        org_id=client.org_id,
        client_id=client.id,
        design_system_id=None,
        product_id=None,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/123",
        theme_name="legacy-theme-name",
        theme_role="MAIN",
        status="draft",
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(draft)
    db_session.flush()
    version = ShopifyThemeTemplateDraftVersion(
        draft_id=draft.id,
        org_id=client.org_id,
        client_id=client.id,
        version_number=4,
        source="build_job",
        payload={
            "shopDomain": "example.myshopify.com",
            "workspaceName": "Acme Workspace",
            "designSystemId": "design-system-1",
            "designSystemName": "Acme DS",
            "brandName": "Acme",
            "logoAssetPublicId": str(uuid4()),
            "logoUrl": "https://assets.example.com/public/assets/logo-1",
            "themeId": "gid://shopify/OnlineStoreTheme/123",
            "themeName": "updated-theme-name",
            "themeRole": "MAIN",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "dataTheme": "light",
            "productId": None,
            "componentImageAssetMap": {
                "templates/collection.json.sections.main-collection.blocks.promotion.settings.image": str(
                    image_asset_public_id
                )
            },
            "componentImageUrls": {
                "templates/collection.json.sections.main-collection.blocks.promotion.settings.image": "shopify://shop_images/promo-image.png"
            },
            "componentTextValues": {
                "templates/collection.json.sections.main-collection.blocks.promotion.settings.heading": "Glow brighter"
            },
            "imageSlots": [],
            "textSlots": [],
            "metadata": {},
        },
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()

    def fake_sync_compliance_for_export(
        *,
        client_id: str,
        shop_domain: str | None,
        auth,
        session,
        sync_to_shopify: bool = True,
    ):
        assert client_id
        assert shop_domain == "example.myshopify.com"
        assert auth.user_id == "test-user"
        assert session is not None
        assert sync_to_shopify is False
        return {
            "rulesetVersion": "meta_tiktok_compliance_ruleset_v1",
            "shopDomain": "example.myshopify.com",
            "pages": [
                {
                    "pageKey": "privacy_policy",
                    "pageId": "gid://shopify/Page/101",
                    "title": "Privacy Policy",
                    "handle": "privacy-policy",
                    "url": "https://example.myshopify.com/pages/privacy-policy",
                    "operation": "created",
                }
            ],
            "updatedProfileUrls": {
                "privacy_policy_url": "https://example.myshopify.com/pages/privacy-policy"
            },
            "renderedPages": [
                {
                    "pageKey": "privacy_policy",
                    "title": "Privacy Policy",
                    "handle": "privacy-policy",
                    "markdown": "# Privacy Policy\n\nGenerated copy.",
                    "url": "https://example.myshopify.com/pages/privacy-policy",
                }
            ],
        }

    def fake_resolve_latest_snapshot(
        *,
        session,
        org_id: str,
        client_id: str,
        design_system_id: str,
    ):
        assert session is not None
        assert org_id == str(client.org_id)
        assert client_id
        assert design_system_id == "design-system-1"
        return (
            "Latest Brand Name",
            "latest-logo",
            "https://assets.example.com/public/assets/latest-logo",
            {
                "--color-brand": "#654321",
                "--color-page-bg-secondary": "#f4efe7",
                "--footer-text-color": "#010203",
                "--announcement-text-color": "#fefefe",
            },
            [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "dark",
        )

    monkeypatch.setattr(
        clients_router,
        "_resolve_latest_template_publish_design_system_snapshot",
        fake_resolve_latest_snapshot,
    )
    monkeypatch.setattr(
        clients_router,
        "_sync_compliance_policy_pages_for_template_export",
        fake_sync_compliance_for_export,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/template/export-zip",
        json={"draftId": str(draft.id)},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="updated-theme-name.zip"'
    )

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    archive_write_order = archive.namelist()
    namelist = sorted(archive_write_order)
    exported_layout = archive.read("layout/theme.liquid").decode("utf-8")
    workspace_css_filename = clients_router._resolve_local_theme_workspace_css_filename(
        layout_content=exported_layout
    )
    assert workspace_css_filename in namelist
    assert "assets/theme.css" in namelist
    assert "layout/theme.liquid" in namelist
    assert "templates/index.json" in namelist
    assert "templates/collection.json" in namelist
    assert "sections/footer-group.json" in namelist
    assert "sections/a-header.liquid" in namelist
    assert "sections/a-footer.liquid" in namelist
    assert "sections/a-search-drawer.liquid" in namelist
    assert "sections/a-multicolumn-with-icons.liquid" in namelist
    assert "sections/a-ss-footer-4.liquid" in namelist
    assert "snippets/header-drawer.liquid" in namelist
    assert all(not entry.startswith("mos-template-export/") for entry in namelist)
    exported_workspace_css = archive.read(workspace_css_filename).decode("utf-8")
    exported_settings = json.loads(archive.read("config/settings_data.json").decode("utf-8"))
    assert (
        "--font-navigation-size: 18px !important;" in exported_workspace_css
        or "--font-navigation-size: 18px;" in exported_workspace_css
    )
    assert "--font-navigation-size: var(--text-sm)" not in exported_workspace_css
    assert exported_settings["current"]["type_navigation_size"] == 18
    exported_before_after_4 = archive.read("sections/ss-before-after-4.liquid").decode("utf-8")
    exported_before_after_image_4 = archive.read("sections/ss-before-after-image-4.liquid").decode(
        "utf-8"
    )
    exported_countdown_4 = archive.read("sections/ss-countdown-timer-4.liquid").decode("utf-8")
    assert "background-color: var(--color-page-bg-secondary);" in exported_before_after_4
    assert "background-color: var(--color-page-bg-secondary);" in exported_before_after_image_4
    assert "background-color: var(--color-page-bg-secondary);" in exported_countdown_4
    assert "background-image: none;" in exported_before_after_4
    assert "background-image: none;" in exported_before_after_image_4
    assert "background-image: none;" in exported_countdown_4
    assert 'fill="var(--color-page-bg-secondary)"' in exported_countdown_4
    assert archive_write_order.index("sections/footer.liquid") < archive_write_order.index(
        "sections/footer-group.json"
    )
    assert archive_write_order.index(
        "sections/ss-footer-4.liquid"
    ) < archive_write_order.index("sections/footer-group.json")
    assert archive_write_order.index(
        "sections/main-collection.liquid"
    ) < archive_write_order.index("templates/collection.json")
    assert archive_write_order.index("sections/ss-footer-4.liquid") < archive_write_order.index(
        "templates/index.json"
    )
    exported_header_drawer = archive.read("snippets/header-drawer.liquid").decode("utf-8")
    assert "/collections/test" not in exported_header_drawer
    assert "/pages/contact" not in exported_header_drawer
    exported_index_template = archive.read("templates/index.json").decode("utf-8")
    assert "/collections/test" not in exported_index_template
    assert "shopify://products/" not in exported_index_template
    exported_collection_template = json.loads(
        archive.read("templates/collection.json").decode("utf-8")
    )
    exported_footer_group_template = json.loads(
        archive.read("sections/footer-group.json").decode("utf-8")
    )
    exported_header_group_template = json.loads(
        archive.read("sections/header-group.json").decode("utf-8")
    )
    exported_overlay_group_template = json.loads(
        archive.read("sections/overlay-group.json").decode("utf-8")
    )
    assert (
        exported_collection_template["sections"]["main-collection"]["blocks"]["promotion"][
            "settings"
        ]["heading"]
        == "Glow brighter"
    )
    assert (
        exported_collection_template["sections"]["main-collection"]["blocks"]["promotion"][
            "settings"
        ]["image"]
        == "shopify://shop_images/promo-image.png"
    )
    assert (
        exported_footer_group_template["sections"]["footer"]["type"] == "a-footer"
    )
    assert (
        exported_header_group_template["sections"]["header"]["type"] == "a-header"
    )
    assert (
        exported_overlay_group_template["sections"]["search-drawer"]["type"]
        == "a-search-drawer"
    )

    db_session.expire_all()
    refreshed_draft = db_session.scalar(
        select(ShopifyThemeTemplateDraft).where(ShopifyThemeTemplateDraft.id == draft.id)
    )
    assert refreshed_draft is not None
    assert refreshed_draft.theme_name == "legacy-theme-name"
    latest_version = db_session.scalar(
        select(ShopifyThemeTemplateDraftVersion)
        .where(ShopifyThemeTemplateDraftVersion.draft_id == draft.id)
        .order_by(ShopifyThemeTemplateDraftVersion.version_number.desc())
    )
    assert latest_version is not None
    assert str(latest_version.id) == str(version.id)
    assert latest_version.payload["themeName"] == "updated-theme-name"


def test_export_shopify_theme_template_zip_uses_cached_shopify_file_url(
    api_client, db_session, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
    client = db_session.scalar(select(Client).where(Client.id == client_id))
    assert client is not None
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    image_asset_public_id = uuid4()
    db_session.add(
        Asset(
            org_id=client.org_id,
            client_id=client.id,
            source_type=AssetSourceEnum.generated,
            channel_id="meta",
            format="image",
            content={"label": "hero image"},
            public_id=image_asset_public_id,
            asset_kind="image",
            ai_metadata={
                "shopifyFileUrlsByShopDomain": {
                    "example.myshopify.com": "shopify://shop_images/cached-promo.png"
                }
            },
        )
    )
    draft = ShopifyThemeTemplateDraft(
        org_id=client.org_id,
        client_id=client.id,
        design_system_id=None,
        product_id=None,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/123",
        theme_name="cached-theme-name",
        theme_role="MAIN",
        status="draft",
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(draft)
    db_session.flush()
    version = ShopifyThemeTemplateDraftVersion(
        draft_id=draft.id,
        org_id=client.org_id,
        client_id=client.id,
        version_number=1,
        source="build_job",
        payload={
            "shopDomain": "example.myshopify.com",
            "workspaceName": "Acme Workspace",
            "designSystemId": "design-system-1",
            "designSystemName": "Acme DS",
            "brandName": "Acme",
            "logoAssetPublicId": str(uuid4()),
            "logoUrl": "https://assets.example.com/public/assets/logo-1",
            "themeId": "gid://shopify/OnlineStoreTheme/123",
            "themeName": "cached-theme-name",
            "themeRole": "MAIN",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "dataTheme": "light",
            "productId": None,
            "componentImageAssetMap": {
                "templates/collection.json.sections.main-collection.blocks.promotion.settings.image": str(
                    image_asset_public_id
                )
            },
            "componentImageUrls": {
                "templates/collection.json.sections.main-collection.blocks.promotion.settings.image": "shopify://shop_images/cached-promo.png"
            },
            "componentTextValues": {},
            "imageSlots": [],
            "textSlots": [],
            "metadata": {},
        },
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()

    def fake_sync_compliance_for_export(
        *,
        client_id: str,
        shop_domain: str | None,
        auth,
        session,
        sync_to_shopify: bool = True,
    ):
        assert client_id
        assert shop_domain == "example.myshopify.com"
        assert auth.user_id == "test-user"
        assert session is not None
        assert sync_to_shopify is False
        return {
            "rulesetVersion": "meta_tiktok_compliance_ruleset_v1",
            "shopDomain": "example.myshopify.com",
            "pages": [],
            "updatedProfileUrls": {},
            "renderedPages": [],
        }

    def fake_resolve_latest_snapshot(
        *,
        session,
        org_id: str,
        client_id: str,
        design_system_id: str,
    ):
        assert session is not None
        assert org_id == str(client.org_id)
        assert client_id
        assert design_system_id == "design-system-1"
        return (
            "Latest Brand Name",
            "latest-logo",
            "https://assets.example.com/public/assets/latest-logo",
            {
                "--color-brand": "#654321",
                "--color-page-bg-secondary": "#f4efe7",
            },
            [],
            "dark",
        )

    def fail_if_called(
        *,
        client_id: str,
        shop_domain: str,
        component_image_urls: dict[str, str],
    ):
        raise AssertionError(
            "Expected export ZIP to use cached Shopify file URL without resolver call."
        )

    monkeypatch.setattr(
        clients_router,
        "_resolve_latest_template_publish_design_system_snapshot",
        fake_resolve_latest_snapshot,
    )
    monkeypatch.setattr(
        clients_router,
        "_resolve_template_export_component_image_urls_to_shopify_files",
        fail_if_called,
    )
    monkeypatch.setattr(
        clients_router,
        "_sync_compliance_policy_pages_for_template_export",
        fake_sync_compliance_for_export,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/template/export-zip",
        json={"draftId": str(draft.id)},
    )

    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    exported_collection_template = json.loads(
        archive.read("templates/collection.json").decode("utf-8")
    )
    assert (
        exported_collection_template["sections"]["main-collection"]["blocks"]["promotion"][
            "settings"
        ]["image"]
        == "shopify://shop_images/cached-promo.png"
    )


def test_export_shopify_theme_template_zip_requires_stored_component_image_urls(
    api_client, db_session, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
    client = db_session.scalar(select(Client).where(Client.id == client_id))
    assert client is not None

    draft = ShopifyThemeTemplateDraft(
        org_id=client.org_id,
        client_id=client.id,
        design_system_id=None,
        product_id=None,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/123",
        theme_name="missing-image-url-theme",
        theme_role="MAIN",
        status="draft",
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(draft)
    db_session.flush()
    missing_slot_path = (
        "templates/collection.json.sections.main-collection.blocks.promotion.settings.image"
    )
    db_session.add(
        ShopifyThemeTemplateDraftVersion(
            draft_id=draft.id,
            org_id=client.org_id,
            client_id=client.id,
            version_number=1,
            source="build_job",
            payload={
                "shopDomain": "example.myshopify.com",
                "workspaceName": "Acme Workspace",
                "designSystemId": "design-system-1",
                "designSystemName": "Acme DS",
                "brandName": "Acme",
                "logoAssetPublicId": str(uuid4()),
                "logoUrl": "https://assets.example.com/public/assets/logo-1",
                "themeId": "gid://shopify/OnlineStoreTheme/123",
                "themeName": "missing-image-url-theme",
                "themeRole": "MAIN",
                "cssVars": {"--color-brand": "#123456"},
                "fontUrls": [],
                "dataTheme": "light",
                "productId": None,
                "componentImageAssetMap": {missing_slot_path: str(uuid4())},
                "componentImageUrls": {},
                "componentTextValues": {},
                "imageSlots": [],
                "textSlots": [],
                "metadata": {},
            },
            created_by_user_external_id="test-user",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    def fake_sync_compliance_for_export(
        *,
        client_id: str,
        shop_domain: str | None,
        auth,
        session,
        sync_to_shopify: bool = True,
    ):
        assert sync_to_shopify is False
        return {
            "rulesetVersion": "meta_tiktok_compliance_ruleset_v1",
            "shopDomain": "example.myshopify.com",
            "pages": [],
            "updatedProfileUrls": {},
            "renderedPages": [],
        }

    monkeypatch.setattr(
        clients_router,
        "_sync_compliance_policy_pages_for_template_export",
        fake_sync_compliance_for_export,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/template/export-zip",
        json={"draftId": str(draft.id)},
    )

    assert response.status_code == 409
    assert "requires stored Shopify image URLs" in response.json()["detail"]
    assert missing_slot_path in response.json()["detail"]


def test_generate_shopify_theme_template_draft_images_backfills_component_image_urls(
    api_client, db_session, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
    client = db_session.scalar(select(Client).where(Client.id == client_id))
    assert client is not None

    mapped_slot_path = (
        "templates/collection.json.sections.main-collection.blocks.promotion.settings.image"
    )
    draft = ShopifyThemeTemplateDraft(
        org_id=client.org_id,
        client_id=client.id,
        design_system_id=None,
        product_id=None,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/123",
        theme_name="backfill-image-urls-theme",
        theme_role="MAIN",
        status="draft",
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(draft)
    db_session.flush()
    db_session.add(
        ShopifyThemeTemplateDraftVersion(
            draft_id=draft.id,
            org_id=client.org_id,
            client_id=client.id,
            version_number=1,
            source="build_job",
            payload={
                "shopDomain": "example.myshopify.com",
                "workspaceName": "Acme Workspace",
                "designSystemId": "design-system-1",
                "designSystemName": "Acme DS",
                "brandName": "Acme",
                "logoAssetPublicId": str(uuid4()),
                "logoUrl": "https://assets.example.com/public/assets/logo-1",
                "themeId": "gid://shopify/OnlineStoreTheme/123",
                "themeName": "backfill-image-urls-theme",
                "themeRole": "MAIN",
                "cssVars": {"--color-brand": "#123456"},
                "fontUrls": [],
                "dataTheme": "light",
                "productId": None,
                "componentImageAssetMap": {mapped_slot_path: str(uuid4())},
                "componentImageUrls": {},
                "componentTextValues": {},
                "imageSlots": [
                    {
                        "path": mapped_slot_path,
                        "key": "image",
                        "role": "primary",
                        "recommendedAspect": "1:1",
                        "currentValue": None,
                    }
                ],
                "textSlots": [],
                "metadata": {},
            },
            created_by_user_external_id="test-user",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    observed: dict[str, object] = {}

    def fake_resolve_with_cache(
        *,
        session,
        org_id: str,
        client_id: str,
        shop_domain: str,
        component_image_asset_map: dict[str, str],
    ) -> dict[str, str]:
        observed["org_id"] = org_id
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        observed["component_image_asset_map"] = dict(component_image_asset_map)
        return {mapped_slot_path: "shopify://shop_images/backfilled-image.png"}

    monkeypatch.setattr(
        clients_router,
        "_resolve_template_export_component_image_urls_from_asset_map_with_cache",
        fake_resolve_with_cache,
    )

    response = clients_router._generate_shopify_theme_template_draft_images(
        client_id=client_id,
        payload=ShopifyThemeTemplateGenerateImagesRequest(draftId=str(draft.id)),
        auth=AuthContext(user_id="test-user", org_id=str(client.org_id)),
        session=db_session,
        generate_text=False,
    )

    assert response.generatedImageCount == 0
    assert response.generatedTextCount == 0
    assert response.version.versionNumber == 2
    assert response.version.data.componentImageUrls == {
        mapped_slot_path: "shopify://shop_images/backfilled-image.png"
    }
    assert response.version.data.metadata["componentImageUrlCount"] == 1
    assert observed == {
        "org_id": str(client.org_id),
        "client_id": client_id,
        "shop_domain": "example.myshopify.com",
        "component_image_asset_map": {
            mapped_slot_path: response.version.data.componentImageAssetMap[mapped_slot_path]
        },
    }


def test_export_shopify_theme_template_zip_writes_base64_file_payloads(
    api_client, db_session, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
    client = db_session.scalar(select(Client).where(Client.id == client_id))
    assert client is not None

    draft = ShopifyThemeTemplateDraft(
        org_id=client.org_id,
        client_id=client.id,
        design_system_id=None,
        product_id=None,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/123",
        theme_name="futrgroup2-0theme",
        theme_role="MAIN",
        status="draft",
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(draft)
    db_session.flush()
    version = ShopifyThemeTemplateDraftVersion(
        draft_id=draft.id,
        org_id=client.org_id,
        client_id=client.id,
        version_number=1,
        source="build_job",
        payload={
            "shopDomain": "example.myshopify.com",
            "workspaceName": "Acme Workspace",
            "designSystemId": "design-system-1",
            "designSystemName": "Acme DS",
            "brandName": "Draft Snapshot Brand",
            "logoAssetPublicId": str(uuid4()),
            "logoUrl": "https://assets.example.com/public/assets/logo-1",
            "themeId": "gid://shopify/OnlineStoreTheme/123",
            "themeName": "futrgroup2-0theme",
            "themeRole": "MAIN",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "dataTheme": "light",
            "productId": None,
            "componentImageAssetMap": {},
            "componentTextValues": {},
            "imageSlots": [],
            "textSlots": [],
            "metadata": {},
        },
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()

    def fake_sync_compliance_for_export(
        *,
        client_id: str,
        shop_domain: str | None,
        auth,
        session,
        sync_to_shopify: bool = True,
    ):
        assert sync_to_shopify is False
        return {
            "rulesetVersion": "meta_tiktok_compliance_ruleset_v1",
            "shopDomain": "example.myshopify.com",
            "pages": [],
            "updatedProfileUrls": {},
            "renderedPages": [],
        }

    def fake_resolve_latest_snapshot(
        *,
        session,
        org_id: str,
        client_id: str,
        design_system_id: str,
    ):
        assert session is not None
        assert org_id == str(client.org_id)
        assert client_id
        assert design_system_id == "design-system-1"
        return (
            "Latest Brand Name",
            "latest-logo",
            "https://assets.example.com/public/assets/latest-logo",
            {
                "--color-brand": "#654321",
                "--color-page-bg-secondary": "#f4efe7",
            },
            [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "dark",
        )

    monkeypatch.setattr(
        clients_router,
        "_resolve_latest_template_publish_design_system_snapshot",
        fake_resolve_latest_snapshot,
    )
    monkeypatch.setattr(
        clients_router,
        "_sync_compliance_policy_pages_for_template_export",
        fake_sync_compliance_for_export,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/template/export-zip",
        json={"draftId": str(draft.id)},
    )

    assert response.status_code == 200
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="futrgroup2-0theme.zip"'
    )
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert "assets/hero.png" not in archive.namelist()
    assert "config/settings_data.json" in archive.namelist()
    assert any(
        entry.startswith("assets/") and entry.endswith("workspace-brand.css")
        for entry in archive.namelist()
    )


def test_export_shopify_theme_template_zip_refreshes_slot_snapshot_when_changed(
    api_client, db_session, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
    client = db_session.scalar(select(Client).where(Client.id == client_id))
    assert client is not None

    draft = ShopifyThemeTemplateDraft(
        org_id=client.org_id,
        client_id=client.id,
        design_system_id=None,
        product_id=None,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/123",
        theme_name="futrgroup2-0theme",
        theme_role="MAIN",
        status="draft",
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(draft)
    db_session.flush()
    version = ShopifyThemeTemplateDraftVersion(
        draft_id=draft.id,
        org_id=client.org_id,
        client_id=client.id,
        version_number=1,
        source="build_job",
        payload={
            "shopDomain": "example.myshopify.com",
            "workspaceName": "Acme Workspace",
            "designSystemId": "design-system-1",
            "designSystemName": "Acme DS",
            "brandName": "Draft Snapshot Brand",
            "logoAssetPublicId": str(uuid4()),
            "logoUrl": "https://assets.example.com/public/assets/logo-1",
            "themeId": "gid://shopify/OnlineStoreTheme/123",
            "themeName": "futrgroup2-0theme",
            "themeRole": "MAIN",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "dataTheme": "light",
            "productId": None,
            "componentImageAssetMap": {},
            "componentTextValues": {},
            "imageSlots": [],
            "textSlots": [],
            "metadata": {},
        },
        created_by_user_external_id="test-user",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()

    def fake_sync_compliance_for_export(
        *,
        client_id: str,
        shop_domain: str | None,
        auth,
        session,
        sync_to_shopify: bool = True,
    ):
        assert sync_to_shopify is False
        return {
            "rulesetVersion": "meta_tiktok_compliance_ruleset_v1",
            "shopDomain": "example.myshopify.com",
            "pages": [],
            "updatedProfileUrls": {},
            "renderedPages": [],
        }

    def fake_resolve_latest_snapshot(
        *,
        session,
        org_id: str,
        client_id: str,
        design_system_id: str,
    ):
        return (
            "Latest Brand Name",
            "latest-logo",
            "https://assets.example.com/public/assets/latest-logo",
            {
                "--color-brand": "#654321",
                "--color-page-bg-secondary": "#f4efe7",
            },
            [],
            "dark",
        )

    monkeypatch.setattr(
        clients_router,
        "_resolve_latest_template_publish_design_system_snapshot",
        fake_resolve_latest_snapshot,
    )
    monkeypatch.setattr(
        clients_router,
        "_sync_compliance_policy_pages_for_template_export",
        fake_sync_compliance_for_export,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/template/export-zip",
        json={"draftId": str(draft.id)},
    )

    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert all(
        not filename.startswith("mos-template-export/")
        for filename in archive.namelist()
    )

    latest_version = db_session.scalar(
        select(ShopifyThemeTemplateDraftVersion)
        .where(ShopifyThemeTemplateDraftVersion.draft_id == draft.id)
        .order_by(ShopifyThemeTemplateDraftVersion.version_number.desc())
        .limit(1)
    )
    assert latest_version is not None
    assert latest_version.source == "build_job"
    payload = latest_version.payload
    assert isinstance(payload, dict)
    assert len(payload["imageSlots"]) == 0
    assert len(payload["textSlots"]) == 0


def test_sync_shopify_theme_brand_is_disabled(api_client):
    client_id = _create_client(api_client)

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={"themeName": "futrgroup2-0theme"},
    )

    assert response.status_code == 409
    assert "Direct Shopify theme sync is disabled" in response.json()["detail"]


def test_audit_shopify_theme_brand_returns_audit_payload(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        observed["status_client_id"] = client_id
        observed["selected_shop_domain"] = selected_shop_domain
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain or "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
        observed["design_system_id"] = design_system_id
        return type(
            "FakeDesignSystem",
            (),
            {
                "id": design_system_id,
                "name": "Acme Design System",
                "client_id": client_id,
                "tokens": {"placeholder": True},
            },
        )()

    def fake_validate(tokens):
        assert tokens == {"placeholder": True}
        return {
            "dataTheme": "light",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_audit_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        css_vars: dict[str, str],
        data_theme: str | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["audit_client_id"] = client_id
        observed["workspace_name"] = workspace_name
        observed["css_vars"] = css_vars
        observed["data_theme"] = data_theme
        observed["theme_id"] = theme_id
        observed["theme_name"] = theme_name
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": "example.myshopify.com",
            "themeId": "gid://shopify/OnlineStoreTheme/1",
            "themeName": "futrgroup2-0theme",
            "themeRole": "MAIN",
            "layoutFilename": "layout/theme.liquid",
            "cssFilename": "assets/acme-workspace-workspace-brand.css",
            "settingsFilename": "config/settings_data.json",
            "hasManagedMarkerBlock": True,
            "layoutIncludesManagedCssAsset": True,
            "managedCssAssetExists": True,
            "coverage": {
                "requiredSourceVars": [],
                "requiredThemeVars": [],
                "missingSourceVars": [],
                "missingThemeVars": [],
            },
            "settingsAudit": {
                "settingsFilename": "config/settings_data.json",
                "expectedPaths": [],
                "syncedPaths": [],
                "mismatchedPaths": [],
                "missingPaths": [],
                "requiredMissingPaths": [],
                "requiredMismatchedPaths": [],
            },
            "isReady": True,
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router.DesignSystemsRepository, "get", fake_design_system_get)
    monkeypatch.setattr(clients_router, "validate_design_system_tokens", fake_validate)
    monkeypatch.setattr(clients_router, "audit_client_shopify_theme_brand", fake_audit_theme_brand)

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/audit",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["shopDomain"] == "example.myshopify.com"
    assert payload["themeName"] == "futrgroup2-0theme"
    assert payload["isReady"] is True
    assert observed["workspace_name"] == "Acme Workspace"
    assert observed["data_theme"] == "light"
    assert observed["shop_domain"] == "example.myshopify.com"


def test_audit_shopify_theme_brand_requires_ready_connection(api_client, monkeypatch):
    client_id = _create_client(api_client)

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "installed_missing_storefront_token",
            "message": "Shopify is installed but missing storefront access token.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/audit",
        json={"designSystemId": "design-system-1", "themeName": "futrgroup2-0theme"},
    )

    assert response.status_code == 409
    assert "Shopify connection is not ready" in response.json()["detail"]


def test_shopify_routes_require_existing_client(api_client):
    missing_client_id = "00000000-0000-0000-0000-00000000abcd"

    status_response = api_client.get(f"/clients/{missing_client_id}/shopify/status")
    install_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/install-url",
        json={"shopDomain": "example.myshopify.com"},
    )
    patch_response = api_client.patch(
        f"/clients/{missing_client_id}/shopify/installation",
        json={"shopDomain": "example.myshopify.com", "storefrontAccessToken": "token"},
    )
    auto_provision_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/installation/auto-storefront-token",
        json={"shopDomain": "example.myshopify.com"},
    )
    disconnect_response = api_client.request(
        method="DELETE",
        url=f"/clients/{missing_client_id}/shopify/installation",
        json={"shopDomain": "example.myshopify.com"},
    )
    default_shop_response = api_client.put(
        f"/clients/{missing_client_id}/shopify/default-shop",
        json={"shopDomain": "example.myshopify.com"},
    )
    create_product_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/products",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )
    sync_theme_brand_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/theme/brand/sync",
        json={"designSystemId": "design-system-1", "themeName": "futrgroup2-0theme"},
    )
    audit_theme_brand_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/theme/brand/audit",
        json={"designSystemId": "design-system-1", "themeName": "futrgroup2-0theme"},
    )

    assert status_response.status_code == 404
    assert install_response.status_code == 404
    assert patch_response.status_code == 404
    assert auto_provision_response.status_code == 404
    assert disconnect_response.status_code == 404
    assert default_shop_response.status_code == 404
    assert create_product_response.status_code == 404
    assert sync_theme_brand_response.status_code == 404
    assert audit_theme_brand_response.status_code == 404
