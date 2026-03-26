# Store Templates UI — Refactor Plan

## What's wrong today

### 1. Two pages doing the same thing

`StoreTemplatesPage.tsx` (850+ lines) and `TemplateGalleryPage.tsx` (806 lines) both render template browsing, Medusa config, variant creation, and governance UI. They copy-paste the same helpers and inline components:

- `MedusaConnectionCard` (~180 lines of forms/state, duplicated in both files)
- `MedusaStatusBadge` (~30 lines, duplicated)
- `RequirementRow` (~25 lines, duplicated)
- `GovernancePanel` (~70 lines, inlined in TemplateGalleryPage)
- Helpers: `formatPageType()`, `formatSlot()`, `requirementTone()`, `readQueryError()`, `resolveFamilyDefaults()`, `isImportActiveStatus()`, `formatImportModelLabel()` — all duplicated

The legacy page has 20+ `useState` calls managing templates, imports, conversion forms, variant creation, and save state all in one component.

### 2. Site Imports hidden behind a separate nav entry

Templates live at `/workspaces/store-templates`, but imports live at `/workspaces/imports` with their own sidebar item. These are parts of the same workflow — "get a template and use it" — but users have to know to click a completely different menu item to import from a URL.

### 3. The import wizard has too many steps

Current flow: **Create → Capture → Review → Configure → Approve → Publish** (6 steps, 7 pages including the list).

- **Capture** is a loading screen. It polls the backend and shows a spinner/activity log until the import finishes. This is a loading state, not a step.
- **Configure** is a small form (name + family + page type). It could be a sidebar or section within Review.
- **Approve** and **Publish** are variant lifecycle actions, not import steps. They belong on a variant detail view.

### 4. ImportWizardContext doesn't survive navigation

The context holds ~6 strings (`selectedSectionIds`, `variantName`, `family`, `pageType`, `reviewNotes`, `selectedVariantId`). It resets on page refresh because each route creates a fresh provider. The fields are simple enough for URL search params or local component state.

---

## Reference: Screenshot-to-Code patterns

The local `screenshot-to-code/` repo has a clean UX for a similar workflow (input → processing → result). Key patterns to adopt:

### Pattern 1 — State machine, not page navigation

STC uses an `AppState` enum (`INITIAL → CODING → CODE_READY`) rendered by a single `App.tsx`. The same page smoothly transitions between states instead of navigating to separate routes. The layout shifts: `INITIAL` shows the input pane full-width; `CODING`/`CODE_READY` switches to a sidebar + preview split.

**Apply to imports:** The import flow should be a single route (`/store-templates/import/:id`) with an internal state machine:

```
INPUTTING  →  PROCESSING  →  REVIEWING  →  SAVING
(URL form)    (activity)     (sections)    (name + family)
```

No page navigation between these states. The URL stays the same, the UI transitions smoothly. This eliminates the ImportWizardContext problem entirely — all state is local to one component tree.

### Pattern 2 — Sidebar + preview split layout

STC's layout during `CODING`/`CODE_READY` is:

```
┌──────────┬─────────────────────────────────┐
│ Sidebar  │         Preview Pane            │
│ (28rem)  │    (remaining width)            │
│          │                                 │
│ Activity │  Live preview / screenshot      │
│ Events   │  Desktop / Mobile toggle        │
│          │                                 │
│ Edit box │  Version navigation             │
└──────────┴─────────────────────────────────┘
```

**Apply to import review:** Instead of separate Capture and Review pages, show the screenshot/section overlay on the right and the activity log + controls on the left. When processing finishes, the left pane transitions from activity events to section selection controls. The preview stays visible throughout.

### Pattern 3 — Inline processing visibility

STC's `AgentActivity` component shows a timeline of events while code generates:
- Thinking events with expandable content and duration
- Tool execution events with icons and status
- `WorkingPulse` shows elapsed time with an animated gradient background
- Everything streams in real-time, auto-scrolling to latest

**Apply to imports:** Our `ImportActivityPanel` already does this well. The change is where it appears — not on its own page, but in the sidebar of the review layout, visible alongside the growing screenshot preview.

### Pattern 4 — Unified input with tabs

STC's `UnifiedInputPane` presents 4 input methods (Upload, URL, Text, Import) as tabs in a single component. Each tab has its own submit action but shares the output config.

**Apply to the main page:** Our "Gallery" and "Import" tabs follow this same pattern — two ways to get a template. The tabbed approach is correct.

### Pattern 5 — Settings out of the way

STC puts API keys and theme config in a dedicated `SettingsTab` accessed from the icon strip. The main creation flow has only one config option inline (stack selector as a simple dropdown).

**Apply to Medusa config:** Move `MedusaConnectionCard` out of the template browsing flow. Put it behind a settings icon or in a collapsible section at the bottom of the page. Don't make users scroll past Medusa forms to see templates.

