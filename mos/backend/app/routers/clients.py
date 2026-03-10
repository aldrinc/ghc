import base64
import binascii
import concurrent.futures
from contextlib import nullcontext
from contextvars import ContextVar
from datetime import datetime, timezone
from html import escape
import io
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
from uuid import UUID, uuid4
import zipfile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import DataError, StatementError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.base import SessionLocal
from app.db.deps import get_session
from app.db.models import ClientComplianceProfile, ClientUserPreference, Funnel, FunnelPage, Product
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.client_compliance_profiles import (
    ClientComplianceProfilesRepository,
)
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.db.repositories.jobs import (
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    JobsRepository,
)
from app.db.repositories.shopify_theme_template_drafts import (
    ShopifyThemeTemplateDraftsRepository,
)
from app.db.repositories.products import ProductOffersRepository, ProductsRepository, ProductVariantsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum, AssetStatusEnum, FunnelStatusEnum
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.schemas.preferences import ActiveProductUpdateRequest
from app.schemas.common import ClientCreate
from app.schemas.clients import ClientDeleteRequest, ClientUpdateRequest
from app.schemas.onboarding import OnboardingStartRequest
from app.schemas.intent import CampaignIntentRequest
from app.schemas.shopify_connection import (
    ShopifyThemeBrandAuditRequest,
    ShopifyThemeBrandAuditResponse,
    ShopifyCreateProductRequest,
    ShopifyDefaultShopRequest,
    ShopifyInstallationDisconnectRequest,
    ShopifyInstallationAutoStorefrontTokenRequest,
    ShopifyProductListResponse,
    ShopifyProductCreateResponse,
    ShopifyConnectionStatusResponse,
    ShopifyInstallationUpdateRequest,
    ShopifyInstallUrlRequest,
    ShopifyInstallUrlResponse,
    ShopifyThemeBrandSyncRequest,
    ShopifyThemeBrandSyncJobStartResponse,
    ShopifyThemeBrandSyncJobProgress,
    ShopifyThemeBrandSyncJobStatusResponse,
    ShopifyThemeBrandSyncResponse,
    ShopifyThemeTemplateBuildJobStartResponse,
    ShopifyThemeTemplateBuildJobStatusResponse,
    ShopifyThemeTemplateBuildRequest,
    ShopifyThemeTemplateBuildResponse,
    ShopifyThemeTemplateDraftData,
    ShopifyThemeTemplateDraftResponse,
    ShopifyThemeTemplateDraftUpdateRequest,
    ShopifyThemeTemplateDraftVersionResponse,
    ShopifyThemeTemplateFeatureHighlights,
    ShopifyThemeTemplateGenerateImagesJobStartResponse,
    ShopifyThemeTemplateGenerateImagesJobStatusResponse,
    ShopifyThemeTemplateGenerateImagesRequest,
    ShopifyThemeTemplateGenerateImagesResponse,
    ShopifyThemeTemplateImageSlot,
    ShopifyThemeTemplatePublishJobStartResponse,
    ShopifyThemeTemplatePublishJobStatusResponse,
    ShopifyThemeTemplatePublishRequest,
    ShopifyThemeTemplatePublishResponse,
    ShopifyThemeTemplateTextSlot,
)
from app.services.design_system_generation import (
    DesignSystemGenerationError,
    validate_design_system_tokens,
)
from app.services.compliance import (
    build_page_requirements,
    get_policy_page_handle,
    get_policy_template,
    get_profile_url_field_for_page_key,
    markdown_to_shopify_html,
    resolve_theme_contact_page_values,
    render_policy_template_markdown,
)
from app.services.funnels import (
    create_funnel_image_asset,
    create_funnel_unsplash_asset,
    resolve_funnel_image_model_config,
)
from app.services.funnel_testimonials import (
    generate_shopify_theme_review_card_payloads,
    generate_shopify_theme_testimonial_image_asset,
)
from app.services.media_storage import MediaStorage
from app.services.public_routing import require_product_route_slug
from app.services.shopify_connection import (
    audit_client_shopify_theme_brand,
    auto_provision_client_shopify_storefront_token,
    build_client_shopify_install_urls,
    create_client_shopify_product,
    disconnect_client_shopify_store,
    get_client_shopify_connection_status,
    list_client_shopify_theme_template_slots,
    list_client_shopify_products,
    list_shopify_installations,
    normalize_shop_domain,
    resolve_client_shopify_image_urls_to_files,
    set_client_shopify_storefront_token,
    sync_client_shopify_theme_brand,
    upsert_client_shopify_policy_pages,
)
from app.services.shopify_collection_sync import (
    sync_workspace_shopify_catalog_collection,
)
from app.services.shopify_theme_copy_agent import (
    generate_shopify_theme_component_copy,
)
from app.services.shopify_theme_content_planner import (
    plan_shopify_theme_component_content,
)
from app.services.product_types import canonical_product_type
from app.testimonial_renderer.renderer import ThreadedTestimonialRenderer
from app.testimonial_renderer.validate import TestimonialRenderError
from app.strategy_v2.downstream import require_strategy_v2_outputs_if_enabled
from app.strategy_v2.feature_flags import is_strategy_v2_enabled
from app.strategy_v2.pricing import parse_price_to_cents_and_currency
from app.temporal.client import get_temporal_client
from app.temporal.workflows.client_onboarding import (
    ClientOnboardingInput,
    ClientOnboardingWorkflow,
)
from app.temporal.workflows.campaign_intent import (
    CampaignIntentInput,
    CampaignIntentWorkflow,
)

router = APIRouter(prefix="/clients", tags=["clients"])
logger = logging.getLogger(__name__)

_JOB_TYPE_SHOPIFY_THEME_BRAND_SYNC = "shopify_theme_brand_sync"
_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_BUILD = "shopify_theme_template_build"
_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_GENERATE_IMAGES = "shopify_theme_template_generate_images"
_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_PUBLISH = "shopify_theme_template_publish"
_JOB_SUBJECT_TYPE_CLIENT = "client"
_THEME_COMPONENT_HTML_TAG_RE = re.compile(
    r"</?\s*(?:p|strong|em|span|b|i|u|br|div|h[1-6]|li|ul|ol|a)\b[^<>]*>",
    re.IGNORECASE,
)
_THEME_COMPONENT_ORPHAN_CLOSING_TAG_RE = re.compile(
    r"/\s*(?:p|strong|em|span|b|i|u|br|div|h[1-6]|li|ul|ol|a)\b",
    re.IGNORECASE,
)
_THEME_RICHTEXT_TOP_LEVEL_TAG_RE = re.compile(
    r"^\s*<(?:p|ul|ol|h[1-6])\b",
    re.IGNORECASE,
)
_THEME_RICHTEXT_MARKUP_RE = re.compile(
    r"<(?:p|ul|ol|h[1-6]|li|br)\b",
    re.IGNORECASE,
)
_THEME_FEATURE_IMAGE_SLOT_PATH_RE = re.compile(
    r"^templates/index\.json\.sections\.ss_feature_1_pro_[^.]+\.blocks\.slide_[^.]+\.settings\.image$",
    re.IGNORECASE,
)
_THEME_FEATURE_HIGHLIGHT_CARD_SLOT_PATHS: dict[str, tuple[str, str]] = {
    "card1": (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.title",
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.text",
    ),
    "card2": (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.title",
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.text",
    ),
    "card3": (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.title",
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.text",
    ),
    "card4": (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp.settings.title",
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp.settings.text",
    ),
}
_THEME_FEATURE_HIGHLIGHT_MANAGED_TEXT_SLOT_PATHS: frozenset[str] = frozenset(
    path
    for card_paths in _THEME_FEATURE_HIGHLIGHT_CARD_SLOT_PATHS.values()
    for path in card_paths
)
_THEME_RICH_TEXT_SECTION_FILENAME = "sections/rich-text.liquid"
_THEME_FOOTER_GROUP_FILENAME = "sections/footer-group.json"
_THEME_HEADER_DRAWER_FILENAME = "snippets/header-drawer.liquid"
_THEME_INDEX_TEMPLATE_FILENAME = "templates/index.json"
_THEME_PRODUCT_CARD_SNIPPET_FILENAME = "snippets/product-card.liquid"
_THEME_SHOPPABLE_VIDEO_SECTION_FILENAME = "sections/ss-shoppable-video.liquid"
_THEME_MAIN_PAGE_BUTTON_LINK_KEYS: frozenset[str] = frozenset({"button_link", "button_url"})
_THEME_PRODUCT_CARD_TITLE_PRODUCT_URL_HREF_RE = re.compile(
    (
        r'(<a\b(?=[^>]*\bclass="[^"]*(?:product-card__title|title)[^"]*")'
        r'[^>]*\bhref=)"\{\{\s*product(?:_|\.)url\s*\}\}"'
    ),
    re.IGNORECASE,
)
_THEME_PRODUCT_CARD_PRODUCT_URL_HREF_RE = re.compile(
    r'href="\{\{\s*product(?:_|\.)url\s*\}\}"',
    re.IGNORECASE,
)
_THEME_SHOPPABLE_VIDEO_CART_JSON_LINE_RE = re.compile(
    (
        r"^(?P<indent>\s*)"
        r"const\s+cart\{\{\s*forloop\.index\s*\}\}\s*="
        r"\s*await\s+res\{\{\s*forloop\.index\s*\}\}\.json\(\);\s*$"
    )
)
_THEME_SHOPPABLE_VIDEO_CART_UPDATE_PUBLISH_RE = re.compile(
    (
        r"theme\.pubsub\.publish\(\s*"
        r"theme\.pubsub\.PUB_SUB_EVENTS\.cartUpdate\s*,\s*"
        r"\{\s*cart:\s*cart\{\{\s*forloop\.index\s*\}\}\s*\}\s*"
        r"\)\s*;"
    )
)
_THEME_TRACK_ORDER_TITLE_RE = re.compile(
    r"^\s*track\s+(?:your|my)\s+order\s*$",
    re.IGNORECASE,
)
_THEME_TRACK_ORDER_LINK_HREF_RE = re.compile(
    r'href\s*=\s*["\']/pages/(?:track-order|track-your-order)["\']',
    re.IGNORECASE,
)
_THEME_FOOTER_TABS_SECTION_FILENAMES: frozenset[str] = frozenset(
    {"sections/ss-footer-4.liquid", "sections/a-ss-footer-4.liquid"}
)
_THEME_FOOTER_CONTACT_PAGE_PATH = "/pages/contact"
_THEME_FOOTER_CONTACT_SUPPORT_LINK_HTML = (
    f'<a href="{_THEME_FOOTER_CONTACT_PAGE_PATH}"><strong><u>Contact our support team</u></strong></a>'
)
_THEME_FOOTER_CONTACT_US_LINK_HTML = (
    f'<a href="{_THEME_FOOTER_CONTACT_PAGE_PATH}"><strong><u>Contact us</u></strong></a>'
)
_THEME_FOOTER_REFUND_CONTACT_TEXT_RE = re.compile(
    r"Contact\s+our\s+support\s+team",
    re.IGNORECASE,
)
_THEME_FOOTER_QUESTIONS_HELP_SENTENCE_RE = re.compile(
    r"Our\s+team\s+is\s+here\s+to\s+help\.?",
    re.IGNORECASE,
)
_THEME_FOOTER_TAB_LINK_STYLE_SNIPPET = (
    "  .footer-tab-text-{{ section.id }} a,\n"
    "  .footer-tab-height-cal-{{ section.id }} a {\n"
    "    text-decoration: underline !important;\n"
    "    text-underline-offset: 2px;\n"
    "    font-weight: 700;\n"
    "    cursor: pointer;\n"
    "  }\n\n"
)
_THEME_CONTACT_TEMPLATE_FILENAME_RE = re.compile(
    r"^templates/page\.contact(?:-[a-z0-9]+)*\.json$",
    re.IGNORECASE,
)
_THEME_CONTACT_EMAIL_VALUE_RE = re.compile(
    r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$",
    re.IGNORECASE,
)
_THEME_EXPORT_REQUIRED_TEMPLATE_FILES: tuple[str, ...] = (
    "templates/collection.json",
    "templates/list-collections.json",
)
_THEME_EXPORT_REQUIRED_ARCHIVE_FILES: tuple[str, ...] = (
    "templates/index.json",
    "templates/collection.json",
    "sections/footer-group.json",
)
_THEME_EXPORT_REQUIRED_COLLECTION_SECTIONS: tuple[str, ...] = (
    "main-collection-banner",
    "main-collection",
)
_THEME_SECONDARY_SECTION_BACKGROUND_CSS_VAR = "--color-page-bg-secondary"
_THEME_SECONDARY_SECTION_BACKGROUND_FILENAMES: tuple[str, ...] = (
    "sections/ss-before-after-4.liquid",
    "sections/ss-before-after-image-4.liquid",
    "sections/ss-countdown-timer-4.liquid",
)
_THEME_SECONDARY_SECTION_BACKGROUND_COLOR_RE = re.compile(
    r"background-color:\s*\{\{\s*background_color\s*\}\}\s*;",
    re.IGNORECASE,
)
_THEME_SECONDARY_SECTION_BACKGROUND_IMAGE_RE = re.compile(
    r"background-image:\s*\{\{\s*background_gradient\s*\}\}\s*;",
    re.IGNORECASE,
)
_THEME_SECONDARY_COUNTDOWN_SHAPE_FILL_RE = re.compile(
    r'fill="\{\{\s*background_color\s*\}\}"',
    re.IGNORECASE,
)
_LOCAL_THEME_COLLECTION_BANNER_SECTION_FILENAME = "sections/main-collection-banner.liquid"
_LOCAL_THEME_COLLECTION_BANNER_SECTION_VARIABLES_SNIPPET = (
    "    {%- if desktop_image != blank %}\n"
    "      {%- render 'section-variables', section: section -%}\n"
    "      {%- if section.settings.image_height == 'adapt' %}\n"
)
_LOCAL_THEME_COLLECTION_BANNER_SECTION_VARIABLES_REPLACEMENT = (
    "    {%- render 'section-variables', section: section -%}\n"
    "    {%- if desktop_image != blank %}\n"
    "      {%- if section.settings.image_height == 'adapt' %}\n"
)
_LOCAL_THEME_COLLECTION_BANNER_BOX_CLASS_SNIPPET = (
    'class="banner__box md:text-{{ section.settings.text_alignment }} '
    'text-{{ section.settings.text_alignment_mobile }}"'
)
_LOCAL_THEME_COLLECTION_BANNER_BOX_CLASS_REPLACEMENT = (
    'class="banner__box main-collection-banner__content md:text-{{ '
    'section.settings.text_alignment }} text-{{ section.settings.text_alignment_mobile }}"'
)
_LOCAL_THEME_COLLECTION_BANNER_TEXT_COLOR_STYLE_SNIPPET = (
    "\n"
    "  #shopify-section-{{ section.id }} .main-collection-banner__content {\n"
    "    color: rgb(var(--color-foreground));\n"
    "  }\n"
)
_THEME_EXPORT_ALLOWED_ROOT_DIRECTORIES: frozenset[str] = frozenset(
    {
        "assets",
        "config",
        "layout",
        "locales",
        "sections",
        "snippets",
        "templates",
    }
)
_LOCAL_SHOPIFY_THEME_DEFAULT_SHOP_DOMAIN = "local.mos"
_LOCAL_SHOPIFY_THEME_DEFAULT_THEME_NAME = "mos-local-theme"
_LOCAL_SHOPIFY_THEME_DEFAULT_THEME_ROLE = "MAIN"
_LOCAL_SHOPIFY_THEME_DEFAULT_NAVIGATION_SIZE_PX = 18
_LOCAL_SHOPIFY_THEME_BASELINE_ZIP_RELATIVE_PATH = os.path.join(
    "shopify-funnel-app",
    "theme",
    "futrgroup2-theme.zip",
)
_LOCAL_SHOPIFY_THEME_SLOT_SOURCE_FILENAMES: tuple[str, ...] = (
    "templates/index.json",
    "templates/collection.json",
)
_LOCAL_SHOPIFY_THEME_BASELINE_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "mos-template-export/",
)
_LOCAL_SHOPIFY_THEME_SECTION_GROUP_IMPORT_COMPAT_TYPE_ALIASES: dict[str, str] = {
    "header": "a-header",
    "footer": "a-footer",
    "search-drawer": "a-search-drawer",
    "multicolumn-with-icons": "a-multicolumn-with-icons",
    "ss-footer-4": "a-ss-footer-4",
}
_LOCAL_SHOPIFY_THEME_SECTION_GROUP_IMPORT_COMPAT_FILENAMES: tuple[str, ...] = (
    "sections/header-group.json",
    "sections/footer-group.json",
    "sections/overlay-group.json",
)
_LOCAL_SHOPIFY_THEME_LAYOUT_FILENAME = "layout/theme.liquid"
_LOCAL_SHOPIFY_THEME_FOOTER_GROUP_FILENAME = "sections/footer-group.json"
_LOCAL_SHOPIFY_THEME_SETTINGS_FILENAME = "config/settings_data.json"
_LOCAL_SHOPIFY_THEME_INDEX_TEMPLATE_FILENAME = "templates/index.json"
_LOCAL_SHOPIFY_THEME_RICH_TEXT_SECTION_ID = "rich_text_U6caVk"
_LOCAL_SHOPIFY_THEME_RICH_TEXT_HEADING_BLOCK_ID = "heading_PpFgCk"
_LOCAL_SHOPIFY_THEME_RICH_TEXT_HEADING_EMPHASIS_WORD_COUNT = 3
_LOCAL_SHOPIFY_THEME_MAX_DISCOVERED_IMAGE_SLOTS = 24
_LOCAL_SHOPIFY_THEME_MAX_DISCOVERED_TEXT_SLOTS = 80
_LOCAL_SHOPIFY_THEME_IMAGE_FILE_EXTENSION_RE = re.compile(
    r"\.(?:avif|gif|jpe?g|png|svg|webp)(?:$|[?#])",
    re.IGNORECASE,
)
_LOCAL_SHOPIFY_THEME_LAYOUT_WORKSPACE_CSS_RE = re.compile(
    r"""['"](?P<asset>[^'"]*workspace-brand\.css)['"]\s*\|\s*asset_url""",
    re.IGNORECASE,
)
_LOCAL_SHOPIFY_THEME_CSS_IMPORT_URL_RE = re.compile(
    r"""@import\s+url\((?P<quote>["']?)(?P<url>[^"')]+)(?P=quote)\)\s*;""",
    re.IGNORECASE,
)
_LOCAL_SHOPIFY_THEME_HEX_COLOR_RE = re.compile(
    r"^#(?P<hex>[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$",
    re.IGNORECASE,
)
_LOCAL_SHOPIFY_THEME_RGB_COLOR_RE = re.compile(
    r"^rgba?\((?P<channels>[^)]+)\)$",
    re.IGNORECASE,
)
_LOCAL_SHOPIFY_THEME_CSS_VAR_RE = re.compile(
    r"^var\(\s*(?P<name>--[a-z0-9\-_]+)\s*\)$",
    re.IGNORECASE,
)
_LOCAL_SHOPIFY_THEME_BRAND_LOGO_CSS_VAR_RE = re.compile(
    r'(?m)^(\s*--mos-brand-logo-url\s*:\s*")(?P<url>(?:[^"\\]|\\.)*)(";\s*)$'
)
_LOCAL_SHOPIFY_THEME_BRAND_LOGO_META_RE = re.compile(
    r'(<meta\s+name="mos-brand-logo-url"\s+content=")(?P<url>[^"]*)("\s*/?>)',
    re.IGNORECASE,
)
_ASSET_SHOPIFY_FILE_URLS_CACHE_KEY = "shopifyFileUrlsByShopDomain"
_THEME_TEMPLATE_BRAND_LOGO_UPLOAD_SETTING_PATH = "__brand_logo__"
_LOCAL_SHOPIFY_THEME_TEXT_ENUM_VALUES = {
    "adapt",
    "auto",
    "center",
    "false",
    "left",
    "large",
    "medium",
    "none",
    "no",
    "right",
    "small",
    "solid",
    "true",
    "yes",
}
_THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH = 180
_THEME_IMAGE_PROMPT_GENERAL_CONTEXT_MAX_LENGTH = 2000
_THEME_IMAGE_PROMPT_SLOT_CONTEXT_MAX_LENGTH = 900
_THEME_IMAGE_PROMPT_BRAND_DESCRIPTION_MAX_LENGTH = 480
_THEME_IMAGE_PROMPT_METADATA_BRAND_DESCRIPTION_KEY = "brandDescription"
_THEME_COPY_GUIDELINE_MAX_LENGTH = 180
_THEME_COPY_OPTION_MAX_LENGTH = 32
_THEME_SYNC_AI_IMAGE_PROMPT_BASE = (
    "Premium ecommerce product image aligned to the provided product and brand context. "
    "High-detail, photoreal quality, commercially usable composition. "
    "Do not introduce unrelated product categories; depict only the product described in context. "
    "No text, no logos, no watermark, no UI."
)
_THEME_SYNC_AI_IMAGE_ROLE_GUIDANCE_BY_NAME = {
    "hero": "Hero composition with the product as the focal subject, fully utilizing the requested aspect ratio.",
    "gallery": "Product detail composition showing materials, features, and craftsmanship.",
    "supporting": "Clean supporting visual tied to documented product benefits and usage context.",
    "background": "Ambient background scene that complements the product identity.",
    "generic": "Lifestyle composition aligned to the product and brand positioning.",
}
_THEME_SYNC_AI_FEATURE_ICON_ROLE_GUIDANCE = (
    "Create a clean ecommerce feature icon that directly symbolizes the feature claim and fills most of the frame."
)
_THEME_SYNC_AI_FEATURE_ICON_CONSTRAINTS = (
    "Icon-style requirements: single symbolic icon, simple centered composition, clear silhouette, "
    "minimal background detail, no text, no letters, no numbers, no people, no product photography. "
    "Scale policy: make the icon large and legible, occupying roughly 70-80% of the canvas with tight outer padding. "
    "Do not place the icon inside a badge, card, tile, frame, or inset square. "
    "Background policy: hard requirement: always use a flat solid background with the exact --color-page-bg hex value "
    "provided in context; no gradients, shadows, borders, or off-tone background variations. "
    "Icon color policy: hard requirement: all icon strokes, fills, and shapes must use the exact "
    "--color-cta-shell hex value provided in context; do not introduce other accent colors."
)
_THEME_SYNC_AI_IMAGE_ASPECT_RATIO_BY_RECOMMENDED_ASPECT = {
    "landscape": "16:9",
    "portrait": "3:4",
    "square": "1:1",
    "any": "4:3",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "4:3",
    "3:4": "3:4",
    "1:1": "1:1",
}
_THEME_SYNC_AI_IMAGE_MIN_SIZE_BY_ASPECT_RATIO = {
    "16:9": "1920x1080",
    "9:16": "1080x1920",
    "4:3": "1600x1200",
    "3:4": "1200x1600",
    "1:1": "1600x1600",
}
_THEME_IMAGE_SLOT_CONFIG_PATH = (
    Path(__file__).resolve().parents[4] / "theme_image_slot_config.json"
)
_THEME_SYNC_SLOT_GENERATION_STRATEGY_DEFAULT = "default"
_THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER = "testimonial_renderer"
_THEME_SYNC_SLOT_TESTIMONIAL_TEMPLATE_REVIEW_CARD = "review_card"


def _load_theme_sync_slot_prompt_overrides() -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
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

    aspect_ratio_overrides: dict[str, str] = {}
    render_hint_overrides: dict[str, str] = {}
    generation_strategy_by_path: dict[str, str] = {}
    testimonial_template_by_path: dict[str, str] = {}
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

        for index, raw_slot in enumerate(raw_slots):
            if not isinstance(raw_slot, dict):
                raise RuntimeError(
                    "Shared theme image slot config contains a non-object slot entry. "
                    f"theme={raw_theme_name}, index={index}."
                )
            raw_path = raw_slot.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise RuntimeError(
                    "Shared theme image slot config contains an invalid path value. "
                    f"theme={raw_theme_name}, index={index}."
                )
            slot_path = raw_path.strip()

            prompt_aspect_ratio = raw_slot.get("promptAspectRatio")
            if prompt_aspect_ratio is not None:
                if (
                    not isinstance(prompt_aspect_ratio, str)
                    or not prompt_aspect_ratio.strip()
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains an invalid "
                        "promptAspectRatio value. "
                        f"theme={raw_theme_name}, index={index}."
                    )
                normalized_aspect_ratio = prompt_aspect_ratio.strip()
                existing_aspect_ratio = aspect_ratio_overrides.get(slot_path)
                if (
                    existing_aspect_ratio is not None
                    and existing_aspect_ratio != normalized_aspect_ratio
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains conflicting "
                        "promptAspectRatio values. "
                        f"path={slot_path}."
                    )
                aspect_ratio_overrides[slot_path] = normalized_aspect_ratio

            prompt_render_hint = raw_slot.get("promptRenderHint")
            if prompt_render_hint is not None:
                if (
                    not isinstance(prompt_render_hint, str)
                    or not prompt_render_hint.strip()
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains an invalid "
                        "promptRenderHint value. "
                        f"theme={raw_theme_name}, index={index}."
                    )
                normalized_render_hint = prompt_render_hint.strip()
                existing_render_hint = render_hint_overrides.get(slot_path)
                if (
                    existing_render_hint is not None
                    and existing_render_hint != normalized_render_hint
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains conflicting "
                        "promptRenderHint values. "
                        f"path={slot_path}."
                    )
                render_hint_overrides[slot_path] = normalized_render_hint

            raw_generation_strategy = raw_slot.get("generationStrategy")
            normalized_generation_strategy = _THEME_SYNC_SLOT_GENERATION_STRATEGY_DEFAULT
            if raw_generation_strategy is not None:
                if (
                    not isinstance(raw_generation_strategy, str)
                    or not raw_generation_strategy.strip()
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains an invalid "
                        "generationStrategy value. "
                        f"theme={raw_theme_name}, index={index}."
                    )
                normalized_generation_strategy = raw_generation_strategy.strip().lower()
                if normalized_generation_strategy not in {
                    _THEME_SYNC_SLOT_GENERATION_STRATEGY_DEFAULT,
                    _THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER,
                }:
                    raise RuntimeError(
                        "Shared theme image slot config contains an unsupported "
                        "generationStrategy value. "
                        f"path={slot_path}, generationStrategy={normalized_generation_strategy}."
                    )
                existing_generation_strategy = generation_strategy_by_path.get(slot_path)
                if (
                    existing_generation_strategy is not None
                    and existing_generation_strategy != normalized_generation_strategy
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains conflicting "
                        "generationStrategy values. "
                        f"path={slot_path}."
                    )
                if normalized_generation_strategy != _THEME_SYNC_SLOT_GENERATION_STRATEGY_DEFAULT:
                    generation_strategy_by_path[slot_path] = normalized_generation_strategy

            raw_testimonial_template = raw_slot.get("testimonialTemplate")
            if raw_testimonial_template is not None:
                if (
                    not isinstance(raw_testimonial_template, str)
                    or not raw_testimonial_template.strip()
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains an invalid "
                        "testimonialTemplate value. "
                        f"theme={raw_theme_name}, index={index}."
                    )
                normalized_testimonial_template = raw_testimonial_template.strip()
                if (
                    normalized_testimonial_template
                    != _THEME_SYNC_SLOT_TESTIMONIAL_TEMPLATE_REVIEW_CARD
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains an unsupported "
                        "testimonialTemplate value. "
                        f"path={slot_path}, testimonialTemplate={normalized_testimonial_template}."
                    )
                if (
                    normalized_generation_strategy
                    != _THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER
                ):
                    raise RuntimeError(
                        "Shared theme image slot config can only use testimonialTemplate "
                        "when generationStrategy=testimonial_renderer. "
                        f"path={slot_path}."
                    )
                existing_testimonial_template = testimonial_template_by_path.get(slot_path)
                if (
                    existing_testimonial_template is not None
                    and existing_testimonial_template != normalized_testimonial_template
                ):
                    raise RuntimeError(
                        "Shared theme image slot config contains conflicting "
                        "testimonialTemplate values. "
                        f"path={slot_path}."
                    )
                testimonial_template_by_path[slot_path] = normalized_testimonial_template

    return (
        aspect_ratio_overrides,
        render_hint_overrides,
        generation_strategy_by_path,
        testimonial_template_by_path,
    )


(
    _THEME_SYNC_SLOT_ASPECT_RATIO_OVERRIDE_BY_PATH,
    _THEME_SYNC_SLOT_IMAGE_RENDER_HINT_BY_PATH,
    _THEME_SYNC_SLOT_GENERATION_STRATEGY_BY_PATH,
    _THEME_SYNC_SLOT_TESTIMONIAL_TEMPLATE_BY_PATH,
) = _load_theme_sync_slot_prompt_overrides()
_GEMINI_IMAGE_REFERENCES_ENABLED_TRUE_VALUES = {"1", "true", "yes", "on"}
_THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY = max(
    1, settings.FUNNEL_IMAGE_GENERATION_MAX_CONCURRENCY
)
_SHOPIFY_TEMPLATE_IMAGE_GENERATION_MAX_CONCURRENCY = 1
_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_ATTEMPTS = 24
_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_BASE_DELAY_SECONDS = 8.0
_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_DELAY_SECONDS = 120.0
_UNSUPPORTED_THEME_TEXT_VALUE_TRANSLATION = str.maketrans(
    {
        '"': "",
        "'": "’",
        "<": "",
        ">": "",
        "\n": " ",
        "\r": " ",
    }
)
_THEME_SYNC_PROGRESS_CALLBACK: ContextVar[Any | None] = ContextVar(
    "theme_sync_progress_callback", default=None
)


def _has_explicit_gemini_hard_quota_signal(message: str) -> bool:
    if not isinstance(message, str):
        return False
    message_lower = message.lower()
    return (
        "exceeded your current quota" in message_lower
        or "quota exceeded" in message_lower
        or "insufficient quota" in message_lower
        or "billing account" in message_lower
        or "quota has been exhausted" in message_lower
    )


def _resolve_theme_export_sales_page_path(
    *,
    client_id: str,
    auth: AuthContext,
    session: Session,
) -> tuple[str, str | None]:
    product = session.scalars(
        select(Product)
        .where(Product.org_id == auth.org_id, Product.client_id == client_id)
        .order_by(Product.created_at.asc(), Product.id.asc())
        .limit(1)
    ).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Theme ZIP export requires at least one workspace product to resolve "
                "Shopify theme links."
            ),
        )

    try:
        require_product_route_slug(product=product)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Theme ZIP export could not resolve a public product slug for the first "
                f"workspace product: {exc}"
            ),
        ) from exc

    def _find_latest_sales_page_for_product(
        *,
        product_id: str | None,
    ) -> Any | None:
        query = (
            select(Product, Funnel.route_slug, FunnelPage.slug)
            .join(Funnel, Funnel.product_id == Product.id)
            .join(FunnelPage, FunnelPage.funnel_id == Funnel.id)
            .where(
                Funnel.org_id == auth.org_id,
                Funnel.client_id == client_id,
                Funnel.status.in_((FunnelStatusEnum.draft, FunnelStatusEnum.published)),
                FunnelPage.template_id == "sales-pdp",
            )
            .order_by(
                FunnelPage.created_at.desc(),
                FunnelPage.id.desc(),
                Funnel.created_at.desc(),
                Funnel.id.desc(),
                FunnelPage.ordering.desc(),
            )
            .limit(1)
        )
        if product_id is not None:
            query = query.where(Funnel.product_id == product_id)
        return session.execute(query).first()

    def _build_sales_page_path(
        *,
        target_product: Product,
        route_slug: Any,
        page_slug: Any,
    ) -> str | None:
        target_funnel_slug = str(route_slug or "").strip()
        target_page_slug = str(page_slug or "").strip()
        if not target_funnel_slug or not target_page_slug:
            return None
        try:
            target_product_slug = require_product_route_slug(product=target_product)
        except ValueError:
            return None
        return f"/f/{target_product_slug}/{target_funnel_slug}/{target_page_slug}"

    first_product_sales_page = _find_latest_sales_page_for_product(product_id=product.id)
    if first_product_sales_page is not None:
        first_product_record, first_route_slug, first_page_slug = first_product_sales_page
        if isinstance(first_product_record, Product):
            first_product_sales_page_path = _build_sales_page_path(
                target_product=first_product_record,
                route_slug=first_route_slug,
                page_slug=first_page_slug,
            )
            if first_product_sales_page_path:
                return first_product_sales_page_path, None

    latest_workspace_sales_page = _find_latest_sales_page_for_product(product_id=None)
    if latest_workspace_sales_page is not None:
        workspace_product, workspace_route_slug, workspace_page_slug = (
            latest_workspace_sales_page
        )
        if isinstance(workspace_product, Product):
            workspace_sales_page_path = _build_sales_page_path(
                target_product=workspace_product,
                route_slug=workspace_route_slug,
                page_slug=workspace_page_slug,
            )
            if workspace_sales_page_path:
                return (
                    workspace_sales_page_path,
                    (
                        "Theme ZIP downloaded, but sales page was not found for the first "
                        f"workspace product '{product.title}'. Using latest available sales page "
                        f"from workspace product '{workspace_product.title}'."
                    ),
                )

    return (
        "",
        (
            "Theme ZIP downloaded, but sales page was not found for the first "
            f"workspace product '{product.title}'. Links were left blank."
        ),
    )


def _normalize_theme_export_main_page_button_links(
    *,
    filename: str,
    content: str,
    sales_page_path: str,
) -> str:
    if filename != _THEME_INDEX_TEMPLATE_FILENAME:
        return content

    try:
        parsed_content = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Theme ZIP export could not parse templates/index.json while rewriting CTA links.",
        ) from exc

    rewritten_button_count = 0

    def _rewrite_value(value: Any) -> Any:
        nonlocal rewritten_button_count
        if isinstance(value, dict):
            updated: dict[str, Any] = {}
            for key, nested_value in value.items():
                if key in _THEME_MAIN_PAGE_BUTTON_LINK_KEYS and isinstance(nested_value, str):
                    updated[key] = sales_page_path
                    rewritten_button_count += 1
                else:
                    updated[key] = _rewrite_value(nested_value)
            return updated
        if isinstance(value, list):
            return [_rewrite_value(item) for item in value]
        return value

    normalized_content = json.dumps(_rewrite_value(parsed_content), separators=(",", ":"))
    if rewritten_button_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export could not find any homepage CTA button links to rewrite "
                "in templates/index.json."
            ),
        )
    return normalized_content


def _normalize_theme_export_catalog_product_card_links(
    *,
    filename: str,
    content: str,
    sales_page_path: str,
) -> str:
    if filename != _THEME_PRODUCT_CARD_SNIPPET_FILENAME:
        return content

    normalized_content, rewritten_title_count = _THEME_PRODUCT_CARD_TITLE_PRODUCT_URL_HREF_RE.subn(
        rf'\1"{sales_page_path}"',
        content,
        count=1,
    )
    if rewritten_title_count != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export could not rewrite the catalog product title link "
                "in snippets/product-card.liquid."
            ),
        )

    normalized_content, rewritten_link_count = _THEME_PRODUCT_CARD_PRODUCT_URL_HREF_RE.subn(
        f'href="{sales_page_path}"',
        normalized_content,
        count=2,
    )
    if rewritten_link_count != 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export could not rewrite the expected catalog product links "
                "in snippets/product-card.liquid."
            ),
        )
    return normalized_content


