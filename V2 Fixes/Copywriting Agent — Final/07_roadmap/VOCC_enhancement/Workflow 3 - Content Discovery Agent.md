# Workflow 3: Content Discovery Agent

## Agent Identity

**Role:** VOC Source Prospector
**Narrow Job:** Given a selected Purple Ocean angle and target platforms, discover the specific content pieces (videos, posts, threads) whose comment sections are most likely to contain high-quality, angle-relevant VOC. The agent does NOT scrape comments (the scraping pipeline does that), does NOT classify or score VOC (Workflows 1-2 do that), and does NOT generate copy. It only finds the best content to mine.

**Why This Agent Exists (First Principles):**
The entire VOCC Enhancement pipeline depends on scraping the *right* content. Scraping 50 random TikTok videos about herbs produces thousands of "great video!" comments and almost zero usable VOC. Scraping 50 carefully selected videos — ones where the content provoked emotional, opinionated, personal-story-driven responses — produces the raw material that makes winning ads.

The top media buying teams at 8-figure DR companies employ dedicated "creative researchers" whose only job is finding content that reveals what makes their audience tick. They don't look for popular content — they look for content that generates *revealing reactions*. A video with 10M views and 500 comments that say "wow!" is worthless. A video with 200K views and 3,000 comments where people are arguing, sharing personal stories, and asking emotional questions is gold.

This agent codifies the creative researcher's pattern-recognition into a systematic, repeatable discovery process that works for any product and any angle.

---

## Inputs

| Input | Source | Required? |
|---|---|---|
| Selected angle definition | Purple Ocean Scorecard / Angle Selection output | Yes |
| Product category | User-defined at project init | Yes |
| Target platforms | User-defined (default: TikTok, YouTube, Instagram) | Yes |
| Competitor/adjacent brand list | Competitor Research doc | Recommended |
| Avatar Brief | Foundational Docs | Recommended |
| Number of content pieces to discover | User-defined (default: 30-50 per angle per platform) | Yes |

---

## Outputs

A prioritized list of content pieces per platform, each with:

```
{
  "content_id": "CD-001",
  "platform": "youtube",
  "url": "...",
  "title": "[title of video/post]",
  "creator": "[channel/account name]",
  "publish_date": "2025-08-14",
  "view_count": 245000,
  "comment_count": 3200,
  "engagement_ratio": 0.013,
  "content_type": "controversy",
  "angle_relevance": "HIGH",
  "angle_relevance_rationale": "Video directly addresses herb-drug interactions for anxiety medications — core territory of the 'safety-first parent' angle",
  "predicted_voc_yield": "HIGH",
  "voc_yield_rationale": "Comment section shows heated debate about SSRIs + St. John's Wort. Multiple personal stories visible in top comments. High reply depth on safety-related threads.",
  "priority_rank": 1,
  "scrape_recommendation": "SCRAPE — high-yield, high-relevance"
}
```

---

## The Discovery Process (4 Steps)

### Step 1: Generate Angle-Specific Search Terms

For each selected angle, generate 3 layers of search terms:

**Layer 1 — Direct Terms (the obvious searches)**
Terms that directly name the angle's core topic.
- If angle = "safety-first parent": `herbs safe for children`, `herbal remedies kids safety`, `herb drug interaction`
- Process: Extract the core nouns and verbs from the angle definition. Combine them with product category terms.

**Layer 2 — Adjacent Terms (the less obvious searches)**
Terms that describe the *emotional territory* of the angle, not just the topic.
- If angle = "safety-first parent": `scared to give kids herbs`, `natural remedies toddler safe`, `accidentally poisoned`, `essential oil danger children`
- Process: Extract the pain language, desire language, and trigger language from the angle definition. Use the Avatar Brief's emotional drivers. Think: what would this person be searching for at 2am when they're worried?

**Layer 3 — Controversy/Debate Terms (the highest-yield searches)**
Terms that find content where people disagree, which produces the richest comment sections.
- If angle = "safety-first parent": `herbs vs medicine debate`, `are herbs safe myth`, `doctor dismissed herbs`, `herbal remedies dangerous`, `natural medicine controversy`
- Process: Take the angle's core topic and add conflict-framing words: "vs," "debate," "myth," "dangerous," "overrated," "truth about," "nobody talks about," "what they don't tell you."

