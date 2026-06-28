# PRD: Funnel Congruence Audit Service

## Decision

Build a record-backed congruence audit in MOS that compares the actual ad package against the actual funnel path before Meta publish.

The service should not start by capturing pages. Most inputs already exist in MOS:

- generated ad assets live in `assets`
- generated ad-copy inputs and rendered-asset provenance live in `assets.ai_metadata`
- prepared Meta launch copy and destination URLs live in `meta_creative_specs`
- campaign destination contracts live in `campaign_delivery_configs`
- internal funnel/page content lives in `funnel_pages`, `funnel_page_versions`, and `funnel_publications`
- site runtime content lives in `sites`, `site_pages`, `site_page_versions`, `site_publications`, and `site_funnels`
- product, variant, offer, and product-image truth lives in `products`, `product_offer_price_points`, `product_offers`, and `assets`
- approved strategy/copy context lives in `artifacts`, especially `campaign_creative_context` and Strategy V2 artifacts

Browser capture is a verification layer, not the primary data source. Use it only when the audit must prove the rendered live state, inspect an external URL outside MOS, or validate JS/runtime behavior that cannot be read from persisted records.

## Problem

We can currently generate creatives, prepare Meta specs, run paid-ads QA, and publish. But we do not have a dedicated check that asks:

- Does the ad image show the same product/label/packaging as the destination page?
- Does the Meta ad copy preserve the same promise, offer, and CTA as the page it sends users to?
- Does a presell or quiz path continue the same story rather than switching product, promise, or mechanism?
- Does checkout contain the product, variant, price, bundle, and quantity the ad and lander imply?
- Did the landing page or product image change after the ad was rendered?

The recent old-label ad vs updated landing-page label issue is a direct stale-asset/congruence problem. It is not primarily a page-capture problem because MOS already stores the generated ad asset, the product references used during rendering, and the page/product assets currently configured.

## Goals

- Detect ad-to-funnel mismatches before Meta publish.
- Prefer deterministic database records and immutable page/version/publication snapshots over ad hoc browser capture.
- Produce concise findings with exact MOS references, not generic LLM commentary.
- Fail fast when required source records are missing. Do not infer, replace, or use fallback inputs silently.
- Reuse the existing Meta review scope logic, campaign delivery mode logic, generated asset metadata, and paid-ads QA UI pattern.
- Support both internal MOS funnels and external URL campaigns.
- Support the current generated-creative flow and later live campaign audits.

## Non-Goals

- Do not replace paid-ads QA or policy checks.
- Do not rewrite ad copy, regenerate assets, or edit pages automatically.
- Do not autonomously browse arbitrary funnel paths in v1.
- Do not complete a real checkout or charge a payment method.
- Do not change the configured LLM or try model alternatives.
- Do not invent product facts, offer facts, replacement creative ideas, or compliance rules.

## Where This Fits

The audit should run after assets and Meta review specs exist, and before paid-ads QA/publish.

Recommended v1 workflow:

1. Creative production generates `assets`.
2. Operator reviews assets.
3. Prepare Meta review creates or updates `meta_creative_specs`.
4. Congruence audit runs against the prepared Meta specs, generated assets, and destination records.
5. Paid-ads QA runs only if the congruence audit passes or the operator explicitly allows non-blocking review mode.
6. Publish remains gated by existing Meta publish validation plus latest passing congruence audit for the selected generation.

This makes the audit evaluate the same package that will actually launch, not just an earlier creative draft.

## Existing System Context

### Campaign And Delivery

Relevant current structures:

- `Campaign` has `client_id`, `product_id`, channels, asset brief types, and `default_swipe_collection_id`.
- `CampaignDeliveryConfig` supports `internal_funnel` and `external_urls`.
- `campaign_destinations.py` already normalizes destination types: `pre-sales`, `sales`, `checkout`, `thank-you`.
- `campaign_delivery.py` validates external URLs before downstream execution.
- `campaigns.py` already resolves external URL review paths and internal funnel review paths for Meta setup.

