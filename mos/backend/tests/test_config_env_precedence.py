import importlib

import app.config as config_module
from app.temporal.workflows import precanon_market_research as precanon_workflow


def test_strategy_v2_reasoning_defaults_use_gpt55():
    assert config_module.Settings.model_fields["STRATEGY_V2_VOC_MODEL"].default == "gpt-5.5"
    assert config_module.Settings.model_fields["STRATEGY_V2_OFFER_MODEL"].default == "gpt-5.5"


def test_strategy_v2_foundational_step01_defaults_to_deerflow():
    fields = config_module.Settings.model_fields
    assert fields["STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER"].default == "deerflow"
    assert fields["STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL"].default == "deepseek-v4-pro"


def test_strategy_v2_foundational_step04_defaults_to_gpt_with_dsv4_available():
    fields = config_module.Settings.model_fields
    assert fields["STRATEGY_V2_FOUNDATIONAL_STEP04_PROVIDER"].default == "gpt"
    assert fields["STRATEGY_V2_FOUNDATIONAL_STEP04_DEERFLOW_MODEL"].default == "deepseek-v4-pro"


def test_paid_ads_qa_default_uses_gpt55():
    assert config_module.Settings.model_fields["PAID_ADS_QA_LLM_MODEL"].default == "gpt-5.5"


def test_precanon_reasoning_default_uses_gpt55_xhigh():
    assert precanon_workflow.DEFAULT_REASONING_MODEL == "gpt-5.5"
    assert precanon_workflow.DEFAULT_REASONING_EFFORT == "xhigh"
    params = precanon_workflow._llm_params_for_step("01")
    assert params.model == "gpt-5.5"
    assert params.use_reasoning is True
    assert params.reasoning_effort == "xhigh"


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
