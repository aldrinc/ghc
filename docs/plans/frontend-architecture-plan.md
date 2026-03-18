# Frontend Architecture Plan: Onboarding to Closure

## Context

The MOS frontend has grown organically and now suffers from structural problems that block multi-provider expansion and clean delivery mode switching. This plan restructures the frontend to be **provider-agnostic**, **delivery-mode-aware**, and **layout-intentional**.

### Goals
1. Each campaign lifecycle phase has its own dedicated UI surface with an intentional layout
2. Ad platform publishing is provider-agnostic — Meta is the first adapter, with Bing/TikTok/others as future adapters using the same abstractions
3. Internal funnels and external URLs are cleanly swappable via a delivery mode abstraction that propagates to all downstream services
4. The operator always knows where they are in the pipeline
5. Components are maintainable (no 2000-line files)

---

## Part 1: Issues Found

### 1.1 Monolithic CampaignDetailPage (2147 lines)
- **File:** `mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`
- ~20 `useState` + ~12 `useMemo` at top, shared across 6 tabs
- Tab switching with inline JSX blocks of 100-400 lines each

### 1.2 Monolithic CampaignMetaAdsPanel (1981 lines)
- **File:** `mos/frontend/src/components/campaigns/CampaignMetaAdsPanel.tsx`
- ~35 `useState` declarations
- Hardcoded to Meta: `resolveShopHostedUrl`, `funnelId` scoping, Meta creative/adset spec schemas
- No way to swap in a different ad platform

### 1.3 Monolithic StrategyV2ReviewWorkspace (1633 lines)
- **File:** `mos/frontend/src/components/workflows/StrategyV2ReviewWorkspace.tsx`
- 6 gate types in one rendering path

### 1.4 Meta-Specific Publishing with No Provider Abstraction
- Backend already defines `PaidAdsPlatformLiteral = Literal["meta", "tiktok"]` in `schemas/paid_ads_qa.py`
- Compliance ruleset covers both Meta and TikTok (`docs/compliance/meta-tiktok-compliance-ruleset-v1.md`)
- But the frontend only has `CampaignMetaAdsPanel` — no adapter pattern, no way to add TikTok/Bing tabs
- Meta media buying agent architecture (`docs/meta-media-buying-agent.md`) uses compile/execute/observe patterns that are provider-generalizable

### 1.5 Funnel-Coupled Downstream Services
The backend has a deep dependency chain where funnels are consumed downstream:

```
AssetBrief { funnelId, funnelStage }
    → creative generation uses funnelStage to scope requirements
    → meta_review.py: asset_funnel_id_from_briefs(), filter_assets_for_funnel_scope()
    → meta_ads.py: ad set specs require destination_url from funnel resolution
    → paid_ads_qa.py: QA runs accept funnelId for scoping
```

The external funnel delivery plan (`docs/external-funnel-delivery-meta-rollout-plan.md`) extends `AssetBrief` with:
- `deliveryMode` (internal_funnel | external_urls)
- `destinationType` (pre_sales | sales)
- `destinationUrl` (resolved URL)
- `destinationLabel` (human label)

This means the frontend must:
1. Capture delivery mode at campaign level
2. For external: capture + validate URLs (pre_sales, sales, optional checkout/thank_you)
3. Propagate delivery context to creative generation, ad prep, and QA
4. Resolve destinations in a mode-aware way (not assume funnels exist)

### 1.6 Confused Routing & Navigation
- Funnels under Research (`/research/funnels`) — but they're a campaign delivery concern
- "Workflows" is a generic term for Strategy V2
- No pipeline progress visible

### 1.7 No Shared Campaign State
- Each tab independently fetches campaign data
- Only 3 contexts exist: Workspace, Product, Theme

### 1.8 Creative Review Split Across Two Monoliths

Today the creative review is fragmented:

1. **Assets tab** (CampaignDetailPage lines 1561-1738) — shows briefs with nested asset thumbnails. The brief is primary; the image is a small thumbnail in a carousel. The marketer has to click through brief-by-brief to see what was generated.

2. **Meta panel** (CampaignMetaAdsPanel, 1981 lines) — shows the actual ad as it would be sent: source swipe, generated remix, exact copy payload, and a Meta feed preview. But it's buried inside the publish flow, mixed with ad set specs, campaign config, and publish runs.

**The result:** The marketer can't scan the full set of ads at a glance. They scroll vertically through brief-by-brief cards or through a long list of Meta review cards. There's no grid. QA violations are shown in a separate QA card component — not on the individual ads where the violations actually apply.

---

## Part 2: Provider Abstraction Design

### 2.1 The Problem
Today: `CampaignMetaAdsPanel` is a 1981-line monolith that owns creative specs, ad set specs, feed previews, publish runs, and QA — all hardcoded to Meta's API shape.

Tomorrow: we need the same flow for TikTok, Bing, Google Ads — each with different creative formats, targeting models, and publish APIs, but sharing the same upstream (delivery config + creative assets).

### 2.2 Provider Registry Pattern

**New type system:** `src/types/adPlatform.ts`

```typescript
// Provider identity
type AdPlatformId = "meta" | "tiktok" | "bing" | "google_ads";

interface AdPlatformDefinition {
  id: AdPlatformId;
  label: string;                    // "Meta Ads", "TikTok Ads"
  icon: ComponentType;              // Platform icon
  supportedCreativeFormats: string[]; // ["image", "video", "carousel"]
  requiresDestinationUrl: boolean;  // Most do
  configFields: AdPlatformConfigField[]; // Platform-specific setup (ad account, pixel, etc.)
}

// Each platform has its own spec shapes
interface AdPlatformAdapter {
  // Creative spec management
  CreativeSpecCard: ComponentType<{ spec: unknown; onUpdate: ... }>;
  AdSetSpecEditor: ComponentType<{ ... }>;
  FeedPreview: ComponentType<PlatformPreviewProps>;
  PublishPanel: ComponentType<{ ... }>;
  PublishRunsList: ComponentType<{ ... }>;

  // Hooks
  useCreativeSpecs: (campaignId: string) => ...;
  useAdSetSpecs: (campaignId: string) => ...;
  usePublishRuns: (campaignId: string) => ...;
}
```

**Provider registry:** `src/providers/adPlatformRegistry.ts`

```typescript
const registry = new Map<AdPlatformId, AdPlatformAdapter>();

// Meta adapter registered at startup
registry.set("meta", {
  CreativeSpecCard: MetaCreativeSpecCard,
  AdSetSpecEditor: MetaAdSetSpecEditor,
  FeedPreview: MetaFeedPreview,
  PublishPanel: MetaPublishPanel,
  PublishRunsList: MetaPublishRunsList,
  useCreativeSpecs: useMetaCreativeSpecs,
  useAdSetSpecs: useMetaAdSetSpecs,
  usePublishRuns: useMetaPublishRuns,
});
```

