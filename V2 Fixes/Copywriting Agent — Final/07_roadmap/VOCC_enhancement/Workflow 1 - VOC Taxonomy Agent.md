# Workflow 1: VOC Taxonomy Agent (Copy-Function Tagging)

## Agent Identity

**Role:** VOC Classification Specialist
**Narrow Job:** Take raw, cleaned VOC items and assign one or more copy-function tags + a primary function designation to each item. The agent does NOT collect VOC, does NOT score it emotionally, and does NOT extract language patterns. It only classifies.

**Why This Agent Exists (First Principles):**
A pile of customer quotes is not research. Research becomes operational when every data point has a known *use* in the system. In direct response copywriting, every piece of customer language serves a specific function in the final copy: it either describes pain (feeds agitation sections), expresses desire (feeds aspiration/CTA copy), reveals an objection (feeds FAQ/risk reversal), captures a trigger moment (feeds hooks), etc.

Without classification, downstream copywriting agents must re-read the entire corpus every time and make ad-hoc relevance judgments. This wastes context window, introduces inconsistency, and degrades output quality. The top 0.1% of DR operators solve this by classifying VOC at the point of collection so it can be retrieved by function — the way a warehouse labels inventory by SKU, not by "stuff we bought."

---

## Inputs

| Input | Source | Required? |
|---|---|---|
| Cleaned VOC items (post-noise-removal) | Quality Pipeline Agent (Workflow 4) output | Yes |
| Angle definition | Purple Ocean Scorecard / Angle Selection output | Yes |
| Product category | User-defined at project init | Yes |
| Avatar Brief | Foundational Docs | Recommended (improves tagging accuracy) |

Each VOC item arrives with at minimum:
- `text` (the verbatim comment/quote)
- `source_platform` (TikTok, YouTube, Instagram, Reddit, forum, review site, etc.)
- `source_url`
- `date` (if available)
- `parent_content_description` (what the comment was in response to)

---

## Outputs

Each VOC item exits this agent with the following fields added:

```
{
  "voc_id": "V001",
  "text": "[original verbatim text]",
  "source_platform": "tiktok",
  "source_url": "...",
  "date": "2025-11-14",
  "parent_content_description": "TikTok video about herb-drug interactions",

  // === ADDED BY THIS AGENT ===
  "primary_function": "PAIN",
  "all_functions": ["PAIN", "TRIGGER"],
  "tagging_rationale": "Speaker describes a specific negative experience (elevated liver enzymes from kava) that serves as cautionary pain language. Also functions as a trigger because it describes the moment of realization.",
  "copy_usage_hint": "Agitation section (specific adverse experience narrative); hook material (cautionary 'I thought natural meant safe' reframe)"
}
```

---

## The Taxonomy: 8 Copy-Function Tags

### Tag Definitions (Use These Exactly)

**1. `[PAIN]` — Problem/Frustration Language**
- **Definition:** The speaker describes a negative state, problem, frustration, or undesirable situation they are currently in or have experienced.
- **Copy function:** Feeds agitation sections, problem-aware hooks, "you know that feeling when..." copy, empathy-building before solution introduction.
- **Signal words/patterns:** "I'm struggling with," "I can't," "it's so frustrating," "I've been dealing with," "nothing works," "I'm tired of," describing symptoms, describing failed attempts.
- **Boundary rule:** The statement must describe an experienced or ongoing negative state. Hypothetical fears about things that haven't happened = `[OBJECTION]`, not `[PAIN]`.

**Examples:**
- "I bought like 10 different herb books and I'm still lost" = `[PAIN]` (experienced confusion)
- "I wasted $10k+ on tests and supplements" = `[PAIN]` (experienced financial loss)
- "Every website says something different" = `[PAIN]` (experienced information overload)

---

**2. `[DESIRE]` — Aspiration/Outcome Language**
- **Definition:** The speaker describes a wanted outcome, aspiration, positive future state, or goal they are working toward.
- **Copy function:** Feeds aspiration copy, solution-aware hooks, CTA framing, transformation narratives, "imagine if..." sections.
- **Signal words/patterns:** "I want to," "I wish," "my goal is," "I just want to be able to," "wouldn't it be great if," describing a positive future state, describing what success looks like.
- **Boundary rule:** The statement must express a desired positive state. Describing a positive experience they've already had = `[PROOF]`, not `[DESIRE]`.

