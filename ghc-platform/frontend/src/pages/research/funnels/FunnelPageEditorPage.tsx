import { Puck } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useApproveFunnelPage, useFunnel, useFunnelPage, useSaveFunnelDraft, useUpdateFunnelPage } from "@/api/funnels";
import { toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select } from "@/components/ui/select";
import { createFunnelPuckConfig, defaultFunnelPuckData } from "@/funnels/puckConfig";
import { cn } from "@/lib/utils";
import type { FunnelAIChatMessage } from "@/types/funnels";
import { useAuth } from "@clerk/clerk-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

function deepClone<T>(value: T): T {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

function makeBlockId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2);
}

function normalizePuckData(input: unknown): Data {
  const fallback = defaultFunnelPuckData() as unknown as Data;
  if (!input || typeof input !== "object") return fallback;

  const cloned = deepClone(input) as Record<string, unknown>;

  if (!cloned.root || typeof cloned.root !== "object") cloned.root = { props: {} };
  const root = cloned.root as Record<string, unknown>;
  if (!root.props || typeof root.props !== "object") root.props = {};
  const rootProps = root.props as Record<string, unknown>;
  if (typeof rootProps.title !== "string") rootProps.title = "";
  if (typeof rootProps.description !== "string") rootProps.description = "";

  if (!Array.isArray(cloned.content)) cloned.content = [];
  if (!cloned.zones || typeof cloned.zones !== "object") cloned.zones = {};

  const seen = new Set<string>();
  const walk = (value: unknown) => {
    if (Array.isArray(value)) {
      for (const v of value) walk(v);
      return;
    }
    if (!value || typeof value !== "object") return;

    const obj = value as Record<string, unknown>;
    const type = obj.type;
    const propsRaw = obj.props;
    if (typeof type === "string" && propsRaw && typeof propsRaw === "object") {
      const props = propsRaw as Record<string, unknown>;
      let id = typeof props.id === "string" ? props.id : "";
      if (!id || seen.has(id)) {
        id = makeBlockId();
        props.id = id;
      }
      seen.add(id);
    }

    for (const key of Object.keys(obj)) walk(obj[key]);
  };

  walk(cloned.content);
  walk(cloned.zones);

  return cloned as unknown as Data;
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

export function FunnelPageEditorPage() {
  const navigate = useNavigate();
  const { funnelId, pageId } = useParams();
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const { data: funnel } = useFunnel(funnelId);
  const { data: pageDetail, isLoading } = useFunnelPage(funnelId, pageId);
  const saveDraft = useSaveFunnelDraft();
  const approvePage = useApproveFunnelPage();
  const updatePage = useUpdateFunnelPage();

  const [data, setData] = useState<Data>(() => defaultFunnelPuckData() as unknown as Data);
  const [puckKey, setPuckKey] = useState(() => pageId || "puck");
  const [metaName, setMetaName] = useState("");
  const [metaSlug, setMetaSlug] = useState("");
  const [aiMessages, setAiMessages] = useState<FunnelAIChatMessage[]>([]);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiGenerateImages, setAiGenerateImages] = useState(true);
  const [aiMaxImages, setAiMaxImages] = useState("3");
  const [aiIsGenerating, setAiIsGenerating] = useState(false);
  const [aiStreamText, setAiStreamText] = useState<string | null>(null);
  const [aiRawStreamText, setAiRawStreamText] = useState<string | null>(null);
  const [aiGeneratedImages, setAiGeneratedImages] = useState<Array<Record<string, unknown>>>([]);
  const aiBottomRef = useRef<HTMLDivElement | null>(null);
  const initializedPageIdRef = useRef<string | null>(null);
  const aiAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!pageId) return;
    if (initializedPageIdRef.current === pageId) return;
    if (aiAbortRef.current) aiAbortRef.current.abort();
    aiAbortRef.current = null;
    setData(defaultFunnelPuckData() as unknown as Data);
    setPuckKey(pageId);
    setAiMessages([]);
    setAiPrompt("");
    setAiStreamText(null);
    setAiRawStreamText(null);
    setAiIsGenerating(false);
    setAiGeneratedImages([]);
  }, [pageId]);

  useEffect(() => {
    if (!pageDetail) return;
    if (!pageId) return;
    if (initializedPageIdRef.current === pageId) return;
    initializedPageIdRef.current = pageId;
    const initial =
      (pageDetail.latestDraft?.puck_data as Data | undefined) ||
      (pageDetail.latestApproved?.puck_data as Data | undefined) ||
      (defaultFunnelPuckData() as unknown as Data);
    setData(normalizePuckData(initial));
    setPuckKey(`${pageId}:${pageDetail.latestDraft?.id || pageDetail.latestApproved?.id || "initial"}`);
    setMetaName(pageDetail.page.name);
    setMetaSlug(pageDetail.page.slug);
    setAiMessages([]);
    setAiPrompt("");
  }, [pageDetail, pageId]);

  const pageOptions = useMemo(() => {
    return funnel?.pages?.map((p) => ({ label: p.name, value: p.id })) || [];
  }, [funnel?.pages]);

  const config = useMemo(() => createFunnelPuckConfig(pageOptions), [pageOptions]);

  const currentPageLabel = useMemo(() => {
    const page = funnel?.pages?.find((p) => p.id === pageId);
    return page ? `${page.name} (${page.slug})` : "Page";
  }, [funnel?.pages, pageId]);

  const isApproved = Boolean(pageDetail?.latestApproved?.id);
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
  const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

  useEffect(() => {
    if (!aiBottomRef.current) return;
    aiBottomRef.current.scrollIntoView({ behavior: "smooth" });
  }, [aiMessages, aiIsGenerating, aiStreamText]);

  const handleAiGenerate = () => {
    if (!funnelId || !pageId) return;
    const prompt = aiPrompt.trim();
    if (!prompt) return;
    const parsedMaxImages = Number.parseInt(aiMaxImages, 10);
    const maxImages = Number.isFinite(parsedMaxImages) ? Math.max(0, Math.min(10, parsedMaxImages)) : 3;

    setAiPrompt("");
    setAiMessages((prev) => [...prev, { role: "user", content: prompt }]);
    setAiStreamText("");
    setAiRawStreamText("");
    setAiGeneratedImages([]);
    setAiIsGenerating(true);

    if (aiAbortRef.current) aiAbortRef.current.abort();
    const controller = new AbortController();
    aiAbortRef.current = controller;

    const run = async () => {
      const applyDraft = (draft: Record<string, unknown>) => {
        const assistantMessage = typeof draft.assistantMessage === "string" ? draft.assistantMessage : "";
        const puckData = draft.puckData;
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
        setData(nextData);
        const draftVersionId = typeof draft.draftVersionId === "string" ? draft.draftVersionId : "";
        const nonce =
          typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}:${Math.random()}`;
        setPuckKey(`${pageId}:${draftVersionId || nonce}`);
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
            currentPuckData: data,
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
            currentPuckData: data,
            generateImages: aiGenerateImages,
            maxImages,
          }),
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          if (resp.status === 404) {
            // Stream endpoint not available (backend not restarted); fall back to non-stream.
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
            return;
          }
          if (type === "raw" && typeof e.text === "string") {
            setAiRawStreamText((prev) => (prev ?? "") + e.text);
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
    <div className="space-y-4">
      <PageHeader
        title={currentPageLabel}
        description={funnel ? `Funnel: ${funnel.name}` : "Edit funnel page"}
        actions={
          <>
            <Button variant="secondary" size="sm" asChild>
              <Link to={funnelId ? `/research/funnels/${funnelId}` : "/research/funnels"}>Back</Link>
            </Button>
            {funnel?.pages?.length ? (
              <Select
                value={pageId || ""}
                onValueChange={(nextPageId) => {
                  if (!funnelId || !nextPageId) return;
                  navigate(`/research/funnels/${funnelId}/pages/${nextPageId}`);
                }}
                options={[{ label: "Select page", value: "" }, ...pageOptions.map((o) => ({ label: o.label, value: o.value }))]}
              />
            ) : null}
          </>
        }
      />

      {isLoading || !pageDetail ? (
        <div className="ds-card ds-card--md text-sm text-content-muted">Loading editor…</div>
      ) : (
        <>
          <div className="ds-card ds-card--md space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={isApproved ? "success" : "warning"}>{isApproved ? "Approved" : "Needs approval"}</Badge>
                {pageDetail.latestDraft ? <Badge tone="neutral">Draft saved</Badge> : null}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    if (!funnelId || !pageId) return;
                    saveDraft.mutate({ funnelId, pageId, puckData: data });
                  }}
                  disabled={saveDraft.isPending}
                >
                  {saveDraft.isPending ? "Saving…" : "Save draft"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    if (!funnelId || !pageId) return;
                    approvePage.mutate({ funnelId, pageId });
                  }}
                  disabled={approvePage.isPending}
                >
                  {approvePage.isPending ? "Approving…" : "Approve"}
                </Button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Page name</label>
                <Input value={metaName} onChange={(e) => setMetaName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Slug</label>
                <Input value={metaSlug} onChange={(e) => setMetaSlug(e.target.value)} />
              </div>
            </div>
            <div className="flex justify-end">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  if (!funnelId || !pageId) return;
                  updatePage.mutate({ funnelId, pageId, payload: { name: metaName, slug: metaSlug } });
                }}
                disabled={updatePage.isPending}
              >
                {updatePage.isPending ? "Saving…" : "Save page settings"}
              </Button>
            </div>

            <div className="rounded-md border border-border bg-surface-2 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold text-content">AI assistant</div>
                  <div className="text-xs text-content-muted">Generate a draft page (optionally with AI images) and load it into Puck.</div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setAiMessages([])}
                  disabled={aiIsGenerating || !aiMessages.length}
                >
                  Clear
                </Button>
              </div>

              <ScrollArea className="h-44">
                <div className="space-y-2 p-2">
                  {aiMessages.length ? (
                    aiMessages.map((m, idx) => <MessageBubble key={`${m.role}-${idx}`} role={m.role} content={m.content} />)
                  ) : (
                    <div className="text-sm text-content-muted">
                      Describe what you want on this page (copy, layout, CTAs). The assistant will generate a new draft.
                    </div>
                  )}
                  {aiRawStreamText !== null ? (
                    <MessageBubble role="assistant" content={aiRawStreamText || "Streaming raw output…"} />
                  ) : null}
                  {aiStreamText !== null ? <MessageBubble role="assistant" content={aiStreamText || "Generating…"} /> : null}
                  <div ref={aiBottomRef} />
                </div>
              </ScrollArea>

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

              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="flex-1 space-y-1">
                  <label className="text-xs font-semibold text-content">Prompt</label>
                  <textarea
                    rows={2}
                    value={aiPrompt}
                    onChange={(e) => setAiPrompt(e.target.value)}
                    placeholder="e.g. Write a high-converting landing page for a free guide, with a hero, benefits, and a CTA button to the checkout page."
                    className={cn(
                      "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted"
                    )}
                  />
                </div>
                <Button size="sm" onClick={handleAiGenerate} disabled={!aiPrompt.trim() || aiIsGenerating}>
                  {aiIsGenerating ? "Generating…" : "Generate draft"}
                </Button>
              </div>

              {aiGeneratedImages.length ? (
                <div className="pt-2">
                  <div className="text-xs font-semibold text-content">Generated images</div>
                  <div className="mt-2 grid gap-3 md:grid-cols-3">
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

          <div className="ds-card ds-card--md p-0 overflow-hidden">
            <Puck key={puckKey} config={config} data={data} onChange={setData} />
          </div>
        </>
      )}
    </div>
  );
}
