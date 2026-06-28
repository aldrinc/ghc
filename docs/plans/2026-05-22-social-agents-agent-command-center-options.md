# Social Agents Agent Command Center UX Refactor Options

Date: 2026-05-22  
Mode: design plan only  
Current route observed: `/workspaces/execution/social-agents`

## Decision

Ship Option 2: **Agent Command Center with a guided setup wizard and a persistent Agent Dossier on the right**.

The current wizard is better than the earlier all-in-one workbench, but it still exposes the wrong mental model. A customer is not trying to create a Program, Source, Experiment, Variant, Media batch, and Handoff. They are trying to set up a marketing agent, give it boundaries, review its work, and understand what it is doing on their behalf.

## Goal

Make the Social Agents tab answer five customer questions in the first viewport:

1. What is this agent trying to grow?
2. What does it need from me?
3. What is it allowed to do?
4. What work is waiting for approval?
5. What happened, and what should it do next?

## Observable Problem

The live page still reads like backend machinery:

- `Choose Program`, `Add Conversion Source`, `Create Experiment`, `Write Carousel`, `Render Media`, and `Postiz Handoff` are implementation nouns.
- The customer has to infer that these steps create and manage an agent.
- The right side is underused even though it should carry persistent context.
- The current screen mixes setup, creative production, approval, and system readiness language.
- `Action queue` and `Connected social` are secondary buttons, but they are central to trusting an agent.

## Root Cause

The UI mirrors the data model instead of the customer job.

Current machine:

- Backend objects drive page labels.
- Setup and operations share the same language.
- Readiness appears as counts and disabled states.
- Agent trust is implicit.

Designed machine:

- Customer hires and configures a marketing agent.
- Each screen has one purpose.
- Backend nouns become implementation details.
- The right rail always explains the agent's mission, permissions, status, and next blocker.
- The operating loop is approval-centered: draft, review, handoff, learn.

## Backend-To-UX Translation

| Backend concept | Customer-facing concept |
|---|---|
| Growth Program | Agent Mission |
| Conversion Source | Success Signal |
| Content Experiment | Learning Loop |
| Content Variant | Creative Draft |
| Rendered Media | Creative Assets |
| Postiz Handoff Proposal | Approval / Publish Request |
| Agent Action Proposal | Approval Inbox |
| Social Provider Asset | Connected Channel |

## Option 1: Pure Setup Wizard

Use a full-page wizard when the agent is not configured. After completion, switch to a simple management view.

Screens:

1. Mission: what should the agent grow?
2. Channels: where can it publish through Postiz?
3. Success Signal: what counts as a win?
4. Guardrails: what is it allowed to do without approval?
5. Review: preview, edit, approve, and resolve blockers in one place.

Pros:

- Lowest cognitive load.
- Clear one-purpose screens.
- Fastest near-term refactor from the current wizard.

Cons:

- Weak for ongoing management unless a second dashboard is added.
- Can become a long form if each screen gets too many fields.

Best use:

- First-time setup, empty state, onboarding.

## Option 2: Agent Command Center

Recommended.

Use the full page as a management console. The main panel shows the current job; the right panel is a persistent Agent Dossier.

Layout:

```text
Header: Social Agent / status / primary action

Main left: one active job
- If setup incomplete: one wizard screen
- If setup complete: next best action, approvals, learning loop

Right rail: Agent Dossier
- Mission
- Setup progress
- Channels and permissions
- Success signal
- Guardrails
- Current draft / handoff status
- Latest learning
- Blocked reason
```

Primary surfaces:

- Setup: single-purpose screens for mission, channels, success, guardrails, creative brief, first approval.
- Work Queue: drafts and agent actions that need approval.
- Learning Loop: experiments, results, next recommendation.
- History: activity log of what the agent did and why.

Pros:

- Handles setup and ongoing management in one coherent system.
- Uses the full right section for durable context.
- Keeps the user oriented when moving between setup, approval, and learning.

Cons:

- More implementation than a pure wizard.
- Needs careful empty/partial states or it becomes dashboard soup.

Best use:

- The durable Social Agents tab.

## Option 3: Brief-First Agent Interview

Start with a brief-like intake instead of forms. The system maps the brief into mission, success signal, guardrails, and first creative loop behind the scenes.

Flow:

1. User briefs the agent: product, customer, offer, tone, channel, goal.
2. Agent returns a setup summary.
3. User confirms permissions and success signal.
4. Agent drafts first carousel.
5. User approves the Postiz handoff.

Pros:

- Most aligned with "agent does marketing on my behalf."
- Hides backend machinery well.
- Strong first impression.

Cons:

- Higher extraction and validation risk.
- Requires better error handling when the brief is incomplete.
- Harder to test deterministically.

Best use:

- A later layer inside Option 2 as the first setup screen, not the whole product surface yet.

## Option 4: Production Board

