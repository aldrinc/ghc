import { useState } from "react";
import { RefreshCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { useConvertImport } from "@/api/storefrontTemplates";

const supportedFamilies = [
  { label: "Sales PDP", value: "sales-pdp" },
  { label: "Pre-sales Listicle", value: "listicle-presell" },
];

const supportedPageTypes = [
  { label: "Product Detail", value: "product_detail" },
  { label: "Pre-sell", value: "pre_sell" },
];

export function ConvertToDraftCard({
  importId,
  workspaceId,
  selectedSectionIds,
  defaultName,
  defaultFamily,
  defaultPageType,
  onConverted,
}: {
  importId: string;
  workspaceId: string;
  selectedSectionIds: string[];
  defaultName: string;
  defaultFamily: string;
  defaultPageType: string;
  onConverted: (variantId: string) => void;
}) {
  const convertImport = useConvertImport();
  const [name, setName] = useState(defaultName);
  const [family, setFamily] = useState(defaultFamily);
  const [pageType, setPageType] = useState(defaultPageType);
  const [reviewNotes, setReviewNotes] = useState("");

  const handleConvert = async () => {
    if (!name) return;
    try {
      const createdVariant = await convertImport.mutateAsync({
        importId,
        clientId: workspaceId,
        name,
        family,
        pageType,
        acceptedSectionIds: selectedSectionIds,
        reviewNotes: reviewNotes || undefined,
      });
      toast.success({
        title: "Draft created",
        description: `${createdVariant.name} is now available under Draft variants.`,
      });
      onConverted(createdVariant.id);
    } catch (err) {
      console.error("Failed to convert import:", err);
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="text-sm font-semibold text-content">Convert to draft</div>
      <div className="mt-1 text-xs text-content-muted">
        Synthesize selected sections into a reusable Puck draft.
      </div>
      <div className="mt-3 space-y-3">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-content">Name</label>
          <Input placeholder="My variant" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-content">Family</label>
          <Select value={family} onValueChange={setFamily} options={supportedFamilies} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-content">Page type</label>
          <Select value={pageType} onValueChange={setPageType} options={supportedPageTypes} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-content">Review notes (optional)</label>
          <Input
            placeholder="Notes for reviewers"
            value={reviewNotes}
            onChange={(e) => setReviewNotes(e.target.value)}
          />
        </div>
        <Button
          onClick={handleConvert}
          disabled={!name || !selectedSectionIds.length || convertImport.isPending}
          className="w-full"
        >
          {convertImport.isPending ? (
            <>
              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
              Converting...
            </>
          ) : (
            <>
              <Sparkles className="mr-2 h-4 w-4" />
              Convert to Draft
            </>
          )}
        </Button>
        {convertImport.isError && (
          <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
            Failed to convert import. Please try again.
          </div>
        )}
      </div>
    </div>
  );
}
