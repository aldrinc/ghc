from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm import Llm
from loop.contracts import (
    DesignSystemPreflight,
    DesignTokenSet,
    LiveReferenceContext,
    LiveReferenceDesignSystem,
    LiveReferenceRender,
    LoopRunResult,
    ReferenceBundle,
    RequirementsSpec,
    SectionRequirement,
    ValidationReport,
)
from loop.executor import LoopExecutor
from routes.generate_code import (
    CodeGenerationMiddleware,
    ExtractedParams,
    PipelineContext,
)


class _StaticDesignSystemBuilder:
    async def build(self, reference_bundle) -> DesignSystemPreflight:
        return DesignSystemPreflight(
            title="Test design system",
            summary="Use the captured design system.",
            typography=["Body uses 'Inter'."],
            colors=["Primary text uses rgb(17, 24, 39)."],
        )


class _StaticDesignSystemRenderer:
    def render(self, design_system) -> tuple[str, str]:
        payload = cast(Any, design_system).model_dump_json(indent=2)
        return (payload, "<html><body>design system</body></html>")


def _requirements_with_section_blueprint(summary: str) -> RequirementsSpec:
    return RequirementsSpec(
        summary=summary,
        page_outline=["Header", "Hero", "Footer"],
        closing_sections=["Hero", "Footer"],
        footer_present=True,
        footer_description="Footer with legal and contact links.",
        coverage_notes=["Treat the footer as an explicit closing page region."],
        section_requirements=[
            SectionRequirement(
                name="Hero",
                must_include=["headline"],
            )
        ],
    )


@pytest.mark.asyncio
async def test_code_generation_middleware_runs_validated_loop(monkeypatch) -> None:
    sent_messages: list[tuple[str, str | None, int]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index))

    class FakeValidatedLoopOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.executor_model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def run(
            self,
            *,
            reference_bundle,
            initial_file_state,
            resume_state=None,
        ) -> LoopRunResult:
            assert reference_bundle.input_mode == "image"
            assert reference_bundle.reference_url == "https://example.com/reference"
            assert initial_file_state is None
            return LoopRunResult(
                code="<html><body>validated</body></html>",
                requirements=RequirementsSpec(),
                iterations=[],
                stop_reason="pass",
            )

    monkeypatch.setattr(
        "routes.generate_code.ValidationLoopOrchestrator",
        FakeValidatedLoopOrchestrator,
    )

    context = PipelineContext(websocket=MagicMock())
    context.ws_comm = cast(
        Any,
        SimpleNamespace(
            send_message=send_message,
            throw_error=AsyncMock(),
        ),
    )
    context.extracted_params = ExtractedParams(
        stack="html_tailwind",
        input_mode="image",
        should_generate_images=True,
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        openai_base_url=None,
        generation_type="create",
        prompt={
            "text": "Create this page",
            "images": ["data:image/png;base64,abc"],
            "videos": [],
            "reference_url": "https://example.com/reference",
        },
        history=[],
        file_state=None,
        option_codes=[],
        orchestration_mode="validated_loop",
        max_validation_iterations=2,
    )

    middleware = CodeGenerationMiddleware()
    next_called = False

    async def next_func() -> None:
        nonlocal next_called
        next_called = True

    await middleware.process(context, next_func)

    assert context.variant_models == [Llm.GEMINI_3_1_PRO_PREVIEW_HIGH]
    assert context.completions == ["<html><body>validated</body></html>"]
    assert ("setCode", "<html><body>validated</body></html>", 0) in sent_messages
    assert ("variantComplete", "Validated loop generation complete", 0) in sent_messages
    assert next_called is True


@pytest.mark.asyncio
async def test_code_generation_middleware_does_not_require_openai_key_for_validated_loop(
    monkeypatch,
) -> None:
    send_message = AsyncMock()
    throw_error = AsyncMock()

    class FakeValidatedLoopOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.executor_model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def run(
            self,
            *,
            reference_bundle,
            initial_file_state,
            resume_state=None,
        ) -> LoopRunResult:
            return LoopRunResult(
                code="<html><body>validated</body></html>",
                requirements=RequirementsSpec(),
                iterations=[],
                stop_reason="pass",
            )

    monkeypatch.setattr(
        "routes.generate_code.ValidationLoopOrchestrator",
        FakeValidatedLoopOrchestrator,
    )

    context = PipelineContext(websocket=MagicMock())
    context.ws_comm = cast(
        Any,
        SimpleNamespace(
            send_message=send_message,
            throw_error=throw_error,
        ),
    )
    context.extracted_params = ExtractedParams(
        stack="html_tailwind",
        input_mode="image",
        should_generate_images=True,
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        openai_base_url=None,
        generation_type="create",
        prompt={
            "text": "Create this page",
            "images": ["data:image/png;base64,abc"],
            "videos": [],
        },
        history=[],
        file_state=None,
        option_codes=[],
        orchestration_mode="validated_loop",
        max_validation_iterations=2,
    )

    middleware = CodeGenerationMiddleware()

    next_called = False

    async def next_func() -> None:
        nonlocal next_called
        next_called = True

    await middleware.process(context, next_func)

    throw_error.assert_not_awaited()
    assert context.variant_models == [Llm.GEMINI_3_1_PRO_PREVIEW_HIGH]
    assert next_called is True


@pytest.mark.asyncio
async def test_code_generation_middleware_preserves_saved_design_system_on_continue(
    monkeypatch, tmp_path: Path
) -> None:
    from loop.artifacts import ValidatedLoopArtifactStore

    sent_messages: list[tuple[str, str | None, int]] = []
    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    saved_reference_bundle = ReferenceBundle(
        input_mode="image",
        stack="html_tailwind",
        user_text="Original request",
        images=["data:image/png;base64,abc"],
        videos=[],
        reference_url="https://example.com/reference",
        design_system_preflight=DesignSystemPreflight(
            title="Saved design system",
            summary="Reuse me",
            typography=["Inter"],
        ),
    )
    artifact_store.persist_reference_bundle(saved_reference_bundle)
    artifact_store.persist_metadata(
        iteration=0,
        stop_reason=None,
        requirements=None,
        validation_report=None,
    )

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index))

    class FakeValidatedLoopOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.executor_model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def run(
            self,
            *,
            reference_bundle,
            initial_file_state,
            resume_state=None,
        ) -> LoopRunResult:
            assert reference_bundle.design_system_preflight is not None
            assert reference_bundle.design_system_preflight.title == "Saved design system"
            return LoopRunResult(
                code="<html><body>validated</body></html>",
                requirements=RequirementsSpec(),
                iterations=[],
                stop_reason="pass",
            )

    monkeypatch.setattr(
        "routes.generate_code.ValidationLoopOrchestrator",
        FakeValidatedLoopOrchestrator,
    )

    context = PipelineContext(websocket=MagicMock())
    context.ws_comm = cast(
        Any,
        SimpleNamespace(
            send_message=send_message,
            throw_error=AsyncMock(),
        ),
    )
    context.extracted_params = ExtractedParams(
        stack="html_tailwind",
        input_mode="image",
        should_generate_images=True,
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        openai_base_url=None,
        generation_type="update",
        prompt={
            "text": "Continue",
            "images": [],
            "videos": [],
        },
        history=[],
        file_state={"path": "index.html", "content": "<html></html>"},
        option_codes=[],
        orchestration_mode="validated_loop",
        max_validation_iterations=2,
        validated_loop_reference_run_dir=artifact_store.paths.run_dir,
    )

    middleware = CodeGenerationMiddleware()

    async def next_func() -> None:
        return None

    await middleware.process(context, next_func)

    assert ("variantComplete", "Validated loop generation complete", 0) in sent_messages


