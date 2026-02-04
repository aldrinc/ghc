import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/clerk-react";
import { useCallback } from "react";
import { useApiClient, type ApiError } from "@/api/client";
import type { ClaudeChatRequestPayload, ClaudeContextFile, ClaudeStreamEvent } from "@/types/claude";

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

async function parseError(resp: Response): Promise<ApiError> {
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

export function useClaudeContext(params: {
  ideaWorkspaceId?: string;
  clientId?: string;
  productId?: string;
  campaignId?: string;
}) {
  const { get } = useApiClient();
  return useQuery<{ files: ClaudeContextFile[] }>({
    queryKey: ["claude-context", params.ideaWorkspaceId, params.clientId, params.productId, params.campaignId],
    queryFn: () => {
      const search = new URLSearchParams();
      if (params.ideaWorkspaceId) search.set("ideaWorkspaceId", params.ideaWorkspaceId);
      if (params.clientId) search.set("clientId", params.clientId);
      if (params.productId) search.set("productId", params.productId);
      if (params.campaignId) search.set("campaignId", params.campaignId);
      return get(`/claude/context?${search.toString()}`);
    },
    enabled: Boolean(params.ideaWorkspaceId),
  });
}

export type ClaudeStreamHandle = { abort: () => void };

export function useClaudeStream() {
  const { getToken } = useAuth();

  return useCallback(
    async (
      payload: ClaudeChatRequestPayload,
      onEvent: (event: ClaudeStreamEvent) => void
    ): Promise<ClaudeStreamHandle> => {
      const controller = new AbortController();
      const token = await getToken({ template: clerkTokenTemplate, skipCache: true });
      const headers = new Headers({ "Content-Type": "application/json" });
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }

      const resp = await fetch(`${defaultBaseUrl}/claude/chat/stream`, {
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
        throw new Error("Missing response stream");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let sawDone = false;

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
                const parsed = JSON.parse(payloadStr) as ClaudeStreamEvent;
                if (parsed.type === "done") {
                  sawDone = true;
                }
                onEvent(parsed);
              } catch (err) {
                // eslint-disable-next-line no-console
                console.error("Failed to parse Claude stream chunk", err, raw);
              }
              boundary = buffer.indexOf("\n\n");
            }
          }
          if (!sawDone) {
            onEvent({ type: "done" });
          }
        } catch (err) {
          if ((err as DOMException).name === "AbortError") return;
          const message = err instanceof Error ? err.message : String(err);
          onEvent({ type: "error", message });
        }
      };

      void pump();
      return { abort: () => controller.abort() };
    },
    [getToken]
  );
}
