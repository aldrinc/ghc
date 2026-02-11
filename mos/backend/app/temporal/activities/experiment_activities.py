from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from temporalio import activity

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository
from app.db.base import session_scope
from app.schemas.experiment_spec import ExperimentSpecSet
from app.schemas.asset_brief import AssetBrief
from app.services.claude_files import (
    CLAUDE_DEFAULT_MODEL,
    build_document_blocks,
    call_claude_structured_message,
    ensure_uploaded_to_claude,
)


CLAUDE_EXPERIMENT_MODEL = os.getenv("CLAUDE_EXPERIMENT_MODEL", CLAUDE_DEFAULT_MODEL)
CLAUDE_ASSET_BRIEF_MODEL = os.getenv("CLAUDE_ASSET_BRIEF_MODEL", CLAUDE_DEFAULT_MODEL)
CLAUDE_STRUCTURED_MAX_TOKENS = int(os.getenv("CLAUDE_STRUCTURED_MAX_TOKENS", "4096"))
CLAUDE_ASSET_BRIEF_EXPERIMENTS_PER_CALL = int(os.getenv("CLAUDE_ASSET_BRIEF_EXPERIMENTS_PER_CALL", "1"))


def _normalize_token(value: str) -> str:
    return " ".join(value.strip().lower().split())

_DIGIT_RE = re.compile(r"\\d")
_UNVERIFIED_CLAIM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bfda\b", flags=re.IGNORECASE),
    re.compile(r"\bclinically\b", flags=re.IGNORECASE),
    re.compile(r"\bclinical\s+proof\b", flags=re.IGNORECASE),
    re.compile(r"\bclinical\s+trial\b", flags=re.IGNORECASE),
    re.compile(r"\bclinical\s+study\b", flags=re.IGNORECASE),
    re.compile(r"\bpatented\b", flags=re.IGNORECASE),
]
_NEGATING_CLAIM_HINTS = (
    "do not",
    "don't",
    "avoid",
    "without",
    "no ",
    "needs confirmation",
    "if verified",
    "unless verified",
)

EXPERIMENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "experiments": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "hypothesis": {"type": "string"},
                    "metricIds": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "variants": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "channels": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                "guardrails": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["id", "name", "channels"],
                        },
                    },
                    "sampleSizeEstimate": {"type": "integer"},
                    "durationDays": {"type": "integer"},
                    "budgetEstimate": {"type": "number"},
                },
                "required": ["id", "name", "metricIds", "variants"],
            },
        }
    },
    "required": ["experiments"],
}

ASSET_BRIEFS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "asset_briefs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "experimentId": {"type": "string"},
                    "variantId": {"type": "string"},
                    "variantName": {"type": "string"},
                    "creativeConcept": {"type": "string"},
                    "requirements": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "channel": {"type": "string"},
                                "format": {"type": "string"},
                                "angle": {"type": "string"},
                                "hook": {"type": "string"},
                                "funnelStage": {"type": "string"},
                            },
                            "required": ["channel", "format"],
                        },
                    },
                    "constraints": {"type": "array", "items": {"type": "string"}},
                    "toneGuidelines": {"type": "array", "items": {"type": "string"}},
                    "visualGuidelines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "experimentId", "variantId", "requirements"],
            },
        }
    },
    "required": ["asset_briefs"],
}


