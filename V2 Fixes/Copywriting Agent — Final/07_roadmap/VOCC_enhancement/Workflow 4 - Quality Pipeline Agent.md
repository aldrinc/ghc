# Workflow 4: Quality Pipeline Agent (Noise to Signal)

## Agent Identity

**Role:** VOC Quality Gatekeeper
**Narrow Job:** Take raw scraped comments from the scraping pipeline and process them through a 4-stage quality pipeline that removes noise, scores relevance to the target angle, structures the data into a standardized format, and de-duplicates at the concept level. The agent does NOT discover content (Workflow 3 does that), does NOT assign copy-function tags (Workflow 1 does that), and does NOT score emotional charge (Workflow 2 does that). It turns raw data into clean, structured, angle-relevant VOC items ready for downstream processing.

**Why This Agent Exists (First Principles):**
Raw scraped data from social platforms is roughly 80-90% noise by volume. Spam, bots, emoji-only reactions, off-topic tangents, promotional comments, and one-word responses ("wow!", "subscribe!", emoji strings) make up the vast majority of any comment section. Feeding this directly to downstream classification and scoring agents wastes compute, dilutes quality, and introduces garbage data that contaminates the VOCC dossier.

The top DR research operations all have a "cleaning" step between data collection and analysis. In traditional operations, this was a junior researcher manually reading through printed-out comment threads with a marker, crossing out garbage and starring keepers. In an agentic system, this agent automates that junior researcher's job — but with explicit rules instead of vibes.

The critical principle: **it is better to discard a marginally useful comment than to pass noise through.** Downstream agents can't un-contaminate a corpus. Aggressive filtering at this stage protects everything downstream.

---

## Inputs

| Input | Source | Required? |
|---|---|---|
| Raw scraped comments | Scraping pipeline output | Yes |
| Content discovery metadata | Content Discovery Agent (Workflow 3) output — content_type, angle_relevance, platform | Yes |
| Angle definition | Purple Ocean Scorecard / Angle Selection output | Yes |
| Product category | User-defined at project init | Yes |
| Avatar Brief | Foundational Docs | Recommended |

