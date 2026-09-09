export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  // The raw `detail` from a FastAPI error response -- a plain string for
  // most errors, or a structured object (e.g. {code, minority_rate,
  // message}) for errors callers need to branch on, like the
  // imbalance-acknowledgment gate on building a model.
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
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
    const text = await res.text().catch(() => "");
    let detail: unknown;
    let message = text || res.statusText;
    try {
      const parsed = JSON.parse(text);
      detail = parsed.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail === "object" && "message" in (detail as Record<string, unknown>)) {
        message = String((detail as Record<string, unknown>).message);
      }
    } catch {
      // Not JSON -- keep the raw text as the message.
    }
    throw new ApiError(res.status, message, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}
