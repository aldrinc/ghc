from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.services.deerflow_foundational import (
    DeerFlowFoundationalError,
    run_deerflow_foundational_step,
)
from app.temporal.activities import strategy_v2_activities as activities
from scripts.run_deerflow_foundational_step import validate_step04_dsv4_output


def test_step01_provider_default_routes_to_deerflow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activities.settings, "STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER", "deerflow")
    monkeypatch.setattr(
        activities.settings,
        "STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL",
        "deepseek-v4-pro",
    )
    monkeypatch.setattr(
        activities.settings,
        "STRATEGY_V2_DEERFLOW_BACKEND_DIR",
        ".local/deer-flow/backend",
    )
    monkeypatch.setattr(
        activities.settings,
        "STRATEGY_V2_DEERFLOW_CONFIG_PATH",
        ".local/deer-flow/config.yaml",
    )
    monkeypatch.setattr(activities.settings, "STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS", 123)

    calls: list[dict[str, object]] = []

    class _Result:
        summary = "bounded summary"
        content = "full content"
        handoff = {"deerflow": {"tool_counts": {"web_search": 1, "calculator": 1}}}
        run_meta = {
            "deduped_usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "cache_read": 8,
                "cache_miss_input_tokens": 2,
            }
        }

    def _fake_run_with_heartbeats(**kwargs):  # noqa: ANN003
        return kwargs["fn"]()

    def _fake_run_deerflow(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        return _Result()

    monkeypatch.setattr(activities, "_run_with_activity_heartbeats", _fake_run_with_heartbeats)
    monkeypatch.setattr(activities, "run_deerflow_foundational_step", _fake_run_deerflow)

    result = activities._run_foundational_step01(
        prompt_text="Production prompt body",
        workflow_run_id="workflow-1",
    )

    assert result["summary"] == "bounded summary"
    assert result["content"] == "full content"
    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "deepseek-v4-pro"
    assert call["workflow_run_id"] == "workflow-1"
    assert call["timeout_seconds"] == 123
    assert str(call["prompt"]).endswith("<CONTENT>Full output.</CONTENT>\n")


def test_step01_provider_gpt_override_uses_existing_llm_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activities.settings, "STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER", "gpt")
    deerflow_called = False

    def _fake_run_deerflow(**_kwargs):  # noqa: ANN003
        nonlocal deerflow_called
        deerflow_called = True

    def _fake_tagged_step(**kwargs):  # noqa: ANN003
        assert kwargs["step_key"] == "01"
        assert kwargs["use_web_search"] is True
        return {"summary": "gpt summary", "content": "gpt content", "handoff": {}}

    monkeypatch.setattr(activities, "run_deerflow_foundational_step", _fake_run_deerflow)
    monkeypatch.setattr(activities, "_run_tagged_foundational_step", _fake_tagged_step)

    result = activities._run_foundational_step01(
        prompt_text="Production prompt body",
        workflow_run_id="workflow-1",
    )

    assert result["summary"] == "gpt summary"
    assert result["content"] == "gpt content"
    assert deerflow_called is False


def test_step04_provider_gpt_uses_existing_llm_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activities.settings, "STRATEGY_V2_FOUNDATIONAL_STEP04_PROVIDER", "gpt")
    deerflow_called = False

    def _fake_run_deerflow_step04(**_kwargs):  # noqa: ANN003
        nonlocal deerflow_called
        deerflow_called = True

    def _fake_tagged_step(**kwargs):  # noqa: ANN003
        assert kwargs["step_key"] == "04"
        assert kwargs["prompt_text"] == "Step 4 prompt"
        assert kwargs["use_web_search"] is True
        assert kwargs["max_tokens"] == activities._FOUNDTN_STEP04_MAX_TOKENS
        return {"summary": "gpt summary", "content": "gpt content", "handoff": {}}

    monkeypatch.setattr(activities, "run_deerflow_foundational_step04", _fake_run_deerflow_step04)
    monkeypatch.setattr(activities, "_run_tagged_foundational_step", _fake_tagged_step)

    result = activities._run_foundational_step04(
        prompt_text="Step 4 prompt",
        workflow_run_id="workflow-1",
    )

    assert result["summary"] == "gpt summary"
    assert result["content"] == "gpt content"
    assert deerflow_called is False


