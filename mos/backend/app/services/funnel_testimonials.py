from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum
from app.db.models import Asset, Funnel, FunnelPage, FunnelPageVersion, Product
from app.llm.client import LLMClient, LLMGenerationParams
from app.services.funnels import create_funnel_image_asset, create_funnel_upload_asset
from app.services.funnel_ai import _load_product_context
from app.services.funnels import _walk_json as walk_json
from app.testimonial_renderer.renderer import TestimonialRenderer
from app.testimonial_renderer.validate import TestimonialRenderError


class TestimonialGenerationError(RuntimeError):
    pass


class TestimonialGenerationNotFoundError(RuntimeError):
    pass


@dataclass
class _ConfigContext:
    props: dict[str, Any]
    key: str
    parsed: dict[str, Any]
    dirty: bool = False


@dataclass
class _TestimonialRenderTarget:
    image: dict[str, Any]
    label: str
    template: str
    context: _ConfigContext | None = None


@dataclass
class _TestimonialGroup:
    label: str
    renders: list[_TestimonialRenderTarget]
    slide: dict[str, Any] | None = None
    context: _ConfigContext | None = None


_DATE_FORMAT = "%Y-%m-%d"
_TESTIMONIAL_TEMPLATES = {"review_card", "social_comment", "testimonial_media"}

def _require_public_asset_base_url() -> str:
    base_url = settings.PUBLIC_ASSET_BASE_URL
    if not isinstance(base_url, str) or not base_url.strip():
        raise TestimonialGenerationError(
            "PUBLIC_ASSET_BASE_URL is required to build public asset URLs."
        )
    return base_url.rstrip("/")


def _public_asset_url(public_id: str) -> str:
    base_url = _require_public_asset_base_url()
    return f"{base_url}/public/assets/{public_id}"


def _resolve_testimonial_template(image: dict[str, Any]) -> str:
    raw = image.get("testimonialTemplate") or image.get("testimonial_template") or image.get("testimonial_type")
    if raw is None:
        return "review_card"
    if not isinstance(raw, str) or not raw.strip():
        raise TestimonialGenerationError("testimonialTemplate must be a non-empty string when provided.")
    template = raw.strip()
    if template not in _TESTIMONIAL_TEMPLATES:
        allowed = ", ".join(sorted(_TESTIMONIAL_TEMPLATES))
        raise TestimonialGenerationError(
            f"testimonialTemplate must be one of: {allowed}. Received: {template}"
        )
    return template


def _resolve_product_primary_image(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
) -> Asset:
    if not product.primary_asset_id:
        raise TestimonialGenerationError(
            "Product primary image is required to render testimonial hero images."
        )
    asset = session.scalars(
        select(Asset).where(
            Asset.org_id == org_id,
            Asset.client_id == client_id,
            Asset.id == product.primary_asset_id,
        )
    ).first()
    if not asset:
        raise TestimonialGenerationError("Product primary image asset not found.")
    if asset.product_id and str(asset.product_id) != str(product.id):
        raise TestimonialGenerationError("Product primary image asset does not belong to the product.")
    if asset.asset_kind != "image":
        raise TestimonialGenerationError("Product primary asset must be an image.")
    if asset.file_status and asset.file_status != "ready":
        raise TestimonialGenerationError("Product primary image asset is not ready.")
    if not asset.public_id:
        raise TestimonialGenerationError("Product primary image asset is missing public_id.")
    return asset


