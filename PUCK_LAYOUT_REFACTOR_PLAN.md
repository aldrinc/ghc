# Puck Layout System Refactor Plan

## The Problem

Our Puck page builder produces pages that feel boxed and constrained compared to modern storefronts like omnicreatine.com. The root cause is **not Puck** — it is our custom `Section` wrapper and the width-management conventions baked into our block components.

---

## Diagnosis: What Is Actually Wrong

### 1. Our Section conflates two concerns into one

In `puckConfig.tsx:337–437`, our `Section` component treats "outer band" and "inner content frame" as a single thing. Every layout mode (`full`, `contained`, `card`) always applies a `max-w-*` constraint via `containerWidthClass()`:

```
full    → <section><div class="mx-auto max-w-6xl px-6">{content}</div></section>
contained → <section><div class="mx-auto max-w-6xl px-6"><div class="bg p-*">{content}</div></div></section>
card    → <section><div class="mx-auto max-w-6xl px-6"><div class="rounded-2xl border bg p-*">{content}</div></div></section>
```

There is no way to say: "I want the band to be full-bleed edge-to-edge, AND I want the content inside it to be narrower." The `containerWidth` prop controls both the visual band and the content frame simultaneously.

On a site like omnicreatine.com, what you see is:
- **Hero**: background/media fills the entire viewport width. Text is constrained to ~700px center column.
- **Feature sections below**: outer band is edge-to-edge (with background color or subtle gradient). Inner content area is ~1100–1200px max-width, centered.

Our Section cannot express either pattern cleanly.

### 2. Child blocks fight the Section for width control

Our storefront blocks independently hardcode `max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8` in their own render functions:

| Block | Lines | Width Pattern |
|---|---|---|
| StarterStoreHeader | `StarterStorefrontBlocks.tsx:183` | `max-w-[1440px] mx-auto` |
| StarterPromoBar | `StarterStorefrontBlocks.tsx:338` | `max-w-[1440px] mx-auto` |
| StarterHomeHero | `StarterStorefrontBlocks.tsx:438` | `max-w-[1440px] mx-auto` |
| StarterCollectionRails | `StarterStorefrontBlocks.tsx:566` | `max-w-[1440px] mx-auto` |
| StarterStoreFooter | `StarterStorefrontBlocks.tsx:633` | `max-w-[1440px] mx-auto` |
| CommerceStoreTemplate | `CommerceBlocks.tsx:1076` | `max-w-[1440px] mx-auto` |
| CommerceProductDetail | `CommerceBlocks.tsx:1257,1436,1497` | `max-w-[1440px] mx-auto` (3x) |
| CommerceCart | `CommerceBlocks.tsx:1613` | `max-w-[1440px] mx-auto` |
| CommerceCheckout | `CommerceBlocks.tsx:2007` | `max-w-[1440px] mx-auto` |
| CommerceStoreHeader | `CommerceBlocks.tsx:2518` | `max-w-[1440px] mx-auto` |
| CommerceStoreFooter | `CommerceBlocks.tsx:2682` | `max-w-[1440px] mx-auto` |

This means the child block is applying `max-w-[1440px]` *inside* a Section that already applied `max-w-6xl` (1024px). Result: **double containment**. The 1440px cap is irrelevant because the parent already capped at 1024px. The block's own padding (`px-4 sm:px-6 lg:px-8`) stacks with the Section's `px-6`.

Width ownership is split and contradictory. Nobody is in charge.

### 3. The root wrapper is passive

`puckConfig.tsx:334`: `root.render = ({ children }) => <div className="w-full">{children}</div>`

This is fine — but it means there is no page-level layout contract. Each Section and each block is independently deciding its own width. There is no shared layout "rail" that sections participate in.

### 4. containerWidth options are too narrow

```
sm → max-w-2xl  (672px)
md → max-w-4xl  (896px)  ← default
lg → max-w-6xl  (1152px)
xl → max-w-7xl  (1280px)
```

Modern storefronts use 1280–1440px content areas. Our widest option (`xl`) is 1280px, and the *default* is only 1152px. The blocks themselves use 1440px because they know the Section options are too narrow.

