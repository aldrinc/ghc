from typing import Any, Awaitable, Callable, Dict, Optional

from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam

from agent.runner import Agent
from llm import Llm
from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport
from loop.executor_prompt import (
    build_executor_create_prompt,
    build_executor_revision_prompt,
    build_executor_update_messages,
    build_executor_update_prompt,
)
from prompts import system_prompt
from prompts.prompt_types import UserTurnInput


class LoopExecutor:
    def __init__(
        self,
        *,
        send_message: Callable[..., Awaitable[None]],
        openai_api_key: str | None,
        openai_base_url: str | None,
        anthropic_api_key: str | None,
        gemini_api_key: str | None,
        should_generate_images: bool,
        option_codes: list[str] | None,
    ) -> None:
        self._send_message = send_message
        self._openai_api_key = openai_api_key
        self._openai_base_url = openai_base_url
        self._anthropic_api_key = anthropic_api_key
        self._gemini_api_key = gemini_api_key
        self._should_generate_images = should_generate_images
        self._option_codes = option_codes
        self._model = Llm.CLAUDE_OPUS_4_6

    @property
    def model(self) -> Llm:
        return self._model

    async def execute(
        self,
        *,
        reference_bundle: ReferenceBundle,
        requirements: RequirementsSpec,
        file_state: dict[str, str] | None,
        validation_report: ValidationReport | None,
        iteration: int,
    ) -> str:
        prompt_messages = self._build_prompt_messages(
            reference_bundle=reference_bundle,
            requirements=requirements,
            file_state=file_state,
            validation_report=validation_report,
            iteration=iteration,
        )

        runner = Agent(
            send_message=self._send_message,
            variant_index=0,
            openai_api_key=self._openai_api_key,
            openai_base_url=self._openai_base_url,
            anthropic_api_key=self._anthropic_api_key,
            gemini_api_key=self._gemini_api_key,
            should_generate_images=(
                self._should_generate_images
                and reference_bundle.input_mode != "video"
            ),
            initial_file_state=file_state,
            option_codes=self._option_codes,
        )
        return await runner.run(self._model, prompt_messages)

    def _executor_media_prompt(
        self, reference_bundle: ReferenceBundle
    ) -> UserTurnInput:
        # Video references are analyzed once by the supervisor and then omitted from
        # executor turns to keep Gemini tool-calling sessions under the token limit.
        return {
            "text": "",
            "images": reference_bundle.images,
            "videos": [] if reference_bundle.input_mode == "video" else reference_bundle.videos,
        }

    def _build_prompt_messages(
        self,
        *,
        reference_bundle: ReferenceBundle,
        requirements: RequirementsSpec,
        file_state: dict[str, str] | None,
        validation_report: ValidationReport | None,
        iteration: int,
    ) -> list[ChatCompletionMessageParam]:
        if file_state and file_state.get("content", "").strip():
            media_prompt = self._executor_media_prompt(reference_bundle)
            if validation_report is None:
                revision_text = build_executor_update_prompt(
                    reference_bundle=reference_bundle,
                    requirements=requirements,
                    iteration=iteration,
                )
            else:
                revision_text = build_executor_revision_prompt(
                    reference_bundle=reference_bundle,
                    requirements=requirements,
                    validation_report=validation_report,
                    iteration=iteration,
                )
            prompt: UserTurnInput = {
                "text": revision_text,
                "images": media_prompt["images"],
                "videos": media_prompt["videos"],
            }
            return build_executor_update_messages(
                stack=reference_bundle.stack,
                prompt=prompt,
                file_state=file_state,
                image_generation_enabled=self._should_generate_images,
            )

        user_text = build_executor_create_prompt(
            reference_bundle=reference_bundle,
            requirements=requirements,
            image_generation_enabled=self._should_generate_images,
        )
        media_prompt = self._executor_media_prompt(reference_bundle)
        user_content: list[ChatCompletionContentPartParam] = []

        for image in media_prompt["images"]:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image, "detail": "high"},
                }
            )

        for video in media_prompt["videos"]:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": video, "detail": "high"},
                }
            )

        user_content.append({"type": "text", "text": user_text})
        return [
            {"role": "system", "content": system_prompt.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
