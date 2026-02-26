from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from html import escape
import mimetypes
import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from app.config import settings

_THEME_BRAND_LAYOUT_FILENAME = "layout/theme.liquid"
_THEME_BRAND_SETTINGS_FILENAME = "config/settings_data.json"
_THEME_FOOTER_GROUP_FILENAME = "sections/footer-group.json"
_THEME_BRAND_MARKER_START = "<!-- MOS_WORKSPACE_BRAND_START -->"
_THEME_BRAND_MARKER_END = "<!-- MOS_WORKSPACE_BRAND_END -->"
_THEME_TEMPLATE_JSON_FILENAME_RE = re.compile(r"^(?:templates|sections)/.+\.json$")
_THEME_COMPONENT_SETTINGS_SYNC_THEME_NAMES = frozenset({"futrgroup2-0theme"})
_THEME_LOGO_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
_DEFAULT_THEME_VAR_SCOPE_SELECTORS: tuple[str, ...] = (":root",)
_THEME_VAR_SCOPE_SELECTORS_BY_NAME: dict[str, tuple[str, ...]] = {
    "futrgroup2-0theme": (
        ":root",
        "html",
        "body",
        ".color-scheme",
        ".gradient",
        "footer",
        "#shopify-section-footer",
        '[role="contentinfo"]',
        ".footer",
        "[data-color-scheme]",
        '[id*="footer"]',
        '[class*="color-scheme"]',
        '[class*="scheme-"]',
        '[class*="color-"]',
        '[class*="footer"]',
    ),
}
_THEME_COMPAT_ALIASES_BY_NAME: dict[str, dict[str, tuple[str, ...]]] = {
    "futrgroup2-0theme": {
        "--color-page-bg": (
            "--color-base-background",
            "--color-background",
        ),
        "--color-bg": (
            "--color-background-2",
            "--color-base-highlight",
            "--color-drawer-background",
        ),
        "--color-text": (
            "--color-base-text",
            "--color-foreground",
            "--color-drawer-text",
            "--color-info-text",
            "--color-success-text",
            "--color-error-text",
        ),
        "--color-muted": (
            "--color-placeholder",
            "--color-shadow",
        ),
        "--color-border": (
            "--color-button-border",
            "--color-border-light",
            "--color-border-dark",
        ),
        "--color-brand": (
            "--color-highlight",
            "--color-price",
            "--color-rating",
            "--product-in-stock-color",
            "--product-low-stock-color",
            "--color-red-200",
            "--color-red-300",
        ),
        "--color-cta": (
            "--color-base-button",
            "--color-base-button-gradient",
            "--color-button-background",
            "--color-button-gradient",
            "--color-drawer-button-background",
            "--color-drawer-button-gradient",
            "--color-sale-price",
            "--color-sale-tag",
        ),
        "--color-cta-text": (
            "--color-base-button-text",
            "--color-button-text",
            "--color-drawer-button-text",
            "--color-sale-tag-text",
        ),
        "--color-soft": (
            "--color-drawer-overlay",
            "--color-info-background",
            "--color-success-background",
            "--color-error-background",
        ),
        "--focus-outline-color": (
            "--color-keyboard-focus",
            "--focus-outline-color-soft",
        ),
        "--font-sans": (
            "--font-body-family",
            "--font-navigation-family",
            "--font-button-family",
            "--font-product-family",
        ),
        "--font-heading": ("--font-heading-family",),
        "--line": ("--font-body-line-height",),
        "--heading-weight": ("--font-heading-weight",),
        "--heading-line": ("--font-heading-line-height",),
        "--hero-title-letter-spacing": ("--font-heading-letter-spacing",),
        "--cta-font-size-md": ("--font-button-size",),
        "--text-sm": ("--font-navigation-size",),
        "--text-base": ("--font-product-size",),
        "--radius-sm": (
            "--border-radius-small",
            "--inputs-radius",
            "--rounded-input",
        ),
        "--radius-md": (
            "--border-radius-medium",
            "--buttons-radius",
            "--card-radius",
            "--rounded-button",
            "--rounded-block",
        ),
        "--radius-lg": (
            "--border-radius",
            "--rounded-card",
            "--wall-card-radius",
        ),
        "--container-max": (
            "--page-width",
            "--page-container",
        ),
        "--container-pad": (
            "--page-padding",
            "--gap-padding",
        ),
        "--section-pad-y": ("--footer-pad-y",),
    }
}
_THEME_REQUIRED_SOURCE_VARS_BY_NAME: dict[str, tuple[str, ...]] = {
    "futrgroup2-0theme": (
        "--color-page-bg",
        "--color-bg",
        "--color-text",
        "--color-muted",
        "--color-brand",
        "--color-cta",
        "--color-cta-text",
        "--color-border",
        "--color-soft",
        "--focus-outline-color",
        "--font-sans",
        "--font-heading",
        "--line",
        "--heading-line",
        "--hero-title-letter-spacing",
        "--text-sm",
        "--text-base",
        "--cta-font-size-md",
        "--radius-md",
        "--container-max",
        "--container-pad",
        "--section-pad-y",
        "--footer-bg",
    ),
}
_THEME_REQUIRED_THEME_VARS_BY_NAME: dict[str, tuple[str, ...]] = {
    "futrgroup2-0theme": (
        "--color-base-background",
        "--color-background",
        "--color-base-text",
        "--color-base-button",
        "--color-base-button-text",
        "--color-button-border",
        "--color-keyboard-focus",
        "--font-body-family",
        "--font-heading-family",
        "--font-body-line-height",
        "--font-heading-line-height",
        "--font-heading-letter-spacing",
        "--font-navigation-size",
        "--font-button-size",
        "--font-product-size",
        "--border-radius-medium",
        "--page-width",
        "--page-padding",
        "--footer-pad-y",
        "--footer-bg",
    ),
}
_THEME_SETTINGS_VALUE_PATHS_BY_NAME: dict[str, dict[str, str]] = {
    "futrgroup2-0theme": {
        "current.color_background": "--color-page-bg",
        "current.color_foreground": "--color-text",
        "current.color_button": "--color-cta",
        "current.color_button_text": "--color-cta-text",
        "current.color_link": "--color-brand",
        "current.color_accent": "--color-brand",
        "current.footer_background": "--footer-bg",
        "current.footer_text": "--color-text",
        "current.color_schemes[*].settings.background": "--color-page-bg",
        "current.color_schemes[*].settings.text": "--color-text",
        "current.color_schemes[*].settings.button": "--color-cta",
        "current.color_schemes[*].settings.button_label": "--color-cta-text",
        "current.color_schemes[*].settings.secondary_button": "--color-bg",
        "current.color_schemes[*].settings.secondary_button_label": "--color-text",
        "current.color_schemes[*].settings.highlight": "--color-soft",
        "current.color_schemes[*].settings.keyboard_focus": "--focus-outline-color",
        "current.color_schemes[*].settings.shadow": "--color-muted",
        "current.color_schemes[*].settings.image_background": "--color-bg",
    }
}
_THEME_REQUIRED_SETTINGS_PATHS_BY_NAME: dict[str, tuple[str, ...]] = {
    "futrgroup2-0theme": (
        "current.color_background",
        "current.color_foreground",
        "current.color_button",
        "current.color_button_text",
        "current.color_link",
        "current.color_accent",
        "current.footer_background",
        "current.footer_text",
        "current.color_schemes[*].settings.background",
        "current.color_schemes[*].settings.text",
        "current.color_schemes[*].settings.button",
        "current.color_schemes[*].settings.button_label",
        "current.color_schemes[*].settings.secondary_button",
        "current.color_schemes[*].settings.secondary_button_label",
        "current.color_schemes[*].settings.highlight",
        "current.color_schemes[*].settings.keyboard_focus",
        "current.color_schemes[*].settings.shadow",
        "current.color_schemes[*].settings.image_background",
    ),
}
_THEME_COMPONENT_STYLE_OVERRIDES_BY_NAME: dict[
    str, tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
] = {
    "futrgroup2-0theme": (
        (
            "body",
            (
                ("background-color", "var(--color-page-bg)"),
                ("color", "var(--color-text)"),
            ),
        ),
        (
            'a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"])',
            (("color", "var(--color-brand)"),),
        ),
        (
            'button, .button, .btn, input[type="button"], input[type="submit"], input[type="reset"], [role="button"]',
            (
                ("background-color", "var(--color-cta)"),
                ("color", "var(--color-cta-text)"),
                ("border-color", "var(--color-border)"),
            ),
        ),
        (
            "input, textarea, select",
            (
                ("background-color", "var(--color-bg)"),
                ("color", "var(--color-text)"),
                ("border-color", "var(--color-border)"),
            ),
        ),
        (
            'footer, #shopify-section-footer, [role="contentinfo"], .footer, [id*="footer"], [class*="footer"]',
            (
                ("background-color", "var(--footer-bg)"),
                ("color", "var(--color-text)"),
                ("border-color", "var(--color-border)"),
            ),
        ),
    ),
}
_THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME: dict[str, dict[str, str]] = {
    "futrgroup2-0theme": {
        "background": "--color-page-bg",
        "foreground": "--color-text",
        "text": "--color-text",
        "button": "--color-cta",
        "button_text": "--color-cta-text",
        "button_label": "--color-cta-text",
        "secondary_button": "--color-bg",
        "secondary_button_label": "--color-text",
        "link": "--color-brand",
        "accent": "--color-brand",
        "highlight": "--color-soft",
        "keyboard_focus": "--focus-outline-color",
        "shadow": "--color-muted",
        "image_background": "--color-bg",
        "footer_background": "--footer-bg",
        "footer_text": "--color-text",
        "copy": "--color-text",
        "input": "--color-text",
        "input_placeholder": "--color-muted",
        "submit": "--color-cta-text",
        "submit_hover": "--color-cta-text",
        "border": "--color-border",
        "price": "--color-brand",
        "sale_price": "--color-cta",
        "sale_tag": "--color-cta",
        "drawer_overlay": "--color-soft",
        "checkout_error": "--color-text",
    }
}
_THEME_SETTINGS_TYPOGRAPHY_SOURCE_VARS_BY_NAME: dict[str, dict[str, str]] = {
    "futrgroup2-0theme": {
        "heading_font": "--font-heading",
        "body_font": "--font-sans",
        "navigation_font": "--font-sans",
        "button_font": "--font-sans",
        "product_font": "--font-sans",
        "heading_line_height": "--heading-line",
        "body_line_height": "--line",
        "heading_letter_spacing": "--hero-title-letter-spacing",
        "body_letter_spacing": "--hero-title-letter-spacing",
        "body_base_size": "--text-base",
        "navigation_base_size": "--text-sm",
        "button_base_size": "--cta-font-size-md",
        "product_base_size": "--text-base",
    }
}
_THEME_SETTINGS_COLOR_KEY_MARKERS = frozenset(
    {
        "background",
        "foreground",
        "text",
        "button",
        "label",
        "link",
        "accent",
        "highlight",
        "focus",
        "shadow",
        "image",
        "border",
        "color",
    }
)
_THEME_SETTINGS_TYPOGRAPHY_KEY_SKIP_MARKERS = frozenset(
    {
        "capitalize",
        "capitalise",
        "uppercase",
        "lowercase",
    }
)
_THEME_SETTINGS_TYPOGRAPHY_CONTEXT_MARKERS = frozenset(
    {
        "header",
        "heading",
        "body",
        "nav",
        "navigation",
        "button",
        "buttons",
        "product",
        "grid",
    }
)
_THEME_SETTINGS_TYPOGRAPHY_PROPERTY_MARKERS = frozenset(
    {
        "font",
        "line",
        "height",
        "letter",
        "spacing",
        "size",
        "weight",
    }
)
_THEME_SETTINGS_SEMANTIC_KEY_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
_THEME_SETTINGS_SEMANTIC_KEY_COLLAPSE_RE = re.compile(r"_+")
_THEME_SETTINGS_HEX_COLOR_RE = re.compile(
    r"^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$", re.IGNORECASE
)
_THEME_SETTINGS_CSS_COLOR_FUNCTION_RE = re.compile(
    r"^(?:rgb|rgba|hsl|hsla)\s*\(", re.IGNORECASE
)
_THEME_SETTINGS_CSS_GRADIENT_FUNCTION_RE = re.compile(
    r"^(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(",
    re.IGNORECASE,
)
_THEME_SETTINGS_CSS_VAR_RE = re.compile(
    r"^var\(\s*--[A-Za-z0-9_-]+(?:\s*,\s*[^)]+)?\s*\)$"
)
_THEME_SETTINGS_SIMPLE_NUMBER_RE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*(px|em|rem|%)?\s*$", re.IGNORECASE
)
_THEME_SETTINGS_FONT_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_]*_(?:n|i)\d{1,3}$")
_THEME_SETTINGS_FONT_HANDLE_SUFFIX_RE = re.compile(r"_(?:n|i)\d{1,3}$")
_THEME_SETTINGS_FONT_HANDLE_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
_THEME_SETTINGS_FONT_FAMILY_ALIAS_RE = re.compile(r"[\s_-]+")
_THEME_SETTINGS_COLOR_VALUE_KEYWORDS = frozenset(
    {"transparent", "currentcolor", "inherit", "initial", "unset"}
)
_THEME_SETTINGS_GENERIC_FONT_FAMILIES = frozenset(
    {
        "serif",
        "sans-serif",
        "monospace",
        "cursive",
        "fantasy",
        "system-ui",
        "ui-serif",
        "ui-sans-serif",
        "ui-monospace",
        "ui-rounded",
    }
)
_THEME_SETTINGS_FONT_FAMILY_HANDLE_ALIASES = {
    "cormorant garamond": "cormorant",
}
_THEME_COMPONENT_IMAGE_KEY_MARKERS = frozenset(
    {
        "image",
        "img",
        "photo",
        "picture",
        "media",
        "banner",
        "hero",
    }
)
_THEME_COMPONENT_IMAGE_KEY_SKIP_MARKERS = frozenset(
    {
        "color",
        "colour",
        "gradient",
        "opacity",
        "overlay",
        "position",
        "focal",
        "point",
        "aspect",
        "ratio",
        "fit",
        "size",
        "width",
        "height",
        "radius",
        "padding",
        "margin",
        "text",
        "caption",
        "heading",
        "title",
        "alt",
        "video",
        "youtube",
        "vimeo",
        "mp4",
        "poster",
        "parallax",
        "icon",
        "logo",
    }
)
_THEME_COMPONENT_IMAGE_FILENAME_RE = re.compile(
    r"\.(?:png|jpe?g|webp|gif|avif|svg)(?:[?#].*)?$", re.IGNORECASE
)
_THEME_COMPONENT_TEXT_KEY_MARKERS = frozenset(
    {
        "title",
        "heading",
        "headline",
        "subheading",
        "subtitle",
        "description",
        "copy",
        "content",
        "text",
        "body",
        "caption",
        "message",
        "label",
        "button",
        "cta",
        "benefit",
        "feature",
    }
)
_THEME_COMPONENT_TEXT_KEY_SKIP_MARKERS = frozenset(
    {
        "id",
        "type",
        "style",
        "size",
        "width",
        "height",
        "spacing",
        "margin",
        "padding",
        "align",
        "alignment",
        "position",
        "layout",
        "font",
        "family",
        "weight",
        "line",
        "letter",
        "color",
        "colour",
        "gradient",
        "opacity",
        "icon",
        "image",
        "video",
        "url",
        "link",
        "href",
        "handle",
        "schema",
        "variant",
        "product",
        "collection",
        "currency",
        "price",
        "compare",
        "input",
        "placeholder",
        "copyright",
        "social",
    }
)
_THEME_COMPONENT_TEXT_VALUE_SKIP_RE = re.compile(
    r"^(?:https?://|shopify://|#[0-9a-f]{3,8}|var\(|rgba?\(|hsla?\(|\d+(?:\.\d+)?(?:px|rem|em|%)?)",
    re.IGNORECASE,
)
_THEME_COMPONENT_RICHTEXT_TOP_LEVEL_TAG_RE = re.compile(
    r"^\s*<(?:p|ul|ol|h[1-6])(?:\s[^>]*)?>",
    re.IGNORECASE,
)
_THEME_TEMPLATE_SLOT_MANIFEST_BY_NAME: dict[
    str, dict[str, tuple[dict[str, Any], ...]]
] = {
    "futrgroup2-0theme": {
        "imageSlots": (
            {
                "path": "templates/index.json.sections.collage_EiUYGW.blocks.image_CDPHGa.settings.image",
                "key": "image",
                "role": "gallery",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.collage_EiUYGW.blocks.image_PijDXy.settings.image",
                "key": "image",
                "role": "gallery",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.collage_EiUYGW.blocks.image_VfHpJg.settings.image",
                "key": "image",
                "role": "gallery",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.collage_EiUYGW.blocks.image_g4F98H.settings.image",
                "key": "image",
                "role": "gallery",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.image_with_text_M6Cfj7.settings.image",
                "key": "image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.image_with_text_aQPm77.settings.image",
                "key": "image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.image_with_text_overlay_7fYM3f.settings.image",
                "key": "image",
                "role": "hero",
                "recommendedAspect": "landscape",
            },
            {
                "path": "templates/index.json.sections.image_with_text_overlay_7fYM3f.settings.image_mobile",
                "key": "image_mobile",
                "role": "hero",
                "recommendedAspect": "landscape",
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_HwqgmG.settings.after_image",
                "key": "after_image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_HwqgmG.settings.before_image",
                "key": "before_image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_U4jGRN.settings.after_image",
                "key": "after_image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_U4jGRN.settings.before_image",
                "key": "before_image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_dEC66U.settings.after_image",
                "key": "after_image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_dEC66U.settings.before_image",
                "key": "before_image",
                "role": "gallery",
                "recommendedAspect": "portrait",
            },
            {
                "path": "templates/index.json.sections.ss_countdown_timer_4_TxGT4a.settings.image",
                "key": "image",
                "role": "hero",
                "recommendedAspect": "landscape",
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_73JHNR.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_CieJRi.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_DTL7F7.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_EA4mWi.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_LUTUBp.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_MkDhxG.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_bCk3JY.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_dnta3i.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.image_mq6JiQ.settings.image",
                "key": "image",
                "role": "supporting",
                "recommendedAspect": "square",
            },
        ),
        "textSlots": (
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.blocks.tab_AaWBPg.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 220,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.blocks.tab_AaWBPg.settings.title",
                "key": "title",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.blocks.tab_MTkiMM.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 220,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.blocks.tab_MTkiMM.settings.title",
                "key": "title",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.blocks.tab_tcYLPr.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 220,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.blocks.tab_tcYLPr.settings.title",
                "key": "title",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.first_menu_title",
                "key": "first_menu_title",
                "role": "headline",
                "maxLength": 80,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.input_placeholder",
                "key": "input_placeholder",
                "role": "supporting",
                "maxLength": 80,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.newsletter",
                "key": "newsletter",
                "role": "body",
                "maxLength": 220,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.second_menu_title",
                "key": "second_menu_title",
                "role": "headline",
                "maxLength": 80,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.second_text",
                "key": "second_text",
                "role": "body",
                "maxLength": 480,
            },
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.submit",
                "key": "submit",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "sections/header-group.json.sections.announcement-bar.blocks.announcement-1.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 90,
            },
            {
                "path": "sections/header-group.json.sections.announcement-bar.blocks.announcement-2.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 90,
            },
            {
                "path": "templates/index.json.sections.blog_posts_BRnRG9.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.collage_EiUYGW.settings.description",
                "key": "description",
                "role": "body",
                "maxLength": 480,
            },
            {
                "path": "templates/index.json.sections.collage_EiUYGW.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.image_with_text_M6Cfj7.blocks.button_paXetD.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/index.json.sections.image_with_text_M6Cfj7.blocks.heading_Wn7Ret.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.image_with_text_M6Cfj7.blocks.heading_aYG4iV.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.image_with_text_M6Cfj7.blocks.text_camxJq.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 320,
            },
            {
                "path": "templates/index.json.sections.image_with_text_aQPm77.blocks.button_AW4qy3.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/index.json.sections.image_with_text_aQPm77.blocks.heading_FfzHf9.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.image_with_text_aQPm77.blocks.heading_zAPVtx.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.image_with_text_aQPm77.blocks.text_yXMfzq.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 320,
            },
            {
                "path": "templates/index.json.sections.image_with_text_overlay_7fYM3f.blocks.button_gTwRDa.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/index.json.sections.image_with_text_overlay_7fYM3f.blocks.heading_tPmiRD.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.image_with_text_overlay_7fYM3f.blocks.text_3MeVHE.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 320,
            },
            {
                "path": "templates/index.json.sections.rich_text_U6caVk.blocks.heading_PpFgCk.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_HwqgmG.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_HwqgmG.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_HwqgmG.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 420,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_U4jGRN.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_U4jGRN.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_U4jGRN.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 420,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_dEC66U.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_dEC66U.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.ss_before_after_image_4_bAFP6h.blocks.slide_dEC66U.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 420,
            },
            {
                "path": "templates/index.json.sections.ss_countdown_timer_4_TxGT4a.blocks.button_bGGJbk.settings.button",
                "key": "button",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/index.json.sections.ss_countdown_timer_4_TxGT4a.blocks.heading_Ry3fND.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.ss_countdown_timer_4_TxGT4a.blocks.text_KQyqqd.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 320,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 140,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.title",
                "key": "title",
                "role": "headline",
                "maxLength": 90,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 140,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp.settings.title",
                "key": "title",
                "role": "headline",
                "maxLength": 90,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 140,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.title",
                "key": "title",
                "role": "headline",
                "maxLength": 90,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 140,
            },
            {
                "path": "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.title",
                "key": "title",
                "role": "headline",
                "maxLength": 90,
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.testimonial_Epk63H.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 48,
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.testimonial_FEnikR.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 48,
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.testimonial_MHaaUN.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 48,
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.blocks.testimonial_iEhB3e.settings.text",
                "key": "text",
                "role": "supporting",
                "maxLength": 48,
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/index.json.sections.ss_testimonial_6_mbn7JR.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 320,
            },
        ),
    }
}
_THEME_SETTINGS_SEMANTIC_TOKEN_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("secondary", "button", "label"), "secondary_button_label"),
    (("secondary", "button"), "secondary_button"),
    (("button", "background"), "button"),
    (("button", "bg"), "button"),
    (("button", "gradient"), "button"),
    (("button", "border"), "border"),
    (("button", "color"), "button_text"),
    (("button", "label"), "button_label"),
    (("button", "text"), "button_text"),
    (("keyboard", "focus"), "keyboard_focus"),
    (("overlay",), "drawer_overlay"),
    (("toggles", "bg"), "background"),
    (("toggle", "bg"), "background"),
    (("arrow", "bg"), "background"),
    (("item", "bg"), "background"),
    (("card", "bg"), "background"),
    (("body", "bg"), "background"),
    (("image", "bg"), "background"),
    (("line",), "border"),
    (("icon",), "accent"),
    (("stars",), "accent"),
    (("pagination",), "accent"),
    (("dots",), "accent"),
    (("dot",), "accent"),
    (("circle",), "accent"),
    (("arrow",), "accent"),
    (("title",), "text"),
    (("heading",), "text"),
    (("question",), "text"),
    (("answer",), "text"),
    (("date",), "text"),
    (("number",), "text"),
    (("rating",), "text"),
    (("item",), "text"),
    (("image", "background"), "image_background"),
    (("footer", "background"), "footer_background"),
    (("footer", "text"), "footer_text"),
    (("background",), "background"),
    (("foreground",), "foreground"),
    (("highlight",), "highlight"),
    (("shadow",), "shadow"),
    (("accent",), "accent"),
    (("link",), "link"),
    (("border",), "border"),
    (("text",), "text"),
    (("button",), "button"),
)
_SETTINGS_PATH_SEGMENT_RE = re.compile(r"^([A-Za-z0-9_-]+)(?:\[(\*|\d+)\])?$")