The congruence audit should reuse this destination resolution instead of adding another routing model.

### Generated Assets

Generated image ads are persisted in `assets`.

Important fields:

- `assets.storage_key`, `content_type`, `width`, `height`
- `assets.content.assetBriefId`
- `assets.content.requirementIndex`
- `assets.content.prompt`
- `assets.ai_metadata.assetBriefId`
- `assets.ai_metadata.requirementIndex`
- `assets.ai_metadata.swipeCompanyId`
- `assets.ai_metadata.swipeSourceUrl`
- `assets.ai_metadata.swipePromptImageSha256`
- `assets.ai_metadata.swipePromptProductImageSha256`
- `assets.ai_metadata.swipeProductReferenceLocalAssetIds`
- `assets.ai_metadata.swipeProductReferenceImageUrlsSelected`
- `assets.ai_metadata.renderedAdImageSha256`
- `assets.ai_metadata.swipeCopyPack`
- `assets.ai_metadata.swipeCopyInputs`
- `assets.ai_metadata.destinationType`
- `assets.ai_metadata.destinationLabel`
- `assets.ai_metadata.resolvedDestinationUrl`
- `assets.ai_metadata.creativeGenerationBatchId`

These fields are enough to compare what the ad was generated from with what the funnel currently uses.

### Prepared Meta Specs

`setup_campaign_meta_review` creates `MetaCreativeSpec` records from generated assets.

Important fields:

- `asset_id`
- `campaign_id`
- `primary_text`
- `headline`
- `description`
- `call_to_action_type`
- `destination_url`
- `metadata_json.assetBriefId`
- `metadata_json.requirement`
- `metadata_json.swipeCopyPack`
- `metadata_json.swipeCopyInputs`
- `metadata_json.destinationType`
- `metadata_json.destinationPage`
- `metadata_json.resolvedDestinationUrl`
- `metadata_json.deliveryMode`
- `metadata_json.campaignDelivery`
- `metadata_json.reviewPaths`

The audit should prefer `MetaCreativeSpec` when available because it represents the prepared launch unit.

### Internal Funnel Runtime

Legacy funnel runtime:

- `funnels`
- `funnel_pages`
- `funnel_page_versions`
- `funnel_publications`
- `funnel_publication_pages`
- `funnel_publication_links`
- `funnel_orders`

The public funnel runtime can serve active publications, or preview saved draft/approved versions for unpublished funnels. The audit must record which source it used and must not silently switch source if the requested source is unavailable.

Site runtime:

- `sites`
- `site_pages`
- `site_page_versions`
- `site_links`
- `site_funnels`
- `site_funnel_steps`
- `site_publications`
- `site_publication_pages`
- `site_publication_funnels`
- `site_publication_funnel_steps`
- `site_publication_product_bindings`

Public site runtime reads active site publications first. If the audit is configured for active-published validation, missing active publication should be a clean error. If the audit is configured for preview validation, it can use the latest saved draft/approved version and label the run as preview.

### Product, Offer, Checkout

Relevant current structures:

- `Product`
- `Product.primary_asset_id`
- `ProductVariant` in `product_offer_price_points`
- `ProductOffer`
- `ProductOfferBonus`
- `SiteProductPageBinding`
- `SiteFunnel.product_id`
- `SiteFunnel.selected_offer_id`
- legacy `Funnel.selected_offer_id`
- Medusa cart endpoints under `sites.py`

For v1, checkout congruence should verify configured offer/product/variant facts and optional cart initialization in preview mode. It should not complete payment.

## Product Requirements

### Audit Inputs

The audit endpoint should accept a launch scope, not raw URLs by default.

Request shape:

```json
{
  "assetBriefIds": ["brief_123"],
  "generationBatchId": "batch_abc",
  "funnelId": "optional-internal-funnel-id",
  "mode": "pre_publish",
  "runtimeSource": "prepared_meta_specs",
  "includeRenderedVerification": false
}
```

