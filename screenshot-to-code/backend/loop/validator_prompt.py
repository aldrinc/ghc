import json

from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport
from loop.frontend_developer_policy import build_frontend_developer_policy
from loop.prompts import (
    build_live_design_system_rules,
    compact_validation_report_for_prompt,
    compact_validator_requirements_for_prompt,
    reference_summary,
    summarize_design_system_preflight_for_prompt,
    summarize_html_landmarks,
    summarize_live_reference_for_prompt,
    truncate_html_context,
)
from prompts.policies import build_judgment_policy

VALIDATOR_SYSTEM_INSTRUCTION = """
You are a strict visual and interaction QA validator.
Prefer model-based judgment for evaluation and prioritization decisions, and only
rely on deterministic constraints when they are necessary for safety,
validation, policy enforcement, or schema integrity.
Be especially harsh on motion fidelity for video references.
Evaluate with the standards of an expert frontend developer: catch layout
breakage, clipping, hidden states, accessibility regressions, and responsive
or rendering-quality issues that a user would immediately notice.
Be conservative with high scores: 0.96-0.98 should be reserved for outputs that are
extremely close to the reference with no material visual, behavioral, structural,
or motion mismatches remaining.
Return only structured JSON matching the requested schema.
""".strip()

_FUNCTIONALITY_FIRST_FOCUS_CUES = (
    "don't care about images",
    "dont care about images",
    "ignore images",
    "ignore imagery",
    "only care about features",
    "only care about the features",
    "only care about functionality",
    "only care about the functionality",
    "features and functionality",
    "feature functionality",
    "functionality-first",
    "feature-first",
    "focus on functionality",
)


def is_functionality_first_focus(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec | None = None,
) -> bool:
    texts = [reference_bundle.user_text]
    if requirements is not None:
        texts.extend(
            [
                requirements.summary,
                requirements.template_goal,
                *requirements.coverage_notes[:3],
            ]
        )
    haystack = " ".join(text.strip().lower() for text in texts if text.strip())
    return any(cue in haystack for cue in _FUNCTIONALITY_FIRST_FOCUS_CUES)


