import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetReviewGrid } from "@/components/review/AssetReviewGrid";
import type { AssetReviewItem } from "@/types/assetReview";

const ITEMS: AssetReviewItem[] = [
  {
    id: "asset-1",
    kind: "swipe",
    brandName: "Northwind",
    headline: "Winning wellness creative",
    body: "UGC style image ad for a supplement launch.",
    ctaText: "Shop now",
    media: [{ type: "image", url: "https://example.com/a.jpg", thumbUrl: "https://example.com/a-thumb.jpg" }],
    platform: ["META_ADS_LIBRARY"],
    reviewStatus: "pending_review",
    source: "gethookd",
    sourceLastSyncedAt: "2026-03-25T12:00:00Z",
    collectionIds: ["launch"],
    isInLaunchCollection: true,
    destinationHostname: "northwind.test",
    performanceScore: 88,
    performanceTier: "winning",
    daysActive: 12,
    status: "active",
  },
  {
    id: "asset-2",
    kind: "swipe",
    brandName: "Bluebird",
    headline: "Catalog fallback card",
    body: "Static catalog-driven creative.",
    media: [{ type: "image", url: "https://example.com/b.jpg", thumbUrl: "https://example.com/b-thumb.jpg" }],
    platform: ["TIKTOK_CREATIVE_CENTER"],
    reviewStatus: "approved",
    source: "catalog",
    sourceLastSyncedAt: "2026-03-18T12:00:00Z",
    collectionIds: [],
    isInLaunchCollection: false,
    destinationHostname: "bluebird.test",
    performanceScore: 72,
    performanceTier: "optimized",
    daysActive: 4,
    status: "inactive",
  },
];

function Harness({
  onCardClick = vi.fn(),
}: {
  onCardClick?: (item: AssetReviewItem) => void;
}) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  return (
    <AssetReviewGrid
      items={ITEMS}
      selectedIds={selectedIds}
      onSelectionChange={setSelectedIds}
      onCardClick={onCardClick}
      availablePlatforms={["META_ADS_LIBRARY", "TIKTOK_CREATIVE_CENTER"]}
    />
  );
}

describe("AssetReviewGrid", () => {
  it("filters assets by search and source", async () => {
    const user = userEvent.setup();

    render(<Harness />);

    await user.type(screen.getByPlaceholderText(/search brand, headline, body, or asset id/i), "Northwind");

    expect(screen.getByText("Northwind")).toBeInTheDocument();
    expect(screen.queryByText("Bluebird")).not.toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("All sources"), {
      target: { value: "catalog" },
    });

    expect(screen.queryByText("Northwind")).not.toBeInTheDocument();
    expect(screen.queryByText("Bluebird")).not.toBeInTheDocument();
    expect(screen.getByText(/no assets match the current filters/i)).toBeInTheDocument();
  });

  it("selects and deselects only filtered assets", async () => {
    const user = userEvent.setup();

    render(<Harness />);

    fireEvent.change(screen.getByDisplayValue("All sources"), {
      target: { value: "gethookd" },
    });

    await user.click(screen.getByLabelText(/select all/i));
    expect(screen.getByText(/1 of 2 assets/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^1 selected$/i)).toHaveLength(2);

    fireEvent.change(screen.getByDisplayValue("GetHookd"), {
      target: { value: "catalog" },
    });

    expect(screen.getByText(/0 in view • 1 total selected/i)).toBeInTheDocument();

    await user.click(screen.getByLabelText(/select all/i));
    expect(screen.getByText(/1 in view • 2 total selected/i)).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("Catalog"), {
      target: { value: "all" },
    });

    expect(screen.getAllByText(/^2 selected$/i)).toHaveLength(2);
  });

  it("opens the clicked asset from the card body", async () => {
    const user = userEvent.setup();
    const onCardClick = vi.fn();

    render(<Harness onCardClick={onCardClick} />);

    await user.click(screen.getByText("Winning wellness creative"));

    expect(onCardClick).toHaveBeenCalledTimes(1);
    expect(onCardClick).toHaveBeenCalledWith(expect.objectContaining({ id: "asset-1" }));
  });
});