Required behavior:

- If `mode=pre_publish`, prepared Meta creative specs must exist for the selected assets.
- If selected asset briefs span multiple internal funnels, error with the same style used by Meta review setup.
- If the campaign uses `external_urls`, the campaign delivery config must be valid.
- If the campaign uses `internal_funnel`, exactly one internal funnel scope is required unless all selected briefs resolve to one funnel.
- If no generated assets exist for a selected brief/generation, return a 409 with missing asset brief ids.

### Audit Modes

| Mode | Purpose | Required Source |
| --- | --- | --- |
| `generated_asset_review` | Check generated assets before Meta specs exist. | `assets` plus asset brief/destination records |
| `pre_publish` | Check the actual prepared Meta package. | `meta_creative_specs` plus linked `assets` |
| `live_campaign` | Later: compare live/published ad state to current funnel. | Meta live creative plus current destination |

V1 should implement `pre_publish`. `generated_asset_review` can share the same service internally if it is cheap, but it should not block the v1 launch gate.

### Funnel Path Resolution

The service should build an explicit ordered `auditPath`.

Internal legacy funnel:

1. Resolve selected `Funnel`.
2. Resolve entry `FunnelPage`.
3. Resolve ordered pages from `FunnelPage.ordering` and `next_page_id`/publication links where available.
4. Resolve each page version from the requested runtime source:
   - `active_publication`: use `funnel.active_publication_id` and `funnel_publication_pages.page_version_id`
   - `preview_saved_version`: use latest draft, else approved, but only when requested
5. Add configured checkout/offer node from `Funnel.selected_offer_id`, product, variants, and checkout metadata.

Site runtime:

1. Resolve `Site` and optional `SiteFunnel`.
2. Resolve ordered `SiteFunnelStep` records.
3. Resolve each `SitePage`.
4. Resolve each page version from the requested runtime source:
   - `active_publication`: use `site.active_site_publication_id` and publication snapshot rows
   - `preview_saved_version`: use latest draft, else approved, but only when requested
5. Add product binding and selected offer nodes.
6. Add Medusa cart/checkout config facts if commerce provider is `medusa`.

External URL delivery:

1. Use `CampaignDeliveryConfig` as the destination contract.
2. Map `pre-sales`, `sales`, `checkout`, and `thank-you` URLs.
3. V1 extracts text via HTTP fetch using the existing destination validation pattern.
4. Browser capture is optional and only enabled by `includeRenderedVerification=true`.

### Why Capture Is Not The Default

The audit needs facts. MOS already has most facts in structured records.

Use records for:

- exact ad asset id and SHA
- exact product image/reference ids used during generation
- exact prepared Meta copy
- exact destination URL used for publish
- exact page version or publication snapshot
- exact Puck data, image slots, CTA fields, links, and product bindings
- exact product/variant/offer configuration

Use browser capture only for:

- external pages where MOS does not own the content
- proving that the runtime renders what stored records imply
- responsive/JS states that are not represented in `puck_data`
- visual evidence screenshots for high-risk mismatches
- later live audits against public production pages

This keeps v1 faster, cheaper, deterministic, and auditable. It also catches stale product-image problems more directly because it can compare stored asset ids and image hashes.

## Extraction Requirements

### Ad Node Extraction

For each prepared `MetaCreativeSpec`, build an `ad_node`.

Required fields:

- `assetId`
- `assetStorageKey`
- `assetSha256`
- `assetCreatedAt`
- `creativeSpecId`
- `primaryText`
- `headline`
- `description`
- `cta`
- `destinationUrl`
- `assetBriefId`
- `requirementIndex`
- `requirement`
- `generationBatchId`
- `sourceSwipe`
- `productReferenceAssetIds`
- `productReferenceSha256`
- `renderedAdSha256`
- `swipeCopyPack`
- `swipeCopyInputs`