@pytest.mark.asyncio
async def test_code_generation_middleware_marks_max_iteration_stop_as_resumable(
    monkeypatch,
) -> None:
    sent_messages: list[
        tuple[str, str | None, int, dict[str, object] | None]
    ] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeValidatedLoopOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.executor_model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def run(
            self,
            *,
            reference_bundle,
            initial_file_state,
            resume_state=None,
        ) -> LoopRunResult:
            return LoopRunResult(
                code="<html><body>almost there</body></html>",
                requirements=RequirementsSpec(),
                iterations=[],
                stop_reason="max_iterations",
            )

    monkeypatch.setattr(
        "routes.generate_code.ValidationLoopOrchestrator",
        FakeValidatedLoopOrchestrator,
    )

    context = PipelineContext(websocket=MagicMock())
    context.ws_comm = cast(
        Any,
        SimpleNamespace(
            send_message=send_message,
            throw_error=AsyncMock(),
        ),
    )
    context.extracted_params = ExtractedParams(
        stack="html_tailwind",
        input_mode="image",
        should_generate_images=True,
        openai_api_key=None,
        anthropic_api_key="anthropic-key",
        gemini_api_key="key",
        openai_base_url=None,
        generation_type="create",
        prompt={
            "text": "Create this page",
            "images": ["data:image/png;base64,abc"],
            "videos": [],
        },
        history=[],
        file_state=None,
        option_codes=[],
        orchestration_mode="validated_loop",
        max_validation_iterations=10,
    )

    middleware = CodeGenerationMiddleware()

    async def next_func() -> None:
        return None

    await middleware.process(context, next_func)

    assert (
        "variantError",
        "Validated loop stopped before reaching a passing result (max_iterations).",
        0,
        {
            "artifactPath": None,
            "stopReason": "max_iterations",
            "iterationsCompleted": 0,
            "maxIterations": 10,
            "canContinue": True,
            "runDir": None,
        },
    ) in sent_messages


@pytest.mark.asyncio
async def test_code_generation_middleware_normalizes_video_before_validated_loop(
    monkeypatch,
) -> None:
    sent_messages: list[tuple[str, str | None, int]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index))

    normalized_video = "data:video/mp4;base64,normalized"

    class FakeValidatedLoopOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.executor_model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def run(
            self,
            *,
            reference_bundle,
            initial_file_state,
            resume_state=None,
        ) -> LoopRunResult:
            assert reference_bundle.input_mode == "video"
            assert reference_bundle.videos == [normalized_video]
            assert initial_file_state is None
            return LoopRunResult(
                code="<html><body>validated</body></html>",
                requirements=RequirementsSpec(),
                iterations=[],
                stop_reason="pass",
            )

    monkeypatch.setattr(
        "routes.generate_code.ValidationLoopOrchestrator",
        FakeValidatedLoopOrchestrator,
    )
    def fake_normalize_videos(videos: list[str]) -> list[str]:
        return [normalized_video for _video in videos]

    monkeypatch.setattr(
        "routes.generate_code.normalize_video_data_urls_for_llm",
        fake_normalize_videos,
    )

    context = PipelineContext(websocket=MagicMock())
    context.ws_comm = cast(
        Any,
        SimpleNamespace(
            send_message=send_message,
            throw_error=AsyncMock(),
        ),
    )
    context.extracted_params = ExtractedParams(
        stack="html_tailwind",
        input_mode="video",
        should_generate_images=True,
        openai_api_key=None,
        anthropic_api_key="anthropic-key",
        gemini_api_key="key",
        openai_base_url=None,
        generation_type="create",
        prompt={
            "text": "Create this animated page",
            "images": [],
            "videos": ["data:video/quicktime;base64,abc"],
        },
        history=[],
        file_state=None,
        option_codes=[],
        orchestration_mode="validated_loop",
        max_validation_iterations=2,
    )

    middleware = CodeGenerationMiddleware()

    async def next_func() -> None:
        return None

    await middleware.process(context, next_func)

    assert context.extracted_params.prompt["videos"] == [normalized_video]
    assert (
        "status",
        "Normalizing uploaded video for Gemini.",
        0,
    ) in sent_messages


