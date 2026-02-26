# Strategy V2 Asset Data Provision Plan (Apify-Backed)

**Date:** 2026-02-24  
**Status:** In implementation (phase 1 started 2026-02-24)  
**Owner:** Strategy V2 workflow + ingestion layer  
**Objective:** Define exactly which Strategy V2 steps require asset data, what payload each step needs, and how to provision that data using existing Apify integrations plus targeted new Apify scrapers.

---

## 0) Implementation Status (Started)

### Completed in code (phase 1)
- Added deterministic H2 candidate scoring module at `mos/backend/app/strategy_v2/score_candidate_assets.py`.
- Added deterministic selection with explicit diversity caps:
- `max_candidates=40`
- `max_per_competitor=3`
- `max_per_platform=10`
- Wired pre-H2 candidate preparation activity:
- `strategy_v2.prepare_competitor_asset_candidates`
- Wired workflow so H2 `pending_decision_payload` now includes:
- `competitor_urls`
- `candidates` (scored rows with `candidate_asset_score`, `score_components`, `hard_gate_flags`)
- `candidate_summary` (counts, limits, selected IDs, ordering policy)
- Enforced H2 confirmation context integrity against prepared candidate set:
- `reviewed_candidate_ids` must exist in candidate IDs
- `confirmed_asset_refs` must exist in candidate source refs
- Enforced operator confirmation bounds:
- minimum confirmed assets: `3`
- target confirmed assets: `12` (policy metadata)
- maximum confirmed assets: `15`
- Added/extended tests for scoring, diversity, tie-break ordering, prep guardrails, and confirmation max-bound contract validation.

### Remaining from this PRD
- WP2 Apify multi-source ingestion module for Strategy V2 social/text/comment sources.
- WP4 ADS_CONTEXT propagation + competitor-analysis metric-bearing enrichment.
- WP5 merged VOC corpus path (Step-04 + Apify external corpus).
- WP6 proof-asset candidate suggestion builder for offer pipeline.
- WP7 actor allowlist/config guardrails.
- WP8 expanded end-to-end tests with full DB/Temporal-backed workflow coverage.

---

## 1) Scope and Constraints

This plan covers Strategy V2 steps where missing asset/data inputs currently block quality or completion:
- `v2-02` foundational research context
- `v2-02b` competitor asset confirmation gate (H2)
- `v2-03` scrape + virality scoring
- `v2-04` habitat scoring context quality
- `v2-05` VOC extraction corpus quality
- `v2-08` offer proof input quality

Constraints for implementation:
- Fail fast with explicit errors when required data is missing.
- No silent fallbacks.
- No LLM/model swaps; keep configured models as-is.
- Persist raw ingestion outputs for audit/provenance.

---

## 2) Current-State Findings (Confirmed)

## 2.1 H2 receives too little data to pass reliably

Current workflow payload for H2 is only:
- `{"competitor_urls": stage1.competitor_urls}`

Current decision contract requires:
- `confirmed_asset_refs: list[str]` with minimum length `3`
- `reviewed_candidate_ids: list[str]`

Observed failure in latest validation artifact:
- `Need at least 3 competitor refs ... but only found 1 in stage1 competitor_urls`

Impact:
- Workflow blocks at `v2-02b` unless operator manually invents/finds additional refs outside system context.

## 2.2 Strategy V2 foundational prompts do not receive ads context

`_build_foundational_variables()` currently sets:
- `"ADS_CONTEXT": ""`

Precanon already injects Apify-derived ads context via `AdsIngestionWorkflow` and feeds it into steps 03/04/06/07/08/09.

Impact:
- Strategy V2 foundational research runs with less structured market signal than precanon.

## 2.3 `v2-03` virality quality depends on metrics not guaranteed in current asset sheets

Virality extraction expects per-video numeric fields from `competitor_analysis.asset_observation_sheets`:
- `views`, `followers`, `comments`, `shares`, `likes`, `days_since_posted`, `platform`

