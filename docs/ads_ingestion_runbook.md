# Ads Ingestion Runbook (Meta Ads Library v1)

Quick SQL helpers (run in Postgres):

- Recent ingest runs: `select id, research_run_id, brand_channel_identity_id, channel, status, items_count, is_partial, error, started_at, finished_at from ad_ingest_runs order by started_at desc limit 50;`
- Failure rate by channel: `select channel, count(*) filter (where status='FAILED')::float / greatest(count(*),1) as failure_rate, count(*) as runs from ad_ingest_runs group by channel order by runs desc;`
- Median ingest time: `select channel, percentile_cont(0.5) within group (order by extract(epoch from (finished_at - started_at))) as median_seconds from ad_ingest_runs where finished_at is not null group by channel;`
- Items count distribution: `select channel, percentile_cont(0.5) within group (order by items_count) as p50, percentile_cont(0.9) within group (order by items_count) as p90 from ad_ingest_runs group by channel;`
- Partial runs: `select * from ad_ingest_runs where is_partial = true order by finished_at desc limit 50;`

Operational notes:
- Apify token is sourced from `APIFY_API_TOKEN`; avoid logging it. Polling waits up to 5 minutes by default.
- Idempotency: ads are unique on `(channel, external_ad_id)`; media assets are deduped by `sha256` or `(channel, source_url)`. Re-running ingestion updates `last_seen_at` and leaves `first_seen_at` intact.
- Run-level context: `research_runs.brand_discovery_payload` stores Step 01 output; `research_runs.ads_context` stores the deterministic JSON for Step 03 consumption.
- Raw payloads live in `ads.raw_json`; keep access restricted and prefer normalized fields for prompts/analytics.
