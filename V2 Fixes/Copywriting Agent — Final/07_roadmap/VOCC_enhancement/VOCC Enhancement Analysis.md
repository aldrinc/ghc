# VOCC Enhancement Workstream: Strategic Analysis

## What This Document Is

An analysis of the proposed "VOCC Enhancement" workstream — a separate pipeline that scrapes angle-specific Voice of Customer (VOC) data from social platforms after Purple Ocean angle selection. This document evaluates the approach through the lens of what the top 0.1% of professional direct response marketers actually do when building angle-specific customer research at scale.

---

## 1. The Core Problem You've Correctly Identified

Your Purple Ocean Web Research prompt currently does two jobs in one pass:

1. **Angle discovery** — identify 10-30 candidate angles from VOC + competitor analysis
2. **VOC collection** — gather ~200+ VOC items to support those angles

The problem: when you discover 10+ viable angles, your ~200 VOC items get spread thin. Each angle might only have 8-20 supporting quotes. That's enough to *validate* an angle exists, but it's not enough to *write from*.

**This is the right diagnosis.** Here's why it matters so much:

The difference between a $2 CPM creative and a $0.40 CPM creative is almost never the offer, the product, or even the angle selection. It's whether the copywriter had access to the *specific emotional language* that makes a particular segment feel personally addressed. Generic VOCC gives you generic copy. Angle-specific VOCC gives you copy that makes the reader think "are they reading my mind?"

What the top performers understand: **VOC isn't just research input — it's the raw material of the copy itself.** The best hooks, the best body copy, the best testimonial framing — they're all derivatives of real customer language. Thin VOC per angle means thin copy per angle.

---

## 2. What the Top 0.1% Actually Do (And How It Maps to Your System)

### 2.1 They Treat VOC Collection as a Separate, Dedicated Phase — Not a Byproduct

