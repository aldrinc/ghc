# B2C Starter Template — Gap Analysis vs Medusa Next.js Starter

**Date:** 2026-03-27
**Reference:** https://github.com/medusajs/nextjs-starter-medusa
**Status:** Implementation complete — see status table below

---

## Overview

Our B2C starter storefront covers the basic browse → cart → checkout flow but lacks the polish and feature depth of the official Medusa Next.js starter. This document catalogues every meaningful gap and provides implementation details for closing each one.

Checkout is **out of scope** — our current checkout flow is aligned and complete.

---

## Gap Summary

| # | Gap | Priority | Effort | Area | Status |
|---|-----|----------|--------|------|--------|
| 1 | Store page: pagination | P0 | M | Catalog | ✅ Done |
| 2 | Store page: sort dropdown | P0 | S | Catalog | ✅ Done |
| 3 | PDP: multi-image gallery | P0 | M | Product | ✅ Done |
| 4 | PDP: related products | P0 | M | Product | ✅ Done |
| 5 | Category page: full implementation | P0 | M | Catalog | ✅ Done |
| 6 | Collection page: full implementation | P0 | M | Catalog | ✅ Done |
| 7 | Mini-cart dropdown | P0 | L | Navigation | ✅ Done |
| 8 | Cart: empty state | P1 | S | Cart | ✅ Done |
| 9 | Cart: product images & variant details | P1 | S | Cart | ✅ Done |
| 10 | Cart: sign-in prompt for guests | P1 | S | Cart | ✅ Done |
| 11 | PDP: product tabs (info, shipping & returns) | P1 | M | Product | ✅ Done |
| 12 | PDP: mobile actions bar | P1 | M | Product | ✅ Done |
| 13 | PDP: 3-column layout | P1 | M | Product | ✅ Done |
| 14 | Account: password editing | P2 | S | Account | ✅ Done |
| 15 | Account: profile completion % | P2 | S | Account | ✅ Done |
| 16 | Free shipping nudge banner | P2 | S | UX Polish | ✅ Done |
| 17 | 404 / not-found pages | P2 | S | UX Polish | ✅ Done |
| 18 | Skeleton loading parity | P2 | M | UX Polish | ✅ Done |
| 19 | Order confirmed page (was stub) | P1 | M | Post-checkout | ✅ Done |
| 20 | Hardcoded colors → theme tokens | P2 | S | Consistency | ✅ Done |
| 21 | Homepage: use shared product cards | P2 | S | Consistency | ✅ Done |
| 22 | PDP: add-to-cart timeout cleanup | P2 | S | Bug fix | ✅ Done |

**Effort key:** S = small (< half day), M = medium (half day – 1 day), L = large (1–2 days)

---

## P0 — Core UX Gaps

### 1. Store Page: Pagination

**Current state:** `MedusaB2CStorePage.tsx` fetches up to 24 products in a single `refreshProducts({ limit: 24 })` call and renders them all in one grid. No pagination controls, no URL-driven page state.

**Medusa reference:** URL-based pagination (`?page=N`), 12 products per page, smart ellipsis display for 7+ pages, skeleton fallback during page transitions.

**Implementation:**

- Add `page` state derived from URL search params (default 1), and a `PRODUCTS_PER_PAGE = 12` constant.
- Pass `limit` and `offset` to `refreshProducts()`:
  ```
  offset = (page - 1) * PRODUCTS_PER_PAGE
  ```
- The Medusa `listProducts` API already supports `limit` / `offset` and returns a `count` field — use `count` to compute total pages.
- Add a `Pagination` component below the product grid:
  - Show page numbers with ellipsis when totalPages > 7.
  - Highlight current page with `colorPrimary`.
  - Previous / Next arrows, disabled at bounds.
  - On click, update URL search param `?page=N` and scroll to top.
- Show `SkeletonProductGrid` during page transitions.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CStorePage.tsx` — add pagination state, controls, pass offset/limit
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx` — ensure `refreshProducts` returns `count` from API response
- `mos/frontend/src/lib/medusa/data.ts` — ensure `listProducts` response includes `count`

---

### 2. Store Page: Sort Dropdown

**Current state:** No sorting. Products display in whatever order the API returns.

**Medusa reference:** `SortProducts` dropdown with options, default sort by `created_at`.

