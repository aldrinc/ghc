import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { useApiClient, type ApiError } from "@/api/client";
import { useProducts } from "@/api/products";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { Campaign } from "@/types/common";

const CHANNEL_OPTIONS = [{ value: "facebook", label: "Facebook Ads" }];
const ASSET_BRIEF_OPTIONS = [
  { value: "image", label: "Image" },
  { value: "video", label: "Video" },
];
const DEFAULT_CHANNELS = ["facebook"];
const DEFAULT_ASSET_BRIEF_TYPES = ["image"];

export function CampaignsPage() {
  const navigate = useNavigate();
  const { request } = useApiClient();
  const { workspace, clients, isLoading: isLoadingClients } = useWorkspace();
  const { product, products: workspaceProducts } = useProductContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [clientId, setClientId] = useState("");
  const [modalProductId, setModalProductId] = useState("");
  const [name, setName] = useState("");
  const [channels, setChannels] = useState<string[]>(DEFAULT_CHANNELS);
  const [assetBriefTypes, setAssetBriefTypes] = useState<string[]>(DEFAULT_ASSET_BRIEF_TYPES);
  const [banner, setBanner] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { data: modalProducts = [], isLoading: isLoadingModalProducts } = useProducts(clientId || undefined);

  const clientLookup = useMemo(() => {
    const map: Record<string, string> = {};
    clients.forEach((client) => {
      map[client.id] = client.name;
    });
    return map;
  }, [clients]);

  const productLookup = useMemo(() => {
    const map: Record<string, string> = {};
    workspaceProducts.forEach((item) => {
      map[item.id] = item.name;
    });
    return map;
  }, [workspaceProducts]);

  const refresh = useCallback(() => {
    if (workspace?.id && !product?.id) {
      setCampaigns([]);
      setIsLoading(false);
      return;
    }
    const params = new URLSearchParams();
    if (workspace?.id) params.set("client_id", workspace.id);
    if (product?.id) params.set("product_id", product.id);
    const query = params.toString() ? `?${params.toString()}` : "";
    setIsLoading(true);
    request<Campaign[]>(`/campaigns${query}`)
      .then(setCampaigns)
      .catch(() => setCampaigns([]))
      .finally(() => setIsLoading(false));
  }, [request, workspace?.id, product?.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!isModalOpen) return;
    setChannels(DEFAULT_CHANNELS);
    setAssetBriefTypes(DEFAULT_ASSET_BRIEF_TYPES);
    setModalProductId("");
  }, [isModalOpen]);

  useEffect(() => {
    if (!clientId) {
      setModalProductId("");
    }
  }, [clientId]);

  const resolvedClientId = workspace?.id || clientId;
  const resolvedProductId = workspace?.id ? product?.id : modalProductId;

  const getErrorMessage = (err: unknown) => {
    if (typeof err === "string") return err;
    if (err && typeof err === "object" && "message" in err) return (err as ApiError).message || "Request failed";
    return "Request failed";
  };

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!resolvedClientId || !name.trim()) return;
    if (!resolvedProductId) {
      setBanner({ tone: "error", text: "Select a product before creating a campaign." });
      return;
    }
    if (!channels.length) {
      setBanner({ tone: "error", text: "Select at least one channel to create a campaign." });
      return;
    }
    if (!assetBriefTypes.length) {
      setBanner({ tone: "error", text: "Select at least one creative brief type to create a campaign." });
      return;
    }
    setIsSubmitting(true);
    setBanner(null);
    try {
      await request<Campaign>("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          client_id: resolvedClientId,
          product_id: resolvedProductId,
          name: name.trim(),
          channels,
          asset_brief_types: assetBriefTypes,
          start_planning: true,
        }),
      });
      setBanner({ tone: "success", text: "Campaign created and planning started." });
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

  return (
    <div className="space-y-4">
      <PageHeader
        title="Campaigns"
        description={
          workspace
            ? product?.title
              ? `Viewing campaigns for ${workspace.name} · ${product.title}.`
              : `Select a product to view campaigns for ${workspace.name}.`
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

      {workspace && !product?.id && (
        <div className="ds-card ds-card--md text-sm text-content-muted">
          Select a product from the header to view or create campaigns in this workspace.
        </div>
      )}

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
                ? `${campaigns.length} for ${workspace.name}${product?.title ? ` · ${product.title}` : ""}`
                : `${campaigns.length} across all workspaces`}
            </div>
          </div>
          <div className="text-xs text-content-muted">
            Scope: {workspace ? `${workspace.name}${product?.title ? ` · ${product.title}` : ""}` : "All workspaces"}
          </div>
        </div>
        {isLoading ? (
          <div className="p-4 text-sm text-content-muted">Loading campaigns…</div>
        ) : (
          <ul className="divide-y divide-border">
            {campaigns.map((c) => (
              <li
                key={c.id}
                className="group cursor-pointer px-4 py-3 transition hover:bg-surface-hover"
                onClick={() => navigate(`/campaigns/${c.id}`)}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="font-semibold text-content">{c.name}</div>
                    <div className="flex items-center gap-2 text-xs text-content-muted">
                      <span>{clientLookup[c.client_id] || c.client_id}</span>
                      {c.product_id ? <span>· {productLookup[c.product_id] || c.product_id}</span> : null}
                      <Badge tone="neutral">Campaign</Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        navigate(`/campaigns/${c.id}`);
                      }}
                    >
                      Open
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
          <DialogDescription>
            Campaigns are created inside a workspace. We'll kick off planning after creation.
          </DialogDescription>
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

            {workspace ? (
              <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                <div className="text-xs font-semibold uppercase text-content-muted">Product</div>
                <div className={product?.title ? "font-semibold text-content" : "text-content-muted"}>
                  {product?.title || "Select a product in the header"}
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Product</label>
                <Select
                  value={modalProductId}
                  onValueChange={setModalProductId}
                  options={
                    clientId
                      ? modalProducts.length
                        ? [
                            { label: "Select product", value: "" },
                            ...modalProducts.map((item) => ({ label: item.title, value: item.id })),
                          ]
                        : [{ label: isLoadingModalProducts ? "Loading products…" : "No products available", value: "" }]
                      : [{ label: "Select a workspace first", value: "" }]
                  }
                  disabled={!clientId || isLoadingModalProducts || modalProducts.length === 0}
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

            <div className="space-y-2">
              <label className="text-xs font-semibold text-content">Channels</label>
              <div className="flex flex-wrap gap-3">
                {CHANNEL_OPTIONS.map((option) => (
                  <label key={option.value} className="flex items-center gap-2 text-sm text-content">
                    <input
                      type="checkbox"
                      className={cn(
                        "h-4 w-4 rounded border border-border bg-surface text-accent",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                      )}
                      checked={channels.includes(option.value)}
                      onChange={() => {
                        setChannels((prev) =>
                          prev.includes(option.value)
                            ? prev.filter((item) => item !== option.value)
                            : [...prev, option.value]
                        );
                      }}
                    />
                    <span>{option.label}</span>
                  </label>
                ))}
              </div>
              {!channels.length ? (
                <div className="text-xs text-danger">Select at least one channel.</div>
              ) : null}
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-content">Creative brief types</label>
              <div className="flex flex-wrap gap-3">
                {ASSET_BRIEF_OPTIONS.map((option) => (
                  <label key={option.value} className="flex items-center gap-2 text-sm text-content">
                    <input
                      type="checkbox"
                      className={cn(
                        "h-4 w-4 rounded border border-border bg-surface text-accent",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                      )}
                      checked={assetBriefTypes.includes(option.value)}
                      onChange={() => {
                        setAssetBriefTypes((prev) =>
                          prev.includes(option.value)
                            ? prev.filter((item) => item !== option.value)
                            : [...prev, option.value]
                        );
                      }}
                    />
                    <span>{option.label}</span>
                  </label>
                ))}
              </div>
              {!assetBriefTypes.length ? (
                <div className="text-xs text-danger">Select at least one creative brief type.</div>
              ) : null}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button
                type="submit"
                disabled={
                  isSubmitting ||
                  !resolvedClientId ||
                  !resolvedProductId ||
                  !name.trim() ||
                  channels.length === 0 ||
                  assetBriefTypes.length === 0
                }
              >
                {isSubmitting ? "Creating…" : "Create campaign"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
