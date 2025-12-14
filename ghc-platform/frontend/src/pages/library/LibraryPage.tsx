import { PageHeader } from "@/components/layout/PageHeader";
import { SwipesPage } from "@/pages/swipes/SwipesPage";

export function LibraryPage() {
  return (
    <div className="space-y-4">
      <PageHeader title="Library" description="Swipe library and reference assets." />
      <SwipesPage />
    </div>
  );
}
