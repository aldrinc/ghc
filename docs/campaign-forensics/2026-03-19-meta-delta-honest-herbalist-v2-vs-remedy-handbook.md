# Meta Campaign Delta Analysis

Date: 2026-03-19

Compared campaigns:

- `Honest Herbalist V2` (created 2026-03-18 19:25 PDT)
- `[1/30/26] - [Remedy Handbook] - [CBO] - [Broad/Int]` (created 2026-01-30 16:44 PST)

Source:

- Live Meta Graph campaign, ad set, and ad object snapshots pulled on 2026-03-19.

## Executive Summary

`Honest Herbalist V2` is not configured like the January 30, 2026 target campaign.

The biggest structural gap is that `Honest Herbalist V2` is currently a single-ad-set build with an ad-set budget and zero ads, while `[1/30/26] - [Remedy Handbook] - [CBO] - [Broad/Int]` is a true CBO launch with:

- campaign-level budget
- 5 ad sets
- 19 ads live under those ad sets

If the January 30, 2026 campaign is the target template, `Honest Herbalist V2` is still materially under-configured and differs on budgeting, scale, bidding, geography, attribution, placement behavior, and creative population.

## High-Signal Deltas

| Layer | Honest Herbalist V2 | Remedy Handbook target | Delta |
|---|---|---|---|
| Campaign budget model | No campaign `daily_budget` | Campaign `daily_budget = 5000` | New campaign is not set up as target CBO |
| Ad set budgeting | 1 ad set with `daily_budget = 2500` | 5 ad sets with no ad-set budgets | New campaign is effectively ad-set-budgeted, not campaign-budgeted |
| Campaign bid strategy | No campaign bid strategy returned | `LOWEST_COST_WITHOUT_CAP` at campaign | Target is looser scaling logic; new build is not matching it |
| Ad set bid strategy | `LOWEST_COST_WITH_BID_CAP` with `bid_amount = 2500` | No ad-set bid strategy or bid amount returned | New build is materially more constrained |
| Ad set count | 1 | 5 | New build lacks the target campaign's structure depth |
| Ad count | 0 | 19 | New build has no creatives attached yet |
| Attribution | 7-day click only | 7-day click + 1-day view + 1-day engaged-video-view | New build uses narrower attribution |
| Geo footprint | 19 countries | 4 countries: US, CA, GB, AU | New build is far broader geographically |
| Placements | Explicit `facebook feed` + `instagram stream` | No explicit platform/position pins returned | New build is more manually constrained |
| Brand safety filter | No `brand_safety_content_filter_levels` returned | `FACEBOOK_RELAXED` present | New build does not mirror target filtering |
| Audience automation | `advantage_audience = 1` | `advantage_audience = 1` plus age/gender individual setting automation | New build is not identical even where Advantage Audience is enabled |
| Creative layer | No ads, no CTA, no destination URL present | 19 ads, mostly `LEARN_MORE`, destination `https://thehonestherbalist.com/` | New build is missing the full ad layer |

## Detailed Findings

### 1. Budgeting model does not match the target campaign

The January 30, 2026 campaign is configured like a real CBO build:

- campaign daily budget present: `5000`
- ad sets do not carry their own daily budgets

`Honest Herbalist V2` is configured the opposite way:

- no campaign daily budget returned
- the lone ad set carries `daily_budget = 2500`

That is the clearest sign the new campaign is not currently matching the target's campaign-budget optimization structure.

### 2. Structural depth is much smaller

Target campaign:

- 5 ad sets
- 19 ads total
- ad distribution by ad set: `3 / 4 / 4 / 4 / 4`

New campaign:

- 1 ad set
- 0 ads

Even before looking at targeting details, the new campaign is not built out to the same testing or delivery shape.

### 3. Bidding is more restrictive on the new campaign

`Honest Herbalist V2` ad set:

- `bid_strategy = LOWEST_COST_WITH_BID_CAP`
- `bid_amount = 2500`

January 30, 2026 target campaign:

- campaign `bid_strategy = LOWEST_COST_WITHOUT_CAP`
- no ad-set bid cap returned

So the new build is not just smaller. It is also materially more constrained in how Meta can clear auctions.

### 4. Geography is much broader than the target

Target campaign countries:

- `US`, `CA`, `GB`, `AU`

New campaign countries:

- `US`, `IE`, `IT`, `NL`, `NZ`, `NO`, `CA`, `ES`, `SE`, `CH`, `GB`, `FI`, `DK`, `BE`, `AU`, `AT`, `LU`, `FR`, `DE`

This is a major targeting deviation. The new campaign is not a close geographic clone of the target setup.

### 5. Attribution setup differs

`Honest Herbalist V2`:

- 7-day click only

January 30, 2026 target:

- 7-day click
- 1-day view
- 1-day engaged video view

If you are trying to match the prior reporting and optimization behavior, this is another non-trivial mismatch.

### 6. Placement behavior is different

`Honest Herbalist V2` explicitly pins:

- `publisher_platforms = [facebook, instagram]`
- `facebook_positions = [feed]`
- `instagram_positions = [stream]`

The target campaign did not return explicit placement pins in targeting.

Inference:

- the target campaign appears less manually placement-constrained than the new build

### 7. Creative population is missing in the new campaign

The target campaign contains 19 ads. Across those ads:

- 18 use `LEARN_MORE`
- destination URL resolves to `https://thehonestherbalist.com/`
- page id is consistently `875572108982318`
- there are 18 unique titles and 18 unique bodies in the retrieved ad set

`Honest Herbalist V2` currently has no ads attached, so it is not yet comparable at the creative execution layer.

## What To Change If The Goal Is To Match The January 30, 2026 Template

Priority order:

1. Move budgeting to campaign level so the new build is actually CBO-shaped.
2. Expand from 1 ad set to 5 ad sets.
3. Populate ads under those ad sets. Right now the new campaign has zero.
4. Remove the ad-set bid cap if the goal is to mirror `LOWEST_COST_WITHOUT_CAP`.
5. Reduce geo coverage from 19 countries down to the target country set if you want the same footprint.
6. Restore the prior attribution setup if reporting comparability matters.
7. Review placement constraints. The new campaign is more manually pinned than the target.
8. Reapply the prior brand safety and audience automation configuration if exact setup matching is the goal.

## Notes

- The account also contains a similarly named campaign, `Honest Herbalist V2 Launch`, created on 2026-03-18. It shows the same broad structural pattern: 1 ad set and 0 ads.
- This report is configuration-only. It does not compare delivery or performance metrics.
