import { request } from "./client";
import type { ApiKeyCreated, ApiKeyOut } from "../types";

export async function listApiKeys(): Promise<ApiKeyOut[]> {
  return request<ApiKeyOut[]>("/api/v1/api-keys");
}

export async function createApiKey(name: string): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>("/api/v1/api-keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function revokeApiKey(id: string): Promise<void> {
  await request<void>(`/api/v1/api-keys/${id}`, { method: "DELETE" });
}
