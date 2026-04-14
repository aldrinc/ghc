from llm import Llm
from loop.blueprint_validator_prompt import (
    BLUEPRINT_VALIDATOR_SYSTEM_INSTRUCTION,
    build_blueprint_validator_prompt,
)
from loop.contracts import (
    BlueprintValidationReport,
    ReferenceBundle,
    RequirementsSpec,
)
from loop.gemini import (
    GeminiPart,
    data_url_to_part,
    generate_structured_output,
    text_part,
)


def _append_labeled_media(
    parts: list[GeminiPart],
    *,
    label: str,
    data_url: str,
) -> None:
    parts.append(text_part(label))
    parts.append(data_url_to_part(data_url))


class LoopBlueprintValidator:
    def __init__(self, gemini_api_key: str):
        self._gemini_api_key = gemini_api_key
        self._model_name = "gemini-3.1-pro-preview"

    async def validate(
        self,
        *,
        reference_bundle: ReferenceBundle,
        requirements: RequirementsSpec,
        prior_blueprint_validation: BlueprintValidationReport | None = None,
    ) -> BlueprintValidationReport:
        parts: list[GeminiPart] = [
            text_part(
                build_blueprint_validator_prompt(
                    reference_bundle,
                    requirements,
                    prior_blueprint_validation,
                )
            )
        ]

        for index, image in enumerate(reference_bundle.images[:6], start=1):
            _append_labeled_media(parts, label=f"Reference image {index}:", data_url=image)

        if reference_bundle.live_reference is not None:
            for index, render in enumerate(reference_bundle.live_reference.renders[:4], start=1):
                _append_labeled_media(
                    parts,
                    label=(
                        f"Live browser render {index} ({render.label}) "
                        f"from {reference_bundle.live_reference.url}:"
                    ),
                    data_url=render.data_url,
                )

        for index, video in enumerate(reference_bundle.videos[:1], start=1):
            _append_labeled_media(parts, label=f"Reference video {index}:", data_url=video)

        return await generate_structured_output(
            api_key=self._gemini_api_key,
            model_name=self._model_name,
            thinking_level="high",
            system_instruction=BLUEPRINT_VALIDATOR_SYSTEM_INSTRUCTION,
            parts=parts,
            response_schema=BlueprintValidationReport,
        )

    @property
    def model(self) -> Llm:
        return Llm.GEMINI_3_1_PRO_PREVIEW_HIGH