### 5. No true full-bleed option

`layout: "full"` is a misnomer. It does not mean "edge-to-edge." It means "full-width background, constrained content." There is no mode where a Section renders with zero max-width — where the content genuinely fills the viewport.

---

## What Puck Actually Provides

Puck is a headless component renderer. It does not impose layout constraints. Key facts from the official docs:

- `config.components[name].render` is a plain React render function — you control all CSS
- `root.render` wraps the entire page — you can put any layout system here
- Slots (`type: "slot"`) let components accept nested children
- `inline: true` removes Puck's wrapping `<div>`, enabling custom CSS layouts
- `puck.metadata` passes global context to all components
- There are no built-in Section, Band, or Container primitives — those are ours

**Puck is not the bottleneck. Our abstraction layer is.**

---

## Refactor Plan

### Phase 1: Redesign the Section Component

**Goal**: Split the single Section into two independent concerns.

#### New Section Props Schema

```typescript
type BandWidth = "bleed" | "page" | "narrow";
type ContentWidth = "none" | "prose" | "sm" | "md" | "lg" | "xl" | "2xl" | "full";
type ContentAlign = "left" | "center" | "right";

interface SectionProps {
  // --- Existing (keep for backwards compat) ---
  purpose: "section" | "header" | "footer";
  variant: "default" | "muted";

  // --- REPLACED ---
  // layout: "full" | "contained" | "card"      ← REMOVE
  // containerWidth: "sm" | "md" | "lg" | "xl"  ← REMOVE

  // --- NEW: Outer band controls ---
  bandWidth: BandWidth;          // default: "page"
  // "bleed"  → no max-width on the outer section, edge-to-edge
  // "page"   → outer section capped at page max (e.g. max-w-[1440px])
  // "narrow" → outer section capped at max-w-5xl

  // --- NEW: Inner content frame controls ---
  contentWidth: ContentWidth;    // default: "lg"
  // "none" → no inner wrapper, content fills the band
  // "prose" → max-w-prose (65ch)
  // "sm"   → max-w-2xl  (672px)
  // "md"   → max-w-4xl  (896px)
  // "lg"   → max-w-6xl  (1152px)
  // "xl"   → max-w-7xl  (1280px)
  // "2xl"  → max-w-[1440px]
  // "full" → w-full, no constraint

  contentAlign: ContentAlign;    // default: "center"

  // --- NEW: Surface treatment ---
  surface: "none" | "subtle" | "card";  // default: "none"
  // "none"   → no background/border on the inner frame
  // "subtle" → bg-surface-2 on inner frame (replaces "contained")
  // "card"   → rounded-2xl border shadow on inner frame (replaces "card")

  // --- Spacing (keep existing, expand) ---
  padX: "none" | "sm" | "md" | "lg";   // default: "md"
  padY: "none" | "sm" | "md" | "lg";   // default: "md"

  // Slot
  content: Slot;
}
```

#### New Render Logic

```
┌───────────────── bandWidth ──────────────────┐
│ (bleed = 100vw, page = max-w-[1440px])       │
│                                               │
│  ┌──────── contentWidth + surface ─────────┐  │
│  │ (e.g. max-w-6xl, centered, optional bg) │  │
│  │                                         │  │
│  │  {slot content}                         │  │
│  │                                         │  │
│  └─────────────────────────────────────────┘  │
│                                               │
└───────────────────────────────────────────────┘
```

Concrete CSS output for the Omnicreatine hero pattern:
```
bandWidth="bleed" + contentWidth="md" + surface="none"
→ <section class="w-full">
    <div class="mx-auto max-w-4xl px-6 py-12">
      {content}
    </div>
  </section>
```

Full-bleed hero with no content constraint:
```
bandWidth="bleed" + contentWidth="none"
→ <section class="w-full">
    {content}  // block handles its own internal layout
  </section>
```

Card section:
```
bandWidth="page" + contentWidth="lg" + surface="card"
→ <section class="mx-auto max-w-[1440px]">
    <div class="mx-auto max-w-6xl px-6 py-12">
      <div class="rounded-2xl border border-border bg-surface shadow-sm p-7">
        {content}
      </div>
    </div>
  </section>
```

