from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


class TestimonialRenderError(RuntimeError):
    pass


_TEMPLATE_TYPES = {
    "review_card",
    "social_comment",
    "social_comment_no_header",
    "social_comment_instagram",
    "testimonial_media",
}
_MAX_NAME_LENGTH = 80
_MAX_REVIEW_LENGTH = 800
_MAX_COMMENT_LENGTH = 600
_MAX_HEADER_TITLE = 40
_MAX_META_LABEL = 24
_MAX_VIEW_REPLIES = 40
_MAX_INSTAGRAM_USERNAME = 40
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
        view_replies_text = _assert_string(comment.get("viewRepliesText"), f"{prefix}.viewRepliesText", _MAX_VIEW_REPLIES)

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

    raise TestimonialRenderError("Unsupported template.")
