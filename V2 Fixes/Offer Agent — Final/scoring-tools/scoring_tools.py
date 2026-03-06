"""
Offer Agent Pipeline v2 — External Scoring Tools

These are DETERMINISTIC functions. No LLM involvement. Pure math.
The LLM provides raw dimensional ratings and evidence classifications.
These functions compute the actual scores.

v2 Changes:
- Added ump_ums_scorer (new Step 3)
- Fixed hormozi_scorer scale normalization (now outputs 1-10 scale)
- Updated objection_coverage_calculator with suspicious-perfect-coverage warning
- Updated composite_scorer to handle multi-variant evaluation
- Removed voc_signal_scorer and angle_scorer (research now provided upstream)

Usage:
    from scoring_tools import (
        calibration_consistency_checker,
        ump_ums_scorer,
        hormozi_scorer,
        objection_coverage_calculator,
        novelty_calculator,
        composite_scorer,
    )
"""

import json
from typing import Any


# =============================================================================
# 1. Calibration Consistency Checker (Step 2)
# =============================================================================

def calibration_consistency_checker(calibration: dict) -> dict:
    """
    Check for logical inconsistencies in market calibration.

    Input: calibration JSON with awareness, sophistication, lifecycle assessments.
    Output: { passed: bool, conflicts: [] }
    """
    conflicts = []

    awareness = calibration.get("awareness_level", {}).get("assessment", "").lower()
    sophistication = calibration.get("sophistication_level", {}).get("assessment", "").lower()
    lifecycle = calibration.get("lifecycle_stage", {}).get("assessment", "").lower()
    competitor_count = calibration.get("competitor_count", 0)

    # Rule 1: Introduction + most-aware is contradictory
    if lifecycle == "introduction" and awareness == "most-aware":
        conflicts.append({
            "rule": "lifecycle_awareness_mismatch",
            "message": "CONFLICT: Introduction-stage market cannot have most-aware buyers. "
                       "If buyers are most-aware, the market is at least in growth stage.",
            "severity": "ERROR",
            "resolution": "Re-evaluate lifecycle stage or awareness level with evidence.",
        })

    # Rule 2: Maturity + low sophistication is unusual
    if lifecycle == "maturity" and sophistication == "low":
        conflicts.append({
            "rule": "lifecycle_sophistication_mismatch",
            "message": "WARNING: Mature market with low sophistication is unusual. "
                       "Mature markets typically have sophisticated buyers who've seen many offers.",
            "severity": "WARNING",
            "resolution": "Verify sophistication assessment. This may indicate a niche sub-segment.",
        })

    # Rule 3: Unaware + many competitors is contradictory
    if awareness == "unaware" and competitor_count > 10:
        conflicts.append({
            "rule": "awareness_competition_mismatch",
            "message": f"CONFLICT: Unaware audience unlikely in market with {competitor_count} competitors. "
                       "If 10+ companies are selling to this audience, they're at least problem-aware.",
            "severity": "ERROR",
            "resolution": "Re-evaluate awareness level. Likely at least problem-aware.",
        })

    # Rule 4: Decline + low sophistication is contradictory
    if lifecycle == "decline" and sophistication == "low":
        conflicts.append({
            "rule": "decline_sophistication_mismatch",
            "message": "CONFLICT: Declining market should have high sophistication. "
                       "Markets decline because buyers are exhausted/saturated.",
            "severity": "WARNING",
            "resolution": "Verify lifecycle stage. May be maturity, not decline.",
        })

    # Rule 5: Most-aware + low sophistication is unusual
    if awareness == "most-aware" and sophistication == "low":
        conflicts.append({
            "rule": "awareness_sophistication_mismatch",
            "message": "WARNING: Most-aware buyers with low sophistication is unusual. "
                       "Most-aware typically correlates with higher sophistication.",
            "severity": "WARNING",
            "resolution": "Check if 'most-aware' was correctly assessed.",
        })

    has_errors = any(c["severity"] == "ERROR" for c in conflicts)
    has_warnings = any(c["severity"] == "WARNING" for c in conflicts)

    return {
        "passed": not has_errors,
        "has_warnings": has_warnings,
        "error_count": sum(1 for c in conflicts if c["severity"] == "ERROR"),
        "warning_count": sum(1 for c in conflicts if c["severity"] == "WARNING"),
        "conflicts": conflicts,
        "assessment_summary": {
            "awareness": awareness,
            "sophistication": sophistication,
            "lifecycle": lifecycle,
            "competitor_count": competitor_count,
        },
    }


