import { ArrowRight, Building2, FolderPlus, LayoutGrid, List, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useDeleteClient } from "@/api/clients";
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function WorkspacesPage() {
  const navigate = useNavigate();
  const {
    clients,
    selectWorkspace,
    isLoading,
    isError,
    error,
    workspace,
    clearWorkspace,
    refetch,
  } = useWorkspace();
  const deleteClient = useDeleteClient();
  const [view, setView] = useState<"grid" | "list">("grid");
  const [deleteTarget, setDeleteTarget] = useState<(typeof clients)[number] | null>(null);
  const [deleteStage, setDeleteStage] = useState<1 | 2>(1);
  const [confirmName, setConfirmName] = useState("");

  const sortedClients = useMemo(
    () => [...clients].sort((a, b) => a.name.localeCompare(b.name)),
    [clients]
  );
  const errorMessage = useMemo(() => {
    if (!error) return "Failed to load workspaces.";
    if (typeof error === "string") return error;
    if (typeof error === "object" && "message" in error) {
      const message = (error as { message?: unknown }).message;
      return typeof message === "string" ? message : "Failed to load workspaces.";
    }
    return "Failed to load workspaces.";
  }, [error]);

  const handleSelect = (clientId: string) => {
    selectWorkspace(clientId);
    navigate("/workspaces/overview");
  };

  const openDelete = (client: (typeof clients)[number]) => {
    setDeleteTarget(client);
    setDeleteStage(1);
    setConfirmName("");
  };

  const closeDelete = () => {
    setDeleteTarget(null);
    setDeleteStage(1);
    setConfirmName("");
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    const trimmed = confirmName.trim();
    if (trimmed !== deleteTarget.name) return;
    try {
      await deleteClient.mutateAsync({ clientId: deleteTarget.id, confirmName: trimmed });
      if (workspace?.id === deleteTarget.id) {
        clearWorkspace();
      }
      refetch();
      closeDelete();
    } catch {
      // errors surfaced via toast in mutation
    }
  };

  const isDeleting = deleteClient.isPending;
  const requiresName = deleteTarget?.name || "";
  const canDelete = confirmName.trim() === requiresName;

  return (
    <div className="min-h-screen bg-background text-foreground px-6 py-8">
      <div className="mx-auto w-full max-w-6xl space-y-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
              Workspaces
            </p>
            <h1 className="text-3xl font-bold leading-tight text-content">Choose a workspace</h1>
            <p className="max-w-2xl text-base leading-relaxed text-content-muted">
              Workspaces map directly to your idea or business. Pick one to view research, strategy, and angles,
              or start a new onboarding flow.
            </p>
          </div>

          <div className="inline-flex items-center gap-1 rounded-md border border-border bg-surface p-1 shadow-none">
            <button
              type="button"
              onClick={() => setView("grid")}
              className={`inline-flex items-center gap-2 rounded-sm px-3 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-outline)] ${
                view === "grid"
                  ? "bg-surface-hover text-content shadow-inner"
                  : "text-content-muted hover:text-content"
              }`}
              aria-pressed={view === "grid"}
            >
              <LayoutGrid className="h-4 w-4" />
              Cards
            </button>
            <button
              type="button"
              onClick={() => setView("list")}
              className={`inline-flex items-center gap-2 rounded-sm px-3 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-outline)] ${
                view === "list"
                  ? "bg-surface-hover text-content shadow-inner"
                  : "text-content-muted hover:text-content"
              }`}
              aria-pressed={view === "list"}
            >
              <List className="h-4 w-4" />
              List
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="rounded-xl border border-border bg-surface p-6 text-center text-sm text-content-muted shadow-none">
            Loading workspaces…
          </div>
        ) : isError ? (
          <div className="rounded-xl border border-danger/40 bg-danger/5 p-6 text-center text-sm text-danger shadow-none">
            <div className="font-semibold">Workspace load failed</div>
            <div className="mt-2">{errorMessage}</div>
            <Button className="mt-4" variant="secondary" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        ) : !sortedClients.length ? (
          <div className="rounded-xl border border-dashed border-border bg-surface p-10 text-center shadow-none">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface-hover text-accent">
              <FolderPlus className="h-6 w-6" />
            </div>
            <h2 className="mt-4 text-xl font-semibold text-content">No workspaces yet</h2>
            <p className="mt-2 text-sm text-content-muted max-w-md mx-auto">
              Create a workspace to kick off onboarding, generate research, and produce strategy & angle plans.
            </p>
            <button
              onClick={() => navigate("/workspaces/new")}
              className="mt-6 inline-flex items-center gap-2 rounded-md bg-[color:var(--accent)] px-4 py-2 text-sm font-semibold text-[color:var(--accent-contrast)] shadow-sm transition hover:bg-[color:var(--accent-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-outline)]"
            >
              Start onboarding
            </button>
          </div>
        ) : view === "grid" ? (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            <button
              onClick={() => navigate("/workspaces/new")}
              className="group flex h-56 flex-col justify-between rounded-xl border border-dashed border-border bg-surface p-6 text-left transition hover:border-border-strong hover:bg-surface-hover"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface-hover text-content-muted transition group-hover:text-accent">
                <FolderPlus className="h-6 w-6" />
              </div>
              <div>
                <span className="font-semibold text-content">New workspace</span>
                <span className="mt-1 block text-sm text-content-muted">Launch onboarding flow</span>
              </div>
            </button>

            {sortedClients.map((client) => (
              <div
                key={client.id}
                onClick={() => handleSelect(client.id)}
                className="group relative flex h-56 cursor-pointer flex-col justify-between rounded-xl border border-border bg-surface p-6 shadow-none transition hover:-translate-y-1 hover:border-border-strong hover:shadow-md"
              >
                <div>
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface-hover text-lg font-semibold text-content">
                      {client.name.charAt(0)}
                    </div>
                    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-hover px-2.5 py-1 text-xs font-semibold text-success">
                      <span className="h-1.5 w-1.5 rounded-full bg-success" />
                      Active
                    </span>
                  </div>
                  <div className="absolute right-4 top-4">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        openDelete(client);
                      }}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface-hover text-content-muted transition hover:text-danger"
                      aria-label={`Delete ${client.name} workspace`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <h3 className="text-xl font-bold leading-tight text-content transition-colors group-hover:text-accent">
                    {client.name}
                  </h3>
                  <p className="mt-1 text-sm font-medium text-content-muted">
                    {client.industry || "Industry not set"}
                  </p>
                </div>

                <div className="flex items-center justify-between border-t border-border pt-4 text-xs font-medium text-content-muted">
                  <span className="inline-flex items-center gap-1">
                    <Building2 className="h-3.5 w-3.5" />
                    {client.id.slice(0, 6)}…
                  </span>
                  <div className="flex items-center gap-1 text-accent opacity-0 transition-all duration-200 group-hover:translate-x-1 group-hover:opacity-100">
                    Open <ArrowRight className="h-3.5 w-3.5" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <button
              onClick={() => navigate("/workspaces/new")}
              className="group flex w-full items-center justify-between rounded-lg border border-dashed border-border bg-surface px-4 py-3 text-left transition hover:border-border-strong hover:bg-surface-hover"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-md border border-border bg-surface-hover text-content-muted transition group-hover:text-accent">
                  <FolderPlus className="h-5 w-5" />
                </div>
                <div>
                  <div className="font-semibold text-content">New workspace</div>
                  <div className="text-sm text-content-muted">Launch onboarding flow</div>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-content-muted transition group-hover:translate-x-1 group-hover:text-accent" />
            </button>

            {sortedClients.map((client) => (
              <div
                key={client.id}
                onClick={() => handleSelect(client.id)}
                className="group flex w-full cursor-pointer items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 shadow-none transition hover:-translate-y-0.5 hover:border-border-strong hover:bg-surface-hover hover:shadow-md"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md border border-border bg-surface-hover text-base font-semibold text-content">
                    {client.name.charAt(0)}
                  </div>
                  <div>
                    <div className="text-base font-semibold text-content group-hover:text-accent">
                      {client.name}
                    </div>
                    <div className="text-sm text-content-muted">
                      {client.industry || "Industry not set"}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs font-medium text-content-muted">
                  <span className="inline-flex items-center gap-1">
                    <Building2 className="h-3.5 w-3.5" />
                    {client.id.slice(0, 6)}…
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-hover px-2.5 py-1 text-[11px] font-semibold text-success">
                    <span className="h-1.5 w-1.5 rounded-full bg-success" />
                    Active
                  </span>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      openDelete(client);
                    }}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface-hover text-content-muted transition hover:text-danger"
                    aria-label={`Delete ${client.name} workspace`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                  <ArrowRight className="h-3.5 w-3.5 text-content-muted transition group-hover:translate-x-1 group-hover:text-accent" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <AlertDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) closeDelete();
        }}
      >
        <AlertDialogContent>
          <AlertDialogTitle>Delete workspace</AlertDialogTitle>
          <AlertDialogDescription>
            {deleteStage === 1
              ? "This action permanently deletes the workspace and all associated data. This cannot be undone."
              : "Type the workspace name to confirm deletion."}
          </AlertDialogDescription>

          {deleteStage === 2 ? (
            <div className="mt-4 space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.08em] text-content-muted">
                Workspace name
              </label>
              <Input
                value={confirmName}
                onChange={(event) => setConfirmName(event.target.value)}
                placeholder={requiresName}
              />
            </div>
          ) : null}

          <div className="mt-6 flex items-center justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={closeDelete} disabled={isDeleting}>
              Cancel
            </Button>
            {deleteStage === 1 ? (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setDeleteStage(2)}
                disabled={isDeleting}
              >
                Continue
              </Button>
            ) : (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDelete}
                disabled={isDeleting || !canDelete}
              >
                {isDeleting ? "Deleting…" : "Delete workspace"}
              </Button>
            )}
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
