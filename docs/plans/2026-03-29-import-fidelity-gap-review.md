# Decision

The current import-native translation failed the fidelity bar. It preserves section order, some copy, and some media, but it does not preserve the original section composition, layout system, typography, interaction model, or content hierarchy closely enough to replace the original imported template.

For new imports, translation should stop being "reduce the page into a handful of generic editable blocks." It needs to become "preserve each section's actual blueprint first, then expose the right editable controls on top of that blueprint."

# What Broke

## 1. Section composition was flattened too aggressively

The translator currently reduces most imported sections into a tiny generic block set:

- `ImportedNarrativeBlock`
- `ImportedItemGrid`
- `ImportedBadgeStrip`
- `ImportedOfferSelector`
- `ImportedTestimonialsGrid`
- `ImportedComparisonTable`
- `ImportedAccordion`
- `ImportedFooterLinks`

That reduction happens in [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L1444) through [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L1656).

Impact:

- complex hero sections become a generic text-plus-image card
- proof bars and feature belts lose their original density and rhythm
- compound sections with mixed text, media, stats, trust signals, and CTAs get flattened into one or two bland blocks
- the page stops looking like the original imported template

OMNI example:

- the original hero preserves the top utility/header row, rating strip, sale pill, stacked heading treatment, CTA, guarantee text, and a tightly composed hero image composition
- the translated result turns that into a generic narrative layout with a card wrapper and a simplified button

## 2. The translator is using labels as live content

The title selection logic is in [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L1775).

Current order:

1. `parsedData.title`
2. `displayName`
3. first suitable `keyText`

That is wrong for fidelity. `displayName` is a section label, not necessarily the page copy.

OMNI example:

- section `hero-section`
- `displayName = "Hero Section"`
- `parsedData.title = None`
- extracted `keyText` contains split real heading fragments: `"Creatine For"` and `"Body & Mind"`

Result:

- the translated hero title becomes `"Hero Section"` instead of `"Creatine For Body & Mind"`

This is a direct content corruption bug, not just a styling mismatch.

## 3. Heading extraction is too lossy for composed typography

Structured data extraction in [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L688) assumes headings can be recovered from simple `<h1>`, `<h2>`, or `<h3>` extraction in [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L621).

That breaks when the source export composes titles across:

- multiple spans
- line-broken fragments
- styled wrappers
- inline layout containers

OMNI example:

- the hero heading is split into separate fragments in `keyText`
- the extractor never reconstructs the actual heading string

Impact:

- titles become generic labels
- line breaks and emphasis disappear
- large-type hero sections lose their core visual identity

## 4. The renderer applies a house style instead of the imported section's style system

