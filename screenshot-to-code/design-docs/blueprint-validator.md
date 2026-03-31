# Blueprint Validator Spec

## Decision

Add a dedicated blueprint validation gate to the validated screenshot-to-code loop.

- Treat the analyzer's `RequirementsSpec` as the build blueprint.
- Validate that blueprint against the reference media before the executor runs.
- If the blueprint is incomplete or internally inconsistent, repair it by sending the validator feedback back through the analyzer.
- If the blueprint still does not pass after a small repair budget, stop the run before build phase.
- Reuse existing WebSocket `status`, `thinking`, and `assistant` messages instead of adding a new frontend protocol.

This keeps the current validated loop architecture, but inserts a new pre-execution QA checkpoint so bad blueprints cannot reach `LoopExecutor.execute()`.

## Current Problem

Today the validated loop has only one hard pre-execution blueprint check.

- `backend/loop/analyzer.py` produces `RequirementsSpec`.
- `backend/loop/orchestrator.py::_ensure_actionable_requirements()` currently rejects only the extreme failure case where a video/live-reference run returns no `section_requirements` at all.
- The executor then builds HTML from that blueprint.
- The existing `backend/loop/validator.py` can only catch blueprint mistakes after build work has already started.

That leaves a large failure gap:

- a blueprint can have the wrong section breakdown
- lower-page sections can be omitted
- footer or closing states can be missing
- `page_outline`, `closing_sections`, `section_requirements`, and `execution_plan` can disagree
- later video scenes can appear in prose but not in the canonical section list

These are exactly the kinds of failures that waste iterations and allow the system to build against the wrong plan.

## Goals

- Block executor start when the blueprint is not execution-ready.
- Catch missing sections, missing closing states, missing footer coverage, and internal blueprint contradictions before HTML generation.
- Repair recoverable blueprint issues automatically without requiring a full run restart.
- Preserve the current validated loop executor and HTML validator stages.
- Keep the implementation minimal and local to the validated loop path.

## Non-Goals

- Replacing the existing post-render HTML validator.
- Adding fallback blueprint synthesis in the orchestrator.
- Silently executing with a partially valid blueprint.
- Changing the model roster or introducing a different orchestration mode.

## Blueprint Definition

For this feature, the blueprint is the analyzer's `RequirementsSpec`, with special emphasis on:

- `page_outline`
- `closing_sections`
- `footer_present`
- `footer_description`
- `coverage_notes`
- `section_requirements`
- `behavior_requirements`
- `animation_requirements`
- `interaction_checkpoints`
- `execution_plan`
- `acceptance_criteria`

The validator should judge whether these fields together are specific and consistent enough that the executor can build the right page.

## Proposed Flow

```text
reference media
  -> analyzer drafts RequirementsSpec
  -> deterministic blueprint sanity checks
  -> model-based blueprint validator
  -> if needed, analyzer repair pass using blueprint feedback
  -> repeat blueprint QA up to repair budget
  -> only then enter executor/build iterations
  -> existing render + HTML validation loop continues unchanged
```

Detailed flow:

1. Keep live-reference enrichment and design-system preflight exactly where they are today.
2. Run `LoopAnalyzer.analyze()` to produce an initial `RequirementsSpec`.
3. Run a deterministic sanity pass for obvious structural failures.
4. Run a new model-based blueprint validator against the reference media plus `RequirementsSpec`.
5. If the blueprint validator returns `pass`, continue into the current executor loop.
6. If it returns `revise` or `blocked`, rerun the analyzer with the prior blueprint and the blueprint validation report as repair input.
7. Re-run blueprint validation after each repair attempt.
8. If the blueprint still fails after the configured repair budget, raise a run-stopping error before build phase.
9. On resume, apply the same blueprint validation gate after the analyzer refines saved requirements and before executor iterations continue.

## Scope Rules

Run blueprint validation when the request has actual reference evidence:

- image input
- video input
- live reference present
- `reference_url` present

Skip it for text-only runs that have no screenshots, no video, and no live reference, because those runs do not have a visual blueprint to verify against.

## Contract Changes

Add new contracts in `backend/loop/contracts.py`.

### `BlueprintValidationIssue`

