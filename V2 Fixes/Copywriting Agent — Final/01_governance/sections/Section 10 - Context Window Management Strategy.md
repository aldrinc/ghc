# Section 10: Context Window Management Strategy

## Operational Specification for RAG-Based Context Loading

**System:** Copywriting agent for The Honest Herbalist Handbook | Claude/GPT-4 class LLM | RAG orchestration
**Constraint:** Generation quality degrades with excessive context. This document governs what loads, when, and how much.
**Token math:** 1 token per ~0.75 words throughout.

---

## Subsection A: Document Classification by Load Priority

### Tier 1 -- Always Loaded (Core Context)

| Document | Version | Why Always Loaded | Est. Tokens |
|---|---|---|---|
| Section 3 -- Voice & Tone | CONDENSED | Banned/preferred words, emotional register, urgency rules govern every sentence. | ~1,470 |
| Section 4 -- Compliance Layer | CONDENSED | Banned phrases, claim hierarchy, disclaimers, pre-submission checklist apply to all outputs. | ~1,600 |
| Subsection B -- Craft Rules | CONDENSED | Readability targets, specificity, rhythm, bullets, transitions apply universally. | ~1,200 |
| Avatar Brief | FULL | Already compact (~976 words). Defines the reader. Every copy decision depends on audience. | ~1,300 |

**Tier 1 Total: ~5,570 tokens**

### Tier 2 -- Loaded Per Task

| Document | When Loaded | Est. Tokens |
|---|---|---|
| Sub. A -- Structural Principles (~2,990w) | Presell, sales page, upsell/downsell, email. Not compliance review or A/B variants. | ~3,990 |
| Section 2 -- Page-Type Templates (~3,711w) | Any funnel page build: presell, sales page, checkout, thank-you, upsell, downsell. | ~4,950 |
| Section 5 -- Awareness Routing (~3,672w) | Any task where traffic source determines structure: presell, sales page, email, ads. | ~4,900 |
| Section 7 -- Hook Framework (~3,490w) | HookBank generation, presell headline/lead, ad copy, email subject lines. | ~4,650 |
| Section 6 -- Proof Inventory (~5,102w) | Tasks requiring proof selection: sales page proof/mechanism/offer sections, presell, emails with testimonials. | ~6,800 |
| Section 8 -- AB Testing Framework (~3,289w) | A/B variant generation only. | ~4,390 |
| Sub. E -- Behavioral Science (~1,926w) | Sales page, presell, email. Any task involving persuasion architecture. | ~2,570 |
| Offer Brief (~1,135w) | Tasks referencing price, bonuses, guarantee: sales page, checkout, upsell/downsell, email. | ~1,510 |
| "I Believe" Statements (~391w) | Presell, sales page identity section, email sequences. Belief chain alignment tasks. | ~520 |

Only 2-4 Tier 2 docs load per task. Per-task Tier 2 budget: ~1,500-3,500 tokens (light tasks) to ~6,000 tokens (heavy tasks).

### Tier 3 -- Available On Demand

| Document | Retrieval Trigger | Est. Tokens |
|---|---|---|
| Sub. D -- Historical AB Patterns (~2,147w) | Agent cites a benchmark or justifies a copy decision with conversion data. | ~2,860 |
| Competitor Research (~4,073w) | Agent writes differentiator claims or mechanism sections; needs "Only This Product" validation. | ~5,430 |
| VOC Corpus (~24,181w) | Agent needs verbatim customer language for agitation, testimonial framing, or identity hooks. | ~32,240 |
| Purple Ocean Research (~1,665w) | Agent needs market positioning angles beyond the avatar brief. | ~2,220 |
| Design System (~961w) | Agent produces layout or visual placement directives. | ~1,280 |
| Section 9 -- Job Definitions (~2,000w est.) | Post-generation self-evaluation checklist or cross-section flow check. | ~2,670 |
| Section 11 -- Mental Models Layer (Parts 1, 3 full) | When agent needs model definitions or specific evaluation step upgrades. | ~3,000 |

Tier 3 documents are retrieved by section excerpt, never loaded in full (especially the VOC Corpus).

**Special classification — Section 11 (Mental Models Operating Layer):**
- Tier 1: Part 2B countermeasures summary (tool-calling mandate) + Part 4 Universal Operating Rules (~1,500 tokens). Loaded for every session to govern HOW all evaluation is performed.
- Tier 2: Part 3 subsection relevant to current evaluation task.
- Tier 3: Parts 1 and 3 full (model definitions and all specific application rules).

---

## Subsection B: Task-to-Context Mapping

