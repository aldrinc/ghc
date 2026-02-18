import { useAuth } from "@clerk/clerk-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import type { DesignSystem } from "@/types/designSystems";
import { toast } from "@/components/ui/toast";

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

async function readUploadError(resp: Response): Promise<string> {
  try {
    const raw = await resp.clone().json();
    const detail = (raw as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      if (typeof first?.msg === "string") return first.msg;
    }
    if (typeof (raw as { message?: unknown })?.message === "string") {
      return (raw as { message?: string }).message || "Upload failed";
    }
  } catch {
    // Fall through to text parsing
  }
  try {
    const text = await resp.text();
    if (text) return text;
  } catch {
    // Fall through to status text
  }
  return resp.statusText || "Upload failed";
}

export function useDesignSystems(clientId?: string, includeShared: boolean = false) {
  const { get } = useApiClient();
  return useQuery<DesignSystem[]>({
    queryKey: ["design-systems", "list", clientId, includeShared],
    queryFn: () => {
      const query = new URLSearchParams();
      if (clientId) query.set("clientId", clientId);
      if (includeShared) query.set("includeShared", "true");
      const suffix = query.toString();
      return get(`/design-systems${suffix ? `?${suffix}` : ""}`);
    },
    enabled: Boolean(clientId),
  });
}

export function useCreateDesignSystem() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { name: string; tokens: Record<string, unknown>; clientId?: string | null }) =>
      post<DesignSystem>("/design-systems", payload),
    onSuccess: (_data, vars) => {
      toast.success("Design system created");
      queryClient.invalidateQueries({ queryKey: ["design-systems", "list", vars.clientId] });
      if (vars.clientId) {
        queryClient.invalidateQueries({ queryKey: ["clients", vars.clientId] });
      }
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create design system";
      toast.error(message);
    },
  });
}

export function useUpdateDesignSystem() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      designSystemId,
      payload,
      clientId,
    }: {
      designSystemId: string;
      payload: Record<string, unknown>;
      clientId?: string | null;
    }) =>
      request<DesignSystem>(`/design-systems/${designSystemId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: (_data, vars) => {
      toast.success("Design system updated");
      queryClient.invalidateQueries({ queryKey: ["design-systems", "list", vars.clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update design system";
      toast.error(message);
    },
  });
}

export function useUploadDesignSystemLogo() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      designSystemId,
      clientId,
      file,
    }: {
      designSystemId: string;
      clientId: string;
      file: File;
    }) => {
      if (!designSystemId) throw new Error("Design system ID is required to upload a logo.");
      if (!clientId) throw new Error("Client ID is required to upload a logo.");
      if (!file) throw new Error("Logo file is required.");

      const token = await getToken({ template: clerkTokenTemplate, skipCache: true });
      const formData = new FormData();
      formData.append("file", file);
      const resp = await fetch(`${defaultBaseUrl}/design-systems/${designSystemId}/logo`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      if (!resp.ok) {
        throw new Error(await readUploadError(resp));
      }
      return (await resp.json()) as {
        assetId: string;
        publicId: string;
        url: string;
        designSystem: DesignSystem;
      };
    },
    onSuccess: (_data, vars) => {
      toast.success("Logo uploaded and applied");
      queryClient.invalidateQueries({ queryKey: ["design-systems", "list", vars.clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to upload logo";
      toast.error(message);
    },
  });
}

export function useDeleteDesignSystem() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ designSystemId }: { designSystemId: string; clientId?: string | null }) =>
      request<void>(`/design-systems/${designSystemId}`, { method: "DELETE" }),
    onSuccess: (_data, vars) => {
      toast.success("Design system deleted");
      queryClient.invalidateQueries({ queryKey: ["design-systems", "list", vars.clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to delete design system";
      toast.error(message);
    },
  });
}
