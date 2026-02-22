import pytest

from app.observability import langfuse as langfuse_module


@pytest.fixture(autouse=True)
def reset_langfuse_state() -> None:
    langfuse_module._langfuse_client = None
    langfuse_module._langfuse_initialized = False
    yield
    langfuse_module._langfuse_client = None
    langfuse_module._langfuse_initialized = False


def _configure_enabled_langfuse(monkeypatch: pytest.MonkeyPatch, *, auth_check: bool = True) -> None:
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_ENABLED", True)
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_REQUIRED", False)
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_BASE_URL", "https://example.langfuse.test")
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_HOST", "https://cloud.langfuse.com")
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_ENVIRONMENT", "test")
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_RELEASE", "test-release")
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_SAMPLE_RATE", 1.0)
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_DEBUG", False)
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_AUTH_CHECK", auth_check)


def test_initialize_langfuse_raises_when_required_but_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_ENABLED", False)
    monkeypatch.setattr(langfuse_module.settings, "LANGFUSE_REQUIRED", True)

    with pytest.raises(langfuse_module.LangfuseConfigError, match="LANGFUSE_REQUIRED is true"):
        langfuse_module.initialize_langfuse()


def test_initialize_langfuse_raises_when_auth_check_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_enabled_langfuse(monkeypatch, auth_check=True)

    class FakeLangfuse:
        def __init__(self, **_kwargs):
            pass

        def auth_check(self) -> bool:
            return False

    monkeypatch.setattr(langfuse_module, "Langfuse", FakeLangfuse)

    with pytest.raises(langfuse_module.LangfuseConfigError, match="auth check returned false"):
        langfuse_module.initialize_langfuse()
    assert langfuse_module._langfuse_initialized is False
    assert langfuse_module._langfuse_client is None


def test_initialize_langfuse_performs_auth_check_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_enabled_langfuse(monkeypatch, auth_check=True)
    auth_check_calls = {"count": 0}

    class FakeLangfuse:
        def __init__(self, **_kwargs):
            pass

        def auth_check(self) -> bool:
            auth_check_calls["count"] += 1
            return True

    monkeypatch.setattr(langfuse_module, "Langfuse", FakeLangfuse)

    langfuse_module.initialize_langfuse()
    assert auth_check_calls["count"] == 1
    assert langfuse_module._langfuse_initialized is True
    assert isinstance(langfuse_module._langfuse_client, FakeLangfuse)
