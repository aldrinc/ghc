# Plan Gate: Social Agents UI Refactor

## Goal

Make the MOS Social Agents tab a clear operator workbench for configuring, generating, validating, approving, and handing off TikTok carousel variants through Postiz proposal flow.

## Problem Log

1. The current page uses same-weight blocks for different workflow stages.
2. The UI is organized around backend resources rather than operator sequence.
3. Connected assets and approval proposals are isolated in tabs, away from the main creation/handoff path.
4. Preview exists, but it does not yet prove final media readiness.

## Root-Cause Diagnosis

Root cause: weak workflow model. The UI exposes resource CRUD instead of an execution machine, so the user has to infer dependencies from disabled buttons and scattered counts.

## Current Machine

Load programs, sources, experiments, variants, provider assets, and proposals. Show callouts. Show one main TikTok form stack. Put connected assets and queue in separate tabs. Handoff gating lives near the bottom of the form stack.

## Designed Machine

Show one stage-based workbench: Configure -> Generate -> Validate -> Handoff. Keep readiness and queue context persistent. Use a sticky preview/context panel. Move asset and queue tables into secondary panels. Preserve existing backend contracts.

## Worst-Day Test

No program, no assets, pending proposals, and mobile viewport: the UI must still show next action, blockers, proposal context, and no overlapping controls.

## Leading And Lagging Metrics

Leading: stage helpers tested, disabled reasons visible, drawer state preserves form state, screenshots show no overlap.  
Lagging: operator can complete the tested handoff path without route switching; reviewer can verify Postiz proposal-only behavior from one page.

## Owner / Date / Review

Owner: Codex main thread during implementation.  
Date: 2026-05-22.  
Review point: after unit tests, build, and browser validation pass.

## Stop Condition

Planning stops when the plan is written, Kimi raw output is captured, and `plangatecheck` passes. Implementation starts only after the user says `Ship the plan.`