@pytest.mark.asyncio
async def test_code_generation_middleware_reloads_saved_reference_bundle_for_continue(
    monkeypatch, tmp_path: Path
) -> None:
    sent_messages: list[tuple[str, str | None, int]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index))

    from loop.artifacts import ValidatedLoopArtifactStore
    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    artifact_store.persist_reference_bundle(
        ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Original reference request",
            images=[],
            videos=["data:video/mp4;base64,saved-video"],
            reference_url="https://example.com/reference",
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(
                    page_title="Reference Page",
                ),
                renders=[
                    LiveReferenceRender(
                        label="live viewport render",
                        data_url="data:image/png;base64,reference",
                    )
                ],
            ),
        )
    )
    artifact_store.persist_metadata(
        iteration=10,
        stop_reason="max_iterations",
        requirements=RequirementsSpec(summary="Keep iterating from the saved plan"),
        validation_report=ValidationReport(
            verdict="revise",
            overall_score=0.82,
            visual_fidelity_score=0.84,
            behavior_fidelity_score=0.79,
            animation_fidelity_score=0.72,
            editability_score=0.95,
            summary="The baseline is close but the motion timing is still off.",
            patch_instructions=["Fix the motion timing based on the reference video."],
        ),
    )

    class FakeValidatedLoopOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.executor_model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def run(
            self,
            *,
            reference_bundle,
            initial_file_state,
            resume_state=None,
        ) -> LoopRunResult:
            assert reference_bundle.input_mode == "video"
            assert reference_bundle.videos == ["data:video/mp4;base64,saved-video"]
            assert reference_bundle.images == []
            assert reference_bundle.reference_url == "https://example.com/reference"
            assert reference_bundle.live_reference is not None
            assert (
                reference_bundle.user_text
                == "Continue from the current implementation toward exact video fidelity."
            )
            assert initial_file_state == {
                "path": "index.html",
                "content": "<html><body>baseline</body></html>",
            }
            assert resume_state is not None
            assert resume_state.requirements is not None
            assert resume_state.requirements.summary == "Keep iterating from the saved plan"
            assert resume_state.latest_validation is not None
            assert (
                resume_state.latest_validation.patch_instructions
                == ["Fix the motion timing based on the reference video."]
            )
            return LoopRunResult(
                code="<html><body>continued</body></html>",
                requirements=RequirementsSpec(),
                iterations=[],
                stop_reason="pass",
            )

    monkeypatch.setattr(
        "routes.generate_code.ValidationLoopOrchestrator",
        FakeValidatedLoopOrchestrator,
    )

    context = PipelineContext(websocket=MagicMock())
    context.ws_comm = cast(
        Any,
        SimpleNamespace(
            send_message=send_message,
            throw_error=AsyncMock(),
        ),
    )
    context.extracted_params = ExtractedParams(
        stack="html_tailwind",
        input_mode="video",
        should_generate_images=True,
        openai_api_key=None,
        anthropic_api_key="anthropic-key",
        gemini_api_key="key",
        openai_base_url=None,
        generation_type="update",
        prompt={
            "text": "Continue from the current implementation toward exact video fidelity.",
            "images": [],
            "videos": [],
        },
        history=[],
        file_state={
            "path": "index.html",
            "content": "<html><body>baseline</body></html>",
        },
        option_codes=["<html><body>baseline</body></html>"],
        orchestration_mode="validated_loop",
        max_validation_iterations=2,
        validated_loop_reference_run_dir=artifact_store.paths.run_dir,
    )

    middleware = CodeGenerationMiddleware()

    async def next_func() -> None:
        return None

    await middleware.process(context, next_func)

    assert ("setCode", "<html><body>continued</body></html>", 0) in sent_messages


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_emits_supervisor_trace(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert current_html is None
            return RequirementsSpec(
                summary="Simple UI",
                preserve_requirements=["Keep the existing header markup intact."],
                structure_guidance=["Use shared theme tokens"],
            )

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            from loop.contracts import ValidationReport

            return ValidationReport(
                verdict="pass",
                overall_score=0.98,
                visual_fidelity_score=0.98,
                behavior_fidelity_score=0.98,
                animation_fidelity_score=0.98,
                editability_score=0.98,
                summary="Close match",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.contracts import ReferenceBundle
    from loop.orchestrator import ValidationLoopOrchestrator

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=2,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
        initial_file_state=None,
    )

    assert result.stop_reason == "pass"
    supervisor_messages = [
        msg for msg in sent_messages if msg[3] and msg[3].get("source") == "supervisor"
    ]
    assert any(msg[0] == "thinking" for msg in supervisor_messages)
    assert any(msg[0] == "assistant" for msg in supervisor_messages)
    assert any(
        msg[0] == "status"
        and msg[3] is not None
        and msg[3].get("runDir") == result.saved_run_dir
        and msg[3].get("artifactPath") == result.saved_code_path
        for msg in sent_messages
    )
    assert any(
        msg[0] == "status"
        and msg[1] is not None
        and "executing with Gemini 3.1 Pro" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_requires_98_percent_video_motion_match(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert current_html is None
            return RequirementsSpec(
                summary="Animated landing page",
                section_requirements=[
                    SectionRequirement(name="Hero", must_include=["headline"])
                ],
                animation_requirements=[
                    "Hero card and chart should animate into place during the opening sequence"
                ],
            )

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, **kwargs):
            self.calls += 1
            return f"<html><body>iteration-{self.calls}</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        def __init__(self) -> None:
            self.calls = 0

        async def validate(self, **kwargs):
            from loop.contracts import ValidationIssue, ValidationReport

            self.calls += 1
            if self.calls == 1:
                return ValidationReport(
                    verdict="pass",
                    overall_score=0.99,
                    visual_fidelity_score=0.99,
                    behavior_fidelity_score=0.91,
                    animation_fidelity_score=0.82,
                    editability_score=0.97,
                    summary="Static visuals are close, but the animation choreography is still off.",
                    issues=[
                        ValidationIssue(
                            severity="major",
                            category="animation",
                            title="Opening sequence mismatch",
                            observed="The hero content appears statically instead of animating in sequence.",
                            expected="The hero content should animate into place with the same sequencing as the reference video.",
                            fix_instructions="Add sequenced entrance animations for the hero elements and match the timing more closely.",
                        )
                    ],
                    patch_instructions=[
                        "Match the opening hero animation timing and sequencing from the reference video."
                    ],
                )

            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.98,
                summary="Animation and interaction are now close to the reference.",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.contracts import ReferenceBundle
    from loop.orchestrator import ValidationLoopOrchestrator

    executor = FakeExecutor()
    validator = FakeValidator()
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=3,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, executor),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, validator),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Match the animated website",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        initial_file_state=None,
    )

    assert result.stop_reason == "pass"
    assert executor.calls == 2
    assert validator.calls == 2
    assert len(result.iterations) == 2
    assert result.iterations[0].validation.animation_fidelity_score == 0.82
    assert result.iterations[1].validation.animation_fidelity_score == 0.99
    assert any(
        msg[3]
        and msg[3].get("source") == "supervisor"
        and msg[1]
        and "provisional pass" in msg[1].lower()
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_enriches_live_reference_before_analysis(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert current_html is None
            assert reference_bundle.live_reference is not None
            assert reference_bundle.live_reference.url == "https://example.com/reference"
            assert reference_bundle.live_reference.design_system.typography == [
                "h1: font Inter; size 56px; weight 700"
            ]
            return _requirements_with_section_blueprint(
                "Use extracted typography and colors"
            )

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    class FakeLiveReferenceExtractor:
        async def extract(self, *, url: str, viewport):
            assert url == "https://example.com/reference"
            return LiveReferenceContext(
                url=url,
                design_system=LiveReferenceDesignSystem(
                    page_title="Reference Page",
                    typography=["h1: font Inter; size 56px; weight 700"],
                    colors=["text rgb(17, 24, 39) used on ~12 elements"],
                ),
                renders=[
                    LiveReferenceRender(
                        label="live viewport render",
                        data_url="data:image/png;base64,reference",
                        viewport=viewport,
                    )
                ],
            )

    class FakeDesignSystemBuilder:
        async def build(self, reference_bundle):
            assert reference_bundle.live_reference is not None
            return DesignSystemPreflight(
                title="Required design system",
                summary="Use extracted fonts and colors.",
                typography=["Body uses 'Inter'. Heading uses 'Inter Display'."],
                colors=["Primary text is rgb(17, 24, 39)."],
            )

    class FakeDesignSystemRenderer:
        def render(self, design_system) -> tuple[str, str]:
            payload = cast(Any, design_system).model_dump_json(indent=2)
            return (
                payload,
                "<html><body>design system</body></html>",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    validator = FakeValidator()
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=2,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=artifact_store,
        live_reference_extractor=cast(Any, FakeLiveReferenceExtractor()),
        design_system_builder=cast(Any, FakeDesignSystemBuilder()),
        design_system_renderer=cast(Any, FakeDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
            reference_url="https://example.com/reference",
        ),
        initial_file_state=None,
    )

    assert result.saved_run_dir is not None
    persisted_reference = ValidatedLoopArtifactStore.load_reference_bundle(
        result.saved_run_dir
    )
    assert persisted_reference.reference_url == "https://example.com/reference"
    assert persisted_reference.live_reference is not None
    assert persisted_reference.design_system_preflight is not None
    assert persisted_reference.live_reference.design_system.page_title == "Reference Page"
    assert persisted_reference.design_system_preflight.title == "Required design system"
    assert any(
        msg[0] == "status"
        and msg[1]
        and "Inspecting live reference URL" in msg[1]
        for msg in sent_messages
    )
    assert any(
        msg[0] == "status"
        and msg[1]
        and "Design-system preflight ready" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_persists_supplied_preflight_artifacts(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is not None
            assert reference_bundle.design_system_preflight.html_artifact_path.endswith(
                "design-system/design-system.html"
            )
            return RequirementsSpec(summary="Use supplied design system")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    validator = FakeValidator()
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=artifact_store,
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
            design_system_preflight=DesignSystemPreflight(
                title="Supplied preflight",
                summary="Persist me before analysis.",
                typography=["Body uses 'Inter'."],
            ),
        ),
        initial_file_state=None,
    )

    assert result.saved_run_dir is not None
    persisted_reference = ValidatedLoopArtifactStore.load_reference_bundle(
        result.saved_run_dir
    )
    assert persisted_reference.design_system_preflight is not None
    assert persisted_reference.design_system_preflight.html_artifact_path.endswith(
        "design-system/design-system.html"
    )
    assert Path(persisted_reference.design_system_preflight.html_artifact_path).exists()


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_skips_preflight_for_simple_screenshot_run(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is None
            return RequirementsSpec(summary="Simple screenshot requirements")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    class FailIfCalledDesignSystemBuilder:
        async def build(self, reference_bundle):
            raise AssertionError("Design-system preflight should be skipped")

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    validator = FakeValidator()
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=artifact_store,
        design_system_builder=cast(Any, FailIfCalledDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this screenshot match",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
        initial_file_state=None,
    )

    assert result.stop_reason == "pass"
    persisted_reference = ValidatedLoopArtifactStore.load_reference_bundle(
        artifact_store.paths.run_dir
    )
    assert persisted_reference.design_system_preflight is None
    assert any(
        msg[0] == "status"
        and msg[1]
        and "Skipping design-system preflight generation" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_generates_preflight_for_video_run(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is not None
            assert reference_bundle.design_system_preflight.title == "Video design system"
            return _requirements_with_section_blueprint("Video requirements")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    class FakeDesignSystemBuilder:
        async def build(self, reference_bundle):
            return DesignSystemPreflight(
                title="Video design system",
                summary="Required for motion-heavy validation.",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    validator = FakeValidator()
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=artifact_store,
        design_system_builder=cast(Any, FakeDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Create this animated page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        initial_file_state=None,
    )

    assert result.stop_reason == "pass"
    persisted_reference = ValidatedLoopArtifactStore.load_reference_bundle(
        artifact_store.paths.run_dir
    )
    assert persisted_reference.design_system_preflight is not None
    assert persisted_reference.design_system_preflight.title == "Video design system"
    assert any(
        msg[0] == "status"
        and msg[1]
        and "Generating required design-system preflight artifact" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_rejects_empty_section_blueprint_for_video_run(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            return RequirementsSpec(summary="Video requirements without sections")

    class FailIfCalledExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            raise AssertionError("Executor should not run when analysis is invalid")

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            raise AssertionError("Validator should not run when analysis is invalid")

    class FakeDesignSystemBuilder:
        async def build(self, reference_bundle):
            return DesignSystemPreflight(
                title="Video design system",
                summary="Required for motion-heavy validation.",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FailIfCalledExecutor()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path),
        design_system_builder=cast(Any, FakeDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    with pytest.raises(RuntimeError, match="no `section_requirements`"):
        await orchestrator.run(
            reference_bundle=ReferenceBundle(
                input_mode="video",
                stack="html_tailwind",
                user_text="Create this animated page",
                images=[],
                videos=["data:video/mp4;base64,abc"],
            ),
            initial_file_state=None,
        )

    assert any(
        msg[0] == "status"
        and msg[1]
        and "returned no section blueprint" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_skips_preflight_for_text_only_run(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is None
            return RequirementsSpec(summary="Text-only requirements")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    class FailIfCalledDesignSystemBuilder:
        async def build(self, reference_bundle):
            raise AssertionError("Design-system preflight should be skipped")

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=artifact_store,
        design_system_builder=cast(Any, FailIfCalledDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="text",
            stack="html_tailwind",
            user_text="Build a pricing page from this text brief",
            images=[],
            videos=[],
        ),
        initial_file_state=None,
    )

    assert result.stop_reason == "pass"
    persisted_reference = ValidatedLoopArtifactStore.load_reference_bundle(
        artifact_store.paths.run_dir
    )
    assert persisted_reference.design_system_preflight is None
    assert any(
        msg[0] == "status"
        and msg[1]
        and "Skipping design-system preflight generation" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_reuses_explicit_design_system_run_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []
    source_store = ValidatedLoopArtifactStore(repo_root=tmp_path / "source")
    source_design_system = DesignSystemPreflight(
        title="Reusable design system",
        summary="Load from saved run.",
        typography=["Inter"],
    )
    source_json, source_html = _StaticDesignSystemRenderer().render(source_design_system)
    source_json_path, source_html_path = source_store.persist_design_system_artifacts(
        design_system_json=source_json,
        design_system_html=source_html,
    )
    source_store.persist_reference_bundle(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Original request",
            images=["data:image/png;base64,abc"],
            videos=[],
            reference_url="https://example.com/reference",
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(),
                renders=[],
            ),
            design_system_preflight=source_design_system.model_copy(
                update={
                    "json_artifact_path": source_json_path,
                    "html_artifact_path": source_html_path,
                }
            ),
        )
    )
    monkeypatch.setattr(
        "loop.orchestrator.load_design_system_preflight_from_current_cache",
        lambda: None,
    )
    monkeypatch.setattr(
        "loop.orchestrator.load_reference_bundle_from_current_cache",
        lambda: None,
    )

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is not None
            assert reference_bundle.design_system_preflight.title == "Reusable design system"
            return _requirements_with_section_blueprint("Reuse explicit design system")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        design_system_reuse_mode="reuse_if_available",
        design_system_reuse_run_dir=source_store.paths.run_dir,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path / "target"),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
            reference_url="https://example.com/reference",
        ),
        initial_file_state=None,
    )

    assert any(
        msg[0] == "status"
        and msg[1]
        and "Reusing saved design-system preflight artifact" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_rejects_same_count_but_different_media_reuse(
    tmp_path: Path,
) -> None:
    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    source_store = ValidatedLoopArtifactStore(repo_root=tmp_path / "source")
    source_design_system = DesignSystemPreflight(
        title="Reusable design system",
        summary="Load from saved run.",
        typography=["Inter"],
    )
    source_json, source_html = _StaticDesignSystemRenderer().render(source_design_system)
    source_json_path, source_html_path = source_store.persist_design_system_artifacts(
        design_system_json=source_json,
        design_system_html=source_html,
    )
    source_store.persist_reference_bundle(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Original request",
            images=["data:image/png;base64,source"],
            videos=[],
            design_system_preflight=source_design_system.model_copy(
                update={
                    "json_artifact_path": source_json_path,
                    "html_artifact_path": source_html_path,
                }
            ),
        )
    )

    async def send_message(*args, **kwargs):
        return None

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        design_system_reuse_mode="require_reuse",
        design_system_reuse_run_dir=source_store.paths.run_dir,
        analyzer=cast(Any, AsyncMock()),
        executor=cast(Any, AsyncMock()),
        renderer=cast(Any, AsyncMock()),
        validator=cast(Any, AsyncMock()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path / "target"),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    with pytest.raises(RuntimeError, match="not compatible"):
        await orchestrator.run(
            reference_bundle=ReferenceBundle(
                input_mode="image",
                stack="html_tailwind",
                user_text="Create this page",
                images=["data:image/png;base64,different"],
                videos=[],
            ),
            initial_file_state=None,
        )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_require_reuse_rejects_incompatible_run_dir(
    tmp_path: Path,
) -> None:
    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    source_store = ValidatedLoopArtifactStore(repo_root=tmp_path / "source")
    source_design_system = DesignSystemPreflight(
        title="Reusable design system",
        summary="Load from saved run.",
        typography=["Inter"],
    )
    source_json, source_html = _StaticDesignSystemRenderer().render(source_design_system)
    source_json_path, source_html_path = source_store.persist_design_system_artifacts(
        design_system_json=source_json,
        design_system_html=source_html,
    )
    source_store.persist_reference_bundle(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Original request",
            images=["data:image/png;base64,abc"],
            videos=[],
            reference_url="https://example.com/original",
            design_system_preflight=source_design_system.model_copy(
                update={
                    "json_artifact_path": source_json_path,
                    "html_artifact_path": source_html_path,
                }
            ),
        )
    )

    async def send_message(*args, **kwargs):
        return None

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        design_system_reuse_mode="require_reuse",
        design_system_reuse_run_dir=source_store.paths.run_dir,
        analyzer=cast(Any, AsyncMock()),
        executor=cast(Any, AsyncMock()),
        renderer=cast(Any, AsyncMock()),
        validator=cast(Any, AsyncMock()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path / "target"),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    with pytest.raises(RuntimeError, match="not compatible"):
        await orchestrator.run(
            reference_bundle=ReferenceBundle(
                input_mode="image",
                stack="html_tailwind",
                user_text="Create this page",
                images=["data:image/png;base64,abc"],
                videos=[],
                reference_url="https://example.com/different",
            ),
            initial_file_state=None,
        )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_repersist_existing_preflight_into_new_run(
    tmp_path: Path,
) -> None:
    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is not None
            assert reference_bundle.design_system_preflight.html_artifact_path.startswith(
                str(tmp_path)
            )
            assert "/new-run/" in reference_bundle.design_system_preflight.html_artifact_path
            return RequirementsSpec(summary="Repersist supplied design system")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path / "new-run")
    old_html_path = tmp_path / "old-run" / "design-system" / "design-system.html"
    old_json_path = tmp_path / "old-run" / "design-system" / "design-system.json"
    old_html_path.parent.mkdir(parents=True, exist_ok=True)
    old_html_path.write_text("<html>old</html>", encoding="utf-8")
    old_json_path.write_text("{}", encoding="utf-8")

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=artifact_store,
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
            design_system_preflight=DesignSystemPreflight(
                title="Supplied preflight",
                summary="Persist me again.",
                typography=["Inter"],
                json_artifact_path=str(old_json_path),
                html_artifact_path=str(old_html_path),
            ),
        ),
        initial_file_state=None,
    )

    assert result.saved_run_dir is not None
    persisted_reference = ValidatedLoopArtifactStore.load_reference_bundle(
        result.saved_run_dir
    )
    assert persisted_reference.design_system_preflight is not None
    assert persisted_reference.design_system_preflight.html_artifact_path.startswith(
        str(tmp_path / "new-run")
    )
    assert Path(persisted_reference.design_system_preflight.html_artifact_path).exists()


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_reuses_compatible_current_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []
    cached_design_system = DesignSystemPreflight(
        title="Cached design system",
        summary="Reuse current cache.",
        typography=["Inter"],
    )
    cached_reference_bundle = ReferenceBundle(
        input_mode="image",
        stack="html_tailwind",
        user_text="Cached request",
        images=["data:image/png;base64,abc"],
        videos=[],
        reference_url="https://example.com/reference",
        live_reference=LiveReferenceContext(
            url="https://example.com/reference",
            design_system=LiveReferenceDesignSystem(),
            renders=[],
        ),
    )

    monkeypatch.setattr(
        "loop.orchestrator.load_design_system_preflight_from_current_cache",
        lambda: cached_design_system,
    )
    monkeypatch.setattr(
        "loop.orchestrator.load_reference_bundle_from_current_cache",
        lambda: cached_reference_bundle,
    )

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is not None
            assert reference_bundle.design_system_preflight.title == "Cached design system"
            return _requirements_with_section_blueprint("Reuse current cache")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        design_system_reuse_mode="reuse_if_available",
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path / "target"),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
            reference_url="https://example.com/reference",
        ),
        initial_file_state=None,
    )

    assert any(
        msg[0] == "status"
        and msg[1]
        and "Reusing saved design-system preflight artifact" in msg[1]
        for msg in sent_messages
    )


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_regenerates_after_incompatible_current_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    monkeypatch.setattr(
        "loop.orchestrator.load_design_system_preflight_from_current_cache",
        lambda: DesignSystemPreflight(
            title="Cached design system",
            summary="Reuse current cache.",
            typography=["Inter"],
        ),
    )
    monkeypatch.setattr(
        "loop.orchestrator.load_reference_bundle_from_current_cache",
        lambda: ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Cached request",
            images=[],
            videos=[],
            reference_url="",
        ),
    )

    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(msg_type: str, value: str | None, variant_index: int, data=None, eventId=None) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            assert reference_bundle.design_system_preflight is not None
            assert reference_bundle.design_system_preflight.title == "Fresh design system"
            return _requirements_with_section_blueprint(
                "Regenerated after incompatible cache"
            )

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    class FakeDesignSystemBuilder:
        async def build(self, reference_bundle) -> DesignSystemPreflight:
            return DesignSystemPreflight(
                title="Fresh design system",
                summary="Generated after incompatible cache.",
                typography=["Inter"],
            )

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        design_system_reuse_mode="reuse_if_available",
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path / "target"),
        design_system_builder=cast(Any, FakeDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
            reference_url="https://example.com/reference",
        ),
        initial_file_state=None,
    )

    assert any(
        msg[0] == "status"
        and msg[1]
        and "Generating required design-system preflight artifact" in msg[1]
        for msg in sent_messages
    )


