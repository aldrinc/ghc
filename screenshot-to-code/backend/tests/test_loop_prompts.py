from loop.contracts import (
    BlueprintValidationIssue,
    BlueprintValidationReport,
    DesignSystemPreflight,
    DesignTokenSet,
    LiveReferenceContext,
    LiveReferenceDesignSystem,
    LiveReferenceRender,
    ReferenceBundle,
    RequirementsSpec,
    SectionRequirement,
    SectionValidationResult,
    ValidationReport,
)
from loop.analyzer_prompt import build_analyzer_prompt
from loop.blueprint_validator_prompt import build_blueprint_validator_prompt
from loop.execution_blocks import ExecutionBlock
from loop.executor_prompt import (
    build_executor_create_prompt,
    build_executor_revision_prompt,
    build_executor_update_prompt,
)
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
    assert "Populate `page_outline`" in prompt
    assert "Populate `closing_sections`" in prompt
    assert "Set `footer_present` explicitly" in prompt
    assert "Populate `coverage_notes`" in prompt
    assert "Populate `section_requirements` exhaustively, top-to-bottom" in prompt
    assert "do not let later-page sections live only in freeform planning text" in prompt
    assert "Treat thin but visually distinct bands" in prompt
    assert "If a narrow section sits between two larger blocks" in prompt
    assert "mentally rescan the reference from top to bottom" in prompt
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
    assert "data-section-id" in prompt
    assert "full end state described by the requirements" in prompt
    assert "Frontend developer operating mode" in prompt


def test_build_execution_create_prompt_requires_live_design_system_usage() -> None:
    prompt = build_executor_create_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this marketing page",
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
            design_system_preflight=DesignSystemPreflight(
                title="Marketing design system",
                summary="Use the visible design language directly.",
                philosophy=["Warm editorial typography with restrained color."],
                typography=[
                    "Primary typography uses 'Suisseintl' for body and 'Faire Octave' for display headings."
                ],
                section_typography=[
                    "Hero H1: 'Faire Octave', 74px, 300, 78px line-height, -0.4px letter-spacing."
                ],
                section_sizing=[
                    "Hero section uses oversized top/bottom padding and a two-column split with balanced panel heights."
                ],
                motion_components=[
                    "Announcement banner under the header moves horizontally in a continuous loop."
                ],
            ),
        ),
        RequirementsSpec(
            design_tokens=DesignTokenSet(
                colors=["--color-text-primary: rgb(15, 62, 23)"],
                typography=[
                    "--font-body: 'Suisseintl', Arial, sans-serif",
                    "--font-heading: 'Faire Octave', Arial, sans-serif",
                ],
            ),
        ),
        image_generation_enabled=True,
    )

    assert "Live design-system enforcement:" in prompt
    assert "Suisseintl" in prompt
    assert "Faire Octave" in prompt
    assert "var(--font-body)" in prompt
    assert "do not replace the extracted names" in prompt.lower()
    assert "<design_system_preflight>" in prompt
    assert "Announcement banner under the header" in prompt
    assert "Hero H1" in prompt
    assert "Hero section uses oversized top/bottom padding" in prompt


def test_build_execution_create_prompt_scopes_requirements_to_current_block() -> None:
    prompt = build_executor_create_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this page",
            images=[],
            videos=[],
        ),
        RequirementsSpec(
            hard_constraints=["Keep the centralized theme intact."],
            design_tokens=DesignTokenSet(
                colors=["--color-brand: rgb(0, 68, 255)"],
                typography=["--font-body: 'Satoshi', Arial, sans-serif"],
            ),
            section_requirements=[
                SectionRequirement(name="Header", copy_items=["Header copy"]),
                SectionRequirement(name="Footer", copy_items=["Footer copy"]),
            ],
            copy_requirements=[
                "Header should mention the primary navigation.",
                "Footer should mention legal links.",
            ],
            execution_plan=[
                "Build the global theme shell first.",
                "Implement the Header section.",
                "Implement the Footer section.",
            ],
        ),
        image_generation_enabled=False,
        execution_block=ExecutionBlock(
            title="Header block",
            objective="Build the header only.",
            section_names=["Header"],
            preserve_section_names=["Theme"],
            include_media=False,
        ),
    )

    assert "Header copy" in prompt
    assert "Footer copy" not in prompt
    assert "Build the global theme shell first." in prompt
    assert "Implement the Header section." in prompt
    assert "Implement the Footer section." not in prompt
    assert "Preserve these already-completed sections" in prompt