Current competitor analysis schema only guarantees limited fields (e.g., `asset_id`, `primary_angle`, `source_ref`).

Impact:
- `video_scored` can be sparse/low-signal when sheets do not contain required metrics.

## 2.4 `v2-05` VOC extraction is anchored to transformed Step-04 corpus only

Agent 2 currently receives:
- `EXISTING_VOC_CORPUS_JSON` built from tagged Step-04 entries

No dedicated Strategy V2 ingestion path currently brings in external comments/reviews from Apify (Instagram/TikTok/YouTube/Reddit/forums) into that corpus.

Impact:
- VOC breadth and recency are constrained by foundational prompt output alone.

## 2.5 `v2-08` requires proof assets but only as free-text operator input

Offer input guard requires non-empty:
- `existing_proof_assets`

This is manually supplied and not currently connected to ingested asset evidence/provenance.

Impact:
- Evidence quality is inconsistent; no deterministic tie-back to scraped assets.

---

## 3) Step-by-Step Data Requirements and Provisioning Plan

| Step | Required Data Contract | Missing Now | Data To Provide | Provision Method |
|---|---|---|---|---|
| `v2-02` foundational | Prompt vars include `ADS_CONTEXT` | Always empty string | Structured cross-brand ad context + top creative patterns | Reuse existing Apify Meta ads ingestion flow (same pattern used by precanon) |
| `v2-02b` H2 competitor assets | `confirmed_asset_refs >= 3` + `reviewed_candidate_ids` | Pending payload only has `competitor_urls` | Candidate asset catalog with stable IDs and refs for review | Build asset catalog from Apify outputs; send as `pending_decision_payload.candidates` |
| `v2-03` scrape + virality | Video observations with platform + numeric metrics | Not guaranteed in `asset_observation_sheets` | Normalized social video rows (TikTok/IG/YT + Meta video creatives where available) | Add Apify social video ingestion and mapping into competitor analysis payload |
| `v2-04` habitat scoring | Habitat observation inputs need source breadth/quality | Habitat strategy is prompt-only without scraped depth | Normalized text habitat datasets (Reddit/forums/reviews) with thread/comment metadata | Add Apify text-habitat ingestion and pass summary stats + sample evidence |
| `v2-05` VOC extraction | Strong `EXISTING_VOC_CORPUS_JSON` for Agent 2 | Currently step-04 transformed corpus only | Merged corpus: step-04 corpus + normalized external comments/reviews | Add Apify comment corpus ingestion and deterministic merge/dedupe before Agent 2 |
| `v2-08` offer pipeline | Non-empty `existing_proof_assets` | Manual notes only | Evidence-backed proof-note candidates with source refs and timestamps | Derive proof-note suggestions from normalized corpus and require operator confirmation |

## 3.1 Context Management and Asset Selection Policy (Explicit)

This policy defines exactly how much data is carried at each layer.

### Layer A: Raw retention (full fidelity)
- Keep 100% of raw Apify dataset items as persisted artifacts.
- Purpose: auditability, replay, and re-ranking without data loss.

### Layer B: Working normalized pool (selection candidates)
- Build a deterministic candidate pool for each step.
- This pool is larger than prompt inputs, and is what HITL and scorers operate on.

### Layer C: Prompt payload subset (LLM context budget)
- Send a strict subset into prompts to stay inside prompt-size caps already used in code (`_dump_prompt_json(..., max_chars=...)`).

## 3.2 Exact Counts, Selection Rules, and Why

### `v2-02b` H2 competitor asset confirmation
- Candidate pool shown to operator: max 40 assets.
- Composition: max 3 assets per competitor, max 8 competitors, max 10 assets per platform.
- Operator confirmation set: target 12 assets, hard minimum 3 (existing contract), hard maximum 15.
- Why: 40 is reviewable in one gate, 12 gives cross-competitor/platform coverage, and <=15 keeps Stage 2A prompt payload compact.

