from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from typing import Any

import httpx

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
_AGENTA_API_URL: str | None = None
_AGENTA_TIMEOUT_SECONDS = 60.0


def agenta_enabled() -> bool:
    return bool(settings.AGENTA_ENABLED)


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


def _normalized_agenta_api_url() -> str:
    explicit_api_url = os.getenv("AGENTA_API_INTERNAL_URL") or os.getenv("AGENTA_API_URL")
    if explicit_api_url and explicit_api_url.strip():
        return explicit_api_url.strip().rstrip("/")

    host = str(settings.AGENTA_HOST).strip()
    if not host:
        raise AgentaConfigError(
            "AGENTA_ENABLED is true but AGENTA_HOST is not configured."
        )
    return f"{host.rstrip('/')}/api"


def initialize_agenta() -> None:
    global _AGENTA_API_URL, _AGENTA_INITIALIZED

    if _AGENTA_INITIALIZED:
        return
    if not agenta_enabled():
        return

    with _INIT_LOCK:
        if _AGENTA_INITIALIZED:
            return
        _validate_enabled_settings()
        _AGENTA_API_URL = _normalized_agenta_api_url()
        _AGENTA_INITIALIZED = True


def shutdown_agenta() -> None:
    """
    Placeholder for future client cleanup hooks.
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


def _reference_payload(
    *,
    slug: str | None = None,
    version: int | None = None,
    id: str | None = None,
) -> dict[str, Any] | None:
    if slug is None and version is None and id is None:
        return None

    payload: dict[str, Any] = {}
    if slug is not None:
        payload["slug"] = slug
    if version is not None:
        payload["version"] = version
    if id is not None:
        payload["id"] = id
    return payload


def _fetch_config_from_registry(reference: AgentaPromptReference) -> dict[str, Any]:
    initialize_agenta()

    if _AGENTA_API_URL is None:
        raise AgentaConfigError("Agenta client is not initialized.")

    request_body = {
        "variant_ref": _reference_payload(
            slug=reference.variant_slug,
            version=reference.variant_version,
        ),
        "environment_ref": _reference_payload(
            slug=reference.environment_slug,
            version=reference.environment_version,
        ),
        "application_ref": _reference_payload(slug=reference.app_slug),
    }

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_AGENTA_TIMEOUT_SECONDS,
        ) as client:
            response = client.post(
                f"{_AGENTA_API_URL}/variants/configs/fetch",
                headers={
                    "Authorization": str(settings.AGENTA_API_KEY),
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text.strip()
        raise AgentaConfigError(
            "Failed to fetch prompt config from Agenta registry "
            f"(app_slug={reference.app_slug}, variant_slug={reference.variant_slug}, "
            f"variant_version={reference.variant_version}, environment_slug={reference.environment_slug}, "
            f"environment_version={reference.environment_version}, status_code={exc.response.status_code}): "
            f"{body or exc}"
        ) from exc
    except httpx.HTTPError as exc:
        raise AgentaConfigError(
            "Failed to fetch prompt config from Agenta registry "
            f"(app_slug={reference.app_slug}, variant_slug={reference.variant_slug}, "
            f"variant_version={reference.variant_version}, environment_slug={reference.environment_slug}, "
            f"environment_version={reference.environment_version}): {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AgentaConfigError(
            "Agenta returned a non-JSON response while fetching prompt config "
            f"for app_slug={reference.app_slug}."
        ) from exc

    if not isinstance(payload, dict):
        raise AgentaConfigError(
            "Agenta returned an invalid config payload; expected an object response."
        )

    params = payload.get("params")
    if not isinstance(params, dict):
        raise AgentaConfigError(
            "Agenta returned an invalid config payload; expected object field 'params'."
        )
    return params


def _fetch_prompt_from_registry(reference: AgentaPromptReference) -> tuple[str, str]:
    config = _fetch_config_from_registry(reference)
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
