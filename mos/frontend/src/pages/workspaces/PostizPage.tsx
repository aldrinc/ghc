import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { InlineWorkspacePicker } from "@/components/layout/InlineWorkspacePicker";
import { PostizSettings } from "@/components/clients/PostizSettings";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export function PostizPage() {
  const { workspace } = useWorkspace();

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Postiz"
          description="Select a workspace to manage Postiz credentials, channels, profiles, and publications."
        />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to access Postiz publishing settings."
          actions={<InlineWorkspacePicker />}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Postiz"
        description={`Workspace social publishing settings for ${workspace.name}.`}
      />
      <PostizSettings clientId={workspace.id} />
    </div>
  );
}
