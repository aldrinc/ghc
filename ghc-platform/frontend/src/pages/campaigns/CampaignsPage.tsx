import { FormEvent, useEffect, useState } from "react";
import { useApiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import type { Campaign, Client } from "@/types/common";

export function CampaignsPage() {
  const { request } = useApiClient();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    refresh();
    request<Client[]>("/clients").then(setClients).catch(() => setClients([]));
  }, []);

  const refresh = () => {
    request<Campaign[]>("/campaigns").then(setCampaigns).catch(() => setCampaigns([]));
  };

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!clientId || !name.trim()) return;
    setMessage(null);
    await request("/campaigns", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, name }),
    });
    setName("");
    setMessage("Campaign created");
    refresh();
  };

  const handlePlan = async (campaignId: string) => {
    setMessage(null);
    try {
      await request(`/campaigns/${campaignId}/plan`, {
        method: "POST",
        body: JSON.stringify({ business_goal_id: "goal-" + Date.now() }),
      });
      setMessage("Campaign planning workflow started");
    } catch (err) {
      setMessage(`Cannot start planning: ${(err as Error).message}`);
    }
  };

  return (
    <div className="space-y-3">
      <h2 className="text-xl font-semibold text-content">Campaigns</h2>
      <form onSubmit={handleCreate} className="ds-card ds-card--md flex flex-col gap-3">
        <div className="text-sm font-semibold text-content">Create campaign</div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Select
            value={clientId}
            onValueChange={setClientId}
            options={[{ label: "Select client", value: "" }, ...clients.map((c) => ({ label: c.name, value: c.id }))]}
            placeholder="Select client"
            className="flex-1"
          />
          <Input
            className="flex-1"
            placeholder="Campaign name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Button type="submit">Create</Button>
        </div>
      </form>
      {message && <div className="text-sm text-success">{message}</div>}
      <ul className="space-y-2">
        {campaigns.map((c) => (
          <li key={c.id} className="ds-card ds-card--sm">
            <div className="flex items-center justify-between gap-2">
              <div className="space-y-1">
                <div className="font-semibold text-content">{c.name}</div>
                <div className="text-sm text-content-muted flex items-center gap-2">
                  Client: {c.client_id} <Badge tone="neutral">Campaign</Badge>
                </div>
              </div>
              <Button variant="secondary" size="sm" onClick={() => handlePlan(c.id)}>
                Start planning
              </Button>
            </div>
          </li>
        ))}
        {campaigns.length === 0 && <li className="text-sm text-content-muted">No campaigns yet.</li>}
      </ul>
    </div>
  );
}
