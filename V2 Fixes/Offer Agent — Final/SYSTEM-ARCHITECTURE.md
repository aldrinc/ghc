# System Architecture — Offer Agent

**Version**: 2.0
**Last Updated**: February 2026

---

## Section 1: Purpose

The Offer Agent takes a product definition + pre-researched inputs and produces a complete, scored offer document that downstream agents (Copywriting, Landing Page, Ads) consume as their source of truth.

It does NOT write copy. It engineers the architecture that copywriters build on.

---

## Section 2: Pipeline Overview

```
INPUTS                     PIPELINE                           OUTPUTS
──────                     ────────                           ───────
Product Brief ─────┐
Selected Angle ────┤       ┌──────────────────┐
Competitor         ├──────>│  Step 1:         │
  Teardowns ───────┤       │  Avatar Brief    │──── Avatar document (markdown)
VOC Research ──────┤       └────────┬─────────┘
Purple Ocean       │                │
  Research ────────┘                v
                          ┌──────────────────┐
                          │  Step 2:         │──── Calibration JSON
                          │  Market          │──── Binding constraints
                          │  Calibration     │──── Awareness-angle-matrix JSON
                          └────────┬─────────┘
                                   │
                                   v
                          ┌──────────────────┐
                          │  Step 3:         │──── 3-5 scored UMP/UMS pairs
                          │  UMP/UMS         │
                          │  Generation      │
                          └────────┬─────────┘
                                   │
                             ▼ HUMAN SELECTS UMP/UMS ▼
                                   │
                                   v
                          ┌──────────────────┐
                          │  Step 4:         │──── Base offer + 2-3 variants
                          │  Offer           │     (13 phases each)
                          │  Construction    │
                          └────────┬─────────┘
                                   │
                                   v
                          ┌──────────────────┐
                          │  Step 5:         │──── Per-variant evaluation
                          │  Self-Evaluation │──── Composite scores + verdicts
                          │  & Scoring       │──── Revision notes (if REVISE)
                          └────────┬─────────┘
                                   │
                             ▼ HUMAN SELECTS VARIANT ▼
                                   │
                                   v
                          ┌──────────────────┐
                          │  Output          │──── Final offer document (markdown)
                          │  Assembly        │──── Metadata JSON
                          │                  │──── awareness-angle-matrix.md
                          └──────────────────┘
```

---

## Section 3: Pipeline Inputs

| Input | Source | What It Contains |
|-------|--------|-----------------|
| **Product Brief** | Software intake step | Product name, description, category, price range, format, `product_customizable` flag, existing proof assets, brand voice notes |
| **Selected Angle** | Angle engine / human selection | Angle name, definition (who/pain-desire/mechanism-why/belief-shift/trigger), evidence, hook starters |
| **Competitor Teardowns** | Research pipeline | Structural pattern matrix, whitespace map, table stakes checklist, price/bonus/guarantee/proof comparisons |
| **VOC Research** | Research pipeline | Angle-specific voice-of-customer: quote banks, pain clusters, emotional drivers, buyer language |
| **Purple Ocean Research** | Research pipeline | Validated angles with evidence, shadow angles, intersection opportunities |

---

## Section 4: Step Detail

### Step 1: Avatar Brief
- **What it does**: Synthesizes all 5 inputs into a single angle-aware buyer profile
- **Key outputs**: Demographics, top 3 pain points, goals, emotional drivers, fears, curated VOC quote bank (6 themed sections), emotional journey map (Awareness > Frustration > Seeking > Relief), compression audit
- **Evidence traceability**: Every claim tagged as OBSERVED/CONVERGENT/INFERRED/ASSUMED
- **No scoring** — pure synthesis step

### Step 2: Market Calibration
- **What it does**: Translates qualitative research into formal binding parameters
- **Key outputs**:
  - Awareness level assessment (with distribution %) — both broad-market and angle-specific
  - Sophistication level assessment (with Z-score against angle-relevant competitors)
  - Lifecycle stage assessment (with velocity)
  - **8 domains of binding constraints**: headline logic, proof emphasis, bonus framing, mechanism presentation, price presentation, guarantee/risk reversal, tone/copy register, UMP/UMS presentation
  - **Awareness-angle-matrix** (Phase 7) — per-awareness-level framing for the selected angle, consumed by downstream systems (see Section 11)
  - Constant-vs-variable matrix
- **Scoring tool**: `calibration_consistency_checker` — detects logical conflicts