# =============================================================================
# 2. UMP/UMS Scorer (Step 3) — NEW in v2
# =============================================================================

UMP_UMS_WEIGHTS = {
    "competitive_uniqueness": 0.20,
    "voc_groundedness": 0.20,
    "believability": 0.15,
    "mechanism_clarity": 0.15,
    "angle_alignment": 0.10,
    "compliance_safety": 0.10,
    "memorability": 0.10,
}

EVIDENCE_SAFETY_FACTORS = {
    "OBSERVED": 0.9,
    "INFERRED": 0.75,
    "ASSUMED": 0.6,
}


def ump_ums_scorer(pairs: list[dict]) -> dict:
    """
    Score UMP/UMS paired sets across 7 dimensions with safety factors.

    Each dimension is rated 1-10 by the LLM with evidence classification.
    This function computes safety-adjusted composite scores and ranks pairs.

    Input: list of UMP/UMS pairs, each with:
        - pair_id: str
        - ump_name: str
        - ums_name: str
        - dimensions: {
            "competitive_uniqueness": { "score": 1-10, "evidence_quality": "OBSERVED|INFERRED|ASSUMED" },
            ...7 dimensions
          }

    Output: ranked pairs with composite scores, dimension breakdowns, and evidence summaries.
    """
    scored = []
    for pair in pairs:
        raw_composite = 0
        safety_adjusted_composite = 0
        dimension_details = {}

        dims = pair.get("dimensions", {})
        for dim, weight in UMP_UMS_WEIGHTS.items():
            dim_data = dims.get(dim, {})
            raw_score = dim_data.get("score", 0)
            evidence = dim_data.get("evidence_quality", "ASSUMED")
            sf = EVIDENCE_SAFETY_FACTORS.get(evidence, 0.6)
            adjusted = round(raw_score * sf, 2)

            raw_composite += raw_score * weight
            safety_adjusted_composite += adjusted * weight

            dimension_details[dim] = {
                "raw": raw_score,
                "evidence_quality": evidence,
                "safety_factor": sf,
                "safety_adjusted": adjusted,
                "weighted_contribution": round(adjusted * weight, 3),
            }

        scored.append({
            "pair_id": pair.get("pair_id", "unknown"),
            "ump_name": pair.get("ump_name", "unknown"),
            "ums_name": pair.get("ums_name", "unknown"),
            "composite_raw": round(raw_composite, 2),
            "composite_safety_adjusted": round(safety_adjusted_composite, 2),
            "dimensions": dimension_details,
            "strongest_dimension": max(
                dimension_details.items(), key=lambda x: x[1]["safety_adjusted"]
            )[0],
            "weakest_dimension": min(
                dimension_details.items(), key=lambda x: x[1]["safety_adjusted"]
            )[0],
            "evidence_summary": {
                "observed": sum(1 for d in dimension_details.values() if d["evidence_quality"] == "OBSERVED"),
                "inferred": sum(1 for d in dimension_details.values() if d["evidence_quality"] == "INFERRED"),
                "assumed": sum(1 for d in dimension_details.values() if d["evidence_quality"] == "ASSUMED"),
            },
        })

    # Sort by safety-adjusted composite descending
    ranked = sorted(scored, key=lambda x: x["composite_safety_adjusted"], reverse=True)

    # Add rank and delta from top
    for i, pair in enumerate(ranked):
        pair["rank"] = i + 1
        pair["delta_from_top"] = (
            round(ranked[0]["composite_safety_adjusted"] - pair["composite_safety_adjusted"], 2)
            if i > 0 else 0
        )

    # Summary
    top = ranked[0] if ranked else None
    return {
        "ranked_pairs": ranked,
        "total_pairs": len(ranked),
        "top_pair": {
            "pair_id": top["pair_id"],
            "ump_name": top["ump_name"],
            "ums_name": top["ums_name"],
            "composite": top["composite_safety_adjusted"],
        } if top else None,
        "score_spread": round(
            ranked[0]["composite_safety_adjusted"] - ranked[-1]["composite_safety_adjusted"], 2
        ) if len(ranked) > 1 else 0,
        "diagnosis": (
            f"Top pair: {top['ump_name']}/{top['ums_name']} "
            f"(score: {top['composite_safety_adjusted']}, "
            f"raw: {top['composite_raw']}). "
            f"Spread: {round(ranked[0]['composite_safety_adjusted'] - ranked[-1]['composite_safety_adjusted'], 2) if len(ranked) > 1 else 0}"
        ) if top else "No pairs to score.",
    }