Each raw comment arrives with at minimum:
- `raw_text` (the verbatim comment)
- `source_platform` (TikTok, YouTube, Instagram, Reddit, etc.)
- `source_url` (URL of the parent content)
- `parent_content_id` (from Content Discovery Agent)
- `author_handle` (if available)
- `date` (if available)
- `likes` (if available)
- `reply_count` (if available)
- `is_reply` (boolean — is this a reply to another comment?)
- `parent_comment_id` (if it's a reply)

---

## Outputs

Clean, structured VOC items ready for Workflow 1 (Taxonomy) and Workflow 2 (Scoring):

```
{
  "voc_id": "V001",
  "text": "[cleaned verbatim text]",
  "source_platform": "youtube",
  "source_url": "...",
  "parent_content_id": "CD-001",
  "parent_content_type": "controversy",
  "author_handle": "user123",
  "date": "2025-09-22",
  "likes": 47,
  "reply_count": 12,
  "is_reply": false,
  "angle_relevance_score": 0.85,
  "quality_stage_passed": "STAGE_4_COMPLETE",
  "concept_cluster_id": "CC-012",
  "concept_cluster_size": 4,
  "is_cluster_representative": true
}
```

Plus a batch summary report:
```
{
  "batch_summary": {
    "raw_input_count": 3200,
    "stage_1_survivors": 1800,
    "stage_2_survivors": 420,
    "stage_3_structured": 420,
    "stage_4_deduplicated": 285,
    "final_yield_rate": "8.9%",
    "angle_relevance_distribution": {
      "high": 180,
      "medium": 75,
      "low": 30
    },
    "platform_distribution": {
      "youtube": 120,
      "tiktok": 95,
      "instagram": 70
    },
    "discard_reasons": {
      "too_short": 680,
      "spam_or_promo": 240,
      "off_topic": 520,
      "bot_pattern": 180,
      "duplicate_exact": 95,
      "emoji_only": 285,
      "below_relevance_threshold": 815,
      "concept_duplicate": 135
    }
  }
}
```

---

## The 4-Stage Pipeline

### Stage 1: Noise Removal (Hard Filters)

Purpose: Eliminate obviously unusable comments. These are binary pass/fail rules — no judgment, no scoring. If a comment trips any of these filters, it's discarded immediately.

**Disqualification Criteria (discard if ANY of these are true):**

| Filter | Rule | Rationale |
|---|---|---|
| **Too short** | Text is <5 words after removing emojis, mentions, and hashtags | Too short to contain usable customer language |
| **Emoji-only** | Text is 100% emojis, emoticons, or reaction characters | No linguistic content |
| **Spam/promotional** | Contains: product links, affiliate codes, "check out my...", "follow me at...", "DM me for...", "use code...", discount offers, MLM language | Promotional content, not organic VOC |
| **Bot patterns** | Exact duplicate text appearing 3+ times in the batch (same text, different authors), OR text matches known bot patterns (random character strings, clearly auto-generated) | Bot/astroturf contamination |
| **Non-English** | Text is not in English (or the target language of the campaign) | Cannot be used in English-language copy |
| **Tag/mention-only** | Text is only @mentions of other users with no substantive content | Social tagging, not VOC |
| **Timestamp/meta-only** | Text only references video timestamps ("3:42 was crazy") without substantive opinion | Engagement signal but no usable language |

**What Stage 1 does NOT filter:**
- Short but substantive comments (e.g., "never again" = 2 words but potentially high-charge — let Workflow 2 handle this)
- Comments with some emojis mixed with text (emojis are stripped, text is evaluated)
- Comments with mild profanity (these are often the most emotionally honest)
- Comments in informal/slang language (this is authentic voice — preserve it)
- Negative or critical comments (these are valuable VOC — never filter by sentiment)

**Expected yield:** 50-70% of raw comments survive Stage 1.

---

### Stage 2: Relevance Scoring (Angle Alignment)

Purpose: Score each surviving comment for relevance to the specific angle being researched. Not all comments on angle-relevant content are themselves angle-relevant — a video about herb-drug interactions will also have comments about the creator's outfit, off-topic recommendations, and general health discussions.

**Relevance Scoring Methodology:**

For each comment, score relevance to the target angle on a 0-1 scale:

**1.0 — Direct Hit:** The comment directly addresses the angle's core topic, using language that maps to the angle's pain, desire, trigger, or mechanism.
- Angle = "safety-first parent" → Comment: "I'm terrified to give my toddler any herb without knowing exactly what it does" = 1.0

**0.8 — Strong Relevance:** The comment is clearly in the angle's territory but doesn't directly address the core topic. It addresses an adjacent concern that the angle's audience would strongly relate to.
- Angle = "safety-first parent" → Comment: "I always check with my pharmacist before trying any natural remedy" = 0.8

**0.6 — Moderate Relevance:** The comment touches the angle's category but is not specific to the angle's unique positioning. Would be useful as supporting context but not as primary VOC.
- Angle = "safety-first parent" → Comment: "I love using herbs for my family's health" = 0.6

**0.4 — Weak Relevance:** The comment is in the general product category but has little specific connection to this angle.
- Angle = "safety-first parent" → Comment: "Chamomile tea is great before bed" = 0.4

**0.2 — Tangential:** The comment barely relates to the product category, let alone the angle.
- Angle = "safety-first parent" → Comment: "I prefer modern medicine but respect people's choices" = 0.2

**0.0 — Irrelevant:** The comment has no connection to the angle or product category.
- Any angle → Comment: "Love your hair in this video!" = 0.0

**Threshold:** Discard all comments scoring <0.5. This is aggressive by design — it's better to have 100 highly relevant items than 500 items where half are noise.

**Relevance scoring inputs:**
The agent uses these references to assess relevance:
1. The angle definition (who, pain, desire, trigger, mechanism, belief shift)
2. The angle's core keyword cluster
3. The Avatar Brief's pain points and emotional drivers (if available)

**Expected yield:** 20-40% of Stage 1 survivors pass Stage 2.

---

### Stage 3: Structuring and Enrichment

Purpose: Transform surviving comments from raw text into structured VOC items with standardized fields. This stage does not add copy-function tags or emotional scores (Workflows 1-2 handle those) — it adds structural metadata that those agents need.

**Enrichment operations:**

1. **Text Cleaning (Minimal)**
   - Remove platform-specific formatting artifacts (weird Unicode, broken HTML entities)
   - Remove @mentions and #hashtags from the text body (preserve in separate field if needed)
   - Normalize obvious typos ONLY if they would prevent comprehension (do NOT correct informal spelling, slang, or dialect — these are authentic voice)
   - Preserve emojis that carry semantic meaning (like a sarcastic emoji that inverts the text's literal meaning) — strip purely decorative emojis
   - **CRITICAL RULE:** Never paraphrase, rewrite, or "improve" the text. The entire value of VOC is its authenticity. A grammatically wrong, misspelled, stream-of-consciousness comment is worth more than a polished rewrite.

2. **Assign VOC ID**
   - Format: `V[batch_number]-[sequential]` (e.g., V001-001, V001-002)
   - Must be unique within the entire project (not just within one batch)

3. **Attach Content Metadata**
   - Pull from Content Discovery Agent's output: parent_content_type, platform, angle_relevance prediction
   - These become attached to each VOC item so downstream agents have context about WHERE the VOC came from

4. **Thread Context (for replies)**
   - If the comment is a reply, include the parent comment text as a `thread_context` field
   - This is critical because replies often lose meaning without context: "Same!!! This happened to me too" means nothing alone, but paired with a parent comment about herb-drug interactions, it becomes a second data point for that theme

5. **Engagement Signal**
   - Attach likes count and reply count from the raw data
   - High-engagement comments (many likes, many replies) are likely to be more representative of the audience's views — this is a soft signal, not a filter

**Expected yield:** 100% of Stage 2 survivors proceed (this stage is structural, not reductive).

---

### Stage 4: Concept-Level Deduplication

Purpose: When 20 people say "I'm scared to give my kids herbs because every source says something different," that's 20 comments expressing the same concept. Keeping all 20 wastes downstream agent context window. But collapsing them into 1 loses the signal strength that comes from independent confirmation.

**Solution:** Cluster comments that express the same concept, keep the best representative, and note the cluster size as a signal strength indicator.

**Clustering Methodology:**

1. **Semantic Similarity Grouping:**
   - Group comments that express the same core idea, even in different words
   - "I'm scared to give herbs to my kids" and "Terrified of accidentally poisoning my toddler with the wrong dosage" = same concept cluster
   - "I'm scared to give herbs to my kids" and "I love using herbs for my family" = different clusters

2. **Representative Selection:**
   - For each cluster, select the representative comment based on (in priority order):
     a. **Most specific** — names timeframes, details, specific herbs, specific consequences
     b. **Most emotionally vivid** — strongest language, most sensory detail
     c. **Longest (within reason)** — more context is better, up to a point
     d. **Most engaged** — highest like count or reply count (community-validated)

3. **Cluster Metadata:**
   - `concept_cluster_id`: unique ID for the cluster
   - `concept_cluster_size`: how many comments expressed this concept
   - `is_cluster_representative`: true/false
   - Non-representative items are NOT discarded — they're retained in a "cluster archive" accessible if needed, but they're not passed to downstream agents by default

4. **Cluster Size as Signal:**
   - Cluster size 1 = unique observation (interesting but low confidence)
   - Cluster size 2-3 = emerging pattern (moderate confidence)
   - Cluster size 4-9 = established pattern (high confidence)
   - Cluster size 10+ = dominant theme (very high confidence — this is a core audience concern)

**Expected yield:** 30-50% reduction from Stage 3. Final output is the deduplicated corpus of cluster representatives + metadata.

---

## Agent Prompt (The Operational Instruction)

```
SYSTEM:

You are the Quality Pipeline Agent. Your sole job is to transform
raw scraped comments into clean, structured, angle-relevant VOC
items through a 4-stage quality pipeline.

You receive raw scraped comments in bulk. For each batch, you:
1. STAGE 1: Apply hard noise filters (discard spam, bots, too-
   short, emoji-only, non-English, tag-only, promo)
2. STAGE 2: Score each survivor for angle relevance (0-1 scale).
   Discard <0.5.
3. STAGE 3: Structure surviving comments into standardized VOC
   format with assigned IDs, cleaned text, and attached metadata.
   NEVER paraphrase or rewrite — preserve verbatim text.
4. STAGE 4: Cluster semantically similar comments, select the
   most specific/vivid representative per cluster, and note
   cluster size.

You do NOT classify by copy function (Workflow 1). You do NOT
score emotional charge (Workflow 2). You do NOT extract language
patterns (Workflow 5). You clean, filter, structure, and
deduplicate.

STAGE 1 RULES:
[Insert Stage 1 disqualification criteria from above]

STAGE 2 RULES:
[Insert Stage 2 relevance scoring methodology from above]

STAGE 3 RULES:
[Insert Stage 3 structuring rules from above]

STAGE 4 RULES:
[Insert Stage 4 clustering methodology from above]

INPUTS:
- Angle definition: [INSERT]
- Product category: [INSERT]
- Raw scraped comments: [INSERT BATCH]
- Content discovery metadata: [INSERT]
- Avatar Brief summary: [INSERT — optional]

OUTPUT:
1. Clean VOC items (structured format with all fields)
2. Batch summary report (counts at each stage, discard reasons,
   distributions)

QUALITY RULES:
- NEVER alter the semantic content of a comment. Clean formatting
  artifacts only.
- When in doubt about relevance, DISCARD. Downstream quality
  depends on upstream strictness.
- When clustering, always keep the most SPECIFIC and VIVID
  representative — not the most polished or grammatically correct.
- Track and report discard reasons at every stage. This data is
  used to improve the Content Discovery Agent's targeting.
- Flag any anomalies: if a content piece produced 0 usable VOC
  items (all discarded), note it — the Content Discovery Agent
  overestimated its yield.
```

---

## Tools This Agent Has Access To

| Tool | Purpose | Access Level |
|---|---|---|
| Read (raw comments) | Ingest raw scraped comment batches | Read-only |
| Read (content discovery metadata) | Reference content type and predicted yield for calibration | Read-only |
| Read (angle definition) | Reference angle for relevance scoring | Read-only |
| Read (Avatar Brief) | Reference audience profile for relevance calibration | Read-only |
| Write (clean VOC items) | Output structured VOC items for downstream agents | Write (new files) |
| Write (batch summary) | Output pipeline statistics and anomaly reports | Write (new file) |
| Write (cluster archive) | Store non-representative cluster members for reference | Write (append) |

**Tools explicitly NOT available:** Web search, scraping tools, classification/scoring tools, copy generation tools.

---

## Evaluation Criteria

### Pipeline Efficiency Check (per batch):

| Metric | Healthy Range | Unhealthy |
|---|---|---|
| Overall yield rate (raw → final) | 5-15% | <3% (too aggressive — discarding usable items) or >25% (too permissive — passing noise) |
| Stage 1 pass rate | 50-70% | <30% (source quality issue — Content Discovery Agent needs recalibration) or >85% (filters too loose) |
| Stage 2 pass rate | 20-40% of Stage 1 survivors | <10% (search terms too broad) or >60% (threshold too low) |
| Stage 4 dedup rate | 30-50% reduction | <15% (under-clustering — concepts not being merged) or >70% (over-clustering — distinct ideas merged) |

### Quality Spot Check (sample 20 items from final output):

| Criterion | Pass | Fail |
|---|---|---|
| Text authenticity | Verbatim customer language preserved (typos, slang, informal grammar intact) | Text has been paraphrased, polished, or summarized |
| Relevance accuracy | 18+ of 20 sampled items are genuinely relevant to the target angle | <15 of 20 are genuinely relevant (relevance scoring is broken) |
| Cluster quality | Representatives are the most specific/vivid in their cluster | Representatives are the shortest, most generic, or most grammatically correct (wrong selection criteria) |
| ID uniqueness | No duplicate VOC IDs in the batch | Duplicate IDs found |
| Thread context | Reply comments include parent context | Replies are isolated without the comment they're responding to |

### Discard Audit (sample 20 discarded items):

| Criterion | Pass | Fail |
|---|---|---|
| Noise removal accuracy | 18+ of 20 discards were correctly identified as noise | >3 discards were actually usable VOC (filters too aggressive) |
| Relevance discard accuracy | 18+ of 20 relevance-discards were correctly below threshold | >3 relevance-discards were actually angle-relevant (scoring miscalibrated) |

### Content Source Yield Report (feedback to Workflow 3):

For each content piece in the batch:
- How many raw comments were scraped
- How many survived to final output
- What was the yield rate
- What was the dominant discard reason

Content pieces with <2% yield should be flagged to the Content Discovery Agent as "low-yield source — reassess VOC yield prediction model."

---

## Downstream Consumers

| Consumer | What It Receives |
|---|---|
| VOC Taxonomy Agent (Workflow 1) | Clean, structured VOC items ready for copy-function classification |
| Emotional Charge Scoring Agent (Workflow 2) | Same items (Workflows 1 and 2 can run in parallel on the same output) |
| Content Discovery Agent (Workflow 3) | Yield report per content piece (feedback loop for discovery calibration) |
| Angle Dossier Assembly | Batch summary statistics (corpus size, source distribution, cluster distribution) |

---

## Why This Matters From a DR First Principles Perspective

The garbage-in, garbage-out principle is the most violated principle in marketing research. Teams collect thousands of data points and feel productive, but if 80% of those data points are noise, the downstream analysis — and the copy built on it — is contaminated.

The best DR operations treat data quality as a first-class concern, not an afterthought. Agora's research teams famously had strict data hygiene standards for their customer research files. Stefan Georgi talks about reading through customer research and ruthlessly crossing out anything that isn't "real" — anything that feels like a polished review rather than a raw human reaction.

This agent is the quality gate. It ensures that by the time VOC reaches the classification and scoring agents, every item in the corpus is:
1. Real (not spam, bots, or promotional)
2. Relevant (actually about the angle being researched)
3. Authentic (verbatim customer language, not cleaned up)
4. Non-redundant (best representative of each concept, with cluster size as a strength signal)

Without this gate, you're building a $10M creative system on a foundation of TikTok spam comments. With it, you're building on verified, relevant, de-duplicated customer truth.
