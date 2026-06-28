# Social Agents UI Refactor Plan

Date: 2026-05-22  
Source model: `deepinfra/moonshotai/Kimi-K2.6` via local OMP harness  
Mode: plan only

## Decision

Refactor `SocialAgentsPage` into an operator workbench organized around the real workflow:

`Configure -> Generate -> Validate -> Handoff`

Keep Postiz as the posting system of record. MOS should make the agent workflow easier to operate, review, and hand off; it should not become a direct publishing surface.

## Goal

Make the Social Agents tab reviewable and shippable as a clear workbench where an operator can understand readiness, create a six-slide TikTok carousel variant, approve it, attach required media URLs, and create a Postiz handoff proposal without losing queue or connection context.

## Observable Problem

The current page is functionally wired but visually weak:

- Program, Conversion Source, Experiment/Variant, and Postiz Handoff appear as same-weight bordered form blocks.
- Connected Social and Action Queue live in separate tabs, so readiness and approvals are detached from the main workflow.
- Selected Loop and Latest Variant sit in a sidebar instead of guiding the step that needs them.
- The preview uses gradient placeholder cards, which helps layout but does not prove media readiness.

## Root-Cause Diagnosis

The page is organized by backend resource type, not by operator intent. That makes every control look equally important and forces the user to infer the execution sequence from disabled buttons and scattered counts.

Current machine: load resource lists, show three status callouts, put each resource mutation in its own bordered block, hide assets/proposals behind tabs.

Designed machine: show one execution path, expose readiness as persistent context, keep approval and handoff near the variant, and move reference-only tables into secondary drawers or compact side panels.

## Target IA

Top rail:

- Page title, Postiz link, workspace context.
- Status chips for Postiz readiness, pending proposals, growth loops, connected assets.
- Chips open contextual panels/drawers where useful; they do not replace the main workflow.

Main workbench:

- Left: vertical stage rail.
  - Stage 1: Program
  - Stage 2: Conversion Source
  - Stage 3: Experiment + Variant
  - Stage 4: Approval + Postiz Handoff
- Right: sticky context/preview panel.
  - Selected loop summary.
  - Latest variant summary.
  - Six-slide preview from slide data.
  - Media URL readiness count.

Secondary surfaces:

- Connected Social: compact drawer/panel for synced provider assets.
- Action Queue: drawer/panel for proposals, with approval actions and count refresh.

## Component Split

- `SocialAgentsPage`: data orchestration, selected program state, query/mutation wiring.
- `SocialAgentsTopRail`: Postiz link, readiness chips, drawer triggers.
- `SocialAgentsStageRail`: stage list, completion states, disabled reasons.
- `ProgramStage`: create/select growth program.
- `ConversionSourceStage`: configure conversion source.
- `ExperimentVariantStage`: create experiment, edit Larry six-slide formula, create variant.
- `PostizHandoffStage`: approve variant, collect media URLs, create Postiz proposal.
- `VariantPreviewPanel`: sticky loop context, latest variant, six-slide preview, media parity.
- `ConnectedSocialPanel`: provider asset table moved out of primary workflow.
- `ProposalQueuePanel`: pending proposals and approval actions moved out of tab silo.

## Implementation Phases

1. Structure:
   - Replace `Tabs` as the primary IA with a workbench layout.
   - Keep data hooks and mutation contracts intact.
   - Move current tab content into extracted components without behavior changes.

2. Stage states:
   - Add derived stage readiness helpers.
   - Show completion/blocked states for program, source, experiment/variant, approval/handoff.
   - Display concrete disabled reasons beside actions.

3. Preview and context:
   - Move Selected Loop and Latest Variant into `VariantPreviewPanel`.
   - Keep six-slide preview driven by existing `slides`, `slideText`, and entered media URLs.
   - Do not add media polling unless an existing backend source for rendered URLs is confirmed.

4. Secondary context:
   - Move Connected Social and Action Queue into panels/drawers.
   - Keep approval mutation and query invalidation behavior.
   - Preserve proposal-only Postiz handoff.