LLM image observation should extract:

- visible product name
- visible product package/label description
- label color and distinctive design elements
- quantity/bundle shown
- on-image offer or price text
- on-image promise/claim
- CTA or button text if visible
- notable mismatch candidates

The model must return strict JSON. If the image cannot be loaded, error the run. Do not substitute the remote URL if the stored asset is missing unless that behavior is explicitly requested.

### Page Node Extraction

For MOS-owned Puck pages, extract from `puck_data` before using LLM:

- page title/name/slug/page type
- headings and body copy
- CTA labels and target page ids/links
- product image slots and asset refs
- image `src`, `alt`, `imageSlots`, `imageOverrides`
- product blocks and variant/offer refs
- price text, guarantee text, shipping text, bundle text
- outbound links

Then LLM page observation can normalize:

- product identity
- product/package/label description from referenced page images
- offer mechanics
- promise and problem framing
- proof/trust claims
- CTA expectation
- stage role: presell, sales, quiz, cart, checkout, thank-you

For external URLs, v1 can fetch visible text and image URLs. If the service cannot fetch the URL, return a clean destination fetch error. Do not use a different URL.

### Checkout Node Extraction

For v1, use configured checkout facts rather than completing checkout:

- product id/title
- selected offer id/name
- variant id/title/SKU/price/currency
- bundle quantity
- compare-at price
- guarantee text
- bonuses
- cart/checkout page type

Optional preview cart validation:

- create a Medusa preview cart
- add the expected variant and quantity
- verify returned cart line item, quantity, price, and currency
- initialize a payment session only when the endpoint is configured and the run explicitly requests checkout runtime verification
- never complete payment

If a checkout URL is external, v1 records it as a destination node and fetches only text/metadata unless rendered verification is enabled.

## Comparison Requirements

The congruence engine should compare node observations pairwise and path-wide.

Primary comparisons:

- ad image vs landing page hero/product image
- ad copy vs landing page copy
- ad offer vs landing/sales/checkout offer
- ad CTA vs destination page role
- landing page CTA vs next step
- presell/quiz promise vs sales page/product promise
- sales page product/offer vs checkout/cart product/offer
- generated asset product-reference SHA vs current product/page asset SHA

Important stale-asset checks:

- If the generated ad used `swipePromptProductImageSha256` and the current product primary image or page product image has a different SHA, flag the asset as potentially stale.
- If the ad image LLM observation describes old packaging and the page/product image observation describes different packaging, flag as blocker.
- If the page version/publication was created after the ad asset and product imagery changed, flag as stale-review warning or blocker depending on mismatch evidence.

## Finding Taxonomy

Initial rules:

| Rule ID | Severity | Dimension | Check |
| --- | --- | --- | --- |
| `CONG-INPUT-001` | blocker | input | Selected scope has no generated assets. |
| `CONG-INPUT-002` | blocker | input | Prepared Meta specs are missing for pre-publish mode. |
| `CONG-INPUT-003` | blocker | input | Destination cannot be resolved from asset brief or campaign delivery config. |
| `CONG-INPUT-004` | blocker | input | Requested runtime source is unavailable. |
| `CONG-PRODUCT-001` | blocker | product | Ad and destination show different products. |
| `CONG-PRODUCT-002` | blocker | product_image | Ad shows stale or mismatched product label/packaging. |
| `CONG-PRODUCT-003` | high | product_image | Ad product reference differs from current product/page product asset. |
| `CONG-COPY-001` | high | copy | Ad promise is not continued on the destination. |
| `CONG-COPY-002` | high | copy | Destination changes the problem/audience framing materially. |
| `CONG-OFFER-001` | blocker | offer | Ad offer/discount/bundle conflicts with landing/sales/checkout. |
| `CONG-OFFER-002` | high | offer | Ad implies an offer not visible before checkout. |
| `CONG-CTA-001` | medium | cta | Ad CTA does not match destination page role. |
| `CONG-PATH-001` | high | path | Landing/quiz sends user to an unexpected next stage. |
| `CONG-CHECKOUT-001` | blocker | checkout | Checkout/cart product or variant does not match sales page. |
| `CONG-CHECKOUT-002` | blocker | checkout | Checkout/cart price or quantity conflicts with advertised offer. |
| `CONG-RENDER-001` | high | rendered_state | Rendered verification disagrees with stored page data. |

