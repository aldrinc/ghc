import { Select } from "@/components/ui/select";
import { useWorkspace } from "@/contexts/WorkspaceContext";

/**
 * Compact inline workspace picker that can be embedded in empty states.
 * Selecting a workspace stays on the current page instead of redirecting.
 */
export function InlineWorkspacePicker() {
  const { clients, selectWorkspace, isLoading } = useWorkspace();

  if (isLoading) {
    return <span className="text-xs text-content-muted">Loading workspaces…</span>;
  }

  if (!clients.length) {
    return <span className="text-xs text-content-muted">No workspaces available.</span>;
  }

  return (
    <Select
      value=""
      onValueChange={(value) => {
        if (value) selectWorkspace(value);
      }}
      options={[
        { label: "Choose a workspace…", value: "" },
        ...clients.map((c) => ({ label: c.name, value: c.id })),
      ]}
      className="w-64"
    />
  );
}
