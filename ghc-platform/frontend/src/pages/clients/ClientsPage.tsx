import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { buttonClasses } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { useClients } from "@/api/clients";
import { OnboardingWizard } from "@/components/clients/OnboardingWizard";

export function ClientsPage() {
  const navigate = useNavigate();
  const { data: clients, isLoading } = useClients();

  const sortedClients = useMemo(
    () => [...(clients || [])].sort((a, b) => a.name.localeCompare(b.name)),
    [clients]
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Clients"
        description="Create clients and drill into onboarding/campaigns."
        actions={<OnboardingWizard triggerLabel="New client" />}
      />

      <div className="rounded-lg border border-border bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="text-sm font-semibold text-content">Client list</div>
          <div className="text-xs text-content-muted">{clients?.length || 0} total</div>
        </div>
        {isLoading ? (
          <div className="p-4 text-sm text-content-muted">Loading clients…</div>
        ) : (
          <ul className="divide-y divide-border">
            {sortedClients.map((client) => (
              <li key={client.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-content">{client.name}</div>
                    <div className="text-xs text-content-muted">{client.industry || "Industry not set"}</div>
                  </div>
                  <Menu>
                    <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>Actions</MenuTrigger>
                    <MenuContent>
                      <MenuItem onClick={() => navigate(`/clients/${client.id}`)}>Open detail</MenuItem>
                      <MenuItem onClick={() => navigator.clipboard.writeText(client.id)}>Copy ID</MenuItem>
                    </MenuContent>
                  </Menu>
                </div>
              </li>
            ))}
            {!sortedClients.length && (
              <li className="px-4 py-4 text-sm text-content-muted">No clients yet. Create one to get started.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
