import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/clerk-react";
import { useApiClient } from "@/api/client";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";

const defaultBaseUrl = resolveRequiredApiBaseUrl();
const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

export interface AgentTurn {
  id: string;
  seq: number;
  role: string;
  content: string;
  runId?: string | null;
  artifactId?: string | null;
  sitePageVersionId?: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface AgentRuntimeSession {
  id: string;
  status: string;
  runtimeHome: string;
  hermesSessionId?: string | null;
  projectionHash: string;
  toolsets: string[];
  lastError?: string | null;
  lastUsedAt: string;
}

export interface ApprovalItem {
  id: string;
  targetKind: "artifact" | "site_page_version";
  artifactId?: string | null;
  sitePageVersionId?: string | null;
  status: string;
  decision?: string | null;
  resolutionNotes?: string | null;
  createdAt: string;
  resolvedAt?: string | null;
}

export interface AgentThreadDetail {
  thread: Record<string, unknown> & {
    id: string;
    clientId: string;
    productId: string;
    siteId?: string | null;
    pageId?: string | null;
    agentProfile: string;
    objectiveType: string;
    title?: string | null;
    bundleKey: string;
    status: string;
    metadata: Record<string, unknown>;
    createdAt: string;
    updatedAt: string;
  };
  runtimeSession: AgentRuntimeSession;
  turns: AgentTurn[];
  approvals: ApprovalItem[];
}

export interface AgentThreadValidation extends AgentThreadDetail {
  validation: {
    runtime?: Record<string, unknown>;
    pageContextBinding?: Record<string, unknown> | null;
    runs?: Array<Record<string, unknown>>;
  };
}

type PageAgentSessionRequest = {
  clientId: string;
  productId: string;
  siteId: string;
  pageId: string;
  agentProfile?: string;
  objectiveType?: string;
  title?: string;
  bundleKey?: string;
  metadata?: Record<string, unknown>;
  forceNew?: boolean;
};

type PostAgentThreadMessageRequest = {
  content: string;
};

export type AgentThreadStreamEvent =
  | {
      type: "start";
      threadId: string;
      runId: string;
      objectiveType: string;
      outputMode: string;
      message: string;
    }
  | {
      type: "status" | "thinking" | "warning" | "error";
      runId?: string;
      message: string;
      stage?: string;
    }
  | {
      type: "session";
      message: string;
      sessionId?: string | null;
      resumed?: boolean;
    }
  | {
      type: "tool";
      message: string;
      toolName?: string;
      target?: string;
      duration?: string;
      status?: string;
      icon?: string;
    }
  | {
      type: "done";
      threadId: string;
      runId: string;
      hermesSessionId?: string;
      usage?: Record<string, number>;
      detail: AgentThreadDetail;
    };

export type AgentThreadStreamHandle = { abort: () => void };

type ResolveApprovalRequest = {
  targetKind: "artifact" | "site_page_version";
  targetId: string;
  decision: "approved" | "rejected";
  notes?: string;
};

async function parseError(resp: Response) {
  let raw: unknown = undefined;
  try {
    raw = await resp.clone().json();
  } catch {
    raw = await resp.text();
  }
  const detail = (raw as { detail?: unknown })?.detail;
  let message: string | undefined;
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    message = first?.msg;
  } else if (typeof (raw as { message?: unknown })?.message === "string") {
    message = (raw as { message?: string }).message;
  }
  if (!message || typeof message !== "string") {
    message = resp.statusText || "Request failed";
  }
  return { message, status: resp.status, raw };
}

export function usePageAgentSession(requestPayload: PageAgentSessionRequest | null) {
  const { request } = useApiClient();
  return useQuery({
    queryKey: [
      "agentThreads",
      "pageSession",
      requestPayload?.clientId ?? null,
      requestPayload?.productId ?? null,
      requestPayload?.siteId ?? null,
      requestPayload?.pageId ?? null,
      requestPayload?.agentProfile ?? "copy",
      requestPayload?.objectiveType ?? "page_copy_agent",
      requestPayload?.forceNew ?? false,
    ],
    queryFn: () =>
      request<AgentThreadDetail>("/agent-threads/page-session", {
        method: "POST",
        body: JSON.stringify({
          clientId: requestPayload!.clientId,
          productId: requestPayload!.productId,
          siteId: requestPayload!.siteId,
          pageId: requestPayload!.pageId,
          agentProfile: requestPayload!.agentProfile ?? "copy",
          objectiveType: requestPayload!.objectiveType ?? "page_copy_agent",
          title: requestPayload!.title,
          bundleKey: requestPayload!.bundleKey,
          metadata: requestPayload!.metadata ?? {},
          forceNew: requestPayload!.forceNew ?? false,
        }),
      }),
    enabled: !!requestPayload,
    staleTime: 15000,
  });
}

