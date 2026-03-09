from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from app.strategy_v2.contracts import (
    AwarenessAngleMatrix,
    CopyContextFiles,
    OfferPipelineConfig,
    OfferPipelineInput,
    OfferProductBrief,
    OfferProductConstraints,
    ProductBriefStage0,
    ProductBriefStage1,
    ProductBriefStage2,
    ProductBriefStage3,
    validate_stage0,
    validate_stage1,
)
from app.strategy_v2.errors import StrategyV2MissingContextError
from app.strategy_v2.pricing import parse_price_to_cents_and_currency, require_concrete_price


_MARKET_MATURITY_VALUES = ("Introduction", "Growth", "Maturity", "Decline")

_STEP4_CATEGORY_TO_DIMENSION: dict[str, str] = {
    "A": "identity_role",
    "B": "trigger_event",
    "C": "desired_outcome",
    "D": "failed_prior_solution",
    "E": "enemy_blame",
    "F": "fear_risk",
    "G": "failed_prior_solution",
    "H": "pain_problem",
    "I": "enemy_blame",
}

_STEP4_EMOTION_TO_VALENCE: dict[str, str] = {
    "anger": "FRUSTRATION",
    "outrage": "RAGE",
    "frustration": "FRUSTRATION",
    "fear": "ANXIETY",
    "anxiety": "ANXIETY",
    "worry": "ANXIETY",
    "shame": "SHAME",
    "guilt": "SHAME",
    "hope": "HOPE",
    "optimism": "HOPE",
    "relief": "RELIEF",
    "gratitude": "RELIEF",
    "pride": "PRIDE",
    "confidence": "PRIDE",
}

