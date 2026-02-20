from __future__ import annotations

import ast
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.agent.types import ToolContext, ToolResult
from app.db.enums import AgentRunStatusEnum, AgentToolCallStatusEnum
from app.db.repositories.agent_runs import AgentRunsRepository, AgentToolCallsRepository
from app.observability import LangfuseTraceContext, bind_langfuse_trace_context, start_langfuse_span


ArgsT = TypeVar("ArgsT", bound=BaseModel)


class ToolValidationError(ValueError):
    pass


class ToolExecutionError(RuntimeError):
    pass


class BaseTool(Generic[ArgsT]):
    name: str
    ArgsModel: type[ArgsT]

    def run(self, *, ctx: ToolContext, args: ArgsT) -> ToolResult:
        raise NotImplementedError

    def run_stream(self, *, ctx: ToolContext, args: ArgsT) -> Generator[dict[str, Any], None, ToolResult]:
        """
        Streaming-capable tool entrypoint.

        Default implementation yields no events and delegates to `run`.
        """
        result = self.run(ctx=ctx, args=args)
        if False:  # pragma: no cover - makes this method a generator without yielding in normal execution
            yield {}
        return result


@dataclass
class AgentRunHandle:
    run_id: str
    seq: int = 0


class AgentRuntime:
    def __init__(self, *, session: Session, org_id: str, user_id: str) -> None:
        self.session = session
        self.org_id = org_id
        self.user_id = user_id
        self._runs_repo = AgentRunsRepository(session)
        self._calls_repo = AgentToolCallsRepository(session)

    def begin_run(
        self,
        *,
        objective_type: str,
        client_id: Optional[str] = None,
        funnel_id: Optional[str] = None,
        page_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        ruleset_version: Optional[str] = None,
        inputs_json: Optional[dict[str, Any]] = None,
    ) -> AgentRunHandle:
        run = self._runs_repo.create_run(
            org_id=self.org_id,
            user_id=self.user_id,
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
            objective_type=objective_type,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            ruleset_version=ruleset_version,
            inputs_json=inputs_json or {},
        )
        return AgentRunHandle(run_id=str(run.id), seq=0)

    def finish_run(
        self,
        *,
        handle: AgentRunHandle,
        status: AgentRunStatusEnum,
        outputs_json: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        self._runs_repo.finish_run(
            run_id=handle.run_id,
            status=status,
            outputs_json=outputs_json,
            error=error,
        )

    def _validate_args(self, *, tool: BaseTool, raw_args: Any) -> BaseModel:
        try:
            return tool.ArgsModel.model_validate(raw_args)
        except ValidationError as exc:
            raise ToolValidationError(f"Invalid args for tool {tool.name}: {exc}") from exc

    @staticmethod
    def _parse_error_details(error_message: str) -> dict[str, Any] | None:
        marker = "details="
        marker_index = error_message.find(marker)
        if marker_index < 0:
            return None
        details_str = error_message[marker_index + len(marker) :].strip()
        if not details_str:
            return None
        try:
            parsed = ast.literal_eval(details_str)
        except (ValueError, SyntaxError):
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    @classmethod
    def _tool_error_metadata(cls, exc: Exception) -> dict[str, Any]:
        error_message = str(exc)
        metadata: dict[str, Any] = {
            "toolErrorType": type(exc).__name__,
            "toolErrorMessage": error_message,
        }
        details = cls._parse_error_details(error_message)
        if details:
            metadata["toolErrorDetails"] = details
        return metadata

    def invoke_tool_stream(
        self,
        *,
        handle: AgentRunHandle,
        tool: BaseTool,
        raw_args: Any,
        client_id: Optional[str] = None,
        funnel_id: Optional[str] = None,
        page_id: Optional[str] = None,
    ) -> Generator[dict[str, Any], None, ToolResult]:
        """
        Invoke a tool while:
        - emitting tool_called/tool_result/tool_error events
        - persisting tool call traces to agent_tool_calls
        """
        args = self._validate_args(tool=tool, raw_args=raw_args)
        handle.seq += 1

        call = self._calls_repo.create_call(
            run_id=handle.run_id,
            seq=handle.seq,
            tool_name=tool.name,
            args_json=args.model_dump(mode="json"),
        )

        def _redact(payload: Any) -> Any:
            # Keep SSE events small; full args/results are persisted in agent_tool_calls.
            large_keys = {
                "puckData",
                "basePuckData",
                "productContext",
                "brandDocuments",
                "documentBlocks",
                "attachmentBlocks",
                "messages",
                "copyPack",
            }
            if isinstance(payload, dict):
                return {k: ("<omitted>" if k in large_keys else v) for k, v in payload.items()}
            return payload

        yield {
            "type": "tool_called",
            "runId": handle.run_id,
            "toolName": tool.name,
            "args": _redact(call.args_json),
        }

        ctx = ToolContext(
            session=self.session,
            org_id=self.org_id,
            user_id=self.user_id,
            run_id=handle.run_id,
            tool_call_id=str(call.id),
            tool_seq=handle.seq,
            tool_name=tool.name,
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        trace_context = LangfuseTraceContext(
            name=f"agent.{tool.name}",
            session_id=handle.run_id,
            user_id=self.user_id,
            metadata={
                "orgId": self.org_id,
                "agentRunId": handle.run_id,
                "toolCallId": str(call.id),
                "toolName": tool.name,
                "toolSeq": handle.seq,
                "clientId": client_id,
                "funnelId": funnel_id,
                "pageId": page_id,
            },
            tags=["agent", "tool_call", tool.name],
        )

        started = time.monotonic()
        tool_span = None
        try:
            with bind_langfuse_trace_context(trace_context):
                with start_langfuse_span(
                    name=f"agent.tool.{tool.name}",
                    input={"args": _redact(call.args_json)},
                    metadata={
                        "operation": "invoke_tool_stream",
                        "toolName": tool.name,
                        "toolSeq": handle.seq,
                        "toolCallId": str(call.id),
                    },
                    tags=["agent", "tool_call", tool.name],
                    trace_name=f"agent.{tool.name}",
                ) as tool_span:
                    try:
                        result = yield from tool.run_stream(ctx=ctx, args=args)
                    except Exception as exc:  # noqa: BLE001
                        if tool_span is not None:
                            tool_span.update(
                                metadata=self._tool_error_metadata(exc),
                                output={"status": "failed"},
                            )
                        raise
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - started) * 1000)
            self._calls_repo.finish_call(
                call_id=str(call.id),
                status=AgentToolCallStatusEnum.failed,
                error=str(exc),
                duration_ms=duration_ms,
            )
            yield {
                "type": "tool_error",
                "runId": handle.run_id,
                "toolName": tool.name,
                "message": str(exc),
            }
            raise ToolExecutionError(f"Tool {tool.name} failed: {exc}") from exc

        duration_ms = int((time.monotonic() - started) * 1000)
        self._calls_repo.finish_call(
            call_id=str(call.id),
            status=AgentToolCallStatusEnum.completed,
            result_json=result.model_dump(mode="json"),
            duration_ms=duration_ms,
        )
        if tool_span is not None:
            tool_span.update(
                output={
                    "status": "completed",
                    "durationMs": duration_ms,
                }
            )
        yield {
            "type": "tool_result",
            "runId": handle.run_id,
            "toolName": tool.name,
            "ui_details": _redact(result.ui_details),
            "attachments": result.attachments,
        }
        return result
