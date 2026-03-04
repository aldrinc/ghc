# Offer Agent Pipeline — Orchestrator Specification (v2)

## Overview

The Offer Agent pipeline is a **5-step sequential prompt chain** that takes pre-researched inputs (product brief, selected angle, competitor teardowns, VOC research, purple ocean research) and produces a complete, scored offer document for RAG consumption by downstream agents (Copywriting, Landing Page, Ads).

**Key architectural change from v1**: All research is performed upstream by other agents/workflows. The Offer Agent is purely a synthesis → construction → evaluation engine. It does not perform web research.

Each step is a standalone prompt template with `{{placeholder}}` variables. The orchestrator:
1. Validates and injects all provided inputs into each prompt
2. Calls the LLM
3. Extracts structured JSON blocks from the LLM output
4. Calls deterministic scoring tools on extracted JSON
5. Passes enriched output to the next step
6. Manages human decision points (Step 3 UMP/UMS selection)
7. Handles iteration logic (Step 5 → Step 4 loop)

---

## Pipeline Inputs

The pipeline receives ALL of the following as pre-researched inputs:

```json
{
  "product_brief": {
    "name": "string — product name",
    "description": "string — what the product is and does",
    "category": "string — product category / niche",
    "price_cents": "integer — price in cents",
    "currency": "string — 3-letter currency code",
    "business_model": "string — one-time / subscription / freemium / etc.",
    "funnel_position": "string — cold_traffic / post_nurture / retargeting / evergreen",
    "target_platforms": ["string — Meta / TikTok / YouTube / Google / Email"],
    "target_regions": ["string — US / UK / Tier1 / etc."],
    "product_customizable": "boolean — true if product can be shaped to fit the angle (books, supplements, formulations), false if product is fixed (LED mask, physical gadget)",
    "constraints": {
      "compliance_sensitivity": "string — low / medium / high",
      "existing_proof_assets": ["string — what proof already exists"],
      "brand_voice_notes": "string — any tone/voice constraints"
    }
  },
  "selected_angle": {
    "angle_name": "string — the selected purple ocean angle",
    "angle_definition": {
      "who": "string — avatar/segment",
      "pain_desire": "string — specific pain or desire in their context",
      "mechanism_why": "string — the story they believe, why they buy",
      "belief_shift": "string — what they must believe now vs before",
      "trigger": "string — why now? what context triggers the purchase"
    },
    "angle_evidence": ["string — supporting VOC/research evidence"],
    "angle_hooks": ["string — hook starters from purple ocean research"]
  },
  "provided_research": {
    "competitor_teardowns": "string — full competitor offer teardowns/breakdowns (from competitor ads, landers, copy, assets)",
    "voc_research": "string — angle-specific, custom enhanced voice-of-customer research",
    "purple_ocean_research": "string — purple ocean angle research output"
  },
  "config": {
    "llm_model": "string — model identifier",
    "max_iterations": "integer — default 2",
    "score_threshold": "number — default 5.5"
  }
}
```

---

## Pipeline Flow