def _parse_config_context(props: dict[str, Any]) -> tuple[dict[str, Any] | None, _ConfigContext | None]:
    config = props.get("config")
    if isinstance(config, dict):
        return config, None
    raw = props.get("configJson")
    if raw is None:
        return None, None
    if not isinstance(raw, str) or not raw.strip():
        raise TestimonialGenerationError("configJson must be a non-empty JSON string.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TestimonialGenerationError(f"configJson must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise TestimonialGenerationError("configJson must decode to a JSON object.")
    return parsed, _ConfigContext(props=props, key="configJson", parsed=parsed)


def _collect_sales_pdp_targets(
    config: dict[str, Any], *, context: _ConfigContext | None
) -> list[_TestimonialGroup]:
    groups: list[_TestimonialGroup] = []
    review_wall = config.get("reviewWall")
    if isinstance(review_wall, dict):
        tiles = review_wall.get("tiles")
        if not isinstance(tiles, list) or not tiles:
            raise TestimonialGenerationError("Sales PDP reviewWall.tiles must be a non-empty list.")
        for idx, tile in enumerate(tiles):
            if not isinstance(tile, dict):
                raise TestimonialGenerationError("Sales PDP reviewWall.tiles must be objects.")
            image = tile.get("image")
            if not isinstance(image, dict):
                raise TestimonialGenerationError(
                    f"Sales PDP reviewWall.tiles[{idx}].image must be an object."
                )
            label = f"sales_pdp.reviewWall.tiles[{idx}]"
            render = _TestimonialRenderTarget(
                image=image,
                label=label,
                template=_resolve_testimonial_template(image),
                context=context,
            )
            groups.append(_TestimonialGroup(label=label, renders=[render], context=context))

    review_slider = config.get("reviewSlider")
    if isinstance(review_slider, dict):
        slides = review_slider.get("slides")
        if not isinstance(slides, list) or not slides:
            raise TestimonialGenerationError("Sales PDP reviewSlider.slides must be a non-empty list.")
        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                raise TestimonialGenerationError("Sales PDP reviewSlider.slides must be objects.")
            label = f"sales_pdp.reviewSlider.slides[{idx}]"
            render = _TestimonialRenderTarget(
                image=slide,
                label=label,
                template=_resolve_testimonial_template(slide),
                context=context,
            )
            groups.append(_TestimonialGroup(label=label, renders=[render], context=context))
    return groups


def _collect_pre_sales_targets(
    config: dict[str, Any], *, context: _ConfigContext | None
) -> list[_TestimonialGroup]:
    groups: list[_TestimonialGroup] = []
    reviews = config.get("reviews")
    if isinstance(reviews, dict):
        slides = reviews.get("slides")
        if not isinstance(slides, list) or not slides:
            raise TestimonialGenerationError("Pre-sales reviews.slides must be a non-empty list.")
        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                raise TestimonialGenerationError("Pre-sales reviews.slides must be objects.")
            images = slide.get("images")
            if isinstance(images, list) and images:
                renders: list[_TestimonialRenderTarget] = []
                for img_idx, image in enumerate(images):
                    if not isinstance(image, dict):
                        raise TestimonialGenerationError(
                            f"Pre-sales reviews.slides[{idx}].images[{img_idx}] must be an object."
                        )
                    render_label = f"pre_sales.reviews.slides[{idx}].images[{img_idx}]"
                    renders.append(
                        _TestimonialRenderTarget(
                            image=image,
                            label=render_label,
                            template=_resolve_testimonial_template(image),
                            context=context,
                        )
                    )
                groups.append(
                    _TestimonialGroup(
                        label=f"pre_sales.reviews.slides[{idx}]",
                        renders=renders,
                        slide=slide,
                        context=context,
                    )
                )
            else:
                image = slide.get("image")
                if not isinstance(image, dict):
                    raise TestimonialGenerationError(
                        f"Pre-sales reviews.slides[{idx}].images must be a non-empty list."
                    )
                label = f"pre_sales.reviews.slides[{idx}]"
                render = _TestimonialRenderTarget(
                    image=image,
                    label=label,
                    template=_resolve_testimonial_template(image),
                    context=context,
                )
                groups.append(
                    _TestimonialGroup(label=label, renders=[render], slide=slide, context=context)
                )

    review_wall = config.get("reviewsWall")
    if isinstance(review_wall, dict):
        columns = review_wall.get("columns")
        if not isinstance(columns, list) or not columns:
            raise TestimonialGenerationError("Pre-sales reviewsWall.columns must be a non-empty list.")
        for col_idx, column in enumerate(columns):
            if not isinstance(column, list) or not column:
                raise TestimonialGenerationError("Pre-sales reviewsWall.columns must contain lists.")
            for row_idx, item in enumerate(column):
                if not isinstance(item, dict):
                    raise TestimonialGenerationError("Pre-sales reviewsWall.columns entries must be objects.")
                image = item.get("image")
                if not isinstance(image, dict):
                    raise TestimonialGenerationError(
                        f"Pre-sales reviewsWall.columns[{col_idx}][{row_idx}].image must be an object."
                    )
                label = f"pre_sales.reviewsWall.columns[{col_idx}][{row_idx}]"
                render = _TestimonialRenderTarget(
                    image=image,
                    label=label,
                    template=_resolve_testimonial_template(image),
                    context=context,
                )
                groups.append(_TestimonialGroup(label=label, renders=[render], context=context))
    return groups


def _collect_testimonial_targets(
    puck_data: dict[str, Any], template_kind: str
) -> tuple[list[_TestimonialGroup], list[_ConfigContext]]:
    groups: list[_TestimonialGroup] = []
    contexts: list[_ConfigContext] = []
    seen_images: set[int] = set()
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if not isinstance(comp_type, str) or not isinstance(props, dict):
            continue

        if comp_type in ("SalesPdpReviewWall", "SalesPdpReviewSlider", "SalesPdpTemplate") and template_kind == "sales-pdp":
            config, ctx = _parse_config_context(props)
            if not config:
                raise TestimonialGenerationError(f"{comp_type} is missing config/configJson.")
            if ctx:
                contexts.append(ctx)
            if comp_type == "SalesPdpTemplate":
                groups.extend(_collect_sales_pdp_targets(config, context=ctx))
            elif comp_type == "SalesPdpReviewWall":
                groups.extend(_collect_sales_pdp_targets({"reviewWall": config}, context=ctx))
            elif comp_type == "SalesPdpReviewSlider":
                groups.extend(_collect_sales_pdp_targets({"reviewSlider": config}, context=ctx))

        if comp_type in ("PreSalesReviews", "PreSalesReviewWall", "PreSalesTemplate") and template_kind == "pre-sales-listicle":
            config, ctx = _parse_config_context(props)
            if not config:
                raise TestimonialGenerationError(f"{comp_type} is missing config/configJson.")
            if ctx:
                contexts.append(ctx)
            if comp_type == "PreSalesTemplate":
                groups.extend(_collect_pre_sales_targets(config, context=ctx))
            elif comp_type == "PreSalesReviews":
                groups.extend(_collect_pre_sales_targets({"reviews": config}, context=ctx))
            elif comp_type == "PreSalesReviewWall":
                groups.extend(_collect_pre_sales_targets({"reviewsWall": config}, context=ctx))

    if not groups:
        expected: set[str] = set()
        if template_kind == "sales-pdp":
            expected = {"SalesPdpReviewWall", "SalesPdpReviewSlider", "SalesPdpTemplate"}
        elif template_kind == "pre-sales-listicle":
            expected = {"PreSalesReviews", "PreSalesReviewWall", "PreSalesTemplate"}
        counts = {key: 0 for key in expected}
        for obj in walk_json(puck_data):
            if not isinstance(obj, dict):
                continue
            comp_type = obj.get("type")
            if comp_type in counts:
                counts[comp_type] += 1
        found_summary = ", ".join(
            f"{comp_type}={count}" for comp_type, count in sorted(counts.items()) if count
        )
        if not found_summary:
            found_summary = "none"
        expected_summary = ", ".join(sorted(expected)) if expected else "unknown"
        raise TestimonialGenerationError(
            "No testimonial image slots found for this template. "
            f"templateKind={template_kind}. "
            f"Expected at least one of: {expected_summary}. "
            f"Found: {found_summary}."
        )
    for group in groups:
        for render in group.renders:
            image_id = id(render.image)
            if image_id in seen_images:
                raise TestimonialGenerationError(
                    f"Duplicate testimonial image slot detected: {render.label}"
                )
            seen_images.add(image_id)
    return groups, contexts


def _force_pre_sales_review_media_templates(puck_data: dict[str, Any]) -> None:
    def update_reviews_config(reviews: dict[str, Any]) -> None:
        slides = reviews.get("slides")
        if not isinstance(slides, list) or not slides:
            raise TestimonialGenerationError("Pre-sales reviews.slides must be a non-empty list.")
        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                raise TestimonialGenerationError("Pre-sales reviews.slides must be objects.")
            images = slide.get("images")
            if not isinstance(images, list) or len(images) < 3:
                raise TestimonialGenerationError(
                    f"Pre-sales reviews.slides[{idx}].images must include 3 image objects."
                )
            for image in images:
                if isinstance(image, dict):
                    image["testimonialTemplate"] = "testimonial_media"

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        if comp_type not in ("PreSalesReviews", "PreSalesTemplate"):
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        config = props.get("config")
        if isinstance(config, dict):
            if comp_type == "PreSalesReviews":
                update_reviews_config(config)
            else:
                reviews = config.get("reviews")
                if isinstance(reviews, dict):
                    update_reviews_config(reviews)
        raw = props.get("configJson")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise TestimonialGenerationError(
                    f"{comp_type}.configJson must be valid JSON: {exc}"
                ) from exc
            if isinstance(parsed, dict):
                if comp_type == "PreSalesReviews":
                    update_reviews_config(parsed)
                else:
                    reviews = parsed.get("reviews")
                    if isinstance(reviews, dict):
                        update_reviews_config(reviews)
                props["configJson"] = json.dumps(parsed, ensure_ascii=False)


def _apply_review_wall_template_mix(puck_data: dict[str, Any], template_kind: str) -> None:
    def assign_templates(images: list[dict[str, Any]]) -> None:
        for idx, image in enumerate(images):
            template = "social_comment" if idx % 3 == 1 else "review_card"
            image["testimonialTemplate"] = template

    def update_pre_sales_wall(config: dict[str, Any]) -> None:
        reviews_wall = config.get("reviewsWall") if "reviewsWall" in config else config
        if not isinstance(reviews_wall, dict):
            return
        columns = reviews_wall.get("columns")
        if not isinstance(columns, list):
            return
        images: list[dict[str, Any]] = []
        for column in columns:
            if not isinstance(column, list):
                continue
            for item in column:
                if not isinstance(item, dict):
                    continue
                image = item.get("image")
                if isinstance(image, dict):
                    images.append(image)
        assign_templates(images)

    def update_sales_wall(config: dict[str, Any]) -> None:
        review_wall = config.get("reviewWall") if "reviewWall" in config else config
        if not isinstance(review_wall, dict):
            return
        tiles = review_wall.get("tiles")
        if not isinstance(tiles, list):
            return
        images: list[dict[str, Any]] = []
        for tile in tiles:
            if not isinstance(tile, dict):
                continue
            image = tile.get("image")
            if isinstance(image, dict):
                images.append(image)
        assign_templates(images)

    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        comp_type = obj.get("type")
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        if template_kind == "pre-sales-listicle" and comp_type in ("PreSalesReviewWall", "PreSalesTemplate"):
            config = props.get("config")
            if isinstance(config, dict):
                if comp_type == "PreSalesReviewWall":
                    update_pre_sales_wall(config)
                else:
                    reviews_wall = config.get("reviewsWall")
                    if isinstance(reviews_wall, dict):
                        update_pre_sales_wall({"reviewsWall": reviews_wall})
            raw = props.get("configJson")
            if isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise TestimonialGenerationError(
                        f"{comp_type}.configJson must be valid JSON: {exc}"
                    ) from exc
                if isinstance(parsed, dict):
                    if comp_type == "PreSalesReviewWall":
                        update_pre_sales_wall(parsed)
                    else:
                        reviews_wall = parsed.get("reviewsWall")
                        if isinstance(reviews_wall, dict):
                            update_pre_sales_wall({"reviewsWall": reviews_wall})
                    props["configJson"] = json.dumps(parsed, ensure_ascii=False)

        if template_kind == "sales-pdp" and comp_type in ("SalesPdpReviewWall", "SalesPdpTemplate"):
            config = props.get("config")
            if isinstance(config, dict):
                if comp_type == "SalesPdpReviewWall":
                    update_sales_wall(config)
                else:
                    review_wall = config.get("reviewWall")
                    if isinstance(review_wall, dict):
                        update_sales_wall({"reviewWall": review_wall})
            raw = props.get("configJson")
            if isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise TestimonialGenerationError(
                        f"{comp_type}.configJson must be valid JSON: {exc}"
                    ) from exc
                if isinstance(parsed, dict):
                    if comp_type == "SalesPdpReviewWall":
                        update_sales_wall(parsed)
                    else:
                        review_wall = parsed.get("reviewWall")
                        if isinstance(review_wall, dict):
                            update_sales_wall({"reviewWall": review_wall})
                    props["configJson"] = json.dumps(parsed, ensure_ascii=False)


def _collect_sales_pdp_review_wall_images(groups: list[_TestimonialGroup]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for group in groups:
        for render in group.renders:
            if render.label.startswith("sales_pdp.reviewWall.tiles"):
                images.append(render.image)
    return images


def _sync_sales_pdp_guarantee_feed_images(
    puck_data: dict[str, Any],
    *,
    review_wall_images: list[dict[str, Any]],
) -> None:
    guarantee_props: list[dict[str, Any]] = []
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "SalesPdpGuarantee":
            continue
        props = obj.get("props")
        if isinstance(props, dict):
            guarantee_props.append(props)

    if not guarantee_props:
        return

    if not review_wall_images:
        raise TestimonialGenerationError(
            "SalesPdpGuarantee requires SalesPdpReviewWall tiles to populate review feed images."
        )

    for props in guarantee_props:
        feed_images = copy.deepcopy(review_wall_images)
        raw_feed_json = props.get("feedImagesJson")
        if isinstance(raw_feed_json, str):
            props["feedImagesJson"] = json.dumps(feed_images, ensure_ascii=False)
            props["feedImages"] = feed_images
        else:
            props["feedImages"] = feed_images
            if "feedImagesJson" in props:
                props.pop("feedImagesJson", None)


def _extract_copy_lines(puck_data: dict[str, Any]) -> str:
    excluded_keys = {
        "id",
        "assetPublicId",
        "src",
        "href",
        "imageSource",
        "referenceAssetPublicId",
        "targetPageId",
        "anchorId",
        "layout",
        "variant",
        "size",
        "align",
        "radius",
        "width",
        "height",
        "prompt",
        "configJson",
        "copyJson",
        "themeJson",
        "modalsJson",
    }

    def looks_like_url(value: str) -> bool:
        lowered = value.lower()
        if lowered.startswith(("http://", "https://", "file://")):
            return True
        if lowered.startswith("/assets/") or lowered.startswith("/public/"):
            return True
        return False

    lines: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in excluded_keys:
                    continue
                if isinstance(item, str):
                    candidate = item.strip()
                    if not candidate or looks_like_url(candidate):
                        continue
                    lines.append(candidate)
                else:
                    walk(item)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
            return

    walk(puck_data)
    seen: set[str] = set()
    unique_lines: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        unique_lines.append(line)
    text = "\n".join(unique_lines)
    if len(text) > 5000:
        text = text[:5000] + "..."
    return text


def _testimonial_output_schema(count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "testimonials": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "verified": {"type": "boolean"},
                        "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                        "review": {"type": "string"},
                        "persona": {"type": "string"},
                        "avatarPrompt": {"type": "string"},
                        "heroImagePrompt": {"type": "string"},
                        "mediaPrompts": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "items": {"type": "string"},
                        },
                        "meta": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "location": {"type": "string"},
                                "date": {"type": "string"},
                            },
                        },
                    },
                    "required": [
                        "name",
                        "verified",
                        "rating",
                        "review",
                        "persona",
                        "avatarPrompt",
                        "heroImagePrompt",
                        "mediaPrompts",
                    ],
                },
            }
        },
        "required": ["testimonials"],
    }


