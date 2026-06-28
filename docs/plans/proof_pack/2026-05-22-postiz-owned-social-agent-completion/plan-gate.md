# Plan Gate: Postiz-Owned Social Agent Completion

## Goal Artifact

Complete the Connected Social + TikTok Carousel implementation correction by 2026-05-22 with Postiz as the posting system of record.

Measurable success:

- The new growth-program slice has no `content_publications`, `content_performance_snapshots`, or `content_attributions` ledger.
- Approved TikTok carousel variants create Postiz handoff proposals.
- Conversion events can reference concrete Postiz ids without cloning Postiz post state.
- Runtime profiles and PRD wording encode Postiz ownership.
- Tests and proof gates pass.

## Problem Log

- The first pass added a second posting ledger under growth programs.
- That duplicated Postiz responsibilities for compose, schedule, publish, post ids, release ids, and status.
- Duplication would create drift between Postiz and mOS.
- The agent still needed a clean way to hand approved variants to Postiz.

## Root-Cause Diagnosis

Root cause: the first implementation modeled the workflow from a generic content-experiment lens before locking the ownership boundary around Postiz.

5-whys chain:

- Why was duplication introduced? The PRD listed content publication tables as a future content layer.
- Why did that conflict? The user wants Postiz to own posting work.
- Why is this risky? Two ledgers create unclear source of truth for schedule/status/release ids.
- Why does the agent still need local state? mOS needs strategy, drafts, approvals, conversions, and action proposals.
- Why is a handoff enough now? Approved variants can become action proposals that open or feed Postiz, while Postiz owns execution.

## Current Machine

- mOS has content growth programs, variants, slides, approvals, and conversion events.
- Postiz already has credentials, channels, posting profiles, publication routes, and post status sync.
- The added growth-program publication layer overlapped Postiz.

## Designed Machine

- mOS stores approved content variants and conversion references.
- mOS creates `postiz.composer_handoff` action proposals for approved variants.
- Postiz owns compose, schedule, publish, social post lifecycle, and provider-specific posting details.
- Conversion events can carry `contentVariantId`, `postizPostId`, and `postizChannelId`.
- Runtime profiles forbid direct posting from agent runtime.

## Worst-Day Test

- A variant is unapproved: handoff proposal returns 409.
- Media count does not match TikTok carousel slide count: handoff proposal returns 422.
- A schedule/now request lacks channels: handoff proposal returns 422.
- Postiz status changes after handoff: mOS has no duplicate growth posting ledger to drift.
- Conversion data arrives later: mOS stores concrete references only when provided.

## Leading And Lagging Metrics

Leading:

- Approved variants with Postiz handoff proposals.
- Rejected handoff attempts due to missing approval/media/channel input.
- Conversion events carrying concrete content/Postiz references.

Lagging:

- Reports sourced from Postiz analytics and conversion events.
- Reduction in state drift bugs between Postiz and mOS.
- Faster review because posting work stays in Postiz.

## Owner, Date, Review

Owner: Codex / Aldrin  
Date: 2026-05-22  
Review point: next pass before live Postiz executor or frontend composer handoff UI.

## Stop Condition

Stop when targeted tests, compile, migration head, ownership guard, lane proof, plan gate, source manifests, dashboard, and plan contract pass.

