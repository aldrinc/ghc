from loop.contracts import (
    ReferenceBundle,
    RequirementsSpec,
    SectionRequirement,
    ValidationReport,
)
from loop.analyzer_prompt import build_analyzer_prompt
from loop.executor_prompt import build_executor_create_prompt
from loop.validator_prompt import build_validator_prompt
from loop.prompts import compact_requirements_for_prompt, summarize_html_landmarks


def test_build_analysis_prompt_requests_executor_ready_structure() -> None:
    prompt = build_analyzer_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this marketing page",
            images=["data:image/png;base64,abc"],
            videos=[],
        )
    )

    assert "Populate `hard_constraints`" in prompt
    assert "Populate `preserve_requirements`" in prompt
    assert "Populate `section_requirements` top-to-bottom" in prompt
    assert "Populate `design_tokens`" in prompt
    assert "Populate `execution_plan`" in prompt
    assert "put that ambiguity in `known_unknowns`" in prompt
    assert "Frontend developer operating mode" in prompt


def test_build_execution_create_text_calls_out_blueprint_fields() -> None:
    prompt = build_executor_create_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this marketing page",
            images=[],
            videos=[],
        ),
        RequirementsSpec(
            hard_constraints=["Preserve the hero-to-feature section order."],
            section_requirements=[
                SectionRequirement(
                    name="Hero",
                    layout="Two-column hero with headline and mockup.",
                )
            ],
            execution_plan=[
                "Build the hero shell first.",
                "Add the feature cards second.",
            ],
        ),
        image_generation_enabled=True,
    )

    assert "Satisfy `hard_constraints` before lower-priority refinements." in prompt
    assert "Preserve anything covered by `preserve_requirements`" in prompt
    assert "Use `section_requirements` and `execution_plan` as the implementation blueprint." in prompt
    assert "full end state described by the requirements" in prompt
    assert "Frontend developer operating mode" in prompt


def test_build_analysis_prompt_uses_current_html_as_working_baseline() -> None:
    prompt = build_analyzer_prompt(
        ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Match this animated landing page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        "<html><body><section>Current baseline</section></body></html>",
    )

    assert "<current_html>" in prompt
    assert "working baseline" in prompt
    assert "<current_html_landmarks>" in prompt


def test_build_analysis_prompt_includes_saved_context_blocks_on_resume() -> None:
    prompt = build_analyzer_prompt(
        ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Continue matching this animated page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        "<html><body><main id='app-shell'>Current baseline</main></body></html>",
        RequirementsSpec(summary="Persisted requirements"),
        ValidationReport(
            verdict="revise",
            overall_score=0.72,
            visual_fidelity_score=0.74,
            behavior_fidelity_score=0.7,
            animation_fidelity_score=0.66,
            editability_score=0.92,
            summary="Prior block stalled on hero timing.",
            patch_instructions=["Tighten the hero timing."],
        ),
    )

    assert "<prior_requirements>" in prompt
    assert "<prior_validation>" in prompt
    assert "delta-aware requirements spec" in prompt
    assert "full meaningful sequence of the reference" in prompt


def test_build_validator_prompt_includes_frontend_developer_guidance() -> None:
    prompt = build_validator_prompt(
        ReferenceBundle(
            input_mode="video",
            stack="html_tailwind",
            user_text="Validate this animated landing page",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        RequirementsSpec(summary="Match the motion-heavy landing page"),
        "<html><body>Current baseline</body></html>",
        2,
    )

    assert "Frontend developer operating mode" in prompt
    assert "responsive behavior" in prompt
    assert "<current_html_landmarks>" in prompt
    assert "Prefer the settled render" in prompt
    assert "selector" in prompt
    assert "timeline checkpoint renders" in prompt


def test_compact_requirements_for_prompt_truncates_large_fields() -> None:
    large_requirements = RequirementsSpec(
        summary="A" * 2000,
        hard_constraints=["B" * 800 for _ in range(20)],
        preserve_requirements=["P" * 800 for _ in range(20)],
        section_requirements=[
            SectionRequirement(
                name="Hero",
                layout="C" * 800,
                must_include=["D" * 500 for _ in range(10)],
            )
            for _ in range(12)
        ],
        execution_plan=["E" * 800 for _ in range(20)],
    )

    compact = compact_requirements_for_prompt(large_requirements)

    assert len(compact.summary) < len(large_requirements.summary)
    assert len(compact.hard_constraints) == 10
    assert len(compact.preserve_requirements) == 10
    assert len(compact.section_requirements) == 8
    assert len(compact.section_requirements[0].must_include) == 6
    assert compact.execution_plan[0].endswith("[truncated for prompt]")


def test_summarize_html_landmarks_extracts_selectors_and_text() -> None:
    summary = summarize_html_landmarks(
        """
        <main id="app-shell">
          <section class="hero section" data-block="hero">
            <h1>Fewer clicks. More care.</h1>
            <button class="cta-primary">Request a Demo</button>
          </section>
        </main>
        """
    )

    assert "#app-shell" in summary
    assert ".hero.section" in summary
    assert "[data-block]" in summary
    assert 'text="Fewer clicks. More care."' in summary
