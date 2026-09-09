import { request } from "./client";
import type { BuildModelResponse, Leaderboard, ModelGuided, ModelListItem } from "../types";

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