The imported-template render primitives are defined in [ImportedTemplateBlocks.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/imported-site/ImportedTemplateBlocks.tsx#L1).

These primitives impose:

- a shared theme token model
- generic card styling
- generic rounded corners
- generic shadows
- generic spacing
- generic typography rules
- generic section padding

Examples:

- `Card` in [ImportedTemplateBlocks.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/imported-site/ImportedTemplateBlocks.tsx#L147)
- `ImportedSection` wrapper padding and container rules in [ImportedTemplateBlocks.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/imported-site/ImportedTemplateBlocks.tsx#L199)
- `ImportedNarrativeBlock` typography/button/image treatment in [ImportedTemplateBlocks.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/imported-site/ImportedTemplateBlocks.tsx#L227)

Impact:

- imported sections are restyled into a new design language
- original spacing and alignment are lost
- typography scale and line treatment are replaced
- buttons and pills no longer match the source

This is why the translated page looks like a redesign instead of an editable version of the original.

## 5. Interaction-rich sections were simplified into generic data widgets

The purchase/gallery section is forced through `_build_offer_selector_block(...)` in [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L1532).

That translation only keeps a limited shape:

- eyebrow
- title
- body
- review text
- CTA label
- gallery images
- benefits
- offers

What it loses:

- original purchase module hierarchy
- original variant selector UI
- original thumbnail layout and active states
- original guarantee/shipping/urgency block composition
- original inline trust rows
- original motion/hover/state styling

The same pattern happens for:

- testimonials
- comparison tables
- FAQs
- footers

Each is reduced to a generic editable widget instead of preserving the original section blueprint.

## 6. Section boundaries are preserved, but intra-section structure is not

The extractor does preserve ordered source sections in [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L451), which is good.

But inside each section, the actual DOM/component structure is discarded and rebuilt from heuristics. That means the system knows:

- where a section starts and ends
- some text/media/button candidates
- some structured arrays

But it does not preserve:

- nested rows/columns
- exact grouping
- hero overlays
- repeated trust item strips
- mixed media/text compositions
- exact badge/button placements

That is the main architectural reason fidelity collapses.

## 7. Classification is useful for tagging, but destructive for rendering

Section classification in [site_import_archive.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_import_archive.py#L569) is helpful for review tags like:

- `hero`
- `bundle_selector`
- `testimonial_wall`
- `comparison_table`
- `faq`

But it becomes destructive once classification chooses the render primitive.

Example:

- section classified as `proof_bar`
- translation path forces it into `ImportedBadgeStrip` or generic narrative/grid

That means semantic classification is deciding presentation when it should only assist naming, search, edit affordances, and AI tooling.

## 8. The editor is editable, but only at the wrong abstraction layer

The page is technically editable because `ImportedPage` and `ImportedSection` are first-party Puck blocks in [puckConfig.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/funnels/puckConfig.tsx#L1562).

But the editable fields are attached to the simplified translated widgets, not to a preserved section blueprint.

Impact:

- you can edit the wrong thing cleanly
- you cannot refine the original imported layout
- the AI assistant is forced to mutate a lossy model

That means editability was achieved by sacrificing fidelity.

# OMNI-Specific Failures

## Hero section

Observed extraction:

- `displayName = "Hero Section"`
- `parsedData.title = None`
- `keyText` includes `"Creatine For"` and `"Body & Mind"` as separate fragments

Result:

- hero copy is wrong
- hero composition is simplified
- fidelity to the original hero is lost immediately at the top of the page

## Proof belts and trust strips

The original template uses dense horizontally composed proof/trust sections. The translator reduces those to badge strips or generic content. That loses:

- density
- icon rhythm
- spacing cadence
- visual continuity across the page

## Purchase section

The purchase module is the highest-value section on the page and currently the most under-modeled. The generic `ImportedOfferSelector` is not enough to preserve:

- the exact offer layout
- grouped trust items
- guarantee/shipping rows
- flavor/variant hierarchy
- gallery treatment

## Typography system

The imported page has a clear typography voice. The translated page replaces that with the generic imported block typography defined in [ImportedTemplateBlocks.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/imported-site/ImportedTemplateBlocks.tsx#L227), which changes the feel of the page even where the copy survives.

# What Needs To Change

## 1. Preserve section blueprints before making them editable

Translation should preserve a section-level blueprint instead of immediately mapping to generic presentational blocks.

Each imported section should first become something like:

- `ImportedSectionBlueprint`
- ordered child nodes
- source layout metadata
- source style tokens
- source media geometry
- extracted content fields

Then editability can be layered on top of that blueprint.

Without that step, translation will keep redesigning the page.

## 2. Separate section labeling from content extraction

`displayName` and `sectionKey` should remain review/editor labels only.

They should never be used as the visible title/body fallback for the live section.

Required change:

- remove `displayName` fallback from `_section_title(...)`
- only use content recovered from real text nodes, structured JSX extraction, or explicit unresolved markers
- if title extraction fails, the system should mark the section as unresolved instead of inventing `"Hero Section"`

## 3. Replace text heuristics with a section AST

The current extractor is regex- and snippet-driven. That is not enough for fidelity.

The import pipeline should parse the exported React section into a section AST that preserves:

- rows
- columns
- groups
- headings
- rich text fragments
- buttons
- media
- list items
- repeated cards
- tables
- accordions

That AST should be the source of truth for rendering and editing.

LLM usage should come after deterministic AST extraction, not instead of it.

## 4. Keep source styling tokens at the node level

Current translation mostly keeps only coarse theme colors/fonts.

To retain fidelity, each translated node needs preserved style metadata such as:

- layout mode
- alignment
- max width
- gap
- radius
- border
- background
- font size
- font weight
- tracking
- text transform
- decoration
- media aspect ratio

Not every Tailwind class needs to stay verbatim, but the visual intent does.

## 5. Add import-native structural primitives that mirror the source patterns

The current primitive set is too small.

The system needs import-native primitives closer to the real patterns, for example:

- `ImportedHeroSection`
- `ImportedProofStrip`
- `ImportedFeatureStack`
- `ImportedPurchaseModule`
- `ImportedTestimonialWall`
- `ImportedComparisonSection`
- `ImportedFaqSection`
- `ImportedFooterSection`

These should still be generic across imports, but they need to preserve the blueprint of the actual imported section type.

Do not jump straight to free-form runtime fallback. Do not reduce everything to a card/grid primitive either.

## 6. Use a fidelity gate before replacing the source render

The system should not automatically accept a translated section as the canonical editable version unless it passes a fidelity check.

Per section, compare:

- extracted heading/body/button/media count
- layout complexity
- interaction count
- typography complexity
- visual diff against the source render

If the translated section fails the threshold:

- keep it in review
- expose the unresolved constructs
- do not silently replace the source with the low-fidelity translation

## 7. Support hybrid editing during the transition

To preserve workflow while translation improves:

- keep the original imported runtime render as the visual reference
- store the editable translation beside it
- allow section-by-section approval of translated sections
- only materialize the translated version for sections that are good enough

This is not a long-term fallback strategy. It is a migration strategy so the editor does not destroy the imported design while the translation model is still immature.

## 8. Make the AI assistant operate on section blueprints, not generic rewritten blocks

If the AI assistant edits only the simplified translated blocks, it will keep drifting away from the source.

The AI assistant should instead receive:

- section blueprint
- extracted content fields
- preserved style tokens
- semantic tags
- unresolved constructs

Then its job becomes:

- rewrite copy
- change CTA text
- adjust offer labels
- reorder items
- edit FAQ content
- adjust proof points

without collapsing the section design.

# Recommended Implementation Order

1. Fix the hard content bug in `_section_title(...)`.
   - Stop using `displayName` as visible content fallback.

2. Add per-section unresolved-state reporting.
   - If title/body/layout reconstruction is incomplete, surface that explicitly.

3. Introduce a section blueprint schema.
   - Preserve child-node structure before rendering/editing.

4. Replace the current generic imported render path for high-complexity sections.
   - Start with hero, proof strip, and purchase module.

5. Add a fidelity review gate.
   - Do not materialize low-fidelity translations as the only editable version.

6. Rewire the AI editor to operate on blueprint-backed imported sections.
   - AI edits content and selected layout controls, not a lossy redesign.

# Bottom Line

The failure was not just a bad heuristic or a bad theme mapping. The current architecture translates by discarding too much structure too early.

If we want imported pages to stay faithful and still be editable, the system has to preserve the actual section blueprint first and only then expose structured editing controls on top of it.
