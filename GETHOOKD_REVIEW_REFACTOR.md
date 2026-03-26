# Refactor GetHookd Review Inbox to Use Shared Review Components

## Context

The SwipesPage (GetHookd review inbox under Creative Library > Saved) uses a bespoke inline `ReviewCard` component, custom filter bar, array-based selection, and has **no detail view**. Meanwhile, the creative review flow already has production-grade shared components (`AssetReviewGrid`, `AssetReviewCard`, `AdDetailPanel`) with proper multi-select (select-all with indeterminate state), client-side filtering, and a slide-over detail drawer.

This refactor standardizes the GetHookd UI on those shared components, adds a detail panel for inspecting individual swipes, and gives users proper multi-select with "select all."

## Files to change

| File | Action |
|------|--------|
| `mos/frontend/src/lib/library.ts` | Export 4 private media-mapping helpers |
| `mos/frontend/src/lib/assetReviewNormalizers.ts` | **New** — `normalizeSwipeToAssetReviewItem()` |
| `mos/frontend/src/components/review/SwipeDetailPanel.tsx` | **New** — slide-over drawer for swipe details |
| `mos/frontend/src/pages/swipes/SwipesPage.tsx` | Major refactor — replace bespoke grid with shared components |

## Step 1: Export media helpers from `lib/library.ts`

Add `export` to four currently-private functions (no logic changes):

- `mapSwipePlatforms` (line 267)
- `mapSwipeImages` (line 285)
- `mapSwipeVideos` (line 310)
- `mapSwipeStoredMedia` (line 329)

## Step 2: Create `normalizeSwipeToAssetReviewItem`

**New file:** `mos/frontend/src/lib/assetReviewNormalizers.ts`

Pure function mapping `CompanySwipeAsset` → `AssetReviewItem`. Key field mappings:

- `id` → `swipe.id` (internal ID, **not** external — bulk action APIs require this)
- `kind` → `"swipe"`
- `brandName` → `snapshot.page_name ?? swipe.title ?? "Saved swipe"`
- `headline`, `body`, `ctaText` → from snapshot with swipe fallback (same logic as `normalizeSwipeToLibraryItem`)
- `media` → reuse exported `mapSwipeVideos`, `mapSwipeImages`, `mapSwipeStoredMedia`
- `platform` → reuse exported `mapSwipePlatforms`
- `reviewStatus` → `swipe.review_status` (cast to `ReviewStatus`, default `"pending_review"`)
- `source` → `"gethookd"`
- `performanceScore`, `daysActive`, `usedCount` → direct from swipe
- `destinationUrl` / `destinationHostname` → from snapshot/swipe with hostname extraction
- `raw` → full `CompanySwipeAsset` for the detail panel

## Step 3: Create `SwipeDetailPanel`

**New file:** `mos/frontend/src/components/review/SwipeDetailPanel.tsx`

Follow the exact pattern from `AdDetailPanel.tsx` (same Dialog structure, animations, layout):

```
Props: { item: AssetReviewItem | null, open, onClose, onApprove?, onReject?, onMarkPending? }

Structure:
  Dialog.Root → Dialog.Portal → Dialog.Backdrop → Dialog.Viewport → Dialog.Popup
    Header: title + review status badge + action buttons (Approve/Reject/Mark Pending) + Close
    Scrollable body:
      1. Media section — reuse <SwipeMedia> from components/library/SwipeMedia.tsx
      2. Ad copy section — headline, body, CTA, link description (label/value pairs)
      3. Performance & tracking — score, days active, used count, platforms (2-col grid)
      4. Source dates — first seen, last seen, last synced, content changed
      5. Analysis metadata — status, model, ad unit format, channel, hook type, etc. (from raw)
      6. Landing page — clickable destination URL
      7. Raw payload — collapsible <details> with JSON.stringify(item.raw)
```

Key imports: `Dialog` from `@base-ui/react/dialog`, `floatingBackdrop` from `@/components/ui/floating`, `SwipeMedia` from `@/components/library/SwipeMedia`, `Badge`, `Button`.

## Step 4: Refactor `SwipesPage`

### 4a. Remove bespoke code
- Delete inline `ReviewCard` component (lines 42-96)
- Delete `statusTone`, `formatHostname` helpers (lines 26-40)
- Keep `getErrorMessage`, `formatDate` for error callouts

### 4b. Switch selection to `Set<string>`
```ts
const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
```

### 4c. Add detail panel state
```ts
const [detailItem, setDetailItem] = useState<AssetReviewItem | null>(null);
```

### 4d. Normalize swipes to `AssetReviewItem[]`
```ts
const reviewItems = useMemo(
  () => swipes.map(normalizeSwipeToAssetReviewItem),
  [swipes],
);
```

### 4e. Remove custom filter bar UI (lines 154-207)
`AssetReviewGrid` with `showFilters` (default true) provides all filtering — search, review status, changed since, platform, launch collection.

Keep server-side filter as `{ source: "gethookd" }` only; delegate all other filtering to the grid's client-side logic.

### 4f. Replace bespoke grid with shared components
```tsx
<AssetReviewGrid
  items={reviewItems}
  selectedIds={selectedIds}
  onSelectionChange={setSelectedIds}
  onCardClick={(item) => setDetailItem(item)}
  emptyMessage="No GetHookd swipes match the current filters."
/>
```

### 4g. Update bulk action bar
Convert `selectedIds.length` → `selectedIds.size`, `selectedIds` (array) → `Array.from(selectedIds)` for mutation calls, `clearSelection` → `setSelectedIds(new Set())`.

### 4h. Add detail panel + single-item actions
```tsx
<SwipeDetailPanel
  item={detailItem}
  open={detailItem !== null}
  onClose={() => setDetailItem(null)}
  onApprove={handleSingleApprove}
  onReject={handleSingleReject}
  onMarkPending={handleSingleMarkPending}
/>
```

### 4i. Keep the stats summary bar
The per-status breakdown (total/pending/approved/rejected/stale) stays above the grid — it provides at-a-glance info that the toolbar count doesn't replicate.

## What users get after this refactor

1. **Select all / deselect all** — checkbox with indeterminate state when partially selected
2. **Detail view** — click any card body to open a slide-over with full swipe info, media carousel, ad copy, performance data, analysis metadata, and raw payload
3. **Single-item actions** — approve/reject/mark pending from the detail panel without returning to grid
4. **Richer cards** — `AssetReviewCard` shows brand name, performance score, platform badges, metadata grid, launch collection status
5. **Better filtering** — all filters from `AssetReviewToolbar` including platform filter
6. **Dynamic grid columns** — adapts to portrait/landscape content mix

## Verification

1. Run `npm run dev` from `mos/frontend/`
2. Navigate to Creative Library → Saved tab
3. Confirm grid renders with `AssetReviewCard` style cards
4. Test "Select all" checkbox — should toggle all visible items
5. Click a card body — detail panel should slide in from right
6. Verify detail panel shows media, ad copy, metadata, raw payload
7. Test single-item approve/reject/mark pending from detail panel
8. Test bulk actions (add to collection, reject, mark pending) from selection bar
9. Test all filters (search, review status, changed since, platform, launch collection)
10. Run `npx tsc --noEmit` from `mos/frontend/` to verify type safety
