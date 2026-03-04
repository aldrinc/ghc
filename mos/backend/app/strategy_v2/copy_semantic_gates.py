from __future__ import annotations

import re
from typing import Any, Literal, Mapping

from pydantic import Field

from app.strategy_v2.contracts import SCHEMA_VERSION_V2, StrictContract
from app.strategy_v2.copy_contract_spec import CopyPageContract
from app.strategy_v2.copy_input_packet import parse_minimum_delivery_section_index
from app.strategy_v2.errors import StrategyV2DecisionError, StrategyV2SchemaValidationError


_LINK_PATTERN = re.compile(r"\[[^\]]+\]\([^)]+\)")
_LINK_CAPTURE_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
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

_SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hook_or_quote": ("hook", "lead", "quote", "story", "opening"),
    "pain_or_bottleneck": (
        "pain",
        "problem",
        "bottleneck",
        "frustration",
        "struggle",
        "stuck",
        "stress",
        "anxiety",
        "fear",
        "uncertain",
        "confusion",
        "overwhelm",
        "freeze",
    ),
    "failed_solution_logic": ("failed", "tried", "didn't", "did not", "still", "worse", "backfired"),
    "mechanism_signal": ("mechanism", "because", "root cause", "trigger", "why"),
    "proof_signal": ("proof", "evidence", "result", "case", "testimonial", "quote", "review", "feedback", "outcome"),
    "offer_signal": (
        "offer",
        "program",
        "system",
        "framework",
        "guide",
        "handbook",
        "checklist",
        "protocol",
        "toolkit",
        "playbook",
        "reference",
        "method",
        "resource",
        "continue to offer",
    ),
    "value_stack_signal": ("value", "stack", "bonus", "module", "inside", "deliverable", "included"),
    "guarantee_signal": ("guarantee", "risk reversal", "refund", "money-back"),
    "pricing_signal": ("price", "pricing", "payment", "cost", "investment", "one-time", "monthly", "plan", "value"),
    "compliance_signal": (
        "compliance",
        "warning",
        "risk",
        "safety",
        "contraind",
        "avoid",
        "not medical",
        "consult",
        "pharmacist",
        "doctor",
        "ob",
        "pregnan",
        "boundar",
    ),
}

_STOPWORDS = {
    "about",
    "after",
    "again",
    "before",
    "being",
    "between",
    "could",
    "deliver",
    "delivery",
    "detail",
    "details",
    "early",
    "first",
    "from",
    "have",
    "just",
    "many",
    "minimum",
    "must",
    "next",
    "page",
    "promise",
    "question",
    "section",
    "should",
    "specific",
    "that",
    "their",
    "them",
    "there",
    "these",
    "this",
    "timing",
    "what",
    "when",
    "with",
    "your",
}
_PROMISE_META_TERMS = {
    "body",
    "must",
    "contain",
    "include",
    "describe",
    "named",
    "concrete",
    "specific",
    "example",
    "examples",
    "within",
    "section",
    "sections",
    "first",
    "second",
    "third",
    "begin",
    "beginning",
    "resolved",
    "substantially",
    "delivery",
    "timing",
    "minimum",
    "test",
}


class CopySemanticGateResult(StrictContract):
    gate_key: str = Field(min_length=1)
    passed: bool
    detail: str = Field(min_length=1)
    remediation: str | None = None


class CopySectionMatch(StrictContract):
    section_key: str = Field(min_length=1)
    canonical_title: str = Field(min_length=1)
    matched_title: str | None = None
    section_index: int | None = None
    required_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)


class CopyPageSemanticGateReport(StrictContract):
    schema_version: Literal["2.0.0"] = SCHEMA_VERSION_V2
    page_type: Literal["presell_advertorial", "sales_page_warm"]
    passed: bool
    total_sections: int = Field(ge=0)
    markdown_link_count: int = Field(ge=0)
    first_cta_section_index: int | None = None
    guarantee_section_index: int | None = None
    promise_delivery_boundary_section: int = Field(ge=1)
    matched_sections: list[CopySectionMatch] = Field(default_factory=list)
    gate_results: list[CopySemanticGateResult] = Field(default_factory=list)