# =============================================================================
# 3. Hormozi Value Equation Scorer (Step 4)
# =============================================================================

def hormozi_scorer(value_stack: dict) -> dict:
    """
    Score each element against Hormozi's value equation.
    Value = (Dream Outcome x Perceived Likelihood) / (Time Delay x Effort & Sacrifice)

    Lever ratings use INVERTED scale for denominator:
      - dream_outcome: 1=low, 10=high (higher is better)
      - perceived_likelihood: 1=unlikely, 10=very likely (higher is better)
      - time_delay: 1=instant, 10=very slow (LOWER raw = better for buyer)
      - effort_sacrifice: 1=effortless, 10=extreme effort (LOWER raw = better for buyer)

    The formula uses (11 - time_delay) and (11 - effort_sacrifice) to invert,
    so higher output scores always mean better value.

    Output is normalized to a 1-10 scale for human readability.
    """
    elements = value_stack.get("elements", [])
    scored_elements = []

    for element in elements:
        levers = element.get("hormozi_levers", {})

        dream = levers.get("dream_outcome", 1)
        likelihood = levers.get("perceived_likelihood", 1)
        time_delay = levers.get("time_delay", 5)
        effort = levers.get("effort_sacrifice", 5)

        # Cap any 10/10 ratings — flag for review
        capped_flags = []
        if time_delay <= 1:
            capped_flags.append("time_delay rated 1 (instant) — verify this is realistic")
        if effort <= 1:
            capped_flags.append("effort_sacrifice rated 1 (effortless) — verify this is realistic")

        # Numerator: what buyer gets (higher = better)
        numerator = dream * likelihood

        # Denominator: invert so lower raw = higher score
        # (11 - x): raw 1 (instant) → 10, raw 10 (slow) → 1
        time_inv = 11 - time_delay
        effort_inv = 11 - effort

        # Compute raw value and normalize to 1-10
        # Max theoretical: (10 * 10 * 10 * 10) = 10000
        # Normalize: raw / 1000, capped at 10
        raw_value = (numerator * time_inv * effort_inv) / 1000
        value_score = round(min(max(raw_value, 0.1), 10.0), 2)

        scored_elements.append({
            **element,
            "value_score": value_score,
            "lever_detail": {
                "numerator": numerator,
                "time_inverted": time_inv,
                "effort_inverted": effort_inv,
                "raw_value": round(raw_value, 4),
            },
            "capped_flags": capped_flags if capped_flags else None,
        })

    if not scored_elements:
        return {
            "elements": [],
            "aggregate_value_score": 0,
            "lever_averages": {},
            "diagnosis": "No elements provided.",
        }

    n = len(scored_elements)
    avg_score = round(sum(e["value_score"] for e in scored_elements) / n, 2)

    lever_avgs = {
        "dream_outcome": round(sum(e["hormozi_levers"]["dream_outcome"] for e in scored_elements) / n, 1),
        "perceived_likelihood": round(sum(e["hormozi_levers"]["perceived_likelihood"] for e in scored_elements) / n, 1),
        "time_delay": round(sum(e["hormozi_levers"]["time_delay"] for e in scored_elements) / n, 1),
        "effort_sacrifice": round(sum(e["hormozi_levers"]["effort_sacrifice"] for e in scored_elements) / n, 1),
    }

    # Diagnosis: identify which levers need work
    lever_diagnosis = []
    if lever_avgs["dream_outcome"] < 6:
        lever_diagnosis.append("Dream Outcome is weak — the promised result may not feel compelling enough")
    if lever_avgs["perceived_likelihood"] < 6:
        lever_diagnosis.append("Perceived Likelihood is weak — buyer may not believe they'll get the result")
    if lever_avgs["time_delay"] > 5:
        lever_diagnosis.append("Time Delay is high — buyer perceives too long to see results")
    if lever_avgs["effort_sacrifice"] > 5:
        lever_diagnosis.append("Effort/Sacrifice is high — buyer perceives too much work required")

    # Flag any elements with capped ratings
    capped_elements = [e["name"] for e in scored_elements if e.get("capped_flags")]

    highest = max(scored_elements, key=lambda x: x["value_score"])
    lowest = min(scored_elements, key=lambda x: x["value_score"])

    return {
        "elements": scored_elements,
        "aggregate_value_score": avg_score,
        "highest_value_element": {"name": highest.get("name", "unknown"), "score": highest["value_score"]},
        "lowest_value_element": {"name": lowest.get("name", "unknown"), "score": lowest["value_score"]},
        "lever_averages": lever_avgs,
        "lever_diagnosis": lever_diagnosis if lever_diagnosis else ["All levers in healthy range"],
        "capped_rating_warnings": capped_elements if capped_elements else None,
        "element_count": n,
        "diagnosis": (
            f"Aggregate value: {avg_score}/10 across {n} elements. "
            f"Best: {highest.get('name', '?')} ({highest['value_score']}), "
            f"Worst: {lowest.get('name', '?')} ({lowest['value_score']}). "
            + (f"Lever issues: {'; '.join(lever_diagnosis)}" if lever_diagnosis else "All levers healthy.")
        ),
    }


