from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from langfuse import Langfuse
from openai import OpenAI as OpenAIClient

from app.config import settings


logger = logging.getLogger(__name__)


class LangfuseConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class LangfuseTraceContext:
    name: str
    session_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


_langfuse_client: Langfuse | None = None
_langfuse_initialized = False
_current_trace_context: ContextVar[LangfuseTraceContext | None] = ContextVar(
    "langfuse_trace_context",
    default=None,
)


def langfuse_enabled() -> bool:
    return bool(settings.LANGFUSE_ENABLED)


def _langfuse_runtime_environment() -> str:
    return settings.LANGFUSE_ENVIRONMENT or settings.ENVIRONMENT


def _langfuse_host() -> str:
    return settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST


def _validate_settings() -> None:
    if not settings.LANGFUSE_PUBLIC_KEY:
        raise LangfuseConfigError(
            "LANGFUSE_ENABLED is true but LANGFUSE_PUBLIC_KEY is not configured."
        )
    if not settings.LANGFUSE_SECRET_KEY:
        raise LangfuseConfigError(
            "LANGFUSE_ENABLED is true but LANGFUSE_SECRET_KEY is not configured."
        )
    sample_rate = float(settings.LANGFUSE_SAMPLE_RATE)
    if sample_rate < 0.0 or sample_rate > 1.0:
        raise LangfuseConfigError(
            "LANGFUSE_SAMPLE_RATE must be between 0.0 and 1.0."
        )


def initialize_langfuse() -> None:
    global _langfuse_client
    global _langfuse_initialized

    if _langfuse_initialized:
        return

    if not langfuse_enabled():
        if bool(settings.LANGFUSE_REQUIRED):
            raise LangfuseConfigError(
                "LANGFUSE_REQUIRED is true but LANGFUSE_ENABLED is false. "
                "Set LANGFUSE_ENABLED=true and configure Langfuse credentials."
            )
        _langfuse_initialized = True
        logger.info(
            "Langfuse tracing disabled",
            extra={
                "host": _langfuse_host(),
                "environment": _langfuse_runtime_environment(),
            },
        )
        return

    _validate_settings()
    kwargs: dict[str, Any] = {
        "public_key": settings.LANGFUSE_PUBLIC_KEY,
        "secret_key": settings.LANGFUSE_SECRET_KEY,
        "tracing_enabled": True,
        "environment": _langfuse_runtime_environment(),
        "release": settings.LANGFUSE_RELEASE,
        "sample_rate": float(settings.LANGFUSE_SAMPLE_RATE),
        "timeout": int(settings.LANGFUSE_TIMEOUT_SECONDS),
        "debug": bool(settings.LANGFUSE_DEBUG),
    }
    if settings.LANGFUSE_BASE_URL:
        kwargs["base_url"] = settings.LANGFUSE_BASE_URL
    else:
        kwargs["host"] = settings.LANGFUSE_HOST

    client = Langfuse(**kwargs)
    if bool(settings.LANGFUSE_AUTH_CHECK):
        try:
            auth_check_ok = bool(client.auth_check())
        except Exception as exc:  # noqa: BLE001
            raise LangfuseConfigError(
                "Langfuse auth check failed during initialization. "
                "Verify host/base URL and project API keys."
            ) from exc
        if not auth_check_ok:
            raise LangfuseConfigError(
                "Langfuse auth check returned false. "
                "Verify LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and host/base URL."
            )

    _langfuse_client = client
    _langfuse_initialized = True
    logger.info(
        "Langfuse initialized",
        extra={
            "host": _langfuse_host(),
            "environment": _langfuse_runtime_environment(),
            "sample_rate": settings.LANGFUSE_SAMPLE_RATE,
            "auth_check": bool(settings.LANGFUSE_AUTH_CHECK),
        },
    )


def get_langfuse_client() -> Langfuse | None:
    initialize_langfuse()
    if not langfuse_enabled():
        return None
    if _langfuse_client is None:
        raise LangfuseConfigError("Langfuse client is not initialized.")
    return _langfuse_client


def shutdown_langfuse() -> None:
    client = get_langfuse_client()
    if client is not None:
        client.shutdown()


def get_openai_client_class() -> type[OpenAIClient]:
    if langfuse_enabled():
        initialize_langfuse()
        from langfuse.openai import OpenAI as LangfuseOpenAI

        return LangfuseOpenAI
    return OpenAIClient


def get_current_trace_context() -> LangfuseTraceContext | None:
    return _current_trace_context.get()


@contextmanager
def bind_langfuse_trace_context(
    trace_context: LangfuseTraceContext | None,
) -> Iterator[None]:
    token = _current_trace_context.set(trace_context)
    try:
        yield
    finally:
        _current_trace_context.reset(token)


def _merge_metadata(
    base: dict[str, Any] | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    if base:
        merged.update(base)
    if extra:
        merged.update(extra)
    return merged or None


def _merge_tags(base: list[str] | None, extra: list[str] | None) -> list[str] | None:
    merged: list[str] = []
    for tag in base or []:
        if tag not in merged:
            merged.append(tag)
    for tag in extra or []:
        if tag not in merged:
            merged.append(tag)
    return merged or None


def _apply_trace_updates(
    *,
    client: Langfuse,
    default_trace_name: str | None,
    metadata: dict[str, Any] | None,
    tags: list[str] | None,
) -> None:
    ctx = get_current_trace_context()

    trace_name = ctx.name if ctx and ctx.name else default_trace_name
    session_id = ctx.session_id if ctx else None
    user_id = ctx.user_id if ctx else None
    merged_metadata = _merge_metadata(ctx.metadata if ctx else None, metadata)
    merged_tags = _merge_tags(ctx.tags if ctx else None, tags)

    if (
        trace_name is None
        and session_id is None
        and user_id is None
        and merged_metadata is None
        and merged_tags is None
    ):
        return

    client.update_current_trace(
        name=trace_name,
        session_id=session_id,
        user_id=user_id,
        metadata=merged_metadata,
        tags=merged_tags,
    )


@contextmanager
def start_langfuse_span(
    *,
    name: str,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    trace_name: str | None = None,
) -> Iterator[Any | None]:
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    with client.start_as_current_span(name=name, input=input, metadata=metadata) as span:
        _apply_trace_updates(
            client=client,
            default_trace_name=trace_name,
            metadata=metadata,
            tags=tags,
        )
        try:
            yield span
        except Exception as exc:  # noqa: BLE001
            span.update(level="ERROR", status_message=str(exc))
            raise


@contextmanager
def start_langfuse_generation(
    *,
    name: str,
    model: str,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
    model_parameters: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    trace_name: str | None = None,
) -> Iterator[Any | None]:
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    with client.start_as_current_generation(
        name=name,
        input=input,
        model=model,
        metadata=metadata,
        model_parameters=model_parameters,
    ) as generation:
        _apply_trace_updates(
            client=client,
            default_trace_name=trace_name,
            metadata=metadata,
            tags=tags,
        )
        try:
            yield generation
        except Exception as exc:  # noqa: BLE001
            generation.update(level="ERROR", status_message=str(exc))
            raise
