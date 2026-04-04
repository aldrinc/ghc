# Site Import UI Redesign Plan

## Problem Statement

The current site import experience is crammed into a single 2,500-line `StoreTemplatesPage.tsx` with two tabs ("Template Families" and "Import Reference Site") that attempt to surface every concern — URL entry, import history, live generation activity, section review, theme extraction, synthesis analysis, variant conversion, mutation presets, governance checks, approval, and "save as site" — in a flat two-column layout with no clear progression. The result is:

- **No sense of where you are.** There's no stepper, wizard, or breadcrumb. Users must scroll across 10+ stacked cards to find the action they need.
- **Everything is visible at once.** Normalized sections, synthesis block coverage, generator activity, governance, and the convert form all render simultaneously in the detail pane — even when half of them are irrelevant to the current stage.
- **State is fragile.** 20+ `useState` hooks drive the entire flow. Switching tabs, changing imports, or hitting a browser refresh loses all intermediate progress. There's no persistence or URL-driven state.
- **Templates and imports are co-located but barely related.** The "Template Families" tab and "Import Reference Site" tab serve different user goals and different data models, yet they share a page, a URL, and sidebar real estate (Medusa config, binding readiness).
- **Review is blind.** The user picks normalized sections from a text list with confidence percentages but has no visual overlay, no side-by-side comparison with the original screenshot, and no preview of what the final page will look like.
- **Approval is buried.** The governance panel (blockers, asset validation, style audit) sits at the bottom of a long scroll. There's no summary view or gated gate that prevents publishing until issues are resolved.

---

## Proposed Architecture: Step-Based Import Wizard

Replace the monolithic two-tab layout with a dedicated **multi-step import wizard** accessible from a clean imports list page. Each step is its own route, its own component, and its own focused concern.

### New Route Structure

```
/workspaces/store-templates              → TemplateGalleryPage (browse built-in families)
/workspaces/imports                      → ImportsListPage (all imports, filterable)
/workspaces/imports/new                  → Step 1: ImportCreatePage
/workspaces/imports/:importId/capture    → Step 2: ImportCapturePage
/workspaces/imports/:importId/review     → Step 3: ImportReviewPage
/workspaces/imports/:importId/configure  → Step 4: ImportConfigurePage
/workspaces/imports/:importId/approve    → Step 5: ImportApprovePage
/workspaces/imports/:importId/publish    → Step 6: ImportPublishPage
```

Each step is a focused page. The import ID is in the URL, so refreshing, sharing links, and deep-linking to any stage all work.

---

## Step-by-Step Breakdown

### Step 0: Imports List (`/workspaces/imports`)

**Purpose:** Central hub showing all imports for this workspace.

| Element | Description |
|---------|-------------|
| **Header** | "Site Imports" title, workspace badge, "New Import" primary button |
| **Filter bar** | Status pills: All / In Progress / Completed / Failed / Saved |
| **Import cards** | Each card shows: source URL (with favicon), title, status badge, suggested family, created date, page count. Click navigates to the appropriate step based on status. |
| **Quick actions** | "Resume" button on in-progress imports, "View Site" link on saved imports |
| **Empty state** | Illustration + "Import your first reference site" CTA |

**Key improvement:** Replaces the cramped "Import history" card currently buried inside the imports tab. Each import is a first-class object with its own detail flow.

---

### Step 1: Create Import (`/workspaces/imports/new`)

**Purpose:** Enter a URL and kick off the import pipeline.

| Element | Description |
|---------|-------------|
| **URL input** | Large, prominent text field with URL validation. Placeholder: "Paste a live website URL" |
| **URL preview** | On blur/paste, fetch favicon and page title as a preview card |
| **Page type selector** | Visual radio cards (Home, Product Detail, Category, Cart, Checkout) instead of a dropdown |
| **Advanced options** | Collapsible section: site family hint, model slot overrides |
| **Start button** | "Start Import" — on click, creates the import and redirects to Step 2 |

**Key improvement:** Focused single-action page. No distracting import history or template browser. The page type hint uses visual cards instead of a generic `<Select>`.

---

### Step 2: Capture & Generate (`/workspaces/imports/:importId/capture`)

**Purpose:** Show real-time progress while the backend captures the site and generates code.