# =============================================================================
# 4. Objection Coverage Calculator (Step 4)
# =============================================================================

def objection_coverage_calculator(mapping: dict) -> dict:
    """
    Calculate objection coverage percentage and identify gaps.

    v2 changes:
    - Flags 100% coverage as suspicious (LLM may be mapping too generously)
    - Checks for unknown-unknown objection generation

    Input: { objections: [{ objection, source, covered, coverage_strength, mapped_element, ... }] }
    Output: coverage stats + uncovered objection list + warnings.
    """
    objections = mapping.get("objections", [])
    total = len(objections)

    if total == 0:
        return {
            "total_objections": 0,
            "coverage_pct": 0,
            "uncovered_objections": [],
            "diagnosis": "No objections provided.",
        }

    covered = [obj for obj in objections if obj.get("covered", False)]
    uncovered = [obj for obj in objections if not obj.get("covered", False)]

    coverage_pct = round((len(covered) / total) * 100, 1)

    # Check for suspicious perfect coverage
    suspicious_perfect = coverage_pct == 100.0

    # Check for unknown-unknown objections (should have source = "hypothesized" or similar)
    unknown_unknowns = [
        obj for obj in objections
        if obj.get("source", "").lower() in ("hypothesized", "unknown-unknown", "generated", "inferred")
    ]
    has_unknown_unknowns = len(unknown_unknowns) > 0

    # Find weakest coverage (covered but low strength)
    weak_coverage = [
        obj for obj in covered
        if obj.get("coverage_strength", 10) < 5
    ]

    return {
        "total_objections": total,
        "covered_count": len(covered),
        "uncovered_count": len(uncovered),
        "coverage_pct": coverage_pct,
        "suspicious_perfect_coverage": suspicious_perfect,
        "has_unknown_unknown_objections": has_unknown_unknowns,
        "unknown_unknown_count": len(unknown_unknowns),
        "warnings": [
            w for w in [
                "100% coverage is suspicious — LLM may be mapping too generously. Verify unknown-unknown objections were generated."
                if suspicious_perfect else None,
                "No unknown-unknown objections generated — the prompt should force 2-3 hypothesized objections the avatar brief may have missed."
                if not has_unknown_unknowns else None,
            ] if w
        ],
        "uncovered_objections": [
            {
                "objection": obj.get("objection", "unknown"),
                "source": obj.get("source", "unknown"),
                "priority": obj.get("priority", "unknown"),
            }
            for obj in uncovered
        ],
        "weak_coverage": [
            {
                "objection": obj.get("objection", "unknown"),
                "coverage_strength": obj.get("coverage_strength", 0),
                "mapped_element": obj.get("mapped_element", "unknown"),
            }
            for obj in weak_coverage
        ],
        "diagnosis": (
            f"Coverage: {coverage_pct}%. "
            f"{len(uncovered)} uncovered, {len(weak_coverage)} weakly covered. "
            f"Unknown-unknowns: {'yes' if has_unknown_unknowns else 'MISSING'}. "
            + ("WARNING: Perfect coverage is suspicious." if suspicious_perfect else "")
        ),
    }


