import importlib

import app.config as config_module


def test_strategy_v2_copy_defaults_remain_claude():
    assert config_module.Settings.model_fields["STRATEGY_V2_COPY_MODEL"].default == "claude-opus-4-6"
    assert config_module.Settings.model_fields["STRATEGY_V2_COPY_QA_MODEL"].default == "claude-opus-4-6"


def test_process_env_overrides_backend_dotenv(monkeypatch):
    monkeypatch.setenv("STRATEGY_V2_COPY_MODEL", "baseten:moonshotai/Kimi-K2.5")
    monkeypatch.setenv("STRATEGY_V2_COPY_QA_MODEL", "baseten:moonshotai/Kimi-K2.5")

    importlib.reload(config_module)
    try:
        assert config_module.settings.STRATEGY_V2_COPY_MODEL == "baseten:moonshotai/Kimi-K2.5"
        assert config_module.settings.STRATEGY_V2_COPY_QA_MODEL == "baseten:moonshotai/Kimi-K2.5"
    finally:
        monkeypatch.delenv("STRATEGY_V2_COPY_MODEL", raising=False)
        monkeypatch.delenv("STRATEGY_V2_COPY_QA_MODEL", raising=False)
        importlib.reload(config_module)


def test_clerk_audience_accepts_csv_env(monkeypatch):
    monkeypatch.setenv("CLERK_AUDIENCE", "http://localhost:5173,http://localhost:5275,backend")

    importlib.reload(config_module)
    try:
        assert config_module.settings.CLERK_AUDIENCE == [
            "http://localhost:5173",
            "http://localhost:5275",
            "backend",
        ]
    finally:
        monkeypatch.delenv("CLERK_AUDIENCE", raising=False)
        importlib.reload(config_module)


def test_backend_cors_origins_accepts_json_env(monkeypatch):
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["http://localhost:5173","http://localhost:8000"]')

    importlib.reload(config_module)
    try:
        assert "http://localhost:5173" in config_module.settings.BACKEND_CORS_ORIGINS
        assert "http://localhost:8000" in config_module.settings.BACKEND_CORS_ORIGINS
        assert "http://localhost:5275" in config_module.settings.BACKEND_CORS_ORIGINS
        assert "http://127.0.0.1:5275" in config_module.settings.BACKEND_CORS_ORIGINS
    finally:
        monkeypatch.delenv("BACKEND_CORS_ORIGINS", raising=False)
        importlib.reload(config_module)
