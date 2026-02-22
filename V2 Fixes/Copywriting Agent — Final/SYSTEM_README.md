# DR Copywriting System

## What This Is

A complete, brand-agnostic direct response copywriting system. It generates headlines, writes presell advertorials and sales pages, scores everything deterministically, and enforces promise delivery through automated verification.

Built for dual use:
- **AI agents:** Load this folder into a fresh session. Start with this README. Follow the prompt templates.
- **Human teams:** Read ARCHITECTURE_MAP.md for the visual system overview. Use the prompt templates as SOPs.

## Quick Start

### For AI Agents

1. Read this file (SYSTEM_README.md)
2. Read ARCHITECTURE_MAP.md for system topology
3. Load `01_governance/shared_context/audience-product.md` — fill in your brand's specifics using the {PLACEHOLDER} template
4. Load `01_governance/shared_context/brand-voice.md` — adapt to your brand
5. Choose your workflow from `04_prompt_templates/` and follow it

### For Humans

1. Read ARCHITECTURE_MAP.md — understand the system visually
2. Browse `06_examples/honest_herbalist/` — see a complete worked example
3. Fill in `01_governance/shared_context/audience-product.md` for your brand
4. Follow the prompt templates in `04_prompt_templates/` as SOPs

## Folder Structure

```
DR_Copywriting_System/
│
├── SYSTEM_README.md          ← You are here
├── ARCHITECTURE_MAP.md       ← Visual system map + dependency graph
│
├── 01_governance/            ← Foundational docs (READ-ONLY source of truth)
│   ├── sections/             ← Core operating docs (S2-S11, SA-SE)
│   ├── shared_context/       ← Loaded by EVERY workflow (parameterized)
│   └── research_artifacts/   ← Example research inputs
│
├── 02_engines/               ← Executable workflow systems
│   ├── headline_engine/      ← Headline generation + scoring (LIVE)
│   ├── promise_contract/     ← Promise enforcement system (LIVE)
│   └── page_templates/       ← Presale + sales page templates (SCHEMAS DEFINED)
│
├── 03_scorers/               ← Python evaluation tools
│   ├── headline_scorer_v2.py ← 29 tests, 44 pts, deterministic
│   ├── headline_body_congruency.py ← 13 tests, 19 pts, promise enforcement
│   ├── headline_qa_loop.py   ← LLM-powered auto-fix
│   └── page_scorers/         ← Page-level scoring tools
│
├── 04_prompt_templates/      ← Reusable execution patterns
│   ├── headline_generation.md
│   ├── advertorial_writing.md
│   ├── sales_page_writing.md
│   ├── promise_contract_extraction.md
│   └── awareness_angle_matrix.md
│
├── 05_schemas/               ← I/O contracts (JSON)
│   ├── headline_input.json
│   ├── headline_output.json
│   ├── presales_listicle.schema.json
│   └── sales_pdp.schema.json
│
├── 06_examples/              ← Complete worked example (The Honest Herbalist)
│   └── honest_herbalist/     ← Headlines, advertorials, sales pages, scores
│
└── 07_roadmap/               ← Future systems (SPECS ONLY, not built)
    ├── VOCC_enhancement/     ← 7 agent specifications
    ├── auto_craft_rules/     ← Craft rule generation spec
    └── ROADMAP_STATUS.md     ← What's built vs. planned
```

## Core Concepts

### The Belief Chain (B1-B8)
Every piece of copy advances specific beliefs along an 8-step chain:
- **Presell (B1-B4):** Problem is real → Problem is urgent → Solution exists → Look at this product
- **Sales page (B5-B8):** Product solves it → Product is for ME → Offer is fair → Buy now

### The Promise Contract
Every headline makes an implicit promise. The system formalizes it into 4 testable fields and enforces delivery with automated scoring. The PC2 test (Delivery Test Satisfied) is a HARD GATE — if the body doesn't pay off the headline's promise, the page fails.

### Awareness-Level Routing
5 awareness levels (Unaware → Problem-Aware → Solution-Aware → Product-Aware → Most-Aware) determine everything: headline formula, lead strategy, agitation ceiling, proof approach, CTA style.

### Deterministic Scoring
All scoring is deterministic (no LLM judgment). The headline scorer runs 29 tests across 4 dimensions. The congruency scorer runs 13 tests with a hard gate. Results are reproducible and auditable.

## Workflow Execution Order

### Full Funnel (Cold Traffic → Purchase)

```
Step 1: Fill in audience-product.md with your brand
Step 2: Generate awareness-angle matrix for your angles
Step 3: Run headline engine → score → extract Promise Contracts
Step 4: Write presell advertorial (B1-B4) governed by Promise Contract
Step 5: Score advertorial with congruency scorer (target: 75%+)
Step 6: Write sales page (B5-B8) governed by Promise Contract
Step 7: Score sales page with congruency scorer (target: 75%+)
Step 8: Generate Word docs for review
```

### Single Page (If You Only Need One Asset)

```
Step 1: Fill in audience-product.md
Step 2: Run headline engine for your page type
Step 3: Extract Promise Contract (Step 4.5)
Step 4: Follow the relevant prompt template
Step 5: Score with congruency scorer
```

## What's Built vs. What's Planned

| System | Status |
|--------|--------|
| Headline Engine | FULLY OPERATIONAL |
| Headline Scorer v2 | FULLY OPERATIONAL |
| Promise Contract System | FULLY OPERATIONAL |
| Congruency Scorer | FULLY OPERATIONAL |
| QA Auto-Fix Loop | FULLY OPERATIONAL |
| I/O Schemas | FULLY OPERATIONAL |
| Foundational Docs (S2-S11, SA-SE) | FULLY OPERATIONAL |
| Shared Context Layer | FULLY OPERATIONAL |
| Prompt Templates | FULLY OPERATIONAL |
| Page Template Schemas | SCHEMAS DEFINED |
| Page-Level Scorers | BUILT (needs integration) |
| VOCC Enhancement (7 agents) | SPECS ONLY |
| Auto Craft Rules Generator | SPEC ONLY |

See `07_roadmap/ROADMAP_STATUS.md` for the complete build status and implementation priority.

## Dependencies

- Python 3.10+ (for scorers)
- python-docx (for Word document generation)
- No external API keys required for scoring (all deterministic)
- LLM API connection required for headline QA loop only

## Getting Started (New Brand)

1. Copy `01_governance/shared_context/audience-product.md` and fill in all {PLACEHOLDER} fields
2. Adapt `01_governance/shared_context/brand-voice.md` to your brand's voice (keep the structure, change the examples and banned/preferred word lists)
3. Add your research artifacts to `01_governance/research_artifacts/`
4. Follow `04_prompt_templates/headline_generation.md` to generate your first headlines
5. Study `06_examples/honest_herbalist/` to see what good output looks like
