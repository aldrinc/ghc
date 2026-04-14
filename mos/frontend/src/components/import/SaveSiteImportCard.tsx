import { useState } from "react";
import { RefreshCw, Save } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatPageType } from "@/lib/siteFormatters";
import { readQueryError } from "./importUtils";
import { useSaveSiteImport } from "@/api/storefrontTemplates";
import { useNavigate } from "react-router-dom";
import type { SaveSiteImportResponse } from "@/types/storefrontTemplates";

export function SaveSiteImportCard({
  importId,
  workspaceId,
  savedSiteId,
  defaultSiteName,
  onSaved,
}: {
  importId: string;
  workspaceId: string;
  savedSiteId: string | null | undefined;
  defaultSiteName: string;
  onSaved: (result: SaveSiteImportResponse) => void;
}) {
  const navigate = useNavigate();
  const saveSiteImport = useSaveSiteImport();
  const [siteName, setSiteName] = useState(defaultSiteName);
  const [description, setDescription] = useState("");
  const [saveResult, setSaveResult] = useState<SaveSiteImportResponse | null>(null);

  const handleSave = async () => {
    if (!siteName.trim()) return;
    try {
      const result = await saveSiteImport.mutateAsync({
        importId,
        clientId: workspaceId,
        siteName: siteName.trim(),
        description: description.trim() || undefined,
      });
      setSaveResult(result);
      onSaved(result);
    } catch (err) {
      console.error("Failed to save site import:", err);
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-content">Save as site</div>
          <div className="text-xs text-content-muted">
            Creates a new site record from the adapter-backed page set.
          </div>
        </div>
        {savedSiteId ? <Badge tone="success">Already saved</Badge> : null}
      </div>

      {saveResult ? (
        <div className="mt-3 rounded-xl border border-success/30 bg-success/5 px-3 py-3 text-sm text-success">
          <div className="font-semibold">Saved {saveResult.siteName}</div>
          <div className="mt-1">
            Created {saveResult.pageCount} page draft{saveResult.pageCount === 1 ? "" : "s"}
            {saveResult.entryPageType
              ? ` with entry page ${formatPageType(saveResult.entryPageType)}.`
              : "."}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => navigate("/workspaces/sites")}>
              Open Sites
            </Button>
          </div>
        </div>
      ) : null}

      {!savedSiteId ? (
        <div className="mt-3 space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Site name</label>
            <Input value={siteName} onChange={(e) => setSiteName(e.target.value)} placeholder="Imported site" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Description (optional)</label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this import represents"
            />
          </div>
          <Button onClick={handleSave} disabled={!siteName.trim() || saveSiteImport.isPending} className="w-full">
            {saveSiteImport.isPending ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                Saving site...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save as New Site
              </>
            )}
          </Button>
          {saveSiteImport.isError ? (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-3 text-sm text-danger">
              {readQueryError(saveSiteImport.error, "Failed to save import as site.")}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="mt-3 rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
          Saved site id: <span className="font-semibold text-content">{savedSiteId}</span>
        </div>
      )}
    </div>
  );
}