---

## Proposed structure

### One page, three tabs

Collapse everything under `/workspaces/store-templates`:

| Tab | What it shows | Source today |
|-----|---------------|-------------|
| **Gallery** | Browse ready-made template families, preview bindings, create drafts | `TemplateGalleryPage` |
| **Import** | Start a new import, see in-progress/completed imports | `ImportsListPage` + `ImportCreatePage` |
| **My Variants** | All drafted/approved variants for this workspace, governance, publish | Legacy `StoreTemplatesPage` variant list + `ImportApprovePage` |

Remove "Site Imports" from the sidebar entirely. Medusa config moves to a settings section (gear icon in the page header, or a collapsible panel at the bottom — not inline with the template cards).

### Import flow: single-page state machine (inspired by STC)

Instead of 3 separate route pages, the import detail view is **one route with internal states**:

```
/workspaces/store-templates/import/:id
```

The component manages an internal flow:

```
┌─────────────────────────────────────────────────────────────┐
│  State: PROCESSING                                          │
│  ┌──────────────┬──────────────────────────────────────┐    │
│  │  Activity     │  Screenshot preview                  │    │
│  │  timeline     │  (grows as capture runs)             │    │
│  │              │                                      │    │
│  │  Events...   │  ┌──────────────────────────┐        │    │
│  │  Thinking... │  │  Live screenshot          │        │    │
│  │  Capturing.. │  │  (polled from backend)    │        │    │
│  │              │  └──────────────────────────┘        │    │
│  │  [Cancel]    │                                      │    │
│  └──────────────┴──────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  State: REVIEWING                                           │
│  ┌──────────────┬──────────────────────────────────────┐    │
│  │  Sections     │  Screenshot with overlays            │    │
│  │  ☑ Hero      │  (bounding boxes on sections)        │    │
│  │  ☑ Nav       │                                      │    │
│  │  ☐ Footer    │  Desktop / Mobile toggle             │    │
│  │              │                                      │    │
│  │  Theme:      │                                      │    │
│  │  Colors...   │                                      │    │
│  │  [Continue]  │                                      │    │
│  └──────────────┴──────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  State: SAVING                                              │
│  ┌──────────────┬──────────────────────────────────────┐    │
│  │  Variant name │  Synthesis preview                   │    │
│  │  [________]  │  (block coverage, mappings)          │    │
│  │              │                                      │    │
│  │  Family:     │  Screenshot (read-only)              │    │
│  │  [dropdown]  │                                      │    │
│  │              │                                      │    │
│  │  Page type:  │                                      │    │
│  │  [dropdown]  │                                      │    │
│  │              │                                      │    │
│  │  [Save]      │                                      │    │
│  └──────────────┴──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

The state transitions are driven by the import's backend status:
- `queued/capturing/generating/adapting/running` → **PROCESSING** (show activity)
- `completed` + user hasn't saved → **REVIEWING** (show sections)
- User clicks "Continue" → **SAVING** (show config form)
- `failed` → **ERROR** (show error + retry)

No `ImportWizardContext` needed. All state is local to this one component tree. If the user refreshes, the component reads the import status from the API and renders the correct state.

### Start-new-import flow

The "new import" input form lives inline at the top of the Import tab (like STC's input pane). Submitting it creates the import via API and navigates to `/store-templates/import/:id`, which immediately enters the PROCESSING state.

No separate `/import/new` route needed — the form is right there in the tab.

---

## File plan

### Extract shared components (new files)

| Component | Lines | What it does |
|-----------|-------|-------------|
| `components/storefront/MedusaConnectionCard.tsx` | ~180 | Connection config form, test button, create-variant form. Props: `clientId`, `productId`, `onVariantCreated` |
| `components/storefront/MedusaStatusBadge.tsx` | ~30 | Status pill (connected / error / not tested / not configured) |
| `components/storefront/RequirementRow.tsx` | ~25 | Binding requirement row with status badge and icon |
| `components/storefront/GovernancePanel.tsx` | ~80 | Governance report display with approve action |
| `lib/storefront-utils.ts` | ~60 | `formatPageType()`, `formatSlot()`, `requirementTone()`, `readQueryError()`, `resolveFamilyDefaults()`, `isImportActiveStatus()`, `formatImportModelLabel()`, `readProvenanceString()` |

### Restructure pages

```
pages/workspaces/
  StoreTemplatesPage.tsx              ← NEW: thin shell with tabs + header
  tabs/
    TemplateGalleryTab.tsx            ← from TemplateGalleryPage (minus duplicated helpers)
    ImportTab.tsx                     ← import list + inline "new import" form at top
    MyVariantsTab.tsx                 ← variant list + detail + governance from legacy page
  imports/
    ImportDetailPage.tsx              ← NEW: single-page state machine (PROCESSING → REVIEWING → SAVING)
