import { useMemo } from "react";
import { useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { useClient } from "@/api/clients";
import { useWorkflows } from "@/api/workflows";
import { OnboardingWizard } from "@/components/clients/OnboardingWizard";

export function ClientDetailPage() {
  const { clientId } = useParams();
  const { data: client, isLoading } = useClient(clientId);
  const { data: workflows } = useWorkflows();

  const clientWorkflows = useMemo(
    () => (workflows || []).filter((wf) => wf.client_id === clientId),
    [workflows, clientId]
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title={client?.name || "Workspace detail"}
        description={client ? `Industry: ${client.industry || "Not set"}` : "Overview, onboarding, and workflows."}
      />

      <div className="ds-card ds-card--md shadow-none">
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="onboarding">Onboarding</TabsTrigger>
            <TabsTrigger value="workflows">Workflows</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            {isLoading ? (
              <div className="text-sm text-slate-500">Loading client…</div>
            ) : client ? (
              <div className="space-y-2 text-sm text-content">
                <div>
                  <span className="font-semibold">Client ID:</span>{" "}
                  <span className="font-mono text-xs text-content-muted">{client.id}</span>
                </div>
                <div>
                  <span className="font-semibold">Org ID:</span>{" "}
                  <span className="font-mono text-xs text-content-muted">{client.org_id}</span>
                </div>
                <div>
                  <span className="font-semibold">Industry:</span> {client.industry || "Not set"}
                </div>
              </div>
            ) : (
              <div className="text-sm text-danger">Client not found.</div>
            )}
          </TabsContent>

          <TabsContent value="onboarding">
            <div className="flex items-start justify-between">
              <div className="space-y-1 text-sm text-content">
                <div className="font-semibold text-content">Onboarding</div>
                <p className="text-content-muted">
                  Start the staged onboarding wizard to collect brand context, offers, markets, and goals.
                </p>
              </div>
              <OnboardingWizard
                clientId={clientId}
                clientName={client?.name}
                clientIndustry={client?.industry}
              />
            </div>
          </TabsContent>

          <TabsContent value="workflows">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-content">Recent workflows</span>
                <span className="text-xs text-content-muted">{clientWorkflows.length} total</span>
              </div>
              <div className="overflow-hidden">
                <Table variant="ghost">
                  <TableHeader>
                    <TableRow>
                      <TableHeadCell>Kind</TableHeadCell>
                      <TableHeadCell>Status</TableHeadCell>
                      <TableHeadCell>Started</TableHeadCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {clientWorkflows.map((wf) => (
                      <TableRow key={wf.id}>
                        <TableCell className="font-semibold text-content">{wf.kind}</TableCell>
                        <TableCell className="text-content-muted">{wf.status}</TableCell>
                        <TableCell className="text-xs text-content-muted">{wf.started_at}</TableCell>
                      </TableRow>
                    ))}
                    {!clientWorkflows.length && (
                      <TableRow>
                        <TableCell className="px-3 py-3 text-sm text-content-muted" colSpan={3}>
                          No workflows for this client yet.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