class PromptChainProvenanceCheck(StrictContract):
    check_key: str = Field(min_length=1)
    passed: bool
    detail: str = Field(min_length=1)


class CopyPromptChainProvenanceReport(StrictContract):
    schema_version: Literal["2.0.0"] = SCHEMA_VERSION_V2
    passed: bool
    checks: list[PromptChainProvenanceCheck] = Field(default_factory=list)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_h2_sections(markdown: str) -> list[tuple[str, str]]:
    lines = markdown.splitlines()
    sections: list[tuple[str, str]] = []

    current_title: str | None = None
    current_body: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_title is not None:
                sections.append((current_title, "\n".join(current_body).strip()))
            current_title = stripped[3:].strip()
            current_body = []
            continue
        if current_title is not None:
            current_body.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_body).strip()))

    return sections


def _has_signal_keywords(*, signal_type: str, text: str) -> bool:
    keywords = _SIGNAL_KEYWORDS.get(signal_type, ())
    lowered = _normalize_text(text)
    return any(keyword in lowered for keyword in keywords)


def _has_cta_link_intent(body: str) -> bool:
    for anchor_text, _url in _LINK_CAPTURE_PATTERN.findall(body):
        if any(pattern.search(anchor_text) for pattern in _CTA_ANCHOR_INTENT_PATTERNS):
            return True
    return False


def _extract_cta_section_indices(sections: list[tuple[str, str]]) -> list[int]:
    indices: list[int] = []
    for index, (title, _body) in enumerate(sections, start=1):
        title_lower = _normalize_text(title)
        if _CTA_CANONICAL_TITLE_RE.search(title_lower):
            indices.append(index)
    return indices


def _extract_guarantee_section_index(sections: list[tuple[str, str]]) -> int | None:
    for index, (title, body) in enumerate(sections, start=1):
        merged = f"{title}\n{body}".lower()
        if "guarantee" in merged or "risk reversal" in merged:
            return index
    return None


def _extract_promise_terms(promise_contract: Mapping[str, Any]) -> list[str]:
    delivery_test = str(promise_contract.get("delivery_test") or "").strip().lower()
    if delivery_test.startswith("the body must "):
        delivery_test = delivery_test[len("the body must ") :]

    specific_promise = str(promise_contract.get("specific_promise") or "").strip().lower()
    loop_question = str(promise_contract.get("loop_question") or "").strip().lower()

    def _tokenize(value: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z]{4,}", value)
        cleaned: list[str] = []
        for token in tokens:
            if token in _STOPWORDS or token in _PROMISE_META_TERMS:
                continue
            if token in cleaned:
                continue
            cleaned.append(token)
        return cleaned

    priority_order = _tokenize(delivery_test)
    for token in _tokenize(specific_promise):
        if token not in priority_order:
            priority_order.append(token)
    for token in _tokenize(loop_question):
        if token not in priority_order:
            priority_order.append(token)
    return priority_order[:12]


