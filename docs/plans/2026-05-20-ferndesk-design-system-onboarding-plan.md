# FernDesk-Inspired Design System + Onboarding Plan

Date: 2026-05-20
Root: `/Users/aldrinclement/Documents/programming/marketi`
Reference source: `proof_pack/design-system-ferndesk-2026-05-20/source/source_manifest.json`

## Decision

Upgrade the design system first, then rebuild onboarding on top of it. The wrong move is repainting the current wizard. The root issue is missing first-run experience primitives: progress theatre, setup status, context preview, review changes, and publish/loading states.

## Video Read

The FernDesk reference has a tight brand system:

- Split layout: focused white task area on the left, persistent context/preview panel on the right.
- Serif headline, muted body copy, minimal hierarchy.
- Black primary CTA with calm secondary actions.
- Thin top progress rail instead of bulky steppers.
- One job per screen.
- Friendly copy that acknowledges user pain, then moves forward.
- Setup screen shows real-feeling tasks: configured, learning, created.
- Integration grid uses recognizable app chips.
- Main app continues the same language: pale sidebar, black header actions, minimal borders, editorial article preview, status labels for new/updated/deleted work.
- Publish state uses blur-backdrop modal, a restrained spinner, and one clear status line.

## Current Repo Read

Relevant current files:

- `mos/frontend/src/styles/theme.css`
- `mos/frontend/src/styles/design-system.css`
- `mos/frontend/src/components/ui/button.tsx`
- `mos/frontend/src/components/design-system/DesignSystemProvider.tsx`
- `mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx`
- `mos/frontend/src/pages/workspaces/WorkspaceOnboardingPage.tsx`
- `mos/frontend/src/components/clients/OnboardingWizard.tsx`
- `mos/frontend/src/app/AppShell.tsx`
- `mos/frontend/src/hooks/useJourneyPhase.ts`
- `mos/frontend/src/pages/workflows/WorkflowDetailPage.tsx`

Current gap:

- App theme is restrained, but onboarding is still card-heavy admin setup.
- Design-system page manages funnel CSS variables well, but does not manage first-run brand experience assets/tokens.
- Workflow status exists, but onboarding does not turn it into a guided setup theatre.

## Goal -> Problem -> Diagnosis -> Design -> Doing

Goal: Make MOS first-run setup feel like a premium guided operator while preserving real Marketi workflows.

Problem: Current onboarding feels like a form. Current design-system coverage does not define the grammar for premium first-run states.

Diagnosis: Backend payload requirements leak into the UI because there is no dedicated first-run design layer.

Design: Add app-level experience tokens and reusable first-run components before replacing onboarding screens.

Doing: Ship in two implementation phases.

## Phase 1: Design System Foundation

### What We Are Porting From FernDesk

Port the design grammar, not FernDesk's literal identity.

- Port: near-white task canvas, editorial serif headings, low-chrome layout, black primary CTA, thin progress rail, compact input stack, app-chip grid, real work-status checklist, review/change states, blur-backed publish modal.
- Adapt: FernDesk's right-side visual weight becomes a useful Marketi context panel: setup preview, source checklist, generated-output preview, and workflow state.
- Reject: decorative right-side media, extra explanatory cards, dashboard-card mosaics, gradient orb backgrounds, big SaaS hero copy, fake animated progress, and decorative icons that do not map to state.

### Video-Derived Palette Targets

These are approximate samples from `proof_pack/design-system-ferndesk-2026-05-20/source/video-color-samples.json`. Use them as visual targets, not exact imported brand ownership.

| Role | FernDesk sample | Marketi token target | Why |
|---|---:|---|---|
| Task canvas | `#FDFDFC` | `--first-run-bg: #FDFDFC` | Clean white space makes the form feel guided instead of admin-heavy. |
| Editorial/app surface | `#F6F6F6` | `--first-run-surface-subtle: #F6F6F6` | Gives review/work surfaces a quiet paper feel. |
| Sidebar/chrome | `#ECECEC` | `--first-run-chrome: #ECECEC` | Softens app shell without turning it beige. |
| Warm status banner | `#EFE6D5` | `--first-run-callout-bg: #EFE6D5` | Useful for trial/setup notices and non-error guidance. |
| Primary CTA | `#151411` | `--first-run-action: #151411` | Fern's strongest move. One black button anchors every screen. |
| CTA text | inferred | `--first-run-action-fg: #FFFFFF` | Maintains contrast and command clarity. |
| Border | proposed | `--first-run-border: rgba(21, 20, 17, 0.12)` | Keeps borders visible but not boxy. |
| Muted copy | proposed | `--first-run-muted: rgba(21, 20, 17, 0.58)` | Matches Fern's quiet helper text without going low contrast. |
| Focus ring | proposed | `--first-run-focus: rgba(21, 20, 17, 0.32)` | Keeps keyboard focus clear without colored chrome. |

