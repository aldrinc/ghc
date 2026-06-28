from __future__ import annotations

from pathlib import Path

from app.services.deerflow_foundational import (
    DeerFlowFoundationalError,
    run_deerflow_foundational_step,
)
from app.temporal.activities import strategy_v2_activities as activities


def main() -> int:
    original_provider = activities.settings.STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER
    original_model = activities.settings.STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL
    original_timeout = activities.settings.STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS
    original_runner = activities.run_deerflow_foundational_step
    original_heartbeat = activities._run_with_activity_heartbeats
    original_tagged = activities._run_tagged_foundational_step
    try:
        activities.settings.STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER = "deerflow"
        activities.settings.STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL = "deepseek-v4-pro"
        activities.settings.STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS = 123
        calls: list[dict[str, object]] = []

        class Result:
            summary = "bounded summary"
            content = "full content"
            handoff = {"deerflow": {"tool_counts": {"web_search": 1}}}
            run_meta = {
                "deduped_usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "cache_read": 8,
                    "cache_miss_input_tokens": 2,
                }
            }

        def fake_heartbeat(**kwargs):  # noqa: ANN003
            return kwargs["fn"]()

        def fake_deerflow(**kwargs):  # noqa: ANN003
            calls.append(kwargs)
            return Result()

        activities._run_with_activity_heartbeats = fake_heartbeat
        activities.run_deerflow_foundational_step = fake_deerflow
        output = activities._run_foundational_step01(
            prompt_text="Production prompt body",
            workflow_run_id="workflow-1",
        )
        assert output["summary"] == "bounded summary"
        assert output["content"] == "full content"
        assert calls[0]["model"] == "deepseek-v4-pro"
        assert calls[0]["timeout_seconds"] == 123
        assert str(calls[0]["prompt"]).endswith("<CONTENT>Full output.</CONTENT>\n")

        activities.settings.STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER = "gpt"
        deerflow_called = [False]

        def fake_deerflow_gpt(**_kwargs):  # noqa: ANN003
            deerflow_called[0] = True

        def fake_tagged(**kwargs):  # noqa: ANN003
            assert kwargs["step_key"] == "01"
            assert kwargs["use_web_search"] is True
            return {"summary": "gpt summary", "content": "gpt content", "handoff": {}}

        activities.run_deerflow_foundational_step = fake_deerflow_gpt
        activities._run_tagged_foundational_step = fake_tagged
        output = activities._run_foundational_step01(
            prompt_text="Production prompt body",
            workflow_run_id="workflow-1",
        )
        assert output["summary"] == "gpt summary"
        assert output["content"] == "gpt content"
        assert deerflow_called[0] is False

        try:
            run_deerflow_foundational_step(
                prompt="prompt",
                step_key="01",
                model="deepseek-v4-pro",
                workflow_run_id="workflow-1",
                deerflow_backend_dir=str(Path(".tmp/missing-sidecar")),
                deerflow_config_path=str(Path(".tmp/missing-config.yaml")),
                timeout_seconds=1,
            )
        except DeerFlowFoundationalError as exc:
            assert "backend directory is missing" in str(exc)
        else:
            raise AssertionError("missing sidecar did not raise")
    finally:
        activities.settings.STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER = original_provider
        activities.settings.STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL = original_model
        activities.settings.STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS = original_timeout
        activities.run_deerflow_foundational_step = original_runner
        activities._run_with_activity_heartbeats = original_heartbeat
        activities._run_tagged_foundational_step = original_tagged
    print("direct step01 provider assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