def evaluate_copy_page_semantic_gates(
    *,
    markdown: str,
    page_contract: CopyPageContract,
    promise_contract: Mapping[str, Any],
) -> CopyPageSemanticGateReport:
    cleaned = markdown.strip()
    sections = _parse_h2_sections(cleaned)
    section_titles = [title for title, _body in sections]

    gate_results: list[CopySemanticGateResult] = []
    matched_sections: list[CopySectionMatch] = []

    if not cleaned:
        gate_results.append(
            CopySemanticGateResult(
                gate_key="MARKDOWN_NON_EMPTY",
                passed=False,
                detail="Markdown is empty.",
                remediation="Regenerate page markdown from template prompt output.",
            )
        )

    if not sections:
        gate_results.append(
            CopySemanticGateResult(
                gate_key="H2_SECTION_PARSING",
                passed=False,
                detail="No H2 sections (##) were found.",
                remediation="Return markdown with canonical section headings at H2 level.",
            )
        )

    last_index = 0
    required_missing: list[str] = []
    belief_order_ok = True

    for required in page_contract.required_sections:
        matched_index: int | None = None
        matched_title: str | None = None
        missing_signals: list[str] = []

        for index in range(last_index + 1, len(sections) + 1):
            title, body = sections[index - 1]
            normalized_title = _normalize_text(title)
            if not any(marker in normalized_title for marker in required.title_markers):
                continue

            merged_text = f"{title}\n{body}"
            for signal_type in required.required_signals:
                if not _has_signal_keywords(signal_type=signal_type, text=merged_text):
                    missing_signals.append(signal_type)

            matched_index = index
            matched_title = title
            last_index = index
            break

        if matched_index is None:
            required_missing.append(required.canonical_title)
            belief_order_ok = False

        matched_sections.append(
            CopySectionMatch(
                section_key=required.section_key,
                canonical_title=required.canonical_title,
                matched_title=matched_title,
                section_index=matched_index,
                required_signals=list(required.required_signals),
                missing_signals=missing_signals,
            )
        )

    gate_results.append(
        CopySemanticGateResult(
            gate_key="REQUIRED_SECTION_COVERAGE",
            passed=not required_missing,
            detail=(
                "All required section contracts were matched in order."
                if not required_missing
                else f"Missing required sections: {', '.join(required_missing)}"
            ),
            remediation=(
                None
                if not required_missing
                else "Regenerate markdown with all contract sections present and correctly titled."
            ),
        )
    )

    gate_results.append(
        CopySemanticGateResult(
            gate_key="BELIEF_SEQUENCE_ORDER",
            passed=belief_order_ok,
            detail=(
                "Section order matches expected belief progression."
                if belief_order_ok
                else "Required section ordering is broken for belief progression."
            ),
            remediation=(
                None
                if belief_order_ok
                else "Keep required sections in canonical contract order for the page type."
            ),
        )
    )

    missing_signal_rows = [
        f"{row.canonical_title}: {', '.join(row.missing_signals)}"
        for row in matched_sections
        if row.missing_signals
    ]
    gate_results.append(
        CopySemanticGateResult(
            gate_key="REQUIRED_SIGNAL_COVERAGE",
            passed=not missing_signal_rows,
            detail=(
                "All required signal categories are present in matched sections."
                if not missing_signal_rows
                else f"Missing required signals by section: {'; '.join(missing_signal_rows)}"
            ),
            remediation=(
                None
                if not missing_signal_rows
                else "Expand section content to include required mechanism/proof/offer/compliance signals."
            ),
        )
    )

    markdown_link_count = len(_LINK_PATTERN.findall(cleaned))

    cta_section_indices = _extract_cta_section_indices(sections)
    first_cta_section = cta_section_indices[0] if cta_section_indices else None

    guarantee_section_index = _extract_guarantee_section_index(sections)

    total_sections = len(sections)
    minimum_delivery = str(promise_contract.get("minimum_delivery") or "")
    boundary = parse_minimum_delivery_section_index(
        minimum_delivery=minimum_delivery,
        total_sections=total_sections,
    )
    promise_terms = _extract_promise_terms(promise_contract)
    early_text = "\n".join(body for _title, body in sections[:boundary]).lower()
    matched_terms = [
        term for term in promise_terms if re.search(rf"\b{re.escape(term)}\b", early_text)
    ]

    promise_gate_pass = bool(matched_terms)
    gate_results.append(
        CopySemanticGateResult(
            gate_key="PROMISE_DELIVERY_TIMING",
            passed=promise_gate_pass,
            detail=(
                f"Boundary section={boundary}; matched terms={matched_terms[:5]}"
                if promise_gate_pass
                else (
                    f"No promise terms delivered by section boundary {boundary}. "
                    f"Terms considered: {promise_terms[:6]}"
                )
            ),
            remediation=(
                None
                if promise_gate_pass
                else "Deliver specific promise language earlier to satisfy minimum_delivery timing."
            ),
        )
    )

    passed = all(row.passed for row in gate_results)
    return CopyPageSemanticGateReport.model_validate(
        {
            "schema_version": SCHEMA_VERSION_V2,
            "page_type": page_contract.page_type,
            "passed": passed,
            "total_sections": total_sections,
            "markdown_link_count": markdown_link_count,
            "first_cta_section_index": first_cta_section,
            "guarantee_section_index": guarantee_section_index,
            "promise_delivery_boundary_section": boundary,
            "matched_sections": [row.model_dump(mode="python") for row in matched_sections],
            "gate_results": [row.model_dump(mode="python") for row in gate_results],
        }
    )