Represent the agent as a pipeline:

- Needs setup
- Drafting
- Needs approval
- Scheduled / handed off
- Learning

Pros:

- Good for teams managing many campaigns.
- Approval work is obvious.

Cons:

- Too operational for first-time setup.
- Can feel like campaign management software instead of an agent.

Best use:

- A future `History` or `Work Queue` mode, not the primary first experience.

## Recommended IA

First visit, no configured agent:

- Page title: `Set up your marketing agent`
- Primary CTA: `Start setup`
- Main panel: current wizard screen only.
- Right rail: `Agent Dossier`, showing what is known, missing, and blocked.

Configured agent:

- Page title: `Marketing Agent`
- Primary CTA: next required action, such as `Review draft`, `Connect channel`, or `Create next test`.
- Main panel: current work item.
- Right rail: mission, permissions, success signal, current status.

## Wizard Screens

Each screen gets one purpose:

1. **Mission**
   - Customer-facing question: "What should this agent grow?"
   - Writes/updates: Growth Program.
   - UI fields: agent name, product/offer, objective.

2. **Channels**
   - Customer-facing question: "Where can the agent work?"
   - Reads: Postiz channels and social provider assets.
   - UI fields: selected channel, missing connection state, channel permissions.

3. **Success Signal**
   - Customer-facing question: "How does the agent know it won?"
   - Writes/updates: Conversion Source.
   - UI fields: event source, goal events, status.

4. **Guardrails**
   - Customer-facing question: "What is the agent allowed to do?"
   - Writes/updates: authority mode and approval policy metadata where available.
   - UI fields: approval required, scheduling mode, blocked topics, brand safety notes.

5. **Review**
   - Customer-facing question: "What blocks this from going to Postiz?"
   - Writes/updates: Content Experiment, Content Variant, variant approval, and Postiz Handoff Proposal when ready.
   - UI fields: draft preview, key creative settings, asset count, destination badge, blocker-driven CTA.

## Right Rail: Agent Dossier

The right section should be sticky on desktop and collapse into a drawer on mobile.

Sections:

- Mission: agent name, product, objective.
- Setup: progress and next missing item.
- Channels: Postiz readiness, selected channel, connected assets.
- Authority: approval mode and what the agent cannot do.
- Success: conversion source and goal events.
- Current Work: draft status, media count, handoff readiness.
- Latest Learning: current experiment hypothesis and next recommendation.
- Activity: last 3 agent actions.

Rule: the right rail never becomes another form. It is context, status, and trust.

## Main Operating Dashboard

After setup, the main panel should not keep showing setup steps. It should show one next action:

- Review a draft.
- Approve a Postiz handoff.
- Fix a missing channel.
- Add creative assets.
- Start the next learning loop.

Below the next action, use compact sections:

- Approval Inbox.
- Learning Loop.
- Recent Activity.

Avoid a card mosaic. This is an operator surface, not a landing page.

## Visual Thesis

Quiet command-center UI. Dense, sober, operational. One primary action per state. Minimal chrome. Strong status hierarchy. The agent should feel managed and bounded, not magical or vague.

Simplification rule:

- The main panel owns the user's current action.
- The right rail is only a compact status summary.
- Do not show multiple black buttons in the same visible state.
- Do not make the dossier read like a document or second page.
- Replace internal action names like `Create proposal` with the user's next job, such as `Add 2 assets` or `Send to Postiz`.
- Use badges for durable system facts like `Postiz`; do not explain them in paragraphs unless the user is blocked.

## Brand-Matched Visual Direction

Use the existing MOS app language:

- Typography: `Libre Baskerville` for page-level headings, `DM Sans` for product UI.
- Surfaces: white main surface, `#f8fafc`/`#f7f8fa` soft sidebar and secondary panels.
- Text: near-black `#0b0d12` for primary copy, slate-muted text for metadata.
- Action hierarchy: black primary pill buttons, blue accent only for selected/active system states.
- Components: compact badges, thin `#e6e9f0` borders, 8px panel radius, minimal shadows.
- Layout: app-shell faithful, with sidebar, top breadcrumb/product bar, page header, main work panel, and persistent right dossier.

Sample visual artifact:

- HTML mock: `/Users/aldrinclement/Documents/programming/marketi/docs/plans/proof_pack/2026-05-22-social-agents-agent-command-center-options/social-agents-command-center-mock.html`
- Purpose: show simplified Setup and combined Review/Approve states in one standalone review file.
- Copy audit: `/Users/aldrinclement/Documents/programming/marketi/docs/plans/proof_pack/2026-05-22-social-agents-agent-command-center-options/copy-reduction-audit.md`
- Data note: sample copy/counts are visual placeholders only and should not be consumed as real workspace data.

## Interaction Thesis

- Setup screens transition linearly with saved state.
- Right dossier updates live as each setup screen completes.
- Approval actions use strong blocked states: exactly what is missing and how to fix it.

