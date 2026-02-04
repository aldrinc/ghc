import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import type { Client } from "@/types/common";
import { toast } from "@/components/ui/toast";

export function useClients() {
  const { get } = useApiClient();
  return useQuery<Client[]>({
    queryKey: ["clients"],
    queryFn: () => get("/clients"),
  });
}

export function useClient(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<Client>({
    queryKey: ["clients", clientId],
    queryFn: () => get(`/clients/${clientId}`),
    enabled: Boolean(clientId),
  });
}

export function useCreateClient() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { name: string; industry?: string }) => post<Client>("/clients", payload),
    onSuccess: () => {
      toast.success("Client created");
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create client";
      toast.error(message);
    },
  });
}

export function useUpdateClient() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ clientId, payload }: { clientId: string; payload: Record<string, unknown> }) =>
      request<Client>(`/clients/${clientId}`, { method: "PATCH", body: JSON.stringify(payload) }),
    onSuccess: (_data, vars) => {
      toast.success("Client updated");
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      queryClient.invalidateQueries({ queryKey: ["clients", vars.clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update client";
      toast.error(message);
    },
  });
}

export function useStartOnboarding() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ clientId, payload }: { clientId: string; payload: Record<string, unknown> }) =>
      post<{
        workflow_run_id: string;
        temporal_workflow_id: string;
        product_id: string;
        product_name?: string;
      }>(`/clients/${clientId}/onboarding`, payload),
    onSuccess: () => {
      toast.success("Onboarding started");
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to start onboarding";
      toast.error(message);
    },
  });
}

export function useDeleteClient() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ clientId, confirmName }: { clientId: string; confirmName: string }) =>
      request(`/clients/${clientId}`, {
        method: "DELETE",
        body: JSON.stringify({ confirm: true, confirm_name: confirmName }),
      }),
    onSuccess: () => {
      toast.success("Workspace deleted");
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to delete workspace";
      toast.error(message);
    },
  });
}