| Element | Description |
|---------|-------------|
| **Stepper** | Horizontal stepper at top: `Create → Capture → Review → Configure → Approve → Publish`. Step 2 highlighted. |
| **Source preview** | Left column: original desktop + mobile screenshots as they arrive (live) |
| **Activity feed** | Right column: the existing `ImportActivityPanel` — thinking steps, tool calls, variant progress. Polished with a timeline rail design. |
| **Status banner** | Sticky top bar: "Capturing site... (12s)" or "Generating variants... (1m 34s)" with animated progress |
| **Auto-advance** | When status becomes `completed`, show a "Continue to Review" button with a brief celebration state (checkmark animation) |
| **Error recovery** | If status becomes `failed`, show error details inline with "Retry Import" and "Start Over" buttons |

**Key improvement:** Users see progress in real time with clear expectations. The auto-advance eliminates the need to manually figure out when generation is done. The current UI has no progress indication beyond a badge saying "generating".

---

### Step 3: Review Import (`/workspaces/imports/:importId/review`)

**Purpose:** Let the user visually inspect what was imported and select which sections to keep.

This is the most important step and the biggest UX upgrade.

#### Layout: Split-Screen

```
┌──────────────────────────────────────────────────────────────┐
│  Stepper: Create → Capture → [Review] → Configure → ...     │
├─────────────────────────────┬────────────────────────────────┤
│                             │                                │
│   Original Screenshot       │   Section Inspector            │
│   (scrollable, with         │                                │
│    bounding box overlays    │   ┌─────────────────────────┐  │
│    for each section)        │   │ Hero Section     ✓ 94%  │  │
│                             │   ├─────────────────────────┤  │
│                             │   │ Product Gallery   ✓ 87% │  │
│                             │   ├─────────────────────────┤  │
│                             │   │ Testimonials      ○ 72% │  │
│                             │   ├─────────────────────────┤  │
│                             │   │ FAQ Accordion     ○ 65% │  │
│                             │   └─────────────────────────┘  │
│                             │                                │
│                             │   Theme Summary                │
│                             │   ┌─────────────────────────┐  │
│                             │   │ ■ ■ ■ ■  Palette       │  │
│                             │   │ Aa Bb    Fonts          │  │
│                             │   │ 16/24px  Spacing        │  │
│                             │   └─────────────────────────┘  │
│                             │                                │
├─────────────────────────────┴────────────────────────────────┤
│               [Back]                    [Continue →]         │
└──────────────────────────────────────────────────────────────┘
```

| Element | Description |
|---------|-------------|
| **Screenshot viewer** | Zoomable/pannable original screenshot with colored bounding-box overlays for each detected section. Hovering a section in the list highlights it on the screenshot, and vice versa. |
| **Section checklist** | Right panel: each normalized section as a selectable card showing section type, confidence %, key text snippet, and a thumbnail crop from the screenshot. Toggle to include/exclude. Sections above 80% confidence are pre-selected. |
| **Select All / None** | Bulk toggle buttons at the top of the section list |
| **Theme summary** | Compact card showing extracted palette swatches, font families, spacing scale, and CTA style — pulled from `themeCandidate` |
| **Adapted pages preview** | Collapsible section at the bottom showing the adapted page set: page type, slug, link count, puck data availability |
| **Page tab strip** | If multiple adapted pages exist, allow switching between them to see per-page sections |

**Key improvement:** The current UI shows sections as plain text rows. This redesign ties sections visually to the screenshot so users can see exactly what they're selecting. The theme summary is promoted from a hidden card to a clear callout.

---

### Step 4: Configure Variant (`/workspaces/imports/:importId/configure`)

**Purpose:** Choose how the import maps into the Marketi template system, and optionally apply mutation presets.

| Element | Description |
|---------|-------------|
| **Variant name** | Text input, pre-filled with `{source hostname} — {page type}` |
| **Family selector** | Visual radio cards for supported families (Sales PDP, Pre-sales Listicle) with description and icon |
| **Page type selector** | Visual radio cards for supported page types |
| **Synthesis report** | Block coverage dashboard (the 4-stat grid: coverage score, exact, partial, missing) with the block mapping table below it |
| **Missing block requests** | Warning cards for blocks that don't map, with suggested actions |
| **Mutation presets** | Selectable preset cards (currently the `VariantMutationPanel`), shown only if the user has already converted once. Otherwise hidden. |
| **Review notes** | Optional textarea for internal notes |
| **Convert button** | "Create Variant Draft" — creates the `TemplateVariant` record |

**Key improvement:** The current UI mixes the convert form (name, family, page type) and the synthesis output in different cards scattered across the detail pane. This consolidates them into one purposeful step with clear cause-and-effect: "here's what you're configuring, and here's how it maps."

---

### Step 5: Approve (`/workspaces/imports/:importId/approve`)

