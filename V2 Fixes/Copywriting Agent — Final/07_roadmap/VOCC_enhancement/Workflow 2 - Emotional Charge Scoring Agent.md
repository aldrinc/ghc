# Workflow 2: Emotional Charge Scoring Agent

## Agent Identity

**Role:** VOC Emotional Intensity Analyst
**Narrow Job:** Take taxonomy-tagged VOC items and assign an emotional charge score (1-5) to each item based on specific linguistic features. The agent does NOT classify by copy function (Workflow 1 does that), does NOT extract language patterns (Workflow 5 does that), and does NOT make quality/relevance judgments. It only scores emotional intensity.

**Why This Agent Exists (First Principles):**
In direct response copywriting, the raw material of persuasion is emotion — not information. A comment that says "herbs are helpful for sleep" contains information but zero emotional charge. A comment that says "I literally sobbed the first morning I woke up rested after three years of staring at the ceiling at 2am" contains the same information wrapped in visceral, specific emotion that a copywriter can almost directly transplant into body copy.

The top 0.1% of DR copywriters have an intuitive "highlighter test" — when reading through customer research with a marker in hand, they highlight the quotes that make them feel something. The quotes that make the reader's stomach tighten, eyes widen, or head nod involuntarily. Those are the 4s and 5s. Everything else is supporting evidence.

This agent codifies that highlighter instinct into a repeatable, auditable scoring system so that downstream agents can prioritize high-charge items for hooks, headlines, and key copy moments — while still having access to lower-charge items for pattern validation and structural support.

---

## Inputs

| Input | Source | Required? |
|---|---|---|
| Taxonomy-tagged VOC items | VOC Taxonomy Agent (Workflow 1) output | Yes |
| Angle definition | Purple Ocean Scorecard / Angle Selection output | Yes |
| Product category | User-defined at project init | Yes |

Each VOC item arrives with:
- All original fields (text, source, URL, date, etc.)
- Taxonomy tags from Workflow 1 (primary_function, all_functions, tagging_rationale, copy_usage_hint)

---

## Outputs

Each VOC item exits this agent with the following fields added:

```
{
  // === All existing fields preserved ===
  "voc_id": "V001",
  "text": "[original verbatim text]",
  "primary_function": "PAIN",
  "all_functions": ["PAIN", "TRIGGER"],
  // ...

  // === ADDED BY THIS AGENT ===
  "emotional_charge": 4,
  "charge_rationale": "Contains named timeframe ('three years'), sensory detail ('staring at the ceiling at 2am'), emotional extremity ('literally sobbed'), and before/after contrast. Hits 4 of 5 linguistic markers for Level 4.",
  "charge_markers_present": ["named_timeframe", "sensory_detail", "emotional_extremity", "contrast_statement"],
  "copy_tier": "A-tier: headline/hook candidate"
}
```

---

## The Scoring Rubric: 5 Levels

### The 5 Linguistic Markers That Determine Charge

Before scoring, the agent identifies which of these 5 markers are present in the text:

1. **Named Timeframe** — The speaker includes a specific time reference ("after 4 weeks," "for 3 years," "since my daughter was born," "every night at 2am"). Timeframes ground abstract experiences in lived reality.

2. **Sensory/Physical Detail** — The speaker uses language that engages the senses or describes a physical state ("the knot between my shoulder blades," "staring at the ceiling," "my hands were shaking," "I could finally breathe"). Sensory language creates mental images.

3. **Emotional Extremity** — The speaker uses intensifiers, superlatives, or language that signals strong feeling ("literally changed my life," "I was terrified," "the best thing I've ever," "I sobbed," "I can't even describe how," "miracle"). Extremity signals genuine emotional activation (not always — see calibration notes below).

4. **Contrast Statement** — The speaker juxtaposes a before-state and after-state, or contrasts expectations vs. reality ("I went from [X] to [Y]," "I thought it would be [X] but it was actually [Y]," "before I found this, I was [X] — now I'm [Y]"). Contrast creates narrative tension.

