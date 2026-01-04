# PRD: Structured Ad Teardowns (Assertions, Evidence, Dedupe, Taxonomy Validation)

## 1) Summary

We need a first-class way to persist forensic structural teardowns so they are:

- Queryable across thousands of ads (segments, hooks, claims, proof, CTA, signals)
- Auditable (assertions are backed by evidence items)
- Deduplicated (one teardown can apply to many identical creatives)
- Taxonomy-controlled (keys validated in application code now; later migrated to tables)

This must integrate cleanly with the ingestion model: brands -> ads -> ad_asset_links -> media_assets.

## 2) Goals / Success Criteria

- Store a teardown as both raw canonical JSON (full fidelity) and extracted relational rows (fast search and analytics).
- Support assertions that link to evidence items (transcript segment, storyboard scene, claim, signal, etc.).
- Implement creative deduplication so identical creatives share the same teardown object.
- Constrain free-text taxonomies via application validation while storing stable keys for later taxonomy tables.

Queries to support:

- Show ads with hook_type = curiosity_gap and a numeric claim "% reduced risk."
- What proof types appear before the first CTA in top-performing competitor ads?
- Which assertions about target audience are not backed by evidence?
- Reuse an existing teardown when a new ad is ingested with the same creative fingerprint.

## 3) Non-Goals (v1)

- Automated external claim verification.
- Full ontology/taxonomy tables (app validation only for now).
- Full capture versioning of ad library payloads (optional later).

## 4) Core Design Decisions

### 4.1 Attachment to deduped creative (ad copy + media)

- ads are instances that can duplicate across platforms, regions, campaigns, and re-uploads.
- Introduce ad_creatives: a deduped ad-rendering unit computed from media + ad copy.
- Teardowns attach to ad_creatives. Ads attach to ad_creatives.
- Same media + same normalized copy -> same creative. Same media + different normalized copy -> different creative.

### 4.2 Evidence linking with referential integrity

- ad_teardown_evidence_items is a base table with a UUID PK.
- Each evidence subtype table stores payload keyed by evidence_item_id.
- assertion_evidence links to ad_teardown_evidence_items.id via FK.

## 5) Data Model Changes (New Tables)

Conventions: UUID PKs, timestamptz, server_default=now(), JSON defaults {} where relevant.

### 5.1 Dedup layer: ad_creatives + membership

Table: ad_creatives

- id (uuid, PK)
- org_id (uuid, FK -> orgs.id, on delete cascade)
- brand_id (uuid, FK -> brands.id, on delete cascade)
- channel (enum ad_channel, NOT NULL)
- fingerprint_algo (text, NOT NULL) e.g. adcopy+media-sha256-set-v1
- creative_fingerprint (text, NOT NULL)
- primary_media_asset_id (uuid, FK -> media_assets.id, on delete set null)
- media_fingerprint (text, nullable) optional for debugging
- copy_fingerprint (text, nullable) optional for debugging
- metadata (jsonb, NOT NULL default {})
- created_at, updated_at

Constraints and indexes:

- Unique: (org_id, brand_id, channel, fingerprint_algo, creative_fingerprint)
- Index: (org_id, brand_id)
- Index: (org_id, brand_id, media_fingerprint) optional
- Index: (org_id, brand_id, copy_fingerprint) optional
- Index: (org_id, creative_fingerprint) for fast lookup

Table: ad_creative_memberships

- id (uuid, PK)
- creative_id (uuid, FK -> ad_creatives.id, on delete cascade)
- ad_id (uuid, FK -> ads.id, on delete cascade)
- created_at

Constraints:

- Unique: (ad_id) (one ad belongs to one creative)
- Unique: (creative_id, ad_id) (redundant but safe)

### 5.2 Teardown header + raw payload: ad_teardowns

Table: ad_teardowns

- id (uuid, PK)
- org_id (uuid, FK -> orgs.id, on delete cascade)
- creative_id (uuid, FK -> ad_creatives.id, on delete cascade)
- client_id (uuid, FK -> clients.id, on delete set null)
- campaign_id (uuid, FK -> campaigns.id, on delete set null)
- research_run_id (uuid, FK -> research_runs.id, on delete set null)
- created_by_user_id (uuid, FK -> users.id, on delete set null)
- schema_version (int, NOT NULL default 1)
- captured_at (timestamptz, nullable)
- funnel_stage (text, nullable) validated key in app code
- one_liner (text, nullable)
- algorithmic_thesis (text, nullable)
- hook_score (int, nullable) 0-10
- raw_payload (jsonb, NOT NULL default {})
- is_canonical (bool, NOT NULL default true)
- created_at, updated_at