def _canonicalize_theme_profile_lookup_key(raw_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", raw_name.strip().lower())


_THEME_PROFILE_NAME_ALIASES_BY_KEY: dict[str, str] = {
    "futr group 2.0 theme": "futrgroup2-0theme",
}


def _build_theme_profile_lookup_by_canonical_name() -> dict[str, str]:
    lookup: dict[str, str] = {}
    profile_names = (
        list(_THEME_VAR_SCOPE_SELECTORS_BY_NAME.keys())
        + list(_THEME_COMPAT_ALIASES_BY_NAME.keys())
        + list(_THEME_REQUIRED_SOURCE_VARS_BY_NAME.keys())
        + list(_THEME_REQUIRED_THEME_VARS_BY_NAME.keys())
        + list(_THEME_SETTINGS_VALUE_PATHS_BY_NAME.keys())
        + list(_THEME_REQUIRED_SETTINGS_PATHS_BY_NAME.keys())
        + list(_THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME.keys())
        + list(_THEME_SETTINGS_TYPOGRAPHY_SOURCE_VARS_BY_NAME.keys())
    )
    for profile_name in profile_names:
        lookup[_canonicalize_theme_profile_lookup_key(profile_name)] = profile_name
    for alias_name, profile_name in _THEME_PROFILE_NAME_ALIASES_BY_KEY.items():
        lookup[_canonicalize_theme_profile_lookup_key(alias_name)] = profile_name
    return lookup


_THEME_PROFILE_BY_CANONICAL_NAME = _build_theme_profile_lookup_by_canonical_name()
_SUPPORTED_THEME_PROFILE_NAMES = tuple(
    sorted(set(_THEME_PROFILE_BY_CANONICAL_NAME.values()))
)


@dataclass(frozen=True)
class ThemeBrandProfile:
    theme_name: str
    var_scope_selectors: tuple[str, ...]
    compat_aliases: dict[str, tuple[str, ...]]
    required_source_vars: tuple[str, ...]
    required_theme_vars: tuple[str, ...]
    settings_value_paths: dict[str, str]
    required_settings_paths: tuple[str, ...]


class ShopifyApiError(RuntimeError):
    def __init__(self, *, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class ShopifyApiClient:
    def __init__(self) -> None:
        self._timeout = settings.SHOPIFY_REQUEST_TIMEOUT_SECONDS

    async def exchange_code_for_access_token(
        self, *, shop_domain: str, code: str
    ) -> tuple[str, str]:
        url = f"https://{shop_domain}/admin/oauth/access_token"
        payload = {
            "client_id": settings.SHOPIFY_APP_API_KEY,
            "client_secret": settings.SHOPIFY_APP_API_SECRET,
            "code": code,
        }
        response = await self._post_json(url=url, payload=payload)
        access_token = response.get("access_token")
        scopes = response.get("scope")
        if not isinstance(access_token, str) or not access_token:
            raise ShopifyApiError(
                message="OAuth token exchange response is missing access_token"
            )
        if not isinstance(scopes, str):
            raise ShopifyApiError(
                message="OAuth token exchange response is missing scope"
            )
        return access_token, scopes

    async def register_webhook(
        self,
        *,
        shop_domain: str,
        access_token: str,
        topic: str,
        callback_url: str,
    ) -> str:
        query = """
        mutation webhookSubscriptionCreate(
            $topic: WebhookSubscriptionTopic!
            $webhookSubscription: WebhookSubscriptionInput!
        ) {
            webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
                webhookSubscription {
                    id
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": query,
            "variables": {
                "topic": topic,
                "webhookSubscription": {
                    "callbackUrl": callback_url,
                    "format": "JSON",
                },
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        create_data = response.get("webhookSubscriptionCreate") or {}
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            if self._has_duplicate_webhook_address_error(user_errors):
                existing_id = await self._find_existing_http_webhook_id(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    topic=topic,
                    callback_url=callback_url,
                )
                if existing_id:
                    return existing_id
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(
                message=f"Webhook registration failed for {topic}: {messages}"
            )
        webhook = create_data.get("webhookSubscription") or {}
        webhook_id = webhook.get("id")
        if not isinstance(webhook_id, str) or not webhook_id:
            raise ShopifyApiError(
                message=f"Webhook registration for {topic} returned no id"
            )
        return webhook_id

    @staticmethod
    def _has_duplicate_webhook_address_error(user_errors: list[dict[str, Any]]) -> bool:
        for error in user_errors:
            message = error.get("message")
            if isinstance(message, str) and "already been taken" in message.lower():
                return True
        return False

    async def _find_existing_http_webhook_id(
        self,
        *,
        shop_domain: str,
        access_token: str,
        topic: str,
        callback_url: str,
    ) -> str | None:
        query = """
        query webhookSubscriptionsByTopic($topics: [WebhookSubscriptionTopic!]) {
            webhookSubscriptions(first: 50, topics: $topics) {
                edges {
                    node {
                        id
                        endpoint {
                            __typename
                            ... on WebhookHttpEndpoint {
                                callbackUrl
                            }
                        }
                    }
                }
            }
        }
        """
        payload = {"query": query, "variables": {"topics": [topic]}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        target_url = callback_url.rstrip("/")
        subscriptions = (response.get("webhookSubscriptions") or {}).get("edges") or []
        for edge in subscriptions:
            node = edge.get("node") or {}
            endpoint = node.get("endpoint") or {}
            if endpoint.get("__typename") != "WebhookHttpEndpoint":
                continue
            endpoint_callback = endpoint.get("callbackUrl")
            if (
                isinstance(endpoint_callback, str)
                and endpoint_callback.rstrip("/") == target_url
            ):
                webhook_id = node.get("id")
                if isinstance(webhook_id, str) and webhook_id:
                    return webhook_id
        return None

    async def create_cart(
        self,
        *,
        shop_domain: str,
        storefront_access_token: str,
        cart_input: dict[str, Any],
    ) -> tuple[str, str]:
        query = """
        mutation cartCreate($input: CartInput!) {
            cartCreate(input: $input) {
                cart {
                    id
                    checkoutUrl
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {"query": query, "variables": {"input": cart_input}}
        response = await self._storefront_graphql(
            shop_domain=shop_domain,
            storefront_access_token=storefront_access_token,
            payload=payload,
        )
        create_data = response.get("cartCreate") or {}
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(
                message=f"cartCreate failed: {messages}", status_code=409
            )

        cart = create_data.get("cart") or {}
        cart_id = cart.get("id")
        checkout_url = cart.get("checkoutUrl")
        if not isinstance(cart_id, str) or not cart_id:
            raise ShopifyApiError(message="cartCreate response is missing cart.id")
        if not isinstance(checkout_url, str) or not checkout_url:
            raise ShopifyApiError(
                message="cartCreate response is missing cart.checkoutUrl"
            )
        return cart_id, checkout_url

    async def verify_product_exists(
        self,
        *,
        shop_domain: str,
        access_token: str,
        product_gid: str,
    ) -> dict[str, str]:
        query = """
        query productById($id: ID!) {
            product(id: $id) {
                id
                title
                handle
            }
        }
        """
        payload = {"query": query, "variables": {"id": product_gid}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        product = response.get("product")
        if not isinstance(product, dict):
            raise ShopifyApiError(
                message=f"Product not found for GID: {product_gid}", status_code=404
            )

        found_id = product.get("id")
        title = product.get("title")
        handle = product.get("handle")
        if not isinstance(found_id, str) or not found_id:
            raise ShopifyApiError(
                message="Product verification response is missing product.id"
            )
        if not isinstance(title, str) or not title:
            raise ShopifyApiError(
                message="Product verification response is missing product.title"
            )
        if not isinstance(handle, str) or not handle:
            raise ShopifyApiError(
                message="Product verification response is missing product.handle"
            )
        return {"id": found_id, "title": title, "handle": handle}

    async def list_products(
        self,
        *,
        shop_domain: str,
        access_token: str,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        search_query = (query or "").strip()
        graphql_query = """
        query products($first: Int!, $query: String) {
            products(first: $first, query: $query, sortKey: UPDATED_AT, reverse: true) {
                edges {
                    node {
                        id
                        title
                        handle
                        status
                    }
                }
            }
        }
        """
        payload = {
            "query": graphql_query,
            "variables": {
                "first": limit,
                "query": search_query or None,
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        edges = ((response.get("products") or {}).get("edges")) or []
        if not isinstance(edges, list):
            raise ShopifyApiError(message="Product list response is invalid")

        products: list[dict[str, str]] = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node")
            if not isinstance(node, dict):
                continue
            product_id = node.get("id")
            title = node.get("title")
            handle = node.get("handle")
            product_status = node.get("status")

            if not isinstance(product_id, str) or not product_id:
                raise ShopifyApiError(
                    message="Product list response is missing product.id"
                )
            if not isinstance(title, str) or not title:
                raise ShopifyApiError(
                    message="Product list response is missing product.title"
                )
            if not isinstance(handle, str) or not handle:
                raise ShopifyApiError(
                    message="Product list response is missing product.handle"
                )
            if not isinstance(product_status, str) or not product_status:
                raise ShopifyApiError(
                    message="Product list response is missing product.status"
                )

            products.append(
                {
                    "id": product_id,
                    "title": title,
                    "handle": handle,
                    "status": product_status,
                }
            )

        return products

    @staticmethod
    def _price_cents_to_decimal_string(price_cents: int) -> str:
        return str(
            (Decimal(price_cents) / Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )

    @staticmethod
    def _decimal_price_to_cents(price: Any) -> int:
        try:
            decimal_value = Decimal(str(price).strip())
        except (InvalidOperation, ValueError, AttributeError) as exc:
            raise ShopifyApiError(
                message=f"Invalid variant price from Shopify: {price!r}"
            ) from exc
        cents = int(
            (decimal_value * Decimal(100)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        if cents < 0:
            raise ShopifyApiError(
                message=f"Shopify returned a negative variant price: {price!r}"
            )
        return cents

    async def get_product(
        self,
        *,
        shop_domain: str,
        access_token: str,
        product_gid: str,
    ) -> dict[str, Any]:
        cleaned_product_gid = product_gid.strip()
        if not cleaned_product_gid.startswith("gid://shopify/Product/"):
            raise ShopifyApiError(
                message="productGid must be a valid Shopify Product GID.",
                status_code=400,
            )

        graphql_query = """
        query productWithVariants($id: ID!, $first: Int!, $after: String) {
            shop {
                currencyCode
            }
            product(id: $id) {
                id
                title
                handle
                status
                variants(first: $first, after: $after) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    edges {
                        node {
                            id
                            title
                            price
                            compareAtPrice
                            barcode
                            taxable
                            inventoryPolicy
                            inventoryQuantity
                            selectedOptions {
                                name
                                value
                            }
                            inventoryItem {
                                sku
                                tracked
                                requiresShipping
                            }
                        }
                    }
                }
            }
        }
        """

        cursor: str | None = None
        currency: str | None = None
        product_title: str | None = None
        product_handle: str | None = None
        product_status: str | None = None
        variants: list[dict[str, Any]] = []

        while True:
            payload = {
                "query": graphql_query,
                "variables": {
                    "id": cleaned_product_gid,
                    "first": 100,
                    "after": cursor,
                },
            }
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload=payload,
            )

            shop = response.get("shop")
            if not isinstance(shop, dict):
                raise ShopifyApiError(
                    message="Product response is missing shop metadata."
                )
            raw_currency = shop.get("currencyCode")
            if not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
                raise ShopifyApiError(
                    message="Product response is missing shop currencyCode."
                )
            normalized_currency = raw_currency.strip().upper()
            if currency is None:
                currency = normalized_currency
            elif normalized_currency != currency:
                raise ShopifyApiError(
                    message="Shop currency changed while paginating product variants."
                )

            product = response.get("product")
            if not isinstance(product, dict):
                raise ShopifyApiError(
                    message=f"Product not found for GID: {cleaned_product_gid}",
                    status_code=404,
                )

            product_id = product.get("id")
            if not isinstance(product_id, str) or not product_id:
                raise ShopifyApiError(message="Product response is missing product.id")
            if product_id != cleaned_product_gid:
                raise ShopifyApiError(
                    message="Product response returned unexpected product.id"
                )

            raw_title = product.get("title")
            if not isinstance(raw_title, str) or not raw_title:
                raise ShopifyApiError(
                    message="Product response is missing product.title"
                )
            raw_handle = product.get("handle")
            if not isinstance(raw_handle, str) or not raw_handle:
                raise ShopifyApiError(
                    message="Product response is missing product.handle"
                )
            raw_status = product.get("status")
            if not isinstance(raw_status, str) or not raw_status:
                raise ShopifyApiError(
                    message="Product response is missing product.status"
                )

            if product_title is None:
                product_title = raw_title
                product_handle = raw_handle
                product_status = raw_status
            else:
                if (
                    raw_title != product_title
                    or raw_handle != product_handle
                    or raw_status != product_status
                ):
                    raise ShopifyApiError(
                        message="Product metadata changed while paginating variants."
                    )

            variants_connection = product.get("variants")
            if not isinstance(variants_connection, dict):
                raise ShopifyApiError(
                    message="Product response is missing variants connection."
                )
            edges = variants_connection.get("edges")
            if not isinstance(edges, list):
                raise ShopifyApiError(message="Product variants response is invalid.")

            for edge in edges:
                if not isinstance(edge, dict):
                    raise ShopifyApiError(
                        message="Product variants response contains invalid edge."
                    )
                node = edge.get("node")
                if not isinstance(node, dict):
                    raise ShopifyApiError(
                        message="Product variants response contains invalid node."
                    )

                variant_gid = node.get("id")
                title = node.get("title")
                price = node.get("price")
                compare_at_price = node.get("compareAtPrice")
                barcode = node.get("barcode")
                taxable = node.get("taxable")
                inventory_policy = node.get("inventoryPolicy")
                inventory_quantity = node.get("inventoryQuantity")
                selected_options = node.get("selectedOptions")
                inventory_item = node.get("inventoryItem")

                if not isinstance(variant_gid, str) or not variant_gid:
                    raise ShopifyApiError(
                        message="Product variant response is missing variant.id."
                    )
                if not isinstance(title, str) or not title:
                    raise ShopifyApiError(
                        message="Product variant response is missing variant.title."
                    )
                if not isinstance(price, str) or not price:
                    raise ShopifyApiError(
                        message="Product variant response is missing variant.price."
                    )
                if compare_at_price is not None and not isinstance(
                    compare_at_price, str
                ):
                    raise ShopifyApiError(
                        message="Product variant response has invalid compareAtPrice."
                    )
                if barcode is not None and not isinstance(barcode, str):
                    raise ShopifyApiError(
                        message="Product variant response has invalid barcode."
                    )
                if not isinstance(taxable, bool):
                    raise ShopifyApiError(
                        message="Product variant response has invalid taxable value."
                    )
                if inventory_policy is not None and not isinstance(
                    inventory_policy, str
                ):
                    raise ShopifyApiError(
                        message="Product variant response has invalid inventoryPolicy value."
                    )
                if inventory_quantity is not None and not isinstance(
                    inventory_quantity, int
                ):
                    raise ShopifyApiError(
                        message="Product variant response has invalid inventoryQuantity value."
                    )
                if not isinstance(selected_options, list):
                    raise ShopifyApiError(
                        message="Product variant response has invalid selectedOptions value."
                    )
                if not isinstance(inventory_item, dict):
                    raise ShopifyApiError(
                        message="Product variant response has invalid inventoryItem value."
                    )

                option_values: dict[str, str] = {}
                for selected_option in selected_options:
                    if not isinstance(selected_option, dict):
                        raise ShopifyApiError(
                            message="Product variant response has invalid selected option."
                        )
                    option_name = selected_option.get("name")
                    option_value = selected_option.get("value")
                    if not isinstance(option_name, str) or not option_name.strip():
                        raise ShopifyApiError(
                            message="Product variant response has selected option without name."
                        )
                    if not isinstance(option_value, str):
                        raise ShopifyApiError(
                            message="Product variant response has selected option without value."
                        )
                    option_values[option_name.strip()] = option_value

                sku: str | None = None
                inventory_management: str | None = None
                raw_sku = inventory_item.get("sku")
                raw_tracked = inventory_item.get("tracked")
                raw_requires_shipping = inventory_item.get("requiresShipping")
                if raw_sku is not None and not isinstance(raw_sku, str):
                    raise ShopifyApiError(
                        message="Product variant response has invalid inventoryItem.sku."
                    )
                if not isinstance(raw_tracked, bool):
                    raise ShopifyApiError(
                        message="Product variant response has invalid inventoryItem.tracked."
                    )
                if not isinstance(raw_requires_shipping, bool):
                    raise ShopifyApiError(
                        message="Product variant response has invalid inventoryItem.requiresShipping."
                    )
                sku = raw_sku
                inventory_management = "shopify" if raw_tracked else None
                requires_shipping = raw_requires_shipping

                variants.append(
                    {
                        "variantGid": variant_gid,
                        "title": title,
                        "priceCents": self._decimal_price_to_cents(price),
                        "currency": currency,
                        "compareAtPriceCents": (
                            self._decimal_price_to_cents(compare_at_price)
                            if compare_at_price is not None
                            else None
                        ),
                        "sku": sku,
                        "barcode": barcode,
                        "taxable": taxable,
                        "requiresShipping": requires_shipping,
                        "inventoryPolicy": (
                            inventory_policy.strip().lower()
                            if inventory_policy
                            else None
                        ),
                        "inventoryManagement": inventory_management,
                        "inventoryQuantity": inventory_quantity,
                        "optionValues": option_values,
                    }
                )

            page_info = variants_connection.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ShopifyApiError(
                    message="Product variants response is missing pageInfo."
                )
            has_next_page = page_info.get("hasNextPage")
            end_cursor = page_info.get("endCursor")
            if not isinstance(has_next_page, bool):
                raise ShopifyApiError(
                    message="Product variants response has invalid pageInfo.hasNextPage."
                )
            if has_next_page:
                if not isinstance(end_cursor, str) or not end_cursor:
                    raise ShopifyApiError(
                        message="Product variants response has invalid pageInfo.endCursor."
                    )
                cursor = end_cursor
                continue
            break

        if currency is None:
            raise ShopifyApiError(
                message="Product response is missing currency metadata."
            )
        if product_title is None or product_handle is None or product_status is None:
            raise ShopifyApiError(message="Product response is missing metadata.")

        return {
            "productGid": cleaned_product_gid,
            "title": product_title,
            "handle": product_handle,
            "status": product_status,
            "variants": variants,
        }

    async def create_product(
        self,
        *,
        shop_domain: str,
        access_token: str,
        title: str,
        variants: list[dict[str, Any]],
        description: str | None = None,
        handle: str | None = None,
        vendor: str | None = None,
        product_type: str | None = None,
        tags: list[str] | None = None,
        status: str = "DRAFT",
    ) -> dict[str, Any]:
        if not variants:
            raise ShopifyApiError(
                message="At least one variant is required for product creation.",
                status_code=400,
            )

        cleaned_variants: list[dict[str, Any]] = []
        seen_titles: set[str] = set()
        normalized_currency: str | None = None
        for raw_variant in variants:
            if not isinstance(raw_variant, dict):
                raise ShopifyApiError(
                    message="Each variant must be an object.", status_code=400
                )
            raw_title = raw_variant.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ShopifyApiError(
                    message="Each variant requires a non-empty title.", status_code=400
                )
            variant_title = raw_title.strip()
            lower_title = variant_title.lower()
            if lower_title in seen_titles:
                raise ShopifyApiError(
                    message="Variant titles must be unique.", status_code=400
                )
            seen_titles.add(lower_title)

            raw_price_cents = raw_variant.get("priceCents")
            if not isinstance(raw_price_cents, int) or raw_price_cents < 0:
                raise ShopifyApiError(
                    message="Each variant requires a non-negative integer priceCents.",
                    status_code=400,
                )

            raw_currency = raw_variant.get("currency")
            if not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
                raise ShopifyApiError(
                    message="Each variant requires a 3-letter currency code.",
                    status_code=400,
                )
            currency = raw_currency.strip().upper()
            if normalized_currency is None:
                normalized_currency = currency
            elif currency != normalized_currency:
                raise ShopifyApiError(
                    message="All variants must use the same currency for Shopify product creation.",
                    status_code=400,
                )

            cleaned_variants.append(
                {
                    "title": variant_title,
                    "priceCents": raw_price_cents,
                    "price": self._price_cents_to_decimal_string(raw_price_cents),
                    "currency": currency,
                }
            )

        product_input: dict[str, Any] = {
            "title": title.strip(),
            "status": status.strip().upper(),
            "productOptions": [
                {
                    "name": "Title",
                    "values": [
                        {"name": variant["title"]} for variant in cleaned_variants
                    ],
                }
            ],
        }
        if description is not None and description.strip():
            product_input["descriptionHtml"] = description.strip()
        if handle is not None and handle.strip():
            product_input["handle"] = handle.strip()
        if vendor is not None and vendor.strip():
            product_input["vendor"] = vendor.strip()
        if product_type is not None and product_type.strip():
            product_input["productType"] = product_type.strip()
        if tags:
            product_input["tags"] = tags

        create_query = """
        mutation productCreate($product: ProductCreateInput!) {
            productCreate(product: $product) {
                product {
                    id
                    title
                    handle
                    status
                    variants(first: 1) {
                        edges {
                            node {
                                id
                                title
                                price
                            }
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        create_response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={"query": create_query, "variables": {"product": product_input}},
        )
        create_data = create_response.get("productCreate") or {}
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(
                message=f"productCreate failed: {messages}", status_code=409
            )

        product = create_data.get("product")
        if not isinstance(product, dict):
            raise ShopifyApiError(message="productCreate response is missing product")

        product_gid = product.get("id")
        product_title = product.get("title")
        product_handle = product.get("handle")
        product_status = product.get("status")
        if not isinstance(product_gid, str) or not product_gid:
            raise ShopifyApiError(
                message="productCreate response is missing product.id"
            )
        if not isinstance(product_title, str) or not product_title:
            raise ShopifyApiError(
                message="productCreate response is missing product.title"
            )
        if not isinstance(product_handle, str) or not product_handle:
            raise ShopifyApiError(
                message="productCreate response is missing product.handle"
            )
        if not isinstance(product_status, str) or not product_status:
            raise ShopifyApiError(
                message="productCreate response is missing product.status"
            )

        initial_variant_edges = ((product.get("variants") or {}).get("edges")) or []
        if not isinstance(initial_variant_edges, list) or not initial_variant_edges:
            raise ShopifyApiError(
                message="productCreate response is missing initial product variant."
            )
        initial_variant_node = (
            (initial_variant_edges[0] or {}).get("node")
            if isinstance(initial_variant_edges[0], dict)
            else None
        )
        if not isinstance(initial_variant_node, dict):
            raise ShopifyApiError(
                message="productCreate response is missing initial variant node."
            )
        initial_variant_id = initial_variant_node.get("id")
        if not isinstance(initial_variant_id, str) or not initial_variant_id:
            raise ShopifyApiError(
                message="productCreate response is missing initial variant id."
            )

        update_query = """
        mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
            productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants {
                    id
                    title
                    price
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        first_variant = cleaned_variants[0]
        update_response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": update_query,
                "variables": {
                    "productId": product_gid,
                    "variants": [
                        {"id": initial_variant_id, "price": first_variant["price"]}
                    ],
                },
            },
        )
        update_data = update_response.get("productVariantsBulkUpdate") or {}
        update_errors = update_data.get("userErrors") or []
        if update_errors:
            messages = "; ".join(str(error.get("message")) for error in update_errors)
            raise ShopifyApiError(
                message=f"productVariantsBulkUpdate failed: {messages}", status_code=409
            )
        updated_variants = update_data.get("productVariants") or []
        if not isinstance(updated_variants, list) or not updated_variants:
            raise ShopifyApiError(
                message="productVariantsBulkUpdate response is missing variants."
            )
        updated_first_variant = updated_variants[0]
        if not isinstance(updated_first_variant, dict):
            raise ShopifyApiError(
                message="productVariantsBulkUpdate response is invalid."
            )

        created_variants: list[dict[str, Any]] = []
        if len(cleaned_variants) > 1:
            create_variants_query = """
            mutation productVariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                productVariantsBulkCreate(productId: $productId, variants: $variants) {
                    productVariants {
                        id
                        title
                        price
                    }
                    userErrors {
                        field
                        message
                    }
                }
            }
            """
            bulk_create_response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={
                    "query": create_variants_query,
                    "variables": {
                        "productId": product_gid,
                        "variants": [
                            {
                                "price": variant["price"],
                                "optionValues": [
                                    {"optionName": "Title", "name": variant["title"]}
                                ],
                            }
                            for variant in cleaned_variants[1:]
                        ],
                    },
                },
            )
            bulk_create_data = (
                bulk_create_response.get("productVariantsBulkCreate") or {}
            )
            bulk_create_errors = bulk_create_data.get("userErrors") or []
            if bulk_create_errors:
                messages = "; ".join(
                    str(error.get("message")) for error in bulk_create_errors
                )
                raise ShopifyApiError(
                    message=f"productVariantsBulkCreate failed: {messages}",
                    status_code=409,
                )
            raw_created_variants = bulk_create_data.get("productVariants") or []
            if not isinstance(raw_created_variants, list):
                raise ShopifyApiError(
                    message="productVariantsBulkCreate response is invalid."
                )
            for raw_variant in raw_created_variants:
                if not isinstance(raw_variant, dict):
                    continue
                created_variants.append(raw_variant)

        currency = normalized_currency or "USD"
        variant_rows: list[dict[str, Any]] = []
        for variant_node in [updated_first_variant, *created_variants]:
            variant_gid = variant_node.get("id")
            variant_title = variant_node.get("title")
            variant_price = variant_node.get("price")
            if not isinstance(variant_gid, str) or not variant_gid:
                raise ShopifyApiError(
                    message="Variant creation response is missing variant id."
                )
            if not isinstance(variant_title, str) or not variant_title:
                raise ShopifyApiError(
                    message="Variant creation response is missing variant title."
                )
            variant_rows.append(
                {
                    "variantGid": variant_gid,
                    "title": variant_title,
                    "priceCents": self._decimal_price_to_cents(variant_price),
                    "currency": currency,
                }
            )

        if len(variant_rows) != len(cleaned_variants):
            raise ShopifyApiError(
                message=(
                    "Shopify variant creation returned an unexpected number of variants. "
                    f"Expected {len(cleaned_variants)}, got {len(variant_rows)}."
                ),
            )

        return {
            "productGid": product_gid,
            "title": product_title,
            "handle": product_handle,
            "status": product_status,
            "variants": variant_rows,
        }

    async def _resolve_variant_product_gid(
        self,
        *,
        shop_domain: str,
        access_token: str,
        variant_gid: str,
    ) -> str:
        query = """
        query productVariantNode($id: ID!) {
            node(id: $id) {
                ... on ProductVariant {
                    id
                    product {
                        id
                    }
                }
            }
        }
        """
        payload = {"query": query, "variables": {"id": variant_gid}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        node = response.get("node")
        if not isinstance(node, dict):
            raise ShopifyApiError(
                message=f"Product variant not found for GID: {variant_gid}",
                status_code=404,
            )
        product = node.get("product")
        if not isinstance(product, dict):
            raise ShopifyApiError(
                message=f"Product variant is missing parent product for GID: {variant_gid}",
                status_code=404,
            )
        product_gid = product.get("id")
        if not isinstance(product_gid, str) or not product_gid:
            raise ShopifyApiError(
                message=f"Product variant is missing product id for GID: {variant_gid}",
                status_code=404,
            )
        return product_gid

    async def update_variant(
        self,
        *,
        shop_domain: str,
        access_token: str,
        variant_gid: str,
        fields: dict[str, Any],
    ) -> dict[str, str]:
        cleaned_variant_gid = variant_gid.strip()
        if not cleaned_variant_gid.startswith("gid://shopify/ProductVariant/"):
            raise ShopifyApiError(
                message="variantGid must be a valid Shopify ProductVariant GID.",
                status_code=400,
            )
        if not fields:
            raise ShopifyApiError(
                message="At least one variant update field is required.",
                status_code=400,
            )

        supported_fields = {
            "title",
            "priceCents",
            "compareAtPriceCents",
            "sku",
            "barcode",
            "inventoryPolicy",
            "inventoryManagement",
        }
        unsupported_fields = sorted(
            name for name in fields.keys() if name not in supported_fields
        )
        if unsupported_fields:
            raise ShopifyApiError(
                message=f"Unsupported variant update fields: {', '.join(unsupported_fields)}",
                status_code=400,
            )

        variant_input: dict[str, Any] = {"id": cleaned_variant_gid}
        inventory_item_input: dict[str, Any] = {}
        if "title" in fields:
            raw_title = fields.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ShopifyApiError(
                    message="title must be a non-empty string.", status_code=400
                )
            variant_input["optionValues"] = [
                {"optionName": "Title", "name": raw_title.strip()}
            ]

        if "priceCents" in fields:
            raw_price_cents = fields.get("priceCents")
            if not isinstance(raw_price_cents, int) or raw_price_cents < 0:
                raise ShopifyApiError(
                    message="priceCents must be a non-negative integer.",
                    status_code=400,
                )
            variant_input["price"] = self._price_cents_to_decimal_string(
                raw_price_cents
            )

        if "compareAtPriceCents" in fields:
            raw_compare_at_price_cents = fields.get("compareAtPriceCents")
            if raw_compare_at_price_cents is None:
                variant_input["compareAtPrice"] = None
            else:
                if (
                    not isinstance(raw_compare_at_price_cents, int)
                    or raw_compare_at_price_cents < 0
                ):
                    raise ShopifyApiError(
                        message="compareAtPriceCents must be null or a non-negative integer.",
                        status_code=400,
                    )
                variant_input["compareAtPrice"] = self._price_cents_to_decimal_string(
                    raw_compare_at_price_cents
                )

        if "sku" in fields:
            raw_sku = fields.get("sku")
            if raw_sku is None:
                inventory_item_input["sku"] = None
            else:
                if not isinstance(raw_sku, str) or not raw_sku.strip():
                    raise ShopifyApiError(
                        message="sku must be null or a non-empty string.",
                        status_code=400,
                    )
                inventory_item_input["sku"] = raw_sku.strip()

        if "barcode" in fields:
            raw_barcode = fields.get("barcode")
            if raw_barcode is None:
                variant_input["barcode"] = None
            else:
                if not isinstance(raw_barcode, str) or not raw_barcode.strip():
                    raise ShopifyApiError(
                        message="barcode must be null or a non-empty string.",
                        status_code=400,
                    )
                variant_input["barcode"] = raw_barcode.strip()

        if "inventoryPolicy" in fields:
            raw_inventory_policy = fields.get("inventoryPolicy")
            if (
                not isinstance(raw_inventory_policy, str)
                or not raw_inventory_policy.strip()
            ):
                raise ShopifyApiError(
                    message="inventoryPolicy must be one of: deny, continue.",
                    status_code=400,
                )
            normalized_inventory_policy = raw_inventory_policy.strip().upper()
            if normalized_inventory_policy not in {"DENY", "CONTINUE"}:
                raise ShopifyApiError(
                    message="inventoryPolicy must be one of: deny, continue.",
                    status_code=400,
                )
            variant_input["inventoryPolicy"] = normalized_inventory_policy

        if "inventoryManagement" in fields:
            raw_inventory_management = fields.get("inventoryManagement")
            if raw_inventory_management is None:
                inventory_item_input["tracked"] = False
            else:
                if (
                    not isinstance(raw_inventory_management, str)
                    or not raw_inventory_management.strip()
                ):
                    raise ShopifyApiError(
                        message="inventoryManagement must be null or 'shopify'.",
                        status_code=400,
                    )
                normalized_inventory_management = (
                    raw_inventory_management.strip().lower()
                )
                if normalized_inventory_management != "shopify":
                    raise ShopifyApiError(
                        message="inventoryManagement must be null or 'shopify'.",
                        status_code=400,
                    )
                inventory_item_input["tracked"] = True

        if inventory_item_input:
            variant_input["inventoryItem"] = inventory_item_input

        product_gid = await self._resolve_variant_product_gid(
            shop_domain=shop_domain,
            access_token=access_token,
            variant_gid=cleaned_variant_gid,
        )

        mutation = """
        mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
            productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants {
                    id
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": mutation,
            "variables": {
                "productId": product_gid,
                "variants": [variant_input],
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        update_data = response.get("productVariantsBulkUpdate") or {}
        user_errors = update_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(
                message=f"productVariantsBulkUpdate failed: {messages}", status_code=409
            )

        updated_variants = update_data.get("productVariants") or []
        if not isinstance(updated_variants, list) or not updated_variants:
            raise ShopifyApiError(
                message="productVariantsBulkUpdate response is missing variants."
            )

        updated_variant_ids = {
            item.get("id")
            for item in updated_variants
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if cleaned_variant_gid not in updated_variant_ids:
            raise ShopifyApiError(
                message="productVariantsBulkUpdate response did not include requested variant.",
            )

        return {
            "productGid": product_gid,
            "variantGid": cleaned_variant_gid,
        }

    @staticmethod
    def _normalize_policy_page_handle(handle: str) -> str:
        cleaned = handle.strip().lower()
        if not cleaned:
            raise ShopifyApiError(
                message="Policy page handle cannot be empty.", status_code=400
            )
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cleaned):
            raise ShopifyApiError(
                message=(
                    "Policy page handle must use lowercase letters, numbers, and hyphens "
                    "(for example: returns-refunds-policy)."
                ),
                status_code=400,
            )
        return cleaned

    @staticmethod
    def _coerce_page_node(
        *,
        node: Any,
        mutation_name: str,
    ) -> dict[str, str]:
        if not isinstance(node, dict):
            raise ShopifyApiError(
                message=f"{mutation_name} response is missing page object."
            )

        page_id = node.get("id")
        title = node.get("title")
        handle = node.get("handle")

        if not isinstance(page_id, str) or not page_id:
            raise ShopifyApiError(
                message=f"{mutation_name} response is missing page.id."
            )
        if not isinstance(title, str) or not title:
            raise ShopifyApiError(
                message=f"{mutation_name} response is missing page.title."
            )
        if not isinstance(handle, str) or not handle:
            raise ShopifyApiError(
                message=f"{mutation_name} response is missing page.handle."
            )
        return {
            "id": page_id,
            "title": title,
            "handle": handle,
        }

    @classmethod
    def _build_policy_page_url(cls, *, shop_domain: str, handle: str) -> str:
        normalized_handle = cls._normalize_policy_page_handle(handle)
        return f"https://{shop_domain.strip().lower()}/pages/{normalized_handle}"

    @staticmethod
    def _normalize_menu_handle(handle: str) -> str:
        cleaned = handle.strip().lower()
        if not cleaned:
            raise ShopifyApiError(
                message="Footer menu handle cannot be empty.", status_code=409
            )
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cleaned):
            raise ShopifyApiError(
                message=(
                    "Footer menu handle must use lowercase letters, numbers, and hyphens. "
                    f"Received: {handle!r}."
                ),
                status_code=409,
            )
        return cleaned

    @staticmethod
    def _derive_menu_title_from_handle(handle: str) -> str:
        parts = [token for token in handle.split("-") if token]
        if not parts:
            return "Footer"
        return " ".join(token.capitalize() for token in parts)

    @classmethod
    def _build_policy_page_path(cls, *, handle: str) -> str:
        normalized_handle = cls._normalize_policy_page_handle(handle)
        return f"/pages/{normalized_handle}"

    @staticmethod
    def _normalize_menu_item_path(url: Any) -> str | None:
        if not isinstance(url, str):
            return None
        cleaned_url = url.strip()
        if not cleaned_url:
            return None
        parsed = urlparse(cleaned_url)
        if parsed.scheme and parsed.netloc:
            raw_path = parsed.path
        else:
            raw_path = cleaned_url
        if not isinstance(raw_path, str):
            return None
        path_without_fragment = raw_path.split("#", 1)[0]
        path_without_query = path_without_fragment.split("?", 1)[0].strip()
        if not path_without_query:
            return "/"
        if not path_without_query.startswith("/"):
            path_without_query = f"/{path_without_query}"
        return f"/{path_without_query.strip('/').lower()}"

    @classmethod
    def _coerce_menu_summary_node(
        cls,
        *,
        node: Any,
        query_name: str,
    ) -> dict[str, str]:
        if not isinstance(node, dict):
            raise ShopifyApiError(
                message=f"{query_name} response is missing menu node."
            )
        menu_id = node.get("id")
        title = node.get("title")
        handle = node.get("handle")
        if not isinstance(menu_id, str) or not menu_id:
            raise ShopifyApiError(message=f"{query_name} response is missing menu.id.")
        if not isinstance(title, str) or not title:
            raise ShopifyApiError(
                message=f"{query_name} response is missing menu.title."
            )
        if not isinstance(handle, str) or not handle:
            raise ShopifyApiError(
                message=f"{query_name} response is missing menu.handle."
            )
        return {
            "id": menu_id,
            "title": title,
            "handle": cls._normalize_menu_handle(handle),
        }

    @classmethod
    def _coerce_menu_item_node(
        cls,
        *,
        node: Any,
        query_name: str,
    ) -> dict[str, Any]:
        if not isinstance(node, dict):
            raise ShopifyApiError(
                message=f"{query_name} response is missing menu item node."
            )

        title = node.get("title")
        item_type = node.get("type")
        if not isinstance(title, str) or not title:
            raise ShopifyApiError(
                message=f"{query_name} response is missing menu item title."
            )
        if not isinstance(item_type, str) or not item_type:
            raise ShopifyApiError(
                message=f"{query_name} response is missing menu item type."
            )

        parsed_item: dict[str, Any] = {
            "title": title,
            "type": item_type,
        }
        item_id = node.get("id")
        if item_id is not None:
            if not isinstance(item_id, str) or not item_id:
                raise ShopifyApiError(
                    message=f"{query_name} response has an invalid menu item id."
                )
            parsed_item["id"] = item_id

        item_url = node.get("url")
        if item_url is not None:
            if not isinstance(item_url, str):
                raise ShopifyApiError(
                    message=f"{query_name} response has an invalid menu item url."
                )
            parsed_item["url"] = item_url

        resource_id = node.get("resourceId")
        if resource_id is not None:
            if not isinstance(resource_id, str):
                raise ShopifyApiError(
                    message=f"{query_name} response has an invalid menu item resourceId."
                )
            parsed_item["resourceId"] = resource_id

        tags = node.get("tags")
        if tags is not None:
            if not isinstance(tags, list) or any(
                not isinstance(tag, str) for tag in tags
            ):
                raise ShopifyApiError(
                    message=f"{query_name} response has invalid menu item tags."
                )
            parsed_item["tags"] = tags

        raw_items = node.get("items") or []
        if not isinstance(raw_items, list):
            raise ShopifyApiError(
                message=f"{query_name} response has invalid menu item children."
            )
        parsed_item["items"] = [
            cls._coerce_menu_item_node(node=item, query_name=query_name)
            for item in raw_items
        ]
        return parsed_item

    @classmethod
    def _coerce_menu_detail_node(
        cls,
        *,
        node: Any,
        query_name: str,
    ) -> dict[str, Any]:
        parsed_summary = cls._coerce_menu_summary_node(node=node, query_name=query_name)
        raw_items = node.get("items") if isinstance(node, dict) else None
        if not isinstance(raw_items, list):
            raise ShopifyApiError(
                message=f"{query_name} response is missing menu items."
            )
        return {
            **parsed_summary,
            "items": [
                cls._coerce_menu_item_node(node=item, query_name=query_name)
                for item in raw_items
            ],
        }

    @classmethod
    def _collect_footer_menu_handles_from_settings(
        cls,
        *,
        settings: Any,
        handles: set[str],
    ) -> None:
        if not isinstance(settings, dict):
            return
        for key, value in settings.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            normalized_key = key.strip().lower()
            if normalized_key != "menu" and not normalized_key.endswith("_menu"):
                continue
            cleaned_handle = value.strip()
            if not cleaned_handle:
                continue
            handles.add(cls._normalize_menu_handle(cleaned_handle))

    @classmethod
    def _coerce_footer_menu_handles_from_theme_data(
        cls,
        *,
        footer_group_data: dict[str, Any],
    ) -> list[str]:
        raw_sections = footer_group_data.get("sections")
        if not isinstance(raw_sections, dict):
            raise ShopifyApiError(
                message=(
                    f"Theme footer config {_THEME_FOOTER_GROUP_FILENAME} is missing sections."
                ),
                status_code=409,
            )

        handles: set[str] = set()
        for section in raw_sections.values():
            if not isinstance(section, dict):
                continue
            cls._collect_footer_menu_handles_from_settings(
                settings=section.get("settings"),
                handles=handles,
            )
            raw_blocks = section.get("blocks")
            if not isinstance(raw_blocks, dict):
                continue
            for block in raw_blocks.values():
                if not isinstance(block, dict):
                    continue
                cls._collect_footer_menu_handles_from_settings(
                    settings=block.get("settings"),
                    handles=handles,
                )

        if not handles:
            raise ShopifyApiError(
                message=(
                    "No footer menu handles were configured in "
                    f"{_THEME_FOOTER_GROUP_FILENAME}. Configure the footer menu settings first."
                ),
                status_code=409,
            )
        return sorted(handles)

    @classmethod
    def _build_policy_menu_items(
        cls,
        *,
        policy_pages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for policy_page in policy_pages:
            raw_title = policy_page.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ShopifyApiError(
                    message="Policy page sync cannot build footer links without title.",
                    status_code=409,
                )
            raw_page_id = policy_page.get("pageId")
            if not isinstance(raw_page_id, str) or not raw_page_id:
                raise ShopifyApiError(
                    message="Policy page sync cannot build footer links without pageId.",
                    status_code=409,
                )
            items.append(
                {
                    "title": raw_title.strip(),
                    "type": "PAGE",
                    "resourceId": raw_page_id,
                    "items": [],
                }
            )
        return items

    @classmethod
    def _menu_items_to_update_input(
        cls,
        *,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for item in items:
            title = item.get("title")
            item_type = item.get("type")
            if not isinstance(title, str) or not isinstance(item_type, str):
                raise ShopifyApiError(
                    message="Cannot sync footer menu because an existing menu item is invalid.",
                    status_code=409,
                )
            converted: dict[str, Any] = {
                "title": title,
                "type": item_type,
            }
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                converted["id"] = item_id
            item_url = item.get("url")
            if isinstance(item_url, str):
                converted["url"] = item_url
            resource_id = item.get("resourceId")
            if isinstance(resource_id, str):
                converted["resourceId"] = resource_id
            tags = item.get("tags")
            if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
                converted["tags"] = tags
            raw_child_items = item.get("items") or []
            if not isinstance(raw_child_items, list):
                raise ShopifyApiError(
                    message=(
                        "Cannot sync footer menu because an existing menu item has "
                        "invalid nested items."
                    ),
                    status_code=409,
                )
            converted["items"] = cls._menu_items_to_update_input(items=raw_child_items)
            output.append(converted)
        return output

    @classmethod
    def _menu_items_to_create_input(
        cls,
        *,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for item in items:
            title = item.get("title")
            item_type = item.get("type")
            if not isinstance(title, str) or not isinstance(item_type, str):
                raise ShopifyApiError(
                    message="Cannot create footer menu because a policy menu item is invalid.",
                    status_code=409,
                )
            converted: dict[str, Any] = {
                "title": title,
                "type": item_type,
            }
            item_url = item.get("url")
            if isinstance(item_url, str):
                converted["url"] = item_url
            resource_id = item.get("resourceId")
            if isinstance(resource_id, str):
                converted["resourceId"] = resource_id
            tags = item.get("tags")
            if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
                converted["tags"] = tags
            raw_child_items = item.get("items") or []
            if not isinstance(raw_child_items, list):
                raise ShopifyApiError(
                    message=(
                        "Cannot create footer menu because a policy menu item has "
                        "invalid nested items."
                    ),
                    status_code=409,
                )
            converted["items"] = cls._menu_items_to_create_input(items=raw_child_items)
            output.append(converted)
        return output

    @classmethod
    def _apply_policy_pages_to_menu_items(
        cls,
        *,
        menu_items: list[dict[str, Any]],
        policy_pages: list[dict[str, str]],
    ) -> tuple[list[dict[str, Any]], bool]:
        next_items = deepcopy(menu_items)
        existing_by_resource_id: dict[str, dict[str, Any]] = {}
        existing_by_path: dict[str, dict[str, Any]] = {}
        for item in next_items:
            resource_id = item.get("resourceId")
            if isinstance(resource_id, str) and resource_id:
                existing_by_resource_id[resource_id] = item
            normalized_path = cls._normalize_menu_item_path(item.get("url"))
            if normalized_path is not None:
                existing_by_path[normalized_path] = item

        changed = False
        for policy_page in policy_pages:
            raw_page_id = policy_page.get("pageId")
            raw_title = policy_page.get("title")
            raw_handle = policy_page.get("handle")
            if (
                not isinstance(raw_page_id, str)
                or not raw_page_id
                or not isinstance(raw_title, str)
                or not raw_title.strip()
                or not isinstance(raw_handle, str)
                or not raw_handle.strip()
            ):
                raise ShopifyApiError(
                    message=(
                        "Policy page sync cannot update footer menu because policy page data "
                        "is incomplete."
                    ),
                    status_code=409,
                )

            normalized_path = cls._build_policy_page_path(handle=raw_handle)
            existing_item = existing_by_resource_id.get(raw_page_id)
            if existing_item is None:
                existing_item = existing_by_path.get(normalized_path)

            if existing_item is None:
                next_items.append(
                    {
                        "title": raw_title.strip(),
                        "type": "PAGE",
                        "resourceId": raw_page_id,
                        "items": [],
                    }
                )
                changed = True
                continue

            if existing_item.get("title") != raw_title.strip():
                existing_item["title"] = raw_title.strip()
                changed = True
            if existing_item.get("type") != "PAGE":
                existing_item["type"] = "PAGE"
                changed = True
            if existing_item.get("resourceId") != raw_page_id:
                existing_item["resourceId"] = raw_page_id
                changed = True

        return next_items, changed

    async def _resolve_main_theme(
        self,
        *,
        shop_domain: str,
        access_token: str,
    ) -> dict[str, str]:
        query = """
        query themesForPolicyFooterSync($first: Int!) {
            themes(first: $first) {
                nodes {
                    id
                    name
                    role
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={"query": query, "variables": {"first": 100}},
        )
        raw_nodes = (response.get("themes") or {}).get("nodes")
        if not isinstance(raw_nodes, list):
            raise ShopifyApiError(
                message="themes query response is invalid while syncing footer policy links."
            )

        matching_themes: list[dict[str, str]] = []
        for node in raw_nodes:
            parsed_theme = self._coerce_theme_data(
                node=node, query_name="themesForPolicyFooterSync"
            )
            if parsed_theme["role"].strip().upper() == "MAIN":
                matching_themes.append(parsed_theme)

        if not matching_themes:
            raise ShopifyApiError(
                message="Main theme not found while syncing footer policy links.",
                status_code=409,
            )
        if len(matching_themes) > 1:
            theme_ids = ", ".join(theme["id"] for theme in matching_themes)
            raise ShopifyApiError(
                message=(
                    "Multiple main themes were returned while syncing footer policy links. "
                    f"matchedThemeIds={theme_ids}"
                ),
                status_code=409,
            )
        return matching_themes[0]

    async def _load_footer_menu_handles(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
    ) -> list[str]:
        footer_group_content = await self._load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme_id,
            filename=_THEME_FOOTER_GROUP_FILENAME,
        )
        footer_group_data = self._parse_theme_template_json(
            filename=_THEME_FOOTER_GROUP_FILENAME,
            template_content=footer_group_content,
        )
        return self._coerce_footer_menu_handles_from_theme_data(
            footer_group_data=footer_group_data
        )

    async def _list_shop_menus(
        self,
        *,
        shop_domain: str,
        access_token: str,
    ) -> list[dict[str, str]]:
        query = """
        query menusForPolicyFooterSync($first: Int!, $after: String) {
            menus(first: $first, after: $after) {
                nodes {
                    id
                    title
                    handle
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        menus: list[dict[str, str]] = []
        after: str | None = None
        for _ in range(20):
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={
                    "query": query,
                    "variables": {
                        "first": 250,
                        "after": after,
                    },
                },
            )
            connection = response.get("menus")
            if not isinstance(connection, dict):
                raise ShopifyApiError(
                    message=(
                        "menus query response is invalid while syncing footer policy links."
                    )
                )
            raw_nodes = connection.get("nodes")
            if not isinstance(raw_nodes, list):
                raise ShopifyApiError(
                    message=(
                        "menus query response is missing nodes while syncing footer policy links."
                    )
                )
            for node in raw_nodes:
                menus.append(
                    self._coerce_menu_summary_node(
                        node=node,
                        query_name="menusForPolicyFooterSync",
                    )
                )
            page_info = connection.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ShopifyApiError(
                    message=(
                        "menus query response is missing pageInfo while syncing footer policy links."
                    )
                )
            has_next_page = page_info.get("hasNextPage")
            if not isinstance(has_next_page, bool):
                raise ShopifyApiError(
                    message=(
                        "menus query response is missing pageInfo.hasNextPage while syncing "
                        "footer policy links."
                    )
                )
            if not has_next_page:
                return menus
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor:
                raise ShopifyApiError(
                    message=(
                        "menus query response is missing pageInfo.endCursor while syncing "
                        "footer policy links."
                    )
                )
            after = end_cursor

        raise ShopifyApiError(
            message=(
                "menus query exceeded pagination limit while syncing footer policy links. "
                "Reduce menu count or adjust the pagination strategy."
            ),
            status_code=409,
        )

    async def _load_menu_details(
        self,
        *,
        shop_domain: str,
        access_token: str,
        menu_id: str,
    ) -> dict[str, Any]:
        query = """
        query menuForPolicyFooterSync($id: ID!) {
            menu(id: $id) {
                id
                title
                handle
                items {
                    id
                    title
                    type
                    url
                    resourceId
                    tags
                    items {
                        id
                        title
                        type
                        url
                        resourceId
                        tags
                        items {
                            id
                            title
                            type
                            url
                            resourceId
                            tags
                            items {
                                id
                                title
                                type
                                url
                                resourceId
                                tags
                            }
                        }
                    }
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={"query": query, "variables": {"id": menu_id}},
        )
        menu = response.get("menu")
        if menu is None:
            raise ShopifyApiError(
                message=f"Menu not found for menuId={menu_id}.",
                status_code=404,
            )
        return self._coerce_menu_detail_node(
            node=menu,
            query_name="menuForPolicyFooterSync",
        )

    async def _create_menu(
        self,
        *,
        shop_domain: str,
        access_token: str,
        handle: str,
        title: str,
        items: list[dict[str, Any]],
    ) -> dict[str, str]:
        mutation = """
        mutation menuCreateForPolicyFooterSync(
            $title: String!
            $handle: String!
            $items: [MenuItemCreateInput!]!
        ) {
            menuCreate(title: $title, handle: $handle, items: $items) {
                menu {
                    id
                    title
                    handle
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": mutation,
                "variables": {
                    "title": title,
                    "handle": handle,
                    "items": self._menu_items_to_create_input(items=items),
                },
            },
        )
        create_data = response.get("menuCreate")
        if not isinstance(create_data, dict):
            raise ShopifyApiError(
                message="menuCreate response is missing payload.",
                status_code=409,
            )
        user_errors = create_data.get("userErrors") or []
        self._assert_no_user_errors(user_errors=user_errors, mutation_name="menuCreate")
        return self._coerce_menu_summary_node(
            node=create_data.get("menu"),
            query_name="menuCreate",
        )

    async def _update_menu(
        self,
        *,
        shop_domain: str,
        access_token: str,
        menu_id: str,
        title: str,
        handle: str,
        items: list[dict[str, Any]],
    ) -> dict[str, str]:
        mutation = """
        mutation menuUpdateForPolicyFooterSync(
            $id: ID!
            $title: String!
            $handle: String!
            $items: [MenuItemUpdateInput!]!
        ) {
            menuUpdate(id: $id, title: $title, handle: $handle, items: $items) {
                menu {
                    id
                    title
                    handle
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": mutation,
                "variables": {
                    "id": menu_id,
                    "title": title,
                    "handle": handle,
                    "items": self._menu_items_to_update_input(items=items),
                },
            },
        )
        update_data = response.get("menuUpdate")
        if not isinstance(update_data, dict):
            raise ShopifyApiError(
                message="menuUpdate response is missing payload.",
                status_code=409,
            )
        user_errors = update_data.get("userErrors") or []
        self._assert_no_user_errors(user_errors=user_errors, mutation_name="menuUpdate")
        return self._coerce_menu_summary_node(
            node=update_data.get("menu"),
            query_name="menuUpdate",
        )

    async def _sync_policy_pages_to_footer_menus(
        self,
        *,
        shop_domain: str,
        access_token: str,
        policy_pages: list[dict[str, str]],
    ) -> None:
        if not policy_pages:
            return
        main_theme = await self._resolve_main_theme(
            shop_domain=shop_domain,
            access_token=access_token,
        )
        footer_menu_handles = await self._load_footer_menu_handles(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=main_theme["id"],
        )
        all_menus = await self._list_shop_menus(
            shop_domain=shop_domain,
            access_token=access_token,
        )

        menu_summaries_by_handle: dict[str, list[dict[str, str]]] = {}
        for menu in all_menus:
            menu_summaries_by_handle.setdefault(menu["handle"], []).append(menu)

        policy_menu_items = self._build_policy_menu_items(policy_pages=policy_pages)

        for menu_handle in footer_menu_handles:
            matching_menus = menu_summaries_by_handle.get(menu_handle, [])
            if len(matching_menus) > 1:
                menu_ids = ", ".join(menu["id"] for menu in matching_menus)
                raise ShopifyApiError(
                    message=(
                        "Multiple menus matched a footer menu handle while syncing policy links. "
                        f"handle={menu_handle}, matchedMenuIds={menu_ids}"
                    ),
                    status_code=409,
                )

            if not matching_menus:
                created_menu = await self._create_menu(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    handle=menu_handle,
                    title=self._derive_menu_title_from_handle(menu_handle),
                    items=policy_menu_items,
                )
                menu_summaries_by_handle.setdefault(menu_handle, []).append(
                    created_menu
                )
                continue

            matching_menu = matching_menus[0]
            menu_details = await self._load_menu_details(
                shop_domain=shop_domain,
                access_token=access_token,
                menu_id=matching_menu["id"],
            )
            updated_items, changed = self._apply_policy_pages_to_menu_items(
                menu_items=menu_details["items"],
                policy_pages=policy_pages,
            )
            if not changed:
                continue
            await self._update_menu(
                shop_domain=shop_domain,
                access_token=access_token,
                menu_id=menu_details["id"],
                title=menu_details["title"],
                handle=menu_details["handle"],
                items=updated_items,
            )

    async def _find_page_by_handle(
        self,
        *,
        shop_domain: str,
        access_token: str,
        handle: str,
    ) -> dict[str, str] | None:
        normalized_handle = self._normalize_policy_page_handle(handle)
        query = """
        query pagesByHandle($query: String!) {
            pages(first: 10, query: $query, sortKey: UPDATED_AT, reverse: true) {
                edges {
                    node {
                        id
                        title
                        handle
                    }
                }
            }
        }
        """
        payload = {
            "query": query,
            "variables": {"query": f"handle:{normalized_handle}"},
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        edges = ((response.get("pages") or {}).get("edges")) or []
        if not isinstance(edges, list):
            raise ShopifyApiError(message="pages query response is invalid.")

        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node")
            parsed = self._coerce_page_node(
                node=node,
                mutation_name="pages query",
            )
            if parsed["handle"].strip().lower() == normalized_handle:
                return parsed
        return None

    @staticmethod
    def _assert_no_user_errors(
        *, user_errors: list[dict[str, Any]], mutation_name: str
    ) -> None:
        if not user_errors:
            return
        messages = "; ".join(str(error.get("message")) for error in user_errors)
        raise ShopifyApiError(
            message=f"{mutation_name} failed: {messages}", status_code=409
        )

    async def _create_policy_page(
        self,
        *,
        shop_domain: str,
        access_token: str,
        title: str,
        handle: str,
        body_html: str,
    ) -> dict[str, str]:
        mutation = """
        mutation pageCreate($page: PageCreateInput!) {
                pageCreate(page: $page) {
                page {
                    id
                    title
                    handle
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": mutation,
            "variables": {
                "page": {
                    "title": title,
                    "handle": handle,
                    "body": body_html,
                }
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        create_data = response.get("pageCreate") or {}
        user_errors = create_data.get("userErrors") or []
        self._assert_no_user_errors(user_errors=user_errors, mutation_name="pageCreate")
        return self._coerce_page_node(
            node=create_data.get("page"),
            mutation_name="pageCreate",
        )

    async def _update_policy_page(
        self,
        *,
        shop_domain: str,
        access_token: str,
        page_id: str,
        title: str,
        handle: str,
        body_html: str,
    ) -> dict[str, str]:
        mutation = """
        mutation pageUpdate($id: ID!, $page: PageUpdateInput!) {
                pageUpdate(id: $id, page: $page) {
                page {
                    id
                    title
                    handle
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": mutation,
            "variables": {
                "id": page_id,
                "page": {
                    "title": title,
                    "handle": handle,
                    "body": body_html,
                },
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        update_data = response.get("pageUpdate") or {}
        user_errors = update_data.get("userErrors") or []
        self._assert_no_user_errors(user_errors=user_errors, mutation_name="pageUpdate")
        return self._coerce_page_node(
            node=update_data.get("page"),
            mutation_name="pageUpdate",
        )

    async def upsert_policy_pages(
        self,
        *,
        shop_domain: str,
        access_token: str,
        pages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        if not pages:
            raise ShopifyApiError(
                message="At least one policy page is required for sync.",
                status_code=400,
            )

        seen_page_keys: set[str] = set()
        seen_handles: set[str] = set()
        normalized_pages: list[dict[str, str]] = []
        for item in pages:
            if not isinstance(item, dict):
                raise ShopifyApiError(
                    message="Each policy page payload must be an object.",
                    status_code=400,
                )

            raw_page_key = item.get("pageKey")
            if not isinstance(raw_page_key, str) or not raw_page_key.strip():
                raise ShopifyApiError(
                    message="Each policy page requires pageKey.", status_code=400
                )
            page_key = raw_page_key.strip()
            if page_key in seen_page_keys:
                raise ShopifyApiError(
                    message=f"Duplicate pageKey in payload: {page_key}", status_code=400
                )
            seen_page_keys.add(page_key)

            raw_title = item.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ShopifyApiError(
                    message=f"Policy page '{page_key}' requires a non-empty title.",
                    status_code=400,
                )
            title = raw_title.strip()

            raw_handle = item.get("handle")
            if not isinstance(raw_handle, str):
                raise ShopifyApiError(
                    message=f"Policy page '{page_key}' requires handle.",
                    status_code=400,
                )
            handle = self._normalize_policy_page_handle(raw_handle)
            if handle in seen_handles:
                raise ShopifyApiError(
                    message=f"Duplicate page handle in payload: {handle}",
                    status_code=400,
                )
            seen_handles.add(handle)

            raw_body_html = item.get("bodyHtml")
            if not isinstance(raw_body_html, str) or not raw_body_html.strip():
                raise ShopifyApiError(
                    message=f"Policy page '{page_key}' requires non-empty bodyHtml.",
                    status_code=400,
                )
            body_html = raw_body_html.strip()

            normalized_pages.append(
                {
                    "pageKey": page_key,
                    "title": title,
                    "handle": handle,
                    "bodyHtml": body_html,
                }
            )

        results: list[dict[str, str]] = []
        for page in normalized_pages:
            existing_page = await self._find_page_by_handle(
                shop_domain=shop_domain,
                access_token=access_token,
                handle=page["handle"],
            )
            operation: Literal["created", "updated"]
            if existing_page:
                synced_page = await self._update_policy_page(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    page_id=existing_page["id"],
                    title=page["title"],
                    handle=page["handle"],
                    body_html=page["bodyHtml"],
                )
                operation = "updated"
            else:
                synced_page = await self._create_policy_page(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    title=page["title"],
                    handle=page["handle"],
                    body_html=page["bodyHtml"],
                )
                operation = "created"

            results.append(
                {
                    "pageKey": page["pageKey"],
                    "pageId": synced_page["id"],
                    "title": synced_page["title"],
                    "handle": synced_page["handle"],
                    "url": self._build_policy_page_url(
                        shop_domain=shop_domain,
                        handle=synced_page["handle"],
                    ),
                    "operation": operation,
                }
            )
        await self._sync_policy_pages_to_footer_menus(
            shop_domain=shop_domain,
            access_token=access_token,
            policy_pages=results,
        )
        return results

    @staticmethod
    def _normalize_workspace_slug(workspace_name: str) -> str:
        cleaned_workspace = workspace_name.strip().lower()
        if not cleaned_workspace:
            raise ShopifyApiError(
                message="workspaceName must be a non-empty string.", status_code=400
            )
        slug = re.sub(r"[^a-z0-9]+", "-", cleaned_workspace)
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        if not slug:
            raise ShopifyApiError(
                message="workspaceName must include at least one letter or number.",
                status_code=400,
            )
        return slug[:64].rstrip("-")

    @staticmethod
    def _normalize_css_var_key(raw_key: str) -> str:
        key = raw_key.strip()
        if not re.fullmatch(r"--[A-Za-z0-9_-]+", key):
            raise ShopifyApiError(
                message=(
                    "Invalid cssVars key. Keys must look like CSS custom properties "
                    "(for example: --color-brand)."
                ),
                status_code=400,
            )
        return key

    @staticmethod
    def _normalize_css_var_value(raw_value: str) -> str:
        value = raw_value.strip()
        if not value:
            raise ShopifyApiError(
                message="cssVars values cannot be empty.", status_code=400
            )
        if any(char in value for char in ("\n", "\r", "{", "}", ";")):
            raise ShopifyApiError(
                message="cssVars values cannot contain newlines, braces, or semicolons.",
                status_code=400,
            )
        return value

    @classmethod
    def _normalize_theme_brand_css_vars(
        cls, css_vars: dict[str, str]
    ) -> dict[str, str]:
        if not isinstance(css_vars, dict) or not css_vars:
            raise ShopifyApiError(
                message="cssVars must be a non-empty object.", status_code=400
            )

        normalized: dict[str, str] = {}
        for raw_key, raw_value in css_vars.items():
            if not isinstance(raw_key, str):
                raise ShopifyApiError(
                    message="cssVars keys must be strings.", status_code=400
                )
            if not isinstance(raw_value, str):
                raise ShopifyApiError(
                    message="cssVars values must be strings.", status_code=400
                )
            key = cls._normalize_css_var_key(raw_key)
            if key in normalized:
                raise ShopifyApiError(
                    message=f"Duplicate cssVars key after normalization: {key}",
                    status_code=400,
                )
            normalized[key] = cls._normalize_css_var_value(raw_value)
        return normalized

    @staticmethod
    def _normalize_theme_brand_font_urls(font_urls: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_url in font_urls:
            if not isinstance(raw_url, str):
                raise ShopifyApiError(
                    message="fontUrls entries must be strings.", status_code=400
                )
            url = raw_url.strip()
            if not url:
                raise ShopifyApiError(
                    message="fontUrls entries cannot be empty.", status_code=400
                )
            if not (url.startswith("https://") or url.startswith("http://")):
                raise ShopifyApiError(
                    message=f"fontUrls entry must be an absolute http(s) URL: {url}",
                    status_code=400,
                )
            if any(char in url for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"fontUrls entry contains unsupported characters: {url}",
                    status_code=400,
                )
            if url in seen:
                continue
            seen.add(url)
            normalized.append(url)
        return normalized

    @staticmethod
    def _escape_css_string(raw_value: str) -> str:
        return raw_value.replace("\\", "\\\\").replace('"', '\\"')

    @classmethod
    def _resolve_theme_brand_profile(cls, *, theme_name: str) -> ThemeBrandProfile:
        normalized_theme_name = theme_name.strip().lower()
        profile_key = _THEME_PROFILE_BY_CANONICAL_NAME.get(
            _canonicalize_theme_profile_lookup_key(normalized_theme_name),
            normalized_theme_name,
        )
        return ThemeBrandProfile(
            theme_name=profile_key,
            var_scope_selectors=_THEME_VAR_SCOPE_SELECTORS_BY_NAME.get(
                profile_key,
                _DEFAULT_THEME_VAR_SCOPE_SELECTORS,
            ),
            compat_aliases=_THEME_COMPAT_ALIASES_BY_NAME.get(profile_key, {}),
            required_source_vars=_THEME_REQUIRED_SOURCE_VARS_BY_NAME.get(
                profile_key, ()
            ),
            required_theme_vars=_THEME_REQUIRED_THEME_VARS_BY_NAME.get(profile_key, ()),
            settings_value_paths=_THEME_SETTINGS_VALUE_PATHS_BY_NAME.get(
                profile_key, {}
            ),
            required_settings_paths=_THEME_REQUIRED_SETTINGS_PATHS_BY_NAME.get(
                profile_key, ()
            ),
        )

    @staticmethod
    def _assert_theme_brand_profile_supported(
        *, theme_name: str, profile: ThemeBrandProfile
    ) -> None:
        if profile.theme_name in _SUPPORTED_THEME_PROFILE_NAMES:
            return
        supported = ", ".join(_SUPPORTED_THEME_PROFILE_NAMES)
        raise ShopifyApiError(
            message=(
                f"Unsupported theme profile for themeName={theme_name}. "
                f"Supported theme profiles: {supported}."
            ),
            status_code=422,
        )

    @classmethod
    def _build_theme_compat_css_vars(
        cls,
        *,
        profile: ThemeBrandProfile,
        css_vars: dict[str, str],
    ) -> dict[str, str]:
        if not profile.compat_aliases:
            return dict(css_vars)

        expanded = dict(css_vars)
        for source_key, alias_keys in profile.compat_aliases.items():
            if source_key not in css_vars:
                continue
            for alias_key in alias_keys:
                if alias_key in expanded:
                    continue
                expanded[alias_key] = f"var({source_key})"
        return expanded

    @classmethod
    def _build_theme_brand_coverage_summary(
        cls,
        *,
        profile: ThemeBrandProfile,
        source_css_vars: dict[str, str],
        effective_css_vars: dict[str, str],
    ) -> dict[str, list[str]]:
        missing_source_vars = sorted(
            key for key in profile.required_source_vars if key not in source_css_vars
        )
        missing_theme_vars = sorted(
            key for key in profile.required_theme_vars if key not in effective_css_vars
        )
        return {
            "requiredSourceVars": sorted(profile.required_source_vars),
            "requiredThemeVars": sorted(profile.required_theme_vars),
            "missingSourceVars": missing_source_vars,
            "missingThemeVars": missing_theme_vars,
        }

    @staticmethod
    def _assert_theme_brand_coverage_complete(
        *, theme_name: str, coverage: dict[str, list[str]]
    ) -> None:
        missing_source_vars = coverage.get("missingSourceVars") or []
        missing_theme_vars = coverage.get("missingThemeVars") or []
        if not missing_source_vars and not missing_theme_vars:
            return
        detail_parts: list[str] = [
            f"Theme profile coverage failed for themeName={theme_name}."
        ]
        if missing_source_vars:
            detail_parts.append(
                f"Missing source cssVars: {', '.join(missing_source_vars)}."
            )
        if missing_theme_vars:
            detail_parts.append(
                f"Missing mapped theme vars: {', '.join(missing_theme_vars)}."
            )
        raise ShopifyApiError(message=" ".join(detail_parts), status_code=422)

    @staticmethod
    def _parse_settings_path_tokens(path: str) -> list[tuple[str, str | None]]:
        raw_segments = [
            segment.strip() for segment in path.split(".") if segment.strip()
        ]
        if not raw_segments:
            raise ShopifyApiError(
                message=f"Invalid theme settings path: {path}", status_code=500
            )
        tokens: list[tuple[str, str | None]] = []
        for raw_segment in raw_segments:
            match = _SETTINGS_PATH_SEGMENT_RE.fullmatch(raw_segment)
            if not match:
                raise ShopifyApiError(
                    message=f"Invalid theme settings path segment: {raw_segment}",
                    status_code=500,
                )
            tokens.append((match.group(1), match.group(2)))
        return tokens

    @classmethod
    def _set_json_path_value(
        cls,
        *,
        node: Any,
        path: str,
        value: str,
        create_missing_leaf: bool = False,
    ) -> int:
        tokens = cls._parse_settings_path_tokens(path)
        return cls._set_json_path_value_tokens(
            node=node,
            tokens=tokens,
            value=value,
            create_missing_leaf=create_missing_leaf,
        )

    @classmethod
    def _set_json_path_value_tokens(
        cls,
        *,
        node: Any,
        tokens: list[tuple[str, str | None]],
        value: str,
        create_missing_leaf: bool = False,
    ) -> int:
        if not tokens or not isinstance(node, dict):
            return 0
        key, index_selector = tokens[0]
        if key not in node:
            if not create_missing_leaf:
                return 0
            if index_selector is not None:
                return 0
            if len(tokens) == 1:
                node[key] = value
                return 1
            next_index_selector = tokens[1][1]
            if next_index_selector is None:
                node[key] = {}
            else:
                return 0

        if key not in node:
            return 0

        current = node[key]
        if index_selector is None:
            if len(tokens) == 1:
                node[key] = value
                return 1
            return cls._set_json_path_value_tokens(
                node=current,
                tokens=tokens[1:],
                value=value,
                create_missing_leaf=create_missing_leaf,
            )

        if index_selector == "*":
            update_count = 0
            if isinstance(current, list):
                if not current:
                    return 0
                for idx, item in enumerate(current):
                    if len(tokens) == 1:
                        current[idx] = value
                        update_count += 1
                    else:
                        update_count += cls._set_json_path_value_tokens(
                            node=item,
                            tokens=tokens[1:],
                            value=value,
                            create_missing_leaf=create_missing_leaf,
                        )
                return update_count
            if isinstance(current, dict):
                if not current:
                    return 0
                for nested_key, item in current.items():
                    if len(tokens) == 1:
                        current[nested_key] = value
                        update_count += 1
                    else:
                        update_count += cls._set_json_path_value_tokens(
                            node=item,
                            tokens=tokens[1:],
                            value=value,
                            create_missing_leaf=create_missing_leaf,
                        )
                return update_count
            return 0

        if not isinstance(current, list):
            return 0

        index = int(index_selector)
        if index < 0 or index >= len(current):
            return 0
        if len(tokens) == 1:
            current[index] = value
            return 1
        return cls._set_json_path_value_tokens(
            node=current[index],
            tokens=tokens[1:],
            value=value,
            create_missing_leaf=create_missing_leaf,
        )

    @classmethod
    def _read_json_path_values(
        cls,
        *,
        node: Any,
        path: str,
    ) -> list[Any]:
        tokens = cls._parse_settings_path_tokens(path)
        return cls._read_json_path_values_tokens(node=node, tokens=tokens)

    @classmethod
    def _read_json_path_values_tokens(
        cls,
        *,
        node: Any,
        tokens: list[tuple[str, str | None]],
    ) -> list[Any]:
        if not tokens or not isinstance(node, dict):
            return []
        key, index_selector = tokens[0]
        if key not in node:
            return []
        current = node[key]
        if index_selector is None:
            if len(tokens) == 1:
                return [current]
            return cls._read_json_path_values_tokens(node=current, tokens=tokens[1:])

        if index_selector == "*":
            values: list[Any] = []
            if isinstance(current, list):
                for item in current:
                    if len(tokens) == 1:
                        values.append(item)
                    else:
                        values.extend(
                            cls._read_json_path_values_tokens(
                                node=item, tokens=tokens[1:]
                            )
                        )
                return values
            if isinstance(current, dict):
                for item in current.values():
                    if len(tokens) == 1:
                        values.append(item)
                    else:
                        values.extend(
                            cls._read_json_path_values_tokens(
                                node=item, tokens=tokens[1:]
                            )
                        )
                return values
            return values

        if not isinstance(current, list):
            return []

        index = int(index_selector)
        if index < 0 or index >= len(current):
            return []
        if len(tokens) == 1:
            return [current[index]]
        return cls._read_json_path_values_tokens(node=current[index], tokens=tokens[1:])

    @staticmethod
    def _build_settings_path_candidates(path: str) -> list[str]:
        candidates: list[str] = [path]
        if path.startswith("current.settings."):
            candidates.append("current." + path[len("current.settings.") :])
        elif path.startswith("current."):
            candidates.append("current.settings." + path[len("current.") :])

        schemes_settings_fragment = ".color_schemes[*].settings."
        schemes_fragment = ".color_schemes[*]."
        if schemes_settings_fragment in path:
            candidates.append(path.replace(schemes_settings_fragment, schemes_fragment))
        elif schemes_fragment in path:
            candidates.append(path.replace(schemes_fragment, schemes_settings_fragment))

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped

    @staticmethod
    def _is_non_empty_collection_node(value: Any) -> bool:
        if isinstance(value, list):
            return bool(value)
        if isinstance(value, dict):
            return bool(value)
        return False

    @classmethod
    def _extract_color_schemes_from_node(cls, node: Any) -> Any | None:
        if not isinstance(node, dict):
            return None
        direct = node.get("color_schemes")
        if cls._is_non_empty_collection_node(direct):
            return deepcopy(direct)
        nested_settings = node.get("settings")
        if isinstance(nested_settings, dict):
            nested = nested_settings.get("color_schemes")
            if cls._is_non_empty_collection_node(nested):
                return deepcopy(nested)
        return None

    @classmethod
    def _find_first_color_schemes_collection(cls, node: Any) -> Any | None:
        if isinstance(node, dict):
            direct = node.get("color_schemes")
            if cls._is_non_empty_collection_node(direct):
                return deepcopy(direct)
            for value in node.values():
                nested = cls._find_first_color_schemes_collection(value)
                if nested is not None:
                    return nested
            return None
        if isinstance(node, list):
            for item in node:
                nested = cls._find_first_color_schemes_collection(item)
                if nested is not None:
                    return nested
        return None

    @classmethod
    def _ensure_current_color_schemes(cls, *, settings_data: dict[str, Any]) -> None:
        current = settings_data.get("current")
        if not isinstance(current, dict):
            return
        if cls._is_non_empty_collection_node(current.get("color_schemes")):
            return

        from_current_settings = cls._extract_color_schemes_from_node(
            {"settings": current.get("settings")}
        )
        if from_current_settings is not None:
            current["color_schemes"] = from_current_settings
            return

        presets = settings_data.get("presets")
        if isinstance(presets, dict):
            for preset_value in presets.values():
                candidate = cls._extract_color_schemes_from_node(preset_value)
                if candidate is not None:
                    current["color_schemes"] = candidate
                    return

        discovered = cls._find_first_color_schemes_collection(settings_data)
        if discovered is not None:
            current["color_schemes"] = discovered

    @classmethod
    def _has_current_color_schemes_target(
        cls, *, settings_data: dict[str, Any]
    ) -> bool:
        current = settings_data.get("current")
        if not isinstance(current, dict):
            return False
        if cls._is_non_empty_collection_node(current.get("color_schemes")):
            return True
        nested_settings = current.get("settings")
        if isinstance(nested_settings, dict):
            return cls._is_non_empty_collection_node(
                nested_settings.get("color_schemes")
            )
        return False

    @staticmethod
    def _normalize_theme_settings_semantic_key(*, raw_key: str) -> str:
        sanitized = _THEME_SETTINGS_SEMANTIC_KEY_SANITIZE_RE.sub(
            "_", raw_key.strip().lower()
        )
        collapsed = _THEME_SETTINGS_SEMANTIC_KEY_COLLAPSE_RE.sub("_", sanitized)
        return collapsed.strip("_")

    @classmethod
    def _is_theme_settings_color_key(cls, *, key: str) -> bool:
        normalized_key = cls._normalize_theme_settings_semantic_key(raw_key=key)
        if not normalized_key:
            return False
        key_tokens = {token for token in normalized_key.split("_") if token}
        return bool(key_tokens & _THEME_SETTINGS_COLOR_KEY_MARKERS)

    @staticmethod
    def _is_theme_settings_color_like_value(*, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        normalized_value = value.strip()
        if not normalized_value:
            return False
        lowered_value = normalized_value.lower()
        if _THEME_SETTINGS_HEX_COLOR_RE.fullmatch(normalized_value):
            return True
        if _THEME_SETTINGS_CSS_COLOR_FUNCTION_RE.match(normalized_value):
            return True
        if _THEME_SETTINGS_CSS_GRADIENT_FUNCTION_RE.match(normalized_value):
            return True
        if _THEME_SETTINGS_CSS_VAR_RE.fullmatch(normalized_value):
            return True
        return lowered_value in _THEME_SETTINGS_COLOR_VALUE_KEYWORDS

    @classmethod
    def _resolve_theme_settings_semantic_key(
        cls,
        *,
        semantic_source_vars: dict[str, str],
        raw_key: str,
        raw_path: str | None = None,
    ) -> str | None:
        normalized_key = cls._normalize_theme_settings_semantic_key(raw_key=raw_key)
        if not normalized_key:
            return None
        if normalized_key in semantic_source_vars:
            return normalized_key
        key_tokens = {token for token in normalized_key.split("_") if token}
        if not key_tokens:
            return None
        path_tokens = (
            cls._tokenize_theme_settings_path(path=raw_path) if raw_path else set()
        )

        # Section-level footer components should map generic background keys to
        # the footer background semantic token, not the global page background.
        if (
            "footer_background" in semantic_source_vars
            and "footer" in path_tokens
            and ({"background", "bg"} & key_tokens)
        ):
            return "footer_background"
        if (
            "footer_text" in semantic_source_vars
            and "footer" in path_tokens
            and "newsletter" in key_tokens
            and ({"color", "text", "foreground"} & key_tokens)
        ):
            return "footer_text"
        if (
            "button" in semantic_source_vars
            and "announcement" in path_tokens
            and ({"background", "bg"} & key_tokens)
            and "border" not in key_tokens
        ):
            return "button"
        if (
            "text" in semantic_source_vars
            and "announcement" in path_tokens
            and ({"text", "foreground"} & key_tokens)
            and "color" in key_tokens
            and not ({"background", "bg", "border"} & key_tokens)
        ):
            return "text"

        # `button_color` should map to button text before generic variant matching
        # (`button`) so component text colors do not become button backgrounds.
        if (
            not normalized_key.startswith("color_")
            and "button" in key_tokens
            and "color" in key_tokens
            and not ({"bg", "background", "gradient", "border"} & key_tokens)
            and "button_text" in semantic_source_vars
        ):
            return "button_text"

        variant_candidates = (
            normalized_key.removeprefix("color_"),
            normalized_key.removesuffix("_color"),
            normalized_key.removeprefix("color_").removesuffix("_color"),
        )
        for candidate in variant_candidates:
            if candidate and candidate in semantic_source_vars:
                return candidate

        for required_tokens, semantic_key in _THEME_SETTINGS_SEMANTIC_TOKEN_RULES:
            if semantic_key not in semantic_source_vars:
                continue
            if all(token in key_tokens for token in required_tokens):
                return semantic_key
        return None

    @classmethod
    def _collect_theme_current_color_setting_leaves(
        cls,
        *,
        settings_data: dict[str, Any],
    ) -> list[tuple[dict[str, Any], str, str]]:
        current = settings_data.get("current")
        if not isinstance(current, dict):
            return []
        leaves: list[tuple[dict[str, Any], str, str]] = []

        def collect(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    child_path = f"{path}.{key}" if path else key
                    if isinstance(value, (dict, list)):
                        collect(value, child_path)
                        continue
                    if not cls._is_theme_settings_color_key(key=key):
                        continue
                    if not cls._is_theme_settings_color_like_value(value=value):
                        continue
                    leaves.append((node, key, child_path))
                return
            if isinstance(node, list):
                for index, item in enumerate(node):
                    collect(item, f"{path}[{index}]")

        collect(current, "current")
        return leaves

    @classmethod
    def _sync_theme_semantic_color_settings(
        cls,
        *,
        profile: ThemeBrandProfile,
        settings_data: dict[str, Any],
        effective_css_vars: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        semantic_source_vars = _THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME.get(
            profile.theme_name, {}
        )
        if not semantic_source_vars:
            return [], []

        updated_paths: list[str] = []
        unmapped_paths: list[str] = []
        for parent, key, path in cls._collect_theme_current_color_setting_leaves(
            settings_data=settings_data
        ):
            semantic_key = cls._resolve_theme_settings_semantic_key(
                semantic_source_vars=semantic_source_vars,
                raw_key=key,
                raw_path=path,
            )
            if semantic_key is None:
                unmapped_paths.append(path)
                continue
            source_var = semantic_source_vars[semantic_key]
            expected_value = effective_css_vars.get(source_var)
            if expected_value is None:
                raise ShopifyApiError(
                    message=(
                        f"Theme settings semantic mapping requires css var {source_var} for path {path}. "
                        "Add the missing token to the design system."
                    ),
                    status_code=422,
                )
            existing_value = parent.get(key)
            if (
                isinstance(existing_value, str)
                and existing_value.strip() == expected_value
            ):
                continue
            parent[key] = expected_value
            updated_paths.append(path)

        return sorted(set(updated_paths)), sorted(set(unmapped_paths))

    @classmethod
    def _audit_theme_semantic_color_settings(
        cls,
        *,
        profile: ThemeBrandProfile,
        settings_data: dict[str, Any],
        effective_css_vars: dict[str, str],
    ) -> tuple[list[str], list[str], list[str]]:
        semantic_source_vars = _THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME.get(
            profile.theme_name, {}
        )
        if not semantic_source_vars:
            return [], [], []

        synced_paths: list[str] = []
        mismatched_paths: list[str] = []
        unmapped_paths: list[str] = []
        for parent, key, path in cls._collect_theme_current_color_setting_leaves(
            settings_data=settings_data
        ):
            semantic_key = cls._resolve_theme_settings_semantic_key(
                semantic_source_vars=semantic_source_vars,
                raw_key=key,
                raw_path=path,
            )
            if semantic_key is None:
                unmapped_paths.append(path)
                continue
            source_var = semantic_source_vars[semantic_key]
            expected_value = effective_css_vars.get(source_var)
            if expected_value is None:
                mismatched_paths.append(path)
                continue
            existing_value = parent.get(key)
            if (
                isinstance(existing_value, str)
                and existing_value.strip() == expected_value
            ):
                synced_paths.append(path)
            else:
                mismatched_paths.append(path)

        return (
            sorted(set(synced_paths)),
            sorted(set(mismatched_paths)),
            sorted(set(unmapped_paths)),
        )

    @classmethod
    def _tokenize_theme_settings_path(cls, *, path: str) -> set[str]:
        normalized = cls._normalize_theme_settings_semantic_key(
            raw_key=path.replace(".", "_").replace("[", "_").replace("]", "_")
        )
        if not normalized:
            return set()
        return {
            token for token in normalized.split("_") if token and not token.isdigit()
        }

    @classmethod
    def _is_theme_settings_typography_leaf_candidate(
        cls,
        *,
        key: str,
        path: str,
        value: Any,
    ) -> bool:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return False
        key_tokens = cls._tokenize_theme_settings_path(path=key)
        if not key_tokens:
            return False
        if key_tokens & _THEME_SETTINGS_TYPOGRAPHY_KEY_SKIP_MARKERS:
            return False
        path_tokens = cls._tokenize_theme_settings_path(path=path)
        tokens = key_tokens | path_tokens
        if not (tokens & _THEME_SETTINGS_TYPOGRAPHY_PROPERTY_MARKERS):
            return False
        has_typography_context = bool(
            tokens & _THEME_SETTINGS_TYPOGRAPHY_CONTEXT_MARKERS
        )
        has_type_prefix = "type" in tokens or "typography" in tokens
        return has_typography_context or has_type_prefix

    @classmethod
    def _resolve_theme_settings_typography_semantic_key(
        cls,
        *,
        semantic_source_vars: dict[str, str],
        key: str,
        path: str,
    ) -> str | None:
        tokens = cls._tokenize_theme_settings_path(
            path=key
        ) | cls._tokenize_theme_settings_path(path=path)
        is_heading = bool(tokens & {"heading", "header"})
        is_body = "body" in tokens
        is_navigation = bool(tokens & {"nav", "navigation"})
        is_button = bool(tokens & {"button", "buttons"})
        is_product = bool(tokens & {"product", "grid"})

        has_font = "font" in tokens
        has_line_height = "line" in tokens and "height" in tokens
        has_letter_spacing = "letter" in tokens and "spacing" in tokens
        has_spacing = "spacing" in tokens
        has_size = "size" in tokens

        semantic_key: str | None = None
        if has_font:
            if is_heading:
                semantic_key = "heading_font"
            elif is_navigation:
                semantic_key = "navigation_font"
            elif is_button:
                semantic_key = "button_font"
            elif is_product:
                semantic_key = "product_font"
            elif is_body:
                semantic_key = "body_font"
        elif has_line_height:
            if is_heading:
                semantic_key = "heading_line_height"
            elif is_body or is_navigation or is_button or is_product:
                semantic_key = "body_line_height"
        elif has_letter_spacing:
            if is_heading:
                semantic_key = "heading_letter_spacing"
            elif is_body:
                semantic_key = "body_letter_spacing"
        elif has_spacing:
            if is_heading:
                semantic_key = "heading_letter_spacing"
            elif is_body:
                semantic_key = "body_letter_spacing"
        elif has_size:
            if is_navigation:
                semantic_key = "navigation_base_size"
            elif is_button:
                semantic_key = "button_base_size"
            elif is_product:
                semantic_key = "product_base_size"
            elif is_body:
                semantic_key = "body_base_size"

        if semantic_key is None:
            return None
        if semantic_key not in semantic_source_vars:
            return None
        return semantic_key

    @staticmethod
    def _extract_primary_font_family_from_css_value(*, raw_value: str) -> str:
        cleaned = raw_value.strip()
        if not cleaned:
            return cleaned
        if cleaned.lower().startswith("var("):
            return cleaned
        first_family = cleaned.split(",", 1)[0].strip()
        if (
            len(first_family) >= 2
            and first_family[0] == first_family[-1]
            and first_family[0] in {"'", '"'}
        ):
            first_family = first_family[1:-1].strip()
        return first_family or cleaned

    @classmethod
    def _coerce_theme_settings_font_picker_handle(
        cls,
        *,
        source_value: str,
        current_value: str,
        path: str,
    ) -> str:
        primary_family = cls._extract_primary_font_family_from_css_value(
            raw_value=source_value
        ).strip()
        normalized_family = primary_family.strip("'\" ").lower()
        alias_lookup_family = _THEME_SETTINGS_FONT_FAMILY_ALIAS_RE.sub(
            " ", normalized_family
        ).strip()
        aliased_family = _THEME_SETTINGS_FONT_FAMILY_HANDLE_ALIASES.get(
            alias_lookup_family
        )
        if aliased_family is not None:
            normalized_family = aliased_family
        if not normalized_family:
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} requires a non-empty font family, "
                    f"received {source_value!r}."
                ),
                status_code=422,
            )
        if normalized_family.startswith("var("):
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} requires an explicit font family, "
                    f"received {source_value!r}."
                ),
                status_code=422,
            )
        if normalized_family in _THEME_SETTINGS_GENERIC_FONT_FAMILIES:
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} requires a concrete Shopify font family, "
                    f"received generic family {primary_family!r}."
                ),
                status_code=422,
            )

        if _THEME_SETTINGS_FONT_HANDLE_RE.fullmatch(normalized_family):
            return normalized_family

        current_handle = current_value.strip().lower()
        if not _THEME_SETTINGS_FONT_HANDLE_RE.fullmatch(current_handle):
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} requires current value {current_value!r} "
                    "to be a Shopify font handle."
                ),
                status_code=422,
            )
        suffix_match = _THEME_SETTINGS_FONT_HANDLE_SUFFIX_RE.search(current_handle)
        if suffix_match is None:
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} requires current value {current_value!r} "
                    "to be a Shopify font handle."
                ),
                status_code=422,
            )
        base_handle = _THEME_SETTINGS_FONT_HANDLE_SANITIZE_RE.sub(
            "_", normalized_family
        )
        base_handle = base_handle.strip("_")
        if not base_handle:
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} could not derive a Shopify font handle "
                    f"from family {primary_family!r}."
                ),
                status_code=422,
            )
        current_base_handle = current_handle[: suffix_match.start()].strip("_")
        if base_handle == current_base_handle:
            return current_handle
        if aliased_family is not None:
            return f"{base_handle}{suffix_match.group(0)}"
        if base_handle != current_base_handle:
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} cannot map family {primary_family!r} "
                    f"to a known Shopify font handle. Current Shopify handle is {current_value!r}. "
                    "Provide a valid Shopify font handle in the design token (for example, inter_n4)."
                ),
                status_code=422,
            )
        return current_handle

    @staticmethod
    def _parse_simple_numeric_css_value(
        *, raw_value: str
    ) -> tuple[float, str | None] | None:
        match = _THEME_SETTINGS_SIMPLE_NUMBER_RE.fullmatch(raw_value.strip())
        if match is None:
            return None
        unit = match.group(2)
        return float(match.group(1)), unit.lower() if unit else None

    @classmethod
    def _coerce_theme_settings_typography_value(
        cls,
        *,
        semantic_key: str,
        source_value: str,
        current_value: Any,
        path: str,
    ) -> Any:
        if semantic_key.endswith("_font"):
            if not isinstance(current_value, str):
                raise ShopifyApiError(
                    message=(
                        f"Theme settings typography path {path} has unsupported font value type "
                        f"{type(current_value).__name__}."
                    ),
                    status_code=422,
                )
            normalized_current = current_value.strip().lower()
            if normalized_current in {"body", "heading"}:
                return "heading" if semantic_key == "heading_font" else "body"
            return cls._coerce_theme_settings_font_picker_handle(
                source_value=source_value,
                current_value=current_value,
                path=path,
            )

        parsed_numeric = cls._parse_simple_numeric_css_value(raw_value=source_value)
        if parsed_numeric is None:
            raise ShopifyApiError(
                message=(
                    f"Theme settings typography mapping for path {path} requires a simple numeric source value, "
                    f"received {source_value!r}."
                ),
                status_code=422,
            )
        numeric_value, numeric_unit = parsed_numeric

        if semantic_key.endswith("letter_spacing"):
            converted_value = numeric_value
            if numeric_unit in {"em", "rem"}:
                converted_value = numeric_value * 1000
            coerced_int = int(round(converted_value))
            if isinstance(current_value, str):
                return str(coerced_int)
            return coerced_int

        if semantic_key.endswith("line_height"):
            if isinstance(current_value, str):
                return f"{numeric_value:g}"
            return float(numeric_value)

        if semantic_key.endswith("base_size"):
            coerced_size = int(round(numeric_value))
            if isinstance(current_value, str):
                cleaned_current = current_value.strip().lower()
                if cleaned_current.endswith("px"):
                    return f"{coerced_size}px"
                return str(coerced_size)
            return coerced_size

        if isinstance(current_value, str):
            return f"{numeric_value:g}"
        if isinstance(current_value, int):
            return int(round(numeric_value))
        if isinstance(current_value, float):
            return float(numeric_value)
        raise ShopifyApiError(
            message=f"Theme settings typography path {path} has unsupported value type {type(current_value).__name__}.",
            status_code=422,
        )

    @classmethod
    def _sync_theme_semantic_typography_settings(
        cls,
        *,
        profile: ThemeBrandProfile,
        settings_data: dict[str, Any],
        effective_css_vars: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        semantic_source_vars = _THEME_SETTINGS_TYPOGRAPHY_SOURCE_VARS_BY_NAME.get(
            profile.theme_name, {}
        )
        if not semantic_source_vars:
            return [], []

        current = settings_data.get("current")
        if not isinstance(current, dict):
            return [], []

        updated_paths: list[str] = []
        unmapped_paths: list[str] = []

        def walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    child_path = f"{path}.{key}" if path else key
                    if isinstance(value, (dict, list)):
                        walk(value, child_path)
                        continue
                    if not cls._is_theme_settings_typography_leaf_candidate(
                        key=key, path=child_path, value=value
                    ):
                        continue
                    semantic_key = cls._resolve_theme_settings_typography_semantic_key(
                        semantic_source_vars=semantic_source_vars,
                        key=key,
                        path=child_path,
                    )
                    if semantic_key is None:
                        unmapped_paths.append(child_path)
                        continue
                    source_var = semantic_source_vars[semantic_key]
                    source_value = effective_css_vars.get(source_var)
                    if source_value is None:
                        raise ShopifyApiError(
                            message=(
                                f"Theme settings typography mapping requires css var {source_var} for path {child_path}. "
                                "Add the missing token to the design system."
                            ),
                            status_code=422,
                        )
                    expected_value = cls._coerce_theme_settings_typography_value(
                        semantic_key=semantic_key,
                        source_value=source_value,
                        current_value=value,
                        path=child_path,
                    )
                    if value == expected_value:
                        continue
                    node[key] = expected_value
                    updated_paths.append(child_path)
                return
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    walk(item, f"{path}[{idx}]")

        walk(current, "current")
        return sorted(set(updated_paths)), sorted(set(unmapped_paths))

    @classmethod
    def _audit_theme_semantic_typography_settings(
        cls,
        *,
        profile: ThemeBrandProfile,
        settings_data: dict[str, Any],
        effective_css_vars: dict[str, str],
    ) -> tuple[list[str], list[str], list[str]]:
        semantic_source_vars = _THEME_SETTINGS_TYPOGRAPHY_SOURCE_VARS_BY_NAME.get(
            profile.theme_name, {}
        )
        if not semantic_source_vars:
            return [], [], []

        current = settings_data.get("current")
        if not isinstance(current, dict):
            return [], [], []

        synced_paths: list[str] = []
        mismatched_paths: list[str] = []
        unmapped_paths: list[str] = []

        def walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    child_path = f"{path}.{key}" if path else key
                    if isinstance(value, (dict, list)):
                        walk(value, child_path)
                        continue
                    if not cls._is_theme_settings_typography_leaf_candidate(
                        key=key, path=child_path, value=value
                    ):
                        continue
                    semantic_key = cls._resolve_theme_settings_typography_semantic_key(
                        semantic_source_vars=semantic_source_vars,
                        key=key,
                        path=child_path,
                    )
                    if semantic_key is None:
                        unmapped_paths.append(child_path)
                        continue
                    source_var = semantic_source_vars[semantic_key]
                    source_value = effective_css_vars.get(source_var)
                    if source_value is None:
                        mismatched_paths.append(child_path)
                        continue
                    expected_value = cls._coerce_theme_settings_typography_value(
                        semantic_key=semantic_key,
                        source_value=source_value,
                        current_value=value,
                        path=child_path,
                    )
                    if value == expected_value:
                        synced_paths.append(child_path)
                    else:
                        mismatched_paths.append(child_path)
                return
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    walk(item, f"{path}[{idx}]")

        walk(current, "current")
        return (
            sorted(set(synced_paths)),
            sorted(set(mismatched_paths)),
            sorted(set(unmapped_paths)),
        )

    @staticmethod
    def _is_theme_component_settings_sync_enabled_for_profile(
        *, profile: ThemeBrandProfile
    ) -> bool:
        return profile.theme_name in _THEME_COMPONENT_SETTINGS_SYNC_THEME_NAMES

    @staticmethod
    def _parse_theme_template_json(
        *, filename: str, template_content: str
    ) -> dict[str, Any]:
        # Shopify template JSON files may include a UTF-8 BOM and a leading
        # autogenerated comment block before the JSON object.
        normalized_content = (
            template_content[1:]
            if template_content.startswith("\ufeff")
            else template_content
        )
        parse_content = normalized_content.lstrip()
        if parse_content.startswith("/*"):
            comment_end = parse_content.find("*/")
            if comment_end < 0:
                raise ShopifyApiError(
                    message=f"Theme template file {filename} contains an unterminated leading comment block.",
                    status_code=409,
                )
            parse_content = parse_content[comment_end + 2 :].lstrip()
        if not parse_content:
            raise ShopifyApiError(
                message=f"Theme template file {filename} is empty or whitespace-only.",
                status_code=409,
            )
        try:
            parsed = json.loads(parse_content)
        except ValueError as exc:
            prefix = parse_content[:80].encode("unicode_escape").decode("ascii")
            raise ShopifyApiError(
                message=(
                    f"Theme template file {filename} is not valid JSON. "
                    f"parserError={exc}. contentLength={len(parse_content)}. contentPrefix={prefix}"
                ),
                status_code=409,
            ) from exc
        if not isinstance(parsed, dict):
            raise ShopifyApiError(
                message=f"Theme template file {filename} must contain a JSON object.",
                status_code=409,
            )
        sections = parsed.get("sections")
        if sections is not None and not isinstance(sections, dict):
            raise ShopifyApiError(
                message=f"Theme template file {filename} has an invalid sections payload; expected an object.",
                status_code=409,
            )
        return parsed

    @classmethod
    def _collect_theme_template_color_setting_leaves(
        cls,
        *,
        template_filename: str,
        template_data: dict[str, Any],
    ) -> list[tuple[dict[str, Any], str, str]]:
        sections = template_data.get("sections")
        if not isinstance(sections, dict):
            return []

        leaves: list[tuple[dict[str, Any], str, str]] = []

        def collect(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    child_path = f"{path}.{key}" if path else key
                    if isinstance(value, (dict, list)):
                        collect(value, child_path)
                        continue
                    if not cls._is_theme_settings_color_key(key=key):
                        continue
                    if not cls._is_theme_settings_color_like_value(value=value):
                        continue
                    leaves.append((node, key, child_path))
                return
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    collect(item, f"{path}[{idx}]")

        for section_id, section in sections.items():
            if not isinstance(section_id, str) or not isinstance(section, dict):
                continue
            section_settings = section.get("settings")
            if isinstance(section_settings, dict):
                collect(
                    section_settings,
                    f"{template_filename}.sections.{section_id}.settings",
                )

            section_blocks = section.get("blocks")
            if not isinstance(section_blocks, dict):
                continue
            for block_id, block in section_blocks.items():
                if not isinstance(block_id, str) or not isinstance(block, dict):
                    continue
                block_settings = block.get("settings")
                if isinstance(block_settings, dict):
                    collect(
                        block_settings,
                        f"{template_filename}.sections.{section_id}.blocks.{block_id}.settings",
                    )

        return leaves

    @classmethod
    def _sync_theme_template_color_settings_data(
        cls,
        *,
        profile: ThemeBrandProfile,
        template_filename: str,
        template_content: str,
        effective_css_vars: dict[str, str],
    ) -> tuple[str, dict[str, Any]]:
        report = {
            "templateFilename": template_filename,
            "updatedPaths": [],
            "unmappedColorPaths": [],
        }
        semantic_source_vars = _THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME.get(
            profile.theme_name, {}
        )
        if not semantic_source_vars:
            return template_content, report

        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )

        updated_paths: list[str] = []
        unmapped_paths: list[str] = []
        leaves = cls._collect_theme_template_color_setting_leaves(
            template_filename=template_filename,
            template_data=template_data,
        )
        for parent, key, path in leaves:
            semantic_key = cls._resolve_theme_settings_semantic_key(
                semantic_source_vars=semantic_source_vars,
                raw_key=key,
                raw_path=path,
            )
            if semantic_key is None:
                unmapped_paths.append(path)
                continue
            source_var = semantic_source_vars[semantic_key]
            expected_value = effective_css_vars.get(source_var)
            if expected_value is None:
                raise ShopifyApiError(
                    message=(
                        f"Theme template settings mapping requires css var {source_var} for path {path}. "
                        "Add the missing token to the design system."
                    ),
                    status_code=422,
                )
            existing_value = parent.get(key)
            if (
                isinstance(existing_value, str)
                and existing_value.strip() == expected_value
            ):
                continue
            parent[key] = expected_value
            updated_paths.append(path)

        report["updatedPaths"] = sorted(set(updated_paths))
        report["unmappedColorPaths"] = sorted(set(unmapped_paths))
        if not updated_paths:
            return template_content, report
        return (
            json.dumps(template_data, ensure_ascii=False, separators=(",", ":")) + "\n",
            report,
        )

    @classmethod
    def _audit_theme_template_color_settings_data(
        cls,
        *,
        profile: ThemeBrandProfile,
        template_filename: str,
        template_content: str,
        effective_css_vars: dict[str, str],
    ) -> dict[str, Any]:
        report = {
            "templateFilename": template_filename,
            "syncedPaths": [],
            "mismatchedPaths": [],
            "unmappedColorPaths": [],
        }
        semantic_source_vars = _THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME.get(
            profile.theme_name, {}
        )
        if not semantic_source_vars:
            return report

        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )

        synced_paths: list[str] = []
        mismatched_paths: list[str] = []
        unmapped_paths: list[str] = []
        leaves = cls._collect_theme_template_color_setting_leaves(
            template_filename=template_filename,
            template_data=template_data,
        )
        for parent, key, path in leaves:
            semantic_key = cls._resolve_theme_settings_semantic_key(
                semantic_source_vars=semantic_source_vars,
                raw_key=key,
                raw_path=path,
            )
            if semantic_key is None:
                unmapped_paths.append(path)
                continue
            source_var = semantic_source_vars[semantic_key]
            expected_value = effective_css_vars.get(source_var)
            if expected_value is None:
                mismatched_paths.append(path)
                continue
            existing_value = parent.get(key)
            if (
                isinstance(existing_value, str)
                and existing_value.strip() == expected_value
            ):
                synced_paths.append(path)
            else:
                mismatched_paths.append(path)

        report["syncedPaths"] = sorted(set(synced_paths))
        report["mismatchedPaths"] = sorted(set(mismatched_paths))
        report["unmappedColorPaths"] = sorted(set(unmapped_paths))
        return report

    @classmethod
    def _split_theme_template_setting_path(
        cls, *, setting_path: str
    ) -> tuple[str, str]:
        delimiter_index = setting_path.find(".json.")
        if delimiter_index < 0:
            raise ShopifyApiError(
                message=(
                    "componentImageUrls keys must include a template filename and JSON path "
                    "(for example: templates/index.json.sections.hero.settings.image)."
                ),
                status_code=400,
            )
        template_filename = setting_path[: delimiter_index + len(".json")]
        json_path = setting_path[delimiter_index + len(".json.") :]
        if not _THEME_TEMPLATE_JSON_FILENAME_RE.fullmatch(template_filename):
            raise ShopifyApiError(
                message=(
                    "componentImageUrls keys must target template/section JSON files "
                    "(for example: templates/index.json.sections.hero.settings.image)."
                ),
                status_code=400,
            )
        if not json_path:
            raise ShopifyApiError(
                message=(
                    "componentImageUrls keys must include a JSON path after the template filename "
                    "(for example: templates/index.json.sections.hero.settings.image)."
                ),
                status_code=400,
            )
        try:
            cls._parse_settings_path_tokens(json_path)
        except ShopifyApiError as exc:
            raise ShopifyApiError(
                message=f"componentImageUrls key has an invalid JSON path: {setting_path}",
                status_code=400,
            ) from exc
        return template_filename, json_path

    @classmethod
    def _normalize_theme_component_image_urls(
        cls,
        *,
        component_image_urls: dict[str, str] | None,
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_setting_path, raw_url in (component_image_urls or {}).items():
            if not isinstance(raw_setting_path, str):
                raise ShopifyApiError(
                    message="componentImageUrls keys must be strings.",
                    status_code=400,
                )
            setting_path = raw_setting_path.strip()
            if not setting_path:
                raise ShopifyApiError(
                    message="componentImageUrls keys must be non-empty strings.",
                    status_code=400,
                )
            if any(char in setting_path for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"componentImageUrls key contains unsupported characters: {setting_path!r}.",
                    status_code=400,
                )
            if any(char.isspace() for char in setting_path):
                raise ShopifyApiError(
                    message=f"componentImageUrls key must not include whitespace characters: {setting_path!r}.",
                    status_code=400,
                )
            if setting_path in normalized:
                raise ShopifyApiError(
                    message=f"Duplicate componentImageUrls key after normalization: {setting_path}.",
                    status_code=400,
                )
            cls._split_theme_template_setting_path(setting_path=setting_path)

            if not isinstance(raw_url, str):
                raise ShopifyApiError(
                    message=f"componentImageUrls[{setting_path}] must be a string URL.",
                    status_code=400,
                )
            image_url = raw_url.strip()
            if not image_url:
                raise ShopifyApiError(
                    message=f"componentImageUrls[{setting_path}] cannot be empty.",
                    status_code=400,
                )
            if any(char in image_url for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"componentImageUrls[{setting_path}] contains unsupported characters.",
                    status_code=400,
                )
            if any(char.isspace() for char in image_url):
                raise ShopifyApiError(
                    message=f"componentImageUrls[{setting_path}] must not include whitespace characters.",
                    status_code=400,
                )
            if not (
                cls._is_shopify_file_url(value=image_url)
                or image_url.startswith("https://")
                or image_url.startswith("http://")
            ):
                raise ShopifyApiError(
                    message=(
                        f"componentImageUrls[{setting_path}] must be an absolute http(s) URL "
                        "or a shopify:// URL."
                    ),
                    status_code=400,
                )
            if not cls._is_shopify_file_url(value=image_url):
                parsed = urlparse(image_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ShopifyApiError(
                        message=f"componentImageUrls[{setting_path}] must be a valid absolute http(s) URL.",
                        status_code=400,
                    )
            normalized[setting_path] = image_url

        return normalized

    @classmethod
    def _normalize_theme_component_text_values(
        cls,
        *,
        component_text_values: dict[str, str] | None,
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_setting_path, raw_value in (component_text_values or {}).items():
            if not isinstance(raw_setting_path, str):
                raise ShopifyApiError(
                    message="componentTextValues keys must be strings.",
                    status_code=400,
                )
            setting_path = raw_setting_path.strip()
            if not setting_path:
                raise ShopifyApiError(
                    message="componentTextValues keys must be non-empty strings.",
                    status_code=400,
                )
            if any(char in setting_path for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"componentTextValues key contains unsupported characters: {setting_path!r}.",
                    status_code=400,
                )
            if any(char.isspace() for char in setting_path):
                raise ShopifyApiError(
                    message=f"componentTextValues key must not include whitespace characters: {setting_path!r}.",
                    status_code=400,
                )
            if setting_path in normalized:
                raise ShopifyApiError(
                    message=f"Duplicate componentTextValues key after normalization: {setting_path}.",
                    status_code=400,
                )
            cls._split_theme_template_setting_path(setting_path=setting_path)

            if not isinstance(raw_value, str):
                raise ShopifyApiError(
                    message=f"componentTextValues[{setting_path}] must be a string value.",
                    status_code=400,
                )
            text_value = raw_value.strip()
            if not text_value:
                raise ShopifyApiError(
                    message=f"componentTextValues[{setting_path}] cannot be empty.",
                    status_code=400,
                )
            if any(char in text_value for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"componentTextValues[{setting_path}] contains unsupported characters.",
                    status_code=400,
                )
            normalized[setting_path] = text_value
        return normalized

    @classmethod
    def _normalize_theme_auto_component_image_urls(
        cls,
        *,
        auto_component_image_urls: list[str] | None,
    ) -> list[str]:
        normalized: list[str] = []
        seen_urls: set[str] = set()
        for raw_url in auto_component_image_urls or []:
            if not isinstance(raw_url, str):
                raise ShopifyApiError(
                    message="autoComponentImageUrls entries must be strings.",
                    status_code=400,
                )
            image_url = raw_url.strip()
            if not image_url:
                raise ShopifyApiError(
                    message="autoComponentImageUrls entries cannot be empty.",
                    status_code=400,
                )
            if any(char in image_url for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"autoComponentImageUrls entry contains unsupported characters: {image_url}",
                    status_code=400,
                )
            if any(char.isspace() for char in image_url):
                raise ShopifyApiError(
                    message=f"autoComponentImageUrls entry must not include whitespace characters: {image_url}",
                    status_code=400,
                )
            if not (
                cls._is_shopify_file_url(value=image_url)
                or image_url.startswith("https://")
                or image_url.startswith("http://")
            ):
                raise ShopifyApiError(
                    message=(
                        "autoComponentImageUrls entries must be absolute http(s) URLs "
                        "or a shopify:// URL."
                    ),
                    status_code=400,
                )
            if not cls._is_shopify_file_url(value=image_url):
                parsed = urlparse(image_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ShopifyApiError(
                        message=f"autoComponentImageUrls entry must be a valid absolute http(s) URL: {image_url}",
                        status_code=400,
                    )
            if image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            normalized.append(image_url)
        return normalized

    @classmethod
    def _is_theme_template_component_image_setting_key(cls, *, key: str) -> bool:
        normalized_key = cls._normalize_theme_settings_semantic_key(raw_key=key)
        if not normalized_key:
            return False
        key_tokens = {token for token in normalized_key.split("_") if token}
        if not key_tokens:
            return False
        if not (key_tokens & _THEME_COMPONENT_IMAGE_KEY_MARKERS):
            return False
        if key_tokens & _THEME_COMPONENT_IMAGE_KEY_SKIP_MARKERS:
            return False
        return True

    @classmethod
    def _is_theme_template_component_image_setting_value(cls, *, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        normalized_value = value.strip()
        if not normalized_value:
            return False
        lowered_value = normalized_value.lower()
        if cls._is_shopify_file_url(value=normalized_value):
            return True
        if _THEME_SETTINGS_HEX_COLOR_RE.fullmatch(normalized_value):
            return False
        if _THEME_SETTINGS_CSS_COLOR_FUNCTION_RE.match(normalized_value):
            return False
        if _THEME_SETTINGS_CSS_GRADIENT_FUNCTION_RE.match(normalized_value):
            return False
        if lowered_value in _THEME_SETTINGS_COLOR_VALUE_KEYWORDS:
            return False
        parsed = urlparse(normalized_value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return True
        if _THEME_COMPONENT_IMAGE_FILENAME_RE.search(parsed.path):
            return True
        return False

    @classmethod
    def _infer_theme_template_image_slot_role(cls, *, path: str, key: str) -> str:
        path_tokens = cls._tokenize_theme_settings_path(path=path)
        key_tokens = {
            token
            for token in cls._normalize_theme_settings_semantic_key(raw_key=key).split(
                "_"
            )
            if token
        }
        tokens = path_tokens | key_tokens
        if {"hero", "banner", "slideshow"} & tokens:
            return "hero"
        if {"background", "bg", "overlay"} & tokens:
            return "background"
        if {"gallery", "thumb", "thumbnail", "product"} & tokens:
            return "gallery"
        if {"feature", "benefit", "card"} & tokens:
            return "supporting"
        return "generic"

    @classmethod
    def _infer_theme_template_image_recommended_aspect(
        cls, *, path: str, key: str, role: str
    ) -> Literal["landscape", "portrait", "square", "any"]:
        path_tokens = cls._tokenize_theme_settings_path(path=path)
        key_tokens = {
            token
            for token in cls._normalize_theme_settings_semantic_key(raw_key=key).split(
                "_"
            )
            if token
        }
        tokens = path_tokens | key_tokens
        if role in {"hero", "background"}:
            return "landscape"
        if {"portrait", "vertical"} & tokens:
            return "portrait"
        if {"icon", "avatar", "logo", "badge"} & tokens:
            return "square"
        if role == "gallery":
            if {"card", "feature", "benefit"} & tokens:
                return "portrait"
            return "landscape"
        return "any"

    @classmethod
    def _is_theme_template_component_text_setting_key(cls, *, key: str) -> bool:
        normalized_key = cls._normalize_theme_settings_semantic_key(raw_key=key)
        if not normalized_key:
            return False
        key_tokens = {token for token in normalized_key.split("_") if token}
        if not key_tokens:
            return False
        if not (key_tokens & _THEME_COMPONENT_TEXT_KEY_MARKERS):
            return False
        if key_tokens & _THEME_COMPONENT_TEXT_KEY_SKIP_MARKERS:
            return False
        return True

    @classmethod
    def _is_theme_template_component_text_setting_value(cls, *, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        normalized_value = value.strip()
        if not normalized_value:
            return False
        if len(normalized_value) > 280:
            return False
        lowered_value = normalized_value.lower()
        if _THEME_COMPONENT_TEXT_VALUE_SKIP_RE.match(normalized_value):
            return False
        if normalized_value.startswith("{{") or "}}" in normalized_value:
            return False
        if lowered_value.startswith("t:"):
            return False
        return True

    @classmethod
    def _infer_theme_template_text_slot_role(cls, *, path: str, key: str) -> str:
        path_tokens = cls._tokenize_theme_settings_path(path=path)
        key_tokens = {
            token
            for token in cls._normalize_theme_settings_semantic_key(raw_key=key).split(
                "_"
            )
            if token
        }
        tokens = path_tokens | key_tokens
        if {"button", "cta", "label"} & tokens:
            return "cta"
        if {"title", "heading", "headline"} & tokens:
            return "headline"
        if {
            "subtitle",
            "subheading",
            "description",
            "copy",
            "content",
            "body",
        } & tokens:
            return "body"
        if {"caption", "message", "benefit", "feature"} & tokens:
            return "supporting"
        return "generic"

    @classmethod
    def _infer_theme_template_text_slot_max_length(cls, *, role: str) -> int:
        if role == "cta":
            return 28
        if role == "headline":
            return 90
        if role == "body":
            return 220
        if role == "supporting":
            return 120
        return 120

    @classmethod
    def _collect_theme_template_component_image_slots(
        cls,
        *,
        template_filename: str,
        template_content: str,
        excluded_setting_paths: set[str],
    ) -> list[dict[str, Any]]:
        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )
        sections = template_data.get("sections")
        if not isinstance(sections, dict):
            return []

        slots: list[dict[str, Any]] = []

        def collect(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    child_path = f"{path}.{key}" if path else key
                    if isinstance(value, (dict, list)):
                        collect(value, child_path)
                        continue
                    if child_path in excluded_setting_paths:
                        continue
                    if not cls._is_theme_template_component_image_setting_key(key=key):
                        continue
                    if not cls._is_theme_template_component_image_setting_value(
                        value=value
                    ):
                        continue
                    role = cls._infer_theme_template_image_slot_role(
                        path=child_path,
                        key=key,
                    )
                    slots.append(
                        {
                            "path": child_path,
                            "key": key,
                            "currentValue": (
                                value.strip() if isinstance(value, str) else None
                            ),
                            "role": role,
                            "recommendedAspect": cls._infer_theme_template_image_recommended_aspect(
                                path=child_path,
                                key=key,
                                role=role,
                            ),
                        }
                    )
                return
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    collect(item, f"{path}[{idx}]")

        for section_id, section in sections.items():
            if not isinstance(section_id, str) or not isinstance(section, dict):
                continue
            section_settings = section.get("settings")
            if isinstance(section_settings, dict):
                collect(
                    section_settings,
                    f"{template_filename}.sections.{section_id}.settings",
                )

            section_blocks = section.get("blocks")
            if not isinstance(section_blocks, dict):
                continue
            for block_id, block in section_blocks.items():
                if not isinstance(block_id, str) or not isinstance(block, dict):
                    continue
                block_settings = block.get("settings")
                if isinstance(block_settings, dict):
                    collect(
                        block_settings,
                        f"{template_filename}.sections.{section_id}.blocks.{block_id}.settings",
                    )

        deduped_by_path: dict[str, dict[str, Any]] = {}
        for slot in slots:
            deduped_by_path[str(slot["path"])] = slot
        return [deduped_by_path[path] for path in sorted(deduped_by_path.keys())]

    @classmethod
    def _collect_theme_template_component_image_setting_paths(
        cls,
        *,
        template_filename: str,
        template_content: str,
        excluded_setting_paths: set[str],
    ) -> list[str]:
        return [
            str(slot["path"])
            for slot in cls._collect_theme_template_component_image_slots(
                template_filename=template_filename,
                template_content=template_content,
                excluded_setting_paths=excluded_setting_paths,
            )
        ]

    @classmethod
    def _collect_theme_template_component_text_slots(
        cls,
        *,
        template_filename: str,
        template_content: str,
        excluded_setting_paths: set[str],
    ) -> list[dict[str, Any]]:
        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )
        sections = template_data.get("sections")
        if not isinstance(sections, dict):
            return []

        slots: list[dict[str, Any]] = []

        def collect(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    child_path = f"{path}.{key}" if path else key
                    if isinstance(value, (dict, list)):
                        collect(value, child_path)
                        continue
                    if child_path in excluded_setting_paths:
                        continue
                    if not cls._is_theme_template_component_text_setting_key(key=key):
                        continue
                    if not cls._is_theme_template_component_text_setting_value(
                        value=value
                    ):
                        continue
                    role = cls._infer_theme_template_text_slot_role(
                        path=child_path,
                        key=key,
                    )
                    slots.append(
                        {
                            "path": child_path,
                            "key": key,
                            "currentValue": (
                                value.strip() if isinstance(value, str) else None
                            ),
                            "role": role,
                            "maxLength": cls._infer_theme_template_text_slot_max_length(
                                role=role,
                            ),
                        }
                    )
                return
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    collect(item, f"{path}[{idx}]")

        for section_id, section in sections.items():
            if not isinstance(section_id, str) or not isinstance(section, dict):
                continue
            section_settings = section.get("settings")
            if isinstance(section_settings, dict):
                collect(
                    section_settings,
                    f"{template_filename}.sections.{section_id}.settings",
                )

            section_blocks = section.get("blocks")
            if not isinstance(section_blocks, dict):
                continue
            for block_id, block in section_blocks.items():
                if not isinstance(block_id, str) or not isinstance(block, dict):
                    continue
                block_settings = block.get("settings")
                if isinstance(block_settings, dict):
                    collect(
                        block_settings,
                        f"{template_filename}.sections.{section_id}.blocks.{block_id}.settings",
                    )

        deduped_by_path: dict[str, dict[str, Any]] = {}
        for slot in slots:
            deduped_by_path[str(slot["path"])] = slot
        return [deduped_by_path[path] for path in sorted(deduped_by_path.keys())]

    @classmethod
    def _get_theme_template_slot_manifest(
        cls, *, profile: ThemeBrandProfile
    ) -> dict[str, tuple[dict[str, Any], ...]]:
        manifest = _THEME_TEMPLATE_SLOT_MANIFEST_BY_NAME.get(profile.theme_name)
        if manifest is None:
            raise ShopifyApiError(
                message=(
                    "No deterministic template slot manifest is configured for this theme profile. "
                    f"themeName={profile.theme_name}."
                ),
                status_code=409,
            )
        return manifest

    @classmethod
    def _resolve_theme_template_slots_from_manifest(
        cls,
        *,
        profile: ThemeBrandProfile,
        template_contents_by_filename: dict[str, str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        manifest = cls._get_theme_template_slot_manifest(profile=profile)
        raw_image_slots = manifest.get("imageSlots")
        raw_text_slots = manifest.get("textSlots")
        if not isinstance(raw_image_slots, tuple) or not isinstance(
            raw_text_slots, tuple
        ):
            raise ShopifyApiError(
                message=(
                    "Theme template slot manifest is invalid. "
                    f"themeName={profile.theme_name}."
                ),
                status_code=500,
            )

        parsed_templates_by_filename: dict[str, dict[str, Any]] = {}
        missing_paths: list[str] = []

        def resolve_current_value(*, setting_path: str) -> str | None:
            template_filename, json_path = cls._split_theme_template_setting_path(
                setting_path=setting_path
            )
            template_content = template_contents_by_filename.get(template_filename)
            if template_content is None:
                missing_paths.append(setting_path)
                return None
            template_data = parsed_templates_by_filename.get(template_filename)
            if template_data is None:
                template_data = cls._parse_theme_template_json(
                    filename=template_filename,
                    template_content=template_content,
                )
                parsed_templates_by_filename[template_filename] = template_data
            values = cls._read_json_path_values(node=template_data, path=json_path)
            if not values:
                missing_paths.append(setting_path)
                return None
            current_value = values[0]
            if not isinstance(current_value, str):
                return None
            normalized = current_value.strip()
            return normalized or None

        image_slots: list[dict[str, Any]] = []
        image_paths_seen: set[str] = set()
        for item in raw_image_slots:
            if not isinstance(item, dict):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid image slot entry. "
                        f"themeName={profile.theme_name}."
                    ),
                    status_code=500,
                )
            path = item.get("path")
            key = item.get("key")
            role = item.get("role")
            recommended_aspect = item.get("recommendedAspect")
            if (
                not isinstance(path, str)
                or not path.strip()
                or not isinstance(key, str)
                or not key.strip()
                or not isinstance(role, str)
                or not role.strip()
                or not isinstance(recommended_aspect, str)
                or recommended_aspect not in {"landscape", "portrait", "square", "any"}
            ):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid image slot definition. "
                        f"themeName={profile.theme_name}, slot={item}."
                    ),
                    status_code=500,
                )
            normalized_path = path.strip()
            if normalized_path in image_paths_seen:
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains duplicate image slot paths. "
                        f"themeName={profile.theme_name}, path={normalized_path}."
                    ),
                    status_code=500,
                )
            image_paths_seen.add(normalized_path)
            image_slots.append(
                {
                    "path": normalized_path,
                    "key": key.strip(),
                    "currentValue": resolve_current_value(setting_path=normalized_path),
                    "role": role.strip(),
                    "recommendedAspect": recommended_aspect,
                }
            )

        text_slots: list[dict[str, Any]] = []
        text_paths_seen: set[str] = set()
        for item in raw_text_slots:
            if not isinstance(item, dict):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid text slot entry. "
                        f"themeName={profile.theme_name}."
                    ),
                    status_code=500,
                )
            path = item.get("path")
            key = item.get("key")
            role = item.get("role")
            max_length = item.get("maxLength")
            if (
                not isinstance(path, str)
                or not path.strip()
                or not isinstance(key, str)
                or not key.strip()
                or not isinstance(role, str)
                or not role.strip()
                or not isinstance(max_length, int)
                or max_length <= 0
            ):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid text slot definition. "
                        f"themeName={profile.theme_name}, slot={item}."
                    ),
                    status_code=500,
                )
            normalized_path = path.strip()
            if normalized_path in text_paths_seen:
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains duplicate text slot paths. "
                        f"themeName={profile.theme_name}, path={normalized_path}."
                    ),
                    status_code=500,
                )
            text_paths_seen.add(normalized_path)
            text_slots.append(
                {
                    "path": normalized_path,
                    "key": key.strip(),
                    "currentValue": resolve_current_value(setting_path=normalized_path),
                    "role": role.strip(),
                    "maxLength": max_length,
                }
            )

        missing_paths = sorted(set(missing_paths))
        if missing_paths:
            raise ShopifyApiError(
                message=(
                    "Deterministic theme template slot manifest paths are missing from the current theme files. "
                    f"themeName={profile.theme_name}. missingPaths={', '.join(missing_paths)}."
                ),
                status_code=409,
            )

        return image_slots, text_slots

    @classmethod
    def _build_auto_theme_component_image_urls(
        cls,
        *,
        template_filenames: set[str],
        template_contents_by_filename: dict[str, str],
        explicit_component_image_urls: dict[str, str],
        auto_component_image_urls: list[str],
    ) -> dict[str, str]:
        if not auto_component_image_urls:
            return {}

        excluded_setting_paths = set(explicit_component_image_urls.keys())
        discovered_paths: list[str] = []
        for template_filename in sorted(template_filenames):
            template_content = template_contents_by_filename.get(template_filename)
            if template_content is None:
                raise ShopifyApiError(
                    message=f"Theme template file required for auto component image sync was not loaded: {template_filename}",
                    status_code=404,
                )
            discovered_paths.extend(
                cls._collect_theme_template_component_image_setting_paths(
                    template_filename=template_filename,
                    template_content=template_content,
                    excluded_setting_paths=excluded_setting_paths,
                )
            )
        discovered_paths = sorted(set(discovered_paths))
        if not discovered_paths:
            raise ShopifyApiError(
                message=(
                    "Theme template settings sync could not discover image setting paths for "
                    "autoComponentImageUrls. Provide explicit componentImageUrls mappings."
                ),
                status_code=422,
            )

        mapped: dict[str, str] = {}
        for index, setting_path in enumerate(discovered_paths):
            mapped[setting_path] = auto_component_image_urls[
                index % len(auto_component_image_urls)
            ]
        return mapped

    @classmethod
    def _group_theme_component_image_urls_by_template(
        cls,
        *,
        component_image_urls: dict[str, str],
    ) -> dict[str, dict[str, str]]:
        grouped: dict[str, dict[str, str]] = {}
        for setting_path, image_url in component_image_urls.items():
            template_filename, _ = cls._split_theme_template_setting_path(
                setting_path=setting_path
            )
            grouped.setdefault(template_filename, {})[setting_path] = image_url
        return grouped

    @classmethod
    def _group_theme_component_text_values_by_template(
        cls,
        *,
        component_text_values: dict[str, str],
    ) -> dict[str, dict[str, str]]:
        grouped: dict[str, dict[str, str]] = {}
        for setting_path, text_value in component_text_values.items():
            template_filename, _ = cls._split_theme_template_setting_path(
                setting_path=setting_path
            )
            grouped.setdefault(template_filename, {})[setting_path] = text_value
        return grouped

    @classmethod
    def _sync_theme_template_component_text_settings_data(
        cls,
        *,
        template_filename: str,
        template_content: str,
        component_text_values_by_path: dict[str, str],
    ) -> tuple[str, dict[str, Any]]:
        report = {
            "templateFilename": template_filename,
            "updatedPaths": [],
            "missingPaths": [],
        }
        if not component_text_values_by_path:
            return template_content, report

        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )

        updated_paths: list[str] = []
        missing_paths: list[str] = []
        for setting_path, text_value in component_text_values_by_path.items():
            parsed_template_filename, json_path = (
                cls._split_theme_template_setting_path(setting_path=setting_path)
            )
            if parsed_template_filename != template_filename:
                raise ShopifyApiError(
                    message=(
                        "componentTextValues keys must match the current template file during sync. "
                        f"path={setting_path}, templateFilename={template_filename}."
                    ),
                    status_code=500,
                )
            existing_values = cls._read_json_path_values(
                node=template_data,
                path=json_path,
            )
            resolved_text_value = cls._coerce_theme_component_text_value_for_setting(
                text_value=text_value,
                existing_values=existing_values,
            )
            update_count = cls._set_json_path_value(
                node=template_data,
                path=json_path,
                value=resolved_text_value,
                create_missing_leaf=False,
            )
            if update_count > 0:
                updated_paths.append(setting_path)
            else:
                missing_paths.append(setting_path)

        report["updatedPaths"] = sorted(set(updated_paths))
        report["missingPaths"] = sorted(set(missing_paths))
        if not updated_paths:
            return template_content, report
        return (
            json.dumps(template_data, ensure_ascii=False, separators=(",", ":")) + "\n",
            report,
        )

    @staticmethod
    def _is_theme_component_richtext_value(*, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        normalized = value.strip()
        if not normalized:
            return False
        return bool(_THEME_COMPONENT_RICHTEXT_TOP_LEVEL_TAG_RE.match(normalized))

    @classmethod
    def _coerce_theme_component_text_value_for_setting(
        cls,
        *,
        text_value: str,
        existing_values: list[Any],
    ) -> str:
        if any(
            cls._is_theme_component_richtext_value(value=value)
            for value in existing_values
        ):
            collapsed = " ".join(text_value.split()).strip()
            return f"<p>{escape(collapsed)}</p>"
        return text_value

    @classmethod
    def _sync_theme_template_component_image_settings_data(
        cls,
        *,
        template_filename: str,
        template_content: str,
        component_image_urls_by_path: dict[str, str],
    ) -> tuple[str, dict[str, Any]]:
        report = {
            "templateFilename": template_filename,
            "updatedPaths": [],
            "missingPaths": [],
        }
        if not component_image_urls_by_path:
            return template_content, report

        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )

        updated_paths: list[str] = []
        missing_paths: list[str] = []
        for setting_path, image_url in component_image_urls_by_path.items():
            parsed_template_filename, json_path = (
                cls._split_theme_template_setting_path(setting_path=setting_path)
            )
            if parsed_template_filename != template_filename:
                raise ShopifyApiError(
                    message=(
                        "componentImageUrls keys must match the current template file during sync. "
                        f"path={setting_path}, templateFilename={template_filename}."
                    ),
                    status_code=500,
                )
            update_count = cls._set_json_path_value(
                node=template_data,
                path=json_path,
                value=image_url,
                create_missing_leaf=False,
            )
            if update_count > 0:
                updated_paths.append(setting_path)
            else:
                missing_paths.append(setting_path)

        report["updatedPaths"] = sorted(set(updated_paths))
        report["missingPaths"] = sorted(set(missing_paths))
        if not updated_paths:
            return template_content, report
        return (
            json.dumps(template_data, ensure_ascii=False, separators=(",", ":")) + "\n",
            report,
        )

    @classmethod
    def _extract_footer_logo_component_setting_paths(
        cls,
        *,
        template_filename: str,
        template_content: str,
    ) -> list[str]:
        if template_filename != _THEME_FOOTER_GROUP_FILENAME:
            return []

        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )
        raw_sections = template_data.get("sections")
        if not isinstance(raw_sections, dict):
            return []

        setting_paths: list[str] = []
        for section_key, raw_section in raw_sections.items():
            if not isinstance(section_key, str) or not section_key.strip():
                continue
            if not isinstance(raw_section, dict):
                continue
            raw_type = raw_section.get("type")
            normalized_type = raw_type.strip().lower() if isinstance(raw_type, str) else ""
            normalized_section_key = section_key.strip().lower()
            if "footer" not in normalized_type and "footer" not in normalized_section_key:
                continue
            raw_settings = raw_section.get("settings")
            if not isinstance(raw_settings, dict):
                continue
            if "logo" not in raw_settings:
                continue
            setting_paths.append(
                f"{template_filename}.sections.{section_key.strip()}.settings.logo"
            )
        return sorted(set(setting_paths))

    @staticmethod
    def _parse_theme_settings_json(*, settings_content: str) -> dict[str, Any]:
        # Shopify settings_data.json may include a UTF-8 BOM and a leading
        # autogenerated comment block before the JSON object.
        normalized_content = (
            settings_content[1:]
            if settings_content.startswith("\ufeff")
            else settings_content
        )
        parse_content = normalized_content.lstrip()
        if parse_content.startswith("/*"):
            comment_end = parse_content.find("*/")
            if comment_end < 0:
                raise ShopifyApiError(
                    message=(
                        f"Theme settings file {_THEME_BRAND_SETTINGS_FILENAME} contains an unterminated "
                        "leading comment block."
                    ),
                    status_code=409,
                )
            parse_content = parse_content[comment_end + 2 :].lstrip()

        if not parse_content:
            raise ShopifyApiError(
                message=(
                    f"Theme settings file {_THEME_BRAND_SETTINGS_FILENAME} is empty or whitespace-only. "
                    "Populate it with a valid JSON object."
                ),
                status_code=409,
            )
        try:
            parsed = json.loads(parse_content)
        except ValueError as exc:
            prefix = parse_content[:80].encode("unicode_escape").decode("ascii")
            raise ShopifyApiError(
                message=(
                    f"Theme settings file {_THEME_BRAND_SETTINGS_FILENAME} is not valid JSON. "
                    f"parserError={exc}. contentLength={len(parse_content)}. contentPrefix={prefix}"
                ),
                status_code=409,
            ) from exc
        if not isinstance(parsed, dict):
            raise ShopifyApiError(
                message=f"Theme settings file {_THEME_BRAND_SETTINGS_FILENAME} must contain a JSON object.",
                status_code=409,
            )
        return parsed

    @classmethod
    def _sync_theme_settings_data(
        cls,
        *,
        profile: ThemeBrandProfile,
        settings_content: str,
        effective_css_vars: dict[str, str],
        logo_url: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        report = {
            "settingsFilename": _THEME_BRAND_SETTINGS_FILENAME,
            "expectedPaths": sorted(profile.settings_value_paths.keys()),
            "updatedPaths": [],
            "missingPaths": [],
            "requiredMissingPaths": [],
            "semanticUpdatedPaths": [],
            "unmappedColorPaths": [],
            "semanticTypographyUpdatedPaths": [],
            "unmappedTypographyPaths": [],
        }
        if not profile.settings_value_paths:
            return settings_content, report

        settings_data = cls._parse_theme_settings_json(
            settings_content=settings_content
        )
        if logo_url is not None:
            cls._sync_theme_logo_settings_data(
                settings_data=settings_data, logo_url=logo_url
            )
        cls._ensure_current_color_schemes(settings_data=settings_data)
        has_color_schemes_target = cls._has_current_color_schemes_target(
            settings_data=settings_data
        )
        expected_paths = sorted(
            path
            for path in profile.settings_value_paths.keys()
            if has_color_schemes_target or ".color_schemes[*]." not in path
        )
        report["expectedPaths"] = expected_paths

        updated_paths: list[str] = []
        missing_paths: list[str] = []
        for path in expected_paths:
            source_var = profile.settings_value_paths[path]
            expected_value = effective_css_vars.get(source_var)
            if expected_value is None:
                raise ShopifyApiError(
                    message=(
                        f"Theme settings mapping requires css var {source_var} for path {path}. "
                        "Add the missing token to the design system."
                    ),
                    status_code=422,
                )
            update_count = 0
            candidate_paths = cls._build_settings_path_candidates(path)
            for candidate_path in candidate_paths:
                candidate_update_count = cls._set_json_path_value(
                    node=settings_data,
                    path=candidate_path,
                    value=expected_value,
                    create_missing_leaf=False,
                )
                if candidate_update_count > 0:
                    update_count = candidate_update_count
                    break
            if update_count == 0:
                update_count = cls._set_json_path_value(
                    node=settings_data,
                    path=path,
                    value=expected_value,
                    create_missing_leaf=True,
                )
            if update_count:
                updated_paths.append(path)
            else:
                missing_paths.append(path)

        required_missing_paths = sorted(
            path for path in profile.required_settings_paths if path in missing_paths
        )
        if required_missing_paths:
            raise ShopifyApiError(
                message=(
                    "Theme settings sync missing required paths: "
                    f"{', '.join(required_missing_paths)}."
                ),
                status_code=409,
            )
        if missing_paths:
            raise ShopifyApiError(
                message=(
                    "Theme settings sync could not update mapped paths: "
                    f"{', '.join(sorted(missing_paths))}."
                ),
                status_code=409,
            )

        semantic_updated_paths, unmapped_color_paths = (
            cls._sync_theme_semantic_color_settings(
                profile=profile,
                settings_data=settings_data,
                effective_css_vars=effective_css_vars,
            )
        )
        if unmapped_color_paths:
            raise ShopifyApiError(
                message=(
                    "Theme settings sync discovered unmapped color setting paths: "
                    f"{', '.join(unmapped_color_paths)}. "
                    "Add semantic mappings in _THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME."
                ),
                status_code=422,
            )

        semantic_typography_updated_paths, unmapped_typography_paths = (
            cls._sync_theme_semantic_typography_settings(
                profile=profile,
                settings_data=settings_data,
                effective_css_vars=effective_css_vars,
            )
        )
        if unmapped_typography_paths:
            raise ShopifyApiError(
                message=(
                    "Theme settings sync discovered unmapped typography setting paths: "
                    f"{', '.join(unmapped_typography_paths)}. "
                    "Add semantic mappings in _THEME_SETTINGS_TYPOGRAPHY_SOURCE_VARS_BY_NAME."
                ),
                status_code=422,
            )

        report["updatedPaths"] = sorted(updated_paths)
        report["missingPaths"] = sorted(missing_paths)
        report["requiredMissingPaths"] = required_missing_paths
        report["semanticUpdatedPaths"] = sorted(
            set(semantic_updated_paths + semantic_typography_updated_paths)
        )
        report["unmappedColorPaths"] = unmapped_color_paths
        report["semanticTypographyUpdatedPaths"] = semantic_typography_updated_paths
        report["unmappedTypographyPaths"] = unmapped_typography_paths
        return json.dumps(settings_data, indent=2, ensure_ascii=False) + "\n", report

    @classmethod
    def _sync_theme_logo_settings_data(
        cls,
        *,
        settings_data: dict[str, Any],
        logo_url: str,
    ) -> list[str]:
        if not cls._is_shopify_file_url(value=logo_url):
            raise ShopifyApiError(
                message=(
                    "Theme settings logo sync requires a Shopify file URL (shopify://...) "
                    f"for logo fields, received {logo_url!r}."
                ),
                status_code=422,
            )
        current = settings_data.get("current")
        if current is None:
            current = {}
            settings_data["current"] = current
        if not isinstance(current, dict):
            raise ShopifyApiError(
                message=(
                    f"Theme settings file {_THEME_BRAND_SETTINGS_FILENAME} must contain a JSON object at current "
                    "to sync logo fields."
                ),
                status_code=409,
            )

        updated_paths: list[str] = []
        for key in ("logo", "logo_mobile"):
            existing_value = current.get(key)
            if isinstance(existing_value, str) and existing_value.strip() == logo_url:
                continue
            current[key] = logo_url
            updated_paths.append(f"current.{key}")
        return updated_paths

    @classmethod
    def _audit_theme_settings_data(
        cls,
        *,
        profile: ThemeBrandProfile,
        settings_content: str,
        effective_css_vars: dict[str, str],
    ) -> dict[str, Any]:
        report = {
            "settingsFilename": _THEME_BRAND_SETTINGS_FILENAME,
            "expectedPaths": sorted(profile.settings_value_paths.keys()),
            "syncedPaths": [],
            "mismatchedPaths": [],
            "missingPaths": [],
            "requiredMissingPaths": [],
            "requiredMismatchedPaths": [],
            "semanticSyncedPaths": [],
            "semanticMismatchedPaths": [],
            "unmappedColorPaths": [],
            "semanticTypographySyncedPaths": [],
            "semanticTypographyMismatchedPaths": [],
            "unmappedTypographyPaths": [],
        }
        if not profile.settings_value_paths:
            return report

        settings_data = cls._parse_theme_settings_json(
            settings_content=settings_content
        )
        cls._ensure_current_color_schemes(settings_data=settings_data)
        has_color_schemes_target = cls._has_current_color_schemes_target(
            settings_data=settings_data
        )
        expected_paths = sorted(
            path
            for path in profile.settings_value_paths.keys()
            if has_color_schemes_target or ".color_schemes[*]." not in path
        )
        report["expectedPaths"] = expected_paths

        synced_paths: list[str] = []
        mismatched_paths: list[str] = []
        missing_paths: list[str] = []
        for path in expected_paths:
            source_var = profile.settings_value_paths[path]
            expected_value = effective_css_vars.get(source_var)
            if expected_value is None:
                mismatched_paths.append(path)
                continue
            candidate_values: list[list[Any]] = []
            for candidate_path in cls._build_settings_path_candidates(path):
                observed_values = cls._read_json_path_values(
                    node=settings_data, path=candidate_path
                )
                if observed_values:
                    candidate_values.append(observed_values)
            if not candidate_values:
                missing_paths.append(path)
                continue
            if any(
                all(
                    isinstance(value, str) and value.strip() == expected_value
                    for value in observed_values
                )
                for observed_values in candidate_values
            ):
                synced_paths.append(path)
            else:
                mismatched_paths.append(path)

        required_missing_paths = sorted(
            path for path in profile.required_settings_paths if path in missing_paths
        )
        required_mismatched_paths = sorted(
            path for path in profile.required_settings_paths if path in mismatched_paths
        )
        semantic_synced_paths, semantic_mismatched_paths, unmapped_color_paths = (
            cls._audit_theme_semantic_color_settings(
                profile=profile,
                settings_data=settings_data,
                effective_css_vars=effective_css_vars,
            )
        )
        (
            semantic_typography_synced_paths,
            semantic_typography_mismatched_paths,
            unmapped_typography_paths,
        ) = cls._audit_theme_semantic_typography_settings(
            profile=profile,
            settings_data=settings_data,
            effective_css_vars=effective_css_vars,
        )

        report["syncedPaths"] = sorted(synced_paths)
        report["mismatchedPaths"] = sorted(mismatched_paths)
        report["missingPaths"] = sorted(missing_paths)
        report["requiredMissingPaths"] = required_missing_paths
        report["requiredMismatchedPaths"] = required_mismatched_paths
        report["semanticSyncedPaths"] = sorted(
            set(semantic_synced_paths + semantic_typography_synced_paths)
        )
        report["semanticMismatchedPaths"] = sorted(
            set(semantic_mismatched_paths + semantic_typography_mismatched_paths)
        )
        report["unmappedColorPaths"] = unmapped_color_paths
        report["semanticTypographySyncedPaths"] = semantic_typography_synced_paths
        report["semanticTypographyMismatchedPaths"] = (
            semantic_typography_mismatched_paths
        )
        report["unmappedTypographyPaths"] = unmapped_typography_paths
        return report

    @classmethod
    def _render_theme_brand_css(
        cls,
        *,
        theme_name: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        data_theme: str | None,
        css_vars: dict[str, str],
        font_urls: list[str],
        effective_css_vars: dict[str, str] | None = None,
    ) -> str:
        profile = cls._resolve_theme_brand_profile(theme_name=theme_name)
        resolved_effective_css_vars = (
            effective_css_vars
            or cls._build_theme_compat_css_vars(
                profile=profile,
                css_vars=css_vars,
            )
        )
        lines: list[str] = [
            "/* Managed by mOS workspace brand sync. */",
            f"/* Workspace: {workspace_name} */",
            f"/* Brand: {brand_name} */",
            f"/* Theme: {theme_name} */",
        ]
        if data_theme:
            lines.append(f"/* dataTheme: {data_theme} */")
        if font_urls:
            lines.append("")
            for font_url in font_urls:
                lines.append(f'@import url("{font_url}");')

        sorted_keys = sorted(resolved_effective_css_vars.keys())
        lines.extend(["", ", ".join(profile.var_scope_selectors) + " {"])
        for key in sorted_keys:
            lines.append(f"  {key}: {resolved_effective_css_vars[key]} !important;")
        lines.append(
            f'  --mos-workspace-name: "{cls._escape_css_string(workspace_name)}";'
        )
        lines.append(f'  --mos-brand-name: "{cls._escape_css_string(brand_name)}";')
        lines.append(f'  --mos-brand-logo-url: "{cls._escape_css_string(logo_url)}";')
        if data_theme:
            lines.append(f'  --mos-data-theme: "{cls._escape_css_string(data_theme)}";')
        lines.append("}")

        if data_theme:
            escaped_theme = escape(data_theme, quote=True)
            theme_scoped_selectors: list[str] = [f'html[data-theme="{escaped_theme}"]']
            for selector in profile.var_scope_selectors:
                if selector == ":root":
                    continue
                theme_scoped_selectors.append(
                    f'html[data-theme="{escaped_theme}"] {selector}'
                )
            lines.append("")
            lines.append(", ".join(theme_scoped_selectors) + " {")
            for key in sorted_keys:
                lines.append(f"  {key}: {resolved_effective_css_vars[key]} !important;")
            lines.append("}")

        component_style_overrides = _THEME_COMPONENT_STYLE_OVERRIDES_BY_NAME.get(
            profile.theme_name, ()
        )
        if component_style_overrides:
            lines.append("")
            lines.append("/* Managed theme component overrides. */")
            for selector, declarations in component_style_overrides:
                lines.append(f"{selector} {{")
                for prop, value in declarations:
                    lines.append(f"  {prop}: {value} !important;")
                lines.append("}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _render_theme_brand_liquid_block(
        *,
        css_filename: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        data_theme: str | None,
    ) -> str:
        asset_name = css_filename
        if css_filename.startswith("assets/"):
            asset_name = css_filename.split("/", 1)[1]
        block_lines = [
            _THEME_BRAND_MARKER_START,
            "{% comment %}Managed by mOS workspace brand sync. Do not edit manually.{% endcomment %}",
            f"{{{{ '{asset_name}' | asset_url | stylesheet_tag }}}}",
            f'<meta name="mos-workspace-name" content="{escape(workspace_name, quote=True)}">',
            f'<meta name="mos-brand-name" content="{escape(brand_name, quote=True)}">',
            f'<meta name="mos-brand-logo-url" content="{escape(logo_url, quote=True)}">',
        ]
        if data_theme:
            block_lines.append(
                f'<meta name="mos-data-theme" content="{escape(data_theme, quote=True)}">'
            )
        block_lines.append(_THEME_BRAND_MARKER_END)
        return "\n".join(block_lines)

    @staticmethod
    def _replace_theme_brand_liquid_block(
        *,
        layout_content: str,
        replacement_block: str,
    ) -> str:
        start_count = layout_content.count(_THEME_BRAND_MARKER_START)
        end_count = layout_content.count(_THEME_BRAND_MARKER_END)
        if start_count != 1 or end_count != 1:
            raise ShopifyApiError(
                message=(
                    "Theme layout must include exactly one managed brand marker block: "
                    f"{_THEME_BRAND_MARKER_START} ... {_THEME_BRAND_MARKER_END}"
                ),
                status_code=409,
            )

        start_idx = layout_content.find(_THEME_BRAND_MARKER_START)
        end_idx = layout_content.find(_THEME_BRAND_MARKER_END)
        if start_idx < 0 or end_idx < 0 or end_idx < start_idx:
            raise ShopifyApiError(
                message="Theme layout contains an invalid managed brand marker block.",
                status_code=409,
            )
        end_idx += len(_THEME_BRAND_MARKER_END)

        layout_without_block = f"{layout_content[:start_idx]}{layout_content[end_idx:]}"
        head_close_match = re.search(
            r"</head\s*>", layout_without_block, flags=re.IGNORECASE
        )
        if head_close_match is None:
            raise ShopifyApiError(
                message="Theme layout must include a closing </head> tag for managed brand sync.",
                status_code=409,
            )

        insertion_index = head_close_match.start()
        prefix = layout_without_block[:insertion_index]
        suffix = layout_without_block[insertion_index:]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if suffix and not suffix.startswith("\n"):
            suffix = "\n" + suffix
        return f"{prefix}{replacement_block}{suffix}"

    @staticmethod
    def _coerce_theme_data(*, node: Any, query_name: str) -> dict[str, str]:
        if not isinstance(node, dict):
            raise ShopifyApiError(
                message=f"{query_name} response is missing theme data."
            )
        theme_id = node.get("id")
        theme_name = node.get("name")
        theme_role = node.get("role")
        if not isinstance(theme_id, str) or not theme_id:
            raise ShopifyApiError(message=f"{query_name} response is missing theme.id.")
        if not isinstance(theme_name, str) or not theme_name:
            raise ShopifyApiError(
                message=f"{query_name} response is missing theme.name."
            )
        if not isinstance(theme_role, str) or not theme_role:
            raise ShopifyApiError(
                message=f"{query_name} response is missing theme.role."
            )
        return {"id": theme_id, "name": theme_name, "role": theme_role}

    async def _resolve_theme_for_brand_sync(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str | None,
        theme_name: str | None,
    ) -> dict[str, str]:
        if theme_id and theme_name:
            raise ShopifyApiError(
                message="Provide exactly one of themeId or themeName.",
                status_code=400,
            )
        if theme_id:
            query = """
            query themeById($id: ID!) {
                theme(id: $id) {
                    id
                    name
                    role
                }
            }
            """
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={"query": query, "variables": {"id": theme_id}},
            )
            theme = response.get("theme")
            if theme is None:
                raise ShopifyApiError(
                    message=f"Theme not found for themeId={theme_id}.",
                    status_code=404,
                )
            return self._coerce_theme_data(node=theme, query_name="theme")

        if theme_name:
            cleaned_theme_name = theme_name.strip()
            if not cleaned_theme_name:
                raise ShopifyApiError(
                    message="themeName cannot be empty when provided.",
                    status_code=400,
                )
            query = """
            query themesForBrandSync($first: Int!) {
                themes(first: $first) {
                    nodes {
                        id
                        name
                        role
                    }
                }
            }
            """
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={"query": query, "variables": {"first": 100}},
            )
            raw_nodes = (response.get("themes") or {}).get("nodes")
            if not isinstance(raw_nodes, list):
                raise ShopifyApiError(message="themes query response is invalid.")
            requested_name = cleaned_theme_name.lower()
            matches: list[dict[str, str]] = []
            for node in raw_nodes:
                parsed = self._coerce_theme_data(node=node, query_name="themes")
                if parsed["name"].strip().lower() == requested_name:
                    matches.append(parsed)
            if not matches:
                raise ShopifyApiError(
                    message=f"Theme not found for themeName={cleaned_theme_name}.",
                    status_code=404,
                )
            if len(matches) > 1:
                theme_ids = ", ".join(theme["id"] for theme in matches)
                raise ShopifyApiError(
                    message=(
                        f"Multiple themes matched themeName={cleaned_theme_name}. "
                        f"Provide themeId instead. matchedThemeIds={theme_ids}"
                    ),
                    status_code=409,
                )
            return matches[0]

        raise ShopifyApiError(
            message="Exactly one of themeId or themeName is required.",
            status_code=400,
        )

    async def _load_theme_file_text(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
        filename: str,
    ) -> str:
        query = """
        query themeFileByName($id: ID!, $filenames: [String!]!) {
            theme(id: $id) {
                files(first: 10, filenames: $filenames) {
                    nodes {
                        filename
                        body {
                            __typename
                            ... on OnlineStoreThemeFileBodyText {
                                content
                            }
                        }
                    }
                    userErrors {
                        code
                        filename
                    }
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": query,
                "variables": {
                    "id": theme_id,
                    "filenames": [filename],
                },
            },
        )
        theme = response.get("theme")
        if not isinstance(theme, dict):
            raise ShopifyApiError(
                message=f"Theme not found for themeId={theme_id}.", status_code=404
            )
        files = theme.get("files")
        if not isinstance(files, dict):
            raise ShopifyApiError(message="theme files query response is invalid.")
        user_errors = files.get("userErrors") or []
        if user_errors:
            details: list[str] = []
            for error in user_errors:
                if not isinstance(error, dict):
                    continue
                code = error.get("code")
                errored_filename = error.get("filename")
                if isinstance(code, str) and isinstance(errored_filename, str):
                    details.append(f"{code} ({errored_filename})")
                elif isinstance(code, str):
                    details.append(code)
                elif isinstance(errored_filename, str):
                    details.append(errored_filename)
            detail_text = "; ".join(details) if details else str(user_errors)
            raise ShopifyApiError(
                message=f"theme files query failed: {detail_text}", status_code=409
            )
        nodes = files.get("nodes")
        if not isinstance(nodes, list):
            raise ShopifyApiError(
                message="theme files query response is missing nodes."
            )

        matched_node: dict[str, Any] | None = None
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_filename = node.get("filename")
            if isinstance(node_filename, str) and node_filename == filename:
                matched_node = node
                break
        if matched_node is None:
            raise ShopifyApiError(
                message=f"Theme file not found: {filename}",
                status_code=404,
            )

        body = matched_node.get("body")
        if not isinstance(body, dict):
            raise ShopifyApiError(message=f"Theme file body is missing for {filename}.")
        typename = body.get("__typename")
        if typename != "OnlineStoreThemeFileBodyText":
            raise ShopifyApiError(
                message=(
                    f"Theme file {filename} is not text-backed (typename={typename}). "
                    "Use a text theme file for managed brand sync."
                ),
                status_code=409,
            )
        content = body.get("content")
        if not isinstance(content, str):
            raise ShopifyApiError(
                message=f"Theme file body content is missing for {filename}."
            )
        return content

    async def _list_theme_template_json_filenames(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
    ) -> list[str]:
        query = """
        query themeTemplateFilesForBrandSync($id: ID!, $first: Int!, $after: String) {
            theme(id: $id) {
                files(first: $first, after: $after) {
                    nodes {
                        filename
                        body {
                            __typename
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    userErrors {
                        code
                        filename
                    }
                }
            }
        }
        """
        template_filenames: set[str] = set()
        after: str | None = None

        for _ in range(20):
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={
                    "query": query,
                    "variables": {
                        "id": theme_id,
                        "first": 250,
                        "after": after,
                    },
                },
            )
            theme = response.get("theme")
            if not isinstance(theme, dict):
                raise ShopifyApiError(
                    message=f"Theme not found for themeId={theme_id}.", status_code=404
                )
            files = theme.get("files")
            if not isinstance(files, dict):
                raise ShopifyApiError(
                    message="theme template files query response is invalid."
                )
            user_errors = files.get("userErrors") or []
            if user_errors:
                details: list[str] = []
                for error in user_errors:
                    if not isinstance(error, dict):
                        continue
                    code = error.get("code")
                    errored_filename = error.get("filename")
                    if isinstance(code, str) and isinstance(errored_filename, str):
                        details.append(f"{code} ({errored_filename})")
                    elif isinstance(code, str):
                        details.append(code)
                    elif isinstance(errored_filename, str):
                        details.append(errored_filename)
                detail_text = "; ".join(details) if details else str(user_errors)
                raise ShopifyApiError(
                    message=f"theme template files query failed: {detail_text}",
                    status_code=409,
                )

            nodes = files.get("nodes")
            if not isinstance(nodes, list):
                raise ShopifyApiError(
                    message="theme template files query response is missing nodes."
                )
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                filename = node.get("filename")
                if not isinstance(filename, str):
                    continue
                if _THEME_TEMPLATE_JSON_FILENAME_RE.fullmatch(filename) is None:
                    continue
                body = node.get("body")
                typename = body.get("__typename") if isinstance(body, dict) else None
                if typename != "OnlineStoreThemeFileBodyText":
                    continue
                template_filenames.add(filename)

            page_info = files.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ShopifyApiError(
                    message="theme template files query response is missing pageInfo."
                )
            has_next_page = page_info.get("hasNextPage")
            if not isinstance(has_next_page, bool):
                raise ShopifyApiError(
                    message="theme template files query response is missing pageInfo.hasNextPage."
                )
            if not has_next_page:
                return sorted(template_filenames)
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor:
                raise ShopifyApiError(
                    message="theme template files query response is missing pageInfo.endCursor."
                )
            after = end_cursor

        raise ShopifyApiError(
            message=(
                "Theme template files query exceeded pagination limit while loading template settings. "
                "Reduce template file count or adjust the query pagination strategy."
            ),
            status_code=409,
        )

    async def _upsert_theme_files(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
        files: list[dict[str, str]],
    ) -> str | None:
        mutation = """
        mutation themeFilesUpsert($themeId: ID!, $files: [OnlineStoreThemeFilesUpsertFileInput!]!) {
            themeFilesUpsert(themeId: $themeId, files: $files) {
                upsertedThemeFiles {
                    filename
                }
                job {
                    id
                    done
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": mutation,
                "variables": {
                    "themeId": theme_id,
                    "files": [
                        {
                            "filename": item["filename"],
                            "body": {
                                "type": "TEXT",
                                "value": item["content"],
                            },
                        }
                        for item in files
                    ],
                },
            },
        )
        upsert_data = response.get("themeFilesUpsert") or {}
        user_errors = upsert_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(
                message=f"themeFilesUpsert failed: {messages}", status_code=409
            )

        upserted = upsert_data.get("upsertedThemeFiles")
        if not isinstance(upserted, list):
            raise ShopifyApiError(
                message="themeFilesUpsert response is missing upsertedThemeFiles."
            )
        upserted_filenames = {
            item.get("filename")
            for item in upserted
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        }
        expected_filenames = {item["filename"] for item in files}
        if expected_filenames - upserted_filenames:
            missing = ", ".join(sorted(expected_filenames - upserted_filenames))
            raise ShopifyApiError(
                message=f"themeFilesUpsert did not report updated files: {missing}"
            )

        job = upsert_data.get("job")
        if job is None:
            return None
        if not isinstance(job, dict):
            raise ShopifyApiError(
                message="themeFilesUpsert response returned invalid job metadata."
            )
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise ShopifyApiError(
                message="themeFilesUpsert response is missing job.id."
            )
        return job_id

    async def _wait_for_job_completion(
        self,
        *,
        shop_domain: str,
        access_token: str,
        job_id: str,
        poll_interval_seconds: float = 1.0,
        max_attempts: int = 30,
    ) -> None:
        query = """
        query themeFileJobStatus($id: ID!) {
            job(id: $id) {
                id
                done
            }
        }
        """
        for _ in range(max_attempts):
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={"query": query, "variables": {"id": job_id}},
            )
            job = response.get("job")
            if not isinstance(job, dict):
                raise ShopifyApiError(
                    message=f"Job not found for id={job_id}.", status_code=404
                )
            done = job.get("done")
            if not isinstance(done, bool):
                raise ShopifyApiError(
                    message=f"Job response is missing done state for id={job_id}."
                )
            if done:
                return
            await asyncio.sleep(poll_interval_seconds)

        raise ShopifyApiError(
            message=f"Timed out while waiting for theme file job {job_id} to complete.",
            status_code=504,
        )

    @staticmethod
    def _normalize_theme_selector(
        *,
        theme_id: str | None,
        theme_name: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_theme_id = (
            theme_id.strip() if isinstance(theme_id, str) and theme_id.strip() else None
        )
        normalized_theme_name = (
            theme_name.strip()
            if isinstance(theme_name, str) and theme_name.strip()
            else None
        )
        if bool(normalized_theme_id) == bool(normalized_theme_name):
            raise ShopifyApiError(
                message="Exactly one of themeId or themeName is required.",
                status_code=400,
            )
        return normalized_theme_id, normalized_theme_name

    @staticmethod
    def _normalize_theme_data_theme(data_theme: str | None) -> str | None:
        if data_theme is None:
            return None
        cleaned_data_theme = data_theme.strip()
        if not cleaned_data_theme:
            raise ShopifyApiError(
                message="dataTheme cannot be empty when provided.", status_code=400
            )
        if any(char in cleaned_data_theme for char in ('"', "'", "<", ">", "\n", "\r")):
            raise ShopifyApiError(
                message="dataTheme contains unsupported characters.",
                status_code=400,
            )
        return cleaned_data_theme

    async def _try_load_theme_file_text(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
        filename: str,
    ) -> str | None:
        try:
            return await self._load_theme_file_text(
                shop_domain=shop_domain,
                access_token=access_token,
                theme_id=theme_id,
                filename=filename,
            )
        except ShopifyApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    @staticmethod
    def _audit_theme_layout(
        *,
        layout_content: str,
        css_filename: str,
    ) -> dict[str, bool]:
        start_count = layout_content.count(_THEME_BRAND_MARKER_START)
        end_count = layout_content.count(_THEME_BRAND_MARKER_END)
        has_marker_block = start_count == 1 and end_count == 1
        asset_name = (
            css_filename.split("/", 1)[1]
            if css_filename.startswith("assets/")
            else css_filename
        )
        includes_css_asset = asset_name in layout_content
        return {
            "hasManagedMarkerBlock": has_marker_block,
            "layoutIncludesManagedCssAsset": includes_css_asset,
        }

    @staticmethod
    def _is_shopify_file_url(*, value: str) -> bool:
        return value.strip().startswith("shopify://")

    @staticmethod
    def _theme_settings_has_logo_fields(*, settings_data: dict[str, Any]) -> bool:
        current = settings_data.get("current")
        if not isinstance(current, dict):
            return False
        return "logo" in current or "logo_mobile" in current

    @staticmethod
    def _extract_filename_from_url_path(*, raw_url: str) -> str:
        parsed = urlparse(raw_url.strip())
        filename = parsed.path.rsplit("/", 1)[-1].strip()
        if not filename:
            raise ShopifyApiError(
                message=f"Unable to determine uploaded logo filename from url={raw_url!r}.",
                status_code=409,
            )
        if any(
            char in filename for char in ('"', "'", "<", ">", "\n", "\r", "/", "\\")
        ):
            raise ShopifyApiError(
                message=f"Uploaded logo filename contains unsupported characters: {filename!r}.",
                status_code=409,
            )
        return filename

    @classmethod
    def _build_shopify_logo_reference_from_file_url(cls, *, file_url: str) -> str:
        filename = cls._extract_filename_from_url_path(raw_url=file_url)
        return f"shopify://shop_images/{filename}"

    @staticmethod
    def _normalize_http_content_type(*, value: str | None) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.split(";", 1)[0].strip().lower()
        if not normalized:
            return None
        return normalized

    @classmethod
    def _resolve_logo_upload_metadata(
        cls,
        *,
        source_url: str,
        response_content_type: str | None,
    ) -> tuple[str, str]:
        filename = cls._extract_filename_from_url_path(raw_url=source_url)
        normalized_content_type = cls._normalize_http_content_type(
            value=response_content_type
        )
        guessed_content_type, _ = mimetypes.guess_type(filename)
        mime_type = normalized_content_type or guessed_content_type
        if not isinstance(mime_type, str):
            raise ShopifyApiError(
                message=(
                    "Unable to determine logo content type. "
                    f"sourceUrl={source_url!r}, responseContentType={response_content_type!r}."
                ),
                status_code=409,
            )
        mime_type = mime_type.lower()
        if not mime_type.startswith("image/"):
            raise ShopifyApiError(
                message=f"Logo source must be an image content type, received {mime_type!r}.",
                status_code=409,
            )
        if "." not in filename:
            extension = mimetypes.guess_extension(mime_type, strict=False)
            if not isinstance(extension, str) or not extension.startswith("."):
                raise ShopifyApiError(
                    message=(
                        "Unable to determine file extension for logo upload. "
                        f"mimeType={mime_type!r}, sourceUrl={source_url!r}."
                    ),
                    status_code=409,
                )
            filename = f"{filename}{extension}"
        return filename, mime_type

    async def _download_logo_source_file(
        self,
        *,
        logo_url: str,
    ) -> tuple[bytes, str | None]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True
            ) as client:
                response = await client.get(logo_url)
        except httpx.InvalidURL as exc:
            raise ShopifyApiError(
                message=f"logoUrl is not a valid URL for logo download: {logo_url!r}.",
                status_code=400,
            ) from exc
        except httpx.RequestError as exc:
            raise ShopifyApiError(
                message=f"Network error while downloading logo source URL: {exc}",
                status_code=409,
            ) from exc

        if response.status_code >= 400:
            raise ShopifyApiError(
                message=f"Logo source download failed ({response.status_code}) for url={logo_url!r}.",
                status_code=409,
            )

        content = response.content
        if not content:
            raise ShopifyApiError(
                message=f"Logo source download returned empty content for url={logo_url!r}.",
                status_code=409,
            )
        if len(content) > _THEME_LOGO_UPLOAD_MAX_BYTES:
            raise ShopifyApiError(
                message=(
                    "Logo source download exceeded maximum upload size. "
                    f"size={len(content)}, max={_THEME_LOGO_UPLOAD_MAX_BYTES}, url={logo_url!r}."
                ),
                status_code=409,
            )

        content_type = self._normalize_http_content_type(
            value=response.headers.get("Content-Type")
        )
        return content, content_type

    async def _create_logo_staged_upload_target(
        self,
        *,
        shop_domain: str,
        access_token: str,
        filename: str,
        mime_type: str,
        file_size: int,
    ) -> tuple[str, str, list[tuple[str, str]]]:
        mutation = """
        mutation createThemeLogoStagedUpload($input: [StagedUploadInput!]!) {
            stagedUploadsCreate(input: $input) {
                stagedTargets {
                    url
                    resourceUrl
                    parameters {
                        name
                        value
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": mutation,
                "variables": {
                    "input": [
                        {
                            "resource": "IMAGE",
                            "filename": filename,
                            "mimeType": mime_type,
                            "httpMethod": "POST",
                            "fileSize": str(file_size),
                        }
                    ]
                },
            },
        )
        staged_uploads_data = response.get("stagedUploadsCreate")
        if not isinstance(staged_uploads_data, dict):
            raise ShopifyApiError(
                message="stagedUploadsCreate response is missing stagedUploadsCreate payload.",
                status_code=409,
            )
        user_errors = staged_uploads_data.get("userErrors") or []
        if user_errors:
            details: list[str] = []
            for error in user_errors:
                if not isinstance(error, dict):
                    continue
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    details.append(message.strip())
            detail_text = "; ".join(details) if details else str(user_errors)
            raise ShopifyApiError(
                message=f"stagedUploadsCreate failed while preparing logo upload: {detail_text}",
                status_code=409,
            )

        staged_targets = staged_uploads_data.get("stagedTargets")
        if not isinstance(staged_targets, list) or not staged_targets:
            raise ShopifyApiError(
                message="stagedUploadsCreate response did not return stagedTargets for logo upload.",
                status_code=409,
            )
        staged_target = staged_targets[0]
        if not isinstance(staged_target, dict):
            raise ShopifyApiError(
                message="stagedUploadsCreate response returned an invalid stagedTarget entry.",
                status_code=409,
            )
        upload_url = staged_target.get("url")
        resource_url = staged_target.get("resourceUrl")
        if not isinstance(upload_url, str) or not upload_url.strip():
            raise ShopifyApiError(
                message="stagedUploadsCreate response is missing upload url for logo upload.",
                status_code=409,
            )
        if not isinstance(resource_url, str) or not resource_url.strip():
            raise ShopifyApiError(
                message="stagedUploadsCreate response is missing resourceUrl for logo upload.",
                status_code=409,
            )
        raw_parameters = staged_target.get("parameters")
        if not isinstance(raw_parameters, list) or not raw_parameters:
            raise ShopifyApiError(
                message="stagedUploadsCreate response is missing staged upload parameters for logo upload.",
                status_code=409,
            )
        parameters: list[tuple[str, str]] = []
        for raw_parameter in raw_parameters:
            if not isinstance(raw_parameter, dict):
                raise ShopifyApiError(
                    message="stagedUploadsCreate response returned an invalid staged upload parameter entry.",
                    status_code=409,
                )
            name = raw_parameter.get("name")
            value = raw_parameter.get("value")
            if not isinstance(name, str) or not name.strip():
                raise ShopifyApiError(
                    message="stagedUploadsCreate response returned a staged upload parameter without a valid name.",
                    status_code=409,
                )
            if not isinstance(value, str):
                raise ShopifyApiError(
                    message=(
                        "stagedUploadsCreate response returned a staged upload parameter without a valid value. "
                        f"parameterName={name!r}."
                    ),
                    status_code=409,
                )
            parameters.append((name, value))
        return upload_url.strip(), resource_url.strip(), parameters

    async def _upload_logo_file_to_staged_target(
        self,
        *,
        upload_url: str,
        parameters: list[tuple[str, str]],
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> None:
        form_data = self._coerce_staged_upload_form_data(parameters=parameters)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    upload_url,
                    data=form_data,
                    files={"file": (filename, content, mime_type)},
                )
        except httpx.InvalidURL as exc:
            raise ShopifyApiError(
                message=f"Shopify staged upload URL is invalid: {upload_url!r}.",
                status_code=409,
            ) from exc
        except httpx.RequestError as exc:
            raise ShopifyApiError(
                message=f"Network error while uploading logo to staged target: {exc}",
                status_code=409,
            ) from exc

        if response.status_code >= 400:
            error_prefix = response.text[:300]
            raise ShopifyApiError(
                message=(
                    "Logo staged upload request failed. "
                    f"status={response.status_code}, uploadUrl={upload_url!r}, responsePrefix={error_prefix!r}."
                ),
                status_code=409,
            )

    @staticmethod
    def _coerce_staged_upload_form_data(
        *, parameters: list[tuple[str, str]]
    ) -> dict[str, str]:
        form_data: dict[str, str] = {}
        for name, value in parameters:
            if name in form_data:
                raise ShopifyApiError(
                    message=(
                        "stagedUploadsCreate returned duplicate parameter names for logo upload. "
                        f"parameterName={name!r}."
                    ),
                    status_code=409,
                )
            form_data[name] = value
        return form_data

    @staticmethod
    def _coerce_logo_file_node(
        *, node: Any
    ) -> tuple[str | None, str | None, str | None, str | None]:
        if not isinstance(node, dict):
            return None, None, None, None
        typename = node.get("__typename")
        file_id = node.get("id") if isinstance(node.get("id"), str) else None
        file_status = (
            node.get("fileStatus") if isinstance(node.get("fileStatus"), str) else None
        )

        file_url: str | None = None
        if typename == "MediaImage":
            image = node.get("image")
            if isinstance(image, dict) and isinstance(image.get("url"), str):
                candidate = image["url"].strip()
                if candidate:
                    file_url = candidate
        elif typename == "GenericFile":
            if isinstance(node.get("url"), str):
                candidate = node["url"].strip()
                if candidate:
                    file_url = candidate

        return (
            file_id,
            file_status,
            file_url,
            typename if isinstance(typename, str) else None,
        )

    async def _wait_for_logo_file_ready_url(
        self,
        *,
        shop_domain: str,
        access_token: str,
        file_id: str,
        poll_interval_seconds: float = 1.0,
        max_attempts: int = 30,
    ) -> str:
        query = """
        query themeLogoFileStatus($id: ID!) {
            node(id: $id) {
                __typename
                ... on MediaImage {
                    id
                    fileStatus
                    image {
                        url
                    }
                }
                ... on GenericFile {
                    id
                    fileStatus
                    url
                }
            }
        }
        """
        for _ in range(max_attempts):
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={"query": query, "variables": {"id": file_id}},
            )
            node = response.get("node")
            resolved_id, file_status, file_url, typename = self._coerce_logo_file_node(
                node=node
            )
            if resolved_id is None or resolved_id != file_id:
                raise ShopifyApiError(
                    message=f"Logo upload status query returned an unexpected file node for id={file_id}.",
                    status_code=409,
                )
            if file_status is None:
                raise ShopifyApiError(
                    message=f"Logo upload status query is missing fileStatus for id={file_id}.",
                    status_code=409,
                )
            normalized_status = file_status.strip().upper()
            if normalized_status == "READY":
                if file_url is None:
                    raise ShopifyApiError(
                        message=f"Logo upload completed but no file URL was returned for id={file_id}.",
                        status_code=409,
                    )
                return file_url
            if normalized_status in {"FAILED", "ERROR"}:
                raise ShopifyApiError(
                    message=(
                        "Logo upload failed while creating Shopify file reference for theme settings. "
                        f"id={file_id}, typename={typename}, fileStatus={file_status}."
                    ),
                    status_code=409,
                )
            await asyncio.sleep(poll_interval_seconds)

        raise ShopifyApiError(
            message=(
                "Timed out waiting for logo upload file to become READY. "
                f"id={file_id}, maxAttempts={max_attempts}."
            ),
            status_code=409,
        )

    async def _create_shopify_logo_file_reference_from_url(
        self,
        *,
        shop_domain: str,
        access_token: str,
        logo_url: str,
    ) -> str:
        logo_content, response_content_type = await self._download_logo_source_file(
            logo_url=logo_url
        )
        upload_filename, upload_mime_type = self._resolve_logo_upload_metadata(
            source_url=logo_url,
            response_content_type=response_content_type,
        )
        upload_url, resource_url, upload_parameters = (
            await self._create_logo_staged_upload_target(
                shop_domain=shop_domain,
                access_token=access_token,
                filename=upload_filename,
                mime_type=upload_mime_type,
                file_size=len(logo_content),
            )
        )
        await self._upload_logo_file_to_staged_target(
            upload_url=upload_url,
            parameters=upload_parameters,
            filename=upload_filename,
            mime_type=upload_mime_type,
            content=logo_content,
        )

        mutation = """
        mutation createThemeLogoFileFromStagedUpload($files: [FileCreateInput!]!) {
            fileCreate(files: $files) {
                files {
                    __typename
                    ... on MediaImage {
                        id
                        fileStatus
                        image {
                            url
                        }
                    }
                    ... on GenericFile {
                        id
                        fileStatus
                        url
                    }
                }
                userErrors {
                    field
                    message
                    code
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": mutation,
                "variables": {
                    "files": [
                        {
                            "contentType": "IMAGE",
                            "originalSource": resource_url,
                        }
                    ]
                },
            },
        )
        create_data = response.get("fileCreate")
        if not isinstance(create_data, dict):
            raise ShopifyApiError(
                message="fileCreate response is missing fileCreate payload.",
                status_code=409,
            )
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            details: list[str] = []
            for error in user_errors:
                if not isinstance(error, dict):
                    continue
                code = error.get("code")
                message = error.get("message")
                if isinstance(code, str) and isinstance(message, str):
                    details.append(f"{code}: {message}")
                elif isinstance(message, str):
                    details.append(message)
                elif isinstance(code, str):
                    details.append(code)
            detail_text = "; ".join(details) if details else str(user_errors)
            raise ShopifyApiError(
                message=f"fileCreate failed while uploading logo: {detail_text}",
                status_code=409,
            )

        files = create_data.get("files")
        if not isinstance(files, list) or not files:
            raise ShopifyApiError(
                message="fileCreate response did not return uploaded files.",
                status_code=409,
            )
        file_id, file_status, file_url, typename = self._coerce_logo_file_node(
            node=files[0]
        )
        if file_id is None:
            raise ShopifyApiError(
                message="fileCreate response is missing uploaded file id for logo.",
                status_code=409,
            )
        if typename not in {"MediaImage", "GenericFile"}:
            raise ShopifyApiError(
                message=(
                    "fileCreate uploaded logo to an unsupported file type for theme settings. "
                    f"typename={typename}."
                ),
                status_code=409,
            )
        normalized_status = (
            file_status.strip().upper() if isinstance(file_status, str) else ""
        )
        if normalized_status == "READY" and isinstance(file_url, str):
            return self._build_shopify_logo_reference_from_file_url(file_url=file_url)
        if normalized_status in {"FAILED", "ERROR"}:
            raise ShopifyApiError(
                message=(
                    "fileCreate returned a failed status while uploading logo. "
                    f"id={file_id}, typename={typename}, fileStatus={file_status}."
                ),
                status_code=409,
            )
        ready_file_url = await self._wait_for_logo_file_ready_url(
            shop_domain=shop_domain,
            access_token=access_token,
            file_id=file_id,
        )
        return self._build_shopify_logo_reference_from_file_url(file_url=ready_file_url)

    async def list_theme_brand_template_slots(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str | None = None,
        theme_name: str | None = None,
    ) -> dict[str, Any]:
        normalized_theme_id, normalized_theme_name = self._normalize_theme_selector(
            theme_id=theme_id,
            theme_name=theme_name,
        )
        theme = await self._resolve_theme_for_brand_sync(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=normalized_theme_id,
            theme_name=normalized_theme_name,
        )
        profile = self._resolve_theme_brand_profile(theme_name=theme["name"])
        self._assert_theme_brand_profile_supported(
            theme_name=theme["name"], profile=profile
        )
        slot_manifest = self._get_theme_template_slot_manifest(profile=profile)
        manifest_paths: list[str] = []
        for slot_type in ("imageSlots", "textSlots"):
            raw_slots = slot_manifest.get(slot_type, ())
            if not isinstance(raw_slots, tuple):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest is invalid for deterministic slot discovery. "
                        f"themeName={profile.theme_name}, slotType={slot_type}."
                    ),
                    status_code=500,
                )
            for item in raw_slots:
                if not isinstance(item, dict):
                    raise ShopifyApiError(
                        message=(
                            "Theme template slot manifest contains a non-object entry. "
                            f"themeName={profile.theme_name}, slotType={slot_type}."
                        ),
                        status_code=500,
                    )
                path = item.get("path")
                if not isinstance(path, str) or not path.strip():
                    raise ShopifyApiError(
                        message=(
                            "Theme template slot manifest contains an invalid path entry. "
                            f"themeName={profile.theme_name}, slotType={slot_type}, slot={item}."
                        ),
                        status_code=500,
                    )
                manifest_paths.append(path.strip())

        if not manifest_paths:
            return {
                "themeId": theme["id"],
                "themeName": theme["name"],
                "themeRole": theme["role"],
                "imageSlots": [],
                "textSlots": [],
            }

        template_filenames = sorted(
            {
                self._split_theme_template_setting_path(setting_path=path)[0]
                for path in manifest_paths
            }
        )
        template_contents = await asyncio.gather(
            *[
                self._load_theme_file_text(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    theme_id=theme["id"],
                    filename=template_filename,
                )
                for template_filename in template_filenames
            ]
        )
        template_contents_by_filename = {
            template_filename: template_content
            for template_filename, template_content in zip(
                template_filenames, template_contents, strict=True
            )
        }
        image_slots, text_slots = self._resolve_theme_template_slots_from_manifest(
            profile=profile,
            template_contents_by_filename=template_contents_by_filename,
        )

        return {
            "themeId": theme["id"],
            "themeName": theme["name"],
            "themeRole": theme["role"],
            "imageSlots": sorted(image_slots, key=lambda item: str(item["path"])),
            "textSlots": sorted(text_slots, key=lambda item: str(item["path"])),
        }

    async def sync_theme_brand(
        self,
        *,
        shop_domain: str,
        access_token: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str],
        component_image_urls: dict[str, str] | None = None,
        component_text_values: dict[str, str] | None = None,
        auto_component_image_urls: list[str] | None = None,
        data_theme: str | None = None,
        theme_id: str | None = None,
        theme_name: str | None = None,
    ) -> dict[str, Any]:
        cleaned_workspace_name = workspace_name.strip()
        if not cleaned_workspace_name:
            raise ShopifyApiError(
                message="workspaceName must be a non-empty string.", status_code=400
            )
        cleaned_brand_name = brand_name.strip()
        if not cleaned_brand_name:
            raise ShopifyApiError(
                message="brandName must be a non-empty string.", status_code=400
            )
        cleaned_logo_url = logo_url.strip()
        if not (
            self._is_shopify_file_url(value=cleaned_logo_url)
            or cleaned_logo_url.startswith("https://")
            or cleaned_logo_url.startswith("http://")
        ):
            raise ShopifyApiError(
                message="logoUrl must be an absolute http(s) URL or a shopify:// URL.",
                status_code=400,
            )
        if any(char in cleaned_logo_url for char in ('"', "'", "<", ">", "\n", "\r")):
            raise ShopifyApiError(
                message="logoUrl contains unsupported characters.",
                status_code=400,
            )
        if any(char.isspace() for char in cleaned_logo_url):
            raise ShopifyApiError(
                message="logoUrl must not include whitespace characters.",
                status_code=400,
            )
        if not self._is_shopify_file_url(value=cleaned_logo_url):
            parsed_logo_url = urlparse(cleaned_logo_url)
            if (
                parsed_logo_url.scheme not in {"http", "https"}
                or not parsed_logo_url.netloc
            ):
                raise ShopifyApiError(
                    message="logoUrl must be a valid absolute http(s) URL.",
                    status_code=400,
                )

        normalized_css_vars = self._normalize_theme_brand_css_vars(css_vars)
        normalized_font_urls = self._normalize_theme_brand_font_urls(font_urls)
        normalized_component_image_urls = self._normalize_theme_component_image_urls(
            component_image_urls=component_image_urls
        )
        normalized_component_text_values = self._normalize_theme_component_text_values(
            component_text_values=component_text_values
        )
        normalized_auto_component_image_urls = (
            self._normalize_theme_auto_component_image_urls(
                auto_component_image_urls=auto_component_image_urls
            )
        )
        cleaned_data_theme = self._normalize_theme_data_theme(data_theme)
        normalized_theme_id, normalized_theme_name = self._normalize_theme_selector(
            theme_id=theme_id,
            theme_name=theme_name,
        )
        theme = await self._resolve_theme_for_brand_sync(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=normalized_theme_id,
            theme_name=normalized_theme_name,
        )
        profile = self._resolve_theme_brand_profile(theme_name=theme["name"])
        self._assert_theme_brand_profile_supported(
            theme_name=theme["name"], profile=profile
        )
        effective_css_vars = self._build_theme_compat_css_vars(
            profile=profile,
            css_vars=normalized_css_vars,
        )
        coverage = self._build_theme_brand_coverage_summary(
            profile=profile,
            source_css_vars=normalized_css_vars,
            effective_css_vars=effective_css_vars,
        )
        self._assert_theme_brand_coverage_complete(
            theme_name=theme["name"],
            coverage=coverage,
        )

        layout_content = await self._load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            filename=_THEME_BRAND_LAYOUT_FILENAME,
        )
        settings_content = await self._try_load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            filename=_THEME_BRAND_SETTINGS_FILENAME,
        )
        if profile.settings_value_paths and settings_content is None:
            raise ShopifyApiError(
                message=f"Theme file not found: {_THEME_BRAND_SETTINGS_FILENAME}",
                status_code=404,
            )
        settings_logo_url: str | None = None
        if settings_content is not None and profile.settings_value_paths:
            parsed_settings_for_logo = self._parse_theme_settings_json(
                settings_content=settings_content
            )
            if self._theme_settings_has_logo_fields(
                settings_data=parsed_settings_for_logo
            ):
                if self._is_shopify_file_url(value=cleaned_logo_url):
                    settings_logo_url = cleaned_logo_url
                else:
                    settings_logo_url = (
                        await self._create_shopify_logo_file_reference_from_url(
                            shop_domain=shop_domain,
                            access_token=access_token,
                            logo_url=cleaned_logo_url,
                        )
                    )

        should_list_theme_templates = bool(normalized_auto_component_image_urls) or (
            self._is_theme_component_settings_sync_enabled_for_profile(profile=profile)
        )
        template_filenames_for_color_sync: set[str] = set()
        template_filenames_for_auto_component_image_sync: set[str] = set()
        template_filenames_to_load: set[str] = set()
        listed_template_filenames: list[str] = []
        if should_list_theme_templates:
            listed_template_filenames = await self._list_theme_template_json_filenames(
                shop_domain=shop_domain,
                access_token=access_token,
                theme_id=theme["id"],
            )
        if self._is_theme_component_settings_sync_enabled_for_profile(profile=profile):
            template_filenames_for_color_sync = set(listed_template_filenames)
            template_filenames_to_load.update(template_filenames_for_color_sync)
        if normalized_auto_component_image_urls:
            template_filenames_for_auto_component_image_sync = set(
                listed_template_filenames
            )
            template_filenames_to_load.update(
                template_filenames_for_auto_component_image_sync
            )
        component_image_urls_by_template = (
            self._group_theme_component_image_urls_by_template(
                component_image_urls=normalized_component_image_urls
            )
        )
        component_text_values_by_template = (
            self._group_theme_component_text_values_by_template(
                component_text_values=normalized_component_text_values
            )
        )
        template_filenames_to_load.update(component_image_urls_by_template.keys())
        template_filenames_to_load.update(component_text_values_by_template.keys())

        template_settings_contents: dict[str, str] = {}
        if template_filenames_to_load:
            sorted_template_filenames = sorted(template_filenames_to_load)
            template_contents = await asyncio.gather(
                *[
                    self._load_theme_file_text(
                        shop_domain=shop_domain,
                        access_token=access_token,
                        theme_id=theme["id"],
                        filename=template_filename,
                    )
                    for template_filename in sorted_template_filenames
                ]
            )
            template_settings_contents = {
                template_filename: template_content
                for template_filename, template_content in zip(
                    sorted_template_filenames, template_contents, strict=True
                )
            }

        workspace_slug = self._normalize_workspace_slug(cleaned_workspace_name)
        css_filename = f"assets/{workspace_slug}-workspace-brand.css"
        replacement_block = self._render_theme_brand_liquid_block(
            css_filename=css_filename,
            workspace_name=cleaned_workspace_name,
            brand_name=cleaned_brand_name,
            logo_url=cleaned_logo_url,
            data_theme=cleaned_data_theme,
        )
        next_layout = self._replace_theme_brand_liquid_block(
            layout_content=layout_content,
            replacement_block=replacement_block,
        )
        css_content = self._render_theme_brand_css(
            theme_name=theme["name"],
            workspace_name=cleaned_workspace_name,
            brand_name=cleaned_brand_name,
            logo_url=cleaned_logo_url,
            data_theme=cleaned_data_theme,
            css_vars=normalized_css_vars,
            font_urls=normalized_font_urls,
            effective_css_vars=effective_css_vars,
        )
        settings_sync = {
            "settingsFilename": (
                _THEME_BRAND_SETTINGS_FILENAME if profile.settings_value_paths else None
            ),
            "expectedPaths": sorted(profile.settings_value_paths.keys()),
            "updatedPaths": [],
            "missingPaths": [],
            "requiredMissingPaths": [],
            "semanticUpdatedPaths": [],
            "unmappedColorPaths": [],
            "semanticTypographyUpdatedPaths": [],
            "unmappedTypographyPaths": [],
        }
        next_settings_content: str | None = None
        if settings_content is not None and profile.settings_value_paths:
            next_settings_content, settings_sync = self._sync_theme_settings_data(
                profile=profile,
                settings_content=settings_content,
                effective_css_vars=effective_css_vars,
                logo_url=settings_logo_url,
            )

        next_template_contents: dict[str, str] = dict(template_settings_contents)
        template_semantic_updated_paths: list[str] = []
        template_unmapped_color_paths: list[str] = []
        for template_filename in sorted(template_filenames_for_color_sync):
            template_content = next_template_contents.get(template_filename)
            if template_content is None:
                raise ShopifyApiError(
                    message=(
                        "Theme template file required for semantic color sync was not loaded. "
                        f"filename={template_filename}."
                    ),
                    status_code=404,
                )
            next_template_content, template_sync = (
                self._sync_theme_template_color_settings_data(
                    profile=profile,
                    template_filename=template_filename,
                    template_content=template_content,
                    effective_css_vars=effective_css_vars,
                )
            )
            template_semantic_updated_paths.extend(template_sync["updatedPaths"])
            template_unmapped_color_paths.extend(template_sync["unmappedColorPaths"])
            next_template_contents[template_filename] = next_template_content

        template_unmapped_color_paths = sorted(set(template_unmapped_color_paths))
        if template_unmapped_color_paths:
            raise ShopifyApiError(
                message=(
                    "Theme template settings sync discovered unmapped color setting paths: "
                    f"{', '.join(template_unmapped_color_paths)}. "
                    "Add semantic mappings in _THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME."
                ),
                status_code=422,
            )

        footer_group_content = next_template_contents.get(_THEME_FOOTER_GROUP_FILENAME)
        if isinstance(footer_group_content, str):
            footer_logo_component_paths = (
                self._extract_footer_logo_component_setting_paths(
                    template_filename=_THEME_FOOTER_GROUP_FILENAME,
                    template_content=footer_group_content,
                )
            )
            if footer_logo_component_paths:
                resolved_logo_component_url = settings_logo_url or cleaned_logo_url
                footer_component_image_map = component_image_urls_by_template.setdefault(
                    _THEME_FOOTER_GROUP_FILENAME, {}
                )
                for setting_path in footer_logo_component_paths:
                    footer_component_image_map[setting_path] = resolved_logo_component_url
                    normalized_component_image_urls[setting_path] = (
                        resolved_logo_component_url
                    )

        auto_component_image_urls_by_setting_path = (
            self._build_auto_theme_component_image_urls(
                template_filenames=template_filenames_for_auto_component_image_sync,
                template_contents_by_filename=next_template_contents,
                explicit_component_image_urls=normalized_component_image_urls,
                auto_component_image_urls=normalized_auto_component_image_urls,
            )
        )
        all_component_image_urls = dict(normalized_component_image_urls)
        all_component_image_urls.update(auto_component_image_urls_by_setting_path)
        component_image_urls_by_template = (
            self._group_theme_component_image_urls_by_template(
                component_image_urls=all_component_image_urls
            )
        )

        template_component_text_missing_paths: list[str] = []
        for (
            template_filename,
            component_text_map,
        ) in component_text_values_by_template.items():
            template_content = next_template_contents.get(template_filename)
            if template_content is None:
                raise ShopifyApiError(
                    message=f"Theme template file not found for component text sync: {template_filename}",
                    status_code=404,
                )
            _, validation_sync = self._sync_theme_template_component_text_settings_data(
                template_filename=template_filename,
                template_content=template_content,
                component_text_values_by_path=component_text_map,
            )
            template_component_text_missing_paths.extend(
                validation_sync["missingPaths"]
            )

        template_component_text_missing_paths = sorted(
            set(template_component_text_missing_paths)
        )
        if template_component_text_missing_paths:
            raise ShopifyApiError(
                message=(
                    "Theme template component text sync could not update mapped paths: "
                    f"{', '.join(template_component_text_missing_paths)}."
                ),
                status_code=409,
            )

        if component_text_values_by_template:
            for (
                template_filename,
                component_text_map,
            ) in component_text_values_by_template.items():
                template_content = next_template_contents[template_filename]
                next_template_content, _ = (
                    self._sync_theme_template_component_text_settings_data(
                        template_filename=template_filename,
                        template_content=template_content,
                        component_text_values_by_path=component_text_map,
                    )
                )
                next_template_contents[template_filename] = next_template_content

        template_component_image_missing_paths: list[str] = []
        for (
            template_filename,
            component_image_map,
        ) in component_image_urls_by_template.items():
            template_content = next_template_contents.get(template_filename)
            if template_content is None:
                raise ShopifyApiError(
                    message=f"Theme template file not found for component image sync: {template_filename}",
                    status_code=404,
                )
            _, validation_sync = (
                self._sync_theme_template_component_image_settings_data(
                    template_filename=template_filename,
                    template_content=template_content,
                    component_image_urls_by_path=component_image_map,
                )
            )
            template_component_image_missing_paths.extend(
                validation_sync["missingPaths"]
            )

        template_component_image_missing_paths = sorted(
            set(template_component_image_missing_paths)
        )
        if template_component_image_missing_paths:
            raise ShopifyApiError(
                message=(
                    "Theme template component image sync could not update mapped paths: "
                    f"{', '.join(template_component_image_missing_paths)}."
                ),
                status_code=409,
            )

        if component_image_urls_by_template:
            uploaded_component_image_url_cache: dict[str, str] = {}
            for (
                template_filename,
                component_image_map,
            ) in component_image_urls_by_template.items():
                template_content = next_template_contents[template_filename]
                resolved_component_image_map: dict[str, str] = {}
                for setting_path, component_image_url in component_image_map.items():
                    resolved_component_image_url = (
                        uploaded_component_image_url_cache.get(component_image_url)
                    )
                    if resolved_component_image_url is None:
                        if self._is_shopify_file_url(value=component_image_url):
                            resolved_component_image_url = component_image_url
                        else:
                            resolved_component_image_url = (
                                await self._create_shopify_logo_file_reference_from_url(
                                    shop_domain=shop_domain,
                                    access_token=access_token,
                                    logo_url=component_image_url,
                                )
                            )
                        uploaded_component_image_url_cache[component_image_url] = (
                            resolved_component_image_url
                        )
                    resolved_component_image_map[setting_path] = (
                        resolved_component_image_url
                    )

                next_template_content, _ = (
                    self._sync_theme_template_component_image_settings_data(
                        template_filename=template_filename,
                        template_content=template_content,
                        component_image_urls_by_path=resolved_component_image_map,
                    )
                )
                next_template_contents[template_filename] = next_template_content

        template_files_to_upsert: list[dict[str, str]] = []
        for (
            template_filename,
            original_template_content,
        ) in template_settings_contents.items():
            next_template_content = next_template_contents[template_filename]
            if next_template_content == original_template_content:
                continue
            template_files_to_upsert.append(
                {"filename": template_filename, "content": next_template_content}
            )

        settings_sync["semanticUpdatedPaths"] = sorted(
            set(settings_sync["semanticUpdatedPaths"] + template_semantic_updated_paths)
        )
        settings_sync["unmappedColorPaths"] = sorted(
            set(settings_sync["unmappedColorPaths"] + template_unmapped_color_paths)
        )

        files_to_upsert = [
            {"filename": _THEME_BRAND_LAYOUT_FILENAME, "content": next_layout},
            {"filename": css_filename, "content": css_content},
        ]
        if next_settings_content is not None:
            files_to_upsert.append(
                {
                    "filename": _THEME_BRAND_SETTINGS_FILENAME,
                    "content": next_settings_content,
                }
            )
        files_to_upsert.extend(template_files_to_upsert)
        job_id = await self._upsert_theme_files(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            files=files_to_upsert,
        )
        if job_id is not None:
            await self._wait_for_job_completion(
                shop_domain=shop_domain,
                access_token=access_token,
                job_id=job_id,
            )

        return {
            "themeId": theme["id"],
            "themeName": theme["name"],
            "themeRole": theme["role"],
            "layoutFilename": _THEME_BRAND_LAYOUT_FILENAME,
            "cssFilename": css_filename,
            "settingsFilename": (
                _THEME_BRAND_SETTINGS_FILENAME if profile.settings_value_paths else None
            ),
            "jobId": job_id,
            "coverage": coverage,
            "settingsSync": settings_sync,
        }

    async def audit_theme_brand(
        self,
        *,
        shop_domain: str,
        access_token: str,
        workspace_name: str,
        css_vars: dict[str, str],
        data_theme: str | None = None,
        theme_id: str | None = None,
        theme_name: str | None = None,
    ) -> dict[str, Any]:
        cleaned_workspace_name = workspace_name.strip()
        if not cleaned_workspace_name:
            raise ShopifyApiError(
                message="workspaceName must be a non-empty string.", status_code=400
            )
        normalized_css_vars = self._normalize_theme_brand_css_vars(css_vars)
        self._normalize_theme_data_theme(data_theme)
        normalized_theme_id, normalized_theme_name = self._normalize_theme_selector(
            theme_id=theme_id,
            theme_name=theme_name,
        )
        theme = await self._resolve_theme_for_brand_sync(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=normalized_theme_id,
            theme_name=normalized_theme_name,
        )

        profile = self._resolve_theme_brand_profile(theme_name=theme["name"])
        self._assert_theme_brand_profile_supported(
            theme_name=theme["name"], profile=profile
        )
        effective_css_vars = self._build_theme_compat_css_vars(
            profile=profile,
            css_vars=normalized_css_vars,
        )
        coverage = self._build_theme_brand_coverage_summary(
            profile=profile,
            source_css_vars=normalized_css_vars,
            effective_css_vars=effective_css_vars,
        )
        workspace_slug = self._normalize_workspace_slug(cleaned_workspace_name)
        css_filename = f"assets/{workspace_slug}-workspace-brand.css"

        layout_content = await self._load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            filename=_THEME_BRAND_LAYOUT_FILENAME,
        )
        layout_audit = self._audit_theme_layout(
            layout_content=layout_content,
            css_filename=css_filename,
        )
        css_content = await self._try_load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            filename=css_filename,
        )
        settings_content = await self._try_load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            filename=_THEME_BRAND_SETTINGS_FILENAME,
        )
        template_settings_contents: dict[str, str] = {}
        if self._is_theme_component_settings_sync_enabled_for_profile(profile=profile):
            template_filenames = await self._list_theme_template_json_filenames(
                shop_domain=shop_domain,
                access_token=access_token,
                theme_id=theme["id"],
            )
            if template_filenames:
                template_contents = await asyncio.gather(
                    *[
                        self._load_theme_file_text(
                            shop_domain=shop_domain,
                            access_token=access_token,
                            theme_id=theme["id"],
                            filename=template_filename,
                        )
                        for template_filename in template_filenames
                    ]
                )
                template_settings_contents = {
                    template_filename: template_content
                    for template_filename, template_content in zip(
                        template_filenames, template_contents, strict=True
                    )
                }
        settings_audit = {
            "settingsFilename": (
                _THEME_BRAND_SETTINGS_FILENAME if profile.settings_value_paths else None
            ),
            "expectedPaths": sorted(profile.settings_value_paths.keys()),
            "syncedPaths": [],
            "mismatchedPaths": [],
            "missingPaths": [],
            "requiredMissingPaths": [],
            "requiredMismatchedPaths": [],
            "semanticSyncedPaths": [],
            "semanticMismatchedPaths": [],
            "unmappedColorPaths": [],
            "semanticTypographySyncedPaths": [],
            "semanticTypographyMismatchedPaths": [],
            "unmappedTypographyPaths": [],
        }
        if settings_content is not None and profile.settings_value_paths:
            settings_audit = self._audit_theme_settings_data(
                profile=profile,
                settings_content=settings_content,
                effective_css_vars=effective_css_vars,
            )
        elif settings_content is None and profile.settings_value_paths:
            settings_audit["missingPaths"] = sorted(profile.settings_value_paths.keys())
            settings_audit["requiredMissingPaths"] = sorted(
                profile.required_settings_paths
            )

        template_semantic_synced_paths: list[str] = []
        template_semantic_mismatched_paths: list[str] = []
        template_unmapped_color_paths: list[str] = []
        for template_filename, template_content in template_settings_contents.items():
            template_audit = self._audit_theme_template_color_settings_data(
                profile=profile,
                template_filename=template_filename,
                template_content=template_content,
                effective_css_vars=effective_css_vars,
            )
            template_semantic_synced_paths.extend(template_audit["syncedPaths"])
            template_semantic_mismatched_paths.extend(template_audit["mismatchedPaths"])
            template_unmapped_color_paths.extend(template_audit["unmappedColorPaths"])

        settings_audit["semanticSyncedPaths"] = sorted(
            set(settings_audit["semanticSyncedPaths"] + template_semantic_synced_paths)
        )
        settings_audit["semanticMismatchedPaths"] = sorted(
            set(
                settings_audit["semanticMismatchedPaths"]
                + template_semantic_mismatched_paths
            )
        )
        settings_audit["unmappedColorPaths"] = sorted(
            set(settings_audit["unmappedColorPaths"] + template_unmapped_color_paths)
        )

        is_ready = (
            not coverage["missingSourceVars"]
            and not coverage["missingThemeVars"]
            and layout_audit["hasManagedMarkerBlock"]
            and layout_audit["layoutIncludesManagedCssAsset"]
            and css_content is not None
            and not settings_audit["requiredMissingPaths"]
            and not settings_audit["requiredMismatchedPaths"]
            and not settings_audit["semanticMismatchedPaths"]
            and not settings_audit["unmappedColorPaths"]
            and not settings_audit["unmappedTypographyPaths"]
        )

        return {
            "themeId": theme["id"],
            "themeName": theme["name"],
            "themeRole": theme["role"],
            "layoutFilename": _THEME_BRAND_LAYOUT_FILENAME,
            "cssFilename": css_filename,
            "settingsFilename": settings_audit["settingsFilename"],
            "hasManagedMarkerBlock": layout_audit["hasManagedMarkerBlock"],
            "layoutIncludesManagedCssAsset": layout_audit[
                "layoutIncludesManagedCssAsset"
            ],
            "managedCssAssetExists": css_content is not None,
            "coverage": coverage,
            "settingsAudit": settings_audit,
            "isReady": is_ready,
        }

    async def _admin_graphql(
        self,
        *,
        shop_domain: str,
        access_token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"https://{shop_domain}/admin/api/{settings.SHOPIFY_ADMIN_API_VERSION}/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }
        response = await self._post_json(url=url, payload=payload, headers=headers)
        data = response.get("data")
        errors = response.get("errors")
        if errors:
            if isinstance(errors, list):
                for error in errors:
                    if not isinstance(error, dict):
                        continue
                    message = error.get("message")
                    path = error.get("path")
                    normalized_message = (
                        message.strip().lower() if isinstance(message, str) else ""
                    )
                    if "access denied for menus field" in normalized_message or (
                        isinstance(path, list)
                        and any(
                            isinstance(path_part, str)
                            and path_part.strip().lower() == "menus"
                            for path_part in path
                        )
                    ):
                        raise ShopifyApiError(
                            message=(
                                "Admin GraphQL access denied for menu operations. "
                                "Missing required scopes: read_online_store_navigation, "
                                "write_online_store_navigation. "
                                "Update app scopes, then reauthorize the store installation."
                            ),
                            status_code=403,
                        )
            raise ShopifyApiError(message=f"Admin GraphQL errors: {errors}")
        if not isinstance(data, dict):
            raise ShopifyApiError(message="Admin GraphQL response is missing data")
        return data

    async def _storefront_graphql(
        self,
        *,
        shop_domain: str,
        storefront_access_token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"https://{shop_domain}/api/{settings.SHOPIFY_STOREFRONT_API_VERSION}/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Storefront-Access-Token": storefront_access_token,
        }
        response = await self._post_json(url=url, payload=payload, headers=headers)
        data = response.get("data")
        errors = response.get("errors")
        if errors:
            raise ShopifyApiError(
                message=f"Storefront GraphQL errors: {errors}", status_code=409
            )
        if not isinstance(data, dict):
            raise ShopifyApiError(
                message="Storefront GraphQL response is missing data", status_code=409
            )
        return data

    async def _post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise ShopifyApiError(
                message=f"Network error while calling Shopify: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise ShopifyApiError(
                message=f"Shopify API call failed ({response.status_code}): {response.text}",
                status_code=502,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise ShopifyApiError(message="Shopify API returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise ShopifyApiError(message="Shopify API response must be a JSON object")
        return body