### Step 3: UMP/UMS Generation (HUMAN DECISION POINT)
- **What it does**: Generates 3-5 distinct UMP/UMS paired sets
- **Per pair**: Technical + buyer-facing forms, VOC evidence, competitor verification, belief shift mapping, compliance notes, kill conditions, 4 coherence tests
- **Scoring tool**: `ump_ums_scorer` — 7 weighted dimensions:
  - competitive_uniqueness (0.20), voc_groundedness (0.20), believability (0.15), mechanism_clarity (0.15), angle_alignment (0.10), compliance_safety (0.10), memorability (0.10)
- **Human selects** which pair to use — becomes locked input for Step 4

### Step 4: Offer Construction (ITERATION TARGET)
- **What it does**: 13-phase construction engine builds a complete offer around the locked UMP/UMS
- **13 phases**:
  1. Constraint extraction + bottleneck objection (4-layer coverage)
  2. Core promise (grounded in UMP/UMS + angle)
  3. Value stack (core product + 3-5 bonuses + product-shaping recs if customizable)
  4. Pricing rationale + 4-type anchoring
  5. Risk reversal / guarantee (from taxonomy)
  6. Objection coverage matrix + 2-3 unknown-unknowns
  7. Proof & credibility strategy (inventory > deployment > sequencing)
  8. Delivery mechanism variants
  9. Naming & framing (3 variants per element)
  10. Belief architecture (cascade mapped to elements)
  11. Funnel architecture + funnel position adaptation
  12. Post-construction audits (Cialdini, momentum/force diagram, novelty)
  13. 2-3 structural variants (different high-leverage axis each)
- **Scoring tools** (run on base + each variant):
  - `hormozi_scorer` — Value Equation per element
  - `objection_coverage_calculator` — coverage %, gaps, suspicious-100% flag
  - `novelty_calculator` — information value, 35% threshold check

### Step 5: Self-Evaluation & Scoring
- **What it does**: Adversarial evaluation of base + each variant across 8 dimensions
- **8 scorecard dimensions**: Value Equation, Objection Coverage, Competitive Differentiation, Compliance Safety, Internal Consistency, Clarity & Simplicity, Bottleneck Resilience, Momentum Continuity
- **Scoring tool**: `composite_scorer`
  - Applies safety factors: OBSERVED 0.9, INFERRED 0.75, ASSUMED 0.6
  - Computes weighted composite per variant
  - Renders verdict: PASS (>= 5.5), REVISE (< 5.5 + iterations left), HUMAN_REVIEW

---

## Section 5: Iteration Logic

```
IF any variant PASSES:
  → Present all passing variants to human
  → Human selects final variant
  → Proceed to output assembly

IF all REVISE + iterations remaining:
  → Extract revision notes for best variant's weakest 2 dimensions
  → Re-run Step 4 with revision_notes injected
  → Re-run Step 5
  → Max 2 iterations

IF HUMAN_REVIEW:
  → Flag with unresolved notes
  → Proceed with warnings
```

---

## Section 6: Pipeline Outputs

| Output | Format | Consumer |
|--------|--------|----------|
| Final offer document | Markdown | Copywriting Agent, Landing Page Agent, Ads Agent |
| Pipeline metadata JSON | JSON | Database, analytics |
| Awareness-angle-matrix | Markdown + JSON | Downstream agents (Tier 1 shared context) |
| All step outputs | Markdown | Audit trail, debugging |
| All structured data | JSON | Scoring tools, dashboards |

---

## Section 7: External Scoring Tools

All 6 functions live in `scoring-tools/scoring_tools.py`:

| Tool | When | Inputs | Outputs |
|------|------|--------|---------|
| `calibration_consistency_checker` | After Step 2 | Calibration JSON | { passed: bool, conflicts: [] } |
| `ump_ums_scorer` | After Step 3 | UMP/UMS pairs JSON | Ranked pairs with composite scores |
| `hormozi_scorer` | After Step 4 | Per-element JSON | Value Equation scores per element |
| `objection_coverage_calculator` | After Step 4 | Objection matrix JSON | Coverage %, gaps, flags |
| `novelty_calculator` | After Step 4 | Novelty data JSON | Information value score, classification counts |
| `composite_scorer` | After Step 5 | Per-variant evaluation JSON | Safety-adjusted composites, verdict, revision targets |

---

## Section 8: Engineering Safety Factors

Applied to all LLM-assessed ratings before scoring:

| Evidence Quality | Factor | Meaning |
|-----------------|--------|---------|
| OBSERVED | 0.9 | Directly visible in data (VOC quotes, competitor offers, market data) |
| INFERRED | 0.75 | Logically derived from observed data with reasonable assumptions |
| ASSUMED | 0.6 | Based on general marketing knowledge, not product-specific evidence |

