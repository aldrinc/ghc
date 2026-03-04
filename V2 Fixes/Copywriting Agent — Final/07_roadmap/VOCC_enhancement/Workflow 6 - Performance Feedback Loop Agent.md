# Workflow 6: Performance Feedback Loop Agent

## Agent Identity

**Role:** Creative Intelligence Analyst
**Narrow Job:** Take ad performance data from running campaigns and trace winning (and losing) creatives back to the VOC items and language patterns that generated them — then produce actionable intelligence for the next cycle of content discovery, VOC mining, and creative generation. This agent closes the loop between "research → copy → ads → data → research."

**Maturity Level: NOT MVP.** This agent is designed now but built after you have ad performance data flowing. The architecture is specified here so that Workflows 1-5 produce data in the right format for this agent to consume when it comes online.

**Why This Agent Exists (First Principles):**
The top 0.1% of DR media buyers don't treat creative production as a one-shot process. They treat it as a compounding feedback loop:

```
Research → Creative → Traffic → Performance Data
    ↑                                    ↓
    └────────── Intelligence ←───────────┘
```

Most teams run this loop manually and slowly — a media buyer notices Angle B is outperforming, tells the creative team to "make more like this," and the creative team guesses what "like this" means. The result is a gradual drift from data-driven creative to vibes-driven creative.

This agent makes the loop explicit, fast, and traceable. When Angle B's hook about "lying awake at 2am" outperforms Angle A's hook about "feeling overwhelmed," this agent traces back to the exact VOC items that inspired the winning hook, identifies the emotional territory that resonated, and triggers the Content Discovery Agent to find MORE content in that territory — producing a fresh corpus for a new round of creative generation.

This is how 8-figure DR operations scale a winner: not by running the same ad longer, but by mining deeper into the emotional territory that the data says works, and producing *new* creatives from *new* VOC in that territory.

---

## Inputs

| Input | Source | Required? |
|---|---|---|
| Ad performance data | Ad platform exports (Meta, TikTok, YouTube) or reporting dashboard | Yes |
| Creative-to-VOC traceability map | Generated during creative production (see "used_in" tracking below) | Yes |
| Language Banks per angle | Workflow 5 output | Yes |
| Angle Dossiers | Dossier assembly output | Yes |
| Content Discovery logs | Workflow 3 output (which content was scraped, what yield was produced) | Recommended |

### Ad Performance Data Required Fields:

```
{
  "creative_id": "CR-001",
  "angle": "safety-first parent",
  "platform": "meta",
  "ad_format": "video",
  "hook_text": "[the text/VO of the first 3 seconds]",
  "body_concept": "[brief description of the body creative approach]",

  // Performance metrics:
  "impressions": 125000,
  "thumb_stop_rate": 0.38,
  "hook_rate_3s": 0.32,
  "ctr": 0.018,
  "cpc": 2.14,
  "cvr": 0.034,
  "cpa": 62.94,
  "roas": 2.8,
  "spend": 1250,

  // Comment/engagement signals (from the ad itself):
  "ad_comment_count": 47,
  "ad_comment_sentiment": "mixed-positive",
  "ad_share_count": 12,
  "ad_save_count": 89
}
```

### Creative-to-VOC Traceability Map:

This is generated during creative production. When a copywriting agent (or human) creates an ad and uses language from the Language Bank, it logs:

```
{
  "creative_id": "CR-001",
  "voc_items_used": ["V001-042", "V001-078", "V001-112"],
  "language_bank_items_used": [
    {"type": "money_phrase", "phrase": "lying there replaying the day at 2am"},
    {"type": "identity_marker", "phrase": "I'm not anti-medicine, I'm anti-guessing"}
  ],
  "angle": "safety-first parent",
  "hook_source": "Derived from V001-042 (PAIN + TRIGGER)",
  "body_source": "Derived from V001-112 (IDENTITY)"
}
```

