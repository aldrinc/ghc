import { useEffect, useState } from "react";
import { useApiClient } from "@/api/client";
import type { CompanySwipeAsset } from "@/types/swipes";

export function SwipesPage() {
  const { request } = useApiClient();
  const [swipes, setSwipes] = useState<CompanySwipeAsset[]>([]);

  useEffect(() => {
    request<CompanySwipeAsset[]>("/swipes/company").then(setSwipes).catch(() => setSwipes([]));
  }, [request]);

  return (
    <div className="space-y-3">
      <h2 className="text-xl font-semibold text-content">Company Swipes</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {swipes.map((s) => (
          <div key={s.id} className="rounded-lg border border-border bg-white p-3 shadow-sm">
            <div className="font-medium text-content">{s.title || "Untitled"}</div>
            <div className="text-sm text-content-muted">{s.platforms}</div>
          </div>
        ))}
        {swipes.length === 0 && <p className="text-sm text-content-muted">No swipes loaded.</p>}
      </div>
    </div>
  );
}