def test_build_execution_update_prompt_scopes_requirements_to_current_block() -> None:
    prompt = build_executor_update_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Update this page",
            images=[],
            videos=[],
        ),
        RequirementsSpec(
            section_requirements=[
                SectionRequirement(name="Hero", copy_items=["Hero copy"]),
                SectionRequirement(name="FAQ", copy_items=["FAQ copy"]),
            ],
            asset_requirements=[
                "Hero needs a product visual.",
                "FAQ needs disclosure icons.",
            ],
        ),
        iteration=2,
        execution_block=ExecutionBlock(
            title="FAQ block",
            objective="Update the FAQ section.",
            section_names=["FAQ"],
            preserve_section_names=["Hero"],
            include_media=False,
        ),
    )

    assert "FAQ copy" in prompt
    assert "Hero copy" not in prompt
    assert "FAQ needs disclosure icons." in prompt
    assert "Hero needs a product visual." not in prompt


def test_build_execution_revision_prompt_scopes_requirements_to_current_block() -> None:
    prompt = build_executor_revision_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Revise this page",
            images=[],
            videos=[],
        ),
        RequirementsSpec(
            section_requirements=[
                SectionRequirement(name="Stats", copy_items=["Stats copy"]),
                SectionRequirement(name="Testimonials", copy_items=["Testimonials copy"]),
            ],
            styling_requirements=[
                "Stats should use the blue highlight treatment.",
                "Testimonials should remain neutral.",
            ],
            execution_plan=[
                "Preserve the global theme shell.",
                "Refine the Stats section.",
                "Refine the Testimonials section.",
            ],
        ),
        ValidationReport(
            verdict="revise",
            overall_score=0.7,
            visual_fidelity_score=0.7,
            behavior_fidelity_score=0.7,
            animation_fidelity_score=0.7,
            editability_score=0.9,
            summary="Stats need refinement.",
            patch_instructions=["Refine the Stats section."],
        ),
        iteration=2,
        execution_block=ExecutionBlock(
            title="Stats block",
            objective="Refine stats only.",
            section_names=["Stats"],
            preserve_section_names=["Header", "Hero"],
            include_media=False,
        ),
    )

    assert "Stats copy" in prompt
    assert "Testimonials copy" not in prompt
    assert "Refine the Stats section." in prompt
    assert "Refine the Testimonials section." not in prompt


def test_section_models_derive_canonical_section_ids() -> None:
    requirement = SectionRequirement(name="Quality Trust")
    result = SectionValidationResult(
        name="Stats Grid",
        status="present",
        quality_score=0.92,
    )

    assert requirement.section_id == "quality-trust"
    assert result.section_id == "stats-grid"


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


