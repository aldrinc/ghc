# Angle Selection Guide

**Purpose:** How to select a Purple Ocean angle from Agent 3's output and fill the `angle_selection.yaml` template for the Offer Agent.

---

## When To Use This

After Agent 3 (Shadow Angle Clusterer) completes, you'll have 15-30 ranked candidate angles. You must select ONE angle for offer construction. This guide helps you:

1. Evaluate the candidates
2. Select the strongest angle
3. Fill the handoff template correctly

---

## Step 1: Review Agent 3's Output

Read these sections of Agent 3's output in order:

1. **Section 2: Saturated Angle Summary** — understand what competitors already do
2. **Section 7: Decision Readiness Block** — read the pre-mortem and falsifiers first
3. **Section 4: Observation Sheets** — review scored metrics for top candidates
4. **Section 3: Candidate Angle Profiles** — read the full angle primitives
5. **Section 5: Overlap Matrix** — check if your top picks are actually distinct

---

## Step 2: Apply Selection Criteria

Evaluate your top 5-8 candidates against these criteria:

### Hard Gates (Must Pass)

| Criteria | Threshold | Where to Find |
|----------|-----------|---------------|
| Supporting VOC items | >= 5 (target 10+) | Observation sheet: `supporting_voc_count` |
| Compliance | Expressible without RED claims | Observation sheet: `expressible_without_red` |
| Evidence floor | NOT flagged as INSUFFICIENT_EVIDENCE | Agent 3 flags in Step 6 |

### Strong Signals (Prefer Higher)

| Criteria | What to Look For | Where to Find |
|----------|-----------------|---------------|
| Triangulation | MULTI > DUAL > SINGLE | Observation sheet: `triangulation_status` |
| Distinctiveness | 3+ dimensions different from closest saturated angle | Differentiation map: `MINIMUM DISTINCTIVENESS` |
| Velocity | ACCELERATING or STEADY (avoid DECELERATING) | Observation sheet: `velocity_status` |
| Pain intensity | High crisis_language_count, rage/shame/anxiety count | Observation sheet: pain intensity section |
| Creative executability | Single visual expressible, hook under 12 words | Observation sheet: creative section |
| Source diversity | 3+ habitat types, no single source >70% | Observation sheet: `source_habitat_types`, `dominant_source_pct` |

### Red Flags (Proceed With Caution)

- `SINGLE_SOURCE_RISK` flag — angle built from one platform only
- `HIGH_VARIANCE` flag — unstable signal across dimensions
- `news_cycle_dependent: Y` — angle may expire
- `DECELERATING` velocity — demand may be fading
- All supporting VOC from same author
- Contradiction count > 50% of supporting count

---

## Step 3: Fill the Template

Open `angle_selection.yaml` and fill each field using this reference:

### Field-by-Field Source Map

| Template Field | Agent 3 Output Section | Exact Location |
|---------------|----------------------|----------------|
| `angle_id` | Section 3: Candidate Angle Profiles | ANGLE_ID in angle primitive header |
| `angle_name` | Section 3: Candidate Angle Profiles | ANGLE_NAME in angle primitive header |
| `definition.who` | Section 3: Candidate Angle Profiles | WHO field + Source VOC IDs |
| `definition.pain_desire` | Section 3: Candidate Angle Profiles | Combine PAIN field + DESIRED OUTCOME field |
| `definition.mechanism_why` | Section 3: Candidate Angle Profiles | MECHANISM field |
| `definition.belief_shift.before` | Section 3: Candidate Angle Profiles | BELIEF SHIFT → BEFORE |
| `definition.belief_shift.after` | Section 3: Candidate Angle Profiles | BELIEF SHIFT → AFTER |
| `definition.trigger` | Section 3: Candidate Angle Profiles | TRIGGER field |
| `evidence.supporting_voc_count` | Section 4: Observation Sheets | `supporting_voc_count` |
| `evidence.top_quotes` | Section 3: Supporting Evidence Block | Top 5 verbatim quotes with VOC IDs and scores |
| `evidence.triangulation_status` | Section 4: Observation Sheets | `triangulation_status` |
| `evidence.velocity_status` | Section 4: Observation Sheets | `velocity_status` |
| `evidence.contradiction_count` | Section 4: Observation Sheets | `contradiction_count` |
| `hook_starters` | Section 3: Hook Starters | Visual + opening_line + lever for top 3 hooks |
| `compliance.*` | Section 3: Compliance Block | Green/yellow/red counts + flags |
| `purple_ocean_context.saturated_angles` | Section 2: Saturated Angle Summary | Name + competitors + hook pattern |
| `purple_ocean_context.differentiation_summary` | Section 3: Differentiation Map | Summary of how this angle differs |
| `purple_ocean_context.minimum_distinctiveness` | Section 3: Differentiation Map | MINIMUM DISTINCTIVENESS value |
| `selection_rationale` | YOU FILL THIS | Why you chose this angle |
| `selection_date` | YOU FILL THIS | Today's date (YYYY-MM-DD) |

---

## Step 4: Transform for Offer Agent

The Offer Agent's `pipeline-orchestrator.md` expects a slightly different structure. When passing the completed YAML to the Offer Agent, note these transformations:

| angle_selection.yaml Field | Offer Agent Field | Transformation |
|---------------------------|-------------------|----------------|
| `definition.belief_shift.before` + `.after` | `angle_definition.belief_shift` | Combine: "BEFORE → AFTER" as single string |
| `evidence.top_quotes[].quote` | `angle_evidence[]` | Extract just the quote strings into a flat array |
| `hook_starters[].opening_line` | `angle_hooks[]` | Extract just the opening_line strings into a flat array |

All other fields map directly by name.

---

## Common Mistakes

1. **Picking the highest-scored angle without checking compliance** — A high Purple Ocean score with RED compliance is unusable on most platforms.

2. **Ignoring the contradiction count** — Angles with zero contradictions may indicate an echo chamber, not consensus. Some contradictions are healthy.

3. **Selecting a DECELERATING angle** — Even if the evidence is strong, fading demand means diminishing returns on ad spend.

4. **Choosing a SINGLE_SOURCE angle for a broad audience** — An angle built entirely from Reddit data may not resonate on TikTok or Facebook.

5. **Paraphrasing instead of copying** — The template says "copy from Agent 3's output." Do that literally. The Offer Agent needs the original language, not your summary.
