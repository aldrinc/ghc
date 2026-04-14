import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorState } from "@/components/layout/ErrorState";
import { InlineWorkspacePicker } from "@/components/layout/InlineWorkspacePicker";
import { PageHeader } from "@/components/layout/PageHeader";
import { StrategySkillsWorkflowPanel } from "@/components/strategy/StrategySkillsWorkflowPanel";
import { Button, buttonClasses } from "@/components/ui/button";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Callout } from "@/components/ui/callout";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { useClients } from "@/api/clients";
import { useStopWorkflow, useWorkflows } from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";

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
  const workspaceId = workspace?.id;
  const productId = product?.id;
  const workflowsEnabled = Boolean(workspaceId && productId);
  const { data: workflows, isLoading, isError, refetch } = useWorkflows(
    workflowsEnabled && workspaceId && productId ? { clientId: workspaceId, productId } : undefined,
    { enabled: workflowsEnabled },
  );
  const { data: clients } = useClients();
  const [searchParams, setSearchParams] = useSearchParams();
  const [stopId, setStopId] = useState<string | null>(null);
  const stopWorkflow = useStopWorkflow();

  const statusFilter = searchParams.get("status") || "";
  const setStatusFilter = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value) {
      next.delete("status");
    } else {
      next.set("status", value);
    }
    setSearchParams(next, { replace: true });
  };

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

  const filteredWorkflows = useMemo(() => {
    const list = workflows || [];
    return list
      .filter((wf) => {
        if (product?.id && wf.product_id !== product.id) return false;
        if (statusFilter && wf.status !== statusFilter) return false;
        return true;
      })
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
  }, [workflows, statusFilter, product?.id]);

  const handleConfirmStop = () => {
    if (!stopId) return;
    stopWorkflow.mutate(stopId, {
      onSuccess: () => setStopId(null),
      onSettled: () => stopWorkflow.reset(),
    });
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Strategy" description="Select a workspace to get started." />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to view and manage your strategy workflow."
          actions={<InlineWorkspacePicker />}
        />
      </div>
    );
  }

  if (isLoadingProduct && !product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Strategy" description="Loading product strategy..." />
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading...</div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Strategy" description="Select a product to manage its strategy workflow." />
        <EmptyState
          title="No product selected"
          description="Choose a product from the header to manage its strategy workflow."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Strategy"
        description={
          product?.title
            ? `Manage the strategy workflow for ${product.title}.`
            : "Manage your product strategy step by step."
        }
      />

      <StrategySkillsWorkflowPanel productId={product.id} productTitle={product.title} />

      {/* Workflow Run History - collapsible secondary section */}
      <details className="ds-card ds-card--md p-0 shadow-none">
        <summary className="flex cursor-pointer items-center justify-between px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-content">Workflow Run History</div>
            <div className="text-xs text-content-muted">
              {filteredWorkflows.length} runs · {workflows?.length || 0} total
            </div>
          </div>
        </summary>

        <div className="border-t border-border">
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <div className="flex flex-col gap-1 text-xs text-content-muted">
              <span>Status</span>
              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                options={[
                  { value: "", label: "All" },
                  ...statusOptions.map((value) => ({ value, label: value || "Unknown" })),
                ]}
              />
            </div>
            {statusFilter ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setStatusFilter("")}
              >
                Clear
              </Button>
            ) : null}
          </div>

          {isLoading ? (
            <div className="divide-y divide-border">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3">
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-5 w-16 rounded-full" />
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-12" />
                </div>
              ))}
            </div>
          ) : isError ? (
            <div className="p-4">
              <ErrorState
                title="Failed to load workflows"
                message="Could not fetch workflow runs."
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
                    <TableHeadCell>Started</TableHeadCell>
                    <TableHeadCell>Duration</TableHeadCell>
                    <TableHeadCell className="text-right">Actions</TableHeadCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredWorkflows.map((wf) => (
                    <TableRow key={wf.id} hover>
                      <TableCell className="font-semibold text-content">{formatKind(wf.kind)}</TableCell>
                      <TableCell>
                        <StatusBadge status={wf.status} />
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
                  ))}
                  {!filteredWorkflows.length && (
                    <TableRow>
                      <TableCell className="px-3 py-4 text-sm text-content-muted" colSpan={5}>
                        No workflows match the current filters.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </details>

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
              variant="destructive"
              size="sm"
              onClick={handleConfirmStop}
              disabled={!stopId || stopWorkflow.isPending}
            >
              {stopWorkflow.isPending ? "Stopping..." : "Stop workflow"}
            </Button>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
