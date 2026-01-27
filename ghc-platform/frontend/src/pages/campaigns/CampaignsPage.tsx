import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useApiClient, type ApiError } from "@/api/client";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Campaign } from "@/types/common";

export function CampaignsPage() {
  const { request } = useApiClient();
  const { workspace, clients, isLoading: isLoadingClients } = useWorkspace();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [clientId, setClientId] = useState("");
  const [name, setName] = useState("");
  const [banner, setBanner] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [planningId, setPlanningId] = useState<string | null>(null);

  const clientLookup = useMemo(() => {
    const map: Record<string, string> = {};
    clients.forEach((client) => {
      map[client.id] = client.name;
    });
    return map;
  }, [clients]);

  const refresh = useCallback(() => {
    const query = workspace?.id ? `?client_id=${encodeURIComponent(workspace.id)}` : "";
    setIsLoading(true);
    request<Campaign[]>(`/campaigns${query}`)
      .then(setCampaigns)
      .catch(() => setCampaigns([]))
      .finally(() => setIsLoading(false));
  }, [request, workspace?.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const resolvedClientId = workspace?.id || clientId;

  const getErrorMessage = (err: unknown) => {
    if (typeof err === "string") return err;
    if (err && typeof err === "object" && "message" in err) return (err as ApiError).message || "Request failed";
    return "Request failed";
  };

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!resolvedClientId || !name.trim()) return;
    setIsSubmitting(true);
    setBanner(null);
    try {
      await request("/campaigns", {
        method: "POST",
        body: JSON.stringify({ client_id: resolvedClientId, name: name.trim() }),
      });
      setBanner({ tone: "success", text: "Campaign created" });
      setName("");
      if (!workspace) setClientId("");
      setIsModalOpen(false);
      refresh();
    } catch (err) {
      setBanner({ tone: "error", text: `Failed to create campaign: ${getErrorMessage(err)}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePlan = async (campaignId: string) => {
    setBanner(null);
    setPlanningId(campaignId);
    try {
      await request(`/campaigns/${campaignId}/plan`, {
        method: "POST",
        body: JSON.stringify({ business_goal_id: "goal-" + Date.now() }),
      });
      setBanner({ tone: "success", text: "Campaign planning workflow started" });
    } catch (err) {
      setBanner({ tone: "error", text: `Cannot start planning: ${getErrorMessage(err)}` });
    }
    setPlanningId(null);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Campaigns"
        description={
          workspace
            ? `Viewing campaigns for ${workspace.name}. Start planning or create a new campaign for this workspace.`
            : "Manage campaigns across workspaces. Select a workspace to scope creation automatically."
        }
        actions={
          <Button onClick={() => setIsModalOpen(true)} size="sm">
            New campaign
          </Button>
        }
      />

      {banner ? (
        <div
          className={`rounded-md border px-3 py-2 text-sm ${
            banner.tone === "success"
              ? "border-success/50 bg-success/10 text-success"
              : "border-danger/50 bg-danger/10 text-danger"
          }`}
        >
          {banner.text}
        </div>
      ) : null}

      {!workspace && (
        <div className="ds-card ds-card--md text-sm text-content-muted">
          No workspace selected. Pick a workspace from the sidebar to create campaigns without choosing a client each
          time.
        </div>
      )}

      <div className="ds-card ds-card--md p-0 shadow-none">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-content">Campaigns</div>
            <div className="text-xs text-content-muted">
              {workspace
                ? `${campaigns.length} for ${workspace.name}`
                : `${campaigns.length} across all workspaces`}
            </div>
          </div>
          <div className="text-xs text-content-muted">
            Scope: {workspace ? workspace.name : "All workspaces"}
          </div>
        </div>
        {isLoading ? (
          <div className="p-4 text-sm text-content-muted">Loading campaigns…</div>
        ) : (
          <ul className="divide-y divide-border">
            {campaigns.map((c) => (
              <li key={c.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="font-semibold text-content">{c.name}</div>
                    <div className="flex items-center gap-2 text-xs text-content-muted">
                      <span>{clientLookup[c.client_id] || c.client_id}</span>
                      <Badge tone="neutral">Campaign</Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handlePlan(c.id)}
                      disabled={planningId === c.id}
                    >
                      {planningId === c.id ? "Starting…" : "Start planning"}
                    </Button>
                  </div>
                </div>
              </li>
            ))}
            {!campaigns.length && (
              <li className="px-4 py-3 text-sm text-content-muted">No campaigns yet.</li>
            )}
          </ul>
        )}
      </div>

      <DialogRoot open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent>
          <DialogTitle>New campaign</DialogTitle>
          <DialogDescription>Campaigns are created inside a workspace. Add details to start planning faster.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreate}>
            {workspace ? (
              <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                <div className="text-xs font-semibold uppercase text-content-muted">Workspace</div>
                <div className="font-semibold text-content">{workspace.name}</div>
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Workspace</label>
                <Select
                  value={clientId}
                  onValueChange={setClientId}
                  options={
                    clients.length
                      ? [{ label: "Select workspace", value: "" }, ...clients.map((c) => ({ label: c.name, value: c.id }))]
                      : [{ label: isLoadingClients ? "Loading workspaces…" : "No workspaces available", value: "" }]
                  }
                  disabled={isLoadingClients || clients.length === 0}
                />
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Campaign name</label>
              <Input
                placeholder="e.g. Q4 evergreen refresh"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={isSubmitting || !resolvedClientId || !name.trim()}>
                {isSubmitting ? "Creating…" : "Create campaign"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