5. **Identity/Stakes Language** — The speaker connects the experience to their identity, relationships, or life stakes ("as a mother," "I almost lost my marriage over this," "I felt like a failure," "I can finally be there for my kids," "I felt like myself again"). Stakes language signals that the experience matters beyond the surface level.

---

### Scoring Levels

**Level 1 — Neutral/Factual (0-1 markers)**
- **What it sounds like:** A statement of fact or mild opinion with no emotional language. Could be a textbook sentence.
- **Marker count:** 0-1 markers present, and the one present is weak/generic.
- **Copy tier:** D-tier — pattern validation only. Useful for confirming a theme exists, but not usable in copy.
- **Example:** "Herbs can be helpful for sleep issues."
- **Example:** "I use chamomile tea sometimes."
- **Example:** "Valerian root has some evidence for insomnia."

**Level 2 — Mild Sentiment (1 marker, or 2 weak markers)**
- **What it sounds like:** Expresses a clear positive or negative opinion, but in generic terms. The reader can identify the sentiment but doesn't *feel* anything.
- **Marker count:** 1 clear marker, or 2 markers that are generic/weak.
- **Copy tier:** C-tier — supporting evidence. Can validate themes or fill out a proof section, but won't drive creative decisions.
- **Example:** "I've been taking ashwagandha and it helps with my stress." (mild positive, no specificity)
- **Example:** "Herbs are confusing to learn about." (mild negative, no detail)
- **Example:** "I wish there was a simpler guide to herbs." (mild desire, no urgency)

**Level 3 — Clear Emotion With Specificity (2-3 markers)**
- **What it sounds like:** The reader can identify the specific emotion AND the specific context. There's enough detail to create a mental image, but the language isn't yet visceral enough to stop a reader cold.
- **Marker count:** 2-3 markers present, at least one strong.
- **Copy tier:** B-tier — body copy integration. Strong enough for agitation paragraphs, proof blocks, and supporting testimonial-style sections. Not yet headline material.
- **Example:** "After 6 months of trying different supplements, I finally found one that actually helped my sleep. I'm not waking up at 3am anymore." (named timeframe + contrast, but language is measured)
- **Example:** "I'm scared to give my kids any herbs because every source says something different about what's safe." (emotional extremity [scared] + stakes language [kids], but no sensory detail)
- **Example:** "I spent $300 on supplements last month and honestly I'm not sure any of them are doing anything." (named timeframe [last month] + emotional language [honestly, not sure], but no sensory or contrast)

**Level 4 — Strong Emotion With Specific Detail (3-4 markers)**
- **What it sounds like:** The reader feels a gut reaction. The quote creates a vivid mental image or an emotional response. A copywriter would highlight this and write "USE THIS" in the margin.
- **Marker count:** 3-4 markers present, at least two strong.
- **Copy tier:** A-tier — headline/hook candidate. These items can be paraphrased into hooks, used as the emotional anchor of an agitation section, or adapted into high-impact proof/testimonial blocks.
- **Example:** "I've literally got my life back!! After 4 weeks I was laughing, happy, no longer dragging myself through each day." (emotional extremity [literally, life back] + named timeframe [4 weeks] + contrast [dragging myself vs. laughing, happy] + sensory detail [dragging])
- **Example:** "I took kava for anxiety and ended up with elevated liver enzymes. I thought 'natural' meant no side effects. Lesson learned." (contrast [thought natural = safe vs. liver damage] + named consequence [elevated liver enzymes] + identity/stakes [health scare])
- **Example:** "I almost feel like I'm a naughty girl when I mention herbs to my doctor." (identity language [naughty girl] + emotional extremity [almost feel like] + stakes [doctor relationship])