def require_copy_page_semantic_quality(
    *,
    markdown: str,
    page_contract: CopyPageContract,
    promise_contract: Mapping[str, Any],
    page_name: str,
) -> CopyPageSemanticGateReport:
    report = evaluate_copy_page_semantic_gates(
        markdown=markdown,
        page_contract=page_contract,
        promise_contract=promise_contract,
    )
    if report.passed:
        return report

    failed = [row for row in report.gate_results if not row.passed]
    summary = "; ".join(f"{row.gate_key}: {row.detail}" for row in failed)
    raise StrategyV2DecisionError(
        f"{page_name} failed semantic copy gates. {summary}"
    )


def validate_prompt_chain_provenance(
    *,
    prompt_chain: Mapping[str, Any],
) -> CopyPromptChainProvenanceReport:
    checks: list[PromptChainProvenanceCheck] = []
    required_steps = (
        ("headline_prompt_provenance", "headline_prompt_raw_output"),
        ("promise_prompt_provenance", "promise_prompt_raw_output"),
        ("advertorial_prompt_provenance", "advertorial_prompt_raw_output"),
        ("sales_prompt_provenance", "sales_prompt_raw_output"),
    )
    required_provenance_fields = (
        "prompt_path",
        "prompt_sha256",
        "model_name",
        "input_contract_version",
        "output_contract_version",
    )

    for provenance_key, raw_key in required_steps:
        provenance_payload = prompt_chain.get(provenance_key)
        if not isinstance(provenance_payload, Mapping):
            checks.append(
                PromptChainProvenanceCheck(
                    check_key=provenance_key,
                    passed=False,
                    detail="Missing provenance object.",
                )
            )
        else:
            missing_fields = [
                field_name
                for field_name in required_provenance_fields
                if not isinstance(provenance_payload.get(field_name), str)
                or not str(provenance_payload.get(field_name) or "").strip()
            ]
            checks.append(
                PromptChainProvenanceCheck(
                    check_key=provenance_key,
                    passed=not missing_fields,
                    detail=(
                        "All required provenance fields are present."
                        if not missing_fields
                        else f"Missing fields: {', '.join(missing_fields)}"
                    ),
                )
            )

        raw_output = prompt_chain.get(raw_key)
        checks.append(
            PromptChainProvenanceCheck(
                check_key=raw_key,
                passed=isinstance(raw_output, str) and bool(raw_output.strip()),
                detail=(
                    "Raw output is present."
                    if isinstance(raw_output, str) and raw_output.strip()
                    else "Missing or empty raw prompt output."
                ),
            )
        )

    passed = all(check.passed for check in checks)
    return CopyPromptChainProvenanceReport.model_validate(
        {
            "schema_version": SCHEMA_VERSION_V2,
            "passed": passed,
            "checks": [check.model_dump(mode="python") for check in checks],
        }
    )


def require_prompt_chain_provenance(
    *,
    prompt_chain: Mapping[str, Any],
) -> CopyPromptChainProvenanceReport:
    report = validate_prompt_chain_provenance(prompt_chain=prompt_chain)
    if report.passed:
        return report

    failures = "; ".join(
        f"{check.check_key}: {check.detail}" for check in report.checks if not check.passed
    )
    raise StrategyV2SchemaValidationError(
        f"Copy prompt-chain provenance validation failed: {failures}"
    )