**Purpose:** Governance gate — the user reviews all quality checks before publishing.

#### Layout: Checklist Dashboard

```
┌──────────────────────────────────────────────────────────────┐
│  Stepper: ... → Configure → [Approve] → Publish             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                  │
│  │ ● Asset Check    │  │ ○ Style Audit    │                  │
│  │   3/3 approved   │  │   1 warning      │                  │
│  └──────────────────┘  └──────────────────┘                  │
│  ┌──────────────────┐  ┌──────────────────┐                  │
│  │ ● Puck Structure │  │ ● Blockers       │                  │
│  │   Valid           │  │   0 blockers     │                  │
│  └──────────────────┘  └──────────────────┘                  │
│                                                              │
│  ─── Details ─────────────────────────────────────           │
│                                                              │
│  Asset References                                            │
│  ┌───────────────────────────────────────────────┐           │
│  │ hero-bg.jpg     ✓ approved    HeroBlock       │           │
│  │ product-1.png   ✓ approved    GalleryBlock    │           │
│  │ logo.svg        ⚠ pending     HeaderBlock     │           │
│  └───────────────────────────────────────────────┘           │
│                                                              │
│  Style Audit Findings                                        │
│  ┌───────────────────────────────────────────────┐           │
│  │ ✓ Contrast ratio 4.8:1 (AA pass)             │           │
│  │ ⚠ Button border-radius inconsistent           │           │
│  └───────────────────────────────────────────────┘           │
│                                                              │
│  Provenance Timeline                                         │
│  ┌───────────────────────────────────────────────┐           │
│  │ ● Imported — 2026-03-24 14:23                 │           │
│  │ ● Sections selected — 2026-03-24 14:25        │           │
│  │ ● Variant created — 2026-03-24 14:30          │           │
│  └───────────────────────────────────────────────┘           │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  [Back]                          [Approve for Publication →] │
│                                  (disabled if blockers > 0)  │
└──────────────────────────────────────────────────────────────┘
```

| Element | Description |
|---------|-------------|
| **Summary cards** | 4 status cards at top: Asset Check, Style Audit, Puck Structure, Blockers. Each shows pass/fail/warning count with color coding. |
| **Asset table** | Expandable table of all asset references with status, block type, and field path |
| **Style audit findings** | List of pass/fail items with contrast ratios and location info |
| **Puck data validation** | Errors and warnings from structure check |
| **Provenance timeline** | Vertical timeline of all provenance events with timestamps and actors |
| **Approve button** | Disabled when blockers > 0. Shows confirmation dialog before approving. |

**Key improvement:** The governance panel is currently buried at the bottom of a very long scroll. This makes it the primary focus of its own step. The summary cards at the top give an instant "health check" glance.

---

### Step 6: Publish / Save (`/workspaces/imports/:importId/publish`)

**Purpose:** Final step — save the approved import as a site and navigate to it.

| Element | Description |
|---------|-------------|
| **Success state** | Celebration UI: "Your site is ready!" with a checkmark animation |
| **Site name** | Editable text field, pre-filled from import title |
| **Description** | Optional description field |
| **Preview card** | Shows the final site details: family, entry page type, page count, variant status |
| **Save button** | "Create Site" — calls `save_site_import`, then shows the result |
| **Post-save actions** | "View Site" button → navigates to `SiteDetailPage`, "Import Another" → navigates to `/workspaces/imports/new`, "Edit Entry Page" → navigates to the page editor |

**Key improvement:** Currently the "Save as Site" form is one of many cards in the detail pane. Making it a dedicated final step provides a clear sense of completion and satisfying finish to the workflow.

---

## Shared Components

### StepperBar

Horizontal stepper component used across all steps. Shows step labels with status icons:
- Completed steps: green checkmark
- Current step: blue dot with label highlighted
- Future steps: gray dot
- Clicking a completed step navigates back to it

### ImportStatusBanner

Sticky banner at top of capture/review pages showing current import status, elapsed time, and error state. Replaces the scattered status badges.

### SectionOverlayViewer

Screenshot viewer with bounding-box overlays. Props:
- `screenshotUrl: string` — desktop or mobile screenshot
- `sections: NormalizedSection[]` — sections with bounding boxes
- `selectedIds: string[]` — which sections are selected
- `onToggle: (id: string) => void` — toggle callback
- `onHover: (id: string | null) => void` — hover callback

### ThemeSummaryCard

Compact card showing palette swatches, font families, and spacing. Used in both Step 3 (review) and Step 4 (configure).

### GovernanceSummaryCards