export function useAgentThread(threadId: string | null) {
  const { get } = useApiClient();
  return useQuery({
    queryKey: ["agentThreads", threadId],
    queryFn: () => get<AgentThreadDetail>(`/agent-threads/${threadId}`),
    enabled: !!threadId,
    staleTime: 5000,
  });
}

export function useAgentThreadValidation(threadId: string | null) {
  const { get } = useApiClient();
  return useQuery({
    queryKey: ["agentThreads", threadId, "validation"],
    queryFn: () => get<AgentThreadValidation>(`/agent-threads/${threadId}/validation`),
    enabled: !!threadId,
    staleTime: 5000,
  });
}

export function usePostAgentThreadMessage(threadId: string | null) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PostAgentThreadMessageRequest) =>
      post<AgentThreadDetail>(`/agent-threads/${threadId}/messages`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agentThreads", threadId] });
      queryClient.invalidateQueries({ queryKey: ["agentThreads", threadId, "validation"] });
    },
  });
}

export function useStreamAgentThreadMessage(threadId: string | null) {
  const { getToken } = useAuth();

  return async (
    payload: PostAgentThreadMessageRequest,
    onEvent: (event: AgentThreadStreamEvent) => void,
  ): Promise<AgentThreadStreamHandle> => {
    if (!threadId) {
      throw new Error("Missing agent thread id for streamed message.");
    }
    const controller = new AbortController();
    const token = await getToken({ template: clerkTokenTemplate });
    const headers = new Headers({ "Content-Type": "application/json" });
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const resp = await fetch(`${defaultBaseUrl}/agent-threads/${threadId}/messages/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!resp.ok) {
      throw await parseError(resp);
    }
    const reader = resp.body?.getReader();
    if (!reader) {
      throw new Error("Missing agent thread response stream.");
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let sawTerminalEvent = false;

    const pump = async () => {
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const raw = buffer.slice(0, boundary).trim();
            buffer = buffer.slice(boundary + 2);
            if (!raw.startsWith("data:")) {
              boundary = buffer.indexOf("\n\n");
              continue;
            }
            const payloadStr = raw.replace(/^data:\s*/, "");
            if (!payloadStr) {
              boundary = buffer.indexOf("\n\n");
              continue;
            }
            try {
              const parsed = JSON.parse(payloadStr) as AgentThreadStreamEvent;
              if (parsed.type === "done" || parsed.type === "error") {
                sawTerminalEvent = true;
              }
              onEvent(parsed);
            } catch (err) {
              // eslint-disable-next-line no-console
              console.error("Failed to parse agent thread stream chunk", err, raw);
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
        if (!sawTerminalEvent) {
          onEvent({ type: "error", message: "The page-agent stream ended without a terminal event." });
        }
      } catch (err) {
        if ((err as DOMException).name === "AbortError") return;
        const message = err instanceof Error ? err.message : String(err);
        onEvent({ type: "error", message });
      }
    };

    void pump();
    return { abort: () => controller.abort() };
  };
}

export function useResolveAgentThreadApproval(threadId: string | null) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ResolveApprovalRequest) =>
      post<AgentThreadDetail>(`/agent-threads/${threadId}/approve`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agentThreads", threadId] });
      queryClient.invalidateQueries({ queryKey: ["agentThreads", threadId, "validation"] });
    },
  });
}

export function useResetAgentThreadSession(threadId: string | null) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => post<AgentThreadDetail>(`/agent-threads/${threadId}/reset-session`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agentThreads", threadId] });
      queryClient.invalidateQueries({ queryKey: ["agentThreads", threadId, "validation"] });
    },
  });
}
