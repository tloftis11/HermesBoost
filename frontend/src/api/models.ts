import { request } from "./client";
import type { BuildModelResponse, Leaderboard, ModelGuided, ModelListItem, ScoreResponse, ScoreRun } from "../types";

export async function listModels(): Promise<ModelListItem[]> {
  return request<ModelListItem[]>("/api/v1/models");
}

export async function buildModel(specId: string): Promise<BuildModelResponse> {
  return request<BuildModelResponse>(`/api/v1/modeling-specs/${specId}/build`, {
    method: "POST",
  });
}

export async function getModel(modelId: string): Promise<ModelGuided> {
  return request<ModelGuided>(`/api/v1/models/${modelId}`);
}

export async function getLeaderboard(modelId: string): Promise<Leaderboard> {
  return request<Leaderboard>(`/api/v1/models/${modelId}/leaderboard`);
}

export async function getModelForSpec(specId: string): Promise<ModelGuided> {
  return request<ModelGuided>(`/api/v1/modeling-specs/${specId}/models`);
}

export async function scoreModel(modelId: string): Promise<ScoreResponse> {
  return request<ScoreResponse>(`/api/v1/models/${modelId}/score`, { method: "POST" });
}

export async function getScores(modelId: string): Promise<ScoreRun> {
  return request<ScoreRun>(`/api/v1/models/${modelId}/scores`);
}

export async function promoteCandidate(modelId: string, candidateId: string): Promise<ModelGuided> {
  return request<ModelGuided>(`/api/v1/models/${modelId}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_id: candidateId }),
  });
}
