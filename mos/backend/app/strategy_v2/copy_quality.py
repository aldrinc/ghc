from __future__ import annotations

import re
from typing import Literal, NamedTuple

from pydantic import Field

from app.strategy_v2.contracts import SCHEMA_VERSION_V2, StrictContract
from app.strategy_v2.copy_contract_spec import (
    CopyPageContract,
    get_copy_quality_thresholds,
)
from app.strategy_v2.errors import StrategyV2DecisionError


_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
_LINK_CAPTURE_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CTA_CANONICAL_TITLE_RE = re.compile(r"\b(?:cta|continue\s+to\s+offer)\b", re.IGNORECASE)
_CTA_ANCHOR_INTENT_PATTERNS = (
    re.compile(r"\bbuy\s+(?:now|today|here|this|your)\b", re.IGNORECASE),
    re.compile(r"\b(?:order|checkout|check\s*out)\s+(?:now|today|here)\b", re.IGNORECASE),
    re.compile(r"\bplace\s+(?:your\s+)?order\b", re.IGNORECASE),
    re.compile(r"\bstart(?:\s+checkout|\s+order|\s+purchase)\b", re.IGNORECASE),
    re.compile(r"\bclick\s+here\s+to\s+(?:buy|order|checkout|start)\b", re.IGNORECASE),
    re.compile(r"\bclaim\s+(?:your|my|this)\s+(?:copy|spot|access)\b", re.IGNORECASE),
    re.compile(r"\bcomplete\s+(?:the\s+)?purchase\b", re.IGNORECASE),
    re.compile(r"\benroll\s+now\b", re.IGNORECASE),
    re.compile(r"\bsecure\s+(?:your|my)\s+(?:copy|spot|access)\b", re.IGNORECASE),
    re.compile(r"\badd\s+to\s+cart\b", re.IGNORECASE),
)
_CTA_BODY_INTENT_PATTERNS = (
    re.compile(r"\bbuy\s+(?:now|today|here|this|your)\b", re.IGNORECASE),
    re.compile(r"\b(?:order|checkout|check\s*out)\s+(?:now|today|here)\b", re.IGNORECASE),
    re.compile(r"\bplace\s+(?:your\s+)?order\b", re.IGNORECASE),
    re.compile(r"\bstart(?:\s+checkout|\s+order|\s+purchase)\b", re.IGNORECASE),
    re.compile(r"\bclick\s+here\s+to\s+(?:buy|order|checkout|start)\b", re.IGNORECASE),
    re.compile(r"\bclaim\s+(?:your|my|this)\s+(?:copy|spot|access)\b", re.IGNORECASE),
    re.compile(r"\bcomplete\s+(?:the\s+)?purchase\b", re.IGNORECASE),
    re.compile(r"\benroll\s+now\b", re.IGNORECASE),
    re.compile(r"\bsecure\s+(?:your|my)\s+(?:copy|spot|access)\b", re.IGNORECASE),
    re.compile(r"\badd\s+to\s+cart\b", re.IGNORECASE),
)


class _CTASectionSignals(NamedTuple):
    is_canonical_cta_title: bool
    has_anchor_cta_intent: bool
    has_body_cta_intent: bool

    @property
    def is_cta_section(self) -> bool:
        # CTA section counting is canonical-title based to avoid inflating counts
        # from informational sections (e.g. Problem Recap/FAQ) that may contain
        # neutral links or non-transactional language.
        return self.is_canonical_cta_title


class CopyQualityGateResult(StrictContract):
    gate_key: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    passed: bool
    detail: str = Field(min_length=1)
    remediation: str | None = None


class CopySectionWordCount(StrictContract):
    section_index: int = Field(ge=1)
    section_title: str = Field(min_length=1)
    word_count: int = Field(ge=0)


class CopyPageQualityReport(StrictContract):
    schema_version: Literal["2.0.0"] = SCHEMA_VERSION_V2
    page_type: Literal["presell_advertorial", "sales_page_warm"]
    passed: bool
    total_words: int = Field(ge=0)
    section_count: int = Field(ge=0)
    cta_count: int = Field(ge=0)
    first_cta_word_ratio: float | None = None
    section_word_counts: list[CopySectionWordCount] = Field(default_factory=list)
    gates: list[CopyQualityGateResult] = Field(default_factory=list)


