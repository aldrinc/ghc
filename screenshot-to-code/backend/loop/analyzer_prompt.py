from loop.contracts import (
    BlueprintOutlineSpec,
    BlueprintValidationReport,
    ReferenceBundle,
    RequirementsSpec,
    ValidationReport,
)
from loop.frontend_developer_policy import build_frontend_developer_policy
from loop.prompts import (
    compact_blueprint_validation_report_for_prompt,
    compact_requirements_for_prompt,
    compact_validation_report_for_prompt,
    full_live_dom_for_prompt,
    MAX_OUTLINE_JSON_CHARS,
    reference_summary,
    summarize_html_landmarks,
    summarize_design_system_preflight_for_prompt,
    summarize_live_reference_for_prompt,
    truncate_html_context,
    truncate_json_context,
)
from prompts.policies import (
    build_judgment_policy,
    build_selected_stack_policy,
    build_template_output_policy,
)

ANALYZER_SYSTEM_INSTRUCTION = """
You are a senior product designer, front-end architect, and QA analyst.
Produce an executor-ready build specification, not a loose description.
When the reference is a video, be exacting about motion and interaction
details so the executor can recreate the animation closely.
Operate with the discipline of an expert frontend developer focused on
responsive layout quality, accessibility, visual fidelity, and performance.
Be conservative about what counts as “good enough”; if the current implementation
is still materially different from the reference, call that out explicitly instead
of softening the requirement.
Prefer model-based judgment for planning and routing decisions, and only
lean on deterministic constraints when they are necessary for safety,
validation, policy enforcement, or schema integrity.
Return only structured JSON matching the requested schema.
""".strip()


OUTLINE_ANALYZER_SYSTEM_INSTRUCTION = """
You are the outline-planning layer for a screenshot-to-code system.
Identify the complete top-to-bottom page structure before any detailed blueprinting happens.
Use the structured DOM evidence as the primary source of truth for section boundaries,
chrome layers, wrappers, footer bands, and stateful variants. The output must be a
complete page outline, not a styling spec.
Return only structured JSON matching the requested schema.
""".strip()


def build_outline_analyzer_prompt(
    reference_bundle: ReferenceBundle,
    prior_outline: BlueprintOutlineSpec | None = None,
    prior_blueprint_validation: BlueprintValidationReport | None = None,
) -> str:
    selected_stack = build_selected_stack_policy(reference_bundle.stack)
    judgment_policy = build_judgment_policy()
    live_reference_block = ""
    if reference_bundle.live_reference is not None:
        live_reference_block = f"""

Live browser inspection context:
<live_reference>
{summarize_live_reference_for_prompt(reference_bundle.live_reference)}
</live_reference>"""

    design_system_block = ""
    if reference_bundle.design_system_preflight is not None:
        design_system_block = f"""

Required design-system preflight:
<design_system_preflight>
{summarize_design_system_preflight_for_prompt(reference_bundle.design_system_preflight)}
</design_system_preflight>"""

    prior_outline_block = ""
    if prior_outline is not None:
        prior_outline_block = f"""

Previous outline draft:
<prior_outline>
{truncate_json_context(prior_outline.model_dump_json(indent=2), max_chars=MAX_OUTLINE_JSON_CHARS)}
</prior_outline>"""

    prior_blueprint_validation_block = ""
    if prior_blueprint_validation is not None:
        prior_blueprint_validation_block = f"""

Latest blueprint QA report:
<prior_blueprint_validation>
{truncate_json_context(compact_blueprint_validation_report_for_prompt(prior_blueprint_validation).model_dump_json(indent=2))}
</prior_blueprint_validation>"""

    return f"""
{selected_stack}

{judgment_policy}
{design_system_block}
{live_reference_block}
{prior_outline_block}
{prior_blueprint_validation_block}

Create a canonical outline of the page before detailed blueprinting.

Outline requirements:
- Use `design_system.dom_evidence.section_candidates`, `chrome_candidates`, `footer_bands`, `form_candidates`, `repeated_groups`, `state_variants`, and `wrapper_relationships` as the primary planning inventory.
- Every first-party, page-defining section or chrome layer should map to one `page_outline` entry unless it is intentionally merged. Record merges in `coverage_notes`.
- Keep the outline in strict top-to-bottom order.
- Include stateful chrome such as modals, announcement bars, sticky headers, shop-now bars, or newsletter gates when they materially affect the template.
- Use `wrapper_outline` to record shared cards, split containers, nested shells, surface groups, and other parent wrappers that span multiple sections.
- If a wrapper or shell is visible in screenshots or DOM evidence, do not leave it implicit.
- `source_evidence_ids` should point back to the DOM evidence items that justify the outline entry.
- `closing_sections` must include the final 3-5 page regions near the bottom.
- Set `footer_present` explicitly and use `footer_description` to describe the real closing footer/newsletter/legal structure.
- Exclude third-party widgets like chat launchers, cookie managers, and accessibility overlays unless they are clearly first-party branded chrome.
- Prefer stable, reusable names and IDs over copy-specific labels when a component pattern is obvious.
- If the prior blueprint QA report identified missing sections, wrappers, or footer structure, repair those omissions in this outline.

Reference summary:
{reference_summary(reference_bundle)}
""".strip()


