from __future__ import annotations

import hashlib
import importlib
import os
import threading
from dataclasses import dataclass
from typing import Any

from app.config import settings


class AgentaConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentaPromptReference:
    app_slug: str
    parameter_path: str
    variant_slug: str | None = None
    variant_version: int | None = None
    environment_slug: str | None = None
    environment_version: int | None = None


_INIT_LOCK = threading.Lock()
_PROMPT_CACHE_LOCK = threading.Lock()
_AGENTA_INITIALIZED = False
_PROMPT_CACHE: dict[AgentaPromptReference, tuple[str, str]] = {}


def agenta_enabled() -> bool:
    return bool(settings.AGENTA_ENABLED)


def _load_agenta_module() -> Any:
    try:
        return importlib.import_module("agenta")
    except Exception as exc:  # noqa: BLE001
        raise AgentaConfigError(
            "AGENTA_ENABLED is true but the `agenta` package is not available. "
            "Install dependency `agenta` and retry."
        ) from exc


def _validate_enabled_settings() -> None:
    if not settings.AGENTA_API_KEY:
        raise AgentaConfigError(
            "AGENTA_ENABLED is true but AGENTA_API_KEY is not configured."
        )
    if not settings.AGENTA_HOST:
        raise AgentaConfigError(
            "AGENTA_ENABLED is true but AGENTA_HOST is not configured."
        )
    if not isinstance(settings.AGENTA_PROMPT_REGISTRY, dict):
        raise AgentaConfigError(
            "AGENTA_PROMPT_REGISTRY must be a JSON object mapping prompt keys to Agenta references."
        )


def initialize_agenta() -> None:
    global _AGENTA_INITIALIZED

    if _AGENTA_INITIALIZED:
        return
    if not agenta_enabled():
        return

    with _INIT_LOCK:
        if _AGENTA_INITIALIZED:
            return
        _validate_enabled_settings()
        ag = _load_agenta_module()

        # The SDK reads auth/host from env.
        os.environ["AGENTA_API_KEY"] = str(settings.AGENTA_API_KEY)
        os.environ["AGENTA_HOST"] = str(settings.AGENTA_HOST)
        try:
            ag.init()
        except Exception as exc:  # noqa: BLE001
            raise AgentaConfigError(f"Failed to initialize Agenta SDK: {exc}") from exc
        _AGENTA_INITIALIZED = True


def shutdown_agenta() -> None:
    """
    Placeholder for future SDK cleanup hooks.
    """


def clear_prompt_cache() -> None:
    with _PROMPT_CACHE_LOCK:
        _PROMPT_CACHE.clear()


def _entry_for_prompt_key(prompt_key: str) -> dict[str, Any]:
    registry = settings.AGENTA_PROMPT_REGISTRY
    entry = registry.get(prompt_key)
    if entry is None:
        raise AgentaConfigError(
            "AGENTA_ENABLED is true but prompt key is missing from AGENTA_PROMPT_REGISTRY: "
            f"{prompt_key!r}."
        )
    if not isinstance(entry, dict):
        raise AgentaConfigError(
            "AGENTA_PROMPT_REGISTRY entry must be an object for prompt key "
            f"{prompt_key!r}."
        )
    return entry


def _required_string(entry: dict[str, Any], *, key: str, prompt_key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentaConfigError(
            f"AGENTA_PROMPT_REGISTRY[{prompt_key!r}] requires non-empty string field {key!r}."
        )
    return value.strip()


def _optional_string(entry: dict[str, Any], *, key: str, prompt_key: str) -> str | None:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AgentaConfigError(
            f"AGENTA_PROMPT_REGISTRY[{prompt_key!r}] field {key!r} must be a non-empty string when provided."
        )
    return value.strip()


def _optional_int(entry: dict[str, Any], *, key: str, prompt_key: str) -> int | None:
    value = entry.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentaConfigError(
            f"AGENTA_PROMPT_REGISTRY[{prompt_key!r}] field {key!r} must be an integer when provided."
        )
    return value


def _prompt_reference(prompt_key: str) -> AgentaPromptReference:
    entry = _entry_for_prompt_key(prompt_key)
    return AgentaPromptReference(
        app_slug=_required_string(entry, key="app_slug", prompt_key=prompt_key),
        parameter_path=_required_string(entry, key="parameter_path", prompt_key=prompt_key),
        variant_slug=_optional_string(entry, key="variant_slug", prompt_key=prompt_key),
        variant_version=_optional_int(entry, key="variant_version", prompt_key=prompt_key),
        environment_slug=_optional_string(entry, key="environment_slug", prompt_key=prompt_key),
        environment_version=_optional_int(entry, key="environment_version", prompt_key=prompt_key),
    )


def _resolve_parameter_path(payload: Any, parameter_path: str) -> Any:
    current = payload
    for segment in parameter_path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                raise AgentaConfigError(
                    f"Agenta config is missing parameter path segment {segment!r} in {parameter_path!r}."
                )
            current = current[segment]
            continue
        if isinstance(current, list):
            if not segment.isdigit():
                raise AgentaConfigError(
                    "Agenta parameter path attempted non-numeric segment on a list at "
                    f"{segment!r} for path {parameter_path!r}."
                )
            index = int(segment)
            if index < 0 or index >= len(current):
                raise AgentaConfigError(
                    f"Agenta parameter path index out of range at segment {segment!r} for path {parameter_path!r}."
                )
            current = current[index]
            continue
        raise AgentaConfigError(
            f"Agenta parameter path {parameter_path!r} cannot be resolved: encountered scalar at segment {segment!r}."
        )
    return current


def _fetch_prompt_from_registry(reference: AgentaPromptReference) -> tuple[str, str]:
    initialize_agenta()
    ag = _load_agenta_module()

    kwargs: dict[str, Any] = {"app_slug": reference.app_slug}
    if reference.variant_slug is not None:
        kwargs["variant_slug"] = reference.variant_slug
    if reference.variant_version is not None:
        kwargs["variant_version"] = reference.variant_version
    if reference.environment_slug is not None:
        kwargs["environment_slug"] = reference.environment_slug
    if reference.environment_version is not None:
        kwargs["environment_version"] = reference.environment_version

    try:
        config = ag.ConfigManager.get_from_registry(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise AgentaConfigError(
            "Failed to fetch prompt config from Agenta registry "
            f"(app_slug={reference.app_slug}, variant_slug={reference.variant_slug}, "
            f"variant_version={reference.variant_version}, environment_slug={reference.environment_slug}, "
            f"environment_version={reference.environment_version}): {exc}"
        ) from exc

    value = _resolve_parameter_path(config, reference.parameter_path)
    if not isinstance(value, str) or not value.strip():
        raise AgentaConfigError(
            "Resolved Agenta prompt value must be a non-empty string at parameter path "
            f"{reference.parameter_path!r}."
        )
    prompt_text = value
    prompt_sha = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    return prompt_text, prompt_sha


def fetch_prompt_text(prompt_key: str) -> tuple[str, str]:
    if not agenta_enabled():
        raise AgentaConfigError(
            "Attempted to fetch Agenta prompt while AGENTA_ENABLED is false."
        )

    reference = _prompt_reference(prompt_key)
    with _PROMPT_CACHE_LOCK:
        cached = _PROMPT_CACHE.get(reference)
        if cached is not None:
            return cached

    resolved = _fetch_prompt_from_registry(reference)
    with _PROMPT_CACHE_LOCK:
        _PROMPT_CACHE[reference] = resolved
    return resolved
