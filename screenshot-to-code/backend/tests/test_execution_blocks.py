from loop.contracts import (
    ReferenceBundle,
    RequirementsSpec,
    SectionRequirement,
    SectionValidationResult,
    ValidationReport,
)
from loop.execution_blocks import (
    ExecutionBlock,
    plan_execution_blocks,
    split_execution_block,
)


def _requirements_with_sections(count: int) -> RequirementsSpec:
    return RequirementsSpec(
        summary="Build the page",
        section_requirements=[
            SectionRequirement(name=f"Section {index}") for index in range(1, count + 1)
        ],
        behavior_requirements=["Hover interactions must work."],
    )


def test_plan_execution_blocks_chunks_large_initial_build() -> None:
    requirements = _requirements_with_sections(7)
    reference_bundle = ReferenceBundle(
        input_mode="text",
        stack="html_tailwind",
        user_text="Create the full page.",
        reference_url="https://example.com",
        images=[],
        videos=[],
    )

    blocks = plan_execution_blocks(
        reference_bundle=reference_bundle,
        requirements=requirements,
        file_state=None,
        validation_report=None,
    )

    assert len(blocks) >= 3
    assert blocks[0].include_media is True
    assert all(block.include_media is False for block in blocks[1:])
    assert blocks[0].section_names == ["Section 1", "Section 2", "Section 3"]
    assert blocks[1].preserve_section_names == ["Section 1", "Section 2", "Section 3"]


def test_plan_execution_blocks_returns_single_update_block_for_existing_html() -> None:
    requirements = _requirements_with_sections(4)
    validation_report = ValidationReport(
        verdict="revise",
        overall_score=0.75,
        visual_fidelity_score=0.8,
        behavior_fidelity_score=0.7,
        animation_fidelity_score=0.7,
        editability_score=0.9,
        summary="Hero needs refinement.",
        patch_instructions=["Tighten the Hero section spacing."],
    )
    reference_bundle = ReferenceBundle(
        input_mode="image",
        stack="html_tailwind",
        user_text="Revise the page.",
        images=["data:image/png;base64,abc"],
        videos=[],
    )

    blocks = plan_execution_blocks(
        reference_bundle=reference_bundle,
        requirements=requirements,
        file_state={"path": "index.html", "content": "<html></html>"},
        validation_report=validation_report,
    )

    assert len(blocks) == 1
    assert blocks[0].include_media is False


def test_plan_execution_blocks_prioritizes_missing_and_partial_sections() -> None:
    requirements = _requirements_with_sections(4)
    validation_report = ValidationReport(
        verdict="revise",
        overall_score=0.62,
        visual_fidelity_score=0.68,
        behavior_fidelity_score=0.66,
        animation_fidelity_score=0.7,
        editability_score=0.8,
        summary="Later sections are incomplete.",
        section_results=[
            SectionValidationResult(name="Section 1", status="present", quality_score=0.9),
            SectionValidationResult(name="Section 2", status="missing", quality_score=0.0),
            SectionValidationResult(name="Section 3", status="partial", quality_score=0.74),
            SectionValidationResult(name="Section 4", status="present", quality_score=0.88),
        ],
    )
    reference_bundle = ReferenceBundle(
        input_mode="image",
        stack="html_tailwind",
        user_text="Revise the page.",
        images=["data:image/png;base64,abc"],
        videos=[],
    )

    blocks = plan_execution_blocks(
        reference_bundle=reference_bundle,
        requirements=requirements,
        file_state={"path": "index.html", "content": "<html></html>"},
        validation_report=validation_report,
    )

    assert len(blocks) == 1
    assert blocks[0].section_names == ["Section 2", "Section 3"]


def test_split_execution_block_preserves_completed_sections() -> None:
    block = ExecutionBlock(
        title="Large block",
        objective="Build a large group.",
        section_names=["Header", "Hero", "Features", "FAQ"],
        preserve_section_names=["Theme"],
        include_media=False,
    )

    left, right = split_execution_block(block)

    assert left.section_names == ["Header", "Hero"]
    assert right.section_names == ["Features", "FAQ"]
    assert right.preserve_section_names == ["Theme", "Header", "Hero"]