def _chunk_experiment_specs(experiments: list[dict[str, Any]], *, chunk_size: int) -> list[list[dict[str, Any]]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero for asset brief generation.")
    if not experiments:
        return []
    return [experiments[idx : idx + chunk_size] for idx in range(0, len(experiments), chunk_size)]


def _collect_expected_variant_pairs(experiments: list[dict[str, Any]]) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    for experiment in experiments:
        if not isinstance(experiment, dict):
            raise RuntimeError("Experiment specs must be objects.")
        experiment_id = experiment.get("id")
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise RuntimeError("Experiment spec is missing id during asset brief generation.")
        variants = experiment.get("variants")
        if not isinstance(variants, list) or not variants:
            raise RuntimeError(f"Experiment spec {experiment_id!r} is missing variants.")
        for variant in variants:
            if not isinstance(variant, dict):
                raise RuntimeError(f"Experiment spec {experiment_id!r} contains a non-object variant.")
            variant_id = variant.get("id")
            if not isinstance(variant_id, str) or not variant_id.strip():
                raise RuntimeError(f"Experiment spec {experiment_id!r} contains a variant missing id.")
            expected.add((experiment_id, variant_id))
    return expected


def _build_asset_brief_prompt(
    *,
    experiments_json: str,
    channel_hint: str,
    format_hint: str,
    tone_guidelines: list[str],
    constraints: list[str],
    chunk_index: int,
    chunk_total: int,
) -> str:
    return f"""
You are a creative strategist. Using the experiment specs below and the attached canon/strategy/research documents, create precise creative asset briefs.

- Cover each experiment variant with at least one brief.
- Include variantId (must match the experiment variant id) and variantName for each brief.
- Include 1-3 requirements per brief with channel + format + angle/hook and optional funnelStage.
- Respect tone guidelines and constraints if present; keep strings concise and production-ready.
- Do NOT invent product facts or policy specifics (warranty length, return window, price, FDA status, clinical study outcomes, time-to-results, session length, brightness levels).
- Do NOT include unverified regulatory/clinical claims. Avoid these terms unless they are explicitly verified in the attached product/offer facts: FDA, cleared, approved, clinically proven, clinical proof, patented.
- Do NOT use the phrases "clinical proof" or "clinically proven". Use "proof points" or "evidence" instead.
- If a brief needs that kind of proof, add a constraint like: \"Needs confirmation: regulatory or clinical claim support\" and rewrite the hook without the claim.
- Do NOT include numbers anywhere in creativeConcept, requirements[].angle, requirements[].hook, constraints, toneGuidelines, or visualGuidelines.
- If a brief depends on an unknown fact, add a constraint like: "Needs confirmation: <fact>" and keep the hook phrased without the fact.
- This request is chunk {chunk_index} of {chunk_total}; include only briefs for experiment variants present in this chunk.
{channel_hint}
{format_hint}

Experiment specs (inline):
{experiments_json}

Known tone guidelines: {tone_guidelines}
Known constraints: {constraints}

Return JSON that matches the asset_briefs schema.
"""


def _validate_asset_brief_variant_coverage(
    *,
    briefs_raw: list[dict[str, Any]],
    expected_variant_pairs: set[tuple[str, str]],
) -> None:
    seen_variant_pairs: set[tuple[str, str]] = set()
    unexpected_pairs: set[tuple[str, str]] = set()

    for brief in briefs_raw:
        experiment_id = brief.get("experimentId")
        variant_id = brief.get("variantId") or brief.get("variant_id")
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise RuntimeError("Asset brief generation missing experimentId.")
        if not isinstance(variant_id, str) or not variant_id.strip():
            raise RuntimeError("Asset brief generation missing variantId.")
        key = (experiment_id, variant_id)
        seen_variant_pairs.add(key)
        if key not in expected_variant_pairs:
            unexpected_pairs.add(key)

    if unexpected_pairs:
        rendered = ", ".join(sorted([f"{exp}:{var}" for exp, var in unexpected_pairs]))
        raise RuntimeError(f"Asset brief generation returned unknown experiment/variant combinations: {rendered}.")

    missing_pairs = expected_variant_pairs.difference(seen_variant_pairs)
    if missing_pairs:
        rendered = ", ".join(sorted([f"{exp}:{var}" for exp, var in missing_pairs]))
        raise RuntimeError(
            "Asset brief generation did not cover all approved experiment variants. "
            f"Missing combinations: {rendered}."
        )


def _find_unverified_claim_pattern(value: str) -> re.Pattern[str] | None:
    lowered = value.lower()
    for pattern in _UNVERIFIED_CLAIM_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        window_start = max(0, match.start() - 64)
        guardrail_window = lowered[window_start : match.start()]
        if any(hint in guardrail_window for hint in _NEGATING_CLAIM_HINTS):
            continue
        if any(hint in lowered for hint in ("needs confirmation", "if verified", "unless verified")):
            continue
        return pattern
    return None


def _load_metric(repo: ArtifactsRepository, org_id: str, client_id: str, product_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.metric_schema,
    )
    return artifact.data if artifact else {}


def _load_canon(repo: ArtifactsRepository, org_id: str, client_id: str, product_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.client_canon,
    )
    return artifact.data if artifact else {}


def _build_experiment_prompt(
    *,
    available_metric_ids: list[str],
    purple_ocean_angles: list[str],
    campaign_channels: Optional[list[str]] = None,
    asset_brief_types: Optional[list[str]] = None,
) -> str:
    if not available_metric_ids:
        raise RuntimeError("available_metric_ids cannot be empty when building experiment prompt.")
    if not purple_ocean_angles:
        raise RuntimeError(
            "purple_ocean_angles is required to build experiments. "
            "Precanon step 015 (Purple Ocean Angle Analysis) must be present in client canon."
        )
    channel_hint = ""
    format_hint = ""
    if campaign_channels:
        channel_hint = (
            f"\nCampaign channels (use ONLY these identifiers in variants): {campaign_channels}"
        )
    if asset_brief_types:
        format_hint = f"\nCreative brief types for this campaign: {asset_brief_types}"
    angles_hint = "\n".join([f"- {angle}" for angle in purple_ocean_angles])
    return f"""
You are a media & experiment architect. Use the attached client canon, Purple Ocean Angle Analysis, and metric schema to propose ONE experiment per Purple Ocean angle below.

Context hints:
- Available metricIds (use ONLY these exact ids in metricIds): {available_metric_ids}
{channel_hint}{format_hint}

Purple Ocean angle library (use these exact names as experiment.name):
{angles_hint}

Rules:
- Keep strings concise and actionable; no markdown.
- Return {len(purple_ocean_angles)} experiments (one per angle above).
- Each experiment.name must be exactly one of the angle names above (no prefixes/suffixes).
- Include exactly 2 variants per experiment:
  - var_control_generic: generic saturated control messaging (results-first). No regulatory claims.
  - var_angle: the purple-ocean angle. Describe messaging focus + what proof is required (do NOT invent specifics).
- Use only the campaign channels for each variant's channels list when provided.
- Map metricIds to the available metricIds list above.
- Do NOT invent product facts: warranty length, return period, price, FDA status, clinical study results, time-to-results, session length.
- Avoid unverified regulatory/clinical claims (FDA, clinically proven, clinical proof, patented). If proof is needed, state it as \"Needs confirmation\" rather than asserting it.
- Do NOT include any numbers in: experiment.name, experiment.hypothesis, variants[].description.

Hard banned words/phrases (do not use in any hypothesis or variant description unless explicitly verified elsewhere):
- FDA
- clinically proven
- clinical proof
- clinical trial
- clinical study
- patented

Return JSON only that conforms to the requested schema.
"""


def _extract_purple_ocean_angles(canon: Dict[str, Any]) -> list[str]:
    precanon = canon.get("precanon_research") if isinstance(canon, dict) else None
    step_contents = (precanon or {}).get("step_contents") if isinstance(precanon, dict) else None
    step_summaries = (precanon or {}).get("step_summaries") if isinstance(precanon, dict) else None

    content_015 = (step_contents or {}).get("015") if isinstance(step_contents, dict) else None
    summary_015 = (step_summaries or {}).get("015") if isinstance(step_summaries, dict) else None

    def _clean_title(title: str) -> str:
        cleaned = " ".join(title.replace("\u2011", "-").split()).strip()
        # Strip any parenthetical/tagline suffixes: "Angle Name (tagline...)".
        if " (" in cleaned:
            cleaned = cleaned.split(" (", 1)[0].strip()
        cleaned = cleaned.strip("*").strip()
        cleaned = cleaned.strip(".").strip()
        return cleaned

    angles: list[str] = []

    # Prefer parsing the detailed step content, but scope to the "Top 10" section to avoid
    # accidentally capturing other numbered lists (e.g. saturated control angles).
    if isinstance(content_015, str) and content_015.strip():
        scoped = content_015
        # Find the specific "Top 10 Purple Ocean angles" section header, not the executive summary title.
        header_match = re.search(
            r"^#{1,6}\s*Top\s*10.*purple\s*ocean.*angles",
            content_015,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if header_match:
            scoped = content_015[header_match.start() :]
        for match in re.finditer(r"^\s*\d+\)\s*\*\*(.+?)\*\*", scoped, flags=re.MULTILINE):
            title = match.group(1)
            if not isinstance(title, str):
                continue
            cleaned = _clean_title(title)
            if cleaned:
                angles.append(cleaned)
            if len(angles) >= 10:
                break

    # Fallback: parse the summary format if step contents are missing.
    if not angles and isinstance(summary_015, str) and summary_015.strip():
        # Summary format: "... Top 10 ...: A; B; C; ... . This is marketing research ..."
        lower = summary_015.lower()
        idx = lower.find("top 10")
        tail = summary_015[idx:] if idx != -1 else summary_015
        if ":" in tail:
            tail = tail.split(":", 1)[1]
        if "This is marketing research" in tail:
            tail = tail.split("This is marketing research", 1)[0]
        parts = [p.strip() for p in tail.replace("\n", " ").split(";")]
        for part in parts:
            if not part:
                continue
            cleaned = _clean_title(part)
            if cleaned:
                angles.append(cleaned)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for angle in angles:
        key = _normalize_token(angle)
        if key in seen:
            continue
        seen.add(key)
        out.append(angle)
    return out


def _build_client_canon_compact(canon: Dict[str, Any]) -> Dict[str, Any]:
    brand = canon.get("brand") if isinstance(canon, dict) else {}
    voice = canon.get("voiceOfCustomer") if isinstance(canon, dict) else {}
    constraints = canon.get("constraints") if isinstance(canon, dict) else {}
    patterns = canon.get("contentPatterns") if isinstance(canon, dict) else {}
    precanon = canon.get("precanon_research") if isinstance(canon, dict) else {}

    step_summaries = (precanon or {}).get("step_summaries") if isinstance(precanon, dict) else None
    step_summaries = step_summaries if isinstance(step_summaries, dict) else {}

    angles = _extract_purple_ocean_angles(canon)

    return {
        "clientId": canon.get("clientId"),
        "brand": {
            "story": (brand or {}).get("story"),
            "manifesto": (brand or {}).get("manifesto"),
            "values": (brand or {}).get("values") or [],
            "mission": (brand or {}).get("mission"),
            "toneOfVoice": (brand or {}).get("toneOfVoice") or {},
        },
        "offers": canon.get("offers") if isinstance(canon, dict) else [],
        "icps": canon.get("icps") if isinstance(canon, dict) else [],
        "voiceOfCustomer": {
            "quotes": (voice or {}).get("quotes") or [],
            "objections": (voice or {}).get("objections") or [],
            "triggers": (voice or {}).get("triggers") or [],
            "languagePatterns": (voice or {}).get("languagePatterns") or [],
        },
        "constraints": constraints or {},
        "contentPatterns": patterns or {},
        "precanon_research": {
            "step_summaries": step_summaries,
        },
        "purple_ocean_angles": angles,
    }


@activity.defn
def build_experiment_specs_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    campaign_id = params.get("campaign_id")
    idea_workspace_id = (
        params.get("idea_workspace_id")
        or params.get("workflow_id")
        or params.get("campaign_id")
        or params.get("client_id")
    )
    if not idea_workspace_id:
        idea_workspace_id = f"client-{client_id}"
    allow_claude_stub = bool(params.get("allow_claude_stub", False))
    model = params.get("model") or CLAUDE_EXPERIMENT_MODEL
    if not product_id:
        raise RuntimeError("product_id is required to generate experiment specs.")

    campaign_channels: Optional[list[str]] = None
    asset_brief_types: Optional[list[str]] = None
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        metric = _load_metric(repo, org_id, client_id, product_id)
        canon = _load_canon(repo, org_id, client_id, product_id)
        if campaign_id:
            campaigns_repo = CampaignsRepository(session)
            campaign = campaigns_repo.get(org_id=org_id, campaign_id=campaign_id)
            if not campaign:
                raise RuntimeError(f"Campaign not found for experiment generation: {campaign_id}")
            campaign_channels = [
                str(ch).strip() for ch in (campaign.channels or []) if isinstance(ch, str) and ch.strip()
            ]
            asset_brief_types = [
                str(t).strip() for t in (campaign.asset_brief_types or []) if isinstance(t, str) and t.strip()
            ]
            if not campaign_channels:
                raise RuntimeError("Campaign has no channels configured; update the campaign before generating angles.")
            if not asset_brief_types:
                raise RuntimeError(
                    "Campaign has no creative brief types configured; update the campaign before generating angles."
                )

    available_metrics = (
        metric.get("primaryKpis")
        or metric.get("primary_kpis")
        or metric.get("secondaryKpis")
        or metric.get("secondary_kpis")
        or metric.get("kpis")
        or metric.get("metrics")
        or []
    )
    if not available_metrics:
        raise RuntimeError("Metric schema has no KPI definitions; update metric schema before generating experiments.")

    available_metric_ids = [
        str(metric_id).strip()
        for metric_id in (available_metrics or [])
        if isinstance(metric_id, str) and str(metric_id).strip()
    ]
    if not available_metric_ids:
        raise RuntimeError(
            "Metric schema KPI definitions are present but invalid (expected non-empty strings)."
        )

    purple_ocean_angles = _extract_purple_ocean_angles(canon)
    if not purple_ocean_angles:
        raise RuntimeError(
            "Purple Ocean angles not found in client canon. "
            "Expected precanon_research step 015 to be present before generating experiments."
        )

    # Keep the experiment generator focused: upload a compact canon that includes Purple Ocean
    # angle names + step summaries, rather than passing the entire canon (which can be very large).
    canon_compact = _build_client_canon_compact(canon)
    canon_compact_bytes = json.dumps(canon_compact, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key="client_canon_compact",
        doc_title="Client Canon (Compact)",
        source_kind="client_canon_compact",
        step_key=None,
        filename="client_canon_compact.json",
        mime_type="text/plain",
        content_bytes=canon_compact_bytes,
        drive_doc_id=None,
        drive_url=None,
        allow_stub=allow_claude_stub,
    )

    # Ensure metric schema is available in this idea workspace so downstream steps can reuse it.
    metric_bytes = json.dumps(metric, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key="metric_schema",
        doc_title="Metric Schema",
        source_kind="metric_schema",
        step_key=None,
        filename="metric_schema.json",
        mime_type="text/plain",
        content_bytes=metric_bytes,
        drive_doc_id=None,
        drive_url=None,
        allow_stub=allow_claude_stub,
    )

    with session_scope() as session:
        ctx_repo = ClaudeContextFilesRepository(session)
        context_files = ctx_repo.list_for_workspace_or_client(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
        )

    context_files = [
        cf
        for cf in context_files
        if not (cf.doc_key or "").startswith(("strategy_sheet", "experiment_specs"))
    ]

    if not context_files:
        raise RuntimeError(
            f"No eligible Claude context files registered for workspace {idea_workspace_id}; "
            "client_canon and metric_schema are required."
        )

    def _pick_latest(files: list, *, doc_key: str):
        best = None
        for cf in files:
            if (cf.doc_key or "") != doc_key:
                continue
            if best is None:
                best = cf
                continue
            created_at = getattr(cf, "created_at", None)
            best_created_at = getattr(best, "created_at", None)
            if best_created_at is None:
                best = cf
                continue
            if created_at is not None and created_at > best_created_at:
                best = cf
        return best

    # Prefer a small, angle-focused context set.
    selected: list = []
    for key in ("client_canon_compact", "precanon:015", "precanon:07", "precanon:08", "precanon:09", "metric_schema"):
        picked = _pick_latest(context_files, doc_key=key)
        if picked is not None:
            selected.append(picked)

    if not any((cf.doc_key or "").startswith("client_canon") for cf in selected):
        raise RuntimeError("Missing required Claude context file: client_canon (expected client_canon_compact).")
    if not any((cf.doc_key or "").startswith("metric_schema") for cf in selected):
        raise RuntimeError("Missing required Claude context file: metric_schema.")
    if not any((cf.doc_key or "") == "precanon:015" for cf in selected):
        raise RuntimeError(
            "Missing required Claude context file: precanon:015 (Purple Ocean Angle Analysis). "
            "This is required to generate Purple Ocean-aligned experiments."
        )

    documents = build_document_blocks(selected)
    prompt = _build_experiment_prompt(
        available_metric_ids=available_metric_ids,
        purple_ocean_angles=purple_ocean_angles,
        campaign_channels=campaign_channels,
        asset_brief_types=asset_brief_types,
    )
    user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}, *documents]
    claude_response = call_claude_structured_message(
        model=model,
        system="Generate sharp, testable marketing experiments grounded in the attached context. Return JSON only.",
        user_content=user_content,
        output_schema=EXPERIMENT_SCHEMA,
        max_tokens=CLAUDE_STRUCTURED_MAX_TOKENS,
        temperature=0.2,
    )
    parsed = claude_response.get("parsed") or {}
    experiments = parsed.get("experiments") if isinstance(parsed, dict) else None

    if not experiments:
        raise RuntimeError("Claude did not return any experiments")

    if not isinstance(experiments, list):
        raise RuntimeError("Claude returned invalid experiments; expected a list.")
    if len(experiments) != len(purple_ocean_angles):
        raise RuntimeError(
            "Experiment spec generation returned the wrong number of experiments "
            f"(expected={len(purple_ocean_angles)}, got={len(experiments)})."
        )

    angle_set = {angle.strip() for angle in purple_ocean_angles if isinstance(angle, str) and angle.strip()}
    angle_norm = {_normalize_token(angle): angle for angle in angle_set}
    matched_angles: set[str] = set()

    missing_experiment_fields: list[str] = []
    invalid_channels: set[str] = set()
    allowed_channels = {_normalize_token(ch) for ch in campaign_channels or []}
    for exp in experiments:
        if not isinstance(exp, dict):
            missing_experiment_fields.append("experiment_object")
            continue
        if not exp.get("id") or not exp.get("name"):
            missing_experiment_fields.append("experiment_id_or_name")
        exp_name = exp.get("name")
        if isinstance(exp_name, str):
            exp_name_clean = exp_name.strip()
            if _DIGIT_RE.search(exp_name_clean):
                raise RuntimeError("Experiment names must not include numbers.")
            norm = _normalize_token(exp_name_clean)
            if norm not in angle_norm:
                raise RuntimeError(
                    "Experiment name must match a Purple Ocean angle exactly. "
                    f"Got name={exp_name_clean!r}."
                )
            matched_angles.add(norm)
        exp_hypothesis = exp.get("hypothesis")
        if isinstance(exp_hypothesis, str) and _DIGIT_RE.search(exp_hypothesis):
            raise RuntimeError("Experiment hypotheses must not include numbers.")
        variants = exp.get("variants") or []
        if not isinstance(variants, list) or not variants:
            missing_experiment_fields.append("variants")
            continue
        if len(variants) != 2:
            raise RuntimeError("Each experiment must include exactly 2 variants (control + angle).")
        for variant in variants:
            if not isinstance(variant, dict):
                missing_experiment_fields.append("variant_object")
                continue
            if not variant.get("id") or not variant.get("name"):
                missing_experiment_fields.append("variant_id_or_name")
            if not variant.get("description"):
                missing_experiment_fields.append("variant_description")
            desc = variant.get("description")
            if isinstance(desc, str) and _DIGIT_RE.search(desc):
                raise RuntimeError("Variant descriptions must not include numbers.")
            channels = variant.get("channels") or []
            if not isinstance(channels, list) or not channels:
                missing_experiment_fields.append("variant_channels")
            if campaign_channels and isinstance(channels, list):
                for channel in channels:
                    if not isinstance(channel, str) or _normalize_token(channel) not in allowed_channels:
                        invalid_channels.add(str(channel))
        metric_ids = exp.get("metricIds") or []
        if not isinstance(metric_ids, list) or not metric_ids:
            missing_experiment_fields.append("metricIds")
        else:
            # Enforce metricIds are from the allowed list we surfaced to the model.
            allowed_metric_ids = set(available_metric_ids)
            invalid_metric_ids = [m for m in metric_ids if not isinstance(m, str) or m not in allowed_metric_ids]
            if invalid_metric_ids:
                raise RuntimeError(
                    f"Experiment metricIds include unsupported ids: {invalid_metric_ids}. "
                    f"Allowed metricIds: {available_metric_ids}."
                )
    if matched_angles != set(angle_norm.keys()):
        missing = sorted(set(angle_norm.keys()) - matched_angles)
        raise RuntimeError(f"Experiment set did not cover all Purple Ocean angles. Missing: {missing}")
    if invalid_channels:
        invalid_list = ", ".join(sorted(invalid_channels))
        raise RuntimeError(
            f"Experiment spec variants include unsupported channels: {invalid_list}. "
            f"Allowed channels: {campaign_channels}."
        )
    if missing_experiment_fields:
        unique_missing = sorted(set(missing_experiment_fields))
        raise RuntimeError(
            f"Experiment spec generation missing required fields: {', '.join(unique_missing)}"
        )

    specs = ExperimentSpecSet(
        clientId=client_id,
        campaignId=campaign_id,
        experimentSpecs=experiments,  # type: ignore[arg-type]
    )
    data_out = specs.model_dump()
    data_out["rawPrompt"] = prompt
    data_out["claudeResponse"] = claude_response.get("raw")
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
            data=data_out,
        )
    experiments_bytes = json.dumps(data_out, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    experiments_doc_key = f"experiment_specs:{campaign_id or 'none'}"
    experiments_file_id = ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key=experiments_doc_key,
        doc_title="Experiment Specs",
        source_kind="experiment_specs",
        step_key=None,
        filename=f"{experiments_doc_key}.json",
        mime_type="text/plain",
        content_bytes=experiments_bytes,
        drive_doc_id=None,
        drive_url=None,
        allow_stub=allow_claude_stub,
    )
    data_out["claudeFileId"] = experiments_file_id
    return {"experiment_specs": experiments, "claude_file_id": experiments_file_id}


