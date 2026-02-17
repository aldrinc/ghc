import { useMemo, type ReactNode } from "react";
import type { LibraryItem } from "@/types/library";
import { Badge } from "@/components/ui/badge";
import { channelDisplayName } from "@/lib/channels";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function KeyValueRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px,minmax(0,1fr)] gap-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-content-muted">{label}</div>
      <div className="min-w-0 break-words text-sm text-content">{value}</div>
    </div>
  );
}

export function LibraryItemDetailsPanel({ item }: { item: LibraryItem }) {
  const raw = item.raw;

  const rawString = useMemo(() => {
    if (raw === undefined) return { json: null, error: null as string | null };
    try {
      return { json: JSON.stringify(raw, null, 2), error: null as string | null };
    } catch (err: any) {
      return { json: null, error: err?.message || "Failed to serialize raw payload" };
    }
  }, [raw]);

  const rawRecord = isRecord(raw) ? raw : null;

  const platforms = item.platform || [];
  const score = item.scores;

  const landingUrl = rawRecord?.landing_url;
  const destinationDomain = rawRecord?.destination_domain;
  const ctaType = rawRecord?.cta_type;
  const firstSeenAt = rawRecord?.first_seen_at;
  const lastSeenAt = rawRecord?.last_seen_at;
  const researchRunId = rawRecord?.research_run_id;

  const facts = rawRecord?.facts;
  const scores = rawRecord?.scores;

  return (
    <div className="flex flex-col gap-3 overflow-visible rounded-xl border border-border bg-surface-2 p-3 md:max-h-[72vh] md:overflow-auto">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-content">{item.brandName || "Unknown brand"}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            {platforms.map((p) => (
              <Badge key={`${item.id}-${p}`} className="text-[11px]">
                {channelDisplayName(p)}
              </Badge>
            ))}
            {item.status ? (
              <Badge className="text-[11px] uppercase tracking-wide">{item.status}</Badge>
            ) : null}
            {item.kind ? (
              <Badge className="text-[11px] uppercase tracking-wide">{item.kind}</Badge>
            ) : null}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <KeyValueRow label="Ad ID" value={<span className="font-mono text-[12px]">{item.id}</span>} />
        {isRecord(raw) && rawRecord?.brand_id ? (
          <KeyValueRow label="Brand ID" value={<span className="font-mono text-[12px]">{String(rawRecord.brand_id)}</span>} />
        ) : null}
        {isRecord(raw) && rawRecord?.ad_status ? (
          <KeyValueRow
            label="Ad status"
            value={<span className="font-mono text-[12px]">{String(rawRecord.ad_status)}</span>}
          />
        ) : null}
        {isRecord(raw) && rawRecord?.channel ? (
          <KeyValueRow label="Channel" value={<span className="font-mono text-[12px]">{String(rawRecord.channel)}</span>} />
        ) : null}
        {ctaType ? (
          <KeyValueRow label="CTA type" value={<span className="font-mono text-[12px]">{String(ctaType)}</span>} />
        ) : null}
        {item.ctaText ? <KeyValueRow label="CTA text" value={item.ctaText} /> : null}
        {item.destinationUrl ? (
          <KeyValueRow
            label="Link"
            value={
              <a
                href={item.destinationUrl}
                target="_blank"
                rel="noreferrer"
                className="truncate text-sm text-content underline decoration-border hover:decoration-content"
                title={item.destinationUrl}
              >
                {item.destinationUrl}
              </a>
            }
          />
        ) : null}
        {typeof landingUrl === "string" && landingUrl ? (
          <KeyValueRow
            label="Landing"
            value={
              <a
                href={landingUrl}
                target="_blank"
                rel="noreferrer"
                className="truncate text-sm text-content underline decoration-border hover:decoration-content"
                title={landingUrl}
              >
                {landingUrl}
              </a>
            }
          />
        ) : null}
        {typeof destinationDomain === "string" && destinationDomain ? (
          <KeyValueRow label="Domain" value={<span className="font-mono text-[12px]">{destinationDomain}</span>} />
        ) : null}
        {item.startAt ? <KeyValueRow label="Start" value={formatDateTime(item.startAt)} /> : null}
        {item.endAt ? <KeyValueRow label="End" value={formatDateTime(item.endAt)} /> : null}
        {typeof firstSeenAt === "string" && firstSeenAt ? (
          <KeyValueRow label="First seen" value={formatDateTime(firstSeenAt)} />
        ) : null}
        {typeof lastSeenAt === "string" && lastSeenAt ? (
          <KeyValueRow label="Last seen" value={formatDateTime(lastSeenAt)} />
        ) : null}
        {item.capturedAt ? <KeyValueRow label="Captured" value={formatDateTime(item.capturedAt)} /> : null}
      </div>

      {item.media.length ? (
        <div className="space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-content-muted">Media</div>
          <div className="space-y-2">
            {item.media.map((m, idx) => {
              const url = m.fullUrl || m.url;
              return (
                <div key={`${item.id}-media-${idx}`} className="rounded-lg border border-border bg-surface p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold text-content">
                      {idx + 1}. {m.type}
                    </div>
                    {m.status ? (
                      <div className="text-[11px] font-mono text-content-muted">{m.status}</div>
                    ) : null}
                  </div>
                  {url ? (
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block break-all text-xs text-content underline decoration-border hover:decoration-content"
                      title={url}
                    >
                      {url}
                    </a>
                  ) : (
                    <div className="mt-1 text-xs text-content-muted">No URL available</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {(item.headline || item.body) && (
        <div className="space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-content-muted">Copy</div>
          {item.headline ? (
            <div className="rounded-lg border border-border bg-surface p-2">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-content-muted">Headline</div>
              <div className="mt-1 whitespace-pre-wrap text-sm text-content">{item.headline}</div>
            </div>
          ) : null}
          {item.body ? (
            <div className="rounded-lg border border-border bg-surface p-2">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-content-muted">Primary text</div>
              <div className="mt-1 whitespace-pre-wrap text-sm text-content">{item.body}</div>
            </div>
          ) : null}
        </div>
      )}

      {(score || item.hookScore !== undefined || item.funnelStage) && (
        <div className="space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-content-muted">Scores</div>
          <div className="space-y-2">
            {typeof score?.performanceScore === "number" ? (
              <KeyValueRow label="Perf" value={<span className="font-mono text-[12px]">{score.performanceScore}</span>} />
            ) : null}
            {typeof score?.performanceStars === "number" ? (
              <KeyValueRow label="Stars" value={<span className="font-mono text-[12px]">{score.performanceStars}</span>} />
            ) : null}
            {typeof score?.winningScore === "number" ? (
              <KeyValueRow label="Win" value={<span className="font-mono text-[12px]">{score.winningScore}</span>} />
            ) : null}
            {typeof score?.confidence === "number" ? (
              <KeyValueRow label="Conf" value={<span className="font-mono text-[12px]">{score.confidence.toFixed(2)}</span>} />
            ) : null}
            {typeof item.hookScore === "number" ? (
              <KeyValueRow label="Hook" value={<span className="font-mono text-[12px]">{item.hookScore}/10</span>} />
            ) : null}
            {item.funnelStage ? <KeyValueRow label="Stage" value={item.funnelStage} /> : null}
            {score?.scoreVersion ? (
              <KeyValueRow label="Version" value={<span className="font-mono text-[12px]">{score.scoreVersion}</span>} />
            ) : null}
          </div>
        </div>
      )}

      {(facts !== undefined || scores !== undefined || researchRunId !== undefined) && (
        <div className="space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-content-muted">Signals</div>
          {researchRunId ? (
            <KeyValueRow
              label="Run"
              value={<span className="font-mono text-[12px]">{String(researchRunId)}</span>}
            />
          ) : null}
          {facts !== undefined ? (
            <details className="rounded-lg border border-border bg-surface p-2">
              <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-content-muted">
                Facts
              </summary>
              <pre className="mt-2 max-h-[22vh] overflow-auto rounded-md bg-muted p-2 text-[11px] leading-relaxed text-content">
                {JSON.stringify(facts, null, 2)}
              </pre>
            </details>
          ) : null}
          {scores !== undefined ? (
            <details className="rounded-lg border border-border bg-surface p-2">
              <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-content-muted">
                Scores
              </summary>
              <pre className="mt-2 max-h-[22vh] overflow-auto rounded-md bg-muted p-2 text-[11px] leading-relaxed text-content">
                {JSON.stringify(scores, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      )}

      <details className="rounded-lg border border-border bg-surface p-2">
        <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-content-muted">
          Raw payload
        </summary>
        {raw === undefined ? (
          <div className="mt-2 text-sm text-content-muted">Raw payload not available for this item.</div>
        ) : rawString.error ? (
          <div className="mt-2 text-sm text-content-muted">Unable to render raw payload: {rawString.error}</div>
        ) : (
          <pre className="mt-2 max-h-[42vh] overflow-auto rounded-md bg-muted p-2 text-[11px] leading-relaxed text-content">
            {rawString.json}
          </pre>
        )}
      </details>
    </div>
  );
}
