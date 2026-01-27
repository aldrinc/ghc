import { useEffect, useMemo, useRef, useState } from "react";
import type { ClaudeStreamHandle } from "@/api/claude";
import { useClaudeContext, useClaudeStream } from "@/api/claude";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { toast } from "@/components/ui/toast";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { ClaudeContextFile, ClaudeStreamEvent } from "@/types/claude";
import type { ApiError } from "@/api/client";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "error" | "done";
};

function useUuid() {
  return () => {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return crypto.randomUUID();
    }
    return Math.random().toString(36).slice(2);
  };
}

function ContextDocItem({
  doc,
  selected,
  onToggle,
}: {
  doc: ClaudeContextFile;
  selected: boolean;
  onToggle: (fileId: string) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border/70 bg-surface p-3 transition hover:border-border hover:bg-surface-2">
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(doc.claude_file_id)}
        className="mt-1 size-4 rounded border-border text-primary focus:ring-2 focus:ring-primary"
      />
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-sm font-semibold text-content">
            {doc.doc_title || doc.doc_key || "Context file"}
          </div>
          {doc.source_kind ? <Badge tone="accent">{doc.source_kind}</Badge> : null}
          {doc.step_key ? <Badge tone="neutral">Step {doc.step_key}</Badge> : null}
        </div>
        <div className="text-xs text-content-muted">
          {doc.filename || "Unknown filename"}
          {doc.mime_type ? ` • ${doc.mime_type}` : ""}
          {doc.size_bytes ? ` • ${(doc.size_bytes / 1024).toFixed(0)} KB` : ""}
        </div>
        <div className="text-[11px] text-content-muted/80 break-all">
          file_id: {doc.claude_file_id}
        </div>
      </div>
    </label>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl whitespace-pre-wrap rounded-lg px-3 py-2 text-sm shadow-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-surface text-content border border-border/70"
        }`}
      >
        {message.content || (message.status === "streaming" ? "…" : "")}
        {message.status === "error" ? (
          <div className="mt-1 text-[11px] font-medium uppercase tracking-wide text-warning">
            error
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ClaudeChatPage() {
  const { workspace } = useWorkspace();
  const { data: contextData, isLoading: isLoadingContext, refetch } = useClaudeContext({
    ideaWorkspaceId: workspace?.id,
    clientId: workspace?.id,
  });
  const sendClaude = useClaudeStream();
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const streamRef = useRef<ClaudeStreamHandle | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const makeId = useUuid();

  const contextFiles = useMemo(() => contextData?.files || [], [contextData?.files]);

  useEffect(() => {
    if (contextFiles.length) {
      setSelectedFiles(contextFiles.map((f) => f.claude_file_id));
    }
  }, [contextFiles]);

  useEffect(() => {
    if (!bottomRef.current) return;
    bottomRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toggleFile = (fileId: string) => {
    setSelectedFiles((prev) =>
      prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]
    );
  };

  const handleEvent = (assistantId: string) => (event: ClaudeStreamEvent) => {
    if (event.type === "text") {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId ? { ...msg, content: msg.content + event.text } : msg
        )
      );
    } else if (event.type === "error") {
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? { ...msg, status: "error" } : msg))
      );
      setIsStreaming(false);
      toast.error(event.message);
    } else if (event.type === "done") {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId ? { ...msg, status: "done" } : msg
        )
      );
      setIsStreaming(false);
    }
  };

  const sendMessage = async () => {
    if (!workspace) {
      toast.error("Select a workspace to chat with Claude.");
      return;
    }
    const prompt = draft.trim();
    if (!prompt) return;

    if (isStreaming) {
      toast.info("Finishing the current response—please wait.");
      return;
    }

    const assistantId = makeId();
    setMessages((prev) => [
      ...prev,
      { id: makeId(), role: "user", content: prompt },
      { id: assistantId, role: "assistant", content: "", status: "streaming" },
    ]);
    setDraft("");
    setIsStreaming(true);

    try {
      const handle = await sendClaude(
        {
          prompt,
          ideaWorkspaceId: workspace.id,
          clientId: workspace.id,
          fileIds: selectedFiles,
        },
        handleEvent(assistantId)
      );
      streamRef.current = handle;
    } catch (err) {
      setIsStreaming(false);
      const message =
        (err as ApiError)?.message || (err as Error)?.message || "Failed to reach Claude";
      toast.error(message);
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? { ...msg, status: "error" } : msg))
      );
    }
  };

  const stopStream = () => {
    streamRef.current?.abort();
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((msg) => (msg.status === "streaming" ? { ...msg, status: "done" } : msg))
    );
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Claude Chat" description="Select a workspace to load context files." />
        <div className="ds-card ds-card--md ds-card--empty max-w-3xl text-center text-sm">
          Choose a workspace from the sidebar to start chatting with Claude.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Claude Chat"
        description="Chat with Claude using your workspace context files. Attach the documents below to ground responses."
        actions={
          <div className="flex items-center gap-2 text-xs text-content-muted">
            {isLoadingContext ? "Loading context…" : `${contextFiles.length} docs available`}
            <Button variant="ghost" size="sm" onClick={() => refetch()}>
              Refresh
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1.1fr_2fr]">
        <div className="space-y-3">
          <div className="ds-card ds-card--md shadow-none">
            <div className="flex items-center justify-between pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Available context</div>
                <div className="text-xs text-content-muted">
                  Toggle which Claude files are attached to each message.
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone="accent">
                  {selectedFiles.length}/{contextFiles.length} attached
                </Badge>
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() =>
                    setSelectedFiles((prev) =>
                      prev.length === contextFiles.length
                        ? []
                        : contextFiles.map((f) => f.claude_file_id)
                    )
                  }
                >
                  {selectedFiles.length === contextFiles.length ? "Deselect all" : "Attach all"}
                </Button>
              </div>
            </div>

            {isLoadingContext ? (
              <div className="text-sm text-content-muted">Loading documents…</div>
            ) : !contextFiles.length ? (
              <div className="ds-card ds-card--empty text-center text-sm">
                No Claude documents found for this workspace yet.
              </div>
            ) : (
              <div className="space-y-3">
                {contextFiles.map((doc) => (
                  <ContextDocItem
                    key={doc.claude_file_id}
                    doc={doc}
                    selected={selectedFiles.includes(doc.claude_file_id)}
                    onToggle={toggleFile}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="ds-card ds-card--md shadow-none">
          <div className="flex items-center justify-between pb-3">
            <div>
              <div className="text-sm font-semibold text-content">Chat</div>
              <div className="text-xs text-content-muted">
                Messages stream live from Claude with the selected document blocks attached.
              </div>
            </div>
            {isStreaming ? (
              <Button variant="secondary" size="sm" onClick={stopStream}>
                Stop
              </Button>
            ) : null}
          </div>
          <Separator className="mb-3" />
          <ScrollArea className="h-[480px]">
            <div className="space-y-3 pr-2">
              {messages.length === 0 ? (
                <div className="ds-card ds-card--empty text-center text-sm">
                  Start the conversation — Claude will use the attached documents.
                </div>
              ) : (
                <>
                  {messages.map((msg) => (
                    <MessageBubble key={msg.id} message={msg} />
                  ))}
                  <div ref={bottomRef} />
                </>
              )}
            </div>
          </ScrollArea>
          <Separator className="my-3" />
          <div className="space-y-2">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask Claude to generate new marketing copy, campaign ideas, or strategy grounded in your docs…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void sendMessage();
                }
              }}
              disabled={isStreaming}
            />
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs text-content-muted">
                {selectedFiles.length
                  ? `${selectedFiles.length} document${selectedFiles.length > 1 ? "s" : ""} attached`
                  : "No documents attached — Claude will respond without context."}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => setDraft("")} disabled={!draft}>
                  Clear
                </Button>
                <Button onClick={() => void sendMessage()} disabled={isStreaming || !draft.trim()}>
                  {isStreaming ? "Streaming…" : "Send to Claude"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
