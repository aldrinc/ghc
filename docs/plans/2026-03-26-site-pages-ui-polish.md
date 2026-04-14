# Site Pages UI Polish Refactor

**Date:** 2026-03-26
**Scope:** `SitesPage`, `SiteDetailPage`, `SitePageEditorPage`
**Goal:** Tighten visual consistency, reduce inline styling duplication, and improve UX across the three core site management pages.

---

## 1. Cross-Page Issues

### 1.1 Modal Implementation Mismatch

**Problem:** `SitesPage` builds its "Create Site" modal with a raw `fixed inset-0` overlay and manual panel markup (line 417-545), while `SitePageEditorPage` correctly uses the `DialogRoot`/`DialogContent` component system (line 322-381).

**Fix:** Replace the manual modal in `SitesPage` with `DialogRoot`/`DialogContent`. This gives us:
- Proper focus trapping and `Escape` handling
- Consistent backdrop animation (`data-[starting-style]` / `data-[ending-style]`)
- Screen-reader announcements via `DialogTitle`/`DialogDescription`

### 1.2 Duplicated Format Helpers

**Problem:** `formatSiteFamily`, `formatSiteType`, `formatCommerceProvider`, and `formatPageType` are copy-pasted between `SitesPage` and `SiteDetailPage`.

**Fix:** Extract into a shared `lib/siteFormatters.ts` file. One definition, used everywhere.

### 1.3 Inconsistent Card Construction

**Problem:** Cards are built three different ways across these pages:
- Manual Tailwind: `rounded-2xl border border-border bg-surface px-4 py-4` (SitesPage, SiteDetailPage)
- Design system class: `ds-card ds-card--md` (SitePageEditorPage Puck wrapper)
- Interactive buttons styled as cards: `rounded-xl border px-4 py-4 ... hover:border-accent/40` (template cards, site list items)

**Fix:** Standardize on the `ds-card` pattern. Create explicit variants:
- `ds-card--section` for tab content panels (the `rounded-2xl` wrappers)
- `ds-card--interactive` for clickable list items (adds hover/focus states)
- Continue using `ds-card--md` for content-heavy containers

### 1.4 Inconsistent Loading States

**Problem:** Loading indicators are inline `<Loader2>` icons with surrounding text (e.g., "Loading sites...", "Loading site..."). No skeleton placeholders on the list/detail pages -- just a spinner sentence.

**Fix:**
- Add skeleton cards to the template grid and site list on `SitesPage` (match the exact card shape with `animate-pulse` blocks)
- Add skeleton stat cards and skeleton page rows on `SiteDetailPage` overview/pages tabs
- Keep the compact spinner on `SitePageEditorPage` since the Puck editor has its own loading chrome

### 1.5 Form Field Wrapper

**Problem:** Every form input repeats the same label + input + helper text pattern manually:
```tsx
<div className="space-y-1">
  <label className="text-xs font-semibold text-content">Label</label>
  <Input ... />
  <div className="text-xs text-content-muted">Helper text</div>
</div>
```

**Fix:** Create a `<FormField label="..." helper="..." error="...">` wrapper component. Use it in the create-site modal, page-settings dialog, funnel-create form, and binding-create form. Reduces per-field boilerplate from 5 lines to 1.

### 1.6 Error Display Inconsistency

**Problem:** Errors show up in three different ways:
- Inline danger box with custom classes (`rounded-lg border border-danger/30 bg-danger/5 ...` in SitesPage modal)
- `toast.error()` calls (SiteDetailPage theme save)
- `console.error` with no user-facing feedback (funnel/binding creation)

**Fix:**
- Use `toast.error()` for all async action failures (create, delete, save)
- Use inline `<Callout variant="danger">` for pre-submission validation warnings (e.g., "no design systems available")
- Remove `console.error` side-channel errors that leave the user uninformed

---

## 2. SitesPage Specific

### 2.1 Tab Content Wrapper Repetition

**Problem:** All three tabs repeat the same section-card boilerplate:
```tsx
<div className="rounded-2xl border border-border bg-surface px-4 py-4">
  <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
    <div>
      <div className="text-sm font-semibold text-content">Section Title</div>
      <div className="text-xs text-content-muted">Description</div>
    </div>
    <Badge tone="neutral">{count} items</Badge>
  </div>
  ...
</div>
```

**Fix:** Extract a `<SectionCard title="..." description="..." count={n}>` compound component. Keeps the visual rhythm identical across tabs but cuts ~20 lines of duplication per tab.

### 2.2 Template Cards Need Better Visual Hierarchy

**Problem:** Template cards show the commerce provider label in `text-[11px]` uppercase, then the name, then description. The commerce provider badge feels lost at that size.

**Fix:**
- Move the commerce provider into a small `<Badge tone="neutral">` next to the page-count badge (top-right)
- Let the template name be the only top-level text
- This creates a cleaner read order: **Name** (left) / **Provider + Pages** (right) / **Description** (below)

