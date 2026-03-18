import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { LibraryPage } from "@/pages/library/LibraryPage";
import { MetaIntegrationPanel } from "@/pages/library/MetaIntegrationPanel";
import { cn } from "@/lib/utils";

const TOP_TABS = [
  { key: "library", label: "Library" },
  { key: "meta", label: "Meta" },
] as const;

export function CreativeLibraryPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "meta" ? "meta" : "library";

  const description = useMemo(() => {
    if (tab === "meta") {
      return "Track how angles become Meta creatives and browse live Meta inventory.";
    }
    return "A global repository of creative assets to feed new ideas.";
  }, [tab]);

  return (
    <div className="space-y-4">
      <PageHeader title="Creative Library" description={description} />
      <nav className="flex gap-1 border-b border-border">
        {TOP_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set("tab", t.key);
              setParams(next, { replace: true });
            }}
            className={cn(
              "px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
              tab === t.key
                ? "border-accent text-content"
                : "border-transparent text-content-muted hover:text-content hover:border-border",
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "library" ? <LibraryPage showHeader={false} /> : <MetaIntegrationPanel />}
    </div>
  );
}