- `severity`: `critical | major | minor`
- `category`: `coverage | consistency | behavior | animation | design_system | ambiguity`
- `title`: short issue label
- `detail`: what is wrong and why it would mislead execution
- `affected_fields`: list of `RequirementsSpec` field names involved
- `fix_instructions`: direct repair instruction for the analyzer

### `BlueprintValidationReport`

- `verdict`: `pass | revise | blocked`
- `overall_score`: `0.0-1.0`
- `coverage_score`: `0.0-1.0`
- `consistency_score`: `0.0-1.0`
- `execution_readiness_score`: `0.0-1.0`
- `summary`
- `strengths`: specific parts of the blueprint that should be preserved
- `issues`: list of `BlueprintValidationIssue`
- `missing_sections`: list of major sections/scenes missing from the canonical section list
- `repair_instructions`: ordered analyzer-ready repair checklist

Also extend these existing contracts:

- `LoopResumeState.blueprint_validation: BlueprintValidationReport | None = None`
- `LoopRunResult.blueprint_validation: BlueprintValidationReport | None = None`

The run result should expose the final accepted blueprint validation report, or the final rejected report if the run is blocked before execution.

## New Modules

Add:

- `backend/loop/blueprint_validator.py`
- `backend/loop/blueprint_validator_prompt.py`

`LoopBlueprintValidator` should mirror the existing analyzer/validator pattern:

- use Gemini structured output
- accept `ReferenceBundle` and `RequirementsSpec`
- include reference images, videos, live renders, and design-system preflight context the same way the current loop stages do
- return `BlueprintValidationReport`

## Deterministic Sanity Checks

Add a lightweight non-LLM sanity layer in the orchestrator before model-based blueprint validation.

These checks should fail fast on cases that do not require judgment:

- `section_requirements` must contain at least one named section when visual reference evidence exists
- every `section_requirements` entry must have a non-empty `name`
- normalized `section_id` values must be unique
- `page_outline` must not be empty when visual reference evidence exists
- `footer_present` must be explicitly set to `true` or `false` when visual reference evidence exists
- when `footer_present` is `true`, at least one of `footer_description`, `closing_sections`, or `section_requirements` must explicitly represent the footer/closing region

These checks should produce a synthetic `BlueprintValidationReport` shape when possible so the repair loop can reuse one feedback format.

## Blueprint Validator Prompt Rules

The new prompt should tell the model to judge whether the blueprint is execution-ready, not merely non-empty.

It must explicitly check for:

- every major visible section or scene in the reference appears in `page_outline`
- every major visible section or scene appears exactly once in `section_requirements`
- lower-page and closing regions are represented, not just hero/product areas
- `closing_sections` agrees with the actual tail of the page
- footer/newsletter/legal/community regions are captured when visible
- `execution_plan`, `acceptance_criteria`, `behavior_requirements`, and `interaction_checkpoints` do not reference scenes missing from `section_requirements`
- video-only states and motion checkpoints are represented in the blueprint, not just the opening state
- design-system preflight evidence is reflected in the blueprint when live reference or preflight data exists
- ambiguity is recorded explicitly in `coverage_notes` or `known_unknowns` instead of being silently collapsed away

PASS criteria:

- the blueprint covers the full page or full meaningful video sequence
- the canonical section list is complete and stable
- the closing state is represented
- no issue remains that would likely cause the executor to build the wrong page structure

FAIL criteria:

- any major section or scene is missing
- footer or final page state is omitted
- fields disagree in a way that would misroute execution
- the blueprint is too vague to implement faithfully

## Analyzer Repair Loop

Extend `LoopAnalyzer.analyze()` and `build_analyzer_prompt()` to accept prior blueprint validation feedback.

Suggested signature change:

```python
async def analyze(
    self,
    reference_bundle: ReferenceBundle,
    current_html: str | None = None,
    prior_requirements: RequirementsSpec | None = None,
    prior_validation: ValidationReport | None = None,
    prior_blueprint_validation: BlueprintValidationReport | None = None,
) -> RequirementsSpec:
```

Prompt additions:

