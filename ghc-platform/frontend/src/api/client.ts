import { useAuth } from "@clerk/clerk-react";

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

export type ApiError = {
  message: string;
  status: number;
  raw?: unknown;
};

async function parseError(resp: Response): Promise<ApiError> {
  let raw: unknown = undefined;
  try {
    raw = await resp.clone().json();
  } catch {
    raw = await resp.text();
  }
  const message =
    (raw as { detail?: string; message?: string })?.detail ||
    (raw as { message?: string })?.message ||
    resp.statusText ||
    "Request failed";
  return { message, status: resp.status, raw };
}

export function useApiClient(baseUrl: string = defaultBaseUrl) {
  const { getToken } = useAuth();

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await getToken({ template: clerkTokenTemplate, skipCache: true });
    const headers = new Headers(init.headers || {});
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    headers.set("Content-Type", "application/json");

    const resp = await fetch(`${baseUrl}${path}`, { ...init, headers });
    if (!resp.ok) {
      throw await parseError(resp);
    }
    if (resp.status === 204) {
      return undefined as T;
    }
    return resp.json() as Promise<T>;
  }

  function get<T>(path: string): Promise<T> {
    return request<T>(path, { method: "GET" });
  }

  function post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
  }

  return { request, get, post };
}
