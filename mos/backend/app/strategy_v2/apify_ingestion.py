from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

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
    "practicaltools/apify-reddit-api",
    "trudax/reddit-scraper",
    "apify/web-scraper",
    "apify/google-search-scraper",
    "emastra/trustpilot-scraper",
    "junglee/amazon-reviews-scraper",
    # Keep tilde-format aliases for compatibility with existing env values.
    "clockworks~tiktok-scraper",
    "apify~instagram-scraper",
    "streamers~youtube-scraper",
    "practicaltools~apify-reddit-api",
    "trudax~reddit-scraper",
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

_ENGAGEMENT_WEIGHT_COMMENTS = 2
_ENGAGEMENT_WEIGHT_REPLIES = 2
_SOCIAL_HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9._]{3,64}$")


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
    allowed_actor_ids: frozenset[str]
    meta_actor_id: str
    tiktok_actor_id: str
    instagram_actor_id: str
    youtube_actor_id: str
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


def load_strategy_v2_apify_config() -> StrategyV2ApifyConfig:
    return StrategyV2ApifyConfig(
        enabled=_parse_bool(os.getenv("STRATEGY_V2_APIFY_ENABLED"), default=False),
        max_wait_seconds=_parse_positive_int_env("STRATEGY_V2_APIFY_MAX_WAIT_SECONDS", 900),
        max_items_per_dataset=_parse_positive_int_env("STRATEGY_V2_APIFY_MAX_ITEMS_PER_DATASET", 80),
        max_actor_runs=_parse_positive_int_env("STRATEGY_V2_APIFY_MAX_ACTOR_RUNS", 6),
        allowed_actor_ids=_parse_allowed_actor_ids(),
        meta_actor_id=os.getenv(
            "STRATEGY_V2_APIFY_META_ACTOR_ID",
            os.getenv("APIFY_META_ACTOR_ID", "curious_coder~facebook-ads-library-scraper"),
        ),
        tiktok_actor_id=os.getenv("STRATEGY_V2_APIFY_TIKTOK_ACTOR_ID", "clockworks/tiktok-scraper"),
        instagram_actor_id=os.getenv("STRATEGY_V2_APIFY_INSTAGRAM_ACTOR_ID", "apify/instagram-scraper"),
        youtube_actor_id=os.getenv("STRATEGY_V2_APIFY_YOUTUBE_ACTOR_ID", "streamers/youtube-scraper"),
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


def _iter_reddit_comment_rows(raw_comments: Any) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    if not isinstance(raw_comments, list):
        return rows
    for row in raw_comments:
        if not isinstance(row, Mapping):
            continue
        rows.append(row)
        replies = row.get("replies")
        rows.extend(_iter_reddit_comment_rows(replies))
    return rows


def _expand_actor_item_for_candidates(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nested_post = _extract_nested_mapping(item, "post")
    if nested_post is None:
        return [item]
    return [nested_post, item]


def _expand_actor_item_for_external_voc(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = _expand_actor_item_for_candidates(item)
    rows.extend(_iter_reddit_comment_rows(item.get("comments")))
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

    views = _extract_number(raw, "views", "view_count", "playCount", "videoPlayCount")
    if views is None:
        views = _extract_number(stats_map, "playCount", "viewCount", "views")

    likes = _extract_number(raw, "likes", "like_count", "diggCount", "upVotes")
    if likes is None:
        likes = _extract_number(stats_map, "diggCount", "likeCount", "likes", "upVotes")

    comments = _extract_number(raw, "comments", "comment_count", "commentCount", "numberOfComments", "numberOfreplies")
    if comments is None:
        comments = _extract_number(stats_map, "commentCount", "comments", "numberOfComments")

    shares = _extract_number(raw, "shares", "share_count", "shareCount")
    if shares is None:
        shares = _extract_number(stats_map, "shareCount", "shares")

    followers = _extract_number(raw, "followers", "account_followers", "authorFollowers")
    if followers is None:
        followers = _extract_number(author_meta_map, "fans", "followers")

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
                "publishedAt",
                "published_at",
                "createTimeISO",
            )
            or None
        ),
    )


def _infer_asset_kind(*, platform: str, raw: Mapping[str, Any]) -> str:
    if platform in _VIDEO_PLATFORMS:
        return "VIDEO"
    if _extract_string(
        raw,
        "videoUrl",
        "video_hd_url",
        "video_sd_url",
        "video_url",
    ):
        return "VIDEO"
    if _extract_string(raw, "imageUrl", "image_url", "thumbnailUrl", "thumbnail_url"):
        return "IMAGE"
    return "PAGE"


def _infer_compliance_risk(*, quote_or_caption: str) -> str:
    lowered = quote_or_caption.lower()
    if any(token in lowered for token in ("cure", "treat", "diagnose")):
        return "RED"
    if any(token in lowered for token in ("disease", "condition", "symptom", "medication", "drug")):
        return "YELLOW"
    return "GREEN"


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


