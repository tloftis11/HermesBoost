export type DatasetStatus = "uploaded" | "profiling" | "profiled" | "error";

export interface Dataset {
  id: string;
  name: string;
  status: DatasetStatus;
  row_count: number | null;
  column_count: number | null;
  error_message: string | null;
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
