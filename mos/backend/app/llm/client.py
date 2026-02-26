from __future__ import annotations

from collections.abc import Iterator
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from anthropic import Anthropic
from dotenv import load_dotenv
try:
    import google.generativeai as genai
    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - environment-specific dependency issue
    genai = None
    _GENAI_IMPORT_ERROR = exc

from app.observability import (
    get_openai_client_class,
    start_langfuse_generation,
    start_langfuse_span,
)

# Ensure API keys in .env are loaded even if app.config hasn't been imported yet.
_backend_root = Path(__file__).resolve().parents[2]
_repo_root = _backend_root.parent.parent
load_dotenv(_repo_root / ".env", override=False)
# Backend-local env should win for backend processes (matches app.config behavior).
load_dotenv(_backend_root / ".env", override=True)


class LLMClientConfigError(Exception):
    pass


class OpenAIResponsePendingError(RuntimeError):
    def __init__(self, response_id: str, status: str, waited_seconds: float) -> None:
        message = (
            "OpenAI response still pending "
            f"(status={status}, waited_seconds={int(waited_seconds)}, response_id={response_id})"
        )
        super().__init__(message)
        self.response_id = response_id
        self.status = status
        self.waited_seconds = waited_seconds


logger = logging.getLogger(__name__)
_DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL") or "gpt-5.2-2025-12-11"
_DEFAULT_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
_MAX_RETRIES = int(os.getenv("LLM_REQUEST_RETRIES", "2"))
_O3_MAX_OUTPUT_TOKENS = int(os.getenv("O3_DEEP_RESEARCH_MAX_OUTPUT_TOKENS", "64000"))
_POLL_INTERVAL_SECONDS = int(os.getenv("LLM_POLL_INTERVAL_SECONDS", "15"))
_POLL_TIMEOUT_SECONDS = int(os.getenv("LLM_POLL_TIMEOUT_SECONDS", "3600"))
_ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"
_OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass
class LLMGenerationParams:
    model: str
    max_tokens: Optional[int] = None
    temperature: float = 0.2
    use_reasoning: bool = False
    use_web_search: bool = False
    response_format: Optional[dict[str, Any]] = None
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None