def _normalize_theme_export_rich_text_section_content(
    *,
    filename: str,
    content: str,
) -> str:
    if filename != _THEME_RICH_TEXT_SECTION_FILENAME:
        return content

    normalized = re.sub(
        r"^\s*--footer-text-color:\s*\{\{\s*settings\.footer_text\s*\}\}\s*;\s*\n",
        "",
        content,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    normalized = re.sub(
        (
            r"^\s*--color-foreground:\s*\{\{\s*settings\.footer_text\.red\s*\}\}"
            r"\s*\{\{\s*settings\.footer_text\.green\s*\}\}\s*"
            r"\{\{\s*settings\.footer_text\.blue\s*\}\}\s*;\s*\n"
        ),
        "",
        normalized,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    normalized = re.sub(
        (
            r"\n\s*#shopify-section-\{\{\s*section\.id\s*\}\}\s+\.rich-text\s*\{\s*\n"
            r"\s*color:\s*var\(--footer-text-color\);\s*\n"
            r"\s*\}\s*"
        ),
        "\n",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized


def _normalize_theme_export_track_order_links(
    *,
    filename: str,
    content: str,
) -> str:
    normalized = content
    if filename == _THEME_HEADER_DRAWER_FILENAME:
        normalized = _THEME_TRACK_ORDER_LINK_HREF_RE.sub(
            'href="/pages/contact"',
            normalized,
        )

    if filename != _THEME_FOOTER_GROUP_FILENAME:
        return normalized

    template_data = _parse_theme_export_template_json(
        filename=filename,
        content=normalized,
    )
    sections = template_data.get("sections")
    if not isinstance(sections, dict):
        return normalized

    changed = False
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks")
        if not isinstance(blocks, dict):
            continue
        block_keys_to_remove: list[str] = []
        for block_key, block in blocks.items():
            if not isinstance(block, dict):
                continue
            settings = block.get("settings")
            if not isinstance(settings, dict):
                continue
            title = settings.get("title")
            text = settings.get("text")
            if isinstance(text, str) and text.strip():
                if (
                    _THEME_FOOTER_REFUND_CONTACT_TEXT_RE.search(text)
                    and _THEME_FOOTER_CONTACT_PAGE_PATH not in text
                ):
                    updated_text = _THEME_FOOTER_REFUND_CONTACT_TEXT_RE.sub(
                        _THEME_FOOTER_CONTACT_SUPPORT_LINK_HTML,
                        text,
                        count=1,
                    )
                    if updated_text != text:
                        settings["text"] = updated_text
                        changed = True
                        text = updated_text

                if (
                    _THEME_FOOTER_QUESTIONS_HELP_SENTENCE_RE.search(text)
                    and "Contact us" not in text
                    and _THEME_FOOTER_CONTACT_PAGE_PATH not in text
                ):
                    updated_text = _THEME_FOOTER_QUESTIONS_HELP_SENTENCE_RE.sub(
                        f"Our team is here to help. {_THEME_FOOTER_CONTACT_US_LINK_HTML}.",
                        text,
                        count=1,
                    )
                    if updated_text != text:
                        settings["text"] = updated_text
                        changed = True

            if not isinstance(title, str) or not _THEME_TRACK_ORDER_TITLE_RE.match(
                title.strip()
            ):
                continue
            block_keys_to_remove.append(block_key)
        for block_key in block_keys_to_remove:
            blocks.pop(block_key, None)
            changed = True

    if not changed:
        return normalized
    return json.dumps(template_data, separators=(",", ":"))


def _normalize_theme_export_shoppable_video_cart_counter_updates(
    *,
    filename: str,
    content: str,
) -> str:
    if filename != _THEME_SHOPPABLE_VIDEO_SECTION_FILENAME:
        return content

    lines = content.splitlines(keepends=True)
    if not lines:
        return content

    changed = False
    normalized_lines: list[str] = []
    line_count = len(lines)
    for index, line in enumerate(lines):
        normalized_lines.append(line)
        cart_line_match = _THEME_SHOPPABLE_VIDEO_CART_JSON_LINE_RE.match(
            line.rstrip("\r\n")
        )
        if cart_line_match is None:
            continue

        next_line = lines[index + 1].strip() if index + 1 < line_count else ""
        if _THEME_SHOPPABLE_VIDEO_CART_UPDATE_PUBLISH_RE.search(next_line):
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


def _normalize_theme_export_footer_tab_link_styling(
    *,
    filename: str,
    content: str,
) -> str:
    if filename not in _THEME_FOOTER_TABS_SECTION_FILENAMES:
        return content
    if ".footer-tab-text-{{ section.id }} a," in content:
        return content

    media_query_marker = "@media(min-width: 1024px) {"
    if media_query_marker in content:
        return content.replace(
            media_query_marker,
            f"{_THEME_FOOTER_TAB_LINK_STYLE_SNIPPET}{media_query_marker}",
            1,
        )
    return f"{content.rstrip()}\n\n{_THEME_FOOTER_TAB_LINK_STYLE_SNIPPET}"


def _build_theme_export_contact_multiline_html(*, text: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Theme ZIP export contact rewrite received empty multiline text content.",
        )
    return f"<p>{'<br/>'.join(escape(line) for line in lines)}</p>"


def _build_theme_export_contact_email_html(*, email: str) -> str:
    normalized_email = email.strip()
    if not normalized_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Theme ZIP export contact rewrite received an empty support email value.",
        )
    if not _THEME_CONTACT_EMAIL_VALUE_RE.match(normalized_email):
        return _build_theme_export_contact_multiline_html(text=normalized_email)
    escaped_email = escape(normalized_email)
    return f'<p><a href="mailto:{escaped_email}">{escaped_email}</a></p>'


def _build_theme_export_contact_phone_html(
    *,
    phone: str,
    support_hours: str,
) -> str:
    normalized_phone = phone.strip()
    normalized_hours = support_hours.strip()
    if not normalized_phone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Theme ZIP export contact rewrite received an empty support phone value.",
        )
    if not normalized_hours:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Theme ZIP export contact rewrite received empty support hours content.",
        )

    tel_value = re.sub(r"[^0-9+]", "", normalized_phone)
    has_digits = any(char.isdigit() for char in tel_value)
    escaped_phone = escape(normalized_phone)
    escaped_hours = escape(normalized_hours)
    if has_digits:
        phone_line = f'<a href="tel:{escape(tel_value)}">{escaped_phone}</a>'
    else:
        phone_line = escaped_phone
    return f"<p>{phone_line}<br/>{escaped_hours}</p>"


def _normalize_theme_export_contact_page_template_content(
    *,
    filename: str,
    content: str,
    contact_page_values: dict[str, str] | None,
) -> str:
    if not _THEME_CONTACT_TEMPLATE_FILENAME_RE.match(filename):
        return content
    if not isinstance(contact_page_values, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Theme ZIP export cannot rewrite contact template content because compliance "
                "contact values were not provided."
            ),
        )

    required_keys = (
        "businessAddress",
        "supportEmail",
        "supportPhone",
        "supportHours",
    )
    missing_or_invalid_keys: list[str] = []
    normalized_contact_values: dict[str, str] = {}
    for key in required_keys:
        value = contact_page_values.get(key)
        if not isinstance(value, str) or not value.strip():
            missing_or_invalid_keys.append(key)
            continue
        normalized_contact_values[key] = value.strip()
    if missing_or_invalid_keys:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Theme ZIP export cannot rewrite contact template content because compliance "
                "contact values are missing or invalid: "
                + ", ".join(sorted(missing_or_invalid_keys))
                + "."
            ),
        )

    template_data = _parse_theme_export_template_json(
        filename=filename,
        content=content,
    )
    sections = template_data.get("sections")
    if not isinstance(sections, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export cannot rewrite contact template content because "
                f"{filename}.sections is missing or invalid."
            ),
        )

    contact_html_by_heading = {
        "address": _build_theme_export_contact_multiline_html(
            text=normalized_contact_values["businessAddress"]
        ),
        "email": _build_theme_export_contact_email_html(
            email=normalized_contact_values["supportEmail"]
        ),
        "phone": _build_theme_export_contact_phone_html(
            phone=normalized_contact_values["supportPhone"],
            support_hours=normalized_contact_values["supportHours"],
        ),
    }
    rewritten_headings: set[str] = set()
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        section_type = section.get("type")
        if not isinstance(section_type, str) or section_type not in {
            "contact-form",
            "contact-with-map",
        }:
            continue
        blocks = section.get("blocks")
        if not isinstance(blocks, dict):
            continue
        for block in blocks.values():
            if not isinstance(block, dict):
                continue
            if block.get("type") != "contact":
                continue
            settings = block.get("settings")
            if not isinstance(settings, dict):
                continue
            heading = settings.get("heading")
            if not isinstance(heading, str) or not heading.strip():
                continue
            normalized_heading = heading.strip().lower()
            if normalized_heading.startswith("address"):
                settings["text"] = contact_html_by_heading["address"]
                rewritten_headings.add("address")
            elif normalized_heading.startswith("email"):
                settings["text"] = contact_html_by_heading["email"]
                rewritten_headings.add("email")
            elif normalized_heading.startswith("phone"):
                settings["text"] = contact_html_by_heading["phone"]
                rewritten_headings.add("phone")

    required_headings = {"address", "email", "phone"}
    missing_headings = sorted(required_headings - rewritten_headings)
    if missing_headings:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export cannot rewrite contact template content because "
                f"{filename} is missing expected contact blocks: "
                + ", ".join(missing_headings)
                + "."
            ),
        )
    return json.dumps(template_data, separators=(",", ":"))


def _normalize_local_theme_shop_domain(*, shop_domain: str | None) -> str:
    if not isinstance(shop_domain, str) or not shop_domain.strip():
        return _LOCAL_SHOPIFY_THEME_DEFAULT_SHOP_DOMAIN
    normalized = shop_domain.strip().lower()
    if any(char.isspace() for char in normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="shopDomain must not include whitespace characters.",
        )
    if any(char in normalized for char in ('"', "'", "<", ">", "\n", "\r")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="shopDomain contains unsupported characters.",
        )
    return normalized


def _resolve_local_theme_selector(
    *,
    theme_id: str | None,
    theme_name: str | None,
) -> tuple[str, str, str]:
    resolved_theme_name = (
        theme_name.strip()
        if isinstance(theme_name, str) and theme_name.strip()
        else _LOCAL_SHOPIFY_THEME_DEFAULT_THEME_NAME
    )
    resolved_theme_id = (
        theme_id.strip() if isinstance(theme_id, str) and theme_id.strip() else None
    )
    if not resolved_theme_id:
        theme_slug = _slugify_theme_export_token(resolved_theme_name)
        resolved_theme_id = f"local://themes/{theme_slug}"
    return resolved_theme_id, resolved_theme_name, _LOCAL_SHOPIFY_THEME_DEFAULT_THEME_ROLE


def _resolve_local_shopify_theme_baseline_zip_path() -> str:
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    baseline_zip_path = os.path.join(repo_root, _LOCAL_SHOPIFY_THEME_BASELINE_ZIP_RELATIVE_PATH)
    if not os.path.isfile(baseline_zip_path):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline archive is missing. "
                f"Expected file at {_LOCAL_SHOPIFY_THEME_BASELINE_ZIP_RELATIVE_PATH}."
            ),
        )
    return baseline_zip_path


def _normalize_local_shopify_theme_baseline_filename(*, raw_filename: str) -> str:
    if not isinstance(raw_filename, str) or not raw_filename.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local Shopify theme baseline contains an empty filename entry.",
        )
    normalized = raw_filename.strip().replace("\\", "/").lstrip("/")
    path_parts = [part for part in normalized.split("/") if part and part != "."]
    if not path_parts or any(part == ".." for part in path_parts):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline contains an unsupported filename path "
                f"entry={raw_filename!r}."
            ),
        )
    return "/".join(path_parts)


def _load_local_shopify_theme_baseline_files() -> tuple[list[str], dict[str, dict[str, str]]]:
    baseline_zip_path = _resolve_local_shopify_theme_baseline_zip_path()
    try:
        zip_file = zipfile.ZipFile(baseline_zip_path)
    except (FileNotFoundError, OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to open the local Shopify theme baseline archive.",
        ) from exc

    ordered_filenames: list[str] = []
    files_by_filename: dict[str, dict[str, str]] = {}
    with zip_file:
        for info in zip_file.infolist():
            if info.is_dir():
                continue
            filename = _normalize_local_shopify_theme_baseline_filename(
                raw_filename=info.filename
            )
            if any(
                filename.startswith(prefix)
                for prefix in _LOCAL_SHOPIFY_THEME_BASELINE_EXCLUDED_PREFIXES
            ):
                continue
            if filename in files_by_filename:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Local Shopify theme baseline contains duplicate filename entries. "
                        f"filename={filename}."
                    ),
                )
            file_bytes = zip_file.read(info.filename)
            file_entry: dict[str, str] = {"filename": filename}
            try:
                file_entry["content"] = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                file_entry["contentBase64"] = base64.b64encode(file_bytes).decode("ascii")
            ordered_filenames.append(filename)
            files_by_filename[filename] = file_entry

    if not ordered_filenames:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local Shopify theme baseline archive does not contain any files.",
        )
    return ordered_filenames, files_by_filename


def _is_local_theme_image_setting_candidate(*, key: str, value: str) -> bool:
    key_lower = key.strip().lower()
    if not key_lower:
        return False
    if not (
        key_lower in {"image", "mobile_image", "image_mobile", "desktop_image", "logo", "logo_mobile"}
        or key_lower.endswith("_image")
        or re.fullmatch(r"image_\d+", key_lower)
    ):
        return False

    value_text = value.strip()
    if not value_text:
        return True
    if value_text.startswith(("shopify://", "http://", "https://", "/", "gid://")):
        return True
    return bool(_LOCAL_SHOPIFY_THEME_IMAGE_FILE_EXTENSION_RE.search(value_text))


def _is_local_theme_text_setting_candidate(*, key: str, value: str) -> bool:
    key_lower = key.strip().lower()
    if not key_lower:
        return False
    is_allowed_key = (
        key_lower
        in {
            "button_label",
            "caption",
            "content",
            "description",
            "heading",
            "label",
            "overline",
            "preheading",
            "subheading",
            "text",
            "title",
            "body",
        }
        or re.fullmatch(
            r"(?:heading|title|subheading|text|label|description|caption|content|body)_\d+",
            key_lower,
        )
        is not None
    )
    if not is_allowed_key:
        return False

    normalized_value = value.strip()
    if not normalized_value:
        return True
    lowered_value = normalized_value.lower()
    if lowered_value in _LOCAL_SHOPIFY_THEME_TEXT_ENUM_VALUES:
        return False
    if lowered_value.startswith(("shopify://", "http://", "https://", "gid://")):
        return False
    if re.fullmatch(r"#[0-9a-f]{3,8}", lowered_value):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw)?", lowered_value):
        return False
    return True


def _infer_local_theme_image_slot_role(*, setting_path: str) -> str:
    lowered = setting_path.lower()
    if any(token in lowered for token in ("hero", "banner", "slideshow", "featured-product")):
        return "hero"
    if any(
        token in lowered
        for token in (
            "gallery",
            "collage",
            "lookbook",
            "slider",
            "carousel",
            "before_after",
            "before-after",
            "testimonial",
        )
    ):
        return "gallery"
    return "supporting"


def _infer_local_theme_image_slot_recommended_aspect(*, setting_path: str) -> str:
    lowered = setting_path.lower()
    if "logo" in lowered or "icon" in lowered:
        return "square"
    if "mobile" in lowered:
        return "portrait"
    if "before_image" in lowered or "after_image" in lowered:
        return "portrait"
    return "landscape"


def _collect_local_theme_slots_from_json_value(
    *,
    filename: str,
    value: Any,
    path_tokens: list[str],
    image_slots: list[dict[str, str]],
    text_slots: list[dict[str, str]],
    seen_image_slot_paths: set[str],
    seen_text_slot_paths: set[str],
) -> None:
    if isinstance(value, dict):
        if (
            value.get("disabled") is True
            and (
                path_tokens[:1] == ["sections"]
                and len(path_tokens) in {2, 4}
                and (len(path_tokens) == 2 or path_tokens[2] == "blocks")
            )
        ):
            return
        for key, nested_value in value.items():
            next_tokens = [*path_tokens, key]
            if isinstance(nested_value, str) and "settings" in next_tokens:
                setting_path = f"{filename}." + ".".join(next_tokens)
                normalized_current_value = nested_value.strip() or None
                if (
                    len(image_slots) < _LOCAL_SHOPIFY_THEME_MAX_DISCOVERED_IMAGE_SLOTS
                    and setting_path not in seen_image_slot_paths
                    and _is_local_theme_image_setting_candidate(
                        key=key,
                        value=nested_value,
                    )
                ):
                    seen_image_slot_paths.add(setting_path)
                    image_slots.append(
                        {
                            "path": setting_path,
                            "key": key.strip(),
                            "role": _infer_local_theme_image_slot_role(
                                setting_path=setting_path
                            ),
                            "recommendedAspect": _infer_local_theme_image_slot_recommended_aspect(
                                setting_path=setting_path
                            ),
                            "currentValue": normalized_current_value,
                        }
                    )
                if (
                    len(text_slots) < _LOCAL_SHOPIFY_THEME_MAX_DISCOVERED_TEXT_SLOTS
                    and setting_path not in seen_text_slot_paths
                    and _is_local_theme_text_setting_candidate(
                        key=key,
                        value=nested_value,
                    )
                ):
                    seen_text_slot_paths.add(setting_path)
                    text_slots.append(
                        {
                            "path": setting_path,
                            "key": key.strip(),
                            "currentValue": normalized_current_value,
                        }
                    )
                continue
            _collect_local_theme_slots_from_json_value(
                filename=filename,
                value=nested_value,
                path_tokens=next_tokens,
                image_slots=image_slots,
                text_slots=text_slots,
                seen_image_slot_paths=seen_image_slot_paths,
                seen_text_slot_paths=seen_text_slot_paths,
            )
        return
    if isinstance(value, list):
        for list_index, nested_value in enumerate(value):
            _collect_local_theme_slots_from_json_value(
                filename=filename,
                value=nested_value,
                path_tokens=[*path_tokens, str(list_index)],
                image_slots=image_slots,
                text_slots=text_slots,
                seen_image_slot_paths=seen_image_slot_paths,
                seen_text_slot_paths=seen_text_slot_paths,
            )


def _load_local_theme_json_file_from_export_files(
    *,
    files_by_filename: dict[str, dict[str, str]],
    filename: str,
) -> Any:
    file_entry = files_by_filename.get(filename)
    if not isinstance(file_entry, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Template export setting path targets a file that does not exist in the local "
                f"Shopify baseline archive. filename={filename}."
            ),
        )
    content = file_entry.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Template export setting path targets a file without text content in the local "
                f"Shopify baseline archive. filename={filename}."
            ),
        )
    return _parse_theme_export_template_json(filename=filename, content=content)


def _list_local_theme_template_slots(
    *,
    theme_id: str | None,
    theme_name: str | None,
    shop_domain: str | None,
) -> dict[str, Any]:
    resolved_theme_id, resolved_theme_name, resolved_theme_role = (
        _resolve_local_theme_selector(theme_id=theme_id, theme_name=theme_name)
    )
    _ordered_filenames, files_by_filename = _load_local_shopify_theme_baseline_files()
    image_slots: list[dict[str, str]] = []
    text_slots: list[dict[str, str]] = []
    seen_image_slot_paths: set[str] = set()
    seen_text_slot_paths: set[str] = set()
    for filename in _LOCAL_SHOPIFY_THEME_SLOT_SOURCE_FILENAMES:
        template_data = _load_local_theme_json_file_from_export_files(
            files_by_filename=files_by_filename,
            filename=filename,
        )
        _collect_local_theme_slots_from_json_value(
            filename=filename,
            value=template_data,
            path_tokens=[],
            image_slots=image_slots,
            text_slots=text_slots,
            seen_image_slot_paths=seen_image_slot_paths,
            seen_text_slot_paths=seen_text_slot_paths,
        )
    if not image_slots and not text_slots:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline did not provide any image or text "
                "template slots for draft generation."
            ),
        )
    return {
        "shopDomain": _normalize_local_theme_shop_domain(shop_domain=shop_domain),
        "themeId": resolved_theme_id,
        "themeName": resolved_theme_name,
        "themeRole": resolved_theme_role,
        "imageSlots": image_slots,
        "textSlots": text_slots,
    }


def _set_theme_template_json_path_value(
    *,
    template_data: Any,
    setting_path: str,
    path_tokens: list[str],
    value: str,
) -> None:
    current: Any = template_data
    for token_index, token in enumerate(path_tokens):
        is_last_token = token_index == len(path_tokens) - 1
        if isinstance(current, dict):
            if is_last_token:
                current[token] = value
                return
            next_token = path_tokens[token_index + 1]
            next_value = current.get(token)
            if next_value is None:
                next_value = [] if next_token.isdigit() else {}
                current[token] = next_value
            elif not isinstance(next_value, (dict, list)):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Template export could not apply a setting path because an intermediate token "
                        f"is not a JSON object/list. path={setting_path}, token={token}."
                    ),
                )
            current = next_value
            continue
        if isinstance(current, list):
            if not token.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Template export expected a numeric index while applying a list path token. "
                        f"path={setting_path}, token={token!r}."
                    ),
                )
            list_index = int(token)
            while len(current) <= list_index:
                current.append(None)
            if is_last_token:
                current[list_index] = value
                return
            next_token = path_tokens[token_index + 1]
            next_value = current[list_index]
            if next_value is None:
                next_value = [] if next_token.isdigit() else {}
                current[list_index] = next_value
            elif not isinstance(next_value, (dict, list)):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Template export could not apply a setting path because a list entry "
                        f"is not a JSON object/list. path={setting_path}, token={token}."
                    ),
                )
            current = next_value
            continue
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Template export encountered a non-container value while resolving "
                f"path={setting_path}."
            ),
        )


def _coerce_theme_setting_value_for_existing_type(
    *,
    existing_value: Any,
    next_value: str,
) -> str:
    if (
        isinstance(existing_value, str)
        and _THEME_RICHTEXT_MARKUP_RE.search(existing_value) is not None
    ):
        if _THEME_RICHTEXT_TOP_LEVEL_TAG_RE.search(next_value) is not None:
            return next_value

        normalized_text = next_value.replace("\r", "").strip()
        if not normalized_text:
            return ""

        paragraphs = [
            paragraph.strip()
            for paragraph in normalized_text.split("\n")
            if paragraph.strip()
        ]
        if not paragraphs:
            return ""
        return "".join(
            f"<p>{escape(paragraph, quote=False)}</p>"
            for paragraph in paragraphs
        )
    return next_value


def _apply_theme_template_setting_values_to_local_files(
    *,
    files_by_filename: dict[str, dict[str, str]],
    values_by_setting_path: dict[str, str],
) -> None:
    parsed_json_files_by_filename: dict[str, Any] = {}
    for setting_path, value in sorted(values_by_setting_path.items()):
        template_filename, path_tokens = _split_theme_template_setting_path(
            setting_path=setting_path
        )
        template_data = parsed_json_files_by_filename.get(template_filename)
        if template_data is None:
            template_data = _load_local_theme_json_file_from_export_files(
                files_by_filename=files_by_filename,
                filename=template_filename,
            )
            parsed_json_files_by_filename[template_filename] = template_data
        existing_value: Any = None
        try:
            existing_value = _resolve_theme_template_json_path_value(
                template_data=template_data,
                setting_path=setting_path,
                path_tokens=path_tokens,
            )
        except HTTPException:
            existing_value = None
        coerced_value = _coerce_theme_setting_value_for_existing_type(
            existing_value=existing_value,
            next_value=value,
        )
        _set_theme_template_json_path_value(
            template_data=template_data,
            setting_path=setting_path,
            path_tokens=path_tokens,
            value=coerced_value,
        )
    for filename, template_data in parsed_json_files_by_filename.items():
        file_entry = files_by_filename[filename]
        file_entry["content"] = json.dumps(
            template_data,
            indent=2,
            sort_keys=True,
        )
        file_entry.pop("contentBase64", None)


def _apply_local_theme_section_group_import_compatibility(
    *,
    ordered_filenames: list[str],
    files_by_filename: dict[str, dict[str, str]],
) -> None:
    for source_type, alias_type in (
        _LOCAL_SHOPIFY_THEME_SECTION_GROUP_IMPORT_COMPAT_TYPE_ALIASES.items()
    ):
        source_filename = f"sections/{source_type}.liquid"
        source_entry = files_by_filename.get(source_filename)
        source_content = (
            source_entry.get("content") if isinstance(source_entry, dict) else None
        )
        if not isinstance(source_content, str) or not source_content.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline is missing a required section file "
                    "for ZIP import compatibility. "
                    f"filename={source_filename}."
                ),
            )
        alias_filename = f"sections/{alias_type}.liquid"
        existing_alias_entry = files_by_filename.get(alias_filename)
        if existing_alias_entry is None:
            files_by_filename[alias_filename] = {
                "filename": alias_filename,
                "content": source_content,
            }
            ordered_filenames.append(alias_filename)
        else:
            existing_alias_content = existing_alias_entry.get("content")
            if (
                not isinstance(existing_alias_content, str)
                or existing_alias_content != source_content
            ):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Local Shopify theme baseline contains an unexpected section "
                        "alias file for ZIP import compatibility. "
                        f"filename={alias_filename}."
                    ),
                )

    for group_filename in _LOCAL_SHOPIFY_THEME_SECTION_GROUP_IMPORT_COMPAT_FILENAMES:
        group_entry = files_by_filename.get(group_filename)
        group_content = (
            group_entry.get("content") if isinstance(group_entry, dict) else None
        )
        if not isinstance(group_content, str) or not group_content.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline is missing a required section-group "
                    "JSON file for ZIP import compatibility. "
                    f"filename={group_filename}."
                ),
            )
        group_data = _parse_theme_export_template_json(
            filename=group_filename,
            content=group_content,
        )
        sections = group_data.get("sections")
        if not isinstance(sections, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme section-group file is missing sections object "
                    f"for ZIP import compatibility. filename={group_filename}."
                ),
            )

        for section_payload in sections.values():
            if not isinstance(section_payload, dict):
                continue
            section_type = section_payload.get("type")
            if not isinstance(section_type, str) or not section_type.strip():
                continue
            alias_type = _LOCAL_SHOPIFY_THEME_SECTION_GROUP_IMPORT_COMPAT_TYPE_ALIASES.get(
                section_type.strip()
            )
            if alias_type:
                section_payload["type"] = alias_type

        group_entry["content"] = json.dumps(
            group_data,
            indent=2,
            sort_keys=True,
        )
        group_entry.pop("contentBase64", None)


def _resolve_local_theme_workspace_css_filename(*, layout_content: str) -> str:
    match = _LOCAL_SHOPIFY_THEME_LAYOUT_WORKSPACE_CSS_RE.search(layout_content)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline layout/theme.liquid does not include a "
                "workspace-brand CSS asset reference."
            ),
        )
    asset_filename = match.group("asset").strip().lstrip("/")
    if not asset_filename:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline layout/theme.liquid contains an invalid "
                "workspace-brand CSS asset reference."
            ),
        )
    if "/" in asset_filename:
        return asset_filename
    return f"assets/{asset_filename}"


def _merge_local_theme_export_css(
    *,
    existing_content: str,
    css_vars: dict[str, str],
    font_urls: list[str],
) -> str:
    merged_content = existing_content

    existing_import_urls = {
        match.group("url").strip()
        for match in _LOCAL_SHOPIFY_THEME_CSS_IMPORT_URL_RE.finditer(existing_content)
        if isinstance(match.group("url"), str) and match.group("url").strip()
    }
    missing_font_urls = [
        font_url for font_url in font_urls if font_url not in existing_import_urls
    ]
    if missing_font_urls:
        import_block = "".join(
            f'@import url("{font_url}");\n' for font_url in missing_font_urls
        )
        merged_content = f"{import_block}\n{merged_content.lstrip()}"

    missing_css_var_lines: list[str] = []
    for css_var_name, css_var_value in sorted(css_vars.items()):
        var_pattern = re.compile(
            rf"(?m)^(\s*{re.escape(css_var_name)}\s*:\s*)([^;]*)(;)"
        )
        merged_content, replaced_count = var_pattern.subn(
            lambda var_match: (
                f"{var_match.group(1)}"
                f"{css_var_value} !important"
                if "!important" in var_match.group(2).strip().lower()
                else f"{var_match.group(1)}{css_var_value}"
            )
            + var_match.group(3),
            merged_content,
        )
        if replaced_count > 0:
            continue
        missing_css_var_lines.append(f"  {css_var_name}: {css_var_value};")

    if missing_css_var_lines:
        appended_block = "\n".join(
            [
                "",
                "/* Added by mOS local template export variable patch. */",
                ":root {",
                *missing_css_var_lines,
                "}",
                "",
            ]
        )
        merged_content = f"{merged_content.rstrip()}{appended_block}"

    return merged_content if merged_content.endswith("\n") else f"{merged_content}\n"


def _resolve_local_theme_color_reference(
    *,
    raw_value: str,
    css_vars: dict[str, str],
    path: str,
    seen_vars: set[str] | None = None,
) -> str:
    normalized_value = raw_value.strip()
    match = _LOCAL_SHOPIFY_THEME_CSS_VAR_RE.fullmatch(normalized_value)
    if not match:
        return normalized_value

    css_var_name = match.group("name").strip()
    visited = set(seen_vars or ())
    if css_var_name in visited:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Local Shopify theme export detected a circular CSS variable reference while "
                f"resolving {path}: {css_var_name}."
            ),
        )
    next_value = css_vars.get(css_var_name)
    if not isinstance(next_value, str) or not next_value.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Local Shopify theme export requires CSS variable "
                f"{css_var_name} to resolve {path}."
            ),
        )
    visited.add(css_var_name)
    return _resolve_local_theme_color_reference(
        raw_value=next_value,
        css_vars=css_vars,
        path=path,
        seen_vars=visited,
    )


def _parse_local_theme_color_value(
    *,
    raw_value: str,
    css_vars: dict[str, str],
    path: str,
) -> tuple[int, int, int, float]:
    resolved_value = _resolve_local_theme_color_reference(
        raw_value=raw_value,
        css_vars=css_vars,
        path=path,
    )
    hex_match = _LOCAL_SHOPIFY_THEME_HEX_COLOR_RE.fullmatch(resolved_value)
    if hex_match:
        value = hex_match.group("hex")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 1.0
        if len(value) == 4:
            value = "".join(ch * 2 for ch in value)
            return (
                int(value[0:2], 16),
                int(value[2:4], 16),
                int(value[4:6], 16),
                int(value[6:8], 16) / 255.0,
            )
        if len(value) == 6:
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 1.0
        return (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
            int(value[6:8], 16) / 255.0,
        )

    rgb_match = _LOCAL_SHOPIFY_THEME_RGB_COLOR_RE.fullmatch(resolved_value)
    if rgb_match:
        raw_channels = [part.strip() for part in rgb_match.group("channels").split(",")]
        if len(raw_channels) not in {3, 4}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Local Shopify theme export received an invalid RGB color value for "
                    f"{path}: {resolved_value!r}."
                ),
            )

        def parse_rgb_channel(channel: str) -> int:
            try:
                numeric = float(channel)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Local Shopify theme export received an invalid RGB channel for "
                        f"{path}: {resolved_value!r}."
                    ),
                ) from exc
            if numeric < 0 or numeric > 255:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Local Shopify theme export requires RGB channels between 0 and 255 for "
                        f"{path}: {resolved_value!r}."
                    ),
                )
            return int(round(numeric))

        def parse_alpha_channel(channel: str) -> float:
            normalized = channel.strip()
            if normalized.endswith("%"):
                try:
                    percentage = float(normalized[:-1].strip())
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Local Shopify theme export received an invalid RGBA alpha value for "
                            f"{path}: {resolved_value!r}."
                        ),
                    ) from exc
                if percentage < 0 or percentage > 100:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Local Shopify theme export requires RGBA alpha percentages between 0 "
                            f"and 100 for {path}: {resolved_value!r}."
                        ),
                    )
                return percentage / 100.0
            try:
                alpha = float(normalized)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Local Shopify theme export received an invalid RGBA alpha value for "
                        f"{path}: {resolved_value!r}."
                    ),
                ) from exc
            if alpha < 0 or alpha > 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Local Shopify theme export requires RGBA alpha between 0 and 1 for "
                        f"{path}: {resolved_value!r}."
                    ),
                )
            return alpha

        red = parse_rgb_channel(raw_channels[0])
        green = parse_rgb_channel(raw_channels[1])
        blue = parse_rgb_channel(raw_channels[2])
        alpha = parse_alpha_channel(raw_channels[3]) if len(raw_channels) == 4 else 1.0
        return red, green, blue, alpha

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "Local Shopify theme export requires a supported CSS color for "
            f"{path}, received {resolved_value!r}."
        ),
    )


def _blend_local_theme_color_over_background(
    *,
    fg: tuple[int, int, int, float],
    bg: tuple[int, int, int],
) -> tuple[int, int, int]:
    alpha = max(0.0, min(1.0, float(fg[3])))
    if alpha >= 1.0:
        return fg[0], fg[1], fg[2]
    if alpha <= 0.0:
        return bg
    return (
        int(round((fg[0] * alpha) + (bg[0] * (1.0 - alpha)))),
        int(round((fg[1] * alpha) + (bg[1] * (1.0 - alpha)))),
        int(round((fg[2] * alpha) + (bg[2] * (1.0 - alpha)))),
    )


def _relative_luminance_local_theme_rgb(*, r: int, g: int, b: int) -> float:
    def to_linear(channel: int) -> float:
        normalized = channel / 255.0
        if normalized <= 0.04045:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    return (0.2126 * to_linear(r)) + (0.7152 * to_linear(g)) + (0.0722 * to_linear(b))


def _contrast_ratio_local_theme_rgb(
    *,
    a: tuple[int, int, int],
    b: tuple[int, int, int],
) -> float:
    luminance_a = _relative_luminance_local_theme_rgb(r=a[0], g=a[1], b=a[2])
    luminance_b = _relative_luminance_local_theme_rgb(r=b[0], g=b[1], b=b[2])
    lighter, darker = (
        (luminance_a, luminance_b)
        if luminance_a >= luminance_b
        else (luminance_b, luminance_a)
    )
    return (lighter + 0.05) / (darker + 0.05)


def _coerce_local_theme_overlay_opacity(*, value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Local Shopify theme export requires overlay_opacity to be numeric for "
                f"{path}, received bool."
            ),
        )
    if isinstance(value, (int, float)):
        normalized = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            normalized = float(value.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Local Shopify theme export requires overlay_opacity to be numeric for "
                    f"{path}, received {value!r}."
                ),
            ) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Local Shopify theme export requires overlay_opacity to be numeric for "
                f"{path}, received {value!r}."
            ),
        )
    if normalized < 0 or normalized > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Local Shopify theme export requires overlay_opacity between 0 and 100 for "
                f"{path}, received {normalized}."
            ),
        )
    return normalized / 100.0


def _load_local_theme_current_settings(
    *,
    files_by_filename: dict[str, dict[str, str]],
) -> dict[str, Any]:
    settings_payload = _load_local_theme_json_file_from_export_files(
        files_by_filename=files_by_filename,
        filename=_LOCAL_SHOPIFY_THEME_SETTINGS_FILENAME,
    )
    current_settings = settings_payload.get("current")
    if not isinstance(current_settings, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline settings file is missing a valid current settings "
                "object for collection banner color synchronization."
            ),
        )
    return current_settings


def _resolve_local_theme_color_candidate(
    *,
    css_vars: dict[str, str],
    current_settings: dict[str, Any],
    css_var_keys: tuple[str, ...],
    settings_keys: tuple[str, ...],
    path: str,
) -> str:
    for css_var_key in css_var_keys:
        raw_value = css_vars.get(css_var_key)
        if isinstance(raw_value, str) and raw_value.strip():
            return _resolve_local_theme_color_reference(
                raw_value=raw_value,
                css_vars=css_vars,
                path=path,
            )
    for settings_key in settings_keys:
        raw_value = current_settings.get(settings_key)
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "Local Shopify theme export could not resolve a concrete color value for "
            f"{path}."
        ),
    )


