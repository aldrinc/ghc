import { createContext, useContext, type ReactNode } from "react";

import type { RuntimeTrackingEvent } from "@/lib/funnelTracking";
import { buildPublicFunnelPath } from "@/funnels/runtimeRouting";
import type { PublicFunnelCommerce, PublicFunnelStage, SitePageType } from "@/types/funnels";

export type FunnelRuntimeContextValue = {
  productSlug: string;
  funnelSlug: string;
  pageMap: Record<string, string>;
  pageStageMap: Record<string, PublicFunnelStage>;
  pageTypeMap?: Record<string, SitePageType>;
  bundleMode?: boolean;
  entrySlug?: string | null;
  pageStage?: PublicFunnelStage;
  trackEvent?: (event: RuntimeTrackingEvent) => void;
  commerce?: PublicFunnelCommerce | null;
  commerceError?: string | null;
  pageId?: string | null;
  nextPageId?: string | null;
  visitorId?: string | null;
  sessionId?: string | null;
  resolvePagePath?: (slug: string) => string;
  resolveSitePath?: (sitePath: string) => string;
  publicRuntime?: boolean;
};

const FunnelRuntimeContext = createContext<FunnelRuntimeContextValue | null>(null);

export function FunnelRuntimeProvider({
  value,
  children,
}: {
  value: FunnelRuntimeContextValue;
  children: ReactNode;
}) {
  return <FunnelRuntimeContext.Provider value={value}>{children}</FunnelRuntimeContext.Provider>;
}

export function useFunnelRuntime() {
  return useContext(FunnelRuntimeContext);
}

export function resolveRuntimePagePath(runtime: FunnelRuntimeContextValue, slug: string): string {
  const normalizedSlug = (slug || "").trim();
  if (!normalizedSlug) {
    return "#";
  }
  if (runtime.resolvePagePath) {
    return runtime.resolvePagePath(normalizedSlug);
  }
  if (runtime.bundleMode) {
    return `/${encodeURIComponent(runtime.productSlug)}/${encodeURIComponent(runtime.funnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
  }
  return `/f/${encodeURIComponent(runtime.productSlug)}/${encodeURIComponent(runtime.funnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
}

export function resolveRuntimeSitePath(runtime: FunnelRuntimeContextValue, sitePath: string): string {
  const rawSitePath = (sitePath || "").trim();
  const normalizedSitePath = rawSitePath.replace(/^\/+/, "");
  if (!normalizedSitePath) {
    if (runtime.resolveSitePath) {
      return runtime.resolveSitePath("");
    }
    return buildPublicFunnelPath({
      productSlug: runtime.productSlug,
      funnelSlug: runtime.funnelSlug,
      bundleMode: runtime.bundleMode || false,
      sitePath: "",
    });
  }
  if (runtime.resolveSitePath) {
    return runtime.resolveSitePath(normalizedSitePath);
  }
  return buildPublicFunnelPath({
    productSlug: runtime.productSlug,
    funnelSlug: runtime.funnelSlug,
    bundleMode: runtime.bundleMode || false,
    sitePath: normalizedSitePath,
  });
}
