from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI

# Ensure API keys in .env are loaded even if app.config hasn't been imported yet.
_backend_root = Path(__file__).resolve().parents[2]
_repo_root = _backend_root.parent.parent
load_dotenv(_repo_root / ".env", override=False)
load_dotenv(_backend_root / ".env", override=False)


class LLMClientConfigError(Exception):
    pass


_STUB_OUTPUT = (
    "<SUMMARY>Stub summary generated locally for testing.</SUMMARY>"
    "<CONTENT>Stub content generated locally for testing.</CONTENT>"
)
_DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL") or "gpt-5.2-2025-12-11"
_DEFAULT_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
_MAX_RETRIES = int(os.getenv("LLM_REQUEST_RETRIES", "2"))
_O3_MAX_OUTPUT_TOKENS = int(os.getenv("O3_DEEP_RESEARCH_MAX_OUTPUT_TOKENS", "64000"))
_POLL_INTERVAL_SECONDS = int(os.getenv("LLM_POLL_INTERVAL_SECONDS", "15"))
_POLL_TIMEOUT_SECONDS = int(os.getenv("LLM_POLL_TIMEOUT_SECONDS", "1200"))


@dataclass
class LLMGenerationParams:
    model: str
    max_tokens: Optional[int] = None
    temperature: float = 0.2
    use_reasoning: bool = False
    use_web_search: bool = False


class LLMClient:
    """
    Lightweight stub/wrapper for LLM calls used by activities.
    Replace the generate_text implementation with a provider client as needed.
    """

    def __init__(self, default_model: Optional[str] = None) -> None:
        self.default_model = default_model or _DEFAULT_MODEL
        self._gemini_configured = False
        self._anthropic_client: Optional[Anthropic] = None
        self._openai_client: Optional[OpenAI] = None

    def generate_text(self, prompt: str, params: Optional[LLMGenerationParams] = None) -> str:
        model = params.model if params and params.model else self.default_model
        model = model or _DEFAULT_MODEL
        if self._is_openai_model(model):
            return self._generate_with_openai(prompt, model, params)
        if model.startswith("claude"):
            return self._generate_with_anthropic(prompt, model, params)
        return self._generate_with_gemini(prompt, model, params)

    def _is_openai_model(self, model: str) -> bool:
        lower = model.lower()
        prefixes = ("gpt-", "chatgpt-", "o1", "o3", "omni-")
        return any(lower.startswith(prefix) for prefix in prefixes)

    def _generate_with_openai(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return _STUB_OUTPUT

        if not self._openai_client:
            client_kwargs = {"api_key": api_key}
            base_url = os.getenv("OPENAI_BASE_URL")
            if base_url:
                client_kwargs["base_url"] = base_url
            self._openai_client = OpenAI(**client_kwargs)

        # Deep research needs background mode + polling for reliability and a higher token budget.
        if model.lower().startswith("o3-deep-research"):
            return self._generate_openai_deep_research(prompt, model, params)

        max_tokens = params.max_tokens if params and params.max_tokens else None
        temperature = params.temperature if params else 0.2
        use_reasoning = bool(params.use_reasoning) if params else False
        use_web_search = bool(params.use_web_search) if params else False
        should_use_responses = use_reasoning or use_web_search or model.lower().startswith("o")

        # Try the Responses API first when reasoning/web search is requested or for o-models.
        if should_use_responses:
            try:
                request_kwargs = {
                    "model": model,
                    "input": prompt,
                    "temperature": temperature,
                }
                if max_tokens:
                    request_kwargs["max_output_tokens"] = max_tokens
                if use_web_search:
                    request_kwargs["tools"] = [{"type": "web_search"}]
                if use_reasoning:
                    request_kwargs["reasoning"] = {"effort": "medium"}

                response = self._openai_client.responses.create(**request_kwargs)
                text = getattr(response, "output_text", None)
                if not text and getattr(response, "output", None):
                    try:
                        parts = []
                        for item in response.output:
                            content = getattr(item, "content", None)
                            if not content:
                                continue
                            for chunk in content:
                                maybe_text = getattr(chunk, "text", None)
                                if maybe_text:
                                    parts.append(maybe_text)
                        if parts:
                            text = "".join(parts)
                    except Exception:
                        text = None
                if text:
                    return text
            except Exception:
                # Fall back to chat completions when Responses API is unavailable.
                text = None

        try:
            completion = self._openai_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if completion and completion.choices:
                message = completion.choices[0].message
                text = getattr(message, "content", None)
            else:
                text = None
        except Exception:
            text = None

        return text or _STUB_OUTPUT

    def _generate_openai_deep_research(
        self, prompt: str, model: str, params: Optional[LLMGenerationParams]
    ) -> str:
        """
        Run o3-deep-research with background mode + polling.
        This avoids long-lived streams timing out and enables reasoning summaries + source capture.
        """
        max_output_tokens = params.max_tokens if params and params.max_tokens else _O3_MAX_OUTPUT_TOKENS
        use_web_search = bool(params.use_web_search) if params else False
        reasoning_effort = "medium"

        request_kwargs = {
            "model": model,
            "input": prompt,
            "background": True,
            "max_output_tokens": max_output_tokens,
            "reasoning": {"summary": "auto", "effort": reasoning_effort},
        }
        if use_web_search:
            request_kwargs["tools"] = [{"type": "web_search"}]
            request_kwargs["include"] = ["web_search_call.action.sources"]

        response = self._openai_client.responses.create(**request_kwargs)
        status = getattr(response, "status", None)
        response_id = getattr(response, "id", None)

        start = time.monotonic()
        while status in ("queued", "in_progress") and (time.monotonic() - start) < _POLL_TIMEOUT_SECONDS:
            time.sleep(_POLL_INTERVAL_SECONDS)
            response = self._openai_client.responses.retrieve(response_id)
            status = getattr(response, "status", None)

        # If we still don't have a terminal status, fall back to whatever we have.
        if status not in ("completed", "failed", "incomplete", "cancelled"):
            return getattr(response, "output_text", "") or _STUB_OUTPUT

        # Prefer the returned text even if the job is incomplete (e.g., hit max_output_tokens).
        text = getattr(response, "output_text", "") or ""
        if status == "completed":
            return text or _STUB_OUTPUT

        # If incomplete/failed/cancelled, return partial text when available to salvage work.
        return text or _STUB_OUTPUT

    def _generate_with_gemini(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return _STUB_OUTPUT

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
            text = None

        return text or _STUB_OUTPUT

    def _generate_with_anthropic(self, prompt: str, model: str, params: Optional[LLMGenerationParams]) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return _STUB_OUTPUT

        if not self._anthropic_client:
            self._anthropic_client = Anthropic(api_key=api_key)

        max_tokens = params.max_tokens if params and params.max_tokens else 4096
        temperature = params.temperature if params else 0.2
        timeout = _DEFAULT_TIMEOUT

        text = None
        for _ in range(max(1, _MAX_RETRIES)):
            try:
                response = self._anthropic_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=timeout,
                )
                text_parts = [content.text for content in response.content if getattr(content, "text", None)]
                text = "".join(text_parts) if text_parts else None
                if text:
                    break
            except Exception:
                text = None

        return text or _STUB_OUTPUT
