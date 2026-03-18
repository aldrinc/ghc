import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { useDeleteFunnel } from "@/api/funnels";
import { useCampaignContext } from "@/contexts/CampaignContext";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const funnelToneMap: Record<string, "neutral" | "accent" | "success" | "danger"> = {
  draft: "neutral",
  published: "success",
  disabled: "danger",
  archived: "neutral",
};

export function CampaignFunnelsTab() {
  const navigate = useNavigate();
  const deleteFunnel = useDeleteFunnel();
  const {
    funnels,
    funnelsLoading,
    campaignLaunches,
    launchByFunnelId,
    campaignWorkflows,
  } = useCampaignContext();

  // ---- Local state --------------------------------------------------------
  const [selectedUmsIterationFilter, setSelectedUmsIterationFilter] = useState<string>("all");
  const [publishedDeleteTarget, setPublishedDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [deletePendingFunnelId, setDeletePendingFunnelId] = useState<string | null>(null);

  // ---- Derived state ------------------------------------------------------
  const isFunnelGenerationActive = Boolean(
    campaignWorkflows.find((wf) => wf.kind === "campaign_funnel_generation" && wf.status === "running"),
  );

  const umsIterationOptions = useMemo(() => {
    const seen = new Set<string>();
    const rows: Array<{ id: string; label: string }> = [];
    campaignLaunches.forEach((row) => {
      const id = row.selected_ums_id || "primary";
      if (seen.has(id)) return;
      seen.add(id);
      rows.push({
        id,
        label: id === "primary" ? "Primary launch" : id,
      });
    });
    return rows;
  }, [campaignLaunches]);

  const filteredFunnels = useMemo(() => {
    if (selectedUmsIterationFilter === "all") return funnels;
    return funnels.filter((funnel) => {
      const launchRow = launchByFunnelId.get(funnel.id);
      const umsId = launchRow?.selected_ums_id || "primary";
      return umsId === selectedUmsIterationFilter;
    });
  }, [launchByFunnelId, funnels, selectedUmsIterationFilter]);

  useEffect(() => {
    if (selectedUmsIterationFilter === "all") return;
    if (umsIterationOptions.some((option) => option.id === selectedUmsIterationFilter)) return;
    setSelectedUmsIterationFilter("all");
  }, [selectedUmsIterationFilter, umsIterationOptions]);

  // ---- Delete handlers ----------------------------------------------------
  const performFunnelDelete = async (funnelId: string) => {
    setDeletePendingFunnelId(funnelId);
    try {
      await deleteFunnel.mutateAsync({ funnelId });
    } finally {
      setDeletePendingFunnelId((current) => (current === funnelId ? null : current));
    }
  };

  const requestFunnelDelete = async (funnel: { id: string; name: string; status: string }) => {
    if (funnel.status === "published") {
      setPublishedDeleteTarget({ id: funnel.id, name: funnel.name });
      return;
    }
    try {
      await performFunnelDelete(funnel.id);
    } catch {
      // Mutation surfaces errors through toast.
    }
  };

  const confirmPublishedFunnelDelete = async () => {
    if (!publishedDeleteTarget) return;
    try {
      await performFunnelDelete(publishedDeleteTarget.id);
      setPublishedDeleteTarget(null);
    } catch {
      // Mutation surfaces errors through toast.
    }
  };

  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-base font-semibold text-content">Funnels</div>
          <div className="text-sm text-content-muted">
            Funnels are managed in the funnels workspace and can be edited anytime.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-content-muted">
            UMS filter
            <select
              className="ml-2 rounded-md border border-border bg-surface px-2 py-1 text-xs text-content"
              value={selectedUmsIterationFilter}
              onChange={(event) => setSelectedUmsIterationFilter(event.target.value)}
            >
              <option value="all">All groups</option>
              {umsIterationOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <Button variant="secondary" size="sm" onClick={() => navigate("/research/funnels")}>
            View all funnels
          </Button>
        </div>
      </div>
      <div className="mt-2 text-xs text-content-muted">
        Showing {filteredFunnels.length} of {funnels.length} funnels
        {selectedUmsIterationFilter !== "all" ? ` for UMS group '${selectedUmsIterationFilter}'.` : "."}
      </div>
      <div className="mt-4">
        {funnelsLoading ? (
          <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
            Loading funnels…
          </div>
        ) : filteredFunnels.length ? (
          <div className="border border-border bg-transparent">
            <div className="overflow-x-auto">
              <Table variant="ghost">
                <TableHeader>
                  <TableRow>
                    <TableHeadCell>Name</TableHeadCell>
                    <TableHeadCell>Angle / UMS</TableHeadCell>
                    <TableHeadCell>Status</TableHeadCell>
                    <TableHeadCell>Updated</TableHeadCell>
                    <TableHeadCell />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredFunnels.map((funnel) => {
                    const launchRow = launchByFunnelId.get(funnel.id);
                    return (
                      <TableRow key={funnel.id}>
                        <TableCell>
                          <Link
                            to={`/research/funnels/${funnel.id}`}
                            className="font-semibold text-content hover:underline"
                          >
                            {funnel.name}
                          </Link>
                          {funnel.description ? (
                            <div className="mt-1 text-sm text-content-muted">{funnel.description as string}</div>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          {launchRow ? (
                            <div className="text-xs text-content-muted">
                              <div>angle: {launchRow.angle_id}</div>
                              <div>ums: {launchRow.selected_ums_id || "primary"}</div>
                              <div>type: {launchRow.launch_type}</div>
                            </div>
                          ) : (
                            <span className="text-xs text-content-muted">No Strategy V2 launch row</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge tone={funnelToneMap[funnel.status] || "neutral"}>{funnel.status}</Badge>
                        </TableCell>
                        <TableCell className="text-sm text-content-muted">{formatDate(funnel.updated_at)}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button variant="secondary" size="xs" onClick={() => navigate(`/research/funnels/${funnel.id}`)}>
                              Open
                            </Button>
                            <Button
                              variant="destructive"
                              size="xs"
                              onClick={() => void requestFunnelDelete(funnel)}
                              disabled={deleteFunnel.isPending}
                            >
                              {deletePendingFunnelId === funnel.id ? "Deleting…" : "Delete"}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : selectedUmsIterationFilter !== "all" ? (
          <div className="border border-border bg-transparent px-4 py-3 text-base">
            No funnels matched UMS group <span className="font-mono">{selectedUmsIterationFilter}</span>.
          </div>
        ) : isFunnelGenerationActive ? (
          <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
            Creating funnels… This can take a few minutes. We'll attach the pre-sales + sales pages to this campaign
            when ready.
          </div>
        ) : (
          <div className="border border-border bg-transparent px-4 py-3 text-base">
            No funnels connected to this campaign yet.
          </div>
        )}
      </div>

      <AlertDialog
        open={Boolean(publishedDeleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleteFunnel.isPending) setPublishedDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogTitle>Delete published funnel?</AlertDialogTitle>
          <AlertDialogDescription>
            This funnel is currently published. Deleting it will remove the funnel and all of its pages.
          </AlertDialogDescription>
          {publishedDeleteTarget ? (
            <div className="mt-3 rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
              <span className="font-semibold text-content">{publishedDeleteTarget.name}</span>
            </div>
          ) : null}
          <div className="mt-6 flex items-center justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPublishedDeleteTarget(null)}
              disabled={deleteFunnel.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void confirmPublishedFunnelDelete()}
              disabled={deleteFunnel.isPending}
            >
              {deletePendingFunnelId === publishedDeleteTarget?.id ? "Deleting…" : "Delete funnel"}
            </Button>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
