import { request } from "./client";
import type { RiskScoreOut, RiskScoreResult, UsageDoc } from "../types";

export async function listRiskScores(): Promise<RiskScoreOut[]> {
  return request<RiskScoreOut[]>("/api/v1/risk-scores");
}

export async function createRiskScore(body: {
  name: string;
  probability_model_id: string;
  magnitude_model_id: string;
  positive_label: string;
}): Promise<RiskScoreOut> {
  return request<RiskScoreOut>("/api/v1/risk-scores", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getRiskScore(id: string): Promise<RiskScoreOut> {
  return request<RiskScoreOut>(`/api/v1/risk-scores/${id}`);
}

export async function getRiskScoreResults(id: string): Promise<RiskScoreResult> {
  return request<RiskScoreResult>(`/api/v1/risk-scores/${id}/scores`);
}

export async function deleteRiskScore(id: string): Promise<void> {
  await request<void>(`/api/v1/risk-scores/${id}`, { method: "DELETE" });
}

export async function getRiskScoreUsage(id: string): Promise<UsageDoc> {
  return request<UsageDoc>(`/api/v1/risk-scores/${id}/usage`);
}