def build_analyzer_prompt(
    reference_bundle: ReferenceBundle,
    current_html: str | None = None,
    prior_requirements: RequirementsSpec | None = None,
    prior_validation: ValidationReport | None = None,
    prior_blueprint_validation: BlueprintValidationReport | None = None,
    approved_outline: BlueprintOutlineSpec | None = None,
) -> str:
    selected_stack = build_selected_stack_policy(reference_bundle.stack)
    template_policy = build_template_output_policy()
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    current_html_block = ""
    current_html_landmarks_block = ""
    if current_html and current_html.strip():
        current_html_block = f"""

Current implementation snapshot:
<current_html>
{truncate_html_context(current_html)}
</current_html>"""
        current_html_landmarks_block = f"""

Current implementation landmarks:
<current_html_landmarks>
{summarize_html_landmarks(current_html)}
</current_html_landmarks>"""
    prior_requirements_block = ""
    if prior_requirements is not None:
        prior_requirements_json = compact_requirements_for_prompt(
            prior_requirements
        ).model_dump_json(indent=2)
        prior_requirements_block = f"""

Saved supervisor context from the previous block:
<prior_requirements>
{truncate_json_context(prior_requirements_json)}
</prior_requirements>"""
    prior_validation_block = ""
    if prior_validation is not None:
        prior_validation_json = compact_validation_report_for_prompt(
            prior_validation
        ).model_dump_json(indent=2)
        prior_validation_block = f"""

Latest validator report from the previous block:
<prior_validation>
{truncate_json_context(prior_validation_json)}
</prior_validation>"""
    prior_blueprint_validation_block = ""
    if prior_blueprint_validation is not None:
        prior_blueprint_validation_json = compact_blueprint_validation_report_for_prompt(
            prior_blueprint_validation
        ).model_dump_json(indent=2)
        prior_blueprint_validation_block = f"""

Latest blueprint QA report:
<prior_blueprint_validation>
{truncate_json_context(prior_blueprint_validation_json)}
</prior_blueprint_validation>"""
    approved_outline_block = ""
    if approved_outline is not None:
        approved_outline_block = f"""

Approved canonical page outline:
<approved_outline>
{truncate_json_context(approved_outline.model_dump_json(indent=2), max_chars=MAX_OUTLINE_JSON_CHARS)}
</approved_outline>"""
    live_reference_block = ""
    if reference_bundle.live_reference is not None:
        live_reference_block = f"""

Live browser inspection context:
<live_reference>
{summarize_live_reference_for_prompt(reference_bundle.live_reference)}
</live_reference>"""
        if approved_outline is None and reference_bundle.live_reference.full_dom_html.strip():
            live_reference_block += f"""

Full post-load live DOM snapshot:
<live_reference_full_dom>
{full_live_dom_for_prompt(reference_bundle.live_reference.full_dom_html)}
</live_reference_full_dom>"""
    design_system_block = ""
    if reference_bundle.design_system_preflight is not None:
        design_system_block = f"""

Required design-system preflight:
<design_system_preflight>
{summarize_design_system_preflight_for_prompt(reference_bundle.design_system_preflight)}
</design_system_preflight>"""

    return f"""
{selected_stack}

You are the analysis layer for a screenshot-to-code system.
Study the provided reference media and draft a structured requirements spec that will
be used by a separate execution model and a separate validation model.

{template_policy}
{judgment_policy}
{frontend_policy}
{design_system_block}
{live_reference_block}
{current_html_block}
{current_html_landmarks_block}
{prior_requirements_block}
{prior_validation_block}
{prior_blueprint_validation_block}
{approved_outline_block}

Analysis requirements:

- Use the reference media as the source of truth.
- Capture visual layout, styling, imagery, copy, and behavior requirements.
- For video input, extract the key interaction checkpoints and the expected UI state after each checkpoint.
- For interaction checkpoints, set `action_type` when the action is obvious from the reference. Use `dismiss_overlay` for welcome modals, scratch-card promos, cookie walls, newsletter gates, and other blocking overlays that must be closed to reveal the page. Use `scroll` for scroll-driven state changes. Use `wait` when the checkpoint is purely timed.
- Populate `target_description` for interaction checkpoints with a short plain-language description of what the harness should act on, such as "modal close control", "background overlay", or "main page scroll".
- For video input, populate `animation_requirements` with concrete motion expectations including trigger, sequence, direction, timing, easing, sticky behavior, and visible end state.
- For video input, cover the full meaningful sequence of the reference, not just the opening animation. If later sections, state transitions, or scroll-driven scenes matter, include them in `interaction_checkpoints`, `behavior_requirements`, and `acceptance_criteria`.
- Do not invent backend requirements; mock data if the UI implies backend-driven content.
- Be concrete about what must be preserved and what must remain easy to customize later.
- Put special emphasis on how the output should remain easy to re-theme and easy to edit.
- Populate `hard_constraints` with non-negotiable fidelity requirements that the executor must satisfy first.
- Populate `preserve_requirements` only with things that are already very close to the reference. If something is merely acceptable or loosely similar, do not preserve it; call it out as work remaining instead.
- Populate `page_outline` with the full top-to-bottom page scan in reading order before you finalize the executor blueprint. This should be the analyzer's explicit ledger of every major visible section or page region from header through the final closing state.
- If an `<approved_outline>` block is provided, treat it as binding page-structure contract. Do not drop, rename, or silently merge outline entries or wrapper relationships unless you explicitly call that out in `coverage_notes`.
- Populate `closing_sections` with the final 3-5 major sections or page regions visible near the bottom of the page so the closing state cannot be forgotten after the hero/product areas are planned.
- Set `footer_present` explicitly to `true` or `false`; do not leave it implied. If the page has any footer, newsletter signup, social links, legal links, or final contact area, capture that in `footer_description` even if the exact section naming is ambiguous.
- Populate `coverage_notes` with any ambiguity, merges, or lower-page risks that could cause a section to be omitted. If you are unsure whether two lower-page blocks should be split, say so here instead of silently collapsing them.
- Populate `critical_layout_invariants` with the page-defining shell rules that span across sections, especially shared wrappers, surface/background transitions, split layouts, pinned shells, nested cards, and any "these two sections must remain inside the same container" relationships.
- Populate `section_requirements` exhaustively, top-to-bottom, so the executor can build the entire page in a stable order. Every major visible section from the opening viewport through the final page/footer state should appear exactly once here.
- When two or more sections share one visible shell, card, wrapper, split container, or surface group, populate `wrapper_requirements` with an explicit canonical wrapper entry instead of leaving that relationship only in prose.
- Never leave `section_requirements` empty when reference media, a live reference, or a reference URL is provided. If the exact marketing names are unclear, still emit provisional but explicit section names in top-to-bottom order.
- Keep section names stable and distinct, because each `section_requirements` entry becomes a canonical section ID used for executor DOM markers and validator coverage checks.
- When an approved outline exists, every `page_outline` entry should correspond to exactly one `section_requirements` entry or to a documented wrapper/state decision. The detailed blueprint should refine the approved outline, not replace it.
- Every `wrapper_requirements` entry should use a stable `wrapper_id`, name the participating `section_id`s in `participant_section_ids`, and describe the shared shell/container rules the executor must preserve.
- For every `section_requirements` entry, populate `layout_invariants` with the non-negotiable shell/container rules for that section. These are the structure-critical facts that would make the executor build the wrong layout if omitted, such as "shares the same white rounded card as the article body", "must stay inside a split right panel", "uses a soft-pink outer canvas with a centered max-width wrapper", or "must not become a separate full-width section".
- For every `section_requirements` entry, make `layout`, `must_include`, and `styling` concrete enough that another model could rebuild the section structure even if imagery were replaced with placeholders. If a section is recognizable because of a wrapper, surface color, border radius, grouped copy cluster, split panel, overlay treatment, menu shell, or CTA placement, spell that out explicitly.
- When the live reference exposes concrete image, SVG, icon, or CSS background asset URLs, promote them into `asset_requirements` and the relevant `section_requirements[].assets`. Treat those live asset references as implementation requirements for the corresponding sections rather than leaving imagery generic.
- Be especially strict about chrome and framing sections such as promo bars, announcement bars, headers, navigation menus, sticky states, modals, related-content rails, newsletters, and footers. Do not describe them as generic bars or navs; capture their composition, grouping, and distinctive shell treatment.
- `page_outline`, `closing_sections`, and `section_requirements` must agree with each other. If `page_outline` includes a footer, newsletter, social proof block, comparison, FAQ, closing CTA, or legal region, then `section_requirements` must represent that region explicitly instead of stopping early.
- If `execution_plan`, `acceptance_criteria`, or later video checkpoints mention a section or scene, that section must also exist in `section_requirements`; do not let later-page sections live only in freeform planning text.
- If the reference clearly shows additional lower-page sections, comparison tables, testimonials, FAQs, footers, or other major scenes, include them explicitly instead of collapsing them into a generic earlier section.
- Treat thin but visually distinct bands, icon rows, badge strips, newsletter strips, social-proof rails, or separator sections as standalone page sections when they have their own background, spacing, icon set, copy group, or interaction pattern. Do not absorb them into the larger product, testimonial, CTA, or footer section next to them.
- If a narrow section sits between two larger blocks and carries its own icons, badges, headlines, repeated items, or CTA treatment, it must appear as its own `section_requirements` entry instead of being merged away.
- If the reference uses a shared shell across neighboring sections, record that relationship explicitly in `critical_layout_invariants` and the relevant section `layout_invariants`; do not assume the executor will infer it from color tokens alone.
- If a shared shell or wrapper spans multiple sections, do not rely only on repeated wording such as "same shell" in those sections. Add a matching `wrapper_requirements` entry so execution and validation can enforce one shared DOM container.
- Do not hide structure-defining facts only inside `design_tokens`, `layout_requirements`, or prose summary text. If a wrapper, background surface, border radius, or split container is visually decisive, it must also appear in `critical_layout_invariants` or `section_requirements[].layout_invariants`.
- If decorative framing, ambient overlays, logo clusters, mega-menu shells, split hero chrome, or other non-image visual structure changes how the page reads, encode those facts in the affected section's `layout`, `must_include`, and `styling` instead of leaving them implicit.
- If the DOM or reference reveals decorative overlay wrappers, SVG glow layers, blurred color ellipses, ambient background shapes, or other non-content framing elements inside a section shell, capture them in that section's `styling`, `assets`, and `layout_invariants`. These elements are part of the template-defining structure even when they are not standalone sections.
- When the live reference exposes component geometry such as horizontal-vs-vertical card orientation, left/right media-to-text splits, full-height media panels, full-bleed image coverage, repeated row/card patterns, or gradient shells, promote those facts into the affected section `layout`, `layout_invariants`, `must_include`, and `styling` instead of leaving them for screenshot-only inference.
- When a section contains a repeated-item pattern inside a larger shell, capture both levels explicitly: the outer section composition and the representative repeated-item geometry. Do not flatten a split section into a vague card list or flatten a repeated card/list pattern into a generic right-column content block.
- Before finalizing the JSON, mentally rescan the reference from top to bottom and confirm the final visible page state is represented. Do not stop planning at the last product, testimonial, comparison, or FAQ block if the reference still shows more content below it.
- If the reference contains a footer or a closing newsletter/community/legal region, that ending state must appear somewhere in `page_outline`, `closing_sections`, `footer_description`, and `section_requirements`.
- Populate `design_tokens` with reusable color, typography, spacing, radius, shadow, and motion guidance.
- When typography materially defines the layout or brand impression, record exact measured typography instead of generic labels. Capture the font family, size, line-height, weight, letter-spacing, max-width, and surrounding spacing for section-defining text such as hero H1s, header/navigation text, button labels, promo bars, and footer/newsletter headings.
- Do not stop at generic token names such as `text-h1`, `text-body`, `gap-lg`, or `section-py` when the reference clearly exposes role-specific typography or section sizing. Prefer role-scoped tokens such as header nav copy, promo bar copy, hero title width, card gap, sticky CTA height, footer legal copy, newsletter heading, or shell/container sizing.
- If the reference uses non-system fonts, make the need to load the real font assets explicit in `hard_constraints`, `design_tokens.typography`, `asset_requirements`, or section `styling`. Naming a font family without an actual font-loading requirement is not sufficient because fallback fonts materially change perceived size and spacing.
- If section-defining typography controls the perceived section sizing or visual rhythm, mirror that in `layout_requirements`, `styling_requirements`, and the affected section `styling` so the executor does not guess.
- If the reference exposes multiple chrome layers or state variants such as promo bars, announcement bands, sticky/scrolled headers, dropdown shells, mega-menus, modal overlays, newsletters, legal bands, or closing accessibility regions, represent them as distinct sections or explicit blueprint states instead of collapsing them into a single generic header or footer.
- If the live page shows both an opening header shell and a compact sticky/scrolled header state, do not let one stand in for the other. Represent both explicitly or document their intentional merge in `coverage_notes`.
- Treat live-reference fields such as `section_inventory`, `chrome_layers`, `dom_landmarks`, `heading_hierarchy`, and `shell_relationships` as a DOM evidence checklist. Each distinct live region, chrome layer, or closing band should map to a canonical section or an explicit blueprint state/invariant. If you intentionally merge something, record that decision in `coverage_notes` instead of collapsing it silently.
- Treat `design_system.dom_evidence.section_candidates`, `chrome_candidates`, `footer_bands`, `form_candidates`, `repeated_groups`, `state_variants`, and `wrapper_relationships` as the primary structured DOM planning inventory. Each evidence item includes selectors, excerpts, assets, and shell notes that should map directly into the blueprint. Use those indexed evidence items as the coverage checklist before falling back to broader live-reference summaries.
- Do not ignore a structured DOM evidence item just because a screenshot is noisy or a modal is present. If a section candidate, footer band, repeated group, or chrome candidate is visible in `dom_evidence`, represent it explicitly in the blueprint or explain the intentional merge in `coverage_notes`.
- Use `wrapper_relationships` and section-level evidence excerpts to reason about shared shells, nested cards, split layouts, footer sub-bands, and article/product wrappers before scanning the raw DOM. The executor should not need to infer those relationships from generic section names alone.
- Do not ignore a section just because a promotional modal, sticky layer, or other overlay visually blocks it in the screenshot. If the indexed live-reference evidence exposes that region, account for it explicitly in the blueprint or explain the intentional merge in `coverage_notes`.
- Do not elevate third-party utility chrome into template sections unless the user explicitly asked for it or it is clearly first-party branded page chrome. Exclude support chat launchers, cookie consent managers, accessibility widgets, devtool badges, and similar fixed utilities from `page_outline` and `section_requirements`; at most note them in `coverage_notes` if they materially obscure the capture.
- Treat live-reference `asset_inventory` entries as an asset evidence checklist. If the browser inspection exposes exact site image URLs, SVG references, or background-image assets for visible sections, the blueprint should preserve those concrete assets in `asset_requirements` and section-level `assets` instead of downgrading them to placeholder imagery.
- Treat design-system preflight fields such as `section_typography`, `section_sizing`, `layout`, `components`, `motion_components`, and `source_notes` as an evidence checklist. If those fields expose more distinct section roles, shell relationships, or stateful chrome than your blueprint names, the blueprint is too thin and must be expanded before finalizing.
- For rich references, make `hard_constraints`, `critical_layout_invariants`, and section-level fields dense enough that another model would rebuild the same shell and hierarchy, not merely the same broad section order.
- Populate `execution_plan` with an ordered build checklist the executor can follow directly. If current HTML is provided, make it a delta-aware plan that calls out what to preserve and what to change next.
- When visible text is legible, include exact text in the appropriate fields instead of paraphrasing.
- When something is ambiguous, put that ambiguity in `known_unknowns` rather than guessing.
- When live browser inspection context is provided, treat the extracted design-system data as high-confidence evidence for fonts, colors, spacing, radii, shadows, layout containers, and component styling. Use uploaded screenshots/videos and browser renders together when resolving conflicts.
- When a required design-system preflight is provided, treat it as mandatory styling and component guidance, not optional inspiration.
- When live browser inspection or design-system context reveals exact container widths, wrapper radii, shell backgrounds, split-panel composition, or card nesting, promote those facts into `critical_layout_invariants` and the relevant section `layout_invariants` instead of leaving them as soft styling suggestions.
- When live browser inspection or design-system context reveals recognizably structured chrome such as logo-plus-copy bars, menu panel composition, nested cards, overlay framing, or ambient decorative shells, promote those facts into the affected section's `layout`, `must_include`, and `styling` so the executor does not rebuild them as generic blocks.
- Keep acceptance criteria measurable and specific enough for visual QA.
- Do not summarize motion vaguely. For video, describe exactly what animates, when it starts, what causes it to start, how it moves, and what the final resting state should be.
- Do not treat a polished hero sequence as sufficient if the reference video clearly includes additional states or later sections that must also be recreated.
- If current HTML is provided, treat it as the working baseline and identify the highest-leverage gaps between that implementation and the reference instead of re-planning the whole page from scratch.
- If current HTML is provided, assume it is incomplete until proven otherwise. Be strict about identifying any visible or behavioral gap that would still make the user ask for another round.
- Use the current HTML landmarks to refer to concrete sections and elements when describing what should be preserved, changed, or rebuilt.
- If prior requirements are provided, treat them as the previous supervisor draft. Preserve the accurate parts, correct stale assumptions, and sharpen them using the actual current HTML plus the reference media.
- If a prior validator report is provided, use it as evidence of where the last block stalled. Do not repeat old advice blindly if the current HTML already resolved it.
- If a prior blueprint validation report is provided, treat it as a pre-execution rejection of the supervisor plan. Repair the missing or contradictory blueprint fields first so execution will not be blocked again.
- When repairing after blueprint QA feedback, preserve the accurate parts of the prior requirements and change only the sections, outline entries, closing states, footer coverage, or execution guidance that the blueprint report rejected.
- If blueprint QA said a scene or section is missing from the canonical section list, add it to `page_outline`, `closing_sections` when relevant, and `section_requirements` before spending attention on finer styling detail.
- Execution will not start until blueprint QA passes, so do not leave known omissions in the canonical section list.
- On resume, produce a delta-aware requirements spec that helps the executor continue from the current implementation instead of re-building the page from scratch.

Reference summary:
{reference_summary(reference_bundle)}
""".strip()
