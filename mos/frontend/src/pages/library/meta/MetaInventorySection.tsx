import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/layout/EmptyState";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, shortId } from "@/lib/format";
import type { InventoryTab, RemotePayload } from "@/hooks/useMetaInventory";
import { inventoryTabs } from "@/hooks/useMetaInventory";
import type {
  MetaRemoteAd,
  MetaRemoteAdSet,
  MetaRemoteCampaign,
  MetaRemoteCreative,
  MetaRemoteImage,
  MetaRemoteVideo,
} from "@/types/meta";

export type MetaInventorySectionProps = {
  inventoryTab: InventoryTab;
  onTabChange: (tab: InventoryTab) => void;
  inventory: RemotePayload | null;
  inventoryLoading: boolean;
  inventoryError: string | null;
  inventoryFetchedAt: string | null;
  onRefresh: () => void;
  hasConfig: boolean;
  canRefresh: boolean;
};

function InventoryLoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 w-24 rounded bg-surface-2" />
          <div className="h-4 flex-1 rounded bg-surface-2" />
          <div className="h-4 w-16 rounded bg-surface-2" />
          <div className="h-4 w-28 rounded bg-surface-2" />
        </div>
      ))}
    </div>
  );
}

function renderImageRow(item: MetaRemoteImage) {
  return (
    <TableRow key={item.hash}>
      <TableCell className="font-mono text-xs">{shortId(item.hash, 6)}</TableCell>
      <TableCell>{item.name || "—"}</TableCell>
      <TableCell className="truncate max-w-[240px]">{item.url || "—"}</TableCell>
      <TableCell>{formatDate(item.created_time)}</TableCell>
    </TableRow>
  );
}

function renderVideoRow(item: MetaRemoteVideo) {
  return (
    <TableRow key={item.id}>
      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
      <TableCell>{item.title || "—"}</TableCell>
      <TableCell>{item.status || "—"}</TableCell>
      <TableCell>{item.length ? `${item.length}s` : "—"}</TableCell>
    </TableRow>
  );
}

function renderCreativeRow(item: MetaRemoteCreative) {
  return (
    <TableRow key={item.id}>
      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
      <TableCell>{item.name || "—"}</TableCell>
      <TableCell>{item.status || "—"}</TableCell>
      <TableCell>{formatDate(item.updated_time)}</TableCell>
    </TableRow>
  );
}

function renderCampaignRow(item: MetaRemoteCampaign) {
  return (
    <TableRow key={item.id}>
      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
      <TableCell>{item.name || "—"}</TableCell>
      <TableCell>{item.effective_status || item.status || "—"}</TableCell>
      <TableCell>{item.objective || "—"}</TableCell>
    </TableRow>
  );
}

function renderAdSetRow(item: MetaRemoteAdSet) {
  return (
    <TableRow key={item.id}>
      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
      <TableCell>{item.name || "—"}</TableCell>
      <TableCell>{item.effective_status || item.status || "—"}</TableCell>
      <TableCell className="font-mono text-xs">{shortId(item.campaign_id, 6)}</TableCell>
    </TableRow>
  );
}

function renderAdRow(item: MetaRemoteAd) {
  return (
    <TableRow key={item.id}>
      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
      <TableCell>{item.name || "—"}</TableCell>
      <TableCell>{item.effective_status || item.status || "—"}</TableCell>
      <TableCell className="font-mono text-xs">{shortId(item.adset_id, 6)}</TableCell>
    </TableRow>
  );
}

const headersByTab: Record<InventoryTab, string[]> = {
  images: ["Hash", "Name", "URL", "Created"],
  videos: ["ID", "Title", "Status", "Length"],
  creatives: ["ID", "Name", "Status", "Updated"],
  campaigns: ["ID", "Name", "Status", "Objective"],
  adsets: ["ID", "Name", "Status", "Campaign"],
  ads: ["ID", "Name", "Status", "Ad Set"],
};

export function MetaInventorySection({
  inventoryTab,
  onTabChange,
  inventory,
  inventoryLoading,
  inventoryError,
  inventoryFetchedAt,
  onRefresh,
  hasConfig,
  canRefresh,
}: MetaInventorySectionProps) {
  const headers = headersByTab[inventoryTab];

  function renderRows() {
    if (!inventory) return null;
    switch (inventoryTab) {
      case "images":
        return (inventory as { data: MetaRemoteImage[] }).data.map(renderImageRow);
      case "videos":
        return (inventory as { data: MetaRemoteVideo[] }).data.map(renderVideoRow);
      case "creatives":
        return (inventory as { data: MetaRemoteCreative[] }).data.map(renderCreativeRow);
      case "campaigns":
        return (inventory as { data: MetaRemoteCampaign[] }).data.map(renderCampaignRow);
      case "adsets":
        return (inventory as { data: MetaRemoteAdSet[] }).data.map(renderAdSetRow);
      case "ads":
        return (inventory as { data: MetaRemoteAd[] }).data.map(renderAdRow);
    }
  }

  return (
    <div className="ds-card ds-card--md shadow-none space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-content">Meta inventory (live)</div>
          <div className="text-xs text-content-muted">Direct read-only data from Meta.</div>
        </div>
        <div className="flex items-center gap-2 text-xs text-content-muted">
          {inventoryFetchedAt ? <span>Fetched {formatDate(inventoryFetchedAt)}</span> : null}
          <Button
            variant="secondary"
            size="xs"
            onClick={onRefresh}
            disabled={inventoryLoading || !canRefresh}
          >
            {inventoryLoading ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {inventoryTabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onTabChange(tab.key)}
            className={[
              "rounded-full px-3 py-1.5 text-xs font-semibold transition",
              inventoryTab === tab.key
                ? "bg-primary text-primary-foreground"
                : "bg-surface-2 text-content-muted hover:bg-hover",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {inventoryError && (
        <Callout variant="danger" size="sm">
          {inventoryError}
        </Callout>
      )}

      {!hasConfig && (
        <EmptyState description="Select a Meta config to browse remote inventory." />
      )}

      {inventoryLoading && <InventoryLoadingSkeleton />}

      {!inventoryLoading && inventory && (
        <Table variant="ghost">
          <TableHeader>
            <TableRow>
              {headers.map((h) => (
                <TableHeadCell key={h}>{h}</TableHeadCell>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>{renderRows()}</TableBody>
        </Table>
      )}
    </div>
  );
}