def _apply_local_theme_collection_banner_contrasting_text_color(
    *,
    files_by_filename: dict[str, dict[str, str]],
    css_vars: dict[str, str],
) -> None:
    collection_template = _load_local_theme_json_file_from_export_files(
        files_by_filename=files_by_filename,
        filename="templates/collection.json",
    )
    sections = collection_template.get("sections")
    if not isinstance(sections, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline collection template is missing a valid sections "
                "object for banner color synchronization."
            ),
        )
    banner_section = sections.get("main-collection-banner")
    if not isinstance(banner_section, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline collection template is missing the "
                "main-collection-banner section required for banner color synchronization."
            ),
        )
    banner_settings = banner_section.get("settings")
    if not isinstance(banner_settings, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline collection banner is missing a valid settings "
                "object for banner color synchronization."
            ),
        )

    current_settings = _load_local_theme_current_settings(files_by_filename=files_by_filename)
    settings_path = "templates/collection.json.sections.main-collection-banner.settings"

    base_background_value = _resolve_local_theme_color_candidate(
        css_vars=css_vars,
        current_settings=current_settings,
        css_var_keys=("--hero-bg", "--color-page-bg", "--color-bg"),
        settings_keys=("color_background", "color_image_background"),
        path=f"{settings_path}.background",
    )
    base_background_rgb = _blend_local_theme_color_over_background(
        fg=_parse_local_theme_color_value(
            raw_value=base_background_value,
            css_vars=css_vars,
            path=f"{settings_path}.background",
        ),
        bg=(255, 255, 255),
    )

    resolved_background_rgb = base_background_rgb
    for background_key in (
        "color_background",
        "background_color",
        "item_bg_color",
        "body_bg_color",
        "card_bg_color",
    ):
        raw_value = banner_settings.get(background_key)
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        resolved_background_rgb = _blend_local_theme_color_over_background(
            fg=_parse_local_theme_color_value(
                raw_value=raw_value,
                css_vars=css_vars,
                path=f"{settings_path}.{background_key}",
            ),
            bg=base_background_rgb,
        )
        break

    overlay_value = banner_settings.get("color_overlay")
    contrast_background_rgb = resolved_background_rgb
    if isinstance(overlay_value, str) and overlay_value.strip():
        overlay_rgba = _parse_local_theme_color_value(
            raw_value=overlay_value,
            css_vars=css_vars,
            path=f"{settings_path}.color_overlay",
        )
        overlay_alpha = overlay_rgba[3]
        overlay_opacity = banner_settings.get("overlay_opacity")
        if overlay_opacity is not None and (
            not isinstance(overlay_opacity, str) or overlay_opacity.strip()
        ):
            overlay_alpha = _coerce_local_theme_overlay_opacity(
                value=overlay_opacity,
                path=f"{settings_path}.overlay_opacity",
            )
        resolved_background_rgb = _blend_local_theme_color_over_background(
            fg=(overlay_rgba[0], overlay_rgba[1], overlay_rgba[2], overlay_alpha),
            bg=resolved_background_rgb,
        )
        if banner_settings.get("show_image"):
            # Collection banners frequently render text over photography. When an
            # image is present, evaluating contrast against the overlay over a dark
            # image backdrop better matches what users actually see than using the
            # page background token alone.
            contrast_background_rgb = _blend_local_theme_color_over_background(
                fg=(overlay_rgba[0], overlay_rgba[1], overlay_rgba[2], overlay_alpha),
                bg=(0, 0, 0),
            )
        else:
            contrast_background_rgb = resolved_background_rgb

    dark_value = _resolve_local_theme_color_candidate(
        css_vars=css_vars,
        current_settings=current_settings,
        css_var_keys=("--color-text",),
        settings_keys=("color_foreground",),
        path=f"{settings_path}.color_text",
    )
    light_value = _resolve_local_theme_color_candidate(
        css_vars=css_vars,
        current_settings=current_settings,
        css_var_keys=("--color-bg",),
        settings_keys=("color_image_background", "color_background"),
        path=f"{settings_path}.color_text",
    )

    dark_rgb = _blend_local_theme_color_over_background(
        fg=_parse_local_theme_color_value(
            raw_value=dark_value,
            css_vars=css_vars,
            path=f"{settings_path}.color_text.dark",
        ),
        bg=contrast_background_rgb,
    )
    light_rgb = _blend_local_theme_color_over_background(
        fg=_parse_local_theme_color_value(
            raw_value=light_value,
            css_vars=css_vars,
            path=f"{settings_path}.color_text.light",
        ),
        bg=contrast_background_rgb,
    )

    banner_settings["color_text"] = (
        light_value
        if _contrast_ratio_local_theme_rgb(a=light_rgb, b=contrast_background_rgb)
        > _contrast_ratio_local_theme_rgb(a=dark_rgb, b=contrast_background_rgb)
        else dark_value
    )

    file_entry = files_by_filename["templates/collection.json"]
    file_entry["content"] = json.dumps(
        collection_template,
        indent=2,
        sort_keys=True,
    )
    if not file_entry["content"].endswith("\n"):
        file_entry["content"] = f"{file_entry['content']}\n"
    file_entry.pop("contentBase64", None)


def _apply_local_theme_collection_banner_text_styling(
    *,
    files_by_filename: dict[str, dict[str, str]],
) -> None:
    file_entry = files_by_filename.get(_LOCAL_THEME_COLLECTION_BANNER_SECTION_FILENAME)
    section_content = file_entry.get("content") if isinstance(file_entry, dict) else None
    if not isinstance(section_content, str) or not section_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline is missing or has invalid collection banner "
                "section content required for text color synchronization."
            ),
        )

    updated_content = section_content
    if _LOCAL_THEME_COLLECTION_BANNER_SECTION_VARIABLES_REPLACEMENT not in updated_content:
        if _LOCAL_THEME_COLLECTION_BANNER_SECTION_VARIABLES_SNIPPET not in updated_content:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline collection banner does not expose the "
                    "expected section color variable binding required for text color "
                    "synchronization."
                ),
            )
        updated_content = updated_content.replace(
            _LOCAL_THEME_COLLECTION_BANNER_SECTION_VARIABLES_SNIPPET,
            _LOCAL_THEME_COLLECTION_BANNER_SECTION_VARIABLES_REPLACEMENT,
            1,
        )

    if _LOCAL_THEME_COLLECTION_BANNER_BOX_CLASS_REPLACEMENT not in updated_content:
        if _LOCAL_THEME_COLLECTION_BANNER_BOX_CLASS_SNIPPET not in updated_content:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline collection banner does not expose the "
                    "expected banner content wrapper required for text color "
                    "synchronization."
                ),
            )
        updated_content = updated_content.replace(
            _LOCAL_THEME_COLLECTION_BANNER_BOX_CLASS_SNIPPET,
            _LOCAL_THEME_COLLECTION_BANNER_BOX_CLASS_REPLACEMENT,
            1,
        )

    if _LOCAL_THEME_COLLECTION_BANNER_TEXT_COLOR_STYLE_SNIPPET not in updated_content:
        if "</style>" not in updated_content:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline collection banner is missing the style "
                    "block required for text color synchronization."
                ),
            )
        updated_content = updated_content.replace(
            "</style>",
            f"{_LOCAL_THEME_COLLECTION_BANNER_TEXT_COLOR_STYLE_SNIPPET}</style>",
            1,
        )

    file_entry["content"] = updated_content
    file_entry.pop("contentBase64", None)


def _require_local_theme_secondary_background_css_var(
    *,
    css_vars: dict[str, str],
) -> None:
    value = css_vars.get(_THEME_SECONDARY_SECTION_BACKGROUND_CSS_VAR)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Template ZIP export requires design system token "
                f"cssVars[{_THEME_SECONDARY_SECTION_BACKGROUND_CSS_VAR}] to style "
                "SS - Before / After #4 and SS - Countdown Timer #4 section backgrounds."
            ),
        )


def _apply_local_theme_secondary_background_color_to_sections(
    *,
    files_by_filename: dict[str, dict[str, str]],
) -> None:
    replacement_color = f"background-color: var({_THEME_SECONDARY_SECTION_BACKGROUND_CSS_VAR});"
    replacement_image = "background-image: none;"
    for filename in _THEME_SECONDARY_SECTION_BACKGROUND_FILENAMES:
        file_entry = files_by_filename.get(filename)
        section_content = file_entry.get("content") if isinstance(file_entry, dict) else None
        if not isinstance(section_content, str) or not section_content.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline is missing or has invalid section content "
                    f"required for secondary background token wiring. filename={filename}."
                ),
            )

        updated_content, replaced_background_count = (
            _THEME_SECONDARY_SECTION_BACKGROUND_COLOR_RE.subn(
                replacement_color,
                section_content,
            )
        )
        if replaced_background_count < 1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline section does not expose a supported "
                    f"background_color binding for secondary token wiring. filename={filename}."
                ),
            )
        updated_content, replaced_background_image_count = (
            _THEME_SECONDARY_SECTION_BACKGROUND_IMAGE_RE.subn(
                replacement_image,
                updated_content,
            )
        )
        if replaced_background_image_count < 1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Local Shopify theme baseline section does not expose a supported "
                    f"background_gradient binding for secondary token wiring. filename={filename}."
                ),
            )

        if filename == "sections/ss-countdown-timer-4.liquid":
            updated_content, replaced_fill_count = _THEME_SECONDARY_COUNTDOWN_SHAPE_FILL_RE.subn(
                f'fill="var({_THEME_SECONDARY_SECTION_BACKGROUND_CSS_VAR})"',
                updated_content,
            )
            if replaced_fill_count < 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Local Shopify theme baseline countdown section does not expose a "
                        "supported shape fill binding for secondary token wiring."
                    ),
                )

        file_entry["content"] = updated_content
        file_entry.pop("contentBase64", None)


def _apply_local_theme_export_default_navigation_size(
    *,
    settings_file_entry: dict[str, str],
) -> None:
    settings_content = settings_file_entry.get("content")
    if not isinstance(settings_content, str) or not settings_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline settings_data.json is empty or not UTF-8 "
                "text content."
            ),
        )
    try:
        settings_payload = json.loads(settings_content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline config/settings_data.json is not valid JSON."
            ),
        ) from exc
    if not isinstance(settings_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline config/settings_data.json has an invalid "
                "JSON root."
            ),
        )
    current_settings = settings_payload.get("current")
    if not isinstance(current_settings, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline config/settings_data.json is missing a "
                "valid current settings object."
            ),
        )

    current_settings["type_navigation_size"] = (
        _LOCAL_SHOPIFY_THEME_DEFAULT_NAVIGATION_SIZE_PX
    )
    settings_file_entry["content"] = json.dumps(
        settings_payload,
        indent=2,
        sort_keys=True,
    )
    settings_file_entry.pop("contentBase64", None)


def _escape_local_theme_css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _resolve_local_theme_footer_logo_setting_paths(
    *,
    files_by_filename: dict[str, dict[str, str]],
) -> list[str]:
    footer_group_data = _load_local_theme_json_file_from_export_files(
        files_by_filename=files_by_filename,
        filename=_LOCAL_SHOPIFY_THEME_FOOTER_GROUP_FILENAME,
    )
    sections = footer_group_data.get("sections")
    if not isinstance(sections, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline footer-group file is missing a valid sections "
                "object for brand logo synchronization."
            ),
        )

    footer_logo_setting_paths: list[str] = []
    for section_key, section_payload in sections.items():
        if not isinstance(section_key, str) or not section_key.strip():
            continue
        if not isinstance(section_payload, dict):
            continue
        settings_payload = section_payload.get("settings")
        if not isinstance(settings_payload, dict) or "logo" not in settings_payload:
            continue
        footer_logo_setting_paths.append(
            f"{_LOCAL_SHOPIFY_THEME_FOOTER_GROUP_FILENAME}.sections.{section_key.strip()}.settings.logo"
        )

    if not footer_logo_setting_paths:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline footer-group file does not expose a footer logo "
                "setting path for brand logo synchronization."
            ),
        )
    return sorted(footer_logo_setting_paths)


def _apply_local_theme_brand_logo_references(
    *,
    files_by_filename: dict[str, dict[str, str]],
    layout_filename: str,
    css_filename: str,
    logo_url: str,
) -> None:
    logo_setting_paths = {
        f"{_LOCAL_SHOPIFY_THEME_SETTINGS_FILENAME}.current.logo": logo_url,
        f"{_LOCAL_SHOPIFY_THEME_SETTINGS_FILENAME}.current.logo_mobile": logo_url,
    }
    for footer_logo_setting_path in _resolve_local_theme_footer_logo_setting_paths(
        files_by_filename=files_by_filename
    ):
        logo_setting_paths[footer_logo_setting_path] = logo_url
    _apply_theme_template_setting_values_to_local_files(
        files_by_filename=files_by_filename,
        values_by_setting_path=logo_setting_paths,
    )

    css_file_entry = files_by_filename.get(css_filename)
    css_content = css_file_entry.get("content") if isinstance(css_file_entry, dict) else None
    if not isinstance(css_content, str) or not css_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline workspace-brand CSS asset is missing or invalid "
                "for brand logo synchronization."
            ),
        )
    escaped_logo_url = _escape_local_theme_css_string(logo_url)
    updated_css_content, replaced_css_logo_count = _LOCAL_SHOPIFY_THEME_BRAND_LOGO_CSS_VAR_RE.subn(
        lambda match: f'{match.group(1)}{escaped_logo_url}{match.group(3)}',
        css_content,
    )
    if replaced_css_logo_count < 1:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline workspace-brand CSS asset does not expose "
                "--mos-brand-logo-url for brand logo synchronization."
            ),
        )
    css_file_entry["content"] = updated_css_content
    css_file_entry.pop("contentBase64", None)

    layout_file_entry = files_by_filename.get(layout_filename)
    layout_content = (
        layout_file_entry.get("content") if isinstance(layout_file_entry, dict) else None
    )
    if not isinstance(layout_content, str) or not layout_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline layout file is missing or invalid for brand "
                "logo synchronization."
            ),
        )
    updated_layout_content, replaced_layout_logo_count = _LOCAL_SHOPIFY_THEME_BRAND_LOGO_META_RE.subn(
        lambda match: f'{match.group(1)}{escape(logo_url, quote=True)}{match.group(3)}',
        layout_content,
    )
    if replaced_layout_logo_count < 1:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline layout file does not expose the "
                "mos-brand-logo-url meta tag for brand logo synchronization."
            ),
        )
    layout_file_entry["content"] = updated_layout_content
    layout_file_entry.pop("contentBase64", None)


def _apply_local_theme_rich_text_footer_color_styling(
    *,
    files_by_filename: dict[str, dict[str, str]],
) -> None:
    settings_file_entry = files_by_filename.get(_LOCAL_SHOPIFY_THEME_SETTINGS_FILENAME)
    settings_content = (
        settings_file_entry.get("content")
        if isinstance(settings_file_entry, dict)
        else None
    )
    if not isinstance(settings_content, str) or not settings_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline settings file is missing or invalid for "
                "rich text color synchronization."
            ),
        )
    try:
        settings_payload = json.loads(settings_content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline settings file is not valid JSON for rich text "
                "color synchronization."
            ),
        ) from exc
    if not isinstance(settings_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline settings JSON root is invalid for rich text "
                "color synchronization."
            ),
        )
    current_settings = settings_payload.get("current")
    if not isinstance(current_settings, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline settings file is missing a valid current settings "
                "object for rich text color synchronization."
            ),
        )
    footer_background = current_settings.get("footer_background")
    if not isinstance(footer_background, str) or not footer_background.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline current.footer_background is missing for rich text "
                "background synchronization."
            ),
        )
    color_bg = current_settings.get("color_image_background")
    if not isinstance(color_bg, str) or not color_bg.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline current.color_image_background is missing for rich "
                "text highlight synchronization."
            ),
        )

    template_file_entry = files_by_filename.get(_LOCAL_SHOPIFY_THEME_INDEX_TEMPLATE_FILENAME)
    template_content = (
        template_file_entry.get("content")
        if isinstance(template_file_entry, dict)
        else None
    )
    if not isinstance(template_content, str) or not template_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline index template is missing or invalid for rich text "
                "style synchronization."
            ),
        )
    template_payload = _parse_theme_export_template_json(
        filename=_LOCAL_SHOPIFY_THEME_INDEX_TEMPLATE_FILENAME,
        content=template_content,
    )
    sections = template_payload.get("sections")
    if not isinstance(sections, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline index template is missing a valid sections object "
                "for rich text style synchronization."
            ),
        )
    rich_text_section = sections.get(_LOCAL_SHOPIFY_THEME_RICH_TEXT_SECTION_ID)
    if not isinstance(rich_text_section, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline index template is missing the expected rich text "
                f"section ({_LOCAL_SHOPIFY_THEME_RICH_TEXT_SECTION_ID})."
            ),
        )
    section_settings = rich_text_section.get("settings")
    if not isinstance(section_settings, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline rich text section is missing a valid settings "
                "object."
            ),
        )
    section_settings["color_background"] = footer_background.strip()
    section_settings["color_highlight"] = color_bg.strip()

    section_blocks = rich_text_section.get("blocks")
    if not isinstance(section_blocks, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline rich text section is missing a valid blocks object."
            ),
        )
    heading_block = section_blocks.get(_LOCAL_SHOPIFY_THEME_RICH_TEXT_HEADING_BLOCK_ID)
    if not isinstance(heading_block, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline rich text section is missing the expected heading "
                f"block ({_LOCAL_SHOPIFY_THEME_RICH_TEXT_HEADING_BLOCK_ID})."
            ),
        )
    heading_settings = heading_block.get("settings")
    if not isinstance(heading_settings, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline rich text heading block is missing a valid "
                "settings object."
            ),
        )
    raw_heading = heading_settings.get("heading")
    if not isinstance(raw_heading, str) or not raw_heading.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline rich text heading value is missing and cannot be "
                "formatted for scribble emphasis."
            ),
        )
    sanitized_heading = _sanitize_theme_component_text_value(raw_heading)
    heading_words = sanitized_heading.split()
    if len(heading_words) < _LOCAL_SHOPIFY_THEME_RICH_TEXT_HEADING_EMPHASIS_WORD_COUNT:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline rich text heading does not include enough words to "
                "italicize the trailing phrase for scribble emphasis."
            ),
        )
    emphasized_words = heading_words[-_LOCAL_SHOPIFY_THEME_RICH_TEXT_HEADING_EMPHASIS_WORD_COUNT :]
    leading_words = heading_words[: -_LOCAL_SHOPIFY_THEME_RICH_TEXT_HEADING_EMPHASIS_WORD_COUNT]
    emphasized_phrase = " ".join(emphasized_words)
    leading_phrase = " ".join(leading_words).strip()
    heading_settings["heading"] = (
        f"{leading_phrase} <em>{emphasized_phrase}</em>"
        if leading_phrase
        else f"<em>{emphasized_phrase}</em>"
    )
    heading_settings["highlighted_text"] = "scribble"

    template_file_entry["content"] = json.dumps(
        template_payload,
        indent=2,
        sort_keys=True,
    )
    if not template_file_entry["content"].endswith("\n"):
        template_file_entry["content"] = f"{template_file_entry['content']}\n"
    template_file_entry.pop("contentBase64", None)


def _build_local_shopify_theme_export_payload(
    *,
    shop_domain: str,
    workspace_name: str,
    brand_name: str,
    logo_url: str,
    css_vars: dict[str, str],
    font_urls: list[str],
    data_theme: str,
    component_image_urls: dict[str, str],
    component_text_values: dict[str, str],
    theme_id: str,
    theme_name: str,
    theme_role: str,
) -> dict[str, Any]:
    ordered_filenames, files_by_filename = _load_local_shopify_theme_baseline_files()
    layout_filename = _LOCAL_SHOPIFY_THEME_LAYOUT_FILENAME
    layout_file_entry = files_by_filename.get(layout_filename)
    if not isinstance(layout_file_entry, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local Shopify theme baseline is missing layout/theme.liquid.",
        )
    layout_content = layout_file_entry.get("content")
    if not isinstance(layout_content, str) or not layout_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline layout/theme.liquid is empty or not UTF-8 "
                "text content."
            ),
        )
    css_filename = _resolve_local_theme_workspace_css_filename(layout_content=layout_content)
    css_file_entry = files_by_filename.get(css_filename)
    if not isinstance(css_file_entry, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline is missing the workspace-brand CSS asset "
                f"referenced by layout/theme.liquid. filename={css_filename}."
            ),
        )
    settings_filename = _LOCAL_SHOPIFY_THEME_SETTINGS_FILENAME
    settings_file_entry = files_by_filename.get(settings_filename)
    if not isinstance(settings_file_entry, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local Shopify theme baseline is missing config/settings_data.json.",
        )

    css_content = css_file_entry.get("content")
    if not isinstance(css_content, str) or not css_content.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Local Shopify theme baseline workspace-brand CSS asset is empty or not "
                f"UTF-8 text content. filename={css_filename}."
            ),
        )
    _require_local_theme_secondary_background_css_var(css_vars=css_vars)
    css_vars_with_defaults = dict(css_vars)
    css_vars_with_defaults["--font-navigation-size"] = (
        f"{_LOCAL_SHOPIFY_THEME_DEFAULT_NAVIGATION_SIZE_PX}px"
    )
    css_file_entry["content"] = _merge_local_theme_export_css(
        existing_content=css_content,
        css_vars=css_vars_with_defaults,
        font_urls=font_urls,
    )
    css_file_entry.pop("contentBase64", None)
    _apply_local_theme_export_default_navigation_size(
        settings_file_entry=settings_file_entry,
    )
    _apply_local_theme_brand_logo_references(
        files_by_filename=files_by_filename,
        layout_filename=layout_filename,
        css_filename=css_filename,
        logo_url=logo_url,
    )

    _apply_theme_template_setting_values_to_local_files(
        files_by_filename=files_by_filename,
        values_by_setting_path=component_image_urls,
    )
    _apply_theme_template_setting_values_to_local_files(
        files_by_filename=files_by_filename,
        values_by_setting_path=component_text_values,
    )
    _apply_local_theme_collection_banner_text_styling(
        files_by_filename=files_by_filename,
    )
    _apply_local_theme_collection_banner_contrasting_text_color(
        files_by_filename=files_by_filename,
        css_vars=css_vars_with_defaults,
    )
    _apply_local_theme_rich_text_footer_color_styling(
        files_by_filename=files_by_filename,
    )
    _apply_local_theme_section_group_import_compatibility(
        ordered_filenames=ordered_filenames,
        files_by_filename=files_by_filename,
    )
    _apply_local_theme_secondary_background_color_to_sections(
        files_by_filename=files_by_filename
    )
    files = [dict(files_by_filename[filename]) for filename in ordered_filenames]
    return {
        "shopDomain": _normalize_local_theme_shop_domain(shop_domain=shop_domain),
        "themeId": theme_id,
        "themeName": theme_name,
        "themeRole": theme_role,
        "layoutFilename": layout_filename,
        "cssFilename": css_filename,
        "settingsFilename": settings_filename,
        "jobId": None,
        "coverage": {
            "requiredSourceVars": sorted(css_vars.keys()),
            "requiredThemeVars": sorted(css_vars.keys()),
            "missingSourceVars": [],
            "missingThemeVars": [],
        },
        "settingsSync": {
            "settingsFilename": settings_filename,
            "expectedPaths": [],
            "updatedPaths": [],
            "missingPaths": [],
            "requiredMissingPaths": [],
            "requiredMismatchedPaths": [],
            "semanticUpdatedPaths": [],
            "semanticMismatchedPaths": [],
            "unmappedColorPaths": [],
            "semanticTypographyUpdatedPaths": [],
            "semanticTypographyMismatchedPaths": [],
            "unmappedTypographyPaths": [],
        },
        "files": files,
    }


def _normalize_theme_export_text_file_content(
    *,
    filename: str,
    content: str,
    sales_page_path: str,
    contact_page_values: dict[str, str] | None = None,
) -> str:
    normalized = content
    normalized = _normalize_theme_export_main_page_button_links(
        filename=filename,
        content=normalized,
        sales_page_path=sales_page_path,
    )
    normalized = _normalize_theme_export_rich_text_section_content(
        filename=filename,
        content=normalized,
    )
    normalized = _normalize_theme_export_catalog_product_card_links(
        filename=filename,
        content=normalized,
        sales_page_path=sales_page_path,
    )
    normalized = _normalize_theme_export_track_order_links(
        filename=filename,
        content=normalized,
    )
    normalized = _normalize_theme_export_shoppable_video_cart_counter_updates(
        filename=filename,
        content=normalized,
    )
    normalized = _normalize_theme_export_footer_tab_link_styling(
        filename=filename,
        content=normalized,
    )
    normalized = _normalize_theme_export_contact_page_template_content(
        filename=filename,
        content=normalized,
        contact_page_values=contact_page_values,
    )
    return normalized


def _theme_export_zip_write_order_key(*, filename: str) -> tuple[int, int, str]:
    normalized_filename = filename.strip().lower()
    root_segment = normalized_filename.split("/", 1)[0]
    root_priority = {
        "assets": 10,
        "snippets": 20,
        "sections": 30,
        "layout": 40,
        "config": 50,
        "locales": 60,
        "templates": 70,
    }.get(root_segment, 90)

    if normalized_filename.endswith(".liquid"):
        extension_priority = 0
    elif normalized_filename.endswith(".json"):
        extension_priority = 2
    else:
        extension_priority = 1

    return root_priority, extension_priority, normalized_filename


def _parse_theme_export_template_json(
    *,
    filename: str,
    content: str,
) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export could not validate collection templates because "
                f"{filename} is missing from exported files."
            ),
        )

    # Shopify template JSON files can include a UTF-8 BOM and a leading
    # autogenerated comment block before the JSON object.
    parse_content = content[1:] if content.startswith("\ufeff") else content
    parse_content = parse_content.lstrip()
    if parse_content.startswith("/*"):
        comment_end = parse_content.find("*/")
        if comment_end < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Theme ZIP export could not validate collection templates because "
                    f"{filename} has an unterminated leading comment block."
                ),
            )
        parse_content = parse_content[comment_end + 2 :].lstrip()

    if not parse_content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export could not validate collection templates because "
                f"{filename} is empty after removing comments."
            ),
        )

    try:
        template_data = json.loads(parse_content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export could not validate collection templates because "
                f"{filename} is not valid JSON."
            ),
        ) from exc
    if not isinstance(template_data, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export could not validate collection templates because "
                f"{filename} does not contain a JSON object."
            ),
        )
    return template_data


def _validate_required_collection_templates_in_export(
    *,
    exported_text_files_by_filename: dict[str, str],
) -> dict[str, Any]:
    parsed_templates: dict[str, dict[str, Any]] = {}
    missing_templates: list[str] = []
    for template_filename in _THEME_EXPORT_REQUIRED_TEMPLATE_FILES:
        template_content = exported_text_files_by_filename.get(template_filename)
        if not isinstance(template_content, str) or not template_content.strip():
            missing_templates.append(template_filename)
            continue
        parsed_templates[template_filename] = _parse_theme_export_template_json(
            filename=template_filename,
            content=template_content,
        )

    if missing_templates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export is missing required collection templates: "
                + ", ".join(sorted(missing_templates))
                + "."
            ),
        )

    collection_template = parsed_templates["templates/collection.json"]
    sections = collection_template.get("sections")
    if not isinstance(sections, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export collection template is invalid because "
                "templates/collection.json.sections is missing or not an object."
            ),
        )
    missing_sections = [
        section_key
        for section_key in _THEME_EXPORT_REQUIRED_COLLECTION_SECTIONS
        if section_key not in sections
    ]
    if missing_sections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export collection template is missing required sections: "
                + ", ".join(missing_sections)
                + "."
            ),
        )

    return {
        "requiredTemplates": list(_THEME_EXPORT_REQUIRED_TEMPLATE_FILES),
        "validatedTemplates": sorted(parsed_templates.keys()),
        "requiredCollectionSections": list(_THEME_EXPORT_REQUIRED_COLLECTION_SECTIONS),
        "validatedCollectionSections": sorted(sections.keys()),
    }


def _validate_required_theme_archive_files_in_export(
    *,
    exported_filenames: set[str],
) -> dict[str, Any]:
    missing_files = sorted(
        filename
        for filename in _THEME_EXPORT_REQUIRED_ARCHIVE_FILES
        if filename not in exported_filenames
    )
    if missing_files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export is missing required archive files: "
                + ", ".join(missing_files)
                + "."
            ),
        )
    return {
        "requiredFiles": list(_THEME_EXPORT_REQUIRED_ARCHIVE_FILES),
        "validatedFiles": sorted(_THEME_EXPORT_REQUIRED_ARCHIVE_FILES),
    }


def _validate_template_file_format_uniqueness_in_export(
    *,
    exported_filenames: set[str],
) -> None:
    template_formats_by_key: dict[str, set[str]] = {}
    for filename in sorted(exported_filenames):
        normalized_filename = filename.strip()
        if not normalized_filename.startswith("templates/"):
            continue
        if normalized_filename.endswith(".json"):
            extension = "json"
        elif normalized_filename.endswith(".liquid"):
            extension = "liquid"
        else:
            continue
        template_key = normalized_filename.rsplit(".", 1)[0].lower()
        template_formats_by_key.setdefault(template_key, set()).add(extension)

    duplicate_template_keys = sorted(
        template_key
        for template_key, formats in template_formats_by_key.items()
        if "json" in formats and "liquid" in formats
    )
    if duplicate_template_keys:
        duplicate_pairs = ", ".join(
            f"{template_key}.json + {template_key}.liquid"
            for template_key in duplicate_template_keys
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export contains template-format collisions. "
                "A template key can be JSON or Liquid, not both. "
                f"collisions={duplicate_pairs}."
            ),
        )


def _split_theme_template_setting_path(*, setting_path: str) -> tuple[str, list[str]]:
    delimiter = ".json."
    delimiter_index = setting_path.find(delimiter)
    if delimiter_index < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Collection template validation requires a setting path that includes "
                f"a template filename and JSON path suffix. path={setting_path}."
            ),
        )
    template_filename = setting_path[: delimiter_index + len(".json")]
    json_path = setting_path[delimiter_index + len(delimiter) :]
    if not template_filename or not json_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Collection template validation received an invalid setting path. "
                f"path={setting_path}."
            ),
        )
    path_tokens = [token.strip() for token in json_path.split(".") if token.strip()]
    if not path_tokens:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Collection template validation received an empty JSON path suffix. "
                f"path={setting_path}."
            ),
        )
    return template_filename, path_tokens


def _resolve_theme_template_json_path_value(
    *,
    template_data: Any,
    setting_path: str,
    path_tokens: list[str],
) -> Any:
    current = template_data
    for token in path_tokens:
        if isinstance(current, dict):
            if token not in current:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Collection template validation could not resolve setting path "
                        f"in exported theme content. missingToken={token}, path={setting_path}."
                    ),
                )
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Collection template validation expected a numeric list index while "
                        f"resolving path={setting_path}; got token={token!r}."
                    ),
                )
            list_index = int(token)
            if list_index < 0 or list_index >= len(current):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Collection template validation encountered an out-of-range list index "
                        f"while resolving path={setting_path}; index={list_index}."
                    ),
                )
            current = current[list_index]
            continue
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Collection template validation encountered a non-container value while "
                f"resolving path={setting_path}."
            ),
        )
    return current


def _validate_collection_template_component_values_in_export(
    *,
    exported_text_files_by_filename: dict[str, str],
    component_image_urls: dict[str, str],
    component_text_values: dict[str, str],
) -> dict[str, Any]:
    collection_image_values = {
        setting_path: value
        for setting_path, value in component_image_urls.items()
        if setting_path.startswith("templates/collection.json.")
    }
    collection_text_values = {
        setting_path: value
        for setting_path, value in component_text_values.items()
        if setting_path.startswith("templates/collection.json.")
    }
    if not collection_image_values and not collection_text_values:
        return {
            "validatedImagePaths": [],
            "validatedTextPaths": [],
        }

    collection_template_content = exported_text_files_by_filename.get("templates/collection.json")
    collection_template_data = _parse_theme_export_template_json(
        filename="templates/collection.json",
        content=collection_template_content if isinstance(collection_template_content, str) else "",
    )

    validated_image_paths: list[str] = []
    validated_text_paths: list[str] = []
    image_mismatch_paths: list[str] = []
    text_mismatch_paths: list[str] = []

    for setting_path, expected_value in sorted(collection_image_values.items()):
        template_filename, path_tokens = _split_theme_template_setting_path(
            setting_path=setting_path
        )
        if template_filename != "templates/collection.json":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Theme ZIP export collection image validation received a mismatched "
                    f"template filename. path={setting_path}."
                ),
            )
        actual_value = _resolve_theme_template_json_path_value(
            template_data=collection_template_data,
            setting_path=setting_path,
            path_tokens=path_tokens,
        )
        if not isinstance(actual_value, str) or not actual_value.strip():
            image_mismatch_paths.append(setting_path)
            continue
        normalized_actual_value = actual_value.strip()
        normalized_expected_value = expected_value.strip()
        if (
            normalized_actual_value == normalized_expected_value
            or normalized_actual_value.startswith("shopify://")
        ):
            validated_image_paths.append(setting_path)
            continue
        image_mismatch_paths.append(setting_path)

    for setting_path, expected_value in sorted(collection_text_values.items()):
        template_filename, path_tokens = _split_theme_template_setting_path(
            setting_path=setting_path
        )
        if template_filename != "templates/collection.json":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Theme ZIP export collection text validation received a mismatched "
                    f"template filename. path={setting_path}."
                ),
            )
        actual_value = _resolve_theme_template_json_path_value(
            template_data=collection_template_data,
            setting_path=setting_path,
            path_tokens=path_tokens,
        )
        if not isinstance(actual_value, str) or not actual_value.strip():
            text_mismatch_paths.append(setting_path)
            continue
        normalized_actual_text = _sanitize_theme_component_text_value(actual_value)
        normalized_expected_text = _sanitize_theme_component_text_value(expected_value)
        if normalized_actual_text == normalized_expected_text:
            validated_text_paths.append(setting_path)
            continue
        text_mismatch_paths.append(setting_path)

    if image_mismatch_paths or text_mismatch_paths:
        mismatch_details: list[str] = []
        if image_mismatch_paths:
            mismatch_details.append(
                "image paths: " + ", ".join(sorted(image_mismatch_paths))
            )
        if text_mismatch_paths:
            mismatch_details.append(
                "text paths: " + ", ".join(sorted(text_mismatch_paths))
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Theme ZIP export validation detected collection component values that were "
                "not applied as expected in templates/collection.json. "
                + "; ".join(mismatch_details)
            ),
        )

    return {
        "validatedImagePaths": validated_image_paths,
        "validatedTextPaths": validated_text_paths,
    }


def _is_gemini_hard_quota_exhaustion_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if "status=429" not in message:
        return False
    return _has_explicit_gemini_hard_quota_signal(message)


def _is_gemini_quota_or_rate_limit_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if _is_gemini_hard_quota_exhaustion_error(exc):
        return True
    return (
        "status=429" in message
        or "too many requests" in message
        or "status=500" in message
        or "status=502" in message
        or "status=503" in message
        or "status=504" in message
        or "service is currently unavailable" in message
        or "temporarily unavailable" in message
    )


def _emit_theme_sync_progress(update: dict[str, Any]) -> None:
    callback = _THEME_SYNC_PROGRESS_CALLBACK.get()
    if not callable(callback):
        return
    try:
        callback(update)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to publish Shopify theme sync progress update")


def _normalize_asset_public_id(raw_public_id: Any) -> str | None:
    if isinstance(raw_public_id, UUID):
        return str(raw_public_id)
    if isinstance(raw_public_id, str):
        cleaned = raw_public_id.strip()
        if cleaned:
            return cleaned
    return None


def _coerce_non_negative_int(raw_value: Any) -> int | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value if raw_value >= 0 else None
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if cleaned and cleaned.isdigit():
            return int(cleaned)
    return None


def _normalize_theme_template_slot_path_filter(raw_slot_paths: Any) -> list[str]:
    if raw_slot_paths is None:
        return []
    if not isinstance(raw_slot_paths, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slotPaths must be an array of non-empty strings when provided.",
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_path in enumerate(raw_slot_paths):
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"slotPaths[{index}] must be a non-empty string.",
            )
        slot_path = raw_path.strip()
        if slot_path in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"slotPaths contains a duplicate path: {slot_path}",
            )
        seen.add(slot_path)
        normalized.append(slot_path)
    return normalized


@router.get("")
def list_clients(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = ClientsRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.create(
        org_id=auth.org_id,
        name=payload.name,
        industry=payload.industry,
        strategy_v2_enabled=payload.strategyV2Enabled,
    )
    return jsonable_encoder(client)


@router.get("/{client_id}")
def get_client(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return jsonable_encoder(client)


def _serialize_active_product(product: Product) -> dict:
    return {
        "id": str(product.id),
        "title": product.title,
        "client_id": str(product.client_id),
        "product_type": product.product_type,
    }


def _get_client_or_404(*, session: Session, org_id: str, client_id: str):
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _require_client_exists(*, session: Session, org_id: str, client_id: str) -> None:
    _get_client_or_404(session=session, org_id=org_id, client_id=client_id)


def _require_public_asset_base_url() -> str:
    base_url = settings.PUBLIC_ASSET_BASE_URL
    if not isinstance(base_url, str) or not base_url.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "PUBLIC_ASSET_BASE_URL is required to sync Shopify theme brand assets. "
                "Set it in mos/backend and restart."
            ),
        )
    return base_url.rstrip("/")


def _get_client_user_pref(
    *, session: Session, org_id: str, client_id: str, user_external_id: str
) -> ClientUserPreference | None:
    return session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == user_external_id,
        )
    )


def _get_selected_shop_domain(
    *, session: Session, org_id: str, client_id: str, user_external_id: str
) -> str | None:
    pref = _get_client_user_pref(
        session=session,
        org_id=org_id,
        client_id=client_id,
        user_external_id=user_external_id,
    )
    if not pref:
        return None
    selected = getattr(pref, "selected_shop_domain", None)
    if not isinstance(selected, str) or not selected.strip():
        return None
    return selected.strip().lower()


def _serialize_http_exception_detail(detail: Any) -> dict[str, Any]:
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, list):
        return {"items": detail}
    if isinstance(detail, str):
        return {"message": detail}
    return {"message": str(detail)}


def _require_internal_install_for_advanced_shopify(
    *, status_payload: dict[str, Any], action_label: str
) -> None:
    # Single-app mode: advanced operations no longer require a secondary internal install.
    return


def _format_non_fatal_generation_error(*, stage: str, exc: BaseException) -> str:
    normalized_stage = stage.strip() or "Generation"
    if isinstance(exc, HTTPException):
        detail_payload = _serialize_http_exception_detail(exc.detail)
        detail_message = detail_payload.get("message")
        if isinstance(detail_message, str) and detail_message.strip():
            return f"{normalized_stage} failed: {detail_message.strip()}"
        detail_items = detail_payload.get("items")
        if isinstance(detail_items, list) and detail_items:
            joined_items = ", ".join(str(item) for item in detail_items)
            return f"{normalized_stage} failed: {joined_items}"
        raw_detail = str(exc.detail).strip()
        if raw_detail:
            return f"{normalized_stage} failed: {raw_detail}"
        return f"{normalized_stage} failed with status {exc.status_code}."
    raw_message = str(exc).strip()
    if raw_message:
        return f"{normalized_stage} failed: {raw_message}"
    return f"{normalized_stage} failed."


