export interface Artifact<T = unknown> {
  id: string;
  org_id: string;
  client_id: string;
  campaign_id?: string | null;
  type: string;
  version: number;
  data: T;
  created_at: string;
}

export interface ClientCanon {
  clientId: string;
  brand: Record<string, unknown>;
}

export interface MetricSchema {
  clientId: string;
  events: any[];
}

export interface StrategySheet {
  clientId: string;
  goal?: string;
}

export interface ExperimentSpec {
  id: string;
  name: string;
}

export interface AssetBrief {
  id: string;
  clientId: string;
}
