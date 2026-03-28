from typing import Any, cast

import pytest

from loop.contracts import ReferenceBundle, RequirementsSpec, SectionRequirement
from loop.execution_blocks import ExecutionBlock
from loop.executor import LoopExecutor


def _requirements() -> RequirementsSpec:
    return RequirementsSpec(
        summary="Build the page",
        section_requirements=[
            SectionRequirement(name="Header"),
            SectionRequirement(name="Hero"),
            SectionRequirement(name="Features"),
            SectionRequirement(name="FAQ"),
        ],
    )


class _RecordingExecutor(LoopExecutor):
    def __init__(self) -> None:
        async def send_message(*args: Any, **kwargs: Any) -> None:
            return None

        super().__init__(
            send_message=send_message,
            openai_api_key=None,
            openai_base_url=None,
            anthropic_api_key=None,
            gemini_api_key="key",
            should_generate_images=False,
            option_codes=[],
        )
        self.calls: list[dict[str, Any]] = []

    async def _run_agent(
        self,
        prompt_messages,
        file_state,
        reference_bundle,
        *,
        allow_image_generation,
    ):
        user_message = cast(Any, prompt_messages[-1])
        content = cast(Any, user_message).get("content")
        image_count = 0
        if isinstance(content, list):
            image_count = sum(
                1
                for part in cast(list[Any], content)
                if isinstance(part, dict) and part.get("type") == "image_url"
            )
        self.calls.append(
            {
                "image_count": image_count,
                "content": content,
                "has_file_state": bool(file_state and file_state.get("content")),
            }
        )

        if len(self.calls) == 1:
            raise RuntimeError(
                "The input token count exceeds the maximum number of tokens allowed 1048576."
            )
        return f"<html><body>pass-{len(self.calls)}</body></html>"


@pytest.mark.asyncio
async def test_executor_retries_without_media_after_token_limit_error() -> None:
    executor = _RecordingExecutor()
    html = await executor.execute(
        reference_bundle=ReferenceBundle(
            input_mode="image",
            stack="html_tailwind",
            user_text="Build this page.",
            images=["data:image/png;base64,abc"],
            videos=[],
        ),
        requirements=_requirements(),
        file_state=None,
        validation_report=None,
        iteration=1,
        execution_blocks=[
            ExecutionBlock(
                title="Opening block",
                objective="Build the shell and hero.",
                section_names=["Header", "Hero"],
                preserve_section_names=[],
                include_media=True,
            )
        ],
    )

    assert html == "<html><body>pass-2</body></html>"
    assert executor.calls[0]["image_count"] == 1
    assert executor.calls[1]["image_count"] == 0


@pytest.mark.asyncio
async def test_executor_splits_block_after_token_limit_without_media() -> None:
    executor = _RecordingExecutor()
    html = await executor.execute(
        reference_bundle=ReferenceBundle(
            input_mode="text",
            stack="html_tailwind",
            user_text="Build this page.",
            images=[],
            videos=[],
        ),
        requirements=_requirements(),
        file_state=None,
        validation_report=None,
        iteration=1,
        execution_blocks=[
            ExecutionBlock(
                title="Large block",
                objective="Build all major sections.",
                section_names=["Header", "Hero", "Features", "FAQ"],
                preserve_section_names=[],
                include_media=False,
            )
        ],
    )

    assert html == "<html><body>pass-3</body></html>"
    assert len(executor.calls) == 3
    assert executor.calls[1]["has_file_state"] is False
    assert executor.calls[2]["has_file_state"] is True