def test_validation_report_normalizes_model_friendly_values() -> None:
    from loop.contracts import ValidationReport

    report = ValidationReport.model_validate(
        {
            "verdict": "PASS",
            "overall_score": 98,
            "visual_fidelity_score": "97%",
            "behavior_fidelity_score": 0.96,
            "animation_fidelity_score": "95",
            "editability_score": 94,
            "summary": "Close match overall.",
            "section_results": [
                {
                    "name": "Hero",
                    "status": "COMPLETE",
                    "quality_score": "93%",
                    "summary": "Hero is nearly there.",
                }
            ],
            "issues": [
                {
                    "severity": "high",
                    "category": "visibility",
                    "title": "Hero card not visible enough",
                    "observed": "The hero content is partially transparent.",
                    "expected": "The hero content should remain fully readable.",
                    "fix_instructions": "Raise contrast and remove the faded resting state.",
                }
            ],
            "patch_instructions": ["Make the hero content fully visible."],
        }
    )

    assert report.verdict == "pass"
    assert report.overall_score == 0.98
    assert report.visual_fidelity_score == 0.97
    assert report.animation_fidelity_score == 0.95
    assert report.editability_score == 0.94
    assert report.section_results[0].status == "present"
    assert report.section_results[0].quality_score == 0.93
    assert report.issues[0].severity == "critical"
    assert report.issues[0].category == "styling"


