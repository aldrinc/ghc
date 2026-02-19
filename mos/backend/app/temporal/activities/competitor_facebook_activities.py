from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from temporalio import activity

from app.ads.normalization import normalize_facebook_page_url
from app.llm import LLMClient, LLMGenerationParams
from app.observability import LangfuseTraceContext, bind_langfuse_trace_context
from app.schemas.competitors import CompetitorRow, ResolveFacebookRequest, ResolveFacebookResult


logger = logging.getLogger(__name__)

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_FACEBOOK_URL_RE = re.compile(
    r"""(?:(?:https?:)?//|https:\\/\\/)(?:www\\.|m\\.)?facebook\.com/[^"' <>\s]+""",
    re.IGNORECASE,
)


def _shorten(text: str, max_len: int = 4000) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _normalize_extracted_url(candidate: str) -> str:
    value = (candidate or "").strip()
    if not value:
        return ""
    value = value.replace("\\/", "/")
    value = value.rstrip(").,;]")
    if value.startswith("https://") or value.startswith("http://"):
        return value
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("https:/") and not value.startswith("https://"):
        return value.replace("https:/", "https://", 1)
    if value.startswith("http:/") and not value.startswith("http://"):
        return value.replace("http:/", "http://", 1)
    return value


def _is_plausible_page_root(url: str) -> bool:
    """
    Additional guardrails beyond normalize_facebook_page_url:
    only accept URLs that look like canonical Page roots (one path segment).
    """
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False
    segments = [seg for seg in (parsed.path or "/").split("/") if seg]
    if len(segments) != 1:
        return False
    first = segments[0].lower()
    if first in {"sharer", "share", "plugins", "login", "pages", "profile.php"}:
        return False
    if first.endswith(".php"):
        return False
    if first.startswith("hashtag"):
        return False
    return True


def _score_candidate_for_brand(candidate_url: str, brand_name: str) -> int:
    # Cheap heuristic: reward substring matches between brand tokens and the FB slug.
    try:
        parsed = httpx.URL(candidate_url)
    except Exception:
        return 0
    segments = [seg for seg in (parsed.path or "/").split("/") if seg]
    slug = segments[0] if segments else ""
    slug_norm = re.sub(r"[^\w]+", " ", slug.lower()).strip()
    brand_norm = re.sub(r"[^\w]+", " ", (brand_name or "").lower()).strip()
    if not slug_norm or not brand_norm:
        return 0
    score = 0
    for token in brand_norm.split():
        if token and token in slug_norm:
            score += 1
    return score


def _extract_facebook_page_candidates(html: str) -> List[str]:
    candidates: List[str] = []
    for href in _HREF_RE.findall(html or ""):
        if "facebook.com" in (href or "").lower():
            candidates.append(href)
    for match in _FACEBOOK_URL_RE.findall(html or ""):
        candidates.append(match)

    normalized: List[str] = []
    for raw in candidates:
        cleaned = _normalize_extracted_url(raw)
        if not cleaned:
            continue
        canonical = normalize_facebook_page_url(cleaned)
        if not canonical:
            continue
        if not _is_plausible_page_root(canonical):
            continue
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def _website_fetch_candidates(website: Optional[str]) -> List[str]:
    if not website:
        return []
    website = str(website).strip().strip("`'\"")
    if not website:
        return []
    base: Optional[httpx.URL] = None
    for candidate in (website, f"https://{website}"):
        try:
            base = httpx.URL(str(candidate))
            break
        except Exception:
            continue
    if not base or not base.host:
        return []
    if base.scheme and base.scheme not in {"http", "https"}:
        return []

    candidates: List[str] = []
    candidates.append(str(base))
    home = str(base.copy_with(path="/", query=None, fragment=None))
    if home not in candidates:
        candidates.append(home)
    return candidates


