import { request } from "./client";
import type { DataAcquisitionSessionDetail, DataAcquisitionTurnResponse } from "../types";

export async function createDataAcquisitionSession(
  problemDescription: string,
): Promise<DataAcquisitionTurnResponse> {
  return request<DataAcquisitionTurnResponse>("/api/v1/data-acquisition-sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ problem_description: problemDescription }),
  });
}

export async function sendDataAcquisitionMessage(
  sessionId: string,
  message: string,
): Promise<DataAcquisitionTurnResponse> {
  return request<DataAcquisitionTurnResponse>(`/api/v1/data-acquisition-sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function getDataAcquisitionSession(sessionId: string): Promise<DataAcquisitionSessionDetail> {
  return request<DataAcquisitionSessionDetail>(`/api/v1/data-acquisition-sessions/${sessionId}`);
}
