from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse


class TestimonialRenderError(RuntimeError):
    pass


_TEMPLATE_TYPES = {
    "review_card",
    "social_comment",
    "social_comment_no_header",
    "social_comment_instagram",
    "testimonial_media",
    "pdp_ugc_standard",
    "pdp_qa_ugc",
    "pdp_bold_claim",
    "pdp_personal_highlight",
}
_MAX_NAME_LENGTH = 80
_MAX_REVIEW_LENGTH = 800
_MAX_COMMENT_LENGTH = 600
_MAX_HEADER_TITLE = 40
_MAX_META_LABEL = 24
_MAX_VIEW_REPLIES = 40
_MAX_INSTAGRAM_USERNAME = 40
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PDP_OUTPUT_PRESETS = {"tiktok", "feed", "square"}
_PDP_DEFAULT_OUTPUT_PRESET = "tiktok"
_PDP_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_MAX_PDP_HANDLE = 40
_MAX_PDP_COMMENT = 220
_MAX_PDP_CTA = 60
_MAX_PDP_LOGO_TEXT = 24
_MAX_PDP_RATING_VALUE = 16
_MAX_PDP_RATING_DETAIL = 60
_MAX_PDP_BRAND_NAME = 80
_MAX_PDP_BRAND_NOTES = 260
_NANO_REFERENCE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_NANO_REFERENCE_DATA_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
_PDP_DEFAULT_AVATAR_PATH = Path(__file__).resolve().parent / "templates" / "assets" / "pdp-default-avatar.svg"


def _is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def _assert_string(value: Any, field: str, max_length: int | None = None) -> str:
    if not isinstance(value, str):
        raise TestimonialRenderError(f"{field} must be a string.")
    trimmed = value.strip()
    if not trimmed:
        raise TestimonialRenderError(f"{field} must not be empty.")
    if max_length is not None and len(trimmed) > max_length:
        raise TestimonialRenderError(f"{field} must be at most {max_length} characters.")
    return trimmed


