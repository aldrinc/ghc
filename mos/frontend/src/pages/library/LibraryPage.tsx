import { useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { CreativeTeardownsPanel } from "@/pages/library/CreativeTeardownsPanel";
import { AdsPanel } from "@/pages/library/AdsPanel";
import { SwipesPage } from "@/pages/swipes/SwipesPage";

type LibraryTab = "teardowns" | "ads" | "saved";

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "rounded-full px-3 py-1.5 text-sm font-medium transition",
        active ? "bg-primary text-primary-foreground" : "bg-surface-2 text-content-muted hover:bg-hover",
      ].join(" ")}
      type="button"
    >
      {children}
    </button>
  );
}

export function LibraryPage({ showHeader = true }: { showHeader?: boolean }) {
  const [params, setParams] = useSearchParams();
  const rawTab = params.get("libraryTab");
  const tab: LibraryTab = rawTab === "ads" || rawTab === "saved" ? rawTab : "teardowns";

  const selectTab = (nextTab: LibraryTab) => {
    const next = new URLSearchParams(params);
    next.set("libraryTab", nextTab);
    setParams(next, { replace: true });
  };

  const description = useMemo(() => {
    switch (tab) {
      case "teardowns":
        return "Canonical teardown cards built from deduped creatives (ad copy + media).";
      case "ads":
        return "Raw ads you’ve ingested (with full media + metadata).";
      case "saved":
        return "Browse every swipe collection and inspect the swipes inside each set.";
      default:
        return "Swipe library and reference assets.";
    }
  }, [tab]);

  return (
    <div className="space-y-4">
      {showHeader ? <PageHeader title="Library" description={description} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <TabButton active={tab === "teardowns"} onClick={() => selectTab("teardowns")}>
          Teardowns
        </TabButton>
        <TabButton active={tab === "ads"} onClick={() => selectTab("ads")}>
          Ads
        </TabButton>
        <TabButton active={tab === "saved"} onClick={() => selectTab("saved")}>
          Collections
        </TabButton>
      </div>

      {tab === "teardowns" && <CreativeTeardownsPanel />}
      {tab === "ads" && <AdsPanel />}
      {tab === "saved" && <SwipesPage />}
    </div>
  );
}
