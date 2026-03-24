import { PromptContent, PromptMessageRole } from "../../types";

export type CommitHash = string;

export type VariantStatus =
  | "generating"
  | "complete"
  | "cancelled"
  | "error"
  | "paused";

export type VariantResumableStop = {
  stopReason?: string;
  iterationsCompleted?: number;
  maxIterations?: number;
  canContinue?: boolean;
};

export type AgentEventStatus = "running" | "complete" | "error";
export type AgentEventType = "thinking" | "assistant" | "tool";
export type AgentEventSource = "supervisor" | "executor";

export type AgentEvent = {
  id: string;
  type: AgentEventType;
  status: AgentEventStatus;
  source?: AgentEventSource;
  title?: string;
  content?: string;
  toolName?: string;
  input?: any;
  output?: any;
  startedAt: number;
  endedAt?: number;
};

export type VariantHistoryMessage = {
  role: PromptMessageRole;
  text: string;
  imageAssetIds: string[];
  videoAssetIds: string[];
};

export type Variant = {
  code: string;
  history: VariantHistoryMessage[];
  requestStartedAt?: number;
  completedAt?: number;
  status?: VariantStatus;
  errorMessage?: string;
  thinking?: string;
  thinkingStartTime?: number;
  thinkingDuration?: number;
  agentEvents?: AgentEvent[];
  model?: string;
  resumableStop?: VariantResumableStop;
  savedCodePath?: string;
  savedRunDir?: string;
};

export type BaseCommit = {
  hash: CommitHash;
  parentHash: CommitHash | null;
  dateCreated: Date;
  isCommitted: boolean;
  inputMode?: "image" | "video" | "text";
  variants: Variant[];
  selectedVariantIndex: number;
};

export type CommitType = "ai_create" | "ai_edit" | "code_create";

export type AiCreateCommit = BaseCommit & {
  type: "ai_create";
  inputs: PromptContent;
};

export type AiEditCommit = BaseCommit & {
  type: "ai_edit";
  inputs: PromptContent;
};

export type CodeCreateCommit = BaseCommit & {
  type: "code_create";
  inputs: null;
};

export type Commit = AiCreateCommit | AiEditCommit | CodeCreateCommit;