def _assert_optional_string(value: Any, field: str, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    return _assert_string(value, field, max_length)


def _assert_boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise TestimonialRenderError(f"{field} must be a boolean.")
    return value


def _assert_rating(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TestimonialRenderError(f"{field} must be an integer between 1 and 5.")
    if value < 1 or value > 5:
        raise TestimonialRenderError(f"{field} must be an integer between 1 and 5.")
    return value


def _assert_color(value: Any, field: str) -> str:
    color = _assert_string(value, field, 24)
    if not _PDP_COLOR_PATTERN.match(color):
        raise TestimonialRenderError(f"{field} must be a hex color like #fff or #ffffff.")
    return color


def _resolve_image_url(value: Any, base_dir: Optional[Path], field: str) -> str:
    url = _assert_string(value, field)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("data:"):
        return url
    if url.startswith("file://"):
        file_path = url.replace("file://", "", 1)
        if not Path(file_path).exists():
            raise TestimonialRenderError(f"{field} file does not exist: {file_path}")
        return url

    resolved_base = base_dir or Path.cwd()
    candidate = Path(url)
    resolved_path = candidate if candidate.is_absolute() else (resolved_base / candidate)
    resolved_path = resolved_path.resolve()
    if not resolved_path.exists():
        raise TestimonialRenderError(f"{field} file does not exist: {resolved_path}")
    return resolved_path.as_uri()


def _resolve_prompt_file(value: Any, base_dir: Optional[Path], field: str, max_length: int) -> str:
    prompt_path = _assert_string(value, field, 400)
    resolved_base = base_dir or Path.cwd()
    candidate = Path(prompt_path)
    resolved_path = candidate if candidate.is_absolute() else (resolved_base / candidate)
    resolved_path = resolved_path.resolve()
    if not resolved_path.exists():
        raise TestimonialRenderError(f"{field} file does not exist: {resolved_path}")
    try:
        raw_prompt = resolved_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TestimonialRenderError(f"Unable to read {field} file: {resolved_path}") from exc
    return _assert_string(raw_prompt, field, max_length)


def _assert_nano_reference_image_url(resolved_url: str, field: str) -> None:
    trimmed = _assert_string(resolved_url, field)
    if trimmed.startswith("data:"):
        match = re.match(r"^data:([^;]+);", trimmed, flags=re.IGNORECASE)
        mime_type = match.group(1).strip().lower() if match else ""
        if mime_type not in _NANO_REFERENCE_DATA_MIME_TYPES:
            raise TestimonialRenderError(f"{field} must use png/jpg/jpeg/webp when using data URLs.")
        return

    path_like = trimmed
    if trimmed.startswith("http://") or trimmed.startswith("https://") or trimmed.startswith("file://"):
        parsed = urlparse(trimmed)
        path_like = parsed.path or trimmed

    ext = Path(path_like).suffix.lower()
    if ext not in _NANO_REFERENCE_EXTENSIONS:
        raise TestimonialRenderError(f"{field} must reference a png/jpg/jpeg/webp image.")


def _resolve_pdp_default_avatar_url() -> str:
    if not _PDP_DEFAULT_AVATAR_PATH.exists():
        raise TestimonialRenderError(f"Default PDP avatar file does not exist: {_PDP_DEFAULT_AVATAR_PATH}")
    return _PDP_DEFAULT_AVATAR_PATH.resolve().as_uri()


def _validate_meta(
    meta: Any,
    *,
    allowed_keys: list[str],
    field_prefix: str,
) -> Optional[dict[str, Any]]:
    if meta is None:
        return None
    if not _is_plain_object(meta):
        raise TestimonialRenderError(f"{field_prefix} must be an object when provided.")

    allowed_key_set = set(allowed_keys)
    for key in meta.keys():
        if key not in allowed_key_set:
            raise TestimonialRenderError(f"{field_prefix} contains unsupported key: {key}")

    output: dict[str, Any] = {}
    if meta.get("location") is not None:
        output["location"] = _assert_string(meta.get("location"), f"{field_prefix}.location", 120)
    if meta.get("date") is not None:
        date_value = _assert_string(meta.get("date"), f"{field_prefix}.date", 32)
        if not _DATE_PATTERN.match(date_value):
            raise TestimonialRenderError(f"{field_prefix}.date must use YYYY-MM-DD format.")
        output["date"] = date_value
    if meta.get("timeAgo") is not None:
        output["timeAgo"] = _assert_string(meta.get("timeAgo"), f"{field_prefix}.timeAgo", 24)
    if meta.get("reactionCount") is not None:
        reaction_count = meta.get("reactionCount")
        if not isinstance(reaction_count, int) or isinstance(reaction_count, bool) or reaction_count < 0:
            raise TestimonialRenderError(f"{field_prefix}.reactionCount must be a non-negative integer.")
        output["reactionCount"] = reaction_count

    return output


def _validate_header(header: Any) -> dict[str, Any]:
    if not _is_plain_object(header):
        raise TestimonialRenderError("header must be an object.")
    allowed_keys = {"title", "showSortIcon"}
    for key in header.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"header contains unsupported key: {key}")

    title = _assert_string(header.get("title"), "header.title", _MAX_HEADER_TITLE)
    if not isinstance(header.get("showSortIcon"), bool):
        raise TestimonialRenderError("header.showSortIcon must be a boolean.")

    return {"title": title, "showSortIcon": bool(header.get("showSortIcon"))}


def _validate_thread_meta(meta: Any, prefix: str) -> dict[str, Any]:
    if not _is_plain_object(meta):
        raise TestimonialRenderError(f"{prefix} must be an object.")
    allowed_keys = {"time", "followLabel", "authorLabel"}
    for key in meta.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"{prefix} contains unsupported key: {key}")

    time_value = _assert_string(meta.get("time"), f"{prefix}.time", 24)
    output: dict[str, Any] = {"time": time_value}

    if meta.get("followLabel") is not None:
        output["followLabel"] = _assert_string(meta.get("followLabel"), f"{prefix}.followLabel", _MAX_META_LABEL)
    if meta.get("authorLabel") is not None:
        output["authorLabel"] = _assert_string(meta.get("authorLabel"), f"{prefix}.authorLabel", _MAX_META_LABEL)

    return output


