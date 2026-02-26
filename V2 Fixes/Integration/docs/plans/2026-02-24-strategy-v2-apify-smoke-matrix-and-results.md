# Strategy V2 Apify Smoke Matrix and Results (2026-02-24)

## Scope
Validate production-equivalent Strategy V2 asset-data spokes at low volume:
- Ads context (Meta)
- Social video context (TikTok/Instagram/YouTube)
- External VOC + proof candidates (via Web scraper + social/meta text extraction)

All smoke runs use tiny limits for fast iteration while preserving production spoke coverage.

## Low-Volume Smoke Configuration
- `STRATEGY_V2_APIFY_ENABLED=true`
- `STRATEGY_V2_APIFY_MAX_ITEMS_PER_DATASET=1`
- `STRATEGY_V2_APIFY_MAX_ACTOR_RUNS=6`
- `STRATEGY_V2_APIFY_MAX_WAIT_SECONDS=120` (YouTube required 300 in practice)

Actor IDs:
- Meta: `curious_coder~facebook-ads-library-scraper`
- TikTok: `clockworks/tiktok-scraper`
- Instagram: `apify/instagram-scraper`
- YouTube: `streamers/youtube-scraper`
- Reddit: `practicaltools/apify-reddit-api`
- Web: `apify/web-scraper`

## Smoke Spoke Matrix
Each case includes ads + video + external VOC inputs, just with minimal volume.

1. `meta`
- Source refs: Meta page + TikTok profile + landing page URL
- Expected primary spoke: Meta ads actor

2. `tiktok`
- Source refs: Meta page + TikTok profile + landing page URL
- Expected primary spoke: TikTok actor

3. `instagram`
- Source refs: Meta page + Instagram profile + landing page URL
- Expected primary spoke: Instagram actor

4. `youtube`
- Source refs: Meta page + YouTube channel + landing page URL
- Expected primary spoke: YouTube actor

5. `web`
- Source refs: Meta page + TikTok profile + landing page URL
- Expected primary spoke: Web actor

6. `reddit`
- Source refs: Meta page + TikTok profile + Reddit thread + landing page URL
- Expected primary spoke: Reddit actor

## Validation Checks Per Case
1. Expected actor run is present.
2. `ads_context` exists.
3. Video context exists (social observations or video-platform candidates).
4. External VOC corpus exists.
5. Proof candidates exist.
6. Workflow context contract shape is valid.

## Commands Used
Run from `mos/backend`.

```bash
python scripts/run_strategy_v2_apify_smoke.py --cases meta --max-items 1 --max-wait-seconds 120 --max-actor-runs 6 --output artifact-downloads/strategy_v2_apify_smoke_report_meta.json
python scripts/run_strategy_v2_apify_smoke.py --cases tiktok --max-items 1 --max-wait-seconds 120 --max-actor-runs 6 --output artifact-downloads/strategy_v2_apify_smoke_report_tiktok.json
python scripts/run_strategy_v2_apify_smoke.py --cases instagram --max-items 1 --max-wait-seconds 120 --max-actor-runs 6 --output artifact-downloads/strategy_v2_apify_smoke_report_instagram.json
python scripts/run_strategy_v2_apify_smoke.py --cases youtube --max-items 1 --max-wait-seconds 300 --max-actor-runs 6 --output artifact-downloads/strategy_v2_apify_smoke_report_youtube.json
python scripts/run_strategy_v2_apify_smoke.py --cases web --max-items 1 --max-wait-seconds 120 --max-actor-runs 6 --output artifact-downloads/strategy_v2_apify_smoke_report_web.json
python scripts/run_strategy_v2_apify_smoke.py --cases reddit --max-items 1 --max-wait-seconds 120 --max-actor-runs 6 --output artifact-downloads/strategy_v2_apify_smoke_report_reddit.json
```

## Results
- `meta`: passed
- `tiktok`: passed
- `instagram`: passed
- `youtube`: passed (with `--max-wait-seconds 300`)
- `web`: passed
- `reddit`: passed

Legacy reddit actor note:
- `trudax/reddit-scraper` currently returns `403 actor-is-not-rented` for this token.
- `practicaltools/apify-reddit-api` is now validated and compatible with our `startUrls` smoke input.

## Output Artifacts
- `mos/backend/artifact-downloads/strategy_v2_apify_smoke_report_meta.json`
- `mos/backend/artifact-downloads/strategy_v2_apify_smoke_report_tiktok.json`
- `mos/backend/artifact-downloads/strategy_v2_apify_smoke_report_instagram.json`
- `mos/backend/artifact-downloads/strategy_v2_apify_smoke_report_youtube.json`
- `mos/backend/artifact-downloads/strategy_v2_apify_smoke_report_web.json`
- `mos/backend/artifact-downloads/strategy_v2_apify_smoke_report_reddit.json`