Status logic:

- `failed`: any blocker finding exists.
- `needs_review`: no blockers, but at least one high finding exists.
- `passed`: no blocker or high findings.

Launch gating should require `passed` unless an explicit operator override is later designed.

## Output Contract

Persist both a queryable run/finding record and a full JSON artifact.

Pydantic-level shape:

```python
class FunnelCongruenceAuditFinding(BaseModel):
    id: str
    ruleId: str
    severity: Literal["blocker", "high", "medium", "low"]
    status: Literal["failed", "needs_review", "passed"]
    dimension: str
    title: str
    message: str
    fromNodeId: str | None = None
    toNodeId: str | None = None
    artifactType: str
    artifactRef: str | None = None
    evidence: dict[str, Any] = {}
    fixOwner: Literal["ad_creative", "ad_copy", "landing_page", "quiz", "sales_page", "checkout", "routing", "product_catalog", "unknown"]


class FunnelCongruenceAuditResult(BaseModel):
    version: Literal["funnel_congruence_audit_v1"]
    status: Literal["passed", "needs_review", "failed"]
    score: int
    orgId: str
    clientId: str
    campaignId: str
    productId: str | None
    mode: str
    runtimeSource: str
    deliveryMode: str
    generationBatchId: str | None
    assetBriefIds: list[str]
    creativeSpecIds: list[str]
    assetIds: list[str]
    pathNodes: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    comparisons: list[dict[str, Any]]
    findings: list[FunnelCongruenceAuditFinding]
    sourceRefs: list[dict[str, str]]
    createdAt: str
```

## Data Model

Add a dedicated run/finding model similar to paid-ads QA.

### New enum value

Add to `ArtifactTypeEnum`:

- `funnel_congruence_audit`

### New table: `funnel_congruence_audit_runs`

Fields:

- `id`
- `org_id`
- `client_id`
- `campaign_id`
- `product_id`
- `platform`, default `meta`
- `mode`
- `runtime_source`
- `delivery_mode`
- `generation_batch_id`
- `funnel_id`, nullable
- `site_id`, nullable
- `site_funnel_id`, nullable
- `ruleset_version`
- `status`
- `score`
- `blocker_count`
- `high_count`
- `medium_count`
- `low_count`
- `asset_brief_ids` array
- `asset_ids` array
- `creative_spec_ids` array
- `audit_artifact_id`, FK to `artifacts.id`
- `report_markdown`
- `metadata` jsonb
- `created_at`
- `completed_at`

Indexes:

- `(org_id, campaign_id)`
- `(org_id, client_id)`
- `(org_id, generation_batch_id)`
- `(org_id, status)`

### New table: `funnel_congruence_audit_findings`

Fields:

- `id`
- `org_id`
- `audit_run_id`
- `rule_id`
- `dimension`
- `severity`
- `status`
- `artifact_type`
- `artifact_ref`
- `from_node_id`
- `to_node_id`
- `title`
- `message`
- `fix_owner`
- `evidence_json`
- `created_at`

Indexes:

- `(audit_run_id)`
- `(org_id, rule_id)`
- `(org_id, severity)`

## Backend Services

Add:

- `mos/backend/app/schemas/funnel_congruence.py`
- `mos/backend/app/services/funnel_congruence.py`
- `mos/backend/app/db/repositories/funnel_congruence.py`
- `mos/backend/app/routers/funnel_congruence.py`