Selection order for H2 candidates:
1. Eligibility filter:
   - Must have resolvable `source_ref`, `competitor_name`, `platform`, and asset kind.
2. Quality rank:
   - Paid/social assets: `(engagement_velocity, days_active_or_recency, performance_score)`.
   - Text/review assets: `(comment_depth, recency, specificity_signals)`.
3. Diversity caps:
   - Enforce per-competitor and per-platform maxima above.

Deterministic scoring requirement for H2 candidate assets:
- The original VOCC design pattern is observation sheets followed by deterministic scoring scripts and then human selection.
- H2 candidate assets must follow the same pattern (no manual/LLM-only ranking).

Proposed `score_candidate_assets.py` (new):
- Input: normalized candidate assets + competitor observation-sheet fields.
- Output: `candidate_asset_score` (0-100), `score_components`, `hard_gate_flags`.

Per-asset score components:
- `durability_signal` (0.30):
  - derived from `running_duration` / `days_active`.
- `distribution_signal` (0.20):
  - derived from `estimated_spend_tier`, presence across placements/platforms.
- `engagement_signal` (0.20):
  - derived from available views/likes/comments/shares/followers (where present).
- `proof_signal` (0.15):
  - derived from `proof_type` (NONE scores lowest).
- `execution_signal` (0.15):
  - derived from asset format usability for downstream angle/copy synthesis.

Hard gates (fail-fast):
- `compliance_risk = RED` -> excluded from default candidate set.
- Missing required canonical fields (`source_ref`, `platform`, `competitor_name`) -> reject row.
- If scored eligible pool after gates is `< 3`, block H2 with remediation.

Selection then becomes:
1. Filter by hard gates.
2. Sort by `candidate_asset_score` descending.
3. Apply diversity caps (competitor/platform).
4. Take top 40 for operator review.

### `v2-03` Scrape + virality
- Working video pool: max 30 videos.
- Caps: max 10 per platform, max 3 per competitor.
- Required fields per selected row: `views`, `followers`, `comments`, `shares`, `likes`, `days_since_posted`, `platform`.
- Why: 30 is enough for stable virality ranking without overweighting long-tail low-signal rows.

### `v2-05` VOC extraction
- Working merged corpus retained in artifacts: max 400 rows.
- Prompt subset to Agent 2: exactly 80 rows.
- Composition: 40 rows from Step-04 transformed corpus + 40 rows from Apify external corpus.
- Why: fixed 80-row balanced corpus preserves source diversity and stays within current prompt JSON char caps.

VOC subset ranking before prompt injection:
1. Relevance to category/angle tokens.
2. Specificity signals (numbers, time markers, concrete outcomes).
3. Engagement and recency.
4. Source diversity balancing (no single source > 25% of subset).

### `v2-08` proof assets
- Proof-candidate list surfaced to operator: max 10 suggestions.
- Each suggestion must include at least 2 independent `source_refs`.
- Exclude RED compliance candidates from suggested proof list.
- Why: low operator burden with stronger evidence quality and compliance hygiene.

## 3.3 What We Pick From Outputs

From each ingestion output, only rows that pass deterministic filters are promoted:
- Required identity fields present (`source_ref`, platform/source type, timestamp where available).
- Non-empty primary text (`quote`, `caption`, or headline/body equivalent).
- No duplicate canonical URL + normalized text hash collisions.
- Compliance-tagged (for downstream filtering and proof safety).

Rows that fail any rule are discarded from working pools and never sent into prompts.

---

## 4) Apify Data Sources to Use

## 4.1 Reuse immediately (already in codebase)

- Meta ads creative ingestion actor:
  - `curious_coder~facebook-ads-library-scraper`
- Meta totals actor:
  - `apify~facebook-ads-scraper`
- Existing flow/components:
  - `AdsIngestionWorkflow`
  - `ingest_ads_for_identities_activity`
  - `build_ads_context_activity`