def _execute_actor(
    *,
    client: ApifyClient,
    actor_id: str,
    input_payload: dict[str, Any],
    max_wait_seconds: int,
    max_items_per_dataset: int,
) -> dict[str, Any]:
    run_data = client.start_actor_run(actor_id, input_payload=input_payload)
    run_id = str(run_data.get("id") or run_data.get("runId") or "").strip()
    if not run_id:
        raise RuntimeError(f"Apify actor '{actor_id}' did not return run id.")
    final = client.poll_run_until_terminal(run_id, max_wait_seconds=max_wait_seconds)
    status = str(final.get("status") or "").upper()
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
        "actor_id": actor_id,
        "run_id": run_id,
        "status": status,
        "dataset_id": dataset_id,
        "input_payload": input_payload,
        "items": [item for item in items if isinstance(item, dict)],
    }


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
                asset_kind = _infer_asset_kind(platform=platform, raw=row)
                caption = _extract_string(
                    row,
                    "headline",
                    "title",
                    "caption",
                    "description",
                    "text",
                    "body",
                    "bodyText",
                )
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
                    raw_source_artifact_id=f"{run.get('actor_id')}:{run.get('run_id')}",
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
        followers = metrics_raw.get("followers")
        if not isinstance(views, int) or not isinstance(followers, int):
            continue
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
            followers=max(followers, 0),
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
    seen_keys: set[tuple[str, str]] = set()
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
                quote = _extract_string(
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
                nested_snapshot = row.get("snapshot")
                if not quote and isinstance(nested_snapshot, dict):
                    quote = _extract_string(
                        nested_snapshot,
                        "body",
                        "caption",
                        "title",
                        "link_description",
                        "linkDescription",
                    )
                if not source_ref or not quote:
                    continue
                normalized_quote = re.sub(r"\s+", " ", quote.strip().lower())
                dedupe_key = (source_ref, normalized_quote[:240])
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)

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
                platform = derive_platform_from_ref(source_ref)
                external = ExternalVocCorpusItem(
                    voc_id=f"APIFY_V{row_index:04d}",
                    source_type="apify_comment",
                    source_url=source_ref,
                    platform=platform,
                    author=_extract_string(row, "author", "username", "ownerUsername") or "Unknown",
                    date=(
                        _extract_string(row, "date", "createdAt", "publishedAt", "postedAt")
                        or "Unknown"
                    ),
                    quote=quote,
                    thread_title=(
                        _extract_string(row, "thread_title", "threadTitle", "title")
                        or thread_title_fallback
                        or None
                    ),
                    engagement=VocEngagement(likes=max(likes, 0), replies=max(replies, 0)),
                    compliance_risk=_infer_compliance_risk(quote_or_caption=quote),
                ).model_dump(mode="python")
                rows.append(external)
                row_index += 1
    return rows


def _external_voc_to_agent2_row(voc_item: Mapping[str, Any]) -> dict[str, Any]:
    quote = str(voc_item.get("quote") or "").strip()
    source_url = str(voc_item.get("source_url") or "").strip()
    platform = str(voc_item.get("platform") or "WEB").strip()
    return {
        "voc_id": str(voc_item.get("voc_id") or ""),
        "source_type": str(voc_item.get("source_type") or "apify_comment"),
        "author": str(voc_item.get("author") or "Unknown"),
        "date": str(voc_item.get("date") or "Unknown"),
        "source_url": source_url,
        "quote": quote,
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
    source_refs: list[str],
    include_ads_context: bool = True,
    include_social_video: bool = True,
    include_external_voc: bool = True,
) -> dict[str, Any]:
    config = load_strategy_v2_apify_config()
    canonical_refs = _canonical_source_refs(source_refs)
    if not canonical_refs:
        raise RuntimeError(
            "Strategy V2 Apify ingestion requires at least one valid absolute http(s) source ref."
        )

    if not config.enabled:
        seed_candidates = _normalize_candidate_assets(raw_runs=[], seed_urls=canonical_refs)
        return {
            "enabled": False,
            "raw_runs": [],
            "candidate_assets": seed_candidates,
            "social_video_observations": [],
            "external_voc_items": [],
            "external_voc_corpus": [],
            "proof_asset_candidates": [],
            "ads_context": _build_ads_context_summary(
                enabled=False,
                candidate_assets=seed_candidates,
                source_refs=canonical_refs,
            ),
            "summary": {
                "run_count": 0,
                "candidate_asset_count": len(seed_candidates),
                "social_video_count": 0,
                "external_voc_count": 0,
                "proof_candidate_count": 0,
            },
        }

    apify = ApifyClient()
    raw_runs: list[dict[str, Any]] = []

    urls_by_platform: dict[str, list[str]] = {}
    for ref in canonical_refs:
        urls_by_platform.setdefault(derive_platform_from_ref(ref), []).append(ref)

    planned_runs: list[tuple[str, dict[str, Any]]] = []
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
        planned_runs.append((config.meta_actor_id, meta_payload))

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
                )
            )
        planned_runs.append(
            (
                config.web_actor_id,
                _build_web_actor_input(
                    urls=canonical_refs[: min(len(canonical_refs), 10)],
                    max_items=config.max_items_per_dataset,
                ),
            )
        )

    if len(planned_runs) > config.max_actor_runs:
        raise RuntimeError(
            "Strategy V2 Apify ingestion planned actor runs exceed STRATEGY_V2_APIFY_MAX_ACTOR_RUNS "
            f"({len(planned_runs)} > {config.max_actor_runs})."
        )

    for actor_id, payload in planned_runs:
        _ensure_actor_allowed(actor_id=actor_id, allowlist=config.allowed_actor_ids)
        raw_runs.append(
            _execute_actor(
                client=apify,
                actor_id=actor_id,
                input_payload=payload,
                max_wait_seconds=config.max_wait_seconds,
                max_items_per_dataset=config.max_items_per_dataset,
            )
        )

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
            "run_count": len(raw_runs),
            "candidate_asset_count": len(candidate_assets),
            "social_video_count": len(social_videos),
            "external_voc_count": len(external_voc_corpus),
            "proof_candidate_count": len(proof_asset_candidates),
        },
    }
