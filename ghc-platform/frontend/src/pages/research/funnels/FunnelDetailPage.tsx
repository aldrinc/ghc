import { useFunnel, useUpdateFunnel, useCreateFunnelPage, usePublishFunnel, useDisableFunnel, useEnableFunnel, useDuplicateFunnel } from "@/api/funnels";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

export function FunnelDetailPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { funnelId } = useParams();
  const { data: funnel, isLoading } = useFunnel(funnelId);
  const updateFunnel = useUpdateFunnel();
  const createPage = useCreateFunnelPage();
  const publish = usePublishFunnel();
  const disable = useDisableFunnel();
  const enable = useEnableFunnel();
  const duplicate = useDuplicateFunnel();

  const [isPageModalOpen, setIsPageModalOpen] = useState(false);
  const [pageName, setPageName] = useState("");

  const pageOptions = useMemo(() => {
    return funnel?.pages?.map((p) => ({ label: `${p.name} (${p.slug})`, value: p.id })) || [];
  }, [funnel?.pages]);

  const statusTone = useMemo(() => {
    return (status: string) => {
      if (status === "published") return "success" as const;
      if (status === "disabled") return "danger" as const;
      return "neutral" as const;
    };
  }, []);

  const handleSetEntryPage = (entryPageId: string) => {
    if (!funnelId) return;
    updateFunnel.mutate({ funnelId, payload: { entryPageId: entryPageId || null } });
  };

  const handleCreatePage = async (e: FormEvent) => {
    e.preventDefault();
    if (!funnelId || !pageName.trim()) return;
    const resp = await createPage.mutateAsync({ funnelId, name: pageName.trim() });
    setIsPageModalOpen(false);
    setPageName("");
    const page = resp.page;
    navigate(`/research/funnels/${funnelId}/pages/${page.id}`);
  };

  const publicBase = funnel?.public_id ? `/f/${funnel.public_id}` : null;

  return (
    <div className="space-y-4">
      <PageHeader
        title={funnel?.name || "Funnel"}
        description={workspace ? `Workspace: ${workspace.name}` : "Funnel builder"}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setIsPageModalOpen(true)} disabled={!funnelId || !funnel}>
              New page
            </Button>
            <Button
              size="sm"
              onClick={() => funnelId && publish.mutate(funnelId)}
              disabled={!funnel?.canPublish || publish.isPending}
            >
              {publish.isPending ? "Publishing…" : "Publish"}
            </Button>
          </div>
        }
      />

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted">Loading…</div>
      ) : !funnel ? (
        <div className="ds-card ds-card--md text-sm text-content-muted">Funnel not found.</div>
      ) : (
        <>
          <div className="ds-card ds-card--md space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={statusTone(funnel.status)}>{funnel.status}</Badge>
                {funnel.campaign_id ? <Badge tone="neutral">Campaign-linked</Badge> : <Badge tone="neutral">No campaign</Badge>}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    if (!publicBase) return;
                    navigator.clipboard.writeText(window.location.origin + publicBase);
                  }}
                  disabled={!publicBase}
                >
                  Copy share link
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => funnelId && duplicate.mutate({ funnelId })}
                  disabled={!funnelId || duplicate.isPending}
                >
                  {duplicate.isPending ? "Duplicating…" : "Duplicate"}
                </Button>
                {funnel.status === "disabled" ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => funnelId && enable.mutate(funnelId)}
                    disabled={!funnelId || enable.isPending}
                  >
                    Enable
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => funnelId && disable.mutate(funnelId)}
                    disabled={!funnelId || disable.isPending}
                  >
                    Disable
                  </Button>
                )}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <div className="text-xs font-semibold text-content">Entry page</div>
                <Select
                  value={funnel.entry_page_id || ""}
                  onValueChange={handleSetEntryPage}
                  options={[{ label: "Select entry page", value: "" }, ...pageOptions]}
                  disabled={!funnel.pages.length || updateFunnel.isPending}
                />
              </div>
              <div className="space-y-1">
                <div className="text-xs font-semibold text-content">Public link</div>
                <div className="rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-xs text-content">
                  {publicBase ? publicBase : "—"}
                </div>
              </div>
            </div>
          </div>

          <div className="ds-card ds-card--md p-0 shadow-none">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-content">Pages</div>
                <div className="text-xs text-content-muted">{funnel.pages.length} pages</div>
              </div>
              <div className="text-xs text-content-muted">Approve each page, then publish</div>
            </div>
            <ul className="divide-y divide-border">
              {funnel.pages.map((page) => {
                const isApproved = Boolean(page.latestApprovedVersionId);
                return (
                  <li key={page.id} className="px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Link
                            to={`/research/funnels/${funnel.id}/pages/${page.id}`}
                            className="font-semibold text-content hover:underline"
                          >
                            {page.name}
                          </Link>
                          <Badge tone={isApproved ? "success" : "warning"}>{isApproved ? "approved" : "needs approval"}</Badge>
                        </div>
                        <div className="text-xs text-content-muted">
                          Slug: <span className="font-mono">{page.slug}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {publicBase ? (
                          <Link to={`${publicBase}/${page.slug}`} target="_blank" className="text-xs text-content-muted hover:underline">
                            Open public
                          </Link>
                        ) : null}
                        <Button variant="secondary" size="sm" asChild>
                          <Link to={`/research/funnels/${funnel.id}/pages/${page.id}`}>Edit</Link>
                        </Button>
                      </div>
                    </div>
                  </li>
                );
              })}
              {!funnel.pages.length ? (
                <li className="px-4 py-3 text-sm text-content-muted">No pages yet. Create one to start.</li>
              ) : null}
            </ul>
          </div>
        </>
      )}

      <DialogRoot open={isPageModalOpen} onOpenChange={setIsPageModalOpen}>
        <DialogContent>
          <DialogTitle>New page</DialogTitle>
          <DialogDescription>Add a page to this funnel. You can wire CTAs to other pages after saving.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreatePage}>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Page name</label>
              <Input
                placeholder="e.g. Landing page"
                value={pageName}
                onChange={(e) => setPageName(e.target.value)}
                required
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!pageName.trim() || createPage.isPending}>
                {createPage.isPending ? "Creating…" : "Create page"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}

