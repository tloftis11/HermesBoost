import { request } from "./client";
import type { Dataset, DatasetProfile } from "../types";

export async function listDatasets(): Promise<Dataset[]> {
  return request<Dataset[]>("/api/v1/datasets");
}

export async function uploadDataset(file: File): Promise<{ id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  return request("/api/v1/datasets", { method: "POST", body: form });
}

export async function getProfile(datasetId: string): Promise<DatasetProfile> {
  return request<DatasetProfile>(`/api/v1/datasets/${datasetId}/profile`);
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  return request<Dataset>(`/api/v1/datasets/${datasetId}`);
}
