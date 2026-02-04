import { useAuth } from "@clerk/clerk-react";
import { useCallback, useMemo } from "react";

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
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
  const detail = (raw as { detail?: unknown })?.detail;
  let message: string | undefined;
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    message = first?.msg;
  } else if (typeof (raw as { message?: unknown })?.message === "string") {
    message = (raw as { message?: string }).message;
  }
  if (!message || typeof message !== "string") {
    message = resp.statusText || "Request failed";
  }
  return { message, status: resp.status, raw };
}

export function useApiClient(baseUrl: string = defaultBaseUrl) {
  const { getToken } = useAuth();

  const request = useCallback(
    async <T>(path: string, init: RequestInit = {}): Promise<T> => {
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
    },
    [baseUrl, getToken],
  );

  const get = useCallback(<T,>(path: string): Promise<T> => request<T>(path, { method: "GET" }), [request]);

  const post = useCallback(
    <T,>(path: string, body?: unknown): Promise<T> =>
      request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
    [request],
  );

  return useMemo(() => ({ request, get, post }), [get, post, request]);
}
