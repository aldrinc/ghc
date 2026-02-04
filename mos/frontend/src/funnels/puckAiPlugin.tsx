import { createUsePuck, type Data, type Plugin } from "@measured/puck";
import { useAuth } from "@clerk/clerk-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { FunnelAIChatMessage } from "@/types/funnels";
import { normalizePuckData } from "@/funnels/puckData";

type FunnelAiPluginOptions = {
  funnelId?: string;
  pageId?: string;
  templateId?: string;
  ideaWorkspaceId?: string;
  apiBaseUrl: string;
  clerkTokenTemplate: string;
};

type FunnelAiFieldsProps = FunnelAiPluginOptions & {
  children: ReactNode;
};

const usePuck = createUsePuck();

const AI_ATTACHMENT_MAX = 8;

type AiAttachment = {
  id: string;
  name: string;
  size: number;
  previewUrl: string;
  status: "uploading" | "ready" | "error";
  error?: string;
  assetId?: string;
  publicId?: string;
  contentType?: string;
  width?: number | null;
  height?: number | null;
};

const makeAttachmentId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `att-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

type StoredAiState = {
  prompt?: string;
  messages?: FunnelAIChatMessage[];
  generateImages?: boolean;
  maxImages?: string;
};

function readStoredAiState(key: string | null): StoredAiState | null {
  if (!key) return null;
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as StoredAiState;
  } catch {
    return null;
  }
}

function writeStoredAiState(key: string | null, state: StoredAiState): void {
  if (!key) return;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(state));
  } catch {
    // Ignore storage errors (privacy mode, quota, etc.)
  }
}

function clearStoredAiState(key: string | null): void {
  if (!key) return;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // Ignore storage errors
  }
}

function parseJsonObject(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const withoutFences = trimmed.replace(/^\s*```(?:json)?\s*/i, "").replace(/\s*```\s*$/, "");
  try {
    const parsed = JSON.parse(withoutFences) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // fall through to substring parse
  }
  const start = withoutFences.indexOf("{");
  const end = withoutFences.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return null;
  try {
    const parsed = JSON.parse(withoutFences.slice(start, end + 1)) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

function MessageBubble({ role, content }: { role: "user" | "assistant"; content: string }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl whitespace-pre-wrap rounded-lg px-3 py-2 text-sm shadow-sm ${
          isUser ? "bg-primary text-primary-foreground" : "bg-surface text-content border border-border/70"
        }`}
      >
        {content}
      </div>
    </div>
  );
}

function FunnelAiFields({ children, ...options }: FunnelAiFieldsProps) {
  const [activeTab, setActiveTab] = useState<"fields" | "ai">("fields");

  return (
    <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "fields" | "ai")} className="flex h-full flex-col">
      <div className="border-b border-border bg-surface px-2 py-2">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="fields" className="min-w-[88px] px-2 py-1 text-xs">
            Fields
          </TabsTrigger>
          <TabsTrigger value="ai" className="min-w-[120px] px-2 py-1 text-xs">
            AI assistant
          </TabsTrigger>
        </TabsList>
      </div>
      <div className="flex-1 min-h-0">
        <TabsContent value="fields" className="mt-0 h-full border-0 bg-transparent p-0 shadow-none">
          {children}
        </TabsContent>
        <TabsContent value="ai" className="mt-0 h-full border-0 bg-transparent p-0 shadow-none">
          <AiAssistantPanel {...options} />
        </TabsContent>
      </div>
    </Tabs>
  );
}

