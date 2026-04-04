from loop.contracts import BlueprintValidationReport, ReferenceBundle, RequirementsSpec
from loop.frontend_developer_policy import build_frontend_developer_policy
from loop.prompts import (
    compact_blueprint_validation_report_for_prompt,
    compact_requirements_for_prompt,
    reference_summary,
    summarize_design_system_preflight_for_prompt,
    summarize_live_reference_for_prompt,
    truncate_json_context,
)
from prompts.policies import build_judgment_policy

BLUEPRINT_VALIDATOR_SYSTEM_INSTRUCTION = """
You are a strict pre-execution blueprint QA reviewer for a screenshot-to-code system.
Judge whether the supervisor's structured requirements spec is complete,
internally consistent, and safe to hand to the build executor.
Prefer model-based judgment for coverage and planning quality, and only rely on
deterministic constraints when they are necessary for schema integrity or safety.
Do not give credit for a blueprint that only covers the opening viewport if the
reference clearly contains more page content or later video states.
Return only structured JSON matching the requested schema.
""".strip()


def build_blueprint_validator_prompt(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    prior_blueprint_validation: BlueprintValidationReport | None = None,
) -> str:
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    requirements_json = compact_requirements_for_prompt(requirements).model_dump_json(
        indent=2
    )
    prior_validation_block = ""
    if prior_blueprint_validation is not None:
        prior_validation_json = compact_blueprint_validation_report_for_prompt(
            prior_blueprint_validation
        ).model_dump_json(indent=2)
        prior_validation_block = f"""

Prior blueprint QA report:
<prior_blueprint_validation>
{truncate_json_context(prior_validation_json)}
</prior_blueprint_validation>"""
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
You are the blueprint validation layer for a screenshot-to-code system.
Review the supervisor's requirements spec before any HTML generation begins.
The question is not whether the spec is plausible. The question is whether it is
complete and consistent enough that the executor would build the right page.

Requirements spec:
<requirements_spec>
{truncate_json_context(requirements_json)}
</requirements_spec>
{prior_validation_block}

{judgment_policy}
{frontend_policy}
{design_system_block}
{live_reference_block}

Blueprint validation goals:

- Judge whether the blueprint covers the full page or the full meaningful video sequence, not just the opening viewport.
- Score coverage, consistency, and execution readiness separately.
- Treat `page_outline`, `closing_sections`, `footer_present`, `footer_description`, `coverage_notes`, `section_requirements`, `behavior_requirements`, `animation_requirements`, `interaction_checkpoints`, `execution_plan`, and `acceptance_criteria` as one connected plan that must agree internally.
- Verify that every major visible section or scene from the reference appears in `page_outline`.
- Verify that every major visible section or scene appears exactly once in `section_requirements` rather than living only in freeform prose.
- Reject blueprints that stop at the hero, product, or early feature area if the reference clearly shows additional lower-page sections, closing regions, or footer content.
- Reject blueprints that mention later sections, checkpoints, interactions, or scenes in `execution_plan`, `acceptance_criteria`, `behavior_requirements`, or `interaction_checkpoints` without representing those same scenes in `section_requirements`.
- Be strict about footer and closing-state coverage. If the reference shows a footer, newsletter, legal area, community section, closing CTA, or other ending region, the blueprint must capture that ending state explicitly.
- For video input, ensure the blueprint represents later states, transitions, and motion checkpoints instead of describing only the opening scene.
- When live-reference or design-system-preflight context exists, judge whether the blueprint meaningfully reflects that evidence in the planned design tokens, layout guidance, and component expectations.
- If something is ambiguous, prefer an `ambiguity` issue that tells the analyzer to record the uncertainty explicitly in `coverage_notes` or `known_unknowns` instead of silently collapsing it away.
- Use `missing_sections` only for major visible sections or scenes that are absent from the canonical section list.
- Use these issue categories only: `coverage`, `consistency`, `behavior`, `animation`, `design_system`, `ambiguity`.
- Make every `fix_instructions` and every `repair_instructions` item directly usable by the analyzer.

PASS criteria:

- the blueprint covers the full page or full meaningful video sequence
- the canonical section list is complete and stable
- the closing state is represented
- no major contradiction remains between blueprint fields
- the executor could use this blueprint without likely building the wrong structure

FAIL criteria:

- any major section or scene is missing
- lower-page coverage is missing or obviously collapsed away
- footer or final page state is omitted when visible
- fields disagree in a way that would misroute execution
- the blueprint is too vague to implement faithfully

Reference summary:
{reference_summary(reference_bundle)}
""".strip()