def _sanitize_theme_component_text_value(value: str) -> str:
    without_html_tags = _THEME_COMPONENT_HTML_TAG_RE.sub(" ", value)
    without_orphan_closing_tags = _THEME_COMPONENT_ORPHAN_CLOSING_TAG_RE.sub(
        " ", without_html_tags
    )
    sanitized = without_orphan_closing_tags.translate(
        _UNSUPPORTED_THEME_TEXT_VALUE_TRANSLATION
    )
    return " ".join(sanitized.split()).strip()


def _normalize_theme_copy_instruction_list(
    *,
    field_name: str,
    values: list[str] | None,
) -> list[str]:
    if values is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_value in enumerate(values):
        if not isinstance(raw_value, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name}[{index}] must be a string.",
            )
        sanitized_value = _sanitize_theme_component_text_value(raw_value)
        if not sanitized_value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name}[{index}] cannot be empty.",
            )
        if len(sanitized_value) > _THEME_COPY_GUIDELINE_MAX_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"{field_name}[{index}] exceeds max length "
                    f"{_THEME_COPY_GUIDELINE_MAX_LENGTH}."
                ),
            )
        dedupe_key = sanitized_value.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(sanitized_value)
    return normalized


def _normalize_theme_copy_option_value(
    *,
    field_name: str,
    value: str | None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a string when provided.",
        )
    cleaned_value = value.strip()
    if not cleaned_value:
        return None
    if len(cleaned_value) > _THEME_COPY_OPTION_MAX_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} exceeds max length {_THEME_COPY_OPTION_MAX_LENGTH}.",
        )
    return cleaned_value


def _normalize_theme_copy_settings(
    *,
    tone_guidelines: list[str] | None,
    must_avoid_claims: list[str] | None,
    cta_style: str | None,
    reading_level: str | None,
    locale: str | None,
) -> dict[str, Any]:
    return {
        "toneGuidelines": _normalize_theme_copy_instruction_list(
            field_name="toneGuidelines",
            values=tone_guidelines,
        ),
        "mustAvoidClaims": _normalize_theme_copy_instruction_list(
            field_name="mustAvoidClaims",
            values=must_avoid_claims,
        ),
        "ctaStyle": _normalize_theme_copy_option_value(
            field_name="ctaStyle",
            value=cta_style,
        ),
        "readingLevel": _normalize_theme_copy_option_value(
            field_name="readingLevel",
            value=reading_level,
        ),
        "locale": _normalize_theme_copy_option_value(
            field_name="locale",
            value=locale,
        ),
    }


def _build_theme_copy_planner_kwargs(*, copy_settings: dict[str, Any]) -> dict[str, Any]:
    planner_kwargs: dict[str, Any] = {}
    tone_guidelines = copy_settings.get("toneGuidelines")
    if isinstance(tone_guidelines, list) and tone_guidelines:
        planner_kwargs["tone_guidelines"] = tone_guidelines
    must_avoid_claims = copy_settings.get("mustAvoidClaims")
    if isinstance(must_avoid_claims, list) and must_avoid_claims:
        planner_kwargs["must_avoid_claims"] = must_avoid_claims
    cta_style = copy_settings.get("ctaStyle")
    if isinstance(cta_style, str) and cta_style.strip():
        planner_kwargs["cta_style"] = cta_style.strip()
    reading_level = copy_settings.get("readingLevel")
    if isinstance(reading_level, str) and reading_level.strip():
        planner_kwargs["reading_level"] = reading_level.strip()
    locale = copy_settings.get("locale")
    if isinstance(locale, str) and locale.strip():
        planner_kwargs["locale"] = locale.strip()
    return planner_kwargs


def _resolve_theme_copy_settings_from_template_metadata(
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    raw_tone_guidelines = metadata.get("copyToneGuidelines")
    raw_must_avoid_claims = metadata.get("copyMustAvoidClaims")
    raw_cta_style = metadata.get("copyCtaStyle")
    raw_reading_level = metadata.get("copyReadingLevel")
    raw_locale = metadata.get("copyLocale")
    if raw_tone_guidelines is not None and not isinstance(raw_tone_guidelines, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyToneGuidelines must be a list when present."
            ),
        )
    if raw_must_avoid_claims is not None and not isinstance(raw_must_avoid_claims, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyMustAvoidClaims must be a list when present."
            ),
        )
    if raw_cta_style is not None and not isinstance(raw_cta_style, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyCtaStyle must be a string when present."
            ),
        )
    if raw_reading_level is not None and not isinstance(raw_reading_level, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyReadingLevel must be a string when present."
            ),
        )
    if raw_locale is not None and not isinstance(raw_locale, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyLocale must be a string when present."
            ),
        )
    try:
        return _normalize_theme_copy_settings(
            tone_guidelines=raw_tone_guidelines,
            must_avoid_claims=raw_must_avoid_claims,
            cta_style=raw_cta_style,
            reading_level=raw_reading_level,
            locale=raw_locale,
        )
    except HTTPException as exc:
        detail_payload = _serialize_http_exception_detail(exc.detail)
        detail_message = detail_payload.get("message")
        if not isinstance(detail_message, str) or not detail_message.strip():
            detail_message = "Stored copy settings are invalid."
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                f"{detail_message}"
            ),
        ) from exc


def _resolve_workspace_brand_description(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> str | None:
    onboarding_payload = OnboardingPayloadsRepository(session).latest_for_client(
        org_id=org_id,
        client_id=client_id,
    )
    if onboarding_payload is None or not isinstance(onboarding_payload.data, dict):
        return None
    raw_brand_story = onboarding_payload.data.get("brand_story")
    if not isinstance(raw_brand_story, str) or not raw_brand_story.strip():
        return None
    brand_description = _sanitize_theme_component_text_value(raw_brand_story)
    if not brand_description:
        return None
    if len(brand_description) > _THEME_IMAGE_PROMPT_BRAND_DESCRIPTION_MAX_LENGTH:
        brand_description = brand_description[
            :_THEME_IMAGE_PROMPT_BRAND_DESCRIPTION_MAX_LENGTH
        ].rstrip()
    return brand_description


def _resolve_theme_sync_product_reference_image(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
) -> dict[str, Any]:
    product_id = str(product.id).strip()
    if not product_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Product id is required to resolve a Shopify theme image reference.",
        )

    assets_repo = AssetsRepository(session)
    reference_asset: Any | None = None

    primary_asset_id = getattr(product, "primary_asset_id", None)
    if isinstance(primary_asset_id, UUID):
        reference_asset = assets_repo.get(
            org_id=org_id,
            asset_id=str(primary_asset_id),
        )
        if reference_asset is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Product primary asset is missing. Set a valid primary image asset on the product "
                    "before generating Shopify template images with product visual context."
                ),
            )

    if reference_asset is None:
        try:
            product_image_assets = assets_repo.list(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                asset_kind="image",
                statuses=[AssetStatusEnum.approved, AssetStatusEnum.qa_passed],
            )
        except (DataError, StatementError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Product id is invalid for Shopify theme image reference lookup. "
                    f"productId={product_id}."
                ),
            ) from exc
        if not product_image_assets:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Product visual context is required for Shopify template image generation, "
                    "but no approved product images were found. Upload at least one product image "
                    "for this product and retry."
                ),
            )
        reference_asset = product_image_assets[0]

    reference_asset_client_id = str(getattr(reference_asset, "client_id", "")).strip()
    if reference_asset_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product reference asset must belong to this workspace.",
        )

    reference_asset_product_id_raw = getattr(reference_asset, "product_id", None)
    if reference_asset_product_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Product reference asset must be linked to the selected product for Shopify template "
                "image generation."
            ),
        )
    reference_asset_product_id = str(reference_asset_product_id_raw).strip()
    if reference_asset_product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Product reference asset does not belong to the selected product for Shopify template "
                "image generation."
            ),
        )

    storage_key = getattr(reference_asset, "storage_key", None)
    if not isinstance(storage_key, str) or not storage_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Product reference asset is missing media storage metadata (storage_key).",
        )

    storage = MediaStorage()
    try:
        reference_image_bytes, downloaded_mime_type = storage.download_bytes(
            key=storage_key.strip()
        )
    except Exception as exc:  # noqa: BLE001
        reference_asset_public_id = _normalize_asset_public_id(
            getattr(reference_asset, "public_id", None)
        ) or "unknown"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to download product reference asset for Shopify template image generation. "
                f"assetPublicId={reference_asset_public_id}. Error: {exc}"
            ),
        ) from exc
    if not reference_image_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Product reference asset has empty media bytes.",
        )

    configured_mime_type = getattr(reference_asset, "content_type", None)
    mime_type_candidates = [configured_mime_type, downloaded_mime_type]
    reference_mime_type: str | None = None
    for candidate in mime_type_candidates:
        if isinstance(candidate, str) and candidate.strip().lower().startswith("image/"):
            reference_mime_type = candidate.strip()
            break
    if not reference_mime_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Product reference asset content type is not an image. "
                f"contentType={configured_mime_type!r}, downloadedContentType={downloaded_mime_type!r}."
            ),
        )

    reference_asset_public_id = _normalize_asset_public_id(
        getattr(reference_asset, "public_id", None)
    )
    if not reference_asset_public_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Product reference asset does not have a valid public id for Shopify template "
                "image generation."
            ),
        )

    reference_asset_id_raw = getattr(reference_asset, "id", None)
    if not isinstance(reference_asset_id_raw, UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Product reference asset does not have a valid internal id for Shopify template "
                "image generation."
            ),
        )

    return {
        "imageBytes": reference_image_bytes,
        "mimeType": reference_mime_type,
        "assetPublicId": reference_asset_public_id,
        "assetId": str(reference_asset_id_raw),
    }


def _resolve_optional_theme_sync_product_reference_image(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
) -> dict[str, Any] | None:
    if not _is_gemini_image_references_enabled():
        return None
    return _resolve_theme_sync_product_reference_image(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product=product,
    )


def _is_theme_feature_image_slot_path(slot_path: str) -> bool:
    return bool(_THEME_FEATURE_IMAGE_SLOT_PATH_RE.fullmatch(slot_path.strip()))


def _is_theme_feature_highlight_text_slot_path(slot_path: str) -> bool:
    return slot_path.strip() in _THEME_FEATURE_HIGHLIGHT_MANAGED_TEXT_SLOT_PATHS


def _split_theme_text_slots_for_copy_generation(
    *,
    text_slots: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ai_text_slots: list[dict[str, Any]] = []
    managed_feature_text_slots: list[dict[str, Any]] = []
    for raw_slot in text_slots:
        if not isinstance(raw_slot, dict):
            continue
        raw_path = raw_slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        normalized_path = raw_path.strip()
        if _is_theme_feature_highlight_text_slot_path(normalized_path):
            managed_feature_text_slots.append(raw_slot)
            continue
        ai_text_slots.append(raw_slot)
    return ai_text_slots, managed_feature_text_slots


def _sanitize_theme_feature_highlight_value(
    *,
    card_key: str,
    field_name: str,
    value: str | None,
) -> str | None:
    if value is None:
        return None
    sanitized_value = _sanitize_theme_component_text_value(value)
    if not sanitized_value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "featureHighlights value became empty after sanitization. "
                f"path=featureHighlights.{card_key}.{field_name}."
            ),
        )
    return sanitized_value


def _resolve_theme_template_feature_highlights(
    *,
    feature_highlights: ShopifyThemeTemplateFeatureHighlights | None = None,
    existing_feature_highlights: ShopifyThemeTemplateFeatureHighlights | None = None,
    component_text_values: dict[str, str] | None = None,
    text_slots: list[dict[str, Any]] | None = None,
) -> tuple[ShopifyThemeTemplateFeatureHighlights | None, dict[str, str]]:
    text_values_by_path = _collect_theme_sync_text_values_by_path(
        text_slots=text_slots or [],
        component_text_values=component_text_values,
    )
    resolved_cards: dict[str, dict[str, str]] = {}
    resolved_component_text_values: dict[str, str] = {}
    for card_key, (header_path, subtext_path) in _THEME_FEATURE_HIGHLIGHT_CARD_SLOT_PATHS.items():
        resolved_header: str | None = None
        resolved_subtext: str | None = None

        existing_card = (
            getattr(existing_feature_highlights, card_key, None)
            if existing_feature_highlights is not None
            else None
        )
        if existing_card is not None:
            existing_header = _sanitize_theme_feature_highlight_value(
                card_key=card_key,
                field_name="header",
                value=existing_card.header,
            )
            if existing_header:
                resolved_header = existing_header
            existing_subtext = _sanitize_theme_feature_highlight_value(
                card_key=card_key,
                field_name="subtext",
                value=existing_card.subtext,
            )
            if existing_subtext:
                resolved_subtext = existing_subtext

        seeded_header = text_values_by_path.get(header_path)
        if seeded_header:
            resolved_header = seeded_header
        seeded_subtext = text_values_by_path.get(subtext_path)
        if seeded_subtext:
            resolved_subtext = seeded_subtext

        manual_card = (
            getattr(feature_highlights, card_key, None)
            if feature_highlights is not None
            else None
        )
        if manual_card is not None:
            manual_header = _sanitize_theme_feature_highlight_value(
                card_key=card_key,
                field_name="header",
                value=manual_card.header,
            )
            if manual_header:
                resolved_header = manual_header
            manual_subtext = _sanitize_theme_feature_highlight_value(
                card_key=card_key,
                field_name="subtext",
                value=manual_card.subtext,
            )
            if manual_subtext:
                resolved_subtext = manual_subtext

        resolved_card: dict[str, str] = {}
        if resolved_header:
            resolved_card["header"] = resolved_header
            resolved_component_text_values[header_path] = resolved_header
        if resolved_subtext:
            resolved_card["subtext"] = resolved_subtext
            resolved_component_text_values[subtext_path] = resolved_subtext
        if resolved_card:
            resolved_cards[card_key] = resolved_card

    if not resolved_cards:
        return None, resolved_component_text_values
    return ShopifyThemeTemplateFeatureHighlights(**resolved_cards), resolved_component_text_values


def _collect_theme_sync_text_values_by_path(
    *,
    text_slots: list[dict[str, Any]],
    component_text_values: dict[str, str] | None = None,
) -> dict[str, str]:
    text_values_by_path: dict[str, str] = {}
    for raw_slot in text_slots:
        if not isinstance(raw_slot, dict):
            continue
        raw_path = raw_slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        raw_value = raw_slot.get("currentValue")
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized_value = _sanitize_theme_component_text_value(raw_value)
        if not normalized_value:
            continue
        text_values_by_path[raw_path.strip()] = normalized_value

    for raw_path, raw_value in (component_text_values or {}).items():
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized_value = _sanitize_theme_component_text_value(raw_value)
        if not normalized_value:
            continue
        text_values_by_path[raw_path.strip()] = normalized_value
    return text_values_by_path


def _build_theme_sync_slot_text_fragments(
    *,
    slot_path: str,
    text_values_by_path: dict[str, str],
) -> list[str]:
    slot_prefix, separator, _ = slot_path.partition(".settings.")
    if not separator:
        return []

    preferred_keys = ("title", "text", "heading", "subheading", "caption")
    text_fragments: list[str] = []
    for key in preferred_keys:
        candidate_path = f"{slot_prefix}.settings.{key}"
        candidate_value = text_values_by_path.get(candidate_path)
        if not candidate_value:
            continue
        if candidate_value in text_fragments:
            continue
        text_fragments.append(candidate_value)

    if not text_fragments:
        slot_text_prefix = f"{slot_prefix}.settings."
        for candidate_path, candidate_value in text_values_by_path.items():
            if not candidate_path.startswith(slot_text_prefix):
                continue
            if candidate_value in text_fragments:
                continue
            text_fragments.append(candidate_value)
            if len(text_fragments) >= 2:
                break
    return text_fragments


def _build_theme_sync_image_slot_text_hints(
    *,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
    component_text_values: dict[str, str] | None = None,
    feature_slots_only: bool = True,
) -> dict[str, str]:
    if not image_slots or not text_slots:
        return {}

    text_values_by_path = _collect_theme_sync_text_values_by_path(
        text_slots=text_slots,
        component_text_values=component_text_values,
    )
    if not text_values_by_path:
        return {}

    hints_by_image_slot_path: dict[str, str] = {}
    for raw_image_slot in image_slots:
        if not isinstance(raw_image_slot, dict):
            continue
        raw_image_path = raw_image_slot.get("path")
        if not isinstance(raw_image_path, str) or not raw_image_path.strip():
            continue
        normalized_image_path = raw_image_path.strip()
        if feature_slots_only and not _is_theme_feature_image_slot_path(
            normalized_image_path
        ):
            continue
        text_fragments = _build_theme_sync_slot_text_fragments(
            slot_path=normalized_image_path,
            text_values_by_path=text_values_by_path,
        )
        if not text_fragments:
            continue

        combined_hint = " ".join(text_fragments).strip()
        if len(combined_hint) > _THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH:
            combined_hint = combined_hint[:_THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH].rstrip()
        if not combined_hint:
            continue
        hints_by_image_slot_path[normalized_image_path] = combined_hint

    return hints_by_image_slot_path


def _humanize_theme_slot_token(raw_value: str) -> str:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw_value)
    normalized = re.sub(r"[_./-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return "Image Slot"
    words = [word for word in normalized.split(" ") if word]
    return " ".join(word[:1].upper() + word[1:].lower() for word in words)


def _derive_theme_sync_slot_display_name(
    *,
    slot_path: str,
    slot_key: str,
    slot_role: str,
) -> str:
    haystack = f"{slot_role} {slot_key} {slot_path}".lower()
    if "feature" in haystack:
        return "Feature Image"
    if "hero" in haystack and ("icon" in haystack or "badge" in haystack):
        return "Hero Icon"
    if "hero" in haystack:
        return "Hero Image"
    if "gallery" in haystack:
        return "Gallery Image"
    if "review" in haystack or "testimonial" in haystack:
        return "Review Image"
    if slot_role.strip():
        return _humanize_theme_slot_token(slot_role)
    if slot_key.strip():
        return _humanize_theme_slot_token(slot_key)
    path_leaf = slot_path.split(".")[-1] if "." in slot_path else slot_path
    return _humanize_theme_slot_token(path_leaf)


def _build_theme_sync_default_general_prompt_context(
    *,
    draft_data: ShopifyThemeTemplateDraftData,
    product: Product,
    brand_description: str | None = None,
) -> str:
    context_segments: list[str] = []
    workspace_name = _sanitize_theme_component_text_value(draft_data.workspaceName)
    if workspace_name:
        context_segments.append(f"Workspace: {workspace_name}.")
    brand_name = _sanitize_theme_component_text_value(draft_data.brandName)
    if brand_name:
        context_segments.append(f"Brand: {brand_name}.")
    normalized_brand_description = _sanitize_theme_component_text_value(
        str(brand_description or "")
    )
    if normalized_brand_description:
        context_segments.append(
            f"Brand description: {normalized_brand_description}."
        )
    theme_name = _sanitize_theme_component_text_value(draft_data.themeName)
    if theme_name:
        context_segments.append(f"Shopify theme: {theme_name}.")
    theme_role = _sanitize_theme_component_text_value(draft_data.themeRole)
    if theme_role:
        context_segments.append(f"Theme role: {theme_role}.")

    product_title = _sanitize_theme_component_text_value(str(product.title or ""))
    if product_title:
        context_segments.append(f"Product: {product_title}.")
    product_type = _sanitize_theme_component_text_value(str(product.product_type or ""))
    if product_type:
        context_segments.append(f"Product type: {product_type}.")
    product_description = _sanitize_theme_component_text_value(str(product.description or ""))
    if product_description:
        if len(product_description) > 280:
            product_description = product_description[:280].rstrip()
        context_segments.append(f"Product summary: {product_description}.")
    benefit_values = [
        _sanitize_theme_component_text_value(str(item))
        for item in (product.primary_benefits or [])
        if isinstance(item, str) and item.strip()
    ]
    benefit_values = [item for item in benefit_values if item]
    if benefit_values:
        context_segments.append("Primary benefits: " + "; ".join(benefit_values[:4]) + ".")
    color_brand = draft_data.cssVars.get("--color-brand")
    if isinstance(color_brand, str) and color_brand.strip():
        context_segments.append(f"Primary brand color: {color_brand.strip()}.")
    color_cta = draft_data.cssVars.get("--color-cta")
    if isinstance(color_cta, str) and color_cta.strip():
        context_segments.append(f"CTA color: {color_cta.strip()}.")
    color_cta_shell = draft_data.cssVars.get("--color-cta-shell")
    if isinstance(color_cta_shell, str) and color_cta_shell.strip():
        context_segments.append(
            f"Exact CTA shell hex (--color-cta-shell): {color_cta_shell.strip()}."
        )
    color_page_bg = draft_data.cssVars.get("--color-page-bg")
    if isinstance(color_page_bg, str) and color_page_bg.strip():
        context_segments.append(
            f"Exact page background hex (--color-page-bg): {color_page_bg.strip()}."
        )

    combined_context = " ".join(context_segments).strip()
    if not combined_context:
        return ""
    if len(combined_context) <= _THEME_IMAGE_PROMPT_GENERAL_CONTEXT_MAX_LENGTH:
        return combined_context
    return combined_context[:_THEME_IMAGE_PROMPT_GENERAL_CONTEXT_MAX_LENGTH].rstrip()


def _build_theme_sync_default_slot_prompt_context_by_path(
    *,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
    component_text_values: dict[str, str] | None = None,
) -> dict[str, str]:
    text_values_by_path = _collect_theme_sync_text_values_by_path(
        text_slots=text_slots,
        component_text_values=component_text_values,
    )
    context_by_path: dict[str, str] = {}
    for raw_slot in image_slots:
        if not isinstance(raw_slot, dict):
            continue
        raw_path = raw_slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        slot_path = raw_path.strip()
        slot_key_raw = raw_slot.get("key")
        slot_key = (
            slot_key_raw.strip()
            if isinstance(slot_key_raw, str) and slot_key_raw.strip()
            else "image"
        )
        slot_role = _normalize_theme_slot_role(raw_slot.get("role"))
        slot_aspect_ratio = _resolve_theme_slot_aspect_ratio(
            raw_slot.get("recommendedAspect"),
            slot_path=slot_path,
        )
        display_name = _derive_theme_sync_slot_display_name(
            slot_path=slot_path,
            slot_key=slot_key,
            slot_role=slot_role,
        )
        is_feature_icon_slot = _is_theme_feature_image_slot_path(slot_path)
        context_segments = [
            f"Purpose: {display_name}.",
            f"Slot role: {slot_role}.",
            f"Target slot key: {slot_key}.",
            f"Preferred aspect ratio: {slot_aspect_ratio}.",
        ]
        if is_feature_icon_slot:
            context_segments.append("Creative format: icon-style feature illustration.")
        slot_render_hint = _THEME_SYNC_SLOT_IMAGE_RENDER_HINT_BY_PATH.get(slot_path)
        text_fragments = _build_theme_sync_slot_text_fragments(
            slot_path=slot_path,
            text_values_by_path=text_values_by_path,
        )
        if text_fragments:
            related_text = " ".join(text_fragments).strip()
            if len(related_text) > _THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH:
                related_text = related_text[:_THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH].rstrip()
            if related_text:
                if is_feature_icon_slot:
                    context_segments.append(
                        f"Feature message to represent as an icon: {related_text}."
                    )
                else:
                    context_segments.append(f"Related copy context: {related_text}.")
        if is_feature_icon_slot:
            context_segments.append(_THEME_SYNC_AI_FEATURE_ICON_CONSTRAINTS)
        if slot_render_hint:
            context_segments.append(f"Rendering guidance: {slot_render_hint}")
        context_text = " ".join(context_segments).strip()
        if len(context_text) > _THEME_IMAGE_PROMPT_SLOT_CONTEXT_MAX_LENGTH:
            context_text = context_text[:_THEME_IMAGE_PROMPT_SLOT_CONTEXT_MAX_LENGTH].rstrip()
        if context_text:
            context_by_path[slot_path] = context_text
    return context_by_path


def _resolve_theme_sync_slot_generation_metadata(
    slot_path: str,
) -> tuple[str, str | None]:
    normalized_slot_path = slot_path.strip()
    generation_strategy = _THEME_SYNC_SLOT_GENERATION_STRATEGY_BY_PATH.get(
        normalized_slot_path,
        _THEME_SYNC_SLOT_GENERATION_STRATEGY_DEFAULT,
    )
    testimonial_template = _THEME_SYNC_SLOT_TESTIMONIAL_TEMPLATE_BY_PATH.get(
        normalized_slot_path
    )
    return generation_strategy, testimonial_template


def _normalize_theme_slot_role(raw_role: Any) -> str:
    if not isinstance(raw_role, str):
        return "generic"
    normalized = raw_role.strip().lower()
    if normalized in {"hero", "gallery", "supporting", "background", "generic"}:
        return normalized
    return "generic"


def _normalize_theme_slot_recommended_aspect(raw_aspect: Any) -> str:
    if not isinstance(raw_aspect, str):
        return "any"
    normalized = raw_aspect.strip().lower()
    if normalized in {"landscape", "portrait", "square", "any", "16:9", "9:16", "4:3", "3:4", "1:1"}:
        return normalized
    return "any"


def _resolve_theme_slot_aspect_ratio(
    raw_recommended_aspect: Any,
    *,
    slot_path: str | None = None,
) -> str:
    if isinstance(slot_path, str):
        normalized_slot_path = slot_path.strip()
        if normalized_slot_path in _THEME_SYNC_SLOT_ASPECT_RATIO_OVERRIDE_BY_PATH:
            return _THEME_SYNC_SLOT_ASPECT_RATIO_OVERRIDE_BY_PATH[normalized_slot_path]
    normalized = _normalize_theme_slot_recommended_aspect(raw_recommended_aspect)
    return _THEME_SYNC_AI_IMAGE_ASPECT_RATIO_BY_RECOMMENDED_ASPECT[normalized]


def _is_gemini_image_references_enabled() -> bool:
    raw_value = os.getenv("GEMINI_IMAGE_REFERENCES_ENABLED", "")
    return raw_value.strip().lower() in _GEMINI_IMAGE_REFERENCES_ENABLED_TRUE_VALUES


def _build_theme_sync_slot_image_prompt(
    *,
    slot_role: str,
    slot_key: str,
    aspect_ratio: str,
    variant_index: int,
    slot_path: str | None = None,
    slot_text_hint: str | None = None,
    general_prompt_context: str | None = None,
    slot_prompt_context: str | None = None,
) -> str:
    is_feature_icon_slot = (
        isinstance(slot_path, str)
        and slot_path.strip()
        and _is_theme_feature_image_slot_path(slot_path)
    )
    role_guidance = (
        _THEME_SYNC_AI_FEATURE_ICON_ROLE_GUIDANCE
        if is_feature_icon_slot
        else _THEME_SYNC_AI_IMAGE_ROLE_GUIDANCE_BY_NAME.get(
            slot_role,
            _THEME_SYNC_AI_IMAGE_ROLE_GUIDANCE_BY_NAME["generic"],
        )
    )
    size_requirement = _THEME_SYNC_AI_IMAGE_MIN_SIZE_BY_ASPECT_RATIO.get(
        aspect_ratio,
        "1600x1200",
    )
    base_prompt = (
        f"{_THEME_SYNC_AI_IMAGE_PROMPT_BASE} "
        f"{role_guidance} "
        f"Target slot key: {slot_key}. "
        f"Aspect ratio: {aspect_ratio}. "
        f"Required output size: at least {size_requirement}. "
        f"Variation: {variant_index}."
    )
    if is_feature_icon_slot:
        base_prompt = f"{base_prompt} {_THEME_SYNC_AI_FEATURE_ICON_CONSTRAINTS}"
    if isinstance(general_prompt_context, str) and general_prompt_context.strip():
        base_prompt = (
            f"{base_prompt} "
            f"Brand and campaign context: {general_prompt_context.strip()}."
        )
    if isinstance(slot_prompt_context, str) and slot_prompt_context.strip():
        base_prompt = (
            f"{base_prompt} "
            f"Slot-specific objective: {slot_prompt_context.strip()}."
        )
    if not isinstance(slot_text_hint, str) or not slot_text_hint.strip():
        return base_prompt
    return (
        f"{base_prompt} "
        f"Feature context: {slot_text_hint.strip()}. "
        "The image must visually represent this context."
    )


def _select_theme_sync_slots_for_ai_generation(
    *,
    image_slots: list[dict[str, Any]],
    max_images: int | None = None,
) -> list[dict[str, Any]]:
    normalized_slots: list[dict[str, Any]] = []
    for slot in image_slots:
        if not isinstance(slot, dict):
            continue
        raw_path = slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        normalized_slots.append(slot)
    if not normalized_slots:
        return []

    sorted_slots = sorted(normalized_slots, key=lambda item: str(item["path"]))
    if max_images is None:
        max_count = len(sorted_slots)
    elif max_images <= 0:
        return []
    else:
        max_count = min(max_images, len(sorted_slots))
    selected: list[dict[str, Any]] = []
    selected_indices: set[int] = set()
    seen_role_aspect: set[tuple[str, str]] = set()

    for idx, slot in enumerate(sorted_slots):
        role = _normalize_theme_slot_role(slot.get("role"))
        aspect = _normalize_theme_slot_recommended_aspect(slot.get("recommendedAspect"))
        role_aspect = (role, aspect)
        if role_aspect in seen_role_aspect:
            continue
        seen_role_aspect.add(role_aspect)
        selected.append(slot)
        selected_indices.add(idx)
        if len(selected) >= max_count:
            return selected

    for idx, slot in enumerate(sorted_slots):
        if len(selected) >= max_count:
            break
        if idx in selected_indices:
            continue
        selected.append(slot)
    return selected


def _generate_theme_sync_ai_image_assets(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str | None,
    product: Product | None = None,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]] | None = None,
    general_prompt_context: str | None = None,
    slot_prompt_context_by_path: dict[str, str] | None = None,
    max_concurrency: int | None = None,
    stop_on_quota_exhausted: bool = False,
    reference_image_bytes: bytes | None = None,
    reference_image_mime_type: str | None = None,
    reference_asset_public_id: str | None = None,
    reference_asset_id: str | None = None,
) -> tuple[list[Any], list[str], dict[str, Any], list[str], dict[str, str]]:
    selected_slots = _select_theme_sync_slots_for_ai_generation(image_slots=image_slots)
    if not selected_slots:
        return [], [], {}, [], {}
    slot_text_hints = _build_theme_sync_image_slot_text_hints(
        image_slots=selected_slots,
        text_slots=text_slots or [],
    )
    normalized_slot_prompt_context_by_path: dict[str, str] = {}
    for raw_path, raw_context in (slot_prompt_context_by_path or {}).items():
        if (
            not isinstance(raw_path, str)
            or not raw_path.strip()
            or not isinstance(raw_context, str)
            or not raw_context.strip()
        ):
            continue
        normalized_slot_prompt_context_by_path[raw_path.strip()] = raw_context.strip()
    testimonial_review_slot_paths: list[str] = []
    for raw_slot in selected_slots:
        if not isinstance(raw_slot, dict):
            continue
        raw_slot_path = raw_slot.get("path")
        if not isinstance(raw_slot_path, str) or not raw_slot_path.strip():
            continue
        slot_path = raw_slot_path.strip()
        generation_strategy, _ = _resolve_theme_sync_slot_generation_metadata(slot_path)
        if (
            generation_strategy
            == _THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER
        ):
            testimonial_review_slot_paths.append(slot_path)
    testimonial_render_payload_by_slot_path: dict[str, dict[str, Any]] = {}
    if testimonial_review_slot_paths:
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Shopify testimonial image generation requires a product for "
                    "review-card slots."
                ),
            )
        testimonial_render_payload_by_slot_path, _ = (
            generate_shopify_theme_review_card_payloads(
                product=product,
                slot_paths=testimonial_review_slot_paths,
                general_prompt_context=general_prompt_context,
                slot_prompt_context_by_path=normalized_slot_prompt_context_by_path,
            )
        )
    if reference_image_bytes is not None:
        if not reference_image_bytes:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Theme image reference bytes are empty.",
            )
        if not isinstance(reference_image_mime_type, str) or not reference_image_mime_type.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Theme image reference mime type is required when reference bytes are provided.",
            )
        if not _is_gemini_image_references_enabled():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Product reference images are configured for Shopify theme generation, but "
                    "Gemini image references are disabled. Set GEMINI_IMAGE_REFERENCES_ENABLED=true "
                    "and retry."
                ),
            )
    elif reference_image_mime_type is not None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme image reference mime type was provided without reference bytes.",
        )

    def _generate_single_slot_asset(
        *,
        slot_path: str,
        slot_role: str,
        slot_recommended_aspect: str,
        generation_strategy: str,
        aspect_ratio: str,
        prompt: str | None = None,
        render_payload: dict[str, Any] | None = None,
        testimonial_renderer: ThreadedTestimonialRenderer | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as slot_session:
            try:
                if (
                    generation_strategy
                    == _THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER
                ):
                    if not isinstance(render_payload, dict) or not render_payload:
                        raise RuntimeError(
                            "Testimonial render payload is required for routed review slots."
                        )
                    generated_asset = generate_shopify_theme_testimonial_image_asset(
                        session=slot_session,
                        org_id=org_id,
                        client_id=client_id,
                        slot_path=slot_path,
                        payload=render_payload,
                        product_id=product_id,
                        tags=["shopify_theme_sync", "component_image"],
                        renderer=testimonial_renderer,
                    )
                    return {
                        "slotPath": slot_path,
                        "asset": generated_asset,
                        "source": _THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER,
                        "rateLimited": False,
                        "quotaExhausted": False,
                        "error": None,
                        "exception": None,
                    }
                if not isinstance(prompt, str) or not prompt.strip():
                    raise RuntimeError(
                        "AI image prompt is required for non-testimonial Shopify theme slots."
                    )
                generated_asset = create_funnel_image_asset(
                    session=slot_session,
                    org_id=org_id,
                    client_id=client_id,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    usage_context={
                        "kind": "shopify_theme_sync_component_image",
                        "slotPath": slot_path,
                        "slotRole": slot_role,
                        "recommendedAspect": slot_recommended_aspect,
                    },
                    reference_image_bytes=reference_image_bytes,
                    reference_image_mime_type=reference_image_mime_type,
                    reference_asset_public_id=reference_asset_public_id,
                    reference_asset_id=reference_asset_id,
                    product_id=product_id,
                    tags=["shopify_theme_sync", "component_image", "ai_generated"],
                )
                return {
                    "slotPath": slot_path,
                    "asset": generated_asset,
                    "source": "ai",
                    "rateLimited": False,
                    "quotaExhausted": False,
                    "error": None,
                    "exception": None,
                }
            except TestimonialRenderError as exc:
                return {
                    "slotPath": slot_path,
                    "asset": None,
                    "source": None,
                    "rateLimited": False,
                    "quotaExhausted": False,
                    "error": str(exc),
                    "exception": exc,
                }
            except Exception as exc:  # noqa: BLE001
                if _is_gemini_hard_quota_exhaustion_error(exc):
                    return {
                        "slotPath": slot_path,
                        "asset": None,
                        "source": None,
                        "rateLimited": True,
                        "quotaExhausted": True,
                        "error": str(exc),
                        "exception": None,
                    }
                if _is_gemini_quota_or_rate_limit_error(exc):
                    return {
                        "slotPath": slot_path,
                        "asset": None,
                        "source": None,
                        "rateLimited": True,
                        "quotaExhausted": False,
                        "error": str(exc),
                        "exception": None,
                    }
                return {
                    "slotPath": slot_path,
                    "asset": None,
                    "source": None,
                    "rateLimited": False,
                    "quotaExhausted": False,
                    "error": str(exc),
                    "exception": None,
                }

    prepared_slots: list[dict[str, Any]] = []
    generated_assets: list[Any] = []
    rate_limited_slot_paths: list[str] = []
    quota_exhausted_slot_paths: list[str] = []
    slot_error_by_path: dict[str, str] = {}
    generated_asset_by_slot_path: dict[str, Any] = {}
    variant_count_by_role_aspect: dict[tuple[str, str], int] = {}
    for slot in selected_slots:
        slot_path = str(slot["path"]).strip()
        slot_key_raw = slot.get("key")
        slot_key = (
            slot_key_raw.strip()
            if isinstance(slot_key_raw, str) and slot_key_raw.strip()
            else "image"
        )
        slot_role = _normalize_theme_slot_role(slot.get("role"))
        slot_recommended_aspect = _normalize_theme_slot_recommended_aspect(
            slot.get("recommendedAspect")
        )
        aspect_ratio = _resolve_theme_slot_aspect_ratio(
            slot_recommended_aspect,
            slot_path=slot_path,
        )
        generation_strategy, testimonial_template = (
            _resolve_theme_sync_slot_generation_metadata(slot_path)
        )
        role_aspect = (slot_role, slot_recommended_aspect)
        variant_count = variant_count_by_role_aspect.get(role_aspect, 0) + 1
        variant_count_by_role_aspect[role_aspect] = variant_count
        prepared_slot = {
            "slotPath": slot_path,
            "slotKey": slot_key,
            "slotRole": slot_role,
            "recommendedAspect": slot_recommended_aspect,
            "aspectRatio": aspect_ratio,
            "generationStrategy": generation_strategy,
        }
        if (
            generation_strategy
            == _THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER
        ):
            if (
                testimonial_template
                != _THEME_SYNC_SLOT_TESTIMONIAL_TEMPLATE_REVIEW_CARD
            ):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Routed testimonial review slots must declare "
                        "testimonialTemplate=review_card. "
                        f"slotPath={slot_path}."
                    ),
                )
            render_payload = testimonial_render_payload_by_slot_path.get(slot_path)
            if not isinstance(render_payload, dict) or not render_payload:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Shopify testimonial review payload generation did not return a "
                        f"payload for slotPath={slot_path}."
                    ),
                )
            prepared_slot["renderPayload"] = render_payload
            prepared_slots.append(prepared_slot)
            continue
        prompt = _build_theme_sync_slot_image_prompt(
            slot_role=slot_role,
            slot_key=slot_key,
            aspect_ratio=aspect_ratio,
            variant_index=variant_count,
            slot_path=slot_path,
            slot_text_hint=slot_text_hints.get(slot_path),
            general_prompt_context=general_prompt_context,
            slot_prompt_context=normalized_slot_prompt_context_by_path.get(slot_path),
        )
        prepared_slot["prompt"] = prompt
        prepared_slots.append(prepared_slot)

    total_slots = len(prepared_slots)
    _emit_theme_sync_progress(
        {
            "stage": "image_generation",
            "message": "Generating component images for Shopify theme sync.",
            "totalImageSlots": total_slots,
            "completedImageSlots": 0,
            "generatedImageCount": 0,
            "skippedImageCount": 0,
        }
    )

    if not prepared_slots:
        return (
            generated_assets,
            rate_limited_slot_paths,
            generated_asset_by_slot_path,
            quota_exhausted_slot_paths,
            slot_error_by_path,
        )

    resolved_max_concurrency = _THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY
    if max_concurrency is not None:
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Image generation max_concurrency must be a positive integer.",
            )
        resolved_max_concurrency = max_concurrency
    max_workers = min(resolved_max_concurrency, len(prepared_slots))
    outcomes_by_path: dict[str, dict[str, Any]] = {}
    completed_count = 0
    generated_count = 0
    skipped_count = 0
    def _record_outcome(outcome: dict[str, Any]) -> None:
        nonlocal completed_count, generated_count, skipped_count
        slot_path = str(outcome.get("slotPath") or "").strip()
        if slot_path:
            outcomes_by_path[slot_path] = outcome
        completed_count += 1
        if outcome.get("asset") is not None:
            if outcome.get("source") != "unsplash":
                generated_count += 1
        elif outcome.get("rateLimited"):
            skipped_count += 1
        _emit_theme_sync_progress(
            {
                "stage": "image_generation",
                "message": "Generating component images for Shopify theme sync.",
                "totalImageSlots": total_slots,
                "completedImageSlots": completed_count,
                "generatedImageCount": generated_count,
                "skippedImageCount": skipped_count,
            }
        )

    testimonial_renderer_context: (
        ThreadedTestimonialRenderer | nullcontext[None] | None
    ) = None
    testimonial_renderer: ThreadedTestimonialRenderer | None = None
    testimonial_renderer_started = False
    try:
        if testimonial_review_slot_paths:
            testimonial_renderer_context = ThreadedTestimonialRenderer()
            try:
                testimonial_renderer = testimonial_renderer_context.__enter__()
                testimonial_renderer_started = True
            except TestimonialRenderError as exc:
                for slot in prepared_slots:
                    if (
                        slot["generationStrategy"]
                        != _THEME_SYNC_SLOT_GENERATION_STRATEGY_TESTIMONIAL_RENDERER
                    ):
                        continue
                    _record_outcome(
                        {
                            "slotPath": slot["slotPath"],
                            "asset": None,
                            "source": None,
                            "rateLimited": False,
                            "quotaExhausted": False,
                            "error": str(exc),
                            "exception": exc,
                        }
                    )
        else:
            testimonial_renderer_context = nullcontext(None)
            testimonial_renderer = None
            testimonial_renderer_started = True

        slots_pending_generation = [
            slot
            for slot in prepared_slots
            if slot["slotPath"] not in outcomes_by_path
        ]
        if slots_pending_generation:
            max_workers = min(resolved_max_concurrency, len(slots_pending_generation))
            if max_workers == 1:
                hard_quota_exhausted = False
                hard_quota_slot_path: str | None = None
                for slot in slots_pending_generation:
                    slot_path = slot["slotPath"]
                    try:
                        outcome = _generate_single_slot_asset(
                            slot_path=slot_path,
                            slot_role=slot["slotRole"],
                            slot_recommended_aspect=slot["recommendedAspect"],
                            generation_strategy=slot["generationStrategy"],
                            aspect_ratio=slot["aspectRatio"],
                            prompt=slot.get("prompt"),
                            render_payload=slot.get("renderPayload"),
                            testimonial_renderer=testimonial_renderer,
                        )
                    except Exception as exc:  # noqa: BLE001
                        outcome = {
                            "slotPath": slot_path,
                            "asset": None,
                            "source": None,
                            "rateLimited": False,
                            "quotaExhausted": False,
                            "error": str(exc),
                            "exception": None,
                        }
                    _record_outcome(outcome)
                    if stop_on_quota_exhausted and outcome.get("quotaExhausted"):
                        hard_quota_exhausted = True
                        hard_quota_slot_path = slot_path
                        break

                if hard_quota_exhausted and hard_quota_slot_path:
                    for slot in prepared_slots:
                        slot_path = slot["slotPath"]
                        if slot_path in outcomes_by_path:
                            continue
                        _record_outcome(
                            {
                                "slotPath": slot_path,
                                "asset": None,
                                "source": None,
                                "rateLimited": True,
                                "quotaExhausted": False,
                                "error": (
                                    "Skipped because hard Gemini quota exhaustion was detected "
                                    f"at slotPath={hard_quota_slot_path}."
                                ),
                                "exception": None,
                            }
                        )
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures: dict[concurrent.futures.Future[dict[str, Any]], str] = {}
                    for slot in slots_pending_generation:
                        future = pool.submit(
                            _generate_single_slot_asset,
                            slot_path=slot["slotPath"],
                            slot_role=slot["slotRole"],
                            slot_recommended_aspect=slot["recommendedAspect"],
                            generation_strategy=slot["generationStrategy"],
                            aspect_ratio=slot["aspectRatio"],
                            prompt=slot.get("prompt"),
                            render_payload=slot.get("renderPayload"),
                            testimonial_renderer=testimonial_renderer,
                        )
                        futures[future] = slot["slotPath"]
                    for future in concurrent.futures.as_completed(futures):
                        slot_path = futures[future]
                        try:
                            outcome = future.result()
                        except Exception as exc:  # noqa: BLE001
                            outcome = {
                                "slotPath": slot_path,
                                "asset": None,
                                "source": None,
                                "rateLimited": False,
                                "quotaExhausted": False,
                                "error": str(exc),
                                "exception": None,
                            }
                        _record_outcome(outcome)
    finally:
        if testimonial_renderer_context is not None and testimonial_renderer_started:
            testimonial_renderer_context.__exit__(None, None, None)

    for slot in prepared_slots:
        slot_path = slot["slotPath"]
        outcome = outcomes_by_path.get(slot_path) or {}
        generated_asset = outcome.get("asset")
        if generated_asset is None:
            error_message = str(outcome.get("error") or "Unknown image generation error.").strip()
            slot_error_by_path[slot_path] = error_message
            if outcome.get("quotaExhausted"):
                logger.warning(
                    "Theme sync image generation failed for slot due Gemini hard quota exhaustion.",
                    extra={
                        "slotPath": slot_path,
                        "generationError": error_message,
                    },
                )
                rate_limited_slot_paths.append(slot_path)
                quota_exhausted_slot_paths.append(slot_path)
                continue
            if outcome.get("rateLimited"):
                logger.warning(
                    "Theme sync image generation failed for slot due Gemini rate limit.",
                    extra={
                        "slotPath": slot_path,
                        "generationError": error_message,
                    },
                )
                rate_limited_slot_paths.append(slot_path)
                continue
            logger.warning(
                "Theme sync image generation failed for slot; continuing without asset.",
                extra={
                    "slotPath": slot_path,
                    "generationError": error_message,
                },
            )
            continue

        normalized_public_id = _normalize_asset_public_id(
            getattr(generated_asset, "public_id", None)
        )
        if not normalized_public_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "AI theme image generation produced an invalid asset response without public_id. "
                    f"slotPath={slot_path}."
                ),
            )
        width = (
            generated_asset.width
            if isinstance(getattr(generated_asset, "width", None), int)
            else None
        )
        height = (
            generated_asset.height
            if isinstance(getattr(generated_asset, "height", None), int)
            else None
        )
        generated_asset.width = width
        generated_asset.height = height
        generated_assets.append(generated_asset)
        generated_asset_by_slot_path[slot_path] = generated_asset

    return (
        generated_assets,
        rate_limited_slot_paths,
        generated_asset_by_slot_path,
        quota_exhausted_slot_paths,
        slot_error_by_path,
    )


