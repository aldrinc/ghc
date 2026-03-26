# Import-to-Puck Pipeline: Why Screenshot-to-Code Doesn't Translate

## The Problem

The screenshot-to-code generator produces a beautiful, faithful HTML/React reproduction of
the imported site (omnicreatine.com). But when that output is translated into Puck data for
the editor, the result is a broken skeleton: just a "Cart" heading, a product image, and
empty space inside generic Section blocks.

## The Pipeline (6 stages)

```
Screenshot ──► Generator ──► HTML extraction ──► Adapter ──► Synthesis ──► Puck Editor
                                                   ▲              ▲
                                               LOSS #1        LOSS #2
                                            (content lost)   (bypassed)
```

### Stage 1: Screenshot-to-Code (works well)
**File**: `site_import_generator_client.py`

- Takes a screenshot, sends it to the screenshot-to-code WebSocket
- Returns full React/Tailwind component code (23 KB of rich HTML with layout, colors,
  images, gradients, typography)
- This stage works — the "Screenshot-to-code preview" iframe renders beautifully

### Stage 2: HTML Extraction (works)
**File**: `site_import_adapter.py` → `_extract_html_from_code()`

- Regex extracts the HTML template literal from the React code
- Returns the full HTML string — no loss here

### Stage 3: Page Type & Family Detection (works)
**File**: `site_import_adapter.py` → `_detect_page_type_from_content()` / `_infer_site_family_from_content()`

- Scans HTML for commerce markers (`"add to cart"`, `"price"`, etc.)
- Infers `medusa-b2b-starter` family and `home` page type
- This stage works correctly

### Stage 4: Adapter — LOSS POINT #1
**File**: `site_import_adapter.py` → `_build_puck_data_from_code()`

**This is the primary failure.** The adapter does NOT reconstruct Puck blocks from the
HTML structure. Instead it:

1. Loads the **base template** for the detected family/page type
   (e.g., `medusa-b2b-home.json` — our Honest Herbalist template)
2. Extracts only **text snippets** via `_extract_content_preview()` (first 10 `<tag>text</tag>` pairs)
3. Injects those snippets into the template's existing blocks as metadata
4. **Discards the entire HTML structure, layout, images, and styling**

So `adapted_puck_data` = the Honest Herbalist base template + a handful of text overrides.
The omnicreatine layout, colors, hero image, product photography — all gone.

### Stage 5: Synthesis — LOSS POINT #2
**File**: `template_synthesis.py` → `synthesize_import()` → `_build_synthesized_puck_data()`

For `medusa-b2b-starter`, synthesis is **completely bypassed**:

```python
if family == "medusa-b2b-starter":
    return cloned  # Return base template unchanged
```

The normalized sections (which DO contain structured data about the imported site's hero,
features, testimonials, etc.) are never mapped to blocks. They're stored in the database
but ignored during Puck data generation.

For other families (`sales-pdp`, `pre-sales-listicle`), synthesis does map sections to
blocks — but even there, it only injects text/media into the base template's existing block
configs, not reconstructing layout from scratch.

### Stage 6: Puck Editor (renders what it gets)
**File**: `StorefrontVisualReviewPanel.tsx`

The editor receives the adapted Puck data (= base template with text snippets). It renders
faithfully, but the data is just the starter template — not the imported site.

## What the Data Looks Like at Each Stage

### Screenshot-to-Code Output (23 KB, rich)
```html
<div class="min-h-screen bg-white">
  <nav class="flex items-center justify-between px-6 py-4 border-b">
    <span class="text-sm font-medium">SHOP NOW</span>
    <span class="text-2xl font-bold tracking-tight">OMNI</span>
    <div class="flex items-center gap-4">...</div>
  </nav>
  <section class="grid grid-cols-2 min-h-[80vh]">
    <div class="flex flex-col justify-center px-12 py-16">
      <div class="flex items-center gap-2 text-sm text-yellow-500">★★★★★ 4.8 Rating</div>
      <span class="border rounded-full px-3 py-1">SPRING SALE 🔥</span>
      <h1 class="text-6xl font-black text-[#1a365d]">Creatine For Body & Mind</h1>
      <p>OMNI is a creatine infused gummy...</p>
      <button class="bg-[#2d4a7a] rounded-full px-8 py-4 text-white">TRY OMNI TODAY ➤</button>
    </div>
    <div class="relative bg-[#e8edf4]">
      <img src="..." alt="Omni Product Hero" />
      <div class="absolute top-4 right-4">47% OFF badge</div>
    </div>
  </section>
  <!-- ... testimonials, comparison table, FAQ, footer ... -->
</div>
```