**Critical design requirement:** If this traceability map doesn't exist, the feedback loop is blind. The creative production workflow MUST log which VOC items and language patterns were used in each creative. Design this logging into the downstream copywriting agent specs from day one.

---

## Outputs

### Output 1: Performance Attribution Report

For each angle tested:

```
ANGLE PERFORMANCE ATTRIBUTION: [Angle Name]
Period: [date range]
Creatives tested: [n]
Total spend: [$]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WINNING CREATIVES (top 20% by [primary KPI]):
- Creative [ID]: [KPI value]
  → VOC sources used: [list]
  → Language bank items used: [list]
  → Dominant emotional territory: [description]
  → Dominant copy-function: [PAIN/DESIRE/TRIGGER/etc.]

LOSING CREATIVES (bottom 20% by [primary KPI]):
- Creative [ID]: [KPI value]
  → VOC sources used: [list]
  → Language bank items used: [list]
  → Dominant emotional territory: [description]
  → Dominant copy-function: [PAIN/DESIRE/TRIGGER/etc.]

PATTERN ANALYSIS:
- What winning creatives had in common (VOC-level):
  [Analysis of shared VOC sources, shared emotional territories,
   shared copy-function emphasis]
- What losing creatives had in common:
  [Analysis]
- Hypothesis for why winners won:
  [Data-supported hypothesis about which emotional territory
   or language pattern drove performance]
```

### Output 2: Deepening Directive

When a winning pattern is identified, produce a directive for the Content Discovery Agent:

```
DEEPENING DIRECTIVE
Triggered by: [creative_id] outperformance on [metric]
Date: [date]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TARGET EMOTIONAL TERRITORY:
[Description of the emotional territory that performed —
e.g., "fear of accidentally harming a child with the wrong
herb, combined with identity as a protective parent"]

EVIDENCE:
- Winning creative used VOC items [list] which shared:
  - Copy-function: [PAIN + TRIGGER]
  - Emotional charge: [4-5]
  - Common language patterns: [list specific phrases]
  - Source content types: [controversy, personal_story]

NEW SEARCH TERMS FOR CONTENT DISCOVERY:
[10-15 new search terms designed to find more content in
this specific emotional territory]

PLATFORM PRIORITY:
[Which platform(s) produced the VOC that fed the winners]

VOLUME TARGET:
[How many new content pieces to discover and mine]

URGENCY:
[Based on spend level and scaling velocity]
```

### Output 3: VOC Value Scoring Update

Retroactively update VOC items with performance data:

```
VOC ITEMS THAT CONTRIBUTED TO WINNERS:
- V001-042: Used in 3 winning creatives. Performance contribution: HIGH.
  → Recommendation: MINE MORE in this emotional territory
- V001-112: Used in 2 winning creatives. Performance contribution: MEDIUM.
  → Recommendation: Use more frequently in creative generation

VOC ITEMS THAT CONTRIBUTED TO LOSERS:
- V001-067: Used in 2 losing creatives (only). Performance contribution: NEGATIVE.
  → Recommendation: De-prioritize this emotional territory for this angle.
  → Hypothesis: [why this VOC didn't translate to performance]
```

---

## The Feedback Cycle: When to Trigger

This agent does NOT run continuously. It runs at defined checkpoints:

### Trigger 1: Learning Phase Complete (First Trigger)
**When:** After each angle's first round of creatives has accumulated enough data for statistical significance.
- Minimum: 5 creatives per angle, each with 1,000+ impressions
- Preferred: 10+ creatives per angle, each with 5,000+ impressions
**Action:** Run the full Performance Attribution Report for all angles tested.

### Trigger 2: Winner Identified (Scaling Trigger)
**When:** A creative or angle shows clear outperformance against the primary KPI threshold.
- Threshold: CPA is >30% below target, or ROAS is >50% above target, sustained over 3+ days
**Action:** Run Deepening Directive for the winning angle/emotional territory. This triggers a new content discovery + scraping + processing cycle.