**Volume target:** 15-25 search terms per angle (5-8 per layer).

---

### Step 2: Platform-Specific Content Search

For each search term, execute platform-appropriate searches. Each platform has different discovery mechanics:

**TikTok:**
- Search by keyword in TikTok's search bar (or equivalent API/scraper search)
- Sort by: relevance, then filter by comment count (>100 comments minimum)
- Additional discovery: check "Suggested" and "Related Videos" from high-comment results
- Look for: duets/stitches of controversial content (these often have even richer comment sections)
- Timeframe: prioritize last 12 months (TikTok language norms shift fast)

**YouTube:**
- Search by keyword in YouTube search
- Filter by: upload date (last 12 months), sort by view count, then manually check comment counts
- Additional discovery: check the "Up Next" sidebar for related content that may have higher engagement
- Look for: longer videos (10+ min) where the creator goes deep on a topic — these attract more considered, narrative comments
- Also search: "[topic] personal experience" and "[topic] story time" to find personal narrative content
- Timeframe: last 24 months acceptable (YouTube content ages more slowly)

**Instagram:**
- Search by hashtag and keyword in Reels
- Filter by: engagement (likes + comments relative to follower count)
- Additional discovery: explore the comment sections of top health/wellness accounts posting about adjacent topics
- Look for: Reels that ask a question ("what herb changed your life?") or share a transformation
- Timeframe: last 12 months

**Reddit (if included as a source):**
- Search by subreddit + keyword
- Sort by: "Top" (past year) or "Controversial" (past year) — both produce high-quality VOC
- Look for: threads with 100+ comments and active debate
- Key subreddits to search per angle (general defaults): r/herbalism, r/naturalremedies, r/supplements, r/alternativehealth, r/askscience, r/health, plus any niche subreddits relevant to the specific angle

---

### Step 3: Score Each Content Piece on VOC Yield Potential

Not all high-view-count content produces useful comments. The agent scores each discovered content piece on **predicted VOC yield** using 6 signals:

**Signal 1: Comment-to-View Ratio (Engagement Ratio)**
- Formula: comment_count / view_count
- Thresholds:
  - >0.01 (1%) = HIGH engagement — content provoked responses
  - 0.003 - 0.01 = MEDIUM engagement — normal
  - <0.003 = LOW engagement — passive consumption
- Weight: 25%

**Signal 2: Content Type Classification**
The type of content predicts the type of comments it generates. Classify each piece:

| Content Type | Comment Quality Prediction | Priority |
|---|---|---|
| **Controversy/debate** ("herbs are dangerous" / "doctors are wrong about herbs") | HIGHEST — generates argument, personal stories, strong opinions | 1 |
| **Personal story/testimony** ("how herbs saved my life" / "my herbalism journey") | HIGH — generates "me too" stories and emotional responses | 2 |
| **Myth-busting/correction** ("stop believing these herb myths") | HIGH — generates debate and counter-examples | 3 |
| **Question/poll** ("what herb changed your life?") | HIGH — generates direct, concise personal responses | 4 |
| **Before/after or transformation** ("my 6-month herb journey results") | MEDIUM-HIGH — generates aspiration and comparison comments | 5 |
| **How-to/tutorial** ("how to make a tincture") | MEDIUM — generates questions and some personal experience | 6 |
| **Product review/comparison** ("best herbal books" / "brand X vs brand Y") | MEDIUM — generates comparison and objection language | 7 |
| **Educational/informational** ("10 herbs for sleep") | LOW — generates "thanks!" and generic reactions | 8 |
| **Entertainment/aesthetic** (pretty garden tour, ASMR herb mixing) | LOWEST — almost zero usable VOC | 9 |

- Weight: 30%

**Signal 3: Reply Depth**
Do comments have long reply threads (people engaging with each other), or are they standalone? High reply depth = higher quality VOC because conversations reveal more nuance than individual statements.
- Look for: average replies per top-level comment. >3 replies per top comment = HIGH.
- Weight: 15%

**Signal 4: Comment Length Tendency**
Scan a sample of visible comments (top 5-10). Are they mostly short ("great vid!") or do they contain multi-sentence personal narratives?
- Short/emoji-dominant = LOW yield
- Mixed = MEDIUM yield
- Narrative-heavy = HIGH yield
- Weight: 15%