def build_validator_prompt(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    current_html: str,
    iteration: int,
    prior_validation: ValidationReport | None = None,
) -> str:
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    requirements_json = json.dumps(
        compact_validator_requirements_for_prompt(requirements), indent=2
    )
    truncated_html = truncate_html_context(current_html)
    dom_landmarks = summarize_html_landmarks(current_html)
    prior_validation_block = ""
    if prior_validation is not None:
        prior_validation_json = json.dumps(
            compact_validation_report_for_prompt(prior_validation).model_dump(
                mode="json"
            ),
            indent=2,
        )
        prior_validation_block = f"""

Prior validation delta checklist:
<prior_validation>
{prior_validation_json}
</prior_validation>"""
    live_reference_block = ""
    if reference_bundle.live_reference is not None:
        live_reference_block = f"""

Live browser inspection context:
<live_reference>
{summarize_live_reference_for_prompt(reference_bundle.live_reference)}
</live_reference>"""
    live_design_system_rules = build_live_design_system_rules(
        reference_bundle, requirements
    )
    functionality_first_focus = is_functionality_first_focus(
        reference_bundle, requirements
    )
    design_system_block = ""
    if reference_bundle.design_system_preflight is not None:
        design_system_block = f"""

Required design-system preflight:
<design_system_preflight>
{summarize_design_system_preflight_for_prompt(reference_bundle.design_system_preflight)}
</design_system_preflight>"""
    validation_focus_block = ""
    if functionality_first_focus:
        validation_focus_block = """

Feature/functionality-first validation mode:
- Prioritize section completeness, feature presence, interaction correctness, state transitions, and editability over pixel-perfect imagery.
- Treat missing or substituted images as `imagery` issues, not `behavior` or `structure` issues, unless they hide required content or break an interaction.
- Imagery mismatches should primarily affect `visual_fidelity_score`; they should not by themselves force low behavior/editability scores or block PASS when sections and interactions are otherwise correct.
- If all required sections are present and the interactive features work correctly, do not keep the verdict at REVISE solely because imagery differs from the reference.
"""
    return f"""
You are the validation layer for a screenshot-to-code system.
Compare the reference media against the rendered candidate screenshots and the current HTML.
The current HTML block may be truncated for context-window efficiency, so prefer current HTML landmarks when targeting fixes.
When prior validation is provided, use it as the main delta checklist for this round while still catching any obvious regressions or new blockers.

This is validation iteration {iteration}.

Requirements spec:
<requirements_spec>
{requirements_json}
</requirements_spec>
{prior_validation_block}

Current HTML:
<current_html>
{truncated_html}
</current_html>

Current HTML landmarks:
<current_html_landmarks>
{dom_landmarks}
</current_html_landmarks>

{judgment_policy}
{frontend_policy}
{design_system_block}
{live_reference_block}
{live_design_system_rules}
{validation_focus_block}

Validation goals:

- Judge visual fidelity against the reference.
- Judge behavior fidelity using the requirements spec.
- Score visual fidelity, behavior fidelity, animation fidelity, and editability separately.
- Judge whether `hard_constraints`, `critical_layout_invariants`, `section_requirements`, and each section's `layout_invariants` are being satisfied.
- Judge whether `wrapper_requirements` are satisfied. When a required shared wrapper, shell, or grouped surface is missing, count that as a real structure failure even if the child sections exist.
- Use each section's `layout`, `must_include`, and `styling` as part of the blueprint contract, not as optional prose. If those fields describe distinctive chrome composition, framing, grouped CTA/copy clusters, shells, or menu structures and the candidate simplifies them away, count that as a real fidelity miss.
- Return a `section_results` entry for every item in `section_requirements`, preserving the same top-to-bottom order. Use exactly one status per section: `present`, `partial`, or `missing`.
- Treat section coverage as a gating requirement: if any required section is `missing` or `partial`, keep the verdict at REVISE and make the first patch instructions restore coverage before polishing already-good sections.
- Use each `section_results.quality_score` to judge the quality of that specific section only after deciding whether the section is fully present.
- When the current HTML contains exact `data-section-id="<section_id>"` markers that match `section_requirements.section_id`, treat those markers as authoritative evidence that the section root exists in the implementation. Do not mark that section as `missing`.
- When the current HTML contains exact `data-wrapper-id="<wrapper_id>"` markers that match `wrapper_requirements.wrapper_id`, treat those markers as authoritative evidence that the shared wrapper root exists. If a required wrapper marker is absent, do not treat the related structure as fully implemented.
- If the candidate includes the right section roots but breaks the blueprint's shared wrappers, background shells, split panels, or other explicit `critical_layout_invariants` / `layout_invariants`, report that as a `structure` issue rather than silently treating the page as structurally correct.
- If the candidate preserves the section roots but simplifies section-defining chrome or framing called out in `layout`, `must_include`, or `styling` into a generic bar/card/block, report that as a `structure` or `layout` issue rather than giving credit for superficial section presence.
- If the reference clearly contains a major section or later-page scene that is not represented in `section_requirements`, report that as a `structure` issue and say the supervisor blueprint is incomplete rather than silently accepting the smaller checklist.
- Judge whether the current code remains easy to modify for theme, styling, imagery, and copy.
- When `prior_validation` is present, first verify whether the previously reported issues and patch instructions are now resolved, partially resolved, or still broken.
- For each issue, use exactly one of these categories: `layout`, `styling`, `copy`, `imagery`, `behavior`, `animation`, or `structure`.
- Return PASS only when the candidate is very close and there are no critical issues left.
- If it is not ready, return specific patch instructions that the executor model can apply directly.
- Populate `strengths` with specific things the executor should preserve because they are already close enough.
- Make `patch_instructions` ordered, localized, and executor-ready. Each instruction should say what to change, where to change it, and what existing behavior or structure should remain intact.
- Every `patch_instruction` and every issue `fix_instructions` field must point to a concrete target in the current HTML: a selector, `id`, class name, `data-*` attribute, nearby text snippet, or exact element description that an executor can find without guessing.
- The `current_html` block may be truncated. Prefer concrete targets drawn from `current_html_landmarks` whenever possible. If the HTML lacks a clean selector, anchor the fix to the nearest stable nearby text snippet from the current HTML.
- Avoid abstract guidance like “improve spacing” or “fix the layout”. Instead say exactly which element, which classes/styles/content need to change, and what they should become.
- Compare against the actual current HTML and avoid vague “rebuild” guidance unless a localized fix is truly impossible.
- When prescribing decorative glow, blur, orb, or overlay fixes, keep the effect visibly inside the section shell. Do not suggest negative z-index placement or hidden-behind-parent layering unless the settled render already proves that the effect remains visible. Prefer a visible absolute layer plus a higher-z content wrapper.
- Do not ignore new regressions just because they were not present in `prior_validation`.
- Be conservative with scores. If there are still obvious visual mismatches, missing sections, wrong styling, wrong imagery, wrong copy, missing interactions, or noticeably incorrect motion, do not score the run in the high 0.90s.
- Do not return PASS when any required section is `missing` or `partial`, even if the sections that do exist look strong.
- Treat 0.90+ as “nearly complete”, 0.95+ as “extremely close”, and 0.98+ as “ready to ship”. Use materially lower scores whenever meaningful work remains.
- If any issue would require a user to immediately notice and ask for another round, it should not receive a high-0.90s score.
- Prefer the settled render as the source of truth for final-state layout, visibility, and overlap checks. Use the earlier render only as supplemental evidence when reasoning about entrance timing or missing animated elements.
- When live browser inspection context is present, use the extracted design system and browser renders as high-confidence evidence for typography, colors, spacing, component styling, and page-level layout containers.
- When a required design-system preflight is present, treat it as mandatory review criteria for typography, colors, spacing, layout, visible components, and motion intent.
- When live browser inspection context is present, do not return PASS if the candidate substitutes different font-family names, omits centralized theme tokens, or fails to apply the extracted design system in code.
- When custom or non-system fonts are required by the live design system, do not return PASS if the candidate merely names those fonts but does not include a working font-loading mechanism such as `@font-face`, imported font CSS, or explicit font asset URLs.
- When live browser inspection exposes concrete image URLs, SVG references, or CSS background-image assets for visible sections, treat placeholder media or unrelated substitute imagery as a real imagery fidelity miss. Do not return PASS if those extracted site assets were required by the blueprint and the candidate omits them.
- Treat measured typography mismatches as real visual issues whenever typography drives fidelity. Wrong size, line-height, weight, letter-spacing, max-width, or surrounding spacing on section-defining text like hero H1s, header/nav text, buttons, promo bars, and footer/newsletter headings should keep the verdict at REVISE until they are very close.
- For video input, be strict about animation fidelity. Missing or materially different motion, timing, easing, sequencing, sticky behavior, scroll choreography, hover transitions, or reveal order must keep the verdict at REVISE.
- For video input, use the provided timeline checkpoint renders to judge coverage across the full reference sequence. If the candidate only matches the opening portion of the video but misses later states, scenes, transitions, or scroll-driven moments, keep the verdict at REVISE.
- Do not treat a strong first impression as sufficient if the reference video contains additional content or states beyond what the candidate timeline renders successfully represent.
- For video input, do not return PASS unless the motion is extremely close to the reference and `animation_fidelity_score` is at least 0.98.
- For video input, use `behavior_fidelity_score` below 0.98 whenever interactions or state transitions do not closely match the reference.

Reference summary:
{reference_summary(reference_bundle)}
""".strip()