function AiAssistantPanel({ funnelId, pageId, templateId, ideaWorkspaceId, apiBaseUrl, clerkTokenTemplate }: FunnelAiPluginOptions) {
  const appState = usePuck((state) => state.appState);
  const dispatch = usePuck((state) => state.dispatch);
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const storageKey = pageId ? `funnel-ai:${funnelId ?? "unknown"}:${pageId}` : null;

  const [aiMessages, setAiMessages] = useState<FunnelAIChatMessage[]>([]);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiGenerateImages, setAiGenerateImages] = useState(true);
  const [aiMaxImages, setAiMaxImages] = useState("3");
  const [aiIsGenerating, setAiIsGenerating] = useState(false);
  const [aiStreamText, setAiStreamText] = useState<string | null>(null);
  const [aiRawStreamText, setAiRawStreamText] = useState<string | null>(null);
  const [aiGeneratedImages, setAiGeneratedImages] = useState<Array<Record<string, unknown>>>([]);
  const [aiAttachments, setAiAttachments] = useState<AiAttachment[]>([]);
  const aiBottomRef = useRef<HTMLDivElement | null>(null);
  const aiFileInputRef = useRef<HTMLInputElement | null>(null);
  const aiAbortRef = useRef<AbortController | null>(null);
  const aiAttachmentsRef = useRef<AiAttachment[]>([]);
  const rawStreamBufferRef = useRef("");
  const assistantStreamBufferRef = useRef("");
  const hasRestoredRef = useRef(false);

  useEffect(() => {
    if (!aiBottomRef.current) return;
    aiBottomRef.current.scrollIntoView({ behavior: "smooth" });
  }, [aiMessages, aiIsGenerating, aiStreamText, aiRawStreamText]);

  useEffect(() => {
    aiAttachmentsRef.current = aiAttachments;
  }, [aiAttachments]);

  useEffect(() => {
    if (!pageId || !storageKey) return;
    if (aiAbortRef.current) aiAbortRef.current.abort();
    aiAbortRef.current = null;
    hasRestoredRef.current = false;
    const stored = readStoredAiState(storageKey);
    if (stored) {
      setAiMessages(Array.isArray(stored.messages) ? stored.messages : []);
      setAiPrompt(typeof stored.prompt === "string" ? stored.prompt : "");
      setAiGenerateImages(typeof stored.generateImages === "boolean" ? stored.generateImages : true);
      setAiMaxImages(typeof stored.maxImages === "string" ? stored.maxImages : "3");
    } else {
      setAiMessages([]);
      setAiPrompt("");
      setAiGenerateImages(true);
      setAiMaxImages("3");
    }
    setAiStreamText(null);
    setAiRawStreamText(null);
    setAiIsGenerating(false);
    setAiGeneratedImages([]);
    setAiAttachments((prev) => {
      prev.forEach((item) => URL.revokeObjectURL(item.previewUrl));
      return [];
    });
    rawStreamBufferRef.current = "";
    assistantStreamBufferRef.current = "";
    hasRestoredRef.current = true;
  }, [pageId, storageKey]);

  useEffect(() => {
    if (!storageKey || !hasRestoredRef.current) return;
    writeStoredAiState(storageKey, {
      prompt: aiPrompt,
      messages: aiMessages,
      generateImages: aiGenerateImages,
      maxImages: aiMaxImages,
    });
  }, [storageKey, aiPrompt, aiMessages, aiGenerateImages, aiMaxImages]);

  useEffect(() => {
    return () => {
      if (aiAbortRef.current) aiAbortRef.current.abort();
      aiAttachmentsRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    };
  }, []);

  const handleClear = () => {
    setAiMessages([]);
    setAiPrompt("");
    setAiStreamText(null);
    setAiRawStreamText(null);
    setAiIsGenerating(false);
    setAiGeneratedImages([]);
    rawStreamBufferRef.current = "";
    assistantStreamBufferRef.current = "";
    clearStoredAiState(storageKey);
  };

  const aiAttachmentsUploading = aiAttachments.some((item) => item.status === "uploading");
  const aiReadyAttachments = aiAttachments.filter((item) => item.status === "ready" && item.assetId && item.publicId);

  const handleAttachmentSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    if (!funnelId || !pageId) {
      toast.error("Select a funnel page before attaching images.");
      return;
    }
    const remainingSlots = AI_ATTACHMENT_MAX - aiAttachments.length;
    if (remainingSlots <= 0) {
      toast.error(`You can attach up to ${AI_ATTACHMENT_MAX} images.`);
      return;
    }
    const nextFiles = files.slice(0, remainingSlots);
    if (files.length > remainingSlots) {
      toast.error(`Only ${remainingSlots} more image${remainingSlots === 1 ? "" : "s"} can be attached.`);
    }

    nextFiles.forEach((file) => {
      const id = makeAttachmentId();
      const previewUrl = URL.createObjectURL(file);
      setAiAttachments((prev) => [
        ...prev,
        { id, name: file.name, size: file.size, previewUrl, status: "uploading" },
      ]);

      const uploadAttachment = async () => {
        try {
          const token = await getToken({ template: clerkTokenTemplate, skipCache: true });
          const formData = new FormData();
          formData.append("files", file);
          const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
          const resp = await fetch(`${apiBaseUrl}/funnels/${funnelId}/pages/${pageId}/ai/attachments`, {
            method: "POST",
            headers,
            body: formData,
          });
          if (!resp.ok) {
            const raw = await resp.text();
            throw new Error(raw || "Failed to upload image");
          }
          const json = (await resp.json()) as { attachments?: Array<Record<string, unknown>> };
          const uploaded = Array.isArray(json.attachments) ? json.attachments[0] : null;
          const assetId = typeof uploaded?.assetId === "string" ? uploaded.assetId : undefined;
          const publicId = typeof uploaded?.publicId === "string" ? uploaded.publicId : undefined;
          if (!assetId || !publicId) throw new Error("Invalid attachment response");

          setAiAttachments((prev) =>
            prev.map((item) =>
              item.id === id
                ? {
                    ...item,
                    status: "ready",
                    assetId,
                    publicId,
                    contentType: typeof uploaded?.contentType === "string" ? uploaded.contentType : undefined,
                    width: typeof uploaded?.width === "number" ? uploaded.width : null,
                    height: typeof uploaded?.height === "number" ? uploaded.height : null,
                    error: undefined,
                  }
                : item
            )
          );
        } catch (err) {
          const message = err instanceof Error ? err.message : "Failed to upload image";
          setAiAttachments((prev) =>
            prev.map((item) => (item.id === id ? { ...item, status: "error", error: message } : item))
          );
          toast.error(message);
        }
      };

      void uploadAttachment();
    });

    event.target.value = "";
  };

  const handleRemoveAttachment = (id: string) => {
    setAiAttachments((prev) => {
      const target = prev.find((item) => item.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((item) => item.id !== id);
    });
  };

  const handleAiGenerate = () => {
    if (!funnelId || !pageId) return;
    const prompt = aiPrompt.trim();
    if (!prompt) return;
    if (aiAttachmentsUploading) {
      toast.error("Wait for image uploads to finish.");
      return;
    }
    const parsedMaxImages = Number.parseInt(aiMaxImages, 10);
    const maxImages = Number.isFinite(parsedMaxImages) ? Math.max(0, Math.min(10, parsedMaxImages)) : 3;

    setAiPrompt("");
    setAiMessages((prev) => [...prev, { role: "user", content: prompt }]);
    setAiStreamText("");
    setAiRawStreamText("");
    setAiGeneratedImages([]);
    setAiIsGenerating(true);
    rawStreamBufferRef.current = "";
    assistantStreamBufferRef.current = "";

    if (aiAbortRef.current) aiAbortRef.current.abort();
    const controller = new AbortController();
    aiAbortRef.current = controller;

    const run = async () => {
      const applyDraft = (draft: Record<string, unknown>) => {
        const assistantMessage =
          typeof draft.assistantMessage === "string"
            ? draft.assistantMessage
            : typeof draft.assistant_message === "string"
              ? draft.assistant_message
              : "";
        const rawPuckData =
          (draft.puckData as unknown) ??
          (draft.puck_data as unknown) ??
          (draft.puck as unknown);
        const puckData =
          typeof rawPuckData === "string" ? parseJsonObject(rawPuckData) ?? rawPuckData : rawPuckData;
        if (!puckData || typeof puckData !== "object") {
          throw new Error("AI response missing puckData.");
        }
        const nextData = normalizePuckData(puckData);
        const blocks = Array.isArray((nextData as unknown as { content?: unknown }).content)
          ? ((nextData as unknown as { content: unknown[] }).content.length || 0)
          : 0;
        if (blocks === 0) {
          throw new Error("AI returned an empty page (0 blocks). Try a more specific prompt or try again.");
        }

        setAiStreamText(null);
        setAiRawStreamText(null);
        setAiIsGenerating(false);
        rawStreamBufferRef.current = "";
        assistantStreamBufferRef.current = "";
        dispatch({ type: "setData", data: nextData as Data, recordHistory: true });
        dispatch({ type: "setUi", ui: { itemSelector: null } });
        if (Array.isArray(draft.generatedImages)) setAiGeneratedImages(draft.generatedImages as Array<Record<string, unknown>>);
        setAiMessages((prev) => [...prev, { role: "assistant", content: assistantMessage || "Draft generated." }]);
        toast.success(`AI draft applied (${blocks} blocks)`);
        queryClient.invalidateQueries({ queryKey: ["funnels", "page", funnelId, pageId] });
        queryClient.invalidateQueries({ queryKey: ["funnels", "detail", funnelId] });
      };

      const fallbackNonStream = async (headers: Headers) => {
        const resp = await fetch(`${apiBaseUrl}/funnels/${funnelId}/pages/${pageId}/ai/generate`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            prompt,
            messages: aiMessages,
            attachedAssets: aiReadyAttachments.map((item) => ({
              assetId: item.assetId,
              publicId: item.publicId,
              filename: item.name,
              contentType: item.contentType,
              width: item.width ?? null,
              height: item.height ?? null,
            })),
            currentPuckData: appState.data,
            templateId,
            ideaWorkspaceId,
            generateImages: aiGenerateImages,
            maxImages,
          }),
          signal: controller.signal,
        });

        if (!resp.ok) {
          const raw = await resp.text();
          throw new Error(raw || resp.statusText || "Failed to generate AI draft");
        }

        const json = (await resp.json()) as unknown;
        if (!json || typeof json !== "object") throw new Error("Invalid AI response");
        applyDraft(json as Record<string, unknown>);
      };

      try {
        const token = await getToken({ template: clerkTokenTemplate, skipCache: true });
        const headers = new Headers();
        headers.set("Content-Type", "application/json");
        if (token) headers.set("Authorization", `Bearer ${token}`);

        const resp = await fetch(`${apiBaseUrl}/funnels/${funnelId}/pages/${pageId}/ai/generate/stream`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            prompt,
            messages: aiMessages,
            attachedAssets: aiReadyAttachments.map((item) => ({
              assetId: item.assetId,
              publicId: item.publicId,
              filename: item.name,
              contentType: item.contentType,
              width: item.width ?? null,
              height: item.height ?? null,
            })),
            currentPuckData: appState.data,
            templateId,
            ideaWorkspaceId,
            generateImages: aiGenerateImages,
            maxImages,
          }),
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          if (resp.status === 404) {
            await fallbackNonStream(headers);
            return;
          }
          const raw = await resp.text();
          throw new Error(raw || resp.statusText || "Failed to generate AI draft");
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let didComplete = false;

        const handleEvent = (event: unknown) => {
          if (!event || typeof event !== "object") return;
          const e = event as Record<string, unknown>;
          const type = typeof e.type === "string" ? e.type : "";
          if (type === "text" && typeof e.text === "string") {
            setAiStreamText((prev) => (prev ?? "") + e.text);
            assistantStreamBufferRef.current += e.text;
            return;
          }
          if (type === "raw" && typeof e.text === "string") {
            setAiRawStreamText((prev) => (prev ?? "") + e.text);
            rawStreamBufferRef.current += e.text;
            return;
          }
          if (type === "error") {
            const message = typeof e.message === "string" ? e.message : "Failed to generate AI draft";
            throw new Error(message);
          }
          if (type === "done") {
            didComplete = true;
            applyDraft(e);
          }
        };

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          buffer = buffer.replaceAll("\r\n", "\n");

          let sepIdx = buffer.indexOf("\n\n");
          while (sepIdx !== -1) {
            const rawEvent = buffer.slice(0, sepIdx);
            buffer = buffer.slice(sepIdx + 2);
            for (const line of rawEvent.split("\n")) {
              if (!line.startsWith("data:")) continue;
              const payload = line.slice(5).trim();
              if (!payload) continue;
              let parsed: unknown;
              try {
                parsed = JSON.parse(payload);
              } catch {
                continue;
              }
              handleEvent(parsed);
            }
            sepIdx = buffer.indexOf("\n\n");
          }
        }

        if (!didComplete) {
          const recovered = parseJsonObject(rawStreamBufferRef.current);
          if (recovered && typeof recovered === "object") {
            if (
              !("assistantMessage" in recovered) &&
              !("assistant_message" in recovered) &&
              assistantStreamBufferRef.current.trim()
            ) {
              recovered.assistantMessage = assistantStreamBufferRef.current.trim();
            }
            applyDraft(recovered);
            return;
          }
          throw new Error("AI stream ended unexpectedly (no final result).");
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : "Failed to generate AI draft";
        setAiIsGenerating(false);
        setAiStreamText(null);
        setAiRawStreamText(null);
        setAiPrompt(prompt);
        setAiMessages((prev) => [...prev, { role: "assistant", content: `Error generating draft: ${message}` }]);
        toast.error(message);
      } finally {
        if (aiAbortRef.current === controller) aiAbortRef.current = null;
      }
    };

    void run();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-2 border-b border-border p-3">
        <div>
          <div className="text-xs font-semibold text-content">AI assistant</div>
          <div className="text-xs text-content-muted">
            Generate a draft page (optionally with AI images) and load it into Puck.
          </div>
        </div>
        <Button
          variant="secondary"
          size="sm"
          type="button"
          onClick={handleClear}
          disabled={aiIsGenerating || !aiMessages.length}
        >
          Clear
        </Button>
      </div>

      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="space-y-2 p-3">
            {aiMessages.length ? (
              aiMessages.map((m, idx) => <MessageBubble key={`${m.role}-${idx}`} role={m.role} content={m.content} />)
            ) : (
              <div className="text-xs text-content-muted">Responses will appear here.</div>
            )}
            {aiRawStreamText !== null ? (
              <MessageBubble role="assistant" content={aiRawStreamText || "Streaming raw output..."} />
            ) : null}
            {aiStreamText !== null ? <MessageBubble role="assistant" content={aiStreamText || "Generating..."} /> : null}
            <div ref={aiBottomRef} />
          </div>
        </ScrollArea>
      </div>

      <div className="border-t border-border p-3 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-content-muted">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={aiGenerateImages}
              onChange={(e) => setAiGenerateImages(e.target.checked)}
              className="size-4 rounded border-border text-primary focus:ring-2 focus:ring-primary"
            />
            Generate images
          </label>
          <div className="flex items-center gap-2">
            <span>Max images</span>
            <Input
              type="number"
              value={aiMaxImages}
              onChange={(e) => setAiMaxImages(e.target.value)}
              min={0}
              max={10}
              className="h-8 w-20 px-2 py-1 text-xs"
              disabled={!aiGenerateImages}
            />
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Prompt</label>
            <div className="text-xs text-content-muted">
              Describe what you want on this page (copy, layout, CTAs). The assistant will generate a new draft.
            </div>
            <textarea
              rows={6}
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="e.g. Write a high-converting landing page for a free guide, with a hero, benefits, and a CTA button to the checkout page."
              className={cn(
                "min-h-[140px] w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted"
              )}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold text-content">
                Attached images ({aiAttachments.length}/{AI_ATTACHMENT_MAX})
              </div>
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={() => aiFileInputRef.current?.click()}
                disabled={!funnelId || !pageId || aiAttachments.length >= AI_ATTACHMENT_MAX}
              >
                Attach images
              </Button>
              <input
                ref={aiFileInputRef}
                type="file"
                multiple
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="hidden"
                onChange={handleAttachmentSelect}
              />
            </div>
            <div className="text-xs text-content-muted">
              Attach reference images (PNG, JPEG, WebP, GIF). The assistant can place them directly or use them as
              references for new generated scenes.
            </div>
            {aiAttachments.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {aiAttachments.map((item) => (
                  <div key={item.id} className="rounded-md border border-border bg-surface p-2 space-y-2">
                    <div className="relative overflow-hidden rounded-md border border-border bg-surface-2">
                      <img src={item.previewUrl} alt={item.name} className="h-28 w-full object-cover" />
                      {item.status === "uploading" ? (
                        <div className="absolute inset-0 flex items-center justify-center bg-surface/80 text-xs text-content">
                          Uploading...
                        </div>
                      ) : null}
                      {item.status === "error" ? (
                        <div className="absolute inset-0 flex items-center justify-center bg-danger/10 text-xs text-danger">
                          Upload failed
                        </div>
                      ) : null}
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <div className="truncate text-xs text-content-muted">{item.name}</div>
                      <button
                        type="button"
                        className="text-xs font-semibold text-content hover:text-content/80"
                        onClick={() => handleRemoveAttachment(item.id)}
                      >
                        Remove
                      </button>
                    </div>
                    {item.error ? <div className="text-xs text-danger">{item.error}</div> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <Button
            size="sm"
            type="button"
            onClick={handleAiGenerate}
            disabled={!aiPrompt.trim() || aiIsGenerating || aiAttachmentsUploading || !funnelId || !pageId}
          >
            {aiIsGenerating ? "Generating..." : "Generate draft"}
          </Button>
        </div>

        {aiGeneratedImages.length ? (
          <div className="pt-2">
            <div className="text-xs font-semibold text-content">Generated images</div>
            <div className="mt-2 grid gap-3">
              {aiGeneratedImages.map((raw, idx) => {
                const item = raw as Record<string, unknown>;
                const prompt = typeof item.prompt === "string" ? item.prompt : undefined;
                const publicId = typeof item.publicId === "string" ? item.publicId : undefined;
                const error = typeof item.error === "string" ? item.error : undefined;
                return (
                  <div key={`${publicId || "img"}-${idx}`} className="rounded-md border border-border bg-surface p-2 space-y-2">
                    {publicId ? (
                      <img
                        src={`${apiBaseUrl}/public/assets/${publicId}`}
                        alt={prompt || "Generated"}
                        className="w-full rounded-md border border-border"
                      />
                    ) : (
                      <div className="rounded-md border border-dashed border-border bg-surface-2 p-4 text-xs text-content-muted">
                        {error ? "Failed to generate image" : "No image"}
                      </div>
                    )}
                    {prompt ? <div className="text-xs text-content-muted line-clamp-3">{prompt}</div> : null}
                    {error ? <div className="text-xs text-danger">{error}</div> : null}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function createFunnelAiPlugin(options: FunnelAiPluginOptions): Plugin {
  return {
    overrides: {
      fields: ({ children }) => <FunnelAiFields {...options}>{children}</FunnelAiFields>,
    },
  };
}
