import { request } from "./client";
import type { Cadence, JoinDataset, JoinType, ModelingSpec, ModelingSpecDetail } from "../types";

export async function createModelingSpec(datasetId: string): Promise<ModelingSpec> {
  return request<ModelingSpec>(`/api/v1/datasets/${datasetId}/modeling-specs`, {
    method: "POST",
  });
}

export async function getModelingSpec(specId: string): Promise<ModelingSpecDetail> {
  return request<ModelingSpecDetail>(`/api/v1/modeling-specs/${specId}`);
}

export async function sendChatMessage(
  specId: string,
  message: string,
): Promise<{ reply_message: string; spec: ModelingSpec }> {
  return request(`/api/v1/modeling-specs/${specId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function updateModelingSpec(
  specId: string,
  patch: { candidate_features?: string[]; retrain_cadence?: Cadence; score_cadence?: Cadence },
): Promise<ModelingSpec> {
  return request<ModelingSpec>(`/api/v1/modeling-specs/${specId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export async function listJoinDatasets(specId: string): Promise<JoinDataset[]> {
  return request<JoinDataset[]>(`/api/v1/modeling-specs/${specId}/join-datasets`);
}

export async function addJoinDataset(
  specId: string,
  body: { dataset_id: string; join_key_column: string; join_type: JoinType },
): Promise<JoinDataset> {
  return request<JoinDataset>(`/api/v1/modeling-specs/${specId}/join-datasets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function removeJoinDataset(specId: string, joinId: string): Promise<void> {
  await request<void>(`/api/v1/modeling-specs/${specId}/join-datasets/${joinId}`, {
    method: "DELETE",
  });
}