def _normalize_theme_template_component_image_asset_map(
    component_image_asset_map_raw: dict[str, str] | None,
) -> dict[str, str]:
    normalized_component_image_asset_map: dict[str, str] = {}
    for raw_setting_path, raw_asset_public_id in (component_image_asset_map_raw or {}).items():
        if not isinstance(raw_setting_path, str) or not raw_setting_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="componentImageAssetMap keys must be non-empty strings.",
            )
        setting_path = raw_setting_path.strip()
        if setting_path in normalized_component_image_asset_map:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageAssetMap contains duplicate path after normalization: "
                    f"{setting_path}"
                ),
            )
        if not isinstance(raw_asset_public_id, str) or not raw_asset_public_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageAssetMap values must be non-empty asset public ids. "
                    f"Invalid value at path {setting_path}."
                ),
            )
        normalized_component_image_asset_map[setting_path] = raw_asset_public_id.strip()
    return normalized_component_image_asset_map


def _normalize_theme_template_component_image_urls(
    component_image_urls_raw: dict[str, str] | None,
) -> dict[str, str]:
    normalized_component_image_urls: dict[str, str] = {}
    for raw_setting_path, raw_image_url in (component_image_urls_raw or {}).items():
        if not isinstance(raw_setting_path, str) or not raw_setting_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="componentImageUrls keys must be non-empty strings.",
            )
        setting_path = raw_setting_path.strip()
        if setting_path in normalized_component_image_urls:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageUrls contains duplicate path after normalization: "
                    f"{setting_path}"
                ),
            )
        if not isinstance(raw_image_url, str) or not raw_image_url.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageUrls values must be non-empty strings. "
                    f"Invalid value at path {setting_path}."
                ),
            )
        image_url = raw_image_url.strip()
        if not image_url.startswith("shopify://"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageUrls values must be Shopify file URLs (shopify://...). "
                    f"Invalid value at path {setting_path}."
                ),
            )
        normalized_component_image_urls[setting_path] = image_url
    return normalized_component_image_urls


def _normalize_theme_template_component_text_values(
    component_text_values_raw: dict[str, str] | None,
) -> dict[str, str]:
    normalized_component_text_values: dict[str, str] = {}
    for raw_setting_path, raw_text_value in (component_text_values_raw or {}).items():
        if not isinstance(raw_setting_path, str) or not raw_setting_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="componentTextValues keys must be non-empty strings.",
            )
        setting_path = raw_setting_path.strip()
        if setting_path in normalized_component_text_values:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentTextValues contains duplicate path after normalization: "
                    f"{setting_path}"
                ),
            )
        if not isinstance(raw_text_value, str) or not raw_text_value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentTextValues values must be non-empty strings. "
                    f"Invalid value at path {setting_path}."
                ),
            )
        sanitized_value = _sanitize_theme_component_text_value(raw_text_value)
        if not sanitized_value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentTextValues value became empty after sanitization. "
                    f"path={setting_path}."
                ),
            )
        normalized_component_text_values[setting_path] = sanitized_value
    return normalized_component_text_values


def _prepare_shopify_theme_template_build_data(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateBuildRequest,
    auth: AuthContext,
    session: Session,
) -> ShopifyThemeTemplateDraftData:
    _emit_theme_sync_progress(
        {
            "stage": "preparing",
            "message": "Validating Shopify template build request and workspace data.",
        }
    )
    client = _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = _normalize_local_theme_shop_domain(
        shop_domain=payload.shopDomain or selected_shop_domain
    )

    requested_design_system_id = payload.designSystemId.strip() if payload.designSystemId else None
    resolved_design_system_id = requested_design_system_id or (
        str(client.design_system_id) if client.design_system_id else None
    )
    if not resolved_design_system_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No design system selected for Shopify template build. "
                "Set a workspace default design system or provide designSystemId."
            ),
        )

    design_system_repo = DesignSystemsRepository(session)
    design_system = design_system_repo.get(
        org_id=auth.org_id,
        design_system_id=resolved_design_system_id,
    )
    if not design_system:
        if requested_design_system_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace default design system was not found.",
        )

    design_system_client_id = str(design_system.client_id) if design_system.client_id else None
    if design_system_client_id and design_system_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Design system must belong to this workspace.",
        )

    try:
        validated_tokens = validate_design_system_tokens(design_system.tokens)
    except DesignSystemGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    brand_obj = validated_tokens.get("brand")
    if not isinstance(brand_obj, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand must be a JSON object.",
        )
    brand_name_raw = brand_obj.get("name")
    if not isinstance(brand_name_raw, str) or not brand_name_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.name must be a non-empty string.",
        )
    logo_public_id_raw = brand_obj.get("logoAssetPublicId")
    if not isinstance(logo_public_id_raw, str) or not logo_public_id_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.logoAssetPublicId must be a non-empty string.",
        )
    brand_name = brand_name_raw.strip()
    logo_public_id = logo_public_id_raw.strip()

    css_vars_raw = validated_tokens.get("cssVars")
    if not isinstance(css_vars_raw, dict) or not css_vars_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.cssVars must be a non-empty JSON object.",
        )
    css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars_raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.cssVars keys must be non-empty strings.",
            )
        if not isinstance(raw_value, (str, int, float)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Design system cssVars[{raw_key}] must be a string or number.",
            )
        if isinstance(raw_value, str):
            cleaned_value = raw_value.strip()
            if not cleaned_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Design system cssVars[{raw_key}] must not be an empty string.",
                )
        else:
            cleaned_value = str(raw_value)
        css_vars[raw_key.strip()] = cleaned_value

    font_urls_raw = validated_tokens.get("fontUrls")
    if not isinstance(font_urls_raw, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.fontUrls must be a list of non-empty strings.",
        )
    font_urls: list[str] = []
    for item in font_urls_raw:
        if not isinstance(item, str) or not item.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.fontUrls must be a list of non-empty strings.",
            )
        font_urls.append(item.strip())

    data_theme_raw = validated_tokens.get("dataTheme")
    if not isinstance(data_theme_raw, str) or not data_theme_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.dataTheme must be a non-empty string.",
        )
    data_theme = data_theme_raw.strip()

    assets_repo = AssetsRepository(session)
    logo_asset = assets_repo.get_by_public_id(
        org_id=auth.org_id,
        public_id=logo_public_id,
        client_id=client_id,
    )
    if not logo_asset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Design system brand.logoAssetPublicId does not reference an existing logo asset "
                "for this workspace."
            ),
        )

    normalized_component_image_asset_map = _normalize_theme_template_component_image_asset_map(
        payload.componentImageAssetMap
    )
    normalized_manual_component_text_values = _normalize_theme_template_component_text_values(
        payload.componentTextValues
    )
    normalized_non_feature_manual_component_text_values = {
        setting_path: value
        for setting_path, value in normalized_manual_component_text_values.items()
        if not _is_theme_feature_highlight_text_slot_path(setting_path)
    }
    copy_settings = _normalize_theme_copy_settings(
        tone_guidelines=payload.toneGuidelines,
        must_avoid_claims=payload.mustAvoidClaims,
        cta_style=payload.ctaStyle,
        reading_level=payload.readingLevel,
        locale=payload.locale,
    )
    planner_copy_kwargs = _build_theme_copy_planner_kwargs(copy_settings=copy_settings)

    requested_product_id = payload.productId.strip() if payload.productId else None
    resolved_product: Product | None = None
    resolved_product_storage_id: str | None = None
    if requested_product_id:
        product = ProductsRepository(session).get(
            org_id=auth.org_id, product_id=requested_product_id
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found for productId={requested_product_id}.",
            )
        resolved_product = product
        product_client_id = str(product.client_id).strip()
        if product_client_id != client_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product must belong to this workspace.",
            )
        resolved_product_storage_id = str(product.id).strip()

    workspace_name = str(client.name).strip()
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name is required to build Shopify theme template drafts.",
        )
    workspace_brand_description = _resolve_workspace_brand_description(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
    )

    public_asset_base_url = _require_public_asset_base_url()
    logo_url = f"{public_asset_base_url}/public/assets/{logo_public_id}"

    for setting_path, asset_public_id in normalized_component_image_asset_map.items():
        mapped_asset = assets_repo.get_by_public_id(
            org_id=auth.org_id,
            public_id=asset_public_id,
            client_id=client_id,
        )
        if not mapped_asset:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageAssetMap references an asset that does not exist for this workspace. "
                    f"path={setting_path}, assetPublicId={asset_public_id}."
                ),
            )

    _emit_theme_sync_progress(
        {
            "stage": "discover_slots",
            "message": "Discovering theme component slots for template build.",
        }
    )
    discovered_slots = _list_local_theme_template_slots(
        theme_id=payload.themeId,
        theme_name=payload.themeName,
        shop_domain=effective_shop_domain,
    )
    raw_image_slots = discovered_slots.get("imageSlots")
    raw_text_slots = discovered_slots.get("textSlots")
    image_slots = raw_image_slots if isinstance(raw_image_slots, list) else []
    text_slots = raw_text_slots if isinstance(raw_text_slots, list) else []
    planner_text_slots, managed_feature_text_slots = _split_theme_text_slots_for_copy_generation(
        text_slots=text_slots
    )
    resolved_feature_highlights, managed_feature_component_text_values = (
        _resolve_theme_template_feature_highlights(
            feature_highlights=payload.featureHighlights,
            component_text_values=normalized_manual_component_text_values,
            text_slots=text_slots,
        )
    )

    explicit_image_paths = set(normalized_component_image_asset_map.keys())
    planner_image_slots = [
        slot
        for slot in image_slots
        if isinstance(slot, dict)
        and isinstance(slot.get("path"), str)
        and slot["path"] not in explicit_image_paths
    ]
    _emit_theme_sync_progress(
        {
            "stage": "discover_slots",
            "message": "Theme component slot discovery completed.",
            "totalImageSlots": len(planner_image_slots),
            "totalTextSlots": len(planner_text_slots),
        }
    )

    if (
        requested_product_id
        and not planner_image_slots
        and not planner_text_slots
        and not managed_feature_text_slots
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No image or text component slots were discovered for AI product content mapping. "
                f"productId={requested_product_id}."
            ),
        )

    generated_theme_assets: list[Any] = []
    generated_asset_by_slot_path: dict[str, Any] = {}
    rate_limited_slot_paths: list[str] = []
    quota_exhausted_slot_paths: list[str] = []
    slot_error_by_path: dict[str, str] = {}
    product_reference_image: dict[str, Any] | None = None
    if requested_product_id and resolved_product is not None and planner_image_slots:
        product_reference_image = _resolve_optional_theme_sync_product_reference_image(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product=resolved_product,
        )
    if planner_image_slots:
        (
            generated_theme_assets,
            rate_limited_slot_paths,
            generated_asset_by_slot_path,
            quota_exhausted_slot_paths,
            slot_error_by_path,
        ) = _generate_theme_sync_ai_image_assets(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product_id=resolved_product_storage_id,
            product=resolved_product,
            image_slots=planner_image_slots,
            text_slots=text_slots,
            reference_image_bytes=(
                product_reference_image["imageBytes"] if product_reference_image else None
            ),
            reference_image_mime_type=(
                product_reference_image["mimeType"] if product_reference_image else None
            ),
            reference_asset_public_id=(
                product_reference_image["assetPublicId"]
                if product_reference_image
                else None
            ),
            reference_asset_id=(
                product_reference_image["assetId"] if product_reference_image else None
            ),
        )

    component_image_asset_map: dict[str, str] = dict(normalized_component_image_asset_map)
    component_text_values: dict[str, str] = {}
    copy_agent_model: str | None = None

    if requested_product_id and resolved_product is not None:
        product_image_assets = assets_repo.list(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=resolved_product_storage_id,
            asset_kind="image",
            statuses=[AssetStatusEnum.approved, AssetStatusEnum.qa_passed],
        )
        product_image_assets_by_public_id: dict[str, Any] = {}
        for existing_asset in product_image_assets:
            normalized_existing_public_id = _normalize_asset_public_id(
                getattr(existing_asset, "public_id", None)
            )
            if not normalized_existing_public_id:
                continue
            product_image_assets_by_public_id[normalized_existing_public_id] = existing_asset
        for generated_asset in generated_theme_assets:
            normalized_public_id = _normalize_asset_public_id(
                getattr(generated_asset, "public_id", None)
            )
            if not normalized_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme image generation returned an asset without a valid public id. "
                        f"productId={requested_product_id}."
                    ),
                )
            if normalized_public_id in product_image_assets_by_public_id:
                continue
            product_image_assets_by_public_id[normalized_public_id] = generated_asset
            product_image_assets.append(generated_asset)
        if planner_image_slots and not product_image_assets:
            if rate_limited_slot_paths:
                if quota_exhausted_slot_paths:
                    first_quota_slot_path = quota_exhausted_slot_paths[0]
                    first_quota_error = slot_error_by_path.get(first_quota_slot_path)
                    first_quota_error_note = (
                        f" Gemini error: {first_quota_error}"
                        if isinstance(first_quota_error, str) and first_quota_error.strip()
                        else ""
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            "AI theme image generation exhausted Gemini quota for template build, "
                            "and no existing product images were available. "
                            f"productId={requested_product_id}. "
                            + first_quota_error_note
                            + " "
                            "Retry after quota reset or upload product images / provide componentImageAssetMap "
                            "for these slots: "
                            + ", ".join(sorted(quota_exhausted_slot_paths))
                        ),
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "AI theme image generation is rate-limited or out of Gemini quota for template build, "
                        "and no existing product images were available. "
                        f"productId={requested_product_id}. "
                        "Upload product images or provide componentImageAssetMap for these slots: "
                        + ", ".join(sorted(rate_limited_slot_paths))
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No usable product image assets were available for Shopify theme image slot planning. "
                    f"productId={requested_product_id}."
                ),
            )

        offers = ProductOffersRepository(session).list_by_product(
            product_id=str(resolved_product.id)
        )
        _emit_theme_sync_progress(
            {
                "stage": "planning_content",
                "message": "Planning product copy and image-to-slot assignments.",
                "totalImageSlots": len(planner_image_slots),
                "totalTextSlots": len(planner_text_slots),
            }
        )
        try:
            planner_output = plan_shopify_theme_component_content(
                product=resolved_product,
                offers=offers,
                product_image_assets=product_image_assets,
                image_slots=planner_image_slots,
                text_slots=planner_text_slots,
                **planner_copy_kwargs,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "AI theme component planner failed for template build. "
                    f"productId={requested_product_id}. {exc}"
                ),
            ) from exc

        planner_image_map = planner_output.get("componentImageAssetMap") or {}
        if not isinstance(planner_image_map, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI theme component planner returned an invalid componentImageAssetMap payload.",
            )
        for setting_path, asset_public_id in planner_image_map.items():
            if not isinstance(setting_path, str) or not setting_path.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI theme component planner returned an invalid image mapping path.",
                )
            if not isinstance(asset_public_id, str) or not asset_public_id.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an invalid image mapping asset id "
                        f"for path {setting_path}."
                    ),
                )
            normalized_path = setting_path.strip()
            normalized_asset_public_id = asset_public_id.strip()
            if _is_theme_feature_image_slot_path(normalized_path):
                generated_feature_asset = generated_asset_by_slot_path.get(normalized_path)
                if generated_feature_asset is not None:
                    generated_feature_asset_public_id = _normalize_asset_public_id(
                        getattr(generated_feature_asset, "public_id", None)
                    )
                    if (
                        generated_feature_asset_public_id
                        and generated_feature_asset_public_id
                        in product_image_assets_by_public_id
                    ):
                        normalized_asset_public_id = generated_feature_asset_public_id
            if normalized_asset_public_id not in product_image_assets_by_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an image asset id that does not belong to "
                        "the product asset set. "
                        f"path={normalized_path}, assetPublicId={normalized_asset_public_id}."
                    ),
                )
            component_image_asset_map[normalized_path] = normalized_asset_public_id

        planner_text_values = planner_output.get("componentTextValues") or {}
        if not isinstance(planner_text_values, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI theme component planner returned an invalid componentTextValues payload.",
            )
        for setting_path, value in planner_text_values.items():
            if not isinstance(setting_path, str) or not setting_path.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI theme component planner returned an invalid text mapping path.",
                )
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an invalid text value "
                        f"for path {setting_path}."
                    ),
                )
            normalized_path = setting_path.strip()
            if _is_theme_feature_highlight_text_slot_path(normalized_path):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned a managed feature highlight text slot path: "
                        f"{normalized_path}."
                    ),
                )
            sanitized_value = _sanitize_theme_component_text_value(value)
            if not sanitized_value:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned text that became empty after "
                        f"sanitization for path {normalized_path}."
                    ),
                )
            component_text_values[normalized_path] = sanitized_value
        copy_agent_model_raw = planner_output.get("copyAgentModel")
        if isinstance(copy_agent_model_raw, str) and copy_agent_model_raw.strip():
            copy_agent_model = copy_agent_model_raw.strip()
    else:
        if rate_limited_slot_paths:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "AI theme image generation is rate-limited or out of Gemini quota for template build, "
                    "and productId was not provided for fallback product images. "
                    "Provide componentImageAssetMap for these slots: "
                    + ", ".join(sorted(rate_limited_slot_paths))
                ),
            )
        for slot_path, generated_asset in generated_asset_by_slot_path.items():
            normalized_public_id = _normalize_asset_public_id(
                getattr(generated_asset, "public_id", None)
            )
            if not normalized_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme image generation returned an asset without a valid public id. "
                        f"slotPath={slot_path}."
                    ),
                )
            component_image_asset_map[slot_path] = normalized_public_id

    for setting_path, asset_public_id in normalized_component_image_asset_map.items():
        component_image_asset_map[setting_path] = asset_public_id

    component_text_values.update(normalized_non_feature_manual_component_text_values)
    component_text_values.update(managed_feature_component_text_values)

    discovered_theme_id_raw = discovered_slots.get("themeId")
    discovered_theme_name_raw = discovered_slots.get("themeName")
    discovered_theme_role_raw = discovered_slots.get("themeRole")
    if not isinstance(discovered_theme_id_raw, str) or not discovered_theme_id_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme slot discovery did not return a valid themeId.",
        )
    if not isinstance(discovered_theme_name_raw, str) or not discovered_theme_name_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme slot discovery did not return a valid themeName.",
        )
    if not isinstance(discovered_theme_role_raw, str) or not discovered_theme_role_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme slot discovery did not return a valid themeRole.",
        )

    image_slot_payloads: list[ShopifyThemeTemplateImageSlot] = []
    for raw_slot in image_slots:
        if not isinstance(raw_slot, dict):
            continue
        path = raw_slot.get("path")
        key = raw_slot.get("key")
        role = raw_slot.get("role")
        recommended_aspect = raw_slot.get("recommendedAspect")
        current_value = raw_slot.get("currentValue")
        if (
            not isinstance(path, str)
            or not path.strip()
            or not isinstance(key, str)
            or not key.strip()
            or not isinstance(role, str)
            or not role.strip()
            or not isinstance(recommended_aspect, str)
            or not recommended_aspect.strip()
        ):
            continue
        image_slot_payloads.append(
            ShopifyThemeTemplateImageSlot(
                path=path.strip(),
                key=key.strip(),
                role=role.strip(),
                recommendedAspect=recommended_aspect.strip(),
                currentValue=current_value if isinstance(current_value, str) else None,
            )
        )

    text_slot_payloads: list[ShopifyThemeTemplateTextSlot] = []
    for raw_slot in text_slots:
        if not isinstance(raw_slot, dict):
            continue
        path = raw_slot.get("path")
        key = raw_slot.get("key")
        current_value = raw_slot.get("currentValue")
        if (
            not isinstance(path, str)
            or not path.strip()
            or not isinstance(key, str)
            or not key.strip()
        ):
            continue
        text_slot_payloads.append(
            ShopifyThemeTemplateTextSlot(
                path=path.strip(),
                key=key.strip(),
                currentValue=current_value if isinstance(current_value, str) else None,
            )
        )

    metadata = {
        "componentImageUrlCount": 0,
        "componentTextValueCount": len(component_text_values),
        "generatedImageCount": len(generated_theme_assets),
        "rateLimitedSlotPaths": sorted(rate_limited_slot_paths),
    }
    copy_tone_guidelines = copy_settings.get("toneGuidelines")
    if isinstance(copy_tone_guidelines, list) and copy_tone_guidelines:
        metadata["copyToneGuidelines"] = copy_tone_guidelines
    copy_must_avoid_claims = copy_settings.get("mustAvoidClaims")
    if isinstance(copy_must_avoid_claims, list) and copy_must_avoid_claims:
        metadata["copyMustAvoidClaims"] = copy_must_avoid_claims
    copy_cta_style = copy_settings.get("ctaStyle")
    if isinstance(copy_cta_style, str) and copy_cta_style.strip():
        metadata["copyCtaStyle"] = copy_cta_style.strip()
    copy_reading_level = copy_settings.get("readingLevel")
    if isinstance(copy_reading_level, str) and copy_reading_level.strip():
        metadata["copyReadingLevel"] = copy_reading_level.strip()
    copy_locale = copy_settings.get("locale")
    if isinstance(copy_locale, str) and copy_locale.strip():
        metadata["copyLocale"] = copy_locale.strip()
    if isinstance(copy_agent_model, str) and copy_agent_model.strip():
        metadata["copyAgentModel"] = copy_agent_model.strip()
    if workspace_brand_description:
        metadata[_THEME_IMAGE_PROMPT_METADATA_BRAND_DESCRIPTION_KEY] = (
            workspace_brand_description
        )

    return ShopifyThemeTemplateDraftData(
        shopDomain=effective_shop_domain,
        workspaceName=workspace_name,
        designSystemId=str(design_system.id),
        designSystemName=str(design_system.name),
        brandName=brand_name,
        logoAssetPublicId=logo_public_id,
        logoUrl=logo_url,
        themeId=discovered_theme_id_raw.strip(),
        themeName=discovered_theme_name_raw.strip(),
        themeRole=discovered_theme_role_raw.strip(),
        cssVars=css_vars,
        fontUrls=font_urls,
        dataTheme=data_theme,
        productId=requested_product_id,
        componentImageAssetMap=component_image_asset_map,
        componentImageUrls={},
        componentTextValues=component_text_values,
        featureHighlights=resolved_feature_highlights,
        imageSlots=image_slot_payloads,
        textSlots=text_slot_payloads,
        metadata=metadata,
    )


def _serialize_shopify_theme_template_draft_version(
    *,
    version: Any,
) -> ShopifyThemeTemplateDraftVersionResponse:
    payload_raw = version.payload if isinstance(version.payload, dict) else {}
    payload_normalized = dict(payload_raw)
    if "latestLogoUrl" in payload_normalized:
        legacy_latest_logo_url = payload_normalized.pop("latestLogoUrl")
        current_logo_url = payload_normalized.get("logoUrl")
        if (
            (
                not isinstance(current_logo_url, str)
                or not current_logo_url.strip()
            )
            and isinstance(legacy_latest_logo_url, str)
            and legacy_latest_logo_url.strip()
        ):
            payload_normalized["logoUrl"] = legacy_latest_logo_url.strip()
    try:
        data = ShopifyThemeTemplateDraftData(**payload_normalized)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stored Shopify theme template draft version payload is invalid: {exc}",
        ) from exc

    return ShopifyThemeTemplateDraftVersionResponse(
        id=str(version.id),
        draftId=str(version.draft_id),
        versionNumber=int(version.version_number),
        source=str(version.source),
        notes=str(version.notes) if isinstance(version.notes, str) else None,
        createdByUserExternalId=(
            str(version.created_by_user_external_id)
            if isinstance(version.created_by_user_external_id, str)
            else None
        ),
        createdAt=version.created_at,
        data=data,
    )


def _serialize_shopify_theme_template_draft(
    *,
    draft: Any,
    latest_version: Any | None,
) -> ShopifyThemeTemplateDraftResponse:
    latest_version_payload: ShopifyThemeTemplateDraftVersionResponse | None = None
    if latest_version is not None:
        latest_version_payload = _serialize_shopify_theme_template_draft_version(
            version=latest_version
        )

    return ShopifyThemeTemplateDraftResponse(
        id=str(draft.id),
        status=str(draft.status),
        shopDomain=str(draft.shop_domain),
        themeId=str(draft.theme_id),
        themeName=str(draft.theme_name),
        themeRole=str(draft.theme_role),
        designSystemId=(str(draft.design_system_id) if draft.design_system_id else None),
        productId=(str(draft.product_id) if draft.product_id else None),
        createdByUserExternalId=(
            str(draft.created_by_user_external_id)
            if isinstance(draft.created_by_user_external_id, str)
            else None
        ),
        createdAt=draft.created_at,
        updatedAt=draft.updated_at,
        publishedAt=draft.published_at,
        latestVersion=latest_version_payload,
    )


def _resolve_component_image_urls_from_asset_map(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    component_image_asset_map: dict[str, str],
) -> dict[str, str]:
    if not component_image_asset_map:
        return {}
    public_asset_base_url = _require_public_asset_base_url()
    assets_repo = AssetsRepository(session)
    component_image_urls: dict[str, str] = {}
    for setting_path, asset_public_id in component_image_asset_map.items():
        mapped_asset = assets_repo.get_by_public_id(
            org_id=org_id,
            public_id=asset_public_id,
            client_id=client_id,
        )
        if not mapped_asset:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Stored theme template draft references an asset that does not exist for this workspace. "
                    f"path={setting_path}, assetPublicId={asset_public_id}."
                ),
            )
        component_image_urls[setting_path] = (
            f"{public_asset_base_url}/public/assets/{asset_public_id}"
        )
    return component_image_urls


def _resolve_template_export_component_image_urls_to_shopify_files(
    *,
    client_id: str,
    shop_domain: str,
    component_image_urls: dict[str, str],
) -> dict[str, str]:
    if not component_image_urls:
        return {}

    external_image_urls = {
        setting_path: image_url
        for setting_path, image_url in component_image_urls.items()
        if not image_url.strip().startswith("shopify://")
    }
    if not external_image_urls:
        return dict(component_image_urls)

    resolved_payload = resolve_client_shopify_image_urls_to_files(
        client_id=client_id,
        shop_domain=shop_domain,
        image_urls_by_key=external_image_urls,
    )
    raw_resolved_urls = resolved_payload.get("resolvedImageUrls")
    if not isinstance(raw_resolved_urls, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify image URL resolver returned an invalid payload for template ZIP export.",
        )

    resolved_component_image_urls = dict(component_image_urls)
    for setting_path, resolved_url in raw_resolved_urls.items():
        if not isinstance(setting_path, str) or setting_path not in component_image_urls:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify image URL resolver returned an unexpected setting path.",
            )
        if not isinstance(resolved_url, str) or not resolved_url.strip().startswith(
            "shopify://"
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Shopify image URL resolver did not return a Shopify file URL "
                    f"for settingPath={setting_path}."
                ),
            )
        resolved_component_image_urls[setting_path] = resolved_url.strip()
    return resolved_component_image_urls


def _read_asset_cached_shopify_file_url(
    *,
    asset: Any,
    shop_domain: str,
) -> str | None:
    normalized_shop_domain = normalize_shop_domain(shop_domain)
    raw_ai_metadata = getattr(asset, "ai_metadata", None)
    if raw_ai_metadata is None:
        return None
    if not isinstance(raw_ai_metadata, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Asset metadata is malformed for Shopify file URL cache lookup. "
                f"assetPublicId={getattr(asset, 'public_id', '<unknown>')}."
            ),
        )
    raw_cache = raw_ai_metadata.get(_ASSET_SHOPIFY_FILE_URLS_CACHE_KEY)
    if raw_cache is None:
        return None
    if not isinstance(raw_cache, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Asset metadata Shopify file URL cache is malformed. "
                f"assetPublicId={getattr(asset, 'public_id', '<unknown>')}."
            ),
        )
    cached_url = raw_cache.get(normalized_shop_domain)
    if cached_url is None:
        return None
    if not isinstance(cached_url, str) or not cached_url.strip().startswith("shopify://"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Asset metadata Shopify file URL cache contains an invalid entry. "
                f"assetPublicId={getattr(asset, 'public_id', '<unknown>')}."
            ),
        )
    return cached_url.strip()


