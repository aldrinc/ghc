import uuid
from hashlib import sha256
from typing import Any, Awaitable, Callable

from config import (
    DEFAULT_BLUEPRINT_VALIDATION_MAX_ATTEMPTS,
    VALIDATED_LOOP_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_ANIMATION_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_BEHAVIOR_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_PASS_SCORE,
)
from loop.artifacts import (
    ValidatedLoopArtifactStore,
    load_design_system_preflight_from_current_cache,
    load_design_system_preflight_from_run_dir,
    load_reference_bundle_from_current_cache,
)
from loop.analyzer import LoopAnalyzer
from loop.blueprint_validator import LoopBlueprintValidator
from loop.contracts import (
    BlueprintValidationIssue,
    BlueprintValidationReport,
    DesignSystemReuseMode,
    DesignSystemPreflight,
    LoopIterationRecord,
    LoopResumeState,
    LoopRunResult,
    ReferenceBundle,
    RequirementsSpec,
    ValidationReport,
    ViewportSpec,
)
from loop.design_system_preflight import (
    DesignSystemDocumentRenderer,
    DesignSystemPreflightBuilder,
)
from loop.execution_blocks import plan_execution_blocks, summarize_execution_blocks
from loop.executor import LoopExecutor
from loop.live_reference import LiveReferenceExtractor
from loop.renderer import HtmlPreviewRenderer
from loop.validator import LoopValidator


def _live_reference_viewport(reference_bundle: ReferenceBundle) -> ViewportSpec:
    if reference_bundle.input_mode == "video":
        return ViewportSpec(width=1440, height=1024, device="desktop")
    return ViewportSpec(width=1440, height=1024, device="desktop")


def _needs_design_system_preflight(reference_bundle: ReferenceBundle) -> bool:
    return bool(
        reference_bundle.input_mode == "video"
        or reference_bundle.live_reference is not None
        or reference_bundle.reference_url.strip()
    )


def _requires_explicit_section_blueprint(reference_bundle: ReferenceBundle) -> bool:
    return bool(
        reference_bundle.images
        or reference_bundle.videos
        or reference_bundle.input_mode == "video"
        or reference_bundle.live_reference is not None
        or reference_bundle.reference_url.strip()
    )


_FOOTER_KEYWORDS = (
    "footer",
    "legal",
    "newsletter",
    "community",
    "copyright",
)


def _mentions_footer_region(values: list[str]) -> bool:
    return any(
        keyword in value.strip().lower()
        for value in values
        for keyword in _FOOTER_KEYWORDS
        if value.strip()
    )


