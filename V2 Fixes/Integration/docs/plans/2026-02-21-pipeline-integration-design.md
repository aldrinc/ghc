# Pipeline Integration Design — Agentic Marketing Division

**Version:** 1.0
**Date:** February 21, 2026
**Status:** Approved — ready for implementation planning
**Approach:** B — Integration Specs + Handoff Templates + Schema Unification

---

## 1. Executive Summary

This document defines the integration architecture that connects four standalone agent systems into a unified, end-to-end agentic marketing pipeline:

1. **Foundational Docs Pipeline** — competitive research + VOC + buyer segments
2. **VOC + Angle Engine** — structured scraping, VOC extraction, Purple Ocean angle discovery
3. **Offer Agent** — offer architecture, scoring, stress-testing
4. **Copywriting Agent** — headlines, advertorials, sales pages, deterministic scoring

**Relationship:** Sequential. Each system's output feeds the next. The Foundational Docs pipeline runs first, the Copywriting Agent runs last.

**Key Design Decision:** The downstream prompt templates (`07_offer_brief_v2.md`, `08_belief_architecture_v2.md`) in the Foundational Docs folder are **deprecated** — replaced by the full Offer Agent system.

---

## 2. Master Pipeline Architecture

```
STAGE 0: SEED INPUT
  ├── Input: 5 fields
  ├── Output: BUSINESS_CONTEXT, BUSINESS_CONTEXT_JSON
  └── Human: Fill seed data
       │
       ▼
STAGE 1: FOUNDATIONAL RESEARCH
  ├── System: Foundational Docs Pipeline
  ├── Steps: 01 Competitor → 03 Meta-Prompt → 04 Deep Research → 06 Avatar Brief
  ├── Output: STEP1_SUMMARY/CONTENT, STEP4_SUMMARY/CONTENT, STEP6_SUMMARY/CONTENT
  └── Human: Review research quality, proceed
       │
       ├───────────────────────────────┐
       ▼                               ▼
STAGE 2A: COMPETITOR ASSETS       STAGE 2B: VOC + ANGLE DISCOVERY
  ├── Human: Collect 3+ assets     ├── System: VOC + Angle Engine
  ├── Agent: Competitor Asset       │   ├── Agent 0: Habitat Strategist
  │   Analyzer                      │   ├── Agent 0b: Video Strategist
  ├── Output: competitor_           │   ├── [Apify Execution Layer]
  │   analysis.json                 │   ├── Agent 1: Habitat Qualifier
  └── Feeds into 2B                 │   ├── Agent 2: VOC Extractor (DUAL MODE)
       │                            │   └── Agent 3: Shadow Angle Clusterer
       └──────┬─────────────────────┘
              │
              ▼
       HUMAN DECISION: SELECT ANGLE
       (Uses angle_selection.yaml template)
              │
              ▼
STAGE 3: OFFER ARCHITECTURE
  ├── System: Offer Agent (5-step pipeline)
  ├── Human: Select UMP/UMS (Step 3), Select variant (Step 5)
  ├── Output: Final Offer Doc, Awareness-Angle-Matrix, metadata
  └── Bridge: Populate Copywriting shared context
       │
       ▼
STAGE 4: COPY EXECUTION
  ├── System: Copywriting Agent
  ├── Steps: Headlines → Promise Contracts → Advertorials → Sales Pages → Scoring
  └── Output: Scored copy assets
```

---

## 3. Stage Definitions

### Stage 0: Seed Input

**Input Schema:**

```json
{
  "product_name": "string — required",
  "description": "string — required — 1-3 sentences",
  "price": "string — required if known — e.g., '$49 one-time'",
  "competitor_urls": "string[] — optional — known competitor URLs",
  "product_customizable": "boolean — required — can downstream pipelines recommend format/bundle/pricing changes?"
}
```

**Derived Variables:**
- `BUSINESS_CONTEXT` = product name + description composed into 1-sentence context
- `BUSINESS_CONTEXT_JSON` = structured JSON of all 5 fields