## Implementation Phases

1. **Rename the model in the UI**
   - Replace customer-facing backend nouns with agent nouns.
   - Keep API payloads unchanged.
   - Add mapping helpers so code can still speak backend internally.

2. **Extract the right rail**
   - Build `AgentDossierRail`.
   - Feed it selected program, channel readiness, source, variant, media count, and proposals.

3. **Rebuild setup as agent onboarding**
   - Replace the current backend-shaped steps with Mission, Channels, Success Signal, Guardrails, and Review.
   - Keep one screen active at a time.

4. **Add post-setup command mode**
   - If setup is complete, route the main panel to the current next action.
   - Keep setup editable but not the default surface.

5. **Turn queue/assets into management surfaces**
   - Approval Inbox becomes a first-class operating section.
   - Connected Channels become a right-rail or drawer detail, not a disconnected table.

6. **Test and validate**
   - Unit tests for setup gating, handoff gating, right rail status, and proposal approval.
   - Browser screenshots for desktop and mobile.
   - Existing Postiz proposal-only behavior must remain intact.

## Acceptance Checks

- A first-time user can say what the agent will do after reading the first screen.
- Every setup screen has exactly one purpose.
- There is one primary CTA per state.
- Any mock/debug controls must be visually quieter than the real primary CTA.
- Backend nouns are not primary UI labels.
- The right rail explains mission, authority, status, and blocker in a compact summary, not long prose.
- Handoff remains blocked unless variant is approved and media count matches `slideCount`.
- Postiz remains the publishing system of record.
- Existing mutation contracts are preserved.

## Verification Commands

```bash
cd /Users/aldrinclement/Documents/programming/marketi/mos/frontend
npm run test:unit -- src/pages/workspaces/SocialAgentsPage.test.tsx
npm run build
npm run check:semantic-ui
npm run check:design-system
```

Browser validation:

- `/workspaces/execution/social-agents` renders without horizontal overflow.
- Sample HTML mock renders through localhost without horizontal overflow.
- Desktop shows main panel plus sticky Agent Dossier.
- Mobile collapses the dossier without hiding the primary action.
- Empty, partially configured, and handoff-blocked states are readable.

## Failure Modes

- Shallow diagnosis: only renaming labels while keeping the backend-shaped flow.
- Symptom fix: making a nicer wizard without an ongoing management mode.
- Willpower plan: expecting the user to remember prerequisites instead of showing blockers.
- Perfect-day plan: only designing the configured state; empty and broken states must be first-class.
- Overengineering: building a generic agent platform instead of fixing this Social Agents tab.
- Scope creep: changing models, backend contracts, or publishing behavior during UI refactor.

## Speed Map

parallelizable: yes

Parallelization map:

- Lane A: UI language and IA mapping.
- Lane B: `AgentDossierRail`.
- Lane C: setup wizard component extraction.
- Lane D: operating dashboard and approval inbox.
- Lane E: tests and browser proof.

Expected speed gain: high after component boundaries are chosen because the right rail, setup screens, and approval inbox can be built independently.

Token spend justification: worthwhile for implementation because this touches information architecture, visual hierarchy, and tests.

Write ownership:

- Lane A: `SocialAgentsPage.tsx` labels and helper mapping.
- Lane B: `mos/frontend/src/pages/workspaces/social-agents/AgentDossierRail.tsx`.
- Lane C: setup components under `mos/frontend/src/pages/workspaces/social-agents/`.
- Lane D: approval and operating dashboard components.
- Lane E: tests and validation artifacts.

Fan-in plan: main thread owns state wiring, API payload preservation, final visual pass, and all verification commands.

Validation owner: main thread.

Meta-tooling opportunity: add a reusable workbench screenshot smoke for MOS execution pages if this pattern repeats.

## Stop Condition

This plan is ready to ship when the proof gate passes and the user says `Ship the plan.`

## Implementation Addendum

Decision: ship the simplified two-screen version first.

- `Setup`: mission, saved mission selector, compact success signal, one primary `Continue` CTA.
- `Review`: combined review/approval/postiz delivery surface, one computed primary CTA.
- Right rail: compact agent dossier with mission, channel, draft, assets, and current blocker.
- Preserved behavior: Postiz handoff still creates an approval proposal and never publishes directly.

Implementation files:

- `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/SocialAgentsPage.tsx`
- `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/SocialAgentsPage.test.tsx`

Implementation acceptance:

- Setup and Review are the only primary screens.
- Visible app state has one primary black CTA.
- Backend nouns are removed from the primary customer workflow.
- Review and approval are one step.
- Unit tests prove source-image gating, approval gating, action queue approval, empty workspace, and handoff payload preservation.
- Browser proof checks desktop/mobile screenshots, no horizontal overflow, and no forbidden old copy.
