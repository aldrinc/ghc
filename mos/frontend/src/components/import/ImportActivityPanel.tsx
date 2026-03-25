import { useEffect, useMemo, useRef, useState } from "react";
import {
  Lightbulb,
  MessageSquare,
  FilePlus,
  FileEdit,
  Image,
  Scissors,
  Files,
  ChevronDown,
  ChevronRight,
  Terminal,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import type {
  ActivityEvent,
  UpstreamTranscriptEntry,
  UpstreamVariantData,
} from "@/types/importActivity";

// =============================================================================
// Utility Functions
// =============================================================================

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatDurationMs(milliseconds: number): string {
  const seconds = Math.max(1, Math.round(milliseconds / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function formatDuration(startedAt?: number, endedAt?: number): string {
  if (!isFiniteNumber(startedAt) || !isFiniteNumber(endedAt)) return "";
  return formatDurationMs(endedAt - startedAt);
}

function formatElapsedSince(timestampMs: number | undefined, nowMs: number): string {
  if (!isFiniteNumber(timestampMs)) return "";
  return formatDurationMs(Math.max(0, nowMs - timestampMs));
}

// =============================================================================
// Icon Components
// =============================================================================

function getEventIcon(type: ActivityEvent["type"], toolName?: string) {
  if (type === "thinking") {
    return <Lightbulb className="h-4 w-4 text-yellow-500" />;
  }
  if (type === "assistant") {
    return <MessageSquare className="h-4 w-4 text-blue-500" />;
  }
  if (type === "status") {
    return <Terminal className="h-4 w-4 text-gray-500" />;
  }
  if (type === "variant") {
    return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  }
  if (type === "error") {
    return <XCircle className="h-4 w-4 text-red-500" />;
  }
  if (toolName === "create_file") {
    return <FilePlus className="h-4 w-4 text-indigo-500" />;
  }
  if (toolName === "edit_file") {
    return <FileEdit className="h-4 w-4 text-purple-500" />;
  }
  if (toolName === "generate_images") {
    return <Image className="h-4 w-4 text-pink-500" />;
  }
  if (toolName === "remove_background") {
    return <Scissors className="h-4 w-4 text-teal-500" />;
  }
  if (toolName === "retrieve_option") {
    return <Files className="h-4 w-4 text-slate-500" />;
  }
  return <FilePlus className="h-4 w-4 text-gray-500" />;
}

// =============================================================================
// Event Title Generator
// =============================================================================

function getEventTitle(event: ActivityEvent): string {
  if (event.title) {
    if (event.type === "thinking") {
      const duration = formatDuration(event.startedAt, event.endedAt);
      return duration ? `${event.title} (${duration})` : event.title;
    }
    return event.title;
  }

  if (event.type === "thinking") {
    if (event.status === "running") return "Thinking";
    const duration = formatDuration(event.startedAt, event.endedAt);
    return duration ? `Thought for ${duration}` : "Thought";
  }

  if (event.type === "assistant") {
    return "Assistant response";
  }

  if (event.type === "status") {
    return event.content || "Status update";
  }

  if (event.type === "variant") {
    return event.status === "complete" ? "Variant complete" : "Variant update";
  }

  if (event.type === "error") {
    return "Error";
  }

  if (event.type === "tool") {
    if (event.toolName === "create_file") {
      return event.status === "running" ? "Creating file" : "Created file";
    }
    if (event.toolName === "edit_file") {
      return event.status === "running" ? "Editing file" : "Edited file";
    }
    if (event.toolName === "generate_images") {
      const input = event.input as { count?: number } | undefined;
      const output = event.output as { images?: unknown[] } | undefined;
      const count = output?.images?.length || input?.count || 0;
      if (event.status === "running") {
        return count ? `Generating ${count} image${count !== 1 ? "s" : ""}` : "Generating images";
      }
      return count ? `Generated ${count} image${count !== 1 ? "s" : ""}` : "Generated images";
    }
    if (event.toolName === "remove_background") {
      const rbInput = event.input as { image_urls?: string[] } | undefined;
      const rbOutput = event.output as { images?: unknown[] } | undefined;
      const rbCount = rbOutput?.images?.length || rbInput?.image_urls?.length || 0;
      if (event.status === "running") {
        return rbCount > 1 ? `Removing ${rbCount} backgrounds` : "Removing background";
      }
      return rbCount > 1 ? `Removed ${rbCount} backgrounds` : "Background removed";
    }
    if (event.toolName === "retrieve_option") {
      return event.status === "running" ? "Retrieving option" : "Retrieved option";
    }
    return event.status === "running" ? "Running tool" : "Tool completed";
  }

  return "Activity";
}

// =============================================================================
// Tool Details Renderer
// =============================================================================

function renderToolDetails(event: ActivityEvent) {
  if (!event.input && !event.output) return null;

  const renderJson = (data: unknown) => {
    if (!data) return null;
    let json = "";
    try {
      json = JSON.stringify(data, null, 2);
    } catch {
      json = String(data);
    }
    if (json.length > 900) {
      json = json.slice(0, 900) + "...";
    }
    return (
      <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-surface-2 p-2 text-xs text-content-muted">
        {json}
      </pre>
    );
  };

  const output = event.output as { error?: string; images?: unknown[]; edits?: unknown[] } | undefined;
  const input = event.input as { prompts?: string[]; image_urls?: string[] } | undefined;
  const hasError = Boolean(output?.error);
  const images = output?.images;
  const edits = output?.edits as Array<{ old_text?: string; new_text?: string; replaced?: number }> | undefined;

  return (
    <div className="text-sm text-content">
      {hasError && (
        <div className="rounded-md border border-danger/30 bg-danger/5 p-3">
          <div className="text-xs uppercase tracking-wide text-danger">Error</div>
          <div className="mt-1 text-sm text-danger">{output?.error}</div>
          {event.input && (
            <div className="mt-2">
              <div className="text-xs uppercase tracking-wide text-danger/70">Input</div>
              {renderJson(event.input)}
            </div>
          )}
        </div>
      )}

      {event.toolName === "edit_file" && edits && !hasError && (
        <div className="space-y-2">
          {edits.map((edit, index) => (
            <div
              key={`${edit.old_text}-${index}`}
              className="rounded-md border border-border bg-surface p-3"
            >
              <div className="text-xs uppercase tracking-wide text-content-muted">
                Edit {index + 1}
              </div>
              <div className="mt-2 grid gap-2">
                <div>
                  <div className="text-xs text-content-muted">Old</div>
                  <div className="mt-1 rounded bg-danger/10 p-2 text-xs font-mono text-danger break-all">
                    {edit.old_text}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-content-muted">New</div>
                  <div className="mt-1 rounded bg-success/10 p-2 text-xs font-mono text-success break-all">
                    {edit.new_text}
                  </div>
                </div>
              </div>
              {edit.replaced !== undefined && (
                <div className="mt-2 text-xs text-content-muted">
                  Replaced {edit.replaced} time{edit.replaced === 1 ? "" : "s"}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {event.toolName === "generate_images" && !hasError && (
        <div>
          {/* While running: show prompts */}
          {event.status === "running" && input?.prompts && Array.isArray(input.prompts) && (
            <div className="divide-y divide-border">
              {input.prompts.map((prompt: string, index: number) => (
                <div key={index} className="py-1.5 text-xs text-content-muted">
                  {prompt}
                </div>
              ))}
            </div>
          )}
          {/* After complete: show results */}
          {event.status !== "running" && images && Array.isArray(images) && (
            <div className="divide-y divide-border">
              {images.map((item: unknown, index: number) => {
                const imgItem = item as { url?: string; prompt?: string; result_url?: string; image_url?: string };
                return (
                  <div key={`${imgItem.prompt || index}-${index}`} className="flex gap-3 py-2">
                    <div className="w-1/2 shrink-0">
                      {imgItem.url || imgItem.result_url ? (
                        <img
                          src={imgItem.url || imgItem.result_url}
                          alt={imgItem.prompt || `Generated image ${index + 1}`}
                          className="w-full rounded object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="flex aspect-square items-center justify-center rounded bg-surface-2 text-xs text-content-muted">
                          Failed
                        </div>
                      )}
                    </div>
                    <div className="w-1/2 self-center text-xs text-content-muted">
                      {imgItem.prompt}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {event.toolName === "remove_background" && !hasError && (
        <div>
          {/* While running: show source images */}
          {event.status === "running" && input?.image_urls && Array.isArray(input.image_urls) && (
            <div className="divide-y divide-border">
              {input.image_urls.map((url: string, index: number) => (
                <div key={index} className="py-2">
                  <img
                    src={url}
                    alt={`Original image ${index + 1}`}
                    className="w-full rounded object-cover"
                    loading="lazy"
                  />
                </div>
              ))}
            </div>
          )}
          {/* After complete: before/after side by side */}
          {event.status !== "running" && output?.images && Array.isArray(output.images) && (
            <div className="divide-y divide-border">
              {(output.images as Array<{ image_url?: string; result_url?: string }>).map((item, index) => (
                <div key={`${item.image_url}-${index}`} className="flex gap-2 py-2">
                  <div className="w-1/2">
                    <div className="mb-1 text-xs text-content-muted">Before</div>
                    <img
                      src={item.image_url}
                      alt={`Original image ${index + 1}`}
                      className="w-full rounded object-cover"
                      loading="lazy"
                    />
                  </div>
                  <div className="w-1/2">
                    <div className="mb-1 text-xs text-content-muted">After</div>
                    {item.result_url ? (
                      <div className="relative">
                        <div
                          className="absolute inset-0 rounded"
                          style={{
                            backgroundImage:
                              "linear-gradient(45deg, #e5e7eb 25%, transparent 25%), linear-gradient(-45deg, #e5e7eb 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #e5e7eb 75%), linear-gradient(-45deg, transparent 75%, #e5e7eb 75%)",
                            backgroundSize: "10px 10px",
                            backgroundPosition: "0 0, 0 5px, 5px -5px, -5px 0px",
                          }}
                        />
                        <img
                          src={item.result_url}
                          alt="Background removed"
                          className="relative w-full rounded"
                          loading="lazy"
                        />
                      </div>
                    ) : (
                      <div className="flex aspect-square items-center justify-center rounded bg-surface-2 text-xs text-content-muted">
                        Failed
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!event.toolName && !hasError && (
        <>
          {event.input && (
            <div>
              <div className="text-xs uppercase tracking-wide text-content-muted">Input</div>
              {renderJson(event.input)}
            </div>
          )}
          {event.output && (
            <div className="mt-3">
              <div className="text-xs uppercase tracking-wide text-content-muted">Output</div>
              {renderJson(event.output)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function CodePreviewBlock({ code, isGenerating }: { code: string; isGenerating: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isGenerating && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [code, isGenerating]);

  return (
    <div ref={containerRef} className="max-h-60 overflow-auto rounded-md border border-border bg-surface-2 p-2">
      <pre className="whitespace-pre-wrap break-all text-xs text-content">{code}</pre>
    </div>
  );
}

// =============================================================================
// Event Card Component
// =============================================================================

function ActivityEventCard({
  event,
  autoExpand,
  variantCode,
}: {
  event: ActivityEvent;
  autoExpand?: boolean;
  variantCode?: string;
}) {
  const [expanded, setExpanded] = useState(Boolean(autoExpand));

  useEffect(() => {
    if (autoExpand) {
      setExpanded(true);
    }
  }, [autoExpand]);

  const isExpanded = (event.type !== "thinking" && event.status === "running") || expanded;

  if (event.type === "assistant") {
    if (!event.content) return null;
    return (
      <div className="py-1">
        {event.title && (
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-content-muted">
            {event.title}
          </div>
        )}
        <div className="prose prose-sm max-w-none text-sm text-content">
          <ReactMarkdown>{event.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-2 py-1.5 text-left text-content-muted hover:text-content"
      >
        {getEventIcon(event.type, event.toolName)}
        <span
          className={cn(
            "flex-1 text-sm",
            event.status === "running" && "animate-pulse font-medium text-accent"
          )}
        >
          {getEventTitle(event)}
        </span>
        {isExpanded ? (
          <ChevronDown className="shrink-0 text-xs" />
        ) : (
          <ChevronRight className="shrink-0 text-xs" />
        )}
      </button>
      {isExpanded && (
        <div className="pb-2">
          {event.type === "thinking" && event.content && (
            <div className="prose prose-sm max-w-none text-sm text-content">
              <ReactMarkdown>{event.content}</ReactMarkdown>
            </div>
          )}
          {event.type === "tool" && (
            <div className="space-y-3">
              {event.toolName === "create_file" && variantCode ? (
                <CodePreviewBlock code={variantCode} isGenerating={event.status === "running"} />
              ) : null}
              {renderToolDetails(event)}
            </div>
          )}
          {event.type === "error" && event.content && (
            <div className="rounded-md border border-danger/30 bg-danger/5 p-2 text-sm text-danger">
              {event.content}
            </div>
          )}
          {event.type === "status" && event.content && (
            <div className="text-sm text-content-muted">{event.content}</div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Variant Summary Component
// =============================================================================

function VariantSummaryCard({
  variant,
  isSelected,
  onClick,
}: {
  variant: UpstreamVariantData;
  isSelected: boolean;
  onClick: () => void;
}) {
  const statusColor =
    variant.status === "complete"
      ? "bg-success"
      : variant.status === "error"
        ? "bg-danger"
        : variant.status === "paused"
          ? "bg-warning"
          : "bg-content-muted";

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full rounded-xl border px-3 py-2 text-left transition-colors",
        isSelected
          ? "border-accent bg-accent/5"
          : "border-border bg-surface-2 hover:border-accent/40"
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("h-2 w-2 rounded-full", statusColor)} />
        <span className="text-sm font-medium text-content">Option {variant.variantIndex + 1}</span>
        {variant.model && (
          <span className="ml-auto text-xs text-content-muted">{variant.model}</span>
        )}
      </div>
      {variant.status === "generating" && (
        <div className="mt-1 flex items-center gap-1">
          <Loader2 className="h-3 w-3 animate-spin text-accent" />
          <span className="text-xs text-accent">Generating...</span>
        </div>
      )}
    </button>
  );
}

// =============================================================================
// Working Pulse Component
// =============================================================================

function WorkingPulse() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75"></span>
      <span className="relative inline-flex h-2 w-2 rounded-full bg-accent"></span>
    </span>
  );
}

// =============================================================================
// Main Import Activity Panel Component
// =============================================================================

interface ImportActivityPanelProps {
  transcript: UpstreamTranscriptEntry[];
  variants: UpstreamVariantData[];
  isActive?: boolean;
}

export function ImportActivityPanel({ transcript, variants, isActive = false }: ImportActivityPanelProps) {
  const [selectedVariantIndex, setSelectedVariantIndex] = useState<number>(0);
  const [stepsExpandedByVariant, setStepsExpandedByVariant] = useState<Record<string, boolean>>({});
  const [nowMs, setNowMs] = useState(() => Date.now());

  // Update elapsed time while active
  useEffect(() => {
    if (!isActive) return;
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, [isActive]);

  // Parse transcript into activity events
  const activityEvents = useMemo(() => {
    const events: ActivityEvent[] = [];
    const toolEventMap = new Map<string, ActivityEvent>();
    const thinkingEventMap = new Map<number, ActivityEvent>();
    const assistantEventMap = new Map<number, ActivityEvent>();

    const finishRunningNarration = (
      variantIndex: number,
      endedAt: number | undefined,
      status: ActivityEvent["status"] = "complete",
      exceptEventId?: string
    ) => {
      const thinkingEvent = thinkingEventMap.get(variantIndex);
      if (thinkingEvent && thinkingEvent.id !== exceptEventId) {
        thinkingEvent.status = status;
        thinkingEvent.endedAt = endedAt ?? thinkingEvent.endedAt;
        thinkingEventMap.delete(variantIndex);
      }

      const assistantEvent = assistantEventMap.get(variantIndex);
      if (assistantEvent && assistantEvent.id !== exceptEventId) {
        assistantEvent.status = status;
        assistantEvent.endedAt = endedAt ?? assistantEvent.endedAt;
        assistantEventMap.delete(variantIndex);
      }
    };

    const finishRunningTools = (
      variantIndex: number,
      endedAt: number | undefined,
      status: ActivityEvent["status"]
    ) => {
      for (const event of toolEventMap.values()) {
        if (event.variantIndex === variantIndex && event.status === "running") {
          event.status = status;
          event.endedAt = endedAt ?? event.endedAt;
        }
      }
    };

    for (const entry of transcript) {
      const timestamp = entry.timestamp;
      const streamEventId = entry.eventId || `${entry.type}-${entry.variantIndex}-${timestamp || Date.now()}`;
      const baseEvent: ActivityEvent = {
        id: streamEventId,
        type: "status",
        variantIndex: entry.variantIndex,
        status: "complete",
        eventId: entry.eventId,
        startedAt: timestamp,
        endedAt: timestamp,
      };

      switch (entry.type) {
        case "thinking":
          {
            const existing = thinkingEventMap.get(entry.variantIndex);
            if (existing && existing.id === streamEventId) {
              existing.content = `${existing.content || ""}${entry.value || ""}`;
              existing.endedAt = timestamp;
            } else {
              finishRunningNarration(entry.variantIndex, timestamp, "complete", streamEventId);
              const event: ActivityEvent = {
                ...baseEvent,
                type: "thinking",
                content: entry.value,
                title: (entry.data as { title?: string } | undefined)?.title,
                status: "running",
              };
              events.push(event);
              thinkingEventMap.set(entry.variantIndex, event);
            }
          }
          break;

        case "assistant":
          {
            const existing = assistantEventMap.get(entry.variantIndex);
            if (existing && existing.id === streamEventId) {
              existing.content = `${existing.content || ""}${entry.value || ""}`;
              existing.endedAt = timestamp;
            } else {
              const thinkingEvent = thinkingEventMap.get(entry.variantIndex);
              if (thinkingEvent && thinkingEvent.id !== streamEventId) {
                finishRunningNarration(entry.variantIndex, timestamp, "complete", streamEventId);
              }
              const event: ActivityEvent = {
                ...baseEvent,
                type: "assistant",
                content: entry.value,
                title: (entry.data as { title?: string } | undefined)?.title,
                status: "running",
              };
              events.push(event);
              assistantEventMap.set(entry.variantIndex, event);
            }
          }
          break;

        case "toolStart":
          {
            const toolData = entry.data as { name?: string; input?: unknown; title?: string; source?: string } | undefined;
            finishRunningNarration(entry.variantIndex, timestamp, "complete", streamEventId);
            const event: ActivityEvent = {
              ...baseEvent,
              type: "tool",
              toolName: toolData?.name,
              input: toolData?.input,
              title: toolData?.title,
              status: "running",
            };
            events.push(event);
            if (entry.eventId) {
              toolEventMap.set(entry.eventId, event);
            }
          }
          break;

        case "toolResult":
          {
            const toolData = entry.data as { name?: string; output?: unknown; ok?: boolean; title?: string } | undefined;
            if (entry.eventId && toolEventMap.has(entry.eventId)) {
              const existingEvent = toolEventMap.get(entry.eventId)!;
              existingEvent.status = toolData?.ok ? "complete" : "error";
              existingEvent.output = toolData?.output;
              existingEvent.endedAt = timestamp;
            } else {
              events.push({
                ...baseEvent,
                type: "tool",
                toolName: toolData?.name,
                output: toolData?.output,
                status: toolData?.ok ? "complete" : "error",
              });
            }
          }
          break;

        case "status":
          events.push({
            ...baseEvent,
            type: "status",
            content: entry.value,
          });
          break;

        case "variantComplete":
          finishRunningNarration(entry.variantIndex, timestamp, "complete");
          finishRunningTools(entry.variantIndex, timestamp, "complete");
          events.push({
            ...baseEvent,
            type: "variant",
            status: "complete",
            meta: entry.data as Record<string, unknown> | undefined,
          });
          break;

        case "variantError":
          finishRunningNarration(entry.variantIndex, timestamp, "error");
          finishRunningTools(entry.variantIndex, timestamp, "error");
          events.push({
            ...baseEvent,
            type: "error",
            content: entry.value,
            status: "error",
            meta: entry.data as Record<string, unknown> | undefined,
          });
          break;

        case "setCode":
          // Code updates are handled separately via variant data
          break;

        case "chunk":
          // Chunks are incremental updates, not displayed as events
          break;
      }
    }

    for (const event of [...thinkingEventMap.values(), ...assistantEventMap.values()]) {
      if (event.status === "running") {
        event.endedAt = event.endedAt ?? event.startedAt;
      }
    }

    return events.sort((a, b) => (a.startedAt || 0) - (b.startedAt || 0));
  }, [transcript]);

  // Get events for selected variant
  const selectedVariant = variants.find((v) => v.variantIndex === selectedVariantIndex);
  const variantEvents = activityEvents.filter((e) => e.variantIndex === selectedVariantIndex);
  const stepEvents = variantEvents.filter((e) => e.type === "tool" || e.type === "thinking");
  const assistantEvents = variantEvents.filter((e) => e.type === "assistant");
  const lastAssistantEvent = assistantEvents[assistantEvents.length - 1];

  // Determine if this variant is done
  const isDone =
    selectedVariant?.status === "complete" ||
    selectedVariant?.status === "error" ||
    selectedVariant?.status === "paused";

  const requestStartMs = selectedVariant?.requestStartedAt;
  const completedAt = selectedVariant?.completedAt;

  const runningDuration = formatElapsedSince(requestStartMs, nowMs);
  const variantDuration =
    isFiniteNumber(requestStartMs) && isFiniteNumber(completedAt)
      ? formatDurationMs(Math.max(0, completedAt - requestStartMs))
      : isFiniteNumber(requestStartMs)
        ? formatDurationMs(Math.max(0, nowMs - requestStartMs))
        : "";

  const variantUiKey = String(selectedVariantIndex);
  const stepsExpanded = Boolean(stepsExpandedByVariant[variantUiKey]);

  // If no events to show
  if (activityEvents.length === 0 && variants.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface-2 px-4 py-6 text-center text-sm text-content-muted">
        No activity recorded yet.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Variant Selector */}
      {variants.length > 1 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-content">Generated variants</div>
          <div className="grid grid-cols-2 gap-2">
            {variants.map((variant) => (
              <VariantSummaryCard
                key={variant.variantIndex}
                variant={variant}
                isSelected={variant.variantIndex === selectedVariantIndex}
                onClick={() => setSelectedVariantIndex(variant.variantIndex)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Activity Stream */}
      <div className="space-y-1">
        {isDone ? (
          <>
            {/* Collapsed steps summary */}
            <button
              onClick={() =>
                setStepsExpandedByVariant((prev) => ({
                  ...prev,
                  [variantUiKey]: !prev[variantUiKey],
                }))
              }
              className="flex w-full items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-left"
            >
              {stepsExpanded ? (
                <ChevronDown className="text-xs text-content-muted" />
              ) : (
                <ChevronRight className="text-xs text-content-muted" />
              )}
              <span className="text-xs text-content-muted">
                Worked through {stepEvents.length} step{stepEvents.length !== 1 ? "s" : ""}
                {variantDuration ? ` in ${variantDuration}` : ""}
              </span>
            </button>
            {stepsExpanded && (
              <div className="space-y-1">
                {stepEvents.map((event) => (
                  <ActivityEventCard key={event.id} event={event} variantCode={selectedVariant?.code} />
                ))}
              </div>
            )}
            {/* Assistant responses always visible */}
            {assistantEvents.map((event) => (
              <ActivityEventCard
                key={event.id}
                event={event}
                autoExpand={event.id === lastAssistantEvent?.id}
                variantCode={selectedVariant?.code}
              />
            ))}
          </>
        ) : (
          <>
            {/* Active working indicator */}
            {isActive && (
              <div className="flex items-center justify-between rounded-xl border border-accent/30 bg-accent/5 px-3 py-2">
                <div className="flex items-center gap-2 text-sm text-content">
                  <WorkingPulse />
                  <span>Working...</span>
                </div>
                <div className="text-xs font-medium text-content">
                  Time so far {runningDuration || "--"}
                </div>
              </div>
            )}
            {/* All events for active variant */}
            {variantEvents.map((event) => (
              <ActivityEventCard
                key={event.id}
                event={event}
                autoExpand={event.type === "assistant" && event.id === lastAssistantEvent?.id}
                variantCode={selectedVariant?.code}
              />
            ))}
          </>
        )}
      </div>

      {/* Error Display */}
      {selectedVariant?.status === "error" && (
        <div className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-danger">
            <AlertTriangle className="h-4 w-4" />
            <span>Generation failed</span>
          </div>
          <div className="mt-2 text-sm text-danger">
            Check the transcript events above for details.
          </div>
        </div>
      )}
    </div>
  );
}

export default ImportActivityPanel;
