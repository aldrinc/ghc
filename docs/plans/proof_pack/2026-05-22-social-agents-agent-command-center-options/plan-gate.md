# Plan Gate: Social Agents Agent Command Center UX

## Goal

Refactor the Social Agents UI plan around the real customer job: set up, trust, approve, and manage a marketing agent that works through Postiz and learns from conversion signals.

## Problem Log

- The live UI exposes backend nouns as primary customer labels.
- The right section does not carry persistent agent context even though the user called out that full right section as available.
- The current wizard makes the sequence clearer, but not the customer mental model.
- Approval, connection, and learning trust signals are secondary instead of central.

## Root-Cause Diagnosis

The page is organized around data model completion rather than agent management. The root flaw is information architecture: the UI asks the user to configure the system's internals instead of guiding them through hiring and supervising a bounded marketing agent.

## Current Machine

User lands on Social Agents. The UI shows status chips, six backend-shaped steps, form fields, a few counts, and secondary panels. The customer must translate those into agent setup and management.

## Designed Machine

User lands on an Agent Command Center. If the agent is incomplete, they get a single-purpose setup screen. If the agent is configured, they get the next action. The right rail always shows the Agent Dossier: mission, permissions, channels, success signal, current work, blocker, and latest learning.

## Visual Thesis

The design should look like MOS, not a new product: white/slate app shell, Libre Baskerville page titles, DM Sans product UI, one black primary pill button per state, compact badges, thin borders, minimal shadows, and a right-side Agent Dossier that stays terse.

## Worst-Day Test

No channels, no source, one draft, missing media, and a pending action should still produce one obvious next action and a clear right-rail explanation of what is missing. The UI must not collapse into technical labels or disconnected tables.

## Leading And Lagging Metrics

Leading:

- One primary CTA per UI state.
- All setup steps have a single purpose.
- Tests cover handoff gating, right rail status, setup gating, and proposal approval.
- Browser proof shows no desktop/mobile overflow or overlapping text.

Lagging:

- User can complete first approved Postiz handoff from one page.
- User can explain the agent mission, permissions, and blocker from the first viewport.
- Approval queue becomes visible as agent management, not a hidden table.

## Owner / Date / Review

Owner: Codex main thread for plan and future implementation.  
Date: 2026-05-22.  
Review point: after unit tests, build, semantic/design checks, and browser screenshots pass during implementation.

## Stop Condition

Plan stage stops when `plangatecheck` passes and the user has a concise recommendation, implementation options, and a verified standalone visual mock.