class ValidationLoopOrchestrator:
    def __init__(
        self,
        *,
        send_message: Callable[..., Awaitable[None]],
        openai_api_key: str | None,
        openai_base_url: str | None,
        anthropic_api_key: str | None,
        gemini_api_key: str,
        should_generate_images: bool,
        option_codes: list[str] | None,
        max_iterations: int,
        design_system_reuse_mode: DesignSystemReuseMode = "generate",
        design_system_reuse_run_dir: str | None = None,
        renderer: HtmlPreviewRenderer | None = None,
        analyzer: LoopAnalyzer | None = None,
        blueprint_validator: LoopBlueprintValidator | None = None,
        validator: LoopValidator | None = None,
        executor: LoopExecutor | None = None,
        artifact_store: ValidatedLoopArtifactStore | None = None,
        live_reference_extractor: LiveReferenceExtractor | None = None,
        design_system_builder: DesignSystemPreflightBuilder | None = None,
        design_system_renderer: DesignSystemDocumentRenderer | None = None,
        max_blueprint_validation_attempts: int = DEFAULT_BLUEPRINT_VALIDATION_MAX_ATTEMPTS,
    ) -> None:
        self._send_message = send_message
        self._max_iterations = max_iterations
        self._max_blueprint_validation_attempts = max(1, max_blueprint_validation_attempts)
        self._design_system_reuse_mode = design_system_reuse_mode
        self._design_system_reuse_run_dir = design_system_reuse_run_dir
        self._analyzer = analyzer or LoopAnalyzer(gemini_api_key)
        self._blueprint_validator = blueprint_validator or LoopBlueprintValidator(
            gemini_api_key
        )
        self._validator = validator or LoopValidator(gemini_api_key)
        self._renderer = renderer or HtmlPreviewRenderer()
        self._artifact_store = artifact_store or ValidatedLoopArtifactStore()
        self._live_reference_extractor = live_reference_extractor or LiveReferenceExtractor()
        self._design_system_builder = design_system_builder or DesignSystemPreflightBuilder(
            gemini_api_key
        )
        self._design_system_renderer = (
            design_system_renderer or DesignSystemDocumentRenderer()
        )
        self._executor = executor or LoopExecutor(
            send_message=send_message,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            should_generate_images=should_generate_images,
            option_codes=option_codes,
        )

    async def run(
        self,
        *,
        reference_bundle: ReferenceBundle,
        initial_file_state: dict[str, str] | None,
        resume_state: LoopResumeState | None = None,
    ) -> LoopRunResult:
        reference_bundle = await self._enrich_live_reference(reference_bundle)
        reference_bundle = await self._ensure_design_system_preflight(reference_bundle)
        await self._status(
            "Persisting validated loop code to "
            f"{self._artifact_store.paths.current_file_path}."
        )
        self._artifact_store.persist_reference_bundle(reference_bundle)
        await self._status(
            "Saved reference media locally for this run. Future continue/retry steps can reuse it without depending on browser memory.",
            data={
                "artifactPath": self._artifact_store.paths.best_file_path,
                "runDir": self._artifact_store.paths.run_dir,
            },
        )
        current_file_state = initial_file_state or (
            resume_state.best_file_state if resume_state else None
        )
        validation_report: ValidationReport | None = (
            resume_state.latest_validation if resume_state else None
        )
        prior_blueprint_validation: BlueprintValidationReport | None = (
            resume_state.blueprint_validation if resume_state else None
        )
        if resume_state and resume_state.requirements is not None:
            await self._send_supervisor_thinking(
                title="Supervisor: Resuming prior context",
                content=(
                    "Refining the saved supervisor context against the reference "
                    "media and the current best HTML so the next block can continue "
                    "from the exact saved baseline without losing precision."
                ),
            )
            await self._status(
                "Analysis: refining saved supervisor context from the previous run."
            )
            requirements = await self._analyzer.analyze(
                reference_bundle,
                current_file_state.get("content", "") if current_file_state else None,
                prior_requirements=resume_state.requirements,
                prior_validation=resume_state.latest_validation,
                prior_blueprint_validation=resume_state.blueprint_validation,
            )
        else:
            await self._send_supervisor_thinking(
                title="Supervisor: Analyzing reference",
                content=(
                    "Reviewing the source input to extract layout, styling, copy, "
                    "behavior, hard constraints, section blueprints, and template-"
                    "structure requirements before execution."
                ),
            )
            await self._status("Analysis: drafting requirements with Gemini 3.1 Pro.")
            requirements = await self._analyzer.analyze(
                reference_bundle,
                current_file_state.get("content", "") if current_file_state else None,
            )
        (
            requirements,
            blueprint_validation,
            blueprint_was_repaired,
        ) = await self._validate_blueprint_before_execution(
            requirements,
            reference_bundle=reference_bundle,
            current_html=current_file_state.get("content", "") if current_file_state else None,
            prior_validation=validation_report,
            prior_blueprint_validation=prior_blueprint_validation,
        )
        await self._send_supervisor_assistant(
            title=(
                "Supervisor: Blueprint repaired"
                if blueprint_was_repaired
                else "Supervisor: Requirements draft ready"
            ),
            content=self._summarize_requirements(requirements),
        )
        iterations: list[LoopIterationRecord] = []
        last_code = current_file_state.get("content", "") if current_file_state else ""
        best_code = last_code
        best_validation_report = validation_report

        self._artifact_store.persist_metadata(
            iteration=0,
            stop_reason=None,
            requirements=requirements,
            validation_report=validation_report,
            blueprint_validation=blueprint_validation,
        )

        if best_code and best_validation_report is not None:
            self._artifact_store.persist_best_checkpoint(
                html=best_code,
                iteration=0,
                requirements=requirements,
                validation_report=best_validation_report,
                blueprint_validation=blueprint_validation,
            )

        for iteration in range(1, self._max_iterations + 1):
            await self._send_supervisor_thinking(
                title=f"Supervisor: Execution plan for iteration {iteration}",
                content=(
                    f"Handing iteration {iteration} to the executor with the current "
                    "requirements, section blueprint, hard constraints, and any "
                    "validator feedback gathered so far."
                ),
            )
            await self._status(
                f"Iteration {iteration}/{self._max_iterations}: executing with Gemini 3.1 Pro."
            )
            execution_blocks = plan_execution_blocks(
                reference_bundle=reference_bundle,
                requirements=requirements,
                file_state=current_file_state,
                validation_report=validation_report,
            )
            if len(execution_blocks) > 1:
                await self._send_supervisor_thinking(
                    title=f"Supervisor: Execution blocks for iteration {iteration}",
                    content=(
                        "Splitting the implementation into smaller executor blocks so the coding agent keeps the full-page plan while staying within the model context budget."
                    ),
                )
                await self._status(
                    f"Iteration {iteration}/{self._max_iterations}: executing in {len(execution_blocks)} scoped blocks.",
                    data={
                        "executionBlocks": summarize_execution_blocks(execution_blocks),
                    },
                )
            last_code = await self._executor.execute(
                reference_bundle=reference_bundle,
                requirements=requirements,
                file_state=current_file_state,
                validation_report=validation_report,
                iteration=iteration,
                execution_blocks=execution_blocks,
            )

            if not last_code.strip():
                raise RuntimeError("Execution produced empty code")

            self._artifact_store.persist_iteration_code(
                html=last_code,
                iteration=iteration,
            )
            self._artifact_store.persist_metadata(
                iteration=iteration,
                stop_reason=None,
                requirements=requirements,
                validation_report=None,
                blueprint_validation=blueprint_validation,
            )
            await self._status(
                f"Iteration {iteration}/{self._max_iterations}: rendering candidate."
            )
            render_artifact = await self._renderer.render_html(
                last_code,
                requirements.viewport,
                requirements.interaction_checkpoints
                if reference_bundle.input_mode == "video"
                else None,
            )

            await self._status(
                f"Iteration {iteration}/{self._max_iterations}: validating with Gemini 3.1 Pro."
            )
            await self._send_supervisor_thinking(
                title=f"Supervisor: Reviewing iteration {iteration}",
                content=(
                    "Comparing the rendered candidate against the reference and "
                    "checking whether the implementation still looks easy to retheme "
                    "and edit."
                ),
            )
            prior_validation_for_iteration = validation_report
            validation_report = await self._validator.validate(
                reference_bundle=reference_bundle,
                requirements=requirements,
                render_artifact=render_artifact,
                current_html=last_code,
                iteration=iteration,
                prior_validation=prior_validation_for_iteration,
            )
            iterations.append(
                LoopIterationRecord(
                    iteration=iteration,
                    validation=validation_report,
                )
            )

            await self._status(
                "Validation result: "
                f"{validation_report.verdict} at score {validation_report.overall_score:.2f}. "
                f"{validation_report.summary}"
            )
            await self._send_supervisor_assistant(
                title=f"Supervisor: Validation summary for iteration {iteration}",
                content=self._summarize_validation(validation_report),
            )
            self._artifact_store.persist_metadata(
                iteration=iteration,
                stop_reason=None,
                requirements=requirements,
                validation_report=validation_report,
                blueprint_validation=blueprint_validation,
            )

            if self._is_better_validation(
                candidate=validation_report,
                incumbent=best_validation_report,
            ):
                best_code = last_code
                best_validation_report = validation_report
                self._artifact_store.persist_best_checkpoint(
                    html=best_code,
                    iteration=iteration,
                    requirements=requirements,
                    validation_report=best_validation_report,
                    blueprint_validation=blueprint_validation,
                )
            elif best_validation_report is not None:
                await self._send_supervisor_assistant(
                    title=f"Supervisor: Retaining best-so-far after iteration {iteration}",
                    content=(
                        "This iteration did not improve on the best saved checkpoint, "
                        "so future continues will keep using the stronger prior result."
                    ),
                )

            if self._should_stop_after_validation(
                reference_bundle=reference_bundle,
                validation_report=validation_report,
            ):
                final_code = best_code if best_code.strip() else last_code
                self._artifact_store.persist_metadata(
                    iteration=iteration,
                    stop_reason="pass",
                    requirements=requirements,
                    validation_report=validation_report,
                    blueprint_validation=blueprint_validation,
                )
                await self._send_supervisor_assistant(
                    title="Supervisor: Loop complete",
                    content=(
                        "The candidate is close enough to the reference to stop the loop."
                    ),
                )
                return LoopRunResult(
                    code=final_code,
                    requirements=requirements,
                    blueprint_validation=blueprint_validation,
                    iterations=iterations,
                    stop_reason="pass",
                    saved_code_path=self._artifact_store.paths.best_file_path,
                    saved_run_dir=self._artifact_store.paths.run_dir,
                    analyzer_model=self._analyzer.model,
                    executor_model=self._executor.model,
                    validator_model=self._validator.model,
                )

            if validation_report.verdict == "pass":
                await self._send_supervisor_assistant(
                    title="Supervisor: Continuing despite provisional pass",
                    content=(
                        "The validator reported a provisional pass, but the run is "
                        "continuing because the stricter score gates for this input "
                        "mode have not been satisfied yet."
                    ),
                )

            if validation_report.verdict == "blocked":
                self._artifact_store.persist_metadata(
                    iteration=iteration,
                    stop_reason="blocked",
                    requirements=requirements,
                    validation_report=validation_report,
                    blueprint_validation=blueprint_validation,
                )
                await self._send_supervisor_assistant(
                    title="Supervisor: Loop blocked",
                    content=(
                        "Stopping because the validator marked the run as blocked and "
                        "further automatic edits are unlikely to help."
                    ),
                )
                return LoopRunResult(
                    code=best_code if best_code.strip() else last_code,
                    requirements=requirements,
                    blueprint_validation=blueprint_validation,
                    iterations=iterations,
                    stop_reason="blocked",
                    saved_code_path=self._artifact_store.paths.best_file_path,
                    saved_run_dir=self._artifact_store.paths.run_dir,
                    analyzer_model=self._analyzer.model,
                    executor_model=self._executor.model,
                    validator_model=self._validator.model,
                )

            current_file_state = {"path": "index.html", "content": last_code}

        self._artifact_store.persist_metadata(
            iteration=len(iterations),
            stop_reason="max_iterations",
            requirements=requirements,
            validation_report=validation_report,
            blueprint_validation=blueprint_validation,
        )
        await self._send_supervisor_assistant(
            title="Supervisor: Loop stopped at iteration cap",
            content=(
                f"The loop hit the configured limit of {self._max_iterations} iterations "
                "before reaching a passing score."
            ),
        )
        return LoopRunResult(
            code=best_code if best_code.strip() else last_code,
            requirements=requirements,
            blueprint_validation=blueprint_validation,
            iterations=iterations,
            stop_reason="max_iterations",
            saved_code_path=self._artifact_store.paths.best_file_path,
            saved_run_dir=self._artifact_store.paths.run_dir,
            analyzer_model=self._analyzer.model,
            executor_model=self._executor.model,
            validator_model=self._validator.model,
        )

    async def _status(self, message: str, data: dict[str, object] | None = None) -> None:
        await self._send_message("status", message, 0, data, None)

    async def _validate_blueprint_before_execution(
        self,
        requirements: RequirementsSpec,
        *,
        reference_bundle: ReferenceBundle,
        current_html: str | None,
        prior_validation: ValidationReport | None,
        prior_blueprint_validation: BlueprintValidationReport | None,
    ) -> tuple[RequirementsSpec, BlueprintValidationReport | None, bool]:
        if not _requires_explicit_section_blueprint(reference_bundle):
            return requirements, None, False

        current_requirements = requirements
        current_prior_blueprint_validation = prior_blueprint_validation

        for attempt in range(1, self._max_blueprint_validation_attempts + 1):
            await self._send_supervisor_thinking(
                title="Supervisor: Reviewing blueprint coverage",
                content=(
                    "Checking whether the supervisor requirements cover the full page, "
                    "the closing state, and the canonical section blueprint before any "
                    "HTML generation begins."
                ),
            )
            await self._status(
                "Blueprint QA: validating supervisor requirements before execution."
            )
            blueprint_validation = await self._validate_blueprint_once(
                reference_bundle=reference_bundle,
                requirements=current_requirements,
                prior_blueprint_validation=current_prior_blueprint_validation,
            )
            self._artifact_store.persist_metadata(
                iteration=0,
                stop_reason=None,
                requirements=current_requirements,
                validation_report=prior_validation,
                blueprint_validation=blueprint_validation,
            )
            if blueprint_validation.verdict == "pass":
                return current_requirements, blueprint_validation, attempt > 1

            if attempt >= self._max_blueprint_validation_attempts:
                await self._status(
                    "Blueprint QA blocked execution after "
                    f"{self._max_blueprint_validation_attempts} failed repair attempts."
                )
                self._artifact_store.persist_metadata(
                    iteration=0,
                    stop_reason="blocked",
                    requirements=current_requirements,
                    validation_report=prior_validation,
                    blueprint_validation=blueprint_validation,
                )
                raise RuntimeError(self._format_blueprint_failure(blueprint_validation))

            await self._send_supervisor_thinking(
                title="Supervisor: Repairing blueprint",
                content=(
                    "Updating the supervisor requirements to restore missing sections, "
                    "closing coverage, and any contradictory planning details before the "
                    "executor is allowed to continue."
                ),
            )
            await self._status(
                "Blueprint QA: repairing missing sections and blueprint inconsistencies."
            )
            current_requirements = await self._analyzer.analyze(
                reference_bundle,
                current_html,
                prior_requirements=current_requirements,
                prior_validation=prior_validation,
                prior_blueprint_validation=blueprint_validation,
            )
            current_prior_blueprint_validation = blueprint_validation

        return current_requirements, None, False

    async def _validate_blueprint_once(
        self,
        *,
        reference_bundle: ReferenceBundle,
        requirements: RequirementsSpec,
        prior_blueprint_validation: BlueprintValidationReport | None,
    ) -> BlueprintValidationReport:
        sanity_report = self._build_blueprint_sanity_report(
            requirements=requirements,
            reference_bundle=reference_bundle,
        )
        if sanity_report is not None:
            return sanity_report

        return await self._blueprint_validator.validate(
            reference_bundle=reference_bundle,
            requirements=requirements,
            prior_blueprint_validation=prior_blueprint_validation,
        )

    def _build_blueprint_sanity_report(
        self,
        *,
        requirements: RequirementsSpec,
        reference_bundle: ReferenceBundle,
    ) -> BlueprintValidationReport | None:
        if not _requires_explicit_section_blueprint(reference_bundle):
            return None

        issues: list[BlueprintValidationIssue] = []
        missing_sections: list[str] = []

        named_sections = [
            section for section in requirements.section_requirements if section.name.strip()
        ]
        if not named_sections:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="No section blueprint returned",
                    detail=(
                        "The supervisor returned no named `section_requirements` even "
                        "though visual reference evidence exists for this run."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Populate `section_requirements` with the full top-to-bottom "
                        "canonical section list before execution starts."
                    ),
                )
            )
        blank_named_sections = [
            index + 1
            for index, section in enumerate(requirements.section_requirements)
            if not section.name.strip()
        ]
        if blank_named_sections:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="consistency",
                    title="Unnamed section entries in blueprint",
                    detail=(
                        "One or more `section_requirements` entries are present but have "
                        "no stable section name, which breaks canonical section tracking."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Give every `section_requirements` entry a distinct, non-empty "
                        "section name in top-to-bottom order."
                    ),
                )
            )
        section_ids: dict[str, str] = {}
        duplicate_section_ids: list[str] = []
        for section in named_sections:
            prior_name = section_ids.get(section.section_id)
            if prior_name is None:
                section_ids[section.section_id] = section.name.strip()
                continue
            duplicate_section_ids.append(section.section_id)
        if duplicate_section_ids:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="consistency",
                    title="Duplicate canonical section IDs",
                    detail=(
                        "Multiple `section_requirements` normalize to the same "
                        "`section_id`, which would make DOM coverage tracking ambiguous."
                    ),
                    affected_fields=["section_requirements"],
                    fix_instructions=(
                        "Rename the conflicting sections so each normalized `section_id` "
                        "is unique and stable."
                    ),
                )
            )
        if not requirements.page_outline:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="Missing page outline",
                    detail=(
                        "The blueprint does not include `page_outline`, so there is no "
                        "explicit ledger of the full top-to-bottom page scan."
                    ),
                    affected_fields=["page_outline"],
                    fix_instructions=(
                        "Populate `page_outline` with the full top-to-bottom page scan "
                        "before execution begins."
                    ),
                )
            )
        if requirements.footer_present is None:
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="consistency",
                    title="Footer presence not assessed",
                    detail=(
                        "The blueprint leaves `footer_present` unset even though visual "
                        "reference evidence exists."
                    ),
                    affected_fields=["footer_present"],
                    fix_instructions=(
                        "Set `footer_present` explicitly to `true` or `false`, and add "
                        "matching footer coverage when it is present."
                    ),
                )
            )
        closing_references = [
            *requirements.closing_sections,
            *(section.name for section in named_sections),
        ]
        if requirements.footer_present and not (
            requirements.footer_description.strip()
            or _mentions_footer_region(closing_references)
        ):
            issues.append(
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="Footer marked present but not represented",
                    detail=(
                        "The blueprint says a footer or closing region is present, but it "
                        "is not described in `footer_description`, `closing_sections`, or "
                        "the canonical section names."
                    ),
                    affected_fields=[
                        "footer_present",
                        "footer_description",
                        "closing_sections",
                        "section_requirements",
                    ],
                    fix_instructions=(
                        "Add the footer or closing region explicitly to `footer_description`, "
                        "`closing_sections`, and `section_requirements`."
                    ),
                )
            )
            missing_sections.append("Footer or closing region")

        if not issues:
            return None

        coverage_issue_count = sum(issue.category == "coverage" for issue in issues)
        consistency_issue_count = sum(
            issue.category == "consistency" for issue in issues
        )
        return BlueprintValidationReport(
            verdict="blocked",
            overall_score=0.0,
            coverage_score=0.0 if coverage_issue_count else 0.5,
            consistency_score=0.0 if consistency_issue_count else 0.5,
            execution_readiness_score=0.0,
            summary="Blueprint sanity checks failed before execution.",
            issues=issues,
            missing_sections=missing_sections,
            repair_instructions=[issue.fix_instructions for issue in issues],
        )

    def _format_blueprint_failure(
        self,
        blueprint_validation: BlueprintValidationReport,
    ) -> str:
        top_issues = [
            issue.title.strip()
            for issue in blueprint_validation.issues
            if issue.title.strip()
        ]
        top_failure_summary = "; ".join(top_issues[:3])
        if not top_failure_summary:
            top_failure_summary = blueprint_validation.summary.strip() or (
                "Blueprint QA rejected the requirements plan."
            )
        return (
            "Blueprint QA failed before execution: "
            f"{top_failure_summary}. Refusing to execute with a rejected blueprint."
        )

    async def _send_supervisor_thinking(self, *, title: str, content: str) -> None:
        await self._send_message(
            "thinking",
            content,
            0,
            {
                "source": "supervisor",
                "title": title,
            },
            self._next_event_id("supervisor-thinking"),
        )

    async def _send_supervisor_assistant(self, *, title: str, content: str) -> None:
        await self._send_message(
            "assistant",
            content,
            0,
            {
                "source": "supervisor",
                "title": title,
            },
            self._next_event_id("supervisor-assistant"),
        )

    def _next_event_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    async def _enrich_live_reference(
        self, reference_bundle: ReferenceBundle
    ) -> ReferenceBundle:
        if (
            not reference_bundle.reference_url.strip()
            or reference_bundle.live_reference is not None
        ):
            return reference_bundle

        await self._status(
            "Inspecting live reference URL via Chrome DevTools and capturing example renders.",
            data={"referenceUrl": reference_bundle.reference_url},
        )
        try:
            live_reference = await self._live_reference_extractor.extract(
                url=reference_bundle.reference_url,
                viewport=_live_reference_viewport(reference_bundle),
            )
        except Exception as exc:
            raise RuntimeError(
                "Live reference URL inspection failed: " + str(exc)
            ) from exc

        await self._status(
            "Captured live reference renders and extracted design-system details.",
            data={
                "referenceUrl": reference_bundle.reference_url,
                "renderCount": len(live_reference.renders),
            },
        )
        return reference_bundle.model_copy(update={"live_reference": live_reference})

    async def _ensure_design_system_preflight(
        self, reference_bundle: ReferenceBundle
    ) -> ReferenceBundle:
        if reference_bundle.design_system_preflight is not None:
            persisted_design_system = self._persist_design_system_preflight_artifacts(
                reference_bundle.design_system_preflight
            )
            await self._status(
                "Design-system preflight ready.",
                data={
                    "artifactPath": persisted_design_system.html_artifact_path,
                    "runDir": self._artifact_store.paths.run_dir,
                },
            )
            return reference_bundle.model_copy(
                update={"design_system_preflight": persisted_design_system}
            )

        reused_design_system = self._resolve_reusable_design_system(reference_bundle)
        if reused_design_system is not None:
            persisted_design_system = self._persist_design_system_preflight_artifacts(
                reused_design_system
            )
            await self._status(
                "Reusing saved design-system preflight artifact.",
                data={
                    "artifactPath": persisted_design_system.html_artifact_path,
                    "runDir": self._artifact_store.paths.run_dir,
                    "reuseMode": self._design_system_reuse_mode,
                },
            )
            return reference_bundle.model_copy(
                update={"design_system_preflight": persisted_design_system}
            )

        if self._design_system_reuse_mode == "require_reuse":
            raise RuntimeError(
                "Validated loop was configured to require a reusable design-system preflight, "
                "but no compatible saved artifact was available."
            )

        if not _needs_design_system_preflight(reference_bundle):
            await self._status(
                "Skipping design-system preflight generation for this simple run.",
                data={
                    "reason": "No video input, live reference, or reference URL was provided.",
                    "runDir": self._artifact_store.paths.run_dir,
                },
            )
            return reference_bundle

        await self._status(
            "Generating required design-system preflight artifact.",
            data={"runDir": self._artifact_store.paths.run_dir},
        )
        design_system = await self._design_system_builder.build(reference_bundle)
        persisted_design_system = self._persist_design_system_preflight_artifacts(
            design_system
        )
        await self._status(
            "Design-system preflight ready.",
            data={
                "artifactPath": persisted_design_system.html_artifact_path,
                "runDir": self._artifact_store.paths.run_dir,
            },
        )
        return reference_bundle.model_copy(
            update={"design_system_preflight": persisted_design_system}
        )

    def _resolve_reusable_design_system(
        self, reference_bundle: ReferenceBundle
    ) -> DesignSystemPreflight | None:
        if self._design_system_reuse_mode == "generate":
            return None

        candidate_errors: list[str] = []

        explicit_run_dir = (
            self._design_system_reuse_run_dir.strip()
            if self._design_system_reuse_run_dir
            else ""
        )
        if explicit_run_dir:
            try:
                return self._load_compatible_design_system_from_run_dir(
                    explicit_run_dir,
                    reference_bundle,
                )
            except Exception as exc:
                candidate_errors.append(str(exc))

        cached_design_system = load_design_system_preflight_from_current_cache()
        cached_reference_bundle = load_reference_bundle_from_current_cache()
        if (
            cached_design_system is not None
            and cached_reference_bundle is not None
            and self._design_system_reference_bundles_compatible(
                current=reference_bundle,
                candidate=cached_reference_bundle,
            )
        ):
            return cached_design_system

        if self._design_system_reuse_mode == "require_reuse" and candidate_errors:
            raise RuntimeError(candidate_errors[0])

        return None

    def _load_compatible_design_system_from_run_dir(
        self,
        run_dir: str,
        reference_bundle: ReferenceBundle,
    ) -> DesignSystemPreflight:
        source_reference_bundle = ValidatedLoopArtifactStore.load_reference_bundle(run_dir)
        if not self._design_system_reference_bundles_compatible(
            current=reference_bundle,
            candidate=source_reference_bundle,
        ):
            raise RuntimeError(
                "Saved design-system preflight is not compatible with the current reference input."
            )
        return load_design_system_preflight_from_run_dir(run_dir)

    @staticmethod
    def _design_system_reference_bundles_compatible(
        *,
        current: ReferenceBundle,
        candidate: ReferenceBundle,
    ) -> bool:
        if current.input_mode != candidate.input_mode:
            return False

        current_reference_url = current.reference_url.strip()
        candidate_reference_url = candidate.reference_url.strip()
        if bool(current_reference_url) != bool(candidate_reference_url):
            return False
        if current_reference_url and candidate_reference_url:
            if current_reference_url != candidate_reference_url:
                return False

        current_live_url = (
            current.live_reference.url.strip()
            if current.live_reference is not None
            else ""
        )
        candidate_live_url = (
            candidate.live_reference.url.strip()
            if candidate.live_reference is not None
            else ""
        )
        if bool(current_live_url) != bool(candidate_live_url):
            return False
        if current_live_url and candidate_live_url and current_live_url != candidate_live_url:
            return False

        if bool(current.images) != bool(candidate.images):
            return False
        if current.images and candidate.images:
            if _media_fingerprints(current.images) != _media_fingerprints(candidate.images):
                return False

        if bool(current.videos) != bool(candidate.videos):
            return False
        if current.videos and candidate.videos:
            if _media_fingerprints(current.videos) != _media_fingerprints(candidate.videos):
                return False

        if current.images and candidate.images and len(current.images) != len(candidate.images):
            return False

        if current.videos and candidate.videos and len(current.videos) != len(candidate.videos):
            return False

        return True

    def _persist_design_system_preflight_artifacts(
        self, design_system: DesignSystemPreflight
    ) -> DesignSystemPreflight:
        design_system_json, design_system_html = self._design_system_renderer.render(
            design_system
        )
        run_json_path, run_html_path = self._artifact_store.persist_design_system_artifacts(
            design_system_json=design_system_json,
            design_system_html=design_system_html,
        )
        return design_system.model_copy(
            update={
                "json_artifact_path": run_json_path,
                "html_artifact_path": run_html_path,
            }
        )

    def _should_stop_after_validation(
        self,
        *,
        reference_bundle: ReferenceBundle,
        validation_report: ValidationReport,
    ) -> bool:
        if validation_report.verdict != "pass":
            return False

        if self._has_blocking_issues(validation_report):
            return False

        if reference_bundle.input_mode != "video":
            return validation_report.overall_score >= VALIDATED_LOOP_PASS_SCORE

        return (
            validation_report.overall_score >= VIDEO_VALIDATED_LOOP_PASS_SCORE
            and validation_report.behavior_fidelity_score
            >= VIDEO_VALIDATED_LOOP_BEHAVIOR_PASS_SCORE
            and validation_report.animation_fidelity_score
            >= VIDEO_VALIDATED_LOOP_ANIMATION_PASS_SCORE
            and not self._has_major_motion_or_behavior_gaps(validation_report)
        )

    def _has_blocking_issues(self, validation_report: ValidationReport) -> bool:
        return any(issue.severity == "critical" for issue in validation_report.issues)

    def _has_major_motion_or_behavior_gaps(
        self, validation_report: ValidationReport
    ) -> bool:
        return any(
            issue.severity in {"critical", "major"}
            and issue.category in {"behavior", "animation"}
            for issue in validation_report.issues
        )

    def _is_better_validation(
        self,
        *,
        candidate: ValidationReport,
        incumbent: ValidationReport | None,
    ) -> bool:
        if incumbent is None:
            return True

        verdict_rank = {"blocked": 0, "revise": 1, "pass": 2}
        candidate_tuple = (
            verdict_rank[candidate.verdict],
            candidate.overall_score,
            candidate.visual_fidelity_score,
            candidate.behavior_fidelity_score,
            candidate.animation_fidelity_score,
            -sum(issue.severity == "critical" for issue in candidate.issues),
            -sum(issue.severity == "major" for issue in candidate.issues),
            -len(candidate.issues),
            candidate.editability_score,
        )
        incumbent_tuple = (
            verdict_rank[incumbent.verdict],
            incumbent.overall_score,
            incumbent.visual_fidelity_score,
            incumbent.behavior_fidelity_score,
            incumbent.animation_fidelity_score,
            -sum(issue.severity == "critical" for issue in incumbent.issues),
            -sum(issue.severity == "major" for issue in incumbent.issues),
            -len(incumbent.issues),
            incumbent.editability_score,
        )
        return candidate_tuple > incumbent_tuple

    def _summarize_requirements(self, requirements: RequirementsSpec) -> str:
        lines = []
        if requirements.summary:
            lines.append(f"Summary: {requirements.summary}")
        if requirements.template_goal:
            lines.append(f"Template goal: {requirements.template_goal}")
        if requirements.page_outline:
            lines.append(
                "Page outline:\n- " + "\n- ".join(requirements.page_outline[:6])
            )
        if requirements.closing_sections:
            lines.append(
                "Closing sections:\n- "
                + "\n- ".join(requirements.closing_sections[:5])
            )
        if requirements.footer_present is not None:
            footer_line = (
                "Footer assessment: present"
                if requirements.footer_present
                else "Footer assessment: not present"
            )
            if requirements.footer_description:
                footer_line += f" — {requirements.footer_description}"
            lines.append(footer_line)
        if requirements.coverage_notes:
            lines.append(
                "Coverage notes:\n- "
                + "\n- ".join(requirements.coverage_notes[:4])
            )
        if requirements.hard_constraints:
            lines.append(
                "Hard constraints:\n- "
                + "\n- ".join(requirements.hard_constraints[:4])
            )
        if requirements.preserve_requirements:
            lines.append(
                "Preserve as-is:\n- "
                + "\n- ".join(requirements.preserve_requirements[:4])
            )
        if requirements.section_requirements:
            lines.append(
                "Primary sections:\n- "
                + "\n- ".join(
                    section.name for section in requirements.section_requirements[:4]
                )
            )
        if requirements.layout_requirements:
            lines.append(
                "Key layout requirements:\n- "
                + "\n- ".join(requirements.layout_requirements[:4])
            )
        if requirements.execution_plan:
            lines.append(
                "Execution plan:\n- "
                + "\n- ".join(requirements.execution_plan[:4])
            )
        if requirements.behavior_requirements:
            lines.append(
                "Key behavior requirements:\n- "
                + "\n- ".join(requirements.behavior_requirements[:3])
            )
        if requirements.animation_requirements:
            lines.append(
                "Key animation requirements:\n- "
                + "\n- ".join(requirements.animation_requirements[:3])
            )
        if requirements.structure_guidance:
            lines.append(
                "Template structure guidance:\n- "
                + "\n- ".join(requirements.structure_guidance[:4])
            )
        return "\n\n".join(lines) or "Requirements captured."

    def _summarize_validation(self, validation_report: ValidationReport) -> str:
        lines = [
            f"Verdict: {validation_report.verdict}",
            f"Score: {validation_report.overall_score:.2f}",
            f"Visual fidelity: {validation_report.visual_fidelity_score:.2f}",
            f"Behavior fidelity: {validation_report.behavior_fidelity_score:.2f}",
            f"Animation fidelity: {validation_report.animation_fidelity_score:.2f}",
        ]
        if validation_report.summary:
            lines.append(f"Summary: {validation_report.summary}")
        if validation_report.section_results:
            missing_sections = [
                result.name
                for result in validation_report.section_results
                if result.status == "missing"
            ]
            partial_sections = [
                result.name
                for result in validation_report.section_results
                if result.status == "partial"
            ]
            if missing_sections:
                lines.append("Missing sections:\n- " + "\n- ".join(missing_sections[:4]))
            if partial_sections:
                lines.append("Partial sections:\n- " + "\n- ".join(partial_sections[:4]))
        if validation_report.issues:
            lines.append(
                "Top issues:\n- "
                + "\n- ".join(issue.title for issue in validation_report.issues[:4])
            )
        if validation_report.patch_instructions:
            lines.append(
                "Next edits:\n- "
                + "\n- ".join(validation_report.patch_instructions[:4])
            )
        return "\n\n".join(lines)

    @property
    def analyzer_model(self):
        return self._analyzer.model

    @property
    def executor_model(self):
        return self._executor.model

    @property
    def validator_model(self):
        return self._validator.model


def _media_fingerprints(items: list[str]) -> list[str]:
    return [sha256(item.encode("utf-8")).hexdigest() for item in items]