def _write_asset_cached_shopify_file_url(
    *,
    asset: Any,
    shop_domain: str,
    shopify_file_url: str,
) -> None:
    normalized_shop_domain = normalize_shop_domain(shop_domain)
    normalized_shopify_file_url = shopify_file_url.strip()
    if not normalized_shopify_file_url.startswith("shopify://"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Cannot write a non-Shopify file URL into asset cache. "
                f"assetPublicId={getattr(asset, 'public_id', '<unknown>')}."
            ),
        )

    raw_ai_metadata = getattr(asset, "ai_metadata", None)
    if raw_ai_metadata is None:
        next_ai_metadata: dict[str, Any] = {}
    elif isinstance(raw_ai_metadata, dict):
        next_ai_metadata = dict(raw_ai_metadata)
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Asset metadata is malformed for Shopify file URL cache update. "
                f"assetPublicId={getattr(asset, 'public_id', '<unknown>')}."
            ),
        )

    raw_cache = next_ai_metadata.get(_ASSET_SHOPIFY_FILE_URLS_CACHE_KEY)
    if raw_cache is None:
        cache_by_shop_domain: dict[str, str] = {}
    elif isinstance(raw_cache, dict):
        cache_by_shop_domain = dict(raw_cache)
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Asset metadata Shopify file URL cache is malformed during update. "
                f"assetPublicId={getattr(asset, 'public_id', '<unknown>')}."
            ),
        )

    cache_by_shop_domain[normalized_shop_domain] = normalized_shopify_file_url
    next_ai_metadata[_ASSET_SHOPIFY_FILE_URLS_CACHE_KEY] = cache_by_shop_domain
    asset.ai_metadata = next_ai_metadata


def _resolve_template_export_component_image_urls_from_asset_map_with_cache(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    shop_domain: str,
    component_image_asset_map: dict[str, str],
) -> dict[str, str]:
    if not component_image_asset_map:
        return {}

    public_asset_base_url = _require_public_asset_base_url()
    assets_repo = AssetsRepository(session)
    resolved_component_image_urls: dict[str, str] = {}
    unresolved_component_image_urls: dict[str, str] = {}
    unresolved_assets_by_setting_path: dict[str, Any] = {}

    for setting_path, asset_public_id in component_image_asset_map.items():
        mapped_asset = assets_repo.get_by_public_id(
            org_id=org_id,
            public_id=asset_public_id,
            client_id=client_id,
        )
        if not mapped_asset:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Stored theme template draft references an asset that does not exist for this workspace. "
                    f"path={setting_path}, assetPublicId={asset_public_id}."
                ),
            )

        cached_shopify_file_url = _read_asset_cached_shopify_file_url(
            asset=mapped_asset,
            shop_domain=shop_domain,
        )
        if cached_shopify_file_url is not None:
            resolved_component_image_urls[setting_path] = cached_shopify_file_url
            continue

        unresolved_component_image_urls[setting_path] = (
            f"{public_asset_base_url}/public/assets/{asset_public_id}"
        )
        unresolved_assets_by_setting_path[setting_path] = mapped_asset

    if unresolved_component_image_urls:
        newly_resolved_component_image_urls = (
            _resolve_template_export_component_image_urls_to_shopify_files(
                client_id=client_id,
                shop_domain=shop_domain,
                component_image_urls=unresolved_component_image_urls,
            )
        )
        expected_paths = set(unresolved_component_image_urls.keys())
        actual_paths = set(newly_resolved_component_image_urls.keys())
        if expected_paths != actual_paths:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Shopify image URL resolver returned an unexpected setting path set during "
                    "template ZIP export image cache update. "
                    f"expected={sorted(expected_paths)} got={sorted(actual_paths)}."
                ),
            )

        for setting_path, shopify_file_url in newly_resolved_component_image_urls.items():
            mapped_asset = unresolved_assets_by_setting_path.get(setting_path)
            if mapped_asset is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Template ZIP export image cache update encountered an unknown setting path. "
                        f"path={setting_path}."
                    ),
                )
            _write_asset_cached_shopify_file_url(
                asset=mapped_asset,
                shop_domain=shop_domain,
                shopify_file_url=shopify_file_url,
            )
            session.add(mapped_asset)
            resolved_component_image_urls[setting_path] = shopify_file_url
        session.commit()

    return resolved_component_image_urls


def _resolve_theme_template_logo_url_to_shopify_file_with_cache(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    shop_domain: str,
    logo_public_id: str,
    current_logo_url: str,
) -> str:
    logo_asset = AssetsRepository(session).get_by_public_id(
        org_id=org_id,
        public_id=logo_public_id,
        client_id=client_id,
    )
    if not logo_asset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Stored theme template draft references a brand logo asset that does not exist "
                f"for this workspace. assetPublicId={logo_public_id}."
            ),
        )

    cached_shopify_file_url = _read_asset_cached_shopify_file_url(
        asset=logo_asset,
        shop_domain=shop_domain,
    )
    if cached_shopify_file_url is not None:
        return cached_shopify_file_url

    normalized_current_logo_url = current_logo_url.strip()
    if normalized_current_logo_url.startswith("shopify://"):
        _write_asset_cached_shopify_file_url(
            asset=logo_asset,
            shop_domain=shop_domain,
            shopify_file_url=normalized_current_logo_url,
        )
        session.add(logo_asset)
        session.commit()
        return normalized_current_logo_url

    public_asset_base_url = _require_public_asset_base_url()
    resolved_logo_urls = _resolve_template_export_component_image_urls_to_shopify_files(
        client_id=client_id,
        shop_domain=shop_domain,
        component_image_urls={
            _THEME_TEMPLATE_BRAND_LOGO_UPLOAD_SETTING_PATH: (
                f"{public_asset_base_url}/public/assets/{logo_public_id}"
            )
        },
    )
    resolved_logo_url = resolved_logo_urls.get(_THEME_TEMPLATE_BRAND_LOGO_UPLOAD_SETTING_PATH)
    if not isinstance(resolved_logo_url, str) or not resolved_logo_url.strip().startswith(
        "shopify://"
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Shopify image URL resolver did not return a Shopify file URL for the "
                "workspace brand logo during template image generation."
            ),
        )
    normalized_resolved_logo_url = resolved_logo_url.strip()
    _write_asset_cached_shopify_file_url(
        asset=logo_asset,
        shop_domain=shop_domain,
        shopify_file_url=normalized_resolved_logo_url,
    )
    session.add(logo_asset)
    session.commit()
    return normalized_resolved_logo_url


def _resolve_latest_template_publish_logo(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    design_system_id: str,
) -> tuple[str, str]:
    (
        _brand_name,
        logo_public_id,
        logo_url,
        _css_vars,
        _font_urls,
        _data_theme,
    ) = _resolve_latest_template_publish_design_system_snapshot(
        session=session,
        org_id=org_id,
        client_id=client_id,
        design_system_id=design_system_id,
    )
    return logo_public_id, logo_url


def _resolve_uploaded_template_logo_url_for_export(
    *,
    draft_data: ShopifyThemeTemplateDraftData,
    latest_logo_asset_public_id: str,
    latest_logo_url: str,
) -> str:
    draft_logo_url = (
        draft_data.logoUrl.strip()
        if isinstance(draft_data.logoUrl, str) and draft_data.logoUrl.strip()
        else ""
    )
    if not draft_logo_url.startswith("shopify://"):
        return latest_logo_url

    draft_logo_asset_public_id = (
        draft_data.logoAssetPublicId.strip()
        if isinstance(draft_data.logoAssetPublicId, str)
        and draft_data.logoAssetPublicId.strip()
        else ""
    )
    if draft_logo_asset_public_id != latest_logo_asset_public_id.strip():
        return latest_logo_url

    metadata = draft_data.metadata if isinstance(draft_data.metadata, dict) else {}
    uploaded_shop_domain = metadata.get("logoUploadedShopDomain")
    if not isinstance(uploaded_shop_domain, str) or not uploaded_shop_domain.strip():
        return latest_logo_url

    if uploaded_shop_domain.strip().lower() != draft_data.shopDomain.strip().lower():
        return latest_logo_url
    return draft_logo_url


def _resolve_latest_template_publish_design_system_snapshot(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    design_system_id: str,
) -> tuple[str, str, str, dict[str, str], list[str], str]:
    normalized_design_system_id = design_system_id.strip()
    if not normalized_design_system_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Shopify theme template draft is missing designSystemId. "
                "Rebuild the draft before publishing."
            ),
        )

    design_system = DesignSystemsRepository(session).get(
        org_id=org_id,
        design_system_id=normalized_design_system_id,
    )
    if not design_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Design system referenced by the Shopify template draft was not found. "
                "Rebuild the draft before publishing."
            ),
        )

    design_system_client_id = str(design_system.client_id).strip() if design_system.client_id else ""
    if design_system_client_id and design_system_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Design system referenced by the template draft must belong to this workspace.",
        )

    try:
        validated_tokens = validate_design_system_tokens(design_system.tokens)
    except DesignSystemGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    brand_obj = validated_tokens.get("brand")
    if not isinstance(brand_obj, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand must be a JSON object.",
        )
    brand_name_raw = brand_obj.get("name")
    if not isinstance(brand_name_raw, str) or not brand_name_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.name must be a non-empty string.",
        )
    brand_name = brand_name_raw.strip()
    logo_public_id_raw = brand_obj.get("logoAssetPublicId")
    if not isinstance(logo_public_id_raw, str) or not logo_public_id_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.logoAssetPublicId must be a non-empty string.",
        )
    logo_public_id = logo_public_id_raw.strip()

    css_vars_raw = validated_tokens.get("cssVars")
    if not isinstance(css_vars_raw, dict) or not css_vars_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.cssVars must be a non-empty JSON object.",
        )
    css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars_raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.cssVars keys must be non-empty strings.",
            )
        if not isinstance(raw_value, (str, int, float)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Design system cssVars[{raw_key}] must be a string or number.",
            )
        if isinstance(raw_value, str):
            cleaned_value = raw_value.strip()
            if not cleaned_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Design system cssVars[{raw_key}] must not be an empty string.",
                )
        else:
            cleaned_value = str(raw_value)
        css_vars[raw_key.strip()] = cleaned_value

    font_urls_raw = validated_tokens.get("fontUrls")
    if not isinstance(font_urls_raw, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.fontUrls must be a list of non-empty strings.",
        )
    font_urls: list[str] = []
    for item in font_urls_raw:
        if not isinstance(item, str) or not item.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.fontUrls must be a list of non-empty strings.",
            )
        font_urls.append(item.strip())

    data_theme_raw = validated_tokens.get("dataTheme")
    if not isinstance(data_theme_raw, str) or not data_theme_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.dataTheme must be a non-empty string.",
        )
    data_theme = data_theme_raw.strip()

    logo_asset = AssetsRepository(session).get_by_public_id(
        org_id=org_id,
        public_id=logo_public_id,
        client_id=client_id,
    )
    if not logo_asset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Design system brand.logoAssetPublicId does not reference an existing logo asset "
                "for this workspace."
            ),
        )

    public_asset_base_url = _require_public_asset_base_url()
    logo_url = f"{public_asset_base_url}/public/assets/{logo_public_id}"
    return brand_name, logo_public_id, logo_url, css_vars, font_urls, data_theme


def _run_client_shopify_theme_brand_sync_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify theme sync job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload is missing clientId.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload is missing sync request data.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload is missing auth context.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload has invalid auth context values.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeBrandSyncRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload failed validation.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        publish_progress(
            {
                "stage": "running",
                "message": "Running Shopify theme sync.",
            }
        )
        try:
            sync_response = sync_client_shopify_theme_brand_route(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = f"Shopify theme brand sync failed with status {exc.status_code}."
            publish_progress(
                {
                    "stage": "failed",
                    "message": error_message,
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        if isinstance(sync_response, ShopifyThemeBrandSyncResponse):
            result_payload = sync_response.model_dump(mode="json")
        elif isinstance(sync_response, dict):
            result_payload = sync_response
        else:
            result_payload = jsonable_encoder(sync_response)

        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify theme sync completed successfully.",
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme brand sync job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc) or "Unhandled error while running Shopify theme brand sync job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify theme brand sync job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify theme brand sync job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


def _build_or_update_shopify_theme_template_draft(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateBuildRequest,
    auth: AuthContext,
    session: Session,
) -> ShopifyThemeTemplateBuildResponse:
    build_data = _prepare_shopify_theme_template_build_data(
        client_id=client_id,
        payload=payload,
        auth=auth,
        session=session,
    )
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)

    draft_id = payload.draftId.strip() if payload.draftId else None
    if draft_id:
        draft = drafts_repo.get(org_id=auth.org_id, client_id=client_id, draft_id=draft_id)
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shopify theme template draft not found.",
            )
        if str(draft.theme_id) != build_data.themeId:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Requested draft does not match the discovered Shopify theme. "
                    "Create a new draft or use the matching theme selector."
                ),
            )
        if str(draft.shop_domain).strip().lower() != build_data.shopDomain.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Requested draft belongs to a different Shopify store. "
                    "Build against the same shopDomain or create a new draft."
                ),
            )
        draft.design_system_id = build_data.designSystemId
        draft.product_id = build_data.productId
        draft.theme_name = build_data.themeName
        draft.theme_role = build_data.themeRole
        draft.status = "draft"
    else:
        draft = drafts_repo.create_draft(
            org_id=auth.org_id,
            client_id=client_id,
            design_system_id=build_data.designSystemId,
            product_id=build_data.productId,
            shop_domain=build_data.shopDomain,
            theme_id=build_data.themeId,
            theme_name=build_data.themeName,
            theme_role=build_data.themeRole,
            created_by_user_external_id=auth.user_id,
            status="draft",
        )

    version = drafts_repo.create_version(
        draft=draft,
        payload=build_data.model_dump(mode="json"),
        source="build_job",
        created_by_user_external_id=auth.user_id,
    )
    serialized_version = _serialize_shopify_theme_template_draft_version(version=version)
    serialized_draft = _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=version,
    )
    return ShopifyThemeTemplateBuildResponse(
        draft=serialized_draft,
        version=serialized_version,
    )


def _generate_shopify_theme_template_draft_images(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateGenerateImagesRequest,
    auth: AuthContext,
    session: Session,
    image_generation_max_concurrency: int | None = None,
    generate_text: bool = True,
) -> ShopifyThemeTemplateGenerateImagesResponse:
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(
        org_id=auth.org_id,
        client_id=client_id,
        draft_id=payload.draftId.strip(),
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify theme template draft has no versions to generate images from.",
        )

    latest_data = _serialize_shopify_theme_template_draft_version(
        version=latest_version
    ).data
    image_slots = [
        slot.model_dump(mode="json")
        for slot in latest_data.imageSlots
        if isinstance(slot.path, str) and slot.path.strip()
    ]
    text_slots = [slot.model_dump(mode="json") for slot in latest_data.textSlots]
    ai_text_slots, _ = _split_theme_text_slots_for_copy_generation(text_slots=text_slots)
    if not image_slots and not text_slots:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template draft has no image or text slots available for generation.",
        )
    requested_image_model, requested_image_model_source = resolve_funnel_image_model_config()

    all_slot_paths = sorted(
        {
            str(slot.get("path")).strip()
            for slot in image_slots
            if isinstance(slot.get("path"), str) and str(slot.get("path")).strip()
        }
    )
    requested_slot_paths = _normalize_theme_template_slot_path_filter(payload.slotPaths)
    if requested_slot_paths:
        unknown_requested_slot_paths = sorted(
            {
                slot_path
                for slot_path in requested_slot_paths
                if slot_path not in all_slot_paths
            }
        )
        if unknown_requested_slot_paths:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "slotPaths contains one or more unknown template image slot paths: "
                    + ", ".join(unknown_requested_slot_paths)
                ),
            )
        generation_scope_slot_path_set = set(requested_slot_paths)
        generation_scope_slot_paths = list(requested_slot_paths)
    else:
        generation_scope_slot_path_set = set(all_slot_paths)
        generation_scope_slot_paths = list(all_slot_paths)
    latest_component_image_asset_map = _normalize_theme_template_component_image_asset_map(
        latest_data.componentImageAssetMap
    )
    latest_component_image_urls = _normalize_theme_template_component_image_urls(
        latest_data.componentImageUrls
    )
    next_component_image_asset_map = dict(latest_component_image_asset_map)
    next_component_text_values = dict(latest_data.componentTextValues)
    resolved_feature_highlights, managed_feature_component_text_values = (
        _resolve_theme_template_feature_highlights(
            feature_highlights=payload.featureHighlights,
            existing_feature_highlights=latest_data.featureHighlights,
            component_text_values=next_component_text_values,
            text_slots=text_slots,
        )
    )
    next_component_text_values.update(managed_feature_component_text_values)
    latest_metadata = dict(latest_data.metadata or {})
    resolved_logo_url = (
        latest_data.logoUrl.strip()
        if isinstance(latest_data.logoUrl, str) and latest_data.logoUrl.strip()
        else ""
    )
    if not resolved_logo_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored Shopify theme template draft version is missing logoUrl.",
        )
    logo_public_id = (
        latest_data.logoAssetPublicId.strip()
        if isinstance(latest_data.logoAssetPublicId, str)
        and latest_data.logoAssetPublicId.strip()
        else ""
    )
    if not logo_public_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored Shopify theme template draft version is missing logoAssetPublicId.",
        )
    resolved_logo_url = _resolve_theme_template_logo_url_to_shopify_file_with_cache(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        shop_domain=latest_data.shopDomain,
        logo_public_id=logo_public_id,
        current_logo_url=resolved_logo_url,
    )
    current_logo_uploaded_shop_domain = latest_metadata.get("logoUploadedShopDomain")
    if isinstance(current_logo_uploaded_shop_domain, str) and current_logo_uploaded_shop_domain.strip():
        normalized_current_logo_uploaded_shop_domain = (
            current_logo_uploaded_shop_domain.strip().lower()
        )
    else:
        normalized_current_logo_uploaded_shop_domain = None
    resolved_logo_uploaded_shop_domain = (
        latest_data.shopDomain.strip().lower()
        if resolved_logo_url.startswith("shopify://")
        else None
    )
    logo_url_changed = resolved_logo_url != latest_data.logoUrl.strip()
    logo_upload_state_changed = (
        resolved_logo_uploaded_shop_domain != normalized_current_logo_uploaded_shop_domain
    )
    latest_feature_highlights_payload = (
        latest_data.featureHighlights.model_dump(mode="json", exclude_none=True)
        if latest_data.featureHighlights is not None
        else {}
    )
    next_feature_highlights_payload = (
        resolved_feature_highlights.model_dump(mode="json", exclude_none=True)
        if resolved_feature_highlights is not None
        else {}
    )
    mapped_slot_paths = {
        raw_path.strip()
        for raw_path, raw_asset_public_id in next_component_image_asset_map.items()
        if isinstance(raw_path, str)
        and raw_path.strip()
        and isinstance(raw_asset_public_id, str)
        and raw_asset_public_id.strip()
    }
    image_slots_pending_generation = [
        slot
        for slot in image_slots
        if isinstance(slot.get("path"), str)
        and str(slot.get("path")).strip()
        and str(slot.get("path")).strip() in generation_scope_slot_path_set
        and str(slot.get("path")).strip() not in mapped_slot_paths
    ]
    should_generate_images = bool(image_slots_pending_generation)
    should_generate_text = bool(ai_text_slots) and generate_text
    if not should_generate_images and not should_generate_text:
        normalized_component_image_asset_map = (
            _normalize_theme_template_component_image_asset_map(next_component_image_asset_map)
        )
        normalized_component_text_values = _normalize_theme_template_component_text_values(
            next_component_text_values
        )
        latest_component_image_urls_for_current_map = {
            setting_path: image_url
            for setting_path, image_url in latest_component_image_urls.items()
            if setting_path in normalized_component_image_asset_map
        }
        missing_component_image_url_paths = {
            setting_path
            for setting_path in normalized_component_image_asset_map
            if setting_path not in latest_component_image_urls_for_current_map
        }
        if missing_component_image_url_paths:
            normalized_component_image_urls = (
                _resolve_template_export_component_image_urls_from_asset_map_with_cache(
                    session=session,
                    org_id=auth.org_id,
                    client_id=client_id,
                    shop_domain=latest_data.shopDomain,
                    component_image_asset_map=normalized_component_image_asset_map,
                )
            )
        else:
            normalized_component_image_urls = latest_component_image_urls_for_current_map

        component_image_urls_changed = (
            set(latest_component_image_urls.keys())
            != set(normalized_component_image_asset_map.keys())
            or normalized_component_image_urls != latest_component_image_urls_for_current_map
        )
        component_text_values_changed = (
            normalized_component_text_values
            != _normalize_theme_template_component_text_values(latest_data.componentTextValues)
        )
        feature_highlights_changed = (
            next_feature_highlights_payload != latest_feature_highlights_payload
        )
        if (
            component_image_urls_changed
            or component_text_values_changed
            or feature_highlights_changed
            or logo_url_changed
            or logo_upload_state_changed
        ):
            merged_metadata = dict(latest_metadata)
            merged_metadata.update(
                {
                    "componentImageAssetCount": len(normalized_component_image_asset_map),
                    "componentImageUrlCount": len(normalized_component_image_urls),
                    "componentTextValueCount": len(normalized_component_text_values),
                }
            )
            if resolved_logo_uploaded_shop_domain is not None:
                merged_metadata["logoUploadedShopDomain"] = (
                    resolved_logo_uploaded_shop_domain
                )
            else:
                merged_metadata.pop("logoUploadedShopDomain", None)
            next_data = latest_data.model_copy(
                update={
                    "logoUrl": resolved_logo_url,
                    "componentImageAssetMap": normalized_component_image_asset_map,
                    "componentImageUrls": normalized_component_image_urls,
                    "componentTextValues": normalized_component_text_values,
                    "featureHighlights": resolved_feature_highlights,
                    "metadata": merged_metadata,
                }
            )
            next_version = drafts_repo.create_version(
                draft=draft,
                payload=next_data.model_dump(mode="json"),
                source="agent_image_generation_job",
                created_by_user_external_id=auth.user_id,
            )
            serialized_draft = _serialize_shopify_theme_template_draft(
                draft=draft,
                latest_version=next_version,
            )
            serialized_version = _serialize_shopify_theme_template_draft_version(
                version=next_version
            )
            return ShopifyThemeTemplateGenerateImagesResponse(
                draft=serialized_draft,
                version=serialized_version,
                generatedImageCount=0,
                generatedTextCount=0,
                copyAgentModel=None,
                requestedImageModel=requested_image_model,
                requestedImageModelSource=requested_image_model_source,
                generatedSlotPaths=[],
                imageModels=[],
                imageModelBySlotPath={},
                imageSourceBySlotPath={},
                promptTokenCountBySlotPath={},
                promptTokenCountTotal=0,
                rateLimitedSlotPaths=[],
                remainingSlotPaths=[],
                quotaExhaustedSlotPaths=[],
                slotErrorsByPath={},
                imageGenerationError=None,
                copyGenerationError=None,
            )
        serialized_draft = _serialize_shopify_theme_template_draft(
            draft=draft,
            latest_version=latest_version,
        )
        serialized_version = _serialize_shopify_theme_template_draft_version(
            version=latest_version
        )
        return ShopifyThemeTemplateGenerateImagesResponse(
            draft=serialized_draft,
            version=serialized_version,
            generatedImageCount=0,
            generatedTextCount=0,
            copyAgentModel=None,
            requestedImageModel=requested_image_model,
            requestedImageModelSource=requested_image_model_source,
            generatedSlotPaths=[],
            imageModels=[],
            imageModelBySlotPath={},
            imageSourceBySlotPath={},
            promptTokenCountBySlotPath={},
            promptTokenCountTotal=0,
            rateLimitedSlotPaths=[],
            remainingSlotPaths=[],
            quotaExhaustedSlotPaths=[],
            slotErrorsByPath={},
            imageGenerationError=None,
            copyGenerationError=None,
        )

    resolved_product_id = payload.productId.strip() if payload.productId else None
    if not resolved_product_id and isinstance(latest_data.productId, str):
        candidate = latest_data.productId.strip()
        if candidate:
            resolved_product_id = candidate
    if not resolved_product_id and isinstance(draft.product_id, UUID):
        resolved_product_id = str(draft.product_id)
    if not resolved_product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Template image and copy generation requires a productId so assets and copy can "
                "be generated for a workspace product."
            ),
        )

    resolved_product = ProductsRepository(session).get(
        org_id=auth.org_id,
        product_id=resolved_product_id,
    )
    if not resolved_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not found for productId={resolved_product_id}.",
        )
    if str(resolved_product.client_id).strip() != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product must belong to this workspace.",
        )
    workspace_brand_description = _resolve_workspace_brand_description(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
    )
    rate_limited_slot_paths: list[str] = []
    quota_exhausted_slot_paths: list[str] = []
    slot_error_by_path: dict[str, str] = {}
    generated_asset_by_slot_path: dict[str, Any] = {}
    image_generation_error: str | None = None
    copy_generation_error: str | None = None
    if should_generate_images:
        try:
            default_general_context = _build_theme_sync_default_general_prompt_context(
                draft_data=latest_data,
                product=resolved_product,
                brand_description=workspace_brand_description,
            )
            default_slot_context_by_path = _build_theme_sync_default_slot_prompt_context_by_path(
                image_slots=image_slots,
                text_slots=text_slots,
                component_text_values=next_component_text_values,
            )
            effective_general_context = default_general_context
            effective_slot_context_by_path = dict(default_slot_context_by_path)
            product_reference_image: dict[str, Any] | None = (
                _resolve_optional_theme_sync_product_reference_image(
                    session=session,
                    org_id=auth.org_id,
                    client_id=client_id,
                    product=resolved_product,
                )
            )

            _emit_theme_sync_progress(
                {
                    "stage": "image_generation",
                    "message": (
                        "Generating template images from deterministic slot requirements."
                        if not requested_slot_paths
                        else (
                            "Generating template images from deterministic slot requirements "
                            f"for {len(requested_slot_paths)} selected slot(s)."
                        )
                    ),
                    "totalImageSlots": len(image_slots_pending_generation),
                    "completedImageSlots": 0,
                    "generatedImageCount": 0,
                    "fallbackImageCount": 0,
                    "skippedImageCount": 0,
                }
            )
            (
                _,
                rate_limited_slot_paths,
                generated_asset_by_slot_path,
                quota_exhausted_slot_paths,
                slot_error_by_path,
            ) = _generate_theme_sync_ai_image_assets(
                session=session,
                org_id=auth.org_id,
                client_id=client_id,
                product_id=resolved_product_id,
                product=resolved_product,
                image_slots=image_slots_pending_generation,
                text_slots=text_slots,
                general_prompt_context=effective_general_context,
                slot_prompt_context_by_path=effective_slot_context_by_path,
                max_concurrency=image_generation_max_concurrency,
                stop_on_quota_exhausted=True,
                reference_image_bytes=(
                    product_reference_image["imageBytes"] if product_reference_image else None
                ),
                reference_image_mime_type=(
                    product_reference_image["mimeType"] if product_reference_image else None
                ),
                reference_asset_public_id=(
                    product_reference_image["assetPublicId"] if product_reference_image else None
                ),
                reference_asset_id=(
                    product_reference_image["assetId"] if product_reference_image else None
                ),
            )
            rate_limited_slot_paths = sorted(
                {
                    slot_path.strip()
                    for slot_path in rate_limited_slot_paths
                    if isinstance(slot_path, str) and slot_path.strip()
                }
            )
            quota_exhausted_slot_paths = sorted(
                {
                    slot_path.strip()
                    for slot_path in quota_exhausted_slot_paths
                    if isinstance(slot_path, str) and slot_path.strip()
                }
            )
        except TestimonialRenderError:
            raise
        except Exception as exc:  # noqa: BLE001
            image_generation_error = _format_non_fatal_generation_error(
                stage="Image generation",
                exc=exc,
            )
            logger.exception(
                "Shopify template image generation failed; continuing with copy generation",
                extra={"client_id": client_id, "draft_id": str(draft.id)},
            )
            _emit_theme_sync_progress(
                {
                    "stage": "image_generation",
                    "message": image_generation_error,
                    "totalImageSlots": len(image_slots_pending_generation),
                    "completedImageSlots": 0,
                    "generatedImageCount": 0,
                    "skippedImageCount": len(image_slots_pending_generation),
                }
            )
            if _is_gemini_quota_or_rate_limit_error(exc):
                rate_limited_slot_paths = sorted(
                    {
                        str(slot.get("path")).strip()
                        for slot in image_slots_pending_generation
                        if isinstance(slot.get("path"), str)
                        and str(slot.get("path")).strip()
                    }
                )
                if _is_gemini_hard_quota_exhaustion_error(exc):
                    quota_exhausted_slot_paths = list(rate_limited_slot_paths)
            for slot in image_slots_pending_generation:
                slot_path = str(slot.get("path")).strip()
                if not slot_path:
                    continue
                slot_error_by_path.setdefault(slot_path, image_generation_error)
    rate_limited_slot_path_set = set(rate_limited_slot_paths)

    generated_slot_paths: list[str] = []
    image_model_by_slot_path: dict[str, str] = {}
    image_source_by_slot_path: dict[str, str] = {}
    prompt_token_count_by_slot_path: dict[str, int] = {}
    for image_slot in image_slots_pending_generation:
        slot_path = str(image_slot["path"]).strip()
        generated_asset = generated_asset_by_slot_path.get(slot_path)
        if generated_asset is None:
            if slot_path in rate_limited_slot_path_set:
                continue
            slot_error_by_path[slot_path] = (
                "Image generation did not return an asset for a required template slot. "
                f"slotPath={slot_path}."
            )
            if image_generation_error is None:
                image_generation_error = slot_error_by_path[slot_path]
            continue
        normalized_public_id = _normalize_asset_public_id(
            getattr(generated_asset, "public_id", None)
        )
        if not normalized_public_id:
            slot_error_by_path[slot_path] = (
                "Image generation returned an invalid asset without public_id. "
                f"slotPath={slot_path}."
            )
            if image_generation_error is None:
                image_generation_error = slot_error_by_path[slot_path]
            continue
        next_component_image_asset_map[slot_path] = normalized_public_id
        generated_slot_paths.append(slot_path)
        raw_ai_metadata = getattr(generated_asset, "ai_metadata", None)
        if isinstance(raw_ai_metadata, dict):
            raw_model = raw_ai_metadata.get("model")
            if isinstance(raw_model, str) and raw_model.strip():
                image_model_by_slot_path[slot_path] = raw_model.strip()
            raw_source = raw_ai_metadata.get("source")
            if isinstance(raw_source, str) and raw_source.strip():
                image_source_by_slot_path[slot_path] = raw_source.strip()
            raw_prompt_token_count = _coerce_non_negative_int(
                raw_ai_metadata.get("promptTokenCount")
            )
            if raw_prompt_token_count is not None:
                prompt_token_count_by_slot_path[slot_path] = raw_prompt_token_count
        if slot_path not in image_source_by_slot_path:
            raw_file_source = getattr(generated_asset, "file_source", None)
            if isinstance(raw_file_source, str) and raw_file_source.strip():
                image_source_by_slot_path[slot_path] = raw_file_source.strip()

    generated_component_text_values: dict[str, str] = {}
    copy_agent_model: str | None = None
    if should_generate_text:
        try:
            copy_settings = _resolve_theme_copy_settings_from_template_metadata(
                metadata=latest_metadata
            )
            planner_copy_kwargs = _build_theme_copy_planner_kwargs(
                copy_settings=copy_settings
            )
            offers = ProductOffersRepository(session).list_by_product(
                product_id=str(resolved_product.id)
            )
            _emit_theme_sync_progress(
                {
                    "stage": "planning_content",
                    "message": "Generating template copy for discovered text slots.",
                    "totalTextSlots": len(ai_text_slots),
                }
            )
            try:
                copy_agent_output = generate_shopify_theme_component_copy(
                    product=resolved_product,
                    offers=offers,
                    text_slots=ai_text_slots,
                    **planner_copy_kwargs,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Theme copy agent failed for Shopify template generation. "
                        f"productId={resolved_product_id}. {exc}"
                    ),
                ) from exc

            copy_text_values = copy_agent_output.get("componentTextValues")
            if not isinstance(copy_text_values, dict):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Theme copy agent returned an invalid componentTextValues payload.",
                )
            expected_text_slot_paths = {
                str(slot.get("path")).strip()
                for slot in ai_text_slots
                if isinstance(slot.get("path"), str) and str(slot.get("path")).strip()
            }
            for setting_path, value in copy_text_values.items():
                if not isinstance(setting_path, str) or not setting_path.strip():
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Theme copy agent returned an invalid text mapping path.",
                    )
                normalized_path = setting_path.strip()
                if normalized_path not in expected_text_slot_paths:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=(
                            "Theme copy agent returned an unknown text slot path: "
                            f"{normalized_path}."
                        ),
                    )
                if not isinstance(value, str) or not value.strip():
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=(
                            "Theme copy agent returned an invalid text value for path "
                            f"{normalized_path}."
                        ),
                    )
                sanitized_value = _sanitize_theme_component_text_value(value)
                if not sanitized_value:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=(
                            "Theme copy agent returned text that became empty after sanitization "
                            f"for path {normalized_path}."
                        ),
                    )
                if normalized_path in generated_component_text_values:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=(
                            "Theme copy agent returned duplicate text mapping path "
                            f"{normalized_path}."
                        ),
                    )
                generated_component_text_values[normalized_path] = sanitized_value
            if expected_text_slot_paths != set(generated_component_text_values.keys()):
                missing_paths = sorted(
                    expected_text_slot_paths - set(generated_component_text_values.keys())
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Theme copy agent did not assign all text slots: "
                        + ", ".join(missing_paths)
                        + "."
                    ),
                )
            next_component_text_values.update(generated_component_text_values)
            copy_model_raw = copy_agent_output.get("model")
            if isinstance(copy_model_raw, str) and copy_model_raw.strip():
                copy_agent_model = copy_model_raw.strip()
        except Exception as exc:  # noqa: BLE001
            copy_generation_error = _format_non_fatal_generation_error(
                stage="Copy generation",
                exc=exc,
            )
            logger.exception(
                "Shopify template copy generation failed; continuing with generated images",
                extra={"client_id": client_id, "draft_id": str(draft.id)},
            )
            _emit_theme_sync_progress(
                {
                    "stage": "planning_content",
                    "message": copy_generation_error,
                    "totalTextSlots": len(ai_text_slots),
                }
            )

    normalized_component_image_asset_map = (
        _normalize_theme_template_component_image_asset_map(next_component_image_asset_map)
    )
    normalized_component_text_values = _normalize_theme_template_component_text_values(
        next_component_text_values
    )
    latest_component_image_urls_for_current_map = {
        setting_path: image_url
        for setting_path, image_url in latest_component_image_urls.items()
        if setting_path in normalized_component_image_asset_map
    }
    component_image_asset_map_changed_paths = {
        setting_path
        for setting_path, asset_public_id in normalized_component_image_asset_map.items()
        if latest_component_image_asset_map.get(setting_path) != asset_public_id
    }
    missing_component_image_url_paths = {
        setting_path
        for setting_path in normalized_component_image_asset_map
        if setting_path not in latest_component_image_urls_for_current_map
    }
    if component_image_asset_map_changed_paths or missing_component_image_url_paths:
        normalized_component_image_urls = (
            _resolve_template_export_component_image_urls_from_asset_map_with_cache(
                session=session,
                org_id=auth.org_id,
                client_id=client_id,
                shop_domain=latest_data.shopDomain,
                component_image_asset_map=normalized_component_image_asset_map,
            )
        )
    else:
        normalized_component_image_urls = latest_component_image_urls_for_current_map

    component_image_urls_changed = (
        set(latest_component_image_urls.keys()) != set(normalized_component_image_asset_map.keys())
        or normalized_component_image_urls != latest_component_image_urls_for_current_map
    )
    component_text_values_changed = (
        normalized_component_text_values
        != _normalize_theme_template_component_text_values(latest_data.componentTextValues)
    )
    feature_highlights_changed = (
        next_feature_highlights_payload != latest_feature_highlights_payload
    )
    image_models = sorted(
        {
            model_name
            for model_name in image_model_by_slot_path.values()
            if isinstance(model_name, str) and model_name.strip()
        }
    )
    prompt_token_count_total = sum(prompt_token_count_by_slot_path.values())
    remaining_slot_paths = sorted(
        {
            slot_path
            for slot_path in generation_scope_slot_paths
            if slot_path not in normalized_component_image_asset_map
        }
    )

    if (
        not generated_slot_paths
        and not generated_component_text_values
        and not component_text_values_changed
        and not feature_highlights_changed
        and not component_image_urls_changed
        and not logo_url_changed
        and not logo_upload_state_changed
    ):
        serialized_draft = _serialize_shopify_theme_template_draft(
            draft=draft,
            latest_version=latest_version,
        )
        serialized_version = _serialize_shopify_theme_template_draft_version(
            version=latest_version
        )
        return ShopifyThemeTemplateGenerateImagesResponse(
            draft=serialized_draft,
            version=serialized_version,
            generatedImageCount=0,
            generatedTextCount=0,
            copyAgentModel=None,
            requestedImageModel=requested_image_model,
            requestedImageModelSource=requested_image_model_source,
            generatedSlotPaths=[],
            imageModels=[],
            imageModelBySlotPath={},
            imageSourceBySlotPath={},
            promptTokenCountBySlotPath={},
            promptTokenCountTotal=0,
            rateLimitedSlotPaths=rate_limited_slot_paths,
            remainingSlotPaths=remaining_slot_paths,
            quotaExhaustedSlotPaths=quota_exhausted_slot_paths,
            slotErrorsByPath=slot_error_by_path,
            imageGenerationError=image_generation_error,
            copyGenerationError=copy_generation_error,
        )

    merged_metadata = dict(latest_metadata)
    merged_metadata.update(
        {
            "generatedImageCount": len(generated_slot_paths),
            "generatedTextCount": len(generated_component_text_values),
            "rateLimitedSlotPaths": rate_limited_slot_paths,
            "remainingSlotPaths": remaining_slot_paths,
            "quotaExhaustedSlotPaths": quota_exhausted_slot_paths,
            "imageGenerationSlotCount": len(generated_slot_paths),
            "imageModels": image_models,
            "imageModelBySlotPath": image_model_by_slot_path,
            "imageSourceBySlotPath": image_source_by_slot_path,
            "requestedImageModel": requested_image_model,
            "requestedImageModelSource": requested_image_model_source,
            "promptTokenCountBySlotPath": prompt_token_count_by_slot_path,
            "promptTokenCountTotal": prompt_token_count_total,
            "componentImageAssetCount": len(normalized_component_image_asset_map),
            "componentImageUrlCount": len(normalized_component_image_urls),
            "componentTextValueCount": len(normalized_component_text_values),
        }
    )
    if resolved_logo_uploaded_shop_domain is not None:
        merged_metadata["logoUploadedShopDomain"] = resolved_logo_uploaded_shop_domain
    else:
        merged_metadata.pop("logoUploadedShopDomain", None)
    if should_generate_images:
        merged_metadata["imageGenerationGeneratedAt"] = datetime.now(timezone.utc).isoformat()
    if generated_component_text_values:
        merged_metadata["copyGenerationGeneratedAt"] = datetime.now(timezone.utc).isoformat()
    if isinstance(copy_agent_model, str) and copy_agent_model.strip():
        merged_metadata["copyAgentModel"] = copy_agent_model.strip()
    if isinstance(image_generation_error, str) and image_generation_error.strip():
        merged_metadata["imageGenerationError"] = image_generation_error.strip()
    if isinstance(copy_generation_error, str) and copy_generation_error.strip():
        merged_metadata["copyGenerationError"] = copy_generation_error.strip()
    if workspace_brand_description:
        merged_metadata[_THEME_IMAGE_PROMPT_METADATA_BRAND_DESCRIPTION_KEY] = (
            workspace_brand_description
        )

    next_data = latest_data.model_copy(
        update={
            "productId": resolved_product_id,
            "logoUrl": resolved_logo_url,
            "componentImageAssetMap": normalized_component_image_asset_map,
            "componentImageUrls": normalized_component_image_urls,
            "componentTextValues": normalized_component_text_values,
            "featureHighlights": resolved_feature_highlights,
            "metadata": merged_metadata,
        }
    )
    draft.product_id = resolved_product.id
    next_version = drafts_repo.create_version(
        draft=draft,
        payload=next_data.model_dump(mode="json"),
        source="agent_image_generation_job",
        created_by_user_external_id=auth.user_id,
    )
    serialized_draft = _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=next_version,
    )
    serialized_version = _serialize_shopify_theme_template_draft_version(
        version=next_version
    )
    return ShopifyThemeTemplateGenerateImagesResponse(
        draft=serialized_draft,
        version=serialized_version,
        generatedImageCount=len(generated_slot_paths),
        generatedTextCount=len(generated_component_text_values),
        copyAgentModel=copy_agent_model,
        requestedImageModel=requested_image_model,
        requestedImageModelSource=requested_image_model_source,
        generatedSlotPaths=sorted(generated_slot_paths),
        imageModels=image_models,
        imageModelBySlotPath=image_model_by_slot_path,
        imageSourceBySlotPath=image_source_by_slot_path,
        promptTokenCountBySlotPath=prompt_token_count_by_slot_path,
        promptTokenCountTotal=prompt_token_count_total,
        rateLimitedSlotPaths=rate_limited_slot_paths,
        remainingSlotPaths=remaining_slot_paths,
        quotaExhaustedSlotPaths=quota_exhausted_slot_paths,
        slotErrorsByPath=slot_error_by_path,
        imageGenerationError=image_generation_error,
        copyGenerationError=copy_generation_error,
    )


