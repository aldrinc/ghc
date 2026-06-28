# Plan Gate: Connected Social + TikTok Implementation

## Goal Artifact

Ship the first backend foundation for Connected Social Agents and the TikTok Carousel Growth Agent by 2026-05-22.

Measurable success:

- Add persistent primitives for connected provider assets, snapshots, approval-gated action proposals, growth programs, carousel variants, publications, conversion events, and attribution.
- Register Hermes runtime profiles for `meta-ads-manager`, `social-media-manager`, and `tiktok-carousel-growth-manager`.
- Prove the slice with targeted backend tests, migration head validation, compile checks, source manifest checks, lane proof, and `planctl verify`.

## Problem Log

- MOS had no first-class action proposal layer for an agent operating on behalf of a user.
- Connected social data had no durable normalized storage for provider assets and snapshots.
- TikTok carousel workflows had no program/experiment/variant/publication/conversion model.
- Postiz had scheduling/publishing coverage, but MOS lacked analytics and release-id reconciliation surfaces.
- Runtime registry did not expose the social/TikTok agent profiles needed by Hermes.

## Root-Cause Diagnosis

Root cause: the system treated social work as isolated publishing actions instead of an approval-gated growth loop.

5-whys chain:

- Why could agents not operate cleanly on behalf of users? There was no shared proposal/approval primitive.
- Why was there no shared primitive? Existing surfaces focused on workflows and publishing, not durable agent actions.
- Why did TikTok carousel + conversion attribution not fit? Content variants, publications, and conversions were not modeled as one experiment loop.
- Why could connected social data not be reused across agents? Provider assets and snapshots were not normalized in MOS.
- Why would direct external writes be risky? The runtime lacked explicit profile-level guardrails and action approvals for this domain.

## Current Machine

- External accounts and social publishing live outside the MOS data model.
- Postiz handles part of the scheduling/publishing path.
- Agents can generate or reason, but do not have a consistent internal action ledger.
- Analytics and conversion feedback are disconnected from content variants.

## Designed Machine

- Connected provider assets and snapshots store what the user connected and what the agent observed.
- Agents write proposed actions first; approval records gate execution.
- TikTok carousel programs own experiments, variants, slides, publication intents, conversion events, and attribution.
- Postiz client exposes analytics and release-id reconciliation methods for future execution workers.
- Hermes profiles encode the allowed scope and safety rules for each agent.

## Worst-Day Test

- Provider tokens are unavailable: system stores no raw tokens and can still create internal provider asset records from concrete input.
- External write is attempted early: router requires proposal or variant approval before publication intent.
- Postiz release IDs drift: client exposes missing-release and attach-release methods.
- Metrics are absent: schemas require concrete payloads; tests do not invent performance data.
- A model/provider change is tempting: runtime profile rules explicitly forbid model/provider switching.

## Leading And Lagging Metrics

Leading:

- Number of connected provider assets with snapshots.
- Number of agent proposals created, approved, rejected, or expired.
- Number of carousel variants approved before publication intent.
- Percent of publications with platform post/release IDs attached.

Lagging:

- Posts with performance snapshots linked back to variants.
- Conversion events attributed to content variants.
- Hook/CTA rollups with enough concrete events to drive next experiments.
- Failed execution attempts caused by missing approval or missing provider asset.

## Owner, Date, Review

Owner: Codex / Aldrin  
Date: 2026-05-22  
Review point: next implementation pass before enabling live OAuth, live posting, or frontend execution surfaces.

## Stop Condition

Stop when:

- The implementation plan contract passes.
- Targeted tests pass.
- Lane proof passes.
- Source manifests remain verified.
- Proof dashboard renders.

