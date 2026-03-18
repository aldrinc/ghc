import { useMemo } from "react";
import type { PaidAdsQaRun } from "@/api/paidAdsQa";
import type { AdReviewItem } from "@/types/creativeReview";
import type { MetaPipelineAsset, MetaPublishSelection } from "@/types/meta";
import type { AssetBrief } from "@/types/artifacts";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import { summarizeViolations, buildFindingsBySpec } from "./useFindingsBySpec";

const apiBaseUrl = resolveRequiredApiBaseUrl();

function resolveAssetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

function readSwipeString(
  record: Record<string, unknown>,
  camelKey: string,
  snakeKey?: string,
): string | null {
  const camelValue = record[camelKey];
  if (typeof camelValue === "string" && camelValue.trim()) return camelValue;

  if (!snakeKey) return null;
  const snakeValue = record[snakeKey];
  if (typeof snakeValue === "string" && snakeValue.trim()) return snakeValue;
  return null;
}

type UseCreativeReviewInput = {
  pipelineAssets: MetaPipelineAsset[];
  publishSelections: MetaPublishSelection[];
  assetBriefs: AssetBrief[];
  qaRuns: PaidAdsQaRun[];
  experimentNameById: Record<string, string>;
  variantNameById: Record<string, string>;
};

/**
 * Transforms Meta pipeline assets + QA findings + publish selections
 * into a flat list of AdReviewItem objects for the creative review grid.
 */
export function useCreativeReview({
  pipelineAssets,
  publishSelections,
  assetBriefs,
  qaRuns,
  experimentNameById,
  variantNameById,
}: UseCreativeReviewInput): AdReviewItem[] {
  return useMemo(() => {
    const findingsBySpec = buildFindingsBySpec(qaRuns);
    const selectionByAssetId = new Map(
      publishSelections.map((s) => [s.assetId, s]),
    );
    const briefById = new Map(assetBriefs.map((b) => [b.id, b]));

    return pipelineAssets.map((item): AdReviewItem => {
      const asset = item.asset;
      const spec = item.creative_spec;
      const aiMeta = (asset.ai_metadata || {}) as Record<string, unknown>;
      const swipeCopy = (aiMeta.swipeCopyPack || {}) as Record<string, unknown>;
      const swipeInputs = (aiMeta.swipeCopyInputs || {}) as Record<string, unknown>;
      const briefId = typeof aiMeta.assetBriefId === "string" ? aiMeta.assetBriefId : null;
      const brief = briefId ? briefById.get(briefId) ?? null : null;

      // Resolve ad copy from creative spec, falling back to swipe copy pack
      const hasSpec = Boolean(spec?.id);
      let primaryText: string | null = null;
      let headline: string | null = null;
      let description: string | null = null;
      let ctaText: string | null = null;
      let destUrl: string | null = null;
      let copySource: AdReviewItem["copySource"] = "none";

      if (hasSpec) {
        primaryText = spec?.primary_text ?? null;
        headline = spec?.headline ?? null;
        description = spec?.description ?? null;
        ctaText = spec?.call_to_action_type ?? null;
        destUrl = spec?.destination_url ?? null;
        copySource = "creative_spec";
      } else if (Object.keys(swipeCopy).length) {
        primaryText = readSwipeString(swipeCopy, "metaPrimaryText", "meta_primary_text");
        headline = readSwipeString(swipeCopy, "metaHeadline", "meta_headline");
        description = readSwipeString(swipeCopy, "metaDescription", "meta_description");
        ctaText = readSwipeString(swipeCopy, "metaCta", "meta_cta");
        copySource = "swipe_copy_pack";
      }

      const specId = spec?.id ?? null;
      const findings = specId ? findingsBySpec.get(specId) ?? [] : [];
      const selection = selectionByAssetId.get(asset.id);

      return {
        assetId: asset.id,
        specId,
        imageUrl: resolveAssetUrl(asset.public_url),
        imageAlt: `Asset ${asset.id.slice(0, 8)}`,
        assetKind: asset.asset_kind || "image",
        format: (aiMeta.format as string) ?? "",
        width: asset.width ?? null,
        height: asset.height ?? null,
        primaryText,
        headline,
        description,
        cta: ctaText,
        destinationUrl: destUrl,
        copySource,
        platform: "meta",
        briefId,
        experimentName: brief?.experimentId
          ? experimentNameById[brief.experimentId] ?? null
          : null,
        variantName: brief?.variantId
          ? variantNameById[brief.variantId] ?? brief.variantName ?? null
          : null,
        angle: readSwipeString(swipeInputs, "angleUsed") ?? readSwipeString(swipeCopy, "angle") ?? null,
        hook: (swipeCopy.hook as string) ?? null,
        funnelStage: readSwipeString(swipeCopy, "funnelStage", "funnel_stage"),
        selectedVariation: readSwipeString(swipeCopy, "selectedVariation", "selected_variation"),
        requirementIndex: typeof aiMeta.requirementIndex === "number" ? aiMeta.requirementIndex : null,
        sourceSwipeLabel: (aiMeta.swipeSourceLabel as string) ?? null,
        sourceSwipeUrl: null,
        generationGroup: (aiMeta.generationKey as string) ?? null,
        createdAt: asset.created_at || "",
        specReady: hasSpec,
        publishDecision: selection?.decision === "excluded" ? "excluded" : null,
        violations: summarizeViolations(findings),
        findings,
        brief,
      };
    });
  }, [pipelineAssets, publishSelections, assetBriefs, qaRuns, experimentNameById, variantNameById]);
}
