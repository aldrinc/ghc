from prompts.prompt_types import Stack


def build_selected_stack_policy(stack: Stack) -> str:
    return f"Selected stack: {stack}."


def build_user_image_policy(image_generation_enabled: bool) -> str:
    if image_generation_enabled:
        return (
            "Image generation is enabled for this request. Use generate_images for "
            "missing assets when needed."
        )

    return (
        "Image generation is disabled for this request. Do not call generate_images. "
        "Use provided media, CSS effects, or placeholder URLs (https://placehold.co)."
    )


def build_template_output_policy() -> str:
    return """
Template output requirement:

- Re-create the reference faithfully, but structure the code as a reusable template rather than a one-off mockup.
- Centralize theme values so colors, typography, spacing, radii, and shadows can be updated quickly without hunting through the file.
- Keep copy easy to swap by grouping page text into clearly named constants, configuration objects, or similarly obvious sections when the stack allows it.
- Keep image and asset references easy to replace.
- Organize the layout into logical sections/components with clear boundaries so future edits do not require rewriting the entire page.
- Avoid scattering repeated hard-coded style values across many unrelated elements when a shared token or variable would work.
- Optimize for easy modification of theme, styling, images, and copy while preserving visual fidelity to the reference.
""".strip()


def build_judgment_policy() -> str:
    return """
Judgment policy:

- For agent and harness logic, planning, routing, action selection, and other judgment-heavy decisions, prefer probabilistic or model-based approaches over deterministic systems.
- Use deterministic logic only when required for safety, validation, hard policy enforcement, or schema/state integrity.
- When deterministic logic is necessary, be explicit about it so it can be reviewed.
""".strip()