def _validate_testimonial_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise TestimonialGenerationError("Testimonial name must be a non-empty string.")
    if len(name.strip()) > 80:
        raise TestimonialGenerationError("Testimonial name must be 80 characters or fewer.")
    review = payload.get("review")
    if not isinstance(review, str) or not review.strip():
        raise TestimonialGenerationError("Testimonial review must be a non-empty string.")
    if len(review.strip()) > 800:
        raise TestimonialGenerationError("Testimonial review must be 800 characters or fewer.")
    persona = payload.get("persona")
    if not isinstance(persona, str) or not persona.strip():
        raise TestimonialGenerationError("Testimonial persona must be a non-empty string.")
    if len(persona.strip()) > 240:
        raise TestimonialGenerationError("Testimonial persona must be 240 characters or fewer.")
    avatar_prompt = payload.get("avatarPrompt")
    if not isinstance(avatar_prompt, str) or not avatar_prompt.strip():
        raise TestimonialGenerationError("Testimonial avatarPrompt must be a non-empty string.")
    if len(avatar_prompt.strip()) > 500:
        raise TestimonialGenerationError("Testimonial avatarPrompt must be 500 characters or fewer.")
    hero_prompt = payload.get("heroImagePrompt")
    if not isinstance(hero_prompt, str) or not hero_prompt.strip():
        raise TestimonialGenerationError("Testimonial heroImagePrompt must be a non-empty string.")
    if len(hero_prompt.strip()) > 600:
        raise TestimonialGenerationError("Testimonial heroImagePrompt must be 600 characters or fewer.")
    media_prompts = payload.get("mediaPrompts")
    if not isinstance(media_prompts, list) or len(media_prompts) != 3:
        raise TestimonialGenerationError("Testimonial mediaPrompts must be an array of 3 strings.")
    cleaned_media_prompts: list[str] = []
    for idx, prompt in enumerate(media_prompts):
        if not isinstance(prompt, str) or not prompt.strip():
            raise TestimonialGenerationError(
                f"Testimonial mediaPrompts[{idx}] must be a non-empty string."
            )
        if len(prompt.strip()) > 300:
            raise TestimonialGenerationError(
                f"Testimonial mediaPrompts[{idx}] must be 300 characters or fewer."
            )
        cleaned_media_prompts.append(prompt.strip())
    verified = payload.get("verified")
    if not isinstance(verified, bool):
        raise TestimonialGenerationError("Testimonial verified must be a boolean.")
    rating = payload.get("rating")
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise TestimonialGenerationError("Testimonial rating must be an integer between 1 and 5.")
    meta = payload.get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            raise TestimonialGenerationError("Testimonial meta must be an object when provided.")
        location = meta.get("location")
        if location is not None:
            if not isinstance(location, str) or not location.strip():
                raise TestimonialGenerationError("meta.location must be a non-empty string when provided.")
            if len(location.strip()) > 120:
                raise TestimonialGenerationError("meta.location must be 120 characters or fewer.")
        date = meta.get("date")
        if date is not None:
            if not isinstance(date, str):
                raise TestimonialGenerationError("meta.date must be a string when provided.")
            try:
                datetime.strptime(date, _DATE_FORMAT)
            except ValueError as exc:
                raise TestimonialGenerationError("meta.date must be YYYY-MM-DD.") from exc
    return {
        "name": name.strip(),
        "verified": verified,
        "rating": rating,
        "review": review.strip(),
        "persona": persona.strip(),
        "avatarPrompt": avatar_prompt.strip(),
        "heroImagePrompt": hero_prompt.strip(),
        "mediaPrompts": cleaned_media_prompts,
        "meta": meta,
    }