def test_tighten_validation_report_downgrades_optimistic_scores_for_major_video_issues() -> None:
    from loop.contracts import ValidationIssue, ValidationReport
    from loop.validator import _tighten_validation_report

    tightened = _tighten_validation_report(
        ValidationReport(
            verdict="pass",
            overall_score=0.97,
            visual_fidelity_score=0.97,
            behavior_fidelity_score=0.96,
            animation_fidelity_score=0.97,
            editability_score=0.95,
            summary="Looks almost done.",
            issues=[
                ValidationIssue(
                    severity="major",
                    category="animation",
                    title="Hero motion mismatch",
                    observed="The hero appears statically.",
                    expected="The hero should animate in sequence.",
                    fix_instructions="Restore the entrance choreography.",
                )
            ],
            patch_instructions=["Fix the hero entrance animation."],
        ),
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Match this animated page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
    )

    assert tightened.verdict == "revise"
    assert tightened.overall_score <= 0.75
    assert tightened.animation_fidelity_score <= 0.75


def test_tighten_validation_report_caps_visual_scores_for_critical_styling_issues() -> None:
    from loop.contracts import ValidationIssue, ValidationReport
    from loop.validator import _tighten_validation_report

    tightened = _tighten_validation_report(
        ValidationReport(
            verdict="pass",
            overall_score=0.98,
            visual_fidelity_score=0.98,
            behavior_fidelity_score=0.97,
            animation_fidelity_score=0.97,
            editability_score=0.96,
            summary="Almost done.",
            issues=[
                ValidationIssue(
                    severity="critical",
                    category="styling",
                    title="Theme mismatch",
                    observed="The palette is visibly wrong.",
                    expected="The palette should match the reference.",
                    fix_instructions="Replace the colors with the reference palette.",
                )
            ],
            patch_instructions=["Correct the entire color system."],
        ),
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Match this screenshot",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
    )

    assert tightened.verdict == "revise"
    assert tightened.overall_score <= 0.55
    assert tightened.visual_fidelity_score <= 0.6


def test_enforce_section_coverage_marks_missing_required_sections() -> None:
    from loop.contracts import SectionRequirement, SectionValidationResult
    from loop.validator import _enforce_section_coverage

    report = _enforce_section_coverage(
        ValidationReport(
            verdict="pass",
            overall_score=0.97,
            visual_fidelity_score=0.96,
            behavior_fidelity_score=0.95,
            animation_fidelity_score=0.95,
            editability_score=0.94,
            summary="The existing sections look polished.",
            section_results=[
                SectionValidationResult(
                    name="Hero",
                    status="present",
                    quality_score=0.94,
                    summary="Hero is close.",
                )
            ],
        ),
        requirements=RequirementsSpec(
            section_requirements=[
                SectionRequirement(name="Hero", must_include=["headline"]),
                SectionRequirement(
                    name="Testimonials",
                    must_include=["quote cards"],
                    copy_items=["Real customer quotes"],
                ),
            ],
        ),
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Match this screenshot",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
    )

    assert report.verdict == "revise"
    assert report.overall_score <= 0.55
    assert report.visual_fidelity_score <= 0.72
    assert [result.name for result in report.section_results[:2]] == ["Hero", "Testimonials"]
    assert report.section_results[1].status == "missing"
    assert any("Required sections are missing" in issue.title for issue in report.issues)
    assert report.patch_instructions[0].startswith("Insert the missing `Testimonials` section")


def test_enforce_section_coverage_caps_partial_sections_and_preserves_order() -> None:
    from loop.contracts import SectionRequirement, SectionValidationResult
    from loop.validator import _enforce_section_coverage

    report = _enforce_section_coverage(
        ValidationReport(
            verdict="pass",
            overall_score=0.95,
            visual_fidelity_score=0.94,
            behavior_fidelity_score=0.93,
            animation_fidelity_score=0.92,
            editability_score=0.91,
            summary="The page is close.",
            section_results=[
                SectionValidationResult(
                    name="FAQ",
                    status="partial",
                    quality_score=0.96,
                    summary="FAQ exists but is missing disclosure details.",
                ),
                SectionValidationResult(
                    name="Hero",
                    status="present",
                    quality_score=0.93,
                    summary="Hero is close.",
                ),
            ],
        ),
        requirements=RequirementsSpec(
            section_requirements=[
                SectionRequirement(name="Hero", must_include=["headline"]),
                SectionRequirement(
                    name="FAQ",
                    must_include=["accordion rows"],
                    behaviors=["accordion opens on click"],
                ),
            ],
        ),
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Match this animated landing page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
    )

    assert report.verdict == "revise"
    assert report.overall_score <= 0.78
    assert report.animation_fidelity_score <= 0.82
    assert [result.name for result in report.section_results[:2]] == ["Hero", "FAQ"]
    assert report.section_results[1].status == "partial"
    assert report.section_results[1].quality_score <= 0.79
    assert any("partially implemented" in issue.title.lower() for issue in report.issues)
    assert report.patch_instructions[0].startswith("Finish the partially implemented `FAQ` section")


def test_enforce_section_coverage_recovers_false_missing_sections_from_dom_markers() -> None:
    from loop.contracts import SectionRequirement, SectionValidationResult, ValidationIssue
    from loop.validator import _enforce_section_coverage

    report = _enforce_section_coverage(
        ValidationReport(
            verdict="revise",
            overall_score=0.55,
            visual_fidelity_score=0.72,
            behavior_fidelity_score=0.72,
            animation_fidelity_score=0.72,
            editability_score=0.65,
            summary="Visual fidelity is excellent and all required sections are present.",
            section_results=[
                SectionValidationResult(
                    name="Hero",
                    status="present",
                    quality_score=0.93,
                    summary="Hero is close.",
                ),
                SectionValidationResult(
                    name="Quality Trust",
                    status="missing",
                    quality_score=0.0,
                    summary="The model failed to find this section.",
                ),
            ],
            issues=[
                ValidationIssue(
                    severity="critical",
                    category="structure",
                    title="Required sections are missing from the implementation",
                    observed="Missing sections: Quality Trust, Footer.",
                    expected="Every required section should be present.",
                    fix_instructions="Implement the missing sections before refining polish.",
                ),
                ValidationIssue(
                    severity="minor",
                    category="copy",
                    title="Feature copy still needs minor cleanup",
                    observed="One supporting bullet uses shortened wording.",
                    expected="The supporting bullet should match the reference wording.",
                    fix_instructions="Update the supporting bullet copy in `.features-grid` while keeping the existing layout intact.",
                ),
            ],
            patch_instructions=[
                "Insert the missing `Quality Trust` section after the existing `Hero` section.",
                "Insert the missing `Footer` section after the existing `Quality Trust` section.",
                "Update the supporting bullet copy in `.features-grid` while preserving the current spacing.",
            ],
        ),
        requirements=RequirementsSpec(
            section_requirements=[
                SectionRequirement(name="Hero", must_include=["headline"]),
                SectionRequirement(name="Quality Trust", must_include=["quality badges"]),
                SectionRequirement(name="Footer", must_include=["legal links"]),
            ],
        ),
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="react_tailwind",
            user_text="Match this landing page video",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        current_html="""
        <main>
          <section data-section-id="hero"></section>
          <section data-section-id={"quality-trust"}></section>
          <footer data-section-id='footer'></footer>
        </main>
        """,
    )

    assert report.verdict == "revise"
    assert report.overall_score >= 0.84
    assert report.visual_fidelity_score >= 0.86
    assert report.behavior_fidelity_score >= 0.86
    assert report.animation_fidelity_score >= 0.86
    assert report.editability_score >= 0.88
    assert [result.name for result in report.section_results[:3]] == [
        "Hero",
        "Quality Trust",
        "Footer",
    ]
    assert [result.status for result in report.section_results[:3]] == [
        "present",
        "present",
        "present",
    ]
    assert not any("Required sections are missing" in issue.title for issue in report.issues)
    assert report.patch_instructions == [
        "Update the supporting bullet copy in `.features-grid` while preserving the current spacing."
    ]
    assert "data-section-id" in report.summary


