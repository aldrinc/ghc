import type { AssetBriefType } from "@/lib/assetBriefTypes";

export interface Client {
  id: string;
  org_id: string;
  name: string;
  industry?: string;
  design_system_id?: string | null;
}

export interface Campaign {
  id: string;
  org_id: string;
  client_id: string;
  product_id?: string | null;
  name: string;
  channels?: string[];
  asset_brief_types?: AssetBriefType[];
}

export interface WorkflowRun {
  id: string;
  org_id: string;
  client_id?: string | null;
  product_id?: string | null;
  campaign_id?: string | null;
  temporal_workflow_id: string;
  temporal_run_id: string;
  kind: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
}

export interface PendingActivityProgress {
  activity_id: string;
  activity_type: string;
  state?: string | null;
  attempt?: number;
  last_worker_identity?: string;
  last_started_time?: string | null;
  last_heartbeat_time?: string | null;
  scheduled_time?: string | null;
  expiration_time?: string | null;
  heartbeat_progress?: Record<string, unknown> | null;
}

export interface StrategyV2State {
  workflow_run_id?: string;
  current_stage?: string;
  pending_signal_type?: string | null;
  required_signal_type?: string | null;
  pending_decision_payload?: Record<string, unknown> | null;
  scored_candidate_summaries?: Record<string, unknown> | null;
  artifact_refs?: Record<string, string> | null;
}

export interface StrategyV2LaunchRecord {
  id: string;
  launch_type: "initial_angle" | "additional_ums" | "additional_angle";
  launch_key: string;
  campaign_id?: string | null;
  funnel_id?: string | null;
  angle_id: string;
  angle_run_id: string;
  selected_ums_id?: string | null;
  selected_variant_id?: string | null;
  launch_index?: number | null;
  launch_workflow_run_id?: string | null;
  launch_temporal_workflow_id?: string | null;
  launch_status?: string | null;
  created_by_user?: string | null;
  created_at: string;
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
  product_id?: string | null;
  campaign_id?: string | null;
  type: string;
  version: number;
  data: Record<string, unknown>;
  created_by_user?: string | null;
  created_at: string;
}

export interface Asset {
  id: string;
  org_id: string;
  client_id: string;
  campaign_id?: string | null;
  experiment_id?: string | null;
  product_id?: string | null;
  funnel_id?: string | null;
  public_id: string;
  asset_kind: string;
  channel_id: string;
  format: string;
  status: string;
  storage_key?: string | null;
  content_type?: string | null;
  width?: number | null;
  height?: number | null;
  file_status?: string | null;
  created_at: string;
  tags?: string[];
}

export interface ResearchArtifactRef {
  step_key: string;
  title?: string;
  doc_url: string;
  doc_id: string;
  summary?: string;
  content?: unknown;
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
  temporal_status?: string | null;
  pending_activity_progress?: PendingActivityProgress[] | null;
  strategy_v2_state?: StrategyV2State | null;
  strategy_v2_stage3?: Artifact | null;
  strategy_v2_offer?: Artifact | null;
  strategy_v2_copy?: Artifact | null;
  strategy_v2_copy_canonical?: Record<string, unknown> | null;
  strategy_v2_copy_context?: Artifact | null;
  strategy_v2_awareness_angle_matrix?: Artifact | null;
  strategy_v2_launches?: StrategyV2LaunchRecord[] | null;
}