def _validate_reaction_count(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TestimonialRenderError(f"{field} must be a non-negative integer.")
    return value


def _validate_thread_comment(comment: Any, *, base_dir: Optional[Path], prefix: str) -> dict[str, Any]:
    if not _is_plain_object(comment):
        raise TestimonialRenderError(f"{prefix} must be an object.")

    allowed_keys = {
        "name",
        "text",
        "avatarUrl",
        "meta",
        "reactionCount",
        "attachmentUrl",
        "replies",
        "viewRepliesText",
    }
    for key in comment.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"{prefix} contains unsupported key: {key}")

    name = _assert_string(comment.get("name"), f"{prefix}.name", _MAX_NAME_LENGTH)
    text = _assert_string(comment.get("text"), f"{prefix}.text", _MAX_COMMENT_LENGTH)
    avatar_url: str | None = None
    if comment.get("avatarUrl") is not None:
        avatar_url = _resolve_image_url(comment.get("avatarUrl"), base_dir, f"{prefix}.avatarUrl")
    meta = _validate_thread_meta(comment.get("meta"), f"{prefix}.meta")

    reaction_count: int | None = None
    if comment.get("reactionCount") is not None:
        reaction_count = _validate_reaction_count(comment.get("reactionCount"), f"{prefix}.reactionCount")

    attachment_url: str | None = None
    if comment.get("attachmentUrl") is not None:
        attachment_url = _resolve_image_url(comment.get("attachmentUrl"), base_dir, f"{prefix}.attachmentUrl")

    view_replies_text: str | None = None
    if comment.get("viewRepliesText") is not None:
        view_replies_text = _assert_string(
            comment.get("viewRepliesText"), f"{prefix}.viewRepliesText", _MAX_VIEW_REPLIES
        )

    replies: list[dict[str, Any]] | None = None
    if comment.get("replies") is not None:
        raw_replies = comment.get("replies")
        if not isinstance(raw_replies, list) or len(raw_replies) == 0:
            raise TestimonialRenderError(f"{prefix}.replies must be a non-empty array when provided.")
        replies = [
            _validate_thread_comment(reply, base_dir=base_dir, prefix=f"{prefix}.replies[{idx}]")
            for idx, reply in enumerate(raw_replies)
        ]

    return {
        "name": name,
        "text": text,
        "avatarUrl": avatar_url,
        "meta": meta,
        "reactionCount": reaction_count,
        "attachmentUrl": attachment_url,
        "replies": replies,
        "viewRepliesText": view_replies_text,
    }


def _validate_instagram_post(post: Any, *, base_dir: Optional[Path]) -> dict[str, Any]:
    if not _is_plain_object(post):
        raise TestimonialRenderError("post must be an object.")
    allowed_keys = {"username", "avatarUrl", "location", "likeCount", "dateLabel"}
    for key in post.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"post contains unsupported key: {key}")
    username = _assert_string(post.get("username"), "post.username", _MAX_INSTAGRAM_USERNAME)
    avatar_url: str | None = None
    if post.get("avatarUrl") is not None:
        avatar_url = _resolve_image_url(post.get("avatarUrl"), base_dir, "post.avatarUrl")
    location = ""
    if post.get("location") is not None:
        location = _assert_string(post.get("location"), "post.location", 120)
    like_count = _validate_reaction_count(post.get("likeCount"), "post.likeCount")
    date_label = _assert_string(post.get("dateLabel"), "post.dateLabel", 40)
    return {
        "username": username,
        "avatarUrl": avatar_url,
        "location": location,
        "likeCount": like_count,
        "dateLabel": date_label,
    }


def _validate_pdp_output(output: Any) -> dict[str, str]:
    if output is None:
        return {"preset": _PDP_DEFAULT_OUTPUT_PRESET}
    if not _is_plain_object(output):
        raise TestimonialRenderError("output must be an object when provided.")
    allowed_keys = {"preset"}
    for key in output.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"output contains unsupported key: {key}")

    preset = _assert_string(output.get("preset"), "output.preset", 24).lower()
    if preset not in _PDP_OUTPUT_PRESETS:
        allowed = ", ".join(sorted(_PDP_OUTPUT_PRESETS))
        raise TestimonialRenderError(f"output.preset must be one of: {allowed}")
    return {"preset": preset}