def _resolve_facebook_from_website(
    client: httpx.Client, *, brand_name: str, website: Optional[str]
) -> Dict[str, Any]:
    """
    Best-effort deterministic extraction:
    fetch website HTML and pick a canonical Facebook Page URL.

    Returns:
      {facebook_page_url, confidence, evidence_links, error}
    """
    fetch_urls = _website_fetch_candidates(website)
    if not fetch_urls:
        return {"facebook_page_url": None, "confidence": None, "evidence_links": None, "error": "missing_website"}

    chosen: Optional[str] = None
    best_score = -1
    best_evidence: List[str] = []
    last_error: Optional[str] = None

    for fetch_url in fetch_urls:
        try:
            resp = client.get(fetch_url)
            resp.raise_for_status()
            html = resp.text or ""
        except Exception as exc:  # noqa: BLE001
            last_error = f"fetch_failed: {exc}"
            continue

        fb_candidates = _extract_facebook_page_candidates(html)
        if not fb_candidates:
            continue
        for fb in fb_candidates:
            score = _score_candidate_for_brand(fb, brand_name)
            if score > best_score:
                best_score = score
                chosen = fb
                best_evidence = [fetch_url, fb]
        if chosen and best_score >= 1:
            break

    if not chosen:
        return {
            "facebook_page_url": None,
            "confidence": None,
            "evidence_links": None,
            "error": last_error or "no_facebook_links_found",
        }

    confidence = 0.9 if best_score >= 1 else 0.75
    return {
        "facebook_page_url": chosen,
        "confidence": confidence,
        "evidence_links": best_evidence or [chosen],
        "error": None,
    }