### Trigger 3: Creative Fatigue (Refresh Trigger)
**When:** A previously winning creative's performance degrades.
- Signal: CTR or thumb-stop rate drops >25% from peak, or CPA rises >30% from low
**Action:** Run Performance Attribution Report to identify which emotional territory produced the peak performance, then issue Deepening Directive to mine fresh VOC in that territory for new creatives.

### Trigger 4: Periodic Review (Maintenance Trigger)
**When:** Every 2 weeks during active campaign periods.
**Action:** Run full report across all angles and all creatives. Update VOC value scores. Identify emerging patterns and declining ones.

---

## The Traceability Architecture

### How "used_in" Tracking Works:

Every downstream agent that consumes the Language Bank or VOCC Dossier must implement this tracking:

```
When a copywriting agent uses a VOC item or language pattern
in a creative:

1. Log the creative_id
2. Log each voc_id used (directly or as inspiration)
3. Log each language_bank_item used
4. Log which copy section the item was used in (hook, body,
   proof, CTA, etc.)
5. Log the degree of modification:
   - "verbatim" — used exactly as extracted
   - "paraphrased" — modified for flow/compliance but kept
     the core language
   - "inspired" — the VOC item inspired the concept but the
     language is substantially different
```

**Why "inspired" tracking matters:** Even when a copywriter doesn't use exact customer language, the emotional territory they're writing in was chosen based on VOC. If a hook about "the 2am panic" performs well, it's because the emotional territory of late-night parental health anxiety resonates — even if the exact phrase "lying awake at 2am" wasn't used verbatim. Tracing "inspired" connections captures this.

---

## Agent Prompt (The Operational Instruction)

```
SYSTEM:

You are the Performance Feedback Loop Agent. Your job is to
analyze ad performance data, trace results back to the VOC items
and language patterns that produced them, and generate actionable
intelligence for the next cycle of content discovery and creative
generation.

You receive: ad performance data, creative-to-VOC traceability
maps, language banks, and angle dossiers. You:

1. Identify winning and losing creatives per angle
2. Trace winners and losers back to their VOC sources
3. Identify which emotional territories, copy-function types,
   and language patterns correlate with performance
4. Generate Performance Attribution Reports
5. When a winner is identified, generate a Deepening Directive
   with new search terms for the Content Discovery Agent
6. Update VOC items with performance-derived value scores

You do NOT generate copy. You do NOT scrape or discover content.
You do NOT classify or score VOC. You analyze performance and
produce intelligence.

TRIGGER CONDITIONS:
[Insert trigger conditions from above]

TRACEABILITY REQUIREMENTS:
[Insert traceability architecture from above]

INPUTS:
- Ad performance data: [INSERT]
- Creative-to-VOC traceability maps: [INSERT]
- Language Banks: [INSERT]
- Angle Dossiers: [INSERT]

OUTPUTS:
1. Performance Attribution Report (per angle)
2. Deepening Directive (when winner identified)
3. VOC Value Scoring Update

QUALITY RULES:
- Never attribute performance to a single VOC item when
  multiple factors are at play. Use correlation language,
  not causation language.
- Always note sample size and statistical confidence. If
  a pattern is based on 2 creatives with 500 impressions
  each, label it "low confidence — insufficient data."
- Separate platform-specific performance from angle-specific
  performance. An angle might win on TikTok but lose on
  Meta — that's a platform insight, not an angle verdict.
- When generating Deepening Directives, include BOTH the
  winning emotional territory AND adjacent territories
  worth exploring. Don't just mine more of the exact same
  thing — expand the radius slightly.
- Always include a "what could change this conclusion"
  section — what data would invalidate the current
  attribution hypothesis.
```

---

## Tools This Agent Has Access To

