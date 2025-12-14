from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PreCanonMarketResearchInput:
    org_id: str
    client_id: str
    onboarding_payload_id: str


@dataclass(frozen=True)
class ResearchArtifactRef:
    step_key: str
    doc_url: str
    doc_id: str
    summary: str
    prompt_sha256: str
    created_at_iso: str


@dataclass(frozen=True)
class PreCanonMarketResearchResult:
    artifacts: List[ResearchArtifactRef]
    canon_context: Dict[str, Any]


@dataclass(frozen=True)
class StepDefinition:
    key: str
    prompt_filename: str
    title: str
    summary_max_chars: int
    handoff_field: Optional[str] = None
    handoff_max_chars: Optional[int] = None