def test_build_analysis_prompt_includes_prior_blueprint_validation_block() -> None:
    prompt = build_analyzer_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Repair this landing page blueprint",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
        None,
        RequirementsSpec(summary="Prior requirements"),
        None,
        BlueprintValidationReport(
            verdict="revise",
            overall_score=0.45,
            coverage_score=0.3,
            consistency_score=0.5,
            execution_readiness_score=0.35,
            summary="Footer coverage is missing.",
            issues=[
                BlueprintValidationIssue(
                    severity="critical",
                    category="coverage",
                    title="Missing footer coverage",
                    detail="The page ends with a footer that is not in the canonical section list.",
                    affected_fields=["closing_sections", "section_requirements"],
                    fix_instructions="Add the footer to the closing sections and canonical section list.",
                )
            ],
            repair_instructions=[
                "Add the footer to `closing_sections` and `section_requirements`."
            ],
        ),
    )

    assert "<prior_blueprint_validation>" in prompt
    assert "Execution will not start until blueprint QA passes" in prompt
    assert "Repair the missing or contradictory blueprint fields first" in prompt


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
    assert "Return a `section_results` entry for every item in `section_requirements`" in prompt
    assert "Do not return PASS when any required section is `missing` or `partial`" in prompt


def test_build_blueprint_validator_prompt_rejects_missing_lower_page_coverage() -> None:
    prompt = build_blueprint_validator_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Validate the page blueprint",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
        RequirementsSpec(
            page_outline=["Header", "Hero", "Features"],
            closing_sections=["Features"],
            footer_present=True,
            section_requirements=[SectionRequirement(name="Hero")],
            execution_plan=["Build the hero first.", "Build the FAQ and footer last."],
        ),
    )

    assert "Reject blueprints that stop at the hero" in prompt
    assert "footer or final page state is omitted when visible" in prompt
    assert "without representing those same scenes in `section_requirements`" in prompt
    assert "the closing state is represented" in prompt


def test_build_validator_prompt_disallows_pass_when_live_design_system_is_ignored() -> None:
    prompt = build_validator_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Validate this page",
            images=[],
            videos=[],
            reference_url="https://example.com/reference",
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(
                    typography=[
                        'body: font Suisseintl, Arial, sans-serif; size 14px; line-height 20px; weight 400; color rgb(15, 62, 23)',
                    ],
                ),
            ),
            design_system_preflight=DesignSystemPreflight(
                title="Validation design system",
                summary="Use this before approving code.",
                typography=["Body uses 'Suisseintl'."],
                section_typography=["FAQ questions use 'Satoshi' at 20px / 700."],
                section_sizing=[
                    "FAQ section cards share a consistent width and vertical padding rhythm."
                ],
                motion_components=["Banner below header scrolls continuously left to right."],
            ),
        ),
        RequirementsSpec(
            design_tokens=DesignTokenSet(
                colors=["--color-text-primary: rgb(15, 62, 23)"],
                typography=["--font-body: 'Suisseintl', Arial, sans-serif"],
            ),
        ),
        "<html><body>Current baseline</body></html>",
        1,
    )

    assert "Live design-system enforcement:" in prompt
    assert "do not return PASS" in prompt
    assert "omits centralized theme tokens" in prompt
    assert "<design_system_preflight>" in prompt


def test_build_validator_prompt_uses_compact_requirements_and_truncated_html() -> None:
    long_html = "<main id='app-shell'>" + ("A" * 25_000) + "</main>"
    prompt = build_validator_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Validate this page",
            images=[],
            videos=[],
        ),
        RequirementsSpec(
            summary="Validate the shell",
            hard_constraints=["Keep the page shell intact."],
            behavior_requirements=["The accordion should open when clicked."],
            execution_plan=["This bulky execution-plan item should not be present."],
            section_requirements=[
                SectionRequirement(
                    name="Hero",
                    purpose="Lead with the headline.",
                    copy_items=["Hero copy"],
                )
            ],
        ),
        long_html,
        3,
    )

    assert "This bulky execution-plan item should not be present." not in prompt
    assert "The accordion should open when clicked." in prompt
    assert "...[truncated current HTML context]..." in prompt
    assert "current HTML block may be truncated" in prompt


