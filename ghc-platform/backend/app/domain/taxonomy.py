from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class TaxonomyError(ValueError):
    kind: str
    value: str
    allowed: list[str]

    def __str__(self) -> str:
        return f"Invalid {self.kind} '{self.value}'. Allowed: {', '.join(self.allowed)}"


EVIDENCE_TYPES = {
    "transcript_segment",
    "storyboard_scene",
    "numeric_claim",
    "targeting_signal",
    "narrative_beat",
    "proof_usage",
    "cta",
    "production_requirement",
    "ad_copy_block",
}

SPEAKER_ROLES = {"narrator", "spokesperson", "testimonial", "actor", "unknown"}
SIGNAL_MODALITIES = {"visual", "text", "audio"}
SIGNAL_CATEGORIES = {
    "setting",
    "prop",
    "character",
    "action",
    "keyword",
    "pain_point",
    "outcome",
    "mechanism",
    "timeframe",
    "number",
    "authority_cue",
    "social_proof_cue",
}
BEAT_KEYS = {"hook", "lead", "problem", "agitate", "mechanism", "solution", "proof", "offer", "cta"}
PROOF_TYPES = {"ugc_text", "ugc_video", "authority", "stats", "science_signaling", "demo", "guarantee", "before_after"}
CTA_KINDS = {"mid_roll_soft", "mid_roll_direct", "end_roll_direct", "overlay", "button_only"}
VERIFICATION_STATUSES = {"unverified", "verified", "disputed"}
REQ_TYPES = {"location", "prop", "talent", "broll_query", "graphic_asset"}
AD_COPY_FIELDS = {"primary_text", "headline", "description", "cta_label", "destination_url"}

# Configurable/extendable sets
FUNNEL_STAGES = {"cold", "warm", "hot"}
ASSERTION_TYPES = {"why_it_wins", "predicted_audience", "awareness_stage", "repels", "algorithmic_thesis"}

_TAXONOMIES: dict[str, set[str]] = {
    "evidence_type": EVIDENCE_TYPES,
    "speaker_role": SPEAKER_ROLES,
    "signal_modality": SIGNAL_MODALITIES,
    "signal_category": SIGNAL_CATEGORIES,
    "beat_key": BEAT_KEYS,
    "proof_type": PROOF_TYPES,
    "cta_kind": CTA_KINDS,
    "verification_status": VERIFICATION_STATUSES,
    "req_type": REQ_TYPES,
    "ad_copy_field": AD_COPY_FIELDS,
    "funnel_stage": FUNNEL_STAGES,
    "assertion_type": ASSERTION_TYPES,
}


def _normalize(value: str | None) -> Optional[str]:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def assert_key(kind: str, value: str | None, *, allow_none: bool = True) -> Optional[str]:
    if value is None:
        if allow_none:
            return None
        raise TaxonomyError(kind, "None", sorted(_TAXONOMIES.get(kind, [])))
    normalized = _normalize(value)
    allowed = _TAXONOMIES.get(kind)
    if allowed and normalized not in allowed:
        raise TaxonomyError(kind, normalized or "", sorted(allowed))
    return normalized


def assert_one_of(kind: str, value: str | None) -> Optional[str]:
    return assert_key(kind, value, allow_none=True)


def assert_many_of(kind: str, values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    normalized_values: list[str] = []
    for val in values:
        normalized_values.append(assert_key(kind, val, allow_none=False) or "")
    return normalized_values


def funnel_stage_allowed(stage: str | None) -> Optional[str]:
    return assert_key("funnel_stage", stage, allow_none=True)


def assertion_type_allowed(assertion_type: str | None) -> Optional[str]:
    return assert_key("assertion_type", assertion_type, allow_none=True)
