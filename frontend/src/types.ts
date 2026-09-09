export type DatasetStatus = "uploaded" | "profiling" | "profiled" | "error";

export interface Dataset {
  id: string;
  name: string;
  status: DatasetStatus;
  row_count: number | null;
  column_count: number | null;
  error_message: string | null;
  series_id: string | null;
  as_of_date: string | null;
  pending_confirmation: boolean;
  source_url: string | null;
  created_at: string;
}

export interface DatasetSeries {
  id: string;
  name: string;
  created_at: string;
}

export interface TopValue {
  value: string;
  count: number;
}

export type ColumnDtype = "numeric" | "categorical" | "id";

export interface ColumnProfile {
  name: string;
  dtype: ColumnDtype;
  null_rate: number;
  distinct_count: number;
  min: number | null;
  max: number | null;
  mean: number | null;
  top_values: TopValue[] | null;
  histogram: number[] | null;
}

export interface DatasetProfile {
  status: "profiling" | "profiled" | "error";
  row_count: number | null;
  column_count: number | null;
  columns: ColumnProfile[] | null;
  ai_description: string | null;
  ai_description_model: string | null;
  profiled_at: string | null;
  error_message: string | null;
}

export type TaskType =
  | "risk_scoring"
  | "classification"
  | "regression"
  | "time_series_forecast"
  | "clustering"
  | "anomaly_detection";

export type Cadence = "daily" | "weekly" | "monthly";

export interface ModelingSpec {
  id: string;
  dataset_id: string;
  status: "draft" | "confirmed";
  task_type: TaskType | null;
  task_description: string | null;
  target: string | null;
  candidate_features: string[];
  evaluation_metric: string | null;
  entity_id_column: string | null;
  acknowledged_imbalance: boolean;
  retrain_cadence: Cadence;
  score_cadence: Cadence;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ModelingSpecDetail {
  spec: ModelingSpec;
  messages: ChatMessage[];
}

export type ModelStatus = "training" | "ready" | "error";
export type CandidateRole = "recommended" | "baseline";

export interface FeatureImportanceItem {
  feature: string;
  importance: number;
}

export interface ModelCandidate {
  id: string;
  role: CandidateRole;
  algorithm: string;
  ml_task: string;
  metrics: Record<string, number | boolean | null>;
  feature_importance: FeatureImportanceItem[] | null;
  hyperparams: Record<string, unknown> | null;
  // Decimal on the backend -- Pydantic v2 serializes Decimal as a JSON
  // string (e.g. "5.00"), not a number, to preserve precision.
  train_time_seconds: string | null;
}

export interface KeyDriver {
  feature: string;
  plain_description: string;
  relative_importance: number;
}

export interface ModelRun {
  id: string;
  status: "running" | "completed" | "error";
  ml_task: string | null;
  row_count_used: number | null;
  warnings: string[] | null;
  interpretation_summary: string | null;
  interpretation_key_drivers: KeyDriver[] | null;
  interpretation_model: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface ModelGuided {
  id: string;
  modeling_spec_id: string;
  status: ModelStatus;
  error_message: string | null;
  active_candidate: ModelCandidate | null;
  latest_run: ModelRun | null;
}

export interface Leaderboard {
  id: string;
  modeling_spec_id: string;
  status: ModelStatus;
  candidates: ModelCandidate[];
  run: ModelRun | null;
}

export interface BuildModelResponse {
  model_id: string;
  model_run_id: string;
}

export interface ModelListItem {
  id: string;
  modeling_spec_id: string;
  dataset_name: string;
  task_description: string | null;
  status: ModelStatus;
  algorithm: string | null;
  ml_task: string | null;
  primary_metric_label: string | null;
  primary_metric_value: number | null;
  updated_at: string;
}

export type JoinType = "left" | "inner";

export interface JoinDataset {
  id: string;
  dataset_id: string;
  dataset_name: string;
  join_key_column: string;
  join_type: JoinType;
}

export interface ScoreResponse {
  model_id: string;
  model_run_id: string;
}

export interface ScoredRow {
  id: string;
  entity_id: string;
  score_date: string;
  predicted_value: number | null;
  predicted_label: string | null;
  predicted_probability: number | null;
}

export interface ScoreRun {
  id: string;
  modeling_spec_id: string;
  status: ModelStatus;
  run: ModelRun | null;
  rows: ScoredRow[];
  total_row_count: number | null;
}

export interface ApiKeyOut {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKeyOut {
  raw_key: string;
}

export interface RiskScoreOut {
  id: string;
  name: string;
  probability_model_id: string;
  magnitude_model_id: string;
  positive_label: string;
  created_at: string;
}

export interface RiskScoreRow {
  entity_id: string;
  score_date: string;
  probability: number;
  predicted_magnitude: number;
  risk_score: number;
}

export interface RiskScoreResult {
  id: string;
  name: string;
  score_date: string | null;
  rows: RiskScoreRow[];
  total_row_count: number;
}

export interface DataAcquisitionSession {
  id: string;
  problem_description: string;
  status: string;
  created_at: string;
}

export interface DataAcquisitionMessage {
  role: "user" | "assistant";
  display_text: string;
  staged_dataset_ids: string[];
  created_at: string;
}

export interface DataAcquisitionTurnResponse {
  session: DataAcquisitionSession;
  reply_message: string;
  staged_dataset_ids: string[];
}

export interface DataAcquisitionSessionDetail {
  session: DataAcquisitionSession;
  messages: DataAcquisitionMessage[];
}