### 2.3 How This Changes the Campaign Publish Tab

Instead of a single "Meta" tab, the campaign has a **Publish** tab with a **platform selector**:

```
/campaigns/:id/publish              → Platform overview (which platforms are configured)
/campaigns/:id/publish/:platformId  → Platform-specific publish workspace
```

The publish workspace is a **shell** that:
1. Reads the platform adapter from the registry
2. Renders the adapter's components in a standard layout
3. Passes delivery-mode-resolved destinations to the adapter

This means adding TikTok is:
1. Create `src/providers/tiktok/` with TikTok-specific components
2. Register the adapter
3. Done — the publish tab picks it up automatically

### 2.4 Shared vs Platform-Specific Concerns

**Shared (in the shell):**
- Delivery config resolution (destination URLs from internal funnel or external config)
- Asset selection from creative briefs
- QA/compliance checks (already multi-platform in `paid_ads_qa.py`)
- Pipeline stepper position
- Publish validation status

**Platform-specific (in the adapter):**
- Creative spec shape and editor UI
- Ad set/campaign structure and targeting
- Feed preview rendering (Meta news feed mockup vs TikTok For You page mockup)
- Publish API calls
- Platform config (ad account, pixel, page ID, etc.)

### 2.5 Platform Preview Adapters

The feed preview is **platform-specific** but renders through a common interface:

```typescript
interface PlatformPreviewProps {
  imageUrl: string | null;
  imageAlt: string;
  primaryText?: string | null;
  headline?: string | null;
  description?: string | null;
  cta?: string | null;
  destinationUrl?: string | null;
  specReady: boolean;
}

// Registry of preview renderers
type PlatformPreviewRenderer = ComponentType<PlatformPreviewProps>;

const previewRenderers: Record<AdPlatformId, PlatformPreviewRenderer> = {
  meta: MetaFeedPreview,      // Existing component — iPhone news feed mockup
  tiktok: TikTokFeedPreview,  // Future — For You page mockup
  bing: BingSearchPreview,    // Future — Search result ad mockup
  google_ads: GoogleAdPreview, // Future
};
```

The existing `MetaFeedPreview` already renders:
- Brand page icon + "Sponsored"
- Primary text (whitespace-pre-wrap)
- Image/video centered
- Domain + headline + description below
- CTA button

Each new platform just needs its own preview component following the same prop interface.

---

## Part 3: Delivery Mode Abstraction

### 3.1 Backend Contract (from rollout plan)

New `campaign_delivery_configs` table:
```
delivery_mode: "internal_funnel" | "external_urls"
pre_sales_url: string (validated HTTPS)
sales_url: string (validated HTTPS)
checkout_url: string (optional)
thank_you_url: string (optional)
validation_status: "pending" | "valid" | "invalid"
```

Destination resolution hierarchy (backend):
1. Explicit creative spec destination URL (highest priority)
2. External campaign delivery config URL for destination type
3. Internal funnel review path (fallback for internal_funnel mode)

### 3.2 Frontend Implementation

**Types:** `src/types/delivery.ts`
```typescript
type DeliveryMode = "internal_funnel" | "external_urls";
type DestinationType = "pre_sales" | "sales" | "checkout" | "thank_you";

interface CampaignDeliveryConfig {
  deliveryMode: DeliveryMode;
  preSalesUrl?: string;
  salesUrl?: string;
  checkoutUrl?: string;
  thankYouUrl?: string;
  validationStatus: "pending" | "valid" | "invalid";
  validationError?: string;
  validatedAt?: string;
}
```

**Hook:** `src/hooks/useResolvedDestinations.ts`
```typescript
// Returns resolved destination URLs regardless of delivery mode
// For internal_funnel: resolves via shop-hosted funnel URL
// For external_urls: returns validated config URLs
// Consumed by all publish platform adapters
function useResolvedDestinations(campaignId: string, funnelId?: string): {
  destinations: Map<DestinationType, string>;
  isResolved: boolean;
  validationStatus: string;
}
```

### 3.3 Downstream Impact on Frontend

**Creative generation** (Angles tab → "Generate assets" button):
- Currently passes `funnelId` to scope asset brief creation
- Must be updated: if `deliveryMode === "external_urls"`, pass delivery config instead of funnelId
- Backend already plans to extend AssetBrief with `deliveryMode`, `destinationType`, `destinationUrl`

**Publish workspace** (all platform adapters):
- Currently `CampaignMetaAdsPanel` calls `resolveShopHostedUrl()` directly
- Must use `useResolvedDestinations()` which abstracts over both modes
- Ad set spec creation passes resolved URL instead of funnel-derived URL

**QA checks** (CampaignPaidAdsQaCard):
- Currently accepts `funnelId` to scope QA runs
- Must accept either `funnelId` (internal) or explicit URLs (external)
- Backend `paid_ads_qa.py` already supports literal URLs

---

## Part 4: Layout Design Per Page

### 4.1 Design System Inventory

Current stack: Tailwind CSS + Base-UI/Radix primitives. No heavy component library.

Existing layout patterns:
- **Stat grid:** `md:grid-cols-4 xl:grid-cols-7` for metric cards
- **Split pane:** `lg:grid-cols-[220px_1fr]` (StrategyV2ReviewWorkspace)
- **Asymmetric split:** `xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]` (Assets tab)
- **Sectioned card:** `border border-border bg-transparent p-4` with `space-y-4`
- **Compact form fields:** `text-xs font-semibold uppercase tracking-[0.14em]` labels

### 4.2 Layout Principles

1. **Information density matches task type:**
   - **Scanning tasks** (overview, status) → stat grids + tables, low density
   - **Decision tasks** (angle selection, creative review) → grid/cards with detail panel, medium density
   - **Configuration tasks** (delivery setup, platform config) → form layout with validation, medium density
   - **Execution tasks** (publish, QA) → action-oriented with clear primary CTA, high density but focused

2. **Progressive disclosure:** Dense pages start collapsed, expand on interaction
3. **Consistent section anatomy:** Every section has a header (title + optional description + optional actions), body, and optional footer

### 4.3 Page-by-Page Layout Specifications

