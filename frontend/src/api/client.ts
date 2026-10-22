import { devAuthHeaders } from "@/dev-auth/store";

// Thin same-origin fetch wrapper (D-22). Paths are relative, e.g. "/api/v1/...".
export type ApiResult<T> =
  | { ok: true; status: number; data: T; correlationId: string | null }
  | { ok: false; status: number; error: unknown; correlationId: string | null };

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  for (const [name, value] of Object.entries(devAuthHeaders())) headers.set(name, value);

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (error) {
    return { ok: false, status: 0, error, correlationId: null };
  }

  const correlationId = response.headers.get("X-Correlation-ID");
  let body: unknown = null;
  const text = await response.text().catch(() => "");
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  return response.ok
    ? { ok: true, status: response.status, data: body as T, correlationId }
    : { ok: false, status: response.status, error: body, correlationId };
}