@activity.defn
def resolve_competitor_facebook_pages_activity(request: ResolveFacebookRequest) -> ResolveFacebookResult:
    """
    Resolve official Facebook page URLs for competitors using LLM + (optional) web search.

    The activity is non-idempotent by nature (web/search/LLM), so the workflow
    should use a RetryPolicy with maximum_attempts=1.
    """
    competitors = request.competitors or []
    if not competitors:
        return ResolveFacebookResult(competitors=[], evidence={})

    model = (request.category_niche and None) or None  # placeholder to allow future specialization
    llm = LLMClient(default_model=model)
    params = LLMGenerationParams(
        model=model or llm.default_model,
        use_reasoning=True,
        use_web_search=True,
    )

    system_instructions = (
        "You are resolving *official brand Facebook pages* for competitors. Return ONLY a JSON array with one object "
        "per input competitor, in the same order. No prose outside the array.\n"
        "Each object must include: name, website, facebook_page_url (canonical Page URL or null), facebook_page_name "
        "(string or null), confidence (0-1 float), notes, evidence_links (array of strings).\n"
        "Rules:\n"
        "- facebook_page_url MUST be a Page URL starting with https://www.facebook.com/<page>. Do NOT return Ads "
        "Library URLs, posts, groups, events, reels, or query parameters.\n"
        "- Do NOT guess or return numeric page IDs; omit them entirely.\n"
        "- Prefer the official brand/business page in the relevant market.\n"
        "- If uncertain, set facebook_page_url to null and explain in notes.\n"
    )

    context_bits: List[str] = []
    if request.category_niche:
        context_bits.append(f"Category/Niche: {request.category_niche}")
    if request.org_id:
        context_bits.append(f"Org ID: {request.org_id}")
    if request.client_id:
        context_bits.append(f"Client ID: {request.client_id}")

    context_str = "\n".join(context_bits)

    # Step 1: deterministic extraction from competitor websites (fast, high-signal).
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MarketiBot/1.0; +https://marketi.local)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    timeout = httpx.Timeout(10.0, connect=5.0)
    updated_rows: List[Optional[CompetitorRow]] = [None for _ in competitors]
    unresolved: List[tuple[int, CompetitorRow]] = []
    deterministic_debug: Dict[str, Any] = {"resolved": 0, "unresolved": 0, "errors": []}

    with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
        for idx, competitor in enumerate(competitors):
            result = _resolve_facebook_from_website(
                client,
                brand_name=competitor.name,
                website=competitor.website,
            )
            fb_url = result.get("facebook_page_url")
            confidence = result.get("confidence")
            evidence_links = result.get("evidence_links")
            err = result.get("error")
            if err and err not in {"missing_website", "no_facebook_links_found"}:
                # Keep this small; the full resolution output is persisted as an artifact downstream.
                if len(deterministic_debug["errors"]) < 25:
                    deterministic_debug["errors"].append(
                        {"name": competitor.name, "website": competitor.website, "error": str(err)}
                    )
            if isinstance(fb_url, str) and fb_url:
                updated_rows[idx] = CompetitorRow(
                    name=competitor.name,
                    website=competitor.website,
                    facebook_page_url=fb_url,
                    facebook_page_url_source="website_html",
                    facebook_page_url_confidence=float(confidence)
                    if confidence is not None
                    else 0.8,
                    facebook_page_url_evidence=evidence_links if isinstance(evidence_links, list) else None,
                )
                deterministic_debug["resolved"] += 1
            else:
                unresolved.append((idx, competitor))
                deterministic_debug["unresolved"] += 1

    raw_response = ""
    error: Optional[str] = None

    # Step 2: LLM + web search for competitors that could not be deterministically resolved.
    if unresolved:
        payload: List[Dict[str, Optional[str]]] = []
        for _, competitor in unresolved:
            payload.append({"name": competitor.name, "website": competitor.website})

        prompt = system_instructions + "\n\n" + "Input competitors:\n" + json.dumps(
            payload, ensure_ascii=True, indent=2
        )
        if context_str:
            prompt += "\n\nAdditional context:\n" + context_str

        info = activity.info()
        trace_context = LangfuseTraceContext(
            name="workflow.competitor_facebook_resolution",
            session_id=f"{info.workflow_id}:{info.run_id}",
            metadata={
                "orgId": request.org_id,
                "clientId": request.client_id,
                "workflowId": info.workflow_id,
                "workflowRunId": info.run_id,
                "resolvedCount": deterministic_debug["resolved"],
                "unresolvedCount": deterministic_debug["unresolved"],
            },
            tags=["workflow", "activity", "competitor_resolution"],
        )
        with bind_langfuse_trace_context(trace_context):
            raw_response = llm.generate_text(prompt, params)

        parsed_json: Any = None
        try:
            parsed_json = json.loads(raw_response)
        except Exception:
            try:
                start = raw_response.index("[")
                end = raw_response.rindex("]") + 1
                parsed_json = json.loads(raw_response[start:end])
            except Exception as exc:
                error = f"Failed to parse JSON from LLM response: {exc!r}"
                logger.exception("Failed to parse JSON from Facebook resolution response")

        results_list: List[Dict[str, Any]] = []
        if isinstance(parsed_json, list):
            results_list = [item for item in parsed_json if isinstance(item, dict)]
        else:
            if parsed_json is not None:
                error = "Parsed JSON was not a list of objects."

        def _safe_confidence(value: Any) -> Optional[float]:
            try:
                num = float(value)
            except Exception:
                return None
            if num < 0 or num > 1:
                return None
            return num

        for local_idx, (orig_idx, competitor) in enumerate(unresolved):
            fb_url: Optional[str] = None
            confidence: Optional[float] = None
            evidence_links: Optional[List[str]] = None
            if local_idx < len(results_list):
                candidate = results_list[local_idx]
                candidate_url = candidate.get("facebook_page_url")
                normalized = normalize_facebook_page_url(candidate_url) if isinstance(candidate_url, str) else None
                fb_url = normalized
                confidence = _safe_confidence(candidate.get("confidence"))
                maybe_links = candidate.get("evidence_links") or candidate.get("evidence_urls")
                if isinstance(maybe_links, list):
                    evidence_links = [str(link) for link in maybe_links if str(link).strip()]

            updated_rows[orig_idx] = CompetitorRow(
                name=competitor.name,
                website=competitor.website,
                facebook_page_url=fb_url,
                facebook_page_url_source="llm_web_search" if fb_url else None,
                facebook_page_url_confidence=confidence,
                facebook_page_url_evidence=evidence_links,
            )

    finalized: List[CompetitorRow] = []
    for competitor, maybe_row in zip(competitors, updated_rows):
        if maybe_row is None:
            finalized.append(CompetitorRow(name=competitor.name, website=competitor.website))
        else:
            finalized.append(maybe_row)

    evidence: Dict[str, str] = {
        "raw_response": _shorten(raw_response),
        "deterministic": _shorten(json.dumps(deterministic_debug, ensure_ascii=True), max_len=4000),
    }
    if error:
        evidence["error"] = error

    return ResolveFacebookResult(competitors=finalized, evidence=evidence)