---

## Section 9: Human Decision Points

| Gate | When | What the Human Decides | Data Available |
|------|------|----------------------|----------------|
| **UMP/UMS Selection** | After Step 3 | Which UMP/UMS pair to use for offer construction | 3-5 scored pairs with per-dimension breakdowns, composite scores, strategic selection notes |
| **Variant Selection** | After Step 5 | Which offer variant becomes the final offer | Base + 2-3 variants with 8-dimension evaluations, composite scores, cross-variant rankings, trade-off analysis |

### Human Override Conditions

- **HUMAN_REVIEW verdict**: Step 5 produces this when scores are below threshold and iterations exhausted
- **Kill condition triggers**: Any step can flag a kill condition; human decides whether to proceed or restart
- **Angle-drift detection**: Step 2 provides hooks for detecting downstream angle misalignment

---

## Section 10: Configuration

### Pipeline Configuration

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_iterations": 2,
  "score_threshold": 5.5,
  "product_customizable": true
}
```

### Safety Factor Configuration

```json
{
  "evidence_weights": {
    "OBSERVED": 0.9,
    "INFERRED": 0.75,
    "ASSUMED": 0.6
  }
}
```

### UMP/UMS Scoring Weights

```json
{
  "competitive_uniqueness": 0.20,
  "voc_groundedness": 0.20,
  "believability": 0.15,
  "mechanism_clarity": 0.15,
  "angle_alignment": 0.10,
  "compliance_safety": 0.10,
  "memorability": 0.10
}
```

---

## Section 11: Integration Output (Awareness-Angle-Matrix)

### What It Is

The awareness-angle-matrix is a structured output that maps how the selected angle should be framed across all 5 Schwartz awareness levels (Unaware, Problem-Aware, Solution-Aware, Product-Aware, Most-Aware). It bridges the gap between generic awareness-level rules and angle-specific copy execution.

### How It's Produced

Step 2, Phase 7 (Market Calibration) generates the matrix after all awareness-level calibration and binding constraints are established. Phase 7 uses the angle definition, avatar data from Step 1, and the awareness distribution from Phase 6.1 to produce framing guidance for each level.

### Schema

Each awareness level contains 4 fields:

| Field | Description |
|-------|-------------|
| `frame` | 1-2 sentence framing strategy for this level |
| `headline_direction` | Structural headline pattern (not a finished headline) |
| `entry_emotion` | Emotion the reader arrives with |
| `exit_belief` | Belief the reader must hold when they leave |

Plus metadata: `constant_elements`, `variable_elements`, `product_name_first_appears`.

### How Downstream Consumers Use It

The matrix is stored as a Tier 1 shared context file in the downstream system's shared directory (`awareness-angle-matrix.md`). When the downstream agent receives a task specifying an angle + awareness level + page type, it looks up the angle-specific framing from the matrix and combines it with generic awareness-level rules.

### Full Specification

See `downstream-integration/` for:
- `INTEGRATION-GUIDE.md` — complete data contract, field definitions, worked example, loading instructions
- `awareness-angle-matrix-prompt.md` — the generation prompt used by Step 2 Phase 7

See `docs/awareness-angle-matrix-spec.md` for the technical specification.

---

## Section 12: PRD Mapping

If building a Product Requirement Document from this system, each component maps as follows:

| PRD Section | Source Files |
|-------------|-------------|
| Overview & Purpose | This document (Section 1) |
| User Stories | `prompts/pipeline-orchestrator.md` (input/output contracts) |
| System Architecture | This document (Section 2) |
| Data Model | `prompts/pipeline-orchestrator.md` (output schema) + `scoring-tools/scoring_tools.py` |
| Step 1 Functional Requirements | `prompts/step-01-avatar-brief.md` |
| Step 2 Functional Requirements | `prompts/step-02-market-calibration.md` |
| Step 3 Functional Requirements | `prompts/step-03-ump-ums-generation.md` |
| Step 4 Functional Requirements | `prompts/step-04-offer-construction.md` |
| Step 5 Functional Requirements | `prompts/step-05-self-evaluation-scoring.md` |
| Scoring System Requirements | `scoring-tools/scoring_tools.py` + `docs/offer-scoring-framework.md` |
| Integration Output | `downstream-integration/INTEGRATION-GUIDE.md` + `docs/awareness-angle-matrix-spec.md` |
| Iteration Logic | `prompts/pipeline-orchestrator.md` (iteration section) |
| Human Interaction Requirements | This document (Section 9) |
| Configuration | This document (Section 10) |