**Examples:**
- "I just want to know what to reach for at 2am without panicking" = `[DESIRE]`
- "Help parents confidently choose the right herbal remedies for their children" = `[DESIRE]`
- "I want another way" = `[DESIRE]`

---

**3. `[TRIGGER]` — Decision Moment Language**
- **Definition:** The speaker describes a specific moment, event, realization, or circumstance that prompted them to take action (start searching, buying, switching, quitting).
- **Copy function:** Feeds hook copy (the "moment of activation" that cold traffic recognizes), "the moment I decided..." narratives, retargeting copy that references the decision catalyst.
- **Signal words/patterns:** "That's when I realized," "after [specific event] I decided," "the last straw was," "when [thing] happened, I knew I had to," "I finally snapped when."
- **Boundary rule:** Must describe a specific precipitating event or moment, not a general ongoing state. "I've always been interested in herbs" = NOT a trigger. "After my 3-day hospital stay, I decided to learn herbalism" = `[TRIGGER]`.

**Examples:**
- "After a very costly 3-day hospital stay, I wanted another way" = `[TRIGGER]`
- "When cold and flu season arrives, I will be ready" = `[TRIGGER]` (anticipatory trigger)
- "PSA: If you're on SSRIs, do NOT combine with St. John's Wort. I learned the hard way" = `[TRIGGER]`

---

**4. `[OBJECTION]` — Skepticism/Pushback Language**
- **Definition:** The speaker expresses doubt, skepticism, a reason for not acting, a fear about a potential negative outcome, or pushback against a claim or product category.
- **Copy function:** Feeds FAQ sections, risk reversal copy, objection-handling blocks, "but what about..." preemptive responses, guarantee framing.
- **Signal words/patterns:** "But what if," "I'm worried that," "how do I know," "what about [risk]," "sounds too good to be true," "I'm skeptical because," "the problem is," describing fears about what MIGHT happen.
- **Boundary rule:** The statement must express resistance to action or doubt about a claim/approach. Describing something bad that DID happen = `[PAIN]`. Describing something bad that MIGHT happen = `[OBJECTION]`.

**Examples:**
- "What if it interacts with my meds?" = `[OBJECTION]`
- "Another AI-generated herb book" = `[OBJECTION]`
- "I can just Google this" = `[OBJECTION]`
- "natural doesn't always mean safe" = `[OBJECTION]`

---

**5. `[COMPARISON]` — Alternative/Competitor Language**
- **Definition:** The speaker describes their experience with alternatives, competitors, substitutes, or prior solutions — including what worked, what didn't, and why they switched or are considering switching.
- **Copy function:** Feeds differentiation copy, "I tried X but..." sections, mechanism sections that explain why this approach is different, competitive positioning.
- **Signal words/patterns:** "I tried [X] and it didn't," "compared to [X]," "[X] worked for a while but then," "I switched from [X] because," "unlike [X], this actually."
- **Boundary rule:** Must reference a specific alternative, competitor, or prior approach. General frustration without naming what was tried = `[PAIN]`, not `[COMPARISON]`.

**Examples:**
- "I took kava for anxiety and ended up with elevated liver enzymes" = `[COMPARISON]` (tried specific alternative)
- "Tried valerian, hops, passionflower -- the whole 'sleep herb' combo -- and it did zilch" = `[COMPARISON]`
- "I've tried all these 'miracle' supplements -- ashwagandha, turmeric, magnesium -- and nothing really changed" = `[COMPARISON]`

---

**6. `[PROOF]` — Positive Experience/Endorsement Language**
- **Definition:** The speaker describes a positive experience, result, outcome, or endorsement of a product, approach, or remedy they have personally used.
- **Copy function:** Feeds testimonial-style copy, social proof blocks, "real results" sections, credibility cascades, before/after narratives.
- **Signal words/patterns:** "It worked," "I noticed a difference," "this changed my life," "I've been using [X] for [time] and," "I recommend," "5 stars," describing specific positive results.
- **Boundary rule:** Must be about a past or present positive experience, not a future desire. "I want to feel better" = `[DESIRE]`. "I feel 100 times better" = `[PROOF]`.

**Examples:**
- "I've literally got my life back!! After 4 weeks I was laughing, happy" = `[PROOF]`
- "I feel 100 times better... I feel calm" = `[PROOF]`
- "St. John's Wort saved my life" = `[PROOF]`

---

