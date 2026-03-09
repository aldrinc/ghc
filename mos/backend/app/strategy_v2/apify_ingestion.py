from __future__ import annotations

import concurrent.futures
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import queue
import re
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

from app.ads.apify_client import ApifyClient
from app.strategy_v2.contracts import (
    CandidateAssetMetrics,
    CompetitorAssetCandidate,
    ExternalVocCorpusItem,
    ProofAssetCandidate,
    SocialVideoObservation,
    VocEngagement,
)
from app.strategy_v2.score_candidate_assets import (
    derive_competitor_name_from_ref,
    derive_platform_from_ref,
    normalize_source_ref,
)


_DEFAULT_ALLOWED_ACTOR_IDS = {
    "curious_coder~facebook-ads-library-scraper",
    "clockworks/tiktok-scraper",
    "apify/instagram-scraper",
    "streamers/youtube-scraper",
    "streamers/youtube-comments-scraper",
    "practicaltools/apify-reddit-api",
    "apify/web-scraper",
    "apify/google-search-scraper",
    "emastra/trustpilot-scraper",
    "junglee/amazon-reviews-scraper",
    # Keep tilde-format aliases for compatibility with existing env values.
    "clockworks~tiktok-scraper",
    "apify~instagram-scraper",
    "streamers~youtube-scraper",
    "streamers~youtube-comments-scraper",
    "practicaltools~apify-reddit-api",
    "apify~web-scraper",
    "apify~google-search-scraper",
    "emastra~trustpilot-scraper",
    "junglee~amazon-reviews-scraper",
}

_TRUE_VALUES = {"1", "true", "yes", "on"}

_VIDEO_PLATFORMS = {"TIKTOK", "INSTAGRAM", "YOUTUBE"}

_SOURCE_TYPE_BY_PLATFORM: dict[str, str] = {
    "META": "META_AD",
    "TIKTOK": "TIKTOK_VIDEO",
    "INSTAGRAM": "INSTAGRAM_REEL",
    "YOUTUBE": "YOUTUBE_SHORT",
    "REDDIT": "REDDIT_THREAD",
    "WEB": "LANDING_PAGE",
}

_EXTERNAL_COMMENT_SOURCE_TYPE_BY_PLATFORM: dict[str, str] = {
    "TIKTOK": "TIKTOK_COMMENT",
    "INSTAGRAM": "IG_COMMENT",
    "YOUTUBE": "YT_COMMENT",
    "REDDIT": "REDDIT",
}

_ENGAGEMENT_WEIGHT_COMMENTS = 2
_ENGAGEMENT_WEIGHT_REPLIES = 2
_SOCIAL_HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9._]{3,64}$")
_REDDIT_ACTOR_MAX_ITEMS = 100
_SEARCH_HOSTS = {
    "google.com",
    "www.google.com",
    "google.co.uk",
    "google.ca",
    "google.com.au",
    "google.de",
    "google.fr",
    "google.es",
}
_DISALLOWED_DISCOVERY_HOST_TOKENS = (
    "googleadservices.com",
    "doubleclick.net",
    "adservice.google.com",
    "gstatic.com",
)
_URL_FIELD_CANDIDATES = (
    "url",
    "link",
    "href",
    "source_url",
    "sourceUrl",
    "canonical_url",
    "displayedUrl",
    "displayed_url",
    "targetUrl",
    "target_url",
)
_RESULT_CONTAINER_FIELDS = (
    "organicResults",
    "organic_results",
    "results",
    "items",
    "newsResults",
    "news_results",
    "relatedResults",
    "related_results",
    "knowledgeGraph",
    "knowledge_graph",
)
_TEXT_VALUE_FIELDS = (
    "body",
    "text",
    "selftext",
    "caption",
    "description",
    "content",
    "comment",
    "commentText",
    "title",
    "mainText",
    "bodyText",
)

ApifyProgressCallback = Callable[[dict[str, Any]], None]


def _emit_apify_progress(
    *,
    callback: ApifyProgressCallback | None,
    event: Mapping[str, Any],
) -> None:
    if callback is None:
        return
    callback(dict(event))


def _normalize_actor_id(actor_id: str) -> str:
    text = actor_id.strip()
    if "/" in text:
        owner, name = text.split("/", 1)
        if owner and name:
            return f"{owner}~{name}"
    return text


@dataclass(frozen=True)
class StrategyV2ApifyConfig:
    enabled: bool
    max_wait_seconds: int
    max_items_per_dataset: int
    max_actor_runs: int
    max_parallel_actor_runs: int
    discovery_fanout_enabled: bool
    discovery_fanout_max_urls_total: int
    discovery_fanout_max_urls_per_query: int
    discovery_fanout_max_urls_per_domain: int
    discovery_fanout_max_urls_per_run: int
    comment_enrichment_enabled: bool
    comment_enrichment_max_videos_per_platform: int
    comment_enrichment_max_comments_per_video: int
    allowed_actor_ids: frozenset[str]
    meta_actor_id: str
    tiktok_actor_id: str
    instagram_actor_id: str
    youtube_actor_id: str
    youtube_comments_actor_id: str
    reddit_actor_id: str
    web_actor_id: str


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _parse_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be > 0, got {value}.")
    return value


def _parse_allowed_actor_ids() -> frozenset[str]:
    raw = os.getenv("STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS")
    if raw is None or not raw.strip():
        return frozenset(_DEFAULT_ALLOWED_ACTOR_IDS)
    parsed: set[str] = set()
    trimmed = raw.strip()
    if trimmed.startswith("["):
        try:
            payload = json.loads(trimmed)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS must be valid JSON array or comma-separated string."
            ) from exc
        if not isinstance(payload, list):
            raise RuntimeError(
                "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS JSON payload must be an array of actor ids."
            )
        parsed = {
            str(item).strip()
            for item in payload
            if isinstance(item, str) and str(item).strip()
        }
    else:
        parsed = {item.strip() for item in trimmed.split(",") if item.strip()}
    if not parsed:
        raise RuntimeError(
            "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS resolved to an empty allowlist. "
            "Remediation: provide at least one allowed actor id."
        )
    return frozenset(parsed)


def _resolve_actor_max_items(
    *,
    input_payload: Mapping[str, Any],
    default_max_items: int,
    actor_id: str,
    config_id: str,
) -> int:
    candidate_fields = (
        "maxItems",
        "maxResults",
        "resultsLimit",
        "limit",
        "maxPosts",
        "maxCrawlPages",
        "maxRequestsPerCrawl",
    )
    for field_name in candidate_fields:
        raw_value = input_payload.get(field_name)
        if raw_value is None:
            continue
        parsed_value: int | None = None
        if isinstance(raw_value, int):
            parsed_value = raw_value
        elif isinstance(raw_value, float):
            parsed_value = int(raw_value)
        elif isinstance(raw_value, str) and raw_value.strip():
            try:
                parsed_value = int(raw_value.strip())
            except ValueError as exc:
                raise RuntimeError(
                    f"Strategy Apify config '{config_id}' has invalid {field_name}={raw_value!r} for actor '{actor_id}'."
                ) from exc
        if parsed_value is None:
            continue
        if parsed_value <= 0:
            raise RuntimeError(
                f"Strategy Apify config '{config_id}' has non-positive {field_name}={parsed_value} for actor '{actor_id}'."
            )
        return parsed_value
    return default_max_items


def _canonicalize_strategy_actor_input(
    *,
    actor_id: str,
    config_id: str,
    input_payload: Mapping[str, Any],
    default_max_items: int,
) -> dict[str, Any]:
    normalized_actor_id = _normalize_actor_id(actor_id)
    if normalized_actor_id == _normalize_actor_id("practicaltools/apify-reddit-api"):
        requested_urls = _extract_requested_urls_from_payload(input_payload)
        if not requested_urls:
            raise RuntimeError(
                f"Strategy Apify config '{config_id}' for actor '{actor_id}' must include at least one absolute reddit URL."
            )
        max_items = _resolve_actor_max_items(
            input_payload=input_payload,
            default_max_items=default_max_items,
            actor_id=actor_id,
            config_id=config_id,
        )
        # practicaltools/apify-reddit-api rejects maxItems > 100 with HTTP 400.
        max_items = min(max_items, _REDDIT_ACTOR_MAX_ITEMS)
        return _build_reddit_actor_input(urls=requested_urls, max_items=max_items)
    if normalized_actor_id == _normalize_actor_id("apify/web-scraper"):
        requested_urls = _extract_requested_urls_from_payload(input_payload)
        if not requested_urls:
            raise RuntimeError(
                f"Strategy Apify config '{config_id}' for actor '{actor_id}' must include at least one absolute web URL."
            )
        max_items = _resolve_actor_max_items(
            input_payload=input_payload,
            default_max_items=default_max_items,
            actor_id=actor_id,
            config_id=config_id,
        )
        return _build_web_actor_input(urls=requested_urls, max_items=max_items)
    return dict(input_payload)


