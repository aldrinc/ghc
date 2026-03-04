# Architecture Map — DR Copywriting System

## System Overview

A modular, brand-agnostic direct response copywriting system that generates, scores, and verifies headlines, presell advertorials, and sales pages. Built for both AI agent execution and human copywriter workflows.

```
                    ┌─────────────────────────────────────┐
                    │        01_GOVERNANCE                 │
                    │  (Immutable Source of Truth)          │
                    │                                       │
                    │  sections/     shared_context/        │
                    │  S2-S11        audience-product.md    │
                    │  SA-SE         brand-voice.md         │
                    │                compliance.md          │
                    │                mental-models.md       │
                    └──────────────┬───────────────────────┘
                                   │
                         ┌─────────┴─────────┐
                         │                     │
                         ▼                     ▼
              ┌──────────────────┐   ┌──────────────────┐
              │  02_ENGINES       │   │  04_PROMPT        │
              │  (Execution)      │   │  TEMPLATES        │
              │                   │   │  (Procedures)     │
              │  headline_engine/ │   │                   │
              │  promise_contract/│   │  headline_gen.md  │
              │  page_templates/  │   │  advertorial.md   │
              │                   │   │  sales_page.md    │
              │                   │   │  promise_ext.md   │
              └────────┬──────────┘   └───────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  03_SCORERS       │
              │  (Verification)   │
              │                   │
              │  headline_scorer  │
              │  congruency       │
              │  qa_loop          │
              │  page_scorers/    │
              └────────┬──────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  05_SCHEMAS       │
              │  (I/O Contracts)  │
              │                   │
              │  headline_input   │
              │  headline_output  │
              │  listicle.schema  │
              │  sales_pdp.schema │
              └──────────────────┘
```

## Dependency Graph

```
HEADLINE GENERATION
├── Reads: audience-product.md, brand-voice.md, compliance.md
├── Reads: S5 (awareness routing), S7 (hook construction)
├── Reads: WORKFLOW.md Section 3 (archetypes), Section 4 (page-type calibration)
├── Reads: ENGINE.md (execution procedure)
├── Reads: reference/ (formulas, patterns, platform rules)
├── Input schema: headline_input.json
├── Output schema: headline_output.json
├── Scored by: headline_scorer_v2.py (29 tests, 44 pts)
├── QA loop: headline_qa_loop.py (auto-fix failing headlines)
└── Outputs: Scored headlines + Promise Contracts (Step 4.5)

PROMISE CONTRACT EXTRACTION (Step 4.5)
├── Input: Scored headline (B tier or above)
├── Reads: PROMISE_CONTRACT_SYSTEM.md
├── Output: 4-field JSON (loop_question, specific_promise, delivery_test, minimum_delivery)
└── Enforced by: headline_body_congruency.py (13 tests, 19 pts, PC2 hard gate)

ADVERTORIAL WRITING (Presell)
├── Input: Winning headline + Promise Contract
├── Reads: audience-product.md, brand-voice.md, compliance.md
├── Reads: S2 (advertorial template), S9 (section jobs), SA (belief chain B1-B4), SB (craft rules)
├── Template: 6-section structure, 800-1,200 words
├── Belief chain: B1 → B2 → B3 → B4
├── Scored by: headline_body_congruency.py
└── Output: Markdown + Word doc

SALES PAGE WRITING
├── Input: Winning headline + Promise Contract + Presell advertorial (for message match)
├── Reads: audience-product.md, brand-voice.md, compliance.md
├── Reads: S2 (sales template), S9 (section jobs), SA (belief chain B5-B8), SB (craft rules)
├── Reads: Page constraints + purpose docs
├── Template: 12-section structure (or 16-module merged), 1,800-2,800 words (warm traffic)
├── Belief chain: B5 → B6 → B7 → B8
├── Scored by: headline_body_congruency.py
├── Architecture options: Copy-first (md) | Data-first (JSON) | Merged (md+UI)
└── Output: Markdown + Word doc (+ JSON for PDP schema option)
```