**7. `[MECHANISM]` — Curiosity/Understanding Language**
- **Definition:** The speaker asks about, explains, or expresses curiosity about *how* something works — the underlying process, science, method, or reason behind an outcome.
- **Copy function:** Feeds mechanism sections in copy, "here's why it works" blocks, scientific credibility passages, curiosity-driven hooks.
- **Signal words/patterns:** "How does [X] actually work?" "The reason [X] works is because," "I read that [compound] does [thing]," "the science behind," "what's the mechanism," "ELI5 how."
- **Boundary rule:** Must express curiosity about or explanation of a process/mechanism. Asking "does it work?" = `[OBJECTION]`. Asking "HOW does it work?" = `[MECHANISM]`.

**Examples:**
- "Aspirin comes from willow bark. People chewed willow bark for pain since ancient Egypt. Modern medicine isolated the compound" = `[MECHANISM]`
- "It seems to have balanced out whatever was wrong in my brain" = `[MECHANISM]` (naive mechanism hypothesis)
- "Red Clover contains estrogen-like stuff" = `[MECHANISM]`

---

**8. `[IDENTITY]` — Self-Description/Group Membership Language**
- **Definition:** The speaker describes who they are, what group they belong to, how they see themselves, or what values/beliefs define their self-concept in relation to the product category.
- **Copy function:** Feeds audience targeting copy, "this is for people who..." framing, identity-resonance hooks, community-building language, ad targeting persona definitions.
- **Signal words/patterns:** "As a [role/identity]," "I'm the kind of person who," "I'm not [X], I'm [Y]," "we [group]," "I consider myself," descriptions of lifestyle, values, or worldview.
- **Boundary rule:** Must be about who the person IS or how they self-identify. Describing what they WANT = `[DESIRE]`. Describing who they ARE = `[IDENTITY]`.

**Examples:**
- "I'm not anti-medicine. I'm anti-guessing." = `[IDENTITY]`
- "As a prepper, it's important to feel confident" = `[IDENTITY]`
- "crunchy but not crazy" = `[IDENTITY]`
- "Every time I stir a pot of herbal salve, I imagine generations of wise women behind me" = `[IDENTITY]`

---

## Dual-Tagging Rules

Most VOC items serve more than one copy function. The agent must:

1. **Always assign a `primary_function`** — the single most prominent copy function this item would serve. Ask: "If I could only use this quote in ONE section of copy, which section would it go in?"

2. **Assign `all_functions`** — every applicable tag. A single comment can legitimately be `[PAIN]` + `[TRIGGER]` + `[COMPARISON]`.

3. **Decision priority for primary function (when ambiguous):**
   - If the comment describes a specific moment that led to action → primary = `[TRIGGER]`
   - If the comment names specific alternatives tried → primary = `[COMPARISON]`
   - If the comment expresses resistance/doubt about future action → primary = `[OBJECTION]`
   - If the comment describes a result (positive or negative) from personal experience → primary = `[PROOF]` or `[PAIN]`
   - If the comment describes who the person is → primary = `[IDENTITY]`
   - If the comment asks or explains how something works → primary = `[MECHANISM]`
   - Default tiebreaker: which function is most scarce in the current corpus for this angle?

4. **Maximum tags per item:** 3. If more than 3 apply, the comment is likely long enough to split into fragments (handled by Language Pattern Extraction Agent in Workflow 5).

---

## Agent Prompt (The Operational Instruction)

```
SYSTEM:

You are the VOC Taxonomy Agent. Your sole job is to classify Voice
of Customer items by their copy function.

You receive cleaned VOC items. For each item, you:
1. Read the verbatim text
2. Determine the primary copy function (one of 8 tags)
3. Determine all applicable copy functions (max 3)
4. Write a 1-2 sentence tagging rationale
5. Write a copy usage hint (which section(s) of copy this item
   would serve)

You do NOT edit, summarize, or paraphrase the text. You do NOT
score emotional intensity. You do NOT extract language patterns.
You ONLY classify.

TAXONOMY REFERENCE:
[Insert full taxonomy from above]

DUAL-TAGGING RULES:
[Insert dual-tagging rules from above]

INPUTS:
- Angle definition: [INSERT]
- Product category: [INSERT]
- VOC items to classify: [INSERT BATCH]

OUTPUT FORMAT (for each item):
{
  "voc_id": "[existing ID]",
  "primary_function": "[TAG]",
  "all_functions": ["[TAG1]", "[TAG2]"],
  "tagging_rationale": "[1-2 sentences]",
  "copy_usage_hint": "[which copy sections this feeds]"
}

QUALITY RULES:
- Never tag based on what the comment COULD mean with generous
  interpretation. Tag based on what it ACTUALLY says.
- If a comment is ambiguous and could reasonably be two primary
  functions, choose the one that is more scarce in the current
  batch (balances the corpus).
- If a comment doesn't clearly fit any tag, flag it as
  "UNCLASSIFIED" with a note explaining why. Do not force a tag.
- Preserve exact original text. Never alter, truncate, or
  paraphrase.
```

