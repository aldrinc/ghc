import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ClaudeStreamHandle } from "@/api/claude";
import { useClaudeContext, useClaudeStream } from "@/api/claude";
import type { GeminiStreamHandle } from "@/api/gemini";
import { useGeminiContext, useGeminiStream } from "@/api/gemini";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { toast } from "@/components/ui/toast";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import type { ClaudeContextFile, ClaudeStreamEvent } from "@/types/claude";
import type { GeminiCitation, GeminiContextFile, GeminiStreamEvent } from "@/types/gemini";
import type { ApiError } from "@/api/client";
import { ArrowUp, Square } from "lucide-react";

type ChatProvider = "claude" | "gemini";
type StreamHandle = ClaudeStreamHandle | GeminiStreamHandle;
type StreamEvent = ClaudeStreamEvent | GeminiStreamEvent;

type ContextDoc = {
  id: string;
  provider: ChatProvider;
  providerFileId: string;
  doc_key?: string | null;
  doc_title?: string | null;
  source_kind?: string | null;
  step_key?: string | null;
  filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  drive_url?: string | null;
  created_at?: string | null;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "error" | "done" | "stopped";
  attachedFileIds?: string[];
  citations?: GeminiCitation[];
};

function getApiErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (typeof (err as ApiError)?.message === "string") {
    return (err as ApiError).message;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return null;
}