### 2.3 Empty State Polish

**Problem:** Empty states for "My Sites" and "Imports" are plain text paragraphs ("No sites created yet...") without the `<EmptyState>` component used elsewhere.

**Fix:** Use the `<EmptyState>` component with an icon, title, description, and CTA button pointing to the Templates tab or import action.

### 2.4 Create Modal: Theme Radio Group

**Problem:** The theme binding radio group uses native `<input type="radio">` elements with manual layout. This clashes with the rest of the design system which avoids unstyled native inputs.

**Fix:** Replace with a custom `RadioCardGroup` (three stacked interactive cards with a check indicator on the selected one). Same visual pattern as the template cards but with selection state. Alternatively, use Base-UI's radio group for headless accessibility + custom styling.

### 2.5 Create Modal: Button Order

**Problem:** Primary "Create Site" button is on the left, Cancel on the right. Standard convention (and the pattern used in `SitePageEditorPage`'s settings dialog) puts Cancel first and the primary action on the right.

**Fix:** Swap to `Cancel | Create Site` order. Add `justify-end` to the button row.

---

## 3. SiteDetailPage Specific

### 3.1 Badge Overload in PageHeader

**Problem:** The header below the title packs 4-5 badges in a row: Workspace name, Status, Default product, Bound products, and sometimes "Explicit bindings only". This reads as visual noise rather than hierarchy.

**Fix:**
- Keep only **Status** and **Theme** as badges in the header
- Move product context into a compact summary row in the Overview tab
- The workspace name is already in the sidebar -- remove from the header badge row

### 3.2 Overview Tab: Too Many Nested Cards

**Problem:** The Overview tab stacks 6+ cards vertically (Site Information with 4 stat boxes, Theme Source, Provenance, Routing, Quick Stats 3-column grid, Quick Actions). Scrolling through these feels like a long settings page rather than a dashboard.

**Fix:**
- Merge **Site Information** stat cards with the header metadata -- put Type, Family, Commerce Provider, Status as a compact `<dl>` (definition list) or a single row of key-value pairs inside the section header
- Merge **Provenance** and **Routing** into a single "Details" card
- This reduces the overview from ~6 cards to 3-4 (Site details, Theme, Quick Stats, Quick Actions)

### 3.3 Pages Tab: Actions Alignment

**Problem:** Each page row has a "Preview" button and up to two badges (Draft, Approved) right-aligned. When both badges exist, the row gets crowded on narrow viewports.

**Fix:**
- Stack Preview + Edit buttons vertically (or use an icon-only button group)
- Show only the most relevant badge (Draft takes precedence over Approved since it implies "changes pending")
- Add a proper "Edit" button per page row (currently users have to navigate through the page name, which isn't obviously clickable since it's not styled as a link)

### 3.4 Theme Tab: Design System Token Preview

**Problem:** The theme tab shows a good summary (brand name, fonts, key colors) but the color swatches display hex values as text. For a "Theme" section, visual swatches would be much more useful.

**Fix:** Render actual color swatches (small `<div>` circles or squares) next to each color value. For "Not set" values, show a dashed empty swatch.

### 3.5 Tab Count: 6 Tabs is Borderline

**Problem:** The detail page has 6 tabs: Overview, Pages, Funnels, Products, Theme, Settings. On mobile, these wrap and take up significant vertical space.

**Fix:**
- Consider merging **Settings** into the Overview tab as a collapsible section (it's just a Medusa connection card and a few fields)
- Alternatively, group into primary tabs (Overview, Pages, Funnels) + a secondary "Configure" dropdown that opens Theme, Products, Settings in the same panel
- At minimum, ensure the `TabsList` scrolls horizontally on mobile instead of wrapping

### 3.6 Inline Create Forms

**Problem:** "Create Funnel" and "Create Product Binding" forms render inline (within the tab content) as expandable sections with their own card wrappers. This pushes existing content down and can be disorienting.

**Fix:** Move these into `DialogRoot`/`DialogContent` modals, matching the create-site pattern. Modal forms don't displace page content and give a clear "commit or cancel" flow.

---

## 4. SitePageEditorPage Specific

### 4.1 Actions Menu: Overloaded Responsibilities

**Problem:** The "Actions" dropdown menu mixes navigation (Back to Site), page switching (Select page dropdown inside the menu), settings (Edit settings), and data operations (Save draft, Open preview). This is a lot of disparate functionality behind a single trigger.

**Fix:** Restructure:
- **Left side of header:** Back-arrow button (always visible, not buried in a menu) + page switcher inline (a compact Select or breadcrumb)
- **Right side of header:** Dedicated "Save Draft" button (primary) + kebab/menu for secondary actions (Edit settings, Open preview)
- This surfaces the most common actions (navigate back, save) as one-click targets

### 4.2 Breadcrumb Navigation

**Problem:** The editor shows `Site: {name}` as a description, but there's no breadcrumb trail back to Sites > Site Detail > Page.

**Fix:** Add a compact breadcrumb: `Sites / {site.name} / {page.name}` in the header area. Each segment is a link. This replaces the need for the "Back to Site" menu item.

### 4.3 Draft Status Indicator

**Problem:** The "Draft saved" badge appears next to the page name only if a draft exists. There's no visual cue for unsaved changes (data has been modified in Puck but not yet saved as a draft).

**Fix:** Track dirty state (`data !== savedData`) and show:
- No badge if clean
- "Unsaved changes" badge (warning tone) if modified
- "Draft saved" badge (neutral) if saved

### 4.4 Save Feedback

**Problem:** `createVersion.mutate()` is called for save-draft but there's no success toast or visual confirmation. The only signal is the "Saving draft..." text reverting to "Save draft" in the menu.

**Fix:** Add `toast.success("Draft saved")` in the `onSuccess` callback.

---

## 5. Spacing & Typography Tightening

### 5.1 Section Labels

**Problem:** Section labels use two different patterns:
- `text-xs font-semibold uppercase tracking-wide` (most places)
- `text-[11px] font-semibold uppercase tracking-[0.14em]` (template cards)

**Fix:** Standardize on a single `text-overline` utility class:
```css
.text-overline {
  @apply text-xs font-semibold uppercase tracking-wide text-content-muted;
}
```

### 5.2 Card Padding

**Problem:** Cards alternate between `px-4 py-4`, `px-4 py-3`, and `p-6`. The inconsistency is subtle but noticeable when cards are adjacent.

**Fix:**
- Section cards (large containers): `p-5`
- List item cards: `px-4 py-3`
- Stat cards: `px-4 py-3`
- Modal content: `p-6`

Define these in `ds-card` variants so they're not hand-coded each time.

### 5.3 Border Radius

**Problem:** Two radii in play: `rounded-xl` (list items, stat cards, inner elements) and `rounded-2xl` (section cards, modals). This is intentional (nesting), but some places use `rounded-lg` instead of `rounded-xl`.

**Fix:** Audit for stray `rounded-lg` usage and normalize to `rounded-xl` for inner elements, `rounded-2xl` for outer containers.

---

## 6. Accessibility

### 6.1 Button-as-Card Missing Roles

**Problem:** Template cards and site list items are `<button>` elements styled as cards. This is good for keyboard accessibility but they lack `aria-label` attributes, so screen readers announce the entire text content.

**Fix:** Add `aria-label` with a concise label: `aria-label={`Select ${family.name} template`}` or `aria-label={`View site: ${site.name}`}`.

### 6.2 Modal Focus Management

**Problem:** The manual modal in `SitesPage` doesn't trap focus or return focus to the trigger on close.

**Fix:** Resolved automatically by migrating to `DialogRoot` (see 1.1).

### 6.3 Form Labels

**Problem:** Labels use `<label>` elements but are not connected to inputs via `htmlFor`/`id` attributes.

**Fix:** Wire up `htmlFor` on every label, or wrap with the `<FormField>` component (see 1.5) which handles this automatically.

---

## 7. Priority Order

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | 1.1 Modal migration (SitesPage) | Medium | Accessibility + consistency |
| P0 | 2.6 Error handling (console.error -> toast) | Low | UX |
| P1 | 1.2 Extract shared formatters | Low | Maintainability |
| P1 | 1.3 Standardize card variants | Medium | Visual consistency |
| P1 | 1.5 FormField wrapper | Medium | DRY + accessibility |
| P1 | 4.1 Editor header restructure | Medium | Usability |
| P2 | 3.1 Badge reduction in detail header | Low | Visual clarity |
| P2 | 3.2 Overview card consolidation | Medium | Information density |
| P2 | 3.5 Tab consolidation/scroll | Medium | Mobile UX |
| P2 | 5.1 Section label utility class | Low | Consistency |
| P3 | 1.4 Skeleton loading states | Medium | Perceived performance |
| P3 | 2.2 Template card hierarchy | Low | Visual refinement |
| P3 | 2.3 Empty state component usage | Low | Visual refinement |
| P3 | 2.4 Theme radio group | Medium | Polish |
| P3 | 3.4 Color swatches in theme tab | Low | Polish |
| P3 | 4.2 Breadcrumb navigation | Low | Wayfinding |
| P3 | 4.3 Dirty state tracking | Medium | UX |
| P3 | 4.4 Save toast feedback | Low | UX |

---

## 8. Files Affected

```
src/pages/workspaces/SitesPage.tsx
src/pages/workspaces/SiteDetailPage.tsx
src/pages/workspaces/SitePageEditorPage.tsx
src/components/layout/SectionCard.tsx          (new)
src/components/ui/form-field.tsx               (new)
src/components/ui/radio-card-group.tsx         (new, optional)
src/lib/siteFormatters.ts                      (new)
src/styles/design-system.css                   (update card variants)
```