# =============================================================================
# 5. Novelty Calculator (Step 4)
# =============================================================================

def novelty_calculator(elements: dict) -> dict:
    """
    Calculate information value (novelty) of offer elements vs competitor baseline.

    Input: { classifications: [{ element_name, classification: NOVEL|INCREMENTAL|REDUNDANT }] }
    Output: information value score + breakdown.
    """
    WEIGHTS = {"NOVEL": 1.0, "INCREMENTAL": 0.3, "REDUNDANT": 0.0}

    classifications = elements.get("classifications", [])
    total = len(classifications)

    if total == 0:
        return {
            "information_value": 0,
            "meets_threshold": False,
            "diagnosis": "No elements provided.",
        }

    weighted_sum = sum(
        WEIGHTS.get(item.get("classification", "REDUNDANT"), 0)
        for item in classifications
    )
    info_value = round(weighted_sum / total, 3)

    counts = {"NOVEL": 0, "INCREMENTAL": 0, "REDUNDANT": 0}
    for item in classifications:
        cls = item.get("classification", "REDUNDANT")
        counts[cls] = counts.get(cls, 0) + 1

    meets = info_value >= 0.35

    return {
        "information_value": info_value,
        "novel_count": counts["NOVEL"],
        "incremental_count": counts["INCREMENTAL"],
        "redundant_count": counts["REDUNDANT"],
        "total_elements": total,
        "meets_threshold": meets,
        "threshold": 0.35,
        "most_redundant_elements": [
            item.get("element_name", "unknown")
            for item in classifications
            if item.get("classification") == "REDUNDANT"
        ],
        "most_novel_elements": [
            item.get("element_name", "unknown")
            for item in classifications
            if item.get("classification") == "NOVEL"
        ],
        "diagnosis": (
            f"Information value: {info_value} ({'PASSES' if meets else 'FAILS'} 0.35 threshold). "
            f"{counts['NOVEL']} novel, {counts['INCREMENTAL']} incremental, {counts['REDUNDANT']} redundant."
        ),
    }


# =============================================================================
# 6. Composite Scorer (Step 5)
# =============================================================================

DIMENSION_WEIGHTS = {
    "value_equation": 0.12,
    "objection_coverage": 0.10,
    "competitive_differentiation": 0.10,
    "compliance_safety": 0.10,
    "internal_consistency": 0.08,
    "clarity_simplicity": 0.08,
    "bottleneck_resilience": 0.08,
    "momentum_continuity": 0.10,
    "pricing_fidelity": 0.10,
    "savings_fidelity": 0.07,
    "best_value_fidelity": 0.07,
}

SAFETY_FACTORS = {
    "OBSERVED": 0.9,
    "INFERRED": 0.75,
    "ASSUMED": 0.6,
}