**Implementation:**

- Add a `SortProducts` dropdown above the product grid (right-aligned next to the category sidebar heading).
- Sort options:
  - "Latest" → `created_at` desc (default)
  - "Price: Low → High" → `price` asc (client-side sort on `variants[0].calculated_price`)
  - "Price: High → Low" → `price` desc
- Store selected sort in URL param `?sort=created_at|price_asc|price_desc` so it persists across pagination.
- Apply sort client-side after fetch (Medusa list endpoint doesn't support price sorting natively — the reference starter also sorts client-side after fetching 100 products).
- Alternative: if catalog is large (>100 products), consider server-side `order` param for `created_at` and client-side for price.
- Reset to page 1 when sort changes.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CStorePage.tsx` — add sort dropdown, sort logic, integrate with pagination

---

### 3. PDP: Multi-Image Gallery

**Current state:** `MedusaB2CProductPage.tsx` renders a single `product.thumbnail` in an `aspect-square` container. No gallery, no scrolling, no zoom.

**Medusa reference:** Vertical scrolling image list showing all `product.images[]`, with priority loading for the first 3 images. No lightbox/zoom (so we don't need that either).

**Implementation:**

- Replace the single thumbnail with a vertical image list:
  - Show `product.images[]` if available, fall back to `[product.thumbnail]`.
  - Each image in an `aspect-square` container with `object-cover`.
  - On desktop: vertical scroll in left column, max-height constrained to viewport.
  - On mobile: horizontal scroll (swipeable) or vertical stack.
- Add thumbnail strip (optional, Medusa reference doesn't have this but it's standard):
  - Small clickable thumbnails below or beside the main image.
  - Click to scroll/jump to that image.
- Priority load first 2-3 images, lazy-load the rest.

**Data requirement:** `product.images` is already returned by the Medusa API and typed in our `MedusaProduct` type — verify the `images` field is populated in `loadProductByHandle()`.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx` — replace thumbnail with gallery
- `mos/frontend/src/lib/medusa/data.ts` — ensure `fields` param in `getProductByHandle` includes `images`

---

### 4. PDP: Related Products

**Current state:** None. PDP ends after the Add to Cart button.

**Medusa reference:** `RelatedProducts` section below the product, showing products from the same collection + matching tags. 2/3/4-column responsive grid.

**Implementation:**

- Add a "You may also like" section below the product detail area.
- Fetch related products using one of these strategies (in priority order):
  1. Same collection: if product has `collection_id`, fetch products from that collection, exclude current product.
  2. Same category: if product has `categories[]`, fetch products from the first category.
  3. Fallback: show latest products from the catalog.
- Display 4 products max in a responsive grid (2-col mobile, 3-col tablet, 4-col desktop).
- Reuse the same product card component from the store page.
- Lazy-load this section (fetch after main product renders).

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx` — add related products section
- `mos/frontend/src/lib/medusa/data.ts` — may need a `listProducts` call with `collection_id` filter

---

### 5. Category Page: Full Implementation

**Current state:** `MedusaB2CCategoryPage` referenced in `runtimePageMaps.ts` but the actual page component inside `MedusaB2CAdditionalPages.tsx` is a minimal stub that renders `PageShell` with no product content.

**Medusa reference:** Full page with breadcrumb navigation (recursive parent chain), category title + description, subcategory links if children exist, sort dropdown, and paginated product grid.

**Implementation:**

- Load category by handle via `loadCategoryByHandle()` (already exists in runtime).
- Render:
  1. **Breadcrumbs:** Build from `category.parent_category` chain recursively. Each crumb links to its category page. Root → ... → Parent → Current.
  2. **Category title** (`category.name`) and **description** (`category.description`) if present.
  3. **Subcategory links:** If `category.category_children[]` is non-empty, render as horizontal pill links above the product grid.
  4. **Product grid with sort + pagination:** Reuse the same sort/pagination pattern from the store page. Filter products by `category_id[]` param.
- Fetch products with `category_id` filter:
  ```
  refreshProducts({ category_id: [category.id], limit: 12, offset })
  ```

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — implement `MedusaB2CCategoryPage`
- `mos/frontend/src/lib/medusa/data.ts` — ensure `listProducts` supports `category_id` filter param
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx` — ensure category data includes `parent_category` and `category_children`

---

### 6. Collection Page: Full Implementation

**Current state:** `MedusaB2CCollectionPage` referenced in `runtimePageMaps.ts` but the actual component is a minimal stub.

**Medusa reference:** Collection title heading, sort dropdown, paginated product grid.

**Implementation:**

- Load collection by handle (add `loadCollectionByHandle()` to runtime if not present).
- Render:
  1. **Collection title** as page heading.
  2. **Product grid with sort + pagination:** Same pattern as store/category pages. Filter by `collection_id`.
- Fetch products with `collection_id` filter:
  ```
  refreshProducts({ collection_id: [collection.id], limit: 12, offset })
  ```

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — implement `MedusaB2CCollectionPage`
- `mos/frontend/src/lib/medusa/data.ts` — add `getCollectionByHandle()` if missing, ensure `listProducts` supports `collection_id`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx` — add `loadCollectionByHandle()` action

---

### 7. Mini-Cart Dropdown

**Current state:** Cart icon in header shows item count badge. Clicking it navigates to the full cart page. No preview.

**Medusa reference:** Desktop hover-triggered popover showing cart items with thumbnails, titles, variant options, quantity, delete button, subtotal, and "Go to cart" link. Auto-closes after 5 seconds when an item is added.

**Implementation:**

- Add a `MiniCart` popover component, triggered on hover (desktop) / tap (mobile) of the cart icon in `B2CStarterShell.tsx`.
- Popover content:
  - Title: "Shopping Bag" or "Cart"
  - List of `cart.items[]` (max 5, with "and N more..." if truncated):
    - Thumbnail image (small, 64×64)
    - Item title
    - Variant option text (e.g., "Size: M / Color: Blue")
    - Quantity
    - Delete (×) button → calls `removeCartItem()`
  - Subtotal line
  - "Go to cart" button → `navigateToCart()`
  - Empty state: "Your cart is empty"
- Auto-show behavior: when `addToCart()` succeeds, open the popover for 5 seconds then auto-close.
- Close on: click outside, Escape key, or navigation.
- Position: anchored below the cart icon, right-aligned.
- Use a portal or absolute positioning within the shell header.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/B2CStarterShell.tsx` — add MiniCart popover to header cart icon area
- Possibly extract a `MiniCart` sub-component for cleanliness

---

## P1 — Cart & Product Polish

### 8. Cart: Empty State

**Current state:** When cart is empty or null, the cart page shows a loading message or nothing meaningful.

**Medusa reference:** Dedicated `EmptyCartMessage` component with messaging and a "continue shopping" CTA.

**Implementation:**

- When `cart` is null or `cart.items.length === 0`, render:
  - Centered icon or illustration (shopping bag outline)
  - "Your cart is empty" heading
  - "Looks like you haven't added anything yet." subtext
  - "Continue Shopping" button → `navigateToStore()`
- Hide the totals section and checkout button when empty.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — update `MedusaB2CCartPage`

---

### 9. Cart: Product Images & Variant Details

**Current state:** Cart items show title and quantity only. No images, no variant info, no unit prices.

**Medusa reference:** Cart items include product thumbnail, title, variant options (color, size, etc.), unit price, and quantity.

**Implementation:**

- For each `cart.item`:
  - Show `item.thumbnail` (small image, ~80×80)
  - Show `item.product_title` and `item.variant_title`
  - Show unit price (`item.unit_price` formatted with currency)
  - Show line total (`item.total` or `unit_price × quantity`)
- Add subtotal, shipping estimate, tax, and total breakdown below the items list.
- The Medusa cart line item object includes `thumbnail`, `product_title`, `variant_title`, `unit_price`, `total` — all already available from the cart API.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — update `MedusaB2CCartPage` item rendering

---

### 10. Cart: Sign-In Prompt for Guests

**Current state:** No differentiation between guest and authenticated cart experience.

**Medusa reference:** `SignInPrompt` component shown for guest users encouraging them to sign in to link cart to their account.

**Implementation:**

- If `customer` is null (guest), show a banner above or below the cart items:
  - "Already have an account?" + "Sign in for a better experience" subtext
  - "Sign in" button → `navigateToAccount()`
- Hide when customer is authenticated.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — update `MedusaB2CCartPage`

---

### 11. PDP: Product Tabs

**Current state:** Product description is rendered as plain text below the title. No structured metadata display.

**Medusa reference:** Accordion-style tabs below the product info:
- "Product Information" — material, country of origin, type, weight, dimensions
- "Shipping & Returns" — hardcoded copy about fast delivery (3-5 days), simple exchanges, easy returns

**Implementation:**

- Add an accordion/collapsible section below the product description.
- Tab 1 — "Product Information":
  - Render from `product.metadata` or product attributes if available.
  - Fields: Material, Country of Origin, Type, Weight, Dimensions.
  - Show only fields that have values.
  - Fallback: if no metadata, show product type and weight if available.
- Tab 2 — "Shipping & Returns":
  - Static content (configurable via site settings later):
    - "Fast delivery: 3-5 business days"
    - "Simple exchanges: 30-day return policy"
    - "Easy returns: Free returns on all orders"
- Accordion behavior: click header to expand/collapse, one open at a time or independent toggle.
- Style with theme tokens: border, background, text colors.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx` — add tabs section

---

### 12. PDP: Mobile Actions Bar

**Current state:** On mobile, the variant selector, quantity picker, and add-to-cart button are inline in the page flow. They scroll out of view when looking at images or description.

**Medusa reference:** `MobileActions` component — sticky bottom bar on mobile with variant selector and add-to-cart button always visible.

**Implementation:**

- Add a fixed-bottom bar visible only on mobile (below `md` breakpoint):
  - Show selected variant label (or "Select variant" prompt)
  - "Add to Cart" button (full-width)
  - Price display
- Tap variant label to open a bottom sheet or modal with variant options.
- Hide the inline variant/add-to-cart section on mobile when this bar is active (to avoid duplicate controls).
- Use `position: fixed; bottom: 0` with `z-index` above the page content.
- Add padding to the page bottom to prevent content from being hidden behind the bar.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx` — add mobile actions bar

---

### 13. PDP: 3-Column Layout

**Current state:** Single-column flow — image, then title/price/variants, then add-to-cart. On desktop this wastes horizontal space.

**Medusa reference:** 3-column layout on desktop:
- Column 1 (left, sticky): Product info (title, description, price) + Product tabs
- Column 2 (center): Image gallery (scrollable)
- Column 3 (right, sticky): Variant selector + Add to Cart + onboarding CTA

**Implementation:**

- On desktop (≥1024px), restructure the PDP into a 3-column CSS grid or flex layout:
  ```
  grid-template-columns: 1fr 1.5fr 1fr
  ```
  - Left column (sticky top): product title, price, description, product tabs
  - Center column: image gallery (scrollable, gap between images)
  - Right column (sticky top): variant selector, quantity, add-to-cart, "View Cart" link
- On mobile (<1024px): stack vertically — images first, then info, then actions.
- Use `position: sticky; top: <header-height>` for left and right columns.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx` — restructure layout

---

## P2 — Account & Polish

### 14. Account: Password Editing

**Current state:** Profile page allows editing name, email, phone. No password change.

**Medusa reference:** `ProfilePassword` component with current password, new password, confirm password fields.

**Implementation:**

- Add a "Password" section to `MedusaB2CAccountProfilePage`:
  - Current password input
  - New password input
  - Confirm new password input
  - Save button
- Use the Medusa customer update endpoint or a dedicated password change endpoint if available.
- Validate: new password matches confirmation, minimum length.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — update `MedusaB2CAccountProfilePage`

---

### 15. Account: Profile Completion Percentage

**Current state:** Dashboard shows welcome message and navigation links. No progress indicator.

**Medusa reference:** Dashboard overview shows profile completion percentage based on filled fields (email, first name, last name, phone, billing address).

**Implementation:**

- Calculate completion from customer fields:
  - email (20%), first_name (20%), last_name (20%), phone (20%), billing address (20%)
  - Or simpler: count non-empty fields / total fields × 100
- Show as a progress bar or percentage badge on the account dashboard.
- Link to profile page with a "Complete your profile" CTA if < 100%.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — update `MedusaB2CAccountDashboardPage`

---

### 16. Free Shipping Nudge Banner

**Current state:** No free shipping messaging anywhere.

**Medusa reference:** Banner component with progress bar showing how much more the customer needs to spend to qualify for free shipping. Two variants: inline (in layout) and popup (fixed bottom-right with dismiss).

**Implementation:**

- Determine free shipping threshold from shipping options:
  - Fetch shipping options for current region.
  - Find the free shipping option and its `requirements` (min subtotal).
  - If no free shipping option exists, don't show the banner.
- Calculate remaining amount: `threshold - cart.subtotal`.
- Show inline banner above cart items or in the shell header:
  - If below threshold: "Spend $X.XX more for free shipping!" + progress bar
  - If at/above threshold: "You've unlocked free shipping!" + checkmark
- Theme-aware styling with `colorPrimary` for the progress bar fill.

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/B2CStarterShell.tsx` — optional promo bar slot
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — show in cart page

---

### 17. 404 / Not-Found Pages

**Current state:** No custom 404 pages. Invalid routes likely show a blank page or runtime error.

**Medusa reference:** Custom `not-found.tsx` at multiple route levels (root, main group, checkout group).

**Implementation:**

- Add a `NotFoundPage` component for the B2C runtime:
  - "Page not found" heading
  - "The page you're looking for doesn't exist or has been moved." subtext
  - "Continue Shopping" button → `navigateToStore()`
  - "Go Home" button → `navigateToHome()`
- Handle in page type resolution: if `resolveSitePathPageType()` returns null or an unknown type, render `NotFoundPage`.
- Also handle product/collection/category not found: if `loadProductByHandle()` returns null, show a product-specific 404 ("Product not found").

**Files to modify:**
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx` — add `NotFoundPage`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx` — handle not-found in page resolution

---

### 18. Skeleton Loading Parity

**Current state:** Some skeleton states exist (store page has a 6-card grid skeleton, product page has a basic loading state). Most pages show "Loading..." text.

**Medusa reference:** 11 dedicated skeleton components covering every loading surface.

**Implementation:**

Skeletons needed:
- **Product card skeleton** — used in store, category, collection grids (image placeholder + text lines)
- **PDP skeleton** — image placeholder + text lines for title/price/description + button placeholder
- **Cart item skeleton** — row with image placeholder + text lines + quantity placeholder
- **Cart totals skeleton** — 4-5 text line placeholders of varying widths
- **Account page skeleton** — sidebar + content area with text line placeholders

Each skeleton should use `colorBackgroundAlt` for the pulse/shimmer background and `radiusMedium` for rounded corners, consistent with the theme system.

**Files to modify:**
- Various page components in `MedusaB2CAdditionalPages.tsx`, `MedusaB2CStorePage.tsx`, `MedusaB2CProductPage.tsx`
- Consider extracting shared skeleton primitives (SkeletonLine, SkeletonBox) into a utility

---

## Out of Scope

The following features are **not** in the Medusa reference starter and are excluded from this analysis:

- Search (not in reference)
- Wishlist / favorites (not in reference)
- Product reviews / ratings (not in reference)
- Faceted filtering by price, color, size (not in reference — only sort exists)
- Product image zoom / lightbox (not in reference)
- Checkout changes (our checkout is aligned)

---

## Suggested Implementation Order

**Phase 1 — Catalog foundations (P0, ~3 days):**
1. Store page pagination + sort (items 1-2) — these unlock usable catalogs
2. Category page implementation (item 5) — reuses pagination/sort from above
3. Collection page implementation (item 6) — reuses pagination/sort from above

**Phase 2 — PDP overhaul (P0, ~2 days):**
4. Multi-image gallery (item 3)
5. 3-column layout (item 13)
6. Related products (item 4)
7. Product tabs (item 11)
8. Mobile actions bar (item 12)

**Phase 3 — Cart & navigation (P0-P1, ~2 days):**
9. Mini-cart dropdown (item 7)
10. Cart empty state (item 8)
11. Cart images & variant details (item 9)
12. Cart sign-in prompt (item 10)

**Phase 4 — Polish (P2, ~1 day):**
13. Account: password editing (item 14)
14. Account: profile completion % (item 15)
15. Free shipping nudge (item 16)
16. 404 pages (item 17)
17. Skeleton loading parity (item 18)

**Total estimated effort: ~8 days**
