import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from config import (
    VALIDATED_LOOP_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_ANIMATION_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_BEHAVIOR_PASS_SCORE,
    VIDEO_VALIDATED_LOOP_PASS_SCORE,
)
from loop.artifacts import ValidatedLoopArtifactStore
from loop.analyzer import LoopAnalyzer
from loop.contracts import (
    LoopIterationRecord,
    LoopResumeState,
    LoopRunResult,
    ReferenceBundle,
    RequirementsSpec,
    ValidationReport,
)
from loop.executor import LoopExecutor
from loop.renderer import HtmlPreviewRenderer
from loop.validator import LoopValidator


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
        renderer: HtmlPreviewRenderer | None = None,
        analyzer: LoopAnalyzer | None = None,
        validator: LoopValidator | None = None,
        executor: LoopExecutor | None = None,
        artifact_store: ValidatedLoopArtifactStore | None = None,
    ) -> None:
        self._send_message = send_message
        self._max_iterations = max_iterations
        self._analyzer = analyzer or LoopAnalyzer(gemini_api_key)
        self._validator = validator or LoopValidator(gemini_api_key)
        self._renderer = renderer or HtmlPreviewRenderer()
        self._artifact_store = artifact_store or ValidatedLoopArtifactStore()
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
        await self._send_supervisor_assistant(
            title="Supervisor: Requirements draft ready",
            content=self._summarize_requirements(requirements),
        )
        validation_report: ValidationReport | None = (
            resume_state.latest_validation if resume_state else None
        )
        iterations: list[LoopIterationRecord] = []
        last_code = current_file_state.get("content", "") if current_file_state else ""
        best_code = last_code
        best_validation_report = validation_report

        if best_code and best_validation_report is not None:
            self._artifact_store.persist_best_checkpoint(
                html=best_code,
                iteration=0,
                requirements=requirements,
                validation_report=best_validation_report,
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
                f"Iteration {iteration}/{self._max_iterations}: executing with Claude Opus 4.6."
            )
            last_code = await self._executor.execute(
                reference_bundle=reference_bundle,
                requirements=requirements,
                file_state=current_file_state,
                validation_report=validation_report,
                iteration=iteration,
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
            validation_report = await self._validator.validate(
                reference_bundle=reference_bundle,
                requirements=requirements,
                render_artifact=render_artifact,
                current_html=last_code,
                iteration=iteration,
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
                    iterations=iterations,
                    stop_reason="pass",
                    saved_code_path=self._artifact_store.paths.best_file_path,
                    saved_run_dir=self._artifact_store.paths.run_dir,
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
                    iterations=iterations,
                    stop_reason="blocked",
                    saved_code_path=self._artifact_store.paths.best_file_path,
                    saved_run_dir=self._artifact_store.paths.run_dir,
                )

            current_file_state = {"path": "index.html", "content": last_code}

        self._artifact_store.persist_metadata(
            iteration=len(iterations),
            stop_reason="max_iterations",
            requirements=requirements,
            validation_report=validation_report,
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
            iterations=iterations,
            stop_reason="max_iterations",
            saved_code_path=self._artifact_store.paths.best_file_path,
            saved_run_dir=self._artifact_store.paths.run_dir,
        )

    async def _status(self, message: str, data: dict[str, object] | None = None) -> None:
        await self._send_message("status", message, 0, data, None)

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
