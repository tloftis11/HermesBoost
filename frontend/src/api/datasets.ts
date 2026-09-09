import { request } from "./client";
import type { Dataset, DatasetProfile, DatasetSeries } from "../types";

export async function listDatasets(): Promise<Dataset[]> {
  return request<Dataset[]>("/api/v1/datasets");
}

export async function uploadDataset(
  file: File,
  series?: { seriesId: string; asOfDate: string },
): Promise<{ id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  if (series) {
    form.append("series_id", series.seriesId);
    form.append("as_of_date", series.asOfDate);
  }
  return request("/api/v1/datasets", { method: "POST", body: form });
}

export async function getProfile(datasetId: string): Promise<DatasetProfile> {
  return request<DatasetProfile>(`/api/v1/datasets/${datasetId}/profile`);
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  return request<Dataset>(`/api/v1/datasets/${datasetId}`);
}

export async function listDatasetSeries(): Promise<DatasetSeries[]> {
  return request<DatasetSeries[]>("/api/v1/dataset-series");
}

export async function createDatasetSeries(name: string): Promise<DatasetSeries> {
  return request<DatasetSeries>("/api/v1/dataset-series", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}