def test_build_validator_prompt_includes_prior_validation_delta_block() -> None:
    prompt = build_validator_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Validate this page",
            images=[],
            videos=[],
        ),
        RequirementsSpec(summary="Validate the shell"),
        "<html><body><main id='app-shell'>Current baseline</main></body></html>",
        2,
        ValidationReport(
            verdict="revise",
            overall_score=0.82,
            visual_fidelity_score=0.8,
            behavior_fidelity_score=0.85,
            animation_fidelity_score=0.8,
            editability_score=0.95,
            summary="Hero spacing is still off.",
            section_results=[
                SectionValidationResult(
                    name="Hero",
                    status="partial",
                    quality_score=0.76,
                    summary="Hero exists but spacing is still off.",
                )
            ],
            patch_instructions=["Adjust the hero spacing around #app-shell."],
        ),
    )

    assert "<prior_validation>" in prompt
    assert "Hero spacing is still off." in prompt
    assert "main delta checklist" in prompt
    assert "Hero exists but spacing is still off." in prompt


def test_build_validator_prompt_includes_feature_first_guidance_when_requested() -> None:
    prompt = build_validator_prompt(
        ReferenceBundle(
            input_mode="video",
            stack="react_tailwind",
            user_text="I don't care about images, I only care about features and functionality",
            images=[],
            videos=["data:video/mp4;base64,abc"],
        ),
        RequirementsSpec(summary="Validate interactions first"),
        "<html><body>Current baseline</body></html>",
        1,
    )

    assert "Feature/functionality-first validation mode:" in prompt
    assert "do not keep the verdict at REVISE solely because imagery differs" in prompt


def test_design_system_preflight_summary_includes_section_typography_and_motion_components() -> None:
    from loop.prompts import summarize_design_system_preflight_for_prompt

    summary = summarize_design_system_preflight_for_prompt(
        DesignSystemPreflight(
            title="Motion-heavy system",
            section_typography=[
                "Header nav: 'Satoshi', 14px, 700, uppercase, tracking 0.08em."
            ],
            section_sizing=[
                "Announcement section uses compressed vertical padding and full-width container sizing."
            ],
            motion_components=[
                "Moving banner directly under the header slides horizontally in a continuous loop."
            ],
        )
    )

    assert "section_typography" in summary
    assert "section_sizing" in summary
    assert "motion_components" in summary
    assert "Moving banner directly under the header" in summary


def test_build_analysis_prompt_includes_live_browser_context() -> None:
    prompt = build_analyzer_prompt(
        ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Create this marketing page",
            images=[],
            videos=[],
            reference_url="https://example.com/reference",
            live_reference=LiveReferenceContext(
                url="https://example.com/reference",
                design_system=LiveReferenceDesignSystem(
                    page_title="Example Marketing Page",
                    typography=["h1: font Inter; size 56px; weight 700"],
                    colors=["text rgb(17, 24, 39) used on ~12 elements"],
                    spacing=["gap 24px on ~6 elements"],
                    layout=["container max-width 1200px on ~4 layout blocks"],
                    components=["button: background rgb(37, 99, 235); radius 9999px"],
                ),
                renders=[
                    LiveReferenceRender(
                        label="live viewport render",
                        data_url="data:image/png;base64,abc",
                    )
                ],
            ),
        )
    )

    assert "<live_reference>" in prompt
    assert "Example Marketing Page" in prompt
    assert "live viewport render" in prompt


def test_compact_requirements_for_prompt_truncates_large_fields() -> None:
    large_requirements = RequirementsSpec(
        summary="A" * 2000,
        page_outline=["Outline " + ("O" * 200) for _ in range(20)],
        closing_sections=["Closing " + ("C" * 200) for _ in range(10)],
        footer_present=True,
        footer_description="F" * 500,
        coverage_notes=["N" * 400 for _ in range(10)],
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
    assert len(compact.page_outline) == 10
    assert len(compact.closing_sections) == 5
    assert compact.footer_present is True
    assert compact.footer_description.endswith("[truncated for prompt]")
    assert len(compact.coverage_notes) == 6
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
    assert '[data-block="hero"]' in summary
    assert 'text="Fewer clicks. More care."' in summary