**Validation:** All 5 fields must be present. If `price` is unknown, mark as "TBD" and flag for enrichment after Stage 1.

---

### Stage 1: Foundational Research

**System:** Foundational Docs Pipeline (`clean_prompts/`)

**Execution Order:**
1. `01_competitor_research_v2.md` → `STEP1_SUMMARY`, `STEP1_CONTENT`, `CATEGORY_NICHE`
2. `03_deep_research_meta_prompt_v2.md` → `STEP4_PROMPT`
3. Execute `STEP4_PROMPT` with web-access agent → `STEP4_SUMMARY`, `STEP4_CONTENT`
4. `06_avatar_brief_v2.md` → `STEP6_SUMMARY`, `STEP6_CONTENT`

**Quality Gates:**
- STEP1 must identify at least 3 validated competitors
- STEP4 must produce VOC data in at least 5 of 9 research categories
- STEP6 must identify at least 3 buyer segments with differentiation test passing

**Output Manifest:**

| Output Variable | Format | Size | Consumed By |
|----------------|--------|------|-------------|
| `STEP1_SUMMARY` | Markdown (500 words max) | ~500 words | Stage 2A, Stage 2B |
| `STEP1_CONTENT` | Markdown (full) | ~10-20K words | Stage 2A, Stage 2B |
| `STEP4_SUMMARY` | Markdown (500 words max) | ~500 words | Stage 2B |
| `STEP4_CONTENT` | Markdown (full) | ~30-50K words | Stage 2B (Agent 2 DUAL MODE) |
| `STEP6_SUMMARY` | Markdown (400 words max) | ~400 words | Stage 2B, Stage 3 |
| `STEP6_CONTENT` | Markdown (full) | ~15-25K words | Stage 2B, Stage 3 |
| `CATEGORY_NICHE` | String | 1 line | Stage 2B |

---

### Stage 2A: Competitor Asset Analysis

**Prerequisite:** Stage 1 complete (need competitor names + URLs from STEP1)

**Human Action:** Collect 3+ competitor marketing assets (ad copy, landing pages, ad images, video ads)

**System:** Pre-Pipeline Competitor Asset Analyzer

**Input Mapping:**

| Agent Input | Source |
|-------------|--------|
| `COMPETITOR_ASSETS` | Human-collected assets |
| `PRODUCT_BRIEF` | Seed input `BUSINESS_CONTEXT_JSON` |
| `OFFER_BRIEF` (optional) | Not available at this stage — omit |
| `KNOWN_COMPETITORS` | Competitor names from `STEP1_CONTENT` |
| `CATEGORY_CONTEXT` | `CATEGORY_NICHE` from Stage 1 |

**Output:** `competitor_analysis.json` — consumed by ALL agents in Stage 2B

---

### Stage 2B: VOC + Angle Discovery

**Prerequisite:** Stage 1 complete + Stage 2A complete (or running in parallel if competitor assets were collected during Stage 1)

**System:** VOC + Angle Engine (6-component pipeline)

#### Translation Layer: Stage 1 Outputs → VOC + Angle Engine Inputs

| VOC+Angle Engine Input | Source | Transformation |
|----------------------|--------|---------------|
| Agent 0 `PRODUCT_BRIEF` | `BUSINESS_CONTEXT_JSON` enriched with `CATEGORY_NICHE` and market maturity from `STEP1_CONTENT` | Add `category_niche`, `market_maturity_stage`, `primary_icps` from STEP1 analysis |
| Agent 0 `AVATAR_BRIEF` | `STEP6_SUMMARY` + relevant sections of `STEP6_CONTENT` | Direct pass-through. If STEP6_CONTENT exceeds token limits, use STEP6_SUMMARY as primary with key sections extracted. |
| Agent 0 `COMPETITOR_RESEARCH` | `STEP1_SUMMARY` + `STEP1_CONTENT` | Direct pass-through. STEP1_SUMMARY for context, STEP1_CONTENT for detailed competitor data. |
| Agent 0 `COMPETITOR_ANALYSIS_JSON` | `competitor_analysis.json` from Stage 2A | Direct pass-through |
| Agent 0b — same as Agent 0 plus `PRODUCT_CATEGORY_KEYWORDS` | Extract from `CATEGORY_NICHE` + `STEP1_CONTENT` keyword analysis | Parse keywords from competitor research |
| Agent 2 `Existing VOC Corpus` | `STEP4_CONTENT` from Stage 1 | **Transformation required** — see Section 5 |
| Agent 3 `Known Saturated Angles` | `competitor_analysis.json` → `saturation_map` | Extract saturated angle x driver combinations |