@activity.defn
def fetch_experiment_specs_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    campaign_id = params.get("campaign_id")
    experiment_ids = params.get("experiment_ids") or []

    if not campaign_id:
        raise RuntimeError("campaign_id is required to fetch experiment specs.")

    with session_scope() as session:
        repo = ArtifactsRepository(session)
        latest_spec = repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
        )
        if not latest_spec or not isinstance(latest_spec.data, dict):
            raise RuntimeError("Experiment specs not found for this campaign.")
        candidates = latest_spec.data.get("experimentSpecs") or latest_spec.data.get("experiment_specs") or []

    if experiment_ids:
        filtered = [spec for spec in candidates if isinstance(spec, dict) and spec.get("id") in experiment_ids]
    else:
        filtered = [spec for spec in candidates if isinstance(spec, dict)]

    if not filtered:
        raise RuntimeError("No experiment specs matched the selected angles.")

    return {"experiment_specs": filtered}


@activity.defn
def create_asset_briefs_for_experiments_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    org_id = params["org_id"]
    product_id = params.get("product_id")
    experiments = params.get("experiment_specs") or []
    experiment_ids = params.get("experiment_ids") or []
    funnel_map = params.get("funnel_map") or {}

    idea_workspace_id = (
        params.get("idea_workspace_id")
        or params.get("workflow_id")
        or params.get("campaign_id")
        or params.get("client_id")
    )
    if not idea_workspace_id:
        idea_workspace_id = f"client-{client_id}"
    allow_claude_stub = bool(params.get("allow_claude_stub", False))
    model = params.get("model") or CLAUDE_ASSET_BRIEF_MODEL
    if not product_id:
        raise RuntimeError("product_id is required to generate asset briefs.")

    campaign_channels: Optional[list[str]] = None
    asset_brief_types: Optional[list[str]] = None
    with session_scope() as session:
        ctx_repo = ClaudeContextFilesRepository(session)
        # Funnel generation runs may use a fresh Temporal workflow id as idea_workspace_id.
        # Use a broader context query (workspace OR client/campaign) so we can reuse the
        # already-uploaded onboarding + campaign planning docs without forcing a re-upload.
        context_files = ctx_repo.list_for_workspace_or_client(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
        )
        artifacts_repo = ArtifactsRepository(session)
        canon = artifacts_repo.get_latest_by_type(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=ArtifactTypeEnum.client_canon,
        )
        if campaign_id:
            campaigns_repo = CampaignsRepository(session)
            campaign = campaigns_repo.get(org_id=org_id, campaign_id=campaign_id)
            if not campaign:
                raise RuntimeError(f"Campaign not found for asset brief generation: {campaign_id}")
            campaign_channels = [
                str(ch).strip() for ch in (campaign.channels or []) if isinstance(ch, str) and ch.strip()
            ]
            asset_brief_types = [
                str(t).strip() for t in (campaign.asset_brief_types or []) if isinstance(t, str) and t.strip()
            ]
            if not campaign_channels:
                raise RuntimeError("Campaign has no channels configured; update the campaign before creating briefs.")
            if not asset_brief_types:
                raise RuntimeError(
                    "Campaign has no creative brief types configured; update the campaign before creating briefs."
                )
        if not experiments and experiment_ids:
            latest_spec = (
                artifacts_repo.get_latest_by_type_for_campaign(
                    org_id=org_id,
                    campaign_id=campaign_id,
                    artifact_type=ArtifactTypeEnum.experiment_spec,
                )
                if campaign_id
                else artifacts_repo.get_latest_by_type(
                    org_id=org_id,
                    client_id=client_id,
                    product_id=product_id,
                    artifact_type=ArtifactTypeEnum.experiment_spec,
                )
            )
            if latest_spec and isinstance(latest_spec.data, dict):
                candidates = latest_spec.data.get("experimentSpecs") or latest_spec.data.get("experiment_specs") or []
                experiments = [spec for spec in candidates if spec.get("id") in experiment_ids] or candidates

    if not experiments:
        raise RuntimeError("No experiment_specs provided for asset brief generation")

    if funnel_map and not isinstance(funnel_map, dict):
        raise RuntimeError("funnel_map must be a dictionary of experimentId:variantId -> funnelId")

    if not context_files:
        raise RuntimeError(f"No Claude context files registered for workspace {idea_workspace_id}")

    def _pick_latest(files: list, *, doc_key: str):
        best = None
        for cf in files:
            if (cf.doc_key or "") != doc_key:
                continue
            if best is None:
                best = cf
                continue
            created_at = getattr(cf, "created_at", None)
            best_created_at = getattr(best, "created_at", None)
            if best_created_at is None:
                best = cf
                continue
            if created_at is not None and created_at > best_created_at:
                best = cf
        return best

    tone_guidelines = []
    constraints = []
    if canon and isinstance(canon.data, dict):
        tone = canon.data.get("brand", {}).get("toneOfVoice") or canon.data.get("tone_of_voice")
        if tone:
            tone_guidelines = (tone.get("do") or []) + (tone.get("dont") or [])
        cons = canon.data.get("constraints") or {}
        constraints = cons.get("brand") or cons.get("legal") or []

    # Keep the context set small so we stay within model token limits.
    selected: list = []
    strategy_doc_key = f"strategy_sheet:{campaign_id or 'none'}"
    for key in (
        "client_canon_compact",
        "client_canon",
        "precanon:07",
        "precanon:08",
        "precanon:09",
        "metric_schema",
        strategy_doc_key,
    ):
        picked = _pick_latest(context_files, doc_key=key)
        if picked is not None:
            selected.append(picked)

    if not any((cf.doc_key or "").startswith("client_canon") for cf in selected):
        raise RuntimeError("Missing required Claude context file: client_canon (expected client_canon_compact).")

    if CLAUDE_ASSET_BRIEF_EXPERIMENTS_PER_CALL <= 0:
        raise RuntimeError("CLAUDE_ASSET_BRIEF_EXPERIMENTS_PER_CALL must be greater than zero.")

    documents = build_document_blocks(selected)
    channel_hint = ""
    format_hint = ""
    if campaign_channels:
        channel_hint = f"Allowed channels (use ONLY these identifiers): {campaign_channels}"
    if asset_brief_types:
        format_hint = f"Allowed formats (use ONLY these identifiers): {asset_brief_types}"
    normalized_experiments: list[dict[str, Any]] = []
    for experiment in experiments:
        if not isinstance(experiment, dict):
            raise RuntimeError("Experiment specs must be objects.")
        normalized_experiments.append(experiment)

    experiment_chunks = _chunk_experiment_specs(
        normalized_experiments,
        chunk_size=CLAUDE_ASSET_BRIEF_EXPERIMENTS_PER_CALL,
    )
    if not experiment_chunks:
        raise RuntimeError("No valid experiment specs available for asset brief generation.")

    chunk_prompts: list[str] = []
    claude_raw_responses: list[Any] = []
    briefs_raw: list[dict[str, Any]] = []
    for chunk_idx, chunk in enumerate(experiment_chunks, start=1):
        experiments_json = json.dumps({"experiments": chunk}, ensure_ascii=True, indent=2)
        prompt = _build_asset_brief_prompt(
            experiments_json=experiments_json,
            channel_hint=channel_hint,
            format_hint=format_hint,
            tone_guidelines=tone_guidelines,
            constraints=constraints,
            chunk_index=chunk_idx,
            chunk_total=len(experiment_chunks),
        )
        chunk_prompts.append(prompt)
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}, *documents]
        claude_response = call_claude_structured_message(
            model=model,
            system="Generate actionable creative briefs that align with the attached context and experiment goals.",
            user_content=user_content,
            output_schema=ASSET_BRIEFS_SCHEMA,
            max_tokens=CLAUDE_STRUCTURED_MAX_TOKENS,
            temperature=0.4,
        )
        claude_raw_responses.append(claude_response.get("raw"))
        parsed = claude_response.get("parsed") or {}
        chunk_briefs = parsed.get("asset_briefs") if isinstance(parsed, dict) else None
        if not chunk_briefs:
            raise RuntimeError(
                f"Claude did not return any asset_briefs for chunk {chunk_idx}/{len(experiment_chunks)}."
            )
        for brief in chunk_briefs:
            if isinstance(brief, dict):
                briefs_raw.append(brief)

    if not briefs_raw:
        raise RuntimeError("Claude did not return any valid asset_briefs.")

    expected_variant_pairs = _collect_expected_variant_pairs(normalized_experiments)
    _validate_asset_brief_variant_coverage(
        briefs_raw=briefs_raw,
        expected_variant_pairs=expected_variant_pairs,
    )

    for brief in briefs_raw:
        if not isinstance(brief, dict):
            continue
        creative_concept = brief.get("creativeConcept")
        if isinstance(creative_concept, str) and _DIGIT_RE.search(creative_concept):
            raise RuntimeError("Asset brief creativeConcept must not include numbers.")
        if isinstance(creative_concept, str):
            pattern = _find_unverified_claim_pattern(creative_concept)
            if pattern:
                raise RuntimeError(
                    "Asset brief creativeConcept contains an unverified regulatory/clinical claim. "
                    f"Matched={pattern.pattern!r} creativeConcept={creative_concept!r}"
                )
        for list_key in ("constraints", "toneGuidelines", "visualGuidelines"):
            items = brief.get(list_key) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, str) and _DIGIT_RE.search(item):
                    raise RuntimeError(f"Asset brief {list_key} entries must not include numbers.")
                if isinstance(item, str):
                    pattern = _find_unverified_claim_pattern(item)
                    if pattern:
                        raise RuntimeError(
                            f"Asset brief {list_key} contains an unverified regulatory/clinical claim. "
                            f"Matched={pattern.pattern!r} value={item!r}"
                        )
        requirements = brief.get("requirements") or []
        if isinstance(requirements, list):
            for req in requirements:
                if not isinstance(req, dict):
                    continue
                for text_key in ("angle", "hook", "funnelStage"):
                    value = req.get(text_key)
                    if isinstance(value, str) and _DIGIT_RE.search(value):
                        raise RuntimeError(f"Asset brief requirements.{text_key} must not include numbers.")
                    if isinstance(value, str):
                        pattern = _find_unverified_claim_pattern(value)
                        if pattern:
                            raise RuntimeError(
                                f"Asset brief requirements.{text_key} contains an unverified regulatory/clinical claim. "
                                f"Matched={pattern.pattern!r} value={value!r}"
                            )

    invalid_channels: set[str] = set()
    invalid_formats: set[str] = set()
    allowed_channels = {_normalize_token(ch) for ch in campaign_channels or []}
    allowed_formats = {_normalize_token(fmt) for fmt in asset_brief_types or []}
    for brief in briefs_raw:
        requirements = brief.get("requirements") or []
        if not isinstance(requirements, list):
            continue
        for req in requirements:
            if not isinstance(req, dict):
                continue
            if campaign_channels:
                channel_value = req.get("channel")
                if not isinstance(channel_value, str) or _normalize_token(channel_value) not in allowed_channels:
                    invalid_channels.add(str(channel_value))
            if asset_brief_types:
                format_value = req.get("format")
                if not isinstance(format_value, str) or _normalize_token(format_value) not in allowed_formats:
                    invalid_formats.add(str(format_value))
    if invalid_channels:
        invalid_list = ", ".join(sorted(invalid_channels))
        raise RuntimeError(
            f"Asset brief requirements include unsupported channels: {invalid_list}. "
            f"Allowed channels: {campaign_channels}."
        )
    if invalid_formats:
        invalid_list = ", ".join(sorted(invalid_formats))
        raise RuntimeError(
            f"Asset brief requirements include unsupported formats: {invalid_list}. "
            f"Allowed formats: {asset_brief_types}."
        )

    briefs: List[AssetBrief] = []
    brief_ids: List[str] = []
    seen_brief_ids: set[str] = set()
    for brief in briefs_raw:
        brief_id = brief.get("id") or str(uuid4())
        if brief_id in seen_brief_ids:
            raise RuntimeError(f"Asset brief generation returned duplicate brief id: {brief_id}")
        seen_brief_ids.add(brief_id)
        variant_id = brief.get("variantId") or brief.get("variant_id")
        if not variant_id:
            raise RuntimeError("Asset brief generation missing variantId.")
        experiment_id = brief.get("experimentId")
        if funnel_map:
            if not experiment_id:
                raise RuntimeError("Asset brief generation missing experimentId for funnel mapping.")
            funnel_key = f"{experiment_id}:{variant_id}"
            funnel_id = funnel_map.get(funnel_key)
            if not funnel_id:
                raise RuntimeError(f"Funnel mapping missing for {funnel_key}.")
            brief["funnelId"] = funnel_id
        brief_obj = AssetBrief(
            id=brief_id,
            clientId=client_id,
            campaignId=campaign_id,
            experimentId=experiment_id,
            variantId=variant_id,
            funnelId=brief.get("funnelId"),
            variantName=brief.get("variantName") or brief.get("variant_name"),
            creativeConcept=brief.get("creativeConcept"),
            requirements=brief.get("requirements") or [],  # type: ignore[arg-type]
            constraints=brief.get("constraints") or constraints,
            toneGuidelines=brief.get("toneGuidelines") or tone_guidelines,
            visualGuidelines=brief.get("visualGuidelines") or [],
        )
        briefs.append(brief_obj)
        brief_ids.append(brief_id)

    data_out = [b.model_dump() for b in briefs]
    payload_to_store = {
        "asset_briefs": data_out,
        "rawPrompt": chunk_prompts[0] if len(chunk_prompts) == 1 else "\n\n--- chunk ---\n\n".join(chunk_prompts),
        "claudeResponse": claude_raw_responses[0] if len(claude_raw_responses) == 1 else claude_raw_responses,
        "chunk_count": len(experiment_chunks),
    }
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            data=payload_to_store,
        )

    briefs_bytes = json.dumps(payload_to_store, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    briefs_doc_key = f"asset_briefs:{campaign_id or 'none'}"
    claude_file_id = ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key=briefs_doc_key,
        doc_title="Asset Briefs",
        source_kind="asset_briefs",
        step_key=None,
        filename=f"{briefs_doc_key}.json",
        mime_type="text/plain",
        content_bytes=briefs_bytes,
        drive_doc_id=None,
        drive_url=None,
        allow_stub=allow_claude_stub,
    )

    return {"asset_brief_ids": brief_ids, "briefs": data_out, "claude_file_id": claude_file_id}