#### Backwards Compatibility

Map old props to new props at normalization time in `puckData.ts`:

```
layout="full"      + containerWidth="lg" → bandWidth="bleed"  + contentWidth="lg" + surface="none"
layout="contained" + containerWidth="lg" → bandWidth="bleed"  + contentWidth="lg" + surface="subtle"
layout="card"      + containerWidth="lg" → bandWidth="bleed"  + contentWidth="lg" + surface="card"
```

This migration runs in `normalizePuckData()` so existing template JSON keeps working without changes.

#### Files to Change

| File | Change |
|---|---|
| `puckConfig.tsx:337–437` | Rewrite Section fields, defaults, and render function |
| `puckConfig.tsx:138–157` | Update `containerWidthClass()` and `sectionPaddingClass()` to handle new tokens |
| `puckData.ts` | Add migration in `normalizePuckData()` for old→new Section props |

---

### Phase 2: Remove Width Ownership from Child Blocks

**Goal**: Blocks should be layout-neutral. The Section (band + frame) owns width. Blocks fill whatever container they're in.

#### Strategy

For each block that currently hardcodes `max-w-[1440px] mx-auto px-* sm:px-* lg:px-*`:

1. Remove the page-level container wrapper from the block's render function
2. The block's content should fill its parent container using `w-full`
3. Any block-internal sub-containment (e.g., a text column within a hero that should be narrower than the media) stays — that is content layout, not page layout

#### Specific Changes

**StarterStorefrontBlocks.tsx:**

| Block | Current | New |
|---|---|---|
| `StarterStoreHeader:183` | `mx-auto max-w-[1440px] ... px-4 sm:px-6 lg:px-8` | `w-full px-4 sm:px-6 lg:px-8` (remove max-w, remove mx-auto) |
| `StarterPromoBar:338` | `mx-auto max-w-[1440px] ... px-4 sm:px-6 lg:px-8` | `w-full px-4 sm:px-6 lg:px-8` |
| `StarterHomeHero:438` | `mx-auto ... max-w-[1440px] ... px-4 sm:px-6 lg:px-8` | `w-full px-4 sm:px-6 lg:px-8` (keep internal `max-w-2xl` on text column — that is content layout) |
| `StarterCollectionRails:534,566` | `mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8` | `w-full px-4 sm:px-6 lg:px-8` |
| `StarterStoreFooter:633` | `mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8` | `w-full px-4 sm:px-6 lg:px-8` |

**CommerceBlocks.tsx:**

| Block | Lines | Change |
|---|---|---|
| `CommerceStoreTemplate` | `1076` | Remove `mx-auto max-w-[1440px]`, keep internal layout grid |
| `CommerceProductDetail` | `1257, 1436, 1497` | Remove all three `mx-auto max-w-[1440px]` wrappers |
| `CommerceCart` | `1613` | Remove `mx-auto max-w-[1440px]` |
| `CommerceCheckout` | `2007` | Remove `mx-auto max-w-[1440px]` |
| `CommerceStoreHeader` | `2518` | Remove `mx-auto max-w-[1440px]` |
| `CommerceStoreFooter` | `2682` | Remove `mx-auto max-w-[1440px]` |

#### Internal Content Constraints (Keep These)

These are content-level design decisions, not page-level layout — they should stay:
- `StarterHomeHero:439` — `max-w-2xl` on text column (keeps text readable)
- `StarterHomeHero:441` — `max-w-[12ch]` on heading
- `StarterStoreFooter:635` — `max-w-sm` on sidebar
- `CommerceCatalogHero:832` — `max-w-xl` on description text
- `CommerceCart:1848` — `max-w-md` on empty state
- `CommerceProductDetail:1446` — `max-w-2xl` on description text

---

### Phase 3: Update Template JSON Data

**Goal**: Existing templates should use the new Section props to produce better layouts.

#### medusa-b2b-home.json

