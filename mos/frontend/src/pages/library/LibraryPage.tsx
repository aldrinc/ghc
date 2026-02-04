import { useMemo, useState, type ReactNode } from "react";
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
        active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200",
      ].join(" ")}
      type="button"
    >
      {children}
    </button>
  );
}

export function LibraryPage({ showHeader = true }: { showHeader?: boolean }) {
  const [tab, setTab] = useState<LibraryTab>("teardowns");

  const description = useMemo(() => {
    switch (tab) {
      case "teardowns":
        return "Canonical teardown cards built from deduped creatives (ad copy + media).";
      case "ads":
        return "Raw ads you’ve ingested (with full media + metadata).";
      case "saved":
        return "Your saved swipes inside the library.";
      default:
        return "Swipe library and reference assets.";
    }
  }, [tab]);

  return (
    <div className="space-y-4">
      {showHeader ? <PageHeader title="Library" description={description} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <TabButton active={tab === "teardowns"} onClick={() => setTab("teardowns")}>
          Teardowns
        </TabButton>
        <TabButton active={tab === "ads"} onClick={() => setTab("ads")}>
          Ads
        </TabButton>
        <TabButton active={tab === "saved"} onClick={() => setTab("saved")}>
          Saved
        </TabButton>
      </div>

      {tab === "teardowns" && <CreativeTeardownsPanel />}
      {tab === "ads" && <AdsPanel />}
      {tab === "saved" && <SwipesPage />}
    </div>
  );
}