```
INPUTS (all provided upstream)
  ├── product_brief (with product_customizable flag)
  ├── selected_angle (chosen angle + evidence + hooks)
  └── provided_research
       ├── competitor_teardowns (from competitor ads/landers/copy analysis)
       ├── voc_research (angle-specific, custom enhanced VOC)
       └── purple_ocean_research (angle research output)

STEP 1: Avatar Brief
  ├── Input: product_brief + selected_angle + provided_research.voc_research + provided_research.purple_ocean_research + provided_research.competitor_teardowns
  ├── Prompt: step-01-avatar-brief.md
  ├── Tool: LLM only (synthesis, no web)
  ├── Output: step_01_output (markdown — avatar document)
  └── Scoring: none (synthesis step)

STEP 2: Market Calibration
  ├── Input: product_brief + selected_angle + provided_research.competitor_teardowns + provided_research.voc_research + step_01_output
  ├── Prompt: step-02-market-calibration.md
  ├── Tool: LLM only (synthesis, no web)
  ├── Output: step_02_output (markdown + calibration JSON + binding constraints + awareness-angle-matrix JSON)
  ├── SCORING TOOL CALL: calibration_consistency_checker
  │     Input: calibration JSON (awareness, sophistication, lifecycle assessments)
  │     Output: consistency_result { passed: bool, conflicts: [] }
  ├── EXTRACT: awareness_angle_matrix JSON from step_02_output Section 10.3
  │     This is a standalone output consumed by the downstream Copywriting Agent.
  │     Contains: per-awareness-level framing (frame, headline_direction, entry_emotion,
  │     exit_belief) for the selected angle + constant-vs-variable matrix.
  └── Final output: step_02_output with consistency validation appended

STEP 3: UMP/UMS Generation & Scoring  ← HUMAN DECISION POINT
  ├── Input: product_brief + selected_angle + provided_research + step_01_output + step_02_output
  ├── Prompt: step-03-ump-ums-generation.md
  ├── Tool: LLM only (synthesis, no web)
  ├── Output: step_03_output (3-5 UMP/UMS paired sets as structured JSON + narrative)
  ├── SCORING TOOL CALL: ump_ums_scorer
  │     Input: ump_ums_pairs JSON array (each pair has 7 dimensional ratings)
  │     Computation: composite = weighted_average(competitive_uniqueness, voc_groundedness,
  │                   believability, mechanism_clarity, angle_alignment,
  │                   compliance_safety, memorability)
  │     Weights: [0.20, 0.20, 0.15, 0.15, 0.10, 0.10, 0.10]
  │     Output: ranked UMP/UMS pairs with composite scores + per-dimension breakdown
  │
  ├── *** HUMAN DECISION POINT ***
  │     Present ranked UMP/UMS pairs to user.
  │     User selects which pair to use for offer construction.
  │     Selected pair becomes: selected_ump_ums
  │
  └── Final output: step_03_output + selected_ump_ums

STEP 4: Offer Construction  ← ITERATION TARGET
  ├── Input: ALL prior inputs + step_01_output + step_02_output + selected_ump_ums + revision_notes (empty on first run)
  ├── Prompt: step-04-offer-construction.md
  ├── Tool: LLM only (synthesis, no web)
  ├── Output: step_04_output (markdown + multiple JSON blocks)
  │     Produces: BASE OFFER + 2-3 STRUCTURAL VARIANTS
  │     Variants differ on high-leverage axes:
  │       - Variant A: Different bonus architecture
  │       - Variant B: Different guarantee structure
  │       - Variant C: Different pricing/anchoring approach
  │     If product_customizable == true:
  │       - Also generates product-shaping recommendations (how core product
  │         content/structure should be adapted to serve the angle)
  │
  ├── SCORING TOOL CALLS (run on base offer AND each variant):
  │     1. hormozi_scorer
  │        Input: value_stack_json (per-element lever assessments)
  │        Output: scored value stack with per-element + aggregate scores
  │
  │     2. objection_coverage_calculator
  │        Input: objection_mapping_json
  │        Output: { coverage_pct, uncovered_objections[] }
  │
  │     3. novelty_calculator
  │        Input: element_novelty_json
  │        Output: { information_value, novel_count, meets_threshold }
  │
  └── Final output: step_04_output with all variants scored

STEP 5: Self-Evaluation & Composite Scoring
  ├── Input: ALL prior inputs + step_04_output (with scored variants)
  ├── Prompt: step-05-self-evaluation-scoring.md
  ├── Tool: LLM only (adversarial evaluation)
  ├── Output: step_05_output (markdown + evaluation JSON)
  │     Evaluates: base offer AND each variant independently
  │
  ├── SCORING TOOL CALL: composite_scorer
  │     Input: evaluation JSON with per-dimension data (for base + each variant)
  │     Computation:
  │       FOR EACH variant (including base):
  │         FOR EACH dimension:
  │           1. Extract evidence quality classification
  │           2. Apply safety_factor: OBSERVED→0.9, INFERRED→0.75, ASSUMED→0.6
  │           3. Compute safety_adjusted_score
  │           4. Z-score against competitor baseline if available
  │         COMPOSITE = weighted_average(safety_adjusted_scores)
  │         VERDICT: ≥5.5 → PASS, <5.5 + iterations remaining → REVISE, else → HUMAN_REVIEW
  │
  │     Output: per-variant composite scores + verdicts
  │
  └── Final output: step_05_output with composite scores and variant rankings

ITERATION LOGIC:
  IF any variant has verdict == "PASS":
    → Present all passing variants with scores to user
    → User selects final variant (or combines elements)
    → Proceed to output assembly
  IF all variants have verdict == "REVISE" AND iteration < max_iterations:
    1. Identify the best-scoring variant
    2. Extract revision notes targeting its weakest 2 dimensions
    3. Re-run Step 4 with revision_notes injected (revising best variant only)
    4. Re-run Step 5
    5. Increment iteration counter
  IF verdict == "HUMAN_REVIEW":
    → Flag output with unresolved notes
    → Proceed to output assembly with warnings

OUTPUT ASSEMBLY:
  1. Compile final offer document (markdown) from selected Step 4 variant
  2. Compile metadata JSON:
     {
       "product_id": "uuid",
       "pipeline_run_id": "uuid",
       "pipeline_version": "2.0",
       "model_used": "model_identifier",
       "angle_used": "selected_angle.angle_name",
       "ump_ums_selected": { "ump": "...", "ums": "..." },
       "product_customizable": true|false,
       "iterations": N,
       "variants_generated": N,
       "selected_variant": "base|variant_a|variant_b|variant_c",
       "final_composite_score": X.XX,
       "final_verdict": "PASS|HUMAN_REVIEW",
       "per_dimension_scores": {...},
       "generated_at": "ISO timestamp"
     }
  3. Write awareness-angle-matrix to shared/awareness-angle-matrix.md
     - Extract the awareness_angle_matrix JSON from Step 2 output (Section 10.3)
     - Format as markdown with YAML-style blocks per angle per awareness level
     - Store alongside audience-product.md, brand-voice.md, compliance.md
     - This file is a Tier 1 (always-loaded) input for the Copywriting Agent
     - If running multiple angles, append each angle's matrix to the same file
  4. Store in RAG file system for downstream agent consumption
  5. Optionally write to MOS DB
```