function useUuid() {
  return () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
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
  doc: ContextDoc;
  selected: boolean;
  onToggle: (fileId: string) => void;
}) {
  const idLabel = doc.provider === "gemini" ? "document_name" : "file_id";
  return (
    <label className="group flex cursor-pointer items-start gap-3 rounded-xl border border-border/60 bg-surface px-3 py-3 shadow-sm transition hover:border-border hover:bg-surface-2">
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(doc.providerFileId)}
        className="mt-1 size-4 rounded-md border-border/60 text-primary focus:ring-2 focus:ring-primary"
      />
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-[13px] font-semibold text-content">
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
          {idLabel}: {doc.providerFileId}
        </div>
      </div>
    </label>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const attachedCount = message.attachedFileIds?.length ?? 0;
  const citationCount = message.citations?.length ?? 0;
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl whitespace-pre-wrap text-[15px] leading-6 ${
          isUser
            ? "rounded-2xl border border-border/60 bg-surface-2 px-4 py-3 text-content shadow-sm"
            : "px-1 py-1 text-content"
        }`}
      >
        {message.content || (message.status === "streaming" ? "…" : "")}
        {attachedCount ? (
          <div
            className={`mt-2 text-[11px] ${isUser ? "text-content-muted" : "text-content-muted"}`}
          >
            {attachedCount} source{attachedCount > 1 ? "s" : ""} attached
          </div>
        ) : null}
        {!isUser && citationCount ? (
          <div className="mt-2 space-y-1 text-[11px] text-content-muted">
            <div>{citationCount} citation{citationCount > 1 ? "s" : ""}</div>
            {message.citations?.slice(0, 5).map((citation, idx) => {
              const label = citation.title || citation.document_name || citation.uri || "Source";
              return (
                <div key={`${label}-${idx}`} className="truncate">
                  {label}
                </div>
              );
            })}
          </div>
        ) : null}
        {message.status === "error" ? (
          <div className="mt-1 text-[11px] font-medium uppercase tracking-wide text-warning">
            error
          </div>
        ) : null}
        {message.status === "stopped" ? (
          <div className="mt-1 text-[11px] font-medium uppercase tracking-wide text-content-muted">
            stopped
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ClaudeChatPage() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const [provider, setProvider] = useState<ChatProvider>("claude");
  const providerLabel = provider === "claude" ? "Claude" : "Gemini File Search";
  const isClaudeProvider = provider === "claude";
  const isGeminiProvider = provider === "gemini";
  const { data: claudeContextData, isLoading: isLoadingClaudeContext, error: claudeContextError } =
    useClaudeContext({
      ideaWorkspaceId: isClaudeProvider && product?.id ? workspace?.id : undefined,
      clientId: isClaudeProvider && product?.id ? workspace?.id : undefined,
      productId: isClaudeProvider ? product?.id : undefined,
    });
  const { data: geminiContextData, isLoading: isLoadingGeminiContext, error: geminiContextError } =
    useGeminiContext({
      ideaWorkspaceId: isGeminiProvider && product?.id ? workspace?.id : undefined,
      clientId: isGeminiProvider && product?.id ? workspace?.id : undefined,
      productId: isGeminiProvider ? product?.id : undefined,
    });
  const sendClaude = useClaudeStream();
  const sendGemini = useGeminiStream();
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [contextQuery, setContextQuery] = useState("");
  const [isAtBottom, setIsAtBottom] = useState(true);
  const streamRef = useRef<StreamHandle | null>(null);
  const streamBufferRef = useRef<Record<string, string>>({});
  const flushHandleRef = useRef<number | null>(null);
  const hasManualSelectionRef = useRef(false);
  const scrollAreaRef = useRef<HTMLDivElement | null>(null);
  const scrollViewportRef = useRef<HTMLDivElement | null>(null);
  const isAtBottomRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const makeId = useUuid();

  const contextFiles = useMemo<ContextDoc[]>(() => {
    if (provider === "claude") {
      return (claudeContextData?.files || []).map((doc: ClaudeContextFile) => ({
        id: doc.id,
        provider: "claude",
        providerFileId: doc.claude_file_id,
        doc_key: doc.doc_key,
        doc_title: doc.doc_title,
        source_kind: doc.source_kind,
        step_key: doc.step_key,
        filename: doc.filename,
        mime_type: doc.mime_type,
        size_bytes: doc.size_bytes,
        drive_url: doc.drive_url,
        created_at: doc.created_at,
      }));
    }
    return (geminiContextData?.files || []).map((doc: GeminiContextFile) => ({
      id: doc.id,
      provider: "gemini",
      providerFileId: doc.gemini_document_name,
      doc_key: doc.doc_key,
      doc_title: doc.doc_title,
      source_kind: doc.source_kind,
      step_key: doc.step_key,
      filename: doc.filename,
      mime_type: doc.mime_type,
      size_bytes: doc.size_bytes,
      drive_url: doc.drive_url,
      created_at: doc.created_at,
    }));
  }, [provider, claudeContextData?.files, geminiContextData?.files]);
  const isLoadingContext = isClaudeProvider ? isLoadingClaudeContext : isLoadingGeminiContext;
  const contextErrorMessage = isClaudeProvider
    ? getApiErrorMessage(claudeContextError)
    : getApiErrorMessage(geminiContextError);
  const attachedDocs = useMemo(
    () => contextFiles.filter((doc) => selectedFiles.includes(doc.providerFileId)),
    [contextFiles, selectedFiles]
  );
  const filteredDocs = useMemo(() => {
    const query = contextQuery.trim().toLowerCase();
    if (!query) return contextFiles;
    return contextFiles.filter((doc) => {
      const haystack = [
        doc.doc_title,
        doc.doc_key,
        doc.filename,
        doc.source_kind,
        doc.step_key,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [contextFiles, contextQuery]);
  const filteredDocIds = useMemo(
    () => new Set(filteredDocs.map((doc) => doc.providerFileId)),
    [filteredDocs]
  );
  const filteredAttachedDocs = useMemo(
    () => attachedDocs.filter((doc) => filteredDocIds.has(doc.providerFileId)),
    [attachedDocs, filteredDocIds]
  );
  const unattachedDocs = useMemo(
    () => filteredDocs.filter((doc) => !selectedFiles.includes(doc.providerFileId)),
    [filteredDocs, selectedFiles]
  );

  useEffect(() => {
    setSelectedFiles((prev) => {
      const validSelections = prev.filter((id) =>
        contextFiles.some((file) => file.providerFileId === id)
      );
      if (!hasManualSelectionRef.current && contextFiles.length) {
        return contextFiles.map((file) => file.providerFileId);
      }
      return validSelections;
    });
  }, [contextFiles]);

  useEffect(() => {
    setSelectedFiles([]);
    setMessages([]);
    setDraft("");
    setContextQuery("");
    setIsStreaming(false);
    streamRef.current?.abort();
    streamRef.current = null;
    hasManualSelectionRef.current = false;
    streamBufferRef.current = {};
  }, [provider]);

  useEffect(() => {
    setSelectedFiles([]);
    setMessages([]);
    setDraft("");
    setContextQuery("");
    setIsStreaming(false);
    streamRef.current?.abort();
    streamRef.current = null;
    hasManualSelectionRef.current = false;
    streamBufferRef.current = {};
  }, [workspace?.id]);

  useEffect(() => {
    const root = scrollAreaRef.current;
    if (!root) return;
    const viewport = root.querySelector<HTMLDivElement>("[data-base-ui-scroll-area-viewport]");
    if (!viewport) return;
    scrollViewportRef.current = viewport;

    const handleScroll = () => {
      const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
      const nearBottom = distanceFromBottom < 80;
      if (nearBottom !== isAtBottomRef.current) {
        isAtBottomRef.current = nearBottom;
        setIsAtBottom(nearBottom);
      }
    };

    handleScroll();
    viewport.addEventListener("scroll", handleScroll);
    return () => viewport.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const viewport = scrollViewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior });
  }, []);

  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollToBottom("auto");
    }
  }, [messages, scrollToBottom]);

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    const nextHeight = Math.min(textarea.scrollHeight, 160);
    textarea.style.height = `${nextHeight}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [draft, resizeTextarea]);

  useEffect(() => {
    return () => {
      if (flushHandleRef.current !== null) {
        cancelAnimationFrame(flushHandleRef.current);
      }
      streamRef.current?.abort();
      streamRef.current = null;
    };
  }, []);

  const toggleFile = (fileId: string) => {
    hasManualSelectionRef.current = true;
    setSelectedFiles((prev) =>
      prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]
    );
  };

  const flushStreamBuffer = useCallback(() => {
    if (flushHandleRef.current !== null) return;
    flushHandleRef.current = requestAnimationFrame(() => {
      flushHandleRef.current = null;
      const buffers = streamBufferRef.current;
      if (!Object.keys(buffers).length) return;
      setMessages((prev) =>
        prev.map((msg) => {
          const chunk = buffers[msg.id];
          if (!chunk) return msg;
          return { ...msg, content: msg.content + chunk };
        })
      );
      streamBufferRef.current = {};
    });
  }, []);

  const flushStreamBufferNow = useCallback(() => {
    if (flushHandleRef.current !== null) {
      cancelAnimationFrame(flushHandleRef.current);
      flushHandleRef.current = null;
    }
    const buffers = streamBufferRef.current;
    if (!Object.keys(buffers).length) return;
    setMessages((prev) =>
      prev.map((msg) => {
        const chunk = buffers[msg.id];
        if (!chunk) return msg;
        return { ...msg, content: msg.content + chunk };
      })
    );
    streamBufferRef.current = {};
  }, []);

  const handleEvent = (assistantId: string, activeProvider: ChatProvider) => (event: StreamEvent) => {
    if (event.type === "text") {
      streamBufferRef.current[assistantId] =
        (streamBufferRef.current[assistantId] ?? "") + event.text;
      flushStreamBuffer();
    } else if (event.type === "error") {
      flushStreamBufferNow();
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? { ...msg, status: "error" } : msg))
      );
      setIsStreaming(false);
      streamRef.current = null;
      toast.error(event.message);
    } else if (event.type === "done") {
      flushStreamBufferNow();
      const citations =
        activeProvider === "gemini" && "citations" in event && Array.isArray(event.citations)
          ? event.citations
          : undefined;
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId ? { ...msg, status: "done", citations } : msg
        )
      );
      setIsStreaming(false);
      streamRef.current = null;
    }
  };

  const sendMessage = async () => {
    if (!workspace) {
      toast.error(`Select a workspace to chat with ${providerLabel}.`);
      return;
    }
    if (!product?.id) {
      toast.error(`Select a product to chat with ${providerLabel}.`);
      return;
    }
    const prompt = draft.trim();
    if (!prompt) return;

    if (isStreaming) {
      toast.info("Finishing the current response—please wait.");
      return;
    }

    const attachedFileIds = [...selectedFiles];
    const assistantId = makeId();
    setMessages((prev) => [
      ...prev,
      { id: makeId(), role: "user", content: prompt, attachedFileIds },
      { id: assistantId, role: "assistant", content: "", status: "streaming" },
    ]);
    setDraft("");
    setIsStreaming(true);

    try {
      const payload = {
        prompt,
        ideaWorkspaceId: workspace.id,
        clientId: workspace.id,
        productId: product.id,
        fileIds: attachedFileIds,
      };
      const handle =
        provider === "claude"
          ? await sendClaude(payload, handleEvent(assistantId, provider))
          : await sendGemini(payload, handleEvent(assistantId, provider));
      streamRef.current = handle;
    } catch (err) {
      setIsStreaming(false);
      const message =
        (err as ApiError)?.message || (err as Error)?.message || `Failed to reach ${providerLabel}`;
      toast.error(message);
      streamRef.current = null;
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? { ...msg, status: "error" } : msg))
      );
    }
  };

  const stopStream = () => {
    streamRef.current?.abort();
    streamRef.current = null;
    flushStreamBufferNow();
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((msg) => (msg.status === "streaming" ? { ...msg, status: "stopped" } : msg))
    );
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Assistant Chat" description="Select a workspace to load context files." />
        <div className="ds-card ds-card--md ds-card--empty max-w-3xl text-center text-sm">
          Choose a workspace from the sidebar to start chatting.
        </div>
      </div>
    );
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Assistant Chat" description="Select a product to load context files." />
        <div className="ds-card ds-card--md ds-card--empty max-w-3xl text-center text-sm">
          Choose a product from the header to start chatting.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Assistant Chat" />
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant={isClaudeProvider ? "default" : "secondary"}
          onClick={() => setProvider("claude")}
          disabled={isStreaming}
        >
          Claude
        </Button>
        <Button
          size="sm"
          variant={isGeminiProvider ? "default" : "secondary"}
          onClick={() => setProvider("gemini")}
          disabled={isStreaming}
        >
          Gemini File Search
        </Button>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="flex min-h-[calc(100vh-220px)] flex-col">
          <div className="relative flex min-h-0 flex-1 flex-col">
            <ScrollArea
              ref={scrollAreaRef}
              className="flex-1 border-0 bg-transparent"
              viewportClassName="h-full"
            >
              <div className="mx-auto w-full max-w-3xl space-y-6 px-1 py-6 pb-28">
                  {messages.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-border/70 bg-surface-2 px-6 py-10 text-center text-sm text-content-muted">
                      Start the conversation and {providerLabel} will ground answers in your documents.
                    </div>
                  ) : (
                    messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)
                  )}
              </div>
            </ScrollArea>
            {!isAtBottom && messages.length ? (
              <Button
                variant="secondary"
                size="sm"
                className="absolute bottom-6 right-6 shadow-sm"
                onClick={() => scrollToBottom("smooth")}
              >
                Jump to latest
              </Button>
            ) : null}
          </div>
          <div className="sticky bottom-0 z-10 border-t border-border/60 bg-surface/95 py-4 backdrop-blur">
            <div className="rounded-3xl border border-border/70 bg-surface-2 px-4 py-3 shadow-sm focus-within:border-border focus-within:ring-2 focus-within:ring-border/40">
              <div className="flex items-end gap-3">
                <textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onInput={resizeTextarea}
                  placeholder={`Message ${providerLabel}`}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
                      e.preventDefault();
                      void sendMessage();
                    }
                  }}
                  rows={1}
                  aria-label={`Message ${providerLabel}`}
                  className="min-h-[44px] flex-1 resize-none bg-transparent text-[15px] text-content placeholder:text-content-muted focus-visible:outline-none"
                />
                <div className="flex items-center gap-2 pb-1">
                  {isStreaming ? (
                    <Button
                      variant="secondary"
                      size="icon"
                      className="h-10 w-10 rounded-full"
                      onClick={stopStream}
                      aria-label="Stop generating"
                    >
                      <Square className="h-4 w-4" />
                    </Button>
                  ) : null}
                  <Button
                    size="icon"
                    className="h-10 w-10 rounded-full bg-primary text-primary-foreground hover:bg-primary/90"
                    onClick={() => void sendMessage()}
                    disabled={isStreaming || !draft.trim()}
                    aria-label="Send message"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-content-muted">
                <div>Enter to send, Shift+Enter for newline</div>
                <div className="flex items-center gap-2">
                  <span>
                    {selectedFiles.length
                      ? `${selectedFiles.length} document${selectedFiles.length > 1 ? "s" : ""} attached`
                      : "No documents attached"}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-[11px]"
                    onClick={() => setDraft("")}
                    disabled={!draft}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <aside className="flex min-h-0 max-h-[70vh] flex-col px-4 py-4 xl:border-l xl:border-border/60">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-content">Documents</div>
              <div className="text-xs text-content-muted">
                Attach sources to ground {providerLabel} responses.
              </div>
            </div>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                hasManualSelectionRef.current = true;
                setSelectedFiles((prev) =>
                  prev.length === contextFiles.length
                    ? []
                    : contextFiles.map((f) => f.providerFileId)
                );
              }}
              disabled={!contextFiles.length}
            >
              {selectedFiles.length === contextFiles.length ? "Clear all" : "Attach all"}
            </Button>
          </div>
          <Separator className="my-4" />
          <div className="space-y-3">
            <Input
              value={contextQuery}
              onChange={(e) => setContextQuery(e.target.value)}
              placeholder="Search documents"
              className="h-9 rounded-full border-border/60 bg-surface px-4 text-xs"
            />
            <div className="flex items-center justify-between text-xs text-content-muted">
              <Badge tone="accent">
                {selectedFiles.length}/{contextFiles.length} attached
              </Badge>
              {selectedFiles.length === contextFiles.length
                ? "All docs attached"
                : "Partial selection"}
            </div>
          </div>
          <Separator className="my-4" />
          {isLoadingContext ? (
            <div className="text-sm text-content-muted">Loading documents…</div>
          ) : contextErrorMessage ? (
            <div className="rounded-2xl border border-dashed border-border/70 bg-surface px-4 py-6 text-center text-xs text-warning">
              {contextErrorMessage}
            </div>
          ) : !contextFiles.length ? (
            <div className="rounded-2xl border border-dashed border-border/70 bg-surface px-4 py-6 text-center text-xs text-content-muted">
              No {providerLabel} documents found for this workspace yet.
            </div>
          ) : (
            <ScrollArea className="min-h-0 flex-1 border-0 bg-transparent" viewportClassName="h-full">
              <div className="space-y-4 pr-1">
                {filteredAttachedDocs.length ? (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                      Attached
                    </div>
                    {filteredAttachedDocs.map((doc) => (
                      <ContextDocItem
                        key={doc.providerFileId}
                        doc={doc}
                        selected={selectedFiles.includes(doc.providerFileId)}
                        onToggle={toggleFile}
                      />
                    ))}
                  </div>
                ) : null}
                <div className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    All documents
                  </div>
                  {unattachedDocs.length ? (
                    <div className="space-y-3">
                      {unattachedDocs.map((doc) => (
                        <ContextDocItem
                          key={doc.providerFileId}
                          doc={doc}
                          selected={selectedFiles.includes(doc.providerFileId)}
                          onToggle={toggleFile}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-content-muted">
                      {contextQuery
                        ? `No documents match "${contextQuery}".`
                        : "All available documents are already attached."}
                    </div>
                  )}
                </div>
              </div>
            </ScrollArea>
          )}
        </aside>
      </div>
    </div>
  );
}