def _publish_shopify_theme_template_draft(
    *,
    client_id: str,
    payload: ShopifyThemeTemplatePublishRequest,
    auth: AuthContext,
    session: Session,
) -> ShopifyThemeTemplatePublishResponse:
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(
        org_id=auth.org_id,
        client_id=client_id,
        draft_id=payload.draftId.strip(),
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    if not version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify theme template draft has no versions to publish.",
        )

    serialized_version = _serialize_shopify_theme_template_draft_version(version=version)
    draft_data = serialized_version.data

    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=draft_data.shopDomain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Shopify connection is not ready for template publish: "
                f"{status_payload['message']}"
            ),
        )
    _require_internal_install_for_advanced_shopify(
        status_payload=status_payload,
        action_label="template publish",
    )

    component_image_asset_map = _normalize_theme_template_component_image_asset_map(
        draft_data.componentImageAssetMap
    )
    component_text_values = _normalize_theme_template_component_text_values(
        draft_data.componentTextValues
    )
    component_image_urls = _resolve_component_image_urls_from_asset_map(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        component_image_asset_map=component_image_asset_map,
    )
    (
        latest_brand_name,
        latest_logo_asset_public_id,
        latest_logo_url,
        latest_css_vars,
        latest_font_urls,
        latest_data_theme,
    ) = _resolve_latest_template_publish_design_system_snapshot(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        design_system_id=draft_data.designSystemId,
    )

    _emit_theme_sync_progress(
        {
            "stage": "sync_theme",
            "message": "Publishing approved Shopify theme template draft.",
            "componentImageUrlCount": len(component_image_urls),
            "componentTextValueCount": len(component_text_values),
        }
    )
    synced = sync_client_shopify_theme_brand(
        client_id=client_id,
        workspace_name=draft_data.workspaceName,
        brand_name=latest_brand_name,
        logo_url=latest_logo_url,
        css_vars=latest_css_vars,
        font_urls=latest_font_urls,
        data_theme=latest_data_theme,
        component_image_urls=component_image_urls,
        component_text_values=component_text_values,
        auto_component_image_urls=[],
        theme_id=draft_data.themeId,
        theme_name=None,
        shop_domain=draft_data.shopDomain,
    )

    drafts_repo.mark_published(draft=draft)
    serialized_draft = _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=version,
    )
    sync_response = ShopifyThemeBrandSyncResponse(
        shopDomain=synced["shopDomain"],
        workspaceName=draft_data.workspaceName,
        designSystemId=draft_data.designSystemId,
        designSystemName=draft_data.designSystemName,
        brandName=latest_brand_name,
        logoAssetPublicId=latest_logo_asset_public_id,
        logoUrl=latest_logo_url,
        themeId=synced["themeId"],
        themeName=synced["themeName"],
        themeRole=synced["themeRole"],
        layoutFilename=synced["layoutFilename"],
        cssFilename=synced["cssFilename"],
        settingsFilename=synced.get("settingsFilename"),
        jobId=synced["jobId"],
        coverage=synced["coverage"],
        settingsSync=synced["settingsSync"],
    )

    return ShopifyThemeTemplatePublishResponse(
        draft=serialized_draft,
        version=serialized_version,
        sync=sync_response,
    )


def _slugify_theme_export_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or "template"


def _website_url_from_shop_domain(*, shop_domain: str | None) -> str | None:
    if not isinstance(shop_domain, str):
        return None
    cleaned = shop_domain.strip().lower()
    if not cleaned:
        return None
    return f"https://{cleaned}"


def _compliance_profile_page_urls(
    *, profile: ClientComplianceProfile
) -> dict[str, str | None]:
    return {
        "privacy_policy": profile.privacy_policy_url,
        "terms_of_service": profile.terms_of_service_url,
        "returns_refunds_policy": profile.returns_refunds_policy_url,
        "shipping_policy": profile.shipping_policy_url,
        "contact_support": profile.contact_support_url,
        "company_information": profile.company_information_url,
        "subscription_terms_and_cancellation": profile.subscription_terms_and_cancellation_url,
    }


def _compliance_profile_placeholder_values(
    *, profile: ClientComplianceProfile, workspace_name: str
) -> dict[str, str]:
    values: dict[str, str] = {}
    scalar_fields = {
        "legal_business_name": profile.legal_business_name,
        "operating_entity_name": profile.operating_entity_name,
        "company_address_text": profile.company_address_text,
        "business_license_identifier": profile.business_license_identifier,
        "support_email": profile.support_email,
        "support_phone": profile.support_phone,
        "support_hours_text": profile.support_hours_text,
        "response_time_commitment": profile.response_time_commitment,
    }
    for key, value in scalar_fields.items():
        if isinstance(value, str) and value.strip():
            values[key] = value.strip()

    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    for key, raw_value in metadata.items():
        if not isinstance(key, str):
            continue
        placeholder_key = key.strip()
        if not placeholder_key:
            continue
        if raw_value is None:
            continue
        if isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if not cleaned:
                continue
            values[placeholder_key] = cleaned
            continue
        if isinstance(raw_value, (int, float, bool)):
            values[placeholder_key] = str(raw_value)
    values["brand_name"] = workspace_name
    return values


_DEFAULT_TEMPLATE_EXPORT_PAGE_KEYS: tuple[str, ...] = (
    "privacy_policy",
    "returns_refunds_policy",
    "shipping_policy",
    "terms_of_service",
)


def _select_compliance_page_keys_for_template_export(
    *, requirements: dict[str, Any]
) -> list[str]:
    classification_by_page_key = {
        page["pageKey"]: page["classification"]
        for page in requirements["pages"]
    }
    selected_default: list[str] = []
    for page_key in _DEFAULT_TEMPLATE_EXPORT_PAGE_KEYS:
        if classification_by_page_key.get(page_key) == "not_applicable":
            continue
        selected_default.append(page_key)
    if not selected_default:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No default compliance policy pages are applicable for this workspace "
                "profile. Update the compliance profile business models first."
            ),
        )
    return selected_default


def _extract_markdown_section_body(
    *,
    markdown: str,
    section_title: str,
) -> str:
    section_pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(section_title)}\s*\n(?P<body>.*?)(?=^##\s+|\Z)"
    )
    match = section_pattern.search(markdown)
    if not match:
        raise ValueError(
            f"Rendered contact_support policy markdown is missing section '{section_title}'."
        )
    body = match.group("body").strip()
    if not body:
        raise ValueError(
            f"Rendered contact_support policy markdown has an empty section '{section_title}'."
        )
    return body


def _extract_contact_support_template_values_from_markdown(
    *,
    markdown: str,
) -> dict[str, str]:
    channels_body = _extract_markdown_section_body(
        markdown=markdown,
        section_title="Contact Channels",
    )
    support_hours = _extract_markdown_section_body(
        markdown=markdown,
        section_title="Support Hours",
    )
    business_address = _extract_markdown_section_body(
        markdown=markdown,
        section_title="Business Address",
    )

    email_match = re.search(r"(?im)^\s*-\s*Email:\s*(?P<value>.+?)\s*$", channels_body)
    if not email_match:
        raise ValueError(
            "Rendered contact_support policy markdown is missing the Email line in Contact Channels."
        )
    support_email = email_match.group("value").strip()
    if not support_email:
        raise ValueError(
            "Rendered contact_support policy markdown has an empty Email value in Contact Channels."
        )

    phone_match = re.search(r"(?im)^\s*-\s*Phone:\s*(?P<value>.+?)\s*$", channels_body)
    if not phone_match:
        raise ValueError(
            "Rendered contact_support policy markdown is missing the Phone line in Contact Channels."
        )
    support_phone = phone_match.group("value").strip()
    if not support_phone:
        raise ValueError(
            "Rendered contact_support policy markdown has an empty Phone value in Contact Channels."
        )

    return {
        "supportEmail": support_email,
        "supportPhone": support_phone,
        "supportHours": support_hours,
        "businessAddress": business_address,
    }


def _resolve_theme_export_contact_page_values(
    *,
    policy_sync_payload: dict[str, Any],
) -> dict[str, str]:
    raw_contact_values = policy_sync_payload.get("contactSupport")
    if not isinstance(raw_contact_values, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Theme ZIP export cannot rewrite contact template content because the "
                "compliance sync payload is missing contactSupport values."
            ),
        )

    required_keys = (
        "businessAddress",
        "supportEmail",
        "supportPhone",
        "supportHours",
    )
    missing_or_invalid_keys: list[str] = []
    resolved_values: dict[str, str] = {}
    for key in required_keys:
        value = raw_contact_values.get(key)
        if not isinstance(value, str) or not value.strip():
            missing_or_invalid_keys.append(key)
            continue
        resolved_values[key] = value.strip()
    if missing_or_invalid_keys:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Theme ZIP export cannot rewrite contact template content because contactSupport "
                "values from compliance sync are missing or invalid: "
                + ", ".join(sorted(missing_or_invalid_keys))
                + "."
            ),
        )
    return resolved_values


def _sync_compliance_policy_pages_for_template_export(
    *,
    client_id: str,
    shop_domain: str | None,
    auth: AuthContext,
    session: Session,
    sync_to_shopify: bool = True,
) -> dict[str, Any]:
    client = _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    workspace_name = str(client.name).strip()
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace name is required to export compliance policy pages.",
        )

    profile_repo = ClientComplianceProfilesRepository(session)
    profile = profile_repo.get(org_id=auth.org_id, client_id=client_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot export template ZIP because the compliance profile is missing for this workspace. "
                f"Create it first via PUT /clients/{client_id}/compliance/profile."
            ),
        )

    try:
        requirements = build_page_requirements(
            ruleset_version=profile.ruleset_version,
            business_models=profile.business_models,
            page_urls=_compliance_profile_page_urls(profile=profile),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    page_keys_to_sync = _select_compliance_page_keys_for_template_export(
        requirements=requirements
    )

    effective_shop_domain = shop_domain

    placeholders = _compliance_profile_placeholder_values(
        profile=profile,
        workspace_name=workspace_name,
    )
    website_url = _website_url_from_shop_domain(shop_domain=effective_shop_domain)
    if website_url is not None:
        placeholders["website_url"] = website_url

    try:
        contact_support_values = resolve_theme_contact_page_values(
            placeholder_values=placeholders,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    sync_pages_payload: list[dict[str, str]] = []
    rendered_pages_payload: list[dict[str, str]] = []
    for page_key in page_keys_to_sync:
        template = get_policy_template(page_key=page_key)
        try:
            rendered_markdown = render_policy_template_markdown(
                page_key=page_key,
                placeholder_values=placeholders,
            )
            rendered_html = markdown_to_shopify_html(rendered_markdown)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        handle = get_policy_page_handle(page_key=page_key)
        sync_pages_payload.append(
            {
                "pageKey": page_key,
                "title": template["title"],
                "handle": handle,
                "bodyHtml": rendered_html,
            }
        )
        rendered_pages_payload.append(
            {
                "pageKey": page_key,
                "title": template["title"],
                "handle": handle,
                "markdown": rendered_markdown,
            }
        )

    if not sync_to_shopify:
        local_pages: list[dict[str, str]] = []
        for rendered_page in rendered_pages_payload:
            handle = rendered_page["handle"]
            local_pages.append(
                {
                    "pageKey": rendered_page["pageKey"],
                    "pageId": f"local-policy-page:{handle}",
                    "title": rendered_page["title"],
                    "handle": handle,
                    "url": f"/pages/{handle}",
                    "operation": "generated_local",
                }
            )
            rendered_page["url"] = f"/pages/{handle}"
        return {
            "rulesetVersion": profile.ruleset_version,
            "shopDomain": _normalize_local_theme_shop_domain(shop_domain=effective_shop_domain),
            "pages": local_pages,
            "updatedProfileUrls": {},
            "renderedPages": rendered_pages_payload,
            "contactSupport": contact_support_values,
        }

    sync_payload = upsert_client_shopify_policy_pages(
        client_id=client_id,
        pages=sync_pages_payload,
        shop_domain=effective_shop_domain,
    )
    synced_pages = sync_payload["pages"]
    returned_page_keys = {item["pageKey"] for item in synced_pages}
    expected_page_keys = set(page_keys_to_sync)
    if returned_page_keys != expected_page_keys:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Shopify policy-page sync returned an unexpected page set during template ZIP export. "
                f"expected={sorted(expected_page_keys)} got={sorted(returned_page_keys)}"
            ),
        )

    synced_pages_by_key = {item["pageKey"]: item for item in synced_pages}
    for rendered_page in rendered_pages_payload:
        synced_page = synced_pages_by_key.get(rendered_page["pageKey"])
        if not synced_page:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Policy page sync payload was missing a rendered page entry while preparing "
                    "template ZIP export."
                ),
            )
        rendered_page["url"] = synced_page["url"]

    updated_profile_urls: dict[str, str] = {}
    for page in synced_pages:
        page_key = page["pageKey"]
        profile_url_field = get_profile_url_field_for_page_key(page_key=page_key)
        setattr(profile, profile_url_field, page["url"])
        updated_profile_urls[profile_url_field] = page["url"]

    profile.updated_at = func.now()
    session.add(profile)
    session.commit()

    return {
        "rulesetVersion": profile.ruleset_version,
        "shopDomain": sync_payload["shopDomain"],
        "pages": synced_pages,
        "updatedProfileUrls": updated_profile_urls,
        "renderedPages": rendered_pages_payload,
        "contactSupport": contact_support_values,
    }


def _build_shopify_theme_template_export_zip_response(
    *,
    client_id: str,
    payload: ShopifyThemeTemplatePublishRequest,
    auth: AuthContext,
    session: Session,
) -> StreamingResponse:
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(
        org_id=auth.org_id,
        client_id=client_id,
        draft_id=payload.draftId.strip(),
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    if not version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify theme template draft has no versions to export.",
        )

    serialized_version = _serialize_shopify_theme_template_draft_version(version=version)
    draft_data = serialized_version.data

    policy_sync_payload = _sync_compliance_policy_pages_for_template_export(
        client_id=client_id,
        shop_domain=draft_data.shopDomain,
        auth=auth,
        session=session,
        sync_to_shopify=False,
    )
    contact_page_values = _resolve_theme_export_contact_page_values(
        policy_sync_payload=policy_sync_payload
    )

    component_image_asset_map = _normalize_theme_template_component_image_asset_map(
        draft_data.componentImageAssetMap
    )
    component_text_values = _normalize_theme_template_component_text_values(
        draft_data.componentTextValues
    )
    stored_component_image_urls = _normalize_theme_template_component_image_urls(
        draft_data.componentImageUrls
    )
    component_image_urls = {
        setting_path: stored_component_image_urls[setting_path]
        for setting_path in component_image_asset_map
        if setting_path in stored_component_image_urls
    }
    missing_component_image_url_paths = sorted(
        set(component_image_asset_map.keys()) - set(component_image_urls.keys())
    )
    unexpected_component_image_url_paths = sorted(
        set(stored_component_image_urls.keys()) - set(component_image_asset_map.keys())
    )
    if missing_component_image_url_paths or unexpected_component_image_url_paths:
        details: list[str] = []
        if missing_component_image_url_paths:
            details.append("missing=" + ", ".join(missing_component_image_url_paths))
        if unexpected_component_image_url_paths:
            details.append("unexpected=" + ", ".join(unexpected_component_image_url_paths))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Template ZIP export requires stored Shopify image URLs for every mapped image slot. "
                "Regenerate template images before exporting. "
                + " ".join(details)
                + "."
            ),
        )
    (
        latest_brand_name,
        _latest_logo_asset_public_id,
        latest_logo_url,
        latest_css_vars,
        latest_font_urls,
        latest_data_theme,
    ) = _resolve_latest_template_publish_design_system_snapshot(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        design_system_id=draft_data.designSystemId,
    )
    resolved_theme_id, resolved_theme_name, default_theme_role = (
        _resolve_local_theme_selector(
            theme_id=draft_data.themeId,
            theme_name=draft_data.themeName,
        )
    )
    resolved_theme_role = (
        draft_data.themeRole.strip()
        if isinstance(draft_data.themeRole, str) and draft_data.themeRole.strip()
        else default_theme_role
    )
    sales_page_path_resolution = _resolve_theme_export_sales_page_path(
        client_id=client_id,
        auth=auth,
        session=session,
    )
    if isinstance(sales_page_path_resolution, tuple):
        sales_page_path, sales_page_warning = sales_page_path_resolution
    else:
        # Backward-compatible path for tests that monkeypatch this helper with a raw string.
        sales_page_path = str(sales_page_path_resolution or "")
        sales_page_warning = None
    resolved_export_logo_url = _resolve_uploaded_template_logo_url_for_export(
        draft_data=draft_data,
        latest_logo_asset_public_id=_latest_logo_asset_public_id,
        latest_logo_url=latest_logo_url,
    )
    exported = _build_local_shopify_theme_export_payload(
        shop_domain=draft_data.shopDomain,
        workspace_name=draft_data.workspaceName,
        brand_name=latest_brand_name,
        logo_url=resolved_export_logo_url,
        css_vars=latest_css_vars,
        font_urls=latest_font_urls,
        data_theme=latest_data_theme,
        component_image_urls=component_image_urls,
        component_text_values=component_text_values,
        theme_id=resolved_theme_id,
        theme_name=resolved_theme_name,
        theme_role=resolved_theme_role,
    )

    exported_files = exported["files"]
    ordered_exported_files = sorted(
        exported_files,
        key=lambda file_entry: _theme_export_zip_write_order_key(
            filename=(
                file_entry.get("filename")
                if isinstance(file_entry, dict)
                and isinstance(file_entry.get("filename"), str)
                else ""
            )
        ),
    )
    normalized_text_files_by_filename: dict[str, str] = {}
    exported_archive_filenames: set[str] = set()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_entry in ordered_exported_files:
            filename = file_entry["filename"].strip()
            if not filename:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Template export returned a file with an empty filename.",
                )
            root_directory = filename.split("/", 1)[0].strip().lower()
            if root_directory not in _THEME_EXPORT_ALLOWED_ROOT_DIRECTORIES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Theme ZIP export includes a file outside Shopify theme roots. "
                        f"filename={filename}."
                    ),
                )
            content = file_entry.get("content")
            content_base64 = file_entry.get("contentBase64")
            has_text_content = isinstance(content, str)
            has_base64_content = isinstance(content_base64, str)
            if has_text_content == has_base64_content:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "Template export returned an invalid file payload. "
                        "Expected exactly one of content or contentBase64."
                    ),
                )
            if has_text_content:
                normalized_content = _normalize_theme_export_text_file_content(
                    filename=filename,
                    content=content,
                    sales_page_path=sales_page_path,
                    contact_page_values=contact_page_values,
                )
                normalized_text_files_by_filename[filename] = normalized_content
                zip_file.writestr(filename, normalized_content)
                exported_archive_filenames.add(filename)
                continue

            cleaned_content_base64 = content_base64.strip()
            if not cleaned_content_base64:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "Template export returned an empty contentBase64 payload "
                        f"for filename={filename}."
                    ),
                )
            try:
                file_bytes = base64.b64decode(cleaned_content_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "Template export returned malformed contentBase64 payload "
                        f"for filename={filename}."
                    ),
                ) from exc
            zip_file.writestr(filename, file_bytes)
            exported_archive_filenames.add(filename)

        _validate_required_theme_archive_files_in_export(
            exported_filenames=exported_archive_filenames
        )
        _validate_template_file_format_uniqueness_in_export(
            exported_filenames=exported_archive_filenames
        )
        _validate_required_collection_templates_in_export(
            exported_text_files_by_filename=normalized_text_files_by_filename
        )
        _validate_collection_template_component_values_in_export(
            exported_text_files_by_filename=normalized_text_files_by_filename,
            component_image_urls=component_image_urls,
            component_text_values=component_text_values,
        )

    zip_buffer.seek(0)
    filename_theme = _slugify_theme_export_token(str(exported["themeName"]))
    archive_filename = f"{filename_theme}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{archive_filename}"'}
    if sales_page_warning:
        headers["X-Marketi-Theme-Export-Notice"] = sales_page_warning
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers=headers,
    )


def _refresh_shopify_theme_template_draft_slots_for_export(
    *,
    client_id: str,
    drafts_repo: ShopifyThemeTemplateDraftsRepository,
    draft: Any,
    version: Any,
    auth: AuthContext,
) -> tuple[Any, ShopifyThemeTemplateDraftData]:
    serialized_version = _serialize_shopify_theme_template_draft_version(version=version)
    latest_data = serialized_version.data

    discovered_slots = list_client_shopify_theme_template_slots(
        client_id=client_id,
        theme_id=latest_data.themeId,
        theme_name=None,
        shop_domain=latest_data.shopDomain,
    )
    discovered_shop_domain = discovered_slots.get("shopDomain")
    discovered_theme_id = discovered_slots.get("themeId")
    discovered_theme_name = discovered_slots.get("themeName")
    discovered_theme_role = discovered_slots.get("themeRole")
    if (
        not isinstance(discovered_shop_domain, str)
        or not discovered_shop_domain.strip()
        or not isinstance(discovered_theme_id, str)
        or not discovered_theme_id.strip()
        or not isinstance(discovered_theme_name, str)
        or not discovered_theme_name.strip()
        or not isinstance(discovered_theme_role, str)
        or not discovered_theme_role.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Theme slot discovery returned an invalid theme selector payload during template ZIP export.",
        )

    raw_image_slots = discovered_slots.get("imageSlots")
    raw_text_slots = discovered_slots.get("textSlots")
    if not isinstance(raw_image_slots, list) or not isinstance(raw_text_slots, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Theme slot discovery returned invalid slot collections during template ZIP export.",
        )

    refreshed_image_slots: list[ShopifyThemeTemplateImageSlot] = []
    for raw_slot in raw_image_slots:
        if not isinstance(raw_slot, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Theme slot discovery returned a malformed image slot during template ZIP export.",
            )
        path = raw_slot.get("path")
        key = raw_slot.get("key")
        role = raw_slot.get("role")
        recommended_aspect = raw_slot.get("recommendedAspect")
        current_value = raw_slot.get("currentValue")
        if (
            not isinstance(path, str)
            or not path.strip()
            or not isinstance(key, str)
            or not key.strip()
            or not isinstance(role, str)
            or not role.strip()
            or not isinstance(recommended_aspect, str)
            or not recommended_aspect.strip()
            or (
                current_value is not None
                and (
                    not isinstance(current_value, str)
                    or not current_value.strip()
                )
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Theme slot discovery returned an invalid image slot payload "
                    "during template ZIP export."
                ),
            )
        refreshed_image_slots.append(
            ShopifyThemeTemplateImageSlot(
                path=path.strip(),
                key=key.strip(),
                role=role.strip(),
                recommendedAspect=recommended_aspect.strip(),
                currentValue=(
                    current_value.strip() if isinstance(current_value, str) else None
                ),
            )
        )

    refreshed_text_slots: list[ShopifyThemeTemplateTextSlot] = []
    for raw_slot in raw_text_slots:
        if not isinstance(raw_slot, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Theme slot discovery returned a malformed text slot during template ZIP export.",
            )
        path = raw_slot.get("path")
        key = raw_slot.get("key")
        current_value = raw_slot.get("currentValue")
        if (
            not isinstance(path, str)
            or not path.strip()
            or not isinstance(key, str)
            or not key.strip()
            or (
                current_value is not None
                and (
                    not isinstance(current_value, str)
                    or not current_value.strip()
                )
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Theme slot discovery returned an invalid text slot payload "
                    "during template ZIP export."
                ),
            )
        refreshed_text_slots.append(
            ShopifyThemeTemplateTextSlot(
                path=path.strip(),
                key=key.strip(),
                currentValue=(
                    current_value.strip() if isinstance(current_value, str) else None
                ),
            )
        )

    refreshed_data = latest_data.model_copy(
        update={
            "shopDomain": discovered_shop_domain.strip().lower(),
            "themeId": discovered_theme_id.strip(),
            "themeName": discovered_theme_name.strip(),
            "themeRole": discovered_theme_role.strip(),
            "imageSlots": refreshed_image_slots,
            "textSlots": refreshed_text_slots,
        }
    )
    refreshed_image_slot_paths = {
        slot.path.strip()
        for slot in refreshed_image_slots
        if isinstance(slot.path, str) and slot.path.strip()
    }
    refreshed_text_slot_paths = {
        slot.path.strip()
        for slot in refreshed_text_slots
        if isinstance(slot.path, str) and slot.path.strip()
    }
    pruned_component_image_asset_map = {
        raw_path.strip(): raw_asset_public_id.strip()
        for raw_path, raw_asset_public_id in refreshed_data.componentImageAssetMap.items()
        if isinstance(raw_path, str)
        and raw_path.strip()
        and isinstance(raw_asset_public_id, str)
        and raw_asset_public_id.strip()
        and raw_path.strip() in refreshed_image_slot_paths
    }
    legacy_overlay_image_slot_path = (
        "templates/collection.json.sections.images-with-text-overlay.blocks.image.settings.image"
    )
    upgraded_overlay_image_slot_paths = (
        "templates/collection.json.sections.images-with-text-overlay.settings.image_1",
        "templates/collection.json.sections.images-with-text-overlay.settings.image_2",
        "templates/collection.json.sections.images-with-text-overlay.settings.image_3",
        "templates/collection.json.sections.images-with-text-overlay.settings.image_4",
        "templates/collection.json.sections.images-with-text-overlay.settings.image_5",
    )
    legacy_overlay_asset_public_id = refreshed_data.componentImageAssetMap.get(
        legacy_overlay_image_slot_path
    )
    if not (
        isinstance(legacy_overlay_asset_public_id, str)
        and legacy_overlay_asset_public_id.strip()
    ):
        for previous_version in drafts_repo.list_versions(draft_id=str(draft.id)):
            if str(previous_version.id) == str(version.id):
                continue
            previous_payload = (
                previous_version.payload if isinstance(previous_version.payload, dict) else {}
            )
            previous_component_image_asset_map = previous_payload.get("componentImageAssetMap")
            if not isinstance(previous_component_image_asset_map, dict):
                continue
            for upgraded_path in upgraded_overlay_image_slot_paths:
                candidate = previous_component_image_asset_map.get(upgraded_path)
                if isinstance(candidate, str) and candidate.strip():
                    legacy_overlay_asset_public_id = candidate.strip()
                    break
            if (
                isinstance(legacy_overlay_asset_public_id, str)
                and legacy_overlay_asset_public_id.strip()
            ):
                break
            candidate = previous_component_image_asset_map.get(legacy_overlay_image_slot_path)
            if isinstance(candidate, str) and candidate.strip():
                legacy_overlay_asset_public_id = candidate.strip()
                break
    if (
        isinstance(legacy_overlay_asset_public_id, str)
        and legacy_overlay_asset_public_id.strip()
        and all(path in refreshed_image_slot_paths for path in upgraded_overlay_image_slot_paths)
        and not any(
            path in pruned_component_image_asset_map
            for path in upgraded_overlay_image_slot_paths
        )
    ):
        for path in upgraded_overlay_image_slot_paths:
            pruned_component_image_asset_map[path] = legacy_overlay_asset_public_id.strip()
    normalized_component_image_urls = _normalize_theme_template_component_image_urls(
        refreshed_data.componentImageUrls
    )
    pruned_component_image_urls = {
        raw_path.strip(): raw_url.strip()
        for raw_path, raw_url in normalized_component_image_urls.items()
        if isinstance(raw_path, str)
        and raw_path.strip()
        and isinstance(raw_url, str)
        and raw_url.strip()
        and raw_path.strip() in refreshed_image_slot_paths
    }
    pruned_component_text_values = {
        raw_path.strip(): raw_value.strip()
        for raw_path, raw_value in refreshed_data.componentTextValues.items()
        if isinstance(raw_path, str)
        and raw_path.strip()
        and isinstance(raw_value, str)
        and raw_value.strip()
        and raw_path.strip() in refreshed_text_slot_paths
    }
    pruned_non_feature_component_text_values = {
        setting_path: value
        for setting_path, value in pruned_component_text_values.items()
        if not _is_theme_feature_highlight_text_slot_path(setting_path)
    }
    refreshed_text_slot_payloads = [slot.model_dump(mode="json") for slot in refreshed_text_slots]
    resolved_feature_highlights, managed_feature_component_text_values = (
        _resolve_theme_template_feature_highlights(
            existing_feature_highlights=refreshed_data.featureHighlights,
            component_text_values=pruned_component_text_values,
            text_slots=refreshed_text_slot_payloads,
        )
    )
    pruned_component_text_values = _normalize_theme_template_component_text_values(
        {
            **pruned_non_feature_component_text_values,
            **managed_feature_component_text_values,
        }
    )
    refreshed_data = refreshed_data.model_copy(
        update={
            "componentImageAssetMap": pruned_component_image_asset_map,
            "componentImageUrls": pruned_component_image_urls,
            "componentTextValues": pruned_component_text_values,
            "featureHighlights": resolved_feature_highlights,
        }
    )

    normalized_shop_domain = refreshed_data.shopDomain.strip().lower()
    normalized_theme_id = refreshed_data.themeId.strip()
    normalized_theme_name = refreshed_data.themeName.strip()
    normalized_theme_role = refreshed_data.themeRole.strip()
    draft_metadata_changed = (
        str(draft.shop_domain).strip().lower() != normalized_shop_domain
        or str(draft.theme_id).strip() != normalized_theme_id
        or str(draft.theme_name).strip() != normalized_theme_name
        or str(draft.theme_role).strip() != normalized_theme_role
    )
    if draft_metadata_changed:
        draft.shop_domain = normalized_shop_domain
        draft.theme_id = normalized_theme_id
        draft.theme_name = normalized_theme_name
        draft.theme_role = normalized_theme_role

    payload_changed = (
        refreshed_data.model_dump(mode="json") != latest_data.model_dump(mode="json")
    )
    if not payload_changed:
        if draft_metadata_changed:
            draft.updated_at = datetime.now(timezone.utc)
            drafts_repo.session.add(draft)
            drafts_repo.session.commit()
            drafts_repo.session.refresh(draft)
        return version, latest_data

    refreshed_version = drafts_repo.create_version(
        draft=draft,
        payload=refreshed_data.model_dump(mode="json"),
        source="slot_refresh",
        notes="Refreshed template slot snapshot before ZIP export.",
        created_by_user_external_id=auth.user_id,
    )
    return refreshed_version, refreshed_data


def _run_client_shopify_theme_template_build_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify theme template build job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeTemplateBuildRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        publish_progress(
            {
                "stage": "running",
                "message": "Building Shopify theme template draft.",
            }
        )
        try:
            build_response = _build_or_update_shopify_theme_template_draft(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = (
                    f"Shopify theme template build failed with status {exc.status_code}."
                )
            publish_progress({"stage": "failed", "message": error_message})
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        result_payload = build_response.model_dump(mode="json")
        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify theme template draft built successfully.",
                "draftId": build_response.draft.id,
                "draftVersionNumber": build_response.version.versionNumber,
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme template build job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc) or "Unhandled error while running Shopify theme template build job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify theme template build job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify theme template build job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


def _compute_shopify_template_image_retry_delay_seconds(attempt_number: int) -> float:
    if attempt_number <= 1:
        return 0.0
    retry_power = max(0, attempt_number - 2)
    delay_seconds = _SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_BASE_DELAY_SECONDS * (2**retry_power)
    return min(_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_DELAY_SECONDS, delay_seconds)


