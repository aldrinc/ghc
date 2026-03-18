import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorState } from "@/components/layout/ErrorState";
import { InlineWorkspacePicker } from "@/components/layout/InlineWorkspacePicker";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button, buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { useClients } from "@/api/clients";
import { useStopWorkflow, useWorkflows } from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";

type Filters = {
  status: string;
  kind: string;
  client: string;
  campaign: string;
};

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatKind(kind: string) {
  return kind
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

function formatElapsed(startedAt: string, finishedAt?: string | null) {
  const start = new Date(startedAt).getTime();
  if (Number.isNaN(start)) return "—";
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function WorkflowsPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product, isLoading: isLoadingProduct } = useProductContext();
  const workflowsEnabled = Boolean(workspace?.id && product?.id);
  const { data: workflows, isLoading, isError, refetch } = useWorkflows(
    workflowsEnabled ? { clientId: workspace.id, productId: product.id } : undefined,
    { enabled: workflowsEnabled },
  );
  const { data: clients } = useClients();
  const [searchParams, setSearchParams] = useSearchParams();
  const [stopId, setStopId] = useState<string | null>(null);
  const stopWorkflow = useStopWorkflow();

  const filters: Filters = {
    status: searchParams.get("status") || "",
    kind: searchParams.get("kind") || "",
    client: searchParams.get("client") || "",
    campaign: searchParams.get("campaign") || "",
  };

  const setFilter = (key: keyof Filters, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  const clearFilters = () => setSearchParams(new URLSearchParams(), { replace: true });

  const clientLookup = useMemo(() => {
    const map: Record<string, string> = {};
    (clients || []).forEach((client) => {
      map[client.id] = client.name;
    });
    return map;
  }, [clients]);

  const statusOptions = useMemo(
    () => Array.from(new Set((workflows || []).map((wf) => wf.status))).sort(),
    [workflows]
  );
  const kindOptions = useMemo(
    () => Array.from(new Set((workflows || []).map((wf) => wf.kind))).sort(),
    [workflows]
  );
  const clientOptions = useMemo(
    () => Array.from(new Set((workflows || []).map((wf) => wf.client_id).filter(Boolean))).sort(),
    [workflows]
  );
  const campaignOptions = useMemo(
    () => Array.from(new Set((workflows || []).map((wf) => wf.campaign_id).filter(Boolean))).sort(),
    [workflows]
  );

  const filteredWorkflows = useMemo(() => {
    const list = workflows || [];
    return list
      .filter((wf) => {
        if (product?.id && wf.product_id !== product.id) return false;
        if (filters.status && wf.status !== filters.status) return false;
        if (filters.kind && wf.kind !== filters.kind) return false;
        if (filters.client && wf.client_id !== filters.client) return false;
        if (filters.campaign && wf.campaign_id !== filters.campaign) return false;
        return true;
      })
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
  }, [workflows, filters, product?.id]);

  const handleConfirmStop = () => {
    if (!stopId) return;
    stopWorkflow.mutate(stopId, {
      onSuccess: () => setStopId(null),
      onSettled: () => stopWorkflow.reset(),
    });
  };

  const renderFilter = (
    key: keyof Filters,
    label: string,
    options: Array<{ value: string; label: string }>
  ) => (
    <div className="flex flex-col gap-1 text-xs text-content-muted">
      <span>{label}</span>
      <Select
        value={filters[key]}
        onChange={(e) => setFilter(key, e.target.value)}
        options={[{ value: "", label: "All" }, ...options]}
      />
    </div>
  );

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Workflows" description="Select a workspace to view workflow runs." />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to view workflow runs."
          actions={<InlineWorkspacePicker />}
        />
      </div>
    );
  }

  if (isLoadingProduct && !product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Workflows" description="Loading workflow runs for the active product." />
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading workflows…</div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Workflows" description="Select a product to view product-scoped workflow runs." />
        <EmptyState
          title="No product selected"
          description="Choose a product from the header to view workflow runs for that product."
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Workflows"
        description={
          product?.title
            ? `Monitor workflow runs for ${product.title}.`
            : "Monitor workflow runs with filters and quick actions."
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={clearFilters} disabled={!searchParams.toString()}>
              Clear filters
            </Button>
            <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
              Refresh
            </Button>
          </div>
        }
      />

      <div className="ds-card ds-card--md p-0 shadow-none">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
          <div className="text-sm font-semibold text-content">Workflow runs</div>
          <div className="text-xs text-content-muted">
            {filteredWorkflows.length} shown · {workflows?.length || 0} total
          </div>
          </div>
        </div>

        <div className="border-b border-border px-4 py-3">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {renderFilter(
              "status",
              "Status",
              statusOptions.map((value) => ({ value, label: value || "Unknown" }))
            )}
            {renderFilter(
              "kind",
              "Kind",
              kindOptions.map((value) => ({ value, label: value || "Unknown" }))
            )}
            {renderFilter(
              "client",
              "Workspace",
              clientOptions.map((value) => ({ value: value as string, label: clientLookup[value as string] || (value as string) }))
            )}
            {renderFilter(
              "campaign",
              "Campaign",
              campaignOptions.map((value) => ({ value: value as string, label: (value as string) || "Unknown" }))
            )}
          </div>
        </div>

        {isLoading ? (
          <div className="divide-y divide-border">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-3">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-12" />
                <Skeleton className="ml-auto h-8 w-20 rounded-md" />
              </div>
            ))}
          </div>
        ) : isError ? (
          <div className="p-4">
            <ErrorState
              title="Failed to load workflows"
              message="Could not fetch workflow runs. Check your connection and try again."
              onRetry={() => refetch()}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table variant="ghost">
              <TableHeader>
                <TableRow>
                  <TableHeadCell>Kind</TableHeadCell>
                  <TableHeadCell>Status</TableHeadCell>
                  <TableHeadCell>Workspace</TableHeadCell>
                  <TableHeadCell>Campaign</TableHeadCell>
                  <TableHeadCell>Started</TableHeadCell>
                  <TableHeadCell>Duration</TableHeadCell>
                  <TableHeadCell className="text-right">Actions</TableHeadCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredWorkflows.map((wf) => {
                  const clientName = wf.client_id ? clientLookup[wf.client_id] || wf.client_id : "—";
                  return (
                    <TableRow key={wf.id} hover>
                      <TableCell className="font-semibold text-content">{formatKind(wf.kind)}</TableCell>
                      <TableCell>
                        <StatusBadge status={wf.status} />
                      </TableCell>
                      <TableCell>{clientName}</TableCell>
                      <TableCell>
                        {wf.campaign_id ? (
                          <button
                            type="button"
                            className="font-mono text-xs text-accent hover:underline"
                            onClick={() => navigate(`/campaigns/${wf.campaign_id}`)}
                          >
                            {wf.campaign_id.slice(0, 8)}…
                          </button>
                        ) : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-content-muted">{formatDate(wf.started_at)}</TableCell>
                      <TableCell className="text-xs text-content-muted">{formatElapsed(wf.started_at, wf.finished_at)}</TableCell>
                      <TableCell className="text-right">
                        <Menu>
                          <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>
                            Actions
                          </MenuTrigger>
                          <MenuContent>
                            <MenuItem onClick={() => navigate(`/strategy/${wf.id}`)}>Open</MenuItem>
                            <MenuItem onClick={() => setStopId(wf.id)}>Stop</MenuItem>
                            <MenuItem onClick={() => navigator.clipboard.writeText(wf.id)}>Copy ID</MenuItem>
                          </MenuContent>
                        </Menu>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {!filteredWorkflows.length && (
                  <TableRow>
                    <TableCell className="px-3 py-4 text-sm text-content-muted" colSpan={7}>
                      No workflows match the current filters.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <DialogRoot open={Boolean(stopId)} onOpenChange={(open) => !open && setStopId(null)}>
        <DialogContent>
          <DialogTitle>Stop workflow?</DialogTitle>
          <DialogDescription>Send a stop signal to halt the workflow run.</DialogDescription>
          {stopId ? (
            <div className="mt-3">
              <Callout variant="neutral" size="sm" title="Workflow ID">
                <code className="font-mono">{stopId}</code>
              </Callout>
            </div>
          ) : null}
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" size="sm" onClick={() => setStopId(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleConfirmStop}
              disabled={!stopId || stopWorkflow.isPending}
            >
              {stopWorkflow.isPending ? "Stopping…" : "Stop workflow"}
            </Button>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
