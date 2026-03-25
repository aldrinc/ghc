from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm import Llm
from loop.contracts import (
    LoopRunResult,
    ReferenceBundle,
    RequirementsSpec,
    ValidationReport,
)
from loop.executor import LoopExecutor
from routes.generate_code import (
    CodeGenerationMiddleware,
    ExtractedParams,
    PipelineContext,
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
            self.executor_model = Llm.CLAUDE_OPUS_4_6

        async def run(
            self,
            *,
            reference_bundle,
            initial_file_state,
            resume_state=None,
        ) -> LoopRunResult:
            assert reference_bundle.input_mode == "image"
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
        max_validation_iterations=2,
    )

    middleware = CodeGenerationMiddleware()
    next_called = False

    async def next_func() -> None:
        nonlocal next_called
        next_called = True

    await middleware.process(context, next_func)

    assert context.variant_models == [Llm.CLAUDE_OPUS_4_6]
    assert context.completions == ["<html><body>validated</body></html>"]
    assert ("setCode", "<html><body>validated</body></html>", 0) in sent_messages
    assert ("variantComplete", "Validated loop generation complete", 0) in sent_messages
    assert next_called is True


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
            self.executor_model = Llm.CLAUDE_OPUS_4_6

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
            self.executor_model = Llm.CLAUDE_OPUS_4_6

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
            self.executor_model = Llm.CLAUDE_OPUS_4_6

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
        model = Llm.CLAUDE_OPUS_4_6

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
        openai_api_key=None,
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
                animation_requirements=[
                    "Hero card and chart should animate into place during the opening sequence"
                ],
            )

    class FakeExecutor:
        model = Llm.CLAUDE_OPUS_4_6

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
        openai_api_key=None,
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


def test_loop_executor_omits_raw_video_media_from_executor_prompts() -> None:
    executor = LoopExecutor(
        send_message=AsyncMock(),
        openai_api_key=None,
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
        openai_api_key=None,
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
        openai_api_key=None,
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
        model = Llm.CLAUDE_OPUS_4_6

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
            return RequirementsSpec(
                summary="Refined supervisor requirements for the resumed block"
            )

    class FakeExecutor:
        model = Llm.CLAUDE_OPUS_4_6

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
            return RequirementsSpec(summary="Keep improving the landing page")

    class FakeExecutor:
        model = Llm.CLAUDE_OPUS_4_6

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
            self.calls += 1
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
    orchestrator = ValidationLoopOrchestrator(
        send_message=send_message,
        openai_api_key=None,
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

    resume_state = artifact_store.load_resume_state(artifact_store.paths.run_dir)
    assert resume_state.best_file_state == {
        "path": "index.html",
        "content": "<html><body>iteration-1</body></html>",
    }
    assert resume_state.latest_validation is not None
    assert resume_state.latest_validation.overall_score == 0.96