| Section | Current | New |
|---|---|---|
| Header (StarterStoreHeader) | `purpose: "header", layout: "full", containerWidth: "lg"` | `purpose: "header", bandWidth: "bleed", contentWidth: "2xl"` |
| PromoBar | `purpose: "section", layout: "full"` | `bandWidth: "bleed", contentWidth: "2xl"` |
| Hero (StarterHomeHero) | `purpose: "section", layout: "full"` | `bandWidth: "bleed", contentWidth: "none"` (hero manages its own internal layout) |
| CollectionRails | `purpose: "section", layout: "full"` | `bandWidth: "bleed", contentWidth: "2xl"` |
| Product Grid | `purpose: "section"` | `bandWidth: "bleed", contentWidth: "xl"` |
| Footer | `purpose: "footer", layout: "full"` | `purpose: "footer", bandWidth: "bleed", contentWidth: "2xl"` |

Apply the same pattern to `medusa-b2b-category.json`, `medusa-b2b-pdp.json`, `medusa-b2b-cart.json`, `medusa-b2b-checkout.json`.

#### Files to Change

| File | Change |
|---|---|
| `mos/backend/app/templates/funnels/medusa-b2b-home.json` | Update Section props |
| `mos/backend/app/templates/funnels/medusa-b2b-category.json` | Update Section props |
| `mos/backend/app/templates/funnels/medusa-b2b-pdp.json` | Update Section props |
| `mos/backend/app/templates/funnels/medusa-b2b-cart.json` | Update Section props |
| `mos/backend/app/templates/funnels/medusa-b2b-checkout.json` | Update Section props |
| `mos/backend/app/services/template_synthesis.py` | Update synthesis to emit new Section props |

---

### Phase 4: Add Editor Presets

**Goal**: Make it easy for designers to pick good layouts without understanding the raw props.

Add a `preset` field to Section that auto-populates the detailed props:

| Preset Name | bandWidth | contentWidth | surface | padY | Use Case |
|---|---|---|---|---|---|
| Full-Bleed Hero | bleed | none | none | none | Hero/banner with media edge-to-edge |
| Narrative Band | bleed | md | none | lg | Long-form text section |
| Content Section | bleed | xl | none | md | Standard content (features, grids) |
| Wide Content | bleed | 2xl | none | md | Product grids, catalogs |
| Highlighted Section | bleed | lg | subtle | md | Callouts, proof sections |
| Card Section | bleed | lg | card | md | Isolated content block |
| Compact Header | bleed | 2xl | none | sm | Headers, nav bars |
| Compact Footer | bleed | 2xl | none | md | Footers |

Implementation: a `select` field in the Puck config that, when changed, sets `bandWidth`, `contentWidth`, `surface`, `padX`, `padY` to the preset values. The user can then override individual values.

#### Files to Change

| File | Change |
|---|---|
| `puckConfig.tsx` | Add preset field to Section, wire preset→prop mapping |

---

### Phase 5: Improve the Hero Primitive

**Goal**: Heroes should be first-class layout blocks, not content blocks squeezed into a generic Section.

Current problem: `StarterHomeHero` acts as both a content producer and a layout container. It hardcodes `min-h-[620px]`, `max-w-[1440px]`, grid columns, etc. When placed inside a Section, the two fight.

#### New Hero Architecture

Heroes should:
1. Expect to live inside a `bandWidth="bleed" + contentWidth="none"` Section
2. Own their internal layout (media placement, text column width)
3. Support these modes:
   - **Full-viewport**: `min-h-screen` with overlaid text
   - **Tall band**: `min-h-[60vh]` or `min-h-[600px]`
   - **Standard**: auto height based on content
4. Support text placement: overlaid center, overlaid left, split 50/50, anchored bottom
5. Support a constrained text column (`max-w-2xl`) independent of media width

#### Specific Changes

| File | Change |
|---|---|
| `StarterStorefrontBlocks.tsx:360–516` | Refactor `StarterHomeHero`: remove `max-w-[1440px] mx-auto`, add `heroMode` prop (fullscreen/tall/standard), add `textPlacement` prop |
| `CommerceBlocks.tsx:806–852` | Refactor `CommerceCatalogHero`: same pattern |

---

## Implementation Order

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4
   │                                    │
   └──────── Phase 5 (parallel) ────────┘