```

### Delete

| File | Reason |
|------|--------|
| `pages/workspaces/StoreTemplatesPage.tsx` (current) | Replaced by new tabbed shell |
| `pages/workspaces/TemplateGalleryPage.tsx` | Content moves to `TemplateGalleryTab` |
| `pages/workspaces/imports/ImportsListPage.tsx` | Content moves to `ImportTab` |
| `pages/workspaces/imports/ImportCreatePage.tsx` | Form moves inline into `ImportTab` |
| `pages/workspaces/imports/ImportCapturePage.tsx` | Merged into `ImportDetailPage` PROCESSING state |
| `pages/workspaces/imports/ImportReviewPage.tsx` | Merged into `ImportDetailPage` REVIEWING state |
| `pages/workspaces/imports/ImportConfigurePage.tsx` | Merged into `ImportDetailPage` SAVING state |
| `pages/workspaces/imports/ImportApprovePage.tsx` | Moved to `MyVariantsTab` detail view |
| `pages/workspaces/imports/ImportPublishPage.tsx` | Action button on variant detail |
| `contexts/ImportWizardContext.tsx` | No longer needed — state is local to `ImportDetailPage` |

### Update routing

```tsx
// Before: 11 routes, 2 nav entries
/workspaces/store-templates              → TemplateGalleryPage
/workspaces/store-templates/legacy       → StoreTemplatesPage
/workspaces/imports                      → ImportsListPage
/workspaces/imports/new                  → ImportCreatePage
/workspaces/imports/:id/capture          → ImportCapturePage
/workspaces/imports/:id/review           → ImportReviewPage
/workspaces/imports/:id/configure        → ImportConfigurePage
/workspaces/imports/:id/approve          → ImportApprovePage
/workspaces/imports/:id/publish          → ImportPublishPage

// After: 3 routes, 1 nav entry
/workspaces/store-templates              → StoreTemplatesPage (tabbed: Gallery / Import / My Variants)
/workspaces/store-templates/import/:id   → ImportDetailPage (state machine)
/workspaces/store-templates/variant/:id  → variant detail (governance + publish)
```

Update `AppShell.tsx` `WORKSPACE_NAV` to remove the "Site Imports" entry. Add redirects from old `/workspaces/imports/*` URLs.

---

## Execution order

Each step is independently shippable and testable.

### Step 1 — Extract shared components

Pull duplicated code into shared files. **Zero behavior change.** Both pages import from the new locations instead of defining inline.

Files created:
- `components/storefront/MedusaConnectionCard.tsx`
- `components/storefront/MedusaStatusBadge.tsx`
- `components/storefront/RequirementRow.tsx`
- `components/storefront/GovernancePanel.tsx`
- `lib/storefront-utils.ts`

### Step 2 — Build the tabbed page shell

Create the new `StoreTemplatesPage.tsx` with three tabs. Each tab initially just renders the existing page content (TemplateGalleryPage → Gallery, ImportsListPage → Import, variant list from legacy → My Variants). Inline the new-import form at the top of the Import tab.

### Step 3 — Build ImportDetailPage as a state machine

Create `ImportDetailPage.tsx` with sidebar + preview split layout:
- **PROCESSING**: Activity timeline on the left, screenshot preview on the right (merge current Capture + Review loading states)
- **REVIEWING**: Section selection on the left, screenshot with overlays on the right
- **SAVING**: Config form on the left, synthesis preview on the right
- **ERROR**: Error message + retry

State is derived from the import's backend status + local user actions. No wizard context.

Reuse `ImportActivityPanel` and `StorefrontVisualReviewPanel` as-is.

### Step 4 — Move Approve/Publish to variant detail

Add governance + approve/publish actions to the My Variants tab (variant detail view or `/store-templates/variant/:id`). Delete `ImportApprovePage` and `ImportPublishPage`.

### Step 5 — Update routes and nav

Wire up new route structure:
- Remove "Site Imports" nav entry from `AppShell.tsx`
- Add redirect routes from old `/workspaces/imports/*` URLs to new paths
- Delete `ImportWizardContext`

### Step 6 — Delete legacy files

Remove old pages: `StoreTemplatesPage` (legacy), `TemplateGalleryPage`, `ImportsListPage`, and all deleted import wizard pages (`ImportCreatePage`, `ImportCapturePage`, `ImportReviewPage`, `ImportConfigurePage`, `ImportApprovePage`, `ImportPublishPage`).

---

## What stays the same

- **API layer** (`api/storefrontTemplates.ts`) — no backend changes
- **Type definitions** (`types/storefrontTemplates.ts`, `types/importActivity.ts`)
- **Well-extracted components** — `ImportActivityPanel`, `StorefrontVisualReviewPanel`, `StepperBar`
- **Commerce components** — `StarterStorefrontBlocks`, `CommerceBlocks`
- **All backend endpoints and data models**