Do not port FernDesk's decorative right-side palette into Marketi. Those colors do not belong to the experience system we want.

Context-panel tokens replace the removed decorative media system:

- `--first-run-context-bg: #F6F6F6`
- `--first-run-context-border: rgba(21, 20, 17, 0.10)`
- `--first-run-context-muted: rgba(21, 20, 17, 0.50)`
- `--first-run-context-strong: #151411`
- `--first-run-context-callout: #EFE6D5`

Status colors stay functional and muted. They should not become the brand palette:

- `--change-new-fg`: muted green for generated/new items.
- `--change-updated-fg`: warm amber for modified items.
- `--change-deleted-fg`: muted rose for removed/rejected items.
- `--change-blocked-fg`: neutral gray for missing source or blocked jobs.

### Typography Changes

Current MOS already has the right raw materials: `DM Sans` and `Libre Baskerville` in `theme.css`. Do not add a new font dependency unless implementation proves the current serif fails.

Change usage:

- Use serif only for first-run display headings and review article titles.
- Use sans for body, labels, inputs, nav, chips, and buttons.
- Add explicit first-run type tokens:
  - `--first-run-title-font: var(--font-serif)`
  - `--first-run-title-size: clamp(1.65rem, 2.4vw, 2.15rem)`
  - `--first-run-title-line: 1.14`
  - `--first-run-body-size: 0.9375rem`
  - `--first-run-body-line: 1.55`
  - `--first-run-label-size: 0.75rem`
  - `--first-run-micro-size: 0.6875rem`

Why: FernDesk feels premium because the headline has editorial weight while everything else stays utilitarian. Our current onboarding uses mostly admin typography, so all text competes at the same level.

### Layout + Geometry Changes

Add tokens:

- `--first-run-content-max: 480px`
- `--first-run-form-max: 390px`
- `--first-run-context-width: clamp(360px, 34vw, 520px)`
- `--first-run-rail-height: 2px`
- `--first-run-control-height: 44px`
- `--first-run-cta-height: 52px`
- `--first-run-radius: 6px`
- `--first-run-modal-radius: 8px`
- `--first-run-shadow-modal: 0 24px 80px rgba(21, 20, 17, 0.18)`
- `--first-run-backdrop: rgba(246, 246, 246, 0.72)`

Rules:

- Desktop shell is full-height split: left task column, right persistent context panel.
- Left content is centered vertically with a max-width, not wrapped in a card.
- Mobile moves context below the task or into a collapsible review/status block. Required controls stay above it.
- Primary CTA is full width inside the form column.
- Progress is a thin rail at the top, not a pill/stepper row.
- Cards are allowed only for repeated review items, dialogs, and generated-change previews.

Why: Current onboarding has a card inside a grid inside a page shell. FernDesk removes that friction: one canvas, one task, one action.

### Component Contract

Expected files:

- `mos/frontend/src/styles/theme.css`
- `mos/frontend/src/styles/design-system.css`
- `mos/frontend/src/components/ui/button.tsx`
- `mos/frontend/src/components/ui/progress.tsx`
- `mos/frontend/src/components/ui/badge.tsx`
- `mos/frontend/src/components/onboarding/FirstRunShell.tsx`
- `mos/frontend/src/components/onboarding/ContextPreviewPanel.tsx`
- `mos/frontend/src/components/onboarding/OnboardingProgressRail.tsx`
- `mos/frontend/src/components/onboarding/ChoiceList.tsx`
- `mos/frontend/src/components/onboarding/SetupChecklist.tsx`
- `mos/frontend/src/components/onboarding/IntegrationPillGrid.tsx`
- `mos/frontend/src/components/onboarding/AgentWorkLog.tsx`
- `mos/frontend/src/components/onboarding/ReviewChangesPanel.tsx`
- `mos/frontend/src/components/onboarding/PublishProgressDialog.tsx`
- `mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx`

Component changes:

- `FirstRunShell`: owns split layout, content width, mobile collapse, context slot, and top rail slot. This prevents each onboarding screen from inventing layout.
- `ContextPreviewPanel`: renders useful setup context only: source checklist, workflow state, generated outputs, selected product/workspace summary, and next-step blockers. No decorative media.
- `OnboardingProgressRail`: thin deterministic progress rail. Takes current step and total steps. No fake progress.
- `ChoiceList`: Fern-style row choices with title, supporting text, selected state, disabled/blocked state, and optional icon.
- `SetupChecklist`: maps real workflow states to configured/learning/created/blocked rows.
- `IntegrationPillGrid`: chip grid for real supported source types only. Disabled chips explain why they are unavailable.
- `AgentWorkLog`: compact log stream for real workflow events. No synthetic task history.
- `ReviewChangesPanel`: added/updated/deleted/missing/blocked review states for generated outputs.
- `PublishProgressDialog`: blur-backed modal with restrained spinner and one status line for blocking actions.

### Design-System Page Changes

