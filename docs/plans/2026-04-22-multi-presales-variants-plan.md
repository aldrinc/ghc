# Multiple Pre-Sales Variants Plan

## Decision

Build this as a campaign-level pre-sales variant system:

- one campaign
- one shared sales destination
- many pre-sales variants
- each ad assigned to exactly one pre-sales variant
- Meta review and publish resolving the final ad URL from that variant assignment

Do not model this as one campaign-scoped `preSalesUrl` plus manual URL overrides forever. That is useful as a short-term bridge, but it is the wrong durable abstraction for marketing iteration.

## Why This Is Needed

The current `external_urls` model supports only one canonical `preSalesUrl` and one canonical `salesUrl` per campaign.

That means marketing cannot:

- generate multiple pre-sales pages for the same campaign
- send different creative groups to different pre-sales pages
- keep one shared sales page while iterating only the pre-sales headline and page structure
- compare pre-sales variants cleanly inside the same launch model

## Current Constraints

### Delivery model

Today campaign delivery is campaign-scoped and singular:

- `preSalesUrl`
- `salesUrl`
- optional `checkoutUrl`
- optional `thankYouUrl`

Relevant code:

- `mos/backend/app/schemas/campaign_delivery.py`
- `mos/backend/app/services/campaign_delivery.py`
- `mos/backend/app/services/campaign_destinations.py`

### Meta review model

Today Meta review resolves one destination URL per asset from either:

- campaign delivery config for `external_urls`
- one selected funnel for `internal_funnel`

Relevant code:

- `mos/backend/app/routers/campaigns.py`
- `mos/backend/app/services/meta_review.py`

### Funnel model

Funnels and funnel pages already support duplication and separate route slugs. That means page-generation infrastructure already exists for variant creation.

Relevant code:

- `mos/backend/app/routers/funnels.py`
- `mos/backend/app/services/funnels.py`
- `mos/backend/app/db/models.py`

## Product Model

Add a first-class campaign object: `preSalesVariants`.

Recommended fields:

- `id`
- `campaignId`
- `name`
- `slug`
- `status`
- `destinationMode`
- `externalUrl`
- `funnelId`
- `pageId`
- `headlineTheme`
- `validatedAt`
- `metadata`

`destinationMode` should support:

- `external_url`
- `internal_funnel_page`

The sales page remains singular and campaign-scoped.

## Routing Model

Each asset brief and prepared Meta creative should carry:

- `destinationType`
- `preSalesVariantId` when `destinationType = pre-sales`

Resolution rules:

1. `sales` always resolves to the campaign's shared sales page.
2. `pre-sales` must resolve through `preSalesVariantId`.
3. missing `preSalesVariantId` for a pre-sales asset is a blocking validation error.

## Operator Workflow

### Create variants

Marketing can create:

- `Presales A`
- `Presales B`
- `Presales C`

Each variant points to either:

- an external canonical pre-sales URL
- a duplicated mOS funnel page

### Assign creatives

Creatives are assigned to a specific pre-sales variant.

That assignment determines the ad destination URL at review and publish time.

### Publish

One Meta campaign can publish all selected creatives together.

The ad sets stay about buying structure and budget. The destination URL is resolved per ad from its assigned pre-sales variant.

## Implementation Plan

### 1. Data model

Add storage for `preSalesVariants`.

Add `preSalesVariantId` to:

- asset brief metadata
- prepared Meta creative spec metadata
- publish run item metadata

### 2. Destination resolution

Extend campaign destination resolution so:

- `sales` still comes from campaign delivery config
- `pre-sales` resolves from the assigned variant

Validation should surface the fully resolved URL per asset before publish.

### 3. Funnel support

Reuse the existing funnel duplication path for mOS-hosted variants.

When a presales funnel is duplicated for iteration:

- the pre-sales page changes
- the downstream sales destination remains shared

Do not require a duplicated sales page for each pre-sales variant.

### 4. Meta review

Update review setup so it can prepare selected assets that span multiple pre-sales variants without forcing all assets into one funnel identity.

Validation should block when:

- a pre-sales asset has no assigned variant
- the assigned variant is invalid
- the assigned variant URL is not launch-ready

### 5. Meta publish

Keep the existing bucketing logic independent from destination routing.

At publish time:

- the selected asset determines the creative
- the assigned pre-sales variant determines the final click URL
- UTM parameters continue to be applied on top of the resolved destination

### 6. QA and reporting

Update QA to understand variant-scoped destinations.

Update benchmarking and post-publish reporting so results can be grouped by:

- campaign
- ad set
- creative
- pre-sales variant

## Temporary Bridge

Before the full variant system exists, a narrower publish-time override can support limited operator workflows such as:

- duplicate campaign launch with alternate pre-sales URLs
- bucket-specific temporary pre-sales routing

That bridge should remain explicitly temporary and should not replace the first-class variant model.

## Recommended Build Order

1. `preSalesVariants` storage and API
2. destination resolution changes
3. asset brief and creative metadata support
4. Meta review validation updates
5. Meta publish support
6. QA and benchmark updates
7. frontend workflow for creating, assigning, and publishing variants

## Success Criteria

- marketing can create multiple pre-sales variants while keeping one shared sales page
- a single campaign can publish creatives routed to different pre-sales variants
- every ad shows the resolved pre-sales URL before publish
- post-publish reporting can compare creative performance and pre-sales variant performance separately
