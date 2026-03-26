import { PageHeader } from "@/components/layout/PageHeader";
import { useFunnels, useCreateFunnel, useDeleteFunnel } from "@/api/funnels";
import { useProduct } from "@/api/products";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspaceSiteFunnels } from "@/api/siteFunnels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { DialogClose, DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { shortUuidRouteToken } from "@/funnels/runtimeRouting";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EmptyState } from "@/components/layout/EmptyState";
import { InlineWorkspacePicker } from "@/components/layout/InlineWorkspacePicker";
import { Globe, Funnel as FunnelIcon } from "lucide-react";

export function FunnelsPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const clientId = workspace?.id;
  const { data: productDetail } = useProduct(product?.id);
  const { data: legacyFunnels = [], isLoading: legacyLoading } = useFunnels({ clientId, productId: product?.id });
  const { data: siteFunnels = [], isLoading: siteFunnelsLoading } = useWorkspaceSiteFunnels();
  const createFunnel = useCreateFunnel();
  const deleteFunnel = useDeleteFunnel();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedOfferId, setSelectedOfferId] = useState("");
  const [publishedDeleteTarget, setPublishedDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [deletePendingId, setDeletePendingId] = useState<string | null>(null);

  useEffect(() => {
    if (!isModalOpen) return;
    if (!productDetail?.offers?.length) {
      setSelectedOfferId("");
      return;
    }
    setSelectedOfferId((current) => {
      if (current && productDetail.offers.some((offer) => offer.id === current)) return current;
      return productDetail.offers[0].id;
    });
  }, [isModalOpen, productDetail?.offers]);

  const canCreate = Boolean(clientId && product?.id && name.trim());
  const productRouteSlug = shortUuidRouteToken(productDetail?.id || product?.id || "");

  const statusTone = useMemo(() => {
    return (status: string) => {
      if (status === "published" || status === "active") return "success" as const;
      if (status === "disabled" || status === "archived") return "danger" as const;
      if (status === "draft") return "warning" as const;
      return "neutral" as const;
    };
  }, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!clientId || !product?.id || !name.trim()) return;
    const funnel = await createFunnel.mutateAsync({
      clientId,
      productId: product.id,
      selectedOfferId: selectedOfferId || undefined,
      name: name.trim(),
      description: description.trim() || undefined,
    });
    setIsModalOpen(false);
    setName("");
    setDescription("");
    navigate(`/research/funnels/${funnel.id}`);
  };

  const performDelete = async (funnelId: string) => {
    setDeletePendingId(funnelId);
    try {
      await deleteFunnel.mutateAsync({ funnelId });
    } finally {
      setDeletePendingId((current) => (current === funnelId ? null : current));
    }
  };

  const requestDelete = async (funnel: { id: string; name: string; status: string }) => {
    if (funnel.status === "published") {
      setPublishedDeleteTarget({ id: funnel.id, name: funnel.name });
      return;
    }
    try {
      await performDelete(funnel.id);
    } catch {
      // Mutation surfaces errors through toast.
    }
  };

  const confirmPublishedDelete = async () => {
    if (!publishedDeleteTarget) return;
    try {
      await performDelete(publishedDeleteTarget.id);
      setPublishedDeleteTarget(null);
    } catch {
      // Mutation surfaces errors through toast.
    }
  };

  const isLoading = legacyLoading || siteFunnelsLoading;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Funnels"
        description={
          workspace
            ? "Cross-site funnel index and marketing funnels workspace."
            : "Select a workspace to view and manage funnels."
        }
        actions={
          <Button onClick={() => setIsModalOpen(true)} size="sm" disabled={!workspace || !product?.id}>
            New funnel
          </Button>
        }
      />

      {!workspace ? (
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to start building funnels."
          actions={<InlineWorkspacePicker />}
        />
      ) : (
        <div className="space-y-6">
          {/* Site-scoped Funnels Section */}
          <div className="ds-card ds-card--md p-0 shadow-none">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-content flex items-center gap-2">
                  <Globe className="h-4 w-4" />
                  Site Funnels
                </div>
                <div className="text-xs text-content-muted">
                  Funnels attached to sites in {workspace.name}
                </div>
              </div>
              <Badge tone="neutral">{siteFunnels.length}</Badge>
            </div>
            {siteFunnelsLoading ? (
              <div className="p-4 text-sm text-content-muted">Loading site funnels…</div>
            ) : siteFunnels.length === 0 ? (
              <div className="p-4 text-sm text-content-muted">
                No site funnels yet. Create funnels from within a site's detail page.
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {siteFunnels.map((funnel) => (
                  <li key={funnel.id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Link 
                            to={`/workspaces/sites/${funnel.siteId}/funnels/${funnel.id}`} 
                            className="font-semibold text-content hover:underline"
                          >
                            {funnel.name}
                          </Link>
                          <Badge tone={statusTone(funnel.status)} className="text-xs">{funnel.status}</Badge>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-content-muted">
                          <span>Site: {funnel.siteName || funnel.siteId.slice(0, 8)}...</span>
                          {funnel.productId && <span>• Product: {funnel.productId.slice(0, 8)}...</span>}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="secondary" 
                          size="xs" 
                          onClick={() => navigate(`/workspaces/sites/${funnel.siteId}/funnels/${funnel.id}`)}
                        >
                          Open
                        </Button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Legacy Funnels Section */}
          <div className="ds-card ds-card--md p-0 shadow-none">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-content flex items-center gap-2">
                  <FunnelIcon className="h-4 w-4" />
                  Legacy Funnels
                </div>
                <div className="text-xs text-content-muted">
                  {product?.title 
                    ? `Funnels for ${workspace.name} · ${product.title}`
                    : `Product-scoped funnels in ${workspace.name}`
                  }
                </div>
              </div>
              <div className="text-xs text-content-muted">Unlisted links (v1)</div>
            </div>
            {!product ? (
              <div className="p-4 text-sm text-content-muted">
                Select a product to view legacy funnels.
              </div>
            ) : isLoading ? (
              <div className="p-4 text-sm text-content-muted">Loading funnels…</div>
            ) : (
              <ul className="divide-y divide-border">
                {legacyFunnels.map((funnel) => (
                  <li key={funnel.id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-1">
                        <Link to={`/research/funnels/${funnel.id}`} className="font-semibold text-content hover:underline">
                          {funnel.name}
                        </Link>
                        <div className="flex items-center gap-2 text-xs text-content-muted">
                          <Badge tone={statusTone(funnel.status)}>{funnel.status}</Badge>
                          {funnel.campaign_id ? <span>Campaign-linked</span> : <span>No campaign</span>}
                        </div>
                      </div>
                      <div className="text-xs text-content-muted">
                        <div>
                          Public:{" "}
                          <span className="font-mono">
                            {productRouteSlug ? `/f/${productRouteSlug}/${shortUuidRouteToken(funnel.id)}` : "Route unavailable"}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center justify-end gap-2">
                          <Button variant="secondary" size="xs" onClick={() => navigate(`/research/funnels/${funnel.id}`)}>
                            Open
                          </Button>
                          <Button
                            variant="destructive"
                            size="xs"
                            onClick={() => void requestDelete(funnel)}
                            disabled={deleteFunnel.isPending}
                          >
                            {deletePendingId === funnel.id ? "Deleting…" : "Delete"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
                {!legacyFunnels.length && (
                  <li className="px-4 py-3 text-sm text-content-muted">No legacy funnels.</li>
                )}
              </ul>
            )}
          </div>
        </div>
      )}

      <DialogRoot open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent>
          <DialogTitle>New funnel</DialogTitle>
          <DialogDescription>Create a funnel inside the selected workspace.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreate}>
            {workspace ? (
              <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                <div className="text-xs font-semibold uppercase text-content-muted">Workspace</div>
                <div className="font-semibold text-content">{workspace.name}</div>
              </div>
            ) : null}
            {workspace ? (
              <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                <div className="text-xs font-semibold uppercase text-content-muted">Product</div>
                <div className={product?.title ? "font-semibold text-content" : "text-content-muted"}>
                  {product?.title || "Select a product in the header"}
                </div>
              </div>
            ) : null}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Name</label>
              <Input placeholder="e.g. Lead magnet funnel" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Description (optional)</label>
              <Input placeholder="Short note" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Selected offer (optional)</label>
              <select
                className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm"
                value={selectedOfferId}
                onChange={(e) => setSelectedOfferId(e.target.value)}
                disabled={!productDetail?.offers?.length}
              >
                <option value="">{productDetail?.offers?.length ? "No selected offer" : "No offers available"}</option>
                {(productDetail?.offers || []).map((offer) => (
                  <option key={offer.id} value={offer.id}>
                    {offer.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!canCreate || createFunnel.isPending}>
                {createFunnel.isPending ? "Creating…" : "Create funnel"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>

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
              onClick={() => void confirmPublishedDelete()}
              disabled={deleteFunnel.isPending}
            >
              {deletePendingId === publishedDeleteTarget?.id ? "Deleting…" : "Delete funnel"}
            </Button>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