def test_tighten_validation_report_deprioritizes_imagery_in_feature_first_mode() -> None:
    from loop.contracts import ValidationIssue
    from loop.validator import _tighten_validation_report

    report = _tighten_validation_report(
        ValidationReport(
            verdict="revise",
            overall_score=0.55,
            visual_fidelity_score=0.55,
            behavior_fidelity_score=0.98,
            animation_fidelity_score=0.98,
            editability_score=0.98,
            summary="Images are still placeholders.",
            issues=[
                ValidationIssue(
                    severity="critical",
                    category="imagery",
                    title="Placeholder media remains",
                    observed="Several sections still use placeholder blocks instead of final images.",
                    expected="The final imagery should match the reference.",
                    fix_instructions="Replace the placeholder media blocks with final assets.",
                )
            ],
        ),
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="react_tailwind",
            user_text="I don't care about images, I only care about features and functionality",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
    )

    assert report.verdict == "pass"
    assert report.overall_score >= 0.98
    assert report.visual_fidelity_score <= 0.6
    assert report.behavior_fidelity_score >= 0.98
    assert report.animation_fidelity_score >= 0.98
    assert report.editability_score >= 0.98
    assert report.issues[0].category == "imagery"
    assert report.issues[0].severity == "minor"


def test_validator_enforces_live_design_system_usage_in_html() -> None:
    from loop.validator import _enforce_design_system_usage

    report = _enforce_design_system_usage(
        ValidationReport(
            verdict="pass",
            overall_score=0.97,
            visual_fidelity_score=0.96,
            behavior_fidelity_score=0.95,
            animation_fidelity_score=0.95,
            editability_score=0.94,
            summary="Looks close.",
        ),
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Match the live page",
            images=[],
            videos=[],
            reference_url="https://example.com/reference",
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(
                    typography=[
                        'body: font Suisseintl, Arial, sans-serif; size 14px; line-height 20px; weight 400; color rgb(15, 62, 23)',
                        'h1: font "Faire Octave", Arial, sans-serif; size 74px; line-height 78px; weight 300; color rgb(15, 62, 23)',
                    ],
                ),
            ),
        ),
        requirements=RequirementsSpec(
            design_tokens=DesignTokenSet(
                colors=[
                    "--color-text-primary: rgb(15, 62, 23)",
                    "--color-bg-main: rgb(255, 254, 252)",
                ],
                typography=[
                    "--font-body: 'Suisseintl', Arial, sans-serif",
                    "--font-heading: 'Faire Octave', Arial, sans-serif",
                ],
            ),
        ),
        current_html="<html><style>:root { --color-text-primary: rgb(15, 62, 23); }</style><body style='font-family: Inter;'>Hello</body></html>",
    )

    assert report.verdict == "revise"
    assert report.overall_score <= 0.55
    assert any("font-family names are missing" in issue.title.lower() for issue in report.issues)
    assert any("token declarations" in issue.title.lower() for issue in report.issues)
    assert any("var(--font-body)" in instruction for instruction in report.patch_instructions)


def test_validator_requires_real_token_declarations_not_just_var_usage() -> None:
    from loop.validator import _enforce_design_system_usage

    report = _enforce_design_system_usage(
        ValidationReport(
            verdict="pass",
            overall_score=0.95,
            visual_fidelity_score=0.95,
            behavior_fidelity_score=0.95,
            animation_fidelity_score=0.95,
            editability_score=0.95,
            summary="Looks close.",
        ),
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Match the live page",
            images=[],
            videos=[],
            reference_url="https://example.com/reference",
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(
                    typography=['body: font Suisseintl, Arial, sans-serif; size 14px; line-height 20px; weight 400; color rgb(15, 62, 23)'],
                ),
            ),
        ),
        requirements=RequirementsSpec(
            design_tokens=DesignTokenSet(
                typography=["--font-body: 'Suisseintl', Arial, sans-serif"],
            ),
        ),
        current_html="<html><body style='font-family: var(--font-body);'>Hello</body></html>",
    )

    assert any("token declarations" in issue.title.lower() for issue in report.issues)


def test_validator_only_requires_usage_for_extracted_tokens_present() -> None:
    from loop.validator import _enforce_design_system_usage

    report = _enforce_design_system_usage(
        ValidationReport(
            verdict="pass",
            overall_score=0.95,
            visual_fidelity_score=0.95,
            behavior_fidelity_score=0.95,
            animation_fidelity_score=0.95,
            editability_score=0.95,
            summary="Looks close.",
        ),
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Match the live page",
            images=[],
            videos=[],
            reference_url="https://example.com/reference",
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(
                    typography=['body: font Suisseintl, Arial, sans-serif; size 14px; line-height 20px; weight 400; color rgb(15, 62, 23)'],
                ),
            ),
        ),
        requirements=RequirementsSpec(
            design_tokens=DesignTokenSet(
                typography=["--font-body: 'Suisseintl', Arial, sans-serif"],
            ),
        ),
        current_html="<html><style>:root { --font-body: 'Suisseintl', Arial, sans-serif; }</style><body style='font-family: var(--font-body);'>Hello</body></html>",
    )

    assert not any("var(--font-heading)" in issue.observed for issue in report.issues)


@pytest.mark.asyncio
async def test_loop_validator_uses_compact_media_for_image_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from loop.contracts import RenderArtifact, RenderTimelineFrame
    from loop.validator import LoopValidator

    captured: dict[str, object] = {}

    async def fake_generate_structured_output(**kwargs):
        captured["parts"] = kwargs["parts"]
        return ValidationReport(
            verdict="pass",
            overall_score=0.99,
            visual_fidelity_score=0.99,
            behavior_fidelity_score=0.99,
            animation_fidelity_score=0.99,
            editability_score=0.99,
            summary="Looks good.",
        )

    monkeypatch.setattr("loop.validator.generate_structured_output", fake_generate_structured_output)
    monkeypatch.setattr(
        "loop.validator.data_url_to_part",
        lambda data_url: {"media": data_url},
    )

    validator = LoopValidator("key")
    await validator.validate(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Validate this page",
            images=[
                "data:image/png;base64,one",
                "data:image/png;base64,two",
                "data:image/png;base64,three",
            ],
            videos=[],
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(),
                renders=[
                    LiveReferenceRender(
                        label="viewport render",
                        data_url="data:image/png;base64,live-viewport",
                    ),
                    LiveReferenceRender(
                        label="full-page render",
                        data_url="data:image/png;base64,live-full",
                    ),
                ],
            ),
        ),
        requirements=RequirementsSpec(),
        render_artifact=RenderArtifact(
            viewport_screenshot_data_url="data:image/png;base64,candidate-viewport",
            full_page_screenshot_data_url="data:image/png;base64,candidate-full",
            settled_viewport_screenshot_data_url="data:image/png;base64,candidate-settled",
            settled_full_page_screenshot_data_url="data:image/png;base64,candidate-settled-full",
            timeline_frames=[
                RenderTimelineFrame(
                    label="frame 1",
                    elapsed_ms=200,
                    viewport_screenshot_data_url="data:image/png;base64,frame-1",
                )
            ],
        ),
        current_html="<html><body><main id='app-shell'>Current baseline</main></body></html>",
        iteration=1,
    )

    text_parts = [
        part["text"]
        for part in cast(list[object], captured["parts"])
        if isinstance(part, dict) and "text" in part
    ]
    media_texts = text_parts[1:]
    assert any(text == "Source image 1:" for text in media_texts)
    assert any(text == "Source image 2:" for text in media_texts)
    assert not any(text == "Source image 3:" for text in media_texts)
    assert any("viewport render" in text for text in media_texts)
    assert not any("full-page render" in text for text in media_texts)
    assert any(text == "Rendered candidate viewport screenshot:" for text in media_texts)
    assert any(text == "Rendered candidate full-page screenshot:" for text in media_texts)
    assert not any("settled viewport screenshot" in text for text in media_texts)
    assert not any("timeline checkpoint" in text for text in media_texts)


