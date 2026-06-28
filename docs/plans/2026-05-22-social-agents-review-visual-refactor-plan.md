# Social Agents Review Visual Refactor Plan

Date: 2026-05-22

## Goal

Make the Social Agents Review screen usable as a visual creative review surface.

## Problem

The current Review screen is still form-first. Live browser evidence showed roughly 222 visible words, 7 inputs, 4 textareas, and separate Test, Draft, Assets, and Postiz sections before the user can act on the carousel. The image is not the interface.

## Root Cause

The UI exposes backend setup objects during review. Users need to inspect slides and make the next creative operation obvious, but the screen asks them to parse configuration fields.

## Design

1. Put the six-slide carousel workspace first.
2. Treat each slide card as the unit of work.
3. Move slide actions onto or directly below each image with icon buttons.
4. Collapse Test, Draft, Assets, Postiz, and URL fields into one advanced editor panel.
5. Keep one primary gated action for the whole workflow.
6. Keep Postiz handoff proposal-only behavior unchanged.

## Doing

Owner: Codex

Implementation files:

- `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/SocialAgentsPage.tsx`
- `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/SocialAgentsPage.test.tsx`

Verification:

- Unit tests for SocialAgentsPage.
- Production frontend build.
- Semantic UI and design system checks.
- Browser validation on `/workspaces/execution/social-agents`.
- Kimi K2.6 `omp` implementation guidance log.

## Acceptance

- Review screen defaults to visual slide cards, not visible form sections.
- The default Review state has fewer visible textareas than before.
- Each slide card has icon actions for edit, asset, regenerate, and approval-related review.
- The advanced editor exposes the existing Test, Draft, Assets, and Postiz fields without making them the default surface.
- The screen keeps one primary CTA for the workflow state.
- Postiz handoff mutation payload remains unchanged.
- Browser validation shows no horizontal overflow at desktop and mobile sizes.

## Speed Map

parallelizable: yes

Parallelization map:

- Kimi via `omp`: implementation guidance and acceptance risks.
- Main lane: React/Tailwind implementation.
- Verification lane: tests, build, browser evidence, plan contract.

Expected speed gain: Kimi guidance runs while the main lane prepares contract and code context.

Token spend justification: UI direction has been revised several times; external model review reduces repeated taste misses.

Write ownership:

- Main lane edits `SocialAgentsPage.tsx` and `SocialAgentsPage.test.tsx`.
- Verification lane writes proof artifacts only.
- Kimi lane writes logs only.

Fan-in plan: main lane applies only concrete guidance that supports the visual-first plan and preserves current business logic.

Validation owner: main lane.