#### CampaignLayout (shell)
```
┌─────────────────────────────────────────────────────────┐
│ PageHeader: Campaign name, product, status badges       │
├─────────────────────────────────────────────────────────┤
│ PipelineStepper: [Strategy] → [Angles] → [Delivery]    │
│                  → [Creative] → [Publish] → [Manage]   │
├─────────────────────────────────────────────────────────┤
│ <Outlet /> (sub-page content)                           │
└─────────────────────────────────────────────────────────┘
```
- **Layout:** Single column, full width
- **PipelineStepper:** Horizontal step bar showing phase completion state
- Each step is clickable, navigates to the corresponding sub-route
- Active step highlighted, completed steps show checkmark, blocked steps show lock icon

#### Overview Tab (`/campaigns/:id/overview`)
**Task type:** Scanning — "Where does this campaign stand?"

```
┌──────────────────────────────────────────────────────────┐
│ Stat Grid (md:grid-cols-3 xl:grid-cols-5)                │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│ │Delivery  │ │Assets    │ │Creative  │ │Publish   │ ... │
│ │Mode      │ │Generated │ │Specs     │ │Status    │     │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
├──────────────────────────────────────────────────────────┤
│ Two-column: lg:grid-cols-[1fr_1fr]                       │
│ ┌─────────────────────┐ ┌──────────────────────────┐     │
│ │ Strategy Identity    │ │ Active Platforms         │     │
│ │ - Angle name         │ │ - Meta: configured ✓     │     │
│ │ - UMP / UMS          │ │ - TikTok: not started    │     │
│ │ - Core promise       │ │ - Bing: not started      │     │
│ └─────────────────────┘ └──────────────────────────┘     │
├──────────────────────────────────────────────────────────┤
│ Workflow Runs Table (full width)                         │
│ Kind | Status | Started | Duration | Actions            │
└──────────────────────────────────────────────────────────┘
```

- **Information density:** Low-medium. Scannable at a glance.
- **Key change:** "Active Platforms" card replaces the old single-platform assumption. Shows which ad platforms are configured for this campaign.

#### Strategy Tab (`/campaigns/:id/strategy`)
**Task type:** Reference — "What was decided in Strategy V2?"

```
┌──────────────────────────────────────────────────────────┐
│ max-w-4xl mx-auto (readable column)                      │
│                                                          │
│ ┌────────────────────────────────────────────────────┐   │
│ │ Strategy Sheet Summary                              │   │
│ │ Goal: ...          Hypothesis: ...                  │   │
│ └────────────────────────────────────────────────────┘   │
│                                                          │
│ ┌────────────────────────────────────────────────────┐   │
│ │ Channel Plan (table)                                │   │
│ │ Channel | Objective | Budget % | Notes              │   │
│ └────────────────────────────────────────────────────┘   │
│                                                          │
│ ┌────────────────┐ ┌────────────────┐                    │
│ │ Messaging       │ │ Messaging      │  (md:grid-cols-2) │
│ │ Pillar 1        │ │ Pillar 2       │                    │
│ └────────────────┘ └────────────────┘                    │
│                                                          │
│ ┌────────────────┐ ┌────────────────┐                    │
│ │ Risk 1          │ │ Mitigation 1   │  (md:grid-cols-2) │
│ └────────────────┘ └────────────────┘                    │
└──────────────────────────────────────────────────────────┘
```

- **Information density:** Medium. Readable prose + tables.
- **Layout:** Narrow centered column (`max-w-4xl`) for document-like readability.

#### Angles Tab (`/campaigns/:id/angles`)
**Task type:** Decision — "Which experiments/angles to proceed with?"