---

## External Scoring Tools — Function Specifications

These are deterministic functions. No LLM involvement. Pure math.

### 1. `calibration_consistency_checker(calibration: CalibrationJSON) → ConsistencyResult`

```python
CONFLICT_RULES = [
    {
        "condition": lambda c: c["lifecycle"]["assessment"] == "introduction"
                               and c["awareness"]["assessment"] == "most-aware",
        "message": "CONFLICT: Introduction-stage market cannot have most-aware buyers",
        "severity": "ERROR"
    },
    {
        "condition": lambda c: c["lifecycle"]["assessment"] == "maturity"
                               and c["sophistication"]["assessment"] == "low",
        "message": "WARNING: Mature market with low sophistication is unusual — verify",
        "severity": "WARNING"
    },
    {
        "condition": lambda c: c["awareness"]["assessment"] == "unaware"
                               and c.get("competitor_count", 0) > 10,
        "message": "CONFLICT: Unaware audience unlikely in market with 10+ competitors",
        "severity": "ERROR"
    },
    {
        "condition": lambda c: c["lifecycle"]["assessment"] == "decline"
                               and c["sophistication"]["assessment"] == "low",
        "message": "CONFLICT: Declining market should have high sophistication (exhausted buyers)",
        "severity": "WARNING"
    },
]

def calibration_consistency_checker(calibration):
    """Check for logical inconsistencies in market calibration."""
    conflicts = []
    for rule in CONFLICT_RULES:
        if rule["condition"](calibration):
            conflicts.append({
                "message": rule["message"],
                "severity": rule["severity"]
            })

    return {
        "passed": not any(c["severity"] == "ERROR" for c in conflicts),
        "conflicts": conflicts
    }
```

### 2. `ump_ums_scorer(pairs: UMPUMSPair[]) → RankedPairs[]`

