import asyncio
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import traceback
from typing import Callable, Awaitable
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import openai
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
from config import (
    ANTHROPIC_API_KEY,
    DEFAULT_VALIDATED_LOOP_MAX_ITERATIONS,
    GEMINI_API_KEY,
    IS_DEBUG_ENABLED,
    IS_PROD,
    MOS_IMPORT_MODEL_SLOT_1,
    MOS_IMPORT_MODEL_SLOT_2,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    REPLICATE_API_KEY,
)
from custom_types import InputMode, OrchestrationMode
from llm import (
    ANTHROPIC_MODELS,
    GEMINI_MODELS,
    Llm,
)
from loop.artifacts import ValidatedLoopArtifactStore
from loop.contracts import DesignSystemReuseMode, ReferenceBundle
from loop.orchestrator import ValidationLoopOrchestrator
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Literal,
    cast,
    get_args,
)
from openai.types.chat import ChatCompletionMessageParam

from utils import print_prompt_preview

# WebSocket message types
MessageType = Literal[
    "chunk",
    "status",
    "setCode",
    "error",
    "variantComplete",
    "variantError",
    "variantCount",
    "variantModels",
    "thinking",
    "assistant",
    "toolStart",
    "toolResult",
]
from prompts.pipeline import build_prompt_messages
from prompts.request_parsing import parse_prompt_content, parse_prompt_history
from prompts.prompt_types import PromptHistoryMessage, Stack, UserTurnInput
from agent.runner import Agent
from routes.model_choice_sets import (
    ALL_KEYS_MODELS_DEFAULT,
    ALL_KEYS_MODELS_TEXT_CREATE,
    ALL_KEYS_MODELS_UPDATE,
    ANTHROPIC_ONLY_MODELS,
    GEMINI_ANTHROPIC_MODELS,
    GEMINI_OPENAI_MODELS,
    GEMINI_ONLY_MODELS,
    OPENAI_ANTHROPIC_MODELS,
    OPENAI_ONLY_MODELS,
    VIDEO_VARIANT_MODELS,
)
from video import normalize_video_data_urls_for_llm

# from utils import pprint_prompt
from ws.constants import APP_ERROR_WEB_SOCKET_CODE  # type: ignore


router = APIRouter()


