import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { LibraryPage } from "@/pages/library/LibraryPage";
import { MetaIntegrationPanel } from "@/pages/library/MetaIntegrationPanel";

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
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            const next = new URLSearchParams(params);
            next.set("tab", "library");
            setParams(next, { replace: true });
          }}
          className={[
            "rounded-full px-3 py-1.5 text-sm font-medium transition",
            tab === "library"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-700 hover:bg-slate-200",
          ].join(" ")}
        >
          Library
        </button>
        <button
          type="button"
          onClick={() => {
            const next = new URLSearchParams(params);
            next.set("tab", "meta");
            setParams(next, { replace: true });
          }}
          className={[
            "rounded-full px-3 py-1.5 text-sm font-medium transition",
            tab === "meta"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-700 hover:bg-slate-200",
          ].join(" ")}
        >
          Meta
        </button>
      </div>

      {tab === "library" ? <LibraryPage showHeader={false} /> : <MetaIntegrationPanel />}
    </div>
  );
}
