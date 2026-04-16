import { useEffect, useMemo, useState } from "react";

import { MarkdownViewer } from "@/components/ui/MarkdownViewer";
import { resolveRuntimePagePath, useFunnelRuntime } from "@/funnels/puckConfig";
import { resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";

type FunnelCompliancePageKey = "privacy_policy" | "terms_of_service" | "returns_refunds_policy";

type FunnelCompliancePageResponse = {
  pageKey: FunnelCompliancePageKey;
  title: string;
  markdown: string;
};

const apiBaseUrl = resolvePublicApiBaseUrl();

async function parsePublicError(resp: Response): Promise<string> {
  try {
    const payload = (await resp.clone().json()) as { detail?: unknown; message?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message;
    }
  } catch {
    const text = await resp.text();
    if (text.trim()) {
      return text;
    }
  }
  return resp.statusText || "Request failed";
}

function resolveWebsiteUrl(runtime: ReturnType<typeof useFunnelRuntime>): string | null {
  if (!runtime) return null;

  const salesPageId = Object.entries(runtime.pageStageMap).find(([, stage]) => stage === "sales")?.[0] || null;
  const currentSlug = runtime.pageId ? runtime.pageMap[runtime.pageId] || null : null;
  const salesSlug = salesPageId ? runtime.pageMap[salesPageId] || null : null;
  const preferredSlug = salesSlug || currentSlug || runtime.entrySlug || null;
  if (!preferredSlug) return null;

  return new URL(resolveRuntimePagePath(runtime, preferredSlug), window.location.origin).toString();
}

export function FunnelCompliancePage({
  pageKey,
  pageTitle,
}: {
  pageKey: FunnelCompliancePageKey;
  pageTitle?: string;
}) {
  const runtime = useFunnelRuntime();
  const [policyPage, setPolicyPage] = useState<FunnelCompliancePageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const websiteUrl = useMemo(() => resolveWebsiteUrl(runtime), [runtime]);

  useEffect(() => {
    if (!runtime?.productSlug || !runtime.funnelSlug || !websiteUrl) {
      return;
    }

    const controller = new AbortController();
    const query = new URLSearchParams({ website_url: websiteUrl });
    const url = `${apiBaseUrl}/public/funnels/${encodeURIComponent(runtime.productSlug)}/${encodeURIComponent(runtime.funnelSlug)}/policy-pages/${encodeURIComponent(pageKey)}?${query.toString()}`;

    setLoading(true);
    setError(null);
    setPolicyPage(null);

    fetch(url, { signal: controller.signal })
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parsePublicError(resp));
        }
        return (await resp.json()) as FunnelCompliancePageResponse;
      })
      .then((payload) => {
        setPolicyPage(payload);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Unable to load policy page");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [pageKey, runtime?.funnelSlug, runtime?.productSlug, websiteUrl]);

  if (!runtime) {
    throw new Error("FunnelCompliancePage requires funnel runtime context.");
  }

  if (!websiteUrl) {
    throw new Error("FunnelCompliancePage requires a resolvable public funnel URL.");
  }

  return (
    <section className="min-h-screen bg-[#f7f3ed] px-4 py-10 text-content sm:px-6 lg:px-8 lg:py-14">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6">
          <p className="text-xs font-medium uppercase tracking-[0.24em] text-content-muted">Compliance</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-content sm:text-4xl">
            {policyPage?.title || pageTitle || "Policy Page"}
          </h1>
        </div>

        {loading ? (
          <div className="rounded-[28px] border border-border bg-surface px-5 py-5 text-sm text-content-muted shadow-sm sm:px-6">
            Loading {pageTitle || "policy page"}...
          </div>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="rounded-[28px] border border-danger/30 bg-danger/10 px-5 py-5 text-sm text-danger shadow-sm sm:px-6"
          >
            Unable to load {pageTitle || "policy page"}. {error}
          </div>
        ) : null}

        {policyPage ? (
          <div className="rounded-[28px] border border-border bg-surface px-5 py-6 shadow-sm sm:px-6 lg:px-8">
            <MarkdownViewer content={policyPage.markdown} className="max-w-none px-0" />
          </div>
        ) : null}
      </div>
    </section>
  );
}