class LLMClient:
    """
    Lightweight wrapper for LLM calls used by activities.
    Routes to the appropriate provider client based on the requested model.
    """

    def __init__(self, default_model: Optional[str] = None) -> None:
        self.default_model = default_model or _DEFAULT_MODEL
        self._gemini_configured = False
        self._anthropic_client: Optional[Anthropic] = None
        self._openai_client: Optional[Any] = None
        self._openai_client_class = get_openai_client_class()

    def _ensure_openai_client(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMClientConfigError("OPENAI_API_KEY not configured")

        if self._openai_client:
            return

        client_kwargs = {
            "api_key": api_key,
            "timeout": float(_DEFAULT_TIMEOUT),
            "max_retries": _MAX_RETRIES,
            # Explicitly set base_url so wrappers cannot inherit malformed env defaults.
            "base_url": self._openai_base_url(),
        }
        self._openai_client = self._openai_client_class(**client_kwargs)

    @staticmethod
    def _openai_base_url() -> str:
        configured_base_url = os.getenv("OPENAI_BASE_URL")
        normalized_base_url = configured_base_url.strip() if isinstance(configured_base_url, str) else ""
        if not normalized_base_url:
            return _OPENAI_DEFAULT_BASE_URL

        parsed = urlparse(normalized_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LLMClientConfigError(
                "OPENAI_BASE_URL must be a fully qualified http(s) URL, e.g. "
                "'https://api.openai.com/v1'."
            )
        return normalized_base_url

    @staticmethod
    def _anthropic_base_url() -> str:
        configured_base_url = os.getenv("ANTHROPIC_API_BASE_URL")
        if configured_base_url is None:
            configured_base_url = os.getenv("ANTHROPIC_BASE_URL")
        normalized_base_url = configured_base_url.strip() if isinstance(configured_base_url, str) else ""
        return normalized_base_url or _ANTHROPIC_DEFAULT_BASE_URL

    def _ensure_anthropic_client(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMClientConfigError("ANTHROPIC_API_KEY not configured")

        if self._anthropic_client:
            return

        self._anthropic_client = Anthropic(
            api_key=api_key,
            base_url=self._anthropic_base_url(),
        )

    def _langfuse_metadata(
        self,
        *,
        operation: str,
        model: str,
        params: Optional[LLMGenerationParams],
        provider: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "provider": provider,
            "model": model,
            "operation": operation,
        }
        if params:
            metadata["temperature"] = params.temperature
            metadata["maxTokens"] = params.max_tokens
            metadata["useReasoning"] = bool(params.use_reasoning)
            metadata["useWebSearch"] = bool(params.use_web_search)
            if params.response_format is not None:
                metadata["hasResponseFormat"] = True
        return metadata

    @staticmethod
    def _extract_anthropic_usage(response: Any) -> dict[str, int] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None

        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", input_tokens)
            output_tokens = usage.get("output_tokens", output_tokens)

        usage_details: dict[str, int] = {}
        if isinstance(input_tokens, int):
            usage_details["input"] = input_tokens
        if isinstance(output_tokens, int):
            usage_details["output"] = output_tokens
        return usage_details or None

    @staticmethod
    def _extract_anthropic_text(response: Any) -> str | None:
        content_blocks = getattr(response, "content", None)
        if isinstance(content_blocks, list):
            text_parts: list[str] = []
            for block in content_blocks:
                block_text = getattr(block, "text", None)
                if isinstance(block_text, str) and block_text:
                    text_parts.append(block_text)
                    continue
                if isinstance(block, dict):
                    mapped_text = block.get("text")
                    if isinstance(mapped_text, str) and mapped_text:
                        text_parts.append(mapped_text)
            if text_parts:
                return "".join(text_parts)

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text:
            return output_text
        return None

    @staticmethod
    def _extract_gemini_usage(result: Any) -> dict[str, int] | None:
        usage = getattr(result, "usage_metadata", None)
        if usage is None:
            return None

        input_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        if isinstance(usage, dict):
            input_tokens = usage.get("prompt_token_count", input_tokens)
            output_tokens = usage.get("candidates_token_count", output_tokens)

        usage_details: dict[str, int] = {}
        if isinstance(input_tokens, int):
            usage_details["input"] = input_tokens
        if isinstance(output_tokens, int):
            usage_details["output"] = output_tokens
        return usage_details or None

    def generate_text(self, prompt: str, params: Optional[LLMGenerationParams] = None) -> str:
        model = params.model if params and params.model else self.default_model
        model = model or _DEFAULT_MODEL
        provider = "openai" if self._is_openai_model(model) else "anthropic" if model.startswith("claude") else "gemini"
        metadata = self._langfuse_metadata(
            operation="generate_text",
            model=model,
            params=params,
            provider=provider,
        )
        with start_langfuse_span(
            name="llm.generate_text",
            input={"prompt_chars": len(prompt)},
            metadata=metadata,
            tags=["llm", provider],
            trace_name="llm.workflow",
        ):
            if provider == "openai":
                return self._generate_with_openai(prompt, model, params)
            if provider == "anthropic":
                return self._generate_with_anthropic(prompt, model, params)
            return self._generate_with_gemini(prompt, model, params)

    def stream_text(self, prompt: str, params: Optional[LLMGenerationParams] = None) -> Iterator[str]:
        model = params.model if params and params.model else self.default_model
        model = model or _DEFAULT_MODEL
        provider = "openai" if self._is_openai_model(model) else "anthropic" if model.startswith("claude") else "gemini"
        metadata = self._langfuse_metadata(
            operation="stream_text",
            model=model,
            params=params,
            provider=provider,
        )
        with start_langfuse_span(
            name="llm.stream_text",
            input={"prompt_chars": len(prompt)},
            metadata=metadata,
            tags=["llm", provider, "stream"],
            trace_name="llm.workflow",
        ):
            if provider == "openai":
                yield from self._stream_with_openai(prompt, model, params)
                return
            if provider == "anthropic":
                yield from self._stream_with_anthropic(prompt, model, params)
                return

            # Other providers: fallback to a single non-streamed chunk for now.
            yield self.generate_text(prompt, params)

    def _is_openai_model(self, model: str) -> bool:
        lower = model.lower()
        prefixes = ("gpt-", "chatgpt-", "o", "omni-")
        return any(lower.startswith(prefix) for prefix in prefixes)

    def _extract_response_text(self, response: Any) -> Optional[str]:
        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text:
            return text

        maybe_output = getattr(response, "output", None)
        if maybe_output is None and isinstance(response, dict):
            maybe_output = response.get("output")
        if not maybe_output:
            return None

        def _chunk_text(chunk: Any) -> Optional[str]:
            if isinstance(chunk, str):
                return chunk
            if isinstance(chunk, dict):
                raw = chunk.get("text")
                if isinstance(raw, str) and raw:
                    return raw
                raw_output = chunk.get("output_text")
                if isinstance(raw_output, str) and raw_output:
                    return raw_output
                if isinstance(raw_output, dict):
                    nested_text = raw_output.get("text")
                    if isinstance(nested_text, str) and nested_text:
                        return nested_text
                refusal = chunk.get("refusal")
                if isinstance(refusal, str) and refusal:
                    return refusal
                return None
            raw_attr = getattr(chunk, "text", None)
            if isinstance(raw_attr, str) and raw_attr:
                return raw_attr
            refusal_attr = getattr(chunk, "refusal", None)
            if isinstance(refusal_attr, str) and refusal_attr:
                return refusal_attr
            return None

        try:
            parts: list[str] = []
            for item in maybe_output:
                content = getattr(item, "content", None)
                if content is None and isinstance(item, dict):
                    content = item.get("content")
                if isinstance(content, str) and content:
                    parts.append(content)
                    continue
                if not isinstance(content, list):
                    continue
                for chunk in content:
                    extracted = _chunk_text(chunk)
                    if extracted:
                        parts.append(extracted)
            return "".join(parts) if parts else None
        except Exception:
            return None

    @staticmethod
    def _openai_text_format_from_response_format(response_format: dict[str, Any]) -> dict[str, Any]:
        """Normalize Chat Completions `response_format` into Responses API `text.format`.

        OpenAI uses different shapes:
        - Chat Completions: {"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": ...}}
        - Responses API:    {"type": "json_schema", "name": ..., "schema": ..., "strict": ...}

        We accept either and validate required fields so we fail fast with a clear error.
        """

        if not isinstance(response_format, dict):
            raise TypeError(
                "response_format must be a dict compatible with OpenAI response formatting. "
                f"Received {type(response_format).__name__}."
            )

        fmt_type = response_format.get("type")
        if fmt_type != "json_schema":
            # For non-json_schema formats we pass through unchanged.
            return dict(response_format)

        # Chat Completions shape: {"type": "json_schema", "json_schema": {...}}
        json_schema = response_format.get("json_schema")
        if isinstance(json_schema, dict):
            name = json_schema.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    "OpenAI Responses API requires structured outputs to include `text.format.name`. "
                    "Expected response_format like {type: 'json_schema', json_schema: {name: <string>, schema: <object>}}."
                )
            schema = json_schema.get("schema")
            if not isinstance(schema, dict):
                raise ValueError(
                    "OpenAI Responses API requires structured outputs to include `text.format.schema` as a JSON schema object."
                )
            # Lift json_schema fields to the top-level for the Responses API.
            return {"type": "json_schema", **json_schema}

        # Responses API shape (already lifted): {"type": "json_schema", "name": ..., "schema": ...}
        name = response_format.get("name")
        schema = response_format.get("schema")
        if isinstance(name, str) and name.strip() and isinstance(schema, dict):
            return dict(response_format)

        raise ValueError(
            "Invalid json_schema response_format. Provide either Chat Completions shape "
            "{type: 'json_schema', json_schema: {name, schema, ...}} or Responses API shape "
            "{type: 'json_schema', name, schema, ...}."
        )

    def _normalize_openai_status(self, status: Any) -> Optional[str]:
        if status is None:
            return None
        if isinstance(status, str):
            return status
        value = getattr(status, "value", None)
        if isinstance(value, str):
            return value
        return str(status)

    def _extract_openai_usage(self, response: Any) -> dict[str, int] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None

        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        reasoning_tokens = getattr(usage, "reasoning_tokens", None)
        cached_input_tokens = getattr(usage, "cached_input_tokens", None)

        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", input_tokens)
            output_tokens = usage.get("output_tokens", output_tokens)
            total_tokens = usage.get("total_tokens", total_tokens)
            reasoning_tokens = usage.get("reasoning_tokens", reasoning_tokens)
            cached_input_tokens = usage.get("cached_input_tokens", cached_input_tokens)

        payload: dict[str, int] = {}
        if isinstance(input_tokens, int):
            payload["input_tokens"] = input_tokens
        if isinstance(output_tokens, int):
            payload["output_tokens"] = output_tokens
        if isinstance(total_tokens, int):
            payload["total_tokens"] = total_tokens
        if isinstance(reasoning_tokens, int):
            payload["reasoning_tokens"] = reasoning_tokens
        if isinstance(cached_input_tokens, int):
            payload["cached_input_tokens"] = cached_input_tokens
        return payload or None

    def _poll_openai_response(
        self,
        response_id: str,
        *,
        include: Optional[list[str]] = None,
        poll_timeout_seconds: Optional[int] = None,
        initial_response: Any = None,
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> str:
        if not response_id:
            raise RuntimeError("OpenAI responses API returned an empty response_id; cannot poll for output.")
        timeout_seconds = poll_timeout_seconds or _POLL_TIMEOUT_SECONDS
        response = initial_response
        last_pending_log_minute = -1
        if response is None:
            if include:
                response = self._openai_client.responses.retrieve(response_id, include=include)
            else:
                response = self._openai_client.responses.retrieve(response_id)
        status = self._normalize_openai_status(getattr(response, "status", None))
        text = self._extract_response_text(response)
        start = time.monotonic()
        pending_statuses = {"queued", "in_progress", None}

        def _emit_progress(
            *,
            current_status: str | None,
            elapsed_seconds: float,
            usage: dict[str, int] | None = None,
        ) -> None:
            if progress_callback is None:
                return
            payload: dict[str, Any] = {
                "response_id": response_id,
                "status": str(current_status or "unknown"),
                "elapsed_seconds": round(elapsed_seconds, 2),
            }
            if usage:
                payload.update(usage)
            progress_callback(payload)

        _emit_progress(current_status=status, elapsed_seconds=0.0)
        while True:
            if status in ("completed", None) and text:
                elapsed = time.monotonic() - start
                _emit_progress(
                    current_status=status,
                    elapsed_seconds=elapsed,
                    usage=self._extract_openai_usage(response),
                )
                logger.warning(
                    "OpenAI response completed "
                    f"(response_id={response_id}, status={status}, elapsed_seconds={round(elapsed, 2)}, "
                    f"text_chars={len(text)})",
                    extra={
                        "response_id": response_id,
                        "status": status,
                        "elapsed_seconds": round(elapsed, 2),
                        "text_chars": len(text),
                    },
                )
                return text
            if status == "incomplete":
                incomplete = getattr(response, "incomplete_details", None)
                reason = getattr(incomplete, "reason", None)
                if reason is None and isinstance(incomplete, dict):
                    reason = incomplete.get("reason")
                reason_str = str(reason or incomplete or "unknown")
                text_chars = len(text) if isinstance(text, str) else 0
                raise RuntimeError(
                    "OpenAI responses API returned incomplete output "
                    f"(status={status}, reason={reason_str}, response_id={response_id}, text_chars={text_chars})"
                )
            if status not in pending_statuses:
                break
            elapsed = time.monotonic() - start
            _emit_progress(current_status=status, elapsed_seconds=elapsed)
            elapsed_minute = int(elapsed // 60)
            if elapsed_minute >= 1 and elapsed_minute != last_pending_log_minute:
                last_pending_log_minute = elapsed_minute
                logger.warning(
                    "OpenAI response still pending "
                    f"(response_id={response_id}, status={status}, elapsed_seconds={round(elapsed, 2)}, "
                    f"timeout_seconds={timeout_seconds})",
                    extra={
                        "response_id": response_id,
                        "status": status,
                        "elapsed_seconds": round(elapsed, 2),
                        "timeout_seconds": timeout_seconds,
                    },
                )
            if elapsed >= timeout_seconds:
                raise OpenAIResponsePendingError(
                    response_id=response_id,
                    status=str(status or "unknown"),
                    waited_seconds=elapsed,
                )
            time.sleep(_POLL_INTERVAL_SECONDS)
            if include:
                response = self._openai_client.responses.retrieve(response_id, include=include)
            else:
                response = self._openai_client.responses.retrieve(response_id)
            status = self._normalize_openai_status(getattr(response, "status", None))
            text = self._extract_response_text(response)

        error = getattr(response, "error", None)
        incomplete = getattr(response, "incomplete_details", None)
        raise RuntimeError(
            "OpenAI responses API returned no content "
            f"(status={status}, response_id={response_id}, error={error}, incomplete_details={incomplete})"
        )

    def retrieve_openai_response_text(
        self,
        response_id: str,
        *,
        include: Optional[list[str]] = None,
        poll_timeout_seconds: Optional[int] = None,
    ) -> str:
        self._ensure_openai_client()

        return self._poll_openai_response(
            response_id,
            include=include,
            poll_timeout_seconds=poll_timeout_seconds,
        )

    def _generate_with_openai(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> str:
        self._ensure_openai_client()

        # Deep research needs background mode + polling for reliability and a higher token budget.
        if model.lower().startswith("o3-deep-research"):
            return self._generate_openai_deep_research(prompt, model, params)

        max_tokens = params.max_tokens if params and params.max_tokens else None
        temperature = params.temperature if params else 0.2
        use_reasoning = bool(params.use_reasoning) if params else False
        use_web_search = bool(params.use_web_search) if params else False
        response_format = params.response_format if params else None
        model_lower = model.lower()
        if use_web_search and "o3-mini" in model_lower:
            raise RuntimeError(f"Model {model} does not support web_search tools; choose a tool-capable model.")
        should_use_responses = use_reasoning or use_web_search or model.lower().startswith("o")

        # Use the Responses API for reasoning/web-search/o-models. Do NOT fall back; surface errors directly.
        if should_use_responses:
            logger.warning(
                "OpenAI responses request",
                extra={
                    "model": model,
                    "use_web_search": use_web_search,
                    "use_reasoning": use_reasoning,
                },
            )
            include = ["web_search_call.action.sources"] if use_web_search else None
            request_kwargs = {
                "model": model,
                "input": prompt,
                # Background mode prevents long-running calls from exhausting the HTTP timeout; we poll below.
                "background": True,
            }
            if max_tokens:
                request_kwargs["max_output_tokens"] = max_tokens
            if use_web_search:
                request_kwargs["tools"] = [{"type": "web_search"}]
                request_kwargs["include"] = include  # include sources per docs
            if use_reasoning:
                request_kwargs["reasoning"] = {"effort": "medium"}
            if response_format:
                request_kwargs["text"] = {
                    "format": self._openai_text_format_from_response_format(response_format)
                }

            response = self._openai_client.responses.create(**request_kwargs)
            response_id = getattr(response, "id", None)
            logger.warning(
                "OpenAI responses request created "
                f"(model={model}, response_id={response_id}, use_web_search={use_web_search}, "
                f"use_reasoning={use_reasoning})",
                extra={
                    "model": model,
                    "response_id": response_id,
                    "use_web_search": use_web_search,
                    "use_reasoning": use_reasoning,
                },
            )
            try:
                return self._poll_openai_response(
                    response_id,
                    include=include,
                    poll_timeout_seconds=_POLL_TIMEOUT_SECONDS,
                    initial_response=response,
                    progress_callback=params.progress_callback if params else None,
                )
            except OpenAIResponsePendingError:
                logger.warning(
                    "OpenAI response still pending after poll timeout",
                    extra={"model": model, "response_id": response_id},
                )
                raise

        logger.warning(
            "OpenAI chat completion request",
            extra={
                "model": model,
                "use_web_search": use_web_search,
                "use_reasoning": use_reasoning,
            },
        )
        completion_kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            completion_kwargs["temperature"] = temperature
        if max_tokens:
            completion_kwargs["max_tokens"] = max_tokens
        if response_format:
            completion_kwargs["response_format"] = response_format

        try:
            completion = self._openai_client.chat.completions.create(**completion_kwargs)
        except Exception:
            logger.exception("OpenAI chat completion failed", extra={"model": model})
            raise

        if completion and completion.choices:
            message = completion.choices[0].message
            text = getattr(message, "content", None)
        else:
            text = None

        if text:
            return text

        raise RuntimeError(f"OpenAI chat completion returned no content for model {model}")

    def _stream_with_openai(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> Iterator[str]:
        self._ensure_openai_client()

        if model.lower().startswith("o3-deep-research"):
            # Deep research is long-running; keep the more reliable polling flow.
            yield self._generate_openai_deep_research(prompt, model, params)
            return

        max_tokens = params.max_tokens if params and params.max_tokens else None
        temperature = params.temperature if params else 0.2
        use_reasoning = bool(params.use_reasoning) if params else False
        use_web_search = bool(params.use_web_search) if params else False
        response_format = params.response_format if params else None
        model_lower = model.lower()
        if use_web_search and "o3-mini" in model_lower:
            raise RuntimeError(f"Model {model} does not support web_search tools; choose a tool-capable model.")

        should_use_responses = use_reasoning or use_web_search or model_lower.startswith("o")

        if should_use_responses:
            include = ["web_search_call.action.sources"] if use_web_search else None
            request_kwargs = {
                "model": model,
                "input": prompt,
            }
            if max_tokens:
                request_kwargs["max_output_tokens"] = max_tokens
            # Some OpenAI Responses models reject `temperature`. Since our non-streaming Responses path
            # also omits temperature, keep the streaming path consistent to avoid hard 400s.
            if use_web_search:
                request_kwargs["tools"] = [{"type": "web_search"}]
                request_kwargs["include"] = include
            if use_reasoning:
                request_kwargs["reasoning"] = {"effort": "medium"}
            if response_format:
                request_kwargs["text"] = {
                    "format": self._openai_text_format_from_response_format(response_format)
                }

            saw_delta = False
            with self._openai_client.responses.stream(**request_kwargs) as stream:
                for event in stream:
                    event_type = getattr(event, "type", None)
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            saw_delta = True
                            yield delta
                        continue
                    if event_type == "response.output_text.done":
                        if not saw_delta:
                            text = getattr(event, "text", None)
                            if text:
                                yield text
                        continue
                    if event_type == "response.refusal.delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            yield delta
                        continue
                    if event_type == "response.error":
                        error = getattr(event, "error", None)
                        raise RuntimeError(str(error or "OpenAI streaming error"))
            return

        completion_kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            completion_kwargs["temperature"] = temperature
        if max_tokens:
            completion_kwargs["max_tokens"] = max_tokens
        if response_format:
            completion_kwargs["response_format"] = response_format

        with self._openai_client.chat.completions.stream(**completion_kwargs) as stream:
            for event in stream:
                if getattr(event, "type", None) == "content.delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        yield delta

    def _generate_openai_deep_research(
        self, prompt: str, model: str, params: Optional[LLMGenerationParams]
    ) -> str:
        """
        Run o3-deep-research with background mode + polling.
        This avoids long-lived streams timing out and enables reasoning summaries + source capture.
        """
        max_output_tokens = params.max_tokens if params and params.max_tokens else _O3_MAX_OUTPUT_TOKENS
        use_web_search = bool(params.use_web_search) if params else True
        reasoning_effort = "medium"

        tools = [{"type": "web_search"}] if use_web_search else []
        include = ["web_search_call.action.sources"] if use_web_search else None
        if not tools:
            raise ValueError(
                "Deep research requires at least one data source tool (e.g., web_search, file_search, or MCP). "
                "Enable use_web_search or supply another tool."
            )

        request_kwargs = {
            "model": model,
            "input": prompt,
            "background": True,
            "max_output_tokens": max_output_tokens,
            "reasoning": {"summary": "auto", "effort": reasoning_effort},
        }
        request_kwargs["tools"] = tools
        if include:
            request_kwargs["include"] = include

        response = self._openai_client.responses.create(**request_kwargs)
        response_id = getattr(response, "id", None)
        try:
            text = self._poll_openai_response(
                response_id,
                include=include,
                poll_timeout_seconds=_POLL_TIMEOUT_SECONDS,
                initial_response=response,
                progress_callback=params.progress_callback if params else None,
            )
        except OpenAIResponsePendingError:
            logger.warning(
                "OpenAI deep research response still pending after poll timeout",
                extra={"response_id": response_id},
            )
            raise

        if include:
            final_response = self._openai_client.responses.retrieve(response_id, include=include)
        else:
            final_response = self._openai_client.responses.retrieve(response_id)
        status = getattr(final_response, "status", None)
        if status != "completed":
            logger.warning(
                "OpenAI deep research response ended without completed status",
                extra={"status": status, "response_id": response_id},
            )
        return text

    def _generate_with_gemini(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> str:
        if genai is None:
            detail = str(_GENAI_IMPORT_ERROR) if _GENAI_IMPORT_ERROR else "unknown import error"
            raise LLMClientConfigError(
                "google-generativeai dependency is unavailable. "
                f"Fix dependency compatibility and retry. Original error: {detail}"
            )

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise LLMClientConfigError("GEMINI_API_KEY not configured")

        if not self._gemini_configured:
            genai.configure(api_key=api_key)
            self._gemini_configured = True

        generation_config = {
            "temperature": params.temperature if params else 0.2,
        }
        if params and params.max_tokens:
            generation_config["max_output_tokens"] = params.max_tokens

        model_name = model if model.startswith("models/") else f"models/{model}"
        model_client = genai.GenerativeModel(model_name=model_name, generation_config=generation_config)
        with start_langfuse_generation(
            name="llm.gemini.generate",
            model=model,
            input=prompt,
            metadata=self._langfuse_metadata(
                operation="generate_text",
                model=model,
                params=params,
                provider="gemini",
            ),
            model_parameters=generation_config,
            tags=["llm", "gemini"],
            trace_name="llm.workflow",
        ) as generation:
            try:
                result = model_client.generate_content(prompt, request_options={"timeout": 120})
                text = None
                if result and getattr(result, "candidates", None):
                    first = result.candidates[0]
                    if first and first.content and getattr(first.content, "parts", None):
                        parts = first.content.parts
                        if parts and getattr(parts[0], "text", None):
                            text = parts[0].text
                if not text and hasattr(result, "text"):
                    text = result.text
            except Exception:
                logger.exception("Gemini generation failed", extra={"model": model})
                raise

            if generation is not None:
                generation.update(
                    output=text,
                    usage_details=self._extract_gemini_usage(result),
                )

        if text:
            return text

        raise RuntimeError(f"Gemini returned no content for model {model}")

    def _generate_with_anthropic(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> str:
        self._ensure_anthropic_client()

        max_tokens = params.max_tokens if params and params.max_tokens else 4096
        temperature = params.temperature if params else 0.2
        timeout = _DEFAULT_TIMEOUT

        text = None
        last_error: Exception | None = None
        with start_langfuse_generation(
            name="llm.anthropic.generate",
            model=model,
            input=prompt,
            metadata=self._langfuse_metadata(
                operation="generate_text",
                model=model,
                params=params,
                provider="anthropic",
            ),
            model_parameters={"max_tokens": max_tokens, "temperature": temperature},
            tags=["llm", "anthropic"],
            trace_name="llm.workflow",
        ) as generation:
            for _ in range(max(1, _MAX_RETRIES)):
                try:
                    response = self._anthropic_client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        messages=[{"role": "user", "content": prompt}],
                        timeout=timeout,
                    )
                    text = self._extract_anthropic_text(response)
                    if text:
                        if generation is not None:
                            generation.update(
                                output=text,
                                usage_details=self._extract_anthropic_usage(response),
                            )
                        break
                    stop_reason = getattr(response, "stop_reason", None)
                    content_types = [
                        getattr(content, "type", type(content).__name__) for content in getattr(response, "content", [])
                    ]
                    last_error = RuntimeError(
                        "Anthropic response had no text content "
                        f"(stop_reason={stop_reason}, content_types={content_types})"
                    )
                except Exception as exc:
                    logger.exception("Anthropic generation attempt failed", extra={"model": model})
                    text = None
                    last_error = exc

        if text:
            return text

        if last_error is not None:
            raise RuntimeError(f"Anthropic generation failed for model {model}: {last_error}") from last_error
        raise RuntimeError(f"Anthropic returned no content for model {model}")

    def _stream_with_anthropic(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> Iterator[str]:
        self._ensure_anthropic_client()

        max_tokens = params.max_tokens if params and params.max_tokens else 4096
        temperature = params.temperature if params else 0.2
        timeout = _DEFAULT_TIMEOUT

        with start_langfuse_generation(
            name="llm.anthropic.stream",
            model=model,
            input=prompt,
            metadata=self._langfuse_metadata(
                operation="stream_text",
                model=model,
                params=params,
                provider="anthropic",
            ),
            model_parameters={"max_tokens": max_tokens, "temperature": temperature},
            tags=["llm", "anthropic", "stream"],
            trace_name="llm.workflow",
        ) as generation:
            streamed_parts: list[str] = []
            try:
                with self._anthropic_client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=timeout,
                ) as stream:
                    for text in stream.text_stream:
                        if text:
                            streamed_parts.append(text)
                            yield text
                    final = stream.get_final_message()
                    if generation is not None:
                        generation.update(
                            output="".join(streamed_parts) if streamed_parts else None,
                            usage_details=self._extract_anthropic_usage(final),
                        )
            except Exception:
                logger.exception("Anthropic streaming failed; falling back to non-stream", extra={"model": model})
                text = self._generate_with_anthropic(prompt, model, params)
                if generation is not None:
                    generation.update(output=text)
                if text:
                    yield text