## 4.2 Add for Strategy V2 social/video + comments

Candidate actors (already documented internally):
- TikTok: `clockworks/free-tiktok-scraper`
- Instagram: `apify/instagram-scraper`
- YouTube: `streamers/youtube-scraper`

Use for:
- video metrics (`views`, `likes`, `comments_count`, `shares`, `date_posted`, `url`)
- comment corpus extraction (top comments + metadata)

## 4.3 Add for text habitats/reviews

Candidate actors:
- Reddit: `trudax/reddit-scraper`
- Forums/web: `apify/web-scraper`
- Discovery: `apify/google-search-scraper`
- Reviews: `emastra/trustpilot-scraper`, `junglee/amazon-reviews-scraper`

Use for:
- habitat depth signals for `v2-04`
- VOC quote corpus enrichment for `v2-05`

---

## 5) Canonical Data Contracts To Introduce

## 5.1 Competitor asset candidate (for H2)

```json
{
  "candidate_id": "ca_meta_001",
  "source_type": "META_AD|LANDING_PAGE|TIKTOK_VIDEO|INSTAGRAM_REEL|YOUTUBE_SHORT|REDDIT_THREAD",
  "source_ref": "https://...",
  "competitor_name": "string",
  "platform": "META|TIKTOK|INSTAGRAM|YOUTUBE|REDDIT|WEB",
  "asset_kind": "VIDEO|IMAGE|TEXT|PAGE",
  "headline_or_caption": "string",
  "metrics": {
    "views": 0,
    "likes": 0,
    "comments": 0,
    "shares": 0,
    "followers": 0,
    "date_posted": "2026-02-01"
  },
  "raw_source_artifact_id": "artifact-id"
}
```

Usage:
- `pending_decision_payload` at `v2-02b` should include these candidates.
- Operator confirms `confirmed_asset_refs` from `source_ref` values.

## 5.2 Social video observation row (for `v2-03`)

```json
{
  "video_id": "sv_001",
  "platform": "tiktok",
  "views": 100000,
  "followers": 12000,
  "comments": 800,
  "shares": 120,
  "likes": 6400,
  "days_since_posted": 14,
  "description": "...",
  "author": "@creator",
  "source_ref": "https://..."
}
```

Usage:
- Must map deterministically into `competitor_analysis.asset_observation_sheets` fields consumed by `_extract_video_observations()`.

## 5.3 VOC corpus item (for `v2-05`)

```json
{
  "voc_id": "APIFY_V001",
  "source_type": "apify_comment",
  "source_url": "https://...",
  "platform": "TIKTOK|INSTAGRAM|YOUTUBE|REDDIT|FORUM|REVIEW",
  "author": "string",
  "date": "2026-02-01",
  "quote": "raw text",
  "thread_title": "optional",
  "engagement": {
    "likes": 0,
    "replies": 0
  }
}
```

Usage:
- Merge with Step-04 transformed corpus before Agent 2.
- Keep raw text and provenance; scoring still occurs in existing deterministic scorer.

## 5.4 Proof-note candidate (for `v2-08`)

```json
{
  "proof_id": "proof_001",
  "proof_note": "Customers mention faster recovery after long shifts.",
  "source_refs": ["https://...", "https://..."],
  "evidence_count": 2,
  "compliance_flag": "GREEN|YELLOW|RED"
}
```

Usage:
- Present as suggestions; operator must still submit final `existing_proof_assets`.

---

## 6) Runtime Integration Design

## 6.1 New pre-H2 ingestion phase

Add a dedicated Strategy V2 ingestion stage between `v2-01` and `v2-02a` that:
1. Reuses existing Meta ads ingestion for ad context.
2. Runs selected Apify social/text actors.
3. Produces a persisted `asset_catalog` + `voc_corpus_raw` artifact.

Outputs passed forward:
- `ads_context_json` -> foundational prompt vars (`ADS_CONTEXT`)
- `competitor_asset_candidates` -> `pending_decision_payload` at H2
- `normalized_voc_corpus` -> Agent 2 runtime input

