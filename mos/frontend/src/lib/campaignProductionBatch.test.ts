import { describe, expect, it } from "vitest";
import type { MetaPipelineAsset } from "@/types/meta";
import {
  groupPipelineAssetsByBriefId,
  selectLatestProductionBatchPipelineAssets,
} from "./campaignProductionBatch";

function makeAsset({
  id,
  createdAt,
  briefId,
  batchId,
}: {
  id: string;
  createdAt: string;
  briefId?: string;
  batchId?: string;
}): MetaPipelineAsset {
  return {
    asset: {
      id,
      public_id: id,
      created_at: createdAt,
      public_url: `/public/assets/${id}`,
      ai_metadata: {
        ...(briefId ? { assetBriefId: briefId } : {}),
        ...(batchId ? { creativeGenerationBatchId: batchId } : {}),
      },
    },
    campaign: null,
    experiment: null,
    creative_spec: null,
    adset_specs: [],
    meta: null,
  };
}

describe("campaignProductionBatch", () => {
  it("returns only the latest non-null creative generation batch", () => {
    const assets = [
      makeAsset({
        id: "manual-asset",
        createdAt: "2026-04-19T18:00:00Z",
        briefId: "brief-1",
      }),
      makeAsset({
        id: "older-batch-asset",
        createdAt: "2026-04-19T19:00:00Z",
        briefId: "brief-1",
        batchId: "batch-older",
      }),
      makeAsset({
        id: "latest-batch-asset-a",
        createdAt: "2026-04-19T20:00:00Z",
        briefId: "brief-1",
        batchId: "batch-latest",
      }),
      makeAsset({
        id: "latest-batch-asset-b",
        createdAt: "2026-04-19T20:05:00Z",
        briefId: "brief-2",
        batchId: "batch-latest",
      }),
    ];

    const result = selectLatestProductionBatchPipelineAssets(assets, ["brief-1", "brief-2"]);

    expect(result.batchId).toBe("batch-latest");
    expect(result.assets.map((item) => item.asset.id)).toEqual([
      "latest-batch-asset-b",
      "latest-batch-asset-a",
    ]);
  });

  it("ignores assets whose briefs are not part of the current campaign brief set", () => {
    const assets = [
      makeAsset({
        id: "valid-asset",
        createdAt: "2026-04-19T20:00:00Z",
        briefId: "brief-valid",
        batchId: "batch-valid",
      }),
      makeAsset({
        id: "other-brief-asset",
        createdAt: "2026-04-19T21:00:00Z",
        briefId: "brief-other",
        batchId: "batch-other",
      }),
    ];

    const result = selectLatestProductionBatchPipelineAssets(assets, ["brief-valid"]);

    expect(result.batchId).toBe("batch-valid");
    expect(result.assets.map((item) => item.asset.id)).toEqual(["valid-asset"]);
  });

  it("groups selected production assets by brief id", () => {
    const grouped = groupPipelineAssetsByBriefId([
      makeAsset({
        id: "asset-1",
        createdAt: "2026-04-19T20:00:00Z",
        briefId: "brief-1",
        batchId: "batch-latest",
      }),
      makeAsset({
        id: "asset-2",
        createdAt: "2026-04-19T20:01:00Z",
        briefId: "brief-1",
        batchId: "batch-latest",
      }),
      makeAsset({
        id: "asset-3",
        createdAt: "2026-04-19T20:02:00Z",
        briefId: "brief-2",
        batchId: "batch-latest",
      }),
    ]);

    expect(grouped.get("brief-1")?.map((item) => item.asset.id)).toEqual(["asset-1", "asset-2"]);
    expect(grouped.get("brief-2")?.map((item) => item.asset.id)).toEqual(["asset-3"]);
  });
});
