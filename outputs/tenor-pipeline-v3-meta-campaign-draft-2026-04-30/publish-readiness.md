# Tenor Meta Publish Readiness

Campaign: `0a9470aa-97be-4cc2-9099-a30ae8d1daf4`

## Configured

- Final URL registry has 7 destinations: 3 advertorials, 3 listicles, 1 sales/PDP.
- Routing package maps all 30 ads from `phase-9-ads/meta-ads.md` to a final URL.
- Manual creative context was reloaded in production with the supplied URL context.
- Creative compliance remains: no product image/object and no mechanism reveal.

## URL Check

- All 7 supplied URLs returned HTTP 200.
- The selected campaign-level delivery pair is listicle C plus the sales page.
- Presales/listicle/advertorial URLs should not require privacy/support markers; the sales page should.
- The production Meta publish validator expects the configured storefront base URL `https://shop.shoptenorco.com`.
- The supplied launch URLs are absolute `https://shoptenorco.com/...` URLs and can remain per-creative destinations once creative specs exist.

## Publish Blockers

Production validation result for this campaign:

- `includedCount`: 0
- `assetBriefArtifactCount`: 0
- `assetCount`: 0
- `creativeSpecCount`: 0
- `adsetSpecCount`: 0
- `ok`: false

Blockers returned by production:

- No campaign assets were found for this publish generation.
- Campaign CBO launch requires bucket indices 1-5; those bucket specs are created by Prepare Meta review after generated assets exist.

## Not Published

No Meta publish run was created and no Meta campaign/ad set/ad objects were created.

Reason: the deployed production flow still has two blockers:

- External delivery validation still requires privacy/support markers on presales and only scans enough of the sales page to miss its footer privacy marker.
- The new campaign still has no campaign-owned external asset briefs or generated assets, so Prepare Meta review cannot create creative specs or bucket specs yet.

Per-ad URLs should be handled after Prepare Meta review by reconciling each creative spec from `external-ad-routing.json`; the campaign-level pair is only the validator/default.