## 6.2 H2 payload upgrade

Current H2 payload:
- `{"competitor_urls": [...]}`

Target H2 payload:
- `{"competitor_urls": [...], "candidates": [...], "candidate_summary": {...}}`

Decision behavior remains contract-compatible:
- operator returns `confirmed_asset_refs` and `reviewed_candidate_ids`

## 6.3 Competitor analysis enrichment

Update competitor analysis generation inputs to include structured asset metadata, not only raw refs. Require generated `asset_observation_sheets` to carry platform/metric fields needed by `v2-03`.

## 6.4 VOC corpus merge before Agent 2

Build deterministic merger:
- input A: transformed Step-04 corpus
- input B: normalized Apify corpus
- output: deduped merged corpus with stable `voc_id`s and provenance tags

Pass merged corpus as `EXISTING_VOC_CORPUS_JSON` to Agent 2.

## 6.5 Proof input generation for `v2-08`

Add a summary builder that extracts candidate proof statements from merged corpus and competitor assets. Operator still confirms final `existing_proof_assets` input; missing final input remains hard-fail.

---

## 7) Implementation Work Packages

## WP1 — Asset/Data Contracts

Files:
- `mos/backend/app/strategy_v2/contracts.py` (or new `strategy_v2/asset_contracts.py`)

Changes:
- Add typed models for:
  - competitor asset candidate
  - social video observation
  - external VOC corpus item
  - proof-note candidate

Acceptance:
- Invalid ingestion payloads fail schema validation with explicit remediation messages.

## WP2 — Strategy V2 Apify ingestion module

Files:
- New module under `mos/backend/app/strategy_v2/` or `mos/backend/app/temporal/activities/`
- Reuse `mos/backend/app/ads/apify_client.py`

Changes:
- Implement actor-run + poll + dataset-fetch wrappers for social/text ingestion.
- Persist raw results as artifacts for audit.

Acceptance:
- Each run returns normalized records + raw artifact IDs.
- Missing token/actor failures are explicit and terminal.

## WP3 — Workflow orchestration changes

Files:
- `mos/backend/app/temporal/workflows/strategy_v2.py`

Changes:
- Insert ingestion phase before H2.
- Pass `ADS_CONTEXT` and candidate assets forward.
- Enrich `pending_decision_payload` for `strategy_v2_confirm_competitor_assets`.

Acceptance:
- H2 UI payload includes actionable candidate assets and reviewed candidate IDs map cleanly.

## WP4 — Foundational and competitor-analysis input wiring

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Changes:
- Replace `ADS_CONTEXT: ""` with ingested ads context.
- Expand competitor analysis generator input to include structured candidate metadata.
- Enforce metric field presence for social/video rows used by `v2-03` scoring.

Acceptance:
- `v2-03` receives non-empty metric-bearing video observation rows when social inputs exist.

## WP5 — VOC corpus enrichment path

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `mos/backend/app/strategy_v2/translation.py` (if needed for merge helpers)

Changes:
- Add deterministic merge/dedupe of Step-04 corpus + Apify corpus.
- Feed merged corpus to Agent 2 runtime input.

Acceptance:
- `v2-05` payload includes provenance-tagged mixed corpus and higher source diversity.

## WP6 — Proof-asset suggestion builder for Offer

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- optional API/state payload surfacing in `mos/backend/app/routers/workflows.py`

Changes:
- Build `proof_asset_candidates` summary from merged corpus and competitor evidence.
- Surface summary in pending payload before `v2-08` consumption.

Acceptance:
- Operators can select/confirm proof notes with source refs.

## WP7 — Apify configuration and safety controls

Files:
- env config docs / settings module

Changes:
- Add explicit actor ID env vars per platform.
- Add max-results, max-runtime, and cost guardrails.
- Add strict allowlist of actors.

