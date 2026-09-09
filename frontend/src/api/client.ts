export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(options.headers ?? {}),
      // Authorization header hook point: unused while the backend runs
      // AUTH_MODE=dev. Once a login screen exists, attach the Supabase
      // session token here (e.g. `Authorization: Bearer <token>`).
    },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}