Core service functions:

- `resolve_audit_scope(...)`
- `load_prepared_meta_specs(...)`
- `load_generated_assets(...)`
- `build_audit_path(...)`
- `extract_ad_observations(...)`
- `extract_page_observations(...)`
- `extract_checkout_observations(...)`
- `compare_congruence(...)`
- `persist_congruence_audit(...)`
- `render_congruence_report_markdown(...)`

Strict behavior:

- Missing records produce typed errors.
- Unsupported page/runtime source produces typed errors.
- Invalid LLM JSON produces typed errors.
- The service does not try alternate models.
- The service does not replace missing images, URLs, or product references.

## API

### Run audit

`POST /campaigns/{campaign_id}/congruence-audits/run`

Request:

```json
{
  "assetBriefIds": [],
  "generationBatchId": null,
  "funnelId": null,
  "mode": "pre_publish",
  "runtimeSource": "prepared_meta_specs",
  "pageRuntimeSource": "active_publication",
  "includeRenderedVerification": false
}
```

Response:

```json
{
  "runId": "uuid",
  "status": "failed",
  "score": 62,
  "summary": {
    "blockerCount": 1,
    "highCount": 2,
    "mediumCount": 0,
    "lowCount": 1
  },
  "topFindings": [
    {
      "ruleId": "CONG-PRODUCT-002",
      "severity": "blocker",
      "title": "Ad shows stale product label",
      "message": "The ad image shows the older blue label while the landing page product image shows the updated green label.",
      "fixOwner": "ad_creative"
    }
  ]
}
```

### List runs

`GET /campaigns/{campaign_id}/congruence-audits?generationBatchId=...`

### Get run detail

`GET /congruence-audits/{run_id}`

### Publish gate helper

`GET /campaigns/{campaign_id}/congruence-audits/latest-gate?generationBatchId=...`

Returns whether the selected generation has a latest passing audit covering the selected assets/specs.

## Frontend

Add a new panel in the campaign Meta workspace between Review and QA:

- `MetaCongruencePanel`
- shows selected generation/funnel scope
- run button
- latest audit status
- blocker/high summary
- side-by-side asset/page evidence links
- finding owner labels
- link to full JSON/report

Add the phase to:

- `MetaWorkflowPhase`
- `MetaWorkflowHeader`
- `MetaPublishWorkspace`

Recommended phase order:

1. Generate
2. Review
3. Congruence
4. QA
5. Publish
6. Manage

The QA panel should show a blocker banner if the latest congruence audit is missing or not passing for the selected generation.

## LLM Usage

Use the existing configured LLM clients and configured model ids. Do not change models in this feature without explicit authorization.

LLM tasks:

- image observation for generated ad asset and referenced product/page images
- structured normalization of claims/promises/offer facts from ad and page copy
- comparison judgment only after deterministic source refs are assembled

Do not ask the LLM to navigate, fetch alternate pages, rewrite creative, or invent missing details.

All LLM calls must:

- use strict JSON output schemas
- include source refs in the input
- return confidence and evidence snippets
- fail the audit if required parsed JSON is invalid

## Rendered Verification Policy

Rendered verification is optional in v1.

When enabled:

- use repo-local authenticated MOS validation for MOS preview/editor pages
- use the configured dev/private URL policy for local/VM services
- capture exact page URL, viewport, screenshot asset id/path, and DOM text hash
- compare rendered observation to stored record observation
- report `CONG-RENDER-001` if rendered state disagrees with stored data

Do not scrape public/NAT Hetzner URLs for user-facing dev access. Use `./scripts/resolve-dev-access-url.sh <port>` when a shareable dev URL is needed.

## Implementation Plan

### Phase 1: Record-Backed Audit Contract

- Add schemas.
- Add tables and repository.
- Add artifact type.
- Implement scope resolver using existing Meta review setup helpers.
- Implement asset/spec loaders.
- Implement deterministic Puck/page/product/offer extraction.
- Implement markdown and JSON report persistence.

