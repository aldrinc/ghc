import importlib

import app.config as config_module


def test_strategy_v2_copy_defaults_remain_claude():
    assert config_module.Settings.model_fields["STRATEGY_V2_COPY_MODEL"].default == "claude-sonnet-4-6"
    assert config_module.Settings.model_fields["STRATEGY_V2_COPY_QA_MODEL"].default == "claude-sonnet-4-6"


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
