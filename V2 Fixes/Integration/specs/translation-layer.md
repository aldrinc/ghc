# Translation Layer: Foundational Docs → VOC + Angle Engine

**Purpose:** Maps every output variable from the Foundational Docs Pipeline (Stage 1) to the corresponding input variable expected by each agent in the VOC + Angle Engine (Stage 2B).

**When to use:** After Stage 1 completes and before running any Stage 2B agent.

---

## Variable Mapping Table

### Agent 0: Habitat Strategist

| Agent 0 Input | Source | Transformation |
|--------------|--------|----------------|
| `PRODUCT_BRIEF` | Seed `BUSINESS_CONTEXT_JSON` + `CATEGORY_NICHE` + fields from `STEP1_CONTENT` | Enrich seed JSON with: `category_niche` (from Step 01 header), `market_maturity_stage` (from Step 01 market stage assessment section), `primary_icps` (from Step 06 ranked segments). Paste as a combined block. |
| `AVATAR_BRIEF` | `STEP6_SUMMARY` (primary). If more detail needed, include key sections of `STEP6_CONTENT`. | Direct pass-through. Use STEP6_SUMMARY alone if context window is tight. |
| `COMPETITOR_RESEARCH` | `STEP1_SUMMARY` + `STEP1_CONTENT` | Direct pass-through. Paste STEP1_SUMMARY first as overview, then STEP1_CONTENT for full competitor data. |
| `COMPETITOR_ANALYSIS_JSON` | `competitor_analysis.json` from Stage 2A | Direct pass-through. Must be valid JSON. |

### Agent 0b: Social Video Strategist

| Agent 0b Input | Source | Transformation |
|---------------|--------|----------------|
| `PRODUCT_BRIEF` | Same as Agent 0 | Same enrichment as Agent 0 |
| `AVATAR_BRIEF` | Same as Agent 0 | Same as Agent 0 |
| `COMPETITOR_ANALYSIS` | `competitor_analysis.json` from Stage 2A | Direct pass-through |
| `PRODUCT_CATEGORY_KEYWORDS` | Extract from `CATEGORY_NICHE` + keyword analysis in `STEP1_CONTENT` | Parse into comma-separated list. Look for sections in STEP1_CONTENT titled "keyword clusters," "search terms," or "category language." Combine with the `CATEGORY_NICHE` label. Example: "herbal remedies, natural health, herbalism, plant medicine" |
| `KNOWN_COMPETITOR_SOCIAL_ACCOUNTS` (optional) | `STEP1_CONTENT` or `competitor_analysis.json` | Extract any social media handles found during competitor research. If none found, leave blank. |

### Agent 1: Habitat Qualifier

Agent 1's inputs come from Agent 0's output (the habitat map + scraper configs), not directly from Stage 1. However, it also receives:

| Agent 1 Input | Source | Transformation |
|--------------|--------|----------------|
| `Agent 0 Handoff Block` | Agent 0's output | Direct — this is the intra-pipeline handoff |
| `Product Brief` | Same as Agent 0 `PRODUCT_BRIEF` | Same enrichment |
| `Avatar Summary` | `STEP6_SUMMARY` | Direct pass-through |

### Agent 2: VOC Extractor

| Agent 2 Input | Source | Transformation |
|--------------|--------|----------------|
| `Agent 1 Handoff Block` | Agent 1's output | Direct — intra-pipeline handoff |
| `Product Brief` | Same as Agent 0 `PRODUCT_BRIEF` | Same enrichment |
| `Avatar Summary` | `STEP6_SUMMARY` | Direct pass-through |
| `Existing VOC Corpus` (DUAL MODE) | `STEP4_CONTENT` from Stage 1 | **Transformation required** — see VOC Corpus Transformation section below |
| `Known Saturated Angles` (optional) | `competitor_analysis.json` → `saturation_map` | Extract all angle + driver combinations where `status` = `SATURATED`. Format as a list of angle descriptions. |

### Agent 3: Shadow Angle Clusterer

| Agent 3 Input | Source | Transformation |
|--------------|--------|----------------|
| `Agent 2 Handoff Block` | Agent 2's output (full VOC corpus + observation sheets + flags) | Direct — intra-pipeline handoff |
| `Competitor Angle Map` | `competitor_analysis.json` → `asset_observation_sheets` + `competitors` | Restructure: for each competitor, list their assets' `primary_angle`, `core_claim`, `implied_mechanism`, `target_segment_description`, `hook_type`. Group by competitor name. |
| `Known Saturated Angles` | `competitor_analysis.json` → `saturation_map` | Extract the 3-9 angle + driver combos with highest counts (status = SATURATED or highest CONTESTED). List with competitor names and hook patterns. |
| `Product Brief` | Same as Agent 0 | Same enrichment |
| `Avatar Brief` | `STEP6_SUMMARY` + relevant `STEP6_CONTENT` sections | Same as Agent 0 |

---

## VOC Corpus Transformation (STEP4_CONTENT → Agent 2 DUAL MODE)

### When to Use

Use this transformation when:
- Stage 1 (Foundational Research) has been completed
- `STEP4_CONTENT` exists and contains tagged quote banks
- You are about to run Agent 2

