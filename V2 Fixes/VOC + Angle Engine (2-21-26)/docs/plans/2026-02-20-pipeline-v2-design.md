# Research Engine v2 — Pipeline Design Document

**Date:** 2026-02-20
**Status:** Approved
**Version:** 2.0
**Scope:** 6-Component Pipeline for Direct Response Marketing Research
**Supersedes:** Research Engine v1 Design Document (2025-02-19)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Core Principles](#3-core-principles)
4. [Component Specifications](#4-component-specifications)
5. [Scoring Scripts](#5-scoring-scripts)
6. [Observation Sheet Schemas](#6-observation-sheet-schemas)
7. [Handoff Protocols](#7-handoff-protocols)
8. [Apify Integration Spec](#8-apify-integration-spec)
9. [File Structure](#9-file-structure)
10. [What Changed from v1](#10-what-changed-from-v1)
11. [What Did NOT Change from v1](#11-what-did-not-change-from-v1)

---

## 1. Executive Summary

A direct response marketing research engine built on the thesis:

> **"There is no product saturation; only angle saturation."**

The engine discovers underserved advertising angles by systematically scanning where customers congregate, extracting voice-of-customer language, and clustering shadow angles that competitors have not yet claimed. Every market has unexploited angles. This engine finds them.

**v2 adds four capabilities to the proven v1 foundation:**

1. **Scraper-integrated habitat discovery** via Apify, replacing manual browsing with structured data pipelines for Reddit, Trustpilot, Amazon, Google SERP, and general web scraping.
2. **Social video platform mining** across TikTok, Instagram Reels, and YouTube Shorts/Videos — capturing hooks, comments, and virality signals that text-only habitats miss.
3. **Competitor asset analysis** as a formal pre-pipeline step, producing a structured saturation map and whitespace map that all downstream agents consume.
4. **Virality scoring** via a new Python script (`score_virality.py`) that measures engagement density, velocity, and virality ratio to surface high-performing content.

**Current product context:**

- **Product:** The Honest Herbalist Handbook
- **Price:** $49 digital guide
- **Category:** Herbal remedies / natural health
- **Format:** Digital download

---

## 2. Architecture Overview

### 2.1 Pipeline Components (6 total)

| # | Component | Type | Purpose |
|---|-----------|------|---------|
| Pre | Competitor Asset Analyzer | Standalone, pre-pipeline | Analyze competitor ads, landing pages, and funnels to produce saturation map |
| 0 | Agent 0: Habitat Strategist | LLM Agent | Identify text-based habitats and generate scraper configurations |
| 0b | Agent 0b: Social Video Strategist | LLM Agent (parallel with 0) | Identify video platform opportunities and generate video scraper configs |
| Infra | Apify Scraper Layer + score_virality.py | Infrastructure | Execute scrapes, normalize data, score video virality |
| 1 | Agent 1: Habitat Qualifier | LLM Agent | Observe and qualify all pre-scraped habitat data |
| 2-3 | Agent 2: VOC Extractor + Agent 3: Shadow Angle Clusterer | LLM Agents (sequential) | Extract VOC, cluster angles, score Purple Ocean candidates |

### 2.2 Data Flow Diagram

```
                         ┌─────────────────────────────┐
                         │      FOUNDATIONAL DOCS       │
                         │  Avatar Brief, Offer Brief,  │
                         │  Competitor Research,         │
                         │  I Believe Statements,        │
                         │  Design System                │
                         └─────────────┬───────────────┘
                                       │
                    ┌──────────────────┼──────────────────────┐
                    │                  │                      │
                    ▼                  ▼                      ▼
    ┌───────────────────────┐  ┌──────────────┐  ┌───────────────────────┐
    │  COMPETITOR ASSET      │  │              │  │                       │
    │  ANALYZER              │  │  (shared     │  │                       │
    │  (pre-pipeline)        │  │   context)   │  │                       │
    │                        │  │              │  │                       │
    │  IN: user-provided     │  └──────┬───────┘  │                       │
    │      competitor assets  │         │          │                       │
    │  OUT: competitor_       │         │          │                       │
    │       analysis.json     │         │          │                       │
    │       saturation_map    │         │          │                       │
    │       whitespace_map    │         │          │                       │
    └───────────┬─────────────┘         │          │                       │
                │                       │          │                       │
                ▼                       ▼          │                       │
    ┌─────────────────────────────────────────┐    │                       │
    │          competitor_analysis.json        │    │                       │
    │  (available to ALL downstream agents)    │    │                       │
    └───────┬────────────────────┬─────────────┘   │                       │
            │                    │                  │                       │
            ▼                    ▼                  │                       │
┌─────────────────────┐  ┌─────────────────────┐   │                       │
│  AGENT 0             │  │  AGENT 0b            │   │                       │
│  Habitat Strategist  │  │  Social Video        │   │                       │
│  (text-based)        │  │  Strategist           │   │                       │
│                      │  │  (video platforms)    │   │                       │
│  IN: foundational    │  │                      │   │                       │
│      docs +          │  │  IN: foundational    │   │                       │
│      competitor_     │  │      docs +          │   │                       │
│      analysis.json   │  │      competitor_     │   │                       │
│                      │  │      analysis.json + │   │                       │
│  OUT:                │  │      product keywords│   │                       │
│   habitat_strategy   │  │                      │   │                       │
│   .json              │  │  OUT:                │   │                       │
│   apify_configs.json │  │   social_video_      │   │                       │
│   search_queries     │  │   configs.json       │   │                       │
│   .json              │  │   hashtag_clusters   │   │                       │
│                      │  │   .json              │   │                       │
│                      │  │   competitor_accounts │   │                       │
│                      │  │   .json              │   │                       │
└─────────┬───────────┘  └──────────┬───────────┘   │                       │
          │                         │                │                       │
          ▼                         ▼                │                       │
┌──────────────────────────────────────────────────┐ │                       │
│              APIFY SCRAPER LAYER                  │ │                       │
│                                                  │ │                       │
│  Text habitats:                                  │ │                       │
│   Reddit Scraper, Web Scraper, Trustpilot,       │ │                       │
│   Amazon Reviews, Google SERP                    │ │                       │
│                                                  │ │                       │
│  Video platforms:                                │ │                       │
│   TikTok Scraper, Instagram Scraper,             │ │                       │
│   YouTube Scraper                                │ │                       │
│                                                  │ │                       │
│  OUT: raw_scraped_data/text_habitats/            │ │                       │
│       raw_scraped_data/social_video/             │ │                       │
└─────────┬───────────────────────┬────────────────┘ │                       │
          │                       │                  │                       │
          │                       ▼                  │                       │
          │         ┌─────────────────────────┐      │                       │
          │         │  score_virality.py       │      │                       │
          │         │                         │      │                       │
          │         │  IN: raw social video   │      │                       │
          │         │  OUT: scored videos     │      │                       │
          │         │       with tier labels  │      │                       │
          │         └──────────┬──────────────┘      │                       │
          │                    │                      │                       │
          ▼                    ▼                      │                       │
┌──────────────────────────────────────────────────────────────────────────┐
│                    AGENT 1: HABITAT QUALIFIER                            │
│                                                                          │
│  IN: raw_scraped_data/ (text + video, pre-scored for virality)          │
│      competitor_analysis.json                                            │
│      foundational docs                                                   │
│                                                                          │
│  PROCESS: Pure observation on pre-scraped data (NO web search)          │
│           Text habitats: 52-field observation sheet (unchanged from v1)  │
│           Video habitats: 52 + 11 new video-specific fields             │
│                                                                          │
│  OUT: habitat_observations.json                                          │
│       → score_habitats.py → scored habitats                              │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    AGENT 2: VOC EXTRACTOR                                │
│                                                                          │
│  IN: scored habitats + raw data + competitor_analysis.json              │
│                                                                          │
│  PROCESS: Extract VOC from 3 source categories:                         │
│    1. Text VOC (forums, reviews, blogs, Q&A)                            │
│    2. Comment VOC (TikTok/IG/YouTube comments)                          │
│    3. Video Hook VOC (video content hooks, captions)                    │
│                                                                          │
│  OUT: voc_corpus.json → score_voc.py → scored VOC                       │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    AGENT 3: SHADOW ANGLE CLUSTERER                       │
│                                                                          │
│  IN: scored VOC corpus + competitor_analysis.json + foundational docs    │
│                                                                          │
│  PROCESS: Cluster angles, overlay competitor saturation, score Purple    │
│           Ocean candidates                                               │
│                                                                          │
│  OUT: angle_candidates.json → score_angles.py → RANKED ANGLES           │
│       → USER REVIEW                                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Shared Context

The following documents are available to ALL agents as foundational context:

| Document | Purpose |
|----------|---------|
| Avatar Brief | Target customer demographics, psychographics, buyer behavior |
| Offer Brief | Product positioning, features, pricing, delivery mechanism |
| Competitor Research | Competitive landscape analysis |
| `competitor_analysis.json` | Structured output from Competitor Asset Analyzer (NEW in v2) |
| I Believe Statements | Belief architecture for messaging |
| Design System | Visual and copy style guidelines |

### 2.4 Execution Modes

The pipeline supports two execution modes for the Apify layer:

- **Automated (API):** Agent 0/0b outputs are programmatically fed to Apify actors via API calls. Best for repeat runs.
- **Manual (Console):** Agent 0/0b outputs are human-readable configs that the operator pastes into the Apify console. Best for first runs and debugging.

---

## 3. Core Principles

### 3.1 "Agent Observes, Math Decides"

The foundational architecture pattern. Never deviate.

- **LLMs observe:** Fill structured observation sheets with binary (Y/N), categorical, or factual data only. Never assign numerical scores.
- **Python calculates:** All scores computed from predetermined formulas applied to observation sheets.
- **Humans decide:** Scored results presented with underlying observations visible for audit.

```
LLM Agent → Observation Sheet (binary/categorical) → Python Script → Score (deterministic)
```

### 3.2 The 14 Mental Models

Applied automatically across all components. Every weight, gate, and formula traces to one or more of these models.

| # | Model | One-Line Description |
|---|-------|---------------------|
| 1 | First Principles | Decompose every score into directly observable primitives |
| 2 | Bayesian Reasoning | Confidence intervals widen with less evidence |
| 3 | Signal-to-Noise Ratio | Weight high-SNR sources higher than noisy ones |
| 4 | Systems Thinking (Bottleneck) | Weakest critical component caps the whole score |
| 5 | Information Theory | Run entropy checks; flag monoculture; seek disconfirming data |
| 6 | Behavioral Economics | Design around anchoring, availability, and loss aversion biases |
| 7 | Engineering Safety Factors | Hard gates that override scores on critical failures |
| 8 | Logarithmic Diminishing Returns | Apply log scale to volume/quantity variables |
| 9 | Product Lifecycle Theory | Detect maturity stage; weight velocity and trajectory |
| 10 | Momentum (Physics) | Velocity + direction matter more than current position |
| 11 | Z-Score Normalization | Normalize within category before comparing across categories |
| 12 | Regression to the Mean | Shrink extreme scores from thin evidence toward population mean |
| 13 | Simpson's Paradox | Verify trends hold within each subgroup independently |
| 14 | Goodhart's Law | Add calibration anchors; instruct agents to err toward N when uncertain |

### 3.3 Tool Call Protocol

All ranking, scoring, thresholding, counting, aggregation, and similarity measurement MUST be externalized to Python/calculator tool calls. LLMs never compute scores in-prompt.

| Operation | Why It Must Be Externalized |
|-----------|---------------------------|
| Ranking/ordering | Anchoring bias, recency bias |
| Threshold detection | Self-rating bias, sycophancy |
| Counting for decisions | Numerical reasoning weakness |
| Aggregation | Arithmetic errors, consistency drift |
| Similarity measurement | Pattern completion bias, confirmation bias |
| Estimated yields | Anchoring to round numbers, fabrication risk |

### 3.4 Hard Gates

Binary pass/fail checks that override computed scores. No amount of strength elsewhere compensates for these failures.

| Gate | Trigger | Effect | Component |
|------|---------|--------|-----------|
| Compliance gate | Angle uses treat/cure/diagnose language | Angle rejected | Agent 3 / score_angles.py |
| Evidence floor gate | Angle has fewer than 5 supporting VOC items | Score capped at 20.0 | score_angles.py |
| Plausibility gate | Product cannot deliver on angle promise | Score capped at 30.0 | score_angles.py |
| Mining risk gate | Habitat inaccessible (login, rate-limited, non-text, wrong language) | Score capped at 25.0 | score_habitats.py |
| Zero-evidence gate | VOC item has zero specificity + zero intensity + zero angle potential | Score capped at 5.0 | score_voc.py |
| Saturation gate | Angle cluster entropy below threshold (too homogeneous) | Flagged for diversity review | score_angles.py |

---

## 4. Component Specifications

### 4.1 Competitor Asset Analyzer (Pre-Pipeline)

**Purpose:** Analyze competitor advertising assets to produce a structured saturation map (what angles are already claimed) and whitespace map (what angles are unclaimed). This runs once before the pipeline and feeds all downstream agents.

**Inputs:**
- User-provided competitor assets: ad screenshots, landing page URLs, VSL transcripts, email sequences, Facebook Ad Library exports, funnel screenshots
- Product brief and avatar brief for context

**Process:**
1. For each competitor asset, fill the Competitor Asset Observation Sheet (see Section 6.4)
2. Aggregate observations into a saturation map: which angles are used by which competitors, at what frequency
3. Compute whitespace map: which angle dimensions have zero or low competitor coverage
4. Identify competitor messaging patterns: dominant mechanisms, recurring enemies, common belief shifts

**Competitor Asset Observation Sheet (per asset):**

| Field | Type | Description |
|-------|------|-------------|
| `asset_id` | String | Unique identifier (CA-001, CA-002...) |
| `competitor_name` | String | Brand or company name |
| `asset_type` | Enum | AD_IMAGE / AD_VIDEO / LANDING_PAGE / VSL / EMAIL / FUNNEL_PAGE |
| `platform` | Enum | META / TIKTOK / YOUTUBE / GOOGLE / NATIVE / EMAIL / WEBSITE |
| `target_who` | String | Who is this asset targeting (avatar segment) |
| `primary_pain` | String | The main pain point addressed |
| `primary_desire` | String | The main desired outcome promised |
| `enemy_named` | Y/N | Does the asset name a specific enemy/villain |
| `enemy_description` | String | Who/what is the enemy (if named) |
| `mechanism_type` | Enum | INGREDIENT / PROCESS / SECRET / STORY / AUTHORITY / SOCIAL_PROOF |
| `mechanism_description` | String | How does the product supposedly work |
| `belief_shift_attempted` | String | What belief is the asset trying to change |
| `hook_format` | Enum | QUESTION / STATEMENT / STORY / STATISTIC / CONTRARIAN / DEMONSTRATION |
| `emotional_register` | Enum | FEAR / HOPE / ANGER / SHAME / CURIOSITY / URGENCY / RELIEF |
| `proof_type` | Enum | TESTIMONIAL / STUDY / AUTHORITY / DEMONSTRATION / SOCIAL_PROOF / NONE |
| `compliance_risk` | Enum | GREEN / YELLOW / RED |
| `creative_format` | Enum | UGC / TALKING_HEAD / TEXT_OVERLAY / SLIDESHOW / ANIMATION / PROFESSIONAL |
| `estimated_spend_tier` | Enum | LOW / MEDIUM / HIGH / UNKNOWN |
| `running_duration` | Enum | UNDER_30D / 30_TO_90D / OVER_90D / UNKNOWN |

**Outputs:**
- `competitor_analysis.json` — all observation sheets plus computed saturation and whitespace maps
- Saturation map: `{ angle_dimension: [competitors_using_it] }`
- Whitespace map: `{ angle_dimension: coverage_level }` where coverage_level is NONE / LOW / MODERATE / HIGH

### 4.2 Agent 0: Habitat Strategist (Text-Based Habitats)

**Purpose:** Given foundational docs and competitor analysis, identify where target customers congregate online in text-based habitats, and generate Apify scraper configurations and search queries to extract data from those habitats.

**Key difference from v1 Agent 1:** Agent 0 does NOT qualify habitats. It identifies and strategizes. Qualification happens in Agent 1 after data is scraped. This separation allows scraping to happen between strategy and qualification.

**Inputs:**

| Input | Required | Source |
|-------|----------|--------|
| Avatar Brief | Yes | Foundational docs |
| Offer Brief | Yes | Foundational docs |
| Competitor Research | Yes | Foundational docs |
| `competitor_analysis.json` | Yes | Competitor Asset Analyzer |
| I Believe Statements | No | Foundational docs |

**Process:**
1. **Avatar analysis:** Parse avatar brief to identify psychographic clusters, online behavior patterns, platform preferences, and community affiliations
2. **Habitat identification:** Systematically scan 8 habitat categories (Reddit, Niche Forums, Review Sites, Q&A Platforms, Blog Comments, Facebook Groups, YouTube Comments, Competitor-Adjacent), applying the same scan methodology as v1 Agent 1
3. **Apify configuration generation:** For each identified habitat, generate a specific Apify actor configuration (actor ID, input parameters, expected output format)
4. **Search query generation:** For each habitat, generate 3-5 optimized search queries tailored to the platform's search syntax

**Outputs:**
- `habitat_strategy.json` — identified habitats with rationale, organized by category
- `apify_configs.json` — ready-to-execute Apify actor configurations per habitat
- `search_queries.json` — platform-specific search queries per habitat

**Output schema for `apify_configs.json`:**

```json
{
  "configs": [
    {
      "habitat_id": "H-001",
      "habitat_name": "r/herbalism",
      "habitat_type": "Reddit",
      "apify_actor": "apify/reddit-scraper",
      "actor_input": {
        "startUrls": ["https://reddit.com/r/herbalism"],
        "sort": "new",
        "maxItems": 500,
        "searchMode": "subreddit",
        "includeComments": true,
        "maxComments": 50
      },
      "expected_output_type": "reddit_posts",
      "priority": 1,
      "rationale": "Primary habitat for herbal remedy discussion"
    }
  ]
}
```

### 4.3 Agent 0b: Social Video Strategist

**Purpose:** Identify opportunities on TikTok, Instagram, and YouTube for mining voice-of-customer data from video content, comments, and engagement signals. Runs in parallel with Agent 0.

**Inputs:**

| Input | Required | Source |
|-------|----------|--------|
| Avatar Brief | Yes | Foundational docs |
| Offer Brief | Yes | Foundational docs |
| `competitor_analysis.json` | Yes | Competitor Asset Analyzer |
| Product keywords | Yes | Derived from Offer Brief |

**Two Discovery Modes:**

**Mode 1: Viral Content Discovery**
- Goal: Find high-performing content in the product category to understand what resonates
- Generate virality filter parameters (minimum view counts, engagement thresholds)
- Focus on content that went viral organically (not paid promotion)
- Output: search configs filtered for high-engagement content

**Mode 2: Topic/Keyword/Hashtag Mining**
- Goal: Map the hashtag and keyword landscape around the product category
- Identify relevant hashtags, trending sounds, and content formats
- Map competitor accounts and their content strategies
- Output: keyword clusters, hashtag maps, competitor account lists

**Outputs:**
- `social_video_configs.json` — Apify actor configurations for TikTok, Instagram, YouTube scrapers
- `hashtag_clusters.json` — organized hashtag taxonomy with estimated volume
- `competitor_accounts.json` — competitor social accounts with content analysis

**Output schema for `social_video_configs.json`:**

```json
{
  "configs": [
    {
      "platform": "tiktok",
      "apify_actor": "clockworks/tiktok-scraper",
      "discovery_mode": "viral_content",
      "actor_input": {
        "searchQueries": ["herbal remedies", "natural health tips"],
        "resultsPerPage": 100,
        "shouldDownloadVideos": false,
        "shouldDownloadComments": true,
        "maxComments": 100
      },
      "virality_filters": {
        "min_views": 10000,
        "min_engagement_rate": 0.03
      },
      "priority": 1
    }
  ]
}
```

### 4.4 Apify Scraper Layer

**Purpose:** Infrastructure layer that executes scrape configurations from Agents 0 and 0b, normalizes output data into a consistent format, and stores results for Agent 1 to process.

**Supported Actors:**

| Platform | Apify Actor | Data Type | Output Location |
|----------|-------------|-----------|-----------------|
| Reddit | `apify/reddit-scraper` | Posts + comments | `raw_scraped_data/text_habitats/reddit/` |
| General Web | `apify/web-scraper` | HTML content | `raw_scraped_data/text_habitats/web/` |
| Trustpilot | `apify/trustpilot-reviews-scraper` | Reviews | `raw_scraped_data/text_habitats/trustpilot/` |
| Amazon | `junglee/amazon-reviews-scraper` | Product reviews | `raw_scraped_data/text_habitats/amazon/` |
| Google SERP | `apify/google-search-scraper` | Search results | `raw_scraped_data/text_habitats/google/` |
| TikTok | `clockworks/tiktok-scraper` | Videos + comments | `raw_scraped_data/social_video/tiktok/` |
| Instagram | `apify/instagram-scraper` | Posts + comments | `raw_scraped_data/social_video/instagram/` |
| YouTube | `streamers/youtube-scraper` | Videos + comments | `raw_scraped_data/social_video/youtube/` |

**Integration Modes:**

| Mode | When to Use | How It Works |
|------|------------|--------------|
| Automated (API) | Repeat runs, large-scale scrapes | Script reads `apify_configs.json`, calls Apify API, stores output |
| Manual (Console) | First runs, debugging, small scrapes | Operator copies config into Apify console, downloads results manually |

**Output Format Normalization:**

All scraped data is normalized into a common envelope format before Agent 1 processes it:

```json
{
  "source_platform": "reddit",
  "habitat_id": "H-001",
  "habitat_name": "r/herbalism",
  "scrape_timestamp": "2026-02-20T14:30:00Z",
  "item_count": 487,
  "items": [
    {
      "item_id": "scraped-001",
      "content_type": "post",
      "title": "...",
      "body": "...",
      "author": "...",
      "date": "...",
      "url": "...",
      "engagement": {
        "upvotes": 45,
        "comments": 12,
        "shares": 3
      },
      "comments": [...]
    }
  ]
}
```

For video platforms, items include additional fields:

```json
{
  "item_id": "scraped-v001",
  "content_type": "video",
  "caption": "...",
  "author": "...",
  "date": "...",
  "url": "...",
  "engagement": {
    "views": 125000,
    "likes": 8400,
    "comments": 342,
    "shares": 1200,
    "saves": 560
  },
  "duration_seconds": 47,
  "hashtags": ["#herbalism", "#naturalhealth"],
  "sound_name": "...",
  "comments": [...]
}
```

**Error Handling:**
- Rate limit errors: exponential backoff with max 3 retries
- Empty results: logged as `EMPTY_SCRAPE` with config details for debugging
- Partial results: accepted with `partial: true` flag and item count
- Actor failures: logged with error message, config preserved for retry

### 4.5 score_virality.py (NEW)

**Purpose:** Score social video content for virality signals before Agent 1 processes it. This pre-scoring enriches the data so Agent 1 can observe virality tiers rather than raw numbers.

**Three Metrics:**

**1. Virality Ratio (weight: 0.4)**

Measures how engagement scales relative to the creator's typical audience.

```python
def virality_ratio(views, likes, comments, shares, follower_count):
    """
    Virality = total engagement / expected engagement.
    Expected engagement is estimated from follower count.

    [Logarithmic Diminishing Returns] Applied to follower count
    to prevent large accounts from dominating.

    Rationale for 0.4 weight: Virality ratio is the strongest
    predictor of organic resonance. Content that outperforms its
    expected reach has found a nerve. This is the primary signal
    for angle discovery.
    """
    total_engagement = likes + comments * 2 + shares * 3
    if follower_count > 0:
        expected_engagement = math.log(max(1, follower_count)) * 10
        ratio = total_engagement / expected_engagement
    else:
        ratio = total_engagement / 100  # baseline for unknown followers
    return min(1.0, ratio / 10)  # normalize to 0-1, cap at 10x
```

**2. Velocity (weight: 0.3)**

Measures how quickly engagement accumulated relative to content age.

```python
def velocity_score(total_engagement, hours_since_posted):
    """
    Velocity = engagement per hour, log-scaled.

    [Momentum] Fast accumulation signals trending content.

    Rationale for 0.3 weight: Velocity captures momentum.
    Content gaining engagement quickly is riding a wave that
    may represent an emerging angle. Slightly lower than
    virality ratio because velocity alone can be driven by
    paid promotion.
    """
    if hours_since_posted <= 0:
        hours_since_posted = 1
    raw_velocity = total_engagement / hours_since_posted
    return min(1.0, math.log(max(1, raw_velocity)) / math.log(500))
```

**3. Engagement Density (weight: 0.3)**

Measures the depth of engagement (comments, shares) relative to passive engagement (views, likes).

```python
def engagement_density(views, likes, comments, shares):
    """
    Density = deep engagement / surface engagement.
    Comments and shares indicate active processing;
    views and likes indicate passive consumption.

    [Signal-to-Noise] Deep engagement is high-signal;
    passive views are low-signal.

    Rationale for 0.3 weight: Engagement density
    differentiates content that provoked thought from
    content that was merely seen. Comments contain VOC
    data; shares indicate social proof potential.
    """
    deep = comments * 2 + shares * 3
    surface = max(1, views * 0.01 + likes)
    density = deep / surface
    return min(1.0, density)
```

**Composite Score:**

```python
def score_virality_composite(video_data):
    vr = virality_ratio(...)   # 0-1
    vs = velocity_score(...)   # 0-1
    ed = engagement_density(...)  # 0-1

    composite = vr * 0.4 + vs * 0.3 + ed * 0.3
    return round(composite * 100, 1)
```

**Tier Labels:**

| Tier | Score Range | Interpretation |
|------|------------|----------------|
| VIRAL | 75-100 | Exceptional organic resonance; high-priority for angle mining |
| HIGH_PERFORMING | 50-74 | Strong engagement; likely hit a real nerve |
| ABOVE_AVERAGE | 25-49 | Better than baseline; worth including in analysis |
| BASELINE | 0-24 | Typical content; low priority for angle mining |

**High Authority Track:**

Videos with 100K+ views receive a separate analysis track regardless of virality score. High-view content from large accounts may have low virality ratios but still contains valuable angle signals due to the sheer volume of comments.

```python
def high_authority_flag(views):
    return views >= 100000
```

### 4.6 Agent 1: Habitat Qualifier

**Purpose:** Process all pre-scraped data (text habitats and video habitats) through structured observation sheets. Agent 1 does NOT browse the web. It receives pre-scraped data and observes.

**Key difference from v1 Agent 1:** In v1, Agent 1 both discovered and qualified habitats. In v2, discovery is split to Agent 0/0b, and qualification is isolated to Agent 1 working on pre-scraped data. This separation eliminates the quality degradation from doing both tasks in one context window.

**Inputs:**

| Input | Required | Source |
|-------|----------|--------|
| `raw_scraped_data/text_habitats/` | Yes | Apify Scraper Layer |
| `raw_scraped_data/social_video/` | Yes (if video habitats exist) | Apify Scraper Layer |
| `competitor_analysis.json` | Yes | Competitor Asset Analyzer |
| Foundational docs | Yes | Shared context |

**Text Habitat Observation Sheet: 52 fields (unchanged from v1)**

The complete 52-field observation sheet from v1 is preserved without modification. See Section 6.1 for the full schema.

**Video Habitat Observation Sheet: 52 + 11 new fields**

For video habitats, Agent 1 fills the standard 52 fields PLUS 11 video-specific fields:

| Field | Type | Description |
|-------|------|-------------|
| `video_count_scraped` | Integer | Number of videos scraped from this habitat |
| `median_view_count` | Integer | Median view count across scraped videos |
| `viral_videos_found` | Y/N | Were any videos scored VIRAL or HIGH_PERFORMING by score_virality.py |
| `viral_video_count` | Integer | Count of VIRAL + HIGH_PERFORMING videos |
| `comment_sections_active` | Y/N | Do video comment sections contain substantive discussion (not just emoji/tags) |
| `comment_avg_length` | Enum | SHORT (<20 words) / MEDIUM (20-50 words) / LONG (50+ words) |
| `hook_formats_identifiable` | Y/N | Can distinct hook formats be identified from video openings |
| `creator_diversity` | Enum | SINGLE / FEW (2-5) / MANY (6+) — how many distinct creators |
| `contains_testimonial_language` | Y/N | Do videos or comments contain testimonial-style language |
| `contains_objection_language` | Y/N | Do comments contain objections, skepticism, or pushback |
| `contains_purchase_intent` | Y/N | Do comments contain purchase intent signals ("where can I buy", "link?") |

**Mining Risk Hard Gate (same as v1):**

If a habitat answers N to any of the four mining risk observables (`publicly_accessible`, `text_based_content`, `target_language`, `no_rate_limiting`), the habitat score is capped at 25.0 regardless of other components.

Note: For video habitats, `text_based_content` is evaluated based on whether the comments and captions provide sufficient text data for VOC extraction, not whether the primary content is text.

**Outputs:**
- `habitat_observations.json` — complete observation sheets for all habitats
- Fed to `score_habitats.py` for scoring

### 4.7 Agent 2: VOC Extractor (Enhanced)

**Purpose:** Extract, structure, and tag voice-of-customer data from scored habitats. Enhanced in v2 to process three source categories instead of one.

**Three Source Categories:**

| Category | Sources | VOC Type | Source Type Tags |
|----------|---------|----------|-----------------|
| Text VOC | Forums, reviews, blogs, Q&A, Reddit posts | Written statements, reviews, discussions | REDDIT / FORUM / REVIEW / QA / BLOG |
| Comment VOC | TikTok comments, IG comments, YouTube comments | Short-form reactions under video content | TIKTOK_COMMENT / IG_COMMENT / YT_COMMENT |
| Video Hook VOC | Video openings, captions, spoken hooks | Content creator framing of the topic | VIDEO_HOOK |

**New source_type Tags (v2):**

Added to the existing source_type field on each VOC item:

| Tag | Description |
|-----|-------------|
| `TIKTOK_COMMENT` | Comment extracted from a TikTok video |
| `IG_COMMENT` | Comment extracted from an Instagram post/reel |
| `YT_COMMENT` | Comment extracted from a YouTube video |
| `VIDEO_HOOK` | Hook/opening extracted from video content itself |

**New Hook Fields (for VIDEO_HOOK items):**

| Field | Type | Description |
|-------|------|-------------|
| `is_hook` | Y/N | Is this item extracted from a video hook (first 3-5 seconds) |
| `hook_format` | Enum | QUESTION / STATEMENT / STORY / STATISTIC / CONTRARIAN / DEMONSTRATION |
| `hook_word_count` | Integer | Word count of the hook text |
| `video_virality_tier` | Enum | VIRAL / HIGH_PERFORMING / ABOVE_AVERAGE / BASELINE |
| `video_view_count` | Integer | View count of the source video |

**Competitor Saturation Tagging:**

For each VOC item, cross-reference against `competitor_analysis.json`:
- Tag items that align with known saturated angles: `competitor_saturation: [angle_id_list]`
- Tag items in whitespace areas: `in_whitespace: Y/N`

This tagging carries through to Agent 3, enabling saturation-aware clustering.

**All other Agent 2 behavior is unchanged from v1:** dual mode operation, 8 core extraction dimensions, anti-cherry-picking protocol, pattern detection (intensity spikes, sleeping giants, language registry), purchase barrier extraction, cross-habitat triangulation, Simpson's Paradox checks, deduplication, contradiction harvesting, thematic clustering, and corpus health audit.

### 4.8 Agent 3: Shadow Angle Clusterer (Enhanced)

**Purpose:** Cluster underserved angles from the scored VOC corpus, overlay competitor saturation data, and output ranked Purple Ocean candidates.

**Enhanced with `competitor_analysis.json` overlay:**

Agent 3 now receives `competitor_analysis.json` as a primary input alongside the VOC corpus. This enables:

1. **Direct saturation cross-referencing:** For each candidate angle, automatically check whether it overlaps with angles in the saturation map
2. **Whitespace targeting:** Prioritize angle construction in areas the whitespace map identifies as unclaimed
3. **Competitor pattern awareness:** Understanding how competitors construct their mechanisms and belief shifts prevents accidental replication

**New Observation Field:**

| Field | Type | Description |
|-------|------|-------------|
| `competitor_angle_overlap` | Y/N | Does this candidate angle substantially overlap (3+ shared dimensions) with any angle in the competitor saturation map |

When `competitor_angle_overlap = Y`, the angle is not automatically rejected but is flagged for the user's attention. The differentiation map (already in v1) provides the detailed dimensional comparison.

**All other Agent 3 behavior is unchanged from v1:** 3-of-4 dimensional clustering, angle primitive construction, saturation differentiation analysis, evidence assembly, hook starter generation, observation sheets, evidence floor gate, intra-candidate overlap detection, pre-mortem checks, and decision readiness blocks.

---

## 5. Scoring Scripts

### 5.1 score_virality.py (NEW)

- **Input:** Raw social video data from Apify scraper output (`raw_scraped_data/social_video/`)
- **Output:** Scored videos with virality composite (0-100) and tier label (VIRAL / HIGH_PERFORMING / ABOVE_AVERAGE / BASELINE)
- **Formulas:** See Section 4.5 for complete formula documentation
- **Weight justification:**
  - Virality ratio (0.4): strongest predictor of organic resonance [First Principles]
  - Velocity (0.3): captures momentum and trending signals [Momentum]
  - Engagement density (0.3): differentiates active processing from passive consumption [Signal-to-Noise]
- **Sensitivity notes:**
  - Doubling virality ratio weight (0.4 to 0.8): over-indexes on small-account breakouts, may miss steady large-account content
  - Halving engagement density weight (0.3 to 0.15): reduces comment-driven signals, which are the primary VOC source from video platforms
  - High Authority Track (100K+ views) ensures large-account content is never ignored regardless of ratio scores [Engineering Safety]

### 5.2 score_habitats.py (EXTENDED)

Preserved from v1 with extensions for video habitat fields.

**10 Components (unchanged weights):**

| Component | Weight | Rationale | Mental Model |
|-----------|--------|-----------|-------------|
| volume | 0.05 | Floor check, not quality signal | Logarithmic Diminishing Returns |
| recency | 0.10 | Temporal relevance; recent = current market state | Momentum |
| specificity | 0.14 | On-topic precision; direct signals worth more | First Principles |
| emotional_depth | 0.18 | Core mining value; the raw material for angles | First Principles |
| buyer_density | 0.13 | Intent signals predict conversion | Behavioral Economics |
| language_quality | 0.14 | Predicts VOC richness from depth samples | First Principles |
| habitat_snr | 0.07 | Signal / (signal + noise) efficiency | Signal-to-Noise |
| competitor_whitespace | 0.07 | Mining same source as competitors yields diminishing unique insights | Information Theory |
| market_timing | 0.06 | Trend direction + habitat lifecycle stage | Momentum + Product Lifecycle |
| mining_feasibility | 0.06 | Hard gate at 0.5; inaccessible habitat = worthless | Engineering Safety |

**Video Habitat Extension:**

For habitats with video data, the scoring script applies video-specific modifiers:

```python
def apply_video_modifiers(base_components, video_obs):
    """
    Adjust component scores for video habitats based on
    video-specific observation fields.

    Video habitats have different signal profiles:
    - Comments may be shorter but more emotionally raw
    - Volume is measured in videos, not threads
    - Engagement signals include views, shares, saves
    """
    if video_obs.get('viral_videos_found') == 'Y':
        # Viral content signals proven demand resonance
        base_components['emotional_depth'] *= 1.15
        base_components['emotional_depth'] = min(1.0, base_components['emotional_depth'])

    if video_obs.get('comment_sections_active') == 'Y':
        # Active comment sections are high-value mining targets
        base_components['language_quality'] *= 1.10
        base_components['language_quality'] = min(1.0, base_components['language_quality'])

    if video_obs.get('contains_purchase_intent') == 'Y':
        # Purchase intent in comments is a strong buyer density signal
        base_components['buyer_density'] *= 1.20
        base_components['buyer_density'] = min(1.0, base_components['buyer_density'])

    # Creator diversity affects SNR
    diversity_modifier = {
        'SINGLE': 0.85,  # single creator = potential echo chamber
        'FEW': 1.0,
        'MANY': 1.10     # many creators = organic topic coverage
    }.get(video_obs.get('creator_diversity', 'FEW'), 1.0)
    base_components['habitat_snr'] *= diversity_modifier
    base_components['habitat_snr'] = min(1.0, base_components['habitat_snr'])

    return base_components
```

### 5.3 score_voc.py (UNCHANGED)

Preserved exactly from v1. No modifications.

**6 Components with weights:**

| Component | Weight | Mental Model |
|-----------|--------|-------------|
| specificity | 0.22 | First Principles |
| intensity | 0.18 | Behavioral Economics |
| angle_potential (adjusted) | 0.25 | First Principles + SNR |
| credibility | 0.15 | Bayesian Reasoning |
| dimension_bonus | 0.13 | Information Theory |
| signal_density | 0.07 | Signal-to-Noise |

**Preserved features:**
- Freshness decay (durable psychology vs. market-specific)
- Bottleneck cap (weakest critical dimension caps composite)
- Zero-evidence gate (specificity + intensity + angle_potential all zero = capped at 5.0)
- Confidence intervals (width from credibility + dimension completeness)
- Aspiration gap (derived from observables)
- Regression to the Mean shrinkage

### 5.4 score_angles.py (UNCHANGED)

Preserved exactly from v1. No modifications.

**9 Components with weights:**

| Component | Weight | Mental Model |
|-----------|--------|-------------|
| distinctiveness | 0.20 | Information Theory + Systems Thinking |
| evidence_quality | 0.18 | Bayesian Reasoning + SNR |
| demand_signal | 0.15 | Logarithmic Diminishing Returns |
| pain_intensity | 0.13 | Behavioral Economics (loss aversion) |
| compliance_safety | 0.07 | Engineering Safety |
| market_timing | 0.07 | Momentum + Product Lifecycle |
| executability | 0.06 | First Principles |
| addressable_scope | 0.06 | First Principles |
| plausibility | 0.05 | Engineering Safety (hard gate at 0.5) |

**Preserved features:**
- Plausibility hard gate (score capped at 30.0)
- Evidence floor gate (fewer than 5 VOC items = capped at 20.0)
- Source diversity modifier (Simpson's Paradox check)
- Lifecycle stage prediction
- Variance-aware confidence intervals
- Intra-candidate overlap detection

---

## 6. Observation Sheet Schemas

### 6.1 Habitat Observation Sheet (52 fields + 11 video)

**Core 52 Fields (unchanged from v1):**

```
=== HABITAT OBSERVATION SHEET ===
HABITAT_NAME: [string]
HABITAT_TYPE: [Reddit / Forum / Review_Site / QA / Blog_Comments / FB_Group / YouTube / Competitor_Adjacent / TikTok / Instagram]
URL_PATTERN: [string]

# VOLUME (3 fields)
threads_50_plus: [Y/N]
threads_200_plus: [Y/N]
threads_1000_plus: [Y/N]

# RECENCY (4 fields)
posts_last_3mo: [Y/N]
posts_last_6mo: [Y/N]
posts_last_12mo: [Y/N]
recency_ratio: [MAJORITY_RECENT / BALANCED / MAJORITY_OLD]

# SPECIFICITY (4 fields)
exact_category: [Y/N]
purchasing_comparing: [Y/N]
personal_usage: [Y/N]
adjacent_only: [Y/N]

# EMOTIONAL DEPTH (5 fields)
first_person_narratives: [Y/N]
trigger_events: [Y/N]
fear_frustration_shame: [Y/N]
specific_dollar_or_time: [Y/N]
long_detailed_posts: [Y/N]

# BUYER SIGNALS (3 fields)
comparison_discussions: [Y/N]
price_value_mentions: [Y/N]
post_purchase_experience: [Y/N]

# SIGNAL-TO-NOISE (2 fields)
relevance_pct: [OVER_50_PCT / 25_TO_50_PCT / 10_TO_25_PCT / UNDER_10_PCT]
dominated_by_offtopic: [Y/N]

# COMPETITOR OVERLAP (3 fields)
competitor_brands_mentioned: [Y/N]
competitor_brand_count: [0 / 1-3 / 4-7 / 8+]
competitor_ads_present: [Y/N]

# TREND (3 fields)
trend_direction: [HIGHER / SAME / LOWER / CANNOT_DETERMINE]
seasonal_patterns: [Y/N]
seasonal_description: [string or N/A]

# LIFECYCLE (3 fields)
habitat_age: [UNDER_1YR / 1_TO_3YR / 3_TO_7YR / OVER_7YR]
membership_trend: [GROWING / STABLE / DECLINING / CANNOT_DETERMINE]
post_frequency_trend: [INCREASING / SAME / DECREASING / CANNOT_DETERMINE]

# MINING RISK (4 fields)
publicly_accessible: [Y/N]
text_based_content: [Y/N]
target_language: [Y/N]
no_rate_limiting: [Y/N]

# BUYER DENSITY (3 fields)
purchase_intent_density: [MOST / SOME / FEW / NONE]
discusses_spending: [Y/N]
recommendation_threads: [Y/N]

# REUSABILITY (1 field)
reusability: [PRODUCT_SPECIFIC / PATTERN_REUSABLE]

# LANGUAGE DEPTH SAMPLES (variable, 3-5 per habitat)
language_samples: [array of sample objects]
  - post_url: [string]
  - has_trigger_event: [Y/N]
  - has_failed_solution: [Y/N]
  - has_identity_language: [Y/N]
  - has_specific_outcome: [Y/N]
  - word_count: [integer]

# COMPETITIVE OVERLAP (2 fields)
competitors_active: [string list]
overlap_level: [HIGH / MEDIUM / LOW / NONE]

# TREND+LIFECYCLE (2 fields)
trend_evidence: [string]
lifecycle_evidence: [string]
```

**11 Video Extension Fields (NEW in v2):**

```
# VIDEO-SPECIFIC FIELDS (only for video habitats)
video_count_scraped: [integer]
median_view_count: [integer]
viral_videos_found: [Y/N]
viral_video_count: [integer]
comment_sections_active: [Y/N]
comment_avg_length: [SHORT / MEDIUM / LONG]
hook_formats_identifiable: [Y/N]
creator_diversity: [SINGLE / FEW / MANY]
contains_testimonial_language: [Y/N]
contains_objection_language: [Y/N]
contains_purchase_intent: [Y/N]
```

### 6.2 VOC Item Observation Sheet (24 fields + 5 video hook)

**Core 24 Fields (unchanged from v1):**

```
=== VOC ITEM OBSERVATION SHEET ===
VOC_ID: [string]

# SPECIFICITY (5 fields)
specific_number: [Y/N]
specific_product_brand: [Y/N]
specific_event_moment: [Y/N]
specific_body_symptom: [Y/N]
before_after_comparison: [Y/N]

# EMOTIONAL INTENSITY (5 fields)
crisis_language: [Y/N]
profanity_extreme_punctuation: [Y/N]
physical_sensation: [Y/N]
identity_change_desire: [Y/N]
word_count: [integer]

# ANGLE POTENTIAL (5 fields)
clear_trigger_event: [Y/N]
named_enemy: [Y/N]
shiftable_belief: [Y/N]
expectation_vs_reality: [Y/N]
headline_ready: [Y/N]

# SOURCE CREDIBILITY (5 fields)
personal_context: [Y/N]
long_narrative: [Y/N]
engagement_received: [Y/N]
real_person_signals: [Y/N]
moderated_community: [Y/N]

# SIGNAL DENSITY (1 field)
usable_content_pct: [OVER_75_PCT / 50_TO_75_PCT / 25_TO_50_PCT / UNDER_25_PCT]

# TEMPORAL (3 fields)
date_bracket: [LAST_3MO / LAST_6MO / LAST_12MO / LAST_24MO / OLDER / UNKNOWN]
durable_psychology: [Y/N]
market_specific: [Y/N]
```

**5 Video Hook Extension Fields (NEW in v2):**

```
# VIDEO HOOK FIELDS (only for VIDEO_HOOK source type)
is_hook: [Y/N]
hook_format: [QUESTION / STATEMENT / STORY / STATISTIC / CONTRARIAN / DEMONSTRATION]
hook_word_count: [integer]
video_virality_tier: [VIRAL / HIGH_PERFORMING / ABOVE_AVERAGE / BASELINE]
video_view_count: [integer]
```

### 6.3 Angle Observation Sheet (40+ fields, unchanged from v1 except one new field)

Full schema preserved from v1 (see Agent 3 specification in v1 design doc). Fields include:
- Demand signal observables (6 fields)
- Pain intensity observables (5 fields)
- Distinctiveness observables (5 fields per saturated angle)
- Plausibility observables (4 fields)
- Evidence quality observables (4 fields)
- Source diversity observables (2 fields)
- Compliance observables (4 fields)
- Market timing observables (8 fields)
- Addressable scope observables (2 fields)
- Creative executability observables (4 fields)
- Lifecycle stage observables (2 fields)
- Dependency risk observables (3 fields)

**New field (v2):**

```
# COMPETITOR OVERLAP (1 field)
competitor_angle_overlap: [Y/N] — Does this angle overlap 3+ dimensions with any competitor angle from competitor_analysis.json
```

### 6.4 Competitor Asset Observation Sheet (18 fields)

See Section 4.1 for the complete field list with types and enum options.

### 6.5 Video Habitat Extension Schema

See Section 6.1 (11 video extension fields) for the complete field list.

---

## 7. Handoff Protocols

### 7.1 Protocol Format

Every handoff between components includes three blocks:

1. **Human-readable block:** Plain-language summary of findings, reasoning, and flags. For audit.
2. **Machine-readable block:** Structured JSON with the exact schema the next component expects. For downstream consumption.
3. **Lineage metadata:** Which component produced this, what inputs it received, timestamp, and prompt version.

```
<!-- HANDOFF START -->
{
  "lineage": {
    "producer": "agent-00-habitat-strategist",
    "producer_version": "2.0.0",
    "timestamp": "2026-02-20T14:30:00Z",
    "inputs_received": ["avatar_brief", "offer_brief", "competitor_analysis.json"],
    "input_validation": "PASS"
  },
  "data": { ... }
}
<!-- HANDOFF END -->
```

### 7.2 Handoff Map

| From | To | Handoff Content |
|------|----|----------------|
| Competitor Asset Analyzer | All downstream agents | `competitor_analysis.json` (saturation map, whitespace map, asset observations) |
| Agent 0 | Apify Scraper Layer | `apify_configs.json`, `search_queries.json`, `habitat_strategy.json` |
| Agent 0b | Apify Scraper Layer | `social_video_configs.json`, `hashtag_clusters.json`, `competitor_accounts.json` |
| Apify Scraper Layer | score_virality.py | Raw video data for virality scoring |
| score_virality.py | Agent 1 | Scored video data with tier labels |
| Apify Scraper Layer | Agent 1 | Raw text habitat data (`raw_scraped_data/`) |
| Agent 1 | score_habitats.py | `habitat_observations.json` |
| score_habitats.py | Agent 2 | Scored habitats with ranked mining plan |
| Agent 2 | score_voc.py | VOC observation sheets |
| score_voc.py | Agent 3 | Scored VOC corpus |
| Agent 3 | score_angles.py | Angle observation sheets |
| score_angles.py | User | Final ranked Purple Ocean angle candidates |

### 7.3 Handoff Validation Rules

Every receiving component MUST validate its handoff before proceeding:

1. Confirm all required fields are present
2. Confirm field types match schema expectations
3. Confirm lineage metadata is present and producer is the expected upstream component
4. Flag any missing or malformed data
5. Refuse to proceed if critical fields are absent; proceed with warnings if optional fields are missing

---

## 8. Apify Integration Spec

### 8.1 API Authentication

```
APIFY_TOKEN: stored in environment variable
API_BASE: https://api.apify.com/v2
```

All API calls use the token in the Authorization header. Token is NEVER stored in code or configuration files.

### 8.2 Actor Configuration Schemas

Each Apify actor accepts a specific input schema. The `apify_configs.json` file from Agent 0/0b contains the complete input for each actor. Key parameters per actor:

**Reddit Scraper (`apify/reddit-scraper`):**
```json
{
  "startUrls": ["https://reddit.com/r/..."],
  "searchQueries": ["query1", "query2"],
  "sort": "new",
  "maxItems": 500,
  "includeComments": true,
  "maxComments": 50,
  "proxy": { "useApifyProxy": true }
}
```

**TikTok Scraper (`clockworks/tiktok-scraper`):**
```json
{
  "searchQueries": ["keyword1", "keyword2"],
  "hashtags": ["#hashtag1"],
  "resultsPerPage": 100,
  "shouldDownloadVideos": false,
  "shouldDownloadComments": true,
  "maxComments": 100
}
```

**YouTube Scraper (`streamers/youtube-scraper`):**
```json
{
  "searchQueries": ["keyword1"],
  "maxResults": 50,
  "includeComments": true,
  "maxComments": 200,
  "sortBy": "relevance"
}
```

### 8.3 Rate Limiting Considerations

| Platform | Rate Limit | Mitigation |
|----------|-----------|------------|
| Reddit | 60 requests/minute | Apify handles internally; batch scrapes |
| TikTok | Aggressive anti-bot | Use residential proxies via Apify |
| Instagram | Session-based limits | Limit to 100 posts per scrape run |
| YouTube | API quota (10,000 units/day) | Prioritize high-value searches; cache results |
| Amazon | IP-based throttling | Use Apify proxy rotation |
| Trustpilot | Moderate | Standard Apify proxy sufficient |

### 8.4 Output Format Normalization

All Apify actor outputs are normalized into the common envelope format described in Section 4.4 before being stored in `raw_scraped_data/`. The normalization script handles:

- Flattening nested JSON structures
- Standardizing date formats to ISO 8601
- Extracting engagement metrics into a consistent `engagement` object
- Generating unique `item_id` values
- Preserving the original raw data as `_raw` for debugging

### 8.5 Error Handling

| Error Type | Response | Retry |
|-----------|----------|-------|
| Authentication failure | Log error, alert operator | No retry; fix token |
| Rate limit (429) | Exponential backoff: 30s, 60s, 120s | Max 3 retries |
| Actor timeout | Log partial results with `partial: true` | Retry with reduced `maxItems` |
| Empty results | Log as `EMPTY_SCRAPE` | Retry with broadened search queries |
| Malformed output | Log raw output for debugging | No retry; fix normalization |
| Network error | Standard retry | Max 3 retries with backoff |

---

## 9. File Structure

```
Research Engine v2/
  prompts/
    agent-pre-competitor-asset-analyzer.md
    agent-00-habitat-strategist.md
    agent-00b-social-video-strategist.md
    agent-01-habitat-qualifier.md
    agent-02-voc-extractor.md
    agent-03-shadow-angle-clusterer.md
  scoring/
    score_virality.py          # NEW — video virality scoring
    score_habitats.py          # EXTENDED — video habitat modifiers
    score_voc.py               # UNCHANGED
    score_angles.py            # UNCHANGED
  apify/
    README.md                  # Integration guide: setup, auth, manual vs automated mode
  schemas/
    habitat_observation_schema.json
    voc_observation_schema.json
    angle_observation_schema.json
    competitor_asset_schema.json
    video_habitat_extension_schema.json
  docs/
    plans/
      2026-02-20-pipeline-v2-design.md    # THIS FILE
```

**Runtime data directories (created during execution):**

```
  data/
    competitor_analysis.json
    habitat_strategy.json
    apify_configs.json
    search_queries.json
    social_video_configs.json
    hashtag_clusters.json
    competitor_accounts.json
    raw_scraped_data/
      text_habitats/
        reddit/
        web/
        trustpilot/
        amazon/
        google/
      social_video/
        tiktok/
        instagram/
        youtube/
    habitat_observations.json
    habitat_scores.json
    voc_observations.json
    voc_scores.json
    angle_observations.json
    angle_scores.json
```

---

## 10. What Changed from v1

| Change | Description | Rationale |
|--------|------------|-----------|
| Agent 1 split into Agent 0 + Agent 1 | Discovery (Agent 0) separated from qualification (Agent 1) | Context window optimization; each agent does one job well. Discovery requires creativity; qualification requires rigor. Mixing them degraded both. |
| New Agent 0b | Social Video Strategist for TikTok, IG, YouTube | Video platforms contain massive VOC signal invisible to text-only mining. TikTok comments are among the rawest pain language sources available. |
| New Competitor Asset Analyzer | Structured pre-pipeline competitor analysis | v1 relied on ad-hoc competitor data. Structured analysis produces a reusable saturation map that all agents consume consistently. |
| Apify scraper layer | Infrastructure between strategy and qualification | Replaces manual browsing with structured data pipelines. Enables larger-scale, more consistent data collection. |
| score_virality.py added | Virality scoring for social video content | Video engagement signals require their own scoring model. Views, likes, shares, and comments have different information value than text engagement. |
| Video habitat observation fields | 11 new fields for video-specific signals | Text habitat fields do not capture video-specific signals like hook formats, creator diversity, and comment-section activity. |
| Video hook VOC fields | 5 new fields for VIDEO_HOOK source type | Video hooks are a distinct VOC category requiring format, virality tier, and view count metadata. |
| Competitor saturation overlay | Agent 2 tags VOC against saturation map; Agent 3 uses for angle overlap | Direct integration of competitor intelligence into the extraction and clustering steps. |
| New HABITAT_TYPE values | TikTok and Instagram added as habitat types | Extending the habitat taxonomy to cover video-native platforms. |

---

## 11. What Did NOT Change from v1

The following elements are preserved without modification. This is intentional. The v1 foundation is battle-tested and any changes would require re-validation.

| Element | Status | Why Unchanged |
|---------|--------|--------------|
| "Agent Observes, Math Decides" principle | Preserved | Core architectural invariant. Changing this breaks the entire system's reliability model. |
| All 14 mental models | Preserved | Models 12-14 added in the v1 hardening pass are still current. No new models identified. |
| Tool Call Protocol | Preserved | The externalization requirement applies equally to v2 components. |
| Existing observation sheet schemas | Extended, not replaced | v1 fields remain the stable base. Extensions add fields; they never remove or modify existing ones. |
| Hard gates (compliance, evidence floor, mining risk, plausibility) | Preserved | Gates are non-negotiable safety boundaries. Relaxing them would compromise output quality. |
| score_habitats.py formula | Extended for video fields | Core 10-component formula and weights unchanged. Video modifiers are applied after base computation. |
| score_voc.py formula | Unchanged | 6-component formula, freshness decay, bottleneck cap, zero-evidence gate all preserved exactly. |
| score_angles.py formula | Unchanged | 9-component Purple Ocean formula, plausibility gate, evidence floor gate all preserved exactly. |
| Agent 2 core logic | Enhanced with new source types | Extraction dimensions, observation sheets, pattern detection, health audit all unchanged. New source types and tags are additive. |
| Agent 3 core logic | Enhanced with competitor overlay | Clustering algorithm, angle primitive construction, differentiation analysis all unchanged. Competitor overlay is additive. |
| Handoff protocol format | Preserved | Human-readable + machine-readable + lineage metadata. Format unchanged; content expanded for new data types. |
| Compliance rules | Preserved | NEVER use treat/cure/diagnose. Always flag medical claims. Non-negotiable in health/wellness category. |
| Z-Score normalization | Preserved | Applied at all levels (habitat, VOC, angle) for cross-product comparability. |
| Confidence intervals | Preserved | Bayesian intervals at all levels with width proportional to evidence uncertainty. |
| Anti-cherry-picking protocol | Preserved | Required sampling from multiple engagement levels, time periods, and viewpoints. |
| Calibration anchors (Goodhart's Law) | Preserved | Concrete examples of Y vs N for judgment-prone observation fields. |

---

*End of Design Document*