def _build_testimonial_prompt(*, count: int, copy: str, product_context: str, today: str) -> str:
    return (
        "You are generating synthetic customer testimonials for a landing page.\n"
        "Output JSON only. Do not include markdown or commentary.\n"
        "Your response must be a single JSON object that starts with '{' and ends with '}'.\n"
        f"Return exactly {count} testimonials.\n\n"
        "Rules:\n"
        "- Each review must be 1-3 sentences, <= 600 characters.\n"
        "- Names must be <= 80 characters.\n"
        "- rating is an integer 1-5.\n"
        "- verified is a boolean.\n"
        "- Make each testimonial distinct (different personas, locations, and scenes).\n"
        "- persona should be a 1-2 sentence description of the reviewer (age range, context, motivation).\n"
        "- avatarPrompt should describe a realistic, candid portrait of that persona (no brand logos).\n"
        "- heroImagePrompt should describe a realistic lifestyle/product scene relevant to the review.\n"
        "- mediaPrompts must include 3 short image prompts tied to the review; keep them general and product-agnostic (refer to 'the product' instead of specific brand names).\n"
        "- If the review references the product, include the product in at least one mediaPrompt using generic wording.\n"
        "- avatarPrompt and heroImagePrompt must be unique per testimonial.\n"
        "- meta.location (optional) should be <= 120 characters.\n"
        f"- meta.date (optional) must be YYYY-MM-DD; today is {today}.\n"
        "- Keep claims compliant; avoid medical promises or unrealistic outcomes.\n"
        "- Do not mention being AI or synthetic.\n\n"
        "Product context:\n"
        f"{product_context}\n"
        "Page copy:\n"
        f"{copy}\n\n"
        "Return JSON with this exact shape:\n"
        '{ "testimonials": [ { "name": "...", "verified": true, "rating": 5, "review": "...", "persona": "...", "avatarPrompt": "...", "heroImagePrompt": "...", "mediaPrompts": ["...", "...", "..."], "meta": { "location": "...", "date": "YYYY-MM-DD" } } ] }\n'
    )


