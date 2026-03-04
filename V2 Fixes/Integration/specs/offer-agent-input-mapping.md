# Offer Agent Input Mapping

**Purpose:** Maps each of the Offer Agent's 5 pipeline inputs to their exact upstream source, with field-level detail and transformation notes.

**Reference:** Offer Agent's input schema is defined in `Offer Agent — Final/prompts/pipeline-orchestrator.md` (Pipeline Inputs section).

---

## Input 1: product_brief

**Source:** Seed input enriched through Stages 1-2

| Offer Agent Field | Source | Notes |
|------------------|--------|-------|
| `name` | Seed: `product_name` | Direct |
| `description` | Seed: `description` | Direct |
| `category` | Stage 1: `CATEGORY_NICHE` | Extracted from STEP1 output |
| `price_cents` | Seed: `price` | Convert to cents (e.g., "$49" → 4900) |
| `currency` | Default "USD" | Or extract from seed if specified |
| `business_model` | **Operator specifies** | Not produced by upstream systems. Options: one-time / subscription / freemium |
| `funnel_position` | **Operator specifies** | Not produced by upstream. Options: cold_traffic / post_nurture / retargeting / evergreen |
| `target_platforms` | **Operator specifies** | Array: Meta / TikTok / YouTube / Google / Email |
| `target_regions` | **Operator specifies** | Array: US / UK / Tier1 / etc. |
| `product_customizable` | Seed: `product_customizable` | Direct |
| `constraints.compliance_sensitivity` | Derive from `competitor_analysis.json` | If compliance landscape shows >30% RED: "high". If >30% YELLOW: "medium". Otherwise: "low" |
| `constraints.existing_proof_assets` | **Operator specifies** | Array of strings describing available proof |
| `constraints.brand_voice_notes` | **Operator specifies** | Free text |

### Operator-Specified Fields

These fields must be provided by the operator at Stage 3 entry because no upstream system produces them:

- `business_model`
- `funnel_position`
- `target_platforms`
- `target_regions`
- `constraints.existing_proof_assets`
- `constraints.brand_voice_notes`

**Recommendation:** Add these to the seed input schema (Stage 0) so they're captured upfront and don't create a bottleneck at Stage 3.

---

## Input 2: selected_angle

**Source:** `integration/templates/angle_selection.yaml` (completed by operator)

| Offer Agent Field | angle_selection.yaml Field | Transformation |
|------------------|--------------------------|----------------|
| `angle_name` | `selected_angle.angle_name` | Direct |
| `angle_definition.who` | `selected_angle.definition.who` | Direct |
| `angle_definition.pain_desire` | `selected_angle.definition.pain_desire` | Direct |
| `angle_definition.mechanism_why` | `selected_angle.definition.mechanism_why` | Direct |
| `angle_definition.belief_shift` | `selected_angle.definition.belief_shift.before` + `selected_angle.definition.belief_shift.after` | Combine as: "{before} → {after}" (single string) |
| `angle_definition.trigger` | `selected_angle.definition.trigger` | Direct |
| `angle_evidence` | `selected_angle.evidence.top_quotes` | Extract `.quote` strings into flat array |
| `angle_hooks` | `selected_angle.hook_starters` | Extract `.opening_line` strings into flat array |

---

## Input 3: provided_research.competitor_teardowns

**Source:** `competitor_analysis.json` (from Stage 2A) + relevant sections of `STEP1_CONTENT` (from Stage 1)

### What to Include

From `competitor_analysis.json`:
- `asset_observation_sheets` — all per-asset observation data
- `saturation_map` — full angle x driver matrix with SATURATED/CONTESTED/WHITESPACE labels
- `whitespace_map` — all whitespace cells and underserved patterns
- `messaging_patterns` — hook type, CTA type, narrative structure distributions
- `compliance_landscape` — overall and per-competitor compliance profiles
- `competitors` — names, dominant angles, risk profiles
- `key_findings` — the 3-5 data-backed strategic findings

From `STEP1_CONTENT`:
- Competitor positioning summaries (what each competitor claims, how they differentiate)
- Pricing comparisons (price points, discounts, value stacks seen)
- Proof type analysis (testimonials, studies, certifications found)
- Guarantee patterns (types and terms observed across competitors)

### What to Exclude

- `prior_vs_actual` section (internal audit for the Competitor Asset Analyzer, not useful downstream)
- `disconfirmation_flags` (internal audit)
- `analysis_order` metadata (internal)

### Format

Paste as structured text. The Offer Agent processes this as the `competitor_teardowns` string input — it does not parse JSON programmatically.

---

## Input 4: provided_research.voc_research

**Source:** Agent 2 handoff block — **filtered to the selected angle**

### Filtering Rules

The full Agent 2 corpus may contain 200+ VOC items. The Offer Agent should receive 40-80 highly relevant items. Filter as follows:

**Include:**
1. All VOC items listed in the selected angle's cluster (Agent 3 cites specific VOC IDs per angle primitive)
2. All VOC items with the same trigger event category as the selected angle
3. All VOC items with the same pain domain as the selected angle
4. All contradiction/limiting items Agent 3 identified for this angle
5. Language Registry entries relevant to the angle's pain, identity, and enemy dimensions
6. Purchase barrier items (pre-purchase, post-purchase, category exit) related to the angle's segment
7. Any SLEEPING_GIANT items in the selected angle's cluster

**Exclude:**
- VOC items from other angle clusters (unless they share a dimension with the selected angle)
- Corpus-level metadata (health audit table, platform annotations) — keep these in the full corpus for reference but don't pass to Offer Agent
- Duplicate items that were merged during Agent 2's deduplication step

### Format

For each included item, provide the full VOC Record (with all 8 dimensions, classification fields, and flags). Observation sheets can be omitted for the Offer Agent — it uses the extracted language, not the binary features.

**Target:** 40-80 items. If the angle cluster has fewer than 40 supporting items, include all cluster items plus related items from adjacent clusters.

---

## Input 5: provided_research.purple_ocean_research

**Source:** Agent 3 handoff block (full)

### What to Include

Pass the COMPLETE Agent 3 handoff, including:

1. **All angle primitives** — not just the selected angle. The Offer Agent's Step 2 (Market Calibration) benefits from seeing the full competitive angle landscape.
2. **Saturated angle summary** — the 3-9 dominant angles competitors lead with
3. **Observation sheets** for all candidate angles (the Offer Agent can reference these for context)
4. **Overlap matrix** — shows which angles are similar to each other
5. **Decision readiness block** — MVTs, leading indicators, pre-mortem
6. **Orphan signals** — may inform unconventional offer construction
7. **Hook starters** for all angles (not just selected — may inspire alternative hooks)

### What to Exclude

- Agent 3's input validation section (it just confirms what was received)
- Raw computation outputs from tool calls (keep the interpreted results)

### Rationale

The Offer Agent is not just building an offer for one angle — it's positioning the product within a competitive landscape. Seeing all angles helps Step 2 (Market Calibration) correctly assess:
- Where the selected angle sits relative to alternatives
- Which saturated angles to explicitly differentiate from
- What proof types are needed given the market sophistication level