The 4 status summary cards from Step 5, extracted as a reusable component. Can also be used on the Imports List page to show a quick health indicator.

---

## State Management

### URL-Driven State

All import wizard state is derived from the URL:
- `importId` comes from the route param
- `step` comes from the route path
- Section selections, family, page type are query params or stored in a lightweight context scoped to the wizard

### Import Wizard Context

```ts
interface ImportWizardState {
  importId: string;
  selectedSectionIds: string[];
  variantName: string;
  family: string;
  pageType: string;
  reviewNotes: string;
}
```

A `React.createContext` provider wraps the wizard routes. State persists across steps via context, with the import ID as the cache key. If the user refreshes, we re-derive state from the API (import detail has `selectedSectionIds`, `resolvedFamily`, etc.).

### No More 20+ `useState` Hooks

The monolithic `StoreTemplatesPage` currently uses ~20 `useState` hooks. The wizard approach distributes these across 6 focused components, each with 2-4 hooks max.

---

## Component File Structure

```
src/
  pages/
    workspaces/
      TemplateGalleryPage.tsx      ← current "Template Families" tab, extracted
      imports/
        ImportsListPage.tsx        ← Step 0: list of all imports
        ImportCreatePage.tsx       ← Step 1: URL entry
        ImportCapturePage.tsx      ← Step 2: capture & generate progress
        ImportReviewPage.tsx       ← Step 3: visual section review
        ImportConfigurePage.tsx    ← Step 4: variant configuration
        ImportApprovePage.tsx      ← Step 5: governance gate
        ImportPublishPage.tsx      ← Step 6: save as site
  components/
    import/
      ImportActivityPanel.tsx      ← existing, kept as-is
      StepperBar.tsx               ← new shared stepper
      ImportStatusBanner.tsx       ← new status banner
      SectionOverlayViewer.tsx     ← new screenshot + bounding boxes
      ThemeSummaryCard.tsx         ← new extracted theme card
      SectionCard.tsx              ← new section selection card
    governance/
      GovernanceSummaryCards.tsx    ← new extracted summary cards
      AssetValidationTable.tsx     ← new asset table
      StyleAuditList.tsx           ← new style audit findings
      ProvenanceTimeline.tsx       ← new timeline component
    variants/
      VariantMutationPanel.tsx     ← existing, extracted from StoreTemplatesPage
      GovernancePanel.tsx          ← existing, extracted from StoreTemplatesPage
  contexts/
    ImportWizardContext.tsx         ← new wizard state context
```

---

## Migration Strategy

This is a **parallel build** — we don't delete `StoreTemplatesPage.tsx` until the new wizard is complete.

### Phase 1: Infrastructure (1-2 days)
1. Add new routes to `App.tsx`
2. Create `ImportWizardContext`
3. Build `StepperBar` component
4. Build `ImportsListPage` (data already available via `useSiteImports`)

### Phase 2: Core Steps (3-4 days)
5. Build `ImportCreatePage` (extract from existing import form)
6. Build `ImportCapturePage` (wrap existing `ImportActivityPanel`)
7. Build `ImportReviewPage` (the big UX lift — `SectionOverlayViewer` + section cards)
8. Build `ImportConfigurePage` (extract convert form + synthesis display)

### Phase 3: Governance & Publish (2-3 days)
9. Build `ImportApprovePage` (extract and redesign `GovernancePanel`)
10. Build `ImportPublishPage` (extract save-as-site form)
11. Build `TemplateGalleryPage` (extract the template families tab)

### Phase 4: Polish & Cutover (1-2 days)
12. Integrate visual review panel (`StorefrontVisualReviewPanel`) into Step 3
13. Add transition animations between steps
14. QA and fix edge cases (failed imports, re-imports, already-saved imports)
15. Update navigation links throughout the app
16. Remove old `StoreTemplatesPage.tsx`

---

## Summary of UX Wins

| Current Pain | New Solution |
|---|---|
| No sense of progress | Horizontal stepper with 6 clear stages |
| Everything visible at once | Each step shows only its relevant data |
| Lose state on refresh | URL-driven state with import ID in the path |
| Blind section selection | Visual overlay on screenshot with bounding boxes |
| Governance buried at bottom | Dedicated approval step with summary dashboard |
| No clear finish line | Publish step with celebration state and next actions |
| 2,500-line monolith | 6 focused page components, each 200-400 lines |
| Templates and imports mixed | Separate pages with separate routes |
| No deep-linking | Every step has its own URL |
| Manual "is it done yet?" checking | Auto-advance with progress banner |
