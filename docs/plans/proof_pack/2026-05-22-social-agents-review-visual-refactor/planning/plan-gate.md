# Social Agents Review Visual Refactor Plan Gate

## Goal

Refactor the Social Agents Review screen so a customer can review a marketing carousel visually first, understand the one next action, and avoid form-heavy setup machinery unless they choose to open the editor.

## Problem Log

- The previous Review surface exposed Test, Draft, Assets, Postiz, URL, and handoff controls as competing visible work areas.
- The user explicitly flagged the screen as too confusing, too wordy, and unclear about the primary CTA.
- Browser validation after the refactor records 6 visible slide cards, 0 visible textareas by default, 1 primary workflow CTA, and no horizontal overflow on desktop or mobile.

## Root Cause

The UI mapped backend objects onto the main canvas instead of mapping the customer's review job. The customer is trying to answer "is this creative ready?" and "what is blocking launch?", but the screen forced them to operate internal structures before they saw the creative.

## Current Machine

The old machine treated the Review state as a form console:

- visible draft metadata
- visible asset URL fields
- separate review and approval concepts
- wordy Postiz explanation
- repeated black/action buttons

## Designed Machine

The new machine treats each slide as the unit of work:

- 6 responsive slide cards are the default workspace
- actions sit on the card with icons: edit, add media, regenerate, approve
- advanced fields are collapsed into one editor drawer
- one primary workflow CTA reflects the current gate
- Postiz remains a compact handoff destination, not a wall of explanatory text

## Worst-Day Test

When no assets, no approved draft, and no channel are available, the screen must still be readable:

- the slide cards remain visible
- missing media is shown as a compact status chip
- the only primary CTA points to the next gate
- URL fields stay hidden until the user opens Media or Editor
- the layout must not overflow on mobile

## Metrics

Leading checks:

- default Review state has 6 `slide-preview-card` elements
- default Review state has 0 visible textareas
- Review state has 1 `review-primary-cta`
- toolbar labels are compact: Media, Generate, Render, Use, Editor

Lagging checks:

- unit tests pass
- production build passes
- semantic UI check passes
- design-system scan passes
- browser proof shows no horizontal overflow at 1280px and 390px

## Owner / Review

Owner: Codex main thread.

Date: 2026-05-22.

Review point: after unit tests, build, guardrail checks, Browser screenshots, source manifest, lanecheck, plangatecheck, planctl verify, and proof dashboard pass.

## Stop Condition

Stop when the actual MOS app Review screen is visual-first, keeps the business logic intact, and all verification gates pass with proof artifacts in the task proof pack.
