from __future__ import annotations

import ast
import base64
import json
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum
from app.db.models import (
    Asset,
    Funnel,
    FunnelPage,
    FunnelPageVersion,
    Product,
    ProductOffer,
    ProductVariant,
)
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository
from app.llm.client import LLMClient, LLMGenerationParams
from app.services.claude_files import CLAUDE_DEFAULT_MODEL, build_document_blocks, call_claude_structured_message
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnels import default_puck_data
from app.services.funnels import _walk_json as walk_json  # reuse internal helper
from app.services.funnels import create_funnel_image_asset, create_funnel_unsplash_asset
from app.services.funnel_templates import get_funnel_template
from app.services.media_storage import MediaStorage


_ASSISTANT_MESSAGE_MAX_CHARS = 600
_REPAIR_PREVIOUS_RESPONSE_MAX_CHARS = 4000
_CLAUDE_MAX_OUTPUT_TOKENS = 64000
_MAX_AI_ATTACHMENTS = 8
_MAX_PAGE_IMAGE_GENERATIONS = 50
_VISION_ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}


class AiAttachmentError(Exception):
    pass


_CONFIG_JSON_IMAGE_KEYS = ("configJson", "feedImagesJson")
_PLACEHOLDER_SRC_MARKERS = ("/assets/ph-", "/assets/placeholder")


@dataclass
class _ConfigJsonContext:
    component_type: str
    props: dict[str, Any]
    key: str
    parsed: Any
    dirty: bool = False


def _walk_json_with_path(node: Any, path: str) -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else key
            yield from _walk_json_with_path(value, next_path)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            next_path = f"{path}[{idx}]"
            yield from _walk_json_with_path(item, next_path)