def _generate_shopify_theme_template_draft_images_with_retry(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateGenerateImagesRequest,
    auth: AuthContext,
    session: Session,
    publish_progress: Any,
) -> ShopifyThemeTemplateGenerateImagesResponse:
    aggregated_slot_paths: set[str] = set()
    aggregated_generated_text_count = 0
    aggregated_copy_agent_model: str | None = None
    aggregated_model_by_slot_path: dict[str, str] = {}
    aggregated_source_by_slot_path: dict[str, str] = {}
    aggregated_prompt_token_count_by_slot_path: dict[str, int] = {}
    aggregated_slot_errors_by_path: dict[str, str] = {}
    aggregated_image_generation_error: str | None = None
    aggregated_copy_generation_error: str | None = None
    last_remaining_slot_paths: list[str] = []
    final_response: ShopifyThemeTemplateGenerateImagesResponse | None = None

    max_attempts = max(1, _SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_ATTEMPTS)
    template_max_concurrency = max(
        1,
        min(
            _THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY,
            _SHOPIFY_TEMPLATE_IMAGE_GENERATION_MAX_CONCURRENCY,
        ),
    )
    for attempt_number in range(1, max_attempts + 1):
        if attempt_number > 1:
            delay_seconds = _compute_shopify_template_image_retry_delay_seconds(
                attempt_number
            )
            publish_progress(
                {
                    "stage": "waiting_for_retry",
                    "message": (
                        "Template image generation is rate-limited. "
                        f"Retrying pending slots in {delay_seconds:.0f}s "
                        f"(attempt {attempt_number}/{max_attempts})."
                    ),
                    "generatedImageCount": len(aggregated_slot_paths),
                    "skippedImageCount": len(last_remaining_slot_paths),
                }
            )
            time.sleep(delay_seconds)

        publish_progress(
            {
                "stage": "running",
                "message": (
                    "Generating images for Shopify theme template draft "
                    f"(attempt {attempt_number}/{max_attempts}, "
                    f"concurrency={template_max_concurrency})."
                ),
                "generatedImageCount": len(aggregated_slot_paths),
                "skippedImageCount": len(last_remaining_slot_paths),
            }
        )
        response = _generate_shopify_theme_template_draft_images(
            client_id=client_id,
            payload=payload,
            auth=auth,
            session=session,
            image_generation_max_concurrency=template_max_concurrency,
            generate_text=attempt_number == 1,
        )
        final_response = response

        if response.generatedTextCount > 0:
            aggregated_generated_text_count = max(
                aggregated_generated_text_count,
                response.generatedTextCount,
            )
        if (
            aggregated_copy_agent_model is None
            and isinstance(response.copyAgentModel, str)
            and response.copyAgentModel.strip()
        ):
            aggregated_copy_agent_model = response.copyAgentModel.strip()
        if (
            aggregated_image_generation_error is None
            and isinstance(response.imageGenerationError, str)
            and response.imageGenerationError.strip()
        ):
            aggregated_image_generation_error = response.imageGenerationError.strip()
        if (
            aggregated_copy_generation_error is None
            and isinstance(response.copyGenerationError, str)
            and response.copyGenerationError.strip()
        ):
            aggregated_copy_generation_error = response.copyGenerationError.strip()
        aggregated_slot_paths.update(response.generatedSlotPaths)
        aggregated_model_by_slot_path.update(response.imageModelBySlotPath)
        aggregated_source_by_slot_path.update(response.imageSourceBySlotPath)
        for slot_path, raw_error in response.slotErrorsByPath.items():
            if (
                not isinstance(slot_path, str)
                or not slot_path.strip()
                or not isinstance(raw_error, str)
                or not raw_error.strip()
            ):
                continue
            aggregated_slot_errors_by_path[slot_path.strip()] = raw_error.strip()
        for slot_path in response.generatedSlotPaths:
            if not isinstance(slot_path, str) or not slot_path.strip():
                continue
            aggregated_slot_errors_by_path.pop(slot_path.strip(), None)
        for slot_path, raw_prompt_token_count in response.promptTokenCountBySlotPath.items():
            if not isinstance(slot_path, str) or not slot_path.strip():
                continue
            normalized_prompt_token_count = _coerce_non_negative_int(raw_prompt_token_count)
            if normalized_prompt_token_count is None:
                continue
            aggregated_prompt_token_count_by_slot_path[
                slot_path.strip()
            ] = normalized_prompt_token_count
        quota_exhausted_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in response.quotaExhaustedSlotPaths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
        if quota_exhausted_slot_paths:
            generated_so_far = len(aggregated_slot_paths)
            model_note = (
                f" model={response.requestedImageModel}, source={response.requestedImageModelSource}."
                if isinstance(response.requestedImageModel, str)
                and response.requestedImageModel.strip()
                else ""
            )
            first_quota_slot_path = quota_exhausted_slot_paths[0]
            first_quota_error = response.slotErrorsByPath.get(first_quota_slot_path)
            first_quota_error_note = (
                f" Gemini error: {first_quota_error}"
                if isinstance(first_quota_error, str) and first_quota_error.strip()
                else ""
            )
            quota_error_message = (
                "Template image generation stopped early because Gemini quota is exhausted. "
                f"Generated {generated_so_far} slot(s) before stopping.{model_note}"
                f"{first_quota_error_note} "
                "Retry once quota resets. Slots: "
                + ", ".join(quota_exhausted_slot_paths)
            )
            if aggregated_slot_paths or aggregated_generated_text_count > 0:
                if aggregated_image_generation_error is None:
                    aggregated_image_generation_error = quota_error_message
                last_remaining_slot_paths = list(quota_exhausted_slot_paths)
                break
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=quota_error_message,
            )

        remaining_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in response.remainingSlotPaths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
        rate_limited_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in response.rateLimitedSlotPaths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
        last_remaining_slot_paths = remaining_slot_paths
        if not remaining_slot_paths:
            break

        if not rate_limited_slot_paths:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Template image generation left pending image slots without a retryable "
                    "rate-limit signal. Remaining slots: "
                    + ", ".join(remaining_slot_paths)
                ),
            )

    if final_response is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Template image generation did not produce a response payload.",
        )

    if last_remaining_slot_paths:
        first_remaining_slot_path = last_remaining_slot_paths[0]
        first_remaining_slot_error = aggregated_slot_errors_by_path.get(first_remaining_slot_path)
        first_remaining_slot_error_note = (
            f" Latest Gemini error: {first_remaining_slot_error} "
            if isinstance(first_remaining_slot_error, str) and first_remaining_slot_error.strip()
            else ""
        )
        remaining_error_message = (
            "Template image generation remained rate-limited after "
            f"{max_attempts} attempts."
            f"{first_remaining_slot_error_note}"
            "Remaining slots: "
            + ", ".join(last_remaining_slot_paths)
        )
        if aggregated_slot_paths or aggregated_generated_text_count > 0:
            if aggregated_image_generation_error is None:
                aggregated_image_generation_error = remaining_error_message
        else:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=remaining_error_message,
            )

    if (
        not aggregated_slot_paths
        and final_response.generatedImageCount == 0
        and not final_response.generatedSlotPaths
    ):
        return final_response.model_copy(
            update={
                "generatedTextCount": aggregated_generated_text_count,
                "copyAgentModel": aggregated_copy_agent_model,
                "imageGenerationError": aggregated_image_generation_error,
                "copyGenerationError": aggregated_copy_generation_error,
            }
        )

    merged_model_by_slot_path = dict(aggregated_model_by_slot_path)
    merged_source_by_slot_path = dict(aggregated_source_by_slot_path)
    merged_prompt_token_count_by_slot_path = dict(
        sorted(aggregated_prompt_token_count_by_slot_path.items())
    )
    merged_slot_errors_by_path = dict(sorted(aggregated_slot_errors_by_path.items()))
    merged_image_models = sorted(
        {
            model_name.strip()
            for model_name in merged_model_by_slot_path.values()
            if isinstance(model_name, str) and model_name.strip()
        }
    )
    merged_prompt_token_count_total = sum(merged_prompt_token_count_by_slot_path.values())
    merged_rate_limited_slot_paths = sorted(
        {
            slot_path.strip()
            for slot_path in final_response.rateLimitedSlotPaths
            if isinstance(slot_path, str) and slot_path.strip()
        }
    )
    merged_remaining_slot_paths = sorted(
        {
            slot_path.strip()
            for slot_path in (last_remaining_slot_paths or final_response.remainingSlotPaths)
            if isinstance(slot_path, str) and slot_path.strip()
        }
    )
    merged_quota_exhausted_slot_paths = sorted(
        {
            slot_path.strip()
            for slot_path in final_response.quotaExhaustedSlotPaths
            if isinstance(slot_path, str) and slot_path.strip()
        }
    )

    return final_response.model_copy(
        update={
            "generatedImageCount": len(aggregated_slot_paths),
            "generatedTextCount": aggregated_generated_text_count,
            "copyAgentModel": aggregated_copy_agent_model,
            "generatedSlotPaths": sorted(aggregated_slot_paths),
            "imageModels": merged_image_models,
            "imageModelBySlotPath": merged_model_by_slot_path,
            "imageSourceBySlotPath": merged_source_by_slot_path,
            "promptTokenCountBySlotPath": merged_prompt_token_count_by_slot_path,
            "promptTokenCountTotal": merged_prompt_token_count_total,
            "rateLimitedSlotPaths": merged_rate_limited_slot_paths,
            "remainingSlotPaths": merged_remaining_slot_paths,
            "quotaExhaustedSlotPaths": merged_quota_exhausted_slot_paths,
            "slotErrorsByPath": merged_slot_errors_by_path,
            "imageGenerationError": aggregated_image_generation_error,
            "copyGenerationError": aggregated_copy_generation_error,
        }
    )


def _run_client_shopify_theme_template_generate_images_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify template image and copy generation job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeTemplateGenerateImagesRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        requested_image_model, requested_image_model_source = (
            resolve_funnel_image_model_config()
        )
        publish_progress(
            {
                "stage": "running",
                "message": (
                    "Generating images and copy for Shopify theme template draft "
                    f"(model={requested_image_model}, source={requested_image_model_source})."
                ),
            }
        )
        try:
            generate_images_response = _generate_shopify_theme_template_draft_images_with_retry(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
                publish_progress=publish_progress,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = (
                    "Shopify template image generation failed "
                    f"with status {exc.status_code}."
                )
            publish_progress({"stage": "failed", "message": error_message})
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        result_payload = generate_images_response.model_dump(mode="json")
        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify template images and copy generated successfully.",
                "draftId": generate_images_response.draft.id,
                "draftVersionNumber": generate_images_response.version.versionNumber,
                "generatedImageCount": generate_images_response.generatedImageCount,
                "generatedTextCount": generate_images_response.generatedTextCount,
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme template image generation job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc)
                or "Unhandled error while running Shopify template image generation job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify template image generation job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify template image generation job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


def _run_client_shopify_theme_template_publish_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify theme template publish job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeTemplatePublishRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        publish_progress(
            {
                "stage": "running",
                "message": "Publishing Shopify theme template draft.",
            }
        )
        try:
            publish_response = _publish_shopify_theme_template_draft(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = (
                    f"Shopify theme template publish failed with status {exc.status_code}."
                )
            publish_progress({"stage": "failed", "message": error_message})
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        result_payload = publish_response.model_dump(mode="json")
        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify theme template draft published successfully.",
                "draftId": publish_response.draft.id,
                "draftVersionNumber": publish_response.version.versionNumber,
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme template publish job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc) or "Unhandled error while running Shopify theme template publish job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify theme template publish job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify theme template publish job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


@router.get("/{client_id}/shopify/status", response_model=ShopifyConnectionStatusResponse)
def get_client_shopify_status(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    resolved_shop_domain = status_payload.get("shopDomain")
    if status_payload.get("state") == "ready" and isinstance(resolved_shop_domain, str):
        sync_workspace_shopify_catalog_collection(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            shop_domain=resolved_shop_domain,
        )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.post("/{client_id}/shopify/install-url", response_model=ShopifyInstallUrlResponse)
def create_client_shopify_install_url(
    client_id: str,
    payload: ShopifyInstallUrlRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    install_urls = build_client_shopify_install_urls(
        client_id=client_id, shop_domain=payload.shopDomain
    )
    return ShopifyInstallUrlResponse(**install_urls)


@router.patch("/{client_id}/shopify/installation", response_model=ShopifyConnectionStatusResponse)
def update_client_shopify_installation(
    client_id: str,
    payload: ShopifyInstallationUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    set_client_shopify_storefront_token(
        client_id=client_id,
        shop_domain=payload.shopDomain,
        storefront_access_token=payload.storefrontAccessToken,
    )
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    resolved_shop_domain = status_payload.get("shopDomain")
    if status_payload.get("state") == "ready" and isinstance(resolved_shop_domain, str):
        sync_workspace_shopify_catalog_collection(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            shop_domain=resolved_shop_domain,
        )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.post(
    "/{client_id}/shopify/installation/auto-storefront-token",
    response_model=ShopifyConnectionStatusResponse,
)
def auto_provision_client_shopify_installation_storefront_token(
    client_id: str,
    payload: ShopifyInstallationAutoStorefrontTokenRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    auto_provision_client_shopify_storefront_token(
        client_id=client_id,
        shop_domain=payload.shopDomain,
    )
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    resolved_shop_domain = status_payload.get("shopDomain")
    if status_payload.get("state") == "ready" and isinstance(resolved_shop_domain, str):
        sync_workspace_shopify_catalog_collection(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            shop_domain=resolved_shop_domain,
        )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.delete("/{client_id}/shopify/installation", response_model=ShopifyConnectionStatusResponse)
def disconnect_client_shopify_installation(
    client_id: str,
    payload: ShopifyInstallationDisconnectRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    normalized_shop = normalize_shop_domain(payload.shopDomain)
    disconnect_client_shopify_store(client_id=client_id, shop_domain=normalized_shop)

    prefs_with_selected_shop = session.scalars(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == auth.org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.selected_shop_domain == normalized_shop,
        )
    ).all()
    if prefs_with_selected_shop:
        for pref in prefs_with_selected_shop:
            pref.selected_shop_domain = None
            pref.updated_at = func.now()
        session.commit()

    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.put("/{client_id}/shopify/default-shop", response_model=ShopifyConnectionStatusResponse)
def set_client_shopify_default_shop(
    client_id: str,
    payload: ShopifyDefaultShopRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    normalized_shop = normalize_shop_domain(payload.shopDomain)

    installations = list_shopify_installations()
    active_installation = next(
        (
            installation
            for installation in installations
            if installation.client_id == client_id
            and installation.uninstalled_at is None
            and installation.shop_domain == normalized_shop
        ),
        None,
    )
    if not active_installation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected shopDomain is not an active Shopify installation for this workspace.",
        )

    pref = _get_client_user_pref(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    if pref:
        pref.selected_shop_domain = normalized_shop
        pref.updated_at = func.now()
    else:
        session.add(
            ClientUserPreference(
                org_id=auth.org_id,
                client_id=client_id,
                user_external_id=auth.user_id,
                selected_shop_domain=normalized_shop,
            )
        )
    session.commit()

    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=normalized_shop,
    )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.get("/{client_id}/shopify/products", response_model=ShopifyProductListResponse)
def list_client_shopify_products_route(
    client_id: str,
    query: str | None = Query(default=None),
    limit: int = Query(default=20),
    shopDomain: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = shopDomain or selected_shop_domain
    payload = list_client_shopify_products(
        client_id=client_id,
        query=query,
        limit=limit,
        shop_domain=effective_shop_domain,
    )
    return ShopifyProductListResponse(**payload)


@router.post("/{client_id}/shopify/products", response_model=ShopifyProductCreateResponse)
def create_client_shopify_product_route(
    client_id: str,
    payload: ShopifyCreateProductRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = payload.shopDomain or selected_shop_domain
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=effective_shop_domain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )
    _require_internal_install_for_advanced_shopify(
        status_payload=status_payload,
        action_label="theme sync",
    )
    created = create_client_shopify_product(
        client_id=client_id,
        title=payload.title,
        description=payload.description,
        handle=payload.handle,
        vendor=payload.vendor,
        product_type=payload.productType,
        tags=payload.tags,
        status_text=payload.status,
        variants=[variant.model_dump() for variant in payload.variants],
        shop_domain=effective_shop_domain,
    )
    return ShopifyProductCreateResponse(**created)


@router.post(
    "/{client_id}/shopify/theme/brand/template/build-async",
    response_model=ShopifyThemeTemplateBuildJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_template_build_route(
    client_id: str,
    payload: ShopifyThemeTemplateBuildRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    jobs_repo = JobsRepository(session)
    job, _ = jobs_repo.get_or_create(
        org_id=auth.org_id,
        client_id=client_id,
        research_run_id=None,
        job_type=_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_BUILD,
        subject_type=_JOB_SUBJECT_TYPE_CLIENT,
        subject_id=client_id,
        dedupe_key=None,
        input_payload={
            "clientId": client_id,
            "payload": payload.model_dump(mode="json"),
            "auth": {
                "userId": auth.user_id,
                "orgId": auth.org_id,
            },
        },
        status=JOB_STATUS_QUEUED,
    )
    background_tasks.add_task(_run_client_shopify_theme_template_build_job, str(job.id))

    return ShopifyThemeTemplateBuildJobStartResponse(
        jobId=str(job.id),
        status=job.status,
        statusPath=f"/clients/{client_id}/shopify/theme/brand/template/build-jobs/{job.id}",
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/build-jobs/{job_id}",
    response_model=ShopifyThemeTemplateBuildJobStatusResponse,
)
def get_client_shopify_theme_template_build_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build job not found.")

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_TEMPLATE_BUILD
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build job not found.")

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Build job is in an unsupported state: {job.status}",
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeTemplateBuildResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeTemplateBuildResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeTemplateBuildJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/drafts",
    response_model=list[ShopifyThemeTemplateDraftResponse],
)
def list_client_shopify_theme_template_drafts_route(
    client_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    drafts = drafts_repo.list_for_client(org_id=auth.org_id, client_id=client_id, limit=limit)
    response_payload: list[ShopifyThemeTemplateDraftResponse] = []
    for draft in drafts:
        latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
        response_payload.append(
            _serialize_shopify_theme_template_draft(
                draft=draft,
                latest_version=latest_version,
            )
        )
    return response_payload


@router.get(
    "/{client_id}/shopify/theme/brand/template/drafts/{draft_id}",
    response_model=ShopifyThemeTemplateDraftResponse,
)
def get_client_shopify_theme_template_draft_route(
    client_id: str,
    draft_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(org_id=auth.org_id, client_id=client_id, draft_id=draft_id)
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    return _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=latest_version,
    )


@router.put(
    "/{client_id}/shopify/theme/brand/template/drafts/{draft_id}",
    response_model=ShopifyThemeTemplateDraftResponse,
)
def update_client_shopify_theme_template_draft_route(
    client_id: str,
    draft_id: str,
    payload: ShopifyThemeTemplateDraftUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(org_id=auth.org_id, client_id=client_id, draft_id=draft_id)
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify theme template draft has no versions to update.",
        )
    serialized_latest_version = _serialize_shopify_theme_template_draft_version(
        version=latest_version
    )
    latest_data = serialized_latest_version.data

    if payload.componentImageAssetMap is None:
        component_image_asset_map = dict(latest_data.componentImageAssetMap)
    else:
        component_image_asset_map = _normalize_theme_template_component_image_asset_map(
            payload.componentImageAssetMap
        )
    latest_component_image_urls = _normalize_theme_template_component_image_urls(
        latest_data.componentImageUrls
    )
    if payload.componentImageAssetMap is None:
        component_image_urls = {
            setting_path: image_url
            for setting_path, image_url in latest_component_image_urls.items()
            if setting_path in component_image_asset_map
        }
    else:
        previous_component_image_asset_map = dict(latest_data.componentImageAssetMap)
        component_image_urls = {}
        for setting_path, asset_public_id in component_image_asset_map.items():
            previous_asset_public_id = previous_component_image_asset_map.get(setting_path)
            if previous_asset_public_id != asset_public_id:
                continue
            cached_image_url = latest_component_image_urls.get(setting_path)
            if isinstance(cached_image_url, str) and cached_image_url.strip().startswith(
                "shopify://"
            ):
                component_image_urls[setting_path] = cached_image_url.strip()
    if payload.componentTextValues is None:
        component_text_values = dict(latest_data.componentTextValues)
    else:
        component_text_values = _normalize_theme_template_component_text_values(
            payload.componentTextValues
        )
    non_feature_component_text_values = {
        setting_path: value
        for setting_path, value in component_text_values.items()
        if not _is_theme_feature_highlight_text_slot_path(setting_path)
    }
    latest_text_slots = [slot.model_dump(mode="json") for slot in latest_data.textSlots]
    resolved_feature_highlights, managed_feature_component_text_values = (
        _resolve_theme_template_feature_highlights(
            feature_highlights=payload.featureHighlights,
            existing_feature_highlights=latest_data.featureHighlights,
            component_text_values=component_text_values,
            text_slots=latest_text_slots,
        )
    )
    component_text_values = _normalize_theme_template_component_text_values(
        {
            **non_feature_component_text_values,
            **managed_feature_component_text_values,
        }
    )

    _resolve_component_image_urls_from_asset_map(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        component_image_asset_map=component_image_asset_map,
    )

    merged_metadata = dict(latest_data.metadata or {})
    merged_metadata["componentImageAssetCount"] = len(component_image_asset_map)
    merged_metadata["componentImageUrlCount"] = len(component_image_urls)
    merged_metadata["componentTextValueCount"] = len(component_text_values)

    next_data = latest_data.model_copy(
        update={
            "componentImageAssetMap": component_image_asset_map,
            "componentImageUrls": component_image_urls,
            "componentTextValues": component_text_values,
            "featureHighlights": resolved_feature_highlights,
            "metadata": merged_metadata,
        }
    )
    next_version = drafts_repo.create_version(
        draft=draft,
        payload=next_data.model_dump(mode="json"),
        source="manual_edit",
        notes=(payload.notes.strip() if isinstance(payload.notes, str) and payload.notes.strip() else None),
        created_by_user_external_id=auth.user_id,
    )
    return _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=next_version,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/template/generate-images-async",
    response_model=ShopifyThemeTemplateGenerateImagesJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_template_generate_images_route(
    client_id: str,
    payload: ShopifyThemeTemplateGenerateImagesRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    jobs_repo = JobsRepository(session)
    job, _ = jobs_repo.get_or_create(
        org_id=auth.org_id,
        client_id=client_id,
        research_run_id=None,
        job_type=_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_GENERATE_IMAGES,
        subject_type=_JOB_SUBJECT_TYPE_CLIENT,
        subject_id=client_id,
        dedupe_key=None,
        input_payload={
            "clientId": client_id,
            "payload": payload.model_dump(mode="json"),
            "auth": {
                "userId": auth.user_id,
                "orgId": auth.org_id,
            },
        },
        status=JOB_STATUS_QUEUED,
    )
    background_tasks.add_task(
        _run_client_shopify_theme_template_generate_images_job, str(job.id)
    )

    return ShopifyThemeTemplateGenerateImagesJobStartResponse(
        jobId=str(job.id),
        status=job.status,
        statusPath=f"/clients/{client_id}/shopify/theme/brand/template/generate-images-jobs/{job.id}",
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/generate-images-jobs/{job_id}",
    response_model=ShopifyThemeTemplateGenerateImagesJobStatusResponse,
)
def get_client_shopify_theme_template_generate_images_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template image generation job not found.",
        )

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_TEMPLATE_GENERATE_IMAGES
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template image generation job not found.",
        )

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Template image generation job is in an unsupported state: "
                f"{job.status}"
            ),
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeTemplateGenerateImagesResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeTemplateGenerateImagesResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeTemplateGenerateImagesJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/template/export-zip",
)
def export_client_shopify_theme_template_zip_route(
    client_id: str,
    payload: ShopifyThemeTemplatePublishRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    return _build_shopify_theme_template_export_zip_response(
        client_id=client_id,
        payload=payload,
        auth=auth,
        session=session,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/template/publish-async",
    response_model=ShopifyThemeTemplatePublishJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_template_publish_route(
    client_id: str,
    payload: ShopifyThemeTemplatePublishRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Direct Shopify theme publish is disabled. "
            "Export the template ZIP and apply changes via your approved theme extension path."
        ),
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/publish-jobs/{job_id}",
    response_model=ShopifyThemeTemplatePublishJobStatusResponse,
)
def get_client_shopify_theme_template_publish_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found.")

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_TEMPLATE_PUBLISH
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found.")

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publish job is in an unsupported state: {job.status}",
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeTemplatePublishResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeTemplatePublishResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeTemplatePublishJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/sync-async",
    response_model=ShopifyThemeBrandSyncJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_brand_sync_route(
    client_id: str,
    payload: ShopifyThemeBrandSyncRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Direct Shopify theme sync is disabled. "
            "Use template ZIP export and extension-based rollout for storefront changes."
        ),
    )


@router.get(
    "/{client_id}/shopify/theme/brand/sync-jobs/{job_id}",
    response_model=ShopifyThemeBrandSyncJobStatusResponse,
)
def get_client_shopify_theme_brand_sync_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync job not found.")

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_BRAND_SYNC
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync job not found.")

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync job is in an unsupported state: {job.status}",
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeBrandSyncResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeBrandSyncResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeBrandSyncJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/sync",
    response_model=ShopifyThemeBrandSyncResponse,
)
def sync_client_shopify_theme_brand_route(
    client_id: str,
    _payload: ShopifyThemeBrandSyncRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Direct Shopify theme sync is disabled. "
            "Use template ZIP export and extension-based rollout for storefront changes."
        ),
    )


@router.post(
    "/{client_id}/shopify/theme/brand/audit",
    response_model=ShopifyThemeBrandAuditResponse,
)
def audit_client_shopify_theme_brand_route(
    client_id: str,
    payload: ShopifyThemeBrandAuditRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    client = _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = payload.shopDomain or selected_shop_domain
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=effective_shop_domain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )
    _require_internal_install_for_advanced_shopify(
        status_payload=status_payload,
        action_label="theme audit",
    )

    requested_design_system_id = payload.designSystemId.strip() if payload.designSystemId else None
    resolved_design_system_id = requested_design_system_id or (
        str(client.design_system_id) if client.design_system_id else None
    )
    if not resolved_design_system_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No design system selected for Shopify theme audit. "
                "Set a workspace default design system or provide designSystemId."
            ),
        )

    design_system_repo = DesignSystemsRepository(session)
    design_system = design_system_repo.get(
        org_id=auth.org_id,
        design_system_id=resolved_design_system_id,
    )
    if not design_system:
        if requested_design_system_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace default design system was not found.",
        )

    design_system_client_id = str(design_system.client_id) if design_system.client_id else None
    if design_system_client_id and design_system_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Design system must belong to this workspace.",
        )

    try:
        validated_tokens = validate_design_system_tokens(design_system.tokens)
    except DesignSystemGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    css_vars_raw = validated_tokens.get("cssVars")
    if not isinstance(css_vars_raw, dict) or not css_vars_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.cssVars must be a non-empty JSON object.",
        )
    css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars_raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.cssVars keys must be non-empty strings.",
            )
        if not isinstance(raw_value, (str, int, float)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Design system cssVars[{raw_key}] must be a string or number.",
            )
        if isinstance(raw_value, str):
            cleaned_value = raw_value.strip()
            if not cleaned_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Design system cssVars[{raw_key}] must not be an empty string.",
                )
        else:
            cleaned_value = str(raw_value)
        css_vars[raw_key.strip()] = cleaned_value

    data_theme_raw = validated_tokens.get("dataTheme")
    if not isinstance(data_theme_raw, str) or not data_theme_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.dataTheme must be a non-empty string.",
        )
    data_theme = data_theme_raw.strip()

    workspace_name = str(client.name).strip()
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name is required to audit Shopify theme brand assets.",
        )

    audited = audit_client_shopify_theme_brand(
        client_id=client_id,
        workspace_name=workspace_name,
        css_vars=css_vars,
        data_theme=data_theme,
        theme_id=payload.themeId,
        theme_name=payload.themeName,
        shop_domain=effective_shop_domain,
    )

    return ShopifyThemeBrandAuditResponse(
        shopDomain=audited["shopDomain"],
        workspaceName=workspace_name,
        designSystemId=str(design_system.id),
        designSystemName=str(design_system.name),
        themeId=audited["themeId"],
        themeName=audited["themeName"],
        themeRole=audited["themeRole"],
        layoutFilename=audited["layoutFilename"],
        cssFilename=audited["cssFilename"],
        settingsFilename=audited.get("settingsFilename"),
        hasManagedMarkerBlock=audited["hasManagedMarkerBlock"],
        layoutIncludesManagedCssAsset=audited["layoutIncludesManagedCssAsset"],
        managedCssAssetExists=audited["managedCssAssetExists"],
        coverage=audited["coverage"],
        settingsAudit=audited["settingsAudit"],
        isReady=audited["isReady"],
    )


@router.get("/{client_id}/active-product")
def get_active_product(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    pref = session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == auth.org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == auth.user_id,
        )
    )

    active_product: Product | None = None
    if pref and pref.active_product_id:
        active_product = session.scalar(
            select(Product).where(
                Product.org_id == auth.org_id,
                Product.id == pref.active_product_id,
            )
        )
        if not active_product or str(active_product.client_id) != str(client_id):
            pref.active_product_id = None
            pref.updated_at = func.now()
            session.commit()
            active_product = None

    if not active_product:
        active_product = session.scalar(
            select(Product)
            .where(Product.org_id == auth.org_id, Product.client_id == client_id)
            .order_by(Product.created_at.desc(), Product.id.asc())
            .limit(1)
        )
        if not active_product:
            return {"active_product_id": None, "active_product": None}

        if pref:
            pref.active_product_id = active_product.id
            pref.updated_at = func.now()
        else:
            session.add(
                ClientUserPreference(
                    org_id=auth.org_id,
                    client_id=client_id,
                    user_external_id=auth.user_id,
                    active_product_id=active_product.id,
                )
            )
        session.commit()

    return {
        "active_product_id": str(active_product.id),
        "active_product": _serialize_active_product(active_product),
    }


@router.put("/{client_id}/active-product")
def set_active_product(
    client_id: str,
    payload: ActiveProductUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    product = session.scalar(
        select(Product).where(
            Product.org_id == auth.org_id,
            Product.id == payload.product_id,
        )
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if str(product.client_id) != str(client_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product must belong to the selected client.",
        )

    pref = session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == auth.org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == auth.user_id,
        )
    )
    if pref:
        pref.active_product_id = product.id
        pref.updated_at = func.now()
    else:
        session.add(
            ClientUserPreference(
                org_id=auth.org_id,
                client_id=client_id,
                user_external_id=auth.user_id,
                active_product_id=product.id,
            )
        )
    session.commit()

    return {
        "active_product_id": str(product.id),
        "active_product": _serialize_active_product(product),
    }


@router.patch("/{client_id}")
def update_client(
    client_id: str,
    payload: ClientUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    fields: dict[str, object] = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.industry is not None:
        fields["industry"] = payload.industry
    if "designSystemId" in payload.model_fields_set:
        design_system_id = payload.designSystemId or None
        if design_system_id:
            design_system_repo = DesignSystemsRepository(session)
            design_system = design_system_repo.get(
                org_id=auth.org_id, design_system_id=design_system_id
            )
            if not design_system:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Design system not found",
                )
            if design_system.client_id and str(design_system.client_id) != str(client_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Design system must belong to the same client",
                )
        fields["design_system_id"] = design_system_id
    if "strategyV2Enabled" in payload.model_fields_set and payload.strategyV2Enabled is not None:
        fields["strategy_v2_enabled"] = payload.strategyV2Enabled

    updated = repo.update(org_id=auth.org_id, client_id=client_id, **fields)
    return jsonable_encoder(updated)


@router.delete("/{client_id}")
def delete_client(
    client_id: str,
    payload: ClientDeleteRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Deletion not confirmed"
        )

    if payload.confirm_name != client.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation name does not match workspace name",
        )

    deleted = repo.delete(org_id=auth.org_id, client_id=client_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete client",
        )

    return {"ok": True}


@router.post("/{client_id}/onboarding")
async def start_client_onboarding(
    client_id: str,
    payload: OnboardingStartRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.business_type != "new":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Existing customer onboarding is not supported yet.",
        )
    onboarding_repo = OnboardingPayloadsRepository(session)
    clients_repo = ClientsRepository(session)
    products_repo = ProductsRepository(session)
    offers_repo = ProductOffersRepository(session)
    variants_repo = ProductVariantsRepository(session)

    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if not is_strategy_v2_enabled(session=session, org_id=auth.org_id, client_id=client_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Strategy V2 is disabled for this tenant/client. Enable strategy_v2_enabled before onboarding.",
        )

    product_fields: dict[str, object] = {"title": payload.product_name}
    if payload.product_description is not None:
        product_fields["description"] = payload.product_description
    normalized_product_type = canonical_product_type(payload.product_type)
    if not normalized_product_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_type is required.",
        )
    product_fields["product_type"] = normalized_product_type
    if payload.primary_benefits is not None:
        product_fields["primary_benefits"] = payload.primary_benefits
    if payload.feature_bullets is not None:
        product_fields["feature_bullets"] = payload.feature_bullets
    if payload.guarantee_text is not None:
        product_fields["guarantee_text"] = payload.guarantee_text
    if payload.disclaimers is not None:
        product_fields["disclaimers"] = payload.disclaimers

    product = products_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        **product_fields,
    )

    offer_fields: dict[str, object] = {
        "name": product.title,
        "business_model": payload.business_model.strip(),
    }
    if payload.product_description is not None:
        offer_fields["description"] = payload.product_description
    if payload.primary_benefits:
        offer_fields["differentiation_bullets"] = payload.primary_benefits
    if payload.guarantee_text is not None:
        offer_fields["guarantee_text"] = payload.guarantee_text

    default_offer = offers_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        **offer_fields,
    )
    price_cents, currency = parse_price_to_cents_and_currency(
        price_text=payload.price,
        context="Onboarding",
    )
    variants_repo.create(
        product_id=str(product.id),
        offer_id=str(default_offer.id),
        title=product.title,
        price=price_cents,
        currency=currency,
    )

    payload_data = payload.model_dump()
    payload_data["product_type"] = normalized_product_type
    payload_data["product_id"] = str(product.id)
    payload_data["default_offer_id"] = str(default_offer.id)

    onboarding_payload = onboarding_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        data=payload_data,
    )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        ClientOnboardingWorkflow.run,
        ClientOnboardingInput(
            org_id=auth.org_id,
            client_id=client_id,
            onboarding_payload_id=str(onboarding_payload.id),
            product_id=str(product.id),
            business_model=payload.business_model.strip(),
            funnel_position=payload.funnel_position.strip(),
            target_platforms=list(payload.target_platforms),
            target_regions=list(payload.target_regions),
            existing_proof_assets=list(payload.existing_proof_assets),
            brand_voice_notes=payload.brand_voice_notes.strip(),
            compliance_notes=payload.compliance_notes.strip() if isinstance(payload.compliance_notes, str) and payload.compliance_notes.strip() else None,
        ),
        id=f"client-onboarding-{auth.org_id}-{client_id}-{onboarding_payload.id}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    workflows_repo = WorkflowsRepository(session)
    run = workflows_repo.create_run(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        campaign_id=None,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="client_onboarding",
    )
    workflows_repo.log_activity(
        workflow_run_id=str(run.id),
        step="client_onboarding",
        status="started",
        payload_in={
            "client_id": client_id,
            "product_id": str(product.id),
            "onboarding_payload_id": str(onboarding_payload.id),
        },
    )

    return {
        "workflow_run_id": str(run.id),
        "temporal_workflow_id": handle.id,
        "product_id": str(product.id),
        "product_name": product.title,
        "default_offer_id": str(default_offer.id),
    }


@router.post("/{client_id}/intent")
async def start_campaign_intent(
    client_id: str,
    payload: CampaignIntentRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    product_id = payload.productId
    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if str(product.client_id) != client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="productId does not belong to the selected workspace.",
        )
    if not payload.channels or not all(
        isinstance(ch, str) and ch.strip() for ch in payload.channels
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channels must include at least one non-empty value.",
        )
    if not payload.assetBriefTypes or not all(
        isinstance(t, str) and t.strip() for t in payload.assetBriefTypes
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="assetBriefTypes must include at least one non-empty value.",
        )

    strategy_v2_required = is_strategy_v2_enabled(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
    )
    artifacts_repo = ArtifactsRepository(session)
    wf_repo = WorkflowsRepository(session)
    if not strategy_v2_required:
        canon = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=ArtifactTypeEnum.client_canon,
        )
        metric = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=ArtifactTypeEnum.metric_schema,
        )
        if not canon or not metric:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complete client onboarding (canon + metric schema) before starting campaign intent.",
            )
    try:
        require_strategy_v2_outputs_if_enabled(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        CampaignIntentWorkflow.run,
        CampaignIntentInput(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_name=payload.campaignName,
            channels=payload.channels,
            asset_brief_types=payload.assetBriefTypes,
            goal_description=payload.goalDescription,
            objective_type=payload.objectiveType,
            numeric_target=payload.numericTarget,
            baseline=payload.baseline,
            timeframe_days=payload.timeframeDays,
            budget_min=payload.budgetMin,
            budget_max=payload.budgetMax,
        ),
        id=f"campaign-intent-{auth.org_id}-{client_id}-{uuid4()}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    run = wf_repo.create_run(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=None,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="campaign_intent",
    )
    wf_repo.log_activity(
        workflow_run_id=str(run.id),
        step="campaign_intent",
        status="started",
        payload_in={
            "client_id": client_id,
            "product_id": product_id,
            "campaign_name": payload.campaignName,
        },
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}