Elite DR shops (think Agora Financial's research division, or the teams behind 8-figure supplement funnels) separate angle research from angle-specific VOC mining. The workflow is:

```
Phase 1: Angle Discovery (broad scan)
   → Output: Ranked angle candidates (your Purple Ocean Scorecard)

Phase 2: Angle Selection (human decision gate)
   → Output: 3-5 angles greenlit for development

Phase 3: Deep VOC Mining PER ANGLE (dedicated pass)
   → Output: Angle-specific VOC corpus (50-100+ items per angle)

Phase 4: Copy Asset Generation (from angle-specific VOC)
   → Output: Headlines, hooks, body frameworks, proof blocks, review themes
```

**Your proposed VOCC Enhancement workstream maps to Phase 3.** This is the correct architectural decision. The key insight you've landed on — that this should be a *separate workstream* triggered after angle selection, not embedded in the initial research prompt — is how the best operators work.

### 2.2 They Mine Different Sources for Different Jobs

The top 0.1% don't treat all VOC the same. They categorize by *what the VOC is useful for*:

| VOC Type | What It's Good For | Best Sources | Your Current Coverage |
|---|---|---|---|
| **Pain language** | Agitation copy, problem-aware hooks, "you know that feeling when..." | Reddit threads, health forums, Quora, support groups | Covered in Deep Research |
| **Desire language** | Aspiration copy, solution-aware hooks, transformation stories | Success story threads, before/after posts, "what worked for me" posts | Partially covered |
| **Objection language** | FAQ copy, risk reversal, "but what about..." | Amazon Q&A sections, Reddit skeptic comments, forum debates | Partially covered |
| **Comparison language** | Differentiation copy, "I tried X but..." | Reddit "vs" threads, review comparison posts, switching stories | Weak |
| **Trigger language** | Hook copy, "the moment I decided..." | YouTube comments on related content, TikTok reaction comments, Instagram Reel responses | **Not covered (this is your gap)** |
| **Social proof language** | Testimonial-style copy, credibility blocks | Product reviews, course reviews, forum endorsements | Covered but not angle-segmented |
| **Mechanism curiosity language** | Mechanism copy, "how does X actually work" | Forum questions, ELI5-style threads, science discussion posts | Weak |

**The critical gap:** Your current system collects VOC broadly but doesn't tag it by *which job the VOC serves in copy*. The enhancement workstream should not just collect MORE VOC per angle — it should collect VOC *categorized by copy function*.

### 2.3 They Use "Comment Harvesting" as a Proxy for Ad Testing

This is the practice your scraping pipeline is designed to enable, and it's one of the highest-leverage tactics in DR:

- Find viral content (TikTok, YouTube, Reels) in your product's adjacent space
- Harvest the comments — not the content itself, but the *reactions*
- Comments on viral content reveal: what people felt, what surprised them, what they disagreed with, what they wanted more of, and what they said that resonated with THEM

A TikTok video about "herbs that interact with medications" with 2,000 comments is a goldmine — not for the video's content, but for the *language people use in the comments* when they're emotionally activated.

**This is exactly what your MVP scraping pipeline should target first.** The comments on existing viral content in your category are essentially pre-tested emotional triggers.

### 2.4 They Build "VOCC Dossiers" Per Angle, Not a Single Corpus

The top operators don't maintain one big VOC spreadsheet. They build **per-angle dossiers** — structured documents that a copywriter (or agent) can consume to write a specific angle's assets.

A proper angle-specific VOCC dossier contains:

```
ANGLE DOSSIER: [Angle Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ANGLE DEFINITION
   - Who (avatar segment)
   - Core pain/desire
   - Trigger ("why now")
   - Belief shift required
   - Mechanism story

2. RAW VOC CORPUS (50-100+ items)
   - Tagged by function: [PAIN] [DESIRE] [OBJECTION] [TRIGGER] [COMPARISON] [PROOF]
   - Each with: source, date, context, verbatim quote, URL

3. LANGUAGE PATTERNS (extracted from corpus)
   - Top 10 "money phrases" (exact customer language most usable in copy)
   - Emotional temperature map (what words/phrases carry the most charge)
   - Objection clusters (the 3-5 most common pushbacks, in their words)
   - Aspiration clusters (the 3-5 most common desired outcomes, in their words)

4. HOOK RAW MATERIAL
   - Top 5 comment-derived hook concepts (from viral content comments)
   - Top 5 "I was shocked when..." / "Nobody talks about..." patterns
   - Top 5 question-format hooks (from real questions people asked)

5. PROOF ARCHITECTURE
   - Available testimonial-style quotes (positive experiences from forums/reviews)
   - Available "before/after" narrative fragments
   - Available authority/credibility signals (studies mentioned, experts cited by customers)
   - Contradictions / limitations (what would undermine this angle)

6. COMPETITIVE BLIND SPOTS
   - What competitors say about this angle's territory (if anything)
   - What competitors DON'T say that the VOC reveals they should
   - Messaging whitespace opportunities
```

**This is the output format your VOCC Enhancement workstream should produce.** Each angle gets a dossier. The dossier is what your downstream copywriting agents consume.

---

## 3. Gap Analysis: What Your Proposed Approach Gets Right and What's Missing

### What You Get Right

1. **Separate workstream** — Correct. Angle-specific VOCC should not be crammed into the initial Purple Ocean scan.
2. **Social platform scraping as primary source** — Correct. TikTok/Instagram/YouTube comments are the richest untapped VOC source for consumer products.
3. **Keyword-based discovery** — Correct starting point. Find relevant content by keyword, then harvest the comments.
4. **Same scraping infrastructure can surface high-performing videos** — Correct. The scraping layer is dual-use: VOCC mining + creative intelligence (what hooks/formats are working).
5. **Ship without Amazon; add proxies later** — Correct prioritization. Social comment VOC is higher quality for angle-specific copy anyway. Amazon reviews are better for broad pain/desire discovery (which you already did).
6. **Build for all angles, run 3 by default** — Correct. The system should be angle-count agnostic; the bottleneck should be cost/time, not architecture.

### What's Missing or Underspecified

#### Gap 1: No VOC Taxonomy (Copy-Function Tagging)

**The problem:** Your current plan scrapes comments and structures them into "VOCC artifacts." But without a taxonomy that tags VOC by *what it's useful for in copy*, you get a pile of quotes with no operational value beyond "here are things people said."

**What to add:** Every VOC item should be tagged with at least one copy-function label:
- `[PAIN]` — describes a problem, frustration, or negative state
- `[DESIRE]` — describes a wanted outcome, aspiration, or positive state
- `[TRIGGER]` — describes a moment, event, or realization that prompted action
- `[OBJECTION]` — describes skepticism, pushback, or reason for not acting
- `[COMPARISON]` — describes experience with alternatives, competitors, or substitutes
- `[PROOF]` — describes a positive experience, result, or endorsement
- `[MECHANISM]` — describes curiosity about or understanding of how something works
- `[IDENTITY]` — describes who the person is, their self-concept, or group membership

**Why this matters:** When your copywriting agent needs to write an agitation section, it pulls `[PAIN]` and `[TRIGGER]` tagged VOC. When it needs a hook, it pulls `[TRIGGER]` and `[MECHANISM]`. When it needs proof, it pulls `[PROOF]`. Without tagging, the agent has to re-read the entire corpus every time and make its own judgment about relevance — which degrades quality and wastes context window.

#### Gap 2: No "Emotional Charge" Scoring

**The problem:** Not all VOC is created equal. A comment that says "yeah herbs are pretty helpful" is technically VOC but carries zero emotional charge. A comment that says "I literally cried when the valerian finally let me sleep through the night after 3 years of insomnia" is VOC that could be directly paraphrased into a testimonial-style body copy block.

**What to add:** Each VOC item gets an emotional charge score (1-5):
- **1** — Factual/neutral statement with no emotional language
- **2** — Mild sentiment (positive or negative) but generic
- **3** — Clear emotion with some specificity
- **4** — Strong emotion with specific detail (named experience, timeframe, contrast)
- **5** — Visceral, highly specific, would stop a reader cold if used in copy

**Why this matters:** Your downstream agents should weight high-charge VOC items when generating hooks, agitation, and proof. Low-charge items are useful for pattern validation but shouldn't drive copy.

#### Gap 3: No Content Discovery Layer (Finding the Right Videos/Posts to Scrape)

**The problem:** You've spec'd the scraping mechanism (keyword-based discovery -> scrape comments) but haven't specified *how* you find the right content to scrape. Not all content in your category produces usable VOC. A herbalism tutorial video with 50 comments saying "great video!" is worthless. A controversial video about herb-drug interactions with 2,000 heated comments is gold.

**What to add:** A content discovery heuristic that prioritizes:

1. **High comment-to-view ratio** — signals emotional engagement, not passive consumption
2. **Controversy or debate in comments** — signals that people have strong, diverse opinions (rich VOC)
3. **"Story" comments** — content that prompts people to share personal experiences (not just reactions)
4. **Recency** — VOC from the last 6-12 months reflects current language, current concerns, current zeitgeist
5. **Angle-relevance filter** — the content should be adjacent to or directly about the specific angle you're mining for

**Content types that produce the best VOC (in order):**
1. "What [herb/remedy] changed your life?" type engagement posts
2. Controversial takes ("Don't take X if you're on Y")
3. Before/after or personal journey content
4. "I was wrong about..." or myth-busting content
5. Product comparison or "honest review" content

#### Gap 4: No Deduplication or Quality Filter

**The problem:** When you scrape thousands of comments across multiple platforms, you'll get massive amounts of noise: spam, bot comments, one-word reactions, emoji-only responses, off-topic tangents, and promotional content. If you feed this to your copywriting agents unfiltered, you're diluting signal with noise.

**What to add:** A multi-stage quality pipeline:

```
Stage 1: NOISE REMOVAL
  - Remove: <5 words, emoji-only, spam/promotional, bot patterns
  - Remove: off-topic (no relevance to health/herbs/remedies/wellness)
  - Remove: exact and near-duplicates

Stage 2: RELEVANCE SCORING
  - Score each surviving comment for relevance to the specific angle (0-1)
  - Threshold: keep only >0.5 relevance

Stage 3: ENRICHMENT
  - Add copy-function tags ([PAIN], [DESIRE], etc.)
  - Add emotional charge score (1-5)
  - Add language quality flag (usable-in-copy vs. raw-material-only)

Stage 4: DEDUPLICATION AT CONCEPT LEVEL
  - Cluster comments that express the same idea in different words
  - Keep the most emotionally charged / best-phrased version as the "representative"
  - Note cluster size (3 people said this independently = stronger signal)
```

#### Gap 5: No "Language Pattern Extraction" Step

**The problem:** Even with clean, tagged, scored VOC, there's a gap between "here are 80 relevant comments" and "here are the phrases your copywriting agent should actually use." The extraction step — pulling out reusable language patterns — is what separates a research document from a creative brief.

**What to add:** After building the per-angle corpus, run an extraction pass that produces:

1. **Money phrases** — exact 3-8 word fragments that are emotionally loaded and directly usable in copy. These are the phrases a copywriter would highlight with a marker. Examples from your existing VOC:
   - "I've literally got my life back"
   - "I feel like a naughty girl"
   - "every website says something different"
   - "I don't want to be woo-woo"

2. **Problem-state descriptors** — how people describe their negative state in sensory/specific terms. These feed agitation copy. Examples:
   - "lying there replaying the day at 2am"
   - "30 open tabs and still confused"
   - "my doctor just told me to take Advil"

3. **Desire-state descriptors** — how people describe their wanted outcome. These feed aspiration copy and CTA framing. Examples:
   - "know exactly what to reach for at 2am"
   - "be the calm one when someone gets hurt"
   - "stop Googling every symptom"

4. **Objection patterns** — recurring pushback phrased as the customer would phrase it. These feed FAQ and risk-reversal copy. Examples:
   - "I can just Google this"
   - "what if it interacts with my meds"
   - "another AI-generated herb book"

5. **Identity markers** — how people self-identify. These feed hook targeting and audience-segment copy. Examples:
   - "crunchy but not crazy"
   - "I'm not anti-medicine, I'm anti-guessing"
   - "homestead mom"

#### Gap 6: No Feedback Loop from Ad Performance Back to VOCC

**The problem:** Your system as designed is one-directional: VOCC feeds copy. But the best operators close the loop: ad performance data feeds back into VOCC prioritization.

**What to add (not MVP, but design for it):**

When you run ads on 3 angles and Angle B outperforms:
1. Go back to Angle B's VOCC corpus
2. Identify which VOC items were most represented in the winning creative
3. Mine MORE VOC in that specific emotional territory
4. Generate new creative variants from the deeper corpus
5. Repeat

This is how you go from "testing 3 angles" to "scaling the winner" — and it's why the architecture of your VOCC dossiers matters. If the dossiers are well-structured with copy-function tags and emotional charge scores, you can trace winning copy back to the specific VOC items that inspired it.

**Design implication:** Your VOCC dossier schema should include a `used_in` field that downstream agents can populate when they use a VOC item in copy. This creates the traceability needed for the feedback loop.

#### Gap 7: No Handling of Platform-Specific Language Norms

**The problem:** TikTok comments, YouTube comments, and Instagram comments have different linguistic norms. TikTok comments tend to be shorter, more hyperbolic, more meme-inflected. YouTube comments tend to be longer, more narrative, more considered. Instagram comments tend to be more aspirational and identity-driven. If you scrape all three and treat them as interchangeable, you'll miss platform-specific language patterns that matter for platform-specific ad copy.

**What to add:** Platform tagging on each VOC item, plus a note in the dossier about platform-specific language patterns observed. When generating copy for TikTok ads, the agent should weight TikTok-sourced VOC higher (the language will be more native to the platform).

---

## 4. Recommended Architecture for the VOCC Enhancement Workstream

### The Pipeline (Revised)

```
┌──────────────────────────────────────────────────────────────┐
│ STEP 0: ANGLE SELECTION (Input)                              │
│ Purple Ocean Scorecard → Select 3 angles for development     │
│ Human decision gate: confirm/modify angle selection           │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: CONTENT DISCOVERY (Per Angle)                        │
│ For each selected angle:                                     │
│  • Generate angle-specific keyword sets                      │
│  • Search TikTok, YouTube, Instagram for relevant content    │
│  • Filter by: comment count, engagement ratio, recency       │
│  • Prioritize: controversy, personal stories, debates        │
│  • Output: 20-50 high-value content pieces per angle         │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: COMMENT SCRAPING (Bulk Collection)                   │
│ For each selected content piece:                             │
│  • Scrape all comments (including replies/threads)           │
│  • Capture: text, author, date, likes, platform, parent URL  │
│  • Output: Raw comment corpus (thousands per angle)          │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: QUALITY PIPELINE (Noise → Signal)                    │
│  • Stage 1: Noise removal (spam, bots, <5 words, off-topic) │
│  • Stage 2: Relevance scoring (0-1 per angle)                │
│  • Stage 3: Enrichment (copy-function tags, emotion score,   │
│             platform tag, language quality flag)              │
│  • Stage 4: Concept-level dedup (cluster similar ideas)      │
│  • Output: Clean, tagged corpus (50-150 items per angle)     │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 4: LANGUAGE PATTERN EXTRACTION                          │
│  • Money phrases (3-8 word emotionally-loaded fragments)     │
│  • Problem-state descriptors (sensory/specific negatives)    │
│  • Desire-state descriptors (sensory/specific positives)     │
│  • Objection patterns (recurring pushback, in their words)   │
│  • Identity markers (how they self-describe)                 │
│  • Output: Structured language bank per angle                │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 5: ANGLE DOSSIER ASSEMBLY                               │
│ For each angle, compile:                                     │
│  • Angle definition (from Purple Ocean)                      │
│  • Tagged VOC corpus (from Step 3)                           │
│  • Language patterns (from Step 4)                           │
│  • Hook raw material (from viral content comments)           │
│  • Proof architecture (available social proof quotes)        │
│  • Competitive blind spots                                   │
│  • Contradictions + limitations                              │
│  • Output: Production-ready VOCC Dossier per angle           │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ DOWNSTREAM: Copywriting Agents Consume Dossiers              │
│  • Headlines agent pulls: [TRIGGER] + [PAIN] + money phrases │
│  • Body copy agent pulls: [PAIN] + [DESIRE] + [MECHANISM]   │
│  • Proof agent pulls: [PROOF] + emotional charge 4-5 items   │
│  • Review/social proof agent pulls: [PROOF] + [IDENTITY]    │
│  • Lander agent pulls: full dossier as structured context    │
└──────────────────────────────────────────────────────────────┘
```

### MVP vs. Full Build

**MVP (ship first):**
- Steps 0-2 + simplified Step 3 (noise removal only, manual tagging)
- Skip Step 4 (let the copywriting agent extract patterns itself for now)
- Step 5 = simple structured output (angle + raw VOC + basic categorization)
- Sources: TikTok comments, YouTube comments, Instagram Reel comments
- Tool: Keyword search -> scrape top 10-20 pieces of content per angle -> basic cleanup

**Full Build (iterate toward):**
- Automated Step 3 with LLM-powered tagging and scoring
- Dedicated Step 4 extraction pass
- Full dossier format in Step 5
- Add sources: Reddit (not just for discovery but for deep thread mining), health forums, Quora
- Add: Amazon Q&A (not reviews — the questions, which are objection gold)
- Add: Facebook group posts (if accessible)
- Add: Performance feedback loop from ad data

---

## 5. Scraping/Tooling Considerations

### What to Prioritize

1. **TikTok comments** — Highest priority. Richest VOC for cold-traffic ad copy. Most emotionally raw. But: hardest to scrape reliably (anti-bot measures, API changes). Consider third-party data providers (Apify TikTok actors, or commercial API wrappers) before building custom scrapers.

2. **YouTube comments** — Second priority. Longer, more narrative comments. Better for body copy and mechanism curiosity VOC. Easier to scrape (YouTube Data API v3 is official and stable, with quotas).

3. **Instagram Reel comments** — Third priority. More aspirational/identity language. Harder to scrape than YouTube (no official comment API for public posts at scale). Consider Apify or similar.

### ToS/Compliance Decision (Flag This Now)

You correctly flagged this as worth deciding early. The options:

| Approach | Pros | Cons | Recommendation |
|---|---|---|---|
| **Direct scraping** | Free, flexible, immediate | ToS violations, IP bans, maintenance burden, legal grey area | Fine for MVP/personal use; don't build core infrastructure on it |
| **Official APIs** | Stable, legal, documented | Limited (YouTube good; TikTok/IG limited for comments) | Use where available (YouTube) |
| **Third-party data providers** (Apify, Brightdata, etc.) | Reliable, maintained, scalable | Cost ($50-500/mo depending on volume), dependency | Best for TikTok/IG; they handle the anti-bot and maintenance |
| **Residential proxies + custom scrapers** | Flexible, can access anything | Expensive ($200+/mo for quality), complex, fragile, potential legal exposure | Only if data providers fail for your specific needs |

**Recommended stance:** Use YouTube Data API for YouTube. Use a third-party scraping provider (Apify has maintained TikTok and Instagram actors) for TikTok and Instagram. Don't build custom scrapers for social platforms unless the data providers genuinely can't deliver what you need. The maintenance burden of custom social scrapers is a hidden time tax that kills momentum.

### Amazon Access (Deprioritized, But Worth Noting)

Your instinct to deprioritize Amazon is correct for angle-specific VOCC. Amazon reviews are better for Phase 1 (broad pain/desire discovery) which you've already done. For angle-specific deep mining, social platform comments are superior because:
- They're more emotionally raw (Amazon reviews are semi-formal)
- They're more context-rich (comments are in conversation with content)
- They reveal trigger moments (what content activated the person to comment)
- They reflect current language norms (Amazon reviews age poorly)

When you do add Amazon, target the **Q&A sections** (objection gold) rather than reviews.

---

## 6. What Would Change This Analysis

- **If your ad spend is high (>$5K/day):** The feedback loop (Gap 6) becomes critical much earlier. At scale, the angle that's working needs to be deepened aggressively, and performance data should directly inform the next VOCC mining pass.
- **If you expand beyond herbs/wellness:** The source priority would shift. B2B products need LinkedIn and industry forum VOC. Physical products need Amazon reviews more. Digital products need Reddit and Twitter/X.
- **If you find that LLM-powered tagging introduces too much error:** Fall back to human tagging for the first 2-3 angles to establish ground truth, then use those as few-shot examples for automated tagging.
- **If TikTok scraping proves unreliable:** Double down on YouTube (stable API) and Reddit (easy to scrape, rich threads). TikTok comments are the best single source, but YouTube + Reddit together can approximate the same coverage.

---

## 7. Summary: Build Order for the VOCC Enhancement Workstream

| Priority | What to Build | Why | Effort |
|---|---|---|---|
| **1** | Angle Dossier schema (the output format) | Everything downstream depends on the structure of the dossier | Low (design work) |
| **2** | YouTube comment scraping via official API | Stable, legal, rich narrative VOC | Medium |
| **3** | TikTok + IG comment scraping via Apify or equivalent | Highest-value source for cold-traffic copy language | Medium |
| **4** | Quality pipeline (noise removal + relevance scoring) | Without this, raw scraped data is unusable | Medium |
| **5** | Copy-function tagging (LLM-powered) | This is what makes the dossier operationally useful for agents | Medium |
| **6** | Emotional charge scoring | Prioritizes the VOC that actually moves creative quality | Low |
| **7** | Language pattern extraction pass | Bridges the gap between research and creative brief | Medium |
| **8** | Content discovery heuristic | Currently manual (pick videos to scrape); automate later | Low-Medium |
| **9** | Performance feedback loop | Only matters once you're running ads and have data | Defer |
| **10** | Amazon Q&A scraping (via proxy) | Objection gold, but not MVP-blocking | Defer |

---

## 8. The Non-Obvious Insight Most People Miss

The reason the top 0.1% outperform on creative isn't that they have better copywriters or better products. It's that they have **a research-to-copy pipeline that preserves emotional fidelity.**

Here's what that means: when a real person types "I literally cried when I finally slept through the night" — that phrase carries emotional truth. By the time it passes through a generic research process and reaches a copywriter, it usually gets diluted into "improved sleep quality." The job of the VOCC Enhancement workstream isn't just to collect more data. It's to build a pipeline that keeps the emotional rawness intact from source to final copy.

Every processing step you add (scraping, cleaning, tagging, extracting, dossier assembly) should be evaluated against this question: **does this step preserve or destroy the emotional fidelity of the original customer language?**

If a processing step turns "I was terrified I'd accidentally poison my kid with the wrong herb" into "safety concerns regarding pediatric dosing" — that step has failed, no matter how clean and organized the output looks.

Build for emotional fidelity. Everything else is optimization.