def test_step04_provider_deerflow_uses_distinct_step04_sidecar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activities.settings, "STRATEGY_V2_FOUNDATIONAL_STEP04_PROVIDER", "deerflow")
    monkeypatch.setattr(
        activities.settings,
        "STRATEGY_V2_FOUNDATIONAL_STEP04_DEERFLOW_MODEL",
        "deepseek-v4-pro",
    )
    monkeypatch.setattr(
        activities.settings,
        "STRATEGY_V2_DEERFLOW_BACKEND_DIR",
        ".local/deer-flow/backend",
    )
    monkeypatch.setattr(
        activities.settings,
        "STRATEGY_V2_DEERFLOW_CONFIG_PATH",
        ".local/deer-flow/config.yaml",
    )
    monkeypatch.setattr(activities.settings, "STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS", 123)

    calls: list[dict[str, object]] = []

    class _Result:
        summary = "dsv4 summary"
        content = "dsv4 content"
        handoff = {"deerflow": {"mode": "step04_dsv4_research_synthesis"}}
        run_meta = {
            "deduped_usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "cache_read": 40,
                "cache_miss_input_tokens": 60,
            }
        }

    def _fake_run_with_heartbeats(**kwargs):  # noqa: ANN003
        return kwargs["fn"]()

    def _fake_run_deerflow_step04(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        return _Result()

    monkeypatch.setattr(activities, "_run_with_activity_heartbeats", _fake_run_with_heartbeats)
    monkeypatch.setattr(activities, "run_deerflow_foundational_step04", _fake_run_deerflow_step04)

    result = activities._run_foundational_step04(
        prompt_text="Step 4 prompt",
        workflow_run_id="workflow-1",
    )

    assert result["summary"] == "dsv4 summary"
    assert result["content"] == "dsv4 content"
    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "deepseek-v4-pro"
    assert call["workflow_run_id"] == "workflow-1"
    assert call["timeout_seconds"] == 123
    assert str(call["prompt"]).endswith("<CONTENT>Full output.</CONTENT>\n")


def test_step04_dsv4_validation_rejects_status_only_output() -> None:
    errors = validate_step04_dsv4_output(
        "I now have enough data to produce the comprehensive report. Let me write it now."
    )

    assert "missing <SUMMARY> block" in errors
    assert "status/planning text instead of final report" in errors


def test_step04_dsv4_validation_rejects_placeholder_content() -> None:
    raw = (
        "<SUMMARY>Bounded summary.</SUMMARY>\n"
        "<CONTENT>Full research document with all 9 categories (A-I), "
        "each with quote banks.</CONTENT>"
    )

    errors = validate_step04_dsv4_output(raw)

    assert "placeholder content instead of full report" in errors
    assert "content shorter than 8000 chars" in errors


def test_step04_dsv4_validation_accepts_typographic_signal_to_noise_dash() -> None:
    quote_bank = "\n".join(f"QUOTE: quote {idx}\nSOURCE: source {idx}" for idx in range(20))
    categories = "\n".join(f"## Category {letter}\nBody" for letter in "ABCDEFGHI")
    raw = (
        "<SUMMARY>Bounded summary.</SUMMARY>\n"
        "<CONTENT>\n"
        f"{categories}\n"
        f"{quote_bank}\n"
        "## Signal‑to‑Noise Assessment\n"
        "## Bayesian Confidence\n"
        "## Bottleneck Identification\n"
        "## Core Avatar Belief\n"
        f"{'Full content. ' * 700}\n"
        "</CONTENT>"
    )

    assert "missing required section: signal-to-noise" not in validate_step04_dsv4_output(raw)


def test_deerflow_foundational_step_fails_when_sidecar_missing(tmp_path: Path) -> None:
    with pytest.raises(DeerFlowFoundationalError, match="backend directory is missing"):
        run_deerflow_foundational_step(
            prompt="prompt",
            step_key="01",
            model="deepseek-v4-pro",
            workflow_run_id="workflow-1",
            deerflow_backend_dir=str(tmp_path / "missing"),
            deerflow_config_path=str(tmp_path / "config.yaml"),
            timeout_seconds=1,
        )


def test_deerflow_foundational_step_uses_sidecar_virtualenv_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend_dir = tmp_path / "deerflow-backend"
    sidecar_bin = backend_dir / ".venv" / "bin"
    sidecar_bin.mkdir(parents=True)
    sidecar_python = sidecar_bin / "python"
    sidecar_python.write_text("#!/bin/sh\n", encoding="utf-8")
    (backend_dir / ".env").write_text(
        "DEEPSEEK_API_KEY=test\nSERPER_API_KEY=test\nJINA_API_KEY=test\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def _fake_run(command, **kwargs):  # noqa: ANN001, ANN003
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "summary": "bounded summary",
                    "content": "full content",
                    "handoff": {"ok": True},
                    "raw_output": "<SUMMARY>bounded summary</SUMMARY><CONTENT>full content</CONTENT>",
                    "run_meta": {"model": "deepseek-v4-pro"},
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.services.deerflow_foundational.subprocess.run", _fake_run)

    result = run_deerflow_foundational_step(
        prompt="prompt",
        step_key="01",
        model="deepseek-v4-pro",
        workflow_run_id="workflow-1",
        deerflow_backend_dir=str(backend_dir),
        deerflow_config_path=str(config_path),
        timeout_seconds=1,
        artifact_root=str(tmp_path / "artifacts"),
    )

    assert result.summary == "bounded summary"
    assert captured["command"][0] == str(sidecar_python)
    assert "uv" not in captured["command"]