@pytest.mark.asyncio
async def test_loop_validator_caps_video_timeline_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from loop.contracts import RenderArtifact, RenderTimelineFrame
    from loop.validator import LoopValidator

    captured: dict[str, object] = {}

    async def fake_generate_structured_output(**kwargs):
        captured["parts"] = kwargs["parts"]
        return ValidationReport(
            verdict="pass",
            overall_score=0.99,
            visual_fidelity_score=0.99,
            behavior_fidelity_score=0.99,
            animation_fidelity_score=0.99,
            editability_score=0.99,
            summary="Looks good.",
        )

    monkeypatch.setattr("loop.validator.generate_structured_output", fake_generate_structured_output)
    monkeypatch.setattr(
        "loop.validator.data_url_to_part",
        lambda data_url: {"media": data_url},
    )

    validator = LoopValidator("key")
    await validator.validate(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Validate this animation",
            images=[],
            videos=["data:video/mp4;base64,primary", "data:video/mp4;base64,secondary"],
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(),
                renders=[
                    LiveReferenceRender(
                        label="viewport render",
                        data_url="data:image/png;base64,live-viewport",
                    ),
                    LiveReferenceRender(
                        label="full-page render",
                        data_url="data:image/png;base64,live-full",
                    ),
                ],
            ),
        ),
        requirements=RequirementsSpec(
            animation_requirements=["The hero should animate in three steps."],
        ),
        render_artifact=RenderArtifact(
            viewport_screenshot_data_url="data:image/png;base64,candidate-viewport",
            full_page_screenshot_data_url="data:image/png;base64,candidate-full",
            settled_viewport_screenshot_data_url="data:image/png;base64,candidate-settled",
            settled_full_page_screenshot_data_url="data:image/png;base64,candidate-settled-full",
            timeline_frames=[
                RenderTimelineFrame(
                    label=f"frame {index}",
                    elapsed_ms=index * 200,
                    viewport_screenshot_data_url=f"data:image/png;base64,frame-{index}",
                )
                for index in range(1, 7)
            ],
        ),
        current_html="<html><body><main id='app-shell'>Current baseline</main></body></html>",
        iteration=2,
    )

    text_parts = [
        part["text"]
        for part in cast(list[object], captured["parts"])
        if isinstance(part, dict) and "text" in part
    ]
    media_texts = text_parts[1:]
    assert any(text == "Source video 1:" for text in media_texts)
    assert not any(text == "Source video 2:" for text in media_texts)
    assert any("viewport render" in text for text in media_texts)
    assert not any("full-page render" in text for text in media_texts)
    assert any("settled viewport screenshot" in text for text in media_texts)
    assert not any(text == "Rendered candidate full-page screenshot:" for text in media_texts)
    assert not any("settled full-page screenshot" in text for text in media_texts)
    assert len(
        [text for text in media_texts if text.startswith("Rendered candidate timeline checkpoint")]
    ) == 4


@pytest.mark.asyncio
async def test_loop_validator_uses_narrower_media_on_delta_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from loop.contracts import RenderArtifact, ValidationIssue
    from loop.validator import LoopValidator

    captured_parts: list[list[object]] = []

    async def fake_generate_structured_output(**kwargs):
        captured_parts.append(cast(list[object], kwargs["parts"]))
        return ValidationReport(
            verdict="pass",
            overall_score=0.99,
            visual_fidelity_score=0.99,
            behavior_fidelity_score=0.99,
            animation_fidelity_score=0.99,
            editability_score=0.99,
            summary="Looks good.",
        )

    monkeypatch.setattr("loop.validator.generate_structured_output", fake_generate_structured_output)
    monkeypatch.setattr(
        "loop.validator.data_url_to_part",
        lambda data_url: {"media": data_url},
    )

    validator = LoopValidator("key")
    reference_bundle = ReferenceBundle(
        input_mode="image",
        stack="html_tailwind",
        user_text="Validate this page",
        images=["data:image/png;base64,one", "data:image/png;base64,two"],
        videos=[],
        live_reference=LiveReferenceContext(
            url="https://example.com/reference",
            design_system=LiveReferenceDesignSystem(),
            renders=[
                LiveReferenceRender(
                    label="viewport render",
                    data_url="data:image/png;base64,live-viewport",
                )
            ],
        ),
    )
    render_artifact = RenderArtifact(
        viewport_screenshot_data_url="data:image/png;base64,candidate-viewport",
        full_page_screenshot_data_url="data:image/png;base64,candidate-full",
    )

    await validator.validate(
        reference_bundle=reference_bundle,
        requirements=RequirementsSpec(),
        render_artifact=render_artifact,
        current_html="<html><body><main id='hero'>Current baseline</main></body></html>",
        iteration=1,
    )
    await validator.validate(
        reference_bundle=reference_bundle,
        requirements=RequirementsSpec(),
        render_artifact=render_artifact,
        current_html="<html><body><main id='hero'>Current baseline</main></body></html>",
        iteration=2,
        prior_validation=ValidationReport(
            verdict="revise",
            overall_score=0.8,
            visual_fidelity_score=0.8,
            behavior_fidelity_score=0.8,
            animation_fidelity_score=0.8,
            editability_score=0.95,
            summary="CTA copy still needs work.",
            issues=[
                ValidationIssue(
                    severity="major",
                    category="copy",
                    title="CTA copy mismatch",
                    observed="The CTA text is still generic.",
                    expected="The CTA should use the approved pricing language.",
                    fix_instructions="Update the CTA copy inside #hero without changing layout.",
                )
            ],
            patch_instructions=["Update the CTA copy inside #hero."],
        ),
    )

    iteration_one_texts = [
        part["text"]
        for part in captured_parts[0]
        if isinstance(part, dict) and "text" in part
    ][1:]
    iteration_two_texts = [
        part["text"]
        for part in captured_parts[1]
        if isinstance(part, dict) and "text" in part
    ][1:]

    assert "Source image 2:" in iteration_one_texts
    assert "Source image 2:" not in iteration_two_texts
    assert "Rendered candidate full-page screenshot:" in iteration_one_texts
    assert "Rendered candidate full-page screenshot:" not in iteration_two_texts


def test_loop_executor_defaults_to_gemini_3_1_pro() -> None:
    executor = LoopExecutor(
        send_message=AsyncMock(),
        openai_api_key=None,
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
    )

    assert executor.model == Llm.GEMINI_3_1_PRO_PREVIEW_HIGH


def test_validation_loop_orchestrator_allows_missing_openai_key_for_gemini_executor() -> None:
    async def send_message(*args, **kwargs):
        return None

    from loop.orchestrator import ValidationLoopOrchestrator

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key=None,
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
    )

    assert orchestrator.executor_model == Llm.GEMINI_3_1_PRO_PREVIEW_HIGH


@pytest.mark.asyncio
async def test_validation_loop_run_result_includes_model_metadata(tmp_path: Path) -> None:
    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    sent_messages: list[tuple[str, str | None, int, dict[str, object] | None]] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        sent_messages.append((msg_type, value, variant_index, data))

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            return RequirementsSpec(summary="Use model metadata")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            return ValidationReport(
                verdict="pass",
                overall_score=0.99,
                visual_fidelity_score=0.99,
                behavior_fidelity_score=0.99,
                animation_fidelity_score=0.99,
                editability_score=0.99,
                summary="Close match",
            )

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key=None,
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
        initial_file_state=None,
    )

    assert result.analyzer_model == Llm.GEMINI_3_1_PRO_PREVIEW_HIGH
    assert result.executor_model == Llm.GEMINI_3_1_PRO_PREVIEW_HIGH
    assert result.validator_model == Llm.GEMINI_3_1_PRO_PREVIEW_HIGH