Constraints and indexes:

- Index: (creative_id)
- Index: (org_id, client_id)
- GIN index: (raw_payload)
- Optional: partial unique (org_id, creative_id) where is_canonical = true

## 6) Evidence System

### 6.1 Base evidence table

Table: ad_teardown_evidence_items

- id (uuid, PK)
- teardown_id (uuid, FK -> ad_teardowns.id, on delete cascade)
- evidence_type (text, NOT NULL) validated key
- start_ms (int, nullable)
- end_ms (int, nullable)
- created_at

Indexes:

- (teardown_id, evidence_type)
- (teardown_id, start_ms)

### 6.2 Evidence subtype tables

Each uses evidence_item_id as PK + FK -> ad_teardown_evidence_items.id.

Transcript segments (ad_teardown_transcript_segments):

- evidence_item_id (uuid, PK/FK)
- speaker_role (text, nullable) validated key
- spoken_text (text, nullable)
- onscreen_text (text, nullable)
- audio_notes (text, nullable)

Storyboard scenes (ad_teardown_storyboard_scenes):

- evidence_item_id (uuid, PK/FK)
- scene_no (int, NOT NULL)
- visual_description (text)
- action_blocking (text)
- narrative_job (text)
- onscreen_text (text)
- Uniqueness of (teardown_id, scene_no) enforced in app for v1.

Numeric claims (ad_teardown_numeric_claims):

- evidence_item_id (uuid, PK/FK)
- value_numeric (numeric, nullable)
- unit (text, nullable) e.g. %, mg, tons
- claim_text (text, NOT NULL)
- claim_topic (text, nullable) validated key
- verification_status (text, NOT NULL default unverified) validated key
- source_url (text, nullable)

Targeting signals (ad_teardown_targeting_signals):

- evidence_item_id (uuid, PK/FK)
- modality (text, NOT NULL) visual|text|audio
- category (text, NOT NULL) validated key
- value (text, NOT NULL)
- is_observation (bool, NOT NULL default true)
- confidence (numeric, nullable)

Narrative beats (ad_teardown_narrative_beats):

- evidence_item_id (uuid, PK/FK)
- beat_key (text, NOT NULL) validated key
- description (text, NOT NULL)

Proof usage (ad_teardown_proof_usages):

- evidence_item_id (uuid, PK/FK)
- proof_type (text, NOT NULL) validated key
- description (text, nullable)

CTA moments (ad_teardown_ctas):

- evidence_item_id (uuid, PK/FK)
- cta_kind (text, NOT NULL) validated key
- cta_text (text, NOT NULL)
- offer_stack_present (bool, nullable)
- risk_reversal_present (bool, nullable)
- notes (text, nullable)

Production requirements (ad_teardown_production_requirements):

- evidence_item_id (uuid, PK/FK)
- req_type (text, NOT NULL) validated key
- value (text, NOT NULL)

Ad copy blocks (ad_teardown_ad_copy_blocks) optional but recommended:

- evidence_item_id (uuid, PK/FK)
- field (text, NOT NULL) validated key: primary_text|headline|description|cta_label|destination_url
- text (text, nullable) canonicalized value or URL
- raw_text (text, nullable)
- language (text, nullable)

## 7) Assertions and Evidence Linking

Assertions (ad_teardown_assertions):

- id (uuid, PK)
- teardown_id (uuid, FK -> ad_teardowns.id, on delete cascade)
- assertion_type (text, NOT NULL) validated key
- assertion_text (text, NOT NULL)
- confidence (numeric, nullable)
- created_by_user_id (uuid, FK -> users.id, on delete set null)
- created_at

Indexes:

- (teardown_id, assertion_type)

Assertion evidence links (ad_teardown_assertion_evidence):

- id (uuid, PK)
- assertion_id (uuid, FK -> ad_teardown_assertions.id, on delete cascade)
- evidence_item_id (uuid, FK -> ad_teardown_evidence_items.id, on delete cascade)
- created_at

Constraints:

- Unique (assertion_id, evidence_item_id)

## 8) Taxonomies (validated in app code)