### Adapted Puck Data (what editor gets — empty shell)
```json
{
  "content": [
    { "type": "Section", "props": { "purpose": "header", "content": [
        { "type": "StarterStoreHeader", "props": { "storeName": "OMNI Creatine" } }
    ] } },
    { "type": "Section", "props": { "content": [
        { "type": "StarterHomeHero", "props": { "title": "Cart", "description": "..." } }
    ] } },
    { "type": "Section", "props": { "content": [
        { "type": "StarterCollectionRails", "props": {} }
    ] } },
    { "type": "Section", "props": { "purpose": "footer", "content": [
        { "type": "StarterStoreFooter", "props": {} }
    ] } }
  ]
}
```

All the visual richness — gone. Just the Honest Herbalist starter template with a few
text overrides.

## Root Causes

### 1. The adapter treats screenshot-to-code output as disposable metadata
It extracts 10 text snippets and a page title, then throws away the rest. The full
HTML/React code is stored in `upstream_code` but never used for Puck block reconstruction.

### 2. There is no HTML→Puck block translator
The system has no mechanism to convert arbitrary HTML/Tailwind into Puck's component tree.
The adapter always falls back to a base template because it can't create Puck blocks from
HTML structure.

### 3. Synthesis is bypassed for the medusa-b2b-starter family
Even the normalized sections (which capture section types and content) aren't used to
assemble Puck blocks for this family.

### 4. The Puck component vocabulary is too narrow for imports
Available blocks: Section, Columns, Heading, Text, Button, Image, Spacer, FeatureGrid,
Testimonials, FAQ + commerce blocks.

The imported site has: hero with ratings badge + spring sale tag + gradient CTA + product
photography, comparison table with custom columns, video testimonial grid, multi-column
footer with social links, etc. None of these map cleanly to the existing blocks.

## How to Fix This

### Option A: HTML-to-Puck Translator (high effort, high fidelity)

Build a translator that converts the screenshot-to-code HTML into Puck blocks:

1. Parse the generated React/Tailwind code into an AST
2. Map HTML patterns to Puck blocks:
   - `<nav>` → Section(purpose=header) + Columns
   - `<section>` with hero-like structure → Section(bandWidth=bleed, contentWidth=none)
   - `<h1>` → Heading
   - `<p>` → Text
   - `<button>` → Button
   - `<img>` → Image
   - Grid layouts → Columns or FeatureGrid
3. Preserve inline styles as Puck props (variant, surface, padding)
4. Upload extracted images as assets

**Pro**: Highest fidelity — the Puck preview would match the screenshot-to-code output.
**Con**: Fragile against generator output variation; complex AST mapping.

### Option B: Rich Section Blocks (medium effort, good fidelity)

Instead of mapping HTML to granular Puck primitives, create a single "ImportedSection"
Puck block that renders the raw HTML directly:

1. Split the generated HTML into sections (by `<section>`, `<nav>`, `<footer>`)
2. Each section becomes an `ImportedSection` block with `rawHtml` prop
3. The block renders the HTML in an isolated container with scoped styles
4. Users can then replace individual imported sections with native Puck blocks over time

**Pro**: Fast to implement; preserves full visual fidelity; progressive enhancement path.
**Con**: Imported sections aren't editable field-by-field in Puck; scoped CSS isolation needed.

### Option C: AI-Powered Puck Data Generation (medium effort, variable fidelity)

Instead of regex-parsing HTML, send the screenshot-to-code output to an LLM with the
Puck component schema and ask it to generate Puck JSON:

1. Give the LLM the screenshot + generated HTML + Puck block schema
2. LLM generates a Puck `content` array using available blocks
3. Use the same normalization/synthesis pipeline but with LLM-generated mappings

**Pro**: Can handle arbitrary layouts; adapts to component vocabulary.
**Con**: Non-deterministic; may hallucinate props; needs validation.

### Option D: Fix the Existing Pipeline (low effort, incremental improvement)

Make the current pipeline actually work instead of bypassing it:

1. **Remove the medusa-b2b-starter synthesis bypass** (line 652-653 in template_synthesis.py)
2. **Add section→block mappings for medusa-b2b-starter** in `SECTION_TO_BLOCK_MAPPING`
3. **Use normalized sections to populate blocks**: hero text, feature stacks, FAQ items, etc.
4. **Extract and upload images** from the screenshot-to-code HTML as assets
5. **Map the new Section props** (bandWidth, contentWidth, surface) from the imported layout

This won't achieve pixel-perfect fidelity, but it would populate the Puck editor with
meaningful content instead of an empty Honest Herbalist shell.

## Recommended Approach

**Start with Option D** (fix existing pipeline) — this unblocks the workflow with minimal
risk. Then **add Option B** (ImportedSection block) as a parallel track to give users a
"what-you-see-is-what-you-get" starting point that they can progressively replace with
native blocks.

Option A is the long-term ideal but is a large project. Option C could supplement Option D
as an alternative to regex-based section mapping.