@dataclass
class PipelineContext:
    """Context object that carries state through the pipeline"""

    websocket: WebSocket
    ws_comm: "WebSocketCommunicator | None" = None
    params: Dict[str, Any] = field(default_factory=dict)
    extracted_params: "ExtractedParams | None" = None
    prompt_messages: List[ChatCompletionMessageParam] = field(default_factory=list)
    variant_models: List[Llm] = field(default_factory=list)
    completions: List[str] = field(default_factory=list)
    variant_completions: Dict[int, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def send_message(self):
        assert self.ws_comm is not None
        return self.ws_comm.send_message

    @property
    def throw_error(self):
        assert self.ws_comm is not None
        return self.ws_comm.throw_error


class Middleware(ABC):
    """Base class for all pipeline middleware"""

    @abstractmethod
    async def process(
        self, context: PipelineContext, next_func: Callable[[], Awaitable[None]]
    ) -> None:
        """Process the context and call the next middleware"""
        pass


class Pipeline:
    """Pipeline for processing WebSocket code generation requests"""

    def __init__(self):
        self.middlewares: List[Middleware] = []

    def use(self, middleware: Middleware) -> "Pipeline":
        """Add a middleware to the pipeline"""
        self.middlewares.append(middleware)
        return self

    async def execute(self, websocket: WebSocket) -> None:
        """Execute the pipeline with the given WebSocket"""
        context = PipelineContext(websocket=websocket)

        # Build the middleware chain
        async def start(ctx: PipelineContext):
            pass  # End of pipeline

        chain = start
        for middleware in reversed(self.middlewares):
            chain = self._wrap_middleware(middleware, chain)

        await chain(context)

    def _wrap_middleware(
        self,
        middleware: Middleware,
        next_func: Callable[[PipelineContext], Awaitable[None]],
    ) -> Callable[[PipelineContext], Awaitable[None]]:
        """Wrap a middleware with its next function"""

        async def wrapped(context: PipelineContext) -> None:
            await middleware.process(context, lambda: next_func(context))

        return wrapped


class WebSocketCommunicator:
    """Handles WebSocket communication with consistent error handling"""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.is_closed = False

    async def accept(self) -> None:
        """Accept the WebSocket connection"""
        await self.websocket.accept()
        print("Incoming websocket connection...")

    async def send_message(
        self,
        type: MessageType,
        value: str | None,
        variantIndex: int,
        data: Dict[str, Any] | None = None,
        eventId: str | None = None,
    ) -> None:
        """Send a message to the client with debug logging"""
        if self.is_closed:
            return

        # Print for debugging on the backend
        if type == "error":
            print(f"Error (variant {variantIndex + 1}): {value}")
        elif type == "status":
            print(f"Status (variant {variantIndex + 1}): {value}")
        elif type == "variantComplete":
            print(f"Variant {variantIndex + 1} complete")
        elif type == "variantError":
            print(f"Variant {variantIndex + 1} error: {value}")

        try:
            payload: Dict[str, Any] = {"type": type, "variantIndex": variantIndex}
            if value is not None:
                payload["value"] = value
            if data is not None:
                payload["data"] = data
            if eventId is not None:
                payload["eventId"] = eventId
            await self.websocket.send_json(payload)
        except (ConnectionClosedOK, ConnectionClosedError):
            print(f"WebSocket closed by client, skipping message: {type}")
            self.is_closed = True

    async def throw_error(self, message: str) -> None:
        """Send an error message and close the connection"""
        print(message)
        if not self.is_closed:
            try:
                await self.websocket.send_json({"type": "error", "value": message})
                await self.websocket.close(APP_ERROR_WEB_SOCKET_CODE)
            except (ConnectionClosedOK, ConnectionClosedError):
                print("WebSocket already closed by client")
            self.is_closed = True

    async def receive_params(self) -> Dict[str, Any]:
        """Receive parameters from the client"""
        try:
            params: Dict[str, Any] = await self.websocket.receive_json()
            print("Received params")
            return params
        except WebSocketDisconnect as exc:
            print(
                "[GENERATE_CODE] Client disconnected before request payload was fully received "
                f"(code={exc.code})."
            )
            raise

    async def close(self) -> None:
        """Close the WebSocket connection"""
        if not self.is_closed:
            try:
                await self.websocket.close()
            except (ConnectionClosedOK, ConnectionClosedError):
                pass  # Already closed by client
            self.is_closed = True


@dataclass
class ExtractedParams:
    stack: Stack
    input_mode: InputMode
    should_generate_images: bool
    openai_api_key: str | None
    anthropic_api_key: str | None
    gemini_api_key: str | None
    openai_base_url: str | None
    generation_type: Literal["create", "update"]
    prompt: UserTurnInput
    history: List[PromptHistoryMessage]
    file_state: Dict[str, str] | None
    option_codes: List[str]
    request_source: Literal["standard", "mos_import"] = "standard"
    model_slots: List[int] | None = None
    orchestration_mode: OrchestrationMode = "standard"
    max_validation_iterations: int = DEFAULT_VALIDATED_LOOP_MAX_ITERATIONS
    validated_loop_reference_run_dir: str | None = None
    validated_loop_design_system_mode: DesignSystemReuseMode = "generate"
    validated_loop_design_system_run_dir: str | None = None


class ParameterExtractionStage:
    """Handles parameter extraction and validation from WebSocket requests"""

    def __init__(self, throw_error: Callable[[str], Coroutine[Any, Any, None]]):
        self.throw_error = throw_error

    async def extract_and_validate(self, params: Dict[str, Any]) -> ExtractedParams:
        """Extract and validate all parameters from the request"""
        # Read the code config settings (stack) from the request.
        generated_code_config = params.get("generatedCodeConfig", "")
        if generated_code_config not in get_args(Stack):
            await self.throw_error(
                f"Invalid generated code config: {generated_code_config}"
            )
            raise ValueError(f"Invalid generated code config: {generated_code_config}")
        validated_stack = cast(Stack, generated_code_config)

        # Validate the input mode
        input_mode = params.get("inputMode")
        if input_mode not in get_args(InputMode):
            await self.throw_error(f"Invalid input mode: {input_mode}")
            raise ValueError(f"Invalid input mode: {input_mode}")
        validated_input_mode = cast(InputMode, input_mode)

        openai_api_key = self._get_from_settings_dialog_or_env(
            params, "openAiApiKey", OPENAI_API_KEY
        )

        # If neither is provided, we throw an error later only if Claude is used.
        anthropic_api_key = self._get_from_settings_dialog_or_env(
            params, "anthropicApiKey", ANTHROPIC_API_KEY
        )
        gemini_api_key = self._get_from_settings_dialog_or_env(
            params, "geminiApiKey", GEMINI_API_KEY
        )

        # Base URL for OpenAI API
        openai_base_url: str | None = None
        # Disable user-specified OpenAI Base URL in prod
        if not IS_PROD:
            openai_base_url = self._get_from_settings_dialog_or_env(
                params, "openAiBaseURL", OPENAI_BASE_URL
            )
        if not openai_base_url:
            print("Using official OpenAI URL")

        # Get the image generation flag from the request. Fall back to True if not provided.
        should_generate_images = bool(params.get("isImageGenerationEnabled", True))

        # Extract and validate generation type
        generation_type = params.get("generationType", "create")
        if generation_type not in ["create", "update"]:
            await self.throw_error(f"Invalid generation type: {generation_type}")
            raise ValueError(f"Invalid generation type: {generation_type}")
        generation_type = cast(Literal["create", "update"], generation_type)

        orchestration_mode = params.get("orchestrationMode", "standard")
        if orchestration_mode not in get_args(OrchestrationMode):
            await self.throw_error(f"Invalid orchestration mode: {orchestration_mode}")
            raise ValueError(f"Invalid orchestration mode: {orchestration_mode}")
        validated_orchestration_mode = cast(OrchestrationMode, orchestration_mode)

        raw_max_validation_iterations = params.get(
            "maxValidationIterations",
            DEFAULT_VALIDATED_LOOP_MAX_ITERATIONS,
        )
        if (
            isinstance(raw_max_validation_iterations, int)
            and not isinstance(raw_max_validation_iterations, bool)
            and raw_max_validation_iterations > 0
        ):
            max_validation_iterations = raw_max_validation_iterations
        else:
            max_validation_iterations = DEFAULT_VALIDATED_LOOP_MAX_ITERATIONS

        raw_validated_loop_reference_run_dir = params.get(
            "validatedLoopReferenceRunDir"
        )
        validated_loop_reference_run_dir = (
            raw_validated_loop_reference_run_dir
            if isinstance(raw_validated_loop_reference_run_dir, str)
            and raw_validated_loop_reference_run_dir.strip()
            else None
        )

        raw_design_system_mode = params.get(
            "validatedLoopDesignSystemMode",
            "generate",
        )
        design_system_mode_aliases: dict[str, DesignSystemReuseMode] = {
            "generate": "generate",
            "fresh": "generate",
            "reuse_if_available": "reuse_if_available",
            "reuse": "reuse_if_available",
            "require_reuse": "require_reuse",
        }
        if isinstance(raw_design_system_mode, str):
            normalized_design_system_mode = design_system_mode_aliases.get(
                raw_design_system_mode.strip().lower()
            )
            if normalized_design_system_mode is None:
                await self.throw_error(
                    "Invalid validated loop design-system mode: "
                    f"{raw_design_system_mode}"
                )
                raise ValueError(
                    "Invalid validated loop design-system mode: "
                    f"{raw_design_system_mode}"
                )
        else:
            await self.throw_error(
                "Invalid validated loop design-system mode: expected a string value."
            )
            raise ValueError(
                "Invalid validated loop design-system mode: expected a string value."
            )

        raw_design_system_run_dir = params.get("validatedLoopDesignSystemRunDir")
        validated_loop_design_system_run_dir = (
            raw_design_system_run_dir
            if isinstance(raw_design_system_run_dir, str)
            and raw_design_system_run_dir.strip()
            else None
        )

        # Extract prompt content
        prompt: UserTurnInput = parse_prompt_content(params.get("prompt"))

        # Extract history (default to empty list)
        history: List[PromptHistoryMessage] = parse_prompt_history(
            params.get("history")
        )

        # Extract file state for agent edits
        raw_file_state = params.get("fileState")
        file_state: Dict[str, str] | None = None
        if isinstance(raw_file_state, dict):
            content = raw_file_state.get("content")
            if isinstance(content, str) and content.strip():
                path = raw_file_state.get("path") or "index.html"
                file_state = {"path": path, "content": content}

        raw_option_codes = params.get("optionCodes")
        option_codes: List[str] = []
        if isinstance(raw_option_codes, list):
            for entry in raw_option_codes:
                if isinstance(entry, str):
                    option_codes.append(entry)
                elif entry is None:
                    option_codes.append("")
                else:
                    option_codes.append(str(entry))

        raw_request_source = params.get("requestSource", "standard")
        if raw_request_source not in {"standard", "mos_import"}:
            await self.throw_error(f"Invalid request source: {raw_request_source}")
            raise ValueError(f"Invalid request source: {raw_request_source}")
        request_source = cast(Literal["standard", "mos_import"], raw_request_source)

        model_slots: List[int] | None = None
        if request_source == "mos_import":
            raw_model_slots = params.get("modelSlots")
            if not isinstance(raw_model_slots, list) or len(raw_model_slots) == 0:
                await self.throw_error(
                    "MOS import requests must provide a non-empty modelSlots array."
                )
                raise ValueError(
                    "MOS import requests must provide a non-empty modelSlots array."
                )

            validated_slots: List[int] = []
            for raw_slot in raw_model_slots:
                if not isinstance(raw_slot, int) or isinstance(raw_slot, bool):
                    await self.throw_error(
                        "MOS import modelSlots must be integers containing only slots 1 and/or 2."
                    )
                    raise ValueError(
                        "MOS import modelSlots must be integers containing only slots 1 and/or 2."
                    )
                if raw_slot not in {1, 2}:
                    await self.throw_error(
                        f"Unsupported MOS import model slot: {raw_slot}. Only slots 1 and 2 are allowed."
                    )
                    raise ValueError(
                        f"Unsupported MOS import model slot: {raw_slot}. Only slots 1 and 2 are allowed."
                    )
                if raw_slot in validated_slots:
                    await self.throw_error(
                        f"Duplicate MOS import model slot: {raw_slot}. Provide each slot at most once."
                    )
                    raise ValueError(
                        f"Duplicate MOS import model slot: {raw_slot}. Provide each slot at most once."
                    )
                validated_slots.append(raw_slot)

            model_slots = validated_slots

        return ExtractedParams(
            stack=validated_stack,
            input_mode=validated_input_mode,
            should_generate_images=should_generate_images,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            openai_base_url=openai_base_url,
            generation_type=generation_type,
            prompt=prompt,
            history=history,
            file_state=file_state,
            option_codes=option_codes,
            request_source=request_source,
            model_slots=model_slots,
            orchestration_mode=validated_orchestration_mode,
            max_validation_iterations=max_validation_iterations,
            validated_loop_reference_run_dir=validated_loop_reference_run_dir,
            validated_loop_design_system_mode=normalized_design_system_mode,
            validated_loop_design_system_run_dir=validated_loop_design_system_run_dir,
        )

    def _get_from_settings_dialog_or_env(
        self, params: dict[str, Any], key: str, env_var: str | None
    ) -> str | None:
        """Get value from client settings or environment variable"""
        value = params.get(key)
        if value:
            print(f"Using {key} from client-side settings dialog")
            return value

        if env_var:
            print(f"Using {key} from environment variable")
            return env_var

        return None


class ModelSelectionStage:
    """Handles selection of variant models based on available API keys and generation type"""

    def __init__(self, throw_error: Callable[[str], Coroutine[Any, Any, None]]):
        self.throw_error = throw_error

    async def select_models(
        self,
        generation_type: Literal["create", "update"],
        input_mode: InputMode,
        openai_api_key: str | None,
        anthropic_api_key: str | None,
        gemini_api_key: str | None = None,
        request_source: Literal["standard", "mos_import"] = "standard",
        model_slots: List[int] | None = None,
    ) -> List[Llm]:
        """Select appropriate models based on available API keys"""
        try:
            if request_source == "mos_import":
                variant_models = self._get_mos_import_models(
                    model_slots=model_slots,
                    anthropic_api_key=anthropic_api_key,
                    gemini_api_key=gemini_api_key,
                )
            else:
                variant_models = self._get_variant_models(
                    generation_type,
                    input_mode,
                    1,
                    openai_api_key,
                    anthropic_api_key,
                    gemini_api_key,
                )

            # Print the variant models (one per line)
            print("Variant models:")
            for index, model in enumerate(variant_models):
                print(f"Variant {index + 1}: {model.value}")

            return variant_models
        except ValueError as exc:
            await self.throw_error(str(exc))
            raise
        except Exception:
            await self.throw_error(
                "No OpenAI, Anthropic, or Gemini API key found. Please add the environment variable "
                "OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY to backend/.env or in the settings dialog. "
                "If you add it to .env, make sure to restart the backend server."
            )
            raise Exception("No API key")

    def _get_variant_models(
        self,
        generation_type: Literal["create", "update"],
        input_mode: InputMode,
        num_variants: int,
        openai_api_key: str | None,
        anthropic_api_key: str | None,
        gemini_api_key: str | None,
    ) -> List[Llm]:
        """Simple model cycling that scales with num_variants"""

        # Video mode requires Gemini. The app now runs a single generation flow.
        if input_mode == "video":
            if not gemini_api_key:
                raise Exception(
                    "Video mode requires a Gemini API key. "
                    "Please add GEMINI_API_KEY to backend/.env or in the settings dialog"
                )
            return [VIDEO_VARIANT_MODELS[0]]

        # Define models based on available API keys
        if gemini_api_key and anthropic_api_key and openai_api_key:
            if input_mode == "text" and generation_type == "create":
                models = list(ALL_KEYS_MODELS_TEXT_CREATE)
            elif generation_type == "update":
                models = list(ALL_KEYS_MODELS_UPDATE)
            else:
                models = list(ALL_KEYS_MODELS_DEFAULT)
        elif gemini_api_key and anthropic_api_key:
            models = list(GEMINI_ANTHROPIC_MODELS)
        elif gemini_api_key and openai_api_key:
            models = list(GEMINI_OPENAI_MODELS)
        elif openai_api_key and anthropic_api_key:
            models = list(OPENAI_ANTHROPIC_MODELS)
        elif gemini_api_key:
            models = list(GEMINI_ONLY_MODELS)
        elif anthropic_api_key:
            models = list(ANTHROPIC_ONLY_MODELS)
        elif openai_api_key:
            models = list(OPENAI_ONLY_MODELS)
        else:
            raise Exception("No OpenAI or Anthropic key")

        # Cycle through models: [A, B] with num=5 becomes [A, B, A, B, A]
        selected_models: List[Llm] = []
        for i in range(num_variants):
            selected_models.append(models[i % len(models)])

        return selected_models

    def _get_mos_import_models(
        self,
        *,
        model_slots: List[int] | None,
        anthropic_api_key: str | None,
        gemini_api_key: str | None,
    ) -> List[Llm]:
        if not model_slots:
            raise ValueError(
                "MOS import requests must provide at least one explicit model slot."
            )

        slot_models = {
            1: MOS_IMPORT_MODEL_SLOT_1,
            2: MOS_IMPORT_MODEL_SLOT_2,
        }
        selected_models: List[Llm] = []
        for slot in model_slots:
            if slot not in slot_models:
                raise ValueError(
                    f"Unsupported MOS import model slot: {slot}. Only slots 1 and 2 are allowed."
                )

            model = slot_models[slot]
            if model in GEMINI_MODELS and not gemini_api_key:
                raise ValueError(
                    f"MOS import slot {slot} requires GEMINI_API_KEY for model {model.value}."
                )
            if model in ANTHROPIC_MODELS and not anthropic_api_key:
                raise ValueError(
                    f"MOS import slot {slot} requires ANTHROPIC_API_KEY for model {model.value}."
                )
            selected_models.append(model)

        return selected_models


class PromptCreationStage:
    """Handles prompt assembly for code generation"""

    def __init__(self, throw_error: Callable[[str], Coroutine[Any, Any, None]]):
        self.throw_error = throw_error

    async def build_prompt_messages(
        self,
        extracted_params: ExtractedParams,
    ) -> List[ChatCompletionMessageParam]:
        """Create prompt messages"""
        try:
            prompt_messages = await build_prompt_messages(
                stack=extracted_params.stack,
                input_mode=extracted_params.input_mode,
                generation_type=extracted_params.generation_type,
                prompt=extracted_params.prompt,
                history=extracted_params.history,
                file_state=extracted_params.file_state,
                image_generation_enabled=extracted_params.should_generate_images,
            )
            print_prompt_preview(prompt_messages)

            return prompt_messages
        except Exception:
            await self.throw_error(
                "Error assembling prompt. Contact support at support@picoapps.xyz"
            )
            raise


class PostProcessingStage:
    """Handles post-processing after code generation completes"""

    def __init__(self):
        pass

    async def process_completions(
        self,
        completions: List[str],
        websocket: WebSocket,
    ) -> None:
        """Process completions and perform cleanup."""
        return None


class AgenticGenerationStage:
    """Handles agent tool-calling generation for each variant."""

    def __init__(
        self,
        send_message: Callable[
            [MessageType, str | None, int, Dict[str, Any] | None, str | None],
            Coroutine[Any, Any, None],
        ],
        openai_api_key: str | None,
        openai_base_url: str | None,
        anthropic_api_key: str | None,
        gemini_api_key: str | None,
        should_generate_images: bool,
        file_state: Dict[str, str] | None,
        option_codes: List[str] | None,
    ):
        self.send_message = send_message
        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self.anthropic_api_key = anthropic_api_key
        self.gemini_api_key = gemini_api_key
        self.should_generate_images = should_generate_images
        self.file_state = file_state
        self.option_codes = option_codes or []

    async def process_variants(
        self,
        variant_models: List[Llm],
        prompt_messages: List[ChatCompletionMessageParam],
    ) -> Dict[int, str]:
        tasks: List[asyncio.Task[str]] = []
        for index, model in enumerate(variant_models):
            tasks.append(
                asyncio.create_task(self._run_variant(index, model, prompt_messages))
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        variant_completions: Dict[int, str] = {}
        for index, result in enumerate(results):
            if isinstance(result, BaseException):
                print(f"Variant {index + 1} failed: {result}")
                continue
            if result:
                variant_completions[index] = result

        return variant_completions

    async def _run_variant(
        self,
        index: int,
        model: Llm,
        prompt_messages: List[ChatCompletionMessageParam],
    ) -> str:
        try:

            async def send_runner_message(
                type: str,
                value: str | None,
                variant_index: int,
                data: Dict[str, Any] | None,
                event_id: str | None,
            ) -> None:
                await self.send_message(
                    cast(MessageType, type),
                    value,
                    variant_index,
                    data,
                    event_id,
                )

            runner = Agent(
                send_message=send_runner_message,
                variant_index=index,
                openai_api_key=self.openai_api_key,
                openai_base_url=self.openai_base_url,
                anthropic_api_key=self.anthropic_api_key,
                gemini_api_key=self.gemini_api_key,
                should_generate_images=self.should_generate_images,
                initial_file_state=self.file_state,
                option_codes=self.option_codes,
            )
            completion = await runner.run(model, prompt_messages)
            if completion:
                await self.send_message("setCode", completion, index, None, None)
            await self.send_message(
                "variantComplete",
                "Variant generation complete",
                index,
                None,
                None,
            )
            return completion
        except openai.AuthenticationError as e:
            print(f"[VARIANT {index + 1}] OpenAI Authentication failed", e)
            error_message = (
                "Incorrect OpenAI key. Please make sure your OpenAI API key is correct, "
                "or create a new OpenAI API key on your OpenAI dashboard."
                + (
                    " Alternatively, you can purchase code generation credits directly on this website."
                    if IS_PROD
                    else ""
                )
            )
            await self.send_message("variantError", error_message, index, None, None)
            return ""
        except openai.NotFoundError as e:
            print(f"[VARIANT {index + 1}] OpenAI Model not found", e)
            error_message = (
                e.message
                + ". Please make sure you have followed the instructions correctly to obtain "
                "an OpenAI key with GPT vision access: "
                "https://github.com/abi/screenshot-to-code/blob/main/Troubleshooting.md"
                + (
                    " Alternatively, you can purchase code generation credits directly on this website."
                    if IS_PROD
                    else ""
                )
            )
            await self.send_message("variantError", error_message, index, None, None)
            return ""
        except openai.RateLimitError as e:
            print(f"[VARIANT {index + 1}] OpenAI Rate limit exceeded", e)
            error_message = (
                "OpenAI error - 'You exceeded your current quota, please check your plan and billing details.'"
                + (
                    " Alternatively, you can purchase code generation credits directly on this website."
                    if IS_PROD
                    else ""
                )
            )
            await self.send_message("variantError", error_message, index, None, None)
            return ""
        except Exception as e:
            print(f"Error in variant {index + 1}: {e}")
            traceback.print_exception(type(e), e, e.__traceback__)
            await self.send_message("variantError", str(e), index, None, None)
            return ""


# Pipeline Middleware Implementations


class WebSocketSetupMiddleware(Middleware):
    """Handles WebSocket setup and teardown"""

    async def process(
        self, context: PipelineContext, next_func: Callable[[], Awaitable[None]]
    ) -> None:
        # Create and setup WebSocket communicator
        context.ws_comm = WebSocketCommunicator(context.websocket)
        await context.ws_comm.accept()

        try:
            await next_func()
        finally:
            # Always close the WebSocket
            await context.ws_comm.close()


class ParameterExtractionMiddleware(Middleware):
    """Handles parameter extraction and validation"""

    async def process(
        self, context: PipelineContext, next_func: Callable[[], Awaitable[None]]
    ) -> None:
        # Receive parameters
        assert context.ws_comm is not None
        context.params = await context.ws_comm.receive_params()

        # Extract and validate
        param_extractor = ParameterExtractionStage(context.throw_error)
        context.extracted_params = await param_extractor.extract_and_validate(
            context.params
        )

        # Log what we're generating
        print(
            f"Generating {context.extracted_params.stack} code in {context.extracted_params.input_mode} mode"
        )

        await next_func()


class StatusBroadcastMiddleware(Middleware):
    """Sends initial status messages to all variants"""

    async def process(
        self, context: PipelineContext, next_func: Callable[[], Awaitable[None]]
    ) -> None:
        # The app now uses a single generation flow across all orchestration modes.
        num_variants = 1

        # Tell frontend how many variants we're using
        await context.send_message("variantCount", str(num_variants), 0)

        for i in range(num_variants):
            await context.send_message("status", "Generating code...", i)

        await next_func()


class PromptCreationMiddleware(Middleware):
    """Handles prompt creation"""

    async def process(
        self, context: PipelineContext, next_func: Callable[[], Awaitable[None]]
    ) -> None:
        assert context.extracted_params is not None
        if context.extracted_params.orchestration_mode == "validated_loop":
            await next_func()
            return

        prompt_creator = PromptCreationStage(context.throw_error)
        context.prompt_messages = await prompt_creator.build_prompt_messages(
            context.extracted_params,
        )
        await next_func()


class CodeGenerationMiddleware(Middleware):
    """Handles the main code generation logic"""

    async def process(
        self, context: PipelineContext, next_func: Callable[[], Awaitable[None]]
    ) -> None:
        try:
            assert context.extracted_params is not None

            if (
                context.extracted_params.input_mode == "video"
                and context.extracted_params.prompt["videos"]
            ):
                await context.send_message(
                    "status",
                    "Normalizing uploaded video for Gemini.",
                    0,
                    None,
                    None,
                )
                context.extracted_params.prompt["videos"] = await asyncio.to_thread(
                    normalize_video_data_urls_for_llm,
                    context.extracted_params.prompt["videos"],
                )

            if context.extracted_params.orchestration_mode == "validated_loop":
                if not context.extracted_params.gemini_api_key:
                    await context.throw_error(
                        "Validated loop mode requires a Gemini API key. "
                        "Please add GEMINI_API_KEY to backend/.env or in the settings dialog."
                    )
                    return
                reference_bundle: ReferenceBundle
                resume_state = None
                prompt_has_reference_media = bool(
                    context.extracted_params.prompt["images"]
                    or context.extracted_params.prompt["videos"]
                )
                if (
                    not prompt_has_reference_media
                    and context.extracted_params.validated_loop_reference_run_dir
                ):
                    reference_bundle = ValidatedLoopArtifactStore.load_reference_bundle(
                        context.extracted_params.validated_loop_reference_run_dir
                    )
                    resume_state = ValidatedLoopArtifactStore.load_resume_state(
                        context.extracted_params.validated_loop_reference_run_dir
                    )
                    reference_bundle = ReferenceBundle(
                        input_mode=reference_bundle.input_mode,
                        stack=context.extracted_params.stack,
                        user_text=context.extracted_params.prompt["text"],
                        images=reference_bundle.images,
                        videos=reference_bundle.videos,
                        reference_url=(
                            context.extracted_params.prompt.get("reference_url", "")
                            or reference_bundle.reference_url
                        ),
                        live_reference=reference_bundle.live_reference,
                        design_system_preflight=reference_bundle.design_system_preflight,
                    )
                    if (
                        context.extracted_params.file_state is None
                        and resume_state is not None
                        and resume_state.best_file_state is not None
                    ):
                        context.extracted_params.file_state = (
                            resume_state.best_file_state
                        )
                else:
                    reference_bundle = ReferenceBundle(
                        input_mode=context.extracted_params.input_mode,
                        stack=context.extracted_params.stack,
                        user_text=context.extracted_params.prompt["text"],
                        images=context.extracted_params.prompt["images"],
                        videos=context.extracted_params.prompt["videos"],
                        reference_url=context.extracted_params.prompt.get(
                            "reference_url", ""
                        ),
                    )

                loop_orchestrator = ValidationLoopOrchestrator(
                    send_message=context.send_message,
                    openai_api_key=context.extracted_params.openai_api_key,
                    openai_base_url=context.extracted_params.openai_base_url,
                    anthropic_api_key=context.extracted_params.anthropic_api_key,
                    gemini_api_key=context.extracted_params.gemini_api_key,
                    should_generate_images=context.extracted_params.should_generate_images,
                    option_codes=context.extracted_params.option_codes,
                    max_iterations=context.extracted_params.max_validation_iterations,
                    design_system_reuse_mode=context.extracted_params.validated_loop_design_system_mode,
                    design_system_reuse_run_dir=context.extracted_params.validated_loop_design_system_run_dir,
                )
                context.variant_models = [loop_orchestrator.executor_model]

                if IS_DEBUG_ENABLED:
                    await context.send_message(
                        "variantModels",
                        None,
                        0,
                        {"models": [model.value for model in context.variant_models]},
                        None,
                    )

                loop_result = await loop_orchestrator.run(
                    reference_bundle=reference_bundle,
                    initial_file_state=context.extracted_params.file_state,
                    resume_state=resume_state,
                )
                context.metadata["validatedLoop"] = loop_result.model_dump()
                context.variant_completions = {0: loop_result.code}
                context.completions = [loop_result.code]

                await context.send_message("setCode", loop_result.code, 0, None, None)
                if loop_result.stop_reason == "pass":
                    completion_payload = {
                        "artifactPath": loop_result.saved_code_path,
                        "runDir": loop_result.saved_run_dir,
                    }
                    if loop_result.saved_project_dir:
                        completion_payload["projectDir"] = loop_result.saved_project_dir
                    if loop_result.saved_project_app_path:
                        completion_payload["projectAppPath"] = loop_result.saved_project_app_path
                    await context.send_message(
                        "variantComplete",
                        "Validated loop generation complete",
                        0,
                        completion_payload,
                        None,
                    )
                else:
                    error_payload = {
                        "stopReason": loop_result.stop_reason,
                        "iterationsCompleted": len(loop_result.iterations),
                        "maxIterations": context.extracted_params.max_validation_iterations,
                        "canContinue": loop_result.stop_reason == "max_iterations",
                        "artifactPath": loop_result.saved_code_path,
                        "runDir": loop_result.saved_run_dir,
                    }
                    if loop_result.saved_project_dir:
                        error_payload["projectDir"] = loop_result.saved_project_dir
                    if loop_result.saved_project_app_path:
                        error_payload["projectAppPath"] = loop_result.saved_project_app_path
                    await context.send_message(
                        "variantError",
                        (
                            "Validated loop stopped before reaching a passing result "
                            f"({loop_result.stop_reason})."
                        ),
                        0,
                        error_payload,
                        None,
                    )
                await next_func()
                return

            # Select models (handles video mode internally)
            model_selector = ModelSelectionStage(context.throw_error)
            context.variant_models = await model_selector.select_models(
                generation_type=context.extracted_params.generation_type,
                input_mode=context.extracted_params.input_mode,
                openai_api_key=context.extracted_params.openai_api_key,
                anthropic_api_key=context.extracted_params.anthropic_api_key,
                gemini_api_key=context.extracted_params.gemini_api_key,
                request_source=context.extracted_params.request_source,
                model_slots=context.extracted_params.model_slots,
            )
            if IS_DEBUG_ENABLED:
                await context.send_message(
                    "variantModels",
                    None,
                    0,
                    {"models": [model.value for model in context.variant_models]},
                    None,
                )

            generation_stage = AgenticGenerationStage(
                send_message=context.send_message,
                openai_api_key=context.extracted_params.openai_api_key,
                openai_base_url=context.extracted_params.openai_base_url,
                anthropic_api_key=context.extracted_params.anthropic_api_key,
                gemini_api_key=context.extracted_params.gemini_api_key,
                should_generate_images=context.extracted_params.should_generate_images,
                file_state=context.extracted_params.file_state,
                option_codes=context.extracted_params.option_codes,
            )

            context.variant_completions = await generation_stage.process_variants(
                variant_models=context.variant_models,
                prompt_messages=context.prompt_messages,
            )

            # Check if all variants failed
            if len(context.variant_completions) == 0:
                await context.throw_error(
                    "Error generating code. Please contact support."
                )
                return  # Don't continue the pipeline

            # Convert to list format
            context.completions = []
            for i in range(len(context.variant_models)):
                if i in context.variant_completions:
                    context.completions.append(context.variant_completions[i])
                else:
                    context.completions.append("")

        except Exception as e:
            print(f"[GENERATE_CODE] Unexpected error: {e}")
            await context.throw_error(f"An unexpected error occurred: {str(e)}")
            return  # Don't continue the pipeline

        await next_func()


class PostProcessingMiddleware(Middleware):
    """Handles post-processing and logging"""

    async def process(
        self, context: PipelineContext, next_func: Callable[[], Awaitable[None]]
    ) -> None:
        post_processor = PostProcessingStage()
        await post_processor.process_completions(context.completions, context.websocket)

        await next_func()


@router.websocket("/generate-code")
async def stream_code(websocket: WebSocket):
    """Handle WebSocket code generation requests using a pipeline pattern"""
    pipeline = Pipeline()

    # Configure the pipeline
    pipeline.use(WebSocketSetupMiddleware())
    pipeline.use(ParameterExtractionMiddleware())
    pipeline.use(StatusBroadcastMiddleware())
    pipeline.use(PromptCreationMiddleware())
    pipeline.use(CodeGenerationMiddleware())
    pipeline.use(PostProcessingMiddleware())

    # Execute the pipeline
    try:
        await pipeline.execute(websocket)
    except WebSocketDisconnect as exc:
        print(
            "[GENERATE_CODE] WebSocket disconnected during request handling "
            f"(code={exc.code})."
        )