```python
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

def ump_ums_scorer(pairs):
    """
    Score UMP/UMS paired sets across 7 dimensions.
    Each dimension is rated 1-10 by the LLM with evidence classification.
    This function computes safety-adjusted composite scores.
    """
    scored = []
    for pair in pairs:
        raw_composite = 0
        safety_adjusted_composite = 0
        dimension_details = {}

        for dim, weight in UMP_UMS_WEIGHTS.items():
            dim_data = pair["dimensions"][dim]
            raw_score = dim_data["score"]
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
            "pair_id": pair["pair_id"],
            "ump_name": pair["ump_name"],
            "ums_name": pair["ums_name"],
            "composite_raw": round(raw_composite, 2),
            "composite_safety_adjusted": round(safety_adjusted_composite, 2),
            "dimensions": dimension_details,
            "strongest_dimension": max(dimension_details.items(), key=lambda x: x[1]["safety_adjusted"])[0],
            "weakest_dimension": min(dimension_details.items(), key=lambda x: x[1]["safety_adjusted"])[0],
            "evidence_summary": {
                "observed": sum(1 for d in dimension_details.values() if d["evidence_quality"] == "OBSERVED"),
                "inferred": sum(1 for d in dimension_details.values() if d["evidence_quality"] == "INFERRED"),
                "assumed": sum(1 for d in dimension_details.values() if d["evidence_quality"] == "ASSUMED"),
            }
        })

    ranked = sorted(scored, key=lambda x: x["composite_safety_adjusted"], reverse=True)

    # Add rank and delta from top
    for i, pair in enumerate(ranked):
        pair["rank"] = i + 1
        pair["delta_from_top"] = round(ranked[0]["composite_safety_adjusted"] - pair["composite_safety_adjusted"], 2) if i > 0 else 0

    return ranked
```

### 3. `hormozi_scorer(value_stack: ValueStackJSON) → ScoredValueStack`

```python
def hormozi_scorer(value_stack):
    """
    Score each element against Hormozi's value equation.
    Value = (Dream Outcome × Perceived Likelihood) / (Time Delay × Effort & Sacrifice)

    Lever ratings use INVERTED scale for denominator:
      - dream_outcome: 1=low, 10=high (higher is better)
      - perceived_likelihood: 1=unlikely, 10=very likely (higher is better)
      - time_delay: 1=instant, 10=very slow (LOWER is better for buyer)
      - effort_sacrifice: 1=effortless, 10=extreme effort (LOWER is better for buyer)

    The formula uses (11 - time_delay) and (11 - effort_sacrifice) to invert,
    so higher scores always mean better value.
    """
    scored_elements = []
    for element in value_stack["elements"]:
        levers = element["hormozi_levers"]

        # Numerator: what buyer gets
        dream = levers["dream_outcome"]
        likelihood = levers["perceived_likelihood"]
        numerator = dream * likelihood

        # Denominator: buyer's cost (inverted so lower raw = better)
        # Use (11 - x) to invert: a raw 2 (fast) becomes 9, a raw 9 (slow) becomes 2
        time_inv = 11 - levers["time_delay"]
        effort_inv = 11 - levers["effort_sacrifice"]

        # Score = numerator × inverted_denominator (all higher = better now)
        # Normalize to 1-10 scale
        raw_value = (numerator * time_inv * effort_inv) / 1000  # max theoretical ~10
        value_score = round(min(max(raw_value, 0.1), 10.0), 2)

        scored_elements.append({
            **element,
            "value_score": value_score,
            "lever_detail": {
                "numerator": numerator,
                "time_inverted": time_inv,
                "effort_inverted": effort_inv,
            }
        })

    avg_score = round(
        sum(e["value_score"] for e in scored_elements) / len(scored_elements), 2
    ) if scored_elements else 0

    return {
        "elements": scored_elements,
        "aggregate_value_score": avg_score,
        "highest_value_element": max(scored_elements, key=lambda x: x["value_score"])["name"] if scored_elements else None,
        "lowest_value_element": min(scored_elements, key=lambda x: x["value_score"])["name"] if scored_elements else None,
        "lever_averages": {
            "dream_outcome": round(sum(e["hormozi_levers"]["dream_outcome"] for e in scored_elements) / len(scored_elements), 1) if scored_elements else 0,
            "perceived_likelihood": round(sum(e["hormozi_levers"]["perceived_likelihood"] for e in scored_elements) / len(scored_elements), 1) if scored_elements else 0,
            "time_delay": round(sum(e["hormozi_levers"]["time_delay"] for e in scored_elements) / len(scored_elements), 1) if scored_elements else 0,
            "effort_sacrifice": round(sum(e["hormozi_levers"]["effort_sacrifice"] for e in scored_elements) / len(scored_elements), 1) if scored_elements else 0,
        }
    }
```

### 4. `objection_coverage_calculator(mapping: ObjectionMappingJSON) → CoverageResult`