5. Visual pass:
   - Reduce nested card borders.
   - Use dividers, step groups, compact labels, status chips, and restrained surface hierarchy.
   - Verify desktop and mobile text fit, no overlapping controls, and no oversized dashboard-card mosaic.

## Acceptance Checks

- Main page reads as one workflow, not three unrelated tabs.
- Stage 4 cannot create handoff unless the selected variant is approved and media URL count equals `slideCount`.
- Operator can approve a pending proposal without leaving the main workflow.
- Connected provider assets remain visible on demand without competing with the TikTok creation flow.
- Existing payload contracts remain intact:
  - program uses `tiktok`, `tiktok_carousel`, `approval_required`, and `postizSystemOfRecord: true`;
  - handoff creates a Postiz proposal, not a direct publish.
- Empty workspace state still renders.

## Verification

Run after implementation:

```bash
cd /Users/aldrinclement/Documents/programming/marketi/mos/frontend
yarn test:unit src/pages/workspaces/SocialAgentsPage.test.tsx
yarn build
```

Browser validation:

- Open `/workspaces/execution/social-agents`.
- Verify desktop layout at common laptop width.
- Verify mobile layout stacks without text overlap.
- Verify drawer/panel open and close states preserve stage form state.

## Tests To Add Or Update

- Stage gating:
  - no program disables source/variant/handoff stages;
  - unapproved variant disables handoff;
  - wrong media URL count disables handoff with a visible reason.
- Proposal queue:
  - opening queue panel renders pending proposal;
  - approval calls existing mutation;
  - panel close does not reset stage state.
- Preview:
  - six-slide preview renders from `---` split text;
  - media count reflects entered URLs.

## Failure Modes

- Shallow diagnosis: only restyling cards without changing the workflow order.
- Symptom fix: moving tabs around while keeping approvals detached from handoff.
- Willpower plan: relying on the operator to remember prerequisites instead of showing blocked states.
- Perfect-day plan: layout works only when data exists; empty and partially configured states must be first-class.
- Scope creep: adding backend rendering, polling, or model changes during a UI refactor.
- Overengineering: building a generic workflow engine instead of focused Social Agents components.

## Worst-Day Test

With no program, no connected assets, one pending proposal, and a narrow viewport, the page should still explain what is missing, show the next available action, and avoid hiding the approval queue behind unrelated navigation.

## Metrics

Leading:

- Stage readiness helpers are covered by tests.
- Handoff disabled reasons are visible in UI tests.
- Browser screenshots show no overlap on desktop and mobile.

Lagging:

- Operator can complete the tested handoff path without changing routes.
- Review can verify Postiz ownership and proposal-only behavior from one page.

## Parallelization Map

parallelizable: yes

- Lane A: extract workbench shell and stage components.
- Lane B: extract preview/context panel and media readiness display.
- Lane C: move Connected Social and Action Queue into panels/drawers.
- Lane D: update tests and browser validation.

Expected speed gain: meaningful if shipped, because lanes A-C can edit separate components once `SocialAgentsPage` passes shared props down.

Token spend justification: worthwhile during implementation because UI, preview, and tests are separable and review speed matters.

Write ownership:

- Lane A: `SocialAgentsPage.tsx`, new stage shell components.
- Lane B: new preview/context components.
- Lane C: new connected/queue panel components.
- Lane D: tests and validation artifacts.

Fan-in plan: main thread integrates props, removes duplicated state, runs unit/build/browser checks, then fixes visual regressions.

Validation owner: main thread.

Meta-tooling opportunity: add a lightweight screenshot smoke script for operator workbench pages if this pattern repeats.

## Blocked Inputs

No implementation blocker for the plan. Backend-rendered media URL availability is unknown, so the plan keeps preview behavior tied to existing variant slide data and operator-entered media URLs.

## Owner And Review

Owner: Codex main thread on implementation.  
Review point: after unit tests, build, and browser screenshots pass.  
Stop condition: plan is ready to ship when `plangatecheck` passes and the user says `Ship the plan.`

Say "Ship the plan" when you want me to implement and verify it.