**Level 5 — Visceral, Reader-Stopping (4-5 markers, all strong)**
- **What it sounds like:** The quote would stop a reader mid-scroll if it appeared in ad copy. It's so specific, so emotionally raw, and so vivid that it feels like eavesdropping on someone's private moment. These are rare — expect 5-10% of a cleaned corpus at most.
- **Marker count:** 4-5 markers, all strong. The quote essentially tells a complete emotional micro-story.
- **Copy tier:** S-tier — potential headline, hook, or the emotional centerpiece of an entire ad/page. Handle with care — these are your most valuable creative assets.
- **Example:** "After a very costly 3-day hospital stay, I wanted another way. I've been diving into herbalism ever since, and it has given me purpose and hope." (named timeframe [3-day] + stakes [hospital, costly] + emotional extremity [purpose and hope] + contrast [hospital nightmare vs. herbalism hope] + identity [the seeker])
- **Example:** "I was terrified I'd accidentally poison my kid with the wrong herb — I'd lie awake at night imagining the ER visit. That fear is what finally pushed me to actually study this properly instead of Googling at midnight." (emotional extremity [terrified, poison] + sensory [lie awake at night, imagining ER] + stakes/identity [my kid, mother] + trigger [fear pushed me] + contrast [Googling at midnight vs. studying properly])

---

## Calibration Notes (Edge Cases)

### When Emotional Extremity is Fake or Habitual
Some platforms (especially TikTok) have cultural norms where hyperbolic language is standard ("this LITERALLY changed my life" about a face wash). The agent must calibrate for platform norms:
- **On TikTok/Instagram:** Discount emotional extremity markers by one level unless accompanied by specific detail. "This changed my life" without detail = Level 2 on TikTok (it's just platform vernacular), but Level 3 on a health forum (where it's a genuine statement).
- **On Reddit/forums:** Emotional extremity is more likely to be genuine because the platform norms are more measured.
- **On YouTube:** Moderate calibration — longer comments tend to be more considered, but superlatives are still common.

### When Brevity Masks Charge
Very short comments can carry high emotional charge through implication: "Never again." / "This saved my marriage." / "I wish someone had told me." These items may only hit 1-2 explicit markers but carry a density of emotional implication. The agent may score these up by one level with a note: "charge_rationale: Brevity + implication density. Score adjusted +1."

### When Length Dilutes Charge
Very long comments (200+ words) may contain Level 4-5 moments buried in Level 1-2 narration. The agent should:
1. Score the comment based on its highest-charge passage
2. Note in `charge_rationale`: "Peak charge at Level [X] in passage: '[quote the peak passage]'. Surrounding text is Level [Y]. Language Pattern Extraction Agent should isolate the peak passage."

---

## Agent Prompt (The Operational Instruction)

```
SYSTEM:

You are the Emotional Charge Scoring Agent. Your sole job is to
assess the emotional intensity of pre-classified VOC items on a
1-5 scale.

You receive taxonomy-tagged VOC items. For each item, you:
1. Read the verbatim text
2. Identify which of the 5 linguistic markers are present:
   - Named Timeframe
   - Sensory/Physical Detail
   - Emotional Extremity
   - Contrast Statement
   - Identity/Stakes Language
3. Assign an emotional charge score (1-5) based on marker count
   and strength
4. Write a charge rationale citing specific language from the text
5. List which markers are present
6. Assign a copy tier (S/A/B/C/D)

You do NOT re-classify the copy function tags. You do NOT extract
patterns. You do NOT edit the text. You ONLY score emotional
intensity.

SCORING RUBRIC:
[Insert full rubric from above]

CALIBRATION NOTES:
[Insert calibration notes from above]

INPUTS:
- Angle definition: [INSERT]
- Product category: [INSERT]
- Tagged VOC items to score: [INSERT BATCH]

OUTPUT FORMAT (for each item):
{
  "voc_id": "[existing ID]",
  "emotional_charge": [1-5],
  "charge_rationale": "[cites specific language]",
  "charge_markers_present": ["marker1", "marker2"],
  "copy_tier": "[S/A/B/C/D]-tier: [brief description]"
}

QUALITY RULES:
- Never score based on the topic's inherent emotionality. A
  comment about cancer that says "cancer is a serious disease" is
  Level 1. A comment about tea preferences that says "the day I
  found that blend was the day I stopped dreading mornings" is
  Level 4. Score the LANGUAGE, not the TOPIC.
- Always cite specific words/phrases from the text in your
  rationale. "This feels emotional" is not a valid rationale.
- Apply platform calibration for emotional extremity markers.
- If a long comment has mixed charge levels, score by peak
  charge and note the dilution.
- Expect a distribution roughly matching: Level 1 (10-15%),
  Level 2 (25-30%), Level 3 (30-35%), Level 4 (15-20%),
  Level 5 (5-10%). If your distribution is heavily skewed,
  recalibrate.
```