```python
def objection_coverage_calculator(mapping):
    """Calculate objection coverage percentage and identify gaps."""
    total = len(mapping["objections"])
    covered = sum(1 for obj in mapping["objections"] if obj["covered"])
    uncovered = [obj for obj in mapping["objections"] if not obj["covered"]]

    # Force unknown-unknown objection generation
    # If 100% coverage, flag as suspicious
    coverage_pct = round((covered / total) * 100, 1) if total > 0 else 0
    suspicious_perfect = coverage_pct == 100.0

    return {
        "total_objections": total,
        "covered_count": covered,
        "uncovered_count": len(uncovered),
        "coverage_pct": coverage_pct,
        "suspicious_perfect_coverage": suspicious_perfect,
        "warning": "100% coverage is suspicious — LLM may be mapping too generously. Verify unknown-unknown objections were generated." if suspicious_perfect else None,
        "uncovered_objections": [
            {"objection": obj["objection"], "source": obj["source"], "priority": obj.get("priority", "unknown")}
            for obj in uncovered
        ],
        "weakest_coverage": min(
            (obj for obj in mapping["objections"] if obj["covered"]),
            key=lambda x: x.get("coverage_strength", 0),
            default=None
        )
    }
```

### 5. `novelty_calculator(elements: NoveltyJSON) → NoveltyResult`

```python
def novelty_calculator(elements):
    """Calculate information value (novelty) of offer elements vs competitor baseline."""
    WEIGHTS = {"NOVEL": 1.0, "INCREMENTAL": 0.3, "REDUNDANT": 0.0}

    total = len(elements["classifications"])
    if total == 0:
        return {"information_value": 0, "novel_count": 0, "incremental_count": 0, "redundant_count": 0}

    weighted_sum = sum(
        WEIGHTS.get(item["classification"], 0)
        for item in elements["classifications"]
    )
    info_value = round(weighted_sum / total, 3)

    counts = {"NOVEL": 0, "INCREMENTAL": 0, "REDUNDANT": 0}
    for item in elements["classifications"]:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1

    return {
        "information_value": info_value,
        "novel_count": counts["NOVEL"],
        "incremental_count": counts["INCREMENTAL"],
        "redundant_count": counts["REDUNDANT"],
        "total_elements": total,
        "meets_threshold": info_value >= 0.35,
        "most_redundant_elements": [
            item["element_name"] for item in elements["classifications"]
            if item["classification"] == "REDUNDANT"
        ]
    }
```

### 6. `composite_scorer(evaluation: EvaluationJSON, config: ScoringConfig) → CompositeResult`

```python
DIMENSION_WEIGHTS = {
    "value_equation": 0.15,
    "objection_coverage": 0.15,
    "competitive_differentiation": 0.15,
    "compliance_safety": 0.10,
    "internal_consistency": 0.10,
    "clarity_simplicity": 0.10,
    "bottleneck_resilience": 0.10,
    "momentum_continuity": 0.15,
}

SAFETY_FACTORS = {
    "OBSERVED": 0.9,
    "INFERRED": 0.75,
    "ASSUMED": 0.6,
}

def composite_scorer(evaluation, config):
    """
    Compute final composite score with safety factors and Z-score normalization.
    Runs on each variant independently. Returns per-variant results.
    """
    variants = evaluation.get("variants", [{"variant_id": "base", "dimensions": evaluation["dimensions"]}])

    variant_results = []
    for variant in variants:
        dimension_results = {}
        for dim_name, weight in DIMENSION_WEIGHTS.items():
            dim_data = variant["dimensions"].get(dim_name, {})
            raw_score = dim_data.get("raw_score", 0)
            evidence_quality = dim_data.get("evidence_quality", "ASSUMED")

            sf = SAFETY_FACTORS.get(evidence_quality, 0.6)
            safety_adjusted = round(raw_score * sf, 2)

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
                "weighted_contribution": round(safety_adjusted * weight, 3),
                "kill_condition": dim_data.get("kill_condition", "NOT STATED"),
            }

        composite_raw = round(sum(d["raw_score"] * DIMENSION_WEIGHTS[k] for k, d in dimension_results.items()), 2)
        composite_safety = round(sum(d["weighted_contribution"] for d in dimension_results.values()), 2)

        threshold = config.get("score_threshold", 5.5)
        iteration = config.get("current_iteration", 1)
        max_iterations = config.get("max_iterations", 2)

        if composite_safety >= threshold:
            verdict = "PASS"
        elif iteration < max_iterations:
            verdict = "REVISE"
        else:
            verdict = "HUMAN_REVIEW"

        sorted_dims = sorted(dimension_results.items(), key=lambda x: x[1]["safety_adjusted"])
        revision_targets = [sorted_dims[0][0], sorted_dims[1][0]] if verdict == "REVISE" else []

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
            "evidence_quality_summary": {
                "observed_count": sum(1 for d in dimension_results.values() if d["evidence_quality"] == "OBSERVED"),
                "inferred_count": sum(1 for d in dimension_results.values() if d["evidence_quality"] == "INFERRED"),
                "assumed_count": sum(1 for d in dimension_results.values() if d["evidence_quality"] == "ASSUMED"),
            }
        })

    # Rank variants by composite score
    variant_results.sort(key=lambda x: x["composite_safety_adjusted"], reverse=True)
    for i, v in enumerate(variant_results):
        v["rank"] = i + 1

    return {
        "best_variant": variant_results[0]["variant_id"],
        "best_score": variant_results[0]["composite_safety_adjusted"],
        "any_passing": any(v["verdict"] == "PASS" for v in variant_results),
        "variants": variant_results
    }
```

