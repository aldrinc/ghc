import type { MetaPipelineAsset } from "@/types/meta";

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function readPipelineAssetBriefId(item: MetaPipelineAsset): string | null {
  const metadata = readRecord(item.asset.ai_metadata);
  return readString(metadata?.assetBriefId);
}

export function readPipelineCreativeGenerationBatchId(item: MetaPipelineAsset): string | null {
  const metadata = readRecord(item.asset.ai_metadata);
  return readString(metadata?.creativeGenerationBatchId);
}

function createdAtMs(item: MetaPipelineAsset): number {
  const createdAt = item.asset.created_at;
  if (!createdAt) return 0;
  const value = new Date(createdAt).getTime();
  return Number.isFinite(value) ? value : 0;
}

export function selectLatestProductionBatchPipelineAssets(
  items: MetaPipelineAsset[],
  validBriefIds?: Iterable<string>,
): { batchId: string | null; assets: MetaPipelineAsset[] } {
  const allowedBriefIds = validBriefIds ? new Set(validBriefIds) : null;
  const batches = new Map<string, { latestCreatedAt: number; assets: MetaPipelineAsset[] }>();

  items.forEach((item) => {
    const briefId = readPipelineAssetBriefId(item);
    if (!briefId) return;
    if (allowedBriefIds && !allowedBriefIds.has(briefId)) return;

    const batchId = readPipelineCreativeGenerationBatchId(item);
    if (!batchId) return;

    const createdAt = createdAtMs(item);
    const existing = batches.get(batchId);
    if (!existing) {
      batches.set(batchId, { latestCreatedAt: createdAt, assets: [item] });
      return;
    }
    existing.latestCreatedAt = Math.max(existing.latestCreatedAt, createdAt);
    existing.assets.push(item);
  });

  if (!batches.size) {
    return { batchId: null, assets: [] };
  }

  const [latestBatchId, latestBatch] = Array.from(batches.entries()).sort(
    (left, right) => right[1].latestCreatedAt - left[1].latestCreatedAt,
  )[0];

  return {
    batchId: latestBatchId,
    assets: [...latestBatch.assets].sort((left, right) => createdAtMs(right) - createdAtMs(left)),
  };
}

export function groupPipelineAssetsByBriefId(
  items: MetaPipelineAsset[],
): Map<string, MetaPipelineAsset[]> {
  const grouped = new Map<string, MetaPipelineAsset[]>();
  items.forEach((item) => {
    const briefId = readPipelineAssetBriefId(item);
    if (!briefId) return;
    const existing = grouped.get(briefId);
    if (existing) {
      existing.push(item);
    } else {
      grouped.set(briefId, [item]);
    }
  });
  return grouped;
}