def _normalize_strategy_apify_configs(
    raw_configs: list[Mapping[str, Any]],
    *,
    default_max_items: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_config_ids: set[str] = set()
    for idx, raw in enumerate(raw_configs):
        if not isinstance(raw, Mapping):
            raise RuntimeError(
                f"Strategy Apify config at index {idx} must be an object with config_id, actor_id, and input."
            )
        config_id = str(raw.get("config_id") or "").strip()
        actor_id = str(raw.get("actor_id") or "").strip()
        input_payload = raw.get("input")
        metadata_payload = raw.get("metadata")
        if not config_id:
            raise RuntimeError(
                f"Strategy Apify config at index {idx} is missing non-empty config_id."
            )
        if config_id in seen_config_ids:
            raise RuntimeError(
                f"Duplicate strategy Apify config_id '{config_id}' detected."
            )
        seen_config_ids.add(config_id)
        if not actor_id:
            raise RuntimeError(
                f"Strategy Apify config '{config_id}' is missing non-empty actor_id."
            )
        if not isinstance(input_payload, Mapping) or not dict(input_payload):
            raise RuntimeError(
                f"Strategy Apify config '{config_id}' must include a non-empty object in input."
            )
        if metadata_payload is not None and not isinstance(metadata_payload, Mapping):
            raise RuntimeError(
                f"Strategy Apify config '{config_id}' metadata must be an object when provided."
            )
        normalized.append(
            {
                "config_id": config_id,
                "actor_id": actor_id,
                "input": _canonicalize_strategy_actor_input(
                    actor_id=actor_id,
                    config_id=config_id,
                    input_payload=input_payload,
                    default_max_items=default_max_items,
                ),
                "metadata": dict(metadata_payload) if isinstance(metadata_payload, Mapping) else {},
            }
        )
    if not normalized:
        raise RuntimeError("Strategy Apify execution requires at least one valid config object.")
    return normalized


def load_strategy_v2_apify_config() -> StrategyV2ApifyConfig:
    return StrategyV2ApifyConfig(
        enabled=_parse_bool(os.getenv("STRATEGY_V2_APIFY_ENABLED"), default=False),
        max_wait_seconds=_parse_positive_int_env("STRATEGY_V2_APIFY_MAX_WAIT_SECONDS", 900),
        max_items_per_dataset=_parse_positive_int_env("STRATEGY_V2_APIFY_MAX_ITEMS_PER_DATASET", 500),
        max_actor_runs=_parse_positive_int_env("STRATEGY_V2_APIFY_MAX_ACTOR_RUNS", 100),
        max_parallel_actor_runs=_parse_positive_int_env("STRATEGY_V2_APIFY_MAX_PARALLEL_RUNS", 8),
        discovery_fanout_enabled=_parse_bool(
            os.getenv("STRATEGY_V2_APIFY_DISCOVERY_FANOUT_ENABLED"),
            default=True,
        ),
        discovery_fanout_max_urls_total=_parse_positive_int_env(
            "STRATEGY_V2_APIFY_DISCOVERY_FANOUT_MAX_URLS_TOTAL",
            240,
        ),
        discovery_fanout_max_urls_per_query=_parse_positive_int_env(
            "STRATEGY_V2_APIFY_DISCOVERY_FANOUT_MAX_URLS_PER_QUERY",
            8,
        ),
        discovery_fanout_max_urls_per_domain=_parse_positive_int_env(
            "STRATEGY_V2_APIFY_DISCOVERY_FANOUT_MAX_URLS_PER_DOMAIN",
            30,
        ),
        discovery_fanout_max_urls_per_run=_parse_positive_int_env(
            "STRATEGY_V2_APIFY_DISCOVERY_FANOUT_MAX_URLS_PER_RUN",
            25,
        ),
        comment_enrichment_enabled=_parse_bool(
            os.getenv("STRATEGY_V2_APIFY_COMMENT_ENRICHMENT_ENABLED"),
            default=True,
        ),
        comment_enrichment_max_videos_per_platform=_parse_positive_int_env(
            "STRATEGY_V2_APIFY_COMMENT_ENRICHMENT_MAX_VIDEOS_PER_PLATFORM",
            20,
        ),
        comment_enrichment_max_comments_per_video=_parse_positive_int_env(
            "STRATEGY_V2_APIFY_COMMENT_ENRICHMENT_MAX_COMMENTS_PER_VIDEO",
            120,
        ),
        allowed_actor_ids=_parse_allowed_actor_ids(),
        meta_actor_id=os.getenv(
            "STRATEGY_V2_APIFY_META_ACTOR_ID",
            os.getenv("APIFY_META_ACTOR_ID", "curious_coder~facebook-ads-library-scraper"),
        ),
        tiktok_actor_id=os.getenv("STRATEGY_V2_APIFY_TIKTOK_ACTOR_ID", "clockworks/tiktok-scraper"),
        instagram_actor_id=os.getenv("STRATEGY_V2_APIFY_INSTAGRAM_ACTOR_ID", "apify/instagram-scraper"),
        youtube_actor_id=os.getenv("STRATEGY_V2_APIFY_YOUTUBE_ACTOR_ID", "streamers/youtube-scraper"),
        youtube_comments_actor_id=os.getenv(
            "STRATEGY_V2_APIFY_YOUTUBE_COMMENTS_ACTOR_ID",
            "streamers/youtube-comments-scraper",
        ),
        reddit_actor_id=os.getenv("STRATEGY_V2_APIFY_REDDIT_ACTOR_ID", "practicaltools/apify-reddit-api"),
        web_actor_id=os.getenv("STRATEGY_V2_APIFY_WEB_ACTOR_ID", "apify/web-scraper"),
    )


def _ensure_actor_allowed(*, actor_id: str, allowlist: frozenset[str]) -> None:
    normalized_actor_id = _normalize_actor_id(actor_id)
    normalized_allowlist = {_normalize_actor_id(item) for item in allowlist}
    if normalized_actor_id not in normalized_allowlist:
        raise RuntimeError(
            f"Actor '{actor_id}' is not in STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS allowlist. "
            "Remediation: add it explicitly if approved."
        )


def _canonical_source_refs(source_refs: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_ref in source_refs:
        ref = normalize_source_ref(raw_ref)
        if not ref:
            continue
        for expanded_ref in _expand_social_profile_variants(ref):
            canonical_ref = normalize_source_ref(expanded_ref)
            if not canonical_ref or canonical_ref in seen:
                continue
            seen.add(canonical_ref)
            normalized.append(canonical_ref)
    return normalized


def _expand_social_profile_variants(source_ref: str) -> list[str]:
    """
    Add deterministic social handle aliases for known actor failure cases.

    Some source refs include a `the*` handle that resolves to a not-found profile,
    while the canonical account exists without the leading `the`.
    """
    parsed = urlsplit(source_ref)
    host = parsed.netloc.lower()
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 1:
        return [source_ref]

    only_segment = segments[0]
    lower_segment = only_segment.lower()
    variants = [source_ref]

    if "tiktok.com" in host and only_segment.startswith("@") and lower_segment.startswith("@the"):
        candidate_handle = only_segment[4:]
        if _SOCIAL_HANDLE_PATTERN.match(candidate_handle):
            candidate_path = f"/@{candidate_handle}"
            variants.append(urlunsplit((parsed.scheme, parsed.netloc, candidate_path, parsed.query, parsed.fragment)))
        return variants

    if "instagram.com" in host and not only_segment.startswith("@") and lower_segment.startswith("the"):
        candidate_handle = only_segment[3:]
        if _SOCIAL_HANDLE_PATTERN.match(candidate_handle):
            candidate_path = f"/{candidate_handle}"
            variants.append(urlunsplit((parsed.scheme, parsed.netloc, candidate_path, parsed.query, parsed.fragment)))
        return variants

    return variants


def _extract_string(raw: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_number(raw: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, (int, float)):
            return max(int(value), 0)
        if isinstance(value, str) and value.strip():
            cleaned = value.strip().replace(",", "")
            if cleaned.isdigit():
                return int(cleaned)
    return None


def _extract_nested_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = raw.get(key)
    if isinstance(value, Mapping):
        return value
    return None


def _iter_nested_comment_rows(raw_comments: Any) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    stack: list[Any] = [raw_comments]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            rows.append(current)
            for key in ("replies", "comments", "commentReplies", "children"):
                nested = current.get(key)
                if isinstance(nested, (list, Mapping)):
                    stack.append(nested)
        elif isinstance(current, list):
            for value in current:
                if isinstance(value, (list, Mapping)):
                    stack.append(value)
    return rows


def _expand_actor_item_for_candidates(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nested_post = _extract_nested_mapping(item, "post")
    if nested_post is None:
        return [item]
    return [nested_post, item]


def _expand_actor_item_for_external_voc(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = _expand_actor_item_for_candidates(item)
    rows.extend(_iter_nested_comment_rows(item.get("comments")))
    rows.extend(_iter_nested_comment_rows(item.get("commentThreads")))
    return rows


def _source_ref_from_raw(raw: Mapping[str, Any], fallback_ref: str | None = None) -> str:
    nested_snapshot = raw.get("snapshot")
    candidate = _extract_string(
        raw,
        "source_ref",
        "sourceRef",
        "url",
        "link",
        "linkUrl",
        "sourceUrl",
        "postUrl",
        "webVideoUrl",
        "videoUrl",
        "permalink",
        "source_url",
        "inputUrl",
        "facebookUrl",
        "snapshotUrl",
        "adSnapshotUrl",
    )
    if not candidate and isinstance(nested_snapshot, dict):
        candidate = _extract_string(
            nested_snapshot,
            "url",
            "link_url",
            "ad_library_url",
            "page_profile_uri",
        )
    if not candidate and fallback_ref:
        candidate = fallback_ref
    return normalize_source_ref(candidate)


def _parse_days_since_posted(raw: Mapping[str, Any]) -> int | None:
    direct_days = _extract_number(raw, "days_since_posted", "post_age_days", "daysActive", "days_active")
    if direct_days is not None:
        return direct_days

    date_text = _extract_string(
        raw,
        "date_posted",
        "postedAt",
        "postDate",
        "publishedAt",
        "published_at",
        "startDate",
        "firstSeenDate",
    )
    if not date_text:
        return None
    parsed: datetime | None = None
    for candidate in (
        date_text,
        date_text.replace("Z", "+00:00"),
    ):
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except ValueError:
            continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(int(delta.total_seconds() // 86400), 0)


def _extract_metrics(raw: Mapping[str, Any]) -> CandidateAssetMetrics:
    stats = raw.get("stats")
    stats_map = stats if isinstance(stats, Mapping) else {}
    author_meta = raw.get("authorMeta")
    author_meta_map = author_meta if isinstance(author_meta, Mapping) else {}
    about_channel_info = raw.get("aboutChannelInfo")
    about_channel_info_map = about_channel_info if isinstance(about_channel_info, Mapping) else {}
    owner = raw.get("owner")
    owner_map = owner if isinstance(owner, Mapping) else {}
    user = raw.get("user")
    user_map = user if isinstance(user, Mapping) else {}

    views = _extract_number(raw, "views", "view_count", "viewCount", "playCount", "videoPlayCount", "videoViewCount")
    if views is None:
        views = _extract_number(stats_map, "playCount", "viewCount", "views", "videoViewCount")

    likes = _extract_number(raw, "likes", "like_count", "likesCount", "diggCount", "upVotes")
    if likes is None:
        likes = _extract_number(stats_map, "diggCount", "likeCount", "likes", "likesCount", "upVotes")

    comments = _extract_number(
        raw,
        "comments",
        "comment_count",
        "commentCount",
        "commentsCount",
        "numberOfComments",
        "numberOfreplies",
    )
    if comments is None:
        comments = _extract_number(stats_map, "commentCount", "comments", "commentsCount", "numberOfComments")

    shares = _extract_number(raw, "shares", "share_count", "shareCount")
    if shares is None:
        shares = _extract_number(stats_map, "shareCount", "shares")

    followers = _extract_number(
        raw,
        "followers",
        "account_followers",
        "authorFollowers",
        "numberOfSubscribers",
        "subscriberCount",
        "channelSubscriberCount",
    )
    if followers is None:
        followers = _extract_number(author_meta_map, "fans", "followers")
    if followers is None:
        followers = _extract_number(
            about_channel_info_map,
            "numberOfSubscribers",
            "subscriberCount",
            "followers",
        )
    if followers is None:
        followers = _extract_number(owner_map, "followers", "followersCount", "followerCount")
    if followers is None:
        followers = _extract_number(user_map, "followers", "followerCount", "fans")

    return CandidateAssetMetrics(
        views=views,
        likes=likes,
        comments=comments,
        shares=shares,
        followers=followers,
        days_since_posted=_parse_days_since_posted(raw),
        date_posted=(
            _extract_string(
                raw,
                "date_posted",
                "postedAt",
                "postDate",
                "date",
                "publishedAt",
                "published_at",
                "createTimeISO",
            )
            or None
        ),
    )


def _infer_asset_kind(*, platform: str, raw: Mapping[str, Any], source_ref: str) -> str:
    raw_type = _extract_string(raw, "type", "productType").lower()
    path = urlsplit(source_ref).path.lower()

    if _extract_string(
        raw,
        "videoUrl",
        "video_hd_url",
        "video_sd_url",
        "video_url",
    ):
        return "VIDEO"
    if _extract_number(raw, "videoPlayCount", "videoViewCount", "viewCount", "playCount") is not None:
        return "VIDEO"
    if "video" in raw_type or "reel" in raw_type or "short" in raw_type:
        return "VIDEO"
    if platform == "YOUTUBE" and (path.startswith("/watch") or path.startswith("/shorts/")):
        return "VIDEO"
    if platform == "TIKTOK" and "/video/" in path:
        return "VIDEO"
    if platform == "INSTAGRAM" and path.startswith("/reel/"):
        return "VIDEO"

    if raw_type in {"image", "photo", "sidecar", "carousel"}:
        return "IMAGE"
    if _extract_string(raw, "imageUrl", "image_url", "thumbnailUrl", "thumbnail_url"):
        return "IMAGE"
    if platform == "INSTAGRAM" and path.startswith("/p/"):
        return "IMAGE"
    return "PAGE"


def _infer_compliance_risk(*, quote_or_caption: str) -> str:
    lowered = quote_or_caption.lower()
    if any(token in lowered for token in ("cure", "treat", "diagnose")):
        return "RED"
    if any(token in lowered for token in ("disease", "condition", "symptom", "medication", "drug")):
        return "YELLOW"
    return "GREEN"


def _infer_hook_format(*, text: str) -> str:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if not cleaned:
        return "NONE"
    if cleaned.endswith("?"):
        return "QUESTION"
    if re.match(r"^\s*\d+([.,]\d+)?[%x]?\b", cleaned):
        return "STATISTIC"
    if any(token in lowered for token in ("they told me", "nobody tells you", "the truth is", "stop doing")):
        return "CONTRARIAN"
    if any(token in lowered for token in ("watch this", "here's how", "do this", "step 1")):
        return "DEMONSTRATION"
    if any(token in lowered for token in ("when i", "i was", "after i", "my story")):
        return "STORY"
    return "STATEMENT"


def _infer_video_virality_tier_from_views(view_count: int | None) -> str | None:
    if view_count is None:
        return None
    if view_count >= 1_000_000:
        return "VIRAL"
    if view_count >= 250_000:
        return "HIGH_PERFORMING"
    if view_count >= 50_000:
        return "ABOVE_AVERAGE"
    return "BASELINE"


def _classify_non_video_comment_source_type(*, platform: str, source_url: str) -> str:
    if platform == "REDDIT":
        return "REDDIT"
    host = urlsplit(source_url).netloc.lower()
    if any(token in host for token in ("amazon.", "trustpilot.", "g2.", "yelp.", "capterra.")):
        return "REVIEW_SITE"
    if any(token in host for token in ("quora.", "stackexchange.", "stackoverflow.", "reddit.")):
        return "QA"
    if "blog" in host:
        return "BLOG_COMMENT"
    return "FORUM"


def _clean_candidate_caption_text(raw_text: str) -> str:
    trimmed = raw_text.strip()
    if not trimmed:
        return ""
    if "<html" in trimmed.lower() or "<body" in trimmed.lower():
        return ""
    collapsed = re.sub(r"<[^>]+>", " ", trimmed)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    if not collapsed:
        return ""
    return collapsed[:500]


def _extract_candidate_caption(raw: Mapping[str, Any]) -> str:
    primary = _extract_string(
        raw,
        "headline",
        "title",
        "caption",
        "description",
    )
    cleaned_primary = _clean_candidate_caption_text(primary)
    if cleaned_primary:
        return cleaned_primary
    secondary = _extract_string(
        raw,
        "text",
        "body",
        "bodyText",
    )
    return _clean_candidate_caption_text(secondary)


def _classify_external_voc_source_type(*, platform: str, source_url: str, source_role: str) -> str:
    if source_role == "HOOK":
        if platform not in _VIDEO_PLATFORMS:
            raise RuntimeError(
                f"External VOC hook classification requires video platform, got platform={platform!r}, source_url={source_url!r}."
            )
        return "VIDEO_HOOK"
    if source_role != "COMMENT":
        raise RuntimeError(f"Unsupported external VOC source_role={source_role!r}.")
    if platform in _EXTERNAL_COMMENT_SOURCE_TYPE_BY_PLATFORM:
        return _EXTERNAL_COMMENT_SOURCE_TYPE_BY_PLATFORM[platform]
    return _classify_non_video_comment_source_type(platform=platform, source_url=source_url)


def _extract_external_voc_variants(*, row: Mapping[str, Any], platform: str) -> list[tuple[str, str, str]]:
    variants: list[tuple[str, str, str]] = []
    explicit_comment = _extract_string(row, "comment", "commentText")
    explicit_hook = _extract_string(row, "hook", "opening_hook", "openingHook", "caption", "description", "title")
    generic_text = _extract_string(row, "text", "body")

    if platform in _VIDEO_PLATFORMS:
        if explicit_comment:
            variants.append(("COMMENT", explicit_comment, "explicit_comment_field"))
        if explicit_hook:
            variants.append(("HOOK", explicit_hook, "explicit_hook_field"))
        if not variants and generic_text:
            comment_markers = (
                "replies",
                "reply_count",
                "comment_count",
                "numberOfreplies",
                "numberOfComments",
                "commentId",
                "comment_id",
                "parentCommentId",
                "parentId",
            )
            if any(marker in row for marker in comment_markers):
                variants.append(("COMMENT", generic_text, "generic_text_with_comment_markers"))
        return variants

    non_video_quote = _extract_string(
        row,
        "quote",
        "comment",
        "commentText",
        "text",
        "body",
        "caption",
        "description",
        "title",
    )
    if non_video_quote:
        variants.append(("COMMENT", non_video_quote, "non_video_quote_field"))
    return variants


def _build_tiktok_actor_input(*, urls: list[str], max_items: int) -> dict[str, Any]:
    profiles: list[str] = []
    post_urls: list[str] = []
    hashtags: list[str] = []

    for url in urls:
        candidate = url.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if "/video/" in lowered:
            post_urls.append(candidate)
            continue
        if "/tag/" in lowered:
            tag_value = candidate.rstrip("/").split("/tag/")[-1].split("?")[0].strip()
            if tag_value:
                hashtags.append(tag_value)
            continue
        profiles.append(candidate)

    payload: dict[str, Any] = {"maxItems": max_items}
    if profiles:
        payload["profiles"] = profiles
    if post_urls:
        payload["postURLs"] = post_urls
    if hashtags:
        payload["hashtags"] = hashtags
    if not any((profiles, post_urls, hashtags)):
        raise RuntimeError("TikTok actor input requires at least one valid profile, post URL, or hashtag.")
    return payload


def _build_instagram_actor_input(*, urls: list[str], max_items: int) -> dict[str, Any]:
    direct_urls = [url.strip() for url in urls if isinstance(url, str) and url.strip()]
    if not direct_urls:
        raise RuntimeError("Instagram actor input requires at least one valid direct URL.")
    return {
        "directUrls": direct_urls,
        "resultsLimit": max_items,
    }


def _build_youtube_actor_input(*, urls: list[str], max_items: int) -> dict[str, Any]:
    start_urls = [{"url": url.strip()} for url in urls if isinstance(url, str) and url.strip()]
    if not start_urls:
        raise RuntimeError("YouTube actor input requires at least one valid URL.")
    return {
        "startUrls": start_urls,
        "maxResults": max_items,
    }


def _build_reddit_actor_input(*, urls: list[str], max_items: int) -> dict[str, Any]:
    start_urls = [{"url": url.strip()} for url in urls if isinstance(url, str) and url.strip()]
    if not start_urls:
        raise RuntimeError("Reddit actor input requires at least one valid URL.")
    return {
        "startUrls": start_urls,
        "maxItems": max_items,
    }


def _build_web_actor_input(*, urls: list[str], max_items: int) -> dict[str, Any]:
    start_urls = [{"url": url.strip()} for url in urls if isinstance(url, str) and url.strip()]
    if not start_urls:
        raise RuntimeError("Web actor input requires at least one valid URL.")
    return {
        "startUrls": start_urls,
        "maxCrawlPages": max_items,
        "maxResultsPerCrawl": max_items,
        "pageFunction": (
            "async function pageFunction(context) {"
            " const { request, html } = context;"
            " const text = html && typeof html.text === 'function' ? html.text() : '';"
            " return { url: request.url, text: text.slice(0, 4000) };"
            " }"
        ),
    }


def _extract_requested_urls_from_payload(input_payload: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []

    def _append_candidate(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            refs.append(normalize_source_ref(value.strip()))
            return
        if isinstance(value, Mapping):
            url_value = value.get("url")
            if isinstance(url_value, str) and url_value.strip():
                refs.append(normalize_source_ref(url_value.strip()))

    for key in ("startUrls", "urls", "directUrls"):
        raw = input_payload.get(key)
        if isinstance(raw, list):
            for row in raw:
                _append_candidate(row)

    for key in ("profiles", "postURLs"):
        raw = input_payload.get(key)
        if isinstance(raw, list):
            for row in raw:
                _append_candidate(row)

    return [ref for ref in refs if ref]


def _is_search_result_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.netloc.lower()
    if host in _SEARCH_HOSTS and parsed.path.startswith("/search"):
        return True
    return any(token in host for token in _DISALLOWED_DISCOVERY_HOST_TOKENS)


def _iter_candidate_urls_from_discovery_item(item: Mapping[str, Any]) -> list[str]:
    urls: list[str] = []
    stack: list[Any] = [item]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key in _URL_FIELD_CANDIDATES:
                value = current.get(key)
                if isinstance(value, str) and value.strip():
                    urls.append(value.strip())
            for key in _RESULT_CONTAINER_FIELDS:
                nested = current.get(key)
                if isinstance(nested, list):
                    stack.extend(nested)
                elif isinstance(nested, Mapping):
                    stack.append(nested)
            for key, value in current.items():
                if key in _RESULT_CONTAINER_FIELDS or key in _URL_FIELD_CANDIDATES:
                    continue
                if isinstance(value, (list, Mapping)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)
    return urls


def _canonicalize_destination_url(raw_url: str) -> str:
    candidate = normalize_source_ref(raw_url)
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.netloc.lower() in _SEARCH_HOSTS and parsed.path in {"/url", "/imgres"}:
        query_map = dict(parse_qsl(parsed.query, keep_blank_values=False))
        redirected = (
            query_map.get("q")
            or query_map.get("url")
            or query_map.get("imgurl")
            or ""
        ).strip()
        if redirected:
            candidate = normalize_source_ref(unquote(redirected))
            if not candidate:
                return ""
            parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if _is_search_result_url(candidate):
        return ""
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        lowered = key.lower().strip()
        if lowered.startswith("utm_"):
            continue
        if lowered in {
            "gclid",
            "fbclid",
            "msclkid",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "ved",
            "ei",
            "sa",
            "oq",
        }:
            continue
        query_pairs.append((lowered, value))
    query_pairs.sort(key=lambda pair: (pair[0], pair[1]))
    cleaned_query = "&".join(f"{key}={value}" for key, value in query_pairs if key and value)
    cleaned = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") or "/", cleaned_query, ""))
    return cleaned


def _select_discovery_destination_urls(
    *,
    raw_runs: list[dict[str, Any]],
    max_urls_total: int,
    max_urls_per_query: int,
    max_urls_per_domain: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    per_domain: Counter[str] = Counter()
    for run in raw_runs:
        actor_id = str(run.get("actor_id") or "")
        if _normalize_actor_id(actor_id) != _normalize_actor_id("apify/google-search-scraper"):
            continue
        items = [row for row in run.get("items", []) if isinstance(row, Mapping)]
        config_id = str(run.get("config_id") or "").strip()
        run_id = str(run.get("run_id") or "").strip()
        config_metadata = run.get("config_metadata")
        metadata = dict(config_metadata) if isinstance(config_metadata, Mapping) else {}
        strategy_target_id = str(metadata.get("target_id") or "").strip()
        query = ""
        input_payload = run.get("input_payload")
        if isinstance(input_payload, Mapping):
            query = str(input_payload.get("queries") or "").strip()

        per_query_count = 0
        seen_local: set[str] = set()
        for item in items:
            for raw_url in _iter_candidate_urls_from_discovery_item(item):
                destination_url = _canonicalize_destination_url(raw_url)
                if not destination_url or destination_url in seen_local:
                    continue
                seen_local.add(destination_url)
                parsed = urlsplit(destination_url)
                domain = parsed.netloc.lower().removeprefix("www.")
                if per_domain[domain] >= max_urls_per_domain:
                    continue
                selected.append(
                    {
                        "url": destination_url,
                        "domain": domain,
                        "strategy_target_id": strategy_target_id,
                        "parent_config_id": config_id,
                        "parent_run_id": run_id,
                        "parent_query": query,
                        "parent_habitat_name": str(metadata.get("habitat_name") or "").strip(),
                    }
                )
                per_domain[domain] += 1
                per_query_count += 1
                if per_query_count >= max_urls_per_query or len(selected) >= max_urls_total:
                    break
            if per_query_count >= max_urls_per_query or len(selected) >= max_urls_total:
                break
        if len(selected) >= max_urls_total:
            break
    return selected


def _build_discovery_destination_runs(
    *,
    raw_runs: list[dict[str, Any]],
    config: StrategyV2ApifyConfig,
) -> list[tuple[str, dict[str, Any], str | None, Mapping[str, Any] | None]]:
    destination_urls = _select_discovery_destination_urls(
        raw_runs=raw_runs,
        max_urls_total=config.discovery_fanout_max_urls_total,
        max_urls_per_query=config.discovery_fanout_max_urls_per_query,
        max_urls_per_domain=config.discovery_fanout_max_urls_per_domain,
    )
    if not destination_urls:
        return []

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in destination_urls:
        strategy_target_id = str(row.get("strategy_target_id") or "").strip() or "DISCOVERY_UNMAPPED"
        url = str(row["url"]).strip()
        platform = derive_platform_from_ref(url)
        if platform == "REDDIT":
            actor_id = config.reddit_actor_id
            habitat_type = "Reddit"
        elif platform == "YOUTUBE":
            actor_id = config.youtube_actor_id
            habitat_type = "YouTube"
        elif platform == "TIKTOK":
            actor_id = config.tiktok_actor_id
            habitat_type = "TikTok"
        elif platform == "INSTAGRAM":
            actor_id = config.instagram_actor_id
            habitat_type = "Instagram"
        else:
            actor_id = config.web_actor_id
            habitat_type = "Web"
        key = (strategy_target_id, actor_id, habitat_type)
        grouped.setdefault(key, []).append(row)

    planned: list[tuple[str, dict[str, Any], str | None, Mapping[str, Any] | None]] = []
    for (strategy_target_id, actor_id, habitat_type), rows in grouped.items():
        urls: list[str] = []
        for row in rows:
            candidate_url = str(row.get("url") or "").strip()
            if candidate_url and candidate_url not in urls:
                urls.append(candidate_url)
        if not urls:
            continue
        for chunk_index in range(0, len(urls), config.discovery_fanout_max_urls_per_run):
            chunk = urls[chunk_index: chunk_index + config.discovery_fanout_max_urls_per_run]
            if not chunk:
                continue
            if _normalize_actor_id(actor_id) == _normalize_actor_id(config.reddit_actor_id):
                input_payload = _build_reddit_actor_input(urls=chunk, max_items=config.max_items_per_dataset)
            elif _normalize_actor_id(actor_id) == _normalize_actor_id(config.youtube_actor_id):
                input_payload = _build_youtube_actor_input(urls=chunk, max_items=config.max_items_per_dataset)
            elif _normalize_actor_id(actor_id) == _normalize_actor_id(config.tiktok_actor_id):
                input_payload = _build_tiktok_actor_input(urls=chunk, max_items=config.max_items_per_dataset)
            elif _normalize_actor_id(actor_id) == _normalize_actor_id(config.instagram_actor_id):
                input_payload = _build_instagram_actor_input(urls=chunk, max_items=config.max_items_per_dataset)
            elif _normalize_actor_id(actor_id) == _normalize_actor_id(config.web_actor_id):
                input_payload = _build_web_actor_input(urls=chunk, max_items=config.max_items_per_dataset)
            else:
                raise RuntimeError(
                    f"Discovery fan-out produced unsupported actor_id={actor_id!r}. "
                    "Remediation: map the destination platform to a supported actor."
                )
            config_id = f"DISCOVERY_FANOUT_{strategy_target_id}_{chunk_index // config.discovery_fanout_max_urls_per_run + 1:02d}"
            metadata = {
                "source_stage": "discovery_fanout",
                "tier": "fanout",
                "target_id": strategy_target_id,
                "habitat_type": habitat_type,
                "habitat_name": f"discovery://{strategy_target_id}/{habitat_type.lower()}",
            }
            planned.append((actor_id, input_payload, config_id, metadata))
    return planned


def _build_youtube_comments_actor_input(*, urls: list[str], max_comments_per_video: int) -> dict[str, Any]:
    start_urls = [{"url": url} for url in urls if isinstance(url, str) and url.strip()]
    if not start_urls:
        raise RuntimeError("YouTube comments actor input requires at least one valid video URL.")
    return {
        "startUrls": start_urls,
        "maxComments": max_comments_per_video,
    }


def _build_comment_enrichment_runs(
    *,
    candidate_assets: list[dict[str, Any]],
    config: StrategyV2ApifyConfig,
) -> list[tuple[str, dict[str, Any], str | None, Mapping[str, Any] | None]]:
    if not config.comment_enrichment_enabled:
        return []

    top_urls_by_platform: dict[str, list[str]] = {"TIKTOK": [], "INSTAGRAM": [], "YOUTUBE": []}
    seen_urls: set[str] = set()
    ranked = sorted(
        [row for row in candidate_assets if isinstance(row, Mapping)],
        key=lambda row: (
            -int(((row.get("metrics") or {}).get("comments") or 0) if isinstance(row.get("metrics"), Mapping) else 0),
            -int(((row.get("metrics") or {}).get("views") or 0) if isinstance(row.get("metrics"), Mapping) else 0),
        ),
    )
    for row in ranked:
        source_ref = str(row.get("source_ref") or "").strip()
        if not source_ref:
            continue
        canonical_url = _canonicalize_destination_url(source_ref)
        if not canonical_url or canonical_url in seen_urls:
            continue
        platform = derive_platform_from_ref(canonical_url)
        if platform not in top_urls_by_platform:
            continue
        path = urlsplit(canonical_url).path.lower()
        if platform == "YOUTUBE" and not (path.startswith("/watch") or path.startswith("/shorts/")):
            continue
        if platform == "INSTAGRAM" and not (path.startswith("/p/") or path.startswith("/reel/")):
            continue
        if platform == "TIKTOK" and "/video/" not in path:
            continue
        if len(top_urls_by_platform[platform]) >= config.comment_enrichment_max_videos_per_platform:
            continue
        top_urls_by_platform[platform].append(canonical_url)
        seen_urls.add(canonical_url)

    runs: list[tuple[str, dict[str, Any], str | None, Mapping[str, Any] | None]] = []
    if top_urls_by_platform["TIKTOK"]:
        runs.append(
            (
                config.tiktok_actor_id,
                _build_tiktok_actor_input(
                    urls=top_urls_by_platform["TIKTOK"],
                    max_items=config.comment_enrichment_max_comments_per_video,
                ),
                "COMMENT_ENRICHMENT_TIKTOK",
                {
                    "source_stage": "comment_enrichment",
                    "target_id": "COMMENT_ENRICHMENT_TIKTOK",
                    "habitat_type": "TikTok",
                    "habitat_name": "comments://tiktok",
                },
            )
        )
    if top_urls_by_platform["INSTAGRAM"]:
        runs.append(
            (
                config.instagram_actor_id,
                _build_instagram_actor_input(
                    urls=top_urls_by_platform["INSTAGRAM"],
                    max_items=config.comment_enrichment_max_comments_per_video,
                ),
                "COMMENT_ENRICHMENT_INSTAGRAM",
                {
                    "source_stage": "comment_enrichment",
                    "target_id": "COMMENT_ENRICHMENT_INSTAGRAM",
                    "habitat_type": "Instagram",
                    "habitat_name": "comments://instagram",
                },
            )
        )
    if top_urls_by_platform["YOUTUBE"]:
        runs.append(
            (
                config.youtube_comments_actor_id,
                _build_youtube_comments_actor_input(
                    urls=top_urls_by_platform["YOUTUBE"],
                    max_comments_per_video=config.comment_enrichment_max_comments_per_video,
                ),
                "COMMENT_ENRICHMENT_YOUTUBE",
                {
                    "source_stage": "comment_enrichment",
                    "target_id": "COMMENT_ENRICHMENT_YOUTUBE",
                    "habitat_type": "YouTube",
                    "habitat_name": "comments://youtube",
                },
            )
        )
    return runs


def _run_has_textual_content(run_row: Mapping[str, Any]) -> bool:
    items = run_row.get("items")
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if _extract_string(item, *_TEXT_VALUE_FIELDS):
            return True
        posts_sample = item.get("postsSample")
        if isinstance(posts_sample, list):
            for sample in posts_sample:
                if isinstance(sample, str) and sample.strip():
                    return True
        comments = item.get("comments")
        if isinstance(comments, list) and comments:
            return True
    return False


def _validate_ingestion_quality(*, raw_runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not raw_runs:
        raise RuntimeError(
            "Apify ingestion produced zero actor runs. Remediation: verify strategy configs and actor execution."
        )
    missing_target_id_runs = [
        str(row.get("config_id") or row.get("run_id") or "unknown")
        for row in raw_runs
        if not str(((row.get("config_metadata") or {}).get("target_id") if isinstance(row.get("config_metadata"), Mapping) else "") or "").strip()
    ]
    if missing_target_id_runs:
        raise RuntimeError(
            "Apify ingestion quality gate failed: target_id missing in run metadata for "
            f"{len(missing_target_id_runs)} run(s). Examples={missing_target_id_runs[:5]}."
        )

    discovery_runs = [
        row
        for row in raw_runs
        if _normalize_actor_id(str(row.get("actor_id") or ""))
        == _normalize_actor_id("apify/google-search-scraper")
    ]
    destination_runs = [
        row
        for row in raw_runs
        if str(((row.get("config_metadata") or {}).get("source_stage") if isinstance(row.get("config_metadata"), Mapping) else "") or "").strip()
        == "discovery_fanout"
    ]
    if discovery_runs and not destination_runs:
        raise RuntimeError(
            "Apify ingestion quality gate failed: discovery runs completed but produced zero destination fan-out runs. "
            "Remediation: inspect SERP parsing and fan-out URL extraction."
        )

    text_runs = [row for row in raw_runs if _run_has_textual_content(row)]
    if not text_runs:
        raise RuntimeError(
            "Apify ingestion quality gate failed: zero runs contained extractable text content. "
            "Remediation: verify actor inputs include comments/body fields."
        )

    return {
        "run_count": len(raw_runs),
        "discovery_run_count": len(discovery_runs),
        "destination_run_count": len(destination_runs),
        "textual_run_count": len(text_runs),
        "non_textual_run_count": len(raw_runs) - len(text_runs),
    }


def _execute_actor(
    *,
    client: ApifyClient,
    actor_id: str,
    input_payload: dict[str, Any],
    max_wait_seconds: int,
    max_items_per_dataset: int,
    config_id: str | None = None,
    config_metadata: Mapping[str, Any] | None = None,
    progress_callback: ApifyProgressCallback | None = None,
    run_index: int | None = None,
    planned_run_count: int | None = None,
) -> dict[str, Any]:
    run_data = client.start_actor_run(actor_id, input_payload=input_payload)
    run_id = str(run_data.get("id") or run_data.get("runId") or "").strip()
    if not run_id:
        raise RuntimeError(f"Apify actor '{actor_id}' did not return run id.")
    _emit_apify_progress(
        callback=progress_callback,
        event={
            "event": "actor_run_started",
            "actor_id": actor_id,
            "config_id": config_id,
            "run_id": run_id,
            "run_index": run_index,
            "planned_run_count": planned_run_count,
        },
    )

    def _on_poll(payload: dict[str, Any]) -> None:
        _emit_apify_progress(
            callback=progress_callback,
            event={
                "event": "actor_run_poll",
                "actor_id": actor_id,
                "config_id": config_id,
                "run_id": run_id,
                "status": str(payload.get("status") or "UNKNOWN"),
                "elapsed_seconds": float(payload.get("elapsed_seconds") or 0.0),
                "run_index": run_index,
                "planned_run_count": planned_run_count,
            },
        )

    final = client.poll_run_until_terminal(
        run_id,
        max_wait_seconds=max_wait_seconds,
        on_poll=_on_poll if progress_callback is not None else None,
    )
    status = str(final.get("status") or "").upper()
    _emit_apify_progress(
        callback=progress_callback,
        event={
            "event": "actor_run_terminal",
            "actor_id": actor_id,
            "config_id": config_id,
            "run_id": run_id,
            "status": status or "UNKNOWN",
            "run_index": run_index,
            "planned_run_count": planned_run_count,
        },
    )
    if status != "SUCCEEDED":
        raise RuntimeError(
            f"Apify actor run failed (actor_id={actor_id}, run_id={run_id}, status={status})."
        )
    dataset_id = str(final.get("defaultDatasetId") or "").strip()
    if not dataset_id:
        raise RuntimeError(
            f"Apify actor run missing defaultDatasetId (actor_id={actor_id}, run_id={run_id})."
        )
    items = client.fetch_dataset_items(dataset_id, limit=max_items_per_dataset)
    if not isinstance(items, list):
        raise RuntimeError(
            f"Apify dataset payload was not a list (actor_id={actor_id}, run_id={run_id}, dataset_id={dataset_id})."
        )
    return {
        "config_id": config_id,
        "config_metadata": dict(config_metadata) if isinstance(config_metadata, Mapping) else {},
        "actor_id": actor_id,
        "run_id": run_id,
        "status": status,
        "dataset_id": dataset_id,
        "input_payload": input_payload,
        "items": [item for item in items if isinstance(item, dict)],
    }


def _execute_planned_runs_parallel(
    *,
    client: ApifyClient,
    planned_runs: list[tuple[str, dict[str, Any], str | None, Mapping[str, Any] | None]],
    allowlist: frozenset[str],
    max_wait_seconds: int,
    max_items_per_dataset: int,
    max_parallel_actor_runs: int,
    progress_callback: ApifyProgressCallback | None,
    run_index_offset: int,
    planned_run_count: int,
) -> list[dict[str, Any]]:
    if not planned_runs:
        return []

    indexed_runs: list[tuple[int, str, dict[str, Any], str | None, Mapping[str, Any] | None]] = []
    for index, (actor_id, payload, config_id, config_metadata) in enumerate(planned_runs, start=1):
        run_index = run_index_offset + index
        _ensure_actor_allowed(actor_id=actor_id, allowlist=allowlist)
        indexed_runs.append((run_index, actor_id, payload, config_id, config_metadata))

    progress_events: queue.SimpleQueue[dict[str, Any]] | None = (
        queue.SimpleQueue() if progress_callback is not None else None
    )

    def _enqueue_progress(event: Mapping[str, Any]) -> None:
        if progress_events is None:
            return
        progress_events.put(dict(event))

    def _flush_progress_events() -> None:
        if progress_callback is None or progress_events is None:
            return
        while True:
            try:
                payload = progress_events.get_nowait()
            except queue.Empty:
                break
            _emit_apify_progress(callback=progress_callback, event=payload)

    def _execute_indexed_run(
        run_index: int,
        actor_id: str,
        payload: dict[str, Any],
        run_config_id: str | None,
        run_config_metadata: Mapping[str, Any] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            result = _execute_actor(
                client=client,
                actor_id=actor_id,
                input_payload=payload,
                max_wait_seconds=max_wait_seconds,
                max_items_per_dataset=max_items_per_dataset,
                config_id=run_config_id,
                config_metadata=run_config_metadata,
                progress_callback=_enqueue_progress if progress_events is not None else None,
                run_index=run_index,
                planned_run_count=planned_run_count,
            )
        except Exception as exc:
            _emit_apify_progress(
                callback=_enqueue_progress if progress_events is not None else None,
                event={
                    "event": "actor_run_failed",
                    "actor_id": actor_id,
                    "config_id": run_config_id,
                    "run_index": run_index,
                    "planned_run_count": planned_run_count,
                    "error": str(exc),
                    "status": "FAILED",
                },
            )
            result = {
                "config_id": run_config_id,
                "config_metadata": dict(run_config_metadata) if isinstance(run_config_metadata, Mapping) else {},
                "actor_id": actor_id,
                "run_id": "",
                "status": "FAILED",
                "dataset_id": "",
                "input_payload": payload,
                "items": [],
                "error": str(exc),
            }
        return run_index, result

    for run_index, actor_id, _payload, config_id, _config_metadata in indexed_runs:
        _emit_apify_progress(
            callback=progress_callback,
            event={
                "event": "actor_run_dispatch",
                "actor_id": actor_id,
                "config_id": config_id,
                "run_index": run_index,
                "planned_run_count": planned_run_count,
            },
        )

    results_by_index: dict[int, dict[str, Any]] = {}
    pending_futures: set[concurrent.futures.Future[tuple[int, dict[str, Any]]]] = set()
    max_workers = max(1, min(max_parallel_actor_runs, len(indexed_runs)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for run_index, actor_id, payload, config_id, config_metadata in indexed_runs:
            future = executor.submit(
                _execute_indexed_run,
                run_index,
                actor_id,
                payload,
                config_id,
                config_metadata,
            )
            pending_futures.add(future)
        try:
            while pending_futures:
                done_futures, pending_futures = concurrent.futures.wait(
                    pending_futures,
                    timeout=2.0,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                _flush_progress_events()
                for done_future in done_futures:
                    run_index, result = done_future.result()
                    results_by_index[run_index] = result
        except Exception:
            for pending_future in pending_futures:
                pending_future.cancel()
            _flush_progress_events()
            raise
        finally:
            _flush_progress_events()

    return [results_by_index[idx] for idx in sorted(results_by_index)]


def _normalize_candidate_assets(*, raw_runs: list[dict[str, Any]], seed_urls: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_refs: set[str] = set()

    for run in raw_runs:
        requested_urls = _extract_requested_urls_from_payload(
            run.get("input_payload", {}) if isinstance(run.get("input_payload"), dict) else {}
        )
        fallback_ref = requested_urls[0] if requested_urls else None
        for item in run.get("items", []):
            if not isinstance(item, dict):
                continue
            for row in _expand_actor_item_for_candidates(item):
                source_ref = _source_ref_from_raw(row, fallback_ref=fallback_ref)
                if not source_ref or source_ref in seen_refs:
                    continue
                seen_refs.add(source_ref)

                platform = derive_platform_from_ref(source_ref)
                asset_kind = _infer_asset_kind(platform=platform, raw=row, source_ref=source_ref)
                caption = _extract_candidate_caption(row)
                metrics = _extract_metrics(row)
                candidate = CompetitorAssetCandidate(
                    candidate_id=source_ref,
                    source_type=_SOURCE_TYPE_BY_PLATFORM.get(platform, "LANDING_PAGE"),
                    source_ref=source_ref,
                    competitor_name=(
                        _extract_string(
                            row,
                            "competitor_name",
                            "brand",
                            "pageName",
                            "author",
                            "ownerUsername",
                            "username",
                        )
                        or derive_competitor_name_from_ref(source_ref)
                    ),
                    platform=platform,
                    asset_kind=asset_kind,
                    headline_or_caption=caption,
                    metrics=metrics,
                    proof_type="NONE",
                    running_duration="UNKNOWN",
                    estimated_spend_tier="UNKNOWN",
                    compliance_risk=_infer_compliance_risk(quote_or_caption=caption),
                    raw_source_artifact_id=":".join(
                        part
                        for part in (
                            str(run.get("config_id") or "").strip(),
                            str(run.get("actor_id") or "").strip(),
                            str(run.get("run_id") or "").strip(),
                        )
                        if part
                    ),
                ).model_dump(mode="python")
                candidates.append(candidate)

    for ref in seed_urls:
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        platform = derive_platform_from_ref(ref)
        candidates.append(
            CompetitorAssetCandidate(
                candidate_id=ref,
                source_type=_SOURCE_TYPE_BY_PLATFORM.get(platform, "LANDING_PAGE"),
                source_ref=ref,
                competitor_name=derive_competitor_name_from_ref(ref),
                platform=platform,
                asset_kind="VIDEO" if platform in _VIDEO_PLATFORMS else "PAGE",
                headline_or_caption="",
                metrics=CandidateAssetMetrics(),
                proof_type="NONE",
                running_duration="UNKNOWN",
                estimated_spend_tier="UNKNOWN",
                compliance_risk="YELLOW",
            ).model_dump(mode="python")
        )

    return candidates


def _normalize_social_video_observations(candidate_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidate_assets:
        if not isinstance(row, dict):
            continue
        if str(row.get("asset_kind") or "").upper() != "VIDEO":
            continue
        metrics_raw = row.get("metrics")
        if not isinstance(metrics_raw, dict):
            continue
        views = metrics_raw.get("views")
        if not isinstance(views, int):
            continue
        followers_raw = metrics_raw.get("followers")
        source_ref = str(row.get("source_ref") or "").strip()
        if not source_ref:
            continue
        observation_key = str(row.get("candidate_id") or source_ref)
        if observation_key in seen:
            continue
        seen.add(observation_key)
        observation = SocialVideoObservation(
            video_id=observation_key,
            platform=str(row.get("platform") or "WEB"),
            views=max(views, 0),
            followers=max(int(followers_raw), 0) if isinstance(followers_raw, int) else 0,
            comments=max(int(metrics_raw.get("comments") or 0), 0),
            shares=max(int(metrics_raw.get("shares") or 0), 0),
            likes=max(int(metrics_raw.get("likes") or 0), 0),
            days_since_posted=max(int(metrics_raw.get("days_since_posted") or 30), 0),
            description=str(row.get("headline_or_caption") or ""),
            author=str(row.get("competitor_name") or ""),
            source_ref=source_ref,
        )
        videos.append(observation.model_dump(mode="python"))
    return videos


def _normalize_external_voc_items(raw_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    row_index = 1
    for run in raw_runs:
        requested_urls = _extract_requested_urls_from_payload(
            run.get("input_payload", {}) if isinstance(run.get("input_payload"), dict) else {}
        )
        fallback_ref = requested_urls[0] if requested_urls else None
        for item in run.get("items", []):
            if not isinstance(item, dict):
                continue
            thread_title_fallback = ""
            nested_post = _extract_nested_mapping(item, "post")
            if nested_post is not None:
                thread_title_fallback = _extract_string(nested_post, "title")
            for row in _expand_actor_item_for_external_voc(item):
                source_ref = _source_ref_from_raw(row, fallback_ref=fallback_ref)
                nested_snapshot = row.get("snapshot")
                if not source_ref:
                    continue
                platform = derive_platform_from_ref(source_ref)
                variants = _extract_external_voc_variants(row=row, platform=platform)
                if not variants and isinstance(nested_snapshot, Mapping):
                    snapshot_variants = _extract_external_voc_variants(
                        row=nested_snapshot,
                        platform=platform,
                    )
                    if snapshot_variants:
                        variants = snapshot_variants
                if not variants:
                    continue

                likes = _extract_number(row, "likes", "like_count", "upvotes", "upVotes", "score") or 0
                replies = _extract_number(
                    row,
                    "replies",
                    "reply_count",
                    "comments",
                    "comment_count",
                    "numberOfreplies",
                    "numberOfComments",
                ) or 0
                view_count = _extract_number(
                    row,
                    "views",
                    "view_count",
                    "playCount",
                    "videoPlayCount",
                    "viewCount",
                )
                if view_count is None and isinstance(nested_snapshot, Mapping):
                    view_count = _extract_number(
                        nested_snapshot,
                        "views",
                        "view_count",
                        "playCount",
                        "videoPlayCount",
                        "viewCount",
                    )

                for source_role, quote, source_role_reason in variants:
                    cleaned_quote = quote.strip()
                    if not cleaned_quote:
                        continue
                    normalized_quote = re.sub(r"\s+", " ", cleaned_quote.lower())
                    dedupe_key = (source_ref, source_role, normalized_quote[:240])
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)

                    source_type = _classify_external_voc_source_type(
                        platform=platform,
                        source_url=source_ref,
                        source_role=source_role,
                    )
                    hook_word_count = (
                        len([token for token in re.split(r"\s+", cleaned_quote) if token])
                        if source_type == "VIDEO_HOOK"
                        else 0
                    )
                    external = ExternalVocCorpusItem(
                        voc_id=f"APIFY_V{row_index:04d}",
                        source_type=source_type,
                        source_role=source_role,
                        source_role_reason=source_role_reason,
                        source_url=source_ref,
                        platform=platform,
                        author=_extract_string(row, "author", "username", "ownerUsername") or "Unknown",
                        date=(
                            _extract_string(row, "date", "createdAt", "publishedAt", "postedAt")
                            or "Unknown"
                        ),
                        quote=cleaned_quote,
                        is_hook="Y" if source_type == "VIDEO_HOOK" else "N",
                        hook_format=(
                            _infer_hook_format(text=cleaned_quote)
                            if source_type == "VIDEO_HOOK"
                            else "NONE"
                        ),
                        hook_word_count=hook_word_count,
                        video_virality_tier=_infer_video_virality_tier_from_views(view_count),
                        video_view_count=max(view_count, 0) if isinstance(view_count, int) else None,
                        thread_title=(
                            _extract_string(row, "thread_title", "threadTitle", "title")
                            or thread_title_fallback
                            or None
                        ),
                        engagement=VocEngagement(likes=max(likes, 0), replies=max(replies, 0)),
                        compliance_risk=_infer_compliance_risk(quote_or_caption=cleaned_quote),
                    ).model_dump(mode="python")
                    rows.append(external)
                    row_index += 1
    return rows


def _external_voc_to_agent2_row(voc_item: Mapping[str, Any]) -> dict[str, Any]:
    quote = str(voc_item.get("quote") or "").strip()
    source_url = str(voc_item.get("source_url") or "").strip()
    platform = str(voc_item.get("platform") or "WEB").strip()
    source_type = str(voc_item.get("source_type") or "").strip()
    if not source_type:
        raise RuntimeError(
            "External VOC item is missing classified source_type for Agent 2 handoff. "
            "Remediation: ensure _normalize_external_voc_items classification runs before handoff."
        )
    is_hook = "Y" if source_type == "VIDEO_HOOK" else "N"
    hook_format = str(voc_item.get("hook_format") or "").strip().upper()
    if not hook_format:
        hook_format = _infer_hook_format(text=quote) if is_hook == "Y" else "NONE"
    if hook_format not in {"QUESTION", "STATEMENT", "STORY", "STATISTIC", "CONTRARIAN", "DEMONSTRATION", "NONE"}:
        hook_format = "NONE"
    hook_word_count_raw = voc_item.get("hook_word_count")
    hook_word_count = (
        int(hook_word_count_raw)
        if isinstance(hook_word_count_raw, (int, float))
        else len([token for token in re.split(r"\s+", quote) if token]) if is_hook == "Y" else 0
    )
    hook_word_count = max(hook_word_count, 0)
    view_count_raw = voc_item.get("video_view_count")
    if isinstance(view_count_raw, (int, float)):
        video_view_count = max(int(view_count_raw), 0)
    else:
        video_view_count = 0
    virality = str(voc_item.get("video_virality_tier") or "").strip().upper()
    if not virality:
        inferred_virality = _infer_video_virality_tier_from_views(video_view_count if video_view_count > 0 else None)
        virality = inferred_virality or "BASELINE"
    if virality not in {"VIRAL", "HIGH_PERFORMING", "ABOVE_AVERAGE", "BASELINE"}:
        virality = "BASELINE"

    return {
        "voc_id": str(voc_item.get("voc_id") or ""),
        "source_type": source_type,
        "author": str(voc_item.get("author") or "Unknown"),
        "date": str(voc_item.get("date") or "Unknown"),
        "source_url": source_url,
        "quote": quote,
        "is_hook": is_hook,
        "hook_format": hook_format,
        "hook_word_count": hook_word_count,
        "video_virality_tier": virality,
        "video_view_count": video_view_count,
        "trigger_event": "NONE",
        "pain_problem": quote[:200],
        "desired_outcome": "NONE",
        "failed_prior_solution": "NONE",
        "enemy_blame": "NONE",
        "identity_role": "Unknown",
        "fear_risk": "NONE",
        "emotional_valence": "NEUTRAL",
        "buyer_stage": "UNKNOWN",
        "demographic_signals": "Unknown",
        "solution_sophistication": "UNKNOWN",
        "compliance_risk": str(voc_item.get("compliance_risk") or "YELLOW"),
        "conversation_context": f"External Apify corpus ({platform})",
        "flags": ["APIFY_EXTERNAL"],
        "engagement": dict(voc_item.get("engagement") or {}),
    }


def _build_proof_asset_candidates(
    *,
    external_voc_items: list[dict[str, Any]],
    candidate_assets: list[dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    if max_candidates <= 0:
        raise RuntimeError(f"max_candidates must be > 0, got {max_candidates}")

    evidence_assets = [
        row
        for row in candidate_assets
        if isinstance(row, dict) and str(row.get("compliance_risk") or "YELLOW").upper() != "RED"
    ]
    evidence_refs = [
        str(row.get("source_ref") or "").strip()
        for row in evidence_assets
        if isinstance(row.get("source_ref"), str) and str(row.get("source_ref")).strip()
    ]

    ranked_voc = sorted(
        [row for row in external_voc_items if isinstance(row, dict)],
        key=lambda row: (
            -(
                int((row.get("engagement") or {}).get("likes") or 0)
                + (_ENGAGEMENT_WEIGHT_REPLIES * int((row.get("engagement") or {}).get("replies") or 0))
            ),
            str(row.get("voc_id") or ""),
        ),
    )

    proof_rows: list[dict[str, Any]] = []
    seen_notes: set[str] = set()
    for index, row in enumerate(ranked_voc):
        compliance = str(row.get("compliance_risk") or "YELLOW").upper()
        if compliance == "RED":
            continue
        source_url = str(row.get("source_url") or "").strip()
        if not source_url:
            continue
        backup_ref = next((ref for ref in evidence_refs if ref != source_url), "")
        if not backup_ref:
            alternate_row = next(
                (
                    other
                    for other in ranked_voc
                    if str(other.get("source_url") or "").strip()
                    and str(other.get("source_url") or "").strip() != source_url
                ),
                None,
            )
            if alternate_row is not None:
                backup_ref = str(alternate_row.get("source_url") or "").strip()
        if not backup_ref:
            continue

        quote = str(row.get("quote") or "").strip()
        if not quote:
            continue
        note = re.sub(r"\s+", " ", quote).strip()
        note = note[:220]
        if note in seen_notes:
            continue
        seen_notes.add(note)

        proof_candidate = ProofAssetCandidate(
            proof_id=f"proof_{index + 1:03d}",
            proof_note=note,
            source_refs=[source_url, backup_ref],
            evidence_count=2,
            compliance_flag="GREEN" if compliance == "GREEN" else "YELLOW",
        ).model_dump(mode="python")
        proof_rows.append(proof_candidate)
        if len(proof_rows) >= max_candidates:
            break
    return proof_rows


def _build_ads_context_summary(
    *,
    enabled: bool,
    candidate_assets: list[dict[str, Any]],
    source_refs: list[str],
) -> str:
    platform_counts = Counter(
        str(row.get("platform") or "UNKNOWN")
        for row in candidate_assets
        if isinstance(row, dict)
    )
    summary = {
        "source": "apify" if enabled else "seed_urls_only",
        "seed_url_count": len(source_refs),
        "candidate_asset_count": len(candidate_assets),
        "platform_breakdown": dict(platform_counts),
        "top_asset_refs": [
            str(row.get("source_ref"))
            for row in candidate_assets[:10]
            if isinstance(row, dict) and isinstance(row.get("source_ref"), str)
        ],
    }
    return json.dumps(summary, ensure_ascii=True)


def run_strategy_v2_apify_ingestion(
    *,
    source_refs: list[str] | None = None,
    apify_configs: list[Mapping[str, Any]] | None = None,
    include_ads_context: bool = True,
    include_social_video: bool = True,
    include_external_voc: bool = True,
    progress_callback: ApifyProgressCallback | None = None,
) -> dict[str, Any]:
    config = load_strategy_v2_apify_config()
    if not config.enabled:
        raise RuntimeError(
            "Strategy V2 Apify execution requires STRATEGY_V2_APIFY_ENABLED=true. "
            "Remediation: enable Apify before running Stage 2B."
        )

    canonical_refs = _canonical_source_refs(source_refs or [])
    normalized_strategy_configs = (
        _normalize_strategy_apify_configs(apify_configs, default_max_items=config.max_items_per_dataset)
        if apify_configs is not None
        else []
    )
    if apify_configs is None and not canonical_refs:
        raise RuntimeError(
            "Strategy V2 Apify ingestion requires either non-empty apify_configs "
            "or at least one valid absolute http(s) source ref."
        )

    apify = ApifyClient()
    raw_runs: list[dict[str, Any]] = []

    urls_by_platform: dict[str, list[str]] = {}
    for ref in canonical_refs:
        urls_by_platform.setdefault(derive_platform_from_ref(ref), []).append(ref)

    planned_runs: list[tuple[str, dict[str, Any], str | None, Mapping[str, Any] | None]] = []
    if normalized_strategy_configs:
        for row in normalized_strategy_configs:
            planned_runs.append(
                (
                    str(row["actor_id"]),
                    dict(row["input"]),
                    str(row["config_id"]),
                    dict(row["metadata"]) if isinstance(row.get("metadata"), dict) else {},
                )
            )
    else:
        if include_ads_context:
            seed_for_meta = urls_by_platform.get("META") or canonical_refs[: min(len(canonical_refs), 5)]
            meta_count = max(config.max_items_per_dataset, 10)
            meta_payload: dict[str, Any] = {
                "urls": [{"url": url} for url in seed_for_meta],
                "scrapeAdDetails": True,
                "scrapePageAds.activeStatus": os.getenv("APIFY_META_ACTIVE_STATUS", "active"),
                "scrapePageAds.countryCode": os.getenv("APIFY_META_COUNTRY_CODE", "ALL"),
                "limitPerSource": meta_count,
                "count": meta_count,
                "maxItems": meta_count,
            }
            planned_runs.append((config.meta_actor_id, meta_payload, None, None))

        if include_social_video:
            for platform, actor_id in (
                ("TIKTOK", config.tiktok_actor_id),
                ("INSTAGRAM", config.instagram_actor_id),
                ("YOUTUBE", config.youtube_actor_id),
            ):
                urls = urls_by_platform.get(platform, [])
                if not urls:
                    continue
                planned_runs.append(
                    (
                        actor_id,
                        (
                            _build_tiktok_actor_input(
                                urls=urls[: min(len(urls), config.max_items_per_dataset)],
                                max_items=config.max_items_per_dataset,
                            )
                            if platform == "TIKTOK"
                            else _build_instagram_actor_input(
                                urls=urls[: min(len(urls), config.max_items_per_dataset)],
                                max_items=config.max_items_per_dataset,
                            )
                            if platform == "INSTAGRAM"
                            else _build_youtube_actor_input(
                                urls=urls[: min(len(urls), config.max_items_per_dataset)],
                                max_items=config.max_items_per_dataset,
                            )
                        ),
                        None,
                        None,
                    )
                )

        if include_external_voc:
            reddit_urls = urls_by_platform.get("REDDIT", [])
            if reddit_urls:
                planned_runs.append(
                    (
                        config.reddit_actor_id,
                        _build_reddit_actor_input(
                            urls=reddit_urls[: min(len(reddit_urls), config.max_items_per_dataset)],
                            max_items=config.max_items_per_dataset,
                        ),
                        None,
                        None,
                    )
                )
            planned_runs.append(
                (
                    config.web_actor_id,
                    _build_web_actor_input(
                        urls=canonical_refs[: min(len(canonical_refs), 10)],
                        max_items=config.max_items_per_dataset,
                    ),
                    None,
                    None,
                )
            )

    if not planned_runs:
        raise RuntimeError(
            "Strategy V2 Apify ingestion produced zero actor runs. "
            "Remediation: supply executable apify_configs or scrapeable source refs."
        )
    if len(planned_runs) > config.max_actor_runs:
        raise RuntimeError(
            "Strategy V2 Apify ingestion planned actor runs exceed STRATEGY_V2_APIFY_MAX_ACTOR_RUNS "
            f"({len(planned_runs)} > {config.max_actor_runs}) before discovery fan-out."
        )

    strategy_config_run_count = len(normalized_strategy_configs) if normalized_strategy_configs else len(planned_runs)
    raw_runs = _execute_planned_runs_parallel(
        client=apify,
        planned_runs=planned_runs,
        allowlist=config.allowed_actor_ids,
        max_wait_seconds=config.max_wait_seconds,
        max_items_per_dataset=config.max_items_per_dataset,
        max_parallel_actor_runs=config.max_parallel_actor_runs,
        progress_callback=progress_callback,
        run_index_offset=0,
        planned_run_count=len(planned_runs),
    )

    fanout_runs: list[tuple[str, dict[str, Any], str | None, Mapping[str, Any] | None]] = []
    if config.discovery_fanout_enabled:
        fanout_runs = _build_discovery_destination_runs(raw_runs=raw_runs, config=config)
        if len(planned_runs) + len(fanout_runs) > config.max_actor_runs:
            raise RuntimeError(
                "Strategy V2 Apify ingestion planned actor runs exceed STRATEGY_V2_APIFY_MAX_ACTOR_RUNS "
                f"after discovery fan-out (base={len(planned_runs)}, fanout={len(fanout_runs)}, "
                f"max={config.max_actor_runs})."
            )
        if fanout_runs:
            fanout_results = _execute_planned_runs_parallel(
                client=apify,
                planned_runs=fanout_runs,
                allowlist=config.allowed_actor_ids,
                max_wait_seconds=config.max_wait_seconds,
                max_items_per_dataset=config.max_items_per_dataset,
                max_parallel_actor_runs=config.max_parallel_actor_runs,
                progress_callback=progress_callback,
                run_index_offset=len(raw_runs),
                planned_run_count=len(planned_runs) + len(fanout_runs),
            )
            raw_runs.extend(fanout_results)

    candidate_assets_for_comments = _normalize_candidate_assets(raw_runs=raw_runs, seed_urls=canonical_refs)
    comment_runs = _build_comment_enrichment_runs(candidate_assets=candidate_assets_for_comments, config=config)
    if len(planned_runs) + len(fanout_runs) + len(comment_runs) > config.max_actor_runs:
        raise RuntimeError(
            "Strategy V2 Apify ingestion planned actor runs exceed STRATEGY_V2_APIFY_MAX_ACTOR_RUNS "
            f"after comment enrichment (base={len(planned_runs)}, fanout={len(fanout_runs)}, "
            f"comment_runs={len(comment_runs)}, max={config.max_actor_runs})."
        )
    if comment_runs:
        comment_results = _execute_planned_runs_parallel(
            client=apify,
            planned_runs=comment_runs,
            allowlist=config.allowed_actor_ids,
            max_wait_seconds=config.max_wait_seconds,
            max_items_per_dataset=config.max_items_per_dataset,
            max_parallel_actor_runs=config.max_parallel_actor_runs,
            progress_callback=progress_callback,
            run_index_offset=len(raw_runs),
            planned_run_count=len(planned_runs) + len(fanout_runs) + len(comment_runs),
        )
        raw_runs.extend(comment_results)

    if normalized_strategy_configs:
        quality_report = _validate_ingestion_quality(raw_runs=raw_runs)
    else:
        quality_report = {
            "run_count": len(raw_runs),
            "quality_gate": "skipped_source_refs_mode",
        }

    candidate_assets = _normalize_candidate_assets(raw_runs=raw_runs, seed_urls=canonical_refs)
    social_videos = _normalize_social_video_observations(candidate_assets)
    external_voc_items = _normalize_external_voc_items(raw_runs)
    external_voc_corpus = [_external_voc_to_agent2_row(row) for row in external_voc_items]
    proof_asset_candidates = _build_proof_asset_candidates(
        external_voc_items=external_voc_items,
        candidate_assets=candidate_assets,
        max_candidates=10,
    )
    ads_context = _build_ads_context_summary(
        enabled=True,
        candidate_assets=candidate_assets,
        source_refs=canonical_refs,
    )
    return {
        "enabled": True,
        "raw_runs": raw_runs,
        "candidate_assets": candidate_assets,
        "social_video_observations": social_videos,
        "external_voc_items": external_voc_items,
        "external_voc_corpus": external_voc_corpus,
        "proof_asset_candidates": proof_asset_candidates,
        "ads_context": ads_context,
        "summary": {
            "strategy_config_run_count": strategy_config_run_count,
            "base_run_count": len(planned_runs),
            "discovery_fanout_run_count": len(fanout_runs),
            "comment_enrichment_run_count": len(comment_runs),
            "planned_actor_run_count": len(planned_runs) + len(fanout_runs) + len(comment_runs),
            "quality_report": quality_report,
            "run_count": len(raw_runs),
            "candidate_asset_count": len(candidate_assets),
            "social_video_count": len(social_videos),
            "external_voc_count": len(external_voc_corpus),
            "proof_candidate_count": len(proof_asset_candidates),
        },
    }
