import { PosthogAnalyticsSettings } from "@/components/clients/PosthogAnalyticsSettings";
import { EmptyState } from "@/components/layout/EmptyState";
import { InlineWorkspacePicker } from "@/components/layout/InlineWorkspacePicker";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export function AnalyticsPage() {
  const { workspace } = useWorkspace();

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Analytics"
          description="Select a workspace to manage PostHog analytics settings."
        />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to access workspace-owned analytics settings."
          actions={<InlineWorkspacePicker />}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Analytics"
        description={`Workspace PostHog settings for ${workspace.name}.`}
      />
      <PosthogAnalyticsSettings clientId={workspace.id} />
    </div>
  );
}
