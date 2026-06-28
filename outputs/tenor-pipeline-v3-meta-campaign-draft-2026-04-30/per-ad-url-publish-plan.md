# Tenor Per-Ad URL Publish Plan

Decision: use the campaign delivery URL pair only as the external-delivery validator/default. Use each Meta creative spec's `destination_url` as the source of truth for the actual ad destination.

## Why

The campaign delivery config supports only:

- `preSalesUrl`
- `salesUrl`

That is enough for the current external-delivery contract, but not enough for this campaign's 7 launch destinations:

- 3 advertorial URLs
- 3 listicle URLs
- 1 sales/PDP URL

## Required Publish Sequence

1. Set campaign delivery to `external_urls` with one representative listicle as `preSalesUrl` and the sales page as `salesUrl`.
   - Presales/listicle/advertorial pages only need to be public, fetchable, and not under construction.
   - The sales page is the only URL that must expose privacy and contact/support markers.
2. Generate campaign-owned assets for the 30 ads.
3. Run Prepare Meta review to create the default campaign bucket ad set specs and base Meta creative specs.
4. Reconcile every Meta creative spec against `external-ad-routing.json` using `node tenor_campaign_runner.mjs reconcile-creative-urls`:
   - identify the ad by asset brief/ad metadata
   - set `creative_spec.destination_url` to that ad's `finalUrl`
   - preserve primary text, headline, CTA, page ID, and generated asset linkage
5. Validate the publish plan with `bucketDestinationUrls: []`.
6. Publish paused to Meta.

## Guardrails

- Do not use `bucketDestinationUrls` for this campaign. Bucket-level URLs would override creative-level URLs and collapse multiple destinations.
- Do not run Prepare Meta review after the per-ad URL reconciliation unless the reconciliation step is run again afterward.
- Do not publish if any included creative spec is missing `destination_url` or resolves to the wrong final URL.

## Current Routing Source

Use:

- `external-ad-routing.json`
- `external-ad-routing.csv`

Each row includes:

- `adId`
- `destinationKey`
- `finalUrl`