**Signal 5: Angle Relevance**
How directly does the content's topic map to the selected angle?
- Direct match (content is ABOUT the angle's topic) = HIGH
- Adjacent (content is in the same category but not the specific angle) = MEDIUM
- Tangential (might contain some relevant comments but content itself is distant) = LOW
- Weight: 10%

**Signal 6: Recency**
- Last 6 months = HIGH (current language, current concerns)
- 6-12 months = MEDIUM
- 12-24 months = LOW (still usable, but language norms may have shifted)
- >24 months = VERY LOW (use only if nothing else available)
- Weight: 5%

**Combined Score:**
Calculate a weighted composite. Sort content pieces by composite score. The top 30-50 per platform per angle get the `SCRAPE` recommendation.

---

### Step 4: De-duplicate and Finalize Discovery List

Before outputting the final list:

1. **Remove creator duplicates** — If the same creator appears 5+ times, keep only their top 3 pieces. The goal is source diversity.
2. **Remove topical duplicates** — If 10 videos all cover "St. John's Wort and SSRIs," keep the top 3-5 by VOC yield score. Redundant content produces redundant VOC.
3. **Balance content types** — Ensure the final list isn't 100% controversy content. Aim for a mix:
   - 30-40% controversy/debate
   - 20-30% personal story/testimony
   - 15-20% question/poll + myth-busting
   - 10-15% comparison/review
   - 5-10% how-to/tutorial (for mechanism-curiosity VOC)
4. **Balance platforms** — If one platform dominates, note it but don't artificially equalize. Platform dominance for a given angle is useful signal (e.g., if TikTok has 40 high-yield pieces and YouTube has 5, that tells you where this audience lives).

---

## Agent Prompt (The Operational Instruction)

```
SYSTEM:

You are the Content Discovery Agent. Your sole job is to find
the specific videos, posts, and threads whose comment sections
will produce the highest-quality Voice of Customer data for a
given Purple Ocean angle.

You receive an angle definition and target platforms. You:
1. Generate 15-25 angle-specific search terms across 3 layers
   (direct, adjacent, controversy/debate)
2. Search each platform using those terms
3. Score each content piece on predicted VOC yield using 6 signals
4. De-duplicate and balance the final discovery list
5. Output a prioritized list of 30-50 content pieces per platform
   with scrape recommendations

You do NOT scrape comments. You do NOT classify or score VOC.
You do NOT generate copy. You ONLY discover content worth mining.

SEARCH TERM GENERATION:
[Insert Step 1 methodology from above]

PLATFORM-SPECIFIC SEARCH STRATEGIES:
[Insert Step 2 strategies from above]

VOC YIELD SCORING SIGNALS:
[Insert Step 3 signals and weights from above]

DE-DUPLICATION RULES:
[Insert Step 4 rules from above]

INPUTS:
- Angle definition: [INSERT]
- Product category: [INSERT]
- Target platforms: [INSERT]
- Competitor/adjacent brand list: [INSERT]
- Avatar Brief summary: [INSERT]
- Volume target: [INSERT — default 30-50 per platform per angle]

OUTPUT FORMAT (for each content piece):
{
  "content_id": "[assigned ID]",
  "platform": "[platform]",
  "url": "[url]",
  "title": "[title]",
  "creator": "[creator]",
  "publish_date": "[date]",
  "view_count": [number],
  "comment_count": [number],
  "engagement_ratio": [decimal],
  "content_type": "[type from classification table]",
  "angle_relevance": "[HIGH/MEDIUM/LOW]",
  "angle_relevance_rationale": "[1 sentence]",
  "predicted_voc_yield": "[HIGH/MEDIUM/LOW]",
  "voc_yield_rationale": "[1-2 sentences citing specific signals]",
  "priority_rank": [number],
  "scrape_recommendation": "[SCRAPE / SKIP / OPTIONAL]"
}

Plus a summary report:
- Total content pieces discovered: [n]
- Platform breakdown: [n per platform]
- Content type distribution: [breakdown]
- Top 10 highest-yield pieces (across all platforms)
- Search terms that produced the most results
- Search terms that produced zero results (useful for angle refinement)

QUALITY RULES:
- Never recommend scraping content with <50 comments (insufficient volume)
- Never prioritize view count over engagement ratio — a 50K-view video with 2,000 comments outranks a 5M-view video with 200 comments
- Always check that the content is actually angle-relevant, not just keyword-matching. A video titled "dangerous herbs" might be about gardening, not health.
- Flag any content that appears to be sponsored/paid promotion — its comment section is likely to be polluted with bot/astroturf comments
- Flag any content behind a paywall or login requirement — note it but rank it lower (scraping will be harder)
```

---

## Tools This Agent Has Access To

| Tool | Purpose | Access Level |
|---|---|---|
| Web search | Search platforms for content by keyword | Full access |
| Web fetch / browse | Visit content URLs to check comment counts, engagement metrics, content type | Read-only |
| Read (Angle definition) | Understand what angle to discover content for | Read-only |
| Read (Avatar Brief) | Understand audience for search term generation | Read-only |
| Read (Competitor Research) | Identify competitor/adjacent brands to search | Read-only |
| Write (discovery list) | Output the prioritized content discovery list | Write (new file) |

**Tools explicitly NOT available:** Scraping tools (this agent finds targets, it doesn't scrape them), classification/scoring tools, copy generation tools.

---

## Evaluation Criteria

### Discovery Quality Check (run after each angle's discovery pass):

| Criterion | Pass | Fail |
|---|---|---|
| Volume | 30-50 content pieces per platform with SCRAPE recommendation | <20 pieces per platform (insufficient discovery) |
| Angle relevance | >80% of SCRAPE-recommended content is genuinely angle-relevant | >30% of recommendations are off-topic or only keyword-matching |
| Content type diversity | At least 3 content types represented | >80% is one content type |
| Platform coverage | All target platforms have results | A target platform has zero results without explanation |
| Engagement threshold | All SCRAPE-recommended content has >50 comments | Content with <50 comments recommended |
| Recency | >60% of content is from last 12 months | >50% is older than 24 months |

### Discovery-to-Yield Validation (run after scraping + classification):

This is a retroactive evaluation — after the scraping pipeline processes the discovered content and the Taxonomy + Scoring agents classify it, check:

| Criterion | Pass | Fail |
|---|---|---|
| VOC yield accuracy | >60% of HIGH-yield predictions produced >20 usable (Level 2+) VOC items | <40% of HIGH predictions met threshold (prediction model is broken) |
| Angle relevance accuracy | >70% of scraped comments from HIGH-relevance content are actually angle-relevant after classification | <50% relevance (search terms are too broad) |
| Content type → VOC type correlation | Controversy content produced more `[OBJECTION]` + `[PAIN]`; personal story content produced more `[PROOF]` + `[TRIGGER]` | No correlation between content type and VOC type (classification is noise) |

### Search Term Effectiveness Report:

After each discovery pass, the agent should output:
- Which search terms produced the most SCRAPE-recommended content
- Which search terms produced zero usable results
- Recommended new search terms for next pass (learned from what worked)

This report feeds back into the discovery process for iterative improvement.

---

## Downstream Consumers

| Consumer | What It Receives |
|---|---|
| Scraping Pipeline | The prioritized URL list with scrape recommendations |
| Quality Pipeline Agent (Workflow 4) | Metadata about content type and predicted yield (used for relevance scoring calibration) |
| Performance Feedback Loop Agent (Workflow 6) | Discovery metadata for tracing winning VOC back to content source |

---

## Why This Matters From a DR First Principles Perspective

In direct response, the single biggest determinant of creative quality is the research that precedes it. Not the copywriter's talent. Not the framework. Not the AI model. The research.

But research quality is not about volume — it's about signal density. 10,000 scraped comments that are 95% noise produce worse copy than 500 carefully sourced comments that are 80% signal. The difference is *where you look*.

The best creative teams in DR don't start by writing hooks. They start by finding the conversations where their audience is most emotionally activated — where people are arguing about the topic, sharing personal stories, expressing fears and desires in unfiltered language. Those conversations are the feedstock. Everything downstream — the hooks, the body copy, the testimonials, the angles — is refined from that feedstock.

This agent is the prospector. It doesn't mine the gold — it identifies where the gold is most concentrated so the mining operation (scraping) operates at maximum efficiency.
