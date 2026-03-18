# UI Usability Improvements Plan

## Summary

After a page-by-page review of the live application, this plan identifies usability issues grouped by severity and proposes concrete improvements. The focus is on reducing friction, improving wayfinding, and surfacing the right information at the right time.

---

## P0 — Critical Flow Blockers

### 1. Workspace selection is a dead end for most of the app

**Problem:** 10 of 13 sidebar destinations show a dashed empty-state box ("Choose a workspace from the sidebar") when no workspace is selected. The workspace selector itself is buried inside the sidebar header dropdown, which currently shows `W  Select a workspace  Workspace` — the affordance is unclear and the label is redundant. Clicking it doesn't open a picker; it navigates to `/workspaces`, where you must click a card. After selecting, you're redirected to `/workspaces/overview`, losing whatever page you were trying to visit.

**Impact:** New users will click sidebar items, see empty pages, and not understand what to do. There's no inline way to select a workspace — the empty states just say "pick from the sidebar" but the sidebar trigger isn't obviously a workspace picker.

**Proposed fix:**
- Make the header product/workspace selector a **combined cascading picker**: workspace → product, accessible from the header bar on every page (not just the sidebar).
- When a user lands on a workspace-gated page with no workspace selected, show the picker **inline** in the empty state (not just a text instruction). A dropdown or combobox embedded in the empty state that lists workspaces and auto-selects when clicked.
- After workspace selection, stay on the current page (don't redirect to overview).
- Persist workspace selection in localStorage so returning users don't have to re-select.

---

### 2. "New funnel" / "New product" / "New campaign" buttons are enabled without workspace

**Problem:** On `/research/funnels`, `/workspaces/products`, and `/campaigns`, primary action buttons are fully styled and clickable even when no workspace is selected. Clicking "New funnel" or "New product" without a workspace will either error or produce confusing behavior.

**Impact:** Users click the prominent CTA, get an error or unexpected result, lose trust.

**Proposed fix:**
- Disable primary action buttons when the prerequisite context (workspace/product) is missing.
- Add a tooltip on the disabled button: "Select a workspace first".
- Alternatively, clicking the button when no workspace is selected opens the workspace picker inline.

---

## P1 — Navigation & Wayfinding

### 3. Campaign detail header consumes excessive vertical space

**Problem:** The campaign detail page has 5 layers before any tab content appears:
1. Global header bar (breadcrumb + product selector)
2. Campaign name + "Back to campaigns" button + raw campaign UUID
3. Pipeline stepper (Strategy → Angles → Delivery → Creative → Publish prep → Published)
4. Product mismatch warning banner (when scoped to different product)
5. Tab navigation (Overview / Strategy / Angles / Delivery / Creative / Publish)

On a 1080p display, tab content doesn't appear until ~500px down. The pipeline stepper and tab nav serve overlapping purposes (both show phases), and the product mismatch warning is a full-width banner that persists on every tab.

**Proposed fix:**
- Collapse the pipeline stepper into a compact single-line breadcrumb-style indicator, or make it sticky so it doesn't push content down.
- Move the product mismatch warning into a **dismissible** slim bar or a badge next to the campaign name, not a full-width banner on every tab.
- Remove the raw campaign UUID from the visible header — move it to a "copy ID" icon button or show it only on the Overview tab. Users don't navigate by UUID.
- Consider making the tab bar sticky so users always know which tab they're on when scrolling.

### 4. Pipeline stepper label truncation

**Problem:** The stepper labels get truncated at narrow widths — "Publish prep" becomes "Publis prep". The stepper attempts to show 6 phases in a horizontal row which doesn't fit well.

**Proposed fix:**
- Shorten phase labels: "Publish prep" → "Prep", "Published" → "Publish". Keep the rest as-is.
- Or use icons with tooltips at narrow widths instead of text labels.

### 5. Sidebar "Strategy Runs" label is misleading

**Problem:** The sidebar item "Strategy Runs" navigates to `/strategy` which shows a page titled "Workflows" with 109 workflow runs of various kinds. The sidebar label suggests it's strategy-specific, but the page is a general workflow monitor.

**Proposed fix:**
- Scope the page to only show workflows relevant to the selected workspace. Currently shows all 109 runs across all workspaces.
- Rename the sidebar item to "Workflows" to match the page title.
- If it should show all workflows, move it out of the "Workspace" nav section into its own "Operations" or "Monitor" section.

### 6. Campaigns list shows raw UUIDs and has no search/filter

**Problem:** The campaigns list shows 33 campaigns in a flat list with no search, no status filter, no sorting. Each campaign card shows the raw product UUID (e.g., `502a0317-3e6a-484e-b114-1eaeee68b334`) instead of the product name. The "Scope: All workspaces" label suggests filtering but provides no interactive filter control.

**Proposed fix:**
- Add a search input to filter campaigns by name.
- Add filter chips or a dropdown for workspace/status.
- Resolve product UUIDs to human-readable product names in campaign cards.
- Show campaign status (active, draft, completed) as a badge on each card.
- Add last-updated or created-at date to each card for temporal context.

---

## P2 — Information Density & Readability

### 7. Workspaces page is cluttered with test data

**Problem:** The workspaces page shows 20+ cards including many test/duplicate workspaces ("The Honest Herbalist" appears 10+ times with timestamps like "Finalization 1771779156", "Smoke 1771785302", "V2 Queue 1771774835"). Each card shows a truncated UUID at the bottom. There's no search, no archive/hide capability, and no way to distinguish production from test workspaces.

**Proposed fix:**
- Add a search/filter input at the top of the workspaces grid.
- Show the full workspace name (some are truncated in cards).
- Replace truncated UUIDs with meaningful metadata (campaign count, last active date).
- Consider an "archive" or "hide" feature so test workspaces don't crowd the view.
- Add a list view option that's more scannable for many workspaces (Cards/List toggle exists but list view should be the default when > 10 workspaces).

### 8. Workflow runs table shows raw IDs and lacks human context

**Problem:** On the Strategy Runs page, workflow rows show `strategy_v2` as the kind, a status badge, the workspace name, and a truncated UUID. There's no workflow name, no timestamp, no campaign association, and no way to understand what each run was for without clicking into it.

**Proposed fix:**
- Add a "Started" timestamp column.
- Show the associated campaign name (if any) alongside the workspace.
- Replace truncated UUIDs with a "View" button or link.
- Add a duration or elapsed time indicator for running workflows.
- The filter dropdowns (Status, Kind, Workspace) are stacked vertically and consume half the viewport — make them a horizontal filter bar.

### 9. Campaign Overview tab shows redundant metadata

**Problem:** The Overview tab has a "Campaign" card that repeats information already in the header: Workspace name, Product UUID, Campaign UUID. Below that, "Latest workflow: No workflows yet" and "Workflow runs: No workflow runs yet" are two separate sections saying the same thing.

**Proposed fix:**
- Remove the redundant Campaign metadata card (workspace/product/ID are already in the header).
- Merge "Latest workflow" and "Workflow runs" into a single section that shows either the active/recent workflow or the empty state.
- Lead with the "Flow status" section (Strategy sheet, Angle specs, Creative briefs, Funnels) since that's the most actionable information.
- Make the flow status items clickable — clicking "Strategy sheet: Ready" should navigate to the Strategy tab.

### 10. Campaign Angles tab has excessive instructional text

**Problem:** The Angles tab shows 3 paragraphs of instructional text above the actual angle specs:
- "Approving experiments unblocks campaign planning..."
- "Creating funnels uses the default pre-sales + sales templates..."
- "Uncheck variants to run lighter, faster tests..."

This pushes the actual content (angle cards) further down the page.

**Proposed fix:**
- Replace the 3 paragraphs with a single concise line or move them into a collapsible "How it works" section.
- Or show them only on first visit (dismissible).
- The "Select all / 0 angles selected · 0 variants included" bar should be more prominent since it's the primary action interface.

### 11. Campaign Creative tab hides brief selection behind a disclosure

**Problem:** "Select briefs for generation (0/1 selected)" is a collapsed disclosure triangle (`▸`). The empty state below says "Select briefs above and click Generate assets" but the brief selector is hidden. The "Generate assets" button at the top-right is disconnected from the brief selector below.

**Proposed fix:**
- Default the brief selector to expanded when there are briefs available.
- Move the "Generate assets" button next to the brief selector, not in the header area.
- Show a brief count badge next to "Creative briefs" so users see at a glance how many exist.

---

## P3 — Polish & Consistency

### 12. Campaign Publish tab gives equal weight to unavailable platforms

**Problem:** The Publish tab shows Meta Ads (Available), TikTok Ads (Coming soon), and Bing Ads (Coming soon) as equal-sized cards. Two-thirds of the page is "Coming soon" content with no actionable value.

**Proposed fix:**
- Visually de-emphasize "Coming soon" platforms — show them as a compact list or collapsed section rather than full cards.
- Give Meta Ads the primary visual treatment since it's the only available platform.
- Or hide "Coming soon" platforms entirely and add a "More platforms coming soon" note.

### 13. Empty states are inconsistent across pages

**Problem:** Empty states vary across pages:
- Some say "Choose a workspace from the sidebar" (generic instruction)
- Some say "No workspace selected" (bold heading + instruction)
- Some show a dashed border box, others show plain text
- Funnels says "Pick a workspace from the sidebar to start building funnels" (actionable)
- Creative Library says "No teardowns yet. Ingest ads and post teardowns to see them here." (task-specific)

**Proposed fix:**
- Create a standardized `EmptyState` component with consistent styling:
  - Icon (optional)
  - Heading (what's missing)
  - Description (what to do)
  - Action button (inline workspace picker, or relevant CTA)
- Use it uniformly across all workspace-gated pages.

### 14. Creative Library has nested tab confusion

**Problem:** Creative Library has two levels of tabs: `Library | Meta` at the top, then `Teardowns | Ads | Saved` as sub-tabs. The visual treatment is different (top tabs are pill-style, sub-tabs are also pill-style but in a separate row). It's unclear which level of hierarchy you're navigating.

**Proposed fix:**
- Use visually distinct tab styles for the two levels (e.g., underline tabs for top level, pill tabs for sub-level).
- Or flatten the hierarchy: if "Meta" is a separate integration panel, consider making it a sidebar section rather than a tab.

### 15. Delivery tab "Save URLs" and "Validate URLs" are confusing dual actions

**Problem:** The Delivery tab (external URLs mode) has both a "Validate URLs" button inside the form and a separate "Save URLs" button below the form. It's unclear when to use which. The text says "Saving clears previous validation if the normalized URL set changed" which adds to the confusion.

**Proposed fix:**
- Merge into a single flow: typing in the URL fields auto-saves on blur (or shows a "dirty" indicator), and "Validate URLs" is the only explicit action.
- Or: keep "Save URLs" but rename to "Save draft" and make "Validate & Save" the primary action.
- Remove the validation status explanation text — show it as a tooltip on the badge instead.

### 16. Product mismatch warning lacks resolution path

**Problem:** The "This campaign is scoped to a different product" banner shows on every campaign tab with a raw UUID and a "Switch product" button. But clicking "Switch product" changes the global product context (affecting all other pages), which may not be what the user wants.

**Proposed fix:**
- Show the product name instead of UUID in the warning.
- Clarify what "Switch product" does: "Switch global context to [Product Name]".
- Consider auto-switching product context when entering a campaign detail page (with an undo option), rather than showing a persistent warning.

---

## P4 — Perceived Performance & Error Resilience

### 17. No skeleton screens anywhere — all loading is text-only

**Problem:** Every page uses plain text like "Loading campaigns…", "Loading workflows…", "Loading strategy sheet…" in a bordered box. There are no skeleton/shimmer placeholders. The layout shifts when data loads because the loading text occupies different space than the real content.

**Impact:** The app feels slower than it is. Layout shifts cause visual jank.

**Proposed fix:**
- Create a `Skeleton` component (shimmer bars) and a `SkeletonCard` variant.
- Replace text loading states on high-traffic pages (campaigns list, campaign overview, workflow runs) with skeleton layouts that match the real content shape.
- Lower-traffic pages can keep text loading states.

### 18. Several pages have no error handling at all

**Problem:** CampaignStrategyTab, CampaignPublishTab, TasksPage, and WorkflowsPage have no visible error handling. If the API returns an error, the user sees nothing — just a blank or loading state that never resolves.

**Proposed fix:**
- Add a standardized `ErrorState` component (icon + message + retry button).
- Wrap data-fetching sections with error boundaries or query error states.
- At minimum, every page that fetches data should show an error state with a "Retry" button.

### 19. Campaign Overview "Flow status" items are not clickable

**Problem:** The flow status section shows "Strategy sheet: Ready", "Angle specs: 1 specs · Ready", etc. These are the most actionable items on the overview but they're static text — clicking should navigate to the corresponding tab.

**Proposed fix:**
- Make each flow status row a clickable link/button that navigates to its tab (Strategy sheet → Strategy tab, Angle specs → Angles tab, etc.).

---

## Implementation Priority

| Priority | Items | Effort | Impact |
|----------|-------|--------|--------|
| P0 | #1 Workspace selector, #2 Disabled CTAs | Medium | Unblocks first-time users |
| P1 | #3 Header height, #4 Stepper labels, #5 Strategy Runs label, #6 Campaign search | Medium | Daily workflow friction |
| P2 | #7 Workspace clutter, #8 Workflow table, #9 Overview tab, #10 Angles text, #11 Creative briefs | Small–Medium | Information clarity |
| P3 | #12 Publish platforms, #13 Empty states, #14 Library tabs, #15 Delivery actions, #16 Product mismatch | Small | Consistency & polish |
| P4 | #17 Skeleton screens, #18 Error handling gaps, #19 Clickable flow status | Small–Medium | Perceived performance & resilience |

### Suggested execution order

1. **#1 + #2** — Workspace selection & disabled CTAs (biggest unblock)
2. **#13** — Standardized empty states (creates a reusable pattern for all pages)
3. **#3 + #4** — Campaign header compaction (most-visited page)
4. **#6** — Campaign list search/filter (scales with data growth)
5. **#9 + #10 + #11** — Campaign tab content improvements (quick wins)
6. **#8 + #5** — Workflows table & labeling
7. **#7** — Workspaces page cleanup
8. **#12 + #14 + #15 + #16** — Polish items