| Task Type | Tier 2 (Loaded for This Task) | Tier 3 (Available If Needed) |
|---|---|---|
| **Write Presell Advertorial** | Structural Principles, Awareness Routing, Hook Framework, "I Believe" | VOC Corpus, Competitor Research, AB Patterns |
| **Write Sales Page Section** | Structural Principles, Page-Type Templates, Proof Inventory, Behavioral Science, Offer Brief | VOC Corpus, Competitor Research, AB Patterns |
| **Generate HookBank** | Hook Framework, Awareness Routing | VOC Corpus, Competitor Research, AB Patterns |
| **Write Upsell/Downsell** | Page-Type Templates, Offer Brief, Behavioral Science | Proof Inventory, VOC Corpus |
| **Write Email Sequence** | Awareness Routing, Behavioral Science, "I Believe," Offer Brief | VOC Corpus, Proof Inventory, AB Patterns |
| **Generate A/B Variants** | AB Testing Framework, Behavioral Science | AB Patterns, Proof Inventory |
| **Compliance Review** | (none -- Compliance loads as FULL instead of condensed; adds ~4,150 tokens to Tier 1) | Section 9 Job Definitions |
| **Write Checkout/Order Page** | Page-Type Templates, Offer Brief | Proof Inventory, Design System |
| **Write Thank-You Page** | Page-Type Templates, Offer Brief | Design System |

All tasks load all four Tier 1 docs. **(C)** = condensed, **(F)** = full. Compliance Review is the only task that swaps Section 4 to its full version.

---

## Subsection C: Context Loading Protocol

```
STEP 1: IDENTIFY TASK TYPE
  Match user prompt against the Subsection B mapping table.
  If unlisted: select closest match, log assumption.

STEP 2: LOAD TIER 1
  Load all four Tier 1 docs. Order: Compliance, Voice, Craft Rules, Avatar.
  (Compliance constraints override voice; voice overrides craft defaults.)
  Validate total is within ~5,000-6,000 tokens.

STEP 3: LOAD TIER 2
  Load task-specific Tier 2 docs per mapping table.
  Load order: structural docs first (Sub. A, Sec 2, Sec 5), then
  content-selection docs (Sec 6, Sec 7, Sub. E), then product docs
  (Offer Brief, "I Believe").
  Budget check: If Tier 1 + Tier 2 exceeds 10,000 tokens, apply
  Rule 2 trimming (Subsection D).

STEP 4: EXECUTE TASK
  Generate output. Tier 1 = hard constraints. Tier 2 = structural guidance.

STEP 5: TIER 3 RETRIEVAL (IF NEEDED)
  Retrieve only the relevant section excerpt, not full documents.
  Budget check: total must stay under 10,000 tokens. Summarize excerpts
  if necessary.

STEP 6: POST-GENERATION CHECKS
  Pass 1: Compliance scan against Sec 4 banned phrases + claim rules.
  Pass 2: Self-eval via Sec 9 checklist for the relevant section type.
  If either fails: revise before delivery.
```

**Multi-section tasks (e.g., writing Sales Page sections 1-9 sequentially):**
- Tier 1 persists across all sections. Never unloaded.
- Tier 2 structural docs (Sub. A, Sec 2, Sec 5) persist across the entire page build.
- Tier 2 content docs (Sec 6, 7, Sub. E) swap per section as the mapping table dictates.
- Previously generated sections become context for the next section. If cumulative prior output exceeds 2,000 tokens, load a condensed summary instead of verbatim.

---

## Subsection D: Context Optimization Rules

**Rule 1 -- Condensed vs. Full:** Tier 1 loads condensed by default (specs in Subsection E). Exceptions: Avatar Brief always full (already compact). Section 4 loads full only during Compliance Review tasks.

**Rule 2 -- Token Budget:** Hard ceiling of 10,000 tokens of reference context per generation call (excludes system prompt, task instructions, and model output). Target breakdown: Tier 1 ~5,500 / Tier 2 ~3,000 / Tier 3 ~1,500. Trim order if exceeded: (a) reduce Tier 3 excerpts to summaries, (b) drop lowest-priority Tier 2 doc, (c) never reduce Tier 1.

**Rule 3 -- Staleness Prevention:** Flag for human review when: AB Patterns or Compliance Layer are >90 days since last update; Proof Inventory contains items past `review_by` date; Competitor Research >120 days old; VOC Corpus >180 days without new entries. Agent must never suppress staleness flags -- include them in output metadata.