| Tool | Purpose | Access Level |
|---|---|---|
| Read (ad performance data) | Ingest campaign metrics | Read-only |
| Read (traceability maps) | Connect creatives to VOC sources | Read-only |
| Read (Language Banks) | Reference extracted language patterns | Read-only |
| Read (Angle Dossiers) | Reference full angle research context | Read-only |
| Read (Content Discovery logs) | Reference which content was mined and what yield it produced | Read-only |
| Write (Attribution Report) | Output performance analysis | Write (new file) |
| Write (Deepening Directive) | Output intelligence for Content Discovery Agent | Write (new file) |
| Write (VOC Value Update) | Update VOC items with performance data | Write (append to dossier) |

**Tools explicitly NOT available:** Ad platform APIs (this agent reads exported data, it doesn't pull it), web scraping, copy generation, VOC classification/scoring.

---

## Evaluation Criteria

### Attribution Quality Check:

| Criterion | Pass | Fail |
|---|---|---|
| Statistical basis | Conclusions based on 5+ creatives with 1,000+ impressions each | Conclusions based on 1-2 creatives or <500 impressions |
| Traceability completeness | >80% of winning creatives have complete VOC traceability maps | <50% have traceability (system isn't logging properly) |
| Pattern identification | Identified 2+ shared characteristics among winning creatives | No patterns identified, or patterns are trivially obvious |
| Hypothesis quality | Hypothesis is specific, testable, and tied to VOC data | Hypothesis is vague ("better creative") or unfalsifiable |
| Confidence labeling | Every conclusion labeled with confidence level | Conclusions stated as fact without confidence context |

### Deepening Directive Quality Check:

| Criterion | Pass | Fail |
|---|---|---|
| Search term relevance | New search terms are clearly derived from the winning emotional territory | Search terms are generic or don't map to the identified pattern |
| Specificity | Directive names the specific emotional territory, not just the angle | Directive says "find more content about this angle" |
| Actionability | Content Discovery Agent could execute immediately without clarification | Directive requires interpretation or additional briefing |
| Adjacent territory inclusion | Includes 2-3 adjacent territories worth exploring, not just the exact same territory | Only repeats the exact winning territory (risks diminishing returns) |

### Feedback Loop Velocity:

| Metric | Target | Warning |
|---|---|---|
| Time from trigger to report | <24 hours | >72 hours (loop is too slow to influence next creative cycle) |
| Time from directive to new VOC | <1 week | >2 weeks (pipeline is bottlenecked) |
| Cycles per month (during active campaigns) | 2-4 | <1 (not iterating fast enough) or >8 (churning without learning) |

---

## Downstream Consumers

| Consumer | What It Receives |
|---|---|
| Content Discovery Agent (Workflow 3) | Deepening Directives with new search terms and platform priorities |
| Language Pattern Extraction Agent (Workflow 5) | Updated VOC value scores (prioritize extracting from high-value VOC in next cycle) |
| Copywriting Agents | Performance Attribution Report (which emotional territories to emphasize in next creative batch) |
| Human Decision-Makers | Summary intelligence for angle scaling/killing decisions |

---

## Why This Matters From a DR First Principles Perspective

The companies that dominate paid media over multi-year periods all have one thing in common: they've built a compounding creative intelligence loop. Agora Financial can outspend competitors on cold traffic not because their first ad was brilliant, but because their 50th ad was informed by the performance of their first 49 — and each iteration was traced back to which customer insights drove results.

Without a feedback loop, your creative production is a random walk. With one, it's a guided search that gets more efficient with every cycle. The first cycle is your most expensive and least informed. The 10th cycle benefits from the performance data of the previous 9.

This agent is the mechanism that turns ad spend from an expense into an investment in creative intelligence. Every dollar you spend on ads produces not just conversions, but data about which emotional territories resonate — data that makes your next dollar more effective.

Build the traceability architecture into every upstream agent now. Turn this agent on when you have data flowing. The earlier you close the loop, the faster your creative quality compounds.