def _validate_pdp_brand_palette(palette: Any) -> dict[str, str]:
    if not _is_plain_object(palette):
        raise TestimonialRenderError("brand.assets.palette must be an object when provided.")
    allowed_keys = {"primary", "secondary", "accent"}
    for key in palette.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"brand.assets.palette contains unsupported key: {key}")

    output: dict[str, str] = {}
    if palette.get("primary") is not None:
        output["primary"] = _assert_color(palette.get("primary"), "brand.assets.palette.primary")
    if palette.get("secondary") is not None:
        output["secondary"] = _assert_color(palette.get("secondary"), "brand.assets.palette.secondary")
    if palette.get("accent") is not None:
        output["accent"] = _assert_color(palette.get("accent"), "brand.assets.palette.accent")
    if not output:
        raise TestimonialRenderError("brand.assets.palette must include at least one color token.")
    return output


def _validate_pdp_brand_assets(assets: Any, base_dir: Optional[Path]) -> dict[str, Any] | None:
    if assets is None:
        return None
    if not _is_plain_object(assets):
        raise TestimonialRenderError("brand.assets must be an object when provided.")
    allowed_keys = {"logoUrl", "referenceImages", "palette", "notes"}
    for key in assets.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"brand.assets contains unsupported key: {key}")

    logo_url: str | None = None
    if assets.get("logoUrl") is not None:
        logo_url = _resolve_image_url(assets.get("logoUrl"), base_dir, "brand.assets.logoUrl")
        _assert_nano_reference_image_url(logo_url, "brand.assets.logoUrl")

    reference_images: list[str] | None = None
    if assets.get("referenceImages") is not None:
        raw_images = assets.get("referenceImages")
        if not isinstance(raw_images, list) or len(raw_images) == 0:
            raise TestimonialRenderError("brand.assets.referenceImages must be a non-empty array when provided.")
        reference_images = [
            _resolve_image_url(entry, base_dir, f"brand.assets.referenceImages[{idx}]")
            for idx, entry in enumerate(raw_images)
        ]
        for idx, image_url in enumerate(reference_images):
            _assert_nano_reference_image_url(image_url, f"brand.assets.referenceImages[{idx}]")

    palette: dict[str, str] | None = None
    if assets.get("palette") is not None:
        palette = _validate_pdp_brand_palette(assets.get("palette"))

    notes = _assert_optional_string(assets.get("notes"), "brand.assets.notes", _MAX_PDP_BRAND_NOTES)
    if not logo_url and not reference_images and not palette and not notes:
        raise TestimonialRenderError(
            "brand.assets must include at least one of logoUrl, referenceImages, palette, or notes."
        )

    return {
        "logoUrl": logo_url,
        "referenceImages": reference_images,
        "palette": palette,
        "notes": notes,
    }


def _validate_pdp_brand(brand: Any, base_dir: Optional[Path]) -> dict[str, Any]:
    if not _is_plain_object(brand):
        raise TestimonialRenderError("brand must be an object.")
    allowed_keys = {
        "logoUrl",
        "logoText",
        "stripBgColor",
        "stripTextColor",
        "name",
        "assets",
    }
    for key in brand.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"brand contains unsupported key: {key}")

    strip_bg_color = _assert_color(brand.get("stripBgColor"), "brand.stripBgColor")
    strip_text_color = _assert_color(brand.get("stripTextColor"), "brand.stripTextColor")

    logo_url: str | None = None
    if brand.get("logoUrl") is not None:
        logo_url = _resolve_image_url(brand.get("logoUrl"), base_dir, "brand.logoUrl")
    logo_text = _assert_optional_string(brand.get("logoText"), "brand.logoText", _MAX_PDP_LOGO_TEXT)
    if not logo_url and not logo_text:
        raise TestimonialRenderError("brand.logoUrl or brand.logoText is required.")

    name = _assert_optional_string(brand.get("name"), "brand.name", _MAX_PDP_BRAND_NAME)
    assets = _validate_pdp_brand_assets(brand.get("assets"), base_dir)
    return {
        "stripBgColor": strip_bg_color,
        "stripTextColor": strip_text_color,
        "logoUrl": logo_url,
        "logoText": logo_text,
        "name": name,
        "assets": assets,
    }