Acceptance:
- Runs are reproducible and constrained by config; unsupported actor IDs fail immediately.

## WP8 — Tests and validation

Files:
- Strategy V2 workflow/activity tests
- Ads/ingestion unit tests for new normalizers

Changes:
- Add tests for:
  - H2 candidate payload completeness
  - fail-fast on <3 confirmable asset refs
  - merged VOC corpus non-empty and deduped
  - `ADS_CONTEXT` propagation into foundational vars
  - proof candidate generation and operator confirmation path

Acceptance:
- New tests pass and demonstrate no silent fallback behavior.

## WP9 — Deterministic candidate asset scorer

Files:
- New scorer module under `mos/backend/app/strategy_v2/` (or `temporal/activities` helper)
- Tests under `mos/backend/tests/`

Changes:
- Implement `score_candidate_assets.py` with component weights + hard gates.
- Persist component breakdown in H2 payload for operator auditability.

Acceptance:
- H2 candidate ordering is reproducible and script-driven.
- Candidate score output includes component-level explanations and gate flags.

---

## 8) Data Quality Gates (Fail-Fast)

Enforce explicit gates to avoid silent degradation:

1. H2 gate:
- At least 3 candidate assets must be present and reviewable.
- If fewer than 3, block and return remediation.

2. Virality gate (`v2-03` input quality):
- Require at least 1 social platform with metric-bearing rows.
- If zero rows with required numeric fields, block scoring step with remediation.

3. VOC gate (`v2-05` input quality):
- Require merged corpus non-empty with source provenance.
- If merge produces zero usable rows, fail before Agent 2.

4. Offer proof gate (`v2-08`):
- `existing_proof_assets` remains mandatory.
- If absent, fail with explicit instruction.

---

## 9) File-Level Edit Map

| File | Planned Change |
|---|---|
| `mos/backend/app/temporal/workflows/strategy_v2.py` | Add ingestion phase, propagate `ADS_CONTEXT`, enrich H2 pending payload |
| `mos/backend/app/temporal/activities/strategy_v2_activities.py` | Wire ingestion outputs, enrich competitor analysis inputs, add corpus merge and proof-candidate builder |
| `mos/backend/app/strategy_v2/score_candidate_assets.py` (new) | Deterministic scoring + hard gates for H2 candidate assets |
| `mos/backend/app/strategy_v2/contracts.py` (or new asset contracts file) | Add typed models for candidate assets/video rows/corpus rows/proof suggestions |
| `mos/backend/app/ads/apify_client.py` | Reuse for new actor calls (no model/provider change) |
| `mos/backend/app/ads/ingestors/registry.py` and/or new Strategy V2 ingestor registry | Register additional ingestion pathways for social/text sources |
| `mos/backend/app/routers/workflows.py` | Surface enriched pending decision payload data for H2 and optional proof suggestions |
| tests under `mos/backend/tests/` | Add coverage for new gating, payloads, and fail-fast behaviors |

---

## 10) Rollout Sequence

1. Implement WP1-WP3 first to unblock H2 with candidate assets.
2. Implement WP4-WP5 to improve `v2-03` and `v2-05` data quality.
3. Implement WP6 for `v2-08` proof-note assistance.
4. Enable additional actors incrementally by platform (TikTok, Instagram, YouTube, Reddit/forums).
5. Monitor run metrics (asset counts, corpus size, step failure reasons, Apify cost/runtime).

---

## 11) Definition of Done

1. `v2-02b` consistently receives 3+ reviewable candidate assets from system-provided data.
2. Strategy V2 foundational research receives non-empty `ADS_CONTEXT` derived from ingestion.
3. `v2-03` virality scoring uses metric-bearing social video rows, not sparse placeholders.
4. `v2-05` VOC extraction uses merged, provenance-tagged corpus that includes external comments.
5. `v2-08` proof assets are evidence-backed and operator-confirmed.
6. Missing required data fails with explicit remediation; no silent fallback behavior.