```

1. **Phase 1** (Section redesign) — This is the foundation. Everything else depends on it.
2. **Phase 2** (Strip block width wrappers) — Must happen alongside or immediately after Phase 1, otherwise blocks will be double-constrained.
3. **Phase 3** (Template updates) — Update the JSON templates to use new props. Can happen incrementally.
4. **Phase 4** (Presets) — Nice-to-have polish, can ship after Phase 3.
5. **Phase 5** (Hero refactor) — Independent work stream, can parallel with Phase 3/4.

---

## Risk Mitigation

### Breaking existing pages

- The `normalizePuckData()` migration (Phase 1) maps old props to new props automatically
- Any saved page that uses `layout: "full", containerWidth: "lg"` will be translated to `bandWidth: "bleed", contentWidth: "lg"` — same visual output
- Run the migration on all existing template JSONs in a test before deploying

### Double-containment during transition

- Phase 2 (block cleanup) must ship with Phase 1
- If we ship Phase 1 alone, blocks will have their `max-w-[1440px]` inside the new Section's `contentWidth: "2xl"` (also 1440px) — harmless but redundant
- If we ship Phase 2 alone (remove block widths) before Phase 1 — blocks will have no constraint at all if Section doesn't provide one — **dangerous, do not do this**

### PreSales / SalesPdp pages

- These families use `PreSalesPage` and `SalesPdpPage` as root wrappers, not `Section`
- They are unaffected by this refactor
- No changes needed for them

### Testing approach

Before/after visual regression on:
- medusa-b2b-home (the main storefront template)
- medusa-b2b-pdp (complex layout with multiple containment levels)
- Any existing customer pages using old Section props

---

## Expected Outcome

After this refactor, our page builder will support:

```
┌─────────────────────────────────── viewport ──────────────────────────────────┐
│                                                                               │
│  ┌──── Section: bandWidth="bleed", contentWidth="none" ────────────────────┐  │
│  │  ┌──────────────── Hero (edge-to-edge media) ─────────────────────────┐ │  │
│  │  │                                                                    │ │  │
│  │  │   ┌── text column: max-w-2xl ──┐                                   │ │  │
│  │  │   │  Headline                  │                                   │ │  │
│  │  │   │  Subheadline               │                                   │ │  │
│  │  │   │  [CTA Button]             │                                   │ │  │
│  │  │   └────────────────────────────┘                                   │ │  │
│  │  │                                                                    │ │  │
│  │  └────────────────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌──── Section: bandWidth="bleed", contentWidth="xl", bg=muted ────────────┐  │
│  │                                                                          │  │
│  │          ┌──────── max-w-7xl (1280px) centered ─────────┐               │  │
│  │          │                                               │               │  │
│  │          │   Feature Grid / Product Cards / Content      │               │  │
│  │          │                                               │               │  │
│  │          └───────────────────────────────────────────────┘               │  │
│  │                                                                          │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
│  ┌──── Section: bandWidth="bleed", contentWidth="md" ──────────────────────┐  │
│  │                                                                          │  │
│  │          ┌──────── max-w-4xl (896px) centered ──────────┐               │  │
│  │          │                                               │               │  │
│  │          │   Narrative text / Testimonials               │               │  │
│  │          │                                               │               │  │
│  │          └───────────────────────────────────────────────┘               │  │
│  │                                                                          │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

This is how omnicreatine.com and most modern Shopify storefronts compose their pages: full-bleed bands with independently constrained content columns.

---

## Summary

| What | Status | Root Cause |
|---|---|---|
| Section conflates band + frame | **Confirmed** | Our design in `puckConfig.tsx:337–437` |
| Blocks fight Section for width | **Confirmed** | 16 instances of `max-w-[1440px]` in block renders |
| containerWidth options too narrow | **Confirmed** | Max is 1280px, blocks need 1440px |
| No true full-bleed mode | **Confirmed** | `layout: "full"` still applies max-w-* |
| Puck is the bottleneck | **False** | Puck is headless; our wrapper is the bottleneck |

The fix is: redesign our Section abstraction, remove duplicate width logic from blocks, and update templates to use the new props. Puck itself needs zero changes.
