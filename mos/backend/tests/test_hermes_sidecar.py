import json

import pytest

from app.services.hermes_sidecar import HermesSidecarError, HermesSidecarService


def test_session_error_detects_missing_resumed_session():
    output = "Session not found: 20260401_174738_07ec73\nUse a session ID from a previous CLI run (hermes sessions list)."

    assert HermesSidecarService._session_error(output) == output


def test_session_error_ignores_normal_output():
    assert HermesSidecarService._session_error('{"assistantMessage":"ok"}') is None


def test_provider_error_ignores_retriable_api_failure_logs():
    output = (
        "⚠️  API call failed (attempt 1/3): SSLError\n"
        "session_id: 20260402_145807_54550f\n"
    )

    assert HermesSidecarService._provider_error(output) is None


def test_provider_error_detects_non_retryable_provider_failures():
    output = "Non-retryable client error detected: usage_limit_reached"

    assert HermesSidecarService._provider_error(output) == output


def test_load_usage_from_session_reads_exact_usage_payload(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "session_session-1.json").write_text(
        json.dumps(
            {
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 15,
                    "total_tokens": 135,
                    "cache_read_tokens": 80,
                    "cache_write_tokens": 40,
                    "api_call_count": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    usage = HermesSidecarService._load_usage_from_session(
        runtime_home=tmp_path,
        session_id="session-1",
    )

    assert usage == {
        "promptTokens": 120,
        "completionTokens": 15,
        "totalTokens": 135,
        "cacheReadTokens": 80,
        "cacheWriteTokens": 40,
        "apiCallCount": 2,
    }


def test_load_usage_from_session_errors_when_usage_missing(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "session_session-1.json").write_text("{}", encoding="utf-8")

    with pytest.raises(HermesSidecarError, match="exact usage telemetry"):
        HermesSidecarService._load_usage_from_session(
            runtime_home=tmp_path,
            session_id="session-1",
        )


def test_load_runtime_config_reads_repo_owned_settings(tmp_path):
    service = HermesSidecarService()
    service.runtime_config_path = tmp_path / "hermes_runtime_config.json"
    service.runtime_config_path.write_text(
        json.dumps(
            {
                "runtimeSchemaVersion": "config-v1",
                "toolsets": ["file", "skills"],
                "defaults": {
                    "model": "claude-test",
                    "provider": "custom",
                    "baseUrl": "https://api.anthropic.com/v1",
                    "compressionEnabled": True,
                    "compressionThreshold": 0.9,
                    "compressionSummaryProvider": "main",
                    "compressionSummaryModel": None,
                },
                "adapterSpec": {
                    "requiredRunAgentMarkers": ["required marker"],
                    "forbiddenRunAgentMarkers": ["forbidden marker"],
                },
            }
        ),
        encoding="utf-8",
    )

    config = service._load_runtime_config()

    assert config.runtime_schema_version == "config-v1"
    assert config.toolsets == ["file", "skills"]
    assert config.model == "claude-test"
    assert config.required_run_agent_markers == ("required marker",)
    assert config.forbidden_run_agent_markers == ("forbidden marker",)


def test_validate_runtime_installation_errors_on_runtime_drift(tmp_path):
    service = HermesSidecarService()
    service.hermes_run_agent_path = tmp_path / "run_agent.py"
    service.hermes_run_agent_path.write_text(
        "required marker\npayload[\"cache_control\"] = {\"type\": \"ephemeral\"}\n",
        encoding="utf-8",
    )
    service.runtime_config_path = tmp_path / "hermes_runtime_config.json"

    with pytest.raises(HermesSidecarError, match="does not match the repo-owned runtime config"):
        service._validate_runtime_installation(
            runtime_config=type(
                "Config",
                (),
                {
                    "required_run_agent_markers": ("required marker", "missing marker"),
                    "forbidden_run_agent_markers": ("payload[\"cache_control\"] = {\"type\": \"ephemeral\"}",),
                },
            )(),
        )


def test_load_runtime_settings_uses_repo_config_for_non_secret_defaults(tmp_path):
    service = HermesSidecarService()
    service.runtime_config_path = tmp_path / "hermes_runtime_config.json"
    service.sidecar_env_path = tmp_path / "sidecar.env"
    service.hermes_run_agent_path = tmp_path / "run_agent.py"
    service.runtime_config_path.write_text(
        json.dumps(
            {
                "runtimeSchemaVersion": "config-v2",
                "toolsets": ["file", "skills"],
                "defaults": {
                    "model": "claude-config",
                    "provider": "custom",
                    "baseUrl": "https://api.anthropic.com/v1",
                    "compressionEnabled": True,
                    "compressionThreshold": 0.85,
                    "compressionSummaryProvider": "main",
                    "compressionSummaryModel": None,
                },
                "adapterSpec": {
                    "requiredRunAgentMarkers": ["required marker"],
                    "forbiddenRunAgentMarkers": ["forbidden marker"],
                },
            }
        ),
        encoding="utf-8",
    )
    service.sidecar_env_path.write_text(
        "\n".join(
            [
                "MARKETI_HERMES_MODEL=claude-drift",
                "MARKETI_HERMES_PROVIDER=drift-provider",
                "MARKETI_HERMES_OPENAI_BASE_URL=https://example.com/v1",
                "ANTHROPIC_API_KEY=test-key",
            ]
        ),
        encoding="utf-8",
    )
    service.hermes_run_agent_path.write_text("required marker\n", encoding="utf-8")

    settings = service._load_runtime_settings()

    assert settings.runtime_schema_version == "config-v2"
    assert settings.toolsets == ["file", "skills"]
    assert settings.model == "claude-config"
    assert settings.provider == "custom"
    assert settings.base_url == "https://api.anthropic.com/v1"


def test_parse_progress_event_line_recognizes_tool_activity():
    event = HermesSidecarService._parse_progress_event_line(
        "  ┊ 📖 read      /tmp/runtime/START-HERE.md  1.0s"
    )

    assert event == {
        "type": "tool",
        "message": "📖 read      /tmp/runtime/START-HERE.md  1.0s",
        "icon": "📖",
        "toolName": "read",
        "target": "/tmp/runtime/START-HERE.md",
        "duration": "1.0s",
        "status": "completed",
    }


def test_parse_progress_event_line_recognizes_thinking_messages():
    event = HermesSidecarService._parse_progress_event_line(
        "┊ 💬 I need to read the runtime manifest before answering."
    )

    assert event == {
        "type": "thinking",
        "message": "I need to read the runtime manifest before answering.",
    }


def test_parse_progress_event_line_ignores_spinner_frames():
    assert HermesSidecarService._parse_progress_event_line(
        "⠋ (◕‿◕✿) 📖 /tmp/runtime/START-HERE.md (0.0s)"
    ) is None
