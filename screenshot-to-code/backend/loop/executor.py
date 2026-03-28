from typing import Any, Awaitable, Callable, Dict, Optional

from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam

from agent.runner import Agent
from llm import Llm
from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport
from loop.execution_blocks import (
    ExecutionBlock,
    split_execution_block,
    strip_execution_block_media,
)
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
        self._model = Llm.GEMINI_3_1_PRO_PREVIEW_HIGH

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
        execution_blocks: list[ExecutionBlock] | None = None,
    ) -> str:
        blocks = execution_blocks or [
            ExecutionBlock(
                title="Full page build" if not file_state else "Update current implementation",
                objective="Execute the current requirements against the page implementation.",
                section_names=[
                    section.name for section in requirements.section_requirements if section.name.strip()
                ],
                preserve_section_names=[],
                include_media=True,
            )
        ]
        current_file_state = file_state
        latest_code = current_file_state.get("content", "") if current_file_state else ""

        for block_index, block in enumerate(blocks, start=1):
            if len(blocks) > 1:
                await self._send_status(
                    f"Iteration {iteration}: executor block {block_index}/{len(blocks)} — {block.title}."
                )
            latest_code = await self._execute_block_with_fallback(
                reference_bundle=reference_bundle,
                requirements=requirements,
                file_state=current_file_state,
                validation_report=validation_report,
                iteration=iteration,
                execution_block=block,
            )
            current_file_state = {
                "path": current_file_state.get("path", "index.html")
                if current_file_state is not None
                else "index.html",
                "content": latest_code,
            }

        return latest_code

    async def _execute_block_with_fallback(
        self,
        *,
        reference_bundle: ReferenceBundle,
        requirements: RequirementsSpec,
        file_state: dict[str, str] | None,
        validation_report: ValidationReport | None,
        iteration: int,
        execution_block: ExecutionBlock,
    ) -> str:
        try:
            allow_image_generation = self._allow_image_generation_for_block(
                reference_bundle=reference_bundle,
                execution_block=execution_block,
            )
            prompt_messages = self._build_prompt_messages(
                reference_bundle=reference_bundle,
                requirements=requirements,
                file_state=file_state,
                validation_report=validation_report,
                iteration=iteration,
                execution_block=execution_block,
                image_generation_enabled=allow_image_generation,
            )
            return await self._run_agent(
                prompt_messages,
                file_state,
                reference_bundle,
                allow_image_generation=allow_image_generation,
            )
        except Exception as exc:
            if not self._is_token_limit_error(exc):
                raise

            if execution_block.include_media:
                await self._send_status(
                    f"Execution block '{execution_block.title}' exceeded the model token budget, retrying without extra reference media."
                )
                return await self._execute_block_with_fallback(
                    reference_bundle=reference_bundle,
                    requirements=requirements,
                    file_state=file_state,
                    validation_report=validation_report,
                    iteration=iteration,
                    execution_block=strip_execution_block_media(execution_block),
                )

            smaller_blocks = split_execution_block(execution_block)
            if smaller_blocks:
                await self._send_status(
                    f"Execution block '{execution_block.title}' still exceeded the token budget, splitting it into smaller section groups."
                )
                current_file_state = file_state
                latest_code = current_file_state.get("content", "") if current_file_state else ""
                for smaller_block in smaller_blocks:
                    latest_code = await self._execute_block_with_fallback(
                        reference_bundle=reference_bundle,
                        requirements=requirements,
                        file_state=current_file_state,
                        validation_report=validation_report,
                        iteration=iteration,
                        execution_block=smaller_block,
                    )
                    current_file_state = {
                        "path": current_file_state.get("path", "index.html")
                        if current_file_state is not None
                        else "index.html",
                        "content": latest_code,
                    }
                return latest_code

            raise RuntimeError(
                "Executor prompt exceeded the model token budget even after removing extra media and splitting the block."
            ) from exc

    async def _run_agent(
        self,
        prompt_messages: list[ChatCompletionMessageParam],
        file_state: dict[str, str] | None,
        reference_bundle: ReferenceBundle,
        *,
        allow_image_generation: bool,
    ) -> str:
        runner = Agent(
            send_message=self._send_message,
            variant_index=0,
            openai_api_key=self._openai_api_key,
            openai_base_url=self._openai_base_url,
            anthropic_api_key=self._anthropic_api_key,
            gemini_api_key=self._gemini_api_key,
            should_generate_images=allow_image_generation,
            initial_file_state=file_state,
            option_codes=self._option_codes,
        )
        return await runner.run(self._model, prompt_messages)

    def _executor_media_prompt(
        self,
        reference_bundle: ReferenceBundle,
        *,
        execution_block: ExecutionBlock | None,
    ) -> UserTurnInput:
        # Video references are analyzed once by the supervisor and then omitted from
        # executor turns to keep Gemini tool-calling sessions under the token limit.
        if execution_block is not None and not execution_block.include_media:
            return {
                "text": "",
                "images": [],
                "reference_url": reference_bundle.reference_url,
                "videos": [],
            }

        selected_images = list(reference_bundle.images[:2])
        render_images = (
            [
                render.data_url
                for render in reference_bundle.live_reference.renders
                if "full-page" not in render.label.lower()
                and "full page" not in render.label.lower()
            ][:1]
            if reference_bundle.live_reference is not None
            else []
        )
        return {
            "text": "",
            "images": [*selected_images, *render_images],
            "reference_url": reference_bundle.reference_url,
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
        execution_block: ExecutionBlock | None = None,
        image_generation_enabled: bool | None = None,
    ) -> list[ChatCompletionMessageParam]:
        effective_image_generation = (
            self._should_generate_images
            if image_generation_enabled is None
            else image_generation_enabled
        )
        if file_state and file_state.get("content", "").strip():
            media_prompt = self._executor_media_prompt(
                reference_bundle,
                execution_block=execution_block,
            )
            if validation_report is None:
                revision_text = build_executor_update_prompt(
                    reference_bundle=reference_bundle,
                    requirements=requirements,
                    iteration=iteration,
                    execution_block=execution_block,
                )
            else:
                revision_text = build_executor_revision_prompt(
                    reference_bundle=reference_bundle,
                    requirements=requirements,
                    validation_report=validation_report,
                    iteration=iteration,
                    execution_block=execution_block,
                )
            prompt: UserTurnInput = {
                "text": revision_text,
                "images": media_prompt["images"],
                "reference_url": media_prompt.get("reference_url", ""),
                "videos": media_prompt["videos"],
            }
            return build_executor_update_messages(
                stack=reference_bundle.stack,
                prompt=prompt,
                file_state=file_state,
                image_generation_enabled=effective_image_generation,
            )

        user_text = build_executor_create_prompt(
            reference_bundle=reference_bundle,
            requirements=requirements,
            image_generation_enabled=effective_image_generation,
            execution_block=execution_block,
        )
        media_prompt = self._executor_media_prompt(
            reference_bundle,
            execution_block=execution_block,
        )
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

    async def _send_status(self, message: str) -> None:
        await self._send_message("status", message, 0, None, None)

    @staticmethod
    def _is_token_limit_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "input token count exceeds" in message or "token budget" in message

    def _allow_image_generation_for_block(
        self,
        *,
        reference_bundle: ReferenceBundle,
        execution_block: ExecutionBlock,
    ) -> bool:
        return (
            self._should_generate_images
            and reference_bundle.input_mode != "video"
            and execution_block.include_media
        )
