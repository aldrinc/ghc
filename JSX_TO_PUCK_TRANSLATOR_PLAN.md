# Plan: React/Tailwind JSX → Puck Block Translator

## Context

The screenshot-to-code generator produces rich React/Tailwind JSX (23 KB of layout, images, colors, typography). But the adapter in `site_import_adapter.py` throws it all away — it loads the base Honest Herbalist template and injects a few text snippets via regex. The Puck preview shows a broken skeleton ("Cart" heading + empty sections) instead of the imported site's actual content.

**Goal**: Parse the generator's React/Tailwind JSX output into Puck's component tree so the editor preview matches the screenshot-to-code preview.

## Architecture

```
Generator JSX code
       ↓
[1] JSX Pre-processor (className→class, strip expressions)
       ↓
[2] DOM Parser (stdlib html.parser → DomNode tree)
       ↓
[3] Section Identifier (nav/header/section/footer detection)
       ↓
[4] Recursive Block Translator (DOM nodes → Puck blocks)
       ↓
[5] Puck Data Assembly ({ root, content, zones })
```

Integration: Replace `_build_puck_data_from_code()` in `site_import_adapter.py` with a call to the new translator. Falls back to existing template approach on failure.

## New Files

### 1. `mos/backend/app/services/tailwind_mapper.py`

Pure functions that map Tailwind utility classes to Puck prop values. Separated for testability.

**Key mappings:**

| Tailwind pattern | Puck prop |
|---|---|
| `py-0`..`py-2` | `padY: "none"` |
| `py-3`..`py-8` | `padY: "sm"` |
| `py-10`..`py-12` | `padY: "md"` |
| `py-14`..`py-20` | `padY: "lg"` |
| `py-24`+ | `padY: "xl"` |
| `px-0`..`px-2` | `padX: "none"` |
| `px-3`..`px-4` | `padX: "sm"` |
| `px-5`..`px-8` | `padX: "md"` |
| `px-10`+ | `padX: "lg"` |
| `max-w-2xl` and below | `contentWidth: "sm"` |
| `max-w-3xl`..`max-w-4xl` | `contentWidth: "md"` |
| `max-w-5xl`..`max-w-6xl` | `contentWidth: "lg"` |
| `max-w-7xl` | `contentWidth: "xl"` |
| `max-w-[1440px]` | `contentWidth: "2xl"` |
| `bg-gray-*`, `bg-slate-*`, `bg-neutral-*` | `variant: "muted"` |
| `bg-white`, `bg-transparent` | `variant: "default"` |
| `text-6xl`..`text-5xl` | heading level 1 |
| `text-4xl`..`text-3xl` | heading level 2 |
| `text-2xl` | heading level 3 |
| `grid-cols-2` | Columns `ratio: "1:1"` |
| `grid-cols-[2fr_1fr]` | Columns `ratio: "2:1"` |

**Functions:**
- `parse_tailwind_classes(classes) -> TailwindAnalysis` — aggregate analysis
- `infer_pad_y/pad_x/content_width/variant/heading_level/text_size/button_variant/column_ratio/image_radius` — individual mappers
- `is_button_like(tag, classes) -> bool` — classifies `<a>` as button when it has bg + rounded + padding

### 2. `mos/backend/app/services/jsx_to_puck.py`

Core translator module. Contains:

**`preprocess_jsx(code: str) -> str`**
1. Strip `export default function App() { return (...) }` wrapper via regex
2. `className=` → `class=`
3. Strip `style={{...}}` objects
4. Strip JSX comments `{/* ... */}`
5. Preserve `{"text"}` string literals, strip other `{...}` expressions
6. Fix self-closing non-void tags (`<div />` → `<div></div>`)

**`parse_html(html: str) -> DomNode`**
- Uses `html.parser.HTMLParser` subclass (stdlib, no new deps)
- Builds tree of `DomNode(tag, attrs, children, classes)` dataclass instances
- Handles void elements (`img`, `br`, `hr`, `input`) implicitly
- Graceful with malformed input (unclosed tags are no-ops)

**`identify_sections(root: DomNode) -> list[SectionCandidate]`**
- `<nav>`, `<header>` → `purpose="header"`
- `<footer>` → `purpose="footer"`
- `<section>`, `<main>`, `<article>`, substantial `<div>` → `purpose="section"`

**`translate_node(node: DomNode, ctx: TranslationContext) -> list[PuckBlock]`**

Recursive translator. Pattern matchers applied in priority order:

1. **`<h1>`–`<h4>`** → `Heading` (level from tag, font-size classes refine it, align from `text-center`)
2. **`<img>`** → `Image` (preserve `src`, `alt`; radius from `rounded-*` classes)
3. **`<button>`, `<a>` with button-like classes** → `Button` (label from inner text, variant from bg presence, size from padding)
4. **`<p>`** → `Text` (size from font classes, tone from color classes, align)
5. **Text-only `<div>`/`<span>`** → `Text` (if no child elements beyond inline spans)
6. **Two-child grid/flex container** → `Columns` (ratio from grid-cols class, each child recursed into left/right slots)
7. **3+ child grid with card-like children** → `FeatureGrid` (each card: extract title from heading + text from paragraph)
8. **Container with `<blockquote>` or quote patterns** → `Testimonials` (quote, name, role)
9. **Container with `<details>`/`<summary>` or Q&A pairs** → `FAQ` (question, answer)
10. **Wrapper div** (only layout classes like flex/grid/items-*/justify-*) → flatten, recurse children
11. **Fallback**: recurse into children; if leaf with text, emit `Text`

**`translate_jsx_to_puck_data(code: str) -> dict | None`**

Top-level entry point:
1. `preprocess_jsx(code)` → HTML string
2. `parse_html(html)` → DOM tree
3. `identify_sections(root)` → section candidates
4. For each section: analyze Tailwind classes for Section props, recursively translate children
5. Assemble `{ root: { props: { title, description } }, content: [...sections], zones: {} }`
6. Return `None` if parsing fails or content is empty (triggers fallback)

### 3. `mos/backend/tests/test_tailwind_mapper.py`

Unit tests for each mapper function — pure input/output, no fixtures.

### 4. `mos/backend/tests/test_jsx_to_puck.py`

- Pre-processor tests (wrapper stripping, className conversion, JSX expression handling)
- DOM parser tests (nested elements, void elements, malformed input)
- Section identification tests (semantic tags, div children, purpose inference)
- Per-block-type translation tests (Heading, Text, Image, Button, Columns, FeatureGrid, Testimonials, FAQ)
- End-to-end test with OMNI creatine JSX example
- Fallback tests (empty code, unparseable code returns None)

## Modified Files

### 5. `mos/backend/app/services/site_import_adapter.py`

Modify `_build_puck_data_from_code()` to try the translator first:

```python
def _build_puck_data_from_code(code, html, page_type, template_id):
    # NEW: Try JSX-to-Puck translation first
    if code:
        try:
            from app.services.jsx_to_puck import translate_jsx_to_puck_data
            puck_data = translate_jsx_to_puck_data(code)
            if puck_data and puck_data.get("content"):
                return puck_data
        except Exception:
            logger.warning("JSX-to-Puck translation failed", exc_info=True)

    # EXISTING: Fall back to template-based approach (unchanged)
    template = get_funnel_template(template_id)
    ...
```

Zero regression risk — translator failure silently falls back to current behavior.

## Implementation Order

| Step | What | Why |
|------|------|-----|
| 1 | `tailwind_mapper.py` + tests | Pure functions, no dependencies, validate mapping rules |
| 2 | `jsx_to_puck.py` foundations (preprocessor, DOM parser, ID gen) + tests | Core parsing infrastructure |
| 3 | Leaf block translators (Heading, Text, Image, Button, Spacer) + tests | Simplest patterns first |
| 4 | Layout translators (Columns, Section, wrapper flattening) + tests | Composition layer |
| 5 | Compound block detectors (FeatureGrid, Testimonials, FAQ) + tests | Pattern matching |
| 6 | Top-level `translate_jsx_to_puck_data()` + end-to-end tests | Full pipeline |
| 7 | Wire into `site_import_adapter.py` with fallback | Integration |
| 8 | Manual QA against real generator outputs | Validation |

## Verification

1. **Unit tests**: `cd mos/backend && python -m pytest tests/test_tailwind_mapper.py tests/test_jsx_to_puck.py -v`
2. **Existing tests pass**: `python -m pytest tests/test_site_import_adapter.py tests/test_template_synthesis.py -v`
3. **Frontend builds**: `cd mos/frontend && npx vite build` (no frontend changes, but verify nothing broke)
4. **Manual QA**: Re-run the omnicreatine.com import, open the import detail page, verify the Puck preview now shows the actual page structure (hero with heading + image + CTA, sections below) instead of the empty Honest Herbalist template
5. **Preview verification**: Use `preview_start` → navigate to import detail → `preview_screenshot` to verify the Puck editor shows meaningful content

## Key Design Decisions

- **Backend (Python), not frontend**: The adapter already runs server-side; result is stored in `adapted_puck_data` permanently; no UI lag from heavy parsing
- **stdlib `html.parser`, no BeautifulSoup**: Generator output is well-formed JSX, not arbitrary web HTML; avoids adding a dependency
- **Fallback-first**: Translator returns `None` on any failure; adapter falls back to existing template approach; zero regression risk
- **Pattern priority order matters**: Heading/Image/Button checked before generic container; prevents headings from being wrapped in unnecessary Text blocks
- **Wrapper flattening is critical**: Generator JSX has 4-5 layers of layout divs; the translator must skip them to find actual content