def _validate_pdp_rating(rating: Any) -> dict[str, str]:
    if not _is_plain_object(rating):
        raise TestimonialRenderError("rating must be an object.")
    allowed_keys = {"valueText", "detailText"}
    for key in rating.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"rating contains unsupported key: {key}")
    return {
        "valueText": _assert_string(rating.get("valueText"), "rating.valueText", _MAX_PDP_RATING_VALUE),
        "detailText": _assert_string(rating.get("detailText"), "rating.detailText", _MAX_PDP_RATING_DETAIL),
    }


def _validate_pdp_cta(cta: Any) -> dict[str, str]:
    if not _is_plain_object(cta):
        raise TestimonialRenderError("cta must be an object.")
    allowed_keys = {"text"}
    for key in cta.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"cta contains unsupported key: {key}")
    return {"text": _assert_string(cta.get("text"), "cta.text", _MAX_PDP_CTA)}


def _validate_pdp_prompt_vars(vars_payload: Any) -> dict[str, Any]:
    if not _is_plain_object(vars_payload):
        raise TestimonialRenderError("background.promptVars must be an object.")
    allowed_keys = {"product", "scene", "subject", "extra", "avoid"}
    for key in vars_payload.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"background.promptVars contains unsupported key: {key}")

    output: dict[str, Any] = {
        "product": _assert_string(vars_payload.get("product"), "background.promptVars.product", 220),
        "scene": _assert_optional_string(vars_payload.get("scene"), "background.promptVars.scene", 220),
        "subject": _assert_optional_string(vars_payload.get("subject"), "background.promptVars.subject", 220),
        "extra": _assert_optional_string(vars_payload.get("extra"), "background.promptVars.extra", 600),
    }
    if vars_payload.get("avoid") is not None:
        raw_avoid = vars_payload.get("avoid")
        if not isinstance(raw_avoid, list) or len(raw_avoid) == 0:
            raise TestimonialRenderError("background.promptVars.avoid must be a non-empty array when provided.")
        output["avoid"] = [
            _assert_string(entry, f"background.promptVars.avoid[{idx}]", 160)
            for idx, entry in enumerate(raw_avoid)
        ]
    else:
        output["avoid"] = None
    return output


def _validate_pdp_background(background: Any, base_dir: Optional[Path]) -> dict[str, Any]:
    if not _is_plain_object(background):
        raise TestimonialRenderError("background must be an object.")
    allowed_keys = {
        "imageUrl",
        "alt",
        "prompt",
        "promptFile",
        "promptVars",
        "referenceImages",
        "referenceFirst",
        "imageModel",
        "imageConfig",
    }
    for key in background.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"background contains unsupported key: {key}")

    image_url: str | None = None
    if background.get("imageUrl") is not None:
        image_url = _resolve_image_url(background.get("imageUrl"), base_dir, "background.imageUrl")
    alt = _assert_optional_string(background.get("alt"), "background.alt", 200)
    prompt = _assert_optional_string(background.get("prompt"), "background.prompt", 6000)
    if prompt is not None and background.get("promptFile") is not None:
        raise TestimonialRenderError("Provide either background.prompt or background.promptFile, not both.")
    if background.get("promptFile") is not None:
        prompt = _resolve_prompt_file(background.get("promptFile"), base_dir, "background.promptFile", 6000)
    prompt_vars = (
        _validate_pdp_prompt_vars(background.get("promptVars"))
        if background.get("promptVars") is not None
        else None
    )
    if prompt and prompt_vars:
        raise TestimonialRenderError("Provide either background.prompt or background.promptVars, not both.")
    if image_url and (prompt or prompt_vars):
        raise TestimonialRenderError(
            "Provide either background.imageUrl or background.prompt/background.promptVars, not both."
        )
    if not image_url and not prompt and not prompt_vars:
        raise TestimonialRenderError(
            "background.imageUrl is required unless background.prompt or background.promptVars is provided."
        )

    reference_images: list[str] | None = None
    if background.get("referenceImages") is not None:
        raw_reference_images = background.get("referenceImages")
        if not isinstance(raw_reference_images, list) or len(raw_reference_images) == 0:
            raise TestimonialRenderError("background.referenceImages must be a non-empty array when provided.")
        reference_images = [
            _resolve_image_url(entry, base_dir, f"background.referenceImages[{idx}]")
            for idx, entry in enumerate(raw_reference_images)
        ]

    reference_first: bool | None = None
    if background.get("referenceFirst") is not None:
        reference_first = _assert_boolean(background.get("referenceFirst"), "background.referenceFirst")

    image_model = _assert_optional_string(background.get("imageModel"), "background.imageModel", 120)
    image_config: dict[str, Any] | None = None
    if background.get("imageConfig") is not None:
        if not _is_plain_object(background.get("imageConfig")):
            raise TestimonialRenderError("background.imageConfig must be an object when provided.")
        image_config = dict(background.get("imageConfig"))

    if image_url and (
        reference_images is not None
        or reference_first is not None
        or image_model is not None
        or image_config is not None
    ):
        raise TestimonialRenderError(
            "background.referenceImages/referenceFirst/imageModel/imageConfig are only allowed when "
            "generating a background (omit background.imageUrl)."
        )

    return {
        "imageUrl": image_url,
        "alt": alt,
        "prompt": prompt,
        "promptVars": prompt_vars,
        "referenceImages": reference_images,
        "referenceFirst": reference_first,
        "imageModel": image_model,
        "imageConfig": image_config,
    }


