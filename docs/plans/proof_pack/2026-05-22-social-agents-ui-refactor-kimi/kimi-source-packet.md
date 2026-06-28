# MOS Social Agents UI Refactor Source Packet

## Files Provided

- `mos/frontend/src/pages/workspaces/SocialAgentsPage.tsx`
- `mos/frontend/src/pages/workspaces/SocialAgentsPage.test.tsx`
- `mos/frontend/src/api/socialAgents.ts`
- `mos/frontend/src/types/socialAgents.ts`
- `mos/frontend/src/app/AppShell.tsx`
- `mos/frontend/src/app/routes.tsx`

## Current Page Shape

- Route/nav: `Social Agents` is in `EXECUTION_NAV` beside Campaigns, Analytics, and Postiz.
- Page header: title `Social Agents`, description `Connected social and TikTok carousel workflows for {workspace.name}.`, secondary `Postiz` link.
- Top status strip: three callouts for Postiz readiness, pending proposals, and growth loop counts.
- Main tabs:
  - `TikTok Carousel`
  - `Connected Social`
  - `Action Queue`
- TikTok tab layout:
  - left column: Program, Conversion Source, Experiment And Variant, Postiz Handoff.
  - right sidebar: Selected Loop, Latest Variant.
- Current UI implementation uses many `rounded-xl border bg-surface p-4` containers, nested card-like regions, and dense forms.
- Current carousel preview exists but is gradient placeholder art, not final generated media.

## Current Workflow Behavior

- Program creation uses `platformKey: "tiktok"`, `formatKey: "tiktok_carousel"`, `authorityMode: "approval_required"`, and `settings: { postizSystemOfRecord: true }`.
- Conversion source creation sends provider/name/goalEvents/config/credentialsMetadata.
- Experiment creation sends name/hypothesis/hookFamily/ctaFamily/audience.
- Variant creation sends six slides derived from `LARRY_SLIDE_FORMULA`, `basePrompt`, and overlay text split by `---`.
- Variant approval calls `approveVariant`.
- Postiz handoff is disabled unless selected variant is approved and media URL count equals selected variant `slideCount`.
- Handoff creates a Postiz proposal, not a direct publish.
- Action queue approves pending proposals.

## Existing Test Coverage

- Renders Social Agents workbench.
- Verifies Postiz handoff stays disabled until six media URLs are entered.
- Verifies handoff payload contains draft post type, selected channel, six media URLs, and Postiz payload fields.
- Renders empty state without workspace.

## Constraints

- Plan only. Do not implement.
- Do not change configured LLM/AI model behavior.
- Do not add fallbacks without explicit authorization.
- Do not fabricate data.
- Keep Postiz as posting system of record; MOS creates approvals/handoffs.
- Preserve existing API contracts unless the plan explicitly calls out a necessary backend/API follow-up.
- Optimize output for fast human review.

## Planning Ask

Create a clean UI refactor plan for the MOS Social Agents tab. Root issue: the page has weak workflow hierarchy and looks like a stack of forms/tables rather than an operator workbench.

Include:

- decision
- root-cause diagnosis
- target information architecture
- component split
- implementation phases
- acceptance checks
- tests/validation
- risks
- explicit non-goals
