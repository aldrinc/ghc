from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from temporalio import activity

from app.llm import LLMClient, LLMGenerationParams
from app.schemas.competitors import CompetitorRow, ResolveFacebookRequest, ResolveFacebookResult


logger = logging.getLogger(__name__)

FACEBOOK_URL_RE = re.compile(r"^https?://(www\.)?facebook\.com/", re.IGNORECASE)
INVALID_FACEBOOK_PATH_TOKENS = [
    "/sharer",
    "/share",
    "/dialog/",
    "/story.php",
    "/photo.php",
    "/permalink.php",
    "/posts/",
]


def _is_valid_facebook_page_url(url: str) -> bool:
    if not url:
        return False
    if not FACEBOOK_URL_RE.match(url.strip()):
        return False
    parsed = urlparse(url)
    path_lower = (parsed.path or "").lower()
    for token in INVALID_FACEBOOK_PATH_TOKENS:
        if token in path_lower:
            return False
    return True


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
                "example_ads_library_url": "https://www.facebook.com/ads/library/?view_all_page_id=<PAGE_ID>",
            }
        )

    system_instructions = (
        "You are resolving *official brand Facebook pages* for a list of competitors.\n"
        "You must return ONLY a JSON array with one object per input competitor, in the *same order*.\n"
        "Each object must have: name, website, facebook_page_url, facebook_page_id (string, numeric if available), "
        "confidence (0-1 float), notes, evidence_urls (array of strings).\n"
        "Rules:\n"
        "- facebook_page_url must be the canonical brand page (not posts/shares/ads); must start with https://www.facebook.com/.\n"
        "- Extract the numeric page ID if present (from page URL, Ads Library view_all_page_id, or page_id parameter). "
        "If you cannot find a numeric ID, set facebook_page_id to null.\n"
        "- Prefer the official brand/business page in the relevant market.\n"
        "- If uncertain, set facebook_page_url to null and explain in notes.\n"
        "- Do not include any explanation outside the JSON array.\n"
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

    updated_competitors: List[CompetitorRow] = []
    for idx, competitor in enumerate(competitors):
        fb_url: Optional[str] = None
        fb_id: Optional[str] = None
        if idx < len(results_list):
            candidate = results_list[idx]
            candidate_url = candidate.get("facebook_page_url")
            candidate_id = candidate.get("facebook_page_id")
            if isinstance(candidate_url, str) and _is_valid_facebook_page_url(candidate_url):
                fb_url = candidate_url.strip()
            if isinstance(candidate_id, str) and candidate_id.strip():
                fb_id = candidate_id.strip()
        updated_competitors.append(
            CompetitorRow(
                name=competitor.name,
                website=competitor.website,
                facebook_page_url=fb_url,
                facebook_page_id=fb_id,
            )
        )

    evidence: Dict[str, str] = {
        "raw_response": _shorten(raw_response),
    }
    if error:
        evidence["error"] = error

    return ResolveFacebookResult(competitors=updated_competitors, evidence=evidence)
