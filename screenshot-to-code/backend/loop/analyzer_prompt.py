from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport
from loop.frontend_developer_policy import build_frontend_developer_policy
from loop.prompts import (
    compact_requirements_for_prompt,
    compact_validation_report_for_prompt,
    reference_summary,
    summarize_design_system_preflight_for_prompt,
    summarize_live_reference_for_prompt,
    summarize_html_landmarks,
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


def build_analyzer_prompt(
    reference_bundle: ReferenceBundle,
    current_html: str | None = None,
    prior_requirements: RequirementsSpec | None = None,
    prior_validation: ValidationReport | None = None,
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

Analysis requirements:

- Use the reference media as the source of truth.
- Capture visual layout, styling, imagery, copy, and behavior requirements.
- For video input, extract the key interaction checkpoints and the expected UI state after each checkpoint.
- For video input, populate `animation_requirements` with concrete motion expectations including trigger, sequence, direction, timing, easing, sticky behavior, and visible end state.
- For video input, cover the full meaningful sequence of the reference, not just the opening animation. If later sections, state transitions, or scroll-driven scenes matter, include them in `interaction_checkpoints`, `behavior_requirements`, and `acceptance_criteria`.
- Do not invent backend requirements; mock data if the UI implies backend-driven content.
- Be concrete about what must be preserved and what must remain easy to customize later.
- Put special emphasis on how the output should remain easy to re-theme and easy to edit.
- Populate `hard_constraints` with non-negotiable fidelity requirements that the executor must satisfy first.
- Populate `preserve_requirements` only with things that are already very close to the reference. If something is merely acceptable or loosely similar, do not preserve it; call it out as work remaining instead.
- Populate `page_outline` with the full top-to-bottom page scan in reading order before you finalize the executor blueprint. This should be the analyzer's explicit ledger of every major visible section or page region from header through the final closing state.
- Populate `closing_sections` with the final 3-5 major sections or page regions visible near the bottom of the page so the closing state cannot be forgotten after the hero/product areas are planned.
- Set `footer_present` explicitly to `true` or `false`; do not leave it implied. If the page has any footer, newsletter signup, social links, legal links, or final contact area, capture that in `footer_description` even if the exact section naming is ambiguous.
- Populate `coverage_notes` with any ambiguity, merges, or lower-page risks that could cause a section to be omitted. If you are unsure whether two lower-page blocks should be split, say so here instead of silently collapsing them.
- Populate `section_requirements` exhaustively, top-to-bottom, so the executor can build the entire page in a stable order. Every major visible section from the opening viewport through the final page/footer state should appear exactly once here.
- Never leave `section_requirements` empty when reference media, a live reference, or a reference URL is provided. If the exact marketing names are unclear, still emit provisional but explicit section names in top-to-bottom order.
- Keep section names stable and distinct, because each `section_requirements` entry becomes a canonical section ID used for executor DOM markers and validator coverage checks.
- `page_outline`, `closing_sections`, and `section_requirements` must agree with each other. If `page_outline` includes a footer, newsletter, social proof block, comparison, FAQ, closing CTA, or legal region, then `section_requirements` must represent that region explicitly instead of stopping early.
- If `execution_plan`, `acceptance_criteria`, or later video checkpoints mention a section or scene, that section must also exist in `section_requirements`; do not let later-page sections live only in freeform planning text.
- If the reference clearly shows additional lower-page sections, comparison tables, testimonials, FAQs, footers, or other major scenes, include them explicitly instead of collapsing them into a generic earlier section.
- Treat thin but visually distinct bands, icon rows, badge strips, newsletter strips, social-proof rails, or separator sections as standalone page sections when they have their own background, spacing, icon set, copy group, or interaction pattern. Do not absorb them into the larger product, testimonial, CTA, or footer section next to them.
- If a narrow section sits between two larger blocks and carries its own icons, badges, headlines, repeated items, or CTA treatment, it must appear as its own `section_requirements` entry instead of being merged away.
- Before finalizing the JSON, mentally rescan the reference from top to bottom and confirm the final visible page state is represented. Do not stop planning at the last product, testimonial, comparison, or FAQ block if the reference still shows more content below it.
- If the reference contains a footer or a closing newsletter/community/legal region, that ending state must appear somewhere in `page_outline`, `closing_sections`, `footer_description`, and `section_requirements`.
- Populate `design_tokens` with reusable color, typography, spacing, radius, shadow, and motion guidance.
- Populate `execution_plan` with an ordered build checklist the executor can follow directly. If current HTML is provided, make it a delta-aware plan that calls out what to preserve and what to change next.
- When visible text is legible, include exact text in the appropriate fields instead of paraphrasing.
- When something is ambiguous, put that ambiguity in `known_unknowns` rather than guessing.
- When live browser inspection context is provided, treat the extracted design-system data as high-confidence evidence for fonts, colors, spacing, radii, shadows, layout containers, and component styling. Use uploaded screenshots/videos and browser renders together when resolving conflicts.
- When a required design-system preflight is provided, treat it as mandatory styling and component guidance, not optional inspiration.
- Keep acceptance criteria measurable and specific enough for visual QA.
- Do not summarize motion vaguely. For video, describe exactly what animates, when it starts, what causes it to start, how it moves, and what the final resting state should be.
- Do not treat a polished hero sequence as sufficient if the reference video clearly includes additional states or later sections that must also be recreated.
- If current HTML is provided, treat it as the working baseline and identify the highest-leverage gaps between that implementation and the reference instead of re-planning the whole page from scratch.
- If current HTML is provided, assume it is incomplete until proven otherwise. Be strict about identifying any visible or behavioral gap that would still make the user ask for another round.
- Use the current HTML landmarks to refer to concrete sections and elements when describing what should be preserved, changed, or rebuilt.
- If prior requirements are provided, treat them as the previous supervisor draft. Preserve the accurate parts, correct stale assumptions, and sharpen them using the actual current HTML plus the reference media.
- If a prior validator report is provided, use it as evidence of where the last block stalled. Do not repeat old advice blindly if the current HTML already resolved it.
- On resume, produce a delta-aware requirements spec that helps the executor continue from the current implementation instead of re-building the page from scratch.

Reference summary:
{reference_summary(reference_bundle)}
""".strip()
