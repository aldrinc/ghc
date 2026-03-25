import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import {
  DialogRoot,
  DialogTrigger,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "@/components/ui/dialog";
import { FieldRoot, FieldLabel, FieldControl } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import {
  useClientGetHookdCredentials,
  useUpdateClientGetHookdCredentials,
  useClientGetHookdSyncFeeds,
  useCreateClientGetHookdSyncFeed,
  useUpdateClientGetHookdSyncFeed,
  useDeleteClientGetHookdSyncFeed,
} from "@/api/clients";
import type { GetHookdSyncFeed } from "@/types/common";

interface GetHookdSettingsProps {
  clientId: string;
}

export function GetHookdSettings({ clientId }: GetHookdSettingsProps) {
  const { data: credentials, isLoading: credentialsLoading } = useClientGetHookdCredentials(clientId);
  const { data: feeds, isLoading: feedsLoading } = useClientGetHookdSyncFeeds(clientId);
  const updateCredentials = useUpdateClientGetHookdCredentials(clientId);
  const createFeed = useCreateClientGetHookdSyncFeed(clientId);
  const updateFeed = useUpdateClientGetHookdSyncFeed(clientId);
  const deleteFeed = useDeleteClientGetHookdSyncFeed(clientId);

  const [tokenInput, setTokenInput] = useState("");
  const [isTokenDialogOpen, setIsTokenDialogOpen] = useState(false);
  const [editingFeed, setEditingFeed] = useState<GetHookdSyncFeed | null>(null);
  const [feedForm, setFeedForm] = useState({
    name: "",
    sourceUrl: "",
    webhookPath: "",
    isActive: true,
  });
  const [isFeedDialogOpen, setIsFeedDialogOpen] = useState(false);

  const handleSaveToken = () => {
    if (!tokenInput.trim()) return;
    updateCredentials.mutate({ token: tokenInput }, {
      onSuccess: () => {
        setTokenInput("");
        setIsTokenDialogOpen(false);
      },
    });
  };

  const handleCreateFeed = () => {
    if (!feedForm.name.trim() || !feedForm.sourceUrl.trim() || !feedForm.webhookPath.trim()) return;
    createFeed.mutate(feedForm, {
      onSuccess: () => {
        setFeedForm({ name: "", sourceUrl: "", webhookPath: "", isActive: true });
        setIsFeedDialogOpen(false);
      },
    });
  };

  const handleUpdateFeed = () => {
    if (!editingFeed) return;
    updateFeed.mutate(
      { feedId: editingFeed.id, payload: feedForm },
      {
        onSuccess: () => {
          setEditingFeed(null);
          setFeedForm({ name: "", sourceUrl: "", webhookPath: "", isActive: true });
          setIsFeedDialogOpen(false);
        },
      }
    );
  };

  const handleToggleFeed = (feed: GetHookdSyncFeed) => {
    updateFeed.mutate({ feedId: feed.id, payload: { isActive: !feed.isActive } });
  };

  const handleDeleteFeed = (feedId: string) => {
    if (confirm("Delete this sync feed? This action cannot be undone.")) {
      deleteFeed.mutate(feedId);
    }
  };

  const openCreateDialog = () => {
    setEditingFeed(null);
    setFeedForm({ name: "", sourceUrl: "", webhookPath: "", isActive: true });
    setIsFeedDialogOpen(true);
  };

  const openEditDialog = (feed: GetHookdSyncFeed) => {
    setEditingFeed(feed);
    setFeedForm({
      name: feed.name,
      sourceUrl: feed.sourceUrl,
      webhookPath: feed.webhookPath,
      isActive: feed.isActive,
    });
    setIsFeedDialogOpen(true);
  };

  const isLoading = credentialsLoading || feedsLoading;

  return (
    <div className="space-y-6">
      {/* Credentials Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-content">GetHookd Credentials</h3>
            <p className="text-xs text-content-muted">Configure API token for GetHookd sync</p>
          </div>
          <DialogRoot open={isTokenDialogOpen} onOpenChange={setIsTokenDialogOpen}>
            <DialogTrigger
              render={
                <Button variant="secondary" size="sm">
                  {credentials?.isConfigured ? "Update Token" : "Configure Token"}
                </Button>
              }
            />
            <DialogContent>
              <DialogTitle>{credentials?.isConfigured ? "Update GetHookd Token" : "Configure GetHookd Token"}</DialogTitle>
              <DialogDescription>
                Enter your GetHookd API token. This will be stored securely and used for syncing data.
              </DialogDescription>
              <div className="space-y-4 mt-4">
                <FieldRoot>
                  <FieldLabel>API Token</FieldLabel>
                  <FieldControl>
                    <Input
                      type="password"
                      placeholder="gh_..."
                      value={tokenInput}
                      onChange={(e) => setTokenInput(e.target.value)}
                    />
                  </FieldControl>
                </FieldRoot>
                <div className="flex justify-end gap-2">
                  <DialogClose
                    render={<Button variant="ghost" size="sm">Cancel</Button>}
                  />
                  <Button
                    size="sm"
                    onClick={handleSaveToken}
                    disabled={!tokenInput.trim() || updateCredentials.isPending}
                  >
                    {updateCredentials.isPending ? "Saving..." : "Save Token"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </DialogRoot>
        </div>

        <div className="flex items-center gap-3 text-sm">
          <span className="text-content-muted">Status:</span>
          {credentialsLoading ? (
            <span className="text-content-muted">Loading...</span>
          ) : credentials?.isConfigured ? (
            <Badge tone="success">Configured</Badge>
          ) : (
            <Badge tone="warning">Not Configured</Badge>
          )}
          {credentials?.updatedAt && (
            <span className="text-xs text-content-muted">
              Last updated: {new Date(credentials.updatedAt).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>

      {/* Sync Feeds Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-content">Sync Feeds</h3>
            <p className="text-xs text-content-muted">Manage data sync feeds from GetHookd</p>
          </div>
          <Button variant="secondary" size="sm" onClick={openCreateDialog}>
            Add Feed
          </Button>
        </div>

        <div className="overflow-hidden">
          <Table variant="ghost">
            <TableHeader>
              <TableRow>
                <TableHeadCell>Name</TableHeadCell>
                <TableHeadCell>Source URL</TableHeadCell>
                <TableHeadCell>Webhook Path</TableHeadCell>
                <TableHeadCell>Status</TableHeadCell>
                <TableHeadCell>Last Sync</TableHeadCell>
                <TableHeadCell className="text-right">Actions</TableHeadCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell className="px-3 py-3 text-sm text-content-muted" colSpan={6}>
                    Loading feeds...
                  </TableCell>
                </TableRow>
              ) : feeds?.length ? (
                feeds.map((feed) => (
                  <TableRow key={feed.id}>
                    <TableCell className="font-medium text-content">{feed.name}</TableCell>
                    <TableCell className="text-content-muted text-xs max-w-[200px] truncate">
                      {feed.sourceUrl}
                    </TableCell>
                    <TableCell className="text-content-muted text-xs font-mono">
                      {feed.webhookPath}
                    </TableCell>
                    <TableCell>
                      <button
                        onClick={() => handleToggleFeed(feed)}
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                          feed.isActive
                            ? "bg-success/10 text-success hover:bg-success/20"
                            : "bg-muted text-content-muted hover:bg-hover"
                        }`}
                      >
                        {feed.isActive ? "Active" : "Inactive"}
                      </button>
                    </TableCell>
                    <TableCell className="text-xs text-content-muted">
                      {feed.lastSyncAt
                        ? `${new Date(feed.lastSyncAt).toLocaleDateString()} ${feed.lastSyncStatus === "error" ? "(Error)" : ""}`
                        : "Never"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => openEditDialog(feed)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="xs"
                          className="text-danger hover:text-danger"
                          onClick={() => handleDeleteFeed(feed.id)}
                          disabled={deleteFeed.isPending}
                        >
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell className="px-3 py-3 text-sm text-content-muted" colSpan={6}>
                    No sync feeds configured. Add a feed to start syncing data from GetHookd.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Feed Dialog */}
      <DialogRoot open={isFeedDialogOpen} onOpenChange={setIsFeedDialogOpen}>
        <DialogContent>
          <DialogTitle>{editingFeed ? "Edit Sync Feed" : "Add Sync Feed"}</DialogTitle>
          <DialogDescription>
            Configure a GetHookd sync feed to automatically import data.
          </DialogDescription>
          <div className="space-y-4 mt-4">
            <FieldRoot>
              <FieldLabel>Feed Name</FieldLabel>
              <FieldControl>
                <Input
                  placeholder="e.g., Product Catalog"
                  value={feedForm.name}
                  onChange={(e) => setFeedForm({ ...feedForm, name: e.target.value })}
                />
              </FieldControl>
            </FieldRoot>
            <FieldRoot>
              <FieldLabel>Source URL</FieldLabel>
              <FieldControl>
                <Input
                  placeholder="https://api.gethookd.io/v1/..."
                  value={feedForm.sourceUrl}
                  onChange={(e) => setFeedForm({ ...feedForm, sourceUrl: e.target.value })}
                />
              </FieldControl>
            </FieldRoot>
            <FieldRoot>
              <FieldLabel>Webhook Path</FieldLabel>
              <FieldControl>
                <Input
                  placeholder="/webhooks/gethookd/..."
                  value={feedForm.webhookPath}
                  onChange={(e) => setFeedForm({ ...feedForm, webhookPath: e.target.value })}
                />
              </FieldControl>
            </FieldRoot>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="isActive"
                checked={feedForm.isActive}
                onChange={(e) => setFeedForm({ ...feedForm, isActive: e.target.checked })}
                className="rounded border-input-border"
              />
              <label htmlFor="isActive" className="text-sm text-content cursor-pointer">
                Active
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <DialogClose
                render={<Button variant="ghost" size="sm">Cancel</Button>}
              />
              <Button
                size="sm"
                onClick={editingFeed ? handleUpdateFeed : handleCreateFeed}
                disabled={
                  !feedForm.name.trim() ||
                  !feedForm.sourceUrl.trim() ||
                  !feedForm.webhookPath.trim() ||
                  createFeed.isPending ||
                  updateFeed.isPending
                }
              >
                {createFeed.isPending || updateFeed.isPending
                  ? "Saving..."
                  : editingFeed
                  ? "Update Feed"
                  : "Create Feed"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
