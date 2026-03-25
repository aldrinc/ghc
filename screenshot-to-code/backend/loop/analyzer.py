from llm import Llm
from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport
from loop.gemini import (
    GeminiPart,
    data_url_to_part,
    generate_structured_output,
    text_part,
)
from loop.analyzer_prompt import (
    ANALYZER_SYSTEM_INSTRUCTION,
    build_analyzer_prompt,
)


class LoopAnalyzer:
    def __init__(self, gemini_api_key: str):
        self._gemini_api_key = gemini_api_key
        self._model_name = "gemini-3.1-pro-preview"

    async def analyze(
        self,
        reference_bundle: ReferenceBundle,
        current_html: str | None = None,
        prior_requirements: RequirementsSpec | None = None,
        prior_validation: ValidationReport | None = None,
    ) -> RequirementsSpec:
        parts: list[GeminiPart] = [
            text_part(
                build_analyzer_prompt(
                    reference_bundle,
                    current_html,
                    prior_requirements,
                    prior_validation,
                )
            )
        ]

        for index, image in enumerate(reference_bundle.images, start=1):
            parts.append(text_part(f"Reference image {index}:"))
            parts.append(data_url_to_part(image))

        for index, video in enumerate(reference_bundle.videos, start=1):
            parts.append(text_part(f"Reference video {index}:"))
            parts.append(data_url_to_part(video))

        if reference_bundle.input_mode == "text":
            parts.append(text_part("There is no reference media for this request."))

        return await generate_structured_output(
            api_key=self._gemini_api_key,
            model_name=self._model_name,
            thinking_level="high",
            system_instruction=ANALYZER_SYSTEM_INSTRUCTION,
            parts=parts,
            response_schema=RequirementsSpec,
        )

    @property
    def model(self) -> Llm:
        return Llm.GEMINI_3_1_PRO_PREVIEW_HIGH