def _count_component_types(puck_data: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        if not isinstance(comp_type, str) or not comp_type:
            continue
        counts[comp_type] = counts.get(comp_type, 0) + 1
    return counts


def _required_template_component_types(
    base_puck_data: dict[str, Any],
    *,
    template_kind: str | None,
) -> set[str]:
    if template_kind == "sales-pdp":
        candidates = {
            "SalesPdpPage",
            "SalesPdpFaq",
            "SalesPdpReviews",
            "SalesPdpReviewWall",
            "SalesPdpReviewSlider",
            "SalesPdpTemplate",
        }
    elif template_kind == "pre-sales-listicle":
        candidates = {
            "PreSalesPage",
            "PreSalesReviews",
            "PreSalesReviewWall",
            "PreSalesTemplate",
        }
    else:
        return set()

    base_counts = _count_component_types(base_puck_data)
    return {comp_type for comp_type in candidates if base_counts.get(comp_type, 0) > 0}


def _infer_template_component_kind(template_kind: str | None, base_puck_data: dict[str, Any]) -> str | None:
    """
    Some template ids have multiple underlying implementations (e.g. older templates built from
    SalesPdp*/PreSales* blocks vs newer templates built purely from primitive blocks).

    We only enable the specialized "template component" guidance when the base page actually
    contains those template-specific blocks.
    """

    if not template_kind:
        return None
    base_counts = _count_component_types(base_puck_data)
    if template_kind == "sales-pdp":
        if base_counts.get("SalesPdpPage", 0) > 0 or base_counts.get("SalesPdpTemplate", 0) > 0:
            return "sales-pdp"
        return None
    if template_kind == "pre-sales-listicle":
        if base_counts.get("PreSalesPage", 0) > 0 or base_counts.get("PreSalesTemplate", 0) > 0:
            return "pre-sales-listicle"
        return None
    return None


def _describe_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"bool({value})"
    if isinstance(value, (int, float)):
        return f"number({value})"
    if isinstance(value, str):
        return f"string({value[:120]!r})"
    if isinstance(value, list):
        return f"list(len={len(value)})"
    if isinstance(value, dict):
        keys = list(value.keys())[:12]
        return f"object(keys={keys})"
    return f"{type(value).__name__}({str(value)[:120]!r})"


def _validate_pre_sales_listicle_component_configs(puck_data: dict[str, Any]) -> None:
    """
    Ensure PreSales* blocks won't crash the editor/runtime due to basic shape issues.

    This is intentionally minimal: validate container types + a few required keys that are
    directly accessed by the frontend components.
    """

    supported_types = {
        "PreSalesTemplate",
        "PreSalesPage",
        "PreSalesHero",
        "PreSalesReasons",
        "PreSalesReviews",
        "PreSalesMarquee",
        "PreSalesPitch",
        "PreSalesReviewWall",
        "PreSalesFooter",
        "PreSalesFloatingCta",
    }

    def load_config(props: dict[str, Any]) -> tuple[Any, str] | None:
        raw_json = props.get("configJson")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                return json.loads(raw_json), "configJson"
            except json.JSONDecodeError as exc:
                raise ValueError(f"configJson must be valid JSON: {exc}") from exc
        if "config" in props and props.get("config") is not None:
            return props.get("config"), "config"
        return None

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        if comp_type not in supported_types:
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        loaded = load_config(props)
        if not loaded:
            continue
        config, source = loaded
        block_id = props.get("id")
        id_suffix = f" (id={block_id})" if isinstance(block_id, str) and block_id else ""

        if comp_type == "PreSalesHero":
            if not isinstance(config, dict):
                raise ValueError(
                    f"PreSalesHero.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            hero = config.get("hero")
            badges = config.get("badges")
            if not isinstance(hero, dict) or not isinstance(hero.get("title"), str) or not isinstance(hero.get("subtitle"), str):
                raise ValueError(
                    f"PreSalesHero.{source}.hero must be an object with string title/subtitle{id_suffix}. Received {_describe_value(hero)}."
                )
            if not isinstance(badges, list):
                raise ValueError(
                    f"PreSalesHero.{source}.badges must be a list{id_suffix}. Received {_describe_value(badges)}."
                )
        elif comp_type == "PreSalesReasons":
            if not isinstance(config, list):
                raise ValueError(
                    f"PreSalesReasons.{source} must be a JSON array{id_suffix}. Received {_describe_value(config)}."
                )
        elif comp_type == "PreSalesMarquee":
            if not isinstance(config, list):
                raise ValueError(
                    f"PreSalesMarquee.{source} must be a JSON array{id_suffix}. Received {_describe_value(config)}."
                )
        elif comp_type == "PreSalesPitch":
            if not isinstance(config, dict):
                raise ValueError(
                    f"PreSalesPitch.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            bullets = config.get("bullets")
            image = config.get("image")
            if not isinstance(bullets, list):
                raise ValueError(
                    f"PreSalesPitch.{source}.bullets must be a list{id_suffix}. Received {_describe_value(bullets)}."
                )
            if not isinstance(image, dict) or not isinstance(image.get("alt"), str):
                raise ValueError(
                    f"PreSalesPitch.{source}.image must be an object with string alt{id_suffix}. Received {_describe_value(image)}."
                )
        elif comp_type == "PreSalesReviews":
            if not isinstance(config, dict):
                raise ValueError(
                    f"PreSalesReviews.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            slides = config.get("slides")
            if not isinstance(slides, list):
                raise ValueError(
                    f"PreSalesReviews.{source}.slides must be a list{id_suffix}. Received {_describe_value(slides)}."
                )
            for idx, slide in enumerate(slides):
                if not isinstance(slide, dict):
                    raise ValueError(
                        f"PreSalesReviews.{source}.slides[{idx}] must be an object{id_suffix}. Received {_describe_value(slide)}."
                    )
                images = slide.get("images")
                if not isinstance(images, list) or not images:
                    raise ValueError(
                        f"PreSalesReviews.{source}.slides[{idx}].images must be a non-empty list{id_suffix}. "
                        f"Received {_describe_value(images)}."
                    )
                for jdx, img in enumerate(images):
                    if not isinstance(img, dict) or not isinstance(img.get("alt"), str) or not img.get("alt"):
                        raise ValueError(
                            f"PreSalesReviews.{source}.slides[{idx}].images[{jdx}] must be an object with string alt{id_suffix}. "
                            f"Received {_describe_value(img)}."
                        )
        elif comp_type == "PreSalesReviewWall":
            if not isinstance(config, dict):
                raise ValueError(
                    f"PreSalesReviewWall.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            columns = config.get("columns")
            if not isinstance(columns, list):
                raise ValueError(
                    f"PreSalesReviewWall.{source}.columns must be a list{id_suffix}. Received {_describe_value(columns)}."
                )
        elif comp_type == "PreSalesFooter":
            if not isinstance(config, dict):
                raise ValueError(
                    f"PreSalesFooter.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            logo = config.get("logo")
            if not isinstance(logo, dict) or not isinstance(logo.get("alt"), str):
                raise ValueError(
                    f"PreSalesFooter.{source}.logo must be an object with string alt{id_suffix}. Received {_describe_value(logo)}."
                )
        elif comp_type == "PreSalesFloatingCta":
            if not isinstance(config, dict):
                raise ValueError(
                    f"PreSalesFloatingCta.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            if not isinstance(config.get("label"), str):
                raise ValueError(
                    f"PreSalesFloatingCta.{source}.label must be a string{id_suffix}. Received {_describe_value(config.get('label'))}."
                )
        elif comp_type == "PreSalesTemplate":
            if not isinstance(config, dict):
                raise ValueError(
                    f"PreSalesTemplate.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            # Minimal keys that are directly dereferenced by the frontend template.
            required_keys = ("hero", "badges", "reasons", "marquee", "pitch", "reviews", "reviewsWall", "footer", "floatingCta")
            missing = [k for k in required_keys if k not in config]
            if missing:
                missing_str = ", ".join(missing)
                raise ValueError(f"PreSalesTemplate.{source} missing required keys: {missing_str}{id_suffix}.")


def _extract_pre_sales_hero_badges(tree: Any) -> list[dict[str, Any]] | None:
    for obj in walk_json(tree):
        if not isinstance(obj, dict) or obj.get("type") != "PreSalesHero":
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        config = props.get("config")
        if isinstance(config, dict):
            badges = config.get("badges")
            if isinstance(badges, list):
                return badges
        raw_config_json = props.get("configJson")
        if isinstance(raw_config_json, str) and raw_config_json.strip():
            try:
                parsed = json.loads(raw_config_json)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                badges = parsed.get("badges")
                if isinstance(badges, list):
                    return badges
    return None


def _repair_pre_sales_badge_icons(
    *,
    badges: list[Any],
    fallback_badges: list[dict[str, Any]],
) -> bool:
    changed = False
    for idx, badge in enumerate(badges):
        if not isinstance(badge, dict):
            continue
        if idx >= len(fallback_badges):
            continue
        fallback = fallback_badges[idx]
        if not isinstance(fallback, dict):
            continue
        has_icon_src = isinstance(badge.get("iconSrc"), str) and bool(badge.get("iconSrc").strip())
        has_icon_asset = isinstance(badge.get("iconAssetPublicId"), str) and bool(
            badge.get("iconAssetPublicId").strip()
        )
        if not has_icon_src and not has_icon_asset:
            fallback_icon_asset = fallback.get("iconAssetPublicId")
            if isinstance(fallback_icon_asset, str) and fallback_icon_asset.strip():
                badge["iconAssetPublicId"] = fallback_icon_asset.strip()
                changed = True
            fallback_icon_src = fallback.get("iconSrc")
            if isinstance(fallback_icon_src, str) and fallback_icon_src.strip():
                badge["iconSrc"] = fallback_icon_src.strip()
                changed = True
        icon_alt = badge.get("iconAlt")
        if not isinstance(icon_alt, str) or not icon_alt.strip():
            fallback_icon_alt = fallback.get("iconAlt")
            if isinstance(fallback_icon_alt, str) and fallback_icon_alt.strip():
                badge["iconAlt"] = fallback_icon_alt.strip()
                changed = True
    return changed


def _ensure_pre_sales_badge_icons(
    *,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
    fallback_puck_data: dict[str, Any] | None,
) -> None:
    if not fallback_puck_data:
        return
    fallback_badges = _extract_pre_sales_hero_badges(fallback_puck_data)
    if not fallback_badges:
        return
    current_badges = _extract_pre_sales_hero_badges(puck_data)
    if current_badges:
        _repair_pre_sales_badge_icons(badges=current_badges, fallback_badges=fallback_badges)
    for ctx in config_contexts:
        if ctx.component_type != "PreSalesHero":
            continue
        if not isinstance(ctx.parsed, dict):
            continue
        badges = ctx.parsed.get("badges")
        if not isinstance(badges, list):
            continue
        if _repair_pre_sales_badge_icons(badges=badges, fallback_badges=fallback_badges):
            ctx.dirty = True


def _validate_sales_pdp_component_configs(puck_data: dict[str, Any]) -> None:
    """
    Ensure SalesPdp* blocks won't crash the editor/runtime due to basic shape issues.

    This is intentionally minimal: validate container types + a few required keys that are
    directly accessed by the frontend components.
    """

    supported_types = {
        "SalesPdpTemplate",
        "SalesPdpPage",
        "SalesPdpHeader",
        "SalesPdpHero",
        "SalesPdpVideos",
        "SalesPdpMarquee",
        "SalesPdpStoryProblem",
        "SalesPdpStorySolution",
        "SalesPdpComparison",
        "SalesPdpGuarantee",
        "SalesPdpFaq",
        "SalesPdpReviews",
        "SalesPdpReviewWall",
        "SalesPdpFooter",
        "SalesPdpReviewSlider",
    }

    def load_config(props: dict[str, Any]) -> tuple[Any, str] | None:
        raw_json = props.get("configJson")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                return json.loads(raw_json), "configJson"
            except json.JSONDecodeError as exc:
                raise ValueError(f"configJson must be valid JSON: {exc}") from exc
        if "config" in props and props.get("config") is not None:
            return props.get("config"), "config"
        return None

    def load_optional_object_prop(
        *,
        props: dict[str, Any],
        object_key: str,
        json_key: str,
        component_type: str,
        id_suffix: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        raw_json = props.get(json_key)
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{component_type}.{json_key} must be valid JSON{id_suffix}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"{component_type}.{json_key} must decode to a JSON object{id_suffix}. "
                    f"Received {_describe_value(parsed)}."
                )
            return parsed, json_key

        value = props.get(object_key)
        if value is None:
            return None, None
        if not isinstance(value, dict):
            raise ValueError(
                f"{component_type}.{object_key} must be a JSON object{id_suffix}. "
                f"Received {_describe_value(value)}."
            )
        return value, object_key

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        if comp_type not in supported_types:
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        loaded = load_config(props)
        if not loaded:
            continue
        config, source = loaded
        block_id = props.get("id")
        id_suffix = f" (id={block_id})" if isinstance(block_id, str) and block_id else ""

        if comp_type == "SalesPdpHeader":
            if not isinstance(config, dict):
                raise ValueError(
                    f"SalesPdpHeader.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            logo = config.get("logo")
            nav = config.get("nav")
            cta = config.get("cta")
            if not isinstance(logo, dict) or not isinstance(logo.get("alt"), str) or not logo.get("alt"):
                raise ValueError(
                    f"SalesPdpHeader.{source}.logo must be an object with string alt{id_suffix}. Received {_describe_value(logo)}."
                )
            if not isinstance(nav, list):
                raise ValueError(
                    f"SalesPdpHeader.{source}.nav must be a list{id_suffix}. Received {_describe_value(nav)}."
                )
            if not isinstance(cta, dict) or not isinstance(cta.get("label"), str) or not isinstance(cta.get("href"), str):
                raise ValueError(
                    f"SalesPdpHeader.{source}.cta must be an object with string label/href{id_suffix}. Received {_describe_value(cta)}."
                )

        elif comp_type == "SalesPdpReviews":
            if not isinstance(config, dict):
                raise ValueError(
                    f"SalesPdpReviews.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            if not isinstance(config.get("id"), str) or not config.get("id"):
                raise ValueError(
                    f"SalesPdpReviews.{source}.id must be a string{id_suffix}. Received {_describe_value(config.get('id'))}."
                )
            data = config.get("data")
            if not isinstance(data, dict):
                raise ValueError(
                    f"SalesPdpReviews.{source}.data must be a JSON object{id_suffix}. Received {_describe_value(data)}."
                )

        elif comp_type == "SalesPdpMarquee":
            if not isinstance(config, dict):
                raise ValueError(
                    f"SalesPdpMarquee.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            items = config.get("items")
            if not isinstance(items, list):
                raise ValueError(
                    f"SalesPdpMarquee.{source}.items must be a list{id_suffix}. Received {_describe_value(items)}."
                )

        elif comp_type == "SalesPdpFaq":
            if not isinstance(config, dict):
                raise ValueError(
                    f"SalesPdpFaq.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            faq_id = config.get("id")
            title = config.get("title")
            items = config.get("items")
            if not isinstance(faq_id, str) or not faq_id:
                raise ValueError(
                    f"SalesPdpFaq.{source}.id must be a string{id_suffix}. Received {_describe_value(faq_id)}."
                )
            if not isinstance(title, str) or not title.strip():
                raise ValueError(
                    f"SalesPdpFaq.{source}.title must be a string{id_suffix}. Received {_describe_value(title)}."
                )
            if not isinstance(items, list):
                raise ValueError(
                    f"SalesPdpFaq.{source}.items must be a list{id_suffix}. Received {_describe_value(items)}."
                )
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"SalesPdpFaq.{source}.items[{idx}] must be a JSON object{id_suffix}. Received {_describe_value(item)}."
                    )
                question = item.get("question")
                answer = item.get("answer")
                if not isinstance(question, str) or not question.strip():
                    raise ValueError(
                        f"SalesPdpFaq.{source}.items[{idx}].question must be a non-empty string{id_suffix}. "
                        f"Received {_describe_value(question)}."
                    )
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError(
                        f"SalesPdpFaq.{source}.items[{idx}].answer must be a non-empty string{id_suffix}. "
                        f"Received {_describe_value(answer)}."
                    )

        elif comp_type == "SalesPdpFooter":
            if not isinstance(config, dict):
                raise ValueError(
                    f"SalesPdpFooter.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            logo = config.get("logo")
            if not isinstance(logo, dict) or not isinstance(logo.get("alt"), str) or not logo.get("alt"):
                raise ValueError(
                    f"SalesPdpFooter.{source}.logo must be an object with string alt{id_suffix}. Received {_describe_value(logo)}."
                )
            copyright_text = config.get("copyright")
            if not isinstance(copyright_text, str):
                raise ValueError(
                    f"SalesPdpFooter.{source}.copyright must be a string{id_suffix}. Received {_describe_value(copyright_text)}."
                )

        elif comp_type == "SalesPdpReviewSlider":
            if not isinstance(config, dict):
                raise ValueError(
                    f"SalesPdpReviewSlider.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            toggle = config.get("toggle")
            slides = config.get("slides")
            if not isinstance(config.get("title"), str) or not isinstance(config.get("body"), str) or not isinstance(config.get("hint"), str):
                raise ValueError(
                    f"SalesPdpReviewSlider.{source} must include string title/body/hint{id_suffix}. Received {_describe_value(config)}."
                )
            if not isinstance(toggle, dict) or not isinstance(toggle.get("auto"), str) or not isinstance(toggle.get("manual"), str):
                raise ValueError(
                    f"SalesPdpReviewSlider.{source}.toggle must be an object with string auto/manual{id_suffix}. Received {_describe_value(toggle)}."
                )
            if not isinstance(slides, list) or not slides:
                raise ValueError(
                    f"SalesPdpReviewSlider.{source}.slides must be a non-empty list{id_suffix}. Received {_describe_value(slides)}."
                )
            for idx, slide in enumerate(slides):
                if not isinstance(slide, dict) or not isinstance(slide.get("alt"), str) or not slide.get("alt"):
                    raise ValueError(
                        f"SalesPdpReviewSlider.{source}.slides[{idx}] must be an image object with string alt{id_suffix}. "
                        f"Received {_describe_value(slide)}."
                    )

        elif comp_type == "SalesPdpHero":
            if not isinstance(config, dict):
                raise ValueError(
                    f"SalesPdpHero.{source} must be a JSON object{id_suffix}. Received {_describe_value(config)}."
                )
            header = config.get("header")
            gallery = config.get("gallery")
            purchase = config.get("purchase")
            if not isinstance(header, dict) or not isinstance(header.get("logo"), dict):
                raise ValueError(
                    f"SalesPdpHero.{source}.header must be an object{id_suffix}. Received {_describe_value(header)}."
                )
            if not isinstance(gallery, dict):
                raise ValueError(
                    f"SalesPdpHero.{source}.gallery must be an object{id_suffix}. Received {_describe_value(gallery)}."
                )
            free_gifts = gallery.get("freeGifts")
            if not isinstance(free_gifts, dict):
                raise ValueError(
                    f"SalesPdpHero.{source}.gallery.freeGifts must be an object{id_suffix}. "
                    f"Received {_describe_value(free_gifts)}."
                )
            icon = free_gifts.get("icon")
            if not isinstance(icon, dict) or not isinstance(icon.get("alt"), str) or not icon.get("alt"):
                raise ValueError(
                    f"SalesPdpHero.{source}.gallery.freeGifts.icon must be an object with string alt{id_suffix}. "
                    f"Received {_describe_value(icon)}."
                )
            for key in ("title", "body", "ctaLabel"):
                if not isinstance(free_gifts.get(key), str) or not free_gifts.get(key):
                    raise ValueError(
                        f"SalesPdpHero.{source}.gallery.freeGifts.{key} must be a string{id_suffix}. "
                        f"Received {_describe_value(free_gifts.get(key))}."
                    )
            slides = gallery.get("slides") if isinstance(gallery, dict) else None
            if not isinstance(slides, list) or not slides:
                raise ValueError(
                    f"SalesPdpHero.{source}.gallery.slides must be a non-empty list{id_suffix}. Received {_describe_value(slides)}."
                )
            for idx, slide in enumerate(slides):
                if not isinstance(slide, dict) or not isinstance(slide.get("alt"), str) or not slide.get("alt"):
                    raise ValueError(
                        f"SalesPdpHero.{source}.gallery.slides[{idx}] must be an image object with string alt{id_suffix}. "
                        f"Received {_describe_value(slide)}."
                    )
            if not isinstance(purchase, dict):
                raise ValueError(
                    f"SalesPdpHero.{source}.purchase must be an object{id_suffix}. Received {_describe_value(purchase)}."
                )
            if not isinstance(purchase.get("title"), str):
                raise ValueError(
                    f"SalesPdpHero.{source}.purchase.title must be a string{id_suffix}. Received {_describe_value(purchase.get('title'))}."
                )
            for key in ("faqPills", "benefits"):
                value = purchase.get(key)
                if not isinstance(value, list):
                    raise ValueError(
                        f"SalesPdpHero.{source}.purchase.{key} must be a list{id_suffix}. Received {_describe_value(value)}."
                    )
            size = purchase.get("size")
            color = purchase.get("color")
            offer = purchase.get("offer")
            cta = purchase.get("cta")
            if not isinstance(size, dict) or not isinstance(size.get("options"), list) or not size.get("options"):
                raise ValueError(
                    f"SalesPdpHero.{source}.purchase.size.options must be a non-empty list{id_suffix}. Received {_describe_value(size)}."
                )
            if not isinstance(color, dict) or not isinstance(color.get("options"), list) or not color.get("options"):
                raise ValueError(
                    f"SalesPdpHero.{source}.purchase.color.options must be a non-empty list{id_suffix}. Received {_describe_value(color)}."
                )
            if not isinstance(offer, dict) or not isinstance(offer.get("options"), list) or not offer.get("options"):
                raise ValueError(
                    f"SalesPdpHero.{source}.purchase.offer.options must be a non-empty list{id_suffix}. Received {_describe_value(offer)}."
                )
            if not isinstance(cta, dict) or not isinstance(cta.get("labelTemplate"), str):
                raise ValueError(
                    f"SalesPdpHero.{source}.purchase.cta.labelTemplate must be a string{id_suffix}. Received {_describe_value(cta)}."
                )

            size_options = size.get("options") if isinstance(size, dict) else None
            if isinstance(size_options, list):
                for idx, opt in enumerate(size_options):
                    if not isinstance(opt, dict) or not isinstance(opt.get("id"), str) or not isinstance(opt.get("label"), str):
                        raise ValueError(
                            f"SalesPdpHero.{source}.purchase.size.options[{idx}] must be an object with string id/label{id_suffix}. "
                            f"Received {_describe_value(opt)}."
                        )

            color_options = color.get("options") if isinstance(color, dict) else None
            if isinstance(color_options, list):
                for idx, opt in enumerate(color_options):
                    if not isinstance(opt, dict) or not isinstance(opt.get("id"), str) or not isinstance(opt.get("label"), str):
                        raise ValueError(
                            f"SalesPdpHero.{source}.purchase.color.options[{idx}] must be an object with string id/label{id_suffix}. "
                            f"Received {_describe_value(opt)}."
                        )

            offer_options = offer.get("options") if isinstance(offer, dict) else None
            if isinstance(offer_options, list):
                for idx, opt in enumerate(offer_options):
                    if not isinstance(opt, dict):
                        raise ValueError(
                            f"SalesPdpHero.{source}.purchase.offer.options[{idx}] must be an object{id_suffix}. Received {_describe_value(opt)}."
                        )
                    if not isinstance(opt.get("id"), str) or not isinstance(opt.get("title"), str):
                        raise ValueError(
                            f"SalesPdpHero.{source}.purchase.offer.options[{idx}] must include string id/title{id_suffix}. "
                            f"Received {_describe_value(opt)}."
                        )
                    image = opt.get("image")
                    if not isinstance(image, dict) or not isinstance(image.get("alt"), str) or not image.get("alt"):
                        raise ValueError(
                            f"SalesPdpHero.{source}.purchase.offer.options[{idx}].image must be an object with string alt{id_suffix}. "
                            f"Received {_describe_value(image)}."
                        )
                    price = opt.get("price")
                    if not isinstance(price, (int, float)):
                        raise ValueError(
                            f"SalesPdpHero.{source}.purchase.offer.options[{idx}].price must be a number{id_suffix}. "
                            f"Received {_describe_value(price)}."
                        )

            modals, modals_source = load_optional_object_prop(
                props=props,
                object_key="modals",
                json_key="modalsJson",
                component_type=comp_type,
                id_suffix=id_suffix,
            )
            if modals is None:
                raise ValueError(
                    f"SalesPdpHero.modals/modalsJson is required{id_suffix}. "
                    "This drives the size chart, why bundle, and free gifts dialogs."
                )
            size_chart = modals.get("sizeChart")
            why_bundle = modals.get("whyBundle")
            modal_free_gifts = modals.get("freeGifts")
            if not isinstance(size_chart, dict):
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.sizeChart must be an object{id_suffix}. "
                    f"Received {_describe_value(size_chart)}."
                )
            if not isinstance(why_bundle, dict):
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.whyBundle must be an object{id_suffix}. "
                    f"Received {_describe_value(why_bundle)}."
                )
            if not isinstance(modal_free_gifts, dict):
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.freeGifts must be an object{id_suffix}. "
                    f"Received {_describe_value(modal_free_gifts)}."
                )
            if not isinstance(size_chart.get("title"), str) or not isinstance(size_chart.get("note"), str):
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.sizeChart must include string title/note{id_suffix}. "
                    f"Received {_describe_value(size_chart)}."
                )
            sizes = size_chart.get("sizes")
            if not isinstance(sizes, list) or not sizes:
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.sizeChart.sizes must be a non-empty list{id_suffix}. "
                    f"Received {_describe_value(sizes)}."
                )
            if not isinstance(why_bundle.get("title"), str) or not isinstance(why_bundle.get("body"), str):
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.whyBundle must include string title/body{id_suffix}. "
                    f"Received {_describe_value(why_bundle)}."
                )
            quotes = why_bundle.get("quotes")
            if not isinstance(quotes, list):
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.whyBundle.quotes must be a list{id_suffix}. "
                    f"Received {_describe_value(quotes)}."
                )
            if not isinstance(modal_free_gifts.get("title"), str) or not isinstance(modal_free_gifts.get("body"), str):
                raise ValueError(
                    f"SalesPdpHero.{modals_source}.freeGifts must include string title/body{id_suffix}. "
                    f"Received {_describe_value(modal_free_gifts)}."
                )

def _collect_config_json_contexts_all(puck_data: dict[str, Any]) -> list[_ConfigJsonContext]:
    contexts: list[_ConfigJsonContext] = []
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if not isinstance(comp_type, str) or not isinstance(props, dict):
            continue
        for key in _CONFIG_JSON_IMAGE_KEYS:
            raw = props.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{comp_type}.{key} must be valid JSON: {exc}") from exc
            if not isinstance(parsed, (dict, list)):
                raise ValueError(f"{comp_type}.{key} must be a JSON object or array.")
            contexts.append(_ConfigJsonContext(component_type=comp_type, props=props, key=key, parsed=parsed))
    return contexts


def _sync_config_json_contexts(contexts: list[_ConfigJsonContext]) -> None:
    for ctx in contexts:
        if ctx.dirty:
            ctx.props[ctx.key] = json.dumps(ctx.parsed)
            ctx.dirty = False


def _apply_logo_to_tree(node: Any, *, logo_public_id: str, logo_alt_value: str | None) -> bool:
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "logo" and isinstance(value, dict):
                if value.get("assetPublicId") != logo_public_id:
                    value["assetPublicId"] = logo_public_id
                    changed = True
                if logo_alt_value and value.get("alt") != logo_alt_value:
                    value["alt"] = logo_alt_value
                    changed = True
                continue
            if _apply_logo_to_tree(value, logo_public_id=logo_public_id, logo_alt_value=logo_alt_value):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if _apply_logo_to_tree(item, logo_public_id=logo_public_id, logo_alt_value=logo_alt_value):
                changed = True
    return changed


def _apply_brand_logo_overrides_for_ai(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
    design_system_tokens: dict[str, Any] | None,
) -> None:
    if design_system_tokens is None:
        return
    if not isinstance(design_system_tokens, dict):
        raise ValueError("Design system tokens must be a JSON object to apply brand assets.")
    brand = design_system_tokens.get("brand")
    if brand is None:
        raise ValueError("Design system tokens missing brand configuration for template assets.")
    if not isinstance(brand, dict):
        raise ValueError("Design system brand configuration must be a JSON object.")
    logo_public_id = brand.get("logoAssetPublicId")
    if not isinstance(logo_public_id, str) or not logo_public_id.strip():
        raise ValueError("Design system brand.logoAssetPublicId is required to apply brand assets.")
    logo_public_id = logo_public_id.strip()
    if logo_public_id == "__LOGO_ASSET_PUBLIC_ID__":
        raise ValueError(
            "Design system brand.logoAssetPublicId is a placeholder and must be replaced with a real asset public id."
        )
    assets_repo = AssetsRepository(session)
    asset = assets_repo.get_by_public_id(org_id=org_id, client_id=client_id, public_id=logo_public_id)
    if not asset:
        raise ValueError("Brand logo asset not found for this workspace.")
    logo_alt = brand.get("logoAlt")
    logo_alt_value = logo_alt.strip() if isinstance(logo_alt, str) and logo_alt.strip() else None

    _apply_logo_to_tree(puck_data, logo_public_id=logo_public_id, logo_alt_value=logo_alt_value)
    for ctx in config_contexts:
        if _apply_logo_to_tree(ctx.parsed, logo_public_id=logo_public_id, logo_alt_value=logo_alt_value):
            ctx.dirty = True


_PRODUCT_KEYWORDS = (
    "book",
    "handbook",
    "guide",
    "manual",
    "product",
    "program",
    "service",
    "course",
    "kit",
    "membership",
    "subscription",
)

_BOOK_DEVICE_KEYWORDS = (
    "ipad",
    "iphone",
    "tablet",
    "phone",
    "smartphone",
    "mobile",
    "screen",
    "e-reader",
    "ereader",
    "kindle",
)

_STOCK_SCENE_KEYWORDS = (
    "lifestyle",
    "at home",
    "home setting",
    "kitchen",
    "living room",
    "office",
    "workspace",
    "outdoor",
    "street",
    "city",
    "natural light",
    "candid",
    "authentic",
    "realistic",
    "wellness",
    "portrait",
    "person",
    "woman",
    "man",
    "family",
    "group",
    "background",
    "environment",
)

_AI_GRAPHIC_STYLE_KEYWORDS = (
    "vector",
    "icon",
    "illustration",
    "infographic",
    "diagram",
    "transparent background",
    "flat design",
    "line art",
    "logo",
)

_PRODUCT_EXACTNESS_KEYWORDS = (
    "include the product prominently",
    "product photo",
    "product shot",
    "close-up",
    "close up",
    "studio shot",
    "packaging",
    "hero product",
    "on white background",
    "technical detail",
    "e-commerce",
)

_STOCK_SCENE_COMPLEXITY_KEYWORDS = (
    "concept",
    "tracking",
    "progress",
    "before and after",
    "split screen",
    "collage",
    "mockup",
    "visible in corner",
)

_STOCK_PROMPT_MAX_WORDS = 16
_STOCK_PROMPT_MAX_COMMAS = 2


def _text_mentions_product(text: str | None) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in _PRODUCT_KEYWORDS)


def _normalize_product_type(product: Product | None) -> str | None:
    if not product or not isinstance(product.product_type, str):
        return None
    normalized = product.product_type.strip().lower()
    return normalized or None


def _product_prompt_mentions_devices(prompt: str | None) -> bool:
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    lowered = prompt.lower()
    return any(keyword in lowered for keyword in _BOOK_DEVICE_KEYWORDS)


def _has_explicit_image_source(obj: dict[str, Any]) -> bool:
    if "imageSource" in obj and obj.get("imageSource") is not None:
        return True
    if "image_source" in obj and obj.get("image_source") is not None:
        return True
    return False


def _prompt_mentions_product_terms(prompt: str) -> bool:
    lowered = prompt.lower()
    for keyword in _PRODUCT_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}s?\b", lowered):
            return True
    return False


def _is_stock_scene_prompt_too_specific(prompt: str) -> bool:
    lowered = prompt.lower()
    words = re.findall(r"[a-z0-9']+", lowered)
    if len(words) > _STOCK_PROMPT_MAX_WORDS:
        return True
    if lowered.count(",") > _STOCK_PROMPT_MAX_COMMAS:
        return True
    if any(keyword in lowered for keyword in _STOCK_SCENE_COMPLEXITY_KEYWORDS):
        return True
    return False


def _recommend_image_source(
    *,
    prompt: str,
    asset_key: str,
    reference_public_id: str | None,
) -> tuple[str, str]:
    if asset_key == "iconAssetPublicId":
        return "ai", "Icon prompts are generated by AI."
    if reference_public_id:
        return "ai", "referenceAssetPublicId requires AI generation."

    lowered = prompt.lower()
    if any(keyword in lowered for keyword in _AI_GRAPHIC_STYLE_KEYWORDS):
        return "ai", "Graphic/icon/diagram prompts are generated by AI."
    if _prompt_mentions_product_terms(prompt) or any(keyword in lowered for keyword in _PRODUCT_EXACTNESS_KEYWORDS):
        return "ai", "Prompt references product-specific visuals."
    if any(keyword in lowered for keyword in _STOCK_SCENE_KEYWORDS):
        if _is_stock_scene_prompt_too_specific(prompt):
            return "ai", "Prompt is too specific for reliable stock search; use AI."
        return "unsplash", "Prompt is a generic stock-suitable scene."
    return "ai", "Default to AI when stock suitability is unclear."


def _book_prompt_suffix() -> str:
    return "Show a physical printed book. No tablets, phones, e-readers, or screens."


def _build_product_context_prompt(text: str, product_type: str | None) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) > 220:
        cleaned = cleaned[:217].rstrip() + "..."
    base = "Contextual lifestyle scene"
    if cleaned:
        base = f"{base} reflecting: {cleaned}"
    base = f"{base}. Include the product prominently."
    if product_type == "book":
        base = f"{base} {_book_prompt_suffix()}"
    return base


def _collect_product_image_public_ids(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
) -> list[str]:
    assets_repo = AssetsRepository(session)
    assets = assets_repo.list(
        org_id=org_id,
        client_id=client_id,
        product_id=str(product.id),
        asset_kind="image",
    )
    ready_assets = [
        asset
        for asset in assets
        if asset.public_id and (asset.file_status is None or asset.file_status == "ready")
    ]

    def is_candidate(asset: Asset) -> bool:
        if asset.file_source and asset.file_source.lower() == "unsplash":
            return False
        tags = [tag.lower() for tag in (asset.tags or [])]
        if any("testimonial" in tag for tag in tags):
            return False
        if any("funnel" == tag or tag.startswith("funnel_") for tag in tags):
            return False
        if any("unsplash" in tag for tag in tags):
            return False
        return True

    candidates = [asset for asset in ready_assets if is_candidate(asset)]

    primary_public_id: str | None = None
    if product.primary_asset_id:
        primary_asset = assets_repo.get(org_id=org_id, asset_id=str(product.primary_asset_id))
        if primary_asset and primary_asset.public_id:
            primary_public_id = str(primary_asset.public_id)

    public_ids: list[str] = []
    if primary_public_id:
        public_ids.append(primary_public_id)
    for asset in candidates:
        public_id = str(asset.public_id)
        if public_id not in public_ids:
            public_ids.append(public_id)

    if not public_ids:
        raise ValueError("No product image assets found for this product.")
    return public_ids


def _assign_product_asset(
    image: dict[str, Any],
    *,
    public_id: str,
    alt: str | None = None,
) -> None:
    image["assetPublicId"] = public_id
    image.pop("referenceAssetPublicId", None)
    image.pop("reference_asset_public_id", None)
    image.pop("prompt", None)
    image.pop("imageSource", None)
    image.pop("image_source", None)
    if alt and not image.get("alt"):
        image["alt"] = alt


def _apply_product_reference_prompt(
    image: dict[str, Any],
    *,
    public_id: str,
    prompt_hint: str,
    product_type: str | None = None,
    alt: str | None = None,
) -> None:
    image["referenceAssetPublicId"] = public_id
    image.pop("assetPublicId", None)
    image["imageSource"] = "ai"
    prompt = image.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        prompt = prompt_hint
    else:
        prompt = prompt.strip()
        if "product" not in prompt.lower():
            prompt = f"{prompt} {prompt_hint}"
    if product_type == "book":
        if _product_prompt_mentions_devices(prompt):
            prompt = prompt_hint
        if "book" not in prompt.lower():
            prompt = f"{prompt} {_book_prompt_suffix()}"
    image["prompt"] = prompt
    if alt and not image.get("alt"):
        image["alt"] = alt


def _apply_product_prompt(
    image: dict[str, Any],
    *,
    prompt_hint: str,
    product_type: str | None = None,
    alt: str | None = None,
) -> None:
    image.pop("referenceAssetPublicId", None)
    image.pop("reference_asset_public_id", None)
    prompt = image.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        prompt = prompt_hint
    else:
        prompt = prompt.strip()
        if "product" not in prompt.lower():
            prompt = f"{prompt} {prompt_hint}"
    if product_type == "book":
        if _product_prompt_mentions_devices(prompt):
            prompt = prompt_hint
        if "book" not in prompt.lower():
            prompt = f"{prompt} {_book_prompt_suffix()}"
    image["prompt"] = prompt
    if alt and not image.get("alt"):
        image["alt"] = alt


def _ensure_flat_vector_icon_prompts(
    *,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
) -> None:
    def update_tree(tree: Any) -> bool:
        changed = False
        for _, obj in _walk_json_with_path(tree, "root"):
            if not isinstance(obj, dict):
                continue
            if _is_testimonial_image(obj):
                continue
            asset_key = _resolve_image_asset_key(obj)
            if asset_key != "iconAssetPublicId":
                continue
            prompt = obj.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            lowered = prompt.lower()
            if "vector" in lowered and "transparent" in lowered:
                continue
            obj["prompt"] = f"{prompt.strip()} Flat vector icon, transparent background."
            changed = True
        return changed

    update_tree(puck_data)
    for ctx in config_contexts:
        if update_tree(ctx.parsed):
            ctx.dirty = True


def _apply_product_image_overrides_for_ai(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
    template_kind: str | None,
    product: Product | None,
    brand_logo_public_id: str | None = None,
) -> None:
    if not template_kind or not product:
        return
    product_type = _normalize_product_type(product)
    product_public_ids = _collect_product_image_public_ids(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product=product,
    )
    if brand_logo_public_id:
        product_public_ids = [pid for pid in product_public_ids if pid != brand_logo_public_id]
        if not product_public_ids:
            raise ValueError("No product image assets available after excluding the brand logo.")

    def iter_component_configs(component_types: set[str]) -> Iterator[tuple[str, Any, _ConfigJsonContext | None]]:
        for ctx in config_contexts:
            if ctx.component_type in component_types and isinstance(ctx.parsed, (dict, list)):
                yield ctx.component_type, ctx.parsed, ctx
        for obj in walk_json(puck_data):
            if not isinstance(obj, dict):
                continue
            comp_type = obj.get("type")
            if comp_type not in component_types:
                continue
            props = obj.get("props")
            if not isinstance(props, dict):
                continue
            config = props.get("config")
            if isinstance(config, (dict, list)):
                yield comp_type, config, None

    if template_kind == "sales-pdp":
        for comp_type, config, ctx in iter_component_configs({"SalesPdpHero", "SalesPdpStoryProblem", "SalesPdpStorySolution"}):
            if comp_type == "SalesPdpHero":
                hero = config
                gallery = hero.get("gallery") if isinstance(hero, dict) else None
                slides = gallery.get("slides") if isinstance(gallery, dict) else None
                if isinstance(slides, list) and slides:
                    for idx, slide in enumerate(slides):
                        if not isinstance(slide, dict):
                            continue
                        _assign_product_asset(
                            slide,
                            public_id=product_public_ids[idx % len(product_public_ids)],
                            alt="Product image",
                        )
                if ctx:
                    ctx.dirty = True
                continue

            if comp_type in {"SalesPdpStoryProblem", "SalesPdpStorySolution"}:
                image = config.get("image")
                if isinstance(image, dict):
                    title = config.get("title") if isinstance(config, dict) else None
                    paragraphs = config.get("paragraphs") if isinstance(config, dict) else None
                    text = " ".join([str(title or ""), " ".join(paragraphs or [])])
                    if comp_type == "SalesPdpStorySolution" or _text_mentions_product(text):
                        prompt_hint = _build_product_context_prompt(text, product_type)
                        _apply_product_reference_prompt(
                            image,
                            public_id=product_public_ids[0],
                            prompt_hint=prompt_hint,
                            product_type=product_type,
                            alt="Product in use",
                        )
                        if ctx:
                            ctx.dirty = True

    if template_kind == "pre-sales-listicle":
        for comp_type, config, ctx in iter_component_configs({"PreSalesHero", "PreSalesReasons", "PreSalesPitch"}):
            if comp_type == "PreSalesHero":
                hero = config.get("hero") if isinstance(config, dict) else None
                media = hero.get("media") if isinstance(hero, dict) else None
                if isinstance(media, dict) and media.get("type") == "image":
                    _assign_product_asset(
                        media,
                        public_id=product_public_ids[0],
                        alt="Product image",
                    )
                    if ctx:
                        ctx.dirty = True
                continue

            if comp_type == "PreSalesReasons":
                if isinstance(config, list):
                    for reason in config:
                        if not isinstance(reason, dict):
                            continue
                        image = reason.get("image")
                        if not isinstance(image, dict):
                            continue
                        image["aspectRatio"] = "1:1"
                        title = reason.get("title")
                        body = reason.get("body")
                        text = " ".join([str(title or ""), str(body or "")]).strip()
                        if _text_mentions_product(text):
                            prompt_hint = _build_product_context_prompt(text, product_type)
                            _apply_product_reference_prompt(
                                image,
                                public_id=product_public_ids[0],
                                prompt_hint=prompt_hint,
                                product_type=product_type,
                                alt="Product in use",
                            )
                    if ctx:
                        ctx.dirty = True
                continue

            if comp_type == "PreSalesPitch":
                image = config.get("image")
                if isinstance(image, dict):
                    title = config.get("title") if isinstance(config, dict) else None
                    bullets = config.get("bullets") if isinstance(config, dict) else None
                    text = " ".join([str(title or ""), " ".join(bullets or [])])
                    if _text_mentions_product(text):
                        prompt_hint = _build_product_context_prompt(text, product_type)
                        _apply_product_reference_prompt(
                            image,
                            public_id=product_public_ids[0],
                            prompt_hint=prompt_hint,
                            product_type=product_type,
                            alt="Product in use",
                        )
                        if ctx:
                            ctx.dirty = True

    # Generic support for templates that use primitive Image components (not SalesPdp*/PreSales*).
    #
    # We only fill obvious "product image" slots so we do not accidentally overwrite icons or other
    # decorative imagery. These slots are expected to have no src/assetPublicId and an alt/id that
    # clearly indicates a product image placeholder.
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict) or obj.get("type") != "Image":
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        if props.get("assetPublicId") or props.get("src") or props.get("referenceAssetPublicId"):
            continue
        alt = props.get("alt")
        cid = props.get("id")
        alt_str = str(alt or "")
        cid_str = str(cid or "")
        looks_like_product_slot = "product" in alt_str.lower() or "hero_image" in cid_str.lower()
        if not looks_like_product_slot:
            continue
        if not product_public_ids:
            raise ValueError("No product image assets available for funnel generation.")
        props["assetPublicId"] = product_public_ids[0]
        if not alt_str.strip():
            props["alt"] = "Product image"
def _get_image_src_for_asset_key(obj: dict[str, Any], asset_key: str) -> Any:
    if asset_key == "iconAssetPublicId":
        return obj.get("iconSrc")
    if asset_key == "posterAssetPublicId":
        return obj.get("poster")
    if asset_key == "thumbAssetPublicId":
        return obj.get("thumbSrc")
    if asset_key == "swatchAssetPublicId":
        return obj.get("swatchImageSrc")
    return obj.get("src")


def _is_placeholder_src(value: str) -> bool:
    lowered = value.strip().lower()
    for marker in _PLACEHOLDER_SRC_MARKERS:
        if marker in lowered:
            return True
    return False


def _is_testimonial_image(obj: dict[str, Any]) -> bool:
    if not isinstance(obj, dict):
        return False
    raw = obj.get("testimonialTemplate") or obj.get("testimonial_template") or obj.get("testimonial_type")
    return isinstance(raw, str) and raw.strip() != ""


def _iter_image_nodes_for_validation(
    tree: Any,
    *,
    base_path: str,
) -> Iterator[tuple[str, dict[str, Any], str]]:
    for path, obj in _walk_json_with_path(tree, base_path):
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "video":
            continue
        if _is_testimonial_image(obj):
            continue
        asset_key = _resolve_image_asset_key(obj)
        if asset_key:
            yield path, obj, asset_key


def _validate_required_template_images(
    *,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
) -> None:
    missing: list[str] = []

    def check_tree(tree: Any, base_path: str) -> None:
        for path, obj, asset_key in _iter_image_nodes_for_validation(tree, base_path=base_path):
            asset_public_id = obj.get(asset_key)
            if asset_public_id:
                continue
            prompt = obj.get("prompt")
            if isinstance(prompt, str) and prompt.strip():
                continue
            src_value = _get_image_src_for_asset_key(obj, asset_key)
            if isinstance(src_value, str) and src_value.strip():
                if _is_placeholder_src(src_value):
                    missing.append(f"{path} (placeholder src={src_value})")
                continue
            missing.append(f"{path} (missing src/prompt)")

    check_tree(puck_data, "puckData")
    for ctx in config_contexts:
        check_tree(ctx.parsed, f"{ctx.component_type}.{ctx.key}")

    if missing:
        sample = "\n".join(f"- {item}" for item in missing[:12])
        raise ValueError(
            "Template image slots are missing prompts or assets. Add a prompt or assetPublicId for each:\n"
            f"{sample}"
        )


def _collect_image_plans(
    *,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []

    def iter_plans(root: Any, base_path: str, *, skip_image_components: bool) -> None:
        skip_props: set[int] = set()
        for path, obj in _walk_json_with_path(root, base_path):
            if not isinstance(obj, dict):
                continue
            if not skip_image_components and obj.get("type") == "Image":
                props = obj.get("props")
                if isinstance(props, dict):
                    skip_props.add(id(props))
                    target = _extract_image_prompt_target(props, "assetPublicId")
                    if target:
                        prompt, reference_public_id, image_source, aspect_ratio = target
                        explicit_source = _has_explicit_image_source(props)
                        suggested_source, suggested_reason = _recommend_image_source(
                            prompt=prompt,
                            asset_key="assetPublicId",
                            reference_public_id=reference_public_id,
                        )
                        plans.append(
                            {
                                "path": f"{path}.props",
                                "assetKey": "assetPublicId",
                                "prompt": prompt,
                                "imageSource": image_source,
                                "referenceAssetPublicId": reference_public_id,
                                "aspectRatio": aspect_ratio,
                                "routingExplicit": explicit_source,
                                "routingSuggestedImageSource": suggested_source,
                                "routingReason": (
                                    f"Explicit imageSource='{image_source}' was provided."
                                    if explicit_source
                                    else suggested_reason
                                ),
                            }
                        )
                continue
            if skip_props and id(obj) in skip_props:
                continue
            if obj.get("type") == "video":
                continue
            if _is_testimonial_image(obj):
                continue
            asset_key = _resolve_image_asset_key(obj)
            if not asset_key:
                continue
            target = _extract_image_prompt_target(obj, asset_key)
            if target:
                prompt, reference_public_id, image_source, aspect_ratio = target
                explicit_source = _has_explicit_image_source(obj)
                suggested_source, suggested_reason = _recommend_image_source(
                    prompt=prompt,
                    asset_key=asset_key,
                    reference_public_id=reference_public_id,
                )
                plans.append(
                    {
                        "path": path,
                        "assetKey": asset_key,
                        "prompt": prompt,
                        "imageSource": image_source,
                        "referenceAssetPublicId": reference_public_id,
                        "aspectRatio": aspect_ratio,
                        "routingExplicit": explicit_source,
                        "routingSuggestedImageSource": suggested_source,
                        "routingReason": (
                            f"Explicit imageSource='{image_source}' was provided."
                            if explicit_source
                            else suggested_reason
                        ),
                    }
                )

    iter_plans(puck_data, "puckData", skip_image_components=False)
    for ctx in config_contexts:
        iter_plans(ctx.parsed, f"{ctx.component_type}.{ctx.key}", skip_image_components=True)
    return plans


def _auto_route_image_sources(
    *,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
) -> int:
    _ = config_contexts
    routed = 0
    for obj, asset_key, prompt, reference_public_id, image_source, _, ctx in _iter_ai_image_prompt_targets(puck_data):
        if _has_explicit_image_source(obj):
            continue
        recommended_source, _ = _recommend_image_source(
            prompt=prompt,
            asset_key=asset_key,
            reference_public_id=reference_public_id,
        )
        if recommended_source == image_source:
            continue
        obj["imageSource"] = recommended_source
        if ctx:
            ctx.dirty = True
        routed += 1
    return routed


def _ensure_unsplash_usage(
    plans: list[dict[str, Any]],
    *,
    puck_data: dict[str, Any],
    config_contexts: list[_ConfigJsonContext],
) -> list[dict[str, Any]]:
    if not plans:
        return plans
    routed = _auto_route_image_sources(puck_data=puck_data, config_contexts=config_contexts)
    if routed == 0:
        return plans
    return _collect_image_plans(puck_data=puck_data, config_contexts=config_contexts)


class _AssistantMessageJsonExtractor:
    """
    Incrementally extracts and JSON-unescapes the value of the top-level "assistantMessage" field
    from a streamed JSON response.
    """

    def __init__(self) -> None:
        self._pattern = '"assistantMessage"'
        self._search_window = ""
        self._state: Literal["search", "after_key", "after_colon", "in_string", "done"] = "search"
        self._escape = False
        self._unicode_remaining = 0
        self._unicode_buffer = ""
        self._pending_high_surrogate: int | None = None

    def feed(self, chunk: str) -> str:
        emitted: list[str] = []

        for ch in chunk:
            if self._state == "done":
                break

            if self._state == "search":
                self._search_window = (self._search_window + ch)[-len(self._pattern) :]
                if self._search_window.endswith(self._pattern):
                    self._state = "after_key"
                continue

            if self._state == "after_key":
                if ch.isspace():
                    continue
                if ch == ":":
                    self._state = "after_colon"
                else:
                    # Unexpected token; reset search.
                    self._state = "search"
                    self._search_window = ""
                continue

            if self._state == "after_colon":
                if ch.isspace():
                    continue
                if ch == '"':
                    self._state = "in_string"
                else:
                    # assistantMessage isn't a string; stop trying to stream it.
                    self._state = "done"
                continue

            if self._state != "in_string":
                continue

            if self._unicode_remaining:
                if ch.lower() in "0123456789abcdef":
                    self._unicode_buffer += ch
                    self._unicode_remaining -= 1
                    if self._unicode_remaining == 0:
                        codepoint = int(self._unicode_buffer, 16)
                        self._unicode_buffer = ""
                        if self._pending_high_surrogate is not None:
                            high = self._pending_high_surrogate
                            self._pending_high_surrogate = None
                            if 0xDC00 <= codepoint <= 0xDFFF:
                                combined = 0x10000 + ((high - 0xD800) << 10) + (codepoint - 0xDC00)
                                emitted.append(chr(combined))
                            else:
                                emitted.append(chr(high))
                                emitted.append(chr(codepoint))
                        elif 0xD800 <= codepoint <= 0xDBFF:
                            self._pending_high_surrogate = codepoint
                        else:
                            emitted.append(chr(codepoint))
                else:
                    # Invalid escape; emit raw and reset.
                    self._unicode_remaining = 0
                    self._unicode_buffer = ""
                    emitted.append(ch)
                continue

            if self._escape:
                self._escape = False
                if ch in ('"', "\\", "/"):
                    emitted.append(ch)
                elif ch == "b":
                    emitted.append("\b")
                elif ch == "f":
                    emitted.append("\f")
                elif ch == "n":
                    emitted.append("\n")
                elif ch == "r":
                    emitted.append("\r")
                elif ch == "t":
                    emitted.append("\t")
                elif ch == "u":
                    self._unicode_remaining = 4
                    self._unicode_buffer = ""
                else:
                    emitted.append(ch)
                continue

            if ch == "\\":
                self._escape = True
                continue
            if ch == '"':
                if self._pending_high_surrogate is not None:
                    emitted.append(chr(self._pending_high_surrogate))
                    self._pending_high_surrogate = None
                self._state = "done"
                continue

            emitted.append(ch)

        return "".join(emitted)


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Model returned empty response")
    for candidate in (text, _repair_json_text(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(candidate)
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        except Exception:
            pass

    start: int | None = None
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = i
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                start = None
                for attempt in (candidate, _repair_json_text(candidate)):
                    if not attempt:
                        continue
                    try:
                        parsed = json.loads(attempt)
                    except Exception:
                        parsed = None
                    if parsed is None:
                        try:
                            parsed = ast.literal_eval(attempt)
                        except Exception:
                            parsed = None
                    if isinstance(parsed, dict):
                        return cast(dict[str, Any], parsed)

    raise ValueError("Model did not return a JSON object")


def _repair_json_text(text: str) -> str:
    if not text:
        return text
    repaired = _strip_trailing_commas(text)
    return _escape_unescaped_control_chars(repaired)


def _strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            out.append(ch)
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            continue

        if ch in ("}", "]"):
            j = len(out) - 1
            while j >= 0 and out[j].isspace():
                j -= 1
            if j >= 0 and out[j] == ",":
                out.pop(j)
        out.append(ch)

    return "".join(out)


def _escape_unescaped_control_chars(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            if ch == "\b":
                out.append("\\b")
                continue
            if ch == "\f":
                out.append("\\f")
                continue
            if ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue

        if ch == '"':
            in_string = True
        out.append(ch)

    return "".join(out)


def _coerce_assistant_message(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "Generated a new draft page."
    message = raw.strip()
    if len(message) <= _ASSISTANT_MESSAGE_MAX_CHARS:
        return message
    truncated = message[:_ASSISTANT_MESSAGE_MAX_CHARS].rstrip()
    if not truncated.endswith("..."):
        truncated = f"{truncated}..."
    return truncated


def _coerce_max_tokens(model: Optional[str], max_tokens: Optional[int]) -> Optional[int]:
    if not model:
        return max_tokens
    lower = model.lower()
    if lower.startswith("claude"):
        if max_tokens is None:
            return _CLAUDE_MAX_OUTPUT_TOKENS
        return min(max_tokens, _CLAUDE_MAX_OUTPUT_TOKENS)
    return max_tokens


def _sanitize_puck_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return default_puck_data()
    root = data.get("root")
    content = data.get("content")
    zones = data.get("zones")
    if not isinstance(root, dict):
        root = {"props": {}}
    elif not isinstance(root.get("props"), dict):
        root["props"] = {}
    if not isinstance(content, list):
        content = []
    if not isinstance(zones, dict):
        zones = {}
    return {"root": root, "content": content, "zones": zones}


def _ensure_block_ids(puck_data: dict[str, Any]) -> None:
    seen: set[str] = set()
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        t = obj.get("type")
        props = obj.get("props")
        if not isinstance(t, str) or not isinstance(props, dict):
            continue
        block_id = props.get("id")
        if not isinstance(block_id, str) or not block_id.strip() or block_id in seen:
            block_id = str(uuid.uuid4())
            props["id"] = block_id
        seen.add(block_id)


def _coerce_puck_data(raw: Any) -> Any:
    if isinstance(raw, str):
        text = raw.strip()
        if text:
            try:
                return _extract_json_object(text)
            except Exception:
                try:
                    return json.loads(text)
                except Exception:
                    try:
                        return json.loads(_repair_json_text(text))
                    except Exception:
                        return raw
    return raw


def _normalize_attachment_list(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    attachments: list[dict[str, Any]] = []
    for item in raw:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        public_id = item.get("publicId") or item.get("public_id")
        if not isinstance(public_id, str) or not public_id.strip():
            continue
        attachments.append(
            {
                "assetId": item.get("assetId") or item.get("asset_id"),
                "publicId": public_id.strip(),
                "filename": item.get("filename"),
                "contentType": item.get("contentType") or item.get("content_type"),
                "width": item.get("width"),
                "height": item.get("height"),
            }
        )
    if len(attachments) > _MAX_AI_ATTACHMENTS:
        raise AiAttachmentError(f"Too many attached images (max {_MAX_AI_ATTACHMENTS}).")
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in attachments:
        key = item["publicId"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_attachment_blocks(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    attachments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not attachments:
        return [], []
    storage = MediaStorage()
    summaries: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    for idx, attachment in enumerate(attachments):
        public_id = attachment.get("publicId")
        if not isinstance(public_id, str) or not public_id.strip():
            continue
        asset = session.scalars(
            select(Asset).where(
                Asset.org_id == org_id,
                Asset.client_id == client_id,
                Asset.public_id == public_id,
            )
        ).first()
        if not asset:
            raise AiAttachmentError(f"Attached image not found: {public_id}")
        if asset.asset_kind != "image":
            raise AiAttachmentError(f"Attached asset is not an image: {public_id}")
        if asset.file_status != "ready":
            raise AiAttachmentError(f"Attached image is not ready: {public_id}")
        if not asset.storage_key:
            raise AiAttachmentError(f"Attached image has no storage key: {public_id}")
        if attachment.get("assetId") and str(asset.id) != str(attachment.get("assetId")):
            raise AiAttachmentError(f"Attached image mismatch: {public_id}")

        data, content_type = storage.download_bytes(key=asset.storage_key)
        media_type = content_type or asset.content_type or attachment.get("contentType")
        if not media_type or str(media_type) not in _VISION_ALLOWED_MIME_TYPES:
            allowed = ", ".join(sorted(_VISION_ALLOWED_MIME_TYPES))
            raise AiAttachmentError(
                f"Unsupported attachment type for {public_id}: {media_type or 'unknown'}. Allowed: {allowed}."
            )
        if not data:
            raise AiAttachmentError(f"Attached image data is empty: {public_id}")
        encoded = base64.b64encode(data).decode("ascii")

        label_parts = [f"Attachment {idx + 1}", f"assetPublicId={public_id}"]
        filename = attachment.get("filename")
        if isinstance(filename, str) and filename:
            label_parts.append(f"filename={filename}")
        if asset.width and asset.height:
            label_parts.append(f"dimensions={asset.width}x{asset.height}")
        if asset.alt:
            label_parts.append(f"alt={asset.alt}")
        blocks.append({"type": "text", "text": " | ".join(label_parts)})
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": str(media_type),
                    "data": encoded,
                },
            }
        )
        summaries.append(
            {
                "assetId": str(asset.id),
                "publicId": public_id,
                "filename": filename or "",
                "contentType": str(media_type),
                "width": asset.width,
                "height": asset.height,
                "alt": asset.alt,
            }
        )
    return summaries, blocks


def _load_reference_image(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    public_id: str,
) -> tuple[Asset, bytes, str]:
    if not public_id or not isinstance(public_id, str):
        raise AiAttachmentError("Reference image public id is required.")
    asset = session.scalars(
        select(Asset).where(
            Asset.org_id == org_id,
            Asset.client_id == client_id,
            Asset.public_id == public_id,
        )
    ).first()
    if not asset:
        raise AiAttachmentError(f"Referenced image not found: {public_id}")
    if asset.asset_kind != "image":
        raise AiAttachmentError(f"Referenced asset is not an image: {public_id}")
    if asset.file_status != "ready":
        raise AiAttachmentError(f"Referenced image is not ready: {public_id}")
    if not asset.storage_key:
        raise AiAttachmentError(f"Referenced image has no storage key: {public_id}")

    storage = MediaStorage()
    data, content_type = storage.download_bytes(key=asset.storage_key)
    media_type = content_type or asset.content_type
    if not media_type or str(media_type) not in _VISION_ALLOWED_MIME_TYPES:
        allowed = ", ".join(sorted(_VISION_ALLOWED_MIME_TYPES))
        raise AiAttachmentError(
            f"Unsupported reference image type for {public_id}: {media_type or 'unknown'}. Allowed: {allowed}."
        )
    if not data:
        raise AiAttachmentError(f"Referenced image data is empty: {public_id}")
    return asset, data, str(media_type)


def _build_public_asset_url(public_id: str) -> str | None:
    base_url = settings.PUBLIC_ASSET_BASE_URL
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    return f"{base_url.rstrip('/')}/public/assets/{public_id}"


def _serialize_product(product: Product, primary_asset: Asset | None = None) -> dict[str, Any]:
    payload = {
        "id": str(product.id),
        "name": product.title,
        "description": product.description,
        "category": product.product_type,
        "product_type": product.product_type,
        "primary_benefits": product.primary_benefits or [],
        "feature_bullets": product.feature_bullets or [],
        "guarantee_text": product.guarantee_text,
        "disclaimers": product.disclaimers or [],
    }
    if primary_asset:
        payload["primary_image"] = {
            "public_id": str(primary_asset.public_id),
            "url": _build_public_asset_url(str(primary_asset.public_id)),
            "alt": primary_asset.alt,
            "width": primary_asset.width,
            "height": primary_asset.height,
        }
    else:
        payload["primary_image"] = None
    return payload


def _serialize_offer(
    offer: ProductOffer, price_points: list[ProductVariant]
) -> dict[str, Any]:
    return {
        "id": str(offer.id),
        "name": offer.name,
        "description": offer.description,
        "business_model": offer.business_model,
        "differentiation_bullets": offer.differentiation_bullets or [],
        "guarantee_text": offer.guarantee_text,
        "options_schema": offer.options_schema,
        "price_points": [
            {
                "label": point.title,
                "amount_cents": point.price,
                "currency": point.currency,
                "provider": point.provider,
                "external_price_id": point.external_price_id,
                "option_values": point.option_values,
            }
            for point in price_points
        ],
    }


def _load_product_context(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    funnel: Funnel,
) -> tuple[Optional[Product], Optional[ProductOffer], str]:
    if not funnel.product_id:
        context = (
            "Product context unavailable (no product selected). Do not invent details; keep copy high-level and avoid "
            "specific claims, pricing, or guarantees unless explicitly provided elsewhere.\n\n"
        )
        return None, None, context
    product = session.scalars(
        select(Product).where(
            Product.org_id == org_id,
            Product.client_id == client_id,
            Product.id == funnel.product_id,
        )
    ).first()
    if not product:
        context = (
            "Product context unavailable (product not found). Do not invent details; keep copy high-level and avoid "
            "specific claims, pricing, or guarantees unless explicitly provided elsewhere.\n\n"
        )
        return None, None, context

    offer = None
    offer_payload = None
    if funnel.selected_offer_id:
        offer = session.scalars(
            select(ProductOffer).where(
                ProductOffer.id == funnel.selected_offer_id,
                ProductOffer.product_id == product.id,
                ProductOffer.client_id == client_id,
            )
        ).first()
        if not offer:
            raise ValueError("Selected offer does not belong to the funnel product.")
        price_points = list(
            session.scalars(
                select(ProductVariant).where(ProductVariant.offer_id == offer.id)
            ).all()
        )
        offer_payload = _serialize_offer(offer, price_points)

    primary_asset: Asset | None = None
    if product.primary_asset_id:
        primary_asset = session.scalars(
            select(Asset).where(
                Asset.org_id == org_id,
                Asset.client_id == client_id,
                Asset.id == product.primary_asset_id,
            )
        ).first()
        if primary_asset and primary_asset.asset_kind != "image":
            primary_asset = None
        if primary_asset and primary_asset.file_status and primary_asset.file_status != "ready":
            primary_asset = None

    payload = {
        "product": _serialize_product(product, primary_asset),
        "selected_offer": offer_payload,
    }
    product_type = _normalize_product_type(product)
    context = (
        "Product context (source of truth; do not invent missing details):\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
    )
    if product_type == "book":
        context += (
            "Product rendering constraint: this is a physical printed book. "
            "Do not depict it on tablets, phones, or screens.\n\n"
        )
    return product, offer, context


def _puck_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "assistantMessage": {"type": "string"},
            "puckData": {
                "type": "string",
                "description": "JSON-encoded Puck data object with root/content/zones.",
            },
        },
        "required": ["assistantMessage", "puckData"],
    }


def _puck_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "PuckDraft",
            "strict": True,
            "schema": _puck_output_schema(),
        },
    }


def _prompt_wants_header_footer(prompt: str) -> tuple[bool, bool]:
    lowered = (prompt or "").lower()
    wants_header = ("header" in lowered) or ("navigation" in lowered) or (" nav" in lowered) or lowered.startswith("nav")
    wants_footer = "footer" in lowered
    return wants_header, wants_footer


def _resolve_template_id(template_id: Optional[str], page: Optional[FunnelPage]) -> Optional[str]:
    if template_id:
        return template_id
    if page and getattr(page, "template_id", None):
        return str(page.template_id)
    return None


def _puck_has_section_purpose(puck_data: dict[str, Any], purpose: str) -> bool:
    content = puck_data.get("content")
    if not isinstance(content, list):
        return False
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "Section":
            continue
        props = item.get("props")
        if isinstance(props, dict) and props.get("purpose") == purpose:
            return True
    return False


def _make_component(component_type: str, props: dict[str, Any]) -> dict[str, Any]:
    if "id" not in props or not isinstance(props.get("id"), str) or not props.get("id"):
        props["id"] = str(uuid.uuid4())
    return {"type": component_type, "props": props}


def _inject_header_footer_if_missing(
    *,
    puck_data: dict[str, Any],
    page_name: str,
    current_page_id: str,
    page_context: list[dict[str, Any]],
    wants_header: bool,
    wants_footer: bool,
) -> None:
    content = puck_data.get("content")
    if not isinstance(content, list):
        content = []
        puck_data["content"] = content

    if wants_header and not _puck_has_section_purpose(puck_data, "header"):
        nav_targets = [p for p in page_context if str(p.get("id")) and str(p.get("id")) != str(current_page_id)]
        nav_targets = nav_targets[:2]
        nav_buttons: list[dict[str, Any]] = []
        for p in nav_targets:
            nav_buttons.append(
                _make_component(
                    "Button",
                    {
                        "label": str(p.get("name") or "Page"),
                        "variant": "secondary",
                        "size": "sm",
                        "align": "right",
                        "linkType": "funnelPage",
                        "targetPageId": str(p.get("id")),
                    },
                )
            )

        header_left: list[dict[str, Any]] = [
            _make_component(
                "Heading",
                {"text": page_name or "Header", "level": 4, "align": "left"},
            ),
        ]
        header_right: list[dict[str, Any]] = nav_buttons or [
            _make_component(
                "Button",
                {"label": "Continue", "variant": "secondary", "size": "sm", "align": "right"},
            )
        ]
        header = _make_component(
            "Section",
            {
                "purpose": "header",
                "layout": "full",
                "containerWidth": "lg",
                "variant": "default",
                "padding": "sm",
                "content": [
                    _make_component(
                        "Columns",
                        {"ratio": "2:1", "gap": "md", "left": header_left, "right": header_right},
                    )
                ],
            },
        )
        content.insert(0, header)

    if wants_footer and not _puck_has_section_purpose(puck_data, "footer"):
        footer_items: list[dict[str, Any]] = [
            _make_component(
                "Text",
                {
                    "text": "Educational only. Not medical advice. If you have symptoms that worsen or take medications, consult a licensed clinician.",
                    "size": "sm",
                    "tone": "muted",
                },
            )
        ]
        footer = _make_component(
            "Section",
            {
                "purpose": "footer",
                "layout": "full",
                "containerWidth": "lg",
                "variant": "muted",
                "padding": "md",
                "content": footer_items,
            },
        )
        content.append(footer)


def _sanitize_component_tree(items: Any, allowed_types: set[str]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        t = raw.get("type")
        props = raw.get("props")
        if not isinstance(t, str) or t not in allowed_types or not isinstance(props, dict):
            continue

        # Ensure slot-like children are lists to avoid runtime errors.
        if t == "Section":
            if not isinstance(props.get("content"), list):
                props["content"] = []
            props["content"] = _sanitize_component_tree(props.get("content"), allowed_types)
        elif t in ("SalesPdpPage", "PreSalesPage"):
            if not isinstance(props.get("content"), list):
                props["content"] = []
            props["content"] = _sanitize_component_tree(props.get("content"), allowed_types)
        elif t == "Columns":
            if not isinstance(props.get("left"), list):
                props["left"] = []
            if not isinstance(props.get("right"), list):
                props["right"] = []
            props["left"] = _sanitize_component_tree(props.get("left"), allowed_types)
            props["right"] = _sanitize_component_tree(props.get("right"), allowed_types)
        elif t == "FeatureGrid":
            if not isinstance(props.get("features"), list):
                props["features"] = []
        elif t == "Testimonials":
            if not isinstance(props.get("testimonials"), list):
                props["testimonials"] = []
        elif t == "FAQ":
            if not isinstance(props.get("items"), list):
                props["items"] = []

        cleaned.append(cast(dict[str, Any], raw))

    return cleaned


def _resolve_image_asset_key(obj: dict[str, Any]) -> str | None:
    if "iconAssetPublicId" in obj or "iconSrc" in obj:
        return "iconAssetPublicId"
    if "posterAssetPublicId" in obj or "poster" in obj:
        return "posterAssetPublicId"
    if "assetPublicId" in obj or "src" in obj:
        return "assetPublicId"
    if obj.get("type") == "image":
        return "assetPublicId"
    if "prompt" in obj and (
        "alt" in obj or "referenceAssetPublicId" in obj or "imageSource" in obj or "image_source" in obj
    ):
        return "assetPublicId"
    return None


_IMAGE_SOURCE_OPTIONS = {"ai", "unsplash"}
_IMAGE_ASPECT_RATIO_OPTIONS = {"1:1", "4:3", "3:4", "16:9", "9:16"}


def _normalize_image_source(value: Any) -> str:
    if value is None:
        return "ai"
    if not isinstance(value, str) or not value.strip():
        raise AiAttachmentError("imageSource must be a non-empty string when provided.")
    normalized = value.strip().lower()
    if normalized not in _IMAGE_SOURCE_OPTIONS:
        allowed = ", ".join(sorted(_IMAGE_SOURCE_OPTIONS))
        raise AiAttachmentError(f"imageSource must be one of: {allowed}.")
    return normalized


def _normalize_aspect_ratio(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AiAttachmentError("aspectRatio must be a non-empty string when provided.")
    normalized = value.strip()
    if normalized not in _IMAGE_ASPECT_RATIO_OPTIONS:
        allowed = ", ".join(sorted(_IMAGE_ASPECT_RATIO_OPTIONS))
        raise AiAttachmentError(f"aspectRatio must be one of: {allowed}.")
    return normalized


def _extract_image_prompt_target(
    obj: dict[str, Any], asset_key: str
) -> tuple[str, str | None, str, str | None] | None:
    if _is_testimonial_image(obj):
        return None
    reference_public_id_raw = obj.get("referenceAssetPublicId") or obj.get("reference_asset_public_id")
    reference_public_id: str | None = None
    if reference_public_id_raw is not None:
        if isinstance(reference_public_id_raw, str) and reference_public_id_raw.strip():
            reference_public_id = reference_public_id_raw.strip()
        else:
            raise AiAttachmentError("Image referenceAssetPublicId must be a non-empty string.")
    asset_public_id = obj.get(asset_key)
    if asset_public_id and reference_public_id:
        raise AiAttachmentError(f"Image cannot set both {asset_key} and referenceAssetPublicId.")
    if asset_public_id:
        return None
    image_source = _normalize_image_source(obj.get("imageSource") or obj.get("image_source"))
    aspect_ratio = _normalize_aspect_ratio(obj.get("aspectRatio") or obj.get("aspect_ratio"))
    prompt = obj.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        if reference_public_id:
            raise AiAttachmentError("Image prompt is required when referenceAssetPublicId is set.")
        if image_source == "unsplash":
            raise AiAttachmentError("Image prompt is required when imageSource is unsplash.")
        return None
    if image_source == "unsplash" and reference_public_id:
        raise AiAttachmentError("Unsplash images do not support referenceAssetPublicId.")
    if image_source == "unsplash" and asset_key == "iconAssetPublicId":
        raise AiAttachmentError("Icon images must be generated by AI (imageSource must be 'ai').")
    return prompt.strip(), reference_public_id, image_source, aspect_ratio


def _collect_config_json_contexts(puck_data: dict[str, Any]) -> list[_ConfigJsonContext]:
    contexts: list[_ConfigJsonContext] = []
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if not isinstance(comp_type, str) or not isinstance(props, dict):
            continue
        for key in _CONFIG_JSON_IMAGE_KEYS:
            raw = props.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            if "prompt" not in raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{comp_type}.{key} must be valid JSON to use image prompts: {exc}") from exc
            if not isinstance(parsed, (dict, list)):
                raise ValueError(f"{comp_type}.{key} must be a JSON object or array to use image prompts.")
            contexts.append(_ConfigJsonContext(component_type=comp_type, props=props, key=key, parsed=parsed))
    return contexts


def _iter_ai_image_prompt_targets(
    puck_data: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str, str, str | None, str, str | None, _ConfigJsonContext | None]]:
    def iter_prompt_targets(
        root: Any,
        *,
        context: _ConfigJsonContext | None = None,
        skip_image_components: bool = False,
    ) -> Iterator[tuple[dict[str, Any], str, str, str | None, str, str | None, _ConfigJsonContext | None]]:
        skip_props: set[int] = set()
        for obj in walk_json(root):
            if not isinstance(obj, dict):
                continue
            if not skip_image_components and obj.get("type") == "Image":
                props = obj.get("props")
                if isinstance(props, dict):
                    skip_props.add(id(props))
                    target = _extract_image_prompt_target(props, "assetPublicId")
                    if target:
                        prompt, reference_public_id, image_source, aspect_ratio = target
                        yield (
                            props,
                            "assetPublicId",
                            prompt,
                            reference_public_id,
                            image_source,
                            aspect_ratio,
                            context,
                        )
                continue
            if skip_props and id(obj) in skip_props:
                continue
            if obj.get("type") == "video":
                continue
            asset_key = _resolve_image_asset_key(obj)
            if not asset_key:
                continue
            target = _extract_image_prompt_target(obj, asset_key)
            if target:
                prompt, reference_public_id, image_source, aspect_ratio = target
                yield (
                    obj,
                    asset_key,
                    prompt,
                    reference_public_id,
                    image_source,
                    aspect_ratio,
                    context,
                )

    config_contexts = _collect_config_json_contexts(puck_data)
    sources: list[tuple[Any, _ConfigJsonContext | None, bool]] = [(puck_data, None, False)]
    sources.extend((ctx.parsed, ctx, True) for ctx in config_contexts)

    for root, context, skip_image_components in sources:
        yield from iter_prompt_targets(root, context=context, skip_image_components=skip_image_components)


def _count_ai_image_targets(puck_data: dict[str, Any]) -> int:
    return sum(1 for _ in _iter_ai_image_prompt_targets(puck_data))


def _resolve_image_generation_count(
    *,
    puck_data: dict[str, Any],
    image_plans: list[dict[str, Any]] | None = None,
    cap: int = _MAX_PAGE_IMAGE_GENERATIONS,
) -> int:
    total_images_needed = _count_ai_image_targets(puck_data)
    if total_images_needed <= cap:
        return total_images_needed

    if image_plans is None:
        config_contexts = _collect_config_json_contexts_all(puck_data)
        image_plans = _collect_image_plans(puck_data=puck_data, config_contexts=config_contexts)

    sample_paths: list[str] = []
    for plan in image_plans:
        path = plan.get("path")
        if not isinstance(path, str) or not path.strip() or path in sample_paths:
            continue
        sample_paths.append(path)
        if len(sample_paths) >= 12:
            break

    sample = ""
    if sample_paths:
        sample = "\nExample image paths:\n" + "\n".join(f"- {path}" for path in sample_paths)

    raise ValueError(
        f"Refusing to generate {total_images_needed} images for a single page. "
        f"Cap is {cap}. Reduce image prompts before retrying.{sample}"
    )


def _fill_ai_images(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    puck_data: dict[str, Any],
    max_images: int = 3,
    funnel_id: Optional[str] = None,
    product_id: Optional[str] = None,
) -> tuple[int, list[dict[str, Any]]]:
    generated: list[dict[str, Any]] = []
    touched_contexts: list[_ConfigJsonContext] = []
    count = 0
    if max_images <= 0:
        return count, generated

    for obj, asset_key, prompt, reference_public_id, image_source, aspect_ratio, ctx in _iter_ai_image_prompt_targets(
        puck_data
    ):
        if count >= max_images:
            break
        try:
            if image_source == "unsplash":
                asset = create_funnel_unsplash_asset(
                    session=session,
                    org_id=org_id,
                    client_id=client_id,
                    query=prompt,
                    usage_context={"kind": "funnel_page_image"},
                    funnel_id=funnel_id,
                    product_id=product_id,
                    tags=["funnel", "funnel_page_image", "unsplash"],
                )
            elif reference_public_id:
                ref_asset, ref_bytes, ref_mime = _load_reference_image(
                    session=session,
                    org_id=org_id,
                    client_id=client_id,
                    public_id=reference_public_id,
                )
                asset = create_funnel_image_asset(
                    session=session,
                    org_id=org_id,
                    client_id=client_id,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    usage_context={
                        "kind": "funnel_page_image",
                        "referenceAssetPublicId": reference_public_id,
                    },
                    reference_image_bytes=ref_bytes,
                    reference_image_mime_type=ref_mime,
                    reference_asset_public_id=reference_public_id,
                    reference_asset_id=str(ref_asset.id),
                    funnel_id=funnel_id,
                    product_id=product_id,
                    tags=["funnel", "funnel_page_image"],
                )
            else:
                asset = create_funnel_image_asset(
                    session=session,
                    org_id=org_id,
                    client_id=client_id,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    usage_context={"kind": "funnel_page_image"},
                    funnel_id=funnel_id,
                    product_id=product_id,
                    tags=["funnel", "funnel_page_image"],
                )
            obj[asset_key] = str(asset.public_id)
            if ctx:
                ctx.dirty = True
                touched_contexts.append(ctx)
            item: dict[str, Any] = {
                "prompt": prompt,
                "publicId": str(asset.public_id),
                "assetId": str(asset.id),
                "imageSource": image_source,
            }
            if aspect_ratio:
                item["aspectRatio"] = aspect_ratio
            if image_source == "unsplash" and isinstance(asset.content, dict):
                item["unsplashQuery"] = asset.content.get("query")
                item["unsplash"] = asset.content.get("unsplash")
            if asset_key != "assetPublicId":
                item["assetKey"] = asset_key
            if reference_public_id:
                item["referenceAssetPublicId"] = reference_public_id
            if ctx:
                item["componentType"] = ctx.component_type
                item["configKey"] = ctx.key
            generated.append(item)
            count += 1
        except Exception as exc:  # noqa: BLE001
            error_item: dict[str, Any] = {"prompt": prompt, "error": str(exc), "imageSource": image_source}
            if aspect_ratio:
                error_item["aspectRatio"] = aspect_ratio
            if asset_key != "assetPublicId":
                error_item["assetKey"] = asset_key
            if reference_public_id:
                error_item["referenceAssetPublicId"] = reference_public_id
            if ctx:
                error_item["componentType"] = ctx.component_type
                error_item["configKey"] = ctx.key
            generated.append(error_item)
            count += 1

    if touched_contexts:
        unique_contexts = {id(ctx): ctx for ctx in touched_contexts}.values()
        for ctx in unique_contexts:
            if ctx.dirty:
                ctx.props[ctx.key] = json.dumps(ctx.parsed)
    return count, generated


def generate_funnel_page_draft(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    prompt: str,
    messages: Optional[list[dict[str, str]]] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    generate_images: bool = True,
    max_images: int = 3,
) -> tuple[str, FunnelPageVersion, dict[str, Any], list[dict[str, Any]]]:
    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise ValueError("Funnel not found")

    page = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
    ).first()
    if not page:
        raise ValueError("Page not found")

    product, _, product_context = _load_product_context(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        funnel=funnel,
    )

    llm = LLMClient()
    model_id = model or llm.default_model
    max_tokens = _coerce_max_tokens(model_id, max_tokens)

    resolved_template_id = _resolve_template_id(template_id, page)
    template = get_funnel_template(resolved_template_id) if resolved_template_id else None
    if resolved_template_id and not template:
        raise ValueError("Template not found")
    template_mode = template is not None
    template_kind = None
    if template_mode:
        if template.template_id == "sales-pdp":
            template_kind = "sales-pdp"
        elif template.template_id == "pre-sales-listicle":
            template_kind = "pre-sales-listicle"
        else:
            raise ValueError(f"Template {template.template_id} is not supported for AI generation")

    if not funnel.product_id:
        raise ValueError("product_id is required to generate AI funnel drafts.")
    resolved_workspace_id = idea_workspace_id or f"client-{funnel.client_id}"
    context_files = []
    if resolved_workspace_id:
        ctx_repo = ClaudeContextFilesRepository(session)
        context_files = ctx_repo.list_for_generation_context(
            org_id=org_id,
            idea_workspace_id=resolved_workspace_id,
            client_id=str(funnel.client_id),
            product_id=str(funnel.product_id),
            campaign_id=str(funnel.campaign_id) if funnel.campaign_id else None,
        )
    use_claude_context = bool(context_files)
    normalized_attachments = _normalize_attachment_list(attachments)
    if normalized_attachments and model and not model.lower().startswith("claude"):
        raise AiAttachmentError(
            "Image attachments require a Claude model with vision support. Clear the model override or set a Claude model."
        )
    attachment_summaries, attachment_blocks = _build_attachment_blocks(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        attachments=normalized_attachments,
    )
    use_vision_attachments = bool(attachment_blocks)

    pages = list(
        session.scalars(
            select(FunnelPage)
            .where(FunnelPage.funnel_id == funnel_id)
            .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
        ).all()
    )
    page_context = [{"id": str(p.id), "name": p.name, "slug": p.slug} for p in pages]

    latest_draft = session.scalars(
        select(FunnelPageVersion)
        .where(
            FunnelPageVersion.page_id == page_id,
            FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
        )
        .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
    ).first()
    base_puck = current_puck_data or (latest_draft.puck_data if latest_draft else None)
    if not isinstance(base_puck, dict):
        base_puck = None
    if template_mode and base_puck is None:
        base_puck = template.puck_data

    template_component_kind: str | None = None
    if template_mode and isinstance(base_puck, dict):
        template_component_kind = _infer_template_component_kind(template_kind, base_puck)

    if not template_mode:
        structure_guidance = (
            "- Use Section as the top-level blocks in puckData.content (do not place bare Heading/Text directly at the root)\n"
            "- Use Columns inside Sections for two-column layouts (image + copy)\n\n"
        )
    elif template_component_kind == "sales-pdp":
        structure_guidance = (
            "- Use SalesPdpPage as the ONLY top-level block in puckData.content\n"
            "- Put all SalesPdp* sections inside SalesPdpPage.props.content (slot)\n"
            "- Preserve the overall section order; update copy/images inside each section's props.config / props.copy / props.modals\n"
            "- Do NOT override layout sizing tokens like containerMax/containerPad (or --container-max/--container-pad) in props.theme tokens; keep the template width\n\n"
        )
    elif template_component_kind == "pre-sales-listicle":
        structure_guidance = (
            "- Use PreSalesPage as the ONLY top-level block in puckData.content\n"
            "- Put all PreSales* sections inside PreSalesPage.props.content (slot)\n"
            "- Preserve the overall section order; update copy/images inside each section's props.config / props.copy\n"
            "- Do NOT override layout sizing tokens like containerMax/containerPad (or --container-max/--container-pad) in props.theme tokens; keep the template width\n\n"
        )
    else:
        structure_guidance = (
            "- Preserve the template's existing top-level structure in puckData.content.\n"
            "- Do not introduce new component types; only edit props fields.\n\n"
        )
    header_footer_guidance = (
        "Header/Footer guidance:\n"
        "- If the user requests a header: add a Section with props.purpose='header' as the FIRST item in puckData.content\n"
        "- If the user requests a footer: add a Section with props.purpose='footer' as the LAST item in puckData.content\n"
        "- Header should include brand + simple navigation (Buttons linking to internal pages when available)\n"
        "- Footer should include a brief disclaimer + secondary links (Buttons)\n\n"
        if not template_mode
        else ""
    )
    context_guidance = (
        "Context guidance:\n"
        "- Use the attached Claude context documents as the source of truth for brand, offer, and constraints\n\n"
        if use_claude_context
        else ""
    )
    product_guidance = product_context
    attachment_guidance = ""
    if attachment_summaries:
        lines = [
            "Attached images guidance:",
            "- Use Image.props.assetPublicId to place an attached image as-is.",
            "- Use Image.props.referenceAssetPublicId with a prompt to generate a new image based on an attachment.",
            "- Do not invent assetPublicId/referenceAssetPublicId values.",
            "Attached images:",
        ]
        for item in attachment_summaries:
            line = f"- {item.get('publicId')}"
            filename = item.get("filename") or ""
            if filename:
                line += f" (filename: {filename})"
            if item.get("width") and item.get("height"):
                line += f" [{item.get('width')}x{item.get('height')}]"
            lines.append(line)
        attachment_guidance = "\n".join(lines) + "\n\n"
    template_guidance = (
        f"Template guidance:\n- Template id: {template.template_id}\n"
        "- Do not introduce new component types not listed below.\n"
        "- Do not remove or rename existing template components in the current page puckData; only edit their props/config/copy fields.\n"
        if template_mode
        else ""
    )
    template_image_guidance = ""
    if template_mode:
        template_image_guidance = (
            "Template image prompts:\n"
            "- Add a `prompt` on every image object inside props.config/props.modals/props.copy that should be generated.\n"
            "- Do NOT add prompts to brand logos (logo objects). Keep logo assetPublicId intact.\n"
            "- Do NOT add prompts to testimonial images (objects with testimonialTemplate); those are rendered separately.\n"
            "- Leave the corresponding *AssetPublicId field empty so the backend can generate and fill it.\n"
            "- Placeholder /assets/ph-* images must be replaced with prompts or assetPublicId.\n"
            "- Prefer Unsplash for stock-appropriate imagery (lifestyle, generic product-in-use, backgrounds).\n"
            "- To use Unsplash, set imageSource='unsplash' on the image object and include a prompt.\n"
            "- Use AI generation only when stock imagery does not fit the need.\n"
            "- Icon prompts (iconAssetPublicId) must be flat vector icons on transparent backgrounds.\n"
            "- Do not set referenceAssetPublicId unless you are using one of the attached images listed above.\n"
            "- If you want to base it on an attached image, set referenceAssetPublicId on that image object and include the prompt.\n\n"
        )
        if template_kind == "sales-pdp":
            template_image_guidance += (
                "Sales PDP product imagery:\n"
                "- Hero/gallery imagery must show the product clearly.\n"
                "- Any section that calls out the product should include the product in the image.\n\n"
            )
        if template_kind == "pre-sales-listicle":
            template_image_guidance += (
                "Pre-sales listicle imagery:\n"
                "- Reason images should use a square (1:1) aspect ratio.\n"
                "- If copy references the product, include the product in the image.\n\n"
            )
    template_config_guidance = ""
    if template_mode and template_kind == "sales-pdp":
        template_config_guidance = (
            "Sales PDP config requirements:\n"
            "- SalesPdpReviews.config MUST include: id, data.\n"
            "- SalesPdpHero.config.gallery.freeGifts MUST be present (do not remove it).\n"
            "- SalesPdpHero.modals MUST be present (sizeChart/whyBundle/freeGifts).\n"
            "- SalesPdpFaq.config MUST include: id, title, items[] (do not replace it with the primitive FAQ component).\n"
            "- SalesPdpReviewSlider.config MUST include: title, body, hint, toggle { auto, manual }, slides[].\n"
            "- Do not use review wall keys (badge/tiles) inside reviewSlider config.\n\n"
            "Anchor id requirements:\n"
            "- Do not change section ids or header nav href anchors.\n"
            "- Keep SalesPdpStoryProblem.config.id = 'how-it-works' (Problem section; floating CTA triggers after this section).\n"
            "- Keep SalesPdpHeader.config.nav href values pointing at the same section ids (e.g. '#how-it-works', '#guarantee', '#faq', '#reviews').\n\n"
        )
    elif template_mode and template_component_kind == "pre-sales-listicle":
        template_config_guidance = (
            "Pre-sales listicle config requirements:\n"
            "- PreSalesHero.config MUST be: { hero: { title: string, subtitle: string, media?: { type:'image', alt:string, src?:string, assetPublicId?:string } | { type:'video', srcMp4:string, poster?:string, alt?:string, assetPublicId?:string } }, badges: [] }\n"
            "- PreSalesReasons.config MUST be an array of reasons: [{ number: number, title: string, body: string, image?: { alt:string, src?:string, assetPublicId?:string } }]\n"
            "- PreSalesMarquee.config MUST be an array of strings.\n"
            "- PreSalesPitch.config MUST be: { title: string, bullets: string[], image: { alt:string, src?:string, assetPublicId?:string }, cta?: { label: string, linkType?: 'external'|'funnelPage'|'nextPage', href?:string, targetPageId?:string } }\n"
            "- PreSalesFooter.config MUST be: { logo: { alt:string, src?:string, assetPublicId?:string } }\n"
            "- Do NOT use keys like headline/subheadline/ctaLabel/ctaLinkType/items/reasons/reviews/links/copyrightText inside PreSales* configs.\n\n"
        )
    if not template_mode:
        template_component = ""
    elif template_component_kind == "sales-pdp":
        template_component = (
            "11) SalesPdpPage: props { id, anchorId?, theme, themeJson?, content? }\n"
            "12) SalesPdpHeader: props { id, config, configJson? }\n"
            "13) SalesPdpHero: props { id, config, configJson?, modals?, modalsJson?, copy?, copyJson? }\n"
            "14) SalesPdpVideos: props { id, config, configJson? }\n"
            "15) SalesPdpMarquee: props { id, config, configJson? }\n"
            "16) SalesPdpStoryProblem: props { id, config, configJson? }\n"
            "17) SalesPdpStorySolution: props { id, config, configJson? }\n"
            "18) SalesPdpComparison: props { id, config, configJson? }\n"
            "19) SalesPdpGuarantee: props { id, config, configJson?, feedImages?, feedImagesJson? }\n"
            "20) SalesPdpFaq: props { id, config, configJson? }\n"
            "21) SalesPdpReviews: props { id, config, configJson? }\n"
            "22) SalesPdpReviewWall: props { id, config, configJson? }\n"
            "23) SalesPdpFooter: props { id, config, configJson? }\n"
            "24) SalesPdpReviewSlider: props { id, config, configJson? }\n"
        )
    elif template_component_kind == "pre-sales-listicle":
        template_component = (
            "11) PreSalesPage: props { id, anchorId?, theme, themeJson?, content? }\n"
            "12) PreSalesHero: props { id, config, configJson? }\n"
            "13) PreSalesReasons: props { id, config, configJson? }\n"
            "14) PreSalesMarquee: props { id, config, configJson? }\n"
            "15) PreSalesPitch: props { id, config, configJson? }\n"
            "16) PreSalesReviewWall: props { id, config, configJson?, copy?, copyJson? }\n"
            "17) PreSalesFooter: props { id, config, configJson? }\n"
            "18) PreSalesFloatingCta: props { id, config, configJson? }\n"
        )
    else:
        template_component = ""

    page_label = "sales page"
    if template_kind == "pre-sales-listicle":
        page_label = "pre-sales listicle page"

    system = {
        "role": "system",
        "content": (
            f"You are generating content for a Puck editor {page_label}.\n\n"
            "You MUST output valid JSON only (no markdown, no code fences, no commentary).\n"
            "Do not wrap the output in ``` or any code fences.\n"
            "The response must start with '{' and end with '}' (no leading or trailing text).\n"
            "Use \\n for line breaks inside JSON string values (no raw newlines).\n"
            "Return exactly ONE JSON object with this shape:\n"
            '{ "assistantMessage": string, "puckData": string }\n'
            "puckData must be a JSON-encoded string for this object shape:\n"
            '{ "root": { "props": object }, "content": ComponentData[], "zones": object }\n\n'
            "Output the top-level keys in this exact order: assistantMessage, puckData.\n\n"
            "assistantMessage requirements:\n"
            "- Plain text (no markdown)\n"
            f"- Keep it under {_ASSISTANT_MESSAGE_MAX_CHARS} characters (short summary only; do not include full page copy)\n"
            "- Provide a short preview of the page (headings + main CTA only) so it looks good in a chat bubble\n"
            "- Include a medical safety disclaimer and avoid making medical claims\n\n"
            "Copy goals:\n"
            "- High-converting direct-response structure (clear promise, benefits, proof, objections/FAQ, repeated CTA)\n"
            "- Be specific and scannable (short paragraphs, bullets)\n"
            "- Use ethical persuasion; avoid fear-mongering\n\n"
            "Layout guidance:\n"
            "- Default to Section.layout='full' for most sections (full-width background)\n"
            "- Use Section.containerWidth='lg' for a modern website width (use 'xl' if you need more)\n"
            "- Alternate Section.variant between 'default' and 'muted' to create clear visual sections\n\n"
            f"{context_guidance}"
            f"{product_guidance}"
            f"{attachment_guidance}"
            f"{template_guidance}"
            f"{template_image_guidance}"
            f"{template_config_guidance}"
            "Structure guidance:\n"
            f"{structure_guidance}"
            f"{header_footer_guidance}"
            "ComponentData shape:\n"
            "- Every component must be an object with keys: type, props\n"
            "- props should include a string id (unique per component)\n\n"
            "- Do NOT double-encode JSON: only *Json fields (e.g., configJson) may contain JSON strings. props.config must be a JSON object/array, not a JSON-encoded string.\n\n"
            "Available primitives (component types) and their props:\n"
            "1) Section: props { id, purpose?, layout?, containerWidth?, variant?, padding?, content? }\n"
            "   - purpose: 'header' | 'section' | 'footer'\n"
            "   - layout: 'full' | 'contained' | 'card'\n"
            "     - full = full-width background, content constrained to containerWidth\n"
            "     - contained = background constrained to containerWidth (no card styling)\n"
            "     - card = contained card with border/rounding/shadow (avoid for modern landing pages)\n"
            "   - containerWidth: 'sm' | 'md' | 'lg' | 'xl'\n"
            "   - content is a slot: ComponentData[]\n"
            "2) Columns: props { id, ratio?, gap?, left?, right? }\n"
            "   - left/right are slots: ComponentData[]\n"
            "3) Heading: props { id, text, level?, align? }\n"
            "   - level: 1|2|3|4 (H1-H4)\n"
            "   - align: 'left' | 'center'\n"
            "4) Text: props { id, text, size?, tone?, align? }\n"
            "   - size: 'sm' | 'md' | 'lg'\n"
            "   - tone: 'default' | 'muted'\n"
            "   - align: 'left' | 'center'\n"
            "5) Spacer: props { id, height }\n"
            "6) Image: props { id, prompt, alt, imageSource?, assetPublicId?, referenceAssetPublicId?, src?, radius? }\n"
            "   - imageSource: 'ai' (default) | 'unsplash'\n"
            "   - radius: 'none' | 'md' | 'lg'\n"
            "   - If imageSource='unsplash': include prompt and leave assetPublicId empty (no referenceAssetPublicId)\n"
            "   - If referenceAssetPublicId is set: include prompt and leave assetPublicId empty\n"
            "7) Button: props { id, label, variant?, size?, width?, align?, linkType?, targetPageId?, href? }\n"
            "   - variant: 'primary' | 'secondary'\n"
            "   - size: 'sm' | 'md' | 'lg'\n"
            "   - width: 'auto' | 'full'\n"
            "   - align: 'left' | 'center' | 'right'\n"
            "   - If linkType='funnelPage': include targetPageId\n"
            "   - If linkType='external': include href\n"
            "8) FeatureGrid: props { id, title?, columns?, features? }\n"
            "9) Testimonials: props { id, title?, testimonials? }\n"
            "10) FAQ: props { id, title?, items? }\n"
            f"{template_component}\n"
            "Root props (optional):\n"
            "- root.props.title\n"
            "- root.props.description\n\n"
            "Internal funnel pages you can link to (targetPageId should be one of these ids):\n"
            f"{json.dumps(page_context, ensure_ascii=False)}\n\n"
            "Current page puckData (may be null):\n"
            f"{json.dumps(base_puck, ensure_ascii=False)}"
        ),
    }

    conversation: list[dict[str, str]] = []
    if messages:
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                conversation.append({"role": cast(Literal["user", "assistant"], role), "content": content.strip()})
    if prompt and prompt.strip():
        conversation.append({"role": "user", "content": prompt.strip()})
    if not conversation:
        conversation.append({"role": "user", "content": "Generate a simple funnel landing page."})

    base_prompt_parts = [system["content"]] + [f"{m['role'].upper()}: {m['content']}" for m in conversation]
    compiled_prompt = "\n\n".join(base_prompt_parts + ["Return JSON now."])

    allowed_types = {
        "Section",
        "Columns",
        "Heading",
        "Text",
        "Button",
        "Image",
        "Spacer",
        "FeatureGrid",
        "Testimonials",
        "FAQ",
    }
    if template_component_kind == "sales-pdp":
        allowed_types.update(
            {
                "SalesPdpPage",
                "SalesPdpHeader",
                "SalesPdpHero",
                "SalesPdpVideos",
                "SalesPdpMarquee",
                "SalesPdpStoryProblem",
                "SalesPdpStorySolution",
                "SalesPdpComparison",
                "SalesPdpGuarantee",
                "SalesPdpFaq",
                "SalesPdpReviews",
                "SalesPdpReviewWall",
                "SalesPdpFooter",
                "SalesPdpReviewSlider",
                "SalesPdpTemplate",
            }
        )
    elif template_component_kind == "pre-sales-listicle":
        allowed_types.update(
            {
                "PreSalesPage",
                "PreSalesHero",
                "PreSalesReasons",
                "PreSalesReviews",
                "PreSalesMarquee",
                "PreSalesPitch",
                "PreSalesReviewWall",
                "PreSalesFooter",
                "PreSalesFloatingCta",
                "PreSalesTemplate",
            }
        )

    params = LLMGenerationParams(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        use_reasoning=True,
        use_web_search=False,
        response_format=_puck_response_format(),
    )

    def _generate_with_retry(prompt_text: str) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                return llm.generate_text(prompt_text, params=params)
            except RuntimeError as exc:
                message = str(exc)
                if "Anthropic returned no content" not in message:
                    raise
                if attempt == max_attempts - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("LLM generation failed unexpectedly")
    out = ""
    obj: dict[str, Any] | None = None
    final_model = model_id
    if use_claude_context or use_vision_attachments:
        claude_model = model_id if model_id.lower().startswith("claude") else CLAUDE_DEFAULT_MODEL
        claude_max = max_tokens or _CLAUDE_MAX_OUTPUT_TOKENS
        documents = build_document_blocks(context_files)
        user_content = [{"type": "text", "text": compiled_prompt}, *attachment_blocks, *documents]
        response = call_claude_structured_message(
            model=claude_model,
            system=None,
            user_content=user_content,
            output_schema=_puck_output_schema(),
            max_tokens=claude_max,
            temperature=temperature,
        )
        parsed = response.get("parsed") if isinstance(response, dict) else None
        if isinstance(parsed, dict):
            obj = parsed
            out = json.dumps(parsed, ensure_ascii=False)
        final_model = claude_model
    else:
        out = _generate_with_retry(compiled_prompt)

        try:
            obj = _extract_json_object(out)
        except Exception as exc:  # noqa: BLE001
            repair_lines = [
                "The previous response was invalid JSON. Regenerate from scratch.",
                f"Error: {exc}",
                f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                "The response must start with '{' and end with '}' (no code fences).",
            ]
            if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS:
                repair_lines.append(f"Previous response:\n{out}")
            repair_lines.append("Return corrected JSON only.")
            repair_prompt = "\n\n".join(base_prompt_parts + repair_lines)
            out = _generate_with_retry(repair_prompt)
            obj = _extract_json_object(out)

    if obj is None:
        raise RuntimeError("Model returned no parsable JSON response")

    assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)

    puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
    puck_data = _sanitize_puck_data(puck_data_raw)
    puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
    zones = puck_data.get("zones")
    if isinstance(zones, dict):
        for key, value in list(zones.items()):
            zones[key] = _sanitize_component_tree(value, allowed_types)
    _ensure_block_ids(puck_data)
    if not puck_data.get("content"):
        repair_prompt = "\n\n".join(
            base_prompt_parts
            + [
                "Your previous response resulted in an empty page.",
                "Return a complete page using the available component types listed above.",
                f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                "The response must start with '{' and end with '}' (no code fences).",
                f"Previous response:\n{out}" if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS else "",
                "Return corrected JSON only.",
            ]
        )
        out = _generate_with_retry(repair_prompt)
        obj = _extract_json_object(out)
        assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
        puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
        puck_data = _sanitize_puck_data(puck_data_raw)
        puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
        zones = puck_data.get("zones")
        if isinstance(zones, dict):
            for key, value in list(zones.items()):
                zones[key] = _sanitize_component_tree(value, allowed_types)
        _ensure_block_ids(puck_data)

    if template_mode and isinstance(base_puck, dict):
        required_types = _required_template_component_types(base_puck, template_kind=template_component_kind)
        if required_types:
            generated_counts = _count_component_types(puck_data)
            missing_types = sorted(
                comp_type for comp_type in required_types if generated_counts.get(comp_type, 0) == 0
            )
            if missing_types:
                missing_str = ", ".join(missing_types)
                required_str = ", ".join(sorted(required_types))
                raise ValueError(
                    "AI generation removed required template components from puckData "
                    f"(templateKind={template_kind}). Missing: {missing_str}. "
                    f"Required (based on the template input): {required_str}. "
                    "The model must preserve template structure and only edit props/config/copy fields."
                )

    wants_header, wants_footer = _prompt_wants_header_footer(prompt)
    if template_mode:
        wants_header = False
        wants_footer = False
    missing_header = wants_header and not _puck_has_section_purpose(puck_data, "header")
    missing_footer = wants_footer and not _puck_has_section_purpose(puck_data, "footer")
    if missing_header or missing_footer:
        requirements: list[str] = []
        if missing_header:
            requirements.append(
                "- Add a header Section as the FIRST item with props.purpose='header', layout='full', containerWidth='lg', padding='sm'."
            )
            requirements.append("- Header content should include brand + navigation Buttons (link to internal pages when available).")
        if missing_footer:
            requirements.append(
                "- Add a footer Section as the LAST item with props.purpose='footer', layout='full', containerWidth='lg', variant='muted', padding='md'."
            )
            requirements.append("- Footer content should include a brief disclaimer + secondary navigation Buttons.")

        repair_prompt = "\n\n".join(
            base_prompt_parts
            + [
                "Your previous response did not include the requested header/footer sections in puckData.content.",
                *requirements,
                "Keep the rest of the page content unchanged.",
                f"Previous response:\n{out}",
                "Return corrected JSON only.",
            ]
        )
        out = llm.generate_text(repair_prompt, params=params)
        obj = _extract_json_object(out)
        assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
        puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
        puck_data = _sanitize_puck_data(puck_data_raw)
        puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
        zones = puck_data.get("zones")
        if isinstance(zones, dict):
            for key, value in list(zones.items()):
                zones[key] = _sanitize_component_tree(value, allowed_types)
        _ensure_block_ids(puck_data)

    _inject_header_footer_if_missing(
        puck_data=puck_data,
        page_name=page.name,
        current_page_id=page_id,
        page_context=page_context,
        wants_header=wants_header,
        wants_footer=wants_footer,
    )

    if not puck_data.get("content"):
        raise RuntimeError("AI generation produced an empty page (no content).")

    root_props = puck_data.get("root", {}).get("props") if isinstance(puck_data.get("root"), dict) else None
    if isinstance(root_props, dict):
        title = root_props.get("title")
        if not isinstance(title, str) or not title.strip():
            root_props["title"] = page.name
        desc = root_props.get("description")
        if not isinstance(desc, str):
            root_props["description"] = ""

    if template_component_kind == "pre-sales-listicle":
        _validate_pre_sales_listicle_component_configs(puck_data)
    elif template_component_kind == "sales-pdp":
        _validate_sales_pdp_component_configs(puck_data)

    design_system_tokens = resolve_design_system_tokens(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        funnel=funnel,
        page=page,
    )
    brand_logo_public_id: str | None = None
    if isinstance(design_system_tokens, dict):
        brand = design_system_tokens.get("brand")
        if isinstance(brand, dict):
            logo_value = brand.get("logoAssetPublicId")
            if isinstance(logo_value, str) and logo_value.strip():
                brand_logo_public_id = logo_value.strip()
    config_contexts: list[_ConfigJsonContext] = []
    if template_mode:
        config_contexts = _collect_config_json_contexts_all(puck_data)
    _apply_brand_logo_overrides_for_ai(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        puck_data=puck_data,
        config_contexts=config_contexts,
        design_system_tokens=design_system_tokens,
    )
    _apply_product_image_overrides_for_ai(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        puck_data=puck_data,
        config_contexts=config_contexts,
        template_kind=template_component_kind,
        product=product,
        brand_logo_public_id=brand_logo_public_id,
    )
    _ensure_flat_vector_icon_prompts(puck_data=puck_data, config_contexts=config_contexts)
    if template_component_kind == "pre-sales-listicle":
        _ensure_pre_sales_badge_icons(
            puck_data=puck_data,
            config_contexts=config_contexts,
            fallback_puck_data=current_puck_data,
        )
    if template_mode and generate_images:
        _validate_required_template_images(puck_data=puck_data, config_contexts=config_contexts)
    image_plans: list[dict[str, Any]] = []
    if generate_images:
        image_plans = _collect_image_plans(puck_data=puck_data, config_contexts=config_contexts)
        if template_mode:
            image_plans = _ensure_unsplash_usage(
                image_plans,
                puck_data=puck_data,
                config_contexts=config_contexts,
            )
    _sync_config_json_contexts(config_contexts)

    generated_images: list[dict[str, Any]] = []
    requested_image_count = 0
    if generate_images:
        requested_image_count = _resolve_image_generation_count(
            puck_data=puck_data,
            image_plans=image_plans,
        )
        try:
            _, generated_images = _fill_ai_images(
                session=session,
                org_id=org_id,
                client_id=str(funnel.client_id),
                puck_data=puck_data,
                max_images=requested_image_count,
                funnel_id=funnel_id,
                product_id=str(funnel.product_id) if funnel.product_id else None,
            )
        except Exception as exc:  # noqa: BLE001
            generated_images = [{"error": str(exc)}]

    ai_metadata = {
        "prompt": prompt,
        "messages": conversation,
        "model": final_model,
        "temperature": temperature,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "generatedImages": generated_images,
        "imagePlans": image_plans,
        "requestedImageCount": requested_image_count,
        "appliedImageGenerationCap": _MAX_PAGE_IMAGE_GENERATIONS,
        "actorUserId": user_id,
        "ideaWorkspaceId": resolved_workspace_id,
        "templateId": resolved_template_id,
    }
    if attachment_summaries:
        ai_metadata["attachedAssets"] = attachment_summaries

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=puck_data,
        source=FunnelPageVersionSourceEnum.ai,
        created_at=datetime.now(timezone.utc),
        ai_metadata=ai_metadata,
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return assistant_message, version, puck_data, generated_images


def stream_funnel_page_draft(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    prompt: str,
    messages: Optional[list[dict[str, str]]] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    generate_images: bool = True,
    max_images: int = 3,
) -> Iterator[dict[str, Any]]:
    """
    Runs the page-draft generation while returning stream-friendly events.

    Event shapes (dict):
    - {type:"start", model:string}
    - {type:"text", text:string} (assistantMessage deltas)
    - {type:"status", status:string}
    - {type:"done", assistantMessage, puckData, draftVersionId, generatedImages}
    - {type:"error", message}
    """

    llm = LLMClient()
    model_id = model or llm.default_model
    max_tokens = _coerce_max_tokens(model_id, max_tokens)

    yield {"type": "start", "model": model_id}
    yield {"type": "status", "status": "generating"}

    try:
        funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
        if not funnel:
            raise ValueError("Funnel not found")

        page = session.scalars(
            select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
        ).first()
        if not page:
            raise ValueError("Page not found")

        product, _, product_context = _load_product_context(
            session=session,
            org_id=org_id,
            client_id=str(funnel.client_id),
            funnel=funnel,
        )

        resolved_template_id = _resolve_template_id(template_id, page)
        template = get_funnel_template(resolved_template_id) if resolved_template_id else None
        if resolved_template_id and not template:
            raise ValueError("Template not found")
        template_mode = template is not None
        template_kind = None
        if template_mode:
            if template.template_id == "sales-pdp":
                template_kind = "sales-pdp"
            elif template.template_id == "pre-sales-listicle":
                template_kind = "pre-sales-listicle"
            else:
                raise ValueError(f"Template {template.template_id} is not supported for AI generation")

        if not funnel.product_id:
            raise ValueError("product_id is required to generate AI funnel drafts.")
        resolved_workspace_id = idea_workspace_id or f"client-{funnel.client_id}"
        context_files = []
        if resolved_workspace_id:
            ctx_repo = ClaudeContextFilesRepository(session)
            context_files = ctx_repo.list_for_generation_context(
                org_id=org_id,
                idea_workspace_id=resolved_workspace_id,
                client_id=str(funnel.client_id),
                product_id=str(funnel.product_id),
                campaign_id=str(funnel.campaign_id) if funnel.campaign_id else None,
            )
        if context_files or attachments:
            assistant_message, version, puck_data, generated_images = generate_funnel_page_draft(
                session=session,
                org_id=org_id,
                user_id=user_id,
                funnel_id=funnel_id,
                page_id=page_id,
                prompt=prompt,
                messages=messages,
                attachments=attachments,
                current_puck_data=current_puck_data,
                template_id=template_id,
                idea_workspace_id=idea_workspace_id,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                generate_images=generate_images,
                max_images=max_images,
            )
            yield {
                "type": "done",
                "assistantMessage": assistant_message,
                "puckData": puck_data,
                "draftVersionId": str(version.id),
                "generatedImages": generated_images,
            }
            return

        pages = list(
            session.scalars(
                select(FunnelPage)
                .where(FunnelPage.funnel_id == funnel_id)
                .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
            ).all()
        )
        page_context = [{"id": str(p.id), "name": p.name, "slug": p.slug} for p in pages]

        latest_draft = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page_id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
            )
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        ).first()
        base_puck = current_puck_data or (latest_draft.puck_data if latest_draft else None)
        if not isinstance(base_puck, dict):
            base_puck = None
        if template_mode and base_puck is None:
            base_puck = template.puck_data

        template_component_kind: str | None = None
        if template_mode and isinstance(base_puck, dict):
            template_component_kind = _infer_template_component_kind(template_kind, base_puck)

        if not template_mode:
            structure_guidance = (
                "- Use Section as the top-level blocks in puckData.content (do not place bare Heading/Text directly at the root)\n"
                "- Use Columns inside Sections for two-column layouts (image + copy)\n\n"
            )
        elif template_component_kind == "sales-pdp":
            structure_guidance = (
                "- Use SalesPdpPage as the ONLY top-level block in puckData.content\n"
                "- Put all SalesPdp* sections inside SalesPdpPage.props.content (slot)\n"
                "- Preserve the overall section order; update copy/images inside each section's props.config / props.copy / props.modals\n"
                "- Do NOT override layout sizing tokens like containerMax/containerPad (or --container-max/--container-pad) in props.theme tokens; keep the template width\n\n"
            )
        elif template_component_kind == "pre-sales-listicle":
            structure_guidance = (
                "- Use PreSalesPage as the ONLY top-level block in puckData.content\n"
                "- Put all PreSales* sections inside PreSalesPage.props.content (slot)\n"
                "- Preserve the overall section order; update copy/images inside each section's props.config / props.copy\n"
                "- Do NOT override layout sizing tokens like containerMax/containerPad (or --container-max/--container-pad) in props.theme tokens; keep the template width\n\n"
            )
        else:
            structure_guidance = (
                "- Preserve the template's existing top-level structure in puckData.content.\n"
                "- Do not introduce new component types; only edit props fields.\n\n"
            )
        header_footer_guidance = (
            "Header/Footer guidance:\n"
            "- If the user requests a header: add a Section with props.purpose='header' as the FIRST item in puckData.content\n"
            "- If the user requests a footer: add a Section with props.purpose='footer' as the LAST item in puckData.content\n"
            "- Header should include brand + simple navigation (Buttons linking to internal pages when available)\n"
            "- Footer should include a brief disclaimer + secondary links (Buttons)\n\n"
            if not template_mode
            else ""
        )
        template_guidance = (
            f"Template guidance:\n- Template id: {template.template_id}\n"
            "- Do not introduce new component types not listed below.\n"
            "- Do not remove or rename existing template components in the current page puckData; only edit their props/config/copy fields.\n"
            if template_mode
            else ""
        )
        template_image_guidance = ""
        if template_mode:
                template_image_guidance = (
                    "Template image prompts:\n"
                    "- Add a `prompt` on every image object inside props.config/props.modals/props.copy that should be generated.\n"
                    "- Do NOT add prompts to brand logos (logo objects). Keep logo assetPublicId intact.\n"
                    "- Do NOT add prompts to testimonial images (objects with testimonialTemplate); those are rendered separately.\n"
                    "- Leave the corresponding *AssetPublicId field empty so the backend can generate and fill it.\n"
                    "- Placeholder /assets/ph-* images must be replaced with prompts or assetPublicId.\n"
                    "- Prefer Unsplash for stock-appropriate imagery (lifestyle, generic product-in-use, backgrounds).\n"
                    "- To use Unsplash, set imageSource='unsplash' on the image object and include a prompt.\n"
                    "- Use AI generation only when stock imagery does not fit the need.\n"
                    "- Icon prompts (iconAssetPublicId) must be flat vector icons on transparent backgrounds.\n"
                    "- Do not set referenceAssetPublicId unless you are using one of the attached images listed above.\n"
                    "- If you want to base it on an attached image, set referenceAssetPublicId on that image object and include the prompt.\n\n"
                )
                if template_kind == "sales-pdp":
                    template_image_guidance += (
                        "Sales PDP product imagery:\n"
                        "- Hero/gallery imagery must show the product clearly.\n"
                        "- Any section that calls out the product should include the product in the image.\n\n"
                    )
                if template_kind == "pre-sales-listicle":
                    template_image_guidance += (
                        "Pre-sales listicle imagery:\n"
                        "- Reason images should use a square (1:1) aspect ratio.\n"
                        "- If copy references the product, include the product in the image.\n\n"
                    )
        template_config_guidance = ""
        if template_mode and template_kind == "sales-pdp":
            template_config_guidance = (
                "Sales PDP config requirements:\n"
                "- SalesPdpReviews.config MUST include: id, data.\n"
                "- SalesPdpHero.config.gallery.freeGifts MUST be present (do not remove it).\n"
                "- SalesPdpHero.modals MUST be present (sizeChart/whyBundle/freeGifts).\n"
                "- SalesPdpFaq.config MUST include: id, title, items[] (do not replace it with the primitive FAQ component).\n"
                "- SalesPdpReviewSlider.config MUST include: title, body, hint, toggle { auto, manual }, slides[].\n"
                "- Do not use review wall keys (badge/tiles) inside reviewSlider config.\n\n"
                "Anchor id requirements:\n"
                "- Do not change section ids or header nav href anchors.\n"
                "- Keep SalesPdpStoryProblem.config.id = 'how-it-works' (Problem section; floating CTA triggers after this section).\n"
                "- Keep SalesPdpHeader.config.nav href values pointing at the same section ids (e.g. '#how-it-works', '#guarantee', '#faq', '#reviews').\n\n"
            )
        elif template_mode and template_component_kind == "pre-sales-listicle":
            template_config_guidance = (
                "Pre-sales listicle config requirements:\n"
                "- PreSalesHero.config MUST be: { hero: { title: string, subtitle: string, media?: { type:'image', alt:string, src?:string, assetPublicId?:string } | { type:'video', srcMp4:string, poster?:string, alt?:string, assetPublicId?:string } }, badges: [] }\n"
                "- PreSalesReasons.config MUST be an array of reasons: [{ number: number, title: string, body: string, image?: { alt:string, src?:string, assetPublicId?:string } }]\n"
                "- PreSalesMarquee.config MUST be an array of strings.\n"
                "- PreSalesPitch.config MUST be: { title: string, bullets: string[], image: { alt:string, src?:string, assetPublicId?:string }, cta?: { label: string, linkType?: 'external'|'funnelPage'|'nextPage', href?:string, targetPageId?:string } }\n"
                "- PreSalesFooter.config MUST be: { logo: { alt:string, src?:string, assetPublicId?:string } }\n"
                "- Do NOT use keys like headline/subheadline/ctaLabel/ctaLinkType/items/reasons/reviews/links/copyrightText inside PreSales* configs.\n\n"
            )
        if not template_mode:
            template_component = ""
        elif template_component_kind == "sales-pdp":
            template_component = (
                "11) SalesPdpPage: props { id, anchorId?, theme, themeJson?, content? }\n"
                "12) SalesPdpHeader: props { id, config, configJson? }\n"
                "13) SalesPdpHero: props { id, config, configJson?, modals?, modalsJson?, copy?, copyJson? }\n"
                "14) SalesPdpVideos: props { id, config, configJson? }\n"
                "15) SalesPdpMarquee: props { id, config, configJson? }\n"
                "16) SalesPdpStoryProblem: props { id, config, configJson? }\n"
                "17) SalesPdpStorySolution: props { id, config, configJson? }\n"
                "18) SalesPdpComparison: props { id, config, configJson? }\n"
                "19) SalesPdpGuarantee: props { id, config, configJson?, feedImages?, feedImagesJson? }\n"
                "20) SalesPdpFaq: props { id, config, configJson? }\n"
                "21) SalesPdpReviews: props { id, config, configJson? }\n"
                "22) SalesPdpReviewWall: props { id, config, configJson? }\n"
                "23) SalesPdpFooter: props { id, config, configJson? }\n"
                "24) SalesPdpReviewSlider: props { id, config, configJson? }\n"
            )
        elif template_component_kind == "pre-sales-listicle":
            template_component = (
                "11) PreSalesPage: props { id, anchorId?, theme, themeJson?, content? }\n"
                "12) PreSalesHero: props { id, config, configJson? }\n"
                "13) PreSalesReasons: props { id, config, configJson? }\n"
                "14) PreSalesMarquee: props { id, config, configJson? }\n"
                "15) PreSalesPitch: props { id, config, configJson? }\n"
                "16) PreSalesReviewWall: props { id, config, configJson?, copy?, copyJson? }\n"
                "17) PreSalesFooter: props { id, config, configJson? }\n"
                "18) PreSalesFloatingCta: props { id, config, configJson? }\n"
            )
        else:
            template_component = ""

        page_label = "sales page"
        if template_kind == "pre-sales-listicle":
            page_label = "pre-sales listicle page"

        product_guidance = product_context

        system = {
            "role": "system",
            "content": (
                f"You are generating content for a Puck editor {page_label}.\n\n"
                "You MUST output valid JSON only (no markdown, no code fences, no commentary).\n"
                "Do not wrap the output in ``` or any code fences.\n"
                "The response must start with '{' and end with '}' (no leading or trailing text).\n"
                "Use \\n for line breaks inside JSON string values (no raw newlines).\n"
                "Return exactly ONE JSON object with this shape:\n"
                '{ "assistantMessage": string, "puckData": string }\n'
                "puckData must be a JSON-encoded string for this object shape:\n"
                '{ "root": { "props": object }, "content": ComponentData[], "zones": object }\n\n'
                "Output the top-level keys in this exact order: assistantMessage, puckData.\n\n"
                "assistantMessage requirements:\n"
                "- Plain text (no markdown)\n"
                f"- Keep it under {_ASSISTANT_MESSAGE_MAX_CHARS} characters (short summary only; do not include full page copy)\n"
                "- Provide a short preview of the page (headings + main CTA only) so it looks good in a chat bubble\n"
                "- Include a medical safety disclaimer and avoid making medical claims\n\n"
                "Copy goals:\n"
                "- High-converting direct-response structure (clear promise, benefits, proof, objections/FAQ, repeated CTA)\n"
                "- Be specific and scannable (short paragraphs, bullets)\n"
                "- Use ethical persuasion; avoid fear-mongering\n\n"
                "Layout guidance:\n"
                "- Default to Section.layout='full' for most sections (full-width background)\n"
                "- Use Section.containerWidth='lg' for a modern website width (use 'xl' if you need more)\n"
                "- Alternate Section.variant between 'default' and 'muted' to create clear visual sections\n\n"
                f"{product_guidance}"
                f"{template_guidance}"
                f"{template_image_guidance}"
                f"{template_config_guidance}"
                "Structure guidance:\n"
                f"{structure_guidance}"
                f"{header_footer_guidance}"
	                "ComponentData shape:\n"
	                "- Every component must be an object with keys: type, props\n"
	                "- props should include a string id (unique per component)\n\n"
	                "- Do NOT double-encode JSON: only *Json fields (e.g., configJson) may contain JSON strings. props.config must be a JSON object/array, not a JSON-encoded string.\n\n"
	                "Available primitives (component types) and their props:\n"
	                "1) Section: props { id, purpose?, layout?, containerWidth?, variant?, padding?, content? }\n"
	                "   - purpose: 'header' | 'section' | 'footer'\n"
	                "   - layout: 'full' | 'contained' | 'card'\n"
	                "     - full = full-width background, content constrained to containerWidth\n"
	                "     - contained = background constrained to containerWidth (no card styling)\n"
	                "     - card = contained card with border/rounding/shadow (avoid for modern landing pages)\n"
                "   - containerWidth: 'sm' | 'md' | 'lg' | 'xl'\n"
                "   - content is a slot: ComponentData[]\n"
                "2) Columns: props { id, ratio?, gap?, left?, right? }\n"
                "   - left/right are slots: ComponentData[]\n"
                "3) Heading: props { id, text, level?, align? }\n"
                "   - level: 1|2|3|4 (H1-H4)\n"
                "   - align: 'left' | 'center'\n"
                "4) Text: props { id, text, size?, tone?, align? }\n"
                "   - size: 'sm' | 'md' | 'lg'\n"
                "   - tone: 'default' | 'muted'\n"
                "   - align: 'left' | 'center'\n"
                "5) Spacer: props { id, height }\n"
                "6) Image: props { id, prompt, alt, imageSource?, assetPublicId?, referenceAssetPublicId?, src?, radius? }\n"
                "   - imageSource: 'ai' (default) | 'unsplash'\n"
                "   - radius: 'none' | 'md' | 'lg'\n"
                "   - If imageSource='unsplash': include prompt and leave assetPublicId empty (no referenceAssetPublicId)\n"
                "   - If referenceAssetPublicId is set: include prompt and leave assetPublicId empty\n"
                "7) Button: props { id, label, variant?, size?, width?, align?, linkType?, targetPageId?, href? }\n"
                "   - variant: 'primary' | 'secondary'\n"
                "   - size: 'sm' | 'md' | 'lg'\n"
                "   - width: 'auto' | 'full'\n"
                "   - align: 'left' | 'center' | 'right'\n"
                "   - If linkType='funnelPage': include targetPageId\n"
                "   - If linkType='external': include href\n"
                "8) FeatureGrid: props { id, title?, columns?, features? }\n"
                "9) Testimonials: props { id, title?, testimonials? }\n"
                "10) FAQ: props { id, title?, items? }\n"
                f"{template_component}\n"
                "Root props (optional):\n"
                "- root.props.title\n"
                "- root.props.description\n\n"
                "Internal funnel pages you can link to (targetPageId should be one of these ids):\n"
                f"{json.dumps(page_context, ensure_ascii=False)}\n\n"
                "Current page puckData (may be null):\n"
                f"{json.dumps(base_puck, ensure_ascii=False)}"
            ),
        }

        conversation: list[dict[str, str]] = []
        if messages:
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                    conversation.append(
                        {"role": cast(Literal["user", "assistant"], role), "content": content.strip()}
                    )
        if prompt and prompt.strip():
            conversation.append({"role": "user", "content": prompt.strip()})
        if not conversation:
            conversation.append({"role": "user", "content": "Generate a simple funnel landing page."})

        base_prompt_parts = [system["content"]] + [f"{m['role'].upper()}: {m['content']}" for m in conversation]
        compiled_prompt = "\n\n".join(base_prompt_parts + ["Return JSON now."])

        allowed_types = {
            "Section",
            "Columns",
            "Heading",
            "Text",
            "Button",
            "Image",
            "Spacer",
            "FeatureGrid",
            "Testimonials",
            "FAQ",
        }
        if template_component_kind == "sales-pdp":
            allowed_types.update(
                {
                    "SalesPdpPage",
                    "SalesPdpHeader",
                    "SalesPdpHero",
                    "SalesPdpVideos",
                    "SalesPdpMarquee",
                    "SalesPdpStoryProblem",
                    "SalesPdpStorySolution",
                    "SalesPdpComparison",
                    "SalesPdpGuarantee",
                    "SalesPdpFaq",
                    "SalesPdpReviews",
                    "SalesPdpReviewWall",
                    "SalesPdpFooter",
                    "SalesPdpReviewSlider",
                    "SalesPdpTemplate",
                }
            )
        elif template_component_kind == "pre-sales-listicle":
            allowed_types.update(
                {
                    "PreSalesPage",
                    "PreSalesHero",
                    "PreSalesReasons",
                    "PreSalesReviews",
                    "PreSalesMarquee",
                    "PreSalesPitch",
                    "PreSalesReviewWall",
                    "PreSalesFooter",
                    "PreSalesFloatingCta",
                    "PreSalesTemplate",
                }
            )

        params = LLMGenerationParams(
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            use_reasoning=True,
            use_web_search=False,
            response_format=_puck_response_format(),
        )

        extractor = _AssistantMessageJsonExtractor()
        raw_parts: list[str] = []
        for delta in llm.stream_text(compiled_prompt, params=params):
            raw_parts.append(delta)
            if delta:
                yield {"type": "raw", "text": delta}
            assistant_delta = extractor.feed(delta)
            if assistant_delta:
                yield {"type": "text", "text": assistant_delta}

        out = "".join(raw_parts)

        try:
            obj = _extract_json_object(out)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "status", "status": "repairing"}
            repair_lines = [
                "The previous response was invalid JSON. Regenerate from scratch.",
                f"Error: {exc}",
                f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                "The response must start with '{' and end with '}' (no code fences).",
            ]
            if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS:
                repair_lines.append(f"Previous response:\n{out}")
            repair_lines.append("Return corrected JSON only.")
            repair_prompt = "\n\n".join(base_prompt_parts + repair_lines)
            out = llm.generate_text(repair_prompt, params=params)
            obj = _extract_json_object(out)

        assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)

        puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
        puck_data = _sanitize_puck_data(puck_data_raw)
        puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
        zones = puck_data.get("zones")
        if isinstance(zones, dict):
            for key, value in list(zones.items()):
                zones[key] = _sanitize_component_tree(value, allowed_types)
        _ensure_block_ids(puck_data)

        if not puck_data.get("content"):
            yield {"type": "status", "status": "repairing_empty"}
            repair_prompt = "\n\n".join(
                base_prompt_parts
                + [
                    "Your previous response resulted in an empty page.",
                    "Return a complete page using the available component types listed above.",
                    f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                    "The response must start with '{' and end with '}' (no code fences).",
                    f"Previous response:\n{out}" if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS else "",
                    "Return corrected JSON only.",
                ]
            )
            out = llm.generate_text(repair_prompt, params=params)
            obj = _extract_json_object(out)
            assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
            puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
            puck_data = _sanitize_puck_data(puck_data_raw)
            puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
            zones = puck_data.get("zones")
            if isinstance(zones, dict):
                for key, value in list(zones.items()):
                    zones[key] = _sanitize_component_tree(value, allowed_types)
            _ensure_block_ids(puck_data)

        if template_mode and isinstance(base_puck, dict):
            required_types = _required_template_component_types(base_puck, template_kind=template_component_kind)
            if required_types:
                generated_counts = _count_component_types(puck_data)
                missing_types = sorted(
                    comp_type for comp_type in required_types if generated_counts.get(comp_type, 0) == 0
                )
                if missing_types:
                    missing_str = ", ".join(missing_types)
                    required_str = ", ".join(sorted(required_types))
                    raise ValueError(
                        "AI generation removed required template components from puckData "
                        f"(templateKind={template_kind}). Missing: {missing_str}. "
                        f"Required (based on the template input): {required_str}. "
                        "The model must preserve template structure and only edit props/config/copy fields."
                    )

        wants_header, wants_footer = _prompt_wants_header_footer(prompt)
        if template_mode:
            wants_header = False
            wants_footer = False
        missing_header = wants_header and not _puck_has_section_purpose(puck_data, "header")
        missing_footer = wants_footer and not _puck_has_section_purpose(puck_data, "footer")
        if missing_header or missing_footer:
            yield {"type": "status", "status": "repairing_header_footer"}
            requirements: list[str] = []
            if missing_header:
                requirements.append(
                    "- Add a header Section as the FIRST item with props.purpose='header', layout='full', containerWidth='lg', padding='sm'."
                )
                requirements.append(
                    "- Header content should include brand + navigation Buttons (link to internal pages when available)."
                )
            if missing_footer:
                requirements.append(
                    "- Add a footer Section as the LAST item with props.purpose='footer', layout='full', containerWidth='lg', variant='muted', padding='md'."
                )
                requirements.append("- Footer content should include a brief disclaimer + secondary navigation Buttons.")

            repair_prompt = "\n\n".join(
                base_prompt_parts
                + [
                    "Your previous response did not include the requested header/footer sections in puckData.content.",
                    *requirements,
                    "Keep the rest of the page content unchanged.",
                    f"Previous response:\n{out}",
                    "Return corrected JSON only.",
                ]
            )
            out = llm.generate_text(repair_prompt, params=params)
            obj = _extract_json_object(out)
            assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
            puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
            puck_data = _sanitize_puck_data(puck_data_raw)
            puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
            zones = puck_data.get("zones")
            if isinstance(zones, dict):
                for key, value in list(zones.items()):
                    zones[key] = _sanitize_component_tree(value, allowed_types)
            _ensure_block_ids(puck_data)

        _inject_header_footer_if_missing(
            puck_data=puck_data,
            page_name=page.name,
            current_page_id=page_id,
            page_context=page_context,
            wants_header=wants_header,
            wants_footer=wants_footer,
        )

        if not puck_data.get("content"):
            yield {"type": "error", "message": "AI generation produced an empty page (no content)."}
            return

        root_props = puck_data.get("root", {}).get("props") if isinstance(puck_data.get("root"), dict) else None
        if isinstance(root_props, dict):
            title = root_props.get("title")
            if not isinstance(title, str) or not title.strip():
                root_props["title"] = page.name
            desc = root_props.get("description")
            if not isinstance(desc, str):
                root_props["description"] = ""

        if template_component_kind == "pre-sales-listicle":
            _validate_pre_sales_listicle_component_configs(puck_data)
        elif template_component_kind == "sales-pdp":
            _validate_sales_pdp_component_configs(puck_data)

        design_system_tokens = resolve_design_system_tokens(
            session=session,
            org_id=org_id,
            client_id=str(funnel.client_id),
            funnel=funnel,
            page=page,
        )
        brand_logo_public_id: str | None = None
        if isinstance(design_system_tokens, dict):
            brand = design_system_tokens.get("brand")
            if isinstance(brand, dict):
                logo_value = brand.get("logoAssetPublicId")
                if isinstance(logo_value, str) and logo_value.strip():
                    brand_logo_public_id = logo_value.strip()
        config_contexts: list[_ConfigJsonContext] = []
        if template_mode:
            config_contexts = _collect_config_json_contexts_all(puck_data)
        _apply_brand_logo_overrides_for_ai(
            session=session,
            org_id=org_id,
            client_id=str(funnel.client_id),
            puck_data=puck_data,
            config_contexts=config_contexts,
            design_system_tokens=design_system_tokens,
        )
        _apply_product_image_overrides_for_ai(
            session=session,
            org_id=org_id,
            client_id=str(funnel.client_id),
            puck_data=puck_data,
            config_contexts=config_contexts,
            template_kind=template_component_kind,
            product=product,
            brand_logo_public_id=brand_logo_public_id,
        )
        _ensure_flat_vector_icon_prompts(puck_data=puck_data, config_contexts=config_contexts)
        if template_component_kind == "pre-sales-listicle":
            _ensure_pre_sales_badge_icons(
                puck_data=puck_data,
                config_contexts=config_contexts,
                fallback_puck_data=current_puck_data,
            )
        if template_mode and generate_images:
            _validate_required_template_images(puck_data=puck_data, config_contexts=config_contexts)
        image_plans: list[dict[str, Any]] = []
        if generate_images:
            image_plans = _collect_image_plans(puck_data=puck_data, config_contexts=config_contexts)
            if template_mode:
                image_plans = _ensure_unsplash_usage(
                    image_plans,
                    puck_data=puck_data,
                    config_contexts=config_contexts,
                )
        _sync_config_json_contexts(config_contexts)

        generated_images: list[dict[str, Any]] = []
        requested_image_count = 0
        if generate_images:
            yield {"type": "status", "status": "generating_images"}
            requested_image_count = _resolve_image_generation_count(
                puck_data=puck_data,
                image_plans=image_plans,
            )
            try:
                _, generated_images = _fill_ai_images(
                    session=session,
                    org_id=org_id,
                    client_id=str(funnel.client_id),
                    puck_data=puck_data,
                    max_images=requested_image_count,
                    funnel_id=funnel_id,
                    product_id=str(funnel.product_id) if funnel.product_id else None,
                )
            except Exception as exc:  # noqa: BLE001
                generated_images = [{"error": str(exc)}]

        version = FunnelPageVersion(
            page_id=page.id,
            status=FunnelPageVersionStatusEnum.draft,
            puck_data=puck_data,
            source=FunnelPageVersionSourceEnum.ai,
            created_at=datetime.now(timezone.utc),
            ai_metadata={
                "prompt": prompt,
                "messages": conversation,
                "model": model_id,
                    "temperature": temperature,
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "generatedImages": generated_images,
                    "imagePlans": image_plans,
                    "requestedImageCount": requested_image_count,
                    "appliedImageGenerationCap": _MAX_PAGE_IMAGE_GENERATIONS,
                    "actorUserId": user_id,
                },
            )
        session.add(version)
        session.commit()
        session.refresh(version)

        yield {
            "type": "done",
            "assistantMessage": assistant_message,
            "puckData": puck_data,
            "draftVersionId": str(version.id),
            "generatedImages": generated_images,
            "imagePlans": image_plans,
        }
        return
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc)}
        return
