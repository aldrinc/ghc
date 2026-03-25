import pytest

from agent.state import AgentFileState
from agent.tools.runtime import AgentToolRuntime
from agent.tools.types import ToolCall


def test_edit_file_returns_structured_result_with_diff() -> None:
    runtime = AgentToolRuntime(
        file_state=AgentFileState(
            path="index.html",
            content="<div>before</div>\n<p>keep</p>\n",
        ),
        should_generate_images=False,
        openai_api_key=None,
        gemini_api_key=None,
        openai_base_url=None,
    )

    result = runtime._edit_file(
        {
            "old_text": "<div>before</div>",
            "new_text": "<div>after</div>",
        }
    )

    assert result.ok is True
    assert result.updated_content == "<div>after</div>\n<p>keep</p>\n"
    assert result.result["content"] == "Successfully edited file at index.html."
    assert set(result.result["details"].keys()) == {"diff", "firstChangedLine"}
    assert result.result["details"]["firstChangedLine"] == 1
    assert "--- index.html" in result.result["details"]["diff"]
    assert "+++ index.html" in result.result["details"]["diff"]
    assert "-<div>before</div>" in result.result["details"]["diff"]
    assert "+<div>after</div>" in result.result["details"]["diff"]
    assert result.summary["firstChangedLine"] == 1
    assert result.summary["diff"] == result.result["details"]["diff"]


@pytest.mark.asyncio
async def test_execute_edit_file_uses_updated_result_shape() -> None:
    runtime = AgentToolRuntime(
        file_state=AgentFileState(path="index.html", content="<main>old</main>"),
        should_generate_images=False,
        openai_api_key=None,
        gemini_api_key=None,
        openai_base_url=None,
    )

    result = await runtime.execute(
        ToolCall(
            id="call-1",
            name="edit_file",
            arguments={"old_text": "old", "new_text": "new"},
        )
    )

    # execute() is sync for edit_file and should preserve the structured payload.
    assert result.ok is True
    assert result.result["content"] == "Successfully edited file at index.html."
    assert set(result.result["details"].keys()) == {"diff", "firstChangedLine"}
    assert "--- index.html" in result.result["details"]["diff"]


@pytest.mark.asyncio
async def test_generate_images_prefers_gemini_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | list[str] | None] = {}

    async def fake_process_tasks(
        prompts: list[str],
        api_key: str,
        base_url: str | None,
        model: str,
    ) -> list[str]:
        captured["prompts"] = prompts
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        captured["model"] = model
        return ["data:image/png;base64,ZmFrZQ=="]

    monkeypatch.setattr("agent.tools.runtime.REPLICATE_API_KEY", None)
    monkeypatch.setattr("agent.tools.runtime.process_tasks", fake_process_tasks)

    runtime = AgentToolRuntime(
        file_state=AgentFileState(),
        should_generate_images=True,
        openai_api_key="openai-key",
        gemini_api_key="gemini-key",
        openai_base_url="https://example.com/openai",
    )

    result = await runtime.execute(
        ToolCall(
            id="call-1",
            name="generate_images",
            arguments={"prompts": ["hero image"]},
        )
    )

    assert result.ok is True
    assert captured == {
        "prompts": ["hero image"],
        "api_key": "gemini-key",
        "base_url": None,
        "model": "gemini-2.5-flash-image",
    }
    assert result.result["provider"] == "gemini"
    assert result.result["model"] == "gemini-2.5-flash-image"