- include a `<prior_blueprint_validation>` block when present
- tell the analyzer to preserve accurate requirements and repair only the rejected blueprint areas
- tell the analyzer that execution will be blocked until blueprint QA passes
- instruct the analyzer to fix omissions in the canonical section list first, before refining styling detail

## Orchestrator Changes

Modify `backend/loop/orchestrator.py`.

### Constructor

Add:

- `blueprint_validator: LoopBlueprintValidator | None = None`
- `max_blueprint_validation_attempts: int = DEFAULT_BLUEPRINT_VALIDATION_MAX_ATTEMPTS`

Keep the existing analyzer, executor, validator, renderer, and artifact-store wiring unchanged.

### Execution order

After analyzer output is produced, replace the current single `_ensure_actionable_requirements()` gate with a broader pre-execution flow:

1. `requirements = await self._analyzer.analyze(...)`
2. `requirements = await self._ensure_blueprint_sanity(requirements, reference_bundle=reference_bundle)`
3. `requirements, blueprint_validation = await self._repair_until_blueprint_passes(...)`
4. emit supervisor summary for the accepted blueprint
5. enter the existing executor/render/HTML-validator iteration loop

### Failure behavior

- If blueprint QA exhausts its repair budget, raise `RuntimeError` before iteration 1 starts.
- The error message should name the top blueprint failures so the run log is self-explanatory.
- Do not fall through to executor with a rejected blueprint.

### Status messages

Use existing channels only.

Recommended status messages:

- `Blueprint QA: validating supervisor requirements before execution.`
- `Blueprint QA: repairing missing sections and blueprint inconsistencies.`
- `Blueprint QA blocked execution after 2 failed repair attempts.`

Recommended supervisor updates:

- thinking: `Supervisor: Reviewing blueprint coverage`
- assistant: `Supervisor: Blueprint repaired`

## Artifacts And Metadata

Extend `backend/loop/artifacts.py` so blueprint QA is inspectable.

Persist:

- latest blueprint validation report to `assets/validated-loop/current/blueprint-validation.json`
- latest blueprint validation report to `{run_dir}/blueprint-validation.json`
- latest blueprint validation report inside current and run `metadata.json` as `blueprintValidation`

This should be enough to debug why a run was blocked before build phase without introducing a new artifact hierarchy.

## Why A Separate Blueprint Validator

Do not solve this only with more analyzer prompt instructions.

- the analyzer is the author of the blueprint and should not be the only judge of its correctness
- deterministic checks alone cannot reliably detect omitted lower-page sections or later video scenes
- the existing HTML validator is too late in the pipeline because build work has already been spent

The new stage creates a distinct author-reviewer boundary before execution, which is the missing control point.

## Testing

Add or update tests in these areas.

### Prompt tests

Update `backend/tests/test_loop_prompts.py`:

- analyzer prompt includes `<prior_blueprint_validation>` when present
- blueprint validator prompt explicitly rejects missing lower-page coverage, missing footer coverage, and orphan scene references
- blueprint validator prompt defines strict PASS criteria for execution readiness

### Orchestrator tests

Update `backend/tests/test_validated_loop.py`:

- executor is not called when blueprint validation fails
- analyzer repair is attempted when blueprint validation returns `revise`
- run proceeds when repaired blueprint later passes
- run blocks after repair budget is exhausted
- resume flow re-validates the refined blueprint before execution continues
- text-only runs without media skip blueprint validation

### Contract tests

Add tests for:

- duplicate normalized `section_id` detection
- synthetic sanity-check failures producing blocking blueprint reports
- artifact persistence of `blueprintValidation`

## Implementation Notes

- Keep the current executor prompt and current HTML validator unchanged except for any minimal type wiring required by the new contracts.
- Keep blueprint repair attempts separate from `max_iterations`; blueprint QA should not consume build iterations.
- Use the same Gemini model family already used by the validated loop unless there is an explicit reason to change it.
- Do not add silent fallbacks. A rejected blueprint should repair or fail clearly.

## Expected Outcome

After this change, the validated loop should only begin building when the supervisor blueprint has passed an explicit pre-execution QA step. Bad blueprints stop early, recoverable blueprints get repaired automatically, and the existing HTML validation loop can focus on implementation fidelity instead of compensating for a broken plan.