**Rule 4 -- Multi-Step Persistence:** Tier 1 and Tier 2 structural docs persist across all steps of a multi-section task. Tier 2 content docs swap per section. Prior generated output carries forward (summarized above 2,000 tokens). Tier 3 retrievals are discarded after the step that used them.

**Rule 5 -- Fallback Rules:** If context exceeds budget: trim Tier 3 first, then lowest-priority Tier 2, never Tier 1. If trimming is insufficient, split into two generation calls. If agent cannot find needed context: do not hallucinate. Insert `[CONTEXT_GAP: {description}]`, continue generating, list all gaps in output metadata. If a Tier 2 doc is missing from the system: proceed with available context, flag output for human review.

---

## Subsection E: Condensed Document Specifications

### Section 3 -- Voice & Tone (~3,256w full --> ~1,100w condensed)

| KEEP | CUT |
|---|---|
| A1: Sentence length table (numeric ranges only) | A1: Rhythm rule explanations within cells |
| A2: Full 30-word banned list (word + reason columns) | A3: "Why It Works" column (keep word/phrase only) |
| A3: Preferred word/phrase column only | A4: Full jargon policy (replace with 1-line rule) |
| A4: 1-line rule: "Scientific terms require plain-language parenthetical on first use" | A5: Contraction examples |
| A5: 4 contraction rules, no examples | B1: Archetype description (keep 1 line: "The calm, protective guide") |
| B1: 1 line: "The Honest Herbalist is the calm, protective guide." | B2: Credential examples |
| B2: 5 credential rules as bullets | B3: Caveat tone explanation |
| B3: Caveat triggers + 4 approved formats | C: Urgency philosophy narrative |
| C2: Approved urgency phrases (10 items) | D: "Sounds Like" / "Does NOT Sound Like" columns |
| C3: Banned urgency phrases (10 items) | E: Bridge sentence examples |
| C4: Timer policy (4 rules) | F: "Why Banned" explanations |
| D: Register map -- context + register columns only | |
| E: Shift direction + trigger table only | |
| F: 18 anti-pattern names only (no explanations) | |

### Section 4 -- Compliance (~4,315w full --> ~1,200w condensed)

| KEEP | CUT |
|---|---|
| Product classification (1 sentence) | A: Full platform table detail, consequences, review triggers |
| A: 1-line-per-platform prohibited claim summary | B: FTC/testimonial/ASA narrative blocks (replace with bullets) |
| B: FDA 3-tier claim hierarchy with 1 example each | B: Source citations and URLs |
| B: FTC rules (3 bullets), testimonial rules (3 bullets), UK ASA (3 bullets) | D: Full safe alternatives phrasebook |
| C: Full 30-row banned phrase table (all columns) | E: Platform-specific disclaimer placement details |
| E: 4 required disclaimer text blocks (verbatim) | Regulatory source reference table |
| F: Pre-submission checklist (all items) | |

### Subsection B -- Craft Rules (~3,264w full --> ~900w condensed)

| KEEP | CUT |
|---|---|
| Sec 1: Readability target table + word choice hierarchy (3 bullets) | Sec 1: Unbounce data narrative, evidence base |
| Sec 2.1: Specificity hierarchy table | Sec 2: All worked examples |
| Sec 2.2: "Only This Product" test (1 sentence rule) | Sec 2.3: Compliance specificity table (keep 1-line principle) |
| Sec 2.3: Operating principle (1 sentence) | Sec 3: Cadence example, end-of-sentence examples, before/after |
| Sec 3.1: Sentence type table (type, length, purpose) | Sec 4: Bullet formula comparison to DR, all example bullets |
| Sec 3.2: Paragraph rules table | Sec 5: Transition examples, anti-pattern explanations |
| Sec 3.3: End-of-sentence rule (1 sentence) | Sec 6: Retention examples, evidence base section |
| Sec 3.4: One-idea rule (1 sentence) | |
| Sec 4.1: Bullet formula (1 line) | |
| Sec 4.2: 4 bullet style names + 1-line descriptions | |
| Sec 4.3: 5 anti-pattern names (no explanations) | |
| Sec 4.4: Bullet quantity/placement table | |
| Sec 5.2: 3 transition technique names + 1-line descriptions | |
| Sec 6.1: Retention device table (device + frequency) | |
| Self-evaluation checklist (all items, verbatim) | |

---

*This document governs all context loading decisions. The orchestration layer executes the loading protocol (Subsection C) before every generation call. No copy task begins without confirmed Tier 1 loading and task-type classification. Update this document when any foundational doc is added, any doc's word count changes by >20%, or the target LLM changes.*