_CATEGORY_KEYWORD_STOPWORDS = {
    "and",
    "for",
    "the",
    "with",
    "from",
    "that",
    "this",
    "your",
    "you",
    "our",
    "their",
    "guide",
    "handbook",
    "system",
    "method",
    "solution",
    "product",
    "products",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _require_text(*, field_name: str, value: str | None, remediation: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise StrategyV2MissingContextError(
            f"Missing required field '{field_name}'. Remediation: {remediation}"
        )
    return cleaned


def _require_string_list(
    *,
    field_name: str,
    values: list[str],
    remediation: str,
) -> list[str]:
    cleaned = [item.strip() for item in values if isinstance(item, str) and item.strip()]
    if not cleaned:
        raise StrategyV2MissingContextError(
            f"Missing required field '{field_name}'. Remediation: {remediation}"
        )
    return cleaned


def _parse_price_to_cents_and_currency(price_text: str) -> tuple[int, str]:
    return parse_price_to_cents_and_currency(
        price_text=price_text,
        context="Offer pipeline input mapping",
    )


def _extract_step_content(
    *,
    precanon_research: Mapping[str, object],
    step_key: str,
    remediation: str,
) -> str:
    step_contents_raw = precanon_research.get("step_contents")
    if not isinstance(step_contents_raw, dict):
        raise StrategyV2MissingContextError(
            "Missing precanon_research.step_contents in client canon. "
            f"Remediation: {remediation}"
        )
    step_content = step_contents_raw.get(step_key)
    if not isinstance(step_content, str) or not step_content.strip():
        raise StrategyV2MissingContextError(
            f"Missing precanon step content '{step_key}'. Remediation: {remediation}"
        )
    return step_content


def _extract_first_json_object(raw_text: str) -> dict[str, object]:
    text = raw_text.strip()
    if not text:
        raise StrategyV2MissingContextError(
            "competitor_analysis.json source text is empty. "
            "Remediation: rerun precanon step 02 and persist structured competitor output."
        )

    start_index: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if start_index is None:
            if char == "{":
                start_index = index
                depth = 1
            continue

        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start_index : index + 1]
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    break
                return parsed

    raise StrategyV2MissingContextError(
        "Unable to parse competitor_analysis JSON from precanon step 02 output. "
        "Remediation: ensure step 02 persists a valid JSON object."
    )


def _extract_category_niche(step1_content: str) -> str | None:
    patterns = (
        r"(?im)^\s*category\s*/\s*niche\s*:\s*(.+)$",
        r"(?im)^\s*category_niche\s*[:=]\s*(.+)$",
        r"(?im)^\s*niche\s*:\s*(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, step1_content)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def _extract_structured_category_niche(precanon_research: Mapping[str, object]) -> str | None:
    raw_category = precanon_research.get("category_niche")
    if isinstance(raw_category, str) and raw_category.strip():
        return raw_category.strip()

    metadata = precanon_research.get("metadata")
    if isinstance(metadata, Mapping):
        nested = metadata.get("category_niche")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def _extract_market_maturity(step1_content: str) -> str | None:
    for candidate in _MARKET_MATURITY_VALUES:
        if re.search(rf"(?i)\b{re.escape(candidate)}\b", step1_content):
            return candidate
    return None


def _extract_primary_icps(step6_content: str) -> list[str]:
    candidates: list[str] = []
    for line in step6_content.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if re.match(r"^[-*]\s+", cleaned):
            text = re.sub(r"^[-*]\s+", "", cleaned).strip()
        elif re.match(r"^\d+[.)]\s+", cleaned):
            text = re.sub(r"^\d+[.)]\s+", "", cleaned).strip()
        else:
            continue
        if len(text) >= 8:
            candidates.append(text)
        if len(candidates) >= 3:
            break
    return candidates


def _extract_primary_segment_size_estimate(step6_content: str) -> str | None:
    patterns = (
        r"(?im)^\s*size(?:\s+estimate)?\s*[:=]\s*(.+)$",
        r"(?im)^\s*segment\s+size(?:\s+estimate)?\s*[:=]\s*(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, step6_content)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def _extract_primary_segment_key_differentiator(step6_content: str) -> str | None:
    patterns = (
        r"(?im)^\s*key\s+differentiator\s*[:=]\s*(.+)$",
        r"(?im)^\s*differentiator\s*[:=]\s*(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, step6_content)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def _extract_bottleneck(step6_content: str) -> str | None:
    patterns = (
        r"(?im)^\s*(?:primary|main|core|key|critical)?\s*bottleneck(?:\s+to\s+solve)?\s*[:=\-]\s*(.+)$",
        r"(?im)^\s*(?:primary|main|core|key|critical)?\s*bottleneck\s+segment(?:\s+identification)?\s*[:=\-]\s*(.+)$",
        r"(?im)\bbottleneck\s+segment\s*[:=\-]\s*(.+?)(?:[.\n]|$)",
        r"(?im)\b(?:primary|main|core|key|critical)?\s*bottleneck(?:\s+to\s+solve)?\s*[:=\-]\s*(.+?)(?:[.\n]|$)",
        r"(?im)^\s*highest(?:[-\s]+leverage)?\s+(?:segment|opportunity)\s*[:=\-]\s*(.+)$",
        r"(?im)^\s*(?:primary|main|core|key|critical)\s+(?:challenge|obstacle|constraint|friction(?:\s+point)?)\s*[:=\-]\s*(.+)$",
        r"(?im)^\s*(?:challenge|obstacle|constraint|friction(?:\s+point)?)\s*[:=\-]\s*(.+)$",
        r"(?im)^\s*primary\s+segment\s*[:=\-]\s*(.+)$",
        r"(?im)\b(?:the\s+)?primary\s+segment\s*(?:is|[:=\-])\s*(.+?)(?:[.\n]|$)",
        r"(?im)\bsegment\s+with\s+the\s+highest\s+product\s+is\s+(.+?)(?:[.\n]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, step6_content)
        if match and match.group(1).strip():
            return match.group(1).strip().strip("\"'")
    return None


def _extract_positioning_gaps(step1_content: str) -> list[str]:
    gaps: list[str] = []
    for line in step1_content.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if "gap" not in cleaned.lower() and "whitespace" not in cleaned.lower():
            continue
        if re.match(r"^[-*]\s+", cleaned):
            text = re.sub(r"^[-*]\s+", "", cleaned).strip()
            if len(text) >= 8:
                gaps.append(text)
    return gaps


def _extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for raw in re.findall(r"https?://[^\s)]+", text):
        cleaned = raw.strip().rstrip("`'\".,;:")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        urls.append(cleaned)
    return urls


def _extract_competitor_count(step1_content: str, competitor_urls: list[str]) -> int | None:
    explicit = re.search(r"(?im)validated\s+competitor[s]?\s*[:=]\s*(\d+)", step1_content)
    if explicit:
        return int(explicit.group(1))

    urls = _extract_urls(step1_content)
    if urls:
        return len(urls)

    if competitor_urls:
        return len(competitor_urls)

    return None


def _extract_explicit_product_category_keywords(step1_content: str) -> list[str]:
    patterns = (
        r"(?im)^\s*(?:product_)?category(?:\s+)?keywords?\s*[:=]\s*(.+)$",
        r"(?im)^\s*keywords?\s*[:=]\s*(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, step1_content)
        if not match or not match.group(1).strip():
            continue
        raw = match.group(1).strip()
        values = [item.strip() for item in re.split(r"[,;|/]", raw) if item.strip()]
        if values:
            return values
    return []


def _tokenize_keyword_candidates(text: str) -> list[str]:
    tokens = [token.strip().lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text)]
    return [token for token in tokens if token not in _CATEGORY_KEYWORD_STOPWORDS]


def _derive_product_category_keywords(
    *,
    category_niche: str,
    product_name: str,
    step1_content: str,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def _append(value: str) -> None:
        cleaned = value.strip().lower()
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        ordered.append(cleaned)

    explicit = _extract_explicit_product_category_keywords(step1_content)
    for item in explicit:
        _append(item)

    _append(category_niche)
    for part in re.split(r"[,/&|]", category_niche):
        _append(part)

    niche_tokens = _tokenize_keyword_candidates(category_niche)
    for token in niche_tokens:
        _append(token)

    if len(niche_tokens) >= 2:
        _append(f"{niche_tokens[0]} {niche_tokens[1]}")

    product_tokens = _tokenize_keyword_candidates(product_name)
    for token in product_tokens[:3]:
        _append(token)

    if len(ordered) < 3:
        raise StrategyV2MissingContextError(
            "Unable to derive at least 3 product_category_keywords for Stage 1. "
            "Remediation: include an explicit 'Product Category Keywords:' line in foundational step 01 "
            "with a comma-separated list."
        )
    return ordered[:8]


def translate_stage0(
    *,
    product_name: str | None,
    product_description: str | None,
    onboarding_payload: Mapping[str, object] | None,
    stage0_overrides: Mapping[str, object] | None,
) -> ProductBriefStage0:
    payload = onboarding_payload if onboarding_payload is not None else {}
    overrides = stage0_overrides if stage0_overrides is not None else {}

    override_name = overrides.get("product_name")
    override_description = overrides.get("description")
    override_price = overrides.get("price")
    override_customizable = overrides.get("product_customizable")
    override_urls = overrides.get("competitor_urls")

    resolved_name = (
        str(override_name).strip()
        if isinstance(override_name, str) and override_name.strip()
        else (product_name or "").strip()
        or (str(payload.get("product_name")).strip() if isinstance(payload.get("product_name"), str) else "")
    )
    resolved_description = (
        str(override_description).strip()
        if isinstance(override_description, str) and override_description.strip()
        else (product_description or "").strip()
        or (
            str(payload.get("product_description")).strip()
            if isinstance(payload.get("product_description"), str)
            else ""
        )
    )

    if isinstance(override_customizable, bool):
        resolved_customizable = override_customizable
    elif isinstance(payload.get("product_customizable"), bool):
        resolved_customizable = bool(payload.get("product_customizable"))
    else:
        raise StrategyV2MissingContextError(
            "Missing required field 'product_customizable'. Remediation: provide "
            "'product_customizable' in stage0_overrides when starting Strategy V2."
        )

    resolved_price: str
    if isinstance(override_price, str) and override_price.strip():
        resolved_price = override_price.strip()
    elif isinstance(payload.get("price"), str) and str(payload.get("price")).strip():
        resolved_price = str(payload.get("price")).strip()
    else:
        resolved_price = "TBD"
    if resolved_price.upper() != "TBD":
        resolved_price = require_concrete_price(price=resolved_price, context="Stage 0 translation")

    competitor_urls: list[str] = []
    raw_urls = override_urls if isinstance(override_urls, list) else payload.get("competitor_urls")
    if isinstance(raw_urls, list):
        for item in raw_urls:
            if isinstance(item, str) and item.strip():
                competitor_urls.append(item.strip())

    stage0_payload: dict[str, object] = {
        "schema_version": "2.0.0",
        "stage": 0,
        "product_name": _require_text(
            field_name="product_name",
            value=resolved_name,
            remediation="set product title before starting Strategy V2.",
        ),
        "description": _require_text(
            field_name="description",
            value=resolved_description,
            remediation="set product description before starting Strategy V2.",
        ),
        "price": resolved_price,
        "competitor_urls": competitor_urls,
        "product_customizable": resolved_customizable,
    }
    return validate_stage0(stage0_payload)


def translate_stage1(
    *,
    stage0: ProductBriefStage0,
    precanon_research: Mapping[str, object],
) -> ProductBriefStage1:
    step1_content = _extract_step_content(
        precanon_research=precanon_research,
        step_key="01",
        remediation="rerun precanon stage and ensure step 01 is persisted.",
    )
    step6_content = _extract_step_content(
        precanon_research=precanon_research,
        step_key="06",
        remediation="rerun precanon stage and ensure step 06 is persisted.",
    )

    category_niche = _extract_structured_category_niche(precanon_research)
    if not category_niche:
        category_niche = _extract_category_niche(step1_content)
    if not category_niche:
        raise StrategyV2MissingContextError(
            "Unable to extract 'category_niche' from precanon step 01 content. "
            "Remediation: provide structured category_niche in precanon_research or update "
            "step 01 output to include 'Category / Niche'."
        )

    primary_icps = _extract_primary_icps(step6_content)
    if len(primary_icps) < 3:
        raise StrategyV2MissingContextError(
            "Stage 1 requires at least 3 primary ICP segment lines from step 06. "
            "Remediation: update foundational step 06 output with 3+ explicit segments."
        )

    size_estimate = _extract_primary_segment_size_estimate(step6_content)
    key_differentiator = _extract_primary_segment_key_differentiator(step6_content)
    if size_estimate is None:
        size_estimate = primary_icps[1]
    if key_differentiator is None:
        key_differentiator = primary_icps[2]

    bottleneck = _extract_bottleneck(step6_content)
    if not isinstance(bottleneck, str) or not bottleneck.strip():
        step6_excerpt = " ".join(step6_content.split())[:240]
        raise StrategyV2MissingContextError(
            "Stage 1 requires a non-empty bottleneck in step 06 output. "
            "Remediation: include a 'Bottleneck:' line, an equivalent challenge/constraint label, "
            "or the explicit 'The PRIMARY SEGMENT is ...' statement in foundational step 06. "
            f"Observed step 06 excerpt: {step6_excerpt!r}"
        )

    discovered_competitor_urls = _extract_urls(step1_content)
    merged_competitor_urls: list[str] = []
    seen_urls: set[str] = set()
    for url in [*list(stage0.competitor_urls), *discovered_competitor_urls]:
        normalized = str(url).strip()
        if not normalized or normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        merged_competitor_urls.append(normalized)

    competitor_count_validated = _extract_competitor_count(step1_content, merged_competitor_urls)
    if competitor_count_validated is None or competitor_count_validated < 3:
        raise StrategyV2MissingContextError(
            "Stage 1 requires at least 3 validated competitors. "
            "Remediation: update foundational step 01 to include validated competitor count >= 3."
        )

    primary_segment = {
        "name": primary_icps[0],
        "size_estimate": size_estimate,
        "key_differentiator": key_differentiator,
    }
    stage1_payload: dict[str, object] = {
        "schema_version": "2.0.0",
        "stage": 1,
        "product_name": stage0.product_name,
        "description": stage0.description,
        "price": require_concrete_price(
            price=stage0.price,
            context="Stage 1 translation",
        ),
        "competitor_urls": merged_competitor_urls,
        "product_customizable": stage0.product_customizable,
        "category_niche": category_niche,
        "product_category_keywords": _derive_product_category_keywords(
            category_niche=category_niche,
            product_name=stage0.product_name,
            step1_content=step1_content,
        ),
        "market_maturity_stage": _extract_market_maturity(step1_content),
        "primary_segment": primary_segment,
        "bottleneck": bottleneck,
        "positioning_gaps": _extract_positioning_gaps(step1_content),
        "competitor_count_validated": competitor_count_validated,
        "primary_icps": primary_icps,
    }
    return validate_stage1(stage1_payload)


def extract_competitor_analysis(precanon_research: Mapping[str, object]) -> dict[str, object]:
    step2_content = _extract_step_content(
        precanon_research=precanon_research,
        step_key="02",
        remediation="rerun precanon stage and ensure step 02 competitor analysis is persisted.",
    )
    return _extract_first_json_object(step2_content)


def transform_step4_entries_to_agent2_corpus(
    step4_entries: list[Mapping[str, str]],
) -> list[dict[str, object]]:
    corpus: list[dict[str, object]] = []
    for index, entry in enumerate(step4_entries):
        source = str(entry.get("source") or "").strip()
        category = str(entry.get("category") or "").strip().upper()[:1]
        emotion = str(entry.get("emotion") or "").strip().lower()
        buyer_stage = str(entry.get("buyer_stage") or "UNKNOWN").strip()
        segment_hint = str(entry.get("segment_hint") or "None detected").strip()
        quote = str(entry.get("quote") or "").strip()
        if not source or not quote:
            continue

        mapped_dimension = _STEP4_CATEGORY_TO_DIMENSION.get(category)
        mapped_value = quote[:200]
        dimensions = {
            "trigger_event": "NONE",
            "pain_problem": "NONE",
            "desired_outcome": "NONE",
            "failed_prior_solution": "NONE",
            "enemy_blame": "NONE",
            "identity_role": segment_hint if segment_hint else "NONE",
            "fear_risk": "NONE",
        }
        if mapped_dimension is not None:
            dimensions[mapped_dimension] = mapped_value

        valence = "NEUTRAL"
        for token, mapped in _STEP4_EMOTION_TO_VALENCE.items():
            if token in emotion:
                valence = mapped
                break

        lowered_quote = quote.lower()
        compliance = "RED" if any(token in lowered_quote for token in ("cure", "treat", "diagnose")) else "YELLOW"
        if compliance == "YELLOW" and not any(
            token in lowered_quote
            for token in ("disease", "condition", "symptom", "drug", "medication", "diagnosis")
        ):
            compliance = "GREEN"

        corpus.append(
            {
                "voc_id": f"V{index + 1:03d}",
                "source_type": "existing_corpus",
                "author": "Anonymous",
                "date": "Unknown",
                "source_url": source,
                "quote": quote,
                "trigger_event": dimensions["trigger_event"],
                "pain_problem": dimensions["pain_problem"],
                "desired_outcome": dimensions["desired_outcome"],
                "failed_prior_solution": dimensions["failed_prior_solution"],
                "enemy_blame": dimensions["enemy_blame"],
                "identity_role": dimensions["identity_role"],
                "fear_risk": dimensions["fear_risk"],
                "emotional_valence": valence,
                "buyer_stage": buyer_stage,
                "demographic_signals": segment_hint if segment_hint else "None detected",
                "solution_sophistication": "UNKNOWN",
                "compliance_risk": compliance,
                "conversation_context": "Extracted from Stage 1 Deep Research — STEP4_CONTENT",
                "flags": ["EXISTING_CORPUS"],
            }
        )

    if not corpus:
        raise StrategyV2MissingContextError(
            "STEP4 transformation produced an empty Agent 2 corpus. "
            "Remediation: verify STEP4_CONTENT includes tagged SOURCE/CATEGORY/QUOTE blocks."
        )
    return corpus


def build_competitor_angle_map(competitor_analysis: Mapping[str, object]) -> list[dict[str, object]]:
    sheets = competitor_analysis.get("asset_observation_sheets")
    if not isinstance(sheets, list):
        raise StrategyV2MissingContextError(
            "competitor_analysis.asset_observation_sheets is required for Agent 3 competitor angle mapping."
        )

    grouped: dict[str, list[dict[str, str]]] = {}
    for raw_sheet in sheets:
        if not isinstance(raw_sheet, Mapping):
            continue
        competitor_name = str(raw_sheet.get("competitor_name") or raw_sheet.get("brand") or "").strip()
        if not competitor_name:
            competitor_name = "Unknown Competitor"
        grouped.setdefault(competitor_name, []).append(
            {
                "asset_id": str(raw_sheet.get("asset_id") or "").strip(),
                "primary_angle": str(raw_sheet.get("primary_angle") or raw_sheet.get("core_claim") or "").strip(),
                "core_claim": str(raw_sheet.get("core_claim") or raw_sheet.get("headline") or "").strip(),
                "implied_mechanism": str(raw_sheet.get("implied_mechanism") or "").strip(),
                "target_segment_description": str(raw_sheet.get("target_segment_description") or "").strip(),
                "hook_type": str(raw_sheet.get("hook_type") or "").strip(),
            }
        )

    angle_map: list[dict[str, object]] = []
    for competitor_name, assets in grouped.items():
        angle_map.append(
            {
                "competitor_name": competitor_name,
                "assets": assets,
            }
        )
    return angle_map


def extract_saturated_angles(
    competitor_analysis: Mapping[str, object],
    *,
    limit: int = 9,
) -> list[dict[str, str]]:
    saturation_map = competitor_analysis.get("saturation_map")
    if not isinstance(saturation_map, list):
        return []

    rows: list[dict[str, str]] = []
    for row in saturation_map:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or "").strip().upper()
        if status not in {"SATURATED", "CONTESTED"}:
            continue
        rows.append(
            {
                "angle": str(row.get("angle") or row.get("angle_name") or "").strip(),
                "driver": str(row.get("driver") or "").strip(),
                "status": status,
                "competitor_count": str(row.get("competitor_count") or "").strip(),
            }
        )

    rows.sort(
        key=lambda item: (
            0 if item["status"] == "SATURATED" else 1,
            item["competitor_count"],
            item["angle"],
        )
    )
    return rows[: max(1, limit)]


def derive_compliance_sensitivity(competitor_analysis: Mapping[str, object]) -> str:
    compliance = competitor_analysis.get("compliance_landscape")
    if not isinstance(compliance, dict):
        raise StrategyV2MissingContextError(
            "Missing competitor_analysis.compliance_landscape. Remediation: rerun competitor analysis export."
        )

    red_pct_value = compliance.get("red_pct")
    yellow_pct_value = compliance.get("yellow_pct")
    if not isinstance(red_pct_value, (int, float)) or not isinstance(yellow_pct_value, (int, float)):
        overall = compliance.get("overall")
        if not isinstance(overall, dict):
            raise StrategyV2MissingContextError(
                "Missing red/yellow percentages in compliance landscape. "
                "Remediation: include red_pct and yellow_pct in competitor_analysis.json."
            )
        red_pct_value = overall.get("red_pct")
        yellow_pct_value = overall.get("yellow_pct")

    if not isinstance(red_pct_value, (int, float)) or not isinstance(yellow_pct_value, (int, float)):
        raise StrategyV2MissingContextError(
            "Unable to derive compliance sensitivity; red/yellow percentages are missing. "
            "Remediation: include numeric compliance percentages in competitor_analysis.json."
        )

    if float(red_pct_value) > 0.30:
        return "high"
    if float(yellow_pct_value) > 0.30:
        return "medium"
    return "low"


def map_offer_pipeline_input(
    *,
    stage2: ProductBriefStage2,
    selected_angle_payload: Mapping[str, object],
    competitor_teardowns: str,
    voc_research: str,
    purple_ocean_research: str,
    business_model: str,
    funnel_position: str,
    target_platforms: list[str],
    target_regions: list[str],
    existing_proof_assets: list[str],
    brand_voice_notes: str,
    compliance_sensitivity: str,
    llm_model: str,
    max_iterations: int,
    score_threshold: float,
) -> OfferPipelineInput:
    price_cents, currency = _parse_price_to_cents_and_currency(stage2.price)
    product_brief_payload = OfferProductBrief(
        name=stage2.product_name,
        description=stage2.description,
        category=stage2.category_niche,
        price_cents=price_cents,
        currency=currency,
        business_model=_require_text(
            field_name="business_model",
            value=business_model,
            remediation="provide operator business_model before entering Stage 3.",
        ),
        funnel_position=_require_text(
            field_name="funnel_position",
            value=funnel_position,
            remediation="provide operator funnel_position before entering Stage 3.",
        ),
        target_platforms=_require_string_list(
            field_name="target_platforms",
            values=target_platforms,
            remediation="provide at least one target platform before entering Stage 3.",
        ),
        target_regions=_require_string_list(
            field_name="target_regions",
            values=target_regions,
            remediation="provide at least one target region before entering Stage 3.",
        ),
        product_customizable=stage2.product_customizable,
        constraints=OfferProductConstraints(
            compliance_sensitivity=_require_text(
                field_name="compliance_sensitivity",
                value=compliance_sensitivity,
                remediation="derive compliance sensitivity from competitor analysis before Stage 3.",
            ).lower(),
            existing_proof_assets=_require_string_list(
                field_name="existing_proof_assets",
                values=existing_proof_assets,
                remediation="provide existing proof asset notes before entering Stage 3.",
            ),
            brand_voice_notes=_require_text(
                field_name="brand_voice_notes",
                value=brand_voice_notes,
                remediation="provide operator brand_voice_notes before entering Stage 3.",
            ),
        ),
    ).model_dump(mode="python")
    payload = {
        "product_brief": product_brief_payload,
        "selected_angle": dict(selected_angle_payload),
        "competitor_teardowns": _require_text(
            field_name="competitor_teardowns",
            value=competitor_teardowns,
            remediation="pass competitor teardown content from upstream research artifacts.",
        ),
        "voc_research": _require_text(
            field_name="voc_research",
            value=voc_research,
            remediation="pass filtered VOC corpus for the selected angle.",
        ),
        "purple_ocean_research": _require_text(
            field_name="purple_ocean_research",
            value=purple_ocean_research,
            remediation="pass Agent 3 handoff content.",
        ),
        "config": OfferPipelineConfig(
            llm_model=_require_text(
                field_name="llm_model",
                value=llm_model,
                remediation="configure STRATEGY_V2_OFFER_MODEL before running Offer pipeline.",
            ),
            max_iterations=max_iterations,
            score_threshold=score_threshold,
        ).model_dump(mode="python"),
    }
    return OfferPipelineInput.model_validate(payload)


def awareness_angle_matrix_to_markdown(matrix: AwarenessAngleMatrix) -> str:
    m = matrix.awareness_framing
    return (
        f"# Awareness-Angle Matrix\n\n"
        f"## Angle\n"
        f"- Name: {matrix.angle_name}\n\n"
        f"## Unaware\n"
        f"- Frame: {m.unaware.frame}\n"
        f"- Headline Direction: {m.unaware.headline_direction}\n"
        f"- Entry Emotion: {m.unaware.entry_emotion}\n"
        f"- Exit Belief: {m.unaware.exit_belief}\n\n"
        f"## Problem-Aware\n"
        f"- Frame: {m.problem_aware.frame}\n"
        f"- Headline Direction: {m.problem_aware.headline_direction}\n"
        f"- Entry Emotion: {m.problem_aware.entry_emotion}\n"
        f"- Exit Belief: {m.problem_aware.exit_belief}\n\n"
        f"## Solution-Aware\n"
        f"- Frame: {m.solution_aware.frame}\n"
        f"- Headline Direction: {m.solution_aware.headline_direction}\n"
        f"- Entry Emotion: {m.solution_aware.entry_emotion}\n"
        f"- Exit Belief: {m.solution_aware.exit_belief}\n\n"
        f"## Product-Aware\n"
        f"- Frame: {m.product_aware.frame}\n"
        f"- Headline Direction: {m.product_aware.headline_direction}\n"
        f"- Entry Emotion: {m.product_aware.entry_emotion}\n"
        f"- Exit Belief: {m.product_aware.exit_belief}\n\n"
        f"## Most-Aware\n"
        f"- Frame: {m.most_aware.frame}\n"
        f"- Headline Direction: {m.most_aware.headline_direction}\n"
        f"- Entry Emotion: {m.most_aware.entry_emotion}\n"
        f"- Exit Belief: {m.most_aware.exit_belief}\n\n"
        f"## Constant Elements\n"
        + "\n".join(f"- {item}" for item in matrix.constant_elements)
        + "\n\n## Variable Elements\n"
        + "\n".join(f"- {item}" for item in matrix.variable_elements)
        + f"\n\n## Product Name First Appears\n- {matrix.product_name_first_appears or 'Not specified'}\n"
    ).strip()


def _load_default_mental_models_markdown() -> str:
    matches = sorted(
        (_repo_root() / "V2 Fixes").glob(
            "Copywriting Agent */01_governance/shared_context/mental-models.md"
        )
    )
    if len(matches) != 1:
        raise StrategyV2MissingContextError(
            "Unable to resolve default mental-models.md template from V2 Fixes. "
            "Remediation: ensure the copywriting shared context files are present."
        )
    return matches[0].read_text(encoding="utf-8").strip()


def build_copy_context_files(
    *,
    stage3: ProductBriefStage3,
    awareness_angle_matrix: AwarenessAngleMatrix,
    brand_voice_notes: str,
    compliance_notes: str,
    voc_quotes: list[str],
) -> CopyContextFiles:
    icp_lines = [item.strip() for item in stage3.primary_icps if isinstance(item, str) and item.strip()]
    while len(icp_lines) < 3:
        icp_lines.append(icp_lines[-1] if icp_lines else "Unspecified segment")

    pain_desire = stage3.selected_angle.definition.pain_desire
    pain_side = pain_desire.split("->", 1)[0].strip() if "->" in pain_desire else pain_desire.strip()
    goal_side = pain_desire.split("->", 1)[1].strip() if "->" in pain_desire else stage3.core_promise
    purchase_emotion = (stage3.purchase_emotion or "relief").strip()
    compliance_risk = (
        stage3.compliance_constraints.overall_risk
        if stage3.compliance_constraints is not None
        else "UNKNOWN"
    )

    audience_markdown = (
        f"# Audience + Product\n\n"
        f"## Audience\n"
        f"### Demographics\n"
        f"- Primary segment: {stage3.primary_segment.name}\n"
        f"- Segment size estimate: {stage3.primary_segment.size_estimate}\n"
        f"- Key differentiator: {stage3.primary_segment.key_differentiator}\n"
        f"- ICP 1: {icp_lines[0]}\n"
        f"- ICP 2: {icp_lines[1]}\n"
        f"- ICP 3: {icp_lines[2]}\n\n"
        f"### Pain Points\n"
        f"- {pain_side}\n"
        f"- Bottleneck: {stage3.bottleneck}\n"
        f"- Trigger context: {stage3.selected_angle.definition.trigger}\n\n"
        f"### Goals\n"
        f"- {goal_side}\n"
        f"- Achieve the core promise: {stage3.core_promise}\n"
        f"- Reduce risk while implementing {stage3.ums}\n\n"
        f"### Emotional Drivers\n"
        f"- Purchase emotion: {purchase_emotion}\n"
        f"- Desired belief shift: {stage3.selected_angle.definition.belief_shift.after}\n"
        f"- Confidence mechanism: {stage3.selected_angle.definition.mechanism_why}\n\n"
        f"### Fears\n"
        f"- Fear/risk language from angle evidence: {stage3.selected_angle.definition.trigger}\n"
        f"- Compliance risk posture: {compliance_risk}\n"
        f"- Fear of repeating failed approaches: {stage3.selected_angle.definition.mechanism_why}\n\n"
        f"### Curated VOC Quotes\n"
        + "\n".join(f"- \"{quote}\"" for quote in voc_quotes if quote.strip())
        + "\n\n## Product\n"
        f"- Name: {stage3.product_name}\n"
        f"- Description: {stage3.description}\n"
        f"- Price: {stage3.price or 'Not specified'}\n"
        f"- Category: {stage3.category_niche}\n\n"
        f"## Selected Angle\n"
        f"- Angle: {stage3.selected_angle.angle_name}\n"
        f"- Who: {stage3.selected_angle.definition.who}\n"
        f"- Pain/Desire: {stage3.selected_angle.definition.pain_desire}\n"
        f"- Mechanism: {stage3.selected_angle.definition.mechanism_why}\n"
        f"- Trigger: {stage3.selected_angle.definition.trigger}\n\n"
        f"## Offer Core\n"
        f"- UMP: {stage3.ump}\n"
        f"- UMS: {stage3.ums}\n"
        f"- Core Promise: {stage3.core_promise}\n"
        f"- Guarantee: {stage3.guarantee_type or 'Not specified'}\n"
        f"- Pricing Rationale: {stage3.pricing_rationale or 'Not specified'}\n\n"
        f"## Value Stack\n"
        + "\n".join(f"- {item}" for item in stage3.value_stack_summary)
    ).strip()

    brand_voice_markdown = (
        "# Brand Voice\n\n"
        + _require_text(
            field_name="brand_voice_notes",
            value=brand_voice_notes,
            remediation="provide operator brand voice notes in Offer pipeline inputs.",
        )
    )

    compliance_markdown = (
        "# Compliance\n\n"
        + _require_text(
            field_name="compliance_notes",
            value=compliance_notes,
            remediation="provide operator compliance notes in Offer pipeline inputs.",
        )
    )

    return CopyContextFiles(
        audience_product_markdown=audience_markdown,
        brand_voice_markdown=brand_voice_markdown,
        compliance_markdown=compliance_markdown,
        mental_models_markdown=_load_default_mental_models_markdown(),
        awareness_angle_matrix_markdown=awareness_angle_matrix_to_markdown(awareness_angle_matrix),
    )