def _validate_pdp_comment(comment: Any, *, base_dir: Optional[Path], prefix: str) -> dict[str, Any]:
    if not _is_plain_object(comment):
        raise TestimonialRenderError(f"{prefix} must be an object.")
    allowed_keys = {"handle", "text", "questionText", "avatarUrl", "verified"}
    for key in comment.keys():
        if key not in allowed_keys:
            raise TestimonialRenderError(f"{prefix} contains unsupported key: {key}")

    handle = _assert_string(comment.get("handle"), f"{prefix}.handle", _MAX_PDP_HANDLE)
    text = _assert_string(comment.get("text"), f"{prefix}.text", _MAX_PDP_COMMENT)
    question_text = _assert_optional_string(comment.get("questionText"), f"{prefix}.questionText", 140)
    avatar_url = _resolve_pdp_default_avatar_url()
    if comment.get("avatarUrl") is not None:
        if not isinstance(comment.get("avatarUrl"), str):
            raise TestimonialRenderError(f"{prefix}.avatarUrl must be a string.")
        candidate = str(comment.get("avatarUrl")).strip()
        if candidate:
            avatar_url = _resolve_image_url(candidate, base_dir, f"{prefix}.avatarUrl")
    verified: bool | None = None
    if comment.get("verified") is not None:
        verified = _assert_boolean(comment.get("verified"), f"{prefix}.verified")
    return {
        "handle": handle,
        "text": text,
        "questionText": question_text,
        "avatarUrl": avatar_url,
        "verified": verified,
    }


def _validate_pdp_comments(
    *,
    comment: Any,
    comments: Any,
    base_dir: Optional[Path],
) -> list[dict[str, Any]]:
    if comments is not None:
        if not isinstance(comments, list) or len(comments) == 0:
            raise TestimonialRenderError("comments must be a non-empty array.")
        if len(comments) > 2:
            raise TestimonialRenderError("comments must contain at most 2 items for pdp_ugc_standard.")
        return [
            _validate_pdp_comment(entry, base_dir=base_dir, prefix=f"comments[{idx}]")
            for idx, entry in enumerate(comments)
        ]

    if comment is None:
        raise TestimonialRenderError("comment is required.")

    return [_validate_pdp_comment(comment, base_dir=base_dir, prefix="comment")]