```
┌──────────────────────────────────────────────────────────┐
│ Header: Experiment count | Selected count | Actions      │
│         [Approve experiments] [Create funnels/delivery]  │
├──────────────────────────────────────────────────────────┤
│ Experiment Cards (space-y-3, each expandable)            │
│                                                          │
│ ┌────────────────────────────────────────────────────┐   │
│ │ ☐ Experiment A — "Hook: ..."                       │   │
│ │   Hypothesis: ...                                   │   │
│ │   ▸ Variants (3) | Metrics | Duration | Sample     │   │
│ │   [Edit] [Remove]                                   │   │
│ └────────────────────────────────────────────────────┘   │
│                                                          │
│ ┌────────────────────────────────────────────────────┐   │
│ │ ☑ Experiment B — "Hook: ..."  (selected state)     │   │
│ │   ...expanded variant details...                    │   │
│ └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

- **Information density:** High but managed via progressive disclosure (collapsed by default).
- **Layout:** Full width, vertical card stack with expand/collapse.

#### Delivery Tab (`/campaigns/:id/delivery`)
**Task type:** Configuration — "How do we get users to the offer?"

```
┌──────────────────────────────────────────────────────────┐
│ Delivery Mode Selector                                    │
│ ┌─────────────────────┐ ┌──────────────────────────┐     │
│ │ ○ Internal Funnel    │ │ ○ External URLs           │     │
│ │   MOS-hosted pages   │ │   Your own landing pages  │     │
│ └─────────────────────┘ └──────────────────────────┘     │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ IF internal_funnel:                                      │
│ ┌────────────────────────────────────────────────────┐   │
│ │ Funnels Table                                       │   │
│ │ Name | Angle/UMS | Status | Updated | Actions      │   │
│ │ [Generate funnels] [Publish all]                    │   │
│ └────────────────────────────────────────────────────┘   │
│                                                          │
│ IF external_urls:                                        │
│ ┌────────────────────────────────────────────────────┐   │
│ │ URL Configuration Form (max-w-2xl)                  │   │
│ │                                                     │   │
│ │ Pre-Sales Landing Page *                            │   │
│ │ [https://example.com/presale________] ✓ Validated   │   │
│ │                                                     │   │
│ │ Sales Page *                                        │   │
│ │ [https://example.com/sales__________] ✓ Validated   │   │
│ │                                                     │   │
│ │ Checkout (optional)                                 │   │
│ │ [https://__________________________ ]               │   │
│ │                                                     │   │
│ │ Thank You (optional)                                │   │
│ │ [https://__________________________ ]               │   │
│ │                                                     │   │
│ │ [Validate URLs]                                     │   │
│ │                                                     │   │
│ │ Validation: ✓ All URLs accessible, HTTPS, policy OK │   │
│ └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

- **Information density:** Low-medium. Clean form or clean table, not both.
- **Layout:** Full width for table mode; narrow centered form (`max-w-2xl`) for URL mode.
- **Key behavior:** Changing delivery mode warns about downstream impact (creative briefs, publish specs may need regeneration).

#### Creative Tab (`/campaigns/:id/creative`)
**Task type:** Decision — "Review and approve generated ad creatives"

This is the marketer's primary decision surface. Detailed in [Part 5](#part-5-creative-tab-deep-dive).

#### Publish Tab (`/campaigns/:id/publish`)
**Task type:** Execution — "Configure and launch ads on platforms"

**Platform Overview (landing page):**
```
┌──────────────────────────────────────────────────────────┐
│ Configured Platforms                                      │
│                                                          │
│ ┌─────────────────┐ ┌─────────────────┐ ┌────────────┐  │
│ │ [Meta icon]      │ │ [TikTok icon]   │ │ [+ Add     │  │
│ │ Meta Ads         │ │ TikTok Ads      │ │  Platform] │  │
│ │ ───────          │ │ ───────          │ │            │  │
│ │ Specs: 12        │ │ Not configured   │ │            │  │
│ │ Ready: 8         │ │ [Configure →]    │ │            │  │
│ │ Published: 0     │ │                  │ │            │  │
│ │ [Open →]         │ │                  │ │            │  │
│ └─────────────────┘ └─────────────────┘ └────────────┘  │
├──────────────────────────────────────────────────────────┤
│ Shared QA / Compliance                                   │
│ CampaignPaidAdsQaCard (runs against all platforms)       │
└──────────────────────────────────────────────────────────┘
```

**Platform Workspace (`/campaigns/:id/publish/meta`):**
```
┌──────────────────────────────────────────────────────────┐
│ Platform Header: [Meta icon] Meta Ads                     │
│ Config: Ad Account ••1234 | Page: Brand Page | Pixel: ✓  │
├──────────────────────────────────────────────────────────┤
│ Stat Grid (md:grid-cols-4 xl:grid-cols-7)                │
│ [Briefs] [Assets] [Creative Specs] [Ad Sets] [Inc] [Exc]│
├──────────────────────────────────────────────────────────┤
│ Campaign Structure Config                                │
│ Campaign type (CBO/ABO) | Budget | Schedule              │
├──────────────────────────────────────────────────────────┤
│ Ad Set Specs Table                                       │
│ Name | Targeting | Budget | Bid | Destination | Status   │
│ [Edit] per row                                           │
├──────────────────────────────────────────────────────────┤
│ Publish Validation                                       │
│ ✓ All specs valid | ✓ QA passed | ✓ Destinations resolved│
│ [Publish Campaign]                                       │
├──────────────────────────────────────────────────────────┤
│ Publish History (collapsible)                            │
│ Run ID | Status | Created | Assets | Actions             │
└──────────────────────────────────────────────────────────┘
```

- **Information density:** High — but focused on execution. Campaign config + ad sets + publish CTA.
- **Layout:** The adapter pattern means this layout is per-platform. Each adapter owns its publish workspace layout.
- **Key change:** Destination URLs come from `useResolvedDestinations()`, not hardcoded funnel resolution. Creative review has already happened upstream on the Creative tab.

---

## Part 5: Creative Tab Deep Dive

### 5.1 Vision

The Creative tab becomes **the marketer's decision surface**. It shows a **grid of ads as they would appear to the end user**, with:

- The platform feed preview as the visual anchor
- Ad copy visible alongside
- QA violation indicators overlaid directly on each card
- Brief metadata accessible on demand but not dominating the view
- Include/exclude controls per ad
- Works for Meta today, extensible to TikTok/Bing/Google via platform preview adapters

### 5.2 Data Model

Each "reviewable ad" is a **MetaPipelineAsset** (to be generalized as **AdPipelineAsset**) — a unified object containing:

```
AdPipelineAsset {
  asset: {
    id, public_url, asset_kind, content_type, width, height,
    ai_metadata: {
      assetBriefId,
      requirementIndex,
      swipeSourceLabel,
      swipeCopyPack: {
        meta_primary_text, meta_headline, meta_description, meta_cta,
        selected_variation, funnel_stage, angle, hook
      },
      swipeCopyInputs: { angleUsed, destinationPage }
    }
  },
  creative_spec?: {
    id, primary_text, headline, description, call_to_action_type,
    destination_url, status, metadata_json
  },
  adset_specs?: AdSetSpec[],
  platform_data?: { upload, creatives, ads, campaign }
}
```

QA findings link to ads via:
```
PaidAdsQaFinding.artifactType === "creative_spec"
PaidAdsQaFinding.artifactRef === creative_spec.id
creative_spec.asset_id === asset.id
```

Publish inclusion/exclusion via:
```
PublishSelection {
  assetId, decision: "excluded" | null
}
```

### 5.3 Creative Tab Layout

#### Top-Level Structure

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Creative Tab Header                                                      │
│                                                                          │
│ Filters: [All] [Meta] [TikTok]  |  [All] [Included] [Excluded]         │
│          [All] [Has Violations] [Clean]                                  │
│                                                                          │
│ Stats: 24 ads  ·  18 included  ·  6 excluded  ·  3 violations           │
│                                                                          │
│ Actions: [Generate Assets] [Run QA] [Prepare Specs]                      │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ Campaign-Level Violation Banner (if any)                                 │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ ⚠ META-CAMPAIGN-001 · Campaign has no Meta creative specs           │ │
│ │   Fix: Generate creative specs before publishing. [Prepare Specs]   │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ Ad Review Grid (responsive: 1-col mobile, 2-col lg, 3-col xl)          │
│                                                                          │
│ ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐        │
│ │  Ad Card 1       │  │  Ad Card 2       │  │  Ad Card 3       │        │
│ │  (see below)     │  │                  │  │  ⚠ 2 violations  │        │
│ │                  │  │                  │  │                  │        │
│ └──────────────────┘  └──────────────────┘  └──────────────────┘        │
│                                                                          │
│ ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐        │
│ │  Ad Card 4       │  │  Ad Card 5       │  │  Ad Card 6       │        │
│ │                  │  │  (excluded)       │  │                  │        │
│ │                  │  │  dimmed + overlay  │  │                  │        │
│ └──────────────────┘  └──────────────────┘  └──────────────────┘        │
│                                                                          │
│ ... (virtualized if >20 cards)                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

Grid CSS: `grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4`

#### Ad Card Design

Each card represents one generated asset + its creative spec + its QA status.

```
┌─────────────────────────────────────────────┐
│ Card Header                                  │
│ ┌─────────────┐                    ┌──────┐ │
│ │ [Meta icon]  │  Req 2 · Angle A  │ ☐/☑  │ │
│ │ Feed Ad      │  "Value + Proof"   │      │ │
│ └─────────────┘                    └──────┘ │
├─────────────────────────────────────────────┤
│                                             │
│  Platform Feed Preview                      │
│  ┌─────────────────────────────────────┐    │
│  │ ┌──────┐                            │    │
│  │ │Brand │  Brand Page · Sponsored    │    │
│  │ └──────┘                            │    │
│  │                                     │    │
│  │ Primary text goes here. This is     │    │
│  │ the main ad copy that the user      │    │
│  │ sees in their feed...               │    │
│  │                                     │    │
│  │ ┌─────────────────────────────┐     │    │
│  │ │                             │     │    │
│  │ │     [ Ad Creative Image ]   │     │    │
│  │ │                             │     │    │
│  │ └─────────────────────────────┘     │    │
│  │                                     │    │
│  │ example.com                         │    │
│  │ Headline text here                  │    │
│  │ Description text                    │    │
│  │              ┌──────────────┐       │    │
│  │              │  Shop Now →  │       │    │
│  │              └──────────────┘       │    │
│  └─────────────────────────────────────┘    │
│                                             │
├─────────────────────────────────────────────┤
│ Violation Banner (conditional)              │
│ ┌─────────────────────────────────────────┐ │
│ │ ⚠ 2 violations                          │ │
│ │                                         │ │
│ │ ● META-COPY-002 · blocker              │ │
│ │   Copy references private information   │ │
│ │                                         │ │
│ │ ● META-LP-005 · medium                 │ │
│ │   No privacy policy on destination      │ │
│ │                                         │ │
│ │ [View details]                          │ │
│ └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────┤
│ Card Footer                                  │
│ [Exclude] [Edit Copy] [▸ Details]            │
└─────────────────────────────────────────────┘
```

#### Card States

**Included (default):**
- Full color, normal border (`border-border`)
- Checkbox checked
- All controls active

**Excluded:**
- Reduced opacity (`opacity-50`)
- Overlay with "Excluded" label
- Checkbox unchecked
- Click "Restore" to re-include

**Has Blocker Violations:**
- Red left border (`border-l-4 border-l-danger`)
- Violation banner expanded by default
- "Exclude" button emphasized

**Has Non-Blocker Violations:**
- Amber left border (`border-l-4 border-l-accent`)
- Violation banner collapsed by default (expandable)

**Spec Not Ready:**
- Dashed border (`border-dashed`)
- Preview shows placeholder with "Prepare specs" prompt
- Feed preview renders with available data from swipeCopyPack if present

### 5.4 Ad Detail Panel (Slide-Over)

When the marketer clicks "Details" on an ad card, a slide-over panel opens from the right showing the full picture:

```
┌──────────────────────────────────────────────────┐
│ Ad Detail Panel (slide-over from right, w-[480px])│
│                                                   │
│ ╔═══════════════════════════════════════════════╗ │
│ ║ Full Platform Preview (larger)                ║ │
│ ║ [Same feed preview but bigger]                ║ │
│ ╚═══════════════════════════════════════════════╝ │
│                                                   │
│ ┌───────────────────────────────────────────────┐ │
│ │ Ad Copy (editable)                            │ │
│ │                                               │ │
│ │ Primary Text                                  │ │
│ │ ┌─────────────────────────────────────────┐   │ │
│ │ │ [textarea: editable primary text]       │   │ │
│ │ └─────────────────────────────────────────┘   │ │
│ │                                               │ │
│ │ Headline                                      │ │
│ │ ┌─────────────────────────────────────────┐   │ │
│ │ │ [input: editable headline]              │   │ │
│ │ └─────────────────────────────────────────┘   │ │
│ │                                               │ │
│ │ Description                                   │ │
│ │ ┌─────────────────────────────────────────┐   │ │
│ │ │ [input: editable description]           │   │ │
│ │ └─────────────────────────────────────────┘   │ │
│ │                                               │ │
│ │ CTA Button                                    │ │
│ │ ┌─────────────────────────────────────────┐   │ │
│ │ │ [select: Shop Now ▼]                    │   │ │
│ │ └─────────────────────────────────────────┘   │ │
│ │                                               │ │
│ │ Destination URL                               │ │
│ │ ┌─────────────────────────────────────────┐   │ │
│ │ │ [input: destination URL]                │   │ │
│ │ └─────────────────────────────────────────┘   │ │
│ │                                               │ │
│ │ [Save Changes]                                │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌───────────────────────────────────────────────┐ │
│ │ QA Violations (if any)                        │ │
│ │                                               │ │
│ │ Finding 1: META-COPY-002 (blocker)            │ │
│ │ Title: Copy references private information    │ │
│ │ Message: Full explanation text here...         │ │
│ │ Fix: 1. Remove PII from primary text          │ │
│ │      2. Re-run QA after changes               │ │
│ │ Evidence: "Your name John..." (highlighted)   │ │
│ │ Policy: Meta Advertising Standards §4.2       │ │
│ │                                               │ │
│ │ Finding 2: ...                                │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌───────────────────────────────────────────────┐ │
│ │ ▸ Brief Metadata (collapsed by default)       │ │
│ │                                               │ │
│ │   Brief ID: brief_abc123                      │ │
│ │   Experiment: Experiment A                    │ │
│ │   Variant: Variant 1                          │ │
│ │   Angle: "Health benefits"                    │ │
│ │   Hook: "Did you know..."                     │ │
│ │   Funnel Stage: pre-sales                     │ │
│ │   Channel: meta / feed                        │ │
│ │   Destination: Internal funnel / Page 1       │ │
│ │                                               │ │
│ │   Creative Concept: ...                       │ │
│ │   Tone Guidelines: ...                        │ │
│ │   Constraints: ...                            │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌───────────────────────────────────────────────┐ │
│ │ ▸ Creative Lineage (collapsed by default)     │ │
│ │                                               │ │
│ │   Asset ID: asset_xyz789                      │ │
│ │   Created: 2026-03-14 14:32                   │ │
│ │   Source Swipe: [thumbnail] "Brand X ad"      │ │
│ │   Batch: batch:abc123                         │ │
│ │   Generation: Gemini 2.5 Flash                │ │
│ │   Stage 1 Variation: "Value + Proof"          │ │
│ │   Ad Set Specs: spec_001, spec_002            │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌───────────────────────────────────────────────┐ │
│ │ ▸ Source Swipe Image (collapsed by default)   │ │
│ │                                               │ │
│ │   [Large source swipe image preview]          │ │
│ │   Source: "Brand X Facebook Ad"               │ │
│ │   URL: [link]                                 │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ Footer: [Exclude from Package] [Close]            │
└──────────────────────────────────────────────────┘
```

**Key design decisions:**
- Ad copy is **editable** in the detail panel — changes update the creative spec
- QA violations shown with full context (evidence, fix guidance, policy reference)
- Brief metadata is **collapsed by default** — available when needed but doesn't dominate
- Source swipe comparison available but tucked away
- Saving copy changes triggers a live preview update

### 5.5 QA Integration Design

#### Per-Card Violation Indicators

When a QA run exists for the campaign, findings are mapped to individual ad cards:

```typescript
// Build a lookup: creative_spec.id → findings[]
function buildFindingsBySpec(run: PaidAdsQaRun): Map<string, PaidAdsQaFinding[]> {
  const map = new Map<string, PaidAdsQaFinding[]>();
  for (const finding of run.findings) {
    if (finding.artifactType === "creative_spec" && finding.artifactRef) {
      const list = map.get(finding.artifactRef) ?? [];
      list.push(finding);
      map.set(finding.artifactRef, list);
    }
  }
  return map;
}
```

#### Violation Severity Aggregation Per Card

```typescript
type CardViolationSummary = {
  total: number;
  blocker: number;
  high: number;
  medium: number;
  low: number;
  maxSeverity: "blocker" | "high" | "medium" | "low" | null;
};
```

**Visual rules:**
- `maxSeverity === "blocker"` → red left border, violation banner auto-expanded, "Exclude" button visually emphasized
- `maxSeverity === "high"` → red left border, violation banner collapsed but visible
- `maxSeverity === "medium" | "low"` → amber left border, violation banner collapsed
- `maxSeverity === null` → no violation indicator (clean)

#### QA Actions on the Creative Tab

**Run QA button** (in tab header):
- Triggers a new QA run scoped to the campaign
- Shows progress indicator while running
- On completion, findings propagate to all ad cards automatically

**Per-card actions:**
- "View details" → opens detail panel scrolled to violations section
- "Exclude" → marks ad as excluded (bypasses the violation)
- "Edit Copy" → opens detail panel with copy editor focused (fix the violation)

#### Campaign-Level Findings

Findings with `artifactType === "campaign"` (e.g., "Campaign has no creative specs") are shown in a **separate banner above the grid**, not on individual cards.

### 5.6 Interaction Flows

**Flow 1: First-Time Review (Happy Path)**
1. Marketer lands on Creative tab
2. Sees grid of 12 ad cards, each showing feed preview
3. Scans the grid — everything looks good
4. Clicks "Run QA" → QA runs, all pass → green "All clear" banner
5. Done — moves to Publish tab

**Flow 2: Review with Violations**
1. Marketer lands on Creative tab
2. Sees grid — 3 cards have red left borders
3. Clicks on a violated card → detail panel opens
4. Reads violation: "Copy references private information"
5. Sees evidence: the exact text flagged
6. Edits the primary text in the copy editor
7. Clicks "Save Changes" → spec updated → preview refreshes
8. Clicks "Run QA" again → violation cleared
9. Alternatively: clicks "Exclude" if the ad isn't worth fixing

**Flow 3: Bulk Review**
1. Marketer filters to "Has Violations" → only violated cards shown
2. Reviews each, decides to exclude 1 and fix 2
3. Filters to "Excluded" → sees all excluded ads
4. Confirms the exclusions are intentional
5. Filters back to "All" → clean view

**Flow 4: Multi-Platform**
1. Marketer has both Meta and TikTok configured
2. Creative tab shows all ads
3. Filter: [Meta] shows Meta feed previews, [TikTok] shows TikTok previews
4. Same assets, different preview renderers
5. QA runs per platform, violations show platform badge

### 5.7 Relationship to Publish Tab

The Creative tab is **upstream of Publish**. The flow:

1. **Creative tab**: Marketer reviews ads, fixes violations, excludes bad ones → produces a clean set of included ads with passing QA
2. **Publish tab**: Takes the included, QA-passed ads and manages the actual publishing (campaign config, ad set specs, budget, scheduling, publish runs)

The Publish tab **respects** the Creative tab's decisions:
- Only included ads (non-excluded) appear in publish
- Publish tab shows a "QA not passing" blocker if violations exist
- The publish adapter's spec list comes from the filtered creative set

**What moves from the current Meta panel to the Creative tab:**
- Feed preview rendering
- Include/exclude controls
- QA violation display per ad
- Ad copy viewing (and now editing)

**What stays in the Publish tab (per-platform):**
- Campaign structure config (CBO, budget, etc.)
- Ad set spec editor (targeting, bidding)
- Publish validation and publish run execution
- Publish history

---

## Part 6: Component Architecture

### 6.1 New Route Structure

```
/strategy                              (renamed from /workflows)
/strategy/:workflowId                  (renamed from /workflows/:workflowId)
/strategy/:workflowId/research/:key    (renamed from /workflows/:workflowId/research/:stepKey)

/campaigns/:campaignId                 → CampaignLayout (shell + pipeline stepper)
/campaigns/:campaignId/overview        → CampaignOverviewTab
/campaigns/:campaignId/strategy        → CampaignStrategyTab
/campaigns/:campaignId/angles          → CampaignAnglesTab
/campaigns/:campaignId/delivery        → CampaignDeliveryTab
/campaigns/:campaignId/creative        → CampaignCreativeTab
/campaigns/:campaignId/publish         → CampaignPublishTab (platform overview)
/campaigns/:campaignId/publish/:platform → PlatformPublishWorkspace (adapter-driven)
```

### 6.2 CampaignContext + CampaignLayout

**`src/contexts/CampaignContext.tsx`:**
Consolidates the ~20 hooks from CampaignDetailPage (lines 230-596):
- `useCampaign`, `useWorkflows`, `useLatestArtifact`, `useArtifacts`, `useFunnels`
- `useCampaignStrategyV2Launches`, `useProduct`
- NEW: `useCampaignDelivery` — fetches delivery config
- NEW: `useCampaignPipeline` — derives phase completion from all the above

**`src/pages/campaigns/CampaignLayout.tsx`:**
- Fetches data, provides CampaignContext
- Renders PageHeader + PipelineStepper + `<Outlet />`
- ~150 lines total

### 6.3 Pipeline Abstraction

**Phases (provider-agnostic):**
```
Strategy → Angles → Delivery → Creative → Publish Prep → Publish Launch → Management
```

**`src/hooks/useCampaignPipeline.ts`:**
Derives phase status from existing query data (no new backend endpoints):
- Strategy: complete when latest strategy V2 workflow has `status === "completed"`
- Angles: complete when experiment specs are approved
- Delivery: complete when delivery config is validated (either funnels published OR external URLs validated)
- Creative: complete when asset briefs have generated assets
- Publish Prep: complete when at least one platform has specs ready
- Publish Launch: complete when at least one platform has a successful publish run
- Management: active when published campaigns exist

### 6.4 Provider Adapter File Structure

```
src/
  providers/
    adPlatformRegistry.ts              // Registry + types
    meta/
      MetaAdapter.ts                   // Implements AdPlatformAdapter
      MetaCreativeSpecCard.tsx         // Per-creative review card
      MetaFeedPreview.tsx              // iPhone news feed mockup
      MetaAdSetSpecEditor.tsx          // Ad set targeting/budget form
      MetaPublishPanel.tsx             // Publish config + validation + CTA
      MetaPublishRunsList.tsx          // Publish history table
      useMetaPipeline.ts              // Encapsulates Meta's ~35 useState + useMemo
      useMetaCreativeSpecs.ts         // API hook
      useMetaAdSetSpecs.ts            // API hook
      useMetaPublishRuns.ts           // API hook
    tiktok/                           // Future — same adapter interface
    bing/                             // Future — same adapter interface
```

### 6.5 Creative Tab Components

```
src/
  components/
    creative/
      CreativeReviewGrid.tsx           // Grid container with responsive columns
      AdReviewCard.tsx                 // Individual ad card (preview + violations + controls)
      AdDetailPanel.tsx                // Slide-over detail panel
      AdCopyEditor.tsx                 // Editable copy fields with live preview
      PlatformPreviewShell.tsx         // Wraps platform-specific preview renderer
      ViolationBanner.tsx              // Per-card violation summary
      ViolationDetail.tsx              // Full violation detail (in panel)
      CampaignViolationsBanner.tsx     // Campaign-level findings above grid
      CreativeFilterBar.tsx            // Platform + status + violation filters

  providers/
    previewRegistry.ts                 // Maps platform → preview component

  hooks/
    useCreativeReview.ts               // Combines pipeline assets + QA findings + publish selections
    useFindingsBySpec.ts               // Maps QA findings to creative specs → assets
    useAdCopyMutation.ts               // Updates creative spec copy fields
```

### 6.6 AdReviewItem Type

```typescript
type AdReviewItem = {
  // Core identity
  assetId: string;
  specId: string | null;  // null if spec not yet prepared

  // Display data
  imageUrl: string | null;
  imageAlt: string;
  assetKind: "image" | "video";

  // Ad copy (from creative spec or swipe copy pack fallback)
  primaryText: string | null;
  headline: string | null;
  description: string | null;
  cta: string | null;
  destinationUrl: string | null;
  copySource: "creative_spec" | "swipe_copy_pack" | "none";

  // Context
  platform: AdPlatformId;
  briefId: string | null;
  experimentName: string | null;
  variantName: string | null;
  angle: string | null;
  hook: string | null;
  funnelStage: string | null;
  selectedVariation: string | null;
  requirementIndex: number | null;

  // Lineage
  sourceSwipeLabel: string | null;
  sourceSwipeUrl: string | null;
  generationGroup: string | null;
  createdAt: string;

  // Status
  specReady: boolean;
  publishDecision: "excluded" | null;
  violations: CardViolationSummary;
  findings: PaidAdsQaFinding[];  // The actual findings for detail view

  // Full objects for detail panel
  asset: ProductAsset;
  creativeSpec: CreativeSpec | null;  // Platform-agnostic reference
  adsetSpecs: AdSetSpec[];
  brief: AssetBrief | null;
};
```

### 6.7 Creative Tab Data Flow

```
CampaignCreativeTab
  ├── useCampaignContext()              // Gets campaign, assets, briefs, funnels
  ├── useCreativeReview(campaignId)     // Combines:
  │     ├── pipeline assets (existing query)
  │     ├── QA run + findings (existing query)
  │     ├── publish selections (existing query)
  │     └── returns: AdReviewItem[]
  │
  ├── CreativeFilterBar                 // Filters by platform, inclusion, violations
  ├── CampaignViolationsBanner          // Campaign-level findings
  └── CreativeReviewGrid
        └── AdReviewCard[]              // One per AdReviewItem
              ├── PlatformPreviewShell  // Renders MetaFeedPreview (or TikTok etc.)
              ├── ViolationBanner       // If findings exist for this spec
              └── onClick → AdDetailPanel (slide-over)
                    ├── Large preview
                    ├── AdCopyEditor    // Editable copy fields
                    ├── ViolationDetail // Full violation info
                    ├── Brief metadata  // Collapsed
                    └── Lineage info    // Collapsed
```

### 6.8 Decomposed CampaignDetailPage

| Current Tab | New File | Lines (est.) |
|---|---|---|
| overview | `pages/campaigns/tabs/CampaignOverviewTab.tsx` | ~200 |
| strategy | `pages/campaigns/tabs/CampaignStrategyTab.tsx` | ~180 |
| experiments | `pages/campaigns/tabs/CampaignAnglesTab.tsx` | ~300 |
| funnels + external | `pages/campaigns/tabs/CampaignDeliveryTab.tsx` | ~250 |
| assets → creative grid | `pages/campaigns/tabs/CampaignCreativeTab.tsx` | ~150 (shell, logic in hooks/components) |
| meta → publish | `pages/campaigns/tabs/CampaignPublishTab.tsx` | ~150 |
| (platform workspace) | `pages/campaigns/tabs/PlatformPublishWorkspace.tsx` | ~100 (shell) |

**Extracted shared components:**
- `components/campaigns/ExperimentSpecEditDialog.tsx` (~240 lines)
- `components/campaigns/DeliveryModeSelector.tsx` (~80 lines)
- `components/campaigns/ExternalUrlsForm.tsx` (~150 lines)
- `components/campaigns/CampaignPipelineStepper.tsx` (~120 lines)
- `components/campaigns/PlatformCard.tsx` (~80 lines)

### 6.9 Decomposed StrategyV2ReviewWorkspace

| Concern | New File | Lines (est.) |
|---|---|---|
| Gate progress sidebar | `components/workflows/StrategyGateProgress.tsx` | ~100 |
| File review panel | `components/workflows/StrategyReviewFilePanel.tsx` | ~150 |
| Per-gate forms (6) | `components/workflows/gates/*.tsx` | ~100 each |

Parent orchestrator shrinks to ~200 lines.

---

## Part 7: Backend Integration Points

### 7.1 New/Modified Backend Endpoints the Frontend Will Consume

**Delivery config (from rollout plan Phase 1):**
- `GET /campaigns/{id}/delivery-config` — fetch current delivery config
- `PUT /campaigns/{id}/delivery-config` — set delivery mode + URLs
- `POST /campaigns/{id}/delivery-config/validate` — trigger URL validation

**Modified existing endpoints:**
- `POST /campaigns/{id}/meta/review-setup` — already supports literal URLs via resolution hierarchy
- `POST /meta/specs/adsets` — `destination_url` now comes from delivery config resolution
- `POST /paid-ads-qa/runs` — already accepts external URLs; frontend needs to pass them

### 7.2 Frontend Must Propagate Delivery Context To:

1. **Asset brief creation** (Angles tab → "Create funnels/delivery" button):
   - If `external_urls`: skip funnel creation, create briefs with `deliveryMode: "external_urls"` + resolved URLs
   - If `internal_funnel`: existing flow unchanged

2. **Creative generation** (Creative tab → "Generate assets"):
   - Brief already carries delivery context from step 1
   - No change needed if briefs are created correctly

3. **Publish spec creation** (Publish workspace → "Generate creative specs"):
   - Use `useResolvedDestinations()` to get URLs
   - Pass resolved URL to ad set spec creation (replaces `resolveShopHostedUrl`)

4. **QA runs** (Creative tab → "Run QA"):
   - Pass delivery mode + resolved URLs to QA run request
   - Backend already handles both modes

---

## Part 8: Implementation Order

### Phase 0: Foundation (no behavior change, no risk)
1. Create `CampaignContext` provider wrapping existing hooks
2. Create `CampaignLayout` with `<Outlet />` wrapping existing CampaignDetailPage
3. Rename `/workflows` → `/strategy` with redirects
4. Update sidebar labels

### Phase 1: Campaign Sub-Route Extraction
1. Extract each tab into its own routed sub-page, consuming from CampaignContext
2. One tab at a time: overview → strategy → angles → delivery → publish
3. Verify each extraction independently before moving to next
4. Delete tab content from monolithic CampaignDetailPage as each is extracted

### Phase 2: Creative Tab (Ad-First Review Grid)
1. Extract `MetaFeedPreview` from CampaignMetaAdsPanel into `providers/meta/MetaFeedPreview.tsx`
2. Create `useCreativeReview` hook assembling AdReviewItem[] from existing data
3. Create `AdReviewCard` component rendering platform preview + basic status
4. Create `CreativeReviewGrid` rendering cards in responsive grid
5. Replace current Assets tab content with the new grid
6. Create `useFindingsBySpec` hook mapping QA findings to cards
7. Create `ViolationBanner` + `CampaignViolationsBanner` components
8. Add violation visual indicators to AdReviewCard (left border, badge)
9. Create `AdDetailPanel` slide-over with `AdCopyEditor`
10. Create `useAdCopyMutation` hook for saving spec changes
11. Add brief metadata and lineage as collapsed sections in detail panel
12. Create `CreativeFilterBar` with platform, inclusion, and violation filters
13. Create `PlatformPreviewShell` + `previewRegistry.ts` for multi-platform support

### Phase 3: Delivery Tab + Mode Abstraction
1. Create delivery types (`src/types/delivery.ts`)
2. Create `useResolvedDestinations` hook
3. Create `DeliveryModeSelector` + `ExternalUrlsForm` components
4. Create `CampaignDeliveryTab` combining funnels table + new delivery mode UI
5. Remove funnels from Research sidebar
6. Wire delivery config to backend endpoints (as they become available)

### Phase 4: Provider Abstraction + Publish Tab
1. Create `AdPlatformAdapter` types and registry
2. Extract Meta-specific components from `CampaignMetaAdsPanel` into `providers/meta/`
3. Create Meta adapter implementing the interface
4. Create `CampaignPublishTab` (platform overview) and `PlatformPublishWorkspace` (adapter shell)
5. Register Meta adapter → existing Meta flow works through new abstraction
6. Shrink/delete `CampaignMetaAdsPanel`

### Phase 5: Pipeline Stepper + Strategy Review Decomposition
1. Create `useCampaignPipeline` hook
2. Create `CampaignPipelineStepper` component, add to CampaignLayout
3. Extract StrategyV2ReviewWorkspace gate components
4. Extract file review panel and gate progress sidebar

### Phase 6: Polish + Delivery Mode Downstream Wiring
1. Wire delivery mode propagation to creative generation path
2. Wire `useResolvedDestinations` into all publish platform adapters
3. Update breadcrumbs to show pipeline position
4. Clean up duplicate utilities
5. Remove dead code and legacy redirects (after sufficient time)

---

## Part 9: Verification Plan

### Per-Phase Verification

**Phase 0:** Routes still work. Campaign page renders identically. Redirects from old workflow URLs work.

**Phase 1:** Each extracted tab renders its content identically. No data loss. Navigation between tabs works. Deep-linking to specific tabs works.

**Phase 2:**
- Ad grid shows all generated assets as feed preview cards
- Cards show correct platform preview (Meta feed mockup)
- QA violations appear on correct cards with severity-based visual indicators
- Clicking a card opens detail panel with full preview, editable copy, violations, and collapsed metadata
- Copy edits save to creative spec and refresh preview
- Exclude/include works per card
- Filters correctly narrow the grid
- Campaign-level findings show in banner above grid

**Phase 3:** Delivery mode selector appears. Internal funnel mode shows existing funnels table. External URL mode shows form with validation. Switching modes warns about downstream impact.

**Phase 4:** Meta publish flow works identically through new adapter abstraction. Platform overview shows Meta card. Clicking through to Meta workspace shows same UI as before. Adding a mock TikTok adapter entry shows it appears in the overview.

**Phase 5:** Pipeline stepper shows in campaign layout. Phases reflect actual campaign state. Clicking phases navigates to correct sub-route. Strategy review workspace gates still function.

**Phase 6:** External URL campaign can go through full flow: set URLs → generate assets → create publish specs → publish. QA runs work for both delivery modes. No regressions on internal funnel path.

### Cross-Cutting Verification
- All existing onboarding wizard flows still work
- Strategy V2 review + launch still creates campaigns correctly
- Meta publishing full flow (specs → review → publish) works identically
- No console errors, no broken routes, no data fetching regressions

---

## Part 10: Open Questions

1. **Copy editing scope**: Should copy edits on the Creative tab update the creative spec directly? Or create a draft that needs explicit "apply"? Direct editing is simpler. Draft mode is safer but adds complexity.

2. **Video assets**: Current MetaFeedPreview renders images. Videos will need a player in the preview. Should we use a thumbnail-on-hover-play pattern in the grid, with full video in the detail panel?

3. **Bulk actions**: Should the grid support multi-select for bulk exclude/include? Checkboxes on cards with a floating action bar?

4. **Spec preparation**: Currently "Prepare Meta review" is a batch action that creates specs from swipe copy packs. In the new model, should this happen automatically when the Creative tab loads? Or remain a manual trigger?
