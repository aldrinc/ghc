export interface Client {
  id: string;
  org_id: string;
  name: string;
  industry?: string;
}

export interface Campaign {
  id: string;
  org_id: string;
  client_id: string;
  name: string;
}

export interface WorkflowRun {
  id: string;
  org_id: string;
  client_id?: string | null;
  campaign_id?: string | null;
  temporal_workflow_id: string;
  temporal_run_id: string;
  kind: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
}

export interface ActivityLog {
  id: string;
  workflow_run_id: string;
  step: string;
  status: string;
  payload_in?: Record<string, unknown> | null;
  payload_out?: Record<string, unknown> | null;
  error?: string | null;
  created_at: string;
}

export interface Artifact {
  id: string;
  org_id: string;
  client_id: string;
  campaign_id?: string | null;
  type: string;
  version: number;
  data: Record<string, unknown>;
  created_by_user?: string | null;
  created_at: string;
}

export interface ResearchArtifactRef {
  step_key: string;
  doc_url: string;
  doc_id: string;
  summary?: string;
  content?: string;
}

export interface Experiment {
  id: string;
  org_id: string;
  client_id: string;
  campaign_id: string;
  name: string;
  status?: string;
  experiment_spec_artifact_id?: string;
  created_at?: string;
}

export interface WorkflowDetail {
  run: WorkflowRun;
  logs: ActivityLog[];
  client_canon?: Artifact | null;
  metric_schema?: Artifact | null;
  strategy_sheet?: Artifact | null;
  experiment_specs?: Artifact[] | null;
  asset_briefs?: Artifact[] | null;
  precanon_research?: Record<string, unknown> | null;
  research_artifacts?: ResearchArtifactRef[] | null;
  research_highlights?: Record<string, unknown> | null;
}
