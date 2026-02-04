import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import type { ActivityLog, WorkflowDetail, WorkflowRun } from "@/types/common";
import { toast } from "@/components/ui/toast";

export function useWorkflows(filters?: { clientId?: string; productId?: string; campaignId?: string }) {
  const { get } = useApiClient();
  const path = (() => {
    if (!filters) return "/workflows";
    const params = new URLSearchParams();
    if (filters.clientId) params.set("clientId", filters.clientId);
    if (filters.productId) params.set("productId", filters.productId);
    if (filters.campaignId) params.set("campaignId", filters.campaignId);
    const qs = params.toString();
    return qs ? `/workflows?${qs}` : "/workflows";
  })();
  return useQuery<WorkflowRun[]>({
    queryKey: ["workflows", filters?.clientId ?? null, filters?.productId ?? null, filters?.campaignId ?? null],
    queryFn: () => get(path),
  });
}

export function useWorkflowLogs(workflowId?: string) {
  const { get } = useApiClient();
  return useQuery<ActivityLog[]>({
    queryKey: ["workflows", workflowId, "logs"],
    queryFn: () => get(`/workflows/${workflowId}/logs`),
    enabled: Boolean(workflowId),
  });
}

export function useWorkflowDetail(workflowId?: string) {
  const { get } = useApiClient();
  return useQuery<WorkflowDetail>({
    queryKey: ["workflows", workflowId, "detail"],
    queryFn: () => get(`/workflows/${workflowId}`),
    enabled: Boolean(workflowId),
  });
}

export function useWorkflowSignal(workflowId?: string) {
  const queryClient = useQueryClient();
  const { post } = useApiClient();

  return useMutation({
    mutationFn: async ({ signal, body }: { signal: string; body: Record<string, unknown> }) => {
      if (!workflowId) throw new Error("Workflow ID is required");
      return post(`/workflows/${workflowId}/signals/${signal}`, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      if (workflowId) {
        queryClient.invalidateQueries({ queryKey: ["workflows", workflowId, "logs"] });
        queryClient.invalidateQueries({ queryKey: ["workflows", workflowId, "detail"] });
        queryClient.invalidateQueries({ queryKey: ["workflows", workflowId] });
      }
      toast.success("Signal sent");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to send signal";
      toast.error(message);
    },
  });
}

export function useStopWorkflow() {
  const queryClient = useQueryClient();
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (workflowId: string) => post(`/workflows/${workflowId}/signals/stop`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      toast.success("Workflow stopped");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to stop workflow";
      toast.error(message);
    },
  });
}
