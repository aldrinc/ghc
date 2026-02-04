import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import type { DesignSystem } from "@/types/designSystems";
import { toast } from "@/components/ui/toast";

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