`BrandDesignSystemPage` should stop making JSON the main interface. JSON stays as advanced mode.

Add preview/control sections:

- Brand mark: default logo and dark-surface logo only.
- Palette: app canvas, chrome, action, callout, context panel, review status colors.
- Typography: display serif preview, body preview, label/micro preview.
- Controls: CTA, input, select, choice row, integration chip.
- First-run preview: mini split onboarding shell with a live context panel using current tokens.
- Work-state preview: setup checklist, review changes, publish modal.

Why: If design-system editing only exposes CSS variables, every later page still requires taste decisions. The design system should make the desired experience obvious before onboarding is touched.

Acceptance:

- New tokens support display/body/mono text, black CTA, secondary ghost CTA, progress rail, context panel, setup checklist, change-review states, and publish modal.
- Components are reusable and not hardcoded only to workspace onboarding.
- `BrandDesignSystemPage` exposes structured previews for palette, type, CTA, logo, context panel, and workflow states; raw JSON remains available as advanced editing.
- No fake brand data, fake proof, fake integration state, or fake job status.
- Visual result avoids nested cards and generic SaaS dashboard mosaic.

## Phase 2: Onboarding Rebuild

Expected files:

- `mos/frontend/src/pages/workspaces/WorkspaceOnboardingPage.tsx`
- `mos/frontend/src/components/clients/OnboardingWizard.tsx`
- `mos/frontend/src/app/AppShell.tsx`
- `mos/frontend/src/hooks/useJourneyPhase.ts`
- `mos/frontend/src/pages/workflows/WorkflowDetailPage.tsx`
- new or updated tests under `mos/frontend/src/components/clients/` and `mos/frontend/src/pages/workspaces/`

Target flow:

1. Welcome / intent: "What are we building first?" with choice rows.
2. Brand source: URL, store, docs, or manual brand summary.
3. Product / offer: one focused product screen, not a dense product editor card.
4. Sources / integrations: Shopify, Meta, PostHog, assets, competitors, and docs only where the app already supports them; missing sources show clean blocked states.
5. Setup theatre: real workflow status from onboarding run, shown as checklist/log timeline.
6. Review workspace: generated brand/product/research outputs with added/updated/missing/blocked states.
7. Launch next step: start strategy workflow or continue to workspace overview based on real backend state.

Acceptance:

- First viewport is the actual onboarding experience, not explanatory panels.
- Each step has one primary action.
- Progress state is visible without reading helper copy.
- Mobile keeps context subordinate and never hides required controls.
- Submitting still creates client/product/profile records and starts onboarding exactly through existing authorized APIs.
- Backend failures surface clean errors. No silent fallbacks.

## Verification Commands

Run during implementation:

```bash
cd /Users/aldrinclement/Documents/programming/marketi/mos/frontend && npm run check:semantic-ui
cd /Users/aldrinclement/Documents/programming/marketi/mos/frontend && npm test -- --runInBand
cd /Users/aldrinclement/Documents/programming/marketi/mos/frontend && npm run build
cd /Users/aldrinclement/Documents/programming/marketi && /Users/aldrinclement/.codex/bin/capturectl verify proof_pack/design-system-ferndesk-2026-05-20/source/source_manifest.json
```

Use authenticated preview validation for MOS after implementation:

```bash
cd /Users/aldrinclement/Documents/programming/marketi/mos/frontend && node scripts/validate-site-preview.mjs
```

## Speed Map

parallelizable: yes

Parallelization map:

- Lane 1: design-system primitives and tokens.
- Lane 2: onboarding UX rewrite using only Lane 1 public components after the component contract is stable.
- Lane 3: read-only verifier for tests, accessibility, visual screenshots, and no-fake-data/provenance checks.

Expected speed gain: medium. Design-system and verification can run in parallel; onboarding depends on component contracts.

Token spend justification: worth it during `Ship the plan` because visual implementation and verification are separable.

Write ownership:

- Lane 1 owns `styles/`, `components/ui/`, `components/onboarding/`.
- Lane 2 owns onboarding pages/components.
- Lane 3 owns proof artifacts and test logs only.

Fan-in plan: main thread integrates component API mismatches, runs final tests, and verifies screenshots.

Validation owner: main thread.

Meta-tooling opportunity: add a reusable onboarding visual QA script that captures desktop/mobile screenshots for first-run flows.

## Preemptive Failure Modes

- Shallow diagnosis: repainting the wizard without adding primitives.
- Symptom-addressing plan: changing colors/fonts while keeping dense field flow.
- Willpower plan: relying on future per-page taste instead of shared components.
- Perfect-day plan: assuming all brand sources and integrations are present.
- Missing metrics: not checking completion clarity, status visibility, and no-fake-data constraints.
- Overengineered plan: building a full theme builder before the first-run primitives are proven.
- Scope creep: dragging campaign, funnel editor, and unrelated dashboard redesign into this pass.

## Ship Phrase

Ship the plan.