def _parse_testimonials_response(raw: str, *, model_id: str) -> dict[str, Any]:
    if raw is None:
        raise TestimonialGenerationError(
            f"Testimonials response was empty (model={model_id})."
        )
    text = raw.strip()
    if not text:
        raise TestimonialGenerationError(
            f"Testimonials response was empty (model={model_id})."
        )

    def _try_parse(candidate: str) -> Optional[dict[str, Any]]:
        if not candidate:
            return None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    parsed = _try_parse(text)
    if parsed is not None:
        return parsed

    if "```" in text:
        start = text.find("```")
        while start != -1:
            end = text.find("```", start + 3)
            if end == -1:
                break
            block = text[start + 3 : end].strip()
            if block.lower().startswith("json"):
                block = block[4:].strip()
            parsed = _try_parse(block)
            if parsed is not None:
                return parsed
            start = text.find("```", end + 3)

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        parsed = _try_parse(text[first : last + 1])
        if parsed is not None:
            return parsed

    snippet = text[:300].replace("\n", "\\n")
    raise TestimonialGenerationError(
        f"Testimonials response was not valid JSON (model={model_id}). Snippet: {snippet}"
    )


def generate_funnel_page_testimonials(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    draft_version_id: Optional[str] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    synthetic: bool = True,
) -> tuple[FunnelPageVersion, dict[str, Any], list[dict[str, Any]]]:
    if not synthetic:
        raise TestimonialGenerationError("Non-synthetic testimonial generation is not supported yet.")

    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise TestimonialGenerationNotFoundError("Funnel not found")

    page = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
    ).first()
    if not page:
        raise TestimonialGenerationNotFoundError("Page not found")

    base_puck = current_puck_data
    if base_puck is None and draft_version_id:
        draft = session.scalars(
            select(FunnelPageVersion).where(
                FunnelPageVersion.page_id == page_id,
                FunnelPageVersion.id == draft_version_id,
            )
        ).first()
        if not draft:
            raise TestimonialGenerationNotFoundError("Draft version not found")
        base_puck = draft.puck_data
    if base_puck is None:
        raise TestimonialGenerationError(
            "currentPuckData or draftVersionId is required to generate testimonials."
        )
    if not isinstance(base_puck, dict):
        raise TestimonialGenerationError("puckData must be a JSON object.")

    resolved_template_id = template_id or page.template_id
    if not resolved_template_id:
        raise TestimonialGenerationError("templateId is required to generate testimonials.")
    template_kind = None
    if resolved_template_id == "sales-pdp":
        template_kind = "sales-pdp"
    elif resolved_template_id == "pre-sales-listicle":
        template_kind = "pre-sales-listicle"
    else:
        raise TestimonialGenerationError(f"Template {resolved_template_id} is not supported for testimonials.")

    if template_kind == "pre-sales-listicle":
        _force_pre_sales_review_media_templates(base_puck)
    _apply_review_wall_template_mix(base_puck, template_kind)

    groups, contexts = _collect_testimonial_targets(base_puck, template_kind)

    product, _, product_context = _load_product_context(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        funnel=funnel,
    )
    if not product:
        raise TestimonialGenerationError("Product context is required to generate testimonials.")

    # Validate that the product has a primary image configured (required by business rules).
    _resolve_product_primary_image(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        product=product,
    )

    copy_text = _extract_copy_lines(base_puck)
    if not copy_text.strip():
        raise TestimonialGenerationError("Unable to extract page copy for testimonial generation.")

    llm = LLMClient()
    model_id = model or llm.default_model
    today = datetime.now(timezone.utc).date().isoformat()
    testimonials: list[dict[str, Any]] = []
    batch_size = 6
    sales_review_wall_social_index = 0

    for start in range(0, len(groups), batch_size):
        batch = groups[start : start + batch_size]
        prompt = _build_testimonial_prompt(
            count=len(batch),
            copy=copy_text,
            product_context=product_context,
            today=today,
        )

        params = LLMGenerationParams(
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            use_reasoning=True,
            use_web_search=False,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "Testimonials",
                    "strict": True,
                    "schema": _testimonial_output_schema(len(batch)),
                },
            },
        )
        raw = llm.generate_text(prompt, params=params)
        parsed = _parse_testimonials_response(raw, model_id=model_id)
        batch_items = parsed.get("testimonials")
        if not isinstance(batch_items, list):
            raise TestimonialGenerationError("Testimonials response must include a testimonials array.")
        if len(batch_items) != len(batch):
            raise TestimonialGenerationError(
                f"Expected {len(batch)} testimonials, received {len(batch_items)}."
            )
        testimonials.extend(batch_items)

    generated: list[dict[str, Any]] = []
    try:
        with TestimonialRenderer() as renderer:
            for idx, group in enumerate(groups):
                validated = _validate_testimonial_payload(testimonials[idx] or {})

                if group.slide is not None:
                    group.slide["text"] = validated["review"]
                    group.slide["author"] = validated["name"]
                    group.slide["rating"] = validated["rating"]
                    group.slide["verified"] = validated["verified"]
                    if group.context:
                        group.context.dirty = True

                media_targets = [
                    render for render in group.renders if render.template == "testimonial_media"
                ]
                media_prompt_iter: Optional[Iterator[str]] = None
                if media_targets:
                    if len(media_targets) != 3:
                        raise TestimonialGenerationError(
                            "testimonial_media requires exactly 3 image slots for each review slide."
                        )
                    media_prompts = validated["mediaPrompts"]
                    if len(media_prompts) != len(media_targets):
                        raise TestimonialGenerationError(
                            "mediaPrompts must include exactly 3 prompts for testimonial media images."
                        )
                    media_prompt_iter = iter(media_prompts)

                for render in group.renders:
                    if render.template == "testimonial_media":
                        if media_prompt_iter is None:
                            raise TestimonialGenerationError(
                                "mediaPrompts are required for testimonial_media renders."
                            )
                        try:
                            prompt = next(media_prompt_iter)
                        except StopIteration as exc:
                            raise TestimonialGenerationError(
                                "Insufficient mediaPrompts provided for testimonial_media renders."
                            ) from exc

                        media_asset = create_funnel_image_asset(
                            session=session,
                            org_id=org_id,
                            client_id=str(funnel.client_id),
                            prompt=prompt,
                            aspect_ratio="3:4",
                            usage_context={
                                "kind": "testimonial_media_image",
                                "funnelId": funnel_id,
                                "pageId": page_id,
                                "target": render.label,
                            },
                            funnel_id=funnel_id,
                            product_id=str(funnel.product_id) if funnel.product_id else None,
                            tags=["funnel", "testimonial", "testimonial_media", "source"],
                        )

                        payload = {
                            "template": "testimonial_media",
                            "imageUrl": _public_asset_url(str(media_asset.public_id)),
                            "alt": f"Customer scene for {validated['name']}",
                        }
                        image_bytes = renderer.render_png(payload)
                        asset = create_funnel_upload_asset(
                            session=session,
                            org_id=org_id,
                            client_id=str(funnel.client_id),
                            content_bytes=image_bytes,
                            filename=f"testimonial-media-{page_id}-{idx + 1}.png",
                            content_type="image/png",
                            alt=f"Customer scene for {validated['name']}",
                            usage_context={
                                "kind": "testimonial_media_render",
                                "funnelId": funnel_id,
                                "pageId": page_id,
                                "target": render.label,
                            },
                            funnel_id=funnel_id,
                            product_id=str(funnel.product_id) if funnel.product_id else None,
                            tags=["funnel", "testimonial", "testimonial_media"],
                        )
                        render.image["assetPublicId"] = str(asset.public_id)
                        if "alt" not in render.image or not render.image.get("alt"):
                            render.image["alt"] = f"Customer scene for {validated['name']}"
                        if render.context:
                            render.context.dirty = True
                        generated.append(
                            {
                                "target": render.label,
                                "payload": payload,
                                "publicId": str(asset.public_id),
                                "assetId": str(asset.id),
                                "mediaSourcePublicId": str(media_asset.public_id),
                            }
                        )
                        continue

                    if render.template == "social_comment" and len(validated["review"]) > 600:
                        raise TestimonialGenerationError(
                            "Testimonial review must be 600 characters or fewer for social_comment renders."
                        )

                    if render.template == "review_card":
                        payload: dict[str, Any] = {
                            "template": "review_card",
                            "name": validated["name"],
                            "verified": validated["verified"],
                            "rating": validated["rating"],
                            "review": validated["review"],
                        }
                        if validated.get("meta") is not None:
                            payload["meta"] = validated["meta"]
                        payload["avatarPrompt"] = validated["avatarPrompt"]
                        payload["heroImagePrompt"] = validated["heroImagePrompt"]
                        payload["renderContext"] = {
                            "userContext": validated["persona"],
                            "pageCopy": copy_text,
                            "productContext": product_context,
                        }
                        image_model = os.getenv("TESTIMONIAL_RENDERER_IMAGE_MODEL")
                        if image_model:
                            payload["imageModel"] = image_model

                        image_bytes = renderer.render_png(payload)
                        asset = create_funnel_upload_asset(
                            session=session,
                            org_id=org_id,
                            client_id=str(funnel.client_id),
                            content_bytes=image_bytes,
                            filename=f"testimonial-{page_id}-{idx + 1}.png",
                            content_type="image/png",
                            alt=f"Testimonial from {validated['name']}",
                            usage_context={
                                "kind": "testimonial_render",
                                "funnelId": funnel_id,
                                "pageId": page_id,
                                "target": render.label,
                            },
                            funnel_id=funnel_id,
                            product_id=str(funnel.product_id) if funnel.product_id else None,
                            tags=["funnel", "testimonial", "review_card"],
                        )
                        render.image["assetPublicId"] = str(asset.public_id)
                        if "alt" not in render.image or not render.image.get("alt"):
                            render.image["alt"] = f"Review from {validated['name']}"
                        if render.context:
                            render.context.dirty = True
                        generated.append(
                            {
                                "target": render.label,
                                "payload": payload,
                                "publicId": str(asset.public_id),
                                "assetId": str(asset.id),
                            }
                        )
                        continue

                    avatar_asset = create_funnel_image_asset(
                        session=session,
                        org_id=org_id,
                        client_id=str(funnel.client_id),
                        prompt=validated["avatarPrompt"],
                        aspect_ratio="1:1",
                        usage_context={
                            "kind": "testimonial_social_avatar",
                            "funnelId": funnel_id,
                            "pageId": page_id,
                            "target": render.label,
                        },
                        funnel_id=funnel_id,
                        product_id=str(funnel.product_id) if funnel.product_id else None,
                        tags=["funnel", "testimonial", "social_comment", "avatar"],
                    )
                    attachment_asset = create_funnel_image_asset(
                        session=session,
                        org_id=org_id,
                        client_id=str(funnel.client_id),
                        prompt=validated["heroImagePrompt"],
                        aspect_ratio="4:3",
                        usage_context={
                            "kind": "testimonial_social_attachment",
                            "funnelId": funnel_id,
                            "pageId": page_id,
                            "target": render.label,
                        },
                        funnel_id=funnel_id,
                        product_id=str(funnel.product_id) if funnel.product_id else None,
                        tags=["funnel", "testimonial", "social_comment", "attachment"],
                    )
                    time_value = today
                    if isinstance(validated.get("meta"), dict):
                        meta_date = validated["meta"].get("date")
                        if isinstance(meta_date, str) and meta_date.strip():
                            time_value = meta_date.strip()

                    seed = sum(ord(ch) for ch in render.label) + idx
                    variant = seed % 3
                    replies = None
                    view_replies_text = None
                    reaction_count = 3 + (seed % 17)
                    follow_label = "Follow" if variant == 1 else None

                    is_sales_review_wall = (
                        template_kind == "sales-pdp"
                        and "sales_pdp.reviewWall.tiles" in render.label
                    )
                    if is_sales_review_wall:
                        force_reply = sales_review_wall_social_index % 2 == 0
                        sales_review_wall_social_index += 1
                        if force_reply:
                            replies = [
                                {
                                    "name": "Avery P.",
                                    "text": "Same here—this guide made everything feel manageable.",
                                    "avatarUrl": _public_asset_url(str(avatar_asset.public_id)),
                                    "meta": {"time": "2d"},
                                    "reactionCount": 2,
                                }
                            ]
                            view_replies_text = "View 1 reply"

                    if variant == 0:
                        reply_templates = [
                            "Same here—this guide made everything feel manageable.",
                            "Agreed. The steps were easy to follow.",
                            "We had a similar experience and it helped a lot.",
                        ]
                        reply_text = reply_templates[seed % len(reply_templates)]
                        replies = [
                            {
                                "name": "Avery P.",
                                "text": reply_text,
                                "avatarUrl": _public_asset_url(str(avatar_asset.public_id)),
                                "meta": {"time": "2d"},
                                "reactionCount": 2,
                            }
                        ]
                        view_replies_text = "View 1 reply"

                    payload = {
                        "template": "social_comment",
                        "header": {"title": "All comments", "showSortIcon": variant != 2},
                        "comments": [
                            {
                                "name": validated["name"],
                                "text": validated["review"],
                                "avatarUrl": _public_asset_url(str(avatar_asset.public_id)),
                                "attachmentUrl": _public_asset_url(
                                    str(attachment_asset.public_id)
                                ),
                                "meta": {
                                    "time": time_value,
                                    **({"followLabel": follow_label} if follow_label else {}),
                                },
                                "reactionCount": reaction_count,
                                **(
                                    {"replies": replies, "viewRepliesText": view_replies_text}
                                    if replies
                                    else {}
                                ),
                            }
                        ],
                    }
                    image_bytes = renderer.render_png(payload)
                    asset = create_funnel_upload_asset(
                        session=session,
                        org_id=org_id,
                        client_id=str(funnel.client_id),
                        content_bytes=image_bytes,
                        filename=f"testimonial-{page_id}-{idx + 1}.png",
                        content_type="image/png",
                        alt=f"Social comment from {validated['name']}",
                        usage_context={
                            "kind": "testimonial_render",
                            "funnelId": funnel_id,
                            "pageId": page_id,
                            "target": render.label,
                        },
                        funnel_id=funnel_id,
                        product_id=str(funnel.product_id) if funnel.product_id else None,
                        tags=["funnel", "testimonial", "social_comment"],
                    )
                    render.image["assetPublicId"] = str(asset.public_id)
                    if "alt" not in render.image or not render.image.get("alt"):
                        render.image["alt"] = f"Social comment from {validated['name']}"
                    if render.context:
                        render.context.dirty = True
                    generated.append(
                        {
                            "target": render.label,
                            "payload": payload,
                            "publicId": str(asset.public_id),
                            "assetId": str(asset.id),
                            "avatarPublicId": str(avatar_asset.public_id),
                            "attachmentPublicId": str(attachment_asset.public_id),
                        }
                    )
    except TestimonialRenderError as exc:
        raise TestimonialGenerationError(str(exc)) from exc

    missing_assets: list[str] = []
    for group in groups:
        for render in group.renders:
            asset_public_id = render.image.get("assetPublicId")
            if not isinstance(asset_public_id, str) or not asset_public_id.strip():
                missing_assets.append(render.label)
    if missing_assets:
        sample = "\n".join(f"- {label}" for label in missing_assets[:12])
        raise TestimonialGenerationError(
            "Testimonial generation did not populate all image slots:\n"
            f"{sample}"
        )

    if template_kind == "sales-pdp":
        review_wall_images = _collect_sales_pdp_review_wall_images(groups)
        _sync_sales_pdp_guarantee_feed_images(
            base_puck,
            review_wall_images=review_wall_images,
        )

    for ctx in contexts:
        if ctx.dirty:
            ctx.props[ctx.key] = json.dumps(ctx.parsed, ensure_ascii=False)

    ai_metadata = {
        "kind": "testimonial_generation",
        "model": model_id,
        "temperature": temperature,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "synthetic": synthetic,
        "testimonialsProvenance": {"source": "synthetic" if synthetic else "production"},
        "generatedTestimonials": generated,
        "actorUserId": user_id,
        "ideaWorkspaceId": idea_workspace_id,
        "templateId": resolved_template_id,
    }

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=base_puck,
        source=FunnelPageVersionSourceEnum.ai,
        created_at=datetime.now(timezone.utc),
        ai_metadata=ai_metadata,
    )
    session.add(version)
    session.commit()
    session.refresh(version)

    return version, base_puck, generated