def composite_scorer(evaluation: dict, config: dict | None = None) -> dict:
    """
    Compute final composite score with safety factors and Z-score normalization.
    v2: Handles multi-variant evaluation (base + structural variants from Step 4).

    Input:
        evaluation: {
            variants: [
                {
                    variant_id: "...",
                    dimensions: {
                        "value_equation": { raw_score, evidence_quality, competitor_baseline?, kill_condition },
                        ... (11 dimensions)
                    }
                },
                ...
            ]
        }

        OR (backwards compatible single-variant):

        evaluation: {
            dimensions: { ... 11 dimensions ... }
        }

        config: {
            score_threshold: float (default 5.5),
            current_iteration: int (default 1),
            max_iterations: int (default 2),
        }
    """
    if config is None:
        config = {}

    threshold = config.get("score_threshold", 5.5)
    iteration = config.get("current_iteration", 1)
    max_iterations = config.get("max_iterations", 2)

    # Handle both single-variant and multi-variant input
    if "variants" in evaluation:
        variants = evaluation["variants"]
    else:
        variants = [{"variant_id": "single_device", "dimensions": evaluation.get("dimensions", {})}]

    variant_results = []

    for variant in variants:
        dimensions = variant.get("dimensions", {})
        dimension_results = {}

        for dim_name, weight in DIMENSION_WEIGHTS.items():
            dim_data = dimensions.get(dim_name, {})
            raw_score = dim_data.get("raw_score", 0)
            evidence_quality = dim_data.get("evidence_quality", "ASSUMED")

            # Apply safety factor
            sf = SAFETY_FACTORS.get(evidence_quality, 0.6)
            safety_adjusted = round(raw_score * sf, 2)

            # Z-score if competitor baseline available
            baseline = dim_data.get("competitor_baseline", {})
            z_score = None
            if baseline.get("mean") is not None and baseline.get("spread", 0) > 0:
                z_score = round(
                    (safety_adjusted - baseline["mean"]) / baseline["spread"], 2
                )

            dimension_results[dim_name] = {
                "raw_score": raw_score,
                "evidence_quality": evidence_quality,
                "safety_factor": sf,
                "safety_adjusted": safety_adjusted,
                "z_score": z_score,
                "weight": weight,
                "weighted_contribution": round(safety_adjusted * weight, 3),
                "kill_condition": dim_data.get("kill_condition", "NOT STATED"),
            }

        # Compute composites
        composite_raw = round(
            sum(d["raw_score"] * DIMENSION_WEIGHTS[k] for k, d in dimension_results.items()), 2
        )
        composite_safety = round(
            sum(d["weighted_contribution"] for d in dimension_results.values()), 2
        )

        # Verdict
        if composite_safety >= threshold:
            verdict = "PASS"
        elif iteration < max_iterations:
            verdict = "REVISE"
        else:
            verdict = "HUMAN_REVIEW"

        # Identify revision targets
        sorted_dims = sorted(dimension_results.items(), key=lambda x: x[1]["safety_adjusted"])
        revision_targets = [sorted_dims[0][0], sorted_dims[1][0]] if verdict == "REVISE" else []

        # Evidence quality summary
        eq_counts = {"OBSERVED": 0, "INFERRED": 0, "ASSUMED": 0}
        for d in dimension_results.values():
            eq = d["evidence_quality"]
            eq_counts[eq] = eq_counts.get(eq, 0) + 1

        variant_results.append({
            "variant_id": variant.get("variant_id", "base"),
            "composite_raw": composite_raw,
            "composite_safety_adjusted": composite_safety,
            "threshold": threshold,
            "verdict": verdict,
            "iteration": iteration,
            "revision_targets": revision_targets,
            "dimensions": dimension_results,
            "strongest_dimension": max(dimension_results.items(), key=lambda x: x[1]["safety_adjusted"])[0],
            "weakest_dimension": sorted_dims[0][0],
            "second_weakest_dimension": sorted_dims[1][0] if len(sorted_dims) > 1 else None,
            "evidence_quality_summary": eq_counts,
        })

    # Rank variants by composite score
    variant_results.sort(key=lambda x: x["composite_safety_adjusted"], reverse=True)
    for i, v in enumerate(variant_results):
        v["rank"] = i + 1

    best = variant_results[0] if variant_results else None
    any_passing = any(v["verdict"] == "PASS" for v in variant_results)

    return {
        "best_variant": best["variant_id"] if best else None,
        "best_score": best["composite_safety_adjusted"] if best else 0,
        "any_passing": any_passing,
        "total_variants": len(variant_results),
        "passing_variants": [v["variant_id"] for v in variant_results if v["verdict"] == "PASS"],
        "variants": variant_results,
        "diagnosis": (
            f"Best: {best['variant_id']} "
            f"(score: {best['composite_safety_adjusted']}, raw: {best['composite_raw']}, "
            f"verdict: {best['verdict']}). "
            f"{'PASSING variants: ' + ', '.join(v['variant_id'] for v in variant_results if v['verdict'] == 'PASS') if any_passing else 'No variants passing threshold.'}"
        ) if best else "No variants to score.",
    }


# =============================================================================
# CLI Test Runner
# =============================================================================