Agent 2 MUST run in **DUAL MODE** when Stage 1 data is available. This means pasting the transformed corpus into the `Existing VOC Corpus` input field.

### Source Format

The Deep Research output (`STEP4_CONTENT`) contains tagged quotes in this structure:

```
SOURCE: [platform/URL]
CATEGORY: [A through I]
EMOTION: [emotional tag]
INTENSITY: [HIGH/MODERATE/LOW]
BUYER_STAGE: [awareness level]
SEGMENT_HINT: [buyer segment indicator]
"[verbatim quote]"
```

### Category Mapping (Foundational Docs → Agent 2 Dimensions)

| Foundational Docs Category | Agent 2 Core Dimension | Notes |
|---------------------------|----------------------|-------|
| A: Demographics / Identity | Identity/Role | Self-identification, role language |
| B: Purchase Triggers | Trigger Event | "why now" moments, catalysts |
| C: Hopes / Dreams / Aspirations | Desired Outcome | What success looks like |
| D: Victories / Failed Solutions | Failed Prior Solution | What they tried, what didn't work |
| E: Enemies / Blame Targets | Enemy/Blame | Who they hold responsible |
| F: Decision Friction / Fears | Fear/Risk | What stops them from acting |
| G: Existing Solution Landscape | Failed Prior Solution | Current alternatives, competitors tried |
| H: Curiosity / Questions / Confusion | Pain/Problem | What frustrates or confuses them |
| I: Corruption / Distrust | Enemy/Blame | Systems or institutions they blame |

### Emotion Mapping

| Foundational Docs EMOTION tag | Agent 2 Emotional Valence |
|-----------------------------|--------------------------|
| Anger, Outrage, Frustration | FRUSTRATION or RAGE |
| Fear, Anxiety, Worry | ANXIETY |
| Shame, Embarrassment, Guilt | SHAME |
| Hope, Optimism, Excitement | HOPE |
| Relief, Gratitude, Satisfaction | RELIEF |
| Pride, Confidence, Empowerment | PRIDE |
| Neutral, Analytical, Informational | NEUTRAL |

### Transformation Process

1. Extract all tagged quotes from `STEP4_CONTENT`
2. For each quote, create a VOC Record in Agent 2's format:

```
VOC-[sequential ID starting from V001]
Source: [platform from SOURCE field] | [URL if available, or "URL_UNKNOWN"]
Author: Anonymous
Date: Unknown
Context: [thread/article title if available, or "Extracted from Stage 1 Deep Research"]
Verbatim: "[exact quote from STEP4_CONTENT]"

Trigger Event: [map from Category B, or NONE]
Pain/Problem: [map from Category H, or NONE]
Desired Outcome: [map from Category C, or NONE]
Failed Prior Solution: [map from Categories D or G, or NONE]
Enemy/Blame: [map from Categories E or I, or NONE]
Identity/Role: [map from Category A, or NONE]
Fear/Risk: [map from Category F, or NONE]
Emotional Valence: [map using Emotion Mapping table above]

Buyer Stage: [from BUYER_STAGE field]
Demographic Signals: [from SEGMENT_HINT, or "None detected"]
Solution Sophistication: Unknown
Compliance Risk: [assess based on content — GREEN/YELLOW/RED]
Conversation Context: Extracted from Stage 1 Deep Research — STEP4_CONTENT

Flags: EXISTING_CORPUS
```

3. Do NOT fill observation sheets — Agent 2 fills these during DUAL MODE processing
4. Pass the full set of transformed records to Agent 2 as the "Existing VOC Corpus" input
5. Agent 2 will process these (fill observation sheets, validate, deduplicate) before fresh mining

### Quality Notes

- Author and Date will typically be "Anonymous" / "Unknown" for browsing-based research — this is expected
- Some quotes may map to multiple dimensions — assign the PRIMARY dimension, note the secondary
- If a quote's category is ambiguous, prefer the category listed in STEP4_CONTENT's original tag
- Expect 30-80% of STEP4 quotes to survive Agent 2's deduplication and quality checks

---

## Enriching the Product Brief

The seed Product Brief (Stage 0) needs enrichment before it's suitable for the VOC + Angle Engine. Extract these fields from Stage 1 outputs:

| Field to Add | Source | How to Extract |
|-------------|--------|----------------|
| `category_niche` | Step 01 output | Look for the "Category / Niche" label in the first section of STEP1_CONTENT |
| `market_maturity_stage` | Step 01 output | Look for "Market Maturity" or "Product Lifecycle Stage" assessment. Values: Introduction / Growth / Maturity / Decline |
| `primary_icps` | Step 06 output | Look for the ranked buyer segments in STEP6_CONTENT. Extract the top 3 segment names and key descriptors. |
| `positioning_gaps` | Step 01 output | Look for "Positioning Gaps," "Whitespace," or "Underserved" sections in STEP1_CONTENT. List the identified opportunities. |
| `competitor_count_validated` | Step 01 output | Count the number of validated competitors in STEP1_CONTENT |

Paste these enrichments alongside the original seed data when providing the `PRODUCT_BRIEF` input to any VOC + Angle Engine agent.
