# Pipeline Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create all integration specs, handoff templates, and cross-references that connect the four agent systems (Foundational Docs, VOC + Angle Engine, Offer Agent, Copywriting Agent) into a unified, operator-runnable pipeline.

**Architecture:** Documentation-first integration layer. No automation code — structured specs and templates at every system boundary, with cross-references added to each system's existing docs. Refer to the design doc at `docs/plans/2026-02-21-pipeline-integration-design.md` for full architectural context.

**Tech Stack:** Markdown specs, YAML templates, JSON schemas. No runtime dependencies.

---

## Task 1: Create the Angle Selection Handoff Template

**Files:**
- Create: `V2 Fixes/integration/templates/angle_selection.yaml`
- Create: `V2 Fixes/integration/templates/angle_selection_guide.md`

**Why first:** This is the P0 gap. The angle selection handoff is the single most critical human decision point — everything downstream depends on it. Agent 3 outputs 15-30 candidates; the Offer Agent needs exactly one in a specific JSON format. This template bridges the gap.

**Step 1: Create the integration directory structure**

```bash
mkdir -p "V2 Fixes/integration/templates"
mkdir -p "V2 Fixes/integration/specs"
mkdir -p "V2 Fixes/integration/schemas"
```

**Step 2: Create `angle_selection.yaml`**

This is the template the operator fills after reviewing Agent 3's output. Every field maps directly to either an Agent 3 output field or an Offer Agent input field.

```yaml
# angle_selection.yaml
# =====================
# PURPOSE: Bridge between Agent 3 (Shadow Angle Clusterer) output
#          and Offer Agent pipeline input.
#
# WHEN TO FILL: After reviewing Agent 3's ranked Purple Ocean angle
#               candidates and selecting one for offer construction.
#
# HOW TO FILL: Copy values directly from Agent 3's output. Do not
#              rephrase or summarize — use the exact text from the
#              angle primitive and evidence assembly.
#
# DOWNSTREAM: This file is consumed by the Offer Agent's
#             pipeline-orchestrator as the `selected_angle` input.

selected_angle:
  # === FROM AGENT 3 ANGLE PRIMITIVE ===
  angle_id: ""              # e.g., "A04" — from Agent 3's ANGLE_ID
  angle_name: ""            # e.g., "The Dosage Gap" — from ANGLE_NAME

  definition:
    who: ""                 # Copy from WHO field in angle primitive
    pain_desire: ""         # Combine PAIN + DESIRED OUTCOME fields
    mechanism_why: ""       # Copy from MECHANISM field
    belief_shift:
      before: ""            # Copy from BELIEF SHIFT → BEFORE
      after: ""             # Copy from BELIEF SHIFT → AFTER
    trigger: ""             # Copy from TRIGGER field

  # === FROM AGENT 3 EVIDENCE ASSEMBLY ===
  evidence:
    supporting_voc_count: 0 # From observation sheet: supporting_voc_count
    top_quotes:             # Top 5 from Evidence Assembly → Supporting Evidence Block
      - voc_id: ""
        quote: ""
        adjusted_score: 0
      - voc_id: ""
        quote: ""
        adjusted_score: 0
      - voc_id: ""
        quote: ""
        adjusted_score: 0
      - voc_id: ""
        quote: ""
        adjusted_score: 0
      - voc_id: ""
        quote: ""
        adjusted_score: 0
    triangulation_status: ""    # SINGLE / DUAL / MULTI
    velocity_status: ""         # ACCELERATING / STEADY / DECELERATING
    contradiction_count: 0

  # === FROM AGENT 3 HOOK STARTERS ===
  hook_starters:
    - visual: ""
      opening_line: ""
      lever: ""
    - visual: ""
      opening_line: ""
      lever: ""
    - visual: ""
      opening_line: ""
      lever: ""

  # === FROM AGENT 3 COMPLIANCE BLOCK ===
  compliance:
    green_count: 0
    yellow_count: 0
    red_count: 0
    overall_risk: ""            # GREEN / YELLOW / RED
    expressible_without_red: true
    requires_disease_naming: false
    platform_notes: ""

  # === FROM AGENT 3 DIFFERENTIATION MAP ===
  purple_ocean_context:
    saturated_angles:
      - name: ""
        competitors_using: []
        hook_pattern: ""
    differentiation_summary: ""
    minimum_distinctiveness: 0  # Minimum dimensions different from closest saturated angle

# === OPERATOR FILLS ===
selection_rationale: ""         # Why you chose this angle over others
selection_date: ""              # YYYY-MM-DD
```

