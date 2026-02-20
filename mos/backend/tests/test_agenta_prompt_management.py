from __future__ import annotations

import hashlib
import sys
import types

import pytest

from app.config import settings
from app.llm_ops import agenta as agenta_ops
from app.llm_ops.agenta import AgentaConfigError
from app.services import ad_breakdown
from app.temporal.precanon import prompt_utils


def _reset_prompt_state(monkeypatch) -> None:
    agenta_ops.clear_prompt_cache()
    monkeypatch.setattr(agenta_ops, "_AGENTA_INITIALIZED", False)
    ad_breakdown._PROMPT_CACHE.clear()


def test_ad_breakdown_prompt_uses_local_file_when_agenta_disabled(monkeypatch):
    _reset_prompt_state(monkeypatch)
    monkeypatch.setattr(settings, "AGENTA_ENABLED", False)

    text, sha = ad_breakdown.load_ad_breakdown_prompt()

    backend_app_root = ad_breakdown.Path(__file__).resolve().parents[1] / "app"
    prompt_path = backend_app_root / "prompts" / "creative_analysis" / "ad_breakdown.md"
    expected_text = prompt_path.read_text(encoding="utf-8")
    expected_sha = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()

    assert text == expected_text
    assert sha == expected_sha


def test_ad_breakdown_prompt_errors_when_agenta_enabled_and_prompt_missing(monkeypatch):
    _reset_prompt_state(monkeypatch)
    monkeypatch.setattr(settings, "AGENTA_ENABLED", True)
    monkeypatch.setattr(settings, "AGENTA_API_KEY", "test-api-key")
    monkeypatch.setattr(settings, "AGENTA_HOST", "https://cloud.agenta.ai")
    monkeypatch.setattr(settings, "AGENTA_PROMPT_REGISTRY", {})

    with pytest.raises(AgentaConfigError, match="missing from AGENTA_PROMPT_REGISTRY"):
        ad_breakdown.load_ad_breakdown_prompt()


def test_ad_breakdown_prompt_fetches_from_agenta_registry(monkeypatch):
    _reset_prompt_state(monkeypatch)
    monkeypatch.setattr(settings, "AGENTA_ENABLED", True)
    monkeypatch.setattr(settings, "AGENTA_API_KEY", "test-api-key")
    monkeypatch.setattr(settings, "AGENTA_HOST", "https://cloud.agenta.ai")
    monkeypatch.setattr(
        settings,
        "AGENTA_PROMPT_REGISTRY",
        {
            "prompts/creative_analysis/ad_breakdown.md": {
                "app_slug": "ad-breakdown",
                "environment_slug": "production",
                "parameter_path": "template",
            }
        },
    )

    init_calls: list[int] = []
    registry_calls: list[dict[str, object]] = []

    class _FakeConfigManager:
        @staticmethod
        def get_from_registry(**kwargs):
            registry_calls.append(kwargs)
            return {"template": "Prompt text from Agenta"}

    fake_agenta_module = types.SimpleNamespace(
        init=lambda: init_calls.append(1),
        ConfigManager=_FakeConfigManager,
    )
    monkeypatch.setitem(sys.modules, "agenta", fake_agenta_module)

    text, sha = ad_breakdown.load_ad_breakdown_prompt()

    assert text == "Prompt text from Agenta"
    assert sha == hashlib.sha256("Prompt text from Agenta".encode("utf-8")).hexdigest()
    assert init_calls == [1]
    assert len(registry_calls) == 1
    assert registry_calls[0]["app_slug"] == "ad-breakdown"
    assert registry_calls[0]["environment_slug"] == "production"

    # Cached second call should not hit registry again.
    text_2, sha_2 = ad_breakdown.load_ad_breakdown_prompt()
    assert (text_2, sha_2) == (text, sha)
    assert len(registry_calls) == 1


def test_precanon_prompt_utils_fetches_from_agenta_registry(monkeypatch):
    _reset_prompt_state(monkeypatch)
    monkeypatch.setattr(settings, "AGENTA_ENABLED", True)
    monkeypatch.setattr(settings, "AGENTA_API_KEY", "test-api-key")
    monkeypatch.setattr(settings, "AGENTA_HOST", "https://cloud.agenta.ai")
    monkeypatch.setattr(
        settings,
        "AGENTA_PROMPT_REGISTRY",
        {
            "prompts/precanon_research/01_competitor_research.md": {
                "app_slug": "precanon-step-01",
                "variant_slug": "default",
                "parameter_path": "template",
            }
        },
    )

    class _FakeConfigManager:
        @staticmethod
        def get_from_registry(**_kwargs):
            return {"template": "Research prompt from Agenta"}

    fake_agenta_module = types.SimpleNamespace(
        init=lambda: None,
        ConfigManager=_FakeConfigManager,
    )
    monkeypatch.setitem(sys.modules, "agenta", fake_agenta_module)

    text, sha = prompt_utils.read_prompt_file("01_competitor_research.md")

    assert text == "Research prompt from Agenta"
    assert sha == hashlib.sha256("Research prompt from Agenta".encode("utf-8")).hexdigest()