#### Agent 2 DUAL MODE Configuration

Agent 2 MUST run in **DUAL MODE** when Stage 1 has been completed. This means:

1. The existing VOC corpus from `STEP4_CONTENT` is processed first
2. Agent 2 produces a GAP REPORT identifying thin areas
3. Fresh scraping (from Agent 1's mining plan) fills those gaps
4. The final corpus is a merged, deduplicated set

**Why DUAL MODE:** The Foundational Docs' Deep Research produces browsing-based VOC (long-form blog discussions, Google results, editorial content) that Apify's actor-based scraping cannot reach. The two collection methods are complementary — browsing finds considered, long-form content; scraping finds structured, high-volume content.

#### Execution Order Within Stage 2B

```
1. Agent 0 (Habitat Strategist) + Agent 0b (Video Strategist) — run in parallel
2. [Apify Execution Layer] — run scraper configs from Agent 0 + 0b
3. [score_virality.py] — score video data (if video habitats scraped)
4. Agent 1 (Habitat Qualifier) — qualify all scraped habitats
5. [score_habitats.py] — score habitat observations
6. Agent 2 (VOC Extractor) — extract VOC in DUAL MODE
7. [score_voc.py] — score VOC observations
8. Agent 3 (Shadow Angle Clusterer) — cluster and rank Purple Ocean angles
9. [score_angles.py] — score angle observations
```

**Quality Gates:**
- Agent 1 must qualify at least 8 habitats (or explain why fewer)
- Agent 2 must produce at least 200 VOC items across 3+ habitat types
- Agent 3 must produce at least 5 candidate angles with 5+ supporting VOC items each

---

### Human Decision Point: Angle Selection

**When:** After Stage 2B completes (Agent 3 output available)

**Input:** Agent 3's ranked Purple Ocean angle candidates with:
- Full angle primitives
- Observation sheets (scored by `score_angles.py`)
- Hook starters
- Evidence assembly (supporting quotes + contradictions)
- Compliance blocks
- Differentiation maps vs. saturated angles
- Decision readiness block

**Template:** `angle_selection.yaml` (see Section 4)

**Human Evaluates:**
1. Review top 5-8 ranked angles
2. Consider compliance constraints
3. Consider creative executability
4. Consider audience size and pain intensity
5. Select ONE angle for offer construction

**Output:** Completed `angle_selection.yaml` — feeds Stage 3

---

### Stage 3: Offer Architecture

**Prerequisite:** Stage 2B complete + angle selected

**System:** Offer Agent (5-step pipeline)

#### Input Mapping

| Offer Agent Input | Source | Content |
|------------------|--------|---------|
| **Product Brief** | `BUSINESS_CONTEXT_JSON` + Stage 1 enrichments | Product name, description, category, price, format, `product_customizable`, positioning gaps from STEP1, market maturity |
| **Selected Angle** | `angle_selection.yaml` | Full angle primitive with who/pain/mechanism/belief-shift/trigger, evidence, hook starters, compliance status |
| **Competitor Teardowns** | `competitor_analysis.json` + `STEP1_CONTENT` relevant sections | Structural pattern matrix, whitespace map, table stakes, price/bonus/guarantee/proof comparisons |
| **VOC Research** | Agent 2 handoff block — **filtered to selected angle** | Angle-relevant VOC items with observation sheets, quote banks, pain clusters, emotional drivers, buyer language. Filter by: items in the selected angle's cluster + items tagged with the selected angle's pain/trigger/identity dimensions. |
| **Purple Ocean Research** | Agent 3 handoff block | Full context: all validated angles (not just selected), shadow angles, intersection opportunities, saturated angle baseline |

**Critical Note on VOC Filtering:** The Offer Agent runs for ONE angle at a time. When passing Agent 2's VOC corpus, filter to include:
- All items in the selected angle's cluster (from Agent 3)
- All items with matching trigger event category
- All items with matching pain domain
- All contradiction/limiting items for the selected angle
- The Language Registry entries relevant to the angle's pain/identity/enemy dimensions

Do NOT pass the entire 200+ item corpus — it will overwhelm context. Target 40-80 highly relevant items.

#### Execution Order Within Stage 3

1. Step 1: Avatar Brief synthesis
2. Step 2: Market Calibration (7 phases, including Phase 7: Awareness-Angle-Matrix)
3. Step 3: UMP/UMS Generation → **HUMAN SELECTS UMP/UMS PAIR**
4. Step 4: Offer Construction (13 phases, 3 scoring tools)
5. Step 5: Self-Evaluation & Scoring → **HUMAN SELECTS VARIANT**
6. Output Assembly: Final Offer Document + Awareness-Angle-Matrix + metadata

**Quality Gates:**
- Step 2 `calibration_consistency_checker` must pass
- Step 5 composite score must be >= 5.5 (PASS) or enter iteration
- Maximum 2 iterations before HUMAN_REVIEW

---

### Offer-to-Copy Bridge

**When:** After Stage 3 completes

**Purpose:** Transform Offer Agent outputs into the Copywriting Agent's shared context files.

#### Population Guide

| Copywriting Agent File | Source | Mapping |
|----------------------|--------|---------|
| `01_governance/shared_context/audience-product.md` — Audience section | Offer Agent Step 1 (Avatar Brief) | Demographics → `{DEMOGRAPHICS}`. Top 3 pain points → `{PAIN_POINTS}`. Goals → `{GOALS}`. Emotional drivers → `{EMOTIONAL_DRIVERS}`. Fears → `{FEARS}`. VOC quote bank → `{CURATED_QUOTES}`. |
| `01_governance/shared_context/audience-product.md` — Product section | Final Offer Document | Product name → `{PRODUCT_NAME}`. Core promise → `{CORE_PROMISE}`. UMP → `{UMP}`. UMS → `{UMS}`. Value stack summary → `{VALUE_STACK}`. Guarantee → `{GUARANTEE}`. Price → `{PRICE}`. |
| `01_governance/shared_context/awareness-angle-matrix.md` | Step 2 Phase 7 output | Direct placement — already specified in UPSTREAM-INTEGRATION.md |
| `01_governance/shared_context/brand-voice.md` | Operator configuration | Not from pipeline — operator must configure. Can be informed by competitor analysis tone patterns. |
| `01_governance/shared_context/compliance.md` | Offer Agent compliance flags + Agent 3 compliance block + Competitor Asset Analyzer compliance landscape | Merge compliance data from all upstream sources. |

#### Belief Architecture Mapping

The Offer Agent's belief cascade (Step 4, Phase 10) maps to the Copywriting Agent's B1-B8 framework:

| Offer Agent Belief Cascade | Copywriting B1-B8 | Copy Section |
|---------------------------|-------------------|-------------|
| Problem reality + urgency beliefs | B1 + B2 | Presell: Sections 1-2 |
| Solution category existence | B3 | Presell: Section 3 |
| Product differentiation (UMS) | B4 + B5 | Presell: Section 4-5, Sales: Section 1 |
| Product-identity fit | B6 | Sales: Sections 3-4 |
| Offer fairness (value > price) | B7 | Sales: Sections 5-8 |
| Action urgency (risk reversal) | B8 | Sales: Sections 9-12 |

**The Copywriting Agent should load the Offer Agent's belief cascade and use it to inform WHICH specific beliefs to advance in each section, rather than relying on generic B1-B8 guidance.**

---

### Stage 4: Copy Execution

**Prerequisite:** Stage 3 complete + shared context populated

**System:** Copywriting Agent

**Execution Order:**

```
1. Load shared context (audience-product.md, brand-voice.md, compliance.md,
   awareness-angle-matrix.md, mental-models.md)
2. Generate awareness-angle matrix (if not provided by Offer Agent — fallback path)
3. Run headline engine → deterministic scoring (29 tests, 44 pts)
4. Extract Promise Contracts from winning headlines
5. Write presell advertorial (B1-B4) → congruency scoring (13 tests, 19 pts)
6. Write sales page (B5-B8) → congruency scoring
7. QA auto-fix loop for any failing assets
8. Generate output documents
```

**Quality Gates:**
- Headlines must score B-tier or above (28+ points)
- Presell congruency must pass 75% (14.25+ of 19 points)
- Sales page congruency must pass 75%
- PC2 (Promise Contract Delivery Test) is a HARD GATE — must pass

---

## 4. Angle Selection Handoff Template

After reviewing Agent 3's output, the human completes this template:

```yaml
# angle_selection.yaml
# Completed by operator after reviewing Agent 3's Purple Ocean angle candidates

selected_angle:
  # From Agent 3's angle primitive
  angle_id: ""          # e.g., A04
  angle_name: ""        # e.g., "The Dosage Gap"

  definition:
    who: ""             # Avatar segment from angle primitive
    pain_desire: ""     # PAIN + DESIRED OUTCOME from angle primitive
    mechanism_why: ""   # MECHANISM from angle primitive
    belief_shift:
      before: ""        # What they currently believe
      after: ""         # What they must believe to buy
    trigger: ""         # What made them look NOW

  evidence:
    supporting_voc_count: 0     # From Agent 3 observation sheet
    top_quotes:                  # Top 5 from Agent 3 evidence assembly
      - voc_id: ""
        quote: ""
      - voc_id: ""
        quote: ""
      - voc_id: ""
        quote: ""
      - voc_id: ""
        quote: ""
      - voc_id: ""
        quote: ""
    triangulation_status: ""    # SINGLE / DUAL / MULTI
    velocity_status: ""         # ACCELERATING / STEADY / DECELERATING
    contradiction_count: 0      # Number of limiting items

  hook_starters:                # From Agent 3's hook generation
    - visual: ""
      opening_line: ""
      lever: ""
    - visual: ""
      opening_line: ""
      lever: ""
    - visual: ""
      opening_line: ""
      lever: ""

  compliance:
    overall_risk: ""            # GREEN / YELLOW / RED
    expressible_without_red: true
    platform_notes: ""

  # Contextual data the Offer Agent needs
  purple_ocean_context:
    saturated_angles:           # From Agent 3's saturated angle summary
      - name: ""
        competitors_using: []
        hook_pattern: ""
    differentiation_summary: "" # How this angle differs from saturated angles
    minimum_distinctiveness: 0  # Dimensions different from closest saturated angle

selection_rationale: ""         # Human's reasoning for selecting this angle
selection_date: ""              # ISO 8601
```

---

## 5. VOC Corpus Transformation Spec (Stage 1 → Agent 2 DUAL MODE)

### Source Format (Foundational Docs STEP4_CONTENT)

The Deep Research output contains tagged quote banks with 6 metadata fields per quote:

```
SOURCE: [platform/URL]
CATEGORY: [one of 9 research categories: A-I]
EMOTION: [emotional tag]
INTENSITY: [HIGH/MODERATE/LOW]
BUYER_STAGE: [awareness level]
SEGMENT_HINT: [buyer segment indicator]
"[verbatim quote]"
```

### Target Format (Agent 2 VOC Record)

```
VOC-[ID]
Source: [Platform] | [URL]
Author: [handle or "Anonymous"]
Date: [date or "Unknown"]
Context: [thread title or surrounding discussion topic]
Verbatim: "[exact quote]"

Trigger Event: [extracted or NONE]
Pain/Problem: [extracted or NONE]
Desired Outcome: [extracted or NONE]
Failed Prior Solution: [extracted or NONE]
Enemy/Blame: [extracted or NONE]
Identity/Role: [extracted or NONE]
Fear/Risk: [extracted or NONE]
Emotional Valence: [classification]

Buyer Stage: [from BUYER_STAGE field]
Demographic Signals: [from SEGMENT_HINT or "None detected"]
Solution Sophistication: [infer from context or "Unknown"]
Compliance Risk: [GREEN/YELLOW/RED]
Conversation Context: [from surrounding text]

Flags: [EXISTING_CORPUS]

=== OBSERVATION SHEET ===
[Agent 2 fills all observation fields for each transformed item]
```

### Transformation Rules

| Source Field | Target Field | Rule |
|-------------|-------------|------|
| `SOURCE` | `Source` | Direct mapping. If URL present, use it. If platform name only, note as "[Platform] \| URL_UNKNOWN" |
| `CATEGORY` (A-I) | 8 Core Dimensions | Map: A (Demographics) → Identity/Role. B (Purchase Triggers) → Trigger Event. C (Hopes/Dreams) → Desired Outcome. D (Victories/Failures) → Failed Prior Solution. E (Enemies) → Enemy/Blame. F (Decision Friction) → Fear/Risk. G (Existing Solutions) → Failed Prior Solution. H (Curiosity) → Pain/Problem. I (Corruption) → Enemy/Blame. |
| `EMOTION` | `Emotional Valence` | Map to closest enum: RELIEF / RAGE / SHAME / PRIDE / ANXIETY / HOPE / FRUSTRATION / NEUTRAL |
| `INTENSITY` | Not directly mapped | Used as context for observation sheet: HIGH → likely Y on crisis_language, MODERATE → evaluate carefully, LOW → likely N |
| `BUYER_STAGE` | `Buyer Stage` | Direct mapping if Schwartz levels used. Otherwise map conceptually. |
| `SEGMENT_HINT` | `Demographic Signals` | Direct pass-through |
| Author/Date | `Author` / `Date` | Often unavailable in browsing-based research. Mark as "Anonymous" / "Unknown" |
| Observation Sheet | All 24 fields | Agent 2 must fill these for every transformed item. These were NOT produced by Stage 1. |

### Transformation Process

1. Extract all tagged quotes from `STEP4_CONTENT`
2. Assign sequential VOC IDs starting from V001
3. Map source fields to target fields per rules above
4. Flag all transformed items as `EXISTING_CORPUS`
5. Do NOT fill observation sheets yet — Agent 2 fills these during DUAL MODE processing
6. Pass the transformed corpus to Agent 2 as the "Existing VOC Corpus" input
7. Agent 2 processes these items (fills observation sheets, validates, deduplicates) before fresh mining

---

## 6. Product Brief Evolution Schema

The Product Brief is a single evolving document that grows richer as it passes through pipeline stages.

### Stage 0: Seed

```json
{
  "stage": 0,
  "product_name": "",
  "description": "",
  "price": "",
  "competitor_urls": [],
  "product_customizable": true
}
```

### Stage 1: Post-Research

```json
{
  "stage": 1,
  "_inherits": "Stage 0 fields",
  "category_niche": "",
  "market_maturity_stage": "",
  "primary_segment": {
    "name": "",
    "size_estimate": "",
    "key_differentiator": ""
  },
  "bottleneck": "",
  "positioning_gaps": [],
  "competitor_count_validated": 0,
  "primary_icps": []
}
```

### Stage 2: Post-Angle Selection

```json
{
  "stage": 2,
  "_inherits": "Stage 1 fields",
  "selected_angle": {
    "angle_id": "",
    "angle_name": "",
    "who": "",
    "pain_desire": "",
    "mechanism_why": "",
    "belief_shift_before": "",
    "belief_shift_after": "",
    "trigger": ""
  },
  "compliance_constraints": {
    "overall_risk": "",
    "red_flag_patterns": [],
    "platform_notes": ""
  },
  "buyer_behavior_archetype": "",
  "purchase_emotion": "",
  "price_sensitivity": ""
}
```

### Stage 3: Post-Offer

```json
{
  "stage": 3,
  "_inherits": "Stage 2 fields",
  "ump": "",
  "ums": "",
  "core_promise": "",
  "value_stack_summary": [],
  "guarantee_type": "",
  "pricing_rationale": "",
  "awareness_level_primary": "",
  "sophistication_level": "",
  "composite_score": 0.0,
  "variant_selected": ""
}
```

### Stage 4: Copy Input (audience-product.md ready)

```json
{
  "stage": 4,
  "_inherits": "Stage 3 fields",
  "curated_voc_quotes": [],
  "b1_b8_belief_assignments": {},
  "brand_voice_configured": true,
  "awareness_angle_matrix_loaded": true
}
```

---

## 7. Gap Resolution Summary

| Gap | Resolution | Deliverable |
|-----|-----------|-------------|
| Gap 1: Translation Layer | Formal variable mapping + transformation rules | Section 3 (Stage 2B) + Section 5 |
| Gap 2: Angle Selection Handoff | `angle_selection.yaml` template | Section 4 |
| Gap 3: Product Brief Consistency | Evolving schema with stage markers | Section 6 |
| Gap 4: Offer → Copy Population | Offer-to-Copy Bridge population guide + belief mapping | Section 3 (Offer-to-Copy Bridge) |
| Gap 5: Dual VOC Strategy | Agent 2 runs DUAL MODE; transformation spec provided | Section 3 (Stage 2B) + Section 5 |
| Gap 6: Info Asymmetry | Explicit input mapping with granularity specs | Section 3 (Stage 3) |
| Gap 7: Master Orchestration | End-to-end pipeline spec with stages, gates, and human actions | Sections 2 + 3 |
| Gap 8: Scoring Interop | Deferred to productization phase (not blocking MVP) | Future work |
| Gap 9: Belief Architecture | Belief cascade → B1-B8 mapping table | Section 3 (Offer-to-Copy Bridge) |

---

## 8. Human Decision Points (Complete Map)

| Decision | When | Data Available | Template/Tool |
|----------|------|---------------|---------------|
| **Proceed past research** | After Stage 1 | STEP1, STEP4, STEP6 outputs | Review quality gates |
| **Collect competitor assets** | Before Stage 2A | Competitor names/URLs from STEP1 | Manual collection |
| **Select angle** | After Stage 2B | Agent 3 ranked angles + observation sheets + hooks | `angle_selection.yaml` |
| **Select UMP/UMS** | During Stage 3, Step 3 | 3-5 scored pairs with dimension breakdowns | Offer Agent pipeline |
| **Select offer variant** | During Stage 3, Step 5 | Base + 2-3 variants with 8-dimension evaluations | Offer Agent pipeline |
| **Review/approve copy** | After Stage 4 | Scored headlines, advertorials, sales pages | Copywriting Agent scoring |

---

## 9. Error Recovery

| Failure Mode | Stage | Recovery Action |
|-------------|-------|----------------|
| STEP1 finds < 3 competitors | 1 | Broaden search terms, try adjacent categories, or proceed with caveat |
| STEP4 produces thin VOC (< 5 categories) | 1 | Rerun meta-prompt with adjusted emphasis, or accept and compensate in Stage 2B |
| Competitor Asset Analyzer has < 3 assets | 2A | Collect more assets before proceeding — this is a hard minimum |
| Agent 1 qualifies < 8 habitats | 2B | Check if scraping configs need adjustment, consider expanding date ranges |
| Agent 2 produces < 200 VOC items | 2B | Acceptable if items are high quality. Flag in corpus health audit. |
| Agent 3 produces < 5 viable angles | 2B | Indicates either thin VOC or highly saturated market. Consider adjacent segments. |
| All offer variants score < 5.5 | 3 | Iteration logic handles this (max 2 iterations). If still failing, HUMAN_REVIEW. |
| Headlines all score < B-tier | 4 | QA auto-fix loop (max 3 iterations). If still failing, revisit offer promise. |
| Congruency scorer fails PC2 hard gate | 4 | Body copy doesn't deliver headline promise. Rewrite body, not headline. |

---

## 10. Deprecated Components

| Component | Location | Reason | Replacement |
|-----------|----------|--------|-------------|
| `07_offer_brief_v2.md` | Foundational Docs `downstream/` | Superseded by Offer Agent 5-step pipeline | Offer Agent |
| `08_belief_architecture_v2.md` | Foundational Docs `downstream/` | Superseded by Offer Agent Step 4 Phase 10 + Copywriting Agent B1-B8 | Offer Agent + Copywriting Agent |

These files should be marked with a deprecation header but preserved for reference.

---

## 11. Implementation Deliverables

| # | Deliverable | Type | Priority |
|---|-------------|------|----------|
| 1 | Master Pipeline Orchestration Spec (this document) | Documentation | P0 |
| 2 | `angle_selection.yaml` template file | Template | P0 |
| 3 | Translation Layer reference table (Stage 1 → Stage 2B mapping) | Documentation | P0 |
| 4 | VOC Corpus Transformation Spec | Documentation + potential script | P1 |
| 5 | Product Brief Evolution Schema | Schema (JSON) | P1 |
| 6 | Offer-to-Copy Bridge guide | Documentation | P1 |
| 7 | Deprecation notices on old downstream prompts | Light edits | P2 |
| 8 | Cross-references in each system's existing docs | Light edits | P2 |

---

## 12. Mental Models Applied

| Mental Model | Where Applied | Impact |
|-------------|---------------|--------|
| **First Principles** | Identified that the "angle" is the atomic unit — everything flows from angle quality | Prioritized angle selection handoff as P0 |
| **Theory of Constraints** | Found bottleneck at system boundaries (Foundational→VOC, Agent 3→Offer) | Focused design on transition points |
| **Map vs. Territory** | Foundational Docs = map, VOC+Angle Engine = territory | Justified sequential + DUAL MODE |
| **MECE** | Verified each system covers a distinct, non-overlapping scope | Deprecated redundant downstream prompts |
| **Second-Order Thinking** | Chose Approach B over A (too thin) and C (premature) | Selected the approach that enables future automation |
| **Occam's Razor** | Agent 2 DUAL MODE is simpler than running two separate VOC processes | Avoided creating a fifth system |
| **Inversion** | Asked "what breaks if we remove X?" for each system | Proved all four systems are necessary |
| **80/20 (Pareto)** | Approach B captures 80% of value with 20% of effort | Structured handoffs without automation code |
| **Leverage** | Foundational Docs output creates inputs for the entire downstream chain | Justified running it first |
| **Single Source of Truth** | Product Brief evolves through stages instead of being redefined per system | Prevented data loss and confusion |
| **Information Asymmetry** | Identified that Offer Agent didn't know about VOC+Angle Engine's full output | Created explicit input mapping with granularity specs |
| **Systems Thinking** | Viewed all 4 systems as one pipeline with feedback loops | Created master orchestration instead of point-to-point fixes |
| **Redundancy Analysis** | Found belief architecture in 3 places | Unified into cascade → B1-B8 mapping |
| **Interface/Contract Design** | Each system boundary now has explicit input/output contracts | Handoff templates are the contracts |
| **Dependency Mapping** | Mapped which gaps block which other gaps | Prioritized P0 gaps that unblock everything else |
| **Critical Path Analysis** | The middle transitions (Stages 1→2, 2→3) are on the critical path | Focused design effort there |
| **Eisenhower Matrix** | Classified gaps by urgency + importance | Deferred scoring interop (P3) to productization |
| **Feedback Loops** | If copy scores poorly, the issue may trace back to offer quality or angle selection | Error recovery table traces failures upstream |
| **Goodhart's Law** | Scoring systems in each agent already protect against metric gaming | Design preserves these protections across system boundaries |
| **Bayesian Reasoning** | Each agent already uses prior declarations — the integration preserves this | Prior vs. actual comparisons propagate through the pipeline |
