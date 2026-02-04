from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from temporalio import activity

from app.ads.normalization import normalize_facebook_page_url
from app.llm import LLMClient, LLMGenerationParams
from app.schemas.competitors import CompetitorRow, ResolveFacebookRequest, ResolveFacebookResult


logger = logging.getLogger(__name__)


def _shorten(text: str, max_len: int = 4000) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


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

    payload: List[Dict[str, Optional[str]]] = []
    for c in competitors:
        payload.append(
            {
                "name": c.name,
                "website": c.website,
            }
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

    prompt = system_instructions + "\n\n" + "Input competitors:\n" + json.dumps(payload, ensure_ascii=True, indent=2)
    if context_str:
        prompt += "\n\nAdditional context:\n" + context_str

    raw_response = llm.generate_text(prompt, params)

    parsed_json: Any = None
    error: Optional[str] = None

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

    updated_competitors: List[CompetitorRow] = []
    for idx, competitor in enumerate(competitors):
        fb_url: Optional[str] = None
        confidence: Optional[float] = None
        evidence_links: Optional[List[str]] = None
        if idx < len(results_list):
            candidate = results_list[idx]
            candidate_url = candidate.get("facebook_page_url")
            normalized = normalize_facebook_page_url(candidate_url) if isinstance(candidate_url, str) else None
            fb_url = normalized
            confidence = _safe_confidence(candidate.get("confidence"))
            maybe_links = candidate.get("evidence_links") or candidate.get("evidence_urls")
            if isinstance(maybe_links, list):
                evidence_links = [str(link) for link in maybe_links if str(link).strip()]

        updated_competitors.append(
            CompetitorRow(
                name=competitor.name,
                website=competitor.website,
                facebook_page_url=fb_url,
                facebook_page_url_source="llm_web_search" if fb_url else None,
                facebook_page_url_confidence=confidence,
                facebook_page_url_evidence=evidence_links,
            )
        )

    evidence: Dict[str, str] = {
        "raw_response": _shorten(raw_response),
    }
    if error:
        evidence["error"] = error

    return ResolveFacebookResult(competitors=updated_competitors, evidence=evidence)