**Step 3: Create `angle_selection_guide.md`**

Write a short guide (max 2 pages) that tells the operator:
1. Where to find each field in Agent 3's output
2. How to evaluate which angle to select (decision criteria from Agent 3's Decision Readiness Block)
3. Common mistakes (e.g., picking the highest-scored angle without checking compliance, ignoring contradiction count)
4. How to pass the completed file to the Offer Agent

The guide should include a field-by-field reference table:

```markdown
| Template Field | Find It In Agent 3 Output | Section |
|---------------|--------------------------|---------|
| `angle_id` | Angle Primitive → ANGLE_ID | Section 3: Candidate Angle Profiles |
| `angle_name` | Angle Primitive → ANGLE_NAME | Section 3 |
| `definition.who` | Angle Primitive → WHO | Section 3 |
| ... | ... | ... |
```

**Step 4: Verify the template maps to the Offer Agent's expected input**

Cross-reference every field in `angle_selection.yaml` against the Offer Agent's `pipeline-orchestrator.md` input schema (lines 24-64). Confirm:

- `selected_angle.angle_name` → `selected_angle.angle_name` (match)
- `selected_angle.definition.who` → `selected_angle.angle_definition.who` (match)
- `selected_angle.definition.pain_desire` → `selected_angle.angle_definition.pain_desire` (match)
- `selected_angle.definition.mechanism_why` → `selected_angle.angle_definition.mechanism_why` (match)
- `selected_angle.definition.belief_shift` → `selected_angle.angle_definition.belief_shift` (needs note: template has before/after sub-fields, Offer Agent expects a single string — operator should combine as "BEFORE → AFTER")
- `selected_angle.definition.trigger` → `selected_angle.angle_definition.trigger` (match)
- `selected_angle.evidence.top_quotes` → `selected_angle.angle_evidence` (transform: extract quote strings)
- `selected_angle.hook_starters` → `selected_angle.angle_hooks` (transform: extract opening_line strings)

Document any transformations needed in the guide.

---

## Task 2: Create the Translation Layer Spec (Foundational Docs → VOC + Angle Engine)

**Files:**
- Create: `V2 Fixes/integration/specs/translation-layer.md`

**Why:** P0 gap. Without this, the operator has to guess which outputs from Stage 1 correspond to which inputs in Stage 2B.

**Step 1: Write the translation layer spec**

The spec must contain:

**Section A: Variable Mapping Table**

| VOC+Angle Engine Agent | Input Variable | Source (Foundational Docs) | Transformation |
|----------------------|---------------|--------------------------|----------------|
| Agent 0 (Habitat Strategist) | `PRODUCT_BRIEF` | `BUSINESS_CONTEXT_JSON` + `CATEGORY_NICHE` from Step 01 | Add `category_niche`, `market_maturity_stage`, `primary_icps` extracted from STEP1_CONTENT |
| Agent 0 | `AVATAR_BRIEF` | `STEP6_SUMMARY` (primary) + key sections of `STEP6_CONTENT` | Direct pass-through. Use STEP6_SUMMARY if STEP6_CONTENT exceeds token limits. |
| Agent 0 | `COMPETITOR_RESEARCH` | `STEP1_SUMMARY` + `STEP1_CONTENT` | Direct pass-through |
| Agent 0 | `COMPETITOR_ANALYSIS_JSON` | `competitor_analysis.json` from Stage 2A | Direct pass-through |
| Agent 0b (Video Strategist) | `PRODUCT_BRIEF` | Same as Agent 0 | Same as Agent 0 |
| Agent 0b | `AVATAR_BRIEF` | Same as Agent 0 | Same as Agent 0 |
| Agent 0b | `COMPETITOR_ANALYSIS` | Same as Agent 0 COMPETITOR_ANALYSIS_JSON | Same |
| Agent 0b | `PRODUCT_CATEGORY_KEYWORDS` | Extract from `CATEGORY_NICHE` + keyword clusters in `STEP1_CONTENT` | Parse comma-separated keyword list from competitor research |
| Agent 2 (VOC Extractor) | `Product Brief` | Same as Agent 0 PRODUCT_BRIEF | Same |
| Agent 2 | `Avatar Summary` | `STEP6_SUMMARY` | Direct pass-through |
| Agent 2 | `Existing VOC Corpus` (DUAL MODE) | `STEP4_CONTENT` | **Transformation required** — see Section B |
| Agent 2 | `Known Saturated Angles` | `competitor_analysis.json` → `saturation_map` | Extract angle names where status = SATURATED |
| Agent 3 (Shadow Angle Clusterer) | `Competitor Angle Map` | `competitor_analysis.json` → `asset_observation_sheets` + `saturation_map` | Restructure into Agent 3's expected format: competitor names, URLs, hooks/headlines, target segments, mechanisms, proof types |
| Agent 3 | `Known Saturated Angles` | Same extraction as Agent 2 | Same |
| Agent 3 | `Product Brief` | Same as Agent 0 | Same |
| Agent 3 | `Avatar Brief` | Same as Agent 0 | Same |

**Section B: VOC Corpus Transformation (STEP4_CONTENT → Agent 2 DUAL MODE)**

Copy the transformation rules from the design doc Section 5, including:
- Source format (Foundational Docs tagged quote bank schema)
- Target format (Agent 2 VOC Record)
- Field-by-field mapping rules
- Category A-I → 8 Core Dimensions mapping table
- Note: Observation sheets are NOT filled during transformation — Agent 2 fills these

**Section C: Enriching the Product Brief**

Document the specific fields to extract from STEP1_CONTENT to enrich the seed Product Brief:
- `category_niche`: from Step 01 output header
- `market_maturity_stage`: from Step 01's market stage assessment
- `primary_icps`: from Step 06's ranked segments
- `positioning_gaps`: from Step 01's positioning gap analysis

Include example extraction patterns (e.g., "Look for the section titled 'Market Maturity Assessment' in STEP1_CONTENT").

---

## Task 3: Create the Offer Agent Input Mapping Spec

**Files:**
- Create: `V2 Fixes/integration/specs/offer-agent-input-mapping.md`

**Why:** P1 gap — resolves information asymmetry (Gap 6). The Offer Agent needs the right granularity of data from the VOC + Angle Engine.

**Step 1: Write the input mapping spec**

For each of the Offer Agent's 5 inputs (from `pipeline-orchestrator.md` lines 22-64), document:

**Input 1: `product_brief`**
- Source: Seed input `BUSINESS_CONTEXT_JSON` enriched through Stages 1-2
- Map fields:
  - `name` ← seed `product_name`
  - `description` ← seed `description`
  - `category` ← Stage 1 `CATEGORY_NICHE`
  - `price_cents` ← seed `price` (convert to cents)
  - `currency` ← default "USD" or extract from seed
  - `business_model` ← operator must specify (not in upstream outputs)
  - `funnel_position` ← operator must specify
  - `target_platforms` ← operator must specify
  - `target_regions` ← operator must specify
  - `product_customizable` ← seed `product_customizable`
  - `constraints.compliance_sensitivity` ← derive from `competitor_analysis.json` compliance landscape
  - `constraints.existing_proof_assets` ← operator must specify
  - `constraints.brand_voice_notes` ← operator must specify

**Input 2: `selected_angle`**
- Source: `angle_selection.yaml` (from Task 1)
- Map fields:
  - `angle_name` ← `selected_angle.angle_name`
  - `angle_definition.who` ← `selected_angle.definition.who`
  - `angle_definition.pain_desire` ← `selected_angle.definition.pain_desire`
  - `angle_definition.mechanism_why` ← `selected_angle.definition.mechanism_why`
  - `angle_definition.belief_shift` ← combine `before` + " → " + `after`
  - `angle_definition.trigger` ← `selected_angle.definition.trigger`
  - `angle_evidence` ← extract quote strings from `selected_angle.evidence.top_quotes[]`
  - `angle_hooks` ← extract `opening_line` strings from `selected_angle.hook_starters[]`

**Input 3: `provided_research.competitor_teardowns`**
- Source: `competitor_analysis.json` (full) + relevant sections of `STEP1_CONTENT`
- What to include:
  - All asset observation sheets from competitor_analysis.json
  - Saturation map (angle x driver matrix)
  - Whitespace map
  - Messaging pattern distributions
  - Relevant competitor profiles from STEP1_CONTENT (positioning, pricing, proof types)
- What to exclude:
  - Raw prior declarations (internal to competitor analyzer)
  - Disconfirmation sections (internal audit)

**Input 4: `provided_research.voc_research`**
- Source: Agent 2 handoff block — **filtered to selected angle**
- Filtering rules:
  - Include: all VOC items in the selected angle's cluster (Agent 3 lists these by VOC ID)
  - Include: all VOC items with matching trigger event category
  - Include: all VOC items with matching pain domain
  - Include: all contradiction/limiting items for the selected angle
  - Include: Language Registry entries relevant to the angle's pain/identity/enemy dimensions
  - Include: Purchase barriers that relate to the angle's segment
- Target: 40-80 items (not the full 200+ corpus)
- Format: VOC Record format with observation sheets intact

**Input 5: `provided_research.purple_ocean_research`**
- Source: Agent 3 handoff block (full)
- What to include:
  - All angle primitives (not just selected — Offer Agent benefits from seeing alternatives)
  - Saturated angle summary
  - Overlap matrix
  - Decision readiness block
  - Orphan signals (may inform offer construction)
- Rationale: The Offer Agent's Step 2 (Market Calibration) needs the full competitive context, not just the selected angle.

**Step 2: Flag operator-specified fields**

List all fields that NO upstream system produces — these must be specified by the operator at Stage 3 entry:
- `business_model`
- `funnel_position`
- `target_platforms`
- `target_regions`
- `constraints.existing_proof_assets`
- `constraints.brand_voice_notes`

Recommend adding these to the seed input schema (Stage 0) so they're captured upfront.

---

## Task 4: Create the Offer-to-Copy Bridge Spec

**Files:**
- Create: `V2 Fixes/integration/specs/offer-to-copy-bridge.md`

**Why:** P1 gap — resolves Gaps 4 and 9 (Offer → Copywriting population + belief architecture alignment).

**Step 1: Write the population guide**

Map every `{PLACEHOLDER}` field in `audience-product.md` to its source in the Offer Agent's output.

Reference the actual template at `Copywriting Agent — Final/01_governance/shared_context/audience-product.md`.

```markdown
## audience-product.md Population Guide

### Target Audience Summary

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{BRAND_NAME}` | Seed input | `product_brief.name` |
| `{TARGET_AGE_RANGE}` | Offer Agent Step 1 | Avatar Brief → Demographics section |
| `{EXTENDED_AGE_RANGE}` | Offer Agent Step 1 | Avatar Brief → Demographics section |
| `{GENDER_SKEW}` | Offer Agent Step 1 | Avatar Brief → Demographics section |
| `{PRIMARY_MARKETS}` | Operator or seed input | `product_brief.target_regions` |
| `{BUDGET_RANGE}` | Offer Agent Step 1 or seed | Infer from price point |
| `{PROFESSIONAL_BACKGROUNDS}` | Offer Agent Step 1 | Avatar Brief → Psychographic section |
| `{PSYCHOGRAPHIC_IDENTITY_1-5}` | Offer Agent Step 1 | Avatar Brief → Identity markers |
| `{EMOTIONAL_DRIVER_1-3}` | Offer Agent Step 1 | Avatar Brief → Emotional drivers |
| `{KEY_MINDSET_DESCRIPTION}` | Offer Agent Step 1 | Avatar Brief → Mindset/worldview section |

### Pain Points

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{PAIN_POINT_1-3_TITLE}` | Offer Agent Step 1 + VOC | Avatar Brief → Pain points (ranked by intensity) |
| `{PAIN_1-3_DETAIL_A-C}` | Agent 2 VOC corpus | Top VOC items per pain dimension |
| `{EMOTIONAL_FEAR_1-3}` | Offer Agent Step 1 | Avatar Brief → Fear hierarchy |

### Goals & Aspirations

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{SHORT_TERM_GOAL_1-3}` | Offer Agent Step 1 | Avatar Brief → Desired outcomes (immediate) |
| `{LONG_TERM_GOAL_1-3}` | Offer Agent Step 1 | Avatar Brief → Desired outcomes (identity-level) |

### Product Summary

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{PRODUCT_NAME}` | Seed input | `product_brief.name` |
| `{PRICE_POINT}` | Seed/Offer Agent | `product_brief.price_cents` or Final Offer Doc pricing |
| `{PRODUCT_FORMAT}` | Offer Agent Step 4 | Final Offer Doc → format |
| `{PRODUCT_POSITIONING}` | Offer Agent Step 2 | Market Calibration → positioning statement |
| `{CORE_CONTENT_1-7}` | Offer Agent Step 4 | Final Offer Doc → value stack components |
| `{BONUS_1-4_NAME/DESCRIPTION}` | Offer Agent Step 4 | Final Offer Doc → bonus stack |
| `{GUARANTEE_TERMS}` | Offer Agent Step 4 | Final Offer Doc → guarantee section |
| `{UMP_TITLE/DESCRIPTION}` | Offer Agent Step 3 | Selected UMP pair |
| `{UMS_TITLE}` / `{UMS_COMPONENT_1-5}` | Offer Agent Step 3 | Selected UMS pair |

### Belief Chain

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{BELIEF_1-5}` | Offer Agent Step 4 Phase 10 | Belief cascade → map to B1-B5 per bridge table |

### Awareness & Sophistication

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{CONSCIOUSNESS_LEVEL}` | Offer Agent Step 2 | Market Calibration output |
| `{AWARENESS_LEVEL}` | Offer Agent Step 2 | Market Calibration → primary awareness level |
| `{SOPHISTICATION_STAGE}` | Offer Agent Step 2 | Market Calibration → sophistication level |

### Objections

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{OBJECTION_CATEGORY_1-6}` | Offer Agent Step 4 | Final Offer Doc → objection handling section |

### Audience Voice

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{VOC_QUOTE_1-6}` | Agent 2 corpus (filtered) | Top 6 headline-ready quotes from selected angle cluster |
```

**Step 2: Write the belief architecture mapping**

```markdown
## Belief Cascade → B1-B5 Mapping

The Offer Agent's belief cascade (Step 4, Phase 10) identifies the
sequence of beliefs a buyer must hold. The Copywriting Agent's
audience-product.md uses B1-B5 to structure copy sections.

### Mapping Table

| Offer Agent Belief Cascade Element | Copy B# | Copy Section | What Copy Must Do |
|-----------------------------------|---------|-------------|-------------------|
| "The problem is real and getting worse" | B1 | Presell: Sections 1-2 | Validate the reader's pain, make it tangible |
| "The problem has a hidden root cause" | B2 | Presell: Sections 2-3 | Introduce UMP — reframe the problem |
| "A solution category exists that addresses the root cause" | B3 | Presell: Sections 3-4 | Bridge from UMP to UMS territory |
| "This specific product is the best version of that solution" | B4 | Presell: Section 5, Sales: Sections 1-4 | Introduce UMS, product, mechanism |
| "The offer is fair and I should act now" | B5 | Sales: Sections 5-12 | Value stack, proof, guarantee, CTA |

### How to Apply

When populating `{BELIEF_1}` through `{BELIEF_5}`:
1. Read the Offer Agent's belief cascade output (Step 4, Phase 10)
2. Map each cascade element to the closest B# per the table above
3. Use the Offer Agent's exact wording — do not rephrase
4. If the cascade has more than 5 elements, combine adjacent beliefs
5. If fewer than 5, split the broadest belief into sub-beliefs
```

**Step 3: Document compliance context transfer**

```markdown
## Compliance Context Transfer

### Sources
1. Agent 3 compliance block (per-angle)
2. Competitor Asset Analyzer compliance landscape
3. Offer Agent compliance flags

### Target
`01_governance/shared_context/compliance.md` (if this file exists) or
create new file with:

- Overall compliance risk level for this angle
- RED flag patterns to avoid (from competitor analysis)
- Platform-specific compliance notes (Meta, TikTok, YouTube)
- Prohibited language list (from all upstream compliance gates)
- Approved reframes for borderline claims
```

---

## Task 5: Create the Product Brief Evolution Schema

**Files:**
- Create: `V2 Fixes/integration/schemas/product_brief_stage0.json`
- Create: `V2 Fixes/integration/schemas/product_brief_stage1.json`
- Create: `V2 Fixes/integration/schemas/product_brief_stage2.json`
- Create: `V2 Fixes/integration/schemas/product_brief_stage3.json`
- Create: `V2 Fixes/integration/schemas/product_brief_evolution.md`

**Why:** P1 gap — ensures the Product Brief grows cleanly through stages without data loss.

**Step 1: Create each stage's JSON schema**

Each schema should be valid JSON Schema (draft-07) that:
- Defines all fields for that stage
- Marks inherited fields as required
- Marks new fields with descriptions of where they come from
- Includes `"stage"` as a required integer field

Use the schemas from the design doc Section 6 as the source.

**Step 2: Create the evolution guide**

`product_brief_evolution.md` should document:
- Which pipeline stage adds which fields
- Which system is responsible for populating each field
- Which fields are operator-specified vs. system-generated
- A worked example showing a Product Brief at each stage

---

## Task 6: Create the Master Run Book

**Files:**
- Create: `V2 Fixes/integration/RUNBOOK.md`

**Why:** P0 gap — this is the operator-facing document that ties everything together.

**Step 1: Write the run book**

Structure:

```markdown
# Agentic Marketing Pipeline — Operator Run Book

## Quick Start
[5-sentence overview of the full pipeline]

## Prerequisites
- Access to an LLM that supports long context (Claude, GPT-4, etc.)
- Apify account (for VOC + Angle Engine scraping)
- Python 3.10+ (for scoring tools)
- 3+ competitor marketing assets collected

## Stage 0: Seed Input
### What You Do
[Fill in 5 fields + any additional operator-specified fields]

### Template
[Link to product_brief_stage0.json]

### Checklist
- [ ] Product name filled
- [ ] Description is 1-3 sentences, not marketing copy
- [ ] Price specified or marked TBD
- [ ] At least 2 competitor URLs provided
- [ ] product_customizable flag set correctly

---

## Stage 1: Foundational Research
### What You Do
[Run 4 prompts in sequence]

### Prompts to Run (in order)
1. `Foundational Docs Prompts/clean_prompts/01_competitor_research_v2.md`
2. `Foundational Docs Prompts/clean_prompts/03_deep_research_meta_prompt_v2.md`
3. Execute the meta-prompt output (STEP4_PROMPT) with a web-access agent
4. `Foundational Docs Prompts/clean_prompts/06_avatar_brief_v2.md`

### Inputs for Each Prompt
[Exact variable names and where to paste them]

### Quality Checks
- [ ] STEP1 identifies 3+ competitors
- [ ] STEP4 covers 5+ of 9 VOC categories
- [ ] STEP6 identifies 3+ buyer segments

### Save Your Outputs
[Exact filenames and locations to save each output]

---

## Stage 2A: Competitor Asset Collection & Analysis
### What You Do
[Collect assets, run Competitor Asset Analyzer]

### How to Collect Assets
[Guidance on where to find competitor ads, landing pages, etc.]

### Prompt to Run
`VOC + Angle Engine (2-21-26)/prompts/agent-pre-competitor-asset-analyzer.md`

### Inputs
[Reference translation-layer.md for exact mappings]

### Save Your Output
Save as `competitor_analysis.json`

---

## Stage 2B: VOC + Angle Discovery
### What You Do
[Run 6 agents + 4 scoring scripts in sequence]

### Prompts to Run (in order)
1. Agent 0: `VOC + Angle Engine (2-21-26)/prompts/agent-00-habitat-strategist.md`
   - Parallel: Agent 0b: `agent-00b-social-video-strategist.md`
2. [Run Apify scrapers with configs from Agent 0 + 0b]
3. [Run `score_virality.py` on video data if applicable]
4. Agent 1: `agent-01-habitat-qualifier.md`
5. [Run `score_habitats.py`]
6. Agent 2: `agent-02-voc-extractor.md` — USE DUAL MODE
7. [Run `score_voc.py`]
8. Agent 3: `agent-03-shadow-angle-clusterer.md`
9. [Run `score_angles.py`]

### Input Mapping
[Reference translation-layer.md — exact table of what goes where]

### Quality Checks
- [ ] Agent 1: 8+ qualified habitats
- [ ] Agent 2: 200+ VOC items, 3+ habitat types
- [ ] Agent 3: 5+ candidate angles with 5+ supporting items each

---

## Human Decision: Select Your Angle
### What You Do
[Review Agent 3's output, fill angle_selection.yaml]

### Decision Criteria
[From Agent 3's Decision Readiness Block]

### Template
[Link to angle_selection.yaml + guide]

### Checklist
- [ ] Angle has 10+ supporting VOC items (strong) or 5+ (acceptable)
- [ ] Triangulation is DUAL or MULTI source
- [ ] Compliance is expressible without RED claims
- [ ] At least 3 dimensions different from closest saturated angle
- [ ] Velocity is ACCELERATING or STEADY (not DECELERATING)

---

## Stage 3: Offer Architecture
### What You Do
[Run 5-step Offer Agent pipeline]

### Prompt to Run
`Offer Agent — Final/prompts/pipeline-orchestrator.md`
(orchestrates Steps 1-5 automatically)

### Inputs
[Reference offer-agent-input-mapping.md for exact field mapping]

### Human Decision Points
- Step 3: Select UMP/UMS pair (from 3-5 candidates)
- Step 5: Select offer variant (from base + 2-3 variants)

### Quality Checks
- [ ] Calibration consistency checker passes
- [ ] Composite score >= 5.5
- [ ] Belief cascade covers all 5 awareness levels

---

## Bridge: Populate Copywriting Shared Context
### What You Do
[Fill audience-product.md using Offer Agent outputs]

### Guide
[Reference offer-to-copy-bridge.md for exact field mapping]

### Files to Create/Update
1. `Copywriting Agent — Final/01_governance/shared_context/audience-product.md`
2. `Copywriting Agent — Final/01_governance/shared_context/awareness-angle-matrix.md`
3. `Copywriting Agent — Final/01_governance/shared_context/brand-voice.md` (operator configures)
4. `Copywriting Agent — Final/01_governance/shared_context/compliance.md` (if needed)

### Checklist
- [ ] All {PLACEHOLDER} fields in audience-product.md are filled
- [ ] awareness-angle-matrix.md placed from Offer Agent Step 2 output
- [ ] B1-B5 beliefs mapped from belief cascade
- [ ] VOC quotes are real (from corpus), not invented

---

## Stage 4: Copy Execution
### What You Do
[Run Copywriting Agent workflows]

### System
`Copywriting Agent — Final/SYSTEM_README.md` (follow its instructions)

### Key Workflows
1. Headline Engine → deterministic scoring
2. Promise Contracts → from winning headlines
3. Presell Advertorial → congruency scoring
4. Sales Page → congruency scoring
5. QA auto-fix loop for failing assets

### Quality Checks
- [ ] Headlines score B-tier+ (28+ points)
- [ ] Presell congruency passes 75%+
- [ ] Sales page congruency passes 75%+
- [ ] PC2 hard gate passes

---

## Error Recovery

[Copy error recovery table from design doc Section 9]

---

## Appendix: File Map

[Complete list of all files created/referenced by this pipeline]
```

---

## Task 7: Add Deprecation Notices

**Files:**
- Modify: `V2 Fixes/Foundational Docs Prompts/downstream/07_offer_brief_v2.md` (lines 1-3)
- Modify: `V2 Fixes/Foundational Docs Prompts/downstream/08_belief_architecture_v2.md` (lines 1-3)

**Step 1: Add deprecation header to `07_offer_brief_v2.md`**

Prepend to the top of the file:

```markdown
> **DEPRECATED (2026-02-21):** This prompt is superseded by the Offer Agent
> pipeline (`Offer Agent — Final/`). See `integration/RUNBOOK.md` Stage 3
> for the replacement workflow. This file is preserved for reference only.

---

```

**Step 2: Add deprecation header to `08_belief_architecture_v2.md`**

Same pattern:

```markdown
> **DEPRECATED (2026-02-21):** This prompt is superseded by the Offer Agent
> Step 4 Phase 10 (belief cascade) + Copywriting Agent B1-B5 belief chain.
> See `integration/specs/offer-to-copy-bridge.md` for the replacement.
> This file is preserved for reference only.

---

```

---

## Task 8: Add Cross-References to Each System's Docs

**Files:**
- Modify: `V2 Fixes/Foundational Docs Prompts/README.md` — add "Downstream Integration" section
- Modify: `V2 Fixes/VOC + Angle Engine (2-21-26)/docs/` — add integration reference
- Modify: `V2 Fixes/Offer Agent — Final/00-START-HERE.md` — add "Upstream Sources" section
- Modify: `V2 Fixes/Copywriting Agent — Final/UPSTREAM-INTEGRATION.md` — add full pipeline reference

**Step 1: Add downstream section to Foundational Docs README.md**

Append a section:

```markdown
## Downstream Integration

This pipeline's outputs feed the VOC + Angle Engine and Offer Agent.
See `integration/specs/translation-layer.md` for exact variable mappings.

### Output → Consumer Map
| Output | Consumer |
|--------|----------|
| `STEP1_SUMMARY/CONTENT` | VOC + Angle Engine (Agent 0 `COMPETITOR_RESEARCH`) |
| `STEP4_SUMMARY/CONTENT` | VOC + Angle Engine (Agent 2 existing VOC corpus — DUAL MODE) |
| `STEP6_SUMMARY/CONTENT` | VOC + Angle Engine (Agent 0/0b/1/2/3 `AVATAR_BRIEF`) |
| `CATEGORY_NICHE` | VOC + Angle Engine (Agent 0b `PRODUCT_CATEGORY_KEYWORDS`) |

### Deprecated Downstream Prompts
- `downstream/07_offer_brief_v2.md` — replaced by Offer Agent
- `downstream/08_belief_architecture_v2.md` — replaced by Offer Agent + Copywriting Agent
```

**Step 2: Add upstream section to Offer Agent 00-START-HERE.md**

Append a section:

```markdown
## Upstream Sources

All inputs to this pipeline come from upstream systems:

| Input | Source System | Reference |
|-------|-------------|-----------|
| `product_brief` | Seed input + Stage 1 enrichments | `integration/schemas/product_brief_stage2.json` |
| `selected_angle` | VOC + Angle Engine → Human selection | `integration/templates/angle_selection.yaml` |
| `competitor_teardowns` | Competitor Asset Analyzer + Foundational Docs | `integration/specs/offer-agent-input-mapping.md` |
| `voc_research` | VOC + Angle Engine Agent 2 (filtered) | `integration/specs/offer-agent-input-mapping.md` |
| `purple_ocean_research` | VOC + Angle Engine Agent 3 | `integration/specs/offer-agent-input-mapping.md` |

See `integration/RUNBOOK.md` for the full end-to-end pipeline.
```

**Step 3: Extend Copywriting Agent UPSTREAM-INTEGRATION.md**

Add a section at the end:

```markdown
## Full Pipeline Context

This system is Stage 4 of a 5-stage pipeline:

```
Stage 0: Seed Input
Stage 1: Foundational Research (Foundational Docs Pipeline)
Stage 2: Competitor Analysis + VOC + Angle Discovery
Stage 3: Offer Architecture (Offer Agent) ← produces inputs for this system
Stage 4: Copy Execution (THIS SYSTEM)
```

### Complete Input Sources

| Shared Context File | Primary Source | Secondary Source |
|--------------------|---------------|-----------------|
| `audience-product.md` | Offer Agent Steps 1, 3, 4 | Agent 2 VOC corpus (quotes) |
| `awareness-angle-matrix.md` | Offer Agent Step 2 Phase 7 | (can be generated standalone) |
| `brand-voice.md` | Operator configuration | — |
| `compliance.md` | All upstream compliance gates | — |

See `integration/specs/offer-to-copy-bridge.md` for exact field mappings.
See `integration/RUNBOOK.md` for the full end-to-end pipeline.
```

---

## Dependency Map

```
Task 1 (Angle Selection Template) ← no dependencies, start here
Task 2 (Translation Layer) ← no dependencies, can parallel with Task 1
Task 3 (Offer Agent Input Mapping) ← depends on Task 1 (references angle_selection.yaml)
Task 4 (Offer-to-Copy Bridge) ← no dependencies on Tasks 1-3
Task 5 (Product Brief Schema) ← no dependencies
Task 6 (Run Book) ← depends on Tasks 1-5 (references all specs)
Task 7 (Deprecation Notices) ← no dependencies
Task 8 (Cross-References) ← depends on Tasks 1-6 (references integration files)
```

**Recommended execution order:**
- **Parallel batch 1:** Tasks 1, 2, 4, 5, 7 (all independent)
- **Sequential:** Task 3 (after Task 1)
- **Sequential:** Task 6 (after Tasks 1-5)
- **Sequential:** Task 8 (after Task 6)
