import { ArrowRight, Building2, FolderPlus, LayoutGrid, List, Trash2 } from "lucide-react";
import { type KeyboardEvent, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useDeleteClient } from "@/api/clients";
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

type WorkspaceClient = ReturnType<typeof useWorkspace>["clients"][number];

function workspaceInitial(client: WorkspaceClient) {
  return (client.name.trim().charAt(0) || "W").toUpperCase();
}

function workspaceIndustry(client: WorkspaceClient) {
  return client.industry?.trim() || "Industry not set";
}

function shortWorkspaceId(client: WorkspaceClient) {
  return `${client.id.slice(0, 8)}…`;
}

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

  const [searchQuery, setSearchQuery] = useState("");

  const sortedClients = useMemo(
    () => [...clients].sort((a, b) => a.name.localeCompare(b.name)),
    [clients]
  );

  const filteredClients = useMemo(() => {
    if (!searchQuery.trim()) return sortedClients;
    const q = searchQuery.toLowerCase();
    return sortedClients.filter(
      (c) => c.name.toLowerCase().includes(q) || (c.industry || "").toLowerCase().includes(q),
    );
  }, [sortedClients, searchQuery]);
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

  const handleCardKeyDown = (clientId: string) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleSelect(clientId);
    }
  };

  return (
    <div className="min-h-screen bg-background px-4 py-8 text-foreground sm:px-6">
      <div className="mx-auto w-full max-w-6xl space-y-8">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
              Workspaces
            </p>
            <h1 className="font-display text-3xl font-normal leading-tight text-content">Choose a workspace</h1>
            <p className="max-w-2xl text-base leading-relaxed text-content-muted">
              Workspaces map directly to your idea or business. Pick one to view research, strategy, and angles,
              or start a new onboarding flow.
            </p>
          </div>

          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search workspaces…"
              className="w-full text-sm sm:w-[230px]"
            />
            <div className="mos-segmented-control" role="group" aria-label="Workspace view">
              <button
                type="button"
                onClick={() => setView("grid")}
                className={`mos-segmented-option ${view === "grid" ? "is-selected" : ""}`}
                aria-pressed={view === "grid"}
              >
                <LayoutGrid className="h-4 w-4" />
                Cards
              </button>
              <button
                type="button"
                onClick={() => setView("list")}
                className={`mos-segmented-option ${view === "list" ? "is-selected" : ""}`}
                aria-pressed={view === "list"}
              >
                <List className="h-4 w-4" />
                List
              </button>
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="min-h-[188px] rounded-[14px] border-[1.5px] border-border bg-surface p-5">
                <div>
                  <div className="mb-5 flex items-center justify-between">
                    <Skeleton className="h-12 w-12 rounded-lg" />
                    <Skeleton className="h-6 w-16 rounded-full" />
                  </div>
                  <Skeleton className="h-6 w-3/4 rounded-md" />
                  <Skeleton className="mt-2 h-4 w-1/2 rounded-md" />
                </div>
                <div className="mt-6 rounded-[10px] bg-[color:var(--bg-soft)] p-3">
                  <Skeleton className="h-4 w-20 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-xl border border-danger/40 bg-danger/5 p-6 text-center text-sm text-danger shadow-none">
            <div className="font-semibold">Workspace load failed</div>
            <div className="mt-2">{errorMessage}</div>
            <Button className="mt-4" variant="secondary" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        ) : !filteredClients.length && !searchQuery.trim() ? (
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
        ) : !filteredClients.length ? (
          <div className="rounded-xl border border-border bg-surface p-6 text-center text-sm text-content-muted shadow-none">
            No workspaces match "{searchQuery}".
          </div>
        ) : view === "grid" ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {!searchQuery.trim() && (
            <button
              onClick={() => navigate("/workspaces/new")}
              className="group flex min-h-[188px] flex-col justify-between rounded-[14px] border-[1.5px] border-dashed border-border bg-surface p-5 text-left transition hover:border-solid hover:border-border-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-outline)]"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[12px] border border-border bg-[color:var(--bg-soft)] text-content-muted transition group-hover:border-border-strong group-hover:text-content">
                  <FolderPlus className="h-5 w-5" />
                </div>
                <div className="min-w-0 pt-1">
                  <span className="block text-base font-semibold text-content">New workspace</span>
                  <span className="mt-1 block text-sm leading-5 text-content-muted">Launch onboarding flow</span>
                </div>
              </div>
              <div className="mt-5 flex items-center justify-between rounded-[10px] bg-[color:var(--bg-soft)] px-3 py-2.5 text-sm font-semibold text-content">
                <span>Start setup</span>
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </div>
            </button>
            )}

            {filteredClients.map((client) => (
              <div
                key={client.id}
                role="button"
                tabIndex={0}
                onClick={() => handleSelect(client.id)}
                onKeyDown={handleCardKeyDown(client.id)}
                className="group relative flex min-h-[148px] cursor-pointer items-center gap-4 rounded-[14px] border-[1.5px] border-border bg-surface p-5 pr-16 shadow-none transition hover:border-border-strong active:scale-[0.99] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-outline)]"
              >
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    openDelete(client);
                  }}
                  className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-full border border-transparent text-content-muted opacity-0 transition-all group-hover:opacity-100 hover:border-border hover:bg-surface hover:text-danger focus-visible:opacity-100"
                  aria-label={`Delete ${client.name} workspace`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>

                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[12px] border border-border bg-[color:var(--bg-soft)] text-base font-semibold text-content transition group-hover:border-border-strong">
                  {workspaceInitial(client)}
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-xl font-bold leading-tight text-content transition-colors group-hover:text-accent">
                    {client.name}
                  </h3>
                  <p className="mt-1 truncate text-sm font-medium text-content-muted">
                    {workspaceIndustry(client)}
                  </p>
                  <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium text-content-muted">
                    <Building2 className="h-3.5 w-3.5" />
                    {shortWorkspaceId(client)}
                  </div>
                </div>

                <span className="absolute right-5 top-1/2 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-[color:var(--bg-soft)] text-content transition group-hover:translate-x-0.5 group-hover:bg-content group-hover:text-surface">
                  <ArrowRight className="h-4 w-4" />
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {!searchQuery.trim() && (
            <button
              onClick={() => navigate("/workspaces/new")}
              className="group flex w-full items-center justify-between rounded-[14px] border-[1.5px] border-dashed border-border bg-surface px-4 py-3 text-left transition hover:border-solid hover:border-border-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-outline)]"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-[10px] border border-border bg-[color:var(--bg-soft)] text-content-muted transition group-hover:text-content">
                  <FolderPlus className="h-5 w-5" />
                </div>
                <div>
                  <div className="font-semibold text-content">New workspace</div>
                  <div className="text-sm text-content-muted">Launch onboarding flow</div>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-content-muted transition group-hover:translate-x-1 group-hover:text-accent" />
            </button>
            )}

            {filteredClients.map((client) => (
              <div
                key={client.id}
                role="button"
                tabIndex={0}
                onClick={() => handleSelect(client.id)}
                onKeyDown={handleCardKeyDown(client.id)}
                className="group flex w-full cursor-pointer items-center justify-between rounded-[14px] border-[1.5px] border-border bg-surface px-4 py-3 shadow-none transition hover:border-border-strong active:scale-[0.99] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-outline)]"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border border-border bg-[color:var(--bg-soft)] text-base font-semibold text-content">
                    {workspaceInitial(client)}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-base font-semibold text-content group-hover:text-accent">
                      {client.name}
                    </div>
                    <div className="truncate text-sm text-content-muted">
                      {workspaceIndustry(client)}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs font-medium text-content-muted">
                  <span className="inline-flex items-center gap-1">
                    <Building2 className="h-3.5 w-3.5" />
                    {shortWorkspaceId(client)}
                  </span>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      openDelete(client);
                    }}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-transparent text-content-muted opacity-0 transition-all group-hover:opacity-100 hover:border-border hover:bg-surface-hover hover:text-danger focus-visible:opacity-100"
                    aria-label={`Delete ${client.name} workspace`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
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
