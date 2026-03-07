from __future__ import annotations

import asyncio
import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from html import escape
import mimetypes
from pathlib import Path
import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from app.config import settings

_THEME_BRAND_LAYOUT_FILENAME = "layout/theme.liquid"
_THEME_BRAND_SETTINGS_FILENAME = "config/settings_data.json"
_THEME_FOOTER_GROUP_FILENAME = "sections/footer-group.json"
_THEME_MAIN_COLLECTION_SECTION_FILENAME = "sections/main-collection.liquid"
_THEME_HEADER_ICONS_FILENAME = "snippets/header-icons.liquid"
_THEME_HEADER_DRAWER_FILENAME = "snippets/header-drawer.liquid"
_THEME_PRODUCT_CARD_SNIPPET_FILENAME = "snippets/product-card.liquid"
_THEME_SHOPPABLE_VIDEO_SECTION_FILENAME = "sections/ss-shoppable-video.liquid"
_CATALOG_COLLECTION_HANDLE = "all"
_CATALOG_COLLECTION_TITLE = "Catalog"
_SHOP_MENU_TITLE = "Shop"
_CONTACT_MENU_TITLE = "Contact"
_HOME_MENU_TITLE = "Home"
_TRACK_ORDER_MENU_TITLE = "Track Your Order"
_DEFAULT_STORE_NAVIGATION_MENU_HANDLE = "main-menu"
_DEFAULT_FOOTER_QUICK_LINKS_MENU_HANDLE = "footer"
_MANAGED_POLICY_PAGE_HANDLES = frozenset(
    {
        "privacy-policy",
        "returns-refunds-policy",
        "shipping-policy",
        "terms-of-service",
        "contact-support",
        "company-information",
        "subscription-terms-and-cancellation",
    }
)
_MANAGED_POLICY_CANONICAL_PATHS = frozenset(
    f"/pages/{handle}" for handle in _MANAGED_POLICY_PAGE_HANDLES
)
_DEFAULT_FOOTER_QUICK_LINK_CANONICAL_PATHS = frozenset(
    {
        "/",
        f"/collections/{_CATALOG_COLLECTION_HANDLE}",
        "/pages/contact",
    }
)
_POLICY_MENU_SEARCH_PATH = "/search"
_POLICY_MENU_SEARCH_TITLE = "Search"
_DEFAULT_MAIN_MENU_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "title": _HOME_MENU_TITLE,
        "type": "HTTP",
        "url": "/",
        "resourceId": None,
        "aliases": ("home",),
    },
    {
        "title": _SHOP_MENU_TITLE,
        "type": "HTTP",
        "url": "/collections/all",
        "resourceId": None,
        "aliases": ("shop", "catalog"),
    },
    {
        "title": _CONTACT_MENU_TITLE,
        "type": "HTTP",
        "url": "/pages/contact",
        "resourceId": None,
        "aliases": ("contact",),
    },
    {
        "title": _TRACK_ORDER_MENU_TITLE,
        "type": "HTTP",
        "url": "/pages/contact",
        "resourceId": None,
        "aliases": ("track your order", "track my order"),
    },
)
_DEFAULT_FOOTER_QUICK_LINKS_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "title": _HOME_MENU_TITLE,
        "type": "HTTP",
        "url": "/",
        "resourceId": None,
        "aliases": ("home",),
    },
    {
        "title": _SHOP_MENU_TITLE,
        "type": "HTTP",
        "url": "/collections/all",
        "resourceId": None,
        "aliases": ("shop", "catalog"),
    },
    {
        "title": _CONTACT_MENU_TITLE,
        "type": "HTTP",
        "url": "/pages/contact",
        "resourceId": None,
        "aliases": ("contact",),
    },
)
_GRAPHQL_MAX_PAGE_SIZE = 250
_COLLECTION_ADD_PRODUCTS_BATCH_SIZE = 50
_THEME_BRAND_MARKER_START = "<!-- MOS_WORKSPACE_BRAND_START -->"
_THEME_BRAND_MARKER_END = "<!-- MOS_WORKSPACE_BRAND_END -->"
_THEME_TEMPLATE_JSON_FILENAME_RE = re.compile(r"^(?:templates|sections)/.+\.json$")
_THEME_COMPONENT_SETTINGS_SYNC_THEME_NAMES = frozenset({"futrgroup2-0theme"})
_THEME_CATALOG_DETAILS_MENU_ITEM_RE = re.compile(
    r"<li>\s*<details\b[^>]*>.*?<summary[^>]*>\s*Catalog\s*</summary>.*?</details>\s*</li>",
    re.IGNORECASE | re.DOTALL,
)
_THEME_CATALOG_LINK_MENU_ITEM_RE = re.compile(
    r"<li>\s*<a\b[^>]*>\s*Catalog\s*</a>\s*</li>",
    re.IGNORECASE | re.DOTALL,
)
_THEME_FRENCH_UI_TEXT_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bSuivre\s+ma\s+commande\b", re.IGNORECASE),
        "Track my order",
    ),
    (
        re.compile(r"\bVoir\s+le\s+panier\b", re.IGNORECASE),
        "View cart",
    ),
    (
        re.compile(r"\bAjouter\s+au\s+panier\b", re.IGNORECASE),
        "Add to cart",
    ),
    (
        re.compile(r"\bPanier\b", re.IGNORECASE),
        "Cart",
    ),
    (
        re.compile(r"\bPasser\s+(?:a|\u00e0)\s+la\s+caisse\b", re.IGNORECASE),
        "Checkout",
    ),
    (
        re.compile(
            r"\bTaxes\s+incluses\s+et\s+frais\s+d['\u2019]exp(?:e|\u00e9)dition\s+calcul(?:e|\u00e9)es?\s+(?:a|\u00e0)\s+la\s+caisse\.?",
            re.IGNORECASE,
        ),
        "Taxes included and shipping calculated at checkout.",
    ),
    (
        re.compile(r"\bLivraison\b", re.IGNORECASE),
        "Shipping",
    ),
)
_THEME_LOGO_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
_THEME_FILE_IMAGE_RESOLVE_MAX_CONCURRENCY = 4
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
        "current.footer_text": "--footer-text-color",
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
            'header nav li, header .header__inline-menu li, header .list-menu--inline > li, #shopify-section-header nav li, #shopify-section-header .header__inline-menu li, #shopify-section-header .list-menu--inline > li',
            (
                ("display", "flex"),
                ("align-items", "center"),
                ("justify-content", "flex-start"),
            ),
        ),
        (
            'header nav li > a, header nav li > details > summary, header .header__menu-item, header .header__inline-menu a, header .header__inline-menu summary, #shopify-section-header nav li > a, #shopify-section-header nav li > details > summary, #shopify-section-header .header__menu-item, #shopify-section-header .header__inline-menu a, #shopify-section-header .header__inline-menu summary',
            (
                ("display", "inline-flex"),
                ("align-items", "center"),
                ("justify-content", "flex-start"),
                ("text-align", "left"),
                ("width", "100%"),
                ("line-height", "1"),
            ),
        ),
        (
            'header .drawer__menu-item, #shopify-section-header .drawer__menu-item, header .drawer__submenu > button, #shopify-section-header .drawer__submenu > button, header .drawer__submenu a, #shopify-section-header .drawer__submenu a',
            (
                ("display", "inline-flex"),
                ("align-items", "center"),
                ("justify-content", "flex-start"),
                ("text-align", "left"),
                ("width", "100%"),
                ("line-height", "1"),
            ),
        ),
        (
            '.button, .btn, input[type="button"], input[type="submit"], input[type="reset"]',
            (
                ("background-color", "var(--color-cta)"),
                ("color", "var(--color-cta-text)"),
                ("border", "none"),
                ("border-radius", "999px"),
                ("box-shadow", "8px 8px 0 var(--color-muted)"),
                (
                    "transition",
                    "background-color 220ms ease, color 220ms ease, border-color 220ms ease, box-shadow 220ms ease, transform 220ms ease",
                ),
            ),
        ),
        (
            '.button:hover, .button:focus-visible, .btn:hover, .btn:focus-visible, input[type="button"]:hover, input[type="button"]:focus-visible, input[type="submit"]:hover, input[type="submit"]:focus-visible, input[type="reset"]:hover, input[type="reset"]:focus-visible',
            (
                ("background-color", "var(--color-cta-text)"),
                ("color", "var(--color-cta)"),
                ("transform", "translateY(-2px)"),
            ),
        ),
        (
            ".button .icon-arrow-right, .button .icon-arrow-left, .button [class*=\"arrow\"] svg, .button [class*=\"arrow\"] svg *, .btn .icon-arrow-right, .btn .icon-arrow-left, .btn [class*=\"arrow\"] svg, .btn [class*=\"arrow\"] svg *, button .icon-arrow-right, button .icon-arrow-left, button [class*=\"arrow\"] svg, button [class*=\"arrow\"] svg *",
            (
                ("color", "var(--color-cta-text)"),
                ("fill", "currentColor"),
                ("stroke", "currentColor"),
            ),
        ),
        (
            ".button:hover .icon-arrow-right, .button:hover .icon-arrow-left, .button:hover [class*=\"arrow\"] svg, .button:hover [class*=\"arrow\"] svg *, .button:focus-visible .icon-arrow-right, .button:focus-visible .icon-arrow-left, .button:focus-visible [class*=\"arrow\"] svg, .button:focus-visible [class*=\"arrow\"] svg *, .btn:hover .icon-arrow-right, .btn:hover .icon-arrow-left, .btn:hover [class*=\"arrow\"] svg, .btn:hover [class*=\"arrow\"] svg *, .btn:focus-visible .icon-arrow-right, .btn:focus-visible .icon-arrow-left, .btn:focus-visible [class*=\"arrow\"] svg, .btn:focus-visible [class*=\"arrow\"] svg *, button:hover .icon-arrow-right, button:hover .icon-arrow-left, button:hover [class*=\"arrow\"] svg, button:hover [class*=\"arrow\"] svg *, button:focus-visible .icon-arrow-right, button:focus-visible .icon-arrow-left, button:focus-visible [class*=\"arrow\"] svg, button:focus-visible [class*=\"arrow\"] svg *",
            (
                ("color", "var(--color-cta)"),
                ("fill", "currentColor"),
                ("stroke", "currentColor"),
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
            ".cart-drawer, cart-drawer, #CartDrawer, [id=\"CartDrawer\"], [data-cart-drawer], .drawer--cart, .cart-drawer .drawer__inner, .cart-drawer__inner, .cart-drawer .drawer__header, .cart-drawer .drawer__footer, .cart-drawer .cart-items, .cart-drawer .cart-item, cart-drawer .drawer__inner, cart-drawer .drawer__header, cart-drawer .drawer__footer, cart-drawer .cart-items, cart-drawer .cart-item, #CartDrawer .drawer__inner, #CartDrawer .drawer__header, #CartDrawer .drawer__footer, #CartDrawer .cart-items, #CartDrawer .cart-item",
            (
                ("background-color", "#ffffff"),
                ("color", "var(--color-text)"),
                ("border-color", "var(--color-border)"),
            ),
        ),
        (
            ".drawer .modal__container, .quick-view .drawer__inner, .x-modal .drawer__inner, .newsletter-modal .drawer__inner",
            (
                ("background-color", "#ffffff"),
                ("color", "var(--color-text)"),
                ("border-color", "var(--color-border)"),
            ),
        ),
        (
            "header .header__buttons .cart-drawer-button, #shopify-section-header .header__buttons .cart-drawer-button, header .header__buttons .cart-drawer-button:hover, #shopify-section-header .header__buttons .cart-drawer-button:hover, header .header__buttons .cart-drawer-button:focus-visible, #shopify-section-header .header__buttons .cart-drawer-button:focus-visible",
            (
                ("background-color", "transparent"),
                ("border-color", "transparent"),
                ("box-shadow", "none"),
            ),
        ),
        (
            '.swiper-button-prev, .swiper-button-next, .slick-prev, .slick-next, .flickity-prev-next-button, [class*="slider"] [class*="prev"], [class*="slider"] [class*="next"], [class*="carousel"] [class*="prev"], [class*="carousel"] [class*="next"], [class*="arrow-prev"], [class*="arrow-next"], [class*="arrow-left"], [class*="arrow-right"]',
            (
                ("background-color", "transparent"),
                ("border-color", "transparent"),
                ("color", "var(--color-brand)"),
                ("box-shadow", "none"),
            ),
        ),
        (
            'footer, #shopify-section-footer, [role="contentinfo"], .footer, [id*="footer"], [class*="footer"]',
            (
                ("background-color", "var(--footer-bg)"),
                ("color", "var(--footer-text-color)"),
                ("border-color", "var(--footer-text-color)"),
            ),
        ),
        (
            'footer [class*="footer-newsletter-text-"] *, footer [class*="footer-text-"] *, #shopify-section-footer [class*="footer-newsletter-text-"] *, #shopify-section-footer [class*="footer-text-"] *, [role="contentinfo"] [class*="footer-newsletter-text-"] *, [role="contentinfo"] [class*="footer-text-"] *, .footer [class*="footer-newsletter-text-"] *, .footer [class*="footer-text-"] *, [id*="footer"] [class*="footer-newsletter-text-"] *, [id*="footer"] [class*="footer-text-"] *, [class*="footer"] [class*="footer-newsletter-text-"] *, [class*="footer"] [class*="footer-text-"] *',
            (("color", "var(--footer-text-color)"),),
        ),
        (
            'footer [class*="footer-copy-text-"] *, footer [class*="footer-main-title-"], footer [class*="footer-list-title-"], footer [class*="footer-tab-title-"], footer [class*="footer-tab-text-"] *, footer [class*="footer-tab-height-cal-"] *, #shopify-section-footer [class*="footer-copy-text-"] *, #shopify-section-footer [class*="footer-main-title-"], #shopify-section-footer [class*="footer-list-title-"], #shopify-section-footer [class*="footer-tab-title-"], #shopify-section-footer [class*="footer-tab-text-"] *, #shopify-section-footer [class*="footer-tab-height-cal-"] *, [role="contentinfo"] [class*="footer-copy-text-"] *, [role="contentinfo"] [class*="footer-main-title-"], [role="contentinfo"] [class*="footer-list-title-"], [role="contentinfo"] [class*="footer-tab-title-"], [role="contentinfo"] [class*="footer-tab-text-"] *, [role="contentinfo"] [class*="footer-tab-height-cal-"] *, .footer [class*="footer-copy-text-"] *, .footer [class*="footer-main-title-"], .footer [class*="footer-list-title-"], .footer [class*="footer-tab-title-"], .footer [class*="footer-tab-text-"] *, .footer [class*="footer-tab-height-cal-"] *, [id*="footer"] [class*="footer-copy-text-"] *, [id*="footer"] [class*="footer-main-title-"], [id*="footer"] [class*="footer-list-title-"], [id*="footer"] [class*="footer-tab-title-"], [id*="footer"] [class*="footer-tab-text-"] *, [id*="footer"] [class*="footer-tab-height-cal-"] *, [class*="footer"] [class*="footer-copy-text-"] *, [class*="footer"] [class*="footer-main-title-"], [class*="footer"] [class*="footer-list-title-"], [class*="footer"] [class*="footer-tab-title-"], [class*="footer"] [class*="footer-tab-text-"] *, [class*="footer"] [class*="footer-tab-height-cal-"] *',
            (("color", "var(--footer-text-color)"),),
        ),
        (
            'footer [class*="footer-newsletter-input-"], #shopify-section-footer [class*="footer-newsletter-input-"], [role="contentinfo"] [class*="footer-newsletter-input-"], .footer [class*="footer-newsletter-input-"], [id*="footer"] [class*="footer-newsletter-input-"], [class*="footer"] [class*="footer-newsletter-input-"]',
            (("color", "var(--footer-text-color)"),),
        ),
        (
            'footer [class*="footer-newsletter-input-"]::placeholder, #shopify-section-footer [class*="footer-newsletter-input-"]::placeholder, [role="contentinfo"] [class*="footer-newsletter-input-"]::placeholder, .footer [class*="footer-newsletter-input-"]::placeholder, [id*="footer"] [class*="footer-newsletter-input-"]::placeholder, [class*="footer"] [class*="footer-newsletter-input-"]::placeholder',
            (("color", "var(--footer-text-color)"),),
        ),
        (
            'footer a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"]), #shopify-section-footer a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"]), [role="contentinfo"] a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"]), .footer a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"]), [id*="footer"] a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"]), [class*="footer"] a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"])',
            (("color", "var(--footer-text-color)"),),
        ),
        (
            'footer button, footer .button, footer .btn, footer input[type="button"], footer input[type="submit"], footer input[type="reset"], footer [role="button"], #shopify-section-footer button, #shopify-section-footer .button, #shopify-section-footer .btn, #shopify-section-footer input[type="button"], #shopify-section-footer input[type="submit"], #shopify-section-footer input[type="reset"], #shopify-section-footer [role="button"], [role="contentinfo"] button, [role="contentinfo"] .button, [role="contentinfo"] .btn, [role="contentinfo"] input[type="button"], [role="contentinfo"] input[type="submit"], [role="contentinfo"] input[type="reset"], [role="contentinfo"] [role="button"], .footer button, .footer .button, .footer .btn, .footer input[type="button"], .footer input[type="submit"], .footer input[type="reset"], .footer [role="button"], [id*="footer"] button, [id*="footer"] .button, [id*="footer"] .btn, [id*="footer"] input[type="button"], [id*="footer"] input[type="submit"], [id*="footer"] input[type="reset"], [id*="footer"] [role="button"], [class*="footer"] button, [class*="footer"] .button, [class*="footer"] .btn, [class*="footer"] input[type="button"], [class*="footer"] input[type="submit"], [class*="footer"] input[type="reset"], [class*="footer"] [role="button"]',
            (("border-color", "var(--footer-text-color)"),),
        ),
        (
            '.announcement-bar, [id*="announcement"], [class*="announcement"]',
            (("color", "var(--announcement-text-color)"),),
        ),
    ),
}
_THEME_SETTINGS_SEMANTIC_SOURCE_VARS_BY_NAME: dict[str, dict[str, str]] = {
    "futrgroup2-0theme": {
        "hero_background": "--hero-bg",
        "background": "--color-page-bg",
        "foreground": "--color-text",
        "text": "--color-text",
        "announcement_text": "--announcement-text-color",
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
        "footer_text": "--footer-text-color",
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
_THEME_SETTINGS_CSS_VAR_CAPTURE_RE = re.compile(
    r"^var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*(.+?)\s*)?\)$"
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
_THEME_IMAGE_SLOT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "theme_image_slot_config.json"
)
_THEME_IMAGE_SLOT_ALLOWED_RECOMMENDED_ASPECTS = frozenset(
    {"landscape", "portrait", "square", "any"}
)


def _load_theme_image_slots_by_name_from_config() -> dict[str, tuple[dict[str, Any], ...]]:
    try:
        parsed = json.loads(_THEME_IMAGE_SLOT_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Shared theme image slot config file is missing. "
            f"path={_THEME_IMAGE_SLOT_CONFIG_PATH}."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            "Shared theme image slot config file could not be read. "
            f"path={_THEME_IMAGE_SLOT_CONFIG_PATH}, error={exc}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Shared theme image slot config file is invalid JSON. "
            f"path={_THEME_IMAGE_SLOT_CONFIG_PATH}, error={exc}."
        ) from exc

    raw_theme_map = (
        parsed.get("themeImageSlotsByName") if isinstance(parsed, dict) else None
    )
    if not isinstance(raw_theme_map, dict):
        raise RuntimeError(
            "Shared theme image slot config is invalid. "
            "Expected object key `themeImageSlotsByName`."
        )

    normalized_by_name: dict[str, tuple[dict[str, Any], ...]] = {}
    for raw_theme_name, raw_slots in raw_theme_map.items():
        if not isinstance(raw_theme_name, str) or not raw_theme_name.strip():
            raise RuntimeError(
                "Shared theme image slot config contains an invalid theme key. "
                f"theme={raw_theme_name!r}."
            )
        if not isinstance(raw_slots, list):
            raise RuntimeError(
                "Shared theme image slot config contains an invalid slot list. "
                f"theme={raw_theme_name}."
            )

        normalized_slots: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for index, raw_slot in enumerate(raw_slots):
            if not isinstance(raw_slot, dict):
                raise RuntimeError(
                    "Shared theme image slot config contains a non-object slot entry. "
                    f"theme={raw_theme_name}, index={index}."
                )
            path = raw_slot.get("path")
            key = raw_slot.get("key")
            role = raw_slot.get("role")
            recommended_aspect = raw_slot.get("recommendedAspect")
            allow_missing = raw_slot.get("allowMissing", False)
            prompt_aspect_ratio = raw_slot.get("promptAspectRatio")
            prompt_render_hint = raw_slot.get("promptRenderHint")
            if (
                not isinstance(path, str)
                or not path.strip()
                or not isinstance(key, str)
                or not key.strip()
                or not isinstance(role, str)
                or not role.strip()
                or not isinstance(recommended_aspect, str)
                or recommended_aspect
                not in _THEME_IMAGE_SLOT_ALLOWED_RECOMMENDED_ASPECTS
                or not isinstance(allow_missing, bool)
            ):
                raise RuntimeError(
                    "Shared theme image slot config contains an invalid slot definition. "
                    f"theme={raw_theme_name}, index={index}, slot={raw_slot}."
                )
            if prompt_aspect_ratio is not None and (
                not isinstance(prompt_aspect_ratio, str)
                or not prompt_aspect_ratio.strip()
            ):
                raise RuntimeError(
                    "Shared theme image slot config contains an invalid promptAspectRatio. "
                    f"theme={raw_theme_name}, index={index}."
                )
            if prompt_render_hint is not None and (
                not isinstance(prompt_render_hint, str)
                or not prompt_render_hint.strip()
            ):
                raise RuntimeError(
                    "Shared theme image slot config contains an invalid promptRenderHint. "
                    f"theme={raw_theme_name}, index={index}."
                )

            normalized_path = path.strip()
            if normalized_path in seen_paths:
                raise RuntimeError(
                    "Shared theme image slot config contains duplicate slot paths. "
                    f"theme={raw_theme_name}, path={normalized_path}."
                )
            seen_paths.add(normalized_path)

            normalized_slot: dict[str, Any] = {
                "path": normalized_path,
                "key": key.strip(),
                "role": role.strip(),
                "recommendedAspect": recommended_aspect,
            }
            if allow_missing:
                normalized_slot["allowMissing"] = True
            if isinstance(prompt_aspect_ratio, str) and prompt_aspect_ratio.strip():
                normalized_slot["promptAspectRatio"] = prompt_aspect_ratio.strip()
            if isinstance(prompt_render_hint, str) and prompt_render_hint.strip():
                normalized_slot["promptRenderHint"] = prompt_render_hint.strip()
            normalized_slots.append(normalized_slot)

        normalized_by_name[raw_theme_name.strip()] = tuple(normalized_slots)

    return normalized_by_name


_THEME_IMAGE_SLOTS_BY_THEME_NAME = _load_theme_image_slots_by_name_from_config()


def _require_theme_image_slots_for_theme(theme_name: str) -> tuple[dict[str, Any], ...]:
    slots = _THEME_IMAGE_SLOTS_BY_THEME_NAME.get(theme_name)
    if slots is None:
        raise RuntimeError(
            "Shared theme image slot config is missing required theme entries. "
            f"theme={theme_name}."
        )
    return slots


_THEME_TEMPLATE_SLOT_MANIFEST_BY_NAME: dict[
    str, dict[str, tuple[dict[str, Any], ...]]
] = {
    "futrgroup2-0theme": {
        "imageSlots": _require_theme_image_slots_for_theme("futrgroup2-0theme"),
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
                "maxLength": 72,
            },
            {
                "path": "templates/index.json.sections.ss_countdown_timer_4_TxGT4a.blocks.text_KQyqqd.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 140,
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
            {
                "path": "templates/collection.json.sections.main-collection.blocks.promotion.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/collection.json.sections.main-collection.blocks.promotion.settings.content",
                "key": "content",
                "role": "body",
                "maxLength": 320,
                "richText": True,
            },
            {
                "path": "templates/collection.json.sections.main-collection.blocks.promotion.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/collection.json.sections.images-with-text-overlay.blocks.subheading.settings.subheading",
                "key": "subheading",
                "role": "supporting",
                "maxLength": 90,
            },
            {
                "path": "templates/collection.json.sections.images-with-text-overlay.blocks.heading.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/collection.json.sections.images-with-text-overlay.blocks.text.settings.text",
                "key": "text",
                "role": "body",
                "maxLength": 320,
                "richText": True,
            },
            {
                "path": "templates/collection.json.sections.images-with-text-overlay.blocks.button_YJdTtb.settings.button_label",
                "key": "button_label",
                "role": "cta",
                "maxLength": 40,
            },
            {
                "path": "templates/collection.json.sections.recently-viewed.settings.heading",
                "key": "heading",
                "role": "headline",
                "maxLength": 120,
            },
            {
                "path": "templates/collection.json.sections.recently-viewed.settings.subheading",
                "key": "subheading",
                "role": "supporting",
                "maxLength": 90,
            },
            {
                "path": "templates/collection.json.sections.recently-viewed.settings.description",
                "key": "description",
                "role": "body",
                "maxLength": 320,
                "richText": True,
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

    async def create_storefront_access_token(
        self,
        *,
        shop_domain: str,
        access_token: str,
        title: str = "Marketi Funnel Checkout",
    ) -> str:
        query = """
        mutation storefrontAccessTokenCreate($input: StorefrontAccessTokenInput!) {
            storefrontAccessTokenCreate(input: $input) {
                storefrontAccessToken {
                    accessToken
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {"query": query, "variables": {"input": {"title": title}}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        create_data = response.get("storefrontAccessTokenCreate") or {}
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(
                message=f"storefrontAccessTokenCreate failed: {messages}",
                status_code=409,
            )

        storefront_access_token = (
            (create_data.get("storefrontAccessToken") or {}).get("accessToken")
        )
        if (
            not isinstance(storefront_access_token, str)
            or not storefront_access_token.strip()
        ):
            raise ShopifyApiError(
                message=(
                    "storefrontAccessTokenCreate response is missing "
                    "storefrontAccessToken.accessToken"
                )
            )
        return storefront_access_token

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

    async def ensure_catalog_collection_route_is_available(
        self,
        *,
        shop_domain: str,
        access_token: str,
        sync_all_products: bool = True,
    ) -> dict[str, Any]:
        collection = await self._get_collection_by_handle(
            shop_domain=shop_domain,
            access_token=access_token,
            handle=_CATALOG_COLLECTION_HANDLE,
        )
        if collection is None:
            collection = await self._create_collection(
                shop_domain=shop_domain,
                access_token=access_token,
                title=_CATALOG_COLLECTION_TITLE,
                handle=_CATALOG_COLLECTION_HANDLE,
            )

        online_store_publication_id = await self._get_online_store_publication_id(
            shop_domain=shop_domain,
            access_token=access_token,
        )
        is_published = await self._is_collection_published_on_publication(
            shop_domain=shop_domain,
            access_token=access_token,
            collection_id=collection["id"],
            publication_id=online_store_publication_id,
        )
        if not is_published:
            await self._publish_collection_to_publication(
                shop_domain=shop_domain,
                access_token=access_token,
                collection_id=collection["id"],
                publication_id=online_store_publication_id,
            )

        added_product_count = 0
        if sync_all_products:
            shop_product_ids = await self._list_shop_product_ids(
                shop_domain=shop_domain,
                access_token=access_token,
            )
            if shop_product_ids:
                collection_product_ids = await self._list_collection_product_ids(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    collection_id=collection["id"],
                )
                existing_product_ids = set(collection_product_ids)
                missing_product_ids = [
                    product_id
                    for product_id in shop_product_ids
                    if product_id not in existing_product_ids
                ]
                for start in range(
                    0, len(missing_product_ids), _COLLECTION_ADD_PRODUCTS_BATCH_SIZE
                ):
                    await self._add_products_to_collection(
                        shop_domain=shop_domain,
                        access_token=access_token,
                        collection_id=collection["id"],
                        product_ids=missing_product_ids[
                            start : start + _COLLECTION_ADD_PRODUCTS_BATCH_SIZE
                        ],
                    )
                added_product_count = len(missing_product_ids)

        return {
            "collectionId": collection["id"],
            "collectionHandle": collection["handle"],
            "collectionTitle": collection["title"],
            "addedProductCount": added_product_count,
        }

    @staticmethod
    def _normalize_catalog_collection_product_gids(
        *, product_gids: list[str]
    ) -> list[str]:
        normalized_product_gids: list[str] = []
        seen_product_gids: set[str] = set()

        for raw_product_gid in product_gids:
            if not isinstance(raw_product_gid, str):
                raise ShopifyApiError(
                    message="product_gids must contain only Shopify Product GIDs.",
                    status_code=400,
                )
            cleaned_product_gid = raw_product_gid.strip()
            if not cleaned_product_gid.startswith("gid://shopify/Product/"):
                raise ShopifyApiError(
                    message="product_gids must contain only Shopify Product GIDs.",
                    status_code=400,
                )
            if cleaned_product_gid in seen_product_gids:
                continue
            seen_product_gids.add(cleaned_product_gid)
            normalized_product_gids.append(cleaned_product_gid)

        return normalized_product_gids

    async def ensure_catalog_collection_contains_products(
        self,
        *,
        shop_domain: str,
        access_token: str,
        product_gids: list[str],
    ) -> dict[str, Any]:
        normalized_product_gids = self._normalize_catalog_collection_product_gids(
            product_gids=product_gids
        )
        collection = await self.ensure_catalog_collection_route_is_available(
            shop_domain=shop_domain,
            access_token=access_token,
            sync_all_products=False,
        )

        added_product_count = 0
        if normalized_product_gids:
            collection_product_ids = await self._list_collection_product_ids(
                shop_domain=shop_domain,
                access_token=access_token,
                collection_id=collection["collectionId"],
            )
            existing_product_ids = set(collection_product_ids)
            missing_product_ids = [
                product_gid
                for product_gid in normalized_product_gids
                if product_gid not in existing_product_ids
            ]
            for start in range(
                0, len(missing_product_ids), _COLLECTION_ADD_PRODUCTS_BATCH_SIZE
            ):
                await self._add_products_to_collection(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    collection_id=collection["collectionId"],
                    product_ids=missing_product_ids[
                        start : start + _COLLECTION_ADD_PRODUCTS_BATCH_SIZE
                    ],
                )
            added_product_count = len(missing_product_ids)

        return {
            "collectionId": collection["collectionId"],
            "collectionHandle": collection["collectionHandle"],
            "collectionTitle": collection["collectionTitle"],
            "requestedProductCount": len(normalized_product_gids),
            "addedProductCount": added_product_count,
        }

    async def _get_collection_by_handle(
        self,
        *,
        shop_domain: str,
        access_token: str,
        handle: str,
    ) -> dict[str, str] | None:
        cleaned_handle = handle.strip().lower()
        if not cleaned_handle:
            raise ShopifyApiError(message="Collection handle cannot be empty.", status_code=400)
        query = """
        query collectionByHandle($first: Int!, $query: String!) {
            collections(first: $first, query: $query) {
                nodes {
                    id
                    handle
                    title
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
                    "first": 1,
                    "query": f"handle:{cleaned_handle}",
                },
            },
        )
        collections = response.get("collections")
        if not isinstance(collections, dict):
            raise ShopifyApiError(message="collections query response is invalid.")
        nodes = collections.get("nodes")
        if not isinstance(nodes, list):
            raise ShopifyApiError(message="collections query response is missing nodes.")
        if not nodes:
            return None
        first_node = nodes[0]
        if not isinstance(first_node, dict):
            raise ShopifyApiError(message="collections query returned an invalid collection node.")
        collection_id = first_node.get("id")
        collection_handle = first_node.get("handle")
        collection_title = first_node.get("title")
        if not isinstance(collection_id, str) or not collection_id.strip():
            raise ShopifyApiError(message="collections query response is missing collection.id.")
        if (
            not isinstance(collection_handle, str)
            or not collection_handle.strip()
            or collection_handle.strip().lower() != cleaned_handle
        ):
            raise ShopifyApiError(
                message=(
                    "collections query returned an unexpected collection handle "
                    f"while resolving handle={cleaned_handle}."
                )
            )
        if not isinstance(collection_title, str) or not collection_title.strip():
            raise ShopifyApiError(message="collections query response is missing collection.title.")
        return {
            "id": collection_id.strip(),
            "handle": collection_handle.strip(),
            "title": collection_title.strip(),
        }

    async def _get_online_store_publication_id(
        self,
        *,
        shop_domain: str,
        access_token: str,
    ) -> str:
        query = """
        query publicationsForCatalogRoute($first: Int!) {
            publications(first: $first) {
                nodes {
                    id
                    name
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={"query": query, "variables": {"first": 50}},
        )
        publications = response.get("publications")
        if not isinstance(publications, dict):
            raise ShopifyApiError(message="publications query response is invalid.")
        nodes = publications.get("nodes")
        if not isinstance(nodes, list):
            raise ShopifyApiError(message="publications query response is missing nodes.")
        for node in nodes:
            if not isinstance(node, dict):
                continue
            publication_id = node.get("id")
            publication_name = node.get("name")
            if (
                isinstance(publication_id, str)
                and publication_id.strip()
                and isinstance(publication_name, str)
                and publication_name.strip().lower() == "online store"
            ):
                return publication_id.strip()
        raise ShopifyApiError(
            message="Online Store publication was not found while preparing catalog route.",
            status_code=409,
        )

    async def _is_collection_published_on_publication(
        self,
        *,
        shop_domain: str,
        access_token: str,
        collection_id: str,
        publication_id: str,
    ) -> bool:
        cleaned_collection_id = collection_id.strip()
        cleaned_publication_id = publication_id.strip()
        if not cleaned_collection_id:
            raise ShopifyApiError(message="collection_id cannot be empty.", status_code=400)
        if not cleaned_publication_id:
            raise ShopifyApiError(message="publication_id cannot be empty.", status_code=400)
        query = """
        query collectionPublicationState($id: ID!, $publicationId: ID!) {
            collection(id: $id) {
                id
                publishedOnPublication(publicationId: $publicationId)
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": query,
                "variables": {
                    "id": cleaned_collection_id,
                    "publicationId": cleaned_publication_id,
                },
            },
        )
        collection = response.get("collection")
        if collection is None:
            raise ShopifyApiError(
                message=(
                    "Collection not found while checking publication state. "
                    f"id={cleaned_collection_id}."
                ),
                status_code=404,
            )
        if not isinstance(collection, dict):
            raise ShopifyApiError(message="collection publication query response is invalid.")
        published_on_publication = collection.get("publishedOnPublication")
        if not isinstance(published_on_publication, bool):
            raise ShopifyApiError(
                message="collection publication query response is missing publishedOnPublication."
            )
        return published_on_publication

    async def _publish_collection_to_publication(
        self,
        *,
        shop_domain: str,
        access_token: str,
        collection_id: str,
        publication_id: str,
    ) -> None:
        cleaned_collection_id = collection_id.strip()
        cleaned_publication_id = publication_id.strip()
        if not cleaned_collection_id:
            raise ShopifyApiError(message="collection_id cannot be empty.", status_code=400)
        if not cleaned_publication_id:
            raise ShopifyApiError(message="publication_id cannot be empty.", status_code=400)
        mutation = """
        mutation publishCatalogCollection($id: ID!, $input: [PublicationInput!]!) {
            publishablePublish(id: $id, input: $input) {
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
                    "id": cleaned_collection_id,
                    "input": [{"publicationId": cleaned_publication_id}],
                },
            },
        )
        payload = response.get("publishablePublish")
        if not isinstance(payload, dict):
            raise ShopifyApiError(message="publishablePublish response is missing payload.")
        user_errors = payload.get("userErrors") or []
        if not isinstance(user_errors, list):
            raise ShopifyApiError(message="publishablePublish response has invalid userErrors.")
        self._assert_no_user_errors(
            user_errors=user_errors,
            mutation_name="publishablePublish",
        )

    async def _create_collection(
        self,
        *,
        shop_domain: str,
        access_token: str,
        title: str,
        handle: str,
    ) -> dict[str, str]:
        cleaned_title = title.strip()
        cleaned_handle = handle.strip().lower()
        if not cleaned_title:
            raise ShopifyApiError(message="Collection title cannot be empty.", status_code=400)
        if not cleaned_handle:
            raise ShopifyApiError(message="Collection handle cannot be empty.", status_code=400)
        mutation = """
        mutation collectionCreateForCatalog($input: CollectionInput!) {
            collectionCreate(input: $input) {
                collection {
                    id
                    handle
                    title
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
                    "input": {
                        "title": cleaned_title,
                        "handle": cleaned_handle,
                    }
                },
            },
        )
        payload = response.get("collectionCreate")
        if not isinstance(payload, dict):
            raise ShopifyApiError(message="collectionCreate response is missing payload.")
        user_errors = payload.get("userErrors") or []
        if not isinstance(user_errors, list):
            raise ShopifyApiError(message="collectionCreate response has invalid userErrors.")
        self._assert_no_user_errors(
            user_errors=user_errors,
            mutation_name="collectionCreate",
        )
        collection = payload.get("collection")
        if not isinstance(collection, dict):
            raise ShopifyApiError(message="collectionCreate response is missing collection.")
        collection_id = collection.get("id")
        collection_handle = collection.get("handle")
        collection_title = collection.get("title")
        if not isinstance(collection_id, str) or not collection_id.strip():
            raise ShopifyApiError(message="collectionCreate response is missing collection.id.")
        if not isinstance(collection_handle, str) or not collection_handle.strip():
            raise ShopifyApiError(message="collectionCreate response is missing collection.handle.")
        if not isinstance(collection_title, str) or not collection_title.strip():
            raise ShopifyApiError(message="collectionCreate response is missing collection.title.")
        return {
            "id": collection_id.strip(),
            "handle": collection_handle.strip(),
            "title": collection_title.strip(),
        }

    async def _list_shop_product_ids(
        self,
        *,
        shop_domain: str,
        access_token: str,
    ) -> list[str]:
        query = """
        query shopProductsForCatalogRoute($first: Int!, $after: String) {
            products(first: $first, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                }
            }
        }
        """
        product_ids: list[str] = []
        cursor: str | None = None
        for _ in range(100):
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={
                    "query": query,
                    "variables": {
                        "first": _GRAPHQL_MAX_PAGE_SIZE,
                        "after": cursor,
                    },
                },
            )
            products = response.get("products")
            if not isinstance(products, dict):
                raise ShopifyApiError(message="products query response is invalid.")
            nodes = products.get("nodes")
            if not isinstance(nodes, list):
                raise ShopifyApiError(message="products query response is missing nodes.")
            for node in nodes:
                if not isinstance(node, dict):
                    raise ShopifyApiError(
                        message="products query returned an invalid product node."
                    )
                product_id = node.get("id")
                if not isinstance(product_id, str) or not product_id.strip():
                    raise ShopifyApiError(
                        message="products query response is missing product.id."
                    )
                product_ids.append(product_id.strip())

            page_info = products.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ShopifyApiError(message="products query response is missing pageInfo.")
            has_next_page = page_info.get("hasNextPage")
            if not isinstance(has_next_page, bool):
                raise ShopifyApiError(
                    message="products query response is missing pageInfo.hasNextPage."
                )
            if not has_next_page:
                return product_ids
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor.strip():
                raise ShopifyApiError(
                    message="products query response is missing pageInfo.endCursor."
                )
            cursor = end_cursor
        raise ShopifyApiError(
            message="products query exceeded pagination limit while loading shop products."
        )

    async def _list_collection_product_ids(
        self,
        *,
        shop_domain: str,
        access_token: str,
        collection_id: str,
    ) -> list[str]:
        cleaned_collection_id = collection_id.strip()
        if not cleaned_collection_id:
            raise ShopifyApiError(message="collection_id cannot be empty.", status_code=400)
        query = """
        query collectionProductsForCatalogRoute($id: ID!, $first: Int!, $after: String) {
            collection(id: $id) {
                id
                products(first: $first, after: $after) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        id
                    }
                }
            }
        }
        """
        collection_product_ids: list[str] = []
        cursor: str | None = None
        for _ in range(100):
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={
                    "query": query,
                    "variables": {
                        "id": cleaned_collection_id,
                        "first": _GRAPHQL_MAX_PAGE_SIZE,
                        "after": cursor,
                    },
                },
            )
            collection = response.get("collection")
            if collection is None:
                raise ShopifyApiError(
                    message=f"Collection not found while loading collection products. id={cleaned_collection_id}.",
                    status_code=404,
                )
            if not isinstance(collection, dict):
                raise ShopifyApiError(message="collection query response is invalid.")
            products = collection.get("products")
            if not isinstance(products, dict):
                raise ShopifyApiError(
                    message="collection query response is missing collection.products."
                )
            nodes = products.get("nodes")
            if not isinstance(nodes, list):
                raise ShopifyApiError(
                    message="collection query response is missing collection.products.nodes."
                )
            for node in nodes:
                if not isinstance(node, dict):
                    raise ShopifyApiError(
                        message="collection query returned an invalid collection product node."
                    )
                product_id = node.get("id")
                if not isinstance(product_id, str) or not product_id.strip():
                    raise ShopifyApiError(
                        message="collection query response is missing collection product id."
                    )
                collection_product_ids.append(product_id.strip())

            page_info = products.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ShopifyApiError(
                    message="collection query response is missing collection.products.pageInfo."
                )
            has_next_page = page_info.get("hasNextPage")
            if not isinstance(has_next_page, bool):
                raise ShopifyApiError(
                    message=(
                        "collection query response is missing collection.products.pageInfo.hasNextPage."
                    )
                )
            if not has_next_page:
                return collection_product_ids
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor.strip():
                raise ShopifyApiError(
                    message=(
                        "collection query response is missing collection.products.pageInfo.endCursor."
                    )
                )
            cursor = end_cursor
        raise ShopifyApiError(
            message="collection query exceeded pagination limit while loading collection products."
        )

    async def _add_products_to_collection(
        self,
        *,
        shop_domain: str,
        access_token: str,
        collection_id: str,
        product_ids: list[str],
    ) -> None:
        cleaned_collection_id = collection_id.strip()
        if not cleaned_collection_id:
            raise ShopifyApiError(message="collection_id cannot be empty.", status_code=400)
        if not product_ids:
            return
        mutation = """
        mutation collectionAddProductsForCatalog($id: ID!, $productIds: [ID!]!) {
            collectionAddProducts(id: $id, productIds: $productIds) {
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
                    "id": cleaned_collection_id,
                    "productIds": product_ids,
                },
            },
        )
        payload = response.get("collectionAddProducts")
        if not isinstance(payload, dict):
            raise ShopifyApiError(message="collectionAddProducts response is missing payload.")
        user_errors = payload.get("userErrors") or []
        if not isinstance(user_errors, list):
            raise ShopifyApiError(
                message="collectionAddProducts response has invalid userErrors."
            )
        self._assert_no_user_errors(
            user_errors=user_errors,
            mutation_name="collectionAddProducts",
        )

    async def ensure_product_in_catalog_collection(
        self,
        *,
        shop_domain: str,
        access_token: str,
        product_gid: str,
    ) -> dict[str, Any]:
        cleaned_product_gid = product_gid.strip()
        if not cleaned_product_gid.startswith("gid://shopify/Product/"):
            raise ShopifyApiError(
                message="product_gid must be a valid Shopify Product GID.",
                status_code=400,
            )
        return await self.ensure_catalog_collection_contains_products(
            shop_domain=shop_domain,
            access_token=access_token,
            product_gids=[cleaned_product_gid],
        )

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

        await self.ensure_product_in_catalog_collection(
            shop_domain=shop_domain,
            access_token=access_token,
            product_gid=product_gid,
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

    @staticmethod
    def _canonicalize_menu_item_path_for_dedupe(*, path: str) -> str:
        normalized = path.strip().lower()
        policy_match = re.fullmatch(
            r"/policies/([a-z0-9]+(?:-[a-z0-9]+)*)", normalized
        )
        if policy_match is not None:
            return f"/pages/{policy_match.group(1)}"
        return normalized

    @classmethod
    def _build_menu_item_dedupe_keys(
        cls,
        *,
        item: dict[str, Any],
    ) -> tuple[str, ...]:
        keys: list[str] = []
        resource_id = item.get("resourceId")
        if isinstance(resource_id, str) and resource_id:
            item_type = item.get("type")
            normalized_type = (
                item_type.strip().upper()
                if isinstance(item_type, str) and item_type.strip()
                else "UNKNOWN"
            )
            keys.append(f"resource:{normalized_type}:{resource_id}")

        normalized_path = cls._normalize_menu_item_path(item.get("url"))
        if normalized_path is not None:
            canonical_path = cls._canonicalize_menu_item_path_for_dedupe(
                path=normalized_path
            )
            keys.append(f"url:{canonical_path}")

        return tuple(keys)

    @classmethod
    def _dedupe_menu_items(
        cls,
        *,
        menu_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        deduped_items: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        changed = False

        for item in menu_items:
            if not isinstance(item, dict):
                deduped_items.append(item)
                continue

            raw_children = item.get("items")
            if isinstance(raw_children, list):
                deduped_children, child_changed = cls._dedupe_menu_items(
                    menu_items=raw_children
                )
                if child_changed:
                    item["items"] = deduped_children
                    changed = True

            dedupe_keys = cls._build_menu_item_dedupe_keys(item=item)
            if dedupe_keys and any(key in seen_keys for key in dedupe_keys):
                changed = True
                continue
            for key in dedupe_keys:
                seen_keys.add(key)
            deduped_items.append(item)

        return deduped_items, changed

    @staticmethod
    def _normalize_menu_item_title_for_matching(*, title: Any) -> str | None:
        if not isinstance(title, str):
            return None
        normalized_title = " ".join(title.strip().split()).lower()
        if not normalized_title:
            return None
        return normalized_title

    @classmethod
    def _find_matching_menu_item_index(
        cls,
        *,
        menu_items: list[dict[str, Any]],
        aliases: tuple[str, ...],
        used_indexes: set[int],
    ) -> int | None:
        normalized_aliases = {
            alias.strip().lower() for alias in aliases if isinstance(alias, str)
        }
        if not normalized_aliases:
            return None
        for index, item in enumerate(menu_items):
            if index in used_indexes:
                continue
            normalized_title = cls._normalize_menu_item_title_for_matching(
                title=item.get("title")
            )
            if normalized_title in normalized_aliases:
                return index
        return None

    @classmethod
    def _normalize_required_navigation_menu_items(
        cls,
        *,
        menu_items: list[dict[str, Any]],
        required_items: tuple[dict[str, Any], ...],
    ) -> tuple[list[dict[str, Any]], bool]:
        validated_items: list[dict[str, Any]] = []
        for item in menu_items:
            if not isinstance(item, dict):
                raise ShopifyApiError(
                    message="Cannot sync storefront navigation because a menu item is invalid.",
                    status_code=409,
                )
            next_item = deepcopy(item)
            raw_children = next_item.get("items")
            if raw_children is not None and not isinstance(raw_children, list):
                raise ShopifyApiError(
                    message=(
                        "Cannot sync storefront navigation because a menu item has "
                        "invalid nested items."
                    ),
                    status_code=409,
                )
            validated_items.append(next_item)

        next_items: list[dict[str, Any]] = []
        used_indexes: set[int] = set()
        selected_indexes: list[int] = []
        changed = False

        for required_item in required_items:
            required_title = required_item["title"]
            required_type = required_item["type"]
            required_url = required_item["url"]
            required_resource_id = required_item["resourceId"]
            aliases = tuple(required_item.get("aliases") or ())

            matching_index = cls._find_matching_menu_item_index(
                menu_items=validated_items,
                aliases=aliases,
                used_indexes=used_indexes,
            )
            if matching_index is None:
                next_items.append(
                    {
                        "title": required_title,
                        "type": required_type,
                        "url": required_url,
                        "resourceId": required_resource_id,
                        "tags": [],
                        "items": [],
                    }
                )
                changed = True
                continue

            used_indexes.add(matching_index)
            selected_indexes.append(matching_index)
            next_item = validated_items[matching_index]
            original_type = next_item.get("type")
            original_url = next_item.get("url")
            original_resource_id = next_item.get("resourceId")

            if next_item.get("title") != required_title:
                next_item["title"] = required_title
                changed = True
            if next_item.get("type") != required_type:
                next_item["type"] = required_type
                changed = True
            if next_item.get("url") != required_url:
                next_item["url"] = required_url
                changed = True
            if next_item.get("resourceId") != required_resource_id:
                next_item["resourceId"] = required_resource_id
                changed = True
            if next_item.get("items") != []:
                next_item["items"] = []
                changed = True
            if "tags" not in next_item:
                next_item["tags"] = []
                changed = True

            if (
                (
                    original_type != required_type
                    or original_url != required_url
                    or original_resource_id != required_resource_id
                )
                and isinstance(next_item.get("id"), str)
            ):
                next_item.pop("id", None)
                changed = True

            next_items.append(next_item)

        if len(used_indexes) != len(validated_items):
            changed = True
        if selected_indexes != sorted(selected_indexes):
            changed = True

        return next_items, changed

    @classmethod
    def _normalize_catalog_menu_items(
        cls,
        *,
        menu_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        return cls._normalize_required_navigation_menu_items(
            menu_items=menu_items,
            required_items=_DEFAULT_MAIN_MENU_ITEMS,
        )

    @classmethod
    def _normalize_footer_quick_links_menu_items(
        cls,
        *,
        menu_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        return cls._normalize_required_navigation_menu_items(
            menu_items=menu_items,
            required_items=_DEFAULT_FOOTER_QUICK_LINKS_ITEMS,
        )

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
            normalized_title = title.strip()
            if not normalized_title:
                raise ShopifyApiError(
                    message=(
                        "Cannot sync footer menu because an existing menu item has "
                        "an empty title."
                    ),
                    status_code=409,
                )
            normalized_type = item_type.strip().upper()
            if not normalized_type:
                raise ShopifyApiError(
                    message=(
                        "Cannot sync footer menu because an existing menu item has "
                        "an empty type."
                    ),
                    status_code=409,
                )
            converted: dict[str, Any] = {
                "title": normalized_title,
                "type": normalized_type,
            }
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                converted["id"] = item_id
            item_url = item.get("url")
            if isinstance(item_url, str):
                normalized_url = item_url.strip()
                if normalized_url:
                    converted["url"] = normalized_url
            resource_id = item.get("resourceId")
            if isinstance(resource_id, str):
                normalized_resource_id = resource_id.strip()
                if normalized_resource_id:
                    converted["resourceId"] = normalized_resource_id

            has_url = isinstance(converted.get("url"), str)
            has_resource_id = isinstance(converted.get("resourceId"), str)
            force_recreate = False
            if normalized_type == "HTTP":
                if not has_url:
                    raise ShopifyApiError(
                        message=(
                            "Cannot sync footer menu because menu item "
                            f"{normalized_title!r} has type HTTP without a URL."
                        ),
                        status_code=409,
                    )
                if has_resource_id:
                    # HTTP items should not carry a resource binding in update payloads.
                    converted.pop("resourceId", None)
                    has_resource_id = False
                    force_recreate = True
            elif has_url:
                # Keep update payloads URL-based for non-HTTP entries to avoid
                # resource subject validation failures on menuUpdate.
                converted["type"] = "HTTP"
                converted.pop("resourceId", None)
                has_resource_id = False
                force_recreate = True
            elif not has_resource_id:
                raise ShopifyApiError(
                    message=(
                        "Cannot sync footer menu because menu item "
                        f"{normalized_title!r} (type {normalized_type}) is missing both "
                        "resourceId and URL."
                    ),
                    status_code=409,
                )
            if force_recreate:
                # Recreate items when transitioning resource bindings/types to avoid
                # Shopify rejecting in-place updates with ambiguous subject errors.
                converted.pop("id", None)
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
        normalized_policy_pages: list[dict[str, str]] = []
        expected_policy_resource_ids: set[str] = set()
        expected_policy_paths: set[str] = set()
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

            expected_path = cls._build_policy_page_path(handle=raw_handle)
            canonical_path = cls._canonicalize_menu_item_path_for_dedupe(
                path=expected_path
            )
            expected_policy_resource_ids.add(raw_page_id)
            expected_policy_paths.add(canonical_path)
            normalized_policy_pages.append(
                {
                    "pageId": raw_page_id,
                    "title": raw_title.strip(),
                    "handle": raw_handle.strip(),
                    "path": expected_path,
                    "canonicalPath": canonical_path,
                }
            )

        changed = False
        filtered_items: list[dict[str, Any]] = []
        for item in next_items:
            normalized_path = cls._normalize_menu_item_path(item.get("url"))
            canonical_path = (
                cls._canonicalize_menu_item_path_for_dedupe(path=normalized_path)
                if normalized_path is not None
                else None
            )
            if canonical_path in _DEFAULT_FOOTER_QUICK_LINK_CANONICAL_PATHS:
                changed = True
                continue

            if canonical_path not in _MANAGED_POLICY_CANONICAL_PATHS:
                filtered_items.append(item)
                continue

            resource_id = item.get("resourceId")
            has_matching_resource_id = (
                isinstance(resource_id, str) and resource_id in expected_policy_resource_ids
            )
            has_matching_path = canonical_path in expected_policy_paths
            if has_matching_resource_id or has_matching_path:
                filtered_items.append(item)
                continue

            changed = True
        next_items = filtered_items

        existing_by_resource_id: dict[str, dict[str, Any]] = {}
        existing_by_path: dict[str, dict[str, Any]] = {}
        for item in next_items:
            resource_id = item.get("resourceId")
            if isinstance(resource_id, str) and resource_id:
                existing_by_resource_id.setdefault(resource_id, item)
            normalized_path = cls._normalize_menu_item_path(item.get("url"))
            if normalized_path is not None:
                canonical_path = cls._canonicalize_menu_item_path_for_dedupe(
                    path=normalized_path
                )
                existing_by_path.setdefault(canonical_path, item)

        for policy_page in normalized_policy_pages:
            page_id = policy_page["pageId"]
            title = policy_page["title"]
            path = policy_page["path"]
            canonical_path = policy_page["canonicalPath"]
            existing_item = existing_by_resource_id.get(page_id)
            if existing_item is None:
                existing_item = existing_by_path.get(canonical_path)

            if existing_item is None:
                existing_item = {
                    "title": title,
                    "type": "PAGE",
                    "url": path,
                    "resourceId": page_id,
                    "items": [],
                }
                next_items.append(existing_item)
                existing_by_resource_id[page_id] = existing_item
                existing_by_path[canonical_path] = existing_item
                changed = True

            if existing_item.get("title") != title:
                existing_item["title"] = title
                changed = True
            if existing_item.get("type") != "PAGE":
                existing_item["type"] = "PAGE"
                changed = True
            if existing_item.get("resourceId") != page_id:
                existing_item["resourceId"] = page_id
                changed = True
            if existing_item.get("url") != path:
                existing_item["url"] = path
                changed = True

        search_item: dict[str, Any] | None = None
        for item in next_items:
            normalized_path = cls._normalize_menu_item_path(item.get("url"))
            if normalized_path != _POLICY_MENU_SEARCH_PATH:
                continue
            search_item = item
            break
        if search_item is None:
            next_items.append(
                {
                    "title": _POLICY_MENU_SEARCH_TITLE,
                    "type": "HTTP",
                    "url": _POLICY_MENU_SEARCH_PATH,
                    "resourceId": None,
                    "items": [],
                }
            )
            changed = True
        else:
            if search_item.get("title") != _POLICY_MENU_SEARCH_TITLE:
                search_item["title"] = _POLICY_MENU_SEARCH_TITLE
                changed = True
            if search_item.get("type") != "HTTP":
                search_item["type"] = "HTTP"
                changed = True
            if search_item.get("url") != _POLICY_MENU_SEARCH_PATH:
                search_item["url"] = _POLICY_MENU_SEARCH_PATH
                changed = True
            if search_item.get("resourceId") is not None:
                search_item["resourceId"] = None
                changed = True
            if search_item.get("items") != []:
                search_item["items"] = []
                changed = True

        selected_policy_indexes: list[int] = []
        used_policy_indexes: set[int] = set()
        for policy_page in normalized_policy_pages:
            page_id = policy_page["pageId"]
            canonical_path = policy_page["canonicalPath"]
            for index, item in enumerate(next_items):
                if index in used_policy_indexes:
                    continue
                resource_id = item.get("resourceId")
                if isinstance(resource_id, str) and resource_id == page_id:
                    selected_policy_indexes.append(index)
                    used_policy_indexes.add(index)
                    break
                normalized_path = cls._normalize_menu_item_path(item.get("url"))
                if normalized_path is None:
                    continue
                item_canonical_path = cls._canonicalize_menu_item_path_for_dedupe(
                    path=normalized_path
                )
                if item_canonical_path == canonical_path:
                    selected_policy_indexes.append(index)
                    used_policy_indexes.add(index)
                    break

        if selected_policy_indexes:
            reordered_items: list[dict[str, Any]] = []
            for index, item in enumerate(next_items):
                if index in used_policy_indexes:
                    continue
                normalized_path = cls._normalize_menu_item_path(item.get("url"))
                canonical_path = (
                    cls._canonicalize_menu_item_path_for_dedupe(path=normalized_path)
                    if normalized_path is not None
                    else None
                )
                if canonical_path in expected_policy_paths:
                    changed = True
                    continue
                reordered_items.append(item)
            reordered_items.extend(next_items[index] for index in selected_policy_indexes)
            if reordered_items != next_items:
                changed = True
                next_items = reordered_items

        deduped_items, dedupe_changed = cls._dedupe_menu_items(menu_items=next_items)
        if dedupe_changed:
            changed = True
            next_items = deduped_items

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

    async def normalize_catalog_in_default_store_navigation(
        self,
        *,
        shop_domain: str,
        access_token: str,
    ) -> dict[str, Any]:
        all_menus = await self._list_shop_menus(
            shop_domain=shop_domain,
            access_token=access_token,
        )
        menu_definitions: tuple[tuple[str, str], ...] = (
            (_DEFAULT_STORE_NAVIGATION_MENU_HANDLE, "main"),
            (_DEFAULT_FOOTER_QUICK_LINKS_MENU_HANDLE, "footer"),
        )
        menu_summaries_by_handle: dict[str, list[dict[str, str]]] = {}
        for menu in all_menus:
            menu_summaries_by_handle.setdefault(menu["handle"], []).append(menu)

        menu_results: list[dict[str, Any]] = []
        for menu_handle, menu_kind in menu_definitions:
            matching_menus = menu_summaries_by_handle.get(menu_handle, [])
            if not matching_menus:
                menu_results.append(
                    {
                        "handle": menu_handle,
                        "updated": False,
                        "reason": "menu_not_found",
                    }
                )
                continue
            if len(matching_menus) > 1:
                menu_ids = ", ".join(menu["id"] for menu in matching_menus)
                raise ShopifyApiError(
                    message=(
                        "Multiple menus matched the default storefront navigation handle. "
                        f"handle={menu_handle}, matchedMenuIds={menu_ids}"
                    ),
                    status_code=409,
                )

            menu_summary = matching_menus[0]
            menu_details = await self._load_menu_details(
                shop_domain=shop_domain,
                access_token=access_token,
                menu_id=menu_summary["id"],
            )
            if menu_kind == "main":
                next_items, changed = self._normalize_catalog_menu_items(
                    menu_items=menu_details["items"]
                )
            else:
                next_items, changed = self._normalize_footer_quick_links_menu_items(
                    menu_items=menu_details["items"]
                )
            if not changed:
                menu_results.append(
                    {
                        "handle": menu_details["handle"],
                        "updated": False,
                        "reason": "already_normalized",
                    }
                )
                continue

            await self._update_menu(
                shop_domain=shop_domain,
                access_token=access_token,
                menu_id=menu_details["id"],
                title=menu_details["title"],
                handle=menu_details["handle"],
                items=next_items,
            )
            menu_results.append(
                {
                    "handle": menu_details["handle"],
                    "updated": True,
                    "reason": "normalized",
                }
            )

        updated = any(result["updated"] for result in menu_results)
        if updated:
            reason = "catalog_normalized"
        elif all(result["reason"] == "menu_not_found" for result in menu_results):
            reason = "menu_not_found"
        else:
            reason = "catalog_not_present"

        return {
            "handle": _DEFAULT_STORE_NAVIGATION_MENU_HANDLE,
            "updated": updated,
            "reason": reason,
            "menuResults": menu_results,
        }

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
        formatted_errors: list[str] = []
        for error in user_errors:
            message = str(error.get("message"))
            field = error.get("field")
            if isinstance(field, list) and field:
                field_path = ".".join(str(part) for part in field)
                formatted_errors.append(f"{message} (field: {field_path})")
            else:
                formatted_errors.append(message)
        messages = "; ".join(formatted_errors)
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

    @staticmethod
    def _normalize_css_value_for_comparison(raw_value: str) -> str:
        return re.sub(r"\s+", "", raw_value.strip().lower())

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

        if profile.theme_name == "futrgroup2-0theme":
            # Hero-adjacent component backgrounds should track hero bg even when
            # the source token omitted it.
            if "--hero-bg" not in expanded and "--color-page-bg" in expanded:
                expanded["--hero-bg"] = expanded["--color-page-bg"]

            footer_text = expanded.get("--footer-text-color")
            if not isinstance(footer_text, str) or not footer_text.strip():
                color_text = expanded.get("--color-text")
                if isinstance(color_text, str) and color_text.strip():
                    expanded["--footer-text-color"] = color_text
            announcement_text = expanded.get("--announcement-text-color")
            if not isinstance(announcement_text, str) or not announcement_text.strip():
                footer_text_value = expanded.get("--footer-text-color")
                if isinstance(footer_text_value, str) and footer_text_value.strip():
                    expanded["--announcement-text-color"] = footer_text_value
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

    @classmethod
    def _is_theme_template_settings_path_disabled(
        cls,
        *,
        template_data: Any,
        path: str,
    ) -> bool:
        if not isinstance(template_data, dict):
            return False
        tokens = cls._parse_settings_path_tokens(path)
        if len(tokens) < 2 or tokens[0] != ("sections", None):
            return False

        sections = template_data.get("sections")
        if not isinstance(sections, dict):
            return False

        section_id, section_index = tokens[1]
        if section_index is not None:
            return False
        section = sections.get(section_id)
        if not isinstance(section, dict):
            return False
        if section.get("disabled") is True:
            return True

        if len(tokens) < 4 or tokens[2] != ("blocks", None):
            return False

        block_id, block_index = tokens[3]
        if block_index is not None:
            return False
        blocks = section.get("blocks")
        if not isinstance(blocks, dict):
            return False
        block = blocks.get(block_id)
        return isinstance(block, dict) and block.get("disabled") is True

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
    def _resolve_theme_css_value_expression(
        cls,
        *,
        effective_css_vars: dict[str, str],
        raw_value: str,
        source_var: str,
        path: str,
        context: str,
        stack: list[str],
    ) -> str:
        cleaned_value = raw_value.strip()
        if not cleaned_value:
            raise ShopifyApiError(
                message=(
                    f"{context} requires css var {source_var} for path {path} to be non-empty."
                ),
                status_code=422,
            )

        match = _THEME_SETTINGS_CSS_VAR_CAPTURE_RE.fullmatch(cleaned_value)
        if match is None:
            return cleaned_value

        referenced_var = match.group(1)
        fallback_value = match.group(2)
        if referenced_var in stack:
            chain = " -> ".join([*stack, referenced_var])
            raise ShopifyApiError(
                message=(
                    f"{context} detected a circular css var reference while resolving {source_var} "
                    f"for path {path}: {chain}."
                ),
                status_code=422,
            )

        referenced_raw_value = effective_css_vars.get(referenced_var)
        if referenced_raw_value is None:
            fallback_clean = (
                fallback_value.strip()
                if isinstance(fallback_value, str)
                else ""
            )
            if fallback_clean:
                return cls._resolve_theme_css_value_expression(
                    effective_css_vars=effective_css_vars,
                    raw_value=fallback_clean,
                    source_var=source_var,
                    path=path,
                    context=context,
                    stack=[*stack, referenced_var],
                )
            raise ShopifyApiError(
                message=(
                    f"{context} requires css var {source_var} for path {path}, but {source_var} "
                    f"references missing token {referenced_var} with no fallback."
                ),
                status_code=422,
            )

        if not isinstance(referenced_raw_value, str):
            raise ShopifyApiError(
                message=(
                    f"{context} requires css var {source_var} for path {path} to resolve to a string value, "
                    f"but referenced token {referenced_var} is {type(referenced_raw_value).__name__}."
                ),
                status_code=422,
            )

        return cls._resolve_theme_css_value_expression(
            effective_css_vars=effective_css_vars,
            raw_value=referenced_raw_value,
            source_var=source_var,
            path=path,
            context=context,
            stack=[*stack, referenced_var],
        )

    @classmethod
    def _resolve_theme_settings_color_source_value(
        cls,
        *,
        effective_css_vars: dict[str, str],
        source_var: str,
        path: str,
        context: str,
    ) -> str:
        raw_value = effective_css_vars.get(source_var)
        if raw_value is None:
            raise ShopifyApiError(
                message=(
                    f"{context} requires css var {source_var} for path {path}. "
                    "Add the missing token to the design system."
                ),
                status_code=422,
            )
        if not isinstance(raw_value, str):
            raise ShopifyApiError(
                message=(
                    f"{context} requires css var {source_var} for path {path} to be a string value, "
                    f"received {type(raw_value).__name__}."
                ),
                status_code=422,
            )

        resolved_value = cls._resolve_theme_css_value_expression(
            effective_css_vars=effective_css_vars,
            raw_value=raw_value,
            source_var=source_var,
            path=path,
            context=context,
            stack=[source_var],
        )
        if _THEME_SETTINGS_CSS_VAR_RE.fullmatch(resolved_value):
            raise ShopifyApiError(
                message=(
                    f"{context} requires css var {source_var} for path {path} to resolve to a concrete CSS color, "
                    f"received {resolved_value!r}."
                ),
                status_code=422,
            )
        if not cls._is_theme_settings_color_like_value(value=resolved_value):
            raise ShopifyApiError(
                message=(
                    f"{context} requires css var {source_var} for path {path} to resolve to a CSS color value, "
                    f"received {resolved_value!r}."
                ),
                status_code=422,
            )
        return resolved_value

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
            and "border" in key_tokens
            and ({"color", "text", "foreground"} & key_tokens)
        ):
            return "footer_text"
        if (
            "footer_text" in semantic_source_vars
            and "footer" in path_tokens
            and "newsletter" in key_tokens
            and ({"color", "text", "foreground"} & key_tokens)
        ):
            return "footer_text"
        if (
            "footer_text" in semantic_source_vars
            and "footer" in path_tokens
            and ({"copy", "input", "text"} & key_tokens)
            and ({"color", "text", "foreground"} & key_tokens)
            and not ({"background", "bg", "border"} & key_tokens)
        ):
            return "footer_text"
        if (
            "footer_text" in semantic_source_vars
            and "footer" in path_tokens
            and "link" in key_tokens
            and ({"color", "text", "foreground"} & key_tokens)
            and not ({"background", "bg", "border"} & key_tokens)
        ):
            return "footer_text"
        if (
            "footer_text" in semantic_source_vars
            and "footer" in path_tokens
            and ({"submit", "button"} & key_tokens)
            and "border" in key_tokens
            and ({"color", "text", "foreground"} & key_tokens)
        ):
            return "footer_text"
        if (
            "footer_text" in semantic_source_vars
            and "footer" in path_tokens
            and ({"input", "tabs", "tab"} & key_tokens)
            and "border" in key_tokens
            and ({"color", "text", "foreground"} & key_tokens)
        ):
            return "footer_text"
        if (
            "hero_background" in semantic_source_vars
            and ({"hero", "banner"} & path_tokens)
            and ({"background", "bg"} & key_tokens)
            and "border" not in key_tokens
            and not ({"button", "submit", "cta"} & key_tokens)
        ):
            return "hero_background"
        if (
            "button" in semantic_source_vars
            and "announcement" in path_tokens
            and ({"background", "bg"} & key_tokens)
            and "border" not in key_tokens
        ):
            return "button"
        if (
            ("announcement_text" in semantic_source_vars or "text" in semantic_source_vars)
            and "announcement" in path_tokens
            and ({"text", "foreground"} & key_tokens)
            and "color" in key_tokens
            and not ({"background", "bg", "border"} & key_tokens)
        ):
            if "announcement_text" in semantic_source_vars:
                return "announcement_text"
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
            expected_value = cls._resolve_theme_settings_color_source_value(
                effective_css_vars=effective_css_vars,
                source_var=source_var,
                path=path,
                context="Theme settings semantic mapping",
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
            try:
                expected_value = cls._resolve_theme_settings_color_source_value(
                    effective_css_vars=effective_css_vars,
                    source_var=source_var,
                    path=path,
                    context="Theme settings semantic audit",
                )
            except ShopifyApiError:
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
            expected_value = cls._resolve_theme_settings_color_source_value(
                effective_css_vars=effective_css_vars,
                source_var=source_var,
                path=path,
                context="Theme template settings mapping",
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
            try:
                expected_value = cls._resolve_theme_settings_color_source_value(
                    effective_css_vars=effective_css_vars,
                    source_var=source_var,
                    path=path,
                    context="Theme template settings audit",
                )
            except ShopifyApiError:
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
    def _coerce_theme_template_order_entries(cls, *, raw_order: Any) -> list[str]:
        if not isinstance(raw_order, list):
            return []
        ordered_entries: list[str] = []
        seen_entries: set[str] = set()
        for item in raw_order:
            if not isinstance(item, str):
                continue
            cleaned_item = item.strip()
            if not cleaned_item or cleaned_item in seen_entries:
                continue
            seen_entries.add(cleaned_item)
            ordered_entries.append(cleaned_item)
        return ordered_entries

    @classmethod
    def _extract_theme_template_slot_location(
        cls, *, setting_path: str
    ) -> tuple[str, str | None, str | None]:
        template_filename, json_path = cls._split_theme_template_setting_path(
            setting_path=setting_path
        )
        tokens = [token.strip() for token in json_path.split(".") if token.strip()]
        if len(tokens) < 2 or tokens[0] != "sections":
            return template_filename, None, None
        section_id = tokens[1]
        if len(tokens) >= 4 and tokens[2] == "blocks":
            return template_filename, section_id, tokens[3]
        return template_filename, section_id, None

    @classmethod
    def _build_theme_template_render_order_maps(
        cls, *, template_contents_by_filename: dict[str, str]
    ) -> tuple[
        dict[str, int],
        dict[tuple[str, str], int],
        dict[tuple[str, str, str], int],
    ]:
        template_filenames = sorted(template_contents_by_filename.keys())
        template_rank_by_filename = {
            template_filename: index
            for index, template_filename in enumerate(template_filenames)
        }
        section_rank_by_key: dict[tuple[str, str], int] = {}
        block_rank_by_key: dict[tuple[str, str, str], int] = {}

        for template_filename in template_filenames:
            template_content = template_contents_by_filename.get(template_filename)
            if template_content is None:
                continue
            template_data = cls._parse_theme_template_json(
                filename=template_filename,
                template_content=template_content,
            )
            sections_node = template_data.get("sections")
            if not isinstance(sections_node, dict):
                continue

            ordered_section_ids: list[str] = []
            section_ids_seen: set[str] = set()
            for section_id in cls._coerce_theme_template_order_entries(
                raw_order=template_data.get("order")
            ):
                if section_id in sections_node and section_id not in section_ids_seen:
                    section_ids_seen.add(section_id)
                    ordered_section_ids.append(section_id)
            for section_id in sections_node.keys():
                if (
                    isinstance(section_id, str)
                    and section_id
                    and section_id not in section_ids_seen
                ):
                    section_ids_seen.add(section_id)
                    ordered_section_ids.append(section_id)

            for section_index, section_id in enumerate(ordered_section_ids):
                section_rank_by_key[(template_filename, section_id)] = section_index
                section_node = sections_node.get(section_id)
                if not isinstance(section_node, dict):
                    continue
                blocks_node = section_node.get("blocks")
                if not isinstance(blocks_node, dict):
                    continue

                ordered_block_ids: list[str] = []
                block_ids_seen: set[str] = set()
                for raw_order in (
                    section_node.get("block_order"),
                    section_node.get("order"),
                ):
                    for block_id in cls._coerce_theme_template_order_entries(
                        raw_order=raw_order
                    ):
                        if block_id in blocks_node and block_id not in block_ids_seen:
                            block_ids_seen.add(block_id)
                            ordered_block_ids.append(block_id)
                for block_id in blocks_node.keys():
                    if (
                        isinstance(block_id, str)
                        and block_id
                        and block_id not in block_ids_seen
                    ):
                        block_ids_seen.add(block_id)
                        ordered_block_ids.append(block_id)

                for block_index, block_id in enumerate(ordered_block_ids):
                    block_rank_by_key[(template_filename, section_id, block_id)] = (
                        block_index
                    )

        return template_rank_by_filename, section_rank_by_key, block_rank_by_key

    @classmethod
    def _sort_theme_template_image_slots_by_render_order(
        cls,
        *,
        image_slots: list[dict[str, Any]],
        template_contents_by_filename: dict[str, str],
    ) -> list[dict[str, Any]]:
        if not image_slots:
            return []

        (
            template_rank_by_filename,
            section_rank_by_key,
            block_rank_by_key,
        ) = cls._build_theme_template_render_order_maps(
            template_contents_by_filename=template_contents_by_filename
        )
        max_rank = 10**9
        manifest_rank_by_path = {
            str(item["path"]): index
            for index, item in enumerate(image_slots)
            if isinstance(item.get("path"), str) and str(item["path"]).strip()
        }

        def sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
            path = item.get("path")
            if not isinstance(path, str) or not path.strip():
                return max_rank, max_rank, max_rank, max_rank, ""
            normalized_path = path.strip()
            template_filename, section_id, block_id = (
                cls._extract_theme_template_slot_location(setting_path=normalized_path)
            )
            template_rank = template_rank_by_filename.get(template_filename, max_rank)
            if section_id:
                section_rank = section_rank_by_key.get(
                    (template_filename, section_id), max_rank
                )
            else:
                section_rank = max_rank
            if block_id:
                block_rank = block_rank_by_key.get(
                    (template_filename, section_id or "", block_id), max_rank
                )
            else:
                block_rank = -1
            manifest_rank = manifest_rank_by_path.get(normalized_path, max_rank)
            return (
                template_rank,
                section_rank,
                block_rank,
                manifest_rank,
                normalized_path,
            )

        return sorted(image_slots, key=sort_key)

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
    def _get_optional_theme_template_slot_paths_from_manifest(
        cls, *, profile: ThemeBrandProfile
    ) -> tuple[set[str], set[str]]:
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

        optional_image_paths: set[str] = set()
        optional_text_paths: set[str] = set()

        for slot_type, raw_slots in (
            ("imageSlots", raw_image_slots),
            ("textSlots", raw_text_slots),
        ):
            for item in raw_slots:
                if not isinstance(item, dict):
                    raise ShopifyApiError(
                        message=(
                            "Theme template slot manifest contains an invalid slot entry. "
                            f"themeName={profile.theme_name}, slotType={slot_type}."
                        ),
                        status_code=500,
                    )
                path = item.get("path")
                allow_missing = item.get("allowMissing", False)
                if not isinstance(path, str) or not path.strip():
                    raise ShopifyApiError(
                        message=(
                            "Theme template slot manifest contains an invalid path entry. "
                            f"themeName={profile.theme_name}, slotType={slot_type}, slot={item}."
                        ),
                        status_code=500,
                    )
                if not isinstance(allow_missing, bool):
                    raise ShopifyApiError(
                        message=(
                            "Theme template slot manifest contains an invalid allowMissing value. "
                            f"themeName={profile.theme_name}, slotType={slot_type}, slot={item}."
                        ),
                        status_code=500,
                    )
                if not allow_missing:
                    continue
                if slot_type == "imageSlots":
                    optional_image_paths.add(path.strip())
                else:
                    optional_text_paths.add(path.strip())

        return optional_image_paths, optional_text_paths

    @classmethod
    def _get_richtext_theme_template_slot_paths_from_manifest(
        cls, *, profile: ThemeBrandProfile
    ) -> set[str]:
        manifest = cls._get_theme_template_slot_manifest(profile=profile)
        raw_text_slots = manifest.get("textSlots")
        if not isinstance(raw_text_slots, tuple):
            raise ShopifyApiError(
                message=(
                    "Theme template slot manifest is invalid. "
                    f"themeName={profile.theme_name}."
                ),
                status_code=500,
            )

        richtext_paths: set[str] = set()
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
            rich_text = item.get("richText", False)
            if not isinstance(path, str) or not path.strip():
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid text slot path. "
                        f"themeName={profile.theme_name}, slot={item}."
                    ),
                    status_code=500,
                )
            if not isinstance(rich_text, bool):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid richText value. "
                        f"themeName={profile.theme_name}, slot={item}."
                    ),
                    status_code=500,
                )
            if rich_text:
                richtext_paths.add(path.strip())
        return richtext_paths

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

        def get_template_data(*, template_filename: str) -> dict[str, Any] | None:
            template_content = template_contents_by_filename.get(template_filename)
            if template_content is None:
                return None
            template_data = parsed_templates_by_filename.get(template_filename)
            if template_data is None:
                template_data = cls._parse_theme_template_json(
                    filename=template_filename,
                    template_content=template_content,
                )
                parsed_templates_by_filename[template_filename] = template_data
            return template_data

        def is_disabled_slot(*, setting_path: str) -> bool:
            template_filename, json_path = cls._split_theme_template_setting_path(
                setting_path=setting_path
            )
            template_data = get_template_data(template_filename=template_filename)
            if template_data is None:
                return False
            return cls._is_theme_template_settings_path_disabled(
                template_data=template_data,
                path=json_path,
            )

        def resolve_current_value(
            *, setting_path: str, allow_missing: bool = False
        ) -> str | None:
            template_filename, json_path = cls._split_theme_template_setting_path(
                setting_path=setting_path
            )
            template_data = get_template_data(template_filename=template_filename)
            if template_data is None:
                missing_paths.append(setting_path)
                return None
            values = cls._read_json_path_values(node=template_data, path=json_path)
            if not values:
                if not allow_missing:
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
            allow_missing = item.get("allowMissing", False)
            if (
                not isinstance(path, str)
                or not path.strip()
                or not isinstance(key, str)
                or not key.strip()
                or not isinstance(role, str)
                or not role.strip()
                or not isinstance(recommended_aspect, str)
                or recommended_aspect not in {"landscape", "portrait", "square", "any"}
                or not isinstance(allow_missing, bool)
            ):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid image slot definition. "
                        f"themeName={profile.theme_name}, slot={item}."
                    ),
                    status_code=500,
                )
            normalized_path = path.strip()
            if is_disabled_slot(setting_path=normalized_path):
                continue
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
                    "currentValue": resolve_current_value(
                        setting_path=normalized_path,
                        allow_missing=allow_missing,
                    ),
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
            allow_missing = item.get("allowMissing", False)
            if (
                not isinstance(path, str)
                or not path.strip()
                or not isinstance(key, str)
                or not key.strip()
                or not isinstance(role, str)
                or not role.strip()
                or not isinstance(max_length, int)
                or max_length <= 0
                or not isinstance(allow_missing, bool)
            ):
                raise ShopifyApiError(
                    message=(
                        "Theme template slot manifest contains an invalid text slot definition. "
                        f"themeName={profile.theme_name}, slot={item}."
                    ),
                    status_code=500,
                )
            normalized_path = path.strip()
            if is_disabled_slot(setting_path=normalized_path):
                continue
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
                    "currentValue": resolve_current_value(
                        setting_path=normalized_path,
                        allow_missing=allow_missing,
                    ),
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
    def _group_theme_component_setting_paths_by_template(
        cls,
        *,
        setting_paths: set[str],
    ) -> dict[str, set[str]]:
        grouped: dict[str, set[str]] = {}
        for setting_path in setting_paths:
            template_filename, _ = cls._split_theme_template_setting_path(
                setting_path=setting_path
            )
            grouped.setdefault(template_filename, set()).add(setting_path)
        return grouped

    @classmethod
    def _sync_theme_template_component_text_settings_data(
        cls,
        *,
        template_filename: str,
        template_content: str,
        component_text_values_by_path: dict[str, str],
        allow_missing_leaf_paths: set[str] | None = None,
        richtext_setting_paths: set[str] | None = None,
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
        allowed_missing_leaf_paths = set(allow_missing_leaf_paths or ())
        normalized_richtext_paths = set(richtext_setting_paths or ())

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
                expect_richtext=setting_path in normalized_richtext_paths,
            )
            update_count = cls._set_json_path_value(
                node=template_data,
                path=json_path,
                value=resolved_text_value,
                create_missing_leaf=setting_path in allowed_missing_leaf_paths,
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
        expect_richtext: bool = False,
    ) -> str:
        if expect_richtext or any(
            cls._is_theme_component_richtext_value(value=value)
            for value in existing_values
        ):
            collapsed = " ".join(text_value.split()).strip()
            return f"<p>{escape(collapsed)}</p>"
        return text_value

    @classmethod
    def _stabilize_collection_images_with_text_overlay_settings(
        cls,
        *,
        template_filename: str,
        template_content: str,
    ) -> str:
        if template_filename != "templates/collection.json":
            return template_content

        template_data = cls._parse_theme_template_json(
            filename=template_filename,
            template_content=template_content,
        )
        sections = template_data.get("sections")
        if not isinstance(sections, dict):
            return template_content
        section = sections.get("images-with-text-overlay")
        if not isinstance(section, dict) or section.get("type") != "images-with-text-overlay":
            return template_content
        section_settings = section.get("settings")
        blocks = section.get("blocks")
        if not isinstance(section_settings, dict) or not isinstance(blocks, dict):
            return template_content

        has_button_with_label = False
        for block in blocks.values():
            if not isinstance(block, dict) or block.get("type") != "button":
                continue
            block_settings = block.get("settings")
            if not isinstance(block_settings, dict):
                continue
            button_label = block_settings.get("button_label")
            if isinstance(button_label, str) and button_label.strip():
                has_button_with_label = True
                break
        if not has_button_with_label:
            return template_content

        changed = False
        if section_settings.get("image_height") in {"400px", "450px"}:
            section_settings["image_height"] = "550px"
            changed = True
        if section_settings.get("image_height_mobile") in {
            "auto",
            "200px",
            "250px",
            "300px",
            "400px",
        }:
            section_settings["image_height_mobile"] = "500px"
            changed = True
        if section_settings.get("content_position") == "md:items-center md:justify-start":
            section_settings["content_position"] = "md:items-start md:justify-start"
            changed = True

        for block in blocks.values():
            if not isinstance(block, dict) or block.get("type") != "spacing":
                continue
            block_settings = block.get("settings")
            if not isinstance(block_settings, dict):
                continue
            spacing_height = block_settings.get("height")
            if isinstance(spacing_height, (int, float)) and spacing_height > 32:
                block_settings["height"] = 32
                changed = True
            spacing_height_mobile = block_settings.get("height_mobile")
            if isinstance(spacing_height_mobile, (int, float)) and spacing_height_mobile > 8:
                block_settings["height_mobile"] = 8
                changed = True

        if not changed:
            return template_content
        return json.dumps(template_data, ensure_ascii=False, separators=(",", ":")) + "\n"

    @classmethod
    def _stabilize_main_collection_sidebar_menu_layout(
        cls,
        *,
        filename: str,
        content: str,
    ) -> str:
        if filename != _THEME_MAIN_COLLECTION_SECTION_FILENAME:
            return content

        updated_content = content

        def _rewrite_menu_heading(match: re.Match[str]) -> str:
            class_tokens = [token for token in match.group("class").split() if token]
            class_tokens = [
                token for token in class_tokens if token not in {"text-center", "text-left"}
            ]
            class_tokens.extend(["w-full", "text-left"])
            return f'<h3 class="{" ".join(class_tokens)}">Menu</h3>'

        updated_content = re.sub(
            r'<h3\s+class="(?P<class>[^"]*)">\s*Menu\s*</h3>',
            _rewrite_menu_heading,
            updated_content,
            count=1,
        )

        def _rewrite_collection_nav_class(match: re.Match[str]) -> str:
            class_tokens = [token for token in match.group("class").split() if token]
            class_tokens = [
                token
                for token in class_tokens
                if token not in {"mb-4", "flex-col", "items-start", "w-full"}
            ]
            class_tokens.extend(["mb-4", "flex-col", "items-start", "w-full"])
            return (
                f'{match.group("prefix")}{" ".join(class_tokens)}'
                f'{match.group("suffix")}'
            )

        updated_content = re.sub(
            r'(?P<prefix>class:\s*")(?P<class>[^"]*)(?P<suffix>"\s*,\s*limit:\s*link_count)',
            _rewrite_collection_nav_class,
            updated_content,
            count=1,
        )

        return updated_content

    @classmethod
    def _stabilize_header_icons_cart_controls(
        cls,
        *,
        filename: str,
        content: str,
    ) -> str:
        if filename != _THEME_HEADER_ICONS_FILENAME:
            return content

        updated_content = content

        # Remove the custom "Track my order" button and the separator that follows it.
        updated_content = re.sub(
            r'<a\s+href="\{\{\s*routes\.cart_url\s*\}\}"[^>]*>'
            r'.*?(?:Suivre\s+ma\s+commande|Track\s+my\s+order).*?</a>\s*'
            r'(?:<div\s+class="h-full\s+divider"><span></span></div>\s*)?',
            "",
            updated_content,
            flags=re.IGNORECASE | re.DOTALL,
            count=1,
        )

        # Keep the native cart drawer trigger wiring on the remaining cart control.
        # Some storefront scripts bind cart state updates and drawer state to those hooks.

        # Render icon/count only in the top-right cart control.
        updated_content = re.sub(
            r'\s*<span\s+class="hidden\s+md:block">\s*'
            r'\{\{\s*[\'"]general\.cart\.title[\'"]\s*\|\s*t\s*\}\}'
            r'\s*</span>\s*',
            "\n",
            updated_content,
            flags=re.DOTALL,
        )
        return updated_content

    @classmethod
    def _stabilize_product_card_inventory_language(
        cls,
        *,
        filename: str,
        content: str,
    ) -> str:
        if filename != _THEME_PRODUCT_CARD_SNIPPET_FILENAME:
            return content

        updated_content = re.sub(
            r'assign\s+stock_text\s*=\s*["\']En stock["\']',
            'assign stock_text = "In stock"',
            content,
        )
        updated_content = re.sub(
            r'assign\s+stock_text\s*=\s*["\']Presque épuisé["\']',
            'assign stock_text = "Almost sold out"',
            updated_content,
        )
        return updated_content

    @classmethod
    def _stabilize_shoppable_video_cart_count_updates(
        cls,
        *,
        filename: str,
        content: str,
    ) -> str:
        if filename != _THEME_SHOPPABLE_VIDEO_SECTION_FILENAME:
            return content

        cart_json_line_re = re.compile(
            (
                r"^(?P<indent>\s*)"
                r"const\s+cart\{\{\s*forloop\.index\s*\}\}\s*="
                r"\s*await\s+res\{\{\s*forloop\.index\s*\}\}\.json\(\);\s*$"
            )
        )
        cart_update_publish_re = re.compile(
            (
                r"theme\.pubsub\.publish\(\s*"
                r"theme\.pubsub\.PUB_SUB_EVENTS\.cartUpdate\s*,\s*"
                r"\{\s*cart:\s*cart\{\{\s*forloop\.index\s*\}\}\s*\}\s*"
                r"\)\s*;"
            )
        )

        lines = content.splitlines(keepends=True)
        if not lines:
            return content

        changed = False
        normalized_lines: list[str] = []
        line_count = len(lines)
        for index, line in enumerate(lines):
            normalized_lines.append(line)
            cart_line_match = cart_json_line_re.match(line.rstrip("\r\n"))
            if cart_line_match is None:
                continue

            next_line = lines[index + 1].strip() if index + 1 < line_count else ""
            if cart_update_publish_re.search(next_line):
                continue

            indent = cart_line_match.group("indent")
            if line.endswith("\r\n"):
                line_ending = "\r\n"
            elif line.endswith("\n"):
                line_ending = "\n"
            elif line.endswith("\r"):
                line_ending = "\r"
            else:
                line_ending = ""

            normalized_lines.append(
                indent
                + "theme.pubsub.publish(theme.pubsub.PUB_SUB_EVENTS.cartUpdate, { cart: cart{{ forloop.index }} });"
                + line_ending
            )
            changed = True

        if not changed:
            return content
        return "".join(normalized_lines)

    @classmethod
    def _strip_catalog_navigation_from_header_drawer(
        cls,
        *,
        content: str,
    ) -> str:
        without_catalog_details = _THEME_CATALOG_DETAILS_MENU_ITEM_RE.sub("", content)
        return _THEME_CATALOG_LINK_MENU_ITEM_RE.sub("", without_catalog_details)

    @classmethod
    def _normalize_theme_text_to_english(
        cls,
        *,
        content: str,
    ) -> str:
        normalized = content
        for pattern, replacement in _THEME_FRENCH_UI_TEXT_REPLACEMENTS:
            normalized = pattern.sub(replacement, normalized)
        return normalized

    @classmethod
    def _sync_theme_template_component_image_settings_data(
        cls,
        *,
        template_filename: str,
        template_content: str,
        component_image_urls_by_path: dict[str, str],
        allow_missing_leaf_paths: set[str] | None = None,
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
        allowed_missing_leaf_paths = set(allow_missing_leaf_paths or ())

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
                create_missing_leaf=setting_path in allowed_missing_leaf_paths,
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
            expected_value = cls._resolve_theme_settings_color_source_value(
                effective_css_vars=effective_css_vars,
                source_var=source_var,
                path=path,
                context="Theme settings mapping",
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
            try:
                expected_value = cls._resolve_theme_settings_color_source_value(
                    effective_css_vars=effective_css_vars,
                    source_var=source_var,
                    path=path,
                    context="Theme settings audit",
                )
            except ShopifyApiError:
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
                message="Provide at most one of themeId or themeName.",
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

        cleaned_theme_name = theme_name.strip() if theme_name is not None else None
        if cleaned_theme_name is not None and not cleaned_theme_name:
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
        parsed_nodes = [
            self._coerce_theme_data(node=node, query_name="themes") for node in raw_nodes
        ]
        if cleaned_theme_name:
            requested_name = cleaned_theme_name.lower()
            matches = [
                parsed
                for parsed in parsed_nodes
                if parsed["name"].strip().lower() == requested_name
            ]
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

        main_themes = [
            parsed
            for parsed in parsed_nodes
            if parsed["role"].strip().upper() == "MAIN"
        ]
        if len(main_themes) == 1:
            return main_themes[0]
        if not main_themes:
            raise ShopifyApiError(
                message=(
                    "No MAIN theme was found for this store. "
                    "Provide themeName or themeId explicitly."
                ),
                status_code=409,
            )
        theme_ids = ", ".join(theme["id"] for theme in main_themes)
        raise ShopifyApiError(
            message=(
                "Multiple MAIN themes were found for this store. "
                f"Provide themeName or themeId explicitly. matchedThemeIds={theme_ids}"
            ),
            status_code=409,
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

    @staticmethod
    def _decode_theme_file_bytes_as_utf8(*, raw_bytes: bytes) -> str | None:
        try:
            return raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def _filename_allows_html_body(*, filename: str) -> bool:
        cleaned = filename.strip().lower()
        return cleaned.endswith((".html", ".htm", ".liquid"))

    @staticmethod
    def _looks_like_html_error_document(*, raw_bytes: bytes) -> bool:
        preview = raw_bytes[:8192].decode("utf-8", errors="ignore").lower()
        if (
            "<html" not in preview
            and "<!doctype html" not in preview
            and "<body" not in preview
        ):
            return False
        error_markers = (
            "404",
            "not found",
            "page not found",
            "no such key",
            "access denied",
        )
        return any(marker in preview for marker in error_markers)

    async def _list_theme_files_with_content(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
    ) -> list[dict[str, str]]:
        query = """
        query themeTextFilesForExport($id: ID!, $first: Int!, $after: String) {
            theme(id: $id) {
                files(first: $first, after: $after) {
                    nodes {
                        filename
                        body {
                            __typename
                            ... on OnlineStoreThemeFileBodyText {
                                content
                            }
                            ... on OnlineStoreThemeFileBodyBase64 {
                                contentBase64
                            }
                            ... on OnlineStoreThemeFileBodyUrl {
                                url
                            }
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
        files_by_filename: dict[str, dict[str, str]] = {}
        unsupported_body_types_by_name: dict[str, list[str]] = {}
        after: str | None = None

        for _ in range(40):
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
                    message=f"Theme not found for themeId={theme_id}.",
                    status_code=404,
                )
            files = theme.get("files")
            if not isinstance(files, dict):
                raise ShopifyApiError(
                    message="theme text files export query response is invalid."
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
                    message=f"theme text files export query failed: {detail_text}",
                    status_code=409,
                )

            nodes = files.get("nodes")
            if not isinstance(nodes, list):
                raise ShopifyApiError(
                    message="theme text files export query response is missing nodes."
                )
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                filename = node.get("filename")
                if not isinstance(filename, str) or not filename.strip():
                    continue
                cleaned_filename = filename.strip()
                body = node.get("body")
                typename = body.get("__typename") if isinstance(body, dict) else None
                if typename == "OnlineStoreThemeFileBodyText":
                    content = body.get("content") if isinstance(body, dict) else None
                    if not isinstance(content, str):
                        raise ShopifyApiError(
                            message=(
                                "theme text files export query returned an invalid text body "
                                f"for filename={cleaned_filename}."
                            ),
                            status_code=409,
                        )
                    files_by_filename[cleaned_filename] = {
                        "filename": cleaned_filename,
                        "content": content,
                    }
                elif typename == "OnlineStoreThemeFileBodyBase64":
                    content_base64 = (
                        body.get("contentBase64") if isinstance(body, dict) else None
                    )
                    if not isinstance(content_base64, str) or not content_base64.strip():
                        raise ShopifyApiError(
                            message=(
                                "theme text files export query returned an invalid base64 body "
                                f"for filename={cleaned_filename}."
                            ),
                            status_code=409,
                        )
                    try:
                        decoded_bytes = base64.b64decode(
                            content_base64, validate=True
                        )
                    except (binascii.Error, ValueError) as exc:
                        raise ShopifyApiError(
                            message=(
                                "theme text files export query returned malformed base64 content "
                                f"for filename={cleaned_filename}."
                            ),
                            status_code=409,
                        ) from exc
                    decoded_text = self._decode_theme_file_bytes_as_utf8(
                        raw_bytes=decoded_bytes
                    )
                    if decoded_text is not None:
                        files_by_filename[cleaned_filename] = {
                            "filename": cleaned_filename,
                            "content": decoded_text,
                        }
                    else:
                        files_by_filename[cleaned_filename] = {
                            "filename": cleaned_filename,
                            "contentBase64": base64.b64encode(decoded_bytes).decode(
                                "ascii"
                            ),
                        }
                elif typename == "OnlineStoreThemeFileBodyUrl":
                    body_url = body.get("url") if isinstance(body, dict) else None
                    if not isinstance(body_url, str) or not body_url.strip():
                        raise ShopifyApiError(
                            message=(
                                "theme text files export query returned an invalid body URL "
                                f"for filename={cleaned_filename}."
                            ),
                            status_code=409,
                        )
                    downloaded_bytes = await self._download_theme_file_text_body_from_url(
                        filename=cleaned_filename,
                        body_url=body_url.strip(),
                    )
                    decoded_text = self._decode_theme_file_bytes_as_utf8(
                        raw_bytes=downloaded_bytes
                    )
                    if decoded_text is not None:
                        files_by_filename[cleaned_filename] = {
                            "filename": cleaned_filename,
                            "content": decoded_text,
                        }
                    else:
                        files_by_filename[cleaned_filename] = {
                            "filename": cleaned_filename,
                            "contentBase64": base64.b64encode(downloaded_bytes).decode(
                                "ascii"
                            ),
                        }
                else:
                    normalized_type = (
                        typename if isinstance(typename, str) and typename else "UNKNOWN"
                    )
                    unsupported_body_types_by_name.setdefault(normalized_type, []).append(
                        cleaned_filename
                    )
                    continue

            page_info = files.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ShopifyApiError(
                    message="theme text files export query response is missing pageInfo."
                )
            has_next_page = page_info.get("hasNextPage")
            if not isinstance(has_next_page, bool):
                raise ShopifyApiError(
                    message=(
                        "theme text files export query response is missing "
                        "pageInfo.hasNextPage."
                    )
                )
            if not has_next_page:
                if unsupported_body_types_by_name:
                    samples: list[str] = []
                    for body_type in sorted(unsupported_body_types_by_name.keys()):
                        filenames = sorted(unsupported_body_types_by_name[body_type])
                        sample_filenames = ", ".join(filenames[:3])
                        if len(filenames) > 3:
                            sample_filenames = f"{sample_filenames}, ..."
                        samples.append(f"{body_type}: {sample_filenames}")
                    raise ShopifyApiError(
                        message=(
                            "Theme export encountered unsupported theme file body types: "
                            f"{'; '.join(samples)}."
                        ),
                        status_code=409,
                    )
                if not files_by_filename:
                    raise ShopifyApiError(
                        message=(
                            "Theme export could not load any files from the selected theme."
                        ),
                        status_code=409,
                    )
                return [files_by_filename[filename] for filename in sorted(files_by_filename.keys())]
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor:
                raise ShopifyApiError(
                    message=(
                        "theme text files export query response is missing "
                        "pageInfo.endCursor."
                    )
                )
            after = end_cursor

        raise ShopifyApiError(
            message=(
                "Theme text files export query exceeded pagination limit while exporting. "
                "Reduce theme file count or adjust pagination strategy."
            ),
            status_code=409,
        )

    async def _download_theme_file_text_body_from_url(
        self,
        *,
        filename: str,
        body_url: str,
    ) -> bytes:
        parsed = urlparse(body_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ShopifyApiError(
                message=(
                    "Theme export received an invalid file body URL for "
                    f"filename={filename}: {body_url!r}."
                ),
                status_code=409,
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(body_url)
        except httpx.InvalidURL as exc:
            raise ShopifyApiError(
                message=(
                    "Theme export received an invalid file body URL for "
                    f"filename={filename}: {body_url!r}."
                ),
                status_code=409,
            ) from exc
        except httpx.RequestError as exc:
            raise ShopifyApiError(
                message=(
                    "Theme export failed to download file body URL for "
                    f"filename={filename}: {exc}"
                ),
                status_code=409,
            ) from exc

        if response.status_code != 200:
            raise ShopifyApiError(
                message=(
                    "Theme export failed to download file body URL for "
                    f"filename={filename} (status={response.status_code})."
                ),
                status_code=409,
            )
        if not response.content:
            raise ShopifyApiError(
                message=(
                    "Theme export downloaded an empty file body URL for "
                    f"filename={filename}."
                ),
                status_code=409,
            )
        content_type = response.headers.get("content-type", "").strip().lower()
        if not self._filename_allows_html_body(
            filename=filename
        ) and (
            "text/html" in content_type
            or self._looks_like_html_error_document(raw_bytes=response.content)
        ):
            raise ShopifyApiError(
                message=(
                    "Theme export downloaded an HTML error document for "
                    f"filename={filename}. The file body URL may have expired or "
                    "is not accessible. Retry export."
                ),
                status_code=409,
            )
        return response.content

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
        allow_empty: bool = False,
    ) -> tuple[str | None, str | None]:
        normalized_theme_id = (
            theme_id.strip() if isinstance(theme_id, str) and theme_id.strip() else None
        )
        normalized_theme_name = (
            theme_name.strip()
            if isinstance(theme_name, str) and theme_name.strip()
            else None
        )
        if normalized_theme_id and normalized_theme_name:
            raise ShopifyApiError(
                message="Provide at most one of themeId or themeName.",
                status_code=400,
            )
        if not allow_empty and not normalized_theme_id and not normalized_theme_name:
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

    async def resolve_image_urls_to_shopify_files(
        self,
        *,
        shop_domain: str,
        access_token: str,
        image_urls: dict[str, str],
    ) -> dict[str, str]:
        if not isinstance(image_urls, dict) or not image_urls:
            raise ShopifyApiError(
                message="imageUrls must be a non-empty object.",
                status_code=400,
            )

        normalized_image_urls: dict[str, str] = {}
        for raw_key, raw_url in image_urls.items():
            if not isinstance(raw_key, str) or not raw_key.strip():
                raise ShopifyApiError(
                    message="imageUrls keys must be non-empty strings.",
                    status_code=400,
                )
            key = raw_key.strip()
            if key in normalized_image_urls:
                raise ShopifyApiError(
                    message=f"Duplicate imageUrls key after normalization: {key}.",
                    status_code=400,
                )
            if any(char in key for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"imageUrls key contains unsupported characters: {key}.",
                    status_code=400,
                )

            if not isinstance(raw_url, str) or not raw_url.strip():
                raise ShopifyApiError(
                    message=f"imageUrls[{key}] must be a non-empty string.",
                    status_code=400,
                )
            image_url = raw_url.strip()
            if any(char.isspace() for char in image_url):
                raise ShopifyApiError(
                    message=f"imageUrls[{key}] must not include whitespace characters.",
                    status_code=400,
                )
            if any(char in image_url for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"imageUrls[{key}] contains unsupported characters.",
                    status_code=400,
                )
            if not (
                image_url.startswith("https://")
                or image_url.startswith("http://")
                or self._is_shopify_file_url(value=image_url)
            ):
                raise ShopifyApiError(
                    message=(
                        f"imageUrls[{key}] must be an absolute http(s) URL "
                        "or a shopify:// URL."
                    ),
                    status_code=400,
                )
            normalized_image_urls[key] = image_url

        upload_cache: dict[str, str] = {}
        external_image_urls = [
            image_url
            for image_url in normalized_image_urls.values()
            if not self._is_shopify_file_url(value=image_url)
        ]
        unique_external_image_urls = list(dict.fromkeys(external_image_urls))

        if unique_external_image_urls:
            semaphore = asyncio.Semaphore(_THEME_FILE_IMAGE_RESOLVE_MAX_CONCURRENCY)

            async def _resolve_external_image_url(image_url: str) -> tuple[str, str]:
                async with semaphore:
                    resolved_url = await self._create_shopify_logo_file_reference_from_url(
                        shop_domain=shop_domain,
                        access_token=access_token,
                        logo_url=image_url,
                    )
                    return image_url, resolved_url

            resolved_pairs = await asyncio.gather(
                *[
                    _resolve_external_image_url(image_url)
                    for image_url in unique_external_image_urls
                ]
            )
            for image_url, resolved_url in resolved_pairs:
                upload_cache[image_url] = resolved_url

        resolved_image_urls: dict[str, str] = {}
        for key, image_url in normalized_image_urls.items():
            if self._is_shopify_file_url(value=image_url):
                resolved_image_urls[key] = image_url
                continue
            resolved_url = upload_cache.get(image_url)
            if not isinstance(resolved_url, str) or not resolved_url.strip():
                raise ShopifyApiError(
                    message=(
                        "Image URL resolution did not return a Shopify file URL "
                        f"for key={key}."
                    ),
                    status_code=409,
                )
            resolved_image_urls[key] = resolved_url

        return resolved_image_urls

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
            allow_empty=True,
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
        ordered_image_slots = self._sort_theme_template_image_slots_by_render_order(
            image_slots=image_slots,
            template_contents_by_filename=template_contents_by_filename,
        )

        return {
            "themeId": theme["id"],
            "themeName": theme["name"],
            "themeRole": theme["role"],
            "imageSlots": ordered_image_slots,
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
        upsert_theme_files: bool = True,
        include_file_payloads: bool = False,
        include_all_theme_text_files: bool = False,
        resolve_external_images_to_shopify_files: bool = True,
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
        header_drawer_content = await self._try_load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            filename=_THEME_HEADER_DRAWER_FILENAME,
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
                elif not resolve_external_images_to_shopify_files:
                    # Export mode can disable external URL -> Shopify file uploads.
                    # In that mode, skip settings logo-field sync when the logo URL
                    # is not already a shopify:// reference.
                    settings_logo_url = None
                else:
                    settings_logo_url = (
                        await self._create_shopify_logo_file_reference_from_url(
                            shop_domain=shop_domain,
                            access_token=access_token,
                            logo_url=cleaned_logo_url,
                        )
                    )
        # Export mode should prefer Shopify-hosted logo references in generated files
        # when we resolved one from an external source URL.
        rendered_logo_url = cleaned_logo_url
        if (
            not upsert_theme_files
            and resolve_external_images_to_shopify_files
            and isinstance(settings_logo_url, str)
            and settings_logo_url.strip()
        ):
            rendered_logo_url = settings_logo_url.strip()

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
        optional_manifest_image_paths: set[str] = set()
        optional_manifest_text_paths: set[str] = set()
        richtext_manifest_text_paths: set[str] = set()
        if component_image_urls_by_template or component_text_values_by_template:
            (
                optional_manifest_image_paths,
                optional_manifest_text_paths,
            ) = self._get_optional_theme_template_slot_paths_from_manifest(
                profile=profile
            )
        if component_text_values_by_template:
            richtext_manifest_text_paths = (
                self._get_richtext_theme_template_slot_paths_from_manifest(
                    profile=profile
                )
            )
        optional_component_image_paths_by_template = (
            self._group_theme_component_setting_paths_by_template(
                setting_paths=optional_manifest_image_paths
            )
        )
        optional_component_text_paths_by_template = (
            self._group_theme_component_setting_paths_by_template(
                setting_paths=optional_manifest_text_paths
            )
        )
        richtext_component_text_paths_by_template = (
            self._group_theme_component_setting_paths_by_template(
                setting_paths=richtext_manifest_text_paths
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
            logo_url=rendered_logo_url,
            data_theme=cleaned_data_theme,
        )
        next_layout = self._replace_theme_brand_liquid_block(
            layout_content=layout_content,
            replacement_block=replacement_block,
        )
        next_layout = self._normalize_theme_text_to_english(content=next_layout)
        css_content = self._render_theme_brand_css(
            theme_name=theme["name"],
            workspace_name=cleaned_workspace_name,
            brand_name=cleaned_brand_name,
            logo_url=rendered_logo_url,
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
            next_settings_content = self._normalize_theme_text_to_english(
                content=next_settings_content
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
                allow_missing_leaf_paths=optional_component_text_paths_by_template.get(
                    template_filename, set()
                ),
                richtext_setting_paths=richtext_component_text_paths_by_template.get(
                    template_filename, set()
                ),
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
                        allow_missing_leaf_paths=optional_component_text_paths_by_template.get(
                            template_filename, set()
                        ),
                        richtext_setting_paths=richtext_component_text_paths_by_template.get(
                            template_filename, set()
                        ),
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
                    allow_missing_leaf_paths=optional_component_image_paths_by_template.get(
                        template_filename, set()
                    ),
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
                        elif not resolve_external_images_to_shopify_files:
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
                        allow_missing_leaf_paths=optional_component_image_paths_by_template.get(
                            template_filename, set()
                        ),
                    )
                )
                next_template_contents[template_filename] = next_template_content

        for template_filename, template_content in list(next_template_contents.items()):
            stabilized_template_content = (
                self._stabilize_collection_images_with_text_overlay_settings(
                    template_filename=template_filename,
                    template_content=template_content,
                )
            )
            next_template_contents[template_filename] = self._normalize_theme_text_to_english(
                content=stabilized_template_content
            )

        next_header_drawer_content: str | None = None
        if isinstance(header_drawer_content, str):
            next_header_drawer_content = self._normalize_theme_text_to_english(
                content=header_drawer_content
            )

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
        if (
            isinstance(header_drawer_content, str)
            and isinstance(next_header_drawer_content, str)
            and next_header_drawer_content != header_drawer_content
        ):
            files_to_upsert.append(
                {
                    "filename": _THEME_HEADER_DRAWER_FILENAME,
                    "content": next_header_drawer_content,
                }
            )
        files_to_upsert.extend(template_files_to_upsert)
        job_id: str | None = None
        if upsert_theme_files:
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

        response: dict[str, Any] = {
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
        if include_file_payloads:
            response_files = files_to_upsert
            if include_all_theme_text_files:
                full_theme_text_files = await self._list_theme_files_with_content(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    theme_id=theme["id"],
                )
                merged_by_filename: dict[str, dict[str, str]] = {
                    item["filename"]: dict(item) for item in full_theme_text_files
                }
                for item in files_to_upsert:
                    merged_by_filename[item["filename"]] = {
                        "filename": item["filename"],
                        "content": item["content"],
                    }
                response_files = [
                    merged_by_filename[filename]
                    for filename in sorted(merged_by_filename.keys())
                ]
            for file_entry in response_files:
                filename = file_entry.get("filename")
                content = file_entry.get("content")
                if not isinstance(content, str):
                    continue
                normalized_content = self._normalize_theme_text_to_english(
                    content=content
                )
                if isinstance(filename, str):
                    normalized_content = (
                        self._stabilize_main_collection_sidebar_menu_layout(
                            filename=filename,
                            content=normalized_content,
                        )
                    )
                    normalized_content = self._stabilize_header_icons_cart_controls(
                        filename=filename,
                        content=normalized_content,
                    )
                    normalized_content = (
                        self._stabilize_product_card_inventory_language(
                            filename=filename,
                            content=normalized_content,
                        )
                    )
                    normalized_content = (
                        self._stabilize_shoppable_video_cart_count_updates(
                            filename=filename,
                            content=normalized_content,
                        )
                    )
                if filename == _THEME_HEADER_DRAWER_FILENAME:
                    normalized_content = (
                        self._strip_catalog_navigation_from_header_drawer(
                            content=normalized_content
                        )
                    )
                file_entry["content"] = normalized_content
            response["files"] = response_files
        return response

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
