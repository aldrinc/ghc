// Types for screenshot-to-code upstream events
// Mirrors the WebSocket message types from screenshot-to-code/frontend/src/generateCode.ts

export type UpstreamEventType =
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

export type AgentEventMeta = {
  source?: "supervisor" | "executor";
  title?: string;
};

export type VariantResultMeta = {
  artifactPath?: string;
  runDir?: string;
};

export type VariantErrorMeta = VariantResultMeta & {
  stopReason?: string;
  iterationsCompleted?: number;
  maxIterations?: number;
  canContinue?: boolean;
};

export type VariantModelsData = {
  models?: string[];
};

export type ToolEventData = {
  source?: "supervisor" | "executor";
  title?: string;
  name?: string;
  input?: unknown;
  output?: unknown;
  ok?: boolean;
};

// Unified activity event for display
export type ActivityEvent = {
  id: string;
  type: "thinking" | "assistant" | "tool" | "status" | "variant" | "error";
  variantIndex: number;
  status: "running" | "complete" | "error";
  content?: string;
  title?: string;
  toolName?: string;
  input?: unknown;
  output?: unknown;
  startedAt?: number;
  endedAt?: number;
  eventId?: string;
  meta?: Record<string, unknown>;
};

// Raw upstream transcript entry from backend
export type UpstreamTranscriptEntry = {
  type: UpstreamEventType;
  value?: string;
  data?: unknown;
  eventId?: string;
  variantIndex: number;
  timestamp?: number;
};

// Raw upstream variant data from backend
export type UpstreamVariantData = {
  variantIndex: number;
  code?: string;
  status?: "generating" | "complete" | "error" | "paused" | "cancelled";
  model?: string;
  thinking?: string;
  thinkingDuration?: number;
  requestStartedAt?: number;
  completedAt?: number;
  agentEvents?: ActivityEvent[];
};