def test_loop_executor_omits_raw_video_media_from_executor_prompts() -> None:
    executor = LoopExecutor(
        send_message=AsyncMock(),
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
    )

    prompt_messages = executor._build_prompt_messages(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Recreate this animated page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        requirements=RequirementsSpec(summary="Match the source animation"),
        file_state=None,
        validation_report=None,
        iteration=1,
    )

    user_message = cast(dict[str, Any], prompt_messages[1])
    content = cast(list[dict[str, Any]], user_message["content"])

    image_parts = [part for part in content if part.get("type") == "image_url"]
    text_parts = [part for part in content if part.get("type") == "text"]

    assert image_parts == []
    assert len(text_parts) == 1


def test_loop_executor_uses_current_file_snapshot_for_updates() -> None:
    executor = LoopExecutor(
        send_message=AsyncMock(),
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
    )

    prompt_messages = executor._build_prompt_messages(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Keep matching the reference video",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        requirements=RequirementsSpec(
            summary="Continue from the existing baseline",
            hard_constraints=["Keep the nav structure intact."],
        ),
        file_state={
            "path": "index.html",
            "content": "<html><body>baseline</body></html>",
        },
        validation_report=None,
        iteration=3,
    )

    user_message = cast(dict[str, Any], prompt_messages[1])
    content = cast(str, user_message["content"])

    assert "<current_file path=\"index.html\">" in content
    assert "<html><body>baseline</body></html>" in content
    assert "Apply the requested update." not in content


@pytest.mark.asyncio
async def test_loop_executor_disables_image_generation_for_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def run(self, model: object, prompt_messages: object) -> str:
            return "<html></html>"

    monkeypatch.setattr("loop.executor.Agent", FakeAgent)

    executor = LoopExecutor(
        send_message=AsyncMock(),
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
    )

    result = await executor.execute(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Recreate this animated page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        requirements=RequirementsSpec(summary="Match the source animation"),
        file_state=None,
        validation_report=None,
        iteration=1,
    )

    assert result == "<html></html>"
    assert captured["should_generate_images"] is False


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_passes_initial_file_state_to_analyzer(
    tmp_path: Path,
) -> None:
    captured_html: list[str | None] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        return None

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            captured_html.append(current_html)
            return RequirementsSpec(summary="Use the current implementation as baseline")

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            return "<html><body>ok</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            from loop.contracts import ValidationReport

            return ValidationReport(
                verdict="pass",
                overall_score=0.98,
                visual_fidelity_score=0.98,
                behavior_fidelity_score=0.98,
                animation_fidelity_score=0.98,
                editability_score=0.98,
                summary="Close match",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.contracts import ReferenceBundle
    from loop.orchestrator import ValidationLoopOrchestrator

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Tighten this page",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
        initial_file_state={
            "path": "index.html",
            "content": "<html><body>baseline</body></html>",
        },
    )

    assert captured_html == ["<html><body>baseline</body></html>"]


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_resumes_with_saved_requirements_and_validation(
    tmp_path: Path,
) -> None:
    analyzer_inputs: list[tuple[str | None, RequirementsSpec | None, ValidationReport | None]] = []
    executor_validation_inputs: list[object | None] = []
    validator_prior_inputs: list[ValidationReport | None] = []

    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        return None

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(
            self,
            reference_bundle,
            current_html=None,
            prior_requirements=None,
            prior_validation=None,
        ):
            analyzer_inputs.append(
                (current_html, prior_requirements, prior_validation)
            )
            return _requirements_with_section_blueprint(
                "Refined supervisor requirements for the resumed block"
            )

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def execute(self, **kwargs):
            executor_validation_inputs.append(kwargs.get("validation_report"))
            return "<html><body>resumed</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def validate(self, **kwargs):
            from loop.contracts import ValidationReport

            validator_prior_inputs.append(kwargs.get("prior_validation"))

            return ValidationReport(
                verdict="pass",
                overall_score=0.98,
                visual_fidelity_score=0.98,
                behavior_fidelity_score=0.98,
                animation_fidelity_score=0.98,
                editability_score=0.98,
                summary="Close match",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.contracts import LoopResumeState, ReferenceBundle
    from loop.orchestrator import ValidationLoopOrchestrator

    prior_validation = ValidationReport(
        verdict="revise",
        overall_score=0.82,
        visual_fidelity_score=0.84,
        behavior_fidelity_score=0.79,
        animation_fidelity_score=0.72,
        editability_score=0.95,
        summary="Animation timing still needs work.",
        patch_instructions=["Tighten the opening sequence timing."],
    )
    resume_state = LoopResumeState(
        requirements=RequirementsSpec(summary="Persisted supervisor requirements"),
        latest_validation=prior_validation,
        completed_iterations=10,
        stop_reason="max_iterations",
    )

    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=1,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, FakeValidator()),
        artifact_store=ValidatedLoopArtifactStore(repo_root=tmp_path),
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Continue matching this video exactly",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        initial_file_state={
            "path": "index.html",
            "content": "<html><body>baseline</body></html>",
        },
        resume_state=resume_state,
    )

    assert result.stop_reason == "pass"
    assert analyzer_inputs == [
        (
            "<html><body>baseline</body></html>",
            resume_state.requirements,
            prior_validation,
        )
    ]
    assert executor_validation_inputs == [prior_validation]
    assert validator_prior_inputs == [prior_validation]


@pytest.mark.asyncio
async def test_validation_loop_orchestrator_returns_best_so_far_checkpoint(
    tmp_path: Path,
) -> None:
    async def send_message(
        msg_type: str,
        value: str | None,
        variant_index: int,
        data=None,
        eventId=None,
    ) -> None:
        return None

    class FakeAnalyzer:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        async def analyze(self, reference_bundle, current_html=None):
            return _requirements_with_section_blueprint(
                "Keep improving the landing page"
            )

    class FakeExecutor:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, **kwargs):
            self.calls += 1
            return f"<html><body>iteration-{self.calls}</body></html>"

    class FakeRenderer:
        async def render_html(self, html, viewport, interaction_checkpoints=None):
            from loop.contracts import RenderArtifact

            return RenderArtifact(
                viewport_screenshot_data_url="data:image/png;base64,abc",
                viewport=viewport,
            )

    class FakeValidator:
        model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

        def __init__(self) -> None:
            self.calls = 0
            self.prior_inputs: list[ValidationReport | None] = []

        async def validate(self, **kwargs):
            self.calls += 1
            self.prior_inputs.append(kwargs.get("prior_validation"))
            if self.calls == 1:
                return ValidationReport(
                    verdict="revise",
                    overall_score=0.96,
                    visual_fidelity_score=0.96,
                    behavior_fidelity_score=0.99,
                    animation_fidelity_score=0.99,
                    editability_score=0.97,
                    summary="Almost there.",
                )
            return ValidationReport(
                verdict="revise",
                overall_score=0.55,
                visual_fidelity_score=0.60,
                behavior_fidelity_score=0.65,
                animation_fidelity_score=0.50,
                editability_score=0.95,
                summary="Regression.",
            )

    from loop.artifacts import ValidatedLoopArtifactStore
    from loop.orchestrator import ValidationLoopOrchestrator

    artifact_store = ValidatedLoopArtifactStore(repo_root=tmp_path)
    validator = FakeValidator()
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key="key",
        openai_base_url=None,
        anthropic_api_key=None,
        gemini_api_key="key",
        should_generate_images=True,
        option_codes=[],
        max_iterations=2,
        analyzer=cast(Any, FakeAnalyzer()),
        executor=cast(Any, FakeExecutor()),
        renderer=cast(Any, FakeRenderer()),
        validator=cast(Any, validator),
        artifact_store=artifact_store,
        design_system_builder=cast(Any, _StaticDesignSystemBuilder()),
        design_system_renderer=cast(Any, _StaticDesignSystemRenderer()),
    )

    result = await orchestrator.run(
        reference_bundle=ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Continue matching this video",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        initial_file_state=None,
    )

    assert result.stop_reason == "max_iterations"
    assert result.code == "<html><body>iteration-1</body></html>"
    assert result.saved_code_path == artifact_store.paths.best_file_path
    assert (
        Path(artifact_store.paths.best_file_path).read_text(encoding="utf-8")
        == "<html><body>iteration-1</body></html>"
    )
    assert validator.prior_inputs[0] is None
    assert validator.prior_inputs[1] is not None
    assert validator.prior_inputs[1].overall_score == 0.96

    resume_state = artifact_store.load_resume_state(artifact_store.paths.run_dir)
    assert resume_state.best_file_state == {
        "path": "index.html",
        "content": "<html><body>iteration-1</body></html>",
    }
    assert resume_state.latest_validation is not None
    assert resume_state.latest_validation.overall_score == 0.96