def validate_payload(payload: Any, *, base_dir: Optional[Path] = None) -> dict[str, Any]:
    if not _is_plain_object(payload):
        raise TestimonialRenderError("Payload must be an object.")

    template = payload.get("template")
    if not isinstance(template, str) or template not in _TEMPLATE_TYPES:
        allowed = ", ".join(sorted(_TEMPLATE_TYPES))
        raise TestimonialRenderError(f"template must be one of: {allowed}")

    if template == "review_card":
        name = _assert_string(payload.get("name"), "name", _MAX_NAME_LENGTH)
        review = _assert_string(payload.get("review"), "review", _MAX_REVIEW_LENGTH)
        meta = _validate_meta(
            payload.get("meta"),
            allowed_keys=["location", "date"],
            field_prefix="meta",
        )

        output: dict[str, Any] = dict(payload)
        output["template"] = template
        output["name"] = name
        output["review"] = review
        output["meta"] = meta
        output["verified"] = _assert_boolean(payload.get("verified"), "verified")
        output["rating"] = _assert_rating(payload.get("rating"), "rating")

        if payload.get("heroImageUrl") is not None:
            output["heroImageUrl"] = _resolve_image_url(payload.get("heroImageUrl"), base_dir, "heroImageUrl")
        if payload.get("avatarUrl") is not None:
            output["avatarUrl"] = _resolve_image_url(payload.get("avatarUrl"), base_dir, "avatarUrl")

        return output

    if template == "social_comment":
        header = _validate_header(payload.get("header"))
        raw_comments = payload.get("comments")
        if not isinstance(raw_comments, list) or len(raw_comments) == 0:
            raise TestimonialRenderError("comments must be a non-empty array.")
        comments = [
            _validate_thread_comment(comment, base_dir=base_dir, prefix=f"comments[{idx}]")
            for idx, comment in enumerate(raw_comments)
        ]

        output = dict(payload)
        output["template"] = template
        output["header"] = header
        output["comments"] = comments
        return output

    if template == "social_comment_no_header":
        raw_comments = payload.get("comments")
        if not isinstance(raw_comments, list) or len(raw_comments) == 0:
            raise TestimonialRenderError("comments must be a non-empty array.")
        comments = [
            _validate_thread_comment(comment, base_dir=base_dir, prefix=f"comments[{idx}]")
            for idx, comment in enumerate(raw_comments)
        ]
        output = dict(payload)
        output["template"] = template
        output["comments"] = comments
        return output

    if template == "social_comment_instagram":
        post = _validate_instagram_post(payload.get("post"), base_dir=base_dir)
        raw_comments = payload.get("comments")
        if not isinstance(raw_comments, list) or len(raw_comments) == 0:
            raise TestimonialRenderError("comments must be a non-empty array.")
        comments = [
            _validate_thread_comment(comment, base_dir=base_dir, prefix=f"comments[{idx}]")
            for idx, comment in enumerate(raw_comments)
        ]
        output = dict(payload)
        output["template"] = template
        output["post"] = post
        output["comments"] = comments
        return output

    if template == "testimonial_media":
        image_url = _resolve_image_url(payload.get("imageUrl"), base_dir, "imageUrl")
        alt: str | None = None
        if payload.get("alt") is not None:
            alt = _assert_string(payload.get("alt"), "alt", 200)
        output = dict(payload)
        output["template"] = template
        output["imageUrl"] = image_url
        output["alt"] = alt
        return output

    if template in {"pdp_ugc_standard", "pdp_qa_ugc", "pdp_bold_claim", "pdp_personal_highlight"}:
        output = dict(payload)
        output["template"] = template
        output["output"] = _validate_pdp_output(payload.get("output"))
        output["brand"] = _validate_pdp_brand(payload.get("brand"), base_dir)
        output["rating"] = _validate_pdp_rating(payload.get("rating"))
        output["cta"] = _validate_pdp_cta(payload.get("cta"))
        output["background"] = _validate_pdp_background(payload.get("background"), base_dir)

        if template == "pdp_ugc_standard":
            comments = _validate_pdp_comments(
                comment=payload.get("comment"),
                comments=payload.get("comments"),
                base_dir=base_dir,
            )
            output["comment"] = comments[0]
            output["comments"] = comments
            return output

        if payload.get("comments") is not None:
            raise TestimonialRenderError(f"comments is not supported for template {template}.")

        output["comment"] = _validate_pdp_comment(payload.get("comment"), base_dir=base_dir, prefix="comment")
        if template == "pdp_qa_ugc" and not output["comment"].get("questionText"):
            raise TestimonialRenderError("comment.questionText is required for template pdp_qa_ugc.")
        return output

    raise TestimonialRenderError("Unsupported template.")