---

## Output Schema

The pipeline produces:

```json
{
  "pipeline_run": {
    "id": "uuid",
    "product_name": "string",
    "angle_used": "string",
    "ump_ums_selected": { "ump": "string", "ums": "string" },
    "product_customizable": true|false,
    "version": "2.0",
    "model_used": "string",
    "started_at": "ISO timestamp",
    "completed_at": "ISO timestamp",
    "iterations": "integer",
    "variants_generated": "integer",
    "selected_variant": "string",
    "final_composite_score": "number",
    "final_verdict": "PASS | HUMAN_REVIEW",
    "per_dimension_scores": {}
  },
  "offer_document": "string — complete markdown offer document (selected Step 4 variant)",
  "step_outputs": {
    "step_01": "string — avatar brief markdown",
    "step_02": "string — market calibration markdown",
    "step_03": "string — UMP/UMS generation + scoring markdown",
    "step_04": "string — offer construction (base + variants) markdown",
    "step_05": "string — self-evaluation markdown"
  },
  "structured_data": {
    "calibration": "CalibrationJSON — market calibration parameters",
    "awareness_angle_matrix": "AwarenessAngleMatrixJSON — per-awareness-level angle framing for downstream Copywriting Agent",
    "ump_ums_rankings": "RankedPairs[] — scored UMP/UMS pairs",
    "value_stack_scores": "ScoredValueStack — Hormozi-scored value stack (per variant)",
    "objection_coverage": "CoverageResult — objection mapping analysis (per variant)",
    "novelty_analysis": "NoveltyResult — information theory analysis (per variant)",
    "composite_evaluation": "CompositeResult — final scoring breakdown (per variant)"
  }
}
```

---

## MOS DB Integration (Optional Post-Pipeline)

After pipeline completion, the orchestrator can optionally write to MOS Postgres:

```sql
-- Create or update product
INSERT INTO products (id, org_id, client_id, name, description, category,
                      primary_benefits, feature_bullets, guarantee_text, disclaimers)
VALUES (gen_random_uuid(), :org_id, :client_id, :name, :description, :category,
        :primary_benefits, :feature_bullets, :guarantee_text, :disclaimers)
ON CONFLICT (id) DO UPDATE SET ...;

-- Create offer (includes angle reference)
INSERT INTO product_offers (id, org_id, client_id, product_id, name, description,
                            business_model, differentiation_bullets, guarantee_text,
                            angle_name, ump_text, ums_text)
VALUES (gen_random_uuid(), :org_id, :client_id, :product_id, :offer_name, :offer_description,
        :business_model, :differentiation_bullets, :guarantee_text,
        :angle_name, :ump_text, :ums_text);

-- Create price point(s)
INSERT INTO product_offer_price_points (id, offer_id, product_id, label, amount_cents, currency)
VALUES (gen_random_uuid(), :offer_id, :product_id, :label, :amount_cents, :currency);
```
