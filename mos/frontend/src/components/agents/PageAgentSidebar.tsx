import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, Check, ChevronDown, Loader2, Plus, Send, Sparkles, X } from "lucide-react";
import {
  useAgentThread,
  useAgentThreadValidation,
  usePageAgentSession,
  useResetAgentThreadSession,
  useResolveAgentThreadApproval,
  useStreamAgentThreadMessage,
  type AgentThreadStreamEvent,
  type AgentThreadDetail,
} from "@/api/agentThreads";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";

const QUICK_ACTIONS = [
  "Audit this page for broken UX, copy gaps, and missing sections.",
  "Tighten the whole page copy while keeping the structure fixed.",
  "Fix navigation, links, and CTA targets on this page.",
];

const PAGE_CHAT_OBJECTIVE_TYPE = "page_orchestrator";

type Props = {
  clientId: string | null;
  productId: string | null;
  siteId: string | null;
  pageId: string | null;
  pageName: string;
  pageSlug: string;
  mode: "editor" | "preview";
  enabled?: boolean;
  unavailableReason?: string | null;
};

function formatTimestamp(value?: string | null): string {
  if (!value) return "Unknown time";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function MessageBubble({ role, content, createdAt }: { role: string; content: string; createdAt?: string | null }) {
  const isUser = role === "user";
  return (
    <div
      className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}
      data-page-agent-message-role={role}
    >
      <div className={`min-w-0 max-w-full rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${isUser ? "bg-content text-surface" : "border border-border/70 bg-surface-2 text-content"}`}>
        <div className="overflow-hidden break-words whitespace-pre-wrap">{content}</div>
        <div className={`mt-2 text-[11px] ${isUser ? "text-surface/70" : "text-content-muted"}`}>
          {isUser ? "You" : "Hermes"}{createdAt ? ` \u2022 ${formatTimestamp(createdAt)}` : ""}
        </div>
      </div>
    </div>
  );
}

function latestAssistantTurn(threadDetail: AgentThreadDetail | null) {
  return threadDetail ? [...threadDetail.turns].reverse().find((turn) => turn.role === "assistant") ?? null : null;
}

type LiveActivityItem = AgentThreadStreamEvent & {
  id: string;
  createdAt: string;
};

function activityLabel(item: LiveActivityItem): string {
  switch (item.type) {
    case "start":
      return "Run started";
    case "thinking":
      return "Thinking";
    case "tool":
      return item.toolName || "Tool";
    case "session":
      return item.resumed ? "Resumed" : "Session";
    case "warning":
      return "Warning";
    case "error":
      return "Error";
    case "done":
      return "Completed";
    default:
      return "Status";
  }
}

function activityTone(item: LiveActivityItem): "accent" | "neutral" | "warning" | "success" {
  switch (item.type) {
    case "tool":
      return item.status === "error" ? "warning" : "accent";
    case "warning":
    case "error":
      return "warning";
    case "done":
      return "success";
    default:
      return "neutral";
  }
}

function activityMessage(item: LiveActivityItem): string {
  if ("message" in item && typeof item.message === "string") {
    return item.message;
  }
  return "";
}

const ACTIVITY_TONE_CLASSES: Record<ReturnType<typeof activityTone>, string> = {
  accent: "text-accent",
  neutral: "text-content-muted",
  warning: "text-danger",
  success: "text-success",
};

/** Compact activity row shown inline in the thread. */
function ActivityRow({ item }: { item: LiveActivityItem }) {
  const msg = activityMessage(item);
  const target = item.type === "tool" && item.target ? item.target : null;
  const duration = item.type === "tool" && item.duration ? item.duration : null;
  const shortTarget = target ? target.split("/").pop() || target : null;

  return (
    <div className="flex min-w-0 items-start gap-2 text-[11px] leading-4" data-page-agent-activity-item="true">
      <span className={`shrink-0 font-medium ${ACTIVITY_TONE_CLASSES[activityTone(item)]}`}>{activityLabel(item)}</span>
      <span className="min-w-0 text-content-muted" style={{ overflowWrap: "anywhere" }}>
        {msg || shortTarget || ""}
        {msg && shortTarget ? ` — ${shortTarget}` : ""}
        {duration ? ` (${duration})` : ""}
      </span>
    </div>
  );
}

const VISIBLE_ACTIVITY_COUNT = 4;

export type PageAgentSidebarContentProps = Props & {
  /** Optional close handler rendered as an X button in the header. */
  onClose?: () => void;
};

