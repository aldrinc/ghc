import { Render } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useMemo } from "react";
import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";
import { FunnelRuntimeProvider } from "@/funnels/funnelRuntime";
import { createFunnelPuckConfig } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import type { RuntimeTrackingEvent } from "@/lib/funnelTracking";
import type { PublicFunnelCommerce } from "@/types/commerce";
import type { PublicFunnelMeta, PublicFunnelPage } from "@/types/funnels";
import "@/runtime.css";

const runtimeConfig = createFunnelPuckConfig();

type PublicFunnelPuckRendererProps = {
  page: PublicFunnelPage;
  meta: PublicFunnelMeta | null;
  productSlug: string;
  funnelSlug: string;
  bundleMode: boolean;
  trackEvent: (event: RuntimeTrackingEvent) => void;
  commerce: PublicFunnelCommerce | null;
  commerceError: string | null;
  visitorId: string;
  sessionId: string;
};

export default function PublicFunnelPuckRenderer({
  page,
  meta,
  productSlug,
  funnelSlug,
  bundleMode,
  trackEvent,
  commerce,
  commerceError,
  visitorId,
  sessionId,
}: PublicFunnelPuckRendererProps) {
  const normalizedPuckData = useMemo(
    () => normalizePuckData(page.puckData, { designSystemTokens: page.designSystemTokens ?? null }),
    [page],
  );

  return (
    <div className="min-h-screen bg-surface">
      <FunnelRuntimeProvider
        value={{
          productSlug,
          funnelSlug,
          pageMap: page.pageMap,
          pageStageMap: page.pageStageMap,
          pageTypeMap: page.pageTypeMap,
          bundleMode,
          entrySlug: meta?.entrySlug ?? null,
          pageStage: page.stage,
          trackEvent,
          commerce,
          commerceError,
          pageId: page.pageId,
          nextPageId: page.nextPageId ?? null,
          visitorId,
          sessionId,
        }}
      >
        <DesignSystemProvider tokens={page.designSystemTokens}>
          <Render config={runtimeConfig} data={(normalizedPuckData ?? page.puckData) as unknown as Data} />
        </DesignSystemProvider>
      </FunnelRuntimeProvider>
    </div>
  );
}
