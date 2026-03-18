import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ShopifyTab } from "./ShopifyTab";

export function CommercePage() {
  const { workspace } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  const activeTab = tabParam === "shopify" ? "shopify" : "shopify"; // default to shopify; extend for new providers

  const handleTabChange = (value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", value);
    setSearchParams(next, { replace: true });
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Commerce" description="Select a workspace to manage commerce integrations." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a workspace from the sidebar to manage commerce integrations.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Commerce"
        description={workspace.industry ? `${workspace.name} · ${workspace.industry}` : workspace.name}
      />

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="shopify">Shopify</TabsTrigger>
        </TabsList>
        <TabsContent value="shopify">
          <ShopifyTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