export function PageAgentSidebarContent({
  clientId,
  productId,
  siteId,
  pageId,
  pageName,
  pageSlug,
  mode,
  enabled = true,
  unavailableReason = null,
  onClose,
}: PageAgentSidebarContentProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [liveActivity, setLiveActivity] = useState<LiveActivityItem[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const streamHandleRef = useRef<{ abort: () => void } | null>(null);
  const pageSessionQuery = usePageAgentSession(
    enabled && clientId && productId && siteId && pageId
      ? { clientId, productId, siteId, pageId, agentProfile: "copy", objectiveType: PAGE_CHAT_OBJECTIVE_TYPE, title: `${pageName} page agent`, metadata: { mode } }
      : null
  );
  const threadId = pageSessionQuery.data?.thread.id ?? null;
  const threadQuery = useAgentThread(threadId);
  const validationQuery = useAgentThreadValidation(threadId);
  const streamMessage = useStreamAgentThreadMessage(threadId);
  const resetSession = useResetAgentThreadSession(threadId);
  const resolveApproval = useResolveAgentThreadApproval(threadId);
  const threadDetail = threadQuery.data ?? pageSessionQuery.data ?? null;
  const latestRun = useMemo(() => {
    const runs = validationQuery.data?.validation?.runs;
    return Array.isArray(runs) && runs.length ? runs[runs.length - 1] : null;
  }, [validationQuery.data]);
  const lastAssistantTurn = latestAssistantTurn(threadDetail);
  const canApprove = Boolean(
    lastAssistantTurn?.sitePageVersionId || lastAssistantTurn?.artifactId
  );
  const isSessionRefreshing = resetSession.isPending;
  const isBusy = isStreaming || resolveApproval.isPending || isSessionRefreshing;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [threadDetail?.turns.length, isBusy, liveActivity.length]);

  useEffect(() => {
    return () => {
      streamHandleRef.current?.abort();
    };
  }, []);

  const invalidatePage = () => {
    const queryKeys: Array<readonly unknown[]> = [
      ["sites", siteId, "pages", pageId],
      ["sites", siteId, "pages", pageId, clientId ?? "__missing_client__"],
      ["sites", clientId ?? "__org_scope__", siteId],
      ["sites", "__org_scope__", siteId],
      ["sites", clientId ?? null],
    ];
    for (const queryKey of queryKeys) {
      void queryClient.invalidateQueries({ queryKey });
      void queryClient.refetchQueries({ queryKey, type: "active" });
    }
  };

  const handleResetSession = () => {
    if (!threadId) return;
    streamHandleRef.current?.abort();
    streamHandleRef.current = null;
    resetSession.mutate(undefined, {
      onSuccess: () => {
        setSendError(null);
        setPendingPrompt(null);
        setLiveActivity([]);
        setIsStreaming(false);
        invalidatePage();
        toast.success("Started a fresh Hermes session for this page thread.");
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : "Failed to reset the Hermes session.";
        toast.error(message);
      },
    });
  };

  const handleSend = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || !threadId) return;
    streamHandleRef.current?.abort();
    setDraft("");
    setSendError(null);
    setPendingPrompt(trimmed);
    setLiveActivity([]);
    setIsStreaming(true);
    try {
      const handle = await streamMessage({ content: trimmed }, (event) => {
        setLiveActivity((previous) => {
          const nextItem: LiveActivityItem = {
            ...event,
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            createdAt: new Date().toISOString(),
          };
          return [...previous.slice(-23), nextItem];
        });
        if (event.type === "done") {
          streamHandleRef.current = null;
          setIsStreaming(false);
          setPendingPrompt(null);
          queryClient.setQueryData(["agentThreads", threadId], event.detail);
          queryClient.invalidateQueries({ queryKey: ["agentThreads", threadId, "validation"] });
          invalidatePage();
        } else if (event.type === "error") {
          streamHandleRef.current = null;
          setIsStreaming(false);
          setPendingPrompt(null);
          setSendError(event.message);
          toast.error(event.message);
        }
      });
      streamHandleRef.current = handle;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to send page-agent message.";
      setIsStreaming(false);
      setPendingPrompt(null);
      setSendError(message);
      toast.error(message);
    }
  };

  const handleApprove = (decision: "approved" | "rejected") => {
    if (!lastAssistantTurn) return;
    const targetKind = lastAssistantTurn.sitePageVersionId ? "site_page_version" : "artifact";
    const targetId = lastAssistantTurn.sitePageVersionId || lastAssistantTurn.artifactId;
    if (!targetId) return;
    resolveApproval.mutate(
      { targetKind, targetId, decision },
      {
        onSuccess: () => {
          invalidatePage();
          toast.success(decision === "approved" ? "Draft approved" : "Draft rejected");
        },
        onError: (error) => {
          const message = error instanceof Error ? error.message : "Failed to resolve approval.";
          toast.error(message);
        },
      },
    );
  };

  // -- Guard states --
  if (!clientId || !productId || !siteId || !pageId) {
    return <div className="p-5 text-sm text-content-muted">The page agent is unavailable until this page is bound to a workspace product and site target.</div>;
  }
  if (!enabled) {
    return (
      <div className="p-5 text-sm text-content-muted">
        {unavailableReason || "The page agent is unavailable for this page."}
      </div>
    );
  }
  if (pageSessionQuery.isLoading) {
    return <div className="flex items-center gap-2 p-5 text-sm text-content-muted"><Loader2 className="h-4 w-4 animate-spin" />Starting Hermes session&hellip;</div>;
  }
  if (pageSessionQuery.error) {
    return <div className="p-5 text-sm text-danger">{pageSessionQuery.error instanceof Error ? pageSessionQuery.error.message : "Failed to load the Hermes page session."}</div>;
  }

  const sessionLabel = threadDetail?.thread.title || `${pageName} session`;
  const sessionId = threadDetail?.runtimeSession.hermesSessionId;
  const latestRunStatus = latestRun && typeof latestRun.run === "object" && latestRun.run
    ? String((latestRun.run as Record<string, unknown>).status ?? "completed")
    : null;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ---- Header ---- */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-content text-surface">
            <Bot className="h-3.5 w-3.5" />
          </div>
          {/* Session switcher dropdown */}
          <div className="relative min-w-0">
            <button
              type="button"
              onClick={() => setSessionMenuOpen((v) => !v)}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-content transition-colors hover:bg-surface-2"
            >
              <span className="truncate">{sessionLabel}</span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-content-muted" />
            </button>
            {sessionMenuOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setSessionMenuOpen(false)} />
                <div className="absolute left-0 top-full z-50 mt-1 w-64 rounded-xl border border-border bg-surface p-1 shadow-lg">
                  {/* Current session */}
                  <div className="rounded-lg bg-surface-2 px-3 py-2">
                    <div className="text-xs font-medium text-content">{sessionLabel}</div>
                    <div className="mt-0.5 text-[11px] text-content-muted">
                      {threadDetail?.thread.status ?? "open"} \u2022 {sessionId ? sessionId.slice(0, 12) + "\u2026" : "No session ID"}
                    </div>
                  </div>
                  <Separator className="my-1" />
                  <button
                    type="button"
                    onClick={() => {
                      setSessionMenuOpen(false);
                      handleResetSession();
                    }}
                    disabled={isSessionRefreshing}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-content transition-colors hover:bg-surface-2"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    New session
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {isStreaming ? <Badge tone="accent">Streaming</Badge> : null}
          {latestRunStatus ? <Badge tone="neutral">{latestRunStatus}</Badge> : null}
          {onClose ? (
            <button type="button" onClick={onClose} className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-content-muted transition-colors hover:bg-surface-2 hover:text-content">
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>

      {/* ---- Quick actions ---- */}
      <div className="flex flex-wrap gap-2 border-b border-border px-5 py-3">
        {QUICK_ACTIONS.map((action) => (
          <Button key={action} size="sm" variant="secondary" className="h-auto rounded-full px-3 py-1.5 text-left text-[11px] leading-4" disabled={!threadId || isBusy} onClick={() => { void handleSend(action); }}>
            <Sparkles className="mr-1.5 h-3 w-3" />{action}
          </Button>
        ))}
      </div>

      {/* ---- Error / refreshing banners ---- */}
      {sendError ? (
        <div className="border-b border-danger/20 bg-danger/5 px-5 py-3 text-xs text-danger">
          <div className="font-medium">Session error</div>
          <div className="mt-1">{sendError}</div>
          <Button size="sm" variant="secondary" className="mt-2" disabled={resetSession.isPending} onClick={handleResetSession}>
            {resetSession.isPending ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
            Start fresh session
          </Button>
        </div>
      ) : null}
      {isSessionRefreshing ? (
        <div className="border-b border-border bg-surface-2 px-5 py-3 text-xs text-content-muted">
          <div className="flex items-center gap-2"><Loader2 className="h-3.5 w-3.5 animate-spin" />Starting fresh session&hellip;</div>
        </div>
      ) : null}

      {/* ---- Message thread (chat + inline activity) ---- */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="min-w-0 space-y-3 overflow-hidden px-5 py-4" data-page-agent-live-activity="true">
          {/* Persisted turns */}
          {(threadDetail?.turns ?? []).length
            ? threadDetail?.turns.map((turn) => (
                <MessageBubble key={turn.id} role={turn.role} content={turn.content} createdAt={turn.createdAt} />
              ))
            : (
                <div className="rounded-xl border border-dashed border-border bg-surface-2 px-4 py-4 text-sm text-content-muted">
                  No messages yet. Use a quick action above or type below to start.
                </div>
              )}

          {/* Optimistic user message while streaming */}
          {pendingPrompt ? <MessageBubble role="user" content={pendingPrompt} /> : null}

          {/* Inline streamed activity — compact log rows */}
          {liveActivity.length > 0 ? (
            <div className="min-w-0 space-y-1 overflow-hidden rounded-lg bg-surface-2/50 px-3 py-2">
              {liveActivity.length > VISIBLE_ACTIVITY_COUNT ? (
                <div className="text-[11px] text-content-muted">{liveActivity.length - VISIBLE_ACTIVITY_COUNT} more step{liveActivity.length - VISIBLE_ACTIVITY_COUNT === 1 ? "" : "s"}&hellip;</div>
              ) : null}
              {liveActivity.slice(-VISIBLE_ACTIVITY_COUNT).map((item) => (
                <ActivityRow key={item.id} item={item} />
              ))}
              {isStreaming ? (
                <div className="flex items-center gap-1.5 text-[11px] text-content-muted">
                  <Loader2 className="h-3 w-3 animate-spin" />Working&hellip;
                </div>
              ) : null}
            </div>
          ) : isBusy ? (
            <div className="flex items-center gap-2 rounded-lg bg-surface-2/50 px-3 py-2 text-[11px] text-content-muted">
              <Loader2 className="h-3 w-3 animate-spin" />Hermes is working&hellip;
            </div>
          ) : null}

          {/* Approval card */}
          {canApprove ? (
            <div className="rounded-xl border border-border/70 bg-surface-2 px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-medium text-content">Draft ready</div>
                  <div className="text-xs text-content-muted">
                    {lastAssistantTurn?.sitePageVersionId
                      ? "Approve to promote this page draft."
                      : "Approve this generated artifact."}
                  </div>
                </div>
                <Badge tone={threadDetail?.thread.status === "approved" ? "success" : "warning"}>
                  {threadDetail?.thread.status === "approved" ? "Approved" : "Review"}
                </Badge>
              </div>
              <div className="mt-3 flex gap-2">
                <Button size="sm" disabled={resolveApproval.isPending || threadDetail?.thread.status === "approved"} onClick={() => handleApprove("approved")}>
                  <Check className="mr-2 h-4 w-4" />Approve
                </Button>
                <Button size="sm" variant="secondary" disabled={resolveApproval.isPending} onClick={() => handleApprove("rejected")}>
                  <X className="mr-2 h-4 w-4" />Reject
                </Button>
              </div>
            </div>
          ) : null}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {/* ---- Input ---- */}
      <div className="border-t border-border px-5 py-3">
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Tell Hermes what to change on this page."
          className="min-h-[80px] resize-none"
          disabled={!threadId || isBusy}
          onKeyDown={(event) => { if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); void handleSend(draft); } }}
        />
        <div className="mt-2 flex items-center justify-between gap-2">
          <div className="text-[11px] text-content-muted">{navigator.platform?.includes("Mac") ? "\u2318" : "Ctrl"}+Enter to send</div>
          <Button size="sm" disabled={!draft.trim() || !threadId || isBusy} onClick={() => { void handleSend(draft); }}>
            {isStreaming ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}Send
          </Button>
        </div>
      </div>
    </div>
  );
}

/** @deprecated Use PageAgentPanel instead for the overlay experience. */
export function PageAgentSidebar(props: Props) {
  return (
    <aside className="ds-card ds-card--md sticky top-4 flex h-[calc(100vh-8rem)] flex-col overflow-hidden shadow-none">
      <PageAgentSidebarContent {...props} />
    </aside>
  );
}