## The Belief Chain (B1-B8)

The core persuasion architecture. Every piece of copy in the funnel advances specific beliefs:

```
PRESELL ADVERTORIAL (B1-B4)          SALES PAGE (B5-B8)
─────────────────────────            ──────────────────
B1: The problem is real              B5: This product solves it (UMS)
B2: The problem is urgent            B6: This product is for ME (Identity)
B3: A solution category exists       B7: The offer is fair (Value)
B4: I should look at this product    B8: I should buy now (Risk reversal)
```

Defined in: `01_governance/sections/Subsection A - Structural Principles.md`

## The Promise Contract Flow

```
Headline Generated
        │
        ▼
  Step 4.5: Extract Promise Contract
  ┌───────────────────────────────────┐
  │ loop_question: "What?"             │
  │ specific_promise: "Reader learns X"│
  │ delivery_test: "Body must do Y"    │
  │ minimum_delivery: "By section Z"   │
  └────────────┬──────────────────────┘
               │
               ▼
     Body Copy Written
     (governed by contract)
               │
               ▼
     headline_body_congruency.py
     ┌─────────────────────────┐
     │ PC1: Contract present?   │ 1 pt
     │ PC2: Delivery test met?  │ 3 pts [HARD GATE]
     │ PC3: Timing correct?     │ 2 pts
     │ PC4: Completeness?       │ 1 pt
     │ + HP1-HP5, BH1-BH4       │ 12 pts
     │ Total: 19 pts             │
     │ Pass: 75% (14.25+)       │
     └─────────────────────────┘
```

## Awareness Level Routing

```
                    UNAWARE
                       │
                       ▼
               PROBLEM-AWARE ←── Cold traffic (Meta, TikTok)
                       │           enters here via presell
                       ▼
              SOLUTION-AWARE ←── Presell exits here
                       │           Sales page receives here
                       ▼
               PRODUCT-AWARE
                       │
                       ▼
                 MOST-AWARE ←── Sales page exits here
                                  (ready to buy)
```

Routing logic defined in: `01_governance/sections/Section 5 - Awareness-Level Routing Logic.md`

## Scorer Architecture

```
HEADLINE SCORER (headline_scorer_v2.py)
├── Intrigue & Attention (IA): 6 tests, 10 pts
├── Promise & Trust (PT): 10 tests, 14 pts
├── Craft & Structure (CS): 6 tests, 8 pts
├── Brand Compliance (BC): 7 tests, 12 pts
├── Hard Gates: BC1 (banned words), BC2 (disease claims), BC3 (prohibited phrases)
├── Tiers: S (38+) / A (33-37) / B (28-32) / C (22-27) / D (15-21) / DQ (<15)
└── Zero LLM dependency — fully deterministic

CONGRUENCY SCORER (headline_body_congruency.py)
├── Promise Contract (PC1-PC4): 7 pts (PC2 is HARD GATE)
├── Headline→Body (HP1-HP5): 7 pts
├── Body→Headline (BH1-BH4): 5 pts
├── Total: 19 pts, Pass: 75%
└── Zero LLM dependency — fully deterministic

QA LOOP (headline_qa_loop.py)
├── Takes failing headlines
├── LLM-powered rewrite (max 3 iterations)
├── Re-scores after each attempt
└── Hard gates must pass on final iteration
```

## File Count Summary

| Folder | Files | Purpose |
|--------|-------|---------|
| 01_governance/ | ~22 | Foundational docs, shared context, research artifacts |
| 02_engines/ | ~12 | Headline engine, promise contract, page templates |
| 03_scorers/ | ~7 | Python evaluation tools |
| 04_prompt_templates/ | 6 | Reusable execution patterns |
| 05_schemas/ | 5 | I/O contract definitions |
| 06_examples/ | ~25 | Complete Honest Herbalist worked example |
| 07_roadmap/ | ~10 | VOCC specs, future plans |
| **Total** | **~87** | |
