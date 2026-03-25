from loop.contracts import ReferenceBundle, RequirementsSpec
from loop.frontend_developer_policy import build_frontend_developer_policy
from loop.prompts import reference_summary, summarize_html_landmarks
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


def build_validator_prompt(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    current_html: str,
    iteration: int,
) -> str:
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    requirements_json = requirements.model_dump_json(indent=2)
    dom_landmarks = summarize_html_landmarks(current_html)
    return f"""
You are the validation layer for a screenshot-to-code system.
Compare the reference media against the rendered candidate screenshots and the current HTML.

This is validation iteration {iteration}.

Requirements spec:
<requirements_spec>
{requirements_json}
</requirements_spec>

Current HTML:
<current_html>
{current_html}
</current_html>

Current HTML landmarks:
<current_html_landmarks>
{dom_landmarks}
</current_html_landmarks>

{judgment_policy}
{frontend_policy}

Validation goals:

- Judge visual fidelity against the reference.
- Judge behavior fidelity using the requirements spec.
- Score visual fidelity, behavior fidelity, animation fidelity, and editability separately.
- Judge whether `hard_constraints` and `section_requirements` are being satisfied.
- Judge whether the current code remains easy to modify for theme, styling, imagery, and copy.
- For each issue, use exactly one of these categories: `layout`, `styling`, `copy`, `imagery`, `behavior`, `animation`, or `structure`.
- Return PASS only when the candidate is very close and there are no critical issues left.
- If it is not ready, return specific patch instructions that the executor model can apply directly.
- Populate `strengths` with specific things the executor should preserve because they are already close enough.
- Make `patch_instructions` ordered, localized, and executor-ready. Each instruction should say what to change, where to change it, and what existing behavior or structure should remain intact.
- Every `patch_instruction` and every issue `fix_instructions` field must point to a concrete target in the current HTML: a selector, `id`, class name, `data-*` attribute, nearby text snippet, or exact element description that an executor can find without guessing.
- Prefer concrete targets drawn from `current_html_landmarks` whenever possible. If the HTML lacks a clean selector, anchor the fix to the nearest stable nearby text snippet from the current HTML.
- Avoid abstract guidance like “improve spacing” or “fix the layout”. Instead say exactly which element, which classes/styles/content need to change, and what they should become.
- Compare against the actual current HTML and avoid vague “rebuild” guidance unless a localized fix is truly impossible.
- Be conservative with scores. If there are still obvious visual mismatches, missing sections, wrong styling, wrong imagery, wrong copy, missing interactions, or noticeably incorrect motion, do not score the run in the high 0.90s.
- Treat 0.90+ as “nearly complete”, 0.95+ as “extremely close”, and 0.98+ as “ready to ship”. Use materially lower scores whenever meaningful work remains.
- If any issue would require a user to immediately notice and ask for another round, it should not receive a high-0.90s score.
- Prefer the settled render as the source of truth for final-state layout, visibility, and overlap checks. Use the earlier render only as supplemental evidence when reasoning about entrance timing or missing animated elements.
- For video input, be strict about animation fidelity. Missing or materially different motion, timing, easing, sequencing, sticky behavior, scroll choreography, hover transitions, or reveal order must keep the verdict at REVISE.
- For video input, use the provided timeline checkpoint renders to judge coverage across the full reference sequence. If the candidate only matches the opening portion of the video but misses later states, scenes, transitions, or scroll-driven moments, keep the verdict at REVISE.
- Do not treat a strong first impression as sufficient if the reference video contains additional content or states beyond what the candidate timeline renders successfully represent.
- For video input, do not return PASS unless the motion is extremely close to the reference and `animation_fidelity_score` is at least 0.98.
- For video input, use `behavior_fidelity_score` below 0.98 whenever interactions or state transitions do not closely match the reference.

Reference summary:
{reference_summary(reference_bundle)}
""".strip()