def _count_words(value: str) -> int:
    return len(_WORD_RE.findall(value))


def _parse_h2_sections(markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = stripped[3:].strip()
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(line)
    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections


def _is_canonical_cta_title(title: str) -> bool:
    return _CTA_CANONICAL_TITLE_RE.search(title or "") is not None


def _has_anchor_cta_intent(body: str) -> bool:
    for anchor_text, _url in _LINK_CAPTURE_RE.findall(body):
        anchor = (anchor_text or "").strip()
        if not anchor:
            continue
        if any(pattern.search(anchor) for pattern in _CTA_ANCHOR_INTENT_PATTERNS):
            return True
    return False


def _has_body_cta_intent(*, title: str, body: str) -> bool:
    merged = f"{title}\n{body}"
    return any(pattern.search(merged) for pattern in _CTA_BODY_INTENT_PATTERNS)


def _cta_section_signals(*, title: str, body: str) -> _CTASectionSignals:
    return _CTASectionSignals(
        is_canonical_cta_title=_is_canonical_cta_title(title),
        has_anchor_cta_intent=_has_anchor_cta_intent(body),
        has_body_cta_intent=_has_body_cta_intent(title=title, body=body),
    )


def _section_word_counts(sections: list[tuple[str, str]]) -> list[CopySectionWordCount]:
    return [
        CopySectionWordCount(
            section_index=index,
            section_title=title,
            word_count=_count_words(f"{title}\n{body}"),
        )
        for index, (title, body) in enumerate(sections, start=1)
    ]


def _words_for_keyword_sections(
    *,
    sections: list[tuple[str, str]],
    keywords: tuple[str, ...],
) -> int:
    total = 0
    for title, body in sections:
        lowered = f"{title}\n{body}".lower()
        if any(keyword in lowered for keyword in keywords):
            total += _count_words(f"{title}\n{body}")
    return total


def _first_cta_word_ratio(
    *,
    markdown: str,
    sections: list[tuple[str, str]],
    cta_signals: list[_CTASectionSignals],
) -> float | None:
    total_words = _count_words(markdown)
    if total_words <= 0:
        return None
    running_words = 0
    for (title, body), section_signals in zip(sections, cta_signals):
        section_words = _count_words(f"{title}\n{body}")
        running_words += section_words
        if section_signals.is_cta_section:
            return running_words / float(total_words)
    return None


def evaluate_copy_page_quality(
    *,
    markdown: str,
    page_contract: CopyPageContract,
) -> CopyPageQualityReport:
    cleaned = markdown.strip()
    sections = _parse_h2_sections(cleaned)
    cta_signals = [_cta_section_signals(title=title, body=body) for title, body in sections]
    section_word_counts = _section_word_counts(sections)
    total_words = _count_words(cleaned)
    cta_count = sum(1 for section_signals in cta_signals if section_signals.is_cta_section)
    first_cta_ratio = _first_cta_word_ratio(
        markdown=cleaned,
        sections=sections,
        cta_signals=cta_signals,
    )
    non_cta_leak_sections = [
        f"{index}:{title}"
        for index, ((title, _body), section_signals) in enumerate(zip(sections, cta_signals), start=1)
        if not section_signals.is_canonical_cta_title
        and section_signals.has_anchor_cta_intent
    ]
    profile = get_copy_quality_thresholds(page_type=page_contract.page_type)

    gates: list[CopyQualityGateResult] = []

    word_floor = int(profile.word_floor)
    word_ceiling = int(profile.word_ceiling)
    gates.append(
        CopyQualityGateResult(
            gate_key="WORD_FLOOR",
            reason_code=f"{page_contract.page_type.upper()}_WORD_FLOOR",
            passed=total_words >= word_floor,
            detail=f"total_words={total_words}, required>={word_floor}",
            remediation=None
            if total_words >= word_floor
            else "Increase section depth and concrete proof/mechanism detail.",
        )
    )
    gates.append(
        CopyQualityGateResult(
            gate_key="WORD_CEILING",
            reason_code=f"{page_contract.page_type.upper()}_WORD_CEILING",
            passed=total_words <= word_ceiling,
            detail=f"total_words={total_words}, required<={word_ceiling}",
            remediation=None
            if total_words <= word_ceiling
            else "Tighten copy while preserving required section-level arguments.",
        )
    )

    min_sections = int(profile.min_sections)
    gates.append(
        CopyQualityGateResult(
            gate_key="SECTION_COUNT",
            reason_code=f"{page_contract.page_type.upper()}_SECTION_COUNT",
            passed=len(sections) >= min_sections,
            detail=f"section_count={len(sections)}, required>={min_sections}",
            remediation=None
            if len(sections) >= min_sections
            else "Add missing required sections from page contract.",
        )
    )

    if page_contract.page_type == "presell_advertorial":
        mechanism_depth = _words_for_keyword_sections(
            sections=sections,
            keywords=("mechanism", "root cause", "trigger"),
        )
        offer_depth = _words_for_keyword_sections(
            sections=sections,
            keywords=("offer", "program", "system", "framework", "cta", "guide", "handbook", "checklist", "protocol"),
        )
        mechanism_floor = int(profile.mechanism_depth_floor or 0)
        offer_floor = int(profile.offer_depth_floor or 0)
        gates.append(
            CopyQualityGateResult(
                gate_key="MECHANISM_DEPTH",
                reason_code="PRESELL_MECHANISM_DEPTH",
                passed=mechanism_depth >= mechanism_floor,
                detail=f"mechanism_words={mechanism_depth}, required>={mechanism_floor}",
                remediation=None
                if mechanism_depth >= mechanism_floor
                else "Expand mechanism section with causal explanation and buyer-relevant detail.",
            )
        )
        gates.append(
            CopyQualityGateResult(
                gate_key="OFFER_DEPTH",
                reason_code="PRESELL_OFFER_DEPTH",
                passed=offer_depth >= offer_floor,
                detail=f"offer_words={offer_depth}, required>={offer_floor}",
                remediation=None
                if offer_depth >= offer_floor
                else "Expand offer bridge/CTA section with concrete what-you-get framing.",
            )
        )
    else:
        proof_depth = _words_for_keyword_sections(
            sections=sections,
            keywords=("proof", "testimonial", "evidence", "case"),
        )
        guarantee_depth = _words_for_keyword_sections(
            sections=sections,
            keywords=("guarantee", "risk reversal", "refund"),
        )
        proof_floor = int(profile.proof_depth_floor or 0)
        guarantee_floor = int(profile.guarantee_depth_floor or 0)
        gates.append(
            CopyQualityGateResult(
                gate_key="PROOF_DEPTH",
                reason_code="SALES_PROOF_DEPTH",
                passed=proof_depth >= proof_floor,
                detail=f"proof_words={proof_depth}, required>={proof_floor}",
                remediation=None
                if proof_depth >= proof_floor
                else "Expand proof sections with stronger evidence and objection resolution.",
            )
        )
        gates.append(
            CopyQualityGateResult(
                gate_key="GUARANTEE_DEPTH",
                reason_code="SALES_GUARANTEE_DEPTH",
                passed=guarantee_depth >= guarantee_floor,
                detail=f"guarantee_words={guarantee_depth}, required>={guarantee_floor}",
                remediation=None
                if guarantee_depth >= guarantee_floor
                else "Expand guarantee section with explicit risk-reversal terms and boundaries.",
            )
        )

    passed = all(gate.passed for gate in gates)
    return CopyPageQualityReport.model_validate(
        {
            "schema_version": SCHEMA_VERSION_V2,
            "page_type": page_contract.page_type,
            "passed": passed,
            "total_words": total_words,
            "section_count": len(sections),
            "cta_count": cta_count,
            "first_cta_word_ratio": first_cta_ratio,
            "section_word_counts": [row.model_dump(mode="python") for row in section_word_counts],
            "gates": [row.model_dump(mode="python") for row in gates],
        }
    )


def require_copy_page_quality(
    *,
    markdown: str,
    page_contract: CopyPageContract,
    page_name: str,
) -> CopyPageQualityReport:
    report = evaluate_copy_page_quality(
        markdown=markdown,
        page_contract=page_contract,
    )
    if report.passed:
        return report

    failures = [gate for gate in report.gates if not gate.passed]
    summary = "; ".join(f"{gate.reason_code}: {gate.detail}" for gate in failures)
    raise StrategyV2DecisionError(
        f"{page_name} failed copy depth/structure gates. {summary}"
    )
