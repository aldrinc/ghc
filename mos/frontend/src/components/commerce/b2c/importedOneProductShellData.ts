import { useEffect, useState } from "react";
import type { Data } from "@measured/puck";

import type { SiteDetail, SitePageDetail } from "@/api/sites";
import { augmentImportedSourceSectionProps } from "@/components/imported-site/importedGlobalNavigation";
import { normalizePuckData } from "@/funnels/puckData";
import { resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";

type BlockRecord = {
  type: string;
  props: Record<string, unknown>;
};

type ExtractedSection = {
  wrapperProps: Record<string, unknown>;
  sectionProps: Record<string, unknown>;
};

export type ImportedOneProductShellData = {
  pageName?: string;
  theme?: unknown;
  themeJson?: string;
  renderMode?: string;
  sharedRuntimeSource?: string;
  sharedHeadAssets?: unknown;
  header: ExtractedSection;
  footer: ExtractedSection;
};

export type ImportedOneProductShellState =
  | { status: "loading" }
  | { status: "ready"; shell: ImportedOneProductShellData }
  | { status: "unavailable" }
  | { status: "error"; message: string };

const publicApiBaseUrl = resolvePublicApiBaseUrl();
const importedShellCache = new Map<string, Promise<ImportedOneProductShellData | null>>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isBlockRecord(value: unknown): value is BlockRecord {
  return isRecord(value) && typeof value.type === "string" && isRecord(value.props);
}

function deepClone<T>(value: T): T {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

function getBlocks(value: unknown): BlockRecord[] {
  return Array.isArray(value) ? value.filter(isBlockRecord) : [];
}

function findImportedPageBlock(data: Data): BlockRecord | null {
  return getBlocks(data.content).find((block) => block.type === "ImportedPage") || null;
}

function extractImportedSection(
  sectionBlocks: BlockRecord[],
  innerType: "ImportedHeaderSection" | "ImportedFooterSection",
): ExtractedSection | null {
  for (const block of sectionBlocks) {
    if (block.type !== "ImportedSection") {
      continue;
    }
    const innerBlock = getBlocks(block.props.content).find((candidate) => candidate.type === innerType);
    if (!innerBlock) {
      continue;
    }
    return {
      wrapperProps: deepClone(block.props),
      sectionProps: augmentImportedSourceSectionProps(deepClone(innerBlock.props)),
    };
  }
  return null;
}

export function extractImportedOneProductShellData(data: Data): ImportedOneProductShellData | null {
  const pageBlock = findImportedPageBlock(data);
  if (!pageBlock) {
    return null;
  }

  const sectionBlocks = getBlocks(pageBlock.props.content);
  const header = extractImportedSection(sectionBlocks, "ImportedHeaderSection");
  const footer = extractImportedSection(sectionBlocks, "ImportedFooterSection");
  const sharedRuntimeSource =
    typeof pageBlock.props.sharedRuntimeSource === "string" ? pageBlock.props.sharedRuntimeSource : undefined;

  if (!header || !footer || !sharedRuntimeSource?.trim()) {
    return null;
  }

  return {
    pageName: typeof pageBlock.props.pageName === "string" ? pageBlock.props.pageName : undefined,
    theme: pageBlock.props.theme,
    themeJson: typeof pageBlock.props.themeJson === "string" ? pageBlock.props.themeJson : undefined,
    renderMode: typeof pageBlock.props.renderMode === "string" ? pageBlock.props.renderMode : "source",
    sharedRuntimeSource,
    sharedHeadAssets: pageBlock.props.sharedHeadAssets,
    header,
    footer,
  };
}

function extractPreviewShellKey(siteId: string, siteClientId: string): string {
  return `preview:${siteClientId}:${siteId}`;
}

function extractPublicShellKey(productSlug: string, funnelSlug: string): string {
  return `public:${productSlug}:${funnelSlug}`;
}

async function loadPreviewImportedShell(
  apiGet: <T>(path: string) => Promise<T>,
  siteId: string,
  siteClientId: string,
): Promise<ImportedOneProductShellData | null> {
  const site = await apiGet<SiteDetail>(
    `/sites/${siteId}?clientId=${encodeURIComponent(siteClientId)}`,
  );
  if (!site.entryPageId) {
    return null;
  }

  const pageDetail = await apiGet<SitePageDetail>(
    `/sites/${siteId}/pages/${site.entryPageId}?clientId=${encodeURIComponent(siteClientId)}`,
  );
  const sourcePuckData =
    (pageDetail.latestDraft?.puckData as Data | null | undefined) ||
    (pageDetail.latestApproved?.puckData as Data | null | undefined);
  if (!sourcePuckData) {
    return null;
  }

  const normalizedData = normalizePuckData(sourcePuckData, {
    designSystemTokens: pageDetail.designSystemTokens ?? null,
  });
  return extractImportedOneProductShellData(normalizedData);
}

async function loadPublicImportedShell(
  productSlug: string,
  funnelSlug: string,
): Promise<ImportedOneProductShellData | null> {
  const response = await fetch(
    `${publicApiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/pages/home`,
  );
  if (!response.ok) {
    const message = await response.text();
    throw new Error(
      `Failed to load the imported home page shell (${response.status}): ${message || response.statusText}.`,
    );
  }

  const payload = (await response.json()) as {
    puckData?: Data | null;
    designSystemTokens?: unknown;
  };
  if (!payload.puckData) {
    return null;
  }

  const normalizedData = normalizePuckData(payload.puckData, {
    designSystemTokens: payload.designSystemTokens ?? null,
  });
  return extractImportedOneProductShellData(normalizedData);
}

export function useImportedOneProductShellState({
  apiGet,
  siteId,
  siteClientId,
  productSlug,
  funnelSlug,
}: {
  apiGet: <T>(path: string) => Promise<T>;
  siteId?: string | null;
  siteClientId?: string | null;
  productSlug?: string | null;
  funnelSlug?: string | null;
}): ImportedOneProductShellState {
  const canLoadPreviewShell = Boolean(siteId && siteClientId);
  const canLoadPublicShell = Boolean(!canLoadPreviewShell && productSlug?.trim() && funnelSlug?.trim());
  const [state, setState] = useState<ImportedOneProductShellState>(() =>
    canLoadPreviewShell || canLoadPublicShell ? { status: "loading" } : { status: "unavailable" },
  );

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        if (canLoadPreviewShell) {
          const previewSiteId = siteId?.trim();
          const previewSiteClientId = siteClientId?.trim();
          if (!previewSiteId || !previewSiteClientId) {
            if (!cancelled) {
              setState({ status: "unavailable" });
            }
            return;
          }

          const cacheKey = extractPreviewShellKey(previewSiteId, previewSiteClientId);
          let shellPromise = importedShellCache.get(cacheKey);
          if (!shellPromise) {
            shellPromise = loadPreviewImportedShell(apiGet, previewSiteId, previewSiteClientId);
            importedShellCache.set(cacheKey, shellPromise);
          }

          if (!cancelled) {
            setState({ status: "loading" });
          }
          const shell = await shellPromise;
          if (!cancelled) {
            setState(shell ? { status: "ready", shell } : { status: "unavailable" });
          }
          return;
        }

        const resolvedProductSlug = productSlug?.trim() || "";
        const resolvedFunnelSlug = funnelSlug?.trim() || "";
        if (!canLoadPublicShell || !resolvedProductSlug || !resolvedFunnelSlug) {
          if (!cancelled) {
            setState({ status: "unavailable" });
          }
          return;
        }

        const cacheKey = extractPublicShellKey(resolvedProductSlug, resolvedFunnelSlug);
        let shellPromise = importedShellCache.get(cacheKey);
        if (!shellPromise) {
          shellPromise = loadPublicImportedShell(resolvedProductSlug, resolvedFunnelSlug);
          importedShellCache.set(cacheKey, shellPromise);
        }

        if (!cancelled) {
          setState({ status: "loading" });
        }
        const shell = await shellPromise;
        if (!cancelled) {
          setState(shell ? { status: "ready", shell } : { status: "unavailable" });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Failed to load the imported storefront shell.",
          });
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [apiGet, canLoadPreviewShell, canLoadPublicShell, funnelSlug, productSlug, siteClientId, siteId]);

  return state;
}