Store taxonomy values as text keys and validate in app code at write time.

Recommended controlled sets (initial):

- evidence_type: transcript_segment, storyboard_scene, numeric_claim, targeting_signal, narrative_beat, proof_usage, cta, production_requirement, ad_copy_block
- speaker_role: narrator, spokesperson, testimonial, actor, unknown
- signal_modality: visual, text, audio
- signal_category: setting, prop, character, action, keyword, pain_point, outcome, mechanism, timeframe, number, authority_cue, social_proof_cue
- beat_key: hook, lead, problem, agitate, mechanism, solution, proof, offer, cta
- proof_type: ugc_text, ugc_video, authority, stats, science_signaling, demo, guarantee, before_after
- cta_kind: mid_roll_soft, mid_roll_direct, end_roll_direct, overlay, button_only
- verification_status: unverified, verified, disputed
- req_type: location, prop, talent, broll_query, graphic_asset
- ad_copy field keys: primary_text, headline, description, cta_label, destination_url

## 9) Deduplication Strategy (ad copy + media)

Fingerprint algorithm: adcopy+media-sha256-set-v1.

Inputs:

- Media tokens: from ad_asset_links -> media_assets using stable_id preference: sha256, else stored_url, else source_url. Token: "{role}:{asset_type}:{stable_id}".
- Copy tokens: canonicalize ad copy fields (primary_text, headline, description, cta_type/text, destination_url). Rules: Unicode normalize NFKC, trim, collapse whitespace, lowercase; URLs lowercase host, drop fragment, remove tracking params (utm_*, fbclid, gclid, ttclid), normalize trailing slash. Represent as hashed tokens:
  - copy:primary_text:{sha256(norm_primary_text)}
  - copy:headline:{sha256(norm_headline)}
  - copy:description:{sha256(norm_description)}
  - cta:{cta_type_or_label_normalized}
  - dest:{sha256(canonical_url)}
- If all copy fields are empty, include a single copy:none token for determinism.

Final fingerprint:

1) Union media tokens and copy tokens.
2) Sort lexicographically.
3) Join with "|".
4) SHA256 the string.

Store:

- fingerprint_algo = "adcopy+media-sha256-set-v1"
- creative_fingerprint = <sha256>
- media_fingerprint and copy_fingerprint may store component hashes if columns present.

Primary media selection: prefer first VIDEO, else largest image, else null.

Timing: compute after ad row exists with copy fields and media assets are linked (during ingest). On updates, recompute; if fingerprint changes, upsert/get new ad_creatives and update ad_creative_memberships for that ad_id.

## 10) Service/API Requirements

Create or update teardown (idempotent replace-extracted pattern):

- Inputs: creative_id (or ad_id resolving creative), raw_payload, optional funnel_stage, hook_score, one_liner, algorithmic_thesis, captured_at, assertions payload + evidence mapping.
- Behavior: upsert ad_teardowns, replace extracted evidence (delete existing evidence items cascaded, insert new evidence and subtype rows), insert assertions then assertion_evidence links.

Fetch teardown:

- By ad_id -> resolve creative_id -> canonical teardown.
- By creative_id -> canonical teardown.
- By teardown_id.

Search/analytics (v1 minimal):

- List teardowns for org/client/campaign.
- Filter by taxonomy keys (hook_type, proof_type, beat_key, signal_category).
- Filter by numeric claims (unit, topic).
- Later: full-text search across transcript via tsvector.

## 11) Migration / Backfill Plan

- Phase 1: add new tables and indexes; backfill creatives for existing ads by computing fingerprints and creating ad_creatives + memberships.
- Phase 2: teardown persistence (save raw_payload, extract evidence tables; assertions + evidence linking).
- Phase 3: UX and ops hardening (surface existing teardown match, admin tooling for adding taxonomy keys in code).

## 12) Acceptance Criteria

- Creating a teardown stores raw_payload and extracted evidence rows.
- Assertions can be created and linked to evidence items with real FK integrity.
- Two ads with identical media set and identical normalized copy resolve to the same ad_creatives record.
- Two ads with identical media set but different normalized copy resolve to different ad_creatives records.
- Canonical teardown uniqueness is enforceable per (org_id, creative_id).
- Taxonomy keys are validated in app code and stored as stable strings.
- Deleting a teardown cascades to evidence, assertions, and links cleanly.
