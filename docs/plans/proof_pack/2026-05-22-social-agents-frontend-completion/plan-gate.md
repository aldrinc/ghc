# Plan Gate: Social Agents Frontend Completion

## Goal

Make the Connected Social Agents and TikTok Carousel Agent backend usable from MOS while keeping Postiz as the posting system of record.

## Problem

The backend primitives existed, but operators had no MOS surface to create growth programs, draft TikTok carousel variants, approve variants, or create Postiz handoff proposals. Without a page, the implementation was technically present but not usable.

## Diagnosis

Root cause: the first implementation focused on storage and API contracts. The missing machine was an approval-gated operator surface that connects those APIs to the existing Postiz channel/profile readiness state.

## Current Machine

MOS had Postiz settings, connected social API primitives, and growth-program API primitives, but no execution page tying them together. Operators would need direct API calls to use the workflow.

## Designed Machine

MOS now has a Social Agents execution page with:

- Postiz readiness visibility.
- TikTok carousel growth-program setup.
- Conversion source setup.
- Experiment and six-slide variant drafting.
- Variant approval.
- Postiz handoff proposal creation.
- Connected social asset and action proposal review.

Postiz still owns compose, schedule, publish, and post lifecycle state.

## Worst-Day Test

- No workspace selected: page shows an empty state.
- No Postiz channels: page warns without publishing.
- Variant not approved: Postiz handoff stays disabled.
- Missing conversion source: growth loop can still be set up, but conversion data stays explicit.
- Action proposal pending: operator can approve the proposal; execution remains outside this page.

## Metrics

Leading:

- Growth programs created.
- Variants drafted.
- Variants approved.
- Postiz handoff proposals created.
- Pending action proposals approved.

Lagging:

- Conversion events attributed to `contentVariantId`, `postizPostId`, and `postizChannelId`.
- Reduced operator work needed outside MOS before Postiz handoff.

## Owner / Review

Owner: Codex / Aldrin  
Date: 2026-05-22  
Review point: next pass should cover live OAuth/provider sync and Postiz executor wiring only after credentials/app approval are available.

## Stop Condition

Targeted frontend test, frontend build, Chrome local end-to-end flow, backend tests, compile check, migration head check, Postiz ownership guard, source manifest verification, lane proof, plan gate proof, proof dashboard, and planctl verification pass.
