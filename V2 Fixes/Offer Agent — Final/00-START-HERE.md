# Offer Agent — Final Build

**Version**: 2.0
**Date**: February 2026
**Status**: Complete architecture + implementation-ready prompts

---

## What This Is

This folder contains the complete, standalone Offer Agent system. It takes a product definition + pre-researched inputs and produces a scored, stress-tested offer document.

The Offer Agent does NOT write copy. It engineers the offer architecture — value stack, proof strategy, belief cascade, pricing, guarantees, objection handling — that downstream copywriting systems build on.

---

## Folder Structure

```
Offer Agent — Final/
├── 00-START-HERE.md                    ← You are here
├── SYSTEM-ARCHITECTURE.md              ← Full system map, pipeline, scoring, integration
│
├── prompts/                            ← 6 prompt files (orchestrator + 5 steps)
│   ├── pipeline-orchestrator.md        ← Master control flow
│   ├── step-01-avatar-brief.md         ← Buyer profile synthesis
│   ├── step-02-market-calibration.md   ← Binding constraints + awareness-angle-matrix
│   ├── step-03-ump-ums-generation.md   ← Unique mechanism generation
│   ├── step-04-offer-construction.md   ← 13-phase offer builder
│   └── step-05-self-evaluation-scoring.md ← Adversarial evaluation
│
├── scoring-tools/
│   └── scoring_tools.py                ← 6 deterministic Python scoring functions
│
├── docs/
│   ├── offer-scoring-framework.md      ← Scoring methodology and philosophy
│   └── awareness-angle-matrix-spec.md  ← Technical spec for the bridge output
│
└── downstream-integration/             ← For systems that consume Offer Agent output
    ├── INTEGRATION-GUIDE.md            ← Data contract, schema, worked example
    └── awareness-angle-matrix-prompt.md ← Generation prompt (used by Step 2 Phase 7)
```

---

## How to Read This

1. Start with `SYSTEM-ARCHITECTURE.md` — understand the full pipeline, scoring, and integration output
2. Read `prompts/pipeline-orchestrator.md` — this is the master control flow that orchestrates all 5 steps
3. Read each step prompt in order:
   - `step-01-avatar-brief.md` — buyer profile synthesis
   - `step-02-market-calibration.md` — binding constraints + awareness-angle-matrix (Phase 7)
   - `step-03-ump-ums-generation.md` — UMP/UMS generation (human decision point)
   - `step-04-offer-construction.md` — 13-phase offer builder (iteration target)
   - `step-05-self-evaluation-scoring.md` — adversarial evaluation + composite scoring
4. Review `scoring-tools/scoring_tools.py` for the 6 external scoring functions
5. Reference `docs/offer-scoring-framework.md` for the scoring philosophy
6. If integrating with a downstream system, read `downstream-integration/INTEGRATION-GUIDE.md`

---

## Key Design Decisions

### Single-Angle Pipeline
- The Offer Agent runs for ONE angle at a time
- To build offers for multiple angles, run the pipeline multiple times
- Each run produces a self-contained offer document + awareness-angle-matrix for that angle

### Separation of Concerns
- **LLMs generate and assess** — they produce dimensional ratings, evidence classifications, and structural analysis
- **Python tools score** — they apply safety factors, compute weighted composites, and determine pass/fail
- **Humans decide** — they select UMP/UMS pairs and final offer variants

### Engineering Safety Factors
- OBSERVED evidence: 0.9 multiplier
- INFERRED evidence: 0.75 multiplier
- ASSUMED evidence: 0.6 multiplier
- These protect against LLM overconfidence in self-assessment

### Downstream Integration
- The Offer Agent produces an awareness-angle-matrix as a bridge output
- This matrix tells downstream systems how to frame copy at each awareness level for the processed angle
- The Offer Agent is fully functional without any downstream system connected
- See `downstream-integration/` for the complete integration spec

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Pipeline orchestrator | Complete | Master control flow with iteration logic |
| Step 1: Avatar Brief | Complete | Buyer profile synthesis with evidence traceability |
| Step 2: Market Calibration | Complete | 7 phases including awareness-angle-matrix (Phase 7) |
| Step 3: UMP/UMS Generation | Complete | 3-5 scored pairs + human selection gate |
| Step 4: Offer Construction | Complete | 13-phase builder with 3 scoring tools |
| Step 5: Self-Evaluation | Complete | 8-dimension adversarial evaluation |
| Scoring tools (6 functions) | Complete | Deterministic Python, documented methodology |
| Awareness-angle-matrix bridge | Complete | Phase 7 in Step 2 + spec + integration guide |

---

## File Count Summary

| Directory | Files | Purpose |
|-----------|-------|---------|
| prompts/ | 6 | Pipeline orchestrator + 5 step prompts |
| scoring-tools/ | 1 | 6 scoring functions in one Python file |
| docs/ | 2 | Scoring framework + bridge spec |
| downstream-integration/ | 2 | Integration guide + generation prompt |
| Root | 2 | START-HERE + SYSTEM-ARCHITECTURE |
| **Total** | **13** | |

---

## What Is NOT in This Folder

- **Research inputs** (competitor teardowns, VOC data, purple ocean research) — these are per-product and generated upstream
- **Product-specific outputs** (generated offers, generated copy) — these are runtime outputs
- **The Copywriting Agent** — it is a separate, standalone system that can optionally consume this system's outputs
- **Test outputs and reports** — from development testing, not part of the system spec
- **Word document versions** — convenience exports, not source of truth
- **v1 prompt files** — superseded by v2; only v2 is included