---

## Tools This Agent Has Access To

| Tool | Purpose | Access Level |
|---|---|---|
| Read (VOC items) | Ingest cleaned VOC batches for classification | Read-only |
| Write (tagged output) | Output classified items to the angle dossier staging area | Write (append-only to dossier) |
| Read (Angle definition) | Reference the angle being classified for to maintain relevance context | Read-only |
| Read (Avatar Brief) | Reference audience profile for edge-case classification decisions | Read-only (optional) |

**Tools explicitly NOT available:** Web search, scraping, content discovery, scoring tools. This agent does not gather data or make quality judgments. It classifies.

---

## Evaluation Criteria

### Per-Item Accuracy Check (run on a sample of 20 items per batch):

| Criterion | Pass | Fail |
|---|---|---|
| Primary function tag is correct | The tag matches what a senior DR copywriter would assign | The tag is wrong or forced |
| All-functions tags are complete | No obvious applicable function is missing | A clearly applicable function was omitted |
| All-functions tags are precise | No irrelevant functions included | A tag was applied that doesn't fit the text |
| Tagging rationale is defensible | The rationale explains WHY the tag applies, referencing specific language in the text | Rationale is generic ("this sounds like pain") without pointing to specific words |
| Copy usage hint is actionable | A copywriting agent could read the hint and know which section to use this in | Hint is vague ("could be used in copy") |
| Original text is unaltered | Verbatim text preserved exactly | Text was edited, truncated, or paraphrased |

### Batch-Level Distribution Check:

| Check | Healthy | Unhealthy |
|---|---|---|
| Tag distribution | All 8 tags represented (at least 1 each, ideally >5% each for tags 1-6) | 80%+ of items tagged as one function (likely systematic misclassification) |
| Dual-tag rate | 40-70% of items have 2+ tags | <20% dual-tagged (under-tagging) or >90% dual-tagged (over-tagging) |
| UNCLASSIFIED rate | <10% of items | >20% (indicates taxonomy doesn't cover this domain, or agent is too conservative) |
| Primary function diversity | No single primary function >40% of corpus | One primary function dominates (likely the agent is defaulting) |

### Calibration Test (Run Before First Production Batch):

Take 10 VOC items from the existing Deep Research corpus. Have the agent classify them. Compare to a human-generated "ground truth" classification. If agreement is <80% on primary function, review the taxonomy definitions with the agent and re-calibrate before proceeding.

---

## Downstream Consumers

| Consumer Agent | What It Pulls | Tags It Filters By |
|---|---|---|
| Headline/Hook Agent | High-charge items for hook concepts | `[TRIGGER]`, `[PAIN]`, `[IDENTITY]` |
| Agitation Copy Agent | Problem language for agitation sections | `[PAIN]`, `[TRIGGER]`, `[COMPARISON]` |
| Mechanism Copy Agent | How-it-works language | `[MECHANISM]`, `[PROOF]` |
| Proof/Social Proof Agent | Positive experience language | `[PROOF]`, `[IDENTITY]` |
| FAQ/Objection Agent | Skepticism and pushback language | `[OBJECTION]`, `[COMPARISON]` |
| CTA/Aspiration Agent | Desired outcome language | `[DESIRE]`, `[IDENTITY]` |
| Ad Targeting Agent | Audience self-description language | `[IDENTITY]`, `[TRIGGER]` |

---

## Why This Matters From a DR First Principles Perspective

The top direct response copywriters don't write from inspiration. They write from classified research. When Gary Halbert sat down to write, he had a stack of customer letters sorted by type. When Agora's research teams prepare a brief for a copywriter, every piece of research is tagged by what copy section it serves.

The classification step is what turns a pile of customer quotes into a *system* that produces predictable, high-quality copy. Without it, you have a library with no catalog — every book is there, but finding the right one takes as long as reading them all.

This agent is the catalog.
