import toast from "react-hot-toast";
import { WS_BACKEND_URL } from "./config";
import {
  APP_ERROR_WEB_SOCKET_CODE,
  USER_CLOSE_WEB_SOCKET_CODE,
} from "./constants";
import { FullGenerationSettings } from "./types";

const ERROR_MESSAGE =
  "Error generating code. Check the Developer Console AND the backend logs for details. Feel free to open a Github issue.";

const CANCEL_MESSAGE = "Code generation cancelled";
const PAYLOAD_TOO_LARGE_MESSAGE =
  "The request payload is too large for the websocket. Shorten the video or reduce attached assets and try again.";

type WebSocketResponse = {
  type:
    | "chunk"
    | "status"
    | "setCode"
    | "error"
    | "variantComplete"
    | "variantError"
    | "variantCount"
    | "variantModels"
    | "thinking"
    | "assistant"
    | "toolStart"
    | "toolResult";
  value?: string;
  data?: unknown;
  eventId?: string;
  variantIndex: number;
};

type AgentEventMeta = {
  source?: "supervisor" | "executor";
  title?: string;
};

type VariantResultMeta = {
  artifactPath?: string;
  runDir?: string;
};

type StatusUpdateMeta = VariantResultMeta;

type VariantErrorMeta = VariantResultMeta & {
  stopReason?: string;
  iterationsCompleted?: number;
  maxIterations?: number;
  canContinue?: boolean;
};

type VariantModelsData = {
  models?: string[];
};

type ToolEventData = {
  source?: "supervisor" | "executor";
  title?: string;
  name?: string;
  input?: unknown;
  output?: unknown;
  ok?: boolean;
};

interface CodeGenerationCallbacks {
  onChange: (chunk: string, variantIndex: number) => void;
  onSetCode: (code: string, variantIndex: number) => void;
  onStatusUpdate: (
    status: string,
    variantIndex: number,
    meta?: StatusUpdateMeta
  ) => void;
  onVariantComplete: (
    variantIndex: number,
    meta?: VariantResultMeta
  ) => void;
  onVariantError: (
    variantIndex: number,
    error: string,
    meta?: VariantErrorMeta
  ) => void;
  onVariantCount: (count: number) => void;
  onVariantModels: (models: string[]) => void;
  onThinking: (
    content: string,
    variantIndex: number,
    eventId?: string,
    meta?: AgentEventMeta
  ) => void;
  onAssistant: (
    content: string,
    variantIndex: number,
    eventId?: string,
    meta?: AgentEventMeta
  ) => void;
  onToolStart: (data: ToolEventData, variantIndex: number, eventId?: string) => void;
  onToolResult: (
    data: ToolEventData,
    variantIndex: number,
    eventId?: string
  ) => void;
  onCancel: (
    reason: "user_cancelled" | "request_failed" | "connection_error",
    errorMessage?: string
  ) => void;
  onComplete: () => void;
}

export function generateCode(
  wsRef: React.MutableRefObject<WebSocket | null>,
  params: FullGenerationSettings,
  callbacks: CodeGenerationCallbacks
) {
  const wsUrl = `${WS_BACKEND_URL}/generate-code`;
  console.log("Connecting to backend @ ", wsUrl);

  const ws = new WebSocket(wsUrl);
  wsRef.current = ws;

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify(params));
  });

  ws.addEventListener("message", async (event: MessageEvent) => {
    const response = JSON.parse(event.data) as WebSocketResponse;
    if (response.type === "chunk") {
      callbacks.onChange(response.value || "", response.variantIndex);
    } else if (response.type === "status") {
      callbacks.onStatusUpdate(
        response.value || "",
        response.variantIndex,
        response.data as StatusUpdateMeta | undefined
      );
    } else if (response.type === "setCode") {
      callbacks.onSetCode(response.value || "", response.variantIndex);
    } else if (response.type === "variantComplete") {
      callbacks.onVariantComplete(
        response.variantIndex,
        response.data as VariantResultMeta | undefined
      );
    } else if (response.type === "variantError") {
      callbacks.onVariantError(
        response.variantIndex,
        response.value || "",
        response.data as VariantErrorMeta | undefined
      );
    } else if (response.type === "variantCount") {
      callbacks.onVariantCount(parseInt(response.value || "1"));
    } else if (response.type === "variantModels") {
      callbacks.onVariantModels(
        ((response.data as VariantModelsData | undefined)?.models || []).filter(
          (model): model is string => typeof model === "string"
        )
      );
    } else if (response.type === "thinking") {
      callbacks.onThinking(
        response.value || "",
        response.variantIndex,
        response.eventId,
        response.data as AgentEventMeta | undefined
      );
    } else if (response.type === "assistant") {
      callbacks.onAssistant(
        response.value || "",
        response.variantIndex,
        response.eventId,
        response.data as AgentEventMeta | undefined
      );
    } else if (response.type === "toolStart") {
      callbacks.onToolStart(
        (response.data as ToolEventData | undefined) || {},
        response.variantIndex,
        response.eventId
      );
    } else if (response.type === "toolResult") {
      callbacks.onToolResult(
        (response.data as ToolEventData | undefined) || {},
        response.variantIndex,
        response.eventId
      );
    } else if (response.type === "error") {
      console.error("Error generating code", response.value);
      toast.error(response.value || ERROR_MESSAGE);
    }
  });

  ws.addEventListener("close", (event) => {
    console.log("Connection closed", event.code, event.reason);
    if (event.code === USER_CLOSE_WEB_SOCKET_CODE) {
      toast.success(CANCEL_MESSAGE);
      callbacks.onCancel("user_cancelled");
    } else if (event.code === 1009) {
      console.error("WebSocket payload too large", event);
      toast.error(PAYLOAD_TOO_LARGE_MESSAGE);
      callbacks.onCancel("request_failed", PAYLOAD_TOO_LARGE_MESSAGE);
    } else if (event.code === APP_ERROR_WEB_SOCKET_CODE) {
      console.error("Known server error", event);
      callbacks.onCancel("request_failed", event.reason || ERROR_MESSAGE);
    } else if (event.code !== 1000) {
      console.error("Unknown server or connection error", event);
      toast.error(ERROR_MESSAGE);
      callbacks.onCancel("connection_error", event.reason || ERROR_MESSAGE);
    } else {
      callbacks.onComplete();
    }
  });

  ws.addEventListener("error", (error) => {
    console.error("WebSocket error", error);
    toast.error(ERROR_MESSAGE);
  });
}