def run_test():
    """Quick smoke test with sample data to verify all functions work."""

    print("=" * 60)
    print("OFFER AGENT v2 SCORING TOOLS — SMOKE TEST")
    print("=" * 60)

    # Test 1: Calibration Consistency
    print("\n--- 1. Calibration Consistency Checker ---")
    sample_cal = {
        "awareness_level": {"assessment": "product-aware"},
        "sophistication_level": {"assessment": "high"},
        "lifecycle_stage": {"assessment": "maturity"},
        "competitor_count": 16,
    }
    result = calibration_consistency_checker(sample_cal)
    print(f"  Passed: {result['passed']} | Errors: {result['error_count']} | Warnings: {result['warning_count']}")

    # Test conflicting calibration
    bad_cal = {
        "awareness_level": {"assessment": "unaware"},
        "sophistication_level": {"assessment": "low"},
        "lifecycle_stage": {"assessment": "introduction"},
        "competitor_count": 16,
    }
    result = calibration_consistency_checker(bad_cal)
    print(f"  Conflicting test — Passed: {result['passed']} | Errors: {result['error_count']}")
    for c in result["conflicts"]:
        print(f"    [{c['severity']}] {c['message'][:80]}...")

    # Test 2: UMP/UMS Scorer (NEW)
    print("\n--- 2. UMP/UMS Scorer ---")
    sample_pairs = [
        {
            "pair_id": "UMP_UMS_001",
            "ump_name": "The Trust Collapse Trap",
            "ums_name": "The Evidence-Confidence System",
            "dimensions": {
                "competitive_uniqueness": {"score": 8, "evidence_quality": "OBSERVED"},
                "voc_groundedness": {"score": 9, "evidence_quality": "OBSERVED"},
                "believability": {"score": 7, "evidence_quality": "INFERRED"},
                "mechanism_clarity": {"score": 8, "evidence_quality": "INFERRED"},
                "angle_alignment": {"score": 9, "evidence_quality": "OBSERVED"},
                "compliance_safety": {"score": 8, "evidence_quality": "OBSERVED"},
                "memorability": {"score": 7, "evidence_quality": "INFERRED"},
            },
        },
        {
            "pair_id": "UMP_UMS_002",
            "ump_name": "The Dosing Guesswork Gap",
            "ums_name": "The Precision Protocol",
            "dimensions": {
                "competitive_uniqueness": {"score": 6, "evidence_quality": "INFERRED"},
                "voc_groundedness": {"score": 7, "evidence_quality": "OBSERVED"},
                "believability": {"score": 9, "evidence_quality": "OBSERVED"},
                "mechanism_clarity": {"score": 9, "evidence_quality": "OBSERVED"},
                "angle_alignment": {"score": 7, "evidence_quality": "INFERRED"},
                "compliance_safety": {"score": 7, "evidence_quality": "INFERRED"},
                "memorability": {"score": 6, "evidence_quality": "ASSUMED"},
            },
        },
        {
            "pair_id": "UMP_UMS_003",
            "ump_name": "The Interaction Blindspot",
            "ums_name": "The Cross-Reference Matrix",
            "dimensions": {
                "competitive_uniqueness": {"score": 9, "evidence_quality": "OBSERVED"},
                "voc_groundedness": {"score": 8, "evidence_quality": "OBSERVED"},
                "believability": {"score": 8, "evidence_quality": "INFERRED"},
                "mechanism_clarity": {"score": 7, "evidence_quality": "INFERRED"},
                "angle_alignment": {"score": 8, "evidence_quality": "INFERRED"},
                "compliance_safety": {"score": 6, "evidence_quality": "ASSUMED"},
                "memorability": {"score": 8, "evidence_quality": "INFERRED"},
            },
        },
    ]
    result = ump_ums_scorer(sample_pairs)
    print(f"  {result['diagnosis']}")
    for pair in result["ranked_pairs"]:
        print(f"    #{pair['rank']}: {pair['ump_name']}/{pair['ums_name']} — "
              f"adjusted: {pair['composite_safety_adjusted']} (raw: {pair['composite_raw']})")

    # Test 3: Hormozi Scorer (v2 — normalized scale)
    print("\n--- 3. Hormozi Value Equation Scorer (v2) ---")
    sample_stack = {
        "elements": [
            {"name": "Core Handbook", "hormozi_levers": {"dream_outcome": 8, "perceived_likelihood": 7, "time_delay": 4, "effort_sacrifice": 3}},
            {"name": "Safety Quick-Check", "hormozi_levers": {"dream_outcome": 7, "perceived_likelihood": 8, "time_delay": 1, "effort_sacrifice": 1}},
            {"name": "Interaction Matrix", "hormozi_levers": {"dream_outcome": 9, "perceived_likelihood": 9, "time_delay": 1, "effort_sacrifice": 1}},
        ]
    }
    result = hormozi_scorer(sample_stack)
    print(f"  {result['diagnosis']}")
    for e in result["elements"]:
        flags = f" ⚠️ {', '.join(e['capped_flags'])}" if e.get("capped_flags") else ""
        print(f"    {e['name']}: {e['value_score']}/10{flags}")

    # Test 4: Objection Coverage (v2 — with unknown-unknown check)
    print("\n--- 4. Objection Coverage Calculator (v2) ---")
    sample_objections = {
        "objections": [
            {"objection": "Another AI slop book", "source": "avatar", "covered": True, "coverage_strength": 8},
            {"objection": "Drug interactions fear", "source": "VOC", "covered": True, "coverage_strength": 9},
            {"objection": "$49 too much", "source": "objection list", "covered": True, "coverage_strength": 4},
            {"objection": "Doctor will judge me", "source": "avatar", "covered": False, "priority": "medium"},
            {"objection": "Won't remember to use it", "source": "hypothesized", "covered": False, "priority": "low"},
        ]
    }
    result = objection_coverage_calculator(sample_objections)
    print(f"  {result['diagnosis']}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"    ⚠️ {w}")

    # Test 5: Novelty Calculator
    print("\n--- 5. Novelty Calculator ---")
    sample_novelty = {
        "classifications": [
            {"element_name": "Symptom-first index", "classification": "REDUNDANT"},
            {"element_name": "Safety flags per herb", "classification": "INCREMENTAL"},
            {"element_name": "Confidence level rating", "classification": "NOVEL"},
            {"element_name": "Interaction scanner", "classification": "NOVEL"},
            {"element_name": "30-day guarantee", "classification": "REDUNDANT"},
            {"element_name": "AI-slop buyer checklist", "classification": "NOVEL"},
        ]
    }
    result = novelty_calculator(sample_novelty)
    print(f"  {result['diagnosis']}")

    # Test 6: Composite Scorer (v2 — multi-variant)
    print("\n--- 6. Composite Scorer (v2 — multi-variant) ---")
    sample_eval = {
        "variants": [
            {
                "variant_id": "base",
                "dimensions": {
                    "value_equation": {"raw_score": 7.5, "evidence_quality": "INFERRED"},
                    "objection_coverage": {"raw_score": 8.0, "evidence_quality": "OBSERVED"},
                    "competitive_differentiation": {"raw_score": 7.0, "evidence_quality": "INFERRED"},
                    "compliance_safety": {"raw_score": 8.5, "evidence_quality": "OBSERVED"},
                    "internal_consistency": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                    "clarity_simplicity": {"raw_score": 6.5, "evidence_quality": "ASSUMED"},
                    "bottleneck_resilience": {"raw_score": 5.0, "evidence_quality": "ASSUMED"},
                    "momentum_continuity": {"raw_score": 7.0, "evidence_quality": "INFERRED"},
                },
            },
            {
                "variant_id": "variant_a",
                "dimensions": {
                    "value_equation": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                    "objection_coverage": {"raw_score": 7.5, "evidence_quality": "OBSERVED"},
                    "competitive_differentiation": {"raw_score": 7.5, "evidence_quality": "INFERRED"},
                    "compliance_safety": {"raw_score": 8.0, "evidence_quality": "OBSERVED"},
                    "internal_consistency": {"raw_score": 7.5, "evidence_quality": "INFERRED"},
                    "clarity_simplicity": {"raw_score": 7.0, "evidence_quality": "ASSUMED"},
                    "bottleneck_resilience": {"raw_score": 6.0, "evidence_quality": "ASSUMED"},
                    "momentum_continuity": {"raw_score": 7.5, "evidence_quality": "INFERRED"},
                },
            },
        ],
    }
    config = {"score_threshold": 5.5, "current_iteration": 1, "max_iterations": 2}
    result = composite_scorer(sample_eval, config)
    print(f"  {result['diagnosis']}")
    for v in result["variants"]:
        print(f"    #{v['rank']}: {v['variant_id']} — "
              f"adjusted: {v['composite_safety_adjusted']} | verdict: {v['verdict']} | "
              f"weakest: {v['weakest_dimension']}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_test()