---

## Tools This Agent Has Access To

| Tool | Purpose | Access Level |
|---|---|---|
| Read (tagged VOC items) | Ingest tagged VOC batches for scoring | Read-only |
| Write (scored output) | Output scored items to the angle dossier staging area | Write (append-only to dossier) |
| Read (Angle definition) | Reference angle context for relevance calibration | Read-only |

**Tools explicitly NOT available:** Web search, scraping, classification tools, extraction tools. This agent scores. That's it.

---

## Evaluation Criteria

### Per-Item Accuracy Check (run on a sample of 20 items per batch):

| Criterion | Pass | Fail |
|---|---|---|
| Score is within 1 point of human assessment | Agent scores 3, human scores 3 or 4 | Agent scores 1, human scores 4 (off by 3+) |
| Rationale cites specific language | "Contains 'literally sobbed' (emotional extremity) and '3 years' (named timeframe)" | "This seems emotional" |
| Markers correctly identified | All present markers listed; no phantom markers claimed | Marker listed that isn't in the text, or obvious marker missed |
| Platform calibration applied | TikTok hyperbole discounted; forum sincerity weighted | TikTok "literally changed my life" scored as Level 4 without supporting detail |
| Copy tier matches score | Score 4 = A-tier, Score 2 = C-tier | Score and tier are inconsistent |

### Batch-Level Distribution Check:

| Check | Healthy | Unhealthy |
|---|---|---|
| Score distribution | Roughly bell-curved: 10-15% L1, 25-30% L2, 30-35% L3, 15-20% L4, 5-10% L5 | >50% at any single level (agent is defaulting) |
| L4-5 density | 20-30% of cleaned corpus | <10% (under-scoring, too conservative) or >50% (over-scoring, too generous) |
| Rationale quality | Every rationale cites specific text | >20% of rationales are generic |

### The Highlighter Test (Ground Truth Validation):

Have a human (ideally someone with DR copywriting experience) read through 50 VOC items and physically highlight the ones they'd want to use in copy. Compare the human's highlights to the agent's Level 4-5 items. Overlap should be >75%. If it's lower, the scoring rubric needs recalibration — either the markers aren't capturing what makes copy "land," or the thresholds are wrong.

---

## Downstream Consumers

| Consumer Agent | How It Uses Scores |
|---|---|
| Headline/Hook Agent | Filters for Level 4-5 items only; these are the raw material for hooks |
| Agitation Copy Agent | Prioritizes Level 3-5 `[PAIN]` items; uses Level 1-2 for theme validation |
| Proof/Social Proof Agent | Prioritizes Level 4-5 `[PROOF]` items for featured testimonials; Level 2-3 for supporting proof density |
| Language Pattern Extraction Agent (Workflow 5) | Focuses extraction effort on Level 3-5 items (where the "money phrases" live) |
| Angle Dossier Assembly | Sorts items by score within each copy-function category; presents highest-charge items first |

---

## Why This Matters From a DR First Principles Perspective

Eugene Schwartz said the copywriter's job is not to create desire but to *channel* existing desire. The Emotional Charge Score is a direct measurement of how much desire (or pain, or fear, or hope) is already encoded in a piece of customer language.

A Level 5 VOC item is a customer doing 80% of the copywriter's job for them. The words are already chosen. The emotion is already present. The specificity is already there. The copywriter's (or agent's) job is to recognize it, preserve it, and position it correctly in the page architecture.

A system that can reliably identify these items — and separate them from the noise of Level 1-2 filler — has a structural advantage over any competitor whose research process treats all customer language as equal. It isn't. Some quotes are worth 100x more than others. This agent finds them.