Exit criteria:

- A campaign with prepared Meta specs can produce an audit run with path nodes, observations, findings, and a report.
- Missing spec/assets/destination produce clean 409 errors.

### Phase 2: Image And Copy Observation

- Add image observation for generated ad assets and product/page image assets.
- Add copy/promise/offer normalization.
- Add stale product-image SHA checks.
- Add product label/packaging mismatch checks.

Exit criteria:

- Old-label ad vs updated page product image is detected as `CONG-PRODUCT-002`.
- Product reference SHA drift is detected as `CONG-PRODUCT-003`.

### Phase 3: Meta Workflow Gate

- Add API endpoints.
- Add `MetaCongruencePanel`.
- Add latest passing audit gate before QA/publish.
- Show top blocker/high findings in the Meta workspace.

Exit criteria:

- Operators can run the audit from the Meta workflow.
- QA/publish surfaces missing or failed congruence audit as a blocker.

### Phase 4: Checkout And Site Funnel Support

- Add site runtime path support.
- Add site funnel step extraction.
- Add product binding and selected-offer extraction.
- Add optional Medusa preview cart verification.

Exit criteria:

- Audit can compare ad -> product detail -> cart/checkout for site runtime campaigns.
- Checkout product/variant/price mismatch is detected without completing payment.

### Phase 5: Rendered Verification

- Add optional MOS authenticated rendered verification.
- Add external URL screenshot/DOM capture only when explicitly requested.
- Store screenshots as evidence assets or report refs.

Exit criteria:

- Rendered verification records exact URL, viewport, screenshot, and text hash.
- Disagreement between stored page data and rendered page state produces a finding.

## Tests

Backend tests:

- `test_funnel_congruence_scope.py`
- `test_funnel_congruence_assets.py`
- `test_funnel_congruence_page_extraction.py`
- `test_funnel_congruence_comparison.py`
- `test_funnel_congruence_api.py`
- `test_meta_publish_congruence_gate.py`

Required cases:

- Missing generated assets returns 409 with `missingAssetBriefIds`.
- Missing prepared Meta specs returns 409 in `pre_publish` mode.
- External delivery requires valid `CampaignDeliveryConfig`.
- Internal delivery requires one selected funnel when selected briefs do not determine scope.
- Ad product reference SHA differs from current product/page asset SHA.
- LLM-observed ad label differs from landing page label.
- Ad offer conflicts with checkout variant/price.
- Stored Puck page extraction finds CTA links and image refs.
- Invalid LLM JSON fails the audit cleanly.
- Latest passing audit gate rejects stale audit when selected asset ids/spec ids changed.

Frontend tests:

- Meta workflow shows Congruence phase.
- Congruence panel renders latest run status and findings.
- QA panel blocks when latest congruence run is missing or failed.
- Review panel can advance to Congruence after Meta review setup.

## Acceptance Criteria

- V1 audits prepared Meta specs, linked generated assets, and resolved destination records without requiring browser capture.
- Every finding includes a MOS source ref and evidence JSON.
- Old product-label creative vs updated destination product image is a blocker.
- Missing inputs fail clearly instead of using substitute records.
- A latest passing audit is required before publish validation treats the selected generation as ready.
- The full report is persisted as both queryable rows and a `funnel_congruence_audit` artifact.

## Open Questions

- Should `needs_review` block publish in all cases, or only blocker findings?
  - Recommended v1: block unless explicitly overridden later.
- Should generated-asset review run automatically immediately after creative production?
  - Recommended v1: not required for launch gate, but useful after pre-publish is stable.
- Which page runtime source should Meta review use by default for unpublished internal funnels?
  - Recommendation: audit the same source the review URL uses, but record it explicitly as preview.
- Do we need a canonical product-packaging version field?
  - Recommendation: add later if SHA/image observation mismatch catches enough v1 issues.
